"""
Structural regression guard: the developer's real logs/ directory must
never receive a write from the test suite.

A checklist alone (``.claude/rules/test-config-isolation.md``) did not
prevent this leak the first time -- three tests missed it independently, one
of them despite already using the sanctioned isolation mixin, because that
mixin's scope covered ``toolguard.config``'s three discovery anchors and not
``toolguard.env_config``'s separate, fourth one. Prose guidance is not
self-enforcing; this module is the enforcement.

A single test that snapshots the real ``logs/`` directory before the suite
and diffs it after was considered and rejected: a same-process test can only
observe state as of when it runs, and nothing guarantees such a test runs
strictly first and strictly last under ``unittest discover``'s ordering.

Instead this module intercepts the leak at its only possible source: every
toolguard code path that can write into the real project logs/ directory
does so by calling one of a small, fixed set of functions
(``log_writer.log_command``, ``log_writer.log_discovery``,
``error_log.log_conflict``, ``error_log.log_error``, ``error_log.log_warning``,
``once_per_store.reap``) with a ``log_dir``/``logs_dir`` (directly, or -- for
``log_command`` specifically -- via a ``config["log_dir"]`` dict, the shape
``toolguard.hook.main()`` uses). ``install()`` wraps each of these, at their
DEFINING module, with a guard that:

1. Detects when the resolved ``log_dir`` is the real repo's ``logs/``
   directory (or a path under it).
2. When detected, does NOT call the real function at all -- this guard IS
   the backstop, not merely a detector -- and instead records the offending
   call (function, resolved path, a short call-stack excerpt) in a
   module-level registry.
3. Otherwise calls straight through with no observable difference.

Patching happens at the DEFINING module rather than at each importer, so
that a later ``from toolguard.log_writer import log_command`` (e.g. inside
``toolguard/hook.py``) binds directly to the guarded wrapper -- which is why
``install()`` must run, from ``test/unit/__init__.py``, before any test
module (and therefore before ``toolguard.hook``) is ever imported. A
test-level ``patch("toolguard.hook.log_command")`` simply replaces the
guarded wrapper with a ``Mock``, which is harmless.

The registry is surfaced two ways, both order-independent: a dedicated test
in ``test_zz_real_log_dir_guard.py`` asserts it is empty, and
``test/unit/__init__.py`` also registers an ``atexit`` hook that re-checks it
once after the ENTIRE process's test run and force-exits nonzero if anything
leaked -- the guarantee that does not depend on test discovery order.
"""

import functools
import inspect
import traceback
from pathlib import Path

import toolguard.error_log as error_log
import toolguard.log_writer as log_writer
import toolguard.once_per_store as once_per_store

#: The real repository's logs/ directory -- computed once, from this file's
#: own location, so it works regardless of the process's cwd or invocation
#: style (`unittest discover`, `python -m unittest test.unit.X`, etc.).
#: parents[0]=test/unit, parents[1]=test, parents[2]=repo root.
REAL_LOGS_DIR = (Path(__file__).resolve().parents[2] / "logs").resolve()

#: Leak events recorded so far: each a human-readable string naming the
#: guarded function, the path it tried to write to, and a short call-stack
#: excerpt. Empty in the passing case. Cleared only by tests that explicitly
#: verify the guard itself (see test_zz_real_log_dir_guard.py).
_leak_events = []

#: Guards against double-installation (install() must only wrap each
#: function once; re-running it, e.g. if a module were ever re-imported,
#: must not stack N guard layers on top of each other).
_installed = False


def get_leak_events():
    """Return a snapshot (copy) of every real-logs-dir write attempt recorded so far."""
    return list(_leak_events)


def clear_leak_events():
    """
    Clear recorded leak events.

    Exists solely for test_zz_real_log_dir_guard.py's self-verification test,
    which must start from a known-empty registry regardless of what ran
    before it, and must not let its own synthetic leak linger and fail the
    atexit-registered suite-wide check afterward.
    """
    _leak_events.clear()


def replace_leak_events(events):
    """
    Replace the leak registry contents wholesale.

    Test-only, alongside clear_leak_events(): lets
    test_zz_real_log_dir_guard.py's self-verification test save aside
    whatever was already recorded, run its own synthetic leak in isolation,
    then restore the prior state -- without reaching into the module's
    private list directly.
    """
    _leak_events.clear()
    _leak_events.extend(events)


def _is_real_logs_path(candidate) -> bool:
    """Return True if *candidate* resolves to REAL_LOGS_DIR or a path under it."""
    if candidate is None:
        return False
    try:
        resolved = Path(candidate).resolve()
    except TypeError, ValueError, OSError:
        return False
    return resolved == REAL_LOGS_DIR or REAL_LOGS_DIR in resolved.parents


def _record_leak(func, log_dir) -> None:
    """Append a formatted leak event describing *func*'s attempted write to *log_dir*."""
    stack = "".join(traceback.format_stack(limit=10)[:-1])
    _leak_events.append(
        f"{func.__module__}.{func.__qualname__} attempted to resolve log_dir="
        f"{log_dir!r} to the REAL project logs directory ({REAL_LOGS_DIR}).\n"
        f"Call stack (most recent call last):\n{stack}"
    )


def _guard_simple_log_dir_arg(func, param_name="log_dir"):
    """
    Wrap a function whose log-directory argument is checked directly.

    *param_name* accommodates callables that don't use ``log_dir`` as the
    parameter name (e.g. :mod:`toolguard.once_per_store`'s ``logs_dir``).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
        log_dir = bound.arguments.get(param_name)
        if _is_real_logs_path(log_dir):
            _record_leak(func, log_dir)
            return None
        return func(*args, **kwargs)

    return wrapper


def _guard_log_command(func):
    """
    Wrap ``log_command`` specifically: its ``log_dir`` can arrive either
    directly via the ``log_dir`` parameter or indirectly via
    ``config["log_dir"]`` -- the shape ``toolguard.hook.main()`` actually
    uses on every call site (it always passes ``config=env_config``, never
    ``log_dir=`` directly).
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bound = inspect.signature(func).bind_partial(*args, **kwargs)
        candidates = [bound.arguments.get("log_dir")]
        config = bound.arguments.get("config")
        if isinstance(config, dict):
            candidates.append(config.get("log_dir"))
        for candidate in candidates:
            if _is_real_logs_path(candidate):
                _record_leak(func, candidate)
                return None
        return func(*args, **kwargs)

    return wrapper


def install() -> None:
    """
    Monkeypatch toolguard's log-writing entry points with guarded wrappers.

    Idempotent: a second call is a no-op. Must be called exactly once, from
    test/unit/__init__.py, before any test module is imported -- see the
    module docstring above for why that ordering is guaranteed and why it
    matters.
    """
    global _installed
    if _installed:
        return
    log_writer.log_command = _guard_log_command(log_writer.log_command)
    log_writer.log_discovery = _guard_simple_log_dir_arg(log_writer.log_discovery)
    for name in ("log_conflict", "log_error", "log_warning"):
        setattr(error_log, name, _guard_simple_log_dir_arg(getattr(error_log, name)))
    # reap() is the only once_per_store function still keyed by a project
    # logs_dir; claim/is_claimed/release use the shared ~/.toolguard/ store
    # and are guarded separately, by _real_once_per_home_guard.py.
    once_per_store.reap = _guard_simple_log_dir_arg(
        once_per_store.reap, param_name="logs_dir"
    )
    _installed = True
