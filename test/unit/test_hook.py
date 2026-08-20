"""Unit tests for toolguard.hook: the PreToolUse entry point for Bash and file-path tools."""

import json
import os
import unittest
from contextlib import ExitStack
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
    TakeoverEnabledConflict,
)
from toolguard.compound import FALLBACK_ALLOW_PLACEHOLDER, FALLBACK_DENY_PLACEHOLDER
from toolguard.config_types import RuntimeVerdict
from toolguard.hook import (
    FILE_PATH_TOOLS,
    _emit_decision,
    _handle_command_tool,
    _handle_file_path_tool,
    _log_allowed_command,
    create_hook_output,
    load_file_path_patterns,
    main,
    parse_hook_input,
)
from toolguard.error_log import log_crash
from toolguard.log_writer import LogRecord
from toolguard.file_matching import decide_file_path_at_level_detailed
from toolguard.resolve import resolve_bash_permission_detailed
from toolguard.tool_spec import ToolKind, ToolSpec
from toolguard import ambient, once_per_store

from test.unit._config_isolation import isolate_log_dir_for_module

_NO_TAKEOVER = TakeoverConfig(False, (), (), "deny")

# Most classes here mock toolguard.hook.load_configuration() directly and
# drive toolguard.hook.main() end-to-end (a few call hook functions
# directly and never reach main()). main() calls
# toolguard.env_config.get_env_config() unconditionally, before
# load_configuration() runs, to resolve TOOLGUARD_LOG_DIR for the
# config-discovery diagnostic log -- unpatched, that resolves the real
# process cwd (the repo root under `unittest discover`) and writes into
# the developer's live logs/ directory. See
# test/unit/_config_isolation.py's module docstring and
# .claude/rules/test-config-isolation.md.
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


def check_file_path_permission(
    file_path, allow_patterns, deny_patterns, extended_syntax=True
):
    """Evaluate a file path against flat allow/deny pattern lists, returning (decision, reason)."""
    config = Configuration(layers=())
    result = decide_file_path_at_level_detailed(
        file_path, allow_patterns, deny_patterns, config, extended_syntax
    )
    if result is None:
        return "deny", "Path does not match any allow patterns"
    return result.decision, result.reason


def _fake_config(
    governed=("Bash",),
    bash=((), ()),
    file_patterns=None,
    takeover=_NO_TAKEOVER,
):
    """Build a stand-in Configuration for hook tests, patched in via load_configuration."""
    file_patterns = file_patterns or {}

    def _patterns_for(tool_name):
        if tool_name == "Bash":
            return bash
        return file_patterns.get(tool_name, ((), ()))

    class _FakeConfig:
        project_root = None

        def governed_tools(self_inner):
            return tuple(governed)

        def bash_permissions(self_inner):
            return bash

        def allow_deny_for(self_inner, tool_name):
            return _patterns_for(tool_name)

        def hard_deny(self_inner, tool_name):
            return (), ()

        def resolve_config_path(self_inner, raw_path):
            return raw_path

        def permission_levels_with_provenance(self_inner, tool_name):
            # toolguard.permission_resolution reads this directly. The fake
            # models one hierarchy level with no provenance layers, so
            # provenance lookups against it resolve to None.
            allow, deny = _patterns_for(tool_name)
            if not (allow or deny):
                return ()
            return ((tuple(allow), tuple(deny), (), ()),)

        def has_any_rules(self_inner, tool_name):
            allow, deny = _patterns_for(tool_name)
            return bool(allow or deny)

        def resolved_no_match_fallback(self_inner):
            return "ask"

        parse_failures = ()

        def describe_levels(self_inner):
            return ()

        def resolved_undecidable_fallback(self_inner):
            return "ask"

        def takeover_mode(self_inner):
            return takeover

        def config_sync_settings(self_inner):
            return MappingProxyType(
                {
                    "auto_migrate": False,
                    "backup_dir": "logs/config-backups",
                    "auto_sort_on_migrate": True,
                }
            )

        def validation_issues(self_inner):
            return ()

    return _FakeConfig()


class TestHookToolGovernance(unittest.TestCase):
    """Test that hook correctly governs different tools."""

    def test_bash_tool_is_governed(self):
        """
        Given Bash is governed and 'git *' is an allow pattern
        When main() processes a 'git status' Bash invocation
        Then the hook output decision is 'allow'
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Bash"], bash=(["git *"], []))
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        try:
                            main()
                        except SystemExit:
                            pass

                        output = json.loads(mock_stdout.getvalue())
                        self.assertEqual(
                            output["hookSpecificOutput"]["permissionDecision"], "allow"
                        )

    def test_jetbrains_terminal_is_governed(self):
        """
        Given the JetBrains terminal tool is in the governed list and 'git *' is allowed
        When main() processes a 'git status' invocation of that tool
        Then the hook output decision is 'allow'
        """
        hook_input = {
            "tool_name": "mcp__jetbrains__execute_terminal_command",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(
            governed=["Bash", "mcp__jetbrains__execute_terminal_command"],
            bash=(["git *"], []),
        )
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        try:
                            main()
                        except SystemExit:
                            pass

                        output = json.loads(mock_stdout.getvalue())
                        self.assertEqual(
                            output["hookSpecificOutput"]["permissionDecision"], "allow"
                        )

    def test_ungoverned_tool_is_allowed(self):
        """
        Given only Bash is governed
        When main() processes an invocation of an ungoverned tool
        Then the decision is 'allow' and the reason states it is not a governed tool
        """
        hook_input = {
            "tool_name": "SomeOtherTool",
            "tool_input": {"command": "dangerous command"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Bash"])
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    try:
                        main()
                    except SystemExit:
                        pass

                    output = json.loads(mock_stdout.getvalue())
                    self.assertEqual(
                        output["hookSpecificOutput"]["permissionDecision"], "allow"
                    )
                    self.assertIn(
                        "Not a governed tool",
                        output["hookSpecificOutput"]["permissionDecisionReason"],
                    )


class TestPermissionDecisionSurvivesSqlite3Unavailable(unittest.TestCase):
    """Smoke test: hook.main() must not crash or degrade the permission decision when sqlite3 (toolguard.once_per_store) is unavailable."""

    def test_takeover_enabled_decision_still_resolves_with_sqlite3_unavailable(self):
        """
        Given takeover mode enabled, 'git *' allowed, sqlite3 unavailable
        When main() processes a 'git status' Bash invocation
        Then the permission decision is still 'allow'

        Measured 2026-08-13: main() reaches nothing in once_per_store on this
        path, so this is a smoke test that the decision survives the patch,
        not evidence about throttling.
        """
        config = _fake_config(
            governed=["Bash"],
            bash=(["git *"], []),
            takeover=TakeoverConfig(True, (), (), "deny"),
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch(
                        "toolguard.hook.get_env_config",
                        return_value={"log_dir": Path("/fake/logs")},
                    ):
                        with patch("toolguard.hook.log_command"):
                            with patch.object(once_per_store, "sqlite3", None):
                                try:
                                    main()
                                except SystemExit:
                                    pass

        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")


class TestTakeoverEnabledConflictWiring(unittest.TestCase):
    """End-to-end hook wiring for a cross-level takeover_mode.enabled conflict."""

    def test_enabled_conflict_logs_and_warns_failsafe_off(self):
        """
        Given a config whose takeover_mode() reports an enabled conflict (fail-safe OFF)
        When main() processes a governed Bash command
        Then a conflict-log entry is written, a takeover warning is issued,
             and the command is still evaluated on the safe path (native prompts active)
        """
        conflict = TakeoverEnabledConflict(
            sources=(
                (
                    True,
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/.claude/toolguard_hook.toml"),
                        0,
                    ),
                ),
                (
                    False,
                    Provenance(
                        "user",
                        "toolguard_hook",
                        "toml",
                        Path("/u/.claude/toolguard_hook.toml"),
                        1,
                    ),
                ),
            )
        )
        takeover = TakeoverConfig(False, (), (), "deny", conflict=conflict)
        config = _fake_config(
            governed=["Bash"], bash=(["git *"], []), takeover=takeover
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch(
                        "toolguard.hook.get_env_config",
                        return_value={"log_dir": Path("/fake/logs")},
                    ):
                        with patch("toolguard.hook.log_command"):
                            with patch("toolguard.hook.log_conflict") as mock_conflict:
                                with patch(
                                    "toolguard.hook.issue_takeover_warning"
                                ) as mock_warn:
                                    try:
                                        main()
                                    except SystemExit:
                                        pass

        mock_conflict.assert_called_once()
        conflict_message = mock_conflict.call_args[0][0]
        self.assertIn("conflicting values", conflict_message)
        self.assertIn("DISABLED", conflict_message)
        mock_warn.assert_called_once()
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_log_takeover_conflict_is_noop_without_conflict_or_log_dir(self):
        """
        Given a None conflict or a missing log_dir
        When _log_takeover_enabled_conflict is called
        Then it writes nothing (no-op guard) and does not raise
        """
        from toolguard.hook import _log_takeover_enabled_conflict

        conflict = TakeoverEnabledConflict(
            sources=(
                (
                    True,
                    Provenance(
                        "project", "toolguard_hook", "toml", Path("/p/x.toml"), 0
                    ),
                ),
            )
        )
        with patch("toolguard.hook.log_conflict") as mock_conflict:
            _log_takeover_enabled_conflict(None, Path("/fake/logs"))
            _log_takeover_enabled_conflict(conflict, None)
        mock_conflict.assert_not_called()


class TestHookInputParsing(unittest.TestCase):
    """Test hook input parsing."""

    def test_parse_valid_input(self):
        """
        Given valid hook JSON on stdin
        When parse_hook_input() reads it
        Then the parsed dict exposes the tool_name and tool_input command
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            result = parse_hook_input()
            self.assertEqual(result["tool_name"], "Bash")
            self.assertEqual(result["tool_input"]["command"], "git status")

    def test_parse_missing_required_field(self):
        """
        Given hook JSON on stdin missing the tool_input field
        When parse_hook_input() reads it
        Then a ValueError mentioning tool_input is raised
        """
        hook_input = {
            "tool_name": "Bash",
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with self.assertRaises(ValueError) as ctx:
                parse_hook_input()
            self.assertIn("tool_input", str(ctx.exception))

    def test_parse_empty_input(self):
        """
        Given empty stdin
        When parse_hook_input() reads it
        Then a ValueError mentioning 'Empty input' is raised
        """
        with patch("sys.stdin", StringIO("")):
            with self.assertRaises(ValueError) as ctx:
                parse_hook_input()
            self.assertIn("Empty input", str(ctx.exception))


class TestHookOutput(unittest.TestCase):
    """Test hook output formatting."""

    def test_create_allow_output(self):
        """
        Given an allow verdict
        When create_hook_output() builds the response
        Then the hookSpecificOutput carries decision 'allow' and the verdict's reason
        """
        output = create_hook_output(
            RuntimeVerdict(decision="allow", reason="Command matches allow pattern")
        )
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecisionReason"],
            "Command matches allow pattern",
        )

    def test_create_deny_output(self):
        """
        Given a deny verdict
        When create_hook_output() builds the response
        Then the hookSpecificOutput carries decision 'deny' and the verdict's reason
        """
        output = create_hook_output(
            RuntimeVerdict(decision="deny", reason="Command matches deny pattern")
        )
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecisionReason"],
            "Command matches deny pattern",
        )

    def test_no_additional_context_arg_omits_key_entirely(self):
        """
        Given a verdict built with NO additional_context argument (defaults to None)
        When the output dict is inspected
        Then hookSpecificOutput has no 'additionalContext' key at all (not a
            key set to None -- an absent key, so old consumers see no new shape)
        """
        output = create_hook_output(
            RuntimeVerdict(decision="allow", reason="Command matches allow pattern")
        )
        self.assertNotIn("additionalContext", output["hookSpecificOutput"])

    def test_none_additional_context_omits_key_entirely(self):
        """
        Given a verdict with additional_context=None
        When the output dict is inspected
        Then hookSpecificOutput has no 'additionalContext' key
        """
        output = create_hook_output(
            RuntimeVerdict(
                decision="allow",
                reason="Command matches allow pattern",
                additional_context=None,
            )
        )
        self.assertNotIn("additionalContext", output["hookSpecificOutput"])

    def test_empty_string_additional_context_omits_key_entirely(self):
        """
        Given a verdict with additional_context="" (empty string)
        When the output dict is inspected
        Then hookSpecificOutput has no 'additionalContext' key -- an empty
            string is treated the same as no enrichment, never injected
        """
        output = create_hook_output(
            RuntimeVerdict(
                decision="allow",
                reason="Command matches allow pattern",
                additional_context="",
            )
        )
        self.assertNotIn("additionalContext", output["hookSpecificOutput"])

    def test_non_empty_additional_context_is_included_inside_hook_specific_output(
        self,
    ):
        """
        Given a verdict with a non-empty additional_context
        When the output dict is inspected
        Then hookSpecificOutput carries 'additionalContext' with that exact text
        """
        output = create_hook_output(
            RuntimeVerdict(
                decision="allow",
                reason="Command matches allow pattern",
                additional_context="prefer git status --short",
            )
        )
        self.assertEqual(
            output["hookSpecificOutput"]["additionalContext"],
            "prefer git status --short",
        )


