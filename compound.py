"""
Compound command permission checking for toolguard.

This module provides permission checking for compound bash commands,
validating each sub-command and returning the strictest permission decision.
"""

from typing import List, Tuple

from toolguard.parser.command_extractor import extract_commands
from toolguard.permissions import check_permission


def check_compound_permission(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    ask_patterns: List[str] = None,
    extended_syntax: bool = True,
) -> Tuple[str, str]:
    """
    Check permissions for a compound bash command.

    This function extracts individual commands from a compound command line
    and checks each against the permission patterns. It returns the strictest
    permission decision according to the following rules:

    - If ANY command is denied → deny the entire command
    - Else if ANY command requires ask → ask for the entire command
    - Else if ALL commands are allowed → allow the entire command

    Args:
        command: The bash command line (may be compound)
        allow_patterns: List of patterns that allow commands
        deny_patterns: List of patterns that deny commands
        ask_patterns: List of patterns that require asking (currently unused,
                     reserved for future Phase 3 implementation)
        extended_syntax: If False, skip parsing [regex]/[glob]/[native] prefixes

    Returns:
        Tuple of (decision, reason) where:
        - decision: 'allow' or 'deny'
        - reason: Human-readable explanation of the decision

    Examples:
        >>> check_compound_permission('git status && rm -rf /', ['git *'], ['rm *'])
        ('deny', 'Compound command contains denied sub-command: rm -rf / (matches deny pattern: rm *)')

        >>> check_compound_permission('git status && git log', ['git *'], [])
        ('allow', 'All sub-commands in compound command are allowed')

        >>> check_compound_permission('cat file | grep pattern', ['cat *', 'grep *'], [])
        ('allow', 'All sub-commands in compound command are allowed')
    """
    # Extract individual commands
    commands = extract_commands(command)

    # If no commands extracted, deny
    if not commands:
        return 'deny', 'No valid commands found in command line'

    # If only one command, use regular permission check
    if len(commands) == 1:
        return check_permission(commands[0], allow_patterns, deny_patterns, extended_syntax)

    # Check each sub-command
    denied_commands = []
    ask_commands = []
    allowed_commands = []

    for cmd in commands:
        decision, reason = check_permission(cmd, allow_patterns, deny_patterns, extended_syntax)

        if decision == 'deny':
            denied_commands.append((cmd, reason))
        elif decision == 'ask':
            # Note: Phase 1 doesn't have 'ask' responses, but Phase 3 will
            ask_commands.append((cmd, reason))
        else:
            allowed_commands.append((cmd, reason))

    # Apply strictest policy:
    # 1. Any deny → deny entire command
    if denied_commands:
        cmd, reason = denied_commands[0]
        return 'deny', f'Compound command contains denied sub-command: {cmd} ({reason})'

    # 2. Any ask → ask for entire command
    # (Reserved for Phase 3 - interactive permission system)
    if ask_commands:
        cmd, reason = ask_commands[0]
        return 'ask', f'Compound command contains sub-command requiring approval: {cmd} ({reason})'

    # 3. All allowed → allow entire command
    return 'allow', f'All {len(commands)} sub-commands in compound command are allowed'


def get_command_breakdown(command: str) -> List[str]:
    """
    Get a breakdown of individual commands from a compound command.

    This is a utility function for debugging and logging purposes.

    Args:
        command: The bash command line to break down

    Returns:
        List of individual command strings

    Example:
        >>> get_command_breakdown('git status && rm -rf /')
        ['git status', 'rm -rf /']
    """
    return extract_commands(command)
