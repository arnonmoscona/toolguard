"""
Unit tests for :mod:`toolguard.permission_resolution` (TOO-45 D1a review-debt
item G).

The module's tests stayed where the code used to live -- ~28 existing cascade
call sites are spread across ``test_configuration.py``, ``test_hard_deny.py``,
``test_hierarchical.py``, ``test_logging_streams.py``, and
``test_takeover_mode.py``. This file is the module's own new home, for the
NEW invariants added by the TOO-45 D1a review (see the two test classes
below) -- deliberately NOT a relocation of the existing call sites, which
would be churn without benefit and would obscure this change set.

Run with:
    uv run python -m unittest discover -s test -t .
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.config import Configuration, ConfigLayer, Provenance, TakeoverConfig
from toolguard.permission_resolution import resolve_command_permission


def _project_bash_config(*, deny=(), parse_failures=()):
    """
    Build a single-layer, project-level Bash :class:`Configuration` with zero
    file I/O (hand-constructed :class:`ConfigLayer`/:class:`Provenance`), so
    no ``ConfigIsolationMixin`` is needed -- per
    ``test/unit/CLAUDE.md``'s checklist and the identical precedent in
    ``test_configuration.py``'s ``TestParseFailureAskFloor``.

    Args:
        deny: Raw ``permissions.deny`` entries as they would appear in TOML --
            either bare ``'Bash(...)'`` strings or
            ``{"match": ..., "additionalContext": ...}`` dicts.
        parse_failures: ``(path, message)`` pairs to record on the built
            :class:`Configuration`.
    """
    prov = Provenance(
        "project", "toolguard_hook", "toml", Path("/p/.claude/toolguard_hook.toml")
    )
    layer = ConfigLayer(
        prov,
        MappingProxyType({"permissions": {"allow": [], "deny": list(deny)}}),
    )
    return Configuration(layers=(layer,), parse_failures=parse_failures)


class TestDenyUnderBrokenConfigKeepsProvenance(unittest.TestCase):
    """
    TOO-45 D1a review debt, item A (the highest-value item in that review).

    ``_apply_ask_floor`` (``permission_resolution.py:160``) must never weaken
    a genuine ``deny`` -- including clearing the fields that explain it. A
    reviewer once deleted the ``or resolved.decision == "deny"`` guard from
    that function's early-return condition and the entire 2,321-test suite
    plus the 6,401-case golden corpus stayed green, even though the deletion
    changes real output: a deny made under a config that ALSO has a parse
    failure would silently lose its provenance, its ``additionalContext``,
    and its matched rule. This test is the guard that was missing.
    """

    def test_deny_under_parse_failure_retains_provenance_context_and_matched_rule(
        self,
    ):
        """
        Given a Configuration with BOTH a recorded parse_failures entry for a
            broken file AND a deny rule (carrying additionalContext) that
            matches the command
        When resolve_command_permission('Bash', ...) resolves the command
        Then the decision is 'deny', and its provenance, additional_context,
            AND matched_rule are all preserved unchanged -- the parse-failure
            ASK floor never weakens a deny, so the explanation for why it was
            denied must survive intact. All three are asserted together
            because the bug this test guards against loses all three at
            once; a test checking only one of them would not have caught it.
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        config = _project_bash_config(
            deny=[{"match": "Bash(rm -rf *)", "additionalContext": "see incident 42"}],
            parse_failures=((broken, "unexpected character"),),
        )

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "deny"),
        ):
            resolved = resolve_command_permission(config, "Bash", "rm -rf /tmp/x")

        self.assertEqual(resolved.decision, "deny")
        self.assertIsNotNone(resolved.provenance)
        self.assertEqual(
            resolved.provenance.path, Path("/p/.claude/toolguard_hook.toml")
        )
        self.assertEqual(resolved.additional_context, "see incident 42")
        self.assertEqual(resolved.matched_rule, "rm -rf *")

    def test_allow_under_same_parse_failure_is_still_clamped_to_ask(self):
        """
        Given the SAME broken-config parse_failures entry, but a command that
            matches nothing (no deny rule fires)
        When resolve_command_permission('Bash', ...) resolves the command
        Then the decision is 'ask' -- the floor's normal clamping behaviour
            for a non-deny decision is unaffected by this test module's new
            deny-preservation coverage; a regression that clamped everything
            (including denies) would break this test's sibling above, and a
            regression that clamped nothing would break this one

        Negative control for the test above: confirms the floor still fires
        normally when there is no deny to protect. Uses a 'no_match_fallback'
        of 'ask' explicitly (rather than the sibling test's 'deny') so a
        deny-configured Configuration's no-match branch does not itself
        resolve to 'deny' before the floor ever runs -- that would conflate
        "the floor let a pre-existing deny through" with "the floor clamped
        an allow/ask", which is exactly the distinction this pair of tests
        exists to keep separate.
        """
        broken = Path("/p/.claude/toolguard_hook.local.toml")
        config = _project_bash_config(
            deny=[{"match": "Bash(rm -rf *)", "additionalContext": "see incident 42"}],
            parse_failures=((broken, "unexpected character"),),
        )

        with patch.object(
            Configuration,
            "takeover_mode",
            return_value=TakeoverConfig(False, (), (), "ask"),
        ):
            resolved = resolve_command_permission(config, "Bash", "ls -la")

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(broken), resolved.reason)


if __name__ == "__main__":
    unittest.main()
