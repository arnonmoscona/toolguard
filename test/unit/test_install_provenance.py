"""Unit tests for toolguard.install_provenance."""

import importlib.metadata
import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from toolguard import install_provenance

_GIT = shutil.which("git")


def _write_fake_package(root: Path, project_name="toolguard"):
    """Build the minimal source-checkout shape: pyproject.toml plus toolguard/__init__.py."""
    (root / "pyproject.toml").write_text(f'[project]\nname = "{project_name}"\n')
    pkg = root / "toolguard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return pkg


def _write_shadow_dir(root: Path) -> str:
    """Make *root* a PYTHONPATH entry that would shadow an installed toolguard."""
    pkg = root / "toolguard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return str(root)


def _git_target_dir(call):
    """
    The directory a captured ``subprocess.run`` call points git at.

    Accepts either argv form (``-C <dir>``) or an explicit ``cwd=``, so an
    equivalent reimplementation is not reported as a regression.
    """
    argv = call.args[0]
    cwd = call.kwargs.get("cwd")
    if cwd:
        return str(cwd)
    if "-C" in argv:
        return argv[argv.index("-C") + 1]
    return None


def _fake_git(*, status_stdout="", status_returncode=0, toplevel="/repo"):
    """
    A subprocess.run stand-in that answers as git would, per subcommand.

    A single canned CompletedProcess would make these tests fail for any
    implementation that asks git one more question, so the stub answers by
    subcommand instead of by call count.
    """

    def run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(returncode=0, stdout=f"{toplevel}\n", stderr="")
        if "status" in argv:
            return SimpleNamespace(
                returncode=status_returncode, stdout=status_stdout, stderr=""
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return Mock(side_effect=run)


class _FakeDistribution:
    """
    Stand-in for :class:`importlib.metadata.Distribution`.

    ``locate_file`` joins onto a real temp "site-packages" directory exactly as
    the real one does, so a caller asking for the wrong relative path gets a
    path that does not exist rather than a helpful answer.
    """

    def __init__(self, site_dir: Path):
        self.site_dir = site_dir

    def locate_file(self, name):
        return self.site_dir / str(name)


def _fake_metadata_lookup(site_dir: Path, *installed_names):
    """Build a distribution() stand-in that knows only *installed_names*."""

    def distribution(name):
        if name not in installed_names:
            raise importlib.metadata.PackageNotFoundError(name)
        return _FakeDistribution(site_dir)

    return distribution


class TestGoverningPackageRoot(unittest.TestCase):
    """governing_package_root() -- the directory of THIS import."""

    def test_returns_the_real_toolguard_package_directory(self):
        """
        Given the real, installed toolguard package
        When governing_package_root runs
        Then it returns a directory literally named 'toolguard' holding
        install_provenance.py itself
        """
        root = install_provenance.governing_package_root()
        self.assertEqual(root.name, "toolguard")
        self.assertTrue((root / "install_provenance.py").is_file())


class TestSourceCheckoutRoot(unittest.TestCase):
    """source_checkout_root() -- classifying a package directory as a checkout."""

    def test_recognises_a_well_formed_checkout(self):
        """
        Given a directory with a sibling pyproject.toml naming 'toolguard'
        and a toolguard/__init__.py
        When source_checkout_root runs
        Then it returns the checkout root
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            pkg = _write_fake_package(root)
            self.assertEqual(install_provenance.source_checkout_root(pkg), root)

    def test_missing_init_py_returns_none(self):
        """
        Given a package directory with NO __init__.py (not a real package)
        When source_checkout_root runs
        Then it returns None even though a matching pyproject.toml exists
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text('[project]\nname = "toolguard"\n')
            pkg = root / "toolguard"
            pkg.mkdir()
            self.assertIsNone(install_provenance.source_checkout_root(pkg))

    def test_missing_pyproject_returns_none(self):
        """
        Given a package directory with __init__.py but NO sibling pyproject.toml
        When source_checkout_root runs
        Then it returns None -- this is what an installed distribution looks like
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            pkg = root / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            self.assertIsNone(install_provenance.source_checkout_root(pkg))

    def test_pyproject_naming_a_different_project_returns_none(self):
        """
        Given a sibling pyproject.toml that names a DIFFERENT project
        When source_checkout_root runs
        Then it returns None -- an unrelated nested layout must not false-positive
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            pkg = _write_fake_package(root, project_name="some-other-project")
            self.assertIsNone(install_provenance.source_checkout_root(pkg))

    def test_explicit_expected_name_is_honoured(self):
        """
        Given a checkout whose pyproject.toml names 'some-other-project'
        When source_checkout_root runs with that expected_name
        Then it returns the checkout root, while the default name still rejects it
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            pkg = _write_fake_package(root, project_name="some-other-project")
            self.assertEqual(
                install_provenance.source_checkout_root(
                    pkg, expected_name="some-other-project"
                ),
                root,
            )
            self.assertIsNone(install_provenance.source_checkout_root(pkg))

    def test_malformed_toml_returns_none_without_raising(self):
        """
        Given a sibling pyproject.toml that is not valid TOML
        When source_checkout_root runs
        Then it returns None rather than propagating a parse error
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "pyproject.toml").write_text("not [ valid toml")
            pkg = root / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            self.assertIsNone(install_provenance.source_checkout_root(pkg))

    def test_default_argument_uses_governing_package_root(self):
        """
        Given no explicit package_root argument, running inside this real checkout
        When source_checkout_root runs
        Then it returns the parent of the governing package directory
        """
        governing = install_provenance.governing_package_root()
        result = install_provenance.source_checkout_root()
        self.assertIsNotNone(result)
        self.assertTrue((result / "toolguard" / "install_provenance.py").is_file())
        self.assertEqual(result / governing.name, governing)


