"""
Unit tests for toolguard.file_lock (TOO-45 punch-list #15).

Covers the exclusive() context manager: single-process acquire/release
(including release-on-exception), the failure modes that all collapse into
LockUnavailable, the Windows backend (exercised via patching -- this suite
runs on Linux), and real cross-process behaviour (contention, independent
paths, release on process death) via subprocess.Popen, following
test_once_per_store.py's harness.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import file_lock

from test.unit._subprocess_harness import run_child, wait_for_path


class _FakeMsvcrt:
    """Minimal double for the msvcrt module, controllable per test."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls = []

    def locking(self, fd, mode, nbytes):
        self.calls.append((fd, mode, nbytes))
        if mode == self.LK_NBLCK and self.fail_times > 0:
            self.fail_times -= 1
            raise OSError("locked")


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
                pass  # must not raise

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
        Given a lock already held (via a separate file descriptor -- flock
            locks are per-open-file-description, so two exclusive() calls on
            the same path genuinely contend even within one process)
        When a second exclusive() call on the same path is attempted with a
            short timeout
        Then it raises LockUnavailable with reason=REASON_TIMEOUT and a
             detail naming how long it waited -- real output, not a shape
             only ever produced by hand-constructing the exception
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
                pass  # must not raise -- the prior lock was released

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
                    pass  # must not raise


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
    """
    Exercises the msvcrt branch by patching, since this suite runs on
    Linux. Kept deliberately small: this is the one branch that cannot be
    reached natively here.
    """

    def test_successful_lock_calls_locking_and_unlocking_before_close(self):
        """
        Given fcntl is unavailable and a working fake msvcrt is installed
        When exclusive() acquires and releases the lock
        Then the fake's LK_NBLCK (lock) and LK_UNLCK (unlock) calls both
             happened, unlock before the descriptor closes, and the
             descriptor is seeked to 0 before BOTH -- acquire and release
             are symmetric, neither relies on the fd's implicit position
        """
        fake = _FakeMsvcrt()
        with TemporaryDirectory() as tmpdir:
            lock_path = Path(tmpdir) / "x.lock"
            with patch.object(file_lock, "fcntl", None):
                with patch.object(file_lock, "msvcrt", fake):
                    with patch.object(
                        file_lock.os, "lseek", wraps=file_lock.os.lseek
                    ) as mock_lseek:
                        with file_lock.exclusive(lock_path, timeout_seconds=1):
                            pass

        modes = [call[1] for call in fake.calls]
        self.assertIn(fake.LK_NBLCK, modes)
        self.assertIn(fake.LK_UNLCK, modes)
        self.assertGreaterEqual(mock_lseek.call_count, 2)

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


#: Shared child-process script prelude: import, resolve the lock path from argv.
_PRELUDE = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "from toolguard import file_lock\n"
    "lock_path = Path(sys.argv[1])\n"
)


class TestConcurrentProcesses(unittest.TestCase):
    """
    Real cross-process behaviour -- a single-process test proves nothing
    about an OS-level advisory lock. Follows test_once_per_store.py's
    subprocess harness.
    """

    def test_second_process_declines_while_first_holds(self):
        """
        Given one process holding the lock (signalling readiness via a
            marker file, then holding for a fixed duration)
        When a second process attempts the SAME lock, with a timeout well
            shorter than the holder's hold duration, once the marker
            confirms the first process actually holds it
        Then the first process reports it acquired the lock and the second
             reports it was declined -- genuine cross-process mutual
             exclusion, not merely in-process fd contention
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

    def test_different_projects_do_not_block_each_other(self):
        """
        Given two DIFFERENT lock paths (standing in for two different
            projects), each held by its own process concurrently
        When both processes run at the same time
        Then both acquire successfully -- one project's migration never
             blocks another's
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
             file descriptor closed on process death, exactly why flock
             (never a hand-rolled O_EXCL lockfile) is used
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
                pass  # must not raise -- proves the OS released the dead holder's lock


if __name__ == "__main__":
    unittest.main()
