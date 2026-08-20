"""
Low-level filesystem path helpers: the bounded walk up the parent directories,
the project-root marker sets, and project-root resolution.

Foundation layer: stdlib plus :mod:`toolguard.ambient`, which is where the home
and current directories come from.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

from toolguard import ambient


def iter_dirs_upward(start: Path) -> Iterator[Path]:
    """
    Yield ``start``, then each parent, stopping at the home directory or at the
    top of the path -- ``/`` for an absolute path, ``.`` for a relative one.

    Home is recognised by exact equality with :func:`ambient.home`, so a walk
    that starts outside home never meets it and runs all the way to the top.

    Args:
        start: Directory to begin climbing from.

    Yields:
        Each directory from ``start`` upward, including the stopping point.
    """
    home = ambient.home()
    current = start
    while True:
        yield current
        if current == home or current == current.parent:
            return
        current = current.parent


def find_nearest_marker(start: Path, markers: Iterable[str]) -> Optional[Path]:
    """
    Return the nearest directory at or above ``start`` holding any of ``markers``.

    Stops at the home directory or the top, whichever comes first.

    Args:
        start: Directory to begin the search from.
        markers: Marker file/directory names to look for (e.g. ``('.git',
            'pyproject.toml')``).

    Returns:
        The nearest directory containing a marker, or ``None`` when the walk
        finds none.
    """
    marker_tuple = tuple(markers)
    for directory in iter_dirs_upward(start):
        for marker in marker_tuple:
            if (directory / marker).exists():
                return directory
    return None


#: Markers that identify a project root on their own: a version-control root
#: (``.git``, ``.hg``, ``.jj``) or an explicit Claude Code project marker
#: (``.claude`` directory, ``CLAUDE.md`` file). The tiered resolution below
#: trusts these over build manifests, which can sit in a sub-package well below
#: the real root.
STRONG_PROJECT_ANCHORS: Tuple[str, ...] = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")

#: Marker set for config-root discovery: the strong anchors plus
#: ``pyproject.toml``, and nothing else -- narrower than
#: :data:`DEFAULT_INDICATORS`, which also lists non-Python build manifests.
CONFIG_ROOT_INDICATORS: Tuple[str, ...] = STRONG_PROJECT_ANCHORS + ("pyproject.toml",)

#: Default ``indicators`` for :func:`resolve_project_root`: the strong anchors
#: followed by build manifests. Deliberately neither authoritative nor
#: complete -- a caller may pass its own list.
DEFAULT_INDICATORS: Tuple[str, ...] = STRONG_PROJECT_ANCHORS + (
    "pyproject.toml",
    "package.json",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
    "CMakeLists.txt",
)


class RootStatus(str, Enum):
    """
    Classification of a project-root resolution.

    Attributes:
        RESOLVED_OVERRIDE: An explicit ``override`` was supplied and honoured.
        RESOLVED_ANCHOR: A root was found by climbing -- a strong anchor in the
            tiered (``strict=False``) resolution, or the nearest marker of any
            kind in the flat (``strict=True``) one.
        AMBIGUOUS: Tiered resolution only: no anchor, but weaker build-manifest
            markers offer candidate roots for the caller to choose between.
        NONE: Nothing found.
    """

    RESOLVED_OVERRIDE = "resolved_override"
    RESOLVED_ANCHOR = "resolved_anchor"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True)
class RootCandidate:
    """
    A candidate project root proposed from a detected marker.

    Attributes:
        path: Directory containing the marker.
        marker: The marker file/dir name that was found (e.g. ``'pyproject.toml'``).
        is_anchor: Whether *marker* is one of :data:`STRONG_PROJECT_ANCHORS`
            rather than a weaker build manifest.
    """

    path: Path
    marker: str
    is_anchor: bool


@dataclass(frozen=True)
class ProjectRootResolution:
    """
    Structured result of :func:`resolve_project_root`.

    Attributes:
        status: The :class:`RootStatus` classification.
        root: The resolved root directory when ``status`` is a ``RESOLVED_*``
            value, else ``None``.
        candidates: Candidate roots when ``status`` is ``AMBIGUOUS``, nearest
            first; empty otherwise. One entry per matching directory-and-marker
            pair, so a directory holding two build manifests appears twice.
        reason: Render-ready explanation of what was found.
    """

    status: RootStatus
    root: Optional[Path]
    candidates: Tuple[RootCandidate, ...]
    reason: str

    @property
    def is_resolved(self) -> bool:
        """Whether an unambiguous root was determined (anchor root or override)."""
        return self.status in (RootStatus.RESOLVED_ANCHOR, RootStatus.RESOLVED_OVERRIDE)

    @property
    def safe_to_migrate(self) -> bool:
        """Whether a caller may migrate without asking the user."""
        return self.is_resolved


def _nearest_anchor(start: Path, markers: Tuple[str, ...]) -> Optional[RootCandidate]:
    """Nearest directory at or above ``start`` holding an anchor marker, or ``None``."""
    for directory in iter_dirs_upward(start):
        for marker in markers:
            if (directory / marker).exists():
                return RootCandidate(path=directory, marker=marker, is_anchor=True)
    return None


def _all_non_anchor_candidates(
    start: Path, markers: Tuple[str, ...]
) -> List[RootCandidate]:
    """Every directory-and-marker match at or above ``start``, nearest first."""
    candidates: List[RootCandidate] = []
    for directory in iter_dirs_upward(start):
        for marker in markers:
            if (directory / marker).exists():
                candidates.append(
                    RootCandidate(path=directory, marker=marker, is_anchor=False)
                )
    return candidates


def resolve_project_root(
    start_dir: Optional[Path] = None,
    *,
    strict: bool = False,
    override: Optional[Path] = None,
    indicators: Tuple[str, ...] = DEFAULT_INDICATORS,
) -> ProjectRootResolution:
    """
    Resolve a project root, and classify the result rather than acting on it.

    Two shapes, selected by ``strict``:

    * ``strict=False`` (the default, tiered): an ``override`` wins; else the
      nearest strong anchor, searched for across the whole walk-up before any
      weaker marker is considered; else every build-manifest match is returned
      as ``AMBIGUOUS`` candidates; else ``NONE``.
    * ``strict=True`` (flat): an ``override`` still wins; else the nearest
      marker of any kind in ``indicators``, all equally trusted, as
      ``RESOLVED_ANCHOR``; else ``NONE``. Never returns ``AMBIGUOUS``.

    Decides nothing and never prompts, but is not pure: it reads the
    filesystem, and the current directory when ``start_dir`` is omitted.

    Args:
        start_dir: Directory to resolve from; defaults to the current
            directory. Passed through ``Path.resolve`` before the walk.
        strict: Select the flat shape instead of the tiered one.
        override: An explicit project root, honoured unconditionally and
            regardless of ``strict``. Resolved but NOT checked for existence --
            a path that is not there is returned as the root.
        indicators: The markers to consider, defaulting to
            :data:`DEFAULT_INDICATORS`. In the tiered shape, entries that are
            in :data:`STRONG_PROJECT_ANCHORS` form the anchor tier and the rest
            are proposal-only; ``strict=True`` treats them all alike.

    Returns:
        A :class:`ProjectRootResolution` describing what was found.
    """
    start = (start_dir or ambient.cwd()).resolve()

    if override is not None:
        resolved = override.resolve()
        return ProjectRootResolution(
            status=RootStatus.RESOLVED_OVERRIDE,
            root=resolved,
            candidates=(),
            reason=f"Using the configured project-root override at {resolved}.",
        )

    if strict:
        found = find_nearest_marker(start, indicators)
        if found is not None:
            return ProjectRootResolution(
                status=RootStatus.RESOLVED_ANCHOR,
                root=found,
                candidates=(),
                reason=f"Nearest project marker found at {found}.",
            )
        return ProjectRootResolution(
            status=RootStatus.NONE,
            root=None,
            candidates=(),
            reason=(
                "No project marker was found within the bounded walk-up to the "
                "home directory."
            ),
        )

    anchor_markers = tuple(m for m in indicators if m in STRONG_PROJECT_ANCHORS)
    anchor = _nearest_anchor(start, anchor_markers)
    if anchor is not None:
        return ProjectRootResolution(
            status=RootStatus.RESOLVED_ANCHOR,
            root=anchor.path,
            candidates=(),
            reason=(
                f"Project anchor found at {anchor.path} (marker '{anchor.marker}'); "
                f"this is the project boundary for migration."
            ),
        )

    weak_markers = tuple(m for m in indicators if m not in STRONG_PROJECT_ANCHORS)
    candidates = _all_non_anchor_candidates(start, weak_markers)
    if candidates:
        listed = ", ".join(f"{c.path} ('{c.marker}')" for c in candidates)
        return ProjectRootResolution(
            status=RootStatus.AMBIGUOUS,
            root=None,
            candidates=tuple(candidates),
            reason=(
                "No project anchor (version control, or a Claude Code project "
                "marker such as .claude or CLAUDE.md) was found, so the project "
                f"boundary is not unambiguous. Candidate roots from build "
                f"markers: {listed}. Ask the user which is the project root, or "
                "refuse to migrate."
            ),
        )

    return ProjectRootResolution(
        status=RootStatus.NONE,
        root=None,
        candidates=(),
        reason=(
            "No project anchor or project marker was found, so the project "
            "boundary cannot be established; it is not safe to migrate. Put the "
            "project under version control, or add a .claude directory or "
            "CLAUDE.md file, first."
        ),
    )


def require_project_root(start_dir: Optional[Path] = None) -> Path:
    """
    Resolve a project root in the flat (``strict=True``) shape, or raise.

    Climbs from *start_dir* (or the current directory) to the nearest
    :data:`CONFIG_ROOT_INDICATORS` marker.

    Args:
        start_dir: Directory to start searching from. Defaults to the current
            working directory.

    Returns:
        Path to the project root.

    Raises:
        RuntimeError: If the walk-up finds no marker.
    """
    start = Path(start_dir) if start_dir else ambient.cwd()
    resolution = resolve_project_root(
        start, strict=True, indicators=CONFIG_ROOT_INDICATORS
    )
    if resolution.root is None:
        raise RuntimeError(
            f"Project root not found. Searched from {start.resolve()} upward, stopping "
            f"at {ambient.home()} or the filesystem root, for any of: "
            f"{', '.join(CONFIG_ROOT_INDICATORS)}. Something is badly wrong."
        )
    return resolution.root
