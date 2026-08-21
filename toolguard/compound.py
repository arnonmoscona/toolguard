"""
Compound command permission checking for toolguard.

Splits a compound or multi-line bash command into sub-commands, resolves
each through the caller's own permission cascade, and combines the results
strictest-wins (deny > ask > allow). Governing principle: when in doubt,
ASK by default -- any segment that cannot be safely decomposed resolves to
ASK unless the configured ``undecidable_fallback`` says otherwise (see
:func:`_apply_undecidable_floor`).

Shape: three pure functions, no callbacks -- :func:`decompose`,
:func:`judge_unit`, and :func:`_combine_strictest`. This module never calls
back into :mod:`toolguard.resolve`; the production caller drives these three
directly. See technical-notes.md for why the module is shaped this way.
"""

import logging
from dataclasses import dataclass, replace
from typing import Callable, List, Optional, Sequence, Tuple, Union

from toolguard.config_types import RuntimeVerdict, UnitVerdict
from toolguard.parser.command_extractor import (
    INLINE_FLAG_TOKEN_RE as _INLINE_FLAG_TOKEN_RE,
)
from toolguard.parser.command_extractor import (
    _detect_foreign_inline_code as _is_foreign_inline_code,
)
from toolguard.parser.command_extractor import extract_commands
from toolguard.parser.multiline import (
    LeafCommand,
    UndecidableSegment,
    extract_structured,
)
from toolguard.permissions import check_permission

logger = logging.getLogger(__name__)


#: Maximum length, in characters, of the command shown in the inline/heredoc
#: floor's reason string (see :func:`_truncate_for_display`). The
#: undecidable-segment reason uses its own hardcoded 80-character slice
#: instead, which this constant does not reach.
_MAX_DISPLAY_COMMAND_LEN = 120

#: The ``additionalContext`` word budget enforced by :func:`cap_context_words`.
#: Enrichment is a nudge, not a document -- past this budget it costs more
#: context than it earns.
_MAX_CONTEXT_WORDS = 500


#: Strictness ranking for the ``undecidable_fallback`` floor below -- deny >
#: ask > allow. Kept separate from ``_combine_strictest``'s own ordering:
#: that function combines several already-decided sub-commands with its own
#: reason-building rules, while this floor clamps a single decision.
_DECISION_STRICTNESS = {"allow": 0, "ask": 1, "deny": 2}

#: Maps each recognized ``undecidable_fallback`` value to the decision it
#: floors an undecidable result to. ``'allow_with_warning'`` and ``'allow'``
#: both map to ``'allow'`` -- i.e. no floor at all, the deliberate escape
#: hatch: the floor can only make a verdict stricter than allow, never
#: weaken an explicit deny or ask. Whether a warning is logged is decided
#: separately, by :func:`judge_unit`'s own branches below, not by this
#: table. ``'allow_with_no_warnings'`` never reaches this table -- it is
#: normalized to ``'allow'`` by
#: :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`
#: before compound.py sees it.
_UNDECIDABLE_FLOOR_DECISION = {
    "ask": "ask",
    "deny": "deny",
    "allow_with_warning": "allow",
    "allow": "allow",
}


