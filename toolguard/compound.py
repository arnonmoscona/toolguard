"""
Compound command permission checking for toolguard.

This module provides permission checking for compound bash commands,
validating each sub-command and returning the strictest permission decision.

TOO-17: resolve_compound_permission now uses the multi-line pre-processor
(:mod:`toolguard.parser.multiline`) to correctly handle multi-line commands,
heredocs, inline code, and control structures.  The governing principle is
**"when in doubt, ASK"**: any segment that cannot be safely decomposed
resolves to ASK rather than a silent allow of an undecomposed blob.

Shape (TOO-45 compound/resolve cycle removal)
-----------------------------------------------
Three pure functions, no callbacks: :func:`decompose` splits a command line
into :class:`CommandUnit`\\ s (structure only -- decides nothing);
:func:`judge_unit` decides ONE unit given what a caller's own resolver said
about its ``parts`` (owns the ASK floor); :func:`_combine_strictest` combines
several already-judged units into the compound's own verdict. This module
never calls back into :mod:`toolguard.resolve` -- the production caller
(:func:`~toolguard.resolve.resolve_bash_permission_detailed`) drives these
three functions directly and builds ``sub_matches``/``overrides`` itself, by
ordinary ``append``/``extend`` on visible lines. :func:`resolve_compound_permission_detailed`
below is a convenience driver over the same three functions for callers with
only a plain ``resolve_one`` closure (~40 tests, and
:func:`check_compound_permission`) -- not part of the production path.
"""

import logging
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Tuple, Union

from toolguard.config_types import RuntimeVerdict, UnitVerdict
from toolguard.parser.command_extractor import (
    INLINE_FLAG_TOKEN_RE as _INLINE_FLAG_TOKEN_RE,
)
from toolguard.parser.command_extractor import extract_commands
from toolguard.parser.multiline import (
    LeafCommand,
    UndecidableSegment,
    extract_structured,
)
from toolguard.permissions import check_permission

logger = logging.getLogger(__name__)


#: Maximum length (in characters) of the command portion shown in the
#: ASK-floor reason string rendered to the user's permission prompt
#: (see :func:`_truncate_for_display` and ``compound.py`` line ~71).
_MAX_DISPLAY_COMMAND_LEN = 120

#: Word budget for the accumulated ``additionalContext`` text injected back to
#: Claude for an all-allow compound command (TOO-19 Phase 1). Enrichment is a
#: nudge, not a document: past this budget it costs more context than it earns.
_MAX_CONTEXT_WORDS = 500

# TOO-19: the bundled/attached inline-code flag regex now lives in
# toolguard.parser.command_extractor (imported above as _INLINE_FLAG_TOKEN_RE)
# so this module's outer-command extraction and command_extractor's
# ask_floor detection cannot drift apart. See that module for the full
# docstring on the pattern.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


#: Strictness ranking used by the ``undecidable_fallback`` floor below --
#: deny > ask > allow. Deliberately a SEPARATE table from
#: ``_combine_strictest``'s own deny/ask/allow ordering rather than a shared
#: constant: that function combines several ALREADY-DECIDED sub-command
#: results (with its own reason-building and context-accumulation rules for
#: ties), while the floor here clamps a SINGLE decision (or, for an
#: ``UndecidableSegment``, supplies one outright) against a configured
#: minimum. Coupling the two would tie an unrelated concern (combining
#: multiple leaves) to this one (flooring an undecidable result) for a
#: two-line lookup table; see the TOO-19 implementation report for the full
#: reuse-vs-coupling reasoning.
_DECISION_STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}

#: Maps each recognized ``undecidable_fallback`` value to the decision it
#: floors an undecidable result to. ``'allow_with_warning'`` AND ``'allow'``
#: (TOO-19 allow/allow_with_no_warnings work) both float to ``'allow'`` -- i.e.
#: NO floor at all, the deliberate TOO-19 escape hatch: the floor can only
#: ever make a verdict STRICTER than allow, never weaken an explicit deny or
#: ask. The two values are the SAME strictness level; only whether a warning
#: is logged differs, and that distinction is decided by the callers below
#: (:func:`_resolve_leaf`, :func:`resolve_compound_permission`), not by this
#: table -- ``'allow_with_no_warnings'`` never reaches this table at all
#: (normalized to ``'allow'`` by
#: :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`
#: before compound.py ever sees it).
_UNDECIDABLE_FLOOR_DECISION = {
    "ask": "ask",
    "deny": "deny",
    "allow_with_warning": "allow",
    "allow": "allow",
}


def _apply_undecidable_floor(decision: str, undecidable_fallback: str) -> str:
    """Clamp *decision* to at least as strict as *undecidable_fallback* names (TOO-19).

    ``undecidable_fallback`` names a FLOOR LEVEL, resolved STRICTEST-WINS
    against whatever the leaf/segment itself resolved to. Strictness order:
    ``deny > ask > allow``, so the floor can only ever make the verdict
    STRICTER than ``allow`` -- it never weakens an explicit ``deny`` or
    ``ask``:

    ================  ===========  ============  =======================  ===========
    *decision*         ``ask``      ``deny``      ``allow_with_warning``   ``allow``
    ================  ===========  ============  =======================  ===========
    ``deny``           deny         deny          deny                     deny
    ``ask``            ask          deny          ask                      ask
    ``allow``          ask          deny          allow                    allow
    ================  ===========  ============  =======================  ===========

    ``allow_with_warning`` and ``allow`` (TOO-19) behave IDENTICALLY for
    floor purposes -- same column above -- because they are the same
    strictness level; only whether the eventual allow is logged with a
    warning differs, and that is decided by *reason*-text branching in the
    two callers, not by this floor.

    An unrecognized *undecidable_fallback* value is treated as ``'ask'``
    (the default), matching :meth:`toolguard.config.Configuration.resolved_undecidable_fallback`'s
    own fallback-to-default normalization -- this function never sees a raw,
    unvalidated value in practice, but stays defensive rather than raising.

    Args:
        decision: The decision to floor -- one of ``'allow'``, ``'ask'``, or
            ``'deny'``.
        undecidable_fallback: The configured floor -- one of ``'ask'``,
            ``'deny'``, ``'allow_with_warning'``, or ``'allow'``.

    Returns:
        The floored decision -- one of ``'allow'``, ``'ask'``, or ``'deny'``.
    """
    floor_decision = _UNDECIDABLE_FLOOR_DECISION.get(undecidable_fallback, "ask")
    if _DECISION_STRICTNESS[floor_decision] > _DECISION_STRICTNESS[decision]:
        return floor_decision
    return decision


#: Stand-in recorded wherever a per-sub-command "matched rule" would normally
#: go but the ``allow`` came from a fallback ESCAPE HATCH rather than a rule
#: match (TOO-19 code review M1/m5). Shared by :func:`_combine_strictest`'s
#: multi-leaf summary and by ``hook.py``'s single-leaf audit-log branch so the
#: two cannot drift into two different conventions for the same situation.
#:
#: Deliberately comma-free: ``hook.py``'s ``_parse_compound_match_details``
#: splits the bracketed summary list on ``", "``, so a comma here would be
#: mis-split into two bogus per-sub-command entries.
FALLBACK_ALLOW_PLACEHOLDER = "[fallback allow -- no rule matched]"

