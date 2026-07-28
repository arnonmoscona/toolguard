"""
Maintenance aggregator: compose the rule-maintenance engines into one report.

This is the deterministic backbone the maintenance skill/CLI sit on -- the
counterpart of :mod:`toolguard.tools.security_audit` for the maintenance side.
It does not apply anything and makes no judgement: it runs each tested engine
over the resolved configuration and gathers their findings into a single
structured :class:`MaintenanceReport`.

For each governed tool it collects:

* **redundancies** -- exact/normalised duplicates and corpus-backed subsumption
  (:func:`toolguard.tools.redundancy.find_redundancy`).
* **consolidations** -- strict, equivalence-preserving merges, families 1-2
  (:func:`toolguard.tools.consolidate.propose_consolidations`).
* **broadenings** -- agent-judged, deliberately-widening merges with evidence,
  families 3-4 (:func:`toolguard.tools.consolidate.propose_broadening_consolidations`).
* **cross-layer redundancies** -- a specific rule already covered by a broader
  layer (:func:`toolguard.tools.hierarchy.find_cross_layer_redundancies`).

and, once for the whole config, the corpus **mining** report
(:func:`toolguard.tools.mining.mine_rule_candidates`).

Consolidations and cross-layer findings are replay-verified (decision-neutral
over the corpus) and redundancies are exact/normalised duplicates -- but that
verification is EVIDENCE, not consent: even a decision-neutral merge may belong
at a different level, or be one the user wants left alone. Nothing here is
auto-applied. Broadenings and mining candidates additionally need the
security-audit lens. Every apply decision is the user's, made through the skill
conversation; this module only gathers the evidence.
"""

import argparse
import difflib
import json
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from toolguard.config import Configuration, Provenance
from toolguard.config_write_guard import verified_write_config
from toolguard.constants import GOVERNED_TOOLS
from toolguard.rule_sort import (
    find_section_boundaries,
    is_synthetic_pattern,
    parse_permissions_section_with_comments,
)
from toolguard.tools.annotate import annotate_config_file, clarity_annotations
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions
from toolguard.tools.config_access import load_config, nosecurity_reason_for
from toolguard.tools.corpus import harvest_corpus
from toolguard.tools.decision_ledger import (
    LedgerDecision,
    LedgerError,
    decision_to_dict,
    load_merged,
    new_decision,
    record_decision,
)
from toolguard.tools.edit_proposal import (
    ACTION_REPLACE,
    EditProposal,
    RuleEdit,
    edit_proposal_to_dict,
)
from toolguard.tools.migration_gate import migration_preflight
from toolguard.tools.rule_apply import (
    ChangeReport,
    apply_proposals,
    render_change_report,
)
from toolguard.tools.consolidate import (
    BroadeningProposal,
    ConsolidationProposal,
    propose_broadening_consolidations,
    propose_consolidations,
)
from toolguard.tools.hierarchy import (
    CrossLayerRedundancy,
    find_cross_layer_redundancies,
)
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.mining import (
    MiningReport,
    mine_rule_candidates,
    render_mining_report,
)
from toolguard.tools.redundancy import RedundancyFinding, find_redundancy
from toolguard.tools.replay import EntryDiff, ReplayDiff, replay


@dataclass(frozen=True)
class ToolMaintenance:
    """
    All maintenance findings for a single governed tool.

    Attributes:
        tool: The tool name (e.g. ``'Bash'``).
        redundancies: Duplicate/subsumed rule findings (candidates to drop --
            the user decides).
        consolidations: Strict, equivalence-preserving merge proposals (families
            1-2; replay-verified but never auto-applied -- the user decides).
        broadenings: Agent-judged widening proposals with evidence (families 3-4;
            must be judged, never auto-applied).
        cross_layer_redundancies: Specific rules already covered by a broader
            layer (candidate to drop the specific copy -- the user decides).
        interactions: Confusing same-file rule interactions (clarity findings;
            informational -- they explain non-obvious resolution, not a fix).
    """

    tool: str
    redundancies: Tuple[RedundancyFinding, ...]
    consolidations: Tuple[ConsolidationProposal, ...]
    broadenings: Tuple[BroadeningProposal, ...]
    cross_layer_redundancies: Tuple[CrossLayerRedundancy, ...]
    interactions: Tuple[InteractionFinding, ...]

    @property
    def total(self) -> int:
        """Total number of findings across all categories for this tool."""
        return (
            len(self.redundancies)
            + len(self.consolidations)
            + len(self.broadenings)
            + len(self.cross_layer_redundancies)
            + len(self.interactions)
        )

    @property
    def has_findings(self) -> bool:
        """Whether this tool produced any maintenance finding."""
        return self.total > 0


@dataclass(frozen=True)
class MaintenanceReport:
    """
    Aggregate maintenance report across all inspected tools plus corpus mining.

    Attributes:
        tools: Per-tool maintenance findings, in the order inspected.
        mining: The config-wide corpus mining report (empty when no corpus).
    """

    tools: Tuple[ToolMaintenance, ...]
    mining: MiningReport

    @property
    def total_findings(self) -> int:
        """Total per-tool findings (excludes mining candidates)."""
        return sum(t.total for t in self.tools)

    @property
    def has_any_findings(self) -> bool:
        """Whether there is anything to report (per-tool findings or mining)."""
        return self.total_findings > 0 or bool(self.mining.groups)

    def tools_with_findings(self) -> List[ToolMaintenance]:
        """Return only the per-tool reports that produced at least one finding."""
        return [t for t in self.tools if t.has_findings]


