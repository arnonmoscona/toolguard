"""Unit tests for auto_migrate."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from toolguard import auto_migrate, error_reporter, once_per_store
from toolguard.auto_migrate import (
    AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS,
    AUTO_MIGRATION,
    load_config_sync_settings,
    run_auto_migration,
)
from toolguard.once_per_store import ClaimStatus
from toolguard.permission_migration import MigrationOutcome

from test.unit._config_isolation import ConfigIsolationMixin
from test.unit._once_per_isolation import IsolatedStoreMixin as _IsolatedStoreMixin

#: Takeover mode off, with both ignore lists empty -- the default shape.
_TAKEOVER_OFF = {
    "enabled": False,
    "ignored_allow_patterns": [],
    "additional_ignored_patterns": [],
}


class TestConfigSyncSettings(unittest.TestCase):
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
            self.assertEqual(result["backup_dir"], "logs/config-backups")
            self.assertEqual(result["auto_sort_on_migrate"], True)

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

            self.assertEqual(result["auto_migrate"], True)


class TestAutoMigrationKey(unittest.TestCase):
    def test_key_matches_the_literal_used_by_other_tests(self):
        """
        Given the module-level AUTO_MIGRATION throttled-thing
        When its private key is compared to the literal string other tests
            in this file claim against directly
        Then they match -- if this ever drifts, those tests would silently
             stop exercising the real gate
        """
        self.assertEqual(AUTO_MIGRATION._key, "auto_migration")


class _AutoMigrationFixture(_IsolatedStoreMixin, ConfigIsolationMixin):
    """
    Isolated project + home + claim store for driving run_auto_migration.

    `run_auto_migration` calls the real `load_configuration`, so `Path.home()`
    and the project root must both be redirected or the test reads whatever
    toolguard config the developer's machine happens to carry.
    """

    def setUp(self):
        """Build an empty isolated project with a .claude directory."""
        super().setUp()
        _home, self.project = self.isolate_config_environment()
        self.claude_dir = self.project / ".claude"
        self.claude_dir.mkdir()
        self.config_sync = {
            "auto_migrate": True,
            "backup_dir": "logs/backups",
            "auto_sort_on_migrate": True,
        }

    def write_settings(self, allow=(), deny=(), ask=()):
        """Write the project's settings.local.json with the given native patterns."""
        path = self.claude_dir / "settings.local.json"
        path.write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": list(allow),
                        "deny": list(deny),
                        "ask": list(ask),
                    }
                }
            )
        )
        return path

    def spy(self, name):
        """
        Replace `auto_migrate.<name>` with a Mock delegating to the real
        function, so call arguments are observable without stubbing behaviour.

        Patches the binding `auto_migrate` itself holds: it imports these
        names by value, so patching their defining module has no effect on
        this call path.
        """
        real = getattr(auto_migrate, name)
        spy = MagicMock(side_effect=real)
        self.enterContext(patch.object(auto_migrate, name, spy))
        return spy

    def silence_stderr(self):
        """Swallow this test's progress reports; it asserts on files or calls, not on stderr."""
        self.enterContext(redirect_stderr(io.StringIO()))

    def claim_status_now(self):
        """The status a fresh claim attempt for today's auto-migration slot reports."""
        return once_per_store.claim(
            self.project,
            "auto_migration",
            once_per_store.day_scope(),
            timedelta(days=7),
        ).status


