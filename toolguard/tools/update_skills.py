"""
``toolguard-update-skills``: refresh the user-scope bundled skills in place.

Copies from the skills force-included into this installation, so the skills that
land are the ones belonging to the toolguard build that is actually running --
no network, no git, no version to keep in step by hand. That is the whole point
of the command: ``uv tool upgrade toolguard`` replaces the package and leaves the
installed skills untouched, which is how a fixed skill kept shipping unfixed
(0.6.0 release notes).

The copy, the timestamped backup and the install-journal entries are
:func:`toolguard.tools.installer.cmd_install_skills`; this module only decides
what to hand it.
"""

import argparse
import sys
from types import SimpleNamespace

from toolguard.tools.installer import (
    InstallerError,
    bundle_root,
    bundled_skill_names,
    cmd_install_skills,
)

_DESCRIPTION = """\
Force-refresh toolguard's bundled skills at the USER scope (~/.claude/skills/)
from the copy shipped inside this toolguard installation.

Always overwrites, because an unchanged copy is the failure this command exists to
fix. Each replaced skill is backed up whole into ~/.toolguard/backups/ first and
recorded in the install journal, so the previous version is recoverable.

Run it after `uv tool upgrade toolguard`. To install skills before toolguard is
installed, or into a project scope, use `toolguard-install install-skills`.
"""


def main(argv=None) -> int:
    """
    Refresh the user-scope bundled skills from this installation.

    Returns:
        ``0`` on success, ``1`` if the bundled skills could not be read or copied.
    """
    parser = argparse.ArgumentParser(
        prog="toolguard-update-skills",
        description=_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the bundled skills and where they would be written, then exit",
    )
    args = parser.parse_args(argv)

    try:
        root = bundle_root()
        names = bundled_skill_names(root)
        if args.list:
            print(f"bundled skills, from {root}:")
            for name in names:
                print(f"  {name}")
            return 0
        return cmd_install_skills(
            SimpleNamespace(
                scope="user", project_dir=None, source=str(root), force=True
            )
        )
    except InstallerError as exc:
        print(f"toolguard-update-skills: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