class TestInstalledDistributionRoot(unittest.TestCase):
    """installed_distribution_root() -- locating the installed copy via metadata."""

    def test_returns_parent_of_located_init_file(self):
        """
        Given a toolguard distribution whose site-packages holds toolguard/__init__.py
        When installed_distribution_root runs
        Then it returns that package directory
        """
        with TemporaryDirectory() as d:
            site = Path(d)
            pkg = site / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            with patch.object(
                install_provenance.importlib.metadata,
                "distribution",
                _fake_metadata_lookup(site, "toolguard"),
            ):
                self.assertEqual(install_provenance.installed_distribution_root(), pkg)

    def test_explicit_dist_name_is_honoured(self):
        """
        Given only a distribution named 'other-dist' is installed
        When installed_distribution_root runs with that name
        Then it returns other-dist's package directory, while the default name
        finds nothing
        """
        with TemporaryDirectory() as d:
            site = Path(d)
            pkg = site / "other-dist"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            with patch.object(
                install_provenance.importlib.metadata,
                "distribution",
                _fake_metadata_lookup(site, "other-dist"),
            ):
                self.assertEqual(
                    install_provenance.installed_distribution_root("other-dist"), pkg
                )
                self.assertIsNone(install_provenance.installed_distribution_root())

    def test_package_not_found_returns_none(self):
        """
        Given no toolguard distribution is installed at all
        When installed_distribution_root runs
        Then it returns None rather than raising
        """
        with patch.object(
            install_provenance.importlib.metadata,
            "distribution",
            side_effect=importlib.metadata.PackageNotFoundError("toolguard"),
        ) as lookup:
            self.assertIsNone(install_provenance.installed_distribution_root())
        lookup.assert_called_once()

    def test_located_file_missing_returns_none(self):
        """
        Given locate_file resolves to a path that does not actually exist
        When installed_distribution_root runs
        Then it returns None
        """
        fake_dist = SimpleNamespace(
            locate_file=lambda name: Path("/definitely/does/not/exist/__init__.py")
        )
        with patch.object(
            install_provenance.importlib.metadata,
            "distribution",
            return_value=fake_dist,
        ) as lookup:
            self.assertIsNone(install_provenance.installed_distribution_root())
        lookup.assert_called_once()

    def test_locate_file_raising_returns_none(self):
        """
        Given dist.locate_file itself raises
        When installed_distribution_root runs
        Then it returns None rather than propagating
        """

        def _boom(name):
            raise RuntimeError("boom")

        fake_dist = SimpleNamespace(locate_file=_boom)
        with patch.object(
            install_provenance.importlib.metadata,
            "distribution",
            return_value=fake_dist,
        ) as lookup:
            self.assertIsNone(install_provenance.installed_distribution_root())
        lookup.assert_called_once()


