"""
Ranked static risk findings over toolguard allow rules.

Detection is at the level of a single allow PATTERN, never of a command that
ran: each :class:`DangerDetector` pairs a predicate over one pattern body with a
severity, a stable ID, a rationale template and a remediation hint. The
predicates approximate what a pattern would permit -- none of them invokes the
runtime matcher -- so a clean result is not evidence that a pattern is safe.
The substring tests over-match on purpose; the literal tables miss anything
they do not enumerate, including several bodies that permit everything.

:data:`_DETECTORS` holds four of the five; do not restate the table in prose
here. The fifth, ``blanket-allow-outside-takeover``, is applied by
:func:`_audit_tool` directly, because it needs the takeover state a predicate
signature cannot carry.

Scope
-----
Every discovered layer is scanned, toolguard and native alike, but only its
``allow`` list. Native blanket allows that takeover mode intentionally
suppresses are filtered out before this module sees them, so they are never
findings. Whether the hook is in fact registered for a tool is a different
question, answered by :mod:`~toolguard.tools.takeover_audit`.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List, Optional, Tuple

from toolguard.config import Configuration, Provenance, TakeoverConfig
from toolguard.constants import FILE_TOOLS
from toolguard.patterns import PatternType, parse_pattern
from toolguard.tools.config_access import (
    discover_tools,
    neutralized_by_takeover,
    per_layer_rules,
)


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------


class Severity(IntEnum):
    """Ranked severity for danger findings. Higher is more severe, so findings sort."""

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
class DangerFinding:
    """
    A single danger finding.

    Attributes:
        detector_id: Stable string identifier for the detector that produced
            this finding (e.g. ``'arbitrary-exec-allow'``) -- safe as a dict key.
        severity: :class:`Severity` rank.
        tool: Tool name the flagged rule belongs to (e.g. ``'Bash'``).
        pattern: The flagged pattern with its ``Tool(...)`` wrapper stripped but
            any ``[regex]``/``[glob]``/``[native]`` prefix left intact -- the
            ``'anchor'`` remediation below needs that prefix.
        provenance: Origin of the rule in the configuration hierarchy.
        rationale: Human-readable explanation of the risk.
        remediation: Suggested fix or mitigation (human-readable text).
        takeover_active: Whether takeover mode was ON when this finding was
            produced (for display/context).
        list_type: Which permission list the flagged rule lives in
            (``'allow'``/``'deny'``/``'ask'``), so a structured remediation edit
            can target the right section.
        remediation_kind: ``'remove'`` (delete the rule -- always a safe
            tightening), ``'anchor'`` (prepend ``^`` to an unanchored
            ``[regex]`` body), or ``None`` when the fix is a judgement call
            carried only in ``remediation``.
    """

    detector_id: str
    severity: Severity
    tool: str
    pattern: str
    provenance: Optional[Provenance]
    rationale: str
    remediation: str
    takeover_active: bool
    list_type: str = "allow"
    remediation_kind: Optional[str] = None


# ---------------------------------------------------------------------------
# Detector infrastructure
# ---------------------------------------------------------------------------

_DetectorPredicate = Callable[[str, str, PatternType], bool]


@dataclass(frozen=True)
class DangerDetector:
    """
    A single danger-detection rule in the detector table.

    Attributes:
        detector_id: Stable string ID (used in :class:`DangerFinding`).
        severity: Severity rank.
        list_type: Which list to scan.  :func:`_audit_tool` walks allow lists
            only, so a detector set to anything but ``'allow'`` is never run.
        applies_to_tools: Set of tool names this detector fires for, or ``None``
            to match ALL tools.
        predicate: Callable ``(tool, body, ptype) -> bool`` that returns ``True``
            when the pattern is dangerous.
        rationale_template: Template for the rationale string (may reference
            ``{tool}`` and ``{pattern}``).
        remediation: Suggested remediation text.
        remediation_kind: See :class:`DangerFinding.remediation_kind`; carried
            onto every finding this detector produces.
    """

    detector_id: str
    severity: Severity
    list_type: str
    applies_to_tools: Optional[frozenset]  # None = all tools
    predicate: _DetectorPredicate
    rationale_template: str
    remediation: str
    remediation_kind: Optional[str] = None


# ---------------------------------------------------------------------------
# Predicate helpers
# ---------------------------------------------------------------------------


def _body_fnmatch_matches_any(body: str, literal_prefixes: Tuple[str, ...]) -> bool:
    """
    Return True when *body* is one of *literal_prefixes*, or continues one after
    a ``' '`` or ``':'`` -- the two separators between a command and its
    arguments in a pattern (``rm -rf /tmp``, ``rm -rf:*``).

    So the match is on whole leading tokens, not on characters: ``rm -rf`` does
    not match a body of ``rm -rfoo``. The separator is appended to the prefix, so
    an entry that already ends in one is reached only by the equality test or by
    a doubled separator: ``'python:'`` matches a body of exactly ``'python:'``,
    but not ``'python:*'``. Both prefix tables below contain such entries.

    Args:
        body: The pattern body (type prefix already removed).
        literal_prefixes: Dangerous literal command prefixes, lower-case.

    Returns:
        True when the body matches one of the prefixes.
    """
    body_lower = body.strip().lower()
    for prefix in literal_prefixes:
        if (
            body_lower == prefix
            or body_lower.startswith(prefix + " ")
            or body_lower.startswith(prefix + ":")
        ):
            return True
    return False


def _regex_body_matches_any(body: str, patterns: Tuple[str, ...]) -> bool:
    """
    Return True when any of *patterns* occurs literally inside a regex body.

    The regex is not parsed, so this over-matches on purpose -- a literal inside
    an alternation, a character class, or a negative lookahead that *forbids* the
    dangerous command reads the same as one that permits it.
    """
    body_lower = body.lower()
    for pat in patterns:
        if pat in body_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Detector predicates
# ---------------------------------------------------------------------------

# 1. Arbitrary code execution

#: Interpreter names shared by both branches of :func:`_is_arbitrary_exec` -- add
#: one here and both pick it up. A hand-picked list of common scripting
#: interpreters, not derived from usage evidence: php, deno, bun, pwsh, python2,
#: Rscript and the other shells are knowingly absent.
#:
#: ``exec`` and the multi-token eval forms are NOT folded in, because the two
#: branches treat them differently: ``exec`` is checked in the default/glob branch
#: only, and ``uv run python``/``sh -c``/``bash -c`` are leading prefixes there but
#: bare substrings in the regex branch.
_ARBITRARY_EXEC_INTERPRETERS: Tuple[str, ...] = (
    "python",
    "python3",
    "node",
    "ruby",
    "perl",
)

#: Command prefixes checked in the default/glob branch of :func:`_is_arbitrary_exec`.
_ARBITRARY_EXEC_PREFIXES: Tuple[str, ...] = (
    "uv run python",
    "python3",
    "sh -c",
    "bash -c",
    "python:",
    "python3:",
    "node:",
    "ruby:",
    "perl:",
    "sh -c:",
    "bash -c:",
)

#: Single-word command names for the default/glob branch: the shared interpreters
#: plus ``exec``, which is checked here and nowhere else.
_ARBITRARY_EXEC_BARE: Tuple[str, ...] = _ARBITRARY_EXEC_INTERPRETERS + ("exec",)


def _is_arbitrary_exec(tool: str, body: str, ptype: PatternType) -> bool:
    """Return True when the allow pattern permits arbitrary code execution."""
    # A file-path tool cannot execute anything.
    if tool in FILE_TOOLS:
        return False

    body_stripped = body.strip()
    body_lower = body_stripped.lower()

    if ptype == PatternType.REGEX:
        # ``exec`` is deliberately excluded from the regex tokens: it turns up in
        # negative lookaheads that FORBID exec (``(?!.*exec)``), and a substring
        # test cannot tell those from a rule that permits it. The default/glob
        # branch below checks ``exec`` precisely.
        return _regex_body_matches_any(
            body_lower,
            _ARBITRARY_EXEC_INTERPRETERS + ("uv run python", "sh -c", "bash -c"),
        )
    else:
        if _body_fnmatch_matches_any(body_lower, _ARBITRARY_EXEC_PREFIXES):
            return True
        for bare in _ARBITRARY_EXEC_BARE:
            if (
                body_lower == bare
                or body_lower.startswith(bare + ":")
                or body_lower.startswith(bare + " ")
            ):
                return True
        return False


# 2. Destructive commands
_DESTRUCTIVE_PREFIXES: Tuple[str, ...] = (
    "rm -rf",
    "rm -fr",
    "rm -r ",
    "rm -r:",
    "shred ",
    "shred:",
    "dd if=",
    "mkfs",
    "wipefs",
    "format ",
)


def _is_destructive(tool: str, body: str, ptype: PatternType) -> bool:
    """Return True when the allow pattern could permit a destructive command."""
    if tool in FILE_TOOLS:
        return False
    body_lower = body.strip().lower()

    if ptype == PatternType.REGEX:
        return _regex_body_matches_any(
            body_lower,
            ("rm -rf", "rm -fr", "shred", "dd if=", "mkfs", "wipefs"),
        )
    return _body_fnmatch_matches_any(body_lower, _DESTRUCTIVE_PREFIXES)


# 3. Secrets exposure

#: File-path indicators for well-known secret files. Every entry is substring-
#: tested against the whole pattern body, which is why generic words -- "secret",
#: "password", "credentials" -- are deliberately absent: they would fire on any
#: rule whose command or path happened to contain the word.
_SECRET_PATTERNS: Tuple[str, ...] = (
    ".env",
    ".ssh",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "id_dsa",
    ".pem",
    ".key",
    ".p12",
)


def _is_secrets_exposure(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True when the allow pattern could expose secrets.

    Unlike the exec and destructive predicates this does not exempt file-path
    tools: reading a private key is the risk, not only executing something.
    """
    body_lower = body.strip().lower()

    if ptype == PatternType.REGEX:
        return _regex_body_matches_any(body_lower, _SECRET_PATTERNS)

    for indicator in _SECRET_PATTERNS:
        if indicator in body_lower:
            return True
    return False


