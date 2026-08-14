"""Unit tests for the corpus harvesting helper (toolguard.tools.corpus)."""

import io
import json
import os
import time
import unittest
import warnings
from contextlib import redirect_stderr
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.tools import log_harvest, transcript_harvest
from toolguard.tools.corpus import harvest_corpus, resolve_logs_dir
from toolguard.tools.log_harvest import LogEntry

#: The fixed "today" the rolling-window tests measure against. Deliberately far
#: from any real run date, so a clock patch that fails to take effect drops the
#: whole fixture out of every window and the test fails rather than passing by
#: coincidence.
_TODAY = date(2026, 6, 20)


class _FrozenDate(date):
    """A ``date`` whose ``today()`` is pinned to :data:`_TODAY`."""

    @classmethod
    def today(cls):
        return _TODAY


def _entry(
    stamp: str,
    command: str,
    *,
    tool: str = "Bash",
    status: str = "EXECUTED",
    rule_text: str = None,
    agent: str = "main",
    log_file: Path = None,
) -> LogEntry:
    """Build a LogEntry at the given ``YYYY-MM-DD HH:MM:SS`` stamp."""
    return LogEntry(
        timestamp=datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S"),
        tool=tool,
        command=command,
        status=status,
        rule_text=rule_text,
        agent=agent,
        log_file=log_file,
    )


def _section(stamp: str, command: str, status: str = "EXECUTED", **fields) -> str:
    """Render one daily-log Markdown section, in log_writer's field order."""
    lines = [
        f"## {stamp}",
        "",
        f"- **Status**: {status}",
        f"- **Command**: `{command}`",
    ]
    for label, value in fields.items():
        lines.append(f"- **{label.replace('_', ' ')}**: {value}")
    return "\n".join(lines) + "\n"


