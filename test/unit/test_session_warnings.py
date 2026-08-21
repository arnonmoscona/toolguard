"""Unit tests for toolguard.session_warnings: the takeover-mode-active notice."""

import os
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import error_reporter
from toolguard.config_types import Provenance, TakeoverConfig, TakeoverEnabledConflict
from toolguard.error_reporter import Reporter
from toolguard.hook import _announce_takeover_state
from toolguard.session_warnings import issue_takeover_warning

#: The label NOTICE severity's stderr fallback would render if it had one
#: (see error_reporter._ROUTING) -- it does not, so this must never appear.
BANNER = "[TOOLGUARD WARNING]"
ACTIVE_CLAIM = "Takeover mode is active"
BYPASSED_CLAIM = "native permission prompts are bypassed"
SOLE_AUTHORITY_CLAIM = "sole authority"
FAIL_SAFE_MARKER = "Fail-safe applied"


def _tree(*roots):
    """Return the set of every file under each root, for a before/after comparison."""
    return {p for root in roots for p in Path(root).rglob("*") if p.is_file()}


class _RecordingReporter(Reporter):
    """A `Reporter` that records which severity method it received, for asserting routing."""

    def __init__(self, log_dir=None):
        super().__init__(log_dir=log_dir)
        self.notices = []

    def notice(self, message):
        self.notices.append(message)
        super().notice(message)

    def warning(self, message, corrective_steps):
        raise AssertionError("the takeover notice must not be reported as a warning")

    def fault(self, message, corrective_steps):
        raise AssertionError("the takeover notice must not be reported as a fault")


