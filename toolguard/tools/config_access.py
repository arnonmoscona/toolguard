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
from types import MappingProxyType
from typing import List, Optional, Set, Tuple

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
    ToolPatternLayer,
    load_configuration,
    wrap_tool_pattern,
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


def load_config(start_dir: Optional[Path] = None) -> Configuration:
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


# ---------------------------------------------------------------------------
# Tool discovery helper
# ---------------------------------------------------------------------------


def discover_tools(config: Configuration) -> Tuple[str, ...]:
    """
    Return a sorted tuple of all tool names mentioned in any layer's permission lists.

    A tool name is the text before the first ``"("`` in a ``"Tool(body)"``
    permission pattern string.  Scans allow, deny, and ask lists across every
    discovered config layer.

    This is the canonical tool-discovery implementation extracted from the
    inline loop that :func:`~toolguard.tools.danger.danger` formerly ran
    internally.  Callers in both the audit and context paths share this
    single implementation to prevent drift.

    Args:
        config: The resolved configuration.

    Returns:
        Sorted tuple of unique tool names (e.g. ``('Bash', 'Read', 'Write')``).
    """
    tools_seen: Set[str] = set()
    for layer in config.layers:
        permissions = layer.content.get("permissions", {})
        if isinstance(permissions, dict):
            for perm in (
                permissions.get("allow", [])
                + permissions.get("deny", [])
                + permissions.get("ask", [])
            ):
                if isinstance(perm, str) and "(" in perm and perm.endswith(")"):
                    tool_name = perm[: perm.index("(")]
                    tools_seen.add(tool_name)
    return tuple(sorted(tools_seen))


# ---------------------------------------------------------------------------
# Synthetic-config primitive for proposal evaluation
# ---------------------------------------------------------------------------


def with_layer_rules_replaced(
    config: Configuration,
    tool: str,
    provenance: Provenance,
    list_type: str,
    removed: Set[str],
    added: List[str],
) -> Configuration:
    """
    Return a new :class:`~toolguard.config.Configuration` where, in the single
    layer identified by ``provenance``, the ``list_type`` list (``'allow'``,
    ``'deny'``, or ``'ask'``) for ``tool`` has every pattern in ``removed``
    deleted and every pattern in ``added`` appended.

    This is the canonical synthetic-config builder shared by redundancy analysis,
    consolidation proposals, hierarchy migration, and general edit-proposal
    application (:func:`toolguard.tools.edit_proposal.apply_edits`).  Both
    ``removed`` and ``added`` are wrapper-free pattern bodies; the function
    handles the ``Tool(body)`` wrapping internally, preserving the same form used
    in the raw layer content.

    The modification is SHALLOW: only the target layer's ``list_type`` list is
    reconstructed.  All other layer content -- the other permission lists and all
    patterns for other tools -- is shared by reference via
    :class:`types.MappingProxyType` rebuilding.

    If no layer matches ``provenance``, the original ``config`` is returned
    unchanged (safe fall-through).

    Args:
        config: The original :class:`~toolguard.config.Configuration`.
        tool: Tool name whose list is modified (e.g. ``'Bash'``).
        provenance: The :class:`~toolguard.config.Provenance` identifying which
            layer to modify.  Only the first matching layer is modified.
        list_type: Which permission list to edit: ``'allow'``, ``'deny'``, or
            ``'ask'``.
        removed: Set of wrapper-free pattern bodies to remove.  All occurrences
            of each pattern are removed.
        added: List of wrapper-free pattern bodies to append, in the given order.
            These are appended AFTER removals.

    Returns:
        A new :class:`~toolguard.config.Configuration` with the modified layer,
        or the original ``config`` when ``provenance`` matches no layer.

    Raises:
        ValueError: When ``list_type`` is not one of ``allow``/``deny``/``ask``.
    """
    if list_type not in ("allow", "deny", "ask"):
        raise ValueError(
            f"unknown list_type {list_type!r} (expected 'allow', 'deny', or 'ask')"
        )

    wrapped_removed: Set[str] = {wrap_tool_pattern(tool, p) for p in removed}
    wrapped_added: List[str] = [wrap_tool_pattern(tool, p) for p in added]

    new_layers: List[ConfigLayer] = []
    modified = False

    for layer in config.layers:
        if modified or layer.provenance != provenance:
            new_layers.append(layer)
            continue

        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            new_layers.append(layer)
            continue

        target_list = permissions.get(list_type, [])
        if not isinstance(target_list, list):
            new_layers.append(layer)
            continue

        # Remove all occurrences of each pattern in ``removed``, then append added.
        new_list = [p for p in target_list if p not in wrapped_removed] + wrapped_added
        new_perms = dict(permissions)
        new_perms[list_type] = new_list
        new_content = dict(layer.content)
        new_content["permissions"] = new_perms
        new_layer = ConfigLayer(
            provenance=layer.provenance,
            content=MappingProxyType(new_content),
        )
        new_layers.append(new_layer)
        modified = True

    if not modified:
        return config

    return Configuration(layers=tuple(new_layers), start_dir=config.start_dir)


