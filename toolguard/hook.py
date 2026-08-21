#!/usr/bin/env python3
"""
Claude Code PreToolUse hook entry point: reads one hook event on stdin and
writes a permission decision to stdout.

Command tools (Bash, MCP terminals) go through compound-command parsing;
file-path tools (Read, Write, Edit) go through path matching (glob by
default, with extended-syntax prefixes honoured).

Exit code 0 in the normal case: a well-formed JSON decision on stdout (see
:func:`main` for the stray-invocation paths that emit none instead). Exit 2 is
a last-resort hard block: it fires if writing that JSON to stdout itself
fails, or from argparse's own usage-error path on a malformed CLI invocation
(Claude Code treats exit 2, and only exit 2, as blocking).
"""

import argparse
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toolguard import ambient, error_reporter
from toolguard.api import decide
from toolguard.auto_migrate import run_auto_migration
from toolguard.compound import FALLBACK_ALLOW_PLACEHOLDER, FALLBACK_DENY_PLACEHOLDER
from toolguard.config import load_configuration
from toolguard.config_divergence import check_and_warn_divergence
from toolguard.env_config import get_env_config
from toolguard.error_log import log_conflict, log_crash, log_error, log_warning
from toolguard.error_reporter import Reporter
from toolguard.log_writer import LogRecord, log_command, log_discovery, resolve_log_dir
from toolguard.resolve import (
    RuntimeVerdict,
    UnitVerdict,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)
from toolguard.constants import DEFAULT_COMMAND_PAYLOAD_KEY, FILE_TOOLS
from toolguard.session_warnings import issue_takeover_warning
from toolguard.subagent import identify_current_agent
from toolguard.tool_spec import KNOWN_TOOL_NAMES
from toolguard.tool_spec import payload_key as _tool_payload_key

#: Tools that operate on file paths (glob-matched), as opposed to command
#: tools (compound-parsed). Alias of ``toolguard.constants.FILE_TOOLS`` --
#: prefer ``toolguard.constants.FILE_TOOLS`` in new code.
FILE_PATH_TOOLS = FILE_TOOLS


def _run_startup_validation(
    env_config: Dict[str, Any], start_dir: str = None, config=None
) -> None:
    """
    Route this invocation's configuration issues to the log stream matching each one's severity.

    Obtains the resolved :class:`~toolguard.config.Configuration` and renders the
    structured issues it reports (see :meth:`~toolguard.config.Configuration.validation_issues`
    for what is detected). The hook performs no file discovery, parsing, or
    format branching here -- that lives entirely in the config module.

    Args:
        env_config: Environment configuration dict with log_dir
        start_dir: Directory to start searching for project root from. Defaults to cwd.
        config: Pre-loaded Configuration to reuse. When None, one is loaded via
            ``load_configuration(start_dir)`` so this function remains usable on
            its own.
    """
    if config is None:
        config = load_configuration(start_dir)

    log_dir = env_config.get("log_dir")
    if not log_dir:
        project_root = config.project_root
        if project_root is None:
            return  # Can't log without log dir
        log_dir = project_root / "logs"

    # Route each issue to the stream matching its severity: 'error'-level
    # issues to the error stream, everything else (today only 'warning') to
    # the warning stream.
    for issue in config.validation_issues():
        if issue.level == "error":
            log_error(issue.message, issue.corrective_steps, log_dir)
        else:
            log_warning(issue.message, issue.corrective_steps, log_dir)


