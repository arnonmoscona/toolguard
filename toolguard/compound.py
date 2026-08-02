"""
Compound command permission checking for toolguard.

This module provides permission checking for compound bash commands,
validating each sub-command and returning the strictest permission decision.

TOO-17: resolve_compound_permission now uses the multi-line pre-processor
(:mod:`toolguard.parser.multiline`) to correctly handle multi-line commands,
heredocs, inline code, and control structures.  The governing principle is
**"when in doubt, ASK"**: any segment that cannot be safely decomposed
resolves to ASK rather than a silent allow of an undecomposed blob.
"""

import logging
from typing import Callable, List, Optional, Tuple

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


def _fallback_kind_for_reason(decision: str, reason: str) -> Optional[str]:
    """Classify a ``resolve_one`` result as a fallback-escape-hatch outcome or not.

    TOO-19 code review M1: structured detection where the caller can determine
    the outcome directly from what it just constructed (the ASK-floor and
    ``UndecidableSegment`` branches below), and this TEXT-based fallback ONLY
    for the one place that genuinely cannot be structural: an ordinary
    (non-ASK-floor) sub-command's ``resolve_one`` result. That callable's
    return type is a plain 3-tuple relied on by ~18 test-authored closures
    (see the TOO-19 implementation report), so the richer
    ``ResolvedDecision.fallback_warning`` bit computed inside
    :meth:`~toolguard.config.Configuration.resolve_permission_detailed` never
    reaches this module -- only its already-tested, verbatim reason wording
    does. Only the ``no_match_fallback`` marker can appear here:
    ``undecidable_fallback`` reasons are constructed by THIS module, never by
    ``resolve_one``.

    Args:
        decision: The sub-command's decision.
        reason: The sub-command's reason text.

    Returns:
        ``'warned'`` when *reason* names the ``allow_with_warning`` value of
        ``no_match_fallback``, ``'silent'`` when it names the plain
        ``allow`` value, or ``None`` for a non-``allow`` decision or a
        genuine rule match.
    """
    if decision != "allow":
        return None
    if "no_match_fallback=allow_with_warning" in reason:
        return "warned"
    if "no_match_fallback=allow" in reason:
        return "silent"
    return None


