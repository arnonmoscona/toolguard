"""
Unit tests for toolguard.tools.config_access.

Tests for the thin facade over Configuration: per-layer rule listing,
effective takeover exposure, and config summary.

All tests use stdlib unittest with BDD Given/When/Then docstrings.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import Optional as _Optional
from unittest.mock import patch

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
)
from toolguard.tools.config_access import (
    RuleComment,
    audit_context,
    config_summary,
    discover_tools,
    effective_takeover,
    load_config,
    neutralized_by_takeover,
    nosecurity_reason_for,
    per_layer_rules,
    rule_comments_for_tool,
)


def _write_toml(claude_dir: Path, filename: str, content: str) -> None:
    """Write a TOML config file under claude_dir."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / filename).write_text(content, encoding="utf-8")


class _IsolatedEnvTestCase(unittest.TestCase):
    """Base: removes CLAUDE_SETTINGS_PATH so hierarchy discovery is not diverted."""

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("CLAUDE_SETTINGS_PATH", None)
        self.addCleanup(self._env_patch.stop)


class TestLoadConfig(_IsolatedEnvTestCase):
    """Tests for config_access.load_config()."""

    def test_load_config_returns_configuration(self):
        """
        Given a minimal project with a toolguard_hook.toml
        When load_config is called with the project directory
        Then a Configuration object is returned with at least one layer
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            config = load_config(proj)
            self.assertIsNotNone(config)
            self.assertGreater(len(config.layers), 0)

    def test_load_config_ignores_env_override(self):
        """
        Given CLAUDE_SETTINGS_PATH set to an unrelated file
        When load_config is called (which uses ignore_env_override=True)
        Then the project hierarchy is used, not the env override
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(git:*)"]',
            )
            # Set env override to a nonexistent path
            with patch.dict(
                os.environ,
                {"CLAUDE_SETTINGS_PATH": "/nonexistent/settings.json"},
            ):
                config = load_config(proj)
            # Should still find the project config (ignoring the bad env path)
            allow, _ = config.allow_deny_for("Bash")
            self.assertIn("git:*", allow)


