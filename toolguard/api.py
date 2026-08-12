"""
Public decision interface for toolguard.

:func:`decide` answers what toolguard would decide for a tool + target,
without side effects (no log writes, no process exit) -- the entry point
both the live hook's ``--eval`` path and tooling code (replay, mining,
audits) use.

This module is its own architectural layer, directly above the
decision-engine modules (``permissions``, ``compound``, ``resolve``, ...)
and below both ``runtime`` and ``tooling`` (the ``"api"`` layer in
``.pyscn.toml``'s ``[[architecture.layers]]`` blocks), so either side can
import it without an upward dependency on the other.

Its public surface is exactly one verb, deliberately not a general-purpose
facade over the config or engine layers: most of what tooling and runtime
actually reach for is the *config* model (``Configuration``, ``RuleEntry``,
``rule_sort``'s TOML helpers), not the decision engine, and a facade
re-exporting all of that would be a list of whatever each importer happens
to use rather than a designed interface. ``decide`` is the one thing every
actual consumer asks for.

:func:`decide` delegates to :mod:`toolguard.resolve` -- the same resolver
functions the live hook's own PreToolUse path calls directly -- so there is
no separate copy of the decision logic here.
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
    Evaluate a permission decision for ``tool`` + ``target``, without side effects.

    Routing: ``tool`` in ``FILE_TOOLS`` (``'Read'``, ``'Write'``, ``'Edit'``)
    uses file-path matching with project-root anchoring, hard-deny first;
    every other tool (``'Bash'``, MCP terminals, etc.) uses compound Bash
    matching, hard-deny first per sub-command. The governed-tools list is
    not checked here -- that is the caller's job; this evaluates purely
    against the configured patterns.

    Args:
        config: The resolved configuration hierarchy to evaluate against.
        tool: Tool name (e.g. ``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``).
        target: The command string (for Bash/command tools) or absolute file path
            (for file-path tools).
        extended_syntax: Whether to honour ``[regex]``/``[glob]``/``[native]``
            prefixes in permission patterns. Defaults to ``True``.

    Returns:
        A :class:`~toolguard.config_types.RuntimeVerdict` (see that class's
        docstring for field meanings), with ``tool``/``target`` echoing the
        arguments above.
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

    :func:`~toolguard.resolve.resolve_bash_permission_detailed` always
    evaluates against the ``'Bash'`` permission set and returns
    ``tool='Bash'`` on its verdict regardless of the actual invoking tool
    name. When the caller's ``tool`` differs (e.g. an MCP terminal tool
    routed through the Bash rule set), it is restored on the returned
    verdict.

    Args:
        config: The resolved configuration.
        tool: The invoking tool's own name.
        command: The bash command line (may be compound).
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        The :class:`~toolguard.config_types.RuntimeVerdict` from
        :func:`~toolguard.resolve.resolve_bash_permission_detailed`.
    """
    hd_deny, hd_allow = config.hard_deny("Bash")
    result = resolve_bash_permission_detailed(
        command, config, extended_syntax, hd_deny, hd_allow
    )
    if tool != result.tool:
        return dataclasses.replace(result, tool=tool)
    return result