def _resolve_leaf_detailed(
    leaf: LeafCommand,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> Tuple[str, str, Optional[str], Optional[str]]:
    """Resolve a single leaf command through the grammar splitter then resolve_one.

    The leaf may still be a compound single-line command (``git status && echo x``).
    We run it through the existing PEG grammar to split it further, then apply
    ``resolve_one`` to each sub-command.

    The floor from the leaf's ``ask_floor`` flag is applied AFTER the normal
    resolution, strictest-wins against *undecidable_fallback* (TOO-19; see
    :func:`_apply_undecidable_floor`): an explicit ``deny`` is always
    preserved; ``allow``/``ask`` are clamped to at least as strict as
    *undecidable_fallback* names (``'ask'`` by default, matching the
    pre-TOO-19 behaviour of every existing caller).

    Special case for ASK-floor leaves (foreign inline code / foreign heredoc sinks):
    these often contain embedded newlines or other content that confuses the PEG
    grammar and the newline guard in ``match_command``.  For these leaves we
    resolve the outer command only (first token + flag up to the inline-code arg)
    to check for explicit denies; allows/asks are floored per *undecidable_fallback*.

    ``additional_context`` (TOO-19 Phase 1) handling on the ASK-floor path: a
    ``deny`` here IS the deciding match, so its context passes through
    unchanged -- a deny is the most valuable place for an explanation. On the
    genuinely-floored path (the floor actually raised the verdict) the rule
    match no longer determines the verdict (the floor does), so the context
    is dropped, consistent with how
    :meth:`~toolguard.config.Configuration._apply_parse_failure_ask_floor`
    clears it for the config-level ASK floor. TOO-19 code review m1: when
    ``resolve_one`` already returned ``'ask'`` from a real ``ask`` rule and
    the floor made no change (``floored == decision``), the floor decided
    nothing -- the rule's own reason and context are passed through
    unchanged instead of being misattributed to "ASK floor applied". The
    ``allow_with_warning``/``allow`` (TOO-19) escape-hatch branch
    (``floored == 'allow'``) is NOT affected by this distinction: it always
    names the escape hatch, because that message is about the leaf being
    unverifiable inline/heredoc content, not about whether a rule happened to
    also match the truncated outer command -- see that branch below.

    ``fallback_kind`` (TOO-19 code review M1, the 4th return element): a
    structured tag for whether this leaf's ``allow`` came from a fallback
    escape hatch rather than a matched rule, and if so whether it was the
    warned variant -- ``'warned'``, ``'silent'``, or ``None``. This is what
    lets the OUTER combine (:func:`resolve_compound_permission_detailed`)
    both (a) route a multi-leaf compound's warning to the WARNING log
    stream even when this leaf is only one of several allowed leaves, and
    (b) avoid fabricating a "cmd -> pattern" match for an escape-hatch leaf
    in its multi-allow summary (see :func:`_combine_strictest`). On the
    ASK-floor path this is known STRUCTURALLY, from *undecidable_fallback*
    itself -- no text matching. On the normal path it is collapsed from the
    inner :func:`_combine_strictest` call's own aggregate boolean (itself
    built from :func:`_fallback_kind_for_reason` per sub-command).

    Args:
        leaf: A :class:`~toolguard.parser.multiline.LeafCommand` to resolve.
        resolve_one: Callable mapping a single command string to
            ``(decision, reason, additional_context)``.
        undecidable_fallback: The configured floor (TOO-19) -- one of
            ``'ask'`` (default), ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'`` -- sourced from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.
            Defaults to ``'ask'`` so every pre-TOO-19 caller/test is
            unaffected.

    Returns:
        ``(decision, reason, additional_context, fallback_kind)`` for the
        leaf, with the floor applied.
    """
    # For ASK-floor leaves (foreign inline code, foreign heredoc sinks),
    # we need to check for explicit denies but floor allow/ask per
    # undecidable_fallback. The leaf text may contain embedded newlines
    # (multiline -c arg) that would confuse the PEG grammar and the newline
    # guard.  Resolve only the outer command stub (without the inline
    # payload) for deny checking.
    if leaf.ask_floor:
        outer_cmd = _extract_outer_command(leaf.text)
        decision, reason, additional_context = resolve_one(outer_cmd)
        if decision == "deny":
            return "deny", reason, additional_context, None
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
                # language that misattributes the verdict's real cause.
                return "ask", reason, additional_context, None
            # Genuine floor case: undecidable_fallback raised 'allow' to
            # 'ask'. Wording preserved verbatim from before TOO-19 so
            # existing tests/log parsing do not churn.
            return (
                "ask",
                f"ASK floor applied (inline/heredoc foreign code): {display_cmd}",
                None,
                None,
            )
        if floored == "deny":
            return (
                "deny",
                "Denied by undecidable_fallback=deny (inline/heredoc foreign "
                f"code, unable to safely verify): {display_cmd}",
                None,
                None,
            )
        # floored == "allow": undecidable_fallback is either 'allow_with_warning'
        # or 'allow' (TOO-19) -- both are the deliberate no-floor escape hatch,
        # differing only in whether a warning is logged. Branch on the ACTUAL
        # configured value (not just "floored == allow", which both share) so
        # 'allow' never claims a warning was emitted. fallback_kind is known
        # STRUCTURALLY here -- no text matching needed (TOO-19 code review M1).
        if undecidable_fallback == "allow_with_warning":
            return (
                "allow",
                "Allowed with a warning by undecidable_fallback=allow_with_warning "
                f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}",
                None,
                "warned",
            )
        return (
            "allow",
            "Allowed with no warning by undecidable_fallback=allow "
            f"(inline/heredoc foreign code, unable to safely verify): {display_cmd}",
            None,
            "silent",
        )

    # Use the PEG grammar to further split the leaf into sub-commands
    sub_commands = extract_commands(leaf.text)
    if not sub_commands:
        # Empty leaf -- treat as no-op; should not normally happen
        logger.debug("Empty leaf command after grammar extraction: %r", leaf.text)
        return "deny", "No valid commands found in leaf", None, None

    # Resolve each sub-command and build (decision, reason, cmd, context,
    # fallback_kind) quintuples. For deny/ask, pre-format the reason with the
    # sub-command context so that _combine_strictest can pass the formatted
    # message through unchanged. For allow, pass the raw reason through so
    # _combine_strictest can build the "cmd -> pattern" summary for the
    # all-allowed case.
    quads: List[Tuple[str, str, str, Optional[str], Optional[str]]] = []
    for cmd in sub_commands:
        decision, reason, additional_context = resolve_one(cmd)
        fallback_kind = _fallback_kind_for_reason(decision, reason)
        if decision == "deny":
            formatted = (
                f"Compound command contains denied sub-command: {cmd} ({reason})"
            )
        elif decision == "ask":
            formatted = (
                f"Compound command contains sub-command requiring approval:"
                f" {cmd} ({reason})"
            )
        else:
            # allow: pass raw reason through for "cmd -> pattern" formatting
            formatted = reason
        quads.append((decision, formatted, cmd, additional_context, fallback_kind))

    # Route through the ONE strictest-wins combinator. Its own aggregate
    # fallback_warning bool is collapsed back to the tri-state 'warned'/None
    # here -- an inner multi-sub-command leaf's OWN reason text (either the
    # single-allowed pass-through or the "All N sub-commands allowed: [...]"
    # summary) never has the trailing-colon shape that risks fabrication
    # (see _combine_strictest), so the outer combine needs only to know
    # whether to count this leaf toward the WARNING stream, not to re-gate
    # fabrication for it.
    decision, reason, additional_context, fallback_warning = _combine_strictest(quads)
    return (
        decision,
        reason,
        additional_context,
        ("warned" if fallback_warning else None),
    )


