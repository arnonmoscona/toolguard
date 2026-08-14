"""Unit tests for toolguard.tools.transcript_harvest -- transcripts into the LogEntry corpus shape."""

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from toolguard.tool_spec import (
    BUILTIN_TOOLS,
    KNOWN_TOOL_NAMES,
    TOOLS_BY_NAME,
    ToolKind,
    ToolSpec,
)
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.transcript_harvest import (
    _command_for_tool,
    _extract_text,
    harvest_transcript_file,
    harvest_transcripts,
    transcript_dir_for_project,
)


# ---------------------------------------------------------------------------
# Whole-module isolation guard
# ---------------------------------------------------------------------------

#: Trees no test here may write into. Absolute, captured at import, before any
#: test patches ``Path.home``. Cost measured at 0.04s for ~24,000 files.
_WATCHED_TREES = (
    (Path.home() / ".claude").resolve(),
    (Path.home() / ".toolguard").resolve(),
    (Path(__file__).resolve().parents[2] / "logs"),
)

#: A before/after snapshot cannot attribute a write to a process, and these
#: subtrees are written by the live Claude Code session and its toolguard hook
#: while the suite runs -- another agent's command is enough. A new file under
#: them is therefore not evidence against this module; a *deleted* one still
#: is, and is still checked. Everything outside them is checked both ways.
_LIVE_WRITE_SUBTREES = (
    (Path.home() / ".claude" / "projects").resolve(),
    (Path.home() / ".claude" / "shell-snapshots").resolve(),
    (Path.home() / ".claude" / "todos").resolve(),
    (Path(__file__).resolve().parents[2] / "logs"),
)

_TREE_SNAPSHOT: dict = {}


def _snapshot_watched_trees() -> dict:
    """Map each watched tree to the set of absolute file paths under it."""
    snapshot = {}
    for tree in _WATCHED_TREES:
        found = set()
        for dirpath, _dirnames, filenames in os.walk(tree):
            for filename in filenames:
                found.add(os.path.join(dirpath, filename))
        snapshot[str(tree)] = found
    return snapshot


def _is_live_write_path(path: str) -> bool:
    """True when *path* lies under a subtree other processes write during a run."""
    return any(
        path.startswith(str(subtree) + os.sep) for subtree in _LIVE_WRITE_SUBTREES
    )


def setUpModule():
    """Record the real ~/.claude, ~/.toolguard and repo logs/ trees."""
    _TREE_SNAPSHOT.update(_snapshot_watched_trees())


def tearDownModule():
    """Fail if a file was added or removed in a watched tree by these tests."""
    after = _snapshot_watched_trees()
    damage = {}
    for tree, before in _TREE_SNAPSHOT.items():
        added = sorted(p for p in after[tree] - before if not _is_live_write_path(p))
        removed = sorted(before - after[tree])
        if added or removed:
            damage[tree] = {"added": added[:10], "removed": removed[:10]}
    if damage:
        raise AssertionError(f"tests touched files outside their fixtures: {damage}")


# ---------------------------------------------------------------------------
# Transcript-entry builders
# ---------------------------------------------------------------------------


def _assistant_tool_use(ts, tool, tool_input, use_id, is_sidechain=False):
    """An assistant entry containing one tool_use item."""
    return {
        "type": "assistant",
        "timestamp": ts,
        "isSidechain": is_sidechain,
        "message": {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": use_id, "name": tool, "input": tool_input}
            ],
        },
    }


def _user_tool_result(ts, use_id, is_error, content):
    """A user entry containing one tool_result item."""
    return {
        "type": "user",
        "timestamp": ts,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": use_id,
                    "is_error": is_error,
                    "content": content,
                }
            ],
        },
    }


def _write_transcript(directory: Path, name: str, entries: list) -> Path:
    """Write a list of entry dicts as a JSONL transcript file."""
    path = directory / name
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    return path


