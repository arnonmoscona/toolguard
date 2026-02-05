"""
Unit tests for takeover mode functionality in toolguard.

Tests the takeover mode feature that allows toolguard to act as sole gatekeeper
while Claude's native permission system has blanket allows.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.config import load_takeover_mode_config, load_permissions


class TestTakeoverModeConfig(unittest.TestCase):
    """Test loading takeover_mode configuration."""

    def test_default_config_when_no_files(self):
        """Test default configuration when no config files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertFalse(config['enabled'])
            self.assertEqual(config['ignored_allow_patterns'], [])
            self.assertEqual(config['additional_ignored_patterns'], [])
            self.assertEqual(config['no_match_fallback'], 'deny')

    def test_load_takeover_mode_from_toml(self):
        """Test loading takeover_mode from TOML config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            toml_content = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["Bash(*)", "Read(*)"]
additional_ignored_patterns = ["Write(*)"]
no_match_fallback = "warn_deny"
"""
            (claude_dir / 'toolguard_hook.toml').write_text(toml_content)

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertTrue(config['enabled'])
            self.assertIn('Bash(*)', config['ignored_allow_patterns'])
            self.assertIn('Read(*)', config['ignored_allow_patterns'])
            self.assertIn('Write(*)', config['additional_ignored_patterns'])
            self.assertEqual(config['no_match_fallback'], 'warn_deny')

    def test_load_takeover_mode_from_json(self):
        """Test loading takeover_mode from JSON config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            json_content = {
                'takeover_mode': {
                    'enabled': True,
                    'ignored_allow_patterns': ['Bash(*)', 'Read(*)'],
                    'additional_ignored_patterns': [],
                    'no_match_fallback': 'deny',
                }
            }
            (claude_dir / 'toolguard_hook.json').write_text(json.dumps(json_content))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertTrue(config['enabled'])
            self.assertIn('Bash(*)', config['ignored_allow_patterns'])
            self.assertIn('Read(*)', config['ignored_allow_patterns'])

    def test_merge_takeover_mode_from_multiple_files(self):
        """Test merging takeover_mode from multiple config files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Project-level config
            project_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["Bash(*)"]
no_match_fallback = "deny"
"""
            (claude_dir / 'toolguard_hook.toml').write_text(project_toml)

            # User-level config
            user_dir = Path.home() / '.claude'
            user_dir.mkdir(exist_ok=True)
            user_toml = """
[takeover_mode]
ignored_allow_patterns = ["Read(*)"]
additional_ignored_patterns = ["Write(*)"]
"""
            user_toml_path = user_dir / 'toolguard_hook.toml'
            user_toml_path.write_text(user_toml)

            try:
                with patch('toolguard.config.find_project_root', return_value=project_dir):
                    config = load_takeover_mode_config()

                # Should merge patterns from both files
                self.assertTrue(config['enabled'])
                self.assertIn('Bash(*)', config['ignored_allow_patterns'])
                self.assertIn('Read(*)', config['ignored_allow_patterns'])
                self.assertIn('Write(*)', config['additional_ignored_patterns'])
            finally:
                # Clean up user config
                if user_toml_path.exists():
                    user_toml_path.unlink()

    def test_takeover_mode_not_loaded_from_claude_settings(self):
        """Test that takeover_mode is NOT loaded from Claude settings files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Put takeover_mode in settings.local.json (should be ignored)
            settings_content = {
                'takeover_mode': {'enabled': True, 'ignored_allow_patterns': ['Bash(*)']},
                'permissions': {'allow': ['Bash(git status)']},
            }
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_content))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            # Should use default config (takeover_mode from settings.json is ignored)
            self.assertFalse(config['enabled'])