def _apply_undecidable_floor(decision: str, undecidable_fallback: str) -> str:
    """Clamp *decision* to at least as strict as *undecidable_fallback* names.

    ``undecidable_fallback`` names a floor level, resolved strictest-wins
    against whatever the leaf/segment itself resolved to:

    ================  ===========  ============  =======================  ===========
    *decision*         ``ask``      ``deny``      ``allow_with_warning``   ``allow``
    ================  ===========  ============  =======================  ===========
    ``deny``           deny         deny          deny                     deny
    ``ask``            ask          deny          ask                      ask
    ``allow``          ask          deny          allow                    allow
    ================  ===========  ============  =======================  ===========

    An unrecognized *undecidable_fallback* value is treated as ``'ask'``,
    matching :meth:`toolguard.config.Configuration.resolved_undecidable_fallback`'s
    own default -- this function is defensive rather than raising, though it
    never sees a raw, unvalidated value in practice.

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
#: go but the ``allow`` came from a fallback escape hatch rather than a rule
#: match. Used by both :func:`_combine_strictest`'s multi-leaf summary and
#: ``hook.py``'s own audit-log rendering, so the two never disagree. Kept
#: comma-free: the multi-leaf summary at the bottom of
#: :func:`_combine_strictest` joins entries with ``", "``.
FALLBACK_ALLOW_PLACEHOLDER = "[fallback allow -- no rule matched]"

#: The ``deny``-side counterpart of :data:`FALLBACK_ALLOW_PLACEHOLDER`,
#: recorded as the ``Violated Rules`` entry wherever a deny came from the
#: ``undecidable_fallback=deny`` escape hatch rather than a matched deny
#: rule -- see ``hook.py``'s ``_log_non_allow_decision``. Kept to the same
#: comma-free shape.
FALLBACK_DENY_PLACEHOLDER = "[fallback deny -- no rule matched]"


@dataclass(frozen=True)
class CommandUnit:
    """One decidable element of a compound command line, in extraction order.

    Produced by :func:`decompose`. Carries the element's own text plus the
    command strings a rule engine must decide on its behalf, as data -- so a
    caller (:mod:`toolguard.resolve`) resolves them itself rather than this
    module calling back into the caller (see technical-notes.md for why).

    Attributes:
        text: The unit's real, full source text. Becomes
            ``UnitVerdict.sub_command`` for whatever verdict this unit ends
            up with, regardless of *kind* -- never the ``'inline_code'``
            stub in *parts*.
        kind: One of ``'plain'`` (an ordinary leaf, further PEG-split into
            zero or more sub-commands), ``'inline_code'`` (an ASK-floor leaf
            -- foreign inline code / heredoc sink), ``'undecidable'`` (a
            grammar-level
            :class:`~toolguard.parser.command_extractor.UndecidableSegment`),
            or ``'unknown'`` (the defensive, currently-unreachable fallback
            for an extraction result of neither type). Decides only WHICH
            POLICY :func:`judge_unit` applies -- not whether *parts* holds
            anything to resolve; that is :attr:`parts`'s own contract, and a
            ``'plain'`` unit is not guaranteed non-empty (see
            :attr:`parts`).
        parts: Command strings a rule engine must decide on this unit's
            behalf, in order. Emptiness is the sole, reliable signal for
            "nothing to resolve" -- test ``not unit.parts``, never *kind*:
            ``'plain'`` -> zero or more PEG sub-commands of *text*
            (via :func:`~toolguard.parser.command_extractor.extract_commands`
            -- can itself be empty, e.g. ``$(:)``, handled by that
            emptiness rather than by a distinct kind);
            ``'inline_code'`` -> exactly one element, the untruncated
            outer-command stub (see :func:`_extract_outer_command` --
            deliberately not length-truncated, since truncating here would
            risk weakening explicit-deny detection); ``'undecidable'``/
            ``'unknown'`` -> always empty, by construction.
        audits_as_one: Whether this unit contributes exactly one audit-log
            entry (``True`` for ``'inline_code'``/``'undecidable'`` -- a
            floor decided the outcome, not any part's own rule match, so the
            unit's own final verdict is the only honest audit entry) or
            whether its audit entries ARE its own parts' verdicts (``False``
            for ``'plain'``/``'unknown'`` -- a zero-part unit of either kind
            then contributes no audit entry at all, since there is nothing
            in *parts* to record). Decided by :func:`_audits_as_one`, called
            from :func:`_unit_for`.
        audit_parts: Command strings recorded in the breakdown alongside this
            unit's own judged verdict and folded into its reason text when
            all-allow -- only ``'inline_code'`` populates this, with
            whichever of *text*'s own substitutions are themselves foreign
            inline code (see
            :func:`~toolguard.parser.command_extractor._detect_foreign_inline_code`).
            A ``deny`` or ``ask`` here still decides the unit outright, the
            same as :attr:`deny_check_parts` below -- see :func:`judge_unit`
            and :func:`_pick_strictest`. Empty for every other kind.
        deny_check_parts: Every OTHER substitution of *text* (via
            :func:`~toolguard.parser.command_extractor.extract_commands`,
            minus *text* itself and minus :attr:`audit_parts`) -- checked for
            a deny (ordinary or hard-deny) or an ask the same as
            :attr:`audit_parts`, but never itemised in the breakdown or
            folded into the unit's reason text unless one of them actually
            decides the unit. An allowed entry still contributes to the
            unit's other aggregate fields, via :func:`judge_unit`'s
            ``all_parts``: its
            :attr:`~toolguard.config_types.UnitVerdict.fallback_kind` can
            still set the compound's ``fallback_warning``, and its
            :attr:`~toolguard.config_types.UnitVerdict.additional_context`
            is still accumulated into the unit's own. Kept separate from
            :attr:`audit_parts` so a merely-allowed candidate here (an
            unrelated ``$(mktemp -d)`` alongside a ``python -c`` one, say)
            cannot change what an all-allow leaf's reason/breakdown show --
            only close the real gap this field exists for: an unrelated
            substitution's own ``deny``/hard-deny/``ask`` match must still
            decide, even though it was never itself foreign inline code.
            Empty for every other kind.
        note: :attr:`~toolguard.parser.command_extractor.UndecidableSegment.reason`
            for an ``'undecidable'`` unit, else ``None``.
    """

    text: str
    kind: str
    parts: Tuple[str, ...]
    audits_as_one: bool
    audit_parts: Tuple[str, ...] = ()
    deny_check_parts: Tuple[str, ...] = ()
    note: Optional[str] = None


def _audits_as_one(element: Union[LeafCommand, UndecidableSegment]) -> bool:
    """Whether a floor decides *element*'s outcome rather than any part's own rule match.

    True for an :class:`~toolguard.parser.multiline.UndecidableSegment` (no
    rule matched anything) and for an ask-floored
    :class:`~toolguard.parser.command_extractor.LeafCommand` (the floor's
    outer-stub probe decides it, not real per-part matching); False for an
    ordinary leaf. Decided from *element* directly, so a future
    :func:`_unit_for` branch can set this independently of ``kind``.
    """
    if isinstance(element, UndecidableSegment):
        return True
    return isinstance(element, LeafCommand) and element.ask_floor


def _unit_for(element: Union[LeafCommand, UndecidableSegment]) -> CommandUnit:
    """Map one :func:`~toolguard.parser.multiline.extract_structured` element to a :class:`CommandUnit`.

    The one place ``LeafCommand.ask_floor`` is read to decide a unit's
    ``kind``: mis-mapping an ask-floor leaf to ``'plain'`` would let its
    content bypass the ASK floor entirely and be resolved -- and
    potentially allowed -- as ordinary PEG-split sub-commands.

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
            audits_as_one=_audits_as_one(element),
            note=element.reason,
        )
    if isinstance(element, LeafCommand):
        if element.ask_floor:
            outer_cmd = _extract_outer_command(element.text)
            leaf_text = element.text.strip()
            other_commands = [
                cmd for cmd in extract_commands(element.text) if cmd != leaf_text
            ]
            audit_parts = tuple(
                cmd for cmd in other_commands if _is_foreign_inline_code(cmd)
            )
            deny_check_parts = tuple(
                cmd for cmd in other_commands if cmd not in audit_parts
            )
            return CommandUnit(
                text=element.text,
                kind="inline_code",
                parts=(outer_cmd,),
                audits_as_one=_audits_as_one(element),
                audit_parts=audit_parts,
                deny_check_parts=deny_check_parts,
            )
        sub_commands = extract_commands(element.text)
        return CommandUnit(
            text=element.text,
            kind="plain",
            parts=tuple(sub_commands),
            audits_as_one=_audits_as_one(element),
        )
    # Should not happen -- extract_structured only ever returns the two
    # types above. Logged here, where the actual unexpected type is still
    # known; the driver only ever sees the resulting 'unknown'-kind unit.
    logger.warning("Unknown extraction result type: %r", type(element))
    return CommandUnit(text="", kind="unknown", parts=(), audits_as_one=False)