class TestGitSubtreeIsClean(unittest.TestCase):
    """_git_subtree_is_clean() -- the tri-state (True/False/None) cleanliness check."""

    # These patch install_provenance.subprocess.run, which reaches the call in
    # toolguard._git.run_git only because both names are the ONE global
    # subprocess module object.

    def assert_git_asked_about(self, run, directory, subtree):
        """Prove the patch was reached, pointed at *directory* and scoped to *subtree*."""
        self.assertTrue(run.called, "subprocess.run was never reached")
        calls = [(_git_target_dir(c), c.args[0]) for c in run.call_args_list]
        self.assertIn(directory, [target for target, _ in calls], calls)
        self.assertTrue(any(subtree in argv for _, argv in calls), calls)

    def test_empty_porcelain_output_is_clean(self):
        """
        Given git status --porcelain prints nothing
        When _git_subtree_is_clean runs
        Then it returns True, having asked git about the given checkout and subtree
        """
        with patch.object(
            install_provenance.subprocess, "run", _fake_git(status_stdout="")
        ) as run:
            self.assertTrue(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )
        self.assert_git_asked_about(run, "/repo", "toolguard")

    def test_nonempty_porcelain_output_is_dirty(self):
        """
        Given git status --porcelain prints a modified-file line
        When _git_subtree_is_clean runs
        Then it returns False, having asked git about the given checkout and subtree
        """
        with patch.object(
            install_provenance.subprocess,
            "run",
            _fake_git(status_stdout=" M toolguard/hook.py\n"),
        ) as run:
            self.assertFalse(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )
        self.assert_git_asked_about(run, "/repo", "toolguard")

    def test_nonzero_exit_is_unknown(self):
        """
        Given the status query exits non-zero (e.g. not a work tree)
        When _git_subtree_is_clean runs
        Then it returns None (never a guess)
        """
        with patch.object(
            install_provenance.subprocess, "run", _fake_git(status_returncode=128)
        ) as run:
            self.assertIsNone(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )
        self.assertTrue(run.called)

    def test_subprocess_exception_is_unknown(self):
        """
        Given git is missing or the call times out
        When _git_subtree_is_clean runs
        Then it returns None rather than raising
        """
        with patch.object(
            install_provenance.subprocess, "run", side_effect=OSError("no git")
        ) as run:
            self.assertIsNone(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )
        self.assertTrue(run.called)


class RealGitFixtureMixin:
    """
    Builds real git repositories inside a throwaway HOME.

    Git is genuinely run, so the environment is neutralised: global/system
    config, an upward-walk ceiling, and a committer identity. Without the
    ceiling a fixture's repository lookup can escape into whatever repository
    happens to contain the temp directory.
    """

    def setUp(self):
        super().setUp()
        if _GIT is None:
            self.skipTest("git is not installed; anchoring cannot be measured")
        self.home = Path(self.enterContext(TemporaryDirectory())).resolve()
        self.enterContext(
            patch.dict(
                os.environ,
                {
                    "HOME": str(self.home),
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                    "GIT_CEILING_DIRECTORIES": str(self.home),
                    "GIT_AUTHOR_NAME": "toolguard test",
                    "GIT_AUTHOR_EMAIL": "test@example.invalid",
                    "GIT_COMMITTER_NAME": "toolguard test",
                    "GIT_COMMITTER_EMAIL": "test@example.invalid",
                },
            )
        )

    def make_repo(self, name, package_files, other_files=()):
        """Create and commit a repository holding a toolguard/ package subtree."""
        repo = self.home / name
        (repo / "toolguard").mkdir(parents=True)
        for rel, text in package_files:
            path = repo / "toolguard" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        for rel, text in other_files:
            (repo / rel).write_text(text)
        for argv in (
            ["init", "-q", str(repo)],
            ["-C", str(repo), "add", "-A"],
            ["-C", str(repo), "commit", "-qm", "initial"],
        ):
            subprocess.run([_GIT, *argv], check=True, capture_output=True, text=True)
        return repo


