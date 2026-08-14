"""Unit tests for toolguard.tools.replay."""

import contextlib
import io
import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.api import decide
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.config_types import RuntimeVerdict
from toolguard.tools import replay as replay_module
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.replay import classify_change, replay, replay_single


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

    def test_broadened_deny_to_allow(self):
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

    def test_tightened_ask_to_deny(self):
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


_SIMPLE_ALLOW = _make_config(
    [
        (
            "project",
            "toolguard_hook",
            {"permissions": {"allow": ["Bash(git:*)"], "deny": []}},
        )
    ]
)


class TestReplayOverAnEmptyCorpus(unittest.TestCase):
    """What a replay reports when it evaluated nothing at all."""

    def test_a_replay_that_evaluated_nothing_reports_zero_entries(self):
        """
        Given an empty corpus
        When replay is called
        Then every bucket is empty and total_count is 0 -- the run is reported
            as having covered nothing, not as a clean run
        """
        diff = replay([], config_a=_SIMPLE_ALLOW, config_b=_SIMPLE_ALLOW)

        self.assertEqual(0, diff.total_count)
        self.assertEqual([], diff.diffs)
        self.assertEqual([], diff.broadened())
        self.assertEqual([], diff.tightened())
        self.assertEqual([], diff.unchanged())
        self.assertEqual(0, diff.broadened_count)
        self.assertEqual(0, diff.tightened_count)
        self.assertEqual(0, diff.unchanged_count)

    def test_only_the_entry_count_separates_nothing_replayed_from_nothing_changed(self):
        """
        Given an empty corpus and a corpus whose decisions all stay the same
        When both are replayed against the same pair of configs
        Then the two runs agree on every 'did anything change' signal, and
            total_count is the only field that tells them apart -- so a caller
            reading broadened_count alone cannot tell that nothing was evaluated
        """
        config_a = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
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
                            "allow": ["Bash(git:*)"],
                            "deny": ["Bash(curl:*)"],
                        }
                    },
                )
            ]
        )
        corpus = [_make_bash_entry("git status"), _make_bash_entry("git log")]

        empty = replay([], config_a=config_a, config_b=config_b)
        populated = replay(corpus, config_a=config_a, config_b=config_b)

        for name in ("broadened_count", "tightened_count"):
            self.assertEqual(getattr(empty, name), getattr(populated, name))
        self.assertEqual(empty.broadened(), populated.broadened())
        self.assertEqual(empty.tightened(), populated.tightened())

        self.assertEqual(0, empty.total_count)
        self.assertEqual(len(corpus), populated.total_count)


