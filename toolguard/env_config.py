"""
Environment variable configuration for toolguard.

Provides centralized configuration loading from environment variables and .env files.
"""

import os
import sys
from pathlib import Path
from typing import Dict, Optional


def find_project_root(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find the project root by searching for .git or pyproject.toml.

    Climbs up from start_dir (or current directory) until finding a marker,
    stopping at home directory or filesystem root.

    Args:
        start_dir: Starting directory for search (defaults to current directory)

    Returns:
        Path to project root, or None if not found
    """
    current = start_dir if start_dir else Path.cwd()
    home = Path.home()

    while True:
        # Check for project markers
        if (current / '.git').exists() or (current / 'pyproject.toml').exists():
            return current

        # Stop if we reach home or root
        if current == home or current == current.parent:
            return None

        current = current.parent


def load_env_file(project_root: Path, source_root: str = '') -> Dict[str, str]:
    """
    Load environment variables from .env file.

    Location: {project_root}/{source_root}/.env

    Uses python-dotenv if available, otherwise manual parsing.
    Does NOT override existing environment variables.

    Args:
        project_root: Path to project root
        source_root: Relative path from project root to source root (default: '')

    Returns:
        Dictionary of variables loaded from .env file (empty dict if not found)
    """
    env_path = project_root / source_root / '.env'

    if not env_path.exists():
        return {}

    env_vars = {}

    try:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Skip lines without =
                if '=' not in line:
                    continue
                # Parse KEY=VALUE
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                env_vars[key] = value
    except Exception as e:
        print(f'Warning: Failed to load .env file: {e}', file=sys.stderr)
        return {}

    return env_vars


def get_bool_env(name: str, default: bool, env_vars: Optional[Dict[str, str]] = None) -> bool:
    """
    Get a boolean environment variable with case-insensitive parsing.

    Precedence:
    1. Environment variable (if set)
    2. env_vars dict (typically from .env file)
    3. Default value

    True values: 'true', 'True', 'TRUE', '1', 'yes', 'Yes', 'YES'
    False values: 'false', 'False', 'FALSE', '0', 'no', 'No', 'NO'

    Args:
        name: Environment variable name
        default: Default value if not found
        env_vars: Optional dict of variables from .env file

    Returns:
        Boolean value
    """
    # Check environment variable first (highest priority)
    value = os.environ.get(name)

    # Fall back to env_vars dict (from .env file)
    if value is None and env_vars:
        value = env_vars.get(name)

    # Fall back to default
    if value is None:
        return default

    # Parse boolean
    value_lower = value.lower()
    if value_lower in ('true', '1', 'yes'):
        return True
    elif value_lower in ('false', '0', 'no'):
        return False
    else:
        # Invalid value - warn and use default
        print(f'Warning: Invalid boolean value for {name}: {value}. Using default: {default}', file=sys.stderr)
        return default


def get_env_config() -> Dict[str, any]:
    """
    Load all toolguard configuration from environment variables and .env file.

    Environment variables take precedence over .env file values.

    Returns:
        Dictionary with all config values:
        - logging_enabled: bool
        - log_dir: Path
        - extended_syntax: bool
        - project_root: Path
        - source_root: str
        - create_log_dir: bool
    """
    # Get project root (explicit or auto-detect)
    project_root_str = os.environ.get('TOOLGUARD_PROJECT_ROOT')
    if project_root_str:
        project_root = Path(project_root_str).expanduser().resolve()
    else:
        project_root = find_project_root()
        if project_root is None:
            # No project root found - use current directory
            project_root = Path.cwd()

    # Get source root (for .env file location)
    source_root = os.environ.get('TOOLGUARD_SOURCE_ROOT', '')

    # Load .env file
    env_vars = load_env_file(project_root, source_root)

    # Get configuration values
    logging_enabled = get_bool_env('TOOLGUARD_LOGGING_ENABLED', True, env_vars)
    extended_syntax = get_bool_env('TOOLGUARD_EXTENDED_SYNTAX', True, env_vars)
    create_log_dir = get_bool_env('TOOLGUARD_CREATE_LOG_DIR', False, env_vars)

    # Get log directory
    log_dir_str = os.environ.get('TOOLGUARD_LOG_DIR')
    if log_dir_str is None and env_vars:
        log_dir_str = env_vars.get('TOOLGUARD_LOG_DIR')

    if log_dir_str:
        # Explicit log directory specified
        log_dir = Path(log_dir_str).expanduser()
        if not log_dir.is_absolute():
            # Relative to project root
            log_dir = project_root / log_dir
    else:
        # Default: {project_root}/logs
        log_dir = project_root / 'logs'

    return {
        'logging_enabled': logging_enabled,
        'log_dir': log_dir.resolve(),
        'extended_syntax': extended_syntax,
        'project_root': project_root,
        'source_root': source_root,
        'create_log_dir': create_log_dir,
    }
