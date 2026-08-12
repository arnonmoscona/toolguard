"""
Configuration access for toolguard's own skills and dev tooling: per-layer rule views
with provenance, a structural summary, tool discovery, and a synthetic-config builder
that applies a proposed rule edit in memory rather than to a file.

TOML parsers discard comments, so a loaded :class:`~toolguard.config.Configuration`
cannot see the ``#NOSECURITY`` acknowledgement tag. This module re-reads the layer
file to recover it -- see :func:`_layer_comment_map`.
"""

import re
import tomllib
from dataclasses import dataclass, replace
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
from toolguard.rule_entry import normalize_entry
from toolguard.rule_sort import (
    find_section_boundaries,
    parse_permissions_section_with_comments,
)


@dataclass(frozen=True)
class LayerRules:
    """
    One configuration layer's allow, deny and ask patterns, with provenance.

    Patterns are wrapper-free but otherwise uninterpreted -- an extended-syntax
    prefix such as ``[regex]`` is left on the string for the caller to read.

    Attributes:
        provenance: Origin of this layer (path, level, source type).
        allow: Allow patterns from this layer. On a native layer under takeover
            mode, the ignored blanket allows have already been removed.
        deny: Deny patterns from this layer.
        ask: Ask patterns from this layer. Always empty for a NATIVE layer --
            :func:`per_layer_rules` drops those, though
            :meth:`~toolguard.config.Configuration.permission_layers` returns
            them.
    """

    provenance: Provenance
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...]


@dataclass(frozen=True)
class ConfigSummary:
    """
    High-level summary of the resolved toolguard configuration for a project.

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

    :func:`~toolguard.config.load_configuration` with
    ``ignore_env_override=True``: tooling always wants the project-rooted
    hierarchy, never the single explicit file a stale ``CLAUDE_SETTINGS_PATH``
    would otherwise select.

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

    All three lists come from
    :meth:`~toolguard.config.Configuration.permission_layers`, which has
    already applied takeover filtering and normalized structured
    (``{match = ..., ...}``) entries. EVERY discovered layer gets a
    :class:`LayerRules`, including one that contributes no rule for this tool.
    Ask is dropped for native layers -- see :attr:`LayerRules.ask`.

    Args:
        config: The resolved configuration.
        tool_name: Tool to extract rules for (e.g. ``'Bash'``, ``'Read'``).
    """
    tool_layers: Tuple[ToolPatternLayer, ...] = config.permission_layers(tool_name)

    prov_to_tool_layer = {tl.provenance: tl for tl in tool_layers}

    result: List[LayerRules] = []
    for layer in config.layers:
        tl = prov_to_tool_layer.get(layer.provenance)
        allow = tl.allow if tl is not None else ()
        deny = tl.deny if tl is not None else ()
        ask = tl.ask if (tl is not None and not layer.is_native) else ()

        result.append(
            LayerRules(
                provenance=layer.provenance,
                allow=allow,
                deny=deny,
                ask=ask,
            )
        )

    return result


def effective_takeover(config: Configuration) -> TakeoverConfig:
    """Return the resolved takeover-mode configuration."""
    return config.takeover_mode()