class TestReplayCoversTheWholeCorpus(unittest.TestCase):
    """Every entry handed in is evaluated, and the counts say so."""

    def test_every_entry_is_replayed_including_ones_that_do_not_parse(self):
        """
        Given a corpus mixing ordinary commands with a multiline heredoc, an
            empty command, and a command the bash grammar cannot parse
        When replay is called
        Then one diff is produced per corpus entry, in corpus order, each
            carrying the very LogEntry object it was built from -- nothing is
            silently dropped for being unparseable
        """
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("python <<'PY'\nprint(1)\nPY"),
            _make_bash_entry(""),
            _make_bash_entry("git status |"),
            _make_file_entry("Read", "/tmp/tg-replay-test/a.py"),
        ]

        # The grammar reports its parse failures through the error reporter,
        # which falls back to stderr when no Reporter is installed.
        with contextlib.redirect_stderr(io.StringIO()):
            diff = replay(corpus, config_a=_SIMPLE_ALLOW, config_b=_SIMPLE_ALLOW)

        self.assertEqual(len(corpus), diff.total_count)
        self.assertEqual(len(corpus), len(diff.diffs))
        for expected_entry, actual in zip(corpus, diff.diffs):
            self.assertIs(expected_entry, actual.entry)
            self.assertIn(actual.decision_a.decision, ("allow", "ask", "deny"))

    def test_the_summary_counts_account_for_exactly_the_entries_replayed(self):
        """
        Given a corpus with repeated commands that broaden, tighten and stay put
        When replay is called
        Then each summary count equals the length of its own bucket, and the
            three sum to total_count -- the counts cannot drift from what the
            loop actually classified
        """
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
            _make_bash_entry("git status"),
            _make_bash_entry("ls -la"),
            _make_bash_entry("curl http://x.com"),
            _make_bash_entry("curl http://y.com"),
        ]
        diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(len(corpus), diff.total_count)
        self.assertEqual(len(diff.unchanged()), diff.unchanged_count)
        self.assertEqual(len(diff.tightened()), diff.tightened_count)
        self.assertEqual(len(diff.broadened()), diff.broadened_count)
        self.assertEqual(
            diff.total_count,
            diff.unchanged_count + diff.tightened_count + diff.broadened_count,
        )
        self.assertEqual(2, diff.unchanged_count)
        self.assertEqual(1, diff.tightened_count)
        self.assertEqual(2, diff.broadened_count)

    def test_the_total_counts_recorded_entries_not_the_summary_counters(self):
        """
        Given a ReplayDiff holding one entry but counters claiming ninety-nine
        When total_count is read
        Then it reports 1 -- the total comes from the entries actually recorded,
            so an inflated counter cannot inflate the reported coverage
        """
        one = replay(
            [_make_bash_entry("git status")],
            config_a=_SIMPLE_ALLOW,
            config_b=_SIMPLE_ALLOW,
        ).diffs[0]
        inflated = replay_module.ReplayDiff(
            diffs=[one], unchanged_count=99, tightened_count=99, broadened_count=99
        )

        self.assertEqual(1, inflated.total_count)


