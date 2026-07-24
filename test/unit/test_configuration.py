"""
Unit tests for the TOO-8 Phase 1 public config abstraction.

These tests exercise :func:`toolguard.config.load_configuration` and the
:class:`Configuration` public API, plus the internal delegating helper
``config_sync_settings_from_sources`` that ``auto_migrate`` uses.

Run with:
    uv run python -m unittest discover -s test -t .
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

import toolguard.config as config_module
from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Issue,
    Provenance,
    TakeoverConfig,
    TakeoverEnabledConflict,
    ToolPatternLayer,
    config_sync_settings_from_sources,
    load_configuration,
)


class TestLoadConfigurationHierarchy(ConfigIsolationMixin, unittest.TestCase):
    """load_configuration() discovery + layering."""

    def test_layers_built_from_project(self):
        """
        Given a project with settings.local.json and toolguard_hook.json under .claude
        When load_configuration discovers them
        Then a Configuration with at least two layers is returned, each with provenance and a read-only mapping, and the project files are labelled 'project'
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )
        (claude_dir / "toolguard_hook.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(ls *)"]}})
        )
        config = load_configuration()

        self.assertIsInstance(config, Configuration)
        self.assertGreaterEqual(len(config.layers), 2)
        # Every layer carries provenance and a read-only mapping.
        for layer in config.layers:
            self.assertIsInstance(layer, ConfigLayer)
            self.assertIsInstance(layer.provenance, Provenance)
            self.assertIsInstance(layer.content, MappingProxyType)
        project_levels = [
            layer.provenance.level
            for layer in config.layers
            if str(project) in str(layer.provenance.path)
        ]
        self.assertTrue(project_levels)
        self.assertTrue(all(level == "project" for level in project_levels))

    def test_unparseable_file_skipped(self):
        """
        Given a project with an unparseable toolguard_hook.json and a valid settings.local.json
        When load_configuration runs
        Then the unparseable file is skipped and the valid layer's Bash allow patterns are still available
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.json").write_text("not valid json{")
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )
        config = load_configuration()
        # The valid settings layer is still present.
        allow, _ = config.allow_deny_for("Bash")
        self.assertIn("git *", allow)

    def test_non_dict_top_level_json_skipped_not_crashed(self):
        """
        Given a toolguard_hook.json whose top level is a JSON array (syntactically
            valid, but the wrong shape) alongside a valid settings.local.json
        When load_configuration runs
        Then the wrong-shape file is skipped with a warning (not an uncaught
            AttributeError/TypeError propagating out of load_configuration) and
            the valid layer's Bash allow patterns are still available
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.json").write_text(json.dumps([1, 2, 3]))
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )
        config = load_configuration()
        allow, _ = config.allow_deny_for("Bash")
        self.assertIn("git *", allow)

    def test_claude_settings_path_single_file(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a single settings file with no adjacent hook
        When load_configuration runs
        Then exactly one layer is produced, labelled 'explicit' and recognized as native
        """
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"permissions": {"allow": ["Bash(git *)"]}}, f)
            f.flush()
            path = f.name
        try:
            with patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": path}):
                config = load_configuration()
            self.assertEqual(len(config.layers), 1)
            self.assertEqual(config.layers[0].provenance.level, "explicit")
            self.assertTrue(config.layers[0].is_native)
        finally:
            Path(path).unlink()

    def test_claude_settings_path_with_adjacent_hook(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a settings file with an adjacent toolguard_hook.json
        When load_configuration runs
        Then both a 'claude' and a 'toolguard_hook' source layer are produced
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(git *)"]}}))
            hook = Path(tmp) / "toolguard_hook.json"
            hook.write_text(json.dumps({"permissions": {"allow": ["Bash(ls *)"]}}))
            with patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": str(settings)}):
                config = load_configuration()
            types = [layer.provenance.source_type for layer in config.layers]
            self.assertIn("claude", types)
            self.assertIn("toolguard_hook", types)


class TestPermissionLayers(unittest.TestCase):
    """permission_layers() and allow_deny_for() flattening + takeover filtering."""

    def test_allow_deny_union_dedup(self):
        """
        Given two hook layers with overlapping Read allow patterns and one deny
        When allow_deny_for('Read') flattens them (no takeover)
        Then allow is the order-preserving de-duplicated union and deny carries the single pattern
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "json", Path("/p/toolguard_hook.json")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["Read(/tmp/**)", "Read(/a/**)"],
                            "deny": ["Read(/s/**)"],
                        }
                    }
                ),
            ),
            ConfigLayer(
                Provenance(
                    "user", "toolguard_hook", "json", Path("/u/toolguard_hook.json")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["Read(/a/**)", "Read(/b/**)"],
                            "deny": [],
                        }
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, deny = config.allow_deny_for("Read")
        self.assertEqual(allow, ("/tmp/**", "/a/**", "/b/**"))
        self.assertEqual(deny, ("/s/**",))

    def test_only_requested_tool_extracted(self):
        """
        Given a layer with Read, Write, and Bash allow patterns
        When allow_deny_for('Read') runs
        Then only the Read pattern is returned and Write/Bash are ignored
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["Read(/tmp/**)", "Write(/tmp/*)", "Bash(git *)"],
                            "deny": [],
                        }
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _ = config.allow_deny_for("Read")
        self.assertEqual(allow, ("/tmp/**",))

    def test_takeover_filters_native_allow_only(self):
        """
        Given a native layer and a hook layer that both allow 'Read(*)', with takeover ignoring 'Read(*)'
        When permission_layers('Read') is computed
        Then the native layer drops the blanket '*' (keeping '/tmp/**') while the hook layer keeps '*'
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType(
                    {"permissions": {"allow": ["Read(*)", "Read(/tmp/**)"], "deny": []}}
                ),
            ),
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "json", Path("/p/toolguard_hook.json")
                ),
                MappingProxyType({"permissions": {"allow": ["Read(*)"], "deny": []}}),
            ),
        )
        config = Configuration(layers=layers)
        takeover = TakeoverConfig(True, ("Read(*)",), (), "deny")
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            per_layer = config.permission_layers("Read")
        # Native layer: blanket '*' filtered out, '/tmp/**' kept.
        self.assertEqual(per_layer[0].allow, ("/tmp/**",))
        # Hook layer: '*' kept (never filtered).
        self.assertEqual(per_layer[1].allow, ("*",))

    def test_per_layer_provenance_preserved(self):
        """
        Given a project hook layer and a user hook layer
        When permission_layers('Bash') is computed
        Then the resulting ToolPatternLayers retain their provenance with project before user
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {"permissions": {"allow": ["Bash(git *)"], "deny": []}}
                ),
            ),
            ConfigLayer(
                Provenance(
                    "user", "toolguard_hook", "json", Path("/u/toolguard_hook.json")
                ),
                MappingProxyType(
                    {"permissions": {"allow": ["Bash(ls *)"], "deny": []}}
                ),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            per_layer = config.permission_layers("Bash")
        self.assertEqual(per_layer[0].provenance.level, "project")
        self.assertEqual(per_layer[1].provenance.level, "user")
        self.assertIsInstance(per_layer[0], ToolPatternLayer)

    def test_non_dict_permissions_tolerated(self):
        """
        Given a layer whose 'permissions' value is a string rather than a dict
        When allow_deny_for('Bash') runs
        Then extraction does not crash and returns empty allow and deny tuples
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "json", Path("/p/toolguard_hook.json")
                ),
                MappingProxyType({"permissions": "oops-not-a-dict"}),
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, deny = config.allow_deny_for("Bash")
        self.assertEqual(allow, ())
        self.assertEqual(deny, ())


