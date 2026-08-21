"""
Unit tests for toolguard.tools.rule_apply: applying consolidation proposals
to config files and producing a structured change report.
"""

import json
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard.config import Provenance
from toolguard.config_write_guard import ConfigWriteVerificationError
from toolguard.tools.consolidate import ConsolidationProposal, SafetyResult
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


def _lists_on_disk(path: Path, file_format: str = "toml") -> dict:
    """
    Read a config file's allow/deny/ask pattern lists straight off disk.

    Parses with ``tomllib``/``json`` rather than toolguard's own reader, so a
    placement assertion cannot pass because the read and the write share a bug.
    Structured entries contribute their ``match`` value.
    """
    text = path.read_text()
    data = json.loads(text) if file_format == "json" else tomllib.loads(text)
    perms = data.get("permissions", {})
    return {
        list_type: [
            entry.get("match") if isinstance(entry, dict) else entry
            for entry in (perms.get(list_type, []) or [])
        ]
        for list_type in ("allow", "deny", "ask")
    }


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

#: The git family plus a populated deny and ask list. A consolidation touches
#: `allow` only, so the other two lists are the negative case for every
#: "was anything else disturbed?" question.
_TOML_THREE_LISTS = (
    "[permissions]\n"
    "allow = [\n"
    '  "Bash(git diff:*)",\n'
    '  "Bash(git status:*)",\n'
    '  "Bash(ls:*)",\n'
    "]\n"
    "deny = [\n"
    '  "Bash(rm -rf /:*)",\n'
    "]\n"
    "ask = [\n"
    '  "Bash(curl:*)",\n'
    "]\n"
)

_JSON_THREE_LISTS = {
    "allow": ["Bash(git diff:*)", "Bash(git status:*)", "Bash(ls:*)"],
    "deny": ["Bash(rm -rf /:*)"],
    "ask": ["Bash(curl:*)"],
}

_CONSOLIDATED = "Bash([regex]^git (diff|status))"


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
        Then the resulting allow list on disk is EXACTLY the two untouched rules
             plus the consolidated regex -- no duplicate, no survivor, nothing
             displaced into deny or ask -- and the file is reported as written.
        """
        cfg = self._write("toolguard_hook.toml", _TOML_WITH_FIND)
        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        text = cfg.read_text()
        self.assertNotIn("Bash(git diff:*)", text)
        self.assertNotIn("Bash(git status:*)", text)

        # The whole list, not a substring: an `assertIn` over the file text is
        # satisfied by the pattern appearing in ANY list (proposed ticket 39).
        lists = _lists_on_disk(cfg)
        self.assertEqual(
            sorted(lists["allow"]),
            sorted(
                [
                    _CONSOLIDATED,
                    "Bash([regex]\\bfind\\b(?!.*-exec))",
                    "Bash(ls:*)",
                ]
            ),
        )
        self.assertEqual(lists["deny"], [])
        self.assertEqual(lists["ask"], [])

        self.assertEqual(report.total_applied, 1)
        self.assertEqual(report.total_skipped, 0)
        self.assertEqual(len(report.files_written), 1)
        self.assertTrue(report.files[0].written)
        self.assertEqual(
            report.files[0].patterns_removed,
            ("Bash(git diff:*)", "Bash(git status:*)"),
        )
        self.assertEqual(report.files[0].patterns_added, (_CONSOLIDATED,))

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
             real target path, file_format="toml", the exact text that would be
             written, and an expected_patterns set holding every surviving
             pattern from ALL THREE lists (the final real-file write must go
             through the same self-protection gate as the writer functions it
             reuses)
        """
        cfg = self._write("toolguard_hook.toml", _TOML_THREE_LISTS)
        with patch("toolguard.tools.rule_apply.verified_write_config") as mock_write:
            apply_proposals([_git_family_proposal(_prov(cfg))])

        mock_write.assert_called_once()
        args, kwargs = mock_write.call_args
        self.assertEqual(args[0], cfg)
        self.assertEqual(args[2], "toml")

        # The text handed to the guard is the whole point of the call; parsing
        # it proves the consolidated rule is being written as an ALLOW.
        candidate = tomllib.loads(args[1])["permissions"]
        self.assertEqual(
            sorted(candidate["allow"]), sorted([_CONSOLIDATED, "Bash(ls:*)"])
        )
        self.assertEqual(candidate["deny"], ["Bash(rm -rf /:*)"])
        self.assertEqual(candidate["ask"], ["Bash(curl:*)"])

        # Exact set, so a guard narrowed to one list is visible here. It is a
        # flat set of bare patterns and carries no list identity, which is why
        # a rule MOVED between lists still verifies (proposed ticket 39).
        self.assertEqual(
            sorted(kwargs["expected_patterns"]),
            sorted(
                [
                    _CONSOLIDATED,
                    "Bash(ls:*)",
                    "Bash(rm -rf /:*)",
                    "Bash(curl:*)",
                ]
            ),
        )

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
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepB" }},\n'
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
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{_CONSOLIDATED}", owner = "bob" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertTrue(report.files[0].written)
        text = cfg.read_text()
        self.assertNotIn("Bash(git diff:*)", text)
        self.assertNotIn("Bash(git status:*)", text)
        self.assertEqual(text.count(f'match = "{_CONSOLIDATED}"'), 1)

        metadata = _rule_entry_metadata(cfg, "toml", "allow", _CONSOLIDATED)
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
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepA" }},\n'
            "]\n"
        )
        cfg = self._write("toolguard_hook.toml", toml_content)

        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        self.assertEqual(report.total_skipped, 0)
        text = cfg.read_text()
        self.assertEqual(text.count(f'match = "{_CONSOLIDATED}"'), 1)

        metadata = _rule_entry_metadata(cfg, "toml", "allow", _CONSOLIDATED)
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
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepA" }},\n'
            f'  {{ match = "{_CONSOLIDATED}", additionalContext = "keepB" }},\n'
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


