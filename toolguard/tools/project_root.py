"""Re-export of the project-root primitives implemented in :mod:`toolguard.path_utils`."""

from toolguard.path_utils import (
    CONFIG_ROOT_INDICATORS,
    DEFAULT_INDICATORS,
    ProjectRootResolution,
    RootCandidate,
    RootStatus,
    STRONG_PROJECT_ANCHORS,
    resolve_project_root,
)

__all__ = [
    "CONFIG_ROOT_INDICATORS",
    "DEFAULT_INDICATORS",
    "ProjectRootResolution",
    "RootCandidate",
    "RootStatus",
    "STRONG_PROJECT_ANCHORS",
    "resolve_project_root",
]
