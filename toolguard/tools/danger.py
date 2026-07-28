"""
Ranked static risk findings over toolguard allow rules.

This module audits the REAL toolguard rules (from ``toolguard_hook`` layers and
native ``settings.*`` layers, after takeover filtering) and flags patterns that
are inherently dangerous -- regardless of whether they were intentionally placed
there.

Scope
-----
``danger`` audits toolguard rules only.  Native blanket allows (``Bash(*)``,
``Read(*)``, etc.) are NOT flagged when takeover mode is ON and those patterns
are in the ignored-allow set AND the hook is registered for the relevant tool.
The appropriate module for that is :mod:`~toolguard.tools.takeover_audit`.

Detector table
--------------
The detector set is SIMPLE and DATA-DRIVEN: a list of :class:`DangerDetector`
entries, each with a predicate (pattern-level check), severity, a stable string
ID, a rationale template, and a remediation hint.  The agent layer (skill) handles
subtle judgement; this module handles mechanical pattern matching.

Detectors (in severity order, highest first):

1. **CRITICAL / arbitrary-exec-allow**: ``allow`` rule that permits unrestricted
   arbitrary code execution: ``uv run python``, bare ``python`` / ``python3``,
   ``node``, ``ruby``, ``perl``, ``sh -c``, ``bash -c``, ``exec``.
   Severity: CRITICAL (unfiltered code exec defeats the point of toolguard).

2. **HIGH / destructive-cmd-allow**: ``allow`` rule permitting ``rm -rf``-class
   destructive commands: ``rm -rf``, ``rm -r``, ``shred``, ``dd if=``,
   ``mkfs``, ``wipefs``.  A wildcard that would match these is also flagged.
   Severity: HIGH.

3. **HIGH / secrets-exposure-allow**: ``allow`` rule that could expose secrets
   via Bash execution or file-path tools: patterns matching ``.env``, ``.env.*``,
   ``~/.ssh``, ``id_rsa``, ``id_ed25519``, ``id_ecdsa``, ``*.pem``, ``*.key``.
   Severity: HIGH.

4. **MEDIUM / unanchored-regex-allow**: A ``[regex]`` allow rule that does NOT
   start with ``^``.  Because :func:`~toolguard.patterns.match_pattern` uses
   ``re.search`` (not ``re.fullmatch``), an unanchored regex matches anywhere
   in the command string -- a pattern like ``rm`` would match ``echo "no rm"``
   too.  This is not necessarily a bug (toolguard documents it), but it IS a
   precision risk and every such rule deserves a human eye.
   Severity: MEDIUM.

5. **CRITICAL / blanket-allow-outside-takeover**: A wildcard allow (``*`` or
   matching every input, e.g. pattern body is just ``*``) that is NOT covered by
   the takeover ignored set.  Such a rule bypasses ALL toolguard checks for that
   tool -- a complete governance bypass -- so it is flagged CRITICAL even though it
   may be the user's explicit intent.

Takeover-mode awareness
-----------------------
The :func:`danger` function accepts a pre-resolved
:class:`~toolguard.config.TakeoverConfig` so it can adjust phrasing and severity.
For example: a ``Bash(*)`` allow in a NATIVE layer is NOT a finding when takeover
is ON and ``Bash(*)`` is in the ignored set (it is a deliberate setup artefact).

"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Callable, List, Optional, Tuple

from toolguard.config import Configuration, Provenance, TakeoverConfig
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
    """
    Ranked severity for danger findings.

    Higher values are more severe.  The integer mapping allows natural sorting
    (most severe first).
    """

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    def label(self) -> str:
        """Return the human-readable severity label."""
        return self.name  # 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DangerFinding:
    """
    A single danger finding.

    Attributes:
        detector_id: Stable string identifier for the detector that produced
            this finding (e.g. ``'arbitrary-exec-allow'``).  Safe to use as
            a dict key or for filtering.
        severity: :class:`Severity` rank.
        tool: Tool name the flagged rule belongs to (e.g. ``'Bash'``).
        pattern: The raw flagged pattern (inner form, tool wrapper stripped).
        provenance: Origin of the rule in the configuration hierarchy.
        rationale: Human-readable explanation of the risk.
        remediation: Suggested fix or mitigation (human-readable text).
        takeover_active: Whether takeover mode was ON when this finding was
            produced (for display/context).
        list_type: Which permission list the flagged rule lives in
            (``'allow'``/``'deny'``/``'ask'``); needed to build a structured
            remediation edit that targets the right section.
        remediation_kind: Mechanical remediation kind the audit layer can turn
            into a structured :class:`~toolguard.tools.edit_proposal.EditProposal`:
            ``'remove'`` (delete the dangerous rule -- always a safe tightening),
            ``'anchor'`` (prepend ``^`` to an unanchored ``[regex]`` body), or
            ``None`` when the fix is a judgement call carried only in
            ``remediation`` text.
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

