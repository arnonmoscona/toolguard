"""
Per-day warning deduplication for toolguard takeover mode.

Suppresses repeated warnings using date-stamped marker files (one per
calendar day, not per Claude Code session -- the module name predates this
distinction and keeping it avoids a wider rename; TOO-45).
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
    filename = f".toolguard-warned-{marker_date.strftime('%Y-%m-%d')}"
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
        print(
            f"Warning: Failed to create marker file {today_marker}: {e}",
            file=sys.stderr,
        )
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
        for marker_file in logs_dir.glob(".toolguard-warned-*"):
            # Extract date from filename
            try:
                # Format: .toolguard-warned-YYYY-MM-DD
                date_str = marker_file.name.replace(".toolguard-warned-", "")
                file_date = date.fromisoformat(date_str)

                # Delete if older than cutoff
                if file_date < cutoff_date:
                    marker_file.unlink()
            except ValueError, OSError:
                # Skip files that don't match expected format or can't be deleted
                continue
    except OSError:
        # If we can't list directory, just continue
        pass


def issue_takeover_warning(
    logs_dir: Path, to_stdout: bool = True, cleanup_days: Optional[int] = 7
) -> None:
    """
    Issue an informational notice that takeover mode is active.

    This notice is INFORMATIONAL, not actionable, so as of TOO-8 Phase 4 it is
    NO LONGER persisted to any toolguard log stream. It is emitted to stderr for
    visibility and recorded once per day via a date-stamped marker file so
    repeated invocations within a day stay quiet.

    Notice message:
    [TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are
    bypassed. Toolguard is the sole authority for permission decisions. If toolguard
    fails or is misconfigured, blanket allows in native config will be exposed.

    Args:
        logs_dir: Directory where marker files are stored.
        to_stdout: NOTE -- despite the name, this gates writing to STDERR, not
            stdout (the notice goes to ``sys.stderr``). The name is retained for
            backward compatibility with existing callers/tests; treat it as
            "emit the stderr echo". If True (default), write the notice to
            stderr. The stderr echo always fires (it is not deduplicated) so the
            notice stays visible every invocation.
        cleanup_days: Number of days of marker files to keep (None = no cleanup,
            default: 7).
    """
    warning_message = (
        "[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are "
        "bypassed. Toolguard is the sole authority for permission decisions. If toolguard "
        "fails or is misconfigured, blanket allows in native config will be exposed."
    )

    # Always write to stderr for visibility (every invocation; not deduplicated).
    if to_stdout:
        print(warning_message, file=sys.stderr)

    # Maintain the once-per-day marker (no log file is written anymore).
    if marker_exists_for_today(logs_dir):
        return

    try:
        create_marker_file(logs_dir)

        # Cleanup old markers if requested
        if cleanup_days is not None:
            cleanup_old_markers(logs_dir, cleanup_days)
    except OSError:
        # If we can't create marker, continue (notice was still emitted).
        pass