class TestIssueTakeoverWarning(unittest.TestCase):
    """The takeover-active notice: routed through the error reporter at notice severity, never throttled."""

    def test_routes_through_report_notice(self):
        """
        Given a Reporter registered via error_reporter.active()
        When issue_takeover_warning runs
        Then that Reporter's notice() method receives the call (not warning()
             or fault()) -- proving the notice is routed through the error
             reporter rather than written directly to a stream
        """
        reporter = _RecordingReporter()
        with error_reporter.active(reporter):
            with patch("sys.stderr", new_callable=StringIO):
                issue_takeover_warning(to_stdout=True)

        self.assertEqual(len(reporter.notices), 1)
        self.assertIn(ACTIVE_CLAIM, reporter.notices[0])

    def test_to_stdout_false_reports_nothing_to_the_reporter(self):
        """
        Given to_stdout=False and a Reporter registered via error_reporter.active()
        When issue_takeover_warning runs
        Then the Reporter receives no call at all -- the gate short-circuits
             before the reporter is reached
        """
        reporter = _RecordingReporter()
        with error_reporter.active(reporter):
            issue_takeover_warning(to_stdout=False)

        self.assertEqual(reporter.notices, [])

    def test_notice_goes_to_stderr(self):
        """
        Given to_stdout=True
        When issue_takeover_warning runs
        Then the notice is written to stderr -- notice severity's stderr
             fallback, since it has no log stream (error_reporter._ROUTING)
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            issue_takeover_warning(to_stdout=True)

        self.assertIn(ACTIVE_CLAIM, err.getvalue())

    def test_nothing_reaches_stdout(self):
        """
        Given to_stdout=True
        When issue_takeover_warning runs
        Then stdout stays empty -- stdout is the hook's JSON response channel, so
             a copy of the notice there would corrupt the permission decision
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            with patch("sys.stdout", new_callable=StringIO) as out:
                issue_takeover_warning(to_stdout=True)

        self.assertIn(ACTIVE_CLAIM, err.getvalue())
        self.assertEqual(out.getvalue(), "")

    def test_silent_when_to_stdout_false_and_that_silence_is_the_flag(self):
        """
        Given a call with to_stdout=True, then one with False, then True again
        When each call's streams are captured separately
        Then only the False call is silent -- the third call emitting again rules
             out silence caused by throttling or by the notice never being
             generated at all, which are otherwise indistinguishable
        """
        first = StringIO()
        with patch("sys.stderr", first):
            issue_takeover_warning(to_stdout=True)
        self.assertIn(ACTIVE_CLAIM, first.getvalue())

        quiet_err, quiet_out = StringIO(), StringIO()
        with patch("sys.stderr", quiet_err):
            with patch("sys.stdout", quiet_out):
                issue_takeover_warning(to_stdout=False)

        third = StringIO()
        with patch("sys.stderr", third):
            issue_takeover_warning(to_stdout=True)

        self.assertEqual(quiet_err.getvalue(), "")
        self.assertEqual(quiet_out.getvalue(), "")
        self.assertIn(ACTIVE_CLAIM, third.getvalue())

    def test_default_argument_writes_the_notice(self):
        """
        Given no explicit to_stdout argument
        When issue_takeover_warning runs
        Then the notice is still written (the default is True)
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            issue_takeover_warning()

        self.assertIn(ACTIVE_CLAIM, err.getvalue())

    def test_notice_text_is_accurate_only_for_the_ENABLED_state(self):
        """
        Given issue_takeover_warning runs
        When the emitted text is collected
        Then it carries the enabled-state claims and no banner -- notice
             severity has no stderr label (error_reporter._ROUTING), so the
             old `[TOOLGUARD WARNING]` prefix is gone, not just relocated

        This is the single text the function can emit, and it is TRUE only when
        takeover.enabled is True. It is emitted verbatim on hook's conflict
        branch too, where it is false; see TestTakeoverAnnouncementPerBranch.
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            issue_takeover_warning(to_stdout=True)

        printed = err.getvalue()

        self.assertNotIn(BANNER, printed)
        self.assertIn(ACTIVE_CLAIM, printed)
        self.assertIn(BYPASSED_CLAIM, printed)
        self.assertIn(SOLE_AUTHORITY_CLAIM, printed)

    def test_not_throttled_across_repeated_calls(self):
        """
        Given three consecutive calls with to_stdout=True
        When a Reporter registered via error_reporter.active() collects all three
        Then notice() was called three times -- it is a live reminder, so any
             once-per-process or once-per-session suppression is a regression
        """
        reporter = _RecordingReporter()
        with error_reporter.active(reporter):
            with patch("sys.stderr", new_callable=StringIO):
                for _ in range(3):
                    issue_takeover_warning(to_stdout=True)

        self.assertEqual(len(reporter.notices), 3)

    def test_persists_nothing_anywhere(self):
        """
        Given an isolated home, log directory and project root, and a
            Reporter registered via error_reporter.active() whose log_dir
            resolves into that log directory
        When issue_takeover_warning runs
        Then not one file is created under any of them -- notice severity has
             no log stream at all (error_reporter._ROUTING), so this holds
             even though a log directory IS available, not just because none
             was resolved
        """
        with TemporaryDirectory() as home, TemporaryDirectory() as logs:
            with TemporaryDirectory() as project:
                before = _tree(home, logs, project)
                env = {
                    "HOME": home,
                    "TOOLGUARD_LOG_DIR": logs,
                    "TOOLGUARD_PROJECT_ROOT": project,
                }
                reporter = Reporter(log_dir=Path(logs))
                with patch.object(Path, "home", return_value=Path(home)):
                    with patch.dict(os.environ, env, clear=True):
                        with error_reporter.active(reporter):
                            with patch("sys.stderr", new_callable=StringIO) as err:
                                issue_takeover_warning(to_stdout=True)

                self.assertIn(ACTIVE_CLAIM, err.getvalue())
                self.assertEqual(_tree(home, logs, project), before)

    def test_never_routes_through_the_error_log_streams(self):
        """
        Given the error-log streams patched at their shared entry points, and
            a Reporter registered via error_reporter.active() with a
            resolvable log_dir
        When issue_takeover_warning runs
        Then none of them is called -- notice severity's log_fn_name is None,
             so Reporter._dispatch never reaches error_log at all, log
             directory notwithstanding

        _log_entry is patched rather than log_warning/log_error/log_conflict
        because those three all reach it by a call-time global lookup, so the
        patch survives a `from toolguard.error_log import ...` binding taken at
        import time -- which patching the three by name does not.
        """
        with TemporaryDirectory() as tmp:
            reporter = Reporter(log_dir=Path(tmp))
            with patch("toolguard.error_log._log_entry") as entry:
                with patch("toolguard.error_log.log_crash") as crash:
                    with error_reporter.active(reporter):
                        with patch("sys.stderr", new_callable=StringIO) as err:
                            issue_takeover_warning(to_stdout=True)

        self.assertIn(ACTIVE_CLAIM, err.getvalue())
        entry.assert_not_called()
        crash.assert_not_called()