def _write_daily_log(logs_dir: Path, day: date, *sections: str) -> Path:
    """Write ``toolguard-<day>.md`` holding *sections*, creating *logs_dir*."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"toolguard-{day.isoformat()}.md"
    path.write_text("\n".join(sections), encoding="utf-8")
    return path


def _tool_use(stamp: str, tool: str, payload: dict, use_id: str) -> str:
    """One transcript JSONL line carrying a tool_use item at *stamp*."""
    return json.dumps(
        {
            "timestamp": stamp,
            "isSidechain": False,
            "message": {
                "content": [
                    {"type": "tool_use", "id": use_id, "name": tool, "input": payload}
                ]
            },
        }
    )


def _write_transcript(transcripts_dir: Path, name: str, *lines: str) -> Path:
    """Write a ``*.jsonl`` transcript holding *lines*, creating the directory."""
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    path = transcripts_dir / f"{name}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class TestResolveLogsDir(unittest.TestCase):
    """resolve_logs_dir maps a project to its daily-log directory."""

    def test_returns_logs_subdir_of_resolved_root(self):
        """
        Given a directory whose project root resolves to ROOT
        When resolve_logs_dir is called
        Then it returns ROOT/logs, having resolved from the directory given.
        """
        resolution = mock.Mock(root=Path("/proj/root"))
        with mock.patch(
            "toolguard.tools.corpus.resolve_project_root", return_value=resolution
        ) as resolve:
            self.assertEqual(
                resolve_logs_dir(Path("/proj/root/sub")), Path("/proj/root/logs")
            )
        self.assertEqual(resolve.call_args.args[0], Path("/proj/root/sub"))

    def test_falls_back_to_start_dir_when_root_unresolved(self):
        """
        Given a directory whose project root cannot be resolved (root is None)
        When resolve_logs_dir is called
        Then it falls back to start_dir/logs rather than raising, and the
            resolver was consulted (the fallback is not reached by skipping it).
        """
        resolution = mock.Mock(root=None)
        with mock.patch(
            "toolguard.tools.corpus.resolve_project_root", return_value=resolution
        ) as resolve:
            self.assertEqual(
                resolve_logs_dir(Path("/somewhere")), Path("/somewhere/logs")
            )
        resolve.assert_called_once_with(Path("/somewhere"))

    def test_no_argument_resolves_from_the_current_directory(self):
        """
        Given no project directory at all (the parameter's default)
        When resolve_logs_dir is called with no argument and nothing resolves
        Then the walk starts from the current directory and the result is the
            relative ./logs -- the default is exercised, not just declared.
        """
        resolution = mock.Mock(root=None)
        with mock.patch(
            "toolguard.tools.corpus.resolve_project_root", return_value=resolution
        ) as resolve:
            self.assertEqual(resolve_logs_dir(), Path("logs"))
        resolve.assert_called_once_with(None)


class TestHarvestCorpusPlumbing(unittest.TestCase):
    """harvest_corpus routes directories and the age window to two harvesters."""

    def setUp(self):
        """Patch both harvesters and the transcript-dir resolver as spies."""
        self.resolution = mock.Mock(root=Path("/proj"))
        self.log_entries = [
            _entry("2026-06-20 10:00:00", "git status", rule_text="git *"),
            _entry("2026-06-18 08:30:00", "rm -rf build", status="REFUSED"),
        ]
        self.transcript_entries = [
            _entry("2026-06-19 09:00:00", "ls -la", agent="subagent"),
            _entry("2026-06-21 11:15:00", "/etc/hosts", tool="Read", status="ERROR"),
        ]
        self.resolve = self.enterContext(
            mock.patch(
                "toolguard.tools.corpus.resolve_project_root",
                return_value=self.resolution,
            )
        )
        self.log_harvest = self.enterContext(
            mock.patch("toolguard.tools.corpus.harvest", return_value=self.log_entries)
        )
        self.transcript_harvest = self.enterContext(
            mock.patch(
                "toolguard.tools.corpus.harvest_transcripts",
                return_value=self.transcript_entries,
            )
        )
        self.transcript_dir = self.enterContext(
            mock.patch(
                "toolguard.tools.corpus.transcript_dir_for_project",
                return_value=Path("/home/.claude/projects/x"),
            )
        )

    def test_merges_both_sources_sorted_by_timestamp(self):
        """
        Given each harvester yields two entries, interleaved in time
        When harvest_corpus runs
        Then every harvested entry is returned -- the same objects, none
            dropped, none rebuilt -- oldest first.
        """
        corpus = harvest_corpus(Path("/proj"), max_age_days=30)

        self.assertEqual(len(corpus), 4)
        self.assertEqual(
            [e.command for e in corpus],
            ["rm -rf build", "ls -la", "git status", "/etc/hosts"],
        )
        # Object identity: an inert patch would yield real (or rebuilt) entries
        # and fail here even though the commands might still line up.
        self.assertIs(corpus[0], self.log_entries[1])
        self.assertIs(corpus[1], self.transcript_entries[0])
        self.assertIs(corpus[2], self.log_entries[0])
        self.assertIs(corpus[3], self.transcript_entries[1])

    def test_the_same_age_window_reaches_both_harvesters(self):
        """
        Given max_age_days=30
        When harvest_corpus runs
        Then both harvesters are called once with that window, against the
            project's logs/ and the resolved transcript directory.
        """
        harvest_corpus(Path("/proj"), max_age_days=30)

        self.assertEqual(self.log_harvest.call_args.args[0], Path("/proj/logs"))
        self.assertEqual(self.log_harvest.call_args.kwargs["max_age_days"], 30)
        self.assertEqual(
            self.transcript_harvest.call_args.args[0],
            Path("/home/.claude/projects/x"),
        )
        self.assertEqual(self.transcript_harvest.call_args.kwargs["max_age_days"], 30)

    def test_an_absent_window_is_passed_through_as_no_cap(self):
        """
        Given no max_age_days argument at all (the parameter's default)
        When harvest_corpus runs
        Then both harvesters receive max_age_days=None -- the default is
            forwarded, not quietly replaced with a cap.
        """
        harvest_corpus(Path("/proj"))

        self.assertIsNone(self.log_harvest.call_args.kwargs["max_age_days"])
        self.assertIsNone(self.transcript_harvest.call_args.kwargs["max_age_days"])

    def test_explicit_overrides_bypass_resolution(self):
        """
        Given explicit logs_dir and transcripts_dir overrides
        When harvest_corpus runs
        Then those exact directories are passed to the harvesters and the
            transcript-directory resolver is never consulted.
        """
        harvest_corpus(
            Path("/proj"),
            logs_dir=Path("/custom/logs"),
            transcripts_dir=Path("/custom/transcripts"),
        )

        self.assertEqual(self.log_harvest.call_args.args[0], Path("/custom/logs"))
        self.assertEqual(
            self.transcript_harvest.call_args.args[0], Path("/custom/transcripts")
        )
        self.transcript_dir.assert_not_called()

    def test_claude_home_reaches_the_transcript_directory_resolver(self):
        """
        Given a claude_home override and no transcripts_dir
        When harvest_corpus runs
        Then the resolver is asked for that home's transcript directory for the
            resolved project root.
        """
        harvest_corpus(Path("/proj"), claude_home=Path("/fake/claude"))

        self.transcript_dir.assert_called_once_with(Path("/proj"), Path("/fake/claude"))

    def test_nothing_is_capped_or_de_duplicated(self):
        """
        Given 40 log entries and 40 transcript entries, every one of them a
            duplicate of a log entry at the same timestamp and command
        When harvest_corpus runs
        Then all 80 are returned: no cap truncates the corpus and duplicates
            across the two sources are kept, so a count means "entries", not
            "distinct commands".
        """
        stamps = [f"2026-06-20 10:{n:02d}:00" for n in range(40)]
        self.log_harvest.return_value = [_entry(s, "git status") for s in stamps]
        self.transcript_harvest.return_value = [_entry(s, "git status") for s in stamps]

        corpus = harvest_corpus(Path("/proj"))

        self.assertEqual(len(corpus), 80)
        self.assertEqual(sum(1 for e in corpus if e.command == "git status"), 80)


class TestHarvestCorpusAgainstRealDirectories(ConfigIsolationMixin, unittest.TestCase):
    """
    harvest_corpus against real fixture directories.

    Uses ConfigIsolationMixin for Path.home(): the default transcript directory
    is derived from it, and the project-root walk stops at it.
    """

    def setUp(self):
        """Isolate home and the project root, and take the logs/ directory."""
        self.home, self.project = self.isolate_config_environment()
        self.logs = self.project / "logs"
        self.transcripts = self.home / ".claude" / "projects" / "encoded"

    def test_harvests_the_project_roots_logs_not_the_starting_directory(self):
        """
        Given a log file under the project root's logs/ and a subdirectory to
            start from, itself holding a decoy logs/ with a different command
        When harvest_corpus runs against the subdirectory
        Then the root's log is harvested and the subdirectory's decoy is not.
        """
        _write_daily_log(self.logs, _TODAY, _section("2026-06-20 10:00:00", "git push"))
        sub = self.project / "sub"
        _write_daily_log(sub / "logs", _TODAY, _section("2026-06-20 10:00:00", "decoy"))

        corpus = harvest_corpus(sub)

        self.assertEqual([e.command for e in corpus], ["git push"])

    def test_a_daily_log_entry_carries_every_field_replay_needs(self):
        """
        Given a REFUSED daily-log section with a violated rule and a subagent
        When harvest_corpus runs
        Then the harvested entry carries the timestamp, tool, command, status,
            rule text, agent and source file -- replay attributes a verdict
            from these, so a field bound to the wrong one is silent.
        """
        path = _write_daily_log(
            self.logs,
            _TODAY,
            _section(
                "2026-06-20 14:05:09",
                "rm -rf /tmp/zzz",
                status="REFUSED",
                Violated_Rules="`rm -rf *`",
                Agent="doc-writer",
            ),
        )

        (harvested,) = harvest_corpus(self.project)

        self.assertEqual(harvested.timestamp, datetime(2026, 6, 20, 14, 5, 9))
        self.assertEqual(harvested.tool, "Bash")
        self.assertEqual(harvested.command, "rm -rf /tmp/zzz")
        self.assertEqual(harvested.status, "REFUSED")
        self.assertEqual(harvested.rule_text, "rm -rf *")
        self.assertEqual(harvested.agent, "doc-writer")
        self.assertEqual(harvested.log_file, path)

    def test_a_file_tool_entry_keeps_its_tool_and_its_path(self):
        """
        Given a daily-log section whose Command field is `Read(/etc/hosts)`
        When harvest_corpus runs
        Then the entry's tool is Read and its command is the bare path -- a
            replay of it must reach the file-path matcher, not the Bash one.
        """
        _write_daily_log(
            self.logs,
            _TODAY,
            _section("2026-06-20 09:00:00", "Read(/etc/hosts)", Matched_Rule="`~/**`"),
        )

        (harvested,) = harvest_corpus(self.project)

        self.assertEqual(harvested.tool, "Read")
        self.assertEqual(harvested.command, "/etc/hosts")

    def test_a_transcript_entry_carries_its_tools_own_payload(self):
        """
        Given a transcript under the given claude_home holding a Bash tool_use
            (command) and a Read tool_use (file_path)
        When harvest_corpus runs with that claude_home and no transcripts_dir
        Then both are harvested with their own payload keys, so the transcript
            half of the corpus is not Bash-only.
        """
        claude_home = self.home / "elsewhere-claude"
        encoded = str(self.project.resolve()).replace("/", "-")
        _write_transcript(
            claude_home / "projects" / encoded,
            "session",
            _tool_use("2026-06-20T09:00:00", "Bash", {"command": "git fetch"}, "u1"),
            _tool_use("2026-06-20T09:01:00", "Read", {"file_path": "/etc/motd"}, "u2"),
        )

        corpus = harvest_corpus(self.project, claude_home=claude_home)

        self.assertEqual(
            [(e.tool, e.command) for e in corpus],
            [("Bash", "git fetch"), ("Read", "/etc/motd")],
        )

    def test_a_section_that_does_not_parse_does_not_cost_the_rest_of_the_file(self):
        """
        Given a log file whose middle section is a multi-line command (which
            log_harvest cannot read back -- proposed ticket 51)
        When harvest_corpus runs
        Then the sections either side are still harvested; one unreadable
            entry costs one entry, not the file.
        """
        _write_daily_log(
            self.logs,
            _TODAY,
            _section("2026-06-20 09:00:00", "git status"),
            "## 2026-06-20 09:30:00\n\n- **Status**: EXECUTED\n"
            "- **Command**: `python - <<'PY'\nprint(1)\nPY`\n",
            _section("2026-06-20 10:00:00", "git log"),
        )

        corpus = harvest_corpus(self.project)

        self.assertEqual([e.command for e in corpus], ["git status", "git log"])

    def test_the_two_sources_share_one_clock_when_they_interleave(self):
        """
        Given a transcript entry timestamped in UTC and daily-log entries in
            naive local time, one either side of it once converted
        When harvest_corpus runs under a fixed non-UTC local timezone
        Then the transcript entry sorts between them -- the merge sort is only
            meaningful because transcript times are converted to local.
        """
        self.addCleanup(time.tzset)
        self.enterContext(mock.patch.dict(os.environ, {"TZ": "XXX-05:00"}))
        time.tzset()
        # Precondition, so the fixture below is not silently tz-dependent.
        self.assertEqual(
            datetime(2026, 6, 20, 7, 0, tzinfo=timezone.utc)
            .astimezone()
            .replace(tzinfo=None),
            datetime(2026, 6, 20, 12, 0),
        )
        _write_daily_log(
            self.logs,
            _TODAY,
            _section("2026-06-20 11:59:00", "before"),
            _section("2026-06-20 12:01:00", "after"),
        )
        _write_transcript(
            self.transcripts,
            "session",
            _tool_use("2026-06-20T07:00:00Z", "Bash", {"command": "utc"}, "u1"),
        )

        corpus = harvest_corpus(self.project, transcripts_dir=self.transcripts)

        self.assertEqual([e.command for e in corpus], ["before", "utc", "after"])


class TestRollingWindow(ConfigIsolationMixin, unittest.TestCase):
    """max_age_days bounds both sources against a fixed local 'today'."""

    def setUp(self):
        """Freeze both harvesters' clocks and write four days of both sources."""
        self.home, self.project = self.isolate_config_environment()
        self.logs = self.project / "logs"
        self.transcripts = self.home / ".claude" / "projects" / "encoded"
        self.enterContext(mock.patch.object(log_harvest, "date", _FrozenDate))
        self.enterContext(mock.patch.object(transcript_harvest, "date", _FrozenDate))
        for back in range(4):
            day = _TODAY - timedelta(days=back)
            _write_daily_log(self.logs, day, _section(f"{day} 10:00:00", f"log-{back}"))
            _write_transcript(
                self.transcripts,
                f"s{back}",
                _tool_use(
                    f"{day}T11:00:00", "Bash", {"command": f"tr-{back}"}, f"u{back}"
                ),
            )

    def _commands(self, **kwargs):
        """Harvest the fixture and return the commands, oldest first."""
        return [
            e.command
            for e in harvest_corpus(
                self.project, transcripts_dir=self.transcripts, **kwargs
            )
        ]

    def test_no_window_harvests_every_day_of_both_sources(self):
        """
        Given four days of daily logs and four transcripts
        When harvest_corpus runs with no max_age_days
        Then all eight entries are harvested, oldest first.
        """
        self.assertEqual(
            self._commands(),
            [
                "log-3",
                "tr-3",
                "log-2",
                "tr-2",
                "log-1",
                "tr-1",
                "log-0",
                "tr-0",
            ],
        )

    def test_a_zero_day_window_keeps_today_and_nothing_earlier(self):
        """
        Given entries on today and the three days before it
        When harvest_corpus runs with max_age_days=0
        Then only today's two entries survive -- the floor is today itself.
        """
        self.assertEqual(self._commands(max_age_days=0), ["log-0", "tr-0"])

    def test_a_one_day_window_reaches_back_to_yesterday_inclusive(self):
        """
        Given entries on today and the three days before it
        When harvest_corpus runs with max_age_days=1
        Then yesterday's entries survive and the day before that does not: the
            floor is today-N and it is inclusive, so N=1 spans two dates.
        """
        self.assertEqual(
            self._commands(max_age_days=1), ["log-1", "tr-1", "log-0", "tr-0"]
        )

    def test_the_window_bounds_the_transcript_source_as_well_as_the_logs(self):
        """
        Given both sources carry an entry three days old
        When harvest_corpus runs with max_age_days=2
        Then neither source contributes it -- one window, both sources.
        """
        commands = self._commands(max_age_days=2)

        self.assertNotIn("log-3", commands)
        self.assertNotIn("tr-3", commands)
        self.assertIn("log-2", commands)
        self.assertIn("tr-2", commands)

    def test_an_out_of_window_entry_inside_an_in_window_file_is_dropped(self):
        """
        Given today's log file also holds a section timestamped four days ago
        When harvest_corpus runs with max_age_days=1
        Then that section is dropped: the window is applied to each entry's own
            timestamp, not only to the file it was found in.
        """
        stale = _TODAY - timedelta(days=4)
        _write_daily_log(
            self.logs,
            _TODAY,
            _section(f"{_TODAY} 10:00:00", "log-0"),
            _section(f"{stale} 23:50:00", "smuggled-in"),
        )

        self.assertNotIn("smuggled-in", self._commands(max_age_days=1))

    def test_an_in_window_entry_inside_an_out_of_window_file_is_dropped(self):
        """
        Given a log file NAMED four days ago that holds a section timestamped
            today (a shape a hand-edited or restored log can take)
        When harvest_corpus runs with max_age_days=1
        Then it is dropped unread: the file name is the index, so a file
            outside the window is never opened.
        """
        stale = _TODAY - timedelta(days=4)
        _write_daily_log(
            self.logs, stale, _section(f"{_TODAY} 10:00:00", "misfiled-but-recent")
        )

        self.assertNotIn("misfiled-but-recent", self._commands(max_age_days=1))

    def test_a_negative_window_is_rejected_rather_than_emptying_the_corpus(self):
        """
        Given a corpus that is entirely inside any sane window
        When harvest_corpus runs with max_age_days=-1
        Then it rejects the value, because the alternative is what it does
            today: a floor in the future silently discards every entry and
            returns an empty corpus indistinguishable from a clean one.
        """
        with self.assertRaises(ValueError):
            harvest_corpus(
                self.project, transcripts_dir=self.transcripts, max_age_days=-1
            )


class TestAnEmptyCorpusSaysNothingAboutWhy(ConfigIsolationMixin, unittest.TestCase):
    """What harvest_corpus reports when it harvests nothing (proposed ticket 29)."""

    def setUp(self):
        """Isolate home and the project root, and freeze both clocks."""
        self.home, self.project = self.isolate_config_environment()
        self.logs = self.project / "logs"
        self.transcripts = self.home / ".claude" / "projects" / "encoded"
        self.enterContext(mock.patch.object(log_harvest, "date", _FrozenDate))
        self.enterContext(mock.patch.object(transcript_harvest, "date", _FrozenDate))

    def _populate(self):
        """One parseable entry in each source, both dated today."""
        _write_daily_log(
            self.logs, _TODAY, _section(f"{_TODAY} 10:00:00", "git status")
        )
        _write_transcript(
            self.transcripts,
            "session",
            _tool_use(f"{_TODAY}T11:00:00", "Bash", {"command": "ls"}, "u1"),
        )

    def test_five_different_reasons_all_reach_an_empty_corpus(self):
        """
        Given five unrelated reasons to harvest nothing -- absent directories,
            present but empty ones, a directory of files whose names are not
            daily logs, a file whose every section is unparseable, and a window
            that excludes all the data
        When harvest_corpus runs against each
        Then every one returns an empty list. That they are also
            indistinguishable from each other is what the next test asserts;
            the claim here is only that all five reach empty.
        """
        absent = self.project / "gone"
        empty = self.project / "empty"
        empty.mkdir()
        wrong_names = self.project / "wrong-names"
        wrong_names.mkdir()
        (wrong_names / "toolguard-errors.md").write_text("## 2026-06-20 10:00:00\n")
        unparseable = self.project / "unparseable"
        _write_daily_log(
            unparseable, _TODAY, "## not-a-timestamp\n\n- **Status**: EXECUTED\n"
        )
        stale = self.project / "stale"
        _write_daily_log(
            stale,
            _TODAY - timedelta(days=10),
            _section(f"{_TODAY - timedelta(days=10)} 10:00:00", "long ago"),
        )
        self._populate()

        results = {
            "absent": harvest_corpus(
                self.project, logs_dir=absent, transcripts_dir=absent
            ),
            "empty": harvest_corpus(
                self.project, logs_dir=empty, transcripts_dir=empty
            ),
            "wrong names": harvest_corpus(
                self.project, logs_dir=wrong_names, transcripts_dir=wrong_names
            ),
            "unparseable": harvest_corpus(
                self.project, logs_dir=unparseable, transcripts_dir=empty
            ),
            "window excludes all": harvest_corpus(
                self.project, logs_dir=stale, transcripts_dir=empty, max_age_days=1
            ),
        }

        # The fixture can produce the negative case in both shapes: the
        # populated directories harvest two entries, and the same stale
        # directory harvests its entry once the window stops excluding it.
        self.assertEqual(
            len(harvest_corpus(self.project, transcripts_dir=self.transcripts)), 2
        )
        self.assertEqual(
            len(harvest_corpus(self.project, logs_dir=stale, transcripts_dir=empty)), 1
        )
        for reason, corpus in results.items():
            with self.subTest(reason=reason):
                self.assertEqual(corpus, [])

    def test_a_missing_source_directory_is_reported_on_some_channel(self):
        """
        Given a logs directory that does not exist at all
        When harvest_corpus runs
        Then something says so -- a warning, a line on stderr, or a return
            value richer than a bare list. Today nothing does, and an empty
            corpus is the strongest-looking evidence a consolidation safety
            gate can be handed. Which channel carries it is the fix's choice;
            this test only requires that one of them does.
        """
        self._populate()
        stderr = io.StringIO()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            with redirect_stderr(stderr):
                corpus = harvest_corpus(
                    self.project,
                    logs_dir=self.project / "never-created",
                    transcripts_dir=self.transcripts,
                )

        self.assertEqual([e.command for e in corpus], ["ls"])
        reported = (
            bool(caught) or bool(stderr.getvalue()) or not isinstance(corpus, list)
        )
        self.assertTrue(
            reported,
            "harvesting a directory that does not exist produced no warning, no "
            "stderr and a bare list -- indistinguishable from a clean harvest",
        )


if __name__ == "__main__":
    unittest.main()
