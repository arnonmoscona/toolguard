"""
Log harvester for toolguard daily log files.

Parses ``logs/toolguard-YYYY-MM-DD.md`` files into a structured corpus of
:class:`LogEntry` records.  Each entry captures the timestamp, tool, command or
file path, observed status, matched/violated rule text, and agent identifier.

Log file format (one Markdown section per event)::

    ## 2026-06-23 10:27:35

    - **Status**: EXECUTED
    - **Command**: `ls -la`
    - **Matched Rule**: `ls:*  [explicit: /path/to/config]`
    - **Agent**: main

    ## 2026-06-23 10:27:35

    - **Status**: REFUSED
    - **Command**: `whoami`
    - **Violated Rules**: `Command does not match any allow patterns`
    - **Agent**: main

File-tool entries use a ``Tool(path)`` command shape::

    ## ...
    - **Status**: EXECUTED
    - **Command**: `Read(/abs/path/to/file)`
    - **Matched Rule**: `~/projects/**  [project: ...]`
    - **Agent**: main

Discovery and conflict entries are silently skipped (they have no ``Status``
field in the same format).

Robustness
----------
Malformed sections (missing fields, bad dates, unknown status values, etc.) are
silently skipped rather than raising exceptions so that a bad log day does not
prevent harvesting the rest of the corpus.  The ``status`` field preserves the
raw string value from the log so unknown statuses pass through as-is.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator, List, Optional

from toolguard.constants import FILE_TOOLS


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

# Pattern to detect and parse ``ToolName(...)`` command forms in the log.
_TOOL_WRAPPER_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\((.+)\)$", re.DOTALL)

# Header line format: ``## YYYY-MM-DD HH:MM:SS``
_HEADER_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})$")

# Field extractors -- each matches a ``- **Key**: `value` `` bullet
_STATUS_RE = re.compile(r"^\s*-\s+\*\*Status\*\*:\s+(.+)$")
_COMMAND_RE = re.compile(r"^\s*-\s+\*\*Command\*\*:\s+`(.+)`$", re.DOTALL)
_MATCHED_RULE_RE = re.compile(r"^\s*-\s+\*\*Matched Rule\*\*:\s+`(.+)`$", re.DOTALL)
_VIOLATED_RULES_RE = re.compile(r"^\s*-\s+\*\*Violated Rules\*\*:\s+`(.+)`$", re.DOTALL)
_AGENT_RE = re.compile(r"^\s*-\s+\*\*Agent\*\*:\s+(.+)$")

# Log file name pattern: toolguard-YYYY-MM-DD.md
_LOG_NAME_RE = re.compile(r"^toolguard-(\d{4}-\d{2}-\d{2})\.md$")


@dataclass(frozen=True)
class LogEntry:
    """
    A single parsed event from a toolguard daily log file.

    Attributes:
        timestamp: The datetime of the event (parsed from the section header).
        tool: Tool name (``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``, or
            the raw tool name if not recognised).
        command: For Bash entries, the raw command string; for file-tool entries,
            the absolute file path extracted from the ``ToolName(path)`` wrapper.
        status: Observed status string from the log.  Common values are
            ``'EXECUTED'`` and ``'REFUSED'``; other values are preserved as-is.
        rule_text: Matched rule text (for EXECUTED entries) or violated-rules
            text (for REFUSED entries), or ``None`` when the field is absent.
        agent: Agent identifier string (e.g. ``'main'``, ``'feature-coder'``), or
            ``None`` when the ``Agent`` field is absent.
        log_file: The log file this entry was parsed from (for diagnostics).
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
    Parse the raw command field into ``(tool, command_or_path)``.

    File-tool entries look like ``Read(/abs/path)``; Bash entries are raw
    command strings.

    Args:
        raw: The raw content of the ``Command`` field (backtick-stripped).

    Returns:
        A ``(tool, target)`` tuple where ``tool`` is e.g. ``'Bash'`` or
        ``'Read'`` and ``target`` is the command string or file path.
    """
    m = _TOOL_WRAPPER_RE.match(raw.strip())
    if m:
        tool_name = m.group(1)
        inner = m.group(2).strip()
        if tool_name in FILE_TOOLS:
            return tool_name, inner
        # Unrecognised wrapper -- treat as Bash with the raw text as command
        return "Bash", raw.strip()
    return "Bash", raw.strip()


def _parse_section(lines: List[str], log_file: Optional[Path]) -> Optional[LogEntry]:
    """
    Parse a single Markdown section into a :class:`LogEntry`.

    A section is a list of lines starting with the ``## timestamp`` header line.
    Returns ``None`` for Discovery/conflict entries and malformed sections.

    Args:
        lines: The lines of one Markdown section (including the header).
        log_file: Path to the log file (for the ``log_file`` attribute).

    Returns:
        A :class:`LogEntry` or ``None`` when the section should be skipped.
    """
    if not lines:
        return None

    # Parse header
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
            violated_rules = m.group(1)
            continue
        m = _AGENT_RE.match(stripped)
        if m:
            agent = m.group(1).strip()

    # Skip sections without a Status field (Discovery, conflict, etc.)
    if status is None:
        return None
    # Skip sections without a Command field
    if command_raw is None:
        return None

    tool, command = _parse_command_field(command_raw)
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
    Iterate over Markdown sections (``## ...`` delimited) in ``text``.

    Each section is a list of lines starting with the ``##`` header and
    continuing until the next ``##`` header or end of text.

    Args:
        text: Full text content of a log file.

    Yields:
        Lists of lines, one per section.
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
    Parse a single daily log file into a list of :class:`LogEntry` records.

    Silently skips Discovery/conflict sections and malformed entries.  The
    returned list preserves the chronological order of the entries in the file.

    Args:
        log_path: Path to a ``toolguard-YYYY-MM-DD.md`` log file.

    Returns:
        List of :class:`LogEntry` records (may be empty).

    Raises:
        OSError: If the file cannot be opened/read.
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
    Extract the date from a log file name (``toolguard-YYYY-MM-DD.md``).

    Args:
        log_path: Path to a log file.

    Returns:
        The date encoded in the file name, or ``None`` for non-matching names.
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
    Parse all applicable daily log files in ``logs_dir`` into a corpus.

    Only ``toolguard-YYYY-MM-DD.md`` files are processed; error logs, warning
    logs, and other files are ignored.  Files are processed in chronological
    order so that the returned corpus is sorted by timestamp.

    Time window
    -----------
    The caller can cap the corpus size with ``since`` (a floor date) or
    ``max_age_days`` (a rolling window relative to today).  When both are
    given, the more restrictive floor wins (the later of the two).  When
    neither is given, all available log files are harvested.

    Args:
        logs_dir: Directory containing ``toolguard-YYYY-MM-DD.md`` files.
        since: Only include entries on or after this date.
        max_age_days: Only include entries from the last N calendar days
            (relative to today's local date).

    Returns:
        List of :class:`LogEntry` records sorted by timestamp (oldest first).
        Malformed log files are skipped; malformed individual sections within
        a file are also skipped.
    """
    # toolguard is a desktop tool and works in LOCAL time throughout (log
    # timestamps are naive/local), so "today" is the local date.
    today = date.today()

    # Resolve the effective floor date
    floor: Optional[date] = since
    if max_age_days is not None:
        age_floor = today - timedelta(days=max_age_days)
        if floor is None or age_floor > floor:
            floor = age_floor

    # Discover and sort log files chronologically
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
        # Apply per-entry timestamp filtering (the date filter above is file-level;
        # the very first and last files may contain entries outside the window)
        if floor is not None:
            floor_dt = datetime(floor.year, floor.month, floor.day)
            file_entries = [e for e in file_entries if e.timestamp >= floor_dt]
        entries.extend(file_entries)

    return entries
