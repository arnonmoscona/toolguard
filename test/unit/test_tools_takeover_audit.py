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
    path: Optional[str] = None,
    specificity: int = 0,
) -> Provenance:
    """
    Build a Provenance for test use.

    ``path`` defaults to one derived from ``level``, ``source_type`` and
    ``specificity``, so two fixture layers are never accidentally EQUAL --
    Provenance is a frozen dataclass used as a dict key downstream, and equal
    provenances silently collapse two layers into one.
    """
    if path is None:
        leaf = (
            "settings.local.json" if source_type == "claude" else "toolguard_hook.toml"
        )
        path = f"/fake/{level}-{source_type}-{specificity}/.claude/{leaf}"
    return Provenance(
        level=level,
        source_type=source_type,
        file_format="json" if source_type == "claude" else "toml",
        path=Path(path),
        specificity=specificity,
    )


def _toolguard_layer(
    governed_tools: Optional[List[str]] = None,
    takeover_enabled: Optional[bool] = None,
    no_match_fallback: Optional[str] = None,
    ignored_allow_patterns: Optional[List[str]] = None,
    additional_ignored_patterns: Optional[List[str]] = None,
    allow: Optional[List[str]] = None,
    undecidable_fallback: Optional[str] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """
    Build a toolguard_hook ConfigLayer with the given settings.

    Every argument defaults to "key absent", so a fixture states exactly what it
    varies and inherits production's own defaults for everything else. In
    particular ``no_match_fallback`` unset resolves to ``'ask'``, not ``'deny'``.

    ``undecidable_fallback``, when given, is written as a TOP-LEVEL key
    (sibling of ``takeover_mode``/``governed_tools``), matching its real
    schema: unlike ``no_match_fallback`` it has no ``[takeover_mode]``
    section and no legacy alias.
    """
    content: dict = {}

    if governed_tools is not None:
        content["governed_tools"] = governed_tools

    takeover_section: dict = {}
    if no_match_fallback is not None:
        takeover_section["no_match_fallback"] = no_match_fallback
    if takeover_enabled is not None:
        takeover_section["enabled"] = takeover_enabled
    if ignored_allow_patterns is not None:
        takeover_section["ignored_allow_patterns"] = ignored_allow_patterns
    if additional_ignored_patterns is not None:
        takeover_section["additional_ignored_patterns"] = additional_ignored_patterns
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
        provenance=provenance if provenance is not None else _prov(),
        content=MappingProxyType(content),
    )