#: The ``deny``-side counterpart of :data:`FALLBACK_ALLOW_PLACEHOLDER` (TOO-19
#: deny-side rule fabrication fix). Recorded as the ``Violated Rules`` entry
#: wherever a deny came from the ``undecidable_fallback=deny`` escape hatch
#: rather than a matched deny rule -- see ``hook.py``'s
#: ``_log_non_allow_decision``. Comma-free for the same reason as the allow
#: placeholder, even though nothing currently re-splits a deny reason on
#: ``", "``: keeping the two placeholders to the same shape is cheaper than
#: reasoning about whether that stays true.
FALLBACK_DENY_PLACEHOLDER = "[fallback deny -- no rule matched]"

#: Reason-text markers that identify a fallback-escape-hatch outcome, each
#: mapped to the ``fallback_kind`` tag it implies AND the single *decision* it
#: is valid evidence for -- ``fallback_kind_for_reason`` only matches a marker
#: against reasons carrying that same decision, so an accidental substring
#: collision in a hand-written ``additionalContext`` or pattern name can only
#: ever misclassify within its own decision, never cross an allow reason into
#: a deny finding or vice versa. Ordered LONGEST-MARKER-FIRST WITHIN a decision
#: because ``...=allow_with_warning`` has ``...=allow`` as a prefix -- a
#: shorter marker must never shadow the longer one; the ``deny`` marker has no
#: such prefix collision, so its position relative to the ``allow`` ones does
#: not matter. The ``allow``-side settings: the ``no_match_fallback`` wording
#: is built by :func:`~toolguard.permission_resolution.resolve_permission_cascade`
#: and reaches this module through ``resolve_one``; the ``undecidable_fallback``
#: wording is built by this module itself and reaches ``hook.py`` as the FINAL
#: reason of a single-leaf command (TOO-19 m5). The ``deny``-side marker
#: (TOO-19 deny-side rule fabrication fix) covers BOTH deny reason shapes this
#: module builds for ``undecidable_fallback=deny`` -- the ASK-floor leaf's
#: ``"Denied by undecidable_fallback=deny (...): <display>"`` and the
#: ``UndecidableSegment``'s ``"Undecidable segment denied by
#: undecidable_fallback=deny (...): <display>"`` -- with a single substring,
#: since both contain it verbatim. There is no ``no_match_fallback=deny``
#: marker: that reason (``"Command does not match any allow patterns"``,
#: built by ``permission_resolution.py``) never contains a ``": "`` at all,
#: so it was never at risk of the fabrication this guards against.
_FALLBACK_REASON_MARKERS = (
    ("no_match_fallback=allow_with_warning", "warned", "allow"),
    ("undecidable_fallback=allow_with_warning", "warned", "allow"),
    ("no_match_fallback=allow", "silent", "allow"),
    ("undecidable_fallback=allow", "silent", "allow"),
    ("undecidable_fallback=deny", "denied", "deny"),
)


def fallback_kind_for_reason(decision: str, reason: str) -> Optional[str]:
    """Classify an ``allow`` or ``deny`` result as a fallback-escape-hatch outcome or not.

    TOO-19 code review M1: structured detection where the caller can determine
    the outcome directly from what it just constructed (the ASK-floor and
    ``UndecidableSegment`` branches below), and this TEXT-based fallback ONLY
    for the places that genuinely cannot be structural:

    - an ordinary (non-ASK-floor) sub-command's ``resolve_one`` result. That
      callable's return type is a plain 3-tuple relied on by ~18 test-authored
      closures (see the TOO-19 implementation report), so the richer
      ``RuntimeVerdict.fallback_warning`` bit computed inside
      :func:`~toolguard.permission_resolution.resolve_permission_cascade` never
      reaches this module -- only its already-tested, verbatim reason wording
      does. Only ``no_match_fallback`` markers can appear on that path.
    - ``hook.py``'s audit-log branch for a SINGLE-leaf command (TOO-19 m5 for
      ``allow``; TOO-19 deny-side rule fabrication fix for ``deny``), which
      sees only the final reason string. There the ``undecidable_fallback``
      markers this module itself writes are the ones that matter, which is
      why this helper recognizes both fallback settings and is public rather
      than module-private.

    ``deny`` was folded into this SAME function rather than given a parallel
    ``fallback_kind_for_deny_reason`` (TOO-19 deny-side rule fabrication fix):
    the marker table, the longest-marker-first ordering concern, and the
    "classify this reason string" contract are all identical between the two
    decisions, and the alternative (a second function checking a second
    marker tuple) is exactly the kind of drift risk that made this function
    public in the first place. Each marker in ``_FALLBACK_REASON_MARKERS`` is
    tagged with the one decision it is valid evidence for, and only matched
    against a reason carrying that same decision, so folding ``deny`` into
    the same table cannot let an allow marker misclassify a deny (or vice
    versa) even in the (currently unreachable) case of a substring collision.

    Args:
        decision: The decision the *reason* accompanies.
        reason: The reason text.

    Returns:
        ``'warned'`` when *reason* names the ``allow_with_warning`` value of
        either allow-side fallback setting, ``'silent'`` when it names the
        plain ``allow`` value of either, ``'denied'`` when *decision* is
        ``'deny'`` and *reason* names ``undecidable_fallback=deny``, or
        ``None`` for a decision other than ``'allow'``/``'deny'`` or a
        genuine rule match.
    """
    if decision not in ("allow", "deny"):
        return None
    for marker, kind, applies_to in _FALLBACK_REASON_MARKERS:
        if applies_to == decision and marker in reason:
            return kind
    return None


@dataclass(frozen=True)
class CommandUnit:
    """One decidable element of a compound command line, in extraction order.

    Produced by :func:`decompose`. Carries the element's own text plus the
    command strings a rule engine must decide on its behalf, so a caller
    (:mod:`toolguard.resolve`) can resolve them itself instead of ``compound``
    calling back into that caller (TOO-45 compound/resolve cycle removal --
    this type is the entire content of what the old ``resolve_one``/
    ``resolve_outer``/``record_unit`` callback trio smuggled across the
    module boundary as control flow instead of as data).

    Attributes:
        text: The unit's real, full source text. Becomes
            ``UnitVerdict.sub_command`` for whatever verdict this unit ends
            up with, regardless of *kind* -- NEVER the truncated
            ``'inline_code'`` stub in *parts*.
        kind: One of ``'plain'`` (an ordinary leaf, further PEG-split into
            zero or more sub-commands), ``'inline_code'`` (an ASK-floor leaf
            -- foreign inline code / heredoc sink), ``'undecidable'`` (a
            grammar-level
            :class:`~toolguard.parser.command_extractor.UndecidableSegment`),
            or ``'unknown'`` (the defensive, currently-unreachable fallback
            for an extraction result of neither type -- see
            :func:`~toolguard.parser.multiline.extract_structured`, which
            only ever returns the first two).
        parts: Command strings a rule engine must decide on this unit's
            behalf, in order. ``'plain'`` -> the PEG sub-commands of *text*
            (0, 1, or many, via :func:`~toolguard.parser.command_extractor.extract_commands`);
            ``'inline_code'`` -> exactly one element, the UNTRUNCATED
            outer-command stub (see :func:`_extract_outer_command` -- this
            function deliberately does not length-truncate; truncating here
            would risk weakening explicit-deny detection); ``'undecidable'``/
            ``'unknown'`` -> empty, since there is nothing to resolve against
            a rule.
        audits_as_one: Whether this unit contributes exactly ONE audit-log
            entry (``True`` for ``'inline_code'``/``'undecidable'`` -- a
            FLOOR decided, not any part's own rule match, so the unit's OWN
            final verdict is the only honest audit entry) or whether its
            audit entries ARE its own parts' verdicts (``False`` for
            ``'plain'``/``'unknown'`` -- a zero-part unit of either kind then
            records nothing). Set HERE, by :func:`decompose`, rather than
            re-derived by a caller switching on *kind* (TOO-45 compound-cycle
            judgment R1): a caller (:mod:`toolguard.resolve`) that recorded
            via ``if unit.kind == 'plain'`` would relocate the exact defect
            class TOO-45 R1e was created to fix (an audit entry's very
            EXISTENCE silently depending on a code path in a module other
            than the one that owns the concept) into a different module from
            where kinds are defined -- a fifth kind added to ``decompose``
            without deciding this field would then silently mis-audit,
            green suite and all. Reading this field instead makes that
            impossible: a new kind cannot be added without deciding it.
        note: :attr:`~toolguard.parser.command_extractor.UndecidableSegment.reason`
            for an ``'undecidable'`` unit, else ``None``.
    """

    text: str
    kind: str
    parts: Tuple[str, ...]
    audits_as_one: bool
    note: Optional[str] = None


