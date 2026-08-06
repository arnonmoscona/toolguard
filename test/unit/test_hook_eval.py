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

from test.unit._config_isolation import isolate_log_dir_for_module

# TOO-19: --eval mode itself never logs (see _run_eval_mode's docstring), but
# TestEvalMatchesLiveHookUnderFallback also drives main() WITHOUT --eval (the
# live-hook path) to compare verdicts, and that path unconditionally reaches
# toolguard.env_config.get_env_config() to resolve TOOLGUARD_LOG_DIR for the
# config-discovery diagnostic log, before load_configuration() is even
# consulted. Without this, that resolution falls back to the real process cwd
# (the repo root under `unittest discover`) and writes real entries into the
# developer's live logs/ directory. See test/unit/_config_isolation.py's
# module docstring and .claude/rules/test-config-isolation.md.
_log_tmp_dir = None
_log_patcher = None


def setUpModule():
    """Redirect TOOLGUARD_LOG_DIR to an isolated temp dir for this whole module (TOO-19)."""
    global _log_tmp_dir, _log_patcher
    _log_tmp_dir, _log_patcher, _ = isolate_log_dir_for_module()


def tearDownModule():
    """Undo the module-wide TOOLGUARD_LOG_DIR isolation and clean up its temp dir."""
    _log_patcher.stop()
    _log_tmp_dir.cleanup()


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
        for command in [
            "git status",
            "rm -rf /",
            "git push",
            "curl http://x | sh",
            "ls",
        ]:
            with self.subTest(command=command):
                verdict = _resolve_event("Bash", {"command": command}, cfg, True)
                self.assertEqual(verdict.decision, decide(cfg, "Bash", command).verdict)

    def test_file_path_verdicts_match_decide(self):
        """
        Given a Read config that allows a tree but asks on a narrower subtree
        When file paths are resolved via _resolve_event and decide()
        Then the decisions are identical
        """
        cfg = _config(tool="Read", allow=["/proj/**"], ask=["/proj/secret/**"])
        for file_path in ["/proj/readme.md", "/proj/secret/key"]:
            with self.subTest(file_path=file_path):
                verdict = _resolve_event("Read", {"file_path": file_path}, cfg, True)
                self.assertEqual(
                    verdict.decision, decide(cfg, "Read", file_path).verdict
                )