class _IsolatedHomeMixin:
    """
    Give each test a throwaway HOME and a transcript directory inside it.

    ``transcript_dir_for_project`` falls back to ``Path.home()`` when its
    ``claude_home`` argument is omitted, so a bare temp directory is not
    enough: the fallback has to land somewhere disposable too.
    """

    def setUp(self):
        """Build the throwaway HOME and redirect Path.home() at it."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)

        self.fake_home = self.tmpdir / "home"
        self.fake_home.mkdir()
        home_patch = patch.object(Path, "home", staticmethod(lambda: self.fake_home))
        home_patch.start()
        self.addCleanup(home_patch.stop)
        env_patch = patch.dict(os.environ, {"HOME": str(self.fake_home)}, clear=False)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def chdir_to(self, directory: Path) -> None:
        """Change cwd for the rest of the test, restoring it afterwards."""
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(directory)


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------


class TestStatusDerivation(_IsolatedHomeMixin, unittest.TestCase):
    """tool_use joined to its tool_result yields the right observed status."""

    def test_executed_when_result_not_error(self):
        """
        Given a Bash tool_use whose tool_result has is_error False
        When the file is harvested
        Then one EXECUTED LogEntry carries every attribution field: tool,
        command, status, no reason, the main agent and the source file.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-a.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "ls -la /srv"},
                    "use-bash-1",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-1", False, "total 0"
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertIsInstance(e, LogEntry)
        self.assertEqual(e.tool, "Bash")
        self.assertEqual(e.command, "ls -la /srv")
        self.assertEqual(e.status, "EXECUTED")
        self.assertIsNone(e.rule_text)
        self.assertEqual(e.agent, "main")
        self.assertEqual(e.log_file, path)

    def test_refused_when_user_rejects_prompt(self):
        """
        Given a Bash tool_use whose result error says the user rejected the prompt
        When harvested
        Then the status is REFUSED and the whole rejection text is the reason.
        """
        rejection = (
            "The user doesn't want to proceed with this tool use. "
            "The tool use was rejected."
        )
        path = _write_transcript(
            self.tmpdir,
            "session-b.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "rm -rf /srv/data"},
                    "use-bash-2",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-2", True, rejection
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, "REFUSED")
        self.assertEqual(entries[0].rule_text, rejection)

    def test_rejection_marker_matched_regardless_of_case(self):
        """
        Given a rejection message whose marker is capitalised as Claude Code writes it
        When harvested
        Then it is still classified REFUSED rather than ERROR.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-c.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "curl https://example.test"},
                    "use-bash-3",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z",
                    "use-bash-3",
                    True,
                    "The Tool Use Was Rejected by the operator.",
                ),
            ],
        )
        self.assertEqual(harvest_transcript_file(path)[0].status, "REFUSED")

    def test_error_when_tool_fails_but_not_rejected(self):
        """
        Given a tool_use whose result is an ordinary tool error (not a rejection)
        When harvested
        Then the status is ERROR (permitted but failed) and the error text is
        kept as the reason, exactly as it is for a REFUSED entry.
        """
        failure = "<tool_use_error>File has not been read yet.</tool_use_error>"
        path = _write_transcript(
            self.tmpdir,
            "session-d.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Write",
                    {"file_path": "/srv/report.txt"},
                    "use-write-1",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-write-1", True, failure
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(entries[0].status, "ERROR")
        self.assertEqual(entries[0].rule_text, failure)

    def test_unknown_when_no_matching_result(self):
        """
        Given a tool_use with no corresponding tool_result in the transcript
        When harvested
        Then the entry status is UNKNOWN and it carries no reason.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-e.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "pwd"},
                    "use-bash-4",
                )
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(entries[0].status, "UNKNOWN")
        self.assertIsNone(entries[0].rule_text)

    def test_a_long_error_reason_is_truncated_to_200_characters_with_no_marker(self):
        """
        Given an error result far longer than 200 characters
        When harvested
        Then the reason is the first 200 characters, with nothing in the record
        marking it as truncated -- a cut reason and a naturally short one are
        indistinguishable downstream.
        """
        long_error = "".join(f"line-{n:04d} " for n in range(60))
        self.assertGreater(len(long_error), 200)
        path = _write_transcript(
            self.tmpdir,
            "session-f.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "make build"},
                    "use-bash-5",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-5", True, long_error
                ),
            ],
        )
        reason = harvest_transcript_file(path)[0].rule_text
        self.assertEqual(len(reason), 200)
        self.assertEqual(reason, long_error.strip()[:200])
        self.assertFalse(reason.endswith("..."))

    def test_a_long_rejection_reason_is_stripped_then_truncated(self):
        """
        Given a rejection message padded with whitespace and far longer than
        200 characters
        When harvested
        Then the REFUSED reason is stripped first and then cut to 200
        characters, on the same terms as an ERROR reason.
        """
        padded = (
            "   The user doesn't want to proceed with this tool use. "
            + "".join(f"detail-{n:04d} " for n in range(40))
            + "   "
        )
        path = _write_transcript(
            self.tmpdir,
            "session-f2.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "make deploy"},
                    "use-bash-29",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-29", True, padded
                ),
            ],
        )
        entry = harvest_transcript_file(path)[0]
        self.assertEqual(entry.status, "REFUSED")
        self.assertEqual(len(entry.rule_text), 200)
        self.assertEqual(entry.rule_text, padded.strip()[:200])
        self.assertFalse(entry.rule_text.startswith(" "))

    def test_repeated_tool_use_id_keeps_the_last_result(self):
        """
        Given two tool_results sharing one tool_use_id, an error then a success
        When harvested
        Then the later result wins and the status is EXECUTED.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-g.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "flaky-step"},
                    "use-bash-6",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-6", True, "transient failure"
                ),
                _user_tool_result(
                    "2026-06-20T10:00:02.000Z", "use-bash-6", False, "second try ok"
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(entries[0].status, "EXECUTED")
        self.assertIsNone(entries[0].rule_text)


# ---------------------------------------------------------------------------
# Tool extraction
# ---------------------------------------------------------------------------


class TestToolExtraction(_IsolatedHomeMixin, unittest.TestCase):
    """Which tools reach the corpus, and where each one's subject is read from."""

    def test_file_tool_uses_file_path(self):
        """
        Given an Edit tool_use with input.file_path
        When harvested
        Then the entry's tool is 'Edit' and command is the file path.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-h.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Edit",
                    {
                        "file_path": "/abs/foo.py",
                        "old_string": "a",
                        "new_string": "b",
                    },
                    "use-edit-1",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-edit-1", False, "ok"
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual((entries[0].tool, entries[0].command), ("Edit", "/abs/foo.py"))

    def test_harvest_reads_the_payload_key_the_registry_declares(self):
        """
        Given a registry in which Read's payload key is 'target_path'
        When a transcript Read call carrying only 'target_path' is harvested
        Then that value becomes the entry's command -- the harvester consults
        the registry rather than assuming a key.
        """
        renamed = ToolSpec(
            name="Read",
            kind=ToolKind.FILE,
            payload_key="target_path",
            is_builtin=True,
        )
        path = _write_transcript(
            self.tmpdir,
            "session-i.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Read",
                    {"target_path": "/abs/renamed.py"},
                    "use-read-1",
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-read-1", False, "ok"
                ),
            ],
        )
        with patch.dict(
            "toolguard.tools.transcript_harvest.TOOLS_BY_NAME", {"Read": renamed}
        ):
            self.assertIs(TOOLS_BY_NAME["Read"], renamed)
            entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command, "/abs/renamed.py")

    def test_tool_absent_from_the_registry_is_dropped_without_a_signal(self):
        """
        Given a tool_use for a tool with no ToolSpec at all
        When harvested
        Then it produces no LogEntry.
        """
        unregistered = "mcp__basic-memory__search"
        self.assertNotIn(unregistered, KNOWN_TOOL_NAMES)
        path = _write_transcript(
            self.tmpdir,
            "session-j.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    unregistered,
                    {"query": "x"},
                    "use-mcp-1",
                ),
                _user_tool_result("2026-06-20T10:00:01.000Z", "use-mcp-1", False, "ok"),
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    def test_registered_non_builtin_command_tool_is_dropped_too(self):
        """
        Given a fully described, non-builtin command tool that docs tell users
        to govern (mcp__jetbrains__execute_terminal_command)
        When a transcript call to it is harvested
        Then it produces no LogEntry, because the harvest gate is builtin
        membership and not registry membership -- the corpus therefore cannot
        see a governed tool the daily log does see.
        """
        governable = "mcp__jetbrains__execute_terminal_command"
        self.assertIn(governable, KNOWN_TOOL_NAMES)
        self.assertNotIn(governable, BUILTIN_TOOLS)
        self.assertEqual(TOOLS_BY_NAME[governable].kind, ToolKind.COMMAND)
        self.assertEqual(TOOLS_BY_NAME[governable].payload_key, "command")
        path = _write_transcript(
            self.tmpdir,
            "session-k.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    governable,
                    {"command": "git status --porcelain"},
                    "use-jb-1",
                ),
                _user_tool_result("2026-06-20T10:00:01.000Z", "use-jb-1", False, "ok"),
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    def test_bash_without_command_skipped(self):
        """
        Given a Bash tool_use whose input has no command string
        When harvested
        Then it produces no LogEntry.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-l.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"description": "x"},
                    "use-bash-7",
                )
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    def test_blank_command_skipped(self):
        """
        Given a Bash tool_use whose command is only whitespace
        When harvested
        Then it produces no LogEntry -- a blank subject is no subject.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-m.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "   \t "},
                    "use-bash-8",
                )
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    def test_non_string_target_skipped(self):
        """
        Given an Edit tool_use whose file_path is a dict rather than a string
        When harvested
        Then it produces no LogEntry rather than a non-string command.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-n.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Edit",
                    {"file_path": {"path": "/abs/foo.py"}},
                    "use-edit-2",
                )
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    def test_non_dict_tool_input_skipped(self):
        """
        Given a tool_use whose input is a string rather than an object
        When harvested
        Then it produces no LogEntry.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-o.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z", "Bash", "ls -la", "use-bash-9"
                )
            ],
        )
        self.assertEqual(harvest_transcript_file(path), [])

    @patch.dict(
        "toolguard.tools.transcript_harvest.TOOLS_BY_NAME",
        {
            "Read": ToolSpec(
                name="Read",
                kind=ToolKind.FILE,
                payload_key="target_path",
                is_builtin=True,
            )
        },
    )
    def test_command_for_tool_reads_the_registered_key(self):
        """
        Given a Read registry entry whose payload key is 'target_path'
        When a tool_input carrying only 'target_path' is extracted
        Then the target is returned (not None)
        """
        self.assertEqual(
            _command_for_tool("Read", {"target_path": "/abs/foo.py"}),
            "/abs/foo.py",
        )

    def test_command_for_tool_falls_back_to_command_for_an_unregistered_tool(self):
        """
        Given a tool name with no ToolSpec
        When its subject is extracted
        Then the 'command' key is read as a fallback, so an unregistered
        command-shaped tool still yields a subject rather than raising.
        """
        self.assertNotIn("Totally__Unregistered", TOOLS_BY_NAME)
        self.assertEqual(
            _command_for_tool("Totally__Unregistered", {"command": "echo hi"}),
            "echo hi",
        )


# ---------------------------------------------------------------------------
# Timestamps, agent, and windowing
# ---------------------------------------------------------------------------


class TestTimestampsAgentWindowing(_IsolatedHomeMixin, unittest.TestCase):
    """Timestamp parsing, agent attribution, sorting, and date windowing."""

    def test_timestamp_is_naive_local(self):
        """
        Given the same instant written two ways, as UTC '...Z' and as +02:00
        When both are harvested
        Then both yield the same naive (tz-free) datetime, which is only true
        if each was converted to local time before its tzinfo was dropped.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-p.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "as-utc"},
                    "use-bash-10",
                ),
                _assistant_tool_use(
                    "2026-06-20T12:00:00.000+02:00",
                    "Bash",
                    {"command": "as-offset"},
                    "use-bash-11",
                ),
            ],
        )
        by_command = {e.command: e.timestamp for e in harvest_transcript_file(path)}
        self.assertEqual(set(by_command), {"as-utc", "as-offset"})
        self.assertIsNone(by_command["as-utc"].tzinfo)
        self.assertIsNone(by_command["as-offset"].tzinfo)
        self.assertEqual(by_command["as-utc"], by_command["as-offset"])

    def test_sidechain_attributed_to_subagent(self):
        """
        Given an assistant entry flagged isSidechain True
        When harvested
        Then its entry's agent is 'subagent'.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-q.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "pwd"},
                    "use-bash-12",
                    is_sidechain=True,
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-12", False, "ok"
                ),
            ],
        )
        self.assertEqual(harvest_transcript_file(path)[0].agent, "subagent")

    def test_non_sidechain_attributed_to_main(self):
        """
        Given an assistant entry with isSidechain False
        When harvested
        Then its entry's agent is 'main'.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-r.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "pwd"},
                    "use-bash-13",
                    is_sidechain=False,
                ),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z", "use-bash-13", False, "ok"
                ),
            ],
        )
        self.assertEqual(harvest_transcript_file(path)[0].agent, "main")

    def test_entry_without_a_parseable_timestamp_is_dropped(self):
        """
        Given two Bash uses, one with no timestamp and one with an unparseable one
        When harvested
        Then neither reaches the corpus -- an entry with no time cannot be
        windowed or ordered, so it is dropped rather than dated arbitrarily.
        """
        missing = _assistant_tool_use(
            None, "Bash", {"command": "no-timestamp"}, "use-bash-14"
        )
        del missing["timestamp"]
        unparseable = _assistant_tool_use(
            "not-a-timestamp", "Bash", {"command": "bad-timestamp"}, "use-bash-15"
        )
        path = _write_transcript(self.tmpdir, "session-s.jsonl", [missing, unparseable])
        self.assertEqual(harvest_transcript_file(path), [])

    def test_since_filters_old_entries_and_sorts(self):
        """
        Given one out-of-window (2020) and two in-window Bash uses, all written
        newest-first
        When harvested with since=2025-01-01
        Then the 2020 entry is gone and the two survivors come back
        oldest-first, not in file order.
        """
        _write_transcript(
            self.tmpdir,
            "session-t.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "newest"},
                    "use-bash-16",
                ),
                _assistant_tool_use(
                    "2025-03-05T10:00:00.000Z",
                    "Bash",
                    {"command": "middle"},
                    "use-bash-17",
                ),
                _assistant_tool_use(
                    "2020-01-01T10:00:00.000Z",
                    "Bash",
                    {"command": "ancient"},
                    "use-bash-18",
                ),
            ],
        )
        corpus = harvest_transcripts(self.tmpdir, since=date(2025, 1, 1))
        self.assertEqual([e.command for e in corpus], ["middle", "newest"])

    def test_entry_dated_exactly_on_the_floor_is_kept(self):
        """
        Given a Bash use dated exactly the 'since' day
        When harvested with that day as the floor
        Then it is kept -- the floor is inclusive.
        """
        _write_transcript(
            self.tmpdir,
            "session-u.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T00:30:00.000Z",
                    "Bash",
                    {"command": "on-the-floor"},
                    "use-bash-19",
                )
            ],
        )
        on_floor = harvest_transcript_file(self.tmpdir / "session-u.jsonl")[0]
        corpus = harvest_transcripts(self.tmpdir, since=on_floor.timestamp.date())
        self.assertEqual([e.command for e in corpus], ["on-the-floor"])

    def test_max_age_days_excludes_old(self):
        """
        Given a clearly-old (2020) Bash use
        When harvested with max_age_days=1
        Then it is excluded from the corpus.
        """
        _write_transcript(
            self.tmpdir,
            "session-v.jsonl",
            [
                _assistant_tool_use(
                    "2020-01-01T10:00:00.000Z",
                    "Bash",
                    {"command": "old"},
                    "use-bash-20",
                ),
                _user_tool_result(
                    "2020-01-01T10:00:01.000Z", "use-bash-20", False, "ok"
                ),
            ],
        )
        self.assertEqual(harvest_transcripts(self.tmpdir, max_age_days=1), [])

    def test_the_later_of_since_and_max_age_wins(self):
        """
        Given a Bash use from 2026 and a since of 2020 with max_age_days=1
        When harvested
        Then the max-age floor, being the later one, drops it -- a permissive
        'since' cannot widen a narrow max_age_days.
        """
        _write_transcript(
            self.tmpdir,
            "session-w.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "last-june"},
                    "use-bash-21",
                )
            ],
        )
        corpus = harvest_transcripts(
            self.tmpdir, since=date(2020, 1, 1), max_age_days=1
        )
        self.assertEqual(corpus, [])

    def test_recent_entry_within_window_kept(self):
        """
        Given a Bash use timestamped today
        When harvested with max_age_days=7
        Then it is kept.
        """
        now_iso = (datetime.now() - timedelta(minutes=1)).astimezone().isoformat()
        _write_transcript(
            self.tmpdir,
            "session-x.jsonl",
            [
                _assistant_tool_use(
                    now_iso, "Bash", {"command": "recent"}, "use-bash-22"
                ),
                _user_tool_result(now_iso, "use-bash-22", False, "ok"),
            ],
        )
        corpus = harvest_transcripts(self.tmpdir, max_age_days=7)
        self.assertEqual([e.command for e in corpus], ["recent"])

    def test_entries_from_several_files_are_merged_oldest_first(self):
        """
        Given two transcript files whose alphabetical order is the reverse of
        their entries' chronological order
        When the directory is harvested
        Then the merged corpus is ordered by timestamp, not by file name, and
        each entry still names the file it came from.
        """
        newer = _write_transcript(
            self.tmpdir,
            "aaa-newer.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-21T09:00:00.000Z",
                    "Bash",
                    {"command": "second"},
                    "use-bash-23",
                )
            ],
        )
        older = _write_transcript(
            self.tmpdir,
            "zzz-older.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T09:00:00.000Z",
                    "Bash",
                    {"command": "first"},
                    "use-bash-24",
                )
            ],
        )
        corpus = harvest_transcripts(self.tmpdir)
        self.assertEqual([e.command for e in corpus], ["first", "second"])
        self.assertEqual([e.log_file for e in corpus], [older, newer])