class TestUntargetedListsSurvive(_TempConfigMixin, unittest.TestCase):
    """An allow-list consolidation must leave deny and ask exactly as it found them."""

    def test_toml_deny_and_ask_are_untouched(self):
        """
        Given a TOML config with a populated deny list and ask list alongside the
             allow rules a consolidation targets
        When apply_proposals applies the git-family consolidation
        Then allow holds exactly the consolidated regex plus the untargeted rule,
             and deny and ask come back off disk exactly as written
        """
        cfg = self._write("toolguard_hook.toml", _TOML_THREE_LISTS)
        apply_proposals([_git_family_proposal(_prov(cfg))])

        lists = _lists_on_disk(cfg)
        self.assertEqual(sorted(lists["allow"]), sorted([_CONSOLIDATED, "Bash(ls:*)"]))
        self.assertEqual(lists["deny"], ["Bash(rm -rf /:*)"])
        self.assertEqual(lists["ask"], ["Bash(curl:*)"])

    def test_json_deny_and_ask_are_untouched(self):
        """
        Given a JSON config with a populated deny list and ask list alongside the
             allow rules a consolidation targets
        When apply_proposals applies the git-family consolidation
        Then allow holds exactly the consolidated regex plus the untargeted rule,
             and deny and ask come back off disk exactly as written
        """
        cfg = self._write_json("toolguard_hook.json", _JSON_THREE_LISTS)
        apply_proposals([_git_family_proposal(_prov(cfg, "json"))])

        lists = _lists_on_disk(cfg, "json")
        self.assertEqual(sorted(lists["allow"]), sorted([_CONSOLIDATED, "Bash(ls:*)"]))
        self.assertEqual(lists["deny"], ["Bash(rm -rf /:*)"])
        self.assertEqual(lists["ask"], ["Bash(curl:*)"])

    def test_consolidated_rule_lands_in_allow_and_nowhere_else(self):
        """
        Given a TOML config with all three permission lists populated
        When apply_proposals applies an ALLOW-list consolidation
        Then the consolidated pattern appears in allow and in NEITHER deny nor
             ask -- a rule that changed lists is the one edit the write guard's
             flat expected_patterns cannot see (proposed ticket 39), so it has
             to be caught here
        """
        cfg = self._write("toolguard_hook.toml", _TOML_THREE_LISTS)
        apply_proposals([_git_family_proposal(_prov(cfg))])

        lists = _lists_on_disk(cfg)
        self.assertIn(_CONSOLIDATED, lists["allow"])
        self.assertNotIn(_CONSOLIDATED, lists["deny"])
        self.assertNotIn(_CONSOLIDATED, lists["ask"])
        # The untargeted rules did not move either.
        self.assertNotIn("Bash(rm -rf /:*)", lists["allow"])
        self.assertNotIn("Bash(curl:*)", lists["allow"])


