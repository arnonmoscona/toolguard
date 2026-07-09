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
        return _make_config([
            ("project", "toolguard_hook", {
                "permissions": {
                    "allow": ["Bash(git:*)", "Bash(ls:*)"],
                    "deny": [],
                },
                "hard_deny": {
                    "deny": ["Bash(rm -rf:*)"],
                    "allow": [],
                },
            })
        ])

    def _read_config(self):
        """Return a config that allows Read under /tmp only."""
        return _make_config([
            ("project", "toolguard_hook", {
                "permissions": {
                    "allow": ["Read([glob]/tmp/**)"],
                    "deny": [],
                }
            })
        ])

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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for Bash allow: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for compound Bash allow: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for hard-deny Bash: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for Read allow: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
        self.assertEqual("allow", decision_verdict)

    def test_read_deny_no_drift(self):
        """
        Given a config that allows Read under /tmp/** only
        When decide() and resolve_file_path_permission_detailed() are called with
        '/etc/passwd' (outside allowed path)
        Then both produce the same verdict ('deny')
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for Read deny: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
        self.assertEqual("deny", decision_verdict)


class TestNoMatchSemanticsNoDrift(unittest.TestCase):
    """
    TOO-15: anti-drift coverage for the new no-match resolution semantics.

    Same "same code, same results" property as :class:`TestNoDrift`, but for
    the NEW behaviour: a fully-unconfigured tool resolves to 'ask' (never
    affected by no_match_fallback); a tool with rules that simply do not match
    resolves per no_match_fallback (default 'deny', or 'warn_deny' -> allow).
    """

    def _empty_config(self):
        """Return a config with NO permissions/hard_deny sections at all."""
        return _make_config([("project", "toolguard_hook", {})])

    def _bash_configured_no_match_config(self):
        """Return a config that allows only 'git:*' for Bash (no hard_deny)."""
        return _make_config([
            ("project", "toolguard_hook", {
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": [],
                },
            })
        ])

    def _read_configured_no_match_config(self):
        """Return a config that allows Read only under /tmp/** (no hard_deny)."""
        return _make_config([
            ("project", "toolguard_hook", {
                "permissions": {
                    "allow": ["Read([glob]/tmp/**)"],
                    "deny": [],
                }
            })
        ])

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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for unconfigured Bash: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for unconfigured Read: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
        self.assertEqual("ask", decision_verdict)

    def test_bash_rules_exist_no_match_denies_by_default_no_drift(self):
        """
        Given Bash allows only 'git:*' (rules ARE configured) and no
            no_match_fallback override
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'deny' (default no_match_fallback)
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

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for Bash no-match: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
        self.assertEqual("deny", decision_verdict)

    def test_read_rules_exist_no_match_denies_by_default_no_drift(self):
        """
        Given Read allows only '/tmp/**' (rules ARE configured) and no
            no_match_fallback override
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'deny' (default no_match_fallback)
        """
        config = self._read_configured_no_match_config()
        file_path = "/etc/passwd"
        extended_syntax = True

        decision_verdict = decide(config, "Read", file_path, extended_syntax).verdict

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )
        resolve_verdict = file_result.decision

        self.assertEqual(resolve_verdict, decision_verdict,
                         f"Drift detected for Read no-match: resolve={resolve_verdict}, "
                         f"decide={decision_verdict}")
        self.assertEqual("deny", decision_verdict)

    def test_bash_warn_deny_fallback_allows_no_drift(self):
        """
        Given Bash allows only 'git:*' and top-level no_match_fallback='warn_deny'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
            (does not match any rule)
        Then both agree the verdict is 'allow' (auto-allowed with a warning reason)
        """
        config = _make_config([
            ("project", "toolguard_hook", {
                "no_match_fallback": "warn_deny",
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": [],
                },
            })
        ])
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.verdict,
                         f"Drift detected for Bash warn_deny: resolve={bash_result.decision}, "
                         f"decide={decision.verdict}")
        self.assertEqual("allow", decision.verdict)
        self.assertIn("warn_deny", bash_result.reason)

    def test_read_warn_deny_fallback_allows_no_drift(self):
        """
        Given Read allows only '/tmp/**' and top-level no_match_fallback='warn_deny'
        When decide() and resolve_file_path_permission_detailed() evaluate
            '/etc/passwd' (does not match any rule)
        Then both agree the verdict is 'allow' (auto-allowed with a warning reason)
        """
        config = _make_config([
            ("project", "toolguard_hook", {
                "no_match_fallback": "warn_deny",
                "permissions": {
                    "allow": ["Read([glob]/tmp/**)"],
                    "deny": [],
                },
            })
        ])
        file_path = "/etc/passwd"
        extended_syntax = True

        decision = decide(config, "Read", file_path, extended_syntax)

        file_result = resolve_file_path_permission_detailed(
            "Read", file_path, config, extended_syntax
        )

        self.assertEqual(file_result.decision, decision.verdict,
                         f"Drift detected for Read warn_deny: resolve={file_result.decision}, "
                         f"decide={decision.verdict}")
        self.assertEqual("allow", decision.verdict)
        self.assertIn("warn_deny", file_result.reason)

    def test_legacy_takeover_alias_warn_deny_honored_no_drift(self):
        """
        Given ONLY the legacy [takeover_mode].no_match_fallback='warn_deny' is set
            (no top-level key), and Bash allows only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
        Then both agree the verdict is 'allow' (legacy alias still honoured)
        """
        config = _make_config([
            ("project", "toolguard_hook", {
                "takeover_mode": {"no_match_fallback": "warn_deny"},
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": [],
                },
            })
        ])
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("allow", decision.verdict)

    def test_top_level_no_match_fallback_wins_over_legacy_alias_no_drift(self):
        """
        Given the top-level no_match_fallback='deny' AND the legacy
            [takeover_mode].no_match_fallback='warn_deny' are BOTH set, with Bash
            allowing only 'git:*'
        When decide() and resolve_bash_permission_detailed() evaluate 'ls -la'
        Then both agree the verdict is 'deny' (top-level wins over the legacy alias)
        """
        config = _make_config([
            ("project", "toolguard_hook", {
                "no_match_fallback": "deny",
                "takeover_mode": {"no_match_fallback": "warn_deny"},
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": [],
                },
            })
        ])
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
        config = _make_config([
            ("project", "toolguard_hook", {
                "takeover_mode": {"enabled": True, "no_match_fallback": "deny"},
                "permissions": {
                    "allow": ["Bash(git:*)"],
                    "deny": [],
                },
            })
        ])
        command = "ls -la"
        extended_syntax = True

        decision = decide(config, "Bash", command, extended_syntax)

        hd_deny, hd_allow = config.hard_deny("Bash")
        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )

        self.assertEqual(bash_result.decision, decision.verdict)
        self.assertEqual("deny", decision.verdict)


if __name__ == "__main__":
    unittest.main()
