"""
Unit tests for toolguard.tools.self_permission.

Covers the declarative self-permission table, the "already permitted?"
evaluation (via the real decision engine), and the risk-aware recommendations.
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.self_permission import (
    evaluate_self_permissions,
    missing_self_permissions,
    required_self_permissions,
    self_permission_status_to_dict,
)


def _prov() -> Provenance:
    """Build a minimal toolguard_hook project-level Provenance."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=0,
    )


def _config(
    allow: Optional[List[str]] = None, ask: Optional[List[str]] = None
) -> Configuration:
    """Build a single-layer Configuration with wrapped Bash allow/ask patterns."""
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"Bash({p})" for p in (allow or [])],
                "deny": [],
                "ask": [f"Bash({p})" for p in (ask or [])],
            }
        }
    )
    layer = ConfigLayer(provenance=_prov(), content=content)
    return Configuration(layers=(layer,), start_dir=None)


class TestSelfPermissionTable(unittest.TestCase):
    """The declarative self-permission set matches the design guard-rails."""

    def test_only_audit_and_maintain_are_declared(self):
        """
        Given the required self-permission table
        When it is inspected
        Then it contains exactly toolguard-audit (read-only/allow) and
        toolguard-maintain (mutating/ask) -- hook entry points are excluded
        """
        perms = {p.command: p for p in required_self_permissions()}
        self.assertEqual(set(perms), {"toolguard-audit", "toolguard-maintain"})
        self.assertEqual(perms["toolguard-audit"].list_type, "allow")
        self.assertEqual(perms["toolguard-audit"].risk, "read-only")
        self.assertEqual(perms["toolguard-maintain"].list_type, "ask")
        self.assertEqual(perms["toolguard-maintain"].risk, "mutating")

    def test_no_hook_entry_points_present(self):
        """
        Given the required self-permission table
        When the declared commands are listed
        Then no hook entry point (toolguard / toolguard-session-start /
        toolguard-update-check) appears -- they never run as Bash calls
        """
        commands = {p.command for p in required_self_permissions()}
        self.assertNotIn("toolguard", commands)
        self.assertNotIn("toolguard-session-start", commands)
        self.assertNotIn("toolguard-update-check", commands)


class TestSelfPermissionEvaluation(unittest.TestCase):
    """Evaluation uses the real decision engine and is risk-aware."""

    def test_unconfigured_config_flags_audit_as_needed(self):
        """
        Given a config with no rules at all, where every tool resolves to
        'ask' rather than a fail-closed 'deny'
        When missing_self_permissions is evaluated
        Then only toolguard-audit needs action -- 'ask' would interrupt a
        read-only call, while for the mutating toolguard-maintain 'ask' is
        already the wanted per-invocation-consent posture
        """
        missing = missing_self_permissions(Configuration(layers=(), start_dir=None))
        by_cmd = {s.permission.command: s for s in missing}
        self.assertEqual(set(by_cmd), {"toolguard-audit"})
        self.assertEqual(by_cmd["toolguard-audit"].current_verdict, "ask")
        self.assertIn("ALLOW", by_cmd["toolguard-audit"].recommendation)

    def test_properly_permissioned_config_needs_no_action(self):
        """
        Given a config that ALLOWs toolguard-audit and ASKs toolguard-maintain
        When missing_self_permissions is evaluated
        Then nothing needs action (the skills can run and the mutating tool is
        gated by ask)
        """
        config = _config(allow=["toolguard-audit:*"], ask=["toolguard-maintain:*"])
        self.assertEqual(missing_self_permissions(config), [])

    def test_over_broad_mutating_allow_warns_but_is_not_missing(self):
        """
        Given a config that ALLOWs the mutating toolguard-maintain outright
        When it is evaluated
        Then it does not "need action" (it is permitted) but its recommendation
        warns that blanket-allowing a mutating tool bypasses human review
        """
        config = _config(allow=["toolguard-audit:*", "toolguard-maintain:*"])
        statuses = {s.permission.command: s for s in evaluate_self_permissions(config)}
        maintain = statuses["toolguard-maintain"]
        self.assertEqual(maintain.current_verdict, "allow")
        self.assertFalse(maintain.needs_action)
        self.assertIn("ASK", maintain.recommendation)

    def test_status_serialization_round_trips_fields(self):
        """
        Given an evaluated self-permission status
        When it is serialized to a dict
        Then the dict carries the nested permission, verdict, needs_action, and
        recommendation
        """
        status = evaluate_self_permissions(Configuration(layers=(), start_dir=None))[0]
        payload = self_permission_status_to_dict(status)
        self.assertEqual(payload["permission"]["command"], status.permission.command)
        self.assertEqual(payload["current_verdict"], status.current_verdict)
        self.assertEqual(payload["needs_action"], status.needs_action)
        self.assertIn("recommendation", payload)


if __name__ == "__main__":
    unittest.main()
