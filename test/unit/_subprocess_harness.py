"""
Shared cross-process test harness (TOO-45 punch-list #15 fix pass, item 6).

Extracted from four independent copies of the same pattern
(test_once_per_store.py, test_config_divergence.py, test_file_lock.py,
test_migration.py): spawn a ``python -c <script>`` child with this repo as
its working directory, and poll a marker/barrier file with a monotonic
deadline instead of asserting on a guessed ``sleep()`` duration. The child
scripts themselves stay per-test -- they run in a separate process, so there
is nothing here to share beyond launching them and watching the filesystem.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Sequence

#: test/unit/_subprocess_harness.py -> parents[0]=test/unit, [1]=test, [2]=repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]

#: Default interval between filesystem polls below.
DEFAULT_POLL_SECONDS = 0.01

#: Default wait before giving up on a marker or barrier.
DEFAULT_TIMEOUT_SECONDS = 10.0


def run_child(
    script: str, *args: str, env: Optional[Dict[str, str]] = None
) -> "subprocess.Popen[str]":
    """Launch ``python -c script *args`` as a child process, cwd=repo root."""
    return subprocess.Popen(
        [sys.executable, "-c", script, *args],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_path(
    path: Path,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_SECONDS,
) -> bool:
    """Poll until *path* exists or *timeout* elapses; True if it appeared."""
    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(poll_interval)
    return path.exists()


def release_barrier_when_ready(
    barrier: Path,
    ready_markers: Sequence[Path],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    poll_interval: float = DEFAULT_POLL_SECONDS,
) -> bool:
    """
    Touch *barrier* only once every path in *ready_markers* exists.

    Replaces guessing a fixed ``sleep()`` before releasing a barrier, which
    degrades silently to a sequential (non-concurrent) run -- and still
    passes -- if any child is slow to start. Each child must touch its own
    ready marker immediately before entering its busy-wait loop on
    *barrier*; this waits for ALL of them before releasing it, so release is
    deterministic rather than a timing guess.

    Returns:
        True if every marker appeared and the barrier was touched. False
        (barrier NOT touched) if *timeout* elapsed first -- callers should
        assert this rather than silently letting the run continue, since a
        missing marker means a child never reached the wait loop at all.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(marker.exists() for marker in ready_markers):
            barrier.touch()
            return True
        time.sleep(poll_interval)
    return False
