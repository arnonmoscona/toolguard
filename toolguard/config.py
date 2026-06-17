"""
Configuration loading for toolguard.

Loads and parses permissions from Claude Code settings files with support for:
- Config file hierarchy (project -> user)
- Extended pattern syntax in toolguard_hook.json files
- Merging permissions from multiple sources

Public abstraction
------------------
The public entry point is :func:`load_configuration`, which returns an immutable
:class:`Configuration`. All file discovery, JSON/TOML parsing, ``.claude/`` layout,
``.local`` handling, and ``CLAUDE_SETTINGS_PATH`` behaviour are internal to this module.
No code outside this module should open a config file, parse JSON/TOML, or branch on
file format/location. Clients ask the :class:`Configuration` semantic questions instead.

The lower-level loaders are internal implementation behind this abstraction; new clients
should always prefer :func:`load_configuration`. A few remain public only because
not-yet-migrated non-test callers still use them -- ``find_project_root``,
``discover_config_files`` and ``load_takeover_mode_config`` (used by ``log_writer`` and
``scripts/migrate_permissions``), and ``config_sync_settings_from_sources`` (used by
``auto_migrate``). That is transitional and tracked as a TOO-8 follow-up; everything else
internal is underscore-prefixed.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Tuple

from toolguard.config_validation import validate_permissions

# Structural matcher for a ``Tool(inner)`` permission wrapper. An identifier made
# of word characters followed by a parenthesised body. ``.*`` (greedy, DOTALL via
# the trailing ``\)``) lets the inner body itself contain parentheses, e.g.
# ``Bash(foo(bar))`` -> ``foo(bar)``. This needs no known-tool list.
_TOOL_WRAPPER_RE = re.compile(r'[A-Za-z0-9_]+\((.*)\)', re.DOTALL)


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


# Within-level candidates, highest-to-lowest priority. Each entry is
# (base_name, source_type, prefer_toml). Mirrors the ordering used by the legacy
# two-level discover_config_files so within-level behaviour (incl. TOML-over-JSON)
# is identical at every level of the hierarchy.
_LEVEL_CANDIDATES: Tuple[Tuple[str, str, bool], ...] = (
    ('toolguard_hook.local', 'toolguard_hook', True),
    ('settings.local', 'claude', False),
    ('toolguard_hook', 'toolguard_hook', True),
    ('settings', 'claude', False),
)


def _discover_in_dir(claude_dir: Path) -> List[Tuple[Path, str, str]]:
    """
    Discover config files within a single ``.claude`` directory.

    Applies the within-level priority ordering (``.local`` first, toolguard_hook
    before native settings) and TOML-over-JSON preference, exactly as the legacy
    two-level discovery did per level.

    Args:
        claude_dir: A ``.claude`` directory to scan.

    Returns:
        List of (path, source_type, format) triples for files that exist,
        highest-priority first.
    """
    found: List[Tuple[Path, str, str]] = []
    for base_name, source_type, prefer_toml in _LEVEL_CANDIDATES:
        toml_path = claude_dir / f'{base_name}.toml'
        json_path = claude_dir / f'{base_name}.json'
        toml_exists = toml_path.exists()
        json_exists = json_path.exists()

        if prefer_toml and toml_exists:
            found.append((toml_path, source_type, 'toml'))
            if json_exists:
                print(
                    f'Warning: Both {toml_path.name} and {json_path.name} exist. Using TOML ({toml_path.name})',
                    file=sys.stderr,
                )
        elif json_exists:
            found.append((json_path, source_type, 'json'))
    return found


def _hierarchical_toggle(project_claude_dir: Optional[Path]) -> bool:
    """
    Read the ``hierarchical_configuration`` toggle from the project level only.

    Per the fixed-bootstrap rule, the toggle is read ONLY from the most-specific
    (project) ``toolguard_hook`` config so that ancestors cannot vote on whether
    ancestors are traversed. Defaults to ``True`` when unset or unreadable.

    Args:
        project_claude_dir: The project's ``.claude`` directory, or None when no
            project root could be found.

    Returns:
        True to walk the full hierarchy, False to use only project + user levels.
    """
    if project_claude_dir is None:
        return True
    # Only toolguard_hook sources carry this toggle (not native settings).
    for path, source_type, file_format in _discover_in_dir(project_claude_dir):
        if source_type != 'toolguard_hook':
            continue
        content = _parse_source(path, file_format)
        if content is None:
            continue
        if 'hierarchical_configuration' in content:
            return bool(content['hierarchical_configuration'])
        # First (highest-priority) toolguard_hook source wins; stop after it so a
        # less-specific project-level file cannot override the toggle decision.
        break
    return True


def _discover_levels(start_dir: Path = None) -> List[Tuple[Path, str, str, int]]:
    """
    Discover config files across the directory hierarchy, most-specific first.

    Walks from the project root (see :func:`find_project_root`) UP TO and
    including the user's home directory, collecting config files from every
    ancestor that has a ``.claude`` subdirectory. The user-level ``~/.claude`` is
    ALWAYS included as the least-specific level, even when the project is not
    located under ``~`` (preserving "user config always applies"). The walk never
    ascends above ``~``.

    Each level is assigned a ``specificity`` index: 0 = project (most specific),
    increasing with distance, and the user level last (least specific). When the
    ``hierarchical_configuration`` toggle (read from the project level only) is
    False, only the project and user levels are collected -- today's behaviour.

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to cwd.

    Returns:
        List of (path, source_type, format, specificity) tuples, ordered
        most-specific first then by within-level priority.
    """
    home = Path.home()
    user_claude_dir = home / '.claude'

    try:
        project_root = find_project_root(start_dir)
        project_claude_dir = project_root / '.claude'
    except RuntimeError:
        project_root = None
        project_claude_dir = None

    hierarchical = _hierarchical_toggle(project_claude_dir)

    # Build the ordered list of .claude directories (most specific first),
    # de-duplicated, with the user level always present and always last.
    level_dirs: List[Path] = []

    def _add(claude_dir: Path) -> None:
        resolved = claude_dir.resolve()
        for existing in level_dirs:
            if existing.resolve() == resolved:
                return
        level_dirs.append(claude_dir)

    if project_root is not None:
        if hierarchical:
            current = project_root
            while True:
                _add(current / '.claude')
                if current == home or current == current.parent:
                    break
                current = current.parent
        else:
            _add(project_root / '.claude')

    # User level always applies and is always least specific (appended last,
    # unless it was already reached by the upward walk -- in which case it keeps
    # its natural, least-specific position at the tail).
    _add(user_claude_dir)

    results: List[Tuple[Path, str, str, int]] = []
    for specificity, claude_dir in enumerate(level_dirs):
        if not claude_dir.exists():
            continue
        for path, source_type, file_format in _discover_in_dir(claude_dir):
            results.append((path, source_type, file_format, specificity))
    return results


def _load_permissions_from_file(
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


def _merge_permissions(permissions_list: List[Tuple[List[str], List[str]]]) -> Tuple[List[str], List[str]]:
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


def _load_governed_tools_from_file(file_path: Path, file_format: str = 'json') -> List[str]:
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


def _merge_governed_tools(tools_lists: List[List[str]]) -> List[str]:
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


def load_takeover_mode_config(start_dir: Path = None) -> dict:
    """
    Load takeover_mode configuration from toolguard_hook files.

    Only reads from toolguard_hook files (NOT from Claude settings files).
    Merges configuration from multiple sources.

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        Dictionary with takeover_mode configuration:
        {
            'enabled': bool,
            'ignored_allow_patterns': List[str],
            'additional_ignored_patterns': List[str],
            'no_match_fallback': str  # 'deny' or 'warn_deny'
        }
        Returns default config if no takeover_mode found in any file.
    """
    default_config = {
        'enabled': False,
        'ignored_allow_patterns': [
            'Bash(*)',
            'Read(*)',
            'Write(*)',
            'Edit(*)',
            'mcp__jetbrains__execute_terminal_command(*)',
        ],
        'additional_ignored_patterns': [],
        'no_match_fallback': 'deny',
    }

    # Discover config files in hierarchy
    config_files = discover_config_files(start_dir)

    # Filter to only toolguard_hook files (NOT Claude settings files)
    hook_files = [(path, fmt) for path, source_type, fmt in config_files if source_type == 'toolguard_hook']

    if not hook_files:
        return default_config

    # Load takeover_mode from all hook files and merge
    merged_config = default_config.copy()

    for path, fmt in hook_files:
        try:
            if fmt == 'toml':
                import tomllib

                with open(path, 'rb') as f:
                    config = tomllib.load(f)
            else:
                with open(path, 'r') as f:
                    config = json.load(f)

            takeover_mode = config.get('takeover_mode', {})
            if not takeover_mode:
                continue

            # Merge enabled (OR logic - any file can enable it)
            if takeover_mode.get('enabled', False):
                merged_config['enabled'] = True

            # Merge ignored_allow_patterns (union)
            for pattern in takeover_mode.get('ignored_allow_patterns', []):
                if pattern not in merged_config['ignored_allow_patterns']:
                    merged_config['ignored_allow_patterns'].append(pattern)

            # Merge additional_ignored_patterns (union)
            for pattern in takeover_mode.get('additional_ignored_patterns', []):
                if pattern not in merged_config['additional_ignored_patterns']:
                    merged_config['additional_ignored_patterns'].append(pattern)

            # Use last no_match_fallback found (priority order)
            if 'no_match_fallback' in takeover_mode:
                merged_config['no_match_fallback'] = takeover_mode['no_match_fallback']

        except Exception:
            continue

    return merged_config


def _load_governed_tools(start_dir: Path = None) -> List[str]:
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
            tools = _load_governed_tools_from_file(hook_file, 'json')
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
        tools = _load_governed_tools_from_file(path, fmt)
        if tools:
            tools_lists.append(tools)

    # If no governed_tools found in any file, use default
    if not tools_lists:
        return ['Bash']

    # Merge all governed tools
    return _merge_governed_tools(tools_lists)


def _load_permissions(start_dir: Path = None) -> Tuple[List[str], List[str]]:
    """
    Load and parse permissions from Claude Code settings files.

    If CLAUDE_SETTINGS_PATH is set, uses ONLY that file (backward compatible).
    Otherwise, discovers and merges permissions from config file hierarchy:
    1. Project .claude/settings.local.json + .claude/toolguard_hook.local.json
    2. Project .claude/settings.json + .claude/toolguard_hook.json
    3. User ~/.claude/settings.local.json + ~/.claude/toolguard_hook.local.json
    4. User ~/.claude/settings.json + ~/.claude/toolguard_hook.json

    Respects takeover_mode configuration:
    - When takeover_mode.enabled is True, filters out patterns from native Claude config
      that match ignored_allow_patterns or additional_ignored_patterns
    - Patterns from toolguard_hook files are NEVER filtered

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        Tuple of (allow_patterns, deny_patterns) where each is a list of strings

    Raises:
        SystemExit: If CLAUDE_SETTINGS_PATH is set but file cannot be loaded
    """
    # Load takeover mode configuration
    takeover_config = load_takeover_mode_config(start_dir)
    takeover_enabled = takeover_config['enabled']
    ignored_patterns = set(takeover_config['ignored_allow_patterns'] + takeover_config['additional_ignored_patterns'])

    # Normalize ignored patterns: strip tool wrappers to match the extracted format
    # that _load_permissions_from_file() produces (e.g. "Bash(*)" -> "*", "Read(/tmp/**)" -> "/tmp/**").
    # _strip_tool_wrapper is the single structural strip shared across the module.
    ignored_patterns = {_strip_tool_wrapper(p) for p in ignored_patterns}

    settings_path = os.environ.get('CLAUDE_SETTINGS_PATH')

    # If CLAUDE_SETTINGS_PATH is set, load from that file AND adjacent toolguard_hook files
    if settings_path:
        print(f'Using config from CLAUDE_SETTINGS_PATH: {settings_path}', file=sys.stderr)
        permissions_list = []

        # Load from the settings file
        try:
            allow_perms, deny_perms = _load_permissions_from_file(Path(settings_path), 'claude', 'json', strict=True)

            # Apply takeover mode filtering for native Claude config
            if takeover_enabled:
                filtered_allow = [p for p in allow_perms if p not in ignored_patterns]
                permissions_list.append((filtered_allow, deny_perms))
            else:
                permissions_list.append((allow_perms, deny_perms))

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
                perms = _load_permissions_from_file(hook_toml, 'toolguard_hook', 'toml')
                permissions_list.append(perms)  # Never filter toolguard_hook patterns
            except Exception as e:
                print(f'Warning: Failed to load {hook_toml}: {e}', file=sys.stderr)
        elif hook_json.exists():
            try:
                perms = _load_permissions_from_file(hook_json, 'toolguard_hook', 'json')
                permissions_list.append(perms)  # Never filter toolguard_hook patterns
            except Exception as e:
                print(f'Warning: Failed to load {hook_json}: {e}', file=sys.stderr)

        return _merge_permissions(permissions_list)

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
            allow_perms, deny_perms = _load_permissions_from_file(path, source_type, fmt)

            # Apply takeover mode filtering for native Claude config files
            if takeover_enabled and source_type == 'claude':
                # Filter out patterns that match ignored patterns (exact string match)
                filtered_allow = [p for p in allow_perms if p not in ignored_patterns]
                filtered_deny = deny_perms  # Don't filter deny patterns
                permissions_list.append((filtered_allow, filtered_deny))
            else:
                # No filtering for toolguard_hook files or when takeover mode disabled
                permissions_list.append((allow_perms, deny_perms))

        except Exception as e:
            print(f'Warning: Failed to load {path}: {e}', file=sys.stderr)
            continue

    # Merge all permissions
    allow_patterns, deny_patterns = _merge_permissions(permissions_list)

    print(f'Loaded {len(allow_patterns)} allow patterns, {len(deny_patterns)} deny patterns', file=sys.stderr)

    return allow_patterns, deny_patterns


# ---------------------------------------------------------------------------
# Public configuration abstraction
# ---------------------------------------------------------------------------
#
# Everything below builds an immutable, file/format-agnostic view of the
# toolguard configuration on top of the internal sourcing/parsing helpers above.
# Clients should use load_configuration() and the Configuration methods rather
# than touching files, formats, or discovery order directly.

def _strip_tool_wrapper(pattern: str) -> str:
    """
    Strip a ``Tool(...)`` wrapper from a permission pattern, if present.

    Permission patterns are authored wrapped as ``Tool(inner)`` (e.g.
    ``Bash(git *)``) but the loaders compare against the unwrapped inner pattern
    (``git *``). This is the single source of truth for that unwrapping. It is
    purely STRUCTURAL: any ``identifier(...)`` shape is stripped, so no
    hand-maintained tool list is needed and new tools require no change. The
    inner body may itself contain parentheses (``Bash(foo(bar))`` -> ``foo(bar)``).

    Returns the inner pattern when wrapped (e.g. ``'Bash(*)' -> '*'``); otherwise
    returns the pattern unchanged (already in extracted form).

    Args:
        pattern: A permission pattern, possibly wrapped in ``Tool(...)``.

    Returns:
        The pattern with any tool wrapper removed.
    """
    match = _TOOL_WRAPPER_RE.fullmatch(pattern)
    if match:
        return match.group(1)
    return pattern


def is_tool_wrapper(pattern: str) -> bool:
    """
    Report whether a permission pattern is a ``Tool(...)`` wrapper.

    Shares the single structural recogniser (``_TOOL_WRAPPER_RE``) with
    :func:`_strip_tool_wrapper`, so the wrapper shape lives in exactly one place.
    Used by clients (e.g. ``config_divergence``) that need to recognise
    tool-scoped native permission strings without re-deriving the regex.

    Args:
        pattern: A candidate permission string.

    Returns:
        True if the whole string is an ``identifier(...)`` tool wrapper.
    """
    return isinstance(pattern, str) and _TOOL_WRAPPER_RE.fullmatch(pattern) is not None


@dataclass(frozen=True)
class Provenance:
    """
    Display-only origin of a single configuration source.

    Carries enough information to tell a human (or a future permission-mover)
    where a layer's content physically came from, without exposing file/format
    decisions as control flow to clients.

    Attributes:
        level: Conceptual level label ('project', 'user', or 'explicit' for
            a CLAUDE_SETTINGS_PATH single-file source).
        source_type: Either 'claude' (native settings) or 'toolguard_hook'.
        file_format: Either 'json' or 'toml'.
        path: Absolute path to the source file (display only).
        specificity: Hierarchy distance from the project root. 0 = most specific
            (project level); larger values are less specific; the user level is
            largest. Used by the more-specific-wins resolver. Sources at the same
            specificity belong to the same hierarchy level.
    """

    level: str
    source_type: str
    file_format: str
    path: Path
    specificity: int = 0

    def describe(self) -> str:
        """Return a short human-readable description of this source."""
        return f'{self.level}: {self.path} [{self.source_type}, {self.file_format}]'


@dataclass(frozen=True)
class ConfigLayer:
    """
    One discovered configuration source, with provenance and parsed content.

    Layers are produced most-specific first (project before user, ``.local``
    before regular). The parsed content is exposed as a read-only mapping so it
    cannot be mutated by clients. Pattern matching is intentionally NOT done
    here; layers carry typed pattern lists that matching code consumes.

    Attributes:
        provenance: Display-only origin of this layer.
        content: Read-only view of the parsed config dict for this source.
    """

    provenance: Provenance
    content: Mapping = field(default_factory=lambda: MappingProxyType({}))

    @property
    def source_type(self) -> str:
        """Convenience accessor for the source type ('claude'/'toolguard_hook')."""
        return self.provenance.source_type

    @property
    def is_native(self) -> bool:
        """True when this layer is a native Claude settings file."""
        return self.provenance.source_type == 'claude'

    @property
    def specificity(self) -> int:
        """Hierarchy specificity of this layer (0 = most specific)."""
        return self.provenance.specificity


@dataclass(frozen=True)
class ToolPatternLayer:
    """
    Per-layer allow/deny patterns for a single tool, with provenance.

    This is the per-layer shape returned by ``Configuration.permission_layers``.
    Patterns are extracted (tool wrapper removed) and takeover filtering has
    already been applied. Phase 1 callers flatten + union these; a future
    per-layer resolver can consume the same shape without changes.

    Attributes:
        provenance: Origin of the patterns in this layer.
        allow: Extracted allow patterns from this layer (order preserved).
        deny: Extracted deny patterns from this layer (order preserved).
    """

    provenance: Provenance
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]


@dataclass(frozen=True)
class TakeoverConfig:
    """
    Resolved takeover-mode configuration.

    Resolution matches current behaviour: ``enabled`` is OR across sources,
    pattern lists are unioned, and ``no_match_fallback`` takes the last value
    seen in discovery (priority) order. NO Phase 5 conflict special-case.

    Attributes:
        enabled: Whether takeover mode is active.
        ignored_allow_patterns: Blanket allow patterns suppressed from native config.
        additional_ignored_patterns: Extra user-supplied ignored patterns.
        no_match_fallback: 'deny' or 'warn_deny'.
    """

    enabled: bool
    ignored_allow_patterns: Tuple[str, ...]
    additional_ignored_patterns: Tuple[str, ...]
    no_match_fallback: str

    def normalized_ignored_patterns(self) -> frozenset:
        """
        Return the set of ignored patterns in extracted (wrapper-free) form.

        Combines ``ignored_allow_patterns`` and ``additional_ignored_patterns``
        and strips any recognised tool wrapper so the values can be compared
        against extracted pattern lists.
        """
        combined = tuple(self.ignored_allow_patterns) + tuple(self.additional_ignored_patterns)
        return frozenset(_strip_tool_wrapper(p) for p in combined)


@dataclass(frozen=True)
class Issue:
    """
    A structured, content-level configuration issue (display/log only).

    Replaces the hand-rolled validation walk in the hook. The config module
    detects issues and returns them; the hook decides whether/where to log.
    The config module performs NO logging side effects.

    Attributes:
        level: Severity label ('warning' or 'error').
        message: Human-readable description of the issue.
        corrective_steps: Suggested remediation.
    """

    level: str
    message: str
    corrective_steps: str


@dataclass(frozen=True)
class Configuration:
    """
    Immutable, file/format-agnostic view of the resolved toolguard config.

    Built by :func:`load_configuration`. Holds the discovered layers (most
    specific first) plus the start directory used for discovery. All semantic
    questions are answered by methods here; clients never touch files/formats.

    Phase 1 is behaviour-preserving: resolution is still union + global
    deny-first over two levels (project + user). The per-layer shape exists so
    a future resolver (Phase 2) can apply more-specific-wins without changing
    the public surface.
    """

    layers: Tuple[ConfigLayer, ...]
    start_dir: Optional[Path] = None

    # -- project root ------------------------------------------------------

    @property
    def project_root(self) -> Optional[Path]:
        """
        Return the resolved project root, or None when none can be found.

        The project root is the anchor for ALL relative paths declared anywhere
        in the configuration (see :meth:`resolve_config_path`). Resolved via
        :func:`find_project_root` from :attr:`start_dir`. None is returned when
        no project marker (``pyproject.toml``/``.git``) is found up to ``~``.
        """
        try:
            return find_project_root(self.start_dir)
        except RuntimeError:
            return None

    def resolve_config_path(self, raw_path: str) -> str:
        """
        Resolve a path declared in configuration against the PROJECT ROOT.

        Any relative path appearing anywhere in configuration -- regardless of
        which level/directory declared it -- resolves against the project root,
        NOT against the ancestor directory that holds the declaring file and NOT
        against the current working directory. This is the single anchor point
        for that rule.

        Absolute paths and ``~``-paths are returned unchanged here (``~`` is
        expanded by downstream matching/normalisation, not by this method).

        Args:
            raw_path: A path string from configuration (e.g. a ``backup_dir`` or
                a relative file-path permission pattern, already stripped of any
                extended-syntax prefix and tool wrapper).

        Returns:
            For a relative path: ``<project_root>/<raw_path>`` as a string (or
            the original when no project root is known). Absolute and ``~`` paths
            are returned unchanged.
        """
        if not raw_path:
            return raw_path
        if raw_path.startswith('/') or raw_path.startswith('~'):
            return raw_path
        root = self.project_root
        if root is None:
            return raw_path
        return str(root / raw_path)

    # -- governed tools ----------------------------------------------------

    def governed_tools(self) -> Tuple[str, ...]:
        """
        Return the resolved list of governed tools.

        Union across all toolguard_hook layers, preserving first-occurrence
        order. Defaults to ``('Bash',)`` when nothing is configured. Mirrors
        the legacy ``_load_governed_tools`` behaviour exactly.
        """
        return tuple(_load_governed_tools(self.start_dir))

    # -- takeover mode -----------------------------------------------------

    def takeover_mode(self) -> TakeoverConfig:
        """
        Return the resolved takeover-mode configuration.

        Resolved exactly as today (enabled=OR, pattern lists=union,
        no_match_fallback=last-wins). No Phase 5 conflict handling.
        """
        raw = load_takeover_mode_config(self.start_dir)
        return TakeoverConfig(
            enabled=bool(raw['enabled']),
            ignored_allow_patterns=tuple(raw['ignored_allow_patterns']),
            additional_ignored_patterns=tuple(raw['additional_ignored_patterns']),
            no_match_fallback=raw['no_match_fallback'],
        )

    # -- permissions -------------------------------------------------------

    def hard_deny(self, tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return the pooled hard-deny (deny, allow) patterns for a tool.

        ``[hard_deny]`` is a toolguard EXTENSION read ONLY from ``toolguard_hook``
        layers -- never from native Claude settings, which have no such concept.
        Unlike the normal more-specific-wins cascade, hard_deny is COLLECTED FROM
        ALL LEVELS INTO ONE POOL (union across the whole hierarchy, de-duplicated,
        order-preserving most-specific first). It is evaluated FIRST, before the
        cascade, and cannot be overridden by any level's normal allow.

        Semantics of the returned lists:

        - ``deny``: a command/path matching any of these is hard-denied UNLESS it
          also matches an ``allow`` carve-out.
        - ``allow``: an EXCEPTION to ``deny`` only (e.g. hard-deny all ``curl``
          EXCEPT ``curl localhost``). It is NOT a forced/normal allow and does
          NOT affect the normal cascade.

        Patterns are returned in extracted form (the ``Tool(...)`` wrapper is
        stripped, exactly like :meth:`permission_layers`), tool-scoped to
        ``tool_name``, and carry the same extended syntax (``[regex]``/``[glob]``/
        ``[native]``) the normal matchers understand. Relative file-path patterns
        are NOT anchored here; anchoring to the project root happens at match time
        in the hook (reusing the Phase 2 anchoring), mirroring normal patterns.

        Args:
            tool_name: Tool to extract hard-deny patterns for (e.g. 'Bash',
                'Read', 'Write', 'Edit').

        Returns:
            Tuple of (deny_patterns, allow_patterns) as immutable, de-duplicated
            tuples pooled across all toolguard_hook layers.
        """
        prefix = f'{tool_name}('
        seen_deny: Dict[str, None] = {}
        seen_allow: Dict[str, None] = {}

        for layer in self.layers:
            # hard_deny is a toolguard extension; ignore native Claude settings.
            if layer.is_native:
                continue
            section = layer.content.get('hard_deny', {})
            if not isinstance(section, dict):
                continue
            for perm in section.get('deny', []):
                if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(')'):
                    seen_deny.setdefault(perm[len(prefix) : -1], None)
            for perm in section.get('allow', []):
                if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(')'):
                    seen_allow.setdefault(perm[len(prefix) : -1], None)

        return tuple(seen_deny.keys()), tuple(seen_allow.keys())

    def permission_layers(self, tool_name: str) -> Tuple[ToolPatternLayer, ...]:
        """
        Return per-layer allow/deny patterns for a tool, most-specific first.

        Each layer carries provenance and the extracted (wrapper-free) patterns
        for ``tool_name`` from that source. Takeover filtering is already
        applied: when takeover mode is enabled, blanket ignored allow patterns
        are removed from native ('claude') layers only. Deny patterns are never
        filtered.

        Phase 1 callers flatten+union these (see :meth:`allow_deny_for`),
        preserving current behaviour. The per-layer shape supports a future
        more-specific-wins resolver without changing this API.

        Args:
            tool_name: Tool to extract patterns for (e.g. 'Bash', 'Read').

        Returns:
            Tuple of :class:`ToolPatternLayer`, ordered most-specific first.
        """
        takeover = self.takeover_mode()
        ignored = takeover.normalized_ignored_patterns() if takeover.enabled else frozenset()

        prefix = f'{tool_name}('
        result = []

        for layer in self.layers:
            permissions = layer.content.get('permissions', {})
            if not isinstance(permissions, dict):
                permissions = {}

            allow = []
            for perm in permissions.get('allow', []):
                if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(')'):
                    pattern = perm[len(prefix) : -1]
                    if takeover.enabled and layer.is_native and pattern in ignored:
                        continue
                    allow.append(pattern)

            deny = []
            for perm in permissions.get('deny', []):
                if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(')'):
                    deny.append(perm[len(prefix) : -1])

            result.append(ToolPatternLayer(provenance=layer.provenance, allow=tuple(allow), deny=tuple(deny)))

        return tuple(result)

    def permission_levels(self, tool_name: str) -> Tuple[Tuple[Tuple[str, ...], Tuple[str, ...]], ...]:
        """
        Group per-layer patterns for a tool into per-LEVEL (allow, deny) pairs.

        Layers sharing a specificity (e.g. a ``.local`` and a regular file in the
        same ``.claude`` directory) are collapsed into a single level, preserving
        within-level priority order. Levels are returned most-specific first --
        the order the more-specific-wins resolver consumes.

        Args:
            tool_name: Tool to resolve patterns for (e.g. 'Bash', 'Read').

        Returns:
            Tuple of (allow_patterns, deny_patterns) pairs, one per hierarchy
            level, ordered most-specific first.
        """
        grouped: Dict[int, Tuple[List[str], List[str]]] = {}
        order: List[int] = []
        for layer in self.permission_layers(tool_name):
            spec = layer.provenance.specificity
            if spec not in grouped:
                grouped[spec] = ([], [])
                order.append(spec)
            allow_acc, deny_acc = grouped[spec]
            allow_acc.extend(layer.allow)
            deny_acc.extend(layer.deny)
        return tuple((tuple(grouped[s][0]), tuple(grouped[s][1])) for s in order)

    def resolve_permission(self, tool_name: str, decide) -> Tuple[str, str]:
        """
        Resolve a permission decision using more-specific-wins across levels.

        Evaluates hierarchy levels MOST-SPECIFIC -> LEAST-SPECIFIC. ``decide`` is
        called per level with that level's (allow, deny) pattern tuples and must
        return a ``(decision, reason)`` pair when the level produces ANY match
        (deny or allow), or ``None`` when the level matches nothing. The FIRST
        level that returns a non-None result decides; the cascade stops there.
        When no level matches anything, the result is a fail-closed DENY.

        Pattern MATCHING lives entirely in ``decide`` (supplied by
        permissions.py / compound.py); this method owns only the level cascade.

        Args:
            tool_name: Tool whose levels to evaluate.
            decide: Callable ``(allow, deny) -> (decision, reason) | None``.

        Returns:
            The winning ``(decision, reason)``, or a default deny when nothing
            matched at any level.
        """
        for allow, deny in self.permission_levels(tool_name):
            result = decide(allow, deny)
            if result is not None:
                return result
        return 'deny', 'Command does not match any allow patterns'

    def allow_deny_for(self, tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return flattened, de-duplicated (allow, deny) patterns for a tool.

        This is the Phase 1 (behaviour-preserving) flattening of
        :meth:`permission_layers`: union across layers in discovery order with
        duplicates removed, mirroring the legacy ``load_file_path_patterns`` and
        Bash ``_load_permissions`` results. Global deny-first matching is applied
        downstream by the matching code, not here.

        Args:
            tool_name: Tool to resolve patterns for.

        Returns:
            Tuple of (allow_patterns, deny_patterns) as immutable tuples.
        """
        seen_allow: Dict[str, None] = {}
        seen_deny: Dict[str, None] = {}
        for layer in self.permission_layers(tool_name):
            for p in layer.allow:
                seen_allow.setdefault(p, None)
            for p in layer.deny:
                seen_deny.setdefault(p, None)
        return tuple(seen_allow.keys()), tuple(seen_deny.keys())

    def bash_permissions(self) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return resolved (allow, deny) Bash command patterns.

        Behaviour-preserving wrapper around the legacy ``_load_permissions``
        path (which also handles the ``CLAUDE_SETTINGS_PATH`` single-file mode
        and emits the discovery diagnostics on stderr). Kept as the command-tool
        entry point so the hook never opens files itself.

        Returns:
            Tuple of (allow_patterns, deny_patterns) as immutable tuples.
        """
        allow, deny = _load_permissions(self.start_dir)
        return tuple(allow), tuple(deny)

    # -- scalars -----------------------------------------------------------

    def scalar(self, name: str, default=None):
        """
        Resolve a top-level scalar setting from a named config section.

        Supports dotted names of the form ``'section.key'`` (e.g.
        ``'config_sync.backup_dir'``). Reads only from toolguard_hook layers,
        last-occurrence wins across discovery order -- matching the legacy
        ``load_config_sync_settings`` resolution. A bare ``name`` resolves a
        top-level key directly.

        Phase 1 is behaviour-preserving. Layers are ordered most-specific first
        (project before user). The legacy ``load_config_sync_settings`` resolver
        iterates discovery order (project first, user last) with last-occurrence
        wins, which means the *user* (least-specific) value wins on conflict. To
        preserve that exact behaviour we iterate ``self.layers`` in forward
        (discovery) order here, so the last layer seen -- the user layer -- wins.

        # FIXME(TOO-8 Phase 2, decision #4): Phase 2 will intentionally switch
        # config_sync (and other scalars) to more-specific-wins (project-wins).
        # That is a conscious behaviour change and must be made test-visible by
        # flipping the pinning test in test/unit/test_configuration.py
        # (test_config_sync_conflict_is_user_wins_phase1). Do NOT change this
        # resolution direction without updating that test.

        Args:
            name: Scalar name, optionally ``'section.key'``.
            default: Value to return when the scalar is absent.

        Returns:
            The resolved value, or ``default`` if not found.
        """
        section: Optional[str]
        if '.' in name:
            section, key = name.split('.', 1)
        else:
            section, key = None, name

        value = default
        # Iterate discovery order (most-specific first, least-specific last) so
        # the last layer seen -- the user layer -- wins on conflict. This matches
        # the legacy last-occurrence-wins resolution exactly (USER-wins).
        for layer in self.layers:
            if layer.is_native:
                continue
            content = layer.content
            if section is not None:
                sect = content.get(section, {})
                if isinstance(sect, dict) and key in sect:
                    value = sect[key]
            else:
                if key in content:
                    value = content[key]
        return value

    def config_sync_settings(self) -> Mapping:
        """
        Return resolved config_sync settings as a read-only mapping.

        Behaviour-preserving wrapper that resolves the same defaults and
        last-wins semantics as the legacy ``load_config_sync_settings``.

        Returns:
            Read-only mapping with keys ``auto_migrate``, ``backup_dir``,
            ``auto_sort_on_migrate``.
        """
        return MappingProxyType(
            {
                'auto_migrate': self.scalar('config_sync.auto_migrate', False),
                'backup_dir': self.scalar('config_sync.backup_dir', 'logs/config-backups'),
                'auto_sort_on_migrate': self.scalar('config_sync.auto_sort_on_migrate', True),
            }
        )

    # -- raw toolguard permissions (for divergence / migration) -----------

    def toolguard_permissions(self) -> Mapping:
        """
        Return raw (wrapper-intact) permissions from toolguard_hook layers.

        Aggregates allow/deny/ask permission strings (exact, with tool
        wrappers) across all toolguard_hook layers, de-duplicated and
        order-preserving. Used by divergence detection and migration tooling so
        those clients never open or parse config files themselves.

        Returns:
            Read-only mapping with keys 'allow', 'deny', 'ask', each a tuple of
            permission strings.
        """
        result = {'allow': [], 'deny': [], 'ask': []}
        for layer in self.layers:
            if layer.is_native:
                continue
            permissions = layer.content.get('permissions', {})
            if not isinstance(permissions, dict):
                continue
            for perm_type in ('allow', 'deny', 'ask'):
                for perm in permissions.get(perm_type, []):
                    if isinstance(perm, str) and perm not in result[perm_type]:
                        result[perm_type].append(perm)
        return MappingProxyType({k: tuple(v) for k, v in result.items()})

    # -- validation --------------------------------------------------------

    def validation_issues(self) -> Tuple[Issue, ...]:
        """
        Return structured content-level configuration issues.

        Replaces the hand-rolled file walk in the hook's startup validation.
        Detects:

        - Both a TOML and a JSON config file present at the same level/base.
        - Unsupported tools referenced in toolguard_hook permissions.
        - Tools referenced in permissions but absent from governed_tools.

        The config module only RETURNS issues; logging is the hook's job.

        Returns:
            Tuple of :class:`Issue`, in detection order (duplicate-file issues
            first, then permission-validation issues).
        """
        issues: List[Issue] = []

        # 1) Both TOML and JSON at the same (directory, base) -> warn.
        seen_bases: Dict[Tuple[str, str], str] = {}
        for layer in self.layers:
            path = layer.provenance.path
            base_name = path.stem
            parent = str(path.parent)
            key = (parent, base_name)
            fmt = layer.provenance.file_format
            if key in seen_bases:
                if seen_bases[key] != fmt:
                    issues.append(
                        Issue(
                            level='warning',
                            message=f'Both {base_name}.toml and {base_name}.json exist in {parent}',
                            corrective_steps=(
                                f'Remove one of the files to avoid confusion. TOML ({base_name}.toml) is being used.'
                            ),
                        )
                    )
            else:
                seen_bases[key] = fmt

        # 2) Permission validation over the merged toolguard_hook content only.
        merged_config: Dict = {
            'governed_tools': [],
            'additional_supported_tools': [],
            'permissions': {'allow': [], 'deny': [], 'ask': []},
        }
        for layer in self.layers:
            if layer.is_native:
                continue
            content = layer.content
            for tool in content.get('governed_tools', []):
                if tool not in merged_config['governed_tools']:
                    merged_config['governed_tools'].append(tool)
            for tool in content.get('additional_supported_tools', []):
                if tool not in merged_config['additional_supported_tools']:
                    merged_config['additional_supported_tools'].append(tool)
            permissions = content.get('permissions', {})
            if isinstance(permissions, dict):
                for perm_type in ('allow', 'deny', 'ask'):
                    for perm in permissions.get(perm_type, []):
                        if perm not in merged_config['permissions'][perm_type]:
                            merged_config['permissions'][perm_type].append(perm)

        for warning in validate_permissions(merged_config):
            issues.append(
                Issue(
                    level=warning.get('level', 'warning'),
                    message=warning['message'],
                    corrective_steps=warning['corrective_steps'],
                )
            )

        return tuple(issues)

    # -- provenance / introspection ---------------------------------------

    def describe_sources(self) -> Tuple[str, ...]:
        """Return human-readable descriptions of all discovered sources."""
        return tuple(layer.provenance.describe() for layer in self.layers)


def _parse_source(path: Path, file_format: str) -> Optional[dict]:
    """
    Parse a single config source file, returning its dict or None on failure.

    Args:
        path: Path to the config file.
        file_format: 'json' or 'toml'.

    Returns:
        Parsed dict, or None if the file cannot be read/parsed.
    """
    try:
        if file_format == 'toml':
            import tomllib

            with open(path, 'rb') as f:
                return tomllib.load(f)
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001 - tolerate any unreadable source
        print(f'Warning: Failed to load {path}: {e}', file=sys.stderr)
        return None


def _level_for_path(path: Path) -> str:
    """
    Determine the conceptual level label for a discovered source path.

    Args:
        path: Path to the source file.

    Returns:
        'user' if the path is under the user's ~/.claude directory, otherwise
        'project'.
    """
    user_claude = Path.home() / '.claude'
    try:
        path.resolve().relative_to(user_claude.resolve())
        return 'user'
    except ValueError:
        return 'project'


def load_configuration(start_dir: Path = None, ignore_env_override: bool = False) -> Configuration:
    """
    Load the toolguard configuration as an immutable :class:`Configuration`.

    This is the single public entry point. It performs all discovery and
    parsing internally and returns a file/format-agnostic view. When
    ``CLAUDE_SETTINGS_PATH`` is set, a single explicit source (plus any adjacent
    ``toolguard_hook`` file) is used, bypassing the hierarchy -- matching the
    legacy behaviour. The runtime hook relies on this single-file behaviour, so
    it is the default.

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to
            the current working directory.
        ignore_env_override: When True, ignore ``CLAUDE_SETTINGS_PATH`` and
            always discover the hierarchy rooted at the project. This exists for
            the migration/divergence tooling, whose write-target selection is
            already project-based; forcing the read path to be project-based too
            keeps that tooling internally consistent and unaffected by a stale
            ``CLAUDE_SETTINGS_PATH`` pointing at an unrelated project. The
            runtime hook never sets this.

    Returns:
        An immutable :class:`Configuration`. Note that command-permission
        resolution (Bash) and governed-tools/takeover resolution intentionally
        delegate to the legacy loaders so that ``CLAUDE_SETTINGS_PATH`` handling
        and stderr diagnostics remain byte-for-byte identical in Phase 1.
    """
    layers: List[ConfigLayer] = []

    settings_path = None if ignore_env_override else os.environ.get('CLAUDE_SETTINGS_PATH')
    if settings_path:
        explicit = Path(settings_path)
        content = _parse_source(explicit, 'json')
        if content is not None:
            layers.append(
                ConfigLayer(
                    provenance=Provenance('explicit', 'claude', 'json', explicit),
                    content=MappingProxyType(content),
                )
            )
        settings_dir = explicit.parent
        hook_toml = settings_dir / 'toolguard_hook.toml'
        hook_json = settings_dir / 'toolguard_hook.json'
        if hook_toml.exists():
            content = _parse_source(hook_toml, 'toml')
            if content is not None:
                layers.append(
                    ConfigLayer(
                        provenance=Provenance('explicit', 'toolguard_hook', 'toml', hook_toml),
                        content=MappingProxyType(content),
                    )
                )
        elif hook_json.exists():
            content = _parse_source(hook_json, 'json')
            if content is not None:
                layers.append(
                    ConfigLayer(
                        provenance=Provenance('explicit', 'toolguard_hook', 'json', hook_json),
                        content=MappingProxyType(content),
                    )
                )
        return Configuration(layers=tuple(layers), start_dir=start_dir)

    for path, source_type, file_format, specificity in _discover_levels(start_dir):
        content = _parse_source(path, file_format)
        if content is None:
            continue
        level = _level_for_path(path)
        layers.append(
            ConfigLayer(
                provenance=Provenance(level, source_type, file_format, path, specificity),
                content=MappingProxyType(content),
            )
        )

    return Configuration(layers=tuple(layers), start_dir=start_dir)


# ---------------------------------------------------------------------------
# Internal helpers shared with divergence/migration tooling
# ---------------------------------------------------------------------------
#
# These keep all JSON/TOML parsing inside the config module while preserving the
# legacy (config_files) signatures that divergence/migration code and their tests
# rely on. Callers pass the discovered (path, source_type, format) triples; the
# parsing/format-branching lives here, not in those clients.


def _toolguard_permissions_from_sources(config_files: List[Tuple[Path, str, str]]) -> Dict[str, List[str]]:
    """
    Extract raw allow/deny/ask permissions from toolguard_hook sources.

    Parses each toolguard_hook source (JSON or TOML), aggregating permission
    strings (with tool wrappers intact), de-duplicated and order-preserving.
    Native ('claude') sources are skipped. All file/format handling is internal
    to the config module.

    Args:
        config_files: List of (path, source_type, format) triples as produced
            by :func:`discover_config_files`.

    Returns:
        Dict with keys 'allow', 'deny', 'ask', each a list of permission strings.
    """
    result: Dict[str, List[str]] = {'allow': [], 'deny': [], 'ask': []}
    for path, source_type, file_format in config_files:
        if source_type != 'toolguard_hook':
            continue
        content = _parse_source(path, file_format)
        if content is None:
            continue
        permissions = content.get('permissions', {})
        if not isinstance(permissions, dict):
            continue
        for perm_type in ('allow', 'deny', 'ask'):
            for perm in permissions.get(perm_type, []):
                if isinstance(perm, str) and perm not in result[perm_type]:
                    result[perm_type].append(perm)
    return result


def config_sync_settings_from_sources(config_files: List[Tuple[Path, str, str]]) -> Dict:
    """
    Resolve config_sync settings from toolguard_hook sources.

    Parses each toolguard_hook source and applies last-occurrence-wins
    resolution over discovery order, returning defaults for missing values.
    All file/format handling is internal to the config module.

    Args:
        config_files: List of (path, source_type, format) triples as produced
            by :func:`discover_config_files`.

    Returns:
        Dict with keys 'auto_migrate', 'backup_dir', 'auto_sort_on_migrate'.
    """
    resolved: Dict = {
        'auto_migrate': False,
        'backup_dir': 'logs/config-backups',
        'auto_sort_on_migrate': True,
    }
    for path, source_type, file_format in config_files:
        if source_type != 'toolguard_hook':
            continue
        content = _parse_source(path, file_format)
        if content is None:
            continue
        config_sync = content.get('config_sync', {})
        if not isinstance(config_sync, dict) or not config_sync:
            continue
        for key in ('auto_migrate', 'backup_dir', 'auto_sort_on_migrate'):
            if key in config_sync:
                resolved[key] = config_sync[key]
    return resolved