def run_maintenance(
    config: Configuration,
    tools: Optional[Sequence[str]] = None,
    corpus: Optional[List[LogEntry]] = None,
) -> MaintenanceReport:
    """
    Run every maintenance engine over ``config`` and aggregate the findings.

    Args:
        config: The resolved configuration to inspect.
        tools: Tool names to inspect.  Defaults to the governed tools, in sorted
            order for deterministic output.
        corpus: Optional harvested command corpus.  When supplied it enables
            corpus-backed redundancy, broadening evidence, and mining; when
            ``None`` those fall back to static-only / empty results.

    Returns:
        A :class:`MaintenanceReport` aggregating all findings.  Nothing is applied.
    """
    target_tools = list(tools) if tools is not None else sorted(GOVERNED_TOOLS)

    tool_reports: List[ToolMaintenance] = []
    for tool in target_tools:
        tool_reports.append(
            ToolMaintenance(
                tool=tool,
                redundancies=tuple(find_redundancy(config, tool, corpus)),
                consolidations=tuple(propose_consolidations(config, tool)),
                broadenings=tuple(
                    propose_broadening_consolidations(config, tool, corpus)
                ),
                cross_layer_redundancies=tuple(
                    find_cross_layer_redundancies(config, tool)
                ),
                interactions=tuple(find_confusing_interactions(config, tool)),
            )
        )

    mining = mine_rule_candidates(config, corpus or [])
    return MaintenanceReport(tools=tuple(tool_reports), mining=mining)


def _headline(report: MaintenanceReport) -> str:
    """
    Build the one-line headline summary of a maintenance report.

    Args:
        report: The report to summarise.

    Returns:
        A compact count summary across all categories.
    """
    redundancies = sum(len(t.redundancies) for t in report.tools)
    consolidations = sum(len(t.consolidations) for t in report.tools)
    broadenings = sum(len(t.broadenings) for t in report.tools)
    cross_layer = sum(len(t.cross_layer_redundancies) for t in report.tools)
    interactions = sum(len(t.interactions) for t in report.tools)
    return (
        f"{redundancies} redundancy, {consolidations} strict-consolidation, "
        f"{broadenings} broadening (agent-judged), {cross_layer} cross-layer, "
        f"{interactions} clarity, {len(report.mining.groups)} mining candidate(s)."
    )


def render(report: MaintenanceReport, fmt: str = "markdown") -> str:
    """
    Render a maintenance report as a human-readable summary.

    This is the SUMMARY view (counts + per-category listing).  The verbose,
    paste-ready per-file recommendation with application modes is produced by the
    skill/CLI layer on top of this report, not here.

    Args:
        report: The report to render.
        fmt: ``'markdown'`` (default) or ``'text'``.

    Returns:
        The rendered report string.
    """
    lines: List[str] = []
    bullet = "- " if fmt == "markdown" else "  * "
    heading = "## " if fmt == "markdown" else ""

    lines.append(f"{heading}Maintenance summary")
    lines.append(_headline(report))
    if not report.has_any_findings:
        lines.append("")
        lines.append("No maintenance findings.")
        return "\n".join(lines)

    for tool_report in report.tools_with_findings():
        lines.append("")
        lines.append(f"{heading}{tool_report.tool}")
        for finding in tool_report.redundancies:
            lines.append(
                f"{bullet}redundant: `{finding.redundant_pattern}` -- {finding.note}"
            )
        for proposal in tool_report.consolidations:
            lines.append(
                f"{bullet}consolidate ({proposal.kind}): "
                f"{list(proposal.removed_patterns)} -> `{proposal.added_pattern}`"
            )
        for proposal in tool_report.broadenings:
            lines.append(
                f"{bullet}broaden ({proposal.kind}, AGENT-JUDGED): "
                f"-> `{proposal.added_pattern}`; "
                f"{len(proposal.newly_admitted_commands)} newly-admitted, "
                f"{len(proposal.overlaps_guard_rules)} guard-overlap(s)"
            )
        for redundancy in tool_report.cross_layer_redundancies:
            lines.append(
                f"{bullet}cross-layer redundant: `{redundancy.pattern}` -- "
                f"{redundancy.note}"
            )
        for interaction in tool_report.interactions:
            lines.append(
                f"{bullet}clarity ({interaction.kind}): {interaction.explanation}"
            )

    if report.mining.groups:
        lines.append("")
        lines.append(f"{heading}Corpus mining")
        lines.append(render_mining_report(report.mining, "text"))

    return "\n".join(lines)


def _provenance_to_dict(provenance: Optional[Provenance]) -> Optional[Dict[str, Any]]:
    """
    Serialize a :class:`~toolguard.config.Provenance` to a JSON-safe dict.

    Args:
        provenance: The provenance to serialize, or ``None``.

    Returns:
        A dict with the raw provenance fields plus a human-readable ``describe``
        string, or ``None`` when ``provenance`` is ``None``.
    """
    if provenance is None:
        return None
    return {
        "level": provenance.level,
        "source_type": provenance.source_type,
        "file_format": provenance.file_format,
        "path": str(provenance.path),
        "specificity": provenance.specificity,
        "describe": provenance.describe(),
    }


