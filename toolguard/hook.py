#!/usr/bin/env python3
"""
Toolguard Pre-Tool-Use Hook for Claude Code.

This hook validates bash commands and file operations against allow/deny patterns.

Supported tools:
- Command tools (Bash, MCP terminals): Uses compound command parsing
- File path tools (Read, Write, Edit): Uses GLOB pattern matching

Input: JSON via stdin with tool information
Output: JSON via stdout with permission decision

Exit code: Always 0 (errors communicated via JSON output)
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from toolguard.api import decide
from toolguard.auto_migrate import run_auto_migration
from toolguard.compound import (
    FALLBACK_ALLOW_PLACEHOLDER,
    FALLBACK_DENY_PLACEHOLDER,
    fallback_kind_for_reason,
)
from toolguard.config import load_configuration
from toolguard.config_divergence import check_and_warn_divergence
from toolguard.env_config import get_env_config
from toolguard.error_log import log_conflict, log_crash, log_error, log_warning
from toolguard.log_writer import LogRecord, log_command, log_discovery
from toolguard.resolve import (
    RuntimeVerdict,
    UnitVerdict,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)
from toolguard.constants import FILE_TOOLS
from toolguard.session_warnings import issue_takeover_warning
from toolguard.subagent import identify_current_agent

# Tools that operate on file paths (use GLOB matching). Alias of the shared
# foundation constant. TOO-45 R5a removed the production importer
# (toolguard.tools.decision now takes FILE_TOOLS from toolguard.constants
# directly, as its sibling tooling modules already did, which broke the
# hook <-> tools.decision cycle). Only tests import this name now; prefer
# toolguard.constants.FILE_TOOLS in new code.
FILE_PATH_TOOLS = FILE_TOOLS

# Tools that execute commands (use compound command parsing)
COMMAND_TOOLS = {
    "Bash",
    "mcp__jetbrains__execute_terminal_command",
    "mcp__local-tools__checked_bash",
}

# Module-level flags to ensure checks run only once per session
_validation_done = False
_divergence_check_done = False
_takeover_conflict_logged = False


def _run_startup_validation(
    env_config: Dict[str, Any], start_dir: str = None, config=None
) -> None:
    """
    Run configuration validation once at startup.

    Obtains the resolved :class:`~toolguard.config.Configuration` and renders the
    structured issues it reports. The hook performs NO file discovery, parsing,
    or format branching here -- those concerns live entirely in the config
    module. The hook only renders/logs the returned issues. Issues surfaced:
    - Both TOML and JSON config files existing at the same level
    - Unsupported tools in permissions
    - Ungoverned tools in permissions

    Args:
        env_config: Environment configuration dict with log_dir
        start_dir: Directory to start searching for project root from. Defaults to cwd.
        config: Pre-loaded Configuration to reuse. When None, one is loaded via
            ``load_configuration(start_dir)`` so this function remains usable on
            its own.
    """
    global _validation_done
    if _validation_done:
        return
    _validation_done = True

    if config is None:
        config = load_configuration(start_dir)

    # Get log directory from env config
    log_dir = env_config.get("log_dir")
    if not log_dir:
        project_root = config.project_root
        if project_root is None:
            return  # Can't log without log dir
        log_dir = project_root / "logs"

    # The config module detects content-level issues and returns them; the hook
    # only decides where to log. No files are opened or parsed here. Route each
    # issue to the stream matching its severity so the Phase 4 stream separation
    # holds: 'error'-level issues to the error stream, everything else (today
    # only 'warning') to the warning stream.
    for issue in config.validation_issues():
        if issue.level == "error":
            log_error(issue.message, issue.corrective_steps, log_dir)
        else:
            log_warning(issue.message, issue.corrective_steps, log_dir)


class EmptyStdinError(ValueError):
    """
    Raised when stdin was read but contained no data.

    A DISTINCT subclass, not a bare ``ValueError``, so ``main()`` can treat it
    like the TTY guard (a stray manual/probing invocation -- e.g. a `toolguard
    --version` an agent ran to check the installed version, an unrecognized
    flag silently discarded by argparse, or any other non-hook invocation)
    rather than an unexpected internal error worth a crash report. A real
    install hit this twice: the crash report it produced was a red herring
    that looked like a hook defect but was really just a manual probe.
    """


def parse_hook_input() -> Dict[str, Any]:
    """
    Parse hook input from stdin.

    Expected JSON format from Claude Code:
    {
        "session_id": "abc123",
        "transcript_path": "/path/to/transcript.jsonl",
        "cwd": "/current/working/dir",
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "git status"
        },
        "tool_use_id": "toolu_01ABC123..."
    }

    Returns:
        Parsed JSON data as dictionary

    Raises:
        json.JSONDecodeError: If input is not valid JSON
        EmptyStdinError: If stdin was read but contained no data.
        ValueError: If required fields are missing.
    """
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            raise EmptyStdinError("Empty input from stdin")

        data = json.loads(input_data)

        # Validate required fields
        required_fields = ["tool_name", "tool_input", "hook_event_name"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        return data

    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON from stdin: {e.msg}", e.doc, e.pos)


def create_hook_output(verdict: RuntimeVerdict) -> Dict[str, Any]:
    """
    Create hook output in the format expected by Claude Code.

    TOO-45 R1d: takes the whole :class:`~toolguard.config_types.RuntimeVerdict`
    instead of a bare ``(decision, reason, additional_context)`` triple, so
    every call site (including the error/guard paths that build a synthetic
    verdict inline, e.g. ``RuntimeVerdict(decision="deny", reason=...)``) goes
    through the same, single construction shape. Only ``decision``,
    ``reason``, and ``additional_context`` are consumed here -- the hook's
    JSON response is a projection of the verdict, not the whole of it (see
    the TOO-45 R1 scoping trace's Q2: this projection is faithful across the
    entire verdict corpus, unlike the audit-log path).

    Args:
        verdict: The resolved permission verdict. ``verdict.decision`` becomes
            ``permissionDecision``; ``verdict.reason`` becomes
            ``permissionDecisionReason``; ``verdict.additional_context`` (see
            below) becomes ``additionalContext``. Every OTHER field
            (``provenance``, ``matched_rule``, ``sub_matches``, ``overrides``,
            ``fallback_warning``, ``tool``, ``target``) is intentionally
            ignored here -- those drive the audit log, not the hook's JSON
            response to Claude.

    Returns:
        Dictionary formatted for JSON output to Claude Code. The
        ``"additionalContext"`` key is present inside ``hookSpecificOutput``
        ONLY when ``verdict.additional_context`` is a non-empty string --
        omitted entirely (not set to ``null``) otherwise, so existing
        consumers that don't know about the field see no change in shape.
    """
    output: Dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": verdict.decision,
            "permissionDecisionReason": verdict.reason,
        }
    }
    if verdict.additional_context:
        output["hookSpecificOutput"]["additionalContext"] = verdict.additional_context
    return output


def _build_crash_context(local_vars: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a small, readable snapshot of in-flight hook state for :func:`log_crash`.

    ``main()``'s ``except`` clauses can fire before ``hook_data``/``tool_name``/
    ``tool_input``/``cwd`` are ever assigned (e.g. a parse failure on stdin
    itself), so this only includes whichever of those keys are actually present
    in *local_vars* -- passing ``locals()`` from the catch site -- rather than
    referencing them directly and risking a ``NameError`` from inside error
    handling.

    Args:
        local_vars: The calling frame's ``locals()``, taken at the except site.

    Returns:
        A dict with whichever of ``tool_name``, ``tool_input``, ``cwd`` were
        available; empty if none were.
    """
    return {
        key: local_vars[key]
        for key in ("tool_name", "tool_input", "cwd")
        if key in local_vars
    }


