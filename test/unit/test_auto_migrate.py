"""
Unit tests for auto_migrate module.

Tests automatic permission migration functionality including config loading,
marker file management, and integration with migration script.
"""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.auto_migrate import (
    cleanup_old_markers,
    create_marker_file,
    get_marker_file_path,
    load_config_sync_settings,
    marker_exists_for_today,
    run_auto_migration,
    should_run_migration,
)


class TestMarkerFiles(unittest.TestCase):
    """Test marker file operations for once-per-day execution."""

    def test_get_marker_file_path(self):
        """Test marker file path generation."""
        logs_dir = Path('/tmp/logs')
        test_date = date(2026, 2, 5)

        marker_path = get_marker_file_path(logs_dir, test_date)

        self.assertEqual(marker_path, logs_dir / '.toolguard-migration-2026-02-05')

    def test_marker_exists_for_today_false(self):
        """Test marker_exists_for_today returns False when no marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            result = marker_exists_for_today(logs_dir)

            self.assertFalse(result)

    def test_marker_exists_for_today_true(self):
        """Test marker_exists_for_today returns True when marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            result = marker_exists_for_today(logs_dir)

            self.assertTrue(result)

    def test_create_marker_file(self):
        """Test creating marker file."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / 'logs'

            create_marker_file(logs_dir)

            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())
            self.assertTrue(logs_dir.exists())

    def test_cleanup_old_markers(self):
        """Test cleanup of old marker files."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create markers for today, 5 days ago, and 10 days ago
            today = date.today()
            today_marker = get_marker_file_path(logs_dir, today)
            recent_marker = get_marker_file_path(logs_dir, today - timedelta(days=5))
            old_marker = get_marker_file_path(logs_dir, today - timedelta(days=10))

            today_marker.touch()
            recent_marker.touch()
            old_marker.touch()

            # Cleanup with 7-day retention
            cleanup_old_markers(logs_dir, days=7)

            # Today and recent should remain, old should be deleted
            self.assertTrue(today_marker.exists())
            self.assertTrue(recent_marker.exists())
            self.assertFalse(old_marker.exists())

    def test_cleanup_old_markers_no_logs_dir(self):
        """Test cleanup when logs directory doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / 'nonexistent'

            # Should not raise error
            cleanup_old_markers(logs_dir, days=7)

    def test_cleanup_old_markers_invalid_filename(self):
        """Test cleanup skips invalid marker filenames."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create valid and invalid marker files
            valid_marker = get_marker_file_path(logs_dir, date.today() - timedelta(days=10))
            invalid_marker = logs_dir / '.toolguard-migration-invalid'

            valid_marker.touch()
            invalid_marker.touch()

            # Cleanup should remove valid old marker but skip invalid
            cleanup_old_markers(logs_dir, days=7)

            self.assertFalse(valid_marker.exists())
            self.assertTrue(invalid_marker.exists())  # Invalid format preserved


