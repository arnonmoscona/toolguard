"""
Unit tests for toolguard.tools.transcript_harvest -- harvesting Claude Code
conversation transcripts into the shared LogEntry corpus shape.

Tests cover:
- Bash tool_use -> EXECUTED / REFUSED / ERROR / UNKNOWN status derivation.
- File-tool (Write) uses input.file_path as the command/target.
- Non-governed tools are skipped.
- Timestamps are parsed to naive local datetimes; corpus is time-sorted.
- since / max_age_days windowing.
- isSidechain -> 'subagent' agent attribution.
- Missing directory and malformed lines are handled gracefully.
- transcript_dir_for_project path encoding.
"""

import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.transcript_harvest import (
    _extract_text,
    harvest_transcript_file,
    harvest_transcripts,
    transcript_dir_for_project,
)


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


class _TempDirMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmpdir = Path(self._tmp.name)


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------


class TestStatusDerivation(_TempDirMixin, unittest.TestCase):
    """tool_use joined to its tool_result yields the right observed status."""

    def test_executed_when_result_not_error(self):
        """
        Given a Bash tool_use whose tool_result has is_error False
        When the file is harvested
        Then one EXECUTED LogEntry is produced with the command and no reason.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "ls -la"}, "t1"),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "total 0"),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertIsInstance(e, LogEntry)
        self.assertEqual((e.tool, e.command, e.status), ("Bash", "ls -la", "EXECUTED"))
        self.assertIsNone(e.rule_text)

    def test_refused_when_user_rejects_prompt(self):
        """
        Given a Bash tool_use whose result error says the user rejected the prompt
        When harvested
        Then the entry status is REFUSED and the rejection text is kept as the reason.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "rm -rf /"}, "t1"),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z",
                    "t1",
                    True,
                    "The user doesn't want to proceed with this tool use. The tool use was rejected.",
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].status, "REFUSED")
        self.assertIn("doesn't want to proceed", entries[0].rule_text)

    def test_error_when_tool_fails_but_not_rejected(self):
        """
        Given a tool_use whose result is an ordinary tool error (not a rejection)
        When harvested
        Then the status is ERROR (permitted but failed), not REFUSED.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2026-06-20T10:00:00.000Z", "Write", {"file_path": "/x"}, "t1"),
                _user_tool_result(
                    "2026-06-20T10:00:01.000Z",
                    "t1",
                    True,
                    "<tool_use_error>File has not been read yet.</tool_use_error>",
                ),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(entries[0].status, "ERROR")

    def test_unknown_when_no_matching_result(self):
        """
        Given a tool_use with no corresponding tool_result in the transcript
        When harvested
        Then the entry status is UNKNOWN.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [_assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "pwd"}, "t1")],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual(entries[0].status, "UNKNOWN")


# ---------------------------------------------------------------------------
# Tool extraction
# ---------------------------------------------------------------------------


class TestToolExtraction(_TempDirMixin, unittest.TestCase):
    """Governed tools are extracted with the right command/target; others skipped."""

    def test_file_tool_uses_file_path(self):
        """
        Given an Edit tool_use with input.file_path
        When harvested
        Then the entry's tool is 'Edit' and command is the file path.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z",
                    "Edit",
                    {"file_path": "/abs/foo.py", "old_string": "a", "new_string": "b"},
                    "t1",
                ),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "ok"),
            ],
        )
        entries = harvest_transcript_file(path)
        self.assertEqual((entries[0].tool, entries[0].command), ("Edit", "/abs/foo.py"))

    def test_non_governed_tool_skipped(self):
        """
        Given a tool_use for a non-governed tool (an MCP tool)
        When harvested
        Then it produces no LogEntry.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z", "mcp__basic-memory__search", {"query": "x"}, "t1"
                ),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "ok"),
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
            "s.jsonl",
            [_assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"description": "x"}, "t1")],
        )
        self.assertEqual(harvest_transcript_file(path), [])


# ---------------------------------------------------------------------------
# Timestamps, agent, and windowing
# ---------------------------------------------------------------------------


