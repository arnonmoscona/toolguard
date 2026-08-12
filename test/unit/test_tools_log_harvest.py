"""Unit tests for toolguard.tools.log_harvest."""

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path


def _write_log(log_dir: Path, filename: str, content: str) -> Path:
    """Write a log file under log_dir and return its path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


_SIMPLE_EXECUTED = """\
## 2026-06-20 10:00:00

- **Status**: EXECUTED
- **Command**: `git status`
- **Matched Rule**: `git:*  [project: /proj/.claude/toolguard_hook.toml]`
- **Agent**: main

"""

_SIMPLE_REFUSED = """\
## 2026-06-20 10:01:00

- **Status**: REFUSED
- **Command**: `whoami`
- **Violated Rules**: `Command does not match any allow patterns`
- **Agent**: main

"""

_READ_ENTRY = """\
## 2026-06-20 10:02:00

- **Status**: EXECUTED
- **Command**: `Read(/home/arnon/projects/foo/file.py)`
- **Matched Rule**: `/home/arnon/projects/**`
- **Agent**: main

"""

_WRITE_ENTRY = """\
## 2026-06-20 10:03:00

- **Status**: EXECUTED
- **Command**: `Write(/home/arnon/projects/foo/newfile.py)`
- **Matched Rule**: `/home/arnon/projects/**`
- **Agent**: feature-coder

"""

_EDIT_ENTRY = """\
## 2026-06-20 10:04:00

- **Status**: EXECUTED
- **Command**: `Edit(/home/arnon/projects/foo/existing.py)`
- **Matched Rule**: `/home/arnon/projects/**`

"""

_DISCOVERY_ENTRY = """\
## 2026-06-20 10:05:00

- **Discovery**: discovered 2 config levels: project: /proj/.claude/toolguard_hook.toml, user: ~/.claude/toolguard_hook.toml

"""

_MALFORMED_NO_STATUS = """\
## 2026-06-20 10:06:00

- **Command**: `ls -la`
- **Agent**: main

"""

_MALFORMED_NO_COMMAND = """\
## 2026-06-20 10:07:00

- **Status**: EXECUTED
- **Agent**: main

"""

_MALFORMED_BAD_HEADER = """\
## not-a-date

- **Status**: EXECUTED
- **Command**: `ls`

