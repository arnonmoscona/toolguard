"""
Library implementation of toolguard's own-install update detection (TOO-16).

Supports three install kinds:

**git** (``uv tool install git+https://...``): uv pins the exact commit it
resolved and records it in PEP 610 ``direct_url.json`` as ``vcs_info``.
"Up to date?" = installed commit vs ``git ls-remote <url> HEAD``.
``--upgrade`` auto-runs ``uv tool upgrade <dist>``.

**local** (``uv tool install /local/path`` or ``uv pip install -e .``): uv
records ``dir_info`` with a ``file://`` URL in ``direct_url.json``, or no
usable metadata but the module file lives inside a git work tree that can be
discovered by walking up the directory tree. "Up to date?" = ``git rev-parse
HEAD`` vs ``git ls-remote origin HEAD`` in the checkout. Remediation is
**manual** -- this module never mutates a working tree.

**unknown**: neither kind resolves. Punts with exit 2 and a clear message.

Exit codes (a stable contract relied on by the shell snippets in the docs):

* ``0`` -- up to date (installed commit == remote HEAD).
* ``1`` -- update available (installed commit != remote HEAD).
* ``2`` -- could not determine: install kind is unknown, or the remote is
  unreachable (offline). Never blocks, never hangs.

Once toolguard is published to a package index this whole commit-comparison
becomes a plain version check and ``uv tool upgrade`` handles it natively; this
module can then be retired.

TOO-45 R5c split this out of :mod:`toolguard.update_check`. Before this
split, that console-script module was simultaneously the
``toolguard-update-check`` CLI entry point AND the library
:mod:`toolguard.tools.installer` imported for install-kind detection -- R5's
leafness predicate flags exactly this shape (an entry point that is also a
library other modules import). This module holds only ``constants`` and
``_git`` imports, both ``foundation``-layer leaves, so it is itself a
``foundation``-layer leaf -- the same shape as its sibling
:mod:`toolguard.install_provenance` (a related but distinct question: that
module asks whether the CURRENTLY GOVERNING copy is a stale/shadowed
checkout; this one asks whether the INSTALLED distribution is behind the
remote). :mod:`toolguard.update_check` is now a thin CLI wrapper
(``main``) around :func:`_check` here.
"""

import importlib.metadata
import json
import os

# subprocess is imported for its own sake here (not just for run_git()'s
# benefit) -- see is_git_worktree()/local_repo_head()/local_remote_head()/
# remote_head() below, whose module-attribute access
# (patch.object(install_update.subprocess, "run", ...) in test_update_check.py)
# requires this module to hold its own reference to the module, even though
# the actual subprocess.run() call itself now lives in toolguard._git.run_git.
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from toolguard._git import run_git
from toolguard.constants import DIST_NAME as _DEFAULT_DIST_NAME

# Exit codes (stable contract -- see module docstring).
EXIT_UP_TO_DATE = 0
EXIT_UPDATE_AVAILABLE = 1
EXIT_UNKNOWN = 2


class InstallKind(Enum):
    """The detected kind of toolguard installation."""

    GIT = auto()  # git+https uv tool install (vcs_info present)
    LOCAL = auto()  # local path or editable install (dir_info or __file__ walk-up)
    UNKNOWN = auto()  # cannot determine


@dataclass(frozen=True)
class InstallInfo:
    """
    Describes the detected install of toolguard.

    Attributes:
        kind: The install kind (GIT, LOCAL, or UNKNOWN).
        url: For GIT installs, the git remote URL. For LOCAL installs, the
            file:// URL or None when discovered via __file__ walk-up.
        installed_commit: The commit SHA that is currently installed, if known.
        repo_path: For LOCAL installs, the resolved Path to the checkout root.
        editable: True when the install is an editable (``uv pip install -e``);
            False when it is a non-editable local uv tool install. None for
            non-LOCAL kinds or when not known.
    """

    kind: InstallKind
    url: Optional[str] = None
    installed_commit: Optional[str] = None
    repo_path: Optional[Path] = None
    editable: Optional[bool] = None


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


