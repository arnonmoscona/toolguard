"""
Update checker for a git-installed toolguard (TOO-16).

When toolguard is installed as a uv tool from a git source
(``uv tool install git+https://github.com/<owner>/toolguard``), uv pins the
exact commit it resolved and records it in the installed package's PEP 610
``direct_url.json``. uv cannot perform a *version*-tracking upgrade from a git
source -- it follows the branch HEAD -- so "is there a newer toolguard?" must be
answered by comparing the installed commit against the remote HEAD. That is what
this module does.

The reliable upgrade command for a git install is plain ``uv tool upgrade
<dist>`` (it re-resolves HEAD and rebuilds when the commit moved); this module
can run it for you with ``--upgrade``.

Exit codes (a stable contract relied on by the shell snippets in the docs):

* ``0`` -- up to date (installed commit == remote HEAD).
* ``1`` -- update available (installed commit != remote HEAD).
* ``2`` -- could not determine: toolguard is not a git install, or the remote
  is unreachable (offline). Never blocks, never hangs.

Once toolguard is published to a package index this whole commit-comparison
becomes a plain version check and ``uv tool upgrade`` handles it natively; this
module can then be retired.
"""

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys

# Distribution name to introspect and to print in the upgrade command. Kept as a
# fallback only; the live value is read from installed metadata so the printed
# command stays correct even if the distribution is renamed (e.g. for PyPI).
_DEFAULT_DIST_NAME = "toolguard"

# Exit codes (stable contract -- see module docstring).
EXIT_UP_TO_DATE = 0
EXIT_UPDATE_AVAILABLE = 1
EXIT_UNKNOWN = 2

# Network guard for ``git ls-remote``: never prompt for credentials, never hang.
_LS_REMOTE_TIMEOUT_SECONDS = 10


def distribution_name() -> str:
    """
    Return the installed distribution name for toolguard.

    Read from installed metadata so the upgrade command this module prints stays
    correct even if the distribution is later renamed (the import package and
    entry points stay ``toolguard``, but a future PyPI release may use a
    different *distribution* name).

    Returns:
        The distribution name, or ``_DEFAULT_DIST_NAME`` if it cannot be read.
    """
    try:
        return importlib.metadata.distribution(_DEFAULT_DIST_NAME).metadata["Name"]
    except Exception:
        return _DEFAULT_DIST_NAME


def installed_origin() -> tuple[str, str] | None:
    """
    Return the git ``(url, commit_id)`` toolguard was installed from.

    Reads this package's own PEP 610 ``direct_url.json`` via
    :mod:`importlib.metadata`. That file is present only for direct-reference
    installs (e.g. ``uv tool install git+...``) and carries a ``vcs_info`` block
    for VCS installs.

    Returns:
        ``(url, commit_id)`` for a git install, or ``None`` when toolguard is not
        a git install (no ``direct_url.json``, or no ``vcs_info`` -- e.g. an
        editable install or a future package-index install).
    """
    try:
        raw = importlib.metadata.distribution(_DEFAULT_DIST_NAME).read_text(
            "direct_url.json"
        )
    except Exception:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError, TypeError:
        return None
    vcs_info = data.get("vcs_info")
    url = data.get("url")
    if not isinstance(vcs_info, dict) or not url:
        return None
    commit_id = vcs_info.get("commit_id")
    if not commit_id:
        return None
    return url, commit_id


def remote_head(url: str) -> str | None:
    """
    Return the remote HEAD commit sha for a git ``url``, or ``None``.

    Runs ``git ls-remote <url> HEAD`` with terminal prompts disabled and a short
    timeout, so it is offline-safe: any failure (no network, missing ``git``,
    auth prompt, timeout, non-zero exit, unexpected output) yields ``None``
    rather than raising or hanging.

    Args:
        url: The git remote URL to query.

    Returns:
        The 40-character HEAD sha, or ``None`` if it cannot be determined.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", "ls-remote", url, "HEAD"],
            env=env,
            capture_output=True,
            text=True,
            timeout=_LS_REMOTE_TIMEOUT_SECONDS,
        )
    except OSError, subprocess.SubprocessError:
        return None
    if result.returncode != 0:
        return None
    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    sha = first_line.split("\t", 1)[0].strip() if first_line else ""
    return sha or None


def run_upgrade(dist_name: str) -> int:
    """
    Run ``uv tool upgrade <dist_name>`` and return its exit code.

    Args:
        dist_name: The distribution name to upgrade.

    Returns:
        The subprocess exit code, or :data:`EXIT_UNKNOWN` if ``uv`` could not be
        launched.
    """
    try:
        result = subprocess.run(["uv", "tool", "upgrade", dist_name])
    except OSError, subprocess.SubprocessError:
        print(
            "Could not run 'uv tool upgrade' -- is uv installed and on PATH?",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN
    return result.returncode


def _check(quiet: bool, do_upgrade: bool) -> int:
    """
    Perform the update check (and optional upgrade) and return an exit code.

    Args:
        quiet: When True, suppress output in the up-to-date case (exit 0). Output
            is still produced when an update is available or the state is unknown.
        do_upgrade: When True, run ``uv tool upgrade`` if an update is available.

    Returns:
        One of :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE`, or
        :data:`EXIT_UNKNOWN`.
    """
    dist_name = distribution_name()

    origin = installed_origin()
    if origin is None:
        print(
            f"toolguard is not a git install; nothing to compare. "
            f"Use 'uv tool upgrade {dist_name}' (or your normal upgrade path).",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    url, installed_commit = origin
    remote = remote_head(url)
    if remote is None:
        print(
            "Could not reach the toolguard remote to check for updates "
            "(offline, or git unavailable).",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    if installed_commit == remote:
        if not quiet:
            print(f"toolguard is up to date ({installed_commit[:9]}).")
        return EXIT_UP_TO_DATE

    print(
        f"toolguard update available: {installed_commit[:9]} -> {remote[:9]}\n"
        f"Run: uv tool upgrade {dist_name}"
    )
    if do_upgrade:
        return run_upgrade(dist_name)
    return EXIT_UPDATE_AVAILABLE


def main() -> None:
    """
    Console-script entry point for ``toolguard-update-check``.

    Compares the installed git commit against the remote HEAD and exits with the
    code described in the module docstring. With ``--upgrade`` it also runs
    ``uv tool upgrade`` when an update is available.
    """
    parser = argparse.ArgumentParser(
        prog="toolguard-update-check",
        description=(
            "Check whether a git-installed toolguard is behind its remote HEAD."
        ),
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="If an update is available, run 'uv tool upgrade' to install it.",
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