"""


class TestParseSingleLogFile(unittest.TestCase):
    """Tests for log_harvest.parse_log_file()."""

    def test_parse_executed_bash_entry(self):
        """
        Given a log file with one EXECUTED Bash entry
        When parse_log_file is called
        Then one LogEntry is returned with status=EXECUTED, tool=Bash, correct command
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _SIMPLE_EXECUTED
            )
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        e = entries[0]
        self.assertEqual("EXECUTED", e.status)
        self.assertEqual("Bash", e.tool)
        self.assertEqual("git status", e.command)
        self.assertEqual("main", e.agent)
        self.assertIsNotNone(e.rule_text)
        self.assertIn("git:*", e.rule_text)

    def test_parse_refused_entry(self):
        """
        Given a log file with one REFUSED entry
        When parse_log_file is called
        Then one LogEntry is returned with status=REFUSED and rule_text from Violated Rules
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _SIMPLE_REFUSED
            )
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        e = entries[0]
        self.assertEqual("REFUSED", e.status)
        self.assertEqual("Bash", e.tool)
        self.assertEqual("whoami", e.command)
        self.assertIn("does not match any allow patterns", e.rule_text)

    def test_parse_read_file_tool_entry(self):
        """
        Given a log file with a Read(/path) command entry
        When parse_log_file is called
        Then a LogEntry is returned with tool='Read' and command='/home/arnon/projects/foo/file.py'
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(Path(tmpdir), "toolguard-2026-06-20.md", _READ_ENTRY)
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        e = entries[0]
        self.assertEqual("Read", e.tool)
        self.assertEqual("/home/arnon/projects/foo/file.py", e.command)

    def test_parse_write_file_tool_entry(self):
        """
        Given a log file with a Write(/path) command entry
        When parse_log_file is called
        Then a LogEntry is returned with tool='Write' and the correct path as command
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(Path(tmpdir), "toolguard-2026-06-20.md", _WRITE_ENTRY)
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        e = entries[0]
        self.assertEqual("Write", e.tool)
        self.assertEqual("/home/arnon/projects/foo/newfile.py", e.command)
        self.assertEqual("feature-coder", e.agent)

    def test_parse_edit_file_tool_entry(self):
        """
        Given a log file with an Edit(/path) command entry with no Agent field
        When parse_log_file is called
        Then a LogEntry is returned with tool='Edit' and agent=None
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(Path(tmpdir), "toolguard-2026-06-20.md", _EDIT_ENTRY)
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        e = entries[0]
        self.assertEqual("Edit", e.tool)
        self.assertIsNone(e.agent)

    def test_discovery_entries_are_skipped(self):
        """
        Given a log file containing only a Discovery section (no Status field)
        When parse_log_file is called
        Then zero LogEntry records are returned (Discovery sections are skipped)
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _DISCOVERY_ENTRY
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_malformed_no_status_is_skipped(self):
        """
        Given a log section with no Status field (only Command and Agent)
        When parse_log_file is called
        Then the section is silently skipped and zero entries are returned
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _MALFORMED_NO_STATUS
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_malformed_no_command_is_skipped(self):
        """
        Given a log section with no Command field
        When parse_log_file is called
        Then the section is silently skipped and zero entries are returned
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _MALFORMED_NO_COMMAND
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_malformed_bad_header_is_skipped(self):
        """
        Given a log section with an invalid date in the header
        When parse_log_file is called
        Then the section is silently skipped and zero entries are returned
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _MALFORMED_BAD_HEADER
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_multiple_sections_all_parsed(self):
        """
        Given a log file with four valid sections (mix of types)
        When parse_log_file is called
        Then all valid entries are returned and invalid ones are skipped
        """
        from toolguard.tools.log_harvest import parse_log_file

        content = _SIMPLE_EXECUTED + _SIMPLE_REFUSED + _DISCOVERY_ENTRY + _READ_ENTRY
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(Path(tmpdir), "toolguard-2026-06-20.md", content)
            entries = parse_log_file(log_path)

        self.assertEqual(3, len(entries))
        tools = [e.tool for e in entries]
        self.assertIn("Bash", tools)
        self.assertIn("Read", tools)

    def test_timestamp_is_parsed_correctly(self):
        """
        Given a log entry with timestamp '2026-06-20 10:00:00'
        When parse_log_file is called
        Then the LogEntry has timestamp equal to datetime(2026, 6, 20, 10, 0, 0)
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _SIMPLE_EXECUTED
            )
            entries = parse_log_file(log_path)

        self.assertEqual(datetime(2026, 6, 20, 10, 0, 0), entries[0].timestamp)

    def test_log_file_path_is_stored_on_entry(self):
        """
        Given a log file at a known path
        When parse_log_file is called
        Then each entry's log_file attribute points to that path
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _SIMPLE_EXECUTED
            )
            entries = parse_log_file(log_path)

        self.assertEqual(log_path, entries[0].log_file)


