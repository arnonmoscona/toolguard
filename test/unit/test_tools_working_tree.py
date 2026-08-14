"""Unit tests for the working-tree cleanliness guard (toolguard.tools.working_tree)."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from toolguard.tools import working_tree as working_tree_module
from toolguard.tools.working_tree import WorkingTreeStatus, working_tree_status


def _completed(returncode: int, stdout: str = "") -> SimpleNamespace:
    """Build a stand-in for subprocess.run's CompletedProcess."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


class _UnexpectedGitFailure(Exception):
    """A fault that is neither OSError nor SubprocessError, so it must propagate."""


class RealGitFixture(unittest.TestCase):
    """
    Base fixture giving each test a throwaway HOME containing throwaway repos.

    The guard shells out to the real git, so the tests do too -- a mocked
    ``subprocess.run`` cannot observe which directory git was pointed at, nor
    what porcelain really emits. Git is detached from the developer's own
    configuration (``GIT_CONFIG_GLOBAL``/``SYSTEM`` at ``/dev/null``, a ceiling
    directory, identity from the environment) so no machine state can change an
    answer, and the fixtures live under the throwaway HOME rather than in a bare
    temp dir so nothing above them is discoverable.

    The helpers here only ever run ``git init``/``add``/``mv``/``commit``. None
    of them runs or parses ``git status --porcelain``: the fixture must not
    re-implement the code under test.
    """

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.home = self.base / "home"
        self.home.mkdir()

        env_patch = mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.home),
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                # Stops git's upward .git search at the fixture root, so a
                # repository anywhere above TMPDIR cannot answer for us.
                "GIT_CEILING_DIRECTORIES": str(self.base),
                "GIT_AUTHOR_NAME": "toolguard-test",
                "GIT_AUTHOR_EMAIL": "toolguard-test@example.invalid",
                "GIT_COMMITTER_NAME": "toolguard-test",
                "GIT_COMMITTER_EMAIL": "toolguard-test@example.invalid",
            },
        )
        env_patch.start()
        self.addCleanup(env_patch.stop)
        for inherited in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            os.environ.pop(inherited, None)

    def git(self, cwd: Path, *args: str) -> subprocess.CompletedProcess:
        """Run a git fixture command, loudly."""
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            check=True,
        )

    def make_repo(self, name: str) -> Path:
        """Create an initialised repository with one committed file."""
        repo = self.home / name
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q", "-b", "main")
        (repo / "tracked.txt").write_text("v1\n")
        (repo / "sub").mkdir()
        (repo / "sub" / "nested.txt").write_text("n1\n")
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-qm", "base")
        return repo

    def chdir(self, target: Path) -> None:
        """Change directory for the duration of the test, restoring afterwards."""
        original = Path.cwd()
        # Cleanups run last-registered-first, so the check goes on before the
        # restore in order to run after it -- and both go on before the chdir,
        # so a failure inside the test still restores.
        self.addCleanup(
            lambda: self.assertEqual(Path.cwd(), original, "cwd was not restored")
        )
        self.addCleanup(os.chdir, original)
        os.chdir(target)


class TestRealGitIsAvailable(unittest.TestCase):
    """The suite's dependency on a real git, asserted rather than skipped."""

    def test_git_is_installed(self):
        """
        Given the working-tree guard is a wrapper around the git binary
        When the test suite runs
        Then git must be present, so the real-git tests cannot be silently
            skipped into a green run.
        """
        self.assertIsNotNone(shutil.which("git"), "git is required by these tests")