def decompose(command: str) -> List[CommandUnit]:
    """Split a command line into decidable units. Pure structure -- decides nothing.

    Args:
        command: The bash command line (may be compound or multi-line).

    Returns:
        The ordered list of :class:`CommandUnit`\\ s, one per
        ``extract_structured`` element. Empty when *command* contains no
        valid commands at all.
    """
    return [_unit_for(element) for element in extract_structured(command)]


@dataclass(frozen=True)
class ResolveOneResult:
    """One command string's cascade resolution, as returned by a ``resolve_one`` callable.

    The ``resolve_one`` contract for this module's own test-only
    compound-resolution driver (:func:`resolve_compound_permission_detailed`,
    :func:`check_compound_permission`, :func:`_resolve_leaf`) -- not used on
    the production hook path, which builds :class:`UnitVerdict` directly
    (see :mod:`toolguard.resolve`).

    A frozen dataclass rather than a positional tuple: it carries
    ``fallback_kind`` as data supplied by the caller's own resolution,
    rather than a downstream classifier having to guess it back from
    *reason*.

    Attributes:
        decision: ``'allow'``, ``'ask'``, or ``'deny'``.
        reason: Human-readable reason for this decision.
        additional_context: This result's own ``additionalContext``
            enrichment, or ``None``.
        fallback_kind: ``'warned'``, ``'silent'``, ``'denied'``, or
            ``None`` -- see :attr:`~toolguard.config_types.UnitVerdict.fallback_kind`.
    """

    decision: str
    reason: str
    additional_context: Optional[str] = None
    fallback_kind: Optional[str] = None


def _unit_from_result(sub_command: str, resolved: ResolveOneResult) -> UnitVerdict:
    """Adapt a ``resolve_one``-shaped :class:`ResolveOneResult` into a :class:`UnitVerdict`.

    ``resolve_one`` carries no ``matched_rule``/``provenance``; ``fallback_kind``
    is read from *resolved* directly, exactly as the caller resolved it.

    Args:
        sub_command: The command string that was resolved.
        resolved: ``resolve_one``'s own result for it.

    Returns:
        The corresponding :class:`UnitVerdict`, with ``matched_rule``/
        ``provenance`` both ``None``.
    """
    return UnitVerdict(
        sub_command=sub_command,
        decision=resolved.decision,
        matched_rule=None,
        provenance=None,
        reason=resolved.reason,
        additional_context=resolved.additional_context,
        fallback_kind=resolved.fallback_kind,
    )


def _combine_inline_code_reason(
    stub_verdict: UnitVerdict, audit_part_verdicts: Sequence[UnitVerdict]
) -> Optional[Tuple[str, Optional[str]]]:
    """Reason/additional_context an inline_code unit shows when it has audit_parts.

    Delegates to :func:`_combine_strictest` over ``[stub_verdict,
    *audit_part_verdicts]`` for the same "cmd -> pattern" aggregate wording a
    ``'plain'`` unit with the same sub-commands would produce. This text
    reaches the permission prompt and the audit log, not just a display
    surface -- so the caller must pass *stub_verdict* with its
    ``fallback_kind`` already set to reflect the escape hatch (see the
    ``'inline_code'`` branch above), never the stub's own naturally-computed
    value: a genuine-looking ``matched_rule`` on the truncated stub is not a
    verified match, and combining it here as one would fabricate an
    attribution. ``fallback_kind`` on the returned unit as a whole is still
    the caller's own to derive -- this
    function's combine only tracks whether one of *these* parts is genuinely
    ``'warned'``, not the escape hatch itself.

    Returns:
        None (meaning: use the floor's own simpler wording instead) when
        there are no *audit_part_verdicts*, or when any of them -- or
        *stub_verdict* -- did not decide ``'allow'``. An audit part's own
        deny/ask match must never leak into text describing a floor-decided
        allow.
    """
    if not audit_part_verdicts:
        return None
    combine_over = [stub_verdict, *audit_part_verdicts]
    if any(v.decision != "allow" for v in combine_over):
        return None
    combined = _combine_strictest(combine_over)
    return (combined.reason, combined.additional_context)


