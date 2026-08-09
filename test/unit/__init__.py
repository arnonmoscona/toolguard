"""
Unit tests for toolguard package modules.
"""

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import toolguard.once_per_store as once_per_store
from test.unit._real_log_dir_guard import REAL_LOGS_DIR, get_leak_events, install
from test.unit._real_once_per_home_guard import (
    REAL_ONCE_PER_DB,
    get_leak_events as get_once_per_home_leak_events,
    install as install_once_per_home_guard,
)

# TOO-19: install the real-logs-dir write guard before any test_*.py module in
# this package is imported. Python guarantees a package's __init__.py runs
# before any of its submodules are imported, including via
# `unittest discover` and `python -m unittest test.unit.<module>` alike -- see
# test/unit/_real_log_dir_guard.py's module docstring for the full mechanism
# and why installing here (rather than in a fixture some tests might skip) is
# what makes this reliable regardless of which tests run or in what order.
install()
# TOO-45 R2: same guarantee, for the shared ~/.toolguard/once_per.db --
# see test/unit/_real_once_per_home_guard.py's module docstring.
install_once_per_home_guard()

# TOO-45 R2: toolguard.once_per_store._STORE_PATH is a fixed module-level
# constant (~/.toolguard/once_per.db), unlike logs_dir, which almost
# every test already passes as a per-test tmp path. Now that
# check_and_warn_divergence/run_auto_migration key their claims by PROJECT
# ROOT rather than logs_dir, they are reachable from ordinary
# toolguard.hook.main() end-to-end tests that never intended to exercise the
# claim store at all (e.g. most of test_hook.py) -- and those tests' real,
# resolved project root is genuinely this repository, so without a default
# redirect they would hit the real store. Point the default at a
# process-wide tmp file so no test needs to opt in just to avoid that;
# tests that verify claim-store semantics themselves still layer their own
# per-test patch.object(once_per_store, "_STORE_PATH", ...) on top of this for
# independent claims between test methods (see test.unit._once_per_isolation
# .IsolatedStoreMixin).
_default_once_per_store_dir = tempfile.mkdtemp(prefix="toolguard-test-once-per-")
once_per_store._STORE_PATH = Path(_default_once_per_store_dir) / "once_per.db"
atexit.register(shutil.rmtree, _default_once_per_store_dir, ignore_errors=True)


def _fail_hard_on_real_log_dir_leak_at_exit() -> None:
    """
    Order-independent backstop: after the ENTIRE process's test run finishes,
    re-check the leak registry and force a nonzero exit with a clear stderr
    banner if anything leaked -- regardless of whether the dedicated
    test_zz_real_log_dir_guard.py test ran, was discovered, or ran before
    every leaking test. This is what actually delivers "reliable regardless
    of test order"; the dedicated test is the readable unittest-report signal
    for the common case.

    Uses os._exit() rather than sys.exit(): verified empirically (TOO-19,
    2026-07-31, Python 3.14.5) that a SystemExit raised from inside an
    atexit callback is caught by CPython's own exit-function runner and
    reported as "Exception ignored in atexit callback" WITHOUT changing the
    process's exit code -- sys.exit() here would make this function look
    like a working backstop while silently not being one. os._exit() bypasses
    that entirely by terminating the process immediately at the C level, so
    stdout/stderr are flushed explicitly first since os._exit() skips normal
    buffered-stream flushing.

    Checks BOTH the real-logs-dir registry and the real-once-per-home
    registry (TOO-45 R2), so a leak in either fails the whole run the same way.
    """
    log_dir_events = get_leak_events()
    once_per_events = get_once_per_home_leak_events()
    if not log_dir_events and not once_per_events:
        return
    if log_dir_events:
        sys.stderr.write(
            "\n\n"
            "=" * 70 + "\nTOO-19 REAL LOG DIR GUARD: the real project logs directory\n"
            f"({REAL_LOGS_DIR}) would have been written to by the test suite.\n"
            "The write was suppressed, but this is a regression -- see\n"
            ".claude/rules/test-config-isolation.md.\n" + "=" * 70 + "\n\n"
        )
        for event in log_dir_events:
            sys.stderr.write(event + "\n")
    if once_per_events:
        sys.stderr.write(
            "\n\n"
            "=" * 70 + "\nTOO-45 REAL CLAIM STORE GUARD: the real\n"
            f"~/.toolguard/once_per.db ({REAL_ONCE_PER_DB}) would have been\n"
            "accessed by the test suite. The access was suppressed, but this is a\n"
            "regression -- see .claude/rules/test-config-isolation.md.\n"
            + "=" * 70
            + "\n\n"
        )
        for event in once_per_events:
            sys.stderr.write(event + "\n")
    # Flush BEFORE os._exit(): os._exit() terminates at the C level and skips
    # Python's normal buffered-stream teardown, so anything not flushed here
    # (including unittest's own already-printed summary) could be lost.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(1)


# This hard-exit backstop is confined to this test-harness package: it lives
# in test/unit/__init__.py, is never imported by toolguard/ itself, and has
# no effect on anything outside a `unittest discover` run of this suite.
# atexit callbacks run at interpreter shutdown, after every test method, every
# tearDown/tearDownModule, and unittest's own result summary have already
# executed -- so by the time this fires, all test code has unconditionally
# finished running; os._exit() here cannot cut off a test or truncate the
# summary that precedes it (stdout/stderr are flushed immediately above, the
# one real hazard of os._exit() bypassing normal buffered-stream teardown).
atexit.register(_fail_hard_on_real_log_dir_leak_at_exit)