class TestAgainstRealGit(RealGitFixture):
    """Classification of real git working-tree state for the apply gate."""

    def test_a_clean_repository_is_a_repo_and_clean_and_safe(self):
        """
        Given a real repository with nothing uncommitted
        When working_tree_status is called on it
        Then it is a git repo, clean, safe to apply to, and lists no paths.
        """
        repo = self.make_repo("clean")
        status = working_tree_status(repo)
        self.assertIs(status.is_git_repo, True)
        self.assertIs(status.is_clean, True)
        self.assertIs(status.is_safe_to_apply, True)
        # dirty_paths is () for a non-repo too, so it is asserted only alongside
        # is_git_repo, which is what distinguishes the two.
        self.assertEqual(status.dirty_paths, ())

    def test_a_dirty_repository_lists_exactly_the_changed_paths_in_git_order(self):
        """
        Given a repository with a staged addition, a rename, a modification and
            an untracked file
        When working_tree_status is called on it
        Then it is an unclean repo that is not safe to apply to, and dirty_paths
            is exactly git's own list, in git's order, with the status prefix
            stripped.
        """
        repo = self.make_repo("dirty")
        (repo / "staged.txt").write_text("s\n")
        self.git(repo, "add", "staged.txt")
        self.git(repo, "mv", "sub/nested.txt", "sub/renamed.txt")
        (repo / "tracked.txt").write_text("v2\n")
        (repo / "untracked.txt").write_text("u\n")

        status = working_tree_status(repo)

        self.assertIs(status.is_git_repo, True)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)
        # Exact tuple equality, not membership: "tracked.txt" is a substring of
        # "untracked.txt", so assertIn could not tell the two apart, and only an
        # ordered comparison can see a truncation or a reordering.
        self.assertEqual(
            status.dirty_paths,
            (
                "staged.txt",
                "sub/nested.txt -> sub/renamed.txt",
                "tracked.txt",
                "untracked.txt",
            ),
        )

    def test_an_untracked_file_alone_makes_the_tree_unclean(self):
        """
        Given an otherwise clean repository with one untracked file
        When working_tree_status is called on it
        Then the tree is unclean and unsafe, and the untracked path is listed.
        """
        repo = self.make_repo("untracked-only")
        (repo / "scratch.txt").write_text("x\n")
        status = working_tree_status(repo)
        self.assertIs(status.is_git_repo, True)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)
        self.assertEqual(status.dirty_paths, ("scratch.txt",))

    def test_staged_modified_and_untracked_arrive_indistinguishable(self):
        """
        Given three files in three different git states
        When working_tree_status is called on the repository
        Then git distinguishes them by a two-character prefix but the result
            carries only the bare paths, so the caller cannot tell which is
            which.
        """
        repo = self.make_repo("kinds")
        (repo / "a-staged.txt").write_text("s\n")
        self.git(repo, "add", "a-staged.txt")
        (repo / "tracked.txt").write_text("v2\n")
        (repo / "z-untracked.txt").write_text("u\n")

        # The information exists at the source: three distinct porcelain codes.
        raw = self.git(repo, "status", "--porcelain").stdout.splitlines()
        self.assertEqual(len(raw), 3)
        self.assertEqual(len({line[:2] for line in raw}), 3)

        status = working_tree_status(repo)
        self.assertEqual(
            status.dirty_paths,
            ("a-staged.txt", "tracked.txt", "z-untracked.txt"),
        )

    def test_an_untracked_directory_collapses_to_one_entry(self):
        """
        Given an untracked directory holding several files
        When working_tree_status is called
        Then dirty_paths carries a single trailing-slash entry standing for
            everything beneath it, as WorkingTreeStatus documents.
        """
        repo = self.make_repo("untracked-dir")
        (repo / "newdir").mkdir()
        (repo / "newdir" / "a.txt").write_text("a\n")
        (repo / "newdir" / "b.txt").write_text("b\n")
        status = working_tree_status(repo)
        self.assertEqual(status.dirty_paths, ("newdir/",))

    def test_a_non_ascii_path_arrives_c_quoted_rather_than_usable(self):
        """
        Given an untracked file whose name is not ASCII
        When working_tree_status is called
        Then the entry is git's own C-quoted string, not a path a caller could
            open -- these are display strings.
        """
        repo = self.make_repo("quoting")
        (repo / "café.txt").write_text("e\n")
        status = working_tree_status(repo)
        self.assertEqual(status.dirty_paths, ('"caf\\303\\251.txt"',))

    def test_a_directory_that_is_not_a_repository_is_not_safe(self):
        """
        Given a directory with no repository at or above it
        When working_tree_status is called
        Then it reports not-a-repo, not clean, and not safe to apply.
        """
        plain = self.home / "plain"
        plain.mkdir()
        status = working_tree_status(plain)
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)
        self.assertEqual(status.dirty_paths, ())

    def test_a_nonexistent_directory_is_reported_as_a_non_repo(self):
        """
        Given a path that does not exist
        When working_tree_status is called
        Then it reports not-a-repo rather than raising.
        """
        status = working_tree_status(self.home / "no-such-dir")
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_safe_to_apply, False)

    def test_a_bare_repository_has_no_work_tree_and_is_not_safe(self):
        """
        Given a bare repository, which has no work tree to inspect
        When working_tree_status is called on it
        Then it reports not-a-repo, so the gate refuses rather than treating an
            un-revertible location as trivially clean.
        """
        bare = self.home / "bare.git"
        bare.mkdir()
        self.git(bare, "init", "-q", "--bare")
        status = working_tree_status(bare)
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_safe_to_apply, False)

    def test_status_is_reported_for_the_directory_given_not_the_process_cwd(self):
        """
        Given a clean repository and a dirty one
        When working_tree_status is called from inside each about the other
        Then each answer describes the directory it was given, never the
            process's current directory.
        """
        clean = self.make_repo("cwd-clean")
        dirty = self.make_repo("cwd-dirty")
        (dirty / "tracked.txt").write_text("v2\n")

        self.chdir(clean)
        from_clean = working_tree_status(dirty)
        self.chdir(dirty)
        from_dirty = working_tree_status(clean)

        # Both directions, so neither can be satisfied by the cwd's own state.
        self.assertIs(from_clean.is_clean, False)
        self.assertEqual(from_clean.dirty_paths, ("tracked.txt",))
        self.assertIs(from_dirty.is_clean, True)
        self.assertEqual(from_dirty.dirty_paths, ())

    def test_the_directory_given_is_used_rather_than_its_parent(self):
        """
        Given a repository whose parent directory is not a repository
        When working_tree_status is called on each
        Then the repository reports a repo and the parent does not, so the
            directory inspected is the one passed in and not an ancestor of it.
        """
        repo = self.make_repo("child")
        self.assertFalse((repo.parent / ".git").exists())
        self.assertIs(working_tree_status(repo).is_git_repo, True)
        self.assertIs(working_tree_status(repo.parent).is_git_repo, False)

    def test_a_subdirectory_reports_the_whole_repository_root_relative(self):
        """
        Given changes both inside and outside a repository's subdirectory
        When working_tree_status is called on that subdirectory
        Then it reports the whole repository, and every path is relative to the
            repository root rather than to the directory it was given.
        """
        repo = self.make_repo("subdir")
        (repo / "tracked.txt").write_text("v2\n")
        (repo / "sub" / "nested.txt").write_text("n2\n")
        status = working_tree_status(repo / "sub")
        self.assertIs(status.is_git_repo, True)
        self.assertIs(status.is_clean, False)
        # "tracked.txt" lies outside the directory asked about, and the nested
        # entry still carries its "sub/" prefix: both are root-relative.
        self.assertEqual(status.dirty_paths, ("sub/nested.txt", "tracked.txt"))


