"""
Auto-migration module for toolguard.

Provides automatic consolidation of permissions from settings.local.json
to toolguard configuration files when divergence is detected.
"""

from pathlib import Path
from typing import Dict, List

from toolguard import once_per
from toolguard.config import config_sync_settings_from_sources, load_configuration
from toolguard.config_divergence import (
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)
from toolguard.error_reporter import report_notice, report_warning
from toolguard.once_per import Repeat
from toolguard.permission_migration import migrate

#: The single named object for this module's once-per-day throttling. One
#: name carries both the key and the human description (TOO-45 punch-list
#: #01 item 4) -- no separate _KEY constant to drift from it.
AUTO_MIGRATION = once_per.day("auto_migration", "automatic permission migration")


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


def run_auto_migration(
    project_root: Path, config_sync: Dict, takeover_config: Dict
) -> bool:
    """
    Run automatic migration of permissions from settings.local.json to toolguard config.

    Creates backups and migrates divergent patterns, at most once per day.
    The day's slot is claimed only immediately before ``migrate()`` itself --
    the side effect being deduplicated -- never before the analysis that
    decides whether there's anything to migrate, so an exception raised
    during that analysis never leaves the day's slot claimed with nothing
    done. That closes the real race this replaces: two concurrent processes
    could previously both pass a stale "already ran today?" check and both
    run ``migrate()`` (which writes settings.local.json and the toolguard
    config) at once. A cheap read-only pre-check skips the analysis entirely
    on an already-migrated day.

    ``migrate()`` must NOT run when the once-per-day guarantee itself is
    unavailable: two concurrent processes could then both migrate at once
    with no mutual exclusion, and last-writer-wins can silently discard one
    process's changes (TOO-45 punch-list #15). ``AUTO_MIGRATION.run(...,
    repeating=Repeat.UNSAFE)`` makes that choice explicit; see
    :class:`toolguard.once_per.Repeat`.

    The claim is NOT released when ``migrate()`` fails. This function's only
    production caller (:func:`toolguard.hook._run_divergence_check`) is only
    reached when :func:`toolguard.config_divergence.check_and_warn_divergence`
    itself claims the day's ``divergence_warning`` slot, which happens at
    most once a day -- so there is never a later same-day call to retry
    against. A failed migration is retried the next day (TOO-45 D4: an
    earlier version released this claim on failure, but the release was
    unreachable through the only real caller and existed only as a promise
    two direct-call tests pinned).

    Args:
        project_root: Path to project root directory
        config_sync: Config sync settings (auto_sort_on_migrate, backup_dir)
        takeover_config: Takeover mode configuration (for ignored patterns)

    Returns:
        True if migration succeeded, False if failed, skipped, already
        attempted today, or nothing needs migrating.

    Side effects:
        - Creates backup files
        - Modifies settings.local.json
        - Modifies or creates toolguard config file
        - Reports status via :mod:`toolguard.error_reporter`
    """
    if AUTO_MIGRATION.done(project_root):
        # Already migrated today -- skip the analysis entirely.
        return False

    # ignore_env_override=True: migration is project-scoped end-to-end (it writes
    # to this project's files), so it must read this project's hierarchy rather
    # than whatever CLAUDE_SETTINGS_PATH happens to point at.
    config = load_configuration(project_root, ignore_env_override=True)

    # Determine backup directory. A relative backup_dir is anchored to the PROJECT
    # ROOT via the config module's single anchoring rule (regardless of which
    # level declared it); absolute and ~ paths are honoured as written.
    backup_dir_str = config_sync.get("backup_dir", "logs/config-backups")
    backup_dir = Path(config.resolve_config_path(backup_dir_str)).expanduser()

    # Determine auto_sort setting
    auto_sort = config_sync.get("auto_sort_on_migrate", True)

    # Check if there's anything to migrate
    settings_path = project_root / ".claude" / "settings.local.json"
    if not settings_path.exists():
        # No claim was ever taken, so there's nothing to release.
        return False

    native_perms = get_native_permissions(settings_path)
    toolguard_perms = get_toolguard_permissions(config)

    # Get ignored patterns from takeover config
    ignored_patterns = []
    if takeover_config.get("enabled", False):
        ignored_patterns = takeover_config.get(
            "ignored_allow_patterns", []
        ) + takeover_config.get("additional_ignored_patterns", [])

    # Find divergent patterns (governed tools only: never auto-migrate a rule for a
    # tool toolguard does not govern -- it would become inert; issue #1).
    divergent = find_divergent_patterns(
        native_perms,
        toolguard_perms,
        ignored_patterns,
        governed_tools=set(config.governed_tools()),
    )
    total_divergent = sum(len(patterns) for patterns in divergent.values())

    if total_divergent == 0:
        # No claim was ever taken, so there's nothing to release.
        return False

    def _migrate() -> bool:
        """Run migrate(), reporting outcome; the once-per-day slot is already ours."""
        report_notice("[TOOLGUARD AUTO-MIGRATION] Running automatic migration...")
        try:
            exit_code = migrate(
                project_root=project_root,
                dry_run=False,
                auto_sort=auto_sort,
                backup_dir=backup_dir,
            )
        except Exception as e:
            report_warning(
                f"[TOOLGUARD AUTO-MIGRATION] Migration error: {e}",
                "Check the migration's backup and settings.local.json, then retry.",
            )
            return False
        if exit_code != 0:
            report_warning(
                "[TOOLGUARD AUTO-MIGRATION] Migration failed",
                "Check the migration's backup and settings.local.json, then retry.",
            )
            return False
        report_notice(
            f"[TOOLGUARD AUTO-MIGRATION] Successfully migrated {total_divergent} pattern(s)"
        )
        return True

    migrated = AUTO_MIGRATION.run(project_root, _migrate, repeating=Repeat.UNSAFE)
    return bool(migrated)
