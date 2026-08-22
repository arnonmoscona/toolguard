"""
A deny rule must reach INSIDE every shell construct the grammar supports.

Written after a grammar change silently stopped decomposing brace groups: the
inner command stopped being its own leaf, so ``deny = ["Bash(rm:*)"]`` no longer
matched ``{ rm -rf /tmp/zz; }``. Nothing caught it -- the corpus contains no
brace-group commands, so a clean ``corpus_build.py --verify`` said nothing about
it, and no unit test covered the construct.

One case per construct, so a decomposition regression names the construct that
broke instead of surfacing as a mystery elsewhere.
"""

import unittest

from toolguard.testing.sandbox import experiment

#: allow-everything plus one narrow deny, so any non-deny result means the deny
#: rule failed to reach the command rather than that nothing matched.
_CONFIG = """no_match_fallback = "ask"

[permissions]
allow = ["Bash(*)"]
deny = ["Bash(rm:*)"]
"""

_DENIED = "rm -rf /tmp/zz"

#: (construct name, command embedding _DENIED in that construct).
_CONSTRUCTS = [
    ("bare", _DENIED),
    ("sequence", f"echo a; {_DENIED}"),
    ("and_list", f"echo a && {_DENIED}"),
    ("or_list", f"echo a || {_DENIED}"),
    ("pipeline", f"echo a | {_DENIED}"),
    ("background", f"{_DENIED} &"),
    ("subshell", f"( {_DENIED} )"),
    ("brace_group", f"{{ {_DENIED}; }}"),
    ("nested_subshell", f"( ( {_DENIED} ) )"),
    ("command_substitution", f"echo $({_DENIED})"),
    ("backticks", f"echo `{_DENIED}`"),
    ("if_then", f"if true; then {_DENIED}; fi"),
    ("while_loop", f"while true; do {_DENIED}; done"),
    ("for_loop", f"for i in 1; do {_DENIED}; done"),
    ("output_redirect", f"{_DENIED} > /tmp/log"),
    ("env_assignment", f"FOO=bar {_DENIED}"),
    ("stripped_wrapper", f"timeout 5 {_DENIED}"),
]


class TestDenyReachesInsideEveryConstruct(unittest.TestCase):
    """Each construct gets its own subTest, so a failure names the construct."""

    def test_a_deny_rule_matches_the_command_inside_each_construct(self):
        """
        Given deny Bash(rm:*) alongside a blanket allow
        When a denied command is embedded in each supported shell construct
        Then every one is denied -- a construct whose contents stop being
             decomposed would otherwise silently fall through to the allow
        """
        with experiment(project_config=_CONFIG) as sandbox:
            for name, command in _CONSTRUCTS:
                with self.subTest(construct=name):
                    self.assertEqual(
                        sandbox.evaluate("Bash", command).decision,
                        "deny",
                        f"deny rule did not reach inside {name}: {command!r}",
                    )

    def test_an_undenied_command_is_still_allowed_in_each_construct(self):
        """
        Given the same rules
        When a command NOT matched by the deny is embedded in each construct
        Then it is allowed -- proving the test above fails for the right reason
             and not because every construct denies everything
        """
        with experiment(project_config=_CONFIG) as sandbox:
            for name, command in _CONSTRUCTS:
                benign = command.replace(_DENIED, "echo safe")
                with self.subTest(construct=name):
                    self.assertEqual(
                        sandbox.evaluate("Bash", benign).decision,
                        "allow",
                        f"benign command was not allowed inside {name}: {benign!r}",
                    )


if __name__ == "__main__":
    unittest.main()
