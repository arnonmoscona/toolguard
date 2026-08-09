"""
Unit tests for auto_migrate module.

Tests automatic permission migration functionality including config loading,
marker file management, and integration with migration script.
"""

import json
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import once_per_store
from toolguard.auto_migrate import (
    AUTO_MIGRATION,
    load_config_sync_settings,
    run_auto_migration,
)
from toolguard.once_per_store import ClaimStatus

from test.unit._once_per_isolation import IsolatedStoreMixin as _IsolatedStoreMixin


class TestConfigSyncSettings(unittest.TestCase):
    """Test loading config_sync settings from config files."""

    def test_load_config_sync_defaults(self):
        """
        Given an empty list of config files
        When load_config_sync_settings runs
        Then it returns the documented defaults (auto_migrate off, default backup_dir, auto_sort on)
        """
        config_files = []

        result = load_config_sync_settings(config_files)

        self.assertEqual(result["auto_migrate"], False)
        self.assertEqual(result["backup_dir"], "logs/config-backups")
        self.assertEqual(result["auto_sort_on_migrate"], True)

    def test_load_config_sync_from_toml(self):
        """
        Given a TOML hook file with an explicit config_sync section
        When load_config_sync_settings runs
        Then the auto_migrate, backup_dir, and auto_sort_on_migrate values are read from the file
        """
        with TemporaryDirectory() as tmpdir:
            toml_file = Path(tmpdir) / "toolguard_hook.toml"
            toml_file.write_text(
                """
[config_sync]
auto_migrate = true
backup_dir = "custom/backup"
auto_sort_on_migrate = false
"""
            )

            config_files = [(toml_file, "toolguard_hook", "toml")]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result["auto_migrate"], True)
            self.assertEqual(result["backup_dir"], "custom/backup")
            self.assertEqual(result["auto_sort_on_migrate"], False)

    def test_load_config_sync_from_json(self):
        """
        Given a JSON hook file with an explicit config_sync section
        When load_config_sync_settings runs
        Then the auto_migrate, backup_dir, and auto_sort_on_migrate values are read from the file
        """
        with TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "toolguard_hook.json"
            json_file.write_text(
                json.dumps(
                    {
                        "config_sync": {
                            "auto_migrate": True,
                            "backup_dir": "/tmp/backups",
                            "auto_sort_on_migrate": True,
                        }
                    }
                )
            )

            config_files = [(json_file, "toolguard_hook", "json")]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result["auto_migrate"], True)
            self.assertEqual(result["backup_dir"], "/tmp/backups")
            self.assertEqual(result["auto_sort_on_migrate"], True)

    def test_load_config_sync_ignores_claude_files(self):
        """
        Given a claude settings file that defines config_sync
        When load_config_sync_settings runs
        Then the claude file is ignored and defaults are returned
        """
        with TemporaryDirectory() as tmpdir:
            claude_file = Path(tmpdir) / "settings.local.json"
            claude_file.write_text(json.dumps({"config_sync": {"auto_migrate": True}}))

            config_files = [(claude_file, "claude", "json")]

            result = load_config_sync_settings(config_files)

            # Should return defaults (ignored claude file)
            self.assertEqual(result["auto_migrate"], False)

    def test_load_config_sync_partial_config(self):
        """
        Given a TOML hook file setting only auto_migrate
        When load_config_sync_settings runs
        Then auto_migrate is taken from the file and the other keys fall back to defaults
        """
        with TemporaryDirectory() as tmpdir:
            toml_file = Path(tmpdir) / "toolguard_hook.toml"
            toml_file.write_text(
                """
[config_sync]
auto_migrate = true
"""
            )

            config_files = [(toml_file, "toolguard_hook", "toml")]

            result = load_config_sync_settings(config_files)

            self.assertEqual(result["auto_migrate"], True)
            self.assertEqual(result["backup_dir"], "logs/config-backups")  # default
            self.assertEqual(result["auto_sort_on_migrate"], True)  # default

    def test_load_config_sync_last_file_wins(self):
        """
        Given two hook files setting conflicting auto_migrate values
        When load_config_sync_settings merges them
        Then the last file's value wins
        """
        with TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "hook1.toml"
            file1.write_text("[config_sync]\nauto_migrate = false\n")

            file2 = Path(tmpdir) / "hook2.toml"
            file2.write_text("[config_sync]\nauto_migrate = true\n")

            config_files = [
                (file1, "toolguard_hook", "toml"),
                (file2, "toolguard_hook", "toml"),
            ]

            result = load_config_sync_settings(config_files)

            # Last file (file2) should win
            self.assertEqual(result["auto_migrate"], True)

    def test_load_config_sync_invalid_file(self):
        """
        Given an invalid TOML file followed by a valid one
        When load_config_sync_settings runs
        Then the invalid file is skipped and settings are loaded from the valid file
        """
        with TemporaryDirectory() as tmpdir:
            invalid_toml = Path(tmpdir) / "invalid.toml"
            invalid_toml.write_text("invalid toml content [[[")

            valid_toml = Path(tmpdir) / "valid.toml"
            valid_toml.write_text("[config_sync]\nauto_migrate = true\n")

            config_files = [
                (invalid_toml, "toolguard_hook", "toml"),
                (valid_toml, "toolguard_hook", "toml"),
            ]

            result = load_config_sync_settings(config_files)

            # Should load from valid file despite invalid file present
            self.assertEqual(result["auto_migrate"], True)


