"""
Unified security audit aggregator for toolguard.

Runs four independent analysers -- rule danger, takeover-mode invariants,
rule-interaction clarity, and environment shadowing -- normalises whatever they
return into one :class:`RankedFinding` list, and reports it as a
:class:`SecurityReport`. It detects nothing itself; what it contributes is the
normalised shape, the ranking, and the clarity findings' severity and wording.
:func:`render` formats a report for a human, and :func:`main` is the
``toolguard-audit`` console script.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from toolguard.config import Configuration, TakeoverConfig
from toolguard.constants import BUILTIN_TOOLS
from toolguard.tools.clarity import find_confusing_interactions
from toolguard.tools.config_access import (
    audit_context,
    load_config,
    nosecurity_reason_for,
)
from toolguard.tools.danger import DangerFinding, Severity, danger
from toolguard.tools.edit_proposal import (
    ACTION_REMOVE,
    ACTION_REPLACE,
    EditProposal,
    RuleEdit,
    apply_edits,
    edit_proposal_from_dict,
    edit_proposal_to_dict,
)
from toolguard.tools.environment_audit import audit_environment
from toolguard.tools.takeover_audit import audit_takeover, effective_takeover_state

#: Marker prefix of an extended-syntax regex pattern body (``[regex]<body>``).
_REGEX_MARKER = "[regex]"


# ---------------------------------------------------------------------------
# Normalised finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Remediation:
    """
    A finding's suggested fix, in human and machine-actionable forms.

    Attributes:
        text: Human-readable guidance -- always present.  It may name a more
            surgical or judgement-based fix than ``proposal`` does, e.g. "narrow
            this rule" where the mechanical proposal deletes it outright.
        proposal: The deterministic edit when the fix can be expressed as one,
            else ``None`` -- the guidance then lives only in ``text``.
    """

    text: str
    proposal: Optional[EditProposal]


@dataclass(frozen=True)
class RankedFinding:
    """
    One security finding, in the single shape every analyser is normalised into.

    Attributes:
        source: Which analyser produced it -- ``"rule"``, ``"takeover"``,
            ``"clarity"``, or ``"environment"``.
        finding_id: Stable detector/finding identifier (e.g.
            ``"arbitrary-exec-allow"`` or ``"hook-not-registered"``).
        severity_value: Integer severity: 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL.
        severity_label: The same severity as a label (e.g. ``"CRITICAL"``).
        tool: Tool name the finding concerns (e.g. ``"Bash"``), or ``None`` for a
            configuration-wide one.  Always ``None`` for environment findings.
        locus: Compact origin label from ``provenance.describe_brief()`` when the
            source finding has provenance; ``None`` otherwise.
        pattern: For a rule finding the flagged pattern; for a clarity finding the
            allow pattern of the overlapping pair.  ``None`` for takeover and
            environment findings, which concern configuration structure and the
            process environment rather than a single pattern.
        summary: The primary human-readable explanation of the finding.
        impact: Separate impact text.  Always ``""`` for a rule finding, which
            folds impact into its rationale; takeover and environment findings
            carry their own, and this module supplies the clarity text.
        remediation: Suggested fix, as a :class:`Remediation`.
        takeover_active: Whether takeover mode was ON when this finding was produced.
        acknowledged: ``True`` when the flagged rule carries a ``#NOSECURITY``
            comment.  Only rule findings are looked up, so the other three sources
            are always ``False``.  An acknowledged finding is still reported and
            labelled -- toolguard acknowledges, it does not hide -- but it sorts
            last within ``SecurityReport.findings``; the renderer groups by
            severity first, so it still appears in its own severity section.
        acknowledgement: The ``#NOSECURITY`` reason text when ``acknowledged`` is
            ``True`` (``""`` for a bare tag with no reason); ``None`` otherwise.
    """

    source: str
    finding_id: str
    severity_value: int
    severity_label: str
    tool: Optional[str]
    locus: Optional[str]
    pattern: Optional[str]
    summary: str
    impact: str
    remediation: Remediation
    takeover_active: bool
    acknowledged: bool = False
    acknowledgement: Optional[str] = None


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityReport:
    """
    Aggregated security audit result.

    Attributes:
        findings: Tuple of :class:`RankedFinding`.  Acknowledgement is the
            PRIMARY sort key and puts acknowledged findings last, so an
            acknowledged CRITICAL follows an un-acknowledged LOW; then severity
            descending, source, tool (``None`` sorting as ``""``), finding_id.
            Deterministic -- the same config always yields the same order.
        takeover_active: Whether takeover mode was ON when the audit ran.
        highest_severity: The highest ``severity_value`` across all findings, or
            ``0`` when there are no findings.
        counts: Mapping from severity label (``"LOW"``, ``"MEDIUM"``, ``"HIGH"``,
            ``"CRITICAL"``) to the count of findings at that severity.  Only labels
            that actually occur are keys; a severity with no findings is absent
            rather than zero.
    """

    findings: Tuple[RankedFinding, ...]
    takeover_active: bool
    highest_severity: int
    counts: Mapping[str, int]


# ---------------------------------------------------------------------------
# Structured remediation
# ---------------------------------------------------------------------------


def _danger_proposal(df: DangerFinding) -> Optional[EditProposal]:
    """
    Build the structured edit for a danger finding, when one exists.

    Follows the finding's own ``remediation_kind`` hint, targeting the exact rule
    at its exact layer: ``'remove'`` deletes it, ``'anchor'`` re-writes an
    unanchored ``[regex]`` body with a leading ``^``.

    Returns:
        An :class:`EditProposal`, or ``None`` when nothing deterministic applies
        -- no ``remediation_kind``, no provenance to target, or an ``'anchor'``
        hint on a body that is not ``[regex]`` or is already anchored.
    """
    if df.remediation_kind is None or df.provenance is None:
        return None

    origin = f"audit:{df.detector_id}"

    if df.remediation_kind == "remove":
        return EditProposal(
            action=ACTION_REMOVE,
            tool=df.tool,
            rationale=df.remediation,
            edits=(
                RuleEdit(
                    tool=df.tool,
                    list_type=df.list_type,
                    provenance=df.provenance,
                    removed_patterns=(df.pattern,),
                    added_patterns=(),
                ),
            ),
            origin=origin,
        )

    if df.remediation_kind == "anchor":
        if not df.pattern.startswith(_REGEX_MARKER):
            return None
        body = df.pattern[len(_REGEX_MARKER) :]
        if body.startswith("^"):
            return None
        anchored = f"{_REGEX_MARKER}^{body}"
        return EditProposal(
            action=ACTION_REPLACE,
            tool=df.tool,
            rationale=df.remediation,
            edits=(
                RuleEdit(
                    tool=df.tool,
                    list_type=df.list_type,
                    provenance=df.provenance,
                    removed_patterns=(df.pattern,),
                    added_patterns=(anchored,),
                ),
            ),
            origin=origin,
        )

    return None


# ---------------------------------------------------------------------------
# Core aggregator
# ---------------------------------------------------------------------------


def security_audit(
    config: Configuration,
    takeover: Optional[TakeoverConfig] = None,
    env: Optional[Mapping[str, str]] = None,
) -> SecurityReport:
    """
    Run every security analyser and return a unified :class:`SecurityReport`.

    Args:
        config: The resolved configuration hierarchy to audit.
        takeover: Pre-resolved takeover configuration.  When ``None`` it is
            resolved once, here, so every finding reports the same resolved
            takeover state.
        env: Environment mapping for the environment analyser, which falls back
            to ``os.environ``.  Exposed so a test need not mutate the real
            environment.

    Returns:
        A :class:`SecurityReport`; see it for the finding order.
    """
    if takeover is None:
        takeover = effective_takeover_state(config)

    ranked: List[RankedFinding] = []

    for df in danger(config, takeover):
        reason = (
            nosecurity_reason_for(df.provenance, df.list_type, df.tool, df.pattern)
            if df.provenance
            else None
        )
        ranked.append(
            RankedFinding(
                source="rule",
                finding_id=df.detector_id,
                severity_value=df.severity.value,
                severity_label=df.severity.label(),
                tool=df.tool,
                locus=df.provenance.describe_brief() if df.provenance else None,
                pattern=df.pattern,
                summary=df.rationale,
                impact="",
                remediation=Remediation(
                    text=df.remediation, proposal=_danger_proposal(df)
                ),
                takeover_active=df.takeover_active,
                acknowledged=reason is not None,
                acknowledgement=reason,
            )
        )

    for af in audit_takeover(config, takeover):
        ranked.append(
            RankedFinding(
                source="takeover",
                finding_id=af.finding_id,
                severity_value=af.severity.value,
                severity_label=af.severity.label(),
                tool=af.tool,
                locus=af.provenance.describe_brief() if af.provenance else None,
                pattern=None,
                summary=af.description,
                impact=af.impact,
                remediation=Remediation(text=af.remediation, proposal=None),
                takeover_active=takeover.enabled,
            )
        )

    # Clarity is the one source carrying no severity of its own, so this module
    # picks one: LOW, because a confusing-but-correct rule set is a latent risk
    # rather than a vulnerability.
    for tool in sorted(BUILTIN_TOOLS):
        for cf in find_confusing_interactions(config, tool):
            ranked.append(
                RankedFinding(
                    source="clarity",
                    finding_id=cf.kind,
                    severity_value=Severity.LOW.value,
                    severity_label=Severity.LOW.label(),
                    tool=cf.tool,
                    locus=cf.provenance.describe_brief() if cf.provenance else None,
                    pattern=cf.allow_pattern,
                    summary=cf.explanation,
                    impact=(
                        "Non-obvious rule resolution (within a file or across layers) "
                        "makes it hard to reason about what is actually permitted -- a "
                        "latent security risk."
                    ),
                    remediation=Remediation(
                        text=(
                            "Make the interaction explicit: drop the overlapping rule "
                            "if it is redundant, or annotate it so the effective "
                            "verdict is clear."
                        ),
                        proposal=None,
                    ),
                    takeover_active=takeover.enabled,
                )
            )

    for ef in audit_environment(env):
        ranked.append(
            RankedFinding(
                source="environment",
                finding_id=ef.finding_id,
                severity_value=ef.severity.value,
                severity_label=ef.severity.label(),
                tool=None,
                locus=None,
                pattern=None,
                summary=ef.description,
                impact=ef.impact,
                remediation=Remediation(text=ef.remediation, proposal=None),
                takeover_active=takeover.enabled,
            )
        )

    ranked.sort(
        key=lambda f: (
            f.acknowledged,
            -f.severity_value,
            f.source,
            f.tool or "",
            f.finding_id,
        )
    )

    findings_tuple: Tuple[RankedFinding, ...] = tuple(ranked)

    highest_severity = max((f.severity_value for f in findings_tuple), default=0)

    counts: dict[str, int] = {}
    for f in findings_tuple:
        label = f.severity_label
        counts[label] = counts.get(label, 0) + 1

    return SecurityReport(
        findings=findings_tuple,
        takeover_active=takeover.enabled,
        highest_severity=highest_severity,
        counts=counts,
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

#: Severity labels in display order, highest first.
_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def render(report: SecurityReport, fmt: str = "markdown") -> str:
    """
    Format a :class:`SecurityReport` as human-readable text.

    The result is strict ASCII: every character is passed through
    ``encode("ascii", errors="replace")``.

    Args:
        fmt: ``"markdown"`` (headings and bullets) or ``"text"`` (indented lines
            for a terminal).

    Returns:
        The formatted report.

    Raises:
        ValueError: When ``fmt`` is neither ``"markdown"`` nor ``"text"``.
    """
    if fmt not in ("markdown", "text"):
        raise ValueError(f"fmt must be 'markdown' or 'text', got: {fmt!r}")

    lines: List[str] = []

    if fmt == "markdown":
        _render_markdown(report, lines)
    else:
        _render_text(report, lines)

    result = "\n".join(lines)
    # Not merely defensive: patterns, loci and #NOSECURITY reasons are copied
    # verbatim out of the user's config files and need not be ASCII.
    result = result.encode("ascii", errors="replace").decode("ascii")
    return result


def _counts_summary(report: SecurityReport) -> str:
    """
    Build the one-line severity tally.

    Lists all four labels, supplying the zeros ``report.counts`` itself omits:
    ``"CRITICAL: 2  HIGH: 1  MEDIUM: 0  LOW: 0"``.
    """
    parts = [f"{label}: {report.counts.get(label, 0)}" for label in _SEVERITY_ORDER]
    return "  ".join(parts)


def _takeover_banner(report: SecurityReport) -> str:
    """Return ``"Takeover mode: ACTIVE"`` or ``"Takeover mode: INACTIVE"``."""
    state = "ACTIVE" if report.takeover_active else "INACTIVE"
    return f"Takeover mode: {state}"


def _render_markdown(report: SecurityReport, lines: List[str]) -> None:
    """Append the markdown report to *lines*, grouped by severity."""
    lines.append("# Toolguard Security Audit")
    lines.append("")
    lines.append(f"**{_takeover_banner(report)}**")
    lines.append("")
    lines.append(_counts_summary(report))
    lines.append("")

    if not report.findings:
        lines.append("No security findings.")
        return

    for sev_label in _SEVERITY_ORDER:
        group = [f for f in report.findings if f.severity_label == sev_label]
        if not group:
            continue
        lines.append(f"## {sev_label}")
        lines.append("")
        for f in group:
            _render_finding_markdown(f, lines)
        lines.append("")


def _render_finding_markdown(f: RankedFinding, lines: List[str]) -> None:
    """Append one finding to *lines* as a markdown bullet block."""
    tool_label = f.tool if f.tool else "(global)"
    lines.append(f"- **[{f.finding_id}]** source={f.source}  tool={tool_label}")
    if f.pattern:
        lines.append(f"  - pattern: `{f.pattern}`")
    if f.locus:
        lines.append(f"  - locus: {f.locus}")
    if f.acknowledged:
        lines.append(f"  - acknowledged: {_acknowledgement_label(f)}")
    lines.append(f"  - summary: {f.summary}")
    if f.impact:
        lines.append(f"  - impact: {f.impact}")
    lines.append(f"  - remediation: {f.remediation.text}")
    if f.remediation.proposal is not None:
        lines.append("  - structured fix: available (see JSON `remediation.proposal`)")
    lines.append("")


def _render_text(report: SecurityReport, lines: List[str]) -> None:
    """Append the plain-text report to *lines*, grouped by severity."""
    title = "Toolguard Security Audit"
    lines.append(title)
    lines.append("=" * len(title))
    lines.append("")
    lines.append(_takeover_banner(report))
    lines.append(_counts_summary(report))
    lines.append("")

    if not report.findings:
        lines.append("No security findings.")
        return

    for sev_label in _SEVERITY_ORDER:
        group = [f for f in report.findings if f.severity_label == sev_label]
        if not group:
            continue
        lines.append(f"[{sev_label}]")
        lines.append("-" * (len(sev_label) + 2))
        for f in group:
            _render_finding_text(f, lines)
        lines.append("")


def _render_finding_text(f: RankedFinding, lines: List[str]) -> None:
    """Append one finding to *lines* as indented plain-text lines."""
    tool_label = f.tool if f.tool else "(global)"
    lines.append(f"  [{f.finding_id}]  source={f.source}  tool={tool_label}")
    if f.pattern:
        lines.append(f"    pattern     : {f.pattern}")
    if f.locus:
        lines.append(f"    locus       : {f.locus}")
    if f.acknowledged:
        lines.append(f"    acknowledged: {_acknowledgement_label(f)}")
    lines.append(f"    summary     : {f.summary}")
    if f.impact:
        lines.append(f"    impact      : {f.impact}")
    lines.append(f"    remediation : {f.remediation.text}")
    if f.remediation.proposal is not None:
        lines.append("    structured  : fix available (see JSON remediation.proposal)")
    lines.append("")


def _acknowledgement_label(f: RankedFinding) -> str:
    """``#NOSECURITY: <reason>`` when a reason was given, else bare ``#NOSECURITY``."""
    if f.acknowledgement:
        return f"#NOSECURITY: {f.acknowledgement}"
    return "#NOSECURITY"


