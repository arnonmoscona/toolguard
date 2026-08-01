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
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from toolguard.auto_migrate import run_auto_migration
from toolguard.config import load_configuration
from toolguard.config_divergence import check_and_warn_divergence
from toolguard.env_config import get_env_config
from toolguard.error_log import log_conflict, log_crash, log_error, log_warning
from toolguard.log_writer import log_command, log_discovery
from toolguard.resolve import (
    _anchor_file_pattern,  # noqa: F401  re-exported for backwards compat
    _check_file_path_hard_deny,  # noqa: F401  re-exported for backwards compat
    _decide_file_path_at_level_detailed,  # noqa: F401  re-exported for backwards compat
    _match_file_path_pattern,  # noqa: F401  re-exported for backwards compat
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)
from toolguard.constants import FILE_TOOLS
from toolguard.session_warnings import issue_takeover_warning
from toolguard.subagent import identify_current_agent

# Tools that operate on file paths (use GLOB matching).  Alias of the shared
# constant, kept under this name for backward compatibility with importers
# (e.g. toolguard.tools.decision, tests).
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


def create_hook_output(
    decision: str, reason: str, additional_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create hook output in the format expected by Claude Code.

    Args:
        decision: Permission decision ('allow', 'ask', or 'deny')
        reason: Human-readable reason for the decision
        additional_context: The winning rule's ``additionalContext`` enrichment
            (TOO-19 Phase 1) to inject back to Claude, or ``None``/empty when
            there is nothing to add. Only decision call sites that have a
            matched rule pass this -- error/guard paths (parse failure, no
            command provided, ungoverned tool, etc.) have no matched rule and
            always use the default.

    Returns:
        Dictionary formatted for JSON output to Claude Code. The
        ``"additionalContext"`` key is present inside ``hookSpecificOutput``
        ONLY when ``additional_context`` is a non-empty string -- omitted
        entirely (not set to ``null``) otherwise, so existing consumers that
        don't know about the field see no change in shape.
    """
    output: Dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if additional_context:
        output["hookSpecificOutput"]["additionalContext"] = additional_context
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


#: Marker substrings (TOO-19 code review m6) that identify an 'allow' reason
#: as having come from the ``allow_with_warning`` value of one of the two
#: fallback settings, rather than from an explicit rule. Both markers are
#: exact, already-tested wording embedded verbatim in the reason strings
#: produced by config.py's ``resolved_no_match_fallback`` path and
#: compound.py's ``undecidable_fallback`` ask-floor/segment paths (see
#: test_configuration.py / test_compound.py) -- a substring containment
#: check, not the prefix/suffix extraction m3 flagged as fragile, since
#: nothing here needs to be RECOVERED from the reason, only detected.
_ALLOW_WITH_WARNING_MARKERS = (
    "no_match_fallback=allow_with_warning",
    "undecidable_fallback=allow_with_warning",
)


def _log_fallback_allow_warning(reason: str, log_dir) -> None:
    """
    Route an ``allow_with_warning``-fallback 'allow' decision to the WARNING
    log stream (TOO-19 code review m6).

    ``docs/configuration.md`` promises that ``allow_with_warning`` will
    "allow the command but log a warning" for BOTH ``no_match_fallback`` and
    ``undecidable_fallback``. Previously that promise was kept only in the
    permission-decision ``reason`` string (visible in the resolution log and
    the permission prompt) -- it never reached
    :func:`toolguard.error_log.log_warning`'s dedicated WARNING stream. This
    detects either fallback setting's marker wording in *reason* and, when
    found, writes the warning stream entry too. A no-op when *log_dir* is
    unresolved or the reason carries neither marker (the common case: an
    explicit allow rule matched).

    Args:
        reason: The permission-decision reason string for an 'allow' decision.
        log_dir: Directory for the warning log, or None (no-op).
    """
    if not log_dir:
        return
    if not any(marker in reason for marker in _ALLOW_WITH_WARNING_MARKERS):
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


_COMPOUND_MATCH_PATTERN = re.compile(r"All \d+ sub-commands allowed: \[(.+)\]")


def _parse_compound_match_details(reason: str):
    """
    Parse per-sub-command match details from a compound command's allow reason.

    Args:
        reason: The reason string from check_compound_permission, e.g.
                "All 2 sub-commands allowed: [git status -> git *, git log -> git *]"

    Returns:
        List of (sub_command, matched_rule) tuples, or None if not a compound match reason.
    """
    m = _COMPOUND_MATCH_PATTERN.match(reason)
    if not m:
        return None

    details = []
    for part in m.group(1).split(", "):
        if " -> " in part:
            cmd, rule = part.rsplit(" -> ", 1)
            details.append((cmd.strip(), rule.strip()))
    return details if details else None


def _log_allowed_command(
    command: str,
    reason: str,
    agent_info: str,
    env_config: dict,
    permission_mode: Optional[str] = None,
    additional_context: Optional[str] = None,
) -> None:
    """
    Log an allowed command, handling compound commands by logging each sub-command separately.

    For simple commands or single-command results, logs one entry with the matched rule.
    For compound commands where check_compound_permission returns per-sub-command details,
    logs a separate entry for each sub-command with its own matched rule.

    Args:
        command: The original command string
        reason: The allow reason from permission checking
        agent_info: Agent identification string
        env_config: Environment configuration dict
        permission_mode: Claude Code's own ``permission_mode`` from the hook input,
            if present -- recorded for diagnosis only, see ``log_command``.
        additional_context: The accumulated ``additionalContext`` enrichment
            (TOO-19 Phase 1) for the WHOLE compound command, or ``None``. It is
            not attributable to a single sub-command (it may combine several
            sub-commands' contexts, see ``compound.py::_accumulate_contexts``),
            so it is recorded on every logged sub-command entry the same way
            the hook injects one accumulated block for the whole command.
    """
    compound_details = _parse_compound_match_details(reason)
    if compound_details:
        # Compound command: log each sub-command separately
        for sub_cmd, matched_rule in compound_details:
            log_command(
                sub_cmd,
                "executed",
                matched_rule=matched_rule,
                extra_info=agent_info,
                config=env_config,
                permission_mode=permission_mode,
                additional_context=additional_context,
            )
    else:
        # Simple command: extract matched rule from reason
        matched_rule = reason.split(": ", 1)[1] if ": " in reason else None
        log_command(
            command,
            "executed",
            matched_rule=matched_rule,
            extra_info=agent_info,
            config=env_config,
            permission_mode=permission_mode,
            additional_context=additional_context,
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
) -> Tuple[str, str, Optional[str]]:
    """
    Resolve a single hook event to a ``(decision, reason, additional_context)``
    triple, READ-ONLY.

    This adds only the parts :func:`main` owns on top of the shared decision
    primitive -- the governed-tool check and the empty-input guard -- and then
    delegates the actual resolution to :func:`toolguard.tools.decision.decide`, the
    single side-effect-free primitive that also backs the replay harness and other
    tooling.  Delegating (rather than re-copying the file-vs-command dispatch and
    the ``[hard_deny]`` handling) makes the ``--eval`` verdict identical to the live
    hook's by construction.  No logging, divergence checks, or auto-migration
    happen here.  ``no_match_fallback`` (including the TOO-15 ``allow_with_warning``
    auto-allow, whose deprecated legacy alias is ``warn_deny``) is resolved entirely
    inside :func:`~toolguard.tools.decision.decide` via the shared config layer --
    there is no separate reason-rewrite step here or in :func:`main` to keep in sync.

    TOO-19 Phase 1: the third element carries the winning rule's
    ``additionalContext`` enrichment, so ``--eval`` (whose whole purpose is
    previewing what the live hook would do) doesn't silently omit a real output
    field. The two synthetic guard verdicts above (ungoverned tool, missing
    target) have no matched rule and always report ``None``.

    Args:
        tool_name: The tool being invoked (e.g. ``'Bash'``, ``'Read'``).
        tool_input: The tool input dict (carrying ``command`` or ``file_path``).
        config: The resolved configuration to evaluate against.
        extended_syntax: Whether extended (regex/glob) prefixes are honoured.

    Returns:
        A ``(decision, reason, additional_context)`` triple where decision is
        ``'allow'``, ``'deny'``, or ``'ask'``, and ``additional_context`` is the
        matched rule's enrichment text or ``None``.
    """
    # Local import: toolguard.tools.decision imports FILE_PATH_TOOLS from this
    # module, so importing decide() at module top-level would be a circular import.
    # This documented cycle is the sanctioned exception to the no-local-imports rule.
    from toolguard.tools.decision import decide

    governed_tools = list(config.governed_tools())
    if tool_name not in governed_tools:
        return (
            "allow",
            f"Not a governed tool (governed: {', '.join(governed_tools)})",
            None,
        )

    if tool_name in FILE_PATH_TOOLS:
        target = tool_input.get("file_path", "")
        if not target:
            return "deny", "No file_path provided in tool input", None
    else:
        target = tool_input.get("command", "")
        if not target:
            return "deny", "No command provided in tool input", None

    result = decide(config, tool_name, target, extended_syntax)
    return result.verdict, result.reason, result.additional_context


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
        decision, reason, additional_context = _resolve_event(
            tool_name, tool_input, config, extended_syntax
        )
        print(json.dumps(create_hook_output(decision, reason, additional_context)))
    except json.JSONDecodeError as e:
        output = create_hook_output("deny", f"Failed to parse hook input: {str(e)}")
        print(json.dumps(output), file=sys.stderr)
    except ValueError as e:
        output = create_hook_output("deny", f"Invalid hook input: {str(e)}")
        print(json.dumps(output), file=sys.stderr)
    except Exception as e:
        output = create_hook_output("deny", f"Unexpected error in hook: {str(e)}")
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

        # Single-file override footgun (TOO-15): CLAUDE_SETTINGS_PATH makes toolguard
        # read ONE settings file for EVERY directory, bypassing the whole hierarchy. As
        # a persistently-exported shell variable it silently lets one project's config
        # govern the entire machine (and, if that config is fail-closed takeover, can
        # lock it out). Surface it on stderr so the bypass is never invisible.
        settings_path_override = os.environ.get("CLAUDE_SETTINGS_PATH")
        if settings_path_override:
            print(
                "[TOOLGUARD WARNING] CLAUDE_SETTINGS_PATH is set "
                f"({settings_path_override}). Toolguard is in single-file mode: the "
                "configuration hierarchy is BYPASSED -- only this file and its adjacent "
                "toolguard_hook.toml govern every directory. If this is unintended, "
                "unset CLAUDE_SETTINGS_PATH.",
                file=sys.stderr,
            )

        # Emit a config-discovery diagnostic to the resolution log when the
        # discovered levels changed since the last recorded entry for this
        # project root (TOO-8 Phase 4, M2; TOO-19): "discovered N config
        # levels: <level: path>, ...". toolguard is a fresh process on every
        # tool call, so there is no in-process "once per session" -- the
        # change-detecting JSONL log inside log_discovery is the guard
        # instead, and it is a no-op (writes nothing) when nothing changed.
        disco_log_dir = env_config.get("log_dir")
        if disco_log_dir:
            log_discovery(
                list(config.describe_levels()),
                disco_log_dir,
                str(env_config.get("project_root", "")),
            )

        # Run startup validation (once per session), reusing the loaded config.
        _run_startup_validation(env_config, cwd, config)

        # Resolve takeover mode configuration and issue warning if enabled
        takeover = config.takeover_mode()
        if takeover.enabled:
            log_dir = env_config.get("log_dir")
            if log_dir:
                issue_takeover_warning(log_dir, to_stdout=True)
        elif takeover.conflict is not None:
            # Cross-level disagreement on takeover_mode.enabled (TOO-8 Phase 5):
            # enabled is already fail-safe OFF. Record the conflict to the
            # conflict log and surface a once-per-session warning. The downstream
            # path is already the safe one (native prompts active).
            log_dir = env_config.get("log_dir")
            if log_dir:
                global _takeover_conflict_logged
                if not _takeover_conflict_logged:
                    _takeover_conflict_logged = True
                    _log_takeover_enabled_conflict(takeover.conflict, log_dir)
                    issue_takeover_warning(log_dir, to_stdout=True)

        # Divergence/auto-migration tooling still consumes a plain dict; build it
        # from the resolved TakeoverConfig so those clients stay unchanged.
        takeover_dict = {
            "enabled": takeover.enabled,
            "ignored_allow_patterns": list(takeover.ignored_allow_patterns),
            "additional_ignored_patterns": list(takeover.additional_ignored_patterns),
            "no_match_fallback": takeover.no_match_fallback,
        }

        # Check for config divergence (once per session)
        global _divergence_check_done
        if not _divergence_check_done:
            _divergence_check_done = True
            log_dir = env_config.get("log_dir")
            if log_dir:
                project_root = config.project_root
                if project_root is not None:
                    divergent_patterns = check_and_warn_divergence(
                        project_root, log_dir, takeover_dict
                    )

                    # Auto-migration: consolidate permissions if configured
                    if divergent_patterns:
                        config_sync = config.config_sync_settings()

                        if config_sync["auto_migrate"]:
                            # Auto-migration enabled - run it
                            run_auto_migration(
                                project_root, log_dir, dict(config_sync), takeover_dict
                            )
                        # else: warning already shown by check_and_warn_divergence

        # Resolve the list of governed tools via the config abstraction
        governed_tools = list(config.governed_tools())

        # Only handle tools in the governed list
        if tool_name not in governed_tools:
            # Not a governed tool - allow (other hooks handle other tools)
            output = create_hook_output(
                "allow", f"Not a governed tool (governed: {', '.join(governed_tools)})"
            )
            print(json.dumps(output))
            sys.exit(0)

        # Identify current agent context (used for logging)
        transcript_path = hook_data.get("transcript_path", "")
        agent_context = identify_current_agent(transcript_path)
        agent_info = (
            agent_context["subagent_name"]
            if agent_context["agent_type"] == "subagent"
            else "main"
        )

        # Claude Code's own permission_mode (e.g. 'default', 'plan', an auto
        # mode) is recorded alongside the decision, purely for diagnosis -- it
        # never affects the verdict itself. See log_command's docstring.
        permission_mode = hook_data.get("permission_mode")

        # Handle file path tools (Read, Write, Edit)
        if tool_name in FILE_PATH_TOOLS:
            file_path = tool_input.get("file_path", "")
            if not file_path:
                output = create_hook_output(
                    "deny", "No file_path provided in tool input"
                )
                log_command(
                    f"{tool_name}()",
                    "refused",
                    ["no file_path provided"],
                    extra_info=agent_info,
                    config=env_config,
                    permission_mode=permission_mode,
                )
                print(json.dumps(output))
                sys.exit(0)

            # Resolve file path permission via more-specific-wins level cascade.
            # No early "no allow configured" short-circuit here (TOO-15): an
            # entirely unconfigured tool resolves to 'ask' and a configured-but-
            # non-matching tool resolves per no_match_fallback -- both are
            # decided centrally inside resolve_file_path_permission_detailed /
            # Configuration.resolve_permission_detailed, so the hook and
            # toolguard.tools.decision.decide() cannot drift apart.
            extended_syntax = env_config.get("extended_syntax", True)
            file_result = resolve_file_path_permission_detailed(
                tool_name, file_path, config, extended_syntax
            )
            decision, reason, override, additional_context = (
                file_result.decision,
                file_result.reason,
                file_result.override,
                file_result.additional_context,
            )

            # Log the decision
            log_target = f"{tool_name}({file_path})"
            if decision == "allow":
                # Conflict: a more-specific allow overrode a less-specific deny.
                _log_conflict_override(log_target, override, env_config.get("log_dir"))
                _log_fallback_allow_warning(reason, env_config.get("log_dir"))
                matched_rule = reason.split(": ", 1)[1] if ": " in reason else None
                log_command(
                    log_target,
                    "executed",
                    matched_rule=matched_rule,
                    extra_info=agent_info,
                    config=env_config,
                    permission_mode=permission_mode,
                    additional_context=additional_context,
                )
            elif decision == "ask":
                log_command(
                    log_target,
                    "ask",
                    note=reason,
                    extra_info=agent_info,
                    config=env_config,
                    permission_mode=permission_mode,
                    additional_context=additional_context,
                )
            else:
                violated_rules = [
                    reason.split(": ", 1)[1] if ": " in reason else reason
                ]
                log_command(
                    log_target,
                    "refused",
                    violated_rules,
                    extra_info=agent_info,
                    config=env_config,
                    permission_mode=permission_mode,
                    additional_context=additional_context,
                )

            output = create_hook_output(decision, reason, additional_context)
            print(json.dumps(output))
            sys.exit(0)

        # Handle command tools (Bash, MCP terminals)
        command = tool_input.get("command", "")
        if not command:
            output = create_hook_output("deny", "No command provided in tool input")
            log_command(
                command,
                "refused",
                ["no command provided"],
                extra_info=agent_info,
                config=env_config,
                permission_mode=permission_mode,
            )
            print(json.dumps(output))
            sys.exit(0)

        # Command tools (Bash, MCP terminals) all resolve against the Bash
        # permission patterns. No early "no allow configured" short-circuit here
        # (TOO-15): an entirely unconfigured Bash resolves to 'ask' and a
        # configured-but-non-matching Bash resolves per no_match_fallback (default
        # 'ask'; 'deny' fails closed; 'allow_with_warning' -- or its deprecated
        # 'warn_deny' alias -- auto-allows) -- both decided centrally inside
        # resolve_bash_permission_detailed / Configuration.resolve_permission_detailed
        # so the hook and toolguard.tools.decision.decide() cannot drift apart.
        # Resolve via more-specific-wins: each sub-command of a compound command
        # cascades independently through the levels; compound allowed iff all are.
        # The unoverridable [hard_deny] pool is checked FIRST per sub-command, so a
        # compound is hard-denied if ANY sub-command is hard-denied.
        extended_syntax = env_config.get("extended_syntax", True)
        hd_deny, hd_allow = config.hard_deny("Bash")

        bash_result = resolve_bash_permission_detailed(
            command, config, extended_syntax, hd_deny, hd_allow
        )
        decision, reason, bash_overrides, additional_context = (
            bash_result.decision,
            bash_result.reason,
            bash_result.overrides,
            bash_result.additional_context,
        )

        # Log the decision with agent identification
        if decision == "allow":
            # Conflict logging: any sub-command whose more-specific allow overrode
            # a less-specific deny is recorded to the conflict stream.
            conflict_log_dir = env_config.get("log_dir")
            for sub_command, override in bash_overrides:
                _log_conflict_override(sub_command, override, conflict_log_dir)
            _log_fallback_allow_warning(reason, conflict_log_dir)
            _log_allowed_command(
                command,
                reason,
                agent_info,
                env_config,
                permission_mode,
                additional_context,
            )
        elif decision == "ask":
            log_command(
                command,
                "ask",
                note=reason,
                extra_info=agent_info,
                config=env_config,
                permission_mode=permission_mode,
                additional_context=additional_context,
            )
        else:
            # Extract violated rule from reason for logging
            violated_rules = [reason.split(": ", 1)[1] if ": " in reason else reason]
            log_command(
                command,
                "refused",
                violated_rules,
                extra_info=agent_info,
                config=env_config,
                permission_mode=permission_mode,
                additional_context=additional_context,
            )

        # Create and output decision
        output = create_hook_output(decision, reason, additional_context)
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
        output = create_hook_output("deny", error_reason)
        print(json.dumps(output), file=sys.stderr)
        crash_context = _build_crash_context(locals())
        crash_context["raw_stdin"] = e.doc
        log_crash(e, crash_context, caught_as="json.JSONDecodeError")
        sys.exit(0)

    except ValueError as e:
        # Validation error - deny with error message
        error_reason = f"Invalid hook input: {str(e)}"
        output = create_hook_output("deny", error_reason)
        print(json.dumps(output), file=sys.stderr)
        log_crash(e, _build_crash_context(locals()), caught_as="ValueError")
        sys.exit(0)

    except Exception as e:
        # Unexpected error - deny and log
        error_reason = f"Unexpected error in hook: {str(e)}"
        output = create_hook_output("deny", error_reason)
        print(json.dumps(output), file=sys.stderr)
        print(f"Error: {error_reason}", file=sys.stderr)
        log_crash(e, _build_crash_context(locals()), caught_as="unexpected Exception")
        sys.exit(0)


if __name__ == "__main__":
    main()
