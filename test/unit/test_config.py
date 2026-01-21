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
    load_governed_tools,
    load_governed_tools_from_file,
    load_permissions,
    load_permissions_from_file,
    merge_governed_tools,
    merge_permissions,
)
from toolguard.patterns import PatternType, match_pattern, parse_pattern


class TestPatternParsing(unittest.TestCase):
    """Test extended pattern syntax parsing."""

    def test_parse_default_pattern(self):
        """Test parsing default patterns without prefix."""
        pattern_type, pattern = parse_pattern('git *')
        self.assertEqual(pattern_type, PatternType.DEFAULT)
        self.assertEqual(pattern, 'git *')

    def test_parse_regex_pattern(self):
        """Test parsing regex patterns with [regex] prefix."""
        pattern_type, pattern = parse_pattern('[regex]^git (status|log).*')
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, '^git (status|log).*')

    def test_parse_glob_pattern(self):
        """Test parsing glob patterns with [glob] prefix."""
        pattern_type, pattern = parse_pattern('[glob]/Users/*/projects/**/*.py')
        self.assertEqual(pattern_type, PatternType.GLOB)
        self.assertEqual(pattern, '/Users/*/projects/**/*.py')

    def test_parse_pattern_with_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        pattern_type, pattern = parse_pattern('  [regex]test.*  ')
        self.assertEqual(pattern_type, PatternType.REGEX)
        self.assertEqual(pattern, 'test.*')


