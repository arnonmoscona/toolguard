"""
Session-based warning system for toolguard takeover mode.

Provides warning deduplication using date-stamped marker files to avoid
repeated warnings to the error log while maintaining visibility on stdout.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


def get_marker_file_path(logs_dir: Path, marker_date: date) -> Path:
    """
    Get the path to a marker file for a specific date.

    Marker files use the format: .toolguard-warned-YYYY-MM-DD

    Args:
        logs_dir: Directory where marker files are stored
        marker_date: Date for the marker file

    Returns:
        Path to the marker file
    """
    filename = f'.toolguard-warned-{marker_date.strftime("%Y-%m-%d")}'
    return logs_dir / filename


def marker_exists_for_today(logs_dir: Path) -> bool:
    """
    Check if a warning marker file exists for today.

    Args:
        logs_dir: Directory where marker files are stored

    Returns:
        True if marker file exists for today, False otherwise
    """
    today_marker = get_marker_file_path(logs_dir, date.today())
    return today_marker.exists()


def create_marker_file(logs_dir: Path) -> None:
    """
    Create a marker file for today to track that warning was issued.

    Creates the logs directory if it doesn't exist.

    Args:
        logs_dir: Directory where marker files are stored

    Raises:
        OSError: If unable to create marker file or directory
    """
    # Create log directory if it doesn't exist
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Create marker file for today
    today_marker = get_marker_file_path(logs_dir, date.today())
    try:
        today_marker.touch()
    except OSError as e:
        print(f'Warning: Failed to create marker file {today_marker}: {e}', file=sys.stderr)
        raise


def cleanup_old_markers(logs_dir: Path, days: int = 7) -> None:
    """
    Remove marker files older than the specified number of days.

    This prevents accumulation of old marker files over time.

    Args:
        logs_dir: Directory where marker files are stored
        days: Number of days to keep (default: 7)
    """
    if not logs_dir.exists():
        return

    cutoff_date = date.today() - timedelta(days=days)

    # Find all marker files
    try:
        for marker_file in logs_dir.glob('.toolguard-warned-*'):
            # Extract date from filename
            try:
                # Format: .toolguard-warned-YYYY-MM-DD
                date_str = marker_file.name.replace('.toolguard-warned-', '')
                file_date = date.fromisoformat(date_str)

                # Delete if older than cutoff
                if file_date < cutoff_date:
                    marker_file.unlink()
            except (ValueError, OSError):
                # Skip files that don't match expected format or can't be deleted
                continue
    except OSError:
        # If we can't list directory, just continue
        pass


def issue_takeover_warning(
    logs_dir: Path, to_stdout: bool = True, to_error_log: bool = True, cleanup_days: Optional[int] = 7
) -> None:
    """
    Issue a warning that takeover mode is active.

    Warning is always written to stdout for visibility. Writing to error log
    is deduplicated using marker files (once per day).

    Warning message:
    [TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are
    bypassed. Toolguard is the sole authority for permission decisions. If toolguard
    fails or is misconfigured, blanket allows in native config will be exposed.

    Args:
        logs_dir: Directory where logs and marker files are stored
        to_stdout: If True, write warning to stdout (default: True)
        to_error_log: If True, write warning to error log (deduplicated) (default: True)
        cleanup_days: Number of days of marker files to keep (None = no cleanup, default: 7)
    """
    warning_message = (
        "[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are "
        'bypassed. Toolguard is the sole authority for permission decisions. If toolguard '
        'fails or is misconfigured, blanket allows in native config will be exposed.'
    )

    corrective_steps = (
        'This is informational. Ensure toolguard_hook.toml is properly configured with '
        'appropriate allow/deny patterns for your use case.'
    )

    # Always write to stdout for visibility
    if to_stdout:
        print(warning_message, file=sys.stderr)

    # Write to error log with deduplication
    if to_error_log:
        # Check if we've already warned today
        if marker_exists_for_today(logs_dir):
            # Already warned today - skip error log
            return

        # Issue warning to error log
        from toolguard.error_log import log_warning

        log_warning(warning_message, corrective_steps, logs_dir)

        # Create marker file to track that we warned today
        try:
            create_marker_file(logs_dir)

            # Cleanup old markers if requested
            if cleanup_days is not None:
                cleanup_old_markers(logs_dir, cleanup_days)
        except OSError:
            # If we can't create marker, continue (warning was still logged)
            pass