class TestFilePathTools(unittest.TestCase):
    """Test file path tool constants and identification."""

    def test_file_path_tools_constant(self):
        """
        Given the FILE_PATH_TOOLS constant
        When its membership and size are inspected
        Then it contains exactly Read, Write, and Edit
        """
        self.assertIn("Read", FILE_PATH_TOOLS)
        self.assertIn("Write", FILE_PATH_TOOLS)
        self.assertIn("Edit", FILE_PATH_TOOLS)
        self.assertEqual(len(FILE_PATH_TOOLS), 3)


class TestCheckFilePathPermission(unittest.TestCase):
    """Test file path permission checking with GLOB patterns."""

    def test_simple_glob_match(self):
        """
        Given an allow pattern '/tmp/*' and no deny patterns
        When check_file_path_permission evaluates '/tmp/test.txt'
        Then the decision is 'allow'
        """
        allow_patterns = ["/tmp/*"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/tmp/test.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_globstar_recursive_match(self):
        """
        Given an allow pattern '/tmp/**'
        When check_file_path_permission evaluates a deeply nested path under /tmp
        Then the decision is 'allow' because ** matches across separators
        """
        allow_patterns = ["/tmp/**"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/tmp/subdir/deep/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_single_star_does_not_match_nested(self):
        """
        Given an allow pattern '/tmp/*'
        When check_file_path_permission evaluates a nested path '/tmp/subdir/file.txt'
        Then the decision is 'deny' because a single * does not cross separators
        """
        allow_patterns = ["/tmp/*"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/tmp/subdir/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

    def test_deny_takes_precedence(self):
        """
        Given an allow pattern that matches and a deny pattern that also matches
        When check_file_path_permission evaluates the path
        Then the decision is 'deny' and cites the deny pattern -- the adapter
            also renders a no-match level as 'deny', so the pattern in the
            reason is what shows deny-first actually fired
        """
        allow_patterns = ["/tmp/**"]
        deny_patterns = ["/tmp/secret/**"]

        decision, reason = check_file_path_permission(
            "/tmp/secret/password.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("deny pattern: /tmp/secret/**", reason)

    def test_no_match_returns_deny(self):
        """
        Given an allow pattern '/home/**' that does not match the target path
        When decide_file_path_at_level_detailed evaluates '/tmp/file.txt'
        Then it reports no match at this level by returning None, which the
            check_file_path_permission adapter renders as 'deny'
        """
        allow_patterns = ["/home/**"]
        deny_patterns = []

        # The adapter synthesises both the 'deny' and its "does not match"
        # wording when the level returns None, so asserting on them alone
        # tests the adapter, not the matcher.
        self.assertIsNone(
            decide_file_path_at_level_detailed(
                "/tmp/file.txt",
                allow_patterns,
                deny_patterns,
                Configuration(layers=()),
                True,
            )
        )

        decision, _ = check_file_path_permission(
            "/tmp/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

    def test_tilde_expansion(self):
        """
        Given an allow pattern using '~/projects/**'
        When check_file_path_permission evaluates an absolute path under the expanded home
        Then the decision is 'allow' because the tilde is expanded before matching
        """
        import os

        home = os.path.expanduser("~")
        allow_patterns = ["~/projects/**"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            f"{home}/projects/test.py", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_file_extension_pattern(self):
        """
        Given an allow pattern '/tmp/**/*.txt'
        When check_file_path_permission evaluates a .txt path and a .py path
        Then the .txt path is allowed and the .py path is denied
        """
        allow_patterns = ["/tmp/**/*.txt"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/tmp/docs/readme.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

        decision, reason = check_file_path_permission(
            "/tmp/src/main.py", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")


class TestCheckFilePathPermissionExtendedSyntax(unittest.TestCase):
    """Test [regex]/[glob]/[native] extended-syntax prefixes on already-unwrapped file path patterns."""

    def test_regex_prefix_matches_file_path(self):
        """
        Given an allow pattern carrying a [regex] prefix
        When check_file_path_permission evaluates a path matching that regex
        Then the decision is 'allow' and the reason notes the [regex] match
        """
        allow_patterns = ["[regex]^/Users/[^/]+/\\.claude/projects/.*/memory/.*"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/Users/arnon/.claude/projects/proj/memory/note.md",
            allow_patterns,
            deny_patterns,
        )
        self.assertEqual(decision, "allow")
        self.assertIn("[regex]", reason)

    def test_regex_prefix_does_not_match_other_paths(self):
        """
        Given an allow pattern carrying a [regex] prefix
        When check_file_path_permission evaluates a path outside that regex
        Then the decision is 'deny'
        """
        allow_patterns = ["[regex]^/Users/[^/]+/\\.claude/projects/.*/memory/.*"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/Users/arnon/documents/secret.md", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

    def test_glob_prefix_matches_file_path(self):
        """
        Given an allow pattern carrying a [glob] prefix with globstars
        When check_file_path_permission evaluates a matching nested path
        Then the decision is 'allow' and the reason notes the [glob] match
        """
        allow_patterns = ["[glob]/Users/*/projects/**/memory/**"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/Users/arnon/projects/myproj/memory/sub/note.md",
            allow_patterns,
            deny_patterns,
        )
        self.assertEqual(decision, "allow")
        self.assertIn("[glob]", reason)

    def test_glob_prefix_single_star_no_recursion(self):
        """
        Given a [glob]/tmp/* pattern and a [glob]/tmp/** pattern
        When check_file_path_permission evaluates a nested path against each
        Then the single-star pattern denies but the globstar pattern allows
        """
        allow_patterns = ["[glob]/tmp/*"]
        deny_patterns = []

        decision, _ = check_file_path_permission(
            "/tmp/sub/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

        decision, _ = check_file_path_permission(
            "/tmp/sub/file.txt", ["[glob]/tmp/**"], deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_regex_prefix_in_deny_list(self):
        """
        Given a broad [glob] allow pattern and a [regex] deny pattern for .env files
        When check_file_path_permission evaluates a matching .env path
        Then the decision is 'deny' and the reason cites the deny pattern
        """
        allow_patterns = ["[glob]/Users/*/**"]
        deny_patterns = ["[regex]\\.env(\\.|$)"]

        decision, reason = check_file_path_permission(
            "/Users/arnon/project/.env", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("deny pattern", reason)

    def test_default_pattern_still_works_like_glob(self):
        """
        Given an unprefixed allow pattern '/tmp/**'
        When check_file_path_permission evaluates a nested path
        Then the decision is 'allow', preserving glob semantics for backwards compatibility
        """
        allow_patterns = ["/tmp/**"]
        deny_patterns = []

        decision, _ = check_file_path_permission(
            "/tmp/a/b/c.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

    def test_extended_syntax_disabled_treats_prefix_as_literal(self):
        """
        Given a '[regex]^/tmp/.*' allow pattern
        When check_file_path_permission evaluates '/tmp/file.txt' with extended_syntax on then off
        Then it is allowed with extended syntax but denied without, where the prefix is a literal glob
        """
        allow_patterns = ["[regex]^/tmp/.*"]
        deny_patterns = []

        decision, _ = check_file_path_permission(
            "/tmp/file.txt", allow_patterns, deny_patterns, extended_syntax=True
        )
        self.assertEqual(decision, "allow")

        decision, _ = check_file_path_permission(
            "/tmp/file.txt", allow_patterns, deny_patterns, extended_syntax=False
        )
        self.assertEqual(decision, "deny")

    def test_native_prefix_matches_file_path(self):
        """
        Given an allow pattern carrying a [native] prefix with single-star segments
        When check_file_path_permission evaluates a path matching those segments
        Then the decision is 'allow'
        """
        allow_patterns = ["[native]/Users/*/projects/*"]
        deny_patterns = []

        decision, _ = check_file_path_permission(
            "/Users/arnon/projects/myproj", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")


class TestLoadFilePathPatterns(unittest.TestCase):
    """Test loading file path patterns from config."""

    @staticmethod
    def _config_from_permissions(permissions):
        """Build a one-layer Configuration whose native layer holds permissions."""
        layer = ConfigLayer(
            Provenance(
                "project", "claude", "json", Path("/fake/.claude/settings.local.json")
            ),
            MappingProxyType({"permissions": permissions}),
        )
        return Configuration(layers=(layer,))

    def test_load_patterns_from_config(self):
        """
        Given a config with allow/deny entries for Read, Write, and Bash
        When load_file_path_patterns is asked for 'Read'
        Then only the Read allow and deny patterns are returned, unwrapped
        """
        config = self._config_from_permissions(
            {
                "allow": [
                    "Read(/tmp/**)",
                    "Read(/home/**)",
                    "Write(/tmp/*)",
                    "Bash(git status:*)",
                ],
                "deny": ["Read(/tmp/secret/**)"],
            }
        )

        allow, deny = load_file_path_patterns("Read", config=config)

        self.assertEqual(len(allow), 2)
        self.assertIn("/tmp/**", allow)
        self.assertIn("/home/**", allow)

        self.assertEqual(len(deny), 1)
        self.assertIn("/tmp/secret/**", deny)

    def test_load_write_patterns(self):
        """
        Given a config with allow entries for Read and Write
        When load_file_path_patterns is asked for 'Write'
        Then only the two Write patterns are returned, unwrapped
        """
        config = self._config_from_permissions(
            {
                "allow": ["Read(/tmp/**)", "Write(/tmp/*)", "Write(~/projects/**)"],
                "deny": [],
            }
        )

        allow, deny = load_file_path_patterns("Write", config=config)

        self.assertEqual(len(allow), 2)
        self.assertIn("/tmp/*", allow)
        self.assertIn("~/projects/**", allow)


class TestFilePathToolsInMain(unittest.TestCase):
    """Test that main() correctly handles file path tools."""

    def test_read_tool_allowed(self):
        """
        Given Read is governed and patterns allow '/tmp/**'
        When main() processes a Read of '/tmp/test.txt'
        Then the decision is 'allow'
        """
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(
            governed=["Read", "Write", "Edit"],
            file_patterns={"Read": (["/tmp/**"], [])},
        )
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "allow",
                            )

    def test_write_tool_asks_on_no_match_by_default(self):
        """
        Given Write is governed and patterns only allow '/tmp/**' (rules ARE
            configured, but none matches the target path)
        When main() processes a Write to '/etc/passwd'
        Then the decision is 'ask' AND the reason names the fallback that
            produced it -- 'ask' alone cannot distinguish no_match_fallback
            from any of the safety nets that also floor to 'ask'
        """
        hook_input = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/etc/passwd"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(
            governed=["Read", "Write", "Edit"],
            file_patterns={"Write": (["/tmp/**"], [])},
        )
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "ask",
                            )
                            self.assertIn(
                                "no_match_fallback=ask",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_edit_tool_with_deny_pattern(self):
        """
        Given Edit is governed with allow '/tmp/**' and deny '/tmp/secret/**'
        When main() processes an Edit of '/tmp/secret/config.txt'
        Then the decision is 'deny' and the reason cites that exact deny
            pattern -- naming it separates a real deny match from the
            fail-closed denies, which carry no pattern at all
        """
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/secret/config.txt"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(
            governed=["Read", "Write", "Edit"],
            file_patterns={"Edit": (["/tmp/**"], ["/tmp/secret/**"])},
        )
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "deny",
                            )
                            self.assertIn(
                                "deny pattern: /tmp/secret/**",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_read_no_file_path_denied(self):
        """
        Given Read is governed but the tool input has no file_path
        When main() processes the invocation
        Then the decision is 'deny' and the reason is the missing-file_path
            guard specifically, not some other deny that also mentions the key
        """
        hook_input = {
            "tool_name": "Read",
            "tool_input": {},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Read", "Write", "Edit"])
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "deny",
                            )
                            self.assertIn(
                                "No file_path provided",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_read_no_allow_patterns_asks(self):
        """
        Given Read is governed but NO permission rules are configured at all
            (no allow, deny, ask, or hard_deny anywhere)
        When main() processes a Read of '/tmp/test.txt'
        Then the decision is 'ask' (an entirely unconfigured tool must not
             brick a fresh install by denying everything) and the reason
             notes no Read permission rules are configured
        """
        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Read", "Write", "Edit"])
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch(
                        "toolguard.hook.load_file_path_patterns", return_value=([], [])
                    ):
                        with patch("toolguard.hook.log_command"):
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "ask",
                                )
                                self.assertIn(
                                    "No Read permission",
                                    output["hookSpecificOutput"][
                                        "permissionDecisionReason"
                                    ],
                                )

    def test_bash_no_allow_patterns_asks(self):
        """
        Given Bash is governed but NO permission rules are configured at all
            (no allow, deny, ask, or hard_deny anywhere)
        When main() processes a 'git status' Bash invocation
        Then the decision is 'ask' (an entirely unconfigured tool must not
             brick a fresh install by denying everything)
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Bash"])
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "ask",
                            )
                            self.assertIn(
                                "No Bash permission",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )


class TestNoMatchFallbackThroughMain(unittest.TestCase):
    """End-to-end main() coverage of no_match_fallback resolution against a real Configuration (not the fake double)."""

    @staticmethod
    def _hook_layer(content):
        """Build a single project-level toolguard_hook ConfigLayer."""
        return ConfigLayer(
            Provenance(
                "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml"), 0
            ),
            MappingProxyType(content),
        )

    def test_bash_default_no_match_fallback_asks_via_main(self):
        """
        Given a real Configuration governing Bash, allowing only 'git *', with
            NO no_match_fallback set at all (relying on the default)
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is 'ask' AND the reason names both the unmatched
            sub-command and no_match_fallback=ask -- a bare 'ask' cannot
            distinguish the default fallback from the undecidable-segment ask
            floor, which every command also passes through
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "ask",
                            )
                            reason = output["hookSpecificOutput"][
                                "permissionDecisionReason"
                            ]
                            self.assertIn("whoami", reason)
                            self.assertIn("no_match_fallback=ask", reason)

    def test_permission_mode_from_hook_input_is_recorded_on_the_logged_decision(self):
        """
        Given a real Configuration and a hook input that includes Claude
        Code's own 'permission_mode' field
        When main() processes an unmatched Bash invocation (resolves to 'ask')
        Then log_command is called with that exact permission_mode value --
        recorded for diagnosis only, it must not change the verdict itself
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "cd /tmp"},
            "hook_event_name": "PreToolUse",
            "permission_mode": "default",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command") as mock_log:
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "ask",
                            )
                            mock_log.assert_called_once()
                            self.assertEqual(
                                mock_log.call_args.args[0].permission_mode,
                                "default",
                            )

    def test_missing_permission_mode_in_hook_input_logs_none(self):
        """
        Given a hook input with NO 'permission_mode' field at all (older
        Claude Code versions may omit it)
        When main() processes an unmatched Bash invocation
        Then log_command is called with permission_mode=None rather than
        raising -- the field is optional, never required
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "cd /tmp"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO):
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command") as mock_log:
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            mock_log.assert_called_once()
                            self.assertIsNone(
                                mock_log.call_args.args[0].permission_mode
                            )

    def test_bash_takeover_enabled_default_no_match_fallback_asks_via_main(self):
        """
        Given a real Configuration with takeover_mode enabled and NO
            no_match_fallback set at all (relying on the default), allowing
            only 'git *' for Bash
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is 'ask' AND the reason names the unmatched
            sub-command and no_match_fallback=ask (the default applies in
            takeover mode too, not just non-takeover mode) -- a bare 'ask'
            cannot distinguish that from the undecidable ask floor
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "takeover_mode": {"enabled": True},
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch(
                        "toolguard.hook.get_env_config",
                        return_value={"log_dir": Path("/fake/logs")},
                    ):
                        with patch("toolguard.hook.log_command"):
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "ask",
                                )
                                reason = output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ]
                                self.assertIn("whoami", reason)
                                self.assertIn("no_match_fallback=ask", reason)

    def test_bash_allow_with_warning_fallback_allows_via_main(self):
        """
        Given a real Configuration governing Bash, allowing only 'git *', with
            the top-level no_match_fallback set to the canonical
            'allow_with_warning'
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is 'allow' and the reason mentions allow_with_warning
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "allow",
                            )
                            self.assertIn(
                                "allow_with_warning",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_bash_no_match_allow_with_warning_reaches_warning_log_stream(self):
        """
        Given the same no_match_fallback='allow_with_warning' setup as
            test_bash_allow_with_warning_fallback_allows_via_main
        When main() processes the unmatched command
        Then error_log.log_warning is called once with the same reason text
            (allow_with_warning must actually reach the WARNING log stream
            the docs promise, not just say "warning" inside the reason
            string)
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO):
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                mock_log_warning.assert_called_once()
                                warned_reason = mock_log_warning.call_args.args[0]
                                self.assertIn(
                                    "no_match_fallback=allow_with_warning",
                                    warned_reason,
                                )

    def test_bash_explicit_allow_does_not_reach_warning_log_stream(self):
        """
        Given a command that matches an explicit allow rule (no fallback
            involved at all)
        When main() processes it
        Then error_log.log_warning is NOT called -- the m6 fix must only
            fire for the allow_with_warning fallback, never for an ordinary
            explicit allow
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO):
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                mock_log_warning.assert_not_called()

    def test_bash_undecidable_allow_with_warning_reaches_warning_log_stream(self):
        """
        Given undecidable_fallback='allow_with_warning' and a heredoc feeding
            foreign inline code into an otherwise-allowed interpreter
        When main() processes the compound command
        Then the decision is 'allow' AND error_log.log_warning is called with
            a reason naming undecidable_fallback=allow_with_warning (the
            undecidable_fallback half of the same no_match_fallback gap)
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "undecidable_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(uv run*)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "uv run python - <<'PY'\nimport os\nPY"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "allow",
                                )
                                mock_log_warning.assert_called_once()
                                warned_reason = mock_log_warning.call_args.args[0]
                                self.assertIn(
                                    "undecidable_fallback=allow_with_warning",
                                    warned_reason,
                                )

    def test_bash_no_match_allow_does_not_reach_warning_log_stream(self):
        """
        Given no_match_fallback='allow' (allow with NO warning)
        When main() processes an unmatched command
        Then the decision is 'allow' but error_log.log_warning is NEVER
            called -- 'allow' must not trip the same warning-stream logic
            'allow_with_warning' does, and the reason text does not claim a
            warning was emitted
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "no_match_fallback": "allow",
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "allow",
                                )
                                mock_log_warning.assert_not_called()
                                self.assertNotIn(
                                    "allow_with_warning",
                                    output["hookSpecificOutput"][
                                        "permissionDecisionReason"
                                    ],
                                )

    def test_bash_no_match_allow_with_no_warnings_alias_via_main(self):
        """
        Given no_match_fallback='allow_with_no_warnings' (the long-form
            alias for 'allow')
        When main() processes an unmatched command
        Then the decision is 'allow', error_log.log_warning is NEVER called
            (identical behaviour to plain 'allow'), and the reason names
            no_match_fallback=allow (the alias is normalized before the
            reason is built)
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "no_match_fallback": "allow_with_no_warnings",
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "allow",
                                )
                                mock_log_warning.assert_not_called()
                                reason = output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ]
                                self.assertIn("no_match_fallback=allow", reason)
                                self.assertNotIn("allow_with_warning", reason)

    def test_bash_undecidable_allow_does_not_reach_warning_log_stream(self):
        """
        Given undecidable_fallback='allow' (allow with NO warning) and a
            heredoc feeding foreign inline code into an otherwise-allowed
            interpreter
        When main() processes the compound command
        Then the decision is 'allow' but error_log.log_warning is NEVER
            called -- the undecidable_fallback half of the same no-warning
            guarantee 'no_match_fallback=allow' has
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "undecidable_fallback": "allow",
                        "permissions": {"allow": ["Bash(uv run*)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "uv run python - <<'PY'\nimport os\nPY"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch("toolguard.hook.log_warning") as mock_log_warning:
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "allow",
                                )
                                mock_log_warning.assert_not_called()

    def test_bash_warn_deny_legacy_alias_allows_via_main(self):
        """
        Given a real Configuration governing Bash, allowing only 'git *', with
            the top-level no_match_fallback set to the DEPRECATED legacy value
            'warn_deny'
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is 'allow' (the legacy alias still allows, exactly
             like 'allow_with_warning') and the reason mentions
             allow_with_warning (not the old 'warn_deny' name)
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "no_match_fallback": "warn_deny",
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "allow",
                            )
                            self.assertIn(
                                "allow_with_warning",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_bash_takeover_enabled_deny_fallback_still_fails_closed_via_main(self):
        """
        Given a real Configuration with takeover_mode enabled and an explicit
            no_match_fallback='deny', allowing only 'git *' for Bash
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is still 'deny' AND the reason names the unmatched
            sub-command and the no-allow-match cause (takeover mode does not
            weaken the fail-closed fallback) -- a bare 'deny' cannot
            distinguish the fallback from the empty-extraction deny, which
            reports 'No valid commands found' and names no sub-command
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "takeover_mode": {"enabled": True, "no_match_fallback": "deny"},
                        "permissions": {"allow": ["Bash(git *)"], "deny": []},
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch(
                        "toolguard.hook.get_env_config",
                        return_value={"log_dir": Path("/fake/logs")},
                    ):
                        with patch("toolguard.hook.log_command"):
                            with patch(
                                "toolguard.hook.identify_current_agent",
                                return_value={"agent_type": "main"},
                            ):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(
                                    output["hookSpecificOutput"]["permissionDecision"],
                                    "deny",
                                )
                                reason = output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ]
                                self.assertIn("whoami", reason)
                                self.assertIn(
                                    "does not match any allow patterns", reason
                                )