class TestScalarsAndConfigSync(unittest.TestCase):
    """scalar() resolution and config_sync_settings()."""

    def _hook_layer(self, level, content):
        return ConfigLayer(
            Provenance(
                level, "toolguard_hook", "json", Path(f"/{level}/toolguard_hook.json")
            ),
            MappingProxyType(content),
        )

    def test_scalar_dotted_more_specific_wins(self):
        """
        Given project and user hook layers each defining config_sync.backup_dir
        When scalar('config_sync.backup_dir') resolves the value
        Then the project (more-specific) value wins (TOO-8 Phase 5 more-specific-wins)

        Phase 5 flips the Phase-1 user-wins (last-occurrence) resolution to
        more-specific-wins: layers are ordered most-specific first, so the first
        layer that defines the key wins. See
        test_config_sync_conflict_is_project_wins for the explicit pin.
        """
        layers = (
            self._hook_layer(
                "project", {"config_sync": {"backup_dir": "proj/backups"}}
            ),
            self._hook_layer("user", {"config_sync": {"backup_dir": "user/backups"}}),
        )
        config = Configuration(layers=layers)
        self.assertEqual(
            config.scalar("config_sync.backup_dir", "default"), "proj/backups"
        )

    def test_config_sync_conflict_is_project_wins(self):
        """
        Given project and user hook layers with conflicting config_sync values
        When scalar() and config_sync_settings() resolve them under Phase 5
        Then the PROJECT (more-specific) value wins on every conflict

        This pins the conflict DIRECTION after the TOO-8 Phase 5 flip from
        user-wins to more-specific-wins (decision #4). Layers are most-specific
        first, so the first defining layer (project) wins.
        """
        layers = (
            self._hook_layer(
                "project",
                {"config_sync": {"auto_migrate": True, "backup_dir": "proj/backups"}},
            ),
            self._hook_layer(
                "user",
                {"config_sync": {"auto_migrate": False, "backup_dir": "user/backups"}},
            ),
        )
        config = Configuration(layers=layers)

        # scalar() resolves project-wins (more-specific-wins) on conflict.
        self.assertEqual(
            config.scalar("config_sync.backup_dir", "default"), "proj/backups"
        )
        self.assertIs(config.scalar("config_sync.auto_migrate", None), True)

        # config_sync_settings() (the public accessor used by the hook) reflects
        # the same more-specific-wins resolution.
        cs = config.config_sync_settings()
        self.assertEqual(cs["backup_dir"], "proj/backups")
        self.assertIs(cs["auto_migrate"], True)

    def test_scalar_default_when_absent(self):
        """
        Given a configuration with no layers
        When scalar('config_sync.backup_dir', 'fallback') resolves
        Then the supplied default 'fallback' is returned
        """
        config = Configuration(layers=())
        self.assertEqual(
            config.scalar("config_sync.backup_dir", "fallback"), "fallback"
        )

    def test_scalar_ignores_native_layers(self):
        """
        Given only a native ('claude') layer that defines config_sync.backup_dir
        When scalar('config_sync.backup_dir', 'default') resolves
        Then the native value is ignored and the default is returned
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType({"config_sync": {"backup_dir": "should-be-ignored"}}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.scalar("config_sync.backup_dir", "default"), "default")

    def test_scalar_bare_top_level_key(self):
        """
        Given a hook layer with a top-level 'some_flag' set to True
        When scalar('some_flag', False) resolves the bare key
        Then it returns True
        """
        layers = (self._hook_layer("project", {"some_flag": True}),)
        config = Configuration(layers=layers)
        self.assertIs(config.scalar("some_flag", False), True)

    def test_config_sync_settings_defaults(self):
        """
        Given a configuration with no layers
        When config_sync_settings() is called
        Then it returns a read-only mapping of the documented defaults that rejects mutation
        """
        config = Configuration(layers=())
        cs = config.config_sync_settings()
        self.assertIsInstance(cs, MappingProxyType)
        self.assertEqual(cs["auto_migrate"], False)
        self.assertEqual(cs["backup_dir"], "logs/config-backups")
        self.assertEqual(cs["auto_sort_on_migrate"], True)
        with self.assertRaises(TypeError):
            cs["auto_migrate"] = True  # read-only


class TestToolguardPermissions(unittest.TestCase):
    """toolguard_permissions() aggregation from hook layers."""

    def test_aggregates_wrapper_intact(self):
        """
        Given a native layer and a hook layer with allow/deny/ask permissions
        When toolguard_permissions() aggregates them
        Then the hook patterns are returned with their tool wrappers intact and the native pattern is skipped
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType({"permissions": {"allow": ["Bash(should-skip)"]}}),
            ),
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "json", Path("/p/toolguard_hook.json")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["Bash(git *)"],
                            "deny": ["Bash(rm *)"],
                            "ask": [],
                        }
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertEqual(perms["allow"], ("Bash(git *)",))
        self.assertEqual(perms["deny"], ("Bash(rm *)",))
        self.assertEqual(perms["ask"], ())
        self.assertNotIn("Bash(should-skip)", perms["allow"])


class TestValidationIssues(unittest.TestCase):
    """validation_issues() structured issue detection (no logging side effects)."""

    def test_duplicate_toml_json_issue(self):
        """
        Given both toolguard_hook.toml and toolguard_hook.json layers at the same base
        When validation_issues() runs
        Then it reports an Issue warning about the duplicate TOML+JSON pair
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "toml",
                    Path("/p/.claude/toolguard_hook.toml"),
                ),
                MappingProxyType({}),
            ),
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "json",
                    Path("/p/.claude/toolguard_hook.json"),
                ),
                MappingProxyType({}),
            ),
        )
        config = Configuration(layers=layers)
        issues = config.validation_issues()
        self.assertTrue(
            any(
                "Both toolguard_hook.toml and toolguard_hook.json" in i.message
                for i in issues
            )
        )
        for i in issues:
            self.assertIsInstance(i, Issue)

    def test_ungoverned_and_unsupported_tools(self):
        """
        Given a hook layer governing only Bash but allowing Read and WebSearch
        When validation_issues() runs
        Then it flags WebSearch as unsupported and Read as supported-but-ungoverned
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "json",
                    Path("/p/.claude/toolguard_hook.json"),
                ),
                MappingProxyType(
                    {
                        "governed_tools": ["Bash"],
                        "permissions": {"allow": ["Read(/tmp/**)", "WebSearch"]},
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        messages = " ".join(i.message for i in config.validation_issues())
        self.assertIn("WebSearch", messages)  # unsupported
        self.assertIn("Read", messages)  # supported but ungoverned

    def test_native_layers_not_validated(self):
        """
        Given only a native settings.local.json layer allowing WebSearch and WebFetch
        When validation_issues() runs
        Then no issues are reported because native layers are not validated
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "claude", "json", Path("/p/.claude/settings.local.json")
                ),
                MappingProxyType({"permissions": {"allow": ["WebSearch", "WebFetch"]}}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.validation_issues(), ())

    def test_non_bool_takeover_enabled_reported_as_error(self):
        """
        Given a hook layer whose takeover_mode.enabled is the string "false" (not a bool)
        When validation_issues() runs
        Then it reports an error Issue naming takeover_mode.enabled and the bad type
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "json",
                    Path("/p/.claude/toolguard_hook.json"),
                ),
                MappingProxyType({"takeover_mode": {"enabled": "false"}}),
            ),
        )
        config = Configuration(layers=layers)
        issues = config.validation_issues()
        matching = [i for i in issues if "takeover_mode.enabled" in i.message]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].level, "error")
        self.assertIn("str", matching[0].message)

    def test_bool_takeover_enabled_not_reported(self):
        """
        Given a hook layer whose takeover_mode.enabled is a real boolean
        When validation_issues() runs
        Then no takeover_mode.enabled issue is reported (valid values are not flagged)
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "json",
                    Path("/p/.claude/toolguard_hook.json"),
                ),
                MappingProxyType({"takeover_mode": {"enabled": False}}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertFalse(
            any(
                "takeover_mode.enabled" in i.message for i in config.validation_issues()
            )
        )


class TestTakeoverConfig(unittest.TestCase):
    """TakeoverConfig normalization helper."""

    def test_normalized_ignored_strips_wrappers(self):
        """
        Given a TakeoverConfig with wrapped and already-bare ignored patterns
        When normalized_ignored_patterns() runs
        Then it returns the frozenset of patterns with tool wrappers stripped and bare ones kept
        """
        tc = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=("Bash(*)", "Read(/tmp/**)"),
            additional_ignored_patterns=("already-bare",),
            no_match_fallback="deny",
        )
        self.assertEqual(
            tc.normalized_ignored_patterns(),
            frozenset({"*", "/tmp/**", "already-bare"}),
        )


class TestImmutability(unittest.TestCase):
    """Public dataclasses are frozen."""

    def test_configuration_frozen(self):
        """
        Given a Configuration instance
        When its layers attribute is reassigned
        Then an exception is raised because the dataclass is frozen
        """
        config = Configuration(layers=())
        with self.assertRaises(Exception):
            config.layers = (1,)

    def test_provenance_frozen(self):
        """
        Given a Provenance instance
        When its level attribute is reassigned
        Then an exception is raised because the dataclass is frozen
        """
        prov = Provenance("project", "claude", "json", Path("/x"))
        with self.assertRaises(Exception):
            prov.level = "user"


class TestInternalHelpers(unittest.TestCase):
    """Delegating helpers used by config_divergence / auto_migrate."""

    def test_config_sync_settings_from_sources_last_wins(self):
        """
        Given two toolguard_hook sources with overlapping config_sync keys
        When config_sync_settings_from_sources merges them
        Then the last source wins on conflict and defaults fill unset keys
        """
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "toolguard_hook.json"
            first.write_text(
                json.dumps({"config_sync": {"auto_migrate": True, "backup_dir": "a"}})
            )
            second = Path(tmp) / "toolguard_hook.local.json"
            second.write_text(json.dumps({"config_sync": {"backup_dir": "b"}}))
            config_files = [
                (first, "toolguard_hook", "json"),
                (second, "toolguard_hook", "json"),
            ]
            result = config_sync_settings_from_sources(config_files)
            self.assertEqual(result["auto_migrate"], True)
            self.assertEqual(result["backup_dir"], "b")  # last wins
            self.assertEqual(result["auto_sort_on_migrate"], True)  # default

    def test_config_sync_settings_from_sources_defaults(self):
        """
        Given an empty list of config sources
        When config_sync_settings_from_sources runs
        Then it returns the full set of documented defaults
        """
        result = config_sync_settings_from_sources([])
        self.assertEqual(
            result,
            {
                "auto_migrate": False,
                "backup_dir": "logs/config-backups",
                "auto_sort_on_migrate": True,
            },
        )

    def test_config_sync_skips_unparseable_and_empty(self):
        """
        Given hook sources where one is unparseable and one has an empty config_sync
        When config_sync_settings_from_sources runs
        Then nothing usable is found and the documented defaults are returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "toolguard_hook.json"
            bad.write_text("}{ not json")
            empty = Path(tmp) / "toolguard_hook.local.json"
            empty.write_text(json.dumps({"config_sync": {}}))
            config_files = [
                (bad, "toolguard_hook", "json"),
                (empty, "toolguard_hook", "json"),
            ]
            result = config_sync_settings_from_sources(config_files)
            # Falls back to defaults since nothing usable was found.
            self.assertEqual(result["auto_migrate"], False)
            self.assertEqual(result["backup_dir"], "logs/config-backups")