class TestGitSubtreeIsCleanAgainstRealGit(RealGitFixtureMixin, unittest.TestCase):
    """_git_subtree_is_clean() run against real repositories, from a foreign cwd."""

    def setUp(self):
        super().setUp()
        self.repo = self.make_repo(
            "clean-repo", [("a.py", "print(1)\n")], [("docs.md", "hi\n")]
        )
        # A second, DIRTY repository is made the process cwd, so a check that
        # forgot to anchor on its argument would answer about this one instead.
        self.other = self.make_repo("other-repo", [("a.py", "print(9)\n")])
        (self.other / "toolguard" / "a.py").write_text("print(10)\n")
        original_cwd = os.getcwd()
        self.addCleanup(self.assertEqual, original_cwd, os.getcwd())
        self.addCleanup(os.chdir, original_cwd)
        os.chdir(self.other)

    def test_committed_subtree_is_clean(self):
        """
        Given a committed repository with no uncommitted changes
        When _git_subtree_is_clean runs on it from inside a different, dirty repository
        Then it returns True -- the answer is about the directory it was given
        """
        self.assertTrue(
            install_provenance._git_subtree_is_clean(self.repo, "toolguard")
        )

    def test_modified_file_inside_the_subtree_is_dirty(self):
        """
        Given a tracked file under toolguard/ has been modified
        When _git_subtree_is_clean runs
        Then it returns False
        """
        (self.repo / "toolguard" / "a.py").write_text("print(2)\n")
        self.assertFalse(
            install_provenance._git_subtree_is_clean(self.repo, "toolguard")
        )

    def test_untracked_file_inside_the_subtree_is_dirty(self):
        """
        Given a new, untracked file under toolguard/
        When _git_subtree_is_clean runs
        Then it returns False -- an untracked file is a difference from the commit
        """
        (self.repo / "toolguard" / "new.py").write_text("print(3)\n")
        self.assertFalse(
            install_provenance._git_subtree_is_clean(self.repo, "toolguard")
        )

    def test_change_outside_the_subtree_leaves_it_clean(self):
        """
        Given the repository is dirty only OUTSIDE toolguard/
        When _git_subtree_is_clean runs on the toolguard subtree
        Then it returns True -- the question is scoped to the subtree
        """
        (self.repo / "docs.md").write_text("changed\n")
        self.assertTrue(
            install_provenance._git_subtree_is_clean(self.repo, "toolguard")
        )

    def test_directory_that_is_not_a_work_tree_is_unknown(self):
        """
        Given a directory that is not inside any git work tree
        When _git_subtree_is_clean runs
        Then it returns None rather than guessing
        """
        plain = self.home / "not-a-repo"
        (plain / "toolguard").mkdir(parents=True)
        self.assertIsNone(install_provenance._git_subtree_is_clean(plain, "toolguard"))

    def test_untracked_checkout_inside_an_unrelated_repository_is_unknown(self):
        """
        Given a checkout that git tracks nothing of, nested inside an unrelated
        repository that ignores it
        When _git_subtree_is_clean runs
        Then it returns None -- the ancestor repository's cleanliness is not this
        checkout's, and "clean" here was never measured
        """
        outer = self.make_repo(
            "outer", [("z.py", "print(0)\n")], [(".gitignore", "nested/\n")]
        )
        nested = outer / "nested" / "checkout"
        (nested / "toolguard").mkdir(parents=True)
        (nested / "toolguard" / "a.py").write_text("print(1)\n")
        self.assertIsNone(install_provenance._git_subtree_is_clean(nested, "toolguard"))