def with_layer_allow_replaced(
    config: Configuration,
    tool: str,
    provenance: Provenance,
    removed: Set[str],
    added: List[str],
) -> Configuration:
    """
    Allow-list specialisation of :func:`with_layer_rules_replaced`.

    Retained as the canonical allow-only builder used by redundancy analysis,
    consolidation proposals, and hierarchy migration; it simply delegates with
    ``list_type='allow'`` so there is a single implementation.

    Args:
        config: The original :class:`~toolguard.config.Configuration`.
        tool: Tool name whose allow list is modified (e.g. ``'Bash'``).
        provenance: The :class:`~toolguard.config.Provenance` identifying which
            layer to modify.
        removed: Set of wrapper-free pattern bodies to remove from the allow list.
        added: List of wrapper-free pattern bodies to append to the allow list.

    Returns:
        A new :class:`~toolguard.config.Configuration` with the modified layer,
        or the original ``config`` when ``provenance`` matches no layer.
    """
    return with_layer_rules_replaced(
        config, tool, provenance, "allow", removed, added
    )


# ---------------------------------------------------------------------------
# Takeover neutralization helper
# ---------------------------------------------------------------------------


def neutralized_by_takeover(
    pattern: str, is_native: bool, takeover: TakeoverConfig
) -> bool:
    """
    Return True when a native allow pattern is intentionally neutralized by takeover mode.

    A pattern is neutralized when all three conditions hold:

    1. Takeover mode is enabled (``takeover.enabled`` is ``True``).
    2. The pattern originates from a native Claude settings layer (``is_native``).
    3. The extracted pattern appears in the effective ignored-allow set
       (``takeover.normalized_ignored_patterns()``).

    This is the single source of truth for the "native blanket allow
    intentionally in the ignored set under takeover -- skip as a risk"
    rule that :func:`~toolguard.tools.danger.danger` formerly applied
    inline.

    Args:
        pattern: The extracted (tool-wrapper-free) allow pattern to test.
        is_native: Whether the layer that owns the pattern is a native Claude
            settings layer (``provenance.source_type == 'claude'``).
        takeover: The resolved takeover configuration.

    Returns:
        ``True`` when all three conditions hold; ``False`` otherwise.
    """
    return takeover.enabled and is_native and pattern in takeover.normalized_ignored_patterns()


# ---------------------------------------------------------------------------
# Audit context dataclasses and builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerContext:
    """
    Per-layer rule view used by the audit context.

    Carries the full pattern lists for a single configuration layer alongside
    enough metadata for an AI pass to reason about layer identity without
    reimplementing config logic.

    Attributes:
        locus: Human-readable origin label from ``provenance.describe()``.
        is_native: ``True`` when the layer is a native Claude settings file
            (``provenance.source_type == 'claude'``).
        allow: Extracted allow patterns for this tool in this layer.
        deny: Extracted deny patterns for this tool in this layer.
        ask: Extracted ask patterns for this tool in this layer
            (empty for native layers, which have no ask concept).
    """

    locus: str
    is_native: bool
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...]


