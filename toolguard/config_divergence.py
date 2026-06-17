"""
Config divergence detection for toolguard.

Detects when Claude adds permissions to settings.local.json that are not
present in toolguard config, helping users identify configuration drift.
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

from toolguard.config import toolguard_permissions_from_sources
from toolguard.error_log import log_warning


def get_marker_file_path(logs_dir: Path, marker_date: date) -> Path:
    """
    Get the path to a divergence marker file for a specific date.

    Marker files use the format: .toolguard-divergence-warned-YYYY-MM-DD

    Args:
        logs_dir: Directory where marker files are stored
        marker_date: Date for the marker file

    Returns:
        Path to the marker file
    """
    filename = f'.toolguard-divergence-warned-{marker_date.strftime("%Y-%m-%d")}'
    return logs_dir / filename


def marker_exists_for_today(logs_dir: Path) -> bool:
    """
    Check if a divergence warning marker file exists for today.

    Args:
        logs_dir: Directory where marker files are stored

    Returns:
        True if marker file exists for today, False otherwise
    """
    today_marker = get_marker_file_path(logs_dir, date.today())
    return today_marker.exists()


def create_marker_file(logs_dir: Path) -> None:
    """
    Create a marker file for today to track that divergence warning was issued.

    Creates the logs directory if it doesn't exist.

    Args:
        logs_dir: Directory where marker files are stored

    Raises:
        OSError: If unable to create marker file or directory
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    today_marker = get_marker_file_path(logs_dir, date.today())
    try:
        today_marker.touch()
    except OSError as e:
        print(f'Warning: Failed to create divergence marker file {today_marker}: {e}', file=sys.stderr)
        raise


def cleanup_old_markers(logs_dir: Path, days: int = 7) -> None:
    """
    Remove divergence marker files older than the specified number of days.

    This prevents accumulation of old marker files over time.

    Args:
        logs_dir: Directory where marker files are stored
        days: Number of days to keep (default: 7)
    """
    if not logs_dir.exists():
        return

    cutoff_date = date.today() - timedelta(days=days)

    try:
        for marker_file in logs_dir.glob('.toolguard-divergence-warned-*'):
            try:
                # Format: .toolguard-divergence-warned-YYYY-MM-DD
                date_str = marker_file.name.replace('.toolguard-divergence-warned-', '')
                file_date = date.fromisoformat(date_str)

                if file_date < cutoff_date:
                    marker_file.unlink()
            except (ValueError, OSError):
                # Skip files that don't match expected format or can't be deleted
                continue
    except OSError:
        # If we can't list directory, just continue
        pass


def get_native_permissions(settings_path: Path) -> Dict[str, List[str]]:
    """
    Load allow/deny/ask permissions from Claude's native settings.local.json.

    Extracts patterns for governed tools (Bash, Read, Write, Edit) from the
    permissions.allow, permissions.deny, and permissions.ask lists.

    Args:
        settings_path: Path to settings.local.json file

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each containing list of patterns.
        Returns empty dict if file doesn't exist or can't be parsed.
    """
    if not settings_path.exists():
        return {'allow': [], 'deny': [], 'ask': []}

    try:
        with open(settings_path, 'r') as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError, Exception) as e:
        print(f'Warning: Failed to load {settings_path}: {e}', file=sys.stderr)
        return {'allow': [], 'deny': [], 'ask': []}

    permissions = config.get('permissions', {})

    result = {'allow': [], 'deny': [], 'ask': []}

    # Extract patterns for governed tools
    governed_tool_prefixes = ['Bash(', 'Read(', 'Write(', 'Edit(']

    for perm_type in ['allow', 'deny', 'ask']:
        for perm in permissions.get(perm_type, []):
            if isinstance(perm, str):
                # Check if this is a governed tool pattern
                for prefix in governed_tool_prefixes:
                    if perm.startswith(prefix) and perm.endswith(')'):
                        result[perm_type].append(perm)
                        break

    return result


