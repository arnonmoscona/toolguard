"""
Thin facade over :class:`~toolguard.config.Configuration` for toolguard tooling.

This module provides a small, stable surface for skills and automation tooling to
inspect the toolguard configuration hierarchy without reaching into hook internals
or reimplementing config logic.

All real work delegates to :func:`~toolguard.config.load_configuration` and the
:class:`~toolguard.config.Configuration` methods. This facade only adds convenience
wrappers tailored to the tooling use-cases (per-layer rule listing with provenance,
effective takeover state, etc.).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from toolguard.config import (
    Configuration,
    Provenance,
    TakeoverConfig,
    ToolPatternLayer,
    load_configuration,
)


@dataclass(frozen=True)
class LayerRules:
    """
    Allow, deny, and ask patterns for a single configuration layer, with provenance.

    This is the per-layer view of rules as exposed by the config facade.  It is
    intentionally flat (no extended-syntax interpretation here) so the caller can
    inspect raw patterns as the user authored them.

    Attributes:
        provenance: Origin of this layer (path, level, source type).
        allow: Raw (wrapper-free) allow patterns from this layer.
        deny: Raw (wrapper-free) deny patterns from this layer.
        ask: Raw (wrapper-free) ask patterns from this layer.  These come from
            toolguard_hook layers only (native Claude settings have no ``ask``
            concept).
    """

    provenance: Provenance
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...]


@dataclass(frozen=True)
class ConfigSummary:
    """
    High-level summary of the resolved toolguard configuration for a project.

    Intended for skills that need a quick structural overview without stepping
    through layers individually.

    Attributes:
        start_dir: The directory used to discover the configuration hierarchy.
        project_root: Resolved project root, or None when none was found.
        sources: Human-readable descriptions of all discovered config sources,
            most-specific first.
        governed_tools: Effective list of governed tools (union across levels).
        takeover: Resolved takeover-mode configuration.
        layer_count: Number of discovered config layers.
    """

    start_dir: Optional[Path]
    project_root: Optional[Path]
    sources: Tuple[str, ...]
    governed_tools: Tuple[str, ...]
    takeover: TakeoverConfig
    layer_count: int


def load_config(start_dir: Path = None) -> Configuration:
    """
    Load the toolguard configuration hierarchy starting from ``start_dir``.

    This is a thin re-export of :func:`~toolguard.config.load_configuration`
    with ``ignore_env_override=True`` so that a stale ``CLAUDE_SETTINGS_PATH``
    environment variable does not divert the hierarchy walk away from the
    project.  Tools always want the project-rooted hierarchy, not a single
    explicit file.

    Args:
        start_dir: Directory to start project-root discovery from.  Defaults to
            the current working directory when ``None``.

    Returns:
        An immutable :class:`~toolguard.config.Configuration` object.
    """
    return load_configuration(start_dir, ignore_env_override=True)


def per_layer_rules(config: Configuration, tool_name: str) -> List[LayerRules]:
    """
    Return per-layer allow/deny/ask rules for ``tool_name``, most-specific first.

    Delegates to :meth:`~toolguard.config.Configuration.permission_layers` for
    the allow/deny portion (takeover filtering already applied there) and reads
    the ``ask`` list directly from each layer's raw content.

    Args:
        config: The resolved configuration.
        tool_name: Tool to extract rules for (e.g. ``'Bash'``, ``'Read'``).

    Returns:
        List of :class:`LayerRules`, one per discovered config layer, ordered
        most-specific first.
    """
    prefix = f"{tool_name}("
    # permission_layers returns ToolPatternLayer objects (allow + deny, takeover-filtered)
    tool_layers: Tuple[ToolPatternLayer, ...] = config.permission_layers(tool_name)

    # Build a provenance -> ToolPatternLayer index for quick lookup
    prov_to_tool_layer = {tl.provenance: tl for tl in tool_layers}

    result: List[LayerRules] = []
    for layer in config.layers:
        tl = prov_to_tool_layer.get(layer.provenance)
        # allow and deny come from the ToolPatternLayer (with takeover filtering)
        allow = tl.allow if tl is not None else ()
        deny = tl.deny if tl is not None else ()

        # ask patterns: toolguard extension, only in toolguard_hook layers
        ask: List[str] = []
        if not layer.is_native:
            permissions = layer.content.get("permissions", {})
            if isinstance(permissions, dict):
                for perm in permissions.get("ask", []):
                    if (
                        isinstance(perm, str)
                        and perm.startswith(prefix)
                        and perm.endswith(")")
                    ):
                        ask.append(perm[len(prefix):-1])

        result.append(
            LayerRules(
                provenance=layer.provenance,
                allow=allow,
                deny=deny,
                ask=tuple(ask),
            )
        )

    return result


def effective_takeover(config: Configuration) -> TakeoverConfig:
    """
    Return the resolved takeover-mode configuration.

    Thin wrapper over :meth:`~toolguard.config.Configuration.takeover_mode`.

    Args:
        config: The resolved configuration.

    Returns:
        A :class:`~toolguard.config.TakeoverConfig` describing the effective
        takeover state, the ignored allow patterns, and whether a conflict was
        detected.
    """
    return config.takeover_mode()


def config_summary(config: Configuration) -> ConfigSummary:
    """
    Return a high-level summary of the configuration.

    Useful for skills that need a quick structural overview of what was
    discovered (which files, how many levels, which tools are governed, etc.)
    without stepping through individual layer details.

    Args:
        config: The resolved configuration.

    Returns:
        A :class:`ConfigSummary` describing the configuration.
    """
    return ConfigSummary(
        start_dir=config.start_dir,
        project_root=config.project_root,
        sources=tuple(config.describe_sources()),
        governed_tools=config.governed_tools(),
        takeover=config.takeover_mode(),
        layer_count=len(config.layers),
    )