class TestPerLayerRules(_IsolatedEnvTestCase):
    """Tests for config_access.per_layer_rules()."""

    def test_per_layer_rules_returns_allow_deny_ask(self):
        """
        Given a config with allow, deny and ask rules for Bash
        When per_layer_rules is called with tool_name='Bash'
        Then the returned LayerRules carries the correct allow, deny, and ask patterns
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                """
[permissions]
allow = ["Bash(git:*)"]
deny = ["Bash(rm -rf:*)"]
ask = ["Bash(sudo:*)"]
""",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            self.assertGreater(len(layers), 0)
            # The project-level layer should have the expected patterns
            project_layer = layers[0]
            self.assertIn("git:*", project_layer.allow)
            self.assertIn("rm -rf:*", project_layer.deny)
            self.assertIn("sudo:*", project_layer.ask)

    def test_per_layer_rules_surfaces_structured_ask_entry(self):
        """
        Given a toolguard_hook.toml whose "ask" list contains a structured
            ({match = ..., additionalContext = ...}) entry rather than a bare
            string
        When per_layer_rules is called with tool_name='Bash'
        Then the structured entry's pattern is present in the layer's ask
            tuple -- TOO-19 fix: the previous hand-rolled ask extraction only
            recognized bare strings (isinstance(perm, str)) and silently
            dropped a structured ask entry, making it invisible to
            maintenance/security-audit tooling
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                """
[permissions]
allow = []
deny = []
ask = [{ match = "Bash(sudo:*)", additionalContext = "needs review" }]
""",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            project_layer = layers[0]
            self.assertIn("sudo:*", project_layer.ask)

    def test_per_layer_rules_native_layer_has_no_ask(self):
        """
        Given a native Claude settings.json file with allow rules
        When per_layer_rules is called
        Then the native layer has empty ask list (native settings have no ask concept)
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            claude.mkdir(parents=True, exist_ok=True)
            (claude / "settings.json").write_text(
                json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}),
                encoding="utf-8",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            native_layers = [
                lr for lr in layers if lr.provenance.source_type == "claude"
            ]
            for lr in native_layers:
                self.assertEqual((), lr.ask)

    def test_per_layer_rules_multiple_levels_most_specific_first(self):
        """
        Given project-level and user-level configs with different allow patterns
        When per_layer_rules is called
        Then the first returned layer corresponds to the project level (most specific)
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            proj_claude = proj / ".claude"
            _write_toml(
                proj_claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(git:*)"]',
            )
            user_claude = Path(tmpdir) / ".claude"
            _write_toml(
                user_claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                layers = per_layer_rules(config, "Bash")

            self.assertGreater(len(layers), 1)
            # First layer (most specific = project) should have 'git:*'
            self.assertIn("git:*", layers[0].allow)


class TestEffectiveTakeover(_IsolatedEnvTestCase):
    """Tests for config_access.effective_takeover()."""

    def test_effective_takeover_enabled(self):
        """
        Given a config with takeover_mode.enabled = true
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=True
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                "[takeover_mode]\nenabled = true\n",
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                takeover = effective_takeover(config)

            self.assertTrue(takeover.enabled)

    def test_effective_takeover_disabled_by_default(self):
        """
        Given a config with no takeover_mode section
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=False (default off)
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                '[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                takeover = effective_takeover(config)

            self.assertFalse(takeover.enabled)


class TestConfigSummary(_IsolatedEnvTestCase):
    """Tests for config_access.config_summary()."""

    def test_config_summary_reports_sources_and_tools(self):
        """
        Given a project config that governs Bash and Read
        When config_summary is called
        Then the summary reports the correct governed tools and non-zero source count
        """

        with tempfile.TemporaryDirectory() as tmpdir:
            proj = Path(tmpdir) / "proj"
            proj.mkdir()
            (proj / ".git").mkdir()
            claude = proj / ".claude"
            _write_toml(
                claude,
                "toolguard_hook.toml",
                'governed_tools = ["Bash", "Read"]\n[permissions]\nallow = ["Bash(ls:*)"]',
            )
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config = load_config(proj)
                summary = config_summary(config)

            self.assertIn("Bash", summary.governed_tools)
            self.assertIn("Read", summary.governed_tools)
            self.assertGreater(summary.layer_count, 0)
            self.assertGreater(len(summary.sources), 0)


# ---------------------------------------------------------------------------
# Fixture helpers for the new tests
# ---------------------------------------------------------------------------

# These mirror the style used in test_tools_security_audit.py so the two
# test files stay consistent in fixture approach.


def _prov(
    level: str = "project",
    source_type: str = "toolguard_hook",
    path: str = "/fake/.claude/toolguard_hook.toml",
    specificity: int = 0,
) -> Provenance:
    """Build a Provenance for test use."""
    return Provenance(
        level=level,
        source_type=source_type,
        file_format="toml",
        path=Path(path),
        specificity=specificity,
    )


def _toolguard_layer(
    allow: _Optional[list] = None,
    deny: _Optional[list] = None,
    ask: _Optional[list] = None,
    specificity: int = 0,
    takeover_enabled: _Optional[bool] = None,
    ignored_allow_patterns: _Optional[list] = None,
) -> ConfigLayer:
    """Build a toolguard_hook ConfigLayer."""
    content: dict = {}
    perms: dict = {}
    if allow is not None:
        perms["allow"] = allow
    if deny is not None:
        perms["deny"] = deny
    if ask is not None:
        perms["ask"] = ask
    if perms:
        content["permissions"] = perms
    takeover_section: dict = {}
    if takeover_enabled is not None:
        takeover_section["enabled"] = takeover_enabled
    if ignored_allow_patterns is not None:
        takeover_section["ignored_allow_patterns"] = ignored_allow_patterns
    if takeover_section:
        content["takeover_mode"] = takeover_section
    return ConfigLayer(
        provenance=_prov(specificity=specificity),
        content=MappingProxyType(content),
    )


def _native_layer(
    allow: _Optional[list] = None,
    specificity: int = 1,
) -> ConfigLayer:
    """Build a native Claude settings ConfigLayer."""
    content: dict = {}
    if allow is not None:
        content["permissions"] = {"allow": allow, "deny": []}
    return ConfigLayer(
        provenance=_prov(
            level="project",
            source_type="claude",
            path="/fake/.claude/settings.local.json",
            specificity=specificity,
        ),
        content=MappingProxyType(content),
    )


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


# ---------------------------------------------------------------------------
# Tests for discover_tools
# ---------------------------------------------------------------------------


class TestDiscoverTools(unittest.TestCase):
    """Tests for config_access.discover_tools()."""

    def test_discovers_tool_from_allow_list(self):
        """
        Given a config with a Bash allow rule in one layer
        When discover_tools is called
        Then 'Bash' appears in the returned tuple
        """

        layer = _toolguard_layer(allow=["Bash(git:*)"])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)

    def test_discovers_tool_from_deny_list(self):
        """
        Given a config whose only rule is a Bash deny (no allow)
        When discover_tools is called
        Then 'Bash' is still discovered (deny list also counts)
        """

        layer = _toolguard_layer(deny=["Bash(rm -rf:*)"])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)

    def test_discovers_tool_from_ask_list(self):
        """
        Given a config whose only rule is a Bash ask
        When discover_tools is called
        Then 'Bash' is still discovered (ask list also counts)
        """

        layer = _toolguard_layer(ask=["Bash(sudo:*)"])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)

    def test_discovers_multiple_tools_deduped(self):
        """
        Given a config with Bash and Read rules across two layers
        When discover_tools is called
        Then both tools appear exactly once (de-duplication)
        """

        layer1 = _toolguard_layer(allow=["Bash(ls:*)", "Read(*.py)"])
        layer2 = _toolguard_layer(allow=["Bash(git:*)"])  # Bash again
        config = _make_config(layer1, layer2)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)
        self.assertIn("Read", tools)
        self.assertEqual(tools.count("Bash"), 1, "Bash should appear only once")

    def test_result_is_sorted(self):
        """
        Given a config with Write, Bash, and Read rules
        When discover_tools is called
        Then the returned tuple is sorted alphabetically
        """

        layer = _toolguard_layer(allow=["Write(/tmp:*)", "Bash(ls:*)", "Read(*.txt)"])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertEqual(list(tools), sorted(tools))

    def test_empty_config_returns_empty_tuple(self):
        """
        Given a config with no permission rules (no allow/deny/ask in any layer)
        When discover_tools is called
        Then an empty tuple is returned
        """

        layer = _toolguard_layer()  # no permissions
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertEqual(tools, ())

    def test_discovers_tool_from_native_layer(self):
        """
        Given a config with only a native layer that has a Bash allow
        When discover_tools is called
        Then 'Bash' is discovered (native layers are also scanned)
        """

        layer = _native_layer(allow=["Bash(*)"])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)

    def test_discovers_tool_governed_only_by_structured_entry(self):
        """
        TOO-19 fix: given a config whose ONLY rule for a tool is a structured
            ({match = ..., additionalContext = ...}) allow entry -- no bare
            string entry for that tool at all
        When discover_tools is called
        Then the tool is still discovered -- previously the bare
            isinstance(perm, str) check silently skipped structured entries,
            so a tool governed only by one was invisible to this function
        """

        structured = {"match": "Bash(sudo:*)", "additionalContext": "needs review"}
        layer = _toolguard_layer(allow=[structured])
        config = _make_config(layer)
        tools = discover_tools(config)
        self.assertIn("Bash", tools)


