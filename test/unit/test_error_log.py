"""
Unit tests for toolguard.error_log.log_crash (TOO-15 crash-capture).

log_crash is the durable "black box" for unhandled exceptions in the hook's
main() entry point: unlike log_error/log_warning/log_conflict (which need a
resolved project log_dir and only take a short message), log_crash writes to
the fixed, user-level ~/.toolguard/errors/ location -- so it works even when
the exception happened before/during config resolution -- and captures the
full exception type, message, traceback, and caller-supplied context.
"""

import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.error_log import log_crash


class TestLogCrash(unittest.TestCase):
    """log_crash captures full exception detail to ~/.toolguard/errors/."""

    def test_log_crash_writes_file_with_full_detail(self):
        """
        Given an exception raised and caught, and a context dict describing the
        in-flight hook call
        When log_crash is called with Path.home() mocked to a temp directory
        Then a markdown file is written under <home>/.toolguard/errors/ containing
        the exception type, message, the caught_as label, a full traceback, and
        the context values
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with patch("pathlib.Path.home", return_value=home):
                try:
                    raise ValueError("boom: something broke")
                except ValueError as exc:
                    result = log_crash(
                        exc,
                        {
                            "tool_name": "Bash",
                            "tool_input": {"command": "git status"},
                        },
                        caught_as="ValueError",
                    )

            errors_dir = home / ".toolguard" / "errors"
            self.assertIsNotNone(result)
            self.assertEqual(result.parent, errors_dir)
            self.assertTrue(result.exists())

            content = result.read_text()
            self.assertIn("ValueError", content)
            self.assertIn("boom: something broke", content)
            self.assertIn("Traceback", content)
            self.assertIn("tool_name", content)
            self.assertIn("Bash", content)
            self.assertIn("git status", content)

    def test_log_crash_creates_errors_dir_when_toolguard_absent(self):
        """
        Given ~/.toolguard does not exist at all (no init-state has ever run, and
        the crash could even be happening during install itself)
        When log_crash is called
        Then it creates ~/.toolguard/errors/ on demand and writes the file
        successfully -- it must not depend on init-state having run first
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            self.assertFalse((home / ".toolguard").exists())

            with patch("pathlib.Path.home", return_value=home):
                try:
                    raise RuntimeError("no state dir yet")
                except RuntimeError as exc:
                    result = log_crash(exc, {}, caught_as="unexpected Exception")

            self.assertIsNotNone(result)
            self.assertTrue((home / ".toolguard" / "errors").is_dir())
            self.assertTrue(result.exists())

    def test_log_crash_colliding_timestamp_writes_distinct_files(self):
        """
        Given two crashes are logged with datetime.now() forced to return the
        identical second-granularity timestamp both times (simulating two
        crashes landing in the same wall-clock second)
        When log_crash is called twice
        Then two distinct files are written and the first crash report's
        content is left completely untouched by the second call (the same
        "prove no data loss" shape as create_backup's collision fix in
        toolguard/scripts/migrate_permissions.py)
        """
        fixed_now = datetime(2026, 7, 9, 10, 15, 0)
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with (
                patch("pathlib.Path.home", return_value=home),
                patch("toolguard.error_log.datetime") as mock_datetime,
            ):
                mock_datetime.now.return_value = fixed_now

                try:
                    raise ValueError("first crash")
                except ValueError as exc1:
                    first = log_crash(exc1, {}, caught_as="ValueError")

                try:
                    raise ValueError("second crash")
                except ValueError as exc2:
                    second = log_crash(exc2, {}, caught_as="ValueError")

            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())

            self.assertIn("first crash", first.read_text())
            self.assertIn("second crash", second.read_text())
            # No clobbering: the first file must not have been overwritten by
            # the second call's content.
            self.assertNotIn("second crash", first.read_text())

    def test_log_crash_write_failure_returns_none_without_raising(self):
        """
        Given the crash-report write itself fails (e.g. an OSError from the
        filesystem)
        When log_crash is called
        Then it does not raise -- it catches the failure, warns on stderr, and
        returns None, so a caller inside an already-failing except block is
        never made worse by log_crash itself blowing up
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with (
                patch("pathlib.Path.home", return_value=home),
                patch("pathlib.Path.write_text", side_effect=OSError("disk full")),
            ):
                try:
                    raise ValueError("boom")
                except ValueError as exc:
                    result = log_crash(exc, {}, caught_as="ValueError")

            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
