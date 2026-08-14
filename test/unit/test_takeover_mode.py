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
    TakeoverEnabledConflict,
    load_configuration,
)
from toolguard.hook import load_file_path_patterns
from toolguard.permission_resolution import resolve_command_permission

#: The four blanket allows takeover suppresses by default. Seeded by
#: Configuration.takeover_mode() whether or not takeover is enabled, so a
#: fixture that empties them when disabled is not modelling production.
BLANKET_IGNORED = ("Bash(*)", "Read(*)", "Write(*)", "Edit(*)")


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
        # The native file IS discovered -- its permissions arrive -- so the
        # assertion above is about the takeover_mode section being skipped, not
        # about the file being absent.
        self.assertIn("git status", config.allow_deny_for("Bash")[0])

    def test_enabled_true_in_a_hook_file_switches_takeover_on(self):
        """
        Given a single project toolguard_hook.toml with takeover_mode.enabled = true
        When load_configuration(...).takeover_mode() resolves the configuration
        Then takeover is enabled -- the control case proving the fixtures in this
            class can produce ON as well as OFF
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            "[takeover_mode]\nenabled = true\n"
        )

        tc = load_configuration(project, ignore_env_override=True).takeover_mode()

        self.assertTrue(tc.enabled)
        self.assertIsNone(tc.conflict)

    def test_cross_level_enabled_disagreement_fails_safe_off_and_records_both(self):
        """
        Given a user-level toolguard_hook.toml enabling takeover and a project-level
            one disabling it -- a genuine cross-level disagreement discovered from
            real files, not hand-built layers
        When load_configuration(...).takeover_mode() resolves the configuration
        Then enabled fails safe to False (native prompts stay active) and the
            conflict record cites both levels with their values
        """
        home, project = self.isolate_config_environment()
        (home / ".claude").mkdir()
        (home / ".claude" / "toolguard_hook.toml").write_text(
            "[takeover_mode]\nenabled = true\n"
        )
        (project / ".claude").mkdir()
        (project / ".claude" / "toolguard_hook.toml").write_text(
            "[takeover_mode]\nenabled = false\n"
        )

        tc = load_configuration(project, ignore_env_override=True).takeover_mode()

        self.assertFalse(tc.enabled)
        self.assertIsInstance(tc.conflict, TakeoverEnabledConflict)
        self.assertEqual(
            sorted((value, prov.level) for value, prov in tc.conflict.sources),
            [(False, "project"), (True, "user")],
        )

    def test_non_bool_enabled_does_not_switch_takeover_on(self):
        """
        Given a project toolguard_hook.toml whose takeover_mode.enabled is the
            STRING "true" rather than a boolean
        When load_configuration(...).takeover_mode() resolves the configuration
        Then the level casts no vote and takeover stays off -- a truthy non-bool
            must never be coerced into enabling the highest-consequence switch
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            '[takeover_mode]\nenabled = "true"\n'
        )

        tc = load_configuration(project, ignore_env_override=True).takeover_mode()

        self.assertFalse(tc.enabled)
        self.assertIsNone(tc.conflict)


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
        Given takeover enabled with native Read allows '*' and a specific path, and
            native Read denies of BOTH a specific path and the blanket '*' that
            takeover suppresses on the allow side
        When load_file_path_patterns('Read') runs
        Then both denies survive -- including the '*' that would vanish if the
            ignored set were applied to denies -- while the blanket allow is filtered
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
            "permissions": {
                "allow": ["Read(*)", "Read(~/projects/**)"],
                "deny": ["Read(**/.env)", "Read(*)"],
            }
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

        allow_patterns, deny_patterns = load_file_path_patterns("Read")

        self.assertIn("**/.env", deny_patterns)
        self.assertIn("*", deny_patterns)
        self.assertNotIn("*", allow_patterns)
        self.assertIn("~/projects/**", allow_patterns)

    def test_additional_ignored_pattern_suppresses_a_native_read_allow(self):
        """
        Given takeover enabled and a hook additional_ignored_patterns naming a
            NON-blanket native allow, alongside a native allow it does not name
        When load_file_path_patterns('Read') runs
        Then the named pattern is suppressed and the unnamed one survives -- the
            user-facing knob for extending the ignored set beyond the four blankets
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()

        hook_toml = """
