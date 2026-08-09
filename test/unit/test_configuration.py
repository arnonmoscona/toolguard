"""
Unit tests for the TOO-8 Phase 1 public config abstraction.

These tests exercise :func:`toolguard.config.load_configuration` and the
:class:`Configuration` public API, plus the internal delegating helper
``config_sync_settings_from_sources`` that ``auto_migrate`` uses.

Run with:
    uv run python -m unittest discover -s test -t .
"""

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import Optional, Sequence
from unittest.mock import patch

import toolguard.config as config_module
from test.unit._config_isolation import ConfigIsolationMixin
from toolguard import error_reporter
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
from toolguard.config_types import LevelMatch, entry_for_pattern
from toolguard.permission_resolution import resolve_permission_detailed
from toolguard.rule_entry import ADDITIONAL_CONTEXT_KEY, RuleEntry, _strip_tool_wrapper


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

    def test_multiline_structured_entry_skipped_with_actionable_diagnostic(self):
        """
        Given a toolguard_hook.toml whose allow list has a structured entry
            written across multiple physical lines -- not valid TOML 1.0 (an
            inline table must sit on one physical line) -- alongside a valid
            settings.local.json
        When load_configuration runs
        Then the malformed file is skipped (same fail-open behaviour as any
            other unparseable file -- unchanged, out of this change's scope)
            but the printed warning names the file, the offending line, and
            the actual fix ("single ... line"), not tomllib's cryptic raw
            "Invalid initial character..." message, and the valid layer's
            rules are still available
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        hook_path = claude_dir / "toolguard_hook.toml"
        hook_path.write_text(
            '[permissions]\nallow = [\n  {\n    match = "Bash(git status)",\n  },\n]\n'
        )
        (claude_dir / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git *)"]}})
        )

        with patch("sys.stderr", new_callable=io.StringIO) as captured_stderr:
            config = load_configuration()

        allow, _ = config.allow_deny_for("Bash")
        self.assertIn("git *", allow)
        self.assertNotIn("git status", allow)  # the skipped file's own rule

        stderr_output = captured_stderr.getvalue()
        self.assertIn(str(hook_path), stderr_output)
        self.assertIn("single", stderr_output)
        self.assertIn("line", stderr_output)
        self.assertNotIn("Invalid initial character", stderr_output)

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

    def test_structured_entry_appears_in_deny_not_silently_dropped(self):
        """
        Given a toolguard hook layer with a plain string and a structured-entry table in deny
        When permission_layers('Bash') is computed
        Then both the plain and structured patterns appear in .deny -- this pins the fix for
        the silent-drop bug, which was most dangerous on the deny side
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [],
                            "deny": [
                                "Bash(rm -rf /)",
                                {"match": "Bash(git push --force*)"},
                            ],
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
            per_layer = config.permission_layers("Bash")
        self.assertEqual(per_layer[0].deny, ("rm -rf /", "git push --force*"))

    def test_mixed_plain_and_structured_allow_entries_populated(self):
        """
        Given an allow list mixing a plain string and a structured entry with metadata
        When permission_layers('Bash') is computed
        Then allow_entries holds both RuleEntry objects in the same order as allow, and
        each allow[i] is the wrapper-stripped form of allow_entries[i].pattern (the
        index invariant later increments rely on)
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [
                                "Bash(git *)",
                                {
                                    "match": "Bash(ls *)",
                                    "additionalContext": "read-only listing",
                                },
                            ],
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
            per_layer = config.permission_layers("Bash")
        layer = per_layer[0]
        self.assertEqual(layer.allow, ("git *", "ls *"))
        self.assertEqual(len(layer.allow), len(layer.allow_entries))
        for pattern, entry in zip(layer.allow, layer.allow_entries):
            self.assertEqual(_strip_tool_wrapper(entry.pattern), pattern)
        self.assertEqual(
            dict(layer.allow_entries[1].metadata),
            {"additionalContext": "read-only listing"},
        )

    def test_structured_entry_in_native_layer_ignored(self):
        """
        Given a NATIVE (claude) layer whose allow list contains a structured-entry table
        When permission_layers('Bash') is computed
        Then the structured entry is rejected (structured entries are a toolguard
        extension, never interpreted from native settings) and only the plain string
        survives, in both .allow and .allow_entries
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [
                                "Bash(git *)",
                                {"match": "Bash(ls *)"},
                            ],
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
            per_layer = config.permission_layers("Bash")
        layer = per_layer[0]
        self.assertEqual(layer.allow, ("git *",))
        self.assertEqual(len(layer.allow_entries), 1)

    def test_takeover_filters_native_allow_entries_too(self):
        """
        Given a native layer allowing a blanket pattern that takeover ignores
        When permission_layers('Read') is computed under takeover mode
        Then the blanket pattern is removed from BOTH .allow and .allow_entries,
        preserving the index invariant between them
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json")),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": ["Read(*)", "Read(/tmp/**)"],
                            "deny": [],
                        }
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        takeover = TakeoverConfig(True, ("Read(*)",), (), "deny")
        with patch.object(Configuration, "takeover_mode", return_value=takeover):
            per_layer = config.permission_layers("Read")
        layer = per_layer[0]
        self.assertEqual(layer.allow, ("/tmp/**",))
        self.assertEqual(len(layer.allow_entries), 1)
        self.assertEqual(layer.allow_entries[0].pattern, "Read(/tmp/**)")

    def test_entries_scoped_to_requested_tool_only(self):
        """
        Given an allow list with structured entries for two different tools
        When permission_layers('Read') is computed
        Then only the Read-scoped structured entry survives; Bash's is excluded from
        both .allow and .allow_entries
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [
                                {"match": "Read(/tmp/**)"},
                                {"match": "Bash(git *)"},
                            ],
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
            per_layer = config.permission_layers("Read")
        layer = per_layer[0]
        self.assertEqual(layer.allow, ("/tmp/**",))
        self.assertEqual(len(layer.allow_entries), 1)

    def test_malformed_entries_do_not_raise_and_are_excluded(self):
        """
        Given an allow list with a malformed structured entry (missing 'match') and a bare int
        When permission_layers('Bash') is computed
        Then no exception is raised and neither malformed element appears in .allow or
        .allow_entries
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [
                                "Bash(git *)",
                                {"no_match_key": 1},
                                42,
                            ],
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
            per_layer = config.permission_layers("Bash")
        layer = per_layer[0]
        self.assertEqual(layer.allow, ("git *",))
        self.assertEqual(len(layer.allow_entries), 1)


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
        Then the hook patterns are returned as RuleEntry with tool wrappers intact
             and the native pattern is skipped

        TOO-19 Phase 0a increment 8: toolguard_permissions()'s return type widened
        from plain pattern strings to RuleEntry (see the method's docstring for
        why), so this test compares `.pattern` rather than the tuple directly.
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
        self.assertEqual([e.pattern for e in perms["allow"]], ["Bash(git *)"])
        self.assertEqual([e.pattern for e in perms["deny"]], ["Bash(rm *)"])
        self.assertEqual(perms["ask"], ())
        self.assertNotIn("Bash(should-skip)", [e.pattern for e in perms["allow"]])

    def test_structured_entry_is_not_silently_dropped(self):
        """
        Given a hook layer whose allow list holds a structured (dict) entry
        When toolguard_permissions() aggregates it
        Then the entry is preserved as a RuleEntry with its metadata intact
             (regression guard for the W1 defect: the old isinstance(perm, str)
             filter silently dropped every structured entry here)
        """
        layers = (
            ConfigLayer(
                Provenance(
                    "project", "toolguard_hook", "toml", Path("/p/toolguard_hook.toml")
                ),
                MappingProxyType(
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git *)",
                                    "additionalContext": "review carefully",
                                }
                            ],
                            "deny": [],
                            "ask": [],
                        }
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertEqual(len(perms["allow"]), 1)
        entry = perms["allow"][0]
        self.assertEqual(entry.pattern, "Bash(git *)")
        self.assertEqual(entry.metadata["additionalContext"], "review carefully")


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

    def test_structured_entry_unsupported_tool_reaches_validation_issues(self):
        """
        Given a hook layer allowing a structured {match = ...} entry for an
        unsupported tool
        When validation_issues() runs
        Then the structured entry's tool is flagged, end-to-end, exactly as a
        plain-string entry would be (TOO-19 Phase 0a, increment 4 bug fix:
        structured entries used to be silently skipped by
        validate_permissions, not just at the lower layers)
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
                        "permissions": {
                            "allow": [
                                {"match": "WebSearch()", "additionalContext": "why"}
                            ]
                        },
                    }
                ),
            ),
        )
        config = Configuration(layers=layers)
        issues = config.validation_issues()
        self.assertTrue(any("WebSearch" in i.message for i in issues))
        for i in issues:
            self.assertIsInstance(i, Issue)

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
        Then it returns the default ('Bash', 'Read', 'Write', 'Edit')
        """
        config = Configuration(layers=())
        self.assertEqual(config.governed_tools(), ("Bash", "Read", "Write", "Edit"))

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
        Then the malformed entry is skipped and the default ('Bash', 'Read', 'Write', 'Edit')
        is returned
        """
        layers = (self._hook_layer("project", {"governed_tools": "not-a-list"}, 0),)
        config = Configuration(layers=layers)
        self.assertEqual(config.governed_tools(), ("Bash", "Read", "Write", "Edit"))

    def test_governed_tools_ignores_native_layers(self):
        """
        Given a native ('claude') layer declaring governed_tools and no hook layer doing so
        When Configuration.governed_tools() resolves
        Then the native list is ignored and the default ('Bash', 'Read', 'Write', 'Edit')
        is returned
        """
        layers = (
            ConfigLayer(
                Provenance("project", "claude", "json", Path("/p/settings.json"), 0),
                MappingProxyType({"governed_tools": ["Read", "Write"]}),
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.governed_tools(), ("Bash", "Read", "Write", "Edit"))

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
            self._hook_layer("project", {"permissions": {"allow": ["Bash(git *)"]}}),
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
            self._hook_layer("project", {"permissions": {"deny": ["Bash(rm *)"]}}),
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
            self._hook_layer("project", {"permissions": {"ask": ["Bash(curl *)"]}}),
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
            self._hook_layer("project", {"hard_deny": {"deny": ["Bash(rm -rf *)"]}}),
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
            self._hook_layer("project", {"permissions": {"allow": ["Read(/tmp/**)"]}}),
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
    'deny', 'allow_with_warning', and 'allow' (TOO-19). Two spellings are
    accepted but normalized before reaching the recognized set: the
    deprecated legacy value 'warn_deny' normalizes to 'allow_with_warning',
    and the deliberate (non-deprecated) long-form synonym
    'allow_with_no_warnings' normalizes to 'allow'.
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

    def test_value_allow_is_returned_as_is(self):
        """
        Given a hook layer setting the top-level 'no_match_fallback' key to
            'allow' (TOO-19, the canonical no-warning spelling)
        When Configuration.resolved_no_match_fallback() resolves
        Then it returns 'allow' unchanged
        """
        layers = (self._hook_layer("project", {"no_match_fallback": "allow"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow")

    def test_allow_with_no_warnings_normalizes_to_allow_via_top_level_key(self):
        """
        Given a hook layer setting the top-level 'no_match_fallback' key to
            'allow_with_no_warnings' (TOO-19's deliberate long-form synonym)
        When Configuration.resolved_no_match_fallback() resolves
        Then it is normalized to the canonical 'allow' -- identical to setting
            'allow' directly
        """
        layers = (
            self._hook_layer(
                "project", {"no_match_fallback": "allow_with_no_warnings"}
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow")

    def test_allow_with_no_warnings_via_legacy_takeover_alias_normalizes(self):
        """
        Given only the legacy [takeover_mode].no_match_fallback is set to
            'allow_with_no_warnings' (no top-level key anywhere)
        When Configuration.resolved_no_match_fallback() resolves
        Then the legacy-alias value is still normalized to 'allow' -- the
            alias normalization applies regardless of which mechanism
            supplied the raw value (TOO-19)
        """
        layers = (
            self._hook_layer(
                "project",
                {"takeover_mode": {"no_match_fallback": "allow_with_no_warnings"}},
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "allow")


class TestResolvedUndecidableFallback(unittest.TestCase):
    """
    Configuration.resolved_undecidable_fallback() (TOO-19): the top-level
    ``undecidable_fallback`` key ONLY, most-specific-wins across non-native
    layers. Unlike ``no_match_fallback`` there is deliberately NO legacy
    ``[takeover_mode]`` alias and NO deprecated ``'warn_deny'`` spelling --
    this is a brand-new setting with no history to be backwards-compatible
    with. Defaults to 'ask'. The recognized values are 'ask', 'deny',
    'allow_with_warning', and 'allow'. The deliberate (non-deprecated)
    long-form synonym 'allow_with_no_warnings' IS honoured here (normalizes
    to 'allow') -- that alias was introduced for both settings at once
    (TOO-19), unlike 'warn_deny', which remains no_match_fallback-only.
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
        Given no layer sets the top-level 'undecidable_fallback' key
        When Configuration.resolved_undecidable_fallback() resolves
        Then it returns the default 'ask'
        """
        config = Configuration(layers=(self._hook_layer("project", {}),))
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_value_ask_explicit_is_returned_as_is(self):
        """
        Given a hook layer explicitly setting the top-level
            'undecidable_fallback' key to 'ask'
        When Configuration.resolved_undecidable_fallback() resolves
        Then it returns 'ask'
        """
        layers = (self._hook_layer("project", {"undecidable_fallback": "ask"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_value_deny_is_returned_as_is(self):
        """
        Given a hook layer setting the top-level 'undecidable_fallback' key
            to 'deny'
        When Configuration.resolved_undecidable_fallback() resolves
        Then it returns 'deny'
        """
        layers = (self._hook_layer("project", {"undecidable_fallback": "deny"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "deny")

    def test_value_allow_with_warning_is_returned_as_is(self):
        """
        Given a hook layer setting the top-level 'undecidable_fallback' key
            to 'allow_with_warning'
        When Configuration.resolved_undecidable_fallback() resolves
        Then it returns 'allow_with_warning'
        """
        layers = (
            self._hook_layer("project", {"undecidable_fallback": "allow_with_warning"}),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "allow_with_warning")

    def test_more_specific_layer_wins(self):
        """
        Given two layers both set the top-level key, project='deny' and
            user='allow_with_warning' (project more specific)
        When Configuration.resolved_undecidable_fallback() resolves
        Then the more-specific (project) value 'deny' wins
        """
        layers = (
            self._hook_layer("project", {"undecidable_fallback": "deny"}, 0),
            self._hook_layer("user", {"undecidable_fallback": "allow_with_warning"}, 1),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "deny")

    def test_native_layer_top_level_key_ignored(self):
        """
        Given ONLY a native ('claude') layer sets a top-level
            'undecidable_fallback' key (toolguard extensions are never read
            from native settings)
        When Configuration.resolved_undecidable_fallback() resolves
        Then the native value is ignored and the default 'ask' is returned
        """
        native_layer = ConfigLayer(
            Provenance("project", "claude", "json", Path("/p/settings.json"), 0),
            MappingProxyType({"undecidable_fallback": "deny"}),
        )
        config = Configuration(layers=(native_layer,))
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_invalid_value_falls_back_to_ask(self):
        """
        Given a layer sets the top-level 'undecidable_fallback' to an
            unrecognized value (a typo / bad config, e.g. 'nonsense')
        When Configuration.resolved_undecidable_fallback() resolves
        Then the value is not propagated; it normalizes to the default 'ask'
        """
        layers = (self._hook_layer("project", {"undecidable_fallback": "nonsense"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_legacy_takeover_mode_alias_is_not_honored(self):
        """
        Given ONLY the [takeover_mode].undecidable_fallback 'alias' shape is
            set (no top-level key anywhere) -- mirroring no_match_fallback's
            legacy alias syntax, which undecidable_fallback deliberately does
            NOT have
        When Configuration.resolved_undecidable_fallback() resolves
        Then the [takeover_mode] value is NOT honored and the default 'ask'
            is returned -- undecidable_fallback has no legacy alias, by
            design (TOO-19), and must not gain one
        """
        layers = (
            self._hook_layer(
                "project", {"takeover_mode": {"undecidable_fallback": "deny"}}
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_value_allow_is_returned_as_is(self):
        """
        Given a hook layer setting the top-level 'undecidable_fallback' key
            to 'allow' (TOO-19, the canonical no-warning spelling)
        When Configuration.resolved_undecidable_fallback() resolves
        Then it returns 'allow' unchanged
        """
        layers = (self._hook_layer("project", {"undecidable_fallback": "allow"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "allow")

    def test_allow_with_no_warnings_normalizes_to_allow(self):
        """
        Given a hook layer setting the top-level 'undecidable_fallback' key
            to 'allow_with_no_warnings' (TOO-19's deliberate long-form synonym)
        When Configuration.resolved_undecidable_fallback() resolves
        Then it is normalized to the canonical 'allow' -- identical to
            setting 'allow' directly, and identical in meaning between the
            two settings
        """
        layers = (
            self._hook_layer(
                "project", {"undecidable_fallback": "allow_with_no_warnings"}
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "allow")

    def test_warn_deny_is_not_honored_falls_back_to_ask(self):
        """
        Given a hook layer setting the top-level 'undecidable_fallback' key
            to 'warn_deny' -- no_match_fallback's deprecated legacy spelling
        When Configuration.resolved_undecidable_fallback() resolves
        Then 'warn_deny' is NOT normalized (unlike for no_match_fallback) --
            it is simply an unrecognized value here and falls back to the
            default 'ask'. This is the deliberate no_match_fallback/
            undecidable_fallback asymmetry the TOO-19 allow/allow_with_no_warnings
            work must preserve.
        """
        layers = (self._hook_layer("project", {"undecidable_fallback": "warn_deny"}),)
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_independent_from_no_match_fallback(self):
        """
        Given a single layer setting no_match_fallback='deny' and
            undecidable_fallback='allow_with_warning' together
        When both resolved_no_match_fallback() and
            resolved_undecidable_fallback() are called
        Then each resolves independently to its own configured value --
            neither setting leaks into the other's resolution
        """
        layers = (
            self._hook_layer(
                "project",
                {
                    "no_match_fallback": "deny",
                    "undecidable_fallback": "allow_with_warning",
                },
            ),
        )
        config = Configuration(layers=layers)
        self.assertEqual(config.resolved_no_match_fallback(), "deny")
        self.assertEqual(config.resolved_undecidable_fallback(), "allow_with_warning")


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


class TestUnrecognizedFallbackSettings(unittest.TestCase):
    """
    Configuration.unrecognized_fallback_settings() (TOO-19 m5).

    Arnon set ``no_match_fallback = "allow_with_no_warning"`` (singular). It
    was unrecognized, so it resolved to 'ask' -- maximum friction -- with no
    diagnostic anywhere, and the conclusion drawn was "the feature is broken"
    rather than "there is a typo". Resolution semantics are unchanged ('ask'
    IS the safe direction); what changed is that the typo is now named, with
    the offending value, the setting, the file, and the accepted spellings.
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

    def test_the_real_typo_is_detected_and_still_resolves_to_ask(self):
        """
        Given no_match_fallback = 'allow_with_no_warning' (singular -- the
            real typo that cost a round trip)
        When unrecognized_fallback_settings() runs
        Then exactly one record names the setting, the offending value, the
            file, and the accepted spellings -- and resolution still returns
            'ask', because the safe direction is deliberately unchanged
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    "user", {"no_match_fallback": "allow_with_no_warning"}
                ),
            )
        )
        found = config.unrecognized_fallback_settings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].key, "no_match_fallback")
        self.assertEqual(found[0].value, "allow_with_no_warning")
        self.assertEqual(found[0].provenance.level, "user")
        self.assertIn("allow_with_no_warnings", found[0].accepted)
        self.assertEqual(config.resolved_no_match_fallback(), "ask")

    def test_applies_to_undecidable_fallback_too(self):
        """
        Given undecidable_fallback set to a value that is not recognized
        When unrecognized_fallback_settings() runs
        Then it is reported the same way no_match_fallback would be
        """
        config = Configuration(
            layers=(self._hook_layer("user", {"undecidable_fallback": "allowed"}),)
        )
        found = config.unrecognized_fallback_settings()
        self.assertEqual([f.key for f in found], ["undecidable_fallback"])
        self.assertEqual(config.resolved_undecidable_fallback(), "ask")

    def test_valid_and_alias_values_never_fire(self):
        """
        Given every accepted spelling of both settings, including the aliases
            normalized away before validation ('warn_deny',
            'allow_with_no_warnings')
        When unrecognized_fallback_settings() runs
        Then nothing is reported for any of them
        """
        for value in (
            "ask",
            "deny",
            "allow",
            "allow_with_warning",
            "allow_with_no_warnings",
        ):
            with self.subTest(value=value):
                config = Configuration(
                    layers=(
                        self._hook_layer(
                            "user",
                            {
                                "no_match_fallback": value,
                                "undecidable_fallback": value,
                            },
                        ),
                    )
                )
                self.assertEqual(config.unrecognized_fallback_settings(), ())

        config = Configuration(
            layers=(self._hook_layer("user", {"no_match_fallback": "warn_deny"}),)
        )
        self.assertEqual(config.unrecognized_fallback_settings(), ())

    def test_unset_never_fires(self):
        """
        Given a layer that sets neither fallback setting
        When unrecognized_fallback_settings() runs
        Then nothing is reported
        """
        config = Configuration(layers=(self._hook_layer("user", {}),))
        self.assertEqual(config.unrecognized_fallback_settings(), ())

    def test_non_string_value_is_reported(self):
        """
        Given no_match_fallback set to a boolean rather than a string
        When unrecognized_fallback_settings() runs
        Then it is reported too -- a non-string is treated as unset by
            resolution, which is the same silent outcome a typo produced
        """
        config = Configuration(
            layers=(self._hook_layer("user", {"no_match_fallback": True}),)
        )
        found = config.unrecognized_fallback_settings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].value, "True")

    def test_every_offending_layer_is_reported_not_just_the_winner(self):
        """
        Given a more-specific layer with a VALID value masking a
            less-specific layer with a typo
        When unrecognized_fallback_settings() runs
        Then the masked typo is still reported -- it is inert today but
            becomes live the moment the masking layer is removed
        """
        config = Configuration(
            layers=(
                self._hook_layer("project", {"no_match_fallback": "deny"}, 1),
                self._hook_layer("user", {"no_match_fallback": "denyy"}, 0),
            )
        )
        found = config.unrecognized_fallback_settings()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].provenance.level, "user")
        self.assertEqual(config.resolved_no_match_fallback(), "deny")

    def test_native_layers_are_ignored(self):
        """
        Given a NATIVE settings.json layer carrying a no_match_fallback key
        When unrecognized_fallback_settings() runs
        Then nothing is reported -- these are toolguard extensions and are
            never read from native layers, so flagging one would be noise
        """
        native = ConfigLayer(
            Provenance(
                "project",
                "claude",
                "json",
                Path("/project/.claude/settings.json"),
                0,
            ),
            MappingProxyType({"no_match_fallback": "nonsense"}),
        )
        config = Configuration(layers=(native,))
        self.assertEqual(config.unrecognized_fallback_settings(), ())

    def test_reaches_validation_issues_as_a_warning(self):
        """
        Given a misspelled no_match_fallback value
        When validation_issues() runs
        Then one 'warning' Issue carries the value, the setting, the file, and
            the accepted spellings -- so it reaches the resolution-log warning
            stream the hook routes issues to
        """
        config = Configuration(
            layers=(
                self._hook_layer(
                    "user", {"no_match_fallback": "allow_with_no_warning"}
                ),
            )
        )
        matching = [
            issue
            for issue in config.validation_issues()
            if "no_match_fallback" in issue.message
        ]
        self.assertEqual(len(matching), 1)
        issue = matching[0]
        self.assertEqual(issue.level, "warning")
        self.assertIn("allow_with_no_warning", issue.message)
        self.assertIn("toolguard_hook.toml", issue.message)
        self.assertIn("allow_with_no_warnings", issue.message)
        self.assertIn("allow_with_no_warnings", issue.corrective_steps)


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
# TOO-19 follow-up (also RED-phase for this increment): a second, pre-existing
# candidate rules directory, ~/.toolguard/rules, was never scanned -- a real
# ruleset placed there was silently unenforced. Added on top of the above:
#
#   - toolguard.config._rules_dirs()                  (replaces _rules_dir();
#     returns BOTH candidate directories, XDG first)
#   - toolguard.config._merged_rules_by_stem()         (new, private;
#     first-directory-wins per stem across candidate dirs)
#   - toolguard.config._discover_rules_files_multi()   (new, private; multi-dir
#     discovery wrapper used by _discover_levels())
#   - toolguard.config._shadowed_rules_stems()         (new, private; detects a
#     stem present in more than one candidate directory)
#   - toolguard.config.ConfigLayer.shadowed_path       (new field, default None)
#   - toolguard.config.Configuration.validation_issues() (new shadowing-warning
#     check, alongside the existing "both formats" check)
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
    """_rules_dirs(), _discover_rules_files(), and end-to-end discovery via
    load_configuration() into the user level (TOO-30, extended by TOO-19 for
    the second ~/.toolguard/rules candidate directory)."""

    # -- _rules_dirs() (white-box, no I/O) ------------------------------------
    #
    # TOO-19: _rules_dir() (single directory) was replaced by _rules_dirs(),
    # returning BOTH candidate directories in precedence order (XDG first,
    # then the legacy ~/.toolguard/rules). These do no filesystem I/O, so they
    # need no ConfigIsolationMixin setup -- but the expected value MUST be
    # computed with Path.home() called INSIDE the same patched environment as
    # the code under test. Path.home() is not pure: it reads $HOME and falls
    # back to the pwd database when unset, so a Path.home() evaluated outside
    # a clear=True patch can differ from one evaluated inside it. That made
    # these three tests pass only because $HOME happened to match the pwd entry
    # on the developer's machine; they failed under any other $HOME (found
    # 2026-07-28 while replacing test/unit/CLAUDE.md's live-config sanity check
    # with an empty-$HOME run).

    def test_rules_dirs_uses_xdg_config_home_when_set(self):
        """
        Given XDG_CONFIG_HOME set to a custom path
        When _rules_dirs() resolves the candidate rules directories
        Then it returns (<XDG_CONFIG_HOME>/toolguard/rules, ~/.toolguard/rules),
        XDG first
        """
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/xdg"}, clear=True):
            result = config_module._rules_dirs()
            expected_home = Path.home()
        self.assertEqual(
            result,
            (
                Path("/custom/xdg") / "toolguard" / "rules",
                expected_home / ".toolguard" / "rules",
            ),
        )

    def test_rules_dirs_defaults_to_home_config_when_xdg_unset(self):
        """
        Given XDG_CONFIG_HOME is not set in the environment
        When _rules_dirs() resolves the candidate rules directories
        Then the first entry defaults to ~/.config/toolguard/rules and the
        second entry is ~/.toolguard/rules
        """
        with patch.dict(os.environ, {}, clear=True):
            result = config_module._rules_dirs()
            expected_home = Path.home()
        self.assertEqual(
            result,
            (
                expected_home / ".config" / "toolguard" / "rules",
                expected_home / ".toolguard" / "rules",
            ),
        )

    def test_rules_dirs_falls_back_to_default_when_xdg_config_home_is_empty(self):
        """
        Given XDG_CONFIG_HOME is set but to an empty string
        When _rules_dirs() resolves the candidate rules directories
        Then the first entry falls back to the ~/.config/toolguard/rules
        default (empty is treated as unset, not as a literal empty-string
        base); the second entry is still ~/.toolguard/rules
        """
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}, clear=True):
            result = config_module._rules_dirs()
            expected_home = Path.home()
        self.assertEqual(
            result,
            (
                expected_home / ".config" / "toolguard" / "rules",
                expected_home / ".toolguard" / "rules",
            ),
        )

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

    # -- _shadowed_rules_stems() (white-box, direct temp dirs, no Path.home()) -

    def test_shadowed_rules_stems_reports_distinct_real_files(self):
        """
        Given the same stem 'gh.toml' present in both candidate directories as
        two genuinely distinct real files (not a symlink of one to the other)
        When _shadowed_rules_stems() compares them
        Then the stem is reported, mapped to the second (legacy) directory's path
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg_dir = Path(tmp) / "xdg"
            xdg_dir.mkdir()
            legacy_dir = Path(tmp) / "legacy"
            legacy_dir.mkdir()
            (xdg_dir / "gh.toml").write_text("[permissions]\nallow = []\n")
            legacy_file = legacy_dir / "gh.toml"
            legacy_file.write_text("[permissions]\nallow = []\n")
            result = config_module._shadowed_rules_stems((xdg_dir, legacy_dir))
        self.assertEqual(result, {"gh": legacy_file})

    def test_shadowed_rules_stems_excludes_stem_resolving_to_same_real_file(self):
        """
        Given the same stem 'gh.toml' present in both candidate directories,
        where the XDG directory's entry is a SYMLINK pointing at the legacy
        directory's real file (one rules directory symlinked into the other --
        the actual TOO-19 stopgap workaround, and a natural migration move any
        user might make)
        When _shadowed_rules_stems() compares them via Path.resolve()
        Then the stem is NOT reported as shadowed, since both entries are the
        same real file and nothing is actually being ignored
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg_dir = Path(tmp) / "xdg"
            xdg_dir.mkdir()
            legacy_dir = Path(tmp) / "legacy"
            legacy_dir.mkdir()
            real_file = legacy_dir / "gh.toml"
            real_file.write_text("[permissions]\nallow = []\n")
            (xdg_dir / "gh.toml").symlink_to(real_file)
            result = config_module._shadowed_rules_stems((xdg_dir, legacy_dir))
        self.assertEqual(result, {})

    def test_shadowed_rules_stems_stem_only_in_legacy_dir_not_reported(self):
        """
        Given a stem present ONLY in the legacy directory (not in the XDG
        directory at all)
        When _shadowed_rules_stems() compares the two directories
        Then the stem is not reported as shadowed (it is simply promoted
        normally -- no collision, nothing ignored)
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg_dir = Path(tmp) / "xdg"
            xdg_dir.mkdir()
            legacy_dir = Path(tmp) / "legacy"
            legacy_dir.mkdir()
            (legacy_dir / "gh.toml").write_text("[permissions]\nallow = []\n")
            result = config_module._shadowed_rules_stems((xdg_dir, legacy_dir))
        self.assertEqual(result, {})

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
            layer
            for layer in config.layers
            if layer.provenance.path.parent == rules_dir
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
            (rules_dir / "gh.toml").write_text(
                _toml_permissions_block(allow=["Bash(gh *)"])
            )
            (rules_dir / "gh.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(gh-json *)"]}})
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.path.parent == rules_dir
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.file_format, "toml")
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertIn("Both gh.toml and gh.json", messages)

    # -- TOO-19: second candidate rules directory (~/.toolguard/rules) ------

    def test_legacy_toolguard_dir_file_discovered_end_to_end(self):
        """
        Given a rules file that exists ONLY under the legacy ~/.toolguard/rules
        directory (not under the XDG directory) -- the originally reported
        TOO-19 bug, where such a file was silently never enforced
        When load_configuration() runs
        Then it becomes a 'toolguard_hook_rules' layer at the 'user' level and
        its permissions resolve normally
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            legacy_rules_dir = fake_home / ".toolguard" / "rules"
            legacy_rules_dir.mkdir(parents=True)
            (legacy_rules_dir / "gh.toml").write_text(
                _toml_permissions_block(allow=["Bash(gh *)"])
            )
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.level, "user")
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("gh *", allow)

    def test_different_stems_in_both_dirs_both_load(self):
        """
        Given distinct stems 'alpha' (XDG dir) and 'beta' (legacy
        ~/.toolguard/rules dir)
        When load_configuration() runs
        Then both become 'toolguard_hook_rules' layers and both patterns resolve
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            (xdg_rules_dir / "alpha.toml").write_text(
                _toml_permissions_block(allow=["Bash(alpha *)"])
            )
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            legacy_rules_dir = fake_home / ".toolguard" / "rules"
            legacy_rules_dir.mkdir(parents=True)
            (legacy_rules_dir / "beta.toml").write_text(
                _toml_permissions_block(allow=["Bash(beta *)"])
            )
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(
            sorted(layer.provenance.path.name for layer in rules_layers),
            ["alpha.toml", "beta.toml"],
        )
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("alpha *", allow)
        self.assertIn("beta *", allow)

    def test_same_stem_in_both_dirs_xdg_wins_and_shadow_warning_emitted(self):
        """
        Given a 'gh.toml' file present in BOTH the XDG rules directory and the
        legacy ~/.toolguard/rules directory, as two GENUINELY DISTINCT real
        files (not a symlink of one to the other) with different allow
        patterns
        When load_configuration() runs
        Then only the XDG file becomes a layer (its pattern resolves; the
        legacy file's pattern does not) AND validation_issues() reports a
        warning naming both the winning XDG path and the shadowed legacy path
        (regression guard: the resolve()-based same-real-file exclusion added
        to fix the symlink false-positive must not over-suppress a genuine
        shadowing case)
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            xdg_gh = xdg_rules_dir / "gh.toml"
            xdg_gh.write_text(_toml_permissions_block(allow=["Bash(gh-xdg *)"]))
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            legacy_rules_dir = fake_home / ".toolguard" / "rules"
            legacy_rules_dir.mkdir(parents=True)
            legacy_gh = legacy_rules_dir / "gh.toml"
            legacy_gh.write_text(_toml_permissions_block(allow=["Bash(gh-legacy *)"]))
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.path, xdg_gh)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("gh-xdg *", allow)
        self.assertNotIn("gh-legacy *", allow)
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertIn(str(xdg_gh), messages)
        self.assertIn(str(legacy_gh), messages)

    def test_symlinked_same_file_across_dirs_is_not_reported_as_shadowed(self):
        """
        Given a 'gh.toml' rules file that physically exists ONLY under the
        legacy ~/.toolguard/rules directory, with the XDG rules directory's
        entry for the same stem being a SYMLINK to that same real file (the
        actual stopgap workaround that motivated TOO-19: one rules directory
        symlinked into the other is a natural migration/compatibility move,
        not an accident)
        When load_configuration() runs
        Then exactly one 'toolguard_hook_rules' layer is produced for that
        stem -- the file is discovered and enforced exactly once, not twice
        -- AND validation_issues() reports NO shadowing warning, since both
        directory entries resolve to the same real file and nothing is
        actually being ignored
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            legacy_rules_dir = fake_home / ".toolguard" / "rules"
            legacy_rules_dir.mkdir(parents=True)
            real_file = legacy_rules_dir / "gh.toml"
            real_file.write_text(_toml_permissions_block(allow=["Bash(gh *)"]))
            symlinked_path = xdg_rules_dir / "gh.toml"
            symlinked_path.symlink_to(real_file)
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            allow, _deny = config.allow_deny_for("Bash")
        self.assertEqual(allow.count("gh *"), 1)
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertNotIn("shadows", messages)

    def test_cross_dir_format_mismatch_is_shadowing_not_duplicate_format(self):
        """
        Given 'gh.toml' in the XDG rules directory and 'gh.json' (a different
        format for the same stem) in the legacy ~/.toolguard/rules directory
        When load_configuration() runs
        Then the winning XDG layer's duplicate_format is False (no TOML+JSON
        pair exists WITHIN the winning directory) and validation_issues()
        reports the cross-directory shadowing warning naming both files
        instead of the "both formats" warning
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            xdg_gh = xdg_rules_dir / "gh.toml"
            xdg_gh.write_text(_toml_permissions_block(allow=["Bash(gh-xdg *)"]))
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            legacy_rules_dir = fake_home / ".toolguard" / "rules"
            legacy_rules_dir.mkdir(parents=True)
            legacy_gh = legacy_rules_dir / "gh.json"
            legacy_gh.write_text(
                json.dumps({"permissions": {"allow": ["Bash(gh-legacy *)"]}})
            )
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertFalse(rules_layers[0].duplicate_format)
        messages = [issue.message for issue in config.validation_issues()]
        self.assertFalse(any("Both gh.toml and gh.json" in m for m in messages))
        self.assertTrue(any(str(xdg_gh) in m and str(legacy_gh) in m for m in messages))

    def test_missing_legacy_toolguard_dir_is_a_no_op(self):
        """
        Given the XDG rules directory has a file but ~/.toolguard/rules does
        not exist on disk at all
        When load_configuration() runs
        Then discovery proceeds normally with only the XDG file's layer, and
        no shadowing warning is produced
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            (xdg_rules_dir / "alpha.toml").write_text(
                _toml_permissions_block(allow=["Bash(alpha *)"])
            )
            self.isolate_config_environment(xdg_config_home=xdg)
            # NOTE: ~/.toolguard/rules is deliberately left absent (not created).
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.path.name, "alpha.toml")
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertNotIn("shadows", messages)

    def test_empty_legacy_toolguard_dir_is_a_no_op(self):
        """
        Given ~/.toolguard/rules exists but is empty, alongside a populated
        XDG rules directory
        When load_configuration() runs
        Then only the XDG file's layer is produced; the empty legacy
        directory contributes nothing and produces no shadowing warning
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            xdg_rules_dir = xdg / "toolguard" / "rules"
            xdg_rules_dir.mkdir(parents=True)
            (xdg_rules_dir / "alpha.toml").write_text(
                _toml_permissions_block(allow=["Bash(alpha *)"])
            )
            fake_home, _project = self.isolate_config_environment(xdg_config_home=xdg)
            (fake_home / ".toolguard" / "rules").mkdir(parents=True)
            config = load_configuration()
        rules_layers = [
            layer
            for layer in config.layers
            if layer.provenance.source_type == "toolguard_hook_rules"
        ]
        self.assertEqual(len(rules_layers), 1)
        self.assertEqual(rules_layers[0].provenance.path.name, "alpha.toml")
        messages = " ".join(issue.message for issue in config.validation_issues())
        self.assertNotIn("shadows", messages)


class TestRulesDirectoryMergeSemantics(ConfigIsolationMixin, unittest.TestCase):
    """
    Existing generic Configuration surfaces (permission_levels_with_provenance,
    the engine's resolve_permission_detailed, hard_deny, toolguard_permissions,
    allow_deny_for) correctly treat rules-dir-sourced layers as ordinary
    user-level layers once such layers exist -- no new code is needed for
    that (TOO-30 item 9).

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
                    "project",
                    "toolguard_hook",
                    "toml",
                    Path("/p/.claude/toolguard_hook.toml"),
                    0,
                ),
                MappingProxyType(
                    {"permissions": {"allow": [], "deny": ["Bash(gh *)"]}}
                ),
            ),
            self._rules_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": []}}, specificity=1
            ),
        )
        config = Configuration(layers=layers)

        def _decide(
            allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
        ) -> Optional[LevelMatch]:
            if "gh *" in deny:
                return LevelMatch(
                    decision="deny",
                    reason="Command matches deny pattern: gh *",
                    matched_pattern="gh *",
                )
            if "gh *" in allow:
                return LevelMatch(
                    decision="allow",
                    reason="Command matches allow pattern: gh *",
                    matched_pattern="gh *",
                )
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(config, "Bash", _decide)
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

        def _decide(
            allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
        ) -> Optional[LevelMatch]:
            if "gh *" in deny:
                return LevelMatch(
                    decision="deny",
                    reason="Command matches deny pattern: gh *",
                    matched_pattern="gh *",
                )
            if "gh *" in allow:
                return LevelMatch(
                    decision="allow",
                    reason="Command matches allow pattern: gh *",
                    matched_pattern="gh *",
                )
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(config, "Bash", _decide)
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

        The sneaky ``governed_tools`` value is deliberately a tool NOT in the
        default governed set (``Bash``/``Read``/``Write``/``Edit``, see
        ``toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS``) -- otherwise a leaked
        value would be indistinguishable from the default and this assertion
        would prove nothing.
        """
        with tempfile.TemporaryDirectory() as tmp:
            xdg = Path(tmp) / "xdg"
            rules_dir = xdg / "toolguard" / "rules"
            rules_dir.mkdir(parents=True)
            (rules_dir / "sneaky.toml").write_text(
                'governed_tools = ["mcp__jetbrains__execute_terminal_command"]\n'
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
        self.assertEqual(config.governed_tools(), ("Bash", "Read", "Write", "Edit"))
        self.assertEqual(config.resolved_no_match_fallback(), "ask")
        self.assertFalse(config.takeover_mode().enabled)

    def test_toolguard_permissions_includes_rules_dir_patterns(self):
        """
        Given a rules-dir layer with a Bash allow pattern
        When toolguard_permissions() aggregates raw permissions
        Then the rules-dir pattern (tool wrapper intact) is included

        TOO-19 Phase 0a increment 8: compares `.pattern` since
        toolguard_permissions() now returns RuleEntry, not plain strings.
        """
        layers = (
            self._rules_layer(
                {"permissions": {"allow": ["Bash(gh *)"], "deny": [], "ask": []}},
                specificity=1,
            ),
        )
        config = Configuration(layers=layers)
        perms = config.toolguard_permissions()
        self.assertIn("Bash(gh *)", [e.pattern for e in perms["allow"]])

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


class TestRulesDirectoryValidationAndProvenance(
    ConfigIsolationMixin, unittest.TestCase
):
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

    def test_config_layer_shadowed_path_defaults_to_none(self):
        """
        Given a ConfigLayer constructed without a shadowed_path argument
        When its shadowed_path attribute is read
        Then it defaults to None (backward compatible with existing
        direct-construction call sites; TOO-19)
        """
        prov = Provenance(
            "user",
            "toolguard_hook_rules",
            "toml",
            Path("/u/.config/toolguard/rules/gh.toml"),
            1,
        )
        layer = ConfigLayer(prov, MappingProxyType({"permissions": {"allow": []}}))
        self.assertIsNone(layer.shadowed_path)

    # TOO-19 (2026-07-28): these four asserted against the private
    # _level_for_path(), which re-derived a source's level from its path shape
    # and has been REMOVED -- _discover_levels() now emits the level directly,
    # since it is the pass that actually found the file. The behaviours are
    # unchanged and still asserted, now through discovery itself, which also
    # makes them end-to-end rather than white-box.

    def _discovered_level(self, project, filename):
        """
        Return the level(s) discovery assigns to a file, by name.

        Args:
            project: Project root to discover from.
            filename: The file's base name.

        Returns:
            A list of level labels for every discovered source with that name.
        """
        return [
            level
            for path, _stype, _fmt, _spec, level in config_module._discover_levels(
                project
            )
            if path.name == filename
        ]

    def test_rules_dir_file_is_discovered_at_the_user_level(self):
        """
        Given a rules file in the (isolated, default-location) rules directory
        When the hierarchy levels are discovered
        Then the file is assigned the 'user' level, not 'project'
        """
        fake_home, project = self.isolate_config_environment()
        rules_dir = fake_home / ".config" / "toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "gh.toml").write_text("[permissions]\n")

        self.assertEqual(self._discovered_level(project, "gh.toml"), ["user"])

    def test_project_claude_file_is_discovered_at_the_project_level(self):
        """
        Given a config file in the project's own .claude directory
        When the hierarchy levels are discovered
        Then it is assigned the 'project' level
        """
        _fake_home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text("[permissions]\n")

        self.assertEqual(
            self._discovered_level(project, "toolguard_hook.toml"), ["project"]
        )

    def test_legacy_toolguard_rules_file_is_discovered_at_the_user_level(self):
        """
        Given a rules file in the legacy ~/.toolguard/rules directory
        When the hierarchy levels are discovered
        Then it is assigned the 'user' level (TOO-19: the second candidate
        rules directory is a user-level source)
        """
        fake_home, project = self.isolate_config_environment()
        legacy_rules_dir = fake_home / ".toolguard" / "rules"
        legacy_rules_dir.mkdir(parents=True)
        (legacy_rules_dir / "gh.toml").write_text("[permissions]\n")

        self.assertEqual(self._discovered_level(project, "gh.toml"), ["user"])

    def test_symlinked_rules_file_is_discovered_at_the_user_level(self):
        """
        Given a rules file physically under ~/.toolguard/rules, symlinked INTO
        the XDG rules directory (the real stopgap workaround shape from TOO-19)
        When the hierarchy levels are discovered
        Then it is still assigned the 'user' level

        Under the removed path-shape derivation this depended on resolve()
        landing on a recognised anchor. Discovery now assigns the level from
        WHERE THE FILE WAS FOUND, so the symlink target is irrelevant.
        """
        fake_home, project = self.isolate_config_environment()
        legacy_rules_dir = fake_home / ".toolguard" / "rules"
        legacy_rules_dir.mkdir(parents=True)
        real_file = legacy_rules_dir / "gh.rules.toml"
        real_file.write_text("[permissions]\n")
        xdg_rules_dir = fake_home / ".config" / "toolguard" / "rules"
        xdg_rules_dir.mkdir(parents=True)
        (xdg_rules_dir / "gh.rules.toml").symlink_to(real_file)

        levels = self._discovered_level(project, "gh.rules.toml")
        self.assertTrue(levels, "the symlinked rules file was not discovered at all")
        self.assertEqual(set(levels), {"user"})

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
            prov,
            MappingProxyType({"permissions": {"allow": ["Bash(gh *)"], "deny": []}}),
        )
        config = Configuration(layers=(layer,))

        def _decide(
            allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
        ) -> Optional[LevelMatch]:
            if "gh *" in allow:
                return LevelMatch(
                    decision="allow",
                    reason="Command matches allow pattern: gh *",
                    matched_pattern="gh *",
                )
            return None

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(config, "Bash", _decide)
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


class TestParseFailureAskFloor(unittest.TestCase):
    """
    TOO-19 fail-open fix: permission_resolution.resolve_permission_detailed()
    clamps every decision to 'ask' when Configuration.parse_failures is
    non-empty (a governed config file failed to parse), mirroring the ASK
    floor already implemented for foreign inline code in
    toolguard/compound.py:65-71 -- an explicit 'deny' (including hard_deny,
    which never reaches this function -- see resolve.py, checked before
    resolve_permission_detailed is called) is
    preserved unchanged; 'allow' and 'ask' are clamped to 'ask' with a reason
    naming the broken file(s). Closes the hole where a single TOML syntax
    error silently dropped every rule (including deny/hard_deny) in that
    file, with only an easy-to-miss stderr warning as evidence.

    These tests build Configuration directly from hand-constructed
    ConfigLayer/Provenance objects with zero file I/O, so no ConfigIsolationMixin
    is needed (per test/unit/CLAUDE.md's checklist).
    """

    @staticmethod
    def _config(*, allow=(), deny=(), parse_failures=()):
        """Build a single-layer project-level Bash Configuration.

        allow/deny are given as bare patterns; wrapped in Bash(...) here
        since permission_layers() strips that wrapper during extraction.
        """
        prov = Provenance(
            "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml")
        )
        layer = ConfigLayer(
            prov,
            MappingProxyType(
                {
                    "permissions": {
                        "allow": [f"Bash({p})" for p in allow],
                        "deny": [f"Bash({p})" for p in deny],
                    }
                }
            ),
        )
        return Configuration(layers=(layer,), parse_failures=parse_failures)

    @staticmethod
    def _decide_allow_git(
        allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
    ) -> Optional[LevelMatch]:
        """A decide_detailed closure that allows 'git *' when configured."""
        if "git *" in allow:
            return LevelMatch(
                decision="allow",
                reason="Command matches allow pattern: git *",
                matched_pattern="git *",
            )
        return None

    @staticmethod
    def _decide_deny_rm(
        allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
    ) -> Optional[LevelMatch]:
        """A decide_detailed closure that denies 'rm -rf /' when configured."""
        if "rm -rf /" in deny:
            return LevelMatch(
                decision="deny",
                reason="Command matches deny pattern: rm -rf /",
                matched_pattern="rm -rf /",
            )
        return None

    def test_allow_clamped_to_ask_when_config_broken(self):
        """
        Given a config whose Bash allow pattern matches the command AND a
            recorded parse_failures entry for a broken file
        When resolve_permission_detailed('Bash', ...) resolves the command
        Then the decision is 'ask' (not 'allow') and the reason names the
            broken file and its parse error, not the original allow reason
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        config = self._config(
            allow=["git *"], parse_failures=((broken, "unexpected character"),)
        )

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(
                config, "Bash", self._decide_allow_git
            )

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(broken), resolved.reason)
        self.assertIn("unexpected character", resolved.reason)
        self.assertNotIn("Command matches allow pattern", resolved.reason)

    def test_ask_reason_rewritten_to_name_broken_file(self):
        """
        Given a config with NO matching rule (falls through to the default
            'ask' no-match-fallback) AND a recorded parse failure
        When resolve_permission_detailed('Bash', ...) resolves the command
        Then the decision is 'ask' and the reason is the ASK-floor message
            naming the broken file -- not the generic no-match reason --
            mirroring compound.py's floor, which always rewrites the reason
            for a non-deny decision rather than only rewriting on 'allow'
        """
        broken = Path("/p/.claude/toolguard_hook.toml")
        config = self._config(parse_failures=((broken, "bad TOML"),))

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(
                config, "Bash", self._decide_allow_git
            )

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(broken), resolved.reason)
        self.assertNotIn("Command does not match any allow patterns", resolved.reason)

    def test_explicit_deny_not_weakened_when_config_broken(self):
        """
        Given a config whose Bash deny pattern matches the command AND a
            recorded parse failure for a DIFFERENT file
        When resolve_permission_detailed('Bash', ...) resolves the command
        Then the decision is still 'deny' -- a deny is never weakened by the
            ASK floor -- and the reason is the ORIGINAL deny reason, not the
            broken-file ASK-floor message
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        config = self._config(deny=["rm -rf /"], parse_failures=((broken, "boom"),))

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(config, "Bash", self._decide_deny_rm)

        self.assertEqual(resolved.decision, "deny")
        self.assertIn("Command matches deny pattern: rm -rf /", resolved.reason)
        self.assertNotIn(str(broken), resolved.reason)

    def test_valid_config_unaffected_no_parse_failures(self):
        """
        Given a config with NO recorded parse failures (the default/normal
            case -- Configuration.parse_failures defaults to ())
        When resolve_permission_detailed('Bash', ...) resolves an allow match
        Then the decision is 'allow', unchanged -- this is the most important
            regression guard: the overwhelming majority of the 1691-test
            baseline builds Configuration this way and must see zero change
        """
        config = self._config(allow=["git *"])

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(
                config, "Bash", self._decide_allow_git
            )

        self.assertEqual(resolved.decision, "allow")
        self.assertIn("Command matches allow pattern: git *", resolved.reason)

    def test_additional_context_cleared_by_ask_floor(self):
        """
        Given a structured allow entry carrying additionalContext AND a
            recorded parse failure for a broken file
        When resolve_permission_detailed('Bash', ...) resolves the command
        Then the decision is clamped to 'ask' by the floor and
            additional_context is None -- the winning rule match no longer
            determines the verdict, same reasoning as provenance/override
            being cleared
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        prov = Provenance(
            "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml")
        )
        layer = ConfigLayer(
            prov,
            MappingProxyType(
                {
                    "permissions": {
                        "allow": [{"match": "Bash(git *)", "additionalContext": "why"}],
                        "deny": [],
                    }
                }
            ),
        )
        config = Configuration(
            layers=(layer,), parse_failures=((broken, "unexpected character"),)
        )

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(
                config, "Bash", self._decide_allow_git
            )

        self.assertEqual(resolved.decision, "ask")
        self.assertIsNone(resolved.additional_context)

    def test_undecidable_fallback_allow_with_warning_does_not_relax_parse_failure_floor(
        self,
    ):
        """
        HARD INVARIANT (TOO-19): the parse-failure ASK floor is permanently
        exempt from undecidable_fallback -- no config value may ever relax it.

        Given a config with undecidable_fallback='allow_with_warning' (the
            most permissive possible setting -- the deliberate "no floor"
            escape hatch) AND a recorded parse failure for a broken file, and
            an allow rule that matches the command
        When resolve_permission_detailed('Bash', ...) resolves the command
        Then the decision is STILL clamped to 'ask' -- a broken config is not
            a policy question undecidable_fallback (or any setting) can
            answer, so it is completely unaffected by this test's
            undecidable_fallback value
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        prov = Provenance(
            "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml")
        )
        layer = ConfigLayer(
            prov,
            MappingProxyType(
                {
                    "undecidable_fallback": "allow_with_warning",
                    "permissions": {
                        "allow": ["Bash(git *)"],
                        "deny": [],
                    },
                }
            ),
        )
        config = Configuration(
            layers=(layer,), parse_failures=((broken, "unexpected character"),)
        )
        # Confirm the fixture actually set the permissive value under test --
        # a self-check that this test would notice if resolved_undecidable_fallback()
        # itself regressed.
        self.assertEqual(config.resolved_undecidable_fallback(), "allow_with_warning")

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_permission_detailed(
                config, "Bash", self._decide_allow_git
            )

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(broken), resolved.reason)


class TestAdditionalContextResolution(unittest.TestCase):
    """
    TOO-19 Phase 1, increment 2: permission_resolution._resolve_unclamped
    surfaces the winning RuleEntry's additional_context property onto
    RuntimeVerdict.additional_context.

    These tests build Configuration directly from hand-constructed
    ConfigLayer/Provenance objects with zero file I/O, so no ConfigIsolationMixin
    is needed (per test/unit/CLAUDE.md's checklist).
    """

    @staticmethod
    def _config(*, allow=(), deny=(), ask=()):
        """
        Build a single-layer project-level Bash Configuration.

        Each of allow/deny/ask is a list of raw permission-list elements
        (plain strings or structured {match=..., additionalContext=...}
        dicts) -- NOT yet Bash(...)-wrapped, since this helper wraps the
        'match'/plain-string pattern itself.
        """

        def _wrap(entry):
            if isinstance(entry, dict):
                wrapped = dict(entry)
                wrapped["match"] = f"Bash({wrapped['match']})"
                return wrapped
            return f"Bash({entry})"

        prov = Provenance(
            "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml")
        )
        layer = ConfigLayer(
            prov,
            MappingProxyType(
                {
                    "permissions": {
                        "allow": [_wrap(e) for e in allow],
                        "deny": [_wrap(e) for e in deny],
                        "ask": [_wrap(e) for e in ask],
                    }
                }
            ),
        )
        return Configuration(layers=(layer,))

    @staticmethod
    def _decide(
        allow: Sequence[str], deny: Sequence[str], ask: Sequence[str]
    ) -> Optional[LevelMatch]:
        """A decide_detailed closure that deny-first/ask/allow-matches 'git *'."""
        if "git *" in deny:
            return LevelMatch(
                decision="deny",
                reason="Command matches deny pattern: git *",
                matched_pattern="git *",
            )
        if "git *" in ask:
            return LevelMatch(
                decision="ask",
                reason="Command matches ask pattern: git *",
                matched_pattern="git *",
            )
        if "git *" in allow:
            return LevelMatch(
                decision="allow",
                reason="Command matches allow pattern: git *",
                matched_pattern="git *",
            )
        return None

    def _resolve(self, config):
        """Resolve 'git *' against *config* with takeover mode disabled."""
        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            return resolve_permission_detailed(config, "Bash", self._decide)

    def test_structured_allow_entry_surfaces_additional_context(self):
        """
        Given a structured allow entry with additionalContext = 'why'
        When resolve_permission_detailed('Bash', ...) resolves a match
        Then the decision is 'allow' and additional_context is 'why'
        """
        config = self._config(allow=[{"match": "git *", "additionalContext": "why"}])
        resolved = self._resolve(config)
        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(resolved.additional_context, "why")

    def test_structured_deny_entry_surfaces_additional_context(self):
        """
        Given a structured deny entry with additionalContext = 'why not'
        When resolve_permission_detailed('Bash', ...) resolves a match
        Then the decision is 'deny' and additional_context is 'why not'
        """
        config = self._config(deny=[{"match": "git *", "additionalContext": "why not"}])
        resolved = self._resolve(config)
        self.assertEqual(resolved.decision, "deny")
        self.assertEqual(resolved.additional_context, "why not")

    def test_structured_ask_entry_surfaces_additional_context(self):
        """
        Given a structured ask entry with additionalContext = 'careful'
        When resolve_permission_detailed('Bash', ...) resolves a match
        Then the decision is 'ask' and additional_context is 'careful'
        """
        config = self._config(ask=[{"match": "git *", "additionalContext": "careful"}])
        resolved = self._resolve(config)
        self.assertEqual(resolved.decision, "ask")
        self.assertEqual(resolved.additional_context, "careful")

    def test_plain_string_rule_yields_none(self):
        """
        Given a plain-string (unstructured) allow rule
        When resolve_permission_detailed('Bash', ...) resolves a match
        Then additional_context is None -- there is no metadata to surface
        """
        config = self._config(allow=["git *"])
        resolved = self._resolve(config)
        self.assertEqual(resolved.decision, "allow")
        self.assertIsNone(resolved.additional_context)

    def test_structured_entry_without_key_yields_none(self):
        """
        Given a structured allow entry with no additionalContext key at all
        When resolve_permission_detailed('Bash', ...) resolves a match
        Then additional_context is None
        """
        config = self._config(allow=[{"match": "git *", "autoMode": True}])
        resolved = self._resolve(config)
        self.assertEqual(resolved.decision, "allow")
        self.assertIsNone(resolved.additional_context)

    def test_no_match_fallback_yields_none(self):
        """
        Given a config with rules configured but none matching the command
        When resolve_permission_detailed('Bash', ...) falls through to the
            no_match_fallback branch
        Then additional_context is None (no rule matched, nothing to surface)
        """
        config = self._config(allow=[{"match": "ls *", "additionalContext": "why"}])
        resolved = self._resolve(config)
        self.assertIsNone(resolved.additional_context)


class TestEntryForPatternLookup(unittest.TestCase):
    """
    ``config_types.entry_for_pattern`` (TOO-45 R2d: moved off ``Configuration``,
    beside :class:`ToolPatternLayer`, which it searches).

    Built directly from hand-constructed ToolPatternLayer objects with zero
    file I/O (no ConfigIsolationMixin needed, per test/unit/CLAUDE.md's
    checklist).

    TOO-45 R2 note: the pre-R2 version of this class (``TestEntryForPatternDrift``)
    also covered a DRIFTED-parallel-lists corner case (TOO-19 code review m4):
    ``ToolPatternLayer`` used to store ``allow``/``allow_entries`` as two
    independent, positionally-correlated fields, so a caller could construct
    one with mismatched lengths and the lookup had to defensively guard
    against that. R2 made ``allow``/``deny``/``ask`` derived properties over
    ``allow_entries``/``deny_entries``/``ask_entries`` -- the only stored
    fields -- so that drifted state is no longer constructible at all (see
    ``test_layer_rejects_a_separately_supplied_pattern_tuple`` below). The two
    tests that existed only to fire that now-deleted defensive guard
    (``test_misaligned_layer_returns_none_instead_of_falling_through``,
    ``test_drift_does_not_change_the_resolved_verdict``) were deleted along
    with it; the remaining (never-drifted) lookup test is kept, adapted to
    the new call target.
    """

    @staticmethod
    def _entry(pattern, context=None):
        metadata = MappingProxyType(
            {ADDITIONAL_CONTEXT_KEY: context} if context else {}
        )
        return RuleEntry(pattern=pattern, metadata=metadata)

    def test_aligned_layer_resolves_normally(self):
        """
        Given a layer with one allow entry
        When entry_for_pattern searches for the pattern it contains
        Then it returns that layer's own entry
        """
        layer = ToolPatternLayer(
            provenance=Provenance("project", "toolguard_hook", "toml", Path("/p.toml")),
            allow_entries=(self._entry("git *", "normal context"),),
        )
        result = entry_for_pattern((layer,), "git *", "allow")
        self.assertIsNotNone(result)
        self.assertEqual(result.additional_context, "normal context")

    def test_layer_rejects_a_separately_supplied_pattern_tuple(self):
        """
        Given an attempt to construct a ToolPatternLayer the OLD way, with a
            separately-supplied `allow` pattern tuple alongside `allow_entries`
        When the constructor call is made
        Then it raises TypeError -- `allow` is a derived property, not a
            constructor field, so a hand-drifted pair of parallel lists (the
            defect the deleted TestEntryForPatternDrift tests existed to
            guard against) can no longer be built at all
        """
        with self.assertRaises(TypeError):
            ToolPatternLayer(
                provenance=Provenance(
                    "project", "toolguard_hook", "toml", Path("/p.toml")
                ),
                allow=("git *", "ls *"),
                allow_entries=(self._entry("git *"),),
            )


class TestParseFailuresPropagation(ConfigIsolationMixin, unittest.TestCase):
    """
    load_configuration() records genuinely broken (exists-but-unparseable)
    config files into Configuration.parse_failures, but never for files that
    are merely absent or a valid-but-differently-shaped sibling (TOO-19 scope
    note: "broken" means the file existed and failed to parse/was not a
    table -- not "absent").
    """

    def test_broken_rules_dir_file_recorded_alongside_valid_layer(self):
        """
        Given a broken (unparseable) TOML file in the candidate rules
            directory alongside a separately valid toolguard_hook.toml
        When load_configuration() runs
        Then Configuration.parse_failures has exactly one entry naming the
            broken file, while the valid file's rules are still available
        """
        home, project = self.isolate_config_environment(
            xdg_config_home="/nonexistent-xdg"
        )
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            '[permissions]\nallow = ["Bash(git *)"]\n'
        )
        rules_dir = home / ".toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        broken_path = rules_dir / "gh.toml"
        broken_path.write_text("[permissions]\nallow = [\n")  # unterminated array

        with patch("sys.stderr", new_callable=io.StringIO):
            config = load_configuration()

        self.assertEqual(len(config.parse_failures), 1)
        recorded_path, message = config.parse_failures[0]
        self.assertEqual(recorded_path, broken_path)
        self.assertTrue(message)

        allow, _deny = config.allow_deny_for("Bash")
        self.assertIn("git *", allow)

    def test_broken_file_warning_reaches_stderr(self):
        """
        Given a broken (unparseable) TOML file in the candidate rules
            directory
        When load_configuration() runs
        Then the failure message, naming the broken file, reaches stderr
            (TOO-45 punch-list #04: via error_reporter.report_warning, no
            Reporter registered in this test so it degrades to the bare
            message -- see toolguard.error_reporter)
        """
        home, project = self.isolate_config_environment(
            xdg_config_home="/nonexistent-xdg"
        )
        rules_dir = home / ".toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        broken_path = rules_dir / "gh.toml"
        broken_path.write_text("[permissions]\nallow = [\n")  # unterminated array

        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            load_configuration()

        self.assertIn(str(broken_path), stderr_buf.getvalue())
        self.assertIn("Failed to load", stderr_buf.getvalue())

    def test_broken_file_warning_reaches_the_warning_log_with_an_active_reporter(
        self,
    ):
        """
        Given a broken (unparseable) TOML file in the candidate rules
            directory, AND a registered error_reporter.Reporter with a
            resolvable log directory is active (TOO-45 punch-list #04 fix
            pass item 8a: a real converted call site, not a synthetic
            message)
        When load_configuration() runs
        Then the failure, naming the broken file, lands in the WARNING log
             file, not just stderr
        """
        home, project = self.isolate_config_environment(
            xdg_config_home="/nonexistent-xdg"
        )
        rules_dir = home / ".toolguard" / "rules"
        rules_dir.mkdir(parents=True)
        broken_path = rules_dir / "gh.toml"
        broken_path.write_text("[permissions]\nallow = [\n")  # unterminated array
        log_dir = project / "logs"
        log_dir.mkdir()

        with error_reporter.active(error_reporter.Reporter(log_dir=log_dir)):
            load_configuration()

        warning_files = list(log_dir.glob("toolguard-warning-*.md"))
        self.assertEqual(len(warning_files), 1)
        content = warning_files[0].read_text()
        self.assertIn(str(broken_path), content)
        self.assertIn("Failed to load", content)

    def test_valid_config_has_no_parse_failures(self):
        """
        Given a completely valid, well-formed configuration
        When load_configuration() runs
        Then Configuration.parse_failures is empty -- the primary regression
            guard for the "no existing behaviour changes" requirement
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "toolguard_hook.toml").write_text(
            '[permissions]\nallow = ["Bash(git *)"]\n'
        )

        config = load_configuration()

        self.assertEqual(config.parse_failures, ())

    def test_top_level_not_a_table_is_a_parse_failure(self):
        """
        Given a syntactically valid JSON file whose top level is a bare array
            (not an object/table) -- _parse_source's other None-return case
        When load_configuration() runs
        Then it is recorded in Configuration.parse_failures too: the same
            silent-information-loss reasoning applies (every rule in the file
            is dropped with only a stderr warning), so it counts as "broken"
        """
        _home, project = self.isolate_config_environment()
        claude_dir = project / ".claude"
        claude_dir.mkdir()
        bad_path = claude_dir / "settings.local.json"
        bad_path.write_text(json.dumps([1, 2, 3]))

        with patch("sys.stderr", new_callable=io.StringIO):
            config = load_configuration()

        self.assertEqual(len(config.parse_failures), 1)
        recorded_path, message = config.parse_failures[0]
        self.assertEqual(recorded_path, bad_path)
        self.assertIn("table", message)

    def test_claude_settings_path_missing_file_is_not_a_parse_failure(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a file that does not exist on
            disk at all
        When load_configuration() runs
        Then Configuration.parse_failures is empty -- absence is not
            "broken" (scope note: only exists-but-unparseable files count),
            even though the pre-existing stderr warning for a missing file
            is still printed unchanged
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist.json"
            self.isolate_config_environment(
                extra_env={"CLAUDE_SETTINGS_PATH": str(missing)}
            )
            with patch("sys.stderr", new_callable=io.StringIO) as captured:
                config = load_configuration()

        self.assertEqual(config.parse_failures, ())
        self.assertIn(str(missing), captured.getvalue())

    def test_claude_settings_path_broken_file_is_a_parse_failure(self):
        """
        Given CLAUDE_SETTINGS_PATH points at a file that exists but fails to
            parse (malformed JSON)
        When load_configuration() runs
        Then Configuration.parse_failures has one entry for it -- the
            explicit single-file branch feeds load_configuration's returned
            Configuration just like the hierarchy-discovery branch, so it
            must propagate too
        """
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "settings.json"
            broken.write_text("{not valid json")
            self.isolate_config_environment(
                extra_env={"CLAUDE_SETTINGS_PATH": str(broken)}
            )
            with patch("sys.stderr", new_callable=io.StringIO):
                config = load_configuration()

        self.assertEqual(len(config.parse_failures), 1)
        recorded_path, _message = config.parse_failures[0]
        self.assertEqual(recorded_path, broken)


class TestValidationIssuesParseFailures(unittest.TestCase):
    """validation_issues() reports each recorded parse failure as an 'error'."""

    def test_reports_error_issue_per_broken_file(self):
        """
        Given a Configuration with two recorded parse_failures entries
        When validation_issues() is called
        Then it returns one 'error'-level Issue per broken file, each
            naming that file's path
        """
        broken_a = Path("/p/.claude/toolguard_hook.toml")
        broken_b = Path("/p/.claude/toolguard_hook.local.toml")
        config = Configuration(
            layers=(),
            parse_failures=((broken_a, "bad TOML"), (broken_b, "also bad")),
        )

        issues = config.validation_issues()
        error_issues = [i for i in issues if i.level == "error"]
        messages = [i.message for i in error_issues]

        self.assertTrue(any(str(broken_a) in m for m in messages))
        self.assertTrue(any(str(broken_b) in m for m in messages))

    def test_no_issues_when_no_parse_failures(self):
        """
        Given a Configuration with an empty parse_failures (the default)
        When validation_issues() is called
        Then no parse-failure-related error issue is produced
        """
        config = Configuration(layers=())

        issues = config.validation_issues()

        self.assertEqual(issues, ())


if __name__ == "__main__":
    unittest.main()