class TestRunAutoMigration(_AutoMigrationFixture, unittest.TestCase):
    def test_run_auto_migration_already_claimed_today(self):
        """
        Given today's slot is already claimed for this module's key
            (as if a prior call, in this process or another, already attempted
            migration today), and a genuinely divergent settings.local.json
        When run_auto_migration is invoked
        Then it skips before doing any analysis -- neither load_configuration
             nor migrate runs -- and returns False, proving the up-front
             `done()` check is what stopped it, not the claim `run()` would
             have failed to take a moment later
        """
        self.write_settings(allow=["Bash(git status)"])
        once_per_store.claim(
            self.project,
            "auto_migration",
            once_per_store.day_scope(),
            timedelta(days=7),
        )
        load_config = self.spy("load_configuration")

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertFalse(result)
        load_config.assert_not_called()
        mock_migrate.assert_not_called()

    def test_run_auto_migration_no_settings_file(self):
        """
        Given no settings.local.json exists in the project
        When run_auto_migration is invoked
        Then it returns False without reading any native permissions -- the
             existence check short-circuits the analysis rather than letting
             it run over an empty permission set and reach the same answer
        """
        native = self.spy("get_native_permissions")

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertFalse(result)
        native.assert_not_called()
        mock_migrate.assert_not_called()

    def test_run_auto_migration_no_divergence(self):
        """
        Given a settings file whose only pattern is already in the project's
            toolguard config, so the real divergence analysis finds nothing
        When run_auto_migration is invoked
        Then it returns False without calling migrate, and today's slot is
             still free -- it returns before AUTO_MIGRATION.run(), the only
             place in this function that claims anything, so the day is never
             spent on a project with nothing to migrate
        """
        self.write_settings(allow=["Bash(git status)"])
        (self.claude_dir / "toolguard_hook.toml").write_text(
            '[permissions]\nallow = ["Bash(git status)"]\n'
        )

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertFalse(result)
        mock_migrate.assert_not_called()
        self.assertEqual(self.claim_status_now(), ClaimStatus.CLAIMED)

    def test_takeover_ignored_patterns_are_passed_to_the_divergence_analysis(self):
        """
        Given takeover mode is enabled and lists Bash(*) as ignored plus
            Bash(rm *) as an additional ignored pattern, and settings.local.json
            declares exactly those two
        When run_auto_migration is invoked
        Then both lists are folded together and handed to the divergence
             analysis -- asserted on the call arguments, not merely on the
             empty outcome, which an analysis ignoring the argument entirely
             would also produce -- so nothing is left to migrate
        """
        self.write_settings(allow=["Bash(*)", "Bash(rm *)"])
        divergence = self.spy("find_divergent_patterns")
        takeover = {
            "enabled": True,
            "ignored_allow_patterns": ["Bash(*)"],
            "additional_ignored_patterns": ["Bash(rm *)"],
        }

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            result = run_auto_migration(self.project, self.config_sync, takeover)

        self.assertTrue(divergence.called, "the spy never ran; wrong patch target")
        self.assertEqual(divergence.call_args.args[2], ["Bash(*)", "Bash(rm *)"])
        self.assertFalse(result)
        mock_migrate.assert_not_called()

    def test_ignored_patterns_are_dropped_when_takeover_is_disabled(self):
        """
        Given takeover mode is DISABLED but still lists Bash(*) as ignored,
            and settings.local.json declares Bash(*)
        When run_auto_migration is invoked
        Then the ignore list is discarded (an empty list reaches the analysis)
             and Bash(*) is migrated anyway.

        PINS CURRENT BEHAVIOUR, WHICH IS KNOWN TO DISAGREE WITH ITS SIBLING:
        config_divergence.check_and_warn_divergence applies
        ignored_allow_patterns unconditionally, so with takeover off a pattern
        can be excluded from the divergence WARNING and still be migrated by
        the migration that warning gates. Which of the two is correct is a
        product decision; this test exists so the drift cannot be changed
        silently on this side.
        """
        self.silence_stderr()
        self.write_settings(allow=["Bash(*)"])
        divergence = self.spy("find_divergent_patterns")
        takeover = {
            "enabled": False,
            "ignored_allow_patterns": ["Bash(*)"],
            "additional_ignored_patterns": [],
        }

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.SUCCEEDED
            result = run_auto_migration(self.project, self.config_sync, takeover)

        self.assertTrue(divergence.called, "the spy never ran; wrong patch target")
        self.assertEqual(divergence.call_args.args[2], [])
        self.assertTrue(result)
        mock_migrate.assert_called_once()

    def test_run_auto_migration_success(self):
        """
        Given a settings file carrying one pattern the toolguard config does
            not have, and a migrate call that succeeds
        When run_auto_migration is invoked
        Then it returns True, spends today's slot, and calls migrate exactly
             once with the relative backup_dir resolved against the project root
        """
        self.silence_stderr()
        self.write_settings(allow=["Bash(git status)"])

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.SUCCEEDED
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertTrue(result)
        self.assertEqual(self.claim_status_now(), ClaimStatus.HELD_BY_SOMEONE_ELSE)
        mock_migrate.assert_called_once_with(
            project_root=self.project,
            dry_run=False,
            auto_sort=True,
            backup_dir=self.project / "logs" / "backups",
            lock_timeout_seconds=AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS,
        )

    def test_run_auto_migration_success_reports_notices_only(self):
        """
        Given a divergent native pattern and a migrate call that succeeds
        When run_auto_migration is invoked
        Then both the "running" and "successfully migrated" progress messages
             reach stderr as NOTICES -- no [WARNING] label appears, which is
             the only thing separating the two severities on stderr, since
             error_reporter prints a warning's text there as well
        """
        self.write_settings(allow=["Bash(git status)"])

        buf = io.StringIO()
        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.SUCCEEDED
            with redirect_stderr(buf):
                run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        stderr_text = buf.getvalue()
        self.assertIn("Running automatic migration", stderr_text)
        self.assertIn("Successfully migrated 1 pattern", stderr_text)
        self.assertNotIn("[WARNING]", stderr_text)

    def test_run_auto_migration_nonzero_exit_reports_a_warning(self):
        """
        Given migrate() returns MigrationOutcome.FAILED
        When run_auto_migration is invoked
        Then "Migration failed" reaches stderr under the [WARNING] label --
             not as a bare notice line -- and False is returned
        """
        self.write_settings(allow=["Bash(git status)"])

        buf = io.StringIO()
        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.FAILED
            with redirect_stderr(buf):
                result = run_auto_migration(
                    self.project, self.config_sync, _TAKEOVER_OFF
                )

        self.assertFalse(result)
        self.assertIn(
            "[WARNING] [TOOLGUARD AUTO-MIGRATION] Migration failed", buf.getvalue()
        )

    def test_run_auto_migration_declined_locked_reports_a_notice_not_a_failure(self):
        """
        Given migrate() returns MigrationOutcome.DECLINED_LOCKED (another
            migration already holds this project's lock; nothing was
            attempted)
        When run_auto_migration is invoked
        Then a "skipping" NOTICE reaches stderr -- carrying no [WARNING]
             label and never the "Migration failed" text, since nothing
             failed -- False is returned, and the day's claim stays consumed
             (not released): the other process holding the lock is doing the
             work, so there is nothing here to retry
        """
        self.write_settings(allow=["Bash(git status)"])

        buf = io.StringIO()
        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.DECLINED_LOCKED
            with redirect_stderr(buf):
                result = run_auto_migration(
                    self.project, self.config_sync, _TAKEOVER_OFF
                )

        self.assertFalse(result)
        stderr_text = buf.getvalue()
        self.assertIn("already running for this project", stderr_text)
        self.assertNotIn("Migration failed", stderr_text)
        self.assertNotIn("[WARNING]", stderr_text)
        self.assertEqual(self.claim_status_now(), ClaimStatus.HELD_BY_SOMEONE_ELSE)

    def test_run_auto_migration_exception_reports_a_warning(self):
        """
        Given migrate() raises
        When run_auto_migration is invoked
        Then a [WARNING] naming the exception reaches stderr and False is
             returned, without the exception propagating
        """
        self.write_settings(allow=["Bash(git status)"])

        buf = io.StringIO()
        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.side_effect = RuntimeError("disk full")
            with redirect_stderr(buf):
                result = run_auto_migration(
                    self.project, self.config_sync, _TAKEOVER_OFF
                )

        self.assertFalse(result)
        self.assertIn(
            "[WARNING] [TOOLGUARD AUTO-MIGRATION] Migration error", buf.getvalue()
        )
        self.assertIn("disk full", buf.getvalue())

    def test_run_auto_migration_nonzero_exit_reaches_the_warning_log(self):
        """
        Given migrate() returns MigrationOutcome.FAILED, AND an error_reporter
            invocation with a resolvable log directory is active
        When run_auto_migration is invoked
        Then the "Migration failed" warning lands in the WARNING log file,
             not just stderr
        """
        self.silence_stderr()
        self.write_settings(allow=["Bash(git status)"])
        log_dir = self.project / "logs"
        log_dir.mkdir()

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.FAILED
            with error_reporter.active(error_reporter.Reporter(log_dir=log_dir)):
                result = run_auto_migration(
                    self.project, self.config_sync, _TAKEOVER_OFF
                )

        self.assertFalse(result)
        warning_files = list(log_dir.glob("toolguard-warning-*.md"))
        self.assertEqual(len(warning_files), 1)
        self.assertIn("Migration failed", warning_files[0].read_text())

    def test_run_auto_migration_custom_backup_dir(self):
        """
        Given config_sync specifies an absolute backup_dir and auto_sort disabled
        When run_auto_migration triggers a migration
        Then migrate is called once with that directory unchanged (an absolute
             path is never re-anchored on the project root) and auto_sort=False
        """
        self.silence_stderr()
        self.write_settings(allow=["Bash(git status)"])
        custom_backup = "/custom/backup/path"
        config_sync = {
            "auto_migrate": True,
            "backup_dir": custom_backup,
            "auto_sort_on_migrate": False,
        }

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.SUCCEEDED
            run_auto_migration(self.project, config_sync, _TAKEOVER_OFF)

        mock_migrate.assert_called_once_with(
            project_root=self.project,
            dry_run=False,
            auto_sort=False,
            backup_dir=Path(custom_backup),
            lock_timeout_seconds=AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS,
        )

    def test_run_auto_migration_migrate_failure(self):
        """
        Given a divergent pattern but migrate returns FAILED
        When run_auto_migration is invoked
        Then it returns False and today's slot stays consumed -- the claim is
             taken by AUTO_MIGRATION.run() before the action runs and nothing
             releases it on failure, so a failed migration waits for tomorrow
             rather than retrying on the next tool call
        """
        self.silence_stderr()
        self.write_settings(allow=["Bash(git status)"])

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.FAILED
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertFalse(result)
        self.assertEqual(self.claim_status_now(), ClaimStatus.HELD_BY_SOMEONE_ELSE)

    def test_skips_migration_when_sqlite_unavailable(self):
        """
        Given a divergent pattern and sqlite3 unavailable, so the once-per-day
            guarantee cannot be verified
        When run_auto_migration is invoked
        Then migrate() is NOT called and False is returned: this action is
             declared Repeat.UNSAFE, so an unverifiable throttle fails CLOSED.
             Without it every hook call on every tool use would re-run a
             migration that rewrites permission config.
        """
        self.write_settings(allow=["Bash(git status)"])
        # The "throttling unavailable" notice is sent at most once per
        # OncePer INSTANCE, and AUTO_MIGRATION is module-level state shared
        # with every other test in this process.
        AUTO_MIGRATION._degraded_notice_sent = False
        self.addCleanup(setattr, AUTO_MIGRATION, "_degraded_notice_sent", False)

        with patch.object(auto_migrate, "migrate") as mock_migrate:
            mock_migrate.return_value = MigrationOutcome.SUCCEEDED
            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    result = run_auto_migration(
                        self.project, self.config_sync, _TAKEOVER_OFF
                    )

        self.assertFalse(result)
        mock_migrate.assert_not_called()
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("sqlite3 is unavailable", printed)
        self.assertIn("skipped", printed)