def _unit_for(element: Union[LeafCommand, UndecidableSegment]) -> CommandUnit:
    """Map one :func:`~toolguard.parser.multiline.extract_structured` element to a :class:`CommandUnit`.

    The ONE place ``LeafCommand.ask_floor`` is read to decide a unit's
    ``kind`` (TOO-45 risk R1 in the execution plan: mis-mapping an
    ask-floor leaf to ``'plain'`` would let its content bypass the ASK
    floor entirely and be resolved -- and potentially allowed -- as
    ordinary PEG-split sub-commands).

    Args:
        element: A :class:`~toolguard.parser.command_extractor.LeafCommand`
            or :class:`~toolguard.parser.command_extractor.UndecidableSegment`,
            as produced by :func:`~toolguard.parser.multiline.extract_structured`.

    Returns:
        The corresponding :class:`CommandUnit`.
    """
    if isinstance(element, UndecidableSegment):
        return CommandUnit(
            text=element.original,
            kind="undecidable",
            parts=(),
            audits_as_one=True,
            note=element.reason,
        )
    if isinstance(element, LeafCommand):
        if element.ask_floor:
            outer_cmd = _extract_outer_command(element.text)
            return CommandUnit(
                text=element.text,
                kind="inline_code",
                parts=(outer_cmd,),
                audits_as_one=True,
            )
        sub_commands = extract_commands(element.text)
        return CommandUnit(
            text=element.text,
            kind="plain",
            parts=tuple(sub_commands),
            audits_as_one=False,
        )
    # Should not happen -- extract_structured only ever returns the two
    # types above. Logged here, where the actual unexpected type is still
    # known; the driver only ever sees the resulting 'unknown'-kind unit.
    logger.warning("Unknown extraction result type: %r", type(element))
    return CommandUnit(text="", kind="unknown", parts=(), audits_as_one=False)


def decompose(command: str) -> List[CommandUnit]:
    """Split a command line into decidable units. Pure structure -- decides nothing.

    The public entry point for turning a (possibly compound, possibly
    multi-line) Bash command line into the ordered list of
    :class:`CommandUnit`\\ s a caller must resolve and judge. Delegates
    entirely to :func:`~toolguard.parser.multiline.extract_structured` for
    the actual grammar-level splitting; this function's only job is mapping
    each resulting element to a :class:`CommandUnit` via :func:`_unit_for`.

    Args:
        command: The bash command line (may be compound or multi-line).

    Returns:
        The ordered list of :class:`CommandUnit`\\ s, one per
        ``extract_structured`` element. Empty when *command* contains no
        valid commands at all.
    """
    return [_unit_for(element) for element in extract_structured(command)]


def _unit_from_tuple(
    sub_command: str, resolved: Tuple[str, str, Optional[str]]
) -> UnitVerdict:
    """Adapt a ``resolve_one``-shaped 3-tuple result into a :class:`UnitVerdict`.

    TOO-45 step 3/R5: the ``resolve_one`` contract (a plain 3-tuple, relied on
    by ~18 test-authored closures and therefore frozen) carries no
    ``matched_rule``/``provenance`` -- so this adapter's ``fallback_kind`` is
    computed by the TEXT-based :func:`fallback_kind_for_reason`, the one
    place that heuristic genuinely still earns its keep (see that function's
    own docstring). Used by :func:`resolve_compound_permission_detailed` to
    build ``part_verdicts`` for :func:`judge_unit`, for every part of every
    unit kind -- including an ``'inline_code'`` unit's single outer-command
    stub, which this driver has no way to resolve more precisely than
    *resolve_one* allows for (unlike :mod:`toolguard.resolve`'s own
    production driver, which builds real :class:`UnitVerdict`\\ s directly).

    Args:
        sub_command: The command string that was resolved.
        resolved: ``resolve_one``'s own ``(decision, reason,
            additional_context)`` result for it.

    Returns:
        The corresponding :class:`UnitVerdict`, with ``matched_rule``/
        ``provenance`` both ``None`` (unknowable from a bare 3-tuple).
    """
    decision, reason, additional_context = resolved
    return UnitVerdict(
        sub_command=sub_command,
        decision=decision,
        matched_rule=None,
        provenance=None,
        reason=reason,
        additional_context=additional_context,
        fallback_kind=fallback_kind_for_reason(decision, reason),
    )


