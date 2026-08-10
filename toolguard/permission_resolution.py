"""
Decision orchestration for permission resolution (TOO-45 D1, punch-list #03).

``Configuration`` is a query object over resolved config; this module is the
engine that DECIDES, driving the more-specific-wins cascade and applying the
TOO-19 parse-failure ASK floor. It is deliberately decoupled from
:mod:`toolguard.config`: it never imports that module, or :mod:`toolguard.resolve`.
It imports :mod:`toolguard.config_types`, :mod:`toolguard.permissions`,
:mod:`toolguard.file_matching`, and the stdlib -- all three are, like this
module, in the ``engine`` layer, and none of them import back into this one,
so the import graph stays a DAG. That decoupling is an import-graph claim
only: at runtime this module and :mod:`toolguard.file_matching` still call
``Configuration``'s methods through the Protocol-typed ``config`` parameter
below -- a real edge with no import counterpart, the same invisibility class
as the callable this punch-list removed. It is currently acyclic (narrowed,
not eliminated); nothing here would notice if a future ``Configuration``
method called back into this module.

Everything THIS MODULE needs from a configuration arrives through the
``config`` argument. :func:`resolve_command_permission` takes
:class:`~toolguard.config_types.ResolutionConfig` -- a narrow four-member
Protocol (TOO-45 D2):

- ``permission_levels_with_provenance(tool_name)``
- ``has_any_rules(tool_name)``
- ``resolved_no_match_fallback()``
- ``parse_failures`` (attribute)

:func:`resolve_file_path_permission` takes
:class:`~toolguard.config_types.FilePathResolutionConfig`, the same four plus
``resolve_config_path`` (project-root anchoring, forwarded to
:mod:`toolguard.file_matching`) -- see that Protocol's own docstring.

(``provenance_for_pattern``/``entry_for_pattern`` -- TOO-45 R2d moved these
off ``Configuration`` entirely, to live beside
:class:`~toolguard.config_types.ToolPatternLayer` in
:mod:`toolguard.config_types`, since they held no configuration state and
their whole job was reading that type. This module imports and calls them
directly rather than reaching them through ``config``.)

TOO-45 punch-list #03 removed the runtime cycle a static import graph could
not see: ``resolve.py`` used to hand this module a per-level decision
callable (``decide_detailed``) whose body lived in ``resolve.py`` itself, so
every real decision's call stack went ``resolve -> permission_resolution ->
resolve``. There is no injected callable any more.
:func:`resolve_command_permission`/:func:`resolve_file_path_permission`
import their matchers directly (:func:`~toolguard.permissions.decide_command_at_level_detailed`,
:func:`~toolguard.file_matching.decide_file_path_at_level_detailed`) and call
them eagerly, once per hierarchy level, before folding the results with
:func:`resolve_permission_cascade` -- a pure function of already-computed
:class:`~toolguard.config_types.LevelMatch` values, taking no callable and no
``config`` at all. This costs a small, measured amount of eager matching
(+0.58% of matcher invocations on the realistic corpus, since a few
allow/deny-decided levels that the old lazy cascade never had to visit for
override detection now always are) in exchange for a call graph every tool
here can check.

This is THE single chokepoint every governed tool's decision passes through
(see :mod:`toolguard.resolve`) -- both Bash/MCP-terminal (per sub-command) and
file-path (Read/Write/Edit) resolution call :func:`resolve_command_permission`/
:func:`resolve_file_path_permission` respectively.
"""

from typing import List, Optional, Sequence, Tuple

from toolguard.config_types import (
    ConflictOverride,
    FilePathResolutionConfig,
    LevelMatch,
    ResolutionConfig,
    RuntimeVerdict,
    ToolPatternLayer,
    entry_for_pattern,
    provenance_for_pattern,
)
from toolguard.file_matching import decide_file_path_at_level_detailed
from toolguard.permissions import decide_command_at_level_detailed

