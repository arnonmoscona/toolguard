"""
Facade for throttling a warning or action to at most once per period, per
project (TOO-45 punch-list #01, conceptual overhaul, second pass).

``day`` is the single call target for calendar-day throttling. A caller
builds ONE named object per throttled thing, once, at module level::

    DIVERGENCE_WARNING = once_per.day("divergence_warning", "the configuration divergence warning")
    ...
    if not DIVERGENCE_WARNING.warn(project_root, warning_message):
        return DivergenceCheckResult(divergent_patterns=[])

and calls ``.done()`` / ``.warn()`` / ``.run()`` on it. Claim mechanics,
storage, and periodic housekeeping live here and in
:mod:`toolguard.once_per_store`; a caller never sees a claim, a scope, a
ttl, a store, or sqlite -- and never calls anything named "sweep": every
successful claim opportunistically (and internally) triggers housekeeping,
throttled under its own shared key.
"""

import sys
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from toolguard import once_per_store
from toolguard.once_per_store import ClaimStatus

_T = TypeVar("_T")

#: Shared key for the internal housekeeping sweep -- see OncePer._maybe_sweep.
#: No caller ever sees this name; housekeeping happens as a side effect of
#: any other successful claim.
_SWEEP_KEY = "periodic_sweep"


class Repeat(Enum):
    """
    Whether repeating the action is safe -- a domain fact about the action,
    stated by the caller. Consulted only when the once-per-period guarantee
    cannot be verified for a call.

    Deliberately has no default at the :meth:`OncePer.run` call site: a
    primitive that always proceeded would make "fail open" the accidental
    behaviour of every caller that didn't think about it.
    """

    #: Repeating the action causes no harm (a warning, idempotent housekeeping).
    SAFE = "safe"

    #: Repeating the action is unsafe (concurrent, uncoordinated writers).
    UNSAFE = "unsafe"


class _Period:
    """
    A throttling period (e.g. "day"). Call it to name a single throttled
    thing for that period: ``day("key", "description") -> OncePer``.

    ``scope`` takes a *context* argument -- ``None`` today, always -- rather
    than being a zero-arg callable: a period is not inherently "a function of
    wall-clock time" (a future session period would need the calling hook
    invocation's own session id, which arrives as input, not ambient state).
    Threading that context through now, while there is exactly one period and
    three call sites, costs nothing; retrofitting it after a session period
    existed would not.
    """

    def __init__(
        self,
        period_name: str,
        scope: Callable[[Any], str],
        retention: timedelta,
    ):
        self._period_name = period_name
        self._scope = scope
        self._retention = retention

    def __call__(self, key: str, description: str) -> "OncePer":
        """Name a single thing throttled to at most once per this period, per project."""
        return OncePer(self, key, description)


class OncePer:
    """
    One thing -- a warning or an action -- throttled to at most once per
    period, per project. Built via a period factory (e.g. :data:`day`),
    never directly.
    """

    def __init__(self, period: _Period, key: str, description: str):
        self._period = period
        self._key = key
        self._description = description
        #: Whether the "throttling unavailable" notice has already been
        #: printed for THIS thing, this process. Per-instance (TOO-45
        #: punch-list #01 item 8): a shared registry keyed on `key` alone
        #: would let two different periods throttling the same key silently
        #: swallow each other's notice.
        self._degraded_notice_sent = False

    def done(self, project: Optional[Path], context: Any = None) -> bool:
        """
        Whether this thing has already been satisfied for *project* this period.

        Read-only and cheap -- an optimisation letting a caller skip
        expensive analysis before deciding whether to warn/run at all.
        """
        return once_per_store.is_claimed(
            project, self._key, self._period._scope(context)
        )

    def warn(self, project: Optional[Path], message: str, context: Any = None) -> bool:
        """
        Print *message* to stderr at most once per period for *project*.

        Always prints, even when throttling itself is unavailable -- a
        warning that goes unseen is worse than one seen twice.

        Returns True if this call printed *message*, False if this thing was
        already satisfied this period for *project* (nothing printed).
        """
        result = self._claim(project, context)
        if result.status is ClaimStatus.HELD_BY_SOMEONE_ELSE:
            return False
        if result.status is ClaimStatus.UNGUARANTEED:
            self._notify_degraded(result.reason, Repeat.SAFE)
        print(message, file=sys.stderr)
        return True

    def run(
        self,
        project: Optional[Path],
        action: Callable[[], _T],
        *,
        repeating: Repeat,
        context: Any = None,
    ) -> Optional[_T]:
        """
        Run *action* at most once per period for *project*.

        *repeating* states whether running *action* more than once is safe.

        Returns *action*'s result, or None if it did not run -- either this
        thing was already satisfied this period for *project*, or throttling
        is unavailable and *repeating* is :attr:`Repeat.UNSAFE`.
        """
        result = self._claim(project, context)
        if result.status is ClaimStatus.HELD_BY_SOMEONE_ELSE:
            return None
        if result.status is ClaimStatus.UNGUARANTEED:
            self._notify_degraded(result.reason, repeating)
            if repeating is Repeat.UNSAFE:
                return None
        return action()

    def _claim(self, project: Optional[Path], context: Any):
        """Take this thing's claim for the current period, opportunistically sweeping after."""
        result = once_per_store.claim(
            project,
            self._key,
            self._period._scope(context),
            ttl=self._period._retention,
        )
        if result.status is ClaimStatus.CLAIMED:
            self._maybe_sweep(project, context)
        return result

    def _maybe_sweep(self, project: Optional[Path], context: Any) -> None:
        """
        Opportunistically clear expired claims and stale artefacts, throttled
        to once per period across every caller (shared :data:`_SWEEP_KEY`) --
        no caller here needs to know the store accumulates garbage.
        """
        sweep_result = once_per_store.claim(
            project,
            _SWEEP_KEY,
            self._period._scope(context),
            ttl=self._period._retention,
        )
        if sweep_result.status is not ClaimStatus.CLAIMED or project is None:
            return
        # TRANSITIONAL (TOO-45 punch-list #01): reap()'s legacy-artefact
        # sweep still wants a project logs directory, for cleanup of
        # pre-upgrade per-project marker files only -- nothing writes those
        # anymore, so this convention-based guess (never the authoritative
        # TOOLGUARD_LOG_DIR) is good enough. Delete this whole path once
        # enough time has passed that no such marker file could still exist.
        once_per_store.reap(project / "logs")

    def _notify_degraded(self, reason: str, repeating: Repeat) -> None:
        """Print the "throttling unavailable" notice for this thing, once per process."""
        if self._degraded_notice_sent:
            return
        self._degraded_notice_sent = True
        if repeating is Repeat.UNSAFE:
            consequence = "so it will be skipped until this is resolved"
        else:
            consequence = "so it may run more often than intended"
        print(
            f"[TOOLGUARD WARNING] {self._description} cannot be limited to once "
            f"per {self._period._period_name} right now ({reason}), {consequence}.",
            file=sys.stderr,
        )


#: Calendar-day period: at most once per day, per project. Call it to name a
#: throttled thing: ``once_per.day("key", "description")``.
day = _Period("day", lambda context: once_per_store.day_scope(), timedelta(days=7))
