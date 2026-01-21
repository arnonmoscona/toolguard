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
from typing import List, Tuple, Optional

from .patterns import parse_pattern, match_pattern, PatternType
from .normalization import normalize_command


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
        Tuple of (matched: bool, matched_pattern: str or None)
    """
    # Try matching with both original and normalized command
    command_variants = [command_str, normalize_path_in_command(command_str)]

    for pattern in patterns:
        # Parse pattern to determine type
        pattern_type, actual_pattern = parse_pattern(pattern, extended_syntax)

        # REGEX and GLOB patterns bypass all DEFAULT logic
        if pattern_type == PatternType.REGEX or pattern_type == PatternType.GLOB:
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

            for cmd_var in command_variants:
                # If args pattern is * or empty, just match the command prefix
                if args_pattern in ('*', '**', ''):
                    # Match command prefix more flexibly
                    # Extract the base command from the pattern (e.g., "cat" from "cat ./*")
                    pattern_parts = cmd_pattern.split(None, 1)
                    base_cmd = pattern_parts[0]

                    # Check if command starts with the same base command
                    if cmd_var.startswith(base_cmd + ' ') or cmd_var == base_cmd:
                        # Now check if the full command matches the pattern
                        if fnmatch.fnmatch(cmd_var, cmd_pattern + '*'):
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
