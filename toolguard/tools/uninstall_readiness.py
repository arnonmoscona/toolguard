"""
Uninstall readiness: the fixed rule set an install seeds so toolguard's OWN
later teardown is not hard-blocked.

Toolguard's guided install can put the installing agent under full takeover
governance. If nothing permits the actions a clean uninstall needs -- editing
Claude's native settings to remove the hook registration, running
``uv tool uninstall``, deleting toolguard's own config and skill files --
teardown can block and has to be handed off out of band. A real install hit
exactly that (TOO-15).

The table is declarative and writes nothing itself: a caller gets explicit
user consent and writes the rules at the chosen scope.

What is easy to get wrong here:

- **Every entry is ``allow``, and ``ask`` is not a safe substitute.** An
  ``ask`` verdict was observed not reaching an interactive prompt during a
  real install (TOO-15; root cause unconfirmed), so seeding ``ask`` can
  reproduce the very hard-block this table exists to prevent.
- **The multi-token ``rm``/``uv tool uninstall`` patterns carry no ``:*``, and
  that is deliberate.** With it, the args wildcard crosses spaces, so
  ``rm -rf <skill dir>:*`` also admits ``rm -rf <skill dir> <any other path>``
  -- a rule naming one fixed path that grants deletion of a second, unrelated
  one. Written exactly, each admits only the command it names, at the price of
  sending a variant such as ``rm -rf <skill dir> -f`` to ``ask``.
- **``cd`` is here for ordinary navigation, and is safe to allow on its own
  merits.** ``cd`` itself runs no program, and the PEG parser extracts a
  ``$(...)``/backtick substitution in its argument as a separate sub-command
  that is checked in its own right.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from toolguard.api import decide
from toolguard.config import Configuration


# ---------------------------------------------------------------------------
# Declarative uninstall-readiness table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UninstallReadinessPermission:
    """
    One action a later uninstall needs and how to permit it ahead of time.

    Attributes:
        description: Short human-readable label for the action (e.g.
            ``'restore native settings (Write)'``).
        tool: The governed tool the action appears under -- ``'Bash'``,
            ``'Write'``, or ``'Edit'``.
        pattern: The recommended permission pattern body: for ``Bash``, the
            inner form of a ``Bash(...)`` rule (e.g. ``'cd:*'``); for
            ``Write``/``Edit``, the literal absolute file path.
        list_type: Always ``'allow'`` (see module docstring for why).
        probe: A representative target (command string or file path) used to
            evaluate whether the action is already permitted under a
            configuration.
        rationale: Human-readable reason the rule is needed.
    """

    description: str
    tool: str
    pattern: str
    list_type: str
    probe: str
    rationale: str


def required_uninstall_readiness_permissions(
    claude_dir: Path, settings_path: Path
) -> Tuple[UninstallReadinessPermission, ...]:
    """
    Build the declarative uninstall-readiness rule set for one scope.

    Args:
        claude_dir: The resolved ``.claude`` directory for the install's
            chosen scope (``~/.claude`` for user scope, or
            ``<project_dir>/.claude`` for project scope).
        settings_path: The resolved Claude Code settings file for that scope
            (``settings.json`` for user scope, ``settings.local.json`` for
            project scope).

    Returns:
        The fixed tuple of :class:`UninstallReadinessPermission` entries, in
        declaration order. Every entry is ``allow``.
    """
    settings_str = str(settings_path)
    hook_toml = str(claude_dir / "toolguard_hook.toml")
    hook_local_toml = str(claude_dir / "toolguard_hook.local.toml")
    audit_skill_dir = str(claude_dir / "skills" / "toolguard-security-audit")
    maintenance_skill_dir = str(claude_dir / "skills" / "toolguard-maintenance")

    return (
        UninstallReadinessPermission(
            description="cd navigation",
            tool="Bash",
            pattern="cd:*",
            list_type="allow",
            probe="cd /tmp",
            rationale=(
                "cd cannot execute code by itself -- it only changes the shell's "
                "working directory -- and toolguard's parser already extracts and "
                "separately checks any $(...)/backtick command substitution "
                "embedded in its argument. It is needed for ordinary navigation "
                "during install and uninstall alike."
            ),
        ),
        UninstallReadinessPermission(
            description="restore native settings (Write)",
            tool="Write",
            pattern=settings_str,
            list_type="allow",
            probe=settings_str,
            rationale=(
                "Uninstall restores the pre-install settings file to remove the "
                "hook registration. A literal, single-purpose path -- allowed so "
                "this step never hard-blocks once the user has already asked to "
                "uninstall."
            ),
        ),
        UninstallReadinessPermission(
            description="restore native settings (Edit)",
            tool="Edit",
            pattern=settings_str,
            list_type="allow",
            probe=settings_str,
            rationale=(
                "Same action as the Write entry above, covered under whichever "
                "tool the agent happens to use to restore the file's content."
            ),
        ),
        UninstallReadinessPermission(
            description="uninstall the package",
            tool="Bash",
            pattern="uv tool uninstall toolguard",
            list_type="allow",
            probe="uv tool uninstall toolguard",
            rationale=(
                "The final teardown step for a uv tool install. A literal, "
                "single-purpose command -- allowed so uninstall always completes."
            ),
        ),
        UninstallReadinessPermission(
            description="remove toolguard_hook.toml",
            tool="Bash",
            pattern=f"rm {hook_toml}",
            list_type="allow",
            probe=f"rm {hook_toml}",
            rationale="Deletes the config file the install wrote, at a known, fixed path.",
        ),
        UninstallReadinessPermission(
            description="remove toolguard_hook.local.toml",
            tool="Bash",
            pattern=f"rm {hook_local_toml}",
            list_type="allow",
            probe=f"rm {hook_local_toml}",
            rationale="Same as the toolguard_hook.toml entry, for the .local variant.",
        ),
        UninstallReadinessPermission(
            description="remove the security-audit skill",
            tool="Bash",
            pattern=f"rm -rf {audit_skill_dir}",
            list_type="allow",
            probe=f"rm -rf {audit_skill_dir}",
            rationale=(
                "Removes the bundled skill directory the install created, at a "
                "known, fixed path."
            ),
        ),
        UninstallReadinessPermission(
            description="remove the maintenance skill",
            tool="Bash",
            pattern=f"rm -rf {maintenance_skill_dir}",
            list_type="allow",
            probe=f"rm -rf {maintenance_skill_dir}",
            rationale="Same as the security-audit skill entry, for the maintenance skill.",
        ),
    )


@dataclass(frozen=True)
class UninstallReadinessStatus:
    """
    The current governance status of one :class:`UninstallReadinessPermission`.

    Attributes:
        permission: The uninstall-readiness entry being evaluated.
        current_verdict: :func:`~toolguard.api.decide`'s verdict for
            ``permission.probe`` (``'allow'``/``'ask'``/``'deny'``).
        needs_action: ``True`` when ``current_verdict`` is not ``'allow'``.
        recommendation: Human-readable next step.
    """

    permission: UninstallReadinessPermission
    current_verdict: str
    needs_action: bool
    recommendation: str


def _status_for(
    permission: UninstallReadinessPermission, verdict: str
) -> UninstallReadinessStatus:
    """Classify one uninstall-readiness entry's current verdict into an actionable status."""
    needs_action = verdict != "allow"
    recommendation = (
        f"Add {permission.tool}({permission.pattern}) to the ALLOW list -- "
        "otherwise this action is not guaranteed to complete during a later "
        "uninstall."
        if needs_action
        else "Already allowed -- no action needed."
    )
    return UninstallReadinessStatus(
        permission=permission,
        current_verdict=verdict,
        needs_action=needs_action,
        recommendation=recommendation,
    )