def get_toolguard_permissions(config_files: List[tuple]) -> Dict[str, List[str]]:
    """
    Extract permissions from toolguard_hook config files.

    Only processes toolguard_hook files (not Claude settings files).
    Merges permissions from multiple files.

    Args:
        config_files: List of (path, source_type, format) tuples from discover_config_files()

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each containing list of patterns
    """
    # Delegate parsing/format handling to the config module so this client never
    # opens files or branches on file format.
    return toolguard_permissions_from_sources(config_files)


def find_divergent_patterns(
    native: Dict[str, List[str]], toolguard: Dict[str, List[str]], ignored_patterns: List[str]
) -> Dict[str, List[str]]:
    """
    Find patterns in native config that are not in toolguard config.

    Uses exact string matching for pattern comparison. In takeover mode,
    patterns matching ignored_patterns are excluded (expected blanket allows).

    Args:
        native: Native permissions from settings.local.json
        toolguard: Toolguard permissions from toolguard_hook files
        ignored_patterns: Patterns to ignore (from takeover_mode.ignored_allow_patterns)

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each containing divergent patterns
    """
    ignored_set = set(ignored_patterns)

    result = {'allow': [], 'deny': [], 'ask': []}

    for perm_type in ['allow', 'deny', 'ask']:
        native_patterns = set(native.get(perm_type, []))
        toolguard_patterns = set(toolguard.get(perm_type, []))

        # Find patterns in native but not in toolguard
        divergent = native_patterns - toolguard_patterns

        # Filter out ignored patterns (only for 'allow' type in takeover mode)
        if perm_type == 'allow':
            divergent = divergent - ignored_set

        result[perm_type] = sorted(list(divergent))

    return result


def check_and_warn_divergence(project_root: Path, logs_dir: Path, takeover_config: Dict) -> List[str]:
    """
    Check for config divergence and issue warning if found.

    Scans settings.local.json for patterns not present in toolguard config.
    Warning is deduplicated using date-stamped marker files (once per day).

    Args:
        project_root: Path to project root
        logs_dir: Directory where logs and marker files are stored
        takeover_config: Takeover mode configuration dict with ignored_allow_patterns

    Returns:
        List of divergent patterns found (for testing), or empty list if none
    """
    # Check if we've already warned today
    if marker_exists_for_today(logs_dir):
        return []

    # Load native permissions from settings.local.json
    settings_path = project_root / '.claude' / 'settings.local.json'
    native_perms = get_native_permissions(settings_path)

    # Load toolguard permissions from config files
    from toolguard.config import discover_config_files

    config_files = discover_config_files(project_root)
    toolguard_perms = get_toolguard_permissions(config_files)

    # Find divergent patterns
    ignored_patterns = takeover_config.get('ignored_allow_patterns', [])
    if takeover_config.get('enabled', False):
        # In takeover mode, also include additional_ignored_patterns
        ignored_patterns = ignored_patterns + takeover_config.get('additional_ignored_patterns', [])

    divergent = find_divergent_patterns(native_perms, toolguard_perms, ignored_patterns)

    # Collect all divergent patterns
    all_divergent = []
    for perm_type in ['allow', 'deny', 'ask']:
        all_divergent.extend(divergent[perm_type])

    if not all_divergent:
        return []

    # Format warning message
    warning_lines = ['[TOOLGUARD WARNING] New permission(s) found in settings.local.json but not in toolguard config:']
    for pattern in all_divergent[:10]:  # Limit to first 10 for readability
        warning_lines.append(f'  - {pattern}')

    if len(all_divergent) > 10:
        warning_lines.append(f'  ... and {len(all_divergent) - 10} more')

    warning_message = '\n'.join(warning_lines)
    corrective_steps = (
        'Consider migrating to toolguard config. Run: uv run python -m toolguard.scripts.migrate_permissions'
    )

    # Write to stdout
    print(warning_message, file=sys.stderr)

    # Write to error log with deduplication
    log_warning(warning_message, corrective_steps, logs_dir)

    # Create marker file
    try:
        create_marker_file(logs_dir)
        cleanup_old_markers(logs_dir, days=7)
    except OSError:
        # If we can't create marker, continue (warning was still logged)
        pass

    return all_divergent
