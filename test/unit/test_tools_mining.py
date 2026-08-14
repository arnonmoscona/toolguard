"""
Unit tests for toolguard.tools.mining -- classifying a corpus into rule
candidates and measuring a proposed allow rule by decision-replay.

Mining does no file I/O: it takes an already-harvested ``List[LogEntry]`` and a
hand-built :class:`Configuration`, so no config-isolation mixin is needed (see
``.claude/rules/test-config-isolation.md``).  ``TestNoAmbientStateDependence``
holds that claim.
"""

import dataclasses
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.config_access import with_layer_allow_replaced
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.mining import (
    SIGNAL_ALLOW_CANDIDATE,
    SIGNAL_ASKED,
    SIGNAL_CONSISTENT,
    SIGNAL_DECLINED,
    SIGNAL_DENIED,
    AddRuleEffect,
    _classify,
    _command_key,
    evaluate_added_allow_rule,
    mine_rule_candidates,
    render_mining_report,
)

# Vocabulary shared with the production module and the log format.
TOOL_BASH = "Bash"
TOOL_READ = "Read"
TOOL_WRITE = "Write"
TOOL_MCP = "mcp__example__run"

STATUS_EXECUTED = "EXECUTED"
STATUS_REFUSED = "REFUSED"
STATUS_ASK = "ASK"
STATUS_ERROR = "ERROR"
STATUS_UNKNOWN = "UNKNOWN"

VERDICT_ALLOW = "allow"
VERDICT_ASK = "ask"
VERDICT_DENY = "deny"

FMT_TEXT = "text"
FMT_MARKDOWN = "markdown"

#: A command the suite must never see admitted by a mined proposal.
DANGEROUS_WITNESS = "rm -rf /"


def evidence(effect: AddRuleEffect):
    """
    An AddRuleEffect with the echoed pattern blanked -- everything the result
    says about what was measured, and nothing it merely repeats back.

    Two proposals whose evidence compares equal are indistinguishable to anyone
    reading the measurement; adding a field to AddRuleEffect separates them.
    """
    return dataclasses.replace(effect, pattern="")


_BASE_TIME = datetime(2026, 6, 25, 10, 0, 0)


