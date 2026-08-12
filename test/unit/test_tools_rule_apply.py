"""
Unit tests for toolguard.tools.rule_apply: applying consolidation proposals
to config files and producing a structured change report.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.config import Provenance
from toolguard.config_write_guard import ConfigWriteVerificationError
from toolguard.tools.consolidate import ConsolidationProposal
from toolguard.tools.rule_apply import (
    _read_raw_permissions,
    apply_proposals,
    render_change_report,
)


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

    def test_real_write_routes_through_verified_write_config(self):
        """
        Given a TOML config with a matching consolidation proposal (not dry-run)
        When apply_proposals runs
        Then toolguard.tools.rule_apply.verified_write_config is called with the
             real target path, file_format="toml", and expected_patterns covering
             every pattern in the newly-consolidated allow list (the final
             real-file write must go through the same self-protection gate
             as the writer functions it reuses)
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        with patch("toolguard.tools.rule_apply.verified_write_config") as mock_write:
            apply_proposals([_git_family_proposal(_prov(cfg))])

        mock_write.assert_called_once()
        args, kwargs = mock_write.call_args
        self.assertEqual(args[0], cfg)
        self.assertEqual(args[2], "toml")
        self.assertIn("Bash([regex]^git (diff|status))", kwargs["expected_patterns"])
        self.assertIn("Bash(ls:*)", kwargs["expected_patterns"])

    def test_refused_write_propagates_and_reports_unwritten(self):
        """
        Given verified_write_config() raising ConfigWriteVerificationError
             (simulating a would-be corrupting write)
        When apply_proposals runs (not dry-run)
        Then the error propagates out of apply_proposals rather than being
             swallowed, and the real file on disk is left completely unchanged
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        before = cfg.read_text()
        with patch(
            "toolguard.tools.rule_apply.verified_write_config",
            side_effect=ConfigWriteVerificationError(cfg, "invalid TOML", "boom"),
        ):
            with self.assertRaises(ConfigWriteVerificationError):
                apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(cfg.read_text(), before)

    def test_apply_survives_an_unrelated_malformed_structured_entry(self):
        """
        Given a TOML config whose allow list ALSO contains a structured entry
             missing its "match" key, elsewhere in the same file
        When a git-family consolidation targeting the OTHER rules is applied
        Then the write succeeds (no ConfigWriteVerificationError) and the
             malformed entry survives verbatim -- expected_patterns must not
             include a synthesized pattern for an entry that can never
             appear in the written text
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            '  { additionalContext = "oops" },\n'
            '  "Bash(ls:*)",\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", text)
        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertTrue(report.files[0].written)
        written_text = cfg.read_text()
        self.assertIn("Bash([regex]^git (diff|status))", written_text)
        self.assertIn('{ additionalContext = "oops" }', written_text)


class TestStructuredEntrySurvivesUnrelatedEdit(_TempConfigMixin, unittest.TestCase):
    """A structured entry elsewhere in the allow list must round-trip byte-identical through an edit targeting a different rule."""

    def test_structured_entry_untouched_by_unrelated_consolidation(self):
        """
        Given a TOML allow list with a structured entry (with its own leading
             comment) plus the git diff/status rules a consolidation proposal
             targets
        When apply_proposals consolidates ONLY the git family
        Then the structured entry's original line and its leading comment
             survive byte-identical, while the git rules are still replaced
        """
        # "Bash(ls:*)" is listed FIRST: a comment_block preceding the very
        # first rule in a subsection anchors to the section top rather than
        # to that rule, so without a rule ahead of it the structured entry's
        # own comment would attach to the wrong place and this test's
        # "travels with the rule when re-sorted" assertion would be vacuous.
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls:*)",\n'
            "  # keep an eye on this one\n"
            '  { match = "Bash(rm -rf:*)", additionalContext = "dangerous" },\n'
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])
        text = cfg.read_text()

        self.assertIn(
            "  # keep an eye on this one\n"
            '  { match = "Bash(rm -rf:*)", additionalContext = "dangerous" },\n',
            text,
        )
        self.assertNotIn("Bash(git diff:*)", text)
        self.assertNotIn("Bash(git status:*)", text)
        self.assertIn("Bash([regex]^git (diff|status))", text)
        self.assertEqual(report.total_applied, 1)


def _rule_entry_metadata(path: Path, file_format: str, list_type: str, pattern: str):
    """Read back one entry's metadata dict from a config file on disk, by pattern."""
    raw = _read_raw_permissions(path, file_format)
    for entry in raw[list_type]:
        if entry.pattern == pattern:
            return dict(entry.metadata)
    return None


