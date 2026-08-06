"""
Update checker for toolguard (TOO-16).

The ``toolguard-update-check`` console script: a thin CLI wrapper (argument
parsing and exit-code plumbing) around :func:`toolguard.install_update._check`,
which does the actual install-kind detection and remote-commit comparison.
Exit codes (a stable contract relied on by the shell snippets in the docs):

* ``0`` -- up to date (installed commit == remote HEAD).
* ``1`` -- update available (installed commit != remote HEAD).
* ``2`` -- could not determine: install kind is unknown, or the remote is
  unreachable (offline). Never blocks, never hangs.

TOO-45 R5c split the detection/comparison LOGIC out of this module into
:mod:`toolguard.install_update`: this script is a console-script entry point
(declared in ``pyproject.toml``'s ``[project.scripts]``), and R5's leafness
predicate requires that no entry point also be a library other modules
import for their logic. Before the split, :mod:`toolguard.tools.installer`
imported ``InstallKind``, ``detect_install``, ``local_remote_head``, and
``remote_head`` from this module directly -- see
:mod:`toolguard.install_update`'s docstring for the full rationale.
"""

import argparse
import sys

from toolguard.install_update import _check


def main() -> None:
    """
    Console-script entry point for ``toolguard-update-check``.

    Detects the install kind (git, local, or unknown) and compares the installed
    state against the remote. Exits with the code described in the module
    docstring. With ``--upgrade`` it also runs ``uv tool upgrade`` for git
    installs (prints manual steps for local installs).
    """
    parser = argparse.ArgumentParser(
        prog="toolguard-update-check",
        description=(
            "Audience: END-USER -- a maintenance command you run yourself to check "
            "for (and with --upgrade, install) toolguard updates.\n\n"
            "Check whether toolguard is up to date. Works for both git installs "
            "(uv tool install git+https://...) and local/editable installs. "
            "Exit code: 0=up-to-date, 1=update-available, 2=could-not-determine."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help=(
            "If an update is available, run 'uv tool upgrade' to install it "
            "(git installs only; for local installs, prints manual steps instead)."
        ),
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print nothing when already up to date (for shell-startup use).",
    )
    args = parser.parse_args()
    sys.exit(_check(quiet=args.quiet, do_upgrade=args.upgrade))


if __name__ == "__main__":
    main()
