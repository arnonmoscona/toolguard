"""Error and warning logging for toolguard."""

import sys
from datetime import datetime
from pathlib import Path


def log_warning(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log a warning message to both stdout and date-stamped log file.

    Writes to logs/toolguard-error-YYYY-MM-DD.md

    Args:
        message: Warning message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry('WARNING', message, corrective_steps, log_dir)


def log_error(message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Log an error message to both stdout and date-stamped log file.

    Writes to logs/toolguard-error-YYYY-MM-DD.md

    Args:
        message: Error message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    _log_entry('ERROR', message, corrective_steps, log_dir)


def _log_entry(level: str, message: str, corrective_steps: str, log_dir: Path) -> None:
    """
    Internal function to write a log entry.

    Args:
        level: Log level ('WARNING' or 'ERROR')
        message: Message to log
        corrective_steps: Suggested corrective actions
        log_dir: Directory where log files should be written
    """
    # Create log directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)

    # Generate date-stamped filename
    log_filename = f'toolguard-error-{datetime.now().strftime("%Y-%m-%d")}.md'
    log_file = log_dir / log_filename

    # Prepare log entry
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Format log entry in markdown
    log_content = f'## {timestamp} - {level}\n\n'
    log_content += f'**Message**: {message}\n\n'
    log_content += f'**Corrective Steps**: {corrective_steps}\n\n'
    log_content += '---\n\n'

    # Write to stdout
    print(f'[{level}] {message}', file=sys.stderr)
    print(f'Corrective steps: {corrective_steps}', file=sys.stderr)

    # Write to file
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_content)
    except Exception as e:
        print(f'Warning: Failed to write to log file {log_file}: {e}', file=sys.stderr)
