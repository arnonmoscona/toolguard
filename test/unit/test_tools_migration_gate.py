"""
Unit tests for the migration safety pre-flight (toolguard.tools.migration_gate).

The two composed primitives (resolve_project_root, working_tree_status) are
patched so the combination logic is exercised in isolation.
"""

import unittest
from pathlib import Path
from unittest import mock

from toolguard.tools.migration_gate import MigrationPreflight, migration_preflight
from toolguard.tools.project_root import ProjectRootResolution, RootStatus
from toolguard.tools.working_tree import WorkingTreeStatus

_GATE = "toolguard.tools.migration_gate"


def _resolved_anchor(root: str = "/repo") -> ProjectRootResolution:
    """A RESOLVED_ANCHOR resolution rooted at ``root``."""
    return ProjectRootResolution(
        status=RootStatus.RESOLVED_ANCHOR,
        root=Path(root),
        candidates=(),
        reason="anchor root found",
    )


def _none_resolution() -> ProjectRootResolution:
    """A NONE resolution (no project boundary)."""
    return ProjectRootResolution(
        status=RootStatus.NONE,
        root=None,
        candidates=(),
        reason="no project marker found",
    )


class TestMigrationPreflight(unittest.TestCase):
    """Combination of the project-root and working-tree gates."""

    def test_resolved_root_and_clean_tree_is_safe(self):
        """
        Given a resolved anchor root and a clean working tree
        When migration_preflight runs
        Then it is safe with no blockers.
        """
        clean = WorkingTreeStatus(is_git_repo=True, is_clean=True, dirty_paths=())
        with mock.patch(f"{_GATE}.resolve_project_root", return_value=_resolved_anchor()):
            with mock.patch(f"{_GATE}.working_tree_status", return_value=clean):
                result = migration_preflight(Path("/repo/pkg"))
        self.assertIsInstance(result, MigrationPreflight)
        self.assertTrue(result.is_safe)
        self.assertEqual(result.blockers, [])

    def test_resolved_root_but_dirty_tree_is_blocked(self):
        """
        Given a resolved anchor root but a dirty working tree
        When migration_preflight runs
        Then it is not safe and the blocker names uncommitted changes.
        """
        dirty = WorkingTreeStatus(
            is_git_repo=True, is_clean=False, dirty_paths=("a.py", "b.py")
        )
        with mock.patch(f"{_GATE}.resolve_project_root", return_value=_resolved_anchor()):
            with mock.patch(f"{_GATE}.working_tree_status", return_value=dirty):
                result = migration_preflight(Path("/repo"))
        self.assertFalse(result.is_safe)
        self.assertEqual(len(result.blockers), 1)
        self.assertIn("uncommitted changes", result.blockers[0])

    def test_unresolved_root_blocks_with_root_reason(self):
        """
        Given no resolvable project boundary
        When migration_preflight runs
        Then the working tree is not inspected and the blocker is the root reason.
        """
        with mock.patch(
            f"{_GATE}.resolve_project_root", return_value=_none_resolution()
        ):
            with mock.patch(f"{_GATE}.working_tree_status") as tree_call:
                result = migration_preflight(Path("/tmp/bare"))
        self.assertFalse(result.is_safe)
        self.assertIsNone(result.working_tree)
        self.assertEqual(result.blockers, ["no project marker found"])
        tree_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
