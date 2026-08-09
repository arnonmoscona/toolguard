"""
The takeover-mode-active notice.

The once-per-day throttling facade that used to live here moved to
:mod:`toolguard.once_per` (TOO-45 punch-list #01, conceptual overhaul,
second pass). This notice never lived there for throttling reasons of its
own -- it is explicitly NOT throttled -- only because it used to trigger the
claim store's housekeeping sweep directly; now that housekeeping is internal
to :mod:`toolguard.once_per` and happens automatically as a side effect of
any OTHER throttled thing's successful claim, this module has no reason to
touch the claim store at all.
"""

import sys


def issue_takeover_warning(to_stdout: bool = True) -> None:
    """
    Emit the takeover-mode-active notice to stderr.

    Informational, not actionable (TOO-8 Phase 4): never persisted to any
    toolguard log stream, and never throttled -- it is a live reminder,
    printed on every call, that native prompts are bypassed.

    Args:
        to_stdout: NOTE -- despite the name, this gates writing to STDERR,
            not stdout (the notice goes to ``sys.stderr``). The name is
            retained for backward compatibility with existing callers/tests;
            treat it as "emit the stderr echo". If True (default), the
            notice is written.
    """
    if not to_stdout:
        return
    print(
        "[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are "
        "bypassed. Toolguard is the sole authority for permission decisions. If toolguard "
        "fails or is misconfigured, blanket allows in native config will be exposed.",
        file=sys.stderr,
    )
