"""
Unit tests for toolguard config hierarchy and pattern parsing.

Tests config file discovery, loading, merging, and extended pattern syntax.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.config import (
    discover_config_files,
    _load_governed_tools,
    _load_governed_tools_from_file,
    _load_permissions,
    _load_permissions_from_file,
    _merge_governed_tools,
    _merge_permissions,
)
from toolguard.patterns import PatternType, match_pattern, parse_pattern


class TestPatternParsing(unittest.TestCase):
    """Test extended pattern syntax parsing."""

    def test_parse_default_pattern(self):
        """
        Given a pattern string with no type prefix
        When parse_pattern parses it
        Then the type is DEFAULT and the pattern is returned unchanged
        """
        pattern_type, pattern = parse_pattern('git *')
        self.assertEqual(pattern_type, PatternType.DEFAULT)
        self.assertEqual(pattern, 'git *')

    def test_parse_regex_pattern(self):
        """
        Given a pattern string prefixed with [regex]
        When parse_pattern parses it
        Then the type is REGEX and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern('[regex]^git (status|log).*')
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, '^git (status|log).*')

    def test_parse_glob_pattern(self):
        """
        Given a pattern string prefixed with [glob]
        When parse_pattern parses it
        Then the type is GLOB and the prefix is stripped from the pattern body
        """
        pattern_type, pattern = parse_pattern('[glob]/Users/*/projects/**/*.py')
        self.assertEqual(pattern_type, PatternType.GLOB)
        self.assertEqual(pattern, '/Users/*/projects/**/*.py')

    def test_parse_pattern_with_whitespace(self):
        """
        Given a [regex] pattern with leading and trailing whitespace
        When parse_pattern parses it
        Then the type is REGEX and surrounding whitespace is stripped from the body
        """
        pattern_type, pattern = parse_pattern('  [regex]test.*  ')
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, 'test.*')


