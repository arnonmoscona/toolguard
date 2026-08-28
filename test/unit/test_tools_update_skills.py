"""
Tests for ``toolguard-update-skills`` and the manifest-backed bundled-skill list.

The behaviour worth pinning is that the skill list has exactly ONE declaration
(``[tool.toolguard] bundled_skills``) and that an installed copy answers from its
own force-included bundle rather than from a repository it cannot see.
"""

import io
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from toolguard.tools import update_skills as update_skills_module
from toolguard.tools.installer import (
    InstallerError,
    _bundle_manifest,
    bundle_root,
    bundled_skill_names,
)

REPO_ROOT = Path(__file__).parent.parent.parent


def _declared_skills() -> list:
    """Read the bundled-skill names straight from the repository's pyproject.toml."""
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["tool"]["toolguard"]["bundled_skills"]


class TestBundledSkillDeclaration(unittest.TestCase):
    """The declared list, the shipped directories and the wheel config agree."""

    def test_every_declared_skill_exists_in_the_skills_tree(self):
        """
        Given the skill names declared in [tool.toolguard] bundled_skills
        When each is looked for under skills/
        Then it is a directory containing a SKILL.md
        """
        declared = _declared_skills()
        self.assertTrue(declared, "pyproject declares no bundled skills")
        for name in declared:
            skill_md = REPO_ROOT / "skills" / name / "SKILL.md"
            self.assertTrue(
                skill_md.is_file(),
                f"{name} is declared in [tool.toolguard] bundled_skills but "
                f"{skill_md} does not exist",
            )

    def test_every_skill_directory_is_declared(self):
        """
        Given the directories actually present under skills/
        When compared against the declaration
        Then none is shipped without being declared

        The reverse of the test above. A skill nobody declared is a skill
        `install-skills` and `update-skills` both silently skip.
        """
        present = {p.name for p in (REPO_ROOT / "skills").iterdir() if p.is_dir()}
        self.assertEqual(present, set(_declared_skills()))

    def test_the_wheel_force_includes_the_skills_and_the_manifest(self):
        """
        Given the wheel build configuration
        When its force-include map is read
        Then skills/ and pyproject.toml are mapped into toolguard/_bundled/

        Without both entries an installed toolguard has no skills to copy from,
        which is the whole failure this command exists to prevent.
        """
        config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
        force_include = config["tool"]["hatch"]["build"]["targets"]["wheel"][
            "force-include"
        ]
        self.assertEqual(force_include["skills"], "toolguard/_bundled/skills")
        self.assertEqual(
            force_include["pyproject.toml"], "toolguard/_bundled/manifest.toml"
        )

    def test_reader_returns_the_declared_names(self):
        """
        Given the repository checkout
        When bundled_skill_names() is called
        Then it returns exactly what pyproject declares
        """
        self.assertEqual(list(bundled_skill_names()), _declared_skills())


class TestBundleRootResolution(unittest.TestCase):
    """Where the skills are read from, in each of the two layouts."""

    def test_checkout_resolves_to_the_repository_root(self):
        """
        Given a source checkout, where toolguard/_bundled does not exist
        When bundle_root() is called
        Then it returns the repository root, which holds skills/ and pyproject.toml
        """
        root = bundle_root()
        self.assertTrue((root / "skills").is_dir())
        self.assertTrue((root / "pyproject.toml").is_file())

    def test_manifest_prefers_the_installed_name(self):
        """
        Given a bundle holding both manifest.toml and pyproject.toml
        When the manifest is resolved
        Then manifest.toml wins, so an installed copy never reads a stray pyproject
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.toml").write_text("", encoding="utf-8")
            (root / "pyproject.toml").write_text("", encoding="utf-8")
            self.assertEqual(_bundle_manifest(root).name, "manifest.toml")

    def test_missing_manifest_is_an_error_not_a_silent_empty_list(self):
        """
        Given a bundle directory with no manifest at all
        When the manifest is resolved
        Then InstallerError is raised

        A silent empty list would install nothing and report success.
        """
        with TemporaryDirectory() as tmp:
            with self.assertRaises(InstallerError):
                _bundle_manifest(Path(tmp))

    def test_manifest_without_the_section_is_an_error(self):
        """
        Given a manifest that declares no [tool.toolguard] bundled_skills
        When the names are read
        Then InstallerError is raised rather than an empty tuple returned
        """
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.toml").write_text('[project]\nname = "x"\n', "utf-8")
            with self.assertRaises(InstallerError):
                bundled_skill_names(root)


class TestUpdateSkillsCommand(unittest.TestCase):
    """The command's own behaviour: user scope, always forced, errors reported."""

    def test_list_prints_the_skills_and_installs_nothing(self):
        """
        Given --list
        When the command runs
        Then it prints each bundled skill and never reaches the install step
        """
        out = io.StringIO()
        with patch.object(update_skills_module, "cmd_install_skills") as install:
            with redirect_stdout(out):
                code = update_skills_module.main(["--list"])

        self.assertEqual(code, 0)
        install.assert_not_called()
        for name in _declared_skills():
            self.assertIn(name, out.getvalue())

    def test_install_is_user_scope_and_forced(self):
        """
        Given no arguments
        When the command runs
        Then it installs at user scope with force set and no project dir

        Force is the point: an unchanged copy is the failure being fixed, and
        `install-skills` is a no-op on an existing directory without it.
        """
        with patch.object(
            update_skills_module, "cmd_install_skills", return_value=0
        ) as install:
            code = update_skills_module.main([])

        self.assertEqual(code, 0)
        args = install.call_args.args[0]
        self.assertEqual(args.scope, "user")
        self.assertIsNone(args.project_dir)
        self.assertTrue(args.force)
        self.assertTrue(Path(args.source).is_dir())

    def test_source_is_this_installation_not_a_remote(self):
        """
        Given no arguments
        When the command runs
        Then the source is the local bundle root, so no network or git is involved
        """
        with patch.object(
            update_skills_module, "cmd_install_skills", return_value=0
        ) as install:
            update_skills_module.main([])

        self.assertEqual(install.call_args.args[0].source, str(bundle_root()))

    def test_installer_error_is_reported_and_exits_nonzero(self):
        """
        Given an install that raises InstallerError
        When the command runs
        Then the message reaches stderr and the exit code is 1
        """
        err = io.StringIO()
        with patch.object(
            update_skills_module,
            "cmd_install_skills",
            side_effect=InstallerError("no skills here"),
        ):
            with redirect_stderr(err):
                code = update_skills_module.main([])

        self.assertEqual(code, 1)
        self.assertIn("no skills here", err.getvalue())

    def test_namespace_carries_every_attribute_the_installer_reads(self):
        """
        Given the namespace this command hands to cmd_install_skills
        When compared with the attributes that function documents
        Then all four are present

        A SimpleNamespace has no schema, so a rename in the installer would
        otherwise surface as an AttributeError at the user's terminal.
        """
        with patch.object(
            update_skills_module, "cmd_install_skills", return_value=0
        ) as install:
            update_skills_module.main([])

        args = install.call_args.args[0]
        self.assertIsInstance(args, SimpleNamespace)
        for attribute in ("scope", "project_dir", "source", "force"):
            self.assertTrue(hasattr(args, attribute), f"missing {attribute}")


if __name__ == "__main__":
    unittest.main()
