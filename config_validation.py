"""Configuration validation for toolguard."""

from typing import Dict, List

# Known supported tools that toolguard can govern
KNOWN_SUPPORTED_TOOLS = {
    'Bash',
    'Read',
    'Write',
    'Edit',
    'mcp__jetbrains__execute_terminal_command',
}


def extract_tool_name(permission: str) -> str:
    """
    Extract the tool name from a permission string.

    Examples:
        'Bash(ls:*)' -> 'Bash'
        'Read(/tmp/**)' -> 'Read'
        'WebSearch' -> 'WebSearch'

    Args:
        permission: Permission string (e.g., 'Bash(ls:*)' or 'WebSearch')

    Returns:
        The tool name extracted from the permission string
    """
    if '(' in permission:
        return permission.split('(', 1)[0]
    return permission


def validate_permissions(config: dict) -> List[Dict[str, str]]:
    """
    Validate configuration and return list of warnings.

    Checks for:
    1. Unsupported tools in permissions (tools that toolguard cannot govern)
    2. Ungoverned tools (tools in permissions but not in governed_tools list)

    Args:
        config: Configuration dictionary (from TOML or JSON)

    Returns:
        List of warning dictionaries with keys:
        - level: Warning severity ('warning' or 'error')
        - message: Human-readable warning message
        - corrective_steps: Suggested actions to fix the issue
    """
    warnings = []

    # Get governed_tools from config (defaults to ['Bash'])
    governed_tools = config.get('governed_tools', ['Bash'])
    if not isinstance(governed_tools, list):
        governed_tools = ['Bash']

    # Get additional_supported_tools from config (defaults to empty list)
    additional_supported_tools = config.get('additional_supported_tools', [])
    if not isinstance(additional_supported_tools, list):
        additional_supported_tools = []

    # Combine known and additional supported tools
    all_supported_tools = KNOWN_SUPPORTED_TOOLS | set(additional_supported_tools)

    # Get permissions section
    permissions = config.get('permissions', {})
    if not isinstance(permissions, dict):
        return warnings

    # Collect all tools mentioned in permissions
    tools_in_permissions = set()
    for permission_list in ['allow', 'deny', 'ask']:
        perms = permissions.get(permission_list, [])
        if isinstance(perms, list):
            for perm in perms:
                if isinstance(perm, str):
                    tool_name = extract_tool_name(perm)
                    tools_in_permissions.add(tool_name)

    # Check for unsupported tools
    for tool in tools_in_permissions:
        if tool not in all_supported_tools:
            warnings.append(
                {
                    'level': 'warning',
                    'message': f'Tool "{tool}" is not a known supported tool',
                    'corrective_steps': (
                        f'If "{tool}" is a valid tool that should be governed, '
                        f'add it to "additional_supported_tools" in your config. '
                        f'Otherwise, remove it from permissions or update the tool name.'
                    ),
                }
            )

    # Check for ungoverned tools (tools in permissions but not in governed_tools)
    for tool in tools_in_permissions:
        if tool in all_supported_tools and tool not in governed_tools:
            warnings.append(
                {
                    'level': 'warning',
                    'message': f'Tool "{tool}" appears in permissions but is not in governed_tools list',
                    'corrective_steps': (
                        f'Add "{tool}" to governed_tools if you want toolguard to enforce these permissions. '
                        f'Otherwise, remove "{tool}" permissions from the config.'
                    ),
                }
            )

    return warnings