@dataclass(frozen=True)
class ToolContext:
    """
    Full rule hierarchy for a single tool across all config layers.

    Attributes:
        tool: Tool name (e.g. ``'Bash'``, ``'Read'``).
        layers: Per-layer rule views, most-specific first, matching the order
            returned by :func:`per_layer_rules`.
    """

    tool: str
    layers: Tuple[LayerContext, ...]


@dataclass(frozen=True)
class AuditContext:
    """
    Consolidated configuration context for an AI-assisted security pass.

    Bundles everything the deterministic analyzers see into a single
    serializable object so an LLM skill can receive exactly the same
    consolidated material without reimplementing config logic.

    Attributes:
        summary: High-level configuration summary (discovered files,
            governed tools, layer count, etc.).
        takeover: Resolved takeover-mode configuration.
        tools: Per-tool rule hierarchy, one :class:`ToolContext` per
            tool name found in any layer, sorted by tool name.
        neutralized_allow_patterns: Flat sorted de-duplicated tuple of every
            allow pattern (across all tools and layers) for which
            :func:`neutralized_by_takeover` returns ``True``.  These are
            native blanket allows that takeover mode intentionally suppresses,
            listed here so the AI pass can identify them without rechecking
            the takeover logic itself.
    """

    summary: ConfigSummary
    takeover: TakeoverConfig
    tools: Tuple[ToolContext, ...]
    neutralized_allow_patterns: Tuple[str, ...]


def audit_context(config: Configuration) -> AuditContext:
    """
    Build and return a consolidated :class:`AuditContext` for ``config``.

    Assembles the full rule hierarchy, takeover state, and the set of
    neutralized native blanket allow patterns into one value using only the
    existing config-facade helpers -- no detection logic, no custom parsing.

    ``neutralized_allow_patterns`` is computed from the RAW native layer
    content rather than from :func:`per_layer_rules`, because
    :func:`per_layer_rules` (via ``Configuration.permission_layers``) already
    filters out takeover-suppressed patterns before returning them.  Scanning
    the raw content is the only way to discover which patterns were present in
    the original config but suppressed by takeover mode.

    Args:
        config: The resolved configuration.

    Returns:
        An :class:`AuditContext` ready for serialization and hand-off to an
        AI-assisted audit pass.
    """
    summary = config_summary(config)
    takeover = effective_takeover(config)

    tool_contexts: List[ToolContext] = []
    for tool in discover_tools(config):
        layer_rules = per_layer_rules(config, tool)
        layer_contexts: List[LayerContext] = []
        for lr in layer_rules:
            is_native = lr.provenance.source_type == "claude"
            layer_contexts.append(
                LayerContext(
                    locus=lr.provenance.describe(),
                    is_native=is_native,
                    allow=lr.allow,
                    deny=lr.deny,
                    ask=lr.ask,
                )
            )
        tool_contexts.append(
            ToolContext(
                tool=tool,
                layers=tuple(layer_contexts),
            )
        )

    # Compute neutralized_allow_patterns from raw native layer content.
    # per_layer_rules (via permission_layers) already filters out takeover-
    # suppressed patterns, so we must look at the unfiltered raw allow lists
    # to discover which native patterns are being suppressed.
    neutralized: Set[str] = set()
    if takeover.enabled:
        for layer in config.layers:
            is_native = layer.provenance.source_type == "claude"
            if not is_native:
                continue
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                continue
            for perm in permissions.get("allow", []):
                if not isinstance(perm, str):
                    continue
                if "(" in perm and perm.endswith(")"):
                    body = perm[perm.index("(") + 1 : -1]
                    if neutralized_by_takeover(body, is_native=True, takeover=takeover):
                        neutralized.add(body)

    return AuditContext(
        summary=summary,
        takeover=takeover,
        tools=tuple(tool_contexts),
        neutralized_allow_patterns=tuple(sorted(neutralized)),
    )
