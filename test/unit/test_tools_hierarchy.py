"""
Unit tests for toolguard.tools.hierarchy -- moving rules between config layers
(replay-gated) and reporting cross-layer duplication.
"""

import json
import unittest
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional, Tuple

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.constants import STATUS_EXECUTED
from toolguard.tools.config_access import per_layer_rules, with_layer_allow_replaced
from toolguard.tools.hierarchy import (
    HierarchyMigration,
    evaluate_migration,
    find_cross_layer_redundancies,
    migrate_config,
    migration_effect_to_dict,
)
from toolguard.tools.log_harvest import LogEntry


TOOL = "Bash"
ALLOW, DENY = "allow", "deny"
PROMOTE, DEMOTE, SIDEGRADE = "promote", "demote", "sidegrade"

# Level labels. Deliberately non-prefixing: an `assertIn`-style check on "proj"
# would also be satisfied by "project-local", so no label here is a substring of
# another, and neither is any path built from them.
PROJ, MID, USER = "proj", "mid", "user"

SRC_HOOK = "toolguard_hook"
SRC_RULES = "toolguard_hook_rules"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prov(specificity: int, name: str, source_type: str = SRC_HOOK) -> Provenance:
    """
    Provenance at a given specificity (0 = most specific).

    Every field that distinguishes one layer from another varies with the
    arguments -- ``path`` and ``specificity`` included, because two layers with
    an equal ``Provenance`` collapse onto one key in :func:`per_layer_rules`
    and two layers at one specificity are one level to the resolver.
    """
    return Provenance(
        level=name,
        source_type=source_type,
        file_format="toml",
        path=Path(f"/cfg/{name}-{specificity}.toml"),
        specificity=specificity,
    )


def _layer(provenance: Provenance, allow=None, deny=None, ask=None) -> ConfigLayer:
    """One config layer holding the given wrapper-free Bash pattern bodies."""
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
    """A Configuration over the given layers, most-specific first."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _entry(command: str, status: str = STATUS_EXECUTED) -> LogEntry:
    """One harvested corpus entry for `command`."""
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool=TOOL,
        command=command,
        status=status,
        rule_text=None,
        agent="main",
        log_file=None,
    )


def _levels(config: Configuration) -> Tuple[Tuple[str, int, Tuple[str, ...]], ...]:
    """
    The ``(level, specificity, allow-bodies)`` triple of every layer, in order.

    The fixture-integrity view. Two ways a hand-built multi-level config
    silently collapses -- every ``Provenance`` defaulting to specificity 0, and
    two layers sharing a ``Provenance`` so one layer's rules are attributed to
    both -- are visible here and invisible in a finding count.
    """
    return tuple(
        (lr.provenance.level, lr.provenance.specificity, lr.allow)
        for lr in per_layer_rules(config, TOOL)
    )


def _verdict(
    config: Configuration, command: str
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    What toolguard actually decides: ``(decision, deciding level, matched rule)``.

    ``matched_rule`` separates a real rule match from the fail-closed/undecidable
    floors, which produce the same verdict string with no rule.
    """
    verdict = decide(config, TOOL, command)
    level = verdict.provenance.level if verdict.provenance is not None else None
    return (verdict.decision, level, verdict.matched_rule)


def _findings(config: Configuration) -> List[Tuple[str, str, str]]:
    """Cross-layer findings as ``(pattern, redundant level, covering level)`` triples."""
    return [
        (f.pattern, f.redundant_provenance.level, f.covered_by_provenance.level)
        for f in find_cross_layer_redundancies(config, TOOL)
    ]


def _without(config: Configuration, provenance: Provenance, pattern: str):
    """The config with one allow pattern dropped from one layer."""
    return with_layer_allow_replaced(config, TOOL, provenance, {pattern}, [])


def _rules(config: Configuration, provenance: Provenance, list_type: str):
    """One layer's patterns from one permission list."""
    for lr in per_layer_rules(config, TOOL):
        if lr.provenance == provenance:
            return getattr(lr, list_type)
    return ()