class TestHarvest(unittest.TestCase):
    """Tests for log_harvest.harvest()."""

    def _setup_log_dir(self, tmpdir: str, files: dict) -> Path:
        """Write multiple log files and return the logs dir."""
        logs_dir = Path(tmpdir) / "logs"
        logs_dir.mkdir()
        for filename, content in files.items():
            (logs_dir / filename).write_text(content, encoding="utf-8")
        return logs_dir

    def test_harvest_all_files_no_filter(self):
        """
        Given a logs directory with two daily log files
        When harvest is called with no time window arguments
        Then all entries from all files are returned in chronological order
        """
        from toolguard.tools.log_harvest import harvest

        day1_content = """\
## 2026-06-19 09:00:00

- **Status**: EXECUTED
- **Command**: `git log`
- **Matched Rule**: `git:*`
- **Agent**: main

"""
        day2_content = """\
## 2026-06-20 10:00:00

- **Status**: EXECUTED
- **Command**: `git status`
- **Matched Rule**: `git:*`
- **Agent**: main

"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-19.md": day1_content,
                    "toolguard-2026-06-20.md": day2_content,
                },
            )
            entries = harvest(logs_dir)

        self.assertEqual(2, len(entries))
        self.assertEqual(datetime(2026, 6, 19, 9, 0, 0), entries[0].timestamp)
        self.assertEqual(datetime(2026, 6, 20, 10, 0, 0), entries[1].timestamp)

    def test_harvest_with_since_filter(self):
        """
        Given two log files from different dates
        When harvest is called with since=date(2026, 6, 20)
        Then only entries from 2026-06-20 onward are returned
        """
        from toolguard.tools.log_harvest import harvest

        day1_content = """\
## 2026-06-19 09:00:00

- **Status**: EXECUTED
- **Command**: `git log`
- **Matched Rule**: `git:*`
- **Agent**: main

"""
        day2_content = """\
## 2026-06-20 10:00:00

- **Status**: EXECUTED
- **Command**: `git status`
- **Matched Rule**: `git:*`
- **Agent**: main

"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-19.md": day1_content,
                    "toolguard-2026-06-20.md": day2_content,
                },
            )
            entries = harvest(logs_dir, since=date(2026, 6, 20))

        self.assertEqual(1, len(entries))
        self.assertEqual("git status", entries[0].command)

    def test_harvest_with_max_age_days(self):
        """
        Given a very old log file and a recent one
        When harvest is called with max_age_days=1 (today only)
        Then only entries from today are returned
        """
        from datetime import date as d_cls
        from toolguard.tools.log_harvest import harvest

        today = d_cls.today()
        today_str = today.strftime("%Y-%m-%d")
        today_ts = today.strftime("%Y-%m-%d 12:00:00")

        today_content = f"""\
## {today_ts}

- **Status**: EXECUTED
- **Command**: `ls -la`
- **Matched Rule**: `ls:*`
- **Agent**: main

"""
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-01-01.md": _SIMPLE_EXECUTED,
                    f"toolguard-{today_str}.md": today_content,
                },
            )
            entries = harvest(logs_dir, max_age_days=0)

        self.assertEqual(1, len(entries))
        self.assertEqual("ls -la", entries[0].command)

    def test_harvest_ignores_non_log_files(self):
        """
        Given a logs directory with error/warning log files and a daily log file
        When harvest is called
        Then only toolguard-YYYY-MM-DD.md entries are included
        """
        from toolguard.tools.log_harvest import harvest

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-20.md": _SIMPLE_EXECUTED,
                    "toolguard-error-2026-06-20.md": _SIMPLE_EXECUTED,
                    "toolguard-warning-2026-06-20.md": _SIMPLE_EXECUTED,
                    "some-other.log": "## Not a log\n- **Status**: EXECUTED\n- **Command**: `ls`\n",
                },
            )
            entries = harvest(logs_dir)

        self.assertEqual(1, len(entries))
        self.assertEqual("git status", entries[0].command)

    def test_harvest_empty_directory(self):
        """
        Given an empty logs directory
        When harvest is called
        Then an empty list is returned without error
        """
        from toolguard.tools.log_harvest import harvest

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "logs"
            logs_dir.mkdir()
            entries = harvest(logs_dir)

        self.assertEqual([], entries)

    def test_harvest_nonexistent_directory(self):
        """
        Given a logs directory path that does not exist
        When harvest is called
        Then an empty list is returned without raising an exception
        """
        from toolguard.tools.log_harvest import harvest

        entries = harvest(Path("/nonexistent/logs/path/that/does/not/exist"))
        self.assertEqual([], entries)
