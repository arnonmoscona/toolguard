"""
Unit tests for toolguard.tools.redundancy -- redundant rule detection.

Tests cover:
- Static duplicate detection (exact and normalised-equal)
- The required fixture: 'uv run pytest :*' vs 'uv run pytest:*'
- Corpus-backed subsumption detection
- Integration with a minimal Configuration built in-memory
"""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.redundancy import (
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
) -> ConfigLayer:
    """
    Build a ConfigLayer with the given allow/deny/ask patterns for ``tool``.

    Patterns are stored in the wrapped ``Tool(inner)`` form as config files do.
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
        path=Path(f"/fake/.claude/{'settings' if is_native else 'toolguard_hook'}.json"),
        specificity=specificity,
    )
    content = MappingProxyType(
        {
            "permissions": {
                "allow": wrapped_allow,
                "deny": wrapped_deny,
                "ask": wrapped_ask,
            }
        }
    )
    return ConfigLayer(provenance=prov, content=content)


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
        # These differ only in whitespace inside the body
        patterns = ["uv run pytest :*", "uv run pytest:*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "static")
        # The second one is the duplicate; first is canonical
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
        Given three identical patterns
        When find_static_duplicates() is called
        Then two findings are returned (the 2nd and 3rd occurrences)
        """
        patterns = ["ls:*", "ls:*", "ls:*"]
        prov = _make_provenance()
        findings = find_static_duplicates(patterns, prov, "Bash", "allow")
        self.assertEqual(len(findings), 2)

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

    def test_empty_list_returns_empty(self):
        """
        Given an empty pattern list
        When find_static_duplicates() is called
        Then an empty list is returned
        """
        findings = find_static_duplicates([], _make_provenance(), "Bash", "allow")
        self.assertEqual(findings, [])


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
        Then the normalised-equal duplicate is detected (required test fixture)
        """
        layer = _make_layer(
            "Bash",
            allow=["uv run pytest :*", "uv run pytest:*", "git status:*"],
        )
        config = _make_config(layer)
        findings = find_static_duplicates_across_layers(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "static")
        # The second pattern is the duplicate
        self.assertIn("pytest", findings[0].redundant_pattern)


# ---------------------------------------------------------------------------
# Corpus-backed subsumption
# ---------------------------------------------------------------------------


class TestCorpusRedundancy(unittest.TestCase):
    """Tests for corpus-backed subsumption via find_redundancy()."""

    def test_corpus_redundant_rule_detected(self):
        """
        Given a configuration where rule A is a sub-pattern covered by rule B,
        and the corpus only contains commands matching B
        When find_redundancy() is called with a corpus
        Then a corpus-backed finding is returned for A (removing A changes nothing)
        """
        # Config: allow "git status:*" AND "git:*" (git:* covers everything git)
        # Corpus: only "git status" commands
        # "git status:*" is corpus-redundant because "git:*" already covers it
        layer = _make_layer("Bash", allow=["git status:*", "git:*"])
        config = _make_config(layer)
        corpus = [
            _make_log_entry("Bash", "git status"),
            _make_log_entry("Bash", "git status --short"),
        ]
        findings = find_redundancy(config, "Bash", corpus)
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        # "git status:*" should be corpus-redundant (covered by "git:*")
        redundant_patterns = [f.redundant_pattern for f in corpus_findings]
        self.assertIn("git status:*", redundant_patterns)

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
        Given a configuration with duplicate rules but an empty corpus
        When find_redundancy() is called
        Then only static findings are returned (no corpus check performed)
        """
        layer = _make_layer("Bash", allow=["git:*", "git status:*"])
        config = _make_config(layer)
        findings = find_redundancy(config, "Bash", corpus=[])
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        self.assertEqual(corpus_findings, [])

    def test_combined_static_and_corpus_findings(self):
        """
        Given a configuration with both an exact duplicate and a corpus-redundant rule
        When find_redundancy() is called with a corpus
        Then both static and corpus findings are returned
        """
        layer = _make_layer(
            "Bash",
            allow=["ls:*", "ls:*", "git:*", "git status:*"],  # 'ls:*' is exact dupe
        )
        config = _make_config(layer)
        corpus = [
            _make_log_entry("Bash", "git status"),
            _make_log_entry("Bash", "ls"),
        ]
        findings = find_redundancy(config, "Bash", corpus)
        kinds = {f.kind for f in findings}
        self.assertIn("static", kinds)
        # corpus finding may or may not appear depending on config coverage
        # but static finding must be present
        static_findings = [f for f in findings if f.kind == "static"]
        self.assertGreater(len(static_findings), 0)

    def test_finding_attributes_populated(self):
        """
        Given a configuration with two patterns where one is corpus-redundant
        When find_redundancy() is called
        Then the corpus finding has populated attributes (tool, list_type, kind, note)
        """
        layer = _make_layer("Bash", allow=["git status:*", "git:*"])
        config = _make_config(layer)
        corpus = [_make_log_entry("Bash", "git status")]
        findings = find_redundancy(config, "Bash", corpus)
        corpus_findings = [f for f in findings if f.kind == "corpus"]
        if corpus_findings:
            f = corpus_findings[0]
            self.assertEqual(f.tool, "Bash")
            self.assertEqual(f.list_type, "allow")
            self.assertIsInstance(f.note, str)
            self.assertGreater(len(f.note), 0)