#: One hierarchy level's already-computed match paired with its contributing
#: layers -- the unit :func:`resolve_permission_cascade` folds over. A
#: strict pair, not two parallel sequences (this project's
#: ``find_parallel_arrays`` fitness check exists to catch exactly that
#: shape): every level's match and layers travel together from the moment
#: they are computed, so there is nothing to drift out of alignment.
LevelOutcome = Tuple[Optional[LevelMatch], Tuple[ToolPatternLayer, ...]]


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
    the single-sub-command chokepoint (:func:`resolve_permission_cascade`,
    via :func:`_apply_ask_floor`) and the compound-command boundary
    (:func:`toolguard.resolve.resolve_bash_permission_detailed`, which can
    produce a verdict from grammar-level
    :class:`~toolguard.parser.multiline.UndecidableSegment` instances that
    never reach :func:`resolve_command_permission` and so never see the
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


def _detect_override(
    levels: Sequence[LevelOutcome],
    winning_index: int,
    winning_pattern: str,
    winning_prov,
) -> Optional[ConflictOverride]:
    """
    Scan LESS-specific levels (after *winning_index*) for a deny overridden
    by the winning allow. Returns the first such :class:`ConflictOverride`,
    or None when no less-specific level denies the command.

    TOO-45 punch-list #03: *levels* carries each level's match already
    computed (the cascade is eager -- see :func:`resolve_permission_cascade`),
    so this only reads ``result.decision`` -- no matching happens here. The
    old lazy version's ``if not deny: continue`` skip is gone: it was purely
    an optimisation to avoid an unnecessary ``decide_detailed`` call on a
    level with no deny patterns (which could never yield ``decision ==
    'deny'`` anyway), and there is no call left here to skip.
    """
    for result, layers in levels[winning_index + 1 :]:
        # We only care about a DENY at this less-specific level. Matching is
        # deny-first, so a deny here surfaces as decision == 'deny'.
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
    levels: Sequence[LevelOutcome],
    tool_name: str,
    has_any_rules: bool,
    no_match_fallback: str,
    subject: str = "Command",
) -> RuntimeVerdict:
    """
    The raw more-specific-wins fold, BEFORE the TOO-19 ASK floor.

    Pure: *levels* already carries every hierarchy level's match, computed by
    the caller. The first level (most-specific first) whose match is not
    ``None`` wins. No match at any level falls through to the TOO-15 branch
    below (unconfigured tool vs. ``no_match_fallback``).

    Args:
        levels: One entry per hierarchy level, most-specific first -- see
            :data:`LevelOutcome`.
        tool_name: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'`` -- named
            only in the TOO-15 "entirely unconfigured" reason below.
        has_any_rules: Whether the tool has ANY rule configured anywhere
            (TOO-15) -- see :meth:`~toolguard.config_types.ResolutionConfig.has_any_rules`.
        no_match_fallback: The effective ``no_match_fallback`` policy -- see
            :meth:`~toolguard.config_types.ResolutionConfig.resolved_no_match_fallback`.
        subject: The noun the no-match-fallback reason (below) opens with --
            ``"Command"`` for Bash, ``"Path"`` for a file-path tool (TOO-45
            R3).

    Returns the per-level :class:`~toolguard.config_types.RuntimeVerdict`
    with ``tool``/``target`` left ``None`` (this function is never handed a
    target string) and ``overrides`` holding at most one ``(None,
    ConflictOverride)`` pair (no sub_command/target identifier is known at
    this layer; see ``RuntimeVerdict``'s docstring for how the two
    ``resolve.py`` callers re-pair it with a real identifier).
    """
    for index, (result, layers) in enumerate(levels):
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
            override = _detect_override(levels, index, matched_pattern, prov)
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
    if not has_any_rules:
        return RuntimeVerdict(
            decision="ask",
            reason=(
                f"No {tool_name} permission rules configured at any level; "
                f"defaulting to 'ask'"
            ),
            provenance=None,
        )
    fallback = no_match_fallback
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


