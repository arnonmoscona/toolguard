"""
Permission checking logic for toolguard.

Replicates the exact matching logic from checked_bash.py including:
- fnmatch pattern matching
- Path normalization
- Special handling for path component patterns
- Command:args pattern separation
- Extended pattern support (REGEX and GLOB)
"""

import fnmatch
from typing import List, Optional, Tuple

from .patterns import parse_pattern, match_pattern, PatternType
from .normalization import normalize_command, normalize_path


def normalize_path_in_command(command_str: str) -> str:
    """
    Normalize paths in a command to canonical form.

    This uses the comprehensive normalization from normalization.py which:
    - Converts /Users/<username>/... to ~/...
    - Resolves symlinks (max 3 iterations)
    - Normalizes multiple leading slashes to single /
    - Expands relative paths to ./

    Additionally handles the case where arguments don't clearly look like paths
    but should be treated as such (e.g., 'ls mydir' -> 'ls ./mydir').

    Args:
        command_str: The command string to normalize

    Returns:
        Normalized command string with canonical paths

    Examples:
        >>> normalize_path_in_command('cat /Users/arnon/file.txt')
        'cat ~/file.txt'
        >>> normalize_path_in_command('cat file.txt')
        'cat ./file.txt'
        >>> normalize_path_in_command('ls mydir')
        'ls ./mydir'
    """
    # First apply comprehensive normalization from normalization.py
    result = normalize_command(command_str)

    # Additionally, for backwards compatibility, add ./ prefix to args
    # that don't start with ., /, -, or ~
    # This handles cases like 'ls mydir' -> 'ls ./mydir'
    parts = result.split(None, 1)  # Split into command and args
    if len(parts) == 2:
        cmd, args = parts
        # If args don't start with . or / or - or ~, add ./ prefix
        if args and not args.startswith(('.', '/', '-', '~')):
            result = f'{cmd} ./{args}'

    return result


def contains_path_component(command_str: str, component: str) -> bool:
    """
    Check if a command contains a specific path component.

    For example, '.env' as a component in 'cat .env', 'cat dir/.env', 'cat .env/file', etc.

    Args:
        command_str: The command string to check
        component: The path component to search for

    Returns:
        True if the component is found in any path argument, False otherwise
    """
    # Remove the command part, focus on arguments
    parts = command_str.split(None, 1)
    if len(parts) < 2:
        return False

    args = parts[1]

    # Check if the component appears as:
    # - Exact match: "cat .env"
    # - After a slash: "cat dir/.env" or "cat /path/.env"
    # - Before a slash: "cat .env/file"
    # - In the middle: "cat dir/.env/file"

    # Split args by spaces to handle multiple arguments
    for arg in args.split():
        # Split by path separators
        path_parts = arg.replace('\\', '/').split('/')
        if component in path_parts:
            return True

    return False


