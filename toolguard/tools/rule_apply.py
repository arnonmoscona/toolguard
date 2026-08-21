"""
Apply accepted consolidation proposals to config files and report what changed.

Turns :class:`~toolguard.tools.consolidate.ConsolidationProposal` records into
edits on the config files their provenance names.  It applies the proposals it
is given; whether they are worth making is not decided here.

``allow``-list proposals only -- a proposal naming any other list is skipped
and reported.

The whole ``permissions`` section is rewritten from what
:func:`_read_raw_permissions` returns, so an entry missing from that read is
deleted from the user's config.
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
        patterns_removed: Each applied proposal's ``removed_patterns``, wrapped
            (e.g. ``Bash(git diff:*)``).
        patterns_added: Each applied proposal's ``added_pattern``, wrapped;
            a pure-drop proposal contributes nothing here.
        diff: Unified diff of the file's current text against the text this
            module would write.  Re-rendering is not identity, so this can be
            non-empty even when no proposal applied.
        written: Whether the file was modified on disk.  ``False`` for a dry
            run, when no proposal applied, or when the rendered text matched
            the file's current text.
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
        files: One :class:`FileChange` per distinct ``(path, format)`` the
            proposals name, in first-seen order.
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
    Read a config file's allow/deny/ask lists, unresolved and unfiltered.

    :func:`~toolguard.rule_entry.normalize_entries_preserving` keeps an element
    it cannot parse rather than dropping it, which is what this read needs: the
    lists returned here are the ones written back.

    Args:
        path: Config file path.
        file_format: ``'toml'`` or ``'json'``.

    Returns:
        Dict with ``'allow'``, ``'deny'``, ``'ask'`` keys mapping to lists of
        :class:`RuleEntry`.  All three are empty when the file is absent, or
        when it has no ``permissions`` table.
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

    Copies the original into a temporary directory, runs the comment-preserving
    writer on the copy, and returns the result.  A real apply writes this text
    verbatim, so a dry run's diff is the one it would produce.

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

    The proposal contributes a bare pattern string, but the file may already
    carry entries for that same pattern, some of them structured. Grouping,
    union and contradiction semantics all belong to
    :func:`~toolguard.rule_entry.merge_entries`; this only turns its outcome
    into an apply-or-refuse answer.

    Args:
        allow: The current allow list (as read from the file, or as already
            mutated by earlier proposals in this batch).
        added_wrapped: The wrapped pattern (e.g. ``"Bash([regex]...)"``) this
            proposal wants to add.

    Returns:
        A ``(skip_reason, resolved_entries)`` pair. On a clean merge
        ``skip_reason`` is ``None`` and ``resolved_entries`` holds the single
        entry that should replace every existing ``allow`` entry for
        ``added_wrapped`` -- one entry, because every input shares one
        pattern. The proposal is refused instead (``skip_reason`` set,
        ``resolved_entries`` empty) when :func:`merge_entries` reports a
        metadata conflict -- ``skip_reason`` then names the contended key and
        contains the literal phrase "would lose rule enrichment" -- or when
        :func:`~toolguard.rule_entry.normalize_entry` rejects ``added_wrapped``
        itself (e.g. an embedded newline), in which case ``skip_reason`` is
        that rejection's message.
    """
    new_entry, issues = normalize_entry(added_wrapped, is_native=False)
    if new_entry is None:
        return issues[0].message, ()

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

    A proposal is skipped, with its reason recorded, when it names a list
    other than ``allow``, when any of its ``removed_patterns`` is absent from
    the file (config drift), when :func:`_resolve_added_entry` refuses its
    ``added_pattern``, or when this file's post-change text cannot even be
    RENDERED (e.g. its pre-existing content was never valid TOML/JSON) -- the
    last case skips every proposal for this file, since none of them actually
    took effect.  The rest are applied in order to one in-memory copy of the
    allow list, so each sees its predecessors' effect.

    The file is written only when at least one proposal applied, ``dry_run``
    is False, and the rendered text differs from the file's current text.  A
    failure in that REAL write (as opposed to the throwaway-copy render
    above) propagates rather than being caught -- see the write call below.

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
    allow = list(raw["allow"])

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
        # Recomputed per proposal: `allow` mutates as earlier ones apply.
        allow_patterns = [entry.pattern for entry in allow]
        missing = [w for w in removed_wrapped if w not in allow_patterns]
        if missing:
            skipped.append((prop, f"patterns not found in file: {missing}"))
            continue

        # Resolved BEFORE any mutation of `allow`, so a refused proposal
        # contributes nothing rather than half of itself.
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
            # One occurrence per removed pattern, not every match.
            for i, entry in enumerate(allow):
                if entry.pattern == wrapped:
                    del allow[i]
                    break
            removed_all.append(wrapped)

        if added_wrapped is not None:
            existing_at_added = [e for e in allow if e.pattern == added_wrapped]
            if list(resolved_added_entries) != existing_at_added:
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
    try:
        # A throwaway-copy render (see _render_via_writer) has no side
        # effects on the real file, so a failure here -- e.g. this file's
        # OWN pre-existing content was never valid TOML/JSON to begin with
        # -- is reported as a skip rather than aborting the whole batch and
        # losing whatever earlier files already accomplished. A failure in
        # the REAL write below is a different matter and is NOT caught here:
        # see this function's docstring.
        new_text = _render_via_writer(path, file_format, new_permissions)
    except Exception as exc:  # noqa: BLE001 -- render-only, no side effects to protect
        reason = f"could not render this file: {exc}"
        return FileChange(
            path=path,
            file_format=file_format,
            applied=(),
            skipped=tuple((p, reason) for p in proposals),
            patterns_removed=(),
            patterns_added=(),
            diff="",
            written=False,
        )

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
        # _render_via_writer produced `new_text` on a throwaway copy, so this
        # is the first write to the real path -- take it through the write
        # guard rather than writing the text directly.
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
    ``layer_provenance``) and applied per file.  ``dry_run=True`` still
    produces the diffs and the full report; only the writes are withheld.

    A file whose post-change text cannot even be rendered does not abort the
    batch -- see :func:`_apply_to_file`. A failure in an actual write DOES
    propagate out of this function unswallowed, so a caller can tell "this
    file's own content was never valid" apart from "a write that should have
    succeeded did not."

    Args:
        proposals: Accepted proposals to apply.
        dry_run: When True, compute and report the change without writing any file.

    Returns:
        A :class:`ChangeReport`, one :class:`FileChange` per target file, in
        first-seen order.
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
    Render a :class:`ChangeReport` as a human-readable summary.

    Args:
        report: The change report to render.
        fmt: ``'text'`` (default) or ``'markdown'``.

    Returns:
        A per-file summary of the applied and skipped proposals and the
        patterns removed/added.  Diffs are NOT inlined here -- each
        :class:`FileChange` carries its own.

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
            verification = prop.verification.value.upper()
            if prop.added_pattern is not None:
                added = wrap_tool_pattern(prop.tool, prop.added_pattern)
                lines.append(f"  + {prop.kind}: {removed} -> {added} [{verification}]")
            else:
                lines.append(f"  + {prop.kind}: drop {removed} [{verification}]")

        for prop, reason in fchange.skipped:
            removed = ", ".join(
                wrap_tool_pattern(prop.tool, b) for b in prop.removed_patterns
            )
            lines.append(f"  - skipped {prop.kind} ({removed}): {reason}")

        lines.append("")

    return "\n".join(lines)
