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

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.decision import decide
from toolguard.resolve import (
    BashResolution,
    FileResolution,
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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, BashResolution)
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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, BashResolution)
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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        self.assertIsInstance(bash_result, BashResolution)
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

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        self.assertIsInstance(file_result, FileResolution)
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

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        self.assertIsInstance(file_result, FileResolution)
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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

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

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

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

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

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

        decision_verdict = decide(config, "Bash", command, extended_syntax).verdict

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

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

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
            decision.verdict,
            f"Drift detected for Bash allow_with_warning: "
            f"resolve={bash_result.decision}, decide={decision.verdict}",
        )
        self.assertEqual("allow", decision.verdict)
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
            decision.verdict,
            f"Drift detected for Read allow_with_warning: "
            f"resolve={file_result.decision}, decide={decision.verdict}",
        )
        self.assertEqual("allow", decision.verdict)
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
            decision.verdict,
            f"Drift detected for Bash warn_deny alias: "
            f"resolve={bash_result.decision}, decide={decision.verdict}",
        )
        self.assertEqual("allow", decision.verdict)
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
            decision.verdict,
            f"Drift detected for Read warn_deny alias: "
            f"resolve={file_result.decision}, decide={decision.verdict}",
        )
        self.assertEqual("allow", decision.verdict)
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

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("allow", decision.verdict)
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

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("deny", decision.verdict)

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

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("deny", decision.verdict)

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
            decision.verdict,
            f"Drift detected for takeover-enabled default: "
            f"resolve={bash_result.decision}, decide={decision.verdict}",
        )
        self.assertEqual("ask", decision.verdict)

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

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("allow", decision.verdict)


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
            three undecidable_fallback settings
        Then the decision matches that setting's floor exactly (ask/deny/allow)
        """
        cmd = 'python3 -c "import os"'
        expected = {"ask": "ask", "deny": "deny", "allow_with_warning": "allow"}
        for fallback, want in expected.items():
            with self.subTest(fallback=fallback):
                config = self._config_with_fallback(fallback, allow=["python3 -c:*"])
                result = self._resolve(config, cmd)
                self.assertEqual(result.decision, want)

    def test_undecidable_segment_under_each_fallback(self):
        """
        Given a process-substitution command (`diff <(sort a) <(sort b)`)
        When resolve_bash_permission_detailed() resolves it under each of the
            three undecidable_fallback settings
        Then the decision matches that setting's floor exactly (ask/deny/allow)
        """
        cmd = "diff <(sort a) <(sort b)"
        expected = {"ask": "ask", "deny": "deny", "allow_with_warning": "allow"}
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
        Configuration.resolve_permission_detailed -- and therefore through
        the parse-failure ASK floor -- cannot be downgraded below 'ask' by
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


class TestParseFailureFloorCoversUndecidableSegments(unittest.TestCase):
    """
    TOO-19 fail-open fix: a grammar-level UndecidableSegment (process
    substitution, an unparseable control structure) has NO leaves and so
    never calls Configuration.resolve_permission_detailed -- unlike an
    ask_floor LEAF (foreign inline code / heredoc), which does. Before this
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


class TestFilePathAdditionalContext(unittest.TestCase):
    """
    TOO-19 Phase 1, increment 2: FileResolution.additional_context is threaded
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

    def test_file_resolution_three_tuple_unpacking_still_works(self):
        """
        Given a FileResolution returned for a Read allow match
        When it is unpacked as a 3-tuple (decision, reason, override), the
            legacy calling convention
        Then unpacking succeeds and yields exactly (decision, reason,
            override) -- additional_context is a NEW field and must NOT be
            yielded, or every legacy 3-tuple call site would break
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
        decision, reason, override = result
        self.assertEqual(decision, result.decision)
        self.assertEqual(reason, result.reason)
        self.assertEqual(override, result.override)


class TestBashAdditionalContext(unittest.TestCase):
    """
    TOO-19 Phase 1, increments 3 and 5: BashResolution.additional_context is
    threaded through resolve_bash_permission_detailed -> resolve_compound_permission,
    sourcing the per-sub-command context from ResolvedDecision.additional_context
    (already populated by increment 2's Configuration._resolve_permission_detailed_unclamped).
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

    def test_bash_resolution_three_tuple_unpacking_still_works(self):
        """
        Given a BashResolution returned for a Bash allow match
        When it is unpacked as a 3-tuple (decision, reason, overrides), the
            legacy calling convention
        Then unpacking succeeds and yields exactly (decision, reason,
            overrides) -- additional_context is a NEW field and must NOT be
            yielded, or every legacy 3-tuple call site would break
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
        decision, reason, overrides = result
        self.assertEqual(decision, result.decision)
        self.assertEqual(reason, result.reason)
        self.assertEqual(overrides, result.overrides)

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