# ---------------------------------------------------------------------------
# Fixture integrity
# ---------------------------------------------------------------------------


class TestFixtureIntegrity(unittest.TestCase):
    """
    The hierarchy fixtures really are hierarchies.

    Every other class here asserts something about layer precedence, so a
    fixture that collapsed to one level would make those assertions pass for a
    reason unrelated to what they claim.
    """

    def test_a_three_level_fixture_presents_three_distinct_levels(self):
        """
        Given three layers built at specificities 0, 1 and 2, each with its own rule
        When the per-layer view is taken
        Then all three survive, in order, each holding only its own rule.
        """
        config = _config(
            _layer(_prov(0, PROJ), allow=["aaa:*"]),
            _layer(_prov(1, MID), allow=["bbb:*"]),
            _layer(_prov(2, USER), allow=["ccc:*"]),
        )
        self.assertEqual(
            _levels(config),
            (
                (PROJ, 0, ("aaa:*",)),
                (MID, 1, ("bbb:*",)),
                (USER, 2, ("ccc:*",)),
            ),
        )

    def test_the_helper_varies_every_field_that_distinguishes_two_layers(self):
        """
        Given the three provenances the fixtures here are built from
        When their level, path and specificity are compared pairwise
        Then all three fields differ in every pair.

        Two layers sharing a Provenance are one dict key to per_layer_rules, so
        the later layer's rules stand in for both and the earlier layer's are
        lost -- with no error and no change in the layer count.
        """
        provenances = [_prov(0, PROJ), _prov(1, MID), _prov(2, USER)]
        self.assertEqual(
            [
                len({p.level for p in provenances}),
                len({p.path for p in provenances}),
                len({p.specificity for p in provenances}),
            ],
            [3, 3, 3],
        )

    def test_a_provenance_without_a_specificity_flattens_two_layers_into_one_level(
        self,
    ):
        """
        Given two layers whose Provenance omits specificity (so both default to 0)
        When the levels the resolver consumes are counted
        Then there is ONE, against TWO for the same layers built with specificities.

        The reason every fixture here passes specificity explicitly: a flattened
        config has no hierarchy left to test, and it looks like a two-layer
        config from the outside.
        """
        flat = _config(
            _layer(
                Provenance(PROJ, SRC_HOOK, "toml", Path("/cfg/a.toml")), allow=["a:*"]
            ),
            _layer(
                Provenance(USER, SRC_HOOK, "toml", Path("/cfg/b.toml")), allow=["b:*"]
            ),
        )
        graded = _config(
            _layer(_prov(0, PROJ), allow=["a:*"]), _layer(_prov(2, USER), allow=["b:*"])
        )
        self.assertEqual(
            (
                len(flat.permission_levels_with_provenance(TOOL)),
                len(graded.permission_levels_with_provenance(TOOL)),
            ),
            (1, 2),
        )


# ---------------------------------------------------------------------------
# migrate_config
# ---------------------------------------------------------------------------


class TestMigrateConfig(unittest.TestCase):
    """migrate_config relocates an allow rule between layers."""

    def test_rule_moves_from_source_to_target(self):
        """
        Given a project layer holding 'git status:*' and 'ls:*' and an empty user layer
        When migrate_config moves 'git status:*' project -> user
        Then the project layer keeps 'ls:*' alone and the user layer holds
             'git status:*' alone -- one rule moved, none duplicated, none lost.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj, allow=["git status:*", "ls:*"]), _layer(user))
        self.assertEqual(
            _levels(config), ((PROJ, 0, ("git status:*", "ls:*")), (USER, 2, ()))
        )

        migrated = migrate_config(
            config,
            HierarchyMigration(TOOL, ALLOW, "git status:*", proj, user, PROMOTE),
        )
        self.assertEqual(
            _levels(migrated), ((PROJ, 0, ("ls:*",)), (USER, 2, ("git status:*",)))
        )

    def test_a_target_layer_absent_from_the_config_does_not_lose_the_rule(self):
        """
        Given a migration whose target Provenance matches no layer in the config
        When migrate_config applies it
        Then the rule is not silently deleted: either the call is rejected, or
             the rule still exists somewhere in the result.

        migrate_config composes a removal and an addition, and
        with_layer_rules_replaced returns the config UNCHANGED when the
        provenance matches nothing -- so the removal lands and the addition
        does not.  Written so any fix satisfies it (a raise, a no-op, or
        creating the layer).
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        absent = _prov(5, "ghost")
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))

        try:
            migrated = migrate_config(
                config,
                HierarchyMigration(TOOL, ALLOW, "git status:*", proj, absent, PROMOTE),
            )
        except (
            ValueError,
            KeyError,
            LookupError,
        ):
            return

        surviving = [body for _, _, bodies in _levels(migrated) for body in bodies]
        self.assertIn("git status:*", surviving)


