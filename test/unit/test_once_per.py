"""
Unit tests for toolguard.once_per: the once-per-period facade
(``day`` / ``OncePer`` / ``Repeat``).
"""

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import once_per, once_per_store


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
        Then it returns True
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.warn(project, "message")

            self.assertTrue(thing.done(project))


class TestOncePerWarn(_IsolatedStoreMixin, unittest.TestCase):
    """Test the fail-open warning primitive."""

    def test_prints_and_returns_true_the_first_time(self):
        """
        Given no prior warning for this thing
        When warn() is called
        Then it prints the message and returns True
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch("builtins.print") as mock_print:
                result = thing.warn(project, "hello")

            self.assertTrue(result)
            mock_print.assert_called_once()
            self.assertEqual(mock_print.call_args.args[0], "hello")

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

    def test_degraded_notice_composes_caller_description_once(self):
        """
        Given sqlite3 is unavailable
        When warn() is called twice with description "a thing"
        Then the degraded-mode notice mentions "a thing" and the reason, and
             is printed only ONCE across both calls
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    thing.warn(project, "hello")
                    thing.warn(project, "hello")

            printed = [c.args[0] for c in mock_print.call_args_list if c.args]
            degraded = [p for p in printed if "cannot be limited" in p]
            self.assertEqual(len(degraded), 1)
            self.assertIn("a thing", degraded[0])

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

        printed = [c.args[0] for c in mock_print.call_args_list if c.args]
        degraded = [p for p in printed if "cannot be limited" in p]
        self.assertEqual(len(degraded), 1)
        self.assertIn("project", degraded[0])


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
        Then a notice is printed naming *description* and saying it will be
             skipped
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


class TestOncePerInternalHousekeeping(_IsolatedStoreMixin, unittest.TestCase):
    """Housekeeping is internal to OncePer: a caller never asks for it."""

    def test_successful_claim_triggers_reap(self):
        """
        Given an expired claim under a different key for the same project
        When a fresh call to warn() successfully claims its own key
        Then the expired row is gone -- housekeeping ran as a side effect,
             with no caller-visible "sweep" call anywhere
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            once_per_store.claim(project, "other", "s", ttl=timedelta(seconds=-1))

            thing.warn(project, "hello")

            self.assertFalse(once_per_store.is_claimed(project, "other", "s"))

    def test_already_satisfied_call_does_not_reattempt_housekeeping(self):
        """
        Given warn() already ran (and swept) once today
        When warn() is called again the same day and is deduplicated
        Then once_per_store.reap is not called a second time
        """
        thing = once_per.day("k", "a thing")
        with TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)
            thing.warn(project, "hello")

            with patch.object(once_per_store, "reap") as mock_reap:
                thing.warn(project, "hello again")

            mock_reap.assert_not_called()


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