class TestHashPyFiles(unittest.TestCase):
    """_hash_py_files() -- deterministic content digest over a directory."""

    def test_identical_content_hashes_equal_regardless_of_creation_order(self):
        """
        Given two directories with the same relative .py files and content,
        created in a DIFFERENT order
        When _hash_py_files runs on each
        Then the digests are equal
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            root1, root2 = Path(d1), Path(d2)
            (root1 / "b.py").write_text("print(2)\n")
            (root1 / "a.py").write_text("print(1)\n")
            (root2 / "a.py").write_text("print(1)\n")
            (root2 / "b.py").write_text("print(2)\n")
            self.assertEqual(
                install_provenance._hash_py_files(root1),
                install_provenance._hash_py_files(root2),
            )

    def test_differing_content_hashes_differ(self):
        """
        Given two directories whose same-named .py file has different content
        When _hash_py_files runs on each
        Then the digests differ
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            root1, root2 = Path(d1), Path(d2)
            (root1 / "a.py").write_text("print(1)\n")
            (root2 / "a.py").write_text("print(2)\n")
            self.assertNotEqual(
                install_provenance._hash_py_files(root1),
                install_provenance._hash_py_files(root2),
            )

    def test_content_in_a_subpackage_reaches_the_digest(self):
        """
        Given two directories differing only in a .py file one level down
        When _hash_py_files runs on each
        Then the digests differ -- the scan is recursive, not top-level only
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            root1, root2 = Path(d1), Path(d2)
            for root, body in ((root1, "print(1)\n"), (root2, "print(2)\n")):
                (root / "a.py").write_text("print(0)\n")
                (root / "parser").mkdir()
                (root / "parser" / "b.py").write_text(body)
            self.assertNotEqual(
                install_provenance._hash_py_files(root1),
                install_provenance._hash_py_files(root2),
            )

    def test_same_content_at_a_different_relative_path_hashes_differently(self):
        """
        Given two directories holding identical file CONTENT at different
        relative paths
        When _hash_py_files runs on each
        Then the digests differ -- a moved file is a difference
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            root1, root2 = Path(d1), Path(d2)
            (root1 / "a.py").write_text("print(1)\n")
            (root2 / "sub").mkdir()
            (root2 / "sub" / "a.py").write_text("print(1)\n")
            self.assertNotEqual(
                install_provenance._hash_py_files(root1),
                install_provenance._hash_py_files(root2),
            )

    def test_unreadable_py_file_makes_the_digest_undetermined(self):
        """
        Given a .py file under the root that cannot be read
        When _hash_py_files runs
        Then it returns None -- an unreadable file is uncertainty, and this
        module's rule is that uncertainty is never turned into a difference
        """
        with TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text("print(1)\n")
            (root / "broken.py").symlink_to(root / "missing-target.py")
            with self.assertRaises(OSError):
                (root / "broken.py").read_bytes()
            self.assertIsNone(install_provenance._hash_py_files(root))

    def test_no_py_files_returns_none(self):
        """
        Given a directory with no .py files at all
        When _hash_py_files runs
        Then it returns None -- an empty root must never look like a "match"
        """
        with TemporaryDirectory() as d:
            (Path(d) / "readme.txt").write_text("hi")
            self.assertIsNone(install_provenance._hash_py_files(Path(d)))

    def test_nonexistent_directory_returns_none(self):
        """
        Given a root path that does not exist
        When _hash_py_files runs
        Then it returns None
        """
        self.assertIsNone(
            install_provenance._hash_py_files(Path("/definitely/does/not/exist"))
        )


