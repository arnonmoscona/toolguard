"""Unit tests for toolguard.tools.replay."""

import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.tools.log_harvest import LogEntry


def _make_config(layers_content):
    """Build a Configuration from (level, source_type, content_dict) triples, in order."""
    layers = []
    for i, (level, source_type, content) in enumerate(layers_content):
        prov = Provenance(
            level=level,
            source_type=source_type,
            file_format="toml",
            path=Path(f"/fake/{level}/{source_type}_{i}"),
            specificity=i,
        )
        layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(layers), start_dir=None)


def _make_bash_entry(command: str, status: str = "EXECUTED") -> LogEntry:
    """Build a minimal synthetic Bash LogEntry for replay testing."""
    return LogEntry(
        timestamp=datetime(2026, 6, 20, 10, 0, 0),
        tool="Bash",
        command=command,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


def _make_file_entry(tool: str, path: str, status: str = "EXECUTED") -> LogEntry:
    """Build a minimal synthetic file-tool LogEntry for replay testing."""
    return LogEntry(
        timestamp=datetime(2026, 6, 20, 10, 0, 0),
        tool=tool,
        command=path,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


class TestClassifyChange(unittest.TestCase):
    """Tests for replay.classify_change()."""

    def test_unchanged_same_verdict(self):
        """
        Given verdict_a == verdict_b (both 'allow')
        When classify_change is called
        Then the result is 'unchanged'
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("unchanged", classify_change("allow", "allow"))
        self.assertEqual("unchanged", classify_change("deny", "deny"))
        self.assertEqual("unchanged", classify_change("ask", "ask"))

    def test_broadened_allow_to_deny_is_wrong_direction(self):
        """
        Given verdict_a='deny' and verdict_b='allow' (B is looser)
        When classify_change is called
        Then the result is 'broadened' (allow < ask < deny in strictness)
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("broadened", classify_change("deny", "allow"))

    def test_tightened_allow_to_deny(self):
        """
        Given verdict_a='allow' and verdict_b='deny' (B is stricter)
        When classify_change is called
        Then the result is 'tightened'
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("tightened", classify_change("allow", "deny"))

    def test_broadened_ask_to_allow(self):
        """
        Given verdict_a='ask' and verdict_b='allow' (B is looser)
        When classify_change is called
        Then the result is 'broadened' (allowing without asking is broader)
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("broadened", classify_change("ask", "allow"))

    def test_tightened_allow_to_ask(self):
        """
        Given verdict_a='allow' and verdict_b='ask' (B is stricter, now requires approval)
        When classify_change is called
        Then the result is 'tightened'
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("tightened", classify_change("allow", "ask"))

    def test_tightened_deny_to_ask(self):
        """
        Given verdict_a='ask' and verdict_b='deny' (B is stricter)
        When classify_change is called
        Then the result is 'tightened'
        """
        from toolguard.tools.replay import classify_change

        self.assertEqual("tightened", classify_change("ask", "deny"))


class TestReplayUnchanged(unittest.TestCase):
    """Tests that identical configs yield all-unchanged diff."""

    def test_identical_configs_produce_all_unchanged(self):
        """
        Given two identical configurations (config A == config B)
        When replay is called with a corpus of Bash commands
        Then all entries are classified as 'unchanged' and broadened_count == 0
        """
        from toolguard.tools.replay import replay

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": ["Bash(rm -rf:*)"],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("git log"),
            _make_bash_entry("ls -la"),
            _make_bash_entry("whoami"),
        ]
        diff = replay(corpus, config_a=config, config_b=config)

        self.assertEqual(len(corpus), diff.total_count)
        self.assertEqual(0, diff.broadened_count)
        self.assertEqual(0, diff.tightened_count)
        self.assertEqual(len(corpus), diff.unchanged_count)

    def test_identical_file_tool_configs_produce_unchanged(self):
        """
        Given two identical configurations for Read tool
        When replay is called with a corpus of Read file entries
        Then all entries are classified as 'unchanged'
        """
        from toolguard.tools.replay import replay

        home = str(Path.home())
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [f"Read([glob]{home}/projects/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_file_entry("Read", f"{home}/projects/foo/bar.py"),
            _make_file_entry("Read", "/etc/passwd"),
        ]
        diff = replay(corpus, config_a=config, config_b=config)

        self.assertEqual(2, diff.total_count)
        self.assertEqual(0, diff.broadened_count)
        self.assertEqual(0, diff.tightened_count)


class TestReplayTightening(unittest.TestCase):
    """Tests that narrowing permissions is detected as tightened."""

    def test_removing_allow_rule_tightens_decisions(self):
        """
        Given config A that allows 'ls:*' and config B that does NOT allow it
            (no explicit no_match_fallback set -- TOO-15 default is 'ask')
        When replay is called with a corpus containing 'ls -la'
        Then the 'ls -la' entry is classified as 'tightened' (A=allow, B=ask
            -- 'allow -> ask' is still stricter, per replay's documented
            allow > ask > deny ordering)
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("ls -la"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        tightened = diff.tightened()
        self.assertEqual(1, len(tightened))
        self.assertEqual("ls -la", tightened[0].entry.command)
        self.assertEqual("allow", tightened[0].decision_a.decision)
        self.assertEqual("ask", tightened[0].decision_b.decision)
        self.assertEqual("tightened", tightened[0].classification)

    def test_adding_deny_rule_tightens_decisions(self):
        """
        Given config A with no deny rules and config B that adds 'git push:*' to deny
        When replay is called with 'git push origin main' in the corpus
        Then that entry is classified as 'tightened'
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": ["Bash(git push:*)"],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("git push origin main"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        tightened = diff.tightened()
        self.assertEqual(1, len(tightened))
        self.assertEqual("git push origin main", tightened[0].entry.command)

        unchanged = diff.unchanged()
        self.assertEqual(1, len(unchanged))
        self.assertEqual("git status", unchanged[0].entry.command)


class TestReplayBroadening(unittest.TestCase):
    """Tests that broadening permissions is detected."""

    def test_adding_allow_rule_broadens_decisions(self):
        """
        Given config A that does NOT allow 'whoami' and config B that adds 'whoami' to allow
            (both EXPLICITLY set no_match_fallback='deny' -- this is the
            CRITICAL safety check class, so the fixture preserves a strict
            fail-closed posture regardless of TOO-15's new 'ask' default, to
            keep demonstrating the deny->allow broadening it names)
        When replay is called with 'whoami' in the corpus
        Then that entry is classified as 'broadened' (A=deny, B=allow)
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
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
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(whoami)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("whoami"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(1, diff.broadened_count)
        broadened = diff.broadened()
        self.assertEqual(1, len(broadened))
        self.assertEqual("whoami", broadened[0].entry.command)
        self.assertEqual("deny", broadened[0].decision_a.decision)
        self.assertEqual("allow", broadened[0].decision_b.decision)

    def test_alembic_landmine_broadening_detected(self):
        """
        Given config A where 'uv run alembic <sub>:*' specific commands are in allow
        and 'uv run alembic:*' is in ask (the alembic landmine pattern), with
        no_match_fallback EXPLICITLY set to 'deny' in both configs (this is the
        CRITICAL safety check class, so the fixture preserves a strict
        fail-closed posture regardless of TOO-15's new 'ask' default -- the
        landmine narrative below specifically requires config A to DENY the
        unmatched dangerous command, not merely ask about it)
        And config B that 'consolidates' all alembic allows into 'uv run alembic:*' allow
        When replay is called with alembic commands in the corpus
        Then the previously-ask entries are classified as 'broadened' (ask -> allow)
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {
                            "allow": [
                                "Bash(uv run alembic upgrade head:*)",
                                "Bash(uv run alembic current:*)",
                                "Bash(uv run alembic history:*)",
                            ],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "no_match_fallback": "deny",
                        "permissions": {
                            "allow": [
                                "Bash(uv run alembic:*)",
                            ],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("uv run alembic upgrade head"),
            _make_bash_entry("uv run alembic current"),
            _make_bash_entry("uv run alembic downgrade -1", status="REFUSED"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        upgrade_diffs = [d for d in diff.diffs if "upgrade" in d.entry.command]
        self.assertEqual(1, len(upgrade_diffs))
        self.assertEqual("allow", upgrade_diffs[0].decision_a.decision)
        self.assertEqual("allow", upgrade_diffs[0].decision_b.decision)
        self.assertEqual("unchanged", upgrade_diffs[0].classification)

        downgrade_diffs = [d for d in diff.diffs if "downgrade" in d.entry.command]
        self.assertEqual(1, len(downgrade_diffs))
        self.assertEqual("deny", downgrade_diffs[0].decision_a.decision)
        self.assertEqual("allow", downgrade_diffs[0].decision_b.decision)
        self.assertEqual("broadened", downgrade_diffs[0].classification)

        self.assertGreater(diff.broadened_count, 0)

    def test_removing_deny_rule_broadens_decisions(self):
        """
        Given config A that denies 'curl:*' and config B that removes that deny rule
        When replay is called with 'curl http://example.com' in corpus (which A denies)
        Then that entry is classified as 'broadened' because B allows it via a broad rule
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(curl *)"],
                            "deny": ["Bash(curl:*)"],
                        }
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(curl *)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("curl http://example.com", status="REFUSED"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(1, diff.broadened_count)
        broadened = diff.broadened()
        self.assertEqual("deny", broadened[0].decision_a.decision)
        self.assertEqual("allow", broadened[0].decision_b.decision)


class TestReplaySummaryAndHelpers(unittest.TestCase):
    """Tests for ReplayDiff summary counts and helper methods."""

    def test_replay_diff_summary_counts_are_correct(self):
        """
        Given a corpus with 3 entries and a config change that broadens 1,
        tightens 1, and leaves 1 unchanged
        When replay is called
        Then ReplayDiff.broadened_count == 1, tightened_count == 1, unchanged_count == 1
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": ["Bash(curl:*)"],
                        }
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                "Bash(git:*)",
                                "Bash(curl:*)",
                            ],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("ls -la"),
            _make_bash_entry("curl http://x.com"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(3, diff.total_count)
        self.assertEqual(1, diff.unchanged_count)
        self.assertEqual(1, diff.tightened_count)
        self.assertEqual(1, diff.broadened_count)

    def test_replay_diff_helper_methods_return_correct_subsets(self):
        """
        Given a ReplayDiff with known counts
        When broadened(), tightened(), and unchanged() methods are called
        Then each returns the correct subset of EntryDiff records
        """
        from toolguard.tools.replay import replay

        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": ["Bash(curl:*)"],
                        }
                    },
                )
            ]
        )
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(curl:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("ls -la"),
            _make_bash_entry("curl http://x.com"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(1, len(diff.broadened()))
        self.assertEqual(1, len(diff.tightened()))
        self.assertEqual(1, len(diff.unchanged()))
        self.assertEqual("curl http://x.com", diff.broadened()[0].entry.command)
        self.assertEqual("ls -la", diff.tightened()[0].entry.command)
        self.assertEqual("git status", diff.unchanged()[0].entry.command)


class TestReplaySingleConfig(unittest.TestCase):
    """Tests for replay.replay_single()."""

    def test_replay_single_returns_decisions_for_all_entries(self):
        """
        Given a corpus of 3 commands and a single config
        When replay_single is called
        Then a list of 3 SingleDecision records is returned
        """
        from toolguard.tools.replay import replay_single

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("git log"),
            _make_bash_entry("whoami", status="REFUSED"),
        ]
        results = replay_single(corpus, config)

        self.assertEqual(3, len(results))

    def test_replay_single_matches_observed_correctly(self):
        """
        Given a corpus where 'git status' was EXECUTED and 'whoami' was REFUSED
        When replay_single is called with a config that matches that behavior
        Then matches_observed is True for entries consistent with the log
        """
        from toolguard.tools.replay import replay_single

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        corpus = [
            _make_bash_entry("git status", status="EXECUTED"),
            _make_bash_entry("whoami", status="REFUSED"),
        ]
        results = replay_single(corpus, config)

        self.assertTrue(results[0].matches_observed)
        self.assertTrue(results[1].matches_observed)

    def test_replay_single_empty_corpus_returns_empty_list(self):
        """
        Given an empty corpus
        When replay_single is called
        Then an empty list is returned
        """
        from toolguard.tools.replay import replay_single

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        results = replay_single([], config)
        self.assertEqual([], results)
