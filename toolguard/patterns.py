"""
Extended pattern matching for toolguard.

Four pattern types, selected by an optional ``[type]`` prefix that
:func:`parse_pattern` strips: DEFAULT (no prefix), REGEX (``[regex]``), GLOB
(``[glob]``), NATIVE (``[native]``). :func:`match_pattern` applies the
selected type's semantics.
"""

import re
import fnmatch
from enum import Enum
from pathlib import PurePath
from typing import Tuple

from .normalization import expand_tilde


class PatternType(Enum):
    """Pattern syntax selected by a pattern string's ``[type]`` prefix (see :func:`parse_pattern`)."""

    DEFAULT = "default"
    REGEX = "regex"
    GLOB = "glob"
    NATIVE = "native"


def parse_pattern(
    pattern_str: str, extended_syntax: bool = True
) -> Tuple[PatternType, str]:
    """
    Split a pattern string into its :class:`PatternType` and prefix-stripped body.

    A ``[regex]``/``[glob]``/``[native]`` prefix selects that type; anything
    else (or ``extended_syntax=False``, which skips prefix recognition
    entirely) is DEFAULT.

    Args:
        pattern_str: The pattern string to parse.
        extended_syntax: If False, treat pattern_str as DEFAULT regardless of
            any ``[...]`` prefix it starts with.

    Returns:
        ``(pattern_type, body)`` -- body has the ``[type]`` prefix, if any,
        and surrounding whitespace stripped.
    """
    pattern_str = pattern_str.strip()

    if not extended_syntax:
        return PatternType.DEFAULT, pattern_str

    if pattern_str.startswith("[regex]"):
        return PatternType.REGEX, pattern_str[7:].strip()
    elif pattern_str.startswith("[glob]"):
        return PatternType.GLOB, pattern_str[6:].strip()
    elif pattern_str.startswith("[native]"):
        return PatternType.NATIVE, pattern_str[8:].strip()
    else:
        return PatternType.DEFAULT, pattern_str


def match_pattern(pattern_type: PatternType, pattern: str, command: str) -> bool:
    """
    Match a command against a pattern under pattern_type's own matching semantics.

    Args:
        pattern_type: Selects the matching semantics -- see the corresponding
            branch below.
        pattern: The pattern to match against (already stripped of its
            ``[type]`` prefix by :func:`parse_pattern`, if any).
        command: The command string to match.

    Returns:
        True if command matches under pattern_type's semantics, False
        otherwise -- a malformed REGEX pattern is treated as non-matching
        rather than raised.
    """
    if pattern_type == PatternType.REGEX:
        # re.search: matches anywhere in command, not anchored to the start.
        try:
            return bool(re.search(pattern, command))
        except re.error:
            return False

    elif pattern_type == PatternType.GLOB:
        # PurePath.full_match(): anchored to the whole string. * does not
        # cross a path separator; ** does, but only as a whole path
        # component. ~ is expanded on both sides first since full_match()
        # has no notion of home-directory expansion.
        expanded_pattern = expand_tilde(pattern)
        expanded_command = expand_tilde(command)
        try:
            return PurePath(expanded_command).full_match(expanded_pattern)
        except ValueError, TypeError:
            return False

    elif pattern_type == PatternType.NATIVE:
        # Intended as Claude Code's own wildcard syntax: * matches any run of
        # characters, including whitespace. The literal segments between *s
        # must occur in order, each found from just past the previous one.
        #
        # The search never backtracks -- worth the paragraph, because the
        # resulting failure is silent. A wildcard pattern ending in * always
        # matches correctly. One NOT ending in * fails whenever its final
        # segment is found short of the command's end: the end-anchor check
        # tests that occurrence, not the last one. So "*id_rsa" does not
        # match "cat id_rsa.pub id_rsa". Every deviation is a false negative
        # -- on a deny rule, a bypass.
        if "*" not in pattern:
            return pattern == command

        segments = pattern.split("*")

        pos = 0
        for i, segment in enumerate(segments):
            if not segment:
                # Adjacent *s, or a leading/trailing *, split to an empty
                # segment here -- nothing to search for.
                continue

            idx = command.find(segment, pos)
            if idx == -1:
                return False

            if i == 0 and not pattern.startswith("*"):
                # No leading * -- the first segment must start at position 0.
                if idx != 0:
                    return False

            pos = idx + len(segment)

        if segments and segments[-1] and not pattern.endswith("*"):
            # No trailing * -- the last segment must end at the command's end.
            if pos != len(command):
                return False

        return True

    elif pattern_type == PatternType.DEFAULT:
        # fnmatch.fnmatch: also a full-string match, but unlike GLOB its *
        # DOES cross a path separator.
        return fnmatch.fnmatch(command, pattern)

    return False
