"""
Unit tests for takeover mode functionality in toolguard.

Tests the takeover mode feature that allows toolguard to act as sole gatekeeper
while Claude's native permission system has blanket allows.

These tests use the current hierarchical API (``Configuration.takeover_mode()``)
rather than the removed ``load_takeover_mode_config`` legacy loader.  Scenarios
already covered by ``test_configuration.py`` (pattern-list union across levels,
no_match_fallback resolution, enabled conflict detection) were dropped to avoid
duplication; see the implementation report for the full drop/port decision log.
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
from toolguard.permission_resolution import resolve_permission_detailed
from toolguard.permissions import decide_command_at_level_detailed


class TestTakeoverModeConfig(ConfigIsolationMixin, unittest.TestCase):
    """Test loading takeover_mode configuration via the hierarchical API."""

    def test_default_config_when_no_files(self):
        """
        Given a project with no toolguard_hook config files at all
        When load_configuration(...).takeover_mode() resolves the configuration
        Then takeover is disabled, the default blanket ignored patterns are
            present in ignored_allow_patterns, and no_match_fallback is 'ask'
            (the TOO-15 default, unrelated to takeover.enabled which is False
            here regardless)
        """
        _home, project = self.isolate_config_environment()
        config = load_configuration(project, ignore_env_override=True)

        tc = config.takeover_mode()
        self.assertFalse(tc.enabled)
        # Default ignored_allow_patterns includes standard blanket patterns.
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

        # Put takeover_mode in settings.local.json -- should be ignored.
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
        # takeover_mode in settings.json is ignored; defaults should apply.
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

        # Native Claude settings with blanket Read(*)
        settings_json = {"permissions": {"allow": ["Read(*)", "Bash(*)"]}}
        (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        # Blanket * should be filtered; specific pattern from toolguard_hook remains
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

        # Both patterns should be present (no filtering)
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

        # toolguard_hook has Read(*) - should NOT be filtered even with takeover
        hook_toml = """
[takeover_mode]
enabled = true

[permissions]
allow = ["Read(*)"]
"""
        (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        # * from toolguard_hook should remain (never filtered)
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

        # Deny pattern should remain
        self.assertIn("**/.env", deny_patterns)
        # Allow * should be filtered
        self.assertNotIn("*", allow_patterns)


class TestBashTakeoverFiltering(unittest.TestCase):
    """
    Test that takeover mode suppresses native Bash(*) allows in the live
    resolve_permission_detailed path.

    These tests exercise the full stack from Configuration.permission_layers
    through resolve_permission_detailed, confirming that a native blanket
    Bash(*) allow cannot bypass a toolguard deny when takeover is enabled,
    while a toolguard_hook Bash(*) allow is never suppressed.
    """

    @staticmethod
    def _make_bash_config(native_allows, hook_allows, hook_denies, takeover_enabled):
        """
        Build a Configuration with a native layer and a hook layer for Bash.

        Args:
            native_allows: List of Bash allow patterns in wrapped form for the
                native (settings.json) layer, e.g. ['Bash(*)'].
            hook_allows: List of Bash allow patterns for the toolguard_hook layer.
            hook_denies: List of Bash deny patterns for the toolguard_hook layer.
            takeover_enabled: Whether takeover mode is enabled.

        Returns:
            A Configuration instance with the described layers and takeover config.
        """
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
        # Patch takeover_mode to return the desired state without file I/O.
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
        """
        Drive a single Bash command through resolve_permission_detailed.

        Returns:
            Tuple of (decision, reason).
        """

        def _decide(allow_patterns, deny_patterns, ask_patterns=()):
            return decide_command_at_level_detailed(
                command,
                list(allow_patterns),
                list(deny_patterns),
                ask_patterns=list(ask_patterns),
            )

        resolved = resolve_permission_detailed(config, "Bash", _decide)
        return resolved.decision, resolved.reason

    def test_native_blanket_bash_allow_suppressed_when_takeover_enabled(self):
        """
        Given takeover mode enabled, native settings allowing Bash(*), and a
            toolguard_hook deny for 'rm *' with no hook allow
        When 'rm -rf /' is resolved through resolve_permission_detailed
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
        When 'rm -rf /' is resolved through resolve_permission_detailed
        Then the native Bash(*) allow is NOT filtered, so the allow at the
            native level wins (unless the hook-level deny matches first at its
            level) -- specifically the deny fires here because hook level is
            more specific and deny-first within level wins
        """
        # NOTE: hook_layer is more specific (lower specificity index in layers),
        # so hook deny fires first. This test confirms that disabling takeover
        # does not change which level is consulted first.
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=[],
            hook_denies=["Bash(rm *)"],
            takeover_enabled=False,
        )
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            decision, _reason = self._resolve(config, "rm -rf /")
        # Hook layer (most specific) fires first; it has no allow but has deny rm*.
        # deny-first within a level means deny fires before considering native level.
        self.assertEqual(decision, "deny")

    def test_toolguard_hook_bash_allow_not_filtered_by_takeover(self):
        """
        Given takeover mode enabled and a toolguard_hook layer allowing Bash(*)
            (not a native Claude settings layer), with no deny rules
        When 'git status' is resolved through resolve_permission_detailed
        Then the hook's Bash(*) allow is never filtered and the command is allowed
        """
        # Only a hook layer with Bash(*) allow -- no native layer.
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
