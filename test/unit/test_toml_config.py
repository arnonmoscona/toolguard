"""Unit tests for TOML configuration support in toolguard."""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.config_validation import (
    KNOWN_SUPPORTED_TOOLS,
    extract_tool_name,
    validate_permissions,
)
from toolguard.error_log import log_warning, log_error
from toolguard.config import _parse_source, discover_config_files, load_config_file
from toolguard.issues import Issue


class TestTomlConfigLoader(unittest.TestCase):
    """Test TOML configuration loading."""

    def test_load_valid_toml_config(self):
        """
        Given a valid TOML config with governed_tools and allow/deny/ask permissions
        When load_config_file reads it as TOML
        Then the parsed dict exposes the governed tools and each permission list
        """
        toml_content = b"""
governed_tools = ["Bash", "Read"]

[permissions]
allow = ["Bash(ls:*)", "Read(/tmp/**)"]
deny = ["Bash(rm -rf:*)"]
ask = ["Bash(alembic:*)"]
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_config_file(filepath, "toml")
            self.assertEqual(config["governed_tools"], ["Bash", "Read"])
            self.assertEqual(
                config["permissions"]["allow"], ["Bash(ls:*)", "Read(/tmp/**)"]
            )
            self.assertEqual(config["permissions"]["deny"], ["Bash(rm -rf:*)"])
            self.assertEqual(config["permissions"]["ask"], ["Bash(alembic:*)"])
        finally:
            filepath.unlink()

    def test_load_toml_with_missing_optional_sections(self):
        """
        Given a TOML config that defines only governed_tools
        When load_config_file reads it as TOML
        Then governed_tools is parsed and no permissions key is present
        """
        toml_content = b"""
governed_tools = ["Bash"]
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_config_file(filepath, "toml")
            self.assertEqual(config["governed_tools"], ["Bash"])
            self.assertNotIn("permissions", config)
        finally:
            filepath.unlink()

    def test_load_toml_with_additional_supported_tools(self):
        """
        Given a TOML config declaring additional_supported_tools
        When load_config_file reads it as TOML
        Then that list is exposed in the parsed config
        """
        toml_content = b"""
governed_tools = ["Bash", "mcp__custom__tool"]
additional_supported_tools = ["mcp__custom__tool"]

[permissions]
allow = ["Bash(ls:*)", "mcp__custom__tool(*)"]
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_config_file(filepath, "toml")
            self.assertEqual(
                config["additional_supported_tools"], ["mcp__custom__tool"]
            )
        finally:
            filepath.unlink()

    def test_load_invalid_toml_raises_error(self):
        """
        Given a file containing malformed TOML
        When load_config_file reads it as TOML
        Then an exception (TOML decode error) is raised
        """
        toml_content = b"""
