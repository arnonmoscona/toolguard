"""
Unit tests for toolguard.tools.mining -- classifying a corpus into rule
candidates and verifying a proposed allow rule by decision-replay.

Tests cover:
- Signal classification: allow-candidate (ask-approved and deny-but-ran),
  declined, denied, asked, and consistent (omitted).
- Grouping by command key (Bash executable token; file-tool parent dir).
- Sorting and min_occurrences filtering.
- evaluate_added_allow_rule: replay-measured newly-allowed commands.
- render_mining_report formatting and invalid-format handling.
"""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.mining import (
    SIGNAL_ALLOW_CANDIDATE,
    SIGNAL_ASKED,
    SIGNAL_CONSISTENT,
    SIGNAL_DECLINED,
    SIGNAL_DENIED,
    _classify,
    evaluate_added_allow_rule,
    mine_rule_candidates,
    render_mining_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prov(path: str = "/fake/.claude/toolguard_hook.toml") -> Provenance:
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(path),
        specificity=0,
    )


def _layer(allow=None, deny=None, ask=None, provenance=None) -> ConfigLayer:
    prov = provenance or _prov()
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"Bash({p})" if "(" not in p else p for p in (allow or [])],
                "deny": [f"Bash({p})" if "(" not in p else p for p in (deny or [])],
                "ask": [f"Bash({p})" if "(" not in p else p for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=prov, content=content)


def _config(*layers: ConfigLayer) -> Configuration:
    return Configuration(layers=tuple(layers), start_dir=None)


def _entry(tool: str, command: str, status: str) -> LogEntry:
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool=tool,
        command=command,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class TestSignalClassification(unittest.TestCase):
    """Each corpus entry is classified by current-verdict vs observed-outcome."""

    def test_classify_signal_mappings(self):
        """
        Given each (current_verdict, observed_status) combination of interest
        When _classify is applied
        Then it maps to the documented signal: ask/deny + EXECUTED ->
             allow-candidate; any REFUSED -> declined; deny -> denied; ask ->
             asked; allow + EXECUTED -> consistent.
        """
        self.assertEqual(_classify("ask", "EXECUTED"), SIGNAL_ALLOW_CANDIDATE)
        self.assertEqual(_classify("deny", "EXECUTED"), SIGNAL_ALLOW_CANDIDATE)
        self.assertEqual(_classify("allow", "REFUSED"), SIGNAL_DECLINED)
        self.assertEqual(_classify("deny", "UNKNOWN"), SIGNAL_DENIED)
        self.assertEqual(_classify("ask", "UNKNOWN"), SIGNAL_ASKED)
        self.assertEqual(_classify("allow", "EXECUTED"), SIGNAL_CONSISTENT)

    def test_deny_then_executed_is_allow_candidate(self):
        """
        Given an ask-by-default config (TOO-15) and a corpus entry that
            EXECUTED anyway
        When mined
        Then it is an allow-candidate with current_verdict 'ask' (_classify
            treats 'ask' and 'deny' identically for the EXECUTED-anyway
            allow-candidate signal -- see test_classify_signal_mappings).
        """
        config = _config(_layer(allow=["ls:*"]))  # everything else asks
        report = mine_rule_candidates(config, [_entry("Bash", "whoami", "EXECUTED")])
        self.assertEqual(len(report.allow_candidates), 1)
        self.assertEqual(report.allow_candidates[0].current_verdict, "ask")

    def test_refused_is_declined(self):
        """
        Given a corpus entry the user REFUSED at the prompt
        When mined
        Then it is classified 'declined'.
        """
        config = _config(_layer(allow=["ls:*"]))
        report = mine_rule_candidates(
            config, [_entry("Bash", "rm -rf /tmp/x", "REFUSED")]
        )
        self.assertEqual(len(report.declined), 1)
        self.assertEqual(report.declined[0].command_key, "rm")

    def test_denied_without_execution_is_denied(self):
        """
        Given a config with no_match_fallback EXPLICITLY set to 'deny' (this
            test specifically exercises the SIGNAL_DENIED classification
            bucket, which requires an actual 'deny' verdict -- TOO-15's new
            'ask' default would instead classify as SIGNAL_ASKED, already
            covered by test_classify_signal_mappings) and a command observed
            only as UNKNOWN
        When mined
        Then it is classified 'denied' (not an allow-candidate).
        """
        content = MappingProxyType(
            {
                "no_match_fallback": "deny",
                "permissions": {
                    "allow": ["Bash(ls:*)"],
                    "deny": [],
                    "ask": [],
                },
            }
        )
        config = _config(ConfigLayer(provenance=_prov(), content=content))
        report = mine_rule_candidates(
            config, [_entry("Bash", "curl evil.test", "UNKNOWN")]
        )
        self.assertEqual(len(report.allow_candidates), 0)
        self.assertEqual(len(report.by_signal("denied")), 1)

    def test_consistent_allowed_command_is_omitted(self):
        """
        Given a config that allows 'ls' and a corpus entry where it EXECUTED
        When mined
        Then no group is produced (it is consistent, not a candidate).
        """
        config = _config(_layer(allow=["ls:*"]))
        report = mine_rule_candidates(config, [_entry("Bash", "ls -la", "EXECUTED")])
        self.assertEqual(report.groups, ())


