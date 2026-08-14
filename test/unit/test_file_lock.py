"""
Unit tests for toolguard.file_lock's exclusive() context manager: single-process
acquire/release, the failure modes that all collapse into LockUnavailable, the
timeout budget (measured on a fake clock), backend selection, the Windows
backend (reachable only by patching -- this suite runs on Linux), and real
cross-process behaviour via subprocess.
"""

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import file_lock

from test.unit._subprocess_harness import run_child, wait_for_path


def _fd_is_open(fd: int) -> bool:
    """True while *fd* is still an open descriptor in this process."""
    try:
        os.fstat(fd)
        return True
    except OSError:
        return False


def _recording_lseek(events: list):
    """
    An ``os.lseek`` replacement that records ``("seek", (pos, whence))`` into
    *events* and then really seeks. Sharing one list with :class:`_FakeMsvcrt`
    is what makes seek/lock order observable: a call count cannot tell a seek
    before the lock from two seeks after it.
    """
    real_lseek = os.lseek

    def recorder(fd, pos, whence):
        events.append(("seek", (pos, whence)))
        return real_lseek(fd, pos, whence)

    return recorder


class _FakeMsvcrt:
    """Minimal double for the msvcrt module, controllable per test."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(
        self,
        fail_times: int = 0,
        unlock_raises: bool = False,
        events: list | None = None,
    ):
        self.fail_times = fail_times
        self.unlock_raises = unlock_raises
        self.calls = []
        self.events = events if events is not None else []

    def locking(self, fd, mode, nbytes):
        self.calls.append((fd, mode, nbytes))
        kind = "lock" if mode == self.LK_NBLCK else "unlock"
        self.events.append((kind, _fd_is_open(fd)))
        if mode == self.LK_UNLCK and self.unlock_raises:
            raise OSError("unlock refused")
        if mode == self.LK_NBLCK and self.fail_times > 0:
            self.fail_times -= 1
            raise OSError("locked")


class _FakeClock:
    """
    Stand-in for the ``time`` module whose ``monotonic()`` advances one second
    per reading, so a timeout budget is exhausted deterministically instead of
    by real elapsed time.
    """

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self) -> float:
        value = self.now
        self.now += 1.0
        return value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class TestExclusiveSingleProcess(unittest.TestCase):
    """In-process acquire/release/contend/timeout behaviour."""

    def test_acquire_and_release_allows_a_later_acquire(self):
        """
        Given no prior lock on a path
        When exclusive() is entered and exited
        Then a later exclusive() call on the same path succeeds
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "locks" / "x.lock"

            with file_lock.exclusive(lock_path, timeout_seconds=1):
                pass
            with file_lock.exclusive(lock_path, timeout_seconds=1):
                pass

    def test_creates_missing_parent_directory(self):
        """
        Given a lock path whose parent directory does not exist yet
        When exclusive() is entered
        Then the parent directory is created and the lock is acquired
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "does" / "not" / "exist" / "x.lock"

            with file_lock.exclusive(lock_path, timeout_seconds=1):
                pass

            self.assertTrue(lock_path.parent.is_dir())

    def test_nested_acquire_on_same_path_times_out(self):
        """
        Given a lock already held (flock binds to the open file DESCRIPTION,
            so two exclusive() calls on the same path contend even within
            one process)
        When a second exclusive() call on the same path is attempted with a
            short timeout
        Then it raises LockUnavailable with reason=REASON_TIMEOUT and a
             detail naming how long it waited
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"

            with file_lock.exclusive(lock_path, timeout_seconds=1):
                with self.assertRaises(file_lock.LockUnavailable) as ctx:
                    with file_lock.exclusive(lock_path, timeout_seconds=0.3):
                        self.fail("should not have acquired a held lock")

            self.assertEqual(ctx.exception.reason, file_lock.REASON_TIMEOUT)
            self.assertEqual(ctx.exception.path, lock_path)
            self.assertIn("0.3", ctx.exception.detail)
            self.assertIn("0.3", str(ctx.exception))

    def test_lock_released_on_exception_inside_block(self):
        """
        Given a lock acquired inside a block that then raises
        When the exception propagates out of exclusive()
        Then the lock is released -- a later acquire succeeds
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"

            with self.assertRaises(ValueError):
                with file_lock.exclusive(lock_path, timeout_seconds=1):
                    raise ValueError("boom")

            with file_lock.exclusive(lock_path, timeout_seconds=1):
                pass

    def test_lock_file_is_not_removed_when_the_block_exits(self):
        """
        Given a lock acquired on a path
        When the block exits normally
        Then the lock file still exists -- deleting it would let a process
             that re-creates it hold the same lock as one already waiting on
             the old inode
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"

            with file_lock.exclusive(lock_path, timeout_seconds=1):
                self.assertTrue(lock_path.exists())

            self.assertTrue(lock_path.exists())

    def test_different_paths_do_not_contend(self):
        """
        Given two different lock paths
        When both are held at once (nested, in-process)
        Then neither blocks the other
        """
        with TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "a.lock"
            path_b = Path(tmpdir) / "b.lock"

            with file_lock.exclusive(path_a, timeout_seconds=1):
                with file_lock.exclusive(path_b, timeout_seconds=1):
                    pass


