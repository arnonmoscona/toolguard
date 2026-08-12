"""Unit tests for toolguard.tools.security_audit -- unified security audit aggregator."""

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional
from unittest.mock import MagicMock, patch

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.tools.security_audit import (
    RankedFinding,
    Remediation,
    SecurityReport,
    _acknowledgement_label,
    _danger_proposal,
    _finding_delta,
    _render_edit_banner,
    main,
    render,
    security_audit,
)
from toolguard.tools.edit_proposal import EditProposal
from toolguard.tools.config_access import per_layer_rules
from toolguard.tools.danger import DangerFinding, Severity
from toolguard.tools.edit_proposal import apply_edits, edit_proposal_to_dict

_pythonpath_patcher = None


def setUpModule():
    """
    Isolate PYTHONPATH for the module: security_audit() calls audit_environment(),
    which reads PYTHONPATH from the real environment by default (env=None), so an
    untouched test would depend on whatever happens to be set on the machine
    running the suite. Popped for the module's lifetime via patch.dict's
    save/restore. Tests exercising the environment finding pass env= explicitly
    instead of relying on this module-wide patch.
    """
    global _pythonpath_patcher
    _pythonpath_patcher = patch.dict(os.environ, {})
    _pythonpath_patcher.start()
    os.environ.pop("PYTHONPATH", None)


def tearDownModule():
    """Restore PYTHONPATH (and anything else) to its pre-module state."""
    if _pythonpath_patcher is not None:
        _pythonpath_patcher.stop()


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


def _danger_allow_layer(
    tool: str, allow: List[str], specificity: int = 0
) -> ConfigLayer:
    """Build a toolguard_hook layer with ``tool``'s dangerous allow patterns wrapped in ``Tool(inner)`` form, as stored in real configs."""
    wrapped = [f"{tool}({p})" for p in allow]
    return ConfigLayer(
        provenance=_prov(specificity=specificity),
        content=MappingProxyType(
            {
                "permissions": {
                    "allow": wrapped,
                    "deny": [],
                    "ask": [],
                }
            }
        ),
    )


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _clean_config() -> Configuration:
    """Return a Configuration with Bash governed and hooked, no_match_fallback='deny', and no dangerous rules -- produces no findings from either analyser."""
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    native_layer = _native_layer(hooks=_hooks_for("Bash"))
    return _make_config(tg_layer, native_layer)


def _danger_only_config() -> Configuration:
    """Return a Configuration with Bash allowed 'uv run python:*' (fires arbitrary-exec-allow) and hooked -- danger findings only."""
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    danger_layer = _danger_allow_layer("Bash", ["uv run python:*"])
    native_layer = _native_layer(hooks=_hooks_for("Bash"))
    return _make_config(tg_layer, danger_layer, native_layer)


def _takeover_only_config() -> Configuration:
    """Return a Configuration with Bash governed but no hook registered -- takeover findings only."""
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    return _make_config(tg_layer)


def _mixed_config() -> Configuration:
    """Return a Configuration with a dangerous allow rule and no hook registered -- both danger and takeover findings."""
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    danger_layer = _danger_allow_layer("Bash", ["uv run python:*"])
    return _make_config(tg_layer, danger_layer)


def _takeover_on_config() -> Configuration:
    """Return a Configuration with takeover mode enabled, Bash governed and hooked, and no dangerous rules."""
    governed = ["Bash"]
    ignored = ["Bash(*)"]
    tg_layer = _toolguard_layer(
        governed_tools=governed,
        takeover_enabled=True,
        no_match_fallback="deny",
        ignored_allow_patterns=ignored,
    )
    native_layer = _native_layer(
        allow=["Bash(*)"],
        hooks=_hooks_for("Bash"),
    )
    return _make_config(tg_layer, native_layer)


def _loose_undecidable_fallback_config() -> Configuration:
    """Return a Configuration with undecidable_fallback='allow_with_warning', Bash governed and hooked -- isolates the finding to loose-undecidable-fallback only."""
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
        undecidable_fallback="allow_with_warning",
    )
    native_layer = _native_layer(hooks=_hooks_for("Bash"))
    return _make_config(tg_layer, native_layer)


def _locus_config() -> Configuration:
    """Return a Configuration with a takeover finding carrying provenance -- uses a custom tool name because Bash(*) is always in the default ignored set."""
    tg_layer = _toolguard_layer(
        governed_tools=["mcp__custom__tool"],
        takeover_enabled=True,
        no_match_fallback="deny",
        ignored_allow_patterns=[],
    )
    native_layer = _native_layer(
        allow=["mcp__custom__tool(*)"],
        hooks=_hooks_for("mcp__custom__tool"),
    )
    return _make_config(tg_layer, native_layer)


# ---------------------------------------------------------------------------
# Empty / clean configuration
# ---------------------------------------------------------------------------


class TestSecurityAuditEmpty(unittest.TestCase):
    """Tests for a configuration that produces zero findings."""

    def test_empty_findings_tuple(self):
        """
        Given a configuration with no dangerous patterns and a properly registered hook
        When security_audit() is called
        Then the report contains an empty findings tuple
        """
        report = security_audit(_clean_config())
        self.assertEqual(report.findings, ())

    def test_highest_severity_zero(self):
        """
        Given a clean configuration with no findings
        When security_audit() is called
        Then highest_severity is 0
        """
        report = security_audit(_clean_config())
        self.assertEqual(report.highest_severity, 0)

    def test_counts_empty(self):
        """
        Given a clean configuration with no findings
        When security_audit() is called
        Then counts is an empty mapping (no severity labels appear)
        """
        report = security_audit(_clean_config())
        self.assertEqual(dict(report.counts), {})

    def test_render_markdown_no_findings_line(self):
        """
        Given a clean configuration producing no findings
        When render() is called with fmt='markdown'
        Then the output includes 'No security findings.'
        """
        report = security_audit(_clean_config())
        out = render(report, fmt="markdown")
        self.assertIn("No security findings.", out)

    def test_render_text_no_findings_line(self):
        """
        Given a clean configuration producing no findings
        When render() is called with fmt='text'
        Then the output includes 'No security findings.'
        """
        report = security_audit(_clean_config())
        out = render(report, fmt="text")
        self.assertIn("No security findings.", out)


# ---------------------------------------------------------------------------
# Danger findings only (source="rule")
# ---------------------------------------------------------------------------


