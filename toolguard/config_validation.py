"""Content-level validation of a toolguard permissions section."""

from typing import List, Tuple

from toolguard.issues import Issue
from toolguard.rule_entry import normalize_entry
from toolguard.tool_spec import KNOWN_TOOL_NAMES

#: Tool names toolguard recognizes out of the box. A tool outside this set is
#: recognized by adding it to ``additional_supported_tools`` in config, not by
#: extending this.
KNOWN_SUPPORTED_TOOLS = KNOWN_TOOL_NAMES


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
        return tuple(issues)

    tools_in_permissions = set()
    # is_native=False: `config` is a plain dict with no per-layer provenance.
    # Correct in practice -- Configuration.validation_issues skips native
    # layers before merging.
    for permission_list in ["allow", "deny", "ask"]:
        perms = permissions.get(permission_list, [])
        if isinstance(perms, list):
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