def _prov(path: str = "/fake/.claude/toolguard_hook.toml") -> Provenance:
    """Build a project-level toolguard_hook provenance rooted at a fake path."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(path),
        specificity=0,
    )


def _layer(
    allow=None, deny=None, ask=None, provenance=None, no_match_fallback=None
) -> ConfigLayer:
    """
    Build one config layer from bare (tool-wrapper-free) Bash pattern bodies.

    Every pattern is wrapped as ``Bash(...)``; pass bodies only, never an
    already-wrapped rule.
    """

    def wrap(patterns):
        return [f"Bash({p})" for p in (patterns or [])]

    content = {
        "permissions": {
            "allow": wrap(allow),
            "deny": wrap(deny),
            "ask": wrap(ask),
        }
    }
    if no_match_fallback is not None:
        content["no_match_fallback"] = no_match_fallback
    return ConfigLayer(
        provenance=provenance or _prov(), content=MappingProxyType(content)
    )


def _config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers with no start directory."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _entry(
    tool: str,
    command: str,
    status: str,
    *,
    minute: int = 0,
    rule_text: str = "Matched Rule: Bash(ls:*)",
    agent: str = "researcher",
    log_file: str = "/fake/logs/toolguard-2026-06-25.md",
) -> LogEntry:
    """
    Build one corpus entry.

    Every field carries a distinct non-default value so a mutant that hardcodes
    or drops one is visible; ``minute`` offsets the timestamp so entries are
    individually identifiable.
    """
    return LogEntry(
        timestamp=_BASE_TIME + timedelta(minutes=minute),
        tool=tool,
        command=command,
        status=status,
        rule_text=rule_text,
        agent=agent,
        log_file=Path(log_file),
    )


class TestClassifySignal(unittest.TestCase):
    """_classify maps a (current verdict, observed status) pair to one signal."""

    def test_the_whole_verdict_by_status_matrix_maps_to_the_documented_signals(self):
        """
        Given every combination of the three verdicts with five observed statuses
        When _classify is applied to each in a fixed order
        Then the resulting signals equal the documented mapping exactly, so any
             two branches swapped or merged changes the tuple.
        """
        verdicts = (VERDICT_ALLOW, VERDICT_ASK, VERDICT_DENY)
        statuses = (
            STATUS_EXECUTED,
            STATUS_REFUSED,
            STATUS_ASK,
            STATUS_ERROR,
            STATUS_UNKNOWN,
        )
        actual = tuple(
            _classify(verdict, status) for verdict in verdicts for status in statuses
        )
        expected = (
            # allow
            SIGNAL_CONSISTENT,
            SIGNAL_DECLINED,
            SIGNAL_CONSISTENT,
            SIGNAL_CONSISTENT,
            SIGNAL_CONSISTENT,
            # ask
            SIGNAL_ALLOW_CANDIDATE,
            SIGNAL_DECLINED,
            SIGNAL_ASKED,
            SIGNAL_ASKED,
            SIGNAL_ASKED,
            # deny
            SIGNAL_ALLOW_CANDIDATE,
            SIGNAL_DECLINED,
            SIGNAL_DENIED,
            SIGNAL_DENIED,
            SIGNAL_DENIED,
        )
        self.assertEqual(actual, expected)

    def test_the_four_reported_signals_are_four_distinct_strings(self):
        """
        Given the four signals that reach a CommandGroup plus the dropped one
        When their string values are collected
        Then all five are distinct, so no two signals can be conflated by a
             constant sharing another's value.
        """
        signals = (
            SIGNAL_ALLOW_CANDIDATE,
            SIGNAL_DECLINED,
            SIGNAL_DENIED,
            SIGNAL_ASKED,
            SIGNAL_CONSISTENT,
        )
        self.assertEqual(len(set(signals)), 5)

    def test_an_unrecognised_verdict_never_becomes_an_allow_candidate(self):
        """
        Given a verdict string outside allow/ask/deny paired with EXECUTED
        When classified
        Then it is not an allow-candidate -- an unreadable verdict must not
             turn into advice to widen the config.
        """
        self.assertNotEqual(
            _classify("banana", STATUS_EXECUTED), SIGNAL_ALLOW_CANDIDATE
        )


class TestCommandKey(unittest.TestCase):
    """_command_key computes the coarse grouping key for one corpus entry."""

    def test_a_command_tool_keys_on_the_leading_token(self):
        """
        Given command strings differing in leading whitespace, internal spacing,
            an absolute program path and a trailing pipeline
        When keyed as a command tool
        Then each key is the leading token exactly, as an ordered tuple.
        """
        commands = (
            "git status",
            "  git   status  ",
            "/usr/bin/git status",
            "git status | wc -l",
            "curl https://example.test",
        )
        actual = tuple(_command_key(TOOL_BASH, c) for c in commands)
        self.assertEqual(actual, ("git", "git", "/usr/bin/git", "git", "curl"))

    def test_an_mcp_terminal_tool_keys_like_a_command_tool(self):
        """
        Given an MCP terminal tool name and a two-token command
        When keyed
        Then the key is the leading token, not the tool name and not the path.
        """
        self.assertEqual(_command_key(TOOL_MCP, "deploy --now"), "deploy")

    def test_a_file_tool_keys_on_the_parent_directory(self):
        """
        Given absolute, root-level and relative file paths
        When keyed as file tools
        Then each key is the parent directory, except that a path with no usable
             parent keys on the path itself.
        """
        actual = (
            _command_key(TOOL_READ, "/a/b/x.py"),
            _command_key(TOOL_WRITE, "/a/b/y.py"),
            _command_key(TOOL_READ, "/x.py"),
            _command_key(TOOL_READ, "x.py"),
            _command_key(TOOL_WRITE, "relative/y.py"),
        )
        self.assertEqual(actual, ("/a/b", "/a/b", "/", "x.py", "relative"))

    def test_an_empty_or_whitespace_command_keys_on_the_empty_string(self):
        """
        Given an empty command string and a whitespace-only one
        When keyed as a command tool
        Then both key on the empty string rather than raising.
        """
        self.assertEqual(
            (_command_key(TOOL_BASH, ""), _command_key(TOOL_BASH, "   \t ")), ("", "")
        )


class TestGrouping(unittest.TestCase):
    """Entries cluster by (tool, command key, signal) and are summarised."""

    def setUp(self):
        self.config = _config(_layer(allow=["ls:*"]))

    def test_command_entries_sharing_a_leading_token_form_one_group(self):
        """
        Given three git entries -- two of them the same command -- all EXECUTED
            under an ask-by-default config
        When mined
        Then one group keyed 'git' reports three occurrences, the two distinct
             commands sorted, and the status tally.
        """
        corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "git diff HEAD", STATUS_EXECUTED, minute=1),
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=2),
        ]
        report = mine_rule_candidates(self.config, corpus)
        self.assertEqual(len(report.groups), 1)
        group = report.groups[0]
        self.assertEqual(
            (
                group.tool,
                group.command_key,
                group.signal,
                group.distinct_commands,
                group.occurrences,
                group.current_verdict,
                group.observed_counts,
            ),
            (
                TOOL_BASH,
                "git",
                SIGNAL_ALLOW_CANDIDATE,
                ("git diff HEAD", "git status"),
                3,
                VERDICT_ASK,
                {STATUS_EXECUTED: 3},
            ),
        )

    def test_file_tool_entries_in_one_directory_form_one_group(self):
        """
        Given two Read entries on files in the same directory and one in another
        When mined
        Then two groups appear, each keyed on its own parent directory.
        """
        corpus = [
            _entry(TOOL_READ, "/a/b/x.py", STATUS_EXECUTED, minute=0),
            _entry(TOOL_READ, "/a/b/y.py", STATUS_EXECUTED, minute=1),
            _entry(TOOL_READ, "/a/c/z.py", STATUS_EXECUTED, minute=2),
        ]
        report = mine_rule_candidates(self.config, corpus)
        actual = tuple(
            (g.command_key, g.occurrences, g.distinct_commands)
            for g in sorted(report.groups, key=lambda g: g.command_key)
        )
        self.assertEqual(
            actual,
            (
                ("/a/b", 2, ("/a/b/x.py", "/a/b/y.py")),
                ("/a/c", 1, ("/a/c/z.py",)),
            ),
        )

    def test_two_tools_sharing_a_command_key_do_not_merge(self):
        """
        Given a Bash entry and an MCP-terminal entry whose commands share a
            leading token
        When mined
        Then they stay in two groups, one per tool.
        """
        corpus = [
            _entry(TOOL_BASH, "deploy prod", STATUS_EXECUTED, minute=0),
            _entry(TOOL_MCP, "deploy prod", STATUS_EXECUTED, minute=1),
        ]
        report = mine_rule_candidates(self.config, corpus)
        self.assertEqual(
            tuple(sorted((g.tool, g.command_key) for g in report.groups)),
            ((TOOL_BASH, "deploy"), (TOOL_MCP, "deploy")),
        )

    def test_two_signals_sharing_a_command_key_do_not_merge(self):
        """
        Given two curl entries with the same key, one EXECUTED and one REFUSED
        When mined
        Then they form two groups, one allow-candidate and one declined.
        """
        corpus = [
            _entry(TOOL_BASH, "curl a.test", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "curl b.test", STATUS_REFUSED, minute=1),
        ]
        report = mine_rule_candidates(self.config, corpus)
        self.assertEqual(
            tuple(sorted((g.signal, g.distinct_commands) for g in report.groups)),
            (
                (SIGNAL_ALLOW_CANDIDATE, ("curl a.test",)),
                (SIGNAL_DECLINED, ("curl b.test",)),
            ),
        )

    def test_observed_counts_tally_every_status_in_the_cluster(self):
        """
        Given four ask-verdict entries under one key with three different
            non-EXECUTED, non-REFUSED statuses
        When mined
        Then the group's observed_counts holds each status with its own count.
        """
        corpus = [
            _entry(TOOL_BASH, "find . -name x", STATUS_ERROR, minute=0),
            _entry(TOOL_BASH, "find . -name y", STATUS_ERROR, minute=1),
            _entry(TOOL_BASH, "find . -name z", STATUS_ASK, minute=2),
            _entry(TOOL_BASH, "find /", STATUS_UNKNOWN, minute=3),
        ]
        report = mine_rule_candidates(self.config, corpus)
        self.assertEqual(len(report.groups), 1)
        self.assertEqual(
            report.groups[0].observed_counts,
            {STATUS_ERROR: 2, STATUS_ASK: 1, STATUS_UNKNOWN: 1},
        )

    def test_a_command_the_config_already_allows_produces_no_group(self):
        """
        Given a config that allows 'ls' and an ls entry recorded EXECUTED
        When mined
        Then no group is produced -- consistent entries are dropped.
        """
        report = mine_rule_candidates(
            self.config, [_entry(TOOL_BASH, "ls -la", STATUS_EXECUTED)]
        )
        self.assertEqual(report.groups, ())

    def test_a_refused_entry_is_declined_and_reachable_from_both_accessors(self):
        """
        Given one REFUSED entry
        When mined
        Then MiningReport.declined and by_signal('declined') return the same
             single group, keyed on the command's leading token.
        """
        report = mine_rule_candidates(
            self.config, [_entry(TOOL_BASH, "rm -rf /tmp/x", STATUS_REFUSED)]
        )
        self.assertEqual(len(report.declined), 1)
        self.assertEqual(report.declined, report.by_signal(SIGNAL_DECLINED))
        self.assertEqual(report.declined[0].command_key, "rm")
        self.assertEqual(report.allow_candidates, [])

    def test_a_denied_command_never_executed_is_reported_as_denied(self):
        """
        Given a config whose no_match_fallback is explicitly deny and a command
            observed only as UNKNOWN
        When mined
        Then it is 'denied' with verdict deny, and not an allow-candidate.
        """
        config = _config(_layer(allow=["ls:*"], no_match_fallback=VERDICT_DENY))
        report = mine_rule_candidates(
            config, [_entry(TOOL_BASH, "curl evil.test", STATUS_UNKNOWN)]
        )
        self.assertEqual(report.allow_candidates, [])
        self.assertEqual(len(report.by_signal(SIGNAL_DENIED)), 1)
        self.assertEqual(
            report.by_signal(SIGNAL_DENIED)[0].current_verdict, VERDICT_DENY
        )

    def test_a_clusters_verdict_is_the_most_common_one_not_the_rarest(self):
        """
        Given four commands sharing the key 'zap', three of which the config
            denies and one of which it only asks about, all EXECUTED
        When mined
        Then the group's current_verdict is deny -- the majority verdict -- and
             its occurrence and distinct-command counts cover all four.
        """
        config = _config(_layer(allow=["ls:*"], deny=["[regex]^zap [abc]$"]))
        commands = ("zap a", "zap b", "zap c", "zap d")
        self.assertEqual(
            tuple(decide(config, TOOL_BASH, c).decision for c in commands),
            (VERDICT_DENY, VERDICT_DENY, VERDICT_DENY, VERDICT_ASK),
        )
        corpus = [
            _entry(TOOL_BASH, c, STATUS_EXECUTED, minute=i)
            for i, c in enumerate(commands)
        ]
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(len(report.groups), 1)
        group = report.groups[0]
        self.assertEqual(
            (
                group.command_key,
                group.current_verdict,
                group.occurrences,
                group.distinct_commands,
            ),
            ("zap", VERDICT_DENY, 4, commands),
        )

    def test_a_sixty_entry_corpus_is_grouped_without_loss(self):
        """
        Given sixty entries spread over four command keys in a known 30/15/10/5
            split, interleaved so no key is contiguous
        When mined
        Then every entry is accounted for: the occurrence counts match the split
             exactly and their sum is sixty, so a silent cap or dedup shows.
        """
        split = {"alpha": 30, "bravo": 15, "charlie": 10, "delta": 5}
        corpus = []
        pending = dict(split)
        minute = 0
        while any(pending.values()):
            for key in split:
                if pending[key]:
                    pending[key] -= 1
                    corpus.append(
                        _entry(
                            TOOL_BASH,
                            f"{key} run-{pending[key]}",
                            STATUS_EXECUTED,
                            minute=minute,
                        )
                    )
                    minute += 1
        self.assertEqual(len(corpus), 60)

        report = mine_rule_candidates(self.config, corpus)
        actual = {g.command_key: g.occurrences for g in report.groups}
        self.assertEqual(actual, split)
        self.assertEqual(sum(actual.values()), 60)
        self.assertEqual(
            {g.command_key: len(g.distinct_commands) for g in report.groups}, split
        )


class TestMinOccurrencesThreshold(unittest.TestCase):
    """min_occurrences drops clusters holding too few corpus entries."""

    def setUp(self):
        self.config = _config(_layer(allow=["ls:*"]))
        self.corpus = [
            _entry(TOOL_BASH, "curl a.test", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "curl b.test", STATUS_EXECUTED, minute=1),
        ]

    def test_the_threshold_is_inclusive_at_the_boundary(self):
        """
        Given a cluster of exactly two entries
        When mined at thresholds 1, 2 and 3
        Then it survives at 1 and 2 and is dropped at 3 -- the boundary is
             'at least min_occurrences', not 'more than'.
        """
        surviving = tuple(
            len(
                mine_rule_candidates(self.config, self.corpus, min_occurrences=n).groups
            )
            for n in (1, 2, 3)
        )
        self.assertEqual(surviving, (1, 1, 0))

    def test_the_threshold_counts_entries_not_distinct_commands(self):
        """
        Given one command repeated three times and three commands under three
            different keys recorded once each
        When mined at a threshold of three
        Then the repeated command's group survives and each single-entry group
             is dropped, because occurrences count entries.
        """
        corpus = [
            _entry(TOOL_BASH, "curl a.test", STATUS_EXECUTED, minute=i)
            for i in range(3)
        ] + [
            _entry(TOOL_BASH, f"{prog} a.test", STATUS_EXECUTED, minute=10 + i)
            for i, prog in enumerate(("wget", "aria2c", "httpie"))
        ]
        report = mine_rule_candidates(self.config, corpus, min_occurrences=3)
        self.assertEqual(
            tuple((g.command_key, g.occurrences) for g in report.groups),
            (("curl", 3),),
        )

    def test_one_event_recorded_by_two_harvesters_does_not_meet_a_threshold_of_two(
        self,
    ):
        """
        Given a single real event that the daily log and the transcript both
            recorded -- identical timestamp, tool and command, differing only in
            source file, which is exactly what harvest_corpus concatenates
        When mined with min_occurrences=2
        Then it does not clear the threshold, because one event is not two
             observations. Accepts any fix: de-duplication, distinct-event
             counting, or a source-aware occurrence count.
        """
        one_event_twice = [
            _entry(
                TOOL_BASH,
                "curl a.test",
                STATUS_EXECUTED,
                minute=0,
                log_file="/fake/logs/toolguard-2026-06-25.md",
            ),
            _entry(
                TOOL_BASH,
                "curl a.test",
                STATUS_EXECUTED,
                minute=0,
                log_file="/fake/transcripts/session.jsonl",
            ),
        ]
        report = mine_rule_candidates(self.config, one_event_twice, min_occurrences=2)
        self.assertEqual(
            report.groups,
            (),
            "one event recorded by both harvesters was counted as two "
            "observations and cleared a threshold of two",
        )


class TestGroupOrdering(unittest.TestCase):
    """Groups sort by occurrences, then signal priority, then tool, then key."""

    def test_groups_sort_by_occurrences_descending(self):
        """
        Given three allow-candidate clusters of sizes 1, 3 and 2
        When mined
        Then the groups come back largest first.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = (
            [
                _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=i)
                for i in range(3)
            ]
            + [
                _entry(TOOL_BASH, "wget a", STATUS_EXECUTED, minute=10 + i)
                for i in range(2)
            ]
            + [_entry(TOOL_BASH, "curl a", STATUS_EXECUTED, minute=20)]
        )
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(
            tuple((g.command_key, g.occurrences) for g in report.groups),
            (("git", 3), ("wget", 2), ("curl", 1)),
        )

    def test_equal_occurrences_break_by_signal_priority(self):
        """
        Given one single-entry cluster for each of the four reported signals,
            supplied in reverse priority order
        When mined
        Then they come back allow-candidate, declined, denied, asked.
        """
        config = _config(_layer(allow=["ls:*"], deny=["zap:*"]))
        corpus = [
            _entry(TOOL_BASH, "yum up", STATUS_UNKNOWN, minute=0),  # asked
            _entry(TOOL_BASH, "zap it", STATUS_UNKNOWN, minute=1),  # denied
            _entry(TOOL_BASH, "apt up", STATUS_REFUSED, minute=2),  # declined
            _entry(TOOL_BASH, "brew up", STATUS_EXECUTED, minute=3),  # allow-candidate
        ]
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(
            tuple(g.signal for g in report.groups),
            (SIGNAL_ALLOW_CANDIDATE, SIGNAL_DECLINED, SIGNAL_DENIED, SIGNAL_ASKED),
        )

    def test_equal_occurrences_and_signal_break_by_tool_then_command_key(self):
        """
        Given four single-entry allow-candidate clusters across two tools and
            two keys per tool, supplied in reverse order
        When mined
        Then they come back ordered by tool name, then command key.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry(TOOL_READ, "/zz/f.py", STATUS_EXECUTED, minute=0),
            _entry(TOOL_READ, "/aa/f.py", STATUS_EXECUTED, minute=1),
            _entry(TOOL_BASH, "zoo run", STATUS_EXECUTED, minute=2),
            _entry(TOOL_BASH, "ant run", STATUS_EXECUTED, minute=3),
        ]
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(
            tuple((g.tool, g.command_key) for g in report.groups),
            (
                (TOOL_BASH, "ant"),
                (TOOL_BASH, "zoo"),
                (TOOL_READ, "/aa"),
                (TOOL_READ, "/zz"),
            ),
        )


class TestVerdictEvidenceInsideAGroup(unittest.TestCase):
    """
    A group summarises many entries into one verdict string; these tests hold
    what that summary must not lose.
    """

    def test_a_currently_denied_command_is_not_summarised_away_as_ask(self):
        """
        Given a config that denies exactly 'rm -rf /' and a corpus in which that
            command and two ordinary rm commands were all EXECUTED
        When mined
        Then a reader can still tell that one member of the cluster is currently
             DENIED -- either the group's verdict says deny, or the denied
             command is in a group of its own. Otherwise the rendered line
             '[allow-candidate] Bash rm x3 (now: ask)' invites widening a hard
             deny, and the deny verdict was computed and discarded.
        """
        config = _config(_layer(allow=["ls:*"], deny=["[regex]^rm -rf /$"]))
        self.assertEqual(
            decide(config, TOOL_BASH, DANGEROUS_WITNESS).decision, VERDICT_DENY
        )
        self.assertEqual(decide(config, TOOL_BASH, "rm foo.txt").decision, VERDICT_ASK)

        corpus = [
            _entry(TOOL_BASH, DANGEROUS_WITNESS, STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "rm foo.txt", STATUS_EXECUTED, minute=1),
            _entry(TOOL_BASH, "rm bar.txt", STATUS_EXECUTED, minute=2),
        ]
        report = mine_rule_candidates(config, corpus)
        holders = [g for g in report.groups if DANGEROUS_WITNESS in g.distinct_commands]
        self.assertEqual(len(holders), 1)
        self.assertEqual(
            holders[0].current_verdict,
            VERDICT_DENY,
            "the group holding a currently-denied command reports verdict "
            f"{holders[0].current_verdict!r}; the deny is unrecoverable from "
            "the group and from the rendered report",
        )

    def test_an_empty_command_is_not_offered_as_a_rule_to_add(self):
        """
        Given a corpus entry whose command field is empty -- which resolves to
            deny through the fail-closed empty-extraction net, with no matched
            rule -- recorded as EXECUTED
        When mined
        Then it is not an allow-candidate: 'add an allow rule for the empty
             command' is advice derived from a safety net, not from a rule.
        """
        config = _config(_layer(allow=["ls:*"]))
        verdict = decide(config, TOOL_BASH, "")
        self.assertEqual(verdict.decision, VERDICT_DENY)
        self.assertIsNone(verdict.matched_rule)

        report = mine_rule_candidates(config, [_entry(TOOL_BASH, "", STATUS_EXECUTED)])
        self.assertEqual(
            report.allow_candidates,
            [],
            "an empty command denied by the extraction safety net was reported "
            "as a candidate to add to the allow list",
        )

    def test_a_command_that_does_not_parse_is_not_offered_as_a_rule_to_add(self):
        """
        Given a corpus entry the bash grammar cannot parse, which floors to ask
            through the undecidable net rather than matching any rule, recorded
            as EXECUTED
        When mined
        Then it is not an allow-candidate -- the ask came from the floor, so
             there is no approval fatigue to relieve and no pattern to write.
        """
        config = _config(_layer(allow=["ls:*"]))
        unparseable = "'unclosed"
        self.assertEqual(decide(config, TOOL_BASH, unparseable).decision, VERDICT_ASK)

        report = mine_rule_candidates(
            config, [_entry(TOOL_BASH, unparseable, STATUS_EXECUTED)]
        )
        self.assertEqual(
            report.allow_candidates,
            [],
            "an unparseable command floored to ask was reported as a candidate "
            "to add to the allow list",
        )

    def test_a_disclosure_comment_does_not_split_a_command_from_its_own_group(self):
        """
        Given the same git command recorded twice, once carrying the leading
            disclosure comment this project mandates and once without
        When mined
        Then both land in one group: the PEG extractor discards the comment
             before matching, so grouping must not key on '#'.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(
                TOOL_BASH,
                "# INTENT: check state\ngit status",
                STATUS_EXECUTED,
                minute=1,
            ),
        ]
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(
            tuple(g.command_key for g in report.groups),
            ("git",),
            "a disclosed command was filed under a separate group key",
        )


