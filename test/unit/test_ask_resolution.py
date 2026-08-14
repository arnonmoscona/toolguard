"""
Resolver tests for the ``ask`` permission list, driving the real decision engine
through :func:`toolguard.api.decide`.

The model under test: within a layer a deny wins over any allow or ask, however
specific; otherwise the more specific of a matching allow and ask wins, with an
exact tie going to ask; and a blanket ``*``-class ask is excluded from matching
(:func:`toolguard.permissions.is_universal_pattern`), so a layer holding only
that declines to decide and the cascade runs on to ``no_match_fallback``. Also
covered here: the parse-failure ASK floor, and the inline/heredoc ASK floor's
reach across command tools.

Fixtures set a non-default ``no_match_fallback`` wherever ``ask`` would
otherwise be the fallback's answer too -- without that, an ``ask`` assertion
cannot tell a matched ask rule from a command nothing matched.
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional, Tuple

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance

#: An MCP command tool: routed through the ``Bash`` pattern namespace by
#: :func:`toolguard.api.decide`.
MCP_TERMINAL = "mcp__jetbrains__execute_terminal_command"


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
    tool: str = "Bash",
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    no_match_fallback: Optional[str] = None,
) -> ConfigLayer:
    """Build one toolguard layer with *tool*-wrapped allow/deny/ask bodies."""
    content = {
        "permissions": {
            "allow": [f"{tool}({p})" for p in (allow or [])],
            "deny": [f"{tool}({p})" for p in (deny or [])],
            "ask": [f"{tool}({p})" for p in (ask or [])],
        }
    }
    if no_match_fallback is not None:
        content["no_match_fallback"] = no_match_fallback
    return ConfigLayer(provenance=_prov(specificity), content=MappingProxyType(content))


def _config(
    *layers: ConfigLayer,
    parse_failures: Tuple[Tuple[Path, str], ...] = (),
) -> Configuration:
    """Build a Configuration from the given layers (most-specific first)."""
    return Configuration(
        layers=tuple(layers), start_dir=None, parse_failures=parse_failures
    )


class TestAskResolution(unittest.TestCase):
    """The ask list participates in resolution per the documented model."""

    def test_specific_ask_prompts_where_the_fallback_would_deny(self):
        """
        Given a single specific ask 'toolguard-maintain:*', no allow, and
        no_match_fallback='deny'
        When 'toolguard-maintain --write' and an unrelated command are evaluated
        Then the asked command is 'ask' (the ask rule matched and decided its
        level) while the unrelated one is 'deny' (the fallback), so the 'ask'
        cannot have come from the fallback
        """
        config = _config(_layer(ask=["toolguard-maintain:*"], no_match_fallback="deny"))
        self.assertEqual(
            decide(config, "Bash", "toolguard-maintain --write").decision, "ask"
        )
        self.assertEqual(decide(config, "Bash", "ls -la").decision, "deny")

    def test_blanket_ask_is_excluded_so_the_fallback_decides(self):
        """
        Given only a blanket ask '*' and no allow
        When any command is evaluated under no_match_fallback='deny' and again
        under 'allow'
        Then the verdict follows the fallback each time ('deny', then 'allow'),
        proving the blanket ask never matched and the level declined to decide
        """
        for fallback, expected in (("deny", "deny"), ("allow", "allow")):
            with self.subTest(no_match_fallback=fallback):
                config = _config(_layer(ask=["*"], no_match_fallback=fallback))
                self.assertEqual(decide(config, "Bash", "rm -rf /").decision, expected)

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

    def test_more_specific_allow_bypasses_a_broader_ask(self):
        """
        Given an allow 'git diff:*' and a broader ask 'git:*' that also matches
        When 'git diff HEAD' is evaluated
        Then the verdict is 'allow' -- the more-specific allow bypasses the ask
        """
        config = _config(_layer(allow=["git diff:*"], ask=["git:*"]))
        self.assertEqual(decide(config, "Bash", "git diff HEAD").decision, "allow")

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

    def test_deny_wins_over_ask_however_specific_the_ask(self):
        """
        Given a deny for 'toolguard-maintain:*' beside an identical ask, and
        separately a broad deny 'git:*' beside a strictly more-specific allow
        and ask on 'git diff:*'
        When each matching command is evaluated
        Then both are 'deny' -- deny wins inside its layer even when it is the
        least specific rule there
        """
        tied = _config(
            _layer(deny=["toolguard-maintain:*"], ask=["toolguard-maintain:*"])
        )
        self.assertEqual(
            decide(tied, "Bash", "toolguard-maintain --write").decision, "deny"
        )
        broader_deny = _config(
            _layer(deny=["git:*"], allow=["git diff:*"], ask=["git diff:*"])
        )
        self.assertEqual(decide(broader_deny, "Bash", "git diff HEAD").decision, "deny")

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
        Given a compound where git is allowed, toolguard-maintain is asked, and
        no_match_fallback='allow' so an unmatched sub-command cannot produce a
        prompt
        When 'git status && toolguard-maintain --write' is evaluated, and an
        all-allowed compound alongside it
        Then the first is 'ask' (the one asked sub-command floats up) and the
        second is 'allow'
        """
        config = _config(
            _layer(
                allow=["git status:*"],
                ask=["toolguard-maintain:*"],
                no_match_fallback="allow",
            )
        )
        self.assertEqual(
            decide(config, "Bash", "git status && toolguard-maintain --write").decision,
            "ask",
        )
        self.assertEqual(decide(config, "Bash", "git status && ls").decision, "allow")

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
    """The literal-prefix tie-break when an allow and an ask both match."""

    def test_fully_literal_ask_outranks_broad_allow(self):
        """
        Given a broad allow '*' and a fully-literal ask 'git-status' (no wildcard)
        When the exact command 'git-status' is evaluated
        Then the more-specific ask wins and the decision is ask
        """
        cfg = _config(_layer(allow=["*"], ask=["git-status"]))
        self.assertEqual(decide(cfg, "Bash", "git-status").decision, "ask")

    def test_extended_syntax_ask_scored_by_literal_lead_outranks_allow(self):
        """
        Given an allow 'git*' (literal lead 'git') and a regex ask whose literal
        lead is only longer once the '[regex]' marker is stripped
        When 'gitx status' is evaluated
        Then the ask outscores the allow and the decision is ask -- with the
        marker left on, the ask would score 0 and the allow would win
        """
        cfg = _config(_layer(allow=["git*"], ask=["[regex]^gitx.*"]))
        self.assertEqual(decide(cfg, "Bash", "gitx status").decision, "ask")