# Predicate type: given (tool, pattern_body, pattern_type) -> bool
_DetectorPredicate = Callable[[str, str, PatternType], bool]


@dataclass(frozen=True)
class DangerDetector:
    """
    A single danger-detection rule in the detector table.

    Attributes:
        detector_id: Stable string ID (used in :class:`DangerFinding`).
        severity: Severity rank.
        list_type: Which list to scan (``'allow'``, ``'deny'``, or ``'ask'``).
            Almost all detectors target ``'allow'``.
        applies_to_tools: Set of tool names this detector fires for, or ``None``
            to match ALL tools.
        predicate: Callable ``(tool, body, ptype) -> bool`` that returns ``True``
            when the pattern is dangerous.
        rationale_template: Template for the rationale string (may reference
            ``{tool}`` and ``{pattern}``).
        remediation: Suggested remediation text.
        remediation_kind: Mechanical remediation kind for a structured fix
            (``'remove'``, ``'anchor'``, or ``None`` -- see
            :class:`DangerFinding.remediation_kind`).  Carried onto every finding
            this detector produces.
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
    Return True when the DEFAULT/GLOB pattern body starts with any of the given
    literal prefixes, ignoring extended-syntax bodies.

    This is a conservative first-pass check: if the body literally starts with
    the dangerous prefix (possibly followed by whitespace and a wildcard like
    ``:*``), the rule might allow the dangerous command.

    Args:
        body: The stripped pattern body (without type prefix).
        literal_prefixes: Tuple of dangerous literal command prefixes to check.

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
    Return True when a regex body could match any of the dangerous literal strings.

    Uses a simple substring check: if any dangerous literal appears as a
    sub-pattern in the regex body it might allow the dangerous command.
    This is a conservative heuristic (false positives are acceptable; false
    negatives are not).

    Args:
        body: The regex body string.
        patterns: Dangerous literal strings to look for inside the regex.

    Returns:
        True when a dangerous literal is found in the regex body.
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
#
# Single source of truth for the INTERPRETER NAMES that, when permitted, allow
# arbitrary code execution.  Both matching branches of ``_is_arbitrary_exec`` build
# on this so the regex and default/glob checks cannot silently drift apart -- add a
# new interpreter HERE and both branches pick it up.
#
# This is a heuristic curation of the common scripting interpreters, NOT derived
# from usage evidence; known omissions (php, deno, bun, pwsh/powershell, python2,
# Rscript, other shells, ...) are deliberately out for now.  The shell-eval forms
# (``sh -c``/``bash -c``/``uv run python``) and ``exec`` are matched slightly
# differently per branch (see below), so they are added alongside this set rather
# than folded into it: ``exec`` is checked only in the default/glob branch, and the
# multi-token eval forms are prefixes in that branch but substrings in the regex one.
_ARBITRARY_EXEC_INTERPRETERS: Tuple[str, ...] = (
    "python",
    "python3",
    "node",
    "ruby",
    "perl",
)

_ARBITRARY_EXEC_PREFIXES: Tuple[str, ...] = (
    "uv run python",
    "python3",
    # NOTE: bare-name forms ("python <args>", "node <args>", ...) are covered by
    # _ARBITRARY_EXEC_BARE below. Trailing-space entries were removed here because
    # _body_fnmatch_matches_any strips the body, so "node " could never match.
    "sh -c",
    "bash -c",
    "python:",  # handle toolguard pattern form python:*
    "python3:",
    "node:",
    "ruby:",
    "perl:",
    "sh -c:",
    "bash -c:",
)
# Bare command names that, with a wildcard, allow arbitrary execution (covers
# "python:*"/"exec *" style patterns). The bare check matches an exact body, a
# "<name> ..." prefix, or a "<name>:..." prefix, so these also cover the "exec"
# case that a trailing-space/colon prefix entry cannot (the prefix helper appends
# its own separator, which would require a double space to match).
# Default/glob branch: the shared interpreter names plus ``exec`` (checked here
# only -- see the note on _ARBITRARY_EXEC_INTERPRETERS).
_ARBITRARY_EXEC_BARE: Tuple[str, ...] = _ARBITRARY_EXEC_INTERPRETERS + ("exec",)


def _is_arbitrary_exec(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True when the allow pattern permits arbitrary code execution.

    Args:
        tool: Tool name (checked to avoid false positives on file-path tools).
        body: Pattern body (tool wrapper stripped, type prefix stripped).
        ptype: Detected pattern type.

    Returns:
        True when the pattern is an arbitrary-execution allow.
    """
    # Only flag command tools (Bash and variants); file-path tools can't exec
    if tool in ("Read", "Write", "Edit"):
        return False

    body_stripped = body.strip()
    body_lower = body_stripped.lower()

    if ptype == PatternType.REGEX:
        # Conservative substring heuristic: if a dangerous interpreter/eval token
        # appears anywhere in the regex body, treat the rule as arbitrary-exec.
        # Uses the shared interpreter names (bare, so an anchored body like
        # "^node:.*" is caught the same way "^python:.*" is) plus the eval forms.
        # "python" subsumes "python3"; "exec" is deliberately NOT a substring token
        # because it appears in negative lookaheads that forbid exec (e.g.
        # "(?!.*exec)") -- the DEFAULT branch checks it precisely. False positives
        # are acceptable here; false negatives are not.
        return _regex_body_matches_any(
            body_lower,
            _ARBITRARY_EXEC_INTERPRETERS + ("uv run python", "sh -c", "bash -c"),
        )
    else:
        # DEFAULT or GLOB: check for literal prefix
        if _body_fnmatch_matches_any(body_lower, _ARBITRARY_EXEC_PREFIXES):
            return True
        # Also catch bare "python:*" / "python3:*" style (body is "python" exactly)
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
    """
    Return True when the allow pattern could permit a destructive command.

    Args:
        tool: Tool name.
        body: Pattern body.
        ptype: Pattern type.

    Returns:
        True when the pattern matches a destructive command category.
    """
    if tool in ("Read", "Write", "Edit"):
        return False
    body_lower = body.strip().lower()

    if ptype == PatternType.REGEX:
        return _regex_body_matches_any(
            body_lower,
            ("rm -rf", "rm -fr", "shred", "dd if=", "mkfs", "wipefs"),
        )
    return _body_fnmatch_matches_any(body_lower, _DESTRUCTIVE_PREFIXES)


