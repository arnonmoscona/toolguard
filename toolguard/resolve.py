"""
Permission resolver layer for toolguard.

The single entry point both callers share: the hook and the api/tooling
layer both call the two public functions below for a Bash or file-path
decision, so what the hook does at runtime and what tooling computes can
never drift apart.

Not pure: pattern matching reads live filesystem state (``normalization.py``'s
``exists()``/``is_symlink()``/``resolve()`` calls, reached through
``permissions.py``). The resulting check-to-use race is a known,
deliberately deprioritised design decision; it is not mitigated here.

No logging, no stdin/stdout, no ``sys.exit``, and never imports
``toolguard.hook`` (the reverse would be circular).
"""

from typing import List, Optional, Tuple

from toolguard.compound import (
    _combine_strictest,
    cap_context_words,
    decompose,
    judge_unit,
)
from toolguard.config_types import ConflictOverride
from toolguard.config_types import LevelMatch as LevelMatch
from toolguard.config_types import ResolveConfig
from toolguard.config_types import RuntimeVerdict as RuntimeVerdict
from toolguard.config_types import UnitVerdict as UnitVerdict
from toolguard.file_matching import check_file_path_hard_deny
from toolguard.permission_resolution import (
    apply_parse_failure_floor,
    resolve_command_permission,
    resolve_file_path_permission,
)
from toolguard.permissions import check_hard_deny


# ---------------------------------------------------------------------------
# Hard-deny lookup and the file-path resolver
# ---------------------------------------------------------------------------


def _hard_deny_additional_context(
    config, tool_name: str, matched_pattern: Optional[str]
) -> Optional[str]:
    """
    Look up the ``additionalContext`` of a matched ``[hard_deny]`` pattern.

    Shared by the file-path and Bash hard-deny paths, so their enrichment
    text cannot drift apart. Enrichment is cosmetic: any failure to resolve
    it degrades to ``None`` and never affects the deny itself.

    Args:
        config: The resolved configuration.
        tool_name: The governed tool whose hard-deny pool was matched.
        matched_pattern: The wrapper-stripped pattern that matched.

    Returns:
        The matched entry's enrichment text, or ``None`` when there is none
        or the pattern is unknown.
    """
    if matched_pattern is None:
        return None
    deny_entries, _allow_entries = config.hard_deny_entries(tool_name)
    for entry in deny_entries:
        if entry.stripped_pattern == matched_pattern:
            return entry.additional_context
    return None


def resolve_file_path_permission_detailed(
    tool_name: str,
    file_path: str,
    config: ResolveConfig,
    extended_syntax: bool = True,
) -> "RuntimeVerdict":
    """
    Resolve a file-path tool decision, hard-deny-first, more-specific-wins.

    The unoverridable ``[hard_deny]`` pool is checked first; a match denies
    immediately regardless of any level's own allow. Otherwise delegates to
    :func:`~toolguard.permission_resolution.resolve_file_path_permission`.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: The resolved configuration.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (see that class's
        docstring for field meanings).
    """
    hard = check_file_path_hard_deny(tool_name, file_path, config, extended_syntax)
    if hard is not None:
        return RuntimeVerdict(
            decision=hard.decision,
            reason=hard.reason,
            provenance=None,
            additional_context=cap_context_words(
                _hard_deny_additional_context(config, tool_name, hard.matched_pattern)
            ),
            matched_rule=hard.matched_pattern,
            tool=tool_name,
            target=file_path,
        )

    resolved = resolve_file_path_permission(
        config, tool_name, file_path, extended_syntax
    )
    # The per-level verdict pairs its bare override with identifier None
    # (see RuntimeVerdict's "overrides" docstring); re-pair with the real
    # file path now that it is known.
    overrides = [(file_path, override) for _, override in resolved.overrides]
    return RuntimeVerdict(
        decision=resolved.decision,
        reason=resolved.reason,
        provenance=resolved.provenance,
        overrides=overrides,
        additional_context=cap_context_words(resolved.additional_context),
        fallback_warning=resolved.fallback_warning,
        matched_rule=resolved.matched_rule,
        tool=tool_name,
        target=file_path,
    )


