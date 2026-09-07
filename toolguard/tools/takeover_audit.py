"""
Takeover-mode invariant checker for toolguard.

Takeover mode (see ``docs/takeover-mode.md``) has Claude treat native blanket
allows -- ``Bash(*)``, ``Read(*)`` and friends -- as "never prompt", leaving
toolguard as the real gatekeeper. The arrangement only holds while several
independent settings agree with each other. :func:`audit_takeover` checks them
and returns one :class:`AuditFinding` per violation; a correctly configured
setup yields none.

What each finding reads:

``hook-not-registered`` (CRITICAL) and ``partial-hook-registration``
    ``config.governed_tools()`` against the matchers that carry a toolguard
    ``PreToolUse`` hook in a native settings layer. A governed tool with no such
    hook is never handed to toolguard at all.
``takeover-conflict-with-blanket-allows`` (HIGH)
    a cross-level ``takeover_mode.enabled`` disagreement, which resolves
    fail-safe to OFF, while native blanket allows are present and therefore
    unfiltered.
``uncovered-blanket-allow`` (HIGH)
    takeover ON, and a native blanket allow absent from the raw
    ``ignored_allow_patterns``/``additional_ignored_patterns`` lists.
``loose-no-match-fallback`` (LOW)
    :meth:`~toolguard.config.Configuration.resolved_no_match_fallback`, the
    setting that actually governs, whenever it is anything other than
    ``'deny'``.
``loose-undecidable-fallback`` (HIGH)
    :meth:`~toolguard.config.Configuration.resolved_undecidable_fallback`, when
    it is ``'allow_with_warning'`` or ``'allow'``. ``'deny'`` is deliberately
    not flagged: it is stricter than the ``'ask'`` default, and a finding on a
    safe configuration would train users to ignore findings.
``loose-no-match-fallback-in-auto-mode`` (LOW) / ``loose-undecidable-fallback-in-auto-mode`` (HIGH)
    As the two findings above, but reading ``resolved_no_match_fallback_in_auto_mode``/
    ``resolved_undecidable_fallback_in_auto_mode`` -- this tool has no
    ``Invocation``, so it reports what the auto-mode setting would resolve to, not
    whether a live call is actually in auto mode. Fires only when the auto value is
    both loose AND different from the base one, so an unset auto setting (which always
    equals the base by construction) never duplicates the finding above.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import List, Optional, Set, Tuple

from toolguard.claude_code_contract import PRE_TOOL_USE_EVENT
from toolguard.config import (
    NO_MATCH_FALLBACK_IN_AUTO_MODE_KEY,
    NO_MATCH_FALLBACK_KEY,
    UNDECIDABLE_FALLBACK_IN_AUTO_MODE_KEY,
    UNDECIDABLE_FALLBACK_KEY,
    Configuration,
    Provenance,
    TakeoverConfig,
)
from toolguard.constants import (
    DECISION_ALLOW,
    DECISION_ASK,
    DECISION_DENY,
    FALLBACK_ALLOW_WITH_WARNING,
)
from toolguard.rule_entry import strip_tool_wrapper


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class AuditSeverity(IntEnum):
    """Severity rank for a takeover audit finding; higher is more severe."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def label(self) -> str:
        """Return the severity name, for display."""
        return self.name


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditFinding:
    """
    A single takeover-invariant audit finding.

    Attributes:
        finding_id: Stable string identifier, e.g. ``'hook-not-registered'``.
        severity: :class:`AuditSeverity` rank.
        tool: Tool the finding concerns, or ``None`` for a configuration-wide
            one.
        provenance: Origin of the affected config element, when traceable.
        description: What the violation is.
        impact: Its security consequence.
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
    Return the ``PreToolUse`` matchers that register a toolguard hook.

    Scans the ``hooks.PreToolUse`` section of every native (``is_native``) layer.
    A matcher qualifies when any of its hook entries has a ``command`` containing
    ``toolguard``, case-insensitively -- so wrapper scripts and alternate install
    paths (``uvx toolguard``, ``~/.local/bin/toolguard``) all count.

    Args:
        config: The resolved configuration.

    Returns:
        Set of matcher strings, exactly as written in the settings file; they are
        not interpreted here.
    """
    registered: Set[str] = set()

    for layer in config.layers:
        if not layer.is_native:
            continue
        hooks_section = layer.content.get("hooks", {})
        if not isinstance(hooks_section, dict):
            continue
        pre_tool_use = hooks_section.get(PRE_TOOL_USE_EVENT, [])
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
    Return native-layer blanket allows absent from the ignored-pattern lists.

    A blanket allow is a native ``permissions.allow`` entry whose body strips to
    ``*`` -- ``Bash(*)``, ``mcp__custom__tool(*)``, or a bare ``*``.

    Membership is tested on the raw, wrapper-intact form, so ``Bash(*)`` in the
    ignored lists does not make ``mcp__custom__tool(*)`` covered. Takeover's own
    filtering compares the wrapper-stripped form instead, via
    :meth:`~toolguard.config_types.TakeoverConfig.normalized_ignored_patterns`.

    Args:
        config: The resolved configuration.
        takeover: The resolved takeover config.

    Returns:
        List of ``(pattern, provenance)`` pairs, pattern wrapper-intact.
    """
    raw_ignored = frozenset(
        list(takeover.ignored_allow_patterns)
        + list(takeover.additional_ignored_patterns)
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
            extracted = strip_tool_wrapper(perm)
            if extracted == "*":
                if perm not in raw_ignored:
                    uncovered.append((perm, layer.provenance))

    return uncovered


def _has_any_blanket_allow_in_native(config: Configuration) -> bool:
    """
    Return True when any native layer carries a blanket allow.

    Args:
        config: The resolved configuration.

    Returns:
        True when at least one native ``permissions.allow`` entry strips to
        ``*``.
    """
    for layer in config.layers:
        if not layer.is_native:
            continue
        permissions = layer.content.get("permissions", {})
        if not isinstance(permissions, dict):
            continue
        for perm in permissions.get("allow", []):
            if isinstance(perm, str) and strip_tool_wrapper(perm) == "*":
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

    See the module docstring for what each finding reads. An empty list means
    every invariant held.

    Findings are sorted by severity descending, then by tool name (``None``
    sorts first), then by ``finding_id``, so the output is stable run to run.

    Args:
        config: The resolved configuration hierarchy to audit.
        takeover: Pre-resolved takeover configuration; read from
            ``config.takeover_mode()`` when not given.

    Returns:
        Sorted list of :class:`AuditFinding` records.
    """
    if takeover is None:
        takeover = config.takeover_mode()

    findings: List[AuditFinding] = []

    governed_set = set(config.governed_tools())
    registered_tools = _get_registered_toolguard_tools(config)
    # A "*" or "" matcher is taken to register the hook for every tool.
    if "*" in registered_tools or "" in registered_tools:
        registered_governed = set(governed_set)
        missing_governed: Set[str] = set()
    else:
        registered_governed = governed_set & registered_tools
        missing_governed = governed_set - registered_tools

    # Invariant 1a: one CRITICAL finding per governed tool with no toolguard hook.
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

    # Invariant 1b: the MIXED state -- some governed tools hooked, some not.
    # Reported in its own right, on top of the per-tool findings above, which
    # fire whether the state is mixed or nothing-registered.
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

    # Invariant 4: Loose no_match_fallback (LOW).
    #
    # Read off ``config.resolved_no_match_fallback()``, not the raw
    # ``[takeover_mode]`` value: the top-level key wins outright over the
    # legacy alias (see Configuration.resolved_no_match_fallback), so the raw
    # alias can disagree with the setting that actually governs.
    #
    # A blanket "!= 'deny'" test rather than an enumeration of the loose values,
    # so an added or renamed loose spelling needs no change here.
    expected_fallback = DECISION_DENY
    resolved_fallback = config.resolved_no_match_fallback()
    if resolved_fallback != expected_fallback:
        findings.append(
            AuditFinding(
                finding_id="loose-no-match-fallback",
                severity=AuditSeverity.LOW,
                tool=None,
                provenance=None,
                description=(
                    f"no_match_fallback is '{resolved_fallback}', not '{DECISION_DENY}'. "
                    f"Commands that match no allow rule will not be hard-blocked."
                ),
                impact=(
                    "Toolguard's fail-closed guarantee is weakened: unrecognised "
                    "commands are warned but not blocked (or are allowed, depending on "
                    "the fallback value). This increases the attack surface for new or "
                    "unexpected commands."
                ),
                remediation=(
                    f'Set no_match_fallback = "{DECISION_DENY}" in [takeover_mode] of '
                    "your toolguard_hook.toml/json to restore fail-closed behaviour."
                ),
            )
        )

    # Invariant 5: Loose undecidable_fallback (HIGH).
    #
    # Read off ``config``, not ``takeover``: undecidable_fallback is a top-level
    # toolguard_hook key with no [takeover_mode] alias, and applies whether or
    # not takeover is enabled. 'allow_with_no_warnings' never arrives here as
    # such -- resolved_undecidable_fallback() normalizes it to 'allow' first.
    resolved_undecidable = config.resolved_undecidable_fallback()
    if resolved_undecidable in (FALLBACK_ALLOW_WITH_WARNING, DECISION_ALLOW):
        if resolved_undecidable == FALLBACK_ALLOW_WITH_WARNING:
            execution_note = (
                "will execute with a warning instead of being asked about or denied."
            )
            no_rule_note = (
                ". toolguard.compound's governing principle is 'when in doubt, "
                "ASK: any segment that cannot be safely decomposed resolves to "
                "ASK rather than a silent allow of an undecomposed blob' -- "
                "this setting switches that principle off, turning every "
                "undecidable segment into a silent allow."
            )
        else:
            execution_note = (
                "will execute with NO warning at all, and nothing recorded, "
                "instead of being asked about or denied."
            )
            no_rule_note = (
                ", and -- unlike 'allow_with_warning' -- without even a "
                "warning log entry marking that it happened. "
                "toolguard.compound's governing principle is 'when in doubt, "
                "ASK: any segment that cannot be safely decomposed resolves to "
                "ASK rather than a silent allow of an undecomposed blob' -- "
                "this setting switches that principle off AND removes the "
                "one record that it did."
            )
        findings.append(
            AuditFinding(
                finding_id="loose-undecidable-fallback",
                severity=AuditSeverity.HIGH,
                tool=None,
                provenance=None,
                description=(
                    f"undecidable_fallback is '{resolved_undecidable}', not "
                    f"'{DECISION_ASK}' (the default) or '{DECISION_DENY}'. Commands "
                    "toolguard could not safely parse at all -- foreign inline code, "
                    "heredoc payloads, process substitution, unparseable control "
                    f"structures -- {execution_note}"
                ),
                impact=(
                    "This is a stronger weakening than a loose "
                    "no_match_fallback: no_match_fallback only affects "
                    "commands toolguard read and understood but that matched "
                    "no rule, so toolguard still knew what it was allowing. "
                    f"undecidable_fallback='{resolved_undecidable}' instead "
                    "executes commands toolguard could not parse at all, "
                    f"with NO rule ever evaluated against their contents{no_rule_note}"
                ),
                remediation=(
                    f'Set undecidable_fallback to "{DECISION_ASK}" (the default) or '
                    f'"{DECISION_DENY}" at the top level of your toolguard_hook.toml/json '
                    "to restore the ASK floor for command segments toolguard "
                    "cannot safely decompose."
                ),
            )
        )

    # Invariants 6/7: loose *_in_auto_mode fallback -- see this module's own
    # docstring for why it only fires when the auto value differs from the base
    # one. This is the gap invariant 4/5 alone cannot see: a strict base ('deny')
    # with a loose auto override is otherwise invisible here.
    resolved_fallback_auto = config.resolved_no_match_fallback_in_auto_mode()
    if (
        resolved_fallback_auto != resolved_fallback
        and resolved_fallback_auto != expected_fallback
    ):
        findings.append(
            AuditFinding(
                finding_id="loose-no-match-fallback-in-auto-mode",
                severity=AuditSeverity.LOW,
                tool=None,
                provenance=None,
                description=(
                    f"{NO_MATCH_FALLBACK_IN_AUTO_MODE_KEY} is "
                    f"'{resolved_fallback_auto}', looser than the non-auto "
                    f"{NO_MATCH_FALLBACK_KEY} ('{resolved_fallback}'). Under Claude "
                    "Code's auto permission mode, commands that match no allow rule "
                    "are governed by this setting instead."
                ),
                impact=(
                    "Toolguard's fail-closed guarantee is weakened specifically "
                    f"under auto mode, in a way invisible to the non-auto "
                    f"{NO_MATCH_FALLBACK_KEY} reading above."
                ),
                remediation=(
                    f'Set {NO_MATCH_FALLBACK_IN_AUTO_MODE_KEY} = "{DECISION_DENY}" (or '
                    f"leave it unset to defer to {NO_MATCH_FALLBACK_KEY}) to restore "
                    "fail-closed behaviour under auto mode."
                ),
            )
        )

    loose_undecidable_values = (FALLBACK_ALLOW_WITH_WARNING, DECISION_ALLOW)
    resolved_undecidable_auto = config.resolved_undecidable_fallback_in_auto_mode()
    if (
        resolved_undecidable_auto != resolved_undecidable
        and resolved_undecidable_auto in loose_undecidable_values
    ):
        findings.append(
            AuditFinding(
                finding_id="loose-undecidable-fallback-in-auto-mode",
                severity=AuditSeverity.HIGH,
                tool=None,
                provenance=None,
                description=(
                    f"{UNDECIDABLE_FALLBACK_IN_AUTO_MODE_KEY} is "
                    f"'{resolved_undecidable_auto}', looser than the non-auto "
                    f"{UNDECIDABLE_FALLBACK_KEY} ('{resolved_undecidable}'). Under "
                    "Claude Code's auto permission mode, commands toolguard could "
                    "not safely parse at all are governed by this setting instead."
                ),
                impact=(
                    "As with the non-auto reading above, but scoped to auto mode "
                    "and invisible to it: commands toolguard never evaluated any "
                    "rule against execute with no rule ever having seen them."
                ),
                remediation=(
                    f'Set {UNDECIDABLE_FALLBACK_IN_AUTO_MODE_KEY} to "{DECISION_ASK}" '
                    f'or "{DECISION_DENY}" (or leave it unset to defer to '
                    f"{UNDECIDABLE_FALLBACK_KEY}) to restore the ASK floor under "
                    "auto mode."
                ),
            )
        )

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

    Args:
        config: The resolved configuration.

    Returns:
        The resolved :class:`~toolguard.config.TakeoverConfig`.
    """
    return config.takeover_mode()
