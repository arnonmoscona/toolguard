"""Unit tests for toolguard.error_reporter -- which destination each severity reaches."""

import io
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import error_log, error_reporter
from toolguard.error_reporter import Reporter

#: The prefix `Reporter._dispatch` prints when the log call itself raised.
LOG_FAILURE_PREFIX = "Warning: error reporter failed to write log:"


@contextmanager
def _captured_stderr_reporter(log_dir):
    """Build a `Reporter(log_dir=log_dir)` with stderr redirected; yields ``(reporter, buffer)``."""
    buf = io.StringIO()
    with redirect_stderr(buf):
        yield Reporter(log_dir=log_dir), buf


@contextmanager
def _captured_streams():
    """Redirect both standard streams; yields ``(stdout_buffer, stderr_buffer)``."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        yield out, err


class _RecordingReporter(Reporter):
    """A `Reporter` that records the calls it receives, so a test can assert WHICH instance was reached."""

    def __init__(self, log_dir=None):
        super().__init__(log_dir=log_dir)
        self.received = []

    def notice(self, message):
        self.received.append(("notice", message))
        super().notice(message)

    def warning(self, message, corrective_steps):
        self.received.append(("warning", message))
        super().warning(message, corrective_steps)


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


class TestNothingIsWrittenToStdout(unittest.TestCase):
    """
    stdout is the hook's decision channel, so no severity may print there.

    The other tests here capture stderr with `redirect_stderr`, which is
    satisfied by a report landing on NEITHER stream as well as by one landing
    on stderr. These two watch both streams at once.
    """

    def test_no_severity_writes_to_stdout_when_logging_succeeds(self):
        """
        Given a Reporter with a resolvable log directory
        When notice(), warning() and fault() are all called
        Then stdout is empty and every message is on stderr
        """
        with TemporaryDirectory() as tmpdir:
            reporter = Reporter(log_dir=Path(tmpdir))
            with _captured_streams() as (out, err):
                reporter.notice("a notice")
                reporter.warning("a warning", "fix it")
                reporter.fault("a fault", "investigate")

        self.assertEqual(out.getvalue(), "")
        for message in ("a notice", "a warning", "a fault"):
            self.assertIn(message, err.getvalue())

    def test_no_severity_writes_to_stdout_on_the_stderr_fallback(self):
        """
        Given a Reporter with no log_dir, so every severity takes the stderr fallback
        When notice(), warning() and fault() are all called
        Then stdout is empty and every message is on stderr
        """
        reporter = Reporter()
        with _captured_streams() as (out, err):
            reporter.notice("a notice")
            reporter.warning("a warning", "fix it")
            reporter.fault("a fault", "investigate")

        self.assertEqual(out.getvalue(), "")
        for message in ("a notice", "a warning", "a fault"):
            self.assertIn(message, err.getvalue())


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
            self.assertNotIn(LOG_FAILURE_PREFIX, stderr_text)

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
            with redirect_stderr(io.StringIO()):
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
            with redirect_stderr(io.StringIO()):
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
            with redirect_stderr(io.StringIO()):
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


class TestMissingLogDirectoryIsCreated(unittest.TestCase):
    """A log directory that does not exist YET is created, not degraded away from."""

    def test_a_log_dir_that_does_not_exist_yet_is_created_and_written(self):
        """
        Given the Reporter's log_dir does not exist
        When warning() is called
        Then the directory is created, the warning lands in a log file inside
             it, and neither failure path says anything on stderr -- no
             degradation happened
        """
        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "does-not-exist"
            with _captured_stderr_reporter(missing) as (reporter, buf):
                reporter.warning("bad config", "fix the file")

            self.assertTrue(missing.is_dir())
            warning_files = list(missing.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertIn("bad config", warning_files[0].read_text())

            stderr_text = buf.getvalue()
            self.assertIn("bad config", stderr_text)
            self.assertNotIn(LOG_FAILURE_PREFIX, stderr_text)
            self.assertNotIn("Failed to write to log file", stderr_text)


class TestLogWriteFailureDegradesToStderr(unittest.TestCase):
    """The reporter's own log-writing path fails."""

    def test_write_failure_still_produces_stderr_and_does_not_raise(self):
        """
        Given the Reporter's "log directory" is actually a regular file (so
            the log stream's own mkdir() raises instead of writing)
        When fault() is called
        Then no exception propagates, stderr carries both the message and the
             reporter's own report of the failed log write, nothing was
             written next to the occupied path, and the fault still reaches
             Claude
        """
        with TemporaryDirectory() as tmpdir:
            not_a_directory = Path(tmpdir) / "log_dir_is_a_file"
            not_a_directory.write_text("occupied")

            with _captured_stderr_reporter(not_a_directory) as (reporter, buf):
                reporter.fault("toolguard is broken", "investigate")
                claude_text = reporter.drain_claude_context()

            stderr_text = buf.getvalue()
            self.assertIn("toolguard is broken", stderr_text)
            self.assertIn("investigate", stderr_text)
            self.assertIn(LOG_FAILURE_PREFIX, stderr_text)

            self.assertEqual(not_a_directory.read_text(), "occupied")
            self.assertEqual(
                [p.name for p in Path(tmpdir).iterdir()], ["log_dir_is_a_file"]
            )
            self.assertEqual(claude_text, "toolguard is broken")


