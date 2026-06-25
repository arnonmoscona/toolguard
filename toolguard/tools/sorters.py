"""
Canonical sorting of toolguard rule arrays -- thin delegation layer.

This module re-exports the canonical sort functions from
:mod:`toolguard.rule_sort` and adds :func:`sort_layer_rules` for the common
case of sorting allow, deny, and ask lists in one call.

Sorting order (authoritative definition lives in :mod:`toolguard.rule_sort`):

1. **Tool priority**: Bash (0), Read (1), Write (2), Edit (3), all others (4).
2. **Within each tool bucket**: case-insensitive alphabetical on the FULL
   pattern string (e.g. ``Bash(git:*)`` before ``Bash(uv run:*)``).

This ordering matches the one used by the migration script so that
``migrate_permissions`` and the tools layer always agree on sort order and
config files do not accumulate diff noise between passes.

Scope
-----
This module sorts IN-MEMORY rule lists only.  Comment-preserving file rewriting
is handled by :mod:`toolguard.rule_sort` (used by the migration script and
deferred higher-level tools).  This module never reads or writes files.
"""

from typing import List, Optional, Tuple

from toolguard.rule_sort import get_tool_priority, sort_patterns


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


# Re-export the canonical sort functions so callers that import them from
# ``toolguard.tools.sorters`` continue to work without change.
__all__ = [
    "get_tool_priority",
    "sort_patterns",
    "sort_layer_rules",
    "stable_rule_key",
]


def sort_layer_rules(
    allow: List[str],
    deny: List[str],
    ask: Optional[List[str]] = None,
) -> Tuple[List[str], List[str], Optional[List[str]]]:
    """
    Return canonical sorted copies of allow, deny, and ask pattern lists.

    Sorts each list independently using the canonical tool-priority order.
    Returns ``None`` for *ask* when the input was ``None`` (preserving the
    distinction between "no ask list" and "empty ask list").  The input lists
    are never mutated.

    Args:
        allow: Allow patterns for a single tool layer.
        deny: Deny patterns for a single tool layer.
        ask: Ask patterns for a single tool layer, or ``None``.

    Returns:
        Tuple of ``(sorted_allow, sorted_deny, sorted_ask_or_None)``.
    """
    sorted_allow = sort_patterns(allow)
    sorted_deny = sort_patterns(deny)
    sorted_ask: Optional[List[str]] = None if ask is None else sort_patterns(ask)
    return sorted_allow, sorted_deny, sorted_ask


def stable_rule_key(pattern: str) -> Tuple[int, str]:
    """
    Expose the canonical sort key for a pattern.

    Delegates to :func:`toolguard.rule_sort.get_tool_priority`, which returns a
    ``(tool_priority, lowercase_pattern)`` tuple.  Useful when a caller needs to
    sort a heterogeneous collection of ``(tool, pattern)`` pairs using the same
    ordering that :func:`sort_patterns` applies, without calling
    :func:`sort_patterns` twice.

    Args:
        pattern: A full permission pattern (e.g. ``Bash(git:*)``).

    Returns:
        The ``(tool_priority, lowercase_pattern)`` tuple used as the sort key.
    """
    return get_tool_priority(pattern)
