"""
Command string matching and permission decisions for the command-kind tools. The two
tie-break primitives -- :func:`is_universal_pattern` and :func:`resolve_allow_ask` -- are
also used by the file-path side; nothing else here is.

Matches a command against allow/deny/ask pattern lists -- DEFAULT fnmatch-style matching
plus the extended ``[regex]``/``[glob]``/``[native]`` syntax handled by
:mod:`toolguard.patterns`. Includes a bare allow/deny check (:func:`check_permission`),
the unoverridable hard-deny pool (:func:`check_hard_deny`), one hierarchy level of the
more-specific-wins cascade (:func:`decide_command_at_level_detailed`), and the
allow/ask tie-break primitives (:func:`resolve_allow_ask`, :func:`is_universal_pattern`)
that combine matches into a level's outcome.

No bash structure is parsed here -- commands arrive already decomposed by the grammar,
and the splitting this module does is token-level. Further spellings of one command --
notably the one with a leading ``NAME=value`` assignment removed -- arrive as a
:class:`~toolguard.config_types.CommandSpellings` built by
:func:`toolguard.parser.command_extractor.command_spellings`. Importing the parser here
instead fails the exact per-module import allow-list in ``test/unit/test_architecture.py``;
``.pyscn.toml`` puts both in one layer and permits it, so that test is what holds the line.
"""

import fnmatch
from typing import List, Optional, Sequence, Tuple

from .config_types import CommandSpellings, LevelMatch
from .patterns import parse_pattern, match_pattern, PatternType
from .normalization import expand_tilde_in_command, normalize_command, normalize_path


def normalize_path_in_command(
    command_str: str, *, resolve_symlinks: bool = True
) -> str:
    """
    Normalize a command's path arguments to canonical form.

    Delegates to :func:`~toolguard.normalization.normalize_command`, then also adds a
    ``./`` prefix to a command's argument string when it doesn't already look like a path
    (doesn't start with ``.``, ``/``, ``-``, or ``~``) -- e.g. ``'ls mydir'`` ->
    ``'ls ./mydir'`` -- covering a case that function does not normalize on its own.

    Args:
        command_str: The command string to normalize.
        resolve_symlinks: Forwarded to
            :func:`~toolguard.normalization.normalize_command`.

    Returns:
        The normalized command string.
    """
    result = normalize_command(command_str, resolve_symlinks=resolve_symlinks)

    parts = result.split(None, 1)
    if len(parts) == 2:
        cmd, args = parts
        if args and not args.startswith((".", "/", "-", "~")):
            result = f"{cmd} ./{args}"

    return result


def contains_path_component(command_str: str, component: str) -> bool:
    """
    Check whether *component* appears as a whole ``/``- or ``\\``-separated segment of any
    argument.

    E.g. ``component='.env'`` matches ``'cat .env'``, ``'cat dir/.env'``, and
    ``'cat .env/file'`` -- segments are compared whole, so this is not a substring search.

    Args:
        command_str: The command string to check.
        component: The path component to search for.

    Returns:
        True if *component* is found in any argument, False otherwise.
    """
    parts = command_str.split(None, 1)
    if len(parts) < 2:
        return False

    args = parts[1]
    for arg in args.split():
        path_parts = arg.replace("\\", "/").split("/")
        if component in path_parts:
            return True

    return False


def _matches_on_token_boundary(command_str: str, cmd_pattern: str) -> bool:
    """
    Match *command_str* against a DEFAULT ``cmd:*`` pattern's command part: the command
    must equal *cmd_pattern* or continue after it with a space, so the prefix ends on a
    token boundary.

    This is Claude Code's own ``Bash(x:*)`` == ``Bash(x *)`` semantics, where a trailing
    wildcard with a space before it requires a space or end-of-string -- ``git log:*``
    matches ``git log --oneline`` but not ``git logfoo``.
    """
    return fnmatch.fnmatch(command_str, cmd_pattern) or fnmatch.fnmatch(
        command_str, cmd_pattern + " *"
    )


