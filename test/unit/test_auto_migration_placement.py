"""
Where automatic config migration may run: session start, never the hook.

The hook writes its JSON decision to stdout, and the migration workflow writes a
human report to stdout too. When both fire in one invocation Claude Code receives
prose followed by JSON, cannot parse it, and reads an exit-0 hook as "no opinion"
-- falling through to native permission handling with nothing warning. Migration
also does a backup-and-rewrite of config files inside a synchronous PreToolUse
call, and fires on a once-a-day throttle rather than in response to the tool call.

These run the real entry points as subprocesses against an isolated HOME and a
throwaway project, because the defect is in what reaches a real stdout.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Native patterns absent from the project's toolguard config, so divergence
#: exists and there is something for a migration to move.
SETTINGS_LOCAL = {
    "permissions": {
        "allow": ["Bash(git status:*)", "Bash(ls:*)", "Bash(echo:*)"],
        "deny": [],
        "ask": [],
    }
}

MIGRATABLE_PATTERN = "Bash(git status:*)"


class AutoMigrationPlacementCase(unittest.TestCase):
    """Fixture: an isolated home plus a project whose config diverges."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.home = base / "home"
        (self.home / ".config").mkdir(parents=True)
        self.project = base / "project"

    def build_project(self, auto_migrate: bool) -> Path:
        """Create the project tree, with automatic migration on or off."""
        (self.project / ".claude").mkdir(parents=True, exist_ok=True)
        (self.project / "logs").mkdir(exist_ok=True)
        (self.project / ".claude" / "settings.local.json").write_text(
            json.dumps(SETTINGS_LOCAL)
        )
        self.toolguard_config = self.project / ".claude" / "toolguard_hook.toml"
        self.toolguard_config.write_text(
            "[config_sync]\n"
            f"auto_migrate = {str(auto_migrate).lower()}\n"
            'backup_dir = "logs/config-backups"\n'
            "\n"
            "[permissions]\n"
            'allow = ["Bash(true:*)"]\n'
        )
        return self.project

    def _env(self) -> dict:
        """Environment pinning every anchor away from the real machine."""
        env = dict(os.environ)
        env.update(
            {
                "HOME": str(self.home),
                "XDG_CONFIG_HOME": str(self.home / ".config"),
                "TOOLGUARD_LOG_DIR": str(self.project / "logs"),
                "TOOLGUARD_PROJECT_ROOT": str(self.project),
                "PYTHONPATH": str(REPO_ROOT),
            }
        )
        return env

    def run_entry_point(self, module: str, event: dict) -> subprocess.CompletedProcess:
        """Run ``python -m <module>`` against the fixture project."""
        return subprocess.run(
            [sys.executable, "-m", module],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            cwd=str(self.project),
            env=self._env(),
            timeout=60,
        )

    def run_hook(self) -> subprocess.CompletedProcess:
        """One PreToolUse invocation."""
        return self.run_entry_point(
            "toolguard.hook",
            {
                "session_id": "auto-migration-placement",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "cwd": str(self.project),
            },
        )

    def run_session_start(self) -> subprocess.CompletedProcess:
        """One SessionStart invocation."""
        return self.run_entry_point(
            "toolguard.session_start",
            {
                "session_id": "auto-migration-placement",
                "hook_event_name": "SessionStart",
                "cwd": str(self.project),
            },
        )

    def assertMigrated(self, migrated: bool):
        """Assert whether the divergent pattern reached the toolguard config."""
        text = self.toolguard_config.read_text()
        if migrated:
            self.assertIn(MIGRATABLE_PATTERN, text)
        else:
            self.assertNotIn(MIGRATABLE_PATTERN, text)


class TestTheHookNeverMigrates(AutoMigrationPlacementCase):
    """The PreToolUse path must not run migration, whatever the config says."""

    def test_the_hook_emits_exactly_one_json_document_when_auto_migrate_is_on(self):
        """
        Given a project with auto_migrate enabled and patterns to migrate
        When the PreToolUse hook runs
        Then its stdout parses as a single JSON decision

        Anything else is read by Claude Code as "no opinion", and an exit-0 hook
        that says nothing falls through to native permission handling silently --
        so a deny can stop being enforced with no error anywhere.
        """
        self.build_project(auto_migrate=True)
        result = self.run_hook()
        try:
            json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            self.fail(
                f"hook stdout is not valid JSON ({exc}); "
                f"first 200 chars: {result.stdout[:200]!r}"
            )

    def test_the_hook_does_not_rewrite_the_toolguard_config(self):
        """
        Given a project with auto_migrate enabled and patterns to migrate
        When the PreToolUse hook runs
        Then the toolguard config is left alone -- migration is a backup-and-
            rewrite of config files, which does not belong inside a synchronous
            per-tool-call hook on a ~60ms budget
        """
        self.build_project(auto_migrate=True)
        self.run_hook()
        self.assertMigrated(False)

    def test_the_hook_still_emits_valid_json_with_auto_migrate_off(self):
        """
        Given the same project with auto_migrate disabled
        When the PreToolUse hook runs
        Then its stdout parses as JSON

        The control: without it, a passing result above cannot distinguish a
        fixed hook from a fixture that never triggered migration at all.
        """
        self.build_project(auto_migrate=False)
        result = self.run_hook()
        json.loads(result.stdout)


class TestSessionStartMigrates(AutoMigrationPlacementCase):
    """Session start is where automatic migration belongs."""

    def test_session_start_migrates_when_auto_migrate_is_on(self):
        """
        Given a project with auto_migrate enabled and patterns to migrate
        When the SessionStart hook runs
        Then the divergent pattern reaches the toolguard config
        """
        self.build_project(auto_migrate=True)
        self.run_session_start()
        self.assertMigrated(True)

    def test_session_start_does_not_migrate_when_auto_migrate_is_off(self):
        """
        Given a project with auto_migrate disabled
        When the SessionStart hook runs
        Then nothing is migrated -- the setting still governs
        """
        self.build_project(auto_migrate=False)
        self.run_session_start()
        self.assertMigrated(False)

    def test_a_second_session_start_the_same_day_does_not_migrate_again(self):
        """
        Given a session start that has already migrated today
        When a second SessionStart runs against the same home
        Then no second migration is attempted -- the once-a-day throttle still
            governs, so opening several sessions does not rewrite config
            repeatedly
        """
        self.build_project(auto_migrate=True)
        self.run_session_start()
        self.assertMigrated(True)

        backups = self.project / "logs" / "config-backups"
        after_first = (
            sorted(p.name for p in backups.glob("*")) if backups.is_dir() else []
        )

        # Re-diverge, so a second migration would leave a visible trace.
        (self.project / ".claude" / "settings.local.json").write_text(
            json.dumps(SETTINGS_LOCAL)
        )
        self.run_session_start()

        after_second = (
            sorted(p.name for p in backups.glob("*")) if backups.is_dir() else []
        )
        self.assertEqual(
            after_first,
            after_second,
            "a second session start the same day made another backup, so the "
            "once-a-day throttle is not governing",
        )


if __name__ == "__main__":
    unittest.main()
