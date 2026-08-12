"""
Error, warning, conflict, and crash logging for toolguard.

Errors, warnings and conflicts each get their OWN date-stamped Markdown file
in the caller-supplied log directory, so the streams stay separable:
``toolguard-error-YYYY-MM-DD.md``, ``toolguard-warning-YYYY-MM-DD.md``,
``toolguard-conflict-YYYY-MM-DD.md``. The similarly named high-volume
resolution log, ``toolguard-YYYY-MM-DD.*``, is :mod:`toolguard.log_writer`'s,
not this module's.

:func:`log_crash` is a DIFFERENT concern: full unhandled-exception detail
(type, message, traceback), written to a fixed, user-level directory rather
than to the caller's.
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def log_warning(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log an actionable warning to stderr and ``toolguard-warning-YYYY-MM-DD.md``.

    For conditions the user can and should act on.

    Args:
        message: Warning message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry("WARNING", "warning", message, corrective_steps, log_dir)


def log_error(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log a real error to stderr and ``toolguard-error-YYYY-MM-DD.md``.

    Genuine failures only -- warnings and conflicts have their own streams.

    Args:
        message: Error message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry("ERROR", "error", message, corrective_steps, log_dir)


def log_conflict(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log a configuration conflict to stderr and ``toolguard-conflict-YYYY-MM-DD.md``.

    A conflict is a disagreement within the configuration that toolguard
    resolved by policy rather than refusing to run.

    Args:
        message: Human-readable conflict description.
        corrective_steps: Suggested corrective actions.
        log_dir: Directory where log files should be written.
    """
    _log_entry("CONFLICT", "conflict", message, corrective_steps, log_dir)


def _log_entry(
    level: str, stream: str, message: str, corrective_steps: str, log_dir: Path
) -> None:
    """
    Write one Markdown entry to ``<log_dir>/toolguard-<stream>-YYYY-MM-DD.md``.

    The ``## <timestamp> - <level>`` heading is parsed, not merely displayed:
    :func:`toolguard.session_start._count_conflict_entries` counts conflict
    entries by matching it, and a reformatted heading silently counts zero.

    A failed write is swallowed -- a stderr warning, nothing raised. A ``log_dir``
    that cannot be created is not: ``mkdir`` runs before both the stderr echo and
    the ``try``, so the caller sees the exception and nothing is echoed.

    Args:
        level: Display label for the entry ('WARNING', 'ERROR', 'CONFLICT').
        stream: File-stream selector ('warning', 'error', 'conflict'); selects
            the ``toolguard-<stream>-...`` filename.
        message: Message to log.
        corrective_steps: Suggested corrective actions.
        log_dir: Directory where log files should be written.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    log_filename = f"toolguard-{stream}-{datetime.now().strftime('%Y-%m-%d')}.md"
    log_file = log_dir / log_filename

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    log_content = f"## {timestamp} - {level}\n\n"
    log_content += f"**Message**: {message}\n\n"
    log_content += f"**Corrective Steps**: {corrective_steps}\n\n"
    log_content += "---\n\n"

    print(f"[{level}] {message}", file=sys.stderr)
    print(f"Corrective steps: {corrective_steps}", file=sys.stderr)

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

    Takes no ``log_dir``: the directory is fixed and created on demand, so this
    works even when the exception happened before or during config resolution.
    Each crash gets its own file, ``toolguard-error-<timestamp>.md`` at second
    granularity, with a ``-2``, ``-3``, ... suffix on a same-second collision so
    an earlier report is never silently overwritten.

    A failure while writing the report (permissions, disk full, ...) is caught:
    a short warning goes to stderr and ``None`` is returned, so a caller already
    handling a failure is not handed a second one.

    Args:
        exc: The exception instance that was caught. ``type(exc).__name__`` and
            ``str(exc)`` are recorded, along with the full current traceback
            (via :func:`traceback.format_exc`, so this must be called while the
            exception's context is still active).
        context: Whatever in-flight state is available at the catch site (e.g.
            ``tool_name``/``tool_input``), rendered as Markdown bullets. May be
            empty if little or nothing was resolved yet.
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
