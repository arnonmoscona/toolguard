"""
A leading ``NAME=value`` assignment must not hide the command under it from a deny
rule, and must not smuggle one past an allow rule either.

Four layers are covered here because the asymmetry is spread across them: the
grammar-fed split (:mod:`toolguard.parser.command_extractor`), the matcher that
consumes it (:mod:`toolguard.permissions`), the configured list of assignment names
an allow rule may be looked past (:mod:`toolguard.config`), and the live resolver
that wires the three together (:mod:`toolguard.resolve`).
"""

import unittest
from pathlib import Path

from test.unit._config_isolation import ConfigIsolationMixin

from toolguard.config import load_configuration
from toolguard.parser.command_extractor import command_spellings, leading_assignments
from toolguard.permissions import (
    check_hard_deny,
    check_permission,
    decide_command_at_level_detailed,
)
from toolguard.resolve import resolve_bash_permission_detailed

#: A deny pattern per pattern type, each verified below to match ``rm -rf /tmp/x``
#: on its own. The bypass this file exists for was invisible to three of the four,
#: because only DEFAULT patterns consulted the alternative spellings.
DENY_BY_PATTERN_TYPE = {
    "default": "rm:*",
    "regex": "[regex]^rm ",
    "glob": "[glob]rm -rf /**",
    "native": "[native]rm *",
}

PREFIXED_RM = "FOO=1 rm -rf /tmp/x"
PLAIN_RM = "rm -rf /tmp/x"


def _decide(command, allow, deny, looked_past=(), ask=None):
    """Decide *command* at one level, with the spellings the production path supplies."""
    spellings = command_spellings(command, looked_past)
    match = decide_command_at_level_detailed(
        command,
        list(allow),
        list(deny),
        ask_patterns=list(ask or []),
        spellings=spellings,
    )
    return None if match is None else match.decision


