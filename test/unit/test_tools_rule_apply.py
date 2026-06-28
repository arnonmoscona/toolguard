"""
Unit tests for toolguard.tools.rule_apply -- applying consolidation proposals to
config files and producing a structured change report.

Tests cover:
- TOML apply: originals removed, consolidated rule added, file written.
- Dry run: diff produced but nothing written.
- Comment / single-quoted-literal / other-rule preservation through a rewrite.
- JSON apply.
- Config drift: a proposal whose patterns are absent is skipped, not applied.
- Multiple proposals targeting one file.
- Missing file path is reported as a skip.
- render_change_report formatting and invalid-format handling.
"""

import json
import tempfile
import unittest
from pathlib import Path

from toolguard.config import Provenance
from toolguard.tools.consolidate import ConsolidationProposal
from toolguard.tools.rule_apply import (
    apply_proposals,
    render_change_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prov(path, file_format: str = "toml") -> Provenance:
    """Build a Provenance pointing at a real (temp) config file."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format=file_format,
        path=path,
        specificity=0,
    )


def _git_family_proposal(prov: Provenance) -> ConsolidationProposal:
    """A literal-alternation proposal consolidating git diff/status."""
    return ConsolidationProposal(
        kind="literal-alternation",
        tool="Bash",
        list_type="allow",
        layer_provenance=prov,
        removed_patterns=("git diff:*", "git status:*"),
        added_pattern="[regex]^git (diff|status)",
        rationale="alternation at token 1",
        replay_summary="probes unchanged; no corpus",
    )


_TOML_WITH_FIND = (
    "[permissions]\n"
    "allow = [\n"
    '  "Bash(git diff:*)",\n'
    '  "Bash(git status:*)",\n'
    "  # find guard (single-quoted literal)\n"
    "  'Bash([regex]\\bfind\\b(?!.*-exec))',\n"
    '  "Bash(ls:*)",\n'
    "]\n"
)


class _TempConfigMixin:
    """Provides a per-test temporary directory and a config-file factory."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)

    def _write(self, name: str, text: str) -> Path:
        path = self.tmpdir / name
        path.write_text(text)
        return path

    def _write_json(self, name: str, permissions: dict) -> Path:
        path = self.tmpdir / name
        path.write_text(json.dumps({"permissions": permissions}, indent=2) + "\n")
        return path


# ---------------------------------------------------------------------------
# TOML apply
# ---------------------------------------------------------------------------


class TestApplyToml(_TempConfigMixin, unittest.TestCase):
    """Applying an allow-list consolidation to a TOML config."""

    def test_consolidation_applied_and_written(self):
        """
        Given a TOML config with git diff/status allow rules and a matching proposal
        When apply_proposals runs (not dry)
        Then the originals are removed, the consolidated regex is present, and the
             file is reported as written.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        text = cfg.read_text()
        self.assertNotIn("Bash(git diff:*)", text)
        self.assertNotIn("Bash(git status:*)", text)
        self.assertIn("Bash([regex]^git (diff|status))", text)
        self.assertEqual(report.total_applied, 1)
        self.assertEqual(report.total_skipped, 0)
        self.assertEqual(len(report.files_written), 1)
        self.assertTrue(report.files[0].written)

    def test_single_quoted_literal_and_other_rules_preserved(self):
        """
        Given a TOML config whose allow list also has a single-quoted find guard,
              a comment, and an unrelated 'Bash(ls:*)' rule
        When a git-family consolidation is applied
        Then the single-quoted find rule (verbatim), its comment, and 'Bash(ls:*)'
             all survive the rewrite.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        apply_proposals([_git_family_proposal(_prov(cfg))])

        text = cfg.read_text()
        self.assertIn("'Bash([regex]\\bfind\\b(?!.*-exec))',", text)
        self.assertIn("# find guard (single-quoted literal)", text)
        self.assertIn('"Bash(ls:*)",', text)

    def test_dry_run_writes_nothing_but_reports_diff(self):
        """
        Given a TOML config and a matching proposal
        When apply_proposals runs with dry_run=True
        Then the file on disk is unchanged, but the report still marks the proposal
             applied and carries a non-empty unified diff, with written=False.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        before = cfg.read_text()
        report = apply_proposals([_git_family_proposal(_prov(cfg))], dry_run=True)

        self.assertEqual(cfg.read_text(), before)
        self.assertEqual(report.total_applied, 1)
        self.assertEqual(len(report.files_written), 0)
        self.assertFalse(report.files[0].written)
        self.assertIn("Bash([regex]^git (diff|status))", report.files[0].diff)


# ---------------------------------------------------------------------------
# JSON apply
# ---------------------------------------------------------------------------


class TestApplyJson(_TempConfigMixin, unittest.TestCase):
    """Applying an allow-list consolidation to a JSON config."""

    def test_consolidation_applied_to_json(self):
        """
        Given a JSON config with git diff/status allow rules and a matching proposal
        When apply_proposals runs
        Then the JSON permissions.allow list drops the originals and gains the
             consolidated regex, and the file remains valid JSON.
        """
        cfg = self._write_json(
            "toolguard_hook.json",
            {"allow": ["Bash(git diff:*)", "Bash(git status:*)", "Bash(ls:*)"]},
        )
        apply_proposals([_git_family_proposal(_prov(cfg, "json"))])

        data = json.loads(cfg.read_text())
        allow = data["permissions"]["allow"]
        self.assertNotIn("Bash(git diff:*)", allow)
        self.assertNotIn("Bash(git status:*)", allow)
        self.assertIn("Bash([regex]^git (diff|status))", allow)
        self.assertIn("Bash(ls:*)", allow)


# ---------------------------------------------------------------------------
# Config drift / skips
# ---------------------------------------------------------------------------


class TestDriftAndSkips(_TempConfigMixin, unittest.TestCase):
    """Proposals that cannot be safely applied are skipped and reported."""

    def test_missing_pattern_is_skipped_not_applied(self):
        """
        Given a TOML config that does NOT contain the proposal's removed patterns
        When apply_proposals runs
        Then the proposal is skipped with a 'not found' reason, nothing is applied,
             and the file is not written.
        """
        cfg = self._write(
            "toolguard_hook.toml",
            '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n',
        )
        before = cfg.read_text()
        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 0)
        self.assertEqual(report.total_skipped, 1)
        self.assertIn("not found", report.files[0].skipped[0][1])
        self.assertEqual(cfg.read_text(), before)
        self.assertFalse(report.files[0].written)

    def test_missing_file_path_is_skipped(self):
        """
        Given a proposal whose provenance has no file path (path=None)
        When apply_proposals runs
        Then the proposal is skipped with a 'no file path' reason and nothing is written.
        """
        prov = _prov(None)
        report = apply_proposals([_git_family_proposal(prov)])

        self.assertEqual(report.total_applied, 0)
        self.assertEqual(report.total_skipped, 1)
        self.assertIn("no file path", report.files[0].skipped[0][1])
        self.assertEqual(len(report.files_written), 0)


# ---------------------------------------------------------------------------
# Multiple proposals on one file
# ---------------------------------------------------------------------------


class TestMultipleProposalsSameFile(_TempConfigMixin, unittest.TestCase):
    """Two proposals targeting one file are both applied in a single rewrite."""

    def test_alternation_and_subsumption_both_applied(self):
        """
        Given a TOML config with the git family plus a subsumed mkdir rule
        When a literal-alternation proposal and a static-subsumption (pure drop)
             proposal target the same file
        Then both apply: the git family becomes one regex and the subsumed mkdir
             rule is dropped, and the file is written once.
        """
        cfg = self._write(
            "toolguard_hook.toml",
            (
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(git diff:*)",\n'
                '  "Bash(git status:*)",\n'
                '  "Bash(mkdir -p /tmp/:*)",\n'
                '  "Bash(mkdir -p /tmp/claude-code:*)",\n'
                "]\n"
            ),
        )
        prov = _prov(cfg)
        alternation = _git_family_proposal(prov)
        subsumption = ConsolidationProposal(
            kind="static-subsumption",
            tool="Bash",
            list_type="allow",
            layer_provenance=prov,
            removed_patterns=("mkdir -p /tmp/claude-code:*",),
            added_pattern=None,
            rationale="subsumed by mkdir -p /tmp/:*",
            replay_summary="static proof",
        )

        report = apply_proposals([alternation, subsumption])
        text = cfg.read_text()

        self.assertIn("Bash([regex]^git (diff|status))", text)
        self.assertNotIn("Bash(mkdir -p /tmp/claude-code:*)", text)
        self.assertIn("Bash(mkdir -p /tmp/:*)", text)
        self.assertEqual(report.total_applied, 2)
        self.assertEqual(len(report.files_written), 1)


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


class TestRenderChangeReport(_TempConfigMixin, unittest.TestCase):
    """render_change_report produces an ASCII summary and validates its format."""

    def test_text_report_lists_applied_change(self):
        """
        Given a report from a successful git-family consolidation
        When render_change_report(fmt='text') is called
        Then the output names the file and shows the removed -> added change.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        report = apply_proposals([_git_family_proposal(_prov(cfg))])
        out = render_change_report(report, fmt="text")

        self.assertIn("toolguard_hook.toml", out)
        self.assertIn("1 applied", out)
        self.assertIn("literal-alternation", out)
        self.assertIn("Bash([regex]^git (diff|status))", out)

    def test_markdown_report_uses_headings(self):
        """
        Given a report
        When render_change_report(fmt='markdown') is called
        Then the output uses markdown headings.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        report = apply_proposals([_git_family_proposal(_prov(cfg))])
        out = render_change_report(report, fmt="markdown")

        self.assertIn("# Toolguard Rule Change Report", out)
        self.assertIn("## ", out)

    def test_invalid_format_raises_value_error(self):
        """
        Given any report
        When render_change_report is called with an unknown format
        Then it raises ValueError.
        """
        report = apply_proposals([])
        with self.assertRaises(ValueError):
            render_change_report(report, fmt="xml")


if __name__ == "__main__":
    unittest.main()
