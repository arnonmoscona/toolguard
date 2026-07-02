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

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Optional, Set, Tuple

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
    ToolPatternLayer,
    load_configuration,
    wrap_tool_pattern,
)
from toolguard.rule_sort import (
    find_section_boundaries,
    parse_permissions_section_with_comments,
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
# Per-rule comment exposure (enables the #NOSECURITY acknowledge-not-hide tag)
# ---------------------------------------------------------------------------

# ``#NOSECURITY`` (optionally ``# NOSECURITY``), case-insensitive, with an
# optional free-form reason after an optional colon.  Mirrors bandit's
# ``# nosec`` precedent.  A bare tag yields an empty ("") reason; an absent tag
# yields ``None`` (see :meth:`RuleComment.nosecurity_reason`).
_NOSECURITY_RE = re.compile(r"#\s*NOSECURITY\b\s*:?\s*(.*)", re.IGNORECASE)


@dataclass(frozen=True)
class RuleComment:
    """
    The source-file comments attached to a single permission rule.

    TOML parsers discard comments, so these are recovered by re-reading the
    layer file and re-associating leading/inline comments with their rule (via
    :func:`~toolguard.rule_sort.parse_permissions_section_with_comments`).  Only
    exists for ``toml`` layers; native ``json`` settings carry no comments.

    Attributes:
        list_type: Which list the rule lives in (``'allow'``/``'deny'``/``'ask'``).
        pattern: The extracted inner pattern body (tool wrapper stripped), aligned
            with the entries in :attr:`LayerContext.allow`/``deny``/``ask``.
        leading: The comment block immediately preceding the rule line (``""``
            when none), newlines preserved.
        inline: The trailing ``#`` comment on the rule's own line (``""`` when none).
    """

    list_type: str
    pattern: str
    leading: str
    inline: str

    def nosecurity_reason(self) -> Optional[str]:
        """
        Return the ``#NOSECURITY`` reason for this rule, or ``None`` when untagged.

        Checks the inline comment first (more specific to the rule), then the
        leading block.  A bare ``#NOSECURITY`` returns ``""`` (tagged, no reason);
        ``#NOSECURITY: <reason>`` returns the stripped reason text.
        """
        for text in (self.inline, self.leading):
            match = _NOSECURITY_RE.search(text)
            if match:
                return match.group(1).strip()
        return None


def _split_tool_pattern(full_pattern: str) -> Tuple[str, str]:
    """
    Split a full ``Tool(body)`` pattern into ``(tool, body)``.

    Falls back to ``("", full_pattern)`` when the pattern has no tool wrapper,
    so bare patterns still key deterministically.
    """
    if "(" in full_pattern and full_pattern.endswith(")"):
        return full_pattern[: full_pattern.index("(")], full_pattern[full_pattern.index("(") + 1 : -1]
    return "", full_pattern


def _inline_comment_after_pattern(line: str) -> str:
    """
    Extract a trailing ``#`` comment that follows the quoted pattern on *line*.

    Locates the closing quote of the pattern (the last quote character on the
    line) and returns the first ``#``-to-end run after it, stripped.  Returns
    ``""`` when there is no trailing comment.  Anchoring on the closing quote
    avoids treating a ``#`` inside the pattern body (e.g. a regex) as a comment.
    """
    last_quote = max(line.rfind("'"), line.rfind('"'))
    if last_quote == -1:
        return ""
    rest = line[last_quote + 1 :]
    hash_pos = rest.find("#")
    return rest[hash_pos:].strip() if hash_pos != -1 else ""


def _layer_comment_map(provenance: Provenance) -> Dict[Tuple[str, str, str], RuleComment]:
    """
    Build a ``(list_type, tool, inner_pattern) -> RuleComment`` map for a layer.

    Reads the layer's TOML file and re-associates comments with rules.  Returns
    an empty map for native (``json``) layers, an unreadable/absent file, or a
    file with no ``[permissions]`` section -- so callers can treat "no comments"
    and "cannot read comments" identically (both degrade to no acknowledgement,
    which is the safe direction: a finding is shown normally rather than hidden).

    Args:
        provenance: Origin of the layer whose file is read.

    Returns:
        Mapping from ``(list_type, tool, inner_pattern)`` to its
        :class:`RuleComment`.  Rules without any comment are omitted.
    """
    if provenance.file_format != "toml":
        return {}
    try:
        text = Path(provenance.path).read_text(encoding="utf-8")
    except OSError:
        return {}

    start, end = find_section_boundaries(text, "permissions")
    if start == -1:
        return {}
    parsed = parse_permissions_section_with_comments(text[start:end])

    result: Dict[Tuple[str, str, str], RuleComment] = {}
    for list_type in ("allow", "deny", "ask"):
        pending_leading = ""
        for item_type, content, value in parsed.get(list_type, []):
            if item_type == "comment_block":
                pending_leading = content
                continue
            if item_type == "rule":
                tool, inner = _split_tool_pattern(value)
                inline = _inline_comment_after_pattern(content)
                if pending_leading or inline:
                    result[(list_type, tool, inner)] = RuleComment(
                        list_type=list_type,
                        pattern=inner,
                        leading=pending_leading,
                        inline=inline,
                    )
                pending_leading = ""
    return result


def rule_comments_for_tool(provenance: Provenance, tool: str) -> Tuple[RuleComment, ...]:
    """
    Return all :class:`RuleComment` records for *tool* in the given layer.

    Convenience wrapper over :func:`_layer_comment_map` that filters to a single
    tool and drops the key, for embedding in :class:`LayerContext`.  Order is
    stable (allow, then deny, then ask; insertion order within each).
    """
    return tuple(
        comment
        for (_, key_tool, _), comment in _layer_comment_map(provenance).items()
        if key_tool == tool
    )


def nosecurity_reason_for(
    provenance: Provenance, list_type: str, tool: str, pattern: str
) -> Optional[str]:
    """
    Return the ``#NOSECURITY`` reason tagged on a specific rule, or ``None``.

    Looks the rule up by ``(list_type, tool, pattern)`` in its layer's recovered
    comment map.  ``None`` means "not tagged" (or the comment could not be read);
    ``""`` means "tagged with no reason"; any other string is the reason.  This
    is the deterministic hook the audit uses to acknowledge-not-hide an
    intentionally-insecure rule.

    Args:
        provenance: Origin of the rule (its layer file is read for comments).
        list_type: ``'allow'``/``'deny'``/``'ask'``.
        tool: Tool name the rule belongs to (e.g. ``'Bash'``).
        pattern: Extracted inner pattern body (tool wrapper stripped).

    Returns:
        The reason string (possibly empty) when tagged, else ``None``.
    """
    comment = _layer_comment_map(provenance).get((list_type, tool, pattern))
    return comment.nosecurity_reason() if comment is not None else None


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
        comments: Per-rule comments recovered from the layer file for this tool
            (leading + inline), one :class:`RuleComment` per commented rule.
            Empty for native (``json``) layers and for rules without comments.
            Exposes the ``#NOSECURITY`` annotations an AI pass reasons about.
    """

    locus: str
    is_native: bool
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...]
    comments: Tuple[RuleComment, ...] = ()


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
                    comments=rule_comments_for_tool(lr.provenance, tool),
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