class TestUnsupportedListType(_TempConfigMixin, unittest.TestCase):
    """Only allow-list proposals are enacted; anything else is refused, not redirected."""

    def test_deny_list_proposal_is_skipped_and_nothing_is_written(self):
        """
        Given a proposal whose list_type is 'deny' but whose patterns are all
             present in the file's ALLOW list
        When apply_proposals runs
        Then it is skipped naming the unsupported list type, the file is
             byte-unchanged, and in particular the proposal's added pattern was
             NOT written into allow -- silently treating a deny proposal as an
             allow one is how this module would enact a widening
        """
        cfg = self._write("toolguard_hook.toml", _TOML_THREE_LISTS)
        before = cfg.read_text()
        prop = ConsolidationProposal(
            kind="literal-alternation",
            tool="Bash",
            list_type="deny",
            layer_provenance=_prov(cfg),
            removed_patterns=("git diff:*", "git status:*"),
            added_pattern="[regex]^git (diff|status)",
            rationale="alternation at token 1",
            replay_summary="probes unchanged; no corpus",
        )

        report = apply_proposals([prop])

        self.assertEqual(report.total_applied, 0)
        self.assertEqual(report.total_skipped, 1)
        self.assertIn("unsupported list_type", report.files[0].skipped[0][1])
        self.assertIn("deny", report.files[0].skipped[0][1])
        self.assertFalse(report.files[0].written)
        self.assertEqual(cfg.read_text(), before)
        self.assertNotIn(_CONSOLIDATED, _lists_on_disk(cfg)["allow"])


class TestIdempotence(_TempConfigMixin, unittest.TestCase):
    """Re-applying a consolidation that already landed changes nothing."""

    def test_second_apply_of_the_same_proposal_is_a_no_op(self):
        """
        Given a consolidation that has already been applied to a TOML config
        When the very same proposal is applied a second time
        Then the second run applies nothing, skips with a drift reason, writes
             no file, leaves the text byte-identical to the first run's output,
             and does not duplicate the consolidated rule
        """
        cfg = self._write("toolguard_hook.toml", _TOML_THREE_LISTS)
        first = apply_proposals([_git_family_proposal(_prov(cfg))])
        after_first = cfg.read_text()

        second = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(first.total_applied, 1)
        self.assertTrue(first.files[0].written)
        self.assertEqual(second.total_applied, 0)
        self.assertEqual(second.total_skipped, 1)
        self.assertIn("not found", second.files[0].skipped[0][1])
        self.assertFalse(second.files[0].written)
        self.assertEqual(cfg.read_text(), after_first)
        self.assertEqual(_lists_on_disk(cfg)["allow"].count(_CONSOLIDATED), 1)


class TestDuplicateRemovedPattern(_TempConfigMixin, unittest.TestCase):
    """Removal takes one occurrence per removed pattern, not every match."""

    def test_a_second_copy_of_a_removed_rule_survives(self):
        """
        Given a TOML allow list carrying 'Bash(git diff:*)' TWICE
        When the git-family consolidation removing it is applied
        Then exactly one copy is removed and one survives alongside the new
             regex.

        Characterization of the deliberate one-occurrence removal in
        _apply_to_file, not an endorsement: the survivor is narrower than the
        regex that replaced it, so the outcome is a redundant rule rather than
        a widening -- but the consolidation is incomplete. Recorded so a change
        of policy is visible.
        """
        cfg = self._write(
            "toolguard_hook.toml",
            (
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(git diff:*)",\n'
                '  "Bash(ls:*)",\n'
                '  "Bash(git diff:*)",\n'
                '  "Bash(git status:*)",\n'
                "]\n"
            ),
        )
        report = apply_proposals([_git_family_proposal(_prov(cfg))])

        self.assertEqual(report.total_applied, 1)
        allow = _lists_on_disk(cfg)["allow"]
        self.assertEqual(allow.count("Bash(git diff:*)"), 1)
        self.assertEqual(allow.count("Bash(git status:*)"), 0)
        self.assertEqual(allow.count(_CONSOLIDATED), 1)