# ---------------------------------------------------------------------------
# Bash / command-tool resolver
# ---------------------------------------------------------------------------


def _deciding_sub_match(
    decision: str, sub_matches: List[UnitVerdict]
) -> Optional[UnitVerdict]:
    """
    Find the sub-command that decided a compound Bash verdict, if there is one.

    For 'deny'/'ask', returns the first sub-command whose own decision
    equals *decision* -- an escape-hatch floor (the ASK floor for foreign
    inline code, or ``undecidable_fallback``) can override a leaf's rule
    match, so this checks the leaf's TRUE FINAL decision, not just whichever
    rule first matched it.

    For 'allow', returns the sub-command when exactly one entry both allowed
    and carries a genuine ``matched_rule`` -- an escape-hatch allow is
    excluded, since the escape hatch decided, not a rule. With zero or more
    than one such entry, including a multi-leaf all-allow compound where
    every leaf's own rule had to allow, there is no single decider and this
    returns ``None``. The filter matters in the mixed case -- one genuine
    allow plus one escape-hatch allow -- where without it the genuine
    match would lose its attribution.

    Args:
        decision: The compound's final decision, after the parse-failure
            floor (:func:`~toolguard.permission_resolution.apply_parse_failure_floor`)
            has already been applied.
        sub_matches: The per-sub-command records accumulated while
            resolving, in extraction order.

    Returns:
        The deciding :class:`UnitVerdict`, or ``None`` when there is no single
        decider to attribute.
    """
    if decision in ("deny", "ask"):
        for sub_match in sub_matches:
            if sub_match.decision == decision:
                return sub_match
        return None
    if decision == "allow":
        genuine = [
            sub_match
            for sub_match in sub_matches
            if sub_match.decision == "allow" and sub_match.matched_rule is not None
        ]
        if len(genuine) == 1:
            return genuine[0]
    return None


