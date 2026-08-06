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

from test.unit import _real_log_dir_guard


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


if __name__ == "__main__":
    unittest.main()
