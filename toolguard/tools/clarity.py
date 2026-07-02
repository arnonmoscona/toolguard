"""
Rule-interaction clarity analyzer (P2-F).

toolguard's within-file resolution has non-obvious semantics: a deny always wins
(regardless of which rule is more specific), a broad ask with no matching allow
collapses to deny, and otherwise the more-specific rule wins.  A rule set can
therefore be CORRECT yet inscrutable -- even an expert cannot reliably eyeball
the effective verdict.  A "correct but confusing" config is a latent bug, so
clarity is a first-class concern alongside security.

This module detects a finite, curated catalog of confusing same-file interactions
and explains the actual semantics, so the security audit and the maintenance
skill can surface them.  Offering a clearer *equivalent* configuration (only when
one provably exists) and emitting marker-tagged explanatory comments are later
slices; this first slice ships the DETECTOR plus a canonical explanation.

First detector: an allow rule whose DEFAULT command-space overlaps a deny or ask
rule in the SAME config layer.  Overlap is textual (precedence-ignorant); the
explanation states which rule actually wins so the reader is not surprised.
"""

from dataclasses import dataclass
from typing import List, Optional

from toolguard.config import Configuration, Provenance
from toolguard.tools.config_access import per_layer_rules
from toolguard.tools.pattern_overlap import default_prefix_tokens, prefixes_overlap


@dataclass(frozen=True)
class InteractionFinding:
    """
    A confusing same-file rule interaction with a calibrated explanation.

    Attributes:
        tool: Tool the interacting rules apply to (e.g. ``'Bash'``).
        provenance: Provenance of the config layer/file holding both rules.
        kind: The interaction class -- ``'deny-shadows-allow'`` or
            ``'ask-overlaps-allow'``.
        allow_pattern: The wrapper-free allow body involved.
        guard_section: The section of the overlapping guard -- ``'deny'``,
            ``'ask'``, or ``'deny+ask'`` for a multi-section interaction.
        guard_pattern: The wrapper-free guard body that overlaps the allow.
        explanation: A render-ready explanation of the ACTUAL resolution, so the
            confusing interaction is made legible rather than just flagged.
        guard_provenance: For a ``'cross-layer-dependent'`` finding, the provenance
            of the OTHER layer holding the overlapping guard (the allow lives in
            :attr:`provenance`).  ``None`` for same-file interactions.
    """

    tool: str
    provenance: Provenance
    kind: str
    allow_pattern: str
    guard_section: str
    guard_pattern: str
    explanation: str
    guard_provenance: Optional[Provenance] = None


def _explain(kind: str, allow: str, guard: str) -> str:
    """
    Build the canonical explanation for an overlap finding.

    Args:
        kind: The interaction class.
        allow: The allow body involved.
        guard: The overlapping deny/ask body.

    Returns:
        A calibrated explanation of the real resolution for this interaction.
    """
    if kind == "deny-shadows-allow":
        return (
            f"deny `{guard}` and allow `{allow}` overlap in this file: for any "
            f"command matching both, the DENY wins (toolguard denies always "
            f"override allows, regardless of which rule is more specific), so "
            f"part of this allow's intended coverage is silently blocked."
        )
    return (
        f"ask `{guard}` and allow `{allow}` overlap in this file: for commands "
        f"matching both, the MORE-SPECIFIC rule wins -- a more-specific allow "
        f"bypasses the ask, while a more-specific (or broad, then collapsing) "
        f"ask gates it -- so the effective verdict is not obvious from the lists."
    )


def _explain_multi_section(allow: str, deny_guard: str, ask_guard: str) -> str:
    """
    Explain an allow whose command-space overlaps BOTH a deny and an ask in one file.

    Args:
        allow: The allow body governed by two guard sections.
        deny_guard: The overlapping deny body.
        ask_guard: The overlapping ask body.

    Returns:
        A calibrated explanation of the combined three-section resolution.
    """
    return (
        f"allow `{allow}` overlaps BOTH deny `{deny_guard}` and ask `{ask_guard}` "
        f"in this file: three sections govern this command family. Where the deny "
        f"overlaps, the DENY wins (blocked); where only the ask overlaps, the "
        f"more-specific rule wins (the ask prompts unless a more-specific allow "
        f"bypasses it). The effective verdict is especially non-obvious -- consider "
        f"splitting the allow so each part's outcome is explicit."
    )


def _explain_cross_layer(
    section: str, allow: str, allow_more_specific: bool, guard: str
) -> str:
    """
    Explain an allow whose effective verdict depends on a guard in ANOTHER layer.

    Args:
        section: The overlapping guard's section (``'deny'`` or ``'ask'``).
        allow: The allow body (lives in the more/less specific layer per the flag).
        allow_more_specific: True when the allow's layer is MORE specific than the
            guard's layer (a lower specificity distance).
        guard: The overlapping guard body in the other layer.

    Returns:
        A calibrated explanation of the cross-layer resolution.
    """
    if section == "deny":
        if allow_more_specific:
            return (
                f"allow `{allow}` and deny `{guard}` overlap ACROSS layers: the allow "
                f"is in a more-specific layer, which OVERRIDES the broader deny, so the "
                f"command is permitted -- you cannot tell that from the deny's file alone."
            )
        return (
            f"allow `{allow}` and deny `{guard}` overlap ACROSS layers: the deny is in a "
            f"more-specific layer, so it WINS and blocks part of this allow -- the "
            f"effective verdict depends on a rule in another file."
        )
    if allow_more_specific:
        return (
            f"allow `{allow}` and ask `{guard}` overlap ACROSS layers: the allow is in a "
            f"more-specific layer, so it BYPASSES the broader ask and runs without a "
            f"prompt -- the effective verdict depends on a rule in another file."
        )
    return (
        f"allow `{allow}` and ask `{guard}` overlap ACROSS layers: the ask is in a "
        f"more-specific layer, so it GATES this allow into a prompt -- the effective "
        f"verdict depends on a rule in another file."
    )