def _write(directory: Path, name: str, text: str) -> Path:
    """Write *text* to ``directory/name``, creating the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


class TestLeadingAssignmentsAreReadFromTheGrammar(unittest.TestCase):
    """The split of a leaf into its assignment prefix and the command under it."""

    def test_a_single_assignment_is_split_off(self):
        """
        Given a command with one leading NAME=value assignment
        When its leading assignments are read
        Then the variable name and the command without the prefix are reported
        """
        prefix = leading_assignments(PREFIXED_RM)
        self.assertEqual(prefix.names, ("FOO",))
        self.assertEqual(prefix.without_prefix, PLAIN_RM)

    def test_several_assignments_are_all_reported_in_source_order(self):
        """
        Given a command with three leading assignments before the command word
        When its leading assignments are read
        Then all three names come back in order, and the command word starts the rest
        """
        prefix = leading_assignments("A=1 B=2 C=3 rm -rf /tmp/x")
        self.assertEqual(prefix.names, ("A", "B", "C"))
        self.assertEqual(prefix.without_prefix, PLAIN_RM)

    def test_the_append_operator_is_an_assignment_and_is_not_part_of_the_name(self):
        """
        Given bash's append form FOO+=1 used as a leading assignment
        When its leading assignments are read
        Then the name is FOO, without the '+', and the command under it is found
        """
        prefix = leading_assignments("FOO+=1 rm -rf /tmp/x")
        self.assertEqual(prefix.names, ("FOO",))
        self.assertEqual(prefix.without_prefix, PLAIN_RM)

    def test_a_substitution_in_the_value_does_not_hide_the_command(self):
        """
        Given an assignment whose value is a command substitution
        When its leading assignments are read
        Then the substitution is part of the value and the command under it is found
        """
        prefix = leading_assignments("FOO=$(id) rm -rf /tmp/x")
        self.assertEqual(prefix.names, ("FOO",))
        self.assertEqual(prefix.without_prefix, PLAIN_RM)

    def test_an_assignment_looking_token_that_is_not_leading_is_not_one(self):
        """
        Given a command whose ARGUMENT looks like an assignment
        When its leading assignments are read
        Then it reports none, so nothing is stripped from an argument
        """
        self.assertIsNone(leading_assignments("echo FOO=1 rm"))
        self.assertIsNone(leading_assignments(PLAIN_RM))


class TestDenyIsNotEvadedByAnAssignmentPrefix(unittest.TestCase):
    """Every pattern type must see the command under a leading assignment."""

    def test_each_pattern_type_denies_the_plain_command(self):
        """
        Given the deny pattern this file uses for each of the four pattern types
        When the plain command is decided against it
        Then every one of them denies, so the bypass tests below have real force
        """
        for kind, pattern in DENY_BY_PATTERN_TYPE.items():
            with self.subTest(pattern_type=kind):
                self.assertEqual(_decide(PLAIN_RM, [], [pattern]), "deny")

    def test_each_pattern_type_denies_through_the_assignment_prefix(self):
        """
        Given a deny rule for rm, in each of the four pattern types
        When 'FOO=1 rm -rf /tmp/x' is decided against it
        Then it is denied -- the prefix does not hide the command from any of them
        """
        for kind, pattern in DENY_BY_PATTERN_TYPE.items():
            with self.subTest(pattern_type=kind):
                self.assertEqual(_decide(PREFIXED_RM, [], [pattern]), "deny")

    def test_an_ask_rule_also_sees_through_the_prefix(self):
        """
        Given an ask rule for rm and no other rule
        When 'FOO=1 rm -rf /tmp/x' is decided
        Then it asks, because an ask rule restricts and so looks past the prefix
        """
        self.assertEqual(_decide(PREFIXED_RM, [], [], ask=["rm:*"]), "ask")

    def test_a_hard_deny_sees_through_the_prefix(self):
        """
        Given a hard_deny pool denying rm with no carve-out
        When 'FOO=1 rm -rf /tmp/x' is checked against the pool
        Then it is hard-denied
        """
        spellings = command_spellings(PREFIXED_RM)
        match = check_hard_deny(PREFIXED_RM, ["rm:*"], [], spellings=spellings)
        self.assertIsNotNone(match)
        self.assertEqual(match.decision, "deny")

    def test_a_rule_keyed_on_the_marker_itself_still_matches(self):
        """
        Given a deny rule written against the marked spelling, 'TG_INTENT=1 rm:*'
        When the marked command is decided
        Then it is denied -- the raw spelling is still matched alongside the stripped one
        """
        self.assertEqual(
            _decide("TG_INTENT=1 rm -rf /tmp/x", [], ["TG_INTENT=1 rm:*"]), "deny"
        )

    def test_several_assignments_do_not_hide_the_command_either(self):
        """
        Given a deny rule for rm and a command behind three leading assignments
        When it is decided
        Then it is denied
        """
        self.assertEqual(_decide("A=1 B=2 C=3 rm -rf /tmp/x", [], ["rm:*"]), "deny")


class TestAllowIsNotWidenedByAnAssignmentPrefix(unittest.TestCase):
    """An allow rule looks past an assignment only for names configured as safe."""

    def test_an_unlisted_assignment_is_not_looked_past(self):
        """
        Given allow Bash(ls:*) and nothing configured as safe to look past
        When 'LD_PRELOAD=/tmp/evil.so ls' is decided
        Then no level matches, so the allow does not cover it
        """
        self.assertIsNone(_decide("LD_PRELOAD=/tmp/evil.so ls", ["ls:*"], []))

    def test_an_unlisted_assignment_is_not_looked_past_even_when_others_are(self):
        """
        Given allow Bash(ls:*) with only TG_INTENT safe to look past
        When 'LD_PRELOAD=/tmp/evil.so ls' is decided
        Then the allow still does not cover it
        """
        self.assertIsNone(
            _decide(
                "LD_PRELOAD=/tmp/evil.so ls", ["ls:*"], [], looked_past=("TG_INTENT",)
            )
        )

    def test_a_listed_assignment_is_looked_past_and_only_then(self):
        """
        Given allow Bash(ls:*) and the command 'TG_INTENT=1 ls -la'
        When it is decided with, and without, TG_INTENT configured as safe
        Then it is allowed only once TG_INTENT is configured
        """
        self.assertIsNone(_decide("TG_INTENT=1 ls -la", ["ls:*"], []))
        self.assertEqual(
            _decide("TG_INTENT=1 ls -la", ["ls:*"], [], looked_past=("TG_INTENT",)),
            "allow",
        )

    def test_one_unlisted_name_in_the_prefix_withdraws_the_whole_grant(self):
        """
        Given allow Bash(ls:*) with only TG_INTENT safe to look past
        When 'TG_INTENT=1 LD_PRELOAD=x ls' is decided
        Then the allow does not cover it -- every name in the prefix must be listed
        """
        self.assertIsNone(
            _decide(
                "TG_INTENT=1 LD_PRELOAD=x ls", ["ls:*"], [], looked_past=("TG_INTENT",)
            )
        )

    def test_a_hard_deny_carve_out_is_not_widened_either(self):
        """
        Given a hard_deny on rm carved out for 'rm -rf /tmp/*'
        When 'LD_PRELOAD=x rm -rf /tmp/x' is checked with nothing safe to look past
        Then the carve-out does not apply and the command stays hard-denied
        """
        command = "LD_PRELOAD=x rm -rf /tmp/x"
        spellings = command_spellings(command)
        match = check_hard_deny(
            command, ["rm:*"], ["rm -rf /tmp/*"], spellings=spellings
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.decision, "deny")

    def test_a_command_with_no_prefix_is_unaffected(self):
        """
        Given allow Bash(ls:*) and a command with no leading assignment
        When it is decided
        Then it is allowed exactly as before, with no spellings offered
        """
        self.assertEqual(_decide("ls -la", ["ls:*"], []), "allow")
        self.assertEqual(command_spellings("ls -la").restricting, ())
        self.assertEqual(command_spellings("ls -la").granting, ())

    def test_a_deny_still_beats_a_looked_past_allow(self):
        """
        Given a level that both allows ls and denies it, with TG_INTENT looked past
        When the marked command is decided
        Then deny wins, since deny-first applies to the stripped spelling too
        """
        self.assertEqual(
            _decide(
                "TG_INTENT=1 ls -la", ["ls:*"], ["ls:*"], looked_past=("TG_INTENT",)
            ),
            "deny",
        )


class TestFlatCheckPermissionFollowsTheSameAsymmetry(unittest.TestCase):
    """The flat, unprovenanced allow/deny check behaves like the cascade."""

    def _check(self, command, allow, deny, looked_past=()):
        """Run check_permission with the spellings a caller is expected to supply."""
        spellings = command_spellings(command, looked_past)
        return check_permission(command, list(allow), list(deny), spellings=spellings)[
            0
        ]

    def test_deny_sees_past_the_prefix(self):
        """
        Given a flat allow-everything/deny-rm pair
        When 'FOO=1 rm -rf /tmp/x' is checked
        Then it is denied
        """
        self.assertEqual(self._check(PREFIXED_RM, ["*"], ["rm:*"]), "deny")

    def test_allow_does_not_see_past_an_unlisted_prefix(self):
        """
        Given a flat allow of ls only
        When 'LD_PRELOAD=x ls' is checked with nothing safe to look past
        Then it is denied for want of a matching allow
        """
        self.assertEqual(self._check("LD_PRELOAD=x ls", ["ls:*"], []), "deny")


class TestLookedPastNamesAreConfiguration(ConfigIsolationMixin, unittest.TestCase):
    """The safe-list is read from toolguard_hook config, and defaults to empty."""

    def test_it_is_empty_when_nothing_configures_it(self):
        """
        Given a project config that sets no looked-past assignments
        When the configuration is loaded
        Then no assignment name may be looked past
        """
        _home, project = self.isolate_config_environment()
        _write(project / ".claude", "toolguard_hook.toml", "[permissions]\n")

        config = load_configuration(project)

        self.assertEqual(config.assignments_looked_past_when_granting(), ())

    def test_names_are_pooled_across_levels_most_specific_first(self):
        """
        Given a user level and a project level each listing a different name
        When the configuration is loaded
        Then both names apply, the project's first
        """
        home, project = self.isolate_config_environment()
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_ATTEST_READONLY"]\n',
        )
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_INTENT"]\n',
        )

        config = load_configuration(project)

        self.assertEqual(
            config.assignments_looked_past_when_granting(),
            ("TG_INTENT", "TG_ATTEST_READONLY"),
        )

    def test_a_non_list_value_contributes_nothing_and_is_reported(self):
        """
        Given the setting written as a bare string instead of a list
        When the configuration is loaded
        Then no name may be looked past, and one issue reports a non-list value
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = "TG_INTENT"\n',
        )

        config = load_configuration(project)

        self.assertEqual(config.assignments_looked_past_when_granting(), ())
        messages = [
            issue.message
            for issue in config.validation_issues()
            if "assignments_looked_past_when_granting" in issue.message
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("is str, not a list", messages[0])
        self.assertIn("the whole setting is ignored", messages[0])
        self.assertNotIn("not a string", messages[0])

    def test_a_non_string_entry_is_dropped_and_reported(self):
        """
        Given a list holding one usable name and one number
        When the configuration is loaded
        Then only the name applies, and one issue names the number
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_INTENT", 7]\n',
        )

        config = load_configuration(project)

        self.assertEqual(config.assignments_looked_past_when_granting(), ("TG_INTENT",))
        messages = [
            issue.message
            for issue in config.validation_issues()
            if "assignments_looked_past_when_granting" in issue.message
        ]
        self.assertEqual(len(messages), 1)
        self.assertIn("non-string entry 7", messages[0])

    def test_each_bad_entry_is_named_rather_than_reported_identically(self):
        """
        Given a list holding two different non-string entries
        When the configuration is loaded
        Then each is reported by its own value, so the messages are not interchangeable
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["ok", 1, 2]\n',
        )

        config = load_configuration(project)

        self.assertEqual(config.assignments_looked_past_when_granting(), ("ok",))
        messages = [
            issue.message
            for issue in config.validation_issues()
            if "assignments_looked_past_when_granting" in issue.message
        ]
        self.assertEqual(len(messages), 2)
        self.assertNotEqual(messages[0], messages[1])
        self.assertIn("non-string entry 1", messages[0])
        self.assertIn("non-string entry 2", messages[1])


