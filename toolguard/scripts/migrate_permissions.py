"""
The ``toolguard-migrate`` console script.

A thin CLI wrapper -- argument parsing, project-root resolution, exit code --
around :func:`toolguard.permission_migration.migrate`, which merges permission
patterns from Claude's ``settings.local.json`` into toolguard configuration
files with timestamped backups and a dry-run preview mode.

Keep the logic on the other side of that call: as an entry point, this module
must stay a leaf that nothing imports for its behaviour.
"""

import argparse
import sys
from pathlib import Path

from toolguard.config import find_project_root
from toolguard.permission_migration import migrate


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
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
    Resolve the project root and run the migration.

    This is where a :class:`~toolguard.permission_migration.MigrationOutcome`
    becomes a shell exit code, and it should stay the only such place.

    Returns:
        1 if the project root itself cannot be resolved. Otherwise the
        outcome's ``.exit_code``: 0 on success, 1 on error, 3 if another
        migration already holds this project's lock, 4 if exclusive access
        could not be guaranteed for any other reason.
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
