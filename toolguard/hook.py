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

import json
import re
import sys
from typing import Any, Dict, List, Tuple

from toolguard.auto_migrate import run_auto_migration
from toolguard.compound import resolve_compound_permission
from toolguard.patterns import PatternType, match_pattern, parse_pattern
from toolguard.permissions import check_hard_deny, make_command_level_decider
from toolguard.config import load_configuration
from toolguard.config_divergence import check_and_warn_divergence
from toolguard.env_config import get_env_config
from toolguard.error_log import log_warning
from toolguard.log_writer import log_command
from toolguard.normalization import expand_tilde
from toolguard.session_warnings import issue_takeover_warning
from toolguard.subagent import identify_current_agent

# Tools that operate on file paths (use GLOB matching)
FILE_PATH_TOOLS = {'Read', 'Write', 'Edit'}

# Tools that execute commands (use compound command parsing)
COMMAND_TOOLS = {'Bash', 'mcp__jetbrains__execute_terminal_command', 'mcp__local-tools__checked_bash'}

# Module-level flags to ensure checks run only once per session
_validation_done = False
_divergence_check_done = False


def _run_startup_validation(env_config: Dict[str, Any], start_dir: str = None, config=None) -> None:
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
    log_dir = env_config.get('log_dir')
    if not log_dir:
        project_root = config.project_root
        if project_root is None:
            return  # Can't log without log dir
        log_dir = project_root / 'logs'

    # The config module detects content-level issues and returns them; the hook
    # only decides where to log. No files are opened or parsed here.
    for issue in config.validation_issues():
        log_warning(issue.message, issue.corrective_steps, log_dir)


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
        ValueError: If required fields are missing
    """
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            raise ValueError('Empty input from stdin')

        data = json.loads(input_data)

        # Validate required fields
        required_fields = ['tool_name', 'tool_input', 'hook_event_name']
        for field in required_fields:
            if field not in data:
                raise ValueError(f'Missing required field: {field}')

        return data

    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f'Invalid JSON from stdin: {e.msg}', e.doc, e.pos)


def create_hook_output(decision: str, reason: str) -> Dict[str, Any]:
    """
    Create hook output in the format expected by Claude Code.

    Args:
        decision: Permission decision ('allow' or 'deny')
        reason: Human-readable reason for the decision

    Returns:
        Dictionary formatted for JSON output to Claude Code
    """
    return {
        'hookSpecificOutput': {
            'hookEventName': 'PreToolUse',
            'permissionDecision': decision,
            'permissionDecisionReason': reason,
        }
    }


def load_file_path_patterns(tool_name: str, start_dir: str = None, config=None) -> Tuple[List[str], List[str]]:
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


def _anchor_file_pattern(pattern: str, config, extended_syntax: bool) -> str:
    """
    Anchor a relative file-path permission pattern to the PROJECT ROOT.

    Per the project-root-relative-path rule, a relative file-path pattern (one not
    starting with ``/`` or ``~`` after any extended-syntax prefix) resolves against
    the project root regardless of which config level declared it. Absolute and
    ``~`` patterns are returned unchanged.

    Any extended-syntax prefix (``[glob]``/``[regex]``/``[native]``) is preserved:
    only the path body after the prefix is anchored. ``[regex]`` patterns are left
    untouched (a regex is not a path and must not be path-joined).

    Args:
        pattern: A file-path permission pattern (wrapper already stripped).
        config: The resolved :class:`~toolguard.config.Configuration`.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        The pattern with its path body anchored to the project root when relative.
    """
    prefix = ''
    body = pattern
    if extended_syntax:
        for known in ('[glob]', '[regex]', '[native]'):
            if pattern.startswith(known):
                prefix = known
                body = pattern[len(known):]
                break
    # A regex pattern is not a filesystem path; never path-join it.
    if prefix == '[regex]':
        return pattern
    return prefix + config.resolve_config_path(body)


def _match_file_path_pattern(pattern: str, expanded_path: str, extended_syntax: bool) -> bool:
    """
    Match a file path against a single pattern, respecting extended syntax prefixes.

    DEFAULT patterns are treated as GLOB (backwards compatible with existing behavior).
    Extended prefixes ([regex], [glob], [native]) are honored inside tool wrappers
    e.g. "Write([regex]/path/.*)" — the wrapper is stripped by the caller, and this
    function sees just "[regex]/path/.*".
    """
    pattern_type, actual_pattern = parse_pattern(pattern, extended_syntax)

    # For file paths, DEFAULT patterns use the same semantics as GLOB
    if pattern_type == PatternType.DEFAULT:
        pattern_type = PatternType.GLOB

    try:
        return match_pattern(pattern_type, actual_pattern, expanded_path)
    except (ValueError, TypeError):
        return False


def check_file_path_permission(
    file_path: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    extended_syntax: bool = True,
) -> Tuple[str, str]:
    """
    Check if a file path is permitted based on allow and deny patterns.

    Uses GLOB pattern matching by default (with proper globstar ** support via
    PurePath.full_match()). Extended syntax prefixes are honored when wrapped in
    the tool form, e.g. "Write([regex]...)", "Write([glob]...)", "Write([native]...)" —
    the tool wrapper is stripped before reaching this function.

    Args:
        file_path: The file path to check
        allow_patterns: List of patterns that allow access (may contain extended prefixes)
        deny_patterns: List of patterns that deny access (may contain extended prefixes)
        extended_syntax: If False, treat all patterns as plain glob

    Returns:
        Tuple of (decision, reason) where decision is 'allow' or 'deny'
    """
    # Expand tilde in file path for matching
    expanded_path = expand_tilde(file_path)

    # Check deny list first
    for pattern in deny_patterns:
        if _match_file_path_pattern(pattern, expanded_path, extended_syntax):
            return 'deny', f'Path matches deny pattern: {pattern}'

    # Check allow list
    for pattern in allow_patterns:
        if _match_file_path_pattern(pattern, expanded_path, extended_syntax):
            return 'allow', f'Path matches allow pattern: {pattern}'

    # Default: deny (not explicitly allowed)
    return 'deny', 'Path does not match any allow patterns'


def _decide_file_path_at_level(file_path, allow_patterns, deny_patterns, config, extended_syntax):
    """
    Decide a file path's outcome against ONE hierarchy level's patterns.

    Deny-first within the level. Relative patterns are anchored to the project
    root (see :func:`_anchor_file_pattern`) before matching. Returns ``None`` when
    neither list matches at this level, so the more-specific-wins cascade falls
    through to the next level.

    Args:
        file_path: The file path under evaluation.
        allow_patterns: This level's allow patterns (wrapper-free).
        deny_patterns: This level's deny patterns (wrapper-free).
        config: The resolved Configuration (provides project-root anchoring).
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        ``(decision, reason)`` when this level matches, else ``None``.
    """
    expanded_path = expand_tilde(file_path)

    for pattern in deny_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return 'deny', f'Path matches deny pattern: {pattern}'

    for pattern in allow_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return 'allow', f'Path matches allow pattern: {pattern}'

    return None


def _check_file_path_hard_deny(tool_name, file_path, config, extended_syntax):
    """
    Apply the unoverridable hard-deny rule to a file path, checked FIRST.

    The pooled ``[hard_deny]`` (deny, allow) patterns for ``tool_name`` are
    collected across ALL levels (see
    :meth:`~toolguard.config.Configuration.hard_deny`). The path is hard-denied
    when it matches any hard-deny ``deny`` pattern AND does NOT match a hard-deny
    ``allow`` carve-out. Relative patterns are anchored to the project root, the
    same as normal file-path patterns.

    Args:
        tool_name: 'Read', 'Write', or 'Edit'.
        file_path: The file path under evaluation.
        config: The resolved Configuration (provides hard_deny pool + anchoring).
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        ``('deny', reason)`` when the path is hard-denied, otherwise ``None`` so
        the caller falls through to the normal more-specific-wins cascade.
    """
    deny_patterns, allow_patterns = config.hard_deny(tool_name)
    if not deny_patterns:
        return None

    expanded_path = expand_tilde(file_path)

    matched_deny = None
    for pattern in deny_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            matched_deny = pattern
            break

    if matched_deny is None:
        return None

    # A hard-deny matched. An allow carve-out exempts the path from the hard deny.
    for pattern in allow_patterns:
        anchored = _anchor_file_pattern(pattern, config, extended_syntax)
        if _match_file_path_pattern(anchored, expanded_path, extended_syntax):
            return None

    return 'deny', f'Path matches hard_deny pattern: {matched_deny} (cannot be overridden)'


def resolve_file_path_permission(tool_name, file_path, config, extended_syntax=True):
    """
    Resolve a file-path tool decision using more-specific-wins across levels.

    The unoverridable ``[hard_deny]`` pool is checked FIRST (see
    :func:`_check_file_path_hard_deny`); a hard-deny match denies immediately and
    cannot be overridden by any level's normal allow. Otherwise this drives the
    level cascade via :meth:`~toolguard.config.Configuration.resolve_permission`,
    applying deny-first within each level and project-root anchoring to relative
    patterns. The first level that matches anything decides; no match at any level
    => fail-closed deny.

    Args:
        tool_name: 'Read', 'Write', or 'Edit'.
        file_path: The file path under evaluation.
        config: The resolved Configuration.
        extended_syntax: Whether extended prefixes are honoured.

    Returns:
        Tuple of (decision, reason).
    """
    hard = _check_file_path_hard_deny(tool_name, file_path, config, extended_syntax)
    if hard is not None:
        return hard

    def _decide(allow_patterns, deny_patterns):
        return _decide_file_path_at_level(
            file_path, list(allow_patterns), list(deny_patterns), config, extended_syntax
        )

    decision, reason = config.resolve_permission(tool_name, _decide)
    if decision == 'deny' and reason == 'Command does not match any allow patterns':
        # Normalise the default-deny reason to file-path phrasing.
        reason = 'Path does not match any allow patterns'
    return decision, reason


_COMPOUND_MATCH_PATTERN = re.compile(r'All \d+ sub-commands allowed: \[(.+)\]')


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
    for part in m.group(1).split(', '):
        if ' -> ' in part:
            cmd, rule = part.rsplit(' -> ', 1)
            details.append((cmd.strip(), rule.strip()))
    return details if details else None


def _log_allowed_command(command: str, reason: str, agent_info: str, env_config: dict) -> None:
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
    """
    compound_details = _parse_compound_match_details(reason)
    if compound_details:
        # Compound command: log each sub-command separately
        for sub_cmd, matched_rule in compound_details:
            log_command(sub_cmd, 'executed', matched_rule=matched_rule, extra_info=agent_info, config=env_config)
    else:
        # Simple command: extract matched rule from reason
        matched_rule = reason.split(': ', 1)[1] if ': ' in reason else None
        log_command(command, 'executed', matched_rule=matched_rule, extra_info=agent_info, config=env_config)