def config_summary(config: Configuration) -> ConfigSummary:
    """Return a high-level :class:`ConfigSummary` of the configuration."""
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
    Return every tool name appearing in a ``[permissions]`` list, sorted.

    A tool name is the text before the first ``"("`` of a ``Tool(body)``
    pattern. The ``allow``, ``deny`` and ``ask`` lists of every discovered
    layer are scanned, native and toolguard alike; ``[hard_deny]`` is NOT, so a
    tool governed only by a hard-deny rule does not appear here.

    Each element is normalized first, so a structured (``{match = ..., ...}``)
    entry names its tool exactly as a plain string does -- except in a native
    layer, where a structured entry is not recognized at all.

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
                entry, _issues = normalize_entry(perm, layer.is_native)
                if entry is None:
                    continue
                pattern = entry.pattern
                if "(" in pattern and pattern.endswith(")"):
                    tool_name = pattern[: pattern.index("(")]
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
    Return a new :class:`~toolguard.config.Configuration` with one layer's
    permission list edited.

    In the layer identified by ``provenance``, the ``list_type`` list for
    ``tool`` loses every pattern in ``removed`` and gains every pattern in
    ``added``, appended after the removals. Both hold wrapper-free pattern
    bodies; the ``Tool(body)`` wrapping is applied here.

    The rewrite is SHALLOW: only the target layer's ``list_type`` list is
    rebuilt. Every other permission list, and every other tool's patterns in
    the same list, is shared by reference with the original.

    Args:
        config: The original :class:`~toolguard.config.Configuration`.
        tool: Tool name whose list is modified (e.g. ``'Bash'``).
        provenance: Identifies the layer to modify. Only the FIRST matching
            layer is modified.
        list_type: ``'allow'``, ``'deny'``, or ``'ask'``.
        removed: Pattern bodies to remove; every occurrence of each one goes.
        added: Pattern bodies to append, in the given order.

    Returns:
        A new :class:`~toolguard.config.Configuration` with the modified layer.
        The original ``config`` object is returned unchanged when ``provenance``
        matches no layer, and also when the matched layer's ``permissions`` is
        not a table or its ``list_type`` value is not a list.

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

        # Membership is decided on the NORMALIZED pattern, never on the raw
        # element: a structured entry is a `dict`, so `element in
        # wrapped_removed` would try to hash it and raise `TypeError`.
        #
        # A kept element is re-appended as the original `str`/`dict` object,
        # not a re-rendering of it, so editing one pattern never reformats a
        # neighbour. An element that fails to normalize is kept for the same
        # reason: this function edits a list, it does not validate one.
        new_list = []
        for element in target_list:
            entry, _issues = normalize_entry(element, is_native=layer.is_native)
            if entry is not None and entry.pattern in wrapped_removed:
                continue
            new_list.append(element)
        new_list = new_list + wrapped_added
        new_perms = dict(permissions)
        new_perms[list_type] = new_list
        new_content = dict(layer.content)
        new_content["permissions"] = new_perms
        # `dataclasses.replace`, not a fresh `ConfigLayer(...)`: every
        # non-`content` field carries through instead of silently resetting to
        # its default.
        new_layer = replace(layer, content=MappingProxyType(new_content))
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

    Arguments and return value are that function's, with ``list_type='allow'``.
    """
    return with_layer_rules_replaced(config, tool, provenance, "allow", removed, added)


# ---------------------------------------------------------------------------
# Takeover neutralization helper
# ---------------------------------------------------------------------------


def neutralized_by_takeover(
    pattern: str, is_native: bool, takeover: TakeoverConfig
) -> bool:
    """
    Return True when a native allow pattern is intentionally neutralized by takeover mode.

    Such a pattern is still written in the config file, but takeover mode strips
    it from the native layer's allow list before any resolution reads it.

    Args:
        pattern: The extracted (tool-wrapper-free) allow pattern to test.
        is_native: Whether the layer that owns the pattern is a native Claude
            settings layer (``provenance.source_type == 'claude'``).
        takeover: The resolved takeover configuration.
    """
    return (
        takeover.enabled
        and is_native
        and pattern in takeover.normalized_ignored_patterns()
    )


# ---------------------------------------------------------------------------
# Per-rule comment exposure (enables the #NOSECURITY acknowledge-not-hide tag)
# ---------------------------------------------------------------------------

#: ``#NOSECURITY`` (or ``# NOSECURITY``), case-insensitive, with an optional
#: free-form reason after an optional colon. Group 1 is the reason, empty for a
#: bare tag.
_NOSECURITY_RE = re.compile(r"#\s*NOSECURITY\b\s*:?\s*(.*)", re.IGNORECASE)


@dataclass(frozen=True)
class RuleComment:
    """
    The source-file comments attached to a single permission rule.

    Recovered by re-reading the layer file (see :func:`_layer_comment_map`), and
    produced for TOML layers only.

    Attributes:
        list_type: Which list the rule lives in (``'allow'``/``'deny'``/``'ask'``).
        pattern: The rule's inner pattern body, tool wrapper stripped -- the
            same form as :attr:`LayerContext.allow`/``deny``/``ask``.
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

        The inline comment wins over the leading block, being the more
        specific of the two. A bare tag returns ``""``, not ``None``.
        """
        for text in (self.inline, self.leading):
            match = _NOSECURITY_RE.search(text)
            if match:
                return match.group(1).strip()
        return None


def _split_tool_pattern(full_pattern: str) -> Tuple[str, str]:
    """
    Split a full ``Tool(body)`` pattern into ``(tool, body)``, or into
    ``("", full_pattern)`` when there is no wrapper.
    """
    if "(" in full_pattern and full_pattern.endswith(")"):
        return full_pattern[: full_pattern.index("(")], full_pattern[
            full_pattern.index("(") + 1 : -1
        ]
    return "", full_pattern


def _inline_comment_after_pattern(line: str) -> str:
    """
    Extract a trailing ``#`` comment that follows a rule's own quoted value(s).

    Returns ``""`` when there is none. Anchoring on the LAST quote in *line*
    is what keeps a ``#`` inside a quoted value -- a regex body, a structured
    entry's ``additionalContext`` -- from being read as the start of a comment.
    """
    last_quote = max(line.rfind("'"), line.rfind('"'))
    if last_quote == -1:
        return ""
    rest = line[last_quote + 1 :]
    hash_pos = rest.find("#")
    return rest[hash_pos:].strip() if hash_pos != -1 else ""


def _layer_comment_map(
    provenance: Provenance,
) -> Dict[Tuple[str, str, str], RuleComment]:
    """
    Build a ``(list_type, tool, inner_pattern) -> RuleComment`` map for a layer.

    Best-effort ENRICHMENT read: it yields an empty map for a layer that is not
    TOML, for a file that is missing or fails to open, for a file with no
    ``[permissions]`` section, and for a ``[permissions]`` section that does not
    parse as TOML. Failing quietly is deliberate -- one malformed file must not
    abort a whole tooling run, and what is lost here is a comment, never a rule.

    Args:
        provenance: Origin of the layer whose file is read.

    Returns:
        Mapping from ``(list_type, tool, inner_pattern)`` to its
        :class:`RuleComment`. Rules without any comment are omitted.
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
    try:
        parsed = parse_permissions_section_with_comments(text[start:end])
    except tomllib.TOMLDecodeError:
        return {}

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