def load_file_path_patterns(
    tool_name: str, start_dir: str = None, config=None
) -> Tuple[List[str], List[str]]:
    """
    Load allow/deny patterns for file path tools (Read, Write, Edit).

    Thin adapter over the config abstraction: it asks the resolved
    :class:`~toolguard.config.Configuration` for the flattened, de-duplicated
    allow/deny patterns for ``tool_name`` (tool wrapper already stripped and
    takeover filtering already applied per layer). The hook itself opens no
    files and makes no format/location decisions.

    Args:
        tool_name: The tool name to load patterns for (Read, Write, or Edit)
        start_dir: Directory to start searching for project root from. Defaults to cwd.
        config: Pre-loaded Configuration to reuse. When None, one is loaded via
            ``load_configuration(start_dir)``.

    Returns:
        Tuple of (allow_patterns, deny_patterns) - path patterns without tool prefix
    """
    if config is None:
        config = load_configuration(start_dir)
    allow, deny = config.allow_deny_for(tool_name)
    return list(allow), list(deny)


def _format_conflict_message(target, override) -> str:
    """
    Compose a human/LLM-readable conflict-log message for an allow-over-deny override.

    Cites BOTH sides' provenance and the command/path that triggered the override
    (TOO-8 Phase 4). The decision still follows more-specific-wins (the allow
    won); this message merely records that a less-specific deny was overridden.

    Args:
        target: The command or file-path target that triggered the override.
        override: The :class:`~toolguard.config.ConflictOverride` describing the
            winning allow and the overridden deny.

    Returns:
        A Markdown-friendly message string.
    """
    win_origin = (
        override.winning_provenance.describe_brief()
        if override.winning_provenance
        else "unknown"
    )
    overridden_origin = (
        override.overridden_provenance.describe_brief()
        if override.overridden_provenance
        else "unknown"
    )
    return (
        f"allow-over-deny override for: {target}. "
        f"More-specific allow pattern `{override.winning_pattern}` [{win_origin}] "
        f"overrode less-specific deny pattern `{override.overridden_pattern}` [{overridden_origin}]. "
        f"Decision: allow (more-specific-wins)."
    )


def _log_conflict_override(target, override, log_dir) -> None:
    """
    Write an allow-over-deny override to the conflict log, if a log dir exists.

    Args:
        target: The command/path that triggered the override.
        override: The :class:`~toolguard.config.ConflictOverride`, or None (no-op).
        log_dir: Directory for the conflict log, or None (no-op).
    """
    if override is None or not log_dir:
        return
    corrective = (
        "Review whether the more-specific allow is intended to override the "
        "less-specific deny. If not, remove or narrow the allow, or promote the "
        "deny to [hard_deny] so it cannot be overridden."
    )
    log_conflict(_format_conflict_message(target, override), corrective, log_dir)


def _log_fallback_allow_warning(fallback_warning: bool, reason: str, log_dir) -> None:
    """
    Route an ``allow_with_warning``-fallback 'allow' decision to the WARNING
    log stream (TOO-19 code review m6; TOO-19 allow/allow_with_no_warnings
    follow-up).

    ``docs/configuration.md`` promises that ``allow_with_warning`` will
    "allow the command but log a warning" for BOTH ``no_match_fallback`` and
    ``undecidable_fallback``. Previously that promise was kept only in the
    permission-decision ``reason`` string (visible in the resolution log and
    the permission prompt) -- it never reached
    :func:`toolguard.error_log.log_warning`'s dedicated WARNING stream.

    *fallback_warning* is real data carried by the resolver result
    (:attr:`~toolguard.config_types.RuntimeVerdict.fallback_warning`) -- this
    function does not inspect *reason* itself to decide whether to log. For
    the Bash path, that structured flag is computed per-sub-command inside
    :func:`toolguard.compound.resolve_compound_permission_detailed` (TOO-19
    code review M1) -- and only a single narrow spot there still resorts to a
    marker-substring check, immediately after ``resolve_one`` returns and
    before any multi-leaf summarisation, rather than downstream on the
    already-summarised compound reason (see that function and
    :func:`toolguard.compound._combine_strictest` for why the OLD downstream
    check silently lost the warning -- and misattributed the allow to a
    fabricated rule -- for a multi-leaf all-allow compound). Either way the
    hook layer -- the thing this project's own CLAUDE.md most wants kept
    honest -- reads a plain boolean instead of parsing prose itself.
    Critically, this means the new
    ``no_match_fallback='allow'``/``'allow_with_no_warnings'`` values
    (TOO-19) -- which allow with NO warning by design -- can never
    accidentally trip this: their *fallback_warning* is always ``False``,
    regardless of what their reason text says.

    Args:
        fallback_warning: Whether *reason* should be routed to the WARNING
            stream -- ``True`` only for an 'allow' produced by
            ``allow_with_warning``.
        reason: The permission-decision reason string for an 'allow' decision.
        log_dir: Directory for the warning log, or None (no-op).
    """
    if not log_dir or not fallback_warning:
        return
    log_warning(
        reason,
        "Add an explicit allow/deny/ask rule covering this case to silence "
        "this warning.",
        log_dir,
    )


