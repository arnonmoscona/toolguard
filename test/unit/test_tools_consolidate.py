"""Unit tests for toolguard.tools.consolidate -- consolidation proposal engine."""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.config_access import with_layer_allow_replaced
from toolguard.tools.consolidate import (
    BroadeningProposal,
    _check_family1_safe,
    _static_prefix_of,
    propose_broadening_consolidations,
    propose_consolidations,
)
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.redundancy import _config_without_allow


# ---------------------------------------------------------------------------
# Test helpers (mirror redundancy test helpers for consistency)
# ---------------------------------------------------------------------------


def _make_provenance(
    path: str = "/fake/.claude/toolguard_hook.toml",
    specificity: int = 0,
    level: str = "project",
) -> Provenance:
    """Build a minimal Provenance for test use."""
    return Provenance(
        level=level,
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(path),
        specificity=specificity,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """Build a ConfigLayer whose allow/deny/ask hold the given patterns, wrapped as ``Tool(inner)``."""
    if provenance is None:
        provenance = _make_provenance()
    prefix = f"{tool}("
    wrapped_allow = [f"{prefix}{p})" for p in (allow or [])]
    wrapped_deny = [f"{prefix}{p})" for p in (deny or [])]
    wrapped_ask = [f"{prefix}{p})" for p in (ask or [])]

    content = MappingProxyType(
        {
            "permissions": {
                "allow": wrapped_allow,
                "deny": wrapped_deny,
                "ask": wrapped_ask,
            }
        }
    )
    return ConfigLayer(provenance=provenance, content=content)


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
# Step-0 primitive: with_layer_allow_replaced
# ---------------------------------------------------------------------------


class TestWithLayerAllowReplaced(unittest.TestCase):
    """Tests for with_layer_allow_replaced() -- the synthetic-config primitive."""

    def test_removes_specified_patterns(self):
        """
        Given a layer with three allow patterns
        When with_layer_allow_replaced is called with one pattern in 'removed'
        Then the returned config's allow list omits that pattern and retains the others.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git diff:*", "git status:*", "git log:*"],
            provenance=prov,
        )
        config = _make_config(layer)

        result = with_layer_allow_replaced(config, "Bash", prov, {"git diff:*"}, [])

        from toolguard.tools.config_access import per_layer_rules

        rules = per_layer_rules(result, "Bash")
        self.assertEqual(len(rules), 1)
        allow = set(rules[0].allow)
        self.assertNotIn("git diff:*", allow)
        self.assertIn("git status:*", allow)
        self.assertIn("git log:*", allow)

    def test_adds_new_patterns(self):
        """
        Given a layer with one allow pattern
        When with_layer_allow_replaced is called with an added pattern
        Then the returned config's allow list contains the new pattern.
        """
        prov = _make_provenance()
        layer = _make_layer("Bash", allow=["git diff:*"], provenance=prov)
        config = _make_config(layer)

        result = with_layer_allow_replaced(
            config, "Bash", prov, set(), ["[regex]^git (diff|status)\\b"]
        )

        from toolguard.tools.config_access import per_layer_rules

        rules = per_layer_rules(result, "Bash")
        allow = set(rules[0].allow)
        self.assertIn("[regex]^git (diff|status)\\b", allow)

    def test_removes_and_adds_simultaneously(self):
        """
        Given a layer with three allow patterns
        When with_layer_allow_replaced is called with two patterns removed and one added
        Then the returned config has only the original un-removed patterns plus the new one.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git diff:*", "git status:*", "git log:*"],
            provenance=prov,
        )
        config = _make_config(layer)

        result = with_layer_allow_replaced(
            config,
            "Bash",
            prov,
            {"git diff:*", "git status:*"},
            ["[regex]^git (diff|status)\\b"],
        )

        from toolguard.tools.config_access import per_layer_rules

        rules = per_layer_rules(result, "Bash")
        allow = set(rules[0].allow)
        self.assertEqual(allow, {"git log:*", "[regex]^git (diff|status)\\b"})

    def test_returns_original_when_provenance_not_found(self):
        """
        Given a config where no layer matches the given provenance
        When with_layer_allow_replaced is called
        Then the original config object is returned unchanged.
        """
        prov_a = _make_provenance("/fake/a.toml")
        prov_b = _make_provenance("/fake/b.toml")
        layer = _make_layer("Bash", allow=["git diff:*"], provenance=prov_a)
        config = _make_config(layer)

        result = with_layer_allow_replaced(config, "Bash", prov_b, {"git diff:*"}, [])

        self.assertIs(result, config)

    def test_does_not_modify_other_layers(self):
        """
        Given two layers that BOTH hold the removed pattern, the TARGET layer
            second
        When with_layer_allow_replaced names the second layer's provenance
        Then the first layer keeps its copy and only the named layer loses one
            -- the edit is located by provenance, not by taking the first layer
            that happens to hold the pattern.
        """
        prov_a = _make_provenance("/fake/a.toml")
        prov_b = _make_provenance("/fake/b.toml")
        other = _make_layer(
            "Bash", allow=["git diff:*", "git status:*"], provenance=prov_a
        )
        target = _make_layer("Bash", allow=["git diff:*"], provenance=prov_b)
        config = _make_config(other, target)

        result = with_layer_allow_replaced(config, "Bash", prov_b, {"git diff:*"}, [])

        from toolguard.tools.config_access import per_layer_rules

        rules_a = [r for r in per_layer_rules(result, "Bash") if r.provenance == prov_a]
        self.assertEqual(len(rules_a), 1)
        self.assertIn("git diff:*", rules_a[0].allow)
        self.assertIn("git status:*", rules_a[0].allow)
        rules_b = [r for r in per_layer_rules(result, "Bash") if r.provenance == prov_b]
        self.assertNotIn("git diff:*", rules_b[0].allow)

    def test_inherits_structured_entry_preservation_from_delegate(self):
        """
        Given an allow list holding a plain pattern and a structured entry
        When with_layer_allow_replaced removes only the plain pattern
        Then it does not raise and the structured entry survives as the same
            object (inherited from with_layer_rules_replaced via delegation).
        """
        prov = _make_provenance()
        structured = {"match": "Bash(git push:*)", "additionalContext": "careful"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git diff:*)", structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _make_config(layer)

        result = with_layer_allow_replaced(config, "Bash", prov, {"git diff:*"}, [])

        raw_allow = result.layers[0].content["permissions"]["allow"]
        self.assertEqual(len(raw_allow), 1)
        self.assertIs(raw_allow[0], structured)


