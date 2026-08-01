"""
Logging utilities for toolguard.

Provides logging functionality with same format as checked_bash.py.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from toolguard.config import find_project_root

#: Filename for the config-discovery change-log (TOO-19). Deliberately
#: NOT date-partitioned like the main resolution log (``toolguard-YYYY-MM-DD.md``):
#: a dated discovery log would start empty every morning and re-log the same
#: discovered levels on the day's first invocation, reproducing exactly the
#: noise this mechanism exists to remove. It stays small on its own because a
#: new line is only appended when the discovered levels actually change for a
#: given project root -- do not "fix" this to match the dated pattern.
#:
#: Plain text, not JSON (TOO-19 code review M3): every record is one line, and
#: the only thing ever read back is the most recent line for a given project
#: root, so JSON's structure buys nothing here that a delimiter doesn't. See
#: :func:`_last_discovery_levels_for_root` for the read side and the line
#: format below.
_DISCOVERY_LOG_FILENAME = "toolguard-discovery.log"

#: Field separator between a record's timestamp / project_root / levels-blob.
#: A tab is used because it is, for all practical purposes, never present in a
#: filesystem path or a "level: path" description string -- unlike a comma or
#: a colon, both of which DO appear in those strings routinely. If a path
#: somehow did contain a tab, the worst case is a failed project-root match on
#: that one line (degrading to "no prior entry" for this read, never a wrong
#: verdict -- see the bounded-tail docstring below), not a crash.
_DISCOVERY_FIELD_SEP = "\t"

#: Separator joining the individual ``levels`` strings within a record's third
#: field. The ASCII Unit Separator (0x1F) is used rather than a printable
#: character precisely because it is not reachable from normal text input --
#: no config path or level description can ever contain it -- so splitting on
#: it is unambiguous without any escaping logic.
_DISCOVERY_LEVELS_SEP = "\x1f"

#: How much of the discovery log is read from the END of the file per hook
#: invocation (TOO-19 code review M3). This is NOT a size cap on the file --
#: the file is never truncated or rotated, by design (see the module-level
#: rationale above) -- it only bounds how much of it any single read touches,
#: which is what keeps the read cheap regardless of how large the file grows.
#: 64 KiB comfortably holds many hundreds of records (each line is well under
#: 200 bytes in normal use), which is far more churn than any real project's
#: discovered-levels set changes between two lookups. If the most recent
#: record for this project root happens to have scrolled outside this window
#: (e.g. a very large number of OTHER projects interleaving into a shared
#: ``TOOLGUARD_LOG_DIR``), the read degrades to "no prior entry" -- which
#: costs exactly one redundant log write, never an incorrect verdict.
_DISCOVERY_TAIL_READ_BYTES = 65_536  # 64 KiB

#: Word budget for the ``additionalContext`` preview written to a single log
#: line (TOO-19 Phase 1, increment 7). The accumulated enrichment text can be
#: up to 500 words (see ``compound.py::_MAX_CONTEXT_WORDS``) and would
#: otherwise land in the log on EVERY matching invocation -- these logs are
#: read by a human scanning for anomalies, and a 500-word block per line
#: destroys that. The FULL text is still injected to Claude via
#: ``hookSpecificOutput``; only the LOGGED copy is capped.
_LOG_CONTEXT_PREVIEW_WORDS = 40


def _preview_additional_context(
    text: str, max_words: int = _LOG_CONTEXT_PREVIEW_WORDS
) -> str:
    """
    Bound an ``additionalContext`` block to a short preview for a log line.

    Keeps the first *max_words* words and, when the text was actually cut,
    appends an ellipsis plus the FULL word count so a human scanning the log
    can tell there is more without having to open a separate detail store --
    there is none; the full text lives only in the hook's JSON output for
    that single invocation.

    Args:
        text: The full accumulated ``additionalContext`` string.
        max_words: Maximum number of words to keep before the ellipsis
            marker. Defaults to :data:`_LOG_CONTEXT_PREVIEW_WORDS`.

    Returns:
        The text unchanged if it is within budget, otherwise a truncated
        preview followed by ``" ... (N words total)"``.
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    preview = " ".join(words[:max_words])
    return f"{preview} ... ({len(words)} words total)"


