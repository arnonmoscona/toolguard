"""
Uninstall readiness: the allow rules a governed installing agent needs so its
OWN later teardown never gets hard-blocked.

Toolguard's guided install runbook can put the installing agent under full
takeover governance. If none of the actions a clean uninstall needs (editing
Claude's native settings to remove the hook registration, running
``uv tool uninstall``, deleting toolguard's own config/skill files) are
permitted anywhere, the agent's own tool calls for those actions are denied
outright -- forcing an out-of-band hand-off instead of a prompt. A real
install hit exactly this (TOO-15).

This module is the SINGLE SOURCE OF TRUTH for that fixed rule set. Like
:mod:`toolguard.tools.self_permission` (a sibling module, not extended here --
that one is scoped to what a bundled SKILL runs via Bash; this one is scoped
to what the INSTALLING AGENT itself needs for its own later teardown, a
different concern), it is deliberately declarative and writes nothing itself:
callers (the install runbook, via ``toolguard-install seed-self-perms``) get
explicit user consent and write the rules at the chosen scope.

Design guard-rails:

- **Every entry here is ``allow``, not ``ask``.** This is a deliberate change
  from an earlier ``ask``-gated design (Arnon, TOO-15): an ``ask`` verdict was
  observed NOT reliably reaching an interactive prompt in at least one real
  install (root cause still unconfirmed as of this writing), which means
  seeding ``ask`` rules does not actually guarantee uninstall completes --
  it can reproduce the exact hard-block this module exists to prevent.
  ``allow`` is immune to that failure mode. This is judged an acceptable
  trade-off specifically for this fixed, narrow set of actions because: (1)
  every pattern here is a literal, single-purpose command or exact file path
  -- not a wildcard grant -- so it can only do the one thing it is scoped to;
  and (2) by the time any of these would fire, the user has already given
  explicit, global consent by starting a guided uninstall conversation --
  the meaningful consent moment is "yes, uninstall toolguard," not each
  individual step of carrying that out.
- **``cd`` is included for the same reason it always was.** It cannot execute
  code by itself -- it only changes the shell's working directory -- and
  toolguard's own command parser already extracts and separately checks any
  embedded ``$(...)``/backtick command substitution in its argument, so
  allowing it does not create an enforcement gap on its own merits (this was
  true independent of the ``ask``-reliability question above).
- **Suggest, never auto-apply.** This module reports what is missing; the
  write is always an explicit, consented action performed elsewhere.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from toolguard.config import Configuration
from toolguard.tools.decision import decide


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
            ``<project_dir>/.claude`` for project scope) -- the same value
            :func:`toolguard.tools.installer._claude_dir` resolves.
        settings_path: The resolved Claude Code settings file for that scope
            (``settings.json`` for user scope, ``settings.local.json`` for
            project scope) -- the same value
            :func:`toolguard.tools.installer._settings_path` resolves.

    Returns:
        A fixed tuple of :class:`UninstallReadinessPermission` entries, in
        declaration order: ``cd`` navigation, restoring native settings
        (Write and Edit), uninstalling the package, removing the two
        toolguard config files, and removing the two bundled skill
        directories. Every entry is ``allow``.
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
            pattern="uv tool uninstall toolguard:*",
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
            pattern=f"rm {hook_toml}:*",
            list_type="allow",
            probe=f"rm {hook_toml}",
            rationale="Deletes the config file the install wrote, at a known, fixed path.",
        ),
        UninstallReadinessPermission(
            description="remove toolguard_hook.local.toml",
            tool="Bash",
            pattern=f"rm {hook_local_toml}:*",
            list_type="allow",
            probe=f"rm {hook_local_toml}",
            rationale="Same as the toolguard_hook.toml entry, for the .local variant.",
        ),
        UninstallReadinessPermission(
            description="remove the security-audit skill",
            tool="Bash",
            pattern=f"rm -rf {audit_skill_dir}:*",
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
            pattern=f"rm -rf {maintenance_skill_dir}:*",
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
        current_verdict: What the hook would decide for ``permission.probe``
            today (``'allow'``/``'ask'``/``'deny'``).
        needs_action: ``True`` when the entry is not yet ``allow`` -- i.e. the
            action could still be blocked or merely prompted (not guaranteed
            to complete) during a later uninstall.
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
    Evaluate every uninstall-readiness entry against *config* using the real
    decision engine.

    Reuses :func:`~toolguard.tools.decision.decide` (no reimplementation) to
    learn what the hook would actually decide for each entry's probe, then
    classifies the result.

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
    Return only the uninstall-readiness entries that need a rule suggested.

    These are the actions that are not yet ``allow`` under *config* -- the
    concrete rules the install runbook should offer to add, with the user's
    consent, at the chosen scope.
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
