"""
Low-level filesystem path helpers shared across toolguard.

Leaf module: it imports only the standard library, so any module (including
low-level ones like :mod:`toolguard.config` and :mod:`toolguard.env_config`) can
use it without risking an import cycle.  It exists to hold the single bounded
"climb toward home" walk-up that several root-finders previously duplicated.
"""

from pathlib import Path
from typing import Iterable, Iterator, Optional


def iter_dirs_upward(start: Path) -> Iterator[Path]:
    """
    Yield ``start`` and each parent directory up to (and including) the home dir.

    The walk stops at the user's home directory or the filesystem root, so it
    never escapes above the user's home.  Both the stopping directory and
    ``start`` itself are yielded.

    Args:
        start: Directory to begin climbing from.

    Yields:
        Each directory from ``start`` upward, inclusive of the stopping point.
    """
    home = Path.home()
    current = start
    while True:
        yield current
        if current == home or current == current.parent:
            return
        current = current.parent


def find_nearest_marker(start: Path, markers: Iterable[str]) -> Optional[Path]:
    """
    Return the nearest ancestor (including ``start``) that holds any marker.

    Climbs from ``start`` toward the home directory and returns the first
    directory containing any of ``markers``, or ``None`` when none is found within
    the bounded walk-up.

    Args:
        start: Directory to begin the search from.
        markers: Marker file/directory names to look for (e.g. ``('.git',
            'pyproject.toml')``).

    Returns:
        The nearest directory containing a marker, or ``None``.
    """
    marker_tuple = tuple(markers)
    for directory in iter_dirs_upward(start):
        for marker in marker_tuple:
            if (directory / marker).exists():
                return directory
    return None
