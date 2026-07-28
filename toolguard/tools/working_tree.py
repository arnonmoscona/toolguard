"""
Working-tree cleanliness guard for the apply/migrate safety gate.

Applying a config change onto a DIRTY git working tree mixes the tool's edits
with the user's uncommitted work, making the change hard to review and hard to
revert.  This module reports the working-tree state as a structured,
decision-free result; the skill/CLI layer decides whether to proceed, warn, or
refuse.  Read-only: it only ever runs ``git status``.

This mirrors :mod:`toolguard.tools.project_root` -- a pure deterministic safety
primitive that classifies the situation and leaves the ask/refuse policy to the
caller.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

# Bound the git subprocess so a hung/networked git can never stall the gate.
_GIT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class WorkingTreeStatus:
    """
    Structured git working-tree state for the apply/migrate gate.

    Attributes:
        is_git_repo: Whether ``root`` is inside a git work tree (``git status``
            succeeded).  ``False`` when git is missing or the path is not a repo.
        is_clean: Whether the work tree has no uncommitted changes.  Only
            meaningful when ``is_git_repo`` is ``True``.
        dirty_paths: The changed paths reported by ``git status --porcelain``
            (status prefix stripped), in git's order; empty when clean or non-repo.
    """

    is_git_repo: bool
    is_clean: bool
    dirty_paths: Tuple[str, ...]

    @property
    def is_safe_to_apply(self) -> bool:
        """
        Whether the gate may write changes without escalating.

        Only a git work tree with no uncommitted changes is safe: a dirty tree
        would entangle the tool's edits with the user's work, and a non-repo has
        no revert safety net.  Anything else must be escalated (warn/refuse) by
        the caller.
        """
        return self.is_git_repo and self.is_clean


def working_tree_status(root: Path) -> WorkingTreeStatus:
    """
    Report the git working-tree state at ``root`` via ``git status --porcelain``.

    This is read-only and never modifies anything.  A non-zero git exit, a
    missing git binary, or a subprocess error is treated as "not a git repo".

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

    # Porcelain v1 lines are ``XY <path>`` (3-char status prefix); keep the path.
    dirty = tuple(line[3:] if len(line) > 3 else line for line in lines)
    return WorkingTreeStatus(is_git_repo=True, is_clean=False, dirty_paths=dirty)
