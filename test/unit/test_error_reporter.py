"""Unit tests for toolguard.error_reporter -- which destination each severity reaches."""

import io
import unittest
from contextlib import contextmanager, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import error_log, error_reporter
from toolguard.error_reporter import Reporter


@contextmanager
def _captured_stderr_reporter(log_dir):
    """Build a `Reporter(log_dir=log_dir)` with stderr redirected; yields ``(reporter, buffer)``."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        yield Reporter(log_dir=log_dir), buf


class TestDefaultReporterHasNoLogDir(unittest.TestCase):
    """A bare `Reporter()`: the safe default -- stderr only, no logs, no buffer."""

    def test_notice_prints_to_stderr_only(self):
        """
        Given a Reporter with no log_dir
        When notice() is called
        Then stderr carries exactly that message and nothing else
        """
        buf = io.StringIO()
        with redirect_stderr(buf):
            Reporter().notice("routine notice")

        self.assertEqual(buf.getvalue(), "routine notice\n")

    def test_warning_prints_the_labeled_message_with_no_log(self):
        """
        Given a Reporter with no log_dir
        When warning() is called
        Then stderr carries the labeled message and corrective-steps line --
             the SAME shape `error_log`'s own echo would have produced had a
             log write succeeded
        """
        buf = io.StringIO()
        with redirect_stderr(buf):
            Reporter().warning("something is off", "do X")

        self.assertEqual(
            buf.getvalue(), "[WARNING] something is off\nCorrective steps: do X\n"
        )

    def test_fault_still_reaches_claude_with_no_log_dir(self):
        """
        Given a Reporter with no log_dir
        When fault() is called
        Then stderr gets the labeled message AND drain_claude_context()
             returns the fault text -- the Claude buffer is per-instance
             state, not gated on a log directory having resolved
        """
        reporter = Reporter()
        buf = io.StringIO()
        with redirect_stderr(buf):
            reporter.fault("toolguard is broken", "investigate")

        self.assertEqual(
            buf.getvalue(),
            "[ERROR] toolguard is broken\nCorrective steps: investigate\n",
        )
        self.assertEqual(reporter.drain_claude_context(), "toolguard is broken")


class TestReporterRoutesWarning(unittest.TestCase):
    """A warning, with a resolvable log directory."""

    def test_warning_reaches_stderr_and_the_warning_log_only(self):
        """
        Given a Reporter with a resolvable, existing log directory
        When warning() is called
        Then stderr contains the message AND corrective steps (from the log
             stream's own echo), the WARNING log file contains both, and no
             error log file is created
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with _captured_stderr_reporter(log_dir) as (reporter, buf):
                reporter.warning("bad config", "fix the file")

            stderr_text = buf.getvalue()
            self.assertIn("bad config", stderr_text)
            self.assertIn("fix the file", stderr_text)
            self.assertEqual(stderr_text.count("bad config"), 1)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            content = warning_files[0].read_text()
            self.assertIn("bad config", content)
            self.assertIn("fix the file", content)

            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])

    def test_warning_never_reaches_claude(self):
        """
        Given a Reporter with a resolvable log directory
        When warning() is called
        Then drain_claude_context() returns None -- only faults reach Claude
        """
        with TemporaryDirectory() as tmpdir:
            reporter = Reporter(log_dir=Path(tmpdir))
            reporter.warning("bad config", "fix the file")
            self.assertIsNone(reporter.drain_claude_context())