# ---------------------------------------------------------------------------
# Grouping, sorting, filtering
# ---------------------------------------------------------------------------


class TestGroupingAndSorting(unittest.TestCase):
    """Commands cluster by key; report is sorted and can be size-filtered."""

    def test_bash_commands_group_by_executable_token(self):
        """
        Given several distinct 'git ...' commands all EXECUTED under a deny config
        When mined
        Then they form ONE group keyed 'git' listing all distinct commands.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry("Bash", "git status", "EXECUTED"),
            _entry("Bash", "git diff HEAD", "EXECUTED"),
            _entry("Bash", "git status", "EXECUTED"),
        ]
        report = mine_rule_candidates(config, corpus)
        git_groups = [g for g in report.groups if g.command_key == "git"]
        self.assertEqual(len(git_groups), 1)
        self.assertEqual(git_groups[0].occurrences, 3)
        self.assertEqual(
            git_groups[0].distinct_commands, ("git diff HEAD", "git status")
        )

    def test_file_tool_groups_by_parent_directory(self):
        """
        Given two Read entries on files in the same directory, executed under deny
        When mined
        Then they group under that parent directory as the command_key.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry("Read", "/a/b/x.py", "EXECUTED"),
            _entry("Read", "/a/b/y.py", "EXECUTED"),
        ]
        report = mine_rule_candidates(config, corpus)
        read_groups = [g for g in report.groups if g.tool == "Read"]
        self.assertEqual(len(read_groups), 1)
        self.assertEqual(read_groups[0].command_key, "/a/b")

    def test_sorted_by_occurrences_desc(self):
        """
        Given a frequent 'git' candidate and a rare 'curl' candidate
        When mined
        Then the more frequent group sorts first.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [_entry("Bash", "git status", "EXECUTED") for _ in range(3)]
        corpus.append(_entry("Bash", "curl x", "EXECUTED"))
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(report.groups[0].command_key, "git")

    def test_min_occurrences_filters_small_groups(self):
        """
        Given a single 'curl' candidate
        When mined with min_occurrences=2
        Then no group is returned.
        """
        config = _config(_layer(allow=["ls:*"]))
        report = mine_rule_candidates(
            config, [_entry("Bash", "curl x", "EXECUTED")], min_occurrences=2
        )
        self.assertEqual(report.groups, ())


# ---------------------------------------------------------------------------
# Candidate verification
# ---------------------------------------------------------------------------


class TestEvaluateAddedAllowRule(unittest.TestCase):
    """A proposed allow rule is measured by decision-replay."""

    def test_newly_allowed_commands_reported(self):
        """
        Given a deny-by-default config and a corpus of 'git push' commands
        When evaluate_added_allow_rule adds 'git push:*' at the project layer
        Then the replay reports those commands as newly allowed and 0 tightened.
        """
        prov = _prov()
        config = _config(_layer(allow=["ls:*"], provenance=prov))
        corpus = [
            _entry("Bash", "git push origin main", "EXECUTED"),
            _entry("Bash", "git push", "EXECUTED"),
            _entry("Bash", "ls -la", "EXECUTED"),  # already allowed -> unchanged
        ]
        effect = evaluate_added_allow_rule(config, "Bash", "git push:*", prov, corpus)
        self.assertEqual(effect.tightened_count, 0)
        self.assertIn("git push origin main", effect.newly_allowed)
        self.assertIn("git push", effect.newly_allowed)
        self.assertNotIn("ls -la", effect.newly_allowed)
        self.assertEqual(effect.broadened_count, 2)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderMiningReport(unittest.TestCase):
    """render_mining_report produces an ASCII summary and validates its format."""

    def test_text_report_contains_signal_counts_and_group(self):
        """
        Given a report with one allow-candidate
        When rendered as text
        Then the output shows the signal tally and the command key.
        """
        config = _config(_layer(allow=["ls:*"]))
        report = mine_rule_candidates(config, [_entry("Bash", "whoami", "EXECUTED")])
        out = render_mining_report(report, fmt="text")
        self.assertIn("allow-candidate: 1", out)
        self.assertIn("whoami", out)

    def test_invalid_format_raises_value_error(self):
        """
        Given any report
        When rendered with an unknown format
        Then ValueError is raised.
        """
        report = mine_rule_candidates(_config(_layer(allow=["ls:*"])), [])
        with self.assertRaises(ValueError):
            render_mining_report(report, fmt="html")


if __name__ == "__main__":
    unittest.main()