class TestAutoMigrationWritesTheConfig(_AutoMigrationFixture, unittest.TestCase):
    """End-to-end: run_auto_migration driving the REAL migrate(), asserted on the files it leaves behind."""

    def test_the_migrated_pattern_moves_from_settings_into_the_toolguard_config(self):
        """
        Given a project whose settings.local.json allows Bash(git status) and
            whose toolguard_hook.toml does not
        When run_auto_migration runs with no migrate() stub at all
        Then the pattern is GONE from settings.local.json, PRESENT in
             toolguard_hook.toml, and both files were backed up first --
             every other test in this file stubs migrate() and can therefore
             only observe that success was reported, never that anything was
             written
        """
        settings_path = self.write_settings(allow=["Bash(git status)"])
        hook_path = self.claude_dir / "toolguard_hook.toml"
        hook_path.write_text("[permissions]\nallow = []\n")

        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertTrue(result)
        self.assertEqual(
            json.loads(settings_path.read_text())["permissions"]["allow"], []
        )
        self.assertIn("Bash(git status)", hook_path.read_text())
        backup_dir = self.project / "logs" / "backups"
        self.assertTrue(backup_dir.is_dir(), "no backup directory under the project")
        backups = sorted(p.name.split(".")[0] for p in backup_dir.iterdir())
        self.assertEqual(backups, ["settings", "toolguard_hook"])

    def test_success_notice_must_not_claim_a_count_migrate_never_confirmed(self):
        """
        Given a divergent pattern that migrate() itself declines to migrate
            (here: the project's takeover config ignores it, which migrate
            honours and run_auto_migration's caller-supplied takeover dict
            does not), so migrate() writes nothing and still returns SUCCEEDED
            -- its documented value for the "nothing to migrate" no-op
        When run_auto_migration is invoked
        Then the announced count must not exceed what was actually written.

        EXPECTED TO FAIL against current production. The count in the notice
        is run_auto_migration's OWN pre-analysis total; MigrationOutcome
        carries no count, so "migrated 1 pattern(s)" and "migrated nothing"
        are byte-identical on stderr and both return True. Fixing this means
        migrate() returning what it wrote, not a better assertion here.
        """
        settings_path = self.write_settings(allow=["Bash(git status)"])
        (self.claude_dir / "toolguard_hook.toml").write_text(
            "[takeover_mode]\nenabled = true\n"
            'ignored_allow_patterns = ["Bash(git status)"]\n'
        )

        buf = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(buf):
            run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertEqual(
            json.loads(settings_path.read_text())["permissions"]["allow"],
            ["Bash(git status)"],
            "fixture broken: migrate() was supposed to write nothing here",
        )
        self.assertNotIn("Successfully migrated 1 pattern", buf.getvalue())


class TestRunAutoMigrationExceptionSafety(_AutoMigrationFixture, unittest.TestCase):
    def test_exception_during_analysis_leaves_period_unclaimed(self):
        """
        Given load_configuration raises during the analysis phase (e.g. a
            malformed config file), before migrate() is ever reached
        When run_auto_migration is called
        Then the exception propagates AND a subsequent call the same day
             can still take the claim -- the crash must not have consumed
             the day's slot
        """
        self.write_settings(allow=["Bash(git status)"])
        boom = RuntimeError("malformed config file")

        with patch.object(auto_migrate, "load_configuration", side_effect=boom):
            with self.assertRaises(RuntimeError):
                run_auto_migration(self.project, self.config_sync, _TAKEOVER_OFF)

        self.assertEqual(self.claim_status_now(), ClaimStatus.CLAIMED)


if __name__ == "__main__":
    unittest.main()
