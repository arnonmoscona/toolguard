"""
Unit tests for toolguard permission checking logic.

Tests the permission checking, pattern matching, and configuration loading
functionality of the toolguard pre-tool-use hook.
"""

import contextlib
import io
import json
import unittest
from unittest.mock import patch, mock_open

from toolguard.config import load_permissions
from toolguard.permissions import (
    normalize_path_in_command,
    contains_path_component,
    match_command,
    check_permission,
)


class TestNormalizePathInCommand(unittest.TestCase):
    """Test path normalization in commands."""

    def test_normalize_adds_prefix_to_relative_path(self):
        """Test that relative paths get ./ prefix."""
        self.assertEqual(normalize_path_in_command('cat file.txt'), 'cat ./file.txt')
        self.assertEqual(normalize_path_in_command('ls mydir'), 'ls ./mydir')

    def test_normalize_preserves_dot_paths(self):
        """Test that paths starting with . are not modified."""
        self.assertEqual(normalize_path_in_command('cat ./file.txt'), 'cat ./file.txt')
        self.assertEqual(normalize_path_in_command('cat ../file.txt'), 'cat ../file.txt')

    def test_normalize_preserves_absolute_paths(self):
        """Test that absolute paths are not modified."""
        self.assertEqual(normalize_path_in_command('cat /etc/hosts'), 'cat /etc/hosts')
        self.assertEqual(normalize_path_in_command('ls /usr/bin'), 'ls /usr/bin')

    def test_normalize_preserves_flags(self):
        """Test that flags starting with - are not modified."""
        self.assertEqual(normalize_path_in_command('ls -la'), 'ls -la')
        self.assertEqual(normalize_path_in_command('git --version'), 'git --version')

    def test_normalize_preserves_tilde_paths(self):
        """Test that tilde paths are not modified."""
        self.assertEqual(normalize_path_in_command('cat ~/file.txt'), 'cat ~/file.txt')

    def test_normalize_command_only_unchanged(self):
        """Test that commands without arguments are unchanged."""
        self.assertEqual(normalize_path_in_command('git'), 'git')
        self.assertEqual(normalize_path_in_command('ls'), 'ls')


class TestContainsPathComponent(unittest.TestCase):
    """Test path component detection in commands."""

    def test_exact_match(self):
        """Test exact match of component."""
        self.assertTrue(contains_path_component('cat .env', '.env'))
        self.assertTrue(contains_path_component('vim test.py', 'test.py'))

    def test_component_after_slash(self):
        """Test component appearing after a slash."""
        self.assertTrue(contains_path_component('cat dir/.env', '.env'))
        self.assertTrue(contains_path_component('cat /path/to/.env', '.env'))

    def test_component_before_slash(self):
        """Test component appearing before a slash."""
        self.assertTrue(contains_path_component('cat .env/file', '.env'))

    def test_component_in_middle(self):
        """Test component appearing in the middle of a path."""
        self.assertTrue(contains_path_component('cat dir/.env/file', '.env'))

    def test_no_match(self):
        """Test when component is not present."""
        self.assertFalse(contains_path_component('cat file.txt', '.env'))
        self.assertFalse(contains_path_component('git status', '.env'))

    def test_command_only_no_match(self):
        """Test command without arguments."""
        self.assertFalse(contains_path_component('ls', 'file'))


