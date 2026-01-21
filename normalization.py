"""Path normalization utilities for consistent pattern matching.

This module provides functions to normalize paths in both patterns and commands
to a canonical form, enabling consistent matching across different path representations.
"""

from pathlib import Path
import re
from typing import Optional


def normalize_path(path: str, project_root: Optional[Path] = None) -> str:
    """Normalize a path to canonical form for pattern matching.

    Normalization steps:
    1. Convert /Users/<username>/... to ~/...
    2. Resolve symlinks (max 3 iterations to prevent infinite loops)
    3. Normalize multiple leading slashes to single /
    4. Expand relative paths to ./ (relative to project_root if provided)

    Args:
        path: The path to normalize
        project_root: Optional project root for relative path expansion

    Returns:
        Normalized path string

    Examples:
        >>> normalize_path('/Users/arnon/projects/file.txt')
        '~/projects/file.txt'
        >>> normalize_path('//tmp/file')
        '/tmp/file'
        >>> normalize_path('file.txt', Path('/Users/arnon/projects'))
        './file.txt'
    """
    if not path:
        return path

    # Step 1: Normalize multiple leading slashes
    # Replace multiple leading slashes with single slash
    path = re.sub(r'^/+', '/', path)

    # Step 2: Resolve symlinks (max 3 iterations)
    # Only resolve if the path actually is a symlink, not its parent directories
    try:
        path_obj = Path(path)
        if path_obj.exists() and path_obj.is_symlink():
            for _ in range(3):
                if path_obj.is_symlink():
                    path_obj = path_obj.resolve()
                else:
                    break
            path = str(path_obj)
    except (OSError, RuntimeError):
        # If resolution fails, continue with original path
        pass

    # Step 3: Convert /Users/<username>/... to ~/...
    home = Path.home()
    try:
        path_obj = Path(path)
        # Check if path is under home directory
        if path_obj.is_absolute():
            try:
                relative_to_home = path_obj.relative_to(home)
                path = f'~/{relative_to_home}'
            except ValueError:
                # Path is not under home directory
                pass
    except (OSError, ValueError):
        pass

    # Step 4: Expand relative paths to ./
    # Don't add ./ if it already starts with . (like ./ or ../)
    if not path.startswith(('/', '~', '.')):
        # This is a relative path without ./ or ../ prefix
        if project_root:
            # Check if the path exists relative to project_root
            try:
                full_path = project_root / path
                if full_path.exists():
                    path = f'./{path}'
            except (OSError, ValueError):
                pass
        else:
            # No project root, just add ./ prefix
            path = f'./{path}'

    return path


def expand_tilde(path: str) -> str:
    """Expand ~ to actual home path for GLOB pattern matching.

    This is specifically for GLOB patterns where we need to expand ~ to
    the actual home directory path for glob matching to work correctly.

    Args:
        path: Path potentially containing ~ prefix

    Returns:
        Path with ~ expanded to home directory

    Examples:
        >>> expand_tilde('~/projects/*.py')
        '/Users/arnon/projects/*.py'
    """
    if not path or not path.startswith('~'):
        return path

    home = str(Path.home())

    if path == '~':
        return home

    if path.startswith('~/'):
        return home + path[1:]

    # Handle ~username format (though we don't use this currently)
    return path


def normalize_command(command: str, project_root: Optional[Path] = None) -> str:
    """Normalize paths within a command string.

    This function identifies path-like tokens in a command string and normalizes them.
    It handles both absolute and relative paths, preserving the command structure.

    Only normalizes tokens that clearly look like paths:
    - Start with /, ~, or .
    - Contain / (path separator)
    - Have a file extension (e.g., file.txt)

    Plain words without path indicators are left unchanged to avoid false positives.

    Args:
        command: The command string to normalize
        project_root: Optional project root for relative path expansion

    Returns:
        Command with normalized paths

    Examples:
        >>> normalize_command('cat /Users/arnon/file.txt')
        'cat ~/file.txt'
        >>> normalize_command('ls //tmp')
        'ls /tmp'
        >>> normalize_command('echo hello world')
        'echo hello world'  # Plain words unchanged
    """
    if not command:
        return command

    # Split command into tokens
    tokens = command.split()
    normalized_tokens = []

    for i, token in enumerate(tokens):
        # Skip the first token (command itself) and flags
        if i == 0 or token.startswith('-'):
            normalized_tokens.append(token)
            continue

        # Check if token looks like a path
        # Paths typically start with /, ~, ./ or contain / somewhere
        is_path = '/' in token or token.startswith('~') or token.startswith('.')

        # Additional heuristic: if it contains a dot (likely a file extension)
        # but check it's not just any word with a dot
        if not is_path and '.' in token:
            # Check if it looks like a filename (has extension)
            # Example: file.txt, script.py, etc.
            parts = token.rsplit('.', 1)
            if len(parts) == 2 and len(parts[1]) <= 4 and parts[1].isalnum():
                # Likely a file extension
                is_path = True

        if is_path:
            # Try to normalize it as a path
            normalized = normalize_path(token, project_root)
            normalized_tokens.append(normalized)
        else:
            # Not a path, keep as-is
            normalized_tokens.append(token)

    return ' '.join(normalized_tokens)