class TestEvaluateAddedAllowRule(unittest.TestCase):
    """A proposed allow rule is measured by decision-replay over the corpus."""

    def setUp(self):
        self.prov = _prov()
        self.config = _config(_layer(allow=["ls:*"], provenance=self.prov))
        self.corpus = [
            _entry(TOOL_BASH, "git push origin main", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "git push", STATUS_EXECUTED, minute=1),
            _entry(TOOL_BASH, "ls -la", STATUS_EXECUTED, minute=2),
        ]

    def test_newly_allowed_names_exactly_the_corpus_commands_the_rule_admits(self):
        """
        Given an ask-by-default config allowing only ls, and a corpus of two git
            push commands plus one already-allowed ls
        When 'git push:*' is evaluated at the project layer
        Then newly_allowed is exactly the two git push commands, sorted, with
             two broadened and nothing tightened.
        """
        effect = evaluate_added_allow_rule(
            self.config, TOOL_BASH, "git push:*", self.prov, self.corpus
        )
        self.assertEqual(
            (
                effect.tool,
                effect.pattern,
                effect.newly_allowed,
                effect.broadened_count,
                effect.tightened_count,
            ),
            (
                TOOL_BASH,
                "git push:*",
                ("git push", "git push origin main"),
                2,
                0,
            ),
        )
        self.assertEqual(effect.target_locus, self.prov.describe())

    def test_the_measured_config_keeps_the_layer_s_deny_list_and_fallback(self):
        """
        Given a layer carrying a deny rule and an explicit deny fallback
        When an allow rule is added for measurement
        Then the proposed config still denies the denied command and still
             falls back to deny, so nothing is reported as broadened merely
             because the measurement dropped the rest of the layer.
        """
        prov = _prov()
        config = _config(
            _layer(
                allow=["ls:*"],
                deny=["rm -rf:*"],
                provenance=prov,
                no_match_fallback=VERDICT_DENY,
            )
        )
        corpus = [
            _entry(TOOL_BASH, "rm -rf /tmp/x", STATUS_REFUSED, minute=0),
            _entry(TOOL_BASH, "curl a.test", STATUS_UNKNOWN, minute=1),
        ]
        effect = evaluate_added_allow_rule(
            config, TOOL_BASH, "git push:*", prov, corpus
        )
        self.assertEqual((effect.newly_allowed, effect.broadened_count), ((), 0))

        proposed = with_layer_allow_replaced(
            config, TOOL_BASH, prov, set(), ["git push:*"]
        )
        self.assertEqual(proposed.resolved_no_match_fallback(), VERDICT_DENY)
        self.assertEqual(
            decide(proposed, TOOL_BASH, "rm -rf /tmp/x").decision, VERDICT_DENY
        )
        self.assertEqual(decide(proposed, TOOL_BASH, "ls -la").decision, VERDICT_ALLOW)

    def test_newly_allowed_excludes_an_entry_that_broadened_only_to_ask(self):
        """
        Given a deny-by-default config with an ask rule for whoami, and a corpus
            holding both 'zap it' and the compound 'zap it && whoami'
        When 'zap:*' is proposed
        Then both entries are counted as broadened, but only the one that
             reaches allow is named in newly_allowed -- the compound stops at
             ask because its other leaf still asks.
        """
        prov = _prov()
        config = _config(
            _layer(
                allow=["ls:*"],
                ask=["whoami:*"],
                provenance=prov,
                no_match_fallback=VERDICT_DENY,
            )
        )
        corpus = [
            _entry(TOOL_BASH, "zap it", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "zap it && whoami", STATUS_EXECUTED, minute=1),
        ]
        proposed = with_layer_allow_replaced(config, TOOL_BASH, prov, set(), ["zap:*"])
        self.assertEqual(
            tuple(decide(proposed, TOOL_BASH, e.command).decision for e in corpus),
            (VERDICT_ALLOW, VERDICT_ASK),
        )

        effect = evaluate_added_allow_rule(config, TOOL_BASH, "zap:*", prov, corpus)
        self.assertEqual(
            (effect.newly_allowed, effect.broadened_count, effect.tightened_count),
            (("zap it",), 2, 0),
        )

    def test_a_wider_pattern_admits_the_dangerous_witness_the_evidence_omits(self):
        """
        Given the same corpus of git commands measured under two proposals --
            'git:*' and the tool-wide '*'
        When each proposal's config is driven through the real decision engine
        Then '*' admits 'rm -rf /' by matched_rule '*' while 'git:*' does not,
             so the two proposals are not equally safe...
        And the two AddRuleEffect results must therefore differ somewhere other
            than the echoed pattern, or the measurement certifies a tool-wide
            grant with the evidence of a narrow one.
        """
        corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "git diff HEAD", STATUS_EXECUTED, minute=1),
        ]
        narrow_cfg = with_layer_allow_replaced(
            self.config, TOOL_BASH, self.prov, set(), ["git:*"]
        )
        wide_cfg = with_layer_allow_replaced(
            self.config, TOOL_BASH, self.prov, set(), ["*"]
        )
        wide_verdict = decide(wide_cfg, TOOL_BASH, DANGEROUS_WITNESS)
        self.assertEqual(
            (wide_verdict.decision, wide_verdict.matched_rule), ("allow", "*")
        )
        self.assertNotEqual(
            decide(narrow_cfg, TOOL_BASH, DANGEROUS_WITNESS).decision, VERDICT_ALLOW
        )

        narrow = evaluate_added_allow_rule(
            self.config, TOOL_BASH, "git:*", self.prov, corpus
        )
        wide = evaluate_added_allow_rule(self.config, TOOL_BASH, "*", self.prov, corpus)

        self.assertNotEqual(
            evidence(narrow),
            evidence(wide),
            "a tool-wide grant and a git-only grant produced identical "
            f"replay evidence {evidence(wide)}; only the echoed pattern differs",
        )

    def test_an_empty_corpus_is_distinguishable_from_a_rule_that_admits_nothing(self):
        """
        Given the tool-wide pattern '*' measured against an EMPTY corpus, and a
            pattern matching nothing measured against a real two-entry corpus
        When both are evaluated
        Then their evidence differs: measuring nothing must not produce the same
             report as measuring something and finding no effect. Both currently
             yield newly_allowed=(), broadened=0, tightened=0.
        """
        real_corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "git diff HEAD", STATUS_EXECUTED, minute=1),
        ]
        measured_nothing = evaluate_added_allow_rule(
            self.config, TOOL_BASH, "*", self.prov, []
        )
        measured_something = evaluate_added_allow_rule(
            self.config, TOOL_BASH, "zzz-no-such-command:*", self.prov, real_corpus
        )

        self.assertNotEqual(
            evidence(measured_nothing),
            evidence(measured_something),
            "a tool-wide grant measured against zero entries reported the same "
            f"evidence {evidence(measured_nothing)} as a rule that genuinely "
            "admits nothing measured against a real corpus",
        )

    def test_a_rule_the_corpus_never_exercises_reports_no_effect(self):
        """
        Given a corpus with no matching command
        When a rule for a command absent from the corpus is evaluated
        Then nothing is reported as newly allowed or broadened.
        """
        effect = evaluate_added_allow_rule(
            self.config, TOOL_BASH, "docker compose:*", self.prov, self.corpus
        )
        self.assertEqual(
            (effect.newly_allowed, effect.broadened_count, effect.tightened_count),
            ((), 0, 0),
        )


