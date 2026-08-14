"""Unit tests for toolguard.tools.config_access, the thin facade over Configuration."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import Optional as _Optional
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
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


class TestLoadConfig(ConfigIsolationMixin, unittest.TestCase):
    """Tests for config_access.load_config()."""

    def test_load_config_returns_configuration(self):
        """
        Given an isolated hierarchy whose only config file is the project's
            toolguard_hook.toml
        When load_config is called with the project directory
        Then the returned Configuration's layers are exactly that one file --
            not merely non-empty, which the developer's own ~/.claude satisfies
            on its own
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(ls:*)"]',
        )
        config = load_config(proj)
        self.assertEqual(
            [lr.provenance.path for lr in config.layers],
            [proj / ".claude" / "toolguard_hook.toml"],
        )

    def test_load_config_ignores_env_override(self):
        """
        Given CLAUDE_SETTINGS_PATH set to an unrelated file
        When load_config is called (which uses ignore_env_override=True)
        Then the project hierarchy is used, not the env override
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(git:*)"]',
        )
        with patch.dict(
            os.environ,
            {"CLAUDE_SETTINGS_PATH": "/nonexistent/settings.json"},
        ):
            config = load_config(proj)
        allow, _ = config.allow_deny_for("Bash")
        self.assertIn("git:*", allow)


class TestPerLayerRules(ConfigIsolationMixin, unittest.TestCase):
    """Tests for config_access.per_layer_rules()."""

    def test_per_layer_rules_returns_allow_deny_ask(self):
        """
        Given a config with allow, deny and ask rules for Bash
        When per_layer_rules is called with tool_name='Bash'
        Then the returned LayerRules carries the correct allow, deny, and ask patterns
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            """
[permissions]
allow = ["Bash(git:*)"]
deny = ["Bash(rm -rf:*)"]
ask = ["Bash(sudo:*)"]
""",
        )
        config = load_config(proj)
        layers = per_layer_rules(config, "Bash")

        self.assertGreater(len(layers), 0)
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

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            """
[permissions]
allow = []
deny = []
ask = [{ match = "Bash(sudo:*)", additionalContext = "needs review" }]
""",
        )
        config = load_config(proj)
        layers = per_layer_rules(config, "Bash")

        project_layer = layers[0]
        self.assertIn("sudo:*", project_layer.ask)

    def test_per_layer_rules_surfaces_a_native_ask_rule(self):
        """
        Given a native Claude settings.json holding an ask rule for Bash, which
            Configuration.permission_layers extracts and the resolver decides on
        When per_layer_rules is called
        Then the native layer's ask tuple carries that rule -- a live rule the
            tooling view must not hide (proposed ticket CA1: the
            `not layer.is_native` guard drops it, so the security audit and the
            maintenance skill cannot see or reconcile it)
        """

        _home, proj = self.isolate_config_environment()
        claude = proj / ".claude"
        claude.mkdir(parents=True, exist_ok=True)
        (claude / "settings.json").write_text(
            json.dumps(
                {
                    "permissions": {
                        "allow": ["Bash(ls:*)"],
                        "ask": ["Bash(git push:*)"],
                    }
                }
            ),
            encoding="utf-8",
        )
        config = load_config(proj)
        layers = per_layer_rules(config, "Bash")

        native_layers = [lr for lr in layers if lr.provenance.source_type == "claude"]
        self.assertEqual(
            len(native_layers), 1, "fixture must produce exactly one native layer"
        )
        self.assertEqual(
            ("git push:*",),
            tuple(tl.ask for tl in config.permission_layers("Bash") if tl.ask)[0],
            "precondition: Configuration itself extracts the native ask rule",
        )
        self.assertIn("git push:*", native_layers[0].ask)

    def test_per_layer_rules_multiple_levels_most_specific_first(self):
        """
        Given project-level and user-level configs with different allow patterns
        When per_layer_rules is called
        Then the project layer comes first and the user layer last
        """

        home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(git:*)"]',
        )
        _write_toml(
            home / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(ls:*)"]',
        )
        config = load_config(proj)
        layers = per_layer_rules(config, "Bash")

        self.assertGreater(len(layers), 1)
        self.assertIn("git:*", layers[0].allow)
        self.assertIn("ls:*", layers[-1].allow)

    def test_every_discovered_layer_gets_a_layer_rules_entry(self):
        """
        Given a two-layer config in which only the user layer names the tool
        When per_layer_rules is called for that tool
        Then one LayerRules is returned per discovered layer, in layer order --
            the project layer present with empty tuples rather than omitted, so
            a caller can tell "this layer contributes nothing" from "this layer
            was not examined"
        """

        home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Read(*.py)"]',
        )
        _write_toml(
            home / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(ls:*)"]',
        )
        config = load_config(proj)
        layers = per_layer_rules(config, "Bash")

        self.assertEqual(
            [lr.provenance for lr in layers], [lyr.provenance for lyr in config.layers]
        )
        self.assertEqual(((), (), ()), (layers[0].allow, layers[0].deny, layers[0].ask))
        self.assertIn("ls:*", layers[-1].allow)