# ---------------------------------------------------------------------------
# evaluate_migration
# ---------------------------------------------------------------------------


class TestEvaluateMigration(unittest.TestCase):
    """Replay-gated evaluation of a hierarchy migration."""

    def test_simple_promotion_is_decision_neutral(self):
        """
        Given 'git status:*' at the project layer and an empty user layer
        When the rule is promoted to the user layer and a two-command corpus is replayed
        Then every count is zero, the effect is neutral, and the corpus really was
             decided by the rule -- before the move the project layer decides, after
             it the user layer does, both on the same matched rule.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj, allow=["git status:*", "ls:*"]), _layer(user))
        migration = HierarchyMigration(TOOL, ALLOW, "git status:*", proj, user, PROMOTE)

        self.assertEqual(
            _verdict(config, "git status"), ("allow", PROJ, "git status:*")
        )
        moved = migrate_config(config, migration)
        self.assertEqual(_verdict(moved, "git status"), ("allow", USER, "git status:*"))

        effect = evaluate_migration(
            config, migration, [_entry("git status"), _entry("ls -la")]
        )
        self.assertEqual(
            (
                effect.decision_neutral,
                effect.changed_count,
                effect.broadened_count,
                effect.tightened_count,
            ),
            (True, 0, 0, 0),
        )
        self.assertTrue(effect.scope_note.startswith("Promotion:"))

    def test_promotion_past_intermediate_deny_is_not_neutral(self):
        """
        Given project allow 'whoami:*', an intermediate-layer deny 'whoami:*', and
              an empty user layer
        When 'whoami:*' is promoted from project to user
        Then the intermediate deny takes the decision over: the corpus verdict goes
             from an allow decided at the project layer to a deny decided at the
             intermediate one, and the move is reported non-neutral and tightening.
        """
        proj, mid, user = _prov(0, PROJ), _prov(1, MID), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["whoami:*"]),
            _layer(mid, deny=["whoami:*"]),
            _layer(user),
        )
        migration = HierarchyMigration(TOOL, ALLOW, "whoami:*", proj, user, PROMOTE)

        self.assertEqual(_verdict(config, "whoami"), ("allow", PROJ, "whoami:*"))
        moved = migrate_config(config, migration)
        self.assertEqual(_verdict(moved, "whoami"), ("deny", MID, "whoami:*"))

        effect = evaluate_migration(config, migration, [_entry("whoami")])
        self.assertEqual(
            (
                effect.decision_neutral,
                effect.changed_count,
                effect.broadened_count,
                effect.tightened_count,
            ),
            (False, 1, 0, 1),
        )

    def test_scope_note_names_the_direction_and_the_two_loci_in_order(self):
        """
        Given a migration from the broader user layer down to the narrower project layer
        When evaluated
        Then the note opens with 'Demotion:' and names the source locus before the
             destination locus -- so a note built from the two loci the wrong way
             round does not satisfy it.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj), _layer(user, allow=["git status:*"]))
        migration = HierarchyMigration(TOOL, ALLOW, "git status:*", user, proj, DEMOTE)

        note = evaluate_migration(config, migration, [_entry("git status")]).scope_note
        self.assertTrue(note.startswith("Demotion:"), note)
        self.assertIn(user.describe(), note)
        self.assertIn(proj.describe(), note)
        self.assertLess(note.index(user.describe()), note.index(proj.describe()), note)

    def test_scope_note_for_a_move_within_one_level_reports_no_scope_change(self):
        """
        Given two layers at the SAME specificity (a ~/.claude file and a rules-directory
              file, which discovery places at one level) and a move between them
        When evaluated
        Then the note is neither a promotion nor a demotion.
        """
        claude = _prov(2, "claude", SRC_HOOK)
        rules = _prov(2, "rulesdir", SRC_RULES)
        config = _config(_layer(claude, allow=["git status:*"]), _layer(rules))
        migration = HierarchyMigration(
            TOOL, ALLOW, "git status:*", claude, rules, SIDEGRADE
        )

        note = evaluate_migration(config, migration, [_entry("git status")]).scope_note
        self.assertTrue(note.startswith("Same-level move"), note)
        self.assertNotIn("Promotion", note)
        self.assertNotIn("Demotion", note)

    def test_an_empty_corpus_is_distinguishable_from_a_corpus_that_changed_nothing(
        self,
    ):
        """
        Given the same migration evaluated against an empty corpus and against a
              one-entry corpus whose decision the move does not change
        When both effects are serialised
        Then the two payloads differ -- a consumer can tell "replayed and nothing
             changed" from "nothing was replayed".

        decision_neutral is True in both cases and no field records how many
        entries were examined, so the audit payload is byte-identical.  Ticket
        29's family.  Any distinguishing field satisfies this.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))
        migration = HierarchyMigration(TOOL, ALLOW, "git status:*", proj, user, PROMOTE)

        examined_nothing = migration_effect_to_dict(
            evaluate_migration(config, migration, [])
        )
        examined_one = migration_effect_to_dict(
            evaluate_migration(config, migration, [_entry("git status")])
        )
        self.assertNotEqual(examined_nothing, examined_one)


# ---------------------------------------------------------------------------
# Cross-layer redundancy
# ---------------------------------------------------------------------------


class TestCrossLayerRedundancy(unittest.TestCase):
    """
    Which allow rules find_cross_layer_redundancies reports. A finding means a
    broader layer repeats the body, not that dropping the specific copy is safe
    -- an intermediate deny between the two can flip the verdict.
    """

    def test_duplicated_rule_flagged_against_broader_layer(self):
        """
        Given 'git status:*' present in BOTH the project and the user layer
        When find_cross_layer_redundancies runs
        Then exactly one finding names the project copy as the redundant one and
             the user layer as its cover, with the specificities that ordered them.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["git status:*"]),
        )
        findings = find_cross_layer_redundancies(config, TOOL)
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            (
                findings[0].tool,
                findings[0].pattern,
                findings[0].redundant_provenance,
                findings[0].covered_by_provenance,
            ),
            (TOOL, "git status:*", proj, user),
        )

    def test_the_nearest_broader_layer_is_the_one_named_as_cover(self):
        """
        Given 'git status:*' at all three of the project, intermediate and user layers
        When find_cross_layer_redundancies runs
        Then the project copy is covered by the INTERMEDIATE layer and the
             intermediate copy by the user layer -- each finding names the nearest
             broader holder, not the broadest one.
        """
        proj, mid, user = _prov(0, PROJ), _prov(1, MID), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(mid, allow=["git status:*"]),
            _layer(user, allow=["git status:*"]),
        )
        self.assertEqual(
            _findings(config),
            [("git status:*", PROJ, MID), ("git status:*", MID, USER)],
        )

    def test_unique_rule_not_flagged(self):
        """
        Given 'git status:*' only at the project layer, the user layer holding 'ls:*'
        When find_cross_layer_redundancies runs
        Then nothing is flagged -- and adding the missing user copy to the same
             fixture does produce a finding, so the empty result is a verdict on
             the config and not a fixture that cannot report anything.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["ls:*"]),
        )
        duplicated = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["ls:*", "git status:*"]),
        )
        self.assertEqual(
            (_findings(config), _findings(duplicated)),
            ([], [("git status:*", PROJ, USER)]),
        )

    def test_broader_only_rule_not_flagged_as_redundant(self):
        """
        Given 'git status:*' present ONLY at the broader user layer
        When find_cross_layer_redundancies runs
        Then nothing is flagged -- redundancy drops the more-specific copy and there
             is none; moving the same rule down to the project layer as well does
             produce a finding.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj), _layer(user, allow=["git status:*"]))
        also_specific = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["git status:*"]),
        )
        self.assertEqual(
            (_findings(config), _findings(also_specific)),
            ([], [("git status:*", PROJ, USER)]),
        )

    def test_the_layer_named_as_cover_is_the_one_that_decides_after_the_drop(self):
        """
        Given a project and a user layer both holding 'git status:*', with nothing between
        When the copy the scan reports as redundant is removed
        Then the decision is unchanged and is now made by exactly the layer the
             finding named as its cover.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["git status:*"]),
        )
        finding = find_cross_layer_redundancies(config, TOOL)[0]

        self.assertEqual(
            _verdict(config, "git status"), ("allow", PROJ, "git status:*")
        )
        dropped = _without(config, finding.redundant_provenance, finding.pattern)
        self.assertEqual(
            _verdict(dropped, "git status"),
            ("allow", finding.covered_by_provenance.level, "git status:*"),
        )

    def test_a_reported_redundancy_survives_being_dropped(self):
        """
        Given project allow 'git push:*', an intermediate deny of the same body, and a
              user allow of it -- an ordinary project/directory/user hierarchy
        When each reported redundancy is dropped and the command re-decided
        Then the decision does not change.

        The scan reads allow lists only, so it cannot see the intervening deny
        that takes the decision over; the finding's own note tells the operator
        the copy "can be dropped".  Measured: allow (project) becomes deny
        (intermediate).  Any fix that stops reporting this, or gates it on a
        replay, satisfies the test.
        """
        proj, mid, user = _prov(0, PROJ), _prov(1, MID), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git push:*"]),
            _layer(mid, deny=["git push:*"]),
            _layer(user, allow=["git push:*"]),
        )
        before = _verdict(config, "git push")
        self.assertEqual(before, ("allow", PROJ, "git push:*"))

        for finding in find_cross_layer_redundancies(config, TOOL):
            dropped = _without(config, finding.redundant_provenance, finding.pattern)
            self.assertEqual(_verdict(dropped, "git push"), before, finding.note)

    def test_a_cover_that_matches_a_different_command_set_is_not_reported(self):
        """
        Given project allow 'git status:*' and user allow 'Git status:*'
        When find_cross_layer_redundancies runs
        Then the project rule is not reported as covered by the user one.

        The duplicate key is lowercased while every matcher is case-sensitive, so
        the two patterns match disjoint command sets.  Measured: dropping the
        reported-redundant project copy turns 'git status' from allow into ask.
        A second, independent route to an unsafe finding.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["Git status:*"]),
        )
        self.assertEqual(
            _verdict(config, "git status"), ("allow", PROJ, "git status:*")
        )
        self.assertEqual(_findings(config), [])

    def test_a_same_specificity_duplicate_in_another_file_is_reported(self):
        """
        Given 'git status:*' in both ~/.claude's hook file and a rules-directory file,
              which discovery places at the SAME specificity
        When find_cross_layer_redundancies runs
        Then the duplicate is reported.

        The cover search compares specificities strictly, so two layers at one
        level never cover each other -- and the within-layer scan in
        tools.redundancy never crosses layers, so nothing reports it.  The later
        copy is genuinely dead: both bodies land in one level and the first wins.
        """
        claude = _prov(2, "claude", SRC_HOOK)
        rules = _prov(2, "rulesdir", SRC_RULES)
        config = _config(
            _layer(claude, allow=["git status:*"]),
            _layer(rules, allow=["git status:*"]),
        )
        self.assertEqual(
            _levels(config),
            (("claude", 2, ("git status:*",)), ("rulesdir", 2, ("git status:*",))),
        )
        self.assertEqual(
            [f.pattern for f in find_cross_layer_redundancies(config, TOOL)],
            ["git status:*"],
        )

    def test_a_scan_that_examined_nothing_is_distinguishable_from_a_clean_scan(self):
        """
        Given a config with no layers at all, a config whose layers hold no rule for
              the tool, and a tool name no layer mentions
        When each is scanned and compared with a genuine clean scan of a populated config
        Then at least one of them is distinguishable from the clean result.

        All four return a bare [] today, so "no cross-layer duplication" and
        "nothing was compared" are the same answer.  Ticket 29's family.  Any
        distinguishing signal -- a raise, a richer result, a warning -- satisfies
        this; the test asserts only that the two cases are told apart.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        populated = _config(
            _layer(proj, allow=["git status:*"]),
            _layer(user, allow=["ls:*"]),
        )
        empty_layers = _config(_layer(proj), _layer(user))

        def scan(config, tool=TOOL):
            try:
                return ("ok", find_cross_layer_redundancies(config, tool))
            except Exception as exc:  # a raise is a perfectly good distinction
                return ("raised", type(exc).__name__)

        clean = scan(populated)
        examined_nothing = [
            scan(_config()),
            scan(empty_layers),
            scan(populated, "Nonexistent"),
        ]
        self.assertNotEqual(
            [clean] * len(examined_nothing),
            examined_nothing,
            "a scan that examined nothing reports exactly what a clean scan reports",
        )


class TestMigrationSerialization(unittest.TestCase):
    """migration_effect_to_dict produces the JSON-able form fed to the audit."""

    def test_serialized_effect_carries_every_field_of_the_migration(self):
        """
        Given an evaluated promotion of 'git status:*' from project to user
        When migration_effect_to_dict serializes it
        Then the result is JSON-serializable and equals the full expected payload
             -- so a field silently reading its opposite number (to_locus from the
             source layer, say) does not pass.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(_layer(proj, allow=["git status:*"]), _layer(user))
        migration = HierarchyMigration(
            TOOL, ALLOW, "git status:*", proj, user, "keep it everywhere"
        )
        effect = evaluate_migration(config, migration, [_entry("git status")])

        payload = migration_effect_to_dict(effect)
        json.dumps(payload)  # must not raise
        self.assertEqual(
            payload,
            {
                "tool": TOOL,
                "list_type": ALLOW,
                "pattern": "git status:*",
                "from_locus": proj.describe(),
                "to_locus": user.describe(),
                "from_specificity": 0,
                "to_specificity": 2,
                "rationale": "keep it everywhere",
                "decision_neutral": True,
                "changed_count": 0,
                "broadened_count": 0,
                "tightened_count": 0,
                "scope_note": effect.scope_note,
            },
        )

    def test_the_serialized_list_type_names_the_list_that_actually_changed(self):
        """
        Given a migration declaring list_type 'deny' for a body the source layer holds
              in BOTH its allow and its deny list
        When it is applied and serialized
        Then the list the payload names is the list that moved.

        migrate_config edits the allow list whatever list_type says, and the
        payload repeats the declared value -- so the audit record can describe an
        action that was taken on a different list.  Rejecting the unsupported
        list_type instead also satisfies this.
        """
        proj, user = _prov(0, PROJ), _prov(2, USER)
        config = _config(
            _layer(proj, allow=["whoami:*"], deny=["whoami:*"]), _layer(user)
        )
        migration = HierarchyMigration(TOOL, DENY, "whoami:*", proj, user, PROMOTE)

        try:
            migrated = migrate_config(config, migration)
        except ValueError:
            return

        moved_lists = {
            list_type
            for list_type in (ALLOW, DENY)
            if _rules(config, proj, list_type) != _rules(migrated, proj, list_type)
        }
        payload = migration_effect_to_dict(
            evaluate_migration(config, migration, [_entry("whoami")])
        )
        self.assertEqual(moved_lists, {payload["list_type"]})


if __name__ == "__main__":
    unittest.main()