class TestStaleInstallReport(unittest.TestCase):
    """stale_install_report() -- the composed, silent-on-uncertainty predicate."""

    def test_no_checkout_root_reports_not_stale(self):
        """
        Given checkout_root is None and source_checkout_root() also finds none
        When stale_install_report runs
        Then it reports is_stale=False with both roots None
        """
        with patch.object(
            install_provenance, "source_checkout_root", return_value=None
        ) as finder:
            report = install_provenance.stale_install_report()
        finder.assert_called_once()
        self.assertFalse(report.is_stale)
        self.assertIsNone(report.checkout_root)
        self.assertIsNone(report.installed_root)

    def test_omitted_checkout_root_falls_back_to_the_governing_checkout(self):
        """
        Given no checkout_root argument and source_checkout_root() finds one
        When stale_install_report runs
        Then that checkout is the one reported and compared
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            (installed / "a.py").write_text("print(2)\n")
            with (
                patch.object(
                    install_provenance, "source_checkout_root", return_value=checkout
                ) as finder,
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=True
                ),
            ):
                report = install_provenance.stale_install_report()
        finder.assert_called_once()
        self.assertEqual(report.checkout_root, checkout)
        self.assertTrue(report.is_stale)

    def test_no_installed_distribution_reports_not_stale(self):
        """
        Given a real checkout_root but no installed distribution can be found
        When stale_install_report runs
        Then it reports is_stale=False (nothing to compare against)
        """
        with TemporaryDirectory() as d:
            checkout = Path(d)
            (checkout / "toolguard").mkdir()
            with patch.object(
                install_provenance, "installed_distribution_root", return_value=None
            ) as locator:
                report = install_provenance.stale_install_report(checkout)
        locator.assert_called_once()
        self.assertFalse(report.is_stale)
        self.assertEqual(report.checkout_root, checkout)
        self.assertIsNone(report.installed_root)

    def test_dirty_tree_reports_not_stale(self):
        """
        Given the checkout is confirmed DIRTY (uncommitted changes)
        When stale_install_report runs
        Then it reports is_stale=False even if content would otherwise differ --
        never nag on an ordinary dev-loop dirty tree
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            (installed / "a.py").write_text("print(2)\n")
            with (
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=False
                ) as cleanliness,
            ):
                report = install_provenance.stale_install_report(checkout)
        cleanliness.assert_called_once()
        self.assertEqual(cleanliness.call_args.args[0], checkout)
        self.assertFalse(report.is_stale)

    def test_undetermined_cleanliness_reports_not_stale(self):
        """
        Given cleanliness could not be determined (git unavailable/not a repo)
        When stale_install_report runs
        Then it reports is_stale=False -- uncertainty stays silent, never a guess
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            (installed / "a.py").write_text("print(2)\n")
            with (
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=None
                ) as cleanliness,
            ):
                report = install_provenance.stale_install_report(checkout)
        cleanliness.assert_called_once()
        self.assertFalse(report.is_stale)

    def test_unhashable_installed_root_reports_not_stale(self):
        """
        Given a clean checkout but an installed root holding no .py files
        When stale_install_report runs
        Then it reports is_stale=False -- a degenerate side is undetermined, not
        a difference
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            (installed / "readme.txt").write_text("no python here")
            with (
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=True
                ),
            ):
                report = install_provenance.stale_install_report(checkout)
        self.assertFalse(report.is_stale)
        self.assertEqual(report.installed_root, installed)

    def test_clean_and_matching_content_reports_not_stale(self):
        """
        Given the tree is clean and its content hash MATCHES the installed copy
        When stale_install_report runs
        Then it reports is_stale=False
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            # A decoy outside the package directory: only checkout/toolguard/
            # is the subject of the comparison.
            (checkout / "setup.py").write_text("print(999)\n")
            (installed / "a.py").write_text("print(1)\n")
            with (
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=True
                ),
            ):
                report = install_provenance.stale_install_report(checkout)
        self.assertFalse(report.is_stale)

    def test_clean_and_differing_content_reports_stale(self):
        """
        Given the tree is CLEAN and its content hash DIFFERS from the installed copy
        When stale_install_report runs
        Then it reports is_stale=True -- the one actionable case
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            checkout, installed = Path(d1), Path(d2)
            (checkout / "toolguard").mkdir()
            (checkout / "toolguard" / "a.py").write_text("print(1)\n")
            (installed / "a.py").write_text("print(2)\n")
            with (
                patch.object(
                    install_provenance,
                    "installed_distribution_root",
                    return_value=installed,
                ),
                patch.object(
                    install_provenance, "_git_subtree_is_clean", return_value=True
                ),
            ):
                report = install_provenance.stale_install_report(checkout)
        self.assertTrue(report.is_stale)
        self.assertEqual(report.checkout_root, checkout)
        self.assertEqual(report.installed_root, installed)


