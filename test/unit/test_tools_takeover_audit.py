"""Unit tests for toolguard.tools.takeover_audit -- takeover invariant checker."""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.tools.takeover_audit import (
    AuditSeverity,
    audit_takeover,
    effective_takeover_state,
    _get_registered_toolguard_tools,
    _has_any_blanket_allow_in_native,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    governed_tools: Optional[List[str]] = None,
    takeover_enabled: Optional[bool] = None,
    no_match_fallback: str = "deny",
    ignored_allow_patterns: Optional[List[str]] = None,
    allow: Optional[List[str]] = None,
    specificity: int = 0,
    undecidable_fallback: Optional[str] = None,
) -> ConfigLayer:
    """
    Build a toolguard_hook ConfigLayer with the given settings.

    ``undecidable_fallback``, when given, is written as a TOP-LEVEL key
    (sibling of ``takeover_mode``/``governed_tools``), matching its real
    schema: unlike ``no_match_fallback`` it has no ``[takeover_mode]``
    section and no legacy alias.
    """
    content: dict = {}

    if governed_tools is not None:
        content["governed_tools"] = governed_tools

    takeover_section: dict = {"no_match_fallback": no_match_fallback}
    if takeover_enabled is not None:
        takeover_section["enabled"] = takeover_enabled
    if ignored_allow_patterns is not None:
        takeover_section["ignored_allow_patterns"] = ignored_allow_patterns
    if takeover_section:
        content["takeover_mode"] = takeover_section

    if undecidable_fallback is not None:
        content["undecidable_fallback"] = undecidable_fallback

    if allow:
        content["permissions"] = {
            "allow": allow,
            "deny": [],
            "ask": [],
        }

    return ConfigLayer(
        provenance=_prov(specificity=specificity),
        content=MappingProxyType(content),
    )


def _native_layer(
    allow: Optional[List[str]] = None,
    hooks: Optional[dict] = None,
    specificity: int = 1,
) -> ConfigLayer:
    """Build a native Claude settings ConfigLayer."""
    content: dict = {}
    if allow:
        content["permissions"] = {"allow": allow, "deny": []}
    if hooks:
        content["hooks"] = hooks
    return ConfigLayer(
        provenance=_prov(
            level="project",
            source_type="claude",
            path="/fake/.claude/settings.local.json",
            specificity=specificity,
        ),
        content=MappingProxyType(content),
    )


def _hooks_for(*tools: str) -> dict:
    """Build a hooks dict registering toolguard as PreToolUse for the given tools."""
    pre = [
        {
            "matcher": tool,
            "hooks": [{"type": "command", "command": "~/.local/bin/toolguard"}],
        }
        for tool in tools
    ]
    return {"PreToolUse": pre}


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


# ---------------------------------------------------------------------------
# Correct setup yields no findings (required)
# ---------------------------------------------------------------------------


