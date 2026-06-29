"""
Unit tests for toolguard.tools.hierarchy -- promoting/moving rules between config
layers (replay-gated) and detecting cross-layer redundancy.

Tests cover:
- migrate_config relocates the rule (gone from source layer, present in target).
- evaluate_migration: a safe promotion is decision-neutral; a promotion past an
  intermediate deny is caught as non-neutral (tightened).
- scope_note direction (promotion vs demotion vs same-level).
- find_cross_layer_redundancies: a specific rule duplicated in a broader layer is
  flagged; a rule unique to one layer is not; direction is respected.
"""

import json
import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.config_access import per_layer_rules
from toolguard.tools.hierarchy import (
    HierarchyMigration,
    evaluate_migration,
    find_cross_layer_redundancies,
    migrate_config,
    migration_effect_to_dict,
)
from toolguard.tools.log_harvest import LogEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prov(specificity: int, name: str) -> Provenance:
    """Provenance at a given specificity (0 = most specific)."""
    return Provenance(
        level=name,
        source_type="toolguard_hook",
        file_format="toml",
        path=Path(f"/cfg/{name}.toml"),
        specificity=specificity,
    )


def _layer(provenance: Provenance, allow=None, deny=None, ask=None) -> ConfigLayer:
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"Bash({p})" for p in (allow or [])],
                "deny": [f"Bash({p})" for p in (deny or [])],
                "ask": [f"Bash({p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=provenance, content=content)


def _config(*layers: ConfigLayer) -> Configuration:
    return Configuration(layers=tuple(layers), start_dir=None)


def _entry(command: str, status: str = "EXECUTED") -> LogEntry:
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool="Bash",
        command=command,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


def _allow_bodies(config: Configuration, provenance: Provenance) -> List[str]:
    """The wrapper-free allow bodies for a given layer provenance."""
    for lr in per_layer_rules(config, "Bash"):
        if lr.provenance == provenance:
            return list(lr.allow)
    return []


# ---------------------------------------------------------------------------
# migrate_config
# ---------------------------------------------------------------------------


class TestMigrateConfig(unittest.TestCase):
    """migrate_config relocates a rule between layers."""

    def test_rule_moves_from_source_to_target(self):
        """
        Given a project layer holding 'git status:*' and an empty user layer
        When migrate_config moves the rule project -> user
        Then the rule is absent from the project layer and present in the user layer.
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))
        migration = HierarchyMigration(
            "Bash", "allow", "git status:*", proj, user, "promote"
        )
        migrated = migrate_config(config, migration)
        self.assertNotIn("git status:*", _allow_bodies(migrated, proj))
        self.assertIn("git status:*", _allow_bodies(migrated, user))


# ---------------------------------------------------------------------------
# evaluate_migration
# ---------------------------------------------------------------------------


class TestEvaluateMigration(unittest.TestCase):
    """Replay-gated evaluation of a hierarchy migration."""

    def test_simple_promotion_is_decision_neutral(self):
        """
        Given 'git status:*' at the project layer and an empty user layer
        When the rule is promoted to the user layer and the corpus is replayed
        Then no decision changes (decision_neutral True) and the scope note flags
             the promotion's cross-context broadening.
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))
        migration = HierarchyMigration(
            "Bash", "allow", "git status:*", proj, user, "promote"
        )
        effect = evaluate_migration(config, migration, [_entry("git status")])
        self.assertTrue(effect.decision_neutral)
        self.assertEqual(effect.changed_count, 0)
        self.assertIn("Promotion", effect.scope_note)

    def test_promotion_past_intermediate_deny_is_not_neutral(self):
        """
        Given project allow 'whoami:*', an intermediate-layer deny 'whoami:*', and
              an empty user layer (so 'whoami' currently resolves allow via the
              most-specific project rule)
        When 'whoami:*' is promoted from project to user
        Then the intermediate deny now wins: the move is non-neutral and tightens
             one corpus decision.
        """
        proj, mid, user = _prov(0, "proj"), _prov(1, "mid"), _prov(2, "user")
        config = _config(
            _layer(proj, allow=["whoami:*"]),
            _layer(mid, deny=["whoami:*"]),
            _layer(user),
        )
        migration = HierarchyMigration("Bash", "allow", "whoami:*", proj, user, "promote")
        effect = evaluate_migration(config, migration, [_entry("whoami")])
        self.assertFalse(effect.decision_neutral)
        self.assertEqual(effect.tightened_count, 1)

    def test_scope_note_demotion_direction(self):
        """
        Given a migration from a broader (user) layer down to a narrower (project) layer
        When evaluated
        Then the scope note describes a demotion.
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(_layer(proj), _layer(user, allow=["git status:*"]))
        migration = HierarchyMigration("Bash", "allow", "git status:*", user, proj, "demote")
        effect = evaluate_migration(config, migration, [_entry("git status")])
        self.assertIn("Demotion", effect.scope_note)


# ---------------------------------------------------------------------------
# Cross-layer redundancy
# ---------------------------------------------------------------------------


class TestCrossLayerRedundancy(unittest.TestCase):
    """A specific rule already present in a broader layer is redundant."""

    def test_duplicated_rule_flagged_against_broader_layer(self):
        """
        Given 'git status:*' present in BOTH the project and the user layer
        When find_cross_layer_redundancies runs
        Then the project (more-specific) copy is flagged as covered by the user layer.
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["git status:*"]),
        )
        findings = find_cross_layer_redundancies(config, "Bash")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].pattern, "git status:*")
        self.assertEqual(findings[0].redundant_provenance, proj)
        self.assertEqual(findings[0].covered_by_provenance, user)

    def test_unique_rule_not_flagged(self):
        """
        Given 'git status:*' only at the project layer (not at the broader layer)
        When find_cross_layer_redundancies runs
        Then nothing is flagged (there is no broader copy covering it).
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["ls:*"]),
        )
        self.assertEqual(find_cross_layer_redundancies(config, "Bash"), [])

    def test_broader_only_rule_not_flagged_as_redundant(self):
        """
        Given 'git status:*' present ONLY at the broader user layer
        When find_cross_layer_redundancies runs
        Then nothing is flagged (redundancy drops the more-specific copy, and there
             is none here).
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(_layer(proj), _layer(user, allow=["git status:*"]))
        self.assertEqual(find_cross_layer_redundancies(config, "Bash"), [])


class TestMigrationSerialization(unittest.TestCase):
    """migration_effect_to_dict produces the JSON-able form fed to the audit."""

    def test_serialized_effect_is_json_able_and_complete(self):
        """
        Given an evaluated promotion of 'git status:*' from project to user
        When migration_effect_to_dict serializes it
        Then the result is JSON-serializable and carries the migration identity,
             the neutrality flag, the target specificity, and the scope note.
        """
        proj, user = _prov(0, "proj"), _prov(2, "user")
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))
        migration = HierarchyMigration(
            "Bash", "allow", "git status:*", proj, user, "promote"
        )
        effect = evaluate_migration(config, migration, [_entry("git status")])

        d = migration_effect_to_dict(effect)
        json.dumps(d)  # must not raise
        self.assertEqual(d["tool"], "Bash")
        self.assertEqual(d["pattern"], "git status:*")
        self.assertTrue(d["decision_neutral"])
        self.assertEqual(d["to_specificity"], 2)
        self.assertIn("Promotion", d["scope_note"])


if __name__ == "__main__":
    unittest.main()
