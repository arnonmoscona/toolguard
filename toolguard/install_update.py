"""
Detects whether the installed toolguard distribution is behind its git remote.

Two install kinds are recognised, normally from the package's PEP 610
``direct_url.json``:

**git** -- a ``vcs_info`` block holds the commit that was installed; it is
compared against ``git ls-remote <url> HEAD``. ``--upgrade`` runs
``uv tool upgrade``.

**local** -- a ``dir_info`` block with a ``file://`` URL, or, failing any
usable metadata, a ``.git`` directory found by walking up from this module's
own file. The checkout's ``HEAD`` is compared against its ``origin`` HEAD,
and remediation is always manual: nothing here mutates a working tree.

Anything else is ``UNKNOWN``.

Exit codes:

* ``0`` -- installed commit equals remote HEAD.
* ``1`` -- they differ.
* ``2`` -- could not determine: unknown install kind, unreadable checkout,
  unreachable remote, or ``uv`` missing.

No git subprocess here can hang: every one runs under
:func:`~toolguard._git.run_git`'s timeout, and the two ``ls-remote`` calls
set ``GIT_TERMINAL_PROMPT=0`` so git does not stop for a terminal
credential prompt. ``--upgrade`` is the exception -- :func:`run_upgrade`
runs ``uv`` untimed, and when it runs, ``uv``'s own exit code is returned in
place of the three above.
"""

import importlib.metadata
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from toolguard._git import run_git
from toolguard.constants import DIST_NAME as _DEFAULT_DIST_NAME

#: Process exit codes -- also documented for end users in
#: ``docs/configuration.md``, so renumbering them is a user-visible change.
EXIT_UP_TO_DATE = 0
EXIT_UPDATE_AVAILABLE = 1
EXIT_UNKNOWN = 2


class InstallKind(Enum):
    """How toolguard was installed, as far as :func:`detect_install` can tell."""

    GIT = auto()
    LOCAL = auto()
    UNKNOWN = auto()


@dataclass(frozen=True)
class InstallInfo:
    """
    What :func:`detect_install` established about the current install.

    Attributes:
        kind: GIT, LOCAL, or UNKNOWN.
        url: The git remote URL (GIT) or the ``file://`` URL (LOCAL) -- None
            for a LOCAL checkout found by walking up from ``__file__``.
        installed_commit: The installed commit (GIT) or the checkout's HEAD
            (LOCAL), when it could be read.
        repo_path: The local checkout path; LOCAL only.
        editable: Whether a LOCAL install is editable. None for other kinds.
    """

    kind: InstallKind
    url: Optional[str] = None
    installed_commit: Optional[str] = None
    repo_path: Optional[Path] = None
    editable: Optional[bool] = None


def distribution_name() -> str:
    """
    Return the installed distribution name, or
    :data:`~toolguard.constants.DIST_NAME` when it cannot be read.
    """
    try:
        return importlib.metadata.distribution(_DEFAULT_DIST_NAME).metadata["Name"]
    except Exception:
        return _DEFAULT_DIST_NAME


def _read_direct_url_json() -> Optional[dict]:
    """
    Read and parse this package's PEP 610 ``direct_url.json``.

    Returns:
        Parsed JSON, or None when the file is absent, empty or unparseable.
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
        return json.loads(raw)
    except ValueError, TypeError:
        return None


def _file_url_to_path(file_url: str) -> Optional[Path]:
    """Return the path in a ``file://`` URL, or None for anything else."""
    try:
        parsed = urlparse(file_url)
        if parsed.scheme != "file":
            return None
        return Path(parsed.path)
    except Exception:
        return None


def _walk_up_to_git_root(start: Path) -> Optional[Path]:
    """Return the nearest directory at or above ``start`` holding ``.git``, or None."""
    current = start if start.is_dir() else start.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def is_git_worktree(repo: Path) -> bool:
    """
    Return True when git confirms ``repo`` is inside a work tree, False on
    any failure.
    """
    result = run_git(["-C", str(repo), "rev-parse", "--is-inside-work-tree"])
    if result is None:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def local_repo_head(repo: Path) -> Optional[str]:
    """
    Return HEAD's commit SHA in the checkout ``repo``, or None on any failure
    (not a repo, git missing, no output).
    """
    result = run_git(["-C", str(repo), "rev-parse", "HEAD"])
    if result is None or result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if sha else None


