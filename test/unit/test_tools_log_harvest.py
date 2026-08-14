"""Unit tests for toolguard.tools.log_harvest."""

import io
import tempfile
import unittest
import warnings
from contextlib import contextmanager, redirect_stderr
from datetime import date, datetime
from pathlib import Path
from typing import Iterator, List
from unittest.mock import MagicMock, patch

from toolguard import error_reporter


def _write_log(log_dir: Path, filename: str, content: str) -> Path:
    """Write a log file under log_dir and return its path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def _frozen_date(year: int, month: int, day: int):
    """
    A ``date`` subclass whose ``today()`` is fixed, for patching
    ``log_harvest.date``. Keeps ``fromisoformat``/``min``, which the module
    also uses, so only the clock is replaced.
    """

    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return date(year, month, day)

    return _FrozenDate


class _FixedOrderDir:
    """
    Stands in for a logs directory, yielding its real children in a fixed
    order. ``harvest`` uses nothing but ``iterdir()``, so this pins file
    ordering independently of the filesystem's own (which is arbitrary --
    measured returning 18, 21, 20, 19 for files created 19, 20, 21, 18).
    """

    def __init__(self, real_dir: Path, names: List[str]):
        self._children = [real_dir / name for name in names]

    def iterdir(self) -> Iterator[Path]:
        return iter(self._children)


@contextmanager
def _capture_reader_output() -> Iterator[List[str]]:
    """
    Capture every channel the harvester could report a problem through: the
    active ``Reporter``, Python warnings, and stderr. Yields a list, filled
    on exit with one string per signal.

    Deliberately channel-agnostic: the contract under test is that a loss is
    *not silent*, and pinning one channel would prejudge how that is fixed.
    """
    signals: List[str] = []
    reporter = MagicMock(spec=error_reporter.Reporter)
    stderr = io.StringIO()
    with (
        error_reporter.active(reporter),
        warnings.catch_warnings(record=True) as caught,
        redirect_stderr(stderr),
    ):
        warnings.simplefilter("always")
        yield signals
    signals.extend(f"{name}{args}" for name, args, _ in reporter.method_calls)
    signals.extend(str(w.message) for w in caught)
    if stderr.getvalue().strip():
        signals.append(stderr.getvalue().strip())


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

#: A header the regex accepts but the calendar rejects (Feb 30th).
_CALENDAR_INVALID_HEADER = """\
## 2026-02-30 10:00:00

- **Status**: EXECUTED
- **Command**: `ls`

"""

_HEADER_WITH_TRAILING_TEXT = """\
## 2026-06-20 10:08:00 -- backup note

- **Status**: EXECUTED
- **Command**: `ls`

"""

_NON_FILE_TOOL_WRAPPER = """\
## 2026-06-20 10:09:00

- **Status**: EXECUTED
- **Command**: `Task(run the audit)`
- **Matched Rule**: `Task:*`

"""

_BOTH_RULE_FIELDS = """\
## 2026-06-20 10:10:00

- **Status**: EXECUTED
- **Command**: `git push`
- **Matched Rule**: `git:*`
- **Violated Rules**: `git push*`

"""

#: Two rules, rendered the way log_writer renders a multi-rule violation.
_MULTI_RULE_VIOLATION = """\
## 2026-06-20 10:11:00

- **Status**: REFUSED
- **Command**: `rm -rf /`
- **Violated Rules**: `rm -rf *`, `sudo *`

"""

#: A disclosure block plus a two-line command: the '#' lines are the shape
#: that would also split the section if the split test were '#' rather than
#: '## ' (3,544 such lines in this repo's logs, measured 2026-08-13).
_MULTILINE_COMMAND_TEXT = (
    "# INTENT: back up the settings file before editing it\n"
    "# TOUCHES: reads settings.json; WRITES ~/.toolguard/backups/\n"
    "mkdir -p ~/.toolguard/backups\n"
    "cp settings.json ~/.toolguard/backups/settings.json.bak"
)

#: A multi-line command, written exactly as log_writer emits one: raw
#: newlines between the backticks. 1,856 sections of this repo's own logs
#: take this shape (measured 2026-08-13).
_MULTILINE_COMMAND = f"""\
## 2026-06-20 10:12:00

