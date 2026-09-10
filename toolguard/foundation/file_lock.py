"""
Cross-process OS advisory file locking: one context manager, :func:`exclusive`.

POSIX uses ``fcntl.flock``, never ``fcntl.lockf``: POSIX record locks are
released when ANY descriptor for the path closes anywhere in the process, so
an unrelated ``open()``/``close()`` elsewhere would silently drop the lock.
Windows uses ``msvcrt.locking``. Both imports are gated, so a missing module
on either platform is not an import-time crash.

The lock is bound to an open file *description* and released when that
closes, so the OS releases it if the holding process dies -- never a
hand-rolled ``O_EXCL`` lockfile, which strands on a crash.
"""

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, Optional, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised via patching on this platform
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - not present on POSIX
    msvcrt = None

#: How often exclusive() re-attempts a contended lock while waiting.
_POLL_SECONDS = 0.05

#: exclusive()'s default wait before giving up.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: The recognised :attr:`LockUnavailable.reason` values.
REASON_NO_PRIMITIVE = "no OS advisory-lock primitive available on this platform"
REASON_DIRECTORY_UNAVAILABLE = "lock directory unavailable"
REASON_FILE_UNAVAILABLE = "lock file unavailable"
REASON_TIMEOUT = "timed out waiting for the lock"


class LockUnavailable(Exception):
    """
    Raised when exclusive access to a path could not be GUARANTEED.

    The only failure mode :func:`exclusive` raises: one exception type, with
    the distinction carried on *reason* rather than in a class hierarchy, so
    a caller that must not proceed without the guarantee catches one thing.

    Attributes:
        path: The lock file path involved.
        reason: Short, machine-stable category (one of the ``REASON_*``
            constants above) -- structured data a caller can branch on
            without parsing the message.
        detail: The underlying error's detail, for display only.
    """

    def __init__(self, path: Path, reason: str, detail: str = "") -> None:
        self.path = path
        self.reason = reason
        self.detail = detail
        suffix = f": {detail}" if detail else ""
        super().__init__(f"lock unavailable for {path} ({reason}){suffix}")


def _try_acquire_posix(fd: int) -> bool:
    """Attempt a non-blocking exclusive flock; True on success."""
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _release_posix(fd: int) -> None:
    """No-op: closing the descriptor releases the flock."""


def _try_acquire_windows(fd: int) -> bool:
    """Attempt a non-blocking exclusive msvcrt lock on one byte; True on success."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _release_windows(fd: int) -> None:
    """Undo the msvcrt lock before the caller closes the descriptor."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass


def _select_backend() -> Optional[Tuple[Callable[[int], bool], Callable[[int], None]]]:
    """Return (acquire, release) for whichever platform primitive is present, or None."""
    if fcntl is not None:
        return _try_acquire_posix, _release_posix
    if msvcrt is not None:
        return _try_acquire_windows, _release_windows
    return None


@contextmanager
def exclusive(
    path: Path, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
) -> Iterator[None]:
    """
    Hold an exclusive OS advisory lock on *path* for the duration of the block.

    Polls at a short fixed interval until *timeout_seconds* elapses. Creates
    *path*'s parent directory if needed, and *path* itself if it does not
    exist. Released when the block exits, on success or exception, and by
    the OS if the holding process dies.

    Not reentrant: each call opens its own descriptor, so a second
    ``exclusive(path)`` inside a block already holding *path* contends with
    itself and times out.

    Args:
        path: The lock file to acquire exclusive access to.
        timeout_seconds: How long to wait for a contended lock before
            raising.

    Raises:
        LockUnavailable: the lock could not be guaranteed -- no platform
            primitive is available, the lock directory/file could not be
            created or opened, or the timeout elapsed with the lock still
            held.
    """
    backend = _select_backend()
    if backend is None:
        raise LockUnavailable(path, REASON_NO_PRIMITIVE)
    acquire, release = backend

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise LockUnavailable(path, REASON_DIRECTORY_UNAVAILABLE, str(e)) from None

    try:
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR)
    except OSError as e:
        raise LockUnavailable(path, REASON_FILE_UNAVAILABLE, str(e)) from None

    try:
        deadline = time.monotonic() + timeout_seconds
        acquired = acquire(fd)
        while not acquired and time.monotonic() < deadline:
            time.sleep(_POLL_SECONDS)
            acquired = acquire(fd)
        if not acquired:
            raise LockUnavailable(path, REASON_TIMEOUT, f"waited {timeout_seconds}s")
        try:
            yield
        finally:
            release(fd)
    finally:
        os.close(fd)
