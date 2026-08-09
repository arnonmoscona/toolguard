"""
Permission migration script for toolguard.

The ``toolguard-migrate`` console script: a thin CLI wrapper (argument parsing
and project-root resolution) around :func:`toolguard.permission_migration.migrate`,
which does the actual work of merging permission patterns from Claude's
``settings.local.json`` into toolguard configuration files (TOML or JSON),
with timestamped backups and a dry-run preview mode.

TOO-45 R5b split the migration LOGIC out of this module into
:mod:`toolguard.permission_migration`: this script is a console-script entry
point (declared in ``pyproject.toml``'s ``[project.scripts]``), and R5's
leafness predicate requires that no entry point also be a library other
modules import for their logic. Before the split, :mod:`toolguard.
auto_migrate`, :mod:`toolguard.tools.installer`, and
:mod:`toolguard.tools.rule_apply` all imported functions from this module
directly -- see :mod:`toolguard.permission_migration`'s docstring for the
full rationale.
"""

import argparse
import sys
from pathlib import Path

from toolguard.config import find_project_root
from toolguard.permission_migration import migrate


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Migrate permissions from settings.local.json to toolguard config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without making them
  toolguard-migrate --dry-run

  # Migrate with default settings
  toolguard-migrate

  # Migrate without auto-sorting
  toolguard-migrate --no-sort

  # Use custom backup directory
  toolguard-migrate --backup-dir /tmp/backups

Note: this module can also be run as `uv run python -m
toolguard.scripts.migrate_permissions`, but only from inside a local toolguard
checkout -- after `uv tool install`, prefer the `toolguard-migrate` console
script shown above, which works from any directory.
        """,
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )

    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Do not sort patterns after migration (default: auto-sort)",
    )

    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for backup files (default: logs/config-backups/)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the migration script.

    Resolves the project root, then delegates all actual migration work to
    :func:`toolguard.permission_migration.migrate`, converting its
    :class:`~toolguard.permission_migration.MigrationOutcome` to a shell
    exit code here -- the only place in the call chain that should (TOO-45
    punch-list #15 final item).

    Returns:
        1 if the project root itself cannot be resolved. Otherwise
        :func:`~toolguard.permission_migration.migrate`'s outcome's
        ``.exit_code``: 0 on success, 1 on error, or 3 if another migration
        already holds this project's lock.
    """
    args = parse_args()

    try:
        project_root = find_project_root()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return migrate(
        project_root=project_root,
        dry_run=args.dry_run,
        auto_sort=not args.no_sort,
        backup_dir=args.backup_dir,
    ).exit_code


if __name__ == "__main__":
    sys.exit(main())
