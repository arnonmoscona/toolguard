"""
TOO-45 ticket 82: a wrapper native strips before matching Bash rules must not hide the
command under it from either side -- unlike a leading ``NAME=value`` assignment
(``test_assignment_prefix.py``), wrapper stripping is NOT gated: native's own worked
example strips a wrapper for an ALLOW rule (``Bash(npm test *)`` matches
``timeout 30 npm test``). See :data:`toolguard.parser.command_extractor.STRIPPED_WRAPPERS`
for the fetched, dated source quote.

This file also proves the pre-existing assignment asymmetry (ticket 77) is unchanged by
wrapper stripping being added to the same :class:`~toolguard.config_types.CommandSpellings`
pair -- the "one structure, two questions" hazard this ticket's brief calls out by name.
"""

import unittest

from toolguard.parser.command_extractor import (
    STRIPPED_WRAPPERS,
    _strip_wrapper,
    command_spellings,
)
from toolguard.permissions import check_permission, decide_command_at_level_detailed


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


class TestStrippedWrappersIsTheDocumentedNine(unittest.TestCase):
    """The constant matches the fetched-and-dated contract, not a guess."""

    def test_the_tuple_has_exactly_the_documented_nine_names(self):
        """
        Given the fetched native doc's stripped-wrapper list
        When STRIPPED_WRAPPERS is inspected
        Then it holds exactly those nine names, in a tuple (a named constant, not
             inline literals scattered through the module)
        """
        self.assertEqual(
            STRIPPED_WRAPPERS,
            (
                "timeout",
                "time",
                "nice",
                "nohup",
                "stdbuf",
                "command",
                "builtin",
                "noglob",
                "xargs",
            ),
        )


