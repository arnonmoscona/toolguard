"""
Apply accepted consolidation proposals to config files, comment-preservingly,
and produce a structured change report.

This module turns a list of :class:`~toolguard.tools.consolidate.ConsolidationProposal`
records into edits on the underlying config files and reports exactly what
changed.  It is the deterministic "apply" half of the maintenance core; deciding
*which* proposals to apply, refusing to run on a dirty git tree, and obtaining
the user's approval are the SKILL's responsibility, not this module's.

Reuse (no reimplementation)
---------------------------
- The comment-preserving file writers
  :func:`~toolguard.permission_migration.write_toml_config` and
  :func:`~toolguard.permission_migration.write_json_config` perform the
  actual section rewrite (TOML comments are preserved via
  :mod:`toolguard.rule_sort`; JSON is rewritten structurally).
- Current (raw, unresolved) permissions are read with the canonical
  :func:`toolguard.config.load_config_file` loader -- deliberately NOT from a
  loaded :class:`Configuration`, whose layer content may have been
  takeover-filtered (writing that back would silently drop the blanket allows
  takeover strips).
- The unified diff is produced with :func:`difflib.unified_diff` by rendering the
  change onto a throwaway copy, so a dry run never touches the real file.

Scope
-----
This slice applies ALLOW-list proposals only (the only kind
:func:`~toolguard.tools.consolidate.propose_consolidations` currently emits).  A
proposal whose target patterns are absent from the file (config drift) is skipped
and reported rather than applied.  A proposal is also skipped, with a "would
lose rule enrichment" reason, when applying it would require silently
resolving a genuine metadata CONTRADICTION among the file's own existing
entries for the pattern it would write (TOO-19 Phase 0a increment 9) -- see
:func:`_resolve_added_entry`.
"""

import difflib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from toolguard.config import load_config_file, wrap_tool_pattern
from toolguard.config_write_guard import verified_write_config
from toolguard.permission_migration import write_json_config, write_toml_config
from toolguard.rule_entry import (
    RuleEntry,
    merge_entries,
    normalize_entries_preserving,
    normalize_entry,
    real_patterns,
)
from toolguard.tools.consolidate import ConsolidationProposal


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileChange:
    """
    The outcome of applying proposals to a single config file.

    Attributes:
        path: The config file the proposals targeted.
        file_format: ``'toml'`` or ``'json'``.
        applied: Proposals that were successfully applied.
        skipped: ``(proposal, reason)`` pairs for proposals that were not applied
            (e.g. config drift, unsupported list type, missing file path).
        patterns_removed: Wrapped patterns (e.g. ``Bash(git diff:*)``) removed.
        patterns_added: Wrapped patterns added (the consolidated rules).
        diff: Unified diff of the file's text before vs after (empty when nothing
            changed).
        written: Whether the file was actually modified on disk (always ``False``
            for a dry run or a no-op).
    """

    path: Optional[Path]
    file_format: str
    applied: Tuple[ConsolidationProposal, ...]
    skipped: Tuple[Tuple[ConsolidationProposal, str], ...]
    patterns_removed: Tuple[str, ...]
    patterns_added: Tuple[str, ...]
    diff: str
    written: bool


@dataclass(frozen=True)
class ChangeReport:
    """
    The result of applying a batch of proposals across one or more files.

    Attributes:
        files: One :class:`FileChange` per distinct target file, in first-seen order.
    """

    files: Tuple[FileChange, ...]

    @property
    def total_applied(self) -> int:
        """Total number of proposals applied across all files."""
        return sum(len(f.applied) for f in self.files)

    @property
    def total_skipped(self) -> int:
        """Total number of proposals skipped across all files."""
        return sum(len(f.skipped) for f in self.files)

    @property
    def files_written(self) -> Tuple[FileChange, ...]:
        """The files that were actually modified on disk."""
        return tuple(f for f in self.files if f.written)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_raw_permissions(path: Path, file_format: str) -> Dict[str, List[RuleEntry]]:
    """
    Read the raw (unresolved, unfiltered) allow/deny/ask lists from a config file.

    Uses the canonical :func:`toolguard.config.load_config_file` loader so the
    values are exactly what is on disk -- NOT what a loaded :class:`Configuration`
    would expose (which may be takeover-filtered).  Missing keys yield empty lists.

    Every raw element is normalized into a :class:`~toolguard.rule_entry.RuleEntry`
    via :func:`~toolguard.rule_entry.normalize_entries_preserving` (TOO-19 Phase
    0a increment 8) -- an element that fails to normalize is preserved verbatim,
    never dropped: this reads a file that gets written back out (whole or in
    part) by :func:`_apply_to_file`, so silently losing an entry here would
    silently delete it from the user's config.

    Args:
        path: Config file path.
        file_format: ``'toml'`` or ``'json'``.

    Returns:
        Dict with ``'allow'``, ``'deny'``, ``'ask'`` keys mapping to lists of
        :class:`RuleEntry`.
    """
    empty: Dict[str, List[RuleEntry]] = {"allow": [], "deny": [], "ask": []}
    if not path.exists():
        return empty

    data = load_config_file(path, file_format)

    if not isinstance(data, dict):
        return empty
    perms = data.get("permissions", {})
    if not isinstance(perms, dict):
        return empty

    return {
        "allow": list(
            normalize_entries_preserving(perms.get("allow", []) or [], is_native=False)
        ),
        "deny": list(
            normalize_entries_preserving(perms.get("deny", []) or [], is_native=False)
        ),
        "ask": list(
            normalize_entries_preserving(perms.get("ask", []) or [], is_native=False)
        ),
    }


