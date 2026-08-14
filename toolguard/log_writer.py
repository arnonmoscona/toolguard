"""
Writes toolguard's on-disk audit trail: the per-invocation resolution log
(:func:`log_command`, markdown or JSONLines) and the config-discovery
change-log (:func:`log_discovery`, which also mirrors each change into the
resolution log). Neither ever raises -- logging must never fail the hook
call it is logging.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from toolguard.path_utils import require_project_root

#: The two resolution-log formats :func:`log_command` can render. Markdown
#: is the default and, currently, the only one any production caller
#: selects -- JSONLines exists for future opt-in machine consumption; no
#: config key selects it yet (see ``docs/architecture.md``).
LOG_FORMAT_MARKDOWN = "markdown"
LOG_FORMAT_JSONLINES = "jsonlines"

#: Filename for the config-discovery change-log. Deliberately NOT
#: date-partitioned like the main resolution log
#: (``toolguard-YYYY-MM-DD.md``): a dated file would start empty every
#: morning and re-log the same discovered levels on the day's first
#: invocation -- exactly the noise this mechanism exists to avoid. Stays
#: small because a line is only appended when the discovered levels change
#: for a given project root; do not "fix" this to match the dated pattern.
#:
#: Plain text, not JSON: every record is one line, and the only thing ever
#: read back is the most recent line for a given project root (see
#: :func:`_last_discovery_levels_for_root`), so JSON's structure buys
#: nothing here that a delimiter doesn't.
_DISCOVERY_LOG_FILENAME = "toolguard-discovery.log"

#: Field separator between a discovery record's timestamp / project_root /
#: levels-blob. A tab is used because it is, for all practical purposes,
#: never present in a filesystem path or a "level: path" description
#: string -- unlike a comma or colon, which both appear in those routinely.
#: A path that somehow did contain a tab just means that record's
#: project_root won't match on lookup.
_DISCOVERY_FIELD_SEP = "\t"

#: Separator joining the individual ``levels`` strings within a discovery
#: record's third field. The ASCII Unit Separator (0x1F), not a printable
#: character, since it cannot occur in normal text -- so splitting on it
#: needs no escaping logic.
_DISCOVERY_LEVELS_SEP = "\x1f"

#: How much of the discovery log is read from the END of the file per hook
#: invocation -- NOT a size cap on the file, which is never truncated or
#: rotated; only a bound on how much of it one read touches, so the read
#: stays cheap as the file grows. 64 KiB comfortably holds many hundreds
#: of records, far more churn than any real project's discovered levels
#: change between two lookups. A record that has scrolled outside this
#: window (e.g. many other projects interleaving into a shared
#: ``TOOLGUARD_LOG_DIR``) degrades the read to "no prior entry" -- one
#: redundant log write, never an incorrect verdict.
_DISCOVERY_TAIL_READ_BYTES = 65_536  # 64 KiB


@dataclass(frozen=True)
class LogRecord:
    """
    The fields of one resolution-log entry, built by the caller and passed
    to :func:`log_command`.

    Deliberately not the same shape as
    :class:`~toolguard.config_types.RuntimeVerdict`: ``status`` here is
    ``'executed'``/``'refused'``/``'ask'``, not ``RuntimeVerdict.decision``'s
    ``'allow'``/``'deny'``/``'ask'``. A single compound command can also
    produce several of these, one per sub-command, with no 1:1
    correspondence to the one ``RuntimeVerdict`` it resolved to.
    """

    command_str: str
    status: str
    violated_rules: List[str] = field(default_factory=list)
    extra_info: Optional[str] = None
    matched_rule: Optional[str] = None
    provenance: Optional[str] = None
    note: Optional[str] = None
    permission_mode: Optional[str] = None
    additional_context: Optional[str] = None


def _logging_enabled(config: Optional[dict]) -> bool:
    """
    Whether logging is switched on for this invocation.

    Args:
        config: Optional environment config dict (from ``get_env_config()``).

    Returns:
        ``config['logging_enabled']`` (default True) when *config* is
        given; True with no config at all.
    """
    if config is not None:
        return config.get("logging_enabled", True)
    return True


def _existing_log_dir_or_warn(log_dir_path: Path) -> Optional[Path]:
    """
    Return *log_dir_path* if it exists, else warn to stderr and return None.

    Never raises or exits over a missing log directory -- see the module
    docstring.

    Args:
        log_dir_path: The directory to check.

    Returns:
        *log_dir_path* if it exists, else None.
    """
    if log_dir_path.exists():
        return log_dir_path
    print(
        f"Warning: Logging directory does not exist: {log_dir_path}. Logging disabled.",
        file=sys.stderr,
    )
    return None


def _log_dir_from_config(config: dict) -> Optional[Path]:
    """
    Resolve the log directory from a resolved environment config.

    A *missing* directory is created when ``create_log_dir`` is set; otherwise
    a warning is printed and logging is disabled for this invocation.

    Args:
        config: Environment config dict carrying ``log_dir`` and, optionally,
            ``create_log_dir``.

    Returns:
        The directory to log into, or None when logging is disabled for this
        invocation.
    """
    log_dir_path = config["log_dir"]
    if log_dir_path.exists():
        return log_dir_path
    if config.get("create_log_dir", False):
        log_dir_path.mkdir(parents=True, exist_ok=True)
        return log_dir_path
    print(
        f"Warning: Logging directory does not exist: {log_dir_path}. Logging disabled.",
        file=sys.stderr,
    )
    return None


def _log_dir_from_environment() -> Optional[Path]:
    """
    Resolve the log directory with neither an explicit path nor a resolved config.

    Falls back to ``<project root>/logs``, or None if that directory doesn't
    exist (see :func:`_existing_log_dir_or_warn`). Deliberately honours no
    environment variable of its own: ``TOOLGUARD_LOG_DIR`` is the supported
    override, read only once a config is resolved.

    Not only a rare no-args fallback: this path is also reachable at points
    in startup before any config has been resolved yet, so a warning raised
    there lands in this default directory even when ``TOOLGUARD_LOG_DIR``
    (env var or ``.env`` file) would otherwise point elsewhere.

    Returns:
        The resolved log directory, or None if it doesn't exist.

    Raises:
        RuntimeError: Propagated from
            :func:`toolguard.path_utils.require_project_root` when no project
            root can be found.
    """
    log_dir_path = require_project_root() / "logs"
    return _existing_log_dir_or_warn(log_dir_path)


def resolve_log_dir(log_dir: Optional[Path], config: Optional[dict]) -> Optional[Path]:
    """
    Pick the directory a log entry is written to, in caller-precedence order.

    An explicitly passed *log_dir* wins (used by tests), then the resolved
    environment *config*, then the ``<project root>/logs`` default.

    Args:
        log_dir: Directory passed directly by the caller, or None.
        config: Environment config dict, or None.

    Returns:
        The directory to log into, or None when this invocation should not log.

    Raises:
        RuntimeError: From :func:`_log_dir_from_environment`, when both
            *log_dir* and *config* are None and no project root can be found.
    """
    if log_dir is not None:
        return _existing_log_dir_or_warn(log_dir)
    if config is not None:
        return _log_dir_from_config(config)
    return _log_dir_from_environment()


def _build_jsonlines_entry(record: LogRecord) -> dict:
    """
    Render one log entry as a JSONLines-ready dict. Pure aside from reading
    the current time.

    Optional fields are omitted entirely when falsy. Key order is part of
    the on-disk shape and is preserved here (dict insertion order,
    guaranteed since Python 3.7).

    Computes its own ISO timestamp via ``datetime.now()``, independent of
    :func:`log_command`'s precomputed markdown-heading timestamp.

    Args:
        record: The entry's fields.

    Returns:
        A dict ready for ``json.dumps``, in on-disk key order.
    """
    entry = {
        "timestamp": datetime.now().isoformat(),
        "status": record.status,
        "command": record.command_str,
        "violated_rules": record.violated_rules,
    }
    optional = (
        ("matched_rule", record.matched_rule),
        ("provenance", record.provenance),
        ("note", record.note),
        ("extra_info", record.extra_info),
        ("permission_mode", record.permission_mode),
    )
    for key, value in optional:
        if value:
            entry[key] = value
    if record.additional_context:
        entry["additional_context"] = record.additional_context
    return entry


#: Escapes a real newline in a rendered Command field. Applied AFTER
#: :data:`_BACKSLASH_ESCAPE`, so an already-escaped backslash is never
#: mistaken for one of these on decode -- see :func:`unescape_command_field`.
_NEWLINE_ESCAPE = "\\n"

#: Escapes a literal backslash in a rendered Command field, applied first so
#: :func:`escape_command_field`'s two passes can't collide.
_BACKSLASH_ESCAPE = "\\\\"


def escape_command_field(command_str: str) -> str:
    """
    Escape *command_str* for the Command field's single rendered line.

    A raw newline would split the command across physical lines, and a
    resulting line starting with ``## `` would be read back as a new
    section heading by the harvester -- both silently drop the entry (see
    ``toolguard/tools/log_harvest.py``'s module docstring). Reversed by
    :func:`unescape_command_field`.

    Args:
        command_str: The raw command text.

    Returns:
        *command_str* with backslashes and newlines escaped.
    """
    return command_str.replace("\\", _BACKSLASH_ESCAPE).replace("\n", _NEWLINE_ESCAPE)


def unescape_command_field(text: str) -> str:
    """
    Reverse :func:`escape_command_field`.

    A backslash not followed by ``n`` or ``\\`` is left as-is, so text from
    an older, unescaped log entry round-trips unchanged.

    Args:
        text: A Command field's raw (still-escaped) text.

    Returns:
        The original command text.
    """
    result: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] in ("n", "\\"):
            result.append("\n" if text[i + 1] == "n" else "\\")
            i += 2
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def _render_markdown_entry(record: LogRecord, timestamp: str) -> str:
    """
    Render one log entry in the default Markdown format. Pure: returns the
    text, performs no IO.

    Args:
        record: The entry's fields.
        timestamp: Pre-formatted local timestamp for the entry heading.

    Returns:
        The full markdown text for one entry, including its trailing blank
        line separator.
    """
    lines = [
        f"## {timestamp}\n\n",
        f"- **Status**: {record.status.upper()}\n",
        f"- **Command**: `{escape_command_field(record.command_str)}`\n",
    ]
    if record.matched_rule:
        lines.append(f"- **Matched Rule**: `{record.matched_rule}`\n")
    if record.violated_rules:
        lines.append(
            f"- **Violated Rules**: {', '.join(f'`{rule}`' for rule in record.violated_rules)}\n"
        )
    if record.provenance:
        # Rendered AFTER Violated Rules so a deny's Provenance sits below
        # the field it describes, not above it.
        lines.append(f"- **Provenance**: {record.provenance}\n")
    if record.permission_mode:
        lines.append(f"- **Permission Mode**: `{record.permission_mode}`\n")
    if record.note:
        # A non-violation note (e.g. why an 'ask' verdict was reached) --
        # rendered under its own field, never folded into Violated Rules.
        lines.append(f"- **Note**: {record.note}\n")
    if record.additional_context:
        lines.append(f"- **Context**: {record.additional_context}\n")
    if record.extra_info:
        lines.append(f"- **Agent**: {record.extra_info}\n")
    lines.append("\n")
    return "".join(lines)


def log_command(
    record: LogRecord,
    log_dir: Optional[Path] = None,
    config: Optional[dict] = None,
    log_format: str = LOG_FORMAT_MARKDOWN,
) -> None:
    """
    Append one resolution-log entry, if logging is enabled.

    Writes to ``<log_dir>/toolguard-YYYY-MM-DD.<ext>`` under whichever
    directory :func:`resolve_log_dir` picks.

    *log_dir*/*config*/*log_format* are kept separate from *record*: they
    are routing concerns (where and how to write), not part of the entry's
    own data.

    Args:
        record: The entry's data -- see :class:`LogRecord` for field
            meanings.
        log_dir: Explicit log directory (used by tests), bypassing
            environment/config resolution.
        config: Optional environment config dict (from ``get_env_config()``).
        log_format: :data:`LOG_FORMAT_MARKDOWN` (default) or
            :data:`LOG_FORMAT_JSONLINES`.
    """
    if not _logging_enabled(config):
        return

    try:
        # Single normalisation point: extension and content both read
        # is_jsonlines, so they can't disagree on an unrecognised value.
        is_jsonlines = log_format.lower() == LOG_FORMAT_JSONLINES

        log_dir_path = resolve_log_dir(log_dir, config)
        if log_dir_path is None:
            return

        extension = LOG_FORMAT_JSONLINES if is_jsonlines else "md"
        log_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.{extension}"
        log_file = log_dir_path / log_filename

        # Markdown heading only.
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Render the entry first, then write it in a single f.write() call.
        # This narrows the interleaving window when two hook processes
        # append to the same file concurrently, and means a mid-render
        # exception (e.g. a bad format string) leaves no half-written
        # record in the audit log -- a truncated record would be worse than
        # a missing one for a security tool's audit trail.
        if is_jsonlines:
            rendered = json.dumps(_build_jsonlines_entry(record)) + "\n\n"
        else:
            rendered = _render_markdown_entry(record, timestamp)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(rendered)

    except Exception as e:
        # Includes RuntimeError from a missing project root -- warn like
        # any other logging failure, never raise further.
        print(f"Warning: Failed to write log: {e}", file=sys.stderr)


def _parse_discovery_line(line: str) -> Optional[Tuple[str, str, List[str]]]:
    """
    Parse one plain-text discovery-log line into ``(timestamp, project_root, levels)``.

    Line shape: ``<iso timestamp>\\t<project_root>\\t<levels joined by
    _DISCOVERY_LEVELS_SEP>`` (see the module-level separator constants for
    why tab and the Unit Separator are safe delimiters here). A line
    missing a tab returns ``None`` rather than raising, so a torn write
    left by an interrupted process (see :func:`log_discovery`'s
    Concurrency note) degrades to "skip this line" instead of crashing the
    read.

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

    Reads only the last :data:`_DISCOVERY_TAIL_READ_BYTES` of
    ``<log_dir>/toolguard-discovery.log`` (see that constant for why), then
    scans those lines from the end, so the most recent record for this
    project root wins even when a shared ``TOOLGUARD_LOG_DIR`` interleaves
    entries from several projects.

    Args:
        log_dir: Directory containing the discovery log.
        project_root: The project root string to match against each
            record's ``project_root`` field.

    Returns:
        The matching record's ``levels`` list, or ``None`` if no matching
        record was found within the read window.
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
        # Never fail the hook over a read error -- degrade to "no prior entry".
        return None

    lines = text.split("\n")
    if start > 0:
        # Seeking into the middle of the file can land mid-line -- the read
        # didn't start at byte 0, so the first line may be a partial record.
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

    toolguard is a ``PreToolUse`` hook: it runs as a fresh process on every
    tool call, so there is no in-process "once per session" state to guard
    with. This function is the guard instead: it compares the current
    *source_descriptions* against the most recent record for *project_root*
    in ``<log_dir>/toolguard-discovery.log`` (see
    :func:`_last_discovery_levels_for_root`) and writes -- to both the
    discovery log and the main resolution log -- only when they differ, or
    when there is no prior record for this project root within the read
    window. On no change, nothing is written to either log. The discovery
    log IS the state; there is no separate marker file.

    Concurrency: two racing hook processes can both append a record,
    producing a harmless duplicate line (both carry the same ``levels``, so
    the next read still resolves correctly). A write interrupted partway
    (e.g. a killed process) can instead leave an unterminated final line --
    the next write does not concatenate onto it (see step 1 below), and a
    reader that meets the torn line tolerates it by skipping the
    unparseable line (:func:`_parse_discovery_line`). No locking is added
    for either case, since the cost of a lock on every tool call is not
    worth it.

    Args:
        source_descriptions: Human-readable per-source descriptions, e.g.
            the output of ``Configuration.describe_levels()``.
        log_dir: Directory where both the resolution log and the discovery
            change-log are written.
        project_root: This invocation's resolved project root, used to key
            the discovery-log comparison so a shared ``TOOLGUARD_LOG_DIR``
            across projects does not flap between them.
    """
    try:
        levels = list(source_descriptions)
        project_root_str = str(project_root)
        previous_levels = _last_discovery_levels_for_root(log_dir, project_root_str)
        if previous_levels == levels:
            return  # Unchanged for this project root -- nothing to log.

        log_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()

        # 1. Append the plain-text change record -- this IS the state the
        #    next invocation compares against; no marker file, no rotation.
        #    If the existing file's last byte isn't a newline (an earlier
        #    torn write left an unterminated final line -- see
        #    _parse_discovery_line), prefix a newline so this record lands
        #    on its own line instead of concatenating onto the truncated one.
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

        # 2. Mirror to the main resolution log, as a Status-less section --
        #    toolguard/tools/log_harvest.py skips any section without a
        #    Status field, and this one has none.
        log_filename = f"toolguard-{now.strftime('%Y-%m-%d')}.md"
        log_file = log_dir / log_filename
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        count = len(levels)
        joined = ", ".join(levels) if levels else "(none)"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"## {timestamp}\n\n")
            f.write(f"- **Discovery**: discovered {count} config levels: {joined}\n\n")
    except Exception as e:
        # Never fail the hook over a discovery-diagnostic write error.
        print(f"Warning: Failed to write discovery diagnostic: {e}", file=sys.stderr)
