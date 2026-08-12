"""The takeover-mode-active notice."""

import sys


def issue_takeover_warning(to_stdout: bool = True) -> None:
    """
    Emit the takeover-mode-active notice to stderr.

    Not throttled and never written to a toolguard log stream: a live reminder
    that native prompts are bypassed.

    Args:
        to_stdout: Despite the name, gates the write to ``sys.stderr``.
            Nothing is emitted when False.
    """
    if not to_stdout:
        return
    print(
        "[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are "
        "bypassed. Toolguard is the sole authority for permission decisions. If toolguard "
        "fails or is misconfigured, blanket allows in native config will be exposed.",
        file=sys.stderr,
    )
