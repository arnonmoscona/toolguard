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

from toolguard.config import load_takeover_mode_config
from toolguard.hook import load_file_path_patterns


class TestTakeoverModeConfig(unittest.TestCase):
    """Test loading takeover_mode configuration."""

    def test_default_config_when_no_files(self):
        """
        Given a project with no toolguard config files
        When load_takeover_mode_config runs
        Then takeover is disabled, the default blanket ignored patterns are present, and no_match_fallback is 'deny'
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertFalse(config["enabled"])
            # Default ignored_allow_patterns includes standard blanket patterns
            self.assertIn("Bash(*)", config["ignored_allow_patterns"])
            self.assertIn("Read(*)", config["ignored_allow_patterns"])
            self.assertIn("Write(*)", config["ignored_allow_patterns"])
            self.assertIn("Edit(*)", config["ignored_allow_patterns"])
            self.assertEqual(config["additional_ignored_patterns"], [])
            self.assertEqual(config["no_match_fallback"], "deny")

    def test_load_takeover_mode_from_toml(self):
        """
        Given a toolguard_hook.toml with a takeover_mode section
        When load_takeover_mode_config runs
        Then the enabled flag, ignored and additional patterns, and no_match_fallback are read from the TOML
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            toml_content = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["Bash(*)", "Read(*)"]
additional_ignored_patterns = ["Write(*)"]
no_match_fallback = "warn_deny"
"""
            (claude_dir / "toolguard_hook.toml").write_text(toml_content)

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertTrue(config["enabled"])
            self.assertIn("Bash(*)", config["ignored_allow_patterns"])
            self.assertIn("Read(*)", config["ignored_allow_patterns"])
            self.assertIn("Write(*)", config["additional_ignored_patterns"])
            self.assertEqual(config["no_match_fallback"], "warn_deny")

    def test_load_takeover_mode_from_json(self):
        """
        Given a toolguard_hook.json with a takeover_mode section
        When load_takeover_mode_config runs
        Then the enabled flag and ignored_allow_patterns are read from the JSON
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            json_content = {
                "takeover_mode": {
                    "enabled": True,
                    "ignored_allow_patterns": ["Bash(*)", "Read(*)"],
                    "additional_ignored_patterns": [],
                    "no_match_fallback": "deny",
                }
            }
            (claude_dir / "toolguard_hook.json").write_text(json.dumps(json_content))

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertTrue(config["enabled"])
            self.assertIn("Bash(*)", config["ignored_allow_patterns"])
            self.assertIn("Read(*)", config["ignored_allow_patterns"])

    def test_merge_takeover_mode_from_multiple_files(self):
        """
        Given project-level and user-level toolguard_hook.toml files with takeover settings
        When load_takeover_mode_config runs
        Then the patterns from both files are merged into the resulting config
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Project-level config
            project_toml = """
[takeover_mode]
enabled = true
ignored_allow_patterns = ["Bash(*)"]
no_match_fallback = "deny"
"""
            (claude_dir / "toolguard_hook.toml").write_text(project_toml)

            # User-level config
            user_dir = Path.home() / ".claude"
            user_dir.mkdir(exist_ok=True)
            user_toml = """
[takeover_mode]
ignored_allow_patterns = ["Read(*)"]
additional_ignored_patterns = ["Write(*)"]
"""
            user_toml_path = user_dir / "toolguard_hook.toml"
            user_toml_path.write_text(user_toml)

            try:
                with patch(
                    "toolguard.config.find_project_root", return_value=project_dir
                ):
                    config = load_takeover_mode_config()

                # Should merge patterns from both files
                self.assertTrue(config["enabled"])
                self.assertIn("Bash(*)", config["ignored_allow_patterns"])
                self.assertIn("Read(*)", config["ignored_allow_patterns"])
                self.assertIn("Write(*)", config["additional_ignored_patterns"])
            finally:
                # Clean up user config
                if user_toml_path.exists():
                    user_toml_path.unlink()

    def test_takeover_mode_not_loaded_from_claude_settings(self):
        """
        Given takeover_mode defined only in settings.local.json
        When load_takeover_mode_config runs
        Then the setting is ignored and takeover remains disabled (defaults)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Put takeover_mode in settings.local.json (should be ignored)
            settings_content = {
                "takeover_mode": {
                    "enabled": True,
                    "ignored_allow_patterns": ["Bash(*)"],
                },
                "permissions": {"allow": ["Bash(git status)"]},
            }
            (claude_dir / "settings.local.json").write_text(
                json.dumps(settings_content)
            )

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            # Should use default config (takeover_mode from settings.json is ignored)
            self.assertFalse(config["enabled"])


