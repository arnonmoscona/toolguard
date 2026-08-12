"""
Resolver tests for the ``ask`` permission list, driving the real decision engine
through :func:`toolguard.api.decide`.

The model under test: within a layer a deny wins over any allow or ask, however
specific; otherwise the more specific of a matching allow and ask wins, with an
exact tie going to ask; and a blanket ``*``-class ask is excluded from matching
(:func:`toolguard.permissions.is_universal_pattern`), so a layer holding only
that declines to decide and the cascade runs on to ``no_match_fallback``.
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance


def _prov(specificity: int = 0, level: str = "project") -> Provenance:
    """Build a toolguard_hook Provenance at the given hierarchy specificity."""
    return Provenance(
        level=level,
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(f"/fake/{specificity}/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _layer(
    specificity: int = 0,
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
) -> ConfigLayer:
    """Build a single toolguard layer with wrapped Bash allow/deny/ask bodies."""
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"Bash({p})" for p in (allow or [])],
                "deny": [f"Bash({p})" for p in (deny or [])],
                "ask": [f"Bash({p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=_prov(specificity), content=content)


def _config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers (most-specific first)."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _file_layer(
    specificity: int = 0,
    tool: str = "Read",
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
) -> ConfigLayer:
    """Build a single toolguard layer with wrapped file-path allow/deny/ask bodies."""
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"{tool}({p})" for p in (allow or [])],
                "deny": [f"{tool}({p})" for p in (deny or [])],
                "ask": [f"{tool}({p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=_prov(specificity), content=content)


class TestAskResolution(unittest.TestCase):
    """The ask list participates in resolution per the documented model."""

    def test_specific_ask_with_no_allow_prompts(self):
        """
        Given a single specific ask rule 'toolguard-maintain:*' and no allow
        When 'toolguard-maintain --write' is evaluated
        Then the verdict is 'ask' (a specific ask matches and prompts on its own)
        """
        config = _config(_layer(ask=["toolguard-maintain:*"]))
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "ask"
        )

    def test_blanket_ask_with_no_allow_collapses_to_no_match_fallback(self):
        """
        Given only a blanket ask '*' and no allow
        When any command is evaluated
        Then the verdict is 'ask' -- the blanket ask is excluded from
        level-matching, so the command falls through to no_match_fallback,
        whose default is also 'ask'
        """
        config = _config(_layer(ask=["*"]))
        self.assertEqual(decide(config, "Bash", "rm -rf /").decision, "ask")

    def test_more_specific_ask_gates_a_broad_allow(self):
        """
        Given a broad allow '*' and a more-specific ask 'toolguard-maintain:*'
        When 'toolguard-maintain --write' is evaluated
        Then the verdict is 'ask' (the more-specific ask gates the broad allow)
        """
        config = _config(_layer(allow=["*"], ask=["toolguard-maintain:*"]))
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "ask"
        )

    def test_more_specific_allow_bypasses_a_broad_ask(self):
        """
        Given a specific allow 'git status:*' and a blanket ask '*'
        When 'git status' is evaluated
        Then the verdict is 'allow' (the more-specific allow bypasses the ask;
        the blanket ask is inert)
        """
        config = _config(_layer(allow=["git status:*"], ask=["*"]))
        self.assertEqual(decide(config, "Bash", "git status").decision, "allow")

    def test_specific_allow_vs_specific_ask_more_specific_wins_both_ways(self):
        """
        Given allow 'git:*' and a more-specific ask 'git diff:*'
        When 'git diff HEAD' and 'git status' are evaluated
        Then 'git diff' resolves to 'ask' (more-specific ask gates) and
        'git status' resolves to 'allow' (only the broader allow matches)
        """
        config = _config(_layer(allow=["git:*"], ask=["git diff:*"]))
        self.assertEqual(decide(config, "Bash", "git diff HEAD").decision, "ask")
        self.assertEqual(decide(config, "Bash", "git status").decision, "allow")

    def test_exact_tie_between_allow_and_ask_resolves_to_ask(self):
        """
        Given allow and ask for the identical pattern 'toolguard-maintain:*'
        When 'toolguard-maintain --write' is evaluated
        Then the verdict is 'ask' (a true tie resolves to a prompt, not a silent
        allow)
        """
        config = _config(
            _layer(allow=["toolguard-maintain:*"], ask=["toolguard-maintain:*"])
        )
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "ask"
        )

    def test_deny_still_wins_over_ask(self):
        """
        Given both a deny and an ask for 'toolguard-maintain:*'
        When 'toolguard-maintain --write' is evaluated
        Then the verdict is 'deny' (deny always wins)
        """
        config = _config(
            _layer(deny=["toolguard-maintain:*"], ask=["toolguard-maintain:*"])
        )
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "deny"
        )

    def test_more_specific_layer_ask_gates_less_specific_layer_allow(self):
        """
        Given a broad allow '*' in a layer of higher specificity index and a
        specific ask 'toolguard-maintain:*' in the more-specific layer
        When 'toolguard-maintain --write' is evaluated
        Then the verdict is 'ask' (the more-specific LAYER decides, and its ask
        gates the broad allow below it)
        """
        config = _config(
            _layer(specificity=0, ask=["toolguard-maintain:*"]),
            _layer(specificity=1, allow=["*"]),
        )
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "ask"
        )

    def test_compound_command_with_one_ask_subcommand_is_ask(self):
        """
        Given a compound 'git status && toolguard-maintain --write' where git is
        allowed and toolguard-maintain is asked
        When the compound command is evaluated
        Then the compound verdict is 'ask' (any sub-command ask floats up)
        """
        config = _config(_layer(allow=["git status:*"], ask=["toolguard-maintain:*"]))
        self.assertEqual(
            decide(config, "Bash", "git status && toolguard-maintain --write").decision,
            "ask",
        )

    def test_allow_only_still_allows_and_deny_only_still_denies(self):
        """
        Given a config with only an allow (and separately an allow plus a deny)
        When a matching command is evaluated
        Then the verdict follows the matching list: allow -> allow, deny -> deny
        """
        self.assertEqual(
            decide(
                _config(_layer(allow=["git status:*"])), "Bash", "git status"
            ).decision,
            "allow",
        )
        self.assertEqual(
            decide(
                _config(_layer(allow=["*"], deny=["rm -rf:*"])), "Bash", "rm -rf /"
            ).decision,
            "deny",
        )


class TestAskAllowTieBreak(unittest.TestCase):
    """The literal-prefix tie-break when a broad allow and a specific ask both match."""

    def test_fully_literal_ask_outranks_broad_allow(self):
        """
        Given a broad allow '*' and a fully-literal ask 'git-status' (no wildcard)
        When the exact command 'git-status' is evaluated
        Then the more-specific ask wins and the decision is ask
        """
        cfg = _config(_layer(allow=["*"], ask=["git-status"]))
        self.assertEqual(decide(cfg, "Bash", "git-status").decision, "ask")

    def test_extended_syntax_ask_scored_by_literal_lead_outranks_broad_allow(self):
        """
        Given a broad allow '*' and a regex ask whose literal lead is '^gitx'
        When a command matching the regex is evaluated
        Then the marker is stripped, the ask outscores the broad allow, and it asks
        """
        cfg = _config(_layer(allow=["*"], ask=["[regex]^gitx.*"]))
        self.assertEqual(decide(cfg, "Bash", "gitx status").decision, "ask")


class TestFilePathAskResolution(unittest.TestCase):
    """
    The same ask-resolution model for file-path tools (Read/Write/Edit), whose
    resolver is :func:`toolguard.file_matching.decide_file_path_at_level_detailed`.
    """

    def test_specific_file_ask_with_no_allow_prompts(self):
        """
        Given a Read layer whose only rule is a specific ask on /secrets/**
        When a file under /secrets is read
        Then the decision is ask (a specific ask with no allow yields a prompt)
        """
        cfg = _config(_file_layer(tool="Read", ask=["/secrets/**"]))
        self.assertEqual(decide(cfg, "Read", "/secrets/key.txt").decision, "ask")

    def test_blanket_file_ask_collapses_to_no_match_fallback(self):
        """
        Given a Read layer whose only rule is a blanket ask on * (universal)
        When an arbitrary file is read
        Then the verdict is 'ask' -- the blanket ask is excluded from
        level-matching and it falls through to no_match_fallback, whose
        default is also 'ask'
        """
        cfg = _config(_file_layer(tool="Read", ask=["*"]))
        self.assertEqual(decide(cfg, "Read", "/etc/hosts").decision, "ask")

    def test_more_specific_file_ask_gates_broad_allow(self):
        """
        Given a Read layer that allows /proj/** but asks on the narrower /proj/secret/**
        When a file under /proj/secret is read
        Then the more-specific ask wins and the decision is ask
        """
        cfg = _config(
            _file_layer(tool="Read", allow=["/proj/**"], ask=["/proj/secret/**"])
        )
        self.assertEqual(decide(cfg, "Read", "/proj/secret/x").decision, "ask")

    def test_broad_allow_survives_blanket_ask_for_non_gated_path(self):
        """
        Given a Read layer that allows /proj/** alongside a blanket ask on *
        When a file under /proj that is not otherwise gated is read
        Then the blanket ask is ignored and the allow wins (allow)
        """
        cfg = _config(_file_layer(tool="Read", allow=["/proj/**"], ask=["*"]))
        self.assertEqual(decide(cfg, "Read", "/proj/readme.md").decision, "allow")


if __name__ == "__main__":
    unittest.main()