# ---------------------------------------------------------------------------
# As-if-enacted edit review (--edits)
# ---------------------------------------------------------------------------


def _finding_key(f: RankedFinding) -> tuple:
    """Identity used to match a finding across a before/after audit."""
    return (f.finding_id, f.tool, f.pattern, f.locus)


def _finding_summary(f: RankedFinding) -> Dict[str, object]:
    """A compact, JSON-safe summary of a finding for the edit delta."""
    return {
        "finding_id": f.finding_id,
        "severity_label": f.severity_label,
        "tool": f.tool,
        "pattern": f.pattern,
        "locus": f.locus,
    }


def _finding_delta(base: SecurityReport, proposed: SecurityReport) -> Dict[str, object]:
    """
    Compute which findings the proposed edits introduce or resolve.

    Args:
        base: The audit of the current config.
        proposed: The audit of the as-if-enacted config.

    Returns:
        ``{"introduced": [...], "resolved": [...]}`` -- findings present only
        after the edits, and only before them, as compact summaries.  Findings
        that share a :func:`_finding_key` collapse to one entry.
    """
    base_map = {_finding_key(f): f for f in base.findings}
    proposed_map = {_finding_key(f): f for f in proposed.findings}
    introduced = [
        _finding_summary(proposed_map[k]) for k in proposed_map if k not in base_map
    ]
    resolved = [
        _finding_summary(base_map[k]) for k in base_map if k not in proposed_map
    ]
    return {"introduced": introduced, "resolved": resolved}


