"""
Configuration loading for toolguard.

Loads and parses permissions from Claude Code settings files with support for:
- Config file hierarchy (project -> user)
- Extended pattern syntax in toolguard_hook.json files
- Merging permissions from multiple sources
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Tuple


def find_project_root(start_dir: Path = None) -> Path:
    """
    Find the project root by searching for pyproject.toml or .git directory.

    Climbs up from start_dir (or current directory) until finding a marker file/directory,
    stopping at home directory or filesystem root.

    Args:
        start_dir: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to project root

    Raises:
        RuntimeError: If project root cannot be found
    """
    current = Path(start_dir) if start_dir else Path.cwd()
    home = Path.home()

    while True:
        # Check for project markers
        if (current / 'pyproject.toml').exists() or (current / '.git').exists():
            return current

        # Stop if we reach home or root
        if current == home or current == current.parent:
            raise RuntimeError(
                'Project root not found. Searched for pyproject.toml or .git directory '
                f'from {Path.cwd()} up to {current}. Something is badly wrong.'
            )

        current = current.parent


def discover_config_files(start_dir: Path = None) -> List[Tuple[Path, str, str]]:
    """
    Discover all applicable config files in priority order.

    TOML files take precedence over JSON when both exist at the same level.

    Returns config files in this order (highest to lowest priority):
    1. Project .claude/toolguard_hook.local.toml (or .json if no .toml)
    2. Project .claude/settings.local.json
    3. Project .claude/toolguard_hook.toml (or .json if no .toml)
    4. Project .claude/settings.json
    5. User ~/.claude/toolguard_hook.local.toml (or .json if no .toml)
    6. User ~/.claude/settings.local.json
    7. User ~/.claude/toolguard_hook.toml (or .json if no .toml)
    8. User ~/.claude/settings.json

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        List of (Path, source_type, format) tuples where:
        - source_type is 'claude' or 'toolguard_hook'
        - format is 'json' or 'toml'
    """
    config_files = []

    # Try to find project root
    try:
        project_root = find_project_root(start_dir)
        project_claude_dir = project_root / '.claude'
    except RuntimeError:
        # No project root found - skip project-level configs
        project_claude_dir = None

    # Define config file candidates in priority order with format preference
    # Each entry is (base_name, source_type, prefer_toml)
    candidates = []

    # Project level
    if project_claude_dir:
        candidates.extend(
            [
                (project_claude_dir, 'toolguard_hook.local', 'toolguard_hook', True),
                (project_claude_dir, 'settings.local', 'claude', False),
                (project_claude_dir, 'toolguard_hook', 'toolguard_hook', True),
                (project_claude_dir, 'settings', 'claude', False),
            ]
        )

    # User level
    user_claude_dir = Path.home() / '.claude'
    candidates.extend(
        [
            (user_claude_dir, 'toolguard_hook.local', 'toolguard_hook', True),
            (user_claude_dir, 'settings.local', 'claude', False),
            (user_claude_dir, 'toolguard_hook', 'toolguard_hook', True),
            (user_claude_dir, 'settings', 'claude', False),
        ]
    )

    # Check for both TOML and JSON, with TOML taking precedence
    for directory, base_name, source_type, prefer_toml in candidates:
        toml_path = directory / f'{base_name}.toml'
        json_path = directory / f'{base_name}.json'

        toml_exists = toml_path.exists()
        json_exists = json_path.exists()

        if prefer_toml and toml_exists:
            # TOML file found - use it
            config_files.append((toml_path, source_type, 'toml'))

            # Warn if both exist
            if json_exists:
                print(
                    f'Warning: Both {toml_path.name} and {json_path.name} exist. Using TOML ({toml_path.name})',
                    file=sys.stderr,
                )
        elif json_exists:
            # JSON file found (or only JSON exists)
            config_files.append((json_path, source_type, 'json'))

    return config_files


def load_permissions_from_file(
    file_path: Path, source_type: str, file_format: str = 'json', strict: bool = False
) -> Tuple[List[str], List[str]]:
    """
    Load permissions from a single config file (JSON or TOML).

    Args:
        file_path: Path to the config file
        source_type: Either 'claude' or 'toolguard_hook'
        file_format: Either 'json' or 'toml'
        strict: If True, raise exceptions instead of returning empty lists

    Returns:
        Tuple of (allow_patterns, deny_patterns)

    Raises:
        FileNotFoundError: If file doesn't exist (only if strict=True)
        json.JSONDecodeError: If file contains invalid JSON (only if strict=True)
        tomllib.TOMLDecodeError: If file contains invalid TOML (only if strict=True)
    """
    try:
        if file_format == 'toml':
            import tomllib

            with open(file_path, 'rb') as f:
                config = tomllib.load(f)
        else:
            with open(file_path, 'r') as f:
                config = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        if strict:
            raise
        print(f'Warning: Invalid {file_format.upper()} in {file_path}: {e}', file=sys.stderr)
        return [], []

    permissions = config.get('permissions', {})

    allow_patterns = []
    deny_patterns = []

    # Extract patterns from allow list
    for perm in permissions.get('allow', []):
        if isinstance(perm, str) and perm.startswith('Bash(') and perm.endswith(')'):
            # Extract the pattern between "Bash(" and ")"
            pattern = perm[5:-1]  # Remove "Bash(" and ")"
            allow_patterns.append(pattern)

    # Extract patterns from deny list
    for perm in permissions.get('deny', []):
        if isinstance(perm, str) and perm.startswith('Bash(') and perm.endswith(')'):
            # Extract the pattern between "Bash(" and ")"
            pattern = perm[5:-1]  # Remove "Bash(" and ")"
            deny_patterns.append(pattern)

    return allow_patterns, deny_patterns


def merge_permissions(permissions_list: List[Tuple[List[str], List[str]]]) -> Tuple[List[str], List[str]]:
    """
    Merge permissions from multiple sources using simple union.

    Args:
        permissions_list: List of (allow_patterns, deny_patterns) tuples

    Returns:
        Tuple of (merged_allow_patterns, merged_deny_patterns)
    """
    all_allow = []
    all_deny = []

    for allow_patterns, deny_patterns in permissions_list:
        all_allow.extend(allow_patterns)
        all_deny.extend(deny_patterns)

    # Remove duplicates while preserving order
    seen_allow = set()
    unique_allow = []
    for pattern in all_allow:
        if pattern not in seen_allow:
            seen_allow.add(pattern)
            unique_allow.append(pattern)

    seen_deny = set()
    unique_deny = []
    for pattern in all_deny:
        if pattern not in seen_deny:
            seen_deny.add(pattern)
            unique_deny.append(pattern)

    return unique_allow, unique_deny


def load_governed_tools_from_file(file_path: Path, file_format: str = 'json') -> List[str]:
    """
    Load governed tools list from a single config file (JSON or TOML).

    Only reads from toolguard_hook files (not Claude settings files).

    Args:
        file_path: Path to the config file
        file_format: Either 'json' or 'toml'

    Returns:
        List of tool names to govern, or empty list if not found/invalid
    """
    try:
        if file_format == 'toml':
            import tomllib

            with open(file_path, 'rb') as f:
                config = tomllib.load(f)
        else:
            with open(file_path, 'r') as f:
                config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, Exception):
        return []

    governed_tools = config.get('governed_tools', [])

    # Validate it's a list of strings
    if not isinstance(governed_tools, list):
        return []

    return [tool for tool in governed_tools if isinstance(tool, str)]


def merge_governed_tools(tools_lists: List[List[str]]) -> List[str]:
    """
    Merge governed tools from multiple sources using union.

    Args:
        tools_lists: List of tool name lists from different sources

    Returns:
        List of unique tool names (order preserved from first occurrence)
    """
    all_tools = []

    for tools in tools_lists:
        all_tools.extend(tools)

    # Remove duplicates while preserving order
    seen = set()
    unique_tools = []
    for tool in all_tools:
        if tool not in seen:
            seen.add(tool)
            unique_tools.append(tool)

    return unique_tools


def load_governed_tools(start_dir: Path = None) -> List[str]:
    """
    Load list of tools to govern from config files.

    Searches for 'governed_tools' key in toolguard_hook files (TOML or JSON).
    Not in Claude settings files. Merges from multiple sources using union.

    If no configuration found, returns default: ["Bash"]

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        List of tool names to govern (default: ["Bash"])
    """
    # Check if CLAUDE_SETTINGS_PATH is set (backward compatible)
    settings_path = os.environ.get('CLAUDE_SETTINGS_PATH')
    if settings_path:
        # When using CLAUDE_SETTINGS_PATH, only look for adjacent toolguard_hook.json
        settings_dir = Path(settings_path).parent
        hook_file = settings_dir / 'toolguard_hook.json'
        if hook_file.exists():
            tools = load_governed_tools_from_file(hook_file, 'json')
            if tools:
                return tools

        # No toolguard_hook.json found - use default
        return ['Bash']

    # Discover config files in hierarchy
    config_files = discover_config_files(start_dir)

    # Filter to only toolguard_hook files
    hook_files = [(path, fmt) for path, source_type, fmt in config_files if source_type == 'toolguard_hook']

    if not hook_files:
        # No hook files found - use default
        return ['Bash']

    # Load governed tools from all hook files
    tools_lists = []
    for path, fmt in hook_files:
        tools = load_governed_tools_from_file(path, fmt)
        if tools:
            tools_lists.append(tools)

    # If no governed_tools found in any file, use default
    if not tools_lists:
        return ['Bash']

    # Merge all governed tools
    return merge_governed_tools(tools_lists)


def load_permissions(start_dir: Path = None) -> Tuple[List[str], List[str]]:
    """
    Load and parse permissions from Claude Code settings files.

    If CLAUDE_SETTINGS_PATH is set, uses ONLY that file (backward compatible).
    Otherwise, discovers and merges permissions from config file hierarchy:
    1. Project .claude/settings.local.json + .claude/toolguard_hook.local.json
    2. Project .claude/settings.json + .claude/toolguard_hook.json
    3. User ~/.claude/settings.local.json + ~/.claude/toolguard_hook.local.json
    4. User ~/.claude/settings.json + ~/.claude/toolguard_hook.json

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        Tuple of (allow_patterns, deny_patterns) where each is a list of strings

    Raises:
        SystemExit: If CLAUDE_SETTINGS_PATH is set but file cannot be loaded
    """
    settings_path = os.environ.get('CLAUDE_SETTINGS_PATH')

    # If CLAUDE_SETTINGS_PATH is set, load from that file AND adjacent toolguard_hook files
    if settings_path:
        print(f'Using config from CLAUDE_SETTINGS_PATH: {settings_path}', file=sys.stderr)
        permissions_list = []

        # Load from the settings file
        try:
            perms = load_permissions_from_file(Path(settings_path), 'claude', 'json', strict=True)
            permissions_list.append(perms)
        except FileNotFoundError:
            print(f'Error: Settings file not found: {settings_path}', file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f'Error: Invalid JSON in settings file: {e}', file=sys.stderr)
            sys.exit(1)

        # Also check for adjacent toolguard_hook files (TOML takes precedence)
        settings_dir = Path(settings_path).parent
        hook_toml = settings_dir / 'toolguard_hook.toml'
        hook_json = settings_dir / 'toolguard_hook.json'

        if hook_toml.exists():
            try:
                perms = load_permissions_from_file(hook_toml, 'toolguard_hook', 'toml')
                permissions_list.append(perms)
            except Exception as e:
                print(f'Warning: Failed to load {hook_toml}: {e}', file=sys.stderr)
        elif hook_json.exists():
            try:
                perms = load_permissions_from_file(hook_json, 'toolguard_hook', 'json')
                permissions_list.append(perms)
            except Exception as e:
                print(f'Warning: Failed to load {hook_json}: {e}', file=sys.stderr)

        return merge_permissions(permissions_list)

    # Discover config files in hierarchy
    config_files = discover_config_files(start_dir)

    if not config_files:
        print('Warning: No config files found in hierarchy', file=sys.stderr)
        print('Searched for:', file=sys.stderr)
        print('  - .claude/settings.local.json (project)', file=sys.stderr)
        print('  - .claude/settings.json (project)', file=sys.stderr)
        print('  - ~/.claude/settings.local.json (user)', file=sys.stderr)
        print('  - ~/.claude/settings.json (user)', file=sys.stderr)
        print('  - .claude/toolguard_hook.local.json (project)', file=sys.stderr)
        print('  - .claude/toolguard_hook.json (project)', file=sys.stderr)
        print('  - ~/.claude/toolguard_hook.local.json (user)', file=sys.stderr)
        print('  - ~/.claude/toolguard_hook.json (user)', file=sys.stderr)
        return [], []

    # Log discovered files
    print('Discovered config files (in priority order):', file=sys.stderr)
    for path, source_type, fmt in config_files:
        print(f'  - {path} [{source_type}, {fmt}]', file=sys.stderr)

    # Load permissions from all discovered files
    permissions_list = []
    for path, source_type, fmt in config_files:
        try:
            perms = load_permissions_from_file(path, source_type, fmt)
            permissions_list.append(perms)
        except Exception as e:
            print(f'Warning: Failed to load {path}: {e}', file=sys.stderr)
            continue

    # Merge all permissions
    allow_patterns, deny_patterns = merge_permissions(permissions_list)

    print(f'Loaded {len(allow_patterns)} allow patterns, {len(deny_patterns)} deny patterns', file=sys.stderr)

    return allow_patterns, deny_patterns
