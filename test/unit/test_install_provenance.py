"""Unit tests for toolguard.install_provenance."""

import importlib.metadata
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from toolguard import install_provenance


def _write_fake_package(root: Path, project_name="toolguard"):
    """Build the minimal source-checkout shape: pyproject.toml plus toolguard/__init__.py."""
    (root / "pyproject.toml").write_text(f'[project]\nname = "{project_name}"\n')
    pkg = root / "toolguard"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    return pkg


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
        Then it resolves the same checkout governing_package_root's parent names
        """
        result = install_provenance.source_checkout_root()
        self.assertIsNotNone(result)
        self.assertTrue((result / "toolguard" / "install_provenance.py").is_file())


class TestInstalledDistributionRoot(unittest.TestCase):
    """installed_distribution_root() -- locating the installed copy via metadata."""

    def test_returns_parent_of_located_init_file(self):
        """
        Given importlib.metadata.distribution resolves a dist whose locate_file
        points at a real __init__.py
        When installed_distribution_root runs
        Then it returns that file's parent directory
        """
        with TemporaryDirectory() as d:
            pkg = Path(d) / "toolguard"
            pkg.mkdir()
            init_file = pkg / "__init__.py"
            init_file.write_text("")
            fake_dist = SimpleNamespace(locate_file=lambda name: init_file)
            with patch.object(
                install_provenance.importlib.metadata,
                "distribution",
                return_value=fake_dist,
            ):
                self.assertEqual(install_provenance.installed_distribution_root(), pkg)

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
        ):
            self.assertIsNone(install_provenance.installed_distribution_root())

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
        ):
            self.assertIsNone(install_provenance.installed_distribution_root())

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
        ):
            self.assertIsNone(install_provenance.installed_distribution_root())


class TestGitSubtreeIsClean(unittest.TestCase):
    """_git_subtree_is_clean() -- the tri-state (True/False/None) cleanliness check."""

    def test_empty_porcelain_output_is_clean(self):
        """
        Given git status --porcelain prints nothing
        When _git_subtree_is_clean runs
        Then it returns True
        """
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with patch.object(install_provenance.subprocess, "run", return_value=completed):
            self.assertTrue(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )

    def test_nonempty_porcelain_output_is_dirty(self):
        """
        Given git status --porcelain prints a modified-file line
        When _git_subtree_is_clean runs
        Then it returns False
        """
        completed = SimpleNamespace(
            returncode=0, stdout=" M toolguard/hook.py\n", stderr=""
        )
        with patch.object(install_provenance.subprocess, "run", return_value=completed):
            self.assertFalse(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )

    def test_nonzero_exit_is_unknown(self):
        """
        Given git exits non-zero (e.g. not a work tree)
        When _git_subtree_is_clean runs
        Then it returns None (never a guess)
        """
        completed = SimpleNamespace(returncode=128, stdout="", stderr="fatal")
        with patch.object(install_provenance.subprocess, "run", return_value=completed):
            self.assertIsNone(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )

    def test_subprocess_exception_is_unknown(self):
        """
        Given git is missing or the call times out
        When _git_subtree_is_clean runs
        Then it returns None rather than raising
        """
        with patch.object(
            install_provenance.subprocess, "run", side_effect=OSError("no git")
        ):
            self.assertIsNone(
                install_provenance._git_subtree_is_clean(Path("/repo"), "toolguard")
            )


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
        ):
            report = install_provenance.stale_install_report()
        self.assertFalse(report.is_stale)
        self.assertIsNone(report.checkout_root)
        self.assertIsNone(report.installed_root)

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
            ):
                report = install_provenance.stale_install_report(checkout)
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
                ),
            ):
                report = install_provenance.stale_install_report(checkout)
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
                ),
            ):
                report = install_provenance.stale_install_report(checkout)
        self.assertFalse(report.is_stale)

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
            pkg = Path(d) / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            env = {"PYTHONPATH": d}
            self.assertEqual(install_provenance.pythonpath_shadow_entries(env), (d,))

    def test_entry_without_toolguard_package_is_not_flagged(self):
        """
        Given PYTHONPATH contains an ordinary directory with no toolguard/ package
        When pythonpath_shadow_entries runs
        Then it returns an empty tuple
        """
        with TemporaryDirectory() as d:
            env = {"PYTHONPATH": d}
            self.assertEqual(install_provenance.pythonpath_shadow_entries(env), ())

    def test_only_shadowing_entries_are_returned_from_a_mixed_list(self):
        """
        Given PYTHONPATH lists a shadowing directory and a harmless one
        When pythonpath_shadow_entries runs
        Then only the shadowing entry is returned
        """
        with TemporaryDirectory() as shadow_dir, TemporaryDirectory() as plain_dir:
            pkg = Path(shadow_dir) / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            env = {"PYTHONPATH": os.pathsep.join([plain_dir, shadow_dir])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow_dir,)
            )

    def test_duplicate_entries_are_deduplicated(self):
        """
        Given PYTHONPATH lists the same shadowing directory twice
        When pythonpath_shadow_entries runs
        Then it is reported only once
        """
        with TemporaryDirectory() as shadow_dir:
            pkg = Path(shadow_dir) / "toolguard"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            env = {"PYTHONPATH": os.pathsep.join([shadow_dir, shadow_dir])}
            self.assertEqual(
                install_provenance.pythonpath_shadow_entries(env), (shadow_dir,)
            )

    def test_defaults_to_os_environ_when_env_not_given(self):
        """
        Given no explicit env mapping is passed
        When pythonpath_shadow_entries runs with a real os.environ patched clean
        Then it reads PYTHONPATH from os.environ itself
        """
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(install_provenance.pythonpath_shadow_entries(), ())


if __name__ == "__main__":
    unittest.main()
