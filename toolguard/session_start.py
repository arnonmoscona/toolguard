"""
Toolguard SessionStart Hook for Claude Code.

This hook runs at the start of every Claude Code session and surfaces any
configuration conflicts that are present so the agent (and user) become aware
of them immediately. Claude Code injects SessionStart stdout directly into the
session context, so printing a summary here makes it visible to the agent.

Two sources of conflict are checked:

1. **Static conflicts** (recomputed live): ``config.takeover_mode().conflict``
   detects a cross-level disagreement on ``takeover_mode.enabled`` in real time.
   The check self-clears when the configuration is fixed -- no stale state.

2. **Dynamic conflicts** (previously recorded): the conflict log file(s) in
   ``logs/toolguard-conflict-YYYY-MM-DD.md`` accumulate allow-over-deny overrides
   that can only be detected at tool-use time (when an actual command is evaluated).
   The most recent file with recorded entries is surfaced here.

The hook nags every session while conflicts remain. There is no deduplication
marker: persistent nagging is intentional to encourage resolution.

Input: JSON via stdin (SessionStart shape -- ``hook_event_name``, ``cwd``,
       ``session_id``; NO ``tool_name`` / ``tool_input`` fields).
Output: A short conflict summary on stdout when conflicts exist; nothing otherwise.
Exit code: Always 0 (a SessionStart hook must never block the session).
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from toolguard.config import load_configuration


def _parse_session_start_input() -> dict:
    """
    Parse the SessionStart JSON payload from stdin.

    The SessionStart payload has ``hook_event_name``, ``session_id``, and ``cwd``
    but does NOT have ``tool_name`` or ``tool_input``. This parser is intentionally
    lenient: it falls back gracefully on missing or malformed input rather than
    raising, because a broken SessionStart hook must never block a session.

    Returns:
        Parsed JSON data as a dictionary, or an empty dict on failure.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _recent_conflict_logs(log_dir: Path) -> list:
    """
    Return existing ``toolguard-conflict-*.md`` files, most recent first.

    Sorts by filename descending; a lexicographic sort on the date suffix is
    correct because dates are in ``YYYY-MM-DD`` ISO format. Returns an empty list
    when ``log_dir`` does not exist or contains no conflict log files.

    Args:
        log_dir: Directory to search for conflict log files.

    Returns:
        List of conflict-log Paths, most recent first (possibly empty).
    """
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("toolguard-conflict-*.md"), reverse=True)


def _count_conflict_entries(log_file: Path) -> int:
    """
    Count the number of conflict entries recorded in a conflict log file.

    Each entry written by :func:`toolguard.error_log.log_conflict` begins with a
    Markdown heading of the form ``## YYYY-MM-DD HH:MM:SS - CONFLICT``. Counting
    lines that match this pattern gives the entry count without a full parse.

    Args:
        log_file: Path to a ``toolguard-conflict-*.md`` file.

    Returns:
        Number of entries found, or 0 if the file cannot be read.
    """
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return sum(
                1 for line in f if line.startswith("## ") and "- CONFLICT" in line
            )
    except Exception:
        return 0


def _check_dynamic_conflicts(log_dir: Optional[Path]):
    """
    Check for previously recorded dynamic conflicts in the conflict log.

    Walks the conflict-log files in ``log_dir`` from most recent to least recent
    and returns a description of the FIRST one that has recorded entries. Walking
    (rather than only inspecting the single most-recent file) matters because an
    empty current-day log must not shadow an older log that still has unresolved
    conflicts -- the nag should persist until they are actually cleared.

    Args:
        log_dir: The directory to search for conflict log files, or None.

    Returns:
        Tuple of ``(relative_path_str, entry_count)`` describing the conflict log,
        or None when no recorded dynamic conflicts exist.
    """
    if log_dir is None:
        return None
    for log_file in _recent_conflict_logs(log_dir):
        count = _count_conflict_entries(log_file)
        if count == 0:
            continue
        # Express the path relative to the log dir's parent (the project root) for
        # a concise, human-readable display. Fall back to the absolute path when the
        # relationship cannot be established.
        try:
            display_path = log_file.relative_to(log_dir.parent)
        except ValueError:
            display_path = log_file
        return str(display_path), count
    return None


def _format_summary(static_conflict, dynamic_conflict) -> str:
    """
    Format a brief conflict summary for stdout.

    Produces a short, human-readable summary of any detected conflicts for
    injection into the Claude Code session context. The output is intentionally
    concise: a header line, one bullet per conflict source, and a closing
    action prompt.

    Args:
        static_conflict: A ``TakeoverEnabledConflict`` describing cross-level
            disagreement on ``takeover_mode.enabled``, or None.
        dynamic_conflict: A ``(path_str, count)`` tuple for the most recent
            conflict log file with recorded entries, or None.

    Returns:
        A multi-line string suitable for printing to stdout.
    """
    lines = ["toolguard: configuration conflicts detected --"]

    if static_conflict is not None:
        # Build a compact provenance string: cite the first disagreeing source
        # so the human knows where to look, without flooding the session context.
        provenance_parts = [
            f"{value} [{prov.describe_brief()}]"
            for value, prov in static_conflict.sources
        ]
        provenance_summary = "; ".join(provenance_parts)
        lines.append(
            f"  - takeover_mode.enabled disagrees across levels; "
            f"failed safe to OFF ({provenance_summary})"
        )

    if dynamic_conflict is not None:
        path_str, count = dynamic_conflict
        noun = "entry" if count == 1 else "entries"
        lines.append(f"  - conflict log {path_str} has {count} recorded {noun}")

    lines.append("Review and resolve; see the conflict log for details.")
    return "\n".join(lines)


def _detect_conflicts(cwd: Optional[str]):
    """
    Load configuration and detect both static and dynamic conflicts.

    This is the core logic of the SessionStart hook. It is extracted from
    ``main()`` so it can be unit-tested independently without needing to mock
    stdin or sys.exit.

    Args:
        cwd: Working directory string from the hook payload, or None.

    Returns:
        Tuple ``(static_conflict, dynamic_conflict)`` where either may be None
        when no conflict of that type exists.
    """
    config = load_configuration(cwd)

    # Determine log directory from project root (same logic as the PreToolUse hook).
    project_root = config.project_root
    log_dir = project_root / "logs" if project_root is not None else None

    # 1. Static conflict: cross-level disagreement on takeover_mode.enabled.
    takeover = config.takeover_mode()
    static_conflict = takeover.conflict  # TakeoverEnabledConflict or None

    # 2. Dynamic conflict: previously recorded entries in the conflict log.
    dynamic_conflict = _check_dynamic_conflicts(log_dir)

    return static_conflict, dynamic_conflict


def main() -> None:
    """
    Main entry point for the SessionStart hook.

    Reads the SessionStart JSON payload from stdin, checks for static and dynamic
    configuration conflicts, and prints a brief summary to stdout when any are
    found. Claude Code injects this stdout into the session context so the agent
    immediately learns of any unresolved conflicts. Always exits 0 -- a SessionStart
    hook must never block or break a session.

    Exit codes:
        0: Always.
    """
    try:
        payload = _parse_session_start_input()
        cwd = payload.get("cwd") or os.getcwd()

        static_conflict, dynamic_conflict = _detect_conflicts(cwd)

        if static_conflict is not None or dynamic_conflict is not None:
            print(_format_summary(static_conflict, dynamic_conflict))

    except Exception as exc:  # noqa: BLE001 - SessionStart must never raise
        print(f"toolguard session-start: unexpected error ({exc})", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
