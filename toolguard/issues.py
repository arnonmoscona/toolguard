"""
Structured configuration issue type.

Extracted from :mod:`toolguard.config` (TOO-19 Phase 0a, increment 1) so that
leaf modules -- currently :mod:`toolguard.rule_entry` -- can construct
:class:`Issue` instances without importing :mod:`toolguard.config` and
creating a circular import (``config.py`` already depends on
``config_validation.py``, which a later increment needs to depend on
``rule_entry.py`` in turn).

:mod:`toolguard.config` re-exports :class:`Issue` from here, so existing
``from toolguard.config import Issue`` call sites are unaffected.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Issue:
    """
    A structured, content-level configuration issue (display/log only).

    Replaces the hand-rolled validation walk in the hook. The config module
    detects issues and returns them; the hook decides whether/where to log.
    The config module performs NO logging side effects.

    Attributes:
        level: Severity label ('warning' or 'error').
        message: Human-readable description of the issue.
        corrective_steps: Suggested remediation.
    """

    level: str
    message: str
    corrective_steps: str