class TestReplayUsesTheDecisionEngine(unittest.TestCase):
    """The replayed verdicts come from toolguard.api.decide, not a re-derivation."""

    def _spy(self, decision_for_config):
        """Return a (spy, calls, returned) triple standing in for the decision engine."""
        calls = []
        returned = []

        def spy(config, tool, target, extended_syntax=True):
            calls.append((config, tool, target, extended_syntax))
            verdict = RuntimeVerdict(
                decision=decision_for_config(config),
                reason="stub verdict",
                matched_rule="stub rule",
                tool=tool,
                target=target,
            )
            returned.append(verdict)
            return verdict

        return spy, calls, returned

    def test_each_diff_carries_the_verdict_object_the_engine_returned(self):
        """
        Given a decision engine replaced by a stub returning identifiable verdicts
        When replay is called
        Then each EntryDiff holds the exact objects the stub returned for that
            entry under config A and config B, and the classification follows
            from those verdicts
        """
        config_a = _SIMPLE_ALLOW
        config_b = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": [], "deny": ["Bash(git:*)"]}},
                )
            ]
        )
        corpus = [_make_bash_entry("git status"), _make_file_entry("Read", "/tmp/a.py")]
        spy, calls, returned = self._spy(
            lambda cfg: "allow" if cfg is config_a else "deny"
        )

        with patch.object(replay_module, "decide", spy):
            diff = replay(corpus, config_a=config_a, config_b=config_b)

        self.assertEqual(2 * len(corpus), len(calls))
        self.assertEqual(2 * len(corpus), len(returned))
        self.assertIs(returned[0], diff.diffs[0].decision_a)
        self.assertIs(returned[1], diff.diffs[0].decision_b)
        self.assertIs(returned[2], diff.diffs[1].decision_a)
        self.assertIs(returned[3], diff.diffs[1].decision_b)
        self.assertEqual(
            ["tightened", "tightened"], [d.classification for d in diff.diffs]
        )

    def test_the_engine_is_asked_about_each_entry_under_both_configs(self):
        """
        Given a stubbed decision engine and extended_syntax turned off
        When replay is called
        Then the engine is called once per entry per config, with that entry's
            own tool and command and the caller's extended_syntax value
        """
        config_a = _SIMPLE_ALLOW
        config_b = _make_config(
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
        corpus = [
            _make_bash_entry("git status"),
            _make_file_entry("Write", "/tmp/a.py"),
        ]
        spy, calls, _returned = self._spy(lambda cfg: "allow")

        with patch.object(replay_module, "decide", spy):
            replay(corpus, config_a=config_a, config_b=config_b, extended_syntax=False)

        expected = [
            (config_a, corpus[0]),
            (config_b, corpus[0]),
            (config_a, corpus[1]),
            (config_b, corpus[1]),
        ]
        self.assertEqual(len(expected), len(calls))
        for (want_config, want_entry), (got_config, tool, target, ext) in zip(
            expected, calls
        ):
            self.assertIs(want_config, got_config)
            self.assertEqual(want_entry.tool, tool)
            self.assertEqual(want_entry.command, target)
            self.assertFalse(ext)

    def test_a_replayed_verdict_carries_the_engine_attribution(self):
        """
        Given a config whose allow rule decides the corpus command
        When replay is called against the real decision engine
        Then the verdict is the one a direct decide() call produces, carrying
            the deciding rule, its provenance, and the tool/target evaluated --
            not a bare decision string re-derived by the replay itself
        """
        corpus = [_make_bash_entry("git status")]
        diff = replay(corpus, config_a=_SIMPLE_ALLOW, config_b=_SIMPLE_ALLOW)
        verdict = diff.diffs[0].decision_a

        self.assertEqual(decide(_SIMPLE_ALLOW, "Bash", "git status", True), verdict)
        self.assertEqual("git:*", verdict.matched_rule)
        self.assertIsNotNone(verdict.provenance)
        self.assertEqual("Bash", verdict.tool)
        self.assertEqual("git status", verdict.target)

    def test_entries_are_routed_by_their_own_tool(self):
        """
        Given a config that allows a path under a Read rule only
        When a Read entry and a Bash entry for the same target text are replayed
        Then the Read entry is allowed by the file-path rule and the Bash entry
            is not, and each verdict names the tool it was evaluated as
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/tg-replay-test/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        target = "/tmp/tg-replay-test/a.py"
        corpus = [
            _make_file_entry("Read", target),
            _make_bash_entry(target),
        ]
        diff = replay(corpus, config_a=config, config_b=config)

        self.assertEqual("allow", diff.diffs[0].decision_a.decision)
        self.assertEqual("Read", diff.diffs[0].decision_a.tool)
        self.assertNotEqual("allow", diff.diffs[1].decision_a.decision)
        self.assertEqual("Bash", diff.diffs[1].decision_a.tool)

    def test_extended_syntax_is_honoured_only_when_asked_for(self):
        """
        Given a config whose only allow rule uses the [regex] prefix
        When the same corpus is replayed with extended_syntax on and then off
        Then the command is allowed with it on and unmatched with it off
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Bash([regex]^git .*$)"], "deny": []}},
                )
            ]
        )
        corpus = [_make_bash_entry("git status")]

        on = replay(corpus, config_a=config, config_b=config, extended_syntax=True)
        off = replay(corpus, config_a=config, config_b=config, extended_syntax=False)

        self.assertEqual("allow", on.diffs[0].decision_a.decision)
        self.assertNotEqual("allow", off.diffs[0].decision_a.decision)
        self.assertNotEqual("allow", off.diffs[0].decision_b.decision)


