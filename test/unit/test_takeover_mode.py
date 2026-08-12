"""
Unit tests for takeover mode: toolguard as sole gatekeeper while Claude's
native permission system carries blanket allows.
"""

import json
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
    load_configuration,
)
from toolguard.hook import load_file_path_patterns
from toolguard.permission_resolution import resolve_command_permission


class TestTakeoverModeConfig(ConfigIsolationMixin, unittest.TestCase):
    """Test loading takeover_mode configuration via the hierarchical API."""

    def test_default_config_when_no_files(self):
        """
        Given a project with no toolguard_hook config files at all
        When load_configuration(...).takeover_mode() resolves the configuration
        Then takeover is disabled, the default blanket ignored patterns are
            present in ignored_allow_patterns, and no_match_fallback is 'ask'
        """
        _home, project = self.isolate_config_environment()
        config = load_configuration(project, ignore_env_override=True)

        tc = config.takeover_mode()
        self.assertFalse(tc.enabled)
        self.assertIn("Bash(*)", tc.ignored_allow_patterns)
        self.assertIn("Read(*)", tc.ignored_allow_patterns)
        self.assertIn("Write(*)", tc.ignored_allow_patterns)
        self.assertIn("Edit(*)", tc.ignored_allow_patterns)
        self.assertEqual(tc.additional_ignored_patterns, ())
        self.assertEqual(tc.no_match_fallback, "ask")

    def test_takeover_mode_not_loaded_from_claude_settings(self):
        """
        Given takeover_mode defined only in settings.local.json (native Claude config)
        When load_configuration(...).takeover_mode() resolves the configuration
        Then the setting is ignored and takeover remains disabled (toolguard reads
            takeover from toolguard_hook files only, never from settings.json)
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()

        settings_content = {
            "takeover_mode": {
                "enabled": True,
                "ignored_allow_patterns": ["Bash(*)"],
            },
            "permissions": {"allow": ["Bash(git status)"]},
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings_content))

        config = load_configuration(project, ignore_env_override=True)

        tc = config.takeover_mode()
        self.assertFalse(tc.enabled)


class TestFilePathToolTakeoverFiltering(ConfigIsolationMixin, unittest.TestCase):
    """Test that takeover mode filtering applies to file path tools (Read, Write, Edit)."""

    def test_filters_blanket_read_pattern(self):
        """
        Given takeover enabled with native Read(*) and a specific hook Read pattern
        When load_file_path_patterns('Read') runs
        Then the blanket '*' is filtered and only the hook's '~/projects/**' remains
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()

        hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Read(~/projects/**)"]
"""
        (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

        settings_json = {"permissions": {"allow": ["Read(*)", "Bash(*)"]}}
        (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        self.assertNotIn("*", allow_patterns)
        self.assertIn("~/projects/**", allow_patterns)

    def test_filters_blanket_write_pattern(self):
        """
        Given takeover enabled with native Write(*) and a specific hook Write pattern
        When load_file_path_patterns('Write') runs
        Then the blanket '*' is filtered and only the hook's '~/projects/**' remains
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
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

        allow_patterns, deny_patterns = load_file_path_patterns("Write")

        self.assertNotIn("*", allow_patterns)
        self.assertIn("~/projects/**", allow_patterns)

    def test_does_not_filter_file_patterns_when_disabled(self):
        """
        Given takeover disabled with native Read(*) and a hook Read pattern
        When load_file_path_patterns('Read') runs
        Then both '*' and '~/projects/**' are present (no filtering)
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
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

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        self.assertIn("*", allow_patterns)
        self.assertIn("~/projects/**", allow_patterns)

    def test_never_filters_toolguard_hook_file_patterns(self):
        """
        Given takeover enabled with the toolguard_hook itself allowing Read(*)
        When load_file_path_patterns('Read') runs
        Then the hook's '*' remains because toolguard_hook file patterns are never filtered
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()

        hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Read(*)"]
"""
        (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        self.assertIn("*", allow_patterns)

    def test_file_deny_patterns_not_filtered(self):
        """
        Given takeover enabled with native Read allow '*' and a native Read deny pattern
        When load_file_path_patterns('Read') runs
        Then the deny pattern remains while the blanket allow '*' is filtered
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
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

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        self.assertIn("**/.env", deny_patterns)
        self.assertNotIn("*", allow_patterns)


