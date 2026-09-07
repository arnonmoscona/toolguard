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
from toolguard.config import _FALLBACK_SETTINGS
from toolguard.invocation import Invocation
from toolguard.permission_resolution import (
    apply_parse_failure_floor,
    resolve_command_permission,
    resolve_file_path_permission,
)
from toolguard.resolve import resolve_bash_permission_detailed

_PROJECT_PATH = Path("/p/.claude/toolguard_hook.toml")
_USER_PATH = Path("/h/.claude/toolguard_hook.toml")
_BROKEN_PATH = Path("/p/.claude/toolguard_hook.local.toml")
#: A configuration's ``parse_failures`` naming one unparseable file.
_PARSE_FAILURES = ((_BROKEN_PATH, "unexpected character"),)


def _layer(level, path, *, allow=(), deny=(), ask=(), specificity=0, **settings):
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
        ask: Same, for ``permissions.ask``.
        specificity: Hierarchy distance from the project root; layers sharing a
            value collapse into one level. Two levels need two distinct values.
        settings: Extra top-level ``toolguard_hook`` keys, e.g.
            ``no_match_fallback``.
    """
    # Refuse rather than overwrite: 'permissions' arriving via **settings would be
    # silently replaced by the allow=/deny=/ask= rebuild below, leaving a test that
    # asserts against no rules at all and passes for the wrong reason.
    if "permissions" in settings:
        raise TypeError("pass rules via allow=/deny=/ask=, not permissions=")
    content = dict(settings)
    content["permissions"] = {
        "allow": list(allow),
        "deny": list(deny),
        "ask": list(ask),
    }
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

        resolved = resolve_command_permission(
            Invocation.for_evaluation(config), "rm -rf /tmp/x"
        )

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

        resolved = resolve_command_permission(
            Invocation.for_evaluation(config), "ls -la"
        )

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
        context = Invocation.for_evaluation(config)

        unmatched = resolve_command_permission(context, "ls -la")
        self.assertEqual(unmatched.decision, "allow")
        self.assertTrue(unmatched.fallback_warning)
        self.assertNotIn(str(_BROKEN_PATH), unmatched.reason)

        matched = resolve_command_permission(context, "rm -rf /tmp/x")
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
            Invocation.for_evaluation(self._two_level_config()),
            "git push origin main",
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
            Invocation.for_evaluation(
                self._two_level_config(parse_failures=_PARSE_FAILURES)
            ),
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
            Invocation.for_evaluation(
                self._read_config(parse_failures=_PARSE_FAILURES), tool_name="Read"
            ),
            "/etc/hosts",
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
            Invocation.for_evaluation(self._read_config(), tool_name="Read"),
            "/etc/hosts",
        )

        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(resolved.matched_rule, "/etc/**")


class TestParseFailureFloorHoldsForEveryRegisteredFallbackSetting(unittest.TestCase):
    """
    The parse-failure ASK floor must hold for every
    fallback-shaped setting, not just today's two. Iterates
    ``toolguard.config._FALLBACK_SETTINGS`` -- the single declared registry also read by
    ``Configuration.unrecognized_fallback_settings`` -- instead of naming settings by
    hand, so a future setting added to that registry is automatically covered here too:
    adding a setting to the registry is what makes it visible to the diagnostic, and the
    same addition pulls it under this invariant with no second place to remember.
    """

    def _resolve(self, setting, value, permission_mode):
        """Resolve a floor-triggering command with *setting* set to *value*, under a recorded parse failure."""
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=["Bash(git:*)", "Bash(python3 -c:*)"],
                **{setting.key: value},
            ),
            parse_failures=_PARSE_FAILURES,
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode=permission_mode,
        )
        command = "ls -la" if setting.kind == "no_match" else 'python3 -c "import os"'
        return resolve_bash_permission_detailed(command, invocation)

    def test_floor_holds_for_every_setting_value_and_mode(self):
        """
        Given every setting in the fallback-settings registry, each of its valid
            values in turn, under a recorded parse failure, and under every
            permission_mode where that setting's value is actually consulted
            (both modes for a base setting; only 'auto' for an auto-only one --
            testing an auto-only setting's value under a mode where it is never
            read would assert nothing about that setting)
        When the corresponding floor-triggering command is resolved
        Then the decision is 'ask' in every case except 'deny', which the
            floor's already-deny exemption leaves unchanged -- regardless of
            which registered setting supplied the value or which of its
            consulted modes was in effect
        """
        for setting in _FALLBACK_SETTINGS:
            modes = ("auto",) if setting.auto_only else ("auto", "default")
            for value in sorted(setting.valid_values):
                want = "deny" if value == "deny" else "ask"
                for mode in modes:
                    with self.subTest(setting=setting.key, value=value, mode=mode):
                        result = self._resolve(setting, value, mode)
                        self.assertEqual(result.decision, want)


class TestNoMatchFallbackAutoMode(unittest.TestCase):
    """
    resolve_command_permission() consults no_match_fallback_in_auto_mode
    instead of no_match_fallback when Invocation.permission_mode is the auto mode,
    and leaves the base setting's own behaviour untouched otherwise.
    """

    def _build_config(
        self, *, no_match_fallback=None, no_match_fallback_in_auto_mode=None, **kw
    ):
        """
        Build a config with the given top-level keys set, omitting any left None.

        Always carries an unrelated deny rule so has_any_rules() is True and an
        unmatched "ls -la" reaches the no_match_fallback branch, rather than the
        separate "tool entirely unconfigured" branch that always resolves 'ask'
        regardless of no_match_fallback.
        """
        settings = dict(kw)
        if no_match_fallback is not None:
            settings["no_match_fallback"] = no_match_fallback
        if no_match_fallback_in_auto_mode is not None:
            settings["no_match_fallback_in_auto_mode"] = no_match_fallback_in_auto_mode
        return _config(
            _layer("project", _PROJECT_PATH, deny=["Bash(rm -rf /)"], **settings)
        )

    def _resolve(self, config, command, *, permission_mode=None):
        """Resolve *command* with the given Invocation.permission_mode."""
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode=permission_mode,
        )
        return resolve_command_permission(invocation, command)

    def test_auto_mode_setting_applies_only_under_auto_permission_mode(self):
        """
        Given no_match_fallback_in_auto_mode='allow' and the base
            no_match_fallback left at its 'ask' default
        When an unmatched command is resolved once under
            permission_mode='auto' and once under permission_mode='default'
        Then the auto-mode call resolves to 'allow' and the default-mode call
            resolves to 'ask' -- the mode alone selects which setting governs
        """
        config = self._build_config(no_match_fallback_in_auto_mode="allow")

        auto_result = self._resolve(config, "ls -la", permission_mode="auto")
        default_result = self._resolve(config, "ls -la", permission_mode="default")

        self.assertEqual(auto_result.decision, "allow")
        self.assertEqual(default_result.decision, "ask")

    def test_unset_auto_mode_setting_is_inert_even_under_auto_mode(self):
        """
        Given ONLY the base no_match_fallback='deny' set, with
            no_match_fallback_in_auto_mode left UNSET
        When an unmatched command is resolved under permission_mode='auto'
        Then the decision is 'deny' -- the SAME as under any other mode --
            proving an unset auto-mode setting changes nothing
        """
        config = self._build_config(no_match_fallback="deny")

        auto_result = self._resolve(config, "ls -la", permission_mode="auto")
        default_result = self._resolve(config, "ls -la", permission_mode="default")

        self.assertEqual(auto_result.decision, "deny")
        self.assertEqual(default_result.decision, "deny")

    # A broken-config/parse-failure test for this setting used to live here as its
    # own method; it is now subsumed by
    # TestParseFailureFloorHoldsForEveryRegisteredFallbackSetting, which covers the
    # same assertion (and every other registered setting/value/mode combination)
    # from one registry-driven test instead of one method per setting.

    def test_no_match_and_undecidable_auto_mode_settings_are_independent(self):
        """
        Given a SINGLE config setting no_match_fallback_in_auto_mode='allow'
            AND undecidable_fallback_in_auto_mode='deny' together, under
            permission_mode='auto'
        When a plain no-match command is resolved
        Then it is ALLOWED -- governed only by no_match_fallback_in_auto_mode,
            proving the two auto-mode settings do not couple (the undecidable
            side of the same config is exercised in
            test_resolve.TestUndecidableFallbackAutoMode)
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=["Bash(rm -rf /)"],
                no_match_fallback_in_auto_mode="allow",
                undecidable_fallback_in_auto_mode="deny",
            )
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode="auto",
        )

        resolved = resolve_command_permission(invocation, "ls -la")

        self.assertEqual(resolved.decision, "allow")


