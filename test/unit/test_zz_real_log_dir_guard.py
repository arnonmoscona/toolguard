"""
Regression tests for the guards against writes to the real repo ``logs/``
directory and the real ``~/.toolguard/once_per.db``.

Named ``test_zz_...`` so it sorts last under ``unittest discover``, and so
normally runs after the tests it checks -- a convenience only; the ordering
guarantee is ``test/unit/__init__.py``'s ``atexit`` re-check.
"""

import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from test.unit import _real_log_dir_guard, _real_once_per_home_guard
from toolguard import once_per_store
from toolguard.once_per_store import ClaimStatus


class TestRealLogDirGuardHasNoRecordedLeaks(unittest.TestCase):
    """Asserts nothing in this run attempted to write to the real repo logs/ dir."""

    def test_no_real_log_dir_writes_were_attempted(self):
        """
        Given the TOO-19 real-logs-dir write guard installed for this whole run
        When every test that ran before this one is taken into account
        Then no toolguard log-writing call attempted to resolve the real
            project logs/ directory as its target
        """
        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            events,
            [],
            "One or more tests attempted to write to the real project logs "
            "directory (write suppressed by the guard, but this is a "
            "regression -- see .claude/rules/test-config-isolation.md):\n\n"
            + "\n".join(events),
        )


class TestRealSuppressionHomeGuardHasNoRecordedLeaks(unittest.TestCase):
    """Asserts nothing in this run touched the real ~/.toolguard/once_per.db."""

    def test_no_real_once_per_store_access_was_attempted(self):
        """
        Given the TOO-45 real-once-per-home guard installed for this whole run
        When every test that ran before this one is taken into account
        Then no claim-store call resolved the real ~/.toolguard/once_per.db
            as its target
        """
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            events,
            [],
            "One or more tests attempted to access the real ~/.toolguard/ "
            "claim store (access suppressed by the guard, but this is "
            "a regression -- see .claude/rules/test-config-isolation.md):\n\n"
            + "\n".join(events),
        )


class TestRealLogDirGuardActuallyFires(unittest.TestCase):
    """
    Self-verification: deliberately targets the real logs/ directory and asserts the
    guard records and suppresses the write, restoring the registry afterwards.
    """

    def setUp(self):
        """Start from a clean leak registry regardless of what ran earlier."""
        self._pre_existing = _real_log_dir_guard.get_leak_events()
        _real_log_dir_guard.clear_leak_events()

    def tearDown(self):
        """Restore whatever was already recorded before this test ran."""
        _real_log_dir_guard.replace_leak_events(self._pre_existing)

    def test_guard_records_and_suppresses_a_real_dir_write_attempt(self):
        """
        Given the guard installed and an empty leak registry
        When toolguard.log_writer.log_discovery is called with the REAL repo
            logs/ directory as log_dir (simulating the TOO-19 regression)
        Then the call is recorded as a leak event and the discovery log file
            is NOT created in the real logs/ directory
        """
        import toolguard.log_writer as log_writer

        discovery_log = (
            _real_log_dir_guard.REAL_LOGS_DIR / log_writer._DISCOVERY_LOG_FILENAME
        )
        before_exists = discovery_log.exists()
        before_mtime = discovery_log.stat().st_mtime if before_exists else None

        log_writer.log_discovery(
            ["project: /synthetic/toolguard_hook.toml"],
            _real_log_dir_guard.REAL_LOGS_DIR,
            "/synthetic",
        )

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("log_discovery", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])

        after_exists = discovery_log.exists()
        after_mtime = discovery_log.stat().st_mtime if after_exists else None
        self.assertEqual(
            before_exists,
            after_exists,
            "guard failed to suppress the real-dir write: file existence changed",
        )
        if before_exists:
            self.assertEqual(
                before_mtime,
                after_mtime,
                "guard failed to suppress the real-dir write: file mtime changed",
            )

    def test_guard_fires_for_log_command_via_config_log_dir(self):
        """
        Given the guard installed and an empty leak registry
        When toolguard.log_writer.log_command is called with a LogRecord and a
            config dict whose log_dir is the REAL repo logs/ directory -- the
            shape toolguard.hook.main() uses, which pins that the guard's
            inspect.signature-based log_dir/config extraction resolves against
            log_command's signature and not only log_discovery's
        Then the call is recorded as a leak event and no resolution log file
            is created in the real logs/ directory
        """
        import toolguard.log_writer as log_writer
        from datetime import datetime as _datetime

        resolution_log = (
            _real_log_dir_guard.REAL_LOGS_DIR
            / f"toolguard-{_datetime.now().strftime('%Y-%m-%d')}.md"
        )
        before_exists = resolution_log.exists()
        before_mtime = resolution_log.stat().st_mtime if before_exists else None

        log_writer.log_command(
            log_writer.LogRecord(command_str="ls -la", status="executed"),
            config={"log_dir": _real_log_dir_guard.REAL_LOGS_DIR},
        )

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("log_command", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])

        after_exists = resolution_log.exists()
        after_mtime = resolution_log.stat().st_mtime if after_exists else None
        self.assertEqual(
            before_exists,
            after_exists,
            "guard failed to suppress the real-dir write: file existence changed",
        )
        if before_exists:
            self.assertEqual(
                before_mtime,
                after_mtime,
                "guard failed to suppress the real-dir write: file mtime changed",
            )

    def test_guard_fires_for_claim_store_reap_via_logs_dir(self):
        """
        Given the guard installed, an empty leak registry, and
            once_per_store._STORE_PATH isolated to a tmp file (so the
            ~/.toolguard/-facing guard passes through and does not mask this one)
        When toolguard.once_per_store.reap is called with the REAL repo logs/
            directory as logs_dir -- reap is the one claim-store entry point
            that still takes a project logs_dir, so it is guarded here too
        Then the call is recorded as a leak event
        """
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(once_per_store, "_STORE_PATH", Path(tmp) / "once_per.db"):
                once_per_store.reap(_real_log_dir_guard.REAL_LOGS_DIR)

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("reap", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])