class TestEnrichmentGuard(_TempConfigMixin, unittest.TestCase):
    """A proposal is refused, whole, rather than silently dropping rule enrichment."""

    _CONSOLIDATED = "Bash([regex]^git (diff|status))"

    def test_contradiction_is_skipped_and_file_is_byte_unchanged(self):
        """
        Given a TOML allow list where the proposal's own consolidated pattern
             ALREADY exists twice, as two structured entries disagreeing on
             the same metadata key (a genuine merge_entries case-3
             contradiction)
        When apply_proposals runs the git-family consolidation
        Then the proposal is skipped with a "would lose rule enrichment"
             reason, nothing is applied, and the file is byte-for-byte
             unchanged on disk (never apply-and-drop)
        """
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepB" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)
        before = cfg.read_text()

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 0)
        self.assertEqual(report.total_skipped, 1)
        self.assertIn("would lose rule enrichment", report.files[0].skipped[0][1])
        self.assertEqual(cfg.read_text(), before)
        self.assertFalse(report.files[0].written)

    def test_clean_union_applies_with_merged_metadata(self):
        """
        Given a TOML allow list where the proposal's own consolidated pattern
             ALREADY exists twice, as two structured entries with DISJOINT
             metadata keys (a compatible merge_entries case-2 union)
        When apply_proposals runs the git-family consolidation
        Then the proposal applies, the git diff/status originals are removed,
             and exactly ONE entry survives for the consolidated pattern,
             carrying the UNION of both entries' metadata
        """
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{self._CONSOLIDATED}", owner = "bob" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertTrue(report.files[0].written)
        text = cfg.read_text()
        self.assertNotIn("Bash(git diff:*)", text)
        self.assertNotIn("Bash(git status:*)", text)
        self.assertEqual(text.count(f'match = "{self._CONSOLIDATED}"'), 1)

        metadata = _rule_entry_metadata(cfg, "toml", "allow", self._CONSOLIDATED)
        self.assertEqual(metadata, {"additionalContext": "keepA", "owner": "bob"})

    def test_bare_vs_structured_same_pattern_applies_no_guard(self):
        """
        Given a TOML allow list where the proposal's own consolidated pattern
             already exists ONCE, as a single structured entry (case 1: bare
             vs. structured, same pattern)
        When apply_proposals runs the git-family consolidation (which would
             otherwise add a bare duplicate for that same pattern)
        Then the proposal applies without being refused (case 1 has no
             conflict), and the pre-existing structured entry's metadata
             survives untouched, appearing exactly once
        """
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepA" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertEqual(report.total_skipped, 0)
        text = cfg.read_text()
        self.assertEqual(text.count(f'match = "{self._CONSOLIDATED}"'), 1)

        metadata = _rule_entry_metadata(cfg, "toml", "allow", self._CONSOLIDATED)
        self.assertEqual(metadata, {"additionalContext": "keepA"})

    def test_unrelated_enriched_entry_untouched_dict_preserved(self):
        """
        Given a TOML allow list holding an UNRELATED structured entry (its own
             pattern, own metadata) alongside the plain git diff/status rules
             a consolidation proposal targets
        When apply_proposals consolidates ONLY the git family (a proposal
             touching plain entries only -- the unrelated entry's pattern is
             never part of removed_patterns or added_pattern)
        Then the proposal applies normally and the unrelated entry's metadata
             dict, read back from disk, is exactly preserved (not merely a
             text substring match)
        """
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls:*)",\n'
            '  { match = "Bash(rm -rf:*)", additionalContext = "dangerous" },\n'
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertEqual(report.total_skipped, 0)
        metadata = _rule_entry_metadata(cfg, "toml", "allow", "Bash(rm -rf:*)")
        self.assertEqual(metadata, {"additionalContext": "dangerous"})

    def test_skip_reason_visible_in_change_report(self):
        """
        Given a proposal refused by the enrichment guard (case-3 contradiction)
        When render_change_report renders the resulting ChangeReport
        Then the "would lose rule enrichment" reason text a caller would see
             is present in the rendered output, not only on the internal
             FileChange.skipped tuple
        """
        toml_content = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(git diff:*)",\n'
            '  "Bash(git status:*)",\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{self._CONSOLIDATED}", additionalContext = "keepB" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])
        out = render_change_report(report, fmt="text")

        self.assertIn("would lose rule enrichment", out)


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