class TestGovernedAndTakeoverDelegation(unittest.TestCase):
    """governed_tools() delegation and takeover_mode() hierarchical resolution."""

    @staticmethod
    def _hook_layer(level, content, specificity=0):
        """Build a toolguard_hook ConfigLayer at the given level/specificity."""
        return ConfigLayer(
            Provenance(
                level,
                "toolguard_hook",
                "toml",
                Path(f"/{level}/toolguard_hook.toml"),
                specificity,
            ),
            MappingProxyType(content),
        )

    def test_governed_tools_default_when_unconfigured(self):
        """
        Given a Configuration with no layers
        When Configuration.governed_tools() resolves
        Then it returns the default ('Bash',)
        """
        config = Configuration(layers=())
        self.assertEqual(config.governed_tools(), ("Bash",))

    def test_governed_tools_union_across_three_levels(self):
        """
        Given three hook levels each adding a distinct governed tool (one duplicated)
        When Configuration.governed_tools() resolves the union
        Then all distinct tools appear once, in most-specific-first order
        """
        layers = (
            self._hook_layer("project", {"governed_tools": ["Bash", "Read"]}, 0),
            self._hook_layer("project", {"governed_tools": ["Write"]}, 1),
            self._hook_layer("user", {"governed_tools": ["Read", "Edit"]}, 2),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.governed_tools(), ("Bash", "Read", "Write", "Edit"))

    def test_governed_tools_tolerates_non_list_value(self):
        """
        Given a hook layer whose governed_tools value is a string rather than a list
        When Configuration.governed_tools() resolves
        Then the malformed entry is skipped and the default ('Bash',) is returned
        """
        layers = (self._hook_layer("project", {"governed_tools": "not-a-list"}, 0),)
        config = Configuration(layers=layers)
        self.assertEqual(config.governed_tools(), ("Bash",))

    def test_governed_tools_ignores_native_layers(self):
        """
        Given a native ('claude') layer declaring governed_tools and no hook layer doing so
        When Configuration.governed_tools() resolves
        Then the native list is ignored and the default ('Bash',) is returned
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json"), 0),
                MappingProxyType({"governed_tools": ["Read", "Write"]}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.governed_tools(), ("Bash",))

    def test_takeover_mode_shape(self):
        """
        Given a single toolguard_hook layer with a takeover_mode section
        When Configuration.takeover_mode() resolves it over self.layers
        Then enabled, ignored_allow_patterns (defaults + extras), and no_match_fallback are reflected
        """
        layers = (
            self._hook_layer(
                "project",
                {
                    "takeover_mode": {
                        "enabled": True,
                        "ignored_allow_patterns": ["Bash(*)"],
                        "additional_ignored_patterns": ["Read(/x/**)"],
                        "no_match_fallback": "warn_deny",
                    }
                },
            ),
        )
        config = Configuration(layers=layers)
        tc = config.takeover_mode()
        self.assertTrue(tc.enabled)
        self.assertIn("Bash(*)", tc.ignored_allow_patterns)
        self.assertEqual(tc.additional_ignored_patterns, ("Read(/x/**)",))
        self.assertEqual(tc.no_match_fallback, "warn_deny")
        self.assertIsNone(tc.conflict)


class TestTakeoverEnabledResolution(unittest.TestCase):
    """takeover_mode.enabled single-owner + fail-safe-on-conflict (TOO-8 Phase 5)."""

    @staticmethod
    def _hook_layer(level, content, specificity):
        """Build a toolguard_hook ConfigLayer at the given level/specificity."""
        return ConfigLayer(
            Provenance(
                level,
                "toolguard_hook",
                "toml",
                Path(f"/{level}/toolguard_hook.toml"),
                specificity,
            ),
            MappingProxyType(content),
        )

    def test_enabled_off_when_no_level_sets_it(self):
        """
        Given hook layers that never set takeover_mode.enabled
        When takeover_mode() resolves enabled
        Then enabled is False (default OFF) and there is no conflict
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"no_match_fallback": "deny"}}, 0
            ),
            self._hook_layer("user", {}, 1),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertFalse(tc.enabled)
        self.assertIsNone(tc.conflict)

    def test_enabled_on_when_one_level_sets_true(self):
        """
        Given exactly one hook layer setting takeover_mode.enabled = true
        When takeover_mode() resolves enabled
        Then enabled is True and there is no conflict
        """
        layers = (
            self._hook_layer("project", {}, 0),
            self._hook_layer("user", {"takeover_mode": {"enabled": True}}, 1),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertTrue(tc.enabled)
        self.assertIsNone(tc.conflict)

    def test_enabled_agreement_across_two_levels_no_conflict(self):
        """
        Given two hook layers both setting takeover_mode.enabled = true
        When takeover_mode() resolves enabled
        Then enabled is True and there is no conflict (agreement, not disagreement)
        """
        layers = (
            self._hook_layer("project", {"takeover_mode": {"enabled": True}}, 0),
            self._hook_layer("user", {"takeover_mode": {"enabled": True}}, 1),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertTrue(tc.enabled)
        self.assertIsNone(tc.conflict)

    def test_enabled_conflict_fails_safe_off_and_reports(self):
        """
        Given two hook levels that DISAGREE on takeover_mode.enabled (true vs false)
        When takeover_mode() resolves enabled
        Then enabled is fail-safe False and a TakeoverEnabledConflict cites both sources with provenance
        """
        layers = (
            self._hook_layer("project", {"takeover_mode": {"enabled": True}}, 0),
            self._hook_layer("user", {"takeover_mode": {"enabled": False}}, 1),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertFalse(tc.enabled)
        self.assertIsInstance(tc.conflict, TakeoverEnabledConflict)
        # Both disagreeing sources are recorded, most-specific first.
        values = [v for v, _prov in tc.conflict.sources]
        self.assertEqual(values, [True, False])
        levels = [prov.level for _v, prov in tc.conflict.sources]
        self.assertEqual(levels, ["project", "user"])
        self.assertIn("conflicting values", tc.conflict.describe())

    def test_non_bool_enabled_does_not_vote(self):
        """
        Given one level setting enabled = true and another setting enabled = "false" (a string)
        When takeover_mode() resolves enabled
        Then the non-bool level is ignored (not coerced to a vote), so the single real
        vote wins with no conflict
        """
        layers = (
            self._hook_layer("project", {"takeover_mode": {"enabled": True}}, 0),
            self._hook_layer("user", {"takeover_mode": {"enabled": "false"}}, 1),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertTrue(tc.enabled)
        self.assertIsNone(tc.conflict)

    def test_pattern_lists_union_across_three_levels(self):
        """
        Given three hook levels each adding distinct takeover ignored/additional patterns
        When takeover_mode() resolves the pattern lists
        Then ignored_allow_patterns and additional_ignored_patterns union across all three levels
        """
        layers = (
            self._hook_layer(
                "project",
                {
                    "takeover_mode": {
                        "ignored_allow_patterns": ["Foo(*)"],
                        "additional_ignored_patterns": ["Read(/a/**)"],
                    }
                },
                0,
            ),
            self._hook_layer(
                "project",
                {"takeover_mode": {"additional_ignored_patterns": ["Read(/b/**)"]}},
                1,
            ),
            self._hook_layer(
                "user",
                {"takeover_mode": {"additional_ignored_patterns": ["Read(/c/**)"]}},
                2,
            ),
        )
        tc = Configuration(layers=layers).takeover_mode()
        # Default blanket allows plus the project's extra are all present.
        self.assertIn("Bash(*)", tc.ignored_allow_patterns)
        self.assertIn("Foo(*)", tc.ignored_allow_patterns)
        # additional_ignored_patterns unions across all three levels.
        self.assertEqual(
            tc.additional_ignored_patterns,
            ("Read(/a/**)", "Read(/b/**)", "Read(/c/**)"),
        )

    def test_no_match_fallback_more_specific_wins(self):
        """
        Given project and user hook levels with conflicting no_match_fallback values
        When takeover_mode() resolves no_match_fallback
        Then the project (more-specific) value wins
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"no_match_fallback": "warn_deny"}}, 0
            ),
            self._hook_layer(
                "user", {"takeover_mode": {"no_match_fallback": "deny"}}, 1
            ),
        )
        tc = Configuration(layers=layers).takeover_mode()
        self.assertEqual(tc.no_match_fallback, "warn_deny")


class TestHasAnyRules(unittest.TestCase):
    """
    Configuration.has_any_rules() (TOO-15): distinguishes a tool with NO
    permission rules configured anywhere (allow/deny/ask/hard_deny all empty at
    every level) from a tool that has rules which simply do not match a given
    command/path. The former must resolve to 'ask'; the latter is governed by
    no_match_fallback.
    """

    @staticmethod
    def _hook_layer(level, content, specificity=0):
        """Build a toolguard_hook ConfigLayer at the given level/specificity."""
        return ConfigLayer(
            Provenance(
                level,
                "toolguard_hook",
                "toml",
                Path(f"/{level}/toolguard_hook.toml"),
                specificity,
            ),
            MappingProxyType(content),
        )

    def test_false_when_tool_fully_unconfigured(self):
        """
        Given a hook layer with no permissions/hard_deny section at all for 'Bash'
        When Configuration.has_any_rules('Bash') is checked
        Then it returns False
        """
        layers = (self._hook_layer("project", {}),)
        config = Configuration(layers=layers)
        self.assertFalse(config.has_any_rules("Bash"))

    def test_false_when_no_layers_at_all(self):
        """
        Given a Configuration with zero layers
        When Configuration.has_any_rules('Bash') is checked
        Then it returns False
        """
        config = Configuration(layers=())
        self.assertFalse(config.has_any_rules("Bash"))

    def test_true_when_allow_configured(self):
        """
        Given a hook layer with a Bash allow pattern
        When Configuration.has_any_rules('Bash') is checked
        Then it returns True
        """
        layers = (
            self._hook_layer(
                "project", {"permissions": {"allow": ["Bash(git *)"]}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertTrue(config.has_any_rules("Bash"))

    def test_true_when_only_deny_configured(self):
        """
        Given a hook layer with ONLY a Bash deny pattern (no allow/ask)
        When Configuration.has_any_rules('Bash') is checked
        Then it returns True
        """
        layers = (
            self._hook_layer(
                "project", {"permissions": {"deny": ["Bash(rm *)"]}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertTrue(config.has_any_rules("Bash"))

    def test_true_when_only_ask_configured(self):
        """
        Given a hook layer with ONLY a Bash ask pattern (no allow/deny)
        When Configuration.has_any_rules('Bash') is checked
        Then it returns True
        """
        layers = (
            self._hook_layer(
                "project", {"permissions": {"ask": ["Bash(curl *)"]}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertTrue(config.has_any_rules("Bash"))

    def test_true_when_only_hard_deny_configured(self):
        """
        Given a hook layer with ONLY a [hard_deny] section for Bash (no normal
            permissions section at all)
        When Configuration.has_any_rules('Bash') is checked
        Then it returns True (hard_deny counts as a configured rule)
        """
        layers = (
            self._hook_layer(
                "project", {"hard_deny": {"deny": ["Bash(rm -rf *)"]}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertTrue(config.has_any_rules("Bash"))

    def test_false_is_tool_scoped(self):
        """
        Given a hook layer with rules configured for 'Read' but nothing for 'Bash'
        When Configuration.has_any_rules is checked for each tool
        Then it is True for 'Read' and False for 'Bash'
        """
        layers = (
            self._hook_layer(
                "project", {"permissions": {"allow": ["Read(/tmp/**)"]}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertTrue(config.has_any_rules("Read"))
        self.assertFalse(config.has_any_rules("Bash"))


class TestResolvedNoMatchFallback(unittest.TestCase):
    """
    Configuration.resolved_no_match_fallback() (TOO-15): the top-level
    ``no_match_fallback`` key, with the legacy ``[takeover_mode].no_match_fallback``
    honoured as a backwards-compatible alias when no layer sets the top-level
    key. The top-level key wins when both are set. Applies regardless of
    takeover_mode.enabled. Defaults to 'ask'. The recognized values are 'ask',
    'deny', and 'allow_with_warning'; the deprecated legacy value 'warn_deny'
    (whether set via the top-level key or the ``[takeover_mode]`` alias) is
    normalized to 'allow_with_warning'.
    """

    @staticmethod
    def _hook_layer(level, content, specificity=0):
        """Build a toolguard_hook ConfigLayer at the given level/specificity."""
        return ConfigLayer(
            Provenance(
                level,
                "toolguard_hook",
                "toml",
                Path(f"/{level}/toolguard_hook.toml"),
                specificity,
            ),
            MappingProxyType(content),
        )

    def test_defaults_to_ask_when_nothing_set(self):
        """
        Given no layer sets either the top-level key or the legacy alias
        When Configuration.resolved_no_match_fallback() resolves
        Then it returns 'ask' (TOO-15: the new default, so a fresh install with
            rules configured but an unmatched command is never silently
            bricked -- it prompts instead)
        """
        config = Configuration(layers=(self._hook_layer("project", {}),))
        self.assertEqual(config.resolved_no_match_fallback(), "ask")

    def test_top_level_key_honored(self):
        """
        Given a hook layer setting the top-level 'no_match_fallback' key to
            'allow_with_warning' (the canonical, non-legacy value)
        When Configuration.resolved_no_match_fallback() resolves
        Then it returns 'allow_with_warning' unchanged
        """
        layers = (
            self._hook_layer("project", {"no_match_fallback": "allow_with_warning"}),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow_with_warning")

    def test_value_ask_explicit_is_returned_as_is(self):
        """
        Given a hook layer explicitly setting the top-level 'no_match_fallback'
            key to 'ask' (not merely relying on the default)
        When Configuration.resolved_no_match_fallback() resolves
        Then it returns 'ask'
        """
        layers = (self._hook_layer("project", {"no_match_fallback": "ask"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "ask")

    def test_value_deny_is_returned_as_is(self):
        """
        Given a hook layer setting the top-level 'no_match_fallback' key to 'deny'
        When Configuration.resolved_no_match_fallback() resolves
        Then it returns 'deny'
        """
        layers = (self._hook_layer("project", {"no_match_fallback": "deny"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "deny")

    def test_legacy_alias_warn_deny_via_top_level_key_normalizes(self):
        """
        Given a hook layer setting the top-level 'no_match_fallback' key to the
            deprecated legacy value 'warn_deny' (not under [takeover_mode])
        When Configuration.resolved_no_match_fallback() resolves
        Then it is normalized to the canonical 'allow_with_warning'
        """
        layers = (self._hook_layer("project", {"no_match_fallback": "warn_deny"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow_with_warning")

    def test_legacy_takeover_alias_honored_when_no_top_level_key(self):
        """
        Given only the legacy [takeover_mode].no_match_fallback is set to
            'warn_deny' (no top-level key anywhere)
        When Configuration.resolved_no_match_fallback() resolves
        Then the legacy alias value is used and normalized to 'allow_with_warning'
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"no_match_fallback": "warn_deny"}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow_with_warning")

    def test_top_level_wins_over_legacy_alias_when_both_set(self):
        """
        Given the top-level key is set to 'deny' AND the legacy
            [takeover_mode].no_match_fallback is set to 'warn_deny'
        When Configuration.resolved_no_match_fallback() resolves
        Then the top-level value ('deny') wins
        """
        layers = (
            self._hook_layer(
                "project",
                {
                    "no_match_fallback": "deny",
                    "takeover_mode": {"no_match_fallback": "warn_deny"},
                },
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "deny")

    def test_top_level_wins_even_when_set_at_a_less_specific_level(self):
        """
        Given the legacy alias is set at the MORE-specific (project) level to
            'warn_deny' and the top-level key is set at the LESS-specific (user)
            level to 'deny'
        When Configuration.resolved_no_match_fallback() resolves
        Then the top-level value ('deny') still wins over the legacy alias,
            regardless of relative specificity between the two mechanisms
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"no_match_fallback": "warn_deny"}}, 0
            ),
            self._hook_layer("user", {"no_match_fallback": "deny"}, 1),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "deny")

    def test_top_level_more_specific_layer_wins_among_top_level_setters(self):
        """
        Given two layers both set the top-level key, project='warn_deny' and
            user='deny'
        When Configuration.resolved_no_match_fallback() resolves
        Then the more-specific (project) value wins and is normalized to
            'allow_with_warning' (the deprecated 'warn_deny' alias)
        """
        layers = (
            self._hook_layer("project", {"no_match_fallback": "warn_deny"}, 0),
            self._hook_layer("user", {"no_match_fallback": "deny"}, 1),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow_with_warning")

    def test_native_layer_top_level_key_ignored(self):
        """
        Given ONLY a native ('claude') layer sets a top-level 'no_match_fallback'
            key (toolguard extensions are never read from native settings)
        When Configuration.resolved_no_match_fallback() resolves
        Then the native value is ignored and the default 'ask' is returned
        """
        native_layer = ConfigLayer(
            Provenance("project", "claude", "json", Path("/p/settings.json"), 0),
            MappingProxyType({"no_match_fallback": "warn_deny"}),
        )
        config = Configuration(layers=(native_layer,))
        self.assertEqual(config.resolved_no_match_fallback(), "ask")

    def test_invalid_top_level_value_falls_back_to_ask(self):
        """
        Given a layer sets the top-level 'no_match_fallback' to an unrecognized
            value (a typo / bad config, e.g. 'nonsense' -- note 'ask' is now a
            valid value, not an example of an invalid one)
        When Configuration.resolved_no_match_fallback() resolves
        Then the value is not propagated; it normalizes to the default 'ask'
        """
        layers = (self._hook_layer("project", {"no_match_fallback": "nonsense"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "ask")

    def test_invalid_legacy_alias_value_falls_back_to_ask(self):
        """
        Given only the legacy [takeover_mode].no_match_fallback is set, to an
            unrecognized value (no top-level key anywhere)
        When Configuration.resolved_no_match_fallback() resolves
        Then the bad legacy value normalizes to the default 'ask'
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"no_match_fallback": "bogus"}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "ask")


class TestProvenanceAndIntrospection(unittest.TestCase):
    """Provenance.describe, source_type property, describe_sources."""

    def test_describe_and_source_type(self):
        """
        Given a toolguard_hook TOML provenance and its layer
        When describe(), source_type, and is_native are inspected
        Then describe mentions the level and source, source_type is 'toolguard_hook', and is_native is False
        """
        prov = Provenance(
            "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
        )
        layer = ConfigLayer(prov, MappingProxyType({}))
        self.assertIn("project", prov.describe())
        self.assertIn("toolguard_hook", prov.describe())
        self.assertEqual(layer.source_type, "toolguard_hook")
        self.assertFalse(layer.is_native)

    def test_describe_sources(self):
        """
        Given a configuration with a single claude settings layer
        When describe_sources() is called
        Then it returns one description mentioning the settings.json file
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType({}),
            ),
        )
        config = Configuration(layers=layers)
        descs = config.describe_sources()
        self.assertEqual(len(descs), 1)
        self.assertIn("settings.json", descs[0])


class TestToolguardPermissionsEdgeCases(unittest.TestCase):
    """toolguard_permissions() tolerates malformed permissions."""

    def test_non_dict_permissions_skipped(self):
        """
        Given a hook layer whose 'permissions' value is a list rather than a dict
        When toolguard_permissions() aggregates it
        Then the malformed entry is skipped and allow is empty
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "json", Path("/p/toolguard_hook.json")
                ),
                MappingProxyType({"permissions": ["not", "a", "dict"]}),
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertEqual(perms["allow"], ())


class TestValidationAdditionalSupportedTools(unittest.TestCase):
    """additional_supported_tools suppress the unsupported-tool issue."""

    def test_additional_supported_tool_recognized(self):
        """
        Given a hook layer that declares a custom tool via additional_supported_tools and uses it
        When validation_issues() runs
        Then no 'not a known supported tool' issue is raised for that custom tool
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project",
                    "toolguard_hook",
                    "json",
                    Path("/p/.claude/toolguard_hook.json"),
                ),
                MappingProxyType(
                    {
                        "governed_tools": ["Bash", "mcp__custom__tool"],
                        "additional_supported_tools": ["mcp__custom__tool"],
                        "permissions": {"allow": ["mcp__custom__tool(do *)"]},
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        messages = " ".join(i.message for i in config.validation_issues())
        self.assertNotIn("not a known supported tool", messages)


class TestExplicitModeAdjacentToml(unittest.TestCase):
    """CLAUDE_SETTINGS_PATH with an adjacent toolguard_hook.toml (TOML preferred)."""

    def test_adjacent_toml_layer(self):
        """
        Given CLAUDE_SETTINGS_PATH with both an adjacent toolguard_hook.toml and .json
        When load_configuration runs
        Then the TOML hook layer is used and the JSON one is excluded
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(git *)"]}}))
            hook_toml = Path(tmp) / "toolguard_hook.toml"
            hook_toml.write_text('[permissions]\nallow = ["Bash(ls *)"]\n')
            # A JSON also present, but TOML must win.
            (Path(tmp) / "toolguard_hook.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(skip)"]}})
            )
            with patch.dict(os.environ, {"CLAUDE_SETTINGS_PATH": str(settings)}):
                config = load_configuration()
            formats = {
                layer.provenance.file_format
                for layer in config.layers
                if not layer.is_native
            }
            self.assertIn("toml", formats)
            self.assertNotIn("json", formats)


