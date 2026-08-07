"""
Logging utilities for toolguard.

Provides logging functionality with same format as checked_bash.py.
"""

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from toolguard.path_utils import require_project_root

#: The two resolution-log output formats :func:`log_command` can render.
#: Markdown is the default and the only one any production caller selects; the
#: JSONLines variant exists for machine consumption (``docs/security.md`` names
#: ``logs/toolguard-YYYY-MM-DD.jsonlines`` "for scripting").
#:
#: TOO-19 m5: these replace a legacy ``CHECKED_BASH_LOGGING_FORMAT``
#: environment variable -- one of three undocumented checked_bash.py-era
#: fallbacks removed with 1.0RC1 in view. See :func:`log_command`'s
#: ``log_format`` parameter for why the FORMAT survived its selector.
LOG_FORMAT_MARKDOWN = "markdown"
LOG_FORMAT_JSONLINES = "jsonlines"

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


@dataclass(frozen=True)
class LogRecord:
    """
    The fields of a single resolution-log entry, in one value.

    TOO-45 R1d: hoisted from a module-private class built at the WRITER
    boundary (inside :func:`log_command`, out of 12 loose parameters) to a
    public one built at the CALLER boundary (``toolguard.hook``). The shape
    was already right -- it existed "only to keep the two format writers
    (:func:`_build_jsonlines_entry` / :func:`_render_markdown_entry`) from
    each taking eight positional arguments" -- it was just constructed one
    hop too late, forcing :func:`log_command` itself to carry the same 12
    loose parameters its own docstring named as TOO-45 R1's target. Callers
    (``toolguard.hook``) now build this directly from the
    :class:`~toolguard.config_types.RuntimeVerdict` fields they already have
    in scope, instead of threading each field through as its own argument.

    Deliberately NOT the same type as ``RuntimeVerdict``: this is a
    log-RENDERING record (``status`` is ``'executed'``/``'refused'``/
    ``'ask'``, not ``RuntimeVerdict.decision``'s ``'allow'``/``'deny'``/
    ``'ask'``; ``violated_rules``/``note`` are call-site judgement calls --
    e.g. the fallback-escape-hatch placeholder substitution in
    ``hook.py::_reason_suffix_or_placeholder`` -- not raw verdict fields) and
    it also carries per-sub-command data (one compound command logs several
    of these, one per sub-command) that has no 1:1 correspondence with the
    single ``RuntimeVerdict`` the whole compound resolution produced.
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
    Decide whether logging is switched on for this invocation.

    Uses the resolved environment config when one was supplied (production
    always supplies one -- every ``log_command`` call in ``hook.py`` passes
    ``config=env_config``). With no config -- direct/test callers only --
    logging is ON.

    TOO-19 m5: this used to consult a legacy ``CHECKED_BASH_LOGGING_ON``
    environment variable in the no-config case, a checked_bash.py-era
    fallback that was undocumented, referenced by no config or doc, and able
    to silently switch the audit log off. It defaulted to ``"true"`` when
    unset, so removing it is a no-op for anyone who never set it -- which,
    with 1.0RC1 in view, was everyone. ``TOOLGUARD_LOGGING_ENABLED`` (read via
    :func:`toolguard.env_config.get_env_config` into the ``logging_enabled``
    key) is the supported way to turn logging off.

    Args:
        config: Optional environment config dict (from ``get_env_config()``).

    Returns:
        True when a log entry should be written.
    """
    if config is not None:
        return config.get("logging_enabled", True)
    return True


def _require_existing_log_dir(log_dir_path: Path) -> None:
    """
    Abort the process when a caller-specified log directory does not exist.

    This is the historical behaviour for the two paths where the directory is
    named without a resolved environment config behind it (the explicit
    ``log_dir`` argument and the no-config default, see
    :func:`_log_dir_from_environment`): a missing directory is a configuration
    error, not something to silently create.

    Args:
        log_dir_path: The directory that must already exist.
    """
    if not log_dir_path.exists():
        print(
            f"Error: Logging directory does not exist: {log_dir_path}",
            file=sys.stderr,
        )
        sys.exit(1)