def resolve_permission_cascade(
    levels: Sequence[LevelOutcome],
    tool_name: str,
    parse_failures: Tuple[Tuple[object, str], ...],
    has_any_rules: bool,
    no_match_fallback: str,
    subject: str = "Command",
) -> RuntimeVerdict:
    """
    Resolve a decision from already-computed per-level matches (TOO-45
    punch-list #03: the pure fold).

    Provenance and allow-over-deny conflict detection, then the TOO-19
    parse-failure ASK floor. Only allow-over-deny overrides are conflicts
    here -- ``hard_deny`` denials are handled by the caller BEFORE any
    matching happens and never reach this function at all.

    Pure: no matching happens here, and nothing here is a callable or a
    ``config`` object -- every level's match was already computed by the
    caller (:func:`resolve_command_permission`/:func:`resolve_file_path_permission`
    in production; a hand-built list in a test). This is what lets the
    cascade -- more-specific-wins, override detection, the ASK floor -- be
    tested in isolation from real pattern matching without an injected
    callable crossing a module boundary.

    Args:
        levels: One entry per hierarchy level, most-specific first -- see
            :data:`LevelOutcome`.
        tool_name: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
        parse_failures: The configuration's REAL, complete ``parse_failures``
            -- see :func:`apply_parse_failure_floor`'s caller obligation.
        has_any_rules: See :meth:`~toolguard.config_types.ResolutionConfig.has_any_rules`.
        no_match_fallback: See :meth:`~toolguard.config_types.ResolutionConfig.resolved_no_match_fallback`.
        subject: Forwarded to :func:`_resolve_unclamped` -- see that
            parameter's own docstring (TOO-45 R3). Defaults to ``"Command"``;
            :func:`resolve_file_path_permission` passes ``"Path"``.

    THE single chokepoint every governed tool's decision passes through (see
    :mod:`toolguard.resolve`) -- both the live hook and the read-only
    ``--eval``/replay path (:mod:`toolguard.api`) reach it in turn, via
    :func:`resolve_command_permission`/:func:`resolve_file_path_permission`.
    That is why the config-level ASK floor (TOO-19, see :func:`_apply_ask_floor`)
    is applied HERE rather than in the Bash-specific compound pipeline
    (:mod:`toolguard.compound`): it then covers every governed tool uniformly.
    """
    resolved = _resolve_unclamped(
        levels, tool_name, has_any_rules, no_match_fallback, subject
    )
    return _apply_ask_floor(parse_failures, resolved)


def resolve_command_permission(
    config: ResolutionConfig,
    tool_name: str,
    command: str,
    extended_syntax: bool = True,
) -> RuntimeVerdict:
    """
    Resolve one (already-decomposed) command against ``tool_name``'s cascade.

    Matches *command* against every hierarchy level eagerly (TOO-45
    punch-list #03), via :func:`~toolguard.permissions.decide_command_at_level_detailed`,
    then folds the results with :func:`resolve_permission_cascade`. The
    production entry point for Bash/MCP-terminal resolution -- see
    :mod:`toolguard.resolve`'s two public resolvers, which call this once
    per sub-command.
    """
    levels = config.permission_levels_with_provenance(tool_name)
    matched_levels: List[LevelOutcome] = [
        (
            decide_command_at_level_detailed(
                command,
                list(allow),
                list(deny),
                extended_syntax,
                ask_patterns=list(ask),
            ),
            layers,
        )
        for allow, deny, ask, layers in levels
    ]
    return resolve_permission_cascade(
        matched_levels,
        tool_name,
        config.parse_failures,
        config.has_any_rules(tool_name),
        config.resolved_no_match_fallback(),
    )


def resolve_file_path_permission(
    config: FilePathResolutionConfig,
    tool_name: str,
    file_path: str,
    extended_syntax: bool = True,
) -> RuntimeVerdict:
    """
    Resolve one file path against ``tool_name``'s cascade.

    Matches *file_path* against every hierarchy level eagerly (TOO-45
    punch-list #03), via :func:`~toolguard.file_matching.decide_file_path_at_level_detailed`
    (which needs ``config`` for project-root anchoring -- see
    :class:`~toolguard.config_types.FilePathResolutionConfig`), then folds
    the results with :func:`resolve_permission_cascade`. The production
    entry point for Read/Write/Edit resolution -- see
    :mod:`toolguard.resolve`'s file-path resolver, called AFTER the
    unoverridable ``[hard_deny]`` pool check.
    """
    levels = config.permission_levels_with_provenance(tool_name)
    matched_levels: List[LevelOutcome] = [
        (
            decide_file_path_at_level_detailed(
                file_path,
                list(allow),
                list(deny),
                config,
                extended_syntax,
                ask_patterns=list(ask),
            ),
            layers,
        )
        for allow, deny, ask, layers in levels
    ]
    return resolve_permission_cascade(
        matched_levels,
        tool_name,
        config.parse_failures,
        config.has_any_rules(tool_name),
        config.resolved_no_match_fallback(),
        subject="Path",
    )