class TestConfigSyncSettings(unittest.TestCase):
    """Test loading config_sync settings from config files."""

    def test_load_config_sync_defaults(self):
        """Test default config_sync settings when no config files present."""
        config_files = []

        result = load_config_sync_settings(config_files)

        self.assertEqual(result['auto_migrate'], False)
        self.assertEqual(result['backup_dir'], 'logs/config-backups')
        self.assertEqual(result['auto_sort_on_migrate'], True)

    def test_load_config_sync_from_toml(self):
        """Test loading config_sync from TOML file."""
        with TemporaryDirectory() as tmpdir:
            toml_file = Path(tmpdir) / 'toolguard_hook.toml'
            toml_file.write_text(
                """
[config_sync]
auto_migrate = true
backup_dir = "custom/backup"
auto_sort_on_migrate = false
"""
            )

            config_files = [(toml_file, 'toolguard_hook', 'toml')]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result['auto_migrate'], True)
            self.assertEqual(result['backup_dir'], 'custom/backup')
            self.assertEqual(result['auto_sort_on_migrate'], False)

    def test_load_config_sync_from_json(self):
        """Test loading config_sync from JSON file."""
        with TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / 'toolguard_hook.json'
            json_file.write_text(
                json.dumps(
                    {'config_sync': {'auto_migrate': True, 'backup_dir': '/tmp/backups', 'auto_sort_on_migrate': True}}
                )
            )

            config_files = [(json_file, 'toolguard_hook', 'json')]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result['auto_migrate'], True)
            self.assertEqual(result['backup_dir'], '/tmp/backups')
            self.assertEqual(result['auto_sort_on_migrate'], True)

    def test_load_config_sync_ignores_claude_files(self):
        """Test that config_sync is only loaded from toolguard_hook files."""
        with TemporaryDirectory() as tmpdir:
            claude_file = Path(tmpdir) / 'settings.local.json'
            claude_file.write_text(json.dumps({'config_sync': {'auto_migrate': True}}))

            config_files = [(claude_file, 'claude', 'json')]

            result = load_config_sync_settings(config_files)

            # Should return defaults (ignored claude file)
            self.assertEqual(result['auto_migrate'], False)

    def test_load_config_sync_partial_config(self):
        """Test loading config_sync with partial settings (uses defaults for missing)."""
        with TemporaryDirectory() as tmpdir:
            toml_file = Path(tmpdir) / 'toolguard_hook.toml'
            toml_file.write_text(
                """
[config_sync]
auto_migrate = true
"""
            )

            config_files = [(toml_file, 'toolguard_hook', 'toml')]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result['auto_migrate'], True)
            self.assertEqual(result['backup_dir'], 'logs/config-backups')  # default
            self.assertEqual(result['auto_sort_on_migrate'], True)  # default

    def test_load_config_sync_last_file_wins(self):
        """Test that last config file wins for conflicting settings."""
        with TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / 'hook1.toml'
            file1.write_text('[config_sync]\nauto_migrate = false\n')

            file2 = Path(tmpdir) / 'hook2.toml'
            file2.write_text('[config_sync]\nauto_migrate = true\n')

            config_files = [(file1, 'toolguard_hook', 'toml'), (file2, 'toolguard_hook', 'toml')]

            result = load_config_sync_settings(config_files)

            # Last file (file2) should win
            self.assertEqual(result['auto_migrate'], True)

    def test_load_config_sync_invalid_file(self):
        """Test loading config_sync handles invalid files gracefully."""
        with TemporaryDirectory() as tmpdir:
            invalid_toml = Path(tmpdir) / 'invalid.toml'
            invalid_toml.write_text('invalid toml content [[[')

            valid_toml = Path(tmpdir) / 'valid.toml'
            valid_toml.write_text('[config_sync]\nauto_migrate = true\n')

            config_files = [
                (invalid_toml, 'toolguard_hook', 'toml'),
                (valid_toml, 'toolguard_hook', 'toml'),
            ]

            result = load_config_sync_settings(config_files)

            # Should load from valid file despite invalid file present
            self.assertEqual(result['auto_migrate'], True)


class TestShouldRunMigration(unittest.TestCase):
    """Test should_run_migration logic."""

    def test_should_run_migration_no_marker(self):
        """Test should_run_migration returns True when no marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            result = should_run_migration(logs_dir)

            self.assertTrue(result)

    def test_should_run_migration_marker_exists(self):
        """Test should_run_migration returns False when marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            create_marker_file(logs_dir)

            result = should_run_migration(logs_dir)

            self.assertFalse(result)