def local_remote_head(repo: Path) -> Optional[str]:
    """
    Return the ``origin`` HEAD commit SHA as seen from the checkout ``repo``,
    or None on any failure (no ``origin``, offline, git missing).
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = run_git(["-C", str(repo), "ls-remote", "origin", "HEAD"], env=env)
    if result is None or result.returncode != 0:
        return None
    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    sha = first_line.split("\t", 1)[0].strip() if first_line else ""
    return sha or None


def detect_install() -> InstallInfo:
    """
    Determine how toolguard was installed.

    From the metadata: a ``vcs_info`` commit and a URL make it GIT; a
    ``dir_info`` ``file://`` URL makes it LOCAL, or UNKNOWN outright when the
    path is not a git checkout.

    Returns:
        An :class:`InstallInfo`, its ``kind`` UNKNOWN when nothing resolves.
    """
    data = _read_direct_url_json()

    if data is not None:
        url = data.get("url", "")
        vcs_info = data.get("vcs_info")
        dir_info = data.get("dir_info")

        if isinstance(vcs_info, dict):
            commit_id = vcs_info.get("commit_id")
            if commit_id and url:
                return InstallInfo(
                    kind=InstallKind.GIT,
                    url=url,
                    installed_commit=commit_id,
                )

        if isinstance(dir_info, dict) and url.startswith("file://"):
            repo_path = _file_url_to_path(url)
            editable = bool(dir_info.get("editable", False))
            if repo_path is not None and is_git_worktree(repo_path):
                head = local_repo_head(repo_path)
                return InstallInfo(
                    kind=InstallKind.LOCAL,
                    url=url,
                    installed_commit=head,
                    repo_path=repo_path,
                    editable=editable,
                )
            return InstallInfo(kind=InstallKind.UNKNOWN)

    try:
        module_file = Path(__file__).resolve()
    except Exception:
        return InstallInfo(kind=InstallKind.UNKNOWN)

    repo_path = _walk_up_to_git_root(module_file.parent)
    if repo_path is not None and is_git_worktree(repo_path):
        head = local_repo_head(repo_path)
        return InstallInfo(
            kind=InstallKind.LOCAL,
            installed_commit=head,
            repo_path=repo_path,
            editable=False,
        )

    return InstallInfo(kind=InstallKind.UNKNOWN)


def remote_head(url: str) -> Optional[str]:
    """
    Return the HEAD commit SHA at the git remote ``url``, or None on any
    failure (offline, git missing, timeout, unexpected output).
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    result = run_git(["ls-remote", url, "HEAD"], env=env)
    if result is None or result.returncode != 0:
        return None
    first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    sha = first_line.split("\t", 1)[0].strip() if first_line else ""
    return sha or None


