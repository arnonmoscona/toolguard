"""Unit tests for toolguard.session_warnings: the takeover-mode-active notice."""

import unittest
from io import StringIO
from unittest.mock import patch

from toolguard.session_warnings import issue_takeover_warning


class TestIssueTakeoverWarning(unittest.TestCase):
    """Test the takeover-active notice: an unconditional stderr echo, never throttled."""

    def test_writes_to_stderr(self):
        """
        Given to_stdout=True
        When issue_takeover_warning runs
        Then the notice is written to stderr
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            issue_takeover_warning(to_stdout=True)

        self.assertIn("Takeover mode is active", err.getvalue())

    def test_does_not_write_when_to_stdout_is_false(self):
        """
        Given to_stdout=False
        When issue_takeover_warning runs
        Then nothing is printed
        """
        with patch("builtins.print") as mock_print:
            issue_takeover_warning(to_stdout=False)

        mock_print.assert_not_called()

    def test_does_not_call_log_warning(self):
        """
        Given issue_takeover_warning emits the notice
        When toolguard.error_log.log_warning is patched
        Then it is never called -- the notice is stderr-only, never
             persisted to a toolguard log stream
        """
        with patch("toolguard.error_log.log_warning") as mock_log:
            issue_takeover_warning(to_stdout=True)

        mock_log.assert_not_called()

    def test_notice_message_content(self):
        """
        Given issue_takeover_warning runs with to_stdout=True
        When the printed text is collected
        Then it contains the expected takeover-mode phrases
        """
        with patch("builtins.print") as mock_print:
            issue_takeover_warning(to_stdout=True)

        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)

        self.assertIn("TOOLGUARD WARNING", printed)
        self.assertIn("Takeover mode is active", printed)
        self.assertIn("native permission prompts are bypassed", printed)
        self.assertIn("sole authority", printed)

    def test_default_argument_writes_the_notice(self):
        """
        Given no explicit to_stdout argument
        When issue_takeover_warning runs
        Then the notice is still written (the default is True)
        """
        with patch("sys.stderr", new_callable=StringIO) as err:
            issue_takeover_warning()

        self.assertIn("Takeover mode is active", err.getvalue())


if __name__ == "__main__":
    unittest.main()
