"""
Redundancy detection for toolguard permission rules.  Two independent strategies:

1. **Static duplicates** -- within one layer's allow (or deny or ask) list for one
   tool, patterns whose bodies normalise to the same string, e.g.
   ``uv run pytest :*`` and ``uv run pytest:*``.  Purely textual; see
   :func:`_normalised_body` for what normalisation does not preserve.

2. **Corpus-backed subsumption** -- an allow rule whose removal changes no
   decision anywhere in a harvested command corpus, established by replaying the
   corpus against the config with and without it.

No static subsumption between two *different* patterns is attempted -- literal
alternations and globs are never expanded.
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
        redundant_pattern: The wrapper-free pattern identified as redundant.
        provenance: Origin of the layer it came from; ``None`` only when the
            caller supplied none.
        kind: ``'static'`` or ``'corpus'``.
        list_type: Which list the pattern lives in -- ``'allow'``, ``'deny'``,
            or ``'ask'``.
        tool: The tool name this pattern applies to (e.g. ``'Bash'``).
        covered_by: For a static finding, the earlier pattern it duplicates.
            Always ``None`` for a corpus finding -- the replay diff shows that
            nothing changed, not which rule took over.
        note: Human-readable explanation, for display.
    """

    redundant_pattern: str
    provenance: Optional[Provenance]
    kind: str
    list_type: str
    tool: str
    covered_by: Optional[str]
    note: str


# ---------------------------------------------------------------------------
# Normalisation helper
# ---------------------------------------------------------------------------


def _normalised_body(pattern: str, *, fold_case: bool = True) -> Tuple[str, str]:
    """
    Reduce a pattern to its duplicate-detection key.

    The key pairs the :class:`~toolguard.patterns.PatternType` value
    (``'default'``, ``'regex'``, ``'glob'``, ``'native'``) with the body,
    stripped and, by default, lowercased.  A DEFAULT body is normalised
    further: runs of two or more spaces become one, and whitespace around
    every ``:`` is removed, so ``uv run pytest :*`` and ``uv run pytest:*``
    land on one key.

    Coarser than matching -- two patterns can share a key and still match
    different commands.  Measured: ``Git *`` and ``git *`` share a key and
    ``git status`` matches only the second; ``a  b:*`` and ``a b:*`` share a key
    and ``a  b x`` matches only the first.  A shared key is grounds for review,
    not a safe deletion.

    Args:
        pattern: A raw permission pattern, tool wrapper already stripped.
        fold_case: Whether to lowercase the body.  True (default) for the
            within-layer static-duplicate scan, where over-matching is an
            accepted false-positive rate; a cross-layer caller reporting a
            command set as truly covered needs ``False``, since the real
            matcher is case-sensitive.

    Returns:
        ``(type_key, normalised_body)``.
    """
    ptype, body = parse_pattern(pattern, extended_syntax=True)
    norm = body.strip()
    if fold_case:
        norm = norm.lower()
    if ptype.value == "default":
        norm = re.sub(r"  +", " ", norm)
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
    Flag normalised-equal duplicates within a single pattern list.

    Patterns are grouped by :func:`_normalised_body`; every occurrence after the
    first in a group is returned as a ``kind='static'`` finding naming the first
    as its ``covered_by``.

    Args:
        patterns: Raw patterns from one allow/deny/ask array, tool wrapper
            already stripped.
        provenance: Origin of the layer these patterns came from.
        tool: Tool name (e.g. ``'Bash'``) for the finding record.
        list_type: Which list (``'allow'``, ``'deny'``, or ``'ask'``).

    Returns:
        One :class:`RedundancyFinding` per duplicate, in input order.  Empty
        when there are none.
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
    Find normalised-equal duplicates in every layer's allow, deny and ask list.

    Each list is scanned on its own, so a pattern present in two layers, or in
    both a layer's allow and its deny, is not a finding.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).

    Returns:
        All static duplicate findings for ``tool``, layer by layer.
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

    Only the FIRST layer holding ``pattern_to_remove`` is edited, and every
    occurrence in that layer goes.

    Args:
        config: The original configuration.
        tool: The tool whose allow list is modified (e.g. ``'Bash'``).
        pattern_to_remove: The wrapper-free pattern body to remove.

    Returns:
        A new :class:`Configuration`, or the ``config`` object itself -- not a
        copy of it -- when no layer holds the pattern, so a caller can tell
        "nothing to remove" from "removed" by identity.
    """
    wrapped_target = wrap_tool_pattern(tool, pattern_to_remove)

    for layer in config.layers:
        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            continue
        allow_list = permissions.get("allow", [])
        if not isinstance(allow_list, list):
            continue
        # Locate the layer by normalized `.pattern`, not by raw element: an
        # allow-list element may be a structured `dict`, against which
        # `wrapped_target in allow_list` is always False, so the layer would
        # never be found and the removal would silently no-op.
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

    return config


def find_corpus_redundant_allows(
    config: Configuration,
    tool: str,
    corpus: List[LogEntry],
) -> List[RedundancyFinding]:
    """
    Find allow rules for ``tool`` whose removal changes no decision over ``corpus``.

    Each allow pattern is removed in turn and the corpus replayed against the
    config with and without it; the pattern is reported when the diff has zero
    broadened and zero tightened entries.  A pattern occurring in more than one
    layer is tested once.  Deny and ask rules are not tested at all.

    A corpus that never exercises a rule yields the same zero diff as a rule
    another rule genuinely covers, so a finding is a candidate for review whose
    strength is the corpus's coverage.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).
        corpus: Harvested command corpus from :func:`~toolguard.tools.log_harvest.harvest`.

    Returns:
        One :class:`RedundancyFinding` per reported pattern.  Always empty when
        ``corpus`` is empty.
    """
    if not corpus:
        return []

    layer_rules = per_layer_rules(config, tool)
    findings: List[RedundancyFinding] = []

    tested: Set[str] = set()

    for lr in layer_rules:
        for pattern in lr.allow:
            if pattern in tested:
                continue
            tested.add(pattern)

            config_without = _config_without_allow(config, tool, pattern)
            if config_without is config:
                # Nothing was removed, so the replay below would trivially show
                # no change and report the pattern redundant.
                continue

            diff = replay(corpus, config, config_without)

            if diff.broadened_count == 0 and diff.tightened_count == 0:
                findings.append(
                    RedundancyFinding(
                        redundant_pattern=pattern,
                        provenance=lr.provenance,
                        kind="corpus",
                        list_type="allow",
                        tool=tool,
                        covered_by=None,
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
    Run both detection strategies for ``tool`` in ``config``.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).
        corpus: Optional command corpus.  When ``None`` or empty, only the
            static check runs.

    Returns:
        All :class:`RedundancyFinding` records found, static before corpus.
    """
    static = find_static_duplicates_across_layers(config, tool)
    corpus_findings: List[RedundancyFinding] = []
    if corpus:
        corpus_findings = find_corpus_redundant_allows(config, tool, corpus)
    return static + corpus_findings