class EmptyStdinError(ValueError):
    """
    Raised when stdin was read but contained no data.

    A distinct subclass, not a bare ``ValueError``, so :func:`main` can treat it
    like the TTY guard -- a stray manual/probing invocation (e.g. a `toolguard
    --version` an agent ran to check the installed version, an unrecognized
    flag silently discarded by argparse, or any other non-hook invocation),
    not an unexpected internal error worth a crash report. A real install hit
    this twice, and the crash report it produced looked like a hook defect
    while being nothing but a manual probe.
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

    Takes the whole :class:`~toolguard.config_types.RuntimeVerdict` -- including
    the error/guard paths in this module that build a synthetic verdict inline
    (e.g. ``RuntimeVerdict(decision="deny", reason=...)``) -- so every call site
    goes through the same construction shape. Only ``decision``, ``reason``, and
    ``additional_context`` are consumed here: the hook's JSON response is a
    projection of the verdict, not the whole of it (the audit-log functions in
    this module read ``provenance``, ``matched_rule``, ``sub_matches``,
    ``overrides`` and ``fallback_warning`` as well).

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
        only when ``verdict.additional_context`` is a non-empty string --
        omitted entirely (not set to ``null``) otherwise.
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


def _finalize_output(verdict: RuntimeVerdict, reporter: Reporter) -> Dict[str, Any]:
    """
    Build the hook's JSON response for *verdict*, merging in any faults
    *reporter* accumulated so far this invocation -- appended to
    ``additionalContext``, alongside the rule's own enrichment rather than
    replacing it. Used on both the success path and inside :func:`main`'s
    ``except`` handlers, which drain the same *reporter*.
    """
    output = create_hook_output(verdict)
    fault_context = reporter.drain_claude_context()
    if fault_context:
        hook_output = output["hookSpecificOutput"]
        existing = hook_output.get("additionalContext")
        hook_output["additionalContext"] = (
            f"{existing}\n\n{fault_context}" if existing else fault_context
        )
    return output


def _emit_decision(output: Dict[str, Any]) -> None:
    """
    Print the hook's JSON decision to stdout -- the ONE place any code path in
    :func:`main` delivers a decision, success or error alike. Every path must
    go through here: an exit-0 hook with no usable decision on stdout is not
    neutral -- Claude Code reads it as "no opinion" and silently falls through
    to native permission handling, the exact fail-open this hook exists to
    prevent.

    Args:
        output: The JSON-serializable decision dict, from
            :func:`_finalize_output` on the live-hook path, or
            :func:`create_hook_output` directly on the ``--eval`` path (which
            never drains a fault buffer -- see :func:`_run_eval_mode`).

    If serializing or writing *output* raises, there is no decision left to
    deliver: falls back to ``sys.exit(2)`` with the failure on stderr -- the
    one case where the host's own blocking signal (exit 2) is all that's left.

    The flush is inside the ``try`` deliberately: Claude Code's stdout is a
    pipe, which is block-buffered, so a bare ``print()`` can return
    successfully with the bytes still sitting in the buffer -- a broken reader
    then only surfaces at interpreter shutdown, past this function, and the
    process exits non-zero-non-2 (the same fail-open this function exists to
    close). Flushing here is what makes a real write failure raise where it
    can still be caught.

    Swapping *sys.stdout* for a working stream before ``sys.exit(2)`` is also
    deliberate: CPython flushes stdout again during interpreter shutdown, and
    when that second flush ALSO fails on the still-broken pipe, CPython
    silently overrides ``sys.exit(2)``'s requested code with exit status 120
    -- the exact non-2 code this function exists to avoid. Leaving
    ``sys.exit`` (not ``os._exit``) keeps this path testable and lets normal
    interpreter cleanup still run.
    """
    try:
        print(json.dumps(output))
        sys.stdout.flush()
    except Exception as e:
        print(f"toolguard: failed to emit decision: {e}", file=sys.stderr)
        sys.stdout = io.StringIO()
        sys.exit(2)


#: Corrective steps shared by all three of :func:`main`'s crash-handling ``except`` clauses.
_CRASH_CORRECTIVE_STEPS = (
    "Check the crash report under ~/.toolguard/errors/ for the full traceback."
)


def _report_crash_fault(reporter: Reporter, error_reason: str) -> None:
    """Report :func:`main`'s own crash as a fault, so it reaches Claude via ``additionalContext``."""
    reporter.fault(
        f"toolguard crashed while deciding: {error_reason}", _CRASH_CORRECTIVE_STEPS
    )


