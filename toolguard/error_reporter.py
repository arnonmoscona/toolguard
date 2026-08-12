"""
Central error/warning/notice reporting for toolguard.

A caller's whole contract is severity and what happened --
:meth:`Reporter.notice`, :meth:`Reporter.warning`, :meth:`Reporter.fault`.
No stream, no log directory, no audience: this module owns all of that, in
the one routing table below (see :data:`_ROUTING`, and :class:`_Routing`'s
``stderr_fallback`` for a limit on what that table alone controls).

:class:`Reporter` is a plain, directly constructible class --
``Reporter(log_dir=...)`` -- holding the resolved log directory and the
Claude-facing fault buffer as instance state, no globals. A process entry
point constructs one instance for its whole invocation and threads it
through explicitly.

The module-level :func:`report_notice`/:func:`report_warning` free
functions exist for callers reached through several layers of call chain,
where threading a ``Reporter`` through every intervening signature is
impractical. :func:`active` installs the ``Reporter`` those two functions
resolve against -- an ambient registry, but a declared, named module-level
binding rather than a hidden global. It goes away if those call chains are
ever refactored to take a ``Reporter`` as an explicit parameter.
"""

import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from toolguard import error_log

#: Routine, expected under normal operation (e.g. a migration's progress/outcome).
SEVERITY_NOTICE = "notice"
#: Something is wrong; toolguard still works.
SEVERITY_WARNING = "warning"
#: Toolguard itself is broken.
SEVERITY_FAULT = "fault"


@dataclass(frozen=True)
class _Routing:
    """One severity's destinations. See the module-level table below."""

    #: Print to stderr when this severity has no log stream, or when the
    #: log call did not run (no `log_dir`) or raised. Does NOT control
    #: stderr on a write that succeeds: `error_log._log_entry` echoes to
    #: stderr unconditionally on that path regardless of this flag -- a
    #: policy that wants to silence a severity's stderr entirely must also
    #: touch `error_log`.
    stderr_fallback: bool
    #: Attribute name on `toolguard.error_log` for this severity's log
    #: function, resolved via `getattr` at dispatch time rather than bound
    #: here, so a test's `patch.object(error_log, "log_warning", ...)` still
    #: takes effect. None means no log stream for this severity.
    log_fn_name: Optional[str]
    #: The `[LABEL]` the stderr fallback renders, matching the label
    #: `error_log` renders on a logged write (see `_print_fallback` for how
    #: closely the two shapes match). None keeps the bare-message shape (no
    #: log stream to match, e.g. `notice`).
    stderr_label: Optional[str]
    #: Whether this severity accumulates into the per-invocation Claude buffer.
    reaches_claude: bool


#: Per-severity routing. Most policy changes are made here -- except stderr
#: on a successful log write, which `error_log` controls unconditionally
#: (see `_Routing.stderr_fallback`).
#:
#: `notice` keeps stderr deliberately -- it has no log stream at all, so
#: `stderr_fallback=False` would send notices nowhere. Do not "tidy" this row
#: to match `warning`/`fault`.
#:
#: It is also the line to edit if the standing goal of nothing-on-stderr-under-
#: normal-conditions is ever acted on: the takeover-mode notice is unthrottled
#: and stderr-only (`session_warnings.issue_takeover_warning`), so in a
#: takeover-mode project it prints on every tool call. Where the user sees it
#: is a reserved decision.
_ROUTING: Dict[str, _Routing] = {
    SEVERITY_NOTICE: _Routing(
        stderr_fallback=True, log_fn_name=None, stderr_label=None, reaches_claude=False
    ),
    SEVERITY_WARNING: _Routing(
        stderr_fallback=True,
        log_fn_name="log_warning",
        stderr_label="WARNING",
        reaches_claude=False,
    ),
    SEVERITY_FAULT: _Routing(
        stderr_fallback=True,
        log_fn_name="log_error",
        stderr_label="ERROR",
        reaches_claude=True,
    ),
}


