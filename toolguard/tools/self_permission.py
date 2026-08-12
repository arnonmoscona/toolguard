"""
Self-permissioning: the allow/ask rules toolguard's own skills need to function.

Toolguard's bundled skills shell out to the installed toolguard console scripts
(e.g. ``toolguard-audit``).  Under toolguard governance -- especially takeover
mode -- those invocations are themselves ``Bash`` commands toolguard must permit,
or the skill's own call is denied (a chicken-and-egg bootstrapping problem).

The table is declarative and writes nothing: toolguard must never self-grant a
privilege.  A caller suggests the rules, gets explicit user consent, and writes
them at the chosen scope.

Each entry's recommended list follows from its risk, not from convenience: a
read-only tool can stand on ``allow``, a config-mutating one is recommended as
``ask``.
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple

from toolguard.api import decide
from toolguard.config import Configuration


# ---------------------------------------------------------------------------
# Declarative self-permission table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfPermission:
    """
    One toolguard console script a skill runs via ``Bash`` and how to permit it.

    Attributes:
        command: The console-script name (e.g. ``'toolguard-audit'``).
        tool: The governed tool the invocation appears under -- always ``'Bash'``.
        pattern: The recommended permission pattern body (e.g.
            ``'toolguard-audit:*'``), i.e. the inner form of a ``Bash(...)`` rule.
        list_type: The recommended list for the rule: ``'allow'`` for read-only
            tools, ``'ask'`` for config-mutating tools.
        risk: ``'read-only'`` or ``'mutating'`` -- why the ``list_type`` differs.
        probe: A representative invocation used to evaluate whether the tool is
            already permitted under a configuration.
        rationale: Human-readable reason the rule is needed.
    """

    command: str
    tool: str
    pattern: str
    list_type: str
    risk: str
    probe: str
    rationale: str


#: Hook entry points (``toolguard``, ``toolguard-session-start``,
#: ``toolguard-update-check``) are deliberately absent from this table: Claude
#: Code's hook machinery runs them, never a Bash tool call.
_SELF_PERMISSIONS: Tuple[SelfPermission, ...] = (
    SelfPermission(
        command="toolguard-audit",
        tool="Bash",
        pattern="toolguard-audit:*",
        list_type="allow",
        risk="read-only",
        probe="toolguard-audit --format json",
        rationale=(
            "The security-audit and maintenance skills run toolguard-audit to read "
            "the config and report risk; it never writes, so it is safe to allow."
        ),
    ),
    SelfPermission(
        command="toolguard-maintain",
        tool="Bash",
        pattern="toolguard-maintain:*",
        list_type="ask",
        risk="mutating",
        probe="toolguard-maintain --format json",
        rationale=(
            "The maintenance skill runs toolguard-maintain, which can --apply --write "
            "config edits.  It is recommended as ASK (per-invocation consent) rather "
            "than a blanket allow, so the security config cannot be mutated without a "
            "human in the loop."
        ),
    ),
)


@dataclass(frozen=True)
class SelfPermissionStatus:
    """
    The current governance status of one :class:`SelfPermission` under a config.

    Attributes:
        permission: The self-permission entry being evaluated.
        current_verdict: :func:`~toolguard.api.decide`'s verdict for
            ``permission.probe`` (``'allow'``/``'ask'``/``'deny'``).
        needs_action: ``True`` for a read-only tool that is not ``'allow'``, or a
            mutating tool that is ``'deny'``.
        recommendation: Human-readable next step.
    """

    permission: SelfPermission
    current_verdict: str
    needs_action: bool
    recommendation: str


def required_self_permissions() -> Tuple[SelfPermission, ...]:
    """Return the fixed self-permission table."""
    return _SELF_PERMISSIONS


def _status_for(permission: SelfPermission, verdict: str) -> SelfPermissionStatus:
    """Classify one self-permission's current verdict into an actionable status."""
    if permission.risk == "read-only":
        needs_action = verdict != "allow"
        recommendation = (
            f"Add Bash({permission.pattern}) to the ALLOW list at your chosen scope."
            if needs_action
            else "Already allowed -- no action needed."
        )
    else:  # mutating
        if verdict == "deny":
            needs_action = True
            recommendation = (
                f"Add Bash({permission.pattern}) to the ASK list at your chosen scope "
                "(per-invocation consent; do NOT blanket-allow a mutating tool)."
            )
        elif verdict == "allow":
            needs_action = False
            recommendation = (
                "Currently ALLOWED.  Consider moving it to ASK: a mutating tool that "
                "is blanket-allowed lets the model edit the security config without a "
                "prompt."
            )
        else:  # ask
            needs_action = False
            recommendation = "Already ask -- no action needed."
    return SelfPermissionStatus(
        permission=permission,
        current_verdict=verdict,
        needs_action=needs_action,
        recommendation=recommendation,
    )


def evaluate_self_permissions(config: Configuration) -> List[SelfPermissionStatus]:
    """
    Evaluate every self-permission's probe through :func:`~toolguard.api.decide`
    and classify the verdict.

    Args:
        config: The resolved configuration hierarchy to evaluate against.

    Returns:
        One :class:`SelfPermissionStatus` per required self-permission, in
        declaration order.
    """
    statuses: List[SelfPermissionStatus] = []
    for permission in _SELF_PERMISSIONS:
        decision = decide(config, permission.tool, permission.probe)
        statuses.append(_status_for(permission, decision.decision))
    return statuses


def missing_self_permissions(config: Configuration) -> List[SelfPermissionStatus]:
    """
    Return only the self-permissions whose status has ``needs_action`` set.
    """
    return [s for s in evaluate_self_permissions(config) if s.needs_action]


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _self_permission_to_dict(permission: SelfPermission) -> Dict[str, str]:
    """Serialize a :class:`SelfPermission` to a JSON-friendly dict."""
    return {
        "command": permission.command,
        "tool": permission.tool,
        "pattern": permission.pattern,
        "list_type": permission.list_type,
        "risk": permission.risk,
        "probe": permission.probe,
        "rationale": permission.rationale,
    }


def self_permission_status_to_dict(status: SelfPermissionStatus) -> Dict[str, object]:
    """Serialize a :class:`SelfPermissionStatus` to a JSON-friendly dict."""
    return {
        "permission": _self_permission_to_dict(status.permission),
        "current_verdict": status.current_verdict,
        "needs_action": status.needs_action,
        "recommendation": status.recommendation,
    }