class TestLockUnavailableFailureModes(unittest.TestCase):
    """Every way exclusive() can fail collapses into LockUnavailable."""

    def test_no_primitive_available_on_either_platform(self):
        """
        Given both fcntl and msvcrt are unavailable
        When exclusive() is entered
        Then it raises LockUnavailable with reason=REASON_NO_PRIMITIVE,
             without touching the filesystem
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "locks" / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", None):
                    with self.assertRaises(file_lock.LockUnavailable) as ctx:
                        with file_lock.exclusive(lock_path, timeout_seconds=1):
                            self.fail("should not have acquired")

            self.assertEqual(ctx.exception.reason, file_lock.REASON_NO_PRIMITIVE)
            self.assertFalse(lock_path.parent.exists())

    def test_unwritable_lock_directory_raises(self):
        """
        Given a lock path whose parent cannot be created (a plain file
            already occupies where the parent directory needs to go)
        When exclusive() is entered
        Then it raises LockUnavailable with reason=REASON_DIRECTORY_UNAVAILABLE
        """
        with TemporaryDirectory() as tmpdir:
            blocked = Path(tmpdir) / "not_a_directory"
            blocked.write_text("occupied")
            lock_path = blocked / "sub" / "x.lock"

            with self.assertRaises(file_lock.LockUnavailable) as ctx:
                with file_lock.exclusive(lock_path, timeout_seconds=1):
                    self.fail("should not have acquired")

            self.assertEqual(
                ctx.exception.reason, file_lock.REASON_DIRECTORY_UNAVAILABLE
            )

    def test_lock_path_that_is_a_directory_raises(self):
        """
        Given a lock path that is itself an existing directory (so opening
            it for read/write raises)
        When exclusive() is entered
        Then it raises LockUnavailable with reason=REASON_FILE_UNAVAILABLE
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            lock_path.mkdir()

            with self.assertRaises(file_lock.LockUnavailable) as ctx:
                with file_lock.exclusive(lock_path, timeout_seconds=1):
                    self.fail("should not have acquired")

            self.assertEqual(ctx.exception.reason, file_lock.REASON_FILE_UNAVAILABLE)

    def test_reason_is_structured_and_message_carries_detail(self):
        """
        Given a LockUnavailable raised with a reason and a detail
        When its attributes are inspected
        Then reason is available as data (not requiring message parsing) and
             the detail still appears in the rendered message
        """
        exc = file_lock.LockUnavailable(
            Path("/tmp/x.lock"), file_lock.REASON_TIMEOUT, "waited 10.0s"
        )

        self.assertEqual(exc.reason, file_lock.REASON_TIMEOUT)
        self.assertEqual(exc.detail, "waited 10.0s")
        self.assertIn("waited 10.0s", str(exc))


