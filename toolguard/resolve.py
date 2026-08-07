"""
Permission resolver layer for toolguard.

Not pure, despite what an earlier version of this docstring claimed (TOO-45
R6-S2 correction). Command-vs-pattern matching reads live filesystem state:
``normalization.py``'s ``exists()``/``is_symlink()``/``resolve()`` calls
(around lines 47-50 and 81), reached from ``permissions.py``'s pattern
matching (around lines 146 and 194), which every resolver below calls into.
A related check-to-use race in that disk read has been deliberately
deprioritised as a design decision; it is not mitigated here and should not
be chased as part of this correction. The narrower claim below IS still true
and is the actual contract callers rely on.

This module is the canonical, single source of truth for the core permission
resolution algorithms.  It contains ONLY functions that are:

- Side-effect-free in the sense callers actually depend on: no logging, no
  stdin/stdout, no ``sys.exit``.
- Self-contained at their level (they may import ``config``, ``permissions``,
  ``compound``, ``patterns``, and ``normalization``; they do NOT import
  ``hook``).

Both the live hook (``toolguard.hook``) and the ``api``/tooling layer
(``toolguard.api``, TOO-45 R6-S2's public decision interface; the previous
name for this, ``toolguard.tools.decision``, is now a backward-compatible
re-export -- see that module's docstring) import from here, ensuring that
what the hook decides at runtime is EXACTLY what tooling computes -- there is
no separate copy of the logic to drift.

Functions moved here from ``hook.py`` (previously private helpers):
- :func:`_anchor_file_pattern`
- :func:`_match_file_path_pattern`
- :func:`_decide_file_path_at_level_detailed`
- :func:`_check_file_path_hard_deny`
- :func:`resolve_file_path_permission_detailed`
- :func:`resolve_bash_permission_detailed`

``hook.py`` re-exports every name that was previously importable from it so
that all existing callers (including tests) remain unbroken.

Result dataclasses
------------------
:class:`~toolguard.config_types.RuntimeVerdict` is the structured return type
from both public resolver functions below (TOO-45 R1c collapsed the former
``BashResolution``/``FileResolution`` here, and ``ResolvedDecision`` in
:mod:`toolguard.config_types`, into this one type).
:class:`~toolguard.config_types.UnitVerdict` (formerly ``SubMatch``) records
one sub-command's outcome inside a compound Bash resolution, carried on
``RuntimeVerdict.sub_matches``. :class:`~toolguard.config_types.LevelMatch`
(TOO-45 R1f) is a third, lower altitude still: the raw
``(decision, reason, matched_pattern)`` result of ONE hierarchy level or
hard-deny pool check, returned by :func:`_decide_file_path_at_level_detailed`
and :func:`_check_file_path_hard_deny` below (and by
:func:`toolguard.permissions.check_hard_deny`/
:func:`toolguard.permissions.decide_command_at_level_detailed`) -- it is the
``decide_detailed`` callback contract
:func:`~toolguard.permission_resolution.resolve_permission_detailed` consumes.
All three are actually DEFINED in :mod:`toolguard.config_types`, not here --
see that module's docstring and each class's own docstring for why
(:mod:`toolguard.permission_resolution` constructs/consumes them directly and
cannot import this module) -- and re-exported here since this is where
callers have always imported them from. Callers use attribute access
(``result.decision``, ``result.reason``, etc.) -- as of TOO-45 R1a neither
``RuntimeVerdict`` nor ``UnitVerdict`` supports tuple unpacking (``LevelMatch``
never did either); the ``__iter__`` compatibility shims that used to let
callers unpack the result as a bare 3-tuple were removed once their only
callers (8 test call sites) were converted to attribute access.
"""

from typing import List, Optional, Sequence, Tuple

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
from toolguard.normalization import expand_tilde
from toolguard.patterns import PatternType, match_pattern, parse_pattern
from toolguard.permission_resolution import (
    apply_parse_failure_floor,
    resolve_permission_detailed,
)
from toolguard.permissions import (
    check_hard_deny,
    decide_command_at_level_detailed,
    is_universal_pattern,
    resolve_allow_ask,
)


# ---------------------------------------------------------------------------
# File-path helpers (pure)
# ---------------------------------------------------------------------------