class TestAutoMigrationKey(unittest.TestCase):
    """Locks in the key string other tests here claim directly against the store."""

    def test_key_matches_the_literal_used_by_other_tests(self):
        """
        Given the module-level AUTO_MIGRATION throttled-thing
        When its private key is compared to the literal string other tests
            in this file claim against directly
        Then they match -- if this ever drifts, those tests would silently
             stop exercising the real gate
        """
        self.assertEqual(AUTO_MIGRATION._key, "auto_migration")


class TestRunAutoMigration(_IsolatedStoreMixin, unittest.TestCase):
    """Test run_auto_migration function."""

    def test_run_auto_migration_already_claimed_today(self):
        """
        Given today's slot is already claimed for this module's key
            (as if a prior call, in this process or another, already attempted
            migration today), and a genuinely divergent settings.local.json
        When run_auto_migration is invoked
        Then it skips (never calling migrate) and returns False -- proving the
             gate is the claim itself, not merely "no settings file"
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            once_per_store.claim(
                project_root,
                "auto_migration",
                once_per_store.day_scope(),
                timedelta(days=7),
            )

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {"enabled": False}

            with patch("toolguard.auto_migrate.migrate") as mock_migrate:
                result = run_auto_migration(project_root, config_sync, takeover_config)

            self.assertFalse(result)
            mock_migrate.assert_not_called()

    def test_run_auto_migration_no_settings_file(self):
        """
        Given no settings.local.json exists in the project
        When run_auto_migration is invoked
        Then it returns False because there is nothing to migrate
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {"enabled": False}

            result = run_auto_migration(project_root, config_sync, takeover_config)

            self.assertFalse(result)

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.config.discover_config_files")
    def test_run_auto_migration_no_divergence(
        self, mock_discover, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """
        Given a settings file exists but native and toolguard permissions show no divergence
        When run_auto_migration is invoked
        Then it returns False, and releases today's claim so a later call
             the same day (e.g. after new divergence appears) can retry
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(json.dumps({"permissions": {}}))

            mock_get_native.return_value = {"allow": [], "deny": [], "ask": []}
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            mock_find_divergent.return_value = {"allow": [], "deny": [], "ask": []}
            mock_discover.return_value = []

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {
                "enabled": False,
                "ignored_allow_patterns": [],
                "additional_ignored_patterns": [],
            }

            result = run_auto_migration(project_root, config_sync, takeover_config)

            self.assertFalse(result)
            self.assertEqual(
                once_per_store.claim(
                    project_root,
                    "auto_migration",
                    once_per_store.day_scope(),
                    timedelta(days=7),
                ).status,
                ClaimStatus.CLAIMED,
            )

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.config.discover_config_files")
    def test_run_auto_migration_takeover_mode_ignored_patterns(
        self, mock_discover, mock_find_divergent, mock_get_toolguard, mock_get_native
    ):
        """
        Given takeover mode ignores Bash(*) and divergence detection filters it out
        When run_auto_migration is invoked
        Then no divergence remains and it returns False
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(*)"]}})
            )

            mock_get_native.return_value = {"allow": ["Bash(*)"], "deny": [], "ask": []}
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            # find_divergent_patterns should filter out ignored patterns
            mock_find_divergent.return_value = {
                "allow": [],
                "deny": [],
                "ask": [],
            }  # Bash(*) was ignored
            mock_discover.return_value = []

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {
                "enabled": True,
                "ignored_allow_patterns": ["Bash(*)"],
                "additional_ignored_patterns": [],
            }

            result = run_auto_migration(project_root, config_sync, takeover_config)

            # No divergence after filtering, so no migration
            self.assertFalse(result)

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.auto_migrate.migrate")
    @patch("toolguard.config.discover_config_files")
    def test_run_auto_migration_success(
        self,
        mock_discover,
        mock_migrate,
        mock_find_divergent,
        mock_get_toolguard,
        mock_get_native,
    ):
        """
        Given a divergent native pattern and a migrate call that succeeds
        When run_auto_migration is invoked
        Then it returns True, claims today's slot, and calls migrate once
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Setup mocks
            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            mock_get_native.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            mock_find_divergent.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_migrate.return_value = 0  # Success
            mock_discover.return_value = []

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {
                "enabled": False,
                "ignored_allow_patterns": [],
                "additional_ignored_patterns": [],
            }

            result = run_auto_migration(project_root, config_sync, takeover_config)

            self.assertTrue(result)
            still_claimed = (
                once_per_store.claim(
                    project_root,
                    "auto_migration",
                    once_per_store.day_scope(),
                    timedelta(days=7),
                ).status
                == ClaimStatus.HELD_BY_SOMEONE_ELSE
            )
            self.assertTrue(still_claimed)
            mock_migrate.assert_called_once()

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.auto_migrate.migrate")
    @patch("toolguard.config.discover_config_files")
    def test_run_auto_migration_custom_backup_dir(
        self,
        mock_discover,
        mock_migrate,
        mock_find_divergent,
        mock_get_toolguard,
        mock_get_native,
    ):
        """
        Given config_sync specifies a custom backup_dir and auto_sort disabled
        When run_auto_migration triggers a migration
        Then migrate is called once with that backup directory and auto_sort=False
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            mock_get_native.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            mock_find_divergent.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_migrate.return_value = 0
            mock_discover.return_value = []

            custom_backup = "/custom/backup/path"
            config_sync = {
                "auto_migrate": True,
                "backup_dir": custom_backup,
                "auto_sort_on_migrate": False,
            }
            takeover_config = {
                "enabled": False,
                "ignored_allow_patterns": [],
                "additional_ignored_patterns": [],
            }

            run_auto_migration(project_root, config_sync, takeover_config)

            # Verify migrate was called with custom backup dir and no sorting
            mock_migrate.assert_called_once_with(
                project_root=project_root,
                dry_run=False,
                auto_sort=False,
                backup_dir=Path(custom_backup),
            )

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.auto_migrate.migrate")
    @patch("toolguard.config.discover_config_files")
    def test_run_auto_migration_migrate_failure(
        self,
        mock_discover,
        mock_migrate,
        mock_find_divergent,
        mock_get_toolguard,
        mock_get_native,
    ):
        """
        Given a divergent pattern but migrate returns a non-zero failure code
        When run_auto_migration is invoked
        Then it returns False and the day's claim stays held -- the only
             production caller only ever reaches this function once a day
             (gated by check_and_warn_divergence's own daily claim), so
             there is no same-day retry to release for (TOO-45 D4)
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            mock_get_native.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            mock_find_divergent.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_migrate.return_value = 1  # Failure exit code
            mock_discover.return_value = []

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {
                "enabled": False,
                "ignored_allow_patterns": [],
                "additional_ignored_patterns": [],
            }

            result = run_auto_migration(project_root, config_sync, takeover_config)

            self.assertFalse(result)
            # Claim was NOT released on failure -- a fresh claim attempt reports HELD.
            self.assertEqual(
                once_per_store.claim(
                    project_root,
                    "auto_migration",
                    once_per_store.day_scope(),
                    timedelta(days=7),
                ).status,
                ClaimStatus.HELD_BY_SOMEONE_ELSE,
            )

    @patch("toolguard.config_divergence.get_native_permissions")
    @patch("toolguard.config_divergence.get_toolguard_permissions")
    @patch("toolguard.config_divergence.find_divergent_patterns")
    @patch("toolguard.auto_migrate.migrate")
    @patch("toolguard.config.discover_config_files")
    def test_skips_migration_when_sqlite_unavailable(
        self,
        mock_discover,
        mock_migrate,
        mock_find_divergent,
        mock_get_toolguard,
        mock_get_native,
    ):
        """
        Given a divergent pattern and sqlite3 unavailable
        When run_auto_migration is invoked
        Then migrate() is NOT called and the function returns False -- unlike
             a warning, migrate() writes permission config, so concurrent,
             uncoordinated processes could otherwise both run it at once with
             no mutual exclusion and last-writer-wins could silently discard
             one process's changes (TOO-45 punch-list #15: once-per-day
             throttling being unavailable now fails CLOSED for this action,
             not open)
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            mock_get_native.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_get_toolguard.return_value = {"allow": [], "deny": [], "ask": []}
            mock_find_divergent.return_value = {
                "allow": ["Bash(git status)"],
                "deny": [],
                "ask": [],
            }
            mock_migrate.return_value = 0
            mock_discover.return_value = []

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {
                "enabled": False,
                "ignored_allow_patterns": [],
                "additional_ignored_patterns": [],
            }

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    result = run_auto_migration(
                        project_root, config_sync, takeover_config
                    )

            self.assertFalse(result)
            mock_migrate.assert_not_called()
            printed = " ".join(
                str(c.args[0]) for c in mock_print.call_args_list if c.args
            )
            self.assertIn("sqlite3 is unavailable", printed)
            self.assertIn("skipped", printed)


