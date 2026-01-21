"""
Unit tests for toolguard hook functionality.

Tests hook behavior with different tool names and governed tools configuration.
Includes tests for file path tools (Read, Write, Edit) with GLOB pattern matching.
"""

import json
import unittest
from io import StringIO
from unittest.mock import patch

from toolguard.hook import (
    FILE_PATH_TOOLS,
    check_file_path_permission,
    create_hook_output,
    load_file_path_patterns,
    main,
    parse_hook_input,
)


class TestHookToolGovernance(unittest.TestCase):
    """Test that hook correctly governs different tools."""

    def test_bash_tool_is_governed(self):
        """Test that Bash tool is governed (checked against permissions)."""
        hook_input = {
            'tool_name': 'Bash',
            'tool_input': {'command': 'git status'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Bash']):
                    with patch('toolguard.hook.load_permissions', return_value=(['git *'], [])):
                        with patch('toolguard.hook.log_command'):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            # Should be allowed because 'git status' matches 'git *'
                            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'allow')

    def test_jetbrains_terminal_is_governed(self):
        """Test that JetBrains terminal tool can be governed."""
        hook_input = {
            'tool_name': 'mcp__jetbrains__execute_terminal_command',
            'tool_input': {'command': 'git status'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch(
                    'toolguard.hook.load_governed_tools',
                    return_value=['Bash', 'mcp__jetbrains__execute_terminal_command'],
                ):
                    with patch('toolguard.hook.load_permissions', return_value=(['git *'], [])):
                        with patch('toolguard.hook.log_command'):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            # Should be allowed because tool is governed and command matches
                            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'allow')

    def test_ungoverned_tool_is_allowed(self):
        """Test that tools not in governed list are allowed through."""
        hook_input = {
            'tool_name': 'SomeOtherTool',
            'tool_input': {'command': 'dangerous command'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Bash']):
                    # No need to mock permissions since tool shouldn't be checked
                    try:
                        main()
                    except SystemExit:
                        pass

                    output = json.loads(mock_stdout.getvalue())
                    # Should be allowed because tool is not governed
                    self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'allow')
                    # Reason should mention it's not governed
                    self.assertIn('Not a governed tool', output['hookSpecificOutput']['permissionDecisionReason'])


class TestHookInputParsing(unittest.TestCase):
    """Test hook input parsing."""

    def test_parse_valid_input(self):
        """Test parsing valid JSON input."""
        hook_input = {
            'tool_name': 'Bash',
            'tool_input': {'command': 'git status'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            result = parse_hook_input()
            self.assertEqual(result['tool_name'], 'Bash')
            self.assertEqual(result['tool_input']['command'], 'git status')

    def test_parse_missing_required_field(self):
        """Test that missing required field raises ValueError."""
        hook_input = {
            'tool_name': 'Bash',
            # Missing tool_input
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with self.assertRaises(ValueError) as ctx:
                parse_hook_input()
            self.assertIn('tool_input', str(ctx.exception))

    def test_parse_empty_input(self):
        """Test that empty input raises ValueError."""
        with patch('sys.stdin', StringIO('')):
            with self.assertRaises(ValueError) as ctx:
                parse_hook_input()
            self.assertIn('Empty input', str(ctx.exception))


class TestHookOutput(unittest.TestCase):
    """Test hook output formatting."""

    def test_create_allow_output(self):
        """Test creating allow output."""
        output = create_hook_output('allow', 'Command matches allow pattern')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'allow')
        self.assertEqual(output['hookSpecificOutput']['permissionDecisionReason'], 'Command matches allow pattern')

    def test_create_deny_output(self):
        """Test creating deny output."""
        output = create_hook_output('deny', 'Command matches deny pattern')
        self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(output['hookSpecificOutput']['permissionDecisionReason'], 'Command matches deny pattern')


class TestFilePathTools(unittest.TestCase):
    """Test file path tool constants and identification."""

    def test_file_path_tools_constant(self):
        """Test that FILE_PATH_TOOLS contains expected tools."""
        self.assertIn('Read', FILE_PATH_TOOLS)
        self.assertIn('Write', FILE_PATH_TOOLS)
        self.assertIn('Edit', FILE_PATH_TOOLS)
        self.assertEqual(len(FILE_PATH_TOOLS), 3)


class TestCheckFilePathPermission(unittest.TestCase):
    """Test file path permission checking with GLOB patterns."""

    def test_simple_glob_match(self):
        """Test simple glob pattern matching."""
        allow_patterns = ['/tmp/*']
        deny_patterns = []

        decision, reason = check_file_path_permission('/tmp/test.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_globstar_recursive_match(self):
        """Test ** globstar matches nested paths."""
        allow_patterns = ['/tmp/**']
        deny_patterns = []

        # Should match nested path
        decision, reason = check_file_path_permission('/tmp/subdir/deep/file.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_single_star_does_not_match_nested(self):
        """Test * does not match path separators (unlike **)."""
        allow_patterns = ['/tmp/*']
        deny_patterns = []

        # Single * should NOT match nested path
        decision, reason = check_file_path_permission('/tmp/subdir/file.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

    def test_deny_takes_precedence(self):
        """Test deny patterns are checked first."""
        allow_patterns = ['/tmp/**']
        deny_patterns = ['/tmp/secret/**']

        # Should be denied even though allow pattern matches
        decision, reason = check_file_path_permission('/tmp/secret/password.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

    def test_no_match_returns_deny(self):
        """Test that paths not matching any allow pattern are denied."""
        allow_patterns = ['/home/**']
        deny_patterns = []

        decision, reason = check_file_path_permission('/tmp/file.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('does not match', reason)

    def test_tilde_expansion(self):
        """Test that tilde is expanded in patterns and paths."""
        import os

        home = os.path.expanduser('~')
        allow_patterns = ['~/projects/**']
        deny_patterns = []

        # Test with expanded path matching tilde pattern
        decision, reason = check_file_path_permission(f'{home}/projects/test.py', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_file_extension_pattern(self):
        """Test glob pattern with file extensions."""
        allow_patterns = ['/tmp/**/*.txt']
        deny_patterns = []

        # Should match .txt files
        decision, reason = check_file_path_permission('/tmp/docs/readme.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

        # Should not match .py files
        decision, reason = check_file_path_permission('/tmp/src/main.py', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')


class TestLoadFilePathPatterns(unittest.TestCase):
    """Test loading file path patterns from config."""

    def test_load_patterns_from_config(self):
        """Test loading Read patterns from config files."""
        mock_config = {
            'permissions': {
                'allow': ['Read(/tmp/**)', 'Read(/home/**)', 'Write(/tmp/*)', 'Bash(git status:*)'],
                'deny': ['Read(/tmp/secret/**)'],
            }
        }

        with patch('toolguard.hook.discover_config_files', return_value=[('/fake/path', 'claude', 'json')]):
            with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(mock_config))):
                allow, deny = load_file_path_patterns('Read')

                # Should only get Read patterns, not Write or Bash
                self.assertEqual(len(allow), 2)
                self.assertIn('/tmp/**', allow)
                self.assertIn('/home/**', allow)

                # Should get deny patterns for Read
                self.assertEqual(len(deny), 1)
                self.assertIn('/tmp/secret/**', deny)

    def test_load_write_patterns(self):
        """Test loading Write patterns from config files."""
        mock_config = {
            'permissions': {
                'allow': ['Read(/tmp/**)', 'Write(/tmp/*)', 'Write(~/projects/**)'],
                'deny': [],
            }
        }

        with patch('toolguard.hook.discover_config_files', return_value=[('/fake/path', 'claude', 'json')]):
            with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(mock_config))):
                allow, deny = load_file_path_patterns('Write')

                # Should only get Write patterns
                self.assertEqual(len(allow), 2)
                self.assertIn('/tmp/*', allow)
                self.assertIn('~/projects/**', allow)


class TestFilePathToolsInMain(unittest.TestCase):
    """Test that main() correctly handles file path tools."""

    def test_read_tool_allowed(self):
        """Test Read tool with matching allow pattern."""
        hook_input = {
            'tool_name': 'Read',
            'tool_input': {'file_path': '/tmp/test.txt'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Read', 'Write', 'Edit']):
                    with patch('toolguard.hook.load_file_path_patterns', return_value=(['/tmp/**'], [])):
                        with patch('toolguard.hook.log_command'):
                            with patch('toolguard.hook.identify_current_agent', return_value={'agent_type': 'main'}):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'allow')

    def test_write_tool_denied(self):
        """Test Write tool denied when no matching pattern."""
        hook_input = {
            'tool_name': 'Write',
            'tool_input': {'file_path': '/etc/passwd'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Read', 'Write', 'Edit']):
                    with patch('toolguard.hook.load_file_path_patterns', return_value=(['/tmp/**'], [])):
                        with patch('toolguard.hook.log_command'):
                            with patch('toolguard.hook.identify_current_agent', return_value={'agent_type': 'main'}):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_edit_tool_with_deny_pattern(self):
        """Test Edit tool blocked by deny pattern."""
        hook_input = {
            'tool_name': 'Edit',
            'tool_input': {'file_path': '/tmp/secret/config.txt'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Read', 'Write', 'Edit']):
                    with patch(
                        'toolguard.hook.load_file_path_patterns', return_value=(['/tmp/**'], ['/tmp/secret/**'])
                    ):
                        with patch('toolguard.hook.log_command'):
                            with patch('toolguard.hook.identify_current_agent', return_value={'agent_type': 'main'}):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                                self.assertIn('deny pattern', output['hookSpecificOutput']['permissionDecisionReason'])

    def test_read_no_file_path_denied(self):
        """Test Read tool with missing file_path is denied."""
        hook_input = {
            'tool_name': 'Read',
            'tool_input': {},  # Missing file_path
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Read', 'Write', 'Edit']):
                    with patch('toolguard.hook.log_command'):
                        with patch('toolguard.hook.identify_current_agent', return_value={'agent_type': 'main'}):
                            try:
                                main()
                            except SystemExit:
                                pass

                            output = json.loads(mock_stdout.getvalue())
                            self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                            self.assertIn('file_path', output['hookSpecificOutput']['permissionDecisionReason'])

    def test_read_no_allow_patterns_denied(self):
        """Test Read tool with no allow patterns is denied."""
        hook_input = {
            'tool_name': 'Read',
            'tool_input': {'file_path': '/tmp/test.txt'},
            'hook_event_name': 'PreToolUse',
        }

        with patch('sys.stdin', StringIO(json.dumps(hook_input))):
            with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
                with patch('toolguard.hook.load_governed_tools', return_value=['Read', 'Write', 'Edit']):
                    with patch('toolguard.hook.load_file_path_patterns', return_value=([], [])):  # No patterns
                        with patch('toolguard.hook.log_command'):
                            with patch('toolguard.hook.identify_current_agent', return_value={'agent_type': 'main'}):
                                try:
                                    main()
                                except SystemExit:
                                    pass

                                output = json.loads(mock_stdout.getvalue())
                                self.assertEqual(output['hookSpecificOutput']['permissionDecision'], 'deny')
                                self.assertIn(
                                    'No Read permissions', output['hookSpecificOutput']['permissionDecisionReason']
                                )


class TestStartupValidation(unittest.TestCase):
    """Test startup validation only validates toolguard_hook files."""

    def test_validation_ignores_settings_local_json(self):
        """Test that validation does NOT warn about tools in settings.local.json.

        Only toolguard_hook.toml/json files should be validated.
        settings.local.json contains Claude's native permission format which
        toolguard doesn't understand, so it should be ignored.
        """
        import tempfile
        from pathlib import Path

        import toolguard.hook as hook_module

        # Reset validation flag for this test
        original_flag = hook_module._validation_done
        hook_module._validation_done = False

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                project_dir = Path(tmpdir) / 'project'
                project_dir.mkdir()
                (project_dir / '.git').mkdir()
                claude_dir = project_dir / '.claude'
                claude_dir.mkdir()
                logs_dir = project_dir / 'logs'
                logs_dir.mkdir()

                # Create settings.local.json with unsupported tools (should be IGNORED)
                settings_local = {
                    'permissions': {
                        'allow': ['WebSearch', 'WebFetch', 'mcp__unknown__tool'],
                    }
                }
                (claude_dir / 'settings.local.json').write_text(json.dumps(settings_local))

                # Create toolguard_hook.toml with valid config (should be validated)
                toolguard_toml = """
governed_tools = ["Bash", "Read"]

[permissions]
allow = ["Bash(ls:*)", "Read(/tmp/**)"]
"""
                (claude_dir / 'toolguard_hook.toml').write_text(toolguard_toml)

                env_config = {'log_dir': logs_dir}

                with patch('toolguard.hook.find_project_root', return_value=project_dir):
                    with patch('toolguard.hook.discover_config_files') as mock_discover:
                        # Return both settings.local.json and toolguard_hook.toml
                        mock_discover.return_value = [
                            (claude_dir / 'settings.local.json', 'claude', 'json'),
                            (claude_dir / 'toolguard_hook.toml', 'toolguard_hook', 'toml'),
                        ]

                        # Reset flag again before calling
                        hook_module._validation_done = False

                        # Import and call the validation function
                        from toolguard.hook import _run_startup_validation

                        _run_startup_validation(env_config, str(project_dir))

                # Check log file - should NOT have warnings for WebSearch, WebFetch
                # because those are in settings.local.json which is ignored
                log_files = list(logs_dir.glob('toolguard-error-*.md'))

                if log_files:
                    content = log_files[0].read_text()
                    # These tools are in settings.local.json which should be ignored
                    self.assertNotIn('WebSearch', content)
                    self.assertNotIn('WebFetch', content)
                    self.assertNotIn('mcp__unknown__tool', content)
                # If no log file exists, that's also correct (no warnings generated)

        finally:
            # Restore original flag
            hook_module._validation_done = original_flag


if __name__ == '__main__':
    unittest.main()
