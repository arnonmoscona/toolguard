"""
The decision engine for permission resolution.

``Configuration`` (:mod:`toolguard.config`) is a query object over resolved config; this
module is the engine that DECIDES, driving the more-specific-wins cascade and applying the
TOO-19 parse-failure ASK floor. This is THE single chokepoint every governed tool's decision
passes through (see :mod:`toolguard.resolve`): both Bash/MCP-terminal (per sub-command) and
file-path (Read/Write/Edit) resolution call :func:`resolve_command_permission`/
:func:`resolve_file_path_permission` respectively.

It never imports :mod:`toolguard.config` or :mod:`toolguard.resolve` -- only
:mod:`toolguard.config_types`, :mod:`toolguard.constants`, :mod:`toolguard.permissions`,
:mod:`toolguard.file_matching`, and the stdlib, and none of the toolguard ones import back into
this one, so the import graph stays a DAG, which ``test.unit.test_architecture`` enforces. That is an import-graph property only:
at runtime this module and :mod:`toolguard.file_matching` still call a real ``Configuration``'s
methods through the Protocol-typed ``config`` parameter below -- a real coupling the import
graph does not show, and nothing would flag a future ``Configuration`` method calling back into
this module.

Everything this module needs about one decision arrives through a single ``context``
parameter (TOO-28): :func:`resolve_command_permission` takes
:class:`~toolguard.config_types.ResolutionContext`; :func:`resolve_file_path_permission`
takes :class:`~toolguard.config_types.FilePathResolutionContext`, the same surface narrowed
so ``context.config`` additionally supports ``resolve_config_path`` (project-root anchoring,
forwarded to :mod:`toolguard.file_matching`) -- see those Protocols' own docstrings for what
each member means. A concrete :class:`~toolguard.invocation.Invocation` structurally
satisfies both; this module never imports it, the same way it never imports
:mod:`toolguard.config`.
:func:`~toolguard.config_types.provenance_for_pattern`/
:func:`~toolguard.config_types.entry_for_pattern` live in :mod:`toolguard.config_types`,
beside :class:`~toolguard.config_types.ToolPatternLayer`, and are imported and called
directly here rather than reached through ``config``.

Each hierarchy level's match is computed eagerly by the caller
(:func:`resolve_command_permission`/:func:`resolve_file_path_permission`, via
:func:`~toolguard.permissions.decide_command_at_level_detailed`/
:func:`~toolguard.file_matching.decide_file_path_at_level_detailed`) before
:func:`resolve_permission_cascade` folds the results -- a pure function of already-computed
:class:`~toolguard.config_types.LevelMatch` values, taking no callable and no ``config`` at
all. This costs a small amount of extra matching: a level is matched even when a
more-specific level already decided the outcome.
"""

from typing import List, Optional, Sequence, Tuple

from toolguard.config_types import (
    AUTO_PERMISSION_MODE,
    CommandSpellings,
    ConflictOverride,
    FilePathResolutionContext,
    LevelMatch,
    ResolutionContext,
    RuntimeVerdict,
    ToolPatternLayer,
    entry_for_pattern,
    provenance_for_pattern,
)
from toolguard.constants import (
    DECISION_ALLOW,
    DECISION_ASK,
    DECISION_DENY,
    FALLBACK_ALLOW_WITH_WARNING,
)
from toolguard.file_matching import decide_file_path_at_level_detailed
from toolguard.permissions import decide_command_at_level_detailed

#: One hierarchy level's already-computed match paired with its contributing
#: layers -- the unit :func:`resolve_permission_cascade` folds over. A
#: strict pair, not two parallel sequences: every level's match and layers
#: travel together from the moment they are computed, so there is nothing to
#: drift out of alignment.
LevelOutcome = Tuple[Optional[LevelMatch], Tuple[ToolPatternLayer, ...]]


