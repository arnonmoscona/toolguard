"""
Migration safety pre-flight: combine the project-root and working-tree gates.

A migration is safe only when BOTH hold -- the project boundary resolved
unambiguously, and that root is a git work tree with no uncommitted changes, so
the edit stays reviewable and revertible.

Structured and decision-free: the ask/refuse policy belongs to the caller.
Read-only, but not pure -- resolving the boundary reads the filesystem and the
cleanliness check runs ``git status``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from toolguard.tools.project_root import ProjectRootResolution, resolve_project_root
from toolguard.tools.working_tree import WorkingTreeStatus, working_tree_status


@dataclass(frozen=True)
class MigrationPreflight:
    """
    Combined project-root + working-tree safety verdict for a migration.

    Attributes:
        root: The project-root resolution.
        working_tree: The working-tree status at the resolved root, or ``None``
            when no root could be resolved (so there was nothing to inspect).
    """

    root: ProjectRootResolution
    working_tree: Optional[WorkingTreeStatus]

    @property
    def blockers(self) -> List[str]:
        """At most one human-readable reason the migration is unsafe; empty when safe."""
        if not self.root.safe_to_migrate:
            return [self.root.reason]

        tree = self.working_tree
        if tree is None or not tree.is_git_repo:
            return [
                "The resolved project root is not a git work tree, so a migration "
                "could not be reviewed or reverted; put it under version control "
                "first."
            ]
        if not tree.is_clean:
            preview = ", ".join(tree.dirty_paths[:5])
            extra = (
                ""
                if len(tree.dirty_paths) <= 5
                else f" (+{len(tree.dirty_paths) - 5} more)"
            )
            return [
                f"The working tree has uncommitted changes ({preview}{extra}); "
                "commit or stash them first so the migration stays reviewable and "
                "revertible."
            ]
        return []

    @property
    def is_safe(self) -> bool:
        """Whether the migration may proceed -- no blockers."""
        return not self.blockers


def migration_preflight(
    start_dir: Optional[Path] = None,
    *,
    override: Optional[Path] = None,
) -> MigrationPreflight:
    """
    Run the combined migration safety pre-flight.

    Args:
        start_dir: Directory to resolve from (defaults to the current directory).
        override: An explicit project root to use instead of resolving one.

    Returns:
        A :class:`MigrationPreflight` combining both gates.
    """
    root = resolve_project_root(start_dir, override=override)
    tree = working_tree_status(root.root) if root.root is not None else None
    return MigrationPreflight(root=root, working_tree=tree)
