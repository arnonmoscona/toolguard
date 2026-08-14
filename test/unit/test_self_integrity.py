"""
Unit tests for toolguard.tools.self_integrity: the declarative [hard_deny]
patterns covering the rm and find ... -delete forms that target ~/.toolguard.

Behaviour is exercised through the REAL decision engine (toolguard.api.decide)
rather than only structurally against the table -- a hard_deny pattern that
looks right but does not match is worse than none, because it is trusted.
"""

import dataclasses
import unittest
from pathlib import Path
from types import MappingProxyType

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.self_integrity import (
    SelfIntegrityProtection,
    required_self_integrity_hard_deny_patterns,
)

_BASH_WRAPPER_PREFIX = "Bash("


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


def _pattern_body(pattern):
    """Strip the Bash(...) wrapper, giving the text decide() reports as matched_rule."""
    return pattern[len(_BASH_WRAPPER_PREFIX) : -1]


class TestSelfIntegrityTable(unittest.TestCase):
    """The declarative self-integrity hard-deny table matches the design guard-rails."""

    def test_the_table_is_populated_and_every_entry_is_scoped_to_toolguard(self):
        """
        Given the required self-integrity hard-deny table
        When its size and the text of every pattern are inspected
        Then it holds at least the two documented entries and each names
        .toolguard -- an empty table is a silent no-op that would satisfy every
        per-entry check below, and an entry not naming .toolguard would deny
        unrelated deletions
        """
        protections = required_self_integrity_hard_deny_patterns()
        self.assertGreaterEqual(
            len(protections), 2, "the self-integrity table lost entries"
        )
        for protection in protections:
            with self.subTest(pattern=protection.pattern):
                self.assertIn(".toolguard", protection.pattern)

    def test_every_entry_targets_bash(self):
        """
        Given the required self-integrity hard-deny table
        When each entry's pattern is inspected
        Then it is wrapped under Bash(...) -- this protects against shell
        deletion commands, not file-path tool calls
        """
        protections = required_self_integrity_hard_deny_patterns()
        self.assertTrue(protections, "empty table: the loop below checks nothing")
        for protection in protections:
            self.assertTrue(protection.pattern.startswith(_BASH_WRAPPER_PREFIX))

    def test_no_duplicate_patterns(self):
        """
        Given the required self-integrity hard-deny table
        When the patterns are collected into a set
        Then no pattern is duplicated
        """
        patterns = [p.pattern for p in required_self_integrity_hard_deny_patterns()]
        self.assertTrue(patterns, "empty table: the comparison below is 0 == 0")
        self.assertEqual(len(patterns), len(set(patterns)))

    def test_every_entry_has_a_nonempty_rationale(self):
        """
        Given the required self-integrity hard-deny table
        When each entry's rationale is inspected
        Then it is a non-empty, human-readable SelfIntegrityProtection.rationale string
        """
        protections = required_self_integrity_hard_deny_patterns()
        self.assertTrue(protections, "empty table: the loop below checks nothing")
        for protection in protections:
            self.assertIsInstance(protection, SelfIntegrityProtection)
            self.assertTrue(protection.rationale.strip())

    def test_entries_are_frozen_dataclass_instances(self):
        """
        Given each required self-integrity hard-deny entry
        When an attempt is made to mutate its pattern
        Then it raises FrozenInstanceError specifically -- the table is
        immutable, where a bare Exception would also be satisfied by any
        unrelated error. The field name is checked separately because a frozen
        dataclass raises the same error for a name that does not exist.
        """
        protections = required_self_integrity_hard_deny_patterns()
        self.assertTrue(protections, "empty table: the loop below checks nothing")
        for protection in protections:
            with self.subTest(pattern=protection.pattern):
                field_names = {f.name for f in dataclasses.fields(protection)}
                self.assertIn("pattern", field_names)
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    protection.pattern = "Bash(rm -rf /)"


