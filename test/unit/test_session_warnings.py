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
        """Test that marker file path uses correct format."""
        logs_dir = Path('/tmp/logs')
        test_date = date(2025, 1, 15)

        result = get_marker_file_path(logs_dir, test_date)

        expected = logs_dir / '.toolguard-warned-2025-01-15'
        self.assertEqual(result, expected)

    def test_uses_iso_date_format(self):
        """Test that date format is YYYY-MM-DD."""
        logs_dir = Path('/var/log')
        test_date = date(2024, 12, 31)

        result = get_marker_file_path(logs_dir, test_date)

        self.assertTrue(result.name.endswith('2024-12-31'))

    def test_includes_leading_dot(self):
        """Test that marker file name starts with dot (hidden file)."""
        logs_dir = Path('/logs')
        test_date = date.today()

        result = get_marker_file_path(logs_dir, test_date)

        self.assertTrue(result.name.startswith('.toolguard-warned-'))


class TestMarkerExistsForToday(unittest.TestCase):
    """Test marker file existence checking."""

    def test_returns_true_when_marker_exists(self):
        """Test detection of existing marker file."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            today_marker = get_marker_file_path(logs_dir, date.today())
            today_marker.touch()

            result = marker_exists_for_today(logs_dir)

            self.assertTrue(result)

    def test_returns_false_when_marker_missing(self):
        """Test detection of missing marker file."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            result = marker_exists_for_today(logs_dir)

            self.assertFalse(result)

    def test_returns_false_when_directory_missing(self):
        """Test handling of non-existent log directory."""
        logs_dir = Path('/nonexistent/directory')

        result = marker_exists_for_today(logs_dir)

        self.assertFalse(result)

    def test_ignores_old_markers(self):
        """Test that old marker files don't affect today's check."""
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
        """Test that marker file is created."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            create_marker_file(logs_dir)

            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())

    def test_creates_directory_if_missing(self):
        """Test that log directory is created if it doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir) / 'new_logs'
            self.assertFalse(logs_dir.exists())

            create_marker_file(logs_dir)

            self.assertTrue(logs_dir.exists())
            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())

    def test_idempotent_creation(self):
        """Test that creating marker twice doesn't cause errors."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            create_marker_file(logs_dir)
            create_marker_file(logs_dir)  # Second call should be safe

            today_marker = get_marker_file_path(logs_dir, date.today())
            self.assertTrue(today_marker.exists())


class TestCleanupOldMarkers(unittest.TestCase):
    """Test marker file cleanup."""

    def test_removes_old_markers(self):
        """Test that markers older than threshold are removed."""
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
        """Test that markers within threshold are kept."""
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
        """Test that cleanup handles non-existent directory gracefully."""
        logs_dir = Path('/nonexistent/directory')

        # Should not raise exception
        cleanup_old_markers(logs_dir, days=7)

    def test_ignores_non_marker_files(self):
        """Test that cleanup doesn't touch non-marker files."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create some non-marker files
            (logs_dir / 'some_log.txt').touch()
            (logs_dir / '.other_hidden_file').touch()

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            # Cleanup
            cleanup_old_markers(logs_dir, days=7)

            # Non-marker files should still exist
            self.assertTrue((logs_dir / 'some_log.txt').exists())
            self.assertTrue((logs_dir / '.other_hidden_file').exists())

            # Old marker should be removed
            self.assertFalse(old_marker.exists())

    def test_handles_malformed_marker_names(self):
        """Test that cleanup handles marker files with invalid date formats."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker with malformed date
            malformed = logs_dir / '.toolguard-warned-invalid-date'
            malformed.touch()

            # Should not raise exception
            cleanup_old_markers(logs_dir, days=7)

            # Malformed file should still exist (not deleted)
            self.assertTrue(malformed.exists())


class TestIssueTakeoverWarning(unittest.TestCase):
    """Test warning issuance with deduplication."""

    def test_writes_to_stdout(self):
        """Test that warning is written to stdout."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch('sys.stderr') as mock_stderr:
                issue_takeover_warning(logs_dir, to_stdout=True, to_error_log=False)

                # Should have printed warning
                mock_stderr.write.assert_called()

    def test_writes_to_error_log_first_time(self):
        """Test that warning is written to error log on first call."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch('toolguard.error_log.log_warning') as mock_log:
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True)

                # Should have logged warning
                mock_log.assert_called_once()
                args = mock_log.call_args[0]
                self.assertIn('Takeover mode is active', args[0])

    def test_skips_error_log_on_duplicate(self):
        """Test that error log is skipped if marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker to simulate previous warning
            create_marker_file(logs_dir)

            with patch('toolguard.error_log.log_warning') as mock_log:
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True)

                # Should NOT have logged warning
                mock_log.assert_not_called()

    def test_stdout_always_written(self):
        """Test that stdout is written even when marker exists."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create marker
            create_marker_file(logs_dir)

            with patch('sys.stderr') as mock_stderr:
                issue_takeover_warning(logs_dir, to_stdout=True, to_error_log=True)

                # Should still print to stdout even though marker exists
                mock_stderr.write.assert_called()

    def test_creates_marker_after_logging(self):
        """Test that marker is created after logging to prevent duplicates."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch('toolguard.error_log.log_warning'):
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True)

                # Marker should be created
                today_marker = get_marker_file_path(logs_dir, date.today())
                self.assertTrue(today_marker.exists())

    def test_cleanup_called_when_specified(self):
        """Test that cleanup is called when cleanup_days is specified."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            with patch('toolguard.error_log.log_warning'):
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True, cleanup_days=7)

                # Old marker should be cleaned up
                self.assertFalse(old_marker.exists())

    def test_cleanup_skipped_when_none(self):
        """Test that cleanup is skipped when cleanup_days is None."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            # Create old marker
            old_date = date.today() - timedelta(days=10)
            old_marker = get_marker_file_path(logs_dir, old_date)
            old_marker.touch()

            with patch('toolguard.error_log.log_warning'):
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True, cleanup_days=None)

                # Old marker should NOT be cleaned up
                self.assertTrue(old_marker.exists())

    def test_warning_message_content(self):
        """Test that warning message contains expected content."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch('toolguard.error_log.log_warning') as mock_log:
                issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True)

                args = mock_log.call_args[0]
                message = args[0]

                # Check key phrases in message
                self.assertIn('TOOLGUARD WARNING', message)
                self.assertIn('Takeover mode is active', message)
                self.assertIn('native permission prompts are bypassed', message)
                self.assertIn('sole authority', message)

    def test_handles_marker_creation_failure(self):
        """Test that warning still logs even if marker creation fails."""
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)

            with patch('toolguard.error_log.log_warning') as mock_log:
                with patch('toolguard.session_warnings.create_marker_file', side_effect=OSError('Permission denied')):
                    # Should not raise exception
                    issue_takeover_warning(logs_dir, to_stdout=False, to_error_log=True)

                    # Warning should still have been logged
                    mock_log.assert_called_once()


if __name__ == '__main__':
    unittest.main()