def _tool_to_dict(tool_report: ToolMaintenance) -> Dict[str, Any]:
    """
    Serialize a :class:`ToolMaintenance` to a JSON-safe dict.

    Args:
        tool_report: The per-tool findings to serialize.

    Returns:
        A dict mirroring the dataclass, with provenances expanded and tuples
        rendered as lists.
    """
    return {
        "tool": tool_report.tool,
        "total": tool_report.total,
        "redundancies": [
            {
                "redundant_pattern": r.redundant_pattern,
                "provenance": _provenance_to_dict(r.provenance),
                "kind": r.kind,
                "list_type": r.list_type,
                "tool": r.tool,
                "covered_by": r.covered_by,
                "note": r.note,
            }
            for r in tool_report.redundancies
        ],
        "consolidations": [
            {
                "kind": c.kind,
                "tool": c.tool,
                "list_type": c.list_type,
                "layer_provenance": _provenance_to_dict(c.layer_provenance),
                "removed_patterns": list(c.removed_patterns),
                "added_pattern": c.added_pattern,
                "rationale": c.rationale,
                "replay_summary": c.replay_summary,
            }
            for c in tool_report.consolidations
        ],
        "broadenings": [
            {
                "kind": b.kind,
                "tool": b.tool,
                "list_type": b.list_type,
                "layer_provenance": _provenance_to_dict(b.layer_provenance),
                "removed_patterns": list(b.removed_patterns),
                "added_pattern": b.added_pattern,
                "rationale": b.rationale,
                "newly_admitted_commands": list(b.newly_admitted_commands),
                "overlaps_guard_rules": list(b.overlaps_guard_rules),
                "probe_admitted_surface": list(b.probe_admitted_surface),
            }
            for b in tool_report.broadenings
        ],
        "cross_layer_redundancies": [
            {
                "tool": x.tool,
                "pattern": x.pattern,
                "redundant_provenance": _provenance_to_dict(x.redundant_provenance),
                "covered_by_provenance": _provenance_to_dict(x.covered_by_provenance),
                "note": x.note,
            }
            for x in tool_report.cross_layer_redundancies
        ],
        "interactions": [
            {
                "tool": i.tool,
                "provenance": _provenance_to_dict(i.provenance),
                "kind": i.kind,
                "allow_pattern": i.allow_pattern,
                "guard_section": i.guard_section,
                "guard_pattern": i.guard_pattern,
                "explanation": i.explanation,
                "guard_provenance": (
                    _provenance_to_dict(i.guard_provenance)
                    if i.guard_provenance is not None
                    else None
                ),
            }
            for i in tool_report.interactions
        ],
    }


def report_to_dict(report: MaintenanceReport) -> Dict[str, Any]:
    """
    Serialize a :class:`MaintenanceReport` to a JSON-safe dict.

    This is the structured contract the maintenance skill (and any AI-assisted
    pass) consumes instead of re-parsing the rendered text.  Provenances are
    expanded to dicts, tuples to lists, and corpus-mining groups are included.

    Args:
        report: The maintenance report to serialize.

    Returns:
        A JSON-serializable dict capturing the whole report.
    """
    return {
        "total_findings": report.total_findings,
        "has_any_findings": report.has_any_findings,
        "tools": [_tool_to_dict(t) for t in report.tools],
        "mining": {
            "groups": [
                {
                    "tool": g.tool,
                    "command_key": g.command_key,
                    "signal": g.signal,
                    "distinct_commands": list(g.distinct_commands),
                    "occurrences": g.occurrences,
                    "current_verdict": g.current_verdict,
                    "observed_counts": dict(g.observed_counts),
                }
                for g in report.mining.groups
            ],
        },
    }


def collect_consolidations(report: MaintenanceReport) -> List[ConsolidationProposal]:
    """
    Flatten every tool's strict consolidation proposals into one list.

    Only :class:`~toolguard.tools.consolidate.ConsolidationProposal` records are
    returned -- the replay-verified (decision-neutral over the corpus) allow-list
    merges that the apply path (:func:`~toolguard.tools.rule_apply.apply_proposals`)
    can enact once the user has approved them.
    Agent-judged broadenings and the informational findings (redundancies,
    cross-layer, clarity interactions) are deliberately excluded: they are
    reported for human action, not auto-applied.

    Args:
        report: The maintenance report to harvest proposals from.

    Returns:
        All consolidation proposals across tools, in tool/report order.
    """
    return [c for tool in report.tools for c in tool.consolidations]


def consolidation_to_edit_proposal(prop: ConsolidationProposal) -> EditProposal:
    """
    Express a consolidation as a general :class:`~toolguard.tools.edit_proposal.EditProposal`.

    A consolidation replaces a family of allow patterns with one merged pattern at
    a single layer; that maps to a ``replace`` edit on the ``list_type`` list.
    The shared model lets the maintenance skill hand its proposed changes to
    ``toolguard-audit --edits`` for an as-if-enacted security review before writing.

    Args:
        prop: The consolidation proposal to convert.

    Returns:
        The equivalent :class:`EditProposal` (a single-edit ``replace``).
    """
    return EditProposal(
        action=ACTION_REPLACE,
        tool=prop.tool,
        rationale=prop.rationale,
        edits=(
            RuleEdit(
                tool=prop.tool,
                list_type=prop.list_type,
                provenance=prop.layer_provenance,
                removed_patterns=tuple(prop.removed_patterns),
                added_patterns=(prop.added_pattern,) if prop.added_pattern else (),
            ),
        ),
        origin=f"consolidation:{prop.kind}",
    )


def change_report_to_dict(change: ChangeReport) -> Dict[str, Any]:
    """
    Serialize a :class:`~toolguard.tools.rule_apply.ChangeReport` to a dict.

    This is the structured contract for the apply path: it lets the maintenance
    skill present each file's diff and applied/skipped proposals without
    re-parsing the rendered text.

    Args:
        change: The change report (from a dry-run or real apply) to serialize.

    Returns:
        A JSON-serializable dict capturing the per-file outcome, including the
        unified diff for each changed file.
    """
    return {
        "total_applied": change.total_applied,
        "total_skipped": change.total_skipped,
        "files_written": [str(f.path) for f in change.files_written if f.path],
        "files": [
            {
                "path": str(f.path) if f.path is not None else None,
                "file_format": f.file_format,
                "applied": [
                    {
                        "removed_patterns": list(p.removed_patterns),
                        "added_pattern": p.added_pattern,
                        "rationale": p.rationale,
                    }
                    for p in f.applied
                ],
                "skipped": [
                    {"removed_patterns": list(p.removed_patterns), "reason": reason}
                    for p, reason in f.skipped
                ],
                "patterns_removed": list(f.patterns_removed),
                "patterns_added": list(f.patterns_added),
                "diff": f.diff,
                "written": f.written,
            }
            for f in change.files
        ],
    }


