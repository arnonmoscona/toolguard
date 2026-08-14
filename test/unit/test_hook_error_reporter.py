"""
Unit tests for the error-reporter wiring in toolguard.hook: main() owns one
error_reporter.Reporter per invocation, registers it via error_reporter.active()
for the whole call, and drains its fault buffer into
hookSpecificOutput.additionalContext.

In production a fault comes only from an exception main() itself catches, so
these tests raise from a step inside main()'s try block -- the real path a
fault reaches additionalContext through.

Reuses test_hook.py's _fake_config/_NO_TAKEOVER doubles rather than
duplicating them (private-but-test-shared, per the project's API-visibility
convention).

Three module-level fixtures are load-bearing; see setUpModule.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import error_log, error_reporter
from toolguard.config import TakeoverConfig
from toolguard.config_types import RuntimeVerdict
from toolguard.hook import _finalize_output, _resolve_reporter_log_dir, main
from toolguard.session_warnings import issue_takeover_warning

from test.unit._config_isolation import isolate_log_dir_for_module
from test.unit.test_hook import _fake_config, _NO_TAKEOVER

_log_tmp_dir = None
_log_patcher = None
_root_tmp_dir = None
_root_patcher = None
_home_tmp_dir = None
_home_patcher = None
_crash_home = None

_HOOK_INPUT = {
    "tool_name": "Bash",
    "tool_input": {"command": "git status"},
    "hook_event_name": "PreToolUse",
}

_CRASH_PREFIX = "toolguard crashed while deciding"


class _FixtureHomePath:
    """Stands in for error_log's Path; home() is the fixture's, never the developer's."""

    def __new__(cls, *args, **kwargs):
        return Path(*args, **kwargs)

    @staticmethod
    def home():
        return _crash_home


class _HomelessPath:
    """Stands in for error_log's Path; home() raises as pathlib does with no resolvable home."""

    def __new__(cls, *args, **kwargs):
        return Path(*args, **kwargs)

    @staticmethod
    def home():
        raise RuntimeError("Could not determine home directory")


def _errors_dir_contents():
    """Crash reports log_crash has written under the fixture home, newest name last."""
    errors_dir = _crash_home / ".toolguard" / "errors"
    return (
        sorted(p.name for p in errors_dir.glob("*.md")) if errors_dir.exists() else []
    )


def setUpModule():
    """
    Install the three isolation anchors this module's tests reach.

    TOOLGUARD_LOG_DIR covers env_config's log resolution, as for test_hook.py.
    Two more are specific to this module:

    `toolguard.log_writer.require_project_root` -- main() resolves a COARSE
    log dir (`<project root>/logs`) before env_config exists, and warns to
    stderr when that directory is missing. Unpatched, TestOrdinaryInvocationStderr
    passes only because the developer's own repo happens to have a logs/
    directory: measured 2026-08-13, both its tests fail in a copy of the tree
    without one.

    `toolguard.error_log.Path` -- log_crash hard-codes `Path.home()` (proposed
    ticket 23), so a test driving main() through a crash writes a real crash
    report into the developer's ~/.toolguard/errors. Measured: 2 files per run
    of this module, against a directory that had accumulated 1,622.
    """
    global _log_tmp_dir, _log_patcher, _root_tmp_dir, _root_patcher
    global _home_tmp_dir, _home_patcher, _crash_home

    _log_tmp_dir, _log_patcher, _ = isolate_log_dir_for_module()

    _root_tmp_dir = TemporaryDirectory(prefix="too45_hook_reporter_root_")
    (Path(_root_tmp_dir.name) / "logs").mkdir()
    _root_patcher = patch(
        "toolguard.log_writer.require_project_root",
        return_value=Path(_root_tmp_dir.name),
    )
    _root_patcher.start()

    _home_tmp_dir = TemporaryDirectory(prefix="too45_hook_reporter_home_")
    _crash_home = Path(_home_tmp_dir.name)
    _home_patcher = patch("toolguard.error_log.Path", _FixtureHomePath)
    _home_patcher.start()


def tearDownModule():
    """Undo setUpModule's three patches and clean up their temp dirs."""
    _home_patcher.stop()
    _home_tmp_dir.cleanup()
    _root_patcher.stop()
    _root_tmp_dir.cleanup()
    _log_patcher.stop()
    _log_tmp_dir.cleanup()


