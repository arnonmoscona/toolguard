"""
Canonical sorting and comment-preserving section machinery for toolguard rules.

This module contains the single authoritative implementation of permission-rule
sorting and TOML ``[permissions]`` section parsing/reassembly.  Both the
migration script and the tools layer import from here so that there is exactly
ONE sort order in the codebase.

Sorting order
-------------
1. Tool priority: Bash (0), Read (1), Write (2), Edit (3), all others (4).
2. Within each tool bucket: case-insensitive alphabetical on the FULL pattern
   string (e.g. ``Bash(git:*)`` sorts before ``Bash(uv run:*)``).

All functions are pure (no side-effects, no I/O) and depend only on the Python
standard library.
"""

import re
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def get_tool_priority(pattern: str) -> Tuple[int, str]:
    """
    Return a sort key for a permission pattern.

    The key is a ``(priority, lowercase_pattern)`` tuple where priority is:

    * 0 -- Bash
    * 1 -- Read
    * 2 -- Write
    * 3 -- Edit
    * 4 -- any other tool

    The secondary key (``lowercase_pattern``) is the full pattern string
    lowercased, giving case-insensitive alphabetical ordering within each tool
    bucket.

    Args:
        pattern: A permission pattern string such as ``Bash(git:*)`` or
            ``Read(/tmp/*)`` (may include an extended-syntax prefix like
            ``[regex]``).

    Returns:
        Tuple ``(priority, lowercase_pattern)`` for use as a sort key.
    """
    tool_priorities = {"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}

    # Extract tool name (text before the first '(' or the whole string).
    tool_name = pattern.split("(")[0] if "(" in pattern else pattern
    priority = tool_priorities.get(tool_name, 4)

    return (priority, pattern.lower())


def sort_patterns(patterns: List[str]) -> List[str]:
    """
    Return a new sorted list of permission patterns in canonical order.

    Patterns are sorted by tool priority (Bash first, then Read, Write, Edit,
    then others) and then alphabetically by the full pattern string
    (case-insensitive).  The input list is never mutated.  The sort is stable:
    patterns that compare equal under the key retain their original relative
    order.

    Args:
        patterns: A list of raw permission patterns in their full wrapped form
            (e.g. ``['Read(/tmp/*)', 'Bash(git:*)']``).

    Returns:
        A new list containing the same patterns in canonical order.
    """
    return sorted(patterns, key=get_tool_priority)


# ---------------------------------------------------------------------------
# TOML [permissions] section parsing and reassembly
# ---------------------------------------------------------------------------


def find_section_boundaries(text: str, section_name: str) -> Tuple[int, int]:
    """
    Find start and end character positions of a TOML section in *text*.

    Args:
        text: Full TOML file content.
        section_name: Section name without brackets (e.g. ``'permissions'``).

    Returns:
        ``(start_pos, end_pos)`` where *start_pos* is the index of the
        ``[section_name]`` line and *end_pos* is the index of the next
        section header (i.e. the next line starting with ``[``) or the end of
        the string.  Returns ``(-1, -1)`` when the section is not found.
    """
    section_header = f"[{section_name}]"
    start_pos = text.find(section_header)

    if start_pos == -1:
        return (-1, -1)

    # Find the end of this section: the next line that starts with '['.
    end_pos = len(text)
    search_from = start_pos + len(section_header)

    for i in range(search_from, len(text)):
        if text[i] == "\n":
            if i + 1 < len(text) and text[i + 1] == "[":
                end_pos = i + 1
                break

    return (start_pos, end_pos)


def parse_permissions_section_with_comments(section_text: str) -> Dict:
    """
    Parse a ``[permissions]`` section, preserving comments and their associations.

    Each permission sub-list (allow / deny / ask) is represented as an ordered
    list of typed items so that comments can be round-tripped through a
    sort-and-reassemble cycle without loss.

    Item types:

    * ``'comment_block'`` -- one or more consecutive comment/blank lines.
    * ``'rule'``          -- a quoted permission pattern line.
    * ``'header'``        -- (reserved, not currently emitted).

    A *comment_block* that immediately precedes a *rule* is considered to
    "belong to" that rule and travels with it when rules are re-sorted.
    Comment blocks that appear before the first rule or after the last rule are
    anchored to the top or bottom of the sub-section respectively.

    Args:
        section_text: The full text of the ``[permissions]`` section, including
            its ``[permissions]`` header line.

    Returns:
        ``Dict`` with keys ``'allow'``, ``'deny'``, ``'ask'``.  Each value is
        a list of ``(item_type, content, parsed_value)`` tuples, where
        *parsed_value* is the extracted pattern string for ``'rule'`` items and
        ``None`` for ``'comment_block'`` items.
    """
    result = {"allow": [], "deny": [], "ask": []}
    lines = section_text.split("\n")

    current_subsection = None
    comment_buffer = []

    for line in lines:
        stripped = line.strip()

        # Skip the [permissions] header itself.
        if stripped == "[permissions]":
            continue

        # Detect subsection headers like [permissions.allow].
        subsection_match = re.match(r"\[permissions\.(allow|deny|ask)\]", stripped)
        if subsection_match:
            current_subsection = subsection_match.group(1)
            # Flush any pending comments as top-of-section.
            if comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # Detect simple subsection assignments like "allow = [".
        assign_match = re.match(r"(allow|deny|ask)\s*=\s*\[", stripped)
        if assign_match:
            current_subsection = assign_match.group(1)
            # Flush any pending comments as top-of-section.
            if comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # Comment line -- accumulate into buffer.
        if stripped.startswith("#"):
            comment_buffer.append(line)
            continue

        # Blank line inside an active comment buffer is kept as part of the block.
        if stripped == "":
            if current_subsection and comment_buffer:
                comment_buffer.append(line)
            continue

        # Closing bracket -- flush any pending comments as bottom-of-section.
        if stripped == "]":
            if current_subsection and comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # Rule line (contains a quoted pattern -- double- OR single-quoted).
        # TOML basic strings use double quotes (with backslash escapes); TOML
        # literal strings use single quotes (no escaping).  Real configs use
        # single-quoted literals for rules that contain backslashes, e.g.
        # ``'Bash([regex]\bfind\b)'``, so both must be recognised or such a rule
        # is silently dropped/regenerated on a sort-and-reassemble cycle.
        if current_subsection and ('"' in stripped or "'" in stripped):
            pattern_value = None
            double_quoted = re.search(r'"([^"]*)"', stripped)
            if double_quoted:
                # Basic (double-quoted) string: unescape.
                pattern_value = (
                    double_quoted.group(1).replace('\\"', '"').replace("\\\\", "\\")
                )
            else:
                single_quoted = re.search(r"'([^']*)'", stripped)
                if single_quoted:
                    # Literal (single-quoted) string: value is verbatim, no unescaping.
                    pattern_value = single_quoted.group(1)

            if pattern_value is not None:
                # Attach any pending comments to this rule.
                if comment_buffer:
                    result[current_subsection].append(
                        ("comment_block", "\n".join(comment_buffer), None)
                    )
                    comment_buffer = []

                # Preserve the original line text (keeps inline comments AND the
                # original quoting style, so an unchanged literal rule round-trips).
                result[current_subsection].append(("rule", line, pattern_value))
                continue

    # Flush any remaining comments as bottom-of-section.
    if current_subsection and comment_buffer:
        result[current_subsection].append(
            ("comment_block", "\n".join(comment_buffer), None)
        )

    return result


def reassemble_permissions_section(
    parsed_structure: Dict,
    new_permissions: Dict[str, List[str]],
    auto_sort: bool = True,
) -> str:
    """
    Rebuild a ``[permissions]`` section with comments preserved and rules sorted.

    Uses the parsed structure produced by
    :func:`parse_permissions_section_with_comments` to re-associate comments
    with their rules (comments that preceded a rule travel with it when rules
    are re-ordered by the sort).

    Args:
        parsed_structure: Structure returned by
            :func:`parse_permissions_section_with_comments`.
        new_permissions: New permission values to use, as a dict with keys
            ``'allow'``, ``'deny'``, ``'ask'`` containing lists of pattern
            strings.
        auto_sort: When ``True`` (the default), patterns are sorted using
            :func:`sort_patterns` before reassembly.

    Returns:
        Complete ``[permissions]`` section text, including the header line, with
        comments preserved and rules ordered.
    """
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        patterns = new_permissions.get(perm_type, [])
        if not patterns:
            continue

        parsed_items = parsed_structure.get(perm_type, [])

        # Classify parsed items into top/bottom comment anchors and per-rule
        # comment associations.
        top_comments = []
        bottom_comments = []
        rule_comments = {}   # pattern_value -> preceding comment block text
        rule_lines = {}      # pattern_value -> original line text (inline comments)

        current_comment_block = None
        seen_first_rule = False

        for item_type, content, value in parsed_items:
            if item_type == "comment_block":
                if not seen_first_rule:
                    top_comments.append(content)
                else:
                    current_comment_block = content
            elif item_type == "rule":
                seen_first_rule = True
                rule_lines[value] = content
                if current_comment_block:
                    rule_comments[value] = current_comment_block
                    current_comment_block = None

        # Any trailing comment block belongs to the bottom.
        if current_comment_block:
            bottom_comments.append(current_comment_block)

        # Sort patterns if requested.
        sorted_patterns = sort_patterns(patterns) if auto_sort else patterns

        lines.append(f"{perm_type} = [")

        for comment_block in top_comments:
            lines.append(comment_block)

        for pattern in sorted_patterns:
            # Preceding comment block travels with the rule.
            if pattern in rule_comments:
                lines.append(rule_comments[pattern])

            # Use original line (preserves inline comments); generate new if needed.
            if pattern in rule_lines:
                lines.append(rule_lines[pattern])
            else:
                escaped = pattern.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'  "{escaped}",')

        for comment_block in bottom_comments:
            lines.append(comment_block)

        lines.append("]")
        lines.append("")

    return "\n".join(lines)
