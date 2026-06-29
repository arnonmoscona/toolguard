"""
Unified security audit aggregator for toolguard.

This module is a THIN DETERMINISTIC AGGREGATOR over two independently-tested
analysers:

* :mod:`~toolguard.tools.danger` -- flags dangerous allow-rule patterns in the
  toolguard configuration (arbitrary-exec, destructive commands, secrets exposure,
  unanchored regex, blanket allows).
* :mod:`~toolguard.tools.takeover_audit` -- audits takeover-mode invariants (hook
  registration, conflicts, uncovered blanket allows, loose fallback).

This module contains NO detection logic of its own.  It calls the two public
functions (:func:`~toolguard.tools.danger.danger` and
:func:`~toolguard.tools.takeover_audit.audit_takeover`), normalises their outputs
into a single :class:`RankedFinding` list, and returns a :class:`SecurityReport`.
A :func:`render` helper produces human-readable text (ASCII only, no Unicode) and
a :func:`main` entry point wires everything to a CLI.

Public API summary
------------------
* :class:`RankedFinding` -- normalised finding from either source.
* :class:`SecurityReport` -- aggregated report: findings tuple + summary fields.
* :func:`security_audit` -- run both analysers and return a SecurityReport.
* :func:`render` -- format a SecurityReport as markdown or plain text.
* :func:`main` -- CLI entry point (``toolguard-audit`` console script).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Tuple

from toolguard.config import Configuration, TakeoverConfig
from toolguard.tools.config_access import audit_context, load_config
from toolguard.tools.danger import danger
from toolguard.tools.takeover_audit import audit_takeover, effective_takeover_state


# ---------------------------------------------------------------------------
# Normalised finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RankedFinding:
    """
    Normalised security finding from either the danger or takeover-audit analyser.

    Both :class:`~toolguard.tools.danger.DangerFinding` and
    :class:`~toolguard.tools.takeover_audit.AuditFinding` are converted into this
    shape so that consumers deal with a single uniform type.

    Attributes:
        source: ``"rule"`` for findings from
            :func:`~toolguard.tools.danger.danger`; ``"takeover"`` for findings
            from :func:`~toolguard.tools.takeover_audit.audit_takeover`.
        finding_id: Stable detector/finding identifier (e.g.
            ``"arbitrary-exec-allow"`` or ``"hook-not-registered"``).
        severity_value: Integer severity (1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL).
            Derived from the source finding's IntEnum ``.value``.
        severity_label: Human-readable severity label (e.g. ``"CRITICAL"``).
            Derived from the source finding's ``.label()`` method.
        tool: Tool name the finding concerns (e.g. ``"Bash"``), or ``None`` for
            configuration-wide findings.
        locus: Compact origin label from ``provenance.describe_brief()`` when
            provenance is available; ``None`` otherwise.
        pattern: The flagged pattern body for rule findings; ``None`` for takeover
            findings (they concern configuration structure, not a single pattern).
        summary: Primary human-readable explanation.  For danger findings this is
            the ``rationale``; for takeover findings it is the ``description``.
        impact: Additional impact text.  Empty string for danger findings (danger
            embeds impact in the rationale); takeover findings carry a separate
            ``impact`` field.
        remediation: Suggested fix or mitigation.
        takeover_active: Whether takeover mode was ON when this finding was produced.
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
    remediation: str
    takeover_active: bool


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SecurityReport:
    """
    Aggregated security audit result.

    Attributes:
        findings: Tuple of :class:`RankedFinding` sorted by severity descending,
            then by source, then by tool (empty string when None), then by
            finding_id.  Deterministic -- same config always yields the same order.
        takeover_active: Whether takeover mode was ON when the audit ran.
        highest_severity: The highest ``severity_value`` across all findings, or
            ``0`` when there are no findings.
        counts: Mapping from severity label (``"LOW"``, ``"MEDIUM"``, ``"HIGH"``,
            ``"CRITICAL"``) to the count of findings at that severity.  Only labels
            that actually occur in ``findings`` are included; labels with zero
            findings are omitted.
    """

    findings: Tuple[RankedFinding, ...]
    takeover_active: bool
    highest_severity: int
    counts: Mapping[str, int]