def _native_layer(
    allow: Optional[List[str]] = None,
    hooks: Optional[dict] = None,
    specificity: int = 1,
    level: str = "project",
) -> ConfigLayer:
    """Build a native Claude settings ConfigLayer."""
    content: dict = {}
    if allow:
        content["permissions"] = {"allow": allow, "deny": []}
    if hooks:
        content["hooks"] = hooks
    return ConfigLayer(
        provenance=_prov(
            level=level,
            source_type="claude",
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


def _ids(findings) -> List[str]:
    """Return the finding_ids of a findings list, in order."""
    return [f.finding_id for f in findings]


# ---------------------------------------------------------------------------
# Correct setup yields no findings (required)
# ---------------------------------------------------------------------------


_CORRECT_GOVERNED = ["Bash", "Read", "Write", "Edit"]
_CORRECT_BLANKETS = ["Bash(*)", "Read(*)", "Write(*)", "Edit(*)"]


def _correct_setup(hooked: Optional[List[str]] = None) -> Configuration:
    """
    Build the canonical correct takeover setup: takeover on, every governed tool
    blanket-allowed natively, every blanket allow ignored, fallback 'deny'.

    ``hooked`` restricts which governed tools carry a toolguard hook; the
    default hooks all of them.
    """
    return _make_config(
        _toolguard_layer(
            governed_tools=_CORRECT_GOVERNED,
            takeover_enabled=True,
            no_match_fallback="deny",
            ignored_allow_patterns=_CORRECT_BLANKETS,
        ),
        _native_layer(
            allow=_CORRECT_BLANKETS,
            hooks=_hooks_for(*(hooked if hooked is not None else _CORRECT_GOVERNED)),
        ),
    )


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
        findings = audit_takeover(_correct_setup())
        self.assertEqual(
            findings,
            [],
            msg=(
                "Expected no findings for a correct takeover setup, got: "
                + str(_ids(findings))
            ),
        )

    def test_clean_report_is_not_a_report_that_examined_nothing(self):
        """
        Given the SAME correct setup, perturbed one governed tool at a time by
             removing only that tool's toolguard hook
        When audit_takeover() is called on each perturbation
        Then each one yields a CRITICAL 'hook-not-registered' naming exactly the
             perturbed tool -- so the empty result of the unperturbed run means
             every governed tool WAS examined, rather than that the audit
             examined nothing at all
        """
        for dropped in _CORRECT_GOVERNED:
            with self.subTest(dropped=dropped):
                remaining = [t for t in _CORRECT_GOVERNED if t != dropped]
                findings = audit_takeover(_correct_setup(hooked=remaining))
                missing = [f for f in findings if f.finding_id == "hook-not-registered"]
                self.assertEqual([f.tool for f in missing], [dropped])
                self.assertEqual(missing[0].severity, AuditSeverity.CRITICAL)

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


def _partially_hooked_config(takeover_enabled: bool) -> Configuration:
    """
    Build a config governing Bash and Read with a toolguard hook for Bash only.

    ``takeover_enabled`` is the ONLY thing that varies between calls; every
    other setting is identical, so any difference in the audit output is
    attributable to the switch alone.
    """
    return _make_config(
        _toolguard_layer(
            governed_tools=["Bash", "Read"],
            takeover_enabled=takeover_enabled,
            ignored_allow_patterns=["Bash(*)", "Read(*)"],
        ),
        _native_layer(
            allow=["Bash(*)", "Read(*)"],
            hooks=_hooks_for("Bash"),
        ),
    )


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
        findings = audit_takeover(_partially_hooked_config(takeover_enabled=True))
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
        findings = audit_takeover(_partially_hooked_config(takeover_enabled=True))
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
        findings = audit_takeover(_partially_hooked_config(takeover_enabled=False))
        partial = [f for f in findings if f.finding_id == "partial-hook-registration"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0].severity, AuditSeverity.HIGH)

    def test_takeover_switch_alone_changes_severity_and_impact(self):
        """
        Given ONE config shape audited twice, differing only in takeover_mode.enabled
        When audit_takeover() is called on each
        Then the two reports name the same findings, but the switch alone raises
             both registration findings from HIGH/OFF-wording to CRITICAL/ON-wording
             -- so the audit output is demonstrably sensitive to the switch itself
        """
        on = audit_takeover(_partially_hooked_config(takeover_enabled=True))
        off = audit_takeover(_partially_hooked_config(takeover_enabled=False))
        self.assertEqual(sorted(_ids(on)), sorted(_ids(off)))

        by_id_on = {f.finding_id: f for f in on}
        by_id_off = {f.finding_id: f for f in off}

        self.assertEqual(
            by_id_on["partial-hook-registration"].severity, AuditSeverity.CRITICAL
        )
        self.assertEqual(
            by_id_off["partial-hook-registration"].severity, AuditSeverity.HIGH
        )
        for finding_id in ("hook-not-registered", "partial-hook-registration"):
            self.assertIn("Takeover mode is ON", by_id_on[finding_id].impact)
            self.assertNotIn("Takeover mode is ON", by_id_off[finding_id].impact)

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

    def _conflicting_toolguard_layers(self):
        """Return a (project=True, user=False) pair of toolguard layers."""
        return (
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=True,
            ),
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=False,
                provenance=_prov(level="user", specificity=2),
            ),
        )

    def test_conflict_with_blanket_allows_flagged(self):
        """
        Given a cross-level takeover enabled conflict (project=True, user=False)
        And native settings contain a Bash(*) blanket allow
        When audit_takeover() is called
        Then a HIGH 'takeover-conflict-with-blanket-allows' finding is returned
        """
        project_tg, user_tg = self._conflicting_toolguard_layers()
        config = _make_config(
            project_tg,
            user_tg,
            _native_layer(allow=["Bash(*)"], hooks=_hooks_for("Bash")),
        )
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
        project_tg, user_tg = self._conflicting_toolguard_layers()
        config = _make_config(
            project_tg,
            user_tg,
            _native_layer(allow=["Bash(git status:*)"], hooks=_hooks_for("Bash")),
        )
        findings = audit_takeover(config)
        conflict_findings = [
            f
            for f in findings
            if f.finding_id == "takeover-conflict-with-blanket-allows"
        ]
        self.assertEqual(conflict_findings, [])

    def test_agreeing_levels_with_blanket_allows_not_flagged(self):
        """
        Given the same two-level shape but with BOTH levels agreeing (enabled=True)
        And native settings contain a Bash(*) blanket allow
        When audit_takeover() is called
        Then no 'takeover-conflict-with-blanket-allows' finding is returned --
             the finding requires the disagreement, not merely two levels and a
             blanket allow
        """
        config = _make_config(
            _toolguard_layer(governed_tools=["Bash"], takeover_enabled=True),
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=True,
                ignored_allow_patterns=["Bash(*)"],
                provenance=_prov(level="user", specificity=2),
            ),
            _native_layer(allow=["Bash(*)"], hooks=_hooks_for("Bash")),
        )
        self.assertIsNone(config.takeover_mode().conflict)
        findings = audit_takeover(config)
        self.assertNotIn("takeover-conflict-with-blanket-allows", _ids(findings))