class TestRenderMiningReport(unittest.TestCase):
    """render_mining_report turns a MiningReport into text or markdown."""

    def _one_group_report(self):
        config = _config(_layer(allow=["ls:*"]))
        return mine_rule_candidates(
            config, [_entry(TOOL_BASH, "whoami", STATUS_EXECUTED)]
        )

    def test_the_text_report_has_a_title_rule_tally_and_group_block(self):
        """
        Given a report holding one single-entry allow-candidate group
        When rendered as text
        Then the whole output equals the underlined title, the four-signal
             tally, the group header and its one command, exactly.
        """
        self.assertEqual(
            render_mining_report(self._one_group_report(), fmt=FMT_TEXT),
            "Toolguard Rule Mining Report\n"
            "============================\n"
            "\n"
            "allow-candidate: 1  declined: 0  denied: 0  asked: 0\n"
            "\n"
            "[allow-candidate] Bash 'whoami' x1 (now: ask)\n"
            "  - whoami\n",
        )

    def test_the_markdown_report_uses_headings_and_drops_the_underline(self):
        """
        Given the same one-group report
        When rendered as markdown
        Then the title becomes an H1, the group header an H2, and the ASCII
             underline is gone.
        """
        self.assertEqual(
            render_mining_report(self._one_group_report(), fmt=FMT_MARKDOWN),
            "# Toolguard Rule Mining Report\n"
            "\n"
            "allow-candidate: 1  declined: 0  denied: 0  asked: 0\n"
            "\n"
            "## [allow-candidate] Bash 'whoami' x1 (now: ask)\n"
            "  - whoami\n",
        )

    def test_the_default_format_is_text(self):
        """
        Given a report rendered with no fmt argument
        When compared with an explicit text render
        Then the two outputs are identical, so the default is exercised.
        """
        report = self._one_group_report()
        self.assertEqual(
            render_mining_report(report), render_mining_report(report, FMT_TEXT)
        )

    def test_the_tally_line_counts_groups_per_signal_with_distinct_totals(self):
        """
        Given a corpus producing one allow-candidate group -- holding five
            entries, so a group count and an occurrence count differ -- plus two
            declined groups, three denied and four asked
        When rendered
        Then the tally line reads each count against its own label, so swapping
             two labels, or counting occurrences instead of groups, changes it.
        """
        config = _config(_layer(allow=["ls:*"], deny=["zap:*", "pow:*", "bam:*"]))
        corpus = [
            _entry(TOOL_BASH, f"brew up {i}", STATUS_EXECUTED, minute=i)
            for i in range(5)
        ]
        corpus += [
            _entry(TOOL_BASH, f"{k} it", STATUS_REFUSED, minute=10 + i)
            for i, k in enumerate(("apt", "yay"))
        ]
        corpus += [
            _entry(TOOL_BASH, f"{k} it", STATUS_UNKNOWN, minute=20 + i)
            for i, k in enumerate(("zap", "pow", "bam"))
        ]
        corpus += [
            _entry(TOOL_BASH, f"{k} it", STATUS_UNKNOWN, minute=30 + i)
            for i, k in enumerate(("yum", "dnf", "apk", "pip"))
        ]
        report = mine_rule_candidates(config, corpus)
        self.assertEqual(len(report.groups), 10)
        tally = render_mining_report(report).splitlines()[3]
        self.assertEqual(tally, "allow-candidate: 1  declined: 2  denied: 3  asked: 4")

    def test_a_group_header_reports_occurrences_not_distinct_command_count(self):
        """
        Given one command recorded five times under a single key
        When rendered
        Then the header reads x5 even though there is one distinct command.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry(TOOL_BASH, "whoami", STATUS_EXECUTED, minute=i) for i in range(5)
        ]
        report = mine_rule_candidates(config, corpus)
        header = render_mining_report(report).splitlines()[5]
        self.assertEqual(header, "[allow-candidate] Bash 'whoami' x5 (now: ask)")

    def test_a_group_header_carries_the_clusters_own_current_verdict(self):
        """
        Given one group whose current verdict is deny and one whose is ask
        When rendered
        Then each header quotes its own verdict, so a hardcoded verdict shows.
        """
        config = _config(_layer(allow=["ls:*"], deny=["zap:*"]))
        corpus = [
            _entry(TOOL_BASH, "zap it", STATUS_UNKNOWN, minute=0),
            _entry(TOOL_BASH, "yum up", STATUS_UNKNOWN, minute=1),
        ]
        report = mine_rule_candidates(config, corpus)
        headers = tuple(
            line
            for line in render_mining_report(report).splitlines()
            if line.startswith("[")
        )
        self.assertEqual(
            headers,
            (
                "[denied] Bash 'zap' x1 (now: deny)",
                "[asked] Bash 'yum' x1 (now: ask)",
            ),
        )

    def test_an_empty_report_still_renders_a_tally_of_zeroes(self):
        """
        Given a report with no groups
        When rendered as text
        Then the output is the title and an all-zero tally, with no group block.
        """
        report = mine_rule_candidates(_config(_layer(allow=["ls:*"])), [])
        self.assertEqual(
            render_mining_report(report),
            "Toolguard Rule Mining Report\n"
            "============================\n"
            "\n"
            "allow-candidate: 0  declined: 0  denied: 0  asked: 0\n",
        )

    def test_an_unknown_format_raises_value_error_naming_the_format(self):
        """
        Given a valid report
        When rendered with a format that is neither text nor markdown
        Then ValueError is raised and the message echoes the rejected format.
        """
        report = mine_rule_candidates(_config(_layer(allow=["ls:*"])), [])
        for bad in ("html", "TEXT", "", "json"):
            with self.subTest(fmt=bad):
                with self.assertRaises(ValueError) as caught:
                    render_mining_report(report, fmt=bad)
                self.assertIn(repr(bad), str(caught.exception))


class TestNoAmbientStateDependence(unittest.TestCase):
    """Mining reads no configuration files and writes nothing."""

    def _snapshot(self):
        """
        Name, size and modification time of every entry directly under the three
        real directories mining must not touch, keyed by absolute path.

        Size and mtime are part of the key on purpose: a name-only listing cannot
        see a file being REWRITTEN, so an earlier test in the same run creating
        the file would make every later write invisible.
        """
        roots = [
            Path.home() / ".claude",
            Path.home() / ".toolguard",
            Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
            / "logs",
        ]

        def listing(root):
            if not root.is_dir():
                return None
            out = []
            for p in sorted(root.iterdir()):
                stat = p.stat()
                out.append((p.name, stat.st_size, stat.st_mtime_ns))
            return out

        return {str(root): listing(root) for root in roots}

    def test_driving_every_entry_point_writes_nothing_under_home_or_logs(self):
        """
        Given the name/size/mtime listing of ~/.claude, ~/.toolguard and the
            repo's logs/ taken from inside the test process
        When every public mining entry point is driven over a mixed corpus
        Then the listings are unchanged -- no file created, removed or rewritten.
        """
        before = self._snapshot()
        prov = _prov()
        config = _config(_layer(allow=["ls:*"], deny=["zap:*"], provenance=prov))
        corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(TOOL_BASH, "zap it", STATUS_REFUSED, minute=1),
            _entry(TOOL_READ, "/a/b/x.py", STATUS_EXECUTED, minute=2),
        ]
        report = mine_rule_candidates(config, corpus)
        render_mining_report(report, FMT_TEXT)
        render_mining_report(report, FMT_MARKDOWN)
        evaluate_added_allow_rule(config, TOOL_BASH, "git:*", prov, corpus)
        self.assertEqual(self._snapshot(), before)

    def test_the_same_corpus_mines_identically_from_a_foreign_working_directory(self):
        """
        Given a corpus mined from the repository root
        When the process changes to the filesystem root and mines it again
        Then the two reports are equal, so no ambient path resolution leaks in.
        """
        config = _config(_layer(allow=["ls:*"]))
        corpus = [
            _entry(TOOL_BASH, "git status", STATUS_EXECUTED, minute=0),
            _entry(TOOL_READ, "/a/b/x.py", STATUS_EXECUTED, minute=1),
        ]
        here = os.getcwd()
        first = mine_rule_candidates(config, corpus)
        self.addCleanup(os.chdir, here)
        os.chdir(os.sep)
        self.assertEqual(mine_rule_candidates(config, corpus), first)


if __name__ == "__main__":
    unittest.main()