class TestPerRuleAutoModeBehavior(unittest.TestCase):
    """
    A matched rule's own ``auto_mode_behavior`` replaces its list's
    decision only when ``permission_mode == 'auto'``, applied AFTER provenance and
    ``additionalContext`` resolve against the rule's REAL matched decision -- so both
    still attribute to the rule that actually decided, even though the effective
    decision changed.
    """

    def _resolve(self, config, command, permission_mode):
        """Resolve *command* with the given Invocation.permission_mode."""
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode=permission_mode,
        )
        return resolve_command_permission(invocation, command)

    def test_widening_ask_rule_allows_under_auto_and_still_asks_under_default(self):
        """
        Given an ask rule declaring auto_mode_behavior='allow'
        When the matching command is resolved once under permission_mode='auto'
            and once under 'default'
        Then the auto-mode call allows and the default-mode call still asks
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[{"match": "Bash(git push:*)", "auto_mode_behavior": "allow"}],
            )
        )
        auto_result = self._resolve(config, "git push origin main", "auto")
        default_result = self._resolve(config, "git push origin main", "default")

        self.assertEqual(auto_result.decision, "allow")
        self.assertEqual(default_result.decision, "ask")

    def test_narrowing_ask_rule_denies_under_auto_and_still_asks_under_default(self):
        """
        Given an ask rule declaring auto_mode_behavior='deny'
        When the matching command is resolved once under permission_mode='auto'
            and once under 'default'
        Then the auto-mode call denies and the default-mode call still asks
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[{"match": "Bash(git push:*)", "auto_mode_behavior": "deny"}],
            )
        )
        auto_result = self._resolve(config, "git push origin main", "auto")
        default_result = self._resolve(config, "git push origin main", "default")

        self.assertEqual(auto_result.decision, "deny")
        self.assertEqual(default_result.decision, "ask")

    def test_rule_without_the_key_behaves_identically_under_every_mode(self):
        """
        Given an ordinary ask rule with no auto_mode_behavior at all
        When the matching command is resolved under 'auto', 'default', and None
        Then every mode resolves to 'ask' -- unset means unchanged, which is
            what makes the corpus equivalence result (unset everywhere) mean
            something
        """
        config = _config(_layer("project", _PROJECT_PATH, ask=["Bash(git push:*)"]))
        for mode in ("auto", "default", None):
            with self.subTest(mode=mode):
                result = self._resolve(config, "git push origin main", mode)
                self.assertEqual(result.decision, "ask")

    def test_provenance_and_additional_context_survive_widening(self):
        """
        Given an ask rule carrying BOTH additionalContext and
            auto_mode_behavior='allow', under permission_mode='auto'
        When the matching command is resolved
        Then the decision is 'allow', but matched_rule, provenance, and
            additional_context all still attribute to the SAME ask rule that
            actually matched -- proving the provenance/entry lookup used the
            rule's real ('ask') decision, not the post-auto-mode 'allow'
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[
                    {
                        "match": "Bash(git push:*)",
                        "additionalContext": "needs review",
                        "auto_mode_behavior": "allow",
                    }
                ],
            )
        )

        result = self._resolve(config, "git push origin main", "auto")

        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "git push:*")
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.path, _PROJECT_PATH)
        self.assertEqual(result.additional_context, "needs review")

    def test_provenance_and_additional_context_survive_widening_from_deny(self):
        """
        Given a DENY rule carrying additionalContext and
            auto_mode_behavior='allow', under permission_mode='auto' -- the
            ordering trap's sharpest case, since 'deny' and 'allow' are
            DIFFERENT lists a naive reorder would search
        When the matching command is resolved
        Then the decision is 'allow', but matched_rule, provenance, and
            additional_context still attribute to the DENY rule that actually
            matched
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=[
                    {
                        "match": "Bash(rm -rf *)",
                        "additionalContext": "classifier trusted here",
                        "auto_mode_behavior": "allow",
                    }
                ],
            )
        )

        result = self._resolve(config, "rm -rf /tmp/x", "auto")

        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "rm -rf *")
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.path, _PROJECT_PATH)
        self.assertEqual(result.additional_context, "classifier trusted here")

    def test_provenance_survives_narrowing_from_allow(self):
        """
        Given an ALLOW rule declaring auto_mode_behavior='ask', under
            permission_mode='auto'
        When the matching command is resolved
        Then the decision is 'ask', and matched_rule/provenance still
            attribute to the ALLOW rule that actually matched
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(git push:*)", "auto_mode_behavior": "ask"}],
            )
        )

        result = self._resolve(config, "git push origin main", "auto")

        self.assertEqual(result.decision, "ask")
        self.assertEqual(result.matched_rule, "git push:*")
        self.assertIsNotNone(result.provenance)

    def test_deny_may_widen_to_allow_no_config_error(self):
        """
        Given a deny rule declaring auto_mode_behavior='allow'
        When the config is built and the matching command is resolved under
            'auto'
        Then it resolves cleanly to 'allow' -- Arnon, 2026-09-07: any list may
            declare any decision, the classifier is the second gate the user
            chose to trust; only [hard_deny] is unconditional (see
            TestHardDenyRegressionGuards)
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=[{"match": "Bash(rm -rf *)", "auto_mode_behavior": "allow"}],
            )
        )

        result = self._resolve(config, "rm -rf /tmp/x", "auto")

        self.assertEqual(result.decision, "allow")

    def test_widened_allow_is_still_checked_for_an_override_conflict(self):
        """
        Given a less-specific user-level deny and a more-specific project-level
            ask rule for the same command, the ask rule declaring
            auto_mode_behavior='allow'
        When the command is resolved under permission_mode='auto'
        Then the decision is 'allow' AND a ConflictOverride is recorded --
            the override check runs against the EFFECTIVE (post-auto-mode)
            decision, since this is now a genuine allow needing the same
            allow-over-deny conflict logging any other allow gets
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[{"match": "Bash(git push:*)", "auto_mode_behavior": "allow"}],
                specificity=0,
            ),
            _layer("user", _USER_PATH, deny=["Bash(git push:*)"], specificity=9),
        )

        result = self._resolve(config, "git push origin main", "auto")

        self.assertEqual(result.decision, "allow")
        self.assertEqual(len(result.overrides), 1)

    def test_override_provenance_names_the_overridden_rules_real_list_when_it_too_migrated(
        self,
    ):
        """
        Given a more-specific ask rule declaring auto_mode_behavior='allow' (the
            winner), and a LESS-specific ALLOW rule declaring
            auto_mode_behavior='deny' for the same command -- the overridden
            rule ALSO migrated groups, so its provenance lookup hits the same
            ordering trap the winning rule's does
        When the command is resolved under permission_mode='auto'
        Then the decision is 'allow' with one override recorded, and the
            override's overridden_provenance is not None -- the lookup found
            the overridden rule in its real (allow) list, not the (deny) list
            its effective decision would suggest
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[{"match": "Bash(git push:*)", "auto_mode_behavior": "allow"}],
                specificity=0,
            ),
            _layer(
                "user",
                _USER_PATH,
                allow=[{"match": "Bash(git push:*)", "auto_mode_behavior": "deny"}],
                specificity=9,
            ),
        )

        result = self._resolve(config, "git push origin main", "auto")

        self.assertEqual(result.decision, "allow")
        self.assertEqual(len(result.overrides), 1)
        _, override = result.overrides[0]
        self.assertIsNotNone(override.overridden_provenance)
        self.assertEqual(override.overridden_provenance.path, _USER_PATH)

    def test_allow_migrated_to_deny_wins_deny_first_precedence_over_a_matching_ask(
        self,
    ):
        """
        Given, in the SAME level, an allow rule declaring auto_mode_behavior='deny'
            and an unrelated ask rule that ALSO matches the same command
        When resolved under permission_mode='auto'
        Then the decision is 'deny' -- the migrated rule competes on its
            EFFECTIVE group's precedence (deny-first beats ask), not the
            precedence of the list it is written in (Arnon, 2026-09-07: "a
            rule's group determines its precedence")
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {"match": "Bash(mycmd *)", "auto_mode_behavior": "deny"},
                ],
                ask=["Bash(mycmd --dangerous*)"],
            )
        )

        result = self._resolve(config, "mycmd --dangerous now", "auto")

        self.assertEqual(result.decision, "deny")

    def test_provenance_and_additional_context_survive_narrowing_to_deny(self):
        """
        Given an ALLOW rule carrying additionalContext and
            auto_mode_behavior='deny', under permission_mode='auto' -- the
            mirror of the deny-widened-to-allow case, this time narrowing
        When the matching command is resolved
        Then the decision is 'deny', but matched_rule, provenance, and
            additional_context still attribute to the ALLOW rule that
            actually matched, not to any deny-list entry
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {
                        "match": "Bash(mycmd *)",
                        "additionalContext": "auto-denied by classifier",
                        "auto_mode_behavior": "deny",
                    }
                ],
            )
        )

        result = self._resolve(config, "mycmd --dangerous now", "auto")

        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "mycmd *")
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.path, _PROJECT_PATH)
        self.assertEqual(result.additional_context, "auto-denied by classifier")

    def test_reason_names_the_rules_real_list_not_its_effective_one(self):
        """
        Given a DENY rule declaring auto_mode_behavior='allow', under
            permission_mode='auto'
        When the matching command is resolved
        Then the reason's base clause says "matches deny pattern" -- the
            rule's REAL list, so a reader grepping the deny list finds it --
            and the suffix separately states the effective decision
            (Arnon, 2026-09-07: "the provenance of the rule is still in the
            actual group it resides in"; the sentence must say so too, not
            just the Provenance object)
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=[{"match": "Bash(rm -rf *)", "auto_mode_behavior": "allow"}],
            )
        )

        result = self._resolve(config, "rm -rf /tmp/x", "auto")

        self.assertEqual(result.decision, "allow")
        self.assertIn("matches deny pattern: rm -rf *", result.reason)
        self.assertNotIn("matches allow pattern", result.reason)
        self.assertIn("auto_mode_behavior='allow'", result.reason)
        self.assertIn("applied", result.reason)

    def test_reason_names_the_real_list_in_the_narrowing_direction_too(self):
        """
        Given an ALLOW rule declaring auto_mode_behavior='deny', under
            permission_mode='auto' -- the mirror direction
        When the matching command is resolved
        Then the reason's base clause says "matches allow pattern", the
            rule's real list, not "matches deny pattern"
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(mycmd *)", "auto_mode_behavior": "deny"}],
            )
        )

        result = self._resolve(config, "mycmd --dangerous now", "auto")

        self.assertEqual(result.decision, "deny")
        self.assertIn("matches allow pattern: mycmd *", result.reason)
        self.assertNotIn("matches deny pattern", result.reason)
        self.assertIn("auto_mode_behavior='deny'", result.reason)
        self.assertIn("applied", result.reason)


