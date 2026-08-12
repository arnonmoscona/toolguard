"""
Config divergence detection: permissions present in Claude's native
settings.local.json but absent from toolguard's own configuration.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

from toolguard import once_per
from toolguard.config import is_tool_wrapper, load_configuration
from toolguard.config_validation import extract_tool_name
from toolguard.error_reporter import report_warning

#: Once-per-day throttle for the divergence warning.
DIVERGENCE_WARNING = once_per.day(
    "divergence_warning", "the configuration divergence warning"
)


def get_native_permissions(settings_path: Path) -> Dict[str, List[str]]:
    """
    Read tool-scoped allow/deny/ask patterns from a Claude settings file.

    Every ``Tool(...)``-wrapped entry is kept, whatever the tool -- including
    tools toolguard does not govern. Restricting to governed tools is a
    separate step, in :func:`find_divergent_patterns`.

    Args:
        settings_path: Path to a ``settings.local.json``.

    Returns:
        ``{'allow': [...], 'deny': [...], 'ask': [...]}``, wrappers intact.
        A missing file yields three empty lists silently; an unreadable or
        unparseable one yields the same after reporting a warning.
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

    for perm_type in ["allow", "deny", "ask"]:
        for perm in permissions.get(perm_type, []):
            if is_tool_wrapper(perm):
                result[perm_type].append(perm)

    return result


def get_toolguard_permissions(config) -> Dict[str, List[str]]:
    """
    Extract raw permission patterns from a resolved toolguard configuration.

    Patterns keep their ``Tool(...)`` wrappers, so they compare directly
    against the output of :func:`get_native_permissions`.

    Args:
        config: A resolved :class:`~toolguard.config.Configuration`.

    Returns:
        ``{'allow': [...], 'deny': [...], 'ask': [...]}``.
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
    Find patterns present in *native* but not in *toolguard*.

    Comparison is exact string equality over whole wrapped patterns, so a
    native ``Bash(git *)`` and a toolguard ``Bash(git*)`` are two different
    rules.

    Args:
        native: Permissions read from ``settings.local.json``.
        toolguard: Permissions read from ``toolguard_hook`` files.
        ignored_patterns: Patterns dropped from the ``allow`` result only.
        governed_tools: When given, keep only patterns whose tool (per
            :func:`extract_tool_name`) is in this set; ``None`` applies no
            tool filter. A rule for a tool toolguard does not govern (e.g.
            ``WebFetch(...)``) must never be reported divergent -- migrating
            it removes it from ``settings.local.json``, leaving it enforced
            by neither toolguard nor native Claude.

    Returns:
        ``{'allow': [...], 'deny': [...], 'ask': [...]}``, each sorted.
    """
    ignored_set = set(ignored_patterns)

    result = {"allow": [], "deny": [], "ask": []}

    for perm_type in ["allow", "deny", "ask"]:
        native_patterns = set(native.get(perm_type, []))
        toolguard_patterns = set(toolguard.get(perm_type, []))

        divergent = native_patterns - toolguard_patterns

        if perm_type == "allow":
            divergent = divergent - ignored_set

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
    Outcome of one :func:`check_and_warn_divergence` call.

    Attributes:
        divergent_patterns: Patterns found in native config but not in
            toolguard config, flattened across allow/deny/ask. Empty when
            there is nothing to report -- either no divergence was found, or
            a warning had already been issued today.
        warning_message: The warning text, for the caller to log; ``None``
            when there is nothing new to warn about.
        corrective_steps: Suggested corrective-action text to log alongside
            ``warning_message``; ``None`` under the same conditions.
    """

    divergent_patterns: List[str]
    warning_message: Optional[str] = None
    corrective_steps: Optional[str] = None


def check_and_warn_divergence(
    project_root: Path, takeover_config: Dict
) -> DivergenceCheckResult:
    """
    Compare settings.local.json against toolguard config, warning once a day.

    A new warning is printed to stderr here, and also returned so the caller
    can log it too.

    The day's claim is taken at the very end, once there is something to
    show for it: an exception while loading or comparing config never
    consumes the day, and a day that found no divergence stays open for
    divergence appearing later that day.

    Args:
        project_root: Path to the project root.
        takeover_config: Takeover-mode settings.
            ``ignored_allow_patterns`` is always honoured;
            ``additional_ignored_patterns`` only when ``enabled``.

    Returns:
        A :class:`DivergenceCheckResult`, empty and ``None``-valued when
        there is nothing new to report.
    """
    # Cheap read-only pre-check, so an already-warned day skips the analysis.
    if DIVERGENCE_WARNING.done(project_root):
        return DivergenceCheckResult(divergent_patterns=[])

    settings_path = project_root / ".claude" / "settings.local.json"
    native_perms = get_native_permissions(settings_path)

    # ignore_env_override=True: this compares one project's
    # settings.local.json against that same project's toolguard config, so a
    # stale CLAUDE_SETTINGS_PATH pointing at an unrelated project must not be
    # honoured.
    config = load_configuration(project_root, ignore_env_override=True)
    toolguard_perms = get_toolguard_permissions(config)

    ignored_patterns = takeover_config.get("ignored_allow_patterns", [])
    if takeover_config.get("enabled", False):
        ignored_patterns = ignored_patterns + takeover_config.get(
            "additional_ignored_patterns", []
        )

    divergent = find_divergent_patterns(
        native_perms,
        toolguard_perms,
        ignored_patterns,
        governed_tools=set(config.governed_tools()),
    )

    all_divergent = []
    for perm_type in ["allow", "deny", "ask"]:
        all_divergent.extend(divergent[perm_type])

    if not all_divergent:
        return DivergenceCheckResult(divergent_patterns=[])

    warning_lines = [
        "[TOOLGUARD WARNING] New permission(s) found in settings.local.json but not in toolguard config:"
    ]
    for pattern in all_divergent[:10]:  # Limit to first 10 for readability
        warning_lines.append(f"  - {pattern}")

    if len(all_divergent) > 10:
        warning_lines.append(f"  ... and {len(all_divergent) - 10} more")

    warning_message = "\n".join(warning_lines)
    corrective_steps = "Consider migrating to toolguard config. Run: toolguard-migrate"

    # warn() prints and takes the day's claim in one step. False means
    # another invocation claimed it since the pre-check above and has
    # already printed.
    if not DIVERGENCE_WARNING.warn(project_root, warning_message):
        return DivergenceCheckResult(divergent_patterns=[])

    return DivergenceCheckResult(
        divergent_patterns=all_divergent,
        warning_message=warning_message,
        corrective_steps=corrective_steps,
    )