invalid toml [
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            with self.assertRaises(Exception):  # tomllib.TOMLDecodeError
                load_config_file(filepath, "toml")
        finally:
            filepath.unlink()

    def test_load_nonexistent_file_raises_error(self):
        """
        Given a path to a TOML file that does not exist
        When load_config_file reads it as TOML
        Then a FileNotFoundError is raised
        """
        with self.assertRaises(FileNotFoundError):
            load_config_file(Path("/nonexistent/file.toml"), "toml")


class TestParseSourceTomlDiagnostics(unittest.TestCase):
    """Test _parse_source()'s TOML-failure warning message."""

    def test_multiline_structured_entry_gets_actionable_message(self):
        """
        Given a toolguard_hook.toml whose only content is a structured entry
            written across multiple physical lines (not valid TOML 1.0)
        When _parse_source() parses it
        Then it returns None (fail-open, unchanged) and prints a message
            naming the file, the offending line, and the single-line fix --
            not tomllib's own cryptic "Invalid initial character..." wording
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(
                "[permissions]\n"
                "allow = [\n"
                "  {\n"
                '    match = "Bash(git status)",\n'
                "  },\n"
                "]\n"
            )
            with patch("sys.stderr", new_callable=io.StringIO) as captured:
                result = _parse_source(path, "toml")

        self.assertIsNone(result)
        message = captured.getvalue()
        self.assertIn(str(path), message)
        self.assertIn("line 3", message)
        self.assertIn("single", message)
        self.assertNotIn("Invalid initial character", message)

    def test_unrelated_toml_error_keeps_generic_tomllib_message(self):
        """
        Given a toolguard_hook.toml with a genuinely malformed TOML syntax
            error that has NOTHING to do with a multi-line structured entry
            (an unterminated array)
        When _parse_source() parses it
        Then it returns None (fail-open, unchanged) and the printed message
            is tomllib's own original message, unmodified -- detection must
            not misattribute an unrelated error to the multi-line cause
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text("[permissions]\nallow = [\n")
            with patch("sys.stderr", new_callable=io.StringIO) as captured:
                result = _parse_source(path, "toml")

        self.assertIsNone(result)
        message = captured.getvalue()
        self.assertIn(str(path), message)
        self.assertNotIn("single", message)


class TestLoadConfigFileCacheInvalidation(unittest.TestCase):
    """Test load_config_file()'s stat-keyed parse cache against a same-mtime rewrite."""

    def test_rewrite_within_same_mtime_tick_is_not_served_stale(self):
        """
        Given a TOML file is read once, then rewritten with new content while its
            st_mtime_ns happens to be unchanged (simulating a same-tick rewrite)
        When load_config_file reads it again
        Then the SECOND read returns the NEW content, not a stale cached parse
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toolguard_hook.toml"
            path.write_text('governed_tools = ["Bash"]\n')

            first = load_config_file(path, "toml")
            self.assertNotIn("permissions", first)

            original_mtime_ns = path.stat().st_mtime_ns
            new_content = (
                'governed_tools = ["Bash"]\n\n[permissions]\nallow = ["Bash(ls:*)"]\n'
            )
            path.write_text(new_content)
            os.utime(path, ns=(original_mtime_ns, original_mtime_ns))
            self.assertEqual(path.stat().st_mtime_ns, original_mtime_ns)

            second = load_config_file(path, "toml")
            self.assertIn("permissions", second)
            self.assertEqual(second["permissions"]["allow"], ["Bash(ls:*)"])


class TestConfigDiscoveryTomlPrecedence(ConfigIsolationMixin, unittest.TestCase):
    """Test that TOML files take precedence over JSON."""

    def test_toml_takes_precedence_over_json(self):
        """
        Given a project with both toolguard_hook.toml and toolguard_hook.json
        When discover_config_files runs
        Then the TOML hook file is included and the JSON one is excluded
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "toolguard_hook.toml").write_text('governed_tools = ["Bash"]')
        (claude_dir / "toolguard_hook.json").write_text('{"governed_tools": ["Read"]}')

        configs = discover_config_files()

        hook_configs = [
            (p, t, f)
            for p, t, f in configs
            if t == "toolguard_hook" and "local" not in p.name
        ]

        self.assertTrue(any(f == "toml" for _, _, f in hook_configs))
        hook_paths = [str(p) for p, _, _ in hook_configs]
        self.assertIn(str(claude_dir / "toolguard_hook.toml"), hook_paths)
        self.assertNotIn(str(claude_dir / "toolguard_hook.json"), hook_paths)

    def test_json_used_when_no_toml(self):
        """
        Given a project with only a toolguard_hook.json (no TOML)
        When discover_config_files runs
        Then the JSON hook file is included
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()

        (claude_dir / "toolguard_hook.json").write_text('{"governed_tools": ["Bash"]}')

        configs = discover_config_files()

        hook_configs = [
            (p, t, f)
            for p, t, f in configs
            if t == "toolguard_hook" and "local" not in p.name
        ]

        self.assertTrue(any(f == "json" for _, _, f in hook_configs))


class TestExtractToolName(unittest.TestCase):
    """Test extraction of tool names from permission strings."""

    def test_extract_bash_tool(self):
        """
        Given Bash permission strings with parenthesized arguments
        When extract_tool_name parses them
        Then it returns 'Bash'
        """
        self.assertEqual(extract_tool_name("Bash(ls:*)"), "Bash")
        self.assertEqual(extract_tool_name("Bash(git status)"), "Bash")

    def test_extract_read_tool(self):
        """
        Given a Read permission string with a path argument
        When extract_tool_name parses it
        Then it returns 'Read'
        """
        self.assertEqual(extract_tool_name("Read(/tmp/**)"), "Read")

    def test_extract_write_tool(self):
        """
        Given a Write permission string with a path argument
        When extract_tool_name parses it
        Then it returns 'Write'
        """
        self.assertEqual(extract_tool_name("Write(~/projects/**)"), "Write")

    def test_extract_tool_without_parens(self):
        """
        Given permission strings with no parentheses
        When extract_tool_name parses them
        Then the whole string is returned as the tool name
        """
        self.assertEqual(extract_tool_name("WebSearch"), "WebSearch")
        self.assertEqual(
            extract_tool_name("mcp__basic-memory__write_note"),
            "mcp__basic-memory__write_note",
        )

    def test_extract_mcp_tool(self):
        """
        Given an MCP tool permission string with no parentheses
        When extract_tool_name parses it
        Then the full MCP tool name is returned
        """
        self.assertEqual(
            extract_tool_name("mcp__jetbrains__execute_terminal_command"),
            "mcp__jetbrains__execute_terminal_command",
        )


class TestValidatePermissions(unittest.TestCase):
    """Test permission validation."""

    def test_validate_no_warnings_for_valid_config(self):
        """
        Given a config whose permissions reference only governed, supported tools
        When validate_permissions runs
        Then it produces an empty tuple of issues
        """
        config = {
            "governed_tools": ["Bash", "Read"],
            "permissions": {
                "allow": ["Bash(ls:*)", "Read(/tmp/**)"],
                "deny": ["Bash(rm -rf:*)"],
            },
        }
        issues = validate_permissions(config)
        self.assertEqual(issues, ())

    def test_warning_for_unsupported_tool(self):
        """
        Given permissions that reference unsupported tools (WebSearch, WebFetch)
        When validate_permissions runs
        Then Issues are produced naming each unsupported tool
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": ["Bash(ls:*)", "WebSearch", "WebFetch(domain:example.com)"],
            },
        }
        issues = validate_permissions(config)

        messages = [issue.message for issue in issues]
        self.assertTrue(any("WebSearch" in msg for msg in messages))
        self.assertTrue(any("WebFetch" in msg for msg in messages))

    def test_warning_for_ungoverned_tool(self):
        """
        Given a permission for Read while only Bash is in governed_tools
        When validate_permissions runs
        Then an Issue notes that Read is not in governed_tools
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": ["Bash(ls:*)", "Read(/tmp/**)"],
            },
        }
        issues = validate_permissions(config)

        messages = [issue.message for issue in issues]
        self.assertTrue(
            any("Read" in msg and "governed_tools" in msg for msg in messages)
        )

    def test_additional_supported_tools_no_warning(self):
        """
        Given a custom tool declared in additional_supported_tools and governed
        When validate_permissions runs on permissions using it
        Then no issues are produced
        """
        config = {
            "governed_tools": ["Bash", "mcp__custom__tool"],
            "additional_supported_tools": ["mcp__custom__tool"],
            "permissions": {
                "allow": ["Bash(ls:*)", "mcp__custom__tool(*)"],
            },
        }
        issues = validate_permissions(config)

        self.assertEqual(issues, ())

    def test_warnings_include_corrective_steps(self):
        """
        Given a config that produces at least one issue
        When validate_permissions runs
        Then every Issue has a non-empty corrective_steps field
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": ["WebSearch"],
            },
        }
        issues = validate_permissions(config)

        self.assertTrue(len(issues) > 0)
        for issue in issues:
            self.assertIsInstance(issue, Issue)
            self.assertTrue(len(issue.corrective_steps) > 0)

    def test_empty_config_no_warnings(self):
        """
        Given an empty config dict
        When validate_permissions runs
        Then it produces an empty tuple of issues
        """
        config = {}
        issues = validate_permissions(config)
        self.assertEqual(issues, ())

    def test_structured_entry_unsupported_tool_is_flagged(self):
        """
        Given an allow list holding a structured entry for an unsupported tool
        When validate_permissions runs
        Then it flags the unsupported tool exactly as it would for a plain string

        This is the bug fix: previously the 'isinstance(perm, str)' filter
        silently skipped structured entries, so an unsupported tool named
        only inside a {match = ...} table was never reported.
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [{"match": "WebSearch()", "additionalContext": "why"}],
            },
        }
        issues = validate_permissions(config)
        self.assertTrue(any("WebSearch" in issue.message for issue in issues))

    def test_structured_entry_ungoverned_tool_is_flagged(self):
        """
        Given a structured entry for a supported tool absent from governed_tools
        When validate_permissions runs
        Then it flags the tool as supported-but-ungoverned, same as a plain string
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [{"match": "Read(/tmp/**)"}],
            },
        }
        issues = validate_permissions(config)
        self.assertTrue(
            any(
                "Read" in issue.message and "governed_tools" in issue.message
                for issue in issues
            )
        )

    def test_malformed_dict_entry_produces_error_issue(self):
        """
        Given a structured entry dict with no 'match' key
        When validate_permissions runs
        Then it produces an error-level Issue rather than vanishing
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [{"additionalContext": "no match key here"}],
            },
        }
        issues = validate_permissions(config)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any(issue.level == "error" for issue in issues))

    def test_bare_int_entry_produces_error_issue(self):
        """
        Given a permission entry that is a bare int (not a str or dict)
        When validate_permissions runs
        Then it produces an error-level Issue rather than vanishing
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [42],
            },
        }
        issues = validate_permissions(config)
        self.assertTrue(len(issues) > 0)
        self.assertTrue(any(issue.level == "error" for issue in issues))

    def test_duplicate_malformed_entries_deduplicated(self):
        """
        Given the exact same malformed entry repeated twice in an allow list
        When validate_permissions runs
        Then only one Issue with that message is produced, not two
        """
        malformed = {"additionalContext": "still no match key"}
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [malformed, dict(malformed)],
            },
        }
        issues = validate_permissions(config)
        error_issues = [issue for issue in issues if issue.level == "error"]
        self.assertEqual(len(error_issues), 1)

    def test_unknown_enrichment_key_warns_without_suppressing_tool_check(self):
        """
        Given a structured entry with an unknown enrichment key naming an
        unsupported tool
        When validate_permissions runs
        Then it produces a warning Issue about the unknown key AND still
        flags the unsupported tool -- the unknown key must not swallow the
        entry's other checks
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [{"match": "WebSearch()", "totallyMadeUpKey": "x"}],
            },
        }
        issues = validate_permissions(config)
        self.assertTrue(any("totallyMadeUpKey" in issue.message for issue in issues))
        self.assertTrue(any("WebSearch" in issue.message for issue in issues))

    def test_valid_structured_entry_governed_supported_tool_no_issue(self):
        """
        Given a structured entry for a governed, supported tool with no
        unknown enrichment keys
        When validate_permissions runs
        Then no issues are produced
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": [{"match": "Bash(git status)"}],
            },
        }
        issues = validate_permissions(config)
        self.assertEqual(issues, ())

    def test_returned_issues_are_issue_instances_not_dicts(self):
        """
        Given a config that produces issues from both plain and structured entries
        When validate_permissions runs
        Then the return value is a tuple of Issue instances, not dicts
        """
        config = {
            "governed_tools": ["Bash"],
            "permissions": {
                "allow": ["WebSearch", {"match": "WebFetch()"}],
            },
        }
        issues = validate_permissions(config)
        self.assertIsInstance(issues, tuple)
        self.assertTrue(len(issues) > 0)
        for issue in issues:
            self.assertIsInstance(issue, Issue)

    def test_known_supported_tools_constant(self):
        """
        Given the KNOWN_SUPPORTED_TOOLS constant
        When its membership is inspected
        Then it contains Bash, Read, Write, Edit, and the JetBrains terminal tool
        """
        self.assertIn("Bash", KNOWN_SUPPORTED_TOOLS)
        self.assertIn("Read", KNOWN_SUPPORTED_TOOLS)
        self.assertIn("Write", KNOWN_SUPPORTED_TOOLS)
        self.assertIn("Edit", KNOWN_SUPPORTED_TOOLS)
        self.assertIn("mcp__jetbrains__execute_terminal_command", KNOWN_SUPPORTED_TOOLS)