def _log_dir_from_config(config: dict) -> Optional[Path]:
    """
    Resolve the log directory from a resolved environment config.

    Unlike the explicit/legacy paths this one is tolerant: a missing directory
    is created when ``create_log_dir`` is set, and otherwise merely disables
    logging for this invocation with a warning -- a hook must not kill the
    tool call over a missing log directory.

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


def _log_dir_from_environment() -> Path:
    """
    Resolve the log directory with neither an explicit path nor a resolved config.

    Falls back to ``<project root>/logs``. The directory must already exist
    (see :func:`_require_existing_log_dir`).

    TOO-19 m5: the directory name used to be overridable by a legacy
    ``CHECKED_BASH_LOGGING_DIR`` environment variable that defaulted to
    ``"logs"`` -- a checked_bash.py-era fallback, undocumented and referenced
    by no config or doc. Removing it is a no-op for anyone who never set it.
    ``TOOLGUARD_LOG_DIR`` (read via
    :func:`toolguard.env_config.get_env_config`) is the supported override,
    and production always goes through it because ``hook.py`` passes a
    resolved config to every ``log_command`` call, so this function is reached
    only by direct/test callers.

    Returns:
        The resolved log directory.

    Raises:
        RuntimeError: Propagated from
            :func:`toolguard.path_utils.require_project_root` when no project
            root can be found. :func:`log_command` catches this specifically
            and treats it as fatal (prints and exits 1), so it is not
            swallowed here.
    """
    log_dir_path = require_project_root() / "logs"
    _require_existing_log_dir(log_dir_path)
    return log_dir_path


def _resolve_log_dir(log_dir: Optional[Path], config: Optional[dict]) -> Optional[Path]:
    """
    Pick the directory a log entry is written to, in caller-precedence order.

    An explicitly passed *log_dir* wins (used by tests), then the resolved
    environment *config*, then the ``<project root>/logs`` default.

    Args:
        log_dir: Directory passed directly by the caller, or None.
        config: Environment config dict, or None.

    Returns:
        The directory to log into, or None when this invocation should not log.
    """
    if log_dir is not None:
        _require_existing_log_dir(log_dir)
        return log_dir
    if config is not None:
        return _log_dir_from_config(config)
    return _log_dir_from_environment()


def _build_jsonlines_entry(record: LogRecord) -> dict:
    """
    Render one log entry as a JSONLines-ready dict. Pure: no IO, no side
    effects other than reading the current time (see the timestamp note
    below).

    Optional fields are omitted entirely when falsy, so a consumer sees the
    same keys it always has. Key order is part of the on-disk shape and is
    preserved here (dict insertion order, guaranteed since Python 3.7).

    Deliberately calls ``datetime.now()`` again here rather than accepting
    :func:`log_command`'s pre-formatted markdown ``timestamp`` string: the
    JSONLines record carries its own independent ISO timestamp field, and
    that second, distinct ``datetime.now()`` call -- separate from the one
    that produces the markdown heading -- reproduces the original
    implementation's call sequence exactly. This asymmetry between the two
    renderers (this one calls ``datetime.now()`` itself; the markdown one
    below takes a string) is required, not an oversight -- do NOT "clean it
    up" by threading one shared timestamp into both formats. Tests patching
    ``datetime.now`` with a ``side_effect`` list (see ``log_filename`` then
    ``timestamp`` then this call, in :func:`log_command`) depend on the
    sequence staying exactly as it is.

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
        entry["additional_context"] = _preview_additional_context(
            record.additional_context
        )
    return entry