# ---------------------------------------------------------------------------
# Tests for neutralized_by_takeover
# ---------------------------------------------------------------------------


class TestNeutralizedByTakeover(unittest.TestCase):
    """Tests for config_access.neutralized_by_takeover()."""

    def _takeover_on(self, ignored: list) -> TakeoverConfig:
        """Build a TakeoverConfig with takeover enabled and given ignored patterns."""
        return TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=tuple(ignored),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )

    def _takeover_off(self) -> TakeoverConfig:
        """Build a TakeoverConfig with takeover disabled."""
        return TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=(),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )

    def test_true_when_all_conditions_met(self):
        """
        Given takeover enabled, pattern is native, and pattern is in ignored set
        When neutralized_by_takeover is called
        Then True is returned
        """

        # normalized_ignored_patterns strips the tool wrapper, so "*" maps to "Bash(*)"
        takeover = self._takeover_on(["Bash(*)"])
        result = neutralized_by_takeover("*", is_native=True, takeover=takeover)
        self.assertTrue(result)

    def test_false_when_takeover_disabled(self):
        """
        Given takeover disabled (enabled=False), native pattern in what would be ignored
        When neutralized_by_takeover is called
        Then False is returned (takeover is OFF)
        """

        takeover = self._takeover_off()
        result = neutralized_by_takeover("*", is_native=True, takeover=takeover)
        self.assertFalse(result)

    def test_false_when_not_native(self):
        """
        Given takeover enabled, pattern in ignored set, but layer is NOT native
        When neutralized_by_takeover is called
        Then False is returned (only native layers can be neutralized)
        """

        takeover = self._takeover_on(["Bash(*)"])
        result = neutralized_by_takeover("*", is_native=False, takeover=takeover)
        self.assertFalse(result)

    def test_false_when_pattern_not_in_ignored_set(self):
        """
        Given takeover enabled and layer is native, but pattern NOT in the ignored set
        When neutralized_by_takeover is called
        Then False is returned (specific pattern is not suppressed)
        """

        takeover = self._takeover_on(["Bash(*)"])  # only Bash(*) is ignored
        result = neutralized_by_takeover(
            "git status", is_native=True, takeover=takeover
        )
        self.assertFalse(result)

    def test_additional_ignored_patterns_also_neutralize(self):
        """
        Given takeover enabled, native layer, and pattern is in additional_ignored_patterns
        When neutralized_by_takeover is called
        Then True is returned (additional patterns also count)
        """

        takeover = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=(),
            additional_ignored_patterns=("Read(*)",),
            no_match_fallback="deny",
        )
        # normalized_ignored_patterns strips "Read(" and ")" -> "*"
        result = neutralized_by_takeover("*", is_native=True, takeover=takeover)
        self.assertTrue(result)