class TestPerLayerRulesEqualProvenance(unittest.TestCase):
    """per_layer_rules' layer lookup when two layers carry an EQUAL Provenance."""

    def test_each_layer_keeps_its_own_rules_under_an_equal_provenance(self):
        """
        Given two ConfigLayers whose Provenance objects are equal (a frozen
            dataclass, so equal field values are one dict key) and which hold
            different Bash allow rules
        When per_layer_rules is called
        Then each returned LayerRules carries its OWN layer's rules -- the
            defect (proposed ticket CL3) keys the lookup by Provenance, so the
            second layer overwrites the first and its rules are then reported
            for BOTH layers: the first layer's rules vanish and the second's are
            counted twice, which is how one dangerous rule became two CRITICAL
            findings in the security audit's own fixture (ticket 56)
        """

        shared = _prov()
        config = _make_config(
            _layer_with(shared, allow=["Bash(first:*)"]),
            _layer_with(shared, allow=["Bash(second:*)"]),
        )
        self.assertEqual(
            [("first:*",), ("second:*",)],
            [tl.allow for tl in config.permission_layers("Bash")],
            "precondition: Configuration itself keeps the two layers apart",
        )

        layers = per_layer_rules(config, "Bash")

        self.assertEqual([("first:*",), ("second:*",)], [lr.allow for lr in layers])


class TestEffectiveTakeover(ConfigIsolationMixin, unittest.TestCase):
    """Tests for config_access.effective_takeover()."""

    def test_effective_takeover_enabled(self):
        """
        Given a config with takeover_mode.enabled = true
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=True
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            "[takeover_mode]\nenabled = true\n",
        )
        config = load_config(proj)
        self.assertTrue(effective_takeover(config).enabled)

    def test_effective_takeover_disabled_by_default(self):
        """
        Given a config with no takeover_mode section
        When effective_takeover is called
        Then the returned TakeoverConfig has enabled=False (default off)
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(ls:*)"]',
        )
        config = load_config(proj)
        self.assertFalse(effective_takeover(config).enabled)


class TestConfigSummary(ConfigIsolationMixin, unittest.TestCase):
    """Tests for config_access.config_summary()."""

    def test_config_summary_reports_sources_and_tools(self):
        """
        Given a project config that governs Bash and Read
        When config_summary is called
        Then the summary reports the correct governed tools and non-zero source count
        """

        _home, proj = self.isolate_config_environment()
        _write_toml(
            proj / ".claude",
            "toolguard_hook.toml",
            'governed_tools = ["Bash", "Read"]\n[permissions]\nallow = ["Bash(ls:*)"]',
        )
        config = load_config(proj)
        summary = config_summary(config)

        self.assertIn("Bash", summary.governed_tools)
        self.assertIn("Read", summary.governed_tools)
        self.assertGreater(summary.layer_count, 0)
        self.assertGreater(len(summary.sources), 0)

    def test_summary_of_an_empty_hierarchy_still_names_the_default_tools(self):
        """
        Given a Configuration with no layers at all
        When config_summary is called
        Then it reports zero layers and no sources, while governed_tools still
            names the four built-in defaults -- so the tool list in a summary is
            not evidence that any config was read (proposed ticket 29's family:
            a report whose "examined nothing" case looks like its normal one)
        """

        summary = config_summary(_make_config())

        self.assertEqual(0, summary.layer_count)
        self.assertEqual((), summary.sources)
        self.assertEqual(("Bash", "Read", "Write", "Edit"), summary.governed_tools)


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
    file_format: str = "toml",
) -> Provenance:
    """Build a Provenance for test use."""
    return Provenance(
        level=level,
        source_type=source_type,
        file_format=file_format,
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
    path: str = "/fake/.claude/toolguard_hook.toml",
) -> ConfigLayer:
    """
    Build a toolguard_hook ConfigLayer.

    Pass a distinct ``path`` for every layer in a multi-layer fixture:
    ``Provenance`` is a frozen dataclass, so two layers built from the same
    arguments compare equal and collapse into one key in per_layer_rules.
    """
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
        provenance=_prov(specificity=specificity, path=path),
        content=MappingProxyType(content),
    )