class TestTimestampsAgentWindowing(_TempDirMixin, unittest.TestCase):
    """Timestamp parsing, agent attribution, sorting, and date windowing."""

    def test_timestamp_is_naive_local(self):
        """
        Given a UTC ('...Z') transcript timestamp
        When harvested
        Then the entry timestamp is a naive (tz-free) datetime.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "pwd"}, "t1"),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "ok"),
            ],
        )
        ts = harvest_transcript_file(path)[0].timestamp
        self.assertIsInstance(ts, datetime)
        self.assertIsNone(ts.tzinfo)

    def test_sidechain_attributed_to_subagent(self):
        """
        Given an assistant entry flagged isSidechain True
        When harvested
        Then its entry's agent is 'subagent'.
        """
        path = _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use(
                    "2026-06-20T10:00:00.000Z", "Bash", {"command": "pwd"}, "t1", is_sidechain=True
                ),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "ok"),
            ],
        )
        self.assertEqual(harvest_transcript_file(path)[0].agent, "subagent")

    def test_since_filters_old_entries_and_sorts(self):
        """
        Given a transcript with an old (2020) and a recent (2026) Bash use, out of order
        When harvested with since=2025-01-01
        Then only the 2026 entry remains, and the corpus is timestamp-sorted.
        """
        _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "new"}, "t2"),
                _user_tool_result("2026-06-20T10:00:01.000Z", "t2", False, "ok"),
                _assistant_tool_use("2020-01-01T10:00:00.000Z", "Bash", {"command": "old"}, "t1"),
                _user_tool_result("2020-01-01T10:00:01.000Z", "t1", False, "ok"),
            ],
        )
        corpus = harvest_transcripts(self.tmpdir, since=date(2025, 1, 1))
        self.assertEqual([e.command for e in corpus], ["new"])

    def test_max_age_days_excludes_old(self):
        """
        Given a clearly-old (2020) Bash use
        When harvested with max_age_days=1
        Then it is excluded from the corpus.
        """
        _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use("2020-01-01T10:00:00.000Z", "Bash", {"command": "old"}, "t1"),
                _user_tool_result("2020-01-01T10:00:01.000Z", "t1", False, "ok"),
            ],
        )
        self.assertEqual(harvest_transcripts(self.tmpdir, max_age_days=1), [])

    def test_recent_entry_within_window_kept(self):
        """
        Given a Bash use timestamped today
        When harvested with max_age_days=7
        Then it is kept.
        """
        now_iso = (datetime.now() - timedelta(minutes=1)).astimezone().isoformat()
        _write_transcript(
            self.tmpdir,
            "s.jsonl",
            [
                _assistant_tool_use(now_iso, "Bash", {"command": "recent"}, "t1"),
                _user_tool_result(now_iso, "t1", False, "ok"),
            ],
        )
        corpus = harvest_transcripts(self.tmpdir, max_age_days=7)
        self.assertEqual([e.command for e in corpus], ["recent"])


# ---------------------------------------------------------------------------
# Robustness and helpers
# ---------------------------------------------------------------------------


class TestRobustnessAndHelpers(_TempDirMixin, unittest.TestCase):
    """Graceful handling of bad input and the project-dir mapping."""

    def test_missing_directory_returns_empty(self):
        """
        Given a directory that does not exist
        When harvest_transcripts is called
        Then it returns an empty list rather than raising.
        """
        self.assertEqual(harvest_transcripts(self.tmpdir / "nope"), [])

    def test_malformed_lines_are_skipped(self):
        """
        Given a transcript file with a malformed JSON line among valid ones
        When harvested
        Then the valid tool use is still extracted and the bad line is ignored.
        """
        path = self.tmpdir / "s.jsonl"
        good_use = json.dumps(
            _assistant_tool_use("2026-06-20T10:00:00.000Z", "Bash", {"command": "pwd"}, "t1")
        )
        good_res = json.dumps(_user_tool_result("2026-06-20T10:00:01.000Z", "t1", False, "ok"))
        path.write_text(good_use + "\n{ this is not json\n" + good_res + "\n")
        entries = harvest_transcript_file(path)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].command, "pwd")

    def test_transcript_dir_for_project_encodes_path(self):
        """
        Given a project directory and a fake claude home
        When transcript_dir_for_project is called
        Then the project's absolute path is encoded with '/' replaced by '-'.
        """
        result = transcript_dir_for_project(
            Path("/home/arnon/projects/toolguard"), claude_home=self.tmpdir
        )
        self.assertEqual(result, self.tmpdir / "projects" / "-home-arnon-projects-toolguard")


class TestExtractText(unittest.TestCase):
    """
    _extract_text flattens a tool_result content value (string, list of blocks,
    None, or other) into a single string.
    """

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