class TestRealSuppressionHomeGuardActuallyFires(unittest.TestCase):
    """
    Self-verification: deliberately points _STORE_PATH back at the real
    ~/.toolguard/once_per.db (test/unit/__init__.py otherwise redirects it to a tmp
    file) and asserts the guard intercepts the call; both are restored afterwards.
    """

    def setUp(self):
        """Start from a clean leak registry and force _STORE_PATH to the real path."""
        self._pre_existing = _real_once_per_home_guard.get_leak_events()
        _real_once_per_home_guard.clear_leak_events()
        self._store_patcher = patch.object(
            once_per_store,
            "_STORE_PATH",
            _real_once_per_home_guard.REAL_ONCE_PER_DB,
        )
        self._store_patcher.start()

    def tearDown(self):
        """Restore _STORE_PATH and whatever was already recorded before this test ran."""
        self._store_patcher.stop()
        _real_once_per_home_guard.replace_leak_events(self._pre_existing)

    def test_guard_fires_for_claim_against_the_unpatched_real_store(self):
        """
        Given the guard installed and _STORE_PATH forced to the real, unisolated path
        When toolguard.once_per_store.claim is called with a REAL (non-None) project
            -- claim(None, ...) short-circuits before touching storage, so it would
            pass even with the guard's install() deleted
        Then the call is recorded as a leak event, reports UNGUARANTEED (the
            fail-soft outcome), and the real database is NOT created
        """
        before_exists = _real_once_per_home_guard.REAL_ONCE_PER_DB.exists()

        result = once_per_store.claim(
            Path("/synthetic/project"),
            "synthetic_kind",
            "synthetic_scope",
            timedelta(days=1),
        )

        self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("claim", events[0])
        self.assertIn(str(_real_once_per_home_guard.REAL_ONCE_PER_DB), events[0])

        after_exists = _real_once_per_home_guard.REAL_ONCE_PER_DB.exists()
        self.assertEqual(
            before_exists,
            after_exists,
            "guard failed to suppress the real-store write: db existence changed",
        )

    def test_guard_fires_for_is_claimed_against_the_unpatched_real_store(self):
        """
        Given the guard installed and _STORE_PATH forced to the real, unisolated path
        When toolguard.once_per_store.is_claimed is called with a REAL (non-None)
            project -- is_claimed(None, ...) short-circuits before touching
            storage, so it would pass even with the guard's install() deleted
        Then the call is recorded as a leak event and returns False
        """
        result = once_per_store.is_claimed(
            Path("/synthetic/project"), "synthetic_kind", "synthetic_scope"
        )

        self.assertFalse(result)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("is_claimed", events[0])


if __name__ == "__main__":
    unittest.main()
