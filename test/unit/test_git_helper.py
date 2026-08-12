"""
Unit tests for toolguard._git -- the shared git-subprocess helper.

Its two callers, :mod:`toolguard.install_update` and
:mod:`toolguard.install_provenance`, are checked here rather than in their own
test files: the subject is the cross-module delegation, which neither owns.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import _git, constants, install_provenance, install_update


class TestSharedConstants(unittest.TestCase):
    """The distribution name and git timeout come from toolguard.constants."""

    def test_update_check_dist_name_is_the_shared_constant(self):
        """
        Given install_update.py's distribution_name() fallback
        When compared to toolguard.constants.DIST_NAME
        Then it is that value
        """
        self.assertIs(install_update._DEFAULT_DIST_NAME, constants.DIST_NAME)

    def test_install_provenance_dist_name_is_the_shared_constant(self):
        """
        Given install_provenance.py's default project/distribution name
        When compared to toolguard.constants.DIST_NAME
        Then it is that value
        """
        self.assertIs(install_provenance._DEFAULT_NAME, constants.DIST_NAME)

    def test_run_git_default_timeout_is_the_shared_constant(self):
        """
        Given toolguard._git.run_git's default timeout parameter (keyword-only)
        When compared to toolguard.constants.GIT_TIMEOUT_SECONDS
        Then it is that value
        """
        default_timeout = _git.run_git.__kwdefaults__["timeout"]
        self.assertIs(default_timeout, constants.GIT_TIMEOUT_SECONDS)


class TestRunGitSharedHelper(unittest.TestCase):
    """Both modules' git-touching functions delegate through run_git."""

    def test_update_check_local_repo_head_uses_run_git(self):
        """
        Given install_update.local_repo_head() is called
        When toolguard._git.run_git is patched to a spy
        Then it is invoked with a "-C <repo> rev-parse HEAD" argv
        """
        with patch("toolguard.install_update.run_git", wraps=_git.run_git) as spy:
            spy.return_value = None  # short-circuit: no real git needed
            install_update.local_repo_head(Path("/nonexistent-repo"))
        spy.assert_called_once()
        (args,), _kwargs = spy.call_args
        self.assertEqual(args, ["-C", "/nonexistent-repo", "rev-parse", "HEAD"])

    def test_install_provenance_git_subtree_is_clean_uses_run_git(self):
        """
        Given _git_subtree_is_clean() is called
        When toolguard._git.run_git is patched to a spy
        Then it is invoked with a "-C <repo> status --porcelain -- <subtree>"
            argv
        """
        with patch("toolguard.install_provenance.run_git", wraps=_git.run_git) as spy:
            spy.return_value = None
            install_provenance._git_subtree_is_clean(
                Path("/nonexistent-repo"), "toolguard"
            )
        spy.assert_called_once()
        (args,), _kwargs = spy.call_args
        self.assertEqual(
            args,
            ["-C", "/nonexistent-repo", "status", "--porcelain", "--", "toolguard"],
        )

    def test_run_git_returns_none_on_launch_failure_without_raising(self):
        """
        Given the underlying subprocess.run raises OSError (git missing)
        When run_git executes
        Then it returns None rather than propagating the exception
        """
        with patch.object(_git.subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(_git.run_git(["status"]))


if __name__ == "__main__":
    unittest.main()