class TestRunAutoMigrationExceptionSafety(_IsolatedStoreMixin, unittest.TestCase):
    """TOO-45 follow-up defect 1 regression: a crash must not leak the claim."""

    def test_exception_during_analysis_leaves_period_unclaimed(self):
        """
        Given load_configuration raises during the analysis phase (e.g. a
            malformed config file), before migrate() is ever reached
        When run_auto_migration is called
        Then the exception propagates AND a subsequent call the same day
             can still take the claim -- the crash must not have consumed
             the day's slot
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status)"]}})
            )

            config_sync = {
                "auto_migrate": True,
                "backup_dir": "logs/backups",
                "auto_sort_on_migrate": True,
            }
            takeover_config = {"enabled": False}
            boom = RuntimeError("malformed config file")

            with patch("toolguard.auto_migrate.load_configuration", side_effect=boom):
                with self.assertRaises(RuntimeError):
                    run_auto_migration(project_root, config_sync, takeover_config)

            # A subsequent claim attempt the same day still succeeds -- the
            # crash left nothing claimed.
            self.assertEqual(
                once_per_store.claim(
                    project_root,
                    "auto_migration",
                    once_per_store.day_scope(),
                    timedelta(days=7),
                ).status,
                ClaimStatus.CLAIMED,
            )


if __name__ == "__main__":
    unittest.main()
