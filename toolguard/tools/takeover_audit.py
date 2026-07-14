"""
Takeover-mode invariant checker for toolguard.

Takeover mode (see ``docs/takeover-mode.md``) is designed to make Claude operate
in a "never prompt" mode where native blanket allows (``Bash(*)``, ``Read(*)``,
etc.) tell Claude not to ask permission, while toolguard is the REAL gatekeeper.
For this to work correctly, several invariants must hold simultaneously.  This
module audits those invariants and emits ranked :class:`AuditFinding` records for
any violation.

Invariants checked
------------------
1. **CRITICAL / hook-not-registered**: The toolguard hook is NOT registered as a
   ``PreToolUse`` hook for a governed tool.  In this state, Claude calls the tool
   without consulting toolguard, so all blanket allows are live and toolguard
   NEVER RUNS for that tool.

2. **HIGH / takeover-conflict-with-blanket-allows**: A cross-level
   ``takeover_mode.enabled`` conflict is present (so effective takeover is OFF due
   to fail-safe), but blanket allows ARE present in native settings.  The result is
   that toolguard is silently disabled (fail-safe OFF) while native blanket allows
   bypass Claude prompts.

3. **HIGH / uncovered-blanket-allow**: Takeover is ON, but a blanket allow in a
   native settings layer is NOT in the effective ``ignored_allow_patterns`` set.
   Toolguard strips the ignored patterns; an uncovered blanket allow remains live
   and bypasses the real-gatekeeper role.

4. **LOW / loose-no-match-fallback**: ``no_match_fallback`` is set to
   anything other than ``'deny'`` (e.g. the TOO-15 default ``'ask'``,
   ``'allow_with_warning'``, or its deprecated legacy alias ``'warn_deny'``).
   Looser fallbacks mean that commands not matching any rule are prompted or
   allowed-with-a-warning rather than blocked -- weakening the fail-closed
   guarantee.

Design
------
- Reuses :class:`~toolguard.config.Configuration`,
  :class:`~toolguard.config.TakeoverConfig`, and
  :class:`~toolguard.config.TakeoverEnabledConflict` directly -- no conflict
  logic is reimplemented here.
- Native settings hooks are read from the ``hooks.PreToolUse`` section of each
  native (``is_native=True``) :class:`~toolguard.config.ConfigLayer`.
- A correctly-configured takeover setup must yield NO findings from
  :func:`audit_takeover`.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Set, Tuple

from toolguard.config import Configuration, Provenance, TakeoverConfig, _strip_tool_wrapper


# ---------------------------------------------------------------------------
# Severity (mirrors danger.py for consistency)
# ---------------------------------------------------------------------------


class AuditSeverity(IntEnum):
    """
    Ranked severity for takeover audit findings.

    Higher values are more severe.  Allows natural sorting (most severe first).
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def label(self) -> str:
        """Return the human-readable severity label."""
        return self.name


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditFinding:
    """
    A single takeover-invariant audit finding.

    Attributes:
        finding_id: Stable string identifier (e.g. ``'hook-not-registered'``).
        severity: :class:`AuditSeverity` rank.
        tool: Tool name the finding concerns (e.g. ``'Bash'``).  May be ``None``
            for configuration-wide findings.
        provenance: Origin of the affected config element, when traceable.
        description: Human-readable description of the invariant violation.
        impact: Explanation of the security impact.
        remediation: Suggested fix.
    """

    finding_id: str
    severity: AuditSeverity
    tool: Optional[str]
    provenance: Optional[Provenance]
    description: str
    impact: str
    remediation: str


# ---------------------------------------------------------------------------
# Hook registration helpers
# ---------------------------------------------------------------------------