def _judge_undecidable_unit(
    unit: "CommandUnit", undecidable_fallback: str
) -> UnitVerdict:
    """Verdict for an 'undecidable' unit -- no rule matched, so only the
    ``undecidable_fallback`` floor decides (see :func:`_apply_undecidable_floor`).
    """
    # No rule matched, so there is no underlying decision to floor.
    # 'allow' (the least strict) is used as the base, so this always
    # resolves to whatever _UNDECIDABLE_FLOOR_DECISION maps
    # undecidable_fallback to.
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
        reason = f"Undecidable segment ({unit.note}): {display}"
    elif floored == "deny":
        reason = (
            f"Undecidable segment denied by undecidable_fallback=deny "
            f"({unit.note}): {display}"
        )
    elif undecidable_fallback == "allow_with_warning":
        # Deliberate no-floor escape hatch, with a warning. fallback_kind
        # is known structurally here -- no text matching needed.
        reason = (
            "Undecidable segment allowed with a warning by "
            f"undecidable_fallback=allow_with_warning ({unit.note}): "
            f"{display}"
        )
        fallback_kind = "warned"
    else:
        # undecidable_fallback == "allow": same no-floor escape hatch,
        # but no warning -- say so plainly rather than letting the
        # 'allow_with_warning' wording above cover both.
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


def _judge_inline_code_unit(
    unit: "CommandUnit",
    part_verdicts: List[UnitVerdict],
    undecidable_fallback: str,
    audit_part_verdicts: Sequence[UnitVerdict],
    deny_check_verdicts: Sequence[UnitVerdict],
) -> UnitVerdict:
    """Verdict for an 'inline_code' unit (ASK-floor leaf: foreign inline code
    or heredoc sink). ``part_verdicts[0]`` is the outer-command stub's own
    resolution; an explicit deny/ask anywhere in *unit* still decides ahead
    of the floor -- see :attr:`CommandUnit.audit_parts` and
    :attr:`CommandUnit.deny_check_parts`.
    """
    # ASK-floor leaves (foreign inline code, foreign heredoc sinks) still
    # need an explicit-deny check, but allow/ask floors per
    # undecidable_fallback. The leaf text may contain embedded newlines
    # (a multiline -c arg) that would confuse the PEG grammar -- parts[0]
    # is the outer command stub only (without the inline payload), for
    # exactly this reason.
    #
    # The six UnitVerdict constructions below look near-duplicate enough
    # to consolidate into a table -- don't. This is the one branch where
    # a silent inversion during that kind of refactor is a security hole,
    # not just a style regression.
    outer_cmd = unit.parts[0]
    stub = part_verdicts[0]
    # Every part contributing to this unit's decision and, once the
    # floor allows, its aggregate fields (fallback_kind/warned,
    # additional_context): the stub itself, audit_parts, and
    # deny_check_parts, checked in that order. Defined once and reused
    # by every consumer below, so a further aggregate field is one more
    # reader of all_parts rather than a fresh enumeration to get wrong.
    # reason is the one deliberate exception -- only the stub and
    # audit_parts fold into it, see _combine_inline_code_reason;
    # sub_matches itemisation is narrower again, see
    # CommandUnit.deny_check_parts.
    all_parts = (stub, *audit_part_verdicts, *deny_check_verdicts)
    # A substitution's own deny OR ask -- an ordinary rule, hard_deny, or
    # ask match, on the stub itself, an audit_part, or a deny_check_part
    # -- still decides the unit: none of the three is merely
    # observational for a deny/ask, only for allow. Routed through
    # _pick_strictest, the same first-match-within-a-tier primitive
    # _combine_strictest itself uses to combine a compound's units --
    # not a bespoke, deny-only scan, which would silently drop an ask
    # reaching no branch at all.
    strictest_kind, strictest_verdict = _pick_strictest(all_parts)
    deciding = stub if strictest_kind == "allow" else strictest_verdict
    decision, reason, additional_context, matched_rule, provenance = (
        deciding.decision,
        deciding.reason,
        deciding.additional_context,
        deciding.matched_rule,
        deciding.provenance,
    )
    if decision == "deny":
        # Either the stub's own deny, or an audit part's -- either way a
        # real rule fired, so matched_rule/provenance are genuine
        # attributions, not an escape hatch. Only the recorded
        # sub_command text needs correcting, to the leaf's real, full
        # text.
        return UnitVerdict(
            sub_command=unit.text,
            decision="deny",
            matched_rule=matched_rule,
            provenance=provenance,
            reason=reason,
            additional_context=additional_context,
            fallback_kind=None,
        )
    # allow or ask -> floor per undecidable_fallback. Bound the command
    # shown in the reason so an unbounded inline-code blob never reaches
    # the permission prompt -- the deny check above already used the
    # untruncated outer_cmd, so this cannot weaken deny detection. The
    # floor, not the rule match, decides from here -- its context is
    # dropped.
    display_cmd = _truncate_for_display(outer_cmd)
    floored = _apply_undecidable_floor(decision, undecidable_fallback)
    if floored == "ask":
        if decision == "ask":
            # The floor made no change -- an explicit ask rule already
            # decided 'ask' before the floor was consulted, whether on
            # the stub itself or on a substitution _pick_strictest
            # promoted above. Preserve that verdict's own reason/context
            # rather than floor language that would misattribute the
            # verdict's real cause; matched_rule/provenance are genuine
            # attributions here too -- only the sub_command text needs
            # correcting.
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
        # 'ask'. The floor, not whatever the stub matched, decided --
        # matched_rule/provenance must NOT carry the stub's match.
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
        # fallback_kind='denied' here is safe: _combine_strictest
        # discards fallback_kind entirely for any non-allow decision, so
        # this is a more informative audit tag with no behavioural
        # change to the compound's own reason.
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
    # floored == "allow": undecidable_fallback is either
    # 'allow_with_warning' or 'allow' -- both are the deliberate
    # no-floor escape hatch, differing only in whether a warning is
    # logged. Branch on the actual configured value (not just "floored
    # == allow", which both share) so 'allow' never claims a warning was
    # emitted.
    if undecidable_fallback == "allow_with_warning":
        floor_reason = (
            "Allowed with a warning by undecidable_fallback=allow_with_warning "
            f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}"
        )
        floor_fallback_kind = "warned"
    else:
        floor_reason = (
            "Allowed with no warning by undecidable_fallback=allow "
            f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}"
        )
        floor_fallback_kind = "silent"
    # With audit_parts, the breakdown should still show them, the same
    # way a 'plain' unit over the same sub-commands would -- see
    # _combine_inline_code_reason. That folded text only survives to
    # RuntimeVerdict.reason when this is the compound's ONLY allowed
    # unit; with two or more, _combine_strictest's own multi-unit
    # summary replaces it with the fabrication-guard placeholder
    # instead. Without audit_parts (the common case), the floor's own
    # wording above is unchanged either way.
    #
    # The stub is fed in with fallback_kind FORCED to floor_fallback_kind
    # rather than its own natural value: reaching this branch at all
    # means the escape hatch decided (decision was already 'allow'
    # before the floor, or _pick_strictest above found nothing
    # stricter), so even a genuine-looking matched_rule on the stub is a
    # coincidental glob match on the TRUNCATED stub text (see
    # _extract_outer_command), never a verified read of the leaf's real
    # content. Trusting that match would bypass _combine_strictest's own
    # fabrication guard for exactly the leaves this branch exists to
    # floor.
    combined = _combine_inline_code_reason(
        replace(stub, sub_command=unit.text, fallback_kind=floor_fallback_kind),
        audit_part_verdicts,
    )
    combined_reason = combined[0] if combined else floor_reason
    # additional_context: accumulated over all_parts in full (see its
    # own comment above), not just the stub/audit_parts pair reason
    # folds in.
    combined_context = _accumulate_contexts([v.additional_context for v in all_parts])
    # fallback_kind: 'warned' whenever the floor itself is, or any part
    # in all_parts was genuinely warned by no_match_fallback.
    warned = floor_fallback_kind == "warned" or any(
        v.fallback_kind == "warned" for v in all_parts
    )
    fallback_kind = "warned" if warned else floor_fallback_kind
    return UnitVerdict(
        sub_command=unit.text,
        decision="allow",
        matched_rule=None,
        provenance=None,
        reason=combined_reason,
        additional_context=combined_context,
        fallback_kind=fallback_kind,
    )


