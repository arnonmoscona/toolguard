"""
Unit tests for :mod:`toolguard.tools.decision_ledger`, the store for the maintenance
skill's settled meta-decisions.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from toolguard.tools import decision_ledger as dl


class TestDecisionIdentity(unittest.TestCase):
    """Decision identity is level-independent and derived from what it is about."""

    def test_id_is_kind_family_target(self):
        """
        Given a kind, family, and target
        When the decision id is computed
        Then it is the stable kind::family::target slug
        """
        self.assertEqual(
            dl.decision_id("reject-consolidation", "git-diff", "^git (diff|log)"),
            "reject-consolidation::git-diff::^git (diff|log)",
        )

    def test_same_target_same_id_across_levels(self):
        """
        Given two decisions about the same thing recorded at different levels
        When their ids are compared
        Then they are equal (identity does not include the storing level)
        """
        a = dl.new_decision(
            "reject-promotion", "git", "promote:user", "reject", "", "project"
        )
        b = dl.new_decision(
            "reject-promotion", "git", "promote:user", "reject", "", "user"
        )
        self.assertEqual(a.id, b.id)


class TestValidation(unittest.TestCase):
    """Unknown enum values are rejected loudly at construction time."""

    def test_unknown_kind_raises(self):
        """
        Given a decision built with an unrecognised kind
        When new_decision is called
        Then a LedgerError is raised naming the field
        """
        with self.assertRaises(dl.LedgerError):
            dl.new_decision("bogus-kind", "fam", "t", "reject", "", "project")

    def test_unknown_decision_raises(self):
        """
        Given a decision built with an unrecognised disposition
        When new_decision is called
        Then a LedgerError is raised
        """
        with self.assertRaises(dl.LedgerError):
            dl.new_decision("custom", "fam", "t", "maybe", "", "project")

    def test_unknown_level_raises(self):
        """
        Given a decision built for an unrecognised level
        When new_decision is called
        Then a LedgerError is raised
        """
        with self.assertRaises(dl.LedgerError):
            dl.new_decision("custom", "fam", "t", "reject", "", "global")


class TestLevelPaths(unittest.TestCase):
    """Ledger files live at level-scoped, config-mirroring locations."""

    def test_project_path_anchors_at_vcs_root(self):
        """
        Given a nested directory under a .git-rooted project
        When the project ledger path is resolved
        Then it is <root>/.claude/toolguard_decisions.json regardless of start depth
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            nested = root / "pkg" / "sub"
            nested.mkdir(parents=True)
            self.assertEqual(
                dl.project_ledger_path(nested),
                root / ".claude" / "toolguard_decisions.json",
            )

    def test_project_path_falls_back_to_start_when_no_root(self):
        """
        Given a directory with no VCS/pyproject marker up to home
        When the project ledger path is resolved
        Then it anchors at the start directory itself (a record still lands sensibly)
        """
        with tempfile.TemporaryDirectory() as d:
            start = Path(d)
            with mock.patch(
                "toolguard.tools.decision_ledger.find_project_root",
                side_effect=RuntimeError("no root"),
            ):
                self.assertEqual(
                    dl.project_ledger_path(start),
                    start / ".claude" / "toolguard_decisions.json",
                )

    def test_user_level_uses_toolguard_namespace(self):
        """
        Given the user level
        When the ledger path is resolved
        Then it is under ~/.toolguard (not ~/.claude), toolguard's own namespace
        """
        self.assertEqual(
            dl.ledger_path_for_level("user", Path(".")),
            dl.USER_LEDGER_PATH,
        )
        self.assertTrue(str(dl.USER_LEDGER_PATH).endswith(".toolguard/decisions.json"))


