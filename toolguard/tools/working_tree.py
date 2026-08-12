"""
Working-tree cleanliness guard for the apply/migrate safety gate.

Applying a config change onto a DIRTY git working tree mixes the tool's edits
with the user's uncommitted work, making the change hard to review and hard to
revert.  This module reports the working-tree state as a structured,
decision-free result; the caller decides whether to proceed, warn, or refuse.
Read-only: it only ever runs ``git status``.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

#: Bound on the ``git status`` subprocess so a hung git cannot stall the gate.
#: :exc:`subprocess.TimeoutExpired` is a :exc:`subprocess.SubprocessError`, so a
#: timed-out git reports as "not a git repo" -- fail-safe, never as clean.
_GIT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class WorkingTreeStatus:
    """
    Structured git working-tree state for the apply/migrate gate.

    Attributes:
        is_git_repo: Whether ``git status`` succeeded at ``root``.  ``False``
            when git is missing, errored, or the path is not a repo.
        is_clean: Whether the work tree has no uncommitted changes.  Only
            meaningful when ``is_git_repo`` is ``True``.
        dirty_paths: ``git status --porcelain`` lines with the 3-character
            status prefix stripped, in git's order; empty when clean or
            non-repo.  These are git's own strings rather than plain paths: a
            rename reads ``old -> new``, and an untracked directory collapses
            to a single trailing-slash entry covering everything beneath it.
    """

    is_git_repo: bool
    is_clean: bool
    dirty_paths: Tuple[str, ...]

    @property
    def is_safe_to_apply(self) -> bool:
        """
        Whether the gate may write changes without escalating.

        A non-repo counts as unsafe, not as trivially clean: there is no revert
        safety net.
        """
        return self.is_git_repo and self.is_clean


def working_tree_status(root: Path) -> WorkingTreeStatus:
    """
    Report the git working-tree state at ``root`` via ``git status --porcelain``.

    A non-zero git exit, a missing git binary and a subprocess error are all
    reported alike, as "not a git repo".

    Args:
        root: Directory to inspect (typically the resolved project root).

    Returns:
        A :class:`WorkingTreeStatus` describing the work tree.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return WorkingTreeStatus(is_git_repo=False, is_clean=False, dirty_paths=())

    if result.returncode != 0:
        # Not a git repository (exit 128) or git otherwise unavailable.
        return WorkingTreeStatus(is_git_repo=False, is_clean=False, dirty_paths=())

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return WorkingTreeStatus(is_git_repo=True, is_clean=True, dirty_paths=())

    # Porcelain v1 prefixes every entry with two status characters and a space.
    dirty = tuple(line[3:] if len(line) > 3 else line for line in lines)
    return WorkingTreeStatus(is_git_repo=True, is_clean=False, dirty_paths=dirty)
