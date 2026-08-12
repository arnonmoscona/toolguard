"""
Structured configuration issue type.

A leaf module -- imports nothing else from :mod:`toolguard` -- so that
modules :mod:`toolguard.config` depends on can construct :class:`Issue`
without importing ``config.py`` back and creating a cycle.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """
    A structured, content-level configuration issue (display/log only).

    Attributes:
        level: Severity label ('warning' or 'error').
        message: Human-readable description of the issue.
        corrective_steps: Suggested remediation.
    """

    level: str
    message: str
    corrective_steps: str