class TestPatternMatching(unittest.TestCase):
    """Test pattern matching with different types."""

    def test_match_regex_pattern(self):
        """
        Given a REGEX pattern with an alternation (e.g. ^git (status|log))
        When matched against commands inside and outside the alternation
        Then matching commands match and non-matching ones do not
        """
        self.assertTrue(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git status'))
        self.assertTrue(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git log'))
        self.assertFalse(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git push'))

    def test_match_regex_anywhere(self):
        """
        Given an unanchored REGEX pattern (e.g. \\.env)
        When matched against commands where the pattern appears anywhere
        Then it matches regardless of position in the command
        """
        self.assertTrue(match_pattern(PatternType.REGEX, r'\.env', 'cat /path/.env'))
        self.assertTrue(match_pattern(PatternType.REGEX, r'\.env', 'cat .env'))

    def test_match_glob_pattern(self):
        """
        Given a GLOB pattern with a trailing wildcard (e.g. 'git *')
        When matched against commands starting with that prefix versus others
        Then prefixed commands match and unrelated commands do not
        """
        self.assertTrue(match_pattern(PatternType.GLOB, 'git *', 'git status'))
        self.assertTrue(match_pattern(PatternType.GLOB, 'git *', 'git log'))
        self.assertFalse(match_pattern(PatternType.GLOB, 'git *', 'cat file'))

    def test_match_invalid_regex(self):
        """
        Given a malformed REGEX pattern
        When match_pattern attempts to match a command against it
        Then it returns False instead of raising
        """
        self.assertFalse(match_pattern(PatternType.REGEX, '[invalid(regex', 'test'))


class TestConfigDiscovery(unittest.TestCase):
    """Test config file discovery in hierarchy."""

    def test_discover_with_project_configs(self):
        """
        Given a project with .claude/settings.local.json and toolguard_hook.json present
        When discover_config_files runs with the project root resolved
        Then both project config files appear in the discovered config paths
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a project structure
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create some config files
            (claude_dir / 'settings.local.json').write_text('{}')
            (claude_dir / 'toolguard_hook.json').write_text('{}')

            # Mock find_project_root to return our temp project
            with patch('toolguard.config.find_project_root', return_value=project_dir):
                configs = discover_config_files()

            # Should find project configs
            config_paths = [str(path) for path, _, _ in configs]
            self.assertIn(str(claude_dir / 'settings.local.json'), config_paths)
            self.assertIn(str(claude_dir / 'toolguard_hook.json'), config_paths)

    def test_discover_without_project_root(self):
        """
        Given find_project_root raises RuntimeError (no project found)
        When discover_config_files runs
        Then it does not crash and returns a list (only user-level configs, if any)
        """
        with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
            configs = discover_config_files()
            # Should only find user-level configs (if they exist)
            # Since we're in a test environment, user configs may or may not exist
            # Just verify it doesn't crash
            self.assertIsInstance(configs, list)

    def test_discover_prioritizes_local_over_regular(self):
        """
        Given a project with both settings.local.json and settings.json
        When discover_config_files runs
        Then settings.local.json appears before settings.json in the ordering
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create both local and regular files
            (claude_dir / 'settings.local.json').write_text('{}')
            (claude_dir / 'settings.json').write_text('{}')

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                configs = discover_config_files()

            config_paths = [path for path, _, _ in configs]
            # settings.local.json should come before settings.json
            local_idx = next(i for i, p in enumerate(config_paths) if p.name == 'settings.local.json')
            regular_idx = next(i for i, p in enumerate(config_paths) if p.name == 'settings.json')
            self.assertLess(local_idx, regular_idx)


class TestLoadPermissionsFromFile(unittest.TestCase):
    """Test loading permissions from a single file."""

    def test_load_empty_file(self):
        """
        Given a JSON config file containing an empty object
        When _load_permissions_from_file reads it with format 'claude'
        Then both allow and deny lists are empty
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = _load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, [])
            self.assertEqual(deny, [])
        finally:
            filepath.unlink()

    def test_load_with_bash_permissions(self):
        """
        Given a config file with Bash() allow and deny permissions
        When _load_permissions_from_file reads it with format 'claude'
        Then the Bash patterns are returned with the Bash() wrapper stripped
        """
        config = {'permissions': {'allow': ['Bash(git *)', 'Bash(ls *)'], 'deny': ['Bash(rm *)']}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = _load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, ['git *', 'ls *'])
            self.assertEqual(deny, ['rm *'])
        finally:
            filepath.unlink()

    def test_load_ignores_non_bash_permissions(self):
        """
        Given a config file mixing Bash() entries with Read()/Write()/Edit() entries
        When _load_permissions_from_file reads it with format 'claude'
        Then only the Bash patterns are returned and the rest are ignored
        """
        config = {'permissions': {'allow': ['Bash(git *)', 'Read(*)', 'Write(*)'], 'deny': ['Bash(rm *)', 'Edit(*)']}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = _load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, ['git *'])
            self.assertEqual(deny, ['rm *'])
        finally:
            filepath.unlink()

    def test_load_invalid_json_returns_empty(self):
        """
        Given a config file containing invalid JSON
        When _load_permissions_from_file reads it
        Then it returns empty allow and deny lists instead of raising
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('invalid json{]')
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = _load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, [])
            self.assertEqual(deny, [])
        finally:
            filepath.unlink()


class TestMergePermissions(unittest.TestCase):
    """Test merging permissions from multiple sources."""

    def test_merge_empty_lists(self):
        """
        Given an empty list of permission sources
        When _merge_permissions is called
        Then it returns a pair of empty allow and deny lists
        """
        result = _merge_permissions([])
        self.assertEqual(result, ([], []))

    def test_merge_single_source(self):
        """
        Given a single (allow, deny) permission source
        When _merge_permissions is called
        Then its allow and deny lists are returned unchanged
        """
        perms = [(['git *', 'ls *'], ['rm *'])]
        allow, deny = _merge_permissions(perms)
        self.assertEqual(allow, ['git *', 'ls *'])
        self.assertEqual(deny, ['rm *'])

    def test_merge_multiple_sources(self):
        """
        Given several (allow, deny) permission sources with distinct patterns
        When _merge_permissions is called
        Then the allow and deny lists contain the union of all source patterns
        """
        perms = [(['git *'], ['rm *']), (['ls *'], ['mv *']), (['cat *'], [])]
        allow, deny = _merge_permissions(perms)
        self.assertEqual(set(allow), {'git *', 'ls *', 'cat *'})
        self.assertEqual(set(deny), {'rm *', 'mv *'})

    def test_merge_removes_duplicates(self):
        """
        Given permission sources sharing some identical allow and deny patterns
        When _merge_permissions is called
        Then duplicate patterns are collapsed so each appears only once
        """
        perms = [
            (['git *', 'ls *'], ['rm *']),
            (['git *', 'cat *'], ['rm *', 'mv *']),
        ]
        allow, deny = _merge_permissions(perms)
        # Should have unique patterns
        self.assertEqual(len(allow), 3)  # git, ls, cat
        self.assertEqual(len(deny), 2)  # rm, mv

    def test_merge_preserves_order(self):
        """
        Given permission sources where a later source repeats an earlier allow pattern
        When _merge_permissions is called
        Then patterns keep their first-occurrence order in the merged allow list
        """
        perms = [
            (['a', 'b', 'c'], []),
            (['b', 'd'], []),  # 'b' is duplicate
        ]
        allow, deny = _merge_permissions(perms)
        # 'a' should come before 'd' since 'a' was first
        self.assertEqual(allow.index('a'), 0)
        self.assertEqual(allow.index('b'), 1)
        self.assertEqual(allow.index('c'), 2)
        self.assertEqual(allow.index('d'), 3)


class TestLoadPermissions(unittest.TestCase):
    """Test the main _load_permissions function."""

    def test_load_with_claude_settings_path_env(self):
        """
        Given CLAUDE_SETTINGS_PATH pointing at a config file with a Bash allow pattern
        When _load_permissions is called
        Then permissions are read from that file, taking precedence over the hierarchy
        """
        config = {'permissions': {'allow': ['Bash(git *)'], 'deny': []}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = f.name

        try:
            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': filepath}):
                allow, deny = _load_permissions()
                self.assertEqual(allow, ['git *'])
                self.assertEqual(deny, [])
        finally:
            Path(filepath).unlink()

    def test_load_without_env_uses_hierarchy(self):
        """
        Given no CLAUDE_SETTINGS_PATH set and a project config file in the hierarchy
        When _load_permissions is called
        Then permissions are discovered from the project hierarchy config
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create a config file
            config = {'permissions': {'allow': ['Bash(git *)'], 'deny': []}}
            config_file = claude_dir / 'settings.local.json'
            config_file.write_text(json.dumps(config))

            with patch.dict(os.environ, {}, clear=True):
                # Remove CLAUDE_SETTINGS_PATH if it exists
                os.environ.pop('CLAUDE_SETTINGS_PATH', None)
                with patch('toolguard.config.find_project_root', return_value=project_dir):
                    allow, deny = _load_permissions()
                    self.assertEqual(allow, ['git *'])

    def test_load_with_no_configs_returns_empty(self):
        """
        Given no CLAUDE_SETTINGS_PATH, no discoverable project, and no existing config files
        When _load_permissions is called
        Then it returns empty allow and deny lists
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CLAUDE_SETTINGS_PATH', None)
            with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
                with patch('pathlib.Path.exists', return_value=False):
                    allow, deny = _load_permissions()
                    self.assertEqual(allow, [])
                    self.assertEqual(deny, [])


class TestLoadGovernedTools(unittest.TestCase):
    """Test loading governed tools configuration."""

    def test_load_governed_tools_default(self):
        """
        Given no config files and no project root
        When _load_governed_tools is called
        Then it returns the default governed tools list ['Bash']
        """
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CLAUDE_SETTINGS_PATH', None)
            with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
                with patch('pathlib.Path.exists', return_value=False):
                    tools = _load_governed_tools()
                    self.assertEqual(tools, ['Bash'])

    def test_load_governed_tools_from_config(self):
        """
        Given a toolguard_hook.json declaring a governed_tools list
        When _load_governed_tools is called with the project root resolved
        Then the configured governed tools are returned
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create toolguard_hook.json with governed_tools
            config = {'governed_tools': ['Bash', 'mcp__jetbrains__execute_terminal_command']}
            hook_file = claude_dir / 'toolguard_hook.json'
            hook_file.write_text(json.dumps(config))

            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop('CLAUDE_SETTINGS_PATH', None)
                with patch('toolguard.config.find_project_root', return_value=project_dir):
                    tools = _load_governed_tools()
                    self.assertEqual(tools, ['Bash', 'mcp__jetbrains__execute_terminal_command'])

    def test_load_governed_tools_merges_sources(self):
        """
        Given two hook files declaring overlapping governed_tools lists
        When _load_governed_tools is called
        Then the result is the de-duplicated union of all declared tools
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Create two hook files with different tools
            config1 = {'governed_tools': ['Bash', 'Tool1']}
            hook_file1 = claude_dir / 'toolguard_hook.json'
            hook_file1.write_text(json.dumps(config1))

            # 'Bash' is duplicate
            config2 = {'governed_tools': ['Tool2', 'Bash']}
            hook_file2 = claude_dir / 'toolguard_hook.local.json'
            hook_file2.write_text(json.dumps(config2))

            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop('CLAUDE_SETTINGS_PATH', None)
                with patch('toolguard.config.find_project_root', return_value=project_dir):
                    tools = _load_governed_tools()
                    # Should have all three unique tools
                    self.assertEqual(set(tools), {'Bash', 'Tool1', 'Tool2'})
                    # Should not have duplicates
                    self.assertEqual(len(tools), 3)


class TestLoadGovernedToolsFromFile(unittest.TestCase):
    """Test loading governed tools from a single file."""

    def test_load_from_valid_file(self):
        """
        Given a file declaring a governed_tools list
        When _load_governed_tools_from_file reads it
        Then the declared tools are returned in order
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'governed_tools': ['Bash', 'OtherTool']}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = _load_governed_tools_from_file(filepath)
            self.assertEqual(tools, ['Bash', 'OtherTool'])
        finally:
            filepath.unlink()

    def test_load_from_missing_file(self):
        """
        Given a path to a nonexistent file
        When _load_governed_tools_from_file is called
        Then it returns an empty list
        """
        tools = _load_governed_tools_from_file(Path('/nonexistent/file.json'))
        self.assertEqual(tools, [])

    def test_load_from_file_without_governed_tools(self):
        """
        Given a config file that has no governed_tools key
        When _load_governed_tools_from_file reads it
        Then it returns an empty list
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'other_key': 'value'}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = _load_governed_tools_from_file(filepath)
            self.assertEqual(tools, [])
        finally:
            filepath.unlink()

    def test_load_ignores_non_string_values(self):
        """
        Given a governed_tools list mixing strings with non-string values (int, None)
        When _load_governed_tools_from_file reads it
        Then only the string entries are returned
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'governed_tools': ['Bash', 123, None, 'OtherTool']}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = _load_governed_tools_from_file(filepath)
            self.assertEqual(tools, ['Bash', 'OtherTool'])
        finally:
            filepath.unlink()


class TestMergeGovernedTools(unittest.TestCase):
    """Test merging governed tools from multiple sources."""

    def test_merge_single_list(self):
        """
        Given a single governed-tools list
        When _merge_governed_tools is called
        Then the list is returned unchanged
        """
        result = _merge_governed_tools([['Bash', 'Tool1']])
        self.assertEqual(result, ['Bash', 'Tool1'])

    def test_merge_multiple_lists(self):
        """
        Given several governed-tools lists with no overlap
        When _merge_governed_tools is called
        Then all tools are concatenated in order
        """
        result = _merge_governed_tools([['Bash'], ['Tool1', 'Tool2'], ['Tool3']])
        self.assertEqual(result, ['Bash', 'Tool1', 'Tool2', 'Tool3'])

    def test_merge_removes_duplicates(self):
        """
        Given governed-tools lists that share a common tool
        When _merge_governed_tools is called
        Then the shared tool appears only once in the result
        """
        result = _merge_governed_tools([['Bash', 'Tool1'], ['Bash', 'Tool2']])
        self.assertEqual(result, ['Bash', 'Tool1', 'Tool2'])
        # Verify no duplicates
        self.assertEqual(len(result), len(set(result)))

    def test_merge_preserves_order(self):
        """
        Given governed-tools lists where a later list repeats an earlier tool
        When _merge_governed_tools is called
        Then tools keep their first-occurrence order in the merged result
        """
        result = _merge_governed_tools([['A', 'B'], ['C'], ['B', 'D']])
        # 'B' appears first in first list, so it should come before 'C'
        self.assertEqual(result.index('A'), 0)
        self.assertEqual(result.index('B'), 1)
        self.assertEqual(result.index('C'), 2)
        self.assertEqual(result.index('D'), 3)

    def test_merge_empty_lists(self):
        """
        Given an empty collection of governed-tools lists
        When _merge_governed_tools is called
        Then it returns an empty list
        """
        result = _merge_governed_tools([])
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