def _command_variants(command_str: str) -> List[str]:
    """
    The spellings of *command_str* a DEFAULT pattern is matched against, deduplicated:
    raw, path-normalized, and path-normalized with symlinks resolved.

    The latter two diverge only under a symlink, and then they name different places --
    ``~/.claude/x`` through a symlinked ``.claude`` resolves under the link's target. Both
    are kept because a rule author may have written either spelling. The tilde-expanded
    spelling that lets an absolute-path rule see a ``~``-spelled command is added earlier,
    by :func:`match_command`'s own ``spellings`` loop, before this function ever runs.
    """
    variants = [command_str]
    for variant in (
        normalize_path_in_command(command_str, resolve_symlinks=False),
        normalize_path_in_command(command_str),
    ):
        if variant not in variants:
            variants.append(variant)
    return variants


def match_command(
    command_str: str,
    patterns: List[str],
    extended_syntax: bool = True,
    *,
    also_spelled: Sequence[str] = (),
) -> Tuple[bool, Optional[str]]:
    """
    Check whether *command_str* matches any pattern in *patterns*; return the first hit.

    Every pattern type is matched against *command_str*, against each entry of
    *also_spelled*, and against the tilde-expanded form of each -- so a rule naming a
    location by its absolute path under home still sees a command that names it with
    ``~``. Offering an alternative spelling to the DEFAULT branch alone would leave
    ``[regex]``/``[glob]``/``[native]`` denies bypassable by the very spelling the
    alternative exists to see past.

    A DEFAULT pattern (no ``[regex]``/``[glob]``/``[native]`` prefix) is checked first
    for a ``**/<component>/**`` shape -- before ``**`` is normalized down to ``*`` --
    matching when a spelling contains that literal path component anywhere
    (via :func:`contains_path_component`). Otherwise it is matched via ``fnmatch``
    against every path-normalization :func:`_command_variants` produces from each
    spelling -- as a boundary-checked ``cmd:*`` prefix when the pattern's ``**``-normalized
    end is ``:*`` (Claude Code's own rule: the ``:*`` shorthand is recognised only there, so a
    ``:`` anywhere else, e.g. inside a URL, is a literal character), or as a whole-string
    match otherwise. ``[regex]``/``[glob]``/``[native]`` patterns bypass all DEFAULT
    handling and match the spellings directly via :func:`~toolguard.patterns.match_pattern`.

    A leaf command that still contains a newline (should not normally happen after the
    multi-line pre-pass upstream) is excluded from DEFAULT matching, so a DEFAULT prefix
    allow cannot match a multi-statement blob this way. REGEX/GLOB/NATIVE patterns
    bypass this guard.

    Args:
        command_str: The command string to match.
        patterns: Patterns to match against, tried in order.
        extended_syntax: If False, skip parsing ``[regex]``/``[glob]``/``[native]`` prefixes.
        also_spelled: Further spellings of the same command to match -- whichever
            side of a :class:`~toolguard.config_types.CommandSpellings` suits
            *patterns*. Empty -- the default -- matches *command_str* alone, so a
            caller that omits it can neither widen a grant nor lose a restriction it
            had before.

    Returns:
        ``(matched, matched_pattern)``. ``matched_pattern`` is the RAW list element from
        *patterns*, extended-syntax prefix included -- not what
        :func:`~toolguard.patterns.parse_pattern` would extract.
        :func:`~toolguard.config_types.provenance_for_pattern` relies on this identity: it
        searches for a layer entry whose ``stripped_pattern`` equals this value, so
        returning a normalized/wrapper-stripped pattern here would silently break it.
    """
    command_has_newline = "\n" in command_str or "\r" in command_str
    spellings: List[str] = []
    # The GLOB branch of match_pattern expands '~' too, but only at the very start of
    # each side: this subsumes its command side, and leaves its pattern side as the
    # one route among [regex]/[glob]/[native] by which a '~'-spelled rule reaches an
    # absolutely-spelled command. A DEFAULT rule reaches it too, via _command_variants'
    # home collapse below.
    for spelling in (command_str, *also_spelled):
        for variant in (spelling, expand_tilde_in_command(spelling)):
            if variant not in spellings:
                spellings.append(variant)
    command_variants: List[str] = []
    for spelling in spellings:
        for variant in _command_variants(spelling):
            if variant not in command_variants:
                command_variants.append(variant)

    for pattern in patterns:
        pattern_type, actual_pattern = parse_pattern(pattern, extended_syntax)

        if pattern_type in (PatternType.REGEX, PatternType.GLOB, PatternType.NATIVE):
            if any(
                match_pattern(pattern_type, actual_pattern, spelling)
                for spelling in spellings
            ):
                return True, pattern
            continue

        if command_has_newline:
            # Defense-in-depth against a fail-open bypass: a leaf that still
            # contains a newline here must not be matched by DEFAULT rules.
            continue

        if actual_pattern.startswith("**/") and actual_pattern.endswith("/**"):
            component = actual_pattern[3:-3]
            if any(
                contains_path_component(spelling, component) for spelling in spellings
            ):
                return True, pattern
            continue

        pattern_normalized = actual_pattern.replace("**", "*")

        if pattern_normalized.endswith(":*"):
            # ':*' is recognised as the trailing-wildcard shorthand only when it is
            # this normalized pattern's end -- matching native's own rule. A ':'
            # anywhere else (mid-pattern, or inside a URL like 'http://') is a
            # literal character and falls through to the whole-string fnmatch below.
            cmd_pattern = pattern_normalized[: -len(":*")].strip()
            pattern_parts = cmd_pattern.split(None, 1)
            # pattern_parts is empty only for a bare ':*'/':**' pattern (cmd_pattern == ""
            # after stripping), giving base_cmd = "". That MATCHES an empty command_str or
            # one starting with a space (fnmatch("", "") is True) instead of raising
            # IndexError -- a silent fail-open on those two shapes, not "matches nothing".
            # It stays harmless because the command extractor upstream already strips
            # leading whitespace and never emits an empty leaf, so no real Bash invocation
            # reaches this branch that way; see docs/native-pattern-reference.md.
            base_cmd = pattern_parts[0] if pattern_parts else ""

            # A pattern's base command is normalized the same way a real
            # command is, so e.g. 'bin/x:*' and './bin/x:*' both canonicalize
            # to './bin/x' and match a command starting with either spelling.
            base_cmd_variants = [base_cmd]
            if "/" in base_cmd:
                normalized_base = normalize_path(base_cmd)
                if normalized_base != base_cmd:
                    base_cmd_variants.append(normalized_base)

            for cmd_var in command_variants:
                matched_base = any(
                    cmd_var.startswith(bc + " ") or cmd_var == bc
                    for bc in base_cmd_variants
                )
                if matched_base:
                    for bc in base_cmd_variants:
                        full_cmd_pattern = bc + cmd_pattern[len(base_cmd) :]
                        if _matches_on_token_boundary(cmd_var, full_cmd_pattern):
                            return True, pattern
        else:
            for cmd_var in command_variants:
                if fnmatch.fnmatch(cmd_var, pattern_normalized):
                    return True, pattern

    return False, None