class TestMultipleFiles(_TempConfigMixin, unittest.TestCase):
    """Proposals naming different files are applied to their own file, not merged."""

    def test_each_file_gets_only_its_own_proposal(self):
        """
        Given two TOML configs, each with its own proposal -- a git-family
             consolidation on the first and a pure-drop subsumption on the
             second
        When apply_proposals runs over both
        Then two FileChanges come back in first-seen order, each naming its own
             path, and each file on disk carries only its own edit
        """
        first = self._write("first.toml", _TOML_THREE_LISTS)
        second = self._write(
            "second.toml",
            (
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(mkdir -p /tmp/:*)",\n'
                '  "Bash(mkdir -p /tmp/claude-code:*)",\n'
                "]\n"
            ),
        )
        drop = ConsolidationProposal(
            kind="static-subsumption",
            tool="Bash",
            list_type="allow",
            layer_provenance=_prov(second),
            removed_patterns=("mkdir -p /tmp/claude-code:*",),
            added_pattern=None,
            rationale="subsumed by mkdir -p /tmp/:*",
            replay_summary="static proof",
        )

        report = apply_proposals([_git_family_proposal(_prov(first)), drop])

        self.assertEqual([f.path for f in report.files], [first, second])
        self.assertEqual(report.total_applied, 2)
        self.assertEqual(len(report.files_written), 2)

        first_allow = _lists_on_disk(first)["allow"]
        self.assertEqual(sorted(first_allow), sorted([_CONSOLIDATED, "Bash(ls:*)"]))

        second_allow = _lists_on_disk(second)["allow"]
        self.assertEqual(second_allow, ["Bash(mkdir -p /tmp/:*)"])
        self.assertNotIn(_CONSOLIDATED, second_allow)


class TestBatchAtomicity(_TempConfigMixin, unittest.TestCase):
    """A batch must not leave a file rewritten while the caller loses the report."""

    _MALFORMED = 'permissions = "hello"\n'

    def test_a_rewritten_file_is_never_lost_from_the_report(self):
        """
        Given two proposals, the first naming a good TOML config and the second
             naming a config whose `permissions` key is a string rather than a
             table, so re-rendering it raises
        When apply_proposals runs over both
        Then the caller can still account for every file that changed: either
             the call returns a report naming both files, or it raises having
             written nothing at all.

        Deliberately mechanism-agnostic -- it passes whether the fix is to skip
        the unrenderable file with a reason or to validate every target before
        the first write. At HEAD it fails: the first file is rewritten on disk
        and the exception destroys the ChangeReport, so a user's config is
        modified with no record of what changed.
        """
        good = self._write("good.toml", _TOML_THREE_LISTS)
        bad = self._write("bad.toml", self._MALFORMED)
        before_good = good.read_text()

        try:
            report = apply_proposals(
                [_git_family_proposal(_prov(good)), _git_family_proposal(_prov(bad))]
            )
        except Exception:
            self.assertEqual(
                good.read_text(),
                before_good,
                "apply_proposals raised after already rewriting an earlier file, "
                "so the caller has a modified config and no report of the change",
            )
        else:
            self.assertEqual([f.path for f in report.files], [good, bad])

    def test_a_dry_run_previews_the_files_it_can_render(self):
        """
        Given the same good/malformed pair
        When apply_proposals runs with dry_run=True
        Then the caller gets a preview covering the good file rather than
             losing it -- a dry run writes nothing, so an unrenderable sibling
             has nothing to protect the caller from.

        Mechanism-agnostic in the same way as the sibling test, and RED at HEAD:
        _render_via_writer runs for every target before the dry-run gate, so one
        malformed file aborts the whole preview.
        """
        good = self._write("good.toml", _TOML_THREE_LISTS)
        bad = self._write("bad.toml", self._MALFORMED)

        report = apply_proposals(
            [_git_family_proposal(_prov(good)), _git_family_proposal(_prov(bad))],
            dry_run=True,
        )

        self.assertIn(good, [f.path for f in report.files])
        good_change = next(f for f in report.files if f.path == good)
        self.assertIn(_CONSOLIDATED, good_change.diff)
        self.assertEqual(good.read_text(), _TOML_THREE_LISTS)


