"""
Repo-grain project-root resolution for the migration safety gate.

Hierarchy migration (promoting a rule from a project layer up to the user layer)
is only safe when we can name an unambiguous *project boundary*.  The canonical
boundary is the **version-control root**: it is language-agnostic and
unambiguous, whereas a build manifest (``pyproject.toml``, ``package.json``, ...)
can sit in a sub-package *below* the real repo root and give the wrong grain.
The migration grain is therefore the **repository**, not the package.

This module provides a single pure primitive, :func:`resolve_project_root`, that
classifies the situation into a structured :class:`ProjectRootResolution` and
leaves the *decision* (proceed / ask / refuse) to the caller.  The deterministic
core never prompts: when the boundary is unambiguous (a VCS root, or an explicit
persisted override) it resolves it; when only weaker markers exist it returns
``AMBIGUOUS`` with candidate roots for a skill to disambiguate; when nothing is
found it returns ``NONE`` so the gate can refuse.

Relationship to the two existing ``find_project_root`` helpers (intentionally
distinct, NOT a fork):

* :func:`toolguard.config.find_project_root` -- *package*-grain, RAISES; finds the
  nearest ``pyproject.toml``/``.git`` for **config-file discovery** (a package's
  ``.claude`` may legitimately live below the repo root).
* :func:`toolguard.env_config.find_project_root` -- nearest ``.git``/``pyproject``
  or ``None``, for **.env loading**.

Both are nearest-marker finders; neither is repo-grain nor returns the
VCS-vs-other distinction the migration gate needs.  (A future cleanup could share
the trivial walk-up loop across all three; tracked, not done here.)
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple

from toolguard.path_utils import iter_dirs_upward

# VCS markers, in precedence order, are the canonical migration boundary.
VCS_MARKERS: Tuple[str, ...] = (".git", ".hg", ".jj")

# Default, DEFAULTED-and-NON-AUTHORITATIVE indicator list.  It exists only to
# PROPOSE candidate roots and reduce prompting; it never has to be complete, and
# the user may extend it.  VCS markers come first (the safety anchor); the rest
# are build manifests used only to suggest a candidate when no VCS root exists.
DEFAULT_INDICATORS: Tuple[str, ...] = VCS_MARKERS + (
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
        RESOLVED_VCS: A version-control root was found -- the safe migration anchor.
        AMBIGUOUS: No VCS root, but weaker markers offer candidate roots; a caller
            must disambiguate (ask the user) before migrating.
        NONE: No marker at all -- not safe to migrate; refuse.
    """

    RESOLVED_OVERRIDE = "resolved_override"
    RESOLVED_VCS = "resolved_vcs"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


@dataclass(frozen=True)
class RootCandidate:
    """
    A candidate project root proposed from a detected marker.

    Attributes:
        path: Directory containing the marker.
        marker: The marker file/dir name that was found (e.g. ``'pyproject.toml'``).
        is_vcs: Whether the marker is a version-control root marker.
    """

    path: Path
    marker: str
    is_vcs: bool


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
        """Whether an unambiguous root was determined (VCS root or override)."""
        return self.status in (RootStatus.RESOLVED_VCS, RootStatus.RESOLVED_OVERRIDE)

    @property
    def safe_to_migrate(self) -> bool:
        """
        Whether the gate may migrate without further user input.

        Only a VCS-anchored root or an explicit override is sufficient; an
        ``AMBIGUOUS`` or ``NONE`` result must be escalated (ask) or refused.
        """
        return self.is_resolved


def _nearest_vcs(start: Path, markers: Tuple[str, ...]) -> Optional[RootCandidate]:
    """
    Return the nearest VCS root climbing up from ``start``, or ``None``.

    Args:
        start: Directory to start from.
        markers: VCS marker names to look for (subset of :data:`VCS_MARKERS`).

    Returns:
        The nearest :class:`RootCandidate` whose directory holds a VCS marker, or
        ``None`` when none is found within the bounded walk-up.
    """
    for directory in iter_dirs_upward(start):
        for marker in markers:
            if (directory / marker).exists():
                return RootCandidate(path=directory, marker=marker, is_vcs=True)
    return None


def _all_non_vcs_candidates(
    start: Path, markers: Tuple[str, ...]
) -> List[RootCandidate]:
    """
    Collect every non-VCS marker directory climbing up from ``start``.

    Args:
        start: Directory to start from.
        markers: Non-VCS indicator names to look for.

    Returns:
        Candidates in nearest-first order (one per directory+marker that matches).
    """
    candidates: List[RootCandidate] = []
    for directory in iter_dirs_upward(start):
        for marker in markers:
            if (directory / marker).exists():
                candidates.append(
                    RootCandidate(path=directory, marker=marker, is_vcs=False)
                )
    return candidates


def resolve_project_root(
    start_dir: Optional[Path] = None,
    *,
    override: Optional[Path] = None,
    indicators: Tuple[str, ...] = DEFAULT_INDICATORS,
) -> ProjectRootResolution:
    """
    Resolve the migration project boundary as a structured, decision-free result.

    Resolution order: an explicit ``override`` wins; else the nearest
    version-control root (the canonical, repo-grain boundary); else the weaker
    build-marker candidates are returned as ``AMBIGUOUS`` proposals for a caller
    to disambiguate; else ``NONE`` (refuse to migrate).  This function is pure and
    never prompts -- the ask/refuse decision belongs to the skill/CLI layer.

    Args:
        start_dir: Directory to resolve from (defaults to the current directory).
        override: An explicit, previously-persisted project root.  When given it
            is honoured unconditionally (status ``RESOLVED_OVERRIDE``).
        indicators: The detection markers to consider.  Defaults to
            :data:`DEFAULT_INDICATORS`; the list is a non-authoritative
            convenience and may be customised by the caller.  Any entry in
            :data:`VCS_MARKERS` is treated as a version-control anchor; the rest
            are weaker proposal-only markers.

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

    vcs_markers = tuple(m for m in indicators if m in VCS_MARKERS)
    vcs = _nearest_vcs(start, vcs_markers)
    if vcs is not None:
        return ProjectRootResolution(
            status=RootStatus.RESOLVED_VCS,
            root=vcs.path,
            candidates=(),
            reason=(
                f"Version-control root found at {vcs.path} (marker '{vcs.marker}'); "
                f"this is the project boundary for migration."
            ),
        )

    other_markers = tuple(m for m in indicators if m not in VCS_MARKERS)
    candidates = _all_non_vcs_candidates(start, other_markers)
    if candidates:
        listed = ", ".join(f"{c.path} ('{c.marker}')" for c in candidates)
        return ProjectRootResolution(
            status=RootStatus.AMBIGUOUS,
            root=None,
            candidates=tuple(candidates),
            reason=(
                "No version-control root was found, so the project boundary is not "
                f"unambiguous. Candidate roots from build markers: {listed}. Ask the "
                "user which is the project root, or refuse to migrate."
            ),
        )

    return ProjectRootResolution(
        status=RootStatus.NONE,
        root=None,
        candidates=(),
        reason=(
            "No version-control root or project marker was found, so the project "
            "boundary cannot be established; it is not safe to migrate. Put the "
            "project under version control first."
        ),
    )