class TestStaleInstallReportAgainstRealGit(RealGitFixtureMixin, unittest.TestCase):
    """stale_install_report() with git really run against a real checkout."""

    def setUp(self):
        super().setUp()
        self.checkout = self.make_repo(
            "checkout", [("a.py", "print(1)\n")], [("docs.md", "hi\n")]
        )
        self.installed = self.home / "site-packages" / "toolguard"
        self.installed.mkdir(parents=True)
        (self.installed / "a.py").write_text("print(2)\n")

    def _report(self):
        with patch.object(
            install_provenance,
            "installed_distribution_root",
            return_value=self.installed,
        ):
            return install_provenance.stale_install_report(self.checkout)

    def test_clean_checkout_differing_from_the_install_is_stale(self):
        """
        Given a committed checkout whose toolguard/ content differs from the
        installed copy
        When stale_install_report runs with git really executed
        Then it reports is_stale=True
        """
        self.assertTrue(self._report().is_stale)

    def test_change_outside_the_package_does_not_silence_the_report(self):
        """
        Given the checkout is dirty only OUTSIDE toolguard/
        When stale_install_report runs
        Then it still reports is_stale=True -- cleanliness is asked about the
        package subtree, not the whole repository
        """
        (self.checkout / "docs.md").write_text("changed\n")
        self.assertTrue(self._report().is_stale)

    def test_change_inside_the_package_silences_the_report(self):
        """
        Given the checkout has an uncommitted change under toolguard/
        When stale_install_report runs
        Then it reports is_stale=False -- an ordinary dev loop must not nag
        """
        (self.checkout / "toolguard" / "a.py").write_text("print(3)\n")
        self.assertFalse(self._report().is_stale)

    def test_checkout_matching_the_install_is_not_stale(self):
        """
        Given a committed checkout whose toolguard/ content matches the install
        When stale_install_report runs
        Then it reports is_stale=False
        """
        (self.installed / "a.py").write_text("print(1)\n")
        self.assertFalse(self._report().is_stale)

    def test_checkout_that_is_not_a_git_repository_is_not_stale(self):
        """
        Given a source checkout that is not under git at all
        When stale_install_report runs
        Then it reports is_stale=False -- cleanliness is undetermined, so the
        differing content is never announced
        """
        self.checkout = self.home / "unversioned"
        (self.checkout / "toolguard").mkdir(parents=True)
        (self.checkout / "toolguard" / "a.py").write_text("print(1)\n")
        self.assertFalse(self._report().is_stale)

    def test_untracked_checkout_nested_in_another_repository_is_not_stale(self):
        """
        Given an unversioned checkout nested inside an unrelated repository that
        ignores it
        When stale_install_report runs
        Then it reports is_stale=False -- announcing "this checkout has changes
        that are not in the installed distribution" would assert a cleanliness
        nothing established
        """
        outer = self.make_repo(
            "outer", [("z.py", "print(0)\n")], [(".gitignore", "nested/\n")]
        )
        self.checkout = outer / "nested" / "checkout"
        (self.checkout / "toolguard").mkdir(parents=True)
        (self.checkout / "toolguard" / "a.py").write_text("print(1)\n")
        self.assertFalse(self._report().is_stale)