class TestRunAutoMigration(unittest.TestCase):
    """Test run_auto_migration function."""

    def test_run_auto_migration_already_ran_today(self):
        """Test auto-migration skips when already ran today."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            # Create marker file for today
            create_marker_file(logs_dir)

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {'enabled': False}

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            self.assertFalse(result)

    def test_run_auto_migration_no_settings_file(self):
        """Test auto-migration when settings.local.json doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {'enabled': False}

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            self.assertFalse(result)

    @patch('toolguard.config_divergence.get_native_permissions')
    @patch('toolguard.config_divergence.get_toolguard_permissions')
    @patch('toolguard.config_divergence.find_divergent_patterns')
    @patch('toolguard.config.discover_config_files')
    def test_run_auto_migration_no_divergence(
        self, mock_discover, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """Test auto-migration when no divergent patterns found."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({'permissions': {}}))

            mock_get_native.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_get_toolguard.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_find_divergent.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_discover.return_value = []

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {'enabled': False, 'ignored_allow_patterns': [], 'additional_ignored_patterns': []}

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            self.assertFalse(result)

    @patch('toolguard.config_divergence.get_native_permissions')
    @patch('toolguard.config_divergence.get_toolguard_permissions')
    @patch('toolguard.config_divergence.find_divergent_patterns')
    @patch('toolguard.config.discover_config_files')
    def test_run_auto_migration_takeover_mode_ignored_patterns(
        self, mock_discover, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """Test auto-migration respects takeover mode ignored patterns."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({'permissions': {'allow': ['Bash(*)']}}))

            mock_get_native.return_value = {'allow': ['Bash(*)'], 'deny': [], 'ask': []}
            mock_get_toolguard.return_value = {'allow': [], 'deny': [], 'ask': []}
            # find_divergent_patterns should filter out ignored patterns
            mock_find_divergent.return_value = {'allow': [], 'deny': [], 'ask': []}  # Bash(*) was ignored
            mock_discover.return_value = []

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {
                'enabled': True,
                'ignored_allow_patterns': ['Bash(*)'],
                'additional_ignored_patterns': [],
            }

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            # No divergence after filtering, so no migration
            self.assertFalse(result)

    @patch('toolguard.config_divergence.get_native_permissions')
    @patch('toolguard.config_divergence.get_toolguard_permissions')
    @patch('toolguard.config_divergence.find_divergent_patterns')
    @patch('toolguard.scripts.migrate_permissions.migrate')
    @patch('toolguard.config.discover_config_files')
    def test_run_auto_migration_success(
        self, mock_discover, mock_migrate, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """Test successful auto-migration."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            # Setup mocks
            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({'permissions': {'allow': ['Bash(git status)']}}))

            mock_get_native.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_get_toolguard.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_find_divergent.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_migrate.return_value = 0  # Success
            mock_discover.return_value = []

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {'enabled': False, 'ignored_allow_patterns': [], 'additional_ignored_patterns': []}

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            self.assertTrue(result)
            self.assertTrue(marker_exists_for_today(logs_dir))
            mock_migrate.assert_called_once()

    @patch('toolguard.config_divergence.get_native_permissions')
    @patch('toolguard.config_divergence.get_toolguard_permissions')
    @patch('toolguard.config_divergence.find_divergent_patterns')
    @patch('toolguard.scripts.migrate_permissions.migrate')
    @patch('toolguard.config.discover_config_files')
    def test_run_auto_migration_custom_backup_dir(
        self, mock_discover, mock_migrate, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """Test auto-migration uses custom backup directory."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({'permissions': {'allow': ['Bash(git status)']}}))

            mock_get_native.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_get_toolguard.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_find_divergent.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_migrate.return_value = 0
            mock_discover.return_value = []

            custom_backup = '/custom/backup/path'
            config_sync = {'auto_migrate': True, 'backup_dir': custom_backup, 'auto_sort_on_migrate': False}
            takeover_config = {'enabled': False, 'ignored_allow_patterns': [], 'additional_ignored_patterns': []}

            run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            # Verify migrate was called with custom backup dir and no sorting
            mock_migrate.assert_called_once_with(
                project_root=project_root, dry_run=False, auto_sort=False, backup_dir=Path(custom_backup)
            )

    @patch('toolguard.config_divergence.get_native_permissions')
    @patch('toolguard.config_divergence.get_toolguard_permissions')
    @patch('toolguard.config_divergence.find_divergent_patterns')
    @patch('toolguard.scripts.migrate_permissions.migrate')
    @patch('toolguard.config.discover_config_files')
    def test_run_auto_migration_migrate_failure(
        self, mock_discover, mock_migrate, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """Test auto-migration handles migration failure gracefully."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'
            logs_dir.mkdir()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({'permissions': {'allow': ['Bash(git status)']}}))

            mock_get_native.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_get_toolguard.return_value = {'allow': [], 'deny': [], 'ask': []}
            mock_find_divergent.return_value = {'allow': ['Bash(git status)'], 'deny': [], 'ask': []}
            mock_migrate.return_value = 1  # Failure exit code
            mock_discover.return_value = []

            config_sync = {'auto_migrate': True, 'backup_dir': 'logs/backups', 'auto_sort_on_migrate': True}
            takeover_config = {'enabled': False, 'ignored_allow_patterns': [], 'additional_ignored_patterns': []}

            result = run_auto_migration(project_root, logs_dir, config_sync, takeover_config)

            self.assertFalse(result)
            # Marker should NOT be created on failure
            self.assertFalse(marker_exists_for_today(logs_dir))


if __name__ == '__main__':
    unittest.main()
