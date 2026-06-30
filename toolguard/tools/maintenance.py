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

Strict findings (redundancies, consolidations, cross-layer) are safe to apply;
broadenings and mining candidates are agent-judged and must be weighed (with the
security-audit lens) before acting -- the skill layer owns that decision.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from toolguard.config import Configuration
from toolguard.constants import GOVERNED_TOOLS
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
from toolguard.tools.mining import MiningReport, mine_rule_candidates, render_mining_report
from toolguard.tools.redundancy import RedundancyFinding, find_redundancy


@dataclass(frozen=True)
class ToolMaintenance:
    """
    All maintenance findings for a single governed tool.

    Attributes:
        tool: The tool name (e.g. ``'Bash'``).
        redundancies: Duplicate/subsumed rule findings (safe to drop).
        consolidations: Strict, equivalence-preserving merge proposals (families
            1-2; safe to apply).
        broadenings: Agent-judged widening proposals with evidence (families 3-4;
            must be judged, never auto-applied).
        cross_layer_redundancies: Specific rules already covered by a broader
            layer (safe to drop the specific copy).
    """

    tool: str
    redundancies: Tuple[RedundancyFinding, ...]
    consolidations: Tuple[ConsolidationProposal, ...]
    broadenings: Tuple[BroadeningProposal, ...]
    cross_layer_redundancies: Tuple[CrossLayerRedundancy, ...]

    @property
    def total(self) -> int:
        """Total number of findings across all categories for this tool."""
        return (
            len(self.redundancies)
            + len(self.consolidations)
            + len(self.broadenings)
            + len(self.cross_layer_redundancies)
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
    return (
        f"{redundancies} redundancy, {consolidations} strict-consolidation, "
        f"{broadenings} broadening (agent-judged), {cross_layer} cross-layer, "
        f"{len(report.mining.groups)} mining candidate(s)."
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

    if report.mining.groups:
        lines.append("")
        lines.append(f"{heading}Corpus mining")
        lines.append(render_mining_report(report.mining, "text"))

    return "\n".join(lines)
