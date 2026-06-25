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
- :data:`toolguard.hook.FILE_PATH_TOOLS`
  -- canonical set of file-path tool names
"""

from dataclasses import dataclass, field
from typing import List, Optional

from toolguard.hook import FILE_PATH_TOOLS
from toolguard.resolve import (
    SubMatch,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)
from toolguard.config import Configuration, Provenance


@dataclass(frozen=True)
class Decision:
    """
    Result of a side-effect-free permission decision.

    This is a lightweight, stable data-transfer object analogous to
    :class:`~toolguard.config.ResolvedDecision` but with a richer ``verdict``
    field that distinguishes ``ask`` from ``allow`` and ``deny``, and an explicit
    ``tool`` and ``target`` so callers can log or compare without re-extracting
    them.

    Attributes:
        tool: The tool name (``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``).
        target: The command string (Bash) or file path (file tools).
        verdict: ``'allow'``, ``'ask'``, or ``'deny'``.
        reason: Human-readable explanation matching what the hook would log.
        provenance: The winning rule's provenance (config source), or ``None``
            when no rule matched (default deny / fail-closed).  For a compound
            Bash command this is the provenance of the sub-command that DECIDED
            the verdict (first deny for a deny, first ask for an ask, else the
            first allow's provenance).  For file-path tools it is the provenance
            of the matched rule (fixing a regression where normal allows
            previously returned ``None``).
        sub_matches: For Bash commands: one :class:`~toolguard.resolve.SubMatch`
            per extracted sub-command (in order), carrying per-sub-command
            decision, matched rule, and provenance.  ``None`` for file-path tools.
    """

    tool: str
    target: str
    verdict: str
    reason: str
    provenance: Optional[Provenance]
    sub_matches: Optional[List[SubMatch]] = field(default=None, compare=False)


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
    - ``tool`` in ``FILE_PATH_TOOLS`` (``'Read'``, ``'Write'``, ``'Edit'``):
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
        A :class:`Decision` with the ``verdict``, ``reason``, and ``provenance``
        of the winning rule (or ``None`` provenance for a default deny).
    """
    if tool in FILE_PATH_TOOLS:
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
    ``Decision.provenance`` is set to the provenance of the sub-command that
    DECIDED the compound verdict:

    - If the overall verdict is ``'deny'``: the FIRST sub-command with a
      ``'deny'`` decision.
    - If the overall verdict is ``'ask'``: the FIRST sub-command with an
      ``'ask'`` decision.
    - Otherwise (``'allow'``): the FIRST sub-command's provenance (or ``None``
      when no sub-commands were extracted).

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

    # Determine the deciding sub-command's provenance.
    provenance: Optional[Provenance] = None
    if result.decision in ("deny", "ask"):
        # First sub whose decision matches the compound verdict decided it.
        for sm in sub_matches:
            if sm.decision == result.decision:
                provenance = sm.provenance
                break
    elif sub_matches:
        # Allow: use the first sub-command's provenance.
        provenance = sub_matches[0].provenance

    return Decision(
        tool=tool,
        target=command,
        verdict=result.decision,
        reason=result.reason,
        provenance=provenance,
        sub_matches=sub_matches if sub_matches else None,
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
    from :attr:`~toolguard.resolve.FileResolution.provenance`, which the resolver
    already populates from ``ResolvedDecision.provenance`` for all matched rules.

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
    )