def _log_takeover_enabled_conflict(conflict, log_dir) -> None:
    """
    Record a cross-level ``takeover_mode.enabled`` disagreement (TOO-8 Phase 5).

    Writes a conflict-log entry citing every disagreeing level's value and
    provenance and noting that fail-safe OFF was applied (so native Claude
    prompts stay active). No-op when there is no conflict or no log dir.

    Args:
        conflict: The :class:`~toolguard.config.TakeoverEnabledConflict`, or None.
        log_dir: Directory for the conflict log, or None (no-op).
    """
    if conflict is None or not log_dir:
        return
    message = (
        f"{conflict.describe()}. Fail-safe applied: takeover mode is treated as "
        "DISABLED (OFF), so Claude native permission prompts stay active and "
        "nothing is silently bypassed."
    )
    corrective = (
        "takeover_mode is a single-owner policy. Set takeover_mode.enabled at "
        "exactly ONE level (typically the user level) and remove or align the "
        "conflicting settings at the other levels so they no longer disagree."
    )
    log_conflict(message, corrective, log_dir)


def _reason_suffix_or_placeholder(
    decision: str, reason: str, placeholder: str, matched_rule: Optional[str]
) -> Optional[str]:
    """
    Return *matched_rule*, or *placeholder* when *reason* names a fallback escape hatch.

    A fallback ESCAPE-HATCH reason (``undecidable_fallback``'s allow/deny
    branches) ends in the same ``": <text>"`` shape as a genuine rule-match
    reason, but the text is a truncated DISPLAY COMMAND, not a pattern --
    e.g. ``Denied by undecidable_fallback=deny (...): python -c``. Crediting
    that text to a rule would fabricate an attribution for a rule that does
    not exist in the config (TOO-19 m5 allow-side / deny-side fix).
    :func:`~toolguard.compound.fallback_kind_for_reason` is the ONE
    mechanism that tells the two shapes apart. Used by
    :func:`_log_non_allow_decision` (deny) -- the allow side no longer needs
    this reason-text classification (TOO-45 R1e:
    :class:`~toolguard.config_types.UnitVerdict.fallback_kind` now carries
    the SAME classification structurally, computed once at the point each
    unit's outcome is decided rather than re-derived from *reason* at log
    time -- see :func:`_log_allowed_command`).

    Args:
        decision: The decision *reason* accompanies (``'allow'`` or
            ``'deny'``).
        reason: Consulted ONLY for the escape-hatch classification above --
            never parsed for a value.
        placeholder: What to return when *reason* names a fallback escape
            hatch instead of a genuine rule match.
        matched_rule: The structured matched-rule value already resolved by
            the caller (``None`` when no rule matched).

    Returns:
        *placeholder* when *reason* names a fallback escape hatch, otherwise
        *matched_rule* unchanged (which may itself be ``None`` -- an absent
        record beats a false one either way).
    """
    if fallback_kind_for_reason(decision, reason) is not None:
        return placeholder
    return matched_rule


def _provenance_brief(provenance: Optional[Any]) -> Optional[str]:
    """
    Render a resolution's winning provenance for the audit log, or ``None``.

    Args:
        provenance: The resolution's winning
            :class:`~toolguard.config_types.Provenance`, or ``None`` (no
            single rule to attribute -- e.g. a hard-deny match, pooled
            across levels, or no rule matched at all).

    Returns:
        ``provenance.describe_brief()``, or ``None``.
    """
    return provenance.describe_brief() if provenance is not None else None


def _unit_matched_rule_for_log(unit: UnitVerdict) -> Optional[str]:
    """
    Derive the ``Matched Rule`` audit-log field for ONE sub-command's unit verdict.

    TOO-45 R1e: replaces the reason-text classification
    (``fallback_kind_for_reason``) with a direct read of
    :attr:`~toolguard.config_types.UnitVerdict.fallback_kind`, computed once
    where the unit's outcome is decided (see ``compound.py``/``resolve.py``)
    rather than re-derived here from *reason* text.

    Args:
        unit: The sub-command's resolved :class:`~toolguard.config_types.UnitVerdict`.

    Returns:
        :data:`~toolguard.compound.FALLBACK_ALLOW_PLACEHOLDER` when
        ``unit.fallback_kind`` names an allow-side escape hatch (``'warned'``
        or ``'silent'``), otherwise ``unit.matched_rule`` unchanged (which
        may itself be ``None`` -- an absent record beats a false one).
    """
    if unit.fallback_kind in ("warned", "silent"):
        return FALLBACK_ALLOW_PLACEHOLDER
    return unit.matched_rule