def log_command(
    command_str: str,
    status: str,
    violated_rules: Optional[List[str]] = None,
    log_dir: Optional[Path] = None,
    extra_info: Optional[str] = None,
    config: Optional[dict] = None,
    matched_rule: Optional[str] = None,
    note: Optional[str] = None,
    permission_mode: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> None:
    """
    Log command execution to file if logging is enabled.

    Uses the same logging format as checked_bash.py for compatibility.
    Logs to logs/toolguard-YYYY-MM-DD.md by default.

    Args:
        command_str: The command that was executed, refused, or left pending a prompt
        status: 'executed', 'refused', or 'ask' (TOO-15: the command was not
            outright blocked but requires an interactive permission prompt)
        violated_rules: List of rules that were violated (for 'refused' commands
            only -- NOT used for 'ask', which is not a violation; see ``note``)
        log_dir: Optional directory path for logs (for testing). If provided, uses this
                 directory directly instead of resolving from environment or project root.
        extra_info: Optional additional info to include in the log entry (e.g., agent identification)
        config: Optional environment config dict (from get_env_config())
        matched_rule: Optional pattern string that permitted the command (for allowed commands)
        note: Optional free-text note for a non-violation outcome (e.g. WHY an
            'ask' verdict was reached). Rendered under its own field, distinct
            from ``violated_rules``, so an 'ask' outcome is never mislabeled as
            a rule violation.
        permission_mode: Claude Code's own ``permission_mode`` field from the hook
            input (e.g. ``'default'``, ``'plan'``, ``'auto'``/similar), when present.
            Toolguard's ``ask``/``allow``/``deny`` verdict is independent of this --
            it never changes the decision -- but recording it makes it possible to
            later tell whether Claude Code's own mode (e.g. an auto-mode override of
            a hook ``ask``, see anthropics/claude-code changelog v2.1.211) was a
            factor in what actually happened to a command after toolguard decided.
        additional_context: The winning rule's accumulated ``additionalContext``
            enrichment (TOO-19 Phase 1), or ``None`` when there was none. Answers
            "why did Claude get this nudge" after the fact. Rendered under its
            own field in both formats, CAPPED to a short word-budget preview
            (see :func:`_preview_additional_context`) rather than logged in
            full -- the full text already reached Claude via the hook's JSON
            output for that invocation; logging it in full on every matching
            command would make the log unreadable for a human scanning it.
    """
    # Check if logging is enabled (backward compatibility with CHECKED_BASH_LOGGING_ON)
    if config is not None:
        logging_on = config.get("logging_enabled", True)
    else:
        logging_on = os.environ.get("CHECKED_BASH_LOGGING_ON", "true").lower() == "true"

    if not logging_on:
        return

    try:
        # Get logging configuration
        logging_format = os.environ.get(
            "CHECKED_BASH_LOGGING_FORMAT", "markdown"
        ).lower()

        # Resolve log directory path
        if log_dir is not None:
            # Use provided log directory (for testing)
            # Check directory exists (old behavior for explicit log_dir - exit on error)
            log_dir_path = log_dir
            if not log_dir_path.exists():
                print(
                    f"Error: Logging directory does not exist: {log_dir_path}",
                    file=sys.stderr,
                )
                sys.exit(1)
        elif config is not None:
            # Use config from env_config
            log_dir_path = config["log_dir"]
            create_log_dir = config.get("create_log_dir", False)

            # Check if directory exists
            if not log_dir_path.exists():
                if create_log_dir:
                    # Create directory
                    log_dir_path.mkdir(parents=True, exist_ok=True)
                else:
                    # Warn and disable logging for this invocation
                    print(
                        f"Warning: Logging directory does not exist: {log_dir_path}. Logging disabled.",
                        file=sys.stderr,
                    )
                    return
        else:
            # Backward compatibility: use environment variables
            logging_dir = os.environ.get("CHECKED_BASH_LOGGING_DIR", "logs")
            if Path(logging_dir).is_absolute():
                log_dir_path = Path(logging_dir)
            else:
                project_root = find_project_root()
                log_dir_path = project_root / logging_dir

            # Check directory exists (old behavior - exit on error)
            if not log_dir_path.exists():
                print(
                    f"Error: Logging directory does not exist: {log_dir_path}",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Generate log filename with current date and appropriate extension
        extension = "md" if logging_format == "markdown" else "jsonlines"
        log_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.{extension}"
        log_file = log_dir_path / log_filename

        # Prepare log entry
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        violated_rules = violated_rules or []

        # Write log entry
        with open(log_file, "a", encoding="utf-8") as f:
            if logging_format == "jsonlines":
                # JSONLines format
                entry = {
                    "timestamp": datetime.now().isoformat(),
                    "status": status,
                    "command": command_str,
                    "violated_rules": violated_rules,
                }
                if matched_rule:
                    entry["matched_rule"] = matched_rule
                if note:
                    entry["note"] = note
                if extra_info:
                    entry["extra_info"] = extra_info
                if permission_mode:
                    entry["permission_mode"] = permission_mode
                if additional_context:
                    entry["additional_context"] = _preview_additional_context(
                        additional_context
                    )
                f.write(json.dumps(entry) + "\n\n")
            else:
                # Markdown format (default)
                f.write(f"## {timestamp}\n\n")
                f.write(f"- **Status**: {status.upper()}\n")
                f.write(f"- **Command**: `{command_str}`\n")
                if matched_rule:
                    f.write(f"- **Matched Rule**: `{matched_rule}`\n")
                if violated_rules:
                    f.write(
                        f"- **Violated Rules**: {', '.join(f'`{rule}`' for rule in violated_rules)}\n"
                    )
                if permission_mode:
                    f.write(f"- **Permission Mode**: `{permission_mode}`\n")
                if note:
                    # A non-violation note (e.g. WHY an 'ask' verdict was
                    # reached) -- deliberately rendered under its own field,
                    # never under Violated Rules (TOO-15 review finding #3).
                    f.write(f"- **Note**: {note}\n")
                if additional_context:
                    # The rule's additionalContext enrichment (TOO-19 Phase 1),
                    # capped to a short preview -- see _preview_additional_context.
                    f.write(
                        f"- **Context**: {_preview_additional_context(additional_context)}\n"
                    )
                if extra_info:
                    f.write(f"- **Agent**: {extra_info}\n")
                f.write("\n")

    except RuntimeError as e:
        # Project root not found - fatal error
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Other logging errors - print warning but don't fail
        print(f"Warning: Failed to write log: {e}", file=sys.stderr)


def _parse_discovery_line(line: str) -> Optional[Tuple[str, str, List[str]]]:
    """
    Parse one plain-text discovery-log line into ``(timestamp, project_root, levels)``.

    Line shape: ``<iso timestamp>\\t<project_root>\\t<levels joined by
    _DISCOVERY_LEVELS_SEP>`` (see the module-level separator constants for why
    tab and the Unit Separator are safe delimiters here). A line missing
    either tab, or one that is otherwise malformed, is treated as unparseable
    -- returns ``None`` -- rather than raising, so a torn write from two hook
    processes racing on the same file (see :func:`log_discovery`) degrades to
    "skip this line" instead of crashing the read.

    Args:
        line: A single line's text, WITHOUT its trailing newline.

    Returns:
        ``(timestamp, project_root, levels)``, or ``None`` if *line* does not
        have the expected two-tab shape.
    """
    parts = line.split(_DISCOVERY_FIELD_SEP, 2)
    if len(parts) != 3:
        return None
    timestamp, project_root, levels_blob = parts
    levels = levels_blob.split(_DISCOVERY_LEVELS_SEP) if levels_blob else []
    return timestamp, project_root, levels


def _last_discovery_levels_for_root(
    log_dir: Path, project_root: str
) -> Optional[List[str]]:
    """
    Return the ``levels`` list from the most recent discovery-log record for
    *project_root*, or ``None`` if there is no matching record in the read
    window.

    TOO-19 code review M3: reads only a BOUNDED TAIL of
    ``<log_dir>/toolguard-discovery.log`` -- the last
    :data:`_DISCOVERY_TAIL_READ_BYTES` bytes -- rather than the whole file, so
    the read stays cheap no matter how large the file grows. There is no size
    cap on the file itself and nothing is ever rotated or truncated (the
    prior 1 MB read-size cap degraded to "no prior entry" once exceeded,
    which made every subsequent invocation append -- a self-accelerating bug;
    see the code review finding). Bounding the READ instead of the FILE means
    growth never breaks anything; at worst a lookup misses an entry that has
    scrolled outside the tail window and costs one redundant log write, never
    an incorrect verdict -- the same safety argument that already applied to
    tolerating a torn final line.

    Scans the tail's lines from the end, so the most recent record for this
    project root wins even when a shared ``TOOLGUARD_LOG_DIR`` interleaves
    entries from several projects (TOO-19). The first line of the tail read
    is discarded when the read did not start at byte 0 of the file, since
    seeking into the middle of the file can land mid-line.

    Args:
        log_dir: Directory containing the discovery log.
        project_root: The project root string to match against each
            record's ``project_root`` field.

    Returns:
        The matching record's ``levels`` list, or ``None`` when the file is
        missing, empty, or has no valid entry for this project root within
        the read window.
    """
    log_path = log_dir / _DISCOVERY_LOG_FILENAME
    try:
        if not log_path.exists():
            return None
        with open(log_path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - _DISCOVERY_TAIL_READ_BYTES)
            f.seek(start)
            tail_bytes = f.read()
        text = tail_bytes.decode("utf-8", errors="ignore")
    except Exception:
        # Diagnostic logging must never fail the hook -- degrade to "no
        # prior entry" rather than propagate a read error.
        return None

    lines = text.split("\n")
    if start > 0:
        # The read did not start at the file's beginning, so the first line
        # in the tail may be a partial line split mid-record -- drop it.
        lines = lines[1:]

    for line in reversed(lines):
        line = line.strip("\r")
        if not line:
            continue
        parsed = _parse_discovery_line(line)
        if parsed is None:
            continue
        _timestamp, line_project_root, levels = parsed
        if line_project_root == project_root:
            return levels
    return None


def log_discovery(
    source_descriptions: List[str], log_dir: Path, project_root: str
) -> None:
    """
    Write a config-discovery diagnostic when the discovered levels changed.

    Records which configuration levels were discovered and from where, e.g.
    ``discovered 3 config levels: project: /p/.claude/toolguard_hook.toml, ...``.
    This replaces the discovery diagnostics that the legacy permission loader
    used to print to stderr (TOO-8 Phase 4, M2).

    toolguard is a ``PreToolUse`` hook: it runs as a fresh process on every
    tool call, so there is no in-process "once per session" to guard with
    (TOO-19 -- a prior module-level flag advertised that guarantee and could
    never deliver it, since the flag reset to ``False`` on every invocation).
    This function is the guard instead: it compares the current
    *source_descriptions* against the most recent record for *project_root*
    in ``<log_dir>/toolguard-discovery.log`` (see
    :func:`_last_discovery_levels_for_root``) and only writes anything -- to
    either the discovery log or the main resolution log -- when they differ,
    or when there is no prior record for this project root (within the read
    window -- see that function's docstring). On no change, nothing is
    written to either log. The discovery log IS the state; there is no
    separate marker file, and it is plain text, one record per line (TOO-19
    code review M3) -- not JSON, since the only thing ever read back is the
    single most recent matching line.

    Concurrency: two hook processes racing can both append a record. That
    produces a harmless duplicate line (both carry the same ``levels``, so
    the next read still de-duplicates correctly) -- no locking is added for
    this, since the cost of a lock on every tool call is not worth guarding
    against an at-worst-duplicate-line outcome.

    Args:
        source_descriptions: Human-readable per-source descriptions, e.g. the
            output of ``Configuration.describe_levels()`` (the brief
            ``level: path`` form passed by the hook caller).
        log_dir: Directory where both the resolution log and the discovery
            change-log are written.
        project_root: This invocation's resolved project root (e.g.
            ``env_config["project_root"]``), used to key the discovery-log
            comparison so a shared ``TOOLGUARD_LOG_DIR`` across projects
            does not flap between them (TOO-19).
    """
    try:
        levels = list(source_descriptions)
        project_root_str = str(project_root)
        previous_levels = _last_discovery_levels_for_root(log_dir, project_root_str)
        if previous_levels == levels:
            return  # Unchanged for this project root -- nothing to log.

        log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()

        # 1. Append the plain-text change record. This IS the state that the
        #    next invocation compares against -- no separate marker file, no
        #    size cap, no rotation (TOO-19 code review M3 -- see the module
        #    docstring above). If the existing file's last byte isn't a
        #    newline (a torn write left an unterminated final line -- see
        #    _last_discovery_levels_for_root), prefix a newline so the new
        #    record lands on its own line instead of concatenating onto the
        #    truncated one.
        log_path = log_dir / _DISCOVERY_LOG_FILENAME
        line = (
            f"{now.isoformat()}{_DISCOVERY_FIELD_SEP}"
            f"{project_root_str}{_DISCOVERY_FIELD_SEP}"
            f"{_DISCOVERY_LEVELS_SEP.join(levels)}"
        )
        needs_leading_newline = False
        if log_path.exists() and log_path.stat().st_size > 0:
            with open(log_path, "rb") as f:
                f.seek(-1, os.SEEK_END)
                needs_leading_newline = f.read(1) != b"\n"
        with open(log_path, "a", encoding="utf-8") as f:
            if needs_leading_newline:
                f.write("\n")
            f.write(line + "\n")

        # 2. Mirror to the main resolution log, in the pre-existing format
        #    (log_harvest.py depends on this exact shape -- see its tests).
        log_filename = f"toolguard-{now.strftime('%Y-%m-%d')}.md"
        log_file = log_dir / log_filename
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        count = len(levels)
        joined = ", ".join(levels) if levels else "(none)"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"## {timestamp}\n\n")
            f.write(f"- **Discovery**: discovered {count} config levels: {joined}\n\n")
    except Exception as e:
        # Diagnostic logging must never fail the hook.
        print(f"Warning: Failed to write discovery diagnostic: {e}", file=sys.stderr)
