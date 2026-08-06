"""
Side-effect-free decision primitive for toolguard tooling.

This module provides a single public function :func:`decide` that evaluates a
command or file path against a :class:`~toolguard.config.Configuration` and
returns the permission decision -- WITHOUT writing any logs, without triggering
any process exits, and without touching any global state.

Fidelity guarantee
------------------
The result of :func:`decide` EXACTLY matches what the live hook produces for the
same input because both delegate to the SAME shared resolver layer
(:mod:`toolguard.resolve`).  There is no separate copy of the orchestration
logic here -- this module is pure delegation + tuple-to-:class:`Decision`
adaptation.

Side-effect isolation
---------------------
All logging, stdin/stdout, and ``sys.exit`` live in :func:`toolguard.hook.main`.
The resolvers in :mod:`toolguard.resolve` are already side-effect-free; this
module simply routes calls to them and wraps the result in a stable
:class:`Decision` dataclass.

DELEGATION POINTS:
- :func:`toolguard.resolve.resolve_bash_permission_detailed`
  -- pure compound Bash resolver
- :func:`toolguard.resolve.resolve_file_path_permission_detailed`
  -- pure file-path resolver
- :data:`toolguard.constants.FILE_TOOLS`
  -- canonical set of file-path tool names
"""

from dataclasses import dataclass, field
from typing import List, Optional

from toolguard.constants import FILE_TOOLS
from toolguard.resolve import (
    UnitVerdict,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)
from toolguard.config import Configuration, Provenance


@dataclass(frozen=True)
class Decision:
    """
    Result of a side-effect-free permission decision.

    This is a lightweight, stable data-transfer object analogous to
    :class:`~toolguard.config_types.RuntimeVerdict` but with a richer
    ``verdict`` field that distinguishes ``ask`` from ``allow`` and ``deny``,
    and an explicit ``tool`` and ``target`` so callers can log or compare
    without re-extracting them. This is the TOOLING altitude in the R1
    scoping trace's three-altitude picture (unit / runtime / tooling) --
    unifying it with ``RuntimeVerdict`` is deferred to TOO-45 R6.

    Attributes:
        tool: The tool name (``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``).
        target: The command string (Bash) or file path (file tools).
        verdict: ``'allow'``, ``'ask'``, or ``'deny'``.
        reason: Human-readable explanation matching what the hook would log.
        provenance: The winning rule's provenance (config source), or ``None``
            when no rule matched (default deny / fail-closed).  For a compound
            Bash command this is the provenance of the sub-command that DECIDED
            the verdict -- sourced directly from
            :attr:`~toolguard.config_types.RuntimeVerdict.provenance` (TOO-45
            R1e finishing pass), the same ``matched_rule``-consistent
            attribution :func:`~toolguard.resolve._deciding_sub_match`
            computes: first deny for a deny, first ask for an ask, else the
            SOLE genuine (non-escape-hatch) rule match among the allowed
            sub-commands, or ``None`` when there is no single decider to
            attribute. Previously re-derived independently here as "the first
            sub-command's provenance", which silently returned an escape-hatch
            leaf's ``None`` whenever it happened to extract first, even though
            a later sub-command had a real, attributable match (e.g.
            ``diff <(cat a) <(cat b) && ls -la`` returned ``None`` instead of
            the ``ls -la`` leaf's provenance). For file-path tools it is the
            provenance of the matched rule (fixing a regression where normal
            allows previously returned ``None``).
        sub_matches: For Bash commands: one
            :class:`~toolguard.resolve.UnitVerdict` per extracted sub-command
            (in order), carrying per-sub-command decision, matched rule, and
            provenance.  ``None`` for file-path tools.
        additional_context: The winning rule's ``additionalContext`` enrichment
            (TOO-19 Phase 1), or ``None`` when the matched rule (or fail-closed
            default) carried none. Sourced from
            :attr:`~toolguard.config_types.RuntimeVerdict.additional_context`
            without any re-derivation here. Declared LAST so existing
            positional construction of ``Decision`` stays valid.
        matched_rule: The winning rule's pattern text (wrapper-free), or
            ``None`` for a hard-deny match or a fail-closed/fallback default
            (no rule matched). Sourced from
            :attr:`~toolguard.config_types.RuntimeVerdict.matched_rule`
            (TOO-45 D1a review debt item E), the same way
            ``additional_context`` is -- not re-derived from *reason*.
            Declared LAST for the same positional-construction reason as
            ``additional_context``.
    """

    tool: str
    target: str
    verdict: str
    reason: str
    provenance: Optional[Provenance]
    sub_matches: Optional[List[UnitVerdict]] = field(default=None, compare=False)
    additional_context: Optional[str] = None
    matched_rule: Optional[str] = None


