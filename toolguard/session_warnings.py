"""The takeover-mode notices: enabled-and-bypassed, or a fail-safe conflict."""

from typing import Optional

from toolguard import error_reporter


def issue_takeover_warning(
    to_stdout: bool = True, conflict_message: Optional[str] = None
) -> None:
    """
    Report the takeover-mode notice via the active error reporter.

    Reported at :data:`~toolguard.error_reporter.SEVERITY_NOTICE`: routine,
    expected on every call while takeover is active, never logged, never
    reaching Claude (see :mod:`toolguard.error_reporter`'s ``_ROUTING``
    table). Not throttled: a live reminder of the current state.

    Args:
        to_stdout: Whether to report the notice at all. Nothing is
            reported when False. The name predates routing through the
            error reporter and is kept for hook.py's call-site
            compatibility; it no longer refers to any stream directly.
        conflict_message: When given, this text is reported instead of the
            enabled/bypassed claim -- used when a cross-level conflict
            fail-safed takeover OFF, where nothing was actually bypassed
            (see :func:`toolguard.hook.describe_takeover_conflict`).
    """
    if not to_stdout:
        return
    if conflict_message is not None:
        error_reporter.report_notice(conflict_message)
        return
    error_reporter.report_notice(
        "Takeover mode is active. Claude's native permission prompts are "
        "bypassed. Toolguard is the sole authority for permission decisions. "
        "If toolguard fails or is misconfigured, blanket allows in native "
        "config will be exposed."
    )