# 3. Secrets exposure
# This table is intentionally limited to specific file-path indicators for
# well-known secret files.  Generic substrings like "secret", "password", or
# "credentials" are omitted because they are too noise-prone (they would flag
# any rule whose pattern merely contains those words in a comment or path
# segment).  Specific additional indicators -- e.g. AWS credential paths --
# can be added deliberately here when the false-positive risk is acceptable.
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

    Args:
        tool: Tool name.
        body: Pattern body.
        ptype: Pattern type.

    Returns:
        True when the pattern could expose credentials or secret files.
    """
    body_lower = body.strip().lower()

    if ptype == PatternType.REGEX:
        return _regex_body_matches_any(body_lower, _SECRET_PATTERNS)

    # For DEFAULT/GLOB: check if body contains any secret indicator
    for indicator in _SECRET_PATTERNS:
        if indicator in body_lower:
            return True
    return False


# 4. Unanchored regex allow
def _is_unanchored_regex(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True when the pattern is a ``[regex]`` allow without a ``^`` anchor.

    ``re.search`` is unanchored -- it matches anywhere in the string.  A regex
    allow like ``rm`` would match a command that merely contains the string ``rm``
    anywhere (including ``echo "nope no rm here"``).  Without ``^`` the rule is
    broader than it may look.

    Args:
        tool: Tool name (not used by this predicate, present for signature compat).
        body: Pattern body.
        ptype: Pattern type.

    Returns:
        True when the pattern type is REGEX and the body does not start with ``^``.
    """
    if ptype != PatternType.REGEX:
        return False
    return not body.strip().startswith("^")