def _judge_plain_unit(
    unit: "CommandUnit", part_verdicts: List[UnitVerdict]
) -> UnitVerdict:
    """Verdict for a 'plain' unit -- combines its own PEG sub-command verdicts
    strictest-wins, or fails closed to deny if extraction produced none.
    """
    if not part_verdicts:
        # Empty leaf -- should not normally happen. Denies the whole
        # compound (a defensive fail-closed default, not a no-op), but
        # is not an audit-log entry of its own: not a real sub-command
        # that ran.
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

    # Reformat each part's own reason for the leaf's aggregate wording,
    # for _combine_strictest's inner call below only -- it never touches
    # part_verdicts itself, which the caller separately uses for
    # sub_matches. Deny/ask get the sub-command context folded into the
    # reason so _combine_strictest can pass it through unchanged; allow
    # passes the raw reason through so _combine_strictest can build the
    # "cmd -> pattern" summary for the all-allowed case.
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

    # Route through the one strictest-wins combinator. Its own aggregate
    # fallback_warning bool collapses to 'warned'/None here -- the outer
    # combine only needs to know whether to count this leaf toward the
    # warning stream.
    combined = _combine_strictest(inner_units)
    # No single decider to attribute across potentially several inner
    # sub-commands, so matched_rule/provenance stay None.
    return UnitVerdict(
        sub_command=unit.text,
        decision=combined.decision,
        matched_rule=None,
        provenance=None,
        reason=combined.reason,
        additional_context=combined.additional_context,
        fallback_kind=("warned" if combined.fallback_warning else None),
    )


def _judge_unknown_unit(unit: "CommandUnit") -> UnitVerdict:
    """Verdict for the defensive, currently-unreachable 'unknown' unit kind."""
    # Defensive fallback for the unreachable 'unknown' kind -- see
    # _unit_for's own comment for why.
    return UnitVerdict(
        sub_command=unit.text,
        decision="ask",
        matched_rule=None,
        provenance=None,
        reason="Unknown extraction result; cannot verify",
        additional_context=None,
        fallback_kind=None,
    )


