"""
Anti-drift contract test: decision.decide() must produce the same verdict
as calling toolguard.resolve.resolve_*() directly.

These tests document (and guard) the property that toolguard.tools.decision.decide()
delegates to toolguard.resolve.* -- rather than maintaining a separate copy of the
orchestration logic. Because both sides share the same code, this test is essentially
"same code, same results"; if someone were to accidentally reintroduce a divergence
(e.g. re-copy orchestration into decision.py), these tests would catch it.

Coverage:
  - Simple Bash allow
  - Compound Bash (multi-sub-command) allow
  - Bash hard-deny
  - Read allow (file path)
  - Read deny (file path, no match)
"""

import unittest
from pathlib import Path
from types import MappingProxyType

from unittest.mock import patch

from toolguard.compound import FALLBACK_ALLOW_PLACEHOLDER, FALLBACK_DENY_PLACEHOLDER
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.hook import (
    _log_allowed_command,
    _log_non_allow_decision,
)
from toolguard.tools.decision import decide
from toolguard.resolve import (
    RuntimeVerdict,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)


def _make_config(layers_content):
    """
    Build a minimal Configuration from a list of (level, source_type, content_dict).

    Args:
        layers_content: List of (level, source_type, content_dict) tuples.

    Returns:
        A Configuration with those layers (specificity increases with index).
    """
    layers = []
    for i, (level, source_type, content) in enumerate(layers_content):
        prov = Provenance(
            level=level,
            source_type=source_type,
            file_format="toml",
            path=Path(f"/fake/{level}/{source_type}"),
            specificity=i,
        )
        layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(layers), start_dir=None)


class TestNoDrift(unittest.TestCase):
    """
    Anti-drift: decide() must match resolve_*() verdict for a representative battery.

    These tests do NOT test behaviour (that is covered elsewhere in test/unit/); they
    test DELEGATION -- that the shared resolver and the decide() wrapper agree on the
    verdict for the same inputs, proving no separate logic path exists.
    """

    def _bash_config(self):
        """Return a config with allow=git/ls and hard-deny rm -rf."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": [],
                        },
                        "hard_deny": {
                            "deny": ["Bash(rm -rf:*)"],
                            "allow": [],
                        },
                    },
                )
            ]
        )

    def _read_config(self):
        """Return a config that allows Read under /tmp only."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )

    def test_simple_bash_allow_no_drift(self):
        """
        Given a config that allows 'git:*'
        When decide() is called with 'git status' AND resolve_bash_permission_detailed is
        called with the same config and command
        Then both produce the same verdict ('allow')
        """
        config = self._bash_config()
        command = "git status"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, RuntimeVerdict)
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Bash allow: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("allow", decision_verdict)

    def test_compound_bash_all_allowed_no_drift(self):
        """
        Given a config that allows 'git:*' and 'ls:*'
        When decide() and resolve_bash_permission_detailed() are called with a
        compound command 'git status && ls -la'
        Then both produce the same verdict ('allow')
        """
        config = self._bash_config()
        command = "git status && ls -la"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, RuntimeVerdict)
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for compound Bash allow: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("allow", decision_verdict)

    def test_bash_hard_deny_no_drift(self):
        """
        Given a config with hard-deny on 'rm -rf:*'
        When decide() and resolve_bash_permission_detailed() are called with 'rm -rf /'
        Then both produce the same verdict ('deny')
        """
        config = self._bash_config()
        command = "rm -rf /"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, RuntimeVerdict)
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for hard-deny Bash: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("deny", decision_verdict)

    def test_read_allow_no_drift(self):
        """
        Given a config that allows Read under /tmp/**
        When decide() and resolve_file_path_permission_detailed() are called with
        '/tmp/some/file.txt'
        Then both produce the same verdict ('allow')
        """
        config = self._read_config()
        file_path = "/tmp/some/file.txt"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).decision

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        self.assertIsInstance(file_result, RuntimeVerdict)
        resolve_verdict = file_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Read allow: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("allow", decision_verdict)

    def test_read_no_match_no_drift(self):
        """
        Given a config that allows Read under /tmp/** only
        When decide() and resolve_file_path_permission_detailed() are called with
        '/etc/passwd' (outside allowed path, matches no rule)
        Then both produce the same verdict ('ask', the TOO-15 default
            no_match_fallback)
        """
        config = self._read_config()
        file_path = "/etc/passwd"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).decision

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        self.assertIsInstance(file_result, RuntimeVerdict)
        resolve_verdict = file_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Read no-match: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("ask", decision_verdict)


