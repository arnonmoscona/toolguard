"""
Unit tests for :mod:`toolguard.permission_resolution`.

Most cascade coverage predates this file and still lives where the code used
to: ``test_configuration.py``, ``test_hard_deny.py``, ``test_hierarchical.py``,
``test_logging_streams.py`` and ``test_takeover_mode.py``.
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
    file I/O, so no ``ConfigIsolationMixin`` is needed.

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
    ``_apply_ask_floor`` must never weaken a genuine ``deny``, including
    clearing the fields that explain it.

    Deleting the ``or resolved.decision == "deny"`` guard from its early
    return once left the whole suite and the golden corpus green while a deny
    made under a parse-failing config silently lost its provenance,
    ``additionalContext`` and matched rule. This is the guard that was missing.
    """

    def test_deny_under_parse_failure_retains_provenance_context_and_matched_rule(
        self,
    ):
        """
        Given a Configuration with BOTH a recorded parse_failures entry for a
            broken file AND a deny rule (carrying additionalContext) that
            matches the command
        When resolve_command_permission('Bash', ...) resolves the command
        Then the decision is 'deny', and its provenance, additional_context
            AND matched_rule all survive unchanged -- the parse-failure ASK
            floor never weakens a deny, so the explanation for it must
            survive too. All three are asserted together because the bug
            loses all three at once.
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
        Then the decision is 'ask' -- the floor still clamps a non-deny
            decision

        Negative control for the sibling above: clamping everything would
        break that one, clamping nothing would break this one. The
        'no_match_fallback' is 'ask' rather than the sibling's 'deny' so the
        no-match branch cannot itself produce the deny under test.
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
