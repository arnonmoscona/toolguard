"""
Public decision interface for toolguard -- the ``api`` layer.

This module is the single entry point both downstream layers reach for a
permission decision: :func:`decide` is what the live hook's ``--eval`` path
calls (:mod:`toolguard.hook`, the runtime layer) and what every tooling
consumer -- the replay harness, the corpus builder, ``self_permission``,
``uninstall_readiness``, the config-migration mining pass, the takeover-audit
consolidation step, and :mod:`toolguard.testing.sandbox` -- calls directly.

Why this module exists (TOO-45 R6-S2)
--------------------------------------
Before this stage, :func:`decide` lived in :mod:`toolguard.tools.decision`,
in the ``tooling`` layer. The live hook needed the same function for
``--eval``, but ``runtime -> tooling`` is an upward import under this
project's declared layering (``foundation < config < engine < api < runtime
< tooling < support`` -- see ``.pyscn.toml``'s ``[[architecture.layers]]``
blocks), so ``hook.py`` carried a function-local import and a comment
explaining why hoisting it to module level would not fix anything (the
violation is the DEPENDENCY, not its placement -- TOO-45 R6 reassessment,
section 4, DEMONSTRATED BY EXECUTION). The only change that clears the
violation is moving :func:`decide` to a layer both callers can legally
import from downward. ``api`` sits directly above ``engine`` for exactly
that reason: it is allowed to import ``engine``/``config``/``foundation``,
and both ``runtime`` and ``tooling`` are allowed to import it.

This is deliberately NOT a general-purpose facade over the config or engine
layers -- an earlier probe (TOO-45 R6 reassessment, section 5b, "S4") found
that 74% of what tooling+runtime actually reach into is the *config* model
(``Configuration``, ``RuleEntry``, ``rule_sort``'s TOML helpers, etc.), not
the decision engine, and that a facade re-exporting all of it would be "a
list of what 21 modules happen to import" rather than a designed interface.
This module's public surface is exactly one verb -- "decide" -- because that
is the one thing every actual consumer, runtime and tooling alike, asks for.

Fidelity guarantee
-------------------
The result of :func:`decide` EXACTLY matches what the live hook produces for
the same input because both delegate to the SAME shared resolver layer
(:mod:`toolguard.resolve`). There is no separate copy of the orchestration
logic here -- this module is pure delegation, returning the resolver's own
:class:`~toolguard.config_types.RuntimeVerdict` unmodified (Bash) or with
only its ``tool`` field overridden (see :func:`_decide_bash`'s docstring for
why).

Side-effect isolation
-----------------------
All logging, stdin/stdout, and ``sys.exit`` live in :func:`toolguard.hook.main`.
The resolvers in :mod:`toolguard.resolve` are already side-effect-free (with
the caveat documented on that module -- matching reads live filesystem state
via :mod:`toolguard.normalization`); this module simply routes calls to them.

DELEGATION POINTS:
- :func:`toolguard.resolve.resolve_bash_permission_detailed`
  -- pure compound Bash resolver
- :func:`toolguard.resolve.resolve_file_path_permission_detailed`
  -- pure file-path resolver
- :data:`toolguard.constants.FILE_TOOLS`
  -- canonical set of file-path tool names
"""

import dataclasses

from toolguard.config import Configuration
from toolguard.config_types import RuntimeVerdict
from toolguard.constants import FILE_TOOLS
from toolguard.resolve import (
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)


def decide(
    config: Configuration,
    tool: str,
    target: str,
    extended_syntax: bool = True,
) -> RuntimeVerdict:
    """
    Evaluate a permission decision for ``tool`` + ``target`` without side effects.

    This is the single entry point for the live hook's ``--eval`` mode, the
    replay harness, and any other caller that needs to know what the hook
    *would* decide for a given command or path under a given configuration,
    without actually running the hook (and without any log writes or process
    exits).

    Routing
    -------
    - ``tool`` in ``FILE_TOOLS`` (``'Read'``, ``'Write'``, ``'Edit'``):
      file-path matching with project-root anchoring, hard-deny first.
    - All other tools (``'Bash'``, MCP terminals, etc.): compound Bash matching
      with hard-deny first per sub-command.

    Fail-closed behaviour
    -----------------------
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
        A :class:`~toolguard.config_types.RuntimeVerdict` with the ``decision``,
        ``reason``, ``provenance``, ``matched_rule``, and ``additional_context``
        of the winning rule (or the fail-closed default for no match), plus
        ``tool``/``target`` echoing the arguments above.
    """
    if tool in FILE_TOOLS:
        return resolve_file_path_permission_detailed(
            tool, target, config, extended_syntax
        )
    return _decide_bash(config, tool, target, extended_syntax)


def _decide_bash(
    config: Configuration,
    tool: str,
    command: str,
    extended_syntax: bool,
) -> RuntimeVerdict:
    """
    Resolve a Bash (or command-tool) decision via :mod:`toolguard.resolve`.

    Delegates entirely to
    :func:`toolguard.resolve.resolve_bash_permission_detailed`, which always
    evaluates against the ``'Bash'`` permission set (even for MCP terminal
    tools) and, as of TOO-45 R1d, sets its own returned
    :class:`~toolguard.config_types.RuntimeVerdict`'s ``tool`` field to the
    literal string ``'Bash'`` regardless of the actual invoking tool name.

    ``tool`` override
    ------------------
    A caller-supplied ``tool`` that differs from the resolver's hardcoded
    ``'Bash'`` is preserved on the returned verdict (so an MCP terminal tool
    routed through the Bash rule set is still reported under its own name,
    e.g. for log attribution), via :func:`dataclasses.replace` -- no other
    field changes. In every actual call site in this codebase ``tool`` is
    already the literal string ``'Bash'``, so this override is a no-op in
    practice, but the documented contract for a hypothetical MCP-terminal
    caller is exact rather than silently narrowed.

    Args:
        config: The resolved configuration.
        tool: Tool name (used to override the resolver's ``'Bash'`` default
            when they differ; see above).
        command: The bash command line (may be compound).
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        The :class:`~toolguard.config_types.RuntimeVerdict` returned by
        :func:`~toolguard.resolve.resolve_bash_permission_detailed`, with
        ``tool`` set to the caller's own ``tool`` argument.
    """
    hd_deny, hd_allow = config.hard_deny("Bash")
    result = resolve_bash_permission_detailed(
        command, config, extended_syntax, hd_deny, hd_allow
    )
    if tool != result.tool:
        return dataclasses.replace(result, tool=tool)
    return result