[takeover_mode]
enabled = true
additional_ignored_patterns = ["Read(~/secrets/**)"]
"""
        (claude_dir / "toolguard_hook.toml").write_text(hook_toml)

        settings_json = {
            "permissions": {"allow": ["Read(~/secrets/**)", "Read(~/projects/**)"]}
        }
        (claude_dir / "settings.local.json").write_text(json.dumps(settings_json))

        allow_patterns, _deny_patterns = load_file_path_patterns("Read")

        self.assertNotIn("~/secrets/**", allow_patterns)
        self.assertIn("~/projects/**", allow_patterns)


class TestBashTakeoverFiltering(unittest.TestCase):
    """Takeover filtering of native Bash allows, through the live resolve_command_permission path."""

    @staticmethod
    def _make_bash_config(
        native_allows,
        hook_allows,
        hook_denies,
        takeover_enabled,
        *,
        additional_ignored=(),
        no_match_fallback="ask",
    ):
        """Build (Configuration, TakeoverConfig) from a native layer and a hook layer for Bash.

        ``no_match_fallback`` defaults to production's own default rather than
        'deny', so a test reaching the no-match branch cannot be handed a verdict
        its author did not choose (proposed ticket 47).
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
        # The pattern lists are identical either way: `enabled` must be the only
        # difference between an ON and an OFF fixture, or the pair stops
        # measuring the switch.
        takeover = TakeoverConfig(
            enabled=takeover_enabled,
            ignored_allow_patterns=BLANKET_IGNORED,
            additional_ignored_patterns=additional_ignored,
            no_match_fallback=no_match_fallback,
        )
        return config, takeover

    def _resolve(self, config, takeover, command):
        """Resolve *command* with *takeover* patched in; assert the patch was consulted."""
        with patch.object(
            Configuration, "takeover_mode", return_value=takeover
        ) as takeover_mock:
            verdict = resolve_command_permission(config, "Bash", command)
        self.assertTrue(
            takeover_mock.called, "the takeover_mode patch was never consulted"
        )
        return verdict

    def test_native_blanket_bash_allow_suppressed_when_takeover_enabled(self):
        """
        Given takeover mode enabled, native settings allowing Bash(*), and a
            toolguard_hook that only allows 'git *'
        When 'ls /tmp' -- which only the native Bash(*) covers -- is resolved
        Then the native allow is suppressed, nothing matches, and the command
            takes the configured no_match_fallback ('ask') with no matched rule
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=["Bash(git *)"],
            hook_denies=[],
            takeover_enabled=True,
        )
        verdict = self._resolve(config, takeover, "ls /tmp")
        self.assertEqual(verdict.decision, "ask")
        self.assertIsNone(verdict.matched_rule)

    def test_native_blanket_bash_allow_not_suppressed_when_takeover_disabled(self):
        """
        Given the SAME fixture as the enabled case with takeover mode disabled
        When 'ls /tmp' is resolved
        Then the native Bash(*) allow survives and allows the command -- the
            opposite verdict, so the pair observes the switch itself
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=["Bash(git *)"],
            hook_denies=[],
            takeover_enabled=False,
        )
        verdict = self._resolve(config, takeover, "ls /tmp")
        self.assertEqual(verdict.decision, "allow")
        self.assertEqual(verdict.matched_rule, "*")
        self.assertEqual(verdict.provenance.source_type, "claude")

    def test_hook_deny_still_fires_when_takeover_enabled(self):
        """
        Given takeover mode enabled, native settings allowing Bash(*), and a
            toolguard_hook deny for 'rm *'
        When 'rm -rf /' is resolved
        Then the hook deny -- not the fail-closed empty-extraction path -- produces
            the deny, evidenced by matched_rule naming the deny pattern
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=[],
            hook_denies=["Bash(rm *)"],
            takeover_enabled=True,
        )
        verdict = self._resolve(config, takeover, "rm -rf /")
        self.assertEqual(verdict.decision, "deny")
        self.assertEqual(verdict.matched_rule, "rm *")
        self.assertEqual(verdict.provenance.source_type, "toolguard_hook")

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
            ignored_allow_patterns=BLANKET_IGNORED,
            additional_ignored_patterns=(),
            no_match_fallback="ask",
        )
        verdict = self._resolve(config, takeover, "git status")
        self.assertEqual(verdict.decision, "allow")
        self.assertEqual(verdict.matched_rule, "*")
        self.assertEqual(verdict.provenance.source_type, "toolguard_hook")

    def test_additional_ignored_pattern_suppresses_a_native_bash_allow(self):
        """
        Given takeover enabled with 'Bash(git *)' in additional_ignored_patterns,
            a native allow for exactly that pattern, and an unrelated hook allow
        When 'git status' is resolved
        Then the native allow is suppressed and the command takes the no-match
            fallback -- the extension knob reaching the permission path
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(git *)"],
            hook_allows=["Bash(echo *)"],
            hook_denies=[],
            takeover_enabled=True,
            additional_ignored=("Bash(git *)",),
        )
        verdict = self._resolve(config, takeover, "git status")
        self.assertEqual(verdict.decision, "ask")
        self.assertIsNone(verdict.matched_rule)

    def test_additional_ignored_pattern_inert_when_takeover_disabled(self):
        """
        Given the SAME fixture with takeover disabled
        When 'git status' is resolved
        Then the native allow survives -- additional_ignored_patterns is gated on
            enabled, exactly like the blanket list
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(git *)"],
            hook_allows=["Bash(echo *)"],
            hook_denies=[],
            takeover_enabled=False,
            additional_ignored=("Bash(git *)",),
        )
        verdict = self._resolve(config, takeover, "git status")
        self.assertEqual(verdict.decision, "allow")
        self.assertEqual(verdict.matched_rule, "git *")

    def test_configured_deny_fallback_decides_a_suppressed_command(self):
        """
        Given the suppression fixture with no_match_fallback explicitly 'deny'
        When 'ls /tmp' is resolved
        Then the verdict is deny with no matched rule -- the deny comes from the
            CONFIGURED fallback, not from a rule and not from the fail-closed
            empty-extraction path (production's own default is 'ask')
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=["Bash(git *)"],
            hook_denies=[],
            takeover_enabled=True,
            no_match_fallback="deny",
        )
        verdict = self._resolve(config, takeover, "ls /tmp")
        self.assertEqual(verdict.decision, "deny")
        self.assertIsNone(verdict.matched_rule)

    def test_configured_deny_fallback_survives_suppression_of_every_rule(self):
        """
        Given the canonical takeover setup -- native settings carrying only the
            blanket Bash(*), a toolguard_hook with no Bash rules yet, takeover on,
            and an explicit no_match_fallback of 'deny'
        When 'ls /tmp' is resolved
        Then the configured 'deny' governs. It does not: takeover suppresses the
            only Bash allow, has_any_rules() reads that FILTERED view and reports
            the tool unconfigured, and the hardcoded 'ask' for an unconfigured tool
            silently overrides the user's fail-closed setting. RED ON PURPOSE --
            asserting the correct behaviour, not the current one. Do not relax it
            to 'ask'; see the module report for the has_any_rules() analysis.
        """
        config, takeover = self._make_bash_config(
            native_allows=["Bash(*)"],
            hook_allows=[],
            hook_denies=[],
            takeover_enabled=True,
            no_match_fallback="deny",
        )
        verdict = self._resolve(config, takeover, "ls /tmp")
        self.assertEqual(verdict.decision, "deny")


if __name__ == "__main__":
    unittest.main()