def check_hard_deny(
    command: str,
    deny_patterns: List[str],
    allow_patterns: List[str],
    extended_syntax: bool = True,
    *,
    spellings: CommandSpellings = CommandSpellings(),
) -> Optional[LevelMatch]:
    """
    Apply the unoverridable hard-deny rule to a single command.

    The command is HARD-DENIED when it matches any ``deny_patterns`` entry AND
    does NOT match any ``allow_patterns`` carve-out. The ``allow_patterns`` here
    are EXCEPTIONS to the hard deny only -- they are not a forced/normal allow.

    This is intended to be evaluated FIRST, before the normal more-specific-wins
    cascade. A hard deny cannot be overridden by any level's normal allow.

    Args:
        command: The command (sub-command) to evaluate.
        deny_patterns: Pooled hard-deny deny patterns (wrapper-free).
        allow_patterns: Pooled hard-deny allow (carve-out) patterns (wrapper-free).
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes.
        spellings: Further spellings of *command*. The carve-out list grants an
            exemption, so it is matched against the granting side.

    Returns:
        A :class:`~toolguard.config_types.LevelMatch` with ``decision='deny'``
        when the command is hard-denied, otherwise ``None`` so the caller
        falls through to the normal cascade. ``matched_pattern`` is carried
        as its own field rather than recovered by parsing ``reason`` --
        keeping the two independent so a future wording change to ``reason``
        cannot silently break pattern recovery.
    """
    if not deny_patterns:
        return None

    matched, pattern = match_command(
        command, deny_patterns, extended_syntax, also_spelled=spellings.restricting
    )
    if not matched:
        return None

    if allow_patterns:
        exempt, exempt_pattern = match_command(
            command, allow_patterns, extended_syntax, also_spelled=spellings.granting
        )
        if exempt:
            return None

    return LevelMatch(
        decision="deny",
        reason=f"Command matches hard_deny pattern: {pattern} (cannot be overridden)",
        matched_pattern=pattern,
    )