class TestStripWrapperRecognisesEachDocumentedWrapper(unittest.TestCase):
    """Direct tests of the per-wrapper stripping helper, one per documented shape."""

    def test_timeout_consumes_its_mandatory_duration(self):
        """
        Given 'timeout 30 npm test' -- native's own worked example
        When the wrapper is stripped
        Then the inner command 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("timeout 30 npm test"), "npm test")

    def test_timeout_alone_with_no_duration_is_not_stripped(self):
        """
        Given a malformed 'timeout' with nothing after it
        When the wrapper is stripped
        Then nothing is reported stripped, rather than guessing
        """
        self.assertIsNone(_strip_wrapper("timeout"))

    def test_time_is_stripped(self):
        """
        Given 'time npm test'
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("time npm test"), "npm test")

    def test_nice_is_stripped(self):
        """
        Given 'nice npm test'
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("nice npm test"), "npm test")

    def test_nohup_is_stripped(self):
        """
        Given 'nohup npm test'
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("nohup npm test"), "npm test")

    def test_stdbuf_with_an_attached_flag_value_is_stripped(self):
        """
        Given 'stdbuf -o0 npm test' -- an attached-value flag, one token
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("stdbuf -o0 npm test"), "npm test")

    def test_builtin_is_stripped(self):
        """
        Given 'builtin npm test'
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("builtin npm test"), "npm test")

    def test_noglob_is_stripped(self):
        """
        Given 'noglob npm test'
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("noglob npm test"), "npm test")

    def test_bare_xargs_is_stripped(self):
        """
        Given 'xargs grep pattern' -- native's own worked example for bare xargs
        When the wrapper is stripped
        Then 'grep pattern' is what's left
        """
        self.assertEqual(_strip_wrapper("xargs grep pattern"), "grep pattern")

    def test_xargs_with_any_flag_is_not_stripped_at_all(self):
        """
        Given 'xargs -n1 grep pattern' -- native's own counter-example
        When the wrapper is stripped
        Then nothing is reported stripped: a flagged xargs matches as xargs itself,
             not as its inner command
        """
        self.assertIsNone(_strip_wrapper("xargs -n1 grep pattern"))

    def test_command_v_the_query_form_is_not_stripped(self):
        """
        Given 'command -v npm' -- a lookup, not an execution
        When the wrapper is stripped
        Then nothing is reported stripped
        """
        self.assertIsNone(_strip_wrapper("command -v npm"))

    def test_command_without_v_is_stripped(self):
        """
        Given 'command npm test' -- not the query form
        When the wrapper is stripped
        Then 'npm test' is what's left
        """
        self.assertEqual(_strip_wrapper("command npm test"), "npm test")

    def test_sudo_is_not_a_recognised_wrapper(self):
        """
        Given 'sudo rm -rf x' -- absent from native's stripped list
        When the wrapper is stripped
        Then nothing is reported stripped
        """
        self.assertIsNone(_strip_wrapper("sudo rm -rf x"))

    def test_env_is_not_a_recognised_wrapper(self):
        """
        Given 'env rm -rf x' -- absent from native's stripped list
        When the wrapper is stripped
        Then nothing is reported stripped
        """
        self.assertIsNone(_strip_wrapper("env rm -rf x"))

    def test_a_command_that_only_starts_with_a_wrapper_name_is_not_matched(self):
        """
        Given 'nice5 npm test' -- the letters run past the wrapper name itself
        When the wrapper is stripped
        Then nothing is reported stripped, since 'nice5' is a different word
        """
        self.assertIsNone(_strip_wrapper("nice5 npm test"))

    def test_a_command_with_no_wrapper_at_all_is_unaffected(self):
        """
        Given 'npm test' -- no wrapper present
        When the wrapper is stripped
        Then nothing is reported stripped
        """
        self.assertIsNone(_strip_wrapper("npm test"))


class TestWrapperStrippingIsSymmetricUnlikeAssignmentStripping(unittest.TestCase):
    """
    Native's own wrapper example is an ALLOW rule, so both restricting and granting
    lists must see through a wrapper -- the opposite of the assignment-prefix rule.
    """

    def test_an_allow_rule_matches_the_wrapped_form_directly(self):
        """
        Given allow Bash(npm test *) and no assignment prefix
        When 'timeout 30 npm test' is decided
        Then it is allowed -- reproducing native's own worked example
        """
        self.assertEqual(_decide("timeout 30 npm test", ["npm test:*"], []), "allow")

    def test_a_deny_rule_also_matches_the_wrapped_form(self):
        """
        Given deny Bash(rm *)
        When 'timeout 30 rm -rf /tmp/x' is decided
        Then it is denied -- 'timeout 30 rm -rf /' IS 'rm -rf /', wrapper stripping
             runs its argument as the actual command
        """
        self.assertEqual(_decide("timeout 30 rm -rf /tmp/x", [], ["rm:*"]), "deny")

    def test_check_permission_also_sees_through_the_wrapper_on_both_sides(self):
        """
        Given the flat allow/deny check, with the spellings the production path
             computes for it
        When a wrapped allow and a wrapped deny are each checked
        Then both are decided as if the wrapper were never there
        """
        allow_cmd = "timeout 5 ls -la"
        self.assertEqual(
            check_permission(
                allow_cmd, ["ls:*"], [], spellings=command_spellings(allow_cmd)
            )[0],
            "allow",
        )
        deny_cmd = "nohup rm -rf /tmp/x"
        self.assertEqual(
            check_permission(
                deny_cmd, ["*"], ["rm:*"], spellings=command_spellings(deny_cmd)
            )[0],
            "deny",
        )


class TestTheAssignmentAsymmetryIsUnchangedByWrapperStripping(unittest.TestCase):
    """
    The two invariants the brief requires proven: adding wrapper spellings to the same
    CommandSpellings pair must not touch ticket 77's assignment-prefix behaviour.
    """

    def test_an_unsafe_assignment_still_withholds_the_grant(self):
        """
        Given allow Bash(ls:*) with only TG_INTENT safe to look past
        When 'TG_INTENT=1 LD_PRELOAD=x ls' is decided
        Then it is NOT granted -- one unlisted name in the prefix withdraws the
             whole grant, exactly as before wrapper stripping existed
        """
        self.assertIsNone(
            _decide(
                "TG_INTENT=1 LD_PRELOAD=x ls",
                ["ls:*"],
                [],
                looked_past=("TG_INTENT",),
            )
        )

    def test_an_unsafe_assignment_is_still_caught_by_deny(self):
        """
        Given deny Bash(rm *)
        When 'FOO=bar rm -rf tmp/' is decided
        Then it is still denied -- deny sees past any leading assignment unconditionally
        """
        self.assertEqual(_decide("FOO=bar rm -rf tmp/", [], ["rm:*"]), "deny")

    def test_a_wrapper_behind_an_unsafe_assignment_is_not_granted_either(self):
        """
        Given allow Bash(npm test *) with nothing configured safe to look past
        When 'FOO=bar timeout 30 npm test' is decided
        Then it is NOT granted -- an unsafe assignment must hide the wrapper (and the
             command under it) from granting just as it hides the bare command
        """
        self.assertIsNone(_decide("FOO=bar timeout 30 npm test", ["npm test:*"], []))

    def test_a_wrapper_behind_an_unsafe_assignment_is_still_denied(self):
        """
        Given deny Bash(rm *)
        When 'FOO=bar timeout 30 rm -rf /tmp/x' is decided
        Then it is denied -- restricting sees past both the assignment and the wrapper
        """
        self.assertEqual(
            _decide("FOO=bar timeout 30 rm -rf /tmp/x", [], ["rm:*"]), "deny"
        )

    def test_a_wrapper_behind_a_safe_assignment_is_granted(self):
        """
        Given allow Bash(npm test *) with TG_INTENT configured safe to look past
        When 'TG_INTENT=1 timeout 30 npm test' is decided
        Then it is granted -- a safe assignment does not block the (unconditional)
             wrapper strip behind it
        """
        self.assertEqual(
            _decide(
                "TG_INTENT=1 timeout 30 npm test",
                ["npm test:*"],
                [],
                looked_past=("TG_INTENT",),
            ),
            "allow",
        )


if __name__ == "__main__":
    unittest.main()
