"""
Central error/warning/notice reporting for toolguard (TOO-45 punch-list #04).

A caller's whole contract is severity and what happened -- :class:`Reporter`'s
:meth:`~Reporter.notice`, :meth:`~Reporter.warning`, :meth:`~Reporter.fault`.
No stream, no log directory, no audience, no throttling question: this
module owns all of that, in the one routing table below, so the policy
changes in one place instead of at every call site.

:class:`Reporter` (TOO-45 punch-list #04 follow-up) is a plain, directly
constructible class -- ``Reporter(log_dir=...)`` -- holding both the resolved
log directory and the Claude-facing fault buffer as instance state, no
globals. `hook.py` owns exactly one instance for the whole invocation and
threads it explicitly; its `main()` is the only production caller of
`fault()`/`drain_claude_context()`.

The module-level :func:`report_notice`/:func:`report_warning` remain
free functions because four config-layer modules (`config.py`,
`env_config.py`, `auto_migrate.py`, `config_divergence.py`), 8 call sites
deep under `hook.py`, need to reach a reporter without threading one through
every signature up the stack -- including `get_env_config()`, which is
called from tooling and tests all over the repo. That reach problem is why
an ambient registry exists at all: :func:`active` installs the Reporter
those functions resolve, so the registry is one declared, named module-level
binding rather than a hidden global. It goes away if those four modules'
call chains are ever refactored to receive a `Reporter` as an explicit
parameter.
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

    #: Print to stderr when *log_fn_name* is None, or when the log write did
    #: not happen this time (no log directory, or the write itself failed).
    #: Renamed from `stderr` (TOO-45 punch-list #04 fix pass item 6): when
    #: the log write DOES succeed, `error_log._log_entry` echoes to stderr
    #: unconditionally on its own, so this flag does NOT control whether a
    #: successful write is also echoed -- only whether the fallback fires. A
    #: policy that wants to silence a severity's stderr entirely must also
    #: touch `error_log`.
    stderr_fallback: bool
    #: Attribute name on `toolguard.error_log` for this severity's log
    #: stream, looked up via `getattr` at dispatch time rather than bound
    #: here -- so a test's `patch("toolguard.error_log.log_warning", ...)`
    #: still takes effect (fix pass item 7). None for no log stream.
    log_fn_name: Optional[str]
    #: The `[LABEL]` the stderr fallback renders -- matches the label
    #: `error_log` itself would have echoed had the write succeeded, so the
    #: fallback and logged paths render identically (item 1/5). None keeps
    #: the bare-message shape (`notice` has no log stream to match).
    stderr_label: Optional[str]
    #: Whether this severity accumulates into the per-invocation Claude buffer.
    reaches_claude: bool


#: The routing table -- the one thing to read or edit to change policy.
#:
#: `notice` keeps stderr deliberately, and that is TEMPORARY: Arnon's
#: requirement is that nothing should be on stderr under normal conditions,
#: but the takeover-mode notice (not moved here -- see `session_warnings.py`)
#: violates that on every tool call, and changing where the user sees it is a
#: separate, reserved decision. This row is what he edits when he makes it.
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
    process-wide state is touched. ``log_dir=None`` (the default) is the
    safe fallback -- stderr only, no logs, no Claude buffer -- identical to
    "no invocation active" in the pre-refactor design. ``log_dir`` is a
    plain mutable attribute so a caller resolving it in two stages (a coarse
    fallback before its own config is known, then a refined value once it
    is) can update the SAME instance in place rather than needing a second
    one -- see `hook.py::main`.
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
        """Route one report per :data:`_ROUTING`. Never raises into the caller."""
        rule = _ROUTING[severity]
        logged = False
        if rule.log_fn_name is not None and self.log_dir is not None:
            try:
                getattr(error_log, rule.log_fn_name)(
                    message, corrective_steps, self.log_dir
                )
                logged = True
            except Exception as e:
                # Legitimate hand-rolled print (item s4): this IS the bottom
                # of the recursion -- the reporter's own log-writing failure
                # has nowhere else to report to.
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
    Print one report to stderr, in the same shape `error_log`'s own echo
    uses so a reader cannot tell whether the log write happened (item 1/5).

    Args:
        label: The `[LABEL]` to render, or None for the bare-message shape
            (no log stream to match, e.g. `notice`).
        message: The report's message.
        corrective_steps: Suggested corrective actions; only rendered when
            *label* is set and non-empty.
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
    so nothing leaks into the next invocation -- call this once, at a process
    entry point (`hook.py::main`), not deep in resolution logic.

    Args:
        reporter: The :class:`Reporter` the four config-layer call sites
            should report through for the duration of this block.
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