# 4. Unanchored regex allow
def _is_unanchored_regex(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True when the pattern is a ``[regex]`` allow without a ``^`` anchor.

    :func:`~toolguard.patterns.match_pattern` uses ``re.search``, so an
    unanchored body matches anywhere in the command: an allow of ``rm`` also
    allows ``echo "nope no rm here"``. Broader than it looks, hence a finding --
    but ``re.search`` is documented behaviour, not a defect, so the finding is
    about precision, hence MEDIUM.
    """
    if ptype != PatternType.REGEX:
        return False
    return not body.strip().startswith("^")


# 5. Blanket allow outside takeover
def _is_blanket_allow(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True for a body that matches everything: DEFAULT ``*``, GLOB ``*``/``**``,
    or a catch-all/empty REGEX.

    A recognition test against those exact forms, not a completeness test. A body
    outside them is not reported however broad it really is -- ``[native]*`` and a
    DEFAULT ``**`` both permit everything and both return False here.
    """
    body_stripped = body.strip()
    if ptype == PatternType.DEFAULT and body_stripped == "*":
        return True
    if ptype == PatternType.REGEX and body_stripped in (".*", ".+", "^.*$", "^.+$", ""):
        return True
    if ptype == PatternType.GLOB and body_stripped in ("*", "**"):
        return True
    return False


# ---------------------------------------------------------------------------
# Detector table
# ---------------------------------------------------------------------------

_DETECTORS: List[DangerDetector] = [
    DangerDetector(
        detector_id="arbitrary-exec-allow",
        severity=Severity.CRITICAL,
        list_type="allow",
        applies_to_tools=None,  # checked inside predicate
        predicate=_is_arbitrary_exec,
        rationale_template=(
            "Allow rule '{pattern}' for {tool} permits unrestricted arbitrary code "
            "execution (interpreter: python/node/ruby/perl/sh/bash/exec). An attacker "
            "or compromised model invocation can use this to escape any other toolguard "
            "restriction."
        ),
        remediation=(
            "Restrict the rule to specific scripts or subcommands. For example, replace "
            "'uv run python:*' with explicit named-script allows like 'uv run python scripts/lint.py:*'. "
            "If arbitrary execution is intentional, add a comment explaining why."
        ),
        remediation_kind="remove",
    ),
    DangerDetector(
        detector_id="destructive-cmd-allow",
        severity=Severity.HIGH,
        list_type="allow",
        applies_to_tools=None,
        predicate=_is_destructive,
        rationale_template=(
            "Allow rule '{pattern}' for {tool} permits a destructive file-system command "
            "(rm -rf, shred, dd, mkfs, wipefs, etc.). A single misuse can cause permanent "
            "data loss."
        ),
        remediation=(
            "Narrow the pattern to a specific safe target path or remove the rule. "
            "Consider using a deny rule in [hard_deny] to prevent accidental execution."
        ),
        remediation_kind="remove",
    ),
    DangerDetector(
        detector_id="secrets-exposure-allow",
        severity=Severity.HIGH,
        list_type="allow",
        applies_to_tools=None,
        predicate=_is_secrets_exposure,
        rationale_template=(
            "Allow rule '{pattern}' for {tool} may expose secrets or credentials "
            "(.env, .ssh, private keys, PEM files). Reading or executing these paths "
            "leaks sensitive data to the model."
        ),
        remediation=(
            "Remove or narrow this rule. If access to a specific secret file is needed "
            "for a tooling task, prefer a more-specific path and add a comment. "
            "Consider using a hard_deny rule to block .env and .ssh access globally."
        ),
        remediation_kind="remove",
    ),
    DangerDetector(
        detector_id="unanchored-regex-allow",
        severity=Severity.MEDIUM,
        list_type="allow",
        applies_to_tools=None,
        predicate=_is_unanchored_regex,
        rationale_template=(
            "Allow rule '{pattern}' for {tool} is a [regex] pattern without a '^' anchor. "
            "Toolguard uses re.search (not re.fullmatch), so this pattern matches anywhere "
            "in the command string -- it may permit more commands than intended."
        ),
        remediation=(
            "Add a '^' anchor at the start of the regex body to ensure it matches only "
            "from the beginning of the command. Example: '[regex]^git\\\\b' instead of "
            "'[regex]git\\\\b'. If unanchored matching is intentional, add a comment."
        ),
        remediation_kind="anchor",
    ),
    # blanket-allow-outside-takeover is not a table entry -- see _is_blanket_allow.
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def danger(
    config: Configuration,
    takeover: Optional[TakeoverConfig] = None,
) -> List[DangerFinding]:
    """
    Audit ``config``'s allow rules and return ranked findings.

    A pattern takeover mode has neutralized -- a native allow in the effective
    ignored set -- is skipped by every detector. Everything else is a candidate,
    whichever layer it came from.

    Args:
        config: The resolved configuration.
        takeover: Pre-resolved takeover configuration; read from ``config``
            when not provided.

    Returns:
        :class:`DangerFinding` records sorted by descending severity, then tool,
        then pattern.  Empty when nothing is detected.
    """
    if takeover is None:
        takeover = config.takeover_mode()

    findings: List[DangerFinding] = []

    ignored_extracted = takeover.normalized_ignored_patterns()

    for tool in discover_tools(config):
        findings.extend(_audit_tool(config, tool, takeover, ignored_extracted))

    findings.sort(key=lambda f: (-f.severity.value, f.tool, f.pattern))
    return findings


#: detector_id :func:`assess_pattern_risk` uses for its own, takeover-independent
#: blanket-allow flag -- distinct from ``blanket-allow-outside-takeover``, which
#: only applies inside :func:`danger`'s takeover-aware audit of a layer already
#: in the config.
_PROPOSED_BLANKET_ALLOW_ID = "blanket-allow"


def assess_pattern_risk(tool: str, pattern: str) -> Tuple[str, ...]:
    """
    Statically flag one proposed allow pattern, independent of any config
    layer, corpus, or takeover state.

    Runs the same content detectors :func:`danger` applies to a rule already in
    a layer, plus a takeover-independent blanket-allow check, against a pattern
    that has not been added anywhere yet -- so a tool-wide ``'*'`` proposal is
    distinguishable from a narrow one even before any corpus exercises it.

    Args:
        tool: Tool the pattern would apply to.
        pattern: Wrapper-free allow pattern body (e.g. ``'git push:*'``, ``'*'``).

    Returns:
        The ``detector_id`` of every check the pattern trips, in table order.
        Empty when nothing is detected -- not evidence of safety, only that
        this module's tables do not happen to catch it.
    """
    ptype, body = parse_pattern(pattern, extended_syntax=True)
    ids: List[str] = []
    if _is_blanket_allow(tool, body, ptype):
        ids.append(_PROPOSED_BLANKET_ALLOW_ID)
    for detector in _DETECTORS:
        if detector.list_type != "allow":
            continue
        if (
            detector.applies_to_tools is not None
            and tool not in detector.applies_to_tools
        ):
            continue
        if detector.predicate(tool, body, ptype):
            ids.append(detector.detector_id)
    return tuple(ids)


def _audit_tool(
    config: Configuration,
    tool: str,
    takeover: TakeoverConfig,
    ignored_extracted: frozenset,
) -> List[DangerFinding]:
    """
    Run all detectors over the allow rules for a single tool, layer by layer.

    Args:
        config: The resolved configuration.
        tool: Tool name to audit.
        takeover: Resolved takeover config.
        ignored_extracted: Unused -- :func:`neutralized_by_takeover` derives the
            same set from *takeover* itself.

    Returns:
        Findings for this tool.
    """
    findings: List[DangerFinding] = []
    layer_rules = per_layer_rules(config, tool)

    for lr in layer_rules:
        is_native = lr.provenance.source_type == "claude"

        for pattern in lr.allow:
            ptype, body = parse_pattern(pattern, extended_syntax=True)

            # Dead on every path in this repo: config.permission_layers already
            # drops ignored allows from native layers, so nothing reaching here
            # is neutralized. The same call in the second loop below is dead too.
            if neutralized_by_takeover(pattern, is_native, takeover):
                continue

            # Blanket allows belong to the second loop. Skipping them here stops
            # one pattern (say [regex].*) being reported twice -- once as a
            # blanket allow and again by whichever content detector it trips.
            if _is_blanket_allow(tool, body, ptype):
                continue

            for detector in _DETECTORS:
                if detector.list_type != "allow":
                    continue
                if (
                    detector.applies_to_tools is not None
                    and tool not in detector.applies_to_tools
                ):
                    continue

                if detector.predicate(tool, body, ptype):
                    rationale = detector.rationale_template.format(
                        tool=tool, pattern=pattern
                    )
                    findings.append(
                        DangerFinding(
                            detector_id=detector.detector_id,
                            severity=detector.severity,
                            tool=tool,
                            pattern=pattern,
                            provenance=lr.provenance,
                            rationale=rationale,
                            remediation=detector.remediation,
                            takeover_active=takeover.enabled,
                            list_type=detector.list_type,
                            remediation_kind=detector.remediation_kind,
                        )
                    )
                    # One content finding per pattern: the first matching
                    # detector wins, and _DETECTORS is ordered most-severe-first
                    # so that is the worst one.
                    break

        # Blanket allows, in any layer -- native or toolguard's own.
        for pattern in lr.allow:
            ptype, body = parse_pattern(pattern, extended_syntax=True)
            if _is_blanket_allow(tool, body, ptype):
                if neutralized_by_takeover(pattern, is_native, takeover):
                    continue
                findings.append(
                    DangerFinding(
                        detector_id="blanket-allow-outside-takeover",
                        severity=Severity.CRITICAL,
                        tool=tool,
                        pattern=pattern,
                        provenance=lr.provenance,
                        rationale=(
                            f"Allow rule '{pattern}' for {tool} is a blanket wildcard "
                            f"that permits ALL commands/paths -- a COMPLETE governance "
                            f"bypass for this tool (broader than any specific dangerous "
                            f"allow): toolguard permits everything for {tool}. Takeover "
                            f"mode is {'ON' if takeover.enabled else 'OFF'}."
                        ),
                        remediation=(
                            "Replace with specific allow rules. If this is a deliberate "
                            "takeover-mode setup, ensure takeover.enabled is True and "
                            "the pattern appears in ignored_allow_patterns."
                        ),
                        takeover_active=takeover.enabled,
                        list_type="allow",
                        remediation_kind="remove",
                    )
                )

    return findings