- **Status**: ASK
- **Command**: `{_MULTILINE_COMMAND_TEXT}`
- **Matched Rule**: `mkdir:*`
- **Agent**: main

"""

_HEREDOC_COMMAND_TEXT = "git commit -F - <<'EOF'\n## Release notes\nEOF"

#: A command carrying a Markdown heading -- the shape that splits a section
#: in two, leaving a head with no closing backtick and a tail with no Status.
_HEREDOC_WITH_HEADING = f"""\
## 2026-06-20 10:13:00

- **Status**: ASK
- **Command**: `{_HEREDOC_COMMAND_TEXT}`
- **Agent**: main

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

    def test_calendar_invalid_timestamp_is_skipped(self):
        """
        Given a header the timestamp regex accepts but the calendar rejects
            ('2026-02-30 10:00:00')
        When parse_log_file is called
        Then the section is skipped and no exception escapes
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _CALENDAR_INVALID_HEADER
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_a_heading_with_trailing_text_is_not_an_entry_heading(self):
        """
        Given a '## <timestamp> -- backup note' heading above Status and Command lines
        When parse_log_file is called
        Then no entry is produced, because an entry heading is the timestamp and
            nothing else
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _HEADER_WITH_TRAILING_TEXT
            )
            entries = parse_log_file(log_path)

        self.assertEqual(0, len(entries))

    def test_a_non_file_tool_wrapper_is_treated_as_a_bash_command(self):
        """
        Given a 'Task(run the audit)' command field -- a wrapper naming a tool
            that is not a file tool
        When parse_log_file is called
        Then tool is 'Bash' and the whole wrapper text is the command
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _NON_FILE_TOOL_WRAPPER
            )
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        self.assertEqual("Bash", entries[0].tool)
        self.assertEqual("Task(run the audit)", entries[0].command)

    def test_matched_rule_wins_over_violated_rules(self):
        """
        Given a section carrying both a Matched Rule and a Violated Rules field
        When parse_log_file is called
        Then rule_text is the Matched Rule
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _BOTH_RULE_FIELDS
            )
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        self.assertEqual("git:*", entries[0].rule_text)

    def test_a_multi_rule_violated_rules_line_is_not_mangled(self):
        """
        Given a Violated Rules line listing two rules, as log_writer renders them
        When parse_log_file is called
        Then rule_text carries the rule bodies without the separator and inner
            backticks embedded in it
        """
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(
                Path(tmpdir), "toolguard-2026-06-20.md", _MULTI_RULE_VIOLATION
            )
            entries = parse_log_file(log_path)

        self.assertEqual(1, len(entries))
        rule_text = entries[0].rule_text
        self.assertIn("rm -rf *", str(rule_text))
        self.assertIn("sudo *", str(rule_text))
        self.assertNotIn("`", rule_text)

    def test_multiple_sections_all_parsed(self):
        """
        Given a log file with four sections, three of them valid (mix of types)
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

    def _entry(self, day: int, command: str, hour: int = 10) -> str:
        """One EXECUTED section dated 2026-06-<day> at <hour>:00:00."""
        return (
            f"## 2026-06-{day:02d} {hour:02d}:00:00\n\n"
            "- **Status**: EXECUTED\n"
            f"- **Command**: `{command}`\n"
            "- **Matched Rule**: `x:*`\n\n"
        )

    def test_harvest_with_max_age_days(self):
        """
        Given log files for today, yesterday and the day before, with 'today'
            frozen at 2026-06-20
        When harvest is called with max_age_days=1
        Then today's and yesterday's entries are returned and the older one is
            dropped -- the floor is today minus one day, not today
        """
        from toolguard.tools import log_harvest

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-18.md": self._entry(18, "too old"),
                    "toolguard-2026-06-19.md": self._entry(19, "yesterday"),
                    "toolguard-2026-06-20.md": self._entry(20, "today"),
                },
            )
            with patch.object(log_harvest, "date", _frozen_date(2026, 6, 20)):
                entries = log_harvest.harvest(logs_dir, max_age_days=1)

        self.assertEqual(["yesterday", "today"], [e.command for e in entries])

    def test_since_and_max_age_days_resolve_to_whichever_floor_is_later(self):
        """
        Given log files for 2026-06-18, -19 and -20, with 'today' frozen at
            2026-06-20
        When harvest is called with since and max_age_days in each order of
            strictness
        Then the later of the two floors applies in both directions
        """
        from toolguard.tools import log_harvest

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-18.md": self._entry(18, "d18"),
                    "toolguard-2026-06-19.md": self._entry(19, "d19"),
                    "toolguard-2026-06-20.md": self._entry(20, "d20"),
                },
            )
            with patch.object(log_harvest, "date", _frozen_date(2026, 6, 20)):
                # max_age floor 2026-06-19 is later than since=2026-06-18.
                age_wins = log_harvest.harvest(
                    logs_dir, since=date(2026, 6, 18), max_age_days=1
                )
                # since=2026-06-20 is later than the max_age floor 2026-06-18.
                since_wins = log_harvest.harvest(
                    logs_dir, since=date(2026, 6, 20), max_age_days=2
                )

        self.assertEqual(["d19", "d20"], [e.command for e in age_wins])
        self.assertEqual(["d20"], [e.command for e in since_wins])

    def test_files_dated_outside_the_window_are_not_read(self):
        """
        Given log files for 2026-06-19 and 2026-06-20
        When harvest is called with since=2026-06-20
        Then only the in-window file is read -- the window is applied to file
            names before any file is opened
        """
        from toolguard.tools import log_harvest

        read: list = []
        real_parse = log_harvest.parse_log_file

        def spy(path):
            read.append(path.name)
            return real_parse(path)

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {
                    "toolguard-2026-06-19.md": self._entry(19, "d19"),
                    "toolguard-2026-06-20.md": self._entry(20, "d20"),
                },
            )
            with patch.object(log_harvest, "parse_log_file", spy):
                entries = log_harvest.harvest(logs_dir, since=date(2026, 6, 20))

        # The in-window name proves the spy is on the path harvest actually takes.
        self.assertEqual(["toolguard-2026-06-20.md"], read)
        self.assertEqual(["d20"], [e.command for e in entries])

    def test_a_directory_with_a_log_shaped_name_is_not_read(self):
        """
        Given a logs directory holding a real log file and a DIRECTORY named
            toolguard-2026-06-21.md
        When harvest is called
        Then only the real file is read and its entries are returned
        """
        from toolguard.tools import log_harvest

        read: list = []
        real_parse = log_harvest.parse_log_file

        def spy(path):
            read.append(path.name)
            return real_parse(path)

        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir, {"toolguard-2026-06-20.md": self._entry(20, "d20")}
            )
            (logs_dir / "toolguard-2026-06-21.md").mkdir()
            with patch.object(log_harvest, "parse_log_file", spy):
                entries = log_harvest.harvest(logs_dir)

        self.assertEqual(["toolguard-2026-06-20.md"], read)
        self.assertEqual(["d20"], [e.command for e in entries])

    def test_an_entry_dated_before_the_floor_is_dropped_from_an_in_window_file(self):
        """
        Given a file named toolguard-2026-06-20.md holding one section dated
            2026-06-19 23:50 and one dated 2026-06-20 10:00
        When harvest is called with since=2026-06-20
        Then only the 2026-06-20 entry is returned -- the window is applied to
            entry timestamps too, not only to file names
        """
        from toolguard.tools.log_harvest import harvest

        content = self._entry(19, "before midnight", hour=23) + self._entry(
            20, "after midnight"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(tmpdir, {"toolguard-2026-06-20.md": content})
            entries = harvest(logs_dir, since=date(2026, 6, 20))

        self.assertEqual(["after midnight"], [e.command for e in entries])

    def test_files_are_ordered_by_their_name_date_not_by_directory_order(self):
        """
        Given four log files the directory presents in an order that is neither
            sorted nor reverse-sorted
        When harvest is called
        Then entries come back oldest-first
        """
        from toolguard.tools.log_harvest import harvest

        days = [18, 19, 20, 21]
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = self._setup_log_dir(
                tmpdir,
                {f"toolguard-2026-06-{d}.md": self._entry(d, f"d{d}") for d in days},
            )
            # Neither order nor its reverse, so no-sort and reverse-sort both fail.
            shuffled = [f"toolguard-2026-06-{d}.md" for d in (20, 18, 21, 19)]
            entries = harvest(_FixedOrderDir(logs_dir, shuffled))

        self.assertEqual(["d18", "d19", "d20", "d21"], [e.command for e in entries])

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


class TestUnparseableInputIsNotSilent(unittest.TestCase):
    """
    What the reader does with input it cannot parse.

    Measured against this repository's own ``logs/`` on 2026-08-13: 1,856 of
    49,665 sections carry a Status or Command field and yield no entry. The
    fix may land in the writer or in the reader (TOO-45 proposed ticket 51);
    either way a loss must not be silent, which is what these assert.
    """

    def _parse(self, content: str):
        """Parse one log file's text; return (entries, reported signals)."""
        from toolguard.tools.log_harvest import parse_log_file

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = _write_log(Path(tmpdir), "toolguard-2026-06-20.md", content)
            with _capture_reader_output() as signals:
                entries = parse_log_file(log_path)
        return entries, signals

    def _assert_recovered_or_reported(self, content: str, expected_command: str):
        """The entry comes back intact, or its loss is reported. Never neither."""
        entries, signals = self._parse(content)
        if entries:
            self.assertEqual([expected_command], [e.command for e in entries])
        else:
            self.assertTrue(
                signals,
                "the entry was dropped and nothing was reported on any channel",
            )

    def test_a_multiline_command_is_recovered_or_its_loss_reported(self):
        """
        Given a section whose Command field holds a three-line command, written
            with raw newlines the way log_writer emits one
        When parse_log_file is called
        Then the command comes back intact, or the loss is reported
        """
        self._assert_recovered_or_reported(_MULTILINE_COMMAND, _MULTILINE_COMMAND_TEXT)

    def test_a_command_containing_a_markdown_heading_is_recovered_or_reported(self):
        """
        Given a section whose Command field holds a heredoc containing a '## '
            line, which splits the section in two
        When parse_log_file is called
        Then the command comes back intact, or the loss is reported
        """
        self._assert_recovered_or_reported(_HEREDOC_WITH_HEADING, _HEREDOC_COMMAND_TEXT)

    def test_a_lost_entry_is_reported_but_a_discovery_section_is_not(self):
        """
        Given a log file holding a Discovery section, an entry the reader cannot
            parse and a valid entry
        When parse_log_file is called
        Then the valid entry survives, the unparseable one is recovered or
            reported, and a file with no losses reports nothing -- a Discovery
            section is a different record type, not a loss (7,014 of them in
            this repo's logs)
        """
        lossy_entries, lossy_signals = self._parse(
            _DISCOVERY_ENTRY + _MULTILINE_COMMAND + _SIMPLE_EXECUTED
        )
        clean_entries, clean_signals = self._parse(_DISCOVERY_ENTRY + _SIMPLE_EXECUTED)

        self.assertEqual(["git status"], [e.command for e in clean_entries])
        self.assertEqual([], clean_signals, "a Discovery section is not a loss")
        recovered = [e.command for e in lossy_entries]
        self.assertIn("git status", recovered, "the neighbouring entry was lost too")
        if _MULTILINE_COMMAND_TEXT not in recovered:
            self.assertTrue(
                lossy_signals,
                "an entry that could not be parsed was dropped without a word",
            )