class TestSecurityAuditDangerOnly(unittest.TestCase):
    """Tests for a configuration that triggers only danger (rule) findings."""

    def setUp(self):
        """Set up the report with a danger-only configuration."""
        self.report = security_audit(_danger_only_config())

    def test_findings_present(self):
        """
        Given a configuration with a dangerous allow rule (arbitrary-exec-allow)
        When security_audit() is called
        Then findings is non-empty
        """
        self.assertGreater(len(self.report.findings), 0)

    def test_all_findings_source_rule(self):
        """
        Given a configuration that only triggers danger analyser findings
        When security_audit() is called
        Then every RankedFinding has source='rule'
        """
        for f in self.report.findings:
            self.assertEqual(f.source, "rule", msg=f"Expected source='rule', got {f!r}")

    def test_finding_id_matches_detector(self):
        """
        Given a config with 'uv run python:*' allow rule
        When security_audit() is called
        Then a finding with finding_id='arbitrary-exec-allow' is present
        """
        ids = [f.finding_id for f in self.report.findings]
        self.assertIn("arbitrary-exec-allow", ids)

    def test_pattern_field_populated(self):
        """
        Given a danger finding from a specific pattern
        When security_audit() is called
        Then the RankedFinding.pattern field is set (not None)
        """
        for f in self.report.findings:
            self.assertIsNotNone(
                f.pattern, msg=f"Expected pattern set, got None in {f!r}"
            )

    def test_impact_empty_for_rule_findings(self):
        """
        Given danger findings (source='rule')
        When security_audit() is called
        Then impact is an empty string (danger findings embed impact in rationale)
        """
        for f in self.report.findings:
            self.assertEqual(
                f.impact, "", msg=f"Expected empty impact for rule finding {f!r}"
            )

    def test_severity_value_and_label_consistent(self):
        """
        Given danger findings with known severity enum values
        When security_audit() is called
        Then severity_value and severity_label are consistent (label matches value)
        """
        for f in self.report.findings:
            expected_label = {1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}.get(
                f.severity_value
            )
            self.assertEqual(
                f.severity_label,
                expected_label,
                msg=f"Severity label mismatch in {f!r}",
            )

    def test_tool_field_set(self):
        """
        Given danger findings for Bash tool
        When security_audit() is called
        Then tool field is 'Bash' on all findings
        """
        for f in self.report.findings:
            self.assertEqual(f.tool, "Bash")


# ---------------------------------------------------------------------------
# Takeover audit findings only (source="takeover")
# ---------------------------------------------------------------------------


class TestSecurityAuditTakeoverOnly(unittest.TestCase):
    """Tests for a configuration that triggers only takeover audit findings."""

    def setUp(self):
        """Set up the report with a takeover-only configuration."""
        self.report = security_audit(_takeover_only_config())

    def test_findings_present(self):
        """
        Given a configuration missing the Bash hook registration
        When security_audit() is called
        Then findings is non-empty
        """
        self.assertGreater(len(self.report.findings), 0)

    def test_all_findings_source_takeover(self):
        """
        Given a configuration that only triggers takeover audit findings
        When security_audit() is called
        Then every RankedFinding has source='takeover'
        """
        for f in self.report.findings:
            self.assertEqual(
                f.source, "takeover", msg=f"Expected source='takeover', got {f!r}"
            )

    def test_hook_not_registered_finding_present(self):
        """
        Given a governed tool (Bash) with no hook registered
        When security_audit() is called
        Then a finding with finding_id='hook-not-registered' is present
        """
        ids = [f.finding_id for f in self.report.findings]
        self.assertIn("hook-not-registered", ids)

    def test_pattern_none_for_takeover_findings(self):
        """
        Given takeover audit findings (source='takeover')
        When security_audit() is called
        Then pattern is None (takeover findings do not concern a specific pattern)
        """
        for f in self.report.findings:
            self.assertIsNone(
                f.pattern, msg=f"Expected None pattern for takeover finding {f!r}"
            )

    def test_impact_non_empty_for_takeover_findings(self):
        """
        Given takeover audit findings which carry an impact field
        When security_audit() is called
        Then impact is a non-empty string
        """
        for f in self.report.findings:
            self.assertIsInstance(f.impact, str)
            self.assertGreater(
                len(f.impact), 0, msg=f"Expected non-empty impact in {f!r}"
            )


# ---------------------------------------------------------------------------
# Loose-undecidable-fallback finding, end to end
# ---------------------------------------------------------------------------


