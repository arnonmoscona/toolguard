"""
Sorting of in-memory toolguard rule arrays.

Re-exports :func:`~toolguard.rule_sort.get_tool_priority` and
:func:`~toolguard.rule_sort.sort_patterns`, which define the canonical order
(see that module's docstring), and adds :func:`sort_layer_rules` for sorting a
layer's allow, deny and ask lists in one call.  Nothing here touches a file.
"""

from typing import List, Optional, Tuple

from toolguard.rule_sort import get_tool_priority, sort_patterns


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

    Each list is sorted independently and none of them is mutated.  ``ask``
    comes back ``None`` when it went in ``None``, keeping "no ask list" distinct
    from "empty ask list".

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
    Expose the key :func:`sort_patterns` sorts by.

    Args:
        pattern: A full permission pattern (e.g. ``Bash(git:*)``).

    Returns:
        ``(tool_priority, lowercased_pattern)``.
    """
    return get_tool_priority(pattern)
