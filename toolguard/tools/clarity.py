"""
Rule-interaction clarity analyzer.

toolguard's within-file resolution has non-obvious semantics: a deny wins over
any allow or ask in its own layer, however specific they are; otherwise the more
specific of a matching allow and ask wins, with an exact tie going to ask; and a
blanket ``*``-class ask is excluded from matching altogether, so a layer holding
only that declines to decide and the cascade runs on past it.  A rule set can
therefore be CORRECT yet inscrutable -- even an expert cannot reliably
eyeball the effective verdict, and a "correct but confusing" config is a latent
bug.

This module detects a curated catalog of such interactions and states the
resolution each one actually produces.  Overlap is decided TEXTUALLY, ignoring
precedence: detection says two rules share command-space, and the explanation
says which of them wins.
"""

from dataclasses import dataclass
from typing import List, Optional

from toolguard.config import Configuration, Provenance
from toolguard.tools.config_access import per_layer_rules
from toolguard.tools.pattern_overlap import default_prefix_tokens, prefixes_overlap


@dataclass(frozen=True)
class InteractionFinding:
    """
    One confusing rule interaction, with a render-ready explanation.

    Attributes:
        tool: Tool the interacting rules apply to (e.g. ``'Bash'``).
        provenance: Layer holding the ALLOW.  For a same-layer finding the guard
            is there too; for ``'cross-layer-dependent'`` the guard's layer is in
            :attr:`guard_provenance`.
        kind: ``'deny-shadows-allow'``, ``'ask-overlaps-allow'``,
            ``'multi-section-interaction'`` or ``'cross-layer-dependent'``.
        allow_pattern: The wrapper-free allow body involved.
        guard_section: The section of the overlapping guard -- ``'deny'``,
            ``'ask'``, or ``'deny+ask'`` for a multi-section interaction.
        guard_pattern: The wrapper-free guard body, or ``'<deny> / <ask>'`` for a
            multi-section interaction.
        explanation: Prose stating the ACTUAL resolution, so the interaction is
            made legible rather than merely flagged.
        guard_provenance: Layer holding the guard, set only for
            ``'cross-layer-dependent'``; ``None`` otherwise.
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
    """Explanation for a same-layer pairwise overlap; ``kind`` selects the wording."""
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
    """Explanation for an allow overlapping BOTH a deny and an ask in one layer."""
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
    Explanation for an allow whose verdict depends on a guard in ANOTHER layer.

    ``allow_more_specific`` is True when the allow's layer carries the LOWER
    specificity index (0 = project, the most specific level).
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

    Only prefix-shaped DEFAULT patterns (``cmd:*`` and ``cmd:**``) take part.
    Everything else is skipped on whichever side of the comparison it appears --
    ``[regex]``/``[glob]``/``[native]``, an args-bearing body like
    ``git commit:-m *``, and a bare ``ls``.  Three families are reported:

    - **Same-layer pairwise** -- an allow overlapping a deny
      (``deny-shadows-allow``) or an ask (``ask-overlaps-allow``).
    - **Same-layer multi-section** -- an allow overlapping BOTH a deny AND an ask
      (``multi-section-interaction``).
    - **Cross-layer** -- an allow overlapping a deny/ask in a layer of different
      specificity (``cross-layer-dependent``).

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
    Same-layer findings for one layer: pairwise overlaps plus multi-section overlaps.

    Emits ``deny-shadows-allow`` / ``ask-overlaps-allow`` for every overlapping
    (allow, guard) pair, and one ``multi-section-interaction`` for an allow that
    overlaps both a deny and an ask -- naming the first overlapping guard from
    each section.
    """
    findings: List[InteractionFinding] = []
    allow_tokens = [(a, default_prefix_tokens(a)) for a in layer.allow]
    # allow -> section -> overlapping guards, for the multi-section pass below.
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

    Layers of equal specificity are skipped: they resolve as one level, so a guard
    there is not a cross-level dependency.
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
                continue
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