class TestTheLiveResolverAppliesTheAsymmetry(ConfigIsolationMixin, unittest.TestCase):
    """End to end, through the resolver the hook actually calls."""

    def _resolve(self, project, command):
        """Resolve *command* through the Bash resolver against real config files."""
        config = load_configuration(project)
        return resolve_bash_permission_detailed(command, config, True, (), ()).decision

    def test_a_deny_rule_fires_through_the_prefix(self):
        """
        Given a project config allowing everything and denying rm
        When 'FOO=1 rm -rf /tmp/x' is resolved
        Then it is denied
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Bash(*)"]\ndeny = ["Bash(rm:*)"]\n',
        )

        self.assertEqual(self._resolve(project, PREFIXED_RM), "deny")

    def test_a_marked_command_is_allowed_only_once_its_name_is_configured(self):
        """
        Given a project config allowing ls, first without and then with TG_INTENT
            configured as safe to look past
        When 'TG_INTENT=1 ls -la' is resolved
        Then it is allowed only in the second case
        """
        _home, project = self.isolate_config_environment()
        claude = project / ".claude"
        _write(claude, "toolguard_hook.toml", '[permissions]\nallow = ["Bash(ls:*)"]\n')
        self.assertNotEqual(self._resolve(project, "TG_INTENT=1 ls -la"), "allow")

        _write(
            claude,
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_INTENT"]\n'
            '[permissions]\nallow = ["Bash(ls:*)"]\n',
        )
        self.assertEqual(self._resolve(project, "TG_INTENT=1 ls -la"), "allow")

    def test_a_dangerous_assignment_is_never_allowed_by_the_bare_rule(self):
        """
        Given a project config allowing ls with TG_INTENT configured as safe
        When 'LD_PRELOAD=/tmp/evil.so ls' is resolved
        Then it is not allowed
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_INTENT"]\n'
            '[permissions]\nallow = ["Bash(ls:*)"]\n',
        )

        self.assertNotEqual(
            self._resolve(project, "LD_PRELOAD=/tmp/evil.so ls"), "allow"
        )

    def test_a_later_leaf_of_a_compound_is_looked_past_too(self):
        """
        Given a project config allowing ls, first without and then with TG_INTENT
            configured as safe to look past
        When a compound whose SECOND leaf carries the marker is resolved
        Then it is allowed only in the second case, so the configured list reaches
            every leaf rather than only the one the command starts with
        """
        _home, project = self.isolate_config_environment()
        claude = project / ".claude"
        compound = "ls -la && TG_INTENT=1 ls -R"
        _write(claude, "toolguard_hook.toml", '[permissions]\nallow = ["Bash(ls:*)"]\n')
        self.assertNotEqual(self._resolve(project, compound), "allow")

        _write(
            claude,
            "toolguard_hook.toml",
            'assignments_looked_past_when_granting = ["TG_INTENT"]\n'
            '[permissions]\nallow = ["Bash(ls:*)"]\n',
        )
        self.assertEqual(self._resolve(project, compound), "allow")


if __name__ == "__main__":
    unittest.main()