class TestCorrectTakeoverSetup(unittest.TestCase):
    """Tests that a correctly-configured takeover setup produces NO audit findings."""

    def test_correct_setup_no_findings(self):
        """
        Given a correctly-configured takeover setup:
        - takeover enabled=True in toolguard_hook
        - governed_tools lists Bash, Read, Write, Edit
        - native settings has blanket allows for all governed tools
        - blanket allows are all in ignored_allow_patterns
        - toolguard hook is registered in native settings for all governed tools
        - no_match_fallback is 'deny'
        When audit_takeover() is called
        Then NO findings are returned (the required 'no false alarms' check)
        """
        governed = ["Bash", "Read", "Write", "Edit"]
        ignored = ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)"]
        native_blanket_allows = ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)"]

        tg_layer = _toolguard_layer(
            governed_tools=governed,
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=ignored,
        )
        native_layer = _native_layer(
            allow=native_blanket_allows,
            hooks=_hooks_for(*governed),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        self.assertEqual(
            findings,
            [],
            msg=(
                "Expected no findings for a correct takeover setup, got: "
                + str([f.finding_id for f in findings])
            ),
        )

    def test_featherhill_style_setup_no_findings(self):
        """
        Given a setup styled after the real featherhill config:
        - toolguard governs Bash + mcp__jetbrains__execute_terminal_command + Read + Write + Edit
        - takeover is ON, all governed tools have hooks registered
        - native blanket allows are in the ignored set
        When audit_takeover() is called
        Then NO findings are returned
        """
        governed = [
            "Bash",
            "mcp__jetbrains__execute_terminal_command",
            "Read",
            "Write",
            "Edit",
        ]
        blankets = [
            "Bash(*)",
            "mcp__jetbrains__execute_terminal_command(*)",
            "Read(*)",
            "Write(*)",
            "Edit(*)",
        ]
        tg_layer = _toolguard_layer(
            governed_tools=governed,
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=blankets,
        )
        native_layer = _native_layer(
            allow=blankets,
            hooks=_hooks_for(*governed),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        self.assertEqual(findings, [])


# ---------------------------------------------------------------------------
# Hook-not-registered (CRITICAL)
# ---------------------------------------------------------------------------


class TestHookNotRegistered(unittest.TestCase):
    """Tests for the hook-not-registered CRITICAL invariant."""

    def test_missing_hook_yields_critical_finding(self):
        """
        Given a governed tool 'Bash' with NO hook registered in native settings
        When audit_takeover() is called
        Then a CRITICAL finding with finding_id='hook-not-registered' is returned for Bash
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
        )
        native_layer = _native_layer(allow=["Bash(*)"])
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        hook_findings = [f for f in findings if f.finding_id == "hook-not-registered"]
        self.assertEqual(len(hook_findings), 1)
        self.assertEqual(hook_findings[0].severity, AuditSeverity.CRITICAL)
        self.assertEqual(hook_findings[0].tool, "Bash")

    def test_partially_registered_tools_flagged(self):
        """
        Given governed tools ['Bash', 'Read'] but only Bash has a hook registered
        When audit_takeover() is called
        Then a CRITICAL finding is returned for 'Read' only
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
        )
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        hook_findings = [f for f in findings if f.finding_id == "hook-not-registered"]
        tools_flagged = {f.tool for f in hook_findings}
        self.assertIn("Read", tools_flagged)
        self.assertNotIn("Bash", tools_flagged)

    def test_partial_registration_yields_critical_finding_under_takeover(self):
        """
        Given governed tools ['Bash', 'Read'] with only Bash hooked AND takeover ON
        When audit_takeover() is called
        Then a CRITICAL 'partial-hook-registration' finding is returned naming the
        registered (Bash) and missing (Read) tools
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        partial = [f for f in findings if f.finding_id == "partial-hook-registration"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0].severity, AuditSeverity.CRITICAL)
        self.assertIn("Read", partial[0].description)
        self.assertIn("Bash", partial[0].description)

    def test_partial_registration_high_when_takeover_off(self):
        """
        Given governed tools ['Bash', 'Read'] with only Bash hooked AND takeover OFF
        When audit_takeover() is called
        Then a HIGH (not CRITICAL) 'partial-hook-registration' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=False,
        )
        native_layer = _native_layer(hooks=_hooks_for("Bash"))
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        partial = [f for f in findings if f.finding_id == "partial-hook-registration"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0].severity, AuditSeverity.HIGH)

    def test_no_partial_finding_when_all_registered(self):
        """
        Given all governed tools have toolguard hooks registered (not a mixed state)
        When audit_takeover() is called
        Then NO 'partial-hook-registration' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash", "Read"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        partial = [f for f in findings if f.finding_id == "partial-hook-registration"]
        self.assertEqual(partial, [])

    def test_all_tools_registered_no_hook_finding(self):
        """
        Given all governed tools have toolguard hooks registered
        When audit_takeover() is called
        Then no hook-not-registered finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash", "Read"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        hook_findings = [f for f in findings if f.finding_id == "hook-not-registered"]
        self.assertEqual(hook_findings, [])

    def test_wildcard_matcher_covers_all_tools(self):
        """
        Given a single toolguard hook registered with matcher '*' (all tools)
        When audit_takeover() is called for governed tools ['Bash', 'Read']
        Then NO hook-not-registered and NO partial-hook-registration findings appear
        (a wildcard matcher registers the hook for every tool -- review finding N1)
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        )
        wildcard_hooks = {
            "PreToolUse": [
                {
                    "matcher": "*",
                    "hooks": [{"type": "command", "command": "~/.local/bin/toolguard"}],
                }
            ]
        }
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=wildcard_hooks,
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        reg_findings = [
            f
            for f in findings
            if f.finding_id in ("hook-not-registered", "partial-hook-registration")
        ]
        self.assertEqual(reg_findings, [])


# ---------------------------------------------------------------------------
# Takeover-conflict-with-blanket-allows (HIGH)
# ---------------------------------------------------------------------------


class TestTakeoverConflictWithBlanketAllows(unittest.TestCase):
    """Tests for the takeover-conflict-with-blanket-allows HIGH invariant."""

    def _make_conflict_config(self) -> Configuration:
        """Build a config with a cross-level takeover conflict (project=True, user=False) plus a Bash(*) blanket allow."""
        project_tg = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            specificity=0,
        )
        user_tg = ConfigLayer(
            provenance=_prov(
                level="user",
                source_type="toolguard_hook",
                path="/home/user/.claude/toolguard_hook.toml",
                specificity=2,
            ),
            content=MappingProxyType(
                {
                    "takeover_mode": {"enabled": False},
                    "governed_tools": ["Bash"],
                }
            ),
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        return _make_config(project_tg, user_tg, native_layer)

    def test_conflict_with_blanket_allows_flagged(self):
        """
        Given a cross-level takeover enabled conflict (project=True, user=False)
        And native settings contain a Bash(*) blanket allow
        When audit_takeover() is called
        Then a HIGH 'takeover-conflict-with-blanket-allows' finding is returned
        """
        config = self._make_conflict_config()
        takeover = config.takeover_mode()
        self.assertIsNotNone(takeover.conflict)
        self.assertFalse(takeover.enabled)

        findings = audit_takeover(config)
        conflict_findings = [
            f
            for f in findings
            if f.finding_id == "takeover-conflict-with-blanket-allows"
        ]
        self.assertEqual(len(conflict_findings), 1)
        self.assertEqual(conflict_findings[0].severity, AuditSeverity.HIGH)
        self.assertIsNone(conflict_findings[0].tool)

    def test_conflict_without_blanket_allows_not_flagged(self):
        """
        Given a cross-level takeover conflict
        But native settings have NO blanket allows
        When audit_takeover() is called
        Then no 'takeover-conflict-with-blanket-allows' finding is returned
        (conflict alone is not a direct security issue if no blanket allows are present)
        """
        project_tg = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            specificity=0,
        )
        user_tg = ConfigLayer(
            provenance=_prov(
                level="user",
                source_type="toolguard_hook",
                specificity=2,
            ),
            content=MappingProxyType(
                {"takeover_mode": {"enabled": False}, "governed_tools": ["Bash"]}
            ),
        )
        native_layer = _native_layer(
            allow=["Bash(git status:*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(project_tg, user_tg, native_layer)
        findings = audit_takeover(config)
        conflict_findings = [
            f
            for f in findings
            if f.finding_id == "takeover-conflict-with-blanket-allows"
        ]
        self.assertEqual(conflict_findings, [])


# ---------------------------------------------------------------------------
# Uncovered-blanket-allow (HIGH)
# ---------------------------------------------------------------------------


class TestUncoveredBlanketAllow(unittest.TestCase):
    """Tests for the uncovered-blanket-allow HIGH invariant."""

    def test_uncovered_blanket_allow_flagged(self):
        """
        Given takeover is ON and a native layer has a non-default blanket allow
        that is NOT in ignored_allow_patterns (not covered by the defaults either)
        When audit_takeover() is called
        Then a HIGH 'uncovered-blanket-allow' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "mcp__custom__tool"],
            takeover_enabled=True,
        )
        native_layer = _native_layer(
            allow=["mcp__custom__tool(*)"],
            hooks=_hooks_for("Bash", "mcp__custom__tool"),
        )
        config = _make_config(tg_layer, native_layer)
        takeover = config.takeover_mode()
        self.assertTrue(takeover.enabled)
        self.assertNotIn("mcp__custom__tool(*)", takeover.ignored_allow_patterns)

        findings = audit_takeover(config)
        uncovered = [f for f in findings if f.finding_id == "uncovered-blanket-allow"]
        self.assertGreater(len(uncovered), 0)
        self.assertEqual(uncovered[0].severity, AuditSeverity.HIGH)

    def test_covered_blanket_allow_not_flagged(self):
        """
        Given takeover is ON and 'Bash(*)' IS in ignored_allow_patterns
        When audit_takeover() is called
        Then no 'uncovered-blanket-allow' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        uncovered = [f for f in findings if f.finding_id == "uncovered-blanket-allow"]
        self.assertEqual(uncovered, [])


# ---------------------------------------------------------------------------
# Loose-no-match-fallback (LOW)
# ---------------------------------------------------------------------------


class TestLooseNoMatchFallback(unittest.TestCase):
    """Tests for the loose-no-match-fallback LOW invariant."""

    def test_warn_deny_fallback_flagged(self):
        """
        Given no_match_fallback is 'warn_deny' instead of 'deny'
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="warn_deny",
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        fallback_findings = [
            f for f in findings if f.finding_id == "loose-no-match-fallback"
        ]
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_deny_fallback_not_flagged(self):
        """
        Given no_match_fallback is 'deny' (the expected value)
        When audit_takeover() is called
        Then no 'loose-no-match-fallback' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        fallback_findings = [
            f for f in findings if f.finding_id == "loose-no-match-fallback"
        ]
        self.assertEqual(fallback_findings, [])

    def test_allow_fallback_flagged(self):
        """
        Given no_match_fallback is 'allow' (TOO-19: allow with NO warning)
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned -- the
            blanket '!= deny' check requires no special-casing for this new
            value, it is simply another non-'deny' raw spelling
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="allow",
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        fallback_findings = [
            f for f in findings if f.finding_id == "loose-no-match-fallback"
        ]
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_allow_with_no_warnings_fallback_flagged(self):
        """
        Given no_match_fallback is 'allow_with_no_warnings' (TOO-19's
            long-form alias for 'allow')
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned, exactly as
            for 'allow' -- the raw value read off TakeoverConfig is not
            normalized, but the blanket '!= deny' check does not care which
            non-'deny' spelling was used
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="allow_with_no_warnings",
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        fallback_findings = [
            f for f in findings if f.finding_id == "loose-no-match-fallback"
        ]
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)


# ---------------------------------------------------------------------------
# Loose-undecidable-fallback (HIGH)
# ---------------------------------------------------------------------------


class TestLooseUndecidableFallback(unittest.TestCase):
    """Tests for the loose-undecidable-fallback HIGH invariant."""

    def test_allow_with_warning_flagged_high(self):
        """
        Given undecidable_fallback is 'allow_with_warning'
        When audit_takeover() is called
        Then a HIGH 'loose-undecidable-fallback' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
            undecidable_fallback="allow_with_warning",
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].severity, AuditSeverity.HIGH)
        self.assertIsNone(matches[0].tool)
        self.assertIsNone(matches[0].provenance)

    def test_ask_not_flagged(self):
        """
        Given undecidable_fallback is 'ask' (the default)
        When audit_takeover() is called
        Then no 'loose-undecidable-fallback' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
            undecidable_fallback="ask",
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(matches, [])

    def test_deny_not_flagged(self):
        """
        Given undecidable_fallback is 'deny' (strictly more conservative than default)
        When audit_takeover() is called
        Then no 'loose-undecidable-fallback' finding is returned, because a
             stricter-than-default setting is never itself a risk
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
            undecidable_fallback="deny",
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(matches, [])

    def test_unset_not_flagged(self):
        """
        Given undecidable_fallback is not set anywhere (resolves to default 'ask')
        When audit_takeover() is called
        Then no 'loose-undecidable-fallback' finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(matches, [])

    def test_flagged_regardless_of_takeover_enabled(self):
        """
        Given undecidable_fallback is 'allow_with_warning' and takeover mode is OFF
        When audit_takeover() is called
        Then the HIGH finding still fires, because undecidable_fallback applies
             in both takeover and non-takeover modes
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=False,
            no_match_fallback="deny",
            undecidable_fallback="allow_with_warning",
        )
        config = _make_config(tg_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].severity, AuditSeverity.HIGH)

    def test_allow_flagged_high(self):
        """
        Given undecidable_fallback is 'allow' (TOO-19: allow with NO warning)
        When audit_takeover() is called
        Then a HIGH 'loose-undecidable-fallback' finding is returned -- the
            SAME severity as 'allow_with_warning', never lower, since 'allow'
            is strictly LESS safe (nothing is even logged)
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
            undecidable_fallback="allow",
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].severity, AuditSeverity.HIGH)
        self.assertIn("allow", matches[0].description)
        self.assertIn("NO warning", matches[0].description)

    def test_allow_with_no_warnings_flagged_high(self):
        """
        Given undecidable_fallback is 'allow_with_no_warnings' (TOO-19's
            long-form alias)
        When audit_takeover() is called
        Then a HIGH 'loose-undecidable-fallback' finding is returned -- the
            alias is normalized to 'allow' by resolved_undecidable_fallback()
            before this check runs, so it is flagged identically to 'allow'
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=["Bash(*)"],
            undecidable_fallback="allow_with_no_warnings",
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        matches = [f for f in findings if f.finding_id == "loose-undecidable-fallback"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].severity, AuditSeverity.HIGH)