def find_confusing_interactions(
    config: Configuration, tool: str
) -> List[InteractionFinding]:
    """
    Detect confusing allow/guard overlaps for ``tool``, within and across layers.

    Three detector families, all on DEFAULT patterns (``[regex]``/``[glob]``/
    ``[native]`` are not analysed) and all reported as textual overlaps with a
    calibrated explanation of the REAL resolution:

    - **Same-file pairwise** -- a DEFAULT allow overlapping a deny
      (``deny-shadows-allow``) or an ask (``ask-overlaps-allow``) in the same layer.
    - **Same-file multi-section** -- an allow overlapping BOTH a deny AND an ask in
      the same layer (``multi-section-interaction``): three sections govern one
      command family, so the verdict is especially non-obvious.
    - **Cross-layer** -- an allow whose effective verdict depends on a deny/ask in a
      DIFFERENT (more- or less-specific) layer (``cross-layer-dependent``): the
      outcome cannot be understood from a single file.

    Args:
        config: The resolved configuration to inspect.
        tool: Tool name to inspect (e.g. ``'Bash'``).

    Returns:
        A deterministically ordered list of :class:`InteractionFinding` records.
    """
    layers = list(per_layer_rules(config, tool))
    findings: List[InteractionFinding] = []
    for layer in layers:
        findings.extend(_same_layer_findings(tool, layer))
    findings.extend(_cross_layer_findings(tool, layers))

    findings.sort(
        key=lambda f: (
            f.kind,
            f.allow_pattern,
            f.guard_pattern,
            f.provenance.describe()
            if hasattr(f.provenance, "describe")
            else str(f.provenance),
            f.guard_provenance.describe() if f.guard_provenance is not None else "",
        )
    )
    return findings


def _same_layer_findings(tool: str, layer) -> List[InteractionFinding]:
    """
    Same-file findings for one layer: pairwise overlaps plus multi-section overlaps.

    Emits ``deny-shadows-allow`` / ``ask-overlaps-allow`` for each overlapping
    (allow, guard) pair, and a ``multi-section-interaction`` for any allow that
    overlaps BOTH a deny and an ask in this file.
    """
    findings: List[InteractionFinding] = []
    allow_tokens = [(a, default_prefix_tokens(a)) for a in layer.allow]
    # Per allow, remember the guards it overlaps in each section (for multi-section).
    overlaps: dict = {}
    guard_sets = (
        ("deny", layer.deny, "deny-shadows-allow"),
        ("ask", layer.ask, "ask-overlaps-allow"),
    )
    for section, guards, kind in guard_sets:
        for guard in guards:
            guard_tokens = default_prefix_tokens(guard)
            if guard_tokens is None:
                continue
            for allow, atokens in allow_tokens:
                if atokens is None:
                    continue
                if prefixes_overlap(atokens, guard_tokens):
                    findings.append(
                        InteractionFinding(
                            tool=tool,
                            provenance=layer.provenance,
                            kind=kind,
                            allow_pattern=allow,
                            guard_section=section,
                            guard_pattern=guard,
                            explanation=_explain(kind, allow, guard),
                        )
                    )
                    overlaps.setdefault(allow, {}).setdefault(section, []).append(guard)

    for allow, by_section in overlaps.items():
        if "deny" in by_section and "ask" in by_section:
            deny_guard = by_section["deny"][0]
            ask_guard = by_section["ask"][0]
            findings.append(
                InteractionFinding(
                    tool=tool,
                    provenance=layer.provenance,
                    kind="multi-section-interaction",
                    allow_pattern=allow,
                    guard_section="deny+ask",
                    guard_pattern=f"{deny_guard} / {ask_guard}",
                    explanation=_explain_multi_section(allow, deny_guard, ask_guard),
                )
            )
    return findings


def _cross_layer_findings(tool: str, layers: List) -> List[InteractionFinding]:
    """
    Findings where an allow's verdict depends on a guard in a different-specificity layer.

    For every allow in one layer and every deny/ask in another layer at a DIFFERENT
    specificity, a textual overlap yields a ``cross-layer-dependent`` finding whose
    explanation reflects which layer is more specific (and therefore decides).
    Same-specificity layers are skipped -- they resolve as one level, not a
    cross-level dependency.
    """
    findings: List[InteractionFinding] = []
    entries = [
        (
            layer,
            [(a, default_prefix_tokens(a)) for a in layer.allow],
            [("deny", g, default_prefix_tokens(g)) for g in layer.deny]
            + [("ask", g, default_prefix_tokens(g)) for g in layer.ask],
        )
        for layer in layers
    ]
    for allow_layer, allows, _ in entries:
        allow_spec = allow_layer.provenance.specificity
        for guard_layer, _, guards in entries:
            guard_spec = guard_layer.provenance.specificity
            if guard_spec == allow_spec:
                continue  # same level: resolved together, not a cross-level dependency
            allow_more_specific = allow_spec < guard_spec
            for section, guard, guard_tokens in guards:
                if guard_tokens is None:
                    continue
                for allow, atokens in allows:
                    if atokens is None:
                        continue
                    if prefixes_overlap(atokens, guard_tokens):
                        findings.append(
                            InteractionFinding(
                                tool=tool,
                                provenance=allow_layer.provenance,
                                kind="cross-layer-dependent",
                                allow_pattern=allow,
                                guard_section=section,
                                guard_pattern=guard,
                                explanation=_explain_cross_layer(
                                    section, allow, allow_more_specific, guard
                                ),
                                guard_provenance=guard_layer.provenance,
                            )
                        )
    return findings