# ---------------------------------------------------------------------------
# Robustness and helpers
# ---------------------------------------------------------------------------


class TestRobustnessAndHelpers(_IsolatedHomeMixin, unittest.TestCase):
    """Graceful handling of bad input and the project-dir mapping."""

    def test_missing_directory_returns_empty(self):
        """
        Given a directory that does not exist
        When harvest_transcripts is called
        Then it returns an empty list rather than raising.
        """
        self.assertEqual(harvest_transcripts(self.tmpdir / "nope"), [])

    def test_unreadable_transcript_file_yields_no_entries(self):
        """
        Given a path ending in .jsonl that cannot be read as a file
        When harvest_transcript_file is called on it
        Then it returns an empty list rather than raising.
        """
        not_a_file = self.tmpdir / "session-y.jsonl"
        not_a_file.mkdir()
        self.assertEqual(harvest_transcript_file(not_a_file), [])

    def test_nothing_harvested_looks_the_same_however_it_failed(self):
        """
        Given four directories that yield nothing for four different reasons --
        empty, no .jsonl files, unparseable JSON, and valid JSON in a shape the
        harvester does not recognise
        When each is harvested
        Then all four return the same empty list: a harvest that read nothing
        is indistinguishable from one that read and rejected everything.
        """
        empty = self.tmpdir / "empty"
        empty.mkdir()

        wrong_suffix = self.tmpdir / "wrong-suffix"
        wrong_suffix.mkdir()
        _write_transcript(
            wrong_suffix,
            "session.json",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "never-seen"},
                    "use-bash-25",
                )
            ],
        )

        unparseable = self.tmpdir / "unparseable"
        unparseable.mkdir()
        (unparseable / "session.jsonl").write_text("{ not json at all\nalso not json\n")

        foreign_schema = self.tmpdir / "foreign-schema"
        foreign_schema.mkdir()
        (foreign_schema / "session.jsonl").write_text(
            json.dumps({"event": "tool_call", "tool": "Bash", "cmd": "ls"}) + "\n"
        )

        outcomes = [
            harvest_transcripts(d)
            for d in (empty, wrong_suffix, unparseable, foreign_schema)
        ]
        self.assertEqual(outcomes, [[], [], [], []])

    def test_malformed_lines_are_skipped(self):
        """
        Given a transcript file with a malformed JSON line among valid ones
        When harvested
        Then the valid tool use is still extracted with its status, and the
        bad line is ignored.
        """
        path = self.tmpdir / "session-z.jsonl"
        good_use = json.dumps(
            _assistant_tool_use(
                "2026-06-20T10:00:00.000Z", "Bash", {"command": "pwd"}, "use-bash-26"
            )
        )
        good_res = json.dumps(
            _user_tool_result("2026-06-20T10:00:01.000Z", "use-bash-26", False, "ok")
        )
        path.write_text(good_use + "\n{ this is not json\n" + good_res + "\n")
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command, "pwd")
        self.assertEqual(entries[0].status, "EXECUTED")

    def test_plain_text_messages_around_a_tool_call_are_ignored(self):
        """
        Given a transcript holding the ordinary traffic that surrounds a tool
        call -- user and assistant messages whose content is a string rather
        than a block list, and a tool_result item with no tool_use_id
        When harvested
        Then only the real tool call reaches the corpus, joined to its own
        result. String-content messages are the bulk of a real transcript, so
        the harvester must walk past them rather than trip on them.
        """
        path = _write_transcript(
            self.tmpdir,
            "session-za.jsonl",
            [
                {
                    "type": "user",
                    "timestamp": "2026-06-20T09:59:00.000Z",
                    "message": {"role": "user", "content": "please list /var"},
                },
                {
                    "type": "assistant",
                    "timestamp": "2026-06-20T09:59:30.000Z",
                    "message": {"role": "assistant", "content": "Sure, listing it."},
                },
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "ls -la /var"},
                    "use-bash-30",
                ),
                {
                    "type": "user",
                    "timestamp": "2026-06-20T10:00:01.000Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "is_error": True,
                                "content": "orphan",
                            }
                        ],
                    },
                },
                _user_tool_result(
                    "2026-06-20T10:00:02.000Z", "use-bash-30", False, "total 4"
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command, "ls -la /var")
        self.assertEqual(entries[0].status, "EXECUTED")

    def test_a_transcript_elsewhere_in_home_is_not_harvested(self):
        """
        Given a decoy transcript under the fake HOME's own .claude tree
        When a different directory is harvested
        Then nothing from the decoy appears -- the harvester reads only the
        directory it is handed.
        """
        decoy_dir = self.fake_home / ".claude" / "projects" / "-decoy"
        decoy_dir.mkdir(parents=True)
        _write_transcript(
            decoy_dir,
            "session.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Bash",
                    {"command": "decoy-command"},
                    "use-bash-27",
                )
            ],
        )
        wanted = self.tmpdir / "wanted"
        wanted.mkdir()
        _write_transcript(
            wanted,
            "session.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T11:00:00.000Z",
                    "Bash",
                    {"command": "wanted-command"},
                    "use-bash-28",
                )
            ],
        )
        self.assertEqual(
            [e.command for e in harvest_transcripts(wanted)], ["wanted-command"]
        )

    def test_transcript_dir_for_project_encodes_path(self):
        """
        Given a project directory and a fake claude home
        When transcript_dir_for_project is called
        Then the project's absolute path is encoded with '/' replaced by '-'.
        """
        result = transcript_dir_for_project(
            Path("/home/arnon/projects/toolguard"), claude_home=self.tmpdir
        )
        self.assertEqual(
            result, self.tmpdir / "projects" / "-home-arnon-projects-toolguard"
        )

    def test_claude_home_defaults_to_dot_claude_under_home(self):
        """
        Given no claude_home argument at all
        When transcript_dir_for_project is called
        Then the directory is resolved under ~/.claude, exercising the default
        that a caller passing the argument never reaches.
        """
        result = transcript_dir_for_project(Path("/srv/project"))
        self.assertEqual(
            result, self.fake_home / ".claude" / "projects" / "-srv-project"
        )

    def test_relative_project_dir_is_resolved_before_encoding(self):
        """
        Given a relative project directory and a foreign cwd
        When transcript_dir_for_project is called
        Then the encoded name is built from the absolute path, so two
        processes in different directories agree on one transcript directory.
        """
        workspace = self.tmpdir / "workspace"
        (workspace / "proj").mkdir(parents=True)
        self.chdir_to(workspace)
        expected = str((workspace / "proj").resolve()).replace("/", "-")
        result = transcript_dir_for_project(Path("proj"), claude_home=self.tmpdir)
        self.assertEqual(result, self.tmpdir / "projects" / expected)


