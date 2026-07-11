"""
Low-level filesystem path helpers shared across toolguard.

Leaf module: it imports only the standard library, so any module (including
low-level ones like :mod:`toolguard.config` and :mod:`toolguard.env_config`) can
use it without risking an import cycle. Notably, :mod:`toolguard.hook` (the live
runtime hook) imports :mod:`toolguard.config`/:mod:`toolguard.env_config`
directly, and :mod:`toolguard.tools` is documented as deliberately segregated
from that runtime path -- so anything shared with the hook's config/env loaders
must live in a leaf module like this one, never in :mod:`toolguard.tools`.

It hosts:

* :func:`iter_dirs_upward` / :func:`find_nearest_marker` -- the single bounded
  "climb toward home" walk-up that several root-finders previously duplicated.
* :data:`STRONG_PROJECT_ANCHORS` / :data:`CONFIG_ROOT_INDICATORS` /
  :data:`DEFAULT_INDICATORS` -- the canonical, shared marker sets (TOO-15).
* :func:`resolve_project_root` (with :class:`RootStatus` /
  :class:`RootCandidate` / :class:`ProjectRootResolution`) -- the single
  primitive (TOO-15) that implements BOTH walk-up shapes previously duplicated
  across :mod:`toolguard.config`, :mod:`toolguard.env_config`, and
  :mod:`toolguard.tools.project_root`:

  * ``strict=True`` ("nearest marker of any kind wins", a single flat walk-up
    over the given ``indicators``): used by the runtime config/env loaders,
    which only ever need one unambiguous directory and never distinguish
    marker "trust tiers".
  * ``strict=False`` (the default; "climb fully for the anchor tier first, and
    only fall back to the weaker build-manifest tier -- as an ask-first
    ``AMBIGUOUS`` proposal -- when no anchor exists anywhere"): used by the
    migration safety gate, which must never silently pick the wrong repo
    grain (a build manifest can sit in a sub-package below the real root).

  :mod:`toolguard.tools.project_root` re-exports this primitive unchanged for
  its existing callers (``migration_gate.py``, ``corpus.py``) and their tests.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple


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


# Strong project anchors, in precedence order: a version-control root (``.git``,
# ``.hg``, ``.jj``) or an explicit Claude Code project marker (``.claude``
# directory, ``CLAUDE.md`` file) is unambiguous evidence of a project root --
# the SAME trust tier as version control, not a weaker "ask first" candidate
# (TOO-15). This is the single canonical marker tuple; nothing else in the
# codebase should hardcode its own copy.
STRONG_PROJECT_ANCHORS: Tuple[str, ...] = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")

# The marker set for the "nearest marker of any kind wins" (strict) resolution
# used by toolguard.config.find_project_root and
# toolguard.env_config.find_project_root -- the runtime config/env loaders. It
# is deliberately narrower than DEFAULT_INDICATORS below (no package.json/
# go.mod/Cargo.toml/... ) because those two loaders have never searched for
# non-Python build manifests; only pyproject.toml plus the strong anchors.
CONFIG_ROOT_INDICATORS: Tuple[str, ...] = STRONG_PROJECT_ANCHORS + ("pyproject.toml",)

# Default, DEFAULTED-and-NON-AUTHORITATIVE indicator list for the tiered
# (strict=False) migration-gate resolution.  It exists only to PROPOSE
# candidate roots and reduce prompting; it never has to be complete, and the
# caller may extend it.  STRONG_PROJECT_ANCHORS come first (the safety
# anchor tier); the rest are build manifests used only to suggest a candidate
# when no anchor exists.
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
        RESOLVED_OVERRIDE: An explicit, persisted user override is in effect.
        RESOLVED_ANCHOR: A project anchor was found -- either a strong anchor
            (version control, or a Claude Code ``.claude``/``CLAUDE.md``
            marker) in the tiered (``strict=False``) resolution, or the
            nearest marker of any kind in the flat (``strict=True``)
            resolution. In both cases this is the safe migration boundary /
            unambiguous root.
        AMBIGUOUS: Tiered resolution only: no anchor, but weaker build-manifest
            markers offer candidate roots; a caller must disambiguate (ask the
            user) before migrating. Never produced in ``strict=True`` mode.
        NONE: No marker at all -- not safe to migrate; refuse.
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
        is_anchor: Whether the marker is a strong project anchor (version
            control, or a Claude Code project marker) as opposed to a weaker,
            ask-first build-manifest marker.
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
        candidates: Candidate roots to propose when ``status`` is ``AMBIGUOUS``
            (in nearest-first order); empty otherwise.
        reason: A calibrated, render-ready explanation.  It deliberately never
            claims a migration is "safe" -- only that a boundary was or was not
            unambiguously found.
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
        """
        Whether the gate may migrate without further user input.

        Only an anchor-resolved root or an explicit override is sufficient; an
        ``AMBIGUOUS`` or ``NONE`` result must be escalated (ask) or refused.
        """
        return self.is_resolved


def _nearest_anchor(start: Path, markers: Tuple[str, ...]) -> Optional[RootCandidate]:
    """
    Return the nearest strong-anchor root climbing up from ``start``, or ``None``.

    Args:
        start: Directory to start from.
        markers: Anchor marker names to look for (subset of
            :data:`STRONG_PROJECT_ANCHORS`).

    Returns:
        The nearest :class:`RootCandidate` whose directory holds an anchor
        marker, or ``None`` when none is found within the bounded walk-up.
    """
    for directory in iter_dirs_upward(start):
        for marker in markers:
            if (directory / marker).exists():
                return RootCandidate(path=directory, marker=marker, is_anchor=True)
    return None


def _all_non_anchor_candidates(
    start: Path, markers: Tuple[str, ...]
) -> List[RootCandidate]:
    """
    Collect every non-anchor marker directory climbing up from ``start``.

    Args:
        start: Directory to start from.
        markers: Non-anchor (weaker, ask-first) indicator names to look for.

    Returns:
        Candidates in nearest-first order (one per directory+marker that matches).
    """
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
    Resolve a project root as a structured, decision-free result.

    Two resolution shapes, selected by ``strict``:

    * ``strict=False`` (the default -- the migration-gate shape): an explicit
      ``override`` wins; else the nearest strong-anchor root (the canonical,
      repo-grain boundary, climbed for FIRST across the whole walk-up); else
      the weaker build-marker candidates are returned as ``AMBIGUOUS``
      proposals for a caller to disambiguate; else ``NONE`` (refuse to
      migrate).
    * ``strict=True`` (the config/env-loader shape): an explicit ``override``
      still wins; else a SINGLE flat walk-up treating every marker in
      ``indicators`` as equally trusted, returning the directory holding the
      NEAREST marker of any kind (status ``RESOLVED_ANCHOR``); else ``NONE``.
      This mode NEVER returns ``AMBIGUOUS`` -- callers that only need one
      unambiguous directory (not a disambiguation prompt) get a direct answer.

    This function is pure and never prompts -- the ask/refuse decision belongs
    to the caller.

    Args:
        start_dir: Directory to resolve from (defaults to the current directory).
        strict: Selects the flat "nearest marker wins" shape instead of the
            tiered anchor-first shape. Defaults to ``False`` (unchanged
            behaviour for existing callers).
        override: An explicit, previously-persisted project root.  When given
            it is honoured unconditionally (status ``RESOLVED_OVERRIDE``),
            regardless of ``strict``.
        indicators: The detection markers to consider.  Defaults to
            :data:`DEFAULT_INDICATORS`; the list is a non-authoritative
            convenience and may be customised by the caller.  In the
            ``strict=False`` shape, any entry in :data:`STRONG_PROJECT_ANCHORS`
            is treated as a strong anchor and the rest are weaker
            proposal-only markers; in the ``strict=True`` shape all entries
            are equally trusted.

    Returns:
        A :class:`ProjectRootResolution` describing what was found.
    """
    start = (start_dir or Path.cwd()).resolve()

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
