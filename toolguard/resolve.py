"""
Pure, side-effect-free permission resolver layer for toolguard.

This module is the canonical, single source of truth for the core permission
resolution algorithms.  It contains ONLY functions that are:

- Pure (no logging, no stdin/stdout, no ``sys.exit``).
- Self-contained at their level (they may import ``config``, ``permissions``,
  ``compound``, ``patterns``, and ``normalization``; they do NOT import
  ``hook``).

Both the live hook (``toolguard.hook``) and the replay / tooling layer
(``toolguard.tools.decision``) import from here, ensuring that what the hook
decides at runtime is EXACTLY what the replay computes -- there is no separate
copy of the logic to drift.

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
:class:`SubMatch` records one sub-command's outcome inside a compound Bash
resolution.  :class:`BashResolution` and :class:`FileResolution` are the
structured return types from the two public resolver functions.  They replace
the bare 3-tuples so provenance can be threaded through to callers without
widening the tuple or adding positional-arg confusion.

Backwards compatibility
-----------------------
``hook.py`` previously unpacked the results as 3-tuples
(``decision, reason, overrides``/``override``).  The new dataclasses expose
those same fields as attributes *and* still support attribute access with the
same names; the hook is updated to use attribute access so no behaviour changes.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from toolguard.compound import resolve_compound_permission
from toolguard.normalization import expand_tilde
from toolguard.patterns import PatternType, match_pattern, parse_pattern
from toolguard.permissions import (
    check_hard_deny,
    decide_command_at_level_detailed,
    is_universal_pattern,
    resolve_allow_ask,
)


# ---------------------------------------------------------------------------
# Result dataclasses (public, importable by decision.py)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubMatch:
    """
    Per-sub-command resolution record inside a compound Bash permission check.

    Callers (e.g. :func:`toolguard.tools.decision._decide_bash`) can use
    ``sub_matches`` to identify WHICH sub-command of a compound command produced
    the verdict (first deny => compound deny, first ask => compound ask, else
    allow) and to surface per-sub-command provenance to tooling.

    Attributes:
        sub_command: The individual sub-command string as extracted by the
            compound splitter.
        decision: The decision for this sub-command: ``'allow'``, ``'ask'``, or
            ``'deny'``.
        matched_rule: The winning rule pattern string (wrapper-free, as stored in
            the layer) if one matched, or the hard-deny pattern string when the
            sub-command was hard-denied.  ``None`` when no rule matched (default
            fail-closed deny).
        provenance: Origin of the layer whose rule matched, or ``None`` for a
            hard-deny (pooled across levels, no single provenance) or a
            fail-closed default deny.
    """

    sub_command: str
    decision: str
    matched_rule: Optional[str]
    provenance: Optional[Any]  # Optional[Provenance] -- Any avoids a circular import


@dataclass(frozen=True)
class BashResolution:
    """
    Full result of :func:`resolve_bash_permission_detailed`.

    Backwards-compatible iteration
    ------------------------------
    ``__iter__`` yields ``(decision, reason, overrides)`` so legacy callers that
    unpack the return value as a 3-tuple continue to work unchanged.  New callers
    should use attribute access (``result.decision``, ``result.sub_matches``, etc.)
    for clarity.

    Attributes:
        decision: Compound verdict: ``'allow'``, ``'ask'``, or ``'deny'``.
        reason: Human-readable reason for the compound decision (provenance
            suffix already appended by the cascade for the deciding sub-command).
        overrides: List of ``(sub_command, ConflictOverride)`` pairs for
            sub-commands where a more-specific allow overrode a less-specific
            deny.  Empty when the overall decision is not ``'allow'``.
        sub_matches: One :class:`SubMatch` per extracted sub-command, in order.
            Allows callers to identify the deciding sub-command and its
            provenance/matched-rule without re-running the resolver.
    """

    decision: str
    reason: str
    overrides: List[Tuple[str, Any]]
    sub_matches: List[SubMatch] = field(default_factory=list)

    def __iter__(self):
        """
        Yield ``(decision, reason, overrides)`` for backwards-compatible 3-tuple unpacking.

        Legacy callers that unpack as ``decision, reason, overrides = resolver(...)``
        continue to work without modification.
        """
        yield self.decision
        yield self.reason
        yield self.overrides


@dataclass(frozen=True)
class FileResolution:
    """
    Full result of :func:`resolve_file_path_permission_detailed`.

    Backwards-compatible iteration
    ------------------------------
    ``__iter__`` yields ``(decision, reason, override)`` so legacy callers that
    unpack the return value as a 3-tuple continue to work unchanged.  New callers
    should use attribute access (``result.decision``, ``result.provenance``, etc.)
    for clarity.

    Attributes:
        decision: ``'allow'`` or ``'deny'``.
        reason: Human-readable reason (provenance suffix already appended by
            the cascade when a rule matched).
        override: A :class:`~toolguard.config.ConflictOverride` when a
            more-specific allow overrode a less-specific deny, otherwise
            ``None``.  A ``hard_deny`` match also returns ``None`` here.
        provenance: The winning rule's provenance, or ``None`` for a hard-deny
            or a fail-closed default deny (no rule matched).
    """

    decision: str
    reason: str
    override: Optional[Any]  # Optional[ConflictOverride]
    provenance: Optional[Any]  # Optional[Provenance]

    def __iter__(self):
        """
        Yield ``(decision, reason, override)`` for backwards-compatible 3-tuple unpacking.

        Legacy callers that unpack as ``decision, reason, override = resolver(...)``
        continue to work without modification.  ``provenance`` is NOT yielded as
        it is a new field; access it as ``result.provenance``.
        """
        yield self.decision
        yield self.reason
        yield self.override


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
                body = pattern[len(known):]
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
):
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
        ``(decision, reason, matched_pattern)`` when this level matches, else
        ``None``.
    """
    expanded_path = expand_tilde(file_path)

    for pattern in deny_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return "deny", f"Path matches deny pattern: {pattern}", pattern

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
    return (
        decision,
        f"Path matches {decision} pattern: {matched_pattern}",
        matched_pattern,
    )


