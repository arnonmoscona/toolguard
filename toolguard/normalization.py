"""Path normalization for consistent pattern matching.

Collapses a path -- or the path-like tokens inside a command string -- to one canonical
form, so the same location written differently (an absolute path under the home directory
vs. its '~' form, doubled leading slashes, a symlink vs. its target) normalizes to one
spelling. Symlink resolution is optional (``resolve_symlinks``) because it produces a
different canonical form from the other steps and a matcher may need both.

Reads live filesystem state: :func:`normalize_path` follows symlinks via
:meth:`pathlib.Path.resolve` and checks whether a relative path exists under a
given project root.
"""

from pathlib import Path
import re
from typing import Optional, Tuple


def _involves_a_symlink(path_obj: Path) -> bool:
    """Whether path_obj is a symlink, or is absolute with a symlinked ancestor directory.

    The ancestors of a RELATIVE path are deliberately not examined: they would be
    interpreted against the hook process's own working directory, which is not the
    shell's, so resolving them would rewrite a token against a directory the command
    never named.
    """
    if path_obj.is_symlink():
        return True
    return path_obj.is_absolute() and any(
        parent.is_symlink() for parent in path_obj.parents
    )


def _home_spellings() -> Tuple[Path, ...]:
    """The home directory as reported and, where it differs, as resolved; empty if neither.

    Both spellings are needed because the symlink step above may have rewritten the
    path into its real form while ``Path.home()`` still reports the symlinked one.
    """
    try:
        home = Path.home()
    except OSError, RuntimeError:
        return ()
    try:
        resolved = home.resolve()
    except OSError, RuntimeError:
        return (home,)
    return (home,) if resolved == home else (home, resolved)


def normalize_path(
    path: str, project_root: Optional[Path] = None, *, resolve_symlinks: bool = True
) -> str:
    """Normalize a path to canonical form for pattern matching.

    In order: collapses repeated leading slashes, resolves any symlink in the path
    (the path itself or an ancestor directory, dangling or not), collapses a path under
    the user's home directory to a '~/...' prefix -- home itself becoming plain '~' --
    then, for a bare relative path with no leading '/', '~', or '.', adds a './' prefix.
    That last step is unconditional when no project_root is given, but only fires when
    project_root is given AND the path exists under it.

    Args:
        path: The path to normalize.
        project_root: Optional root a bare relative path's existence is checked against
            before it is given a './' prefix.
        resolve_symlinks: When False, the symlink step is skipped and the path keeps the
            spelling it was written in. Callers that need both forms must ask for both;
            resolution rewrites a path away from the name a rule author is likely to have
            used, so it is one canonical form among several rather than the only one.

    Returns:
        The normalized path. Empty input is returned unchanged.
    """
    if not path:
        return path

    path = re.sub(r"^/+", "/", path)

    # Resolve symlinks anywhere in the path -- the link itself or any ancestor
    # directory, whether or not the target exists yet. A DANGLING link is the
    # security-relevant case: it is a live spelling of a location a rule may
    # protect, and writing through it creates that very target.
    if resolve_symlinks:
        try:
            path_obj = Path(path)
            if _involves_a_symlink(path_obj):
                path = str(path_obj.resolve())
        except OSError, RuntimeError:
            pass

    # Collapse an absolute path under the user's home directory to '~/...'.
    try:
        path_obj = Path(path)
        if path_obj.is_absolute():
            for home in _home_spellings():
                try:
                    relative_to_home = path_obj.relative_to(home)
                except ValueError:
                    continue
                # relative_to() gives '.' for home itself; '~/.' is a second
                # spelling of '~' that no rule author writes.
                path = "~" if str(relative_to_home) == "." else f"~/{relative_to_home}"
                break
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


def normalize_command(
    command: str, project_root: Optional[Path] = None, *, resolve_symlinks: bool = True
) -> str:
    """Normalize each path-like token in a command string via :func:`normalize_path`.

    A token is treated as a path if it starts with '/', '~', or '.'; contains '/'; or has
    a short alphanumeric extension like '.txt'. A leading '-' flag is never treated as a
    path, and the first token is normalized only when it contains '/'.

    Args:
        command: The command string to normalize.
        project_root: Optional project root, forwarded to :func:`normalize_path` for
            each path-like token.
        resolve_symlinks: Forwarded to :func:`normalize_path`.

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
                normalized_tokens.append(
                    normalize_path(
                        token, project_root, resolve_symlinks=resolve_symlinks
                    )
                )
            else:
                normalized_tokens.append(token)
            continue

        is_path = "/" in token or token.startswith("~") or token.startswith(".")

        if not is_path and "." in token:
            parts = token.rsplit(".", 1)
            if len(parts) == 2 and len(parts[1]) <= 4 and parts[1].isalnum():
                is_path = True

        if is_path:
            normalized = normalize_path(
                token, project_root, resolve_symlinks=resolve_symlinks
            )
            normalized_tokens.append(normalized)
        else:
            normalized_tokens.append(token)

    return " ".join(normalized_tokens)