def check_permission(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    extended_syntax: bool = True,
    *,
    spellings: CommandSpellings = CommandSpellings(),
) -> Tuple[str, str]:
    """
    Check a command against a flat, unprovenanced allow/deny pattern pair. Deny-first;
    fails closed when nothing matches either list.

    Args:
        command: The bash command to check.
        allow_patterns: Patterns that allow the command.
        deny_patterns: Patterns that deny the command.
        extended_syntax: If False, skip parsing ``[regex]``/``[glob]``/``[native]`` prefixes.
        spellings: Further spellings of *command*.

    Returns:
        ``(decision, reason)`` where decision is ``'allow'`` or ``'deny'``.
    """
    if deny_patterns:
        matched, pattern = match_command(
            command, deny_patterns, extended_syntax, also_spelled=spellings.restricting
        )
        if matched:
            return "deny", f"Command matches deny pattern: {pattern}"

    matched, pattern = match_command(
        command, allow_patterns, extended_syntax, also_spelled=spellings.granting
    )
    if matched:
        return "allow", f"Command matches allow pattern: {pattern}"

    return "deny", "Command does not match any allow patterns"


def is_universal_pattern(pattern: str) -> bool:
    """
    Return True for a blanket ``*``-class rule: the bare ``*`` and its
    ``[glob]``/``[native]``-prefixed forms, recognised by shape rather than by matching.
    (Only ``[native]*`` actually matches every input -- ``[glob]*`` does not cross ``/``,
    and the bare ``*`` is blocked by the DEFAULT newline guard.)

    A pattern this returns True for should not, by itself, be treated as granting an ask
    prompt: its level declines to decide, so the rest of the cascade runs, and
    ``no_match_fallback`` applies only if no other level matches either.
    """
    body = pattern.strip()
    for marker in ("[glob]", "[native]"):
        if body.startswith(marker):
            body = body[len(marker) :]
    return body == "*"


def _literal_prefix_specificity(pattern: str) -> int:
    """
    Heuristic specificity: the length of the literal prefix before the first wildcard.

    Longer is more specific; a blanket ``*`` scores 0. Used by :func:`resolve_allow_ask`
    to break a tie between an allow and an ask pattern that both match the same command
    (e.g. broad allow ``*`` vs. specific ask ``git diff:*``). An extended-syntax marker is
    stripped first so ``[regex]``/``[glob]``/``[native]`` bodies score by their literal
    lead too.
    """
    body = pattern.strip()
    for marker in ("[regex]", "[glob]", "[native]"):
        if body.startswith(marker):
            body = body[len(marker) :]
            break
    for i, ch in enumerate(body):
        if ch in "*?[":
            return i
    return len(body)