class TestSelfIntegrityHardDenyBehavior(unittest.TestCase):
    """
    End-to-end through the live decision engine: what the patterns block, and
    what they leave alone.
    """

    def setUp(self):
        patterns = [p.pattern for p in required_self_integrity_hard_deny_patterns()]
        self.hard_deny_bodies = {_pattern_body(p) for p in patterns}
        self.config = _config_with_hard_deny(patterns)

    def assert_hard_denied(self, command):
        """Assert the command is denied BY a self-integrity hard_deny pattern.

        The verdict alone is not evidence: an extraction failure also produces
        'deny', with matched_rule left as None.
        """
        verdict = decide(self.config, "Bash", command)
        self.assertEqual(verdict.decision, "deny")
        self.assertIn(verdict.matched_rule, self.hard_deny_bodies)
        return verdict

    def test_rm_variants_targeting_toolguard_are_hard_denied(self):
        """
        Given five rm forms naming ~/.toolguard -- spelled with ~, $HOME and a
        resolved absolute path, with and without -r/-rf, and one naming a file
        inside it
        When each is evaluated through decide()
        Then every variant is denied, and denied by a self-integrity hard_deny
        pattern rather than by the fail-closed empty-extraction default
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
                self.assert_hard_denied(command)

    def test_find_delete_variants_targeting_toolguard_are_hard_denied(self):
        """
        Given a find ... -delete command targeting ~/.toolguard (a deletion path
        a plain rm pattern alone would not catch)
        When evaluated through decide()
        Then it is denied by a self-integrity hard_deny pattern
        """
        commands = [
            "find ~/.toolguard -delete",
            "find ~/.toolguard -type f -delete",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assert_hard_denied(command)

    def test_hard_deny_overrides_an_explicit_allow_rule(self):
        """
        Given a config that explicitly ALLOWs rm/find outright (Bash(rm:*),
        Bash(find:*), set up in _config_with_hard_deny)
        When a command targeting ~/.toolguard is evaluated
        Then it is still denied -- hard_deny is not overridable by a normal
        allow at any level
        """
        self.assert_hard_denied("rm -rf ~/.toolguard")

    def test_a_deletion_hidden_in_a_later_compound_leaf_is_still_denied(self):
        """
        Given a compound command whose first leaf is harmless and whose second
        deletes ~/.toolguard
        When evaluated through decide()
        Then both leaves are extracted and the deletion leaf carries the
        hard_deny match -- the deny comes from per-leaf matching, not from the
        whole line failing to parse
        """
        for command in (
            "echo hi && rm -rf ~/.toolguard",
            "cd /tmp; rm -rf ~/.toolguard",
        ):
            with self.subTest(command=command):
                verdict = self.assert_hard_denied(command)
                self.assertEqual(len(verdict.sub_matches), 2)
                deciding = verdict.sub_matches[-1]
                self.assertEqual(deciding.sub_command, "rm -rf ~/.toolguard")
                self.assertEqual(deciding.decision, "deny")

    def test_unrelated_rm_commands_are_not_affected(self):
        """
        Given an rm command that has nothing to do with .toolguard
        When evaluated through decide()
        Then it resolves per the normal cascade -- allowed here by the
        configured Bash(rm:*) rule, not by a fallback, so a hard_deny pattern
        broadened to every rm would fail this
        """
        verdict = decide(self.config, "Bash", "rm -rf /tmp/scratch")
        self.assertEqual(verdict.decision, "allow")
        self.assertEqual(verdict.matched_rule, "rm:*")

    def test_find_forms_outside_the_pattern_are_not_affected(self):
        """
        Given a find over ~/.toolguard that does not delete, and a find ...
        -delete over an unrelated path
        When each is evaluated through decide()
        Then both are allowed by the configured Bash(find:*) rule -- the
        find pattern requires BOTH .toolguard and -delete, so dropping either
        requirement fails this
        """
        for command in ("find ~/.toolguard -type f", "find /tmp/scratch -delete"):
            with self.subTest(command=command):
                verdict = decide(self.config, "Bash", command)
                self.assertEqual(verdict.decision, "allow")
                self.assertEqual(verdict.matched_rule, "find:*")

    def test_read_only_access_to_toolguard_is_not_hard_denied(self):
        """
        Given commands that merely READ ~/.toolguard (ls, cat) rather than
        deleting it
        When evaluated through decide()
        Then they are NOT hard-denied -- only deletion is blocked, so toolguard's
        own tooling can still inspect ~/.toolguard's contents
        """
        for command in ("ls ~/.toolguard", "cat ~/.toolguard/README.txt"):
            with self.subTest(command=command):
                verdict = decide(self.config, "Bash", command)
                self.assertNotEqual(verdict.decision, "deny")
                self.assertNotIn(verdict.matched_rule, self.hard_deny_bodies)

    def test_a_prefix_token_or_absolute_path_does_not_escape_the_patterns(self):
        """
        Given the same deletions written with a prefix word or an absolute
        interpreter path -- 'sudo rm', '/bin/rm', 'sudo find'
        When each is evaluated through decide()
        Then each is denied by a self-integrity hard_deny pattern, exactly as
        its bare form is: the command still deletes ~/.toolguard, and the
        module's own design note says a false positive here costs nothing
        """
        for command in (
            "sudo rm -rf ~/.toolguard",
            "/bin/rm -rf ~/.toolguard",
            "sudo find ~/.toolguard -delete",
        ):
            with self.subTest(command=command):
                self.assert_hard_denied(command)

    def test_rmdir_is_outside_the_patterns(self):
        """
        Given 'rmdir ~/.toolguard/backups' -- rmdir removes an empty directory
        and is a different program from rm, which \\b in '^rm\\b' correctly
        excludes
        When it is evaluated through decide()
        Then it is not denied

        Records where the table stops, NOT a specification: whether rmdir
        deserves a pattern of its own is an open question, and the \\b that
        excludes it is doing its job either way. Relaxing the leading anchor
        (see the test above) does not change this case.
        """
        self.assertNotEqual(
            decide(self.config, "Bash", "rmdir ~/.toolguard/backups").decision, "deny"
        )


if __name__ == "__main__":
    unittest.main()