class TestTakeoverModePermissionFiltering(unittest.TestCase):
    """Test permission filtering with takeover mode enabled."""

    @patch.dict('os.environ', {}, clear=True)
    def test_filters_native_patterns_when_enabled(self):
        """Test that native Claude config patterns are filtered when takeover enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Toolguard hook config with takeover mode
            hook_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["*", "ls:*"]

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            # Native Claude settings with blanket allow
            settings_json = {'permissions': {'allow': ['Bash(*)', 'Bash(ls:*)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Should only include git status from toolguard_hook, not blanket allows
            self.assertIn('git status', allow_patterns)
            self.assertNotIn('*', allow_patterns)
            self.assertNotIn('ls:*', allow_patterns)

    @patch.dict('os.environ', {}, clear=True)
    def test_does_not_filter_when_disabled(self):
        """Test that patterns are NOT filtered when takeover mode disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Toolguard hook config with takeover mode DISABLED
            hook_toml = """
[takeover_mode]
enabled = false
ignored_allow_patterns = ["*"]

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            # Native Claude settings with blanket allow
            settings_json = {'permissions': {'allow': ['Bash(*)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Should include both patterns (no filtering)
            self.assertIn('git status', allow_patterns)
            self.assertIn('*', allow_patterns)

    @patch.dict('os.environ', {}, clear=True)
    def test_never_filters_toolguard_hook_patterns(self):
        """Test that toolguard_hook patterns are NEVER filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Toolguard hook config with pattern that matches ignored_allow_patterns
            hook_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["*"]

[permissions]
allow = ["Bash(*)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Should include * from toolguard_hook (never filtered)
            self.assertIn('*', allow_patterns)

    @patch.dict('os.environ', {}, clear=True)
    def test_exact_string_matching(self):
        """Test that pattern matching is exact string comparison, not pattern matching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Takeover mode ignores exact pattern "git *"
            hook_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["git *"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            # Native config has various git patterns
            settings_json = {'permissions': {'allow': ['Bash(git *)', 'Bash(git status)', 'Bash(git log)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Only exact match "git *" should be filtered
            self.assertNotIn('git *', allow_patterns)
            self.assertIn('git status', allow_patterns)
            self.assertIn('git log', allow_patterns)

    @patch.dict('os.environ', {}, clear=True)
    def test_additional_ignored_patterns(self):
        """Test that additional_ignored_patterns are also filtered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["ls:*"]
additional_ignored_patterns = ["cat:*"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            settings_json = {'permissions': {'allow': ['Bash(ls:*)', 'Bash(cat:*)', 'Bash(git status)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Both ignored and additional patterns should be filtered
            self.assertNotIn('ls:*', allow_patterns)
            self.assertNotIn('cat:*', allow_patterns)
            self.assertIn('git status', allow_patterns)

    @patch.dict('os.environ', {}, clear=True)
    def test_deny_patterns_not_filtered(self):
        """Test that deny patterns are NOT filtered by takeover mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["rm -rf:*"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            settings_json = {'permissions': {'allow': ['Bash(ls:*)'], 'deny': ['Bash(rm -rf:*)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, deny_patterns = load_permissions()

            # Deny pattern should remain (not filtered)
            self.assertIn('rm -rf:*', deny_patterns)


class TestNoMatchFallback(unittest.TestCase):
    """Test no_match_fallback behavior."""

    def test_deny_fallback_silent(self):
        """Test that 'deny' fallback denies silently."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
no_match_fallback = "deny"

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertEqual(config['no_match_fallback'], 'deny')

    def test_warn_deny_fallback(self):
        """Test that 'warn_deny' fallback is configured correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
no_match_fallback = "warn_deny"

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertEqual(config['no_match_fallback'], 'warn_deny')


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility when takeover_mode not configured."""

    def test_no_takeover_mode_section_uses_defaults(self):
        """Test that missing takeover_mode section uses default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            # Config without takeover_mode section
            hook_toml = """
[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                config = load_takeover_mode_config()

            # Should use default config
            self.assertFalse(config['enabled'])
            self.assertEqual(config['no_match_fallback'], 'deny')

    @patch.dict('os.environ', {}, clear=True)
    def test_behavior_unchanged_when_disabled(self):
        """Test that behavior is unchanged when takeover mode disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / 'project'
            project_dir.mkdir()
            (project_dir / '.git').mkdir()
            claude_dir = project_dir / '.claude'
            claude_dir.mkdir()

            hook_toml = """
[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / 'toolguard_hook.toml').write_text(hook_toml)

            settings_json = {'permissions': {'allow': ['Bash(*)']}}
            (claude_dir / 'settings.local.json').write_text(json.dumps(settings_json))

            with patch('toolguard.config.find_project_root', return_value=project_dir):
                allow_patterns, _ = load_permissions()

            # Should include patterns from both files (default behavior)
            self.assertIn('git status', allow_patterns)
            self.assertIn('*', allow_patterns)


if __name__ == '__main__':
    unittest.main()