def resolve_allow_ask(
    allow_hit: Tuple[bool, Optional[str]],
    ask_hit: Tuple[bool, Optional[str]],
) -> Optional[Tuple[str, str]]:
    """
    Combine one level's allow-match and non-blanket ask-match into a single outcome.

    More-specific-wins between the two: a more-specific allow bypasses the ask
    (``'allow'``); a more-specific -- or exactly tied -- ask gates it into ``'ask'``,
    since a tie resolves to the safer prompt. The caller must already have excluded
    blanket ask patterns before calling this (see :func:`is_universal_pattern`).

    Args:
        allow_hit: ``(matched, pattern)`` from matching the allow list.
        ask_hit: ``(matched, pattern)`` from matching the non-blanket ask list.

    Returns:
        ``(decision, matched_pattern)`` where decision is ``'allow'`` or ``'ask'``,
        or ``None`` when neither matched.
    """
    allow_match, allow_pat = allow_hit
    ask_match, ask_pat = ask_hit
    if ask_match and not allow_match:
        return "ask", ask_pat
    if allow_match and not ask_match:
        return "allow", allow_pat
    if allow_match and ask_match:
        if _literal_prefix_specificity(allow_pat) > _literal_prefix_specificity(
            ask_pat
        ):
            return "allow", allow_pat
        return "ask", ask_pat
    return None


def decide_command_at_level_detailed(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    extended_syntax: bool = True,
    ask_patterns: Optional[List[str]] = None,
    *,
    spellings: CommandSpellings = CommandSpellings(),
) -> Optional[LevelMatch]:
    """
    Decide a command's outcome against ONE hierarchy level's patterns.

    Deny-first within the level: a deny match yields a ``decision='deny'``
    :class:`~toolguard.config_types.LevelMatch`. Otherwise the allow and ask lists are
    combined by more-specific-wins (:func:`resolve_allow_ask`), with blanket ``*``-class
    ask patterns ignored first (:func:`is_universal_pattern`). When the level matches
    nothing, returns ``None`` so the more-specific-wins cascade can fall through to the
    next (less-specific) level. The matched pattern is reported (not just the decision)
    so a caller can map it back to whichever config layer contributed it.

    Args:
        command: The bash command (sub-command) to evaluate.
        allow_patterns: This level's allow patterns (wrapper-free).
        deny_patterns: This level's deny patterns (wrapper-free).
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes.
        ask_patterns: This level's ask patterns (wrapper-free); omitted or empty
            means no ask pattern gates this level.
        spellings: Further spellings of *command*. The ask list restricts, so it is
            matched against the restricting side alongside the deny list.

    Returns:
        A :class:`~toolguard.config_types.LevelMatch` when this level matches,
        else ``None`` so the cascade falls through to the next level.
    """
    if deny_patterns:
        matched, pattern = match_command(
            command, deny_patterns, extended_syntax, also_spelled=spellings.restricting
        )
        if matched:
            return LevelMatch(
                decision="deny",
                reason=f"Command matches deny pattern: {pattern}",
                matched_pattern=pattern,
            )

    allow_hit = match_command(
        command, allow_patterns, extended_syntax, also_spelled=spellings.granting
    )

    ask_hit: Tuple[bool, Optional[str]] = (False, None)
    if ask_patterns:
        non_blanket_ask = [p for p in ask_patterns if not is_universal_pattern(p)]
        if non_blanket_ask:
            ask_hit = match_command(
                command,
                non_blanket_ask,
                extended_syntax,
                also_spelled=spellings.restricting,
            )

    combined = resolve_allow_ask(allow_hit, ask_hit)
    if combined is None:
        return None
    decision, matched_pattern = combined
    return LevelMatch(
        decision=decision,
        reason=f"Command matches {decision} pattern: {matched_pattern}",
        matched_pattern=matched_pattern,
    )
