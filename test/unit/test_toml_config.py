"""Unit tests for TOML configuration support in toolguard."""

import io
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard import config as config_module
from toolguard.config_validation import (
    KNOWN_SUPPORTED_TOOLS,
    extract_tool_name,
    validate_permissions,
)
from toolguard.error_log import log_warning, log_error
from toolguard.config import (
    _parse_source,
    discover_config_files,
    load_config_file,
    load_configuration,
)
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
        Then tomllib.TOMLDecodeError specifically is raised -- not merely
            "some exception", which a typo in the call would also satisfy
        """
        toml_content = b"""
invalid toml [
"""
        with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            with self.assertRaises(tomllib.TOMLDecodeError):
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

    @staticmethod
    def _warning_line(captured: io.StringIO) -> str:
        """
        The single ``[WARNING] ...`` line from captured stderr.

        Asserting against the whole buffer cannot tell the warning line from
        the ``Corrective steps:`` line that follows it -- both carry the
        path, so a routing change that sent only the warning elsewhere left
        the old whole-buffer assertions passing.
        """
        lines = [
            ln for ln in captured.getvalue().splitlines() if ln.startswith("[WARNING]")
        ]
        assert len(lines) == 1, f"expected exactly one [WARNING] line, got {lines!r}"
        return lines[0]

    def test_multiline_structured_entry_gets_actionable_message(self):
        """
        Given a toolguard_hook.toml whose only content is a structured entry
            written across multiple physical lines (not valid TOML 1.0)
        When _parse_source() parses it
        Then it returns None (the file is skipped, not recorded as a parse
            failure) and the [WARNING] line names the file, the offending
            line, and the single-line fix -- not tomllib's own cryptic
            "Invalid initial character..." wording
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
        message = self._warning_line(captured)
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
        Then it returns None and the [WARNING] line carries tomllib's own
            message verbatim inside the "Failed to load <path>: ..." wrapper
            -- detection must neither misattribute this to the multi-line
            cause nor substitute some other wording of its own
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            source = "[permissions]\nallow = [\n"
            path.write_text(source)
            try:
                tomllib.loads(source)
            except tomllib.TOMLDecodeError as exc:
                tomllib_message = str(exc)
            else:  # pragma: no cover - the fixture is malformed by construction
                self.fail("fixture parsed successfully; it cannot exercise the failure")

            with patch("sys.stderr", new_callable=io.StringIO) as captured:
                result = _parse_source(path, "toml")

        self.assertIsNone(result)
        message = self._warning_line(captured)
        self.assertIn(str(path), message)
        self.assertIn(tomllib_message, message)
        self.assertNotIn("single", message)


class TestLoadConfigFileCacheInvalidation(unittest.TestCase):
    """
    load_config_file()'s parse cache keys on (path, format, st_mtime_ns, st_size).

    One test per component of that key, so a component's removal fails exactly
    the test that names it, plus the third case -- an equal-length rewrite with
    mtime restored -- which no component of the key covers.
    """

    def setUp(self):
        # The cache is a module-level lru_cache shared across the whole test
        # process; clear it either side so results do not depend on run order.
        config_module._parse_config_file_cached.cache_clear()
        self.addCleanup(config_module._parse_config_file_cached.cache_clear)

    def test_differently_sized_rewrite_within_same_mtime_tick_is_not_served_stale(self):
        """
        Given a TOML file is read once, then rewritten to a DIFFERENT LENGTH while
            its st_mtime_ns is restored to the original value
        When load_config_file reads it again
        Then the SECOND read returns the NEW content, because st_size is part of
            the cache key -- st_mtime_ns is not what defeats the collision here
            (removing st_size from the key fails this test; removing st_mtime_ns
            does not)
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toolguard_hook.toml"
            path.write_text('governed_tools = ["Bash"]\n')

            first = load_config_file(path, "toml")
            self.assertNotIn("permissions", first)
            original_size = path.stat().st_size

            original_mtime_ns = path.stat().st_mtime_ns
            new_content = (
                'governed_tools = ["Bash"]\n\n[permissions]\nallow = ["Bash(ls:*)"]\n'
            )
            path.write_text(new_content)
            os.utime(path, ns=(original_mtime_ns, original_mtime_ns))
            self.assertEqual(path.stat().st_mtime_ns, original_mtime_ns)
            self.assertNotEqual(path.stat().st_size, original_size)

            second = load_config_file(path, "toml")
            self.assertIn("permissions", second)
            self.assertEqual(second["permissions"]["allow"], ["Bash(ls:*)"])

    def test_equal_length_rewrite_with_a_new_mtime_is_not_served_stale(self):
        """
        Given a TOML file is read once, then rewritten to content of the SAME
            byte length WITHOUT restoring st_mtime_ns
        When load_config_file reads it again
        Then the SECOND read returns the NEW content, because st_mtime_ns is
            part of the cache key -- the one case size cannot cover, and the
            only one that fails when st_mtime_ns is dropped from the key
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toolguard_hook.toml"
            path.write_text('governed_tools = ["Bash"]\n')

            first = load_config_file(path, "toml")
            self.assertEqual(first["governed_tools"], ["Bash"])
            original = path.stat()

            path.write_text('governed_tools = ["Read"]\n')
            os.utime(
                path,
                ns=(original.st_mtime_ns + 1_000_000, original.st_mtime_ns + 1_000_000),
            )
            self.assertEqual(path.stat().st_size, original.st_size)
            self.assertNotEqual(path.stat().st_mtime_ns, original.st_mtime_ns)

            second = load_config_file(path, "toml")
            self.assertEqual(second["governed_tools"], ["Read"])

    def test_equal_length_same_mtime_rewrite_is_not_served_stale(self):
        """
        Given a TOML file is read once, then rewritten to content of the SAME
            byte length with its st_mtime_ns restored -- the shape a
            read-modify-write tool produces when it swaps one rule for another
        When load_config_file reads it again
        Then the SECOND read returns the NEW content

        RED: proposed ticket 27. Neither key component changes, so the rewrite
        collides with the cached entry and the stale parse is served. A content
        hash in the key fixes it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "toolguard_hook.toml"
            path.write_text('governed_tools = ["Bash"]\n')

            first = load_config_file(path, "toml")
            self.assertEqual(first["governed_tools"], ["Bash"])
            original = path.stat()

            path.write_text('governed_tools = ["Read"]\n')
            os.utime(path, ns=(original.st_mtime_ns, original.st_mtime_ns))
            self.assertEqual(path.stat().st_mtime_ns, original.st_mtime_ns)
            self.assertEqual(path.stat().st_size, original.st_size)

            second = load_config_file(path, "toml")
            self.assertEqual(second["governed_tools"], ["Read"])


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


class TestWrongShapedTomlSections(ConfigIsolationMixin, unittest.TestCase):
    """
    TOML that parses but whose sections are the wrong TYPE.

    A TOML document's top level is always a table, so ``_try_parse_source``'s
    "expected a top-level object/table" guard can never fire for TOML -- it is
    reachable from JSON only (proposed ticket 46). The TOML analogue is a
    section of the wrong type one level down: ``[[permissions]]`` yields a
    list where a table is expected, and ``allow = "..."`` yields a string
    where a list is expected. Both parse cleanly and both discard every rule
    in the section.
    """

    def _load_toml(self, text: str) -> dict:
        """Write *text* to a temp toolguard_hook.toml and read it back through the real loader."""
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = tmp / "toolguard_hook.toml"
        path.write_text(text)
        config_module._parse_config_file_cached.cache_clear()
        self.addCleanup(config_module._parse_config_file_cached.cache_clear)
        return load_config_file(path, "toml")

    def test_permissions_written_as_an_array_of_tables_round_trips_as_a_list(self):
        """
        Given a TOML config using [[permissions]] (an array of tables) instead
            of [permissions] (a table)
        When it is written to a file and read back through load_config_file
        Then it parses without error and 'permissions' comes back as a list --
            characterizing the shape the checks below have to cope with
        """
        config = self._load_toml(
            'governed_tools = ["Bash"]\n\n[[permissions]]\nallow = ["Bash(ls:*)"]\n'
        )
        self.assertIsInstance(config, dict)
        self.assertIsInstance(config["permissions"], list)
        self.assertEqual(config["permissions"], [{"allow": ["Bash(ls:*)"]}])

    def test_permissions_of_the_wrong_type_is_reported(self):
        """
        Given a TOML config whose [[permissions]] section parses to a list
        When validate_permissions inspects it
        Then it reports an error-level Issue naming the permissions section

        RED. Today validate_permissions returns () for this input: the
        `isinstance(permissions, dict)` guard returns early with no Issue, so
        every rule the user wrote is discarded in silence. Same family as
        proposed tickets 40 and 46 -- the codebase assumes a parsed document
        is a dict and only sometimes checks.
        """
        config = self._load_toml(
            'governed_tools = ["Bash"]\n\n[[permissions]]\nallow = ["Bash(ls:*)"]\n'
        )
        issues = validate_permissions(config)
        self.assertTrue(
            any(
                issue.level == "error" and "permissions" in issue.message
                for issue in issues
            ),
            f"expected an error naming the permissions section, got {issues!r}",
        )

    def test_allow_written_as_a_bare_string_is_reported(self):
        """
        Given a TOML config whose permissions.allow is a bare string rather
            than an array of strings
        When validate_permissions inspects it
        Then it reports an error-level Issue naming the allow list

        RED. Today the `isinstance(perms, list)` guard skips the list with no
        Issue, so the rule is discarded in silence.
        """
        config = self._load_toml('[permissions]\nallow = "Bash(ls:*)"\n')
        self.assertEqual(config["permissions"]["allow"], "Bash(ls:*)")
        issues = validate_permissions(config)
        self.assertTrue(
            any(
                issue.level == "error" and "allow" in issue.message for issue in issues
            ),
            f"expected an error naming the allow list, got {issues!r}",
        )

    def test_governed_tools_of_the_wrong_type_falls_back_to_bash_silently(self):
        """
        Given a TOML config whose governed_tools is a bare string
        When validate_permissions inspects it
        Then it silently substitutes the ['Bash'] default and reports nothing
            about governed_tools itself

        Characterization, not endorsement: this is the mildest of the three
        wrong-type sites, because the fallback is safe (it governs more, not
        less) and a permission for another tool still draws the
        "not in governed_tools" warning. Pinned so a phase-2 change here is
        visible rather than incidental.
        """
        config = self._load_toml(
            'governed_tools = "Bash"\n\n[permissions]\nallow = ["Read(/tmp/**)"]\n'
        )
        self.assertEqual(config["governed_tools"], "Bash")
        issues = validate_permissions(config)
        self.assertEqual(
            [issue.message for issue in issues],
            ['Tool "Read" appears in permissions but is not in governed_tools list'],
        )

        # A string governed_tools that CONTAINS the tool name: without the
        # fallback, membership degrades from list containment to substring
        # containment and the warning silently disappears.
        containing = self._load_toml(
            'governed_tools = "BashRead"\n\n[permissions]\nallow = ["Read(/tmp/**)"]\n'
        )
        self.assertEqual(
            [issue.message for issue in validate_permissions(containing)],
            ['Tool "Read" appears in permissions but is not in governed_tools list'],
        )

    def test_a_discarded_permissions_section_is_surfaced_somewhere(self):
        """
        Given a project whose only config is a toolguard_hook.toml written with
            [[permissions]] instead of [permissions]
        When load_configuration() loads the hierarchy
        Then the loss is surfaced -- as a recorded parse failure, a validation
            issue, or rules that actually reached the layer

        RED, and this is the blast radius of the two REDs above. Today all
        three are empty: the layer loads "successfully" with zero allow rules,
        zero parse failures and zero validation issues, so nothing anywhere
        tells the user their entire allow list was dropped. Proposed ticket
        29's family, on the TOML config path.
        """
        _home, project_dir = self.isolate_config_environment()
        claude_dir = project_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            'governed_tools = ["Bash"]\n\n[[permissions]]\nallow = ["Bash(ls:*)"]\n'
        )
        config_module._parse_config_file_cached.cache_clear()
        self.addCleanup(config_module._parse_config_file_cached.cache_clear)

        configuration = load_configuration()

        self.assertTrue(
            configuration.parse_failures
            or configuration.validation_issues()
            or configuration.has_any_rules("Bash"),
            "the [[permissions]] section was discarded with no parse failure, "
            "no validation issue and no surviving rule",
        )


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

        A crash smoke test, not a behavioural one: with no permissions the
        entry loop runs zero times, so () is what every non-crashing
        implementation returns. Kept for the crash coverage, labelled so it is
        not mistaken for evidence about the defaulting it appears to check.
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
        Then exactly one date-stamped toolguard-warning-YYYY-MM-DD.md file is
            created, and no error file

        The date stamp is the assertion that carries weight: the previous
        startswith/endswith pair only restated the glob that produced the name
        and so could not fail.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning("Test warning", "Fix by doing X", log_dir)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertRegex(
                warning_files[0].name, r"^toolguard-warning-\d{4}-\d{2}-\d{2}\.md$"
            )

            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])

    def test_warning_log_dir_is_created_when_missing(self):
        """
        Given a log directory path that does not exist yet
        When log_warning writes a warning
        Then the directory is created and the entry lands in it

        The other tests here hand log_warning a directory that already exists,
        so none of them can see the mkdir disappear.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "not" / "created" / "yet"
            self.assertFalse(log_dir.exists())

            log_warning("Test warning", "Fix by doing X", log_dir)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertIn("Test warning", warning_files[0].read_text())

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
