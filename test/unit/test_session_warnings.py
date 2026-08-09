"""
Unit tests for toolguard.session_warnings: the takeover-mode-active notice.

The once-per-day facade (``OncePer`` / ``day`` / ``Repeat``) moved to
:mod:`toolguard.once_per` and is tested in test_once_per.py (TOO-45
punch-list #01, conceptual overhaul, second pass). issue_takeover_warning no
longer touches the claim store at all -- see its docstring -- so the tests
below cover only its own, much smaller contract: an unconditional stderr
print, gated by a single boolean.

TOO-45 punch-list #01 deleted issue_takeover_warning's project/logs_dir
parameters and its once-per-day housekeeping trigger (`cleanup_days`, the
`_SWEEP_KEY` claim, and the sqlite3-unavailable degraded notice that
housekeeping used to produce). The tests that pinned exactly that deleted
behaviour were removed rather than adapted -- there is no store interaction
left to test at this layer:
  - test_stdout_always_written_even_with_marker (pinned: a pre-existing
    sweep-key claim not affecting the stderr echo)
  - test_claims_once_per_day_for_housekeeping (pinned: the sweep-key claim
    being held after a call)
  - test_cleanup_skipped_when_none (pinned: the cleanup_days=None no-op)
  - test_cleanup_days_controls_claim_ttl (pinned: cleanup_days setting the
    housekeeping claim's ttl)
  - test_handles_claim_failure_gracefully (pinned: fail-soft behaviour when
    the claim store's parent could not be created)
  - test_none_project_still_writes_notice_and_stores_nothing (pinned: a
    project parameter that no longer exists)
  - test_warns_when_sqlite_unavailable / test_no_sqlite_warning_when_
    cleanup_disabled (pinned: the housekeeping-triggered degraded notice)
"""

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
        Given issue_takeover_warning runs
        Then log_warning is never called -- the notice is stderr-only,
             never persisted to a toolguard log stream (TOO-8 Phase 4)
        """
        with patch("toolguard.error_log.log_warning") as mock_log:
            issue_takeover_warning(to_stdout=True)

        mock_log.assert_not_called()

    def test_notice_message_content(self):
        """
        Given issue_takeover_warning emits the notice to stderr
        Then the message contains the expected takeover-mode phrases
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