def resolve_bash_permission_detailed(
    command: str,
    config: ResolveConfig,
    extended_syntax: bool,
    hard_deny_deny,
    hard_deny_allow,
) -> "RuntimeVerdict":
    """
    Resolve a (possibly compound) Bash command, with per-sub-command provenance.

    Each extracted sub-command is resolved independently -- the unoverridable
    ``[hard_deny]`` pool first, then the more-specific-wins cascade -- and
    the sub-decisions are combined strictest-wins (deny > ask > allow) via
    :func:`toolguard.compound._combine_strictest`. Foreign inline code /
    heredoc sinks and undecidable segments (control structures, process
    substitution) that cannot be safely decomposed are floored per
    ``config.resolved_undecidable_fallback()`` -- see
    :func:`toolguard.compound.judge_unit`.

    Allow-over-deny overrides discovered on any sub-command are returned so
    the caller can log them to the conflict stream; a ``hard_deny`` denial is
    never a conflict.

    Args:
        command: The bash command line (may be compound).
        config: The resolved configuration.
        extended_syntax: Whether extended prefixes are honoured.
        hard_deny_deny: Pooled hard-deny deny patterns for Bash.
        hard_deny_allow: Pooled hard-deny allow (carve-out) patterns for Bash.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (see that class's
        docstring for field meanings), with per-sub-command detail recorded
        in ``sub_matches`` and ``provenance``/``matched_rule`` sourced from
        :func:`_deciding_sub_match`.
    """
    overrides: List[Tuple[str, ConflictOverride]] = []
    sub_matches: List[UnitVerdict] = []

    def _decide(sub_command: str) -> Tuple[UnitVerdict, Optional[ConflictOverride]]:
        """Resolve one sub-command: hard-deny pool first, then the cascade."""
        hard = check_hard_deny(
            sub_command, list(hard_deny_deny), list(hard_deny_allow), extended_syntax
        )
        if hard is not None:
            return (
                UnitVerdict(
                    sub_command=sub_command,
                    decision=hard.decision,
                    matched_rule=hard.matched_pattern,
                    provenance=None,  # hard_deny is pooled; no single provenance
                    reason=hard.reason,
                    additional_context=_hard_deny_additional_context(
                        config, "Bash", hard.matched_pattern
                    ),
                    fallback_kind=None,  # hard-deny is always a genuine match, never an escape hatch
                ),
                None,  # override
            )

        resolved = resolve_command_permission(
            config, "Bash", sub_command, extended_syntax
        )
        fallback_kind = None
        if resolved.decision == "allow" and resolved.matched_rule is None:
            fallback_kind = "warned" if resolved.fallback_warning else "silent"
        override = resolved.overrides[0][1] if resolved.overrides else None
        return (
            UnitVerdict(
                sub_command=sub_command,
                decision=resolved.decision,
                matched_rule=resolved.matched_rule,
                provenance=resolved.provenance,
                reason=resolved.reason,
                additional_context=resolved.additional_context,
                fallback_kind=fallback_kind,
            ),
            override,
        )

    units = decompose(command)
    unit_verdicts: List[UnitVerdict] = []
    for unit in units:
        part_verdicts: List[UnitVerdict] = []
        for part in unit.parts:
            verdict, override = _decide(part)
            part_verdicts.append(verdict)
            if (
                not unit.audits_as_one
                and verdict.decision == "allow"
                and override is not None
            ):
                # Gate on the same `audits_as_one` field that governs
                # sub_matches below, so an inline-code unit's outer-stub
                # probe (not a real per-sub-command decision) never
                # contributes a conflict-log entry of its own.
                overrides.append((part, override))
        judged = judge_unit(unit, part_verdicts, config.resolved_undecidable_fallback())
        unit_verdicts.append(judged)
        # A plain unit audits as its own sub-commands; a floored or
        # undecidable unit audits as ONE entry, since the floor -- not any
        # part's rule match -- decided it. Read from unit.audits_as_one (set
        # by _unit_for) rather than unit.kind: a fifth CommandUnit.kind
        # cannot be added without deciding audits_as_one, so this driver
        # cannot silently under-audit it the way a `unit.kind == "plain"`
        # check could.
        if unit.audits_as_one:
            sub_matches.append(judged)
        else:
            sub_matches.extend(part_verdicts)

    if not units:
        # decompose(command) returning [] would otherwise reach
        # _combine_strictest's own generic "No commands to evaluate"
        # wording; use the same reason text
        # resolve_compound_permission_detailed's equivalent guard uses.
        combined = RuntimeVerdict(
            decision="deny", reason="No valid commands found in command line"
        )
    else:
        combined = _combine_strictest(unit_verdicts)
    decision, reason, additional_context, fallback_warning = (
        combined.decision,
        combined.reason,
        combined.additional_context,
        combined.fallback_warning,
    )

    # Re-apply the parse-failure ASK floor here, at the compound boundary --
    # this is NOT redundant with the per-sub-command application inside
    # _decide. A grammar-level undecidable unit (process substitution,
    # `case`, unparseable control structures) has no parts and never calls
    # _decide, so the per-leaf floor never runs for it; only this call site
    # sees the final compound decision regardless of how it was produced.
    # Reapplying to an already-floored decision is an idempotent no-op. Do
    # NOT remove this as "redundant" -- doing so reopens a fail-open bypass
    # for undecidable segments.
    decision, reason = apply_parse_failure_floor(
        config.parse_failures, decision, reason
    )

    # Overrides are only conflicts when the overall decision is 'allow';
    # clear them otherwise. fallback_warning is cleared here too because the
    # parse-failure floor above can clamp 'allow' down to 'ask', and a
    # since-overridden verdict must not still claim a WARNING-stream entry.
    if decision != "allow":
        overrides = []
        fallback_warning = False
    deciding = _deciding_sub_match(decision, sub_matches)
    return RuntimeVerdict(
        decision=decision,
        reason=reason,
        provenance=deciding.provenance if deciding is not None else None,
        overrides=overrides,
        sub_matches=sub_matches,
        additional_context=cap_context_words(additional_context),
        fallback_warning=fallback_warning,
        matched_rule=deciding.matched_rule if deciding is not None else None,
        tool="Bash",
        target=command,
    )
