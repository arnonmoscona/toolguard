"""
Unit tests for TOML configuration support in toolguard.

Tests TOML loading, config file discovery with TOML precedence,
and permission validation.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.toml_config import load_toml_config
from toolguard.config_validation import (
    KNOWN_SUPPORTED_TOOLS,
    extract_tool_name,
    validate_permissions,
)
from toolguard.error_log import log_warning, log_error
from toolguard.config import discover_config_files


class TestTomlConfigLoader(unittest.TestCase):
    """Test TOML configuration loading."""

    def test_load_valid_toml_config(self):
        """
        Given a valid TOML config with governed_tools and allow/deny/ask permissions
        When load_toml_config reads it
        Then the parsed dict exposes the governed tools and each permission list
        """
        toml_content = b"""
governed_tools = ["Bash", "Read"]

[permissions]
allow = ["Bash(ls:*)", "Read(/tmp/**)"]
deny = ["Bash(rm -rf:*)"]
ask = ["Bash(alembic:*)"]
"""
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_toml_config(filepath)
            self.assertEqual(config['governed_tools'], ['Bash', 'Read'])
            self.assertEqual(config['permissions']['allow'], ['Bash(ls:*)', 'Read(/tmp/**)'])
            self.assertEqual(config['permissions']['deny'], ['Bash(rm -rf:*)'])
            self.assertEqual(config['permissions']['ask'], ['Bash(alembic:*)'])
        finally:
            filepath.unlink()

    def test_load_toml_with_missing_optional_sections(self):
        """
        Given a TOML config that defines only governed_tools
        When load_toml_config reads it
        Then governed_tools is parsed and no permissions key is present
        """
        toml_content = b"""
governed_tools = ["Bash"]
"""
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_toml_config(filepath)
            self.assertEqual(config['governed_tools'], ['Bash'])
            self.assertNotIn('permissions', config)
        finally:
            filepath.unlink()

    def test_load_toml_with_additional_supported_tools(self):
        """
        Given a TOML config declaring additional_supported_tools
        When load_toml_config reads it
        Then that list is exposed in the parsed config
        """
        toml_content = b"""
governed_tools = ["Bash", "mcp__custom__tool"]
additional_supported_tools = ["mcp__custom__tool"]

[permissions]
allow = ["Bash(ls:*)", "mcp__custom__tool(*)"]
"""
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            config = load_toml_config(filepath)
            self.assertEqual(config['additional_supported_tools'], ['mcp__custom__tool'])
        finally:
            filepath.unlink()

    def test_load_invalid_toml_raises_error(self):
        """
        Given a file containing malformed TOML
        When load_toml_config reads it
        Then an exception (TOML decode error) is raised
        """
        toml_content = b"""