def _append_provenance(reason: str, provenance) -> str:
    """
    Append matched-rule provenance to *reason* as a bracketed suffix.

    Appended as a suffix, not a prefix, so the ``<lead-in>: <pattern>`` shape
    of the reason survives, e.g.::

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

    The core TOO-19 clamp, shared by two call sites so they cannot drift: the
    single-sub-command chokepoint (:func:`resolve_permission_cascade`, via
    :func:`_apply_ask_floor`) and the compound-command boundary
    (:func:`toolguard.resolve.resolve_bash_permission_detailed`, which can
    produce a verdict from grammar-level
    :class:`~toolguard.parser.command_extractor.UndecidableSegment` instances
    that never reach :func:`resolve_command_permission` and so never see the
    per-leaf clamp). Never weakens an already-``'deny'`` decision.

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
    if not parse_failures or decision == DECISION_DENY:
        return decision, reason
    return DECISION_ASK, _parse_failure_reason(parse_failures)


def _apply_ask_floor(
    parse_failures: Tuple[Tuple[object, str], ...], resolved: RuntimeVerdict
) -> RuntimeVerdict:
    """
    Clamp *resolved* to 'ask' when any governed config file failed to parse.

    Delegates the clamp decision to :func:`apply_parse_failure_floor` so the
    two call sites cannot drift; this function's own job is translating
    to/from :class:`~toolguard.config_types.RuntimeVerdict` and clearing the
    fields that describe a rule match that no longer determines the verdict.
    """
    # This guard looks identical to apply_parse_failure_floor's own
    # `decision == "deny"` check above, but is NOT redundant with it -- that
    # one decides whether to rewrite (decision, reason); this one additionally
    # decides whether provenance/overrides/additional_context survive.
    # Deleting this guard (keeping only the delegate's) silently drops all
    # three from a genuine deny made under a broken config -- caught by
    # test_permission_resolution.TestDenyUnderBrokenConfigKeepsProvenance.
    if not parse_failures or resolved.decision == DECISION_DENY:
        return resolved
    decision, reason = apply_parse_failure_floor(
        parse_failures, resolved.decision, resolved.reason
    )
    # overrides/sub_matches/additional_context/fallback_warning/matched_rule/
    # tool/target all fall back to RuntimeVerdict's own defaults -- this is a
    # rebuilt verdict, not a copy of resolved, and none of those fields
    # describe a rule match that still determines the outcome.
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

    *levels* carries each level's match already computed (the cascade is
    eager -- see :func:`resolve_permission_cascade`), so this only reads
    ``result.decision``; no matching happens here.
    """
    for result, layers in levels[winning_index + 1 :]:
        # We only care about a DENY at this less-specific level. Matching is
        # deny-first, so a deny here surfaces as decision == 'deny'.
        if result is not None and result.decision == DECISION_DENY:
            overridden_pattern = result.matched_pattern
            overridden_prov = provenance_for_pattern(
                layers, overridden_pattern, DECISION_DENY
            )
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
        has_any_rules: Whether the tool has ANY rule configured anywhere --
            see :meth:`~toolguard.config_types.ResolutionConfig.has_any_rules`.
        no_match_fallback: The effective ``no_match_fallback`` policy -- see
            :meth:`~toolguard.config_types.ResolutionConfig.resolved_no_match_fallback`.
        subject: The noun the no-match-fallback reason (below) opens with --
            ``"Command"`` for Bash, ``"Path"`` for a file-path tool.

    Returns the internal cascade verdict, with ``tool``/``target`` left
    ``None`` (this function is never handed a target string) and
    ``overrides`` holding at most one ``(None, ConflictOverride)`` pair (no
    sub_command/target identifier is known at this layer; see
    ``RuntimeVerdict``'s docstring for how the two ``resolve.py`` callers
    re-pair it with a real identifier). The no-match branch below sets
    ``fallback_cause='no_match'``; the genuine-match branch above leaves it
    ``None``.
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
        if decision == DECISION_ALLOW:
            override = _detect_override(levels, index, matched_pattern, prov)
        return RuntimeVerdict(
            decision=decision,
            reason=reason_with_prov,
            provenance=prov,
            overrides=[(None, override)] if override is not None else [],
            additional_context=additional_context,
            # Carry the matched pattern rather than making a caller parse it
            # back out of `reason_with_prov` -- it is already in hand here,
            # since both lookups above key off it.
            matched_rule=matched_pattern,
        )

    # No level matched anything for this command/path (TOO-15). Two distinct
    # cases share this no-match branch:
    #
    # - The tool has NO permission rules configured anywhere (no allow, deny,
    #   ask, or hard_deny at any level): the tool is entirely unconfigured, so
    #   this ALWAYS resolves to 'ask' -- regardless of no_match_fallback -- so
    #   a fresh install is never bricked by a blanket deny. A user who wants
    #   fail-closed-on-empty writes their own catch-all deny rule, which then
    #   flows through the normal matched-deny branch above.
    # - Rules ARE configured but simply did not match: governed by
    #   no_match_fallback -- 'ask' (the default), 'deny', 'allow_with_warning'
    #   (allow, with a warning reason instead of blocking), or 'allow' (allow
    #   with NO warning anywhere). The deprecated legacy value
    #   'warn_deny' is normalized to 'allow_with_warning', and the deliberate
    #   long-form synonym 'allow_with_no_warnings' is normalized to 'allow',
    #   both by resolved_no_match_fallback() before this branch ever sees them.
    if not has_any_rules:
        return RuntimeVerdict(
            decision=DECISION_ASK,
            reason=(
                f"No {tool_name} permission rules configured at any level; "
                f"defaulting to 'ask'"
            ),
            provenance=None,
            fallback_cause="no_match",
        )
    fallback = no_match_fallback
    if fallback == FALLBACK_ALLOW_WITH_WARNING:
        return RuntimeVerdict(
            decision=DECISION_ALLOW,
            reason=(
                f"{subject} does not match any allow patterns; allowed with a "
                f"warning by no_match_fallback={FALLBACK_ALLOW_WITH_WARNING} (add an "
                "explicit rule to silence this)"
            ),
            provenance=None,
            fallback_warning=True,
            fallback_cause="no_match",
        )
    if fallback == DECISION_ALLOW:
        return RuntimeVerdict(
            decision=DECISION_ALLOW,
            reason=(
                f"{subject} does not match any allow patterns; allowed with no "
                f"warning by no_match_fallback={DECISION_ALLOW} (add an explicit rule to "
                "silence this)"
            ),
            provenance=None,
            fallback_cause="no_match",
        )
    if fallback == DECISION_ASK:
        return RuntimeVerdict(
            decision=DECISION_ASK,
            reason=(
                f"{subject} does not match any allow patterns; awaiting a "
                f"decision (no_match_fallback={DECISION_ASK})"
            ),
            provenance=None,
            fallback_cause="no_match",
        )
    return RuntimeVerdict(
        decision=DECISION_DENY,
        reason=f"{subject} does not match any allow patterns",
        provenance=None,
        fallback_cause="no_match",
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
    Resolve a decision from already-computed per-level matches -- the pure fold.

    Provenance and allow-over-deny conflict detection, then the TOO-19
    parse-failure ASK floor. Only allow-over-deny overrides are conflicts
    here -- ``hard_deny`` denials are handled by the caller BEFORE any
    matching happens and never reach this function at all.

    Pure: no matching happens here, and nothing here is a callable or a
    ``config`` object -- every level's match was already computed by the
    caller (:func:`resolve_command_permission`/:func:`resolve_file_path_permission`
    in production; a hand-built list in a test). This is what lets the
    cascade -- more-specific-wins, override detection, the ASK floor -- be
    tested in isolation from real pattern matching.

    The ASK floor is applied here, at the cascade's own chokepoint, rather
    than in the Bash-specific compound pipeline (:mod:`toolguard.compound`),
    so it covers every governed tool uniformly -- both the live hook and the
    read-only ``--eval``/replay path (:mod:`toolguard.api`) reach it, via
    :func:`resolve_command_permission`/:func:`resolve_file_path_permission`.

    Args:
        levels: One entry per hierarchy level, most-specific first -- see
            :data:`LevelOutcome`.
        tool_name: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
        parse_failures: The configuration's REAL, complete ``parse_failures``
            -- see :func:`apply_parse_failure_floor`'s caller obligation.
        has_any_rules: See :meth:`~toolguard.config_types.ResolutionConfig.has_any_rules`.
        no_match_fallback: See :meth:`~toolguard.config_types.ResolutionConfig.resolved_no_match_fallback`.
        subject: Forwarded to :func:`_resolve_unclamped` -- see that
            parameter's own docstring. Defaults to ``"Command"``;
            :func:`resolve_file_path_permission` passes ``"Path"``.
    """
    resolved = _resolve_unclamped(
        levels, tool_name, has_any_rules, no_match_fallback, subject
    )
    return _apply_ask_floor(parse_failures, resolved)


def _effective_no_match_fallback(context: ResolutionContext) -> str:
    """
    Pick ``context.config``'s no-match fallback (TOO-28): the auto-mode variant when
    ``context.permission_mode`` is :data:`~toolguard.config_types.AUTO_PERMISSION_MODE`,
    the base setting otherwise. Shared by :func:`resolve_command_permission` and
    :func:`resolve_file_path_permission` so the two cannot pick this differently.
    """
    if context.permission_mode == AUTO_PERMISSION_MODE:
        return context.config.resolved_no_match_fallback_in_auto_mode()
    return context.config.resolved_no_match_fallback()


def resolve_command_permission(
    context: ResolutionContext,
    command: str,
    *,
    spellings: CommandSpellings = CommandSpellings(),
) -> RuntimeVerdict:
    """
    Resolve one (already-decomposed) command against ``context.tool_name``'s cascade.

    Matches *command* against every hierarchy level eagerly, via
    :func:`~toolguard.permissions.decide_command_at_level_detailed`, then
    folds the results with :func:`resolve_permission_cascade`. The
    production entry point for Bash/MCP-terminal resolution.

    Args:
        context: Supplies ``tool_name``, ``config``, and ``extended_syntax`` --
            see :class:`~toolguard.config_types.ResolutionContext`.
        command: The already-decomposed command string to resolve.
        spellings: Built by the caller: this module does not import the parser, an
            import ``test/unit/test_architecture.py``'s per-module allow-list rejects.
            Omitting it matches *command* as spelled, which is what a caller with no
            leaf in hand should do.
    """
    levels = context.config.permission_levels_with_provenance(context.tool_name)
    matched_levels: List[LevelOutcome] = [
        (
            decide_command_at_level_detailed(
                command,
                list(allow),
                list(deny),
                context.extended_syntax,
                ask_patterns=list(ask),
                spellings=spellings,
            ),
            layers,
        )
        for allow, deny, ask, layers in levels
    ]
    return resolve_permission_cascade(
        matched_levels,
        context.tool_name,
        context.config.parse_failures,
        context.config.has_any_rules(context.tool_name),
        _effective_no_match_fallback(context),
    )


def resolve_file_path_permission(
    context: FilePathResolutionContext,
    file_path: str,
) -> RuntimeVerdict:
    """
    Resolve one file path against ``context.tool_name``'s cascade.

    Matches *file_path* against every hierarchy level eagerly, via
    :func:`~toolguard.file_matching.decide_file_path_at_level_detailed`
    (which needs ``config`` for project-root anchoring -- see
    :class:`~toolguard.config_types.FilePathResolutionConfig`), then folds
    the results with :func:`resolve_permission_cascade`. The production
    entry point for Read/Write/Edit resolution -- see
    :mod:`toolguard.resolve`'s file-path resolver, called AFTER the
    unoverridable ``[hard_deny]`` pool check.

    Args:
        context: Supplies ``tool_name``, ``config``, and ``extended_syntax`` --
            see :class:`~toolguard.config_types.FilePathResolutionContext`.
        file_path: The file path under evaluation.
    """
    levels = context.config.permission_levels_with_provenance(context.tool_name)
    matched_levels: List[LevelOutcome] = [
        (
            decide_file_path_at_level_detailed(
                file_path,
                list(allow),
                list(deny),
                context.config,
                context.extended_syntax,
                ask_patterns=list(ask),
            ),
            layers,
        )
        for allow, deny, ask, layers in levels
    ]
    return resolve_permission_cascade(
        matched_levels,
        context.tool_name,
        context.config.parse_failures,
        context.config.has_any_rules(context.tool_name),
        _effective_no_match_fallback(context),
        subject="Path",
    )
