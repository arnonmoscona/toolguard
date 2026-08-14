"""
Unit tests for toolguard.install_update and the toolguard.update_check CLI wrapper.

All side effects (metadata, git, uv) are stubbed -- no real network, subprocess,
or install runs. The git calls reach ``subprocess.run`` from inside
:mod:`toolguard._git`, not from ``install_update``, so patching the one global
``subprocess`` module is what isolates them.
"""

import io
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import install_update, update_check
from toolguard.constants import DIST_NAME, GIT_TIMEOUT_SECONDS
from toolguard.install_update import InstallInfo, InstallKind


def _completed(returncode=0, stdout="", stderr=""):
    """Return a stand-in for subprocess.CompletedProcess."""
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


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
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            self.assertEqual(
                install_update.installed_origin(),
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
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            self.assertIsNone(install_update.installed_origin())

    def test_missing_direct_url_returns_none(self):
        """
        Given a distribution whose read_text returns None (no direct_url.json)
        When installed_origin runs
        Then it returns None
        """
        with patch.object(
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(None),
        ):
            self.assertIsNone(install_update.installed_origin())

    def test_metadata_lookup_failure_returns_none(self):
        """
        Given importlib.metadata raises (package not found)
        When installed_origin runs
        Then it returns None rather than propagating the error
        """
        with patch.object(
            install_update.importlib.metadata,
            "distribution",
            side_effect=install_update.importlib.metadata.PackageNotFoundError(
                "toolguard"
            ),
        ):
            self.assertIsNone(install_update.installed_origin())


class TestInstalledOriginPartialMetadata(unittest.TestCase):
    """installed_origin rejects vcs metadata that is present but incomplete."""

    def _dist_returning(self, text):
        """Return a fake distribution whose read_text yields ``text``."""
        return SimpleNamespace(read_text=lambda name: text)

    def _origin_for(self, payload):
        """Run installed_origin against a direct_url.json body."""
        with patch.object(
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            return install_update.installed_origin()

    def test_vcs_info_without_commit_id_returns_none(self):
        """
        Given a vcs_info block that names a vcs but carries no commit_id
        When installed_origin runs
        Then it returns None rather than a tuple with a missing commit
        """
        payload = '{"url":"https://github.com/x/toolguard","vcs_info":{"vcs":"git"}}'
        self.assertIsNone(self._origin_for(payload))

    def test_vcs_info_that_is_not_a_mapping_returns_none(self):
        """
        Given a vcs_info field holding a string rather than an object
        When installed_origin runs
        Then it returns None rather than raising on the .get lookup
        """
        payload = '{"url":"https://github.com/x/toolguard","vcs_info":"git"}'
        self.assertIsNone(self._origin_for(payload))

    def test_vcs_info_without_url_returns_none(self):
        """
        Given a commit_id but no url to fetch it from
        When installed_origin runs
        Then it returns None
        """
        payload = '{"vcs_info":{"vcs":"git","commit_id":"abc123"}}'
        self.assertIsNone(self._origin_for(payload))


class TestReadDirectUrlJson(unittest.TestCase):
    """Parsing the direct_url.json payload itself."""

    def _dist_returning(self, text):
        """Return a fake distribution whose read_text yields ``text``."""
        return SimpleNamespace(read_text=lambda name: text)

    def _parse(self, payload):
        """Run _read_direct_url_json against a raw direct_url.json body."""
        with patch.object(
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            return install_update._read_direct_url_json()

    def test_valid_object_is_parsed(self):
        """
        Given a well-formed JSON object
        When _read_direct_url_json runs
        Then it returns the parsed mapping
        """
        self.assertEqual(self._parse('{"url":"file:///x"}'), {"url": "file:///x"})

    def test_malformed_json_returns_none(self):
        """
        Given a direct_url.json that is not valid JSON
        When _read_direct_url_json runs
        Then it returns None rather than raising
        """
        self.assertIsNone(self._parse("{not json"))


class TestDistributionName(unittest.TestCase):
    """The name used in the printed 'uv tool upgrade <name>' instruction."""

    def test_returns_the_name_from_package_metadata(self):
        """
        Given installed metadata whose Name differs from the built-in default
        When distribution_name runs
        Then it returns the metadata Name
        """
        dist = SimpleNamespace(metadata={"Name": "claude-toolguard"})
        with patch.object(
            install_update.importlib.metadata, "distribution", return_value=dist
        ):
            self.assertEqual(install_update.distribution_name(), "claude-toolguard")

    def test_unreadable_metadata_falls_back_to_the_shared_constant(self):
        """
        Given importlib.metadata raises (toolguard not installed as a distribution)
        When distribution_name runs
        Then it returns toolguard.constants.DIST_NAME
        """
        with patch.object(
            install_update.importlib.metadata,
            "distribution",
            side_effect=install_update.importlib.metadata.PackageNotFoundError("x"),
        ):
            self.assertEqual(install_update.distribution_name(), DIST_NAME)


class TestFileUrlToPath(unittest.TestCase):
    """Converting a PEP 610 ``file://`` url into a path."""

    def test_file_url_returns_its_path(self):
        """
        Given a file:// url
        When _file_url_to_path runs
        Then it returns the path component
        """
        self.assertEqual(
            install_update._file_url_to_path("file:///home/user/toolguard"),
            Path("/home/user/toolguard"),
        )

    def test_non_file_scheme_returns_none(self):
        """
        Given an https:// url
        When _file_url_to_path runs
        Then it returns None rather than a bogus path
        """
        self.assertIsNone(
            install_update._file_url_to_path("https://github.com/x/toolguard")
        )


class TestWalkUpToGitRoot(unittest.TestCase):
    """Finding the nearest ancestor directory holding a ``.git`` entry."""

    def test_nearest_dot_git_wins_over_an_outer_one(self):
        """
        Given nested directories where both an outer and an inner ancestor hold .git
        When _walk_up_to_git_root runs from below the inner one
        Then it returns the inner (nearest) directory
        """
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp)
            (outer / ".git").mkdir()
            inner = outer / "a" / "b"
            inner.mkdir(parents=True)
            (inner / ".git").mkdir()
            deep = inner / "c" / "d"
            deep.mkdir(parents=True)
            self.assertEqual(install_update._walk_up_to_git_root(deep), inner)

    def test_a_file_argument_is_searched_from_its_directory(self):
        """
        Given a path to a file rather than a directory
        When _walk_up_to_git_root runs
        Then the search starts at the file's parent and finds that directory
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            module_file = root / "toolguard" / "install_update.py"
            module_file.parent.mkdir()
            module_file.write_text("")
            self.assertEqual(install_update._walk_up_to_git_root(module_file), root)


class TestIsGitWorktree(unittest.TestCase):
    """Confirming a path is inside a git work tree."""

    def _probe(self, result):
        """Run is_git_worktree with run_git stubbed to ``result``.

        install_update imports run_git by value, so its own binding is the
        holder to patch.
        """
        with patch.object(install_update, "run_git", return_value=result) as spy:
            answer = install_update.is_git_worktree(Path("/repo"))
        return answer, spy

    def test_true_output_means_inside_a_worktree(self):
        """
        Given git rev-parse --is-inside-work-tree prints "true"
        When is_git_worktree runs
        Then it returns True
        """
        answer, spy = self._probe(_completed(0, "true\n"))
        self.assertTrue(answer)
        self.assertEqual(
            spy.call_args.args[0],
            ["-C", "/repo", "rev-parse", "--is-inside-work-tree"],
        )

    def test_false_output_means_not_inside_a_worktree(self):
        """
        Given git exits 0 but prints "false" (e.g. a bare repository)
        When is_git_worktree runs
        Then it returns False
        """
        answer, _ = self._probe(_completed(0, "false\n"))
        self.assertFalse(answer)

    def test_nonzero_exit_means_not_a_worktree(self):
        """
        Given git exits non-zero while still printing "true" on stdout
        When is_git_worktree runs
        Then it returns False, because the exit status is checked too
        """
        answer, _ = self._probe(_completed(128, "true\n"))
        self.assertFalse(answer)

    def test_git_unavailable_means_not_a_worktree(self):
        """
        Given run_git returns None (git missing, or it timed out)
        When is_git_worktree runs
        Then it returns False without raising
        """
        answer, _ = self._probe(None)
        self.assertFalse(answer)


class TestGitSubprocessSafety(unittest.TestCase):
    """
    The bounds install_update's module docstring claims for its git subprocesses:
    every call timed, and the two ls-remote calls non-interactive.
    """

    def _spy_git(self, returncode=0, stdout="deadbeef\tHEAD\n"):
        """Patch the global subprocess.run that toolguard._git ultimately calls."""
        return patch.object(
            subprocess, "run", return_value=_completed(returncode, stdout)
        )

    def test_remote_ls_remote_is_bounded_by_a_timeout(self):
        """
        Given remote_head reaches the network
        When its git subprocess is launched
        Then it carries the shared GIT_TIMEOUT_SECONDS timeout
        """
        with self._spy_git() as run:
            install_update.remote_head("https://example/x")
        self.assertEqual(run.call_args.kwargs["timeout"], GIT_TIMEOUT_SECONDS)

    def test_local_ls_remote_is_bounded_by_a_timeout(self):
        """
        Given local_remote_head reaches the network
        When its git subprocess is launched
        Then it carries the shared GIT_TIMEOUT_SECONDS timeout
        """
        with self._spy_git() as run:
            install_update.local_remote_head(Path("/repo"))
        self.assertEqual(run.call_args.kwargs["timeout"], GIT_TIMEOUT_SECONDS)

    def test_rev_parse_is_bounded_by_a_timeout(self):
        """
        Given local_repo_head reads HEAD from a checkout
        When its git subprocess is launched
        Then it too carries the shared timeout
        """
        with self._spy_git(stdout="localsha\n") as run:
            install_update.local_repo_head(Path("/repo"))
        self.assertEqual(run.call_args.kwargs["timeout"], GIT_TIMEOUT_SECONDS)

    def test_worktree_probe_is_bounded_by_a_timeout(self):
        """
        Given is_git_worktree probes a path
        When its git subprocess is launched
        Then it too carries the shared timeout
        """
        with self._spy_git(stdout="true\n") as run:
            install_update.is_git_worktree(Path("/repo"))
        self.assertEqual(run.call_args.kwargs["timeout"], GIT_TIMEOUT_SECONDS)

    def test_remote_ls_remote_disables_the_terminal_credential_prompt(self):
        """
        Given remote_head may hit a repository requiring credentials
        When its git subprocess is launched
        Then GIT_TERMINAL_PROMPT=0 is in its environment, so git cannot block on a prompt
        """
        with patch.dict(os.environ, {}, clear=True), self._spy_git() as run:
            install_update.remote_head("https://example/x")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_local_ls_remote_disables_the_terminal_credential_prompt(self):
        """
        Given local_remote_head may hit an origin requiring credentials
        When its git subprocess is launched
        Then GIT_TERMINAL_PROMPT=0 is in its environment
        """
        with patch.dict(os.environ, {}, clear=True), self._spy_git() as run:
            install_update.local_remote_head(Path("/repo"))
        self.assertEqual(run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_ls_remote_env_is_the_process_environment_plus_that_override(self):
        """
        Given a controlled process environment holding one variable
        When remote_head launches git
        Then the subprocess environment is that variable plus GIT_TERMINAL_PROMPT=0
        """
        with (
            patch.dict(os.environ, {"TG_PROBE": "1"}, clear=True),
            self._spy_git() as run,
        ):
            install_update.remote_head("https://example/x")
        self.assertEqual(
            run.call_args.kwargs["env"],
            {"TG_PROBE": "1", "GIT_TERMINAL_PROMPT": "0"},
        )

    def test_rev_parse_inherits_the_environment_unchanged(self):
        """
        Given local_repo_head never reaches the network
        When it launches git
        Then it passes env=None, inheriting the process environment as-is
        """
        with self._spy_git(stdout="localsha\n") as run:
            install_update.local_repo_head(Path("/repo"))
        self.assertIsNone(run.call_args.kwargs["env"])

    def test_git_output_is_captured_as_text(self):
        """
        Given the callers parse result.stdout as a string
        When git is launched
        Then output is captured in text mode rather than inherited by this process
        """
        with self._spy_git() as run:
            install_update.remote_head("https://example/x")
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertTrue(run.call_args.kwargs["text"])

    def test_a_timed_out_ls_remote_reports_the_remote_as_unreachable(self):
        """
        Given git exceeds the timeout and subprocess raises TimeoutExpired
        When remote_head runs
        Then it returns None rather than propagating, so the check degrades to 'unknown'
        """
        with patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            self.assertIsNone(install_update.remote_head("https://example/x"))

    def test_a_timed_out_local_ls_remote_reports_the_remote_as_unreachable(self):
        """
        Given git exceeds the timeout from inside a checkout
        When local_remote_head runs
        Then it returns None rather than propagating
        """
        with patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            self.assertIsNone(install_update.local_remote_head(Path("/repo")))


class TestDetectInstall(unittest.TestCase):
    """Resolving git / local / unknown from direct_url.json or a __file__ walk-up."""

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
            install_update.importlib.metadata,
            "distribution",
            return_value=self._dist_returning(payload),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.GIT)
        self.assertEqual(info.url, "https://github.com/x/toolguard")
        self.assertEqual(info.installed_commit, "gitcommit1")

    def test_vcs_info_without_commit_id_falls_through_to_the_walk_up(self):
        """
        Given a vcs_info block carrying no commit_id and no dir_info
        When detect_install runs and no git root is found above __file__
        Then it returns kind=UNKNOWN rather than a GIT install with no commit
        """
        payload = '{"url":"https://github.com/x/toolguard","vcs_info":{"vcs":"git"}}'
        with (
            patch.object(
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(install_update, "_walk_up_to_git_root", return_value=None),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)

    def test_dir_info_with_valid_file_url_and_git_worktree_returns_local_kind(self):
        """
        Given a direct_url.json with dir_info pointing to a valid git worktree
        When detect_install runs
        Then it returns InstallInfo with kind=LOCAL and the resolved repo_path
        """
        payload = '{"url":"file:///home/user/toolguard","dir_info":{"editable":false}}'
        with (
            patch.object(
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(install_update, "is_git_worktree", return_value=True),
            patch.object(install_update, "local_repo_head", return_value="localhead1"),
        ):
            info = install_update.detect_install()
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
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(install_update, "is_git_worktree", return_value=True),
            patch.object(install_update, "local_repo_head", return_value="edithead1"),
        ):
            info = install_update.detect_install()
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
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(payload),
            ),
            patch.object(install_update, "is_git_worktree", return_value=False),
        ):
            info = install_update.detect_install()
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
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(None),
            ),
            patch.object(
                install_update, "_walk_up_to_git_root", return_value=fake_repo
            ),
            patch.object(install_update, "is_git_worktree", return_value=True),
            patch.object(install_update, "local_repo_head", return_value="walkuphead1"),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.LOCAL)
        self.assertEqual(info.repo_path, fake_repo)
        self.assertEqual(info.installed_commit, "walkuphead1")

    def test_walk_up_root_that_is_not_a_worktree_returns_unknown(self):
        """
        Given the walk-up finds a directory holding .git but git denies it is a worktree
        When detect_install runs
        Then it returns kind=UNKNOWN rather than a LOCAL install
        """
        with (
            patch.object(
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(None),
            ),
            patch.object(
                install_update,
                "_walk_up_to_git_root",
                return_value=Path("/home/user/toolguard"),
            ),
            patch.object(install_update, "is_git_worktree", return_value=False),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)

    def test_no_direct_url_and_no_git_root_returns_unknown(self):
        """
        Given no direct_url.json and __file__ is not inside any git work tree
        When detect_install runs
        Then it returns InstallInfo with kind=UNKNOWN
        """
        with (
            patch.object(
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning(None),
            ),
            patch.object(install_update, "_walk_up_to_git_root", return_value=None),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)

    def test_direct_url_json_that_is_not_an_object_returns_unknown(self):
        """
        Given a direct_url.json whose top level parses to a list, not an object
        When detect_install runs
        Then it returns kind=UNKNOWN rather than raising AttributeError on .get
        """
        with (
            patch.object(
                install_update.importlib.metadata,
                "distribution",
                return_value=self._dist_returning("[1, 2]"),
            ),
            patch.object(install_update, "_walk_up_to_git_root", return_value=None),
        ):
            info = install_update.detect_install()
        self.assertEqual(info.kind, InstallKind.UNKNOWN)


class TestRemoteHead(unittest.TestCase):
    """Parsing the remote HEAD sha from ``git ls-remote`` output."""

    def test_parses_sha_from_ls_remote_output(self):
        """
        Given git ls-remote succeeds with a HEAD line
        When remote_head runs
        Then it returns the leading tab-separated sha field
        """
        completed = _completed(0, "1a2b3c4d5e6f70819293a4b5c6d7e8f901234567\tHEAD\n")
        with patch.object(subprocess, "run", return_value=completed):
            self.assertEqual(
                install_update.remote_head("https://example/x"),
                "1a2b3c4d5e6f70819293a4b5c6d7e8f901234567",
            )

    def test_nonzero_exit_returns_none(self):
        """
        Given git ls-remote exits non-zero but still prints a sha-shaped line
        When remote_head runs
        Then it returns None, because the exit status alone decides
        """
        completed = _completed(128, "deadbeef0123\tHEAD\n", "fatal")
        with patch.object(subprocess, "run", return_value=completed):
            self.assertIsNone(install_update.remote_head("https://example/x"))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is missing or the call times out
        When remote_head runs
        Then it returns None rather than raising (offline-safe)
        """
        with patch.object(subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(install_update.remote_head("https://example/x"))

    def test_empty_output_returns_none(self):
        """
        Given git ls-remote succeeds but prints nothing
        When remote_head runs
        Then it returns None
        """
        with patch.object(subprocess, "run", return_value=_completed(0, "\n")):
            self.assertIsNone(install_update.remote_head("https://example/x"))


class TestLocalRepoHead(unittest.TestCase):
    """Parsing HEAD sha from a local checkout via ``git rev-parse HEAD``."""

    def test_returns_head_sha_from_local_repo(self):
        """
        Given git rev-parse HEAD succeeds in the local repo
        When local_repo_head is called
        Then it returns the HEAD sha
        """
        with patch.object(
            subprocess, "run", return_value=_completed(0, "localsha123\n")
        ):
            result = install_update.local_repo_head(Path("/repo"))
        self.assertEqual(result, "localsha123")

    def test_nonzero_exit_returns_none(self):
        """
        Given git rev-parse exits non-zero but still prints a sha on stdout
        When local_repo_head is called
        Then it returns None, because the exit status alone decides
        """
        completed = _completed(128, "localsha123\n", "fatal")
        with patch.object(subprocess, "run", return_value=completed):
            self.assertIsNone(install_update.local_repo_head(Path("/repo")))

    def test_empty_output_returns_none(self):
        """
        Given git rev-parse exits 0 but prints only whitespace
        When local_repo_head is called
        Then it returns None rather than an empty sha
        """
        with patch.object(subprocess, "run", return_value=_completed(0, "\n")):
            self.assertIsNone(install_update.local_repo_head(Path("/repo")))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is not available (OSError)
        When local_repo_head is called
        Then it returns None without raising
        """
        with patch.object(subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(install_update.local_repo_head(Path("/repo")))


class TestLocalRemoteHead(unittest.TestCase):
    """Parsing the remote origin HEAD sha via ``git ls-remote origin HEAD``."""

    def test_returns_remote_sha_from_local_repo(self):
        """
        Given git ls-remote origin HEAD succeeds in the local repo
        When local_remote_head is called
        Then it returns the remote HEAD sha
        """
        completed = _completed(0, "remotesha456\tHEAD\n")
        with patch.object(subprocess, "run", return_value=completed):
            result = install_update.local_remote_head(Path("/repo"))
        self.assertEqual(result, "remotesha456")

    def test_nonzero_exit_returns_none(self):
        """
        Given git ls-remote exits non-zero but still prints a sha-shaped line
        When local_remote_head is called
        Then it returns None, because the exit status alone decides
        """
        completed = _completed(128, "remotesha456\tHEAD\n", "fatal")
        with patch.object(subprocess, "run", return_value=completed):
            self.assertIsNone(install_update.local_remote_head(Path("/repo")))

    def test_empty_output_returns_none(self):
        """
        Given git ls-remote exits 0 but prints only whitespace
        When local_remote_head is called
        Then it returns None rather than an empty sha
        """
        with patch.object(subprocess, "run", return_value=_completed(0, "\n")):
            self.assertIsNone(install_update.local_remote_head(Path("/repo")))

    def test_subprocess_exception_returns_none(self):
        """
        Given git is not available (OSError)
        When local_remote_head is called
        Then it returns None without raising (offline-safe)
        """
        with patch.object(subprocess, "run", side_effect=OSError("no git")):
            self.assertIsNone(install_update.local_remote_head(Path("/repo")))


class TestCheck(unittest.TestCase):
    """The core _check logic: exit codes, flags, and printed output."""

    REPO = Path("/home/user/toolguard")
    URL = "https://github.com/x/toolguard"

    def setUp(self):
        """Pin the distribution name so no test reads the real installed metadata."""
        patcher = patch.object(
            install_update, "distribution_name", return_value="toolguard"
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run_check(self, quiet=False, do_upgrade=False):
        """Run _check capturing (exit_code, stdout, stderr)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = install_update._check(quiet=quiet, do_upgrade=do_upgrade)
        return code, out.getvalue(), err.getvalue()

    def _git_info(self, commit="installed123"):
        """Return an InstallInfo for a git kind install."""
        return InstallInfo(
            kind=InstallKind.GIT,
            url=self.URL,
            installed_commit=commit,
        )

    def _local_info(self, commit="localhead1", editable=False):
        """Return an InstallInfo for a local kind install."""
        return InstallInfo(
            kind=InstallKind.LOCAL,
            installed_commit=commit,
            repo_path=self.REPO,
            editable=editable,
        )

    def test_git_up_to_date_returns_zero(self):
        """
        Given a git install where the installed commit equals the remote HEAD
        When _check runs
        Then it queries the remote, returns exit code 0, and reports up to date
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(
                install_update, "remote_head", return_value="same"
            ) as mock_remote,
        ):
            code, out, _ = self._run_check()
        mock_remote.assert_called_once_with(self.URL)
        self.assertEqual(code, install_update.EXIT_UP_TO_DATE)
        self.assertIn("up to date", out)

    def test_git_quiet_suppresses_up_to_date_output(self):
        """
        Given a git install up to date and --quiet
        When _check runs
        Then it still queries the remote, returns 0, and prints nothing to stdout
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(
                install_update, "remote_head", return_value="same"
            ) as mock_remote,
        ):
            code, out, _ = self._run_check(quiet=True)
        mock_remote.assert_called_once_with(self.URL)
        self.assertEqual(code, install_update.EXIT_UP_TO_DATE)
        self.assertEqual(out, "")

    def test_git_update_available_returns_one_and_prints_command(self):
        """
        Given a git install where the installed commit differs from the remote HEAD
        When _check runs
        Then it returns exit code 1 and prints the upgrade command with the dist name
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._git_info("oldcommit"),
            ),
            patch.object(install_update, "remote_head", return_value="newcommit"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, install_update.EXIT_UPDATE_AVAILABLE)
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
                install_update, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(install_update, "remote_head", return_value="new"),
        ):
            code, out, _ = self._run_check(quiet=True)
        self.assertEqual(code, install_update.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)

    def test_git_printed_command_uses_distribution_name(self):
        """
        Given a non-default distribution name (e.g. a future PyPI rename) and a git install
        When _check reports an available update
        Then the printed upgrade command uses that distribution name
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(install_update, "remote_head", return_value="new"),
            patch.object(
                install_update, "distribution_name", return_value="claude-toolguard"
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
                install_update, "detect_install", return_value=self._git_info("commit")
            ),
            patch.object(install_update, "remote_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, install_update.EXIT_UNKNOWN)
        self.assertIn("Could not reach", err)

    def test_git_upgrade_flag_returns_uvs_own_exit_code(self):
        """
        Given a git install behind the remote, do_upgrade is True, and uv exits 7
        When _check runs
        Then run_upgrade is invoked and 7 is returned -- outside the 0/1/2 contract
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._git_info("old")
            ),
            patch.object(install_update, "remote_head", return_value="new"),
            patch.object(install_update, "run_upgrade", return_value=7) as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_called_once_with("toolguard")
        self.assertEqual(code, 7)

    def test_git_upgrade_flag_does_not_run_when_up_to_date(self):
        """
        Given a git install up to date and do_upgrade is True
        When _check runs
        Then run_upgrade is NOT invoked and exit code is 0
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._git_info("same")
            ),
            patch.object(install_update, "remote_head", return_value="same"),
            patch.object(install_update, "run_upgrade") as mock_upgrade,
        ):
            code, _, _ = self._run_check(do_upgrade=True)
        mock_upgrade.assert_not_called()
        self.assertEqual(code, install_update.EXIT_UP_TO_DATE)

    def test_local_up_to_date_returns_zero(self):
        """
        Given a local install where HEAD equals the remote origin HEAD
        When _check runs
        Then it queries origin, returns 0, and names the checkout path
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("same"),
            ),
            patch.object(install_update, "local_repo_head", return_value="same"),
            patch.object(
                install_update, "local_remote_head", return_value="same"
            ) as mock_remote,
        ):
            code, out, _ = self._run_check()
        mock_remote.assert_called_once_with(self.REPO)
        self.assertEqual(code, install_update.EXIT_UP_TO_DATE)
        self.assertIn("up to date", out)
        self.assertIn(str(self.REPO), out)

    def test_local_quiet_suppresses_up_to_date_output(self):
        """
        Given a local install up to date and --quiet
        When _check runs
        Then it still queries origin, returns 0, and prints nothing to stdout
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("same"),
            ),
            patch.object(install_update, "local_repo_head", return_value="same"),
            patch.object(
                install_update, "local_remote_head", return_value="same"
            ) as mock_remote,
        ):
            code, out, _ = self._run_check(quiet=True)
        mock_remote.assert_called_once_with(self.REPO)
        self.assertEqual(code, install_update.EXIT_UP_TO_DATE)
        self.assertEqual(out, "")

    def test_local_behind_returns_one_and_prints_git_pull(self):
        """
        Given a local install where HEAD is behind the remote origin HEAD
        When _check runs
        Then it returns exit code 1 and prints the git pull command for the checkout
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._local_info("old")
            ),
            patch.object(install_update, "local_repo_head", return_value="old"),
            patch.object(install_update, "local_remote_head", return_value="new"),
        ):
            code, out, _ = self._run_check()
        self.assertEqual(code, install_update.EXIT_UPDATE_AVAILABLE)
        self.assertIn("update available", out)
        self.assertIn(f"git -C {self.REPO} pull", out)

    def test_local_non_editable_prints_uv_tool_install_force(self):
        """
        Given a non-editable local install that is behind
        When _check runs
        Then the output includes 'uv tool install --force <checkout>' as a reinstall step
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("old", editable=False),
            ),
            patch.object(install_update, "local_repo_head", return_value="old"),
            patch.object(install_update, "local_remote_head", return_value="new"),
        ):
            _, out, _ = self._run_check()
        self.assertIn(f"uv tool install --force {self.REPO}", out)

    def test_local_non_editable_reinstall_alternative_is_its_own_line(self):
        """
        Given a non-editable local install that is behind
        When _check prints the manual steps
        Then the 'or: uv tool upgrade' alternative is a separate line, not a trailing
            comment that hides it inside the install command
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("old", editable=False),
            ),
            patch.object(install_update, "local_repo_head", return_value="old"),
            patch.object(install_update, "local_remote_head", return_value="new"),
        ):
            _, out, _ = self._run_check()
        install_line = next(
            line for line in out.splitlines() if "uv tool install --force" in line
        )
        self.assertNotIn("uv tool upgrade", install_line)

    def test_local_editable_does_not_print_uv_tool_install(self):
        """
        Given an editable local install that is behind
        When _check runs
        Then the output does NOT include 'uv tool install --force' (git pull suffices)
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("old", editable=True),
            ),
            patch.object(install_update, "local_repo_head", return_value="old"),
            patch.object(install_update, "local_remote_head", return_value="new"),
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
                install_update, "detect_install", return_value=self._local_info("old")
            ),
            patch.object(install_update, "local_repo_head", return_value="old"),
            patch.object(install_update, "local_remote_head", return_value="new"),
            patch.object(install_update, "run_upgrade") as mock_upgrade,
        ):
            code, _, err = self._run_check(do_upgrade=True)
        mock_upgrade.assert_not_called()
        self.assertEqual(code, install_update.EXIT_UPDATE_AVAILABLE)
        self.assertIn("manual", err.lower())

    def test_local_remote_unreachable_returns_unknown(self):
        """
        Given a local install where the remote origin HEAD cannot be fetched (offline)
        When _check runs
        Then it returns exit code 2 saying the remote could not be reached
        """
        with (
            patch.object(
                install_update, "detect_install", return_value=self._local_info("head")
            ),
            patch.object(install_update, "local_repo_head", return_value="head"),
            patch.object(install_update, "local_remote_head", return_value=None),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, install_update.EXIT_UNKNOWN)
        self.assertIn("Could not reach", err)
        self.assertNotIn("Could not read HEAD", err)

    def test_local_head_unreadable_returns_unknown(self):
        """
        Given a local install where git rev-parse HEAD fails, while origin is reachable
            and agrees with the commit detect_install recorded
        When _check runs
        Then it returns exit code 2 saying HEAD could not be read from that checkout,
            and never consults origin
        """
        with (
            patch.object(
                install_update,
                "detect_install",
                return_value=self._local_info("localhead1"),
            ),
            patch.object(install_update, "local_repo_head", return_value=None),
            patch.object(
                install_update, "local_remote_head", return_value="localhead1"
            ) as mock_remote,
        ):
            code, _, err = self._run_check()
        mock_remote.assert_not_called()
        self.assertEqual(code, install_update.EXIT_UNKNOWN)
        self.assertIn("Could not read HEAD", err)
        self.assertIn(str(self.REPO), err)

    def test_unknown_install_returns_exit_two(self):
        """
        Given detect_install returns kind=UNKNOWN (no direct_url, no discoverable repo)
        When _check runs
        Then it returns exit code 2 naming both manual update routes
        """
        with patch.object(
            install_update,
            "detect_install",
            return_value=InstallInfo(kind=InstallKind.UNKNOWN),
        ):
            code, _, err = self._run_check()
        self.assertEqual(code, install_update.EXIT_UNKNOWN)
        self.assertIn("could not determine install type", err)
        self.assertIn("uv tool upgrade toolguard", err)
        self.assertIn("git pull", err)