class TestGitFailureModes(unittest.TestCase):
    """
    How the guard fails when git cannot answer.

    Every case must fail CLOSED -- a fault must never come back as a clean
    repository, because the gate reads is_safe_to_apply as permission to write.
    """

    def _run_with(self, **patch_kwargs):
        """Call the guard with subprocess.run replaced, proving the patch was used."""
        with mock.patch(
            "toolguard.tools.working_tree.subprocess.run", **patch_kwargs
        ) as runner:
            status = working_tree_status(Path("/repo"))
        runner.assert_called_once()
        return status

    def test_a_missing_git_binary_fails_closed(self):
        """
        Given the git binary is absent, so launching it raises FileNotFoundError
        When working_tree_status is called
        Then it returns a non-repo, unclean, unsafe status rather than raising
            or reporting clean.
        """
        status = self._run_with(side_effect=FileNotFoundError("no git here"))
        self.assertIsInstance(status, WorkingTreeStatus)
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)

    def test_an_unlaunchable_git_fails_closed(self):
        """
        Given git cannot be executed, so launching it raises PermissionError
        When working_tree_status is called
        Then it fails closed to a non-repo, unclean, unsafe status.
        """
        status = self._run_with(side_effect=PermissionError("not executable"))
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)

    def test_a_timed_out_git_fails_closed(self):
        """
        Given the git subprocess exceeds its timeout
        When working_tree_status is called
        Then the timeout is caught and reported as a non-repo, unclean, unsafe
            status -- never as clean.
        """
        status = self._run_with(
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=10)
        )
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)

    def test_a_non_zero_exit_fails_closed_even_with_output_on_stdout(self):
        """
        Given git exits non-zero but has still written porcelain-shaped output
        When working_tree_status is called
        Then the exit status decides: a non-repo, unclean, unsafe status with no
            paths, rather than the output being parsed.
        """
        status = self._run_with(
            return_value=_completed(128, " M toolguard/config.py\n")
        )
        self.assertIs(status.is_git_repo, False)
        self.assertIs(status.is_clean, False)
        self.assertIs(status.is_safe_to_apply, False)
        self.assertEqual(status.dirty_paths, ())

    def test_an_unexpected_exception_propagates_instead_of_reading_as_no_repo(self):
        """
        Given the subprocess call raises something that is neither an OSError
            nor a SubprocessError
        When working_tree_status is called
        Then the exception propagates, so a bug is not disguised as "git is
            unavailable".
        """
        with self.assertRaises(_UnexpectedGitFailure):
            self._run_with(side_effect=_UnexpectedGitFailure("a bug, not a git fault"))

    def test_the_subprocess_is_bounded_by_the_modules_timeout_constant(self):
        """
        Given the module's timeout constant is replaced with a distinctive value
        When working_tree_status is called
        Then subprocess.run receives that value, so the call is bounded and the
            bound is the constant rather than a literal at the call site.
        """
        sentinel_timeout = 4242
        with mock.patch.object(
            working_tree_module, "_GIT_TIMEOUT_SECONDS", sentinel_timeout
        ):
            with mock.patch(
                "toolguard.tools.working_tree.subprocess.run",
                return_value=_completed(0, ""),
            ) as runner:
                working_tree_status(Path("/repo"))
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs.get("timeout"), sentinel_timeout)


class TestIsSafeToApply(unittest.TestCase):
    """The gate's verdict, over every combination the dataclass can hold."""

    def test_only_a_clean_git_repo_is_safe_to_apply(self):
        """
        Given each combination of is_git_repo and is_clean
        When is_safe_to_apply is read
        Then only a clean git repo is safe -- in particular a non-repo reporting
            clean is not, because there is no revert safety net.
        """
        cases = {
            (True, True): True,
            (True, False): False,
            (False, True): False,
            (False, False): False,
        }
        for (is_repo, is_clean), expected in cases.items():
            with self.subTest(is_git_repo=is_repo, is_clean=is_clean):
                status = WorkingTreeStatus(
                    is_git_repo=is_repo, is_clean=is_clean, dirty_paths=()
                )
                self.assertIs(status.is_safe_to_apply, expected)


if __name__ == "__main__":
    unittest.main()
