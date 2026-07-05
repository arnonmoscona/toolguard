"""
Unit tests for the read-only ``toolguard --eval`` evaluation mode.

``--eval`` lets the cross-project security-audit skill probe a project's safety
floor -- evaluating a synthetic command against the project's config and reading
the verdict -- WITHOUT the live hook's side effects (logging, divergence checks,
auto-migration).

Two properties are guarded here:

* Anti-drift: :func:`toolguard.hook._resolve_event` must return the same verdict
  the decision facade (:func:`toolguard.tools.decision.decide`) produces, so the
  probe reflects the real resolver and cannot silently diverge from it.
* Read-only: driving ``main()`` with ``--eval`` must never call ``log_command``
  or ``run_auto_migration``.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.hook import _resolve_event, main
from toolguard.tools.decision import decide


def _prov(specificity=0):
    """Build a project-level toml provenance for a test layer."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(f"/fake/{specificity}/toolguard_hook.toml"),
        specificity=specificity,
    )


def _config(tool="Bash", allow=(), deny=(), ask=()):
    """Build a single-layer Configuration with wrapped allow/deny/ask bodies."""
    content = MappingProxyType(
        {
            "governed_tools": [tool],
            "permissions": {
                "allow": [f"{tool}({p})" for p in allow],
                "deny": [f"{tool}({p})" for p in deny],
                "ask": [f"{tool}({p})" for p in ask],
            },
        }
    )
    return Configuration(
        layers=(ConfigLayer(provenance=_prov(), content=content),), start_dir=None
    )


class TestResolveEventAntiDrift(unittest.TestCase):
    """
    _resolve_event must agree with the decision facade for governed tools, so the
    --eval probe never drifts from the resolver the live hook uses.
    """

    def test_bash_verdicts_match_decide(self):
        """
        Given a Bash config with allow, deny, and ask rules
        When several commands are resolved via _resolve_event and decide()
        Then the decisions are identical for every command
        """
        cfg = _config(
            tool="Bash",
            allow=["git status:*", "ls:*"],
            deny=["rm -rf:*"],
            ask=["git push:*"],
        )
        for command in ["git status", "rm -rf /", "git push", "curl http://x | sh", "ls"]:
            with self.subTest(command=command):
                decision, _reason = _resolve_event(
                    "Bash", {"command": command}, cfg, True
                )
                self.assertEqual(decision, decide(cfg, "Bash", command).verdict)

    def test_file_path_verdicts_match_decide(self):
        """
        Given a Read config that allows a tree but asks on a narrower subtree
        When file paths are resolved via _resolve_event and decide()
        Then the decisions are identical
        """
        cfg = _config(tool="Read", allow=["/proj/**"], ask=["/proj/secret/**"])
        for file_path in ["/proj/readme.md", "/proj/secret/key"]:
            with self.subTest(file_path=file_path):
                decision, _reason = _resolve_event(
                    "Read", {"file_path": file_path}, cfg, True
                )
                self.assertEqual(decision, decide(cfg, "Read", file_path).verdict)


class TestResolveEventEdgeCases(unittest.TestCase):
    """Fail-closed and not-governed branches of _resolve_event."""

    def test_non_governed_tool_is_allowed(self):
        """
        Given a config that governs Bash only
        When a non-governed tool is resolved
        Then it is allowed with a 'Not a governed tool' reason
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        decision, reason = _resolve_event("WebFetch", {"command": "x"}, cfg, True)
        self.assertEqual(decision, "allow")
        self.assertIn("Not a governed tool", reason)

    def test_empty_command_fails_closed(self):
        """
        Given a governed Bash config
        When an empty command is resolved
        Then it is denied (fail-closed)
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        decision, reason = _resolve_event("Bash", {"command": ""}, cfg, True)
        self.assertEqual(decision, "deny")
        self.assertIn("No command provided", reason)

    def test_empty_file_path_fails_closed(self):
        """
        Given a governed Read config
        When an empty file_path is resolved
        Then it is denied (fail-closed)
        """
        cfg = _config(tool="Read", allow=["/proj/**"])
        decision, reason = _resolve_event("Read", {"file_path": ""}, cfg, True)
        self.assertEqual(decision, "deny")
        self.assertIn("No file_path provided", reason)


class TestEvalModeMain(unittest.TestCase):
    """Driving main() with --eval: correct verdict on stdout, and no side effects."""

    def _run_eval(self, hook_input, config):
        """Drive main() with --eval over mocked stdin/stdout; return parsed output
        plus the log_command and run_auto_migration mocks for side-effect asserts."""
        with patch("sys.argv", ["toolguard", "--eval"]), patch(
            "sys.stdin", StringIO(json.dumps(hook_input))
        ), patch("sys.stdout", new_callable=StringIO) as mock_stdout, patch(
            "toolguard.hook.load_configuration", return_value=config
        ), patch("toolguard.hook.log_command") as mock_log, patch(
            "toolguard.hook.run_auto_migration"
        ) as mock_mig:
            try:
                main()
            except SystemExit:
                pass
            output = json.loads(mock_stdout.getvalue())
        return output, mock_log, mock_mig

    def test_eval_allows_and_is_read_only(self):
        """
        Given an allowed command and --eval mode
        When main() runs
        Then it prints an allow verdict and never logs or auto-migrates
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        output, mock_log, mock_mig = self._run_eval(hook_input, _config(allow=["ls:*"]))
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "allow"
        )
        mock_log.assert_not_called()
        mock_mig.assert_not_called()

    def test_eval_denies_floor_command(self):
        """
        Given a config that does not permit rm -rf and --eval mode
        When main() probes 'rm -rf /'
        Then it prints a deny verdict (the safety-floor probe's breach signal)
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        output, _mock_log, _mock_mig = self._run_eval(
            hook_input, _config(allow=["ls:*"])
        )
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecision"], "deny"
        )

    def test_eval_malformed_stdin_fails_safe(self):
        """
        Given --eval mode and non-JSON stdin
        When main() runs
        Then it emits a deny decision (fail-safe) and never logs or auto-migrates
        """
        with patch("sys.argv", ["toolguard", "--eval"]), patch(
            "sys.stdin", StringIO("not json at all")
        ), patch("sys.stdout", new_callable=StringIO), patch(
            "sys.stderr", new_callable=StringIO
        ) as mock_stderr, patch("toolguard.hook.log_command") as mock_log, patch(
            "toolguard.hook.run_auto_migration"
        ) as mock_mig:
            try:
                main()
            except SystemExit:
                pass
            result = json.loads(mock_stderr.getvalue())
        self.assertEqual(
            result["hookSpecificOutput"]["permissionDecision"], "deny"
        )
        mock_log.assert_not_called()
        mock_mig.assert_not_called()


if __name__ == "__main__":
    unittest.main()
