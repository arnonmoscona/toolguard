"""Configuration validation for toolguard."""

from typing import List, Tuple

from toolguard.issues import Issue
from toolguard.rule_entry import normalize_entry

# Known supported tools that toolguard can govern
KNOWN_SUPPORTED_TOOLS = {
    "Bash",
    "Read",
    "Write",
    "Edit",
    "mcp__jetbrains__execute_terminal_command",
}


def extract_tool_name(permission: str) -> str:
    """
    Extract the tool name from a permission string.

    Examples:
        'Bash(ls:*)' -> 'Bash'
        'Read(/tmp/**)' -> 'Read'
        'WebSearch' -> 'WebSearch'

    Args:
        permission: Permission string (e.g., 'Bash(ls:*)' or 'WebSearch')

    Returns:
        The tool name extracted from the permission string
    """
    if "(" in permission:
        return permission.split("(", 1)[0]
    return permission


def validate_permissions(config: dict) -> Tuple[Issue, ...]:
    """
    Validate configuration and return a tuple of structured issues.

    Checks for:
    1. Unsupported tools in permissions (tools that toolguard cannot govern)
    2. Ungoverned tools (tools in permissions but not in governed_tools list)
    3. Malformed or otherwise unparseable permission entries (see
       :func:`toolguard.rule_entry.normalize_entry`)
    4. Structured (``{match = "...", ...}``) entries using an unknown
       enrichment key

    Every ``allow``/``deny``/``ask`` entry -- plain string or structured
    table -- is routed through :func:`toolguard.rule_entry.normalize_entry`,
    which is the single chokepoint for entry-shape normalization across the
    codebase. This is what makes check 1/2 apply identically to a structured
    entry's ``match`` value as to a plain string; previously an
    ``isinstance(perm, str)`` filter here silently skipped structured
    entries entirely.

    Args:
        config: Configuration dictionary (from TOML or JSON). In practice
            this is the MERGED view assembled by
            ``Configuration.validation_issues()`` across every non-native
            config layer, so it carries no per-layer provenance.

    Returns:
        A tuple of :class:`toolguard.issues.Issue`, each with a ``level``
        ('warning' or 'error'), a human-readable ``message``, and
        ``corrective_steps``. Duplicate issues (same level and message,
        e.g. from the same malformed entry repeated in the config) are
        collapsed to one.
    """
    issues: List[Issue] = []
    seen: set = set()

    def add_issue(issue: Issue) -> None:
        """Append ``issue`` unless an identical (level, message) was already added."""
        key = (issue.level, issue.message)
        if key not in seen:
            seen.add(key)
            issues.append(issue)

    # Get governed_tools from config (defaults to ['Bash'])
    governed_tools = config.get("governed_tools", ["Bash"])
    if not isinstance(governed_tools, list):
        governed_tools = ["Bash"]

    # Get additional_supported_tools from config (defaults to empty list)
    additional_supported_tools = config.get("additional_supported_tools", [])
    if not isinstance(additional_supported_tools, list):
        additional_supported_tools = []

    # Combine known and additional supported tools
    all_supported_tools = KNOWN_SUPPORTED_TOOLS | set(additional_supported_tools)

    # Get permissions section
    permissions = config.get("permissions", {})
    if not isinstance(permissions, dict):
        return tuple(issues)

    # Collect all tools mentioned in permissions, and surface any entry-level
    # issue (unparseable entry, unknown enrichment key) that normalize_entry
    # finds along the way.
    #
    # is_native=False: this function validates the MERGED view assembled by
    # Configuration.validation_issues(), which has no per-layer provenance
    # to gate structured-entry recognition with -- and in fact that merge
    # already excludes native layers entirely (`if layer.is_native:
    # continue` there), so every entry seen here is, in practice, already
    # non-native. The authoritative native-layer rejection of structured
    # entries happens per-layer in permission_layers()/hard_deny() (TOO-19
    # increments 2/3); validate_permissions is display/log only, so at worst
    # a genuinely native-sourced structured entry produces one extra
    # advisory warning here, never a permission decision.
    tools_in_permissions = set()
    for permission_list in ["allow", "deny", "ask"]:
        perms = permissions.get(permission_list, [])
        if isinstance(perms, list):
            for perm in perms:
                entry, entry_issues = normalize_entry(perm, is_native=False)
                for issue in entry_issues:
                    add_issue(issue)
                if entry is not None:
                    tools_in_permissions.add(extract_tool_name(entry.pattern))

    # Check each tool for exactly one of: unsupported, or supported-but-
    # ungoverned -- the two conditions are mutually exclusive (the second
    # requires `tool in all_supported_tools`, the first requires the
    # opposite), so a single if/elif per tool covers both checks in one pass
    # instead of scanning `tools_in_permissions` twice. This does not change
    # the ORDER any caller could actually observe: `tools_in_permissions` is
    # a plain `set`, whose iteration order was never stable across runs to
    # begin with (str hashing is randomized per-process by default), so no
    # caller could have relied on the previous two-pass grouping either.
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