def _read_direct_url_json() -> Optional[dict]:
    """
    Read and parse this package's PEP 610 ``direct_url.json``.

    Returns:
        Parsed dict, or None when the file is absent or unparseable.
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
    """
    Convert a ``file://`` URL to a :class:`~pathlib.Path`.

    Args:
        file_url: A URL beginning with ``file://``.

    Returns:
        A Path, or None when the URL cannot be parsed as a local path.
    """
    try:
        parsed = urlparse(file_url)
        if parsed.scheme != "file":
            return None
        return Path(parsed.path)
    except Exception:
        return None


def _walk_up_to_git_root(start: Path) -> Optional[Path]:
    """
    Walk up the directory tree from ``start`` to find a ``.git`` directory.

    Args:
        start: The directory to begin searching from.

    Returns:
        The first ancestor directory (inclusive of ``start``) that contains a
        ``.git`` entry, or None when no such directory is found before
        reaching the filesystem root.
    """
    current = start if start.is_dir() else start.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            # Reached the filesystem root without finding .git
            return None
        current = parent


def is_git_worktree(repo: Path) -> bool:
    """
    Return True when ``repo`` is the root of a git work tree.

    Runs ``git -C <repo> rev-parse --is-inside-work-tree`` to confirm. This
    subprocess is monkeypatch-able by tests (``patch.object(install_update.subprocess,
    "run", ...)`` -- the actual call now lives in :func:`toolguard._git.run_git`,
    which imports the SAME ``subprocess`` module, so patching it here still
    intercepts the call; see the module-level ``import subprocess`` comment).

    Args:
        repo: A directory suspected to be a git work tree root.

    Returns:
        True when git confirms the directory is inside a work tree, False on
        any failure.
    """
    result = run_git(["-C", str(repo), "rev-parse", "--is-inside-work-tree"])
    if result is None:
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"


def local_repo_head(repo: Path) -> Optional[str]:
    """
    Return the HEAD commit SHA in a local git checkout ``repo``.

    Runs ``git -C <repo> rev-parse HEAD``. This subprocess is monkeypatch-able
    by tests.

    Args:
        repo: Path to the git work tree root.

    Returns:
        The HEAD commit SHA, or None on any failure (not a repo, git missing, etc.).
    """
    result = run_git(["-C", str(repo), "rev-parse", "HEAD"])
    if result is None or result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha if sha else None


def local_remote_head(repo: Path) -> Optional[str]:
    """
    Return the remote origin HEAD commit SHA for a local checkout ``repo``.

    Runs ``git -C <repo> ls-remote origin HEAD``. Disables terminal prompts
    and uses a short timeout so this is offline-safe. This subprocess is
    monkeypatch-able by tests.

    Args:
        repo: Path to the git work tree root.

    Returns:
        The remote HEAD SHA, or None on any failure.
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
    Detect the kind of toolguard installation and return an :class:`InstallInfo`.

    Detection order:

    1. Read ``direct_url.json`` from installed metadata.
       - If it has ``vcs_info.commit_id`` -> **git** kind.
       - If it has ``dir_info`` (``file://`` URL) -> **local** kind; resolve
         the checkout path from the URL.
    2. If ``direct_url.json`` is absent or has neither block, walk up from
       this module's own ``__file__`` to the nearest ``.git`` directory
       (fallback for unusual install methods).
    3. For a discovered local path, confirm it is a git work tree; if not ->
       **unknown**.
    4. Nothing found -> **unknown**.

    Returns:
        An :class:`InstallInfo` describing the install kind and relevant details.
    """
    data = _read_direct_url_json()

    if data is not None:
        url = data.get("url", "")
        vcs_info = data.get("vcs_info")
        dir_info = data.get("dir_info")

        # --- git kind: vcs_info present ---
        if isinstance(vcs_info, dict):
            commit_id = vcs_info.get("commit_id")
            if commit_id and url:
                return InstallInfo(
                    kind=InstallKind.GIT,
                    url=url,
                    installed_commit=commit_id,
                )

        # --- local kind: dir_info present ---
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
            # dir_info present but not a git repo -> unknown
            return InstallInfo(kind=InstallKind.UNKNOWN)

    # --- Fallback: walk up from __file__ to find a .git ---
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
    Return the remote HEAD commit sha for a git ``url``, or ``None``.

    Runs ``git ls-remote <url> HEAD`` with terminal prompts disabled and a short
    timeout, so it is offline-safe: any failure (no network, missing ``git``,
    auth prompt, timeout, non-zero exit, unexpected output) yields ``None``
    rather than raising or hanging.

    Args:
        url: The git remote URL to query.

    Returns:
        The HEAD sha, or ``None`` if it cannot be determined.
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


def _check_git(info: InstallInfo, quiet: bool, do_upgrade: bool) -> int:
    """
    Perform the update check for a **git** kind install.

    Compares the installed commit against the remote HEAD. With ``do_upgrade``
    and an available update, runs ``uv tool upgrade``.

    Args:
        info: An :class:`InstallInfo` with ``kind == InstallKind.GIT``.
        quiet: When True, suppress output in the up-to-date case.
        do_upgrade: When True, run ``uv tool upgrade`` when behind.

    Returns:
        One of :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE`, or
        :data:`EXIT_UNKNOWN`.
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
    Perform the update check for a **local** kind install.

    Compares the checkout's HEAD against the remote origin HEAD. Remediation
    is **always manual** -- this function never mutates the working tree,
    even with ``do_upgrade``.

    Args:
        info: An :class:`InstallInfo` with ``kind == InstallKind.LOCAL``.
        quiet: When True, suppress output in the up-to-date case.
        do_upgrade: When True, print manual remediation steps (no auto-run).

    Returns:
        One of :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE`, or
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

    # Update is available -- always manual for local installs
    pull_cmd = f"git -C {repo} pull"
    print(
        f"toolguard update available: {installed[:9]} -> {remote[:9]}\nCheckout: {repo}"
    )

    if info.editable:
        # Editable install: source is picked up live after git pull
        print(
            f"Manual update steps (editable install -- git pull is sufficient):\n"
            f"  {pull_cmd}"
        )
    else:
        # Non-editable local uv tool install: pull + reinstall
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
    Perform the update check (and optional upgrade) and return an exit code.

    Detects the install kind and dispatches to the appropriate check function.

    Args:
        quiet: When True, suppress output in the up-to-date case (exit 0). Output
            is still produced when an update is available or the state is unknown.
        do_upgrade: When True, run ``uv tool upgrade`` if an update is available
            (git kind only). For local installs, prints manual steps instead.

    Returns:
        One of :data:`EXIT_UP_TO_DATE`, :data:`EXIT_UPDATE_AVAILABLE`, or
        :data:`EXIT_UNKNOWN`.
    """
    dist_name = distribution_name()
    info = detect_install()

    if info.kind == InstallKind.GIT:
        return _check_git(info, quiet, do_upgrade)

    if info.kind == InstallKind.LOCAL:
        return _check_local(info, quiet, do_upgrade)

    # Unknown kind
    print(
        f"toolguard: could not determine install type. "
        f"Use 'uv tool upgrade {dist_name}' (git install) or "
        f"'git pull' in your checkout (local install) to update manually.",
        file=sys.stderr,
    )
    return EXIT_UNKNOWN


def installed_origin() -> Optional[tuple]:
    """
    Return the git ``(url, commit_id)`` toolguard was installed from.

    This function is kept for backwards compatibility with existing tests. New
    code should use :func:`detect_install` instead.

    Reads this package's own PEP 610 ``direct_url.json`` via
    :mod:`importlib.metadata`. That file is present only for direct-reference
    installs and carries a ``vcs_info`` block for VCS installs.

    Returns:
        ``(url, commit_id)`` for a git install, or ``None`` when toolguard is not
        a git install (no ``direct_url.json``, or no ``vcs_info`` -- e.g. a
        local install or a future package-index install).

    .. deprecated::
        Use :func:`detect_install` to distinguish git vs local vs unknown kinds.
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
