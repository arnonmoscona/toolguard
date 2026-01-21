"""TOML configuration loader for toolguard."""

import tomllib
from pathlib import Path


def load_toml_config(path: Path) -> dict:
    """
    Load and return TOML configuration from the given path.

    Args:
        path: Path to the TOML configuration file

    Returns:
        Dictionary containing the parsed TOML configuration

    Raises:
        FileNotFoundError: If the file does not exist
        tomllib.TOMLDecodeError: If the file contains invalid TOML
    """
    with open(path, 'rb') as f:
        return tomllib.load(f)
