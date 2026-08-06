"""
Unit tests for toolguard.tools.self_integrity (TOO-15).

Covers the declarative [hard_deny] pattern(s) that stop ~/.toolguard from
being deleted by a Bash rm/find command, even one the installing agent
decides to run on its own initiative -- root-caused from a real install
where an agent ran `rm -rf ~/.toolguard` unprompted while "going further for
a true clean slate," directly contradicting docs/uninstall.md's repeated,
explicit "do not delete ~/.toolguard/" policy.

Behavioral coverage (does the pattern actually block/allow the right
things) lives here via the REAL decision engine (toolguard.tools.decision.decide),
not just structural assertions on the table -- a hard_deny pattern that looks
right but does not actually match is worse than no protection at all, since
it would be trusted.
"""

import unittest
from pathlib import Path
from types import MappingProxyType

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.decision import decide
from toolguard.tools.self_integrity import (
    SelfIntegrityProtection,
    required_self_integrity_hard_deny_patterns,
)


def _config_with_hard_deny(deny_patterns):
    """Build a single-layer Configuration governing Bash with the given hard_deny set."""
    layer = ConfigLayer(
        Provenance(
            "user",
            "toolguard_hook",
            "toml",
            Path("/home/x/.claude/toolguard_hook.toml"),
            0,
        ),
        MappingProxyType(
            {
                "governed_tools": ["Bash"],
                "permissions": {
                    "allow": ["Bash(rm:*)", "Bash(find:*)"],
                    "deny": [],
                    "ask": [],
                },
                "hard_deny": {"deny": list(deny_patterns)},
            }
        ),
    )
    return Configuration(layers=(layer,))


class TestSelfIntegrityTable(unittest.TestCase):
    """The declarative self-integrity hard-deny table matches the design guard-rails."""

    def test_every_entry_targets_bash(self):
        """
        Given the required self-integrity hard-deny table
        When each entry's pattern is inspected
        Then it is wrapped under Bash(...) -- this protects against shell
        deletion commands, not file-path tool calls
        """
        for protection in required_self_integrity_hard_deny_patterns():
            self.assertTrue(protection.pattern.startswith("Bash("))

    def test_no_duplicate_patterns(self):
        """
        Given the required self-integrity hard-deny table
        When the patterns are collected into a set
        Then no pattern is duplicated
        """
        patterns = [p.pattern for p in required_self_integrity_hard_deny_patterns()]
        self.assertEqual(len(patterns), len(set(patterns)))

    def test_every_entry_has_a_nonempty_rationale(self):
        """
        Given the required self-integrity hard-deny table
        When each entry's rationale is inspected
        Then it is a non-empty, human-readable SelfIntegrityProtection.rationale string
        """
        for protection in required_self_integrity_hard_deny_patterns():
            self.assertIsInstance(protection, SelfIntegrityProtection)
            self.assertTrue(protection.rationale.strip())

    def test_entries_are_frozen_dataclass_instances(self):
        """
        Given one required self-integrity hard-deny entry
        When an attempt is made to mutate its pattern
        Then it raises (the table is immutable, matching self_permission.py's
        and recommended_protections.py's frozen-dataclass convention)
        """
        protection = required_self_integrity_hard_deny_patterns()[0]
        with self.assertRaises(Exception):
            protection.pattern = "Bash(rm -rf /)"


class TestSelfIntegrityHardDenyBehavior(unittest.TestCase):
    """
    End-to-end: the patterns actually block the real failure mode through the
    live decision engine, and do not over-reach into unrelated commands.
    """

    def setUp(self):
        patterns = [p.pattern for p in required_self_integrity_hard_deny_patterns()]
        self.config = _config_with_hard_deny(patterns)

    def test_rm_variants_targeting_toolguard_are_hard_denied(self):
        """
        Given the real toolguard state directory referenced with ~, $HOME, or a
        resolved absolute path (three different literal command strings)
        When each is evaluated through decide()
        Then every variant is denied -- this is exactly the command that
        deleted a real install's ~/.toolguard
        """
        commands = [
            "rm -rf ~/.toolguard",
            "rm -rf $HOME/.toolguard",
            "rm -rf /Users/arnon/.toolguard",
            "rm ~/.toolguard/backups/foo.toml",
            "rm -r ~/.toolguard",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decide(self.config, "Bash", command).decision, "deny")

    def test_find_delete_variants_targeting_toolguard_are_hard_denied(self):
        """
        Given a find ... -delete command targeting ~/.toolguard (a deletion path
        a plain rm pattern alone would not catch)
        When evaluated through decide()
        Then it is denied
        """
        commands = [
            "find ~/.toolguard -delete",
            "find ~/.toolguard -type f -delete",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(decide(self.config, "Bash", command).decision, "deny")

    def test_hard_deny_overrides_an_explicit_allow_rule(self):
        """
        Given a config that explicitly ALLOWs rm/find outright (Bash(rm:*),
        Bash(find:*), set up in _config_with_hard_deny)
        When a command targeting ~/.toolguard is evaluated
        Then it is still denied -- hard_deny cannot be overridden by any
        level's normal allow, which is the whole point of using it here
        """
        self.assertEqual(
            decide(self.config, "Bash", "rm -rf ~/.toolguard").decision, "deny"
        )

    def test_unrelated_rm_commands_are_not_affected(self):
        """
        Given an rm command that has nothing to do with .toolguard
        When evaluated through decide()
        Then it resolves per the normal cascade (allowed here, since
        Bash(rm:*) is configured as an explicit allow) -- the hard_deny
        pattern must not over-reach into unrelated deletions
        """
        self.assertEqual(
            decide(self.config, "Bash", "rm -rf /tmp/scratch").decision, "allow"
        )

    def test_read_only_access_to_toolguard_is_not_hard_denied(self):
        """
        Given commands that merely READ ~/.toolguard (ls, cat) rather than
        deleting it
        When evaluated through decide()
        Then they are NOT hard-denied -- only deletion is blocked; toolguard's
        own tooling and a debugging agent still need to be able to inspect
        ~/.toolguard's contents (e.g. reading the journal, backups, or traces)
        """
        for command in ("ls ~/.toolguard", "cat ~/.toolguard/README.txt"):
            with self.subTest(command=command):
                self.assertNotEqual(
                    decide(self.config, "Bash", command).decision, "deny"
                )


if __name__ == "__main__":
    unittest.main()
