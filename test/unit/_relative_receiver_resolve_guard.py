"""
Runtime sentinel: a ``Path.resolve()``/``Path.absolute()`` call whose RECEIVER
is relative reads the working directory; one whose receiver is absolute does
not. That is a property of the object at call time, not of the call site, so
no static scan can decide it -- ``tools/architecture_fitness.py --ambient``
therefore keys ownership per ``(module, member)`` and inventories every
``resolve()`` site rather than judging it. That is closed against a new
module with no owner (fatal), but a new or mutated relative-receiver
``resolve()``/``absolute()`` *inside* an already-owned module is invisible to
it: the ``(module, member)`` key already matches, so the site is skipped
before fatality is ever asked. This sentinel watches the property the AST
scan cannot see, at the only point it exists: the receiver, at call time.

Modelled directly on ``_real_log_dir_guard.py``. Differs in one respect: that
guard SUPPRESSES the real-directory write it intercepts, because the write
itself is a test-isolation hazard. A relative-receiver ``resolve()`` is not
unsafe to let run -- it reads ``os.getcwd()``, nothing more -- and
suppressing it would risk masking a real behavioural difference in the code
under test. So this guard only RECORDS; every call still passes through to
the real implementation.

Installed from ``test/unit/__init__.py``, before any test module is
imported, for the same ordering guarantee ``_real_log_dir_guard.py``'s module
docstring explains in full: patching at the defining class means any
``from pathlib import Path`` anywhere binds the same patched methods.
Surfaced the same two ways: a dedicated test asserting the registry is empty,
and the process-wide ``atexit`` backstop in ``test/unit/__init__.py``.

WHAT THIS CANNOT SEE
---------------------
A relative-receiver ``resolve()``/``absolute()`` call on a code path this
test suite never executes. A sentinel observes only what runs; an owned
module whose one caller of a newly-relative ``resolve()`` is never exercised
by any test produces no event here, and nothing here can tell the difference
between "no such call exists" and "no test reached it".

Sanctioned sites
-----------------
:data:`SANCTIONED_SITES` names call sites where a relative-receiver call is
intentional, keyed by ``(file suffix, calling function)`` rather than a
broad pattern, with the reason carried alongside the key. A hit there is
counted in :func:`get_sanctioned_hits` and never reaches the leak registry,
so it does not need a matching exemption anywhere else. That is deliberately
NOT the same shape as an exemption list: :func:`get_unhit_sanctioned_sites`
fails the moment a declared site stops firing, e.g. because the call was
removed or the test exercising it was deleted, so an entry cannot go stale
unnoticed the way an open exemption list can.
"""

import functools
import traceback
from pathlib import Path
from typing import Dict, Optional, Tuple

#: Leak events recorded so far: each a human-readable string naming the
#: member, the relative receiver, and a short call-stack excerpt. Empty in
#: the passing case. Cleared only by a test that explicitly verifies the
#: guard itself.
_leak_events = []

#: (file suffix, calling function name) -> why a relative-receiver call there
#: is intentional, not a leak. See "Sanctioned sites" above.
SANCTIONED_SITES: Dict[Tuple[str, str], str] = {
    (
        "toolguard/tools/transcript_harvest.py",
        "transcript_dir_for_project",
    ): (
        "Claude Code's own transcript directory naming derives the project key "
        "from the invoking process's cwd; mirroring that scheme (not toolguard's "
        "path matching) is the documented, tested intent -- see this module's "
        "own docstring."
    ),
}

#: SANCTIONED_SITES keys actually hit so far this run.
_sanctioned_hits = set()

#: Guards against double-installation and keeps the un-patched originals so
#: a second install() call cannot stack wrapper layers.
_installed = False
_original_resolve = None
_original_absolute = None


def get_leak_events():
    """Return a snapshot (copy) of every unsanctioned relative-receiver call recorded so far."""
    return list(_leak_events)


def get_sanctioned_hits():
    """Return a snapshot (copy) of the SANCTIONED_SITES keys hit so far this run."""
    return set(_sanctioned_hits)


def get_unhit_sanctioned_sites():
    """
    Return SANCTIONED_SITES entries never hit this run.

    Empty in the passing case. A declared site landing here means either the
    relative-receiver call it names was removed (rewrite the entry or drop
    it) or the test exercising it did not run -- either way the sanction has
    gone stale and needs a human decision, not a silent pass.
    """
    return {
        site: reason
        for site, reason in SANCTIONED_SITES.items()
        if site not in _sanctioned_hits
    }


def clear_leak_events():
    """
    Clear recorded leak events.

    Exists solely for this guard's self-verification test, which must start
    from a known-empty registry regardless of what ran before it, and must
    not let its own synthetic call linger and fail the atexit-registered
    suite-wide check afterward.
    """
    _leak_events.clear()


def replace_leak_events(events):
    """
    Replace the leak registry contents wholesale.

    Test-only, alongside clear_leak_events(): lets the self-verification test
    save aside whatever was already recorded, run its own synthetic case in
    isolation, then restore the prior state without reaching into the
    module's private list directly.
    """
    _leak_events.clear()
    _leak_events.extend(events)


def _sanctioned_site_of(
    caller: Optional[traceback.FrameSummary],
) -> Optional[Tuple[str, str]]:
    """The SANCTIONED_SITES key matching *caller*'s file and function, or None."""
    if caller is None:
        return None
    filename = caller.filename.replace("\\", "/")
    for site in SANCTIONED_SITES:
        suffix, function_name = site
        if caller.name == function_name and filename.endswith(suffix):
            return site
    return None


def _record(member_name: str, receiver: Path) -> None:
    """
    Classify one relative-receiver call by its immediate caller.

    A caller matching SANCTIONED_SITES is counted in _sanctioned_hits and
    never reaches the leak registry; anything else is an unsanctioned leak,
    appended to _leak_events with a formatted call stack.
    """
    # Frames end at THIS function; the caller of Path.resolve()/absolute()'s
    # wrapper is two hops back (drop this frame, then wrap()'s).
    frames = traceback.extract_stack(limit=10)
    caller = frames[-3] if len(frames) >= 3 else None
    site = _sanctioned_site_of(caller)
    if site is not None:
        _sanctioned_hits.add(site)
        return
    stack = "".join(traceback.format_list(frames[:-1]))
    _leak_events.append(
        f"Path.{member_name}() called on a RELATIVE receiver ({receiver!r}), "
        f"reading the working directory.\n"
        f"Call stack (most recent call last):\n{stack}"
    )


def _wrap(member_name, original):
    """Wrap *original* (``Path.resolve`` or ``Path.absolute``) to record a relative receiver, then call through unconditionally."""

    @functools.wraps(original)
    def wrapper(self, *args, **kwargs):
        if not self.is_absolute():
            _record(member_name, self)
        return original(self, *args, **kwargs)

    return wrapper


def install() -> None:
    """
    Monkeypatch ``pathlib.Path.resolve`` and ``Path.absolute`` with recording
    wrappers.

    Idempotent: a second call is a no-op. Must be called exactly once, from
    test/unit/__init__.py, before any test module is imported.
    """
    global _installed, _original_resolve, _original_absolute
    if _installed:
        return
    _original_resolve = Path.resolve
    _original_absolute = Path.absolute
    Path.resolve = _wrap("resolve", _original_resolve)
    Path.absolute = _wrap("absolute", _original_absolute)
    _installed = True