class TestFilePathAskResolution(unittest.TestCase):
    """
    The same ask-resolution model for file-path tools (Read/Write/Edit), whose
    resolver is :func:`toolguard.file_matching.decide_file_path_at_level_detailed`.
    """

    def test_specific_file_ask_prompts_where_the_fallback_would_deny(self):
        """
        Given a Read layer whose only rule is a specific ask on /secrets/**,
        with no_match_fallback='deny'
        When a file under /secrets and an unrelated file are read
        Then /secrets is 'ask' (the ask rule matched) and the unrelated file is
        'deny' (the fallback), so the prompt cannot have come from the fallback
        """
        cfg = _config(
            _layer(tool="Read", ask=["/secrets/**"], no_match_fallback="deny")
        )
        self.assertEqual(decide(cfg, "Read", "/secrets/key.txt").decision, "ask")
        self.assertEqual(decide(cfg, "Read", "/etc/hosts").decision, "deny")

    def test_blanket_file_ask_leaves_the_decision_to_the_fallback(self):
        """
        Given a Read layer whose only rule is a blanket ask on '*'
        When a file outside the project is read under no_match_fallback='deny'
        and again under 'allow'
        Then the verdict follows the fallback each time -- the level declined to
        decide
        """
        # Unlike the Bash sibling, this pins the outcome and not the
        # is_universal_pattern exclusion: a relative file pattern is anchored to
        # the project root first, so '*' cannot match an outside path even with
        # the exclusion deleted (measured, TOO-45 test repair).
        for fallback in ("deny", "allow"):
            with self.subTest(no_match_fallback=fallback):
                cfg = _config(
                    _layer(tool="Read", ask=["*"], no_match_fallback=fallback)
                )
                self.assertEqual(decide(cfg, "Read", "/etc/hosts").decision, fallback)

    def test_more_specific_file_ask_gates_broad_allow(self):
        """
        Given a Read layer that allows /proj/** but asks on the narrower /proj/secret/**
        When a file under /proj/secret is read
        Then the more-specific ask wins and the decision is ask
        """
        cfg = _config(_layer(tool="Read", allow=["/proj/**"], ask=["/proj/secret/**"]))
        self.assertEqual(decide(cfg, "Read", "/proj/secret/x").decision, "ask")

    def test_more_specific_file_allow_bypasses_a_broader_ask(self):
        """
        Given a Read layer that allows /proj/** alongside a broader ask on /**
        When a file under /proj is read
        Then the more-specific allow wins and the decision is allow
        """
        cfg = _config(_layer(tool="Read", allow=["/proj/**"], ask=["/**"]))
        self.assertEqual(decide(cfg, "Read", "/proj/readme.md").decision, "allow")

    def test_file_deny_wins_over_ask(self):
        """
        Given a Read layer that both denies and asks on /secrets/**
        When a file under /secrets is read
        Then the decision is deny -- deny wins inside the layer here too
        """
        cfg = _config(_layer(tool="Read", deny=["/secrets/**"], ask=["/secrets/**"]))
        self.assertEqual(decide(cfg, "Read", "/secrets/key.txt").decision, "deny")


