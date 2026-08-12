"""
Environment-variable and ``.env`` configuration for toolguard: where the
project root is, where logs go, and whether extended pattern syntax is
enabled. Nothing here reads permission rules.
"""

import os
from pathlib import Path
from typing import Dict, Optional

from toolguard.error_reporter import report_warning
from toolguard.path_utils import CONFIG_ROOT_INDICATORS, resolve_project_root


def find_project_root(start_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Find the nearest project root at or above *start_dir*.

    The markers, the walk and where it stops are all
    :func:`toolguard.path_utils.resolve_project_root`'s, in its ``strict=True``
    ("nearest marker of any kind wins") shape.

    Args:
        start_dir: Starting directory for search (defaults to current directory)

    Returns:
        Path to project root, or None if not found
    """
    start = start_dir if start_dir else Path.cwd()
    resolution = resolve_project_root(
        start, strict=True, indicators=CONFIG_ROOT_INDICATORS
    )
    return resolution.root


def load_env_file(project_root: Path, source_root: str = "") -> Dict[str, str]:
    """
    Read ``{project_root}/{source_root}/.env``.

    Parsed by hand rather than with python-dotenv, since toolguard's runtime
    is standard-library only, and the grammar is correspondingly small:
    ``KEY=VALUE`` split on the first ``=``, blank lines and whole-line ``#``
    comments skipped, matching leading/trailing quotes stripped from the
    value. Nothing else is interpreted -- a trailing ``# comment`` ends up
    inside the value, and ``export KEY=v`` yields the key ``"export KEY"``.

    Reads only; never sets or overrides anything in ``os.environ``.

    Args:
        project_root: Path to project root
        source_root: Relative path from project root to source root (default: '')

    Returns:
        The variables read from the file. Empty when the file is absent, or
        when reading it failed (which also reports a warning).
    """
    env_path = project_root / source_root / ".env"

    if not env_path.exists():
        return {}

    env_vars = {}

    try:
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                env_vars[key] = value
    except Exception as e:
        report_warning(
            f"Failed to load .env file: {e}",
            "Fix or remove the .env file so toolguard can read it.",
        )
        return {}

    return env_vars


def get_bool_env(
    name: str, default: bool, env_vars: Optional[Dict[str, str]] = None
) -> bool:
    """
    Read a boolean setting, case-insensitively.

    Precedence: ``os.environ``, then *env_vars*, then *default*. Accepts
    ``true``/``1``/``yes`` and ``false``/``0``/``no`` in any case; any other
    value reports a warning and falls back to *default*.

    Args:
        name: Environment variable name
        default: Default value if not found
        env_vars: Optional dict of variables from .env file

    Returns:
        Boolean value
    """
    value = os.environ.get(name)

    if value is None and env_vars:
        value = env_vars.get(name)

    if value is None:
        return default

    value_lower = value.lower()
    if value_lower in ("true", "1", "yes"):
        return True
    elif value_lower in ("false", "0", "no"):
        return False
    else:
        report_warning(
            f"Invalid boolean value for {name}: {value}. Using default: {default}",
            f"Set {name} to one of: true, false, 1, 0, yes, no.",
        )
        return default


def get_env_config(start_dir: Optional[Path] = None) -> Dict[str, any]:
    """
    Load toolguard's environment configuration.

    ``os.environ`` wins over ``.env`` -- except for ``TOOLGUARD_PROJECT_ROOT``
    and ``TOOLGUARD_SOURCE_ROOT``, which are read from the environment only,
    since both are needed to locate the ``.env`` file in the first place.

    Args:
        start_dir: When provided, anchor project-root discovery -- and hence
            which project's ``.env`` is read -- to THIS directory, ignoring
            ``TOOLGUARD_PROJECT_ROOT``. When ``None``, the override and
            auto-detection apply.

    Returns:
        Dictionary with all config values:
        - logging_enabled: bool
        - log_dir: Path -- absolute; ``TOOLGUARD_LOG_DIR`` if set (a relative
          value resolves against the project root), else ``{project_root}/logs``
        - extended_syntax: bool
        - project_root: Path
        - source_root: str
        - create_log_dir: bool
    """
    if start_dir is not None:
        project_root = (
            find_project_root(Path(start_dir)) or Path(start_dir).expanduser().resolve()
        )
    else:
        project_root_str = os.environ.get("TOOLGUARD_PROJECT_ROOT")
        if project_root_str:
            project_root = Path(project_root_str).expanduser().resolve()
        else:
            project_root = find_project_root()
            if project_root is None:
                project_root = Path.cwd()

    source_root = os.environ.get("TOOLGUARD_SOURCE_ROOT", "")

    env_vars = load_env_file(project_root, source_root)

    logging_enabled = get_bool_env("TOOLGUARD_LOGGING_ENABLED", True, env_vars)
    extended_syntax = get_bool_env("TOOLGUARD_EXTENDED_SYNTAX", True, env_vars)
    create_log_dir = get_bool_env("TOOLGUARD_CREATE_LOG_DIR", False, env_vars)

    log_dir_str = os.environ.get("TOOLGUARD_LOG_DIR")
    if log_dir_str is None and env_vars:
        log_dir_str = env_vars.get("TOOLGUARD_LOG_DIR")

    if log_dir_str:
        log_dir = Path(log_dir_str).expanduser()
        if not log_dir.is_absolute():
            log_dir = project_root / log_dir
    else:
        log_dir = project_root / "logs"

    return {
        "logging_enabled": logging_enabled,
        "log_dir": log_dir.resolve(),
        "extended_syntax": extended_syntax,
        "project_root": project_root,
        "source_root": source_root,
        "create_log_dir": create_log_dir,
    }
