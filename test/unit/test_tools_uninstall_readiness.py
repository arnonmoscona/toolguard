"""
Unit tests for toolguard.tools.uninstall_readiness: the declarative table, its
claude_dir / settings_path substitution, the "already permitted?" evaluation
against the real decision engine, and serialization.
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.uninstall_readiness import (
    evaluate_uninstall_readiness_permissions,
    missing_uninstall_readiness_permissions,
    required_uninstall_readiness_permissions,
    uninstall_readiness_status_to_dict,
)

_CLAUDE_DIR = Path("/home/x/.claude")
_SETTINGS_PATH = _CLAUDE_DIR / "settings.json"


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
    permissions: Optional[Dict[str, List[str]]] = None,
    no_match_fallback: Optional[str] = None,
) -> Configuration:
    """Build a single-layer Configuration with the given raw permissions."""
    content: Dict[str, object] = {
        "permissions": {
            "allow": list((permissions or {}).get("allow", [])),
            "deny": list((permissions or {}).get("deny", [])),
            "ask": list((permissions or {}).get("ask", [])),
        }
    }
    if no_match_fallback is not None:
        content["takeover_mode"] = {
            "enabled": True,
            "no_match_fallback": no_match_fallback,
        }
    layer = ConfigLayer(provenance=_prov(), content=MappingProxyType(content))
    return Configuration(layers=(layer,), start_dir=None)


class TestUninstallReadinessTable(unittest.TestCase):
    """The declarative uninstall-readiness set matches the design guard-rails."""

    def test_every_entry_is_allow(self):
        """
        Given the required uninstall-readiness table
        When each entry's list_type is inspected
        Then every entry is 'allow' -- an 'ask' verdict was observed not
        reaching a prompt in a real install, so seeding 'ask' would not
        guarantee the uninstall completes
        """
        perms = required_uninstall_readiness_permissions(_CLAUDE_DIR, _SETTINGS_PATH)
        self.assertTrue(all(p.list_type == "allow" for p in perms))
        cd_entry = next(p for p in perms if p.description == "cd navigation")
        self.assertEqual(cd_entry.pattern, "cd:*")
        self.assertEqual(cd_entry.tool, "Bash")

    def test_table_covers_the_expected_eight_actions(self):
        """
        Given the required uninstall-readiness table
        When the descriptions are listed
        Then it covers exactly: cd, restoring native settings (Write and
        Edit), uninstalling the package, removing both toolguard config
        files, and removing both bundled skill directories
        """
        perms = required_uninstall_readiness_permissions(_CLAUDE_DIR, _SETTINGS_PATH)
        self.assertEqual(len(perms), 8)
        descriptions = {p.description for p in perms}
        self.assertEqual(
            descriptions,
            {
                "cd navigation",
                "restore native settings (Write)",
                "restore native settings (Edit)",
                "uninstall the package",
                "remove toolguard_hook.toml",
                "remove toolguard_hook.local.toml",
                "remove the security-audit skill",
                "remove the maintenance skill",
            },
        )

    def test_patterns_substitute_the_given_claude_dir_and_settings_path(self):
        """
        Given a specific claude_dir and settings_path
        When the table is built
        Then every path-bearing pattern is scoped under that exact claude_dir
        (config files, skill directories) or equals that exact settings_path
        (native-settings entries) -- no hardcoded ~/.claude leaks in
        """
        claude_dir = Path("/some/project/.claude")
        settings_path = claude_dir / "settings.local.json"
        perms = required_uninstall_readiness_permissions(claude_dir, settings_path)
        by_desc = {p.description: p for p in perms}

        self.assertEqual(
            by_desc["restore native settings (Write)"].pattern, str(settings_path)
        )
        self.assertEqual(
            by_desc["restore native settings (Edit)"].pattern, str(settings_path)
        )
        self.assertIn(
            str(claude_dir / "toolguard_hook.toml"),
            by_desc["remove toolguard_hook.toml"].pattern,
        )
        self.assertIn(
            str(claude_dir / "toolguard_hook.local.toml"),
            by_desc["remove toolguard_hook.local.toml"].pattern,
        )
        self.assertIn(
            str(claude_dir / "skills" / "toolguard-security-audit"),
            by_desc["remove the security-audit skill"].pattern,
        )
        self.assertIn(
            str(claude_dir / "skills" / "toolguard-maintenance"),
            by_desc["remove the maintenance skill"].pattern,
        )

    def test_user_vs_project_scope_produce_different_settings_filenames(self):
        """
        Given a user-scope settings.json path and a project-scope
        settings.local.json path
        When the table is built for each
        Then the native-settings entries reflect the exact filename passed in
        -- this module substitutes, it does not resolve scope
        """
        user_perms = required_uninstall_readiness_permissions(
            Path("/home/x/.claude"), Path("/home/x/.claude/settings.json")
        )
        project_perms = required_uninstall_readiness_permissions(
            Path("/repo/.claude"), Path("/repo/.claude/settings.local.json")
        )
        user_write = next(
            p for p in user_perms if p.description == "restore native settings (Write)"
        )
        project_write = next(
            p
            for p in project_perms
            if p.description == "restore native settings (Write)"
        )
        self.assertTrue(user_write.pattern.endswith("settings.json"))
        self.assertTrue(project_write.pattern.endswith("settings.local.json"))


class TestUninstallReadinessEvaluation(unittest.TestCase):
    """Evaluation of the table against a configuration, via the real decision engine."""

    def test_fresh_unconfigured_config_needs_every_entry(self):
        """
        Given a config with no rules at all (an entirely unconfigured tool
        resolves to 'ask', never a fail-closed 'deny')
        When missing_uninstall_readiness_permissions is evaluated
        Then all eight entries need action, each with a current verdict of
        'ask' -- only an explicit allow satisfies an entry
        """
        missing = missing_uninstall_readiness_permissions(
            _config(), _CLAUDE_DIR, _SETTINGS_PATH
        )
        self.assertEqual(len(missing), 8)
        self.assertTrue(all(s.current_verdict == "ask" for s in missing))

    def test_configured_but_non_matching_with_deny_fallback_flags_everything(self):
        """
        Given a config where Bash/Write/Edit each have SOME unrelated rule
        (so none of them is "entirely unconfigured") and
        no_match_fallback=deny
        When missing_uninstall_readiness_permissions is evaluated
        Then every entry needs action -- each would be hard-blocked (denied
        outright, not merely prompted) during a later uninstall
        """
        config = _config(
            permissions={
                "allow": ["Bash(git:*)", "Write(/tmp/**)", "Edit(/tmp/**)"],
            },
            no_match_fallback="deny",
        )
        missing = missing_uninstall_readiness_permissions(
            config, _CLAUDE_DIR, _SETTINGS_PATH
        )
        self.assertEqual(len(missing), 8)
        self.assertTrue(all(s.current_verdict == "deny" for s in missing))

    def test_fully_seeded_config_needs_no_action(self):
        """
        Given a config with every uninstall-readiness rule already seeded
        exactly as the table recommends
        When missing_uninstall_readiness_permissions is evaluated
        Then nothing needs action
        """
        perms = required_uninstall_readiness_permissions(_CLAUDE_DIR, _SETTINGS_PATH)
        allow = [f"{p.tool}({p.pattern})" for p in perms if p.list_type == "allow"]
        ask = [f"{p.tool}({p.pattern})" for p in perms if p.list_type == "ask"]
        config = _config(permissions={"allow": allow, "ask": ask})
        missing = missing_uninstall_readiness_permissions(
            config, _CLAUDE_DIR, _SETTINGS_PATH
        )
        self.assertEqual(missing, [])

    def test_allowed_destructive_action_needs_no_action_and_no_warning(self):
        """
        Given a config that ALLOWs the package-uninstall Bash command outright
        When it is evaluated
        Then it does not need action and its recommendation carries no warning
        -- allow is the intended end state for every entry in this table
        """
        config = _config(permissions={"allow": ["Bash(uv tool uninstall toolguard:*)"]})
        statuses = {
            s.permission.description: s
            for s in evaluate_uninstall_readiness_permissions(
                config, _CLAUDE_DIR, _SETTINGS_PATH
            )
        }
        entry = statuses["uninstall the package"]
        self.assertEqual(entry.current_verdict, "allow")
        self.assertFalse(entry.needs_action)
        self.assertEqual(entry.recommendation, "Already allowed -- no action needed.")

    def test_status_serialization_round_trips_fields(self):
        """
        Given an evaluated uninstall-readiness status
        When it is serialized to a dict
        Then the dict carries the nested permission, verdict, needs_action,
        and recommendation
        """
        status = evaluate_uninstall_readiness_permissions(
            _config(), _CLAUDE_DIR, _SETTINGS_PATH
        )[0]
        payload = uninstall_readiness_status_to_dict(status)
        self.assertEqual(
            payload["permission"]["description"], status.permission.description
        )
        self.assertEqual(payload["current_verdict"], status.current_verdict)
        self.assertEqual(payload["needs_action"], status.needs_action)
        self.assertIn("recommendation", payload)


if __name__ == "__main__":
    unittest.main()