def _render_apply(change: ChangeReport, fmt: str) -> str:
    """
    Render an apply outcome for a human, inlining each file's unified diff.

    :func:`~toolguard.tools.rule_apply.render_change_report` summarises applied
    and skipped proposals but does NOT inline diffs; for an apply preview the
    diff is the whole point, so this appends each changed file's diff under the
    summary.

    Args:
        change: The change report to render.
        fmt: ``'text'`` or ``'markdown'`` (passed through to the summary
            renderer).

    Returns:
        The summary followed by the per-file diffs.
    """
    parts = [render_change_report(change, fmt=fmt)]
    for fchange in change.files:
        if fchange.diff:
            header = str(fchange.path) if fchange.path is not None else "(config)"
            if fmt == "markdown":
                parts.append(f"\n### Diff: {header}\n\n```diff\n{fchange.diff}```")
            else:
                parts.append(f"\n--- Diff: {header} ---\n{fchange.diff}")
    return "\n".join(parts)


def _nosecurity_block_reason(proposal: ConsolidationProposal) -> Optional[str]:
    """
    Return the ``#NOSECURITY`` reason when *proposal* would rewrite a blessed rule.

    A consolidation replaces a family of rules with one merged rule.  If any rule
    it would REMOVE carries a ``#NOSECURITY`` comment, that rule is intentionally
    blessed HERE (project-local); moving or rewriting it would strip the user's
    deliberate annotation, so the whole proposal is withheld from the apply path.

    Args:
        proposal: The consolidation proposal to check.

    Returns:
        The first blocking reason (``""`` for a bare tag), or ``None`` when no
        removed rule is ``#NOSECURITY``-tagged.
    """
    for pattern in proposal.removed_patterns:
        reason = nosecurity_reason_for(
            proposal.layer_provenance, proposal.list_type, proposal.tool, pattern
        )
        if reason is not None:
            return reason
    return None


def _withheld_to_dict(
    withheld: List[Tuple[ConsolidationProposal, str]],
) -> List[Dict[str, Any]]:
    """Serialize withheld (``#NOSECURITY``-blessed) consolidations for the JSON contract."""
    return [
        {
            "tool": p.tool,
            "list_type": p.list_type,
            "removed_patterns": list(p.removed_patterns),
            "added_pattern": p.added_pattern,
            "reason": reason,
        }
        for p, reason in withheld
    ]


def _partition_nosecurity(
    proposals: List[ConsolidationProposal],
) -> Tuple[List[ConsolidationProposal], List[Tuple[ConsolidationProposal, str]]]:
    """
    Split consolidations into appliable vs withheld because they touch a blessed rule.

    Returns ``(appliable, withheld)`` where *withheld* is a list of
    ``(proposal, reason)``.  This is the ``#NOSECURITY`` migration/edit block: a
    rule the user annotated intentionally-insecure is never auto-rewritten.
    """
    appliable: List[ConsolidationProposal] = []
    withheld: List[Tuple[ConsolidationProposal, str]] = []
    for proposal in proposals:
        reason = _nosecurity_block_reason(proposal)
        if reason is None:
            appliable.append(proposal)
        else:
            withheld.append((proposal, reason))
    return appliable, withheld


def _render_withheld(
    withheld: List[Tuple[ConsolidationProposal, str]], fmt: str
) -> str:
    """Render the withheld (``#NOSECURITY``-blessed) consolidations for a human."""
    if not withheld:
        return ""
    lines = []
    header = "Withheld (blessed by #NOSECURITY -- not rewritten):"
    lines.append(f"\n### {header}" if fmt == "markdown" else f"\n{header}")
    for proposal, reason in withheld:
        removed = ", ".join(proposal.removed_patterns)
        tag = f"#NOSECURITY: {reason}" if reason else "#NOSECURITY"
        lines.append(f"  - {proposal.tool} [{proposal.list_type}] {removed} ({tag})")
    return "\n".join(lines)


def _run_apply(args: argparse.Namespace, report: MaintenanceReport) -> int:
    """
    Execute the ``--apply`` path: preview by default, write only with ``--write``.

    Collects the strict consolidation proposals from ``report`` and runs
    :func:`~toolguard.tools.rule_apply.apply_proposals`.  Without ``--write`` it
    is a dry run (nothing is touched on disk).  With ``--write`` it first runs
    the migration/working-tree pre-flight and REFUSES (leaving the config
    untouched) if there are any blockers, so a real edit is always reviewable and
    revertible.

    Args:
        args: Parsed CLI namespace (uses ``write``, ``dir``, ``format``).
        report: The maintenance report whose consolidations to apply.

    Returns:
        Exit code: ``0`` on success (preview or write), ``2`` when ``--write``
        is refused by the safety pre-flight.
    """
    # Withhold any consolidation that would rewrite a #NOSECURITY-blessed rule:
    # such a rule is intentionally insecure HERE and is never auto-migrated/rewritten.
    proposals, withheld = _partition_nosecurity(collect_consolidations(report))

    if args.write:
        preflight = migration_preflight(Path(args.dir))
        if preflight.blockers:
            lines = [
                "Refusing to write changes -- the safety pre-flight found blockers:",
                *(f"  - {b}" for b in preflight.blockers),
                "Resolve these (commit/stash your changes, confirm the project "
                "root) and re-run.",
            ]
            print("\n".join(lines))
            return 2

    change = apply_proposals(proposals, dry_run=not args.write)

    if args.format == "json":
        payload = change_report_to_dict(change)
        payload["dry_run"] = not args.write
        # The equivalent EditProposals, so the maintenance skill can hand these to
        # `toolguard-audit --edits` for an as-if-enacted security review before writing.
        payload["edit_proposals"] = [
            edit_proposal_to_dict(consolidation_to_edit_proposal(p)) for p in proposals
        ]
        payload["withheld_nosecurity"] = _withheld_to_dict(withheld)
        print(json.dumps(payload, indent=2))
        return 0

    fmt = "markdown" if args.format == "markdown" else "text"
    banner = (
        "APPLIED changes to disk."
        if args.write
        else "DRY RUN -- no files were modified. Re-run with --write to apply."
    )
    print(_render_apply(change, fmt))
    withheld_text = _render_withheld(withheld, fmt)
    if withheld_text:
        print(withheld_text)
    print(f"\n{banner}")
    return 0