def _resolve_leaf(
    leaf: LeafCommand,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> Tuple[str, str, Optional[str]]:
    """Resolve a single leaf command -- backwards-compatible 3-tuple wrapper.

    Thin wrapper around :func:`_resolve_leaf_detailed` (TOO-19 code review
    M1) that drops the structured ``fallback_kind`` 4th element. Kept as a
    separate, unchanged-signature function because it is called directly (not
    just transitively) by many existing tests; :func:`resolve_compound_permission_detailed`
    calls :func:`_resolve_leaf_detailed` directly instead, to get the
    structured flag without widening this function's contract.

    Args:
        leaf: A :class:`~toolguard.parser.multiline.LeafCommand` to resolve.
        resolve_one: Callable mapping a single command string to
            ``(decision, reason, additional_context)``.
        undecidable_fallback: The configured floor (TOO-19) -- see
            :func:`_resolve_leaf_detailed`.

    Returns:
        ``(decision, reason, additional_context)`` for the leaf, with the
        floor applied.
    """
    decision, reason, additional_context, _fallback_kind = _resolve_leaf_detailed(
        leaf, resolve_one, undecidable_fallback
    )
    return decision, reason, additional_context


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


def _combine_strictest(
    results: List[Tuple[str, str, str, Optional[str], Optional[str]]],
) -> Tuple[str, str, Optional[str], bool]:
    """Combine (decision, reason, leaf_text, context, fallback_kind) tuples, strictest-wins.

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
    silently drop the warning before this fix: the old single downstream
    text-search (:func:`toolguard.resolve._bash_result_is_fallback_warning`)
    ran on the summary text below, which never repeats the marker substring.
    ``False`` for every non-``allow`` decision.

    Fabrication guard (TOO-19 code review M1, defect 2): in the multi-allow
    summary below, a leaf whose ``fallback_kind`` is not ``None`` is an
    escape-hatch allow, not a matched rule -- its reason's own trailing
    ``"...): <outer_cmd>"`` text must NOT be parsed as a ``"cmd -> pattern"``
    match (the ``": "`` split below would extract the outer-command stub as a
    fabricated pattern name; this is exactly what previously logged
    ``python -c "print(1)" -> python -c`` for a command no ``python -c`` rule
    ever matched). Such leaves get an explicit, honest placeholder instead: an
    absent/generic record is preferred over a false one. The placeholder is
    deliberately comma-free: ``hook.py``'s ``_parse_compound_match_details``
    splits this same bracketed list on ``", "`` to build its own per-sub-command
    log breakdown, so a placeholder containing a comma would itself be
    mis-split into two bogus entries there -- caught by end-to-end
    verification against the real hook, not by this module's own tests.

    Args:
        results: List of ``(decision, reason, leaf_text, additional_context,
            fallback_kind)`` 5-tuples where ``leaf_text`` is the original
            command text for the element and ``fallback_kind`` is
            ``'warned'``, ``'silent'``, or ``None`` (see
            :func:`_resolve_leaf_detailed`).

    Returns:
        ``(decision, reason, additional_context, fallback_warning)``.
    """
    denied = [(d, r, t, c) for d, r, t, c, _fk in results if d == "deny"]
    asked = [(d, r, t, c) for d, r, t, c, _fk in results if d == "ask"]
    allowed = [(d, r, t, c, fk) for d, r, t, c, fk in results if d == "allow"]

    if denied:
        _d, r, _t, c = denied[0]
        return "deny", r, c, False
    if asked:
        _d, r, _t, c = asked[0]
        return "ask", r, c, False
    if allowed:
        accumulated_context = _accumulate_contexts(
            [c for _d, _r, _t, c, _fk in allowed]
        )
        fallback_warning = any(fk == "warned" for _d, _r, _t, _c, fk in allowed)
        if len(allowed) == 1:
            _d, r, _t, _c, _fk = allowed[0]
            return "allow", r, accumulated_context, fallback_warning
        # Multiple allowed leaves: build "cmd -> pattern" summary.
        match_details = []
        for _d, r, leaf_text, _c, fk in allowed:
            if fk is not None:
                # Escape-hatch allow (TOO-19 code review M1 defect 2): do NOT
                # attempt the "cmd -> pattern" extraction below -- there is no
                # pattern, and the reason's trailing "...): <outer_cmd>" text
                # would be misparsed as one. Record that plainly instead.
                cmd_part = leaf_text.strip().rstrip(";").strip() or "?"
                match_details.append(
                    f"{cmd_part} -> [fallback allow -- no rule matched]"
                )
                continue
            # Extract the pattern from the leaf reason.  The leaf reason may be
            # in one of two forms:
            #   "Command matches allow pattern: <pat>"  (from check_permission)
            #   "cmd -> <pat>"  (already formatted by _resolve_leaf)
            if " -> " in r:
                # Already in "cmd -> pattern" format: use as-is or reformat.
                # If leaf_text is the cmd part, use that for clarity.
                pattern_part = r.split(" -> ", 1)[-1]
                cmd_part = (
                    leaf_text.strip().rstrip(";").strip() or r.split(" -> ", 1)[0]
                )
                match_details.append(f"{cmd_part} -> {pattern_part}")
            elif ": " in r:
                pattern_part = r.split(": ", 1)[1]
                cmd_part = leaf_text.strip().rstrip(";").strip() or "?"
                match_details.append(f"{cmd_part} -> {pattern_part}")
            else:
                match_details.append(r)
        return (
            "allow",
            f"All {len(allowed)} sub-commands allowed: [{', '.join(match_details)}]",
            accumulated_context,
            fallback_warning,
        )
    return "deny", "No commands to evaluate", None, False


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
) -> Tuple[str, str, Optional[str]]:
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
        ``(decision, reason, additional_context)`` where *decision* is
        ``'allow'``, ``'deny'``, or ``'ask'``. ``additional_context`` is
        always ``None`` here since ``check_permission`` carries no enrichment.
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
) -> Tuple[str, str, Optional[str], bool]:
    """Resolve a compound command where each sub-command cascades independently.

    Each extracted sub-command is resolved through ``resolve_one`` -- typically
    a closure over
    :meth:`toolguard.config.Configuration.resolve_permission_detailed`, so every
    sub-command independently runs the full more-specific-wins level cascade.
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
    :func:`_combine_strictest` -- computed from the same widened per-element
    quad :func:`_resolve_leaf_detailed` and the ``UndecidableSegment`` branch
    below already tag their own results with, rather than re-derived from the
    final (possibly leaf-summarised) reason text downstream.

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved ``(decision, reason, additional_context)`` (cascaded
            across config levels).
        undecidable_fallback: The configured floor (TOO-19) for anything that
            cannot be safely decomposed -- one of ``'ask'`` (default),
            ``'deny'``, ``'allow_with_warning'``, or ``'allow'`` -- sourced
            from
            :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`.
            Applied two ways: as a strictest-wins FLOOR against
            ``ask_floor`` leaves' own resolved decision (see
            :func:`_resolve_leaf_detailed`/:func:`_apply_undecidable_floor`,
            since those DID run through ``resolve_one`` and may have hit an
            explicit deny); and taken DIRECTLY for an
            :class:`~toolguard.parser.multiline.UndecidableSegment`, which
            never runs through ``resolve_one`` at all -- there is no
            underlying decision to floor. Defaults to ``'ask'`` so every
            pre-TOO-19 caller/test is unaffected.

    Returns:
        ``(decision, reason, additional_context, fallback_warning)``. For an
        all-allowed compound the reason lists per-sub-command matched rules,
        matching the legacy format the hook logs; ``additional_context`` is
        the accumulated ``additionalContext`` block (TOO-19 Phase 1) -- see
        :func:`_combine_strictest` and :func:`_accumulate_contexts` -- or
        ``None`` when nothing survived; ``fallback_warning`` is ``True`` iff
        the decision is ``'allow'`` and at least one contributing leaf's
        verdict came from the WARNED value of ``no_match_fallback`` or
        ``undecidable_fallback`` (TOO-19 code review M1).
    """
    structured = extract_structured(command)

    if not structured:
        return "deny", "No valid commands found in command line", None, False

    # Resolve each element and collect results.
    # Each entry is (decision, reason, leaf_text, additional_context,
    # fallback_kind) where leaf_text is the original element text (used to
    # build combined "cmd -> pattern" reason) and fallback_kind is
    # 'warned'/'silent'/None (TOO-19 code review M1; see
    # _resolve_leaf_detailed).
    all_results: List[Tuple[str, str, str, Optional[str], Optional[str]]] = []

    for element in structured:
        if isinstance(element, UndecidableSegment):
            # Cannot safely decompose -- no rule was ever matched, so there
            # is no underlying decision to floor; take undecidable_fallback
            # DIRECTLY (TOO-19), not via _apply_undecidable_floor. No rule
            # matched, so no context.
            floored = _UNDECIDABLE_FLOOR_DECISION.get(undecidable_fallback, "ask")
            logger.debug(
                "Undecidable segment (-> %s): %r reason=%s",
                floored,
                element.original[:80],
                element.reason,
            )
            display = element.original[:80]
            fallback_kind = None
            if floored == "ask":
                # Default case: wording preserved verbatim from before
                # TOO-19 so existing tests/log parsing do not churn.
                reason = f"Undecidable segment ({element.reason}): {display}"
            elif floored == "deny":
                reason = (
                    f"Undecidable segment denied by undecidable_fallback=deny "
                    f"({element.reason}): {display}"
                )
            elif undecidable_fallback == "allow_with_warning":
                # The deliberate no-floor escape hatch, WITH a warning.
                # fallback_kind is known STRUCTURALLY here -- no text
                # matching needed (TOO-19 code review M1).
                reason = (
                    "Undecidable segment allowed with a warning by "
                    f"undecidable_fallback=allow_with_warning ({element.reason}): "
                    f"{display}"
                )
                fallback_kind = "warned"
            else:
                # undecidable_fallback == "allow" (TOO-19): same no-floor
                # escape hatch, but no warning -- say so plainly rather than
                # letting the 'allow_with_warning' wording above cover both.
                reason = (
                    "Undecidable segment allowed with no warning by "
                    f"undecidable_fallback=allow ({element.reason}): {display}"
                )
                fallback_kind = "silent"
            all_results.append((floored, reason, element.original, None, fallback_kind))
        elif isinstance(element, LeafCommand):
            d, r, c, fk = _resolve_leaf_detailed(
                element, resolve_one, undecidable_fallback
            )
            all_results.append((d, r, element.text, c, fk))
        else:
            # Should not happen
            logger.warning("Unknown extraction result type: %r", type(element))
            all_results.append(
                ("ask", "Unknown extraction result; cannot verify", "", None, None)
            )

    return _combine_strictest(all_results)


