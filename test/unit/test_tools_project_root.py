"""
Unit tests for the repo-grain migration project-root resolver.

These exercise :func:`toolguard.tools.project_root.resolve_project_root`, the pure
primitive that classifies the project boundary for the migration safety gate.
Each test uses a temporary directory tree so the walk-up is fully controlled.
"""

import tempfile
import unittest
from pathlib import Path

from toolguard.tools.project_root import (
    ProjectRootResolution,
    RootStatus,
    resolve_project_root,
)


class TestResolveProjectRoot(unittest.TestCase):
    """Resolution of the migration project boundary into a structured result."""

    def setUp(self):
        """Create an isolated temp tree rooted under a fresh directory."""
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()

    def tearDown(self):
        """Remove the temp tree."""
        self._tmp.cleanup()

    def test_vcs_root_resolves(self):
        """
        Given a directory tree whose top holds a .git marker and a nested start dir
        When resolve_project_root is called from the nested dir
        Then the status is RESOLVED_ANCHOR, the root is the .git directory, and
            the result reports it is safe to migrate.
        """
        (self.root / ".git").mkdir()
        nested = self.root / "pkg" / "sub"
        nested.mkdir(parents=True)

        result = resolve_project_root(nested)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)
        self.assertTrue(result.safe_to_migrate)

    def test_vcs_root_wins_over_nearer_pyproject(self):
        """
        Given a .git at the repo top and a pyproject.toml in a nearer sub-package
        When resolve_project_root is called from inside the sub-package
        Then the repo-grain anchor root (not the nearer package) is returned.
        """
        (self.root / ".git").mkdir()
        pkg = self.root / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text("[project]\n")

        result = resolve_project_root(pkg)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)

    def test_claude_directory_alone_resolves_as_anchor(self):
        """
        Given a directory tree whose top holds only a .claude directory (no VCS
            marker) and a nested start dir
        When resolve_project_root is called from the nested dir
        Then the status is RESOLVED_ANCHOR (TOO-15: .claude is a first-class
            anchor, the same trust tier as a VCS root, not a weaker ask-first
            candidate) and it is safe to migrate.
        """
        (self.root / ".claude").mkdir()
        nested = self.root / "pkg" / "sub"
        nested.mkdir(parents=True)

        result = resolve_project_root(nested)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)
        self.assertTrue(result.safe_to_migrate)

    def test_claude_md_file_alone_resolves_as_anchor(self):
        """
        Given a directory tree whose top holds only a bare CLAUDE.md file (no
            VCS marker) and a nested start dir
        When resolve_project_root is called from the nested dir
        Then the status is RESOLVED_ANCHOR and it is safe to migrate.
        """
        (self.root / "CLAUDE.md").write_text("# Project\n")
        nested = self.root / "pkg" / "sub"
        nested.mkdir(parents=True)

        result = resolve_project_root(nested)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)
        self.assertTrue(result.safe_to_migrate)

    def test_nearest_anchor_wins_regardless_of_kind(self):
        """
        Given a .git at the repo top and a NEARER .claude directory in a
            sub-package below it
        When resolve_project_root is called from inside the sub-package
        Then the nearer .claude directory wins over the farther .git root --
            anchors are all one tier, resolved nearest-first, not VCS-first.
        """
        (self.root / ".git").mkdir()
        pkg = self.root / "pkg"
        pkg.mkdir()
        (pkg / ".claude").mkdir()

        result = resolve_project_root(pkg)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, pkg)

    def test_strict_mode_nearest_marker_wins_over_tiered_default(self):
        """
        Given a .git at the repo top and a NEARER pyproject.toml in a sub-package
            below it
        When resolve_project_root is called from inside the sub-package once with
            strict=True and once with the tiered default (strict=False)
        Then strict=True returns the NEARER pyproject.toml directory (flat,
            nearest-marker-of-any-kind-wins -- the config.py/env_config.py
            semantics), while the tiered default returns the FARTHER .git anchor
            root instead (anchor tier climbed fully before falling back to the
            weaker tier -- the migration-gate semantics). This is the actual
            behavioral differentiator between the two modes: an implementation
            that just unwraps the tiered algorithm's .root for strict=True would
            pass every other test in this file but fail this one.
        """
        (self.root / ".git").mkdir()
        pkg = self.root / "pkg"
        pkg.mkdir()
        (pkg / "pyproject.toml").write_text("[project]\n")

        strict_result = resolve_project_root(pkg, strict=True)
        tiered_result = resolve_project_root(pkg)

        self.assertEqual(strict_result.root, pkg)
        self.assertEqual(tiered_result.root, self.root)

    def test_strict_mode_never_returns_ambiguous(self):
        """
        Given only a weak marker (pyproject.toml) and no anchor anywhere in the
            tree
        When resolve_project_root is called with strict=True
        Then the status resolves directly to the pyproject.toml directory as
            RESOLVED_ANCHOR rather than AMBIGUOUS -- strict mode never asks the
            caller to disambiguate; it always picks the nearest marker of any
            kind. (Contrast with test_build_marker_without_vcs_is_ambiguous,
            which exercises the same fixture shape under the tiered default and
            gets AMBIGUOUS instead.)
        """
        (self.root / "pyproject.toml").write_text("[project]\n")

        result = resolve_project_root(self.root, strict=True)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)
        self.assertTrue(result.safe_to_migrate)

    def test_build_marker_without_vcs_is_ambiguous(self):
        """
        Given a pyproject.toml but no version-control marker anywhere
        When resolve_project_root is called
        Then the status is AMBIGUOUS, the pyproject dir is offered as a candidate,
            and it is NOT considered safe to migrate.
        """
        (self.root / "pyproject.toml").write_text("[project]\n")

        result = resolve_project_root(self.root)

        self.assertEqual(result.status, RootStatus.AMBIGUOUS)
        self.assertFalse(result.safe_to_migrate)
        self.assertTrue(any(c.marker == "pyproject.toml" for c in result.candidates))

    def test_no_marker_refuses(self):
        """
        Given a directory tree with no VCS root and no project markers
        When resolve_project_root is called
        Then the status is NONE, no root is returned, it is not safe to migrate,
            and the reason advises putting the project under version control.
        """
        bare = self.root / "bare"
        bare.mkdir()

        result = resolve_project_root(bare)

        self.assertEqual(result.status, RootStatus.NONE)
        self.assertIsNone(result.root)
        self.assertFalse(result.safe_to_migrate)
        self.assertIn("version control", result.reason)

    def test_override_is_honoured_unconditionally(self):
        """
        Given an explicit override path AND a different VCS root in the tree
        When resolve_project_root is called with the override
        Then the status is RESOLVED_OVERRIDE and the override path is the root,
            taking precedence over the discoverable VCS root.
        """
        (self.root / ".git").mkdir()
        override = self.root / "chosen"
        override.mkdir()

        result = resolve_project_root(self.root, override=override)

        self.assertEqual(result.status, RootStatus.RESOLVED_OVERRIDE)
        self.assertEqual(result.root, override.resolve())
        self.assertTrue(result.safe_to_migrate)

    def test_returns_structured_resolution_type(self):
        """
        Given any resolution call
        When it returns
        Then the result is a ProjectRootResolution carrying a calibrated, non-empty
            reason string (the render-ready explanation for the skill layer).
        """
        (self.root / ".git").mkdir()

        result = resolve_project_root(self.root)

        self.assertIsInstance(result, ProjectRootResolution)
        self.assertTrue(result.reason)


if __name__ == "__main__":
    unittest.main()