class TestLooseUndecidableFallbackFinding(unittest.TestCase):
    """End-to-end tests: loose-undecidable-fallback reaches security_audit(), render(), and the JSON --format output."""

    def setUp(self):
        """Set up the report for a configuration with undecidable_fallback='allow_with_warning'."""
        self.report = security_audit(_loose_undecidable_fallback_config())
        self.matches = [
            f
            for f in self.report.findings
            if f.finding_id == "loose-undecidable-fallback"
        ]

    def test_finding_present_source_takeover_severity_high(self):
        """
        Given undecidable_fallback='allow_with_warning'
        When security_audit() is called
        Then exactly one loose-undecidable-fallback finding is present, with
             source='takeover' and severity_label='HIGH'
        """
        self.assertEqual(len(self.matches), 1)
        finding = self.matches[0]
        self.assertEqual(finding.source, "takeover")
        self.assertEqual(finding.severity_label, "HIGH")
        self.assertEqual(finding.severity_value, 3)

    def test_ask_and_deny_do_not_produce_the_finding(self):
        """
        Given undecidable_fallback is 'ask' or 'deny' in two separate configs
        When security_audit() is called on each
        Then neither produces a loose-undecidable-fallback finding
        """
        for value in ("ask", "deny"):
            tg_layer = _toolguard_layer(
                governed_tools=["Bash"],
                no_match_fallback="deny",
                undecidable_fallback=value,
            )
            native_layer = _native_layer(hooks=_hooks_for("Bash"))
            config = _make_config(tg_layer, native_layer)
            report = security_audit(config)
            matches = [
                f
                for f in report.findings
                if f.finding_id == "loose-undecidable-fallback"
            ]
            self.assertEqual(
                matches, [], msg=f"undecidable_fallback={value!r} should not flag"
            )

    def test_unset_does_not_produce_the_finding(self):
        """
        Given undecidable_fallback is not set anywhere (resolves to default 'ask')
        When security_audit() is called
        Then no loose-undecidable-fallback finding is produced
        """
        report = security_audit(_clean_config())
        matches = [
            f for f in report.findings if f.finding_id == "loose-undecidable-fallback"
        ]
        self.assertEqual(matches, [])

    def test_appears_in_markdown_render(self):
        """
        Given a report containing the loose-undecidable-fallback finding
        When render() is called with fmt='markdown'
        Then the finding id and its HIGH severity heading both appear in the output
        """
        text = render(self.report, fmt="markdown")
        self.assertIn("loose-undecidable-fallback", text)
        self.assertIn("## HIGH", text)

    def test_appears_in_text_render(self):
        """
        Given a report containing the loose-undecidable-fallback finding
        When render() is called with fmt='text'
        Then the finding id appears in the plain-text output
        """
        text = render(self.report, fmt="text")
        self.assertIn("loose-undecidable-fallback", text)

    def test_appears_in_json_output(self):
        """
        Given a config with undecidable_fallback='allow_with_warning'
        When main() runs with --format json (load_config mocked to avoid any
             real filesystem discovery -- see test-config-isolation.md)
        Then the JSON findings list contains a loose-undecidable-fallback entry
             with severity_label='HIGH'
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            mock_load.return_value = _loose_undecidable_fallback_config()
            captured = io.StringIO()
            with patch("sys.stdout", captured):
                main(["--dir", ".", "--format", "json"])
            data = json.loads(captured.getvalue())
        matches = [
            f
            for f in data["findings"]
            if f["finding_id"] == "loose-undecidable-fallback"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["severity_label"], "HIGH")
        self.assertEqual(matches[0]["source"], "takeover")


# ---------------------------------------------------------------------------
# Mixed danger + takeover findings, sorted correctly
# ---------------------------------------------------------------------------


class TestSecurityAuditMixed(unittest.TestCase):
    """Tests for a configuration that produces both danger and takeover findings."""

    def setUp(self):
        """Set up the report with mixed danger + takeover configuration."""
        self.report = security_audit(_mixed_config())

    def test_both_sources_present(self):
        """
        Given a configuration triggering both danger and takeover findings
        When security_audit() is called
        Then findings include both source='rule' and source='takeover'
        """
        sources = {f.source for f in self.report.findings}
        self.assertIn("rule", sources)
        self.assertIn("takeover", sources)

    def test_sorted_severity_descending(self):
        """
        Given multiple findings at various severities
        When security_audit() is called
        Then findings are ordered with highest severity_value first (descending)
        """
        values = [f.severity_value for f in self.report.findings]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_same_severity_sorted_source_then_id(self):
        """
        Given two CRITICAL findings -- one 'rule' and one 'takeover' -- at the same tool
        When security_audit() is called
        Then within the same severity the 'rule' source sorts before 'takeover'
        (because 'rule' < 'takeover' lexicographically, which is the defined sort key)
        """
        critical = [f for f in self.report.findings if f.severity_value == 4]
        self.assertGreaterEqual(
            len(critical), 2, msg="fixture must produce >=2 CRITICAL findings"
        )
        self.assertIn("rule", {f.source for f in critical})
        self.assertIn("takeover", {f.source for f in critical})
        sources = [f.source for f in critical]
        self.assertEqual(
            sources,
            sorted(sources),
            msg=f"Expected source ordering asc within CRITICAL: {sources!r}",
        )


# ---------------------------------------------------------------------------
# Takeover active flag
# ---------------------------------------------------------------------------


class TestTakeoverActiveFlag(unittest.TestCase):
    """Tests that takeover_active is correctly reflected in report and render."""

    def test_takeover_active_false_for_clean_config(self):
        """
        Given a configuration with takeover mode OFF
        When security_audit() is called
        Then report.takeover_active is False
        """
        report = security_audit(_clean_config())
        self.assertFalse(report.takeover_active)

    def test_takeover_active_true_when_enabled(self):
        """
        Given a configuration with takeover mode enabled=True
        When security_audit() is called
        Then report.takeover_active is True
        """
        report = security_audit(_takeover_on_config())
        self.assertTrue(report.takeover_active)

    def test_render_markdown_shows_active_banner(self):
        """
        Given a report with takeover_active=True
        When render() is called with fmt='markdown'
        Then the output contains 'ACTIVE' in the takeover banner
        """
        report = security_audit(_takeover_on_config())
        out = render(report, fmt="markdown")
        self.assertIn("ACTIVE", out)

    def test_render_text_shows_active_banner(self):
        """
        Given a report with takeover_active=True
        When render() is called with fmt='text'
        Then the output contains 'Takeover mode: ACTIVE'
        """
        report = security_audit(_takeover_on_config())
        out = render(report, fmt="text")
        self.assertIn("Takeover mode: ACTIVE", out)

    def test_render_markdown_shows_inactive_banner(self):
        """
        Given a report with takeover_active=False
        When render() is called with fmt='markdown'
        Then the output contains 'INACTIVE' in the takeover banner
        """
        report = security_audit(_clean_config())
        out = render(report, fmt="markdown")
        self.assertIn("INACTIVE", out)


# ---------------------------------------------------------------------------
# Counts dict
# ---------------------------------------------------------------------------


class TestCountsDict(unittest.TestCase):
    """Tests that counts dict accurately reflects findings severity distribution."""

    def test_counts_empty_for_no_findings(self):
        """
        Given a clean configuration with no findings
        When security_audit() is called
        Then counts is an empty dict
        """
        report = security_audit(_clean_config())
        self.assertEqual(dict(report.counts), {})

    def test_counts_only_includes_present_severities(self):
        """
        Given findings at specific severities
        When security_audit() is called
        Then counts only contains entries for severities that actually appear
        """
        report = security_audit(_danger_only_config())
        for label in report.counts:
            self.assertIn(label, ("LOW", "MEDIUM", "HIGH", "CRITICAL"))
        present_labels = {f.severity_label for f in report.findings}
        self.assertEqual(set(report.counts.keys()), present_labels)

    def test_counts_total_matches_findings_count(self):
        """
        Given a report with some findings
        When security_audit() is called
        Then the sum of counts values equals the total number of findings
        """
        report = security_audit(_mixed_config())
        total = sum(report.counts.values())
        self.assertEqual(total, len(report.findings))

    def test_counts_individual_values_correct(self):
        """
        Given a report with N CRITICAL findings
        When security_audit() is called
        Then counts['CRITICAL'] equals the number of CRITICAL findings in findings tuple
        """
        report = security_audit(_mixed_config())
        for label in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            expected = sum(1 for f in report.findings if f.severity_label == label)
            self.assertEqual(
                report.counts.get(label, 0),
                expected,
                msg=f"Count mismatch for {label}",
            )


# ---------------------------------------------------------------------------
# ASCII-only render output
# ---------------------------------------------------------------------------


class TestRenderAsciiOnly(unittest.TestCase):
    """Tests that render output is strict ASCII (no Unicode, no emoji)."""

    def _assert_ascii(self, text: str, context: str) -> None:
        """Assert every character in text has ord < 128."""
        non_ascii = [(i, c) for i, c in enumerate(text) if ord(c) >= 128]
        self.assertEqual(
            non_ascii,
            [],
            msg=f"{context}: non-ASCII characters at positions {non_ascii!r}",
        )

    def test_render_markdown_ascii_clean_config(self):
        """
        Given a clean configuration
        When render() is called with fmt='markdown'
        Then the output is strict ASCII (all chars ord < 128)
        """
        report = security_audit(_clean_config())
        out = render(report, fmt="markdown")
        self._assert_ascii(out, "markdown/clean")

    def test_render_text_ascii_clean_config(self):
        """
        Given a clean configuration
        When render() is called with fmt='text'
        Then the output is strict ASCII
        """
        report = security_audit(_clean_config())
        out = render(report, fmt="text")
        self._assert_ascii(out, "text/clean")

    def test_render_markdown_ascii_with_findings(self):
        """
        Given a configuration producing findings (danger + takeover)
        When render() is called with fmt='markdown'
        Then the output is still strict ASCII
        """
        report = security_audit(_mixed_config())
        out = render(report, fmt="markdown")
        self._assert_ascii(out, "markdown/findings")

    def test_render_text_ascii_with_findings(self):
        """
        Given a configuration producing findings
        When render() is called with fmt='text'
        Then the output is still strict ASCII
        """
        report = security_audit(_mixed_config())
        out = render(report, fmt="text")
        self._assert_ascii(out, "text/findings")


class TestRenderInvalidFormat(unittest.TestCase):
    """Tests that render() rejects unsupported format names."""

    def test_render_unknown_fmt_raises_value_error(self):
        """
        Given a valid report
        When render() is called with an unsupported fmt (e.g. 'html')
        Then it raises ValueError naming the bad value
        """
        report = security_audit(_clean_config())
        with self.assertRaises(ValueError):
            render(report, fmt="html")


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------


class TestRenderJson(unittest.TestCase):
    """Tests for the JSON output path via main()."""

    def _capture_main(self, argv: list) -> tuple:
        """Run main() and capture stdout, returning (output_str, exit_code)."""
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = main(argv)
        return captured.getvalue(), exit_code

    def _make_report(self, highest: int = 0, takeover: bool = False) -> SecurityReport:
        """Build a minimal SecurityReport for use with a mocked audit."""
        return SecurityReport(
            findings=(),
            takeover_active=takeover,
            highest_severity=highest,
            counts={},
        )

    def test_json_parseable(self):
        """
        Given a clean configuration rendered to JSON via main()
        When the output is parsed with json.loads
        Then it succeeds without raising an exception
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        data = json.loads(out)
        self.assertIsInstance(data, dict)

    def test_json_has_required_top_level_keys(self):
        """
        Given any report rendered to JSON
        When the JSON is parsed
        Then keys 'takeover_active', 'highest_severity', 'counts', 'findings' are present
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        data = json.loads(out)
        for key in ("takeover_active", "highest_severity", "counts", "findings"):
            self.assertIn(key, data, msg=f"Missing key: {key}")

    def test_migrations_embedded_in_context(self):
        """
        Given a JSON file of proposed hierarchy-migration analyses
        When main() runs with --format json --migrations PATH
        Then the output's context contains proposed_migrations with those entries,
             so an AI-assisted pass can assess the risk of enacting them.
        """
        migs = [
            {
                "tool": "Bash",
                "pattern": "git status:*",
                "decision_neutral": True,
                "scope_note": "Promotion: moving up ...",
            }
        ]
        with tempfile.TemporaryDirectory() as td:
            mig_path = Path(td) / "migs.json"
            mig_path.write_text(json.dumps(migs))
            with patch("toolguard.tools.security_audit.load_config") as mock_load:
                with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                    mock_load.return_value = MagicMock()
                    mock_sa.return_value = self._make_report()
                    out, _ = self._capture_main(
                        [
                            "--dir",
                            ".",
                            "--format",
                            "json",
                            "--migrations",
                            str(mig_path),
                        ]
                    )
        data = json.loads(out)
        self.assertIn("context", data)
        self.assertEqual(data["context"]["proposed_migrations"], migs)

    def test_bad_migrations_file_raises_system_exit(self):
        """
        Given a --migrations path that cannot be read
        When main() runs
        Then it exits (argparse error) rather than producing a report.
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                with self.assertRaises(SystemExit):
                    self._capture_main(
                        [
                            "--dir",
                            ".",
                            "--format",
                            "json",
                            "--migrations",
                            "/no/such/file.json",
                        ]
                    )

    def test_json_findings_list_with_required_fields(self):
        """
        Given a report with at least one finding rendered to JSON
        When the JSON is parsed
        Then each finding dict contains all RankedFinding field names
        """
        finding = RankedFinding(
            source="rule",
            finding_id="arbitrary-exec-allow",
            severity_value=4,
            severity_label="CRITICAL",
            tool="Bash",
            locus="project: /fake/path.toml",
            pattern="uv run python:*",
            summary="rationale text",
            impact="",
            remediation=Remediation(text="remediation text", proposal=None),
            takeover_active=False,
        )
        report = SecurityReport(
            findings=(finding,),
            takeover_active=False,
            highest_severity=4,
            counts={"CRITICAL": 1},
        )
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = report
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        data = json.loads(out)
        self.assertEqual(len(data["findings"]), 1)
        fd = data["findings"][0]
        expected_fields = [
            "source",
            "finding_id",
            "severity_value",
            "severity_label",
            "tool",
            "locus",
            "pattern",
            "summary",
            "impact",
            "remediation",
            "remediation_proposal",
            "takeover_active",
        ]
        for field in expected_fields:
            self.assertIn(field, fd, msg=f"Missing field in JSON finding: {field}")
        self.assertEqual(fd["remediation"], "remediation text")
        self.assertIsNone(fd["remediation_proposal"])

    def test_json_is_ascii_safe(self):
        """
        Given a report rendered to JSON
        When the output is inspected character by character
        Then all characters are ASCII (ord < 128) due to ensure_ascii=True
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        non_ascii = [c for c in out if ord(c) >= 128]
        self.assertEqual(non_ascii, [])

    def test_json_highest_severity_value(self):
        """
        Given a report with highest_severity=3
        When rendered to JSON
        Then 'highest_severity' in the JSON equals 3
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report(highest=3)
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        data = json.loads(out)
        self.assertEqual(data["highest_severity"], 3)