def _get_registered_toolguard_tools(config: Configuration) -> Set[str]:
    """
    Return the set of tool names that have a toolguard ``PreToolUse`` hook registered.

    Reads the ``hooks.PreToolUse`` section from every NATIVE (``is_native=True``)
    config layer.  An entry qualifies as "toolguard-registered" when its ``hooks``
    list contains at least one entry whose ``command`` contains ``toolguard``
    (case-insensitive substring match).

    This is intentionally permissive in what qualifies as "the toolguard hook":
    any command path containing the string ``toolguard`` is accepted so that
    wrapper scripts and alternate install paths (e.g. ``uvx toolguard``,
    ``~/.local/bin/toolguard``) are all recognised.

    Args:
        config: The resolved configuration.

    Returns:
        Set of tool name strings for which a toolguard PreToolUse hook is registered.
    """
    registered: Set[str] = set()

    for layer in config.layers:
        if not layer.is_native:
            continue
        hooks_section = layer.content.get("hooks", {})
        if not isinstance(hooks_section, dict):
            continue
        pre_tool_use = hooks_section.get("PreToolUse", [])
        if not isinstance(pre_tool_use, list):
            continue

        for entry in pre_tool_use:
            if not isinstance(entry, dict):
                continue
            matcher = entry.get("matcher")
            if not isinstance(matcher, str):
                continue
            hooks = entry.get("hooks", [])
            if not isinstance(hooks, list):
                continue
            # Check if any hook command references toolguard
            for hook in hooks:
                if not isinstance(hook, dict):
                    continue
                command = hook.get("command", "")
                if isinstance(command, str) and "toolguard" in command.lower():
                    registered.add(matcher)
                    break

    return registered


def _get_blanket_allows_in_native(
    config: Configuration,
    takeover: TakeoverConfig,
) -> List[Tuple[str, Provenance]]:
    """
    Return native-layer blanket allow patterns that are NOT covered by the ignored set.

    A "blanket allow" is a ``Tool(*)`` form (e.g. ``Bash(*)``) in a native Claude
    settings layer.  When takeover is ON, these should all appear in the raw
    ``ignored_allow_patterns`` (or ``additional_ignored_patterns``) list so they
    are explicitly suppressed.

    Coverage check uses the RAW (wrapped) form rather than the normalised (stripped)
    form.  This way a blanket allow for ``mcp__custom__tool(*)`` is NOT considered
    covered by ``Bash(*)`` being in the ignored set -- they are different tools and
    the user must explicitly list each one.  The normalised check (``'*' in ignored``)
    would wrongly suppress the finding since all blanket-allow bodies strip to ``*``.

    Args:
        config: The resolved configuration.
        takeover: The resolved takeover config.

    Returns:
        List of ``(pattern, provenance)`` tuples for uncovered blanket allows.
    """
    # Build the set of RAW (as-authored, wrapper-preserved) ignored patterns
    raw_ignored = frozenset(
        list(takeover.ignored_allow_patterns) + list(takeover.additional_ignored_patterns)
    )

    uncovered: List[Tuple[str, Provenance]] = []

    for layer in config.layers:
        if not layer.is_native:
            continue
        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            continue
        for perm in permissions.get("allow", []):
            if not isinstance(perm, str):
                continue
            extracted = _strip_tool_wrapper(perm)
            # A blanket allow is a native permission whose BODY is exactly "*"
            if extracted == "*":
                # Check if this EXACT wrapper form is in the raw ignored set
                if perm not in raw_ignored:
                    uncovered.append((perm, layer.provenance))

    return uncovered