class TestWindowsBackendViaPatching(unittest.TestCase):
    """Exercises the msvcrt branch by patching -- the one branch a Linux run cannot reach."""

    def test_seek_precedes_each_lock_call_and_unlock_precedes_the_close(self):
        """
        Given fcntl is unavailable and a working fake msvcrt is installed
        When exclusive() acquires and releases the lock
        Then the interleaved call sequence is exactly seek, lock, seek,
             unlock -- each msvcrt call gets its OWN preceding seek to
             offset 0, both seeks are absolute, and the descriptor is still
             open when the unlock happens
        """
        events = []
        fake = _FakeMsvcrt(events=events)
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with patch.object(file_lock.os, "lseek", _recording_lseek(events)):
                        with file_lock.exclusive(lock_path, timeout_seconds=1):
                            pass

        self.assertEqual(
            [kind for kind, _ in events], ["seek", "lock", "seek", "unlock"]
        )
        self.assertEqual(
            [detail for kind, detail in events if kind == "seek"],
            [(0, os.SEEK_SET), (0, os.SEEK_SET)],
        )
        self.assertEqual(
            [fd_open for kind, fd_open in events if kind == "unlock"], [True]
        )

    def test_unlock_still_happens_when_the_block_raises(self):
        """
        Given fcntl is unavailable, a working fake msvcrt, and a block that
            raises
        When the exception propagates out of exclusive()
        Then the fake still recorded an LK_UNLCK -- the msvcrt lock is undone
             on the exception path, not only on the success path
        """
        fake = _FakeMsvcrt()
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with self.assertRaises(ValueError):
                        with file_lock.exclusive(lock_path, timeout_seconds=1):
                            raise ValueError("boom")

        self.assertIn(fake.LK_UNLCK, [call[1] for call in fake.calls])

    def test_unlock_failure_does_not_escape_to_the_caller(self):
        """
        Given fcntl is unavailable and a fake msvcrt whose LK_UNLCK raises
        When exclusive()'s block completes normally
        Then nothing escapes -- closing the descriptor releases the lock
             anyway, so a failed unlock must not turn a completed critical
             section into a caller-visible error
        """
        fake = _FakeMsvcrt(unlock_raises=True)
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with file_lock.exclusive(lock_path, timeout_seconds=1):
                        pass

        self.assertIn(fake.LK_UNLCK, [call[1] for call in fake.calls])

    def test_contended_lock_is_retried_until_it_becomes_available(self):
        """
        Given a fake msvcrt that refuses the first three attempts and then
            succeeds, standing in for a holder that releases mid-wait
        When exclusive() is entered with a timeout long enough to cover them
        Then the block runs and locking() was attempted four times -- waiting
             is a retry loop, not one attempt followed by a give-up
        """
        fake = _FakeMsvcrt(fail_times=3)
        ran = []
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with file_lock.exclusive(lock_path, timeout_seconds=5):
                        ran.append("body")

        self.assertEqual(ran, ["body"])
        attempts = [call for call in fake.calls if call[1] == fake.LK_NBLCK]
        self.assertEqual(len(attempts), 4)

    def test_contended_lock_times_out(self):
        """
        Given fcntl is unavailable and a fake msvcrt whose locking() always
            raises OSError (simulating another holder)
        When exclusive() is attempted with a short timeout
        Then it raises LockUnavailable with reason=REASON_TIMEOUT
        """
        fake = _FakeMsvcrt(fail_times=10_000)
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with self.assertRaises(file_lock.LockUnavailable) as ctx:
                        with file_lock.exclusive(lock_path, timeout_seconds=0.2):
                            self.fail("should not have acquired")

        self.assertEqual(ctx.exception.reason, file_lock.REASON_TIMEOUT)