# ---------------------------------------------------------------------------
# Tests for audit_context
# ---------------------------------------------------------------------------


class TestAuditContext(unittest.TestCase):
    """Tests for config_access.audit_context()."""

    def test_summary_and_takeover_populated(self):
        """
        Given a simple config with one toolguard layer
        When audit_context is called
        Then summary and takeover fields are populated (non-None)
        """

        layer = _toolguard_layer(allow=["Bash(ls:*)"])
        config = _make_config(layer)
        ctx = audit_context(config)
        self.assertIsNotNone(ctx.summary)
        self.assertIsNotNone(ctx.takeover)

    def test_tools_tuple_contains_discovered_tools(self):
        """
        Given a config with Bash and Read rules
        When audit_context is called
        Then tools contains a ToolContext for each tool
        """

        layer = _toolguard_layer(allow=["Bash(ls:*)", "Read(*.py)"])
        config = _make_config(layer)
        ctx = audit_context(config)
        tool_names = tuple(tc.tool for tc in ctx.tools)
        self.assertIn("Bash", tool_names)
        self.assertIn("Read", tool_names)

    def test_tools_sorted_by_name(self):
        """
        Given a config with multiple tools in unsorted order
        When audit_context is called
        Then ctx.tools is ordered alphabetically by tool name
        """

        layer = _toolguard_layer(allow=["Write(/tmp:*)", "Bash(ls:*)", "Read(*.py)"])
        config = _make_config(layer)
        ctx = audit_context(config)
        names = [tc.tool for tc in ctx.tools]
        self.assertEqual(names, sorted(names))

    def test_native_layer_flagged_is_native_true(self):
        """
        Given a config with both a toolguard layer and a native settings layer
        When audit_context is called
        Then the LayerContext for the native layer has is_native=True
        """

        tg_layer = _toolguard_layer(allow=["Bash(ls:*)"])
        native = _native_layer(allow=["Bash(*)"])
        config = _make_config(tg_layer, native)
        ctx = audit_context(config)
        bash_tool = next(tc for tc in ctx.tools if tc.tool == "Bash")
        native_layer_ctxs = [lc for lc in bash_tool.layers if lc.is_native]
        self.assertGreater(
            len(native_layer_ctxs), 0, "Expected at least one native LayerContext"
        )

    def test_toolguard_layer_flagged_is_native_false(self):
        """
        Given a config with a toolguard_hook layer
        When audit_context is called
        Then the LayerContext for the toolguard layer has is_native=False
        """

        tg_layer = _toolguard_layer(allow=["Bash(ls:*)"])
        config = _make_config(tg_layer)
        ctx = audit_context(config)
        bash_tool = next(tc for tc in ctx.tools if tc.tool == "Bash")
        toolguard_layer_ctxs = [lc for lc in bash_tool.layers if not lc.is_native]
        self.assertGreater(
            len(toolguard_layer_ctxs),
            0,
            "Expected at least one non-native LayerContext",
        )

    def test_neutralized_allow_patterns_empty_when_takeover_off(self):
        """
        Given a config with no takeover mode enabled
        When audit_context is called
        Then neutralized_allow_patterns is an empty tuple (nothing can be neutralized)
        """

        tg_layer = _toolguard_layer(allow=["Bash(ls:*)"])
        native = _native_layer(allow=["Bash(*)"])
        config = _make_config(tg_layer, native)
        ctx = audit_context(config)
        self.assertFalse(ctx.takeover.enabled)
        self.assertEqual(ctx.neutralized_allow_patterns, ())

    def test_neutralized_allow_patterns_lists_native_blanket_under_takeover(self):
        """
        Given a config with takeover enabled, Bash(*) in ignored set, and native Bash(*) allow
        When audit_context is called
        Then neutralized_allow_patterns contains the extracted pattern ('*')
        """

        tg_layer = _toolguard_layer(
            allow=["Bash(ls:*)"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)"],
        )
        native = _native_layer(allow=["Bash(*)"])
        config = _make_config(tg_layer, native)
        ctx = audit_context(config)
        self.assertTrue(ctx.takeover.enabled)
        # normalized_ignored_patterns strips the wrapper -> "*"
        self.assertIn("*", ctx.neutralized_allow_patterns)

    def test_layer_context_locus_matches_describe(self):
        """
        Given a config layer with known provenance
        When audit_context is called
        Then each LayerContext.locus matches provenance.describe() for that layer
        """

        tg_layer = _toolguard_layer(allow=["Bash(ls:*)"])
        config = _make_config(tg_layer)
        ctx = audit_context(config)
        bash_tool = next(tc for tc in ctx.tools if tc.tool == "Bash")
        expected_locus = tg_layer.provenance.describe()
        loci = [lc.locus for lc in bash_tool.layers]
        self.assertIn(expected_locus, loci)

    def test_neutralized_allow_patterns_is_sorted_and_deduped(self):
        """
        Given a config with multiple tools having the same native blanket allow under takeover
        When audit_context is called
        Then neutralized_allow_patterns is sorted and contains no duplicates
        """

        tg_layer = _toolguard_layer(
            allow=["Bash(ls:*)", "Read(*.txt)"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        )
        native = _native_layer(allow=["Bash(*)", "Read(*)"])
        config = _make_config(tg_layer, native)
        ctx = audit_context(config)
        pats = list(ctx.neutralized_allow_patterns)
        self.assertEqual(
            pats, sorted(set(pats)), "Patterns should be sorted and unique"
        )


class TestRuleCommentExposure(unittest.TestCase):
    """Per-rule comment recovery and the ``#NOSECURITY`` acknowledge-not-hide tag."""

    _TOML = (
        "[permissions]\n"
        "allow = [\n"
        "    'Bash(node:*)',  # NOSECURITY: intentional dev tool\n"
        "    # NOSECURITY\n"
        "    'Bash(ruby:*)',\n"
        "    'Bash(git:*)',\n"
        "    'Bash([regex]^ls#notacomment)',\n"
        "]\n"
        "deny = []\n"
        "ask = []\n"
    )

    def _prov(self, path: Path, file_format: str = "toml") -> Provenance:
        """Build a toolguard_hook Provenance pointing at a real file path."""
        return Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format=file_format,
            path=path,
            specificity=0,
        )

    def test_inline_nosecurity_reason_recovered(self):
        """
        Given a TOML allow rule 'Bash(node:*)' with an inline
        '# NOSECURITY: intentional dev tool' comment
        When nosecurity_reason_for is called for that rule
        Then it returns the reason text 'intentional dev tool'
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            self.assertEqual(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "node:*"),
                "intentional dev tool",
            )

    def test_leading_bare_nosecurity_returns_empty_reason(self):
        """
        Given a TOML allow rule 'Bash(ruby:*)' preceded by a bare '# NOSECURITY'
        leading comment line
        When nosecurity_reason_for is called for that rule
        Then it returns '' (tagged, but no reason given) -- not None
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            self.assertEqual(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "ruby:*"),
                "",
            )

    def test_untagged_rule_returns_none(self):
        """
        Given a TOML allow rule 'Bash(git:*)' with no comment at all
        When nosecurity_reason_for is called for that rule
        Then it returns None (not tagged)
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            self.assertIsNone(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "git:*")
            )

    def test_hash_inside_regex_pattern_is_not_an_inline_comment(self):
        """
        Given an allow rule whose regex body contains a '#'
        ('Bash([regex]^ls#notacomment)') but no trailing comment
        When nosecurity_reason_for is called for that rule
        Then it returns None (the '#' inside the quoted pattern is not a comment)
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            self.assertIsNone(
                nosecurity_reason_for(
                    self._prov(path), "allow", "Bash", "[regex]^ls#notacomment"
                )
            )

    def test_native_json_layer_has_no_comments(self):
        """
        Given a layer whose provenance file_format is 'json' (native settings)
        When nosecurity_reason_for is called
        Then it returns None without reading any file (JSON carries no comments)
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.local.json"
            path.write_text("{}", encoding="utf-8")
            self.assertIsNone(
                nosecurity_reason_for(
                    self._prov(path, file_format="json"), "allow", "Bash", "node:*"
                )
            )

    def test_missing_file_degrades_to_no_reason(self):
        """
        Given a TOML provenance whose file does not exist on disk
        When nosecurity_reason_for is called
        Then it returns None (safe degradation: the finding is shown normally,
        not hidden)
        """
        prov = self._prov(Path("/no/such/dir/toolguard_hook.toml"))
        self.assertIsNone(nosecurity_reason_for(prov, "allow", "Bash", "node:*"))

    def test_rule_comments_for_tool_lists_only_commented_rules(self):
        """
        Given the TOML fixture with two commented Bash rules (node, ruby) and one
        uncommented (git)
        When rule_comments_for_tool is called for 'Bash'
        Then it returns exactly the commented rules, each a RuleComment carrying
        the recovered #NOSECURITY reason
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            comments = rule_comments_for_tool(self._prov(path), "Bash")
            by_pattern = {c.pattern: c for c in comments}
            self.assertIn("node:*", by_pattern)
            self.assertIn("ruby:*", by_pattern)
            self.assertNotIn("git:*", by_pattern)
            self.assertEqual(
                by_pattern["node:*"].nosecurity_reason(), "intentional dev tool"
            )
            self.assertEqual(by_pattern["ruby:*"].nosecurity_reason(), "")

    def test_rule_comment_nosecurity_reason_variants(self):
        """
        Given RuleComment instances with an inline reason, a bare inline tag, and
        no tag
        When nosecurity_reason is called on each
        Then it returns the reason, '', and None respectively (inline preferred)
        """
        with_reason = RuleComment("allow", "node:*", "", "# NOSECURITY: because dev")
        bare = RuleComment("allow", "ruby:*", "# NOSECURITY", "")
        untagged = RuleComment("allow", "git:*", "# just a note", "# trailing note")
        self.assertEqual(with_reason.nosecurity_reason(), "because dev")
        self.assertEqual(bare.nosecurity_reason(), "")
        self.assertIsNone(untagged.nosecurity_reason())


