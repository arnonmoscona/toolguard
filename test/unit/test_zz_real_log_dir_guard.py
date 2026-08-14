"""
Regression tests for the guards against writes to the real repo ``logs/``
directory and the real ``~/.toolguard/once_per.db``.

Named ``test_zz_...`` so it sorts last under ``unittest discover``, and so
normally runs after the tests it checks -- a convenience only; the ordering
guarantee is ``test/unit/__init__.py``'s ``atexit`` re-check.
"""

import hashlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import toolguard.error_log as error_log
import toolguard.log_writer as log_writer
from test.unit import _real_log_dir_guard, _real_once_per_home_guard
from toolguard import once_per_store
from toolguard.env_config import get_env_config
from toolguard.once_per_store import ClaimStatus

#: Synthetic project root used by every call below. Never a real path, so a
#: guard that failed to intercept could not silently reuse real state.
_SYNTHETIC_ROOT = "/synthetic"
_SYNTHETIC_LEVELS = ["project: /synthetic/toolguard_hook.toml"]


def _content_signature(path: Path):
    """
    Return ``(exists, size, sha256)`` for *path* -- identical iff untouched.

    Content, not existence and not mtime. Existence misses an append to a file
    that already exists; mtime misses it too when the write lands inside the
    filesystem's timestamp granularity, which is ~50ms here and so covers a
    whole unit test. Measured: four consecutive inserts into one claim store
    left size and mtime_ns unchanged and the digest different every time.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return (False, None, None)
    return (True, len(data), hashlib.sha256(data).hexdigest())


class TestRealLogDirGuardHasNoRecordedLeaks(unittest.TestCase):
    """Asserts nothing in this run attempted to write to the real repo logs/ dir."""

    def test_no_real_log_dir_writes_were_attempted(self):
        """
        Given the TOO-19 real-logs-dir write guard installed for this whole run
        When every test that ran before this one is taken into account
        Then no toolguard log-writing call attempted to resolve the real
            project logs/ directory as its target
        """
        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            events,
            [],
            "One or more tests attempted to write to the real project logs "
            "directory (write suppressed by the guard, but this is a "
            "regression -- see .claude/rules/test-config-isolation.md):\n\n"
            + "\n".join(events),
        )


class TestRealSuppressionHomeGuardHasNoRecordedLeaks(unittest.TestCase):
    """Asserts nothing in this run touched the real ~/.toolguard/once_per.db."""

    def test_no_real_once_per_store_access_was_attempted(self):
        """
        Given the TOO-45 real-once-per-home guard installed for this whole run
        When every test that ran before this one is taken into account
        Then no claim-store call resolved the real ~/.toolguard/once_per.db
            as its target
        """
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            events,
            [],
            "One or more tests attempted to access the real ~/.toolguard/ "
            "claim store (access suppressed by the guard, but this is "
            "a regression -- see .claude/rules/test-config-isolation.md):\n\n"
            + "\n".join(events),
        )


class TestRealLogDirGuardActuallyFires(unittest.TestCase):
    """
    Self-verification: deliberately targets the real logs/ directory and asserts the
    guard records and suppresses the write, restoring the registry afterwards.
    """

    def setUp(self):
        """Start from a clean leak registry regardless of what ran earlier."""
        self._pre_existing = _real_log_dir_guard.get_leak_events()
        _real_log_dir_guard.clear_leak_events()

    def tearDown(self):
        """Restore whatever was already recorded before this test ran."""
        _real_log_dir_guard.replace_leak_events(self._pre_existing)

    def test_guard_records_and_suppresses_a_real_dir_write_attempt(self):
        """
        Given the guard installed and an empty leak registry
        When toolguard.log_writer.log_discovery is called with the REAL repo
            logs/ directory as log_dir (simulating the TOO-19 regression)
        Then the call is recorded as a leak event and the discovery log file
            is NOT created in the real logs/ directory
        """
        discovery_log = (
            _real_log_dir_guard.REAL_LOGS_DIR / log_writer._DISCOVERY_LOG_FILENAME
        )
        before = _content_signature(discovery_log)

        log_writer.log_discovery(
            _SYNTHETIC_LEVELS, _real_log_dir_guard.REAL_LOGS_DIR, _SYNTHETIC_ROOT
        )

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("log_discovery", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])
        self.assertEqual(
            before,
            _content_signature(discovery_log),
            "guard failed to suppress the real-dir write: the discovery log changed",
        )

    def test_guard_fires_for_a_path_beneath_the_real_logs_dir(self):
        """
        Given the guard installed and an empty leak registry
        When log_discovery is called with a SUBDIRECTORY of the REAL repo logs/
            directory, which the guard's docstring claims to cover too
        Then the call is recorded as a leak event and the subdirectory is not
            created -- log_discovery mkdirs its log_dir, so an unguarded call
            would leave it behind
        """
        nested = _real_log_dir_guard.REAL_LOGS_DIR / "synthetic-nested"

        log_writer.log_discovery(_SYNTHETIC_LEVELS, nested, _SYNTHETIC_ROOT)

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn(str(nested), events[0])
        self.assertFalse(
            nested.exists(),
            f"guard failed to suppress a write below the real logs dir: {nested} was created",
        )

    def test_guard_fires_for_every_error_log_entry_point(self):
        """
        Given the guard installed and an empty leak registry
        When log_warning, log_error and log_conflict are each called with the
            REAL repo logs/ directory -- three of the six functions install()
            wraps, each writing its own date-stamped stream
        Then each call is recorded as a leak event and its stream's log file in
            the real logs/ directory is unchanged
        """
        today = datetime.now().strftime("%Y-%m-%d")
        for entry_point, stream in (
            ("log_warning", "warning"),
            ("log_error", "error"),
            ("log_conflict", "conflict"),
        ):
            with self.subTest(entry_point=entry_point):
                _real_log_dir_guard.clear_leak_events()
                stream_log = (
                    _real_log_dir_guard.REAL_LOGS_DIR / f"toolguard-{stream}-{today}.md"
                )
                before = _content_signature(stream_log)

                getattr(error_log, entry_point)(
                    "synthetic message",
                    "synthetic corrective steps",
                    _real_log_dir_guard.REAL_LOGS_DIR,
                )

                events = _real_log_dir_guard.get_leak_events()
                self.assertEqual(
                    len(events), 1, f"expected exactly one leak event, got {events}"
                )
                self.assertIn(entry_point, events[0])
                self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])
                self.assertEqual(
                    before,
                    _content_signature(stream_log),
                    f"guard failed to suppress {entry_point}: {stream_log} changed",
                )

    def test_guard_fires_for_log_command_via_config_log_dir(self):
        """
        Given the guard installed and an empty leak registry
        When toolguard.log_writer.log_command is called with a LogRecord and a
            config dict whose log_dir is the REAL repo logs/ directory -- the
            shape toolguard.hook.main() uses, which pins that the guard's
            inspect.signature-based log_dir/config extraction resolves against
            log_command's signature and not only log_discovery's
        Then the call is recorded as a leak event and no resolution log file
            is created in the real logs/ directory
        """
        resolution_log = (
            _real_log_dir_guard.REAL_LOGS_DIR
            / f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"
        )
        before = _content_signature(resolution_log)

        log_writer.log_command(
            log_writer.LogRecord(command_str="ls -la", status="executed"),
            config={"log_dir": _real_log_dir_guard.REAL_LOGS_DIR},
        )

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("log_command", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])
        self.assertEqual(
            before,
            _content_signature(resolution_log),
            "guard failed to suppress the real-dir write: the resolution log changed",
        )

    def test_guard_fires_for_claim_store_reap_via_logs_dir(self):
        """
        Given the guard installed, an empty leak registry, and
            once_per_store._STORE_PATH isolated to a tmp file (so the
            ~/.toolguard/-facing guard passes through and does not mask this one)
        When toolguard.once_per_store.reap is called with the REAL repo logs/
            directory as logs_dir -- reap is the one claim-store entry point
            that still takes a project logs_dir, so it is guarded here too
        Then the call is recorded as a leak event
        """
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(once_per_store, "_STORE_PATH", Path(tmp) / "once_per.db"):
                once_per_store.reap(_real_log_dir_guard.REAL_LOGS_DIR)

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("reap", events[0])
        self.assertIn(str(_real_log_dir_guard.REAL_LOGS_DIR), events[0])


class TestRealLogDirGuardWatchesThePathProductionWouldWrite(unittest.TestCase):
    """
    Every other test here hands the guard its own ``REAL_LOGS_DIR`` back, so all
    of them pass unchanged if that constant points somewhere harmless. This one
    asks toolguard where it would write instead.
    """

    def setUp(self):
        """Start from a clean leak registry regardless of what ran earlier."""
        self._pre_existing = _real_log_dir_guard.get_leak_events()
        _real_log_dir_guard.clear_leak_events()

    def tearDown(self):
        """Restore whatever was already recorded before this test ran."""
        _real_log_dir_guard.replace_leak_events(self._pre_existing)

    def test_the_log_dir_env_config_resolves_for_this_repo_is_intercepted(self):
        """
        Given toolguard.env_config's own log-directory resolution -- the anchor
            the TOO-19 leak went through -- run against this test file's own
            directory with TOOLGUARD_LOG_DIR blanked, so it resolves this
            repository's default log directory and nothing else
        When log_discovery is called with the directory PRODUCTION named, which
            is obtained without consulting the guard's REAL_LOGS_DIR
        Then the guard intercepts it -- so a REAL_LOGS_DIR pointing at any other
            directory fails here, while every sibling test still passes
        """
        with patch.dict(os.environ, {"TOOLGUARD_LOG_DIR": ""}):
            production_log_dir = get_env_config(Path(__file__).resolve().parent)[
                "log_dir"
            ]

        log_writer.log_discovery(_SYNTHETIC_LEVELS, production_log_dir, _SYNTHETIC_ROOT)

        events = _real_log_dir_guard.get_leak_events()
        self.assertEqual(
            len(events),
            1,
            f"toolguard resolves {production_log_dir} as this repo's log directory, "
            f"but the guard watches {_real_log_dir_guard.REAL_LOGS_DIR}; got {events}",
        )
        self.assertIn("log_discovery", events[0])


class TestRealSuppressionHomeGuardActuallyFires(unittest.TestCase):
    """
    Self-verification: deliberately points _STORE_PATH back at the real
    ~/.toolguard/once_per.db (test/unit/__init__.py otherwise redirects it to a tmp
    file) and asserts the guard intercepts the call; both are restored afterwards.
    """

    def setUp(self):
        """Start from a clean leak registry and force _STORE_PATH to the real path."""
        self._pre_existing = _real_once_per_home_guard.get_leak_events()
        _real_once_per_home_guard.clear_leak_events()
        self._store_patcher = patch.object(
            once_per_store,
            "_STORE_PATH",
            _real_once_per_home_guard.REAL_ONCE_PER_DB,
        )
        self._store_patcher.start()

    def tearDown(self):
        """Restore _STORE_PATH and whatever was already recorded before this test ran."""
        self._store_patcher.stop()
        _real_once_per_home_guard.replace_leak_events(self._pre_existing)

    def test_guard_fires_for_claim_against_the_unpatched_real_store(self):
        """
        Given the guard installed and _STORE_PATH forced to the real, unisolated path
        When toolguard.once_per_store.claim is called with a REAL (non-None) project
            -- claim(None, ...) short-circuits before touching storage, so it would
            pass even with the guard's install() deleted
        Then the call is recorded as a leak event, reports UNGUARANTEED (the
            fail-soft outcome), and the real database is NOT created
        """
        before = _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB)

        result = once_per_store.claim(
            Path("/synthetic/project"),
            "synthetic_kind",
            "synthetic_scope",
            timedelta(days=1),
        )

        self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("claim", events[0])
        self.assertIn(str(_real_once_per_home_guard.REAL_ONCE_PER_DB), events[0])
        self.assertEqual(
            before,
            _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB),
            "guard failed to suppress the real-store write: the db changed",
        )

    def test_guard_fires_for_release_against_the_unpatched_real_store(self):
        """
        Given the guard installed and _STORE_PATH forced to the real, unisolated path
        When toolguard.once_per_store.release is called with a REAL (non-None)
            project -- release opens the store without ever creating it, so the
            recorded event is the only evidence it was intercepted
        Then the call is recorded as a leak event and the real database is untouched
        """
        before = _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB)

        once_per_store.release(
            Path("/synthetic/project"), "synthetic_kind", "synthetic_scope"
        )

        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("release", events[0])
        self.assertEqual(
            before,
            _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB),
            "guard failed to suppress the real-store access: the db changed",
        )

    def test_guard_fires_for_reap_against_the_unpatched_real_store(self):
        """
        Given the guard installed, _STORE_PATH forced to the real, unisolated
            path, and a tmp logs_dir so the sibling real-logs-dir guard passes
            through and does not mask this one
        When toolguard.once_per_store.reap is called -- it is wrapped by BOTH
            guards, and this one wraps the outside
        Then the ~/.toolguard/-facing guard records the leak and the real
            database is untouched
        """
        before = _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB)

        with tempfile.TemporaryDirectory() as tmp:
            once_per_store.reap(Path(tmp))

        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("reap", events[0])
        self.assertEqual(
            before,
            _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB),
            "guard failed to suppress the real-store access: the db changed",
        )

    def test_guard_fires_for_is_claimed_against_the_unpatched_real_store(self):
        """
        Given the guard installed and _STORE_PATH forced to the real, unisolated path
        When toolguard.once_per_store.is_claimed is called with a REAL (non-None)
            project -- is_claimed(None, ...) short-circuits before touching
            storage, so it would pass even with the guard's install() deleted
        Then the call is recorded as a leak event and returns False
        """
        result = once_per_store.is_claimed(
            Path("/synthetic/project"), "synthetic_kind", "synthetic_scope"
        )

        self.assertFalse(result)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("is_claimed", events[0])


class TestRealSuppressionHomeGuardCatchesAForgottenIsolation(unittest.TestCase):
    """
    The case the guard exists for: no _STORE_PATH override at all, so the store
    path comes from production's own resolution rather than from anything a test
    set. Its sibling class forces the override to REAL_ONCE_PER_DB, which hands
    the guard its own constant back and so passes wherever that constant points.
    """

    def setUp(self):
        """Start from a clean leak registry with the store override removed."""
        self._pre_existing = _real_once_per_home_guard.get_leak_events()
        _real_once_per_home_guard.clear_leak_events()
        self._store_patcher = patch.object(once_per_store, "_STORE_PATH", None)
        self._store_patcher.start()

    def tearDown(self):
        """Restore _STORE_PATH and whatever was already recorded before this test ran."""
        self._store_patcher.stop()
        _real_once_per_home_guard.replace_leak_events(self._pre_existing)

    def test_claim_with_no_store_override_at_all_is_intercepted(self):
        """
        Given no _STORE_PATH override -- the state a test that forgot to isolate
            leaves behind, where _resolve_store_path() falls through to the real
            ~/.toolguard/once_per.db
        When claim is called with a real project
        Then the guard intercepts it, reports UNGUARANTEED, and the real
            database is neither created nor modified
        """
        before = _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB)

        result = once_per_store.claim(
            Path("/synthetic/project"),
            "synthetic_kind",
            "synthetic_scope",
            timedelta(days=1),
        )

        self.assertEqual(result.status, ClaimStatus.UNGUARANTEED)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("claim", events[0])
        self.assertEqual(
            before,
            _content_signature(_real_once_per_home_guard.REAL_ONCE_PER_DB),
            "an unisolated claim reached the real store: the db changed",
        )


class TestRealSuppressionHomeGuardAnswersReadsItself(unittest.TestCase):
    """
    That the guard ANSWERS an unisolated read rather than forwarding it cannot
    be observed against the true store, which must never be written and on most
    machines does not exist. This class stands a seeded surrogate in its place.
    """

    def setUp(self):
        """Seed a surrogate store with a matching claim, then declare it 'real'."""
        self._pre_existing = _real_once_per_home_guard.get_leak_events()
        self._tmp = tempfile.TemporaryDirectory()
        self.surrogate = Path(self._tmp.name) / "once_per.db"
        with patch.object(once_per_store, "_STORE_PATH", self.surrogate):
            once_per_store.claim(
                Path("/synthetic/project"),
                "synthetic_kind",
                "synthetic_scope",
                timedelta(days=1),
            )
        self._patchers = [
            patch.object(once_per_store, "_STORE_PATH", self.surrogate),
            patch.object(_real_once_per_home_guard, "REAL_ONCE_PER_DB", self.surrogate),
        ]
        for patcher in self._patchers:
            patcher.start()
        _real_once_per_home_guard.clear_leak_events()

    def tearDown(self):
        """Undo both patches, drop the surrogate, restore the prior registry."""
        for patcher in reversed(self._patchers):
            patcher.stop()
        self._tmp.cleanup()
        _real_once_per_home_guard.replace_leak_events(self._pre_existing)

    def test_is_claimed_is_answered_by_the_guard_and_not_by_the_store(self):
        """
        Given a surrogate store holding a live claim for this project/kind/scope,
            declared to be the real one, so a forwarded read would answer True
            and only a suppressed read answers False
        When is_claimed is called
        Then it returns False and the call is recorded as a leak event
        """
        with patch.object(
            _real_once_per_home_guard,
            "REAL_ONCE_PER_DB",
            Path(self._tmp.name) / "not-the-surrogate.db",
        ):
            self.assertTrue(
                once_per_store.is_claimed(
                    Path("/synthetic/project"), "synthetic_kind", "synthetic_scope"
                ),
                "fixture is inert: the surrogate store does not hold the claim, "
                "so a forwarded read would answer False anyway",
            )

        result = once_per_store.is_claimed(
            Path("/synthetic/project"), "synthetic_kind", "synthetic_scope"
        )

        self.assertFalse(result)
        events = _real_once_per_home_guard.get_leak_events()
        self.assertEqual(
            len(events), 1, f"expected exactly one leak event, got {events}"
        )
        self.assertIn("is_claimed", events[0])


if __name__ == "__main__":
    unittest.main()