class TestReplaySingleCorrespondence(unittest.TestCase):
    """replay_single's results line up with the corpus it was given."""

    def test_results_correspond_to_the_corpus_entries_in_order(self):
        """
        Given a corpus of three distinct commands
        When replay_single is called
        Then result i carries corpus entry i itself, and its verdict names that
            entry's own command as the target
        """
        corpus = [
            _make_bash_entry("git status"),
            _make_bash_entry("whoami", status="REFUSED"),
            _make_file_entry("Read", "/tmp/tg-replay-test/b.py"),
        ]
        results = replay_single(corpus, _SIMPLE_ALLOW)

        self.assertEqual(len(corpus), len(results))
        for entry, result in zip(corpus, results):
            self.assertIs(entry, result.entry)
            self.assertEqual(entry.command, result.decision.target)

    def test_extended_syntax_is_honoured_only_when_asked_for(self):
        """
        Given a config whose only allow rule uses the [regex] prefix
        When the same entry is replayed with extended_syntax on and then off
        Then the command is allowed with it on and unmatched with it off
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {"permissions": {"allow": ["Bash([regex]^git .*$)"], "deny": []}},
                )
            ]
        )
        corpus = [_make_bash_entry("git status")]

        on = replay_single(corpus, config, extended_syntax=True)
        off = replay_single(corpus, config, extended_syntax=False)

        self.assertEqual("allow", on[0].decision.decision)
        self.assertNotEqual("allow", off[0].decision.decision)


class TestVerdictCorroboration(unittest.TestCase):
    """What replay_single's matches_observed does and does not claim."""

    def _matches(self, command, status):
        """Replay one entry against a git-only allow config and report corroboration."""
        entry = _make_bash_entry(command, status=status)
        result = replay_single([entry], _SIMPLE_ALLOW)[0]
        return result.decision.decision, result.matches_observed

    def test_an_allow_verdict_does_not_corroborate_a_refused_log_line(self):
        """
        Given a command the log records as REFUSED that the config now allows
        When replay_single is called
        Then the verdict is 'allow' and matches_observed is False
        """
        self.assertEqual(("allow", False), self._matches("git status", "REFUSED"))

    def test_an_ask_verdict_does_not_corroborate_an_executed_log_line(self):
        """
        Given a command the log records as EXECUTED that the config no longer allows
        When replay_single is called
        Then the verdict is 'ask' and matches_observed is False
        """
        self.assertEqual(("ask", False), self._matches("whoami", "EXECUTED"))

    def test_an_unrecognised_status_is_not_corroborated(self):
        """
        Given log entries whose status is ERROR, UNKNOWN, or absent
        When replay_single is called
        Then matches_observed is False for each, whatever the verdict is
        """
        for status in ("ERROR", "UNKNOWN", ""):
            with self.subTest(status=status):
                self.assertEqual(("allow", False), self._matches("git status", status))

    def test_status_matching_ignores_case(self):
        """
        Given a log status written in lower case
        When replay_single is called with a config that allows the command
        Then it corroborates exactly as the upper-case form does
        """
        self.assertEqual(("allow", True), self._matches("git status", "executed"))
        self.assertEqual(("ask", True), self._matches("whoami", "refused"))

    def test_an_ask_verdict_corroborates_an_ask_log_line(self):
        """
        Given a command the log records as ASK -- the status toolguard's own hook
            writes for an ask decision -- and a config that still decides 'ask'
        When replay_single is called
        Then matches_observed is True: the replay agrees with the log exactly
        """
        self.assertEqual(("ask", True), self._matches("whoami", "ASK"))


class TestClassifyChangeIsAntisymmetric(unittest.TestCase):
    """Swapping the two configs must invert every classification."""

    def test_swapping_the_configs_inverts_each_classification(self):
        """
        Given every ordered pair of the three real verdicts
        When classify_change is called both ways round
        Then 'tightened' one way is 'broadened' the other, and 'unchanged' stays
        """
        inverse = {
            "unchanged": "unchanged",
            "tightened": "broadened",
            "broadened": "tightened",
        }
        for a in ("allow", "ask", "deny"):
            for b in ("allow", "ask", "deny"):
                with self.subTest(a=a, b=b):
                    forward = classify_change(a, b)
                    self.assertEqual(inverse[forward], classify_change(b, a))
                    self.assertEqual(a == b, forward == "unchanged")