# 5. Blanket allow outside takeover (checked separately in danger() due to takeover state)
def _is_blanket_allow(tool: str, body: str, ptype: PatternType) -> bool:
    """
    Return True when the pattern body is effectively a blanket allow (matches everything).

    Args:
        tool: Tool name.
        body: Pattern body.
        ptype: Pattern type.

    Returns:
        True when body is ``*`` (default wildcard) or the regex ``.*``/``.+``/empty anchor.
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
    # Blanket-allow-outside-takeover is handled separately in danger() because
    # it needs the effective takeover state to decide whether to fire.
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def danger(
    config: Configuration,
    takeover: Optional[TakeoverConfig] = None,
) -> List[DangerFinding]:
    """
    Audit ``config`` for static risk findings and return ranked results.

    Scans all toolguard allow rules across all layers and tools, applying
    each detector in :data:`_DETECTORS`.  Results are sorted by severity
    descending (CRITICAL first) then by tool name and pattern for stable output.

    Takeover-mode awareness
    -----------------------
    When ``takeover`` is provided and ``takeover.enabled`` is ``True``:

    - Blanket allows (``Bash(*)``, ``Read(*)``, etc.) in NATIVE layers that
      appear in the effective ignored set are NOT flagged (they are intentional
      setup artefacts for takeover mode).
    - The blanket-allow-outside-takeover detector fires for native blanket
      allows NOT in the ignored set.

    When ``takeover`` is ``None``, the effective state is read from ``config``.

    Args:
        config: The resolved configuration.
        takeover: Pre-resolved takeover configuration (optional; read from
            ``config`` when not provided).

    Returns:
        Sorted list of :class:`DangerFinding` records, highest severity first.
        Empty when no dangerous patterns are detected.
    """
    if takeover is None:
        takeover = config.takeover_mode()

    findings: List[DangerFinding] = []

    # Pre-compute the ignored-allow set (extracted form) for blanket-allow check
    ignored_extracted = takeover.normalized_ignored_patterns()

    # Iterate over all tools mentioned in any layer (via shared helper)
    for tool in discover_tools(config):
        findings.extend(_audit_tool(config, tool, takeover, ignored_extracted))

    # Sort: severity descending, then tool, then pattern
    findings.sort(key=lambda f: (-f.severity.value, f.tool, f.pattern))
    return findings


def _audit_tool(
    config: Configuration,
    tool: str,
    takeover: TakeoverConfig,
    ignored_extracted: frozenset,
) -> List[DangerFinding]:
    """
    Run all detectors over the allow rules for a single tool.

    Args:
        config: The resolved configuration.
        tool: Tool name to audit.
        takeover: Resolved takeover config.
        ignored_extracted: Pre-computed ignored-allow patterns in extracted form.

    Returns:
        Findings for this tool.
    """
    findings: List[DangerFinding] = []
    layer_rules = per_layer_rules(config, tool)

    for lr in layer_rules:
        is_native = lr.provenance.source_type == "claude"

        for pattern in lr.allow:
            ptype, body = parse_pattern(pattern, extended_syntax=True)

            # Skip native blanket allows that are intentionally in the ignored set
            # when takeover is ON (they are setup artefacts, not real risks)
            if neutralized_by_takeover(pattern, is_native, takeover):
                continue

            # Blanket allows are reported by the dedicated blanket-allow detector
            # in the second loop below. Skip them here so a blanket pattern (e.g.
            # [regex].*) does not ALSO match a content detector and double-report
            # the same pattern (review finding M1).
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
                    break  # Only one finding per pattern per detector pass; don't stack

        # Blanket-allow-outside-takeover: fire only for native layers when
        # takeover is OFF, or for any layer that has a true blanket allow outside
        # the effective ignored set
        for pattern in lr.allow:
            ptype, body = parse_pattern(pattern, extended_syntax=True)
            if _is_blanket_allow(tool, body, ptype):
                # If takeover is ON and this is in the ignored set, it's fine
                if neutralized_by_takeover(pattern, is_native, takeover):
                    continue
                # Flag: blanket allow that is live (not suppressed by takeover)
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
