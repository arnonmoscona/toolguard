"""
Unit tests for config_divergence module.
"""

import json
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from toolguard.config_divergence import (
    check_and_warn_divergence,
    cleanup_old_markers,
    create_marker_file,
    find_divergent_patterns,
    get_marker_file_path,
    get_native_permissions,
    get_toolguard_permissions,
    marker_exists_for_today,
)


class TestMarkerFiles(unittest.TestCase):
    """Test marker file operations."""

    def test_get_marker_file_path(self):
        """Test marker file path generation."""
        logs_dir = Path('/tmp/logs')
        test_date = date(2025, 2, 5)
        marker_path = get_marker_file_path(logs_dir, test_date)

        self.assertEqual(marker_path, Path('/tmp/logs/.toolguard-divergence-warned-2025-02-05'))

    def test_marker_exists_for_today(self):
        """Test checking for today's marker file."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Should not exist initially
            self.assertFalse(marker_exists_for_today(logs_dir))

            # Create marker for today
            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            # Should exist now
            self.assertTrue(marker_exists_for_today(logs_dir))

    def test_create_marker_file(self):
        """Test creating marker file."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / 'logs'

            # Directory doesn't exist yet
            self.assertFalse(logs_dir.exists())

            # Create marker file
            create_marker_file(logs_dir)

            # Directory and marker should exist
            self.assertTrue(logs_dir.exists())
            self.assertTrue(marker_exists_for_today(logs_dir))

    def test_cleanup_old_markers(self):
        """Test cleaning up old marker files."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create markers for various dates
            today = date.today()
            old_date = today - timedelta(days=10)
            recent_date = today - timedelta(days=3)

            old_marker = get_marker_file_path(logs_dir, old_date)
            recent_marker = get_marker_file_path(logs_dir, recent_date)
            today_marker = get_marker_file_path(logs_dir, today)

            old_marker.touch()
            recent_marker.touch()
            today_marker.touch()

            # Cleanup markers older than 7 days
            cleanup_old_markers(logs_dir, days=7)

            # Old marker should be deleted, recent ones should remain
            self.assertFalse(old_marker.exists())
            self.assertTrue(recent_marker.exists())
            self.assertTrue(today_marker.exists())


class TestGetNativePermissions(unittest.TestCase):
    """Test extracting permissions from settings.local.json."""

    def test_extract_bash_patterns(self):
        """Test extracting Bash patterns from native config."""
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'

            config = {
                'permissions': {
                    'allow': [
                        'Bash(git status:*)',
                        'Bash(ls:*)',
                        'mcp__basic-memory__read_note',  # Not a governed tool
                        'WebSearch',  # Not a governed tool
                    ],
                    'deny': ['Bash(rm -rf:*)'],
                    'ask': ['Bash(git push:*)'],
                }
            }

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertEqual(result['allow'], ['Bash(git status:*)', 'Bash(ls:*)'])
            self.assertEqual(result['deny'], ['Bash(rm -rf:*)'])
            self.assertEqual(result['ask'], ['Bash(git push:*)'])

    def test_extract_file_tool_patterns(self):
        """Test extracting Read/Write/Edit patterns from native config."""
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'

            config = {'permissions': {'allow': ['Read(/tmp/**)', 'Write(/tmp/**)', 'Edit(/tmp/**)', 'Bash(ls:*)']}}

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertIn('Read(/tmp/**)', result['allow'])
            self.assertIn('Write(/tmp/**)', result['allow'])
            self.assertIn('Edit(/tmp/**)', result['allow'])
            self.assertIn('Bash(ls:*)', result['allow'])

    def test_missing_file(self):
        """Test handling missing settings.local.json."""
        result = get_native_permissions(Path('/nonexistent/settings.local.json'))

        self.assertEqual(result, {'allow': [], 'deny': [], 'ask': []})

    def test_invalid_json(self):
        """Test handling invalid JSON."""
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'
            settings_path.write_text('{ invalid json }')

            result = get_native_permissions(settings_path)

            self.assertEqual(result, {'allow': [], 'deny': [], 'ask': []})


class TestGetToolguardPermissions(unittest.TestCase):
    """Test extracting permissions from toolguard_hook files."""

    def test_extract_from_json(self):
        """Test extracting from toolguard_hook.json."""
        with TemporaryDirectory() as tmpdir:
            hook_path = Path(tmpdir) / 'toolguard_hook.json'

            config = {'permissions': {'allow': ['Bash(git status:*)', 'Read(/tmp/**)'], 'deny': ['Bash(rm -rf:*)']}}

            hook_path.write_text(json.dumps(config))

            config_files = [(hook_path, 'toolguard_hook', 'json')]
            result = get_toolguard_permissions(config_files)

            self.assertEqual(result['allow'], ['Bash(git status:*)', 'Read(/tmp/**)'])
            self.assertEqual(result['deny'], ['Bash(rm -rf:*)'])
            self.assertEqual(result['ask'], [])

    def test_ignore_claude_settings(self):
        """Test that Claude settings files are ignored."""
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / 'settings.local.json'

            config = {'permissions': {'allow': ['Bash(git push:*)']}}

            settings_path.write_text(json.dumps(config))

            config_files = [(settings_path, 'claude', 'json')]
            result = get_toolguard_permissions(config_files)

            # Should be empty since we ignore claude settings
            self.assertEqual(result, {'allow': [], 'deny': [], 'ask': []})

    def test_merge_multiple_files(self):
        """Test merging permissions from multiple toolguard_hook files."""
        with TemporaryDirectory() as tmpdir:
            hook1 = Path(tmpdir) / 'toolguard_hook.json'
            hook2 = Path(tmpdir) / 'toolguard_hook.local.json'

            config1 = {'permissions': {'allow': ['Bash(git status:*)']}}
            config2 = {'permissions': {'allow': ['Bash(ls:*)']}}

            hook1.write_text(json.dumps(config1))
            hook2.write_text(json.dumps(config2))

            config_files = [(hook1, 'toolguard_hook', 'json'), (hook2, 'toolguard_hook', 'json')]

            result = get_toolguard_permissions(config_files)

            self.assertIn('Bash(git status:*)', result['allow'])
            self.assertIn('Bash(ls:*)', result['allow'])

    def test_deduplicate_patterns(self):
        """Test that duplicate patterns are not repeated."""
        with TemporaryDirectory() as tmpdir:
            hook1 = Path(tmpdir) / 'toolguard_hook.json'
            hook2 = Path(tmpdir) / 'toolguard_hook.local.json'

            config1 = {'permissions': {'allow': ['Bash(git status:*)']}}
            config2 = {'permissions': {'allow': ['Bash(git status:*)']}}

            hook1.write_text(json.dumps(config1))
            hook2.write_text(json.dumps(config2))

            config_files = [(hook1, 'toolguard_hook', 'json'), (hook2, 'toolguard_hook', 'json')]

            result = get_toolguard_permissions(config_files)

            # Should only appear once
            self.assertEqual(result['allow'].count('Bash(git status:*)'), 1)


class TestFindDivergentPatterns(unittest.TestCase):
    """Test finding divergent patterns."""

    def test_find_new_patterns(self):
        """Test finding patterns in native but not in toolguard."""
        native = {'allow': ['Bash(git status:*)', 'Bash(git push:*)'], 'deny': [], 'ask': []}

        toolguard = {'allow': ['Bash(git status:*)'], 'deny': [], 'ask': []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result['allow'], ['Bash(git push:*)'])
        self.assertEqual(result['deny'], [])
        self.assertEqual(result['ask'], [])

    def test_ignore_patterns_in_takeover_mode(self):
        """Test that ignored patterns are filtered out in takeover mode."""
        native = {'allow': ['Bash(git status:*)', 'Bash(uv run pytest:*)', 'Bash(open:*)'], 'deny': [], 'ask': []}

        toolguard = {'allow': ['Bash(git status:*)'], 'deny': [], 'ask': []}

        ignored = ['Bash(uv run pytest:*)', 'Bash(open:*)']

        result = find_divergent_patterns(native, toolguard, ignored)

        # Should not include ignored patterns
        self.assertEqual(result['allow'], [])

    def test_exact_string_matching(self):
        """Test that pattern matching is exact (no wildcards)."""
        native = {
            'allow': ['Bash(git status:*)', 'Bash(git status:*)  '],  # Trailing space
            'deny': [],
            'ask': [],
        }

        toolguard = {'allow': ['Bash(git status:*)'], 'deny': [], 'ask': []}

        result = find_divergent_patterns(native, toolguard, [])

        # Trailing space makes it different
        self.assertIn('Bash(git status:*)  ', result['allow'])

    def test_all_permission_types(self):
        """Test finding divergences in allow, deny, and ask."""
        native = {'allow': ['Bash(ls:*)'], 'deny': ['Bash(rm:*)'], 'ask': ['Bash(git push:*)']}

        toolguard = {'allow': [], 'deny': [], 'ask': []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result['allow'], ['Bash(ls:*)'])
        self.assertEqual(result['deny'], ['Bash(rm:*)'])
        self.assertEqual(result['ask'], ['Bash(git push:*)'])

    def test_no_divergence(self):
        """Test when there's no divergence."""
        native = {'allow': ['Bash(git status:*)'], 'deny': [], 'ask': []}

        toolguard = {'allow': ['Bash(git status:*)'], 'deny': [], 'ask': []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result, {'allow': [], 'deny': [], 'ask': []})


