"""
Unattended migration of divergent permissions from settings.local.json into
the project's toolguard config, at most once per calendar day per project.
"""

from pathlib import Path
from typing import Dict, List

from toolguard import ambient, once_per
from toolguard.config import config_sync_settings_from_sources, load_configuration
from toolguard.config_divergence import (
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)
from toolguard.error_reporter import report_notice, report_warning
from toolguard.once_per import Repeat
from toolguard.permission_migration import MigrationOutcome, migrate

#: Once-per-day throttle for the automatic migration below.
AUTO_MIGRATION = once_per.day("auto_migration", "automatic permission migration")

#: How long ``migrate()`` waits for this project's lock when called from
#: here. Sub-second deliberately: this runs on the synchronous PreToolUse
#: hook's critical path, so a contended lock should decline fast rather than
#: stall a live tool call.
AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS = 1.0


def load_config_sync_settings(config_files: List[tuple]) -> Dict:
    """Resolve the ``config_sync`` settings, reading only toolguard_hook sources."""
    return config_sync_settings_from_sources(config_files)


def run_auto_migration(
    project_root: Path, config_sync: Dict, takeover_config: Dict
) -> bool:
    """
    Migrate this project's divergent permissions, at most once per day.

    The day's slot is claimed immediately before ``migrate()`` -- never
    before the analysis that decides whether there is anything to migrate --
    so an exception during that analysis does not burn the day. Nothing
    releases the claim afterwards, so a migration that fails or is declined
    waits for the next day rather than retrying. When the once-per-day
    guarantee itself cannot be verified, the migration is skipped rather
    than run.

    Args:
        project_root: Project root.
        config_sync: Supplies ``backup_dir`` and ``auto_sort_on_migrate``.
        takeover_config: Takeover mode settings; its ignored patterns are
            honoured only when ``enabled`` is set.

    Returns:
        True if a migration ran and succeeded; False in every other case,
        including "nothing to migrate" and "already attempted today".

    Side effects:
        When ``migrate()`` finds anything to migrate it backs up and rewrites
        ``settings.local.json`` and the toolguard config file. Progress and
        outcome are reported via :mod:`toolguard.error_reporter`.
    """
    if AUTO_MIGRATION.done(project_root):
        # The run() below would no-op anyway; this skips the analysis first.
        return False

    # ignore_env_override=True: this writes the project's own files, so it must
    # read the project's hierarchy, not whatever CLAUDE_SETTINGS_PATH points at.
    config = load_configuration(project_root, ignore_env_override=True)

    backup_dir_str = config_sync.get("backup_dir", "logs/config-backups")
    backup_dir = ambient.expanduser(config.resolve_config_path(backup_dir_str))

    auto_sort = config_sync.get("auto_sort_on_migrate", True)

    settings_path = project_root / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return False

    native_perms = get_native_permissions(settings_path)
    toolguard_perms = get_toolguard_permissions(config)

    ignored_patterns = []
    if takeover_config.get("enabled", False):
        ignored_patterns = takeover_config.get(
            "ignored_allow_patterns", []
        ) + takeover_config.get("additional_ignored_patterns", [])

    divergent = find_divergent_patterns(
        native_perms,
        toolguard_perms,
        ignored_patterns,
        governed_tools=set(config.governed_tools()),
    )
    total_divergent = sum(len(patterns) for patterns in divergent.values())

    if total_divergent == 0:
        return False

    def _migrate() -> bool:
        """Run migrate() and report its outcome. The day's slot is already claimed."""
        report_notice("[TOOLGUARD AUTO-MIGRATION] Running automatic migration...")
        try:
            outcome = migrate(
                project_root=project_root,
                dry_run=False,
                auto_sort=auto_sort,
                backup_dir=backup_dir,
                lock_timeout_seconds=AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS,
            )
        except Exception as e:
            report_warning(
                f"[TOOLGUARD AUTO-MIGRATION] Migration error: {e}",
                "Check the migration's backup and settings.local.json, then retry.",
            )
            return False
        if outcome is MigrationOutcome.DECLINED_LOCKED:
            # migrate() attempted nothing and wrote nothing, so this is a
            # notice rather than a failure.
            report_notice(
                "[TOOLGUARD AUTO-MIGRATION] Another migration is already "
                "running for this project; skipping."
            )
            return False
        if outcome is not MigrationOutcome.SUCCEEDED:
            report_warning(
                "[TOOLGUARD AUTO-MIGRATION] Migration failed",
                "Check the migration's backup and settings.local.json, then retry.",
            )
            return False
        # MigrationOutcome carries no count, and migrate() resolves takeover
        # mode from the PROJECT'S OWN config, which can disagree with this
        # call's caller-supplied takeover_config -- so total_divergent (the
        # pre-analysis above) is not always what migrate() actually wrote.
        # Re-derive the count against the same source of truth migrate()
        # itself used, from the pre-migration snapshot already in hand,
        # rather than claim a number migrate() never confirmed.
        real_takeover = config.takeover_mode()
        real_ignored_patterns = []
        if real_takeover.enabled:
            real_ignored_patterns = list(real_takeover.ignored_allow_patterns) + list(
                real_takeover.additional_ignored_patterns
            )
        migrated_count = sum(
            len(patterns)
            for patterns in find_divergent_patterns(
                native_perms,
                toolguard_perms,
                real_ignored_patterns,
                governed_tools=set(config.governed_tools()),
            ).values()
        )
        report_notice(
            f"[TOOLGUARD AUTO-MIGRATION] Successfully migrated {migrated_count} pattern(s)"
        )
        return True

    migrated = AUTO_MIGRATION.run(project_root, _migrate, repeating=Repeat.UNSAFE)
    return bool(migrated)