class TestMatchCommand(unittest.TestCase):
    """Test command pattern matching."""

    def test_simple_wildcard_match(self):
        """Test simple wildcard patterns."""
        patterns = ['git *']
        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git *')

    def test_command_args_pattern_match(self):
        """Test command:args pattern matching."""
        patterns = ['git log:*']
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git log:*')

    def test_path_component_pattern_match(self):
        """Test **/.component/** pattern matching."""
        patterns = ['**/.env/**']
        matched, pattern = match_command('cat .env', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '**/.env/**')

        matched, pattern = match_command('cat dir/.env/file', patterns)
        self.assertTrue(matched)

    def test_normalized_path_matching(self):
        """Test that normalized paths are matched."""
        patterns = ['cat ./*:*']
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'cat ./*:*')

    def test_no_match(self):
        """Test when no patterns match."""
        patterns = ['git *', 'ls *']
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_empty_patterns(self):
        """Test with empty pattern list."""
        patterns = []
        matched, pattern = match_command('git status', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_double_star_normalization(self):
        """Test that ** is normalized to * for fnmatch."""
        patterns = ['git **']
        matched, pattern = match_command('git status --short', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git **')


class TestCheckPermission(unittest.TestCase):
    """Test permission checking logic."""

    def test_allow_pattern_match(self):
        """Test command allowed by allow pattern."""
        allow_patterns = ['git *', 'ls *']
        deny_patterns = []
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')
        self.assertIn('allow pattern', reason.lower())

    def test_deny_pattern_match(self):
        """Test command denied by deny pattern."""
        allow_patterns = ['git *']
        deny_patterns = ['git push:*']
        decision, reason = check_permission('git push origin', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('deny pattern', reason.lower())

    def test_deny_takes_precedence(self):
        """Test that deny patterns take precedence over allow patterns."""
        allow_patterns = ['git *']
        deny_patterns = ['git *']
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

    def test_not_in_allow_list(self):
        """Test command not in allow list is denied."""
        allow_patterns = ['git *']
        deny_patterns = []
        decision, reason = check_permission('rm -rf /', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('does not match', reason.lower())

    def test_empty_allow_list(self):
        """Test that empty allow list denies everything."""
        allow_patterns = []
        deny_patterns = []
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')


class TestLoadPermissions(unittest.TestCase):
    """Test configuration loading from settings files."""

    @patch.dict('os.environ', {'CLAUDE_SETTINGS_PATH': '/fake/settings.json'})
    @patch('builtins.open', new_callable=mock_open)
    def test_load_permissions_success(self, mock_file):
        """Test successful loading of permissions."""
        settings_data = {
            'permissions': {
                'allow': ['Bash(git *)', 'Bash(ls:*)'],
                'deny': ['Bash(rm -rf:*)', 'Bash(**/.env/**)'],
            }
        }
        mock_file.return_value.read.return_value = json.dumps(settings_data)

        allow_patterns, deny_patterns = load_permissions()

        self.assertEqual(allow_patterns, ['git *', 'ls:*'])
        self.assertEqual(deny_patterns, ['rm -rf:*', '**/.env/**'])

    @patch.dict('os.environ', {}, clear=True)
    def test_load_permissions_no_env_var(self):
        """Test that missing CLAUDE_SETTINGS_PATH falls back to hierarchy."""
        # Mock find_project_root to raise RuntimeError (no project found)
        with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
            # Mock Path.exists to return False for all user config files
            with patch('pathlib.Path.exists', return_value=False):
                stderr_capture = io.StringIO()
                with contextlib.redirect_stderr(stderr_capture):
                    allow, deny = load_permissions()
                    # Should return empty lists when no configs found
                    self.assertEqual(allow, [])
                    self.assertEqual(deny, [])

    @patch.dict('os.environ', {'CLAUDE_SETTINGS_PATH': '/fake/settings.json'})
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_load_permissions_file_not_found(self, mock_file):
        """Test that missing settings file exits with error."""
        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            with self.assertRaises(SystemExit) as cm:
                load_permissions()
            self.assertEqual(cm.exception.code, 1)

        # Verify error message in stderr
        stderr_output = stderr_capture.getvalue()
        self.assertIn('Settings file not found', stderr_output)

    @patch.dict('os.environ', {'CLAUDE_SETTINGS_PATH': '/fake/settings.json'})
    @patch('builtins.open', new_callable=mock_open)
    def test_load_permissions_invalid_json(self, mock_file):
        """Test that invalid JSON exits with error."""
        mock_file.return_value.read.return_value = 'invalid json {'

        stderr_capture = io.StringIO()
        with contextlib.redirect_stderr(stderr_capture):
            with self.assertRaises(SystemExit) as cm:
                load_permissions()
            self.assertEqual(cm.exception.code, 1)

        # Verify error message in stderr
        stderr_output = stderr_capture.getvalue()
        self.assertIn('Invalid JSON in settings file', stderr_output)

    @patch.dict('os.environ', {'CLAUDE_SETTINGS_PATH': '/fake/settings.json'})
    @patch('builtins.open', new_callable=mock_open)
    def test_load_permissions_ignores_non_bash_patterns(self, mock_file):
        """Test that non-Bash patterns are ignored."""
        settings_data = {
            'permissions': {
                'allow': ['Bash(git *)', 'Read(**/test.py)', 'Write(**/output.txt)'],
                'deny': ['Bash(rm *)', 'Execute(/usr/bin/*)'],
            }
        }
        mock_file.return_value.read.return_value = json.dumps(settings_data)

        allow_patterns, deny_patterns = load_permissions()

        self.assertEqual(allow_patterns, ['git *'])
        self.assertEqual(deny_patterns, ['rm *'])

    @patch.dict('os.environ', {'CLAUDE_SETTINGS_PATH': '/fake/settings.json'})
    @patch('builtins.open', new_callable=mock_open)
    def test_load_permissions_empty_lists(self, mock_file):
        """Test handling of empty permission lists."""
        settings_data = {'permissions': {'allow': [], 'deny': []}}
        mock_file.return_value.read.return_value = json.dumps(settings_data)

        allow_patterns, deny_patterns = load_permissions()

        self.assertEqual(allow_patterns, [])
        self.assertEqual(deny_patterns, [])


class TestExtendedPatterns(unittest.TestCase):
    """Test extended pattern matching (REGEX and GLOB)."""

    def test_regex_pattern_in_allow_list(self):
        """Test that REGEX patterns work in allow list."""
        patterns = ['[regex]^git (log|diff|status).*']

        # Should match
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git (log|diff|status).*')

        matched, pattern = match_command('git diff HEAD~1', patterns)
        self.assertTrue(matched)

        matched, pattern = match_command('git status --short', patterns)
        self.assertTrue(matched)

        # Should not match
        matched, pattern = match_command('git push origin', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        matched, pattern = match_command('ls -la', patterns)
        self.assertFalse(matched)

    def test_regex_pattern_in_deny_list(self):
        """Test that REGEX patterns work in deny list."""
        allow_patterns = ['git *']
        deny_patterns = ['[regex]^git push.*']

        # Should be denied by regex pattern
        decision, reason = check_permission('git push origin main', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('[regex]^git push.*', reason)

        # Should be allowed
        decision, reason = check_permission('git status', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_glob_pattern_in_allow_list(self):
        """Test that GLOB patterns work in allow list."""
        # GLOB patterns match the entire command string, so we need to include the command
        patterns = ['[glob]cat /Users/*/projects/**/*.py']

        # Should match
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.py', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[glob]cat /Users/*/projects/**/*.py')

        # Should not match - different user path
        matched, pattern = match_command('vim /Users/bob/projects/myapp/src/app.py', patterns)
        self.assertFalse(matched)

        # Should not match - wrong path
        matched, pattern = match_command('cat /Users/arnon/documents/file.py', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

        # Should not match - wrong extension
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.txt', patterns)
        self.assertFalse(matched)

    def test_glob_pattern_in_deny_list(self):
        """Test that GLOB patterns work in deny list."""
        allow_patterns = ['cat *']
        deny_patterns = ['[glob]cat *.env*', '[glob]cat*/**/.env*']

        # Should be denied by glob pattern - simple case
        decision, reason = check_permission('cat .env', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')
        self.assertIn('.env', reason)

        # Should be denied by glob pattern - recursive path with **
        decision, reason = check_permission('cat /path/to/.env.production', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'deny')

        # Should be allowed
        decision, reason = check_permission('cat normal_file.txt', allow_patterns, deny_patterns)
        self.assertEqual(decision, 'allow')

    def test_mixed_pattern_types(self):
        """Test mixing DEFAULT, REGEX, and GLOB patterns."""
        patterns = [
            'git status:*',  # DEFAULT
            '[regex]^git (log|diff).*',  # REGEX
            '[glob]cat /Users/*/projects/**/*.py',  # GLOB
        ]

        # DEFAULT pattern should match
        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, 'git status:*')

        # REGEX pattern should match
        matched, pattern = match_command('git log --oneline', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git (log|diff).*')

        # GLOB pattern should match
        matched, pattern = match_command('cat /Users/arnon/projects/flowers/main.py', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[glob]cat /Users/*/projects/**/*.py')

        # None should match
        matched, pattern = match_command('rm -rf /', patterns)
        self.assertFalse(matched)

    def test_invalid_regex_no_match(self):
        """Test that invalid regex patterns don't match."""
        patterns = ['[regex]^git (unclosed']  # Invalid regex - unclosed parenthesis

        # Should not match (invalid regex returns False)
        matched, pattern = match_command('git anything', patterns)
        self.assertFalse(matched)
        self.assertIsNone(pattern)

    def test_regex_bypasses_normalization(self):
        """Test that REGEX patterns match literally without path normalization."""
        # Pattern that matches exactly "cat file.txt"
        patterns = ['[regex]^cat file\\.txt$']

        # SHOULD match - regex matches the literal command string
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match with ./ prefix
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertFalse(matched)

        # Pattern that explicitly requires ./ prefix
        patterns = ['[regex]^cat \\./file\\.txt$']
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match without the ./ prefix
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertFalse(matched)

    def test_regex_ignores_colon_syntax(self):
        """Test that REGEX patterns ignore colon syntax."""
        # Colon in regex is part of the pattern, not a separator
        patterns = ['[regex]^git log:.*']

        # Should match "git log:" literally
        matched, pattern = match_command('git log:something', patterns)
        self.assertTrue(matched)

        # Should NOT match "git log" without colon
        matched, pattern = match_command('git log something', patterns)
        self.assertFalse(matched)

    def test_glob_bypasses_normalization(self):
        """Test that GLOB patterns match literally without path normalization."""
        patterns = ['[glob]cat file.txt']

        # Should match exactly
        matched, pattern = match_command('cat file.txt', patterns)
        self.assertTrue(matched)

        # Should NOT match with ./ prefix (glob is literal)
        matched, pattern = match_command('cat ./file.txt', patterns)
        self.assertFalse(matched)

    def test_glob_ignores_colon_syntax(self):
        """Test that GLOB patterns ignore colon syntax."""
        patterns = ['[glob]git log:*']

        # Should match "git log:" literally with glob wildcard
        matched, pattern = match_command('git log:something', patterns)
        self.assertTrue(matched)

        # Should NOT match "git log " (space instead of colon)
        matched, pattern = match_command('git log something', patterns)
        self.assertFalse(matched)

    def test_first_match_wins(self):
        """Test that first matching pattern wins regardless of type."""
        patterns = [
            '[regex]^git .*',  # This should match first
            'git status:*',  # This would also match but comes second
        ]

        matched, pattern = match_command('git status', patterns)
        self.assertTrue(matched)
        self.assertEqual(pattern, '[regex]^git .*')  # First pattern wins

    def test_env_special_handling_only_for_default(self):
        """Test that **/.env/** special handling only applies to DEFAULT patterns."""
        # DEFAULT pattern with special handling
        default_patterns = ['**/.env/**']
        matched, pattern = match_command('cat .env', default_patterns)
        self.assertTrue(matched)  # Special handling applies

        # REGEX pattern - no special handling (must match full command literally)
        regex_patterns = ['[regex].*\\.env.*']
        matched, pattern = match_command('cat .env', regex_patterns)
        self.assertTrue(matched)  # Regex matches, but no path component special handling

        # GLOB pattern - no special handling, must match the full command string
        glob_patterns = ['[glob]cat .env']
        matched, pattern = match_command('cat .env', glob_patterns)
        self.assertTrue(matched)  # Exact glob match

        # GLOB with wildcard
        glob_patterns = ['[glob]* .env']
        matched, pattern = match_command('cat .env', glob_patterns)
        self.assertTrue(matched)  # Glob wildcard matches


if __name__ == '__main__':
    unittest.main()
