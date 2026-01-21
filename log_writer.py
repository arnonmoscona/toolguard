"""
Logging utilities for toolguard.

Provides logging functionality with same format as checked_bash.py.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from toolguard.config import find_project_root


def log_command(
    command_str: str,
    status: str,
    violated_rules: Optional[List[str]] = None,
    log_dir: Optional[Path] = None,
    extra_info: Optional[str] = None,
    config: Optional[dict] = None,
) -> None:
    """
    Log command execution to file if logging is enabled.

    Uses the same logging format as checked_bash.py for compatibility.
    Logs to logs/toolguard-YYYY-MM-DD.md by default.

    Args:
        command_str: The command that was executed or refused
        status: Either 'executed' or 'refused'
        violated_rules: List of rules that were violated (for refused commands)
        log_dir: Optional directory path for logs (for testing). If provided, uses this
                 directory directly instead of resolving from environment or project root.
        extra_info: Optional additional info to include in the log entry (e.g., agent identification)
        config: Optional environment config dict (from get_env_config())
    """
    # Check if logging is enabled (backward compatibility with CHECKED_BASH_LOGGING_ON)
    if config is not None:
        logging_on = config.get('logging_enabled', True)
    else:
        logging_on = os.environ.get('CHECKED_BASH_LOGGING_ON', 'true').lower() == 'true'

    if not logging_on:
        return

    try:
        # Get logging configuration
        logging_format = os.environ.get('CHECKED_BASH_LOGGING_FORMAT', 'markdown').lower()

        # Resolve log directory path
        if log_dir is not None:
            # Use provided log directory (for testing)
            # Check directory exists (old behavior for explicit log_dir - exit on error)
            log_dir_path = log_dir
            if not log_dir_path.exists():
                print(f'Error: Logging directory does not exist: {log_dir_path}', file=sys.stderr)
                sys.exit(1)
        elif config is not None:
            # Use config from env_config
            log_dir_path = config['log_dir']
            create_log_dir = config.get('create_log_dir', False)

            # Check if directory exists
            if not log_dir_path.exists():
                if create_log_dir:
                    # Create directory
                    log_dir_path.mkdir(parents=True, exist_ok=True)
                else:
                    # Warn and disable logging for this invocation
                    print(
                        f'Warning: Logging directory does not exist: {log_dir_path}. Logging disabled.',
                        file=sys.stderr,
                    )
                    return
        else:
            # Backward compatibility: use environment variables
            logging_dir = os.environ.get('CHECKED_BASH_LOGGING_DIR', 'logs')
            if Path(logging_dir).is_absolute():
                log_dir_path = Path(logging_dir)
            else:
                project_root = find_project_root()
                log_dir_path = project_root / logging_dir

            # Check directory exists (old behavior - exit on error)
            if not log_dir_path.exists():
                print(f'Error: Logging directory does not exist: {log_dir_path}', file=sys.stderr)
                sys.exit(1)

        # Generate log filename with current date and appropriate extension
        extension = 'md' if logging_format == 'markdown' else 'jsonlines'
        log_filename = f'toolguard-{datetime.now().strftime("%Y-%m-%d")}.{extension}'
        log_file = log_dir_path / log_filename

        # Prepare log entry
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        violated_rules = violated_rules or []

        # Write log entry
        with open(log_file, 'a', encoding='utf-8') as f:
            if logging_format == 'jsonlines':
                # JSONLines format
                import json

                entry = {
                    'timestamp': datetime.now().isoformat(),
                    'status': status,
                    'command': command_str,
                    'violated_rules': violated_rules,
                }
                if extra_info:
                    entry['extra_info'] = extra_info
                f.write(json.dumps(entry) + '\n\n')
            else:
                # Markdown format (default)
                f.write(f'## {timestamp}\n\n')
                f.write(f'- **Status**: {status.upper()}\n')
                f.write(f'- **Command**: `{command_str}`\n')
                if violated_rules:
                    f.write(f'- **Violated Rules**: {", ".join(f"`{rule}`" for rule in violated_rules)}\n')
                if extra_info:
                    f.write(f'- **Agent**: {extra_info}\n')
                f.write('\n')

    except RuntimeError as e:
        # Project root not found - fatal error
        print(f'Fatal error: {e}', file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        # Other logging errors - print warning but don't fail
        print(f'Warning: Failed to write log: {e}', file=sys.stderr)