def _run_main(divergence_side_effect=None, takeover=_NO_TAKEOVER):
    """Drive main() once against a governed, cleanly-allowed Bash command."""
    config = _fake_config(governed=["Bash"], bash=(["git *"], []), takeover=takeover)
    with patch("sys.stdin", StringIO(json.dumps(_HOOK_INPUT))):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command") as mock_log_command:
                        patches = []
                        if divergence_side_effect is not None:
                            patches.append(
                                patch(
                                    "toolguard.hook._run_divergence_check",
                                    side_effect=divergence_side_effect,
                                )
                            )
                        for p in patches:
                            p.start()
                        try:
                            try:
                                main()
                            except SystemExit:
                                pass
                        finally:
                            for p in patches:
                                p.stop()

    stdout_text = mock_stdout.getvalue()
    if not stdout_text.strip():
        raise AssertionError(
            "main() emitted nothing on stdout -- Claude Code reads that as no "
            "permission hook at all, not as a denial"
        )
    return json.loads(stdout_text), mock_stderr.getvalue(), mock_log_command


def _reporter_probe(observed, raising=None):
    """
    A _run_divergence_check stand-in that records the Reporter in force inside
    main(), then optionally raises.

    Records the reporter main() actually USES rather than the one it
    constructs: a main() that constructs per invocation but then reuses an
    earlier instance is the same leak, and construction alone cannot see it.
    """

    def probe(*_args, **_kwargs):
        observed.append(error_reporter._active)
        if raising is not None:
            raise raising

    return probe


class TestFixtureIsolationIsLive(unittest.TestCase):
    """setUpModule's patches are consulted -- otherwise every test below is isolated by luck."""

    def test_a_crash_writes_its_report_into_the_fixture_home(self):
        """
        Given main() crashes while resolving, so its except handler calls
            log_crash, which resolves ~/.toolguard/errors from Path.home()
        When the fixture's error_log.Path stands in for pathlib's
        Then the crash report lands under the fixture home, proving the patch
             is consulted and that no report reaches the real ~/.toolguard/errors
        """
        before = _errors_dir_contents()

        _run_main(divergence_side_effect=RuntimeError("crash for the report"))

        after = _errors_dir_contents()
        self.assertGreater(len(after), len(before))
        newest = (
            _crash_home / ".toolguard" / "errors" / sorted(set(after) - set(before))[0]
        )
        self.assertIn("crash for the report", newest.read_text(encoding="utf-8"))

    def test_the_coarse_log_dir_resolves_inside_the_fixture_root(self):
        """
        Given main()'s pre-env_config log-dir fallback resolves
            `require_project_root() / "logs"`
        When this module's patch supplies a fixture root that has one
        Then the resolved directory is the fixture's, not the real repo's --
             the difference between an empty stderr and a "Logging directory
             does not exist" warning
        """
        self.assertEqual(
            _resolve_reporter_log_dir(None), Path(_root_tmp_dir.name) / "logs"
        )


