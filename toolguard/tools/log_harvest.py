"""
Log harvester for toolguard daily log files.

Parses ``toolguard-YYYY-MM-DD.md`` resolution logs into :class:`LogEntry`
records.

Log file format (one Markdown section per event)::

    ## 2026-06-23 10:27:35

    - **Status**: EXECUTED
    - **Command**: `ls -la`
    - **Matched Rule**: `ls:*`
    - **Provenance**: project: /p/.claude/toolguard_hook.toml
    - **Agent**: main

    ## 2026-06-23 10:27:35

    - **Status**: REFUSED
    - **Command**: `whoami`
    - **Violated Rules**: `Command does not match any allow patterns`
    - **Agent**: main

A file-tool entry carries a ``Tool(path)`` command field instead::

    - **Command**: `Read(/abs/path/to/file)`
    - **Matched Rule**: `~/projects/**`

Only ``Status``, ``Command``, ``Matched Rule``, ``Violated Rules`` and
``Agent`` are read; every other field, ``Provenance`` among them, is ignored,
and a section with no ``Status`` field is skipped entirely.

Robustness
----------
A section that does not parse -- unreadable heading, no ``Status``, no
``Command`` -- is skipped rather than raised on, so one bad log day still
yields the rest of the corpus.  An unrecognised status is not a parse failure:
``status`` keeps whatever string the log holds. A section that has a
``Status`` field but still can't be turned into an entry is reported via
:func:`toolguard.error_reporter.report_warning` before being dropped, so the
loss is never silent; a header-less or ``Status``-less fragment (a Discovery
section, or a tail left by an embedded ``## `` line splitting a section) is
not reported, since it never was a lost entry.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, List, Optional

from toolguard import error_reporter
from toolguard.constants import FILE_TOOLS
from toolguard.log_writer import unescape_command_field


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

#: Splits a ``ToolName(target)`` command field into its name and target.
_TOOL_WRAPPER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\((.+)\)$", re.DOTALL)

#: A section heading: ``## YYYY-MM-DD HH:MM:SS``.
_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")

_STATUS_RE = re.compile(r"^\s*-\s+\*\*Status\*\*:\s+(.+)$")
_COMMAND_RE = re.compile(r"^\s*-\s+\*\*Command\*\*:\s+`(.+)`$", re.DOTALL)
_MATCHED_RULE_RE = re.compile(r"^\s*-\s+\*\*Matched Rule\*\*:\s+`(.+)`$", re.DOTALL)
#: The Violated Rules field's line, captured whole -- see
#: :func:`_parse_violated_rules` for why the individual rules are extracted
#: separately rather than by one greedy backtick-to-backtick capture.
_VIOLATED_RULES_RE = re.compile(r"^\s*-\s+\*\*Violated Rules\*\*:\s+(.+)$")
#: One backtick-fenced rule within a Violated Rules line.
_BACKTICKED_ITEM_RE = re.compile(r"`([^`]*)`")
_AGENT_RE = re.compile(r"^\s*-\s+\*\*Agent\*\*:\s+(.+)$")

#: Names a daily resolution log. Deliberately narrow -- the error, warning
#: and conflict logs share the ``toolguard-`` prefix but not this shape.
_LOG_NAME_RE = re.compile(r"^toolguard-(\d{4}-\d{2}-\d{2})\.md$")


@dataclass(frozen=True)
class LogEntry:
    """
    One event in a harvested corpus.

    The field notes describe a daily-log section, the source this module
    parses.

    Attributes:
        timestamp: Event time, from the section header. Naive, local.
        tool: ``'Read'``, ``'Write'`` or ``'Edit'`` for a ``ToolName(path)``
            command field; ``'Bash'`` for anything else, including a wrapper
            naming some other tool.
        command: The command string, or the path for a file-tool entry.
        status: The status string as the log holds it, unrecognised values
            included.
        rule_text: ``Matched Rule`` when the section has one, else
            ``Violated Rules``, else ``None``.
        agent: The ``Agent`` field -- ``'main'`` or a subagent's name -- or
            ``None`` when absent.
        log_file: The file this entry was parsed from.
    """

    timestamp: datetime
    tool: str
    command: str
    status: str
    rule_text: Optional[str]
    agent: Optional[str]
    log_file: Optional[Path]


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_command_field(raw: str):
    """
    Split the ``Command`` field into ``(tool, command_or_path)``.

    A ``Read(/abs/path)``-shaped field yields that file tool and its path.
    Anything else -- including a wrapper naming a tool that is not a file
    tool -- yields ``'Bash'`` and the whole field text as the command.

    Args:
        raw: The ``Command`` field's content, backticks already stripped.

    Returns:
        A ``(tool, target)`` tuple.
    """
    m = _TOOL_WRAPPER_RE.match(raw.strip())
    if m:
        tool_name = m.group(1)
        inner = m.group(2).strip()
        if tool_name in FILE_TOOLS:
            return tool_name, inner
        return "Bash", raw.strip()
    return "Bash", raw.strip()


def _parse_violated_rules(raw: str) -> str:
    """
    Extract a Violated Rules line's rule bodies, dropping the backtick fences
    and ``, `` separator log_writer renders between multiple rules.

    Args:
        raw: The line's text after the ``**Violated Rules**:`` label.

    Returns:
        The rule bodies joined by ``", "``, or *raw* stripped if it holds no
        backtick-fenced item.
    """
    items = _BACKTICKED_ITEM_RE.findall(raw)
    return ", ".join(items) if items else raw.strip()


def _parse_section(lines: List[str], log_file: Optional[Path]) -> Optional[LogEntry]:
    """
    Parse one Markdown section into a :class:`LogEntry`.

    Args:
        lines: The section's lines, its ``## timestamp`` header first.
        log_file: Recorded on the entry as its origin.

    Returns:
        A :class:`LogEntry`, or ``None`` when the section has no parseable
        header, no ``Status`` field, or no ``Command`` field. A section that
        has a ``Status`` field but still can't yield an entry is reported via
        :func:`toolguard.error_reporter.report_warning` before returning
        ``None`` -- see the module docstring's Robustness section. A section
        with no ``Status`` (e.g. a Discovery section, or a header-less
        fragment produced when an embedded ``## `` line inside a command
        splits the section) is not a loss and is not reported.
    """
    if not lines:
        return None

    header_match = _HEADER_RE.match(lines[0].rstrip())
    if not header_match:
        return None
    try:
        timestamp = datetime.strptime(header_match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    status: Optional[str] = None
    command_raw: Optional[str] = None
    matched_rule: Optional[str] = None
    violated_rules: Optional[str] = None
    agent: Optional[str] = None

    for line in lines[1:]:
        stripped = line.rstrip()
        m = _STATUS_RE.match(stripped)
        if m:
            status = m.group(1).strip()
            continue
        m = _COMMAND_RE.match(stripped)
        if m:
            command_raw = m.group(1)
            continue
        m = _MATCHED_RULE_RE.match(stripped)
        if m:
            matched_rule = m.group(1)
            continue
        m = _VIOLATED_RULES_RE.match(stripped)
        if m:
            violated_rules = _parse_violated_rules(m.group(1))
            continue
        m = _AGENT_RE.match(stripped)
        if m:
            agent = m.group(1).strip()

    if status is None:
        return None
    if command_raw is None:
        # A Status field with no readable Command -- e.g. a multi-line or
        # heading-split command (see log_writer.escape_command_field) written
        # before escaping existed. The entry is unrecoverable here; make the
        # loss visible instead of dropping it silently.
        error_reporter.report_warning(
            "log harvester could not recover the Command field of the section"
            f" at {header_match.group(1)} in {log_file}",
            "Check the raw log file near this timestamp -- a Markdown heading"
            " or raw newline inside a multi-line command can split the section.",
        )
        return None

    tool, command = _parse_command_field(unescape_command_field(command_raw))
    rule_text = matched_rule if matched_rule is not None else violated_rules

    return LogEntry(
        timestamp=timestamp,
        tool=tool,
        command=command,
        status=status,
        rule_text=rule_text,
        agent=agent,
        log_file=log_file,
    )


def _iter_sections(text: str) -> Iterator[List[str]]:
    """
    Split *text* into ``## ``-delimited sections.

    Args:
        text: A log file's full text.

    Yields:
        Lists of lines, one per section. Anything before the first ``## ``
        heading is yielded as a leading, header-less list.
    """
    current: List[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                yield current
            current = [line]
        else:
            current.append(line)
    if current:
        yield current


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_log_file(log_path: Path) -> List[LogEntry]:
    """
    Parse one daily log file into :class:`LogEntry` records.

    Args:
        log_path: Path to a ``toolguard-YYYY-MM-DD.md`` log file.

    Returns:
        The file's parseable entries, in the order they appear; sections that
        do not parse are skipped, so the list may be empty.

    Raises:
        OSError: The file cannot be opened or read.
    """
    entries: List[LogEntry] = []
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for section_lines in _iter_sections(text):
        entry = _parse_section(section_lines, log_path)
        if entry is not None:
            entries.append(entry)
    return entries


def _log_date(log_path: Path) -> Optional[date]:
    """
    The date encoded in a ``toolguard-YYYY-MM-DD.md`` file name, or ``None``
    for any other name.
    """
    m = _LOG_NAME_RE.match(log_path.name)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def harvest(
    logs_dir: Path,
    since: Optional[date] = None,
    max_age_days: Optional[int] = None,
) -> List[LogEntry]:
    """
    Parse every daily log file in *logs_dir* into a corpus.

    Only ``toolguard-YYYY-MM-DD.md`` names are read (see :data:`_LOG_NAME_RE`).

    Args:
        logs_dir: Directory holding the daily log files.
        since: Drop entries dated before this day.
        max_age_days: Drop entries dated before ``today - max_age_days``,
            against the local date. Given both, the later floor applies;
            given neither, nothing is dropped.

    Returns:
        The surviving entries, files in file-name date order and each file's
        entries in the order they appear. An unreadable *logs_dir* yields an
        empty list, and an individual file that cannot be read is skipped.
    """
    # Log timestamps are naive local time, so the rolling window is measured
    # against the local date.
    today = date.today()

    floor: Optional[date] = since
    if max_age_days is not None:
        age_floor = today - timedelta(days=max_age_days)
        if floor is None or age_floor > floor:
            floor = age_floor

    log_files: List[Path] = []
    try:
        for child in logs_dir.iterdir():
            if not child.is_file():
                continue
            log_date = _log_date(child)
            if log_date is None:
                continue
            if floor is not None and log_date < floor:
                continue
            log_files.append(child)
    except OSError:
        return []

    log_files.sort(key=lambda p: _log_date(p) or date.min)

    entries: List[LogEntry] = []
    for log_path in log_files:
        try:
            file_entries = parse_log_file(log_path)
        except OSError:
            continue
        if floor is not None:
            floor_dt = datetime(floor.year, floor.month, floor.day)
            file_entries = [e for e in file_entries if e.timestamp >= floor_dt]
        entries.extend(file_entries)

    return entries
