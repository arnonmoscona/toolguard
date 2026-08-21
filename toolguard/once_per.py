"""
Facade for throttling a warning or an action to at most once per period, per
project -- across processes, not merely within one.

A caller builds ONE named object per throttled thing, once, at module
level::

    DIVERGENCE_WARNING = once_per.day("divergence_warning", "the configuration divergence warning")

then calls ``.done()`` / ``.warn()`` / ``.run()`` on it. Claim mechanics and
storage live in :mod:`toolguard.once_per_store`; a caller never sees a
claim, a scope, a ttl or a store, and never asks for housekeeping -- every
successful claim triggers it internally, itself throttled.
"""

import sys
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

from toolguard import once_per_store
from toolguard.once_per_store import ClaimStatus

_T = TypeVar("_T")

#: The key under which housekeeping claims its own slot. Shared by every
#: :class:`OncePer`, so housekeeping runs once per period rather than once
#: per throttled thing.
_SWEEP_KEY = "periodic_sweep"


class Repeat(Enum):
    """
    Whether repeating the action is safe -- a domain fact about the action,
    stated by the caller. Consulted only when the once-per-period guarantee
    could not be verified for a call.

    Deliberately has no default at the :meth:`OncePer.run` call site: a
    primitive that always proceeded would make "fail open" the accidental
    behaviour of every caller that didn't think about it.
    """

    #: Repeating the action causes no harm (a warning, idempotent housekeeping).
    SAFE = "safe"

    #: Repeating the action is unsafe.
    UNSAFE = "unsafe"


class _Period:
    """
    A throttling period (e.g. "day"). Call it to name a single throttled
    thing for that period: ``day("key", "description") -> OncePer``.

    The period comes from *scope*, which returns a different string once the
    period has rolled over. *retention* is not the period: it is passed
    straight through as the claim's ttl.
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
        """Name a throttled thing for this period."""
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
        self._degraded_notice_sent = False

    def done(self, project: Optional[Path], context: Any = None) -> bool:
        """
        Whether this thing has already been satisfied for *project* this period.

        Read-only, cheap, and claims nothing -- an optimisation letting a
        caller skip expensive analysis before deciding whether to warn/run at
        all.
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
        is unavailable and *repeating* is :attr:`Repeat.UNSAFE`. An *action*
        that itself returns None is therefore indistinguishable from one that
        never ran.
        """
        result = self._claim(project, context)
        if result.status is ClaimStatus.HELD_BY_SOMEONE_ELSE:
            return None
        if result.status is ClaimStatus.UNGUARANTEED:
            self._notify_degraded(result.reason, repeating)
            if repeating is Repeat.UNSAFE:
                return None
        return action()

    def release(self, project: Optional[Path], context: Any = None) -> None:
        """
        Give up this period's claim for *project* early, so a later attempt
        this same period can retry.

        For a caller whose action, after :meth:`run` already claimed the
        slot, determined the attempt should not count against the throttle
        after all. Fails soft, like the underlying store operation.
        """
        once_per_store.release(project, self._key, self._period._scope(context))

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
        """Clear expired claims, at most once per period across every OncePer."""
        sweep_result = once_per_store.claim(
            project,
            _SWEEP_KEY,
            self._period._scope(context),
            ttl=self._period._retention,
        )
        if sweep_result.status is not ClaimStatus.CLAIMED or project is None:
            return
        # reap() also sweeps pre-upgrade marker files under a project's logs
        # directory. Nothing writes those anymore, so this convention-based
        # guess -- never the authoritative TOOLGUARD_LOG_DIR -- is good enough.
        once_per_store.reap(project / "logs")

    def _notify_degraded(self, reason: str, repeating: Repeat) -> None:
        """Print the "throttling unavailable" notice, at most once per instance."""
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
