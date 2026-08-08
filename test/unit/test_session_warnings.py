"""
Unit tests for toolguard session warnings.

Tests marker file creation, deduplication, cleanup, and warning issuance.
"""

import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.session_warnings import (
    cleanup_old_markers,
    create_marker_file,
    get_marker_file_path,
    issue_takeover_warning,
    marker_exists_for_today,
)


class TestGetMarkerFilePath(unittest.TestCase):
    """Test marker file path generation."""

    def test_generates_correct_path(self):
        """
        Given a logs directory and a specific date
        When get_marker_file_path builds the path
        Then it is logs_dir/.toolguard-warned-YYYY-MM-DD for that date
        """
        logs_dir = Path("/tmp/logs")
        test_date = date(2025, 1, 15)

        result = get_marker_file_path(logs_dir, test_date)

        expected = logs_dir / ".toolguard-warned-2025-01-15"
        self.assertEqual(result, expected)

    def test_uses_iso_date_format(self):
        """
        Given a logs directory and a date
        When get_marker_file_path builds the path
        Then the marker name ends with the ISO date (YYYY-MM-DD)
        """
        logs_dir = Path("/var/log")
        test_date = date(2024, 12, 31)

        result = get_marker_file_path(logs_dir, test_date)

        self.assertTrue(result.name.endswith("2024-12-31"))

    def test_includes_leading_dot(self):
        """
        Given a logs directory and today's date
        When get_marker_file_path builds the path
        Then the marker name starts with '.toolguard-warned-', making it a hidden file
        """
        logs_dir = Path("/logs")
        test_date = date.today()

        result = get_marker_file_path(logs_dir, test_date)

        self.assertTrue(result.name.startswith(".toolguard-warned-"))


class TestMarkerExistsForToday(unittest.TestCase):
    """Test marker file existence checking."""

    def test_returns_true_when_marker_exists(self):
        """
        Given a marker file for today exists in the logs directory
        When marker_exists_for_today is checked
        Then it returns True
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            result = marker_exists_for_today(logs_dir)

            self.assertTrue(result)

    def test_returns_false_when_marker_missing(self):
        """
        Given an empty logs directory with no marker for today
        When marker_exists_for_today is checked
        Then it returns False
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            result = marker_exists_for_today(logs_dir)

            self.assertFalse(result)

    def test_returns_false_when_directory_missing(self):
        """
        Given a logs directory path that does not exist
        When marker_exists_for_today is checked
        Then it returns False without error
        """
        logs_dir = Path("/nonexistent/directory")

        result = marker_exists_for_today(logs_dir)

        self.assertFalse(result)

    def test_ignores_old_markers(self):
        """
        Given only a marker for yesterday exists
        When marker_exists_for_today is checked
        Then it returns False because only today's marker counts
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker for yesterday
            yesterday = date.today() - timedelta(days=1)
            old_marker = get_marker_file_path(logs_dir, yesterday)
            old_marker.touch()

            result = marker_exists_for_today(logs_dir)

            self.assertFalse(result)


class TestCreateMarkerFile(unittest.TestCase):
    """Test marker file creation."""

    def test_creates_marker_file(self):
        """
        Given an existing logs directory
        When create_marker_file runs
        Then today's marker file exists
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            create_marker_file(logs_dir)

            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())

    def test_creates_directory_if_missing(self):
        """
        Given a logs directory that does not yet exist
        When create_marker_file runs
        Then the directory is created and today's marker exists inside it
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / "new_logs"
            self.assertFalse(logs_dir.exists())

            create_marker_file(logs_dir)

            self.assertTrue(logs_dir.exists())
            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())

    def test_idempotent_creation(self):
        """
        Given a logs directory
        When create_marker_file is called twice
        Then no error occurs and today's marker exists
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            create_marker_file(logs_dir)
            create_marker_file(logs_dir)  # Second call should be safe

            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())


class TestCleanupOldMarkers(unittest.TestCase):
    """Test marker file cleanup."""

    def test_removes_old_markers(self):
        """
        Given markers for 10 days ago, 3 days ago, and today
        When cleanup_old_markers runs with a 7-day threshold
        Then the 10-day-old marker is removed while the recent and today markers remain
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create markers for various dates
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            recent_date = date.today() - timedelta(days=3)
            recent_marker = get_marker_file_path(logs_dir, recent_date)
            recent_marker.touch()

            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            # Cleanup with 7-day threshold
            cleanup_old_markers(logs_dir, days=7)

            # Old marker should be removed
            self.assertFalse(old_marker.exists())

            # Recent markers should remain
            self.assertTrue(recent_marker.exists())
            self.assertTrue(today_marker.exists())

    def test_keeps_markers_within_threshold(self):
        """
        Given markers for each of the last 5 days
        When cleanup_old_markers runs with a 7-day threshold
        Then all five markers are kept
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create markers for last 5 days
            for days_ago in range(5):
                marker_date = date.today() - timedelta(days=days_ago)
                marker = get_marker_file_path(logs_dir, marker_date)
                marker.touch()

            # Cleanup with 7-day threshold
            cleanup_old_markers(logs_dir, days=7)

            # All markers should still exist
            for days_ago in range(5):
                marker_date = date.today() - timedelta(days=days_ago)
                marker = get_marker_file_path(logs_dir, marker_date)
                self.assertTrue(marker.exists())

    def test_handles_missing_directory(self):
        """
        Given a logs directory that does not exist
        When cleanup_old_markers runs
        Then it completes without raising an exception
        """
        logs_dir = Path("/nonexistent/directory")

        # Should not raise exception
        cleanup_old_markers(logs_dir, days=7)

    def test_ignores_non_marker_files(self):
        """
        Given non-marker files and an old marker in the logs directory
        When cleanup_old_markers runs with a 7-day threshold
        Then the non-marker files survive and only the old marker is removed
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create some non-marker files
            (logs_dir / "some_log.txt").touch()
            (logs_dir / ".other_hidden_file").touch()

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            # Cleanup
            cleanup_old_markers(logs_dir, days=7)

            # Non-marker files should still exist
            self.assertTrue((logs_dir / "some_log.txt").exists())
            self.assertTrue((logs_dir / ".other_hidden_file").exists())

            # Old marker should be removed
            self.assertFalse(old_marker.exists())

    def test_handles_malformed_marker_names(self):
        """
        Given a marker file whose date portion is not a valid date
        When cleanup_old_markers runs
        Then it does not raise and the malformed file is left in place
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker with malformed date
            malformed = logs_dir / ".toolguard-warned-invalid-date"
            malformed.touch()

            # Should not raise exception
            cleanup_old_markers(logs_dir, days=7)

            # Malformed file should still exist (not deleted)
            self.assertTrue(malformed.exists())


