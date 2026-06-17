"""
Auto-migration module for toolguard.

Provides automatic consolidation of permissions from settings.local.json
to toolguard configuration files when divergence is detected.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

from toolguard.config import config_sync_settings_from_sources
from toolguard.config_divergence import (
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)


def get_marker_file_path(logs_dir: Path, marker_date: date) -> Path:
    """
    Get the path to a migration marker file for a specific date.

    Marker files use the format: .toolguard-migration-YYYY-MM-DD

    Args:
        logs_dir: Directory where marker files are stored
        marker_date: Date for the marker file

    Returns:
        Path to the marker file
    """
    filename = f'.toolguard-migration-{marker_date.strftime("%Y-%m-%d")}'
    return logs_dir / filename


def marker_exists_for_today(logs_dir: Path) -> bool:
    """
    Check if a migration marker file exists for today.

    Args:
        logs_dir: Directory where marker files are stored

    Returns:
        True if marker file exists for today, False otherwise
    """
    today_marker = get_marker_file_path(logs_dir, date.today())
    return today_marker.exists()


def create_marker_file(logs_dir: Path) -> None:
    """
    Create a marker file for today to track that migration was run.

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
        print(f'Warning: Failed to create migration marker file {today_marker}: {e}', file=sys.stderr)
        raise


def cleanup_old_markers(logs_dir: Path, days: int = 7) -> None:
    """
    Remove migration marker files older than the specified number of days.

    This prevents accumulation of old marker files over time.

    Args:
        logs_dir: Directory where marker files are stored
        days: Number of days to keep (default: 7)
    """
    if not logs_dir.exists():
        return

    cutoff_date = date.today() - timedelta(days=days)

    try:
        for marker_file in logs_dir.glob('.toolguard-migration-*'):
            try:
                # Format: .toolguard-migration-YYYY-MM-DD
                date_str = marker_file.name.replace('.toolguard-migration-', '')
                file_date = date.fromisoformat(date_str)

                if file_date < cutoff_date:
                    marker_file.unlink()
            except (ValueError, OSError):
                # Skip files that don't match expected format or can't be deleted
                continue
    except OSError:
        # If we can't list directory, just continue
        pass


def load_config_sync_settings(config_files: List[tuple]) -> Dict:
    """
    Load config_sync settings from toolguard_hook config files.

    Only reads from toolguard_hook files (not Claude settings files).
    Returns defaults for any missing values.

    Args:
        config_files: List of (path, source_type, format) tuples from discover_config_files()

    Returns:
        Dictionary with config_sync settings:
        {
            'auto_migrate': bool,
            'backup_dir': str,
            'auto_sort_on_migrate': bool
        }
        Returns defaults if no config_sync section found.
    """
    # Delegate parsing/format handling to the config module so this client never
    # opens files or branches on file format. Last-occurrence-wins resolution
    # and defaults are owned by the config module.
    return config_sync_settings_from_sources(config_files)


def should_run_migration(logs_dir: Path) -> bool:
    """
    Check if migration should run based on marker file.

    Returns False if migration already ran today (marker file exists).

    Args:
        logs_dir: Directory where marker files are stored

    Returns:
        True if migration should run, False if already ran today
    """
    return not marker_exists_for_today(logs_dir)


def run_auto_migration(project_root: Path, logs_dir: Path, config_sync: Dict, takeover_config: Dict) -> bool:
    """
    Run automatic migration of permissions from settings.local.json to toolguard config.

    Creates backups, migrates divergent patterns, and creates marker file.

    Args:
        project_root: Path to project root directory
        logs_dir: Directory for logs and marker files
        config_sync: Config sync settings (auto_sort_on_migrate, backup_dir)
        takeover_config: Takeover mode configuration (for ignored patterns)

    Returns:
        True if migration succeeded, False if failed or nothing to migrate

    Side effects:
        - Creates backup files
        - Modifies settings.local.json
        - Modifies or creates toolguard config file
        - Creates marker file
        - Prints status messages to stderr
    """
    from toolguard.config import discover_config_files
    from toolguard.scripts.migrate_permissions import migrate

    # Check if we've already migrated today
    if not should_run_migration(logs_dir):
        return False

    # Determine backup directory
    backup_dir_str = config_sync.get('backup_dir', 'logs/config-backups')
    if Path(backup_dir_str).is_absolute():
        backup_dir = Path(backup_dir_str)
    else:
        backup_dir = project_root / backup_dir_str

    # Determine auto_sort setting
    auto_sort = config_sync.get('auto_sort_on_migrate', True)

    # Check if there's anything to migrate
    settings_path = project_root / '.claude' / 'settings.local.json'
    if not settings_path.exists():
        return False

    native_perms = get_native_permissions(settings_path)
    config_files = discover_config_files(project_root)
    toolguard_perms = get_toolguard_permissions(config_files)

    # Get ignored patterns from takeover config
    ignored_patterns = []
    if takeover_config.get('enabled', False):
        ignored_patterns = takeover_config.get('ignored_allow_patterns', []) + takeover_config.get(
            'additional_ignored_patterns', []
        )

    # Find divergent patterns
    divergent = find_divergent_patterns(native_perms, toolguard_perms, ignored_patterns)
    total_divergent = sum(len(patterns) for patterns in divergent.values())

    if total_divergent == 0:
        return False

    # Run migration
    print('[TOOLGUARD AUTO-MIGRATION] Running automatic migration...', file=sys.stderr)
    try:
        exit_code = migrate(
            project_root=project_root,
            dry_run=False,
            auto_sort=auto_sort,
            backup_dir=backup_dir,
        )

        if exit_code == 0:
            print(f'[TOOLGUARD AUTO-MIGRATION] Successfully migrated {total_divergent} pattern(s)', file=sys.stderr)

            # Create marker file
            try:
                create_marker_file(logs_dir)
                cleanup_old_markers(logs_dir, days=7)
            except OSError:
                # If we can't create marker, continue (migration was still successful)
                pass

            return True
        else:
            print('[TOOLGUARD AUTO-MIGRATION] Migration failed', file=sys.stderr)
            return False

    except Exception as e:
        print(f'[TOOLGUARD AUTO-MIGRATION] Migration error: {e}', file=sys.stderr)
        return False
