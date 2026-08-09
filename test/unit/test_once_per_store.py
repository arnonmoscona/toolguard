"""
Unit tests for toolguard.once_per_store.

Covers the atomic claim/release/reap primitives, keyed on
(project, kind, scope), that replace the four duplicated date-stamped
marker-file mechanisms (TOO-45 punch-list #01) and live at the shared
~/.toolguard/once_per.db (TOO-45 R2; renamed from suppression.db by TOO-45
punch-list #01's second pass).

Every test isolates once_per_store._STORE_PATH to a tmp file via
patch.object -- the same technique toolguard.tools.decision_ledger's own
tests use for its ~/.toolguard-anchored USER_LEDGER_PATH constant. A
process-wide backstop (test/unit/_real_once_per_home_guard.py) also
intercepts any call that reaches the real store, so a missed isolation
fails loud rather than silently touching the developer's real file.
"""

import sqlite3
import subprocess
import sys
import time
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from toolguard import once_per_store
from toolguard.once_per_store import ClaimStatus

#: test/unit/test_once_per_store.py -> parents[0]=test/unit, [1]=test, [2]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class _IsolatedStoreMixin:
    """Isolate once_per_store._STORE_PATH to a fresh tmp file for each test."""

    def setUp(self):
        """Redirect the shared store to a tmp file for the duration of the test."""
        self._store_tmp = TemporaryDirectory()
        self.addCleanup(self._store_tmp.cleanup)
        patcher = patch.object(
            once_per_store, "_STORE_PATH", Path(self._store_tmp.name) / "once_per.db"
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestDayScope(unittest.TestCase):
    """Test the shared per-day scope string builder."""

    def test_format_for_explicit_date(self):
        """
        Given an explicit date
        When day_scope builds a scope string for it
        Then it is 'day:YYYY-MM-DD' for that date
        """
        result = once_per_store.day_scope(date(2026, 8, 8))

        self.assertEqual(result, "day:2026-08-08")

    def test_defaults_to_today(self):
        """
        Given no date argument
        When day_scope builds a scope string
        Then it uses today's ISO date
        """
        result = once_per_store.day_scope()

        self.assertEqual(result, f"day:{date.today().isoformat()}")


class TestClaim(_IsolatedStoreMixin, unittest.TestCase):
    """Test the atomic claim/release primitives."""

    def test_first_claim_wins_second_is_refused(self):
        """
        Given no prior claim for a (project, kind, scope) triple
        When two calls to claim() race for the same triple
        Then the first reports CLAIMED and the second HELD_BY_SOMEONE_ELSE
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            first = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
            second = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(first.status, ClaimStatus.CLAIMED)
            self.assertEqual(second.status, ClaimStatus.HELD_BY_SOMEONE_ELSE)

    def test_different_scope_claims_independently(self):
        """
        Given a claim already held for one scope
        When claim() is called for a DIFFERENT scope under the same project/kind
        Then the second call also reports CLAIMED -- scopes are independent
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            self.assertEqual(
                once_per_store.claim(
                    project, "k", "day:1", ttl=timedelta(days=1)
                ).status,
                ClaimStatus.CLAIMED,
            )
            self.assertEqual(
                once_per_store.claim(
                    project, "k", "day:2", ttl=timedelta(days=1)
                ).status,
                ClaimStatus.CLAIMED,
            )

    def test_different_kind_claims_independently(self):
        """
        Given a claim already held for one kind
        When claim() is called for a DIFFERENT kind under the same project/scope
        Then the second call also reports CLAIMED -- kinds are independent
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            self.assertEqual(
                once_per_store.claim(
                    project, "kind-a", "s", ttl=timedelta(days=1)
                ).status,
                ClaimStatus.CLAIMED,
            )
            self.assertEqual(
                once_per_store.claim(
                    project, "kind-b", "s", ttl=timedelta(days=1)
                ).status,
                ClaimStatus.CLAIMED,
            )

    def test_different_project_claims_independently(self):
        """
        Given a claim already held for one project
        When claim() is called for a DIFFERENT project under the same kind/scope
        Then the second call also reports CLAIMED -- one project can never
             silence another's claim, since isolation now lives in the key
        """
        with TemporaryDirectory() as tmpdir:
            project_a = Path(tmpdir) / "a"
            project_b = Path(tmpdir) / "b"

            self.assertEqual(
                once_per_store.claim(project_a, "k", "s", ttl=timedelta(days=1)).status,
                ClaimStatus.CLAIMED,
            )
            self.assertEqual(
                once_per_store.claim(project_b, "k", "s", ttl=timedelta(days=1)).status,
                ClaimStatus.CLAIMED,
            )

    def test_expired_claim_can_be_reclaimed(self):
        """
        Given a claim whose ttl has already elapsed (a negative ttl, so
            expires_at is already in the past relative to any subsequent call)
        When claim() is called again for the same (project, kind, scope)
        Then it reports CLAIMED again -- expiry is a timestamp comparison,
             not a permanent lock
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            first = once_per_store.claim(project, "k", "s", ttl=timedelta(seconds=-1))
            second = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(first.status, ClaimStatus.CLAIMED)
            self.assertEqual(second.status, ClaimStatus.CLAIMED)

    def test_release_allows_reclaim(self):
        """
        Given an active claim for (project, kind, scope)
        When release() is called and then claim() is attempted again
        Then the second claim reports CLAIMED -- release() gives the slot back
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
            once_per_store.release(project, "k", "s")

            self.assertEqual(
                once_per_store.claim(project, "k", "s", ttl=timedelta(days=1)).status,
                ClaimStatus.CLAIMED,
            )

    def test_release_of_unknown_claim_is_a_no_op(self):
        """
        Given no claim was ever taken for (project, kind, scope)
        When release() is called anyway
        Then it does not raise
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            once_per_store.release(project, "never-claimed", "s")  # must not raise

    def test_none_project_claim_is_unguaranteed_and_stores_nothing(self):
        """
        Given project=None (no project root could be resolved)
        When claim() is called
        Then it reports UNGUARANTEED every time, with a reason naming the
             unresolved project (TOO-45 punch-list #01, item 1: this is the
             exact defect being fixed -- project=None must never be
             indistinguishable from a genuinely held claim), and creates
             nothing
        """
        first = once_per_store.claim(None, "k", "s", ttl=timedelta(days=1))
        second = once_per_store.claim(None, "k", "s", ttl=timedelta(days=1))

        self.assertEqual(first.status, ClaimStatus.UNGUARANTEED)
        self.assertEqual(second.status, ClaimStatus.UNGUARANTEED)
        self.assertIn("project", first.reason)
        self.assertFalse(once_per_store._STORE_PATH.exists())

    def test_claim_fails_soft_on_unwritable_store_parent(self):
        """
        Given a store path whose parent cannot be created (a plain file
            already occupies that path, so mkdir() raises FileExistsError)
        When claim() is called twice for the same (project, kind, scope)
        Then both calls report UNGUARANTEED -- proving no real claim was
             ever stored (a genuine successful claim would make the second
             call HELD_BY_SOMEONE_ELSE, not UNGUARANTEED)
        """
        with TemporaryDirectory() as tmpdir:
            blocked_parent = Path(tmpdir) / "not_a_directory"
            blocked_parent.write_text("occupied")
            with patch.object(
                once_per_store, "_STORE_PATH", blocked_parent / "once_per.db"
            ):
                with TemporaryDirectory() as project_dir:
                    project = Path(project_dir)
                    first = once_per_store.claim(
                        project, "k", "s", ttl=timedelta(days=1)
                    )
                    second = once_per_store.claim(
                        project, "k", "s", ttl=timedelta(days=1)
                    )

            self.assertEqual(first.status, ClaimStatus.UNGUARANTEED)
            self.assertEqual(second.status, ClaimStatus.UNGUARANTEED)

    def test_release_fails_soft_on_unreadable_store(self):
        """
        Given a store path that is itself a directory (so sqlite3.connect()
            on it raises) -- a plain file at the PARENT path is not enough
            to exercise release(), since it returns before touching storage
            once Path.exists() is False for that parent-blocked child path
        When release() is called
        Then it does not raise
        """
        with TemporaryDirectory() as tmpdir:
            blocked_store = Path(tmpdir) / "once_per.db"
            blocked_store.mkdir()
            with patch.object(once_per_store, "_STORE_PATH", blocked_store):
                with TemporaryDirectory() as project_dir:
                    once_per_store.release(
                        Path(project_dir), "k", "s"
                    )  # must not raise

    def test_reap_fails_soft_on_unwritable_logs_dir(self):
        """
        Given a logs_dir path that cannot be created
        When reap() is called
        Then it does not raise
        """
        with TemporaryDirectory() as tmpdir:
            blocked_path = Path(tmpdir) / "not_a_directory"
            blocked_path.write_text("occupied")

            once_per_store.reap(blocked_path)  # must not raise

    def test_concurrent_claim_from_two_processes_only_one_wins(self):
        """
        Given two separate OS processes racing to claim() the same
            (project, kind, scope) against the same shared store, synchronized
            via a barrier file so both attempt the claim at nearly the same
            instant
        When both processes run concurrently
        Then exactly one observes CLAIMED and the other observes
            HELD_BY_SOMEONE_ELSE -- the TOCTOU race the old check-then-create
            marker-file pattern had is closed
        """
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            project = Path(tmpdir) / "project"
            barrier = Path(tmpdir) / "go"

            script = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from datetime import timedelta\n"
                "from toolguard import once_per_store\n"
                "from toolguard.once_per_store import ClaimStatus\n"
                "once_per_store._STORE_PATH = Path(sys.argv[1])\n"
                "barrier = Path(sys.argv[3])\n"
                "deadline = time.monotonic() + 10\n"
                "while not barrier.exists() and time.monotonic() < deadline:\n"
                "    pass\n"
                "result = once_per_store.claim(Path(sys.argv[2]), 'race_kind', 'race_scope', timedelta(days=1))\n"
                "print(1 if result.status is ClaimStatus.CLAIMED else 0)\n"
            )

            procs = [
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(store_path),
                        str(project),
                        str(barrier),
                    ],
                    cwd=str(_REPO_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]

            # Give both children time to reach the busy-wait loop, then release them together.
            time.sleep(0.3)
            barrier.touch()

            outputs = []
            for proc in procs:
                stdout, stderr = proc.communicate(timeout=15)
                self.assertEqual(proc.returncode, 0, msg=stderr)
                outputs.append(stdout.strip())

            self.assertEqual(sorted(outputs), ["0", "1"])