# ---------------------------------------------------------------------------
# Step-0 regression: _config_without_allow delegation
# ---------------------------------------------------------------------------


class TestConfigWithoutAllowDelegation(unittest.TestCase):
    """Regression tests ensuring _config_without_allow still works after refactoring."""

    def test_removes_single_pattern_from_allow(self):
        """
        Given a config with 'git diff:*' and 'git status:*' in Bash allow
        When _config_without_allow is called with 'git diff:*'
        Then the returned config has only 'git status:*' in the allow list.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash", allow=["git diff:*", "git status:*"], provenance=prov
        )
        config = _make_config(layer)

        result = _config_without_allow(config, "Bash", "git diff:*")

        from toolguard.tools.config_access import per_layer_rules

        rules = per_layer_rules(result, "Bash")
        allow = set(rules[0].allow)
        self.assertNotIn("git diff:*", allow)
        self.assertIn("git status:*", allow)

    def test_returns_original_when_pattern_absent(self):
        """
        Given a config where 'git diff:*' is NOT in the allow list
        When _config_without_allow is called with 'git diff:*'
        Then the original config object is returned unchanged.
        """
        prov = _make_provenance()
        layer = _make_layer("Bash", allow=["git status:*"], provenance=prov)
        config = _make_config(layer)

        result = _config_without_allow(config, "Bash", "git diff:*")

        self.assertIs(result, config)

    def test_removes_structured_entry_by_pattern(self):
        """
        Given an allow list holding a structured entry (a dict, not a bare
            string) whose 'match' pattern is 'Bash(git push:*)'
        When _config_without_allow is called with 'git push:*'
        Then the structured entry is actually removed (matched by PATTERN via
            normalize_entry, not by raw `dict in list-of-str` identity, which
            is always False for a structured element) and the returned config
            is a NEW object, not the input unchanged.
        """
        prov = _make_provenance()
        structured = {"match": "Bash(git push:*)", "additionalContext": "careful"}
        layer = ConfigLayer(
            provenance=prov,
            content=MappingProxyType(
                {
                    "permissions": {
                        "allow": ["Bash(git diff:*)", structured],
                        "deny": [],
                        "ask": [],
                    }
                }
            ),
        )
        config = _make_config(layer)

        result = _config_without_allow(config, "Bash", "git push:*")

        self.assertIsNot(result, config)
        raw_allow = result.layers[0].content["permissions"]["allow"]
        self.assertEqual(raw_allow, ["Bash(git diff:*)"])


# ---------------------------------------------------------------------------
# Family 1: Literal-alternation consolidation -- happy path
# ---------------------------------------------------------------------------


class TestFamily1GitHappyPath(unittest.TestCase):
    """Family-1 consolidation: git sub-commands collapsed into one regex."""

    def _make_git_config(self) -> tuple:
        """Build a config with six git sub-command allow patterns; return (config, provenance)."""
        prov = _make_provenance()
        patterns = [
            "git diff:*",
            "git flake8:*",
            "git isort:*",
            "git log:*",
            "git ls-files:*",
            "git status:*",
        ]
        layer = _make_layer("Bash", allow=patterns, provenance=prov)
        return _make_config(layer), prov

    def test_single_proposal_returned(self):
        """
        Given six git sub-command patterns differing only at the second token
        When propose_consolidations is called for Bash
        Then exactly one literal-alternation proposal is returned.
        """
        config, _ = self._make_git_config()
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1, f"Expected 1, got: {family1}")

    def test_proposal_covers_all_six_patterns(self):
        """
        Given six git sub-command patterns
        When the family-1 proposal is accepted
        Then removed_patterns contains all six original patterns.
        """
        config, _ = self._make_git_config()
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1)
        removed = set(family1[0].removed_patterns)
        expected = {
            "git diff:*",
            "git flake8:*",
            "git isort:*",
            "git log:*",
            "git ls-files:*",
            "git status:*",
        }
        self.assertEqual(removed, expected)

    def test_added_pattern_is_regex_alternation(self):
        """
        Given six git sub-command patterns
        When the family-1 proposal is accepted
        Then added_pattern is a [regex]-prefixed alternation anchored with ^ and
             with NO trailing \\b (so it mirrors DEFAULT cmd:* prefix semantics),
             and every original token (possibly regex-escaped) appears in it.
        """
        import re as _re

        config, _ = self._make_git_config()
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1)
        added = family1[0].added_pattern
        self.assertIsNotNone(added)
        self.assertTrue(added.startswith("[regex]^git ("), f"Unexpected: {added}")
        self.assertNotIn("\\b", added)
        for token in ("diff", "flake8", "isort", "log", "ls-files", "status"):
            escaped = _re.escape(token)
            self.assertIn(
                escaped, added, f"Missing escaped token '{escaped}' in: {added}"
            )

    def test_consolidation_preserves_prefix_extension_commands(self):
        """
        Given the six git sub-command allow patterns
        When the family-1 consolidation is applied (originals removed, regex added)
        Then prefix-extension commands such as 'git difftool' and
             'git diffstat HEAD' keep verdict 'allow' -- the consolidation does
             NOT silently tighten what the DEFAULT cmd:* prefix already allowed.
        """
        config, prov = self._make_git_config()
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1)
        p = family1[0]
        config_b = with_layer_allow_replaced(
            config, "Bash", prov, set(p.removed_patterns), [p.added_pattern]
        )
        for cmd in ("git difftool", "git diffstat HEAD", "git diff-index HEAD"):
            self.assertEqual(
                decide(config_b, "Bash", cmd).decision,
                "allow",
                f"{cmd!r} should remain allowed after consolidation",
            )

    def test_proposal_kind_and_list_type(self):
        """
        Given a valid family-1 consolidation scenario
        When a proposal is returned
        Then kind is 'literal-alternation' and list_type is 'allow'.
        """
        config, _ = self._make_git_config()
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1)
        p = family1[0]
        self.assertEqual(p.kind, "literal-alternation")
        self.assertEqual(p.list_type, "allow")

    def test_proposal_passes_with_corpus(self):
        """
        Given six git sub-command patterns and matching corpus entries
        When propose_consolidations is called with the corpus
        Then the proposal is still accepted and replay_summary reports the corpus
             replay changed 0 decisions.
        """
        config, _ = self._make_git_config()
        corpus = [
            _make_log_entry("Bash", "git diff HEAD"),
            _make_log_entry("Bash", "git status"),
            _make_log_entry("Bash", "git log --oneline"),
        ]
        proposals = propose_consolidations(config, "Bash", corpus=corpus)
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(len(family1), 1)
        self.assertIn("0 changed", family1[0].replay_summary)


# ---------------------------------------------------------------------------
# Family 1: Literal-alternation consolidation -- alembic landmine (rejection)
# ---------------------------------------------------------------------------


class TestFamily1EquivalenceAndLandmine(unittest.TestCase):
    """
    What actually stops a family-1 consolidation: the no-changed-decision gate,
    not the token-count structure of the grouping.

    Passing that gate is evidence about the commands it ran, never a proof of
    match-set equality -- shapes that pass it and still tighten are named in
    :func:`toolguard.tools.consolidate._check_family1_safe`.
    """

    def test_different_token_count_patterns_produce_no_proposals(self):
        """
        Given 'uv run alembic db upgrade:*' (5 tokens) and
              'uv run alembic downgrade:*' (4 tokens) in the allow list
        When propose_consolidations is called for Bash
        Then no literal-alternation proposal is returned -- patterns with
             different token counts simply never form a group (incidental
             structure, not the safety mechanism). Equalising the token counts
             makes the same two patterns group, so the empty result is the
             grouping declining, not family 1 being inert.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=[
                "uv run alembic db upgrade:*",
                "uv run alembic downgrade:*",
            ],
            provenance=prov,
        )
        config = _make_config(layer)
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(
            family1,
            [],
            f"Expected no family-1 proposals; got: {family1}",
        )

        equal_counts = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*", "uv run alembic downgrade:*"],
                provenance=prov,
            )
        )
        self.assertTrue(
            [
                p
                for p in propose_consolidations(equal_counts, "Bash")
                if p.kind == "literal-alternation"
            ]
        )

    def test_deny_guarded_landmine_survives_consolidation(self):
        """
        Given 'uv run alembic upgrade:*' and 'uv run alembic downgrade:*'
              (both 4 cmd tokens, varying at position 3) plus a deny guard on
              'uv run alembic db downgrade:*'
        When the accepted family-1 proposal is applied
        Then exactly one proposal is accepted, its added pattern is the anchored
             alternation over the two varying tokens, and every probed command
             keeps its verdict: the deny guard stays 'deny', both consolidated
             commands stay 'allow', and an unnamed sibling stays 'ask'.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=[
                "uv run alembic upgrade:*",
                "uv run alembic downgrade:*",
            ],
            deny=["uv run alembic db downgrade:*"],
            provenance=prov,
        )
        config = _make_config(layer)
        family1 = [
            p
            for p in propose_consolidations(config, "Bash")
            if p.kind == "literal-alternation"
        ]
        self.assertEqual(len(family1), 1, f"Expected 1, got: {family1}")
        p = family1[0]
        self.assertEqual(p.added_pattern, "[regex]^uv run alembic (downgrade|upgrade)")

        config_b = with_layer_allow_replaced(
            config, "Bash", prov, set(p.removed_patterns), [p.added_pattern]
        )
        expected = {
            "uv run alembic upgrade head": "allow",
            "uv run alembic downgrade base": "allow",
            "uv run alembic downgradex": "allow",
            "uv run alembic db downgrade": "deny",
            "uv run alembic destroy": "ask",
        }
        for cmd, verdict in expected.items():
            self.assertEqual(decide(config, "Bash", cmd).decision, verdict, cmd)
            self.assertEqual(decide(config_b, "Bash", cmd).decision, verdict, cmd)

    def test_corpus_replay_rejects_a_tightening_consolidation(self):
        """
        Given 'cat ./x:*' and 'cat ./y:*', which the synthetic probes alone
              accept, and a corpus holding 'cat x' -- a command the originals
              allow only via path normalization, which the generated [regex]
              does not apply
        When propose_consolidations is called WITH that corpus
        Then no family-1 proposal is emitted: the corpus replay sees the
             tightening the probe set missed.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer("Bash", allow=["cat ./x:*", "cat ./y:*"], provenance=prov)
        )
        corpus = [_make_log_entry("Bash", "cat x")]
        family1 = [
            p
            for p in propose_consolidations(config, "Bash", corpus=corpus)
            if p.kind == "literal-alternation"
        ]
        self.assertEqual(family1, [], f"Expected rejection; got: {family1}")

    def test_gate_rejects_decision_changing_consolidation(self):
        """
        Given a git diff/status allow group and a deliberately OVER-BROAD
              consolidated body ('[regex]^git ') that matches ALL git commands
        When _check_family1_safe evaluates it (no corpus)
        Then it returns (False, ...): the synthetic absent-token probe flips from
             deny to allow, so the gate rejects the candidate before emission.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*"], provenance=prov)
        )
        passed, evidence = _check_family1_safe(
            config,
            "Bash",
            prov,
            ["git diff:*", "git status:*"],
            "[regex]^git ",
            ["git"],
            ["diff", "status"],
            [],
            None,
        )
        self.assertFalse(passed, f"Expected rejection; evidence: {evidence}")


# ---------------------------------------------------------------------------
# Family 2: Static subsumption elimination -- mkdir happy path
# ---------------------------------------------------------------------------


class TestFamily2MkdirSubsumption(unittest.TestCase):
    """Family-2 consolidation: structurally subsumed mkdir pattern dropped."""

    def _make_mkdir_config(self) -> tuple:
        """Build a config where 'mkdir -p /tmp/claude-code:*' is subsumed by 'mkdir -p /tmp/:*'; return (config, provenance)."""
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=[
                "mkdir -p /tmp/:*",
                "mkdir -p /tmp/claude-code:*",
            ],
            provenance=prov,
        )
        return _make_config(layer), prov

    def test_subsumption_proposal_returned(self):
        """
        Given 'mkdir -p /tmp/:*' and 'mkdir -p /tmp/claude-code:*' in allow list
        When propose_consolidations is called for Bash
        Then exactly one static-subsumption proposal is returned.
        """
        config, _ = self._make_mkdir_config()
        proposals = propose_consolidations(config, "Bash")
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(
            len(family2), 1, f"Expected 1 subsumption proposal; got: {family2}"
        )

    def test_subsumption_removes_smaller_pattern(self):
        """
        Given the mkdir subsumption scenario
        When the family-2 proposal is accepted
        Then removed_patterns contains 'mkdir -p /tmp/claude-code:*'
             and added_pattern is None (pure drop).
        """
        config, _ = self._make_mkdir_config()
        proposals = propose_consolidations(config, "Bash")
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(len(family2), 1)
        p = family2[0]
        self.assertIn("mkdir -p /tmp/claude-code:*", p.removed_patterns)
        self.assertIsNone(p.added_pattern)

    def test_subsumption_proposal_list_type(self):
        """
        Given the mkdir subsumption scenario
        When the family-2 proposal is accepted
        Then list_type is 'allow' and kind is 'static-subsumption'.
        """
        config, _ = self._make_mkdir_config()
        proposals = propose_consolidations(config, "Bash")
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(len(family2), 1)
        p = family2[0]
        self.assertEqual(p.kind, "static-subsumption")
        self.assertEqual(p.list_type, "allow")

    def test_subsumption_with_corpus(self):
        """
        Given the mkdir subsumption scenario and a corpus entry for the subsumed pattern
        When propose_consolidations is called with the corpus
        Then the proposal is still accepted (replay sees 0 broadened entries).
        """
        config, _ = self._make_mkdir_config()
        corpus = [
            _make_log_entry("Bash", "mkdir -p /tmp/claude-code"),
            _make_log_entry("Bash", "mkdir -p /tmp/claude-code/some/dir"),
        ]
        proposals = propose_consolidations(config, "Bash", corpus=corpus)
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(len(family2), 1)
        self.assertIn("0 broadened", family2[0].replay_summary)


# ---------------------------------------------------------------------------
# Family 2: Static subsumption elimination -- conservative non-claim
# ---------------------------------------------------------------------------


class TestFamily2ConservativeNonClaim(unittest.TestCase):
    """Family-2 must NOT claim subsumption for unrelated patterns."""

    def test_unrelated_git_patterns_produce_no_subsumption_proposal(self):
        """
        Given 'git diff:*' and 'git status:*', plus a third rule
              '[regex]^git status' that keeps every probe for 'git status'
              allowed after removal
        When propose_consolidations is called for Bash
        Then no static-subsumption proposal is returned. The third rule
             deliberately satisfies the probe gate, so the ONLY thing left to
             reject the pair is _static_prefix_of: 'git diff' is not a
             structural prefix of 'git status'.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git diff:*", "git status:*", "[regex]^git status"],
            provenance=prov,
        )
        config = _make_config(layer)
        proposals = propose_consolidations(config, "Bash")
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(
            family2, [], f"Expected no subsumption proposals; got: {family2}"
        )

    def test_git_vs_git_annex_not_subsumed(self):
        """
        Given 'git:*' (allows any git command), 'git-annex:*', and a third rule
              '[regex]^git-annex' that keeps every probe for 'git-annex'
              allowed after removal
        When propose_consolidations is called for Bash
        Then no static-subsumption proposal is returned: the third rule
             satisfies the probe gate, and 'git-annex' does not extend 'git' at
             a space or '/' boundary, so _static_prefix_of is the only rejector.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git:*", "git-annex:*", "[regex]^git-annex"],
            provenance=prov,
        )
        config = _make_config(layer)
        proposals = propose_consolidations(config, "Bash")
        family2 = [p for p in proposals if p.kind == "static-subsumption"]
        self.assertEqual(
            family2,
            [],
            f"git-annex:* must not be reported as subsumed by git:*; got: {family2}",
        )

    def test_probe_gate_rejects_unsound_path_boundary_subsumption(self):
        """
        Given '/usr/bin:*' and '/usr/bin/env:*', a pair _static_prefix_of
              accepts (the '/' boundary) but match_command does not honour --
              '/usr/bin:*' matches nothing under '/usr/bin/env'
        When propose_consolidations is called for Bash
        Then no static-subsumption proposal is returned: the positive-probe gate
             rejects it, which is the only guard here.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer("Bash", allow=["/usr/bin:*", "/usr/bin/env:*"], provenance=prov)
        )
        family2 = [
            p
            for p in propose_consolidations(config, "Bash")
            if p.kind == "static-subsumption"
        ]
        self.assertEqual(family2, [], f"Expected rejection; got: {family2}")

    def test_single_pattern_no_proposals(self):
        """
        Given a config with only one allow pattern
        When propose_consolidations is called for Bash
        Then no proposals of any kind are returned -- and adding one groupable
             sibling to the same layer DOES produce a proposal, so the empty
             result means 'no opportunity', not 'nothing was analysed'.
        """
        prov = _make_provenance()
        one = _make_config(_make_layer("Bash", allow=["git diff:*"], provenance=prov))
        self.assertEqual(propose_consolidations(one, "Bash"), [])

        two = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*"], provenance=prov)
        )
        self.assertNotEqual(propose_consolidations(two, "Bash"), [])

    def test_empty_allow_list_no_proposals(self):
        """
        Given a config whose Bash layer has an empty allow list
        When propose_consolidations is called for Bash
        Then no proposals are returned -- and the same layer with two groupable
             patterns DOES produce one, so the empty result distinguishes an
             empty config from an analyzer that returns nothing regardless.
        """
        prov = _make_provenance()
        empty = _make_config(_make_layer("Bash", allow=[], provenance=prov))
        self.assertEqual(propose_consolidations(empty, "Bash"), [])

        populated = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*"], provenance=prov)
        )
        self.assertNotEqual(propose_consolidations(populated, "Bash"), [])


