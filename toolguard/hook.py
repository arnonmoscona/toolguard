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
from toolguard.compound import check_compound_permission
from toolguard.patterns import PatternType, match_pattern, parse_pattern
from toolguard.config import find_project_root, load_configuration
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

    # Get log directory from env config
    log_dir = env_config.get('log_dir')
    if not log_dir:
        try:
            log_dir = find_project_root(start_dir) / 'logs'
        except RuntimeError:
            return  # Can't log without log dir

    if config is None:
        config = load_configuration(start_dir)

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
                try:
                    project_root = find_project_root(cwd)
                    divergent_patterns = check_and_warn_divergence(project_root, log_dir, takeover_dict)

                    # Auto-migration: consolidate permissions if configured
                    if divergent_patterns:
                        config_sync = config.config_sync_settings()

                        if config_sync['auto_migrate']:
                            # Auto-migration enabled - run it
                            run_auto_migration(project_root, log_dir, dict(config_sync), takeover_dict)
                        else:
                            # Auto-migration disabled - warning already shown by check_and_warn_divergence
                            pass

                except RuntimeError:
                    # No project root found - skip divergence check
                    pass

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

            # Load patterns for this specific tool (reusing the loaded config)
            allow_patterns, deny_patterns = load_file_path_patterns(tool_name, cwd, config)

            if not allow_patterns:
                # No allow patterns - deny (fail closed)
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

            # Check file path permission using GLOB matching (with optional extended syntax)
            extended_syntax = env_config.get('extended_syntax', True)
            decision, reason = check_file_path_permission(
                file_path, allow_patterns, deny_patterns, extended_syntax
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

        # Resolve Bash command permissions via the config abstraction
        allow_patterns, deny_patterns = config.bash_permissions()

        # Use takeover mode configuration resolved earlier
        # (takeover already resolved at startup for the warning check)

        if not allow_patterns:
            # No allow patterns - deny everything (fail closed)
            reason = 'No Bash permissions found in settings - all commands blocked'
            output = create_hook_output('deny', reason)
            log_command(command, 'refused', ['no allow patterns configured'], extra_info=agent_info, config=env_config)
            print(json.dumps(output))
            sys.exit(0)

        # Check permission (handles both simple and compound commands)
        extended_syntax = env_config.get('extended_syntax', True)
        decision, reason = check_compound_permission(command, allow_patterns, deny_patterns, [], extended_syntax)

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
