"""
Extended pattern matching for toolguard.

Supports four pattern types:
- DEFAULT: Standard fnmatch patterns (with special handling for path components)
- REGEX: Patterns prefixed with [regex] for regular expression matching
- GLOB: Patterns prefixed with [glob] for true glob matching with globstar support
- NATIVE: Patterns prefixed with [native] for word-level wildcard matching
"""

import re
import fnmatch
from enum import Enum
from pathlib import PurePath
from typing import Tuple

from .normalization import expand_tilde


class PatternType(Enum):
    """Type of pattern for command matching."""

    DEFAULT = 'default'  # Standard fnmatch with special path component handling
    REGEX = 'regex'  # Regular expression pattern
    GLOB = 'glob'  # True glob pattern with globstar support
    NATIVE = 'native'  # Word-level wildcard matching (Claude Code 2.10 style)


def parse_pattern(pattern_str: str, extended_syntax: bool = True) -> Tuple[PatternType, str]:
    """
    Parse a pattern string to determine its type and extract the actual pattern.

    Supports:
    - [regex]<pattern> - Regular expression pattern
    - [glob]<pattern> - True glob pattern with globstar support
    - [native]<pattern> - Word-level wildcard pattern
    - <pattern> - Default fnmatch pattern with special handling

    Args:
        pattern_str: The pattern string to parse
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes

    Returns:
        Tuple of (PatternType, pattern) where pattern is the extracted pattern string
    """
    pattern_str = pattern_str.strip()

    if not extended_syntax:
        # Extended syntax disabled - treat everything as DEFAULT
        return PatternType.DEFAULT, pattern_str

    if pattern_str.startswith('[regex]'):
        return PatternType.REGEX, pattern_str[7:].strip()
    elif pattern_str.startswith('[glob]'):
        return PatternType.GLOB, pattern_str[6:].strip()
    elif pattern_str.startswith('[native]'):
        return PatternType.NATIVE, pattern_str[8:].strip()
    else:
        return PatternType.DEFAULT, pattern_str


def match_pattern(pattern_type: PatternType, pattern: str, command: str) -> bool:
    """
    Match a command against a pattern using the specified pattern type.

    Args:
        pattern_type: The type of pattern matching to use
        pattern: The pattern to match against
        command: The command string to match

    Returns:
        True if the command matches the pattern, False otherwise
    """
    if pattern_type == PatternType.REGEX:
        # Use re.search to match anywhere in the command
        try:
            return bool(re.search(pattern, command))
        except re.error:
            # Invalid regex pattern - treat as non-matching
            return False

    elif pattern_type == PatternType.GLOB:
        # True glob matching with globstar support using PurePath.full_match()
        # Expand ~ in both pattern and command for proper matching
        expanded_pattern = expand_tilde(pattern)
        expanded_command = expand_tilde(command)
        try:
            # PurePath.full_match() properly distinguishes * from **:
            # - * matches any characters EXCEPT path separator /
            # - ** matches any characters INCLUDING path separators (recursive)
            return PurePath(expanded_command).full_match(expanded_pattern)
        except (ValueError, TypeError):
            # Invalid pattern or command - treat as non-matching
            return False

    elif pattern_type == PatternType.NATIVE:
        # Word-level wildcard matching (Claude Code 2.10 style)
        # * matches any sequence of non-whitespace characters
        # Pattern segments must appear in order in the command
        if '*' not in pattern:
            # No wildcards - must match exactly
            return pattern == command

        # Split pattern by * to get literal segments
        segments = pattern.split('*')

        # Start searching from the beginning of the command
        pos = 0
        for i, segment in enumerate(segments):
            if not segment:
                # Empty segment (e.g., from ** or leading/trailing *)
                continue

            # Find the segment in the remaining command
            idx = command.find(segment, pos)
            if idx == -1:
                # Segment not found
                return False

            # For first segment, check if it should be at the start
            if i == 0 and not pattern.startswith('*'):
                # Pattern doesn't start with *, so first segment must be at start
                if idx != 0:
                    return False

            # Move position past this segment
            pos = idx + len(segment)

        # For last segment, check if it should be at the end
        if segments and segments[-1] and not pattern.endswith('*'):
            # Pattern doesn't end with *, so last segment must be at end
            if pos != len(command):
                return False

        return True

    elif pattern_type == PatternType.DEFAULT:
        # For DEFAULT type, we defer to the existing match_command logic
        # in permissions.py which has special handling for path components
        # This is a fallback - typically match_command should be used directly
        return fnmatch.fnmatch(command, pattern)

    return False