# ---------------------------------------------------------------------------
# Broken configuration (deliberately invalid) - must flag
# ---------------------------------------------------------------------------


class TestBrokenTakeoverConfig(unittest.TestCase):
    """Tests that a deliberately broken takeover config produces findings."""

    def test_takeover_off_with_blanket_allows_and_missing_hook(self):
        """
        Given takeover is NOT enabled (default OFF)
        And native settings have Bash(*) blanket allow
        And the toolguard hook is NOT registered
        When audit_takeover() is called
        Then at least one finding is returned
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash"],
            takeover_enabled=False,
        )
        native_layer = _native_layer(
            allow=["Bash(*)"],
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        self.assertGreater(len(findings), 0)
        hook_findings = [f for f in findings if f.finding_id == "hook-not-registered"]
        self.assertGreater(len(hook_findings), 0)

    def test_findings_sorted_critical_first(self):
        """
        Given a configuration with both CRITICAL and HIGH findings
        When audit_takeover() returns results
        Then findings are sorted CRITICAL first, then HIGH
        """
        tg_layer = _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=True,
            ignored_allow_patterns=[],
        )
        native_layer = _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash"),
        )
        config = _make_config(tg_layer, native_layer)
        findings = audit_takeover(config)
        if len(findings) >= 2:
            severities = [f.severity.value for f in findings]
            for i in range(len(severities) - 1):
                self.assertGreaterEqual(severities[i], severities[i + 1])


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelperFunctions(unittest.TestCase):
    """Tests for internal helpers (exposed for testing)."""

    def test_get_registered_toolguard_tools(self):
        """
        Given a native layer with toolguard hooks for Bash and Read
        When _get_registered_toolguard_tools() is called
        Then {Bash, Read} is returned
        """
        native_layer = _native_layer(hooks=_hooks_for("Bash", "Read"))
        config = _make_config(native_layer)
        registered = _get_registered_toolguard_tools(config)
        self.assertEqual(registered, {"Bash", "Read"})

    def test_non_toolguard_hook_not_counted(self):
        """
        Given a native layer with a non-toolguard hook for Bash
        When _get_registered_toolguard_tools() is called
        Then Bash is NOT in the returned set
        """
        hooks = {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {"type": "command", "command": "/usr/bin/something-else"}
                    ],
                }
            ]
        }
        native_layer = _native_layer(hooks=hooks)
        config = _make_config(native_layer)
        registered = _get_registered_toolguard_tools(config)
        self.assertNotIn("Bash", registered)

    def test_has_any_blanket_allow_in_native_true(self):
        """
        Given a native layer with Bash(*) allow
        When _has_any_blanket_allow_in_native() is called
        Then True is returned
        """
        native_layer = _native_layer(allow=["Bash(*)"])
        config = _make_config(native_layer)
        self.assertTrue(_has_any_blanket_allow_in_native(config))

    def test_has_any_blanket_allow_in_native_false(self):
        """
        Given a native layer with only specific allows (no blanket)
        When _has_any_blanket_allow_in_native() is called
        Then False is returned
        """
        native_layer = _native_layer(allow=["Bash(git status:*)"])
        config = _make_config(native_layer)
        self.assertFalse(_has_any_blanket_allow_in_native(config))

    def test_effective_takeover_state_wrapper(self):
        """
        Given a configuration with takeover enabled=True
        When effective_takeover_state() is called
        Then a TakeoverConfig with enabled=True is returned
        """
        tg_layer = _toolguard_layer(takeover_enabled=True)
        config = _make_config(tg_layer)
        state = effective_takeover_state(config)
        self.assertTrue(state.enabled)