def judge_unit(
    unit: "CommandUnit",
    part_verdicts: List[UnitVerdict],
    undecidable_fallback: str = "ask",
) -> UnitVerdict:
    """Verdict for ONE :class:`CommandUnit`, given what the rules said about its parts.

    TOO-45 compound/resolve cycle removal, step 3: this function IS the old
    ``_resolve_leaf_detailed`` plus the ``UndecidableSegment`` branch that
    used to live inline in :func:`resolve_compound_permission_detailed` --
    moved here, unified under one name, with every injected callback
    (``resolve_one``/``resolve_outer``/``record_unit``) replaced by data the
    CALLER already resolved and hands in via *part_verdicts*. This function
    decides; it never calls back into anything, and it never records
    anything -- the caller (:func:`resolve_compound_permission_detailed`, or
    :mod:`toolguard.resolve`'s own driver) does both.

    Pure function of ``(unit, part_verdicts, undecidable_fallback)``: same
    inputs, same output, every time -- this is what makes the ASK floor
    testable with literals (TOO-45 compound-cycle judgment section 5) instead
    of requiring a fake resolver closure the way the pre-refactor code did.

    The floor branches below (the ``'inline_code'`` dispatch) are relocated
    VERBATIM from ``_resolve_leaf_detailed`` -- same values, same wording,
    same order, only ``probe(outer_cmd)``'s five return values replaced by
    ``part_verdicts[0]``'s five attributes (TOO-45 compound-cycle judgment
    R3: this is the one branch in the codebase where a silent inversion
    during a refactor would be a security hole, so it is not tidied into a
    table here even though the five constructions are visibly near-duplicate).

    Args:
        unit: The :class:`CommandUnit` to judge (see :func:`decompose`).
        part_verdicts: The caller's own resolution of each string in
            ``unit.parts``, IN THAT ORDER and the SAME LENGTH -- for
            ``'plain'``, one :class:`UnitVerdict` per PEG sub-command; for
            ``'inline_code'``, exactly one, the outer-command stub's
            resolution; empty for ``'undecidable'``/``'unknown'``.
        undecidable_fallback: The configured floor (TOO-19) -- one of
            ``'ask'`` (default), ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'`` -- sourced from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.

    Returns:
        A :class:`UnitVerdict` for *unit*, with ``sub_command`` always set to
        ``unit.text`` (the unit's real, full source text -- NEVER the
        truncated ``'inline_code'`` stub).

    Raises:
        ValueError: If ``len(part_verdicts) != len(unit.parts)`` (TOO-45
            compound-cycle judgment R5 -- a loud, immediate failure rather
            than a silent misattribution: this positional invariant cannot
            be violated by construction in the old callback-driven code,
            since the callback resolved and consumed in the same
            expression, so it is a genuinely NEW class of bug this refactor
            introduces and must guard against explicitly), or if
            ``unit.kind`` is not one of ``'plain'``, ``'inline_code'``,
            ``'undecidable'``, or ``'unknown'`` (R5: a fifth kind must be
            decided here, not silently fall through to a default).
    """
    if len(part_verdicts) != len(unit.parts):
        raise ValueError(
            f"judge_unit: part_verdicts has {len(part_verdicts)} entries but "
            f"unit.parts has {len(unit.parts)} for unit.text={unit.text!r} "
            f"(kind={unit.kind!r}) -- part_verdicts must be the caller's own "
            "resolution of unit.parts, in the same order and length."
        )

    if unit.kind == "undecidable":
        # No rule matched, so there is no underlying decision to floor.
        # Modelling that as 'allow' makes this the same operation as every
        # other floor application: the floor is never weaker than 'allow',
        # so clamping 'allow' yields the fallback itself for every value.
        # TOO-45 D4 -- previously a direct table lookup here, which meant
        # the floor had two implementations and mutating either one alone
        # changed nothing.
        floored = _apply_undecidable_floor("allow", undecidable_fallback)
        logger.debug(
            "Undecidable segment (-> %s): %r reason=%s",
            floored,
            unit.text[:80],
            unit.note,
        )
        display = unit.text[:80]
        fallback_kind = None
        if floored == "ask":
            # Default case: wording preserved verbatim from before
            # TOO-19 so existing tests/log parsing do not churn.
            reason = f"Undecidable segment ({unit.note}): {display}"
        elif floored == "deny":
            reason = (
                f"Undecidable segment denied by undecidable_fallback=deny "
                f"({unit.note}): {display}"
            )
        elif undecidable_fallback == "allow_with_warning":
            # The deliberate no-floor escape hatch, WITH a warning.
            # fallback_kind is known STRUCTURALLY here -- no text
            # matching needed (TOO-19 code review M1).
            reason = (
                "Undecidable segment allowed with a warning by "
                f"undecidable_fallback=allow_with_warning ({unit.note}): "
                f"{display}"
            )
            fallback_kind = "warned"
        else:
            # undecidable_fallback == "allow" (TOO-19): same no-floor
            # escape hatch, but no warning -- say so plainly rather than
            # letting the 'allow_with_warning' wording above cover both.
            reason = (
                "Undecidable segment allowed with no warning by "
                f"undecidable_fallback=allow ({unit.note}): {display}"
            )
            fallback_kind = "silent"
        unit_fallback_kind = "denied" if floored == "deny" else fallback_kind
        return UnitVerdict(
            sub_command=unit.text,
            decision=floored,
            matched_rule=None,
            provenance=None,
            reason=reason,
            additional_context=None,
            fallback_kind=unit_fallback_kind,
        )

    if unit.kind == "inline_code":
        # For ASK-floor leaves (foreign inline code, foreign heredoc sinks),
        # we need to check for explicit denies but floor allow/ask per
        # undecidable_fallback. The leaf text may contain embedded newlines
        # (multiline -c arg) that would confuse the PEG grammar and the
        # newline guard -- unit.parts[0] is the outer command stub ONLY
        # (without the inline payload), computed by decompose() for exactly
        # this reason.
        outer_cmd = unit.parts[0]
        stub = part_verdicts[0]
        decision, reason, additional_context, matched_rule, provenance = (
            stub.decision,
            stub.reason,
            stub.additional_context,
            stub.matched_rule,
            stub.provenance,
        )
        if decision == "deny":
            # The stub's own deny IS the deciding match -- a real rule fired,
            # so its matched_rule/provenance are genuine attributions, not an
            # escape hatch (TOO-45 R1e). Only the recorded sub_command text
            # needs correcting, from the stub to the leaf's real, full text.
            return UnitVerdict(
                sub_command=unit.text,
                decision="deny",
                matched_rule=matched_rule,
                provenance=provenance,
                reason=reason,
                additional_context=additional_context,
                fallback_kind=None,
            )
        # allow or ask -> floor per undecidable_fallback.  Bound the command
        # shown in the reason so an unbounded inline-code blob never reaches
        # the permission prompt (the matching above still used the
        # untruncated outer_cmd, so this cannot weaken deny detection). The
        # floor, not the rule match, now decides -- its context is dropped.
        display_cmd = _truncate_for_display(outer_cmd)
        floored = _apply_undecidable_floor(decision, undecidable_fallback)
        if floored == "ask":
            if decision == "ask":
                # TOO-19 code review m1: the floor made NO change -- an
                # explicit ask rule already decided 'ask' on its own before
                # the floor was even consulted. Preserve the rule's own
                # reason and context rather than overwriting them with floor
                # language that misattributes the verdict's real cause. The
                # rule genuinely decided, so matched_rule/provenance are
                # genuine attributions here too (TOO-45 R1e) -- only the
                # sub_command text needs correcting.
                return UnitVerdict(
                    sub_command=unit.text,
                    decision="ask",
                    matched_rule=matched_rule,
                    provenance=provenance,
                    reason=reason,
                    additional_context=additional_context,
                    fallback_kind=None,
                )
            # Genuine floor case: undecidable_fallback raised 'allow' to
            # 'ask'. Wording preserved verbatim from before TOO-19 so
            # existing tests/log parsing do not churn. The floor, not
            # whatever the stub matched, decided -- matched_rule/provenance
            # must NOT carry the stub's match (TOO-45 R1e).
            return UnitVerdict(
                sub_command=unit.text,
                decision="ask",
                matched_rule=None,
                provenance=None,
                reason=f"ASK floor applied (inline/heredoc foreign code): {display_cmd}",
                additional_context=None,
                fallback_kind=None,
            )
        if floored == "deny":
            # TOO-45 R1e finishing pass: fallback_kind='denied' here (unlike
            # the plain None the LeafOutcome-typed return used before this
            # merge, even though record_unit's own value was already
            # 'denied') -- safe because the OUTER combine (_combine_strictest)
            # discards
            # fallback_kind entirely for any non-allow decision (see its
            # `denied = [uv for uv in unit_verdicts if uv.decision == "deny"]`
            # filtering above); a real, attributable tag is strictly more
            # informative for the audit record with no behavioural change to
            # the compound reason.
            return UnitVerdict(
                sub_command=unit.text,
                decision="deny",
                matched_rule=None,
                provenance=None,
                reason=(
                    "Denied by undecidable_fallback=deny (inline/heredoc "
                    f"foreign code, unable to safely verify): {display_cmd}"
                ),
                additional_context=None,
                fallback_kind="denied",
            )
        # floored == "allow": undecidable_fallback is either 'allow_with_warning'
        # or 'allow' (TOO-19) -- both are the deliberate no-floor escape hatch,
        # differing only in whether a warning is logged. Branch on the ACTUAL
        # configured value (not just "floored == allow", which both share) so
        # 'allow' never claims a warning was emitted. fallback_kind is known
        # STRUCTURALLY here -- no text matching needed (TOO-19 code review M1).
        if undecidable_fallback == "allow_with_warning":
            return UnitVerdict(
                sub_command=unit.text,
                decision="allow",
                matched_rule=None,
                provenance=None,
                reason=(
                    "Allowed with a warning by undecidable_fallback=allow_with_warning "
                    f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}"
                ),
                additional_context=None,
                fallback_kind="warned",
            )
        return UnitVerdict(
            sub_command=unit.text,
            decision="allow",
            matched_rule=None,
            provenance=None,
            reason=(
                "Allowed with no warning by undecidable_fallback=allow "
                f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}"
            ),
            additional_context=None,
            fallback_kind="silent",
        )

    if unit.kind == "plain":
        if not part_verdicts:
            # Empty leaf -- treat as no-op; should not normally happen. Not
            # an audit-log entry of its own (unchanged from before the
            # LeafOutcome/UnitVerdict merge): this is a defensive edge case,
            # not a real sub-command that ran.
            logger.debug("Empty leaf command after grammar extraction: %r", unit.text)
            return UnitVerdict(
                sub_command=unit.text,
                decision="deny",
                matched_rule=None,
                provenance=None,
                reason="No valid commands found in leaf",
                additional_context=None,
                fallback_kind=None,
            )

        # Reformat each part's OWN reason for the leaf's aggregate wording --
        # this is purely for _combine_strictest's inner call below, building
        # THIS unit's own combined reason; it never touches part_verdicts
        # itself, which the caller separately uses for sub_matches (TOO-45
        # step 1: For deny/ask, pre-format the reason with the sub-command
        # context so _combine_strictest can pass the formatted message
        # through unchanged; for allow, pass the raw reason through so
        # _combine_strictest can build the "cmd -> pattern" summary for the
        # all-allowed case.
        inner_units: List[UnitVerdict] = []
        for part_verdict in part_verdicts:
            if part_verdict.decision == "deny":
                formatted = (
                    "Compound command contains denied sub-command: "
                    f"{part_verdict.sub_command} ({part_verdict.reason})"
                )
            elif part_verdict.decision == "ask":
                formatted = (
                    "Compound command contains sub-command requiring approval:"
                    f" {part_verdict.sub_command} ({part_verdict.reason})"
                )
            else:
                # allow: pass raw reason through for "cmd -> pattern" formatting
                formatted = part_verdict.reason
            inner_units.append(replace(part_verdict, reason=formatted))

        # Route through the ONE strictest-wins combinator. Its own aggregate
        # fallback_warning bool is collapsed back to the tri-state
        # 'warned'/None here -- an inner multi-sub-command leaf's OWN reason
        # text (either the single-allowed pass-through or the "All N
        # sub-commands allowed: [...]" summary) never has the trailing-colon
        # shape that risks fabrication (see _combine_strictest), so the
        # outer combine needs only to know whether to count this leaf toward
        # the WARNING stream, not to re-gate fabrication for it.
        combined = _combine_strictest(inner_units)
        # No single decider to attribute across potentially several inner
        # sub-commands (mirrors resolve.py's _deciding_sub_match for the same
        # reason) -- matched_rule/provenance stay None. This aggregate value
        # is never itself an audit-log entry (unit.audits_as_one is False for
        # 'plain' -- the caller records part_verdicts directly instead).
        return UnitVerdict(
            sub_command=unit.text,
            decision=combined.decision,
            matched_rule=None,
            provenance=None,
            reason=combined.reason,
            additional_context=combined.additional_context,
            fallback_kind=("warned" if combined.fallback_warning else None),
        )

    if unit.kind == "unknown":
        # Should not happen -- extract_structured only ever returns the two
        # types _unit_for maps to 'plain'/'inline_code'/'undecidable'; the
        # unexpected type itself was already logged there, where it was
        # still known. Preserved as its own explicit branch (not deleted)
        # for the same defensive reason the original code kept it.
        return UnitVerdict(
            sub_command=unit.text,
            decision="ask",
            matched_rule=None,
            provenance=None,
            reason="Unknown extraction result; cannot verify",
            additional_context=None,
            fallback_kind=None,
        )

    # A fifth kind reaching here was never decided (TOO-45 compound-cycle
    # judgment R5) -- raise rather than silently falling through to a
    # default that might mis-audit or mis-floor it.
    raise ValueError(f"judge_unit: unrecognized CommandUnit.kind {unit.kind!r}")