def main() -> None:
    """
    Main hook entry point.

    Algorithm:
    1. Load environment configuration
    2. Run startup validation (once per session) - logs warnings for config issues
    3. Parse input from stdin
    4. Check if tool is governed (configurable list)
    5. Determine tool type (file path or command)
    6. For file tools: extract file_path, check against glob patterns
    7. For command tools: extract command, check against patterns
    8. Log decision
    9. Output decision as JSON to stdout

    Exit codes:
    - Always exits with 0 (errors communicated via JSON)
    """
    try:
        # Load environment configuration
        env_config = get_env_config()

        # Parse hook input first to get cwd
        hook_data = parse_hook_input()

        tool_name = hook_data['tool_name']
        tool_input = hook_data['tool_input']
        cwd = hook_data.get('cwd', None)

        # Obtain the resolved configuration once via the public abstraction.
        # All file discovery, parsing, and format/location decisions live in the
        # config module; the hook only consumes semantic accessors from here on.
        config = load_configuration(cwd)

        # Run startup validation (once per session), reusing the loaded config.
        _run_startup_validation(env_config, cwd, config)

        # Resolve takeover mode configuration and issue warning if enabled
        takeover = config.takeover_mode()
        if takeover.enabled:
            log_dir = env_config.get('log_dir')
            if log_dir:
                issue_takeover_warning(log_dir, to_stdout=True, to_error_log=True)

        # Divergence/auto-migration tooling still consumes a plain dict; build it
        # from the resolved TakeoverConfig so those clients stay unchanged.
        takeover_dict = {
            'enabled': takeover.enabled,
            'ignored_allow_patterns': list(takeover.ignored_allow_patterns),
            'additional_ignored_patterns': list(takeover.additional_ignored_patterns),
            'no_match_fallback': takeover.no_match_fallback,
        }

        # Check for config divergence (once per session)
        global _divergence_check_done
        if not _divergence_check_done:
            _divergence_check_done = True
            log_dir = env_config.get('log_dir')
            if log_dir:
                project_root = config.project_root
                if project_root is not None:
                    divergent_patterns = check_and_warn_divergence(project_root, log_dir, takeover_dict)

                    # Auto-migration: consolidate permissions if configured
                    if divergent_patterns:
                        config_sync = config.config_sync_settings()

                        if config_sync['auto_migrate']:
                            # Auto-migration enabled - run it
                            run_auto_migration(project_root, log_dir, dict(config_sync), takeover_dict)
                        # else: warning already shown by check_and_warn_divergence

        # Resolve the list of governed tools via the config abstraction
        governed_tools = list(config.governed_tools())

        # Only handle tools in the governed list
        if tool_name not in governed_tools:
            # Not a governed tool - allow (other hooks handle other tools)
            output = create_hook_output('allow', f'Not a governed tool (governed: {", ".join(governed_tools)})')
            print(json.dumps(output))
            sys.exit(0)

        # Identify current agent context (used for logging)
        transcript_path = hook_data.get('transcript_path', '')
        agent_context = identify_current_agent(transcript_path)
        agent_info = agent_context['subagent_name'] if agent_context['agent_type'] == 'subagent' else 'main'

        # Handle file path tools (Read, Write, Edit)
        if tool_name in FILE_PATH_TOOLS:
            file_path = tool_input.get('file_path', '')
            if not file_path:
                output = create_hook_output('deny', 'No file_path provided in tool input')
                log_command(
                    f'{tool_name}()', 'refused', ['no file_path provided'], extra_info=agent_info, config=env_config
                )
                print(json.dumps(output))
                sys.exit(0)

            # Determine whether ANY level configures allow patterns for this tool
            # (fail-closed when nothing is configured anywhere).
            all_allow, _all_deny = config.allow_deny_for(tool_name)

            if not all_allow:
                # No allow patterns at any level - deny (fail closed)
                reason = f'No {tool_name} permissions found in settings - all operations blocked'
                output = create_hook_output('deny', reason)
                log_command(
                    f'{tool_name}({file_path})',
                    'refused',
                    ['no allow patterns configured'],
                    extra_info=agent_info,
                    config=env_config,
                )
                print(json.dumps(output))
                sys.exit(0)

            # Resolve file path permission via more-specific-wins level cascade.
            extended_syntax = env_config.get('extended_syntax', True)
            decision, reason = resolve_file_path_permission(
                tool_name, file_path, config, extended_syntax
            )

            # Log the decision
            log_target = f'{tool_name}({file_path})'
            if decision == 'allow':
                matched_rule = reason.split(': ', 1)[1] if ': ' in reason else None
                log_command(log_target, 'executed', matched_rule=matched_rule, extra_info=agent_info, config=env_config)
            else:
                violated_rules = [reason.split(': ', 1)[1] if ': ' in reason else reason]
                log_command(log_target, 'refused', violated_rules, extra_info=agent_info, config=env_config)

            output = create_hook_output(decision, reason)
            print(json.dumps(output))
            sys.exit(0)

        # Handle command tools (Bash, MCP terminals)
        command = tool_input.get('command', '')
        if not command:
            output = create_hook_output('deny', 'No command provided in tool input')
            log_command(command, 'refused', ['no command provided'], extra_info=agent_info, config=env_config)
            print(json.dumps(output))
            sys.exit(0)

        # Command tools (Bash, MCP terminals) all resolve against the Bash
        # permission patterns. Fail-closed when no allow pattern is configured at
        # any level.
        all_allow, _all_deny = config.allow_deny_for('Bash')

        if not all_allow:
            # No allow patterns at any level - deny everything (fail closed)
            reason = 'No Bash permissions found in settings - all commands blocked'
            output = create_hook_output('deny', reason)
            log_command(command, 'refused', ['no allow patterns configured'], extra_info=agent_info, config=env_config)
            print(json.dumps(output))
            sys.exit(0)

        # Resolve via more-specific-wins: each sub-command of a compound command
        # cascades independently through the levels; compound allowed iff all are.
        # The unoverridable [hard_deny] pool is checked FIRST per sub-command, so a
        # compound is hard-denied if ANY sub-command is hard-denied.
        extended_syntax = env_config.get('extended_syntax', True)
        hd_deny, hd_allow = config.hard_deny('Bash')

        def _resolve_one(sub_command, _ext=extended_syntax, _hd_deny=hd_deny, _hd_allow=hd_allow):
            hard = check_hard_deny(sub_command, list(_hd_deny), list(_hd_allow), _ext)
            if hard is not None:
                return hard
            return config.resolve_permission('Bash', make_command_level_decider(sub_command, _ext))

        decision, reason = resolve_compound_permission(command, _resolve_one)

        # Apply takeover mode no_match_fallback if enabled and command was denied for not matching
        if takeover.enabled and decision == 'deny' and 'does not match any allow patterns' in reason.lower():
            if takeover.no_match_fallback == 'warn_deny':
                reason = (
                    'Command does not match any allow patterns. '
                    'Consider adding a rule to toolguard_hook.toml to explicitly allow or deny this command.'
                )

        # Log the decision with agent identification
        if decision == 'allow':
            _log_allowed_command(command, reason, agent_info, env_config)
        else:
            # Extract violated rule from reason for logging
            violated_rules = [reason.split(': ', 1)[1] if ': ' in reason else reason]
            log_command(command, 'refused', violated_rules, extra_info=agent_info, config=env_config)

        # Create and output decision
        output = create_hook_output(decision, reason)
        print(json.dumps(output))
        sys.exit(0)

    except json.JSONDecodeError as e:
        # JSON parsing error - deny with error message
        error_reason = f'Failed to parse hook input: {str(e)}'
        output = create_hook_output('deny', error_reason)
        print(json.dumps(output), file=sys.stderr)
        sys.exit(0)

    except ValueError as e:
        # Validation error - deny with error message
        error_reason = f'Invalid hook input: {str(e)}'
        output = create_hook_output('deny', error_reason)
        print(json.dumps(output), file=sys.stderr)
        sys.exit(0)

    except Exception as e:
        # Unexpected error - deny and log
        error_reason = f'Unexpected error in hook: {str(e)}'
        output = create_hook_output('deny', error_reason)
        print(json.dumps(output), file=sys.stderr)
        print(f'Error: {error_reason}', file=sys.stderr)
        sys.exit(0)


if __name__ == '__main__':
    main()
