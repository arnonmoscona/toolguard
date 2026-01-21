"""
Backwards compatibility verification script for toolguard.

Replays historical commands from checked_bash logs and verifies that
the new toolguard hook produces identical permission decisions.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional

from toolguard.config import load_permissions
from toolguard.permissions import check_permission


def find_log_files() -> List[Path]:
    """
    Find all checked_bash log files in the logs directory.

    Returns:
        List of Path objects for log files, sorted by name
    """
    project_root = Path(__file__).parent.parent.parent
    logs_dir = project_root / 'logs'

    if not logs_dir.exists():
        print(f'Warning: logs directory not found at {logs_dir}', file=sys.stderr)
        return []

    log_files = sorted(logs_dir.glob('checked_bash-*.md'))
    return log_files


def parse_log_entry(lines: List[str]) -> Optional[Tuple[str, str, str]]:
    """
    Parse a single log entry from markdown format.

    Expected format:
        ## 2026-01-07 14:20:58

        - **Status**: EXECUTED
        - **Command**: `command text here`

    Args:
        lines: List of lines for this entry (from ## timestamp to next ## or EOF)

    Returns:
        Tuple of (timestamp, status, command) or None if malformed
    """
    timestamp = None
    status = None
    command = None

    for line in lines:
        line = line.strip()

        # Extract timestamp from header
        if line.startswith('##'):
            timestamp = line[2:].strip()

        # Extract status
        elif '**Status**' in line:
            match = re.search(r'\*\*Status\*\*:\s*(\w+)', line)
            if match:
                status = match.group(1)

        # Extract command from backticks
        elif '**Command**' in line:
            match = re.search(r'`([^`]+)`', line)
            if match:
                command = match.group(1)

    # Only return if we have all required fields
    if timestamp and status and command:
        return timestamp, status, command

    return None


def parse_log_file(log_path: Path) -> List[Tuple[str, str, str]]:
    """
    Parse all entries from a single log file.

    Args:
        log_path: Path to the log file

    Returns:
        List of (timestamp, status, command) tuples
    """
    entries = []

    try:
        with open(log_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f'Warning: Could not read {log_path}: {e}', file=sys.stderr)
        return entries

    # Split by markdown headers (##)
    sections = re.split(r'^##', content, flags=re.MULTILINE)

    for section in sections:
        if not section.strip():
            continue

        # Add back the ## marker for parsing
        lines = ('## ' + section).split('\n')
        entry = parse_log_entry(lines)

        if entry:
            entries.append(entry)

    return entries


def verify_command(
    command: str, expected_status: str, allow_patterns: List[str], deny_patterns: List[str]
) -> Tuple[bool, str, str]:
    """
    Verify a single command against toolguard and compare with expected result.

    Args:
        command: The bash command to verify
        expected_status: Expected status from log (EXECUTED or REFUSED)
        allow_patterns: Allow patterns from config
        deny_patterns: Deny patterns from config

    Returns:
        Tuple of (matches: bool, toolguard_decision: str, reason: str)
    """
    decision, reason = check_permission(command, allow_patterns, deny_patterns)

    # Map log status to expected toolguard decision
    expected_decision = 'allow' if expected_status == 'EXECUTED' else 'deny'

    matches = decision == expected_decision
    return matches, decision, reason


def main():
    """
    Main entry point for backwards compatibility verification.

    Exit codes:
        0 - All commands matched
        1 - Some mismatches found or error occurred
    """
    print('Toolguard Backwards Compatibility Verification')
    print('=' * 60)
    print()

    # Load permissions
    try:
        allow_patterns, deny_patterns = load_permissions()
    except SystemExit:
        # load_permissions prints error and calls sys.exit(1)
        return 1

    print(f'Loaded {len(allow_patterns)} allow patterns and {len(deny_patterns)} deny patterns')
    print()

    # Find and parse all log files
    log_files = find_log_files()
    if not log_files:
        print('No log files found to verify')
        return 1

    print(f'Found {len(log_files)} log files')
    print()

    # Parse all entries
    all_entries = []
    for log_file in log_files:
        entries = parse_log_file(log_file)
        all_entries.extend(entries)

    print(f'Parsed {len(all_entries)} command entries from logs')
    print()

    # Verify each command
    mismatches = []
    total = 0

    for timestamp, status, command in all_entries:
        total += 1
        matches, decision, reason = verify_command(command, status, allow_patterns, deny_patterns)

        if not matches:
            mismatches.append(
                {
                    'timestamp': timestamp,
                    'command': command,
                    'expected': status,
                    'got': decision,
                    'reason': reason,
                }
            )

    # Print summary
    print('Verification Results')
    print('-' * 60)
    print(f'Total commands: {total}')
    print(f'Matches: {total - len(mismatches)}')
    print(f'Mismatches: {len(mismatches)}')
    print()

    # Print mismatches if any
    if mismatches:
        print('MISMATCHES FOUND:')
        print('=' * 60)
        print()

        for i, mismatch in enumerate(mismatches, 1):
            print(f'{i}. Timestamp: {mismatch["timestamp"]}')
            print(f'   Command: {mismatch["command"]}')
            print(f'   Expected (from log): {mismatch["expected"]}')
            print(f'   Got (from toolguard): {mismatch["got"]}')
            print(f'   Reason: {mismatch["reason"]}')
            print()

        return 1
    else:
        print('SUCCESS: All commands matched expected results!')
        return 0


if __name__ == '__main__':
    sys.exit(main())
