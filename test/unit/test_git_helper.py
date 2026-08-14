"""
Unit tests for toolguard._git -- the shared git-subprocess helper.

Its two callers, :mod:`toolguard.install_update` and
:mod:`toolguard.install_provenance`, are checked here rather than in their own
test files: the subject is the cross-module delegation, which neither owns.

No test here launches a process: every one patches the ``subprocess.run``
that :mod:`toolguard._git` calls, or stubs ``run_git`` in a caller's own
binding.
"""

import ast
import inspect
import os
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import _git, constants, install_provenance, install_update


def _completed(returncode=0, stdout="", stderr=""):
    """Return a stand-in for subprocess.CompletedProcess."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _constants_imports(module):
    """
    Map local name -> ``toolguard.constants`` name for *module*'s
    ``from toolguard.constants import ...`` statements.

    Read from the source rather than from the runtime binding because the
    binding cannot tell an import from a re-declared literal of the same
    value: CPython caches both ``"toolguard"`` and ``10``, so ``assertIs``
    passes either way.
    """
    tree = ast.parse(inspect.getsource(module))
    return {
        alias.asname or alias.name: alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "toolguard.constants"
        for alias in node.names
    }


class TestSharedConstants(unittest.TestCase):
    """The distribution name and git timeout come from toolguard.constants."""

    def test_update_check_dist_name_is_the_shared_constant(self):
        """
        Given install_update.py's distribution_name() fallback
        When its value and its binding are compared to toolguard.constants.DIST_NAME
        Then it holds that value and is imported from there, not re-declared
        """
        self.assertIs(install_update._DEFAULT_DIST_NAME, constants.DIST_NAME)
        self.assertEqual(
            _constants_imports(install_update).get("_DEFAULT_DIST_NAME"), "DIST_NAME"
        )

    def test_install_provenance_dist_name_is_the_shared_constant(self):
        """
        Given install_provenance.py's default project/distribution name
        When its value and its binding are compared to toolguard.constants.DIST_NAME
        Then it holds that value and is imported from there, not re-declared
        """
        self.assertIs(install_provenance._DEFAULT_NAME, constants.DIST_NAME)
        self.assertEqual(
            _constants_imports(install_provenance).get("_DEFAULT_NAME"), "DIST_NAME"
        )

    def test_run_git_default_timeout_is_the_shared_constant(self):
        """
        Given toolguard._git.run_git's default timeout parameter (keyword-only)
        When its value and _git.py's binding are compared to GIT_TIMEOUT_SECONDS
        Then it holds that value and is imported from constants, not re-declared
        """
        self.assertIs(
            _git.run_git.__kwdefaults__["timeout"], constants.GIT_TIMEOUT_SECONDS
        )
        self.assertEqual(
            _constants_imports(_git).get("GIT_TIMEOUT_SECONDS"), "GIT_TIMEOUT_SECONDS"
        )


class TestRunGitSubprocessCall(unittest.TestCase):
    """
    What run_git actually hands to subprocess.run.

    Asserting run_git's signature would not do: a default that exists and a
    default that reaches the subprocess are different claims, and deleting
    ``timeout=timeout`` from the call used to pass this whole module.
    """

    def _spy(self, result=None):
        """Patch the subprocess.run that _git calls, returning it as a spy."""
        if result is None:
            result = _completed(0, "out\n")
        return patch.object(_git.subprocess, "run", return_value=result)

    def test_the_git_executable_is_prepended_to_the_arguments(self):
        """
        Given run_git is called with a bare git subcommand and its arguments
        When the subprocess is launched
        Then argv is that list with "git" in front
        """
        with self._spy() as run:
            _git.run_git(["status", "--porcelain"])
        self.assertEqual(run.call_args.args[0], ["git", "status", "--porcelain"])

    def test_the_default_timeout_reaches_the_subprocess(self):
        """
        Given run_git is called without a timeout argument
        When the subprocess is launched
        Then it carries GIT_TIMEOUT_SECONDS, so the call is bounded
        """
        with self._spy() as run:
            _git.run_git(["status"])
        self.assertEqual(run.call_args.kwargs["timeout"], constants.GIT_TIMEOUT_SECONDS)

    def test_an_explicit_timeout_overrides_the_default(self):
        """
        Given a caller passes its own timeout
        When the subprocess is launched
        Then that value is used rather than the shared default
        """
        override = constants.GIT_TIMEOUT_SECONDS + 7.5
        with self._spy() as run:
            _git.run_git(["status"], timeout=override)
        self.assertEqual(run.call_args.kwargs["timeout"], override)

    def test_output_is_captured_as_text(self):
        """
        Given callers read result.stdout as a string
        When the subprocess is launched
        Then output is captured rather than inherited, and decoded as text
        """
        with self._spy() as run:
            _git.run_git(["status"])
        self.assertIs(run.call_args.kwargs["capture_output"], True)
        self.assertIs(run.call_args.kwargs["text"], True)

    def test_no_env_argument_means_the_subprocess_inherits_this_environment(self):
        """
        Given run_git is called without an env argument
        When the subprocess is launched
        Then env is None, which is subprocess's "inherit unchanged"
        """
        with self._spy() as run:
            _git.run_git(["status"])
        self.assertIsNone(run.call_args.kwargs["env"])

    def test_a_supplied_env_reaches_the_subprocess_verbatim(self):
        """
        Given a caller supplies an env holding only GIT_TERMINAL_PROMPT=0
        When the subprocess is launched under a process environment holding
            something else
        Then the subprocess gets exactly the supplied mapping, unmerged
        """
        supplied = {"GIT_TERMINAL_PROMPT": "0"}
        with (
            patch.dict(os.environ, {"TG_PROCESS_ONLY": "1"}, clear=True),
            self._spy() as run,
        ):
            _git.run_git(["ls-remote", "origin", "HEAD"], env=supplied)
        self.assertEqual(run.call_args.kwargs["env"], supplied)

    def test_a_nonzero_exit_is_returned_rather_than_reported_as_a_failure(self):
        """
        Given git runs to completion but exits non-zero
        When run_git returns
        Then the CompletedProcess comes back, because interpreting returncode
            is the caller's job
        """
        failed = _completed(128, "", "fatal: not a git repository\n")
        with self._spy(failed):
            self.assertIs(_git.run_git(["status"]), failed)


class TestRunGitFailureModes(unittest.TestCase):
    """Which exceptions run_git converts to None, and which it lets through."""

    def test_run_git_returns_none_on_launch_failure_without_raising(self):
        """
        Given the underlying subprocess.run raises OSError (git missing)
        When run_git executes
        Then it returns None rather than propagating the exception
        """
        with patch.object(_git.subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(_git.run_git(["status"]))

    def test_run_git_returns_none_when_the_timeout_fires(self):
        """
        Given git exceeds the timeout and subprocess raises TimeoutExpired
        When run_git executes
        Then it returns None, so a hung git degrades to "unknown" not a crash
        """
        with patch.object(
            _git.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            self.assertIsNone(_git.run_git(["status"]))

    def test_an_unexpected_error_is_not_swallowed(self):
        """
        Given subprocess.run raises something that is neither an OSError nor a
            SubprocessError
        When run_git executes
        Then it propagates, because "git could not run" must stay narrow
        """
        with patch.object(_git.subprocess, "run", side_effect=ValueError("boom")):
            with self.assertRaises(ValueError):
                _git.run_git(["status"])


class TestRunGitSharedHelper(unittest.TestCase):
    """Both modules' git-touching functions delegate through run_git."""

    def test_update_check_local_repo_head_uses_run_git(self):
        """
        Given install_update.local_repo_head() is called
        When install_update's own run_git binding is replaced by a spy
        Then it is invoked with a "-C <repo> rev-parse HEAD" argv
        """
        # install_update imports run_git by value, so its binding is the holder;
        # returning None short-circuits the caller without running git.
        with patch.object(install_update, "run_git", return_value=None) as spy:
            install_update.local_repo_head(Path("/nonexistent-repo"))
        spy.assert_called_once()
        (args,), _kwargs = spy.call_args
        self.assertEqual(args, ["-C", "/nonexistent-repo", "rev-parse", "HEAD"])

    def test_install_provenance_git_subtree_is_clean_uses_run_git(self):
        """
        Given _git_subtree_is_clean() is called
        When install_provenance's own run_git binding is replaced by a spy
        Then it is invoked with a "-C <repo> status --porcelain -- <subtree>"
            argv
        """
        with patch.object(install_provenance, "run_git", return_value=None) as spy:
            install_provenance._git_subtree_is_clean(
                Path("/nonexistent-repo"), "toolguard"
            )
        spy.assert_called_once()
        (args,), _kwargs = spy.call_args
        self.assertEqual(
            args,
            ["-C", "/nonexistent-repo", "status", "--porcelain", "--", "toolguard"],
        )

    def test_install_provenance_status_call_is_bounded_by_the_shared_timeout(self):
        """
        Given _git_subtree_is_clean() runs with only subprocess.run stubbed
        When its git subprocess is launched
        Then it carries the shared timeout, which it gets only via run_git
        """
        with patch.object(
            _git.subprocess, "run", return_value=_completed(0, "")
        ) as run:
            install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
        self.assertEqual(
            run.call_args.args[0],
            ["git", "-C", "/repo", "status", "--porcelain", "--", "toolguard"],
        )
        self.assertEqual(run.call_args.kwargs["timeout"], constants.GIT_TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
