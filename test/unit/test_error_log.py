"""
Unit tests for toolguard.error_log.

Mostly log_crash, which unlike its siblings needs no resolved project log_dir:
it writes full exception detail to the fixed ~/.toolguard/errors/ location, so
it still works when the exception happened before config resolution. That fixed
location is also what every test here has to redirect and then prove it
redirected -- an unconsulted patch writes crash reports into the developer's
own ~/.toolguard/errors/.

Stream separation and the '## <timestamp> - <LEVEL>' heading contract belong to
test_logging_streams.py; what is here of _log_entry is only its degradation
when the write fails.
"""

import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import error_log
from toolguard.error_log import log_crash, log_warning


class _HomelessPath:
    """Stands in for error_log's Path; home() raises as pathlib does with no resolvable home."""

    def __new__(cls, *args, **kwargs):
        return Path(*args, **kwargs)

    @staticmethod
    def home():
        raise RuntimeError("Could not determine home directory")


def _raise_from_a_named_frame():
    """Raise from a frame whose name reaches the report only via the traceback body."""
    raise ValueError("boom: something broke")


class TestLogCrash(unittest.TestCase):
    """log_crash captures full exception detail to ~/.toolguard/errors/."""

    def test_log_crash_writes_file_with_full_detail(self):
        """
        Given an exception raised and caught, a caught_as label that is
        deliberately not the exception's own type name, and a context dict
        describing the in-flight hook call
        When log_crash is called with Path.home() redirected to a temp directory
        Then a markdown file is written under <home>/.toolguard/errors/ carrying
        the exception type, its message, the caught_as label as passed, the
        traceback's own frames, and the context keys and values
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with patch("pathlib.Path.home", return_value=home):
                try:
                    _raise_from_a_named_frame()
                except ValueError as exc:
                    result = log_crash(
                        exc,
                        {
                            "tool_name": "Bash",
                            "tool_input": {"command": "git status"},
                        },
                        caught_as="unexpected Exception",
                    )

            errors_dir = home / ".toolguard" / "errors"
            self.assertIsNotNone(result)
            self.assertEqual(result.parent, errors_dir)
            self.assertTrue(result.exists())

            content = result.read_text()
            self.assertIn("ValueError", content)
            self.assertIn("boom: something broke", content)
            # The label as passed, which a report echoing type(exc).__name__ instead
            # would not carry, and the traceback body rather than its heading.
            self.assertIn("unexpected Exception", content)
            self.assertIn("Traceback (most recent call last)", content)
            self.assertIn("_raise_from_a_named_frame", content)
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

    def test_log_crash_echoes_the_written_report_path_to_stderr(self):
        """
        Given a crash report that is written successfully
        When log_crash returns
        Then the path it wrote is echoed on stderr -- the only channel that tells
        anyone a report exists and where to read it
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            stderr = StringIO()
            with (
                patch("pathlib.Path.home", return_value=home),
                patch("sys.stderr", stderr),
            ):
                try:
                    raise ValueError("boom")
                except ValueError as exc:
                    result = log_crash(exc, {}, caught_as="ValueError")

            self.assertIsNotNone(result)
            self.assertEqual(result.parent, home / ".toolguard" / "errors")
            self.assertIn(str(result), stderr.getvalue())

    def test_log_crash_colliding_timestamp_writes_distinct_files(self):
        """
        Given two crashes are logged with datetime.now() forced to return the
        identical second-granularity timestamp both times (simulating two
        crashes landing in the same wall-clock second)
        When log_crash is called twice
        Then two distinct files are written under the redirected home, and the
        first crash report's content is left untouched by the second call
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

            errors_dir = home / ".toolguard" / "errors"
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertNotEqual(first, second)
            self.assertEqual(first.parent, errors_dir)
            self.assertEqual(second.parent, errors_dir)
            self.assertEqual(len(list(errors_dir.glob("*.md"))), 2)

            self.assertIn("first crash", first.read_text())
            self.assertIn("second crash", second.read_text())
            self.assertNotIn("second crash", first.read_text())

    def test_log_crash_write_failure_returns_none_without_raising(self):
        """
        Given the crash-report write itself fails (e.g. an OSError from the
        filesystem)
        When log_crash is called
        Then it does not raise -- it catches the failure, names the cause on
        stderr, leaves no report behind, and returns None, so a caller inside an
        already-failing except block is never made worse by log_crash itself
        blowing up
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            stderr = StringIO()
            with (
                patch("pathlib.Path.home", return_value=home),
                patch("pathlib.Path.write_text", side_effect=OSError("disk full")),
                patch("sys.stderr", stderr),
            ):
                # Without this the fixture cannot produce the negative case.
                with self.assertRaises(OSError):
                    (home / "probe.txt").write_text("x")

                try:
                    raise ValueError("boom")
                except ValueError as exc:
                    result = log_crash(exc, {}, caught_as="ValueError")

            self.assertIsNone(result)
            self.assertIn("disk full", stderr.getvalue())
            errors_dir = home / ".toolguard" / "errors"
            self.assertTrue(errors_dir.is_dir())
            self.assertEqual(list(errors_dir.glob("*.md")), [])

    def test_log_crash_returns_none_when_no_home_directory_resolves(self):
        """
        Given a machine where no home directory can be resolved, so Path.home()
        raises (a container, a missing passwd entry, a deleted home)
        When log_crash is called from inside a caller's except clause
        Then it degrades the way every other crash-report failure does: the cause
        is named on stderr and None is returned, rather than a second exception
        being raised into a caller that is already handling one

        RED at HEAD: errors_dir = Path.home() / ... is built above log_crash's own
        try, so the RuntimeError propagates. Every call site is one of
        hook.main()'s top-level except clauses, ahead of the decision it must
        still emit; proposed ticket 23 states that consequence, and this states
        the same defect as log_crash's own contract.
        """
        stderr = StringIO()
        with (
            patch("toolguard.error_log.Path", _HomelessPath),
            patch("sys.stderr", stderr),
        ):
            # Without this the fixture cannot produce the negative case.
            with self.assertRaises(RuntimeError):
                error_log.Path.home()

            try:
                raise ValueError("boom")
            except ValueError as exc:
                result = log_crash(exc, {}, caught_as="ValueError")

        self.assertIsNone(result)
        self.assertIn("Could not determine home directory", stderr.getvalue())


class TestLogEntryWriteFailure(unittest.TestCase):
    """A stream write that fails degrades to stderr rather than raising."""

    def test_a_failed_stream_write_names_the_file_on_stderr_and_does_not_raise(self):
        """
        Given a log directory that exists but cannot be written into
        When a warning is logged
        Then nothing is raised, stderr carries the warning itself and a report
        naming the file that could not be written, and no stream file is left

        That stderr report is the only trace a dropped entry leaves: _log_entry
        returns None whether it wrote or warned and dropped, so no caller can
        tell the two apart (proposed ticket 29's family; which of the two the
        caller should be told is a product decision, so it is not pinned here).
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()
            log_dir.chmod(0o500)
            try:
                # Without this the fixture cannot produce the negative case.
                with self.assertRaises(OSError):
                    (log_dir / "probe.md").open("a")

                stderr = StringIO()
                with patch("sys.stderr", stderr):
                    log_warning("careful", "fix it", log_dir)

                text = stderr.getvalue()
                self.assertIn("careful", text)
                self.assertIn(str(log_dir), text)
                self.assertEqual(list(log_dir.glob("*.md")), [])
            finally:
                log_dir.chmod(0o700)


if __name__ == "__main__":
    unittest.main()