class TestRunUpgrade(unittest.TestCase):
    """Running 'uv tool upgrade' and surfacing its result."""

    def test_runs_uv_tool_upgrade_for_the_named_distribution(self):
        """
        Given a distribution name
        When run_upgrade runs
        Then it launches exactly 'uv tool upgrade <name>'
        """
        with patch.object(
            subprocess, "run", return_value=SimpleNamespace(returncode=0)
        ) as run:
            install_update.run_upgrade("claude-toolguard")
        self.assertEqual(
            run.call_args.args[0], ["uv", "tool", "upgrade", "claude-toolguard"]
        )

    def test_returns_subprocess_exit_code(self):
        """
        Given uv tool upgrade runs and exits 3
        When run_upgrade runs
        Then it returns 3 rather than a code of its own
        """
        with patch.object(
            subprocess, "run", return_value=SimpleNamespace(returncode=3)
        ):
            self.assertEqual(install_update.run_upgrade("toolguard"), 3)

    def test_uv_missing_returns_unknown(self):
        """
        Given uv is not installed (launch raises OSError)
        When run_upgrade runs
        Then it returns EXIT_UNKNOWN instead of raising
        """
        err = io.StringIO()
        with (
            patch.object(subprocess, "run", side_effect=OSError("no uv")),
            redirect_stderr(err),
        ):
            self.assertEqual(
                install_update.run_upgrade("toolguard"), install_update.EXIT_UNKNOWN
            )
        self.assertIn("uv", err.getvalue())


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

    def test_main_propagates_an_uv_exit_code_outside_the_documented_set(self):
        """
        Given _check returns uv's own exit code under --upgrade
        When main runs
        Then it exits with that code rather than clamping it to 0/1/2
        """
        argv = ["toolguard-update-check", "--upgrade"]
        with (
            patch.object(update_check.sys, "argv", argv),
            patch.object(update_check, "_check", return_value=7),
        ):
            with self.assertRaises(SystemExit) as ctx:
                update_check.main()
        self.assertEqual(ctx.exception.code, 7)

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
            patch("sys.stdout", io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as ctx:
                update_check.main()
        self.assertEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
