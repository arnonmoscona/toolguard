"""
Shared git-subprocess boilerplate for toolguard's low-level, stdlib-only leaf modules.

TOO-19 code review M3: ``update_check.py`` and ``install_provenance.py`` each ran
``subprocess.run(["git", ...], capture_output=True, text=True, timeout=...)`` in a
try/except at five call sites (``is_git_worktree``, ``local_repo_head``,
``local_remote_head``, ``remote_head`` in ``update_check.py``, plus
``_git_subtree_is_clean`` in ``install_provenance.py``), each independently
catching the same exception pair and duplicating the same argv-building shape.
:func:`run_git` is the one place that boilerplate now lives; every call site's
OWN returncode/stdout interpretation still lives in that call site, since those
five genuinely differ (a boolean membership check, a stripped single value, a
tab-split first line) and folding them in here would trade a small, honest
duplication for a misleading one-size-fits-all abstraction.

This module is deliberately as low-level as ``update_check.py`` and
``install_provenance.py`` themselves: stdlib-only, imports nothing else from
``toolguard``, so it creates no dependency either of those two modules' own
callers (:mod:`toolguard.session_start`, :mod:`toolguard.tools.environment_audit`)
would inherit.
"""

import subprocess
from typing import Mapping, Optional, Sequence

from toolguard.constants import GIT_TIMEOUT_SECONDS


def run_git(
    args: Sequence[str],
    *,
    timeout: float = GIT_TIMEOUT_SECONDS,
    env: Optional[Mapping[str, str]] = None,
) -> Optional["subprocess.CompletedProcess[str]"]:
    """
    Run ``git <*args>`` and return its :class:`subprocess.CompletedProcess`, or
    ``None`` when the subprocess machinery itself failed to launch.

    Captures text stdout/stderr and applies the shared
    :data:`~toolguard.constants.GIT_TIMEOUT_SECONDS` network/process guard so no
    caller can hang or prompt for credentials. Callers still interpret
    ``returncode``/``stdout`` themselves -- see the module docstring for why.

    Args:
        args: The git subcommand and its arguments, WITHOUT the leading
            ``"git"`` (e.g. ``["-C", str(repo), "rev-parse", "HEAD"]``).
        timeout: Subprocess timeout in seconds. Defaults to
            :data:`~toolguard.constants.GIT_TIMEOUT_SECONDS`.
        env: Environment mapping for the subprocess, or ``None`` (the default)
            to inherit the current process environment unchanged. Callers that
            need offline-safe network operations pass a copy of
            :data:`os.environ` with ``GIT_TERMINAL_PROMPT`` set to ``"0"``.

    Returns:
        The :class:`subprocess.CompletedProcess`, or ``None`` when git could
        not be launched at all (missing binary, timeout, or any other
        :class:`OSError`/:class:`subprocess.SubprocessError`) -- NOT for a
        non-zero exit, which is a normal git outcome the caller must still
        check via ``result.returncode``.
    """
    try:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except OSError, subprocess.SubprocessError:
        return None
