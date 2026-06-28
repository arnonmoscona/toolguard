"""
Transcript harvester: parse Claude Code conversation transcripts into the SAME
:class:`~toolguard.tools.log_harvest.LogEntry` corpus shape as the daily-log
harvester, so :mod:`~toolguard.tools.replay`, ``redundancy``, and ``consolidate``
operate on it unchanged.

Why transcripts (vs toolguard's own logs)
-----------------------------------------
- toolguard's daily logs capture only GOVERNED tool calls plus the decision
  toolguard made.
- Transcripts additionally capture:
  * permission REJECTIONS -- the user declined a tool-use prompt (the ASK->deny
    resolution), the core signal for suggesting new rules;
  * ungoverned / failed commands and richer surrounding context.
- For a NEW toolguard user (cold start) or an auto-mode user there are NO
  toolguard logs at all -- the transcript is the ONLY governance history, which
  makes this harvester a prerequisite for onboarding/migration as well as
  ongoing maintenance.

Transcript layout
-----------------
Claude Code stores one JSONL file per session under
``~/.claude/projects/<encoded-project-path>/<session-id>.jsonl``, where the
project path is encoded by replacing ``/`` with ``-``.  Each line is a JSON
object; assistant messages carry ``message.content`` lists that may contain
``tool_use`` items (``name``, ``id``, ``input``), and user messages carry
``tool_result`` items (``tool_use_id``, ``is_error``, ``content``).  A top-level
``timestamp`` (ISO-8601, UTC) and ``isSidechain`` flag accompany each entry.

Reuse: :func:`toolguard.subagent.parse_jsonl_lines` for JSONL parsing.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toolguard.constants import (
    FILE_TOOLS,
    GOVERNED_TOOLS,
    STATUS_ERROR,
    STATUS_EXECUTED,
    STATUS_REFUSED,
    STATUS_UNKNOWN,
)
from toolguard.subagent import parse_jsonl_lines
from toolguard.tools.log_harvest import LogEntry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Lowercased substrings that identify a USER permission rejection (an ASK->deny
# resolution) in a tool_result error, as opposed to an ordinary tool error.
_REJECTION_MARKERS = (
    "doesn't want to proceed",
    "tool use was rejected",
    "user doesn't want",
)


# ---------------------------------------------------------------------------
# Project -> transcript directory mapping
# ---------------------------------------------------------------------------


def transcript_dir_for_project(
    project_dir: Path, claude_home: Optional[Path] = None
) -> Path:
    """
    Return the Claude Code transcript directory for a project.

    Claude Code encodes the absolute project path by replacing ``/`` with ``-``
    and stores session JSONL files under
    ``<claude_home>/projects/<encoded>/``.

    Args:
        project_dir: The project's directory (resolved to an absolute path).
        claude_home: The Claude Code home directory (defaults to ``~/.claude``).

    Returns:
        The directory expected to contain the project's ``*.jsonl`` transcripts.
        Existence is NOT checked.
    """
    home = claude_home or (Path.home() / ".claude")
    encoded = str(project_dir.resolve()).replace("/", "-")
    return home / "projects" / encoded


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO-8601 transcript timestamp into a naive LOCAL datetime.

    Transcript timestamps are UTC (``...Z``).  toolguard works in local time
    throughout (the daily-log harvester emits naive local datetimes), so a
    tz-aware timestamp is converted to the local zone and stripped of tzinfo to
    match.

    Args:
        raw: The raw ``timestamp`` string, or ``None``.

    Returns:
        A naive local :class:`datetime`, or ``None`` when ``raw`` is missing or
        unparseable.
    """
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _extract_text(content: Any) -> str:
    """
    Flatten a ``tool_result`` content value into a single string.

    The content may be a plain string or a list of block dicts (each typically
    ``{'type': 'text', 'text': ...}``).  Non-text blocks are stringified.

    Args:
        content: The ``content`` value from a ``tool_result`` item.

    Returns:
        A single concatenated string (possibly empty).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        return " ".join(parts)
    if content is None:
        return ""
    return str(content)


def _index_tool_results(entries: List[Dict[str, Any]]) -> Dict[str, Tuple[bool, str]]:
    """
    Map every ``tool_use_id`` to its ``(is_error, text)`` result.

    Args:
        entries: Parsed transcript entries.

    Returns:
        Dict from tool_use id to a ``(is_error, result_text)`` tuple.  Later
        results win if an id somehow repeats.
    """
    results: Dict[str, Tuple[bool, str]] = {}
    for entry in entries:
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_result":
                continue
            tool_use_id = item.get("tool_use_id")
            if not tool_use_id:
                continue
            results[tool_use_id] = (
                bool(item.get("is_error")),
                _extract_text(item.get("content")),
            )
    return results


def _status_and_reason(
    tool_use_id: Optional[str], results: Dict[str, Tuple[bool, str]]
) -> Tuple[str, Optional[str]]:
    """
    Derive the observed status and an optional reason for a tool use.

    Classification:
    - No matching result          -> ``UNKNOWN`` (interrupted / still open).
    - Result with no error        -> ``EXECUTED``.
    - Error matching a rejection  -> ``REFUSED`` (user declined the prompt).
    - Any other error             -> ``ERROR`` (permitted but the tool failed).

    Args:
        tool_use_id: The id of the tool use (may be ``None``).
        results: The index produced by :func:`_index_tool_results`.

    Returns:
        ``(status, reason)`` where ``reason`` is a truncated result snippet for
        REFUSED/ERROR entries and ``None`` otherwise.
    """
    found = results.get(tool_use_id) if tool_use_id else None
    if found is None:
        return STATUS_UNKNOWN, None
    is_error, text = found
    if not is_error:
        return STATUS_EXECUTED, None
    lowered = text.lower()
    if any(marker in lowered for marker in _REJECTION_MARKERS):
        return STATUS_REFUSED, text.strip()[:200]
    return STATUS_ERROR, text.strip()[:200]


def _command_for_tool(tool: str, tool_input: Dict[str, Any]) -> Optional[str]:
    """
    Extract the command (Bash) or file path (Read/Write/Edit) from a tool input.

    Args:
        tool: Governed tool name.
        tool_input: The ``input`` dict of the tool_use item.

    Returns:
        The command string or file path, or ``None`` when it is missing/empty.
    """
    if tool in FILE_TOOLS:
        value = tool_input.get("file_path")
    else:
        value = tool_input.get("command")
    if isinstance(value, str) and value.strip():
        return value
    return None


# ---------------------------------------------------------------------------
# Per-file and directory harvesting
# ---------------------------------------------------------------------------


def harvest_transcript_file(path: Path) -> List[LogEntry]:
    """
    Parse a single transcript JSONL file into :class:`LogEntry` records.

    Walks the assistant ``tool_use`` items for governed tools, joins each to its
    ``tool_result`` (for status), and emits one entry per governed tool use that
    has a parseable timestamp and a non-empty command/path.

    Args:
        path: Path to a ``*.jsonl`` transcript file.

    Returns:
        List of :class:`LogEntry` records (unsorted).  A file that cannot be read
        yields an empty list.
    """
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []

    entries = parse_jsonl_lines(lines)
    results = _index_tool_results(entries)

    harvested: List[LogEntry] = []
    for entry in entries:
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue

        timestamp = _parse_timestamp(entry.get("timestamp"))
        if timestamp is None:
            continue
        agent = "subagent" if entry.get("isSidechain") else "main"

        for item in content:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            tool = item.get("name")
            if tool not in GOVERNED_TOOLS:
                continue
            tool_input = item.get("input")
            if not isinstance(tool_input, dict):
                continue
            command = _command_for_tool(tool, tool_input)
            if command is None:
                continue

            status, reason = _status_and_reason(item.get("id"), results)
            harvested.append(
                LogEntry(
                    timestamp=timestamp,
                    tool=tool,
                    command=command,
                    status=status,
                    rule_text=reason,
                    agent=agent,
                    log_file=path,
                )
            )

    return harvested


def harvest_transcripts(
    transcripts_dir: Path,
    since: Optional[date] = None,
    max_age_days: Optional[int] = None,
) -> List[LogEntry]:
    """
    Harvest all transcripts in a directory into a time-bounded corpus.

    Mirrors :func:`toolguard.tools.log_harvest.harvest`: every ``*.jsonl`` file in
    ``transcripts_dir`` is parsed, entries are filtered by a floor date, and the
    result is sorted by timestamp (oldest first).

    Time window
    -----------
    ``since`` (a floor date) and ``max_age_days`` (a rolling window relative to
    today's local date) both cap the corpus; when both are given the later floor
    wins.  Unlike daily logs, transcript files are not per-day, so the floor is
    applied per ENTRY (by its timestamp), not per file.

    Args:
        transcripts_dir: Directory of ``*.jsonl`` transcript files (e.g. from
            :func:`transcript_dir_for_project`).
        since: Only include entries on or after this date.
        max_age_days: Only include entries from the last N calendar days.

    Returns:
        List of :class:`LogEntry` records sorted by timestamp.  A missing or
        unreadable directory yields an empty list.
    """
    today = date.today()
    floor: Optional[date] = since
    if max_age_days is not None:
        age_floor = today - timedelta(days=max_age_days)
        if floor is None or age_floor > floor:
            floor = age_floor

    try:
        files = [c for c in transcripts_dir.iterdir() if c.is_file() and c.suffix == ".jsonl"]
    except OSError:
        return []

    entries: List[LogEntry] = []
    for path in sorted(files):
        for entry in harvest_transcript_file(path):
            if floor is not None and entry.timestamp.date() < floor:
                continue
            entries.append(entry)

    entries.sort(key=lambda e: e.timestamp)
    return entries