def _anchor_file_pattern(pattern: str, config, extended_syntax: bool) -> str:
    """
    Anchor a relative file-path permission pattern to the PROJECT ROOT.

    Per the project-root-relative-path rule, a relative file-path pattern (one not
    starting with ``/`` or ``~`` after any extended-syntax prefix) resolves against
    the project root regardless of which config level declared it. Absolute and
    ``~`` patterns are returned unchanged.

    Any extended-syntax prefix (``[glob]``/``[regex]``/``[native]``) is preserved:
    only the path body after the prefix is anchored. ``[regex]`` patterns are left
    untouched (a regex is not a path and must not be path-joined).

    Args:
        pattern: A file-path permission pattern (wrapper already stripped).
        config: The resolved :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        The pattern with its path body anchored to the project root when relative.
    """
    prefix = ""
    body = pattern
    if extended_syntax:
        for known in ("[glob]", "[regex]", "[native]"):
            if pattern.startswith(known):
                prefix = known
                body = pattern[len(known) :]
                break
    # A regex pattern is not a filesystem path; never path-join it.
    if prefix == "[regex]":
        return pattern
    return prefix + config.resolve_config_path(body)


def _collapse_slashes(path_or_pattern: str) -> str:
    """
    Collapse runs of consecutive ``/`` into a single ``/``.

    Fixes patterns or paths that carry a redundant doubled slash (e.g.
    ``//Users/x`` -- common in rules copied from Claude's ``settings.local.json``)
    so they match the equivalent single-slash form. Only slash characters are
    affected; ``**`` globstar segments and other glob metacharacters are untouched.

    Args:
        path_or_pattern: A file path or a GLOB path pattern.

    Returns:
        The input with every run of consecutive slashes reduced to one.
    """
    while "//" in path_or_pattern:
        path_or_pattern = path_or_pattern.replace("//", "/")
    return path_or_pattern


def _match_file_path_pattern(
    pattern: str, expanded_path: str, extended_syntax: bool
) -> bool:
    """
    Match a file path against a single pattern, respecting extended syntax prefixes.

    DEFAULT patterns are treated as GLOB (backwards compatible with existing
    behaviour).  Extended prefixes (``[regex]``, ``[glob]``, ``[native]``) are
    honoured when ``extended_syntax`` is ``True``.

    Args:
        pattern: The (already anchored) permission pattern.
        expanded_path: The file path after tilde-expansion.
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        ``True`` when the pattern matches ``expanded_path``.
    """
    pattern_type, actual_pattern = parse_pattern(pattern, extended_syntax)

    # For file paths, DEFAULT patterns use the same semantics as GLOB
    if pattern_type == PatternType.DEFAULT:
        pattern_type = PatternType.GLOB

    # Collapse redundant slashes for GLOB matching so a pattern carrying a doubled
    # slash (e.g. '//Users/...') still matches the real single-slash path. Applied
    # to BOTH the pattern and the path so allow and deny stay consistent. Left
    # untouched for regex/native, where the exact characters are significant.
    if pattern_type == PatternType.GLOB:
        actual_pattern = _collapse_slashes(actual_pattern)
        expanded_path = _collapse_slashes(expanded_path)

    try:
        return match_pattern(pattern_type, actual_pattern, expanded_path)
    except ValueError, TypeError:
        return False


def _first_matching_file_pattern(
    patterns: List[str], expanded_path: str, config, extended_syntax: bool
) -> Tuple[bool, Optional[str]]:
    """Return ``(True, pattern)`` for the first file pattern that matches, else ``(False, None)``."""
    for pattern in patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return True, pattern
    return False, None


def _decide_file_path_at_level_detailed(
    file_path: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    config,
    extended_syntax: bool,
    ask_patterns: Optional[List[str]] = None,
) -> Optional[LevelMatch]:
    """
    Decide a file path's outcome at ONE config level, reporting the matched pattern.

    Mirrors :func:`toolguard.permissions.decide_command_at_level_detailed` for
    file-path tools so a matched file-path pattern can be mapped back to its
    source provenance by the provenance-aware resolver. Deny-first within the
    level; the allow and ask lists then combine by more-specific-wins (blanket
    ``*``-class ask patterns ignored) so an ask pattern yields an ``ask`` prompt.
    Relative patterns are anchored to the project root before matching.

    Args:
        file_path: The file path under evaluation.
        allow_patterns: This level's allow patterns (wrapper-free).
        deny_patterns: This level's deny patterns (wrapper-free).
        config: The resolved :class:`~toolguard.config.Configuration` (provides
            project-root anchoring).
        extended_syntax: Whether extended prefixes are honoured.
        ask_patterns: This level's ask patterns (wrapper-free).  Optional/defaulting
            to none so legacy callers keep their exact allow/deny behavior.

    Returns:
        A :class:`~toolguard.config_types.LevelMatch` when this level
        matches (TOO-45 R1f converted the bare ``(decision, reason,
        matched_pattern)`` tuple this used to return into this dataclass),
        else ``None``.
    """
    expanded_path = expand_tilde(file_path)

    for pattern in deny_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return LevelMatch(
                decision="deny",
                reason=f"Path matches deny pattern: {pattern}",
                matched_pattern=pattern,
            )

    allow_hit = _first_matching_file_pattern(
        allow_patterns, expanded_path, config, extended_syntax
    )

    ask_hit: Tuple[bool, Optional[str]] = (False, None)
    if ask_patterns:
        non_blanket_ask = [p for p in ask_patterns if not is_universal_pattern(p)]
        ask_hit = _first_matching_file_pattern(
            non_blanket_ask, expanded_path, config, extended_syntax
        )

    combined = resolve_allow_ask(allow_hit, ask_hit)
    if combined is None:
        return None
    decision, matched_pattern = combined
    return LevelMatch(
        decision=decision,
        reason=f"Path matches {decision} pattern: {matched_pattern}",
        matched_pattern=matched_pattern,
    )