# ---------------------------------------------------------------------------
# Edge cases and integration
# ---------------------------------------------------------------------------


class TestConsolidateEdgeCases(unittest.TestCase):
    """Edge cases for propose_consolidations."""

    def test_non_default_patterns_not_grouped(self):
        """
        Given two [regex] patterns whose BODIES are shaped exactly like the
              DEFAULT 'cmd:*' prefixes family 1 groups
        When propose_consolidations is called
        Then no literal-alternation proposal is returned. The bodies pass every
             other screen family 1 applies -- two cmd tokens, '*' args, literal
             varying token -- so only the PatternType check keeps them apart.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["[regex]git diff:*", "[regex]git status:*"],
            provenance=prov,
        )
        config = _make_config(layer)
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(family1, [], f"Expected no family-1 proposals; got: {family1}")

    def test_wildcard_token_patterns_not_grouped(self):
        """
        Given two patterns where the varying token contains a wildcard character
        When propose_consolidations is called
        Then no family-1 proposal is returned (wildcard tokens are excluded from
             literal-alternation grouping).
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git diff*:*", "git status:*"],
            provenance=prov,
        )
        config = _make_config(layer)
        proposals = propose_consolidations(config, "Bash")
        family1 = [p for p in proposals if p.kind == "literal-alternation"]
        self.assertEqual(family1, [])

    def test_proposals_are_deterministically_ordered(self):
        """
        Given four allow patterns that yield four same-kind proposals whose
              DISCOVERY order (grouping-dict insertion) differs from their
              sorted order
        When propose_consolidations is called
        Then the proposals come back sorted by removed_patterns, not in
             discovery order -- and twice in a row gives the same list.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["zzz a:*", "zzz b:*", "aaa a:*", "aaa b:*"],
            provenance=prov,
        )
        config = _make_config(layer)
        first = propose_consolidations(config, "Bash")
        self.assertEqual(
            [p.removed_patterns for p in first],
            [
                ("aaa a:*", "aaa b:*"),
                ("aaa a:*", "zzz a:*"),
                ("aaa b:*", "zzz b:*"),
                ("zzz a:*", "zzz b:*"),
            ],
        )
        self.assertEqual(propose_consolidations(config, "Bash"), first)

    def test_wrong_tool_produces_no_proposals(self):
        """
        Given a config whose ONLY allow patterns are Bash patterns
        When propose_consolidations is called for 'Read'
        Then no proposals are returned, while the same config queried for
             'Bash' does produce one -- so the empty Read result reflects that
             tool's rules rather than an analyzer that found nothing anywhere.
        """
        prov = _make_provenance()
        layer = _make_layer(
            "Bash",
            allow=["git diff:*", "git status:*"],
            provenance=prov,
        )
        config = _make_config(layer)
        self.assertEqual(propose_consolidations(config, "Read"), [])
        self.assertNotEqual(propose_consolidations(config, "Bash"), [])


class TestPrefixBroadening(unittest.TestCase):
    """Tests for propose_broadening_consolidations() -- the agent-judged broadening enumerator (families 3-4)."""

    def test_git_broadening_newly_admits_corpus_subcommand(self):
        """
        Given three narrow 'git <sub>:*' allow rules and a corpus containing a git
            subcommand none of them allow
        When propose_broadening_consolidations is called with that corpus
        Then a single prefix-broadening proposal to 'git :*' is returned whose
            newly_admitted_commands includes the previously-unallowed git command.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git diff:*", "git status:*", "git log:*"],
                provenance=prov,
            )
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        proposals = propose_broadening_consolidations(config, "Bash", corpus)
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal.kind, "prefix-broadening")
        self.assertEqual(proposal.added_pattern, "git :*")
        self.assertIn("git push origin main", proposal.newly_admitted_commands)

    def test_broadening_flags_overlapping_same_layer_guard(self):
        """
        Given two narrow 'uv run alembic <sub>:*' allows plus a broader same-layer
            ask guard 'uv run:*'
        When propose_broadening_consolidations enumerates the broadening
        Then overlaps_guard_rules names the overlapping ask guard. Resolution
            does NOT protect this one: the broadened allow is more
            literal-specific than the ask, so it wins the tie and the commands
            the ask used to gate would become 'allow'.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*", "uv run alembic current:*"],
                ask=["uv run:*"],
                provenance=prov,
            )
        )
        proposals = propose_broadening_consolidations(config, "Bash", None)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].added_pattern, "uv run alembic :*")
        self.assertIn("ask 'uv run:*'", proposals[0].overlaps_guard_rules)

    def test_no_corpus_yields_probe_only_evidence(self):
        """
        Given a broadenable git allow set and NO corpus
        When propose_broadening_consolidations is called with corpus=None
        Then newly_admitted_commands is empty while probe_admitted_surface is
            non-empty -- the synthetic admitted surface still demonstrates breadth.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git diff:*", "git status:*", "git log:*"],
                provenance=prov,
            )
        )
        proposals = propose_broadening_consolidations(config, "Bash", None)
        self.assertEqual(len(proposals), 1)
        proposal = proposals[0]
        self.assertEqual(proposal.newly_admitted_commands, ())
        self.assertTrue(proposal.probe_admitted_surface)

    def test_strict_consolidation_output_unchanged(self):
        """
        Given a git-family config that yields a strict family-1 proposal
        When propose_consolidations is called alongside the new broadening API
        Then it still returns its literal-alternation proposal and emits NO
            BroadeningProposal objects -- the strict path is unaffected.
        """
        prov = _make_provenance()
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["git diff:*", "git status:*", "git log:*"],
                provenance=prov,
            )
        )
        strict = propose_consolidations(config, "Bash")
        family1 = [p for p in strict if p.kind == "literal-alternation"]
        self.assertTrue(family1)
        self.assertFalse(any(isinstance(p, BroadeningProposal) for p in strict))