def _collect_annotations(
    config: Configuration, tools: Optional[Sequence[str]]
) -> Dict[Path, Dict[str, List[str]]]:
    """
    Merge per-file clarity annotations across all requested tools.

    Args:
        config: The resolved configuration to analyze.
        tools: Tools to annotate, or ``None`` for all governed tools.

    Returns:
        ``{ path -> { full_pattern -> [note, ...] } }`` with notes merged and
        sorted across tools (patterns are tool-qualified, so they never collide).
    """
    target_tools = list(tools) if tools is not None else sorted(GOVERNED_TOOLS)
    merged: Dict[Path, Dict[str, List[str]]] = {}
    for tool in target_tools:
        for path, patterns in clarity_annotations(config, tool).items():
            dest = merged.setdefault(path, {})
            for pattern, notes in patterns.items():
                bucket = dest.setdefault(pattern, [])
                for note in notes:
                    if note not in bucket:
                        bucket.append(note)
    for patterns in merged.values():
        for pattern in patterns:
            patterns[pattern] = sorted(patterns[pattern])
    return merged


def _unified_diff(path: Path, old: str, new: str) -> str:
    """Return a unified diff between *old* and *new* text, labeled with *path*."""
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def _permission_patterns_in_text(text: str) -> List[str]:
    """
    Extract every ``[permissions]`` rule pattern present in *text*.

    Used to build the ``expected_patterns`` content-loss guard argument for
    :func:`~toolguard.config_write_guard.verified_write_config` (TOO-19
    corrective change) when annotating a config file: annotation only ever
    INSERTS ``# toolguard:`` comment lines and must never remove a rule, so
    every pattern present in the file BEFORE annotating must still be present
    in the text actually written.

    Excludes any :func:`~toolguard.rule_sort.is_synthetic_pattern` value
    (TOO-19 review fix): a malformed rule entry (e.g. a structured entry
    missing its ``match`` key) parses to a SYNTHESIZED, non-matchable
    stand-in pattern (see :func:`~toolguard.rule_sort._rule_pattern_of_value`)
    that can never appear in the annotated text this function's caller is
    about to write, so including it here previously made the content-loss
    guard wrongly refuse annotation on any file holding one such malformed
    entry.

    Args:
        text: Full TOML file content (before or after annotation).

    Returns:
        List of every REAL rule pattern found in the file's ``[permissions]``
        section (empty if the file has none), excluding synthesized patterns.
    """
    start, end = find_section_boundaries(text, "permissions")
    if start == -1:
        return []
    parsed = parse_permissions_section_with_comments(text[start:end])
    return [
        value
        for perm_type in ("allow", "deny", "ask")
        for item_type, _content, value in parsed.get(perm_type, [])
        if item_type == "rule" and not is_synthetic_pattern(value)
    ]