class TestLogDirIsRefinedInPlace(unittest.TestCase):
    """`log_dir` is a plain mutable attribute -- `hook.main()` resolves it in two stages on ONE Reporter."""

    def test_a_log_dir_set_after_construction_takes_effect(self):
        """
        Given a Reporter that reported a fault before its log_dir was known
        When log_dir is assigned afterwards and a second fault is reported
        Then only the second fault reached the log file, while the Claude
             buffer still holds both -- the reporter reads log_dir per report,
             and refining it neither replaces the instance nor drops the buffer
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            reporter = Reporter()
            with redirect_stderr(io.StringIO()):
                reporter.fault("before the log dir resolved", "investigate")
                reporter.log_dir = log_dir
                reporter.fault("after the log dir resolved", "investigate")

            error_files = list(log_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(error_files), 1)
            logged = error_files[0].read_text()
            self.assertIn("after the log dir resolved", logged)
            self.assertNotIn("before the log dir resolved", logged)

            claude_text = reporter.drain_claude_context()
            self.assertIsNotNone(claude_text)
            self.assertIn("before the log dir resolved", claude_text)
            self.assertIn("after the log dir resolved", claude_text)


class TestReportersDoNotShareState(unittest.TestCase):
    """Each Reporter is a separate instance -- no shared/global buffer."""

    def test_a_second_reporter_starts_with_an_empty_claude_buffer(self):
        """
        Given a first Reporter reported a fault and was never drained
        When a second, separate Reporter is constructed
        Then the second Reporter's Claude buffer is empty while the first
             still holds its own message -- the first Reporter's unfinished
             state neither leaks into the second nor is consumed by it
        """
        with TemporaryDirectory() as tmpdir:
            first = Reporter(log_dir=Path(tmpdir))
            with redirect_stderr(io.StringIO()):
                first.fault("leftover from the first reporter", "n/a")

            second = Reporter(log_dir=Path(tmpdir))
            self.assertIsNone(second.drain_claude_context())
            self.assertEqual(
                first.drain_claude_context(), "leftover from the first reporter"
            )


class TestFallbackShapeMatchesTheLoggedEcho(unittest.TestCase):
    """A reader of stderr cannot tell whether the log write happened -- with one documented exception."""

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

    def test_empty_corrective_steps_is_the_one_documented_divergence(self):
        """
        Given a warning with EMPTY corrective steps, reported once with a log
            directory and once without
        When each is captured on its own stderr
        Then the logged one still prints the corrective-steps line and the
             degraded one omits it -- the single case where the two shapes
             differ, per _print_fallback's docstring
        """
        with TemporaryDirectory() as tmpdir:
            with _captured_stderr_reporter(Path(tmpdir)) as (reporter, logged_buf):
                reporter.warning("bad config", "")

        degraded_buf = io.StringIO()
        with redirect_stderr(degraded_buf):
            Reporter().warning("bad config", "")

        self.assertEqual(
            logged_buf.getvalue(), "[WARNING] bad config\nCorrective steps: \n"
        )
        self.assertEqual(degraded_buf.getvalue(), "[WARNING] bad config\n")


class TestRoutingLooksUpLogFnByName(unittest.TestCase):
    """`_ROUTING` must resolve `error_log`'s functions at dispatch time, not bind them at import."""

    def test_dispatch_calls_whatever_is_currently_bound_on_error_log(self):
        """
        Given `toolguard.error_log.log_warning` is patched with a stand-in
            AFTER `error_reporter` was already imported
        When warning() is called on a Reporter with a resolvable log directory
        Then the stand-in is called, not the original -- proving the
             reporter looks the function up at dispatch time. The absent log
             file is the other half of that proof: the real log_warning did
             not also run
        """
        calls = []

        def _stand_in(message, corrective_steps, log_dir):
            calls.append(message)

        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            with patch.object(
                error_log, "log_warning", side_effect=_stand_in
            ) as mock_log_warning:
                Reporter(log_dir=log_dir).warning("bad config", "fix the file")

            self.assertTrue(mock_log_warning.called)
            self.assertEqual(calls, ["bad config"])
            self.assertEqual(list(log_dir.iterdir()), [])


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
            with redirect_stderr(io.StringIO()):
                with error_reporter.active(reporter):
                    error_reporter.report_warning("bad config", "fix the file")

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertIn("bad config", warning_files[0].read_text())

    def test_report_notice_routes_through_the_registered_reporter(self):
        """
        Given a Reporter is registered via active()
        When the module-level report_notice() is called
        Then that very instance receives the call. Identity is the only
             observable here: notice has no log stream, so a registered
             Reporter and an unregistered default emit identical stderr
        """
        with TemporaryDirectory() as tmpdir:
            reporter = _RecordingReporter(log_dir=Path(tmpdir))
            with _captured_streams() as (out, err):
                with error_reporter.active(reporter):
                    error_reporter.report_notice("migration running")

        self.assertEqual(reporter.received, [("notice", "migration running")])
        self.assertEqual(err.getvalue(), "migration running\n")
        self.assertEqual(out.getvalue(), "")

    def test_no_reporter_registered_falls_back_to_the_default(self):
        """
        Given no Reporter is currently registered via active()
        When report_warning() is called
        Then it degrades to the stderr-only default -- a `Reporter` whose
             log_dir is None. The binding is asserted directly because a
             default holding a log directory would produce identical stderr
        """
        self.assertIsInstance(error_reporter._active, Reporter)
        self.assertIsNone(error_reporter._active.log_dir)

        buf = io.StringIO()
        with redirect_stderr(buf):
            error_reporter.report_warning("unregistered", "n/a")

        self.assertEqual(
            buf.getvalue(), "[WARNING] unregistered\nCorrective steps: n/a\n"
        )

    def test_active_restores_the_previous_registration_on_exit(self):
        """
        Given a Reporter with a log directory is registered via active()
        When the with-block exits and report_warning() is called again
        Then the exited Reporter receives nothing and its log directory stays
             empty. Its stderr shape cannot carry this: a leaked registration
             prints the same bytes the default does
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            registered = _RecordingReporter(log_dir=log_dir)
            with redirect_stderr(io.StringIO()):
                with error_reporter.active(registered):
                    pass

                registered.received.clear()
                buf = io.StringIO()
                with redirect_stderr(buf):
                    error_reporter.report_warning("after the block", "n/a")

            self.assertEqual(registered.received, [])
            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(
                buf.getvalue(), "[WARNING] after the block\nCorrective steps: n/a\n"
            )

    def test_nested_active_restores_the_outer_reporter_on_exit(self):
        """
        Given an outer Reporter is registered via active()
        When a nested active() registers an inner Reporter and exits
        Then each Reporter's log stream holds only its own message (LIFO restore)
        """
        with TemporaryDirectory() as outer_dir, TemporaryDirectory() as inner_dir:
            outer = Reporter(log_dir=Path(outer_dir))
            with redirect_stderr(io.StringIO()):
                with error_reporter.active(outer):
                    with error_reporter.active(Reporter(log_dir=Path(inner_dir))):
                        error_reporter.report_warning("inner", "n/a")

                    error_reporter.report_warning("outer", "n/a")

            inner_text = _only_warning_log(self, Path(inner_dir)).read_text()
            outer_text = _only_warning_log(self, Path(outer_dir)).read_text()
            self.assertIn("inner", inner_text)
            self.assertNotIn("outer", inner_text)
            self.assertIn("outer", outer_text)
            self.assertNotIn("inner", outer_text)

    def test_active_restores_on_exception(self):
        """
        Given a Reporter with a log directory is registered via active()
        When the with-block raises
        Then the registration is still undone -- the exited Reporter receives
             nothing afterward and its log directory stays empty
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            registered = _RecordingReporter(log_dir=log_dir)
            with self.assertRaises(RuntimeError):
                with error_reporter.active(registered):
                    raise RuntimeError("boom")

            registered.received.clear()
            buf = io.StringIO()
            with redirect_stderr(buf):
                error_reporter.report_warning("after the crash", "n/a")

            self.assertEqual(registered.received, [])
            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(
                buf.getvalue(), "[WARNING] after the crash\nCorrective steps: n/a\n"
            )


def _only_warning_log(test_case, log_dir):
    """Return the single warning log file in *log_dir*, failing the test if there is not exactly one."""
    files = list(log_dir.glob("toolguard-warning-*.md"))
    test_case.assertEqual(len(files), 1, f"expected one warning log in {log_dir}")
    return files[0]


if __name__ == "__main__":
    unittest.main()
