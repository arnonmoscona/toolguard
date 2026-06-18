"""
Error, warning, and conflict logging for toolguard.

Each concern is routed to its OWN date-stamped log file so the streams stay
separable (TOO-8 Phase 4):

- ``logs/toolguard-error-YYYY-MM-DD.md``   -- real errors only (:func:`log_error`)
- ``logs/toolguard-warning-YYYY-MM-DD.md`` -- actionable warnings (:func:`log_warning`)
- ``logs/toolguard-conflict-YYYY-MM-DD.md`` -- config conflicts (:func:`log_conflict`)

The high-volume resolution log (``logs/toolguard-YYYY-MM-DD.md``) is handled
separately by :mod:`toolguard.log_writer`. Every entry preserves the existing
per-file Markdown format and echoes a concise line to stderr for visibility.
"""

import sys
from datetime import datetime
from pathlib import Path


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
    _log_entry('WARNING', 'warning', message, corrective_steps, log_dir)


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
    _log_entry('ERROR', 'error', message, corrective_steps, log_dir)


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
    _log_entry('CONFLICT', 'conflict', message, corrective_steps, log_dir)


def _log_entry(level: str, stream: str, message: str, corrective_steps: str, log_dir: Path) -> None:
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
    log_filename = f'toolguard-{stream}-{datetime.now().strftime("%Y-%m-%d")}.md'
    log_file = log_dir / log_filename

    # Prepare log entry
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Format log entry in markdown (preserved per-file format)
    log_content = f'## {timestamp} - {level}\n\n'
    log_content += f'**Message**: {message}\n\n'
    log_content += f'**Corrective Steps**: {corrective_steps}\n\n'
    log_content += '---\n\n'

    # Echo to stderr for visibility
    print(f'[{level}] {message}', file=sys.stderr)
    print(f'Corrective steps: {corrective_steps}', file=sys.stderr)

    # Write to file
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_content)
    except Exception as e:
        print(f'Warning: Failed to write to log file {log_file}: {e}', file=sys.stderr)
