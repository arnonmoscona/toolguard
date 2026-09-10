"""Unit tests for toolguard.observability.auto_mode_trace: the auto-mode trace writer."""

import json
import unittest
from datetime import datetime
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.observability.auto_mode_trace import (
    AutoModeTraceEntry,
    FALLBACK_CAUSE_NO_MATCH,
    log_auto_mode_trace,
)


def _entry(**overrides):
    """An :class:`AutoModeTraceEntry` with every field defaulted, one override at a time."""
    fields = {
        "tool_name": "Bash",
        "target": "whoami",
        "decision": "ask",
        "fallback_cause": FALLBACK_CAUSE_NO_MATCH,
        "permission_mode": "auto",
        "session_id": "sess-1",
        "cwd": "/p",
        "agent_info": "main",
    }
    fields.update(overrides)
    return AutoModeTraceEntry(**fields)


class TestLogAutoModeTraceWritesJsonl(unittest.TestCase):
    """log_auto_mode_trace appends one JSON object per line to a dated file."""

    def test_entry_is_appended_as_one_json_line_to_a_dated_file(self):
        """
        Given an AutoModeTraceEntry and a real, writable log directory
        When log_auto_mode_trace writes it
        Then a toolguard-automode-<today>.jsonl file is created under that
            directory holding exactly one line, and that line parses as
            JSON carrying every field of the entry
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_auto_mode_trace(_entry(), log_dir)

            expected_name = (
                f"toolguard-automode-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
            )
            log_file = log_dir / expected_name
            self.assertTrue(log_file.exists())

            lines = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["tool_name"], "Bash")
            self.assertEqual(record["target"], "whoami")
            self.assertEqual(record["decision"], "ask")
            self.assertEqual(record["fallback_cause"], FALLBACK_CAUSE_NO_MATCH)
            self.assertEqual(record["permission_mode"], "auto")
            self.assertEqual(record["session_id"], "sess-1")
            self.assertEqual(record["cwd"], "/p")
            self.assertEqual(record["agent_info"], "main")
            self.assertIn("timestamp", record)

    def test_two_entries_append_as_two_separate_lines(self):
        """
        Given two AutoModeTraceEntry writes to the same log directory on the same day
        When log_auto_mode_trace is called twice
        Then the dated file holds exactly two lines, each independently
            parseable as JSON and preserving write order
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            log_auto_mode_trace(_entry(target="cmd-one"), log_dir)
            log_auto_mode_trace(_entry(target="cmd-two"), log_dir)

            log_files = list(log_dir.glob("toolguard-automode-*.jsonl"))
            self.assertEqual(len(log_files), 1)
            lines = log_files[0].read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["target"], "cmd-one")
            self.assertEqual(json.loads(lines[1])["target"], "cmd-two")

    def test_log_dir_is_created_if_missing(self):
        """
        Given a log_dir that does not exist yet
        When log_auto_mode_trace is called
        Then the directory is created and the entry is written into it
        """
        with TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "nested" / "logs"
            log_auto_mode_trace(_entry(), log_dir)
            self.assertTrue(log_dir.is_dir())
            self.assertEqual(len(list(log_dir.glob("toolguard-automode-*.jsonl"))), 1)

    def test_none_log_dir_is_a_silent_no_op(self):
        """
        Given log_dir=None
        When log_auto_mode_trace is called
        Then nothing is written and no exception is raised
        """
        log_auto_mode_trace(_entry(), None)


class TestLogAutoModeTraceNeverRaises(unittest.TestCase):
    """A write failure is swallowed, matching every other toolguard log writer."""

    def test_a_write_failure_is_swallowed_not_raised(self):
        """
        Given a log_dir path that is actually an existing FILE, so creating
            a directory there fails
        When log_auto_mode_trace is called
        Then log_auto_mode_trace returns normally (no exception propagates)
            and a warning reaches stderr
        """
        with TemporaryDirectory() as tmpdir:
            blocking_file = Path(tmpdir) / "not-a-directory"
            blocking_file.write_text(
                "occupies the path log_auto_mode_trace wants as a directory"
            )

            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                log_auto_mode_trace(_entry(), blocking_file)

            self.assertIn("Warning", mock_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
