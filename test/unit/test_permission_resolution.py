"""
Unit tests for :mod:`toolguard.permission_resolution`.

Owns the TOO-19 parse-failure ASK floor and its interaction with the
more-specific-wins cascade. Plain cascade coverage (child-beats-parent,
deny-first within a level, no-match fallback) predates this file and still
lives where the code used to: ``test_configuration.py``, ``test_hard_deny.py``,
``test_hierarchical.py``, ``test_logging_streams.py`` and
``test_takeover_mode.py``.
"""

import unittest
from pathlib import Path
from types import MappingProxyType

from toolguard.config import Configuration, ConfigLayer, Provenance
from toolguard.permission_resolution import (
    apply_parse_failure_floor,
    resolve_command_permission,
    resolve_file_path_permission,
)

_PROJECT_PATH = Path("/p/.claude/toolguard_hook.toml")
_USER_PATH = Path("/h/.claude/toolguard_hook.toml")
_BROKEN_PATH = Path("/p/.claude/toolguard_hook.local.toml")
#: A configuration's ``parse_failures`` naming one unparseable file.
_PARSE_FAILURES = ((_BROKEN_PATH, "unexpected character"),)


def _layer(level, path, *, allow=(), deny=(), specificity=0, **settings):
    """
    Build one :class:`ConfigLayer` with zero file I/O, so no
    ``ConfigIsolationMixin`` is needed.

    Args:
        level: Provenance level label, e.g. ``'project'`` or ``'user'``.
        path: Display path recorded on the provenance.
        allow: Raw ``permissions.allow`` entries as they would appear in TOML --
            either bare ``'Bash(...)'`` strings or
            ``{"match": ..., "additionalContext": ...}`` dicts.
        deny: Same, for ``permissions.deny``.
        specificity: Hierarchy distance from the project root; layers sharing a
            value collapse into one level. Two levels need two distinct values.
        settings: Extra top-level ``toolguard_hook`` keys, e.g.
            ``no_match_fallback``.
    """
    content = dict(settings)
    content["permissions"] = {"allow": list(allow), "deny": list(deny)}
    return ConfigLayer(
        Provenance(level, "toolguard_hook", "toml", path, specificity),
        MappingProxyType(content),
    )


def _config(*layers, parse_failures=()):
    """Build a :class:`Configuration` from hand-built layers, most-specific first."""
    return Configuration(layers=layers, parse_failures=parse_failures)


def _project_bash_config(
    *, allow=(), deny=(), parse_failures=(), no_match_fallback="allow_with_warning"
):
    """
    Build a single-layer, project-level Bash :class:`Configuration`.

    ``no_match_fallback`` defaults to ``'allow_with_warning'`` so an unmatched
    command resolves to ``allow`` BEFORE the floor runs. Every other value
    makes the floor's output indistinguishable from the fallback's: with
    ``'ask'`` the clamp is a no-op on the decision, and with ``'deny'`` the
    fallback produces the same ``deny`` the floor's exemption is supposed to
    preserve.
    """
    return _config(
        _layer(
            "project",
            _PROJECT_PATH,
            allow=allow,
            deny=deny,
            no_match_fallback=no_match_fallback,
        ),
        parse_failures=parse_failures,
    )