# ---------------------------------------------------------------------------
# --strict exit codes
# ---------------------------------------------------------------------------


class TestMainStrictExitCode(unittest.TestCase):
    """Tests for --strict exit code behaviour in main()."""

    def _run_main_strict(self, highest_severity: int) -> int:
        """Run main() with --strict using a mocked report and return exit code."""
        report = SecurityReport(
            findings=(),
            takeover_active=False,
            highest_severity=highest_severity,
            counts={},
        )
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            with patch("toolguard.tools.security_audit.load_config") as mock_load:
                with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                    mock_load.return_value = MagicMock()
                    mock_sa.return_value = report
                    return main(["--dir", ".", "--strict"])

    def test_strict_zero_on_no_findings(self):
        """
        Given a clean config (highest_severity=0) and --strict flag
        When main() is called
        Then exit code is 0
        """
        self.assertEqual(self._run_main_strict(0), 0)

    def test_strict_returns_highest_severity_1(self):
        """
        Given findings with highest_severity=1 (LOW) and --strict flag
        When main() is called
        Then exit code is 1
        """
        self.assertEqual(self._run_main_strict(1), 1)

    def test_strict_returns_highest_severity_2(self):
        """
        Given findings with highest_severity=2 (MEDIUM) and --strict flag
        When main() is called
        Then exit code is 2
        """
        self.assertEqual(self._run_main_strict(2), 2)

    def test_strict_returns_highest_severity_3(self):
        """
        Given findings with highest_severity=3 (HIGH) and --strict flag
        When main() is called
        Then exit code is 3
        """
        self.assertEqual(self._run_main_strict(3), 3)

    def test_strict_returns_highest_severity_4(self):
        """
        Given findings with highest_severity=4 (CRITICAL) and --strict flag
        When main() is called
        Then exit code is 4
        """
        self.assertEqual(self._run_main_strict(4), 4)

    def test_no_strict_always_exits_zero(self):
        """
        Given findings with highest_severity=4 but WITHOUT --strict flag
        When main() is called
        Then exit code is always 0
        """
        report = SecurityReport(
            findings=(),
            takeover_active=False,
            highest_severity=4,
            counts={"CRITICAL": 2},
        )
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            with patch("toolguard.tools.security_audit.load_config") as mock_load:
                with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                    mock_load.return_value = MagicMock()
                    mock_sa.return_value = report
                    code = main(["--dir", "."])
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# Locus populated from provenance.describe_brief()
# ---------------------------------------------------------------------------


