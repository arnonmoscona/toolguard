"""
Migration safety pre-flight: combine the project-root and working-tree gates.

Promoting a rule up the hierarchy is only safe when BOTH conditions hold:

* the project boundary is unambiguous -- a version-control root or an explicit
  override (:func:`toolguard.tools.project_root.resolve_project_root`), and
* the working tree is clean, so the migration edit is reviewable and revertible
  (:func:`toolguard.tools.working_tree.working_tree_status`).

This composes those two pure primitives into one structured, decision-free
result so the maintenance skill consults a single tested entry point rather than
re-deriving the combined rule itself.  Read-only; nothing is written.
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
        """
        Human-readable reasons the migration is not safe (empty when safe).

        Reports the project-root reason when the boundary is unresolved;
        otherwise reports the working-tree problem (non-repo or uncommitted
        changes), naming a few dirty paths.
        """
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
                "" if len(tree.dirty_paths) <= 5 else f" (+{len(tree.dirty_paths) - 5} more)"
            )
            return [
                f"The working tree has uncommitted changes ({preview}{extra}); "
                "commit or stash them first so the migration stays reviewable and "
                "revertible."
            ]
        return []

    @property
    def is_safe(self) -> bool:
        """Whether the migration may proceed without escalating to the user."""
        return not self.blockers


def migration_preflight(
    start_dir: Optional[Path] = None,
    *,
    override: Optional[Path] = None,
) -> MigrationPreflight:
    """
    Run the combined migration safety pre-flight.

    Resolves the project boundary and, when a root is found, inspects its working
    tree.  Pure and decision-free: the ask/refuse policy belongs to the caller.

    Args:
        start_dir: Directory to resolve from (defaults to the current directory).
        override: An explicit, previously-persisted project root.

    Returns:
        A :class:`MigrationPreflight` combining both gates.
    """
    root = resolve_project_root(start_dir, override=override)
    tree = working_tree_status(root.root) if root.root is not None else None
    return MigrationPreflight(root=root, working_tree=tree)