def judge_unit(
    unit: "CommandUnit",
    part_verdicts: List[UnitVerdict],
    undecidable_fallback: str = "ask",
    audit_part_verdicts: Sequence[UnitVerdict] = (),
    deny_check_verdicts: Sequence[UnitVerdict] = (),
) -> UnitVerdict:
    """Verdict for ONE :class:`CommandUnit`, given what the rules said about its parts.

    Decides; never resolves and never records -- both are the caller's job.

    Args:
        unit: The :class:`CommandUnit` to judge (see :func:`decompose`).
        part_verdicts: The caller's own resolution of each string in
            ``unit.parts``, in that order and the same length -- for
            ``'plain'``, one :class:`UnitVerdict` per PEG sub-command; for
            ``'inline_code'``, exactly one, the outer-command stub's
            resolution; empty for ``'undecidable'``/``'unknown'``.
        undecidable_fallback: The configured floor -- one of ``'ask'``
            (default), ``'deny'``, ``'allow_with_warning'``, or ``'allow'``
            -- sourced from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.
        audit_part_verdicts: The caller's own resolution of
            ``unit.audit_parts``, in order. An ``allow`` entry only ever
            folds into an ``'inline_code'`` unit's own reason text for
            display (see :func:`_combine_inline_code_reason`); a ``deny`` or
            ``ask`` entry decides the unit outright -- see the
            ``'inline_code'`` branch below and :func:`_pick_strictest`.
            Empty for every unit with no ``audit_parts``.
        deny_check_verdicts: The caller's own resolution of
            ``unit.deny_check_parts``, in order -- checked for a ``deny`` or
            ``ask`` the same as *audit_part_verdicts*, but never folded into
            the reason text and never itemised unless one of them decides.
            Empty for every unit with no ``deny_check_parts``.

    Returns:
        A :class:`UnitVerdict` for *unit*, with ``sub_command`` always set to
        ``unit.text`` (the unit's real, full source text -- never the
        ``'inline_code'`` stub).

    Raises:
        ValueError: If ``len(part_verdicts) != len(unit.parts)``,
            ``len(audit_part_verdicts) != len(unit.audit_parts)``, or
            ``len(deny_check_verdicts) != len(unit.deny_check_parts)`` (a
            loud, immediate failure rather than a silent misattribution), or
            if ``unit.kind`` is not one of ``'plain'``, ``'inline_code'``,
            ``'undecidable'``, or ``'unknown'`` -- a fifth kind must be
            decided here, not silently fall through to a default.
    """
    if len(part_verdicts) != len(unit.parts):
        raise ValueError(
            f"judge_unit: part_verdicts has {len(part_verdicts)} entries but "
            f"unit.parts has {len(unit.parts)} for unit.text={unit.text!r} "
            f"(kind={unit.kind!r}) -- part_verdicts must be the caller's own "
            "resolution of unit.parts, in the same order and length."
        )
    if len(audit_part_verdicts) != len(unit.audit_parts):
        raise ValueError(
            f"judge_unit: audit_part_verdicts has {len(audit_part_verdicts)} "
            f"entries but unit.audit_parts has {len(unit.audit_parts)} for "
            f"unit.text={unit.text!r} (kind={unit.kind!r}) -- "
            "audit_part_verdicts must be the caller's own resolution of "
            "unit.audit_parts, in the same order and length."
        )
    if len(deny_check_verdicts) != len(unit.deny_check_parts):
        raise ValueError(
            f"judge_unit: deny_check_verdicts has {len(deny_check_verdicts)} "
            f"entries but unit.deny_check_parts has {len(unit.deny_check_parts)} "
            f"for unit.text={unit.text!r} (kind={unit.kind!r}) -- "
            "deny_check_verdicts must be the caller's own resolution of "
            "unit.deny_check_parts, in the same order and length."
        )

    if unit.kind == "undecidable":
        return _judge_undecidable_unit(unit, undecidable_fallback)
    if unit.kind == "inline_code":
        return _judge_inline_code_unit(
            unit,
            part_verdicts,
            undecidable_fallback,
            audit_part_verdicts,
            deny_check_verdicts,
        )
    if unit.kind == "plain":
        return _judge_plain_unit(unit, part_verdicts)
    if unit.kind == "unknown":
        return _judge_unknown_unit(unit)

    # A fifth kind reaching here was never decided -- raise rather than
    # silently falling through to a default that might mis-audit or
    # mis-floor it.
    raise ValueError(f"judge_unit: unrecognized CommandUnit.kind {unit.kind!r}")