def _layer_with(
    provenance: Provenance,
    allow: _Optional[list] = None,
    deny: _Optional[list] = None,
    ask: _Optional[list] = None,
) -> ConfigLayer:
    """Build a ConfigLayer with a caller-supplied Provenance."""
    perms: dict = {}
    for name, value in (("allow", allow), ("deny", deny), ("ask", ask)):
        if value is not None:
            perms[name] = value
    return ConfigLayer(
        provenance=provenance,
        content=MappingProxyType({"permissions": perms} if perms else {}),
    )


def _native_layer(
    allow: _Optional[list] = None,
    specificity: int = 1,
    path: str = "/fake/.claude/settings.local.json",
) -> ConfigLayer:
    """Build a native Claude settings ConfigLayer."""
    content: dict = {}
    if allow is not None:
        content["permissions"] = {"allow": allow, "deny": []}
    return ConfigLayer(
        provenance=_prov(
            level="project",
            source_type="claude",
            path=path,
            specificity=specificity,
            file_format="json",
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

        layer1 = _toolguard_layer(
            allow=["Bash(ls:*)", "Read(*.py)"], path="/fake/a.toml"
        )
        layer2 = _toolguard_layer(allow=["Bash(git:*)"], path="/fake/b.toml")
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

        layer = _toolguard_layer()
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

    def test_unclosed_tool_wrapper_names_no_tool(self):
        """
        Given an allow rule whose tool wrapper is unclosed ('Bash(ls:*') --
            accepted verbatim by normalize_entry, which does not validate the
            wrapper -- alongside a well-formed Read rule
        When discover_tools is called
        Then only 'Read' is returned: without the closing-paren check the
            malformed rule would name a tool for a pattern body that was never
            written ('ls:' -- the slice drops the last character)
        """

        layer = _toolguard_layer(allow=["Bash(ls:*", "Read(*.py)"])
        tools = discover_tools(_make_config(layer))
        self.assertEqual(("Read",), tools)

    def test_non_dict_permissions_section_yields_no_tools(self):
        """
        Given a layer whose [permissions] value is a list rather than a table
        When discover_tools is called
        Then it returns an empty tuple instead of raising -- one mistyped
            section must not abort a whole tooling run
        """

        layer = ConfigLayer(
            provenance=_prov(),
            content=MappingProxyType({"permissions": ["Bash(ls:*)"]}),
        )
        self.assertEqual((), discover_tools(_make_config(layer)))


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

    def _takeover_off(self, ignored: list) -> TakeoverConfig:
        """
        Build a disabled TakeoverConfig that still CARRIES ignored patterns.

        An empty ignored tuple would make ``enabled`` unobservable: the pattern
        would fail the membership test either way.
        """
        return TakeoverConfig(
            enabled=False,
            ignored_allow_patterns=tuple(ignored),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )

    def test_true_when_all_conditions_met(self):
        """
        Given takeover enabled, pattern is native, and pattern is in ignored set
        When neutralized_by_takeover is called
        Then True is returned
        """

        takeover = self._takeover_on(["Bash(*)"])
        result = neutralized_by_takeover("*", is_native=True, takeover=takeover)
        self.assertTrue(result)

    def test_false_when_takeover_disabled(self):
        """
        Given takeover disabled (enabled=False) and a native pattern that IS in
            the config's ignored set, so only the enabled flag separates this
            from the neutralized case
        When neutralized_by_takeover is called
        Then False is returned (takeover is OFF)
        """

        takeover = self._takeover_off(["Bash(*)"])
        self.assertIn(
            "*",
            takeover.normalized_ignored_patterns(),
            "fixture must carry the pattern, or `enabled` is unobservable",
        )
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

        takeover = self._takeover_on(["Bash(*)"])
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
        Given two native layers under takeover whose ignored allow rules yield
            three DISTINCT pattern bodies, one of them written in both layers
            and one sorting before the others
        When audit_context is called
        Then neutralized_allow_patterns is exactly the sorted, de-duplicated
            tuple of bodies -- 'Bash(*)' and 'Read(*)' collapsing to a single
            '*' is documented behaviour and cannot on its own show either
            property
        """

        ignored = [
            "Bash(*)",
            "Read(*)",
            "Write(/tmp/**)",
            "Bash(cd:*)",
            "Bash(zzz:*)",
            "Bash(aaa:*)",
        ]
        tg_layer = _toolguard_layer(
            allow=["Bash(ls:*)"],
            takeover_enabled=True,
            ignored_allow_patterns=ignored,
        )
        native_a = _native_layer(
            allow=["Bash(*)", "Write(/tmp/**)", "Bash(zzz:*)"], path="/fake/a.json"
        )
        native_b = _native_layer(
            allow=["Read(*)", "Bash(cd:*)", "Bash(aaa:*)"],
            path="/fake/b.json",
            specificity=2,
        )
        config = _make_config(tg_layer, native_a, native_b)
        ctx = audit_context(config)
        self.assertEqual(
            ("*", "/tmp/**", "aaa:*", "cd:*", "zzz:*"), ctx.neutralized_allow_patterns
        )

    def test_only_native_allow_patterns_are_reported_neutralized(self):
        """
        Given takeover mode whose ignored set names both a native allow body and
            a body written ONLY in the toolguard_hook layer
        When audit_context is called
        Then only the native body is reported: takeover strips native layers,
            and a toolguard rule is never silently dropped, so reporting it as
            neutralized would tell the user a live rule is dead
        """

        tg_layer = _toolguard_layer(
            allow=["Bash(hook-only:*)"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Bash(hook-only:*)"],
        )
        native = _native_layer(allow=["Bash(*)"])
        ctx = audit_context(_make_config(tg_layer, native))
        self.assertEqual(("*",), ctx.neutralized_allow_patterns)

    def test_layer_context_carries_the_layer_s_rule_comments(self):
        """
        Given a layer whose provenance points at a real TOML file carrying a
            '# NOSECURITY: audited' comment on its Bash allow rule
        When audit_context is called
        Then the Bash LayerContext for that layer carries the RuleComment, with
            the reason recovered -- the audit's whole acknowledge-not-hide path
            runs through this field
        """

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(
                "[permissions]\nallow = [\n    'Bash(node:*)',  # NOSECURITY: audited\n]\n",
                encoding="utf-8",
            )
            layer = _layer_with(_prov(path=str(path)), allow=["Bash(node:*)"])
            ctx = audit_context(_make_config(layer))

            bash_tool = next(tc for tc in ctx.tools if tc.tool == "Bash")
            comments = bash_tool.layers[0].comments
            self.assertEqual(
                ["node:*"], [c.pattern for c in comments], "expected one RuleComment"
            )
            self.assertEqual("audited", comments[0].nosecurity_reason())


class TestTakeoverFilteredView(unittest.TestCase):
    """The filtered per-layer view vs. the raw layer content, under takeover mode."""

    def test_a_neutralized_native_allow_leaves_the_hook_copy_as_the_only_live_one(self):
        """
        Given takeover mode ignoring 'Bash(*)', a native layer allowing 'Bash(*)'
            and a toolguard_hook layer allowing both 'Bash(*)' and 'Bash(ls:*)'
        When per_layer_rules is called
        Then the native layer's allow tuple is empty while the hook layer keeps
            '*', even though the native file's raw content still holds it --
            the live blanket allow belongs to the hook layer alone. Proposed
            ticket 22 (RD2) is what happens when a consumer re-finds the owning
            layer by searching raw content instead: it strips the dead native
            copy and reports the finding against the hook layer.
        """

        native = _native_layer(allow=["Bash(*)"])
        hook = _toolguard_layer(
            allow=["Bash(*)", "Bash(ls:*)"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)"],
        )
        config = _make_config(hook, native)

        by_source = {
            lr.provenance.source_type: lr for lr in per_layer_rules(config, "Bash")
        }
        self.assertEqual((), by_source["claude"].allow)
        self.assertEqual(("*", "ls:*"), by_source["toolguard_hook"].allow)
        self.assertEqual(["Bash(*)"], list(native.content["permissions"]["allow"]))
        self.assertEqual(("*",), audit_context(config).neutralized_allow_patterns)


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
        "    'Read(/etc/**)',  # NOSECURITY: another tool entirely\n"
        "    'Bash(cat:*',  # NOSECURITY: unclosed wrapper\n"
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
        When the layer's comments are recovered
        Then no comment is recorded for that rule at all: the '#' inside the
        quoted pattern is not a comment start, so the rule is as uncommented as
        'Bash(git:*)' beside it
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            patterns = {
                c.pattern for c in rule_comments_for_tool(self._prov(path), "Bash")
            }
            self.assertNotIn("[regex]^ls#notacomment", patterns)
            self.assertIsNone(
                nosecurity_reason_for(
                    self._prov(path), "allow", "Bash", "[regex]^ls#notacomment"
                )
            )

    def test_unclosed_tool_wrapper_is_not_split_into_a_tool(self):
        """
        Given a commented allow rule whose tool wrapper is unclosed
        ("Bash(cat:*")
        When the layer's comments are recovered
        Then the comment is keyed under the whole unsplit pattern with an empty
        tool -- splitting on the '(' alone would file it under 'Bash' with the
        body 'cat:', a pattern nobody wrote
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            self.assertNotIn(
                "cat:",
                {c.pattern for c in rule_comments_for_tool(self._prov(path), "Bash")},
            )
            self.assertEqual(
                "unclosed wrapper",
                nosecurity_reason_for(self._prov(path), "allow", "", "Bash(cat:*"),
            )

    def test_comments_are_recovered_only_for_the_requested_tool(self):
        """
        Given a TOML layer with commented rules for both Bash and Read
        When rule_comments_for_tool is called for 'Bash'
        Then the Read rule's comment is absent from the result
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._TOML, encoding="utf-8")
            bash = {c.pattern for c in rule_comments_for_tool(self._prov(path), "Bash")}
            read = {c.pattern for c in rule_comments_for_tool(self._prov(path), "Read")}
            self.assertNotIn("/etc/**", bash)
            self.assertEqual({"/etc/**"}, read)

    def test_a_json_layer_is_not_comment_parsed_even_when_its_bytes_are_toml(self):
        """
        Given a layer declared file_format='json' whose file nevertheless holds
        a TOML [permissions] section with a '# NOSECURITY: bait' comment
        When nosecurity_reason_for is called for that rule
        Then it returns None: the declared format decides, so a native settings
        file is never comment-parsed on the strength of its content
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "settings.local.json"
            path.write_text(
                "[permissions]\nallow = [\n    'Bash(node:*)',  # NOSECURITY: bait\n]\n",
                encoding="utf-8",
            )
            self.assertIsNone(
                nosecurity_reason_for(
                    self._prov(path, file_format="json"), "allow", "Bash", "node:*"
                )
            )
            self.assertEqual(
                (), rule_comments_for_tool(self._prov(path, file_format="json"), "Bash")
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
        Given RuleComment instances with an inline reason, a bare inline tag, no
        tag, and one tagged in BOTH the leading block and the inline comment
        When nosecurity_reason is called on each
        Then it returns the reason, '', and None respectively, and for the last
        the INLINE reason -- the more specific of the two
        """
        with_reason = RuleComment("allow", "node:*", "", "# NOSECURITY: because dev")
        bare = RuleComment("allow", "ruby:*", "# NOSECURITY", "")
        untagged = RuleComment("allow", "git:*", "# just a note", "# trailing note")
        both = RuleComment(
            "allow",
            "gh:*",
            "# NOSECURITY: from the block",
            "# NOSECURITY: from the line",
        )
        self.assertEqual(with_reason.nosecurity_reason(), "because dev")
        self.assertEqual(bare.nosecurity_reason(), "")
        self.assertIsNone(untagged.nosecurity_reason())
        self.assertEqual(both.nosecurity_reason(), "from the line")


class TestRuleCommentExposureStructuredEntries(unittest.TestCase):
    """Comment/NOSECURITY recovery for a structured (``{ match = ..., ... }``) entry, valid TOML only on a single physical line."""

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
        When the layer's comments are recovered
        Then no comment is recorded for the entry at all, and its
        nosecurity_reason_for is None -- the '#' inside the quoted value is
        never mistaken for a comment start
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._SINGLE_LINE_HASH_IN_VALUE, encoding="utf-8")
            self.assertEqual((), rule_comments_for_tool(self._prov(path), "Bash"))
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
