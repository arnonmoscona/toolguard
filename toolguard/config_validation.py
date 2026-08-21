"""Content-level validation of a toolguard permissions section."""

from typing import List, Mapping, Tuple

from toolguard.issues import Issue
from toolguard.rule_entry import normalize_entry
from toolguard.tool_spec import KNOWN_TOOL_NAMES

#: Tool names toolguard recognizes out of the box. A tool outside this set is
#: recognized by adding it to ``additional_supported_tools`` in config, not by
#: extending this.
KNOWN_SUPPORTED_TOOLS = KNOWN_TOOL_NAMES

#: Sections that must be tables, and the list-typed keys each must hold when
#: present. Shared by :func:`find_wrong_shaped_permission_lists` (per-layer,
#: raw content) and :func:`validate_permissions` (merged ``permissions`` only
#: -- ``hard_deny`` is never merged across layers, so it is checked solely by
#: the per-layer scan).
_SHAPE_CHECKED_SECTIONS: Mapping[str, Tuple[str, ...]] = {
    "permissions": ("allow", "deny", "ask"),
    "hard_deny": ("allow", "deny"),
}


def describe_wrong_shaped_section(section_key: str, value: object) -> str:
    """Message for a ``[section_key]`` section present but not a table."""
    return (
        f'"{section_key}" section is not a table (found {type(value).__name__}); '
        "every rule in it was discarded"
    )


def describe_wrong_shaped_list(key: str, value: object) -> str:
    """Message for a permissions list (``key``) present but not a list."""
    return (
        f'"{key}" is not a list (found {type(value).__name__}); every rule '
        "in it was discarded"
    )


def find_wrong_shaped_permission_lists(
    content: Mapping[str, object],
) -> Tuple[str, ...]:
    """
    Find every wrong-shaped ``[permissions]``/``[hard_deny]`` list in one raw,
    UN-merged config layer.

    A ``str`` is neither a ``dict`` (for the section itself, e.g.
    ``[[permissions]]``) nor safe to iterate as a ``list`` (for ``allow`` /
    ``deny`` / ``ask`` written as a bare string) -- both shapes are silently
    coerced to "no rules" by
    :meth:`~toolguard.config.Configuration._extract_tool_entries`, which is
    what makes this a fail-OPEN defect rather than a merely-stricter one: a
    ``deny`` rule can vanish with nothing to show for it. Callers feed the
    result into :attr:`~toolguard.config.Configuration.parse_failures` so the
    TOO-19 ask-floor engages exactly as it does for a syntactically broken
    file.

    Args:
        content: One layer's raw, un-merged parsed dict (TOML or JSON).

    Returns:
        One message per defect found, in section/key order.
    """
    messages: List[str] = []
    for section_key, list_keys in _SHAPE_CHECKED_SECTIONS.items():
        section = content.get(section_key)
        if not section:
            continue
        if not isinstance(section, dict):
            messages.append(describe_wrong_shaped_section(section_key, section))
            continue
        for list_key in list_keys:
            value = section.get(list_key)
            if value is not None and not isinstance(value, list):
                messages.append(
                    describe_wrong_shaped_list(f"{section_key}.{list_key}", value)
                )
    return tuple(messages)


def extract_tool_name(permission: str) -> str:
    """
    Extract the tool name from a permission string: ``'Bash(ls:*)' -> 'Bash'``.

    Unwrapped input comes back unchanged (``'WebSearch' -> 'WebSearch'``).
    """
    if "(" in permission:
        return permission.split("(", 1)[0]
    return permission


def validate_permissions(config: dict) -> Tuple[Issue, ...]:
    """
    Report content-level problems with a configuration's permission entries.

    Two families of issue. Per entry: whatever
    :func:`toolguard.rule_entry.normalize_entry` has to say about it -- an
    unusable shape, an unknown enrichment key, a non-string
    ``additionalContext``. Per tool named by an entry: a tool outside the
    supported set, or a supported tool missing from ``governed_tools``.

    Every entry goes through ``normalize_entry`` first, so the per-tool
    checks see a structured (``{match = "...", ...}``) entry's ``match``
    value exactly as they see a plain string.

    Args:
        config: A configuration dictionary. ``governed_tools`` falls back to
            ``['Bash']`` when absent or not a list;
            ``additional_supported_tools`` to empty.

    Returns:
        A tuple of :class:`toolguard.issues.Issue`. Issues sharing a
        ``(level, message)`` are collapsed to one, so the same mistake
        repeated across entries is reported once.
    """
    issues: List[Issue] = []
    seen: set = set()

    def add_issue(issue: Issue) -> None:
        key = (issue.level, issue.message)
        if key not in seen:
            seen.add(key)
            issues.append(issue)

    governed_tools = config.get("governed_tools", ["Bash"])
    if not isinstance(governed_tools, list):
        governed_tools = ["Bash"]

    additional_supported_tools = config.get("additional_supported_tools", [])
    if not isinstance(additional_supported_tools, list):
        additional_supported_tools = []

    all_supported_tools = KNOWN_SUPPORTED_TOOLS | set(additional_supported_tools)

    permissions = config.get("permissions", {})
    if not isinstance(permissions, dict):
        add_issue(
            Issue(
                level="error",
                message=describe_wrong_shaped_section("permissions", permissions),
                corrective_steps=(
                    'Write it as "[permissions]" with allow/deny/ask arrays, not '
                    '"[[permissions]]".'
                ),
            )
        )
        return tuple(issues)

    tools_in_permissions = set()
    # is_native=False: `config` is a plain dict with no per-layer provenance.
    # Correct in practice -- Configuration.validation_issues skips native
    # layers before merging.
    for permission_list in ["allow", "deny", "ask"]:
        perms = permissions.get(permission_list, [])
        if not isinstance(perms, list):
            add_issue(
                Issue(
                    level="error",
                    message=describe_wrong_shaped_list(permission_list, perms),
                    corrective_steps=(
                        f'Write "{permission_list}" as an array of strings, e.g. '
                        f'{permission_list} = ["Bash(ls:*)"].'
                    ),
                )
            )
            continue
        for perm in perms:
            entry, entry_issues = normalize_entry(perm, is_native=False)
            for issue in entry_issues:
                add_issue(issue)
            if entry is not None:
                tools_in_permissions.add(extract_tool_name(entry.pattern))

    for tool in tools_in_permissions:
        if tool not in all_supported_tools:
            add_issue(
                Issue(
                    level="warning",
                    message=f'Tool "{tool}" is not a known supported tool',
                    corrective_steps=(
                        f'If "{tool}" is a valid tool that should be governed, '
                        f'add it to "additional_supported_tools" in your config. '
                        f"Otherwise, remove it from permissions or update the tool name."
                    ),
                )
            )
        elif tool not in governed_tools:
            add_issue(
                Issue(
                    level="warning",
                    message=f'Tool "{tool}" appears in permissions but is not in governed_tools list',
                    corrective_steps=(
                        f'Add "{tool}" to governed_tools if you want toolguard to enforce these permissions. '
                        f'Otherwise, remove "{tool}" permissions from the config.'
                    ),
                )
            )

    return tuple(issues)