class TestErrorLog(unittest.TestCase):
    """Test error/warning logging functionality."""

    def test_warning_log_file_created(self):
        """
        Given a log directory
        When log_warning writes a warning
        Then exactly one toolguard-warning-*.md file is created (and no error file)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning("Test warning", "Fix by doing X", log_dir)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertTrue(warning_files[0].name.startswith("toolguard-warning-"))
            self.assertTrue(warning_files[0].name.endswith(".md"))

            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])

    def test_warning_log_format(self):
        """
        Given a log directory
        When log_warning writes a message and corrective steps
        Then the entry contains the WARNING label, the message, the steps, and the Message/Corrective Steps fields
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning("Test warning message", "Do this to fix", log_dir)

            log_files = list(log_dir.glob("toolguard-warning-*.md"))
            content = log_files[0].read_text()

            self.assertIn("WARNING", content)
            self.assertIn("Test warning message", content)
            self.assertIn("Do this to fix", content)
            self.assertIn("**Message**:", content)
            self.assertIn("**Corrective Steps**:", content)

    def test_error_log_includes_timestamp(self):
        """
        Given a log directory
        When log_error writes an entry
        Then a toolguard-error-*.md entry is created with a YYYY-MM-DD HH:MM:SS timestamp
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_error("Test error", "Fix it", log_dir)

            log_files = list(log_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(log_files), 1)
            content = log_files[0].read_text()

            import re

            timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
            self.assertTrue(re.search(timestamp_pattern, content))

    def test_warning_and_error_go_to_separate_files(self):
        """
        Given a log directory
        When a warning and then an error are logged
        Then each appears in its OWN per-concern stream file (warning vs error),
             never sharing a single file
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning("First warning", "Step 1", log_dir)
            log_error("Second error", "Step 2", log_dir)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            error_files = list(log_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertEqual(len(error_files), 1)

            warning_content = warning_files[0].read_text()
            error_content = error_files[0].read_text()

            self.assertIn("First warning", warning_content)
            self.assertIn("WARNING", warning_content)
            self.assertNotIn("Second error", warning_content)

            self.assertIn("Second error", error_content)
            self.assertIn("ERROR", error_content)
            self.assertNotIn("First warning", error_content)


if __name__ == "__main__":
    unittest.main()
