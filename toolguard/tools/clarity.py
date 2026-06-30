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
from typing import List

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
        guard_section: The section of the overlapping guard -- ``'deny'`` or
            ``'ask'``.
        guard_pattern: The wrapper-free guard body that overlaps the allow.
        explanation: A render-ready explanation of the ACTUAL resolution, so the
            confusing interaction is made legible rather than just flagged.
    """

    tool: str
    provenance: Provenance
    kind: str
    allow_pattern: str
    guard_section: str
    guard_pattern: str
    explanation: str


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


def find_confusing_interactions(
    config: Configuration, tool: str
) -> List[InteractionFinding]:
    """
    Detect confusing same-file allow/guard overlaps for ``tool``.

    For each config layer, reports any DEFAULT allow rule whose command-space
    overlaps a DEFAULT deny or ask rule in the SAME layer.  Non-DEFAULT patterns
    (``[regex]``/``[glob]``/``[native]``) are not analysed.  Findings are textual
    overlaps; each carries an explanation of the real resolution.

    Args:
        config: The resolved configuration to inspect.
        tool: Tool name to inspect (e.g. ``'Bash'``).

    Returns:
        A deterministically ordered list of :class:`InteractionFinding` records.
    """
    findings: List[InteractionFinding] = []

    for layer in per_layer_rules(config, tool):
        allow_tokens = [(a, default_prefix_tokens(a)) for a in layer.allow]
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

    findings.sort(
        key=lambda f: (
            f.kind,
            f.allow_pattern,
            f.guard_pattern,
            f.provenance.describe()
            if hasattr(f.provenance, "describe")
            else str(f.provenance),
        )
    )
    return findings