class TestLocusFromProvenance(unittest.TestCase):
    """Tests that locus is correctly populated from provenance.describe_brief()."""

    def test_danger_finding_locus_from_provenance(self):
        """
        Given a danger finding produced by a toolguard layer with known provenance
        When security_audit() is called
        Then the corresponding RankedFinding.locus equals provenance.describe_brief()
        """
        report = security_audit(_danger_only_config())
        rule_findings = [f for f in report.findings if f.source == "rule"]
        self.assertGreater(len(rule_findings), 0, "Expected at least one rule finding")
        expected_locus = "project: /fake/.claude/toolguard_hook.toml"
        loci = [f.locus for f in rule_findings]
        self.assertIn(
            expected_locus,
            loci,
            msg=f"Expected locus {expected_locus!r} in {loci!r}",
        )

    def test_takeover_finding_with_provenance_locus(self):
        """
        Given a takeover 'uncovered-blanket-allow' finding which has provenance
        from the native settings layer
        When security_audit() is called
        Then the corresponding RankedFinding.locus equals that layer's describe_brief()
        """
        report = security_audit(_locus_config())
        uncovered = [
            f for f in report.findings if f.finding_id == "uncovered-blanket-allow"
        ]
        self.assertGreater(
            len(uncovered), 0, "Expected uncovered-blanket-allow finding"
        )
        expected_locus = "project: /fake/.claude/settings.local.json"
        for f in uncovered:
            self.assertEqual(
                f.locus,
                expected_locus,
                msg=f"Locus mismatch in {f!r}",
            )

    def test_finding_without_provenance_has_none_locus(self):
        """
        Given a takeover finding that has no provenance (e.g. hook-not-registered)
        When security_audit() is called
        Then the RankedFinding.locus is None
        """
        report = security_audit(_takeover_only_config())
        hook_findings = [
            f for f in report.findings if f.finding_id == "hook-not-registered"
        ]
        self.assertGreater(
            len(hook_findings), 0, "Expected hook-not-registered finding"
        )
        for f in hook_findings:
            self.assertIsNone(
                f.locus,
                msg=f"Expected None locus for finding without provenance, got {f.locus!r}",
            )


# ---------------------------------------------------------------------------
# --with-context flag tests
# ---------------------------------------------------------------------------


