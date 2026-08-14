"""Unit tests for the migration safety pre-flight (toolguard.tools.migration_gate)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolguard.tools.migration_gate import MigrationPreflight, migration_preflight
from toolguard.tools.project_root import ProjectRootResolution, RootStatus
from toolguard.tools.working_tree import WorkingTreeStatus

_GATE = "toolguard.tools.migration_gate"

_ANCHOR_REASON = "anchor root found at /repo"
_NONE_REASON = "no project marker found"
_AMBIGUOUS_REASON = "two build manifests offer competing roots"


def _resolved_anchor(root: str = "/repo") -> ProjectRootResolution:
    """A RESOLVED_ANCHOR resolution rooted at ``root``."""
    return ProjectRootResolution(
        status=RootStatus.RESOLVED_ANCHOR,
        root=Path(root),
        candidates=(),
        reason=_ANCHOR_REASON,
    )


def _none_resolution() -> ProjectRootResolution:
    """A NONE resolution (no project boundary)."""
    return ProjectRootResolution(
        status=RootStatus.NONE,
        root=None,
        candidates=(),
        reason=_NONE_REASON,
    )


class TestMigrationPreflight(unittest.TestCase):
    """Combination of the project-root and working-tree gates."""

    def test_resolved_root_and_clean_tree_is_safe(self):
        """
        Given a resolved anchor root and a clean working tree
        When migration_preflight runs
        Then it is safe, carries both inputs verbatim, and inspected the resolved root.
        """
        resolution = _resolved_anchor()
        clean = WorkingTreeStatus(is_git_repo=True, is_clean=True, dirty_paths=())
        with mock.patch(
            f"{_GATE}.resolve_project_root", return_value=resolution
        ) as resolve_call:
            with mock.patch(
                f"{_GATE}.working_tree_status", return_value=clean
            ) as tree_call:
                result = migration_preflight(Path("/repo/pkg"))
        self.assertIsInstance(result, MigrationPreflight)
        resolve_call.assert_called_once_with(Path("/repo/pkg"), override=None)
        # The tree that is inspected must be the root that was resolved, not the
        # directory the caller started from.
        tree_call.assert_called_once_with(Path("/repo"))
        self.assertIs(result.root, resolution)
        self.assertIs(result.working_tree, clean)
        self.assertTrue(result.is_safe)
        self.assertEqual(result.blockers, [])

    def test_resolved_root_but_dirty_tree_is_blocked(self):
        """
        Given a resolved anchor root but a dirty working tree
        When migration_preflight runs
        Then it is not safe and the blocker names uncommitted changes and the dirty paths.
        """
        resolution = _resolved_anchor()
        dirty = WorkingTreeStatus(
            is_git_repo=True, is_clean=False, dirty_paths=("src/a.py", "src/b.py")
        )
        with mock.patch(
            f"{_GATE}.resolve_project_root", return_value=resolution
        ) as resolve_call:
            with mock.patch(
                f"{_GATE}.working_tree_status", return_value=dirty
            ) as tree_call:
                result = migration_preflight(Path("/repo"))
        resolve_call.assert_called_once_with(Path("/repo"), override=None)
        tree_call.assert_called_once_with(Path("/repo"))
        self.assertIs(result.working_tree, dirty)
        self.assertFalse(result.is_safe)
        self.assertEqual(len(result.blockers), 1)
        self.assertIn("uncommitted changes", result.blockers[0])
        self.assertIn("src/a.py", result.blockers[0])
        self.assertIn("src/b.py", result.blockers[0])

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
        self.assertEqual(result.blockers, [_NONE_REASON])
        tree_call.assert_not_called()

    def test_ambiguous_root_blocks_with_its_own_reason(self):
        """
        Given an AMBIGUOUS root resolution with competing candidates
        When migration_preflight runs
        Then the blocker is that resolution's reason, distinct from the NONE reason.
        """
        ambiguous = ProjectRootResolution(
            status=RootStatus.AMBIGUOUS,
            root=None,
            candidates=(),
            reason=_AMBIGUOUS_REASON,
        )
        with mock.patch(f"{_GATE}.resolve_project_root", return_value=ambiguous):
            with mock.patch(f"{_GATE}.working_tree_status") as tree_call:
                result = migration_preflight(Path("/repo/pkg"))
        self.assertFalse(result.is_safe)
        self.assertEqual(result.blockers, [_AMBIGUOUS_REASON])
        tree_call.assert_not_called()

    def test_explicit_override_is_passed_through(self):
        """
        Given an explicit project-root override
        When migration_preflight runs
        Then the override reaches resolve_project_root rather than being dropped.
        """
        resolution = _resolved_anchor("/override-root")
        clean = WorkingTreeStatus(is_git_repo=True, is_clean=True, dirty_paths=())
        with mock.patch(
            f"{_GATE}.resolve_project_root", return_value=resolution
        ) as resolve_call:
            with mock.patch(
                f"{_GATE}.working_tree_status", return_value=clean
            ) as tree_call:
                result = migration_preflight(
                    Path("/somewhere/else"), override=Path("/override-root")
                )
        resolve_call.assert_called_once_with(
            Path("/somewhere/else"), override=Path("/override-root")
        )
        tree_call.assert_called_once_with(Path("/override-root"))
        self.assertTrue(result.is_safe)

    def test_omitted_start_dir_is_forwarded_as_none(self):
        """
        Given migration_preflight called with no arguments at all
        When it resolves the root
        Then it forwards None, leaving the cwd default to resolve_project_root.
        """
        resolution = _resolved_anchor()
        clean = WorkingTreeStatus(is_git_repo=True, is_clean=True, dirty_paths=())
        with mock.patch(
            f"{_GATE}.resolve_project_root", return_value=resolution
        ) as resolve_call:
            with mock.patch(f"{_GATE}.working_tree_status", return_value=clean):
                migration_preflight()
        resolve_call.assert_called_once_with(None, override=None)


class TestNonRepositoryRoot(unittest.TestCase):
    """A resolved root that is not a git work tree is unsafe, and says so."""

    def test_non_repo_root_is_blocked_even_when_reported_clean(self):
        """
        Given a resolved root whose working tree reports not-a-repo but is_clean True
        When the blockers are computed
        Then it is blocked for not being a git work tree, not for being dirty.
        """
        # is_clean=True is deliberate: it removes the dirty branch as an alternative
        # route to the blocker, so only the is_git_repo check can produce one.
        not_a_repo = WorkingTreeStatus(is_git_repo=False, is_clean=True, dirty_paths=())
        preflight = MigrationPreflight(root=_resolved_anchor(), working_tree=not_a_repo)
        self.assertFalse(preflight.is_safe)
        self.assertEqual(len(preflight.blockers), 1)
        self.assertIn("not a git work tree", preflight.blockers[0])
        self.assertNotIn("uncommitted", preflight.blockers[0])

    def test_non_repo_root_reports_the_repo_reason_not_the_dirty_reason(self):
        """
        Given the shape working_tree_status really returns for a non-repo
        When the blockers are computed
        Then the message is about version control, not about uncommitted changes.
        """
        not_a_repo = WorkingTreeStatus(
            is_git_repo=False, is_clean=False, dirty_paths=()
        )
        preflight = MigrationPreflight(root=_resolved_anchor(), working_tree=not_a_repo)
        self.assertIn("not a git work tree", preflight.blockers[0])
        self.assertNotIn("uncommitted", preflight.blockers[0])

    def test_absent_working_tree_on_a_resolved_root_fails_closed(self):
        """
        Given a resolved root but no working-tree status at all
        When the blockers are computed
        Then the verdict is unsafe rather than defaulting to safe.
        """
        preflight = MigrationPreflight(root=_resolved_anchor(), working_tree=None)
        self.assertFalse(preflight.is_safe)
        self.assertEqual(len(preflight.blockers), 1)


class TestDirtyPathReporting(unittest.TestCase):
    """The blocker text must name the paths it is refusing over."""

    @staticmethod
    def _dirty(*paths: str) -> MigrationPreflight:
        """A blocked preflight over a resolved root with ``paths`` dirty."""
        return MigrationPreflight(
            root=_resolved_anchor(),
            working_tree=WorkingTreeStatus(
                is_git_repo=True, is_clean=False, dirty_paths=paths
            ),
        )

    def test_up_to_five_dirty_paths_are_all_named(self):
        """
        Given exactly five dirty paths
        When the blocker is rendered
        Then all five are named and no overflow count is appended.
        """
        paths = ("src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py")
        blocker = self._dirty(*paths).blockers[0]
        for path in paths:
            self.assertIn(path, blocker)
        self.assertNotIn("+", blocker)

    def test_beyond_five_dirty_paths_are_truncated_and_counted(self):
        """
        Given seven dirty paths
        When the blocker is rendered
        Then the first five are named, the rest are not, and "+2 more" is appended.
        """
        blocker = self._dirty(
            "src/a.py",
            "src/b.py",
            "src/c.py",
            "src/d.py",
            "src/e.py",
            "src/f.py",
            "src/g.py",
        ).blockers[0]
        for path in ("src/a.py", "src/b.py", "src/c.py", "src/d.py", "src/e.py"):
            self.assertIn(path, blocker)
        self.assertNotIn("src/f.py", blocker)
        self.assertNotIn("src/g.py", blocker)
        self.assertIn("+2 more", blocker)


def _enclosing_git_repo() -> Path | None:
    """Nearest directory at or above this test file holding a ``.git``, or ``None``."""
    for directory in Path(__file__).resolve().parents:
        if (directory / ".git").exists():
            return directory
    return None


class TestUnmockedSmoke(unittest.TestCase):
    """One pass with both collaborators real, so the wiring itself is exercised."""

    def test_a_real_git_repository_is_recognised_end_to_end(self):
        """
        Given this suite's own checkout supplied as an explicit override
        When migration_preflight runs with nothing mocked
        Then a real working-tree status comes back reporting a git repository.
        """
        # Positive control for the non-repo test below: without it, a machine with
        # no git binary would satisfy that test's assertions for the wrong reason.
        repo = _enclosing_git_repo()
        if repo is None:
            self.skipTest("suite is not running from a git checkout")
        result = migration_preflight(override=repo)
        self.assertEqual(result.root.root, repo)
        self.assertTrue(result.working_tree.is_git_repo)

    def test_override_to_a_non_repo_directory_is_blocked_end_to_end(self):
        """
        Given a real empty directory supplied as an explicit override
        When migration_preflight runs with nothing mocked
        Then the root resolves to that directory, a real tree status comes back, and
        it is blocked for not being a git work tree.
        """
        with tempfile.TemporaryDirectory() as tmp:
            result = migration_preflight(override=Path(tmp))
        self.assertEqual(result.root.status, RootStatus.RESOLVED_OVERRIDE)
        self.assertEqual(result.root.root, Path(tmp).resolve())
        self.assertIsNotNone(result.working_tree)
        self.assertFalse(result.working_tree.is_git_repo)
        self.assertFalse(result.is_safe)
        self.assertIn("not a git work tree", result.blockers[0])


if __name__ == "__main__":
    unittest.main()