def _build_crash_context(local_vars: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract a small, readable snapshot of in-flight hook state for :func:`log_crash`.

    :func:`main`'s ``except`` clauses can fire before ``hook_data``/``tool_name``/
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

    Cites both sides' provenance and the command/path that triggered the
    override. The decision still follows more-specific-wins (the allow won);
    this message merely records that a less-specific deny was overridden.

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
    Route an ``allow_with_warning``-sourced 'allow' decision to the WARNING
    log stream.

    ``docs/configuration.md`` promises that ``allow_with_warning`` logs a
    warning, for both ``no_match_fallback`` and ``undecidable_fallback`` --
    this is what makes that reach :func:`toolguard.error_log.log_warning`'s
    dedicated stream, beyond the reason text already visible in the
    resolution log. *fallback_warning* is read as a plain boolean
    (:attr:`~toolguard.config_types.RuntimeVerdict.fallback_warning`);
    *reason* is never inspected to decide whether to log, only used as the
    warning text once the caller says to log it.

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


def describe_takeover_conflict(conflict) -> Tuple[str, str]:
    """
    Compose the fail-safe conflict message and its corrective steps.

    Shared by the conflict log entry and the stderr notice, so both describe
    the same fail-safe -- native prompts stay active, nothing is bypassed --
    without duplicating the wording.

    Args:
        conflict: The :class:`~toolguard.config.TakeoverEnabledConflict`.

    Returns:
        ``(message, corrective_steps)``.
    """
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
    return message, corrective


def _log_takeover_enabled_conflict(conflict, log_dir) -> None:
    """
    Record a cross-level ``takeover_mode.enabled`` disagreement.

    Writes a conflict-log entry citing every disagreeing level's value and
    provenance and noting that fail-safe OFF was applied (so native Claude
    prompts stay active). No-op when there is no conflict or no log dir.

    Args:
        conflict: The :class:`~toolguard.config.TakeoverEnabledConflict`, or None.
        log_dir: Directory for the conflict log, or None (no-op).
    """
    if conflict is None or not log_dir:
        return
    message, corrective = describe_takeover_conflict(conflict)
    log_conflict(message, corrective, log_dir)


def _reason_suffix_or_placeholder(
    fallback_kind: Optional[str], placeholder: str, matched_rule: Optional[str]
) -> Optional[str]:
    """
    Return *matched_rule*, or *placeholder* when *fallback_kind* names a fallback escape hatch.

    A fallback escape-hatch reason ends in the same ``": <text>"`` shape as a
    genuine rule-match reason, but the text is a truncated display command,
    not a pattern -- e.g. ``Denied by undecidable_fallback=deny (...): python
    -c``. Crediting that text to a rule would fabricate an attribution for a
    rule that does not exist in the config.
    :attr:`~toolguard.config_types.RuntimeVerdict.fallback_kind` is the
    structural fact that tells the two shapes apart -- computed at the point
    the outcome was decided, never re-derived from *reason* here. The allow
    side reads the per-unit :attr:`~toolguard.config_types.UnitVerdict.fallback_kind`
    instead (see :func:`_unit_matched_rule_for_log`).

    Args:
        fallback_kind: The verdict's own
            :attr:`~toolguard.config_types.RuntimeVerdict.fallback_kind` --
            ``'denied'`` for the ``undecidable_fallback=deny`` escape hatch,
            else ``None``.
        placeholder: What to return when *fallback_kind* names a fallback
            escape hatch instead of a genuine rule match.
        matched_rule: The structured matched-rule value already resolved by
            the caller (``None`` when no rule matched).

    Returns:
        *placeholder* when *fallback_kind* is not ``None``, otherwise
        *matched_rule* unchanged (which may itself be ``None`` -- an absent
        record beats a false one either way).
    """
    if fallback_kind is not None:
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
    Derive the ``Matched Rule`` audit-log field for one sub-command's unit verdict.

    Reads :attr:`~toolguard.config_types.UnitVerdict.fallback_kind` directly,
    at the UNIT altitude -- the counterpart to
    :func:`_reason_suffix_or_placeholder`'s RUNTIME-altitude read of
    :attr:`~toolguard.config_types.RuntimeVerdict.fallback_kind`.

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

    Reads ``verdict.sub_matches`` (one :class:`~toolguard.config_types.UnitVerdict`
    per extracted sub-command, covering every case the combined reason string
    can hold -- including an ask-floor leaf's escape-hatch outcome and an
    undecidable segment) directly, rather than re-parsing the combined reason
    string. A sub-command whose allow came from ``no_match_fallback`` carries
    no ``" -> "`` marker in its raw reason, so a parser looking for that shape
    silently drops it from the audit log instead -- measured at 83% of
    compound-allow decisions under-logged this way before this function read
    ``sub_matches`` structurally. A simple command has exactly one
    ``UnitVerdict`` in ``sub_matches``, so the single-leaf and compound cases
    share this one loop.

    Args:
        verdict: The resolved 'allow' verdict for *command*.
            ``additional_context`` is the accumulated ``additionalContext``
            enrichment for the whole compound command; it is not attributable
            to a single sub-command (it may combine several sub-commands'
            contexts), so it is recorded on every logged sub-command entry the
            same way the hook injects one accumulated block for the whole
            command.
        command: The original command string -- used only as a defensive
            fallback (see below) when ``sub_matches`` is empty, which should
            not happen for a real 'allow' verdict produced by
            :func:`~toolguard.resolve.resolve_bash_permission_detailed`
            (every 'allow' path populates at least one entry).
        agent_info: Agent identification string.
        env_config: Environment configuration dict.
        permission_mode: Claude Code's own ``permission_mode`` from the hook
            input, if present -- recorded on the log entry for diagnosis only
            (see :func:`main`).
    """
    if not verdict.sub_matches:
        # Defensive fallback for a synthetic/hand-built verdict with no
        # sub_matches (should not occur for a real resolver result) -- log
        # what is in hand without the placeholder guard below, since there is
        # no per-unit fallback_kind to consult.
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
        # decide the verdict -- suppressed the same way the placeholder
        # substitution above signals an escape hatch.
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


def _command_target_key(tool_name: str) -> str:
    """
    Return the ``tool_input`` key holding a command tool's target.

    Delegates to :func:`~toolguard.tool_spec.payload_key`, falling back to
    :data:`~toolguard.constants.DEFAULT_COMMAND_PAYLOAD_KEY` for a governed
    tool with no registry entry -- ``governed_tools`` accepts any name.
    """
    if tool_name in KNOWN_TOOL_NAMES:
        return _tool_payload_key(tool_name)
    return DEFAULT_COMMAND_PAYLOAD_KEY


def _governed_tool_verdict(
    tool_name: str, governed_tools: List[str]
) -> Optional[RuntimeVerdict]:
    """
    Return the short-circuit verdict for *tool_name* against *governed_tools*,
    or ``None`` to continue resolving it normally.

    An EMPTY *governed_tools* is not "nothing configured to govern" -- every
    builtin tool populates :data:`~toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS`
    by construction, so empty means no built-in tool is registered: a
    corrupted installation, or an edited-down
    :data:`~toolguard.tool_spec._REGISTRY`. Denies every tool call in that
    case -- fails closed with a stated reason -- rather than reading it the
    same way as a genuinely ungoverned tool and auto-allowing everything,
    hard-denied commands included.

    Returns:
        A synthetic 'deny' verdict when *governed_tools* is empty, a
        synthetic 'allow' verdict when *tool_name* is absent from a
        non-empty *governed_tools*, or ``None`` when *tool_name* is governed
        and resolution should proceed.
    """
    if not governed_tools:
        return RuntimeVerdict(
            decision="deny",
            reason=(
                "No governed tools are configured: no built-in tools are "
                "registered. This is not a valid 'govern nothing' "
                "configuration -- it indicates a broken installation, so "
                "every tool call is refused rather than silently allowed. "
                "Reinstall toolguard or check the installed package."
            ),
        )
    if tool_name not in governed_tools:
        return RuntimeVerdict(
            decision="allow",
            reason=f"Not a governed tool (governed: {', '.join(governed_tools)})",
        )
    return None


def _resolve_event(
    tool_name: str,
    tool_input: Dict[str, Any],
    config,
    extended_syntax: bool,
) -> RuntimeVerdict:
    """
    Resolve a single hook event to a :class:`~toolguard.config_types.RuntimeVerdict`,
    read-only.

    Adds only the parts :func:`main` owns on top of the shared decision
    primitive -- the governed-tool check and the empty-input guard -- and then
    delegates the actual resolution to :func:`toolguard.api.decide`, the same
    side-effect-free primitive that backs the replay harness and other
    tooling. ``decide`` reaches the same underlying resolver functions
    :func:`main`'s own handlers call directly, so delegating here rather than
    re-copying that dispatch makes the ``--eval`` decision match the live
    hook's by construction. No logging, divergence checks, or auto-migration
    happen here, and ``no_match_fallback`` is resolved entirely inside
    ``decide`` -- there is no separate reason-rewrite step here to keep in sync.

    The returned verdict's ``additional_context`` carries the winning rule's
    ``additionalContext`` enrichment, so ``--eval`` (whose whole purpose is
    previewing what the live hook would do) doesn't silently omit a real
    output field. The three synthetic guard verdicts short-circuiting this
    function -- empty registry and ungoverned tool, both from
    :func:`_governed_tool_verdict`, and missing target below -- have no
    matched rule and leave every optional field at
    :class:`~toolguard.config_types.RuntimeVerdict`'s defaults.

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
    verdict = _governed_tool_verdict(tool_name, governed_tools)
    if verdict is not None:
        return verdict

    if tool_name in FILE_PATH_TOOLS:
        key = _tool_payload_key(tool_name)
    else:
        key = _command_target_key(tool_name)
    target = tool_input.get(key, "")
    if not target:
        return RuntimeVerdict(
            decision="deny", reason=f"No {key} provided in tool input"
        )

    return decide(config, tool_name, target, extended_syntax)


def _run_eval_mode() -> None:
    """
    Handle ``toolguard --eval``: read one hook event on stdin, resolve it
    read-only, and print the JSON permissionDecision to stdout -- on success
    and on an internal error alike, via :func:`_emit_decision`. The
    security-audit skill's ``--eval`` probe (see
    ``.claude/skills/toolguard-security-audit/SKILL.md``'s "How the floor is
    checked" section) reads ``hookSpecificOutput.permissionDecision`` from
    stdout only, so an error branch that produced no verdict at all would
    yield no result instead of the deny it was meant to prove -- the same
    fail-open class :func:`main` itself guards against.

    No logging, divergence checks, or auto-migration are performed, so probing
    a project's configuration never mutates the project or writes to its logs
    -- :func:`create_hook_output` is used directly here rather than
    :func:`_finalize_output`, so no fault buffer is drained or implied.
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
        _emit_decision(create_hook_output(verdict))
    except json.JSONDecodeError as e:
        _emit_decision(
            create_hook_output(
                RuntimeVerdict(
                    decision="deny", reason=f"Failed to parse hook input: {str(e)}"
                )
            )
        )
    except ValueError as e:
        _emit_decision(
            create_hook_output(
                RuntimeVerdict(decision="deny", reason=f"Invalid hook input: {str(e)}")
            )
        )
    except Exception as e:
        _emit_decision(
            create_hook_output(
                RuntimeVerdict(
                    decision="deny", reason=f"Unexpected error in hook: {str(e)}"
                )
            )
        )


def _print_not_a_standalone_command_message(reporter: Reporter) -> None:
    """Report the friendly explanation for a stray manual/probing invocation."""
    reporter.notice(
        "toolguard: this is a Claude Code PreToolUse hook, not a standalone command.\n"
        "It reads a JSON hook event on stdin and is invoked automatically by Claude.\n"
        "To smoke-test: "
        'printf \'{"tool_name":"Bash","tool_input":{"command":"ls -la"},'
        '"hook_event_name":"PreToolUse"}\' | toolguard'
    )


def _warn_if_settings_path_override(reporter: Reporter) -> None:
    """
    Warn when ``CLAUDE_SETTINGS_PATH`` puts toolguard in single-file mode.

    ``CLAUDE_SETTINGS_PATH`` makes toolguard read one settings file for every
    directory, bypassing the whole hierarchy. As a persistently-exported shell
    variable it can silently let one project's config govern the entire
    machine (and, if that config is fail-closed takeover, lock it out), so the
    bypass must never be invisible.
    """
    settings_path_override = ambient.env_var("CLAUDE_SETTINGS_PATH")
    if not settings_path_override:
        return
    reporter.warning(
        f"CLAUDE_SETTINGS_PATH is set ({settings_path_override}). Toolguard is "
        "in single-file mode: the configuration hierarchy is BYPASSED -- only "
        "this file and its adjacent toolguard_hook.toml govern every directory.",
        "If this is unintended, unset CLAUDE_SETTINGS_PATH.",
    )


def _log_config_discovery(config, env_config: Dict[str, Any]) -> None:
    """
    Emit a config-discovery diagnostic when the discovered levels changed.

    Writes "discovered N config levels: <level: path>, ..." via
    :func:`log_discovery` (see its docstring for the change-detection
    mechanism and why toolguard needs one at all).

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

    On a cross-level ``takeover_mode.enabled`` disagreement, ``enabled`` is
    already fail-safe OFF; the conflict is recorded to the conflict log and a
    takeover warning is surfaced. The downstream path is already the safe one
    (native prompts active).

    Args:
        takeover: The resolved :class:`~toolguard.config.TakeoverConfig`.
        log_dir: Directory for the warning/conflict logs, or None (no-op).
    """
    if not log_dir:
        return
    if takeover.enabled:
        issue_takeover_warning(to_stdout=True)
        return

    if takeover.conflict is None:
        return
    _log_takeover_enabled_conflict(takeover.conflict, log_dir)
    message, _corrective = describe_takeover_conflict(takeover.conflict)
    issue_takeover_warning(to_stdout=True, conflict_message=message)


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
    Check for config divergence, auto-migrating when configured.

    :func:`check_and_warn_divergence` detects divergence and prints an immediate
    stderr notice; this function writes the structured error-log entry when a new
    warning is due.

    Args:
        config: The resolved configuration.
        env_config: Environment configuration dict (for ``log_dir``).
        takeover_dict: Takeover settings in the plain-dict form these clients take.
    """
    log_dir = env_config.get("log_dir")
    if not log_dir:
        return
    project_root = config.project_root
    if project_root is None:
        return

    divergence = check_and_warn_divergence(project_root, takeover_dict)
    if divergence.warning_message is not None:
        log_warning(divergence.warning_message, divergence.corrective_steps, log_dir)
    if not divergence.divergent_patterns:
        return

    config_sync = config.config_sync_settings()
    if config_sync["auto_migrate"]:
        run_auto_migration(project_root, dict(config_sync), takeover_dict)


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

    Identical for file-path tools and command tools, so both call this. An
    'ask' is recorded under ``note`` (it is not a violation) with the full
    reason text -- never split, so it carries no fabrication risk regardless
    of the reason's shape. A deny records the violated rule from
    ``verdict.matched_rule`` via :func:`_reason_suffix_or_placeholder`, keyed
    off ``verdict.fallback_kind`` (see that function's docstring for the
    escape-hatch/placeholder mechanism). Unlike the allow side, when
    ``verdict.matched_rule`` is ``None`` and ``verdict.fallback_kind`` is
    also ``None``, the full reason is used (not ``None``) -- this covers
    reasons like ``"No commands to evaluate"`` that never named a rule at
    all.

    Args:
        verdict: The resolved 'ask' or deny verdict. ``fallback_kind`` drives
            :func:`_reason_suffix_or_placeholder`'s classification (the
            'ask' branch instead uses ``reason`` verbatim as the log note).
            ``provenance`` is rendered via :func:`_provenance_brief`,
            suppressed the same way as ``matched_rule`` when
            ``fallback_kind`` names a fallback escape hatch (never paired
            with a rule that did not actually decide the verdict), and
            naturally absent for a hard deny (pooled across levels, no
            single provenance).
        log_target: What is being logged -- a command, or ``Tool(path)``.
        agent_info: Agent identification string.
        env_config: Environment configuration dict.
        permission_mode: Claude Code's own permission mode, recorded on the
            log entry for diagnosis only (see :func:`main`).
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
    # record beats a false one when fallback_kind names a fallback escape
    # hatch rather than a matched rule. Provenance is suppressed the same way
    # (see the Args docstring above).
    suffix = _reason_suffix_or_placeholder(
        verdict.fallback_kind,
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

    Resolves the file path permission via the more-specific-wins level
    cascade. No early "no allow configured" short-circuit here: an entirely
    unconfigured tool resolves to 'ask' and a configured-but-non-matching tool
    resolves per ``no_match_fallback`` -- both are decided centrally inside
    ``resolve_file_path_permission_detailed`` /
    ``permission_resolution.resolve_file_path_permission``.

    Args:
        tool_name: The file tool being invoked.
        tool_input: The tool input dict (read for ``file_path``).
        config: The resolved configuration.
        env_config: Environment configuration dict.
        agent_info: Agent identification string.
        permission_mode: Claude Code's own permission mode, recorded on the
            log entry for diagnosis only (see :func:`main`).

    Returns:
        The resolved :class:`~toolguard.config_types.RuntimeVerdict`.
    """
    key = _tool_payload_key(tool_name)
    file_path = tool_input.get(key, "")
    if not file_path:
        log_command(
            LogRecord(
                command_str=f"{tool_name}()",
                status="refused",
                violated_rules=[f"no {key} provided"],
                extra_info=agent_info,
                permission_mode=permission_mode,
            ),
            config=env_config,
        )
        return RuntimeVerdict(
            decision="deny", reason=f"No {key} provided in tool input"
        )

    extended_syntax = env_config.get("extended_syntax", True)
    result = resolve_file_path_permission_detailed(
        tool_name, file_path, config, extended_syntax
    )
    log_target = f"{tool_name}({file_path})"

    if result.decision == "allow":
        # Conflict: a more-specific allow overrode a less-specific deny. A
        # file-path result carries 0 or 1 overrides in this always-a-list
        # field, so this loop runs 0 or 1 times.
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
    tool_name: str,
    tool_input: Dict[str, Any],
    config,
    env_config: Dict[str, Any],
    agent_info: str,
    permission_mode: Optional[str],
) -> RuntimeVerdict:
    """
    Resolve and log a command tool event (Bash, MCP terminals).

    Command tools all resolve against the Bash permission patterns. No early
    "no allow configured" short-circuit here: an entirely unconfigured Bash
    resolves to 'ask' and a configured-but-non-matching Bash resolves per
    ``no_match_fallback`` (default 'ask'; 'deny' fails closed;
    'allow_with_warning' -- or its deprecated 'warn_deny' alias -- auto-allows
    with a warning; 'allow' -- or its 'allow_with_no_warnings' alias --
    auto-allows with no warning) -- all decided centrally inside
    ``resolve_bash_permission_detailed`` / ``permission_resolution.resolve_command_permission``.

    Resolution is more-specific-wins: each sub-command of a compound command
    cascades independently through the levels; the compound is allowed only if
    all are (a governed config file that failed to parse can still clamp an
    all-allow result to 'ask' afterward). The unoverridable ``[hard_deny]``
    pool is checked first per sub-command, so a compound is hard-denied if any
    sub-command is hard-denied.

    Args:
        tool_name: The command tool being invoked -- names the ``tool_input``
            key via :func:`_command_target_key`, since not every command tool
            necessarily shares Bash's ``'command'`` key.
        tool_input: The tool input dict.
        config: The resolved configuration.
        env_config: Environment configuration dict.
        agent_info: Agent identification string.
        permission_mode: Claude Code's own permission mode, recorded on the
            log entry for diagnosis only (see :func:`main`).

    Returns:
        The resolved :class:`~toolguard.config_types.RuntimeVerdict`.
    """
    key = _command_target_key(tool_name)
    command = tool_input.get(key, "")
    if not command:
        log_command(
            LogRecord(
                command_str=command,
                status="refused",
                violated_rules=[f"no {key} provided"],
                extra_info=agent_info,
                permission_mode=permission_mode,
            ),
            config=env_config,
        )
        return RuntimeVerdict(
            decision="deny", reason=f"No {key} provided in tool input"
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


def _resolve_reporter_log_dir(env_config: Optional[Dict[str, Any]]) -> Optional[Path]:
    """
    Resolve a :class:`Reporter`'s log directory, degrading to None on failure.

    Thin wrapper over :func:`toolguard.log_writer.resolve_log_dir` so a
    malformed resolution never takes down reporting itself -- see
    :func:`main`, which calls this twice: once before ``env_config`` is
    known (coarse fallback) and again once it is (refined).
    """
    try:
        return resolve_log_dir(None, env_config)
    except Exception:
        return None


def main() -> None:
    """
    Main hook entry point: parse the piped hook event, resolve a permission
    decision against the configuration hierarchy, log it, and emit the JSON
    decision Claude Code expects.

    Exit codes:
    - 0 in the normal case: a well-formed JSON decision is always printed to
      stdout first, including from every internal error this function catches.
      The exceptions are the stray-invocation paths -- ``--help`` (argparse
      exits 0), a TTY stdin, and, on the non-``--eval`` path,
      :class:`EmptyStdinError` -- which print an explanation instead and exit
      0 with no JSON decision at all, since none of these is a real hook call
      from Claude Code. Under ``--eval``, an empty piped stdin still exits 0
      but with a JSON deny decision, via ``_run_eval_mode``'s own ``except
      ValueError`` (:class:`EmptyStdinError` is a ``ValueError`` subclass).
    - 2 if writing that JSON to stdout itself raises (see :func:`_emit_decision`)
      -- the one case with no decision left to deliver, so the host's own
      blocking signal is what's left -- or from argparse's own usage-error
      path on a malformed CLI invocation, at the ``parse_known_args`` call
      below, before any other logic in this function runs.
    """
    parser = _build_hook_argparser()
    # parse_known_args() is used instead of parse_args() so the hook still
    # works when invoked via the test runner, which places test names in
    # sys.argv -- those unknown args are silently discarded rather than
    # aborting. --help still exits 0 via argparse.
    args, _ = parser.parse_known_args()

    # One Reporter for the whole invocation -- see toolguard/error_reporter.py's
    # module docstring for why it owns both the resolved log directory and the
    # Claude-facing fault buffer as instance state. log_dir starts unresolved;
    # the TTY guard below reports through it with that unresolved default.
    reporter = Reporter()

    # Interactive guard: if a human runs 'toolguard' in a terminal without piping
    # a JSON event, do not block on stdin. Print a brief explanation and exit.
    # Claude always pipes JSON (not a TTY), so this guard never fires in real use.
    # Placed before the --eval branch so 'toolguard --eval' typed by hand (no
    # piped stdin) shows the message instead of hanging on stdin.read().
    if sys.stdin.isatty():
        _print_not_a_standalone_command_message(reporter)
        sys.exit(0)

    # Read-only evaluation mode (--eval): resolve one piped event and print the
    # verdict without logging, divergence checks, or auto-migration. Used by
    # the cross-project security-audit skill to probe a project's safety floor
    # without mutating it.
    if args.eval_mode:
        _run_eval_mode()
        return

    # error_reporter.active(reporter) registers *reporter* as the target the
    # config-layer modules' report_notice/report_warning calls resolve --
    # deep call chains make threading a Reporter through every signature
    # impractical, so an ambient registry stands in instead (see that
    # module's docstring for the full rationale).
    # ambient.active binds home, cwd and the environment for the block below.
    # Both bindings wrap the whole try/except, handlers included, and release on
    # the way out.
    with ambient.active(ambient.resolve()), error_reporter.active(reporter):
        try:
            # Coarse log-dir fallback, resolved before env_config is known,
            # so get_env_config()'s own report_warning call sites (necessarily
            # before any config-derived resolution exists) have somewhere to
            # log to, not just stderr.
            reporter.log_dir = _resolve_reporter_log_dir(None)

            env_config = get_env_config()

            # Refine the SAME reporter's log_dir now that env_config is
            # known -- no new Reporter, no buffer to reconcile.
            reporter.log_dir = _resolve_reporter_log_dir(env_config)

            # Parse hook input first to get cwd
            hook_data = parse_hook_input()

            tool_name = hook_data["tool_name"]
            tool_input = hook_data["tool_input"]
            cwd = hook_data.get("cwd", None)

            # Obtain the resolved configuration once via the public abstraction.
            # All file discovery, parsing, and format/location decisions live in
            # the config module; the hook only consumes semantic accessors from
            # here on.
            config = load_configuration(cwd)

            _warn_if_settings_path_override(reporter)
            _log_config_discovery(config, env_config)

            # Run startup validation, reusing the loaded config.
            _run_startup_validation(env_config, cwd, config)

            takeover_dict = _resolve_takeover_mode(config, env_config)
            _run_divergence_check(config, env_config, takeover_dict)

            governed_tools = list(config.governed_tools())

            governed_verdict = _governed_tool_verdict(tool_name, governed_tools)
            if governed_verdict is not None:
                output = _finalize_output(governed_verdict, reporter)
                _emit_decision(output)
                sys.exit(0)

            agent_info = _agent_info_for(hook_data)

            # Claude Code's own permission_mode (e.g. 'default', 'plan', an auto
            # mode) is recorded alongside the decision, purely for diagnosis --
            # it never affects the verdict itself.
            permission_mode = hook_data.get("permission_mode")

            # File path tools (Read, Write, Edit) and command tools (Bash, MCP
            # terminals) differ only in how the target is extracted and
            # resolved; both return the same RuntimeVerdict shape.
            if tool_name in FILE_PATH_TOOLS:
                verdict = _handle_file_path_tool(
                    tool_name,
                    tool_input,
                    config,
                    env_config,
                    agent_info,
                    permission_mode,
                )
            else:
                verdict = _handle_command_tool(
                    tool_name,
                    tool_input,
                    config,
                    env_config,
                    agent_info,
                    permission_mode,
                )

            output = _finalize_output(verdict, reporter)
            _emit_decision(output)
            sys.exit(0)

        except EmptyStdinError:
            # A stray manual/probing invocation (see EmptyStdinError's own
            # docstring) -- treat it exactly like the TTY guard: a friendly
            # explanation, no crash report.
            _print_not_a_standalone_command_message(reporter)
            sys.exit(0)

        except json.JSONDecodeError as e:
            # Deliver the deny decision the same way the success path does:
            # on stdout (see :func:`_emit_decision` for why an exit-0 path
            # with no usable decision is a fail-open, not a neutral no-op).
            error_reason = f"Failed to parse hook input: {str(e)}"
            crash_context = _build_crash_context(locals())
            crash_context["raw_stdin"] = e.doc
            log_crash(e, crash_context, caught_as="json.JSONDecodeError")
            _report_crash_fault(reporter, error_reason)
            output = _finalize_output(
                RuntimeVerdict(decision="deny", reason=error_reason), reporter
            )
            _emit_decision(output)
            sys.exit(0)

        except ValueError as e:
            # Validation error - deny, delivered on stdout (see above).
            error_reason = f"Invalid hook input: {str(e)}"
            log_crash(e, _build_crash_context(locals()), caught_as="ValueError")
            _report_crash_fault(reporter, error_reason)
            output = _finalize_output(
                RuntimeVerdict(decision="deny", reason=error_reason), reporter
            )
            _emit_decision(output)
            sys.exit(0)

        except Exception as e:
            # The catch-all exists to fail closed on anything unforeseen, so
            # its deny must reach Claude the same way every other decision
            # does: on stdout (see above).
            error_reason = f"Unexpected error in hook: {str(e)}"
            log_crash(
                e, _build_crash_context(locals()), caught_as="unexpected Exception"
            )
            _report_crash_fault(reporter, error_reason)
            output = _finalize_output(
                RuntimeVerdict(decision="deny", reason=error_reason), reporter
            )
            _emit_decision(output)
            sys.exit(0)


if __name__ == "__main__":
    main()