def rule_comments_for_tool(
    provenance: Provenance, tool: str
) -> Tuple[RuleComment, ...]:
    """
    Return all :class:`RuleComment` records for *tool* in the given layer.

    Ordered allow, then deny, then ask; source order within each list.
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

    ``None`` means "not tagged" -- and also covers "the layer's comments could
    not be read at all", which :func:`_layer_comment_map` does not distinguish.
    ``""`` means "tagged with no reason"; any other string is the reason.

    Args:
        provenance: Origin of the rule (its layer file is read for comments).
        list_type: ``'allow'``/``'deny'``/``'ask'``.
        tool: Tool name the rule belongs to (e.g. ``'Bash'``).
        pattern: Extracted inner pattern body (tool wrapper stripped).
    """
    comment = _layer_comment_map(provenance).get((list_type, tool, pattern))
    return comment.nosecurity_reason() if comment is not None else None


# ---------------------------------------------------------------------------
# Audit context dataclasses and builder
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerContext:
    """
    One layer's rules for one tool, as the audit context carries them.

    Attributes:
        locus: Human-readable origin label from ``provenance.describe()``.
        is_native: ``True`` when the layer is a native Claude settings file
            (``provenance.source_type == 'claude'``).
        allow: Extracted allow patterns for this tool in this layer.
        deny: Extracted deny patterns for this tool in this layer.
        ask: Extracted ask patterns for this tool in this layer -- always
            empty for a native layer, see :attr:`LayerRules.ask`.
        comments: One :class:`RuleComment` per commented rule for this tool,
            carrying the ``#NOSECURITY`` tags. An uncommented rule is absent
            from it, and a non-TOML layer contributes none at all.
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

    Attributes:
        summary: High-level configuration summary (discovered files,
            governed tools, layer count, etc.).
        takeover: Resolved takeover-mode configuration.
        tools: Per-tool rule hierarchy, one :class:`ToolContext` per tool name
            :func:`discover_tools` found, sorted by tool name.
        neutralized_allow_patterns: Sorted, de-duplicated pattern BODIES of the
            native allow rules takeover mode suppresses; empty when takeover
            mode is off. The tool wrapper is dropped before de-duplication, so
            ``Bash(*)`` and ``Read(*)`` collapse into a single ``'*'`` and the
            tool they came from is not recoverable from this tuple.
    """

    summary: ConfigSummary
    takeover: TakeoverConfig
    tools: Tuple[ToolContext, ...]
    neutralized_allow_patterns: Tuple[str, ...]


def audit_context(config: Configuration) -> AuditContext:
    """
    Build and return a consolidated :class:`AuditContext` for ``config``.

    ``neutralized_allow_patterns`` is computed from the RAW native layer
    content, not from :func:`per_layer_rules`, which has already dropped the
    takeover-suppressed patterns.
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
