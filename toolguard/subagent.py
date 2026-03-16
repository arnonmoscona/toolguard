"""
Subagent identification for toolguard.

Identifies the current agent context by reading the Claude Code transcript
and finding open Task tool calls that indicate subagent execution.
"""

import json
from pathlib import Path
from typing import Dict, Any, List


def read_transcript_tail(transcript_path: str, max_lines: int = 100) -> List[str]:
    """
    Read the last N lines of a transcript file efficiently.

    Args:
        transcript_path: Path to the JSONL transcript file
        max_lines: Maximum number of lines to read from the end

    Returns:
        List of lines from the end of the file (in chronological order)
    """
    path = Path(transcript_path)
    if not path.exists():
        return []

    try:
        # Read file and get last N lines
        # For very large files, we could optimize with seeking from end
        # but for now, simple approach is sufficient
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            return lines[-max_lines:] if len(lines) > max_lines else lines
    except (IOError, OSError):
        return []


def parse_jsonl_lines(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Parse JSONL lines into list of dictionaries.

    Args:
        lines: List of JSONL lines

    Returns:
        List of parsed JSON objects (invalid lines are skipped)
    """
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            # Skip malformed lines (could be incomplete due to concurrent write)
            continue
    return entries


def find_task_tool_uses(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Find all Task tool_use entries in transcript.

    Args:
        entries: List of transcript entries

    Returns:
        List of Task tool_use info dicts with keys:
        - tool_use_id: The unique ID of the tool use
        - subagent_type: The subagent type (e.g., 'feature-coder')
        - entry_index: Index in the entries list
    """
    task_uses = []

    for idx, entry in enumerate(entries):
        # Look for assistant messages with tool_use
        if entry.get('type') != 'assistant':
            continue

        message = entry.get('message', {})
        content = message.get('content', [])

        # Handle content as list or string (different transcript formats)
        if isinstance(content, str):
            # In some transcript versions, content is a string summary, not a list
            # Skip these entries as they don't have tool_use info
            continue

        for item in content:
            if item.get('type') == 'tool_use' and item.get('name') == 'Task':
                tool_input = item.get('input', {})
                task_uses.append(
                    {
                        'tool_use_id': item.get('id'),
                        'subagent_type': tool_input.get('subagent_type', 'unknown'),
                        'description': tool_input.get('description', ''),
                        'entry_index': idx,
                    }
                )

    return task_uses


def find_tool_results(entries: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Find all tool_result entries and map tool_use_id to entry index.

    Args:
        entries: List of transcript entries

    Returns:
        Dict mapping tool_use_id to entry index where result appears
    """
    results = {}

    for idx, entry in enumerate(entries):
        # Look for user messages with tool_result
        if entry.get('type') != 'user':
            continue

        message = entry.get('message', {})
        content = message.get('content', [])

        # Handle content as list or string (different transcript formats)
        if isinstance(content, str):
            # In some transcript versions, content is a string summary, not a list
            # Skip these entries as they don't have tool_result info
            continue

        for item in content:
            if item.get('type') == 'tool_result':
                tool_use_id = item.get('tool_use_id')
                if tool_use_id:
                    results[tool_use_id] = idx

    return results


def identify_current_agent(transcript_path: str) -> Dict[str, Any]:
    """
    Identify the current agent context from the transcript.

    Reads the transcript and finds the most recent open Task tool call
    (one that has no corresponding tool_result yet).

    Args:
        transcript_path: Path to the Claude Code transcript JSONL file

    Returns:
        Dict with keys:
        - agent_type: 'main' or 'subagent'
        - subagent_name: Name of subagent (e.g., 'feature-coder') or None
        - subagent_description: Description from Task call or None
        - tool_use_id: The Task tool_use_id if in subagent, or None
    """
    # Default result - main agent
    result = {
        'agent_type': 'main',
        'subagent_name': None,
        'subagent_description': None,
        'tool_use_id': None,
    }

    if not transcript_path:
        return result

    # Read transcript tail
    lines = read_transcript_tail(transcript_path, max_lines=200)
    if not lines:
        return result

    # Parse entries
    entries = parse_jsonl_lines(lines)
    if not entries:
        return result

    # Find all Task tool_uses and tool_results
    task_uses = find_task_tool_uses(entries)
    tool_results = find_tool_results(entries)

    # Find the most recent Task that hasn't completed
    # Work backwards through Task uses
    for task in reversed(task_uses):
        tool_use_id = task['tool_use_id']
        task_index = task['entry_index']

        # Check if there's a result for this Task
        if tool_use_id in tool_results:
            result_index = tool_results[tool_use_id]
            # Result must come AFTER the tool_use
            if result_index > task_index:
                # This Task has completed, check next one
                continue

        # Found an open Task - we're in this subagent
        result = {
            'agent_type': 'subagent',
            'subagent_name': task['subagent_type'],
            'subagent_description': task['description'],
            'tool_use_id': tool_use_id,
        }
        break

    return result