class TestAdditionalContextThroughMain(unittest.TestCase):
    """End-to-end main() coverage of additionalContext propagation into the JSON output and log entry, against a real Configuration."""

    @staticmethod
    def _hook_layer(content):
        """Build a single project-level toolguard_hook ConfigLayer."""
        return ConfigLayer(
            Provenance(
                "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml"), 0
            ),
            MappingProxyType(content),
        )

    def test_bash_enriched_allow_rule_puts_context_in_emitted_json(self):
        """
        Given a real Configuration governing Bash with a structured allow
            entry for 'git:*' carrying additionalContext = 'prefer --short'
        When main() processes a matching 'git status' Bash invocation
        Then the decision is 'allow' and the emitted JSON's hookSpecificOutput
            carries 'additionalContext' == 'prefer --short'
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git:*)",
                                    "additionalContext": "prefer --short",
                                }
                            ],
                            "deny": [],
                        },
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command") as mock_log:
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "allow",
                            )
                            self.assertEqual(
                                output["hookSpecificOutput"]["additionalContext"],
                                "prefer --short",
                            )
                            mock_log.assert_called_once()
                            self.assertEqual(
                                mock_log.call_args.args[0].additional_context,
                                "prefer --short",
                            )

    def test_read_enriched_allow_rule_puts_context_in_emitted_json(self):
        """
        Given a real Configuration governing Read with a structured allow
            entry for '/tmp/**' carrying additionalContext = 'scratch only'
        When main() processes a matching Read of '/tmp/test.txt'
        Then the decision is 'allow' and the emitted JSON's hookSpecificOutput
            carries 'additionalContext' == 'scratch only'
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Read"],
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Read([glob]/tmp/**)",
                                    "additionalContext": "scratch only",
                                }
                            ],
                            "deny": [],
                        },
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command") as mock_log:
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "allow",
                            )
                            self.assertEqual(
                                output["hookSpecificOutput"]["additionalContext"],
                                "scratch only",
                            )
                            mock_log.assert_called_once()
                            self.assertEqual(
                                mock_log.call_args.args[0].additional_context,
                                "scratch only",
                            )

    def test_error_path_no_command_provided_emits_no_additional_context(self):
        """
        Given a governed Bash config and a hook input with NO 'command' key
            (an error/guard path -- there is no matched rule)
        When main() processes the event
        Then the decision is the missing-command guard's own deny (named in
            the reason, so it is not confused with any other fail-closed
            deny) and the emitted JSON's hookSpecificOutput has no
            'additionalContext' key at all
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git:*)",
                                    "additionalContext": "prefer --short",
                                }
                            ],
                            "deny": [],
                        },
                    }
                ),
            )
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {},
            "hook_event_name": "PreToolUse",
        }

        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.load_configuration", return_value=config):
                    with patch("toolguard.hook.log_command"):
                        with patch(
                            "toolguard.hook.identify_current_agent",
                            return_value={"agent_type": "main"},
                        ):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(
                                output["hookSpecificOutput"]["permissionDecision"],
                                "deny",
                            )
                            self.assertIn(
                                "No command provided",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )
                            self.assertNotIn(
                                "additionalContext", output["hookSpecificOutput"]
                            )


class TestSettingsPathOverrideWarning(unittest.TestCase):
    """CLAUDE_SETTINGS_PATH bypasses the whole config hierarchy (single-file mode); the hook must surface this on stderr every invocation."""

    @staticmethod
    def _allow_whoami_config():
        """A minimal real Configuration that governs and allows the probe command."""
        return Configuration(
            layers=(
                ConfigLayer(
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/toolguard_hook.toml"),
                        0,
                    ),
                    MappingProxyType(
                        {
                            "governed_tools": ["Bash"],
                            "permissions": {"allow": ["Bash(whoami)"], "deny": []},
                        }
                    ),
                ),
            )
        )

    def _run_main_capture_stderr(self):
        """Drive main() with a benign allowed Bash event, returning captured stderr."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "whoami"},
            "hook_event_name": "PreToolUse",
        }
        config = self._allow_whoami_config()
        with patch("sys.stdin", StringIO(json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO):
                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config",
                            return_value={"log_dir": None},
                        ):
                            with patch("toolguard.hook.log_command"):
                                with patch(
                                    "toolguard.hook.identify_current_agent",
                                    return_value={"agent_type": "main"},
                                ):
                                    try:
                                        main()
                                    except SystemExit:
                                        pass
        return mock_stderr.getvalue()

    def test_warns_when_settings_path_override_active(self):
        """
        Given CLAUDE_SETTINGS_PATH is set in the environment
        When the hook's main() processes an event
        Then a single-file-mode / hierarchy-bypassed warning is printed to stderr,
             naming the variable and the exact override path
        """
        override = "/other/project/.claude/settings.local.json"
        with patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": override}):
            stderr = self._run_main_capture_stderr()
        self.assertIn("CLAUDE_SETTINGS_PATH is set", stderr)
        self.assertIn("single-file mode", stderr)
        self.assertIn(override, stderr)

    def test_no_warning_when_override_absent(self):
        """
        Given CLAUDE_SETTINGS_PATH is NOT set in the environment
        When the hook's main() processes an event
        Then no single-file-mode override warning is printed to stderr
        """
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CLAUDE_SETTINGS_PATH", None)
            stderr = self._run_main_capture_stderr()
        self.assertNotIn("CLAUDE_SETTINGS_PATH is set", stderr)


class TestDoubleSlashNormalization(unittest.TestCase):
    """
    Redundant slashes in file-path patterns (e.g. `//Users/...`, common after
    migrating settings.local.json patterns) must normalize and match like a
    single slash, for both allow and deny -- a prior bug here made a
    migrated allow rule silently deny.
    """

    def test_double_slash_allow_matches_real_path(self):
        """
        Given an allow pattern with a doubled leading slash `//Users/x/**`
        When a real single-slash path `/Users/x/foo` is evaluated
        Then it is allowed (the `//` is normalized to `/` before matching)
        """
        decision, _ = check_file_path_permission("/Users/x/foo", ["//Users/x/**"], [])
        self.assertEqual(decision, "allow")

    def test_double_slash_deny_still_denies(self):
        """
        Given a matching absolute allow `/secrets/**` AND a doubled-slash deny
            `//secrets/**` for the same tree
        When `/secrets/passwd` is evaluated
        Then it is DENIED -- the `//` deny normalizes and wins over the allow, so
            normalization must not weaken deny matching
        """
        decision, _ = check_file_path_permission(
            "/secrets/passwd", ["/secrets/**"], ["//secrets/**"]
        )
        self.assertEqual(decision, "deny")

    def test_double_slash_preserves_globstar(self):
        """
        Given a doubled-slash allow with a globstar `//a/**`
        When a deep path `/a/b/c` is evaluated
        Then it matches (collapsing duplicate slashes does not disturb `**`)
        """
        decision, _ = check_file_path_permission("/a/b/c", ["//a/**"], [])
        self.assertEqual(decision, "allow")

    def test_single_slash_unaffected(self):
        """
        Given an ordinary single-slash allow `/tmp/**` (regression guard)
        When `/tmp/foo` is evaluated
        Then it still matches -- normalization is a no-op on well-formed paths
        """
        decision, _ = check_file_path_permission("/tmp/foo", ["/tmp/**"], [])
        self.assertEqual(decision, "allow")


class TestStartupValidation(unittest.TestCase):
    """Test startup validation only validates toolguard_hook files."""

    def test_validation_ignores_settings_local_json(self):
        """
        Given a native settings.local.json listing unsupported tools, alongside
            a toolguard_hook layer carrying one unsupported tool of its OWN
            (the positive control: without it the config yields zero issues,
            nothing is ever written, and the assertions below cannot fail)
        When _run_startup_validation runs and delegates to
            Configuration.validation_issues()
        Then the log it writes names the toolguard_hook tool and none of the
            native-only ones -- proving the native layers are exempt, not that
            validation simply found nothing anywhere
        """
        import tempfile

        from toolguard.config import Configuration

        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()
            logs_dir = project_dir / "logs"
            logs_dir.mkdir()

            native_layer = ConfigLayer(
                Provenance(
                    "project", "claude", "json", claude_dir / "settings.local.json"
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["WebSearch", "WebFetch", "mcp__unknown__tool"]
                        }
                    }
                ),
            )
            hook_layer = ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "toml",
                    claude_dir / "toolguard_hook.toml",
                ),
                MappingProxyType(
                    {
                        "governed_tools": ["Bash", "Read"],
                        "permissions": {
                            "allow": [
                                "Bash(ls:*)",
                                "Read(/tmp/**)",
                                "Nonesuch(/tmp/**)",
                            ]
                        },
                    }
                ),
            )
            config = Configuration(layers=(native_layer, hook_layer))

            env_config = {"log_dir": logs_dir}

            from toolguard.hook import _run_startup_validation

            with patch("sys.stderr", new_callable=StringIO):
                _run_startup_validation(env_config, str(project_dir), config)

            # Warnings land in toolguard-warning-*.md, not toolguard-error-*.md
            # -- globbing the wrong stream is a second way for this to assert
            # nothing.
            log_files = sorted(logs_dir.glob("toolguard-*.md"))
            self.assertTrue(
                log_files,
                "validation wrote nothing at all, so the exemption asserted "
                "below is untested",
            )
            content = "\n".join(path.read_text() for path in log_files)
            self.assertIn("Nonesuch", content)
            self.assertNotIn("WebSearch", content)
            self.assertNotIn("WebFetch", content)
            self.assertNotIn("mcp__unknown__tool", content)

    def test_validation_logs_issues_from_config(self):
        """
        Given a config whose validation_issues() returns one warning Issue
        When _run_startup_validation runs
        Then log_warning is called once with that issue's message and corrective steps
        """
        from toolguard.config import Issue

        issue = Issue("warning", "bad tool WebSearch", "remove it")

        class _IssueConfig:
            def validation_issues(self_inner):
                return (issue,)

        env_config = {"log_dir": Path("/fake/logs")}
        with patch("toolguard.hook.log_warning") as mock_log_warning:
            from toolguard.hook import _run_startup_validation

            _run_startup_validation(env_config, "/some/dir", _IssueConfig())
            mock_log_warning.assert_called_once_with(
                "bad tool WebSearch", "remove it", Path("/fake/logs")
            )

    def test_validation_loads_config_when_none(self):
        """
        Given no config argument is passed to _run_startup_validation
        When it runs for a given directory
        Then it calls load_configuration with that directory to obtain one itself
        """

        class _EmptyConfig:
            def validation_issues(self_inner):
                return ()

        env_config = {"log_dir": Path("/fake/logs")}
        with patch(
            "toolguard.hook.load_configuration", return_value=_EmptyConfig()
        ) as mock_load:
            with patch("toolguard.hook.log_warning"):
                from toolguard.hook import _run_startup_validation

                _run_startup_validation(env_config, "/some/dir")
                mock_load.assert_called_once_with("/some/dir")


class TestLoadFilePathPatternsAdapter(unittest.TestCase):
    """load_file_path_patterns loads a config itself when none is passed."""

    def test_loads_configuration_when_none(self):
        """
        Given no config is passed to load_file_path_patterns
        When it is called for 'Read' with a directory
        Then it loads a configuration for that directory and returns its Read allow/deny patterns
        """
        config = _fake_config(
            file_patterns={"Read": (("/tmp/**",), ("/tmp/secret/**",))}
        )
        with patch(
            "toolguard.hook.load_configuration", return_value=config
        ) as mock_load:
            allow, deny = load_file_path_patterns("Read", "/some/dir")
            mock_load.assert_called_once_with("/some/dir")
            self.assertEqual(allow, ["/tmp/**"])
            self.assertEqual(deny, ["/tmp/secret/**"])


class TestLogAllowedCommand(unittest.TestCase):
    """
    Test the _log_allowed_command helper function, driving the REAL
    resolve_bash_permission_detailed pipeline (not a hand-constructed
    verdict) so ``sub_matches`` is populated the way production populates
    it -- the retired reason-string regex parser this replaced silently
    dropped the audit-log entry for any sub-command whose allow came from
    ``no_match_fallback``, measured at 813 of 975 under-logged.
    """

    @staticmethod
    def _config(content):
        """Build a single project-level toolguard_hook Configuration."""
        return Configuration(
            layers=(
                ConfigLayer(
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/toolguard_hook.toml"),
                        0,
                    ),
                    MappingProxyType(content),
                ),
            )
        )

    @patch("toolguard.hook.log_command")
    def test_simple_command_logs_matched_rule(self, mock_log):
        """
        Given a real Configuration allowing 'Bash(ls)' and the REAL
            RuntimeVerdict produced by resolving the command 'ls' against it
            (not a hand-picked matched_rule/provenance)
        When _log_allowed_command logs that resolution
        Then log_command is called once with a LogRecord carrying status
            'executed' and the exact matched rule and provenance the
            resolver itself attributed -- pinning the real extraction
            pipeline, not a tautology
        """
        config = self._config({"permissions": {"allow": ["Bash(ls)"], "deny": []}})
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed("ls", config, True, hd_deny, hd_allow)
        self.assertEqual(result.decision, "allow")

        _log_allowed_command(result, "ls", "main", {})
        mock_log.assert_called_once_with(
            LogRecord(
                command_str="ls",
                status="executed",
                matched_rule="ls",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="main",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )

    @patch("toolguard.hook.log_command")
    def test_compound_command_logs_per_subcommand(self, mock_log):
        """
        Given a real Configuration allowing 'Bash(git *)' and the compound
            command 'git status && git log'
        When _log_allowed_command logs the REAL resolution
        Then log_command is called once per sub-command, each with its own
            matched rule and provenance -- one UnitVerdict per sub-command
        """
        config = self._config({"permissions": {"allow": ["Bash(git *)"], "deny": []}})
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "git status && git log", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(len(result.sub_matches), 2)

        _log_allowed_command(result, "git status && git log", "main", {})
        self.assertEqual(mock_log.call_count, 2)
        mock_log.assert_any_call(
            LogRecord(
                command_str="git status",
                status="executed",
                matched_rule="git *",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="main",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )
        mock_log.assert_any_call(
            LogRecord(
                command_str="git log",
                status="executed",
                matched_rule="git *",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="main",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )

    @patch("toolguard.hook.log_command")
    def test_compound_three_commands(self, mock_log):
        """
        Given a real Configuration allowing 'Bash(git *)', 'Bash(cat *)', and
            'Bash(grep *)' and a three-sub-command compound command
        When _log_allowed_command logs the REAL resolution
        Then log_command is called three times, once per sub-command with its
            own matched rule and the agent info threaded through
        """
        config = self._config(
            {
                "permissions": {
                    "allow": ["Bash(git *)", "Bash(cat *)", "Bash(grep *)"],
                    "deny": [],
                }
            }
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        command = "git status && cat file | grep pat"
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(len(result.sub_matches), 3)

        _log_allowed_command(result, command, "sub-agent", {})
        self.assertEqual(mock_log.call_count, 3)
        mock_log.assert_any_call(
            LogRecord(
                command_str="git status",
                status="executed",
                matched_rule="git *",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="sub-agent",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )
        mock_log.assert_any_call(
            LogRecord(
                command_str="cat file",
                status="executed",
                matched_rule="cat *",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="sub-agent",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )
        mock_log.assert_any_call(
            LogRecord(
                command_str="grep pat",
                status="executed",
                matched_rule="grep *",
                provenance="project: /p/toolguard_hook.toml",
                extra_info="sub-agent",
                permission_mode=None,
                additional_context=None,
            ),
            config={},
        )

    @patch("toolguard.hook.log_command")
    def test_mixed_rule_match_and_no_match_fallback_logs_one_entry_each(self, mock_log):
        """
        Given no_match_fallback='allow_with_warning' and a compound command
            whose FIRST sub-command matches a real rule ('Bash(ls)') and
            whose SECOND matches nothing at all (falls through to the
            fallback)
        When _log_allowed_command logs the REAL resolution
        Then log_command is called TWICE -- once per sub-command -- which is
            exactly the case the retired prose-parser dropped: the fallback
            leaf's raw reason has no ' -> ' in it, so the old regex kept only
            the FIRST entry. This is the regression test for the measured
            813-of-975 under-logging defect.
        """
        config = self._config(
            {
                "no_match_fallback": "allow_with_warning",
                "permissions": {"allow": ["Bash(ls)"], "deny": []},
            }
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        command = "ls && cat README.md"
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(
            len(result.sub_matches),
            2,
            "sub_matches must have one entry per sub-command",
        )

        _log_allowed_command(result, command, "main", {})
        self.assertEqual(
            mock_log.call_count,
            2,
            "one audit-log entry per sub-command -- the fallback-allowed "
            "leaf must not be silently dropped",
        )
        logged = {
            call.args[0].command_str: call.args[0] for call in mock_log.call_args_list
        }
        self.assertEqual(logged["ls"].matched_rule, "ls")
        self.assertEqual(
            logged["cat README.md"].matched_rule, FALLBACK_ALLOW_PLACEHOLDER
        )

    @patch("toolguard.hook.log_command")
    def test_logged_matched_rule_never_carries_a_stray_bracket(self, mock_log):
        """
        Given a multi-leaf compound mixing a genuine rule match with an
            undecidable_fallback escape-hatch leaf (the shape that used to
            round-trip through the "All N sub-commands allowed: [...]"
            bracketed summary text)
        When _log_allowed_command logs the REAL resolution
        Then no logged matched_rule value ends with a STRAY extra ']' after
            the placeholder's own closing bracket -- the retired regex's
            greedy capture used to append one, e.g.
            '[fallback allow -- no rule matched]]' (measured on 79 corpus
            cases). The placeholder's own single trailing ']' is expected
            and correct; this pins the DOUBLE bracket is gone, not that
            brackets vanished entirely.
        """
        config = self._config(
            {
                "undecidable_fallback": "allow_with_warning",
                "permissions": {
                    "allow": ["Bash(ls)", "Bash(python *)"],
                    "deny": [],
                },
            }
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        command = 'ls && python -c "print(1)"'
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")

        _log_allowed_command(result, command, "main", {})
        for call in mock_log.call_args_list:
            matched_rule = call.args[0].matched_rule
            self.assertIsNotNone(matched_rule)
            self.assertNotIn("]]", matched_rule)
            self.assertFalse(matched_rule.endswith("]]"))

    @patch("toolguard.hook.log_command")
    def test_per_subcommand_provenance_is_present_in_the_compound_branch(
        self, mock_log
    ):
        """
        Given a compound command whose two sub-commands match rules declared
            at two DIFFERENT config levels (so each carries its OWN
            provenance)
        When _log_allowed_command logs the REAL resolution
        Then each logged entry carries its OWN sub-command's provenance --
            previously the compound branch never logged provenance at all
        """
        config = Configuration(
            layers=(
                ConfigLayer(
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/toolguard_hook.toml"),
                        0,
                    ),
                    MappingProxyType(
                        {"permissions": {"allow": ["Bash(git *)"], "deny": []}}
                    ),
                ),
                ConfigLayer(
                    Provenance(
                        "user", "toolguard_hook", "toml", Path("/home/u/tg.toml"), 1
                    ),
                    MappingProxyType(
                        {"permissions": {"allow": ["Bash(cat *)"], "deny": []}}
                    ),
                ),
            )
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        command = "git status && cat file"
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")

        _log_allowed_command(result, command, "main", {})
        logged = {
            call.args[0].command_str: call.args[0] for call in mock_log.call_args_list
        }
        self.assertEqual(
            logged["git status"].provenance, "project: /p/toolguard_hook.toml"
        )
        self.assertEqual(logged["cat file"].provenance, "user: /home/u/tg.toml")


class TestHandleCommandToolAuditWiring(unittest.TestCase):
    """
    Drives _handle_command_tool itself (mocking only log_command), not just
    the _log_allowed_command / _log_non_allow_decision helpers it calls --
    testing those helpers alone let 6 wiring mutations, including a swapped
    matched_rule/provenance argument pair, survive the full suite.
    """

    @staticmethod
    def _config(content):
        """Build a single project-level toolguard_hook Configuration."""
        return Configuration(
            layers=(
                ConfigLayer(
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/toolguard_hook.toml"),
                        0,
                    ),
                    MappingProxyType(content),
                ),
            )
        )

    @patch("toolguard.hook.log_command")
    def test_plain_allow_logs_the_exact_matched_rule_and_provenance(self, mock_log):
        """
        Given a real Configuration allowing 'Bash(ls)'
        When _handle_command_tool resolves and logs 'ls'
        Then log_command is called with a LogRecord whose matched_rule is
            EXACTLY 'ls' and whose provenance is EXACTLY the config file's
            provenance -- a mutation that swaps the matched_rule/provenance
            arguments at the _log_allowed_command call site must fail this
            test
        """
        config = self._config(
            {
                "governed_tools": ["Bash"],
                "permissions": {"allow": ["Bash(ls)"], "deny": []},
            }
        )
        verdict = _handle_command_tool({"command": "ls"}, config, {}, "main", None)
        self.assertEqual(verdict.decision, "allow")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.matched_rule, "ls")
        self.assertEqual(record.provenance, "project: /p/toolguard_hook.toml")

    @patch("toolguard.hook.log_command")
    def test_plain_deny_logs_the_exact_violated_rule_and_provenance(self, mock_log):
        """
        Given a real Configuration denying 'Bash(rm -rf *)' (allowing
            everything else)
        When _handle_command_tool resolves and logs 'rm -rf /tmp/x'
        Then log_command is called with a LogRecord whose violated_rules is
            EXACTLY ['rm -rf *'] and whose provenance is EXACTLY the config
            file's provenance
        """
        config = self._config(
            {
                "governed_tools": ["Bash"],
                "permissions": {"allow": ["Bash(*)"], "deny": ["Bash(rm -rf *)"]},
            }
        )
        verdict = _handle_command_tool(
            {"command": "rm -rf /tmp/x"}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "deny")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.violated_rules, ["rm -rf *"])
        self.assertEqual(record.provenance, "project: /p/toolguard_hook.toml")

    @patch("toolguard.hook.log_command")
    def test_escape_hatch_allow_logs_placeholder_and_no_provenance(self, mock_log):
        """
        Given undecidable_fallback='allow_with_warning' and NO 'python -c'
            rule anywhere in the config (the single-leaf command is allowed
            ONLY via the escape hatch, even though its truncated stub
            genuinely matches 'Bash(python *)')
        When _handle_command_tool resolves and logs 'python -c "print(1)"'
        Then the logged LogRecord's matched_rule is the fallback placeholder
            (never the misleading real 'python *' stub match) AND provenance
            is None -- the leaf's recorded UnitVerdict (and therefore
            RuntimeVerdict.matched_rule/provenance) is already None at the
            source (see resolve.py::_deciding_sub_match), not a real 'python
            *' stub match hook.py re-classifies away at log time. This pins
            hook.py::_log_allowed_command logging the placeholder via
            UnitVerdict.fallback_kind, not merely forwarding an already-None
            value from elsewhere.
        """
        config = self._config(
            {
                "governed_tools": ["Bash"],
                "undecidable_fallback": "allow_with_warning",
                "permissions": {
                    "allow": ["Bash(ls)", "Bash(python *)"],
                    "deny": [],
                },
            }
        )
        verdict = _handle_command_tool(
            {"command": 'python -c "print(1)"'}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "allow")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.matched_rule, FALLBACK_ALLOW_PLACEHOLDER)
        self.assertIsNone(record.provenance)

    @patch("toolguard.hook.log_command")
    def test_escape_hatch_deny_logs_placeholder_and_no_provenance(self, mock_log):
        """
        Given undecidable_fallback='deny' and a two-leaf compound whose
            FIRST leaf is the escape-hatch command and whose SECOND leaf
            ('rm foo') matches a REAL deny rule ('Bash(rm *)') with its own
            REAL provenance
        When _handle_command_tool resolves and logs
            'python -c "print(1)" && rm foo'
        Then the compound denies via the escape-hatch leaf (strictest-wins
            picks the first denied leaf), and RuntimeVerdict.matched_rule/
            provenance are BOTH None -- the escape-hatch leaf's own
            UnitVerdict correctly says 'deny', so _deciding_sub_match
            attributes the deny to THAT leaf rather than mis-crediting the
            OTHER leaf's genuine 'rm *' match/provenance. The logged
            LogRecord's violated_rules is the placeholder and provenance is
            None either way, proving the deny-branch suppression guard in
            hook.py::_log_non_allow_decision is reason-driven, not merely
            forwarding an already-None value.
        """
        config = self._config(
            {
                "governed_tools": ["Bash"],
                "undecidable_fallback": "deny",
                "permissions": {
                    "allow": ["Bash(ls)", "Bash(python *)"],
                    "deny": ["Bash(rm *)"],
                },
            }
        )
        verdict = _handle_command_tool(
            {"command": 'python -c "print(1)" && rm foo'}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "deny")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.violated_rules, [FALLBACK_DENY_PLACEHOLDER])
        self.assertIsNone(record.provenance)


class TestHandleFilePathToolAuditWiring(unittest.TestCase):
    """
    Drives _handle_file_path_tool itself -- its allow branch calls
    log_command directly (not through _log_allowed_command), and a
    mutation removing its provenance argument survived the full suite.
    """

    @staticmethod
    def _config(content):
        """Build a single project-level toolguard_hook Configuration."""
        return Configuration(
            layers=(
                ConfigLayer(
                    Provenance(
                        "project",
                        "toolguard_hook",
                        "toml",
                        Path("/p/toolguard_hook.toml"),
                        0,
                    ),
                    MappingProxyType(content),
                ),
            )
        )

    @patch("toolguard.hook.log_command")
    def test_file_path_allow_logs_the_exact_matched_rule_and_provenance(self, mock_log):
        """
        Given a real Configuration allowing 'Read(/tmp/x/**)'
        When _handle_file_path_tool resolves and logs a Read of
            '/tmp/x/foo.txt'
        Then log_command is called with a LogRecord whose matched_rule is
            EXACTLY '/tmp/x/**' and whose provenance is EXACTLY the config
            file's provenance
        """
        config = self._config(
            {
                "governed_tools": ["Read"],
                "permissions": {"allow": ["Read(/tmp/x/**)"], "deny": []},
            }
        )
        verdict = _handle_file_path_tool(
            "Read", {"file_path": "/tmp/x/foo.txt"}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "allow")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.matched_rule, "/tmp/x/**")
        self.assertEqual(record.provenance, "project: /p/toolguard_hook.toml")

    @patch("toolguard.hook.log_command")
    def test_file_path_deny_logs_the_exact_violated_rule_and_provenance(self, mock_log):
        """
        Given a real Configuration allowing 'Read(**)' but denying
            'Read(/secrets/**)'
        When _handle_file_path_tool resolves and logs a Read of
            '/secrets/x'
        Then log_command is called with a LogRecord whose violated_rules is
            EXACTLY ['/secrets/**'] and whose provenance is EXACTLY the
            config file's provenance
        """
        config = self._config(
            {
                "governed_tools": ["Read"],
                "permissions": {
                    "allow": ["Read(**)"],
                    "deny": ["Read(/secrets/**)"],
                },
            }
        )
        verdict = _handle_file_path_tool(
            "Read", {"file_path": "/secrets/x"}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "deny")
        mock_log.assert_called_once()
        record = mock_log.call_args.args[0]
        self.assertEqual(record.violated_rules, ["/secrets/**"])
        self.assertEqual(record.provenance, "project: /p/toolguard_hook.toml")

    @patch("toolguard.hook.log_command")
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
    def test_target_is_read_from_the_registered_key(self, mock_log):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When a tool_input carrying only 'target_path' is resolved
        Then the target is found and resolved (not the fail-closed deny)
        """
        config = self._config(
            {
                "governed_tools": ["Read"],
                "permissions": {"allow": ["Read(/tmp/x/**)"], "deny": []},
            }
        )
        verdict = _handle_file_path_tool(
            "Read", {"target_path": "/tmp/x/foo.txt"}, config, {}, "main", None
        )
        self.assertEqual(verdict.decision, "allow")

    @patch("toolguard.hook.log_command")
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
    def test_empty_target_deny_reason_names_the_registered_key(self, mock_log):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When the tool_input lacks 'target_path'
        Then the fail-closed deny reason names 'target_path', not 'file_path'
        """
        config = self._config(
            {
                "governed_tools": ["Read"],
                "permissions": {"allow": ["Read(/tmp/x/**)"], "deny": []},
            }
        )
        verdict = _handle_file_path_tool("Read", {}, config, {}, "main", None)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn("No target_path provided", verdict.reason)


class TestHookArgparseAndIsatty(unittest.TestCase):
    """Tests for the argparse --help flag and the interactive (TTY) guard in hook.main."""

    def test_help_flag_exits_zero(self):
        """
        Given --help on the command line
        When main is called
        Then argparse exits with code 0 (informational, not an error)
        """
        with (
            patch.object(__import__("sys"), "argv", ["toolguard", "--help"]),
            patch("sys.stdout", StringIO()),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 0)

    def test_isatty_true_prints_explanation_and_does_not_read_stdin(self):
        """
        Given a terminal invocation (sys.stdin.isatty() returns True)
        When main is called
        Then it prints an explanation to stderr, exits 0, and does not block on stdin
        """
        err = StringIO()
        stdin_mock = StringIO("")

        with (
            patch("sys.stdin", stdin_mock),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr", err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("Claude Code", err.getvalue())

    def test_isatty_false_processes_piped_event_normally(self):
        """
        Given a piped (non-TTY) invocation with a valid Bash allow event
        When main is called (sys.stdin.isatty() returns False)
        Then the hook processes the event and outputs a JSON permissionDecision
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }
        config = _fake_config(governed=["Bash"], bash=(["git *"], []))

        with (
            patch("sys.stdin", StringIO(json.dumps(hook_input))),
            patch("sys.stdin.isatty", return_value=False),
            patch("sys.stdout", new_callable=StringIO) as mock_stdout,
            patch("toolguard.hook.load_configuration", return_value=config),
            patch("toolguard.hook.log_command"),
        ):
            try:
                main()
            except SystemExit:
                pass

        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")


class TestHookCrashCapture(unittest.TestCase):
    """
    An unhandled exception hitting any of main()'s three except clauses
    must deny-and-continue AND write a full crash report (exception type,
    message, traceback, in-flight context) to ~/.toolguard/errors/ via
    toolguard.error_log.log_crash.
    """

    def test_unexpected_exception_writes_crash_report(self):
        """
        Given a governed Bash event that reaches permission resolution, and
        resolve_bash_permission_detailed forced to raise an unexpected
        RuntimeError
        When main() runs and the exception falls through to the generic
        `except Exception` clause
        Then main() still denies and exits 0, the decision lands on STDOUT
        (TOO-45 punch-list #04 hook.py fix -- this used to go to stderr with
        exit 0, which Claude Code reads as "no opinion" and falls through to
        native permission handling instead of denying), stderr is empty, the
        fault reaches the Claude-facing additionalContext, AND a crash report
        file appears under ~/.toolguard/errors/ describing the RuntimeError
        with a full traceback
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }
        config = _fake_config(governed=["Bash"], bash=(["git *"], []))

        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "logs").mkdir()
            with (
                patch("sys.stdin", StringIO(json.dumps(hook_input))),
                patch("sys.stdin.isatty", return_value=False),
                patch("sys.stdout", new_callable=StringIO) as mock_stdout,
                patch("sys.stderr", new_callable=StringIO) as mock_stderr,
                patch("toolguard.hook.load_configuration", return_value=config),
                patch(
                    "toolguard.hook.resolve_bash_permission_detailed",
                    side_effect=RuntimeError("boom from resolver"),
                ),
                patch("pathlib.Path.home", return_value=home),
                # The outer, config=None error-reporter invocation resolves
                # its log dir via require_project_root(), independent of
                # Path.home() -- isolate it too, or this leaks into the real
                # repo logs/ dir (see .claude/rules/test-config-isolation.md).
                patch("toolguard.log_writer.require_project_root", return_value=home),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

            self.assertEqual(ctx.exception.code, 0)
            # error_log.log_crash/log_error echo their own "[CRASH]"/"[ERROR]"
            # lines to stderr unconditionally as part of writing -- that is
            # unrelated to this fix. What must NOT be on stderr is the
            # decision itself.
            self.assertNotIn('"permissionDecision"', mock_stderr.getvalue())
            stdout_text = mock_stdout.getvalue()
            self.assertTrue(
                stdout_text.strip(), "expected a non-empty decision on stdout"
            )
            output = json.loads(stdout_text)
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn(
                "toolguard crashed while deciding",
                output["hookSpecificOutput"]["additionalContext"],
            )
            self.assertIn(
                "boom from resolver",
                output["hookSpecificOutput"]["additionalContext"],
            )

            errors_dir = home / ".toolguard" / "errors"
            self.assertTrue(errors_dir.is_dir())
            crash_files = list(errors_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(crash_files), 1)
            content = crash_files[0].read_text()
            self.assertIn("RuntimeError", content)
            self.assertIn("boom from resolver", content)
            self.assertIn("Traceback", content)

    def test_json_decode_error_writes_crash_report(self):
        """
        Given stdin contains text that is not valid JSON
        When main() runs and parse_hook_input's json.JSONDecodeError falls
        through to the `except json.JSONDecodeError` clause
        Then main() still denies and exits 0, the decision lands on STDOUT
        and is non-empty (previously this went to stderr with exit 0,
        silently falling through to native permission handling instead of
        denying), the fault reaches additionalContext, AND a crash report
        file appears under ~/.toolguard/errors/ describing the parse
        failure
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "logs").mkdir()
            with (
                patch("sys.stdin", StringIO("not valid json {")),
                patch("sys.stdin.isatty", return_value=False),
                patch("sys.stdout", new_callable=StringIO) as mock_stdout,
                patch("sys.stderr", new_callable=StringIO) as mock_stderr,
                patch("pathlib.Path.home", return_value=home),
                patch("toolguard.log_writer.require_project_root", return_value=home),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

            self.assertEqual(ctx.exception.code, 0)
            # error_log.log_crash/log_error echo their own "[CRASH]"/"[ERROR]"
            # lines to stderr unconditionally as part of writing -- that is
            # unrelated to this fix. What must NOT be on stderr is the
            # decision itself.
            self.assertNotIn('"permissionDecision"', mock_stderr.getvalue())
            stdout_text = mock_stdout.getvalue()
            self.assertTrue(
                stdout_text.strip(), "expected a non-empty decision on stdout"
            )
            output = json.loads(stdout_text)
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn(
                "toolguard crashed while deciding",
                output["hookSpecificOutput"]["additionalContext"],
            )

            errors_dir = home / ".toolguard" / "errors"
            self.assertTrue(errors_dir.is_dir())
            crash_files = list(errors_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(crash_files), 1)
            content = crash_files[0].read_text()
            self.assertIn("JSONDecodeError", content)

    def test_value_error_missing_field_writes_crash_report(self):
        """
        Given valid JSON on stdin that is missing a required field
        (hook_event_name)
        When main() runs and parse_hook_input's ValueError falls through to the
        `except ValueError` clause
        Then main() still denies and exits 0, the decision lands on STDOUT
        and is non-empty (previously this went to stderr with exit 0,
        silently falling through to native permission handling instead of
        denying), the fault reaches additionalContext, AND a crash report
        file appears under ~/.toolguard/errors/ describing the missing
        field
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        }
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "logs").mkdir()
            with (
                patch("sys.stdin", StringIO(json.dumps(hook_input))),
                patch("sys.stdin.isatty", return_value=False),
                patch("sys.stdout", new_callable=StringIO) as mock_stdout,
                patch("sys.stderr", new_callable=StringIO) as mock_stderr,
                patch("pathlib.Path.home", return_value=home),
                patch("toolguard.log_writer.require_project_root", return_value=home),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

            self.assertEqual(ctx.exception.code, 0)
            # error_log.log_crash/log_error echo their own "[CRASH]"/"[ERROR]"
            # lines to stderr unconditionally as part of writing -- that is
            # unrelated to this fix. What must NOT be on stderr is the
            # decision itself.
            self.assertNotIn('"permissionDecision"', mock_stderr.getvalue())
            stdout_text = mock_stdout.getvalue()
            self.assertTrue(
                stdout_text.strip(), "expected a non-empty decision on stdout"
            )
            output = json.loads(stdout_text)
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn(
                "toolguard crashed while deciding",
                output["hookSpecificOutput"]["additionalContext"],
            )

            errors_dir = home / ".toolguard" / "errors"
            self.assertTrue(errors_dir.is_dir())
            crash_files = list(errors_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(crash_files), 1)
            content = crash_files[0].read_text()
            self.assertIn("ValueError", content)
            self.assertIn("Missing required field", content)

    def test_empty_stdin_does_not_write_a_crash_report(self):
        """
        Given stdin is non-interactive (not a TTY) but was read and found
        completely empty -- e.g. a stray `toolguard --version` an agent ran
        to probe the installed version, which argparse silently discards as
        an unrecognized flag, leaving nothing on stdin to read (observed
        twice on real installs, producing a misleading crash report that
        looked like a hook defect but was just a manual probe)
        When main() runs
        Then it exits 0 with the friendly "not a standalone command" message
        on stderr, and NO crash report is written -- this is treated as a
        stray invocation, not an unexpected internal error
        """
        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            with (
                patch("sys.stdin", StringIO("")),
                patch("sys.stdin.isatty", return_value=False),
                patch("sys.stdout", new_callable=StringIO),
                patch("sys.stderr", new_callable=StringIO) as mock_stderr,
                patch("pathlib.Path.home", return_value=home),
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

            self.assertEqual(ctx.exception.code, 0)
            self.assertIn("not a standalone command", mock_stderr.getvalue())
            errors_dir = home / ".toolguard" / "errors"
            self.assertFalse(errors_dir.exists())

    def test_crash_context_carries_tool_name_tool_input_cwd(self):
        """
        Pins the invariant `_build_crash_context` depends on -- that
        `tool_name`, `tool_input`, and `cwd` are still in scope (and thus
        captured via `locals()`) at the point an unexpected exception
        reaches main()'s generic `except Exception` clause.

        Given a governed Bash event with a known tool_name, tool_input, and
        cwd, and resolve_bash_permission_detailed forced to raise an
        unexpected RuntimeError after those three are assigned
        When main() runs and the exception falls through to the generic
        `except Exception` clause
        Then log_crash is called with a crash context dict whose tool_name,
        tool_input, and cwd values equal exactly what was in the hook input
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
            "cwd": "/some/project/dir",
        }
        config = _fake_config(governed=["Bash"], bash=(["git *"], []))

        with TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            (home / "logs").mkdir()
            with (
                patch("sys.stdin", StringIO(json.dumps(hook_input))),
                patch("sys.stdin.isatty", return_value=False),
                patch("sys.stdout", new_callable=StringIO),
                patch("sys.stderr", new_callable=StringIO),
                patch("toolguard.hook.load_configuration", return_value=config),
                patch(
                    "toolguard.hook.resolve_bash_permission_detailed",
                    side_effect=RuntimeError("boom from resolver"),
                ),
                patch("pathlib.Path.home", return_value=home),
                patch("toolguard.log_writer.require_project_root", return_value=home),
                patch("toolguard.hook.log_crash") as mock_log_crash,
            ):
                with self.assertRaises(SystemExit) as ctx:
                    main()

            self.assertEqual(ctx.exception.code, 0)
            mock_log_crash.assert_called_once()
            _exc, crash_context = mock_log_crash.call_args.args[:2]
            self.assertEqual(crash_context["tool_name"], "Bash")
            self.assertEqual(crash_context["tool_input"], {"command": "git status"})
            self.assertEqual(crash_context["cwd"], "/some/project/dir")


def _homeless():
    """Stands in for ambient.home(); raises as pathlib does with no resolvable home."""
    raise RuntimeError("Could not determine home directory")


class TestDecisionReachesStdoutWhenCrashLoggingFails(unittest.TestCase):
    """
    log_crash runs inside all three of main()'s except clauses, ahead of
    _emit_decision, so anything escaping it takes the verdict with it and the
    hook exits with nothing on stdout. An unresolvable home (unset $HOME,
    deleted home, a container with no passwd entry) is the way to provoke that:
    log_crash resolves ~/.toolguard/errors from ambient.home().

    Nothing on stdout is not a denial. Claude Code treats only exit code 2 as
    blocking, so an empty stdout is no permission hook at all, silently. The
    assertion these tests exist for is therefore "stdout still carries a
    verdict", never "log_crash did not raise" -- the second passes with the
    bug present in a different arrangement.

    _drive_main also self-checks that log_crash was actually reached and
    actually failed, so a refactor that moves log_crash off ambient.home()
    fails loudly here instead of leaving this class isolating nothing.
    """

    def _drive_main(self, stdin_text, extra_patches=()):
        """
        Run main() with crash logging unable to resolve a home; return
        (stdout, escaped exception).

        Also asserts that log_crash was actually reached and actually failed
        under this fixture.
        """
        out = StringIO()
        crash_results = []

        def _spy_log_crash(*args, **kwargs):
            result = log_crash(*args, **kwargs)
            crash_results.append(result)
            return result

        with TemporaryDirectory() as tmpdir:
            with ExitStack() as stack:
                for context in (
                    patch("sys.stdin", StringIO(stdin_text)),
                    patch("sys.stdin.isatty", return_value=False),
                    patch("sys.stdout", out),
                    patch("sys.stderr", new_callable=StringIO),
                    # Patching the accessor, not isolating config: only an
                    # ambient.home that raises produces the machine these tests
                    # are about.
                    patch("toolguard.ambient.home", _homeless),
                    # get_env_config() resolves before load_configuration(), so
                    # the Reporter falls back to a log dir the module-level
                    # TOOLGUARD_LOG_DIR isolation does not cover -- removing this
                    # patch as redundant trips _real_log_dir_guard (see
                    # .claude/rules/test-config-isolation.md).
                    patch(
                        "toolguard.log_writer.require_project_root",
                        return_value=Path(tmpdir),
                    ),
                    # Spies on the real log_crash so a future refactor moving it
                    # off ambient.home() fails loudly here, instead of silently
                    # leaving this fixture isolating nothing.
                    patch("toolguard.hook.log_crash", side_effect=_spy_log_crash),
                    *extra_patches,
                ):
                    stack.enter_context(context)

                # Without this the fixture cannot produce the negative case.
                with self.assertRaises(RuntimeError):
                    ambient.home()

                escaped = None
                try:
                    main()
                except SystemExit:
                    pass
                except Exception as exc:  # noqa: BLE001 -- the failure under test
                    escaped = exc

        self.assertTrue(
            crash_results,
            "log_crash was never reached, or raised on the way -- either way "
            "this fixture is no longer isolating what it claims to",
        )
        self.assertIsNone(
            crash_results[0],
            "log_crash did not fail under this fixture, so these tests never "
            "exercise the deny-still-reaches-stdout path they are about",
        )
        return out.getvalue(), escaped

    def _assert_deny_reached_stdout(self, stdout_text, escaped):
        """Assert a parseable JSON deny decision reached stdout and nothing escaped main()."""
        self.assertIsNone(
            escaped,
            f"main() let {type(escaped).__name__}({escaped}) escape its own "
            f"except clause, so _emit_decision never ran",
        )
        self.assertTrue(
            stdout_text.strip(),
            "the hook exited with nothing on stdout -- Claude Code reads that "
            "as no permission hook at all, not as a denial",
        )
        output = json.loads(stdout_text)
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_json_decode_path_still_puts_a_deny_on_stdout(self):
        """
        Given malformed JSON on stdin and a home directory crash logging
            cannot resolve
        When main()'s `except json.JSONDecodeError` clause calls log_crash and
            log_crash itself fails
        Then a deny decision still reaches STDOUT
        """
        stdout_text, escaped = self._drive_main("not valid json {")
        self._assert_deny_reached_stdout(stdout_text, escaped)

    def test_value_error_path_still_puts_a_deny_on_stdout(self):
        """
        Given valid JSON on stdin missing hook_event_name, and a home
            directory crash logging cannot resolve
        When main()'s `except ValueError` clause calls log_crash and log_crash
            itself fails
        Then a deny decision still reaches STDOUT
        """
        stdout_text, escaped = self._drive_main(
            json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
        )
        self._assert_deny_reached_stdout(stdout_text, escaped)

    def test_unexpected_exception_path_still_puts_a_deny_on_stdout(self):
        """
        Given a governed Bash event whose resolution raises, and a home
            directory crash logging cannot resolve
        When main()'s catch-all `except Exception` clause calls log_crash and
            log_crash itself fails
        Then a deny decision still reaches STDOUT
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }
        config = _fake_config(governed=["Bash"], bash=(["git *"], []))
        stdout_text, escaped = self._drive_main(
            json.dumps(hook_input),
            extra_patches=(
                patch("toolguard.hook.load_configuration", return_value=config),
                patch(
                    "toolguard.hook.resolve_bash_permission_detailed",
                    side_effect=RuntimeError("boom from resolver"),
                ),
            ),
        )
        self._assert_deny_reached_stdout(stdout_text, escaped)


class TestEmitDecisionStdoutFailureFallsBackToExit2(unittest.TestCase):
    """
    _emit_decision is the one place every decision reaches stdout; if that
    write itself fails there is nothing left to deliver, so this falls back
    to sys.exit(2) -- the host's own blocking signal -- with the failure
    reason on stderr.
    """

    def test_stdout_write_failure_exits_2_with_reason_on_stderr(self):
        """
        Given sys.stdout itself raises when written to (e.g. a broken pipe)
        When _emit_decision tries to print the JSON decision
        Then it exits 2 (not 0) and the failure reason lands on stderr
        """

        class _BrokenStdout:
            def write(self, _data):
                raise BrokenPipeError("pipe closed")

            def flush(self):
                pass

        with (
            patch("sys.stdout", _BrokenStdout()),
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
        ):
            with self.assertRaises(SystemExit) as ctx:
                _emit_decision({"hookSpecificOutput": {"permissionDecision": "deny"}})

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("failed to emit decision", mock_stderr.getvalue())

    def test_stdout_flush_failure_exits_2_with_reason_on_stderr(self):
        """
        Given sys.stdout accepts the write but raises on flush() -- the shape
            a real, block-buffered pipe takes when its reader has closed
            (measured on a real subprocess with a closed stdout read-end:
            `print()` returned successfully and the process exited 120,
            outside the try/except, because nothing had flushed the
            buffered write yet)
        When _emit_decision tries to print the JSON decision
        Then it exits 2 (not left to fail open at interpreter shutdown) and
             the failure reason lands on stderr
        """

        class _BufferedBrokenPipeStdout:
            def write(self, _data):
                pass

            def flush(self):
                raise BrokenPipeError("pipe closed")

        with (
            patch("sys.stdout", _BufferedBrokenPipeStdout()),
            patch("sys.stderr", new_callable=StringIO) as mock_stderr,
        ):
            with self.assertRaises(SystemExit) as ctx:
                _emit_decision({"hookSpecificOutput": {"permissionDecision": "deny"}})

        self.assertEqual(ctx.exception.code, 2)
        self.assertIn("failed to emit decision", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