class TestExtractText(unittest.TestCase):
    """_extract_text flattens a tool_result content value into a single string."""

    def test_plain_string_passthrough(self):
        """
        Given a plain string content value
        When it is extracted
        Then the same string is returned
        """
        self.assertEqual(_extract_text("hello"), "hello")

    def test_list_of_text_blocks_joined(self):
        """
        Given a list of text block dicts
        When it is extracted
        Then their text fields are space-joined
        """
        content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        self.assertEqual(_extract_text(content), "a b")

    def test_non_dict_block_is_stringified(self):
        """
        Given a list containing a non-dict block
        When it is extracted
        Then that block is stringified into the result
        """
        self.assertEqual(_extract_text(["raw", {"text": "x"}]), "raw x")

    def test_dict_block_without_text_contributes_only_a_separator(self):
        """
        Given a list holding a text block, an image block with no text key, and
        a bare string
        When it is extracted
        Then the image block contributes an empty string rather than its repr,
        leaving a doubled separator.
        """
        content = [{"type": "text", "text": "hi"}, {"type": "image"}, "raw"]
        self.assertEqual(_extract_text(content), "hi  raw")

    def test_none_yields_empty_string(self):
        """
        Given a None content value
        When it is extracted
        Then an empty string is returned
        """
        self.assertEqual(_extract_text(None), "")

    def test_other_type_is_stringified(self):
        """
        Given a content value that is neither string, list, nor None
        When it is extracted
        Then it is stringified
        """
        self.assertEqual(_extract_text(42), "42")


if __name__ == "__main__":
    unittest.main()