class TestReporterRoutesFault(unittest.TestCase):
    """A fault, with a resolvable log directory."""

    def test_fault_reaches_stderr_the_error_log_and_claude(self):
        """
        Given a Reporter with a resolvable, existing log directory
        When fault() is called
        Then stderr and the ERROR log file both carry the message, no
             WARNING log file is created, and drain_claude_context() returns
             the message
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with _captured_stderr_reporter(log_dir) as (reporter, buf):
                reporter.fault("toolguard is broken", "investigate")
                claude_text = reporter.drain_claude_context()

            self.assertIn("toolguard is broken", buf.getvalue())

            error_files = list(log_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(error_files), 1)
            self.assertIn("toolguard is broken", error_files[0].read_text())

            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(claude_text, "toolguard is broken")

    def test_drain_clears_the_buffer(self):
        """
        Given a fault was reported and already drained once
        When drain_claude_context() is called again on the same instance
        Then it returns None -- draining is a take, not a peek
        """
        with TemporaryDirectory() as tmpdir:
            reporter = Reporter(log_dir=Path(tmpdir))
            reporter.fault("boom", "fix it")
            self.assertIsNotNone(reporter.drain_claude_context())
            self.assertIsNone(reporter.drain_claude_context())

    def test_multiple_faults_accumulate_in_report_order(self):
        """
        Given two faults are reported on the same instance
        When drain_claude_context() is called
        Then both messages are present, in the order they were reported
        """
        with TemporaryDirectory() as tmpdir:
            reporter = Reporter(log_dir=Path(tmpdir))
            reporter.fault("first", "a")
            reporter.fault("second", "b")
            text = reporter.drain_claude_context()

        self.assertIsNotNone(text)
        self.assertLess(text.index("first"), text.index("second"))


class TestReporterRoutesNotice(unittest.TestCase):
    """A notice stays stderr-only even with a resolvable log directory."""

    def test_notice_writes_stderr_only_no_logs_no_claude(self):
        """
        Given a Reporter with a resolvable log directory
        When notice() is called
        Then stderr gets exactly the message, no log file is created in
             either stream, and drain_claude_context() returns None
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with _captured_stderr_reporter(log_dir) as (reporter, buf):
                reporter.notice("migration running")
                claude_text = reporter.drain_claude_context()

            self.assertEqual(buf.getvalue(), "migration running\n")
            self.assertEqual(list(log_dir.iterdir()), [])
            self.assertIsNone(claude_text)


class TestLogDirectoryUnresolvable(unittest.TestCase):
    """The log directory does not exist / cannot be written to."""

    def test_unresolvable_log_dir_falls_back_to_stderr_without_raising(self):
        """
        Given the Reporter's log_dir does not exist
        When warning() is called
        Then it does not raise, and stderr still carries the message
        """
        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does-not-exist"
            with _captured_stderr_reporter(missing) as (reporter, buf):
                reporter.warning("bad config", "fix the file")

            self.assertIn("bad config", buf.getvalue())


class TestLogWriteFailureDegradesToStderr(unittest.TestCase):
    """The reporter's own log-writing path fails."""

    def test_write_failure_still_produces_stderr_and_does_not_raise(self):
        """
        Given the Reporter's "log directory" is actually a regular file (so
            the log stream's own mkdir() raises instead of writing)
        When fault() is called
        Then no exception propagates, and stderr still carries the message
        """
        with TemporaryDirectory() as tmpdir:
            not_a_directory = Path(tmpdir) / "log_dir_is_a_file"
            not_a_directory.write_text("occupied")

            with _captured_stderr_reporter(not_a_directory) as (reporter, buf):
                reporter.fault("toolguard is broken", "investigate")

            self.assertIn("toolguard is broken", buf.getvalue())


class TestReportersDoNotShareState(unittest.TestCase):
    """Each Reporter is a separate instance -- no shared/global buffer."""

    def test_a_second_reporter_starts_with_an_empty_claude_buffer(self):
        """
        Given a first Reporter reported a fault and was never drained
        When a second, separate Reporter is constructed
        Then the second Reporter's Claude buffer is empty -- the first
             Reporter's unfinished state does not leak into it
        """
        with TemporaryDirectory() as tmpdir:
            first = Reporter(log_dir=Path(tmpdir))
            first.fault("leftover from the first reporter", "n/a")

            second = Reporter(log_dir=Path(tmpdir))
            self.assertIsNone(second.drain_claude_context())


class TestFallbackShapeMatchesTheLoggedEcho(unittest.TestCase):
    """A reader of stderr cannot tell whether the log write happened."""

    def test_warning_stderr_is_identical_logged_or_degraded(self):
        """
        Given the same warning is reported twice, once through a Reporter
            with a resolvable log directory and once through one with none
        When each is captured on its own stderr
        Then the two stderr captures are byte-for-byte identical
        """
        message, corrective_steps = "bad config", "fix the file"
        with TemporaryDirectory() as tmpdir:
            with _captured_stderr_reporter(Path(tmpdir)) as (reporter, logged_buf):
                reporter.warning(message, corrective_steps)

        degraded_buf = io.StringIO()
        with redirect_stderr(degraded_buf):
            Reporter().warning(message, corrective_steps)

        self.assertEqual(logged_buf.getvalue(), degraded_buf.getvalue())