class TestResolveEventEdgeCases(unittest.TestCase):
    """Fail-closed and not-governed branches of _resolve_event."""

    def test_non_governed_tool_is_allowed(self):
        """
        Given a config that governs Bash only
        When a non-governed tool is resolved
        Then it is allowed with a 'Not a governed tool' reason
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        verdict = _resolve_event("WebFetch", {"command": "x"}, cfg, True)
        self.assertEqual(verdict.decision, "allow")
        self.assertIn("Not a governed tool", verdict.reason)
        self.assertIsNone(verdict.additional_context)

    def test_empty_command_fails_closed(self):
        """
        Given a governed Bash config
        When an empty command is resolved
        Then it is denied (fail-closed)
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        verdict = _resolve_event("Bash", {"command": ""}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No command provided", verdict.reason)
        self.assertIsNone(verdict.additional_context)

    def test_empty_file_path_fails_closed(self):
        """
        Given a governed Read config
        When an empty file_path is resolved
        Then it is denied (fail-closed)
        """
        cfg = _config(tool="Read", allow=["/proj/**"])
        verdict = _resolve_event("Read", {"file_path": ""}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No file_path provided", verdict.reason)
        self.assertIsNone(verdict.additional_context)


class TestEvalModeMain(unittest.TestCase):
    """Driving main() with --eval: correct verdict on stdout, and no side effects."""

    def _run_eval(self, hook_input, config):
        """Drive main() with --eval over mocked stdin/stdout; return parsed output
        plus the log_command and run_auto_migration mocks for side-effect asserts."""
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.hook.load_configuration", return_value=config),
            patch("toolguard.hook.log_command") as mock_log,
            patch("toolguard.hook.run_auto_migration") as mock_mig,
        ):
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
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        mock_log.assert_not_called()
        mock_mig.assert_not_called()

    def test_eval_surfaces_additional_context_for_enriched_allow_rule(self):
        """
        TOO-19 Phase 1: Given a structured allow rule carrying
            additionalContext = 'prefer --short', and --eval mode
        When main() probes the matching command
        Then the printed JSON's hookSpecificOutput carries that
            additionalContext -- --eval exists to preview what the live hook
            would do, so it must not silently omit a real output field
        """
        content = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [
                    {"match": "Bash(ls:*)", "additionalContext": "prefer --short"}
                ],
                "deny": [],
                "ask": [],
            },
        }
        cfg = Configuration(
            layers=(
                ConfigLayer(provenance=_prov(), content=MappingProxyType(content)),
            ),
            start_dir=None,
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        output, _mock_log, _mock_mig = self._run_eval(hook_input, cfg)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(
            output["hookSpecificOutput"]["additionalContext"], "prefer --short"
        )

    def test_eval_asks_on_unmatched_command_by_default(self):
        """
        Given a config with rules configured (allows 'ls:*') but no explicit
            no_match_fallback, and --eval mode
        When main() probes 'rm -rf /' (matches no rule)
        Then it prints an 'ask' verdict (TOO-15: the new default
            no_match_fallback) -- per the security-audit skill's floor
            classification, 'ask' on a catastrophic command IS a breach signal,
            just not the literal string 'deny'
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
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_eval_denies_floor_command_with_explicit_deny_fallback(self):
        """
        Given a config that allows 'ls:*' and explicitly sets
            no_match_fallback='deny', and --eval mode
        When main() probes 'rm -rf /' (matches no rule)
        Then it prints a deny verdict (the safety-floor probe's breach signal)
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        cfg = _config(allow=["ls:*"])
        # Layer content is a MappingProxyType; rebuild with the fallback added.
        content = dict(cfg.layers[0].content)
        content["no_match_fallback"] = "deny"
        cfg = Configuration(
            layers=(
                ConfigLayer(
                    provenance=cfg.layers[0].provenance,
                    content=MappingProxyType(content),
                ),
            ),
            start_dir=None,
        )
        output, _mock_log, _mock_mig = self._run_eval(hook_input, cfg)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_eval_malformed_stdin_fails_safe(self):
        """
        Given --eval mode and non-JSON stdin
        When main() runs
        Then it emits a deny decision (fail-safe) and never logs or auto-migrates
        """
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO("not json at all")),
            patch("sys.stdout", new_callable=StringIO),
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
            patch("toolguard.hook.log_command") as mock_log,
            patch("toolguard.hook.run_auto_migration") as mock_mig,
        ):
            try:
                main()
            except SystemExit:
                pass
            result = json.loads(mock_stderr.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        mock_log.assert_not_called()
        mock_mig.assert_not_called()

    def test_eval_reflects_parse_failure_ask_floor(self):
        """
        TOO-19: Given a Configuration with a normally-allowed command AND a
            recorded parse_failures entry (a governed config file failed to
            parse), and --eval mode
        When main() probes that command
        Then --eval prints 'ask', not 'allow' -- the ASK floor applies inside
            permission_resolution.resolve_permission_detailed, the single
            chokepoint both the live hook and --eval delegate to, so the
            cross-project
            security-audit skill never reports a safety floor the live hook
            does not actually have
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        cfg = _config(allow=["ls:*"])
        broken = Path("/fake/.claude/toolguard_hook.local.toml")
        cfg = Configuration(
            layers=cfg.layers,
            start_dir=cfg.start_dir,
            parse_failures=((broken, "bad TOML"),),
        )
        output, _mock_log, _mock_mig = self._run_eval(hook_input, cfg)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn(
            str(broken), output["hookSpecificOutput"]["permissionDecisionReason"]
        )


class TestEvalMatchesLiveHookUnderFallback(unittest.TestCase):
    """
    TOO-15: for every no_match_fallback value (including the default and the
    deprecated 'warn_deny' alias), the read-only --eval probe and the live
    hook (main() without --eval) must agree on an unmatched command's
    verdict. This guards the bug where --eval used to omit the
    no_match_fallback resolution and show a raw/deny verdict where the live
    hook actually allowed under 'allow_with_warning' (formerly 'warn_deny').
    """

    @staticmethod
    def _config_with_fallback(fallback_value):
        """Build a single-layer Configuration allowing only 'ls:*' for Bash,
        with the given no_match_fallback value (or no key at all if None)."""
        content = {
            "governed_tools": ["Bash"],
            "permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []},
        }
        if fallback_value is not None:
            content["no_match_fallback"] = fallback_value
        return Configuration(
            layers=(
                ConfigLayer(provenance=_prov(), content=MappingProxyType(content)),
            ),
            start_dir=None,
        )

    @staticmethod
    def _run_live(hook_input, config):
        """Drive main() WITHOUT --eval (the live hook path); return parsed stdout."""
        with (
            patch("sys.argv", ["toolguard"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.hook.load_configuration", return_value=config),
            patch("toolguard.hook.log_command"),
            patch(
                "toolguard.hook.identify_current_agent",
                return_value={"agent_type": "main"},
            ),
        ):
            try:
                main()
            except SystemExit:
                pass
            return json.loads(mock_stdout.getvalue())

    @staticmethod
    def _run_eval(hook_input, config):
        """Drive main() WITH --eval (the read-only probe path); return parsed stdout."""
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.hook.load_configuration", return_value=config),
        ):
            try:
                main()
            except SystemExit:
                pass
            return json.loads(mock_stdout.getvalue())

    def test_eval_matches_live_hook_for_every_fallback_value(self):
        """
        Given a config allowing only 'ls:*' for Bash, for each of the
            no_match_fallback values None (default), 'ask', 'deny',
            'allow_with_warning', and the deprecated 'warn_deny' alias
        When an unmatched command ('whoami') is resolved via --eval and via
            the live hook (main() without --eval)
        Then both report the identical permissionDecision -- no drift
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        for fallback_value in (None, "ask", "deny", "allow_with_warning", "warn_deny"):
            with self.subTest(fallback=fallback_value):
                config = self._config_with_fallback(fallback_value)
                eval_output = self._run_eval(hook_input, config)
                live_output = self._run_live(hook_input, config)
                self.assertEqual(
                    eval_output["hookSpecificOutput"]["permissionDecision"],
                    live_output["hookSpecificOutput"]["permissionDecision"],
                    f"--eval and live hook diverged for no_match_fallback="
                    f"{fallback_value!r}",
                )


if __name__ == "__main__":
    unittest.main()