class TestCheckAndWarnDivergence(unittest.TestCase):
    """Test the main divergence check function."""

    def test_no_divergence(self):
        """Test when there's no divergence."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'

            # Create project marker so discover_config_files works
            (project_root / 'pyproject.toml').touch()

            # Create matching configs
            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)

            config = {'permissions': {'allow': ['Bash(git status:*)']}}

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / '.claude' / 'toolguard_hook.json'
            hook_config = {'permissions': {'allow': ['Bash(git status:*)']}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {'enabled': False, 'ignored_allow_patterns': []}

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # No divergence
            self.assertEqual(result, [])

    def test_with_divergence(self):
        """Test when divergence exists."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'

            # Create project marker so discover_config_files works
            (project_root / 'pyproject.toml').touch()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)

            config = {'permissions': {'allow': ['Bash(git status:*)', 'Bash(git push:*)']}}

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / '.claude' / 'toolguard_hook.json'
            hook_config = {'permissions': {'allow': ['Bash(git status:*)']}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {'enabled': False, 'ignored_allow_patterns': []}

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # Should find divergence
            self.assertIn('Bash(git push:*)', result)

    def test_deduplication(self):
        """Test that warnings are deduplicated."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'

            # Create project marker so discover_config_files works
            (project_root / 'pyproject.toml').touch()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)

            config = {'permissions': {'allow': ['Bash(git push:*)']}}

            settings_path.write_text(json.dumps(config))

            takeover_config = {'enabled': False, 'ignored_allow_patterns': []}

            # First call should find divergence
            result1 = check_and_warn_divergence(project_root, logs_dir, takeover_config)
            self.assertIn('Bash(git push:*)', result1)

            # Second call should be deduplicated
            result2 = check_and_warn_divergence(project_root, logs_dir, takeover_config)
            self.assertEqual(result2, [])

    def test_takeover_mode_ignored_patterns(self):
        """Test that ignored patterns work in takeover mode."""
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / 'logs'

            # Create project marker so discover_config_files works
            (project_root / 'pyproject.toml').touch()

            settings_path = project_root / '.claude' / 'settings.local.json'
            settings_path.parent.mkdir(parents=True)

            config = {'permissions': {'allow': ['Bash(uv run pytest:*)', 'Bash(git push:*)']}}

            settings_path.write_text(json.dumps(config))

            takeover_config = {
                'enabled': True,
                'ignored_allow_patterns': ['Bash(uv run pytest:*)'],
                'additional_ignored_patterns': [],
            }

            result = check_and_warn_divergence(project_root, logs_dir, takeover_config)

            # Should only find git push, not pytest
            self.assertIn('Bash(git push:*)', result)
            self.assertNotIn('Bash(uv run pytest:*)', result)


if __name__ == '__main__':
    unittest.main()
