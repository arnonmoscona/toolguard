"""
Error, warning, conflict, and crash logging for toolguard.

Each concern is routed to its OWN date-stamped log file so the streams stay
separable (TOO-8 Phase 4):

- ``logs/toolguard-error-YYYY-MM-DD.md``   -- real errors only (:func:`log_error`)
- ``logs/toolguard-warning-YYYY-MM-DD.md`` -- actionable warnings (:func:`log_warning`)
- ``logs/toolguard-conflict-YYYY-MM-DD.md`` -- config conflicts (:func:`log_conflict`)

The high-volume resolution log (``logs/toolguard-YYYY-MM-DD.md``) is handled
separately by :mod:`toolguard.log_writer`. Every entry preserves the existing
per-file Markdown format and echoes a concise line to stderr for visibility.

:func:`log_crash` is a DIFFERENT concern from the three streams above: it captures
full, unhandled-exception detail (type, message, traceback) for the hook's
top-level ``except`` clauses. Those can fire before a project's configuration --
and therefore its ``log_dir`` -- is even resolvable, so it writes to the fixed,
user-level ``~/.toolguard/errors/`` directory instead of a project-scoped log
(mirrors :data:`toolguard.tools.decision_ledger.USER_LEDGER_PATH`'s use of
``Path.home() / ".toolguard"``).
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def log_warning(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log an actionable warning to stderr and the WARNING log file.

    Writes to ``logs/toolguard-warning-YYYY-MM-DD.md``. Use this for conditions
    the user can and should act on (e.g. both a ``.toml`` and a ``.json`` config
    present, an unsupported or ungoverned tool referenced in permissions).

    Args:
        message: Warning message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry("WARNING", "warning", message, corrective_steps, log_dir)


def log_error(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log a real error to stderr and the ERROR log file.

    Writes to ``logs/toolguard-error-YYYY-MM-DD.md``. Reserved for genuine
    failures, never for warnings or conflicts.

    Args:
        message: Error message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry("ERROR", "error", message, corrective_steps, log_dir)


def log_conflict(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log a configuration conflict to stderr and the CONFLICT log file.

    Writes to ``logs/toolguard-conflict-YYYY-MM-DD.md``. Conflict logging is ON
    by default. A conflict is a MORE-specific level's ``allow`` overriding a
    LESS-specific level's ``deny`` for the same command/path; the decision still
    follows more-specific-wins, and this entry records both sides' provenance so
    a human or LLM can understand the override. The entry is human/LLM-readable
    Markdown -- NOT a structured/machine-readable record.

    Args:
        message: Human-readable conflict description (cites both provenances).
        corrective_steps: Suggested corrective actions.
        log_dir: Directory where log files should be written.
    """
    _log_entry("CONFLICT", "conflict", message, corrective_steps, log_dir)


def _log_entry(
    level: str, stream: str, message: str, corrective_steps: str, log_dir: Path
) -> None:
    """
    Write a single Markdown log entry to the per-concern stream file.

    Each stream writes to ``logs/toolguard-<stream>-YYYY-MM-DD.md`` and echoes a
    concise line to stderr. The Markdown entry format is shared across all
    streams for consistency.

    Args:
        level: Display label for the entry ('WARNING', 'ERROR', 'CONFLICT').
        stream: File-stream selector ('warning', 'error', 'conflict'); selects
            the ``toolguard-<stream>-...`` filename.
        message: Message to log.
        corrective_steps: Suggested corrective actions.
        log_dir: Directory where log files should be written.
    """
    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate date-stamped, per-stream filename
    log_filename = f"toolguard-{stream}-{datetime.now().strftime('%Y-%m-%d')}.md"
    log_file = log_dir / log_filename

    # Prepare log entry
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Format log entry in markdown (preserved per-file format)
    log_content = f"## {timestamp} - {level}\n\n"
    log_content += f"**Message**: {message}\n\n"
    log_content += f"**Corrective Steps**: {corrective_steps}\n\n"
    log_content += "---\n\n"

    # Echo to stderr for visibility
    print(f"[{level}] {message}", file=sys.stderr)
    print(f"Corrective steps: {corrective_steps}", file=sys.stderr)

    # Write to file
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(log_content)
    except Exception as e:
        print(f"Warning: Failed to write to log file {log_file}: {e}", file=sys.stderr)


