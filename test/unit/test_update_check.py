"""
Unit tests for toolguard.update_check (TOO-16).

Cover the update-check exit-code contract (0 up-to-date / 1 update-available /
2 unknown), the ``--upgrade`` and ``--quiet`` flags, the offline/not-a-git-install
fallbacks, and the parsing of installed origin and remote HEAD. All side effects
(metadata, git, uv) are stubbed -- no real network, subprocess, or install runs.

New in this update (local-kind support):
- ``detect_install`` resolves git / local / unknown from direct_url.json.
- Local kind: editable vs non-editable, up-to-date vs behind.
- Local repo discovered via file:// URL and via __file__ walk-up.
- Unknown kind falls through to exit 2.
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import update_check
from toolguard.update_check import InstallInfo, InstallKind


class TestInstalledOrigin(unittest.TestCase):
    """Reading ``(url, commit_id)`` from the package's direct_url.json (legacy API)."""

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


class TestDetectInstall(unittest.TestCase):
    """
    Tests for detect_install: resolves git / local / unknown from direct_url.json
    or from __file__ walk-up.
    """

    def _dist_returning(self, text):
        """Return a fake distribution whose read_text yields ``text``."""
        return SimpleNamespace(read_text=lambda name: text)

    def test_git_vcs_info_returns_git_kind(self):
        """
        Given a direct_url.json with vcs_info.commit_id and a https url
        When detect_install runs
        Then it returns InstallInfo with kind=GIT and the url and commit
        """
        payload = (
            '{"url":"https://github.com/x/toolguard",'
            '"vcs_info":{"vcs":"git","commit_id":"gitcommit1"}}'
        )
        with patch.object(
            update_check.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.GIT)
        self.assertEqual(info.url, "https://github.com/x/toolguard")
        self.assertEqual(info.installed_commit, "gitcommit1")

    def test_dir_info_with_valid_file_url_and_git_worktree_returns_local_kind(self):
        """
        Given a direct_url.json with dir_info pointing to a valid git worktree
        When detect_install runs
        Then it returns InstallInfo with kind=LOCAL and the resolved repo_path
        """
        payload = '{"url":"file:///home/user/toolguard","dir_info":{"editable":false}}'
        with (
            patch.object(
                update_check.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(update_check, "is_git_worktree", return_value=True),
            patch.object(update_check, "local_repo_head", return_value="localhead1"),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.LOCAL)
        self.assertEqual(info.repo_path, Path("/home/user/toolguard"))
        self.assertEqual(info.installed_commit, "localhead1")
        self.assertFalse(info.editable)

    def test_dir_info_editable_true_sets_editable_flag(self):
        """
        Given a direct_url.json with dir_info.editable=true
        When detect_install runs and the path is a git worktree
        Then it returns InstallInfo with kind=LOCAL and editable=True
        """
        payload = '{"url":"file:///home/user/toolguard","dir_info":{"editable":true}}'
        with (
            patch.object(
                update_check.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(update_check, "is_git_worktree", return_value=True),
            patch.object(update_check, "local_repo_head", return_value="edithead1"),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.LOCAL)
        self.assertTrue(info.editable)

    def test_dir_info_path_not_git_worktree_returns_unknown(self):
        """
        Given a direct_url.json with dir_info but the path is not a git worktree
        When detect_install runs
        Then it returns InstallInfo with kind=UNKNOWN
        """
        payload = '{"url":"file:///some/non-git/path","dir_info":{"editable":false}}'
        with (
            patch.object(
                update_check.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(update_check, "is_git_worktree", return_value=False),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)

    def test_no_direct_url_falls_back_to_file_walk_up(self):
        """
        Given no direct_url.json but the module file lives in a git worktree
        When detect_install runs
        Then it returns InstallInfo with kind=LOCAL discovered via __file__ walk-up
        """
        fake_repo = Path("/home/user/toolguard")
        with (
            patch.object(
                update_check.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(None),
            ),
            patch.object(update_check, "_walk_up_to_git_root", return_value=fake_repo),
            patch.object(update_check, "is_git_worktree", return_value=True),
            patch.object(update_check, "local_repo_head", return_value="walkuphead1"),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.LOCAL)
        self.assertEqual(info.repo_path, fake_repo)
        self.assertEqual(info.installed_commit, "walkuphead1")

    def test_no_direct_url_and_no_git_root_returns_unknown(self):
        """
        Given no direct_url.json and __file__ is not inside any git work tree
        When detect_install runs
        Then it returns InstallInfo with kind=UNKNOWN
        """
        with (
            patch.object(
                update_check.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(None),
            ),
            patch.object(update_check, "_walk_up_to_git_root", return_value=None),
        ):
            info = update_check.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)


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


class TestLocalRepoHead(unittest.TestCase):
    """Parsing HEAD sha from a local checkout via ``git rev-parse HEAD``."""

    def test_returns_head_sha_from_local_repo(self):
        """
        Given git rev-parse HEAD succeeds in the local repo
        When local_repo_head is called
        Then it returns the HEAD sha
        """
        completed = SimpleNamespace(returncode=0, stdout="localsha123\n", stderr="")
        with patch.object(update_check.subprocess, "run", return_value=completed):
            result = update_check.local_repo_head(Path("/repo"))
        self.assertEqual(result, "localsha123")

    def test_nonzero_exit_returns_none(self):
        """
        Given git rev-parse exits non-zero (e.g. not a repo)
        When local_repo_head is called
        Then it returns None
        """
        completed = SimpleNamespace(returncode=128, stdout="", stderr="fatal")
        with patch.object(update_check.subprocess, "run", return_value=completed):
            self.assertIsNone(update_check.local_repo_head(Path("/repo")))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is not available (OSError)
        When local_repo_head is called
        Then it returns None without raising
        """
        with patch.object(
            update_check.subprocess, "run", side_effect=OSError("no git")
        ):
            self.assertIsNone(update_check.local_repo_head(Path("/repo")))


class TestLocalRemoteHead(unittest.TestCase):
    """Parsing the remote origin HEAD sha via ``git ls-remote origin HEAD``."""

    def test_returns_remote_sha_from_local_repo(self):
        """
        Given git ls-remote origin HEAD succeeds in the local repo
        When local_remote_head is called
        Then it returns the remote HEAD sha
        """
        completed = SimpleNamespace(
            returncode=0, stdout="remotesha456\tHEAD\n", stderr=""
        )
        with patch.object(update_check.subprocess, "run", return_value=completed):
            result = update_check.local_remote_head(Path("/repo"))
        self.assertEqual(result, "remotesha456")

    def test_nonzero_exit_returns_none(self):
        """
        Given git ls-remote exits non-zero (e.g. no origin or offline)
        When local_remote_head is called
        Then it returns None
        """
        completed = SimpleNamespace(returncode=128, stdout="", stderr="fatal")
        with patch.object(update_check.subprocess, "run", return_value=completed):
            self.assertIsNone(update_check.local_remote_head(Path("/repo")))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is not available (OSError)
        When local_remote_head is called
        Then it returns None without raising (offline-safe)
        """
        with patch.object(
            update_check.subprocess, "run", side_effect=OSError("no git")
        ):
            self.assertIsNone(update_check.local_remote_head(Path("/repo")))


class TestCheck(unittest.TestCase):
    """The core _check logic: exit codes, flags, and printed output."""

    def _run_check(self, quiet=False, do_upgrade=False):
        """Run _check capturing (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = update_check._check(quiet=quiet, do_upgrade=do_upgrade)
        return code, out.getvalue(), err.getvalue()

    def _git_info(self, commit="installed123"):
        """Return an InstallInfo for a git kind install."""
        return InstallInfo(
            kind=InstallKind.GIT,
            url="https://github.com/x/toolguard",
            installed_commit=commit,
        )

    def _local_info(self, commit="localhead1", editable=False):
        """Return an InstallInfo for a local kind install."""
        return InstallInfo(
            kind=InstallKind.LOCAL,
            installed_commit=commit,
            repo_path=Path("/home/user/toolguard"),
            editable=editable,
        )

    # --- git kind tests ---

    def test_git_up_to_date_returns_zero(self):
        """
        Given a git install where the installed commit equals the remote HEAD
        When _check runs
        Then it returns exit code 0 and reports up to date
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(update_check, "remote_head", return_value="same"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertIn("up to date", out)

    def test_git_quiet_suppresses_up_to_date_output(self):
        """
        Given a git install up to date and --quiet
        When _check runs
        Then it returns 0 and prints nothing to stdout
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(update_check, "remote_head", return_value="same"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertEqual(out, "")

    def test_git_update_available_returns_one_and_prints_command(self):
        """
        Given a git install where the installed commit differs from the remote HEAD
        When _check runs
        Then it returns exit code 1 and prints the upgrade command with the dist name
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("oldcommit")
            ),
            patch.object(update_check, "remote_head", return_value="newcommit"),
            patch.object(update_check, "distribution_name", return_value="toolguard"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)
        self.assertIn("uv tool upgrade toolguard", out)

    def test_git_update_available_with_quiet_still_prints(self):
        """
        Given a git install with an available update and --quiet
        When _check runs
        Then it still prints (quiet only suppresses the up-to-date case)
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(update_check, "remote_head", return_value="new"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)

    def test_git_printed_command_uses_distribution_name(self):
        """
        Given a non-default distribution name (e.g. a future PyPI rename) and a git install
        When _check reports an available update
        Then the printed upgrade command uses that distribution name
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(update_check, "remote_head", return_value="new"),
            patch.object(
                update_check, "distribution_name", return_value="claude-toolguard"
            ),
        ):
            _, out, _ = self._run_check()
        self.assertIn("uv tool upgrade claude-toolguard", out)

    def test_git_remote_unreachable_returns_unknown(self):
        """
        Given a git install where the remote HEAD cannot be fetched (offline)
        When _check runs
        Then it returns exit code 2 with an offline message
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("commit")
            ),
            patch.object(update_check, "remote_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        self.assertIn("Could not reach", err)

    def test_git_upgrade_flag_runs_upgrade_only_when_behind(self):
        """
        Given a git install with an update available and do_upgrade is True
        When _check runs
        Then run_upgrade is invoked and its exit code is returned
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(update_check, "remote_head", return_value="new"),
            patch.object(update_check, "run_upgrade", return_value=0) as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_called_once()
        self.assertEqual(code, 0)

    def test_git_upgrade_flag_does_not_run_when_up_to_date(self):
        """
        Given a git install up to date and do_upgrade is True
        When _check runs
        Then run_upgrade is NOT invoked and exit code is 0
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(update_check, "remote_head", return_value="same"),
            patch.object(update_check, "run_upgrade") as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_not_called()
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)

    # --- local kind tests ---

    def test_local_up_to_date_returns_zero(self):
        """
        Given a local install where HEAD equals the remote origin HEAD
        When _check runs
        Then it returns exit code 0 and reports up to date with the checkout path
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info("same")
            ),
            patch.object(update_check, "local_repo_head", return_value="same"),
            patch.object(update_check, "local_remote_head", return_value="same"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertIn("up to date", out)

    def test_local_quiet_suppresses_up_to_date_output(self):
        """
        Given a local install up to date and --quiet
        When _check runs
        Then it returns 0 and prints nothing to stdout
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info("same")
            ),
            patch.object(update_check, "local_repo_head", return_value="same"),
            patch.object(update_check, "local_remote_head", return_value="same"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, update_check.EXIT_UP_TO_DATE)
        self.assertEqual(out, "")

    def test_local_behind_returns_one_and_prints_git_pull(self):
        """
        Given a local install where HEAD is behind the remote origin HEAD
        When _check runs
        Then it returns exit code 1 and prints git pull instructions
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info("old")
            ),
            patch.object(update_check, "local_repo_head", return_value="old"),
            patch.object(update_check, "local_remote_head", return_value="new"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)
        self.assertIn("git", out.lower())
        self.assertIn("pull", out.lower())

    def test_local_non_editable_prints_uv_tool_install_force(self):
        """
        Given a non-editable local install that is behind
        When _check runs
        Then the output includes 'uv tool install --force' as a reinstall step
        """
        with (
            patch.object(
                update_check,
                "detect_install",
                return_value=self._local_info("old", editable=False),
            ),
            patch.object(update_check, "local_repo_head", return_value="old"),
            patch.object(update_check, "local_remote_head", return_value="new"),
        ):
            _, out, _ = self._run_check()
        self.assertIn("uv tool install --force", out)

    def test_local_editable_does_not_print_uv_tool_install(self):
        """
        Given an editable local install that is behind
        When _check runs
        Then the output does NOT include 'uv tool install --force' (git pull suffices)
        """
        with (
            patch.object(
                update_check,
                "detect_install",
                return_value=self._local_info("old", editable=True),
            ),
            patch.object(update_check, "local_repo_head", return_value="old"),
            patch.object(update_check, "local_remote_head", return_value="new"),
        ):
            _, out, _ = self._run_check()
        self.assertNotIn("uv tool install --force", out)

    def test_local_upgrade_flag_does_not_auto_run_prints_manual_note(self):
        """
        Given a local install that is behind and do_upgrade is True
        When _check runs
        Then run_upgrade is NOT called and a manual-steps note is printed to stderr
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info("old")
            ),
            patch.object(update_check, "local_repo_head", return_value="old"),
            patch.object(update_check, "local_remote_head", return_value="new"),
            patch.object(update_check, "run_upgrade") as mock_upgrade,
        ):
            code, _, err = self._run_check(do_upgrade=True)
        mock_upgrade.assert_not_called()
        self.assertEqual(code, update_check.EXIT_UPDATE_AVAILABLE)
        # A note about not auto-running should be in stderr
        self.assertIn("manual", err.lower())

    def test_local_remote_unreachable_returns_unknown(self):
        """
        Given a local install where the remote origin HEAD cannot be fetched (offline)
        When _check runs
        Then it returns exit code 2 with an offline message
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info("head")
            ),
            patch.object(update_check, "local_repo_head", return_value="head"),
            patch.object(update_check, "local_remote_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        self.assertIn("Could not reach", err)

    def test_local_head_unreadable_returns_unknown(self):
        """
        Given a local install where git rev-parse HEAD fails
        When _check runs
        Then it returns exit code 2 with a clear message
        """
        with (
            patch.object(
                update_check, "detect_install", return_value=self._local_info()
            ),
            patch.object(update_check, "local_repo_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        # Error message should mention the checkout
        self.assertTrue(len(err) > 0)

    # --- unknown kind tests ---

    def test_unknown_install_returns_exit_two(self):
        """
        Given detect_install returns kind=UNKNOWN (no direct_url, no discoverable repo)
        When _check runs
        Then it returns exit code 2 with guidance on manual update
        """
        with patch.object(
            update_check,
            "detect_install",
            return_value=InstallInfo(kind=InstallKind.UNKNOWN),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, update_check.EXIT_UNKNOWN)
        # Error message should guide the user
        self.assertTrue(len(err) > 0)


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

    def test_main_help_exits_zero(self):
        """
        Given --help on the command line
        When main runs
        Then argparse exits with code 0 (informational, not an error)
        """
        with (
            patch.object(
                update_check.sys, "argv", ["toolguard-update-check", "--help"]
            ),
            # Suppress the help text from appearing in test output
            patch("sys.stdout", io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as ctx:
                update_check.main()
        self.assertEqual(ctx.exception.code, 0)


# Legacy shim test: installed_origin is still used by some existing callers.
class TestInstalledOriginLegacyBehavior(unittest.TestCase):
    """
    Validate that installed_origin continues to return None for non-git installs
    even after the refactor to detect_install.
    """

    def test_installed_origin_still_returns_none_for_local_install(self):
        """
        Given a direct_url.json with dir_info (local install)
        When installed_origin is called (legacy API)
        Then it still returns None (consistent with pre-refactor behavior)
        """
        payload = '{"url":"file:///home/user/toolguard","dir_info":{"editable":true}}'
        dist = SimpleNamespace(read_text=lambda name: payload)
        with patch.object(
            update_check.importlib.metadata, "distribution", return_value=dist
        ):
            self.assertIsNone(update_check.installed_origin())


if __name__ == "__main__":
    unittest.main()
