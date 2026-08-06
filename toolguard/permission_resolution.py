"""
Decision orchestration for permission resolution (TOO-45 D1).

``Configuration`` is a query object over resolved config; this module is the
engine that DECIDES, driving the more-specific-wins cascade and applying the
TOO-19 parse-failure ASK floor. It is deliberately decoupled from
:mod:`toolguard.config`: it imports only :mod:`toolguard.config_types` and the
stdlib, never ``toolguard.config`` itself. Everything THIS MODULE needs from a
configuration arrives through the ``config`` argument, duck-typed against a
narrow four-member surface:

- ``permission_levels_with_provenance(tool_name)``
- ``has_any_rules(tool_name)``
- ``resolved_no_match_fallback()``
- ``parse_failures`` (attribute)

(``provenance_for_pattern``/``entry_for_pattern`` -- TOO-45 R2d moved these
off ``Configuration`` entirely, to live beside
:class:`~toolguard.config_types.ToolPatternLayer` in
:mod:`toolguard.config_types`, since they held no configuration state and
their whole job was reading that type. This module imports and calls them
directly rather than reaching them through ``config``, shrinking the
duck-typed surface below from six members to four.)

A test double built for THIS module's own functions only needs to implement
these four members. That is NOT true of a double driven through
:mod:`toolguard.resolve` (the module's real caller): it additionally calls
``config.resolve_config_path`` and ``config.resolved_undecidable_fallback``
directly, for reasons outside this module's own scope.

This is THE single chokepoint every governed tool's decision passes through
(see :mod:`toolguard.resolve`) -- both Bash/MCP-terminal (per sub-command) and
file-path (Read/Write/Edit) resolution call :func:`resolve_permission_detailed`.
"""

from typing import Callable, Optional, Tuple

from toolguard.config_types import (
    ConflictOverride,
    LevelMatch,
    RuntimeVerdict,
    entry_for_pattern,
    provenance_for_pattern,
)


def _append_provenance(reason: str, provenance) -> str:
    """
    Append matched-rule provenance to *reason* as a bracketed suffix.

    Appended AFTER the reason (not prepended) so existing
    ``reason.split(': ', 1)`` / "matches allow pattern: X" substring
    consumers keep working, e.g.::

        Command matches allow pattern: git *  [project: /p/.claude/toolguard_hook.toml]

    Returns *reason* unchanged when *provenance* is None.
    """
    if provenance is None:
        return reason
    return f"{reason}  [{provenance.describe_brief()}]"


def _parse_failure_reason(parse_failures: Tuple[Tuple[object, str], ...]) -> str:
    """
    Build the user-visible ASK-floor reason naming every broken config file.

    This becomes ``permissionDecisionReason``, shown directly to the user in
    Claude Code's permission prompt -- keep it compact and actionable.
    """
    files = "\n".join(f"  {path}: {message}" for path, message in parse_failures)
    return (
        "toolguard config is BROKEN -- falling back to ask for every tool "
        "call.\nUnparseable file(s):\n"
        f"{files}\n"
        "Rules in these files are NOT being enforced. Fix the file(s) to "
        "restore normal permission handling."
    )


def apply_parse_failure_floor(
    parse_failures: Tuple[Tuple[object, str], ...], decision: str, reason: str
) -> Tuple[str, str]:
    """
    Clamp a plain ``(decision, reason)`` pair to 'ask' on a broken config.

    The CORE clamp (TOO-19 fail-open-via-undecidable-segments fix), shared by
    the single-sub-command chokepoint (:func:`resolve_permission_detailed`,
    via :func:`_apply_ask_floor`) and the compound-command boundary
    (:func:`toolguard.resolve.resolve_bash_permission_detailed`, which can
    produce a verdict from grammar-level
    :class:`~toolguard.parser.multiline.UndecidableSegment` instances that
    never reach :func:`resolve_permission_detailed` and so never see the
    per-leaf clamp). There must be exactly ONE implementation so the two call
    sites cannot drift. Never weakens an already-``'deny'`` decision.

    HARD INVARIANT (TOO-19): this clamp is UNCONDITIONAL and takes no
    settings-driven parameter -- in particular it never consults
    ``undecidable_fallback``, and no future setting may be threaded in to
    relax it. A parse failure means toolguard does not know what its rules
    ARE, so it has no basis for any verdict at all; it is not a policy
    question a config value can answer. Keep this function's signature free
    of any fallback-selection parameter.

    Caller obligation: *parse_failures* must be the configuration's REAL,
    complete ``parse_failures`` -- never ``()`` and never a filtered subset.
    Passing anything else silently disables this floor for whatever it
    omits, and nothing else in this module re-derives or checks that.
    """
    if not parse_failures or decision == "deny":
        return decision, reason
    return "ask", _parse_failure_reason(parse_failures)