def _resolve_leaf(
    leaf: LeafCommand,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a single leaf command -- thin wrapper dropping the structured detail.

    TOO-45 step 3: drives :func:`_unit_for` + :func:`judge_unit` directly
    (no more ``_resolve_leaf_detailed``, deleted -- its body is now
    ``judge_unit``). Kept as a separate, unchanged-PARAMETER-signature
    function because it is called directly (not just transitively) by many
    existing tests. *resolve_one* is used for EVERY part regardless of
    *leaf*'s kind (this function has no ``resolve_outer`` concept -- see
    :func:`_unit_from_tuple`), matching its pre-refactor behaviour exactly:
    the old ``probe = resolve_outer or (lambda cmd: (*resolve_one(cmd), None,
    None))`` fallback always took the ``resolve_one``-wrapping branch here,
    since this function never received a ``resolve_outer``.

    TOO-45 R1e: returns a :class:`~toolguard.config_types.RuntimeVerdict`
    instead of a bare ``(decision, reason, additional_context)`` 3-tuple --
    reused rather than a new type since this genuinely IS "the runtime
    verdict for this one leaf" (``matched_rule``/``provenance``/etc. simply
    stay at their defaults, the same pattern
    :func:`~toolguard.permission_resolution._apply_ask_floor` already uses
    for a comparable partial construction). Callers unpacking this as a
    3-tuple must move to attribute access (``.decision``/``.reason``/
    ``.additional_context``) -- neither ``RuntimeVerdict`` nor any other
    verdict dataclass in this codebase supports tuple unpacking (TOO-45
    R1a).

    Args:
        leaf: A :class:`~toolguard.parser.multiline.LeafCommand` to resolve.
        resolve_one: Callable mapping a single command string to
            ``(decision, reason, additional_context)``.
        undecidable_fallback: The configured floor (TOO-19) -- see
            :func:`judge_unit`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` for the leaf, with
        the floor applied.
    """
    unit = _unit_for(leaf)
    part_verdicts = [_unit_from_tuple(part, resolve_one(part)) for part in unit.parts]
    outcome = judge_unit(unit, part_verdicts, undecidable_fallback)
    return RuntimeVerdict(
        decision=outcome.decision,
        reason=outcome.reason,
        additional_context=outcome.additional_context,
    )


def _extract_outer_command(leaf_text: str) -> str:
    """Extract the outer command from a leaf that may contain inline code.

    For ``<executor> -c "<code>"`` leaves, returns just the executor + flag
    without the code (e.g., ``uv run python -c``).  This also recognizes
    inline-code flags that are ATTACHED to their payload with no separating
    space or quote (e.g. ``-cimport os``, ``-c'code'``) and combined short
    flags (e.g. ``-uc``): in every case only the flag portion is kept, never
    the attached code.  For heredoc sentinel leaves, returns the command up
    to and including the sentinel.

    This string is used both to check for explicit deny patterns on the
    outer command (:func:`_resolve_leaf`) and, after a separate bounding step
    (see :func:`_truncate_for_display`), for the user-visible ASK-floor
    reason.  It is intentionally NOT length-truncated here: shortening it in
    this function would risk weakening the explicit-deny check, so display
    bounding is applied only at the point the string is rendered.

    Args:
        leaf_text: The leaf command text (may contain embedded newlines).

    Returns:
        The outer command stub (no embedded newlines), suitable for
        ``match_command``.
    """
    tokens = leaf_text.split()
    result_tokens = []
    for idx, tok in enumerate(tokens):
        match = _INLINE_FLAG_TOKEN_RE.match(tok)
        if match:
            bundle, flag_letter, attached = match.groups()
            if attached:
                # Code is attached directly to this token (no space/quote
                # separator) -- the flag stub ends here regardless of what
                # follows.
                result_tokens.append(f"-{bundle}{flag_letter}")
                break
            if idx + 1 < len(tokens):
                # Bare flag (e.g. -c, -uc) with a following token expected
                # to carry the code -- stop after the flag itself.
                result_tokens.append(tok)
                break
            # Bare flag with nothing following: not a recognizable inline
            # invocation, keep scanning like any other token.
            result_tokens.append(tok)
            continue
        result_tokens.append(tok)
        # If this token contains or IS the heredoc sentinel, include it and stop
        if "__HEREDOC_TO_" in tok:
            break
    return " ".join(result_tokens)


def _truncate_for_display(cmd: str, max_len: int = _MAX_DISPLAY_COMMAND_LEN) -> str:
    """Bound a command string for safe display in a permission-prompt reason.

    Collapses any embedded whitespace (including newlines) to single spaces
    -- defense in depth, since callers should already pass a newline-free
    string -- and truncates to at most *max_len* characters, appending a
    visible ellipsis marker when truncation occurs so the executor and flag
    portion at the start of the string always remain visible.

    Args:
        cmd: The command string to bound for display.
        max_len: Maximum number of characters to keep before the ellipsis
            marker.

    Returns:
        A single-line, length-bounded string safe to embed in a
        ``permissionDecisionReason``.
    """
    single_line = " ".join(cmd.split())
    if len(single_line) <= max_len:
        return single_line
    return single_line[:max_len].rstrip() + " ...[truncated]"


def _accumulate_contexts(contexts: List[Optional[str]]) -> Optional[str]:
    """Combine per-leaf ``additionalContext`` texts into one injectable block.

    Used for the all-allow compound case (TOO-19 Phase 1), where several
    sub-commands can each match a different enriched rule and every one of
    them is a decision-maker. The deny/ask cases have exactly one deciding
    leaf and pass its context through directly, so they never call this.

    The rules, in order of application:

    - Empty and blank texts are ignored, so callers may pass a per-leaf list
      containing ``None`` without filtering it first.
    - Duplicates (exact text equality) are dropped, keeping the first
      occurrence. One rule matching several sub-commands of the same compound
      is the common case and must not say the same thing twice.
    - Survivors are joined as separate paragraphs, blank line between, in
      first-seen order.

    Deliberately UNBOUNDED (TOO-19 code review M2): the word budget used to be
    enforced here, but that only ever covered this one code path -- the
    deny/ask Bash branches, Read/Write/Edit contexts, and hard-deny contexts
    never called this function, so they injected uncapped. The budget now
    lives in :func:`cap_context_words`, applied once at the actual injection
    boundary (:func:`toolguard.resolve.resolve_bash_permission_detailed` /
    :func:`toolguard.resolve.resolve_file_path_permission_detailed`) so it
    covers every decision path uniformly. This function's only job is
    dedup + paragraph join.

    Args:
        contexts: Per-leaf enrichment texts in match order; ``None`` entries
            (leaves whose winning rule carried no enrichment) are allowed.

    Returns:
        The joined paragraph block, or ``None`` when nothing survives, so the
        caller can omit the ``additionalContext`` key entirely rather than
        emit an empty string.
    """
    seen = set()
    kept: List[str] = []
    for text in contexts:
        if text is None or not text.strip() or text in seen:
            continue
        seen.add(text)
        kept.append(text)
    if not kept:
        return None
    return "\n\n".join(kept)


def cap_context_words(
    text: Optional[str], max_words: int = _MAX_CONTEXT_WORDS
) -> Optional[str]:
    """Enforce the ``additionalContext`` word budget on the FINAL text.

    TOO-19 code review M2: this is the single place the 500-word budget is
    now enforced, called once at the actual injection boundary --
    :func:`toolguard.resolve.resolve_bash_permission_detailed` and
    :func:`toolguard.resolve.resolve_file_path_permission_detailed` -- so it
    applies uniformly to allow, ask, deny, and hard-deny decisions, across
    every governed tool. Previously the budget lived inside
    :func:`_accumulate_contexts`, which only ran for the Bash all-allow
    branch; every other path injected uncapped (see the M2 finding).

    The algorithm operates on paragraphs (blank-line separated, the same
    separator :func:`_accumulate_contexts` joins with) with a greedy
    FIRST-FIT word budget: a paragraph that would push the running total past
    *max_words* is dropped WHOLE and scanning continues, so a later short
    paragraph can still fit. This preserves the pre-M2 semantics for a
    multi-paragraph accumulated block.

    The one case that changes behaviour: when NOTHING fits whole -- i.e. the
    first (or only) paragraph alone already exceeds *max_words* -- the old
    code returned ``None``, silently injecting nothing even though the rule
    author wrote real text. That is the M2 bug. Now that lone paragraph is
    truncated to a *max_words*-word prefix (at a word boundary, never
    mid-word) and a trailing marker paragraph is appended, so a non-empty
    input never collapses to nothing.

    Args:
        text: The final, already-assembled ``additionalContext`` text (the
            output of :func:`_accumulate_contexts`, or a single rule's raw
            enrichment for the deny/ask/hard-deny/file-path paths). ``None``
            or blank is passed through as ``None``.
        max_words: Total word budget. Defaults to :data:`_MAX_CONTEXT_WORDS`.

    Returns:
        The capped text, or ``None`` when *text* was ``None`` or blank.
    """
    if text is None or not text.strip():
        return None
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return None

    kept: List[str] = []
    total_words = 0
    for paragraph in paragraphs:
        words = len(paragraph.split())
        if total_words + words > max_words:
            continue
        kept.append(paragraph)
        total_words += words
    if kept:
        return "\n\n".join(kept)

    # Lone-oversize case (M2 fix): the first paragraph alone exceeds the
    # budget, so the greedy fit above kept nothing. Truncate it to a
    # max_words-word prefix rather than silently injecting nothing -- the
    # rule author's text is the only content there is.
    first_words = paragraphs[0].split()
    truncated = " ".join(first_words[:max_words])
    return (
        f"{truncated}\n\n"
        f"[toolguard: additionalContext truncated to {max_words} words -- "
        f"the original entry exceeded the injection budget]"
    )


def _combine_strictest(unit_verdicts: List[UnitVerdict]) -> RuntimeVerdict:
    """Combine per-unit UnitVerdicts into the compound's own verdict, strictest-wins.

    TOO-45 (compound/resolve cycle removal, step 1): takes ``List[UnitVerdict]``
    instead of the former ``(decision, reason, leaf_text, additional_context,
    fallback_kind)`` 5-tuple -- field-for-field the same shape
    (``UnitVerdict.decision``/``.reason``/``.sub_command``/
    ``.additional_context``/``.fallback_kind``), so this is a pure type
    change, not a logic change. This is also what lets both call sites in
    :func:`resolve_compound_permission_detailed` stop building two parallel
    representations of the same outcome (a 5-tuple for this function, a
    separate ``UnitVerdict`` for ``record_unit``) -- each now builds ONE
    ``UnitVerdict`` and passes it to both.

    Priority: deny > ask > allow.

    For the all-allowed case with multiple leaves, the combined reason uses the
    ``"cmd -> pattern"`` format (e.g. ``"git status -> git *"``), matching the
    expected log output and test format.

    ``additional_context`` handling (TOO-19 Phase 1): the deny and ask branches
    each have exactly ONE deciding leaf (strictest-wins picks the first), so
    that leaf's context passes through unchanged -- no accumulation. The
    all-allow branch is different: EVERY allowed leaf is a decision-maker (all
    of them had to allow for the compound to allow), so their contexts are
    routed through :func:`_accumulate_contexts` -- including the
    single-allowed-leaf case, so a lone allowed leaf still surfaces its
    context.

    ``fallback_warning`` (TOO-19 code review M1, the 4th return element):
    ``True`` iff the overall decision is ``'allow'`` and at least one
    contributing leaf's ``fallback_kind`` is ``'warned'`` -- i.e. at least one
    allowed leaf's verdict came from the WARNED value of ``no_match_fallback``
    or ``undecidable_fallback``. Computed as a structured ``any()`` over the
    per-leaf tags rather than re-derived from the (possibly summarised) final
    *reason* string, which is what let a multi-leaf all-allow compound
    silently drop the warning before this fix: the old downstream text-search
    (since removed) ran on the summary text below, which never repeats the
    marker substring. ``False`` for every non-``allow`` decision.

    Fabrication guard (TOO-19 code review M1, defect 2): in the multi-allow
    summary below, a leaf whose ``fallback_kind`` is not ``None`` is an
    escape-hatch allow, not a matched rule -- its reason's own trailing
    ``"...): <outer_cmd>"`` text must NOT be parsed as a ``"cmd -> pattern"``
    match (the ``": "`` split below would extract the outer-command stub as a
    fabricated pattern name; this is exactly what previously logged
    ``python -c "print(1)" -> python -c`` for a command no ``python -c`` rule
    ever matched). Such leaves get an explicit, honest placeholder instead: an
    absent/generic record is preferred over a false one. This placeholder
    text is deliberately comma-free even though nothing downstream re-splits
    it any more (TOO-45 R1e retired the ``hook.py`` reason-parse that used
    to): keeping the two placeholders (see :data:`FALLBACK_DENY_PLACEHOLDER`)
    to the same shape is cheaper than reasoning about whether that stays
    true.

    Args:
        unit_verdicts: List of per-unit :class:`~toolguard.config_types.UnitVerdict`
            records, in extraction order. ``sub_command`` is the original
            command/leaf/segment text for the unit; ``fallback_kind`` is
            ``'warned'``, ``'silent'``, ``'denied'``, or ``None`` (see
            :class:`~toolguard.config_types.UnitVerdict`'s own docstring).

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (TOO-45 R1e;
        reused rather than a new type -- ``decision``/``reason``/
        ``additional_context``/``fallback_warning`` is exactly this
        function's shape) with ``matched_rule``/``provenance``/``sub_matches``
        left at their defaults: this function combines already-decided
        REASON TEXT for the verdict's own wording, never structured
        per-sub-command data -- that lives on ``RuntimeVerdict.sub_matches``,
        populated independently by :mod:`toolguard.resolve`'s own driver loop,
        not by this function.
    """
    denied = [uv for uv in unit_verdicts if uv.decision == "deny"]
    asked = [uv for uv in unit_verdicts if uv.decision == "ask"]
    allowed = [uv for uv in unit_verdicts if uv.decision == "allow"]

    if denied:
        deciding = denied[0]
        return RuntimeVerdict(
            decision="deny",
            reason=deciding.reason,
            additional_context=deciding.additional_context,
        )
    if asked:
        deciding = asked[0]
        return RuntimeVerdict(
            decision="ask",
            reason=deciding.reason,
            additional_context=deciding.additional_context,
        )
    if allowed:
        accumulated_context = _accumulate_contexts(
            [uv.additional_context for uv in allowed]
        )
        fallback_warning = any(uv.fallback_kind == "warned" for uv in allowed)
        if len(allowed) == 1:
            deciding = allowed[0]
            return RuntimeVerdict(
                decision="allow",
                reason=deciding.reason,
                additional_context=accumulated_context,
                fallback_warning=fallback_warning,
            )
        # Multiple allowed units: build "cmd -> pattern" summary.
        match_details = []
        for uv in allowed:
            if uv.fallback_kind is not None:
                # Escape-hatch allow (TOO-19 code review M1 defect 2): do NOT
                # attempt the "cmd -> pattern" extraction below -- there is no
                # pattern, and the reason's trailing "...): <outer_cmd>" text
                # would be misparsed as one. Record that plainly instead.
                cmd_part = uv.sub_command.strip().rstrip(";").strip() or "?"
                match_details.append(f"{cmd_part} -> {FALLBACK_ALLOW_PLACEHOLDER}")
                continue
            # Extract the pattern from the unit's own reason.  It may be in
            # one of two forms:
            #   "Command matches allow pattern: <pat>"  (from check_permission)
            #   "cmd -> <pat>"  (already formatted by _resolve_leaf)
            r = uv.reason
            if " -> " in r:
                # Already in "cmd -> pattern" format: use as-is or reformat.
                # If sub_command is the cmd part, use that for clarity.
                pattern_part = r.split(" -> ", 1)[-1]
                cmd_part = (
                    uv.sub_command.strip().rstrip(";").strip() or r.split(" -> ", 1)[0]
                )
                match_details.append(f"{cmd_part} -> {pattern_part}")
            elif ": " in r:
                pattern_part = r.split(": ", 1)[1]
                cmd_part = uv.sub_command.strip().rstrip(";").strip() or "?"
                match_details.append(f"{cmd_part} -> {pattern_part}")
            else:
                match_details.append(r)
        return RuntimeVerdict(
            decision="allow",
            reason=f"All {len(allowed)} sub-commands allowed: [{', '.join(match_details)}]",
            additional_context=accumulated_context,
            fallback_warning=fallback_warning,
        )
    return RuntimeVerdict(decision="deny", reason="No commands to evaluate")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_compound_permission(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    ask_patterns: List[str] = None,
    extended_syntax: bool = True,
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Check permissions for a compound bash command.

    Extracts individual commands from a compound command line and checks each
    against the permission patterns.  Returns the strictest permission decision:

    - If ANY command is denied -> deny the entire command.
    - Else if ANY command requires ask -> ask for the entire command.
    - Else if ALL commands are allowed -> allow the entire command.

    Delegates to :func:`resolve_compound_permission` with a closure over
    :func:`toolguard.permissions.check_permission`, which returns a plain
    ``(decision, reason)`` 2-tuple (it has no notion of ``additionalContext``
    and has many other callers, so its signature is out of scope here) --
    padded to the 3-tuple ``resolve_one`` contract with a trailing ``None``.

    Args:
        command: The bash command line (may be compound or multi-line).
        allow_patterns: Patterns that allow commands.
        deny_patterns: Patterns that deny commands.
        ask_patterns: Reserved for future use.
        extended_syntax: If False, skip ``[regex]``/``[glob]``/``[native]``
            prefix parsing.
        undecidable_fallback: The configured floor (TOO-19) applied to
            foreign inline code / heredoc sinks and undecidable segments --
            one of ``'ask'`` (default), ``'deny'``, ``'allow_with_warning'``,
            or ``'allow'``. See :func:`resolve_compound_permission`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (TOO-45 R1e; reused
        rather than a new type -- this function's shape genuinely is
        ``decision``/``reason``/``additional_context``, ``RuntimeVerdict``'s
        own three required-in-spirit fields) where ``decision`` is
        ``'allow'``, ``'deny'``, or ``'ask'``. ``additional_context`` is
        always ``None`` here since ``check_permission`` carries no
        enrichment; ``sub_matches`` is always empty -- this legacy caller has
        no ``UnitVerdict`` concept (``check_permission`` returns a plain
        2-tuple, not a resolved-with-provenance result).
    """
    return resolve_compound_permission(
        command,
        lambda c: (
            *check_permission(c, allow_patterns, deny_patterns, extended_syntax),
            None,
        ),
        undecidable_fallback=undecidable_fallback,
    )


def resolve_compound_permission_detailed(
    command: str,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a compound command where each sub-command cascades independently.

    Each extracted sub-command is resolved through ``resolve_one`` -- typically
    a closure over
    :func:`toolguard.permission_resolution.resolve_command_permission`, so
    every sub-command independently runs the full more-specific-wins level
    cascade.
    The compound is allowed iff ALL sub-commands resolve to allow; otherwise the
    strictest outcome wins (any deny -> deny, then any ask -> ask).

    TOO-17: Multi-line input is fully pre-processed via
    :func:`toolguard.parser.multiline.extract_structured` before the per-leaf
    grammar step.  Undecidable segments (complex control structures, process
    substitution, foreign inline code without an explicit deny) resolve per
    *undecidable_fallback* (TOO-19; ``'ask'`` by default) rather than failing
    open.

    This is the REAL implementation (TOO-19 code review M1); ``resolve_compound_permission``
    is a thin backwards-compatible 3-tuple wrapper around it (many existing
    tests unpack that function's result as a 3-tuple directly, so its
    signature could not grow). This ``_detailed`` variant additionally
    returns a structured ``fallback_warning`` flag -- see
    :func:`_combine_strictest`.

    TOO-45 (compound/resolve cycle removal, step 5): a CONVENIENCE DRIVER over
    :func:`decompose`/:func:`judge_unit`/:func:`_combine_strictest` for
    callers with no ``UnitVerdict``-producing resolver of their own -- used by
    :func:`check_compound_permission` (which closes over
    :func:`~toolguard.permissions.check_permission`) and by ~40 test call
    sites, all with a plain 3-tuple ``resolve_one`` closure. THE PRODUCTION
    PATH (:mod:`toolguard.resolve`) does NOT use this function -- it drives
    ``decompose``/``judge_unit``/``_combine_strictest`` directly, with its own
    resolver that already produces real :class:`UnitVerdict`\\ s (see
    :func:`~toolguard.resolve.resolve_bash_permission_detailed`). No
    ``resolve_outer``/``record_unit`` callback parameters remain (TOO-45
    R1e's ask-floor-stub/audit-recording plumbing) -- nothing calls them any
    more: every part, of every unit kind, is resolved uniformly through
    :func:`_unit_from_tuple` wrapping *resolve_one*, and ``judge_unit``
    itself never records anything (that was always the caller's job; this
    driver simply has no ``sub_matches`` list to append to, matching its own
    long-standing "always empty" contract below).

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved ``(decision, reason, additional_context)`` (cascaded
            across config levels). Used for every part of every unit,
            including an ``'inline_code'`` unit's single outer-command-stub
            part.
        undecidable_fallback: The configured floor (TOO-19) for anything that
            cannot be safely decomposed -- one of ``'ask'`` (default),
            ``'deny'``, ``'allow_with_warning'``, or ``'allow'`` -- sourced
            from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.
            Threaded straight through to :func:`judge_unit`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (TOO-45 R1e). For
        an all-allowed compound the reason lists per-sub-command matched
        rules, matching the legacy format the hook logs; ``additional_context``
        is the accumulated ``additionalContext`` block (TOO-19 Phase 1) --
        see :func:`_combine_strictest` and :func:`_accumulate_contexts` --
        or ``None`` when nothing survived; ``fallback_warning`` is ``True``
        iff the decision is ``'allow'`` and at least one contributing leaf's
        verdict came from the WARNED value of ``no_match_fallback`` or
        ``undecidable_fallback`` (TOO-19 code review M1). ``sub_matches`` is
        always empty on the RETURNED verdict -- this driver has no
        ``UnitVerdict``-list concept of its own to accumulate one into (see
        :func:`check_compound_permission`'s own docstring for the same
        point).
    """
    units = decompose(command)

    if not units:
        return RuntimeVerdict(
            decision="deny", reason="No valid commands found in command line"
        )

    unit_verdicts = [
        judge_unit(
            unit,
            [_unit_from_tuple(part, resolve_one(part)) for part in unit.parts],
            undecidable_fallback,
        )
        for unit in units
    ]
    return _combine_strictest(unit_verdicts)


def resolve_compound_permission(
    command: str,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a compound command -- thin wrapper dropping the structured detail.

    Thin wrapper around :func:`resolve_compound_permission_detailed` (TOO-19
    code review M1). Kept as a separate, unchanged-PARAMETER-signature
    function because many existing tests (``test_compound.py``,
    ``test_hierarchical.py``, ``test_hard_deny.py``, ``test_multiline_bash.py``)
    call it directly. TOO-45 (compound/resolve cycle removal): the production
    path (:func:`toolguard.resolve.resolve_bash_permission_detailed`) no
    longer calls either this function or :func:`resolve_compound_permission_detailed`
    at all -- it drives :func:`decompose`/:func:`judge_unit`/
    :func:`_combine_strictest` directly.

    TOO-45 R1e: returns the full :class:`~toolguard.config_types.RuntimeVerdict`
    from :func:`resolve_compound_permission_detailed` directly (that
    function already returns exactly this type -- there was never a
    ``fallback_warning`` element to strip once both "detailed" and
    "non-detailed" variants share one return type) -- reused, not a new
    type, for the same reason :func:`check_compound_permission` reuses it.
    Callers unpacking this as a 3-tuple must move to attribute access
    (TOO-45 R1a: no verdict dataclass in this codebase supports tuple
    unpacking).

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved ``(decision, reason, additional_context)``.
        undecidable_fallback: The configured floor (TOO-19) -- see
            :func:`resolve_compound_permission_detailed`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict`.
    """
    return resolve_compound_permission_detailed(
        command, resolve_one, undecidable_fallback=undecidable_fallback
    )


def get_command_breakdown(command: str) -> List[str]:
    """Get a breakdown of individual commands from a compound command.

    Utility for debugging and logging.  Returns only the textual leaf commands
    (undecidable segments are represented by their ``original`` text).

    Args:
        command: The bash command line to break down.

    Returns:
        List of individual command strings.
    """
    structured = extract_structured(command)
    result = []
    for element in structured:
        if isinstance(element, LeafCommand):
            # Further split by PEG grammar
            result.extend(extract_commands(element.text))
        elif isinstance(element, UndecidableSegment):
            result.append(element.original)
    return result
