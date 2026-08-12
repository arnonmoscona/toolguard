"""Unit tests for the working-tree cleanliness guard (toolguard.tools.working_tree)."""

import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from toolguard.tools.working_tree import WorkingTreeStatus, working_tree_status


def _completed(returncode: int, stdout: str = "") -> SimpleNamespace:
    """Build a stand-in for subprocess.run's CompletedProcess."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class TestWorkingTreeStatus(unittest.TestCase):
    """Classification of git working-tree state for the apply gate."""

    def test_clean_repo_is_safe(self):
        """
        Given git status returns success with no output
        When working_tree_status is called
        Then the tree is reported as a clean git repo that is safe to apply to.
        """
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run",
            return_value=_completed(0, ""),
        ):
            status = working_tree_status(Path("/repo"))
        self.assertTrue(status.is_git_repo)
        self.assertTrue(status.is_clean)
        self.assertTrue(status.is_safe_to_apply)
        self.assertEqual(status.dirty_paths, ())

    def test_dirty_repo_lists_paths_and_is_not_safe(self):
        """
        Given git status reports modified and untracked files
        When working_tree_status is called
        Then it is a git repo, not clean, not safe to apply, and the changed paths
            are extracted with the status prefix stripped.
        """
        porcelain = " M toolguard/config.py\n?? new_file.py\n"
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run",
            return_value=_completed(0, porcelain),
        ):
            status = working_tree_status(Path("/repo"))
        self.assertTrue(status.is_git_repo)
        self.assertFalse(status.is_clean)
        self.assertFalse(status.is_safe_to_apply)
        self.assertEqual(status.dirty_paths, ("toolguard/config.py", "new_file.py"))

    def test_non_repo_is_not_safe(self):
        """
        Given git status exits non-zero (not a repository)
        When working_tree_status is called
        Then it reports not-a-git-repo and not safe to apply.
        """
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run",
            return_value=_completed(128, ""),
        ):
            status = working_tree_status(Path("/tmp/not-a-repo"))
        self.assertFalse(status.is_git_repo)
        self.assertFalse(status.is_safe_to_apply)

    def test_git_missing_is_handled_gracefully(self):
        """
        Given the git binary is missing or the subprocess errors
        When working_tree_status is called
        Then it returns a non-repo status rather than raising.
        """
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run",
            side_effect=OSError("git not found"),
        ):
            status = working_tree_status(Path("/repo"))
        self.assertIsInstance(status, WorkingTreeStatus)
        self.assertFalse(status.is_git_repo)
        self.assertFalse(status.is_safe_to_apply)

    def test_subprocess_timeout_is_handled(self):
        """
        Given the git subprocess times out
        When working_tree_status is called
        Then the timeout is caught and reported as a non-repo status.
        """
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10),
        ):
            status = working_tree_status(Path("/repo"))
        self.assertFalse(status.is_git_repo)


if __name__ == "__main__":
    unittest.main()
