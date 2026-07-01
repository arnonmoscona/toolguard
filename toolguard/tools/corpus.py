"""
Corpus harvesting: combine daily-log and transcript evidence for a project.

The rule-maintenance engines (mining, replay-backed redundancy/broadening) take a
``List[LogEntry]`` corpus of observed tool invocations.  Two harvesters produce
those entries from different sources:

* :func:`toolguard.tools.log_harvest.harvest` -- toolguard's own daily resolution
  logs (``logs/toolguard-YYYY-MM-DD.md``), the authoritative record of what the
  hook actually permitted or refused.
* :func:`toolguard.tools.transcript_harvest.harvest_transcripts` -- Claude Code's
  session transcripts (``~/.claude/projects/<encoded>/*.jsonl``), which capture
  tool calls the hook may not have logged (e.g. on a machine where logging was
  off, or for tools that bypass the log).

This module is the single, tested seam that resolves both source directories for
a project and merges them into one chronologically-sorted corpus.  It performs IO
(directory discovery + file reads) and is therefore kept OUT of the pure
:func:`toolguard.tools.maintenance.run_maintenance` aggregator: the CLI/skill
harvests here and passes the resulting corpus in.  Read-only; nothing is written.
"""

from pathlib import Path
from typing import List, Optional

from toolguard.tools.log_harvest import LogEntry, harvest
from toolguard.tools.project_root import resolve_project_root
from toolguard.tools.transcript_harvest import (
    harvest_transcripts,
    transcript_dir_for_project,
)

# Default daily-log subdirectory, matching log_writer's documented default
# (``logs/toolguard-YYYY-MM-DD.md`` under the project root).
DEFAULT_LOGS_SUBDIR = "logs"


def resolve_logs_dir(project_dir: Optional[Path] = None) -> Path:
    """
    Resolve the toolguard daily-log directory for a project.

    Resolves the project root (version-control root or explicit override, via
    :func:`toolguard.tools.project_root.resolve_project_root`) and returns its
    ``logs/`` subdirectory, the documented default location of the daily
    resolution logs.  Existence is NOT checked.

    Args:
        project_dir: Directory to resolve from (defaults to the current
            directory when ``None``).

    Returns:
        The expected daily-log directory (``<project-root>/logs``).
    """
    resolution = resolve_project_root(project_dir)
    root = resolution.root if resolution.root is not None else (project_dir or Path("."))
    return root / DEFAULT_LOGS_SUBDIR


def harvest_corpus(
    project_dir: Optional[Path] = None,
    *,
    max_age_days: Optional[int] = None,
    logs_dir: Optional[Path] = None,
    transcripts_dir: Optional[Path] = None,
    claude_home: Optional[Path] = None,
) -> List[LogEntry]:
    """
    Harvest and merge the daily-log and transcript corpora for a project.

    Both sources are time-bounded by the same ``max_age_days`` rolling window
    (relative to today's local date) and the merged result is sorted by
    timestamp (oldest first), so replay/mining see one coherent timeline.  A
    missing or unreadable source directory contributes nothing rather than
    raising -- a project with no logs yet still yields whatever transcripts
    exist, and vice versa.

    Args:
        project_dir: Project directory whose corpus to harvest (defaults to the
            current directory).  Used to resolve both source directories when
            they are not given explicitly.
        max_age_days: Only include entries from the last N calendar days.
            ``None`` means no age cap (harvest everything available).
        logs_dir: Override for the daily-log directory (default: the project
            root's ``logs/``).
        transcripts_dir: Override for the transcript directory (default: the
            Claude Code transcript dir for the project root).
        claude_home: Override for the Claude Code home (default: ``~/.claude``);
            only used when ``transcripts_dir`` is not given.

    Returns:
        A timestamp-sorted list of :class:`LogEntry` records drawn from both
        sources (may be empty).
    """
    resolution = resolve_project_root(project_dir)
    root = resolution.root if resolution.root is not None else (project_dir or Path("."))

    logs = logs_dir if logs_dir is not None else (root / DEFAULT_LOGS_SUBDIR)
    transcripts = (
        transcripts_dir
        if transcripts_dir is not None
        else transcript_dir_for_project(root, claude_home)
    )

    entries: List[LogEntry] = []
    entries.extend(harvest(logs, max_age_days=max_age_days))
    entries.extend(harvest_transcripts(transcripts, max_age_days=max_age_days))
    entries.sort(key=lambda entry: entry.timestamp)
    return entries
