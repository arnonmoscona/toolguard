"""
Unit tests for toolguard.once_per: the once-per-period facade
(``day`` / ``OncePer`` / ``Repeat``).
"""

import sqlite3
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from test.unit import _real_once_per_home_guard
from toolguard import once_per, once_per_store
from toolguard.once_per_store import ClaimStatus


def _period_with_retention(retention):
    """A test period with a single fixed scope, so *retention* is the only variable."""
    return once_per._Period("test-period", lambda context: "one-scope", retention)


def _notices(mock_print, message):
    """Everything printed that is not the caller's own *message* -- i.e. the degraded notice."""
    printed = [call.args[0] for call in mock_print.call_args_list if call.args]
    return [line for line in printed if line != message]


def _streams(mock_print):
    """The set of ``file=`` streams every captured print() call was routed to."""
    return {call.kwargs.get("file") for call in mock_print.call_args_list}


class _IsolatedStoreMixin:
    """Isolate once_per_store._STORE_PATH to a fresh tmp file for each test."""

    def setUp(self):
        """Redirect the shared store to a tmp file and prove the redirect took effect."""
        self._store_tmp = TemporaryDirectory()
        self.addCleanup(self._store_tmp.cleanup)
        self.store_path = Path(self._store_tmp.name) / "once_per.db"
        patcher = patch.object(once_per_store, "_STORE_PATH", self.store_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        # test/unit/__init__.py already redirects the default process-wide, so an
        # inert patch here would look identical to a working one.
        self.assertEqual(once_per_store._resolve_store_path(), self.store_path)
        self.assertNotEqual(self.store_path, _real_once_per_home_guard.REAL_ONCE_PER_DB)

    def claim_kinds(self):
        """Every ``kind`` currently stored, read straight out of the claims table."""
        conn = sqlite3.connect(str(self.store_path))
        try:
            return sorted(row[0] for row in conn.execute("SELECT kind FROM claims"))
        finally:
            conn.close()


class TestOncePerDone(_IsolatedStoreMixin, unittest.TestCase):
    """Test the read-only pre-check."""

    def test_false_before_anything_claimed(self):
        """
        Given no prior activity for (project, key)
        When done() checks it
        Then it returns False
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            self.assertFalse(thing.done(project))

    def test_true_after_a_successful_warn(self):
        """
        Given warn() has already printed once today for this thing
        When done() checks the same project
        Then it returns True -- done() and warn() address the same claim
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.warn(project, "message")

            self.assertTrue(thing.done(project))

    def test_false_for_a_stored_claim_whose_ttl_has_elapsed(self):
        """
        Given a stored claim for this thing whose ttl has already elapsed
        When done() checks it
        Then it returns False -- the row is present, so only expiry can
             produce this answer
        """
        thing = _period_with_retention(timedelta(days=7))("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "k", "one-scope", ttl=timedelta(seconds=-1))
            self.assertIn("k", self.claim_kinds())

            self.assertFalse(thing.done(project))


class TestOncePerWarn(_IsolatedStoreMixin, unittest.TestCase):
    """Test the fail-open warning primitive."""

    def test_prints_and_returns_true_the_first_time(self):
        """
        Given no prior warning for this thing
        When warn() is called
        Then it prints the message on stderr and returns True
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                result = thing.warn(project, "hello")

            self.assertTrue(result)
            mock_print.assert_called_once()
            self.assertEqual(mock_print.call_args.args[0], "hello")
            # stdout is the hook's decision channel; a warning must never land there.
            self.assertEqual(_streams(mock_print), {sys.stderr})

    def test_second_call_same_day_is_silent_and_returns_false(self):
        """
        Given warn() already printed today for this thing/project
        When warn() is called again the same day
        Then nothing is printed and it returns False
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.warn(project, "hello")

            with patch("builtins.print") as mock_print:
                result = thing.warn(project, "hello again")

            self.assertFalse(result)
            mock_print.assert_not_called()

    def test_always_prints_when_throttling_unavailable(self):
        """
        Given sqlite3 is unavailable
        When warn() is called twice for the same project
        Then both calls print the message and return True -- a warning
             fails OPEN
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    first = thing.warn(project, "hello")
                    second = thing.warn(project, "hello")

            self.assertTrue(first)
            self.assertTrue(second)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed.count("hello"), 2)

    def test_always_prints_when_the_store_reports_a_storage_error(self):
        """
        Given a store path whose parent cannot be created, so every claim
            reports UNGUARANTEED with the storage-error reason
        When warn() is called twice for the same project
        Then both calls print and return True, and the notice carries the
             store's storage-error reason -- a broken store fails OPEN, the
             same as a missing sqlite3
        """
        thing = once_per.day("k", "a thing")
        blocked_parent = Path(self._store_tmp.name) / "not_a_directory"
        blocked_parent.write_text("occupied")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(
                once_per_store, "_STORE_PATH", blocked_parent / "once_per.db"
            ):
                probe = once_per_store.claim(
                    project, "probe", "s", ttl=timedelta(days=1)
                )
                with patch("builtins.print") as mock_print:
                    first = thing.warn(project, "hello")
                    second = thing.warn(project, "hello")

            self.assertEqual(probe.status, ClaimStatus.UNGUARANTEED)
            self.assertEqual(probe.reason, once_per_store._REASON_STORAGE_ERROR)
            self.assertTrue(first)
            self.assertTrue(second)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed.count("hello"), 2)
            notices = _notices(mock_print, "hello")
            self.assertEqual(len(notices), 1)
            self.assertIn(once_per_store._REASON_STORAGE_ERROR, notices[0])

    def test_degraded_notice_composes_caller_description_once(self):
        """
        Given sqlite3 is unavailable
        When warn() is called twice with description "a thing"
        Then the degraded-mode notice mentions "a thing" and is printed on
             stderr only ONCE across both calls
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    thing.warn(project, "hello")
                    thing.warn(project, "hello")

            notices = _notices(mock_print, "hello")
            self.assertEqual(len(notices), 1)
            self.assertIn("a thing", notices[0])
            self.assertIn(once_per_store._REASON_NO_SQLITE, notices[0])
            self.assertEqual(_streams(mock_print), {sys.stderr})

    def test_degraded_notice_names_the_reason_not_a_specific_technology(self):
        """
        Given a project=None (the once-per-period guarantee cannot be
            verified for a different reason than sqlite3)
        When warn() is called
        Then the degraded-mode notice carries the store's own reason text
             rather than the facade naming a storage technology
        """
        thing = once_per.day("k", "a thing")

        with patch("builtins.print") as mock_print:
            thing.warn(None, "hello")

        notices = _notices(mock_print, "hello")
        self.assertEqual(len(notices), 1)
        self.assertIn(once_per_store._REASON_NO_PROJECT, notices[0])
        self.assertNotIn(once_per_store._REASON_NO_SQLITE, notices[0])

    def test_a_degraded_pass_through_is_distinguishable_from_a_genuine_claim(self):
        """
        Given one warn() that genuinely claims and one that could not be
            guaranteed (project=None)
        When both return True
        Then only the unguaranteed one prints a notice, and only the
             genuine one leaves done() reporting True -- "it printed" alone
             does not say whether the guarantee held
        """
        genuine = once_per.day("k", "a thing")
        degraded = once_per.day("k2", "another thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as genuine_print:
                genuine_result = genuine.warn(project, "hello")
            with patch("builtins.print") as degraded_print:
                degraded_result = degraded.warn(None, "hello")

            self.assertTrue(genuine_result)
            self.assertTrue(degraded_result)
            self.assertEqual(_notices(genuine_print, "hello"), [])
            self.assertEqual(len(_notices(degraded_print, "hello")), 1)
            self.assertTrue(genuine.done(project))
            self.assertFalse(degraded.done(None))


class TestOncePerClaimKey(_IsolatedStoreMixin, unittest.TestCase):
    """A claim is keyed on the project, the thing, AND the period -- each separates two calls."""

    def test_two_things_in_one_project_claim_independently(self):
        """
        Given two things with different keys in the same project
        When both warn() in the same period
        Then both print -- one thing's claim never satisfies another's
        """
        thing_a = once_per.day("a", "thing A")
        thing_b = once_per.day("b", "thing B")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                first = thing_a.warn(project, "from a")
                second = thing_b.warn(project, "from b")

            self.assertTrue(first)
            self.assertTrue(second)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed, ["from a", "from b"])

    def test_one_thing_in_two_projects_claims_independently(self):
        """
        Given one thing and two different project roots
        When it warns once for each
        Then both print -- a claim taken for one project never suppresses
             another
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as first_dir, TemporaryDirectory() as second_dir:
            with patch("builtins.print") as mock_print:
                first = thing.warn(Path(first_dir), "from one")
                second = thing.warn(Path(second_dir), "from two")

            self.assertTrue(first)
            self.assertTrue(second)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed, ["from one", "from two"])

    def test_a_new_period_re_enables_the_thing(self):
        """
        Given a thing already warned for one calendar day, using the real
            day_scope
        When it warns again for that day, then for the next day
        Then the same day is silent and the next day prints again -- and
             the still-live 7-day retention does not hold the new day's
             claim back
        """
        period = once_per._Period(
            "day",
            lambda context: once_per_store.day_scope(context),
            timedelta(days=7),
        )
        thing = period("k", "a thing")
        day_one, day_two = date(2026, 1, 1), date(2026, 1, 2)
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                first = thing.warn(project, "day one", context=day_one)
                again = thing.warn(project, "day one again", context=day_one)
                next_day = thing.warn(project, "day two", context=day_two)

            self.assertTrue(first)
            self.assertFalse(again)
            self.assertTrue(next_day)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed, ["day one", "day two"])


class TestOncePerClaimTtl(_IsolatedStoreMixin, unittest.TestCase):
    """Within one scope, whether a second call is suppressed is decided by the claim's ttl."""

    def test_a_live_claim_suppresses_a_second_call_in_the_same_scope(self):
        """
        Given a period whose retention outlasts the test
        When warn() is called twice in the same scope
        Then only the first prints
        """
        thing = _period_with_retention(timedelta(days=7))("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                first = thing.warn(project, "hello")
                second = thing.warn(project, "hello again")

            self.assertTrue(first)
            self.assertFalse(second)
            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            self.assertEqual(printed, ["hello"])

    def test_a_claim_past_its_ttl_is_reclaimed_in_the_same_scope(self):
        """
        Given a period whose retention has already elapsed when the claim
            is written, and housekeeping suppressed so the expired row is
            still there for the second call to collide with
        When warn() is called twice in the same scope
        Then both print -- the expired claim is RECLAIMED rather than
             suppressing forever
        """
        thing = _period_with_retention(timedelta(seconds=-1))("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # Without this, reap() deletes the expired row and the second call is
            # an ordinary insert, which passes with or without the reclaim clause.
            with patch.object(once_per_store, "reap") as suppressed_reap:
                with patch("builtins.print") as first_print:
                    first = thing.warn(project, "hello")
                self.assertIn("k", self.claim_kinds())
                with patch("builtins.print") as second_print:
                    second = thing.warn(project, "hello again")

            self.assertTrue(suppressed_reap.called)
            self.assertTrue(first)
            self.assertTrue(second)
            self.assertEqual(
                [c.args[0] for c in first_print.call_args_list if c.args], ["hello"]
            )
            self.assertEqual(
                [c.args[0] for c in second_print.call_args_list if c.args],
                ["hello again"],
            )


class TestOncePerRun(_IsolatedStoreMixin, unittest.TestCase):
    """Test the run primitive and its two Repeat policies."""

    def test_runs_and_returns_action_result_the_first_time(self):
        """
        Given no prior activity for this thing/project
        When run() is called with an action
        Then the action runs and its result is returned
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            result = thing.run(
                project,
                lambda: "ran",
                repeating=once_per.Repeat.SAFE,
            )

            self.assertEqual(result, "ran")

    def test_second_call_same_day_does_not_run_action(self):
        """
        Given run() already ran today for this thing/project
        When run() is called again the same day
        Then the action does not run and None is returned
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.run(
                project,
                lambda: "ran",
                repeating=once_per.Repeat.SAFE,
            )

            calls = []
            result = thing.run(
                project,
                lambda: calls.append(1),
                repeating=once_per.Repeat.SAFE,
            )

            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_repeating_has_no_default(self):
        """
        Given run() called without stating whether repeats are safe
        When the call is made
        Then it raises TypeError -- fail-open must never be the accidental
             behaviour of a caller that did not think about it
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            with self.assertRaises(TypeError):
                thing.run(Path(tmpdir), lambda: "ran")

    def test_safe_to_repeat_runs_action_when_throttling_unavailable(self):
        """
        Given sqlite3 is unavailable and repeating=SAFE
        When run() is called
        Then the action still runs (fails open)
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(once_per_store, "sqlite3", None):
                result = thing.run(
                    project,
                    lambda: "ran",
                    repeating=once_per.Repeat.SAFE,
                )

            self.assertEqual(result, "ran")

    def test_unsafe_to_repeat_does_not_run_action_when_throttling_unavailable(self):
        """
        Given sqlite3 is unavailable and repeating=UNSAFE
        When run() is called
        Then the action does NOT run (fails closed) and None is returned
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            calls = []

            with patch.object(once_per_store, "sqlite3", None):
                result = thing.run(
                    project,
                    lambda: calls.append(1),
                    repeating=once_per.Repeat.UNSAFE,
                )

            self.assertIsNone(result)
            self.assertEqual(calls, [])

    def test_none_project_with_unsafe_to_repeat_does_not_run_action(self):
        """
        Given project=None (no project root could be resolved -- the once-
            per-period guarantee cannot be verified for this call) and
            repeating=UNSAFE
        When run() is called
        Then the action does NOT run
        """
        thing = once_per.day("k", "a thing")
        calls = []

        result = thing.run(
            None,
            lambda: calls.append(1),
            repeating=once_per.Repeat.UNSAFE,
        )

        self.assertIsNone(result)
        self.assertEqual(calls, [])

    def test_none_project_with_safe_to_repeat_still_runs_action(self):
        """
        Given project=None and repeating=SAFE
        When run() is called
        Then the action DOES run -- the caller declared repeats safe
        """
        thing = once_per.day("k", "a thing")

        result = thing.run(None, lambda: "ran", repeating=once_per.Repeat.SAFE)

        self.assertEqual(result, "ran")

    def test_unsafe_to_repeat_reports_via_the_degraded_notice(self):
        """
        Given sqlite3 is unavailable and repeating=UNSAFE
        When run() is called
        Then a notice is printed on stderr naming *description* and saying
             it will be skipped -- the skip is not silent
        """
        thing = once_per.day("k", "automatic permission migration")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    thing.run(
                        project,
                        lambda: None,
                        repeating=once_per.Repeat.UNSAFE,
                    )

            printed = " ".join(
                str(c.args[0]) for c in mock_print.call_args_list if c.args
            )
            self.assertIn("automatic permission migration", printed)
            self.assertIn("skipped", printed)
            self.assertEqual(_streams(mock_print), {sys.stderr})


class TestOncePerRelease(_IsolatedStoreMixin, unittest.TestCase):
    """release(): giving a claimed slot back early so this period can retry."""

    def test_release_lets_a_later_call_this_period_claim_again(self):
        """
        Given a thing whose slot is claimed for a project
        When release() is called
        Then done() reports free again, and run() executes its action
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.run(project, lambda: "ran", repeating=once_per.Repeat.SAFE)
            self.assertTrue(thing.done(project))

            thing.release(project)

            self.assertFalse(thing.done(project))
            result = thing.run(
                project, lambda: "ran again", repeating=once_per.Repeat.SAFE
            )
            self.assertEqual(result, "ran again")

    def test_release_of_an_unclaimed_slot_is_a_no_op(self):
        """
        Given a thing never claimed for a project
        When release() is called
        Then nothing raises and the slot stays unclaimed
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            thing.release(project)

            self.assertFalse(thing.done(project))

    def test_release_does_not_affect_a_different_thing_same_project(self):
        """
        Given two different things both claimed for the same project
        When release() is called on only one
        Then the other thing's claim is untouched
        """
        thing_a = once_per.day("a", "thing a")
        thing_b = once_per.day("b", "thing b")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing_a.run(project, lambda: "a", repeating=once_per.Repeat.SAFE)
            thing_b.run(project, lambda: "b", repeating=once_per.Repeat.SAFE)

            thing_a.release(project)

            self.assertFalse(thing_a.done(project))
            self.assertTrue(thing_b.done(project))


class TestOncePerInternalHousekeeping(_IsolatedStoreMixin, unittest.TestCase):
    """Housekeeping is internal to OncePer: a caller never asks for it."""

    def test_successful_claim_reaps_the_expired_row(self):
        """
        Given an expired claim under a different key for the same project
        When a fresh call to warn() successfully claims its own key
        Then the expired row is GONE from the claims table while the fresh
             one remains -- housekeeping ran as a side effect, with no
             caller-visible "sweep" call anywhere
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "other", "s", ttl=timedelta(seconds=-1))
            self.assertIn("other", self.claim_kinds())

            thing.warn(project, "hello")

            kinds = self.claim_kinds()
            self.assertNotIn("other", kinds)
            self.assertIn("k", kinds)

    def test_already_satisfied_call_does_not_reattempt_housekeeping(self):
        """
        Given warn() already ran (and swept) once today
        When warn() is called again the same day and is deduplicated
        Then the only claim it attempts is its own -- no second attempt on
             the shared housekeeping key
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.warn(project, "hello")

            with patch.object(
                once_per_store, "claim", wraps=once_per_store.claim
            ) as spy_claim:
                thing.warn(project, "hello again")

            kinds = [call.args[1] for call in spy_claim.call_args_list]
            self.assertEqual(kinds, ["k"])

    def test_housekeeping_is_shared_across_things_and_runs_once_per_period(self):
        """
        Given two different things claiming successfully in one project and
            period
        When each of them sweeps
        Then reap() runs exactly once, against the project's logs
             directory -- the sweep holds its own claim under a key shared
             by every OncePer
        """
        thing_a = once_per.day("a", "thing A")
        thing_b = once_per.day("b", "thing B")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(
                once_per_store, "reap", wraps=once_per_store.reap
            ) as spy_reap:
                self.assertTrue(thing_a.warn(project, "from a"))
                self.assertTrue(thing_b.warn(project, "from b"))

            self.assertEqual(spy_reap.call_count, 1)
            self.assertEqual(spy_reap.call_args.args[0], project / "logs")


class TestOncePerDegradedNoticeIsPerInstance(_IsolatedStoreMixin, unittest.TestCase):
    """The degraded-notice dedup is per instance, not a registry keyed on the key alone."""

    def test_two_things_with_the_same_key_notify_independently(self):
        """
        Given two SEPARATE OncePer instances that happen to share the same
            key string (as two different periods throttling the same key
            would)
        When both hit an unguaranteed claim and call warn()
        Then BOTH print their own degraded-mode notice
        """
        thing_a = once_per.day("shared-key", "thing A")
        thing_b = once_per.day("shared-key", "thing B")

        with patch("builtins.print") as mock_print:
            thing_a.warn(None, "hello a")
            thing_b.warn(None, "hello b")

        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("thing A", printed)
        self.assertIn("thing B", printed)


if __name__ == "__main__":
    unittest.main()