# ---------------------------------------------------------------------------
# Uncovered-blanket-allow (HIGH)
# ---------------------------------------------------------------------------


def _uncovered_blanket_config(takeover_enabled: bool) -> Configuration:
    """
    Build a config whose native layer carries an mcp__custom__tool(*) blanket
    allow that no ignored-pattern list covers.

    ``takeover_enabled`` is the only thing that varies between calls.
    """
    return _make_config(
        _toolguard_layer(
            governed_tools=["Bash", "mcp__custom__tool"],
            takeover_enabled=takeover_enabled,
        ),
        _native_layer(
            allow=["mcp__custom__tool(*)"],
            hooks=_hooks_for("Bash", "mcp__custom__tool"),
        ),
    )


class TestUncoveredBlanketAllow(unittest.TestCase):
    """Tests for the uncovered-blanket-allow HIGH invariant."""

    def test_uncovered_blanket_allow_flagged(self):
        """
        Given takeover is ON and a native layer has a non-default blanket allow
        that is NOT in ignored_allow_patterns (not covered by the defaults either)
        When audit_takeover() is called
        Then a HIGH 'uncovered-blanket-allow' finding is returned, carrying the
             provenance of the NATIVE layer the allow was read from
        """
        config = _uncovered_blanket_config(takeover_enabled=True)
        takeover = config.takeover_mode()
        self.assertTrue(takeover.enabled)
        self.assertNotIn("mcp__custom__tool(*)", takeover.ignored_allow_patterns)

        findings = audit_takeover(config)
        uncovered = [f for f in findings if f.finding_id == "uncovered-blanket-allow"]
        self.assertEqual(len(uncovered), 1)
        self.assertEqual(uncovered[0].severity, AuditSeverity.HIGH)
        native_prov = [layer.provenance for layer in config.layers if layer.is_native]
        self.assertEqual(uncovered[0].provenance, native_prov[0])

    def test_not_flagged_when_takeover_is_off(self):
        """
        Given the SAME uncovered blanket allow but takeover OFF
        When audit_takeover() is called
        Then no 'uncovered-blanket-allow' finding is returned -- the invariant is
             about allows takeover was supposed to strip, so it is meaningless
             when takeover is not stripping anything (a blanket allow with
             takeover off is the danger analyzer's blanket-allow-outside-takeover
             finding, not this one)
        And the ON run of the same config DOES return it, so the difference is
             attributable to the switch
        """
        off = audit_takeover(_uncovered_blanket_config(takeover_enabled=False))
        on = audit_takeover(_uncovered_blanket_config(takeover_enabled=True))
        self.assertNotIn("uncovered-blanket-allow", _ids(off))
        self.assertIn("uncovered-blanket-allow", _ids(on))

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

    def test_additional_ignored_patterns_also_cover_a_blanket_allow(self):
        """
        Given takeover is ON and the blanket allow is listed in
             additional_ignored_patterns rather than ignored_allow_patterns
        When audit_takeover() is called
        Then no 'uncovered-blanket-allow' finding is returned -- both lists count
        """
        config = _make_config(
            _toolguard_layer(
                governed_tools=["Bash", "mcp__custom__tool"],
                takeover_enabled=True,
                additional_ignored_patterns=["mcp__custom__tool(*)"],
            ),
            _native_layer(
                allow=["mcp__custom__tool(*)"],
                hooks=_hooks_for("Bash", "mcp__custom__tool"),
            ),
        )
        self.assertIn(
            "mcp__custom__tool(*)",
            config.takeover_mode().additional_ignored_patterns,
        )
        findings = audit_takeover(config)
        self.assertNotIn("uncovered-blanket-allow", _ids(findings))

    def test_toolguard_layer_blanket_allow_is_not_an_uncovered_native_allow(self):
        """
        Given takeover is ON and the blanket allow sits in a toolguard_hook layer
             rather than a native one
        When audit_takeover() is called
        Then no 'uncovered-blanket-allow' finding is returned -- takeover only
             neutralizes NATIVE allows (neutralized_by_takeover requires
             is_native), so this allow is never stripped and the finding's
             remediation, "add it to ignored_allow_patterns", would not affect it
        And the allow is indeed still live in the resolved permission layers
        """
        config = _make_config(
            _toolguard_layer(
                governed_tools=["Bash", "mcp__custom__tool"],
                takeover_enabled=True,
                allow=["mcp__custom__tool(*)"],
            ),
            _native_layer(hooks=_hooks_for("Bash", "mcp__custom__tool")),
        )
        self.assertNotIn(
            "mcp__custom__tool(*)", config.takeover_mode().ignored_allow_patterns
        )
        findings = audit_takeover(config)
        self.assertNotIn("uncovered-blanket-allow", _ids(findings))
        live = [layer.allow for layer in config.permission_layers("mcp__custom__tool")]
        self.assertIn(("*",), live)

    def test_specific_native_allow_is_not_a_blanket_allow(self):
        """
        Given takeover is ON and a native layer carries a SPECIFIC allow
             ('Bash(git status:*)') alongside a covered blanket allow
        When audit_takeover() is called
        Then no 'uncovered-blanket-allow' finding is returned -- only an allow
             whose body strips to '*' is a blanket allow
        """
        config = _make_config(
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=True,
                ignored_allow_patterns=["Bash(*)"],
            ),
            _native_layer(
                allow=["Bash(*)", "Bash(git status:*)"],
                hooks=_hooks_for("Bash"),
            ),
        )
        findings = audit_takeover(config)
        self.assertNotIn("uncovered-blanket-allow", _ids(findings))