# ---------------------------------------------------------------------------
# TOO-30: ~/.config/toolguard/rules/ split-file discovery (RED phase)
# ---------------------------------------------------------------------------
#
# These tests exercise the NOT-YET-IMPLEMENTED contract described in the TOO-30
# task recall (basic-memory, project='toolguard',
# implementation/coder-latest-task-recall-too-30-red-phase-tests):
#
#   - toolguard.config._rules_dir()               (new, private)
#   - toolguard.config._discover_rules_files()     (new, private)
#   - toolguard.config._discover_levels()          (existing, gains rules-dir entries)
#   - toolguard.config._level_for_path()           (existing, gains rules-dir 'user' case)
#   - toolguard.config.ConfigLayer.unexpected_keys (new field, default ())
#   - toolguard.config.load_configuration()        (existing, filters rules-dir content)
#   - toolguard.config.Configuration.validation_issues() (existing, new unexpected_keys check)
#
# Per this file's test-hygiene convention (see module docstring/CLAUDE.md), the
# not-yet-existing private names are referenced ONLY inside test method bodies via
# ``config_module.<name>`` (imported once, at the top of this file, alongside the
# other imports -- importing the MODULE itself always succeeds since it exists
# today; only the not-yet-existing ATTRIBUTES on it, referenced inside method
# bodies below, are what fail in isolation) -- never imported into the
# top-of-file ``from toolguard.config import (...)`` block -- so a missing
# attribute fails only the one test method, never collection of this whole file.


