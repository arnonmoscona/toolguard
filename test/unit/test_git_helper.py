"""
Unit tests for toolguard._git -- the shared git-subprocess helper (TOO-19 code
review 2026-08-02, Major finding M3).

``update_check.py`` and ``install_provenance.py`` each ran their own
``subprocess.run(["git", ...], capture_output=True, text=True, timeout=...)``
in a try/except at five call sites, independently catching the same exception
pair and duplicating the same argv-building shape. :func:`toolguard._git.run_git`
is the one place that boilerplate now lives, and :mod:`toolguard.constants`
holds the distribution-name and timeout values both modules previously
re-declared. This module verifies the deduplication itself -- that the two
call sites and the shared helper genuinely stay in sync rather than drifting
back into three near-identical copies -- which is why it lives here rather
than folded into either call site's own test file: neither
``test_update_check.py`` nor ``test_install_provenance.py`` is a natural home
for a cross-module identity/delegation guarantee about a module neither of
them owns.

No config-isolation machinery needed: every test here either patches
``toolguard._git.subprocess.run`` directly or compares object identity, with
zero file I/O and no ``toolguard.config`` discovery involved.
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from toolguard import _git, constants, install_provenance, update_check


class TestSharedConstants(unittest.TestCase):
    """Both modules now read the SAME constant objects, not re-declared copies."""

    def test_update_check_dist_name_is_the_shared_constant(self):
        """
        Given update_check.py's distribution_name() fallback
        When compared to toolguard.constants.DIST_NAME
        Then it is the identical object (not a re-declared duplicate)
        """
        self.assertIs(update_check._DEFAULT_DIST_NAME, constants.DIST_NAME)

    def test_install_provenance_dist_name_is_the_shared_constant(self):
        """
        Given install_provenance.py's default project/distribution name
        When compared to toolguard.constants.DIST_NAME
        Then it is the identical object (not a re-declared duplicate)
        """
        self.assertIs(install_provenance._DEFAULT_NAME, constants.DIST_NAME)

    def test_run_git_default_timeout_is_the_shared_constant(self):
        """
        Given toolguard._git.run_git's default timeout parameter (keyword-only)
        When compared to toolguard.constants.GIT_TIMEOUT_SECONDS
        Then it is the identical object (not a re-declared '10')
        """
        default_timeout = _git.run_git.__kwdefaults__["timeout"]
        self.assertIs(default_timeout, constants.GIT_TIMEOUT_SECONDS)


class TestRunGitSharedHelper(unittest.TestCase):
    """
    Both modules' git-touching functions now delegate through the single
    toolguard._git.run_git helper instead of five near-identical
    subprocess.run blocks.
    """

    def test_update_check_local_repo_head_uses_run_git(self):
        """
        Given local_repo_head() is called
        When toolguard._git.run_git is patched to a spy
        Then it is invoked with a "-C <repo> rev-parse HEAD" argv, proving
            update_check.py no longer runs its own subprocess.run for this
        """
        with patch("toolguard.update_check.run_git", wraps=_git.run_git) as spy:
            spy.return_value = None  # short-circuit: no real git needed
            update_check.local_repo_head(Path("/nonexistent-repo"))
        spy.assert_called_once()
        (args,), _kwargs = spy.call_args
        self.assertEqual(args, ["-C", "/nonexistent-repo", "rev-parse", "HEAD"])

    def test_install_provenance_git_subtree_is_clean_uses_run_git(self):
        """
        Given _git_subtree_is_clean() is called
        When toolguard._git.run_git is patched to a spy
        Then it is invoked with a "-C <repo> status --porcelain -- <subtree>"
            argv, proving install_provenance.py no longer runs its own
            subprocess.run for this -- the fifth near-identical block the
            review identified
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
        Then it returns None rather than propagating the exception -- the
            single place this used to be caught five times independently
        """
        with patch.object(_git.subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(_git.run_git(["status"]))


if __name__ == "__main__":
    unittest.main()