class TestRawPermissionsRead(_TempConfigMixin, unittest.TestCase):
    """_read_raw_permissions degrades to three empty lists rather than raising."""

    def test_absent_file_reads_as_three_empty_lists(self):
        """
        Given a path that does not exist
        When _read_raw_permissions reads it
        Then all three lists come back empty rather than the read raising
        """
        missing = self.tmpdir / "nope.toml"
        self.assertFalse(missing.exists())

        self.assertEqual(
            _read_raw_permissions(missing, "toml"),
            {"allow": [], "deny": [], "ask": []},
        )

    def test_a_proposal_naming_an_absent_file_is_skipped_not_created(self):
        """
        Given a proposal whose provenance names a config file that no longer exists
        When apply_proposals runs
        Then the proposal is skipped as drift, nothing is written, and the file
             is NOT brought into being by the apply
        """
        missing = self.tmpdir / "nope.toml"
        report = apply_proposals([_git_family_proposal(_prov(missing))])

        self.assertEqual(report.total_applied, 0)
        self.assertEqual(report.total_skipped, 1)
        self.assertIn("not found", report.files[0].skipped[0][1])
        self.assertFalse(report.files[0].written)
        self.assertFalse(missing.exists())

    def test_a_non_table_permissions_key_reads_as_three_empty_lists(self):
        """
        Given a TOML file whose `permissions` key holds a string, not a table
        When _read_raw_permissions reads it
        Then all three lists come back empty rather than the read raising an
             AttributeError on the string
        """
        cfg = self._write("toolguard_hook.toml", 'permissions = "hello"\n')

        self.assertEqual(
            _read_raw_permissions(cfg, "toml"),
            {"allow": [], "deny": [], "ask": []},
        )


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

    def test_pure_drop_is_rendered_as_a_drop_not_a_replacement(self):
        """
        Given a report from a static-subsumption proposal, which drops a rule
             and adds nothing (added_pattern is None)
        When render_change_report(fmt='text') is called
        Then the line says the rule was dropped and shows no '->' replacement
             arrow, so a pure drop is distinguishable from a consolidation
        """
        cfg = self._write(
            "toolguard_hook.toml",
            (
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(mkdir -p /tmp/:*)",\n'
                '  "Bash(mkdir -p /tmp/claude-code:*)",\n'
                "]\n"
            ),
        )
        drop = ConsolidationProposal(
            kind="static-subsumption",
            tool="Bash",
            list_type="allow",
            layer_provenance=_prov(cfg),
            removed_patterns=("mkdir -p /tmp/claude-code:*",),
            added_pattern=None,
            rationale="subsumed by mkdir -p /tmp/:*",
            replay_summary="static proof",
        )
        out = render_change_report(apply_proposals([drop]), fmt="text")

        self.assertIn("static-subsumption: drop Bash(mkdir -p /tmp/claude-code:*)", out)
        self.assertNotIn("->", out)

    def test_applied_line_names_the_proposal_verification_state(self):
        """
        Given two applied proposals with DIFFERENT verification states -- one
             default (UNVERIFIED) and one explicitly SAFE
        When render_change_report(fmt='text') is called
        Then each applied line carries its own state -- the operator can tell
             a probe-only pass from a corpus-replayed one at a glance, without
             cross-referencing JSON.
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
        unverified = _git_family_proposal(_prov(cfg))
        safe_drop = ConsolidationProposal(
            kind="static-subsumption",
            tool="Bash",
            list_type="allow",
            layer_provenance=_prov(cfg),
            removed_patterns=("mkdir -p /tmp/claude-code:*",),
            added_pattern=None,
            rationale="subsumed by mkdir -p /tmp/:*",
            replay_summary="2 positive probes pass; corpus replay 1 entries, "
            "0 broadened, 0 tightened",
            verification=SafetyResult.SAFE,
        )
        out = render_change_report(apply_proposals([unverified, safe_drop]), fmt="text")

        self.assertIn(
            "literal-alternation: Bash(git diff:*), Bash(git status:*) -> "
            "Bash([regex]^git (diff|status)) [UNVERIFIED]",
            out,
        )
        self.assertIn(
            "static-subsumption: drop Bash(mkdir -p /tmp/claude-code:*) [SAFE]", out
        )

    def test_an_unwritten_file_is_reported_as_not_written(self):
        """
        Given a report whose only proposal was skipped, so nothing was written
        When render_change_report(fmt='text') is called
        Then the file's line says 'not written' -- a reader must be able to tell
             an enacted change from a refused one without reading the counts
        """
        cfg = self._write(
            "toolguard_hook.toml",
            '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n',
        )
        out = render_change_report(
            apply_proposals([_git_family_proposal(_prov(cfg))]), fmt="text"
        )

        self.assertIn("not written", out)
        self.assertIn("0 applied, 1 skipped, 0 file(s) written.", out)

    def test_a_pathless_file_change_is_labelled_no_path(self):
        """
        Given a proposal whose provenance carries no file path
        When render_change_report(fmt='text') is called
        Then the file heading reads '(no path)' rather than rendering None
        """
        out = render_change_report(
            apply_proposals([_git_family_proposal(_prov(None))]), fmt="text"
        )

        self.assertIn("(no path)", out)
        self.assertNotIn("None [toml]", out)

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