def _run_annotate(args: argparse.Namespace, config: Configuration) -> int:
    """
    Execute the ``--annotate`` path: preview by default, write only with ``--write``.

    Computes the ``# toolguard:`` clarity comments for every confusing rule and,
    per file, produces the before/after text.  Without ``--write`` it is a dry run
    (nothing is touched).  With ``--write`` it runs the same safety pre-flight as
    ``--apply`` and REFUSES on blockers (dirty tree / unresolved root), leaving the
    files untouched.  Each actual write goes through
    :func:`~toolguard.config_write_guard.verified_write_config` (TOO-19 corrective
    change), which additionally refuses -- also leaving the file untouched -- if
    the annotated text would fail to parse or would drop any rule pattern that was
    present in the file before annotating (see :func:`_permission_patterns_in_text`).

    Args:
        args: Parsed CLI namespace (uses ``write``, ``dir``, ``format``, ``tool``).
        config: The resolved configuration to annotate.

    Returns:
        Exit code: ``0`` on success (preview or write), ``2`` when ``--write`` is
        refused by the pre-flight.

    Raises:
        ConfigWriteVerificationError: A write's resulting text fails to parse or
            would drop an existing rule pattern.
    """
    merged = _collect_annotations(config, args.tool)

    results: List[Tuple[Path, str, str]] = []
    for path in sorted(merged, key=str):
        try:
            old, new = annotate_config_file(path, merged[path])
        except OSError, tomllib.TOMLDecodeError:
            # A malformed file (e.g. a multi-line structured entry -- not
            # valid TOML 1.0, see toolguard.rule_sort's top-of-file
            # docstring) is skipped here the same as an unreadable one: one
            # bad file must not abort the whole annotate batch. In practice
            # `config` (and therefore `merged`, which is keyed off its
            # findings) never contains such a file's rules to begin with --
            # toolguard.config's loader already fail-open-skips it -- but a
            # file edited on disk between that load and this re-read is a
            # real, if narrow, race this guards against.
            continue
        results.append((path, old, new))
    changed = [(p, o, n) for (p, o, n) in results if o != n]

    if args.write:
        preflight = migration_preflight(Path(args.dir))
        if preflight.blockers:
            print(
                "\n".join(
                    [
                        "Refusing to write annotations -- the safety pre-flight found "
                        "blockers:",
                        *(f"  - {b}" for b in preflight.blockers),
                        "Resolve these (commit/stash your changes, confirm the project "
                        "root) and re-run.",
                    ]
                )
            )
            return 2
        for path, old, new in changed:
            verified_write_config(
                path,
                new,
                "toml",
                expected_patterns=_permission_patterns_in_text(old),
            )

    if args.format == "json":
        payload = {
            "dry_run": not args.write,
            "total_changed": len(changed),
            "files": [
                {"path": str(p), "changed": o != n, "diff": _unified_diff(p, o, n)}
                for (p, o, n) in results
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if not changed:
        print(
            "No clarity annotations to write -- no confusing interactions, or the "
            "config is already annotated."
        )
        return 0
    for path, old, new in changed:
        print(_unified_diff(path, old, new))
    banner = (
        "ANNOTATED config files."
        if args.write
        else "DRY RUN -- no files were modified. Re-run with --write to apply."
    )
    print(f"\n{banner}")
    return 0


def _replay_entry_to_dict(diff_entry: EntryDiff) -> Dict[str, str]:
    """Serialize one replay :class:`EntryDiff` to a small JSON-friendly dict."""
    return {
        "tool": diff_entry.entry.tool,
        "command": diff_entry.entry.command,
        "verdict_before": diff_entry.decision_a.verdict,
        "verdict_after": diff_entry.decision_b.verdict,
    }


def replay_diff_to_dict(diff: ReplayDiff, corpus_size: int) -> Dict[str, Any]:
    """
    Serialize a candidate-replay :class:`ReplayDiff` for the maintenance skill.

    Args:
        diff: The two-config replay result (current config vs candidate).
        corpus_size: Number of corpus observations replayed (0 means the replay
            is vacuous -- necessary evidence is simply absent).

    Returns:
        A dict under the ``replay_candidate`` key with summary counts and the
        broadened/tightened command lists.  Broadened commands are the risk
        signal (the candidate would newly admit them); tightened are usually fine.
    """
    return {
        "replay_candidate": {
            "corpus_size": corpus_size,
            "unchanged": diff.unchanged_count,
            "tightened": diff.tightened_count,
            "broadened": diff.broadened_count,
            "broadened_commands": [_replay_entry_to_dict(d) for d in diff.broadened()],
            "tightened_commands": [_replay_entry_to_dict(d) for d in diff.tightened()],
        }
    }


def _render_replay(diff: ReplayDiff, corpus_size: int, fmt: str = "markdown") -> str:
    """
    Render a candidate-replay result as human-readable text.

    Leads with the necessary-not-sufficient caveat, then lists broadened commands
    (the risk) and tightened commands (informational).  An empty corpus is called
    out explicitly as vacuous rather than reported as a clean pass.
    """
    title = "Corpus replay: current config vs candidate"
    lines = [f"# {title}" if fmt == "markdown" else title, ""]
    if corpus_size == 0:
        lines.append(
            "No corpus observations were harvested, so this replay proves NOTHING "
            "about the candidate. Corpus validation is necessary but not "
            "sufficient; an empty corpus is vacuous, not a clean pass."
        )
        return "\n".join(lines)

    lines.append(f"Observations replayed: {diff.total_count}")
    lines.append(f"  unchanged:                     {diff.unchanged_count}")
    lines.append(f"  tightened (candidate stricter): {diff.tightened_count}")
    lines.append(f"  broadened (candidate looser):   {diff.broadened_count}")

    if diff.broadened_count:
        lines.append("")
        lines.append(
            "BROADENED -- commands the candidate would newly admit (review each):"
        )
        for d in diff.broadened():
            lines.append(f"  [{d.entry.tool}] {d.entry.command}")
            lines.append(f"      {d.decision_a.verdict} -> {d.decision_b.verdict}")
    if diff.tightened_count:
        lines.append("")
        lines.append(
            "TIGHTENED -- commands the candidate would newly restrict (usually fine):"
        )
        for d in diff.tightened():
            lines.append(f"  [{d.entry.tool}] {d.entry.command}")
            lines.append(f"      {d.decision_a.verdict} -> {d.decision_b.verdict}")

    lines.append("")
    lines.append(
        "Necessary, not sufficient: replay only covers OBSERVED commands. A clean "
        "replay is not proof the candidate is safe for unobserved input."
    )
    return "\n".join(lines)


def _run_replay_candidate(args: argparse.Namespace) -> int:
    """
    Execute ``--replay-candidate``: corpus-validate an assembled candidate config.

    Replays the observed command corpus of ``--dir`` against BOTH the current
    config and the candidate config discovered from the ``--replay-candidate``
    directory (a staged project root the maintenance skill assembled), then reports
    which observed commands the candidate would newly BROADEN (admit) or TIGHTEN
    (restrict).

    This is the corpus-validation step of the skill's certification. It is
    read-only and NEVER a gate on its own: a broadening is a red flag to surface,
    an empty corpus is vacuous, and a clean replay only covers observed commands.
    Exit code is ``0`` unless the candidate directory does not exist.

    Args:
        args: Parsed CLI arguments (uses ``dir``, ``replay_candidate``,
            ``max_age_days``, ``format``).

    Returns:
        Process exit code (``0`` on success, ``2`` if the candidate dir is missing).
    """
    candidate_dir = Path(args.replay_candidate)
    if not candidate_dir.exists():
        print(f"--replay-candidate: directory not found: {candidate_dir}")
        return 2

    config_a = load_config(Path(args.dir))
    config_b = load_config(candidate_dir)
    corpus = harvest_corpus(Path(args.dir), max_age_days=args.max_age_days)
    diff = replay(corpus, config_a, config_b)

    if args.format == "json":
        print(json.dumps(replay_diff_to_dict(diff, len(corpus)), indent=2))
    else:
        print(_render_replay(diff, len(corpus), fmt=args.format))
    return 0


def _render_ledger(decisions: Sequence[Any], fmt: str = "text") -> str:
    """
    Render the merged prior-decision ledger as human-readable text.

    Args:
        decisions: The merged :class:`LedgerDecision` list (project then user).
        fmt: ``markdown`` or ``text`` (both currently identical plain output).

    Returns:
        A short, readable summary of every settled decision, grouped by level.
    """
    if not decisions:
        return "No prior maintenance decisions recorded (project or user ledger)."
    lines = [f"Prior maintenance decisions ({len(decisions)}):", ""]
    for decision in decisions:
        reason = f" -- {decision.rationale}" if decision.rationale else ""
        lines.append(
            f"  [{decision.level}] {decision.decision}: {decision.kind} "
            f"on {decision.family_id} ({decision.target}){reason}"
        )
    return "\n".join(lines)


def _run_ledger_show(args: argparse.Namespace) -> int:
    """
    Execute ``--ledger-show``: print the merged prior-decision ledger (read-only).

    Loads the project ledger (``<root>/.claude/toolguard_decisions.json``) and the
    user ledger (``~/.toolguard/decisions.json``) for ``--dir`` and prints them so
    the maintenance skill can filter already-settled suggestions on a periodic run.

    Args:
        args: Parsed CLI arguments (uses ``dir`` and ``format``).

    Returns:
        Process exit code (``0`` on success, ``2`` if a ledger file is malformed).
    """
    try:
        decisions = load_merged(Path(args.dir))
    except LedgerError as exc:
        print(f"--ledger-show: {exc}")
        return 2

    if args.format == "json":
        payload = [{**decision_to_dict(d), "level": d.level} for d in decisions]
        print(json.dumps(payload, indent=2))
    else:
        print(_render_ledger(decisions, fmt=args.format))
    return 0


def _run_record_decision(args: argparse.Namespace) -> int:
    """
    Execute ``--record-decision``: append settled decision(s) to a level's ledger.

    Reads a JSON file (or ``-`` for stdin) describing one decision object or a list
    of them, stamps each with the local time and toolguard version, and records it in
    the ledger for ``--ledger-level`` (idempotent by decision id). This persists the
    meta-decisions the maintenance skill's discussion pass gathers -- the "do not
    re-suggest this" outcomes that have no surviving rule to annotate.

    ``kind``, ``family_id`` and ``target`` are required per entry (a missing one is a
    validation error, exit 2). ``decision`` is optional and defaults to ``"reject"`` --
    the common case, since this mode records rejections; pass ``accept``/``defer``
    explicitly for the others. The whole batch is validated BEFORE anything is written,
    so a malformed entry partway through a list aborts without persisting the earlier
    ones.

    Args:
        args: Parsed CLI arguments (uses ``dir``, ``record_decision``,
            ``ledger_level``).

    Returns:
        Process exit code (``0`` on success, ``2`` on a read/parse/validation error).
    """
    source = args.record_decision
    try:
        raw = (
            sys.stdin.read()
            if source == "-"
            else Path(source).read_text(encoding="utf-8")
        )
    except OSError as exc:
        print(f"--record-decision: cannot read {source}: {exc}")
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"--record-decision: invalid JSON in {source}: {exc}")
        return 2

    entries = payload if isinstance(payload, list) else [payload]
    # Validate/construct EVERY entry before writing ANY of them. Recording is a durable
    # write, so a malformed entry midway through a batch must not leave the earlier
    # entries persisted behind a failure exit code (they would silence suggestions the
    # caller never confirmed). Build all decisions first; only then commit.
    decisions: List[LedgerDecision] = []
    try:
        for entry in entries:
            decisions.append(
                new_decision(
                    kind=entry["kind"],
                    family_id=entry["family_id"],
                    target=entry["target"],
                    decision=entry.get("decision", "reject"),
                    rationale=entry.get("rationale", ""),
                    level=args.ledger_level,
                )
            )
    except (KeyError, TypeError) as exc:
        print(f"--record-decision: malformed decision entry ({exc}) in {source}")
        return 2
    except LedgerError as exc:
        print(f"--record-decision: {exc}")
        return 2

    written = sorted({str(record_decision(Path(args.dir), d)) for d in decisions})
    print(f"Recorded {len(decisions)} decision(s) in: {', '.join(written)}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    CLI entry point for the ``toolguard-maintain`` console script.

    Loads the toolguard configuration from the given directory, runs the
    maintenance aggregator (:func:`run_maintenance`), and prints the summary.
    This function is READ-ONLY: it never writes or modifies any file -- applying
    a change is a separate, explicitly-approved step.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Exit code ``0``.

    Note:
        Static analysis runs by default and is fast.  Pass ``--corpus`` to also
        harvest an evidence corpus (daily logs + transcripts) and populate
        replay-backed and mining findings; that pass parses every observed
        command and can take a while on a large history, so bound it with
        ``--max-age-days``.  Use ``--format json`` for the structured contract
        the maintenance skill consumes.
    """
    parser = argparse.ArgumentParser(
        prog="toolguard-maintain",
        description=(
            "Audience: END-USER and SKILL -- run it yourself, or it is driven by "
            "the maintenance skill. Read-only; never edits config.\n\n"
            "Aggregate toolguard rule-maintenance findings (redundancies, strict "
            "consolidations, agent-judged broadenings, cross-layer redundancies, "
            "and clarity interactions) for the governed tools."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dir",
        default=".",
        metavar="DIR",
        help="Directory to load the toolguard configuration from (default: .).",
    )
    parser.add_argument(
        "--format",
        dest="format",
        choices=["markdown", "text", "json"],
        default="markdown",
        help=(
            "Output format: markdown (default), text, or json. Use json for the "
            "structured contract consumed by the maintenance skill / an AI pass."
        ),
    )
    parser.add_argument(
        "--tool",
        dest="tool",
        action="append",
        default=None,
        metavar="TOOL",
        help=(
            "Restrict to this tool (repeatable). Default: all governed tools "
            "(Bash, Read, Write, Edit)."
        ),
    )
    parser.add_argument(
        "--corpus",
        dest="corpus",
        action="store_true",
        default=False,
        help=(
            "Also harvest an evidence corpus (daily logs + transcripts) to back "
            "replay and mining findings. Off by default; this pass parses every "
            "observed command and can be slow on a large history -- bound it with "
            "--max-age-days."
        ),
    )
    parser.add_argument(
        "--max-age-days",
        dest="max_age_days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "When harvesting the corpus (--corpus), only include observations "
            "from the last N calendar days (default: no age cap)."
        ),
    )
    parser.add_argument(
        "--apply",
        dest="apply",
        action="store_true",
        default=False,
        help=(
            "Switch to apply mode: enact the replay-verified consolidation "
            "proposals the user has approved. Replay-verification is evidence, "
            "not consent -- these are never applied automatically. PREVIEW by "
            "default (dry run, shows the diffs, writes nothing); add --write to "
            "modify the config."
        ),
    )
    parser.add_argument(
        "--annotate",
        dest="annotate",
        action="store_true",
        default=False,
        help=(
            "Switch to annotate mode: write '# toolguard:' comments above rules "
            "with confusing interactions, explaining the real resolution. PREVIEW "
            "by default (dry run) -- add --write to modify the config. Idempotent "
            "and comment-only; never changes a rule and never clobbers your own "
            "comments."
        ),
    )
    parser.add_argument(
        "--write",
        dest="write",
        action="store_true",
        default=False,
        help=(
            "With --apply or --annotate, actually write the changes to disk "
            "(otherwise the mode is a dry-run preview). Refused if the safety "
            "pre-flight finds blockers (dirty working tree, unresolved project root)."
        ),
    )
    parser.add_argument(
        "--replay-candidate",
        dest="replay_candidate",
        default=None,
        metavar="DIR",
        help=(
            "Corpus-validation mode (read-only): replay the observed command "
            "corpus of --dir against BOTH the current config and the assembled "
            "candidate config discovered from DIR (a staged project root), and "
            "report which observed commands the candidate would newly broaden "
            "(admit) or tighten (restrict). Harvests the corpus automatically. "
            "Necessary but not sufficient -- covers only observed commands and "
            "never gates on its own."
        ),
    )
    parser.add_argument(
        "--ledger-show",
        dest="ledger_show",
        action="store_true",
        default=False,
        help=(
            "Prior-decision ledger mode (read-only): print the settled maintenance "
            "decisions for --dir, merging the project ledger "
            "(<root>/.claude/toolguard_decisions.json) and the user ledger "
            "(~/.toolguard/decisions.json). The skill uses this to avoid "
            "re-litigating decisions on a periodic run."
        ),
    )
    parser.add_argument(
        "--record-decision",
        dest="record_decision",
        default=None,
        metavar="FILE",
        help=(
            "Prior-decision ledger mode (write): read a decision JSON object (or a "
            "list of them) from FILE ('-' for stdin) and append it to the ledger for "
            "--ledger-level, idempotent by decision id. Records the 'do not "
            "re-suggest this' outcomes of the skill's discussion that have no "
            "surviving rule to annotate."
        ),
    )
    parser.add_argument(
        "--ledger-level",
        dest="ledger_level",
        choices=["project", "user"],
        default="project",
        help=(
            "Which ledger --record-decision writes to: 'project' (travels with the "
            "repo, default) or 'user' (~/.toolguard, applies everywhere)."
        ),
    )

    args = parser.parse_args(argv)

    ledger_modes = [
        name
        for name, on in (
            ("--apply", args.apply),
            ("--annotate", args.annotate),
            ("--replay-candidate", bool(args.replay_candidate)),
            ("--ledger-show", args.ledger_show),
            ("--record-decision", bool(args.record_decision)),
        )
        if on
    ]
    if len(ledger_modes) > 1:
        parser.error(
            f"{', '.join(ledger_modes)} are separate modes; run them separately"
        )
    if args.write and not (args.apply or args.annotate):
        parser.error("--write requires --apply or --annotate")

    if args.ledger_show:
        return _run_ledger_show(args)
    if args.record_decision:
        return _run_record_decision(args)
    if args.replay_candidate:
        return _run_replay_candidate(args)

    config = load_config(Path(args.dir))

    if args.annotate:
        return _run_annotate(args, config)

    corpus = (
        harvest_corpus(Path(args.dir), max_age_days=args.max_age_days)
        if args.corpus
        else None
    )
    report = run_maintenance(config, tools=args.tool, corpus=corpus)

    if args.apply:
        return _run_apply(args, report)

    if args.format == "json":
        print(json.dumps(report_to_dict(report), indent=2))
    else:
        print(render(report, fmt=args.format))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
