"""
Unit tests for the error-reporter wiring in toolguard.hook: main() owns one
error_reporter.Reporter per invocation, and drains its fault buffer into
hookSpecificOutput.additionalContext.

In production a fault comes only from an exception main() itself catches, so
these tests raise from a step inside main()'s try block -- the real path a
fault reaches additionalContext through.

Reuses test_hook.py's _fake_config/_NO_TAKEOVER doubles rather than
duplicating them (private-but-test-shared, per the project's API-visibility
convention).
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
    """Redirect TOOLGUARD_LOG_DIR to an isolated temp dir for this whole module."""
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
    """A crash mid-resolution still reaches the final JSON response."""

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
    """No state leak across invocations: each main() call constructs its own Reporter."""

    def test_second_invocations_output_carries_no_trace_of_the_first_faults(self):
        """
        Given a first main() invocation crashes and reports a fault
        When a second, separate main() invocation runs afterward in the same
            process and nothing raises
        Then the second invocation's output has no additionalContext at all --
             the per-invocation Reporter resets rather than persisting as a
             module global, which an in-process replay harness would expose
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
        with TemporaryDirectory() as tmpdir:
            # Crashing before load_configuration() makes the Reporter fall back
            # to require_project_root(), which this module's TOOLGUARD_LOG_DIR
            # isolation does not cover: unpatched, this trips the real-log-dir guard.
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
    """What actually reaches stderr on a clean, uneventful invocation."""

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
