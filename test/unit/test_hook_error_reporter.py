"""
Unit tests for the error-reporter wiring in toolguard.hook (TOO-45 punch-list
#04, and its follow-up: main() now owns exactly one error_reporter.Reporter
for the whole invocation, threaded explicitly, instead of the module-global
fault buffer and the two nested error_reporter "invocation" scopes -- see
toolguard/error_reporter.py's module docstring). The fault buffer is drained
into hookSpecificOutput.additionalContext.

Reuses test_hook.py's _fake_config/_NO_TAKEOVER doubles rather than
duplicating them (private-but-test-shared, per the project's API-visibility
convention).

A fault now has exactly ONE production trigger: an exception main() itself
catches (report_fault's only caller is _report_crash_fault, in the three
except handlers) -- there is no longer a module-level report_fault an
arbitrary call site can reach, by design (the Claude-facing buffer is
per-invocation instance state on hook.py's own Reporter, not ambient). Tests
below trigger a fault by making a step inside the try block raise, which is
the real path a fault reaches additionalContext through.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.config import TakeoverConfig
from toolguard.hook import main
from toolguard.session_warnings import issue_takeover_warning

from test.unit._config_isolation import isolate_log_dir_for_module
from test.unit.test_hook import _fake_config, _NO_TAKEOVER

_log_tmp_dir = None
_log_patcher = None

_HOOK_INPUT = {
    "tool_name": "Bash",
    "tool_input": {"command": "git status"},
    "hook_event_name": "PreToolUse",
}


def setUpModule():
    """Redirect TOOLGUARD_LOG_DIR to an isolated temp dir for this whole module (TOO-19)."""
    global _log_tmp_dir, _log_patcher
    _log_tmp_dir, _log_patcher, _ = isolate_log_dir_for_module()


def tearDownModule():
    """Undo the module-wide TOOLGUARD_LOG_DIR isolation and clean up its temp dir."""
    _log_patcher.stop()
    _log_tmp_dir.cleanup()


def _run_main(divergence_side_effect=None, takeover=_NO_TAKEOVER):
    """Drive main() once against a governed, cleanly-allowed Bash command."""
    config = _fake_config(governed=["Bash"], bash=(["git *"], []), takeover=takeover)
    with patch("sys.stdin", StringIO(json.dumps(_HOOK_INPUT))):
        with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
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

    return json.loads(mock_stdout.getvalue()), mock_stderr.getvalue()


class TestFaultReachesAdditionalContext(unittest.TestCase):
    """A crash mid-resolution still reaches the final JSON response, via
    main()'s own crash-fault handling (the sole production path -- see the
    module docstring)."""

    def test_crash_during_divergence_check_reaches_additional_context(self):
        """
        Given _run_divergence_check raises while main() resolves a governed,
            otherwise-cleanly-allowed Bash command
        When main()'s except handler builds its JSON response
        Then it is a deny carrying the crash fault in
             hookSpecificOutput.additionalContext
        """
        output, _stderr = _run_main(
            divergence_side_effect=RuntimeError("divergence check exploded")
        )

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "toolguard crashed while deciding",
            output["hookSpecificOutput"]["additionalContext"],
        )

    def test_no_fault_omits_additional_context_entirely(self):
        """
        Given nothing raises during the invocation
        When main() builds its JSON response
        Then additionalContext is absent (not present as an empty string)
        """
        output, _stderr = _run_main()

        self.assertNotIn("additionalContext", output["hookSpecificOutput"])


class TestInvocationStateDoesNotLeakBetweenCalls(unittest.TestCase):
    """TOO-45 punch-list #04 item 4: no state leak across invocations -- each
    main() call constructs its own Reporter (see toolguard.hook.main)."""

    def test_second_invocations_output_carries_no_trace_of_the_first_faults(self):
        """
        Given a first main() invocation crashes and reports a fault
        When a second, separate main() invocation runs afterward in the same
            process and nothing raises
        Then the second invocation's output has no additionalContext at all
             -- proving the per-invocation Reporter resets rather than
             persisting as a module global (the in-process replay harness
             concern this item exists to close)
        """
        first_output, _ = _run_main(
            divergence_side_effect=RuntimeError("first invocation's crash")
        )
        second_output, _ = _run_main()

        self.assertIn(
            "toolguard crashed while deciding",
            first_output["hookSpecificOutput"]["additionalContext"],
        )
        self.assertNotIn("additionalContext", second_output["hookSpecificOutput"])


class TestOuterReporterCoversGetEnvConfigAndHandlers(unittest.TestCase):
    """
    TOO-45 punch-list #04 fix pass items 1 and 2, still true under the
    single-Reporter design: main()'s Reporter is constructed and registered
    via error_reporter.active() BEFORE get_env_config() runs, so a crash
    there still has a Reporter to report through, and the except handlers
    (which share that same instance) can still deliver a decision.
    """

    def test_get_env_config_raising_reaches_the_crash_response_on_stdout(self):
        """
        Given get_env_config() itself raises
        When main()'s top-level `except Exception` handler builds its JSON
            response
        Then the response -- printed to STDOUT (TOO-45 punch-list #04
            hook.py fix: the except handlers used to print here to stderr
            and exit 0, the fail-open) -- is a deny carrying the crash fault
            in additionalContext, and stdout is non-empty
        """
        with TemporaryDirectory() as tmpdir:
            # get_env_config() raising happens before load_configuration()
            # runs, so main()'s Reporter resolves its log directory via
            # toolguard.log_writer.require_project_root(), independently of
            # this module's TOOLGUARD_LOG_DIR isolation -- redirect it too,
            # or this test would resolve (and, via the real-log-dir guard,
            # trip) the real repo's logs/ directory.
            isolated_root = Path(tmpdir)
            (isolated_root / "logs").mkdir()

            with patch("sys.stdin", StringIO(json.dumps(_HOOK_INPUT))):
                with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                        with patch(
                            "toolguard.hook.get_env_config",
                            side_effect=RuntimeError("env config is broken"),
                        ):
                            with patch("toolguard.hook.log_crash"):
                                with patch(
                                    "toolguard.log_writer.require_project_root",
                                    return_value=isolated_root,
                                ):
                                    try:
                                        main()
                                    except SystemExit:
                                        pass

        # What must NOT be on stderr is the decision itself.
        self.assertNotIn('"permissionDecision"', mock_stderr.getvalue())
        stdout_text = mock_stdout.getvalue()
        self.assertTrue(stdout_text.strip(), "expected a non-empty decision on stdout")
        output = json.loads(stdout_text)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "toolguard crashed while deciding",
            output["hookSpecificOutput"]["additionalContext"],
        )


class TestOrdinaryInvocationStderr(unittest.TestCase):
    """
    Machine-checks the ticket's disputed premise: what actually reaches
    stderr on a clean, uneventful invocation.
    """

    def test_takeover_disabled_writes_nothing_to_stderr(self):
        """
        Given takeover mode is disabled (no notice classified condition
            applies) and nothing reports a warning or fault
        When main() resolves a cleanly-allowed Bash command
        Then stderr is completely empty
        """
        _output, stderr_text = _run_main(takeover=_NO_TAKEOVER)

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

        _output, stderr_text = _run_main(takeover=takeover_enabled)

        self.assertEqual(stderr_text, expected_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
