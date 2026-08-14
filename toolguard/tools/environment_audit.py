"""
Environment shadowing audit: report a ``PYTHONPATH`` that would shadow the
installed toolguard distribution for a freshly-launched process.

The question is deliberately asked of the ENVIRONMENT, not of how THIS process
was launched or imported: the auditor may legitimately be running from a source
tree via ``--dev``, which says nothing about whether an ordinary hook invocation
sharing the same environment would be shadowed.  See technical-notes.md, "The
audit predicate: ``PYTHONPATH`` content, not process provenance".
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
        severity: Ranked severity of the condition.
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
        env: Environment mapping to inspect (defaults to ``os.environ``).
            Exposed for testing without mutating the real environment.

    Returns:
        A list with one HIGH finding when ``PYTHONPATH`` holds a shadowing
        entry; empty -- the normal case -- otherwise.
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
                "toolguard/ package or toolguard.py module. Any toolguard "
                "console-script or '-m toolguard...' invocation launched "
                "with this environment imports THAT one instead of the "
                "installed distribution."
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