def _hard_deny_additional_context(
    config, tool_name: str, matched_pattern: Optional[str]
) -> Optional[str]:
    """
    Look up the ``additionalContext`` of a matched ``[hard_deny]`` pattern.

    A hard deny IS the deciding match, and "why is this forbidden, and what
    should I do instead" is exactly where an explanation earns its keep, so
    both governed paths surface it: the file-path pool
    (:func:`_check_file_path_hard_deny`) and the per-sub-command Bash pool
    (:func:`resolve_bash_permission_detailed`). This is the single lookup they
    share, so the two cannot drift apart -- an asymmetry here would make any
    documentation of the feature wrong for one tool family or the other.

    TOO-45 R2c: searches
    :meth:`~toolguard.config.Configuration.hard_deny_entries` directly by
    each entry's :attr:`~toolguard.rule_entry.RuleEntry.stripped_pattern`,
    rather than locating ``matched_pattern`` in
    :meth:`~toolguard.config.Configuration.hard_deny`'s separately-returned
    stripped-pattern tuple and reading the entry off a second, parallel
    tuple at the same index. There is only one pooled call
    (``hard_deny_entries``) and one collection to search, so there is no
    longer a second collection its result could drift out of alignment
    with.

    Enrichment is cosmetic: every failure to resolve it degrades to ``None``
    and never affects the deny itself.

    Args:
        config: The resolved :class:`~toolguard.config.Configuration`.
        tool_name: The governed tool whose hard-deny pool was matched.
        matched_pattern: The wrapper-stripped pattern that matched, or
            ``None`` when the caller could not recover it.

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


def _check_file_path_hard_deny(
    tool_name: str, file_path: str, config, extended_syntax: bool
) -> Optional[LevelMatch]:
    """
    Apply the unoverridable hard-deny rule to a file path, checked FIRST.

    The pooled ``[hard_deny]`` (deny, allow) patterns for ``tool_name`` are
    collected across ALL levels (see
    :meth:`~toolguard.config.Configuration.hard_deny`). The path is hard-denied
    when it matches any hard-deny ``deny`` pattern AND does NOT match a hard-deny
    ``allow`` carve-out. Relative patterns are anchored to the project root, the
    same as normal file-path patterns.

    TOO-45 R1f: the matched pattern is now reported as its own
    ``LevelMatch.matched_pattern`` field, mirroring
    :func:`toolguard.permissions.check_hard_deny`'s Bash-side convention,
    instead of this function looking up the ``additionalContext`` enrichment
    (TOO-19 Phase 1) itself and returning that. The caller
    (:func:`resolve_file_path_permission_detailed`) now does that lookup via
    :func:`_hard_deny_additional_context`, exactly mirroring how
    :func:`resolve_bash_permission_detailed`'s ``_decide`` closure already
    does it for the Bash side -- one fewer asymmetry between the two
    hard-deny paths. Before R1f the matched pattern itself was discarded
    here (a TOO-45 R3 comment at the call site explained why closing that
    gap was out of R3's scope); this does NOT change the caller's final
    ``RuntimeVerdict.matched_rule``, which deliberately still stays
    ``None`` for a file-path hard-deny -- see that call site's own comment.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: The resolved :class:`~toolguard.config.Configuration` (provides
            hard_deny pool + anchoring).
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        A :class:`~toolguard.config_types.LevelMatch` with
        ``decision='deny'`` and ``matched_pattern`` set to the matched
        hard-deny pattern when the path is hard-denied, otherwise ``None``
        so the caller falls through to the normal more-specific-wins
        cascade.
    """
    deny_patterns, allow_patterns = config.hard_deny(tool_name)
    if not deny_patterns:
        return None

    expanded_path = expand_tilde(file_path)

    matched_deny = None
    for pattern in deny_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            matched_deny = pattern
            break

    if matched_deny is None:
        return None

    # A hard-deny matched. An allow carve-out exempts the path from the hard deny.
    for pattern in allow_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return None

    return LevelMatch(
        decision="deny",
        reason=f"Path matches hard_deny pattern: {matched_deny} (cannot be overridden)",
        matched_pattern=matched_deny,
    )


def resolve_file_path_permission_detailed(
    tool_name: str,
    file_path: str,
    config: ResolveConfig,
    extended_syntax: bool = True,
) -> "RuntimeVerdict":
    """
    Resolve a file-path tool decision using more-specific-wins across levels.

    The unoverridable ``[hard_deny]`` pool is checked FIRST (see
    :func:`_check_file_path_hard_deny`); a hard-deny match denies immediately and
    cannot be overridden by any level's normal allow. Otherwise this drives the
    hard-deny-first, more-specific-wins cascade via
    :func:`~toolguard.permission_resolution.resolve_permission_detailed`, applying
    deny-first within each level and project-root anchoring to relative patterns.
    The first level that matches anything decides; no match at any level =>
    fail-closed deny. Returns the allow-over-deny override (if any) so the caller
    can log it to the conflict stream. Reasons carry the winning rule's provenance
    as a bracketed suffix.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: The resolved configuration -- typed as
            :class:`~toolguard.config_types.ResolveConfig` (TOO-45 D2
            follow-up), in practice always a real
            :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` carrying ``decision``,
        ``reason``, ``overrides`` (0 or 1 ``(file_path, ConflictOverride)``
        pairs -- see that class's docstring for why file-path resolution is
        never compound), ``provenance`` (the winning rule's
        :class:`~toolguard.config.Provenance`, or ``None`` for a hard-deny or
        fail-closed default deny), ``additional_context`` (the winning rule's
        ``additionalContext`` enrichment text, word-capped via
        :func:`~toolguard.compound.cap_context_words` -- TOO-19 code review
        M2 -- or ``None``), ``fallback_warning`` (TOO-19
        allow/allow_with_no_warnings work; ``True`` only for an 'allow'
        produced by ``no_match_fallback='allow_with_warning'``), and
        ``tool``/``target`` set to *tool_name*/*file_path* (TOO-45 R1c;
        unconsumed until R1d).
    """
    hard = _check_file_path_hard_deny(tool_name, file_path, config, extended_syntax)
    if hard is not None:
        return RuntimeVerdict(
            decision=hard.decision,
            reason=hard.reason,
            provenance=None,
            # TOO-45 R1f: `_check_file_path_hard_deny` now reports its
            # matched pattern in `hard.matched_pattern` instead of computing
            # this lookup internally (mirroring how
            # `resolve_bash_permission_detailed`'s `_decide` closure already
            # does it for the Bash side).
            additional_context=cap_context_words(
                _hard_deny_additional_context(config, tool_name, hard.matched_pattern)
            ),
            # TOO-45 R3: even though `hard.matched_pattern` is available here
            # as of R1f, `matched_rule` stays None deliberately -- R1f is a
            # structural tuple-to-dataclass conversion only, not the R3 fix
            # (closing this was explicitly out of R3's scope per the
            # ticket). Populating it would change this verdict's
            # `matched_rule` field, which the corpus track as part of "no
            # verdict may change." NOTE: this means
            # `_log_non_allow_decision`'s "Violated Rules" log entry for a
            # file-path hard-deny falls through to the FULL reason text
            # (e.g. "Path matches hard_deny pattern: X (cannot be
            # overridden)") rather than the OLD colon-split extraction
            # ("X (cannot be overridden)") -- more verbose, not fabricated,
            # and outside the corpus's tracked fields (log content, not the
            # hook's JSON reason) -- see the R3 implementation report.
            matched_rule=None,
            tool=tool_name,
            target=file_path,
        )

    def _decide_detailed(
        allow_patterns: Sequence[str],
        deny_patterns: Sequence[str],
        ask_patterns: Sequence[str],
    ) -> Optional[LevelMatch]:
        """
        Adapt this level's pattern triple to
        :func:`_decide_file_path_at_level_detailed`'s own, differently-shaped
        signature -- this closure's own type (not its body) is what
        satisfies :class:`~toolguard.config_types.DecideDetailed`, the
        contract :func:`~toolguard.permission_resolution.resolve_permission_detailed`
        (below) requires of its callback.
        """
        return _decide_file_path_at_level_detailed(
            file_path,
            list(allow_patterns),
            list(deny_patterns),
            config,
            extended_syntax,
            ask_patterns=list(ask_patterns),
        )

    # TOO-45 R3: `subject="Path"` gets the no-match-fallback reason phrased
    # correctly AT THE SOURCE (see `_resolve_unclamped`'s `subject` param)
    # instead of resolving with the Bash-phrased ("Command...") default and
    # rewriting the prefix here by parsing it back out of `resolved.reason`
    # -- the R3 violation this replaced (`reason.startswith(_no_match_prefix)`).
    resolved = resolve_permission_detailed(
        config, tool_name, _decide_detailed, subject="Path"
    )
    # `resolved.overrides` (the internal per-level verdict) pairs its bare
    # override with identifier None -- see RuntimeVerdict's docstring
    # ("overrides" reconciliation). Re-pair with the real identifier (the
    # file path itself) now that it is known.
    overrides = [(file_path, override) for _, override in resolved.overrides]
    return RuntimeVerdict(
        decision=resolved.decision,
        reason=resolved.reason,
        provenance=resolved.provenance,
        overrides=overrides,
        additional_context=cap_context_words(resolved.additional_context),
        fallback_warning=resolved.fallback_warning,
        # TOO-45 R3: already in hand on `resolved` -- no need for a caller to
        # parse it back out of `reason`.
        matched_rule=resolved.matched_rule,
        tool=tool_name,
        target=file_path,
    )


# ---------------------------------------------------------------------------
# Bash / command-tool resolver (pure)
# ---------------------------------------------------------------------------


def _deciding_sub_match(
    decision: str, sub_matches: List[UnitVerdict]
) -> Optional[UnitVerdict]:
    """
    Find the sub-command whose own decision produced a compound Bash verdict.

    Returns the FIRST sub-command (extraction order) whose recorded decision
    equals the compound's *decision*. Checked for every decision, including a
    single leaf: a floor (the ASK floor for foreign inline code, or
    ``undecidable_fallback``) can override a leaf's own verdict, in which
    case that leaf did not decide and must not be credited with a rule it
    didn't win on -- e.g. `python -c "..."` resolves 'allow' via `python *`,
    the floor makes it 'ask', and the audit log must not name `python *` as
    the deciding rule.

    For a genuinely multi-leaf ALL-allow compound there is no single
    decider -- every leaf had to allow for the compound to allow -- so this
    returns ``None``; per-sub-command detail is still available on
    ``sub_matches`` itself for callers that need it (see
    ``hook.py::_log_allowed_command``).

    TOO-45 R1e: this now ALWAYS agrees with whichever sub-command
    ``_combine_strictest`` surfaced in the reason, because ``sub_matches`` no
    longer holds a stale, PRE-floor entry for an ASK-floor leaf (foreign
    inline/heredoc code). TOO-45 compound/resolve cycle removal:
    :func:`~toolguard.compound.judge_unit` BUILDS that leaf's/segment's
    :class:`UnitVerdict` as its TRUE final decision/matched_rule/provenance
    in the first place (there is no separate stub-then-correct step any
    more -- the driver loop above appends ``judge_unit``'s own return value
    directly for a unit where ``unit.audits_as_one`` is ``True``), instead of
    ever recording the truncated outer-command stub's own pre-floor cascade
    result. Example: `ls && python -c "print(1)"` under
    ``undecidable_fallback=deny`` -- ``sub_matches`` now correctly records
    'deny' for the ``python -c`` leaf (not 'allow', the stub's own match),
    so this function finds it and attributes the compound's 'deny' to that
    leaf, with ``matched_rule``/``provenance`` both ``None`` (an escape
    hatch, not a genuine deny match).

    Before R1e, an ASK-floor leaf whose pre-floor stub decision happened to
    EQUAL the compound's final decision (single-leaf `python -c "..."` under
    `allow_with_warning`/`allow`: the stub's real `python *` match already
    said 'allow', same as the floored result) made this function return that
    leaf's real, misleading ``UnitVerdict`` -- decision equality alone could
    not tell "the rule decided" from "the escape hatch decided and a rule
    happened to also match the stub". That case is now equally covered: the
    leaf's ``UnitVerdict.matched_rule`` is ``None`` at the source (TOO-45
    R1e), so this function's return is correct without help from a
    downstream reason-text re-check.  ``hook.py``'s deny/ask logging
    (``_log_non_allow_decision``) still classifies *reason* via
    ``compound.fallback_kind_for_reason`` before choosing the placeholder --
    that remains a RENDERING choice (which text the human sees), not a data-
    correctness workaround this function's callers still need.

    The ALLOW branch's "single decider" test (TOO-45 R1e finishing pass):
    ``len(sub_matches) == 1`` is no longer the right proxy for "there is one
    decider", now that :mod:`~toolguard.compound` correctly records a
    :class:`UnitVerdict` for EVERY leaf/segment, including escape-hatch ones
    that never call ``_decide`` at all (an :class:`UndecidableSegment`,
    or an ASK-floor leaf that allowed via the floor rather than a rule). A
    two-element compound like ``diff <(cat a) <(cat b) && ls -la`` now
    legitimately has TWO ``sub_matches`` entries (the undecidable ``diff``
    segment and the real ``ls -la`` match), where before this fix the
    undecidable segment produced no entry at all and ``len() == 1``
    accidentally held. The right test is not "exactly one entry" but
    "exactly one entry that is a GENUINE rule match" -- ``matched_rule is not
    None`` is that signal: every escape-hatch entry (``undecidable_fallback``
    or ``no_match_fallback``) always records ``matched_rule=None`` at the
    source (see :class:`UnitVerdict`'s ``matched_rule`` docstring), so an
    ambient escape-hatch companion never competes for attribution. When
    exactly one genuine match exists among possibly several allowed
    sub_matches (some escape-hatch, some genuine), it is correctly named
    the compound's decider, exactly as it would be if it were the ONLY
    allowed leaf. When two or more genuine matches exist (e.g.
    ``git status && ls -la``, no escape hatch involved), there is still no
    single decider -- every leaf's OWN rule had to allow -- so this
    continues to return ``None``, unchanged from before this fix. A single
    ask-floor leaf that allowed ENTIRELY via the escape hatch (e.g. a
    command classified as foreign inline/heredoc code with no underlying
    rule match at all) has zero genuine entries, so this also correctly
    returns ``None`` -- restoring a rule name here would resurrect exactly
    the fabrication ``_combine_strictest``'s "Fabrication guard" note
    describes (attributing the compound's allow to the truncated stub's own
    match when the escape hatch, not that rule, is what actually decided).

    Args:
        decision: The compound's final decision, AFTER the parse-failure
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
    Resolve a (possibly compound) Bash command with provenance and conflicts.

    Each extracted sub-command is resolved independently through the
    provenance-aware more-specific-wins cascade
    (:func:`~toolguard.permission_resolution.resolve_permission_detailed`), with
    the unoverridable ``[hard_deny]`` pool checked FIRST per sub-command. The
    compound decision uses the same strictness :func:`toolguard.compound._combine_strictest`
    always has (any deny -> deny; else any ask -> ask; else allow). Reasons
    carry the winning rule's provenance.

    Allow-over-deny overrides discovered on any sub-command (only meaningful when
    the overall decision is allow) are returned so the caller can log them to the
    conflict stream. ``hard_deny`` denials are NOT conflicts.

    Foreign inline code / heredoc sinks and undecidable segments (control
    structures, process substitution) that cannot be safely decomposed are
    floored per ``config.resolved_undecidable_fallback()`` (TOO-19; ``'ask'``
    by default) -- see :func:`toolguard.compound.judge_unit`. TOO-45 compound/
    resolve cycle removal: this function drives
    :func:`toolguard.compound.decompose`/:func:`toolguard.compound.judge_unit`/
    :func:`toolguard.compound._combine_strictest` directly (see the ``_decide``
    closure and the driver loop below) -- it does NOT call
    :func:`toolguard.compound.resolve_compound_permission_detailed`, which
    remains a convenience driver over the same three functions for callers
    with only a plain ``resolve_one`` closure (tests, and
    :func:`toolguard.compound.check_compound_permission`).

    Per-sub-command provenance is recorded in the returned
    :class:`~toolguard.config_types.RuntimeVerdict`\\ 's ``sub_matches`` list
    (one :class:`UnitVerdict` per sub-command, in order).

    Args:
        command: The bash command line (may be compound).
        config: The resolved configuration -- typed as
            :class:`~toolguard.config_types.ResolveConfig` (TOO-45 D2
            follow-up), in practice always a real
            :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.
        hard_deny_deny: Pooled hard-deny deny patterns for Bash.
        hard_deny_allow: Pooled hard-deny allow (carve-out) patterns for Bash.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` with ``decision``,
        ``reason``, ``overrides`` (list of ``(sub_command, ConflictOverride)``
        pairs, empty when none), ``sub_matches`` (one :class:`UnitVerdict` per
        extracted sub-command), ``additional_context`` (the accumulated
        ``additionalContext`` enrichment text, TOO-19 Phase 1, word-capped via
        :func:`~toolguard.compound.cap_context_words` -- TOO-19 code review
        M2 -- or ``None``), and ``fallback_warning`` (TOO-19
        allow/allow_with_no_warnings work; ``True`` only for an 'allow' with
        at least one contributing sub-command whose verdict came from the
        WARNED value of ``no_match_fallback`` or ``undecidable_fallback`` --
        TOO-19 code review M1). Propagated directly from
        :func:`toolguard.compound._combine_strictest`'s own
        structured ``fallback_warning``, computed from a per-sub-command tag
        rather than re-derived by searching the FINAL (possibly multi-leaf
        summarised) reason text for a marker substring -- the latter is what
        previously let a multi-leaf all-allow compound silently lose its
        warning (and, separately, misattribute the allow to a fabricated
        rule name in the log) when the escape hatch fired on only one of
        several allowed leaves. Also carries ``matched_rule`` and
        ``provenance``, both sourced from :func:`_deciding_sub_match` (the
        single sub-command whose own decision produced the compound verdict,
        or ``None`` when there is none to attribute), and ``tool``/``target``
        set to ``'Bash'``/*command* (TOO-45 R1c; unconsumed until R1d --
        ``tool`` is always the literal ``'Bash'`` here regardless of the
        actual invoking tool name, matching this function's existing
        convention of always evaluating against the Bash rule set).
    """
    overrides: List[Tuple[str, ConflictOverride]] = []
    sub_matches: List[UnitVerdict] = []

    def _decide(sub_command: str) -> Tuple[UnitVerdict, Optional[ConflictOverride]]:
        """
        Per-sub-command decision: hard-deny first, then the cascade. Records nothing.

        Side-effect-free in the sense callers depend on (no logging,
        sub_matches/overrides mutation, or recursion into this function),
        but NOT pure in the strict sense -- like every resolver in this
        module (see this module's own docstring, TOO-45 R6-S2), pattern
        matching reads live filesystem state via ``normalization.py``'s
        ``exists()``/``is_symlink()``/``resolve()``. An earlier draft of this
        docstring, and TOO-45's own compound-cycle plan, called this function
        "already pure" -- that claim was already retracted once at the module
        level and is not repeated here.

        TOO-45 compound/resolve cycle removal (step 4): returns a strict
        ``(UnitVerdict, Optional[ConflictOverride])`` pair instead of the
        former 7-tuple -- ``UnitVerdict`` already carries every field the
        tuple did (``decision``/``reason``/``additional_context``/
        ``matched_rule``/``provenance``/``fallback_kind``); only ``override``
        genuinely has nowhere else to live, so it stays a second, explicit
        return value rather than being smuggled onto ``UnitVerdict`` itself
        (which is a shared, published record -- audit/log/corpus code reads
        it -- not a scratch pad for this function's own internal plumbing). A
        strict pair is fine per this project's convention (see
        ``tools/architecture_fitness.py``'s ``find_bare_verdict_tuples``,
        which does not flag one) and needs no adapter: this function is
        called directly by the driver loop below, never by a test closure
        with a fixed-shape contract to preserve.

        Args:
            sub_command: The individual sub-command string to decide.

        Returns:
            The sub-command's :class:`~toolguard.config_types.UnitVerdict`
            (``fallback_kind`` computed purely structurally -- an 'allow'
            with ``matched_rule`` left ``None`` can ONLY have fallen through
            to ``no_match_fallback``, see ``permission_resolution.py``'s
            ``_resolve_unclamped`` -- never by parsing *reason*), paired with
            the allow-over-deny :class:`~toolguard.config_types.ConflictOverride`
            discovered while resolving it, or ``None`` when there was none.
        """
        hard = check_hard_deny(
            sub_command, list(hard_deny_deny), list(hard_deny_allow), extended_syntax
        )
        if hard is not None:
            # TOO-19 code review m3: check_hard_deny now returns the matched
            # pattern as its own field (a LevelMatch as of TOO-45 R1f) rather
            # than requiring recovery by stripping a fixed prefix/suffix off
            # the reason string -- that round-trip was already fragile for
            # UnitVerdict.matched_rule and would otherwise ALSO have to be
            # load-bearing for _hard_deny_additional_context below. A
            # hard-deny match is always a genuine attribution, never a
            # fallback escape hatch.
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
                    fallback_kind=None,
                ),
                None,  # override
            )

        def _decide_detailed(
            allow_patterns: Sequence[str],
            deny_patterns: Sequence[str],
            ask_patterns: Sequence[str],
        ) -> Optional[LevelMatch]:
            """
            Adapt this level's pattern triple to
            :func:`~toolguard.permissions.decide_command_at_level_detailed`'s
            own, differently-shaped signature -- see the file-path resolver's
            twin closure (above, in
            :func:`resolve_file_path_permission_detailed`) for why this
            closure's TYPE is what satisfies
            :class:`~toolguard.config_types.DecideDetailed`.
            """
            return decide_command_at_level_detailed(
                sub_command,
                list(allow_patterns),
                list(deny_patterns),
                extended_syntax,
                ask_patterns=list(ask_patterns),
            )

        resolved = resolve_permission_detailed(config, "Bash", _decide_detailed)
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

    # TOO-45 compound/resolve cycle removal (step 4): drives
    # compound.decompose/judge_unit/_combine_strictest directly instead of
    # calling compound.resolve_compound_permission_detailed with injected
    # resolve_one/resolve_outer/record_unit callbacks -- this IS the cycle
    # removal: compound.py no longer calls back into this module at all
    # (verified by profiling one real decision; see the implementation
    # report). sub_matches/overrides are populated by ordinary
    # append/extend on the visible lines below, not by a closure's side
    # effect.
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
                # `resolved.overrides` (the internal per-level verdict) pairs
                # its bare override with identifier None -- see
                # RuntimeVerdict's docstring ("overrides" reconciliation).
                # Re-pair with the real sub_command identifier now that it is
                # known. Gated on `not unit.audits_as_one` (TOO-45 compound-
                # cycle judgment R1) so an 'inline_code' unit's outer-stub
                # probe -- a check for an explicit deny, not a real
                # per-sub-command decision -- never contributes a conflict-log
                # entry of its own; only ever true for 'plain' in practice
                # (the only kind with a genuine allow-over-deny concept), but
                # reading the SAME field that governs sub_matches recording
                # keeps the two rules from drifting apart.
                overrides.append((part, override))
        judged = judge_unit(unit, part_verdicts, config.resolved_undecidable_fallback())
        unit_verdicts.append(judged)
        # A plain unit's audit entries are its own sub-commands. A floored or
        # undecidable unit is audited as ONE entry, because the floor -- not
        # any part's rule match -- is what decided it (TOO-45 R1e). Read from
        # unit.audits_as_one (set by decompose, TOO-45 compound-cycle
        # judgment R1) rather than re-derived from unit.kind here: a fifth
        # kind cannot be added to CommandUnit without deciding this field, so
        # this driver cannot silently under-audit it the way a
        # `unit.kind == "plain"` check could.
        if unit.audits_as_one:
            sub_matches.append(judged)
        else:
            sub_matches.extend(part_verdicts)

    if not units:
        # Mirrors compound.resolve_compound_permission_detailed's own empty-
        # command guard exactly (same reason text) -- decompose(command)
        # returning [] means _combine_strictest would otherwise see an empty
        # list and report its own, different "No commands to evaluate"
        # wording.
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

    # TOO-19 fail-open fix: re-apply the parse-failure ASK floor HERE, at the
    # compound boundary, in addition to the per-sub-command application
    # inside _decide (via resolve_permission_detailed). This second
    # application is not redundant: the compound driver above can produce a
    # verdict from a grammar-level undecidable unit (process substitution,
    # `case`, unparseable control structures -- see
    # toolguard/parser/multiline.py) which has NO parts and therefore never
    # calls _decide at all, so the per-part floor never runs for it. Only
    # this call site sees the final compound decision regardless of how it was
    # produced, so it is the only place that can cover that gap. Re-applying
    # to a decision that already passed through the per-leaf floor is a
    # deliberate no-op (the clamp is idempotent: an 'ask' stays 'ask', a
    # 'deny' is never weakened) -- do NOT remove this call as "redundant" with
    # the per-leaf one; that would silently reopen the undecidable-segment
    # bypass this fix closes.
    decision, reason = apply_parse_failure_floor(
        config.parse_failures, decision, reason
    )

    # Only allow-over-deny overrides on an ALLOWED command are conflicts; if the
    # overall decision is a deny, the recorded overrides are irrelevant. The
    # parse-failure floor can also clamp 'allow' down to 'ask' -- when it
    # does, fallback_warning must drop too (mirrors
    # permission_resolution._apply_ask_floor's handling of the
    # single-decision case), or a since-overridden verdict would still claim
    # to warrant a WARNING-stream entry.
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