class TestRuleCommentExposureStructuredEntries(unittest.TestCase):
    """
    Comment/NOSECURITY recovery for a structured (``{ match = ..., ... }``) entry.

    A structured entry is valid TOML only on a single physical line (TOML 1.0
    forbids an inline table from spanning multiple physical lines -- see
    ``toolguard.rule_sort``'s top-of-file docstring); a ``#`` inside one of its
    quoted metadata values must never be mistaken for a comment. This class
    previously also covered a MULTI-line variant of each scenario; TOO-19's
    corrective change made that variant a parse FAILURE (not a supported
    shape), so those cases were converted to instead assert the safe
    degrade-on-parse-failure behaviour ``_layer_comment_map`` now has (see
    ``test_multiline_structured_entry_degrades_to_no_comments_recovered``
    below) rather than testing content-recovery details that no longer apply.
    """

    _SINGLE_LINE_NOSECURITY = (
        "[permissions]\n"
        "allow = [\n"
        '    { match = "Bash(git status)", additionalContext = "read-only" },'
        "  # NOSECURITY: reviewed\n"
        "]\n"
        "deny = []\n"
        "ask = []\n"
    )

    _MULTILINE_NOSECURITY = (
        "[permissions]\n"
        "allow = [\n"
        '    { match = "Bash(git status)",\n'
        '      additionalContext = "read-only" },'
        "  # NOSECURITY: reviewed multiline\n"
        "]\n"
        "deny = []\n"
        "ask = []\n"
    )

    _SINGLE_LINE_HASH_IN_VALUE = (
        "[permissions]\n"
        "allow = [\n"
        '    { match = "Bash(git status)", additionalContext = "see issue #42" },\n'
        "]\n"
        "deny = []\n"
        "ask = []\n"
    )

    _SINGLE_LINE_LEADING_AND_INLINE = (
        "[permissions]\n"
        "allow = [\n"
        "    # reviewed during the TOO-19 audit\n"
        '    { match = "Bash(git status)", additionalContext = "read-only" },'
        "  # keep for CI\n"
        "]\n"
        "deny = []\n"
        "ask = []\n"
    )

    def _prov(self, path: Path) -> Provenance:
        """Build a toolguard_hook Provenance pointing at a real TOML file path."""
        return Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=path,
            specificity=0,
        )

    def test_nosecurity_on_single_line_structured_entry_recovered(self):
        """
        Given an allow rule written as a single-line structured entry
        ('{ match = "Bash(git status)", additionalContext = "read-only" }') with a
        trailing '# NOSECURITY: reviewed' comment
        When nosecurity_reason_for is called for that rule's pattern
        Then it returns the reason 'reviewed'
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._SINGLE_LINE_NOSECURITY, encoding="utf-8")
            self.assertEqual(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "git status"),
                "reviewed",
            )

    def test_multiline_structured_entry_degrades_to_no_comments_recovered(self):
        """
        Given a structured entry written across two physical lines with a
        '# NOSECURITY: reviewed multiline' comment on its own last line -- not
        valid TOML 1.0 (an inline table must be single-line; see
        toolguard.rule_sort's top-of-file docstring), so the raw file fails to
        parse
        When nosecurity_reason_for is called for that rule's pattern
        Then it returns None -- a parse failure degrades to "no comment
        recovered" (the same safe direction as an unreadable file), rather
        than raising and crashing whatever's iterating comments across a
        whole config hierarchy (TOO-19 corrective change: this was previously
        NOT a parse failure at all, because this module pre-normalized the
        multi-line entry before handing it to tomllib -- see rule_sort.py's
        module docstring for why that was wrong)
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._MULTILINE_NOSECURITY, encoding="utf-8")
            self.assertIsNone(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "git status")
            )

    def test_hash_inside_single_line_structured_value_is_not_an_inline_comment(self):
        """
        Given a single-line structured entry whose 'additionalContext' value itself
        contains a '#' ('see issue #42') and no real trailing comment
        When nosecurity_reason_for is called for that rule's pattern
        Then it returns None -- the '#' inside the quoted value is never mistaken
        for a comment start
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._SINGLE_LINE_HASH_IN_VALUE, encoding="utf-8")
            self.assertIsNone(
                nosecurity_reason_for(self._prov(path), "allow", "Bash", "git status")
            )

    def test_leading_and_inline_comments_recovered_for_single_line_structured_entry(
        self,
    ):
        """
        Given a single-line structured entry preceded by a leading human comment and
        followed by a same-line trailing comment
        When rule_comments_for_tool is called for 'Bash'
        Then the returned RuleComment carries both the leading comment and the
        inline comment, each recovered correctly
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._SINGLE_LINE_LEADING_AND_INLINE, encoding="utf-8")
            comments = rule_comments_for_tool(self._prov(path), "Bash")
            by_pattern = {c.pattern: c for c in comments}
            self.assertIn("git status", by_pattern)
            comment = by_pattern["git status"]
            self.assertIn("reviewed during the TOO-19 audit", comment.leading)
            self.assertEqual(comment.inline, "# keep for CI")