class TestFaultReachesAdditionalContext(unittest.TestCase):
    """A crash mid-resolution still reaches the final JSON response."""

    def test_crash_during_divergence_check_reaches_additional_context(self):
        """
        Given _run_divergence_check raises while main() resolves a governed,
            otherwise-cleanly-allowed Bash command
        When main()'s except handler builds its JSON response
        Then it is a deny whose additionalContext carries both the crash
             prefix and the raising exception's own message
        """
        output, _stderr, _log = _run_main(
            divergence_side_effect=RuntimeError("divergence check exploded")
        )

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn(_CRASH_PREFIX, context)
        self.assertIn("divergence check exploded", context)

    def test_no_fault_omits_additional_context_entirely(self):
        """
        Given nothing raises during the invocation
        When main() builds its JSON response
        Then additionalContext is absent (not present as an empty string)
        """
        output, _stderr, _log = _run_main()

        self.assertNotIn("additionalContext", output["hookSpecificOutput"])

    def test_a_clean_invocation_still_logs_the_allowed_command(self):
        """
        Given a cleanly-allowed Bash command and no fault
        When main() finishes
        Then log_command was called -- the patch this module's fixture applies
             to it is on a path the code really takes, not an inert mock
        """
        _output, _stderr, mock_log_command = _run_main()

        self.assertTrue(mock_log_command.called)

    def test_a_rule_supplied_context_is_kept_alongside_the_fault(self):
        """
        Given a verdict that already carries additionalContext of its own AND
            a reporter holding a buffered fault
        When _finalize_output merges the two
        Then both survive, the rule's text first -- the branch no end-to-end
             path reaches, because the only fault() call site builds its
             verdict without additional_context
        """
        reporter = error_reporter.Reporter()
        with patch("sys.stderr", new_callable=StringIO):
            reporter.fault("reporter said so", "")

        output = _finalize_output(
            RuntimeVerdict(
                decision="allow", reason="matched", additional_context="rule said so"
            ),
            reporter,
        )

        merged = output["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(merged, "rule said so\n\nreporter said so")


class TestFaultSurvivesCrashLoggingFailing(unittest.TestCase):
    """
    The reporter-side half of proposed ticket 23. test_hook.py's
    TestDecisionReachesStdoutWhenCrashLoggingFails asserts a deny still reaches
    stdout when log_crash raises; nothing asserts the CRASH FAULT still reaches
    Claude on that path, which is what this module is about. log_crash runs
    ahead of _report_crash_fault in all three handlers, so its failure takes
    the fault with it.
    """

    def test_the_crash_fault_still_reaches_additional_context(self):
        """
        Given a crash during resolution and a home directory crash logging
            cannot resolve, so log_crash raises inside main()'s except clause
        When main() builds its JSON response
        Then additionalContext still carries the crash fault
        """
        escaped = None
        output = None
        with patch("toolguard.error_log.Path", _HomelessPath):
            # Without this the fixture cannot produce the negative case.
            with self.assertRaises(RuntimeError):
                error_log.Path.home()
            try:
                output, _stderr, _log = _run_main(
                    divergence_side_effect=RuntimeError("crash with logging broken")
                )
            except Exception as exc:  # noqa: BLE001 -- the failure under test
                escaped = exc

        self.assertIsNone(
            escaped,
            f"main() let {type(escaped).__name__}({escaped}) escape its own "
            f"except clause, so no fault was ever reported",
        )
        self.assertIn(_CRASH_PREFIX, output["hookSpecificOutput"]["additionalContext"])


class TestInvocationStateDoesNotLeakBetweenCalls(unittest.TestCase):
    """
    No state leak across invocations. Two independent mechanisms produce that:
    main() constructs a fresh Reporter per call, AND drain_claude_context()
    clears the buffer it returns. Either alone is enough to keep a second
    invocation's output clean, so a single test comparing two invocations
    cannot see either one break -- each test below names one.
    """

    def test_each_invocation_uses_its_own_reporter(self):
        """
        Given two separate main() invocations in the same process
        When a probe inside each reads the Reporter in force
        Then they are distinct instances -- one Reporter spanning both would
             carry log_dir and buffer state from the first into the second
        """
        used = []
        _run_main(divergence_side_effect=_reporter_probe(used))
        _run_main(divergence_side_effect=_reporter_probe(used))

        self.assertEqual(len(used), 2, "the probe did not run once per invocation")
        self.assertIsNot(used[0], used[1])

    def test_draining_leaves_the_invocations_reporter_empty(self):
        """
        Given a crashing invocation whose fault was drained into the response
        When the same Reporter is drained again afterwards
        Then it yields nothing -- the buffer was cleared, not merely copied
        """
        used = []
        output, _stderr, _log = _run_main(
            divergence_side_effect=_reporter_probe(
                used, raising=RuntimeError("crash to buffer a fault")
            )
        )

        self.assertEqual(len(used), 1, "the probe never ran")
        self.assertIn(_CRASH_PREFIX, output["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(used[0].drain_claude_context())

    def test_a_second_crashing_invocation_reports_only_its_own_fault(self):
        """
        Given a first main() invocation that crashes and reports a fault
        When a second, separate invocation crashes with a different message
        Then the second response carries only its own fault text -- the first
             invocation's is gone, which an in-process replay harness would
             otherwise expose
        """
        first_output, _stderr, _log = _run_main(
            divergence_side_effect=RuntimeError("first invocation's crash")
        )
        second_output, _stderr, _log = _run_main(
            divergence_side_effect=RuntimeError("second invocation's crash")
        )

        first_context = first_output["hookSpecificOutput"]["additionalContext"]
        second_context = second_output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("first invocation's crash", first_context)
        self.assertIn("second invocation's crash", second_context)
        self.assertNotIn("first invocation's crash", second_context)

    def test_a_clean_invocation_after_a_crash_carries_no_additional_context(self):
        """
        Given a first main() invocation that crashes and reports a fault
        When a second, separate invocation runs afterward and nothing raises
        Then the second invocation's output has no additionalContext at all
        """
        _first, _stderr, _log = _run_main(
            divergence_side_effect=RuntimeError("first invocation's crash")
        )
        second_output, _stderr, _log = _run_main()

        self.assertNotIn("additionalContext", second_output["hookSpecificOutput"])


class TestReporterRegistryIsRegisteredAndRestored(unittest.TestCase):
    """
    main() wraps its whole try/except in error_reporter.active(reporter). A
    test that only checks the registry afterwards cannot tell "restored" from
    "never registered", so the first test below observes the registry from
    INSIDE the invocation.
    """

    def test_main_registers_its_own_reporter_then_restores_the_previous_one(self):
        """
        Given an outer Reporter registered before main() runs
        When a probe inside main()'s try block reads the registry, and the
            registry is read again after main() returns
        Then main() had displaced the outer Reporter with one of its own, and
             the outer one is back afterwards -- a registration that never
             happened restores identically, so both halves are needed
        """
        outer = error_reporter.Reporter()
        used = []

        with error_reporter.active(outer):
            _run_main(divergence_side_effect=_reporter_probe(used))

            self.assertEqual(len(used), 1, "the probe never ran")
            self.assertIsNot(used[0], outer)
            self.assertIs(error_reporter._active, outer)

    def test_a_crashing_invocation_restores_the_previous_registration(self):
        """
        Given an outer Reporter registered before main() runs
        When the invocation crashes and is handled by main()'s except clause
        Then the registry still points back at the outer Reporter
        """
        outer = error_reporter.Reporter()
        used = []

        with error_reporter.active(outer):
            _run_main(
                divergence_side_effect=_reporter_probe(
                    used, raising=RuntimeError("crash inside active()")
                )
            )

            self.assertEqual(len(used), 1, "the probe never ran")
            self.assertIsNot(used[0], outer)
            self.assertIs(error_reporter._active, outer)


class TestOuterReporterCoversGetEnvConfigAndHandlers(unittest.TestCase):
    """
    main()'s Reporter is constructed and registered via error_reporter.active()
    BEFORE get_env_config() runs, so a crash there still has a Reporter to
    report through, and the except handlers share that same instance.
    """

    def test_get_env_config_raising_reaches_the_crash_response_on_stdout(self):
        """
        Given get_env_config() itself raises
        When main()'s top-level `except Exception` handler builds its JSON
            response
        Then the response is printed to STDOUT, not stderr, and is a deny
            carrying the crash fault in additionalContext
        """
        with patch("sys.stdin", StringIO(json.dumps(_HOOK_INPUT))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    with patch(
                        "toolguard.hook.get_env_config",
                        side_effect=RuntimeError("env config is broken"),
                    ) as mock_get_env_config:
                        try:
                            main()
                        except SystemExit:
                            pass

        self.assertTrue(mock_get_env_config.called)
        self.assertNotIn('"permissionDecision"', mock_stderr.getvalue())
        stdout_text = mock_stdout.getvalue()
        self.assertTrue(stdout_text.strip(), "expected a non-empty decision on stdout")
        output = json.loads(stdout_text)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn(_CRASH_PREFIX, context)
        self.assertIn("env config is broken", context)


class TestOrdinaryInvocationStderr(unittest.TestCase):
    """What actually reaches stderr on a clean, uneventful invocation."""

    def test_takeover_disabled_writes_nothing_to_stderr(self):
        """
        Given takeover mode is disabled (no notice classified condition
            applies) and nothing reports a warning or fault
        When main() resolves a cleanly-allowed Bash command
        Then stderr is completely empty
        """
        _output, stderr_text, _log = _run_main(takeover=_NO_TAKEOVER)

        self.assertEqual(stderr_text, "")

    def test_takeover_enabled_stderr_matches_only_the_notice(self):
        """
        Given takeover mode is enabled (the one notice-classified condition
            that fires on every call) and nothing reports a warning or fault
        When main() resolves a cleanly-allowed Bash command
        Then stderr is EXACTLY the takeover notice's own text -- nothing
             from any warning/error/fault path is mixed in
        """
        takeover_enabled = TakeoverConfig(True, (), (), "deny")

        expected_buf = StringIO()
        with patch("sys.stderr", expected_buf):
            issue_takeover_warning(to_stdout=True)
        expected = expected_buf.getvalue()
        # Without this the comparison below holds for two empty strings, and
        # a notice that emitted nothing would read as a match.
        self.assertTrue(expected.strip())

        _output, stderr_text, _log = _run_main(takeover=takeover_enabled)

        self.assertEqual(stderr_text, expected)


if __name__ == "__main__":
    unittest.main()
