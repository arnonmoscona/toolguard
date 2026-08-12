"""
Transcript harvester: parse Claude Code conversation transcripts into the same
:class:`~toolguard.tools.log_harvest.LogEntry` records the daily-log harvester
produces, so one corpus can hold both sources.

Why transcripts as well as toolguard's own logs
-----------------------------------------------
- A transcript records what became of a tool-use prompt, including the user
  declining it. toolguard's own log records the decision toolguard returned,
  which for an ``ask`` is written before the user answers.
- A transcript also covers ungoverned calls, and says whether a call that ran
  actually succeeded.
- A project that has not been running toolguard has no toolguard log at all,
  so at cold start the transcript is the only history there is.

Transcript layout
-----------------
Claude Code stores one JSONL file per session under
``<claude_home>/projects/<encoded-project-path>/<session-id>.jsonl``, where the
project path is encoded by replacing ``/`` with ``-``.  Each line is a JSON
object.  ``message.content`` lists carry ``tool_use`` items (``name``, ``id``,
``input``) and ``tool_result`` items (``tool_use_id``, ``is_error``,
``content``); a top-level ``timestamp`` (ISO-8601, UTC) and ``isSidechain``
flag accompany each entry.
"""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toolguard.constants import (
    BUILTIN_TOOLS,
    STATUS_ERROR,
    STATUS_EXECUTED,
    STATUS_REFUSED,
    STATUS_UNKNOWN,
)
from toolguard.subagent import parse_jsonl_lines
from toolguard.tool_spec import TOOLS_BY_NAME
from toolguard.tools.log_harvest import LogEntry


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Lowercased substrings that mark a ``tool_result`` error as the user having
#: declined the prompt, rather than the tool itself having failed.
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

    Args:
        project_dir: The project's directory; resolved to an absolute path
            before encoding.
        claude_home: The Claude Code home directory (defaults to
            ``~/.claude``).

    Returns:
        ``<claude_home>/projects/<encoded>``. Existence is NOT checked.
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

    Transcript timestamps are UTC (``...Z``) and toolguard works in naive
    local time, so a tz-aware value is converted and its tzinfo dropped.

    Args:
        raw: The raw ``timestamp`` string, or ``None``.

    Returns:
        A naive local :class:`datetime`, or ``None`` when *raw* is missing or
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

    The content may be a plain string or a list of blocks, each typically
    ``{'type': 'text', 'text': ...}``. A block that is not a dict is
    stringified whole; a dict without a ``text`` key contributes nothing but
    its separator.

    Args:
        content: The ``content`` value from a ``tool_result`` item.

    Returns:
        A single space-joined string, possibly empty.
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
        Dict from tool_use id to ``(is_error, result_text)``. A repeated id
        keeps the last result seen.
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

    - No matching result -> ``UNKNOWN`` (interrupted, or still open).
    - Result with no error -> ``EXECUTED``.
    - Error text carrying a :data:`_REJECTION_MARKERS` substring -> ``REFUSED``.
    - Any other error -> ``ERROR`` (the call ran and the tool failed).

    Args:
        tool_use_id: The id of the tool use; ``None`` classifies as
            ``UNKNOWN``.
        results: The index produced by :func:`_index_tool_results`.

    Returns:
        ``(status, reason)``, where *reason* is the result text trimmed to its
        first 200 characters for REFUSED and ERROR, and ``None`` otherwise.
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
    Pull a tool call's subject -- its command line or file path -- from its input.

    Args:
        tool: A registered tool name, whose
            :class:`~toolguard.tool_spec.ToolSpec` names the input key to
            read.
        tool_input: The ``input`` dict of the ``tool_use`` item.

    Returns:
        That key's value, or ``None`` when it is absent, not a string, or
        blank.
    """
    spec = TOOLS_BY_NAME.get(tool)
    key = spec.payload_key if spec else "command"
    value = tool_input.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


# ---------------------------------------------------------------------------
# Per-file and directory harvesting
# ---------------------------------------------------------------------------


def harvest_transcript_file(path: Path) -> List[LogEntry]:
    """
    Parse a single transcript JSONL file into :class:`LogEntry` records.

    One entry per ``tool_use`` item naming a tool in
    :data:`~toolguard.constants.BUILTIN_TOOLS` -- the four tools governed by
    default, a narrower set than the tools toolguard recognises. Each is
    joined to its ``tool_result`` for a status; items with no parseable
    timestamp or no command/path are dropped.

    Args:
        path: Path to a ``*.jsonl`` transcript file.

    Returns:
        The file's entries, unsorted. ``rule_text`` carries the result snippet
        of a REFUSED or ERROR entry and is ``None`` otherwise. A file that
        cannot be read yields an empty list.
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
            if tool not in BUILTIN_TOOLS:
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
    Harvest every ``*.jsonl`` transcript in a directory into one corpus.

    Args:
        transcripts_dir: Directory of transcript files, e.g. from
            :func:`transcript_dir_for_project`.
        since: Drop entries dated before this day.
        max_age_days: Drop entries dated before ``today - max_age_days``,
            against the local date. Given both, the later floor applies;
            given neither, nothing is dropped.

    Returns:
        The surviving entries, sorted by timestamp, oldest first. A missing or
        unreadable directory yields an empty list.
    """
    today = date.today()
    floor: Optional[date] = since
    if max_age_days is not None:
        age_floor = today - timedelta(days=max_age_days)
        if floor is None or age_floor > floor:
            floor = age_floor

    try:
        files = [
            c for c in transcripts_dir.iterdir() if c.is_file() and c.suffix == ".jsonl"
        ]
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