# ---------------------------------------------------------------------------
# Loose-no-match-fallback (LOW)
# ---------------------------------------------------------------------------


def _fallback_config(
    no_match_fallback: Optional[str] = None,
    top_level_no_match_fallback: Optional[str] = None,
) -> Configuration:
    """
    Build an otherwise-correct takeover setup with the given no_match_fallback.

    ``no_match_fallback`` goes into the legacy ``[takeover_mode]`` section;
    ``top_level_no_match_fallback`` goes into the top-level key that
    :meth:`Configuration.resolved_no_match_fallback` honours ahead of it.
    """
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        takeover_enabled=True,
        no_match_fallback=no_match_fallback,
        ignored_allow_patterns=["Bash(*)"],
    )
    if top_level_no_match_fallback is not None:
        content = dict(tg_layer.content)
        content["no_match_fallback"] = top_level_no_match_fallback
        tg_layer = ConfigLayer(
            provenance=tg_layer.provenance, content=MappingProxyType(content)
        )
    return _make_config(
        tg_layer,
        _native_layer(allow=["Bash(*)"], hooks=_hooks_for("Bash")),
    )


class TestLooseNoMatchFallback(unittest.TestCase):
    """Tests for the loose-no-match-fallback LOW invariant."""

    def _fallback_findings(self, config: Configuration):
        return [
            f
            for f in audit_takeover(config)
            if f.finding_id == "loose-no-match-fallback"
        ]

    def test_warn_deny_fallback_flagged(self):
        """
        Given [takeover_mode].no_match_fallback is 'warn_deny' instead of 'deny'
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned
        """
        fallback_findings = self._fallback_findings(_fallback_config("warn_deny"))
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_deny_fallback_not_flagged(self):
        """
        Given [takeover_mode].no_match_fallback is 'deny' (the expected value)
        When audit_takeover() is called
        Then no 'loose-no-match-fallback' finding is returned
        """
        self.assertEqual(self._fallback_findings(_fallback_config("deny")), [])

    def test_unset_fallback_flagged(self):
        """
        Given no_match_fallback is set nowhere, so it resolves to its 'ask' default
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned -- the default
             is not 'deny', and the invariant reports the effective value rather
             than only an explicitly written one
        """
        config = _fallback_config()
        self.assertEqual(config.resolved_no_match_fallback(), "ask")
        fallback_findings = self._fallback_findings(config)
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_allow_fallback_flagged(self):
        """
        Given [takeover_mode].no_match_fallback is 'allow' (TOO-19: allow with NO warning)
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned -- the
            blanket '!= deny' check requires no special-casing for this new
            value, it is simply another non-'deny' raw spelling
        """
        fallback_findings = self._fallback_findings(_fallback_config("allow"))
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_allow_with_no_warnings_fallback_flagged(self):
        """
        Given [takeover_mode].no_match_fallback is 'allow_with_no_warnings'
            (TOO-19's long-form alias for 'allow')
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned, exactly as
            for 'allow'
        """
        fallback_findings = self._fallback_findings(
            _fallback_config("allow_with_no_warnings")
        )
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_loose_top_level_key_is_flagged_though_the_section_says_deny(self):
        """
        Given the top-level no_match_fallback is 'allow' while the legacy
             [takeover_mode] section still says 'deny'
        And resolved_no_match_fallback() -- the value that actually decides --
             is therefore 'allow'
        When audit_takeover() is called
        Then a LOW 'loose-no-match-fallback' finding is returned, because the
             audit must report the setting that governs, not the losing alias
        """
        config = _fallback_config(
            no_match_fallback="deny", top_level_no_match_fallback="allow"
        )
        self.assertEqual(config.resolved_no_match_fallback(), "allow")
        fallback_findings = self._fallback_findings(config)
        self.assertEqual(len(fallback_findings), 1)
        self.assertEqual(fallback_findings[0].severity, AuditSeverity.LOW)

    def test_hardened_top_level_key_is_not_flagged(self):
        """
        Given the top-level no_match_fallback is 'deny' and no [takeover_mode]
             alias is written at all
        And resolved_no_match_fallback() is therefore 'deny'
        When audit_takeover() is called
        Then no 'loose-no-match-fallback' finding is returned -- telling a user
             who has explicitly hardened the governing key that it is loose is a
             false alarm
        """
        config = _fallback_config(top_level_no_match_fallback="deny")
        self.assertEqual(config.resolved_no_match_fallback(), "deny")
        self.assertEqual(self._fallback_findings(config), [])