class TestParseFailureAskFloor(unittest.TestCase):
    """
    The TOO-19 floor: a config file that failed to parse clamps every governed
    decision to ask -- except an already-deny one, which is never weakened.
    """

    BROKEN = (Path("/fake/broken.toml"), "Expected '=' after a key")

    def test_broken_config_clamps_a_matching_allow_to_ask(self):
        """
        Given a layer that allows 'git status:*' and a configuration carrying a
        parse failure
        When 'git status' is evaluated, and again with no parse failure
        Then the broken config yields 'ask' with the floor's own reason naming
        the unparseable file, while the intact config yields 'allow'
        """
        layer = _layer(allow=["git status:*"])
        floored = decide(
            _config(layer, parse_failures=(self.BROKEN,)), "Bash", "git status"
        )
        self.assertEqual(floored.decision, "ask")
        self.assertIn("BROKEN", floored.reason)
        self.assertIn(str(self.BROKEN[0]), floored.reason)
        self.assertEqual(decide(_config(layer), "Bash", "git status").decision, "allow")

    def test_broken_config_never_weakens_an_already_deny(self):
        """
        Given a layer that denies 'git status:*' and a configuration carrying a
        parse failure
        When 'git status' is evaluated
        Then the decision stays 'deny' and keeps the deny rule's own reason --
        the floor's single exemption
        """
        result = decide(
            _config(_layer(deny=["git status:*"]), parse_failures=(self.BROKEN,)),
            "Bash",
            "git status",
        )
        self.assertEqual(result.decision, "deny")
        self.assertNotIn("BROKEN", result.reason)

    def test_the_floor_covers_file_path_tools_too(self):
        """
        Given a Read layer allowing /proj/** and one denying it, both under a
        configuration carrying a parse failure
        When /proj/x is read
        Then the allow is clamped to 'ask' and the deny stays 'deny' -- the floor
        is not Bash-only, and its exemption travels with it
        """
        broken = (self.BROKEN,)
        allowed = decide(
            _config(_layer(tool="Read", allow=["/proj/**"]), parse_failures=broken),
            "Read",
            "/proj/x",
        )
        self.assertEqual(allowed.decision, "ask")
        self.assertIn("BROKEN", allowed.reason)
        denied = decide(
            _config(_layer(tool="Read", deny=["/proj/**"]), parse_failures=broken),
            "Read",
            "/proj/x",
        )
        self.assertEqual(denied.decision, "deny")


class TestInlineCodeAskFloorAcrossCommandTools(unittest.TestCase):
    """
    The inline/heredoc foreign-code ASK floor, which overrides an allow rule.
    Its scope across command tools is the open question in proposed ticket 11.
    """

    def test_inline_foreign_code_is_floored_for_bash_and_for_an_mcp_terminal(self):
        """
        Given a layer allowing everything ('*')
        When 'python -c ...' and a plain 'ls -la' are evaluated as Bash and as an
        MCP terminal tool
        Then the inline-code command is 'ask' for BOTH tools (the floor beats the
        blanket allow) while 'ls -la' is 'allow' for both
        """
        cfg = _config(_layer(allow=["*"]))
        for tool in ("Bash", MCP_TERMINAL):
            with self.subTest(tool=tool):
                floored = decide(cfg, tool, 'python -c "import os"')
                self.assertEqual(floored.decision, "ask")
                self.assertIn("ASK floor", floored.reason)
                self.assertEqual(decide(cfg, tool, "ls -la").decision, "allow")


if __name__ == "__main__":
    unittest.main()