def run_upgrade(dist_name: str) -> int:
    """
    Run ``uv tool upgrade <dist_name>`` and return its exit code, or
    :data:`EXIT_UNKNOWN` when ``uv`` could not be launched.

    Alone among this module's subprocesses it is untimed and its output is
    not captured.
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


def _check_git(info: InstallInfo, quiet: bool, do_upgrade: bool) -> int:
    """
    Compare a GIT install's commit against the remote HEAD and report.

    Args:
        info: An :class:`InstallInfo` with ``kind == InstallKind.GIT``.
        quiet: When True, say nothing in the up-to-date case.
        do_upgrade: When True and behind, run ``uv tool upgrade``.

    Returns:
        :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE` or
        :data:`EXIT_UNKNOWN` -- or, when an upgrade was actually run,
        whatever :func:`run_upgrade` returned.
    """
    dist_name = distribution_name()
    remote = remote_head(info.url)
    if remote is None:
        print(
            "Could not reach the toolguard remote to check for updates "
            "(offline, or git unavailable).",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    if info.installed_commit == remote:
        if not quiet:
            print(f"toolguard is up to date ({info.installed_commit[:9]}).")
        return EXIT_UP_TO_DATE

    print(
        f"toolguard update available: {info.installed_commit[:9]} -> {remote[:9]}\n"
        f"Run: uv tool upgrade {dist_name}"
    )
    if do_upgrade:
        return run_upgrade(dist_name)
    return EXIT_UPDATE_AVAILABLE


def _check_local(info: InstallInfo, quiet: bool, do_upgrade: bool) -> int:
    """
    Compare a LOCAL checkout's HEAD against its ``origin`` HEAD and report,
    printing the manual update steps when it is behind.

    Args:
        info: An :class:`InstallInfo` with ``kind == InstallKind.LOCAL``.
        quiet: When True, say nothing in the up-to-date case.
        do_upgrade: When True, add a note that nothing ran automatically.

    Returns:
        :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE` or
        :data:`EXIT_UNKNOWN`.
    """
    repo = info.repo_path
    dist_name = distribution_name()

    installed = local_repo_head(repo)
    if installed is None:
        print(
            f"Could not read HEAD from local checkout {repo} (is this a git repo?).",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    remote = local_remote_head(repo)
    if remote is None:
        print(
            f"Could not reach the toolguard remote from {repo} "
            "(offline, or no 'origin' remote?).",
            file=sys.stderr,
        )
        return EXIT_UNKNOWN

    if installed == remote:
        if not quiet:
            print(f"toolguard is up to date ({installed[:9]}) [checkout: {repo}].")
        return EXIT_UP_TO_DATE

    pull_cmd = f"git -C {repo} pull"
    print(
        f"toolguard update available: {installed[:9]} -> {remote[:9]}\nCheckout: {repo}"
    )

    if info.editable:
        print(
            f"Manual update steps (editable install -- git pull is sufficient):\n"
            f"  {pull_cmd}"
        )
    else:
        print(
            f"Manual update steps (local uv tool install -- pull then reinstall):\n"
            f"  {pull_cmd}\n"
            f"  uv tool install --force {repo}"
            f"  # or: uv tool upgrade {dist_name} --reinstall"
        )

    if do_upgrade:
        print(
            "\nNote: --upgrade does not auto-run for a local install "
            "to avoid unintended mutation of your working tree. "
            "Run the steps above manually.",
            file=sys.stderr,
        )

    return EXIT_UPDATE_AVAILABLE


def _check(quiet: bool, do_upgrade: bool) -> int:
    """
    Detect the install kind and run the check for it.

    Args:
        quiet: When True, say nothing in the up-to-date case. An available
            update or an undetermined state still prints.
        do_upgrade: When True, upgrade a git install that is behind; a local
            install only ever gets its manual steps.

    Returns:
        The process exit code -- see the module docstring.
    """
    dist_name = distribution_name()
    info = detect_install()

    if info.kind == InstallKind.GIT:
        return _check_git(info, quiet, do_upgrade)

    if info.kind == InstallKind.LOCAL:
        return _check_local(info, quiet, do_upgrade)

    print(
        f"toolguard: could not determine install type. "
        f"Use 'uv tool upgrade {dist_name}' (git install) or "
        f"'git pull' in your checkout (local install) to update manually.",
        file=sys.stderr,
    )
    return EXIT_UNKNOWN


def installed_origin() -> Optional[tuple]:
    """
    Return the git ``(url, commit_id)`` toolguard was installed from, or None
    when it is not a git install.

    Deprecated: superseded by :func:`detect_install`, which returns the same
    facts and recognises local installs as well.
    """
    data = _read_direct_url_json()
    if data is None:
        return None
    vcs_info = data.get("vcs_info")
    url = data.get("url")
    if not isinstance(vcs_info, dict) or not url:
        return None
    commit_id = vcs_info.get("commit_id")
    if not commit_id:
        return None
    return url, commit_id