def _apply_ask_floor(
    parse_failures: Tuple[Tuple[object, str], ...], resolved: RuntimeVerdict
) -> RuntimeVerdict:
    """
    Clamp *resolved* to 'ask' when any governed config file failed to parse.

    Config-level counterpart of the ASK floor in ``toolguard/compound.py``
    (``_resolve_leaf``, for foreign inline code). Delegates the clamp
    decision to :func:`apply_parse_failure_floor` so the two call sites
    cannot drift; this function's own job is translating to/from
    :class:`~toolguard.config_types.RuntimeVerdict` and clearing the
    fields that describe a rule match that no longer determines the verdict.
    """
    # TOO-45 D1a item A: this guard LOOKS identical to
    # apply_parse_failure_floor's own `decision == "deny"` check above, but it
    # is NOT redundant with it -- that one decides whether to rewrite
    # (decision, reason); this one additionally decides whether
    # provenance/overrides/additional_context survive. Deleting this guard
    # (keeping only the delegate's) silently drops all three from a genuine
    # deny made under a broken config -- caught by
    # test_permission_resolution.TestDenyUnderBrokenConfigKeepsProvenance.
    if not parse_failures or resolved.decision == "deny":
        return resolved
    decision, reason = apply_parse_failure_floor(
        parse_failures, resolved.decision, resolved.reason
    )
    # overrides/sub_matches/additional_context/fallback_warning/matched_rule/
    # tool/target all fall back to RuntimeVerdict's own defaults (empty
    # list/False/None) -- matches the OLD 5-positional
    # ResolvedDecision(decision, reason, None, None, None) call this replaced,
    # which never passed a value for those fields either.
    return RuntimeVerdict(decision=decision, reason=reason, provenance=None)


#: The ``decide_detailed`` callback contract every caller of
#: :func:`resolve_permission_detailed` supplies: given one hierarchy level's
#: (or hard-deny pool's) allow/deny/ask pattern lists, return the level's
#: match, or ``None`` when nothing there matched. TOO-45 R1f: this used to be
#: documented as returning a bare ``(decision, reason, matched_pattern)``
#: tuple; the real implementations
#: (:func:`toolguard.permissions.decide_command_at_level_detailed`,
#: :func:`toolguard.permissions.check_hard_deny`,
#: :func:`toolguard.resolve._decide_file_path_at_level_detailed`,
#: :func:`toolguard.resolve._check_file_path_hard_deny`) now all return
#: :class:`~toolguard.config_types.LevelMatch` instead.
DecideDetailed = Callable[[object, object, object], Optional[LevelMatch]]


def _detect_override(
    levels,
    winning_index,
    winning_pattern,
    winning_prov,
    decide_detailed: DecideDetailed,
) -> Optional[ConflictOverride]:
    """
    Scan LESS-specific levels (after *winning_index*) for a deny overridden
    by the winning allow. Returns the first such :class:`ConflictOverride`,
    or None when no less-specific level denies the command.
    """
    for allow, deny, ask, layers in levels[winning_index + 1 :]:
        if not deny:
            continue
        result = decide_detailed(allow, deny, ask)
        # We only care about a DENY at this less-specific level. ``decide``
        # is deny-first, so a deny here surfaces as decision == 'deny'.
        if result is not None and result.decision == "deny":
            overridden_pattern = result.matched_pattern
            overridden_prov = provenance_for_pattern(layers, overridden_pattern, "deny")
            return ConflictOverride(
                winning_pattern=winning_pattern,
                winning_provenance=winning_prov,
                overridden_pattern=overridden_pattern,
                overridden_provenance=overridden_prov,
            )
    return None