class TestPythonpathShadowEntries(unittest.TestCase):
    """pythonpath_shadow_entries() -- the predictive PYTHONPATH-shadow predicate."""

    def test_unset_pythonpath_returns_empty(self):
        """
        Given PYTHONPATH is not set at all
        When pythonpath_shadow_entries runs
        Then it returns an empty tuple
        """
        self.assertEqual(install_provenance.pythonpath_shadow_entries({}), ())

    def test_entry_with_toolguard_package_is_flagged(self):
        """
        Given PYTHONPATH contains a directory holding its own toolguard/ package
        When pythonpath_shadow_entries runs
        Then that entry is returned
        """
        with TemporaryDirectory() as d:
            shadow = _write_shadow_dir(Path(d))
            env = {"PYTHONPATH": shadow}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow,)
            )

    def test_entry_without_toolguard_package_is_not_flagged(self):
        """
        Given PYTHONPATH contains an ordinary directory with no toolguard/ package
        When pythonpath_shadow_entries runs
        Then it returns an empty tuple
        """
        with TemporaryDirectory() as d:
            env = {"PYTHONPATH": d}
            self.assertEqual(install_provenance.pythonpath_shadow_entries(env), ())

    def test_toolguard_directory_without_init_py_is_not_flagged(self):
        """
        Given PYTHONPATH contains a directory holding a toolguard/ folder that
        is not an importable package
        When pythonpath_shadow_entries runs
        Then it returns an empty tuple -- only a real package can shadow
        """
        with TemporaryDirectory() as d:
            (Path(d) / "toolguard").mkdir()
            env = {"PYTHONPATH": d}
            self.assertEqual(install_provenance.pythonpath_shadow_entries(env), ())

    def test_only_shadowing_entries_are_returned_from_a_mixed_list(self):
        """
        Given PYTHONPATH lists a shadowing directory and a harmless one
        When pythonpath_shadow_entries runs
        Then only the shadowing entry is returned
        """
        with TemporaryDirectory() as shadow_dir, TemporaryDirectory() as plain_dir:
            shadow = _write_shadow_dir(Path(shadow_dir))
            env = {"PYTHONPATH": os.pathsep.join([plain_dir, shadow])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow,)
            )

    def test_several_shadowing_entries_keep_their_original_order(self):
        """
        Given PYTHONPATH lists two shadowing directories
        When pythonpath_shadow_entries runs
        Then both are returned in the order PYTHONPATH gave them
        """
        with TemporaryDirectory() as d1, TemporaryDirectory() as d2:
            first = _write_shadow_dir(Path(d1))
            second = _write_shadow_dir(Path(d2))
            env = {"PYTHONPATH": os.pathsep.join([first, second])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (first, second)
            )

    def test_duplicate_entries_are_deduplicated(self):
        """
        Given PYTHONPATH lists the same shadowing directory twice
        When pythonpath_shadow_entries runs
        Then it is reported only once
        """
        with TemporaryDirectory() as d:
            shadow = _write_shadow_dir(Path(d))
            env = {"PYTHONPATH": os.pathsep.join([shadow, shadow])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow,)
            )

    def test_empty_entry_is_not_reported_even_from_a_shadowing_cwd(self):
        """
        Given PYTHONPATH has an empty entry and the process cwd itself holds a
        toolguard/ package
        When pythonpath_shadow_entries runs
        Then the empty entry is not reported -- "" would name the cwd, which is
        not what PYTHONPATH asked for
        """
        with TemporaryDirectory() as cwd_dir, TemporaryDirectory() as d:
            _write_shadow_dir(Path(cwd_dir))
            shadow = _write_shadow_dir(Path(d))
            original_cwd = os.getcwd()
            self.addCleanup(self.assertEqual, original_cwd, os.getcwd())
            self.addCleanup(os.chdir, original_cwd)
            os.chdir(cwd_dir)
            env = {"PYTHONPATH": os.pathsep.join(["", shadow])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow,)
            )

    def test_defaults_to_os_environ_when_env_not_given(self):
        """
        Given no explicit env mapping is passed and os.environ names a
        shadowing directory
        When pythonpath_shadow_entries runs
        Then that entry is returned -- the default really reads os.environ
        """
        with TemporaryDirectory() as d:
            shadow = _write_shadow_dir(Path(d))
            with patch.dict(os.environ, {"PYTHONPATH": shadow}, clear=True):
                self.assertEqual(
                    install_provenance.pythonpath_shadow_entries(), (shadow,)
                )

    def test_no_pythonpath_in_os_environ_returns_empty(self):
        """
        Given no explicit env mapping and an environment with no PYTHONPATH
        When pythonpath_shadow_entries runs
        Then it returns an empty tuple
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(install_provenance.pythonpath_shadow_entries(), ())


if __name__ == "__main__":
    unittest.main()