def _log_allowed_command(
    verdict: RuntimeVerdict,
    command: str,
    agent_info: str,
    env_config: dict,
    permission_mode: Optional[str] = None,
) -> None:
    """
    Log an allowed command, one entry per sub-command in ``verdict.sub_matches``.

    TOO-45 R1e: reads ``verdict.sub_matches`` (one
    :class:`~toolguard.config_types.UnitVerdict` per extracted sub-command,
    ALREADY correct for every case the reason string can hold, including an
    ask-floor leaf's escape-hatch outcome and an
    :class:`~toolguard.parser.multiline.UndecidableSegment` -- see
    ``compound.py``'s ``resolve_outer``/``record_unit`` plumbing) directly,
    instead of regex-parsing the ``"All N sub-commands allowed: [...]"``
    reason string back apart. That regex-parse (the retired
    ``_parse_compound_match_details``) kept only segments containing
    ``" -> "``, silently DROPPING the audit-log entry for any sub-command
    whose allow came from ``no_match_fallback`` (no ``" -> "`` in its raw
    reason) -- measured at 813 of 975 compound-allow corpus cases
    under-logging, 1,943 sub-commands with no audit entry at all. This also
    unifies the single-leaf and compound cases into ONE loop: a simple
    command has exactly one ``UnitVerdict`` in ``sub_matches``, so it was
    never a genuinely different case, just the OLD mechanism's inability to
    parse a non-compound reason.

    TOO-45 R1d: takes the whole *verdict* instead of its fields threaded
    through as separate parameters -- the caller (:func:`_handle_command_tool`)
    already has the verdict in scope.

    Args:
        verdict: The resolved 'allow' verdict for *command*.
            ``additional_context`` is the accumulated ``additionalContext``
            enrichment (TOO-19 Phase 1) for the WHOLE compound command; it is
            not attributable to a single sub-command (it may combine several
            sub-commands' contexts, see ``compound.py::_accumulate_contexts``),
            so it is recorded on every logged sub-command entry the same way
            the hook injects one accumulated block for the whole command.
        command: The original command string -- used ONLY as a defensive
            fallback (see below) when ``sub_matches`` is empty, which should
            not happen for a real 'allow' verdict produced by
            :func:`~toolguard.resolve.resolve_bash_permission_detailed`
            (every 'allow' path populates at least one entry).
        agent_info: Agent identification string.
        env_config: Environment configuration dict.
        permission_mode: Claude Code's own ``permission_mode`` from the hook input,
            if present -- recorded for diagnosis only, see ``log_command``.
    """
    if not verdict.sub_matches:
        # Defensive fallback for a synthetic/hand-built verdict with no
        # sub_matches (should not occur for a real resolver result) -- log
        # what is in hand without the placeholder guard, since there is no
        # per-unit fallback_kind to consult.
        log_command(
            LogRecord(
                command_str=command,
                status="executed",
                matched_rule=verdict.matched_rule,
                provenance=_provenance_brief(verdict.provenance),
                extra_info=agent_info,
                permission_mode=permission_mode,
                additional_context=verdict.additional_context,
            ),
            config=env_config,
        )
        return

    for unit in verdict.sub_matches:
        matched_rule = _unit_matched_rule_for_log(unit)
        # Never pair a real provenance with a rule that did not actually
        # decide the verdict (TOO-19 m5) -- suppressed the same way the
        # placeholder substitution above signals an escape hatch.
        provenance = (
            _provenance_brief(unit.provenance)
            if matched_rule == unit.matched_rule
            else None
        )
        log_command(
            LogRecord(
                command_str=unit.sub_command,
                status="executed",
                matched_rule=matched_rule,
                provenance=provenance,
                extra_info=agent_info,
                permission_mode=permission_mode,
                additional_context=verdict.additional_context,
            ),
            config=env_config,
        )