class TestIsClaimed(_IsolatedStoreMixin, unittest.TestCase):
    """Test the read-only is_claimed pre-check (TOO-45 follow-up)."""

    def test_missing_store_returns_false_and_creates_nothing(self):
        """
        Given a store path that does not exist
        When is_claimed is called
        Then it returns False, and the store still does not exist afterward
             -- a read must never create storage
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            result = once_per_store.is_claimed(project, "k", "s")

            self.assertFalse(result)
            self.assertFalse(once_per_store._STORE_PATH.exists())

    def test_true_right_after_a_live_claim(self):
        """
        Given a fresh claim just taken for (project, kind, scope)
        When is_claimed checks the same triple
        Then it returns True
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertTrue(once_per_store.is_claimed(project, "k", "s"))

    def test_false_for_an_expired_claim(self):
        """
        Given a claim whose ttl has already elapsed
        When is_claimed checks it
        Then it returns False -- an expired claim is not a live claim
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(seconds=-1))

            self.assertFalse(once_per_store.is_claimed(project, "k", "s"))

    def test_false_for_a_different_kind_scope_or_project(self):
        """
        Given a live claim for one (project, kind, scope)
        When is_claimed checks a different kind, a different scope, or a
             different project
        Then all three return False -- projects, kinds, and scopes are all
             independent
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "proj"
            other_project = Path(tmpdir) / "other-proj"
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertFalse(once_per_store.is_claimed(project, "other-kind", "s"))
            self.assertFalse(once_per_store.is_claimed(project, "k", "other-scope"))
            self.assertFalse(once_per_store.is_claimed(other_project, "k", "s"))

    def test_false_after_release(self):
        """
        Given a live claim that is then released
        When is_claimed checks it afterward
        Then it returns False
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
            once_per_store.release(project, "k", "s")

            self.assertFalse(once_per_store.is_claimed(project, "k", "s"))

    def test_false_for_none_project_and_creates_nothing(self):
        """
        Given project=None (no project root could be resolved)
        When is_claimed is called
        Then it returns False without touching the store
        """
        result = once_per_store.is_claimed(None, "k", "s")

        self.assertFalse(result)
        self.assertFalse(once_per_store._STORE_PATH.exists())

    def test_fails_soft_on_unreadable_store(self):
        """
        Given a store path that cannot be opened (a directory already
            occupies that exact path)
        When is_claimed is called
        Then it returns False rather than raising
        """
        with TemporaryDirectory() as tmpdir:
            blocked_store = Path(tmpdir) / "once_per.db"
            blocked_store.mkdir()
            with patch.object(once_per_store, "_STORE_PATH", blocked_store):
                with TemporaryDirectory() as project_dir:
                    result = once_per_store.is_claimed(Path(project_dir), "k", "s")

            self.assertFalse(result)


class TestSqlite3Unavailable(_IsolatedStoreMixin, unittest.TestCase):
    """
    Regression guard (TOO-45 follow-up, extended R2): an interpreter without
    the optional _sqlite3 extension must not make this module -- and
    therefore the hook that imports it transitively -- unimportable, and
    every function must degrade safely rather than raise. Every claim()
    caller sees this as ClaimStatus.UNGUARANTEED (never silently as a claim
    won or held) -- see each dependent module's own warning
    (test_once_per.py, test_auto_migrate.py, test_config_divergence.py).
    """

    def test_claim_reports_unguaranteed_and_touches_nothing(self):
        """
        Given sqlite3 is unavailable
        When claim is called
        Then it reports UNGUARANTEED without creating the store
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            with patch.object(once_per_store, "sqlite3", None):
                result = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
            self.assertFalse(once_per_store._STORE_PATH.exists())

    def test_is_claimed_degrades_to_always_false_and_touches_nothing(self):
        """
        Given sqlite3 is unavailable
        When is_claimed is called
        Then it returns False without creating the store
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            with patch.object(once_per_store, "sqlite3", None):
                result = once_per_store.is_claimed(project, "k", "s")

            self.assertFalse(result)
            self.assertFalse(once_per_store._STORE_PATH.exists())

    def test_release_and_reap_are_no_ops(self):
        """
        Given sqlite3 is unavailable
        When release and reap are called
        Then neither raises
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            with patch.object(once_per_store, "sqlite3", None):
                once_per_store.release(project, "k", "s")  # must not raise
                once_per_store.reap(project)  # must not raise

    def test_claim_never_actually_throttles_without_sqlite(self):
        """
        Given sqlite3 is unavailable
        When claim() is called twice for the same (project, kind, scope)
        Then BOTH calls report UNGUARANTEED -- throttling itself is
             unavailable, not merely silent (the real behavioural
             consequence callers must warn about)
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            with patch.object(once_per_store, "sqlite3", None):
                first = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
                second = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(first.status, ClaimStatus.UNGUARANTEED)
            self.assertEqual(second.status, ClaimStatus.UNGUARANTEED)


class TestReap(_IsolatedStoreMixin, unittest.TestCase):
    """Test expired-claim, legacy-marker-file, and legacy-db cleanup."""

    def test_reap_deletes_expired_claims(self):
        """
        Given a claim whose ttl has already elapsed
        When reap() runs
        Then the underlying database row is gone (a fresh claim() attempt
             thereafter is indistinguishable from one that was never taken)
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(seconds=-1))

            once_per_store.reap(project)

            conn = sqlite3.connect(str(once_per_store._STORE_PATH))
            try:
                with conn:
                    rows = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(rows, 0)

    def test_reap_expiry_sweep_is_global_and_independent_of_logs_dir(self):
        """
        Given expired claims for two DIFFERENT projects
        When reap() runs with a logs_dir that names NEITHER claimed project
             (and doesn't even exist) -- unlike passing one of the two
             claimed projects, this can't coincidentally look like a
             per-project-scoped sweep instead of a genuinely global one
        Then both projects' expired rows are still gone
        """
        with TemporaryDirectory() as tmpdir:
            project_a = Path(tmpdir) / "a"
            project_b = Path(tmpdir) / "b"
            unrelated_logs_dir = Path(tmpdir) / "unrelated-logs-dir"
            once_per_store.claim(project_a, "k", "s", ttl=timedelta(seconds=-1))
            once_per_store.claim(project_b, "k", "s", ttl=timedelta(seconds=-1))

            once_per_store.reap(unrelated_logs_dir)

            conn = sqlite3.connect(str(once_per_store._STORE_PATH))
            try:
                with conn:
                    rows = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(rows, 0)

    def test_reap_keeps_live_claims(self):
        """
        Given a claim that has not yet expired
        When reap() runs
        Then the row survives and a repeat claim() attempt still reports
             HELD_BY_SOMEONE_ELSE
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            once_per_store.reap(project)

            self.assertEqual(
                once_per_store.claim(project, "k", "s", ttl=timedelta(days=1)).status,
                ClaimStatus.HELD_BY_SOMEONE_ELSE,
            )

    def test_reap_sweeps_legacy_marker_files(self):
        """
        Given leftover legacy marker files from the pre-once_per_store-store
            code (all three old prefixes), including one with a malformed date
        When reap() runs
        Then every legacy marker file is removed, unconditionally -- no date
             parsing is involved, they are swept purely by filename prefix
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            legacy_files = [
                logs_dir / ".toolguard-warned-2020-01-01",
                logs_dir / ".toolguard-migration-2020-01-01",
                logs_dir / ".toolguard-divergence-warned-2020-01-01",
                logs_dir / ".toolguard-warned-invalid-date",
            ]
            for f in legacy_files:
                f.touch()

            once_per_store.reap(logs_dir)

            for f in legacy_files:
                self.assertFalse(f.exists(), f"{f} should have been swept")

    def test_reap_removes_stale_legacy_per_project_db(self):
        """
        Given a stale .toolguard-suppression.db left under logs_dir from the
            pre-R2 per-project storage format
        When reap() runs
        Then the stale file is removed -- it is a format nothing writes
             anymore, exactly like the marker-file prefixes
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            legacy_db = logs_dir / ".toolguard-suppression.db"
            legacy_db.write_text("stale sqlite file")

            once_per_store.reap(logs_dir)

            self.assertFalse(legacy_db.exists())

    def test_reap_removes_stale_legacy_shared_store_sibling(self):
        """
        Given a stale suppression.db sibling of the current store path --
            this store's OWN previous filename, before TOO-45 punch-list #01
            retired the "suppression" language
        When reap() runs
        Then the stale sibling file is removed
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir) / "project"
            legacy_sibling = once_per_store._STORE_PATH.parent / "suppression.db"
            legacy_sibling.parent.mkdir(parents=True, exist_ok=True)
            legacy_sibling.write_text("stale sqlite file")

            once_per_store.reap(project / "logs")

            self.assertFalse(legacy_sibling.exists())

    def test_reap_leaves_unrelated_files_alone(self):
        """
        Given files in logs_dir that do NOT match any legacy marker prefix
            or the legacy db filename
        When reap() runs
        Then those files are left untouched
        """
        with TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            unrelated = logs_dir / "toolguard-2026-08-08.md"
            unrelated.write_text("resolution log entry")

            once_per_store.reap(logs_dir)

            self.assertTrue(unrelated.exists())

    def test_reap_on_missing_logs_dir_does_not_raise(self):
        """
        Given a logs_dir that does not exist
        When reap() runs
        Then it completes without raising
        """
        logs_dir = Path("/nonexistent/toolguard-test-dir")

        once_per_store.reap(logs_dir)  # must not raise