def _render_edit_banner(proposals: List[EditProposal], delta: Dict[str, object]) -> str:
    """
    Render the banner that precedes an as-if-enacted (``--edits``) audit.

    Returns:
        A short banner summarising the review scope and the delta.
    """
    introduced = delta["introduced"]  # type: ignore[index]
    resolved = delta["resolved"]  # type: ignore[index]
    lines = [
        "AS-IF-ENACTED REVIEW",
        "====================",
        f"Audited the configuration as if {len(proposals)} proposed edit(s) "
        "were applied (whole hierarchy, all sections).",
        f"Findings introduced by the edits: {len(introduced)}",
        f"Findings resolved by the edits:   {len(resolved)}",
    ]
    for item in introduced:
        lines.append(
            f"  + INTRODUCED {item['finding_id']} ({item['severity_label']}) {item['pattern'] or ''}"
        )
    for item in resolved:
        lines.append(
            f"  - resolved   {item['finding_id']} ({item['severity_label']}) {item['pattern'] or ''}"
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    CLI entry point for the ``toolguard-audit`` console script.

    Loads the configuration hierarchy discovered from ``--dir``, audits it, and
    prints the result to stdout.  READ-ONLY: it writes no file, and ``--edits``
    applies its proposals to an in-memory configuration only.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        ``0``, unless ``--strict`` was given: then ``0`` when there are no
        findings, else the highest finding's severity value -- ``1`` LOW,
        ``2`` MEDIUM, ``3`` HIGH, ``4`` CRITICAL.
    """
    parser = argparse.ArgumentParser(
        prog="toolguard-audit",
        description=(
            "Audience: END-USER and SKILL -- run it yourself, or it is driven by "
            "the 'toolguard-security-audit' skill. Read-only; never edits config.\n\n"
            "Run the toolguard security audit and report findings from both "
            "the rule-danger analyser and the takeover-mode invariant checker. "
            "Use --format json --with-context to feed an AI-assisted pass."
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
        help="Output format: markdown (default), text, or json.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Exit with the highest severity value (1-4) when findings exist, "
            "or 0 when clean.  Without --strict, always exits 0."
        ),
    )
    parser.add_argument(
        "--with-context",
        dest="with_context",
        action="store_true",
        default=False,
        help=(
            "Include the consolidated config context (full rule hierarchy + native "
            "rules + takeover state + neutralized-rule ignore-list) in JSON output, "
            "for an AI-assisted pass.  Only meaningful with --format json; ignored "
            "silently for other formats."
        ),
    )
    parser.add_argument(
        "--migrations",
        dest="migrations",
        default=None,
        metavar="PATH",
        help=(
            "Path to a JSON file holding a list of PROPOSED hierarchy-migration "
            "analyses (as produced by hierarchy.migration_effect_to_dict).  When "
            "given, they are embedded under context['proposed_migrations'] in JSON "
            "output so an AI-assisted pass can assess the risk of enacting them.  "
            "Only meaningful with --format json."
        ),
    )
    parser.add_argument(
        "--edits",
        dest="edits",
        default=None,
        metavar="PATH",
        help=(
            "Path to a JSON file holding a list of PROPOSED edits (EditProposal "
            "dicts, as produced by edit_proposal.edit_proposal_to_dict or a "
            "finding's remediation_proposal).  Unlike --migrations, these are "
            "actually APPLIED in memory and the audit runs on the AS-IF-ENACTED "
            "config (whole hierarchy, all sections), so findings reflect the "
            "proposed state.  A finding delta (introduced/resolved) is added under "
            "context['proposed_edits'].  The maintenance skill uses this to review "
            "its changes before writing."
        ),
    )

    args = parser.parse_args(argv)

    proposed_migrations = None
    if args.migrations is not None:
        try:
            with open(args.migrations, "r") as handle:
                proposed_migrations = json.load(handle)
        except (OSError, ValueError) as exc:
            parser.error(f"could not read --migrations file {args.migrations!r}: {exc}")

    proposed_edits = None
    if args.edits is not None:
        try:
            with open(args.edits, "r") as handle:
                raw_edits = json.load(handle)
            proposed_edits = [edit_proposal_from_dict(d) for d in raw_edits]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            parser.error(f"could not read --edits file {args.edits!r}: {exc}")

    # The tooling loader, not load_configuration: it pins the walk to the project
    # root, so a stale CLAUDE_SETTINGS_PATH cannot divert the audit to another
    # project's config.
    config = load_config(Path(args.dir))
    report = security_audit(config)

    # From here on ``config`` and ``report`` describe the AS-IF-ENACTED state
    # whenever edits were supplied -- including the context block built below.
    edit_delta: Optional[Dict[str, object]] = None
    if proposed_edits is not None:
        base_report = report
        config = apply_edits(config, proposed_edits)
        report = security_audit(config)
        edit_delta = _finding_delta(base_report, report)

    if args.format == "json":
        payload = {
            "takeover_active": report.takeover_active,
            "highest_severity": report.highest_severity,
            "counts": dict(report.counts),
            "findings": [
                {
                    "source": f.source,
                    "finding_id": f.finding_id,
                    "severity_value": f.severity_value,
                    "severity_label": f.severity_label,
                    "tool": f.tool,
                    "locus": f.locus,
                    "pattern": f.pattern,
                    "summary": f.summary,
                    "impact": f.impact,
                    "remediation": f.remediation.text,
                    "remediation_proposal": (
                        edit_proposal_to_dict(f.remediation.proposal)
                        if f.remediation.proposal is not None
                        else None
                    ),
                    "takeover_active": f.takeover_active,
                    "acknowledged": f.acknowledged,
                    "acknowledgement": f.acknowledgement,
                }
                for f in report.findings
            ],
        }
        context = None
        if args.with_context:
            ctx = audit_context(config)
            tc = ctx.takeover
            context = {
                "summary": {
                    "start_dir": str(ctx.summary.start_dir)
                    if ctx.summary.start_dir is not None
                    else None,
                    "project_root": str(ctx.summary.project_root)
                    if ctx.summary.project_root is not None
                    else None,
                    "sources": list(ctx.summary.sources),
                    "governed_tools": list(ctx.summary.governed_tools),
                    "layer_count": ctx.summary.layer_count,
                },
                "takeover": {
                    "enabled": tc.enabled,
                    "no_match_fallback": tc.no_match_fallback,
                    "ignored_allow_patterns": list(tc.ignored_allow_patterns),
                    "additional_ignored_patterns": list(tc.additional_ignored_patterns),
                    "conflict": str(tc.conflict) if tc.conflict is not None else None,
                    "neutralized_allow_patterns": list(ctx.neutralized_allow_patterns),
                },
                "tools": [
                    {
                        "tool": tc_item.tool,
                        "layers": [
                            {
                                "locus": lc.locus,
                                "is_native": lc.is_native,
                                "allow": list(lc.allow),
                                "deny": list(lc.deny),
                                "ask": list(lc.ask),
                                "comments": [
                                    {
                                        "list_type": rc.list_type,
                                        "pattern": rc.pattern,
                                        "leading": rc.leading,
                                        "inline": rc.inline,
                                        "nosecurity_reason": rc.nosecurity_reason(),
                                    }
                                    for rc in lc.comments
                                ],
                            }
                            for lc in tc_item.layers
                        ],
                    }
                    for tc_item in ctx.tools
                ],
            }
        if proposed_migrations is not None:
            if context is None:
                context = {}
            context["proposed_migrations"] = proposed_migrations
        if proposed_edits is not None:
            if context is None:
                context = {}
            context["proposed_edits"] = {
                "edits": [edit_proposal_to_dict(p) for p in proposed_edits],
                "delta": edit_delta,
            }
        if context is not None:
            payload["context"] = context
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        if proposed_edits is not None and edit_delta is not None:
            print(_render_edit_banner(proposed_edits, edit_delta))
        print(render(report, fmt=args.format))

    if args.strict:
        return report.highest_severity
    return 0


if __name__ == "__main__":
    sys.exit(main())