class TestWithContextFlag(unittest.TestCase):
    """Tests for the --with-context CLI flag and JSON context block."""

    def _capture_main(self, argv: list) -> tuple:
        """Run main() and capture stdout, returning (output_str, exit_code)."""
        captured = io.StringIO()
        with patch("sys.stdout", captured):
            exit_code = main(argv)
        return captured.getvalue(), exit_code

    def _make_report(self, highest: int = 0, takeover: bool = False) -> SecurityReport:
        """Build a minimal SecurityReport for use with a mocked audit."""
        return SecurityReport(
            findings=(),
            takeover_active=takeover,
            highest_severity=highest,
            counts={},
        )

    def _run_with_context_json(self, config_fn=None) -> dict:
        """Run main() with --format json --with-context (real config or mocked objects) and return the parsed JSON dict."""
        if config_fn is not None:
            with patch("toolguard.tools.security_audit.load_config") as mock_load:
                mock_load.return_value = config_fn()
                out, _ = self._capture_main(
                    ["--dir", ".", "--format", "json", "--with-context"]
                )
        else:
            with patch("toolguard.tools.security_audit.load_config") as mock_load:
                with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                    mock_load.return_value = MagicMock()
                    mock_sa.return_value = self._make_report()
                    out, _ = self._capture_main(
                        ["--dir", ".", "--format", "json", "--with-context"]
                    )
        return json.loads(out)

    def test_with_context_adds_context_key_in_json(self):
        """
        Given --format json and --with-context flag
        When main() is called with a clean config
        Then the JSON output contains a top-level 'context' key
        """
        data = self._run_with_context_json(config_fn=_clean_config)
        self.assertIn(
            "context", data, "Expected 'context' key in JSON with --with-context"
        )

    def test_context_has_summary_key(self):
        """
        Given --format json --with-context
        When main() is called
        Then context['summary'] is present and has required fields
        """
        data = self._run_with_context_json(config_fn=_clean_config)
        ctx = data["context"]
        self.assertIn("summary", ctx)
        summary = ctx["summary"]
        for key in ("sources", "governed_tools", "layer_count"):
            self.assertIn(key, summary, f"Missing summary field: {key}")

    def test_context_has_takeover_key(self):
        """
        Given --format json --with-context
        When main() is called
        Then context['takeover'] is present and has required fields
        """
        data = self._run_with_context_json(config_fn=_clean_config)
        ctx = data["context"]
        self.assertIn("takeover", ctx)
        takeover = ctx["takeover"]
        for key in (
            "enabled",
            "no_match_fallback",
            "ignored_allow_patterns",
            "additional_ignored_patterns",
            "conflict",
            "neutralized_allow_patterns",
        ):
            self.assertIn(key, takeover, f"Missing takeover field: {key}")

    def test_context_has_tools_key(self):
        """
        Given --format json --with-context with a config that governs Bash
        When main() is called
        Then context['tools'] is a list, and each tool entry has 'tool' and 'layers'
        """
        data = self._run_with_context_json(config_fn=_danger_only_config)
        ctx = data["context"]
        self.assertIn("tools", ctx)
        self.assertIsInstance(ctx["tools"], list)
        if ctx["tools"]:
            first_tool = ctx["tools"][0]
            self.assertIn("tool", first_tool)
            self.assertIn("layers", first_tool)

    def test_layers_have_required_fields(self):
        """
        Given --format json --with-context
        When main() is called
        Then each layer entry inside a tool has locus, is_native, allow, deny, ask fields
        """
        data = self._run_with_context_json(config_fn=_danger_only_config)
        ctx = data["context"]
        for tool_entry in ctx["tools"]:
            for layer in tool_entry["layers"]:
                for key in ("locus", "is_native", "allow", "deny", "ask"):
                    self.assertIn(
                        key, layer, f"Missing layer field '{key}' in {layer!r}"
                    )

    def test_neutralized_allow_patterns_in_takeover_context(self):
        """
        Given --format json --with-context with a takeover-on config that has ignored patterns
        When main() is called
        Then context['takeover']['neutralized_allow_patterns'] is a list (possibly non-empty)
        """
        data = self._run_with_context_json(config_fn=_takeover_on_config)
        ctx = data["context"]
        nap = ctx["takeover"]["neutralized_allow_patterns"]
        self.assertIsInstance(nap, list)

    def test_without_flag_no_context_key_in_json(self):
        """
        Given --format json WITHOUT --with-context
        When main() is called
        Then the JSON output does NOT contain a 'context' key (backward compatibility)
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, _ = self._capture_main(["--dir", ".", "--format", "json"])
        data = json.loads(out)
        self.assertNotIn(
            "context",
            data,
            "The 'context' key must NOT appear when --with-context is absent",
        )

    def test_existing_json_keys_unchanged_with_context(self):
        """
        Given --format json --with-context
        When main() is called
        Then existing top-level keys (takeover_active, highest_severity, counts, findings)
        are all present and unchanged alongside the new 'context' key
        """
        data = self._run_with_context_json(config_fn=_clean_config)
        for key in ("takeover_active", "highest_severity", "counts", "findings"):
            self.assertIn(
                key, data, f"Existing key '{key}' is missing with --with-context"
            )

    def test_with_context_markdown_does_not_error(self):
        """
        Given --format markdown --with-context
        When main() is called
        Then no error is raised and output is normal markdown (context flag is a no-op)
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, exit_code = self._capture_main(
                    ["--dir", ".", "--format", "markdown", "--with-context"]
                )
        self.assertEqual(exit_code, 0)
        self.assertGreater(len(out), 0, "Expected some markdown output")

    def test_with_context_text_does_not_error(self):
        """
        Given --format text --with-context
        When main() is called
        Then no error is raised and output is normal text (context flag is a no-op)
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, exit_code = self._capture_main(
                    ["--dir", ".", "--format", "text", "--with-context"]
                )
        self.assertEqual(exit_code, 0)
        self.assertGreater(len(out), 0, "Expected some text output")

    def test_with_context_markdown_has_no_context_block(self):
        """
        Given --format markdown --with-context
        When main() is called
        Then the output does not contain a raw JSON 'context' block
        (the flag is silently ignored for human formats)
        """
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = self._make_report()
                out, _ = self._capture_main(
                    ["--dir", ".", "--format", "markdown", "--with-context"]
                )
        self.assertNotIn('"context"', out)

    def test_json_with_context_is_ascii_safe(self):
        """
        Given --format json --with-context
        When main() is called
        Then the full output (including the new context block) is strict ASCII
        """
        captured = io.StringIO()
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("sys.stdout", captured):
                mock_load.return_value = _clean_config()
                main(["--dir", ".", "--format", "json", "--with-context"])
        out = captured.getvalue()
        non_ascii = [c for c in out if ord(c) >= 128]
        self.assertEqual(
            non_ascii, [], "Expected ASCII-only output with --with-context"
        )


class TestSecurityAuditClarity(unittest.TestCase):
    """The audit surfaces clarity (confusing-interaction) findings at LOW severity."""

    def test_confusing_interaction_appears_as_low_clarity_finding(self):
        """
        Given a config whose same-file allow is overlapped by a broader deny
        When security_audit() is called
        Then a finding with source 'clarity' and severity LOW is reported for the
            confusing interaction.
        """
        layer = ConfigLayer(
            provenance=_prov(),
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(uv run alembic upgrade:*)"],
                        "deny": ["Bash(uv run:*)"],
                        "ask": [],
                    }
                }
            ),
        )
        report = security_audit(Configuration(layers=(layer,), start_dir=None))
        clarity = [f for f in report.findings if f.source == "clarity"]
        self.assertEqual(len(clarity), 1)
        self.assertEqual(clarity[0].finding_id, "deny-shadows-allow")
        self.assertEqual(clarity[0].severity_label, "LOW")


class TestSecurityAuditEnvironment(unittest.TestCase):
    """The audit surfaces environment (PYTHONPATH-shadow) findings at HIGH severity -- silent by default, one finding when PYTHONPATH would shadow the installed hook."""

    def test_clean_config_and_no_pythonpath_has_no_environment_finding(self):
        """
        Given a clean configuration and an empty environment mapping
        When security_audit() is called with env={}
        Then no finding has source 'environment'
        """
        report = security_audit(_clean_config(), env={})
        environment = [f for f in report.findings if f.source == "environment"]
        self.assertEqual(environment, [])

    def test_shadowing_pythonpath_appears_as_high_environment_finding(self):
        """
        Given PYTHONPATH contains a directory holding its own toolguard/ package
        When security_audit() is called with that env
        Then a finding with source 'environment' and severity HIGH is reported
        """
        with tempfile.TemporaryDirectory() as d:
            pkg = Path(d) / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")

            report = security_audit(_clean_config(), env={"PYTHONPATH": d})

        environment = [f for f in report.findings if f.source == "environment"]
        self.assertEqual(len(environment), 1)
        self.assertEqual(environment[0].finding_id, "pythonpath-shadows-hook")
        self.assertEqual(environment[0].severity_label, "HIGH")
        self.assertIsNone(environment[0].tool)
        self.assertIsNone(environment[0].pattern)

    def test_default_env_none_reads_real_os_environ(self):
        """
        Given env is omitted (defaults to None) and the real PYTHONPATH is
        cleared by this module's setUpModule
        When security_audit() is called
        Then no environment finding is produced -- confirms the default
        argument genuinely delegates to os.environ rather than silently
        finding something on its own
        """
        report = security_audit(_clean_config())
        environment = [f for f in report.findings if f.source == "environment"]
        self.assertEqual(environment, [])


def _danger_finding(
    detector_id: str,
    pattern: str,
    *,
    remediation_kind=None,
    list_type: str = "allow",
    provenance=None,
) -> DangerFinding:
    """Build a DangerFinding for structured-remediation tests."""
    prov = provenance or Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/p/.claude/toolguard_hook.toml"),
        specificity=0,
    )
    return DangerFinding(
        detector_id=detector_id,
        severity=Severity.CRITICAL,
        tool="Bash",
        pattern=pattern,
        provenance=prov,
        rationale="danger",
        remediation="fix it",
        takeover_active=False,
        list_type=list_type,
        remediation_kind=remediation_kind,
    )


class TestStructuredRemediation(unittest.TestCase):
    """RankedFinding.remediation carries a structured, appliable proposal."""

    def test_remove_kind_builds_removal_edit(self):
        """
        Given a danger finding with remediation_kind='remove'
        When _danger_proposal builds its structured fix
        Then it is a 'remove' EditProposal deleting the flagged pattern at its
            locus, and applying it drops the rule from the config.
        """
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=Path("/p/.claude/toolguard_hook.toml"),
            specificity=0,
        )
        df = _danger_finding(
            "arbitrary-exec-allow",
            "uv run python:*",
            remediation_kind="remove",
            provenance=prov,
        )
        proposal = _danger_proposal(df)
        self.assertEqual(proposal.action, "remove")
        edit = proposal.edits[0]
        self.assertEqual(edit.removed_patterns, ("uv run python:*",))
        self.assertEqual(edit.added_patterns, ())
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(uv run python:*)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = Configuration(layers=(layer,), start_dir=None)
        result = apply_edits(config, [proposal])
        self.assertEqual(per_layer_rules(result, "Bash")[0].allow, ())

    def test_anchor_kind_builds_anchoring_replace(self):
        """
        Given a danger finding with remediation_kind='anchor' on an unanchored
            [regex] body
        When _danger_proposal builds its structured fix
        Then it is a 'replace' EditProposal swapping the body for a '^'-anchored one.
        """
        df = _danger_finding(
            "unanchored-regex-allow", "[regex]rm\\b", remediation_kind="anchor"
        )
        proposal = _danger_proposal(df)
        self.assertEqual(proposal.action, "replace")
        edit = proposal.edits[0]
        self.assertEqual(edit.removed_patterns, ("[regex]rm\\b",))
        self.assertEqual(edit.added_patterns, ("[regex]^rm\\b",))

    def test_anchor_on_already_anchored_returns_none(self):
        """
        Given an 'anchor' finding whose body is already anchored
        When _danger_proposal runs
        Then it returns None (nothing to change).
        """
        df = _danger_finding(
            "unanchored-regex-allow", "[regex]^rm\\b", remediation_kind="anchor"
        )
        self.assertIsNone(_danger_proposal(df))

    def test_anchor_on_non_regex_returns_none(self):
        """
        Given an 'anchor' finding whose body is not a [regex] pattern
        When _danger_proposal runs
        Then it returns None (anchor only applies to regex bodies).
        """
        df = _danger_finding(
            "unanchored-regex-allow", "rm -rf:*", remediation_kind="anchor"
        )
        self.assertIsNone(_danger_proposal(df))

    def test_no_kind_or_no_provenance_returns_none(self):
        """
        Given a finding with no remediation_kind, or one with no provenance
        When _danger_proposal runs
        Then it returns None in both cases (no mechanical fix to target).
        """
        self.assertIsNone(_danger_proposal(_danger_finding("x", "foo:*")))
        df = DangerFinding(
            detector_id="arbitrary-exec-allow",
            severity=Severity.CRITICAL,
            tool="Bash",
            pattern="foo:*",
            provenance=None,
            rationale="danger",
            remediation="fix it",
            takeover_active=False,
            list_type="allow",
            remediation_kind="remove",
        )
        self.assertIsNone(_danger_proposal(df))

    def test_json_carries_structured_proposal_and_string_text(self):
        """
        Given a config with an arbitrary-exec allow
        When the audit is rendered as JSON
        Then the finding's 'remediation' stays a human string AND
            'remediation_proposal' carries the structured removal edit.
        """
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=Path("/p/.claude/toolguard_hook.toml"),
            specificity=0,
        )
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(uv run python:*)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = Configuration(layers=(layer,), start_dir=None)
        report = security_audit(config)
        arb = [f for f in report.findings if f.finding_id == "arbitrary-exec-allow"][0]
        self.assertIsInstance(arb.remediation.text, str)
        self.assertIsNotNone(arb.remediation.proposal)
        self.assertEqual(arb.remediation.proposal.action, "remove")


class TestEditsReview(unittest.TestCase):
    """--edits audits the config AS IF the proposed edits were enacted."""

    def _dangerous_config(self):
        """A config with an arbitrary-exec allow (fires arbitrary-exec-allow)."""
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=Path("/p/.claude/toolguard_hook.toml"),
            specificity=0,
        )
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(uv run python:*)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        return Configuration(layers=(layer,), start_dir=None)

    def _capture_main(self, argv):
        """Run main(argv) capturing (stdout, exit_code)."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return buf.getvalue(), code

    def test_finding_delta_reports_resolved_and_introduced(self):
        """
        Given a base audit and an as-if-enacted audit that drops one finding
        When _finding_delta compares them
        Then the dropped finding is 'resolved' and none are 'introduced'.
        """
        config = self._dangerous_config()
        base = security_audit(config)
        removal = [
            f.remediation.proposal for f in base.findings if f.remediation.proposal
        ][0]
        proposed = security_audit(apply_edits(config, [removal]))
        delta = _finding_delta(base, proposed)
        self.assertIn(
            "arbitrary-exec-allow", [f["finding_id"] for f in delta["resolved"]]
        )
        self.assertEqual(delta["introduced"], [])

    def test_edits_flag_audits_proposed_state_and_adds_delta(self):
        """
        Given an --edits file with the audit's own removal proposal
        When main runs with --format json --edits FILE
        Then the top-level findings reflect the AS-IF-ENACTED config (the
            arbitrary-exec finding is gone) and context.proposed_edits.delta lists
            it as resolved.
        """
        config = self._dangerous_config()
        base = security_audit(config)
        removal = [
            f.remediation.proposal for f in base.findings if f.remediation.proposal
        ][0]
        with tempfile.TemporaryDirectory() as tmp:
            edits_path = Path(tmp) / "edits.json"
            edits_path.write_text(json.dumps([edit_proposal_to_dict(removal)]))
            with patch(
                "toolguard.tools.security_audit.load_config", return_value=config
            ):
                out, code = self._capture_main(
                    ["--dir", ".", "--format", "json", "--edits", str(edits_path)]
                )
        self.assertEqual(code, 0)
        data = json.loads(out)
        ids = [f["finding_id"] for f in data["findings"]]
        self.assertNotIn("arbitrary-exec-allow", ids)
        delta = data["context"]["proposed_edits"]["delta"]
        self.assertIn(
            "arbitrary-exec-allow", [f["finding_id"] for f in delta["resolved"]]
        )

    def test_malformed_edits_file_errors_out(self):
        """
        Given an --edits file that is not valid JSON
        When main runs
        Then argparse errors out (SystemExit) rather than crashing.
        """
        config = self._dangerous_config()
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{not json")
            with patch(
                "toolguard.tools.security_audit.load_config", return_value=config
            ):
                with self.assertRaises(SystemExit):
                    self._capture_main(["--dir", ".", "--edits", str(bad)])


class TestNoSecurityAcknowledgement(unittest.TestCase):
    """The #NOSECURITY tag acknowledges (labels + de-prioritizes) but never hides."""

    def _real_toml_layer(self, dir_path, allow_lines, allow_patterns):
        """Write a real toolguard_hook.toml (so comments can be recovered from disk) and return a matching ConfigLayer."""
        elements = "".join(f"    {ln}\n" for ln in allow_lines)
        text = "[permissions]\nallow = [\n" + elements + "]\ndeny = []\nask = []\n"
        path = Path(dir_path) / "toolguard_hook.toml"
        path.write_text(text, encoding="utf-8")
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=path,
            specificity=0,
        )
        return ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {"permissions": {"allow": allow_patterns, "deny": [], "ask": []}}
            ),
        )

    def test_nosecurity_rule_is_acknowledged_not_hidden(self):
        """
        Given a CRITICAL arbitrary-exec allow 'Bash(node:*)' carrying an inline
        '# NOSECURITY: intentional dev tool' comment
        When security_audit() runs
        Then the finding is STILL reported (not hidden), flagged acknowledged with
        the recovered reason
        """
        with tempfile.TemporaryDirectory() as d:
            layer = self._real_toml_layer(
                d,
                ["'Bash(node:*)',  # NOSECURITY: intentional dev tool"],
                ["Bash(node:*)"],
            )
            report = security_audit(_make_config(layer))
            exec_findings = [
                f for f in report.findings if f.finding_id == "arbitrary-exec-allow"
            ]
            self.assertEqual(len(exec_findings), 1)
            self.assertTrue(exec_findings[0].acknowledged)
            self.assertEqual(exec_findings[0].acknowledgement, "intentional dev tool")

    def test_untagged_dangerous_rule_is_not_acknowledged(self):
        """
        Given the same dangerous allow 'Bash(node:*)' but with NO #NOSECURITY comment
        When security_audit() runs
        Then the finding is not acknowledged (acknowledged False, reason None)
        """
        with tempfile.TemporaryDirectory() as d:
            layer = self._real_toml_layer(d, ["'Bash(node:*)',"], ["Bash(node:*)"])
            report = security_audit(_make_config(layer))
            exec_findings = [
                f for f in report.findings if f.finding_id == "arbitrary-exec-allow"
            ]
            self.assertEqual(len(exec_findings), 1)
            self.assertFalse(exec_findings[0].acknowledged)
            self.assertIsNone(exec_findings[0].acknowledgement)

    def test_acknowledged_finding_is_deprioritized_below_unacknowledged(self):
        """
        Given a CRITICAL arbitrary-exec rule tagged #NOSECURITY and a separate
        un-acknowledged MEDIUM unanchored-regex rule
        When security_audit() runs
        Then the un-acknowledged MEDIUM sorts BEFORE the acknowledged CRITICAL
        (acknowledgement de-prioritizes regardless of severity), yet both remain
        in the report
        """
        with tempfile.TemporaryDirectory() as d:
            layer = self._real_toml_layer(
                d,
                [
                    "'Bash(node:*)',  # NOSECURITY: blessed",
                    "'Bash([regex]rm)',",
                ],
                ["Bash(node:*)", "Bash([regex]rm)"],
            )
            report = security_audit(_make_config(layer))
            ack = [f for f in report.findings if f.acknowledged]
            unack_rule = [
                f for f in report.findings if f.source == "rule" and not f.acknowledged
            ]
            self.assertTrue(ack, "acknowledged CRITICAL should still be present")
            self.assertTrue(unack_rule, "un-acknowledged MEDIUM should be present")
            first_ack_index = min(report.findings.index(f) for f in ack)
            last_unack_index = max(report.findings.index(f) for f in unack_rule)
            self.assertLess(last_unack_index, first_ack_index)

    def test_json_output_carries_acknowledgement_fields(self):
        """
        Given a report whose finding is acknowledged via #NOSECURITY
        When main() renders it with --format json
        Then the serialized finding carries 'acknowledged' true and the
        'acknowledgement' reason
        """
        finding = RankedFinding(
            source="rule",
            finding_id="arbitrary-exec-allow",
            severity_value=4,
            severity_label="CRITICAL",
            tool="Bash",
            locus="project: /p/.claude/toolguard_hook.toml",
            pattern="node:*",
            summary="permits arbitrary code execution",
            impact="",
            remediation=Remediation(text="remove the rule", proposal=None),
            takeover_active=False,
            acknowledged=True,
            acknowledgement="intentional dev tool",
        )
        report = SecurityReport(
            findings=(finding,),
            takeover_active=False,
            highest_severity=4,
            counts={"CRITICAL": 1},
        )
        buf = io.StringIO()
        with patch("toolguard.tools.security_audit.load_config") as mock_load:
            with patch("toolguard.tools.security_audit.security_audit") as mock_sa:
                mock_load.return_value = MagicMock()
                mock_sa.return_value = report
                with contextlib.redirect_stdout(buf):
                    main(["--dir", ".", "--format", "json"])
        payload = json.loads(buf.getvalue())
        exec_json = [
            f for f in payload["findings"] if f["finding_id"] == "arbitrary-exec-allow"
        ]
        self.assertEqual(len(exec_json), 1)
        self.assertTrue(exec_json[0]["acknowledged"])
        self.assertEqual(exec_json[0]["acknowledgement"], "intentional dev tool")