# ---------------------------------------------------------------------------
# Loose-undecidable-fallback (HIGH)
# ---------------------------------------------------------------------------


class TestLooseUndecidableFallback(unittest.TestCase):
    """Tests for the loose-undecidable-fallback HIGH invariant."""

    def _undecidable_config(self, value: Optional[str]) -> Configuration:
        """Build an otherwise-correct takeover setup with the given undecidable_fallback."""
        return _make_config(
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=True,
                no_match_fallback="deny",
                ignored_allow_patterns=["Bash(*)"],
                undecidable_fallback=value,
            ),
            _native_layer(allow=["Bash(*)"], hooks=_hooks_for("Bash")),
        )

    def _matches(self, config: Configuration):
        return [
            f
            for f in audit_takeover(config)
            if f.finding_id == "loose-undecidable-fallback"
        ]

    def test_allow_with_warning_flagged_high(self):
        """
        Given undecidable_fallback is 'allow_with_warning'
        When audit_takeover() is called
        Then a HIGH 'loose-undecidable-fallback' finding is returned
        """
        matches = self._matches(self._undecidable_config("allow_with_warning"))
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
        self.assertEqual(self._matches(self._undecidable_config("ask")), [])

    def test_deny_not_flagged(self):
        """
        Given undecidable_fallback is 'deny' (strictly more conservative than default)
        When audit_takeover() is called
        Then no 'loose-undecidable-fallback' finding is returned, because a
             stricter-than-default setting is never itself a risk
        """
        self.assertEqual(self._matches(self._undecidable_config("deny")), [])

    def test_unset_not_flagged(self):
        """
        Given undecidable_fallback is not set anywhere (resolves to default 'ask')
        When audit_takeover() is called
        Then no 'loose-undecidable-fallback' finding is returned
        """
        self.assertEqual(self._matches(self._undecidable_config(None)), [])

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
        matches = self._matches(config)
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
        matches = self._matches(self._undecidable_config("allow"))
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
        matches = self._matches(self._undecidable_config("allow_with_no_warnings"))
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

    def test_findings_sorted_severity_descending(self):
        """
        Given a configuration producing CRITICAL, HIGH and LOW findings at once
             (a governed tool with no hook, a loose undecidable_fallback, and a
             loose no_match_fallback)
        When audit_takeover() returns results
        Then all three severities are present and the list is ordered severity
             descending, ties broken by tool name (None first) then finding_id
        """
        config = _make_config(
            _toolguard_layer(
                governed_tools=["Bash", "Read"],
                takeover_enabled=True,
                no_match_fallback="allow",
                ignored_allow_patterns=["Bash(*)", "Read(*)"],
                undecidable_fallback="allow_with_warning",
            ),
            _native_layer(
                allow=["Bash(*)", "Read(*)"],
                hooks=_hooks_for("Bash"),
            ),
        )
        findings = audit_takeover(config)
        severities = [f.severity for f in findings]
        self.assertEqual(
            {AuditSeverity.CRITICAL, AuditSeverity.HIGH, AuditSeverity.LOW},
            set(severities),
        )
        self.assertEqual(severities, sorted(severities, reverse=True))
        self.assertEqual(
            [(f.finding_id, f.severity, f.tool) for f in findings],
            [
                ("partial-hook-registration", AuditSeverity.CRITICAL, None),
                ("hook-not-registered", AuditSeverity.CRITICAL, "Read"),
                ("loose-undecidable-fallback", AuditSeverity.HIGH, None),
                ("loose-no-match-fallback", AuditSeverity.LOW, None),
            ],
        )

    def test_same_severity_findings_are_ordered_by_finding_id(self):
        """
        Given a config producing exactly two HIGH config-wide findings -- a
             takeover conflict alongside native blanket allows, and a loose
             undecidable_fallback
        When audit_takeover() returns results
        Then they are ordered by finding_id, which is the REVERSE of the order
             the invariants append them in, so the tie-break is what decides
        """
        config = _make_config(
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=True,
                no_match_fallback="deny",
                ignored_allow_patterns=["Bash(*)"],
                undecidable_fallback="allow",
            ),
            _toolguard_layer(
                governed_tools=["Bash"],
                takeover_enabled=False,
                provenance=_prov(level="user", specificity=2),
            ),
            _native_layer(allow=["Bash(*)"], hooks=_hooks_for("Bash")),
        )
        findings = audit_takeover(config)
        self.assertEqual({f.severity for f in findings}, {AuditSeverity.HIGH})
        self.assertEqual(
            _ids(findings),
            ["loose-undecidable-fallback", "takeover-conflict-with-blanket-allows"],
        )