class TestResolveStorePath(unittest.TestCase):
    """TOO-45 D1: the store path is resolved lazily, per call, never at import."""

    def test_override_takes_precedence_and_never_calls_home(self):
        """
        Given a test-patched _STORE_PATH override
        When _resolve_store_path is called
        Then it returns the override without calling Path.home() at all
        """
        override = Path("/tmp/synthetic-once-per.db")
        with patch.object(once_per_store, "_STORE_PATH", override):
            with patch.object(
                Path, "home", side_effect=AssertionError("must not be called")
            ):
                result = once_per_store._resolve_store_path()

        self.assertEqual(result, override)

    def test_returns_none_when_home_is_unresolvable(self):
        """
        Given no _STORE_PATH override and Path.home() raising RuntimeError
            (no HOME and no passwd entry for the uid -- an ordinary
            container/CI shape)
        When _resolve_store_path is called
        Then it returns None rather than raising
        """
        with patch.object(once_per_store, "_STORE_PATH", None):
            with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
                result = once_per_store._resolve_store_path()

        self.assertIsNone(result)


class TestHomeUnresolvable(unittest.TestCase):
    """
    TOO-45 D1: an interpreter with no resolvable $HOME must not make the
    hook unimportable, and every store-touching function must still degrade
    fail-soft rather than raise. once_per_store._STORE_PATH is deliberately
    left at its real default (None, no override) here -- the whole point is
    to exercise the module-default resolution path with Path.home() itself
    forced to fail, not to isolate around it.
    """

    def test_claim_fails_soft_when_home_is_unresolvable(self):
        """
        Given _STORE_PATH has no override and Path.home() raises RuntimeError
        When claim() is called twice for the same (project, kind, scope)
        Then both calls report UNGUARANTEED -- proving no real claim was
             ever stored, not merely that success and fail-soft happen to
             look alike
        """
        with patch.object(once_per_store, "_STORE_PATH", None):
            with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
                first = once_per_store.claim(
                    Path("/synthetic/project"), "k", "s", ttl=timedelta(days=1)
                )
                second = once_per_store.claim(
                    Path("/synthetic/project"), "k", "s", ttl=timedelta(days=1)
                )

        self.assertEqual(first.status, ClaimStatus.UNGUARANTEED)
        self.assertEqual(second.status, ClaimStatus.UNGUARANTEED)

    def test_is_claimed_fails_soft_when_home_is_unresolvable(self):
        """
        Given _STORE_PATH has no override and Path.home() raises RuntimeError
        When claim() reports UNGUARANTEED (fail-soft) and is_claimed() then
             checks the same (project, kind, scope)
        Then is_claimed() returns False -- proving claim()'s report never
             became a real stored claim, rather than is_claimed() simply
             returning its own fail-soft value for an unrelated reason
        """
        with patch.object(once_per_store, "_STORE_PATH", None):
            with patch.object(Path, "home", side_effect=RuntimeError("no HOME")):
                claimed = once_per_store.claim(
                    Path("/synthetic/project"), "k", "s", ttl=timedelta(days=1)
                )
                result = once_per_store.is_claimed(Path("/synthetic/project"), "k", "s")

        self.assertEqual(claimed.status, ClaimStatus.UNGUARANTEED)
        self.assertFalse(result)