invalid toml [
"""
        with tempfile.NamedTemporaryFile(suffix='.toml', delete=False) as f:
            f.write(toml_content)
            f.flush()
            filepath = Path(f.name)

        try:
            with self.assertRaises(Exception):  # tomllib.TOMLDecodeError
                load_toml_config(filepath)
        finally:
            filepath.unlink()

    def test_load_nonexistent_file_raises_error(self):
        """
        Given a path to a TOML file that does not exist
        When load_toml_config reads it
        Then a FileNotFoundError is raised
        """
        with self.assertRaises(FileNotFoundError):
            load_toml_config(Path('/nonexistent/file.toml'))


class TestConfigDiscoveryTomlPrecedence(unittest.TestCase):
    """Test that TOML files take precedence over JSON."""

    def test_toml_takes_precedence_over_json(self):
        """
        Given a project with both toolguard_hook.toml and toolguard_hook.json
        When discover_config_files runs
        Then the TOML hook file is included and the JSON one is excluded
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create both TOML and JSON files
            (claude_dir / 'toolguard_hook.toml').write_text('governed_tools = ["Bash"]')
            (claude_dir / 'toolguard_hook.json').write_text('{"governed_tools": ["Read"]}')

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                configs = discover_config_files()

            # Find toolguard_hook config entries
            hook_configs = [(p, t, f) for p, t, f in configs if t == 'toolguard_hook' and 'local' not in p.name]

            # Should have TOML, not JSON
            self.assertTrue(any(f == 'toml' for _, _, f in hook_configs))
            # The JSON should not be in the list (TOML takes precedence)
            hook_paths = [str(p) for p, _, _ in hook_configs]
            self.assertIn(str(claude_dir / 'toolguard_hook.toml'), hook_paths)
            self.assertNotIn(str(claude_dir / 'toolguard_hook.json'), hook_paths)

    def test_json_used_when_no_toml(self):
        """
        Given a project with only a toolguard_hook.json (no TOML)
        When discover_config_files runs
        Then the JSON hook file is included
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create only JSON file
            (claude_dir / 'toolguard_hook.json').write_text('{"governed_tools": ["Bash"]}')

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                configs = discover_config_files()

            # Find toolguard_hook config entries
            hook_configs = [(p, t, f) for p, t, f in configs if t == 'toolguard_hook' and 'local' not in p.name]

            # Should have JSON
            self.assertTrue(any(f == 'json' for _, _, f in hook_configs))


class TestExtractToolName(unittest.TestCase):
    """Test extraction of tool names from permission strings."""

    def test_extract_bash_tool(self):
        """
        Given Bash permission strings with parenthesized arguments
        When extract_tool_name parses them
        Then it returns 'Bash'
        """
        self.assertEqual(extract_tool_name('Bash(ls:*)'), 'Bash')
        self.assertEqual(extract_tool_name('Bash(git status)'), 'Bash')

    def test_extract_read_tool(self):
        """
        Given a Read permission string with a path argument
        When extract_tool_name parses it
        Then it returns 'Read'
        """
        self.assertEqual(extract_tool_name('Read(/tmp/**)'), 'Read')

    def test_extract_write_tool(self):
        """
        Given a Write permission string with a path argument
        When extract_tool_name parses it
        Then it returns 'Write'
        """
        self.assertEqual(extract_tool_name('Write(~/projects/**)'), 'Write')

    def test_extract_tool_without_parens(self):
        """
        Given permission strings with no parentheses
        When extract_tool_name parses them
        Then the whole string is returned as the tool name
        """
        self.assertEqual(extract_tool_name('WebSearch'), 'WebSearch')
        self.assertEqual(extract_tool_name('mcp__basic-memory__write_note'), 'mcp__basic-memory__write_note')

    def test_extract_mcp_tool(self):
        """
        Given an MCP tool permission string with no parentheses
        When extract_tool_name parses it
        Then the full MCP tool name is returned
        """
        self.assertEqual(
            extract_tool_name('mcp__jetbrains__execute_terminal_command'), 'mcp__jetbrains__execute_terminal_command'
        )


class TestValidatePermissions(unittest.TestCase):
    """Test permission validation."""

    def test_validate_no_warnings_for_valid_config(self):
        """
        Given a config whose permissions reference only governed, supported tools
        When validate_permissions runs
        Then it produces no warnings
        """
        config = {
            'governed_tools': ['Bash', 'Read'],
            'permissions': {
                'allow': ['Bash(ls:*)', 'Read(/tmp/**)'],
                'deny': ['Bash(rm -rf:*)'],
            },
        }
        warnings = validate_permissions(config)
        self.assertEqual(warnings, [])

    def test_warning_for_unsupported_tool(self):
        """
        Given permissions that reference unsupported tools (WebSearch, WebFetch)
        When validate_permissions runs
        Then warnings are produced naming each unsupported tool
        """
        config = {
            'governed_tools': ['Bash'],
            'permissions': {
                'allow': ['Bash(ls:*)', 'WebSearch', 'WebFetch(domain:example.com)'],
            },
        }
        warnings = validate_permissions(config)

        # Should have warnings for WebSearch and WebFetch
        warning_messages = [w['message'] for w in warnings]
        self.assertTrue(any('WebSearch' in msg for msg in warning_messages))
        self.assertTrue(any('WebFetch' in msg for msg in warning_messages))

    def test_warning_for_ungoverned_tool(self):
        """
        Given a permission for Read while only Bash is in governed_tools
        When validate_permissions runs
        Then a warning notes that Read is not in governed_tools
        """
        config = {
            'governed_tools': ['Bash'],  # Read is not governed
            'permissions': {
                'allow': ['Bash(ls:*)', 'Read(/tmp/**)'],
            },
        }
        warnings = validate_permissions(config)

        # Should have warning for Read being ungoverned
        warning_messages = [w['message'] for w in warnings]
        self.assertTrue(any('Read' in msg and 'governed_tools' in msg for msg in warning_messages))

    def test_additional_supported_tools_no_warning(self):
        """
        Given a custom tool declared in additional_supported_tools and governed
        When validate_permissions runs on permissions using it
        Then no warnings are produced
        """
        config = {
            'governed_tools': ['Bash', 'mcp__custom__tool'],
            'additional_supported_tools': ['mcp__custom__tool'],
            'permissions': {
                'allow': ['Bash(ls:*)', 'mcp__custom__tool(*)'],
            },
        }
        warnings = validate_permissions(config)

        # Should have no warnings - custom tool is declared as supported
        self.assertEqual(warnings, [])

    def test_warnings_include_corrective_steps(self):
        """
        Given a config that produces at least one warning
        When validate_permissions runs
        Then every warning includes a non-empty corrective_steps field
        """
        config = {
            'governed_tools': ['Bash'],
            'permissions': {
                'allow': ['WebSearch'],
            },
        }
        warnings = validate_permissions(config)

        self.assertTrue(len(warnings) > 0)
        for warning in warnings:
            self.assertIn('corrective_steps', warning)
            self.assertTrue(len(warning['corrective_steps']) > 0)

    def test_empty_config_no_warnings(self):
        """
        Given an empty config dict
        When validate_permissions runs
        Then it produces no warnings
        """
        config = {}
        warnings = validate_permissions(config)
        self.assertEqual(warnings, [])

    def test_known_supported_tools_constant(self):
        """
        Given the KNOWN_SUPPORTED_TOOLS constant
        When its membership is inspected
        Then it contains Bash, Read, Write, Edit, and the JetBrains terminal tool
        """
        self.assertIn('Bash', KNOWN_SUPPORTED_TOOLS)
        self.assertIn('Read', KNOWN_SUPPORTED_TOOLS)
        self.assertIn('Write', KNOWN_SUPPORTED_TOOLS)
        self.assertIn('Edit', KNOWN_SUPPORTED_TOOLS)
        self.assertIn('mcp__jetbrains__execute_terminal_command', KNOWN_SUPPORTED_TOOLS)
        # Note: mcp__local-tools__checked_bash is user-specific and configured via
        # additional_supported_tools in TOML, not hardcoded here


class TestErrorLog(unittest.TestCase):
    """Test error logging functionality."""

    def test_error_log_file_created(self):
        """
        Given a log directory
        When log_warning writes a warning
        Then exactly one toolguard-error-*.md file is created
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a warning
            log_warning('Test warning', 'Fix by doing X', log_dir)

            # Check that log file was created
            log_files = list(log_dir.glob('toolguard-error-*.md'))
            self.assertEqual(len(log_files), 1)
            self.assertTrue(log_files[0].name.startswith('toolguard-error-'))
            self.assertTrue(log_files[0].name.endswith('.md'))

    def test_error_log_format(self):
        """
        Given a log directory
        When log_warning writes a message and corrective steps
        Then the entry contains the WARNING label, the message, the steps, and the Message/Corrective Steps fields
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning('Test warning message', 'Do this to fix', log_dir)

            log_files = list(log_dir.glob('toolguard-error-*.md'))
            content = log_files[0].read_text()

            # Check format
            self.assertIn('WARNING', content)
            self.assertIn('Test warning message', content)
            self.assertIn('Do this to fix', content)
            self.assertIn('**Message**:', content)
            self.assertIn('**Corrective Steps**:', content)

    def test_error_log_includes_timestamp(self):
        """
        Given a log directory
        When log_error writes an entry
        Then the entry includes a YYYY-MM-DD HH:MM:SS timestamp
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_error('Test error', 'Fix it', log_dir)

            log_files = list(log_dir.glob('toolguard-error-*.md'))
            content = log_files[0].read_text()

            # Timestamp format: YYYY-MM-DD HH:MM:SS
            import re

            timestamp_pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'
            self.assertTrue(re.search(timestamp_pattern, content))

    def test_multiple_log_entries_appended(self):
        """
        Given a log directory
        When a warning and then an error are logged
        Then both entries appear in the same single error file with WARNING and ERROR labels
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            log_warning('First warning', 'Step 1', log_dir)
            log_error('Second error', 'Step 2', log_dir)

            log_files = list(log_dir.glob('toolguard-error-*.md'))
            self.assertEqual(len(log_files), 1)

            content = log_files[0].read_text()
            self.assertIn('First warning', content)
            self.assertIn('Second error', content)
            self.assertIn('WARNING', content)
            self.assertIn('ERROR', content)


if __name__ == '__main__':
    unittest.main()