def decide(
    config: Configuration,
    tool: str,
    target: str,
    extended_syntax: bool = True,
) -> Decision:
    """
    Evaluate a permission decision for ``tool`` + ``target`` without side effects.

    This is the single entry point for the replay harness and any other tooling
    that needs to know what the hook *would* decide for a given command or path
    under a given configuration, without actually running the hook (and without
    any log writes or process exits).

    Routing
    -------
    - ``tool`` in ``FILE_TOOLS`` (``'Read'``, ``'Write'``, ``'Edit'``):
      file-path matching with project-root anchoring, hard-deny first.
    - All other tools (``'Bash'``, MCP terminals, etc.): compound Bash matching
      with hard-deny first per sub-command.

    Fail-closed behaviour
    ---------------------
    When the configuration has no allow patterns configured for ``tool``, the
    decision is ``deny`` with an appropriate reason -- matching the hook's
    fail-closed behaviour for unconfigured tools.  The governed-tools list is
    NOT checked here: the caller (hook) governs that; the decision primitive
    evaluates purely against the configured patterns.

    Args:
        config: The resolved configuration hierarchy to evaluate against.
        tool: Tool name (e.g. ``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``).
        target: The command string (for Bash/command tools) or absolute file path
            (for file-path tools).
        extended_syntax: Whether to honour ``[regex]``/``[glob]``/``[native]``
            prefixes in permission patterns.  Defaults to ``True``.

    Returns:
        A :class:`Decision` with the ``verdict``, ``reason``, ``provenance``, and
        ``additional_context`` of the winning rule (or ``None`` provenance /
        ``additional_context`` for a default deny).
    """
    if tool in FILE_TOOLS:
        return _decide_file_path(config, tool, target, extended_syntax)
    return _decide_bash(config, tool, target, extended_syntax)


# ---------------------------------------------------------------------------
# Private adapters -- pure delegation to toolguard.resolve, no reimplementation
# ---------------------------------------------------------------------------


def _decide_bash(
    config: Configuration,
    tool: str,
    command: str,
    extended_syntax: bool,
) -> Decision:
    """
    Adapt a Bash (or command-tool) decision from :mod:`toolguard.resolve` to a
    :class:`Decision` dataclass.

    Delegates entirely to
    :func:`toolguard.resolve.resolve_bash_permission_detailed`.  The hook always
    resolves command-tools against the ``'Bash'`` permission set (even for MCP
    terminal tools); this adapter mirrors that routing.

    Provenance selection for compound commands
    ------------------------------------------
    ``Decision.provenance`` is ``result.provenance``
    (:attr:`~toolguard.config_types.RuntimeVerdict.provenance`) directly, not
    re-derived here (TOO-45 R1e finishing pass) -- ``resolve_bash_permission_detailed``
    already computes exactly this value via
    :func:`~toolguard.resolve._deciding_sub_match`: the FIRST sub-command with
    a ``'deny'`` decision when the verdict is ``'deny'``; the FIRST with an
    ``'ask'`` decision when the verdict is ``'ask'``; otherwise the SOLE
    genuine (non-escape-hatch) match among the allowed sub-commands, or
    ``None`` when there is no single decider. A prior version of this function
    re-derived the allow case independently as "the first sub-command's
    provenance", which returned ``None`` whenever an escape-hatch entry
    (an :class:`~toolguard.parser.multiline.UndecidableSegment`, or an
    ask-floor leaf that allowed via the floor) happened to extract before a
    later sub-command's genuine, attributable match -- silently discarding
    real provenance ``matched_rule`` (sourced the same way) never lost.

    This single-value provenance is a convenient summary for callers; the full
    per-sub-command detail is available in ``Decision.sub_matches``.

    Args:
        config: The resolved configuration.
        tool: Tool name (used as-is in the returned :class:`Decision`; the
            resolver internally always evaluates against the Bash rule set).
        command: The bash command line (may be compound).
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        A :class:`Decision` for the compound command, with ``sub_matches``
        populated and ``provenance`` pointing at the deciding sub-command.
    """
    hd_deny, hd_allow = config.hard_deny("Bash")
    result = resolve_bash_permission_detailed(
        command, config, extended_syntax, hd_deny, hd_allow
    )
    sub_matches = result.sub_matches

    return Decision(
        tool=tool,
        target=command,
        verdict=result.decision,
        reason=result.reason,
        provenance=result.provenance,
        sub_matches=sub_matches if sub_matches else None,
        additional_context=result.additional_context,
        matched_rule=result.matched_rule,
    )


def _decide_file_path(
    config: Configuration,
    tool: str,
    file_path: str,
    extended_syntax: bool,
) -> Decision:
    """
    Adapt a file-path tool decision from :mod:`toolguard.resolve` to a
    :class:`Decision` dataclass.

    Delegates entirely to
    :func:`toolguard.resolve.resolve_file_path_permission_detailed`.

    Regression fix
    --------------
    Previously ``provenance`` was set from ``override.winning_provenance`` only,
    which meant normal (non-conflict) allows returned ``None``.  It is now taken
    from :attr:`~toolguard.config_types.RuntimeVerdict.provenance`, which the
    resolver populates for all matched rules.

    Args:
        config: The resolved configuration.
        tool: Tool name (``'Read'``, ``'Write'``, or ``'Edit'``).
        file_path: The absolute (or ``~``-prefixed) file path to evaluate.
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        A :class:`Decision` for the file path, with ``provenance`` set to the
        winning rule's origin (``None`` only for hard-deny or fail-closed deny).
    """
    result = resolve_file_path_permission_detailed(
        tool, file_path, config, extended_syntax
    )
    return Decision(
        tool=tool,
        target=file_path,
        verdict=result.decision,
        reason=result.reason,
        provenance=result.provenance,
        sub_matches=None,
        additional_context=result.additional_context,
        matched_rule=result.matched_rule,
    )