#: A deny rule carrying an ``additionalContext``, so a verdict built from it
#: has provenance, context and matched rule to lose.
_DENY_RM = {"match": "Bash(rm -rf *)", "additionalContext": "see incident 42"}


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
            matches the command, under no_match_fallback=allow_with_warning so
            no unmatched-command branch can produce a deny
        When resolve_command_permission('Bash', ...) resolves the command
        Then the decision is 'deny', and its provenance, additional_context
            AND matched_rule all survive unchanged -- the parse-failure ASK
            floor never weakens a deny, so the explanation for it must
            survive too. All four are asserted together because the bug
            loses the last three at once.
        """
        config = _project_bash_config(deny=[_DENY_RM], parse_failures=_PARSE_FAILURES)

        resolved = resolve_command_permission(config, "Bash", "rm -rf /tmp/x")

        self.assertEqual(resolved.decision, "deny")
        self.assertIsNotNone(resolved.provenance)
        self.assertEqual(resolved.provenance.path, _PROJECT_PATH)
        self.assertEqual(resolved.additional_context, "see incident 42")
        self.assertEqual(resolved.matched_rule, "rm -rf *")

    def test_allow_under_same_parse_failure_is_clamped_from_allow_to_ask(self):
        """
        Given the SAME broken-config parse_failures entry, but a command that
            matches nothing, so the no_match_fallback=allow_with_warning
            branch resolves it to 'allow'
        When resolve_command_permission('Bash', ...) resolves the command
        Then the decision is clamped to 'ask', the reason names the broken
            file, and fallback_warning is cleared -- the clamp rebuilds the
            verdict rather than editing the decision in place

        Negative control for the sibling above: clamping everything would
        break that one, clamping nothing would break this one.
        """
        config = _project_bash_config(deny=[_DENY_RM], parse_failures=_PARSE_FAILURES)

        resolved = resolve_command_permission(config, "Bash", "ls -la")

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(_BROKEN_PATH), resolved.reason)
        self.assertFalse(resolved.fallback_warning)

    def test_floor_is_inert_when_no_config_file_failed_to_parse(self):
        """
        Given the SAME config with an EMPTY parse_failures
        When the two commands of the tests above are resolved
        Then the unmatched one keeps its no_match_fallback 'allow' and its
            fallback_warning, and the matched one keeps its deny -- the floor
            changes nothing when nothing failed to parse
        """
        config = _project_bash_config(deny=[_DENY_RM])

        unmatched = resolve_command_permission(config, "Bash", "ls -la")
        self.assertEqual(unmatched.decision, "allow")
        self.assertTrue(unmatched.fallback_warning)
        self.assertNotIn(str(_BROKEN_PATH), unmatched.reason)

        matched = resolve_command_permission(config, "Bash", "rm -rf /tmp/x")
        self.assertEqual(matched.decision, "deny")
        self.assertEqual(matched.matched_rule, "rm -rf *")


class TestApplyParseFailureFloorDirectly(unittest.TestCase):
    """
    The public ``apply_parse_failure_floor`` carries its OWN copy of the
    already-deny exemption, and ``_apply_ask_floor``'s identical-looking guard
    returns first on exactly the input that would exercise it -- so on the
    command path this copy is unreachable, and deleting it changes nothing any
    test above can see. Measured: it is the one mutation of the floor these
    tests miss when the function is only reached through
    ``resolve_command_permission``.
    """

    def test_already_deny_is_returned_unchanged_under_parse_failures(self):
        """
        Given a non-empty parse_failures and a ('deny', reason) pair
        When apply_parse_failure_floor clamps it
        Then both the decision AND the original reason come back untouched
        """
        result = apply_parse_failure_floor(_PARSE_FAILURES, "deny", "matched rm -rf *")

        self.assertEqual(result, ("deny", "matched rm -rf *"))

    def test_non_deny_is_clamped_and_the_reason_names_every_broken_file(self):
        """
        Given a parse_failures naming TWO broken files and an ('allow', reason)
        When apply_parse_failure_floor clamps it
        Then the decision is 'ask' and the rebuilt reason names both files with
            their messages, and no longer carries the original reason
        """
        second = Path("/h/.claude/toolguard_hook.toml")
        failures = _PARSE_FAILURES + ((second, "duplicate key"),)

        decision, reason = apply_parse_failure_floor(failures, "allow", "matched git *")

        self.assertEqual(decision, "ask")
        self.assertIn(str(_BROKEN_PATH), reason)
        self.assertIn("unexpected character", reason)
        self.assertIn(str(second), reason)
        self.assertIn("duplicate key", reason)
        self.assertNotIn("matched git *", reason)

    def test_empty_parse_failures_returns_the_pair_unchanged(self):
        """
        Given an EMPTY parse_failures and an ('allow', reason) pair
        When apply_parse_failure_floor is called
        Then the pair comes back untouched -- the floor is keyed on parse
            failures, not applied unconditionally
        """
        result = apply_parse_failure_floor((), "allow", "matched git *")

        self.assertEqual(result, ("allow", "matched git *"))


class TestFloorInteractionWithTheCascade(unittest.TestCase):
    """
    The floor runs AFTER the more-specific-wins fold, on its result -- so an
    allow that won over a less-specific deny is still clamped, and the
    ``ConflictOverride`` recorded to explain that win does not survive the
    clamp.
    """

    def _two_level_config(self, *, parse_failures=()):
        """Project allows ``git push``; the less-specific user level denies it."""
        return _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=["Bash(git push:*)"],
                specificity=0,
                no_match_fallback="allow_with_warning",
            ),
            _layer("user", _USER_PATH, deny=["Bash(git push:*)"], specificity=9),
            parse_failures=parse_failures,
        )

    def test_more_specific_allow_wins_and_records_the_overridden_deny(self):
        """
        Given a project-level allow and a less-specific user-level deny for the
            same command, and a config that parsed cleanly
        When resolve_command_permission resolves it
        Then the allow wins, and a single ConflictOverride names the user
            level's deny as the overridden rule
        """
        resolved = resolve_command_permission(
            self._two_level_config(), "Bash", "git push origin main"
        )

        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(resolved.matched_rule, "git push:*")
        self.assertEqual(len(resolved.overrides), 1)
        _sub_command, override = resolved.overrides[0]
        self.assertEqual(override.overridden_pattern, "git push:*")
        self.assertEqual(override.overridden_provenance.path, _USER_PATH)
        self.assertEqual(override.winning_provenance.path, _PROJECT_PATH)

    def test_floor_clamps_the_winning_allow_and_drops_its_override(self):
        """
        Given the SAME two levels, now with a recorded parse failure
        When resolve_command_permission resolves the same command
        Then the winning allow is clamped to 'ask', and provenance and the
            ConflictOverride are gone -- they describe a rule match that no
            longer determines the verdict
        """
        resolved = resolve_command_permission(
            self._two_level_config(parse_failures=_PARSE_FAILURES),
            "Bash",
            "git push origin main",
        )

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(_BROKEN_PATH), resolved.reason)
        self.assertIsNone(resolved.provenance)
        self.assertEqual(resolved.overrides, [])
        self.assertIsNone(resolved.matched_rule)


class TestFloorCoversFilePathTools(unittest.TestCase):
    """
    The floor is applied in ``resolve_permission_cascade``, which both
    ``resolve_command_permission`` and ``resolve_file_path_permission`` fold
    through -- so it covers Read/Write/Edit, not only Bash.
    """

    def _read_config(self, *, parse_failures=()):
        return _config(
            _layer("project", _PROJECT_PATH, allow=["Read(/etc/**)"]),
            parse_failures=parse_failures,
        )

    def test_read_path_allowed_by_a_rule_is_clamped_to_ask_under_parse_failure(self):
        """
        Given a Read allow rule matching the path, and a recorded parse failure
        When resolve_file_path_permission resolves the path
        Then the decision is 'ask' and the reason names the broken file
        """
        resolved = resolve_file_path_permission(
            self._read_config(parse_failures=_PARSE_FAILURES), "Read", "/etc/hosts"
        )

        self.assertEqual(resolved.decision, "ask")
        self.assertIn(str(_BROKEN_PATH), resolved.reason)

    def test_same_read_path_is_allowed_when_the_config_parses(self):
        """
        Given the SAME Read allow rule and an EMPTY parse_failures
        When resolve_file_path_permission resolves the path
        Then the decision is 'allow' -- the clamp above came from the parse
            failure, not from file-path resolution being ask-by-default
        """
        resolved = resolve_file_path_permission(
            self._read_config(), "Read", "/etc/hosts"
        )

        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(resolved.matched_rule, "/etc/**")


if __name__ == "__main__":
    unittest.main()
