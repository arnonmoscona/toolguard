"""
Redundancy detection for toolguard permission rules.

Two complementary detection strategies are provided:

1. **Static exact/normalized-equal duplicate detection.**
   Within a tool's allow (or deny or ask) list, patterns that normalise to the
   same form are flagged as duplicates.  Normalisation strips whitespace and
   lowercases the body of the pattern (type prefix kept for grouping), using
   :func:`~toolguard.patterns.parse_pattern`.  Example: ``uv run pytest :*`` and
   ``uv run pytest:*`` normalise to the same body and are flagged.

2. **Corpus-backed subsumption.**
   A rule R is corpus-redundant when removing it from the config changes NO
   decision across a harvested command corpus -- meaning another rule already
   covers every command R would have matched.  This check uses
   :func:`~toolguard.tools.replay.replay` (config-with-R vs config-without-R)
   and classifies R as redundant when the diff contains zero broadened entries
   (removing R never loosens anything) AND zero tightened entries (removing R
   never tightens anything -- so no decision changes AT ALL).

Scope / deferred work
---------------------
Static family-based subsumption (literal-alternation, glob expansion) is
deferred to P2.  This module only handles:
- Exact / normalised-equal duplicates (static).
- Corpus-backed "no decision changes when removed" (dynamic).

Design note on `per_layer_rules` interaction
--------------------------------------------
Redundancy is checked within a SINGLE tool's allow/deny/ask list for the static
case, and within a SINGLE config for the corpus case.  Cross-level interaction
(a rule at project level made redundant by a user-level rule) is NOT detected
here -- that is more-specific-wins territory and must account for the full
cascade.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from toolguard.config import Configuration, Provenance, wrap_tool_pattern
from toolguard.patterns import parse_pattern
from toolguard.rule_entry import normalize_entry
from toolguard.tools.config_access import per_layer_rules, with_layer_allow_replaced
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.replay import replay


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RedundancyFinding:
    """
    A single redundancy finding.

    Attributes:
        redundant_pattern: The raw pattern identified as redundant.
        provenance: Origin of the redundant pattern (config file, level).
            May be ``None`` when the pattern was not traced to a specific source.
        kind: ``'static'`` for normalized-equal duplicates or ``'corpus'`` for
            corpus-backed subsumption findings.
        list_type: Which list the redundant pattern lives in
            (``'allow'``, ``'deny'``, or ``'ask'``).
        tool: The tool name this pattern applies to (e.g. ``'Bash'``).
        covered_by: Patterns that cover the redundant one (for static findings,
            the other duplicate; for corpus findings, always ``None`` since
            determining the exact covering rule would require per-rule replay).
        note: Human-readable explanation of why this pattern is redundant.
    """

    redundant_pattern: str
    provenance: Optional[Provenance]
    kind: str  # 'static' or 'corpus'
    list_type: str  # 'allow', 'deny', or 'ask'
    tool: str
    covered_by: Optional[str]  # pattern that covers this one, if determinable
    note: str


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------


def _normalised_body(pattern: str) -> Tuple[str, str]:
    """
    Parse a pattern into ``(type_prefix_key, normalised_body)``.

    The ``type_prefix_key`` is the string form of the :class:`PatternType`
    (e.g. ``'regex'``, ``'default'``).  The ``normalised_body`` is the body
    with whitespace stripped and lowercased, with additional normalisation for
    the ``cmd:args`` separator syntax:

    - For DEFAULT patterns, whitespace before and after ``:`` is collapsed so
      that ``uv run pytest :*`` and ``uv run pytest:*`` normalise to the same
      key.  Both patterns resolve identically in the toolguard matcher (the
      trailing whitespace in the command portion is ignored when ``args`` is
      ``*``).
    - Internal whitespace sequences are collapsed to a single space.

    Two patterns are considered normalised-equal when BOTH components match.

    Args:
        pattern: A raw permission pattern (tool wrapper must be stripped by caller).

    Returns:
        Tuple of ``(type_prefix_key, normalised_body)``.
    """
    ptype, body = parse_pattern(pattern, extended_syntax=True)
    norm = body.strip().lower()
    # For DEFAULT patterns: collapse whitespace around ':' and collapse internal runs
    if ptype.value == "default":
        # Collapse multiple spaces to one
        norm = re.sub(r"  +", " ", norm)
        # Remove whitespace immediately before or after ':'
        norm = re.sub(r"\s*:\s*", ":", norm)
    return ptype.value, norm


# ---------------------------------------------------------------------------
# Static detection
# ---------------------------------------------------------------------------


def find_static_duplicates(
    patterns: List[str],
    provenance: Optional[Provenance],
    tool: str,
    list_type: str,
) -> List[RedundancyFinding]:
    """
    Find normalised-equal duplicate patterns within a single pattern list.

    Scans ``patterns`` and groups them by their normalised form (type key +
    lowercased body).  All but the FIRST occurrence in each group are flagged as
    redundant (``kind='static'``).  The first occurrence is considered canonical;
    subsequent occurrences are duplicates.

    Args:
        patterns: A list of raw patterns from a single allow/deny/ask array
            (tool wrapper stripped by caller, e.g. just the inner content).
        provenance: Origin of the layer these patterns came from.
        tool: Tool name (e.g. ``'Bash'``) for the finding record.
        list_type: Which list (``'allow'``, ``'deny'``, or ``'ask'``).

    Returns:
        List of :class:`RedundancyFinding` records for each duplicate found.
        Empty when no duplicates exist.
    """
    seen: Dict[Tuple[str, str], str] = {}  # normalised key -> first-seen raw pattern
    findings: List[RedundancyFinding] = []

    for pat in patterns:
        key = _normalised_body(pat)
        if key in seen:
            canonical = seen[key]
            findings.append(
                RedundancyFinding(
                    redundant_pattern=pat,
                    provenance=provenance,
                    kind="static",
                    list_type=list_type,
                    tool=tool,
                    covered_by=canonical,
                    note=(
                        f"Duplicate of '{canonical}': normalises to the same "
                        f"pattern (type={key[0]}, body='{key[1]}')"
                    ),
                )
            )
        else:
            seen[key] = pat

    return findings


def find_static_duplicates_across_layers(
    config: Configuration,
    tool: str,
) -> List[RedundancyFinding]:
    """
    Find normalised-equal duplicate patterns across all layers for a single tool.

    Checks for duplicates within each list type (allow, deny, ask) across all
    layers independently.  Cross-layer duplicates (same rule in project and user
    layer) are NOT flagged here -- those have different semantics (a more-specific
    layer overrides a less-specific one, but that is subsumption, not duplication
    in the same context).  Intra-layer duplicates within allow (or deny or ask)
    are the target.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).

    Returns:
        All static duplicate findings across all layers for ``tool``.
    """
    findings: List[RedundancyFinding] = []
    for layer in per_layer_rules(config, tool):
        findings.extend(
            find_static_duplicates(list(layer.allow), layer.provenance, tool, "allow")
        )
        findings.extend(
            find_static_duplicates(list(layer.deny), layer.provenance, tool, "deny")
        )
        findings.extend(
            find_static_duplicates(list(layer.ask), layer.provenance, tool, "ask")
        )
    return findings


# ---------------------------------------------------------------------------
# Corpus-backed subsumption
# ---------------------------------------------------------------------------


def _config_without_allow(
    config: Configuration,
    tool: str,
    pattern_to_remove: str,
) -> Configuration:
    """
    Return a synthetic :class:`Configuration` with one allow pattern removed.

    Removes ``pattern_to_remove`` from the allow list of ``tool`` in the FIRST
    layer that contains it.  All occurrences within that layer are removed
    (duplicate patterns are fully purged).

    Delegates to :func:`~toolguard.tools.config_access.with_layer_allow_replaced`
    using ``removed={pattern_to_remove}`` and ``added=[]``, so the modification
    technique is kept in exactly one place.  The SHALLOW modification semantics
    (only the matching layer's allow list is rebuilt; all other content is shared
    by reference) are inherited from the shared primitive.

    Args:
        config: The original configuration.
        tool: The tool whose allow list is modified (e.g. ``'Bash'``).
        pattern_to_remove: The wrapper-free pattern body to remove.

    Returns:
        A new :class:`Configuration` with the pattern absent from the first
        matching layer's allow list, or the original ``config`` when the pattern
        is not found.
    """
    wrapped_target = wrap_tool_pattern(tool, pattern_to_remove)

    for layer in config.layers:
        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            continue
        allow_list = permissions.get("allow", [])
        if not isinstance(allow_list, list):
            continue
        # Locate the layer by PATTERN (".pattern" -- "is this the same RULE",
        # per RuleEntry.identity()'s comparison-semantics note), not by raw
        # element identity: an allow-list element may be a structured `dict`,
        # and `wrapped_target in allow_list` (a `str in list` check) is
        # always False against one, so a structured entry's layer was never
        # found and the removal silently no-opped. Mirrors the exact
        # normalize_entry-then-compare-pattern idiom used by
        # with_layer_rules_replaced. An element that fails to normalize is
        # simply not a match here -- never raises.
        entries = (
            normalize_entry(element, is_native=layer.is_native)[0]
            for element in allow_list
        )
        if any(
            entry is not None and entry.pattern == wrapped_target for entry in entries
        ):
            return with_layer_allow_replaced(
                config, tool, layer.provenance, {pattern_to_remove}, []
            )

    # Pattern was not found in any layer's allow list.
    return config


def find_corpus_redundant_allows(
    config: Configuration,
    tool: str,
    corpus: List[LogEntry],
) -> List[RedundancyFinding]:
    """
    Find allow rules that are corpus-redundant for ``tool``.

    A rule R is corpus-redundant when removing it changes NO decision across
    the corpus: the replay of (config) vs (config-without-R) produces zero
    broadened and zero tightened entries (i.e. all unchanged).  This means
    every command that R would have matched is already covered by another rule.

    Only allow rules are tested.  Deny and ask rules cannot generally be removed
    safely without a deeper analysis (removing a deny might unexpectedly allow
    something via the cascade).

    Note: A corpus that does not cover the rule's match-set can give false
    "redundant" signals for rules that protect against uncommon commands.  The
    quality of the result depends on corpus coverage.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).
        corpus: Harvested command corpus from :func:`~toolguard.tools.log_harvest.harvest`.

    Returns:
        Corpus-redundant :class:`RedundancyFinding` records for each allow rule
        that changes no decision when removed.  Empty when no corpus-redundant
        rules are found, or when the corpus is empty.
    """
    if not corpus:
        return []

    # Get per-layer rules to identify each allow pattern and its provenance
    layer_rules = per_layer_rules(config, tool)
    findings: List[RedundancyFinding] = []

    # Track which patterns we've already tested (to skip duplicates)
    tested: Set[str] = set()

    for lr in layer_rules:
        for pattern in lr.allow:
            if pattern in tested:
                continue
            tested.add(pattern)

            # Build a config without this pattern
            config_without = _config_without_allow(config, tool, pattern)
            if config_without is config:
                # Could not find pattern -- skip
                continue

            # Replay corpus against config vs config_without
            diff = replay(corpus, config, config_without)

            # If no decisions changed, this rule is corpus-redundant
            if diff.broadened_count == 0 and diff.tightened_count == 0:
                findings.append(
                    RedundancyFinding(
                        redundant_pattern=pattern,
                        provenance=lr.provenance,
                        kind="corpus",
                        list_type="allow",
                        tool=tool,
                        covered_by=None,  # exact covering rule not determinable from diff alone
                        note=(
                            f"Removing this rule changes no decision across "
                            f"{len(corpus)} corpus entries -- another rule already "
                            f"covers its match-set (or no corpus entry exercises it)."
                        ),
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Top-level convenience
# ---------------------------------------------------------------------------


def find_redundancy(
    config: Configuration,
    tool: str,
    corpus: Optional[List[LogEntry]] = None,
) -> List[RedundancyFinding]:
    """
    Find all redundant rules for ``tool`` in ``config``.

    Runs both static (exact/normalised-equal duplicate) detection and, when a
    corpus is provided, corpus-backed subsumption detection.  Results are
    returned in order: static findings first, then corpus findings.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).
        corpus: Optional command corpus for corpus-backed analysis.  When
            ``None`` or empty, only the static check is performed.

    Returns:
        All :class:`RedundancyFinding` records found, static before corpus.
    """
    static = find_static_duplicates_across_layers(config, tool)
    corpus_findings: List[RedundancyFinding] = []
    if corpus:
        corpus_findings = find_corpus_redundant_allows(config, tool, corpus)
    return static + corpus_findings