class TestHardDenyRegressionGuards(unittest.TestCase):
    """
    [hard_deny] is absolute and unconditional -- an ``auto_mode_behavior`` on a
    permissions-list rule can never carve an exception out of it. ``check_hard_deny``
    runs in ``resolve.py`` BEFORE any cascade matching (see
    ``resolve_bash_permission_detailed``'s own docstring), so this holds structurally;
    these tests pin it so a later refactor cannot silently break it.
    """

    def test_hard_denied_command_stays_denied_despite_a_matching_allow_rule(self):
        """
        Given a [hard_deny] pool denying a command, AND a permissions.allow
            rule matching the same command with auto_mode_behavior='allow'
        When the command is resolved under permission_mode='auto'
        Then the decision is still 'deny' -- hard_deny is checked before the
            cascade ever sees the allow rule's auto-mode declaration
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(rm -rf *)", "auto_mode_behavior": "allow"}],
                hard_deny={"deny": ["Bash(rm -rf *)"]},
            )
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode="auto",
        )

        result = resolve_bash_permission_detailed("rm -rf /tmp/x", invocation)

        self.assertEqual(result.decision, "deny")

    def test_hard_deny_allow_carve_out_ignores_its_own_auto_mode_behavior_key(self):
        """
        Given a [hard_deny].allow carve-out entry itself carrying
            auto_mode_behavior='deny' (Arnon, 2026-09-05: the key inside
            [hard_deny] is ignored, undocumented as a validator rule, by
            design -- hard_deny stays trivially understandable), AND an
            unrelated permissions.allow rule (no auto_mode_behavior) matching
            the same command
        When the command is resolved under permission_mode='auto'
        Then the decision is 'allow' -- Configuration.hard_deny() never
            exposes an entry's metadata at all (see its own docstring), so
            the key has no way to reach this decision either way; the
            cascade's own unrelated allow rule is what actually decides
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=["Bash(rm -rf /tmp/*)"],
                hard_deny={
                    "deny": ["Bash(rm -rf *)"],
                    "allow": [
                        {
                            "match": "Bash(rm -rf /tmp/*)",
                            "auto_mode_behavior": "deny",
                        }
                    ],
                },
            )
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode="auto",
        )

        result = resolve_bash_permission_detailed("rm -rf /tmp/x", invocation)

        self.assertEqual(result.decision, "allow")