# ---------------------------------------------------------------------------
# Malformed native settings
# ---------------------------------------------------------------------------


#: Shapes a hand-edited settings.json can really take, each aimed at one of the
#: type guards in the hooks/permissions walk.
_MALFORMED_NATIVE_CONTENTS = {
    "hooks_is_a_string": {"hooks": "yes"},
    # Non-iterable rather than a string: a string PreToolUse is skipped by the
    # per-entry dict guard downstream, which masks the loss of this one.
    "PreToolUse_is_a_number": {"hooks": {"PreToolUse": 5}},
    "hook_entry_is_a_string": {"hooks": {"PreToolUse": ["toolguard"]}},
    # The matcher must be paired with a REAL toolguard hook, or the walk never
    # reaches the point where a non-str matcher would be used as a set member.
    "matcher_is_a_list": {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": ["Bash"],
                    "hooks": [{"type": "command", "command": "~/.local/bin/toolguard"}],
                }
            ]
        }
    },
    "inner_hooks_is_a_number": {
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": 5}]}
    },
    "inner_hook_is_a_string": {
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ["toolguard"]}]}
    },
    "command_is_a_dict": {
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"command": {"path": "toolguard"}}]}
            ]
        }
    },
    "permissions_is_a_list": {"permissions": ["Bash(*)"]},
    "allow_entry_is_a_dict": {"permissions": {"allow": [{"Bash": "*"}]}},
}