def resolve_compound_permission(
    command: str,
    resolve_one: Callable[[str], Tuple[str, str, Optional[str]]],
    undecidable_fallback: str = "ask",
) -> Tuple[str, str, Optional[str]]:
    """Resolve a compound command -- backwards-compatible 3-tuple wrapper.

    Thin wrapper around :func:`resolve_compound_permission_detailed` (TOO-19
    code review M1) that drops the structured ``fallback_warning`` 4th
    element. Kept as a separate, unchanged-signature function because many
    existing tests (``test_compound.py``, ``test_hierarchical.py``,
    ``test_hard_deny.py``, ``test_multiline_bash.py``) unpack its result as a
    3-tuple directly; :func:`toolguard.resolve.resolve_bash_permission_detailed`
    calls :func:`resolve_compound_permission_detailed` directly instead, to
    get the structured flag without widening this function's contract.

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved ``(decision, reason, additional_context)``.
        undecidable_fallback: The configured floor (TOO-19) -- see
            :func:`resolve_compound_permission_detailed`.

    Returns:
        ``(decision, reason, additional_context)``.
    """
    decision, reason, additional_context, _fallback_warning = (
        resolve_compound_permission_detailed(
            command, resolve_one, undecidable_fallback=undecidable_fallback
        )
    )
    return decision, reason, additional_context


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