class TestTimeoutBudget(unittest.TestCase):
    """How long a doomed acquire waits, measured on a fake clock."""

    def _doomed_acquire(self, **kwargs):
        """
        Run an acquire that can never succeed, on a clock advancing one
        second per reading. Returns (elapsed_on_that_clock, detail, sleeps).
        """
        clock = _FakeClock()
        fake = _FakeMsvcrt(fail_times=10_000)
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with patch.object(file_lock, "time", clock):
                        with self.assertRaises(file_lock.LockUnavailable) as ctx:
                            with file_lock.exclusive(lock_path, **kwargs):
                                self.fail("should not have acquired")
        return clock.now, ctx.exception.detail, clock.sleeps

    def test_explicit_timeout_bounds_the_wait(self):
        """
        Given a clock advancing one second per reading and a lock that is
            never granted
        When exclusive() is called with timeout_seconds=3.0
        Then it gives up after about three of that clock's seconds -- not
             after the module default -- reports that budget in the detail,
             and waited _POLL_SECONDS between attempts
        """
        elapsed, detail, sleeps = self._doomed_acquire(timeout_seconds=3.0)

        self.assertGreaterEqual(elapsed, 3.0)
        self.assertLess(elapsed, 5.0)
        self.assertEqual(detail, "waited 3.0s")
        self.assertGreater(len(sleeps), 0)
        self.assertEqual(sleeps, [file_lock._POLL_SECONDS] * len(sleeps))

    def test_omitted_timeout_uses_the_module_default(self):
        """
        Given the same never-granted lock and fake clock
        When exclusive() is called with NO timeout_seconds argument
        Then it waits DEFAULT_TIMEOUT_SECONDS of that clock and names that
             budget in the detail -- the default is exercised, not merely
             declared
        """
        default = file_lock.DEFAULT_TIMEOUT_SECONDS
        elapsed, detail, _ = self._doomed_acquire()

        self.assertGreaterEqual(elapsed, default)
        self.assertLess(elapsed, default + 2.0)
        self.assertEqual(detail, f"waited {default}s")


class TestBackendSelection(unittest.TestCase):
    """Which primitive wins when more than one is present."""

    def test_posix_backend_is_preferred_over_msvcrt(self):
        """
        Given both primitives present -- the platform's real fcntl plus a
            fake msvcrt
        When exclusive() acquires, and a second acquire on the same path
            contends with it
        Then the fake msvcrt was never called and the contending acquire was
             refused: the flock backend was chosen and it is the real one
        """
        fake = _FakeMsvcrt()
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "msvcrt", fake):
                with file_lock.exclusive(lock_path, timeout_seconds=1):
                    with self.assertRaises(file_lock.LockUnavailable):
                        with file_lock.exclusive(lock_path, timeout_seconds=0.2):
                            self.fail("should not have acquired a held lock")

        self.assertEqual(fake.calls, [])


#: Child-process script prelude: the imports, plus lock_path from argv[1].
_PRELUDE = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from toolguard import file_lock\n"
    "lock_path = Path(sys.argv[1])\n"
)