def _has_any_blanket_allow_in_native(config: Configuration) -> bool:
    """
    Return True when any native layer has a blanket allow (``Tool(*)`` pattern).

    Used to determine whether a takeover conflict is particularly dangerous: a
    conflict (takeover effectively OFF) combined with live blanket allows means
    toolguard is silently bypassed.

    Args:
        config: The resolved configuration.

    Returns:
        True when at least one native blanket allow exists.
    """
    for layer in config.layers:
        if not layer.is_native:
            continue
        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            continue
        for perm in permissions.get("allow", []):
            if isinstance(perm, str) and _strip_tool_wrapper(perm) == "*":
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def audit_takeover(
    config: Configuration,
    takeover: Optional[TakeoverConfig] = None,
) -> List[AuditFinding]:
    """
    Audit takeover-mode invariants and return ranked findings.

    Checks all four invariants (hook registration, conflict + blanket allows,
    uncovered blanket allows, loose fallback) and returns a finding for each
    violation.  A correctly-configured takeover setup returns an empty list.

    Findings are sorted by severity descending (CRITICAL first), then by tool
    name, then by finding_id for deterministic output.

    Args:
        config: The resolved configuration hierarchy to audit.
        takeover: Pre-resolved takeover configuration (optional; read from
            ``config.takeover_mode()`` when not provided).

    Returns:
        Sorted list of :class:`AuditFinding` records.  Empty when all
        invariants hold.
    """
    if takeover is None:
        takeover = config.takeover_mode()

    findings: List[AuditFinding] = []

    governed_set = set(config.governed_tools())
    registered_tools = _get_registered_toolguard_tools(config)
    # A wildcard/empty matcher ("*" or "") registers the toolguard hook for ALL
    # tools, so every governed tool is covered (review finding N1: without this,
    # a valid wildcard registration produced a false-positive hook-not-registered
    # for every governed tool).
    if "*" in registered_tools or "" in registered_tools:
        registered_governed = set(governed_set)
        missing_governed: Set[str] = set()
    else:
        registered_governed = governed_set & registered_tools
        missing_governed = governed_set - registered_tools

    # Invariant 1a: Per-tool hook registration (CRITICAL). One finding per governed
    # tool that has no toolguard PreToolUse hook. Under takeover the impact is
    # sharper: that tool has live blanket allows AND no hook, so it is completely
    # ungoverned.
    for tool in sorted(missing_governed):
        if takeover.enabled:
            impact = (
                f"Takeover mode is ON: '{tool}' carries live blanket allows AND has no "
                "toolguard hook, so it is COMPLETELY UNGOVERNED -- Claude executes any "
                "call to it with no prompt and no toolguard check."
            )
        else:
            impact = (
                "Claude will call this tool without consulting toolguard. Any blanket "
                "allow for this tool is fully live and toolguard NEVER RUNS for it -- "
                "complete permission bypass."
            )
        findings.append(
            AuditFinding(
                finding_id="hook-not-registered",
                severity=AuditSeverity.CRITICAL,
                tool=tool,
                provenance=None,
                description=(
                    f"Toolguard is NOT registered as a PreToolUse hook for "
                    f"governed tool '{tool}'."
                ),
                impact=impact,
                remediation=(
                    f"Add a PreToolUse hook entry for '{tool}' in .claude/settings.local.json "
                    f"(or the appropriate native settings file) pointing to the toolguard "
                    f"binary. Example:\n"
                    f'  {{"matcher": "{tool}", "hooks": [{{"type": "command", '
                    f'"command": "~/.local/bin/toolguard"}}]}}'
                ),
            )
        )

    # Invariant 1b: Partial / asymmetric registration. Toolguard is registered for
    # SOME governed tools but not all (the MIXED state). This is a high-confidence
    # misconfiguration -- clear intent to use toolguard, with gaps -- and is worse
    # than "nothing registered" because it silently splits the tool set into
    # governed vs completely-ungoverned. (Distinct from the per-tool findings above,
    # which fire regardless of whether the state is mixed or all-missing.)
    if registered_governed and missing_governed:
        if takeover.enabled:
            severity = AuditSeverity.CRITICAL
            impact = (
                "Takeover mode is ON: the unregistered governed tools carry live "
                "blanket allows and are COMPLETELY UNGOVERNED, while the registered "
                "tools ARE toolguard-governed. The result is an inconsistent, "
                "partially-bypassed security posture that is easy to miss."
            )
        else:
            severity = AuditSeverity.HIGH
            impact = (
                "Some governed tools are protected by toolguard and others are not, so "
                "the permission policy is enforced inconsistently across tools."
            )
        findings.append(
            AuditFinding(
                finding_id="partial-hook-registration",
                severity=severity,
                tool=None,
                provenance=None,
                description=(
                    "Toolguard is registered for SOME governed tools but not all. "
                    f"Registered: {sorted(registered_governed)}; "
                    f"missing: {sorted(missing_governed)}."
                ),
                impact=impact,
                remediation=(
                    "Register the toolguard PreToolUse hook for every governed tool "
                    f"(missing: {sorted(missing_governed)}), or remove the unintended "
                    "tools from governed_tools so the governed set matches what is "
                    "actually hooked."
                ),
            )
        )

    # Invariant 2: Takeover conflict + blanket allows (HIGH)
    if takeover.conflict is not None and _has_any_blanket_allow_in_native(config):
        findings.append(
            AuditFinding(
                finding_id="takeover-conflict-with-blanket-allows",
                severity=AuditSeverity.HIGH,
                tool=None,
                provenance=None,
                description=(
                    "Cross-level takeover_mode.enabled conflict detected: "
                    + takeover.conflict.describe()
                    + ". Effective takeover is OFF (fail-safe), but native blanket "
                    + "allows ARE present."
                ),
                impact=(
                    "Toolguard is effectively disabled (fail-safe set takeover to OFF) "
                    "while native blanket allows (e.g. Bash(*)) bypass Claude prompts. "
                    "The net effect is that Claude can execute ANY command without "
                    "toolguard intercepting it -- silent full bypass."
                ),
                remediation=(
                    "Resolve the takeover_mode.enabled conflict: ensure all levels "
                    "that set 'enabled' agree on the same value. Check "
                    "toolguard_hook.toml/.json at every hierarchy level."
                ),
            )
        )

    # Invariant 3: Uncovered blanket allows when takeover is ON (HIGH)
    if takeover.enabled:
        uncovered = _get_blanket_allows_in_native(config, takeover)
        for pattern, prov in uncovered:
            findings.append(
                AuditFinding(
                    finding_id="uncovered-blanket-allow",
                    severity=AuditSeverity.HIGH,
                    tool=None,
                    provenance=prov,
                    description=(
                        f"Native blanket allow '{pattern}' is NOT covered by the "
                        f"effective ignored_allow_patterns set while takeover is ON."
                    ),
                    impact=(
                        "Toolguard strips ignored blanket allows; this uncovered one "
                        "remains live in the permission evaluation and can bypass "
                        "toolguard rules for the corresponding tool."
                    ),
                    remediation=(
                        f"Add '{pattern}' to ignored_allow_patterns in your "
                        f"toolguard_hook.toml/json [takeover_mode] section, or "
                        f"additional_ignored_patterns if you do not want to list it "
                        f"explicitly."
                    ),
                )
            )

    # Invariant 4: Loose no_match_fallback (LOW)
    expected_fallback = "deny"
    if takeover.no_match_fallback != expected_fallback:
        findings.append(
            AuditFinding(
                finding_id="loose-no-match-fallback",
                severity=AuditSeverity.LOW,
                tool=None,
                provenance=None,
                description=(
                    f"no_match_fallback is '{takeover.no_match_fallback}', not 'deny'. "
                    f"Commands that match no allow rule will not be hard-blocked."
                ),
                impact=(
                    "Toolguard's fail-closed guarantee is weakened: unrecognised "
                    "commands are warned but not blocked (or are allowed, depending on "
                    "the fallback value). This increases the attack surface for new or "
                    "unexpected commands."
                ),
                remediation=(
                    "Set no_match_fallback = \"deny\" in [takeover_mode] of your "
                    "toolguard_hook.toml/json to restore fail-closed behaviour."
                ),
            )
        )

    # Sort: severity descending, then tool (None sorts first), then finding_id
    findings.sort(
        key=lambda f: (
            -f.severity.value,
            f.tool or "",
            f.finding_id,
        )
    )
    return findings


def effective_takeover_state(
    config: Configuration,
) -> TakeoverConfig:
    """
    Return the effective takeover-mode configuration for the given hierarchy.

    Thin convenience wrapper over :meth:`~toolguard.config.Configuration.takeover_mode`
    to make the entry point consistent with the audit module's API surface.

    Args:
        config: The resolved configuration.

    Returns:
        The resolved :class:`~toolguard.config.TakeoverConfig`.
    """
    return config.takeover_mode()