class TestTakeoverAnnouncementPerBranch(unittest.TestCase):
    """
    What each of hook._announce_takeover_state's branches tells the user.

    The notice's text is session_warnings' contract, but only its call sites fix
    the state it describes, so the branches are compared here as a set.
    """

    @staticmethod
    def _conflict():
        """Build a cross-level takeover_mode.enabled disagreement."""
        user = Provenance(
            "user", "toolguard_hook", "toml", Path("/fake/home/toolguard_hook.toml"), 9
        )
        project = Provenance(
            "project",
            "toolguard_hook",
            "toml",
            Path("/fake/proj/toolguard_hook.toml"),
            0,
        )
        return TakeoverEnabledConflict(((True, user), (False, project)))

    @staticmethod
    def _announce(takeover, with_log_dir=True):
        """
        Run the announcement against a throwaway log dir.

        Returns the pair (stderr text, {log file name: contents}).
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs" if with_log_dir else None
            err = StringIO()
            with patch("sys.stderr", err):
                _announce_takeover_state(takeover, log_dir)
            written = {}
            if log_dir is not None and log_dir.exists():
                written = {p.name: p.read_text() for p in log_dir.iterdir()}
            return err.getvalue(), written

    def test_enabled_branch_announces_the_bypass(self):
        """
        Given takeover.enabled is True
        When the state is announced
        Then the notice claims takeover is active and native prompts bypassed,
             which is exactly what has happened on this branch, and no conflict
             is logged
        """
        stderr, written = self._announce(TakeoverConfig(True, (), (), "deny"))

        self.assertIn(ACTIVE_CLAIM, stderr)
        self.assertIn(BYPASSED_CLAIM, stderr)
        self.assertEqual(written, {})

    def test_disabled_without_conflict_announces_nothing(self):
        """
        Given takeover.enabled is False and there is no conflict
        When the state is announced
        Then nothing is written -- the control that makes the other two
             branches' output attributable to their own branch
        """
        self.assertEqual(
            self._announce(TakeoverConfig(False, (), (), "deny")), ("", {})
        )

    def test_nothing_is_announced_without_a_log_dir(self):
        """
        Given takeover is enabled but no log directory was resolved
        When the state is announced
        Then nothing reaches stderr either -- the log dir gates the whole
             announcement, not just the log write
        """
        stderr, _written = self._announce(
            TakeoverConfig(True, (), (), "deny"), with_log_dir=False
        )

        self.assertEqual(stderr, "")

    def test_conflict_is_recorded_to_the_conflict_log(self):
        """
        Given a cross-level takeover_mode.enabled conflict
        When the state is announced
        Then a conflict log file names both disagreeing levels and the
             fail-safe that was applied
        """
        takeover = TakeoverConfig(False, (), (), "deny", self._conflict())

        _stderr, written = self._announce(takeover)

        self.assertEqual(len(written), 1)
        entry = next(iter(written.values()))
        self.assertIn(FAIL_SAFE_MARKER, entry)
        self.assertIn("/fake/home/toolguard_hook.toml", entry)
        self.assertIn("/fake/proj/toolguard_hook.toml", entry)

    def test_conflict_branch_must_not_claim_the_bypass_happened(self):
        """
        Given a cross-level takeover_mode.enabled conflict, which fail-safes
             enabled to False so native prompts stay active
        When the state is announced
        Then the output must not claim takeover is active or that native
             prompts are bypassed

        RED at HEAD, deliberately. The conflict branch calls
        issue_takeover_warning unchanged, so stderr states both "native
        permission prompts stay active and nothing is silently bypassed" and
        "native permission prompts are bypassed", two lines apart. Any of the
        candidate fixes -- a conflict-specific message, a state parameter, or
        dropping the call on this branch -- turns this green.
        """
        takeover = TakeoverConfig(False, (), (), "deny", self._conflict())

        stderr, _written = self._announce(takeover)

        self.assertIn(FAIL_SAFE_MARKER, stderr)
        self.assertNotIn(BYPASSED_CLAIM, stderr)
        self.assertNotIn(ACTIVE_CLAIM, stderr)


if __name__ == "__main__":
    unittest.main()
