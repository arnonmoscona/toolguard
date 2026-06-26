"""
Unit tests for toolguard.tools.security_audit -- unified security audit aggregator.

Tests cover:
- Empty/clean config -> no findings, highest_severity=0, "No security findings" rendered
- Danger findings only -> source="rule", correct field mapping
- Takeover audit findings only -> source="takeover"
- Mixed danger+takeover -> combined list sorted severity DESC
- takeover_active reflected in report and render banner
- counts dict correctness
- render output is ASCII-only (markdown and text)
- JSON format produces parseable JSON with documented keys
- --strict exit code: 0 on clean, highest_severity on findings
- locus populated from provenance.describe_brief when finding has provenance

Fixture helpers are reused from test_tools_danger.py and test_tools_takeover_audit.py
patterns: MappingProxyType layers built directly from Configuration/ConfigLayer/Provenance.
"""

import io
import json
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
    SecurityReport,
    main,
    render,
    security_audit,
)


# ---------------------------------------------------------------------------
# Fixture helpers (mirroring test_tools_danger.py and test_tools_takeover_audit.py)
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
) -> ConfigLayer:
    """Build a toolguard_hook ConfigLayer with the given settings."""
    content: dict = {}

    if governed_tools is not None:
        content["governed_tools"] = governed_tools

    takeover_section: dict = {"no_match_fallback": no_match_fallback}
    if takeover_enabled is not None:
        takeover_section["enabled"] = takeover_enabled
    if ignored_allow_patterns is not None:
        takeover_section["ignored_allow_patterns"] = ignored_allow_patterns
    # takeover_section always carries at least no_match_fallback, so it is
    # always attached.
    content["takeover_mode"] = takeover_section

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


def _danger_allow_layer(tool: str, allow: List[str], specificity: int = 0) -> ConfigLayer:
    """
    Build a toolguard_hook layer with dangerous allow patterns for ``tool``.

    Wraps each pattern in ``Tool(inner)`` form, as stored in real configs.
    """
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
    """
    Return a Configuration that produces NO findings from either analyser.

    - One governed tool (Bash) with hook registered in native settings.
    - No dangerous allow patterns.
    - no_match_fallback='deny', takeover OFF, no conflicts.
    """
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    native_layer = _native_layer(hooks=_hooks_for("Bash"))
    return _make_config(tg_layer, native_layer)


def _danger_only_config() -> Configuration:
    """
    Return a Configuration that produces danger (rule) findings only.

    - Bash allowed to run 'uv run python:*' (triggers arbitrary-exec-allow CRITICAL).
    - Hook properly registered for Bash -> no takeover audit findings.
    """
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    # Dangerous allow rule in a separate toolguard layer
    danger_layer = _danger_allow_layer("Bash", ["uv run python:*"])
    native_layer = _native_layer(hooks=_hooks_for("Bash"))
    return _make_config(tg_layer, danger_layer, native_layer)


def _takeover_only_config() -> Configuration:
    """
    Return a Configuration that produces takeover audit findings only.

    - Governed tool Bash with NO hook registered -> hook-not-registered (CRITICAL).
    - No dangerous allow patterns -> no danger findings.
    """
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    # No native layer with hooks
    return _make_config(tg_layer)


def _mixed_config() -> Configuration:
    """
    Return a Configuration that produces BOTH danger and takeover audit findings.

    - Dangerous allow rule (arbitrary-exec-allow CRITICAL from danger).
    - No hook registered for Bash (hook-not-registered CRITICAL from takeover audit).
    """
    tg_layer = _toolguard_layer(
        governed_tools=["Bash"],
        no_match_fallback="deny",
    )
    danger_layer = _danger_allow_layer("Bash", ["uv run python:*"])
    # No native layer with hooks
    return _make_config(tg_layer, danger_layer)


def _takeover_on_config() -> Configuration:
    """
    Return a Configuration with takeover mode ON.

    - Bash governed, hook registered, takeover enabled.
    - No dangerous rules, so report shows takeover_active=True with no findings.
    """
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


def _locus_config() -> Configuration:
    """
    Return a Configuration that produces a takeover finding WITH provenance.

    Uses a custom tool name (mcp__custom__tool) that is NOT in the default
    ignored_allow_patterns.  With takeover ON and the blanket allow
    ``mcp__custom__tool(*)`` present in native settings but absent from the
    ignored set, audit_takeover emits an ``uncovered-blanket-allow`` finding
    whose provenance points to the native layer.

    Note: Bash(*) is ALWAYS in the default ignored set, so it would never
    produce an uncovered-blanket-allow finding regardless of configuration.
    """
    # Govern only our custom tool; hook is registered, so no hook-not-registered.
    tg_layer = _toolguard_layer(
        governed_tools=["mcp__custom__tool"],
        takeover_enabled=True,
        no_match_fallback="deny",
        # Explicitly empty -- defaults cover Bash/Read/Write/Edit but NOT mcp__custom__tool
        ignored_allow_patterns=[],
    )
    native_layer = _native_layer(
        allow=["mcp__custom__tool(*)"],   # blanket allow NOT in ignored set
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
            self.assertIsNotNone(f.pattern, msg=f"Expected pattern set, got None in {f!r}")

    def test_impact_empty_for_rule_findings(self):
        """
        Given danger findings (source='rule')
        When security_audit() is called
        Then impact is an empty string (danger findings embed impact in rationale)
        """
        for f in self.report.findings:
            self.assertEqual(f.impact, "", msg=f"Expected empty impact for rule finding {f!r}")

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
            self.assertGreater(len(f.impact), 0, msg=f"Expected non-empty impact in {f!r}")


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
        # The mixed fixture must yield at least two CRITICAL findings spanning
        # both sources, otherwise this ordering test would be vacuous.
        self.assertGreaterEqual(
            len(critical), 2, msg="fixture must produce >=2 CRITICAL findings"
        )
        self.assertIn("rule", {f.source for f in critical})
        self.assertIn("takeover", {f.source for f in critical})
        # Within the same severity, findings are ordered by source ascending.
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
        # Only present labels should be in counts
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
        data = json.loads(out)  # raises if invalid
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
            remediation="remediation text",
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
            "source", "finding_id", "severity_value", "severity_label",
            "tool", "locus", "pattern", "summary", "impact",
            "remediation", "takeover_active",
        ]
        for field in expected_fields:
            self.assertIn(field, fd, msg=f"Missing field in JSON finding: {field}")

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
        # The danger layer has provenance level="project", path="/fake/.claude/toolguard_hook.toml"
        expected_locus = "project: /fake/.claude/toolguard_hook.toml"
        # At least one rule finding should carry this locus
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
        self.assertGreater(len(uncovered), 0, "Expected uncovered-blanket-allow finding")
        # Native layer provenance: level="project", path="/fake/.claude/settings.local.json"
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
        self.assertGreater(len(hook_findings), 0, "Expected hook-not-registered finding")
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
        """
        Run main() with --format json --with-context using either a real config
        function or mocked objects, and return the parsed JSON dict.
        """
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
        self.assertIn("context", data, "Expected 'context' key in JSON with --with-context")

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
            self.assertIn(key, data, f"Existing key '{key}' is missing with --with-context")

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
        # The markdown should not contain a raw JSON "context" key block
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
        self.assertEqual(non_ascii, [], "Expected ASCII-only output with --with-context")


if __name__ == "__main__":
    unittest.main()
