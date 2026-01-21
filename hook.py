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
import sys
from pathlib import PurePath
from typing import Any, Dict, List, Tuple

from toolguard.compound import check_compound_permission
from toolguard.config import discover_config_files, find_project_root, load_governed_tools, load_permissions
from toolguard.env_config import get_env_config
from toolguard.error_log import log_warning
from toolguard.log_writer import log_command
from toolguard.normalization import expand_tilde
from toolguard.subagent import identify_current_agent
from toolguard.toml_config import load_toml_config
from toolguard.config_validation import validate_permissions

# Tools that operate on file paths (use GLOB matching)
FILE_PATH_TOOLS = {'Read', 'Write', 'Edit'}

# Tools that execute commands (use compound command parsing)
COMMAND_TOOLS = {'Bash', 'mcp__jetbrains__execute_terminal_command', 'mcp__local-tools__checked_bash'}

# Module-level flag to ensure validation runs only once per session
_validation_done = False


def _run_startup_validation(env_config: Dict[str, Any], start_dir: str = None) -> None:
    """
    Run configuration validation once at startup.

    Loads full config from discovered files and validates permissions.
    Logs warnings for:
    - Both TOML and JSON config files existing at same level
    - Unsupported tools in permissions
    - Ungoverned tools in permissions

    Args:
        env_config: Environment configuration dict with log_dir
        start_dir: Directory to start searching for project root from. Defaults to cwd.
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

    # Discover config files and check for duplicates
    config_files = discover_config_files(start_dir)

    # Check for duplicate TOML+JSON at same level
    seen_bases = {}  # base_name -> (path, format)
    for path, source_type, file_format in config_files:
        # Extract base name (e.g., 'toolguard_hook' from 'toolguard_hook.toml')
        base_name = path.stem
        parent = str(path.parent)
        key = (parent, base_name)

        if key in seen_bases:
            prev_path, prev_format = seen_bases[key]
            if prev_format != file_format:
                log_warning(
                    f'Both {base_name}.toml and {base_name}.json exist in {parent}',
                    f'Remove one of the files to avoid confusion. TOML ({path.name}) is being used.',
                    log_dir,
                )
        else:
            seen_bases[key] = (path, file_format)

    # Build merged config for validation - ONLY from toolguard_hook files
    # (settings.local.json permissions are for Claude's native system, not toolguard)
    merged_config = {'governed_tools': [], 'permissions': {'allow': [], 'deny': [], 'ask': []}}

    for path, source_type, file_format in config_files:
        # Only process toolguard_hook files for validation
        if source_type != 'toolguard_hook':
            continue

        try:
            if file_format == 'toml':
                config = load_toml_config(path)
            else:
                with open(path, 'r') as f:
                    config = json.load(f)

            # Merge governed_tools
            if 'governed_tools' in config:
                for tool in config['governed_tools']:
                    if tool not in merged_config['governed_tools']:
                        merged_config['governed_tools'].append(tool)

            # Merge additional_supported_tools
            if 'additional_supported_tools' in config:
                if 'additional_supported_tools' not in merged_config:
                    merged_config['additional_supported_tools'] = []
                for tool in config['additional_supported_tools']:
                    if tool not in merged_config['additional_supported_tools']:
                        merged_config['additional_supported_tools'].append(tool)

            # Merge permissions
            if 'permissions' in config:
                for perm_type in ['allow', 'deny', 'ask']:
                    if perm_type in config['permissions']:
                        for perm in config['permissions'][perm_type]:
                            if perm not in merged_config['permissions'][perm_type]:
                                merged_config['permissions'][perm_type].append(perm)
        except Exception:
            continue  # Skip files that can't be loaded

    # Run validation
    warnings = validate_permissions(merged_config)

    # Log each warning
    for warning in warnings:
        log_warning(warning['message'], warning['corrective_steps'], log_dir)


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


def load_file_path_patterns(tool_name: str, start_dir: str = None) -> Tuple[List[str], List[str]]:
    """
    Load allow/deny patterns for file path tools (Read, Write, Edit).

    Extracts patterns like 'Read(/tmp/**)' from the permissions config.

    Args:
        tool_name: The tool name to load patterns for (Read, Write, or Edit)
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        Tuple of (allow_patterns, deny_patterns) - path patterns without tool prefix
    """
    config_files = discover_config_files(start_dir)

    allow_patterns = []
    deny_patterns = []

    prefix = f'{tool_name}('
    suffix = ')'

    for file_path, source_type, file_format in config_files:
        try:
            if file_format == 'toml':
                config = load_toml_config(file_path)
            else:
                with open(file_path, 'r') as f:
                    config = json.load(f)
        except (json.JSONDecodeError, IOError, Exception):
            continue

        permissions = config.get('permissions', {})

        # Extract patterns for this tool from allow list
        for perm in permissions.get('allow', []):
            if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(suffix):
                # Extract the path pattern between "ToolName(" and ")"
                pattern = perm[len(prefix) : -1]
                if pattern not in allow_patterns:
                    allow_patterns.append(pattern)

        # Extract patterns for this tool from deny list
        for perm in permissions.get('deny', []):
            if isinstance(perm, str) and perm.startswith(prefix) and perm.endswith(suffix):
                pattern = perm[len(prefix) : -1]
                if pattern not in deny_patterns:
                    deny_patterns.append(pattern)

    return allow_patterns, deny_patterns


def check_file_path_permission(file_path: str, allow_patterns: List[str], deny_patterns: List[str]) -> Tuple[str, str]:
    """
    Check if a file path is permitted based on allow and deny patterns.

    Uses GLOB pattern matching with proper globstar (**) support via PurePath.full_match().

    Args:
        file_path: The file path to check
        allow_patterns: List of glob patterns that allow access
        deny_patterns: List of glob patterns that deny access

    Returns:
        Tuple of (decision, reason) where decision is 'allow' or 'deny'
    """
    # Expand tilde in file path for matching
    expanded_path = expand_tilde(file_path)

    # Check deny list first
    for pattern in deny_patterns:
        expanded_pattern = expand_tilde(pattern)
        try:
            if PurePath(expanded_path).full_match(expanded_pattern):
                return 'deny', f'Path matches deny pattern: {pattern}'
        except (ValueError, TypeError):
            continue

    # Check allow list
    for pattern in allow_patterns:
        expanded_pattern = expand_tilde(pattern)
        try:
            if PurePath(expanded_path).full_match(expanded_pattern):
                return 'allow', f'Path matches allow pattern: {pattern}'
        except (ValueError, TypeError):
            continue

    # Default: deny (not explicitly allowed)
    return 'deny', 'Path does not match any allow patterns'


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

        # Run startup validation (once per session) using cwd from hook input
        _run_startup_validation(env_config, cwd)

        # Load list of governed tools (using cwd from hook input for project discovery)
        governed_tools = load_governed_tools(cwd)

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

            # Load patterns for this specific tool
            allow_patterns, deny_patterns = load_file_path_patterns(tool_name, cwd)

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

            # Check file path permission using GLOB matching
            decision, reason = check_file_path_permission(file_path, allow_patterns, deny_patterns)

            # Log the decision
            log_target = f'{tool_name}({file_path})'
            if decision == 'allow':
                log_command(log_target, 'executed', extra_info=agent_info, config=env_config)
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

        # Load permissions from settings (using cwd from hook input for project discovery)
        allow_patterns, deny_patterns = load_permissions(cwd)

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

        # Log the decision with agent identification
        if decision == 'allow':
            log_command(command, 'executed', extra_info=agent_info, config=env_config)
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