def _ranked(finding_id, acknowledged=False, acknowledgement=None, pattern="git push:*"):
    """Build a RankedFinding for acknowledgement / delta rendering tests."""
    return RankedFinding(
        source="rule",
        finding_id=finding_id,
        severity_value=3,
        severity_label="HIGH",
        tool="Bash",
        locus="project: /fake/path.toml",
        pattern=pattern,
        summary="summary text",
        impact="",
        remediation=Remediation(text="remediation text", proposal=None),
        takeover_active=False,
        acknowledged=acknowledged,
        acknowledgement=acknowledgement,
    )


class TestAcknowledgementRendering(unittest.TestCase):
    """#NOSECURITY-acknowledged findings are still reported, but carry a visible acknowledgement marker in both render formats."""

    def test_acknowledgement_label_with_reason(self):
        """
        Given an acknowledged finding whose acknowledgement carries a reason
        When its label is rendered
        Then it reads '#NOSECURITY: <reason>'
        """
        f = _ranked("x", acknowledged=True, acknowledgement="trusted dev box")
        self.assertEqual(_acknowledgement_label(f), "#NOSECURITY: trusted dev box")

    def test_acknowledgement_label_without_reason(self):
        """
        Given an acknowledged finding with no reason text
        When its label is rendered
        Then it reads a bare '#NOSECURITY'
        """
        f = _ranked("x", acknowledged=True, acknowledgement=None)
        self.assertEqual(_acknowledgement_label(f), "#NOSECURITY")

    def test_markdown_render_shows_acknowledged_marker(self):
        """
        Given a report with one acknowledged finding
        When it is rendered as markdown
        Then the acknowledgement marker line is present
        """
        report = SecurityReport(
            findings=(_ranked("x", acknowledged=True, acknowledgement="ack me"),),
            takeover_active=False,
            highest_severity=3,
            counts={"HIGH": 1},
        )
        out = render(report, fmt="markdown")
        self.assertIn("acknowledged: #NOSECURITY: ack me", out)

    def test_text_render_shows_acknowledged_marker(self):
        """
        Given a report with one acknowledged finding
        When it is rendered as plain text
        Then the acknowledgement marker line is present
        """
        report = SecurityReport(
            findings=(_ranked("x", acknowledged=True, acknowledgement="ack me"),),
            takeover_active=False,
            highest_severity=3,
            counts={"HIGH": 1},
        )
        out = render(report, fmt="text")
        self.assertIn("acknowledged: #NOSECURITY: ack me", out)