def _render_via_writer(
    path: Path, file_format: str, new_permissions: Dict[str, List[RuleEntry]]
) -> str:
    """
    Render the post-change file text WITHOUT modifying the real file.

    Copies the original file into a temporary directory, runs the comment-preserving
    writer on the copy, and returns the resulting text.  This lets a dry run
    compute the exact diff the real apply would produce while leaving the target
    untouched.

    Args:
        path: The real config file (read for its current content/comments).
        file_format: ``'toml'`` or ``'json'``.
        new_permissions: The new allow/deny/ask lists to write.

    Returns:
        The full text the file would contain after the change.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir) / (path.name or "config")
        if path.exists():
            tmp.write_text(path.read_text())
        if file_format == "json":
            write_json_config(tmp, new_permissions)
        else:
            write_toml_config(tmp, new_permissions)
        return tmp.read_text()


def _resolve_added_entry(
    allow: List[RuleEntry], added_wrapped: str
) -> Tuple[Optional[str], Tuple[RuleEntry, ...]]:
    """
    Resolve what a proposal's ``added_pattern`` should write into ``allow``.

    A :class:`ConsolidationProposal` always adds a PLAIN (metadata-free)
    pattern -- see its ``added_pattern`` docstring -- but the FILE may
    already carry one or more entries for that exact pattern, possibly
    structured (e.g. a prior manual annotation, or leftovers from an earlier
    partial consolidation run). This delegates entirely to
    :func:`~toolguard.rule_entry.merge_entries` (the single source of truth
    for bare-vs-structured / union / contradiction semantics -- see its
    docstring, cases 1-3) rather than re-deriving those rules here:

    - Case 1 (bare dropped, structured wins) and case 2 (multiple structured,
      compatible metadata -> union merge) resolve with no conflict -- safe
      to apply.
    - Case 3 (a genuine metadata CONTRADICTION -- same key, different values
      -- among the file's own existing entries for this pattern) means
      writing this proposal's result would silently discard one side of that
      contradiction. This is the ONLY case that refuses the proposal.

    Args:
        allow: The current allow list (as read from the file, or as already
            mutated by earlier proposals in this batch).
        added_wrapped: The wrapped pattern (e.g. ``"Bash([regex]...)"``) this
            proposal wants to add.

    Returns:
        A ``(skip_reason, resolved_entries)`` pair. ``skip_reason`` is
        ``None`` when it is safe to apply, in which case ``resolved_entries``
        is the merge_entries-consolidated tuple of entries that should
        replace every existing ``allow`` entry for ``added_wrapped`` (in
        practice always exactly one entry, since a single pattern group with
        no conflict always collapses to one). When refused, ``skip_reason``
        explains why (containing the literal phrase "would lose rule
        enrichment") and ``resolved_entries`` is empty.
    """
    new_entry, _issues = normalize_entry(added_wrapped, is_native=False)
    if new_entry is None:
        new_entry = RuleEntry(pattern=added_wrapped, raw=added_wrapped)

    existing = [entry for entry in allow if entry.pattern == added_wrapped]
    outcome = merge_entries(existing + [new_entry])

    if outcome.conflicts:
        conflict = outcome.conflicts[0]
        reason = (
            "would lose rule enrichment: existing entries for "
            f"{added_wrapped!r} disagree on metadata key {conflict.key!r}"
        )
        return reason, ()

    return None, outcome.entries


def _apply_to_file(
    path: Optional[Path],
    file_format: str,
    proposals: List[ConsolidationProposal],
    dry_run: bool,
) -> FileChange:
    """
    Apply all proposals targeting a single file and return the outcome.

    Each allow-list proposal removes its ``removed_patterns`` (and appends its
    ``added_pattern``) from the file's allow list.  A proposal whose removed
    patterns are not all present in the file is skipped (config drift).  A
    proposal whose ``added_pattern`` would silently discard a genuine
    metadata contradiction among the file's own existing entries for that
    pattern is also skipped -- see :func:`_resolve_added_entry` (TOO-19 Phase
    0a increment 9).  The file is rewritten only when at least one proposal
    applied, the content actually changed, and ``dry_run`` is False.

    Args:
        path: Target config file (``None`` is reported as a skip for all proposals).
        file_format: ``'toml'`` or ``'json'``.
        proposals: Proposals whose provenance points at this file.
        dry_run: When True, compute diffs/report but write nothing.

    Returns:
        A :class:`FileChange` describing what was (or would be) done.
    """
    if path is None:
        return FileChange(
            path=None,
            file_format=file_format,
            applied=(),
            skipped=tuple((p, "proposal has no file path") for p in proposals),
            patterns_removed=(),
            patterns_added=(),
            diff="",
            written=False,
        )

    raw = _read_raw_permissions(path, file_format)
    allow = list(raw["allow"])  # List[RuleEntry]

    applied: List[ConsolidationProposal] = []
    skipped: List[Tuple[ConsolidationProposal, str]] = []
    removed_all: List[str] = []
    added_all: List[str] = []

    for prop in proposals:
        if prop.list_type != "allow":
            skipped.append(
                (prop, f"unsupported list_type {prop.list_type!r} (allow only)")
            )
            continue

        removed_wrapped = [
            wrap_tool_pattern(prop.tool, body) for body in prop.removed_patterns
        ]
        # `allow` holds RuleEntry (TOO-19 Phase 0a increment 8), so membership
        # and removal are keyed on `.pattern` (comparison #1, "same RULE" --
        # see RuleEntry.identity()'s docstring), recomputed each iteration
        # since `allow` mutates as proposals in this loop are applied in order.
        allow_patterns = [entry.pattern for entry in allow]
        missing = [w for w in removed_wrapped if w not in allow_patterns]
        if missing:
            skipped.append((prop, f"patterns not found in file: {missing}"))
            continue

        # Enrichment guard (TOO-19 Phase 0a increment 9): resolved BEFORE any
        # mutation of `allow`, so a refused proposal leaves the file
        # untouched rather than applying half of it. See
        # _resolve_added_entry's docstring for the case-1/2/3 semantics --
        # only a genuine case-3 contradiction refuses.
        added_wrapped: Optional[str] = None
        resolved_added_entries: Tuple[RuleEntry, ...] = ()
        if prop.added_pattern is not None:
            added_wrapped = wrap_tool_pattern(prop.tool, prop.added_pattern)
            skip_reason, resolved_added_entries = _resolve_added_entry(
                allow, added_wrapped
            )
            if skip_reason is not None:
                skipped.append((prop, skip_reason))
                continue

        for wrapped in removed_wrapped:
            # Remove exactly one occurrence per removed pattern (mirrors
            # list.remove()'s first-match semantics from before this entries
            # widened from str to RuleEntry).
            for i, entry in enumerate(allow):
                if entry.pattern == wrapped:
                    del allow[i]
                    break
            removed_all.append(wrapped)

        if added_wrapped is not None:
            existing_at_added = [e for e in allow if e.pattern == added_wrapped]
            if list(resolved_added_entries) != existing_at_added:
                # Only rewrite this pattern's entries when the resolved
                # (merge_entries-consolidated) result actually differs from
                # what's already there -- avoids reordering/diff noise for
                # the common case of a brand-new pattern or a true no-op
                # re-application.
                allow[:] = [e for e in allow if e.pattern != added_wrapped]
                allow.extend(resolved_added_entries)
            added_all.append(added_wrapped)

        applied.append(prop)

    new_permissions = {
        "allow": allow,
        "deny": list(raw["deny"]),
        "ask": list(raw["ask"]),
    }

    old_text = path.read_text() if path.exists() else ""
    new_text = _render_via_writer(path, file_format, new_permissions)

    diff = ""
    if old_text != new_text:
        diff = "".join(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
        )

    written = False
    if applied and not dry_run and old_text != new_text:
        # Route through the same self-protection gate write_toml_config/
        # write_json_config already use internally (TOO-19 corrective
        # change): new_text was rendered onto a throwaway temp copy by
        # _render_via_writer, so this is the first time it is written to the
        # REAL target path -- refuse rather than write if it somehow fails to
        # parse or would drop one of new_permissions's own patterns.
        # real_patterns() (TOO-19 review fix) drops any synthesized-pattern
        # entry (see RuleEntry.synthesized_pattern's docstring) -- a
        # malformed entry `_read_raw_permissions` preserved verbatim earlier
        # would otherwise wrongly refuse this write, since its `repr(raw)`
        # pattern can never appear in `new_text`.
        expected_patterns = [
            pattern
            for entries in new_permissions.values()
            for pattern in real_patterns(entries)
        ]
        verified_write_config(
            path, new_text, file_format, expected_patterns=expected_patterns
        )
        written = True

    return FileChange(
        path=path,
        file_format=file_format,
        applied=tuple(applied),
        skipped=tuple(skipped),
        patterns_removed=tuple(removed_all),
        patterns_added=tuple(added_all),
        diff=diff,
        written=written,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_proposals(
    proposals: List[ConsolidationProposal],
    *,
    dry_run: bool = False,
) -> ChangeReport:
    """
    Apply consolidation proposals to their config files and report the changes.

    Proposals are grouped by target file (from each proposal's
    ``layer_provenance``) and applied per file.  With ``dry_run=True`` nothing is
    written, but the diffs and the full report are still produced -- this is what
    a skill uses to show the user the change before asking for approval.

    Args:
        proposals: Accepted proposals to apply (allow-list proposals in this slice).
        dry_run: When True, compute and report the change without writing any file.

    Returns:
        A :class:`ChangeReport`, one :class:`FileChange` per distinct target file
        in first-seen order.
    """
    by_file: Dict[Tuple[Optional[Path], str], List[ConsolidationProposal]] = {}
    order: List[Tuple[Optional[Path], str]] = []

    for prop in proposals:
        path = prop.layer_provenance.path
        fmt = prop.layer_provenance.file_format
        key = (path, fmt)
        if key not in by_file:
            by_file[key] = []
            order.append(key)
        by_file[key].append(prop)

    files = [
        _apply_to_file(path, fmt, by_file[(path, fmt)], dry_run)
        for (path, fmt) in order
    ]
    return ChangeReport(files=tuple(files))


def render_change_report(report: ChangeReport, fmt: str = "text") -> str:
    """
    Render a :class:`ChangeReport` as a human-readable ASCII summary.

    Args:
        report: The change report to render.
        fmt: ``'text'`` (default) or ``'markdown'``.

    Returns:
        An ASCII-only string summarising, per file, the applied and skipped
        proposals and the patterns removed/added.  Diffs are NOT inlined here
        (they are available on each :class:`FileChange.diff` for a caller that
        wants to display them).

    Raises:
        ValueError: When ``fmt`` is not ``'text'`` or ``'markdown'``.
    """
    if fmt not in ("text", "markdown"):
        raise ValueError(f"unknown format {fmt!r} (expected 'text' or 'markdown')")

    md = fmt == "markdown"
    lines: List[str] = []
    title = "Toolguard Rule Change Report"
    lines.append(f"# {title}" if md else title)
    if not md:
        lines.append("=" * len(title))
    lines.append("")
    lines.append(
        f"{report.total_applied} applied, {report.total_skipped} skipped, "
        f"{len(report.files_written)} file(s) written."
    )
    lines.append("")

    for fchange in report.files:
        path_label = str(fchange.path) if fchange.path is not None else "(no path)"
        status = "written" if fchange.written else "not written"
        header = f"{path_label} [{fchange.file_format}] -- {status}"
        lines.append(f"## {header}" if md else header)

        for prop in fchange.applied:
            removed = ", ".join(
                wrap_tool_pattern(prop.tool, b) for b in prop.removed_patterns
            )
            if prop.added_pattern is not None:
                lines.append(
                    f"  + {prop.kind}: {removed} -> {wrap_tool_pattern(prop.tool, prop.added_pattern)}"
                )
            else:
                lines.append(f"  + {prop.kind}: drop {removed}")

        for prop, reason in fchange.skipped:
            removed = ", ".join(
                wrap_tool_pattern(prop.tool, b) for b in prop.removed_patterns
            )
            lines.append(f"  - skipped {prop.kind} ({removed}): {reason}")

        lines.append("")

    return "\n".join(lines)