class TestRecordAndLoad(unittest.TestCase):
    """Recording is idempotent by id; loading round-trips faithfully."""

    def test_record_then_load_roundtrips(self):
        """
        Given a decision recorded to a fresh project ledger
        When the ledger is loaded back
        Then the single decision is returned with its fields intact
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            dec = dl.new_decision(
                "reject-consolidation",
                "git-diff",
                "^git (diff|log)",
                "reject",
                "keep apart",
                "project",
            )
            path = dl.record_decision(root, dec)
            self.assertTrue(path.exists())
            loaded = dl.load_ledger(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].rationale, "keep apart")
            self.assertEqual(loaded[0].level, "project")

    def test_recording_same_id_replaces_in_place(self):
        """
        Given a decision recorded, then a second decision with the same id
        When both have been recorded
        Then the ledger holds one entry (the later one), not a duplicate
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            first = dl.new_decision(
                "reject-removal", "cat-env", "keep", "reject", "v1", "project"
            )
            dl.record_decision(root, first)
            second = dl.new_decision(
                "reject-removal", "cat-env", "keep", "reject", "v2", "project"
            )
            path = dl.record_decision(root, second)
            loaded = dl.load_ledger(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].rationale, "v2")

    def test_missing_ledger_loads_empty(self):
        """
        Given a ledger path that does not exist
        When it is loaded
        Then an empty tuple is returned (a missing ledger is normal, not an error)
        """
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(dl.load_ledger(Path(d) / "nope.json"), ())

    def test_written_file_carries_schema_and_level(self):
        """
        Given a recorded project decision
        When the raw JSON file is inspected
        Then it carries the schema tag and level once at the file level
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            dec = dl.new_decision("custom", "fam", "t", "reject", "", "project")
            path = dl.record_decision(root, dec)
            data = json.loads(path.read_text())
            self.assertEqual(data["schema"], dl.LEDGER_SCHEMA)
            self.assertEqual(data["level"], "project")
            self.assertNotIn("level", data["decisions"][0])


class TestQuery(unittest.TestCase):
    """The suppression query only silences a matching ``reject``."""

    def _decisions(self):
        return [
            dl.new_decision(
                "reject-consolidation", "git", "^git (a|b)", "reject", "", "project"
            ),
            dl.new_decision(
                "reject-promotion", "rm", "promote:user", "accept", "", "user"
            ),
        ]

    def test_matching_reject_is_suppressed(self):
        """
        Given a recorded reject-consolidation decision
        When the same suggestion is queried
        Then is_suppressed returns True
        """
        self.assertTrue(
            dl.is_suppressed(
                self._decisions(), "reject-consolidation", "git", "^git (a|b)"
            )
        )

    def test_matching_accept_is_not_suppressed(self):
        """
        Given a recorded decision whose disposition is 'accept'
        When the same suggestion is queried
        Then is_suppressed returns False (only a reject silences a re-raise)
        """
        self.assertFalse(
            dl.is_suppressed(
                self._decisions(), "reject-promotion", "rm", "promote:user"
            )
        )

    def test_non_matching_target_is_not_suppressed(self):
        """
        Given decisions that do not cover a particular target
        When that target is queried
        Then is_suppressed returns False
        """
        self.assertFalse(
            dl.is_suppressed(self._decisions(), "reject-consolidation", "git", "^other")
        )


class TestMerge(unittest.TestCase):
    """load_merged concatenates project then user ledgers."""

    def test_merged_includes_both_levels(self):
        """
        Given a project ledger and a user ledger each with one decision
        When load_merged runs
        Then both decisions are returned, project first
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            (root / ".git").mkdir(parents=True)
            user_ledger = Path(d) / "user_decisions.json"
            proj_dec = dl.new_decision("custom", "p", "t", "reject", "", "project")
            dl.record_decision(root, proj_dec)
            user_dec = dl.new_decision("custom", "u", "t", "reject", "", "user")
            with mock.patch.object(dl, "USER_LEDGER_PATH", user_ledger):
                dl.record_decision(root, user_dec)
                merged = dl.load_merged(root)
        self.assertEqual([m.family_id for m in merged], ["p", "u"])


class TestCorruptLedger(unittest.TestCase):
    """A present-but-corrupt ledger fails loud rather than silently dropping decisions."""

    def test_invalid_json_raises(self):
        """
        Given a ledger file that is not valid JSON
        When it is loaded
        Then a LedgerError is raised (settled decisions must never be silently lost)
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.write_text("{ not json")
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)

    def test_missing_decisions_array_raises(self):
        """
        Given a JSON ledger with no 'decisions' array
        When it is loaded
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.write_text(
                json.dumps({"schema": dl.LEDGER_SCHEMA, "level": "project"})
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)

    def test_decisions_not_a_list_raises(self):
        """
        Given a ledger whose 'decisions' value is not an array
        When it is loaded
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.write_text(
                json.dumps(
                    {"schema": dl.LEDGER_SCHEMA, "level": "project", "decisions": {}}
                )
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)

    def test_entry_missing_required_field_raises(self):
        """
        Given a ledger entry missing a required field
        When it is loaded
        Then a LedgerError is raised naming the malformed entry
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": dl.LEDGER_SCHEMA,
                        "level": "project",
                        "decisions": [{"kind": "custom", "family_id": "x"}],
                    }
                )
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)

    def test_entry_invalid_enum_from_file_raises(self):
        """
        Given a persisted ledger entry whose 'decision' value is not recognised
        When it is loaded (the file-read validation path, not just construction)
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.write_text(
                json.dumps(
                    {
                        "schema": dl.LEDGER_SCHEMA,
                        "level": "project",
                        "decisions": [
                            {
                                "kind": "custom",
                                "family_id": "x",
                                "target": "t",
                                "decision": "banish",
                            }
                        ],
                    }
                )
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)


if __name__ == "__main__":
    unittest.main()