class TestRoutingLooksUpLogFnByName(unittest.TestCase):
    """`_ROUTING` must resolve `error_log`'s functions at dispatch time, not bind them at import."""

    def test_dispatch_calls_whatever_is_currently_bound_on_error_log(self):
        """
        Given `toolguard.error_log.log_warning` is patched with a stand-in
            AFTER `error_reporter` was already imported
        When warning() is called on a Reporter with a resolvable log directory
        Then the stand-in is called, not the original -- proving the
             reporter looks the function up at dispatch time
        """
        calls = []

        def _stand_in(message, corrective_steps, log_dir):
            calls.append(message)

        with TemporaryDirectory() as tmpdir:
            with patch.object(error_log, "log_warning", side_effect=_stand_in):
                Reporter(log_dir=Path(tmpdir)).warning("bad config", "fix the file")

        self.assertEqual(calls, ["bad config"])


class TestActiveRegistersTheAmbientReporter(unittest.TestCase):
    """`active()` is the registry `report_notice`/`report_warning` resolve against."""

    def test_report_warning_routes_through_the_registered_reporter(self):
        """
        Given a Reporter with a resolvable log directory is registered via active()
        When the module-level report_warning() is called
        Then it reaches that Reporter's log stream, not just stderr
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            reporter = Reporter(log_dir=log_dir)
            with error_reporter.active(reporter):
                error_reporter.report_warning("bad config", "fix the file")

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)

    def test_report_notice_routes_through_the_registered_reporter(self):
        """
        Given a Reporter is registered via active()
        When the module-level report_notice() is called
        Then it reaches that Reporter's stderr fallback (notice has no log
             stream), not a bare unregistered default
        """
        buf = io.StringIO()
        with TemporaryDirectory() as tmpdir:
            reporter = Reporter(log_dir=Path(tmpdir))
            with redirect_stderr(buf):
                with error_reporter.active(reporter):
                    error_reporter.report_notice("migration running")

        self.assertEqual(buf.getvalue(), "migration running\n")

    def test_no_reporter_registered_falls_back_to_the_default(self):
        """
        Given no Reporter has ever been registered via active()
        When report_warning() is called
        Then it degrades to the bare stderr-only default (a plain
             `Reporter()`, no log_dir)
        """
        buf = io.StringIO()
        with redirect_stderr(buf):
            error_reporter.report_warning("unregistered", "n/a")

        self.assertEqual(
            buf.getvalue(), "[WARNING] unregistered\nCorrective steps: n/a\n"
        )

    def test_active_restores_the_previous_registration_on_exit(self):
        """
        Given a Reporter is registered via active()
        When the with-block exits
        Then report_warning() afterward falls back to the default again --
             no leak into the next call
        """
        with TemporaryDirectory() as tmpdir:
            with error_reporter.active(Reporter(log_dir=Path(tmpdir))):
                pass

            buf = io.StringIO()
            with redirect_stderr(buf):
                error_reporter.report_warning("after the block", "n/a")

            self.assertEqual(
                buf.getvalue(), "[WARNING] after the block\nCorrective steps: n/a\n"
            )

    def test_nested_active_restores_the_outer_reporter_on_exit(self):
        """
        Given an outer Reporter is registered via active()
        When a nested active() registers an inner Reporter and exits
        Then the outer Reporter is in effect again afterward (LIFO restore)
        """
        with TemporaryDirectory() as outer_dir, TemporaryDirectory() as inner_dir:
            outer = Reporter(log_dir=Path(outer_dir))
            with error_reporter.active(outer):
                with error_reporter.active(Reporter(log_dir=Path(inner_dir))):
                    error_reporter.report_warning("inner", "n/a")

                error_reporter.report_warning("outer", "n/a")

            self.assertTrue(list(Path(inner_dir).glob("toolguard-warning-*.md")))
            self.assertTrue(list(Path(outer_dir).glob("toolguard-warning-*.md")))

    def test_active_restores_on_exception(self):
        """
        Given a Reporter is registered via active()
        When the with-block raises
        Then the previous registration is still restored -- report_warning()
             afterward falls back to the default, not the exited registration
        """
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(RuntimeError):
                with error_reporter.active(Reporter(log_dir=Path(tmpdir))):
                    raise RuntimeError("boom")

            buf = io.StringIO()
            with redirect_stderr(buf):
                error_reporter.report_warning("after the crash", "n/a")

            self.assertEqual(
                buf.getvalue(), "[WARNING] after the crash\nCorrective steps: n/a\n"
            )


if __name__ == "__main__":
    unittest.main()