def _render_markdown_entry(record: LogRecord, timestamp: str) -> str:
    """
    Render one log entry in the default Markdown format. Pure: returns the
    text, performs no IO.

    Args:
        record: The entry's fields.
        timestamp: Pre-formatted local timestamp for the entry heading. This
            is a plain string, not a fresh ``datetime.now()`` call,
            deliberately: it is the SAME timestamp :func:`log_command`
            already computed once for this entry, whereas the JSONLines
            renderer (:func:`_build_jsonlines_entry`) calls ``datetime.now()``
            again for its own, independent ISO field. That asymmetry is
            required to preserve the original implementation's
            two-distinct-``datetime.now()``-calls behaviour -- see the note
            on :func:`_build_jsonlines_entry` for the full rationale. Do not
            "clean it up" by having this function call ``datetime.now()``
            itself.

    Returns:
        The full markdown text for one entry, including its trailing blank
        line separator.
    """
    lines = [
        f"## {timestamp}\n\n",
        f"- **Status**: {record.status.upper()}\n",
        f"- **Command**: `{record.command_str}`\n",
    ]
    if record.matched_rule:
        lines.append(f"- **Matched Rule**: `{record.matched_rule}`\n")
    if record.violated_rules:
        lines.append(
            f"- **Violated Rules**: {', '.join(f'`{rule}`' for rule in record.violated_rules)}\n"
        )
    if record.provenance:
        # Origin of the matched/violated rule (TOO-45 R3 follow-up): a
        # SEPARATE field, not folded back into Matched Rule / Violated Rules
        # text -- see log_command's provenance parameter. Rendered AFTER
        # Violated Rules so a deny's Provenance sits below the field it
        # describes, not above it.
        lines.append(f"- **Provenance**: {record.provenance}\n")
    if record.permission_mode:
        lines.append(f"- **Permission Mode**: `{record.permission_mode}`\n")
    if record.note:
        # A non-violation note (e.g. WHY an 'ask' verdict was reached) --
        # deliberately rendered under its own field, never under Violated
        # Rules (TOO-15 review finding #3).
        lines.append(f"- **Note**: {record.note}\n")
    if record.additional_context:
        # The rule's additionalContext enrichment (TOO-19 Phase 1), capped to
        # a short preview -- see _preview_additional_context.
        lines.append(
            f"- **Context**: {_preview_additional_context(record.additional_context)}\n"
        )
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
    Log command execution to file if logging is enabled.

    Uses the same logging format as checked_bash.py for compatibility.
    Logs to logs/toolguard-YYYY-MM-DD.md by default.

    TOO-45 R1d: takes the entry's data as one :class:`LogRecord`, built by
    the caller (``toolguard.hook``), instead of the 12 loose parameters this
    function used to carry (the ``# noqa: PLR0913`` marker this replaced was
    R1's own pre-registered acceptance test). *log_dir*/*config*/*log_format*
    stay as separate parameters -- they are ROUTING concerns (where/how to
    write), not part of the entry's own data, so bundling them into
    *record* would conflate two different kinds of information the way the
    old flat parameter list did.

    Args:
        record: The entry's data -- see :class:`LogRecord` for field meanings
            (they mirror this function's former parameter names exactly).
        log_dir: Optional directory path for logs (for testing). If provided, uses this
                 directory directly instead of resolving from environment or project root.
        config: Optional environment config dict (from get_env_config())
        log_format: :data:`LOG_FORMAT_MARKDOWN` (the default, and what every
            production caller uses) or :data:`LOG_FORMAT_JSONLINES`. TOO-19
            m5: this used to be read from a legacy
            ``CHECKED_BASH_LOGGING_FORMAT`` environment variable, removed
            along with the other two ``CHECKED_BASH_*`` fallbacks. It became an
            explicit parameter rather than disappearing entirely because the
            JSONLines renderer is a real, documented output format
            (``docs/security.md`` names ``.jsonlines`` "for scripting") -- the
            legacy env var was the wrong SELECTOR for it, not a reason to
            delete the format itself. Unlike the other two removed variables,
            this one had no modern ``TOOLGUARD_*`` equivalent to fall back on;
            supplying one is a documentation/config decision, not something
            this removal should have made silently.
    """
    if not _logging_enabled(config):
        return

    try:
        logging_format = log_format.lower()

        # Resolve log directory path (None => logging disabled for this call)
        log_dir_path = _resolve_log_dir(log_dir, config)
        if log_dir_path is None:
            return

        # Generate log filename with current date and appropriate extension
        extension = "md" if logging_format == "markdown" else "jsonlines"
        log_filename = f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.{extension}"
        log_file = log_dir_path / log_filename

        # Prepare log entry timestamp (markdown heading only -- see
        # _build_jsonlines_entry's docstring for why JSONLines computes its
        # own, separate timestamp instead of reusing this one).
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Render the entry first, then write it in a single f.write() call.
        # This narrows the interleaving window when two hook processes
        # append to the same file concurrently, and means a mid-render
        # exception (e.g. a bad format string) leaves no half-written
        # record in the audit log -- a truncated record would be worse than
        # a missing one for a security tool's audit trail (TOO-19 m5 review
        # finding #19).
        if logging_format == "jsonlines":
            rendered = json.dumps(_build_jsonlines_entry(record)) + "\n\n"
        else:
            rendered = _render_markdown_entry(record, timestamp)

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(rendered)

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