def log_crash(
    exc: BaseException, context: Dict[str, Any], caught_as: str
) -> Optional[Path]:
    """
    Write a full crash report for an unhandled exception to ``~/.toolguard/errors/``.

    Unlike :func:`log_error`/:func:`log_warning`/:func:`log_conflict`, this does
    NOT depend on a resolved project ``log_dir`` -- it writes to the fixed,
    user-level ``~/.toolguard/errors/`` directory (created on demand; does not
    require ``init-state`` to have run first), so it works even when the
    exception happened before or during config resolution. Each crash gets its
    OWN Markdown file, named ``toolguard-error-<timestamp>.md`` (second
    granularity). If two crashes land in the same rendered second, a
    monotonically increasing ``-2``, ``-3``, ... suffix is appended so an
    earlier crash report is never silently overwritten (same disambiguation
    scheme as ``create_backup`` in
    :mod:`toolguard.permission_migration`, reimplemented locally here to
    avoid pulling in that module's config-resolution machinery from a path
    that must keep working even when config resolution itself is what
    failed).

    Never raises: if writing the report fails for any reason (permissions, disk
    full, etc.), the failure is caught, a short warning is printed to stderr,
    and ``None`` is returned -- callers invoke this from inside an
    already-failing ``except`` block and must not have that made worse.

    Args:
        exc: The exception instance that was caught. ``type(exc).__name__`` and
            ``str(exc)`` are recorded, along with the full current traceback
            (via :func:`traceback.format_exc`, so this must be called while the
            exception's context is still active).
        context: Whatever in-flight state is available at the catch site (e.g.
            ``tool_name``/``tool_input``), rendered as readable ``key: value``
            lines. May be empty if little or nothing was resolved yet.
        caught_as: Short label identifying which ``except`` clause caught the
            exception (e.g. ``"json.JSONDecodeError"``, ``"ValueError"``,
            ``"unexpected Exception"``).

    Returns:
        The ``Path`` of the crash report written, or ``None`` if writing failed.
    """
    now = datetime.now()
    errors_dir = Path.home() / ".toolguard" / "errors"

    try:
        errors_dir.mkdir(parents=True, exist_ok=True)

        # Disambiguate same-second collisions with a "-2", "-3", ... suffix so
        # an earlier crash report is never clobbered.
        base_name = f"toolguard-error-{now.strftime('%Y-%m-%d-%H%M%S')}"
        crash_file = errors_dir / f"{base_name}.md"
        sequence = 2
        while crash_file.exists():
            crash_file = errors_dir / f"{base_name}-{sequence}.md"
            sequence += 1

        if context:
            context_block = "\n".join(
                f"- **{key}**: {value}" for key, value in context.items()
            )
        else:
            context_block = "(no context available)"

        content = (
            "# Toolguard crash report\n\n"
            f"**Timestamp**: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"**Caught as**: {caught_as}\n\n"
            f"**Exception type**: {type(exc).__name__}\n\n"
            f"**Exception message**: {exc}\n\n"
            "## Context\n\n"
            f"{context_block}\n\n"
            "## Traceback\n\n"
            "```\n"
            f"{traceback.format_exc()}"
            "```\n"
        )

        crash_file.write_text(content, encoding="utf-8")
        print(f"[CRASH] Full details written to {crash_file}", file=sys.stderr)
        return crash_file
    except Exception as e:
        print(f"Warning: Failed to write crash report: {e}", file=sys.stderr)
        return None