class TestMalformedNativeSettings(unittest.TestCase):
    """Tests that a malformed native settings layer does not abort the audit."""

    def test_audit_survives_malformed_native_settings(self):
        """
        Given a native settings layer whose hooks or permissions section has a
             wrong-typed value, as a hand-edited settings.json really can
        When audit_takeover() is called
        Then it returns findings rather than raising -- a crashed audit is a
             report that never happened, which is indistinguishable from a clean
             one to anyone reading the exit status
        And the governed tool is still reported as unhooked, since nothing in the
             malformed layer registered it
        """
        for label, content in _MALFORMED_NATIVE_CONTENTS.items():
            with self.subTest(shape=label):
                config = _make_config(
                    _toolguard_layer(governed_tools=["Bash"], takeover_enabled=True),
                    ConfigLayer(
                        provenance=_prov(source_type="claude", specificity=1),
                        content=MappingProxyType(content),
                    ),
                )
                findings = audit_takeover(config)
                self.assertIn("hook-not-registered", _ids(findings))

    def test_helpers_survive_malformed_native_settings(self):
        """
        Given the same malformed native settings layers
        When the two helpers that walk them are called directly
        Then neither raises: no tool is registered, and no blanket allow is found
             (none of these shapes contains a well-formed one)
        """
        for label, content in _MALFORMED_NATIVE_CONTENTS.items():
            with self.subTest(shape=label):
                config = _make_config(
                    ConfigLayer(
                        provenance=_prov(source_type="claude", specificity=1),
                        content=MappingProxyType(content),
                    )
                )
                self.assertEqual(_get_registered_toolguard_tools(config), set())
                self.assertFalse(_has_any_blanket_allow_in_native(config))


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

    def test_hooks_in_a_toolguard_layer_do_not_register(self):
        """
        Given a hooks section written into a toolguard_hook layer rather than a
             native settings layer
        When _get_registered_toolguard_tools() is called
        Then nothing is registered -- only Claude reads hooks, and it reads them
             from native settings only, so a hooks block in toolguard_hook.toml
             registers no hook however well-formed it is
        And audit_takeover() reports the governed tool as unhooked
        """
        tg_layer = ConfigLayer(
            provenance=_prov(),
            content=MappingProxyType(
                {
                    "governed_tools": ["Bash"],
                    "takeover_mode": {"enabled": True},
                    "hooks": _hooks_for("Bash"),
                }
            ),
        )
        config = _make_config(tg_layer)
        self.assertEqual(_get_registered_toolguard_tools(config), set())
        findings = audit_takeover(config)
        self.assertIn("hook-not-registered", _ids(findings))

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

    def test_blanket_allow_in_a_toolguard_layer_is_not_native(self):
        """
        Given a blanket allow written in a toolguard_hook layer, not a native one
        When _has_any_blanket_allow_in_native() is called
        Then False is returned -- takeover only ever neutralizes NATIVE allows
             (neutralized_by_takeover requires is_native), so a toolguard-layer
             blanket allow is not the thing this invariant is about
        """
        config = _make_config(_toolguard_layer(allow=["Bash(*)"]))
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