def _check_file_path_hard_deny(
    tool_name: str, file_path: str, config, extended_syntax: bool
):
    """
    Apply the unoverridable hard-deny rule to a file path, checked FIRST.

    The pooled ``[hard_deny]`` (deny, allow) patterns for ``tool_name`` are
    collected across ALL levels (see
    :meth:`~toolguard.config.Configuration.hard_deny`). The path is hard-denied
    when it matches any hard-deny ``deny`` pattern AND does NOT match a hard-deny
    ``allow`` carve-out. Relative patterns are anchored to the project root, the
    same as normal file-path patterns.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: The resolved :class:`~toolguard.config.Configuration` (provides
            hard_deny pool + anchoring).
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        ``('deny', reason)`` when the path is hard-denied, otherwise ``None`` so
        the caller falls through to the normal more-specific-wins cascade.
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

    return (
        "deny",
        f"Path matches hard_deny pattern: {matched_deny} (cannot be overridden)",
    )


def resolve_file_path_permission_detailed(
    tool_name: str, file_path: str, config, extended_syntax: bool = True
) -> "FileResolution":
    """
    Resolve a file-path tool decision using more-specific-wins across levels.

    The unoverridable ``[hard_deny]`` pool is checked FIRST (see
    :func:`_check_file_path_hard_deny`); a hard-deny match denies immediately and
    cannot be overridden by any level's normal allow. Otherwise this drives the
    hard-deny-first, more-specific-wins cascade via
    :meth:`~toolguard.config.Configuration.resolve_permission_detailed`, applying
    deny-first within each level and project-root anchoring to relative patterns.
    The first level that matches anything decides; no match at any level =>
    fail-closed deny. Returns the allow-over-deny override (if any) so the caller
    can log it to the conflict stream. Reasons carry the winning rule's provenance
    as a bracketed suffix.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: The resolved :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        A :class:`FileResolution` carrying ``decision``, ``reason``,
        ``override`` (:class:`~toolguard.config.ConflictOverride` or ``None``),
        and ``provenance`` (the winning rule's
        :class:`~toolguard.config.Provenance`, or ``None`` for a hard-deny or
        fail-closed default deny).
    """
    hard = _check_file_path_hard_deny(tool_name, file_path, config, extended_syntax)
    if hard is not None:
        decision, reason = hard
        return FileResolution(decision=decision, reason=reason, override=None, provenance=None)

    def _decide_detailed(allow_patterns, deny_patterns, ask_patterns):
        return _decide_file_path_at_level_detailed(
            file_path,
            list(allow_patterns),
            list(deny_patterns),
            config,
            extended_syntax,
            ask_patterns=list(ask_patterns),
        )

    resolved = config.resolve_permission_detailed(tool_name, _decide_detailed)
    reason = resolved.reason
    _no_match_prefix = "Command does not match any allow patterns"
    if reason.startswith(_no_match_prefix):
        # Normalise the "Command"-phrased no-match reason to file-path phrasing,
        # preserving any suffix (e.g. the TOO-15 'ask' or 'allow_with_warning'
        # no_match_fallback explanation).
        reason = "Path does not match any allow patterns" + reason[len(_no_match_prefix):]
    return FileResolution(
        decision=resolved.decision,
        reason=reason,
        override=resolved.override,
        provenance=resolved.provenance,
    )


# ---------------------------------------------------------------------------
# Bash / command-tool resolver (pure)
# ---------------------------------------------------------------------------


def resolve_bash_permission_detailed(
    command: str,
    config,
    extended_syntax: bool,
    hard_deny_deny,
    hard_deny_allow,
) -> "BashResolution":
    """
    Resolve a (possibly compound) Bash command with provenance and conflicts.

    Each extracted sub-command is resolved independently through the
    provenance-aware more-specific-wins cascade
    (:meth:`~toolguard.config.Configuration.resolve_permission_detailed`), with
    the unoverridable ``[hard_deny]`` pool checked FIRST per sub-command. The
    compound decision uses the same strictness as
    :func:`toolguard.compound.resolve_compound_permission` (any deny -> deny;
    else any ask -> ask; else allow). Reasons carry the winning rule's provenance.

    Allow-over-deny overrides discovered on any sub-command (only meaningful when
    the overall decision is allow) are returned so the caller can log them to the
    conflict stream. ``hard_deny`` denials are NOT conflicts.

    Per-sub-command provenance is recorded in the returned
    :class:`BashResolution`\\ 's ``sub_matches`` list (one :class:`SubMatch` per
    sub-command, in order).

    Args:
        command: The bash command line (may be compound).
        config: The resolved :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.
        hard_deny_deny: Pooled hard-deny deny patterns for Bash.
        hard_deny_allow: Pooled hard-deny allow (carve-out) patterns for Bash.

    Returns:
        A :class:`BashResolution` with ``decision``, ``reason``, ``overrides``
        (list of ``(sub_command, ConflictOverride)`` pairs, empty when none),
        and ``sub_matches`` (one :class:`SubMatch` per extracted sub-command).
    """
    overrides: List[Tuple[str, Any]] = []
    sub_matches: List[SubMatch] = []

    def _resolve_one(sub_command: str):
        """Resolve a single sub-command: hard-deny first, then cascade."""
        hard = check_hard_deny(
            sub_command, list(hard_deny_deny), list(hard_deny_allow), extended_syntax
        )
        if hard is not None:
            hard_decision, hard_reason = hard
            # Extract the matched hard-deny pattern from the reason string.
            # Reason format: "Command matches hard_deny pattern: <pattern> (cannot be overridden)"
            matched_rule: Optional[str] = None
            prefix = "Command matches hard_deny pattern: "
            suffix = " (cannot be overridden)"
            if hard_reason.startswith(prefix) and hard_reason.endswith(suffix):
                matched_rule = hard_reason[len(prefix) : -len(suffix)]
            sub_matches.append(
                SubMatch(
                    sub_command=sub_command,
                    decision=hard_decision,
                    matched_rule=matched_rule,
                    provenance=None,  # hard_deny is pooled; no single provenance
                )
            )
            return hard_decision, hard_reason

        def _decide_detailed(allow_patterns, deny_patterns, ask_patterns):
            return decide_command_at_level_detailed(
                sub_command,
                list(allow_patterns),
                list(deny_patterns),
                extended_syntax,
                ask_patterns=list(ask_patterns),
            )

        resolved = config.resolve_permission_detailed("Bash", _decide_detailed)
        if resolved.decision == "allow" and resolved.override is not None:
            overrides.append((sub_command, resolved.override))

        # Extract matched_rule from reason (format: "Command matches <kind> pattern: <rule>  [...]")
        sub_matched_rule: Optional[str] = None
        reason_body = resolved.reason
        # Strip the bracketed provenance suffix if present
        if "  [" in reason_body:
            reason_body = reason_body[: reason_body.rindex("  [")]
        for marker in (
            "Command matches allow pattern: ",
            "Command matches deny pattern: ",
            "Command matches ask pattern: ",
        ):
            if reason_body.startswith(marker):
                sub_matched_rule = reason_body[len(marker):]
                break

        sub_matches.append(
            SubMatch(
                sub_command=sub_command,
                decision=resolved.decision,
                matched_rule=sub_matched_rule,
                provenance=resolved.provenance,
            )
        )
        return resolved.decision, resolved.reason

    decision, reason = resolve_compound_permission(command, _resolve_one)

    # Only allow-over-deny overrides on an ALLOWED command are conflicts; if the
    # overall decision is a deny, the recorded overrides are irrelevant.
    if decision != "allow":
        overrides = []
    return BashResolution(
        decision=decision,
        reason=reason,
        overrides=overrides,
        sub_matches=sub_matches,
    )
