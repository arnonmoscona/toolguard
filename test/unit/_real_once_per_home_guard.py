"""
Structural regression guard (TOO-45 R2): the developer's real
``~/.toolguard/once_per.db`` must never be touched by the test suite.

Same problem, different shape from ``_real_log_dir_guard.py``
-------------------------------------------------------------
That guard wraps functions whose destination is an ARGUMENT (``log_dir`` /
``logs_dir``), so it can inspect the call and compare. The claim store
lives at ``~/.toolguard/``, and ``claim``/``is_claimed``/``release`` take no
directory argument at all; a test that forgets to isolate it (e.g. via
``patch.object(once_per_store, "_STORE_PATH", tmp_path)``, the same technique
:mod:`toolguard.tools.decision_ledger`'s tests use for its own
``~/.toolguard``-anchored constant) would silently read and write the real
file.

So this guard checks a different thing: at CALL TIME, does the store path
that would ACTUALLY be opened resolve to the real one? It calls
``once_per_store._resolve_store_path()`` -- the exact function
``_connect``/``_connect_existing`` use -- rather than reading
``once_per_store._STORE_PATH`` directly. That distinction matters:
``_STORE_PATH`` is an ``Optional[Path]`` OVERRIDE FLAG (``None`` means "use
the default"), not the path itself, so comparing it directly against the
real path would be comparing the wrong thing whenever no override is set.
If a test patched the override, the resolved path differs and the call
passes through unchanged; if a test forgot, resolution falls through to the
real default and the call is intercepted -- recorded as a leak and answered
with the same fail-soft value the real function would return on a genuine
storage error, so a regression can never land a read or write on disk.

Guards ``claim``, ``is_claimed``, ``release``, and ``reap`` (its
``~/.toolguard/``-facing expiry sweep only -- its ``logs_dir``-facing legacy
sweep is already covered by ``_real_log_dir_guard.py``, and the two compose
cleanly since each checks an independent condition).

Installed from ``test/unit/__init__.py``, before any test module is
imported, for the same ordering guarantee ``_real_log_dir_guard.py``'s
module docstring explains in full. Surfaced the same two ways: a dedicated
test in ``test_zz_real_log_dir_guard.py`` and a process-wide ``atexit``
backstop.
"""

import functools
import traceback
from pathlib import Path

import toolguard.once_per_store as once_per_store
from toolguard.once_per_store import ClaimResult, ClaimStatus

#: The real developer's claim store -- resolved once, before any test
#: can set toolguard.once_per_store._STORE_PATH's override. Goes through
#: _resolve_store_path() rather than reading _STORE_PATH directly, since
#: the latter is an override flag (None by default), not the path itself.
REAL_ONCE_PER_DB = once_per_store._resolve_store_path()

#: Fail-soft value claim() reports when this guard intercepts an unisolated
#: call -- UNGUARANTEED, matching what a genuine storage error would report.
_GUARD_CLAIM_RESULT = ClaimResult(ClaimStatus.UNGUARANTEED, "blocked by test guard")

_leak_events = []

_installed = False


def get_leak_events():
    """Return a snapshot (copy) of every real-store-access attempt recorded so far."""
    return list(_leak_events)


def clear_leak_events():
    """Clear recorded leak events (self-verification test support)."""
    _leak_events.clear()


def replace_leak_events(events):
    """Replace the leak registry contents wholesale (self-verification test support)."""
    _leak_events.clear()
    _leak_events.extend(events)


def _record_leak(func) -> None:
    """Append a formatted leak event describing *func*'s attempted real-store access."""
    stack = "".join(traceback.format_stack(limit=10)[:-1])
    _leak_events.append(
        f"{func.__module__}.{func.__qualname__} attempted to use the REAL "
        f"claim store ({REAL_ONCE_PER_DB}) -- toolguard.once_per_store._STORE_PATH "
        "was not isolated for this test.\n"
        f"Call stack (most recent call last):\n{stack}"
    )


def _is_real_store() -> bool:
    """Whether the path a store call would ACTUALLY open right now is the real one."""
    if REAL_ONCE_PER_DB is None:
        return False
    resolved = once_per_store._resolve_store_path()
    if resolved is None:
        return False
    try:
        return Path(resolved).resolve() == REAL_ONCE_PER_DB.resolve()
    except OSError:
        return False


def _guard(func, fail_soft_value):
    """Wrap *func*, short-circuiting to *fail_soft_value* when unisolated."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if _is_real_store():
            _record_leak(func)
            return fail_soft_value
        return func(*args, **kwargs)

    return wrapper


def install() -> None:
    """
    Monkeypatch once_per_store's store-touching functions with guarded wrappers.

    Idempotent: a second call is a no-op. Must be called exactly once, from
    test/unit/__init__.py, before any test module is imported.
    """
    global _installed
    if _installed:
        return
    once_per_store.claim = _guard(once_per_store.claim, _GUARD_CLAIM_RESULT)
    once_per_store.is_claimed = _guard(once_per_store.is_claimed, False)
    once_per_store.release = _guard(once_per_store.release, None)
    once_per_store.reap = _guard(once_per_store.reap, None)
    _installed = True
