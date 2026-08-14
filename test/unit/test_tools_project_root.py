"""
Unit tests for :func:`toolguard.tools.project_root.resolve_project_root`, which
classifies the project boundary for the migration safety gate.

Every tree is built inside a throwaway ``HOME``, because the walk-up stops at
``Path.home()``: with the tree outside home the walk runs to ``/`` and whatever
markers the machine happens to have above the temp directory decide the outcome.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolguard.tools.project_root import (
    ProjectRootResolution,
    RootStatus,
    resolve_project_root,
)

#: Independent copies of the production marker sets. Reading the production
#: tuples instead would make these tests unable to fail when one loses a member.
ANCHOR_MARKERS = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")
WEAK_MARKERS = (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
)

_DIR_MARKERS = frozenset({".git", ".hg", ".jj", ".claude"})


def _make_marker(directory: Path, marker: str) -> Path:
    """Create *marker* inside *directory* (creating it too) and return *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    if marker in _DIR_MARKERS:
        (directory / marker).mkdir()
    else:
        (directory / marker).write_text("x\n")
    return directory


class _BoundedWalkTestCase(unittest.TestCase):
    """A throwaway HOME with the project tree inside it, so the walk-up is bounded."""

    def setUp(self):
        """Build ``<tmp>/home/work/repo`` and point HOME at ``<tmp>/home``."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.above_home = Path(tmp.name).resolve()
        self.home = self.above_home / "home"
        self.root = self.home / "work" / "repo"
        self.root.mkdir(parents=True)
        env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        # An inert HOME patch fails nothing here -- it just lets the real
        # filesystem above the temp directory answer instead of the fixture.
        self.assertEqual(Path.home(), self.home)


class TestStartDirectory(_BoundedWalkTestCase):
    """Where the walk begins: the given directory, or the current one."""

    def test_start_dir_is_resolved_before_the_walk(self):
        """
        Given a .git at the repo top and a start directory spelled with '..'
            components that traverse back through it
        When resolve_project_root is called with that unresolved path
        Then the root is the canonical repo top, not the uncanonicalised parent
            spelling that also holds the marker.
        """
        (self.root / ".git").mkdir()
        (self.root / "pkg" / "sub").mkdir(parents=True)
        unresolved = self.root / "pkg" / "sub" / ".." / ".."

        result = resolve_project_root(unresolved)

        self.assertEqual(result.root, self.root)

    def test_omitted_start_dir_walks_up_from_the_current_directory(self):
        """
        Given two independent anchored trees, with the process chdir'd into a
            nested directory of the first
        When resolve_project_root is called with NO start_dir at all, and again
            with the second tree's nested directory passed explicitly
        Then the argument-less call resolves the tree the process is standing
            in, and the explicit call resolves the other one -- the current
            directory is consulted only in the absence of a start_dir.
        """
        here = _make_marker(self.home / "here", ".git")
        elsewhere = _make_marker(self.home / "elsewhere", ".git")
        (here / "pkg").mkdir()
        (elsewhere / "pkg").mkdir()
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(here / "pkg")

        from_cwd = resolve_project_root()
        from_argument = resolve_project_root(elsewhere / "pkg")

        self.assertEqual(from_cwd.root, here)
        self.assertEqual(from_argument.root, elsewhere)


class TestAnchorTier(_BoundedWalkTestCase):
    """Strong anchors resolve a root on their own, nearest first."""

    def test_each_strong_anchor_alone_resolves_the_root(self):
        """
        Given a directory holding exactly one strong anchor marker and nothing
            else, with a nested start directory below it
        When resolve_project_root is called from the nested directory
        Then the status is RESOLVED_ANCHOR, the root is the marker's directory,
            no candidates are offered, and it is safe to migrate -- every anchor
            sits in one tier, so a Claude Code marker is as good as a VCS root.
        """
        for index, marker in enumerate(ANCHOR_MARKERS):
            with self.subTest(marker=marker):
                top = _make_marker(self.root / f"case{index}", marker)
                nested = top / "pkg" / "sub"
                nested.mkdir(parents=True)

                result = resolve_project_root(nested)

                self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
                self.assertEqual(result.root, top)
                self.assertEqual(result.candidates, ())
                self.assertTrue(result.is_resolved)
                self.assertTrue(result.safe_to_migrate)

    def test_anchor_wins_over_a_nearer_build_manifest(self):
        """
        Given a .git at the repo top and a nearer pyproject.toml in a sub-package
        When resolve_project_root is called from inside the sub-package
        Then the farther anchor root is returned with no candidates -- the whole
            anchor tier is climbed before any weaker marker is considered.
        """
        (self.root / ".git").mkdir()
        pkg = _make_marker(self.root / "pkg", "pyproject.toml")

        result = resolve_project_root(pkg)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, self.root)
        self.assertEqual(result.candidates, ())

    def test_nearest_anchor_wins_regardless_of_kind(self):
        """
        Given a .git at the repo top and a NEARER .claude directory in a
            sub-package below it
        When resolve_project_root is called from inside the sub-package
        Then the nearer .claude directory wins over the farther .git root --
            anchors are resolved nearest-first, not VCS-first.
        """
        (self.root / ".git").mkdir()
        pkg = _make_marker(self.root / "pkg", ".claude")

        result = resolve_project_root(pkg)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, pkg)


class TestAmbiguity(_BoundedWalkTestCase):
    """Build manifests without an anchor propose candidates instead of a root."""

    def test_each_build_manifest_alone_is_ambiguous(self):
        """
        Given a directory holding exactly one build manifest and no anchor
            anywhere above it
        When resolve_project_root is called from that directory
        Then the status is AMBIGUOUS, no root is returned, the manifest's
            directory is offered as a non-anchor candidate, and it is NOT safe
            to migrate.
        """
        for index, marker in enumerate(WEAK_MARKERS):
            with self.subTest(marker=marker):
                top = _make_marker(self.root / f"weak{index}", marker)

                result = resolve_project_root(top)

                self.assertEqual(result.status, RootStatus.AMBIGUOUS)
                self.assertIsNone(result.root)
                self.assertFalse(result.is_resolved)
                self.assertFalse(result.safe_to_migrate)
                self.assertEqual(
                    [(c.path, c.marker, c.is_anchor) for c in result.candidates],
                    [(top, marker, False)],
                )

    def test_every_manifest_match_is_offered_nearest_first(self):
        """
        Given an outer directory holding two build manifests and an inner
            directory below it holding a third, with no anchor anywhere
        When resolve_project_root is called from the inner directory
        Then all three matches are offered -- one entry per directory-and-marker
            pair, nearest directory first -- and every one of them is named in
            the reason so the caller can render the whole choice.
        """
        outer = _make_marker(self.root / "outer", "pyproject.toml")
        _make_marker(outer, "package.json")
        inner = _make_marker(outer / "inner", "Cargo.toml")

        result = resolve_project_root(inner)

        self.assertEqual(result.status, RootStatus.AMBIGUOUS)
        self.assertEqual(len(result.candidates), 3)
        self.assertEqual([c.path for c in result.candidates], [inner, outer, outer])
        self.assertEqual(result.candidates[0].marker, "Cargo.toml")
        self.assertEqual(
            {c.marker for c in result.candidates if c.path == outer},
            {"pyproject.toml", "package.json"},
        )
        self.assertFalse(any(c.is_anchor for c in result.candidates))
        self.assertIn(str(inner), result.reason)
        # By marker name, not by path: outer's path is a prefix of inner's, so
        # asserting the paths cannot see a reason that lists one candidate.
        for marker in ("Cargo.toml", "pyproject.toml", "package.json"):
            self.assertIn(marker, result.reason)


class TestNothingFound(_BoundedWalkTestCase):
    """Refusal when the walk finds nothing within its bound."""

    def test_no_marker_refuses(self):
        """
        Given a directory tree with no anchor and no build manifest
        When resolve_project_root is called
        Then the status is NONE, no root and no candidates are returned, it is
            not safe to migrate, and the reason advises putting the project
            under version control.
        """
        bare = self.root / "bare"
        bare.mkdir()

        result = resolve_project_root(bare)

        self.assertEqual(result.status, RootStatus.NONE)
        self.assertIsNone(result.root)
        self.assertEqual(result.candidates, ())
        self.assertFalse(result.safe_to_migrate)
        self.assertIn("version control", result.reason)

    def test_a_marker_above_the_home_directory_is_out_of_reach(self):
        """
        Given a .git directory ABOVE the home directory, and no marker anywhere
            under home
        When resolve_project_root is called from a directory under home
        Then the status is NONE -- the walk stops at home, so a marker outside
            the user's tree cannot silently become the project boundary.
        """
        (self.above_home / ".git").mkdir()

        result = resolve_project_root(self.root)

        self.assertEqual(result.status, RootStatus.NONE)
        self.assertIsNone(result.root)

    def test_strict_mode_with_no_marker_refuses(self):
        """
        Given a directory tree with no marker of any kind
        When resolve_project_root is called with strict=True
        Then the status is NONE with no root and no candidates -- the flat shape
            has no weaker tier to fall back to.
        """
        bare = self.root / "bare"
        bare.mkdir()

        result = resolve_project_root(bare, strict=True)

        self.assertEqual(result.status, RootStatus.NONE)
        self.assertIsNone(result.root)
        self.assertEqual(result.candidates, ())
        self.assertFalse(result.safe_to_migrate)


class TestOverride(_BoundedWalkTestCase):
    """An explicit override short-circuits discovery entirely."""

    def test_override_wins_over_a_discoverable_anchor(self):
        """
        Given an explicit override path AND a different .git root in the tree
        When resolve_project_root is called with the override
        Then the status is RESOLVED_OVERRIDE, the override is the root, no
            candidates are offered, and it is safe to migrate.
        """
        (self.root / ".git").mkdir()
        override = self.root / "chosen"
        override.mkdir()

        result = resolve_project_root(self.root, override=override)

        self.assertEqual(result.status, RootStatus.RESOLVED_OVERRIDE)
        self.assertEqual(result.root, override)
        self.assertEqual(result.candidates, ())
        self.assertTrue(result.is_resolved)
        self.assertTrue(result.safe_to_migrate)

    def test_override_is_canonicalised_before_it_is_returned(self):
        """
        Given an override spelled with a '..' component
        When resolve_project_root is called with it
        Then the returned root is the canonical directory, so a caller can
            compare it against a resolved path.
        """
        chosen = self.root / "chosen"
        chosen.mkdir()

        result = resolve_project_root(
            self.root, override=self.root / "x" / ".." / "chosen"
        )

        self.assertEqual(result.root, chosen)

    def test_override_wins_in_strict_mode_too(self):
        """
        Given an override and a nearer pyproject.toml that strict mode would
            otherwise resolve
        When resolve_project_root is called with strict=True and the override
        Then the override still wins, with status RESOLVED_OVERRIDE.
        """
        start = _make_marker(self.root / "pkg", "pyproject.toml")
        override = self.root / "chosen"
        override.mkdir()

        result = resolve_project_root(start, strict=True, override=override)

        self.assertEqual(result.status, RootStatus.RESOLVED_OVERRIDE)
        self.assertEqual(result.root, override)

    def test_override_is_not_checked_for_existence(self):
        """
        Given an override naming a directory that does not exist
        When resolve_project_root is called with it
        Then it is still returned as the root AND still reported safe to
            migrate: the override is trusted, never validated, so a caller that
            acts on safe_to_migrate acts on a path that may not be there.
        """
        missing = self.root / "no" / "such" / "dir"

        result = resolve_project_root(self.root, override=missing)

        self.assertEqual(result.status, RootStatus.RESOLVED_OVERRIDE)
        self.assertEqual(result.root, missing)
        self.assertTrue(result.safe_to_migrate)


class TestStrictShape(_BoundedWalkTestCase):
    """The flat shape: nearest marker of any kind, all equally trusted."""

    def test_strict_mode_nearest_marker_wins_over_tiered_default(self):
        """
        Given a .git at the repo top and a NEARER pyproject.toml in a sub-package
        When resolve_project_root is called from a directory BELOW the
            sub-package, once with strict=True and once with the tiered default
        Then strict=True climbs to the NEARER pyproject.toml directory while the
            tiered default returns the FARTHER anchor root.
        """
        (self.root / ".git").mkdir()
        pkg = _make_marker(self.root / "pkg", "pyproject.toml")
        start = pkg / "sub"
        start.mkdir()

        strict_result = resolve_project_root(start, strict=True)
        tiered_result = resolve_project_root(start)

        self.assertEqual(strict_result.root, pkg)
        self.assertEqual(tiered_result.root, self.root)

    def test_strict_mode_never_returns_ambiguous(self):
        """
        Given only a weak marker (pyproject.toml) and no anchor anywhere
        When resolve_project_root is called with strict=True
        Then the status is RESOLVED_ANCHOR at that directory rather than
            AMBIGUOUS -- strict mode never asks the caller to disambiguate.
        """
        top = _make_marker(self.root / "pkg", "pyproject.toml")

        result = resolve_project_root(top, strict=True)

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, top)
        self.assertEqual(result.candidates, ())
        self.assertTrue(result.safe_to_migrate)


class TestIndicators(_BoundedWalkTestCase):
    """The caller-supplied marker set replaces the default one."""

    def test_custom_indicators_replace_the_default_set(self):
        """
        Given a .git at the repo top and a caller-chosen marker file in a
            sub-package, with indicators naming only the caller's marker
        When resolve_project_root is called from the sub-package
        Then only the caller's marker is considered: the .git is invisible, and
            the caller's marker -- not being a strong anchor -- yields AMBIGUOUS.
        """
        (self.root / ".git").mkdir()
        pkg = _make_marker(self.root / "pkg", "marker.txt")

        result = resolve_project_root(pkg, indicators=("marker.txt",))

        self.assertEqual(result.status, RootStatus.AMBIGUOUS)
        self.assertIsNone(result.root)
        self.assertEqual([c.path for c in result.candidates], [pkg])

    def test_custom_indicators_are_still_tiered_by_the_anchor_set(self):
        """
        Given a caller-chosen marker in a sub-package and a .claude directory
            above it, with indicators naming both
        When resolve_project_root is called from the sub-package
        Then the farther .claude wins, because membership of the anchor tier is
            decided by the marker's name, not by its position in indicators.
        """
        top = _make_marker(self.root / "top", ".claude")
        pkg = _make_marker(top / "pkg", "marker.txt")

        result = resolve_project_root(pkg, indicators=(".claude", "marker.txt"))

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, top)

    def test_strict_mode_treats_custom_indicators_alike(self):
        """
        Given the same layout -- a caller-chosen marker below a .claude anchor
        When resolve_project_root is called with strict=True
        Then the NEARER caller-chosen marker wins: the flat shape trusts every
            indicator equally.
        """
        top = _make_marker(self.root / "top", ".claude")
        pkg = _make_marker(top / "pkg", "marker.txt")

        result = resolve_project_root(
            pkg, strict=True, indicators=(".claude", "marker.txt")
        )

        self.assertEqual(result.status, RootStatus.RESOLVED_ANCHOR)
        self.assertEqual(result.root, pkg)


class TestResolutionContract(_BoundedWalkTestCase):
    """The invariants a caller may rely on across every status."""

    def test_every_status_is_reachable_and_only_resolved_ones_carry_a_root(self):
        """
        Given one fixture per RootStatus value
        When each is resolved
        Then every declared status is produced by some call, each result is a
            ProjectRootResolution carrying a non-empty reason, RESOLVED_ANCHOR
            and RESOLVED_OVERRIDE carry a root and report safe_to_migrate, and
            AMBIGUOUS and NONE carry root None and refuse -- the invariant the
            migration gate relies on when it inspects root.root before checking
            root.safe_to_migrate.
        """
        anchored = _make_marker(self.root / "anchored", ".git")
        weak = _make_marker(self.root / "weak", "pyproject.toml")
        bare = self.root / "bare"
        bare.mkdir()
        results = [
            resolve_project_root(anchored, override=anchored),
            resolve_project_root(anchored),
            resolve_project_root(weak),
            resolve_project_root(bare),
        ]
        expected = [
            RootStatus.RESOLVED_OVERRIDE,
            RootStatus.RESOLVED_ANCHOR,
            RootStatus.AMBIGUOUS,
            RootStatus.NONE,
        ]

        self.assertEqual([r.status for r in results], expected)
        self.assertEqual({r.status for r in results}, set(RootStatus))
        for result in results:
            with self.subTest(status=result.status):
                self.assertIsInstance(result, ProjectRootResolution)
                self.assertTrue(result.reason)
                self.assertEqual(result.is_resolved, result.root is not None)
                self.assertEqual(result.safe_to_migrate, result.root is not None)


if __name__ == "__main__":
    unittest.main()