class TestStaticPrefixOf(unittest.TestCase):
    """
    _static_prefix_of's own contract: which command strings it treats as
    structural prefixes of which.

    It is a text test, not a proof about match-sets. Where the two diverge is
    documented on the function; the caller's probe gate is what stands between
    a divergence and an emitted proposal -- see
    test_probe_gate_rejects_unsound_path_boundary_subsumption.
    """

    def test_identical_commands_subsume(self):
        """
        Given two identical command prefixes
        When static subsumption is checked
        Then it holds (a set is a subset of itself)
        """
        self.assertTrue(_static_prefix_of("git push", "git push"))

    def test_word_boundary_prefix_subsumes(self):
        """
        Given a small command that extends the large one at a space boundary
        When static subsumption is checked
        Then it holds
        """
        self.assertTrue(_static_prefix_of("git", "git push"))

    def test_path_boundary_prefix_subsumes(self):
        """
        Given a small command that extends the large one at a path boundary
        When static subsumption is checked
        Then it holds
        """
        self.assertTrue(_static_prefix_of("/usr/bin", "/usr/bin/env"))

    def test_bare_textual_prefix_does_not_subsume(self):
        """
        Given a small command that shares only a bare textual prefix (no boundary)
        When static subsumption is checked
        Then it does NOT hold (git-crypt is not under git)
        """
        self.assertFalse(_static_prefix_of("git", "git-crypt"))


if __name__ == "__main__":
    unittest.main()