def _resolve_unclamped(
    config, tool_name: str, decide_detailed: DecideDetailed, subject: str = "Command"
) -> RuntimeVerdict:
    """
    The raw more-specific-wins resolution, BEFORE the TOO-19 ASK floor.

    Evaluates hierarchy levels MOST-SPECIFIC -> LEAST-SPECIFIC; the first
    level that matches anything wins. No match at any level falls through to
    the TOO-15 branch below (unconfigured tool vs. no_match_fallback).

    Args:
        config: The resolved configuration (duck-typed, see the module
            docstring).
        tool_name: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
        decide_detailed: See :data:`DecideDetailed`.
        subject: The noun the no-match-fallback reason (below) opens with --
            ``"Command"`` for Bash, ``"Path"`` for a file-path tool. TOO-45
            R3: this lets each caller get its own correctly-phrased reason
            AT THE SOURCE, rather than resolving with the Bash-phrased
            default and having ``resolve.py``'s file-path caller rewrite the
            prefix afterwards by parsing it back out of *reason* (the R3
            violation this parameter replaces -- see
            :func:`~toolguard.resolve.resolve_file_path_permission_detailed`'s
            call site, the only one that passes a non-default value).

    Returns the per-level :class:`~toolguard.config_types.RuntimeVerdict`
    with ``tool``/``target`` left ``None`` (this function is never handed a
    target string -- ``decide_detailed`` closes over it privately) and
    ``overrides`` holding at most one ``(None, ConflictOverride)`` pair (no
    sub_command/target identifier is known at this layer; see
    ``RuntimeVerdict``'s docstring for how the two ``resolve.py`` callers
    re-pair it with a real identifier).
    """
    levels = config.permission_levels_with_provenance(tool_name)
    for index, (allow, deny, ask, layers) in enumerate(levels):
        result = decide_detailed(allow, deny, ask)
        if result is None:
            continue
        decision, reason, matched_pattern = (
            result.decision,
            result.reason,
            result.matched_pattern,
        )
        # decision is 'allow' | 'ask' | 'deny'; map it to the list the matched
        # pattern lives in so provenance resolves to the right rule.
        kind = decision
        prov = provenance_for_pattern(layers, matched_pattern, kind)
        reason_with_prov = _append_provenance(reason, prov)
        winning_entry = entry_for_pattern(layers, matched_pattern, kind)
        additional_context = (
            winning_entry.additional_context if winning_entry is not None else None
        )

        override = None
        if decision == "allow":
            override = _detect_override(
                levels, index, matched_pattern, prov, decide_detailed
            )
        return RuntimeVerdict(
            decision=decision,
            reason=reason_with_prov,
            provenance=prov,
            overrides=[(None, override)] if override is not None else [],
            additional_context=additional_context,
            # TOO-45 R3: carry the matched pattern instead of discarding it
            # into `reason_with_prov` for callers to parse back out. It is
            # already in hand here -- both lookups above key off it.
            matched_rule=matched_pattern,
        )

    # No level matched anything for this command/path (TOO-15). Two distinct
    # cases share this fail-closed branch:
    #
    # - The tool has NO permission rules configured anywhere (no allow, deny,
    #   ask, or hard_deny at any level): the tool is entirely unconfigured, so
    #   this ALWAYS resolves to 'ask' -- regardless of no_match_fallback -- so
    #   a fresh install is never bricked by a blanket deny. A user who wants
    #   fail-closed-on-empty writes their own catch-all deny rule, which then
    #   flows through the normal matched-deny branch above.
    # - Rules ARE configured but simply did not match: governed by
    #   no_match_fallback -- 'ask' (the default), 'deny', 'allow_with_warning'
    #   (allow, with a warning reason instead of blocking), or 'allow' (TOO-19;
    #   allow with NO warning anywhere). The deprecated legacy value
    #   'warn_deny' is normalized to 'allow_with_warning', and the deliberate
    #   long-form synonym 'allow_with_no_warnings' is normalized to 'allow',
    #   both by resolved_no_match_fallback() before this branch ever sees them.
    if not config.has_any_rules(tool_name):
        return RuntimeVerdict(
            decision="ask",
            reason=(
                f"No {tool_name} permission rules configured at any level; "
                f"defaulting to 'ask'"
            ),
            provenance=None,
        )
    fallback = config.resolved_no_match_fallback()
    if fallback == "allow_with_warning":
        return RuntimeVerdict(
            decision="allow",
            reason=(
                f"{subject} does not match any allow patterns; allowed with a "
                "warning by no_match_fallback=allow_with_warning (add an "
                "explicit rule to silence this)"
            ),
            provenance=None,
            fallback_warning=True,
        )
    if fallback == "allow":
        return RuntimeVerdict(
            decision="allow",
            reason=(
                f"{subject} does not match any allow patterns; allowed with no "
                "warning by no_match_fallback=allow (add an explicit rule to "
                "silence this)"
            ),
            provenance=None,
        )
    if fallback == "ask":
        return RuntimeVerdict(
            decision="ask",
            reason=(
                f"{subject} does not match any allow patterns; awaiting a "
                "decision (no_match_fallback=ask)"
            ),
            provenance=None,
        )
    return RuntimeVerdict(
        decision="deny",
        reason=f"{subject} does not match any allow patterns",
        provenance=None,
    )


def resolve_permission_detailed(
    config,
    tool_name: str,
    decide_detailed: DecideDetailed,
    subject: str = "Command",
) -> RuntimeVerdict:
    """
    Resolve a decision with provenance and allow-over-deny conflict detection.

    ``decide_detailed`` must return a
    :class:`~toolguard.config_types.LevelMatch` (or ``None``) so the matched
    rule can be mapped to its source provenance -- see :data:`DecideDetailed`.
    Only allow-over-deny overrides are conflicts here -- ``hard_deny``
    denials are handled by the caller BEFORE this runs and never reach it.

    Args:
        config: The resolved configuration (duck-typed, see the module
            docstring).
        tool_name: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
        decide_detailed: See :data:`DecideDetailed`.
        subject: Forwarded to :func:`_resolve_unclamped` -- see that
            parameter's own docstring (TOO-45 R3). Defaults to ``"Command"``,
            matching every caller before this parameter existed; only
            :mod:`toolguard.resolve`'s file-path entry point passes
            ``"Path"``.

    THE single chokepoint every governed tool's decision passes through (see
    :mod:`toolguard.resolve`) -- both the live hook and the read-only
    ``--eval``/replay path (:mod:`toolguard.tools.decision`) call it in turn.
    That is why the config-level ASK floor (TOO-19, see :func:`_apply_ask_floor`)
    is applied HERE rather than in the Bash-specific compound pipeline
    (:mod:`toolguard.compound`): it then covers every governed tool uniformly.
    """
    resolved = _resolve_unclamped(config, tool_name, decide_detailed, subject)
    return _apply_ask_floor(config.parse_failures, resolved)
