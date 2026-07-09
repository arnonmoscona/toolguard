"""
Unit tests for toolguard hook functionality.

Tests hook behavior with different tool names and governed tools configuration.
Includes tests for file path tools (Read, Write, Edit) with GLOB pattern matching.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    ResolvedDecision,
    TakeoverConfig,
    TakeoverEnabledConflict,
)
from toolguard.hook import (
    FILE_PATH_TOOLS,
    _decide_file_path_at_level_detailed,
    _log_allowed_command,
    _parse_compound_match_details,
    create_hook_output,
    load_file_path_patterns,
    main,
    parse_hook_input,
)

_NO_TAKEOVER = TakeoverConfig(False, (), (), "deny")


def check_file_path_permission(
    file_path, allow_patterns, deny_patterns, extended_syntax=True
):
    """
    Evaluate a file path against flat allow/deny pattern lists, returning (decision, reason).

    Thin test adapter over the live single-level resolver
    :func:`toolguard.hook._decide_file_path_at_level_detailed`. It preserves the
    decision semantics the removed ``check_file_path_permission`` had (deny-first,
    glob/regex/native prefixes, tilde expansion, default-deny when nothing matches)
    so the existing file-path test intents carry over unchanged. An empty
    ``Configuration`` is supplied because every pattern these tests use is absolute
    or ``~``-anchored, so project-root anchoring is a no-op.
    """
    config = Configuration(layers=())
    result = _decide_file_path_at_level_detailed(
        file_path, allow_patterns, deny_patterns, config, extended_syntax
    )
    if result is None:
        return "deny", "Path does not match any allow patterns"
    decision, reason, _matched = result
    return decision, reason


def _fake_config(
    governed=("Bash",),
    bash=((), ()),
    file_patterns=None,
    takeover=_NO_TAKEOVER,
):
    """
    Build a stand-in Configuration for hook tests.

    Patching ``toolguard.hook.load_configuration`` with this lets the tests
    assert hook OUTCOMES (allow/deny decisions, governed-tool gating, file-path
    gating) without touching files -- the same intents the old white-box tests
    pinned, re-expressed against the public Configuration surface.

    Args:
        governed: Governed tool names the config reports.
        bash: (allow, deny) tuple returned by ``bash_permissions()``.
        file_patterns: Optional mapping of tool name -> (allow, deny) returned by
            ``allow_deny_for()``. Missing tools resolve to empty patterns.
        takeover: TakeoverConfig returned by ``takeover_mode()``.

    Returns:
        An object exposing the Configuration accessors that ``main`` consumes.
    """
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
            # The fake configures no [hard_deny] pool, so hard-deny never fires
            # here; this keeps the double in sync with the Configuration surface
            # the hook now consumes (TOO-8 Phase 3).
            return (), ()

        def resolve_config_path(self_inner, raw_path):
            # No project root in the fake: relative paths returned unchanged.
            return raw_path

        def resolve_permission_detailed(self_inner, tool_name, decide_detailed):
            # API-sync with Configuration.resolve_permission_detailed (TOO-8
            # Phase 4, TOO-15) -- the sole cascade entry point the hook now
            # calls. The fake models a single hierarchy level per tool with no
            # provenance, so no override (conflict) is ever produced here.
            allow, deny = _patterns_for(tool_name)
            if allow or deny:
                # API-sync with Configuration.resolve_permission_detailed, whose
                # callback now receives (allow, deny, ask); the fake models no ask.
                result = decide_detailed(tuple(allow), tuple(deny), ())
                if result is not None:
                    decision, reason, _matched = result
                    return ResolvedDecision(decision, reason, None, None)
                # Rules ARE configured for this tool but none matched this
                # specific command/path (TOO-15 case 4): default no_match_fallback
                # is 'deny'. The fake does not model a configurable warn_deny
                # fallback -- tests that need that exercise a real Configuration.
                return ResolvedDecision(
                    "deny", "Command does not match any allow patterns", None, None
                )
            # No allow/deny configured at all for this tool anywhere (and the
            # fake models no hard_deny/ask patterns either): TOO-15 case 3 --
            # the tool is entirely unconfigured, so it ALWAYS resolves to 'ask'
            # regardless of no_match_fallback (a fresh install must not be
            # bricked).
            return ResolvedDecision(
                "ask",
                f"No {tool_name} permission rules configured at any level; "
                f"defaulting to 'ask'",
                None,
                None,
            )

        def describe_levels(self_inner):
            # API-sync: the fake exposes no real sources.
            return ()

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
                        # Should be allowed because 'git status' matches 'git *'
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
                        # Should be allowed because tool is governed and command matches
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
                    # Should be allowed because tool is not governed
                    self.assertEqual(
                        output["hookSpecificOutput"]["permissionDecision"], "allow"
                    )
                    # Reason should mention it's not governed
                    self.assertIn(
                        "Not a governed tool",
                        output["hookSpecificOutput"]["permissionDecisionReason"],
                    )


class TestTakeoverEnabledConflictWiring(unittest.TestCase):
    """End-to-end hook wiring for a cross-level takeover_mode.enabled conflict (TOO-8 Phase 5)."""

    def setUp(self):
        """Reset the once-per-session takeover-conflict flag before each test."""
        import toolguard.hook as hook_module

        hook_module._takeover_conflict_logged = False

    def test_enabled_conflict_logs_and_warns_failsafe_off(self):
        """
        Given a config whose takeover_mode() reports an enabled conflict (fail-safe OFF)
        When main() processes a governed Bash command
        Then a conflict-log entry is written, a once-per-session takeover warning is issued,
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

        # A conflict-log entry was written citing the disagreement and fail-safe OFF.
        mock_conflict.assert_called_once()
        conflict_message = mock_conflict.call_args[0][0]
        self.assertIn("conflicting values", conflict_message)
        self.assertIn("DISABLED", conflict_message)
        # A once-per-session takeover/config warning was issued.
        mock_warn.assert_called_once()
        # Fail-safe path: the command is still evaluated normally (allowed by 'git *').
        output = json.loads(mock_stdout.getvalue())
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")

    def test_enabled_conflict_logged_once_per_session(self):
        """
        Given the takeover enabled-conflict path has already fired this session
        When main() processes another governed command in the same session
        Then no additional conflict-log entry or takeover warning is emitted (once-per-session)
        """
        import toolguard.hook as hook_module

        hook_module._takeover_conflict_logged = True

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
            with patch("sys.stdout", new_callable=StringIO):
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

        mock_conflict.assert_not_called()
        mock_warn.assert_not_called()

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
            # Missing tool_input
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
        Given an allow decision and a reason string
        When create_hook_output() builds the response
        Then the hookSpecificOutput carries decision 'allow' and the given reason
        """
        output = create_hook_output("allow", "Command matches allow pattern")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "allow")
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecisionReason"],
            "Command matches allow pattern",
        )

    def test_create_deny_output(self):
        """
        Given a deny decision and a reason string
        When create_hook_output() builds the response
        Then the hookSpecificOutput carries decision 'deny' and the given reason
        """
        output = create_hook_output("deny", "Command matches deny pattern")
        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(
            output["hookSpecificOutput"]["permissionDecisionReason"],
            "Command matches deny pattern",
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

        # Should match nested path
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

        # Single * should NOT match nested path
        decision, reason = check_file_path_permission(
            "/tmp/subdir/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

    def test_deny_takes_precedence(self):
        """
        Given an allow pattern that matches and a deny pattern that also matches
        When check_file_path_permission evaluates the path
        Then the decision is 'deny' because deny is checked first
        """
        allow_patterns = ["/tmp/**"]
        deny_patterns = ["/tmp/secret/**"]

        # Should be denied even though allow pattern matches
        decision, reason = check_file_path_permission(
            "/tmp/secret/password.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

    def test_no_match_returns_deny(self):
        """
        Given an allow pattern '/home/**' that does not match the target path
        When check_file_path_permission evaluates '/tmp/file.txt'
        Then the decision is 'deny' and the reason says it does not match
        """
        allow_patterns = ["/home/**"]
        deny_patterns = []

        decision, reason = check_file_path_permission(
            "/tmp/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")
        self.assertIn("does not match", reason)

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

        # Test with expanded path matching tilde pattern
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

        # Should match .txt files
        decision, reason = check_file_path_permission(
            "/tmp/docs/readme.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "allow")

        # Should not match .py files
        decision, reason = check_file_path_permission(
            "/tmp/src/main.py", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")


class TestCheckFilePathPermissionExtendedSyntax(unittest.TestCase):
    """Test that extended syntax prefixes work inside tool wrappers for file path tools.

    These patterns arrive here already stripped of the Write(...)/Read(...)/Edit(...)
    wrapper by load_file_path_patterns, so they look like "[regex]..." or "[glob]..."
    or "[native]...".
    """

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

        # Single * should NOT match nested path
        decision, _ = check_file_path_permission(
            "/tmp/sub/file.txt", allow_patterns, deny_patterns
        )
        self.assertEqual(decision, "deny")

        # Same path with ** should match
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

        # With extended syntax: regex matches
        decision, _ = check_file_path_permission(
            "/tmp/file.txt", allow_patterns, deny_patterns, extended_syntax=True
        )
        self.assertEqual(decision, "allow")

        # Without extended syntax: [regex]... treated as glob literal, won't match
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

        # Pass the config in directly so the adapter routes through the public
        # Configuration surface rather than opening files.
        allow, deny = load_file_path_patterns("Read", config=config)

        # Should only get Read patterns, not Write or Bash
        self.assertEqual(len(allow), 2)
        self.assertIn("/tmp/**", allow)
        self.assertIn("/home/**", allow)

        # Should get deny patterns for Read
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

        # Should only get Write patterns
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

    def test_write_tool_denied(self):
        """
        Given Write is governed and patterns only allow '/tmp/**'
        When main() processes a Write to '/etc/passwd'
        Then the decision is 'deny'
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
                                "deny",
                            )

    def test_edit_tool_with_deny_pattern(self):
        """
        Given Edit is governed with allow '/tmp/**' and deny '/tmp/secret/**'
        When main() processes an Edit of '/tmp/secret/config.txt'
        Then the decision is 'deny' and the reason cites the deny pattern
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
                                "deny pattern",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_read_no_file_path_denied(self):
        """
        Given Read is governed but the tool input has no file_path
        When main() processes the invocation
        Then the decision is 'deny' and the reason mentions file_path
        """
        hook_input = {
            "tool_name": "Read",
            "tool_input": {},  # Missing file_path
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
                                "file_path",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_read_no_allow_patterns_asks(self):
        """
        Given Read is governed but NO permission rules are configured at all
            (no allow, deny, ask, or hard_deny anywhere)
        When main() processes a Read of '/tmp/test.txt'
        Then the decision is 'ask' (TOO-15: an entirely unconfigured tool must
             not brick a fresh install by denying everything) and the reason
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
                    ):  # No patterns
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
        Then the decision is 'ask' (TOO-15: an entirely unconfigured tool must
             not brick a fresh install by denying everything)
        """
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }

        config = _fake_config(governed=["Bash"])  # bash defaults to ((), ())
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
    """
    TOO-15 end-to-end: main() driven with a REAL Configuration (not the hand
    rolled _FakeConfig double), so the actual centralized no_match_fallback
    resolution in toolguard.config/toolguard.resolve is exercised exactly as
    it runs in production. Covers: warn_deny actually ALLOWS (the bug fix),
    and takeover mode with an explicit 'deny' fallback stays fail-closed.
    """

    @staticmethod
    def _hook_layer(content):
        """Build a single project-level toolguard_hook ConfigLayer."""
        return ConfigLayer(
            Provenance(
                "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml"), 0
            ),
            MappingProxyType(content),
        )

    def test_bash_warn_deny_fallback_allows_via_main(self):
        """
        Given a real Configuration governing Bash, allowing only 'git *', with
            the top-level no_match_fallback set to 'warn_deny'
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is 'allow' (the fix: warn_deny must actually allow,
             not just reword a deny) and the reason mentions warn_deny
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
                                "warn_deny",
                                output["hookSpecificOutput"][
                                    "permissionDecisionReason"
                                ],
                            )

    def test_bash_takeover_enabled_deny_fallback_still_fails_closed_via_main(self):
        """
        Given a real Configuration with takeover_mode enabled and an explicit
            no_match_fallback='deny', allowing only 'git *' for Bash
        When main() processes a 'whoami' Bash invocation (matches no rule)
        Then the decision is still 'deny' (takeover mode does not weaken the
             default fail-closed fallback)
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


class TestStartupValidation(unittest.TestCase):
    """Test startup validation only validates toolguard_hook files."""

    def test_validation_ignores_settings_local_json(self):
        """
        Given a native settings.local.json listing unsupported tools alongside a valid toolguard_hook config
        When _run_startup_validation runs and delegates to Configuration.validation_issues()
        Then no error log warns about the native-only tools (WebSearch, WebFetch, mcp__unknown__tool)

        Only toolguard_hook.toml/json files should be validated; settings.local.json
        holds Claude's native permission format which toolguard does not understand,
        so its tools must never appear in the logged warnings.
        """
        import tempfile

        import toolguard.hook as hook_module
        from toolguard.config import Configuration

        # Reset validation flag for this test
        original_flag = hook_module._validation_done
        hook_module._validation_done = False

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir) / "project"
                project_dir.mkdir()
                (project_dir / ".git").mkdir()
                claude_dir = project_dir / ".claude"
                claude_dir.mkdir()
                logs_dir = project_dir / "logs"
                logs_dir.mkdir()

                # Native settings.local.json with unsupported tools (should be IGNORED)
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
                # toolguard_hook with valid config (should be validated, no issues)
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
                            "permissions": {"allow": ["Bash(ls:*)", "Read(/tmp/**)"]},
                        }
                    ),
                )
                config = Configuration(layers=(native_layer, hook_layer))

                env_config = {"log_dir": logs_dir}

                # Reset flag again before calling
                hook_module._validation_done = False

                from toolguard.hook import _run_startup_validation

                _run_startup_validation(env_config, str(project_dir), config)

                # Check log file - should NOT have warnings for WebSearch, WebFetch
                # because those are in settings.local.json which is ignored
                log_files = list(logs_dir.glob("toolguard-error-*.md"))

                if log_files:
                    content = log_files[0].read_text()
                    # These tools are in settings.local.json which should be ignored
                    self.assertNotIn("WebSearch", content)
                    self.assertNotIn("WebFetch", content)
                    self.assertNotIn("mcp__unknown__tool", content)
                # If no log file exists, that's also correct (no warnings generated)

        finally:
            # Restore original flag
            hook_module._validation_done = original_flag

    def test_validation_logs_issues_from_config(self):
        """
        Given a config whose validation_issues() returns one warning Issue
        When _run_startup_validation runs
        Then log_warning is called once with that issue's message and corrective steps
        """
        from toolguard.config import Issue
        import toolguard.hook as hook_module

        original_flag = hook_module._validation_done
        hook_module._validation_done = False
        try:
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
        finally:
            hook_module._validation_done = original_flag

    def test_validation_loads_config_when_none(self):
        """
        Given no config argument is passed to _run_startup_validation
        When it runs for a given directory
        Then it calls load_configuration with that directory to obtain one itself
        """
        import toolguard.hook as hook_module

        original_flag = hook_module._validation_done
        hook_module._validation_done = False
        try:

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
        finally:
            hook_module._validation_done = original_flag


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


class TestParseCompoundMatchDetails(unittest.TestCase):
    """Test parsing of compound match details from reason strings."""

    def test_parse_two_subcommands(self):
        """
        Given a compound allow reason listing two sub-command -> rule mappings
        When _parse_compound_match_details parses it
        Then it returns the two (command, rule) pairs in order
        """
        reason = "All 2 sub-commands allowed: [git status -> git *, git log -> git *]"
        result = _parse_compound_match_details(reason)
        self.assertEqual(result, [("git status", "git *"), ("git log", "git *")])

    def test_parse_three_subcommands(self):
        """
        Given a compound allow reason listing three sub-command -> rule mappings
        When _parse_compound_match_details parses it
        Then it returns all three (command, rule) pairs in order
        """
        reason = "All 3 sub-commands allowed: [git status -> git *, cat file -> cat *, grep pattern -> grep *]"
        result = _parse_compound_match_details(reason)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0], ("git status", "git *"))
        self.assertEqual(result[1], ("cat file", "cat *"))
        self.assertEqual(result[2], ("grep pattern", "grep *"))

    def test_non_compound_reason_returns_none(self):
        """
        Given a simple (non-compound) command allow reason
        When _parse_compound_match_details parses it
        Then it returns None
        """
        reason = "Command matches allow pattern: git *"
        result = _parse_compound_match_details(reason)
        self.assertIsNone(result)

    def test_simple_allow_reason_returns_none(self):
        """
        Given a simple path-match allow reason
        When _parse_compound_match_details parses it
        Then it returns None
        """
        reason = "Path matches allow pattern: /tmp/**"
        result = _parse_compound_match_details(reason)
        self.assertIsNone(result)


class TestLogAllowedCommand(unittest.TestCase):
    """Test the _log_allowed_command helper function."""

    @patch("toolguard.hook.log_command")
    def test_simple_command_logs_matched_rule(self, mock_log):
        """
        Given a simple allowed command and its single-rule allow reason
        When _log_allowed_command runs
        Then log_command is called once with status 'executed' and the matched rule
        """
        _log_allowed_command(
            "git status", "Command matches allow pattern: git *", "main", {}
        )
        mock_log.assert_called_once_with(
            "git status", "executed", matched_rule="git *", extra_info="main", config={}
        )

    @patch("toolguard.hook.log_command")
    def test_compound_command_logs_per_subcommand(self, mock_log):
        """
        Given a compound allowed command with a two-sub-command allow reason
        When _log_allowed_command runs
        Then log_command is called once per sub-command with its own matched rule
        """
        reason = "All 2 sub-commands allowed: [git status -> git *, git log -> git *]"
        _log_allowed_command("git status && git log", reason, "main", {})
        self.assertEqual(mock_log.call_count, 2)
        mock_log.assert_any_call(
            "git status", "executed", matched_rule="git *", extra_info="main", config={}
        )
        mock_log.assert_any_call(
            "git log", "executed", matched_rule="git *", extra_info="main", config={}
        )

    @patch("toolguard.hook.log_command")
    def test_compound_three_commands(self, mock_log):
        """
        Given a compound allowed command with a three-sub-command allow reason
        When _log_allowed_command runs
        Then log_command is called three times, once per sub-command with its matched rule and agent
        """
        reason = "All 3 sub-commands allowed: [git status -> git *, cat file -> cat *, grep pat -> grep *]"
        _log_allowed_command(
            "git status && cat file | grep pat", reason, "sub-agent", {}
        )
        self.assertEqual(mock_log.call_count, 3)
        mock_log.assert_any_call(
            "git status",
            "executed",
            matched_rule="git *",
            extra_info="sub-agent",
            config={},
        )
        mock_log.assert_any_call(
            "cat file",
            "executed",
            matched_rule="cat *",
            extra_info="sub-agent",
            config={},
        )
        mock_log.assert_any_call(
            "grep pat",
            "executed",
            matched_rule="grep *",
            extra_info="sub-agent",
            config={},
        )


class TestHookArgparseAndIsatty(unittest.TestCase):
    """
    Tests for the argparse --help flag and the interactive (TTY) guard added to
    hook.main (TOO-16 Change 2+3).
    """

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
        stdin_mock = StringIO("")  # empty -- would cause a parse error if read

        with (
            patch("sys.stdin", stdin_mock),
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stderr", err),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()

        self.assertEqual(ctx.exception.code, 0)
        # A meaningful explanation should appear in stderr
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


if __name__ == "__main__":
    unittest.main()
