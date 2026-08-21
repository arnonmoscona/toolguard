"""Unit tests for toolguard.tools.redundancy -- redundant rule detection."""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.permissions import match_command
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.redundancy import (
    _config_without_allow,
    find_corpus_redundant_allows,
    find_redundancy,
    find_static_duplicates,
    find_static_duplicates_across_layers,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provenance(path: str = "/fake/.claude/toolguard_hook.toml") -> Provenance:
    """Build a minimal Provenance for test use."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(path),
        specificity=0,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    is_native: bool = False,
    specificity: int = 0,
    takeover: Optional[dict] = None,
) -> ConfigLayer:
    """
    Build a ConfigLayer whose allow/deny/ask hold the given patterns, wrapped
    as ``Tool(inner)``.  ``takeover``, when given, becomes the layer's
    ``[takeover_mode]`` section.
    """
    prefix = f"{tool}("
    wrapped_allow = [f"{prefix}{p})" for p in (allow or [])]
    wrapped_deny = [f"{prefix}{p})" for p in (deny or [])]
    wrapped_ask = [f"{prefix}{p})" for p in (ask or [])]

    source_type = "claude" if is_native else "toolguard_hook"
    prov = Provenance(
        level="project",
        source_type=source_type,
        file_format="json",
        path=Path(
            f"/fake/.claude/{'settings' if is_native else 'toolguard_hook'}.json"
        ),
        specificity=specificity,
    )
    raw_content = {
        "permissions": {
            "allow": wrapped_allow,
            "deny": wrapped_deny,
            "ask": wrapped_ask,
        }
    }
    if takeover is not None:
        raw_content["takeover_mode"] = takeover
    return ConfigLayer(provenance=prov, content=MappingProxyType(raw_content))


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _make_log_entry(tool: str, command: str, status: str = "EXECUTED") -> LogEntry:
    """Build a minimal LogEntry for corpus-backed tests."""
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool=tool,
        command=command,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


# ---------------------------------------------------------------------------
# Static duplicate detection
# ---------------------------------------------------------------------------


class TestFindStaticDuplicates(unittest.TestCase):
    """Tests for find_static_duplicates() -- single-list duplicate detection."""

    def test_exact_duplicate_flagged(self):
        """
        Given a list with two identical patterns 'git status:*'
        When find_static_duplicates() is called
        Then one finding of kind='static' is returned for the second occurrence
        """
        patterns = ["git status:*", "ls:*", "git status:*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "static")
        self.assertEqual(findings[0].redundant_pattern, "git status:*")
        self.assertEqual(findings[0].covered_by, "git status:*")

    def test_normalised_equal_duplicate_flagged(self):
        """
        Given 'uv run pytest :*' and 'uv run pytest:*' (the required fixture)
        When find_static_duplicates() is called
        Then a finding is returned because both normalise to the same body
        """
        patterns = ["uv run pytest :*", "uv run pytest:*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "static")
        self.assertEqual(findings[0].redundant_pattern, "uv run pytest:*")
        self.assertEqual(findings[0].covered_by, "uv run pytest :*")

    def test_no_duplicates_returns_empty(self):
        """
        Given a list with all distinct patterns
        When find_static_duplicates() is called
        Then an empty list is returned
        """
        patterns = ["git status:*", "ls:*", "uv run pytest:*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(findings, [])

    def test_three_duplicates_flags_two(self):
        """
        Given three distinct spellings that all normalise to the same body
        When find_static_duplicates() is called
        Then the 2nd and 3rd are returned, both naming the FIRST as covered_by
        """
        patterns = ["ls :*", "ls:*", "ls  :*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(len(findings), 2)
        self.assertEqual([f.redundant_pattern for f in findings], ["ls:*", "ls  :*"])
        # First-seen, not previous-seen: the group's canonical never moves.
        self.assertEqual([f.covered_by for f in findings], ["ls :*", "ls :*"])

    def test_finding_carries_correct_tool_and_list_type(self):
        """
        Given duplicate patterns for tool 'Read' in the 'deny' list
        When find_static_duplicates() is called
        Then findings carry tool='Read' and list_type='deny'
        """
        patterns = ["~/.ssh/**", "~/.ssh/**"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Read", "deny")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].tool, "Read")
        self.assertEqual(findings[0].list_type, "deny")

    def test_no_duplicate_possible_returns_empty(self):
        """
        Given a pattern list too short to hold a duplicate -- empty, then one pattern
        When find_static_duplicates() is called
        Then an empty list is returned for both
        """
        prov = _make_provenance()
        self.assertEqual(find_static_duplicates([], prov, "Bash", "allow"), [])
        self.assertEqual(find_static_duplicates(["ls:*"], prov, "Bash", "allow"), [])

    def test_same_body_different_pattern_type_not_a_duplicate(self):
        """
        Given '[regex]git *' and 'git *' -- one body, two pattern types
        When find_static_duplicates() is called
        Then neither is flagged, because the pattern type is part of the key
        """
        patterns = ["[regex]git *", "git *"]
        findings = find_static_duplicates(patterns, _make_provenance(), "Bash", "allow")
        self.assertEqual(findings, [])


class TestStaticDuplicateNoteWording(unittest.TestCase):
    """
    RD1: a shared normalisation key does not mean the matcher treats the two
    patterns alike, so the note must not claim they are one rule.
    """

    def test_a_space_collapsed_pair_is_worded_as_a_spelling_duplicate(self):
        """
        Given 'a  b:*' (double space) and 'a b:*' (single space) -- the same
              normalised key, but the matcher tells them apart: 'a  b x'
              matches only the double-spaced pattern
        When find_static_duplicates() is called
        Then the finding calls it a spelling duplicate needing review, and
             never says the two are the same rule or safe to drop.
        """
        matches_left, _ = match_command("a  b x", ["a  b:*"])
        matches_right, _ = match_command("a  b x", ["a b:*"])
        self.assertTrue(matches_left)
        self.assertFalse(matches_right)

        findings = find_static_duplicates(
            ["a  b:*", "a b:*"], _make_provenance(), "Bash", "allow"
        )
        self.assertEqual(len(findings), 1)
        note = findings[0].note
        self.assertIn("Spelling duplicate", note)
        self.assertNotIn("redundant and can be dropped", note)
        self.assertNotIn("is the same rule", note)

    def test_a_byte_identical_pair_is_worded_as_an_exact_duplicate(self):
        """
        Given the same literal pattern string twice
        When find_static_duplicates() is called
        Then the note calls it an exact duplicate, not hedged as merely a
             spelling match -- an identical string is not a coarser claim.
        """
        findings = find_static_duplicates(
            ["git status:*", "git status:*"], _make_provenance(), "Bash", "allow"
        )
        self.assertEqual(len(findings), 1)
        self.assertIn("Exact duplicate", findings[0].note)


class TestFindStaticDuplicatesAcrossLayers(unittest.TestCase):
    """Tests for find_static_duplicates_across_layers()."""

    def test_duplicate_within_layer_flagged(self):
        """
        Given a configuration with a single layer containing duplicate allow patterns
        When find_static_duplicates_across_layers() is called for 'Bash'
        Then the duplicate is found
        """
        layer = _make_layer("Bash", allow=["git status:*", "git status:*"])
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].redundant_pattern, "git status:*")

    def test_deny_duplicates_also_detected(self):
        """
        Given a configuration with duplicate deny patterns
        When find_static_duplicates_across_layers() is called
        Then the duplicate in the deny list is found
        """
        layer = _make_layer("Bash", allow=[], deny=["rm -rf:*", "rm -rf:*"])
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].list_type, "deny")

    def test_ask_duplicates_also_detected(self):
        """
        Given a configuration with duplicate ask patterns
        When find_static_duplicates_across_layers() is called
        Then the duplicate in the ask list is found
        """
        layer = _make_layer("Bash", allow=[], ask=["curl:*", "curl:*"])
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].list_type, "ask")
        self.assertEqual(findings[0].redundant_pattern, "curl:*")

    def test_distinct_patterns_no_findings(self):
        """
        Given a configuration with all distinct patterns
        When find_static_duplicates_across_layers() is called
        Then no findings are returned
        """
        layer = _make_layer("Bash", allow=["git status:*", "ls:*", "cat:*"])
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(findings, [])

    def test_uv_run_pytest_fixture(self):
        """
        Given a configuration with 'uv run pytest :*' and 'uv run pytest:*'
        When find_static_duplicates_across_layers() is called
        Then the second is flagged as a duplicate of the first (required test fixture)
        """
        layer = _make_layer(
            "Bash",
            allow=["uv run pytest :*", "uv run pytest:*", "git status:*"],
        )
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "static")
        self.assertEqual(findings[0].redundant_pattern, "uv run pytest:*")
        self.assertEqual(findings[0].covered_by, "uv run pytest :*")


# ---------------------------------------------------------------------------
# Corpus-backed subsumption
# ---------------------------------------------------------------------------


class TestCorpusRedundancy(unittest.TestCase):
    """Tests for corpus-backed subsumption via find_redundancy()."""

    def test_corpus_redundant_rule_detected(self):
        """
        Given 'git status:*' and the broader 'git:*', and a corpus every entry of
            which both rules match
        When find_redundancy() is called with that corpus
        Then BOTH are reported corpus-redundant -- each one's removal leaves the
            other covering the whole corpus, so a finding is a review candidate
            and not a licence to delete both
        """
        layer = _make_layer("Bash", allow=["git status:*", "git:*"])
        config = _make_config(layer)
        corpus = [
            _make_log_entry("Bash", "git status"),
            _make_log_entry("Bash", "git status --short"),
        ]
        findings = find_redundancy(config, "Bash", corpus)
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        self.assertEqual(
            {f.redundant_pattern for f in corpus_findings},
            {"git status:*", "git:*"},
        )

    def test_non_redundant_rule_not_flagged(self):
        """
        Given a configuration with two distinct rules where each covers different commands
        and the corpus exercises both
        When find_redundancy() is called
        Then no corpus findings are returned
        """
        layer = _make_layer("Bash", allow=["ls:*", "cat:*"])
        config = _make_config(layer)
        corpus = [
            _make_log_entry("Bash", "ls -la"),
            _make_log_entry("Bash", "cat README.md"),
        ]
        findings = find_redundancy(config, "Bash", corpus)
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        self.assertEqual(corpus_findings, [])

    def test_empty_corpus_skips_corpus_check(self):
        """
        Given a configuration holding a static duplicate but an empty corpus
        When find_redundancy() is called, and find_corpus_redundant_allows()
            is called directly with the same empty corpus
        Then the static duplicate is still reported, no corpus finding is, and
            the primitive returns empty on its own -- not only because the
            facade declined to call it
        """
        layer = _make_layer("Bash", allow=["git status:*", "git status:*", "git:*"])
        config = _make_config(layer)

        findings = find_redundancy(config, "Bash", corpus=[])
        self.assertEqual([f.kind for f in findings], ["static"])
        self.assertEqual(findings[0].redundant_pattern, "git status:*")

        # Asserted separately because find_redundancy's `if corpus:` and
        # find_corpus_redundant_allows' own empty guard mask each other: with
        # only the facade exercised, either one can be removed unnoticed.
        self.assertEqual(find_corpus_redundant_allows(config, "Bash", []), [])

    def test_combined_static_and_corpus_findings(self):
        """
        Given a configuration with both an exact duplicate and a corpus-redundant rule
        When find_redundancy() is called with a corpus
        Then both static and corpus findings are returned, static ones first
        """
        layer = _make_layer(
            "Bash",
            allow=["ls:*", "ls:*", "git:*", "git status:*"],
        )
        config = _make_config(layer)
        corpus = [
            _make_log_entry("Bash", "git status"),
            _make_log_entry("Bash", "ls"),
        ]
        findings = find_redundancy(config, "Bash", corpus)
        self.assertEqual([f.kind for f in findings], ["static", "corpus", "corpus"])
        self.assertEqual(findings[0].redundant_pattern, "ls:*")
        self.assertEqual(
            {f.redundant_pattern for f in findings[1:]},
            {"git:*", "git status:*"},
        )

    def test_finding_attributes_populated(self):
        """
        Given a configuration with two patterns where one is corpus-redundant
        When find_redundancy() is called
        Then at least one corpus finding is returned, carrying tool, list_type,
            the owning layer's provenance, a non-empty note, and covered_by=None
        """
        layer = _make_layer("Bash", allow=["git status:*", "git:*"])
        config = _make_config(layer)
        corpus = [_make_log_entry("Bash", "git status")]
        findings = find_redundancy(config, "Bash", corpus)
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        self.assertGreater(len(corpus_findings), 0)
        f = corpus_findings[0]
        self.assertEqual(f.tool, "Bash")
        self.assertEqual(f.list_type, "allow")
        self.assertEqual(f.provenance, layer.provenance)
        # A replay diff shows that nothing changed, never which rule took over.
        self.assertIsNone(f.covered_by)
        self.assertIsInstance(f.note, str)
        self.assertGreater(len(f.note), 0)

    def test_structured_entry_detected_as_corpus_redundant(self):
        """
        Given an allow list holding a structured entry (a dict, not a bare
            string) 'git push:*' that is genuinely covered by a broader
            bare rule 'git:*' in the same layer, and a corpus exercising it
        When find_redundancy() is called with the corpus
        Then the structured entry IS reported corpus-redundant.
        """
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=Path("/fake/.claude/toolguard_hook.toml"),
            specificity=0,
        )
        structured = {
            "match": "Bash(git push:*)",
            "additionalContext": "careful",
        }
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": [structured, "Bash(git:*)"],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _make_config(layer)
        corpus = [_make_log_entry("Bash", "git push origin main")]

        findings = find_redundancy(config, "Bash", corpus)

        corpus_findings = [f for f in findings if f.kind == "corpus"]
        redundant_patterns = [f.redundant_pattern for f in corpus_findings]
        self.assertIn("git push:*", redundant_patterns)

    def test_structured_entry_not_falsely_flagged_redundant(self):
        """
        Given an allow list holding a SOLE structured entry (a dict, not a
            bare string) as the only rule covering a corpus command, so
            removing it necessarily changes that command's decision
        When find_redundancy() is called with a corpus exercising it
        Then the structured entry is NOT reported corpus-redundant -- and the
            removal it was spared by was really attempted, not skipped because
            the engine failed to locate the entry at all.
        """
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=Path("/fake/.claude/toolguard_hook.toml"),
            specificity=0,
        )
        structured = {
            "match": "Bash(git push:*)",
            "additionalContext": "careful",
        }
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": [structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _make_config(layer)
        corpus = [_make_log_entry("Bash", "git push origin main")]

        # Without this, the assertion below is satisfied by either of two very
        # different worlds: the rule was replayed and found load-bearing, or the
        # engine never found the dict entry and skipped it on the identity guard.
        self.assertIsNot(_config_without_allow(config, "Bash", "git push:*"), config)

        findings = find_redundancy(config, "Bash", corpus)

        corpus_findings = [f for f in findings if f.kind == "corpus"]
        redundant_patterns = [f.redundant_pattern for f in corpus_findings]
        self.assertNotIn("git push:*", redundant_patterns)


# ---------------------------------------------------------------------------
# RD2 -- the rule tested is the rule reported
# ---------------------------------------------------------------------------


class TestConfigWithoutAllowProvenance(unittest.TestCase):
    """_config_without_allow(provenance=...) targets one specific layer."""

    def test_provenance_none_preserves_first_match_search(self):
        """
        Given the same pattern present in two layers
        When _config_without_allow is called with no provenance
        Then the FIRST layer (in config.layers order) is the one edited --
             unchanged legacy behaviour for callers with no known owner.
        """
        first = _make_layer("Bash", allow=["git status:*"], specificity=1)
        second = _make_layer("Bash", allow=["git status:*"], specificity=0)
        config = _make_config(first, second)

        result = _config_without_allow(config, "Bash", "git status:*")

        self.assertEqual(result.layers[0].content["permissions"]["allow"], [])
        self.assertEqual(
            result.layers[1].content["permissions"]["allow"], ["Bash(git status:*)"]
        )

    def test_provenance_given_restricts_the_search_to_that_layer(self):
        """
        Given the same pattern present in two layers
        When _config_without_allow is called with the SECOND layer's provenance
        Then that layer is edited and the first is left untouched, even though
             the first layer is also a match and would win an unscoped search.
        """
        first = _make_layer("Bash", allow=["git status:*"], specificity=1)
        second = _make_layer("Bash", allow=["git status:*"], specificity=0)
        config = _make_config(first, second)

        result = _config_without_allow(
            config, "Bash", "git status:*", provenance=second.provenance
        )

        self.assertEqual(
            result.layers[0].content["permissions"]["allow"], ["Bash(git status:*)"]
        )
        self.assertEqual(result.layers[1].content["permissions"]["allow"], [])

    def test_provenance_given_but_absent_from_that_layer_is_a_no_op(self):
        """
        Given a pattern present in one layer only
        When _config_without_allow is called with a DIFFERENT layer's provenance
        Then the original config object is returned unchanged, even though the
             pattern does exist somewhere in the config.
        """
        holder = _make_layer("Bash", allow=["git status:*"], specificity=1)
        other = _make_layer("Bash", allow=["ls:*"], specificity=0)
        config = _make_config(holder, other)

        result = _config_without_allow(
            config, "Bash", "git status:*", provenance=other.provenance
        )

        self.assertIs(result, config)


class TestCorpusRedundancyProvenanceAttribution(unittest.TestCase):
    """
    The replay that backs a corpus finding must remove the SAME copy the
    finding is attributed to -- not a different layer's occurrence of the
    same pattern.
    """

    def test_a_takeover_neutralised_native_copy_does_not_launder_the_live_hook_copy(
        self,
    ):
        """
        Given a native layer allowing 'Bash(*)' neutralised by takeover, and a
              toolguard_hook layer allowing both 'Bash(*)' (live) and
              'Bash(ls:*)', with a corpus command only the live '*' admits
        When find_corpus_redundant_allows runs
        Then '*' is NOT reported redundant -- removing the hook's live copy
             does change a decision, even though the native layer's already-
             dead copy of the same pattern would replay as a no-op.
        """
        native = _make_layer("Bash", allow=["*"], is_native=True, specificity=1)
        hook = _make_layer(
            "Bash",
            allow=["*", "ls:*"],
            specificity=0,
            takeover={"enabled": True, "ignored_allow_patterns": ["Bash(*)"]},
        )
        config = _make_config(native, hook)
        corpus = [_make_log_entry("Bash", "npm publish")]

        findings = find_corpus_redundant_allows(config, "Bash", corpus)

        self.assertNotIn("*", [f.redundant_pattern for f in findings])

    def test_a_pattern_only_the_dead_native_copy_holds_is_never_tested(self):
        """
        Given the same neutralised-native / live-hook shape, and a corpus
              command 'ls -la' that 'ls:*' alone admits
        When find_corpus_redundant_allows runs
        Then 'ls:*' -- not reachable through the neutralised native copy at
             all -- can still be correctly reported, showing the fix does not
             suppress genuine findings alongside the false one.
        """
        native = _make_layer("Bash", allow=["*"], is_native=True, specificity=1)
        hook = _make_layer(
            "Bash",
            allow=["*", "ls:*"],
            specificity=0,
            takeover={"enabled": True, "ignored_allow_patterns": ["Bash(*)"]},
        )
        config = _make_config(native, hook)
        corpus = [_make_log_entry("Bash", "ls -la")]

        findings = find_corpus_redundant_allows(config, "Bash", corpus)

        # 'ls -la' is admitted by both '*' and 'ls:*', so removing either alone
        # changes nothing over this one-entry corpus -- both are candidates.
        self.assertIn("ls:*", [f.redundant_pattern for f in findings])