# ---------------------------------------------------------------------------
# Core aggregator
# ---------------------------------------------------------------------------


def security_audit(
    config: Configuration,
    takeover: Optional[TakeoverConfig] = None,
) -> SecurityReport:
    """
    Run both security analysers and return a unified :class:`SecurityReport`.

    This function is a pure aggregator: it calls
    :func:`~toolguard.tools.danger.danger` and
    :func:`~toolguard.tools.takeover_audit.audit_takeover`, normalises each
    finding into a :class:`RankedFinding`, sorts the combined list, and computes
    summary statistics.  No detection logic lives here.

    Args:
        config: The resolved configuration hierarchy to audit.
        takeover: Pre-resolved takeover configuration.  When ``None``, it is
            resolved via :func:`~toolguard.tools.takeover_audit.effective_takeover_state`
            so both analysers share the same resolved state.

    Returns:
        A :class:`SecurityReport` with all findings sorted severity-descending.
    """
    if takeover is None:
        takeover = effective_takeover_state(config)

    ranked: List[RankedFinding] = []

    # --- danger findings (source = "rule") ----------------------------------
    for df in danger(config, takeover):
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
                remediation=df.remediation,
                takeover_active=df.takeover_active,
            )
        )

    # --- takeover audit findings (source = "takeover") ----------------------
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
                remediation=af.remediation,
                takeover_active=takeover.enabled,
            )
        )

    # Sort: severity DESC, source, tool (None -> ""), finding_id
    ranked.sort(
        key=lambda f: (-f.severity_value, f.source, f.tool or "", f.finding_id)
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
# Renderer (ASCII only -- hard project rule)
# ---------------------------------------------------------------------------

# Ordered severity labels for display grouping (highest first)
_SEVERITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")


def render(report: SecurityReport, fmt: str = "markdown") -> str:
    """
    Format a :class:`SecurityReport` as human-readable ASCII text.

    All output is strict ASCII (``ord(c) < 128`` for every character).  No
    Unicode characters, no emoji -- this is a hard project requirement.

    Args:
        report: The security report to render.
        fmt: Output format -- ``"markdown"`` (headings and bullets) or
            ``"text"`` (plain indented lines suitable for terminal output).
            Any other value raises :class:`ValueError`.

    Returns:
        A formatted ASCII string representing the report.

    Raises:
        ValueError: When ``fmt`` is not ``"markdown"`` or ``"text"``.
    """
    if fmt not in ("markdown", "text"):
        raise ValueError(f"fmt must be 'markdown' or 'text', got: {fmt!r}")

    lines: List[str] = []

    if fmt == "markdown":
        _render_markdown(report, lines)
    else:
        _render_text(report, lines)

    result = "\n".join(lines)
    # Defensive guard: ensure no non-ASCII bytes slipped in
    result = result.encode("ascii", errors="replace").decode("ascii")
    return result


def _counts_summary(report: SecurityReport) -> str:
    """
    Build the counts summary line.

    Always lists all four severity labels in order so the reader can see
    zeros as well as non-zero counts.

    Args:
        report: The security report.

    Returns:
        A summary string like ``"CRITICAL: 2  HIGH: 1  MEDIUM: 0  LOW: 0"``.
    """
    parts = [f"{label}: {report.counts.get(label, 0)}" for label in _SEVERITY_ORDER]
    return "  ".join(parts)


def _takeover_banner(report: SecurityReport) -> str:
    """
    Return a short takeover-mode status line.

    Args:
        report: The security report.

    Returns:
        ``"Takeover mode: ACTIVE"`` or ``"Takeover mode: INACTIVE"``.
    """
    state = "ACTIVE" if report.takeover_active else "INACTIVE"
    return f"Takeover mode: {state}"


def _render_markdown(report: SecurityReport, lines: List[str]) -> None:
    """
    Append markdown-formatted content to ``lines``.

    Uses level-1 headings for the report title and level-2 headings for each
    severity group.  Individual findings are bullet lists.

    Args:
        report: The report to render.
        lines: Output list of strings to append to (mutated in place).
    """
    lines.append("# Toolguard Security Audit")
    lines.append("")
    lines.append(f"**{_takeover_banner(report)}**")
    lines.append("")
    lines.append(_counts_summary(report))
    lines.append("")

    if not report.findings:
        lines.append("No security findings.")
        return

    # Group by severity
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
    """
    Append one finding as a markdown bullet block.

    Args:
        f: The finding to render.
        lines: Output list to append to (mutated in place).
    """
    tool_label = f.tool if f.tool else "(global)"
    lines.append(f"- **[{f.finding_id}]** source={f.source}  tool={tool_label}")
    if f.pattern:
        lines.append(f"  - pattern: `{f.pattern}`")
    if f.locus:
        lines.append(f"  - locus: {f.locus}")
    lines.append(f"  - summary: {f.summary}")
    if f.impact:
        lines.append(f"  - impact: {f.impact}")
    lines.append(f"  - remediation: {f.remediation}")
    lines.append("")


def _render_text(report: SecurityReport, lines: List[str]) -> None:
    """
    Append plain-text formatted content to ``lines``.

    Uses underline-style section separators and indented key-value pairs.

    Args:
        report: The report to render.
        lines: Output list of strings to append to (mutated in place).
    """
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
    """
    Append one finding as indented plain-text lines.

    Args:
        f: The finding to render.
        lines: Output list to append to (mutated in place).
    """
    tool_label = f.tool if f.tool else "(global)"
    lines.append(f"  [{f.finding_id}]  source={f.source}  tool={tool_label}")
    if f.pattern:
        lines.append(f"    pattern     : {f.pattern}")
    if f.locus:
        lines.append(f"    locus       : {f.locus}")
    lines.append(f"    summary     : {f.summary}")
    if f.impact:
        lines.append(f"    impact      : {f.impact}")
    lines.append(f"    remediation : {f.remediation}")
    lines.append("")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    CLI entry point for the ``toolguard-audit`` console script.

    Loads the toolguard configuration from the specified directory, runs both
    security analysers via :func:`security_audit`, and prints the results to
    stdout.

    This function is READ-ONLY: it never writes or modifies any file.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Exit code.  Default: always ``0``.  With ``--strict``: ``0`` when there
        are no findings; the ``highest_severity`` value (1-4) when there are
        findings.

    Exit codes (``--strict`` mode):
        * ``0`` -- no findings
        * ``1`` -- only LOW findings
        * ``2`` -- highest finding is MEDIUM
        * ``3`` -- highest finding is HIGH
        * ``4`` -- at least one CRITICAL finding
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

    args = parser.parse_args(argv)

    proposed_migrations = None
    if args.migrations is not None:
        try:
            with open(args.migrations, "r") as handle:
                proposed_migrations = json.load(handle)
        except (OSError, ValueError) as exc:
            parser.error(f"could not read --migrations file {args.migrations!r}: {exc}")

    # Use the tooling facade loader (ignore_env_override=True) so the audit always
    # reflects the project-rooted hierarchy, consistent with the rest of the tooling
    # and not diverted by a stale CLAUDE_SETTINGS_PATH.
    config = load_config(Path(args.dir))
    report = security_audit(config)

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
                    "remediation": f.remediation,
                    "takeover_active": f.takeover_active,
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
                    "start_dir": str(ctx.summary.start_dir) if ctx.summary.start_dir is not None else None,
                    "project_root": str(ctx.summary.project_root) if ctx.summary.project_root is not None else None,
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
        if context is not None:
            payload["context"] = context
        print(json.dumps(payload, ensure_ascii=True, indent=2))
    else:
        print(render(report, fmt=args.format))

    if args.strict:
        return report.highest_severity
    return 0


if __name__ == "__main__":
    sys.exit(main())