def evaluate_uninstall_readiness_permissions(
    config: Configuration, claude_dir: Path, settings_path: Path
) -> List[UninstallReadinessStatus]:
    """
    Evaluate every uninstall-readiness entry's probe through
    :func:`~toolguard.api.decide` and classify the verdict.

    Args:
        config: The resolved configuration hierarchy to evaluate against.
        claude_dir: The resolved ``.claude`` directory for the chosen scope.
        settings_path: The resolved settings file for the chosen scope.

    Returns:
        One :class:`UninstallReadinessStatus` per required entry, in
        declaration order.
    """
    statuses: List[UninstallReadinessStatus] = []
    for permission in required_uninstall_readiness_permissions(
        claude_dir, settings_path
    ):
        decision = decide(config, permission.tool, permission.probe)
        statuses.append(_status_for(permission, decision.decision))
    return statuses


def missing_uninstall_readiness_permissions(
    config: Configuration, claude_dir: Path, settings_path: Path
) -> List[UninstallReadinessStatus]:
    """
    Return only the entries that are not yet ``allow`` under *config*.
    """
    return [
        s
        for s in evaluate_uninstall_readiness_permissions(
            config, claude_dir, settings_path
        )
        if s.needs_action
    ]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _uninstall_readiness_permission_to_dict(
    permission: UninstallReadinessPermission,
) -> Dict[str, str]:
    """Serialize an :class:`UninstallReadinessPermission` to a JSON-friendly dict."""
    return {
        "description": permission.description,
        "tool": permission.tool,
        "pattern": permission.pattern,
        "list_type": permission.list_type,
        "probe": permission.probe,
        "rationale": permission.rationale,
    }


def uninstall_readiness_status_to_dict(
    status: UninstallReadinessStatus,
) -> Dict[str, object]:
    """Serialize an :class:`UninstallReadinessStatus` to a JSON-friendly dict."""
    return {
        "permission": _uninstall_readiness_permission_to_dict(status.permission),
        "current_verdict": status.current_verdict,
        "needs_action": status.needs_action,
        "recommendation": status.recommendation,
    }