class TestIsClaimedMalformedTimestamp(_IsolatedStoreMixin, unittest.TestCase):
    """TOO-45 D2: a malformed stored timestamp must never raise into the caller."""

    def test_non_iso_expires_at_is_treated_as_expired(self):
        """
        Given a claim row whose expires_at was overwritten with a value
            datetime.fromisoformat cannot parse (a hand edit, or a
            different toolguard build sharing this file with a mismatched
            schema) -- planted directly via SQL, bypassing claim(), whose
            own comparison happens in SQL and never parses the value
        When is_claimed() reads that row
        Then it returns False (treated as expired) rather than raising
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            conn = sqlite3.connect(str(once_per_store._STORE_PATH))
            try:
                with conn:
                    conn.execute(
                        "UPDATE claims SET expires_at = ? "
                        "WHERE project = ? AND kind = ? AND scope = ?",
                        ("not-a-timestamp", str(project), "k", "s"),
                    )
            finally:
                conn.close()

            result = once_per_store.is_claimed(project, "k", "s")  # must not raise

            self.assertFalse(result)

    def test_non_string_expires_at_is_treated_as_expired(self):
        """
        Given a claim row whose expires_at is an INTEGER (SQLite's TEXT
            column affinity doesn't enforce string storage, so this is a
            genuine TypeError source for datetime.fromisoformat, distinct
            from the malformed-string ValueError case above)
        When is_claimed() reads that row
        Then it returns False rather than raising
        """
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            conn = sqlite3.connect(str(once_per_store._STORE_PATH))
            try:
                with conn:
                    conn.execute(
                        "UPDATE claims SET expires_at = 12345 "
                        "WHERE project = ? AND kind = ? AND scope = ?",
                        (str(project), "k", "s"),
                    )
            finally:
                conn.close()

            result = once_per_store.is_claimed(project, "k", "s")  # must not raise

            self.assertFalse(result)


class TestSchemaVersioning(unittest.TestCase):
    """
    TOO-45 D3: a claims table left over from a different schema shape must
    self-heal via PRAGMA user_version, not silently and permanently disable
    throttling.
    """

    def test_stale_schema_is_recreated_and_throttling_still_works(self):
        """
        Given a claims table already on disk with a DIFFERENT shape (no
            user_version ever set, so it defaults to 0, and columns claim()'s
            INSERT can't satisfy)
        When claim() is called twice for the same (project, kind, scope)
        Then the first call detects the version mismatch, drops and
             recreates the table, and reports CLAIMED; the second call is
             correctly HELD_BY_SOMEONE_ELSE -- proving throttling survives
             the stale schema instead of both calls silently reporting
             CLAIMED forever (the reviewer's reproduced defect)
        """
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            conn = sqlite3.connect(str(store_path))
            try:
                with conn:
                    conn.execute("CREATE TABLE claims (old_column TEXT)")
                    conn.execute("INSERT INTO claims (old_column) VALUES ('stale row')")
            finally:
                conn.close()

            project = Path(tmpdir) / "project"
            with patch.object(once_per_store, "_STORE_PATH", store_path):
                first = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
                second = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(first.status, ClaimStatus.CLAIMED)
            self.assertEqual(second.status, ClaimStatus.HELD_BY_SOMEONE_ELSE)


class TestSchemaVersionNewerThanOurs(unittest.TestCase):
    """
    A store's PRAGMA user_version may be HIGHER than this build's
    _SCHEMA_VERSION (an older build reads a newer build's store) -- that
    must never be treated as a mismatch to repair by dropping the table.
    """

    def test_higher_version_store_is_not_destroyed(self):
        """
        Given a store whose PRAGMA user_version is one HIGHER than this
            build's _SCHEMA_VERSION, already holding a live row
        When claim() is called against the same (project, kind, scope)
        Then it reports UNGUARANTEED and the existing row and version header
             are left exactly as they were -- not dropped and recreated
        """
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            project = Path(tmpdir) / "project"
            newer_version = once_per_store._SCHEMA_VERSION + 1
            conn = sqlite3.connect(str(store_path))
            try:
                with conn:
                    conn.execute(
                        f"CREATE TABLE claims ({once_per_store._CLAIMS_TABLE_COLUMNS})"
                    )
                    conn.execute(
                        "INSERT INTO claims VALUES (?, 'k', 's', ?, ?)",
                        (str(project), "2099-01-01T00:00:00", "2099-01-01T00:00:00"),
                    )
                    conn.execute(f"PRAGMA user_version = {newer_version}")
            finally:
                conn.close()

            with patch.object(once_per_store, "_STORE_PATH", store_path):
                result = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            conn = sqlite3.connect(str(store_path))
            try:
                with conn:
                    version_after = conn.execute("PRAGMA user_version").fetchone()[0]
                    rows_after = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[
                        0
                    ]
            finally:
                conn.close()

            self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
            self.assertEqual(version_after, newer_version)
            self.assertEqual(rows_after, 1)


class TestSchemaVersionMatchesButTableMissing(unittest.TestCase):
    """
    A store's version header can match ours while the claims table itself
    is gone (e.g. an external DROP TABLE) -- the version check alone must
    not skip past that without confirming the table actually exists.
    """

    def test_missing_table_at_matching_version_is_recreated_and_throttles(self):
        """
        Given a store whose PRAGMA user_version already equals
            _SCHEMA_VERSION but has no claims table at all
        When claim() is called twice for the same (project, kind, scope)
        Then the first call heals the table and reports CLAIMED; the second
             is correctly HELD_BY_SOMEONE_ELSE -- proving throttling resumes
             instead of staying silently off forever
        """
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            project = Path(tmpdir) / "project"
            conn = sqlite3.connect(str(store_path))
            try:
                with conn:
                    conn.execute(
                        f"PRAGMA user_version = {once_per_store._SCHEMA_VERSION}"
                    )
            finally:
                conn.close()

            with patch.object(once_per_store, "_STORE_PATH", store_path):
                first = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
                second = once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))

            self.assertEqual(first.status, ClaimStatus.CLAIMED)
            self.assertEqual(second.status, ClaimStatus.HELD_BY_SOMEONE_ELSE)


class TestConnectionNotLeakedOnSchemaFailure(unittest.TestCase):
    """
    TOO-45 D5: a schema-repair failure inside claim()'s transaction must not
    leak the connection. _connect() itself only opens the connection and
    assigns it to the CALLER's variable before anything that can raise --
    claim() manages the transaction (BEGIN IMMEDIATE / commit) itself, so
    this exercises the whole claim() call rather than calling _connect() in
    isolation. sqlite3.Connection is an immutable C type and can't be
    patched directly, so sqlite3.connect() itself is mocked to hand back a
    plain double whose .close() call is what's being verified.
    """

    def test_claim_closes_connection_when_ensure_schema_raises(self):
        """
        Given sqlite3.connect() succeeds but _ensure_schema() then raises
        When claim() is called
        Then it reports UNGUARANTEED (fail-soft) AND the connection is
             closed exactly once -- not left dangling for the caller's
             already-set `conn` variable to miss in its `finally` block
        """
        fake_conn = MagicMock()
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            project = Path(tmpdir) / "project"
            with patch.object(once_per_store, "_STORE_PATH", store_path):
                with patch.object(
                    once_per_store.sqlite3, "connect", return_value=fake_conn
                ):
                    with patch.object(
                        once_per_store,
                        "_ensure_schema",
                        side_effect=sqlite3.OperationalError("boom"),
                    ):
                        result = once_per_store.claim(
                            project, "k", "s", ttl=timedelta(days=1)
                        )

        self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
        fake_conn.close.assert_called_once()


class TestConnectExistingDoesNotCreateOnRace(unittest.TestCase):
    """TOO-45 D6: _connect_existing() must never create the store file it just checked for."""

    def test_file_removed_between_exists_check_and_connect_creates_nothing(self):
        """
        Given a store file that exists at the moment _connect_existing()
            checks for it, but is deleted immediately afterward (simulating
            a concurrent delete between the check and the connect)
        When is_claimed() runs through that race
        Then it returns False rather than creating a fresh, table-less file
             in the deleted one's place -- the mode=rw URI connect raises
             instead of silently creating
        """
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "once_per.db"
            store_path.touch()
            project = Path(tmpdir) / "project"

            real_exists = Path.exists

            def exists_then_delete(path_self):
                found = real_exists(path_self)
                if found and path_self == store_path:
                    store_path.unlink()
                return found

            with patch.object(once_per_store, "_STORE_PATH", store_path):
                with patch.object(Path, "exists", exists_then_delete):
                    result = once_per_store.is_claimed(project, "k", "s")

            self.assertFalse(result)
            self.assertFalse(store_path.exists())


class TestConnectExistingHandlesUriReservedChars(
    _IsolatedStoreMixin, unittest.TestCase
):
    """
    _connect_existing() builds a ``file:`` URI from the store path -- a raw
    ``?`` or ``%`` in the path must not be misread as the query delimiter or
    a percent-escape, which would silently drop ``mode=rw`` and open (or
    create) the wrong file.
    """

    def test_question_mark_and_percent_in_path_still_open_the_right_file(self):
        """
        Given a store path whose directory name contains both '?' and '%'
        When a live claim is taken and then read back via is_claimed()
            (is_claimed always goes through _connect_existing())
        Then it reads the real claim correctly, and no stray file is
             created anywhere alongside the intended one
        """
        with TemporaryDirectory() as tmpdir:
            odd_dir = Path(tmpdir) / "q?dir%25"
            odd_dir.mkdir()
            store_path = odd_dir / "once_per.db"
            project = Path(tmpdir) / "project"

            with patch.object(once_per_store, "_STORE_PATH", store_path):
                once_per_store.claim(project, "k", "s", ttl=timedelta(days=1))
                result = once_per_store.is_claimed(project, "k", "s")

            self.assertTrue(result)
            self.assertEqual(sorted(p.name for p in odd_dir.iterdir()), ["once_per.db"])
            self.assertEqual(
                sorted(p.name for p in Path(tmpdir).iterdir()), [odd_dir.name]
            )


if __name__ == "__main__":
    unittest.main()