def _resolve_leaf(
    leaf: LeafCommand,
    resolve_one: Callable[[str], ResolveOneResult],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a single leaf command -- thin wrapper dropping the structured detail.

    Drives :func:`_unit_for` + :func:`judge_unit` directly. *resolve_one* is
    used for every part regardless of *leaf*'s kind.

    Returns a :class:`~toolguard.config_types.RuntimeVerdict`, not a bare
    :class:`ResolveOneResult` -- ``matched_rule``/``provenance``/etc. simply
    stay at their defaults.

    Args:
        leaf: A :class:`~toolguard.parser.command_extractor.LeafCommand` to
            resolve.
        resolve_one: Callable mapping a single command string to its
            :class:`ResolveOneResult`.
        undecidable_fallback: The configured floor -- see :func:`judge_unit`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` for the leaf, with
        the floor applied.
    """
    unit = _unit_for(leaf)
    part_verdicts = [_unit_from_result(part, resolve_one(part)) for part in unit.parts]
    outcome = judge_unit(unit, part_verdicts, undecidable_fallback)
    return RuntimeVerdict(
        decision=outcome.decision,
        reason=outcome.reason,
        additional_context=outcome.additional_context,
    )


def _extract_outer_command(leaf_text: str) -> str:
    """Extract the outer command from a leaf that may contain inline code.

    For ``<executor> -c "<code>"`` leaves, returns just the executor + flag
    without the code (e.g. ``uv run python -c``). This also recognizes
    inline-code flags that are attached to their payload with no separating
    space (e.g. ``-cimport os``, ``-c'code'``) and combined short
    flags (e.g. ``-uc``): in every case only the flag portion is kept, never
    the attached code. For heredoc sentinel leaves, returns the command up
    to and including the sentinel.

    This string is used both to check for explicit deny patterns on the
    outer command and, after a separate bounding step (see
    :func:`_truncate_for_display`), for the user-visible permission-prompt
    reason. It is intentionally not length-truncated here: shortening it in
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
            # Bare flag as the last token: not a recognizable inline
            # invocation. Append it plainly, like any other token.
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

    Used for the all-allow compound case, where several sub-commands can
    each match a different enriched rule and every one of them is a
    decision-maker. The deny/ask cases have exactly one deciding leaf and
    pass its context through directly, so they never call this.

    The rules, in order of application:

    - Empty and blank texts are ignored, so callers may pass a per-leaf list
      containing ``None`` without filtering it first.
    - Duplicates (exact text equality) are dropped, keeping the first
      occurrence. One rule matching several sub-commands of the same
      compound is the common case and must not say the same thing twice.
    - Survivors are joined as separate paragraphs, blank line between, in
      first-seen order.

    Deliberately unbounded: the word budget lives in :func:`cap_context_words`,
    applied once at the actual injection boundary so it covers every
    decision path uniformly, not just this one. Do not add a cap here.

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

    The single place the word budget is enforced, called once at the actual
    injection boundary --
    :func:`toolguard.resolve.resolve_bash_permission_detailed` and
    :func:`toolguard.resolve.resolve_file_path_permission_detailed` -- so it
    applies uniformly to allow, ask, deny, and hard-deny decisions, across
    every governed tool.

    The algorithm operates on paragraphs (blank-line separated, the same
    separator :func:`_accumulate_contexts` joins with) with a greedy
    first-fit word budget: a paragraph that would push the running total
    past *max_words* is dropped whole and scanning continues, so a later
    short paragraph can still fit.

    When nothing fits whole -- i.e. every paragraph individually exceeds
    *max_words* -- only the first is truncated to a *max_words*-word prefix
    (at a word boundary, never mid-word) and returned, with a trailing
    marker paragraph appended, so a non-empty input never collapses to
    nothing. Any further oversize paragraphs are silently dropped: the
    marker says "truncated", not that later paragraphs were also discarded.

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

    # Lone-oversize case: the first paragraph alone exceeds the budget, so
    # the greedy fit above kept nothing. Truncate it to a max_words-word
    # prefix rather than silently injecting nothing -- the rule author's
    # text is the only content there is.
    first_words = paragraphs[0].split()
    truncated = " ".join(first_words[:max_words])
    return (
        f"{truncated}\n\n"
        f"[toolguard: additionalContext truncated to {max_words} words -- "
        f"the original entry exceeded the injection budget]"
    )


def _pick_strictest(
    verdicts: Sequence[UnitVerdict],
) -> Tuple[str, Optional[UnitVerdict]]:
    """Pick the strictest decision among *verdicts* -- deny > ask > allow, first match per tier.

    The one strictest-wins primitive this module uses everywhere a group of candidate
    verdicts must collapse to a single decider: :func:`_combine_strictest` (combining several
    already-judged units) and :func:`judge_unit`'s ``'inline_code'`` branch (deciding whether a
    substitution's own verdict overrides the outer stub's) both route through this rather than
    each scanning for their own decision type by hand -- a deny-only scan would silently drop an
    ``ask``.

    Args:
        verdicts: Candidate verdicts, in the order a tie within one tier should prefer.

    Returns:
        ``('deny'|'ask', verdict)`` for the first deny, else the first ask. ``('allow', None)``
        when every verdict allows, or *verdicts* is empty -- there is no single decider to name
        for an all-allow group; each caller handles that case itself.
    """
    for v in verdicts:
        if v.decision == "deny":
            return "deny", v
    for v in verdicts:
        if v.decision == "ask":
            return "ask", v
    return "allow", None


def _combine_strictest(unit_verdicts: List[UnitVerdict]) -> RuntimeVerdict:
    """Combine several already-judged UnitVerdicts into one, strictest-wins.

    Priority: deny > ask > allow. *unit_verdicts* may be a compound's own
    per-unit verdicts, or one leaf's own per-part verdicts -- this function
    does not care which; the combined result means whichever of those the
    caller passed in.

    For the all-allowed case with multiple leaves, the combined reason uses
    the ``"cmd -> pattern"`` format (e.g. ``"git status -> git *"``),
    matching the expected log output and test format.

    ``additional_context`` handling: the deny and ask branches each have
    exactly one deciding leaf (strictest-wins picks the first), so that
    leaf's context passes through unchanged -- no accumulation. The
    all-allow branch is different: every allowed leaf is a decision-maker
    (all of them had to allow for the compound to allow), so their contexts
    are routed through :func:`_accumulate_contexts` -- including the
    single-allowed-leaf case, so a lone allowed leaf still surfaces its
    context.

    ``fallback_warning`` is ``True`` iff the overall decision is ``'allow'``
    and at least one contributing leaf's ``fallback_kind`` is ``'warned'``.
    Computed as a structured ``any()`` over the per-leaf tags, not
    re-derived from the (possibly summarised) final *reason* string -- a
    multi-leaf all-allow compound's summary text does not repeat the
    warning marker per leaf, so a text search over it would silently drop
    the warning for anything but a single-leaf compound.

    Args:
        unit_verdicts: List of per-unit :class:`~toolguard.config_types.UnitVerdict`
            records, in extraction order. ``sub_command`` is the original
            command/leaf/segment text for the unit; ``fallback_kind`` is
            ``'warned'``, ``'silent'``, ``'denied'``, or ``None`` (see
            :class:`~toolguard.config_types.UnitVerdict`'s own docstring).

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` with
        ``matched_rule``/``provenance``/``sub_matches`` left at their
        defaults: this function combines already-decided reason text for
        the verdict's own wording, never structured per-sub-command data --
        that lives on ``RuntimeVerdict.sub_matches``, populated
        independently by :mod:`toolguard.resolve`'s own driver loop. The
        deny branch carries the deciding unit's own ``fallback_kind``
        through to ``RuntimeVerdict.fallback_kind`` unchanged (``'denied'``
        for the ``undecidable_fallback=deny`` escape hatch, else ``None``).
        An empty *unit_verdicts* fails closed: ``deny``, "No commands to
        evaluate".
    """
    kind, deciding = _pick_strictest(unit_verdicts)
    if kind == "deny":
        return RuntimeVerdict(
            decision="deny",
            reason=deciding.reason,
            additional_context=deciding.additional_context,
            fallback_kind=deciding.fallback_kind,
        )
    if kind == "ask":
        return RuntimeVerdict(
            decision="ask",
            reason=deciding.reason,
            additional_context=deciding.additional_context,
        )
    allowed = [uv for uv in unit_verdicts if uv.decision == "allow"]
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
                # Fabrication guard: an escape-hatch allow is not a matched
                # rule, so its reason's own trailing "...): <outer_cmd>"
                # text must NOT be parsed as a "cmd -> pattern" match below
                # -- that would fabricate a pattern name from the display
                # command (e.g. logging `python -c "print(1)" -> python -c`
                # for a command no rule ever matched). Record it plainly
                # instead.
                cmd_part = uv.sub_command.strip().rstrip(";").strip() or "?"
                match_details.append(f"{cmd_part} -> {FALLBACK_ALLOW_PLACEHOLDER}")
                continue
            # Extract the pattern from the unit's own reason. It may be in
            # one of two forms:
            #   "Command matches allow pattern: <pat>"  (from check_permission)
            #   "cmd -> <pat>"  (already formatted by _resolve_leaf)
            r = uv.reason
            if " -> " in r:
                # Already in "cmd -> pattern" format: reformat using
                # sub_command as the cmd part when available, for clarity.
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


def check_compound_permission(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    ask_patterns: List[str] = None,
    extended_syntax: bool = True,
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Check permissions for a compound bash command.

    Extracts individual commands from a compound command line and checks
    each against the permission patterns. Returns the strictest permission
    decision:

    - If ANY command is denied -> deny the entire command.
    - Else if ANY command requires ask -> ask for the entire command.
    - Else if ALL commands are allowed -> allow the entire command.

    Delegates to :func:`resolve_compound_permission` with a closure over
    :func:`toolguard.permissions.check_permission`, which returns a plain
    ``(decision, reason)`` 2-tuple -- wrapped as a :class:`ResolveOneResult`
    with ``additional_context``/``fallback_kind`` at their defaults (``check_permission``
    never produces a fallback outcome of its own).

    Args:
        command: The bash command line (may be compound or multi-line).
        allow_patterns: Patterns that allow commands.
        deny_patterns: Patterns that deny commands.
        ask_patterns: Reserved for future use.
        extended_syntax: If False, skip ``[regex]``/``[glob]``/``[native]``
            prefix parsing.
        undecidable_fallback: The configured floor applied to foreign
            inline code / heredoc sinks and undecidable segments -- one of
            ``'ask'`` (default), ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'``. See :func:`resolve_compound_permission`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` where ``decision``
        is ``'allow'``, ``'deny'``, or ``'ask'``. ``additional_context`` is
        always ``None`` here since ``check_permission`` carries no
        enrichment; ``sub_matches`` is always empty.
    """
    return resolve_compound_permission(
        command,
        lambda c: ResolveOneResult(
            *check_permission(c, allow_patterns, deny_patterns, extended_syntax)
        ),
        undecidable_fallback=undecidable_fallback,
    )


def resolve_compound_permission_detailed(
    command: str,
    resolve_one: Callable[[str], ResolveOneResult],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a compound command where each sub-command cascades independently.

    Each extracted sub-command is resolved through ``resolve_one``. The
    compound is allowed iff ALL sub-commands resolve to allow; otherwise the
    strictest outcome wins (any deny -> deny, then any ask -> ask).

    A convenience driver over :func:`decompose`/:func:`judge_unit`/
    :func:`_combine_strictest` for callers with only a plain ``resolve_one``
    closure -- not on the production path (see technical-notes.md for why).

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved :class:`ResolveOneResult` (cascaded across config
            levels). Used for every part of every unit, including an
            ``'inline_code'`` unit's single outer-command-stub part.
        undecidable_fallback: The configured floor for anything that cannot
            be safely decomposed -- one of ``'ask'`` (default), ``'deny'``,
            ``'allow_with_warning'``, or ``'allow'`` -- sourced from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.
            Threaded straight through to :func:`judge_unit`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` -- see
        :func:`_combine_strictest` for what its ``reason``/
        ``additional_context``/``fallback_warning`` mean. ``sub_matches`` is
        always empty on the returned verdict.
    """
    units = decompose(command)

    if not units:
        return RuntimeVerdict(
            decision="deny", reason="No valid commands found in command line"
        )

    unit_verdicts = [
        judge_unit(
            unit,
            [_unit_from_result(part, resolve_one(part)) for part in unit.parts],
            undecidable_fallback,
        )
        for unit in units
    ]
    return _combine_strictest(unit_verdicts)


def resolve_compound_permission(
    command: str,
    resolve_one: Callable[[str], ResolveOneResult],
    undecidable_fallback: str = "ask",
) -> RuntimeVerdict:
    """Resolve a compound command.

    Forwards to :func:`resolve_compound_permission_detailed` unchanged --
    a legacy alias with no behavior of its own.

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved :class:`ResolveOneResult`.
        undecidable_fallback: The configured floor -- see
            :func:`resolve_compound_permission_detailed`.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict`.
    """
    return resolve_compound_permission_detailed(
        command, resolve_one, undecidable_fallback=undecidable_fallback
    )


def get_command_breakdown(command: str) -> List[str]:
    """Get a breakdown of individual commands from a compound command.

    Returns the textual form of each element: PEG-split leaf commands, and
    each undecidable segment's own ``original`` text.

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