class TestAutoModeBehaviorUnderParseFailure(unittest.TestCase):
    """
    The parse-failure ASK floor sits above rule matching
    (:func:`~toolguard.permission_resolution._apply_ask_floor`) and is unconditional --
    a per-rule ``auto_mode_behavior`` cannot escape it, the same as no other
    fallback-shaped setting can (see
    ``test.unit.test_permission_resolution.TestParseFailureFloorHoldsForEveryRegisteredFallbackSetting``,
    the enumerating test this is the per-rule sibling of).
    """

    def test_widened_allow_is_still_floored_to_ask_under_a_parse_failure(self):
        """
        Given an ask rule declaring auto_mode_behavior='allow', AND a recorded
            parse failure, under permission_mode='auto'
        When the matching command is resolved
        Then the decision is 'ask' -- the floor clamps the effective decision
            exactly like it would any other 'allow'
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[{"match": "Bash(git push:*)", "auto_mode_behavior": "allow"}],
            ),
            parse_failures=_PARSE_FAILURES,
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode="auto",
        )

        result = resolve_command_permission(invocation, "git push origin main")

        self.assertEqual(result.decision, "ask")


class TestProgramSourceGuard(unittest.TestCase):
    """
    A matched rule's ``program_source`` constrains it to one
    visibility of executable material. A mismatch makes the WHOLE LEVEL
    unmatched -- the cascade falls through to the next, less-specific level,
    same as the existing no-match branch (``if result is None: continue``) --
    rather than retrying other patterns within the same level's own list.
    """

    def _resolve(self, config, command, program_source):
        """Resolve *command* with the given classification, permission_mode unset."""
        invocation = Invocation(
            tool_name="Bash", tool_input={}, config=config, extended_syntax=True
        )
        return resolve_command_permission(
            invocation, command, program_source=program_source
        )

    def test_file_required_rule_matches_a_file_command(self):
        """
        Given an allow rule requiring program_source='file'
        When resolved with a command classified as 'file'
        Then the rule matches and the decision is 'allow'
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(uv run python *)", "program_source": "file"}],
            )
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "uv run python *")

    def test_file_required_rule_does_not_fire_on_inline_code(self):
        """
        Given an allow rule requiring program_source='file', AND a less-specific
            level with an unconditional ask rule for the same command
        When resolved with a command classified as 'not_file' (inline)
        Then the more-specific level's guard fails, the level is treated as
            unmatched, and the cascade falls through to the ask rule below --
            proving the guard fires on the file case, not on every case
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(uv run python *)", "program_source": "file"}],
                specificity=0,
            ),
            _layer("user", _USER_PATH, ask=["Bash(uv run python *)"], specificity=9),
        )
        result = self._resolve(config, 'uv run python -c "print(1)"', "not_file")
        self.assertEqual(result.decision, "ask")
        self.assertEqual(result.matched_rule, "uv run python *")
        self.assertEqual(result.provenance.path, _USER_PATH)

    def test_not_file_required_rule_does_not_fire_on_a_file(self):
        """
        Given an allow rule requiring program_source='not_file', AND a
            less-specific level with an unconditional ask rule for the same
            command
        When resolved with a command classified as 'file'
        Then the more-specific level's guard fails and the cascade falls
            through -- the negative direction the mirror of the previous test
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {"match": "Bash(uv run python *)", "program_source": "not_file"}
                ],
                specificity=0,
            ),
            _layer("user", _USER_PATH, ask=["Bash(uv run python *)"], specificity=9),
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "ask")
        self.assertEqual(result.provenance.path, _USER_PATH)

    def test_rule_without_program_source_is_unaffected(self):
        """
        Given an allow rule with no program_source at all
        When resolved once with 'file' and once with 'not_file'
        Then both resolve to 'allow' -- an absent guard behaves exactly as
            today, under every command shape
        """
        config = _config(
            _layer("project", _PROJECT_PATH, allow=["Bash(uv run python *)"])
        )
        for classification in ("file", "not_file"):
            with self.subTest(classification=classification):
                result = self._resolve(
                    config, "uv run python script.py", classification
                )
                self.assertEqual(result.decision, "allow")

    def test_program_source_composes_with_a_default_pattern(self):
        """
        Given a DEFAULT (bare cmd:*) pattern carrying program_source='file'
        When resolved with a matching 'file' command
        Then the rule matches
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Bash(uv run python:*)", "program_source": "file"}],
            )
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "allow")

    def test_program_source_composes_with_a_regex_pattern(self):
        """
        Given a [regex]-prefixed pattern carrying program_source='file'
        When resolved with a matching 'file' command
        Then the rule matches
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {
                        "match": "Bash([regex]^uv run python\\b)",
                        "program_source": "file",
                    }
                ],
            )
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "allow")

    def test_program_source_composes_with_a_glob_pattern(self):
        """
        Given a [glob]-prefixed pattern carrying program_source='file'
        When resolved with a matching 'file' command
        Then the rule matches
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {
                        "match": "Bash([glob]uv run python *)",
                        "program_source": "file",
                    }
                ],
            )
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "allow")

    def test_program_source_composes_with_a_native_pattern(self):
        """
        Given a [native]-prefixed pattern carrying program_source='file'
        When resolved with a matching 'file' command
        Then the rule matches
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[
                    {
                        "match": "Bash([native]uv run python*)",
                        "program_source": "file",
                    }
                ],
            )
        )
        result = self._resolve(config, "uv run python script.py", "file")
        self.assertEqual(result.decision, "allow")

    def test_program_source_and_auto_mode_behavior_act_independently(self):
        """
        Given an ask rule carrying BOTH program_source='file' and
            auto_mode_behavior='allow'
        When resolved under permission_mode='auto' with a 'file' command, and
            again with a 'not_file' command
        Then the 'file' command widens to 'allow' (auto_mode_behavior fired),
            while the 'not_file' command's guard fails, so the rule does not
            apply and no auto_mode_behavior is ever consulted -- proving the
            two keys are independent rather than assumed to be
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                ask=[
                    {
                        "match": "Bash(uv run python *)",
                        "program_source": "file",
                        "auto_mode_behavior": "allow",
                    }
                ],
            )
        )
        invocation = Invocation(
            tool_name="Bash",
            tool_input={},
            config=config,
            extended_syntax=True,
            permission_mode="auto",
        )

        file_result = resolve_command_permission(
            invocation, "uv run python script.py", program_source="file"
        )
        not_file_result = resolve_command_permission(
            invocation, 'uv run python -c "print(1)"', program_source="not_file"
        )

        self.assertEqual(file_result.decision, "allow")
        self.assertEqual(not_file_result.decision, "ask")


class TestProgramSourceGuardNeverAppliesToFilePathResolution(unittest.TestCase):
    """
    ``program_source`` classifies Bash/MCP-terminal commands only;
    ``resolve_file_path_permission`` never computes a classification. A rule that
    carries the key on a Read/Write/Edit pattern must be INERT, not a silent change
    in what the rule matches -- an inert allow is a nuisance; a fail-open deny is a
    security defect (Arnon, 2026-09-07 review).
    """

    def test_allow_rule_with_program_source_still_matches_a_file_path(self):
        """
        Given a Read allow rule carrying program_source='file'
        When resolve_file_path_permission resolves a matching path
        Then the decision is 'allow' -- the guard never activates for a
            resolution that never classified anything
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                allow=[{"match": "Read(/tmp/x/**)", "program_source": "file"}],
            )
        )
        result = resolve_file_path_permission(
            Invocation.for_evaluation(config, tool_name="Read"), "/tmp/x/f.txt"
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "/tmp/x/**")

    def test_deny_rule_with_program_source_still_denies_a_file_path(self):
        """
        Given a Read deny rule carrying program_source='file'
        When resolve_file_path_permission resolves a matching path
        Then the decision is 'deny' -- the same guard that must not silently
            widen an allow must not silently narrow a deny to nothing either
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=[{"match": "Read(/tmp/x/secret*)", "program_source": "file"}],
            )
        )
        result = resolve_file_path_permission(
            Invocation.for_evaluation(config, tool_name="Read"),
            "/tmp/x/secret.txt",
        )
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "/tmp/x/secret*")


class TestProgramSourceGuardIsOrderIndependent(unittest.TestCase):
    """
    A rule whose ``program_source`` guard fails did not match AT ALL (Arnon,
    2026-09-07: "a rule match should be considered on the whole rule, not just the
    pattern match... the ordering doesn't matter whatsoever as the guarded form...
    simply would not be considered a match in the first place, masking nothing").
    It is filtered out BEFORE ``match_command`` ever sees it (see
    ``_level_pattern_buckets``), so an unguarded sibling in the same list that also
    matches is unaffected by where the guarded pattern sits in the list.
    """

    def test_the_broader_deny_fires_regardless_of_which_pattern_is_listed_first(self):
        """
        Given a deny list with a guarded pattern that does NOT apply to this
            command (program_source='not_file', but the command is a file) and
            an unguarded sibling pattern that also matches the same command
        When the command is resolved, once with the guarded pattern listed
            first and once with the order reversed
        Then both orderings deny -- the exact case that exposed the original
            bug (Arnon, 2026-09-07)
        """
        guarded = {"match": "Bash(python *)", "program_source": "not_file"}
        broader = "Bash(python /tmp/danger.py)"
        command = "python /tmp/danger.py"

        for deny_list in ([guarded, broader], [broader, guarded]):
            with self.subTest(order=[type(e).__name__ for e in deny_list]):
                config = _config(_layer("project", _PROJECT_PATH, deny=deny_list))
                invocation = Invocation(
                    tool_name="Bash",
                    tool_input={},
                    config=config,
                    extended_syntax=True,
                )

                result = resolve_command_permission(
                    invocation, command, program_source="file"
                )

                self.assertEqual(result.decision, "deny")

    def test_the_guarded_pattern_still_wins_when_its_own_condition_is_met(self):
        """
        Given the same deny list, but a command classification that DOES
            satisfy the guarded pattern's own condition
        When resolved
        Then it still denies -- the guarded rule is a normal deny once its
            guard passes, not disabled by having a guard at all
        """
        config = _config(
            _layer(
                "project",
                _PROJECT_PATH,
                deny=[
                    {"match": "Bash(python *)", "program_source": "not_file"},
                    "Bash(python /tmp/danger.py)",
                ],
            )
        )
        invocation = Invocation(
            tool_name="Bash", tool_input={}, config=config, extended_syntax=True
        )

        result = resolve_command_permission(
            invocation, 'python -c "x"', program_source="not_file"
        )

        self.assertEqual(result.decision, "deny")


if __name__ == "__main__":
    unittest.main()
