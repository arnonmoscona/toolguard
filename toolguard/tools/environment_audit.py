"""
Environment shadowing audit for toolguard (TOO-19).

Detects an environment condition that WOULD cause the installed toolguard
distribution to be shadowed for a fresh process -- e.g. ``PYTHONPATH``
containing an entry (such as ``.``) under which a ``toolguard/`` package
exists. See :func:`toolguard.install_provenance.pythonpath_shadow_entries`
for the underlying predicate, and :mod:`toolguard.session_start` for the
SEPARATE, session-level detection of THIS process actually being shadowed
right now (a different, stronger check -- this module only asks what the
environment permits, not what happened).

This finding is deliberately about the *hook's* resolution, not the auditing
process's own: ``toolguard-audit``/``toolguard-maintain`` may themselves be
invoked with ``--dev`` (running from this source tree on purpose, per
``CLAUDE.md``), which says nothing about whether an ordinary ``toolguard``
PreToolUse hook invocation -- launched separately by Claude Code, sharing the
same environment -- would be shadowed. So this check reads ``PYTHONPATH``
from the environment directly rather than inspecting how THIS process itself
was launched or imported.

Silent in the normal case (no ``PYTHONPATH``, or a ``PYTHONPATH`` with no
shadowing entry) -- like :mod:`toolguard.tools.takeover_audit`'s
``loose-undecidable-fallback`` finding, a finding that always fires trains
people to ignore findings.
"""

from dataclasses import dataclass
from typing import List, Mapping, Optional

from toolguard.install_provenance import pythonpath_shadow_entries
from toolguard.tools.danger import Severity


@dataclass(frozen=True)
class EnvironmentFinding:
    """
    A single environment-level audit finding.

    Attributes:
        finding_id: Stable string identifier (e.g. ``'pythonpath-shadows-hook'``).
        severity: Ranked :class:`~toolguard.tools.danger.Severity` (the same
            shared IntEnum other analysers use, for consistent ranking).
        description: Human-readable description of the condition found.
        impact: Explanation of the security impact.
        remediation: Suggested fix.
    """

    finding_id: str
    severity: Severity
    description: str
    impact: str
    remediation: str


def audit_environment(
    env: Optional[Mapping[str, str]] = None,
) -> List[EnvironmentFinding]:
    """
    Audit the process environment for a toolguard-hook-shadowing condition.

    Args:
        env: Environment mapping to inspect (defaults to ``os.environ`` via
            :func:`~toolguard.install_provenance.pythonpath_shadow_entries`;
            exposed here for testing without mutating the real environment).

    Returns:
        A list with one HIGH finding when ``PYTHONPATH`` would shadow the
        installed toolguard package; empty (the normal case) otherwise.
    """
    entries = pythonpath_shadow_entries(env)
    if not entries:
        return []

    listed = ", ".join(entries)
    return [
        EnvironmentFinding(
            finding_id="pythonpath-shadows-hook",
            severity=Severity.HIGH,
            description=(
                f"PYTHONPATH contains {listed}, which holds its own "
                "toolguard/ package. Any toolguard console-script or "
                "'-m toolguard...' invocation launched with this environment "
                "imports THAT package instead of the installed distribution."
            ),
            impact=(
                "The PreToolUse permission hook is the process making every "
                "allow/deny/ask decision. If it is shadowed this way, an "
                "unreviewed -- possibly uncommitted, mid-refactor -- copy of "
                "toolguard's own code decides permissions instead of the "
                "installed, reviewed release, silently: the hook still runs "
                "and still returns decisions, just from the wrong source."
            ),
            remediation=(
                "Remove the shadowing entry from PYTHONPATH (check shell rc "
                "files for a stray 'export PYTHONPATH=...'). Registering the "
                "hook in its hardened form ('<venv python> -E -P -m "
                "toolguard.hook', the default 'toolguard-install "
                "register-hooks' now writes -- see 'toolguard-install "
                "skills-status' to check an existing registration) also "
                "closes this for the hook itself, since -E/-P make it ignore "
                "PYTHONPATH and cwd entirely."
            ),
        )
    ]
