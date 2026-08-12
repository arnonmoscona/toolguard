"""
The ``toolguard-update-check`` console script.

Argument parsing and exit-code plumbing only. Install-kind detection, the
comparison against the remote, and the meaning of each exit code all live in
:mod:`toolguard.install_update`.
"""

import argparse
import sys

from toolguard.install_update import _check


def main() -> None:
    """Parse the command line, run the check, and exit with its code."""
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
