"""
Unit tests for the maintenance aggregator (toolguard.tools.maintenance).

These verify that run_maintenance composes the individual maintenance engines into
a single structured report, and that render produces a readable summary.  Local
fixture helpers mirror the other maintenance-tool tests for consistency.
"""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.maintenance import (
    MaintenanceReport,
    run_maintenance,
    render,
)


def _make_provenance(specificity: int = 0) -> Provenance:
    """Build a minimal project-level Provenance for tests."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """Build a ConfigLayer with wrapped allow/deny/ask bodies for ``tool``."""
    provenance = provenance or _make_provenance()
    prefix = f"{tool}("
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"{prefix}{p})" for p in (allow or [])],
                "deny": [f"{prefix}{p})" for p in (deny or [])],
                "ask": [f"{prefix}{p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=provenance, content=content)


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _make_log_entry(tool: str, command: str) -> LogEntry:
    """Build an EXECUTED LogEntry for the corpus."""
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool=tool,
        command=command,
        status="EXECUTED",
        rule_text=None,
        agent="main",
        log_file=None,
    )


class TestRunMaintenance(unittest.TestCase):
    """Aggregation of the maintenance engines into a single report."""

    def test_aggregates_consolidations_and_broadenings_for_a_tool(self):
        """
        Given a Bash config with a consolidatable git-family allow set
        When run_maintenance is called
        Then the Bash tool report carries both strict consolidations and
            agent-judged broadenings, and the report reports findings.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        self.assertEqual(len(report.tools), 1)
        bash = report.tools[0]
        self.assertEqual(bash.tool, "Bash")
        self.assertTrue(bash.consolidations)
        self.assertTrue(bash.broadenings)
        self.assertTrue(report.has_any_findings)

    def test_restricts_to_requested_tools(self):
        """
        Given a config and an explicit single-tool request
        When run_maintenance is called with tools=['Bash']
        Then only the Bash tool is inspected (no Read/Write/Edit entries).
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        self.assertEqual([t.tool for t in report.tools], ["Bash"])

    def test_mining_included_when_corpus_supplied(self):
        """
        Given a corpus with an executed command the config does not allow
        When run_maintenance is called with that corpus
        Then the report's mining section contains at least one candidate group.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        report = run_maintenance(config, tools=["Bash"], corpus=corpus)
        self.assertTrue(report.mining.groups)

    def test_empty_config_reports_no_findings(self):
        """
        Given a config with no rules
        When run_maintenance is called and the report is rendered
        Then has_any_findings is False and the rendered summary says so.
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        report = run_maintenance(config, tools=["Bash"])
        self.assertFalse(report.has_any_findings)
        self.assertIn("No maintenance findings", render(report))


class TestRenderMaintenance(unittest.TestCase):
    """Rendering of the aggregate maintenance summary."""

    def test_render_lists_headline_and_tool_section(self):
        """
        Given a report with Bash findings
        When render is called in markdown
        Then the output carries the headline counts and a Bash section naming a
            broadening proposal.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        out = render(report, "markdown")
        self.assertIsInstance(report, MaintenanceReport)
        self.assertIn("Maintenance summary", out)
        self.assertIn("Bash", out)
        self.assertIn("broaden", out)


if __name__ == "__main__":
    unittest.main()