class TestFindingDeltaAndBanner(unittest.TestCase):
    """The as-if-enacted (--edits) review computes a finding delta between the current and proposed audits and renders it as a banner."""

    def _report(self, *findings):
        return SecurityReport(
            findings=tuple(findings),
            takeover_active=False,
            highest_severity=3 if findings else 0,
            counts={},
        )

    def test_finding_delta_splits_introduced_and_resolved(self):
        """
        Given a base audit with finding A and a proposed audit with finding B
        When the finding delta is computed
        Then A is 'resolved' and B is 'introduced'
        """
        base = self._report(_ranked("A", pattern="a:*"))
        proposed = self._report(_ranked("B", pattern="b:*"))
        delta = _finding_delta(base, proposed)
        self.assertEqual([i["finding_id"] for i in delta["introduced"]], ["B"])
        self.assertEqual([r["finding_id"] for r in delta["resolved"]], ["A"])

    def test_finding_delta_unchanged_finding_is_neither(self):
        """
        Given a finding present in both base and proposed audits
        When the finding delta is computed
        Then it appears in neither 'introduced' nor 'resolved'
        """
        shared = _ranked("S", pattern="s:*")
        delta = _finding_delta(self._report(shared), self._report(shared))
        self.assertEqual(delta["introduced"], [])
        self.assertEqual(delta["resolved"], [])

    def test_render_edit_banner_lists_delta(self):
        """
        Given proposals and a delta with one introduced and one resolved finding
        When the banner is rendered
        Then it reports the counts and lists both findings in ASCII
        """
        base = self._report(_ranked("A", pattern="a:*"))
        proposed = self._report(_ranked("B", pattern="b:*"))
        delta = _finding_delta(base, proposed)
        proposals = [
            EditProposal(action="replace", tool="Bash", rationale="r", edits=())
        ]
        banner = _render_edit_banner(proposals, delta)
        self.assertIn("AS-IF-ENACTED REVIEW", banner)
        self.assertIn("as if 1 proposed edit(s)", banner)
        self.assertIn("+ INTRODUCED B", banner)
        self.assertIn("- resolved   A", banner)
        self.assertTrue(all(ord(c) < 128 for c in banner))


if __name__ == "__main__":
    unittest.main()
