"""The takeover-mode notices: enabled-and-bypassed, or a fail-safe conflict."""

import sys
from typing import Optional


def issue_takeover_warning(
    to_stdout: bool = True, conflict_message: Optional[str] = None
) -> None:
    """
    Emit a takeover-mode notice to stderr.

    Not throttled and never written to a toolguard log stream: a live
    reminder of the current state.

    Args:
        to_stdout: Despite the name, gates the write to ``sys.stderr``.
            Nothing is emitted when False.
        conflict_message: When given, this text is printed instead of the
            enabled/bypassed claim -- used when a cross-level conflict
            fail-safed takeover OFF, where nothing was actually bypassed
            (see :func:`toolguard.hook.describe_takeover_conflict`).
    """
    if not to_stdout:
        return
    if conflict_message is not None:
        print(f"[TOOLGUARD WARNING] {conflict_message}", file=sys.stderr)
        return
    print(
        "[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are "
        "bypassed. Toolguard is the sole authority for permission decisions. If toolguard "
        "fails or is misconfigured, blanket allows in native config will be exposed.",
        file=sys.stderr,
    )