class TestNoMatchSemanticsNoDrift(unittest.TestCase):
    """
    TOO-15: anti-drift coverage for the no-match resolution semantics.

    Same "same code, same results" property as :class:`TestNoDrift`, but for
    the no-match behaviour: a fully-unconfigured tool resolves to 'ask' (never
    affected by no_match_fallback); a tool with rules that simply do not match
    resolves per no_match_fallback -- 'ask' (the default), 'deny', or
    'allow_with_warning' (allow, with a warning reason). The deprecated legacy
    value 'warn_deny' is still accepted as an alias for 'allow_with_warning',
    including under the legacy [takeover_mode].no_match_fallback section.
    """

    def _empty_config(self):
        """Return a config with NO permissions/hard_deny sections at all."""
        return _make_config([("project", "toolguard_hook", {})])

    def _bash_configured_no_match_config(self):
        """Return a config that allows only 'git:*' for Bash (no hard_deny)."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )

    def _read_configured_no_match_config(self):
        """Return a config that allows Read only under /tmp/** (no hard_deny)."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )

    def test_bash_fully_unconfigured_resolves_to_ask_no_drift(self):
        """
        Given a config with NO permissions/hard_deny at all for Bash
        When decide() and resolve_bash_permission_detailed() evaluate any command
        Then both agree the verdict is 'ask' (never bricked by an empty install)
        """
        config = self._empty_config()
        command = "ls -la"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for unconfigured Bash: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("ask", decision_verdict)

    def test_read_fully_unconfigured_resolves_to_ask_no_drift(self):
        """
        Given a config with NO permissions/hard_deny at all for Read
        When decide() and resolve_file_path_permission_detailed() evaluate any path
        Then both agree the verdict is 'ask'
        """
        config = self._empty_config()
        file_path = "/tmp/some/file.txt"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).decision

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        resolve_verdict = file_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for unconfigured Read: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("ask", decision_verdict)

    def test_bash_rules_exist_no_match_asks_by_default_no_drift(self):
        """
        Given Bash allows only 'git:*' (rules ARE configured) and no
            no_match_fallback override
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'ask' (TOO-15: the new default
            no_match_fallback -- a config with rules that simply don't cover a
            command must prompt, not silently deny or bricking installs)
        """
        config = self._bash_configured_no_match_config()
        command = "ls -la"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Bash no-match: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("ask", decision_verdict)

    def test_read_rules_exist_no_match_asks_by_default_no_drift(self):
        """
        Given Read allows only '/tmp/**' (rules ARE configured) and no
            no_match_fallback override
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'ask' (TOO-15: the new default
            no_match_fallback)
        """
        config = self._read_configured_no_match_config()
        file_path = "/etc/passwd"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).decision

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        resolve_verdict = file_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Read no-match: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("ask", decision_verdict)

    def test_bash_rules_exist_no_match_denies_with_explicit_deny_no_drift(self):
        """
        Given Bash allows only 'git:*' and top-level no_match_fallback='deny'
            is set EXPLICITLY (overriding the 'ask' default)
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'deny'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision_verdict = decide(config, "Bash", command, extended_syntax).decision

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        resolve_verdict = bash_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Bash explicit deny: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("deny", decision_verdict)

    def test_read_rules_exist_no_match_denies_with_explicit_deny_no_drift(self):
        """
        Given Read allows only '/tmp/**' and top-level no_match_fallback='deny'
            is set EXPLICITLY (overriding the 'ask' default)
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'deny'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        file_path = "/etc/passwd"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).decision

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        resolve_verdict = file_result.decision

        self.assertEqual(
            resolve_verdict,
            decision_verdict,
            f"Drift detected for Read explicit deny: resolve={resolve_verdict}, "
            f"decide={decision_verdict}",
        )
        self.assertEqual("deny", decision_verdict)

    def test_bash_allow_with_warning_fallback_allows_no_drift(self):
        """
        Given Bash allows only 'git:*' and top-level
            no_match_fallback='allow_with_warning'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'allow' (auto-allowed with a warning
            reason naming 'allow_with_warning')
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(
            bash_result.decision,
            decision.decision,
            f"Drift detected for Bash allow_with_warning: "
            f"resolve={bash_result.decision}, decide={decision.decision}",
        )
        self.assertEqual("allow", decision.decision)
        self.assertIn("allow_with_warning", bash_result.reason)

    def test_read_allow_with_warning_fallback_allows_no_drift(self):
        """
        Given Read allows only '/tmp/**' and top-level
            no_match_fallback='allow_with_warning'
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'allow' (auto-allowed with a warning
            reason naming 'allow_with_warning')
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        file_path = "/etc/passwd"
        extended_syntax = True

        decision = decide(config, "Read", file_path, extended_syntax)

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )

        self.assertEqual(
            file_result.decision,
            decision.decision,
            f"Drift detected for Read allow_with_warning: "
            f"resolve={file_result.decision}, decide={decision.decision}",
        )
        self.assertEqual("allow", decision.decision)
        self.assertIn("allow_with_warning", file_result.reason)

    def test_bash_warn_deny_legacy_alias_allows_no_drift(self):
        """
        Given Bash allows only 'git:*' and top-level no_match_fallback is set
            to the DEPRECATED legacy value 'warn_deny'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'allow' (the legacy alias behaves
            identically to 'allow_with_warning', including in the reason text)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "warn_deny",
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(
            bash_result.decision,
            decision.decision,
            f"Drift detected for Bash warn_deny alias: "
            f"resolve={bash_result.decision}, decide={decision.decision}",
        )
        self.assertEqual("allow", decision.decision)
        self.assertIn("allow_with_warning", bash_result.reason)

    def test_read_warn_deny_legacy_alias_allows_no_drift(self):
        """
        Given Read allows only '/tmp/**' and top-level no_match_fallback is set
            to the DEPRECATED legacy value 'warn_deny'
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'allow' (the legacy alias behaves
            identically to 'allow_with_warning', including in the reason text)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "warn_deny",
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        file_path = "/etc/passwd"
        extended_syntax = True

        decision = decide(config, "Read", file_path, extended_syntax)

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )

        self.assertEqual(
            file_result.decision,
            decision.decision,
            f"Drift detected for Read warn_deny alias: "
            f"resolve={file_result.decision}, decide={decision.decision}",
        )
        self.assertEqual("allow", decision.decision)
        self.assertIn("allow_with_warning", file_result.reason)

    def test_legacy_takeover_alias_warn_deny_honored_no_drift(self):
        """
        Given ONLY the legacy [takeover_mode].no_match_fallback='warn_deny' is set
            (no top-level key), and Bash allows only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
        Then both agree the verdict is 'allow' (legacy alias still honoured,
            normalized to 'allow_with_warning' in the reason)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "takeover_mode": {"no_match_fallback": "warn_deny"},
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.decision)
        self.assertEqual("allow", decision.decision)
        self.assertIn("allow_with_warning", bash_result.reason)

    def test_top_level_no_match_fallback_wins_over_legacy_alias_no_drift(self):
        """
        Given the top-level no_match_fallback='deny' AND the legacy
            [takeover_mode].no_match_fallback='warn_deny' are BOTH set, with Bash
            allowing only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
        Then both agree the verdict is 'deny' (top-level wins over the legacy alias)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "takeover_mode": {"no_match_fallback": "warn_deny"},
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.decision)
        self.assertEqual("deny", decision.decision)

    def test_takeover_enabled_no_match_fallback_deny_still_fails_closed_no_drift(self):
        """
        Given takeover_mode.enabled=True with no_match_fallback explicitly 'deny',
            and Bash allowing only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is still 'deny' (fail-closed is preserved
            when takeover mode is on and the fallback is explicitly 'deny')
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "takeover_mode": {"enabled": True, "no_match_fallback": "deny"},
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.decision)
        self.assertEqual("deny", decision.decision)

    def test_takeover_enabled_default_no_match_fallback_asks_no_drift(self):
        """
        Given takeover_mode.enabled=True with NO no_match_fallback set at all
            (relying on the default), and Bash allowing only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'ask' (TOO-15: the default change to
            'ask' applies in takeover mode too, not just non-takeover mode)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "takeover_mode": {"enabled": True},
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(
            bash_result.decision,
            decision.decision,
            f"Drift detected for takeover-enabled default: "
            f"resolve={bash_result.decision}, decide={decision.decision}",
        )
        self.assertEqual("ask", decision.decision)

    def test_takeover_enabled_allow_with_warning_no_drift(self):
        """
        Given takeover_mode.enabled=True with no_match_fallback explicitly
            'allow_with_warning', and Bash allowing only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'allow' (takeover mode does not change
            the allow_with_warning semantics)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "takeover_mode": {
                            "enabled": True,
                            "no_match_fallback": "allow_with_warning",
                        },
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.decision)
        self.assertEqual("allow", decision.decision)


class TestUndecidableFallbackThreading(unittest.TestCase):
    """
    TOO-19: resolve_bash_permission_detailed() sources undecidable_fallback
    from config.resolved_undecidable_fallback() and threads it through
    resolve_compound_permission(), end to end, for both kinds of undecidable
    result: foreign inline code / heredoc sinks (ask_floor leaves) and
    UndecidableSegment (control structures, process substitution).
    """

    def _config_with_fallback(self, undecidable_fallback, allow=()):
        """Return a config with the given top-level undecidable_fallback set."""
        content = {
            "undecidable_fallback": undecidable_fallback,
            "permissions": {
                "allow": [f"Bash({p})" for p in allow],
                "deny": [],
            },
        }
        return _make_config([("project", "toolguard_hook", content)])

    def _resolve(self, config, command):
        """Resolve *command* through resolve_bash_permission_detailed."""
        hd_deny, hd_allow = config.hard_deny("Bash")
        return resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )

    def test_ask_floor_leaf_under_each_fallback(self):
        """
        Given a foreign inline-code command (`python3 -c "..."`) with the
            outer command allowed
        When resolve_bash_permission_detailed() resolves it under each of the
            five undecidable_fallback settings (TOO-19: including the newer
            'allow'/'allow_with_no_warnings' allow-with-no-warning values)
        Then the decision matches that setting's floor exactly (ask/deny/allow)
            -- 'allow_with_warning', 'allow', and 'allow_with_no_warnings' are
            all the SAME strictness level (float to 'allow')
        """
        cmd = 'python3 -c "import os"'
        expected = {
            "ask": "ask",
            "deny": "deny",
            "allow_with_warning": "allow",
            "allow": "allow",
            "allow_with_no_warnings": "allow",
        }
        for fallback, want in expected.items():
            with self.subTest(fallback=fallback):
                config = self._config_with_fallback(fallback, allow=["python3 -c:*"])
                result = self._resolve(config, cmd)
                self.assertEqual(result.decision, want)

    def test_undecidable_segment_under_each_fallback(self):
        """
        Given a process-substitution command (`diff <(sort a) <(sort b)`)
        When resolve_bash_permission_detailed() resolves it under each of the
            five undecidable_fallback settings (TOO-19: including the newer
            'allow'/'allow_with_no_warnings' allow-with-no-warning values)
        Then the decision matches that setting's floor exactly (ask/deny/allow)
            -- 'allow_with_warning', 'allow', and 'allow_with_no_warnings' are
            all the SAME strictness level (float to 'allow')
        """
        cmd = "diff <(sort a) <(sort b)"
        expected = {
            "ask": "ask",
            "deny": "deny",
            "allow_with_warning": "allow",
            "allow": "allow",
            "allow_with_no_warnings": "allow",
        }
        for fallback, want in expected.items():
            with self.subTest(fallback=fallback):
                config = self._config_with_fallback(fallback, allow=["diff:*"])
                result = self._resolve(config, cmd)
                self.assertEqual(result.decision, want)

    def test_default_config_preserves_pre_too19_ask_behaviour(self):
        """
        Given a config with NO undecidable_fallback key set (the pre-TOO-19
            shape)
        When resolve_bash_permission_detailed() resolves a process-substitution
            command
        Then the decision is still 'ask' -- config.resolved_undecidable_fallback()
            defaults to 'ask', so nothing changes for existing installs
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Bash(diff:*)"], "deny": []}},
                )
            ]
        )
        result = self._resolve(config, "diff <(sort a) <(sort b)")
        self.assertEqual(result.decision, "ask")

    def test_no_match_fallback_and_undecidable_fallback_are_independent(self):
        """
        Given a SINGLE config setting no_match_fallback='deny' AND
            undecidable_fallback='allow_with_warning' together
        When a plain no-match command (no rule covers it, fully decomposable)
            and a process-substitution command (undecidable) are each
            resolved
        Then the no-match command is DENIED (governed by no_match_fallback
            alone) and the undecidable command is ALLOWED (governed by
            undecidable_fallback alone) -- each setting governs only its own
            case, proving the two fallbacks are independent
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "undecidable_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(diff:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )

        no_match_result = self._resolve(config, "ls -la")
        undecidable_result = self._resolve(config, "diff <(sort a) <(sort b)")

        self.assertEqual(no_match_result.decision, "deny")
        self.assertEqual(undecidable_result.decision, "allow")

    def test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback(
        self,
    ):
        """
        HARD INVARIANT (TOO-19) end to end: an ask_floor leaf (foreign inline
        code) whose OUTER command resolution goes through
        permission_resolution.resolve_permission_detailed -- and therefore
        through the parse-failure ASK floor -- cannot be downgraded below
        'ask' by
        undecidable_fallback, even when set to the most permissive
        'allow_with_warning'.

        Given a config with undecidable_fallback='allow_with_warning' AND a
            recorded parse failure for a broken file, and an allow pattern
            that would otherwise permit the outer command
        When resolve_bash_permission_detailed() resolves a foreign
            inline-code command
        Then the decision is 'ask' -- the parse-failure floor forces 'ask' on
            the outer command's resolution, and undecidable_fallback's floor
            can only make a result STRICTER, never weaker, so it cannot
            un-clamp it to 'allow'
        """
        broken = Path("/fake/project/toolguard_hook.local.toml")
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Bash(python3 -c:*)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        # Configuration is frozen/dataclass-like; parse_failures is a
        # constructor field, so rebuild with it set (mirrors
        # TestParseFailureAskFloor's direct-construction style).
        config = Configuration(
            layers=config.layers,
            start_dir=config.start_dir,
            parse_failures=((broken, "unexpected character"),),
        )

        result = self._resolve(config, 'python3 -c "import os"')
        self.assertEqual(result.decision, "ask")


class TestUndecidableFallbackMultiLeafWarningParity(unittest.TestCase):
    """
    TOO-19 code review 2026-08-02, Major finding M1: ``allow_with_warning``
    silently lost its warning -- and misattributed the allow to a fabricated
    rule name -- on a multi-leaf all-allow compound.

    Given the exact repro config/commands from that review: ``Bash(ls)`` +
    ``Bash(python *)`` allow, undecidable_fallback set to each of
    ``'allow_with_warning'`` and ``'allow'``.

    A single-leaf ask-floor command and a two-leaf compound wrapping the same
    ask-floor command must agree on fallback_warning -- before this fix the
    multi-leaf case silently reported False (defect 1) and fabricated a
    'python -c' rule match in the reason (defect 2).
    """

    def _repro_config(self, undecidable_fallback):
        """Build the exact M1 repro config: Bash(ls) + Bash(python *) allow only."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": undecidable_fallback,
                        "permissions": {
                            "allow": ["Bash(ls)", "Bash(python *)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )

    def test_single_leaf_allow_with_warning_sets_fallback_warning_true(self):
        """
        Given undecidable_fallback='allow_with_warning'
        When resolving the single-leaf command 'python -c "print(1)"'
        Then the decision is allow and fallback_warning is True (baseline,
            unaffected by this fix -- confirms the repro table's row 1)
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertTrue(result.fallback_warning)

    def test_multi_leaf_allow_with_warning_sets_fallback_warning_true(self):
        """
        Given undecidable_fallback='allow_with_warning'
        When resolving the two-leaf compound 'ls && python -c "print(1)"'
        Then the decision is allow and fallback_warning is True -- BEFORE
            the fix this was False (M1 defect 1: the marker was destroyed by
            the multi-leaf 'cmd -> pattern' summary)
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'ls && python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertTrue(
            result.fallback_warning,
            "multi-leaf compound lost the warning -- M1 defect 1 regressed",
        )

    def test_multi_leaf_reason_never_fabricates_a_matched_rule(self):
        """
        Given undecidable_fallback='allow_with_warning' and NO rule named
            'python -c' anywhere in the config
        When resolving 'ls && python -c "print(1)"'
        Then the reason does NOT claim 'python -c' (or any other pattern) was
            a matched rule for that leaf -- M1 defect 2. An absent record is
            required in place of the fabricated one.
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'ls && python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertNotIn(
            "-> python -c",
            result.reason,
            "fabricated 'python -c' rule attribution reappeared in the reason",
        )
        self.assertIn("[fallback allow -- no rule matched]", result.reason)

    def test_single_vs_multi_leaf_parity_for_silent_allow(self):
        """
        Given undecidable_fallback='allow' (TOO-19 no-warning value)
        When resolving both the single-leaf and two-leaf compound forms
        Then BOTH report fallback_warning False (no warning was ever
            promised for this value) and neither reason fabricates a
            'python -c' rule match
        """
        config = self._repro_config("allow")
        hd_deny, hd_allow = config.hard_deny("Bash")
        for command in ('python -c "print(1)"', 'ls && python -c "print(1)"'):
            with self.subTest(command=command):
                result = resolve_bash_permission_detailed(
                    command, config, True, hd_deny, hd_allow
                )
                self.assertEqual(result.decision, "allow")
                self.assertFalse(result.fallback_warning)
                self.assertNotIn("-> python -c", result.reason)

    def test_multi_leaf_sub_matches_now_holds_the_real_leaf_text_and_placeholder(self):
        """
        Given the same multi-leaf compound with an ask-floor escape-hatch leaf
        When resolving 'ls && python -c "print(1)"'
        Then result.sub_matches records the leaf's REAL, full text (NOT the
            truncated outer-command stub 'python -c') with matched_rule=None
            and fallback_kind='warned' -- TOO-45 R1e closed the exact gap the
            retired hook.py::_parse_compound_match_details (and this test,
            previously) worked around: before the fix, this same UnitVerdict
            held the truncated stub 'python -c' with a matched_rule of
            'python *' (config.py(Bash(python *)) genuinely matches the STUB,
            even though the leaf's real payload was never verified and
            compound.py deliberately floors it to the escape hatch
            regardless) -- the reason a reason-string round trip was needed
            at all. sub_matches is now the complete, correct record.
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'ls && python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        by_command = {sm.sub_command: sm for sm in result.sub_matches}
        self.assertIn(
            'python -c "print(1)"',
            by_command,
            "sub_matches must key on the leaf's real text, not the truncated stub",
        )
        escape_hatch_unit = by_command['python -c "print(1)"']
        self.assertIsNone(escape_hatch_unit.matched_rule)
        self.assertEqual(escape_hatch_unit.fallback_kind, "warned")
        self.assertEqual(escape_hatch_unit.decision, "allow")

    def test_multi_leaf_matched_rule_attributes_the_sole_genuine_match(self):
        """
        Given the same two-leaf compound 'ls && python -c "print(1)"' -- one
            leaf ('ls') a genuine rule match, the other an escape-hatch allow
        When resolving it
        Then result.matched_rule is 'ls' (the sole genuine match) and
            result.provenance is non-None and identifies the project layer --
            NOT None for either field

        TOO-45 R1e finishing pass regression guard: ``_deciding_sub_match``'s
        old "exactly one entry in sub_matches" test for "there is a single
        decider" broke the moment ``sub_matches`` correctly grew a SECOND
        entry for the escape-hatch leaf (closing a separate audit-loss gap
        this same step fixed) -- a genuinely two-entry ``sub_matches`` list
        does not mean there is no single decider any more, because ONE of
        those two entries is an ambient escape hatch that never competed for
        attribution before the audit-loss fix made it visible at all. The
        right test is "exactly one entry with a real matched_rule", not
        "exactly one entry, full stop".
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'ls && python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "ls")
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.level, "project")

    def test_three_leaf_compound_warns_when_any_leaf_is_an_escape_hatch(self):
        """
        Given undecidable_fallback='allow_with_warning' and a THREE-leaf
            compound where only the middle leaf is the ask-floor escape hatch
        When resolving 'ls && python -c "print(1)" && ls'
        Then fallback_warning is still True (any(), not all()) and neither
            genuine leaf ('ls -> ls') is mislabelled as a fallback allow
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'ls && python -c "print(1)" && ls', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertTrue(result.fallback_warning)
        self.assertIn("[fallback allow -- no rule matched]", result.reason)
        self.assertIn("ls -> ls", result.reason)


class TestAuditLogMatchedRuleNeverFabricated(unittest.TestCase):
    """
    TOO-19 m5: the audit log must never name a rule that does not exist.

    ``hook.py::_log_allowed_command`` derived its ``Matched Rule`` field by
    splitting the reason on the first ``": "``. For a fallback ESCAPE-HATCH
    allow the text after that colon is the truncated DISPLAY COMMAND, not a
    pattern, so a config whose only rules were ``Bash(ls)`` and
    ``Bash(python *)`` recorded ``**Matched Rule**: `python -c``` -- a rule
    that exists nowhere.

    The MULTI-leaf path had already been fixed to record
    ``[fallback allow -- no rule matched]``. These tests pin single-leaf and
    compound to that ONE convention together, so they cannot diverge into two
    conventions again, and drive the REAL reason strings through the REAL
    logging entry point rather than asserting against hand-written text.
    """

    def _repro_config(self, undecidable_fallback):
        """Build the m5 repro config: Bash(ls) + Bash(python *) allow only."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": undecidable_fallback,
                        "permissions": {
                            "allow": ["Bash(ls)", "Bash(python *)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )

    def _logged_rules(self, command, undecidable_fallback="allow_with_warning"):
        """Resolve *command*, log the allow, and return the (cmd, matched_rule) pairs."""
        config = self._repro_config(undecidable_fallback)
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        # TOO-45 R1e: `_log_allowed_command` is now driven entirely by
        # `result.sub_matches` (both single-leaf and compound), so the REAL
        # `result` -- not a hand-trimmed copy carrying only reason/
        # matched_rule -- must be passed through. TOO-45 R1d: it takes the
        # whole verdict object instead of loose matched_rule/reason args.
        with patch("toolguard.hook.log_command") as mock_log:
            _log_allowed_command(result, command, "main", {"logging_enabled": True})
        return [
            (call.args[0].command_str, call.args[0].matched_rule)
            for call in mock_log.call_args_list
        ]

    def test_single_leaf_escape_hatch_logs_the_placeholder_not_a_pattern(self):
        """
        Given undecidable_fallback='allow_with_warning' and NO 'python -c'
            rule anywhere in the config
        When the single-leaf command 'python -c "print(1)"' is allowed and
            logged
        Then the recorded matched rule is the fallback placeholder, and in
            particular is NOT the fabricated 'python -c'
        """
        logged = self._logged_rules('python -c "print(1)"')
        self.assertEqual(len(logged), 1)
        command, matched_rule = logged[0]
        self.assertEqual(command, 'python -c "print(1)"')
        self.assertNotEqual(
            matched_rule, "python -c", "the fabricated rule attribution regressed"
        )
        self.assertEqual(matched_rule, FALLBACK_ALLOW_PLACEHOLDER)

    def test_single_leaf_escape_hatch_raw_matched_rule_is_already_correct(
        self,
    ):
        """
        Given the same undecidable_fallback='allow_with_warning' escape hatch
        When 'python -c "print(1)"' is resolved (BEFORE logging)
        Then RuntimeVerdict.matched_rule is ALREADY None -- TOO-45 R1e fixed
            this at the source: before the fix this was the REAL, misleading
            'python *' stub match, and the placeholder substitution in the
            previous test happened only at LOG time via a reason-text
            re-classification. Now compound.py corrects the leaf's own
            UnitVerdict (sub_command/decision/matched_rule) to its TRUE final
            outcome at the point the undecidable_fallback floor is applied,
            so `_deciding_sub_match` (see resolve.py) never sees the
            misleading stub match in the first place -- this pins the fix at
            its source, not merely its downstream symptom.
        """
        config = self._repro_config("allow_with_warning")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertIsNone(result.matched_rule)

    def test_compound_escape_hatch_leaf_logs_the_same_placeholder(self):
        """
        Given the same config and the two-leaf compound
            'ls && python -c "print(1)"'
        When it is allowed and logged
        Then the genuine 'ls' leaf keeps its real matched pattern and the
            escape-hatch leaf records the SAME placeholder the single-leaf
            path uses -- one convention, not two
        """
        logged = dict(self._logged_rules('ls && python -c "print(1)"'))
        self.assertEqual(len(logged), 2)
        self.assertEqual(
            logged['python -c "print(1)"'],
            FALLBACK_ALLOW_PLACEHOLDER,
        )
        self.assertIn("ls", logged["ls"])
        self.assertNotEqual(logged["ls"], FALLBACK_ALLOW_PLACEHOLDER)

    def test_single_leaf_and_compound_agree_for_the_silent_allow_value(self):
        """
        Given undecidable_fallback='allow' (the no-warning value, whose reason
            text differs from the warned one)
        When both the single-leaf and the compound forms are logged
        Then both record the fallback placeholder for the escape-hatch leaf --
            the marker recognition must not be specific to the warned wording
        """
        single = self._logged_rules('python -c "print(1)"', "allow")
        compound = dict(self._logged_rules('ls && python -c "print(1)"', "allow"))
        self.assertEqual(single[0][1], FALLBACK_ALLOW_PLACEHOLDER)
        self.assertEqual(compound['python -c "print(1)"'], FALLBACK_ALLOW_PLACEHOLDER)

    def test_a_genuine_rule_match_still_records_its_pattern(self):
        """
        Given a command that DOES match a configured allow rule ('Bash(ls)')
        When it is allowed and logged
        Then the matched rule is EXACTLY the configured pattern 'ls' -- not
            merely non-None or merely containing the substring 'ls' (a
            mutation that swapped in a wrong-but-plausible value must fail
            this test)
        """
        logged = self._logged_rules("ls")
        self.assertEqual(len(logged), 1)
        _command, matched_rule = logged[0]
        self.assertEqual(matched_rule, "ls")

    def test_no_match_fallback_allow_also_records_the_placeholder(self):
        """
        Given no_match_fallback='allow_with_warning' and a command no rule
            covers at all (the OTHER fallback escape hatch, whose reason text
            is built by config.py rather than compound.py)
        When it is allowed and logged
        Then the placeholder is recorded -- previously this reason had no
            ': ' at all so the field was simply absent, which was not wrong
            but was a second, inconsistent convention for the same situation
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(ls)"], "deny": []},
                    },
                )
            ]
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "cat README.md", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        with patch("toolguard.hook.log_command") as mock_log:
            _log_allowed_command(
                result, "cat README.md", "main", {"logging_enabled": True}
            )
        self.assertEqual(
            mock_log.call_args_list[0].args[0].matched_rule,
            FALLBACK_ALLOW_PLACEHOLDER,
        )


class TestAuditLogViolatedRuleNeverFabricated(unittest.TestCase):
    """
    TOO-19 deny-side rule fabrication fix: the audit log must never name a
    rule that does not exist, on the deny side either.

    ``hook.py::_log_non_allow_decision`` derived its ``Violated Rules`` field
    for a deny by splitting the reason on the first ``": "``. For a deny
    produced by the ``undecidable_fallback=deny`` escape hatch, the text
    after that colon is the truncated DISPLAY COMMAND, not a rule, so a
    config whose only rules were ``Bash(ls)`` and ``Bash(python *)`` recorded
    ``**Violated Rules**: `python -c``` -- a rule that exists nowhere. This is
    the deny-side counterpart of the allow-side m5 fix pinned by
    :class:`TestAuditLogMatchedRuleNeverFabricated` above; both now share the
    SAME mechanism (``fallback_kind_for_reason`` +
    ``FALLBACK_ALLOW_PLACEHOLDER``/``FALLBACK_DENY_PLACEHOLDER``).
    """

    def _repro_config(self, undecidable_fallback):
        """Build the m5-style repro config: Bash(ls) + Bash(python *) allow only."""
        return _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": undecidable_fallback,
                        "permissions": {
                            "allow": ["Bash(ls)", "Bash(python *)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )

    def _log_and_capture(self, config, command):
        """Resolve *command* against *config* and return (result, mock_log_command call)."""
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )
        # TOO-45 R3: matched_rule is now structured data already on `result`
        # -- _log_non_allow_decision no longer re-parses it out of
        # `result.reason`. TOO-45 R1d: it now takes the whole verdict object.
        verdict = RuntimeVerdict(
            decision=result.decision,
            reason=result.reason,
            matched_rule=result.matched_rule,
            additional_context=result.additional_context,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_non_allow_decision(
                verdict, command, "main", {"logging_enabled": True}, None
            )
        self.assertEqual(len(mock_log.call_args_list), 1)
        return result, mock_log.call_args_list[0]

    def test_single_leaf_undecidable_deny_logs_the_placeholder_not_a_command(self):
        """
        Given undecidable_fallback='deny' and NO 'python -c' rule anywhere in
            the config
        When the single-leaf command 'python -c "print(1)"' is denied by the
            undecidable floor and logged
        Then the recorded violated rule is the fallback placeholder, and in
            particular is NOT the fabricated 'python -c'
        """
        config = self._repro_config("deny")
        result, call = self._log_and_capture(config, 'python -c "print(1)"')
        self.assertEqual(result.decision, "deny")
        # Unlike the allow-side escape hatch (whose raw matched_rule is the
        # real, misleading 'python *' stub match), the deny floor's own
        # sub_match here never agrees with the final 'deny' decision, so
        # RuntimeVerdict.matched_rule is None on the raw field itself -- not
        # just at log time.
        self.assertIsNone(result.matched_rule)
        violated_rules = call.args[0].violated_rules
        self.assertNotEqual(
            violated_rules, ["python -c"], "the fabricated rule attribution regressed"
        )
        self.assertEqual(violated_rules, [FALLBACK_DENY_PLACEHOLDER])

    def test_compound_leaf_undecidable_deny_logs_the_same_placeholder(self):
        """
        Given the same config and the two-leaf compound
            'ls && python -c "print(1)"'
        When the compound is denied (any deny -> deny, driven by the
            escape-hatch leaf) and logged
        Then the recorded violated rule is still the placeholder, not the
            escape-hatch leaf's truncated display command -- one convention,
            not two, matching the single-leaf case

        This is also the exact scenario ``resolve._deciding_sub_match``'s
        docstring used to cite for a genuine sub_matches/final-decision
        divergence: before TOO-45 R1e, BOTH sub-commands' recorded
        UnitVerdict.decision were 'allow' ('ls' genuinely, 'python -c' via
        its misleading pre-floor stub match), while the floor made the
        compound 'deny' -- nothing agreed, and RuntimeVerdict.matched_rule
        was None only because ``_deciding_sub_match`` found no matching
        decision to attribute to. R1e closes that divergence: the
        escape-hatch leaf's recorded UnitVerdict now correctly says 'deny'
        (its TRUE final outcome), so ``_deciding_sub_match`` attributes the
        compound's 'deny' to THAT leaf -- matched_rule is still None, but
        now because it is a genuine escape-hatch attribution to the correct
        leaf, not an attribution failure.
        """
        config = self._repro_config("deny")
        result, call = self._log_and_capture(config, 'ls && python -c "print(1)"')
        self.assertEqual(result.decision, "deny")
        self.assertIsNone(result.matched_rule)
        by_command = {sm.sub_command: sm for sm in result.sub_matches}
        self.assertEqual(by_command["ls"].decision, "allow")
        self.assertEqual(
            by_command['python -c "print(1)"'].decision,
            "deny",
            "the escape-hatch leaf's UnitVerdict must reflect its TRUE "
            "final decision, not the pre-floor stub match -- the exact gap "
            "TOO-45 R1e closed",
        )
        self.assertEqual(
            by_command['python -c "print(1)"'].fallback_kind,
            "denied",
        )
        self.assertEqual(call.args[0].violated_rules, [FALLBACK_DENY_PLACEHOLDER])

    def test_undecidable_segment_deny_logs_the_placeholder_not_the_command(self):
        """
        Given undecidable_fallback='deny' and a process-substitution command
            (an UndecidableSegment -- a grammar shape distinct from the
            ASK-floor leaf case above, with its OWN reason-string construction
            in resolve_compound_permission_detailed)
        When the segment cannot be safely decomposed and is denied by the
            floor, then logged
        Then the recorded violated rule is the placeholder, not the
            truncated original segment text -- both deny reason shapes this
            module builds are covered by the SAME marker, not just the
            ASK-floor one
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": "deny",
                        "permissions": {"allow": ["Bash(diff *)"], "deny": []},
                    },
                )
            ]
        )
        result, call = self._log_and_capture(config, "diff <(sort a) <(sort b)")
        self.assertEqual(result.decision, "deny")
        self.assertIn("undecidable_fallback=deny", result.reason)
        self.assertEqual(call.args[0].violated_rules, [FALLBACK_DENY_PLACEHOLDER])

    def test_a_genuine_deny_still_records_its_real_pattern(self):
        """
        Given a command that matches a configured DENY rule directly ('Bash(rm
            -rf *)'; no undecidable_fallback escape hatch involved)
        When it is denied and logged
        Then the violated rule is EXACTLY ['rm -rf *'] -- not merely absent
            the placeholder or merely containing 'rm -rf' (a mutation that
            swapped in a wrong-but-plausible value must fail this test)
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(*)"],
                            "deny": ["Bash(rm -rf *)"],
                        },
                    },
                )
            ]
        )
        result, call = self._log_and_capture(config, "rm -rf /tmp/x")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "rm -rf *")
        violated_rules = call.args[0].violated_rules
        self.assertEqual(violated_rules, ["rm -rf *"])

    def test_a_genuine_hard_deny_still_records_its_real_pattern(self):
        """
        Given a Bash command that matches an unoverridable [hard_deny] rule
            ('Bash(curl:*)')
        When it is hard-denied and logged
        Then the resolution's matched_rule and the logged violated rule are
            EXACTLY 'curl:*' -- pinning the exact attribution, not merely
            that SOME rule was named
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"hard_deny": {"deny": ["Bash(curl:*)"]}},
                )
            ]
        )
        result, call = self._log_and_capture(config, "curl http://x")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "curl:*")
        self.assertEqual(call.args[0].violated_rules, ["curl:*"])
        # Hard-deny is pooled across levels -- there is no single provenance
        # to attribute (see RuntimeVerdict.provenance's docstring).
        self.assertIsNone(result.provenance)

    def test_no_match_fallback_deny_has_no_colon_and_is_unaffected(self):
        """
        Given no_match_fallback='deny' (a config choice, distinct from
            undecidable_fallback) and a file path no Read rule covers at all
        When it is denied and logged
        Then the full reason (which never had a ': ' to begin with) is
            recorded as before -- this path was never at risk of fabrication,
            since :func:`~toolguard.compound.fallback_kind_for_reason` has no
            marker for it and the reason has no colon to mis-split, and stays
            untouched by the fix

        Uses the FILE-PATH resolver rather than Bash: unlike
        ``resolve_bash_permission_detailed``, ``resolve_file_path_permission_detailed``
        never wraps its reason in the "Compound command contains denied
        sub-command: ..." formatting (there is no compound-command concept
        for file paths), so this is the one real caller of
        ``_log_non_allow_decision`` that reaches it with the truly unwrapped,
        colon-free ``no_match_fallback`` reason from ``config.py``.
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {"allow": ["Read(other.txt)"], "deny": []},
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed("Read", "README.md", config)
        self.assertEqual(result.decision, "deny")
        self.assertNotIn(": ", result.reason)
        verdict = RuntimeVerdict(
            decision=result.decision,
            reason=result.reason,
            matched_rule=result.matched_rule,
            additional_context=result.additional_context,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_non_allow_decision(
                verdict, "Read(README.md)", "main", {"logging_enabled": True}, None
            )
        self.assertEqual(len(mock_log.call_args_list), 1)
        self.assertEqual(
            mock_log.call_args_list[0].args[0].violated_rules, [result.reason]
        )

    def test_ask_side_is_unaffected_full_reason_is_always_the_note(self):
        """
        Given the same escape-hatch scenario but undecidable_fallback='ask'
            (the default), so the floor produces 'ask' rather than 'deny'
        When the leaf is floored to 'ask' and logged
        Then the FULL reason text is recorded as the note verbatim -- the
            'ask' branch of _log_non_allow_decision never splits the reason,
            so it was never at risk of this fabrication; this pins that it
            stays that way
        """
        config = self._repro_config("ask")
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            'python -c "print(1)"', config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "ask")
        verdict = RuntimeVerdict(
            decision=result.decision,
            reason=result.reason,
            matched_rule=result.matched_rule,
            additional_context=result.additional_context,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_non_allow_decision(
                verdict, 'python -c "print(1)"', "main", {"logging_enabled": True}, None
            )
        self.assertEqual(len(mock_log.call_args_list), 1)
        call = mock_log.call_args_list[0]
        self.assertEqual(call.args[0].note, result.reason)
        # 'ask' never populates violated_rules on the logged record --
        # there is no violation to name a rule for.
        self.assertEqual(
            call.args[0].violated_rules, [], "ask must not pass violated_rules"
        )


class TestAuditLogProvenanceThreading(unittest.TestCase):
    """
    TOO-45 R3 review follow-up: provenance was silently LOST from the audit
    log once matched_rule/violated_rules stopped carrying it as a bracketed
    text suffix (see RuntimeVerdict.provenance's docstring). These tests
    drive the REAL resolve.py -> hook.py -> log_command pipeline end to end
    and pin that the log's Provenance field gets the right value for allow,
    deny, and hard-deny -- rendering itself is covered separately by
    test_log_writer.TestProvenanceLogging.
    """

    def _config(self, content):
        return _make_config([("project", "toolguard_hook", content)])

    def test_allow_logs_the_winning_rules_provenance(self):
        """
        Given a config allowing 'Bash(ls)' at the project level
        When 'ls' is resolved, allowed, and logged
        Then the log_command call's provenance kwarg is the SAME brief
            description as result.provenance.describe_brief()
        """
        config = self._config({"permissions": {"allow": ["Bash(ls)"], "deny": []}})
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed("ls", config, True, hd_deny, hd_allow)
        self.assertEqual(result.decision, "allow")
        self.assertIsNotNone(result.provenance)
        verdict = RuntimeVerdict(
            decision="allow",
            reason=result.reason,
            matched_rule=result.matched_rule,
            provenance=result.provenance,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_allowed_command(verdict, "ls", "main", {"logging_enabled": True})
        self.assertEqual(
            mock_log.call_args_list[0].args[0].provenance,
            result.provenance.describe_brief(),
        )

    def test_deny_logs_the_violated_rules_provenance(self):
        """
        Given a config denying 'Bash(rm -rf *)' at the project level
        When 'rm -rf /tmp/x' is resolved, denied, and logged
        Then the log_command call's provenance kwarg is the SAME brief
            description as result.provenance.describe_brief()
        """
        config = self._config(
            {"permissions": {"allow": ["Bash(*)"], "deny": ["Bash(rm -rf *)"]}}
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "rm -rf /tmp/x", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "deny")
        self.assertIsNotNone(result.provenance)
        verdict = RuntimeVerdict(
            decision=result.decision,
            reason=result.reason,
            matched_rule=result.matched_rule,
            additional_context=result.additional_context,
            provenance=result.provenance,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_non_allow_decision(
                verdict, "rm -rf /tmp/x", "main", {"logging_enabled": True}, None
            )
        self.assertEqual(
            mock_log.call_args_list[0].args[0].provenance,
            result.provenance.describe_brief(),
        )

    def test_hard_deny_logs_no_provenance(self):
        """
        Given a Bash hard_deny for 'curl:*' (pooled across levels)
        When 'curl http://x' is resolved, hard-denied, and logged
        Then result.provenance is None and the log_command call's
            provenance kwarg is None too -- by design, not omission
        """
        config = self._config({"hard_deny": {"deny": ["Bash(curl:*)"]}})
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "curl http://x", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "deny")
        self.assertIsNone(result.provenance)
        verdict = RuntimeVerdict(
            decision=result.decision,
            reason=result.reason,
            matched_rule=result.matched_rule,
            additional_context=result.additional_context,
            provenance=result.provenance,
        )
        with patch("toolguard.hook.log_command") as mock_log:
            _log_non_allow_decision(
                verdict, "curl http://x", "main", {"logging_enabled": True}, None
            )
        self.assertIsNone(mock_log.call_args_list[0].args[0].provenance)


class TestFallbackWarningField(unittest.TestCase):
    """
    TOO-19 allow/allow_with_no_warnings work: RuntimeVerdict.fallback_warning
    correctly distinguishes an 'allow' produced by ``allow_with_warning``
    (True -- route to the WARNING log stream) from one produced by
    ``allow``/``allow_with_no_warnings`` (False -- no warning anywhere), for
    both settings and both the file-path and
    Bash resolution paths. Also guards the marker-safety property
    hook.py/resolve.py rely on: the newer no-warning reason text must never
    accidentally contain the ``allow_with_warning`` marker substring.
    """

    def test_no_match_fallback_allow_with_warning_sets_bash_fallback_warning_true(
        self,
    ):
        """
        Given Bash allows only 'git:*' and no_match_fallback='allow_with_warning'
        When resolve_bash_permission_detailed() resolves an unmatched command
        Then the decision is 'allow' and fallback_warning is True
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(git:*)"], "deny": []},
                    },
                )
            ]
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "ls -la", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertTrue(result.fallback_warning)

    def test_no_match_fallback_allow_sets_bash_fallback_warning_false(self):
        """
        Given Bash allows only 'git:*' and no_match_fallback='allow' (TOO-19)
        When resolve_bash_permission_detailed() resolves an unmatched command
        Then the decision is 'allow' and fallback_warning is False -- no
            warning is ever emitted for the plain 'allow' value
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow",
                        "permissions": {"allow": ["Bash(git:*)"], "deny": []},
                    },
                )
            ]
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "ls -la", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertFalse(result.fallback_warning)
        self.assertNotIn("allow_with_warning", result.reason)

    def test_no_match_fallback_allow_with_no_warnings_alias_matches_allow(self):
        """
        Given Bash allows only 'git:*' and
            no_match_fallback='allow_with_no_warnings' (the long-form alias)
        When resolve_bash_permission_detailed() resolves an unmatched command
        Then it behaves IDENTICALLY to 'allow': decision 'allow',
            fallback_warning False, no 'allow_with_warning' substring in reason
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_no_warnings",
                        "permissions": {"allow": ["Bash(git:*)"], "deny": []},
                    },
                )
            ]
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "ls -la", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertFalse(result.fallback_warning)
        self.assertNotIn("allow_with_warning", result.reason)
        self.assertIn("no_match_fallback=allow", result.reason)

    def test_no_match_fallback_allow_with_warning_sets_file_fallback_warning_true(
        self,
    ):
        """
        Given Read allows only '/tmp/**' and no_match_fallback='allow_with_warning'
        When resolve_file_path_permission_detailed() resolves an unmatched path
        Then the decision is 'allow' and fallback_warning is True
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/etc/passwd", config, True
        )
        self.assertEqual(result.decision, "allow")
        self.assertTrue(result.fallback_warning)

    def test_no_match_fallback_allow_sets_file_fallback_warning_false(self):
        """
        Given Read allows only '/tmp/**' and no_match_fallback='allow' (TOO-19)
        When resolve_file_path_permission_detailed() resolves an unmatched path
        Then the decision is 'allow' and fallback_warning is False, and the
            reason text does not claim a warning was emitted
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow",
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/etc/passwd", config, True
        )
        self.assertEqual(result.decision, "allow")
        self.assertFalse(result.fallback_warning)
        self.assertIn("no warning", result.reason)
        self.assertNotIn("allow_with_warning", result.reason)

    def test_explicit_rule_match_never_sets_fallback_warning(self):
        """
        Given Bash allows 'git:*' and no_match_fallback='allow_with_warning'
        When resolve_bash_permission_detailed() resolves a command that
            matches the EXPLICIT allow rule (not the fallback)
        Then fallback_warning is False -- an explicit rule match is never
            mistaken for a fallback-driven allow, however the fallback
            setting happens to be configured
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "allow_with_warning",
                        "permissions": {"allow": ["Bash(git:*)"], "deny": []},
                    },
                )
            ]
        )
        hd_deny, hd_allow = config.hard_deny("Bash")
        result = resolve_bash_permission_detailed(
            "git status", config, True, hd_deny, hd_allow
        )
        self.assertEqual(result.decision, "allow")
        self.assertFalse(result.fallback_warning)

    def test_undecidable_fallback_ask_floor_leaf_reason_text_by_value(self):
        """
        Given a foreign inline-code command with the outer command allowed
        When undecidable_fallback is 'allow_with_warning' vs 'allow'
        Then only the 'allow_with_warning' reason claims a warning was
            emitted; the 'allow' reason says "no warning" and never contains
            the 'allow_with_warning' marker substring
        """
        cmd = 'python3 -c "import os"'
        for fallback, warned in (("allow_with_warning", True), ("allow", False)):
            with self.subTest(fallback=fallback):
                config = _make_config(
                    [
                        (
                            "project",
                            "toolguard_hook",
                            {
                                "undecidable_fallback": fallback,
                                "permissions": {
                                    "allow": ["Bash(python3 -c:*)"],
                                    "deny": [],
                                },
                            },
                        )
                    ]
                )
                hd_deny, hd_allow = config.hard_deny("Bash")
                result = resolve_bash_permission_detailed(
                    cmd, config, True, hd_deny, hd_allow
                )
                self.assertEqual(result.decision, "allow")
                self.assertEqual(result.fallback_warning, warned)
                if warned:
                    self.assertIn(
                        "undecidable_fallback=allow_with_warning", result.reason
                    )
                else:
                    self.assertIn("no warning", result.reason)
                    self.assertNotIn("allow_with_warning", result.reason)

    def test_undecidable_fallback_segment_reason_text_by_value(self):
        """
        Given a process-substitution command (grammar-level UndecidableSegment)
        When undecidable_fallback is 'allow_with_warning' vs 'allow'
        Then only the 'allow_with_warning' reason claims a warning was
            emitted; the 'allow' reason says "no warning" and never contains
            the 'allow_with_warning' marker substring
        """
        cmd = "diff <(sort a) <(sort b)"
        for fallback, warned in (("allow_with_warning", True), ("allow", False)):
            with self.subTest(fallback=fallback):
                config = _make_config(
                    [
                        (
                            "project",
                            "toolguard_hook",
                            {
                                "undecidable_fallback": fallback,
                                "permissions": {
                                    "allow": ["Bash(diff:*)"],
                                    "deny": [],
                                },
                            },
                        )
                    ]
                )
                hd_deny, hd_allow = config.hard_deny("Bash")
                result = resolve_bash_permission_detailed(
                    cmd, config, True, hd_deny, hd_allow
                )
                self.assertEqual(result.decision, "allow")
                self.assertEqual(result.fallback_warning, warned)
                if warned:
                    self.assertIn(
                        "undecidable_fallback=allow_with_warning", result.reason
                    )
                else:
                    self.assertIn("no warning", result.reason)
                    self.assertNotIn("allow_with_warning", result.reason)


class TestParseFailureFloorCoversUndecidableSegments(unittest.TestCase):
    """
    TOO-19 fail-open fix: a grammar-level UndecidableSegment (process
    substitution, an unparseable control structure) has NO leaves and so
    never calls permission_resolution.resolve_permission_detailed -- unlike
    an ask_floor LEAF (foreign inline code / heredoc), which does. Before this
    fix, that meant the parse-failure ASK floor never ran for it, and a
    broken config combined with undecidable_fallback='allow_with_warning'
    resolved such commands to 'allow'. See
    TestUndecidableFallbackThreading.test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback
    above for the LEAF case this class is deliberately NOT duplicating --
    that test predates this fix and is a false-confidence test for this bug:
    it exercises the already-covered leaf path, not the true
    UndecidableSegment gap this class targets.

    Configurations are hand-built via ``_config_with_fallback`` (zero file
    I/O) per the existing pattern in ``TestUndecidableFallbackThreading``, so
    no ConfigIsolationMixin is needed (test-config-isolation.md: only
    required when a test reaches toolguard.config's discovery path).
    """

    def _config_with_fallback(self, undecidable_fallback, allow=(), parse_failures=()):
        """Return a config with the given undecidable_fallback and parse_failures set."""
        content = {
            "undecidable_fallback": undecidable_fallback,
            "permissions": {
                "allow": [f"Bash({p})" for p in allow],
                "deny": [],
            },
        }
        config = _make_config([("project", "toolguard_hook", content)])
        return Configuration(
            layers=config.layers,
            start_dir=config.start_dir,
            parse_failures=parse_failures,
        )

    def _resolve(self, config, command):
        """Resolve *command* through resolve_bash_permission_detailed."""
        hd_deny, hd_allow = config.hard_deny("Bash")
        return resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )

    def test_parse_failure_floor_covers_undecidable_segments_that_bypass_the_per_leaf_chokepoint(
        self,
    ):
        """
        Given a broken config file (recorded parse failure) AND
            undecidable_fallback='allow_with_warning' AND an allow pattern
            that would otherwise permit the outer command
        When resolve_bash_permission_detailed() resolves a process
            -substitution command (a grammar-level UndecidableSegment with no
            leaves, unlike the ask_floor-leaf foreign-inline-code case)
        Then the decision is 'ask' and the reason names the broken config
            file -- the parse-failure floor must catch this verdict at the
            compound boundary since it never reaches the per-leaf chokepoint
        """
        broken = Path("/fake/project/toolguard_hook.local.toml")
        config = self._config_with_fallback(
            "allow_with_warning",
            allow=["diff:*"],
            parse_failures=((broken, "unexpected character"),),
        )

        result = self._resolve(config, "diff <(sort a) <(sort b)")

        self.assertEqual(result.decision, "ask")
        self.assertIn(str(broken), result.reason)

    def test_grammar_parse_failure_undecidable_segment_also_floored(self):
        """
        Given a broken config file AND undecidable_fallback='allow_with_warning'
        When resolve_bash_permission_detailed() resolves a 'case' command --
            an UndecidableSegment built from the OTHER construction site
            (a genuine grammar parse failure in
            toolguard/parser/multiline.py, distinct from the process
            -substitution detection site)
        Then the decision is still 'ask', proving the fix covers both
            UndecidableSegment construction sites, not just one
        """
        broken = Path("/fake/project/toolguard_hook.local.toml")
        config = self._config_with_fallback(
            "allow_with_warning",
            parse_failures=((broken, "unexpected character"),),
        )

        result = self._resolve(config, "case $x in a) b;; esac")

        self.assertEqual(result.decision, "ask")
        self.assertIn(str(broken), result.reason)

    def test_broken_config_undecidable_segment_stays_deny_under_deny_fallback(self):
        """
        Given a broken config file AND undecidable_fallback='deny'
        When resolve_bash_permission_detailed() resolves a process
            -substitution command
        Then the decision stays 'deny' -- the parse-failure floor never
            weakens a deny, so the pre-existing deny (from
            undecidable_fallback itself, independent of the broken config)
            is preserved unchanged
        """
        broken = Path("/fake/project/toolguard_hook.local.toml")
        config = self._config_with_fallback(
            "deny",
            allow=["diff:*"],
            parse_failures=((broken, "unexpected character"),),
        )

        result = self._resolve(config, "diff <(sort a) <(sort b)")

        self.assertEqual(result.decision, "deny")

    def test_no_parse_failure_allow_with_warning_undecidable_segment_still_allows(self):
        """
        Given NO recorded parse failure AND undecidable_fallback='allow_with_warning'
        When resolve_bash_permission_detailed() resolves a process
            -substitution command
        Then the decision is 'allow' -- proving the fix does not disable the
            allow_with_warning escape hatch outright, only closes the hole
            that let a BROKEN config bypass the floor
        """
        config = self._config_with_fallback("allow_with_warning", allow=["diff:*"])

        result = self._resolve(config, "diff <(sort a) <(sort b)")

        self.assertEqual(result.decision, "allow")

    def test_normal_decomposable_command_under_broken_config_clamped_exactly_once(
        self,
    ):
        """
        Given a broken config file AND a normal, fully-decomposable command
            that matches an allow pattern
        When resolve_bash_permission_detailed() resolves it
        Then the decision is 'ask' with the single broken-config-file ASK
            -floor reason -- exactly the pre-existing per-leaf-floor
            behaviour, proving the new compound-boundary re-application is a
            no-op (idempotent) for the already-covered leaf case and does not
            double up or corrupt the reason
        """
        broken = Path("/fake/project/toolguard_hook.local.toml")
        config = self._config_with_fallback(
            "ask", allow=["git:*"], parse_failures=((broken, "unexpected character"),)
        )

        result = self._resolve(config, "git status")

        self.assertEqual(result.decision, "ask")
        self.assertEqual(result.reason.count(str(broken)), 1)
        self.assertIn("toolguard config is BROKEN", result.reason)


class TestFilePathMatchedRuleExact(unittest.TestCase):
    """
    TOO-45 R3 review follow-up: pin RuntimeVerdict.matched_rule (for a
    file-path resolution) to the exact
    pattern text, not merely non-None/substring, so a mutation that swaps in
    a wrong-but-plausible value (e.g. the reason string) fails these tests.
    """

    def test_allow_matched_rule_is_exactly_the_configured_pattern(self):
        """
        Given a config allowing 'Read(/tmp/x/**)'
        When a path under that tree is resolved
        Then RuntimeVerdict.matched_rule is EXACTLY '/tmp/x/**'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Read(/tmp/x/**)"], "deny": []}},
                )
            ]
        )
        result = resolve_file_path_permission_detailed("Read", "/tmp/x/foo.txt", config)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.matched_rule, "/tmp/x/**")

    def test_deny_matched_rule_is_exactly_the_configured_pattern(self):
        """
        Given a config denying 'Read(/secrets/**)'
        When a path under that tree is resolved
        Then RuntimeVerdict.matched_rule is EXACTLY '/secrets/**'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read(**)"],
                            "deny": ["Read(/secrets/**)"],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/secrets/passwd", config
        )
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.matched_rule, "/secrets/**")

    def test_hard_deny_matched_rule_is_none_and_unattributed(self):
        """
        Given a Read hard_deny for '/etc/**' (no normal-cascade pattern
            available to attribute -- see resolve_file_path_permission_detailed's
            hard-deny branch)
        When a path under that tree is resolved
        Then RuntimeVerdict.matched_rule and .provenance are both None --
            deliberately, not by omission
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"hard_deny": {"deny": ["Read(/etc/**)"]}},
                )
            ]
        )
        result = resolve_file_path_permission_detailed("Read", "/etc/passwd", config)
        self.assertEqual(result.decision, "deny")
        self.assertIsNone(result.matched_rule)
        self.assertIsNone(result.provenance)


class TestFilePathAdditionalContext(unittest.TestCase):
    """
    TOO-19 Phase 1, increment 2: RuntimeVerdict.additional_context is threaded
    through from the winning RuleEntry's additional_context property (or, for
    a hard-deny match, from the matched hard_deny entry) for Read/Write/Edit.

    Configurations are built directly from :func:`_make_config` (hand-built
    ConfigLayer/Provenance, zero file I/O), so no ConfigIsolationMixin is
    needed (per test/unit/CLAUDE.md's checklist). Absolute patterns are used
    throughout to avoid project-root anchoring concerns, which are out of
    scope here.
    """

    def test_read_allow_structured_entry_surfaces_additional_context(self):
        """
        Given a Read allow structured entry for '/tmp/**' carrying
            additionalContext = 'scratch space only'
        When resolve_file_path_permission_detailed('Read', ...) resolves a
            path under /tmp
        Then the decision is 'allow' and additional_context is
            'scratch space only'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Read(/tmp/**)",
                                    "additionalContext": "scratch space only",
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/tmp/some/file.txt", config, True
        )
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.additional_context, "scratch space only")

    def test_write_deny_structured_entry_surfaces_additional_context(self):
        """
        Given a Write deny structured entry for '/etc/**' carrying
            additionalContext = 'system files are off limits'
        When resolve_file_path_permission_detailed('Write', ...) resolves a
            path under /etc
        Then the decision is 'deny' and additional_context is
            'system files are off limits'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "deny": [
                                {
                                    "match": "Write(/etc/**)",
                                    "additionalContext": (
                                        "system files are off limits"
                                    ),
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Write", "/etc/passwd", config, True
        )
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.additional_context, "system files are off limits")

    def test_edit_ask_structured_entry_surfaces_additional_context(self):
        """
        Given an Edit ask structured entry for '/srv/**' carrying
            additionalContext = 'confirm before editing shared files'
        When resolve_file_path_permission_detailed('Edit', ...) resolves a
            path under /srv
        Then the decision is 'ask' and additional_context is
            'confirm before editing shared files'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "ask": [
                                {
                                    "match": "Edit(/srv/**)",
                                    "additionalContext": (
                                        "confirm before editing shared files"
                                    ),
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Edit", "/srv/shared/file.txt", config, True
        )
        self.assertEqual(result.decision, "ask")
        self.assertEqual(
            result.additional_context, "confirm before editing shared files"
        )

    def test_plain_string_rule_yields_none(self):
        """
        Given a plain-string (unstructured) Read allow rule for '/tmp/**'
        When resolve_file_path_permission_detailed('Read', ...) resolves a
            match
        Then the decision is 'allow' and additional_context is None
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Read(/tmp/**)"]}},
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/tmp/some/file.txt", config, True
        )
        self.assertEqual(result.decision, "allow")
        self.assertIsNone(result.additional_context)

    def test_hard_deny_carries_additional_context(self):
        """
        Given a Read hard_deny structured entry for '/secret/**' carrying
            additionalContext = 'never read secrets'
        When resolve_file_path_permission_detailed('Read', ...) resolves a
            path under /secret
        Then the decision is 'deny' (unoverridable hard-deny) and
            additional_context is 'never read secrets'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "hard_deny": {
                            "deny": [
                                {
                                    "match": "Read(/secret/**)",
                                    "additionalContext": "never read secrets",
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/secret/key.txt", config, True
        )
        self.assertEqual(result.decision, "deny")
        self.assertIn("hard_deny", result.reason)
        self.assertEqual(result.additional_context, "never read secrets")


class TestBashAdditionalContext(unittest.TestCase):
    """
    TOO-19 Phase 1, increments 3 and 5: RuntimeVerdict.additional_context is
    threaded through resolve_bash_permission_detailed -> resolve_compound_permission,
    sourcing the per-sub-command context from the internal per-level
    RuntimeVerdict.additional_context (already populated by increment 2's
    permission_resolution._resolve_unclamped).
    """

    def _resolve(self, config, command, extended_syntax=True):
        """Resolve a Bash command through resolve_bash_permission_detailed."""
        hd_deny, hd_allow = config.hard_deny("Bash")
        return resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

    def test_single_allow_structured_entry_surfaces_additional_context(self):
        """
        Given a Bash allow structured entry for 'git *' carrying
            additionalContext = 'prefer git status --short'
        When resolve_bash_permission_detailed resolves 'git status'
        Then the decision is 'allow' and additional_context is
            'prefer git status --short'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git *)",
                                    "additionalContext": "prefer git status --short",
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve(config, "git status")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.additional_context, "prefer git status --short")

    def test_compound_all_allow_accumulates_two_distinct_contexts(self):
        """
        Given Bash allow structured entries for 'git *' and 'cat *', each
            carrying a DIFFERENT additionalContext
        When resolve_bash_permission_detailed resolves the all-allow compound
            'git status && cat file'
        Then the decision is 'allow' and additional_context is both texts
            joined as paragraphs, in match order
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git *)",
                                    "additionalContext": "git note",
                                },
                                {
                                    "match": "Bash(cat *)",
                                    "additionalContext": "cat note",
                                },
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve(config, "git status && cat file")
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.additional_context, "git note\n\ncat note")

    def test_compound_deny_surfaces_denying_subcommands_context_only(self):
        """
        Given a Bash allow structured entry for 'git *' (with its own
            context) and a deny structured entry for 'rm *' (with a
            different context)
        When resolve_bash_permission_detailed resolves the compound
            'git status && rm -rf /'
        Then the decision is 'deny' and additional_context is the DENYING
            rule's context alone, not an accumulation
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git *)",
                                    "additionalContext": "git note",
                                }
                            ],
                            "deny": [
                                {
                                    "match": "Bash(rm *)",
                                    "additionalContext": "never rm -rf",
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve(config, "git status && rm -rf /")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.additional_context, "never rm -rf")

    def test_plain_string_rule_yields_none_context(self):
        """
        Given a plain-string (unstructured) Bash allow rule for 'git *'
        When resolve_bash_permission_detailed resolves 'git status'
        Then the decision is 'allow' and additional_context is None
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Bash(git *)"]}},
                )
            ]
        )
        result = self._resolve(config, "git status")
        self.assertEqual(result.decision, "allow")
        self.assertIsNone(result.additional_context)

    def test_bash_hard_deny_carries_additional_context(self):
        """
        Given a Bash hard_deny structured entry for 'rm -rf /*' carrying
            additionalContext = 'ask a human first'
        When resolve_bash_permission_detailed resolves a matching command
        Then the decision is 'deny' and additional_context is
            'ask a human first' -- the Bash hard-deny pool surfaces enrichment
            exactly like the file-path pool does, via the shared
            _hard_deny_additional_context lookup. An asymmetry between the two
            would make any documentation of the feature wrong for one tool
            family.
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "hard_deny": {
                            "deny": [
                                {
                                    "match": "Bash(rm -rf /*)",
                                    "additionalContext": "ask a human first",
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve(config, "rm -rf /tmp")
        self.assertEqual(result.decision, "deny")
        self.assertIn("hard_deny", result.reason)
        self.assertEqual(result.additional_context, "ask a human first")

    def test_bash_hard_deny_without_enrichment_yields_none(self):
        """
        Given a plain-string Bash hard_deny pattern carrying no enrichment
        When resolve_bash_permission_detailed resolves a matching command
        Then the decision is 'deny' and additional_context is None -- the
            lookup adds nothing where there is nothing to add
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"hard_deny": {"deny": ["Bash(rm -rf /*)"]}},
                )
            ]
        )
        result = self._resolve(config, "rm -rf /tmp")
        self.assertEqual(result.decision, "deny")
        self.assertIsNone(result.additional_context)


class TestAdditionalContextBudgetAtInjectionBoundary(unittest.TestCase):
    """
    TOO-19 code review M2: the 500-word additionalContext budget is now
    enforced once, uniformly, at the two true injection-boundary functions in
    this module -- resolve_bash_permission_detailed and
    resolve_file_path_permission_detailed -- rather than only inside
    compound._accumulate_contexts's Bash all-allow branch. These tests prove
    (a) a LONE over-budget entry is truncated with a marker rather than
    silently vanishing to None, for both a Bash rule and a Read/Write/Edit
    rule, and (b) deny and hard-deny contexts -- previously uncapped
    entirely -- are now capped too.
    """

    _OVER_BUDGET = " ".join(f"w{i}" for i in range(600))

    def _resolve_bash(self, config, command):
        """Resolve a Bash command through resolve_bash_permission_detailed."""
        hd_deny, hd_allow = config.hard_deny("Bash")
        return resolve_bash_permission_detailed(
            command, config, True, hd_deny, hd_allow
        )

    def test_lone_oversize_bash_allow_context_is_truncated_not_dropped(self):
        """
        Given a Bash allow structured entry whose additionalContext alone is
            600 words (over the 500-word budget)
        When resolve_bash_permission_detailed resolves a matching command
        Then additional_context is NOT None -- it is truncated to 500 words
            plus a marker, fixing the M2 silent-drop bug
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git status:*)",
                                    "additionalContext": self._OVER_BUDGET,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve_bash(config, "git status")
        self.assertEqual(result.decision, "allow")
        self.assertIsNotNone(result.additional_context)
        self.assertIn("truncated to 500 words", result.additional_context)
        kept_prefix = result.additional_context.split("\n\n[toolguard:")[0]
        self.assertEqual(len(kept_prefix.split()), 500)

    def test_lone_oversize_read_allow_context_is_truncated_not_dropped(self):
        """
        Given a Read allow structured entry whose additionalContext alone is
            600 words (over the 500-word budget)
        When resolve_file_path_permission_detailed resolves a matching path
        Then additional_context is NOT None -- it is truncated to 500 words
            plus a marker. Before M2, a Read rule's context was injected
            UNCAPPED regardless of length; this proves it is now bounded.
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Read(/tmp/**)",
                                    "additionalContext": self._OVER_BUDGET,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/tmp/some/file.txt", config, True
        )
        self.assertEqual(result.decision, "allow")
        self.assertIsNotNone(result.additional_context)
        self.assertIn("truncated to 500 words", result.additional_context)
        kept_prefix = result.additional_context.split("\n\n[toolguard:")[0]
        self.assertEqual(len(kept_prefix.split()), 500)

    def test_bash_deny_context_is_now_capped(self):
        """
        Given a Bash deny structured entry whose additionalContext alone is
            600 words -- the deny branch never called _accumulate_contexts
            pre-M2, so this was injected fully uncapped
        When resolve_bash_permission_detailed resolves a matching command
        Then additional_context is capped to 500 words plus a marker
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "deny": [
                                {
                                    "match": "Bash(rm -rf /*)",
                                    "additionalContext": self._OVER_BUDGET,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve_bash(config, "rm -rf /tmp")
        self.assertEqual(result.decision, "deny")
        self.assertIsNotNone(result.additional_context)
        kept_prefix = result.additional_context.split("\n\n[toolguard:")[0]
        self.assertEqual(len(kept_prefix.split()), 500)

    def test_bash_hard_deny_context_is_now_capped(self):
        """
        Given a Bash hard_deny structured entry whose additionalContext alone
            is 600 words -- the hard-deny lookup was never routed through the
            budget pre-M2
        When resolve_bash_permission_detailed resolves a matching command
        Then additional_context is capped to 500 words plus a marker
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "hard_deny": {
                            "deny": [
                                {
                                    "match": "Bash(rm -rf /*)",
                                    "additionalContext": self._OVER_BUDGET,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = self._resolve_bash(config, "rm -rf /tmp")
        self.assertEqual(result.decision, "deny")
        self.assertIn("hard_deny", result.reason)
        self.assertIsNotNone(result.additional_context)
        kept_prefix = result.additional_context.split("\n\n[toolguard:")[0]
        self.assertEqual(len(kept_prefix.split()), 500)

    def test_file_hard_deny_context_is_now_capped(self):
        """
        Given a Read hard_deny structured entry whose additionalContext alone
            is 600 words
        When resolve_file_path_permission_detailed resolves a matching path
        Then additional_context is capped to 500 words plus a marker
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "hard_deny": {
                            "deny": [
                                {
                                    "match": "Read(/secret/**)",
                                    "additionalContext": self._OVER_BUDGET,
                                }
                            ],
                        }
                    },
                )
            ]
        )
        result = resolve_file_path_permission_detailed(
            "Read", "/secret/key.txt", config, True
        )
        self.assertEqual(result.decision, "deny")
        self.assertIsNotNone(result.additional_context)
        kept_prefix = result.additional_context.split("\n\n[toolguard:")[0]
        self.assertEqual(len(kept_prefix.split()), 500)


if __name__ == "__main__":
    unittest.main()
