"""
Unit tests for toolguard.update_check (TOO-16).

Cover the update-check exit-code contract (0 up-to-date / 1 update-available /
2 unknown), the ``--upgrade`` and ``--quiet`` flags, the offline/not-a-git-install
fallbacks, and the parsing of installed origin and remote HEAD. All side effects
(metadata, git, uv) are stubbed -- no real network, subprocess, or install runs.
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import update_check


class TestInstalledOrigin(unittest.TestCase):
    """Reading ``(url, commit_id)`` from the package's direct_url.json."""

    def _dist_returning(self, text):
        """Return a fake distribution whose read_text yields ``text``."""
        return SimpleNamespace(read_text=lambda name: text)

    def test_git_install_returns_url_and_commit(self):
        """
        Given a direct_url.json with a vcs_info commit_id and url
        When installed_origin runs
        Then it returns the (url, commit_id) tuple
        """
        payload = (
            '{"url":"https://github.com/x/toolguard",'
            '"vcs_info":{"vcs":"git","commit_id":"abc123"}}'
        )
        with patch.object(
            update_check.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            self.assertEqual(
                update_check.installed_origin(),
                ("https://github.com/x/toolguard", "abc123"),
            )

    def test_non_git_install_without_vcs_info_returns_none(self):
        """
        Given a direct_url.json with no vcs_info (e.g. an editable/registry install)
        When installed_origin runs
        Then it returns None
        """
        payload = '{"url":"file:///somewhere","dir_info":{"editable":true}}'
        with patch.object(
            update_check.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            self.assertIsNone(update_check.installed_origin())

    def test_missing_direct_url_returns_none(self):
        """
        Given a distribution whose read_text returns None (no direct_url.json)
        When installed_origin runs
        Then it returns None
        """
        with patch.object(
            update_check.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(None),
        ):
            self.assertIsNone(update_check.installed_origin())

    def test_metadata_lookup_failure_returns_none(self):
        """
        Given importlib.metadata raises (package not found)
        When installed_origin runs
        Then it returns None rather than propagating the error
        """
        with patch.object(
            update_check.importlib.metadata,
            "distribution",
            side_effect=update_check.importlib.metadata.PackageNotFoundError(
                "toolguard"
            ),
        ):
            self.assertIsNone(update_check.installed_origin())


class TestRemoteHead(unittest.TestCase):
    """Parsing the remote HEAD sha from ``git ls-remote`` output."""

    def test_parses_sha_from_ls_remote_output(self):
        """
        Given git ls-remote succeeds with a HEAD line
        When remote_head runs
        Then it returns the leading 40-char sha
        """
        completed = SimpleNamespace(
            returncode=0, stdout="deadbeef0123\tHEAD\n", stderr=""
        )
        with patch.object(update_check.subprocess, "run", return_value=completed):
            self.assertEqual(
                update_check.remote_head("https://example/x"), "deadbeef0123"
            )

    def test_nonzero_exit_returns_none(self):
        """
        Given git ls-remote exits non-zero (e.g. repo unreachable)
        When remote_head runs
        Then it returns None
        """
        completed = SimpleNamespace(returncode=128, stdout="", stderr="fatal")
        with patch.object(update_check.subprocess, "run", return_value=completed):
            self.assertIsNone(update_check.remote_head("https://example/x"))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is missing or the call times out
        When remote_head runs
        Then it returns None rather than raising (offline-safe)
        """
        with patch.object(
            update_check.subprocess, "run", side_effect=OSError("no git")
        ):
            self.assertIsNone(update_check.remote_head("https://example/x"))

    def test_empty_output_returns_none(self):
        """
        Given git ls-remote succeeds but prints nothing
        When remote_head runs
        Then it returns None
        """
        completed = SimpleNamespace(returncode=0, stdout="\n", stderr="")
        with patch.object(update_check.subprocess, "run", return_value=completed):
            self.assertIsNone(update_check.remote_head("https://example/x"))


class TestCheck(unittest.TestCase):
    """The core _check logic: exit codes, flags, and printed output."""

    def _run_check(self, quiet=False, do_upgrade=False):
        """Run _check capturing (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = update_check._check(quiet=quiet, do_upgrade=do_upgrade)
        return code, out.getvalue(), err.getvalue()

    def test_up_to_date_returns_zero(self):
        """
        Given the installed commit equals the remote HEAD
        When _check runs
        Then it returns exit code 0 and reports up to date
        """
        with (
            patch.object(
                update_check, "installed_origin", return_value=("url", "samecommit")
            ),
            patch.object(update_check, "remote_head", return_value="samecommit"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertIn("up to date", out)

    def test_quiet_suppresses_up_to_date_output(self):
        """
        Given up to date and --quiet
        When _check runs
        Then it returns 0 and prints nothing to stdout
        """
        with (
            patch.object(
                update_check, "installed_origin", return_value=("url", "same")
            ),
            patch.object(update_check, "remote_head", return_value="same"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertEqual(out, "")

    def test_update_available_returns_one_and_prints_command(self):
        """
        Given the installed commit differs from the remote HEAD
        When _check runs
        Then it returns exit code 1 and prints the upgrade command with the dist name
        """
        with (
            patch.object(
                update_check, "installed_origin", return_value=("url", "oldcommit")
            ),
            patch.object(update_check, "remote_head", return_value="newcommit"),
            patch.object(update_check, "distribution_name", return_value="toolguard"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)
        self.assertIn("uv tool upgrade toolguard", out)

    def test_update_available_with_quiet_still_prints(self):
        """
        Given an update is available and --quiet
        When _check runs
        Then it still prints (quiet only suppresses the up-to-date case)
        """
        with (
            patch.object(update_check, "installed_origin", return_value=("url", "old")),
            patch.object(update_check, "remote_head", return_value="new"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)

    def test_printed_command_uses_distribution_name(self):
        """
        Given a non-default distribution name (e.g. a future PyPI rename)
        When _check reports an available update
        Then the printed upgrade command uses that distribution name
        """
        with (
            patch.object(update_check, "installed_origin", return_value=("url", "old")),
            patch.object(update_check, "remote_head", return_value="new"),
            patch.object(
                update_check, "distribution_name", return_value="claude-toolguard"
            ),
        ):
            _, out, _ = self._run_check()
        self.assertIn("uv tool upgrade claude-toolguard", out)

    def test_not_a_git_install_returns_unknown(self):
        """
        Given installed_origin is None (not a git install)
        When _check runs
        Then it returns exit code 2 with guidance to use uv tool upgrade
        """
        with patch.object(update_check, "installed_origin", return_value=None):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        self.assertIn("uv tool upgrade", err)

    def test_remote_unreachable_returns_unknown(self):
        """
        Given the remote HEAD cannot be fetched (offline)
        When _check runs
        Then it returns exit code 2 with an offline message
        """
        with (
            patch.object(
                update_check, "installed_origin", return_value=("url", "commit")
            ),
            patch.object(update_check, "remote_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        self.assertIn("Could not reach", err)

    def test_upgrade_flag_runs_upgrade_only_when_behind(self):
        """
        Given an update is available and do_upgrade is True
        When _check runs
        Then run_upgrade is invoked and its exit code is returned
        """
        with (
            patch.object(update_check, "installed_origin", return_value=("url", "old")),
            patch.object(update_check, "remote_head", return_value="new"),
            patch.object(update_check, "run_upgrade", return_value=0) as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_called_once()
        self.assertEqual(code, 0)

    def test_upgrade_flag_does_not_run_when_up_to_date(self):
        """
        Given up to date and do_upgrade is True
        When _check runs
        Then run_upgrade is NOT invoked and exit code is 0
        """
        with (
            patch.object(
                update_check, "installed_origin", return_value=("url", "same")
            ),
            patch.object(update_check, "remote_head", return_value="same"),
            patch.object(update_check, "run_upgrade") as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_not_called()
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)


class TestRunUpgrade(unittest.TestCase):
    """Running 'uv tool upgrade' and surfacing its result."""

    def test_returns_subprocess_exit_code(self):
        """
        Given uv tool upgrade runs and exits 0
        When run_upgrade runs
        Then it returns 0
        """
        with patch.object(
            update_check.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0),
        ):
            self.assertEqual(update_check.run_upgrade("toolguard"), 0)

    def test_uv_missing_returns_unknown(self):
        """
        Given uv is not installed (launch raises OSError)
        When run_upgrade runs
        Then it returns EXIT_UNKNOWN instead of raising
        """
        with patch.object(update_check.subprocess, "run", side_effect=OSError("no uv")):
            self.assertEqual(
                update_check.run_upgrade("toolguard"), update_check.EXIT_UNKNOWN
            )


class TestMain(unittest.TestCase):
    """The argparse entry point wires flags through to _check and exits."""

    def test_main_exits_with_check_code(self):
        """
        Given _check returns exit code 1
        When main runs with no flags
        Then main exits with code 1 and passes quiet=False, do_upgrade=False
        """
        with (
            patch.object(update_check.sys, "argv", ["toolguard-update-check"]),
            patch.object(update_check, "_check", return_value=1) as mock_check,
        ):
            with self.assertRaises(SystemExit) as ctx:
                update_check.main()
        self.assertEqual(ctx.exception.code, 1)
        mock_check.assert_called_once_with(quiet=False, do_upgrade=False)

    def test_main_passes_quiet_and_upgrade_flags(self):
        """
        Given --quiet and --upgrade on the command line
        When main runs
        Then it calls _check with quiet=True and do_upgrade=True
        """
        argv = ["toolguard-update-check", "--quiet", "--upgrade"]
        with (
            patch.object(update_check.sys, "argv", argv),
            patch.object(update_check, "_check", return_value=0) as mock_check,
        ):
            with self.assertRaises(SystemExit) as ctx:
                update_check.main()
        self.assertEqual(ctx.exception.code, 0)
        mock_check.assert_called_once_with(quiet=True, do_upgrade=True)


if __name__ == "__main__":
    unittest.main()