def match_command(command_str: str, patterns: List[str], extended_syntax: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Check if the command matches any of the patterns.

    Patterns can be:
    - Simple wildcards: "git *" matches any git command
    - Prefix with args: "git log:*" matches "git log" with any arguments
    - Complex patterns: "cat ./**:*" matches cat with any file in current dir tree
    - Path patterns: "**/.env/**" matches any command containing /.env/ in the path
    - Extended REGEX: "[regex]^git (log|diff|status).*" for regex matching
    - Extended GLOB: "[glob]/Users/*/projects/**/*.py" for true glob matching

    Wildcards:
    - * matches any characters within a path component
    - ** matches any characters including path separators (treated as * for fnmatch)

    Args:
        command_str: The command string to match
        patterns: List of patterns to match against
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes

    Returns:
        Tuple of (matched: bool, matched_pattern: str or None).

        COUPLING: ``matched_pattern`` is the RAW, un-normalized list element from
        ``patterns`` (prefixes such as ``[regex]``/``[glob]`` included), not the
        parsed/stripped form. Provenance lookup in hook.py
        (``_provenance_for_pattern``) relies on this identity -- it does
        ``pattern in candidates`` against the very layer lists passed in here. If
        this is ever changed to return a normalized/wrapper-stripped pattern,
        provenance lookup will silently return None.
    """
    # Try matching with both original and normalized command
    command_variants = [command_str, normalize_path_in_command(command_str)]

    for pattern in patterns:
        # Parse pattern to determine type
        pattern_type, actual_pattern = parse_pattern(pattern, extended_syntax)

        # REGEX, GLOB, and NATIVE patterns bypass all DEFAULT logic
        if pattern_type in (PatternType.REGEX, PatternType.GLOB, PatternType.NATIVE):
            # Match directly against command (no normalization, no colon syntax)
            if match_pattern(pattern_type, actual_pattern, command_str):
                return True, pattern
            continue

        # DEFAULT pattern type - use existing logic
        # Special handling for path component patterns like "**/.env/**"
        # These are patterns that want to match a specific path component anywhere
        if actual_pattern.startswith('**/') and actual_pattern.endswith('/**'):
            # Extract the component between **/ and /**
            component = actual_pattern[3:-3]
            if contains_path_component(command_str, component):
                return True, pattern
            continue

        # Normalize ** to * for fnmatch (fnmatch doesn't distinguish them)
        pattern_normalized = actual_pattern.replace('**', '*')

        if ':' in pattern_normalized:
            # Pattern like "git log:*" or "cat ./*:*"
            # Split into command pattern and args pattern
            cmd_pattern, args_pattern = pattern_normalized.split(':', 1)
            cmd_pattern = cmd_pattern.strip()
            args_pattern = args_pattern.strip()

            # Extract the base command from the pattern (e.g., "cat" from "cat ./*")
            pattern_parts = cmd_pattern.split(None, 1)
            base_cmd = pattern_parts[0]

            # Normalize the pattern's base_cmd the same way we normalize commands,
            # so e.g. `bin/x:*` and `./bin/x:*` both canonicalize to `./bin/x` —
            # matching a command `bin/x` whose own first token normalizes the same way.
            base_cmd_variants = [base_cmd]
            if '/' in base_cmd:
                normalized_base = normalize_path(base_cmd)
                if normalized_base != base_cmd:
                    base_cmd_variants.append(normalized_base)

            for cmd_var in command_variants:
                # If args pattern is * or empty, just match the command prefix
                if args_pattern in ('*', '**', ''):
                    # Match command prefix more flexibly
                    matched_base = any(
                        cmd_var.startswith(bc + ' ') or cmd_var == bc
                        for bc in base_cmd_variants
                    )
                    if matched_base:
                        # Now check if the full command matches the pattern
                        # Try each base_cmd variant as the pattern prefix
                        for bc in base_cmd_variants:
                            full_cmd_pattern = bc + cmd_pattern[len(base_cmd):] + '*'
                            if fnmatch.fnmatch(cmd_var, full_cmd_pattern):
                                return True, pattern
                else:
                    # More specific args pattern - match the full command
                    full_pattern = cmd_pattern + ' ' + args_pattern
                    if fnmatch.fnmatch(cmd_var, full_pattern):
                        return True, pattern
        else:
            # No colon - match the entire command string
            for cmd_var in command_variants:
                if fnmatch.fnmatch(cmd_var, pattern_normalized):
                    return True, pattern

    return False, None


def check_hard_deny(
    command: str, deny_patterns: List[str], allow_patterns: List[str], extended_syntax: bool = True
) -> Optional[Tuple[str, str]]:
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

    Returns:
        ``('deny', reason)`` when the command is hard-denied, otherwise ``None``
        (no hard-deny match, so the caller falls through to the normal cascade).
    """
    if not deny_patterns:
        return None

    matched, pattern = match_command(command, deny_patterns, extended_syntax)
    if not matched:
        return None

    # A deny matched. An allow carve-out exempts the command from the hard deny.
    if allow_patterns:
        exempt, exempt_pattern = match_command(command, allow_patterns, extended_syntax)
        if exempt:
            return None

    return 'deny', f'Command matches hard_deny pattern: {pattern} (cannot be overridden)'


def check_permission(
    command: str, allow_patterns: List[str], deny_patterns: List[str], extended_syntax: bool = True
) -> Tuple[str, str]:
    """
    Check if a command is permitted based on allow and deny patterns.

    Algorithm:
    1. Check deny patterns first - if match, command is denied
    2. Check allow patterns - if match, command is allowed
    3. If no match in either, command is denied (fail closed)

    Args:
        command: The bash command to check
        allow_patterns: List of patterns that allow commands
        deny_patterns: List of patterns that deny commands
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes

    Returns:
        Tuple of (decision, reason) where decision is 'allow' or 'deny'
        and reason is a human-readable explanation
    """
    # Check deny list first - if it matches, reject immediately
    if deny_patterns:
        matched, pattern = match_command(command, deny_patterns, extended_syntax)
        if matched:
            return 'deny', f'Command matches deny pattern: {pattern}'

    # Check if command is allowed
    matched, pattern = match_command(command, allow_patterns, extended_syntax)
    if matched:
        return 'allow', f'Command matches allow pattern: {pattern}'

    # Default: deny (not explicitly allowed)
    return 'deny', 'Command does not match any allow patterns'


def decide_command_at_level_detailed(
    command: str, allow_patterns: List[str], deny_patterns: List[str], extended_syntax: bool = True
) -> Optional[Tuple[str, str, str]]:
    """
    Decide a command's outcome against ONE hierarchy level's patterns.

    Deny-first within the level: a deny match yields ``('deny', reason, pattern)``;
    else an allow match yields ``('allow', reason, pattern)``. When the level
    matches NOTHING, returns ``None`` so the more-specific-wins cascade can fall
    through to the next (less-specific) level. The matched pattern is reported so
    the provenance-aware resolver can map it back to the
    :class:`~toolguard.config.ToolPatternLayer` (and thus the source file/level)
    that contributed it.

    Args:
        command: The bash command (sub-command) to evaluate.
        allow_patterns: This level's allow patterns (wrapper-free).
        deny_patterns: This level's deny patterns (wrapper-free).
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes.

    Returns:
        ``(decision, reason, matched_pattern)`` when this level matches, else
        ``None`` so the cascade falls through to the next level.
    """
    if deny_patterns:
        matched, pattern = match_command(command, deny_patterns, extended_syntax)
        if matched:
            return 'deny', f'Command matches deny pattern: {pattern}', pattern

    matched, pattern = match_command(command, allow_patterns, extended_syntax)
    if matched:
        return 'allow', f'Command matches allow pattern: {pattern}', pattern

    return None