class TestConcurrentProcesses(unittest.TestCase):
    """Real cross-process behaviour: a single-process test proves nothing about an OS lock."""

    def test_second_process_declines_while_first_holds(self):
        """
        Given one process holding the lock (signalling readiness via a
            marker file, then holding for a fixed duration)
        When a second process attempts the SAME lock, with a timeout well
            shorter than the holder's hold duration, once the marker
            confirms the first process actually holds it
        Then the first process reports it acquired the lock and the second
             reports it was declined
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            marker = Path(tmpdir) / "holding"

            holder_script = _PRELUDE + (
                "marker = Path(sys.argv[2])\n"
                "with file_lock.exclusive(lock_path, timeout_seconds=5):\n"
                "    marker.touch()\n"
                "    time.sleep(1.5)\n"
                "print('acquired')\n"
            )
            contender_script = _PRELUDE + (
                "marker = Path(sys.argv[2])\n"
                "deadline = time.monotonic() + 10\n"
                "while not marker.exists() and time.monotonic() < deadline:\n"
                "    time.sleep(0.01)\n"
                "try:\n"
                "    with file_lock.exclusive(lock_path, timeout_seconds=0.3):\n"
                "        print('unexpectedly acquired')\n"
                "except file_lock.LockUnavailable:\n"
                "    print('declined')\n"
            )

            holder = run_child(holder_script, str(lock_path), str(marker))
            contender = run_child(contender_script, str(lock_path), str(marker))

            holder_out, holder_err = holder.communicate(timeout=15)
            contender_out, contender_err = contender.communicate(timeout=15)

            self.assertEqual(holder.returncode, 0, msg=holder_err)
            self.assertEqual(contender.returncode, 0, msg=contender_err)
            self.assertEqual(holder_out.strip(), "acquired")
            self.assertEqual(contender_out.strip(), "declined")

    def test_waits_through_a_held_lock_and_acquires_once_it_is_released(self):
        """
        Given a process holding the lock that, while STILL holding it, writes
            the wall-clock time of its last moment of ownership to a file
        When this process starts a contended acquire with a timeout far
            longer than the hold
        Then the acquire succeeds, and that recorded time falls between the
             moment this process began waiting and the moment it acquired --
             so the lock was demonstrably held after the wait began, and a
             single non-retried attempt could not have produced this
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            marker = Path(tmpdir) / "holding"
            held_until = Path(tmpdir) / "held_until"

            holder_script = _PRELUDE + (
                "marker = Path(sys.argv[2])\n"
                "held_until = Path(sys.argv[3])\n"
                "with file_lock.exclusive(lock_path, timeout_seconds=5):\n"
                "    marker.touch()\n"
                "    time.sleep(1.5)\n"
                "    held_until.write_text(repr(time.time()))\n"
            )
            holder = run_child(
                holder_script, str(lock_path), str(marker), str(held_until)
            )

            self.assertTrue(
                wait_for_path(marker), "holder never signalled it held the lock"
            )
            self.assertFalse(held_until.exists(), "holder released before we waited")

            started_waiting_at = time.time()
            with file_lock.exclusive(lock_path, timeout_seconds=20):
                acquired_at = time.time()

            holder_out, holder_err = holder.communicate(timeout=15)
            self.assertEqual(holder.returncode, 0, msg=holder_err)

            still_held_at = float(held_until.read_text())
            self.assertGreater(still_held_at, started_waiting_at)
            self.assertGreater(acquired_at, still_held_at)

    def test_different_projects_do_not_block_each_other(self):
        """
        Given two DIFFERENT lock paths (standing in for two different
            projects), each held by its own process concurrently
        When both processes run at the same time
        Then both acquire successfully
        """
        with TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "a.lock"
            path_b = Path(tmpdir) / "b.lock"

            script = _PRELUDE + (
                "with file_lock.exclusive(lock_path, timeout_seconds=5):\n"
                "    time.sleep(0.5)\n"
                "print('acquired')\n"
            )

            proc_a = run_child(script, str(path_a))
            proc_b = run_child(script, str(path_b))

            out_a, err_a = proc_a.communicate(timeout=15)
            out_b, err_b = proc_b.communicate(timeout=15)

            self.assertEqual(proc_a.returncode, 0, msg=err_a)
            self.assertEqual(proc_b.returncode, 0, msg=err_b)
            self.assertEqual(out_a.strip(), "acquired")
            self.assertEqual(out_b.strip(), "acquired")

    def test_lock_released_when_holding_process_dies(self):
        """
        Given a process that acquires the lock, signals readiness via a
            marker file, then blocks indefinitely while still holding it
        When that process is killed (SIGKILL, simulating a crash) and a
            fresh acquire is then attempted in THIS process
        Then the lock is acquired -- the OS released it when the holder's
             file descriptor closed on process death
        """
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            marker = Path(tmpdir) / "holding"

            holder_script = _PRELUDE + (
                "marker = Path(sys.argv[2])\n"
                "with file_lock.exclusive(lock_path, timeout_seconds=5):\n"
                "    marker.touch()\n"
                "    time.sleep(60)\n"
            )
            holder = run_child(holder_script, str(lock_path), str(marker))

            self.assertTrue(
                wait_for_path(marker), "holder never signalled it held the lock"
            )

            holder.kill()
            holder.communicate(timeout=15)

            with file_lock.exclusive(lock_path, timeout_seconds=5):
                pass


if __name__ == "__main__":
    unittest.main()
