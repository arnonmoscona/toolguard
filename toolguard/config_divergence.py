"""
Config divergence detection for toolguard.

Detects when Claude adds permissions to settings.local.json that are not
present in toolguard config, helping users identify configuration drift.

This module DETECTS divergence; it does not write to toolguard's structured
error log itself (TOO-45 R5d). ``config_divergence`` is a ``config``-layer
module, and :mod:`toolguard.error_log` is ``runtime``-layer -- a config-layer
module depending on it would be an upward layer violation. The caller
(:mod:`toolguard.hook`, which already legitimately imports ``error_log``) is
responsible for logging the warning message :func:`check_and_warn_divergence`
returns. See :class:`DivergenceCheckResult`.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from toolguard import once_per
from toolguard.config import is_tool_wrapper, load_configuration
from toolguard.config_validation import extract_tool_name
from toolguard.error_reporter import report_warning

#: The single named object for this module's once-per-day throttling. One
#: name carries both the key and the human description (TOO-45 punch-list
#: #01 item 4) -- no separate _KEY constant to drift from it.
DIVERGENCE_WARNING = once_per.day(
    "divergence_warning", "the configuration divergence warning"
)


def get_native_permissions(settings_path: Path) -> Dict[str, List[str]]:
    """
    Load allow/deny/ask permissions from Claude's native settings.local.json.

    Extracts patterns for governed tools (Bash, Read, Write, Edit) from the
    permissions.allow, permissions.deny, and permissions.ask lists.

    Args:
        settings_path: Path to settings.local.json file

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each containing list of patterns.
        Returns empty dict if file doesn't exist or can't be parsed.
    """
    if not settings_path.exists():
        return {"allow": [], "deny": [], "ask": []}

    try:
        with open(settings_path, "r") as f:
            config = json.load(f)
    except (json.JSONDecodeError, IOError, Exception) as e:
        report_warning(
            f"Failed to load {settings_path}: {e}",
            f"Fix or remove {settings_path} so toolguard can read it.",
        )
        return {"allow": [], "deny": [], "ask": []}

    permissions = config.get("permissions", {})

    result = {"allow": [], "deny": [], "ask": []}

    # Keep only tool-scoped permission strings (``Tool(...)``). Recognised
    # structurally via the shared config.is_tool_wrapper helper -- no
    # hand-maintained tool list and no duplicated regex (single source of truth
    # lives in config.py), so newly governed tools need no change here.
    for perm_type in ["allow", "deny", "ask"]:
        for perm in permissions.get(perm_type, []):
            if is_tool_wrapper(perm):
                result[perm_type].append(perm)

    return result


def get_toolguard_permissions(config) -> Dict[str, List[str]]:
    """
    Extract raw permission patterns from the resolved toolguard configuration.

    Only processes toolguard_hook layers (not native Claude settings), merged
    across all hierarchy levels with tool wrappers intact. Delegates entirely to
    the :class:`~toolguard.config.Configuration` abstraction, so this client never
    opens files, parses formats, or branches on discovery order.

    ``Configuration.toolguard_permissions()`` returns
    :class:`~toolguard.rule_entry.RuleEntry` tuples (TOO-19 Phase 0a increment
    8); this function's own contract stays plain pattern strings, since every
    caller here (divergence set-comparison, migration's redundancy/similarity
    checks) only ever needs ``.pattern`` -- so the ``.pattern`` projection
    happens once, right here, rather than pushing ``RuleEntry`` into callers
    that have no use for its metadata.

    Args:
        config: A resolved :class:`~toolguard.config.Configuration`.

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each a list of patterns.
    """
    perms = config.toolguard_permissions()
    return {
        key: [entry.pattern for entry in perms[key]] for key in ("allow", "deny", "ask")
    }


def find_divergent_patterns(
    native: Dict[str, List[str]],
    toolguard: Dict[str, List[str]],
    ignored_patterns: List[str],
    governed_tools: Optional[Set[str]] = None,
) -> Dict[str, List[str]]:
    """
    Find patterns in native config that are not in toolguard config.

    Uses exact string matching for pattern comparison. In takeover mode,
    patterns matching ignored_patterns are excluded (expected blanket allows).

    Args:
        native: Native permissions from settings.local.json
        toolguard: Toolguard permissions from toolguard_hook files
        ignored_patterns: Patterns to ignore (from takeover_mode.ignored_allow_patterns)
        governed_tools: When provided, restrict the result to patterns whose tool is
            in this set (compared via :func:`extract_tool_name`). A pattern for a tool
            toolguard does NOT govern (e.g. ``WebFetch(...)``, ``Skill(...)``) must not
            be reported divergent -- migrating it would move it out of
            ``settings.local.json`` and leave it enforced by neither toolguard nor
            native Claude (issue #1). The set is the config's live governed-tools list,
            so this tracks changes over time (e.g. WebFetch becoming governed) with no
            code change here. When ``None``, no tool filtering is applied.

    Returns:
        Dictionary with keys 'allow', 'deny', 'ask', each containing divergent patterns
    """
    ignored_set = set(ignored_patterns)

    result = {"allow": [], "deny": [], "ask": []}

    for perm_type in ["allow", "deny", "ask"]:
        native_patterns = set(native.get(perm_type, []))
        toolguard_patterns = set(toolguard.get(perm_type, []))

        # Find patterns in native but not in toolguard. Comparison #1 from
        # RuleEntry.identity()'s docstring ("same RULE", pattern-only): both
        # sides are already projected down to bare `.pattern` strings (see
        # get_toolguard_permissions), never `identity()`, so a rule carrying
        # metadata on one side and none/different metadata on the other is
        # never reported divergent -- switching this to identity() would make
        # migration re-add the "missing" native twin forever.
        divergent = native_patterns - toolguard_patterns

        # Filter out ignored patterns (only for 'allow' type in takeover mode)
        if perm_type == "allow":
            divergent = divergent - ignored_set

        # Restrict to governed tools when a set was supplied, so rules for
        # ungoverned tools are never treated as migratable divergences.
        if governed_tools is not None:
            divergent = {
                pattern
                for pattern in divergent
                if extract_tool_name(pattern) in governed_tools
            }

        result[perm_type] = sorted(list(divergent))

    return result


@dataclass(frozen=True)
class DivergenceCheckResult:
    """
    Outcome of a single :func:`check_and_warn_divergence` call.

    ``check_and_warn_divergence`` DETECTS divergence and decides whether a
    new warning is due (once per day); it deliberately does NOT write to
    toolguard's structured error log itself -- doing so
    would make this ``config``-layer module depend on
    :mod:`toolguard.error_log`, a ``runtime``-layer module (TOO-45 R5d). The
    caller (:mod:`toolguard.hook`, which already legitimately depends on
    ``error_log``) is responsible for calling
    :func:`toolguard.error_log.log_warning` with ``warning_message`` and
    ``corrective_steps`` when they are not ``None``.

    Attributes:
        divergent_patterns: Patterns found in native config but not in
            toolguard config (flattened across allow/deny/ask), or an empty
            list when there is nothing to report -- either no divergence was
            found, or a warning was already issued today.
        warning_message: The human-readable warning text to log, or ``None``
            when there is nothing new to warn about.
        corrective_steps: Suggested corrective-action text to log alongside
            ``warning_message``, or ``None`` under the same conditions.
    """

    divergent_patterns: List[str]
    warning_message: Optional[str] = None
    corrective_steps: Optional[str] = None


def check_and_warn_divergence(
    project_root: Path, takeover_config: Dict
) -> DivergenceCheckResult:
    """
    Check for config divergence and prepare a warning if found.

    Scans settings.local.json for patterns not present in toolguard config.
    A new warning is deduplicated once per day. It is only actually printed
    immediately before returning (the side effect being deduplicated) -- not
    before the analysis above it -- so an exception raised while
    loading/comparing config (e.g. a malformed config file) never leaves the
    day's slot claimed with nothing to show for it. A cheap read-only
    pre-check skips the analysis entirely on an already-warned day.

    This function DETECTS divergence, prints an immediate stderr notice, and
    marks that a warning has been issued. It does NOT write to toolguard's
    structured error log -- see :class:`DivergenceCheckResult`'s docstring
    for why; the caller is responsible for that.

    Args:
        project_root: Path to project root
        takeover_config: Takeover mode configuration dict with ignored_allow_patterns

    Returns:
        A :class:`DivergenceCheckResult`. ``divergent_patterns`` is empty,
        and ``warning_message``/``corrective_steps`` are ``None``, when there
        is nothing new to report.
    """
    if DIVERGENCE_WARNING.done(project_root):
        # Already warned today -- skip the analysis entirely.
        return DivergenceCheckResult(divergent_patterns=[])

    # Load native permissions from settings.local.json
    settings_path = project_root / ".claude" / "settings.local.json"
    native_perms = get_native_permissions(settings_path)

    # Load toolguard permissions via the config abstraction (no direct file I/O).
    # ignore_env_override=True: divergence analysis is project-scoped (it compares
    # this project's settings.local.json against this project's toolguard config),
    # so it must ignore CLAUDE_SETTINGS_PATH and discover the project hierarchy,
    # consistent with the migration tool's project-based behaviour.
    config = load_configuration(project_root, ignore_env_override=True)
    toolguard_perms = get_toolguard_permissions(config)

    # Find divergent patterns
    ignored_patterns = takeover_config.get("ignored_allow_patterns", [])
    if takeover_config.get("enabled", False):
        # In takeover mode, also include additional_ignored_patterns
        ignored_patterns = ignored_patterns + takeover_config.get(
            "additional_ignored_patterns", []
        )

    divergent = find_divergent_patterns(
        native_perms,
        toolguard_perms,
        ignored_patterns,
        governed_tools=set(config.governed_tools()),
    )

    # Collect all divergent patterns
    all_divergent = []
    for perm_type in ["allow", "deny", "ask"]:
        all_divergent.extend(divergent[perm_type])

    if not all_divergent:
        # Nothing to report -- no claim was ever taken, so a later call
        # today can still catch divergence appearing mid-day.
        return DivergenceCheckResult(divergent_patterns=[])

    # Format warning message
    warning_lines = [
        "[TOOLGUARD WARNING] New permission(s) found in settings.local.json but not in toolguard config:"
    ]
    for pattern in all_divergent[:10]:  # Limit to first 10 for readability
        warning_lines.append(f"  - {pattern}")

    if len(all_divergent) > 10:
        warning_lines.append(f"  ... and {len(all_divergent) - 10} more")

    warning_message = "\n".join(warning_lines)
    corrective_steps = "Consider migrating to toolguard config. Run: toolguard-migrate"

    # Immediate, direct stderr notice -- independent of the structured error
    # log the caller writes via log_warning (see DivergenceCheckResult). A
    # loss here means another process just warned -- stay quiet.
    if not DIVERGENCE_WARNING.warn(project_root, warning_message):
        return DivergenceCheckResult(divergent_patterns=[])

    return DivergenceCheckResult(
        divergent_patterns=all_divergent,
        warning_message=warning_message,
        corrective_steps=corrective_steps,
    )
