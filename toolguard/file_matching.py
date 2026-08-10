"""
File-path pattern matching for toolguard.

Extracted from :mod:`toolguard.resolve` (TOO-45 punch-list #03): matches a
filesystem path against glob-style (and extended-syntax) permission
patterns, including the path anchoring/normalisation helpers used only on
that path.

:func:`decide_file_path_at_level_detailed` and :func:`check_file_path_hard_deny`
are public: stage 2 wired :mod:`toolguard.permission_resolution` to import
:func:`decide_file_path_at_level_detailed` directly (the per-level matcher
the file-path cascade folds over), and ``resolve.py`` calls
:func:`check_file_path_hard_deny` directly -- both cross a module boundary,
so neither can stay private. ``_anchor_file_pattern``, ``_collapse_slashes``,
``_match_file_path_pattern``, and ``_first_matching_file_pattern`` have no
caller outside this module (production or test, TOO-45 punch-list #03
follow-up review measured it) and stay private.

The public entry point, :func:`~toolguard.resolve.resolve_file_path_permission_detailed`,
stays in ``resolve.py`` (it shares ``_hard_deny_additional_context`` with the
Bash resolver, so moving it here would require importing back from
``resolve.py`` -- exactly the cycle this punch-list removes).
"""

from typing import List, Optional, Tuple

from toolguard.config_types import LevelMatch, PathAnchoring, ResolveConfig
from toolguard.normalization import expand_tilde
from toolguard.patterns import PatternType, match_pattern, parse_pattern
from toolguard.permissions import is_universal_pattern, resolve_allow_ask


def _anchor_file_pattern(
    pattern: str, config: PathAnchoring, extended_syntax: bool
) -> str:
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
    patterns: List[str],
    expanded_path: str,
    config: PathAnchoring,
    extended_syntax: bool,
) -> Tuple[bool, Optional[str]]:
    """Return ``(True, pattern)`` for the first file pattern that matches, else ``(False, None)``."""
    for pattern in patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return True, pattern
    return False, None


def decide_file_path_at_level_detailed(
    file_path: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    config: PathAnchoring,
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
        config: Provides project-root anchoring -- see :class:`~toolguard.config_types.PathAnchoring`.
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


def check_file_path_hard_deny(
    tool_name: str, file_path: str, config: ResolveConfig, extended_syntax: bool
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
    (:func:`~toolguard.resolve.resolve_file_path_permission_detailed`) now
    does that lookup via
    :func:`~toolguard.resolve._hard_deny_additional_context`, exactly
    mirroring how :func:`~toolguard.resolve.resolve_bash_permission_detailed`'s
    ``_decide`` closure already does it for the Bash side -- one fewer
    asymmetry between the two hard-deny paths. Before R1f the matched
    pattern itself was discarded here (a TOO-45 R3 comment at the call site
    explained why closing that gap was out of R3's scope); this does NOT
    change the caller's final ``RuntimeVerdict.matched_rule``, which
    deliberately still stays ``None`` for a file-path hard-deny -- see that
    call site's own comment.

    Args:
        tool_name: ``'Read'``, ``'Write'``, or ``'Edit'``.
        file_path: The file path under evaluation.
        config: Provides the hard_deny pool + anchoring -- see
            :class:`~toolguard.config_types.ResolveConfig`.
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