class TestBashTakeoverFiltering(unittest.TestCase):
    """Takeover filtering of native Bash allows, through the live resolve_command_permission path."""

    @staticmethod
    def _make_bash_config(native_allows, hook_allows, hook_denies, takeover_enabled):
        """Build (Configuration, TakeoverConfig) from a native layer and a hook layer for Bash."""
        native_layer = ConfigLayer(
            Provenance("project", "claude", "json", Path("/p/settings.local.json"), 0),
            MappingProxyType({"permissions": {"allow": native_allows, "deny": []}}),
        )
        hook_layer = ConfigLayer(
            Provenance(
                "project",
                "toolguard_hook",
                "toml",
                Path("/p/toolguard_hook.toml"),
                0,
            ),
            MappingProxyType(
                {"permissions": {"allow": hook_allows, "deny": hook_denies}}
            ),
        )
        config = Configuration(layers=(hook_layer, native_layer))
        takeover = TakeoverConfig(
            enabled=takeover_enabled,
            ignored_allow_patterns=(
                ("Bash(*)", "Read(*)", "Write(*)", "Edit(*)")
                if takeover_enabled
                else ()
            ),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )
        return config, takeover

    def _resolve(self, config, command):
        """Drive one Bash command through resolve_command_permission; return (decision, reason)."""
        resolved = resolve_command_permission(config, "Bash", command)
        return resolved.decision, resolved.reason

    def test_native_blanket_bash_allow_suppressed_when_takeover_enabled(self):
        """
        Given takeover mode enabled, native settings allowing Bash(*), and a
            toolguard_hook deny for 'rm *' with no hook allow
        When 'rm -rf /' is resolved through resolve_command_permission
        Then the native Bash(*) allow is suppressed by takeover filtering so the
            command reaches no allow at any level and is denied
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=[],
            hook_denies=["Bash(rm *)"],
            takeover_enabled=True,
        )
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            decision, _reason = self._resolve(config, "rm -rf /")
        self.assertEqual(decision, "deny")

    def test_native_blanket_bash_allow_not_suppressed_when_takeover_disabled(self):
        """
        Given takeover mode disabled, native settings allowing Bash(*), and a
            toolguard_hook deny for 'rm *'
        When 'rm -rf /' is resolved through resolve_command_permission
        Then the native Bash(*) allow is NOT filtered, so the allow at the
            native level wins (unless the hook-level deny matches first at its
            level) -- specifically the deny fires here because hook level is
            more specific and deny-first within level wins
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=[],
            hook_denies=["Bash(rm *)"],
            takeover_enabled=False,
        )
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            decision, _reason = self._resolve(config, "rm -rf /")
        self.assertEqual(decision, "deny")

    def test_toolguard_hook_bash_allow_not_filtered_by_takeover(self):
        """
        Given takeover mode enabled and a toolguard_hook layer allowing Bash(*)
            (not a native Claude settings layer), with no deny rules
        When 'git status' is resolved through resolve_command_permission
        Then the hook's Bash(*) allow is never filtered and the command is allowed
        """
        hook_layer = ConfigLayer(
            Provenance(
                "project",
                "toolguard_hook",
                "toml",
                Path("/p/toolguard_hook.toml"),
                0,
            ),
            MappingProxyType({"permissions": {"allow": ["Bash(*)"], "deny": []}}),
        )
        config = Configuration(layers=(hook_layer,))
        takeover = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=("Bash(*)", "Read(*)", "Write(*)", "Edit(*)"),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            decision, _reason = self._resolve(config, "git status")
        self.assertEqual(decision, "allow")

    def test_native_bash_allow_suppressed_specific_command_denied(self):
        """
        Given takeover enabled, native settings with Bash(*), and a toolguard_hook
            that only allows 'git *' (no deny rules)
        When 'ls /tmp' is resolved (matches native Bash(*) but NOT hook 'git *')
        Then the native Bash(*) allow is suppressed by takeover, the hook has no
            matching allow for 'ls', and the command is denied fail-closed
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=["Bash(git *)"],
            hook_denies=[],
            takeover_enabled=True,
        )
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            decision, _reason = self._resolve(config, "ls /tmp")
        self.assertEqual(decision, "deny")


if __name__ == "__main__":
    unittest.main()
