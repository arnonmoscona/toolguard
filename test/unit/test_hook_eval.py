"""
Unit tests for the read-only ``toolguard --eval`` evaluation mode.

``--eval`` lets the cross-project security-audit skill probe a project's safety
floor -- evaluating a synthetic command against the project's config and reading
the verdict -- WITHOUT the live hook's side effects (logging, divergence checks,
auto-migration).

Verdict assertions here carry ``matched_rule`` (or, at the JSON boundary where
that field is not projected, the rule text inside ``permissionDecisionReason``).
Both ``deny`` and ``ask`` are also reachable as fail-closed safety nets -- empty
extraction denies, an undecidable segment floors to ask -- so the decision alone
cannot tell a real rule match from a parse loss.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_divergence import DivergenceCheckResult
from toolguard.hook import _resolve_event, _run_divergence_check, main
from toolguard.tool_spec import ToolKind, ToolSpec

from test.unit._config_isolation import ConfigIsolationMixin, isolate_log_dir_for_module

# This module also drives main() WITHOUT --eval, which resolves TOOLGUARD_LOG_DIR
# before load_configuration() is consulted -- see .claude/rules/test-config-isolation.md.
_log_tmp_dir = None
_log_patcher = None


def setUpModule():
    """Redirect TOOLGUARD_LOG_DIR to an isolated temp dir for this whole module."""
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


def _config_from(content):
    """Wrap a raw config dict as a single-layer Configuration."""
    return Configuration(
        layers=(ConfigLayer(provenance=_prov(), content=MappingProxyType(content)),),
        start_dir=None,
    )


def _config(tool="Bash", allow=(), deny=(), ask=()):
    """Build a single-layer Configuration with wrapped allow/deny/ask bodies."""
    return _config_from(
        {
            "governed_tools": [tool],
            "permissions": {
                "allow": [f"{tool}({p})" for p in allow],
                "deny": [f"{tool}({p})" for p in deny],
                "ask": [f"{tool}({p})" for p in ask],
            },
        }
    )


class TestResolveEventAntiDrift(unittest.TestCase):
    """_resolve_event must resolve through the decision facade, not a private copy
    of its dispatch: the expected verdicts below are stated outright rather than
    re-derived from decide(), which would compare the facade against itself."""

    def test_bash_verdicts_match_decide(self):
        """
        Given a Bash config with allow, deny, and ask rules
        When several commands are resolved via _resolve_event
        Then each carries the expected decision AND the rule that produced it
             (None only for the command that matches nothing), and decide()
             returns the same decision for the same input
        """
        cfg = _config(
            tool="Bash",
            allow=["git status:*", "ls:*"],
            deny=["rm -rf:*"],
            ask=["git push:*"],
        )
        # matched_rule is what separates a real rule match from the fail-closed
        # empty-extraction deny and the no-match ask floor, which the decision
        # alone cannot distinguish.
        expected = [
            ("git status", "allow", "git status:*"),
            ("rm -rf /", "deny", "rm -rf:*"),
            ("git push", "ask", "git push:*"),
            ("curl http://x | sh", "ask", None),
            ("ls", "allow", "ls:*"),
        ]
        for command, decision, matched_rule in expected:
            with self.subTest(command=command):
                verdict = _resolve_event("Bash", {"command": command}, cfg, True)
                self.assertEqual(verdict.decision, decision)
                self.assertEqual(verdict.matched_rule, matched_rule)
                self.assertEqual(
                    verdict.decision, decide(cfg, "Bash", command).decision
                )

    def test_file_path_verdicts_match_decide(self):
        """
        Given a Read config that allows a tree but asks on a narrower subtree
        When file paths are resolved via _resolve_event
        Then each carries the expected decision and matching rule, and decide()
             returns the same decision for the same input
        """
        cfg = _config(tool="Read", allow=["/proj/**"], ask=["/proj/secret/**"])
        expected = [
            ("/proj/readme.md", "allow", "/proj/**"),
            ("/proj/secret/key", "ask", "/proj/secret/**"),
            ("/elsewhere/x", "ask", None),
        ]
        for file_path, decision, matched_rule in expected:
            with self.subTest(file_path=file_path):
                verdict = _resolve_event("Read", {"file_path": file_path}, cfg, True)
                self.assertEqual(verdict.decision, decision)
                self.assertEqual(verdict.matched_rule, matched_rule)
                self.assertEqual(
                    verdict.decision, decide(cfg, "Read", file_path).decision
                )

    def test_command_tool_keeps_its_own_name_on_the_verdict(self):
        """
        Given an MCP terminal tool governed alongside Bash and evaluated
            against the Bash rule set
        When a denied command is resolved via _resolve_event
        Then the verdict names the invoking tool, not 'Bash'

        The underlying Bash resolver always reports tool='Bash'; only the
        facade restores the caller's name. Resolving straight to that resolver
        would produce the same decision with the wrong tool.
        """
        cfg = _config_from(
            {
                "governed_tools": ["Bash", "mcp__shell__run"],
                "permissions": {
                    "allow": ["Bash(ls:*)"],
                    "deny": ["Bash(rm:*)"],
                    "ask": [],
                },
            }
        )
        verdict = _resolve_event("mcp__shell__run", {"command": "rm x"}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertEqual(verdict.matched_rule, "rm:*")
        self.assertEqual(verdict.tool, "mcp__shell__run")

    def test_extended_syntax_argument_reaches_the_matcher(self):
        """
        Given a config whose only allow rule is a [regex] pattern
        When the same command is resolved with extended_syntax True and False
        Then True matches the regex rule and False does not (falling through
             to the no-match ask floor with no matched rule)
        """
        cfg = _config_from(
            {
                "governed_tools": ["Bash"],
                "permissions": {
                    "allow": [r"Bash([regex]^echo\s+ok$)"],
                    "deny": [],
                    "ask": [],
                },
            }
        )
        enabled = _resolve_event("Bash", {"command": "echo ok"}, cfg, True)
        self.assertEqual(enabled.decision, "allow")
        self.assertEqual(enabled.matched_rule, r"[regex]^echo\s+ok$")

        disabled = _resolve_event("Bash", {"command": "echo ok"}, cfg, False)
        self.assertEqual(disabled.decision, "ask")
        self.assertIsNone(disabled.matched_rule)


class TestResolveEventEdgeCases(unittest.TestCase):
    """Fail-closed and not-governed branches of _resolve_event."""

    def test_non_governed_tool_is_allowed(self):
        """
        Given a config that governs Bash only
        When a non-governed tool is resolved
        Then it is allowed with a 'Not a governed tool' reason, matching no rule
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        verdict = _resolve_event("WebFetch", {"command": "x"}, cfg, True)
        self.assertEqual(verdict.decision, "allow")
        self.assertIn("Not a governed tool", verdict.reason)
        self.assertIsNone(verdict.matched_rule)
        self.assertIsNone(verdict.additional_context)

    def test_empty_command_fails_closed(self):
        """
        Given a governed Bash config
        When an empty command is resolved
        Then it is denied by the guard (fail-closed), matching no rule
        """
        cfg = _config(tool="Bash", allow=["ls:*"])
        verdict = _resolve_event("Bash", {"command": ""}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No command provided", verdict.reason)
        self.assertIsNone(verdict.matched_rule)
        self.assertIsNone(verdict.additional_context)

    def test_empty_file_path_fails_closed(self):
        """
        Given a governed Read config
        When an empty file_path is resolved
        Then it is denied by the guard (fail-closed), matching no rule
        """
        cfg = _config(tool="Read", allow=["/proj/**"])
        verdict = _resolve_event("Read", {"file_path": ""}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No file_path provided", verdict.reason)
        self.assertIsNone(verdict.matched_rule)
        self.assertIsNone(verdict.additional_context)


class TestResolveEventPayloadKeySeam(unittest.TestCase):
    """_resolve_event must read the payload key from the tool_spec registry, not
    a hardcoded 'file_path' literal -- pinned by a fake registry entry for 'Read'."""

    @patch.dict(
        "toolguard.tool_spec.TOOLS_BY_NAME",
        {
            "Read": ToolSpec(
                name="Read",
                kind=ToolKind.FILE,
                payload_key="target_path",
                is_builtin=True,
            )
        },
    )
    def test_target_is_read_from_the_registered_key(self):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When a tool_input carrying only 'target_path' is resolved
        Then the target is found and matched against the allow rule (not
             treated as empty/fail-closed)
        """
        cfg = _config(tool="Read", allow=["/proj/**"])
        verdict = _resolve_event("Read", {"target_path": "/proj/readme.md"}, cfg, True)
        self.assertEqual(verdict.decision, "allow")
        self.assertEqual(verdict.matched_rule, "/proj/**")

    @patch.dict(
        "toolguard.tool_spec.TOOLS_BY_NAME",
        {
            "Read": ToolSpec(
                name="Read",
                kind=ToolKind.FILE,
                payload_key="target_path",
                is_builtin=True,
            )
        },
    )
    def test_empty_target_deny_reason_names_the_registered_key(self):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When the tool_input lacks 'target_path'
        Then the fail-closed deny reason names 'target_path', not 'file_path'
        """
        cfg = _config(tool="Read", allow=["/proj/**"])
        verdict = _resolve_event("Read", {}, cfg, True)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No target_path provided", verdict.reason)
        self.assertIsNone(verdict.matched_rule)


class TestEvalModeMain(unittest.TestCase):
    """Driving main() with --eval: correct verdict on stdout, and no side effects."""

    def _run_eval(self, hook_input, config):
        """Drive main() with --eval over mocked stdin/stdout; return parsed output
        plus the log_command and run_auto_migration mocks for side-effect asserts.

        Asserts stderr stayed empty: --eval's caller reads stdout only, and the
        live hook's own announcements (takeover, divergence, config warnings)
        all land on stderr, so a stray byte there is the visible symptom of the
        read-only path having run something it should not.
        """
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
            patch("toolguard.hook.load_configuration", return_value=config),
            patch("toolguard.hook.log_command") as mock_log,
            patch("toolguard.hook.run_auto_migration") as mock_mig,
        ):
            try:
                main()
            except SystemExit:
                pass
            output = json.loads(mock_stdout.getvalue())
            self.assertEqual(mock_stderr.getvalue(), "")
        return output, mock_log, mock_mig

    def test_eval_allows_and_is_read_only(self):
        """
        Given an allowed command and --eval mode
        When main() runs
        Then it prints an allow verdict naming the rule that allowed it, and
             never logs or auto-migrates
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        output, mock_log, mock_mig = self._run_eval(hook_input, _config(allow=["ls:*"]))
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertIn("ls:*", output["hookSpecificOutput"]["permissionDecisionReason"])
        mock_log.assert_not_called()
        mock_mig.assert_not_called()

    def test_eval_surfaces_additional_context_for_enriched_allow_rule(self):
        """
        Given a structured allow rule carrying
            additionalContext = 'prefer --short', and --eval mode
        When main() probes the matching command
        Then the printed JSON's hookSpecificOutput carries that
            additionalContext
        """
        cfg = _config_from(
            {
                "governed_tools": ["Bash"],
                "permissions": {
                    "allow": [
                        {"match": "Bash(ls:*)", "additionalContext": "prefer --short"}
                    ],
                    "deny": [],
                    "ask": [],
                },
            }
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
        Then it prints an 'ask' verdict (the default no_match_fallback), whose
             reason is the no-match one rather than any rule's
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
        self.assertIn(
            "does not match any allow patterns",
            output["hookSpecificOutput"]["permissionDecisionReason"],
        )

    def test_eval_denies_floor_command_with_explicit_deny_fallback(self):
        """
        Given a config that allows 'ls:*' and explicitly sets
            no_match_fallback='deny', and --eval mode
        When main() probes 'rm -rf /' (matches no rule)
        Then it prints a deny verdict whose reason is the no-match fallback,
             not the fail-closed 'no valid commands' one
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        cfg = _config(allow=["ls:*"])
        content = dict(cfg.layers[0].content)
        content["no_match_fallback"] = "deny"
        cfg = _config_from(content)
        output, _mock_log, _mock_mig = self._run_eval(hook_input, cfg)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        reason = output["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("does not match any allow patterns", reason)
        self.assertNotIn("No valid commands found", reason)

    def test_eval_malformed_stdin_fails_safe(self):
        """
        Given --eval mode and non-JSON stdin
        When main() runs
        Then it emits a deny decision (fail-safe) on STDOUT, empty stderr,
             and never logs or auto-migrates
        """
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO("not json at all")),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
            patch("toolguard.hook.log_command") as mock_log,
            patch("toolguard.hook.run_auto_migration") as mock_mig,
        ):
            try:
                main()
            except SystemExit:
                pass
            result = json.loads(mock_stdout.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "Failed to parse hook input",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertEqual(mock_stderr.getvalue(), "")
        mock_log.assert_not_called()
        mock_mig.assert_not_called()

    def test_eval_empty_stdin_still_puts_a_deny_on_stdout(self):
        """
        Given --eval mode and an EMPTY stdin
        When main() runs
        Then a deny decision still reaches STDOUT, naming the invalid input

        The non---eval path treats empty stdin as a stray manual invocation and
        prints prose with no decision at all; under --eval the caller parses
        stdout, so that shape would be read as no answer rather than as a deny.
        """
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO("")),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
        ):
            try:
                main()
            except SystemExit:
                pass
            result = json.loads(mock_stdout.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "Invalid hook input",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertEqual(mock_stderr.getvalue(), "")

    def test_eval_non_dict_tool_input_still_puts_a_deny_on_stdout(self):
        """
        Given --eval mode and an event whose 'tool_input' is a string rather
            than an object (present, so field validation passes; unusable, so
            resolution raises)
        When main() runs
        Then the catch-all still emits a deny decision on STDOUT rather than
             letting the exception escape with nothing printed
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": "not a dict",
            "hook_event_name": "PreToolUse",
        }
        with (
            patch("sys.argv", ["toolguard", "--eval"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
            patch(
                "toolguard.hook.load_configuration",
                return_value=_config(allow=["ls:*"]),
            ),
        ):
            try:
                main()
            except SystemExit:
                pass
            result = json.loads(mock_stdout.getvalue())
        self.assertEqual(result["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "Unexpected error in hook",
            result["hookSpecificOutput"]["permissionDecisionReason"],
        )
        self.assertEqual(mock_stderr.getvalue(), "")

    def test_eval_reflects_parse_failure_ask_floor(self):
        """
        Given a Configuration with a normally-allowed command AND a
            recorded parse_failures entry (a governed config file failed to
            parse), and --eval mode
        When main() probes that command
        Then --eval prints 'ask', not 'allow', naming the unparseable file
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

    def test_eval_honours_the_projects_extended_syntax_setting(self):
        """
        Given a config whose only allow rule is a [regex] pattern, and a probed
            project whose env config turns extended syntax OFF
        When main() probes the command that regex would match
        Then --eval reports the ask floor, and reports allow for the same
             config when the project leaves extended syntax ON
        """
        cfg = _config_from(
            {
                "governed_tools": ["Bash"],
                "permissions": {
                    "allow": [r"Bash([regex]^echo\s+ok$)"],
                    "deny": [],
                    "ask": [],
                },
            }
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "echo ok"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        for extended_syntax, expected in ((True, "allow"), (False, "ask")):
            with self.subTest(extended_syntax=extended_syntax):
                with patch(
                    "toolguard.hook.get_env_config",
                    return_value={"extended_syntax": extended_syntax},
                ):
                    output, _log, _mig = self._run_eval(hook_input, cfg)
                self.assertEqual(
                    output["hookSpecificOutput"]["permissionDecision"], expected
                )


class TestEvalIgnoresStaleSettingsPathOverride(ConfigIsolationMixin, unittest.TestCase):
    """--eval anchors on the PROBED project, not on CLAUDE_SETTINGS_PATH -- the
    property that keeps a cross-project sweep faithful to each project."""

    def test_eval_reads_the_probed_project_not_the_env_override(self):
        """
        Given a project whose toolguard config allows 'ls:*', and a
            CLAUDE_SETTINGS_PATH pointing at an unrelated settings file that
            denies it
        When main() probes 'ls' under --eval with that project as cwd
        Then the verdict is the project's allow -- the override is ignored
        """
        home, project = self.isolate_config_environment()
        foreign = home / "foreign"
        foreign.mkdir()
        (foreign / "settings.json").write_text(
            json.dumps(
                {"permissions": {"allow": [], "deny": ["Bash(ls:*)"], "ask": []}}
            )
        )
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            'governed_tools = ["Bash"]\n[permissions]\nallow = ["Bash(ls:*)"]\n'
        )

        with patch.dict(
            "os.environ", {"CLAUDE_SETTINGS_PATH": str(foreign / "settings.json")}
        ):
            hook_input = {
                "tool_name": "Bash",
                "tool_input": {"command": "ls"},
                "cwd": str(project),
                "hook_event_name": "PreToolUse",
            }
            with (
                patch("sys.argv", ["toolguard", "--eval"]),
                patch("sys.stdin", StringIO(json.dumps(hook_input))),
                patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            ):
                try:
                    main()
                except SystemExit:
                    pass
                output = json.loads(mock_stdout.getvalue())

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertIn("ls:*", output["hookSpecificOutput"]["permissionDecisionReason"])


class TestEvalMatchesLiveHook(unittest.TestCase):
    """The read-only --eval probe and the live hook (main() without --eval) must
    produce the identical hookSpecificOutput for the same event and config."""

    #: Governs Bash and Read, with one rule of each kind for both.
    BASE_CONTENT = {
        "governed_tools": ["Bash", "Read"],
        "permissions": {
            "allow": ["Bash(ls:*)", "Read(/proj/**)"],
            "deny": ["Bash(rm -rf:*)"],
            "ask": ["Bash(git push:*)", "Read(/proj/secret/**)"],
        },
    }

    @classmethod
    def _content_with_fallback(cls, fallback_value):
        """BASE_CONTENT, plus a no_match_fallback value (or no key at all if None)."""
        content = dict(cls.BASE_CONTENT)
        if fallback_value is not None:
            content["no_match_fallback"] = fallback_value
        return content

    @staticmethod
    def _run_live(hook_input, config):
        """Drive main() WITHOUT --eval (the live hook path); return
        hookSpecificOutput.

        check_and_warn_divergence is stubbed out: unstubbed it runs against the
        real project the test process happens to sit in, reading that project's
        settings and warning about it.
        """
        with (
            patch("sys.argv", ["toolguard"]),
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.hook.load_configuration", return_value=config),
            patch("toolguard.hook.log_command"),
            patch(
                "toolguard.hook.check_and_warn_divergence",
                return_value=DivergenceCheckResult(divergent_patterns=[]),
            ),
            patch(
                "toolguard.hook.identify_current_agent",
                return_value={"agent_type": "main"},
            ),
        ):
            try:
                main()
            except SystemExit:
                pass
            return json.loads(mock_stdout.getvalue())["hookSpecificOutput"]

    @staticmethod
    def _run_eval(hook_input, config):
        """Drive main() WITH --eval (the read-only probe path); return
        hookSpecificOutput."""
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
            return json.loads(mock_stdout.getvalue())["hookSpecificOutput"]

    def _assert_agree(self, tool_name, tool_input, content, expected_decision):
        """Assert --eval and the live hook produce the identical
        hookSpecificOutput, and that it carries *expected_decision*."""
        hook_input = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        config = _config_from(content)
        eval_output = self._run_eval(hook_input, config)
        live_output = self._run_live(hook_input, config)
        self.assertEqual(eval_output["permissionDecision"], expected_decision)
        self.assertEqual(
            eval_output,
            live_output,
            f"--eval and the live hook diverged for {tool_name} {tool_input}",
        )

    def test_agreement_across_rule_kinds_and_tool_kinds(self):
        """
        Given a config governing Bash and Read with an allow, a deny and an ask
            rule for each
        When a matching command, an unmatched command, an empty target, an
            ungoverned tool and both file-path rule kinds are resolved via
            --eval and via the live hook
        Then both paths report the identical hookSpecificOutput in every case
        """
        cases = [
            ("Bash", {"command": "ls"}, "allow"),
            ("Bash", {"command": "rm -rf /"}, "deny"),
            ("Bash", {"command": "git push"}, "ask"),
            ("Bash", {"command": "whoami"}, "ask"),
            ("Bash", {"command": ""}, "deny"),
            ("WebFetch", {"command": "x"}, "allow"),
            ("Read", {"file_path": "/proj/readme.md"}, "allow"),
            ("Read", {"file_path": "/proj/secret/key"}, "ask"),
            ("Read", {"file_path": ""}, "deny"),
        ]
        for tool_name, tool_input, expected in cases:
            with self.subTest(tool=tool_name, tool_input=tool_input):
                self._assert_agree(tool_name, tool_input, self.BASE_CONTENT, expected)

    def test_agreement_for_every_fallback_value(self):
        """
        Given the same config, for each of the no_match_fallback values None
            (default), 'ask', 'deny', 'allow_with_warning', and the deprecated
            'warn_deny' alias
        When an unmatched command ('whoami') is resolved via --eval and via
            the live hook
        Then both report the identical hookSpecificOutput -- no drift
        """
        expected_by_fallback = {
            None: "ask",
            "ask": "ask",
            "deny": "deny",
            "allow_with_warning": "allow",
            "warn_deny": "allow",
        }
        for fallback_value, expected in expected_by_fallback.items():
            with self.subTest(fallback=fallback_value):
                self._assert_agree(
                    "Bash",
                    {"command": "whoami"},
                    self._content_with_fallback(fallback_value),
                    expected,
                )

    def test_agreement_on_the_parse_failure_ask_floor(self):
        """
        Given a config whose rules allow 'ls' but which recorded a parse
            failure for a governed config file
        When 'ls' is resolved via --eval and via the live hook
        Then both clamp to ask and report the identical hookSpecificOutput
        """
        broken = Path("/fake/.claude/toolguard_hook.local.toml")
        base = _config_from(self.BASE_CONTENT)
        config = Configuration(
            layers=base.layers,
            start_dir=base.start_dir,
            parse_failures=((broken, "bad TOML"),),
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
            "cwd": None,
            "hook_event_name": "PreToolUse",
        }
        eval_output = self._run_eval(hook_input, config)
        live_output = self._run_live(hook_input, config)
        self.assertEqual(eval_output["permissionDecision"], "ask")
        self.assertIn(str(broken), eval_output["permissionDecisionReason"])
        self.assertEqual(eval_output, live_output)


class TestAutoMigrationGate(ConfigIsolationMixin, unittest.TestCase):
    """The live hook auto-migrates a user's config only when config_sync.auto_migrate
    says so -- the one place toolguard writes permission config unasked."""

    def _run_gate(self, auto_migrate, divergent_patterns):
        """Drive _run_divergence_check with the given config_sync setting and
        divergence outcome; return the run_auto_migration mock."""
        home, project = self.isolate_config_environment()
        content = {
            "governed_tools": ["Bash"],
            "permissions": {"allow": ["Bash(ls:*)"], "deny": [], "ask": []},
            "config_sync": {"auto_migrate": auto_migrate},
        }
        config = Configuration(
            layers=(
                ConfigLayer(provenance=_prov(), content=MappingProxyType(content)),
            ),
            start_dir=project,
        )
        env_config = {"log_dir": self.isolated_log_dir, "project_root": str(project)}
        takeover_dict = {
            "enabled": False,
            "ignored_allow_patterns": [],
            "additional_ignored_patterns": [],
            "no_match_fallback": None,
        }
        with (
            patch(
                "toolguard.hook.check_and_warn_divergence",
                return_value=DivergenceCheckResult(
                    divergent_patterns=list(divergent_patterns)
                ),
            ),
            patch("toolguard.hook.run_auto_migration") as mock_mig,
        ):
            _run_divergence_check(config, env_config, takeover_dict)
        return mock_mig, project

    def test_divergence_without_auto_migrate_does_not_migrate(self):
        """
        Given a project with divergent patterns and config_sync.auto_migrate
            left at its default of False
        When the live hook's divergence check runs
        Then auto-migration is NOT invoked -- toolguard does not rewrite a
             config the user never asked it to
        """
        mock_mig, _project = self._run_gate(False, ["Bash(git push:*)"])
        mock_mig.assert_not_called()

    def test_divergence_with_auto_migrate_migrates_that_project(self):
        """
        Given a project with divergent patterns and config_sync.auto_migrate
            set to True
        When the live hook's divergence check runs
        Then auto-migration is invoked for that project root
        """
        mock_mig, project = self._run_gate(True, ["Bash(git push:*)"])
        mock_mig.assert_called_once()
        self.assertEqual(mock_mig.call_args.args[0], project)

    def test_no_divergence_does_not_migrate_even_when_enabled(self):
        """
        Given a project with config_sync.auto_migrate set to True but no
            divergent patterns
        When the live hook's divergence check runs
        Then auto-migration is not invoked
        """
        mock_mig, _project = self._run_gate(True, [])
        mock_mig.assert_not_called()


if __name__ == "__main__":
    unittest.main()
