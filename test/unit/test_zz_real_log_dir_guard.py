"""
Dedicated regression test for the TOO-19 real-logs-dir write guard.

Named ``test_zz_...`` so it sorts after every other ``test_*.py`` file in
this directory under ``unittest discover``'s alphabetical ordering, which
means it normally runs after all the tests it is meant to catch regressions
in -- but that ordering is a convenience, not the guarantee. The actual
reliability guarantee comes from ``test/unit/__init__.py``'s ``atexit``
hook, which re-checks the same registry after the WHOLE process's test run
completes regardless of discovery order; see
``test/unit/_real_log_dir_guard.py``'s module docstring for the full design
rationale.
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
    Self-verification (TOO-19): proves the guard mechanism itself works,
    rather than trusting an untested detector. Calls the guarded
    ``log_writer.log_discovery`` directly with the REAL repo logs/ directory
    as its target and asserts (a) the call is recorded and (b) no file was
    actually written -- then clears the synthetic event so it cannot fail
    ``TestRealLogDirGuardHasNoRecordedLeaks`` or the atexit backstop.
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
        When toolguard.log_writer.log_command is called with a LogRecord and
            a config dict whose log_dir is the REAL repo logs/ directory --
            the exact shape toolguard.hook.main() uses on every call site
            (TOO-45 R1d changed log_command's signature from 12 loose
            parameters to one LogRecord + log_dir/config/log_format; this
            pins that _guard_log_command's inspect.signature-based
            log_dir/config extraction still resolves correctly against the
            NEW signature, since only log_discovery was exercised above)
        Then the call is recorded as a leak event and no resolution log file
            is created in the real logs/ directory
        """
        import toolguard.log_writer as log_writer
        from datetime import datetime as _datetime

        # The resolution log is date-partitioned (unlike the discovery log
        # the sibling test above uses), so build today's filename the same
        # way log_command itself does.
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
            ~/.toolguard/-facing guard from _real_once_per_home_guard.py
            passes through and does not mask this one)
        When toolguard.once_per_store.reap is called with the REAL repo logs/
            directory as logs_dir (TOO-45 R2: claim/is_claimed/release no
            longer take a logs_dir argument at all -- the store moved to
            ~/.toolguard/ -- but reap() still sweeps legacy artefacts under
            a project's logs_dir, so it remains guarded by THIS module too;
            the two guards compose, each checking an independent condition)
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
    Self-verification (TOO-45 R2): proves the ~/.toolguard/once_per.db
    guard mechanism itself works, by DELIBERATELY breaking isolation --
    setting toolguard.once_per_store._STORE_PATH back to the real developer
    path (test/unit/__init__.py otherwise redirects it to a session-wide tmp
    default for every other test, see its module docstring) -- and asserting
    the guard intercepts every call. Both the leak registry and
    _STORE_PATH are saved before and restored after each test, so this
    cannot leak into TestRealSuppressionHomeGuardHasNoRecordedLeaks, the
    atexit backstop, or any test that runs afterward.
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
        When toolguard.once_per_store.claim is called with a REAL (non-None) project --
            claim(None, ...) short-circuits before touching storage regardless of
            the guard, which would make this test pass even with install() deleted
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
            storage regardless of the guard, which would make this test pass
            even with install() deleted
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
