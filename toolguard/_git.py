"""
Shared git-subprocess boilerplate: one place for the argv shape, the output
capture and the timeout.

Interpreting ``returncode`` and ``stdout`` stays with each caller.
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
    Run ``git <*args>``, capturing stdout and stderr as text.

    Args:
        args: The git subcommand and its arguments, WITHOUT the leading
            ``"git"`` (e.g. ``["-C", str(repo), "rev-parse", "HEAD"]``).
        timeout: Subprocess timeout in seconds, defaulting to
            :data:`~toolguard.constants.GIT_TIMEOUT_SECONDS`. It bounds a hang;
            it does not stop git prompting -- a command that may reach the
            network needs ``GIT_TERMINAL_PROMPT=0`` passed in *env*.
        env: Environment mapping for the subprocess, or ``None`` (the default)
            to inherit the current process environment unchanged.

    Returns:
        The :class:`subprocess.CompletedProcess`, or ``None`` when git could
        not be run to completion at all -- missing binary, timeout, or any
        other :class:`OSError`/:class:`subprocess.SubprocessError`. NOT for a
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