def _toml_permissions_block(allow=(), deny=(), ask=()):
    """
    Build a minimal ``[permissions]`` TOML block for a rules-dir test file.

    Args:
        allow: Allow patterns (already tool-wrapped, e.g. ``'Bash(git *)'``).
        deny: Deny patterns, same shape as ``allow``.
        ask: Ask patterns, same shape as ``allow``.

    Returns:
        A TOML source string with a single ``[permissions]`` table.
    """
    lines = ["[permissions]"]
    lines.append("allow = " + json.dumps(list(allow)))
    lines.append("deny = " + json.dumps(list(deny)))
    if ask:
        lines.append("ask = " + json.dumps(list(ask)))
    return "\n".join(lines) + "\n"


class TestRulesDirectoryDiscovery(ConfigIsolationMixin, unittest.TestCase):
    """_rules_dir(), _discover_rules_files(), and end-to-end discovery via
    load_configuration() into the user level."""

    # -- _rules_dir() (white-box, no I/O) -----------------------------------

    def test_rules_dir_uses_xdg_config_home_when_set(self):
        """
        Given XDG_CONFIG_HOME set to a custom path
        When _rules_dir() resolves the rules directory
        Then it returns <XDG_CONFIG_HOME>/toolguard/rules
        """
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/xdg"}, clear=True):
            result = config_module._rules_dir()
        self.assertEqual(result, Path("/custom/xdg") / "toolguard" / "rules")

    def test_rules_dir_defaults_to_home_config_when_xdg_unset(self):
        """
        Given XDG_CONFIG_HOME is not set in the environment
        When _rules_dir() resolves the rules directory
        Then it defaults to ~/.config/toolguard/rules
        """
        with patch.dict(os.environ, {}, clear=True):
            result = config_module._rules_dir()
        self.assertEqual(result, Path.home() / ".config" / "toolguard" / "rules")

    def test_rules_dir_falls_back_to_default_when_xdg_config_home_is_empty(self):
        """
        Given XDG_CONFIG_HOME is set but to an empty string
        When _rules_dir() resolves the rules directory
        Then it falls back to the ~/.config/toolguard/rules default (empty is
        treated as unset, not as a literal empty-string base)
        """
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=True):
            result = config_module._rules_dir()
        self.assertEqual(result, Path.home() / ".config" / "toolguard" / "rules")

    # -- _discover_rules_files() (white-box, flat scan of a real tmp dir) ---

    def test_discover_rules_files_missing_directory_returns_empty(self):
        """
        Given a rules directory path that does not exist on disk
        When _discover_rules_files() scans it
        Then it returns an empty list, not an error
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            result = config_module._discover_rules_files(missing)
        self.assertEqual(result, [])

    def test_discover_rules_files_empty_directory_returns_empty(self):
        """
        Given a rules directory that exists but contains no files
        When _discover_rules_files() scans it
        Then it returns an empty list
        """
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "rules"
            rules_dir.mkdir()
            result = config_module._discover_rules_files(rules_dir)
        self.assertEqual(result, [])

    def test_discover_rules_files_sorted_lexicographically_by_stem(self):
        """
        Given three rules files named 'zeta.toml', 'alpha.json', 'mid.toml'
        When _discover_rules_files() scans the directory
        Then the results are ordered lexicographically by filename stem
        """
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "rules"
            rules_dir.mkdir()
            (rules_dir / "zeta.toml").write_text("[permissions]\n")
            (rules_dir / "alpha.json").write_text("{}")
            (rules_dir / "mid.toml").write_text("[permissions]\n")
            result = config_module._discover_rules_files(rules_dir)
        self.assertEqual([path.stem for path, _fmt in result], ["alpha", "mid", "zeta"])

    def test_discover_rules_files_same_stem_toml_wins_over_json(self):
        """
        Given both gh.toml and gh.json present for the same stem
        When _discover_rules_files() scans the directory
        Then only the TOML entry is returned (format 'toml'); the JSON sibling
        is dropped from the result
        """
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "rules"
            rules_dir.mkdir()
            (rules_dir / "gh.toml").write_text("[permissions]\n")
            (rules_dir / "gh.json").write_text("{}")
            result = config_module._discover_rules_files(rules_dir)
        self.assertEqual(len(result), 1)
        path, fmt = result[0]
        self.assertEqual(path.name, "gh.toml")
        self.assertEqual(fmt, "toml")

    def test_discover_rules_files_ignores_other_extensions_and_subdirectories(self):
        """
        Given a .txt file and a subdirectory alongside a valid gh.toml
        When _discover_rules_files() scans the directory (flat, non-recursive)
        Then only gh.toml is returned; the .txt file and the subdirectory
        (including a .toml file nested inside it) are ignored
        """
        with tempfile.TemporaryDirectory() as tmp:
            rules_dir = Path(tmp) / "rules"
            rules_dir.mkdir()
            (rules_dir / "notes.txt").write_text("ignore me")
            nested = rules_dir / "nested"
            nested.mkdir()
            (nested / "sneaky.toml").write_text("[permissions]\n")
            (rules_dir / "gh.toml").write_text("[permissions]\n")
            result = config_module._discover_rules_files(rules_dir)
        self.assertEqual([path.name for path, _fmt in result], ["gh.toml"])

    # -- end-to-end via load_configuration() --------------------------------

    def test_missing_rules_dir_produces_no_extra_layers_end_to_end(self):
        """
        Given XDG_CONFIG_HOME points at a directory with no toolguard/rules subdir
        When load_configuration() runs
        Then no 'toolguard_hook_rules' layers are produced and loading does not error
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(rules_layers, [])

    def test_empty_rules_dir_produces_no_extra_layers_end_to_end(self):
        """
        Given an existing but empty toolguard/rules directory under XDG_CONFIG_HOME
        When load_configuration() runs
        Then no 'toolguard_hook_rules' layers are produced
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(rules_layers, [])

    def test_rules_dir_non_dict_top_level_skipped_not_crashed(self):
        """
        Given a rules-dir file whose top level is a JSON array (syntactically
            valid, but the wrong shape -- a plausible hand-authoring slip) sitting
            alongside a valid rules-dir file
        When load_configuration() runs
        Then the wrong-shape file is skipped with a warning rather than crashing
            load_configuration() for the whole hook, and the valid file's
            permissions still resolve normally
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "bad.json").write_text(json.dumps([1, 2, 3]))
            (rules_dir / "good.toml").write_text(
                _toml_permissions_block(allow=["Bash(gh *)"])
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("gh *", allow)

    def test_rules_dir_files_become_layers_in_lexicographic_order_end_to_end(self):
        """
        Given two rules-dir files 'alpha.toml' and 'zeta.json', each with a
        distinct Bash allow pattern
        When load_configuration() runs with XDG_CONFIG_HOME pointed at their parent
        Then both become layers, in lexicographic-by-stem order, each labelled
        with level 'user'
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "alpha.toml").write_text(
                _toml_permissions_block(allow=["Bash(alpha *)"])
            )
            (rules_dir / "zeta.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(zeta *)"]}})
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        rules_layers = [
            layer for layer in config.layers if layer.provenance.path.parent == rules_dir
        ]
        self.assertEqual(
            [layer.provenance.path.name for layer in rules_layers],
            ["alpha.toml", "zeta.json"],
        )
        self.assertTrue(all(layer.provenance.level == "user" for layer in rules_layers))

    def test_rules_dir_files_appended_after_primary_user_candidates_end_to_end(self):
        """
        Given a primary ~/.claude/toolguard_hook.toml plus rules-dir files
        'alpha.toml' and 'zeta.json'
        When load_configuration() runs
        Then the user-level layer order is: the primary toolguard_hook.toml
        first, then the rules-dir files in lexicographic order
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "alpha.toml").write_text(
                _toml_permissions_block(allow=["Bash(alpha *)"])
            )
            (rules_dir / "zeta.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(zeta *)"]}})
            )
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            claude_dir = fake_home / ".claude"
            claude_dir.mkdir()
            (claude_dir / "toolguard_hook.toml").write_text(
                _toml_permissions_block(allow=["Bash(primary *)"])
            )
            config = load_configuration()
        # NOTE: filtered by provenance.level, not by path prefix -- the rules
        # directory (xdg/toolguard/rules) is a SIBLING of fake_home, not nested
        # under it, so a path-prefix filter against fake_home would never match
        # the rules-dir layers even with a correct implementation.
        user_level_layers = [
            layer for layer in config.layers if layer.provenance.level == "user"
        ]
        self.assertEqual(
            [layer.provenance.path.name for layer in user_level_layers],
            ["toolguard_hook.toml", "alpha.toml", "zeta.json"],
        )

    def test_rules_dir_duplicate_toml_json_only_toml_layer_and_warning_end_to_end(self):
        """
        Given a same-stem gh.toml and gh.json pair inside the rules directory
        When load_configuration() runs
        Then only the TOML layer is produced for that stem AND
        validation_issues() reports the existing "both formats" warning for it
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "gh.toml").write_text(_toml_permissions_block(allow=["Bash(gh *)"]))
            (rules_dir / "gh.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(gh-json *)"]}})
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        rules_layers = [
            layer for layer in config.layers if layer.provenance.path.parent == rules_dir
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.file_format, "toml")
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertIn("Both gh.toml and gh.json", messages)


class TestRulesDirectoryMergeSemantics(ConfigIsolationMixin, unittest.TestCase):
    """
    Existing generic Configuration methods (permission_levels_with_provenance,
    resolve_permission_detailed, hard_deny, toolguard_permissions, allow_deny_for)
    correctly treat rules-dir-sourced layers as ordinary user-level layers once
    such layers exist -- no new code is needed in those methods (TOO-30 item 9).

    Most tests here construct Configuration directly from hand-built layers
    (zero filesystem I/O, no isolation needed); ConfigIsolationMixin is only
    used by the one end-to-end test that actually calls load_configuration().
    """

    @staticmethod
    def _claude_user_hook_layer(content, specificity):
        """Build a ~/.claude/toolguard_hook.toml-sourced user-level ConfigLayer."""
        return ConfigLayer(
            Provenance(
                "user",
                "toolguard_hook",
                "toml",
                Path("/home/u/.claude/toolguard_hook.toml"),
                specificity,
            ),
            MappingProxyType(content),
        )

    @staticmethod
    def _rules_layer(content, specificity, name="gh.toml"):
        """Build a rules-dir-sourced user-level ConfigLayer."""
        return ConfigLayer(
            Provenance(
                "user",
                "toolguard_hook_rules",
                "toml",
                Path(f"/home/u/.config/toolguard/rules/{name}"),
                specificity,
            ),
            MappingProxyType(content),
        )

    def test_rules_dir_permissions_merge_into_same_user_level_as_claude_hook(self):
        """
        Given a ~/.claude toolguard_hook layer and a rules-dir layer at the SAME
        specificity, each allowing a different Bash pattern
        When permission_levels_with_provenance('Bash') groups the layers
        Then both allow patterns appear in a single collapsed level entry, not two
        """
        layers = (
            self._claude_user_hook_layer(
                {"permissions": {"allow": ["Bash(git *)"], "deny": []}}, specificity=1
            ),
            self._rules_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": []}}, specificity=1
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            levels = config.permission_levels_with_provenance("Bash")
        self.assertEqual(len(levels), 1)
        allow, _deny, _ask, _layers = levels[0]
        self.assertEqual(set(allow), {"git *", "gh *"})

    def test_project_level_deny_still_overrides_rules_dir_allow(self):
        """
        Given a project-level deny on 'gh *' and a (less-specific) rules-dir
        allow on the same pattern
        When resolve_permission_detailed('Bash', ...) resolves the cascade
        Then the project-level deny wins (more-specific-wins across levels,
        unaffected by the new source)
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml"), 0
                ),
                MappingProxyType({"permissions": {"allow": [], "deny": ["Bash(gh *)"]}}),
            ),
            self._rules_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": []}}, specificity=1
            ),
        )
        config = Configuration(layers=layers)

        def _decide(allow, deny, ask):
            if "gh *" in deny:
                return ("deny", "Command matches deny pattern: gh *", "gh *")
            if "gh *" in allow:
                return ("allow", "Command matches allow pattern: gh *", "gh *")
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = config.resolve_permission_detailed("Bash", _decide)
        self.assertEqual(resolved.decision, "deny")

    def test_rules_dir_deny_beats_claude_allow_within_user_level(self):
        """
        Given a ~/.claude allow and a rules-dir deny for the SAME pattern at the
        SAME (user) specificity
        When resolve_permission_detailed('Bash', ...) resolves that level
        Then deny wins within the level (deny-wins-within-a-level, now spanning
        both the ~/.claude source and the rules-dir source)
        """
        layers = (
            self._claude_user_hook_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": []}}, specificity=1
            ),
            self._rules_layer(
                {"permissions": {"allow": [], "deny": ["Bash(gh *)"]}}, specificity=1
            ),
        )
        config = Configuration(layers=layers)

        def _decide(allow, deny, ask):
            if "gh *" in deny:
                return ("deny", "Command matches deny pattern: gh *", "gh *")
            if "gh *" in allow:
                return ("allow", "Command matches allow pattern: gh *", "gh *")
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = config.resolve_permission_detailed("Bash", _decide)
        self.assertEqual(resolved.decision, "deny")

    def test_rules_dir_hard_deny_pooled_with_claude_hard_deny(self):
        """
        Given a ~/.claude [hard_deny] section and a rules-dir [hard_deny] section
        each contributing distinct patterns
        When hard_deny('Bash') pools patterns across all layers
        Then both sources' deny patterns (and the claude source's allow
        carve-out) are present in the pooled result
        """
        layers = (
            self._claude_user_hook_layer(
                {
                    "hard_deny": {
                        "deny": ["Bash(curl *)"],
                        "allow": ["Bash(curl localhost*)"],
                    }
                },
                specificity=1,
            ),
            self._rules_layer({"hard_deny": {"deny": ["Bash(wget *)"]}}, specificity=1),
        )
        config = Configuration(layers=layers)
        deny, allow = config.hard_deny("Bash")
        self.assertIn("curl *", deny)
        self.assertIn("wget *", deny)
        self.assertIn("curl localhost*", allow)

    def test_rules_dir_scalars_have_zero_effect_end_to_end(self):
        """
        Given a rules-dir file that sets governed_tools, no_match_fallback, and
        [takeover_mode].enabled alongside a valid [permissions] block
        When load_configuration() loads it and the resolvers run
        Then governed_tools(), resolved_no_match_fallback(), and
        takeover_mode().enabled do NOT reflect any of those scalar settings
        (confirms the section-restriction actually filters content, not just
        records it for later reporting) WHILE the file's valid [permissions]
        block still loaded and resolves normally (a positive control: without
        it, this test would pass vacuously whenever the file simply failed to
        load at all, which would prove nothing about filtering)
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "sneaky.toml").write_text(
                'governed_tools = ["Write"]\n'
                'no_match_fallback = "deny"\n'
                "[takeover_mode]\n"
                "enabled = true\n"
                "[permissions]\n"
                'allow = ["Bash(gh *)"]\n'
                "deny = []\n"
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        # Positive control: the file's own valid permissions DID load -- so a
        # false pass on the assertions below cannot be explained by the file
        # having simply failed to load at all.
        allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("gh *", allow)
        self.assertEqual(config.governed_tools(), ("Bash",))
        self.assertEqual(config.resolved_no_match_fallback(), "ask")
        self.assertFalse(config.takeover_mode().enabled)

    def test_toolguard_permissions_includes_rules_dir_patterns(self):
        """
        Given a rules-dir layer with a Bash allow pattern
        When toolguard_permissions() aggregates raw permissions
        Then the rules-dir pattern (tool wrapper intact) is included
        """
        layers = (
            self._rules_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": [], "ask": []}},
                specificity=1,
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertIn("Bash(gh *)", perms["allow"])

    def test_extended_regex_pattern_passes_through_from_rules_dir_layer(self):
        """
        Given a rules-dir layer whose allow pattern carries a [regex] prefix
        When allow_deny_for('Bash') extracts patterns for that layer
        Then the extracted pattern retains the [regex] prefix unchanged
        (extended syntax is pure string pass-through at this layer)
        """
        layers = (
            self._rules_layer(
                {"permissions": {"allow": ["Bash([regex]^git .*)"], "deny": []}},
                specificity=1,
            ),
        )
        config = Configuration(layers=layers)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("[regex]^git .*", allow)


class TestRulesDirectoryValidationAndProvenance(ConfigIsolationMixin, unittest.TestCase):
    """ConfigLayer.unexpected_keys, the new validation_issues() check,
    _level_for_path()'s rules-dir case, and provenance formatting."""

    def test_config_layer_unexpected_keys_defaults_to_empty_tuple(self):
        """
        Given a ConfigLayer constructed without an unexpected_keys argument
        When its unexpected_keys attribute is read
        Then it defaults to an empty tuple (backward compatible with existing
        direct-construction call sites)
        """
        prov = Provenance(
            "user",
            "toolguard_hook_rules",
            "toml",
            Path("/u/.config/toolguard/rules/gh.toml"),
            1,
        )
        layer = ConfigLayer(prov, MappingProxyType({"permissions": {"allow": []}}))
        self.assertEqual(layer.unexpected_keys, ())

    def test_config_layer_accepts_unexpected_keys_field(self):
        """
        Given a ConfigLayer constructed with an explicit unexpected_keys tuple
        When its unexpected_keys attribute is read
        Then it returns exactly the tuple supplied
        """
        prov = Provenance(
            "user",
            "toolguard_hook_rules",
            "toml",
            Path("/u/.config/toolguard/rules/gh.toml"),
            1,
        )
        layer = ConfigLayer(
            prov,
            MappingProxyType({"permissions": {"allow": []}}),
            unexpected_keys=("governed_tools",),
        )
        self.assertEqual(layer.unexpected_keys, ("governed_tools",))

    def test_level_for_path_returns_user_for_rules_dir_path(self):
        """
        Given a file path under the (isolated, default-location) rules directory
        When _level_for_path() determines its conceptual level
        Then it returns 'user' (not 'project', the pre-TOO-30 default for any
        path outside ~/.claude)
        """
        fake_home, _project = self.isolate_config_environment()
        rules_dir = fake_home / ".config" / "toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        gh_path = rules_dir / "gh.toml"
        level = config_module._level_for_path(gh_path)
        self.assertEqual(level, "user")

    def test_level_for_path_still_returns_project_for_unrelated_path(self):
        """
        Given a file path unrelated to both ~/.claude and the rules directory
        When _level_for_path() determines its conceptual level
        Then it returns 'project' (unchanged behaviour for the non-user case)
        """
        level = config_module._level_for_path(
            Path("/some/project/.claude/toolguard_hook.toml")
        )
        self.assertEqual(level, "project")

    def test_unexpected_key_reported_as_error_and_permissions_still_resolve_end_to_end(
        self,
    ):
        """
        Given a rules-dir file with a valid [permissions] block AND an
        unexpected top-level 'governed_tools' key
        When load_configuration() loads it
        Then validation_issues() reports exactly one error Issue naming the
        specific file and the 'governed_tools' key, while the valid Bash allow
        pattern from that SAME file still resolves via allow_deny_for() (the
        error is a diagnostic only, not a load-blocker for the valid content)
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            rules_file = rules_dir / "gh.toml"
            rules_file.write_text(
                'governed_tools = ["Write"]\n[permissions]\nallow = ["Bash(gh *)"]\n'
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        error_issues = [
            issue
            for issue in config.validation_issues()
            if issue.level == "error"
            and "governed_tools" in issue.message
            and str(rules_file) in issue.message
        ]
        self.assertEqual(len(error_issues), 1)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("gh *", allow)

    def test_resolve_permission_detailed_reason_cites_rules_dir_file_path(self):
        """
        Given a single rules-dir-sourced layer (level 'user') whose allow
        pattern wins a resolution
        When resolve_permission_detailed('Bash', ...) resolves the decision
        Then the returned reason string cites the specific rules-dir file path
        via the existing provenance-suffix mechanism
        """
        rules_path = Path("/home/u/.config/toolguard/rules/gh.toml")
        prov = Provenance("user", "toolguard_hook_rules", "toml", rules_path, 1)
        layer = ConfigLayer(
            prov, MappingProxyType({"permissions": {"allow": ["Bash(gh *)"], "deny": []}})
        )
        config = Configuration(layers=(layer,))

        def _decide(allow, deny, ask):
            if "gh *" in allow:
                return ("allow", "Command matches allow pattern: gh *", "gh *")
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = config.resolve_permission_detailed("Bash", _decide)
        self.assertIn(str(rules_path), resolved.reason)
        self.assertIn("user:", resolved.reason)


class TestRulesDirectoryExplicitModeBypass(ConfigIsolationMixin, unittest.TestCase):
    """CLAUDE_SETTINGS_PATH bypasses the rules-directory scan entirely."""

    def test_claude_settings_path_bypasses_rules_dir_scan(self):
        """
        Given CLAUDE_SETTINGS_PATH is set AND rules-dir files exist on disk
        When load_configuration() runs
        Then none of the rules-dir files appear in config.layers (the explicit
        single-file branch returns before _discover_levels() is ever called,
        so rules-dir files are never scanned in this mode)
        """
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(git *)"]}}))

            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "gh.toml").write_text(
                _toml_permissions_block(allow=["Bash(gh *)"])
            )

            self.isolate_config_environment(
                xdg_config_home=xdg, extra_env={"CLAUDE_SETTINGS_PATH": str(settings)}
            )
            config = load_configuration()
        for layer in config.layers:
            self.assertNotEqual(layer.provenance.path.parent, rules_dir)
            self.assertNotEqual(layer.provenance.source_type, "toolguard_hook_rules")


if __name__ == "__main__":
    unittest.main()