@dataclass
class Reporter:
    """
    Routes notice/warning/fault reports per :data:`_ROUTING`, for one caller.

    Fully self-contained: construct directly and call its methods, no
    shared/global state is touched. ``log_dir=None`` (the default) is the
    safe fallback for logging -- stderr only, no log files; the Claude
    buffer is separate state and still accumulates ``fault()`` calls
    regardless of ``log_dir``. ``log_dir`` is a plain mutable attribute, not
    fixed at construction, so a caller resolving it in two stages (a coarse
    fallback before its own config is known, then a refined value once it
    is) can update this same instance in place rather than needing a second
    one.
    """

    log_dir: Optional[Path] = None
    _claude_messages: List[str] = field(default_factory=list)

    def notice(self, message: str) -> None:
        """Report a routine, expected condition. See the module-level routing table."""
        self._dispatch(SEVERITY_NOTICE, message, "")

    def warning(self, message: str, corrective_steps: str) -> None:
        """Report that something is wrong but toolguard still works."""
        self._dispatch(SEVERITY_WARNING, message, corrective_steps)

    def fault(self, message: str, corrective_steps: str) -> None:
        """Report that toolguard itself is broken."""
        self._dispatch(SEVERITY_FAULT, message, corrective_steps)

    def drain_claude_context(self) -> Optional[str]:
        """
        Return and clear this reporter's accumulated fault text for Claude.

        None when nothing was reported.
        """
        if not self._claude_messages:
            return None
        text = "\n".join(self._claude_messages)
        self._claude_messages.clear()
        return text

    def _dispatch(self, severity: str, message: str, corrective_steps: str) -> None:
        """Route one report per :data:`_ROUTING`. Swallows a failing log write rather than propagating it."""
        rule = _ROUTING[severity]
        logged = False
        if rule.log_fn_name is not None and self.log_dir is not None:
            try:
                getattr(error_log, rule.log_fn_name)(
                    message, corrective_steps, self.log_dir
                )
                logged = True
            except Exception as e:
                # Deliberately a raw print, not self.fault(...): that would
                # re-enter _dispatch and risk recursing if the log write
                # keeps failing. This is the bottom of the chain.
                print(
                    f"Warning: error reporter failed to write log: {e}",
                    file=sys.stderr,
                )
        if rule.stderr_fallback and not logged:
            _print_fallback(rule.stderr_label, message, corrective_steps)
        if rule.reaches_claude:
            self._claude_messages.append(message)


def _print_fallback(label: Optional[str], message: str, corrective_steps: str) -> None:
    """
    Print one report to stderr, matching the shape `error_log`'s own echo
    uses for a logged write -- except an empty *corrective_steps* omits this
    function's line entirely, where `error_log` always prints it (even
    empty).

    Args:
        label: The `[LABEL]` to render, or None for the bare-message shape
            (no log stream to match, e.g. `notice`).
        message: The report's message.
        corrective_steps: Suggested corrective actions; rendered only when
            *label* is set and *corrective_steps* is non-empty.
    """
    if label is None:
        print(message, file=sys.stderr)
        return
    print(f"[{label}] {message}", file=sys.stderr)
    if corrective_steps:
        print(f"Corrective steps: {corrective_steps}", file=sys.stderr)


#: The Reporter that :func:`report_notice`/:func:`report_warning` resolve --
#: a single, DECLARED module-level binding (see the module docstring for why
#: it exists), mutated ONLY by :func:`active`. Defaults to a plain
#: `Reporter()` (no log dir): the safe fallback when nothing is registered.
_active: Reporter = Reporter()


@contextmanager
def active(reporter: Reporter) -> Iterator[None]:
    """
    Register *reporter* as the target :func:`report_notice`/:func:`report_warning`
    resolve, for the duration of the with-block.

    Restores whatever was active before on exit (including on an exception),
    so nothing leaks into the next invocation -- call this once, near a
    process entry point, not deep in resolution logic.

    Args:
        reporter: The :class:`Reporter` that :func:`report_notice`/
            :func:`report_warning` should resolve to for the duration of
            this block.
    """
    global _active
    previous = _active
    _active = reporter
    try:
        yield
    finally:
        _active = previous


def report_notice(message: str) -> None:
    """Report a routine, expected condition, via the currently active :class:`Reporter`."""
    _active.notice(message)


def report_warning(message: str, corrective_steps: str) -> None:
    """Report that something is wrong, via the currently active :class:`Reporter`."""
    _active.warning(message, corrective_steps)