class TestNoMatchFallback(unittest.TestCase):
    """Test no_match_fallback behavior."""

    def test_deny_fallback_silent(self):
        """
        Given a toolguard_hook configuring no_match_fallback = "deny"
        When load_takeover_mode_config runs
        Then the resolved config reports no_match_fallback as 'deny'
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
no_match_fallback = "deny"

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertEqual(config["no_match_fallback"], "deny")

    def test_warn_deny_fallback(self):
        """
        Given a toolguard_hook configuring no_match_fallback = "warn_deny"
        When load_takeover_mode_config runs
        Then the resolved config reports no_match_fallback as 'warn_deny'
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
no_match_fallback = "warn_deny"

[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            self.assertEqual(config["no_match_fallback"], "warn_deny")


class TestBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility when takeover_mode not configured."""

    def test_no_takeover_mode_section_uses_defaults(self):
        """
        Given a toolguard_hook with no takeover_mode section
        When load_takeover_mode_config runs
        Then takeover is disabled and no_match_fallback defaults to 'deny'
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # Config without takeover_mode section
            hook_toml = """
[permissions]
allow = ["Bash(git status)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                config = load_takeover_mode_config()

            # Should use default config
            self.assertFalse(config["enabled"])
            self.assertEqual(config["no_match_fallback"], "deny")


class TestFilePathToolTakeoverFiltering(unittest.TestCase):
    """Test that takeover mode filtering applies to file path tools (Read, Write, Edit)."""

    @patch.dict("os.environ", {}, clear=True)
    def test_filters_blanket_read_pattern(self):
        """
        Given takeover enabled with native Read(*) and a specific hook Read pattern
        When load_file_path_patterns('Read') runs
        Then the blanket '*' is filtered and only the hook's '~/projects/**' remains
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Read(~/projects/**)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            # Native Claude settings with blanket Read(*)
            settings_json = {"permissions": {"allow": ["Read(*)", "Bash(*)"]}}
            (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                allow_patterns, deny_patterns = load_file_path_patterns("Read")

            # Blanket * should be filtered; specific pattern from toolguard_hook remains
            self.assertNotIn("*", allow_patterns)
            self.assertIn("~/projects/**", allow_patterns)

    @patch.dict("os.environ", {}, clear=True)
    def test_filters_blanket_write_pattern(self):
        """
        Given takeover enabled with native Write(*) and a specific hook Write pattern
        When load_file_path_patterns('Write') runs
        Then the blanket '*' is filtered and only the hook's '~/projects/**' remains
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Write(~/projects/**)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            settings_json = {"permissions": {"allow": ["Write(*)", "Bash(*)"]}}
            (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                allow_patterns, deny_patterns = load_file_path_patterns("Write")

            self.assertNotIn("*", allow_patterns)
            self.assertIn("~/projects/**", allow_patterns)

    @patch.dict("os.environ", {}, clear=True)
    def test_does_not_filter_file_patterns_when_disabled(self):
        """
        Given takeover disabled with native Read(*) and a hook Read pattern
        When load_file_path_patterns('Read') runs
        Then both '*' and '~/projects/**' are present (no filtering)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = false

[permissions]
allow = ["Read(~/projects/**)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            settings_json = {"permissions": {"allow": ["Read(*)"]}}
            (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                allow_patterns, deny_patterns = load_file_path_patterns("Read")

            # Both patterns should be present (no filtering)
            self.assertIn("*", allow_patterns)
            self.assertIn("~/projects/**", allow_patterns)

    @patch.dict("os.environ", {}, clear=True)
    def test_never_filters_toolguard_hook_file_patterns(self):
        """
        Given takeover enabled with the toolguard_hook itself allowing Read(*)
        When load_file_path_patterns('Read') runs
        Then the hook's '*' remains because toolguard_hook file patterns are never filtered
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            # toolguard_hook has Read(*) - should NOT be filtered even with takeover
            hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Read(*)"]
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                allow_patterns, deny_patterns = load_file_path_patterns("Read")

            # * from toolguard_hook should remain (never filtered)
            self.assertIn("*", allow_patterns)

    @patch.dict("os.environ", {}, clear=True)
    def test_file_deny_patterns_not_filtered(self):
        """
        Given takeover enabled with native Read allow '*' and a native Read deny pattern
        When load_file_path_patterns('Read') runs
        Then the deny pattern remains while the blanket allow '*' is filtered
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir) / "project"
            project_dir.mkdir()
            (project_dir / ".git").mkdir()
            claude_dir = project_dir / ".claude"
            claude_dir.mkdir()

            hook_toml = """
[takeover_mode]
enabled = true
"""
            (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

            settings_json = {
                "permissions": {"allow": ["Read(*)"], "deny": ["Read(**/.env)"]}
            }
            (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

            with patch("toolguard.config.find_project_root", return_value=project_dir):
                allow_patterns, deny_patterns = load_file_path_patterns("Read")

            # Deny pattern should remain
            self.assertIn("**/.env", deny_patterns)
            # Allow * should be filtered
            self.assertNotIn("*", allow_patterns)


if __name__ == "__main__":
    unittest.main()
