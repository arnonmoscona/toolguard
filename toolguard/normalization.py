"""Path normalization for consistent pattern matching.

Collapses a path -- or the path-like tokens inside a command string -- to one canonical
form, so the same location written differently (an absolute path under the home directory
vs. its '~' form, doubled leading slashes, a symlink vs. its target) normalizes to one
spelling.

Reads live filesystem state: :func:`normalize_path` checks whether a path exists and
follows symlinks via :meth:`pathlib.Path.resolve`.
"""

from pathlib import Path
import re
from typing import Optional


def normalize_path(path: str, project_root: Optional[Path] = None) -> str:
    """Normalize a path to canonical form for pattern matching.

    In order: collapses repeated leading slashes, resolves symlinks, collapses a path
    under the user's home directory to a '~/...' prefix, then -- for a bare relative
    path with no leading '/', '~', or '.' -- adds a './' prefix. That last step is
    unconditional when no project_root is given, but only fires when project_root is
    given AND the path exists under it.

    Args:
        path: The path to normalize.
        project_root: Optional root a bare relative path's existence is checked against
            before it is given a './' prefix.

    Returns:
        The normalized path. Empty input is returned unchanged.
    """
    if not path:
        return path

    path = re.sub(r"^/+", "/", path)

    # Resolve symlinks -- but only a path that IS a symlink (not one whose parent
    # directory is), and only when it exists: exists() follows the link, so a dangling
    # symlink fails this check and is left as-is.
    try:
        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_symlink():
            for _ in range(3):
                if path_obj.is_symlink():
                    path_obj = path_obj.resolve()
                else:
                    break
            path = str(path_obj)
    except OSError, RuntimeError:
        pass

    # Collapse an absolute path under the user's home directory to '~/...'.
    home = Path.home()
    try:
        path_obj = Path(path)
        if path_obj.is_absolute():
            try:
                relative_to_home = path_obj.relative_to(home)
                path = f"~/{relative_to_home}"
            except ValueError:
                pass
    except OSError, ValueError:
        pass

    if not path.startswith(("/", "~", ".")):
        if project_root:
            try:
                full_path = project_root / path
                if full_path.exists():
                    path = f"./{path}"
            except OSError, ValueError:
                pass
        else:
            path = f"./{path}"

    return path


def expand_tilde(path: str) -> str:
    """Expand a leading '~' to the user's home directory path.

    Only '~' alone and '~/...' are expanded. A '~username' form is returned unchanged,
    as is any path with no leading '~'.

    Args:
        path: A path or pattern, possibly '~'-prefixed.

    Returns:
        path with a leading '~' expanded; otherwise path unchanged.
    """
    if not path or not path.startswith("~"):
        return path

    home = str(Path.home())

    if path == "~":
        return home

    if path.startswith("~/"):
        return home + path[1:]

    return path


def normalize_command(command: str, project_root: Optional[Path] = None) -> str:
    """Normalize each path-like token in a command string via :func:`normalize_path`.

    A token is treated as a path if it starts with '/', '~', or '.'; contains '/'; or has
    a short alphanumeric extension like '.txt'. A leading '-' flag is never treated as a
    path, and the first token is normalized only when it contains '/'.

    Args:
        command: The command string to normalize.
        project_root: Optional project root, forwarded to :func:`normalize_path` for
            each path-like token.

    Returns:
        command with its path-like tokens normalized; other tokens (including flags and
        the bare command name) are left unchanged. Whitespace between tokens is not
        preserved: runs of whitespace, including newlines, collapse to a single space.
        Empty input is returned unchanged.
    """
    if not command:
        return command

    tokens = command.split()
    normalized_tokens = []

    for i, token in enumerate(tokens):
        if token.startswith("-"):
            normalized_tokens.append(token)
            continue

        # A bare first word is normally the command name itself, not a path, even when
        # it contains a dot -- but one with a slash is a path ('bin/script.sh' ->
        # './bin/script.sh').
        if i == 0:
            if "/" in token:
                normalized_tokens.append(normalize_path(token, project_root))
            else:
                normalized_tokens.append(token)
            continue

        is_path = "/" in token or token.startswith("~") or token.startswith(".")

        if not is_path and "." in token:
            parts = token.rsplit(".", 1)
            if len(parts) == 2 and len(parts[1]) <= 4 and parts[1].isalnum():
                is_path = True

        if is_path:
            normalized = normalize_path(token, project_root)
            normalized_tokens.append(normalized)
        else:
            normalized_tokens.append(token)

    return " ".join(normalized_tokens)