class TestPatternMatching(unittest.TestCase):
    """Test pattern matching with different types."""

    def test_match_regex_pattern(self):
        """Test regex pattern matching."""
        self.assertTrue(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git status'))
        self.assertTrue(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git log'))
        self.assertFalse(match_pattern(PatternType.REGEX, r'^git (status|log)', 'git push'))

    def test_match_regex_anywhere(self):
        """Test that regex patterns match anywhere in command."""
        self.assertTrue(match_pattern(PatternType.REGEX, r'\.env', 'cat /path/.env'))
        self.assertTrue(match_pattern(PatternType.REGEX, r'\.env', 'cat .env'))

    def test_match_glob_pattern(self):
        """Test glob pattern matching."""
        self.assertTrue(match_pattern(PatternType.GLOB, 'git *', 'git status'))
        self.assertTrue(match_pattern(PatternType.GLOB, 'git *', 'git log'))
        self.assertFalse(match_pattern(PatternType.GLOB, 'git *', 'cat file'))

    def test_match_invalid_regex(self):
        """Test that invalid regex patterns don't crash."""
        self.assertFalse(match_pattern(PatternType.REGEX, '[invalid(regex', 'test'))


class TestConfigDiscovery(unittest.TestCase):
    """Test config file discovery in hierarchy."""

    def test_discover_with_project_configs(self):
        """Test discovery when project configs exist."""
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
        """Test discovery when no project root is found."""
        with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
            configs = discover_config_files()
            # Should only find user-level configs (if they exist)
            # Since we're in a test environment, user configs may or may not exist
            # Just verify it doesn't crash
            self.assertIsInstance(configs, list)

    def test_discover_prioritizes_local_over_regular(self):
        """Test that .local files come before regular files."""
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
        """Test loading from file with no permissions."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({}, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, [])
            self.assertEqual(deny, [])
        finally:
            filepath.unlink()

    def test_load_with_bash_permissions(self):
        """Test loading Bash permissions from file."""
        config = {'permissions': {'allow': ['Bash(git *)', 'Bash(ls *)'], 'deny': ['Bash(rm *)']}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, ['git *', 'ls *'])
            self.assertEqual(deny, ['rm *'])
        finally:
            filepath.unlink()

    def test_load_ignores_non_bash_permissions(self):
        """Test that non-Bash permissions are ignored."""
        config = {'permissions': {'allow': ['Bash(git *)', 'Read(*)', 'Write(*)'], 'deny': ['Bash(rm *)', 'Edit(*)']}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, ['git *'])
            self.assertEqual(deny, ['rm *'])
        finally:
            filepath.unlink()

    def test_load_invalid_json_returns_empty(self):
        """Test that invalid JSON returns empty lists with warning."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('invalid json{]')
            f.flush()
            filepath = Path(f.name)

        try:
            allow, deny = load_permissions_from_file(filepath, 'claude')
            self.assertEqual(allow, [])
            self.assertEqual(deny, [])
        finally:
            filepath.unlink()


class TestMergePermissions(unittest.TestCase):
    """Test merging permissions from multiple sources."""

    def test_merge_empty_lists(self):
        """Test merging when all lists are empty."""
        result = merge_permissions([])
        self.assertEqual(result, ([], []))

    def test_merge_single_source(self):
        """Test merging from a single source."""
        perms = [(['git *', 'ls *'], ['rm *'])]
        allow, deny = merge_permissions(perms)
        self.assertEqual(allow, ['git *', 'ls *'])
        self.assertEqual(deny, ['rm *'])

    def test_merge_multiple_sources(self):
        """Test merging from multiple sources."""
        perms = [(['git *'], ['rm *']), (['ls *'], ['mv *']), (['cat *'], [])]
        allow, deny = merge_permissions(perms)
        self.assertEqual(set(allow), {'git *', 'ls *', 'cat *'})
        self.assertEqual(set(deny), {'rm *', 'mv *'})

    def test_merge_removes_duplicates(self):
        """Test that duplicates are removed."""
        perms = [
            (['git *', 'ls *'], ['rm *']),
            (['git *', 'cat *'], ['rm *', 'mv *']),
        ]
        allow, deny = merge_permissions(perms)
        # Should have unique patterns
        self.assertEqual(len(allow), 3)  # git, ls, cat
        self.assertEqual(len(deny), 2)  # rm, mv

    def test_merge_preserves_order(self):
        """Test that first occurrence order is preserved."""
        perms = [
            (['a', 'b', 'c'], []),
            (['b', 'd'], []),  # 'b' is duplicate
        ]
        allow, deny = merge_permissions(perms)
        # 'a' should come before 'd' since 'a' was first
        self.assertEqual(allow.index('a'), 0)
        self.assertEqual(allow.index('b'), 1)
        self.assertEqual(allow.index('c'), 2)
        self.assertEqual(allow.index('d'), 3)


class TestLoadPermissions(unittest.TestCase):
    """Test the main load_permissions function."""

    def test_load_with_claude_settings_path_env(self):
        """Test that CLAUDE_SETTINGS_PATH takes precedence."""
        config = {'permissions': {'allow': ['Bash(git *)'], 'deny': []}}

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            f.flush()
            filepath = f.name

        try:
            with patch.dict(os.environ, {'CLAUDE_SETTINGS_PATH': filepath}):
                allow, deny = load_permissions()
                self.assertEqual(allow, ['git *'])
                self.assertEqual(deny, [])
        finally:
            Path(filepath).unlink()

    def test_load_without_env_uses_hierarchy(self):
        """Test that hierarchy is used when env var not set."""
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
                    allow, deny = load_permissions()
                    self.assertEqual(allow, ['git *'])

    def test_load_with_no_configs_returns_empty(self):
        """Test that no configs returns empty lists."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CLAUDE_SETTINGS_PATH', None)
            with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
                with patch('pathlib.Path.exists', return_value=False):
                    allow, deny = load_permissions()
                    self.assertEqual(allow, [])
                    self.assertEqual(deny, [])


class TestLoadGovernedTools(unittest.TestCase):
    """Test loading governed tools configuration."""

    def test_load_governed_tools_default(self):
        """Test that default is ['Bash'] when not configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('CLAUDE_SETTINGS_PATH', None)
            with patch('toolguard.config.find_project_root', side_effect=RuntimeError('No project')):
                with patch('pathlib.Path.exists', return_value=False):
                    tools = load_governed_tools()
                    self.assertEqual(tools, ['Bash'])

    def test_load_governed_tools_from_config(self):
        """Test loading governed tools from toolguard_hook.json."""
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
                    tools = load_governed_tools()
                    self.assertEqual(tools, ['Bash', 'mcp__jetbrains__execute_terminal_command'])

    def test_load_governed_tools_merges_sources(self):
        """Test that governed_tools from multiple files are merged (union)."""
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
                    tools = load_governed_tools()
                    # Should have all three unique tools
                    self.assertEqual(set(tools), {'Bash', 'Tool1', 'Tool2'})
                    # Should not have duplicates
                    self.assertEqual(len(tools), 3)


class TestLoadGovernedToolsFromFile(unittest.TestCase):
    """Test loading governed tools from a single file."""

    def test_load_from_valid_file(self):
        """Test loading from a file with governed_tools."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'governed_tools': ['Bash', 'OtherTool']}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = load_governed_tools_from_file(filepath)
            self.assertEqual(tools, ['Bash', 'OtherTool'])
        finally:
            filepath.unlink()

    def test_load_from_missing_file(self):
        """Test that missing file returns empty list."""
        tools = load_governed_tools_from_file(Path('/nonexistent/file.json'))
        self.assertEqual(tools, [])

    def test_load_from_file_without_governed_tools(self):
        """Test that file without governed_tools returns empty list."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'other_key': 'value'}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = load_governed_tools_from_file(filepath)
            self.assertEqual(tools, [])
        finally:
            filepath.unlink()

    def test_load_ignores_non_string_values(self):
        """Test that non-string values in governed_tools are filtered out."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            config = {'governed_tools': ['Bash', 123, None, 'OtherTool']}
            json.dump(config, f)
            f.flush()
            filepath = Path(f.name)

        try:
            tools = load_governed_tools_from_file(filepath)
            self.assertEqual(tools, ['Bash', 'OtherTool'])
        finally:
            filepath.unlink()


class TestMergeGovernedTools(unittest.TestCase):
    """Test merging governed tools from multiple sources."""

    def test_merge_single_list(self):
        """Test merging a single list."""
        result = merge_governed_tools([['Bash', 'Tool1']])
        self.assertEqual(result, ['Bash', 'Tool1'])

    def test_merge_multiple_lists(self):
        """Test merging multiple lists."""
        result = merge_governed_tools([['Bash'], ['Tool1', 'Tool2'], ['Tool3']])
        self.assertEqual(result, ['Bash', 'Tool1', 'Tool2', 'Tool3'])

    def test_merge_removes_duplicates(self):
        """Test that duplicates are removed."""
        result = merge_governed_tools([['Bash', 'Tool1'], ['Bash', 'Tool2']])
        self.assertEqual(result, ['Bash', 'Tool1', 'Tool2'])
        # Verify no duplicates
        self.assertEqual(len(result), len(set(result)))

    def test_merge_preserves_order(self):
        """Test that first occurrence order is preserved."""
        result = merge_governed_tools([['A', 'B'], ['C'], ['B', 'D']])
        # 'B' appears first in first list, so it should come before 'C'
        self.assertEqual(result.index('A'), 0)
        self.assertEqual(result.index('B'), 1)
        self.assertEqual(result.index('C'), 2)
        self.assertEqual(result.index('D'), 3)

    def test_merge_empty_lists(self):
        """Test merging empty lists."""
        result = merge_governed_tools([])
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()
