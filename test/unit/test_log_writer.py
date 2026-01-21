"""
Unit tests for toolguard logging functionality.

Tests the logging functionality including file creation, format, and content.
"""

import contextlib
import io
import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from toolguard.log_writer import log_command


class TestLogging(unittest.TestCase):
    """Test logging functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Enable logging for tests
        self.env_patcher = patch.dict('os.environ', {'CHECKED_BASH_LOGGING_ON': 'true'})
        self.env_patcher.start()

    def tearDown(self):
        """Clean up after tests."""
        self.env_patcher.stop()

    def test_log_file_creation_with_correct_name_format(self):
        """Test that log file is created with correct name format (toolguard-YYYY-MM-DD.md)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command
            log_command('git status', 'executed', log_dir=log_dir)

            # Check that log file was created with correct name
            expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.md'
            log_file = log_dir / expected_filename

            self.assertTrue(log_file.exists(), f'Log file {log_file} was not created')

    def test_markdown_structure_is_correct(self):
        """Test that markdown structure includes headers and formatting."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command
            log_command('git status', 'executed', log_dir=log_dir)

            # Read the log file
            expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.md'
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check markdown structure
            self.assertIn('##', content, 'Missing markdown header')
            self.assertIn('**Status**:', content, 'Missing status field')
            self.assertIn('**Command**:', content, 'Missing command field')
            self.assertIn('`git status`', content, 'Command not formatted as code')

    def test_content_includes_command_status_violated_rules(self):
        """Test that content includes command, status, and violated rules."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a refused command with violated rules
            violated_rules = ['git push:*', '**/.env/**']
            log_command('git push origin main', 'refused', violated_rules=violated_rules, log_dir=log_dir)

            # Read the log file
            expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.md'
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that all required information is present
            self.assertIn('REFUSED', content, 'Status not found')
            self.assertIn('git push origin main', content, 'Command not found')
            self.assertIn('Violated Rules', content, 'Violated rules section not found')
            self.assertIn('git push:*', content, 'First violated rule not found')
            self.assertIn('**/.env/**', content, 'Second violated rule not found')

    def test_multiple_log_entries_append_correctly(self):
        """Test that multiple log entries append to the same file."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log multiple commands
            log_command('git status', 'executed', log_dir=log_dir)
            log_command('ls -la', 'executed', log_dir=log_dir)
            log_command('rm file.txt', 'refused', violated_rules=['rm *'], log_dir=log_dir)

            # Read the log file
            expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.md'
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that all commands are present
            self.assertIn('git status', content, 'First command not found')
            self.assertIn('ls -la', content, 'Second command not found')
            self.assertIn('rm file.txt', content, 'Third command not found')

            # Count the number of entries (by counting markdown headers)
            header_count = content.count('## ')
            self.assertEqual(header_count, 3, f'Expected 3 entries, found {header_count}')

    def test_logging_respects_disabled_flag(self):
        """Test that logging is disabled when CHECKED_BASH_LOGGING_ON is false."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Disable logging
            with patch.dict('os.environ', {'CHECKED_BASH_LOGGING_ON': 'false'}):
                log_command('git status', 'executed', log_dir=log_dir)

                # Check that no log file was created
                log_files = list(log_dir.glob('toolguard-*.md'))
                self.assertEqual(len(log_files), 0, 'Log file should not be created when logging is disabled')

    def test_jsonlines_format(self):
        """Test that JSONLines format works correctly."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Set logging format to jsonlines
            with patch.dict('os.environ', {'CHECKED_BASH_LOGGING_FORMAT': 'jsonlines'}):
                log_command('git status', 'executed', log_dir=log_dir)

                # Check that log file was created with .jsonlines extension
                expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.jsonlines'
                log_file = log_dir / expected_filename

                self.assertTrue(log_file.exists(), f'JSONLines log file {log_file} was not created')

                # Read and parse the JSON content
                content = log_file.read_text().strip()
                lines = [line for line in content.split('\n') if line.strip()]
                self.assertGreater(len(lines), 0, 'No JSON entries found')

                # Parse the first entry
                entry = json.loads(lines[0])
                self.assertIn('timestamp', entry)
                self.assertIn('status', entry)
                self.assertIn('command', entry)
                self.assertIn('violated_rules', entry)
                self.assertEqual(entry['status'], 'executed')
                self.assertEqual(entry['command'], 'git status')

    def test_log_without_violated_rules(self):
        """Test that logging works correctly when no violated rules are provided."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)

            # Log a command without violated rules
            log_command('git status', 'executed', log_dir=log_dir)

            # Read the log file
            expected_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.md'
            log_file = log_dir / expected_filename
            content = log_file.read_text()

            # Check that violated rules section is not present
            self.assertNotIn('Violated Rules', content, 'Violated rules should not be present')

    def test_log_directory_must_exist(self):
        """Test that logging fails gracefully if log directory does not exist."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Use a non-existent subdirectory
            log_dir = Path(tmpdir) / 'nonexistent'

            # Capture stderr
            stderr_capture = io.StringIO()
            with contextlib.redirect_stderr(stderr_capture):
                # Attempt to log - should exit with error
                with self.assertRaises(SystemExit) as cm:
                    log_command('git status', 'executed', log_dir=log_dir)

                self.assertEqual(cm.exception.code, 1, 'Should exit with code 1 when log directory does not exist')

            # Verify error message in stderr
            stderr_output = stderr_capture.getvalue()
            self.assertIn('Logging directory does not exist', stderr_output)


if __name__ == '__main__':
    unittest.main()