def _build_hook_argparser() -> argparse.ArgumentParser:
    """
    Build the argument parser for the toolguard PreToolUse hook.

    Returns:
        Configured :class:`~argparse.ArgumentParser` with a description explaining
        that this is a Claude Code hook (not meant to be run directly by humans).
    """
    parser = argparse.ArgumentParser(
        prog="toolguard",
        description=(
            "Audience: INTERNAL (Claude Code hook) -- run automatically, not a "
            "user-facing command.\n\n"
            "Claude Code PreToolUse permission hook. "
            "Reads a JSON hook event on stdin and writes a JSON permissionDecision "
            "to stdout. This is invoked automatically by Claude Code -- "
            "it is not intended to be run directly from a terminal. "
            "To smoke-test the install, pipe a sample event:\n\n"
            '  printf \'{"tool_name":"Bash","tool_input":{"command":"ls -la"},'
            '"hook_event_name":"PreToolUse"}\' | toolguard'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--eval",
        dest="eval_mode",
        action="store_true",
        default=False,
        help=(
            "READ-ONLY evaluation mode: read one hook event on stdin, resolve it "
            "against the config, and print the JSON permissionDecision -- WITHOUT "
            "logging, divergence checks, or auto-migration.  Used by the "
            "cross-project security-audit skill to probe a project's safety floor "
            "without mutating it or polluting its logs."
        ),
    )
    return parser


def _resolve_event(
    tool_name: str,
    tool_input: Dict[str, Any],
    config,
    extended_syntax: bool,
) -> RuntimeVerdict:
    """
    Resolve a single hook event to a :class:`~toolguard.config_types.RuntimeVerdict`,
    READ-ONLY.

    This adds only the parts :func:`main` owns on top of the shared decision
    primitive -- the governed-tool check and the empty-input guard -- and then
    delegates the actual resolution to :func:`toolguard.api.decide`, the single
    side-effect-free primitive that also backs the replay harness and other
    tooling (TOO-45 R6-S2: ``decide`` moved into :mod:`toolguard.api`, the
    layer both this module and the tooling layer are allowed to import from;
    :mod:`toolguard.tools.decision` now re-exports the same function object
    unchanged).  Delegating (rather than re-copying the file-vs-command
    dispatch and the ``[hard_deny]`` handling) makes the ``--eval`` verdict
    identical to the live hook's by construction.  No logging, divergence
    checks, or auto-migration happen here.  ``no_match_fallback`` (including
    the TOO-15 ``allow_with_warning`` auto-allow, whose deprecated legacy
    alias is ``warn_deny``) is resolved entirely inside
    :func:`~toolguard.api.decide` via the shared config layer -- there is no
    separate reason-rewrite step here or in :func:`main` to keep in sync.

    TOO-19 Phase 1: the returned verdict's ``additional_context`` carries the
    winning rule's ``additionalContext`` enrichment, so ``--eval`` (whose whole
    purpose is previewing what the live hook would do) doesn't silently omit a
    real output field. The two synthetic guard verdicts below (ungoverned
    tool, missing target) have no matched rule and leave every optional field
    at :class:`~toolguard.config_types.RuntimeVerdict`'s defaults.

    Args:
        tool_name: The tool being invoked (e.g. ``'Bash'``, ``'Read'``).
        tool_input: The tool input dict (carrying ``command`` or ``file_path``).
        config: The resolved configuration to evaluate against.
        extended_syntax: Whether extended (regex/glob) prefixes are honoured.

    Returns:
        The resolved :class:`~toolguard.config_types.RuntimeVerdict`, whose
        ``decision`` is ``'allow'``, ``'deny'``, or ``'ask'``.
    """
    governed_tools = list(config.governed_tools())
    if tool_name not in governed_tools:
        return RuntimeVerdict(
            decision="allow",
            reason=f"Not a governed tool (governed: {', '.join(governed_tools)})",
        )

    if tool_name in FILE_PATH_TOOLS:
        target = tool_input.get("file_path", "")
        if not target:
            return RuntimeVerdict(
                decision="deny", reason="No file_path provided in tool input"
            )
    else:
        target = tool_input.get("command", "")
        if not target:
            return RuntimeVerdict(
                decision="deny", reason="No command provided in tool input"
            )

    # TOO-45 R6-S3: decide() now returns a real RuntimeVerdict directly (the
    # old Decision DTO it used to return, and the _verdict_from_decision
    # adapter that re-rendered one into the other, are both gone), so no
    # further conversion is needed here.
    return decide(config, tool_name, target, extended_syntax)


def _run_eval_mode() -> None:
    """
    Handle ``toolguard --eval``: read one hook event on stdin, resolve it
    READ-ONLY, and print the JSON permissionDecision to stdout.

    No logging, divergence checks, or auto-migration are performed, so probing a
    project's configuration (e.g. from the cross-project security-audit skill)
    never mutates the project or writes to its logs.  Errors are reported as a
    ``deny`` decision on stderr, matching the live hook's fail-safe contract.
    """
    try:
        hook_data = parse_hook_input()
        tool_name = hook_data["tool_name"]
        tool_input = hook_data["tool_input"]
        cwd = hook_data.get("cwd", None)
        # Anchor BOTH the rule hierarchy and the env/.env-derived settings
        # (extended_syntax) to the TARGET project's cwd, ignoring any stale
        # CLAUDE_SETTINGS_PATH / TOOLGUARD_PROJECT_ROOT override -- the same
        # project-rooted rule the audit tooling uses (config_access.load_config).
        # This keeps a cross-project sweep faithful to each probed project.
        config = load_configuration(cwd, ignore_env_override=True)
        env_config = get_env_config(start_dir=cwd)
        extended_syntax = env_config.get("extended_syntax", True)
        verdict = _resolve_event(tool_name, tool_input, config, extended_syntax)
        print(json.dumps(create_hook_output(verdict)))
    except json.JSONDecodeError as e:
        output = create_hook_output(
            RuntimeVerdict(
                decision="deny", reason=f"Failed to parse hook input: {str(e)}"
            )
        )
        print(json.dumps(output), file=sys.stderr)
    except ValueError as e:
        output = create_hook_output(
            RuntimeVerdict(decision="deny", reason=f"Invalid hook input: {str(e)}")
        )
        print(json.dumps(output), file=sys.stderr)
    except Exception as e:
        output = create_hook_output(
            RuntimeVerdict(
                decision="deny", reason=f"Unexpected error in hook: {str(e)}"
            )
        )
        print(json.dumps(output), file=sys.stderr)


def _print_not_a_standalone_command_message() -> None:
    """Print the friendly explanation for a stray manual/probing invocation."""
    print(
        "toolguard: this is a Claude Code PreToolUse hook, not a standalone command.\n"
        "It reads a JSON hook event on stdin and is invoked automatically by Claude.\n"
        "To smoke-test: "
        'printf \'{"tool_name":"Bash","tool_input":{"command":"ls -la"},'
        '"hook_event_name":"PreToolUse"}\' | toolguard',
        file=sys.stderr,
    )


def _warn_if_settings_path_override() -> None:
    """
    Warn on stderr when ``CLAUDE_SETTINGS_PATH`` puts toolguard in single-file mode.

    Single-file override footgun (TOO-15): CLAUDE_SETTINGS_PATH makes toolguard
    read ONE settings file for EVERY directory, bypassing the whole hierarchy. As
    a persistently-exported shell variable it silently lets one project's config
    govern the entire machine (and, if that config is fail-closed takeover, can
    lock it out). Surface it on stderr so the bypass is never invisible.
    """
    settings_path_override = os.environ.get("CLAUDE_SETTINGS_PATH")
    if not settings_path_override:
        return
    print(
        "[TOOLGUARD WARNING] CLAUDE_SETTINGS_PATH is set "
        f"({settings_path_override}). Toolguard is in single-file mode: the "
        "configuration hierarchy is BYPASSED -- only this file and its adjacent "
        "toolguard_hook.toml govern every directory. If this is unintended, "
        "unset CLAUDE_SETTINGS_PATH.",
        file=sys.stderr,
    )


def _log_config_discovery(config, env_config: Dict[str, Any]) -> None:
    """
    Emit a config-discovery diagnostic when the discovered levels changed.

    Writes "discovered N config levels: <level: path>, ..." to the resolution
    log when the set differs from the last recorded entry for this project root
    (TOO-8 Phase 4, M2; TOO-19). toolguard is a fresh process on every tool
    call, so there is no in-process "once per session" -- the change-detecting
    JSONL log inside :func:`log_discovery` is the guard instead, and it is a
    no-op (writes nothing) when nothing changed.

    Args:
        config: The resolved configuration whose levels are described.
        env_config: Environment configuration dict carrying ``log_dir`` and
            ``project_root``. A no-op when no log dir is resolved.
    """
    disco_log_dir = env_config.get("log_dir")
    if not disco_log_dir:
        return
    log_discovery(
        list(config.describe_levels()),
        disco_log_dir,
        str(env_config.get("project_root", "")),
    )


def _announce_takeover_state(takeover, log_dir) -> None:
    """
    Surface takeover-mode status: the enabled warning, or a cross-level conflict.

    On a cross-level ``takeover_mode.enabled`` disagreement (TOO-8 Phase 5)
    ``enabled`` is already fail-safe OFF; the conflict is recorded to the
    conflict log and a once-per-session warning is surfaced. The downstream
    path is already the safe one (native prompts active).

    Args:
        takeover: The resolved :class:`~toolguard.config.TakeoverConfig`.
        log_dir: Directory for the warning/conflict logs, or None (no-op).
    """
    if not log_dir:
        return
    if takeover.enabled:
        issue_takeover_warning(log_dir, to_stdout=True)
        return

    global _takeover_conflict_logged
    if takeover.conflict is None or _takeover_conflict_logged:
        return
    _takeover_conflict_logged = True
    _log_takeover_enabled_conflict(takeover.conflict, log_dir)
    issue_takeover_warning(log_dir, to_stdout=True)


def _resolve_takeover_mode(config, env_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve takeover mode, announce its state, and return the legacy dict form.

    The divergence/auto-migration tooling still consumes a plain dict, so it is
    built from the resolved ``TakeoverConfig`` here and those clients stay
    unchanged.

    Args:
        config: The resolved configuration.
        env_config: Environment configuration dict (for ``log_dir``).

    Returns:
        The takeover settings as the plain dict those clients expect.
    """
    takeover = config.takeover_mode()
    _announce_takeover_state(takeover, env_config.get("log_dir"))
    return {
        "enabled": takeover.enabled,
        "ignored_allow_patterns": list(takeover.ignored_allow_patterns),
        "additional_ignored_patterns": list(takeover.additional_ignored_patterns),
        "no_match_fallback": takeover.no_match_fallback,
    }


def _run_divergence_check(
    config, env_config: Dict[str, Any], takeover_dict: Dict[str, Any]
) -> None:
    """
    Check for config divergence once per session, auto-migrating when configured.

    :func:`check_and_warn_divergence` (``config``-layer) only DETECTS
    divergence and prints an immediate stderr notice -- it deliberately does
    not write to the structured error log itself (TOO-45 R5d: that would make
    a config-layer module depend on error_log, a runtime-layer module). This
    function, which already legitimately imports :mod:`toolguard.error_log`,
    does that write on its behalf when a new warning is due.

    Args:
        config: The resolved configuration.
        env_config: Environment configuration dict (for ``log_dir``).
        takeover_dict: Takeover settings in the plain-dict form these clients take.
    """
    global _divergence_check_done
    if _divergence_check_done:
        return
    _divergence_check_done = True

    log_dir = env_config.get("log_dir")
    if not log_dir:
        return
    project_root = config.project_root
    if project_root is None:
        return

    divergence = check_and_warn_divergence(project_root, log_dir, takeover_dict)
    if divergence.warning_message is not None:
        log_warning(divergence.warning_message, divergence.corrective_steps, log_dir)
    if not divergence.divergent_patterns:
        return

    config_sync = config.config_sync_settings()
    if config_sync["auto_migrate"]:
        run_auto_migration(project_root, log_dir, dict(config_sync), takeover_dict)


def _agent_info_for(hook_data: Dict[str, Any]) -> str:
    """
    Identify the invoking agent for logging purposes.

    Args:
        hook_data: The parsed hook event (read for ``transcript_path``).

    Returns:
        The subagent's name when the call came from a subagent, else ``"main"``.
    """
    agent_context = identify_current_agent(hook_data.get("transcript_path", ""))
    return (
        agent_context["subagent_name"]
        if agent_context["agent_type"] == "subagent"
        else "main"
    )


def _log_non_allow_decision(
    verdict: RuntimeVerdict,
    log_target: str,
    agent_info: str,
    env_config: Dict[str, Any],
    permission_mode: Optional[str],
) -> None:
    """
    Write the resolution-log entry for an 'ask' or 'deny' verdict.

    TOO-45 R1d: takes the whole *verdict* instead of its ``decision``/
    ``reason``/``additional_context``/``matched_rule``/``provenance`` fields
    threaded through as five separate parameters (the change that let the
    ``# noqa: PLR0913`` marker this replaced come off -- see ``log_command``'s
    own R1d note).

    Identical for file-path tools and command tools, so both call this. An
    'ask' is recorded under ``note`` (it is not a violation) with the FULL
    reason text -- never split, so it carries no fabrication risk regardless
    of the reason's shape. A deny records the violated rule from
    ``verdict.matched_rule`` via :func:`_reason_suffix_or_placeholder` (the
    SAME mechanism the allow side uses, via
    :func:`_matched_rule_for_single_command`, so the two call sites cannot
    diverge into two conventions -- see that function's docstring for the
    fabrication risk this guards against). Unlike the allow side, when
    ``verdict.matched_rule`` is ``None`` and ``verdict.reason`` is not a
    recognised escape hatch, the FULL reason is used (not ``None``) -- this
    preserves the pre-TOO-19 behaviour for reasons like ``"No commands to
    evaluate"`` that never named a rule at all.

    Args:
        verdict: The resolved 'ask' or deny verdict. ``reason`` is consulted
            only for :func:`_reason_suffix_or_placeholder`'s
            fallback-escape-hatch classification (the 'ask' branch also uses
            it verbatim as the log note). ``matched_rule`` is ``None`` when
            no rule matched (fail-closed default deny, hard deny, or a
            fallback escape hatch). ``provenance`` is rendered via
            :func:`_provenance_brief`, suppressed the same way as
            ``matched_rule`` when ``reason`` names a fallback escape hatch
            (never paired with a rule that did not actually decide the
            verdict), and naturally absent for a hard deny (pooled across
            levels, no single provenance).
        log_target: What is being logged -- a command, or ``Tool(path)``.
        agent_info: Agent identification string.
        env_config: Environment configuration dict.
        permission_mode: Claude Code's own permission mode, recorded for diagnosis.
    """
    if verdict.decision == "ask":
        log_command(
            LogRecord(
                command_str=log_target,
                status="ask",
                note=verdict.reason,
                extra_info=agent_info,
                permission_mode=permission_mode,
                additional_context=verdict.additional_context,
            ),
            config=env_config,
        )
        return

    # Use the structured violated rule for logging -- an absent/generic
    # record beats a false one when reason names a fallback escape hatch
    # rather than a matched rule. Provenance is suppressed the same way
    # (see the Args docstring above).
    suffix = _reason_suffix_or_placeholder(
        verdict.decision,
        verdict.reason,
        FALLBACK_DENY_PLACEHOLDER,
        verdict.matched_rule,
    )
    violated_rules = [suffix if suffix is not None else verdict.reason]
    logged_provenance = (
        _provenance_brief(verdict.provenance)
        if suffix == verdict.matched_rule
        else None
    )
    log_command(
        LogRecord(
            command_str=log_target,
            status="refused",
            violated_rules=violated_rules,
            extra_info=agent_info,
            permission_mode=permission_mode,
            additional_context=verdict.additional_context,
            provenance=logged_provenance,
        ),
        config=env_config,
    )


def _handle_file_path_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    config,
    env_config: Dict[str, Any],
    agent_info: str,
    permission_mode: Optional[str],
) -> RuntimeVerdict:
    """
    Resolve and log a file-path tool event (Read, Write, Edit).

    Resolves the file path permission via the more-specific-wins level cascade.
    No early "no allow configured" short-circuit here (TOO-15): an entirely
    unconfigured tool resolves to 'ask' and a configured-but-non-matching tool
    resolves per ``no_match_fallback`` -- both are decided centrally inside
    ``resolve_file_path_permission_detailed`` /
    ``permission_resolution.resolve_permission_detailed``, so the hook and
    ``toolguard.api.decide()`` cannot drift apart.

    Args:
        tool_name: The file tool being invoked.
        tool_input: The tool input dict (read for ``file_path``).
        config: The resolved configuration.
        env_config: Environment configuration dict.
        agent_info: Agent identification string.
        permission_mode: Claude Code's own permission mode, recorded for diagnosis.

    Returns:
        The resolved :class:`~toolguard.config_types.RuntimeVerdict` (TOO-45
        R1d -- previously a bare ``(decision, reason, additional_context)``
        tuple that discarded ``provenance``/``matched_rule``/``overrides``/
        ``fallback_warning``/``sub_matches``/``tool``/``target``).
    """
    file_path = tool_input.get("file_path", "")
    if not file_path:
        log_command(
            LogRecord(
                command_str=f"{tool_name}()",
                status="refused",
                violated_rules=["no file_path provided"],
                extra_info=agent_info,
                permission_mode=permission_mode,
            ),
            config=env_config,
        )
        return RuntimeVerdict(
            decision="deny", reason="No file_path provided in tool input"
        )

    extended_syntax = env_config.get("extended_syntax", True)
    result = resolve_file_path_permission_detailed(
        tool_name, file_path, config, extended_syntax
    )
    log_target = f"{tool_name}({file_path})"

    if result.decision == "allow":
        # Conflict: a more-specific allow overrode a less-specific deny. A
        # file-path result carries 0 or 1 overrides (TOO-45 R1c;
        # RuntimeVerdict.overrides is always a list -- see its docstring's
        # "overrides" reconciliation) -- this loop runs 0 or 1 times, same
        # behaviour as the old single `_log_conflict_override(log_target,
        # result.override, ...)` call (which was already a no-op when
        # `override` was None).
        for _, override in result.overrides:
            _log_conflict_override(log_target, override, env_config.get("log_dir"))
        _log_fallback_allow_warning(
            result.fallback_warning, result.reason, env_config.get("log_dir")
        )
        log_command(
            LogRecord(
                command_str=log_target,
                status="executed",
                matched_rule=result.matched_rule,
                provenance=_provenance_brief(result.provenance),
                extra_info=agent_info,
                permission_mode=permission_mode,
                additional_context=result.additional_context,
            ),
            config=env_config,
        )
    else:
        _log_non_allow_decision(
            result, log_target, agent_info, env_config, permission_mode
        )

    return result


def _handle_command_tool(
    tool_input: Dict[str, Any],
    config,
    env_config: Dict[str, Any],
    agent_info: str,
    permission_mode: Optional[str],
) -> RuntimeVerdict:
    """
    Resolve and log a command tool event (Bash, MCP terminals).

    Command tools all resolve against the Bash permission patterns. No early
    "no allow configured" short-circuit here (TOO-15): an entirely unconfigured
    Bash resolves to 'ask' and a configured-but-non-matching Bash resolves per
    ``no_match_fallback`` (default 'ask'; 'deny' fails closed;
    'allow_with_warning' -- or its deprecated 'warn_deny' alias -- auto-allows
    with a warning; 'allow' -- or its 'allow_with_no_warnings' alias, TOO-19 --
    auto-allows with NO warning) -- all decided centrally inside
    ``resolve_bash_permission_detailed`` / ``permission_resolution.resolve_permission_detailed``
    so the hook and ``toolguard.api.decide()`` cannot drift apart.

    Resolution is more-specific-wins: each sub-command of a compound command
    cascades independently through the levels; the compound is allowed iff all
    are. The unoverridable ``[hard_deny]`` pool is checked FIRST per
    sub-command, so a compound is hard-denied if ANY sub-command is hard-denied.

    Args:
        tool_input: The tool input dict (read for ``command``).
        config: The resolved configuration.
        env_config: Environment configuration dict.
        agent_info: Agent identification string.
        permission_mode: Claude Code's own permission mode, recorded for diagnosis.

    Returns:
        The resolved :class:`~toolguard.config_types.RuntimeVerdict` (TOO-45
        R1d -- previously a bare ``(decision, reason, additional_context)``
        tuple that discarded ``provenance``/``matched_rule``/``overrides``/
        ``fallback_warning``/``sub_matches``/``tool``/``target``).
    """
    command = tool_input.get("command", "")
    if not command:
        log_command(
            LogRecord(
                command_str=command,
                status="refused",
                violated_rules=["no command provided"],
                extra_info=agent_info,
                permission_mode=permission_mode,
            ),
            config=env_config,
        )
        return RuntimeVerdict(
            decision="deny", reason="No command provided in tool input"
        )

    extended_syntax = env_config.get("extended_syntax", True)
    hd_deny, hd_allow = config.hard_deny("Bash")
    result = resolve_bash_permission_detailed(
        command, config, extended_syntax, hd_deny, hd_allow
    )

    if result.decision == "allow":
        # Conflict logging: any sub-command whose more-specific allow overrode
        # a less-specific deny is recorded to the conflict stream.
        conflict_log_dir = env_config.get("log_dir")
        for sub_command, override in result.overrides:
            _log_conflict_override(sub_command, override, conflict_log_dir)
        _log_fallback_allow_warning(
            result.fallback_warning, result.reason, conflict_log_dir
        )
        _log_allowed_command(result, command, agent_info, env_config, permission_mode)
    else:
        _log_non_allow_decision(
            result, command, agent_info, env_config, permission_mode
        )

    return result


def main() -> None:
    """
    Main hook entry point.

    Algorithm:
    1. Parse args (provides --help; does NOT consume stdin).
    2. Guard against interactive (TTY) invocation: print an explanation and exit.
    3. Load environment configuration.
    4. Run startup validation (once per session) - logs warnings for config issues.
    5. Parse input from stdin.
    6. Check if tool is governed (configurable list).
    7. Determine tool type (file path or command).
    8. For file tools: extract file_path, check against glob patterns.
    9. For command tools: extract command, check against patterns.
    10. Log decision.
    11. Output decision as JSON to stdout.

    Exit codes:
    - Always exits with 0 (errors communicated via JSON), EXCEPT when --help
      is requested (argparse exits 0) or when stdin is a TTY (exits 0 after
      printing the informational message).
    """
    parser = _build_hook_argparser()
    # parse_known_args() is used instead of parse_args() so that the hook still
    # works correctly when invoked via the test runner (which places test names
    # in sys.argv). This hook accepts NO arguments -- it only reads stdin -- so
    # unknown args are silently discarded. --help still exits 0 via argparse.
    args, _ = parser.parse_known_args()

    # Interactive guard: if a human runs 'toolguard' in a terminal without piping
    # a JSON event, do not block on stdin. Print a brief explanation and exit.
    # Claude always pipes JSON (not a TTY), so this guard never fires in real use.
    # This is placed before the --eval branch so 'toolguard --eval' typed by hand
    # (no piped stdin) shows the message instead of hanging on stdin.read().
    # Exit code 0: informational, not an error (Arnon: change to non-zero if preferred).
    if sys.stdin.isatty():
        _print_not_a_standalone_command_message()
        sys.exit(0)

    # Read-only evaluation mode (--eval): resolve one piped event and print the
    # verdict WITHOUT logging, divergence checks, or auto-migration. Used by the
    # cross-project security-audit skill to probe a project's safety floor without
    # mutating it.
    if args.eval_mode:
        _run_eval_mode()
        return

    try:
        # Load environment configuration
        env_config = get_env_config()

        # Parse hook input first to get cwd
        hook_data = parse_hook_input()

        tool_name = hook_data["tool_name"]
        tool_input = hook_data["tool_input"]
        cwd = hook_data.get("cwd", None)

        # Obtain the resolved configuration once via the public abstraction.
        # All file discovery, parsing, and format/location decisions live in the
        # config module; the hook only consumes semantic accessors from here on.
        config = load_configuration(cwd)

        _warn_if_settings_path_override()
        _log_config_discovery(config, env_config)

        # Run startup validation (once per session), reusing the loaded config.
        _run_startup_validation(env_config, cwd, config)

        takeover_dict = _resolve_takeover_mode(config, env_config)
        _run_divergence_check(config, env_config, takeover_dict)

        # Resolve the list of governed tools via the config abstraction
        governed_tools = list(config.governed_tools())

        # Only handle tools in the governed list
        if tool_name not in governed_tools:
            # Not a governed tool - allow (other hooks handle other tools)
            output = create_hook_output(
                RuntimeVerdict(
                    decision="allow",
                    reason=f"Not a governed tool (governed: {', '.join(governed_tools)})",
                )
            )
            print(json.dumps(output))
            sys.exit(0)

        # Identify current agent context (used for logging)
        agent_info = _agent_info_for(hook_data)

        # Claude Code's own permission_mode (e.g. 'default', 'plan', an auto
        # mode) is recorded alongside the decision, purely for diagnosis -- it
        # never affects the verdict itself. See log_command's docstring.
        permission_mode = hook_data.get("permission_mode")

        # Resolve and log the event: file path tools (Read, Write, Edit) and
        # command tools (Bash, MCP terminals) differ only in how the target is
        # extracted and resolved; both return the same RuntimeVerdict shape
        # (TOO-45 R1d).
        if tool_name in FILE_PATH_TOOLS:
            verdict = _handle_file_path_tool(
                tool_name, tool_input, config, env_config, agent_info, permission_mode
            )
        else:
            verdict = _handle_command_tool(
                tool_input, config, env_config, agent_info, permission_mode
            )

        # Create and output decision
        output = create_hook_output(verdict)
        print(json.dumps(output))
        sys.exit(0)

    except EmptyStdinError:
        # A stray manual/probing invocation (e.g. a bare `toolguard --version`
        # an agent ran to check the installed version), not a real hook call
        # from Claude Code (which always pipes real JSON) and not an
        # unexpected internal error -- treat it exactly like the TTY guard:
        # a friendly explanation, no crash report (TOO-15, recurred twice).
        _print_not_a_standalone_command_message()
        sys.exit(0)

    except json.JSONDecodeError as e:
        # JSON parsing error - deny with error message
        error_reason = f"Failed to parse hook input: {str(e)}"
        output = create_hook_output(
            RuntimeVerdict(decision="deny", reason=error_reason)
        )
        print(json.dumps(output), file=sys.stderr)
        crash_context = _build_crash_context(locals())
        crash_context["raw_stdin"] = e.doc
        log_crash(e, crash_context, caught_as="json.JSONDecodeError")
        sys.exit(0)

    except ValueError as e:
        # Validation error - deny with error message
        error_reason = f"Invalid hook input: {str(e)}"
        output = create_hook_output(
            RuntimeVerdict(decision="deny", reason=error_reason)
        )
        print(json.dumps(output), file=sys.stderr)
        log_crash(e, _build_crash_context(locals()), caught_as="ValueError")
        sys.exit(0)

    except Exception as e:
        # Unexpected error - deny and log
        error_reason = f"Unexpected error in hook: {str(e)}"
        output = create_hook_output(
            RuntimeVerdict(decision="deny", reason=error_reason)
        )
        print(json.dumps(output), file=sys.stderr)
        print(f"Error: {error_reason}", file=sys.stderr)
        log_crash(e, _build_crash_context(locals()), caught_as="unexpected Exception")
        sys.exit(0)


if __name__ == "__main__":
    main()