class TestIssueTakeoverWarning(unittest.TestCase):
    """Test the takeover-active notice (stderr + once-per-day marker only).

    TOO-8 Phase 4: the takeover notice is informational, NOT actionable, so it is
    no longer persisted to any toolguard log stream. These tests pin the new
    contract: stderr echo every time, a once-per-day marker, and NO log file
    write whatsoever.
    """

    def test_writes_to_stdout(self):
        """
        Given to_stdout=True
        When issue_takeover_warning runs
        Then the notice is written to stderr
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch("sys.stderr") as mock_stderr:
                issue_takeover_warning(logs_dir, to_stdout=True)

                # Should have printed notice
                mock_stderr.write.assert_called()

    def test_does_not_write_any_log_file(self):
        """
        Given no marker exists yet
        When issue_takeover_warning runs
        Then NO toolguard log file (error/warning/conflict) is created -- the
             notice is stderr + marker only
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            issue_takeover_warning(logs_dir, to_stdout=False)

            # No persisted log stream should be written by the notice.
            log_files = [p.name for p in logs_dir.glob("toolguard-*.md")]
            self.assertEqual(log_files, [])

    def test_does_not_call_log_warning(self):
        """
        Given no marker exists yet
        When issue_takeover_warning runs
        Then log_warning is never called (the notice no longer logs)
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch("toolguard.error_log.log_warning") as mock_log:
                issue_takeover_warning(logs_dir, to_stdout=False)

                mock_log.assert_not_called()

    def test_stdout_always_written_even_with_marker(self):
        """
        Given today's marker already exists, with to_stdout=True
        When issue_takeover_warning runs
        Then the notice is still written to stderr despite the existing marker
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker
            create_marker_file(logs_dir)

            with patch("sys.stderr") as mock_stderr:
                issue_takeover_warning(logs_dir, to_stdout=True)

                # Should still print to stderr even though marker exists
                mock_stderr.write.assert_called()

    def test_creates_marker(self):
        """
        Given no marker exists
        When issue_takeover_warning runs
        Then today's marker is created (once-per-day guard)
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            issue_takeover_warning(logs_dir, to_stdout=False)

            # Marker should be created
            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())

    def test_cleanup_called_when_specified(self):
        """
        Given an old marker exists and cleanup_days=7 is passed
        When issue_takeover_warning runs
        Then the old marker is cleaned up
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            issue_takeover_warning(logs_dir, to_stdout=False, cleanup_days=7)

            # Old marker should be cleaned up
            self.assertFalse(old_marker.exists())

    def test_cleanup_skipped_when_none(self):
        """
        Given an old marker exists and cleanup_days=None is passed
        When issue_takeover_warning runs
        Then the old marker is left in place (cleanup is skipped)
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            issue_takeover_warning(logs_dir, to_stdout=False, cleanup_days=None)

            # Old marker should NOT be cleaned up
            self.assertTrue(old_marker.exists())

    def test_notice_message_content(self):
        """
        Given no existing marker
        When issue_takeover_warning emits the notice to stderr
        Then the message contains the expected takeover-mode phrases
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                issue_takeover_warning(logs_dir, to_stdout=True)

                printed = " ".join(
                    str(c.args[0]) for c in mock_print.call_args_list if c.args
                )

                # Check key phrases in message
                self.assertIn("TOOLGUARD WARNING", printed)
                self.assertIn("Takeover mode is active", printed)
                self.assertIn("native permission prompts are bypassed", printed)
                self.assertIn("sole authority", printed)

    def test_handles_marker_creation_failure(self):
        """
        Given create_marker_file raises an OSError
        When issue_takeover_warning runs
        Then no exception propagates (the notice is best-effort)
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch(
                "toolguard.session_warnings.create_marker_file",
                side_effect=OSError("Permission denied"),
            ):
                # Should not raise exception
                issue_takeover_warning(logs_dir, to_stdout=False)


if __name__ == "__main__":
    unittest.main()
