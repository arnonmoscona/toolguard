"""
Unit tests for :mod:`toolguard.tools.decision_ledger`, the store for the maintenance
skill's settled meta-decisions.
"""

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from importlib import metadata
from pathlib import Path
from unittest import mock

from toolguard.tools import decision_ledger as dl

#: The user ledger as it reads against the real home directory. Captured before any
#: test redirects it.
REAL_USER_LEDGER_PATH = dl.user_ledger_path()


def _signature(path: Path):
    """``(exists, size, mtime)`` for *path* -- enough to notice any write to it."""
    if not path.exists():
        return (False, 0, 0.0)
    stat = path.stat()
    return (True, stat.st_size, stat.st_mtime)


#: Taken once, at import, so every test can assert the developer's own ledger is untouched.
REAL_USER_LEDGER_SIGNATURE = _signature(REAL_USER_LEDGER_PATH)


class LedgerIsolationMixin:
    """Redirects the user ledger into a temp dir and proves the redirect took effect.

    A user-level ``record_decision`` without this writes the developer's real
    ``~/.toolguard/decisions.json``.
    """

    def setUp(self):
        super().setUp()
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.user_ledger = Path(tmp.name) / ".toolguard" / "decisions.json"
        patcher = mock.patch.object(
            dl, "user_ledger_path", return_value=self.user_ledger
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertNotEqual(self.user_ledger, REAL_USER_LEDGER_PATH)
        # Proof that the patch is consulted at the production read site, rather than
        # merely bound on the module: an inert redirect here is silent and writes home.
        self.assertEqual(dl.ledger_path_for_level("user", Path(".")), self.user_ledger)
        self.addCleanup(self._assert_real_user_ledger_untouched)

    def _assert_real_user_ledger_untouched(self):
        """Fail if the test wrote the developer's real ``~/.toolguard/decisions.json``."""
        self.assertEqual(_signature(REAL_USER_LEDGER_PATH), REAL_USER_LEDGER_SIGNATURE)


class TestDecisionIdentity(LedgerIsolationMixin, unittest.TestCase):
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


class TestValidation(LedgerIsolationMixin, unittest.TestCase):
    """Unknown enum values are rejected loudly at construction time."""

    def test_unknown_kind_raises(self):
        """
        Given a decision built with an unrecognised kind
        When new_decision is called
        Then a LedgerError is raised naming the field
        """
        with self.assertRaises(dl.LedgerError) as caught:
            dl.new_decision("bogus-kind", "fam", "t", "reject", "", "project")
        self.assertIn("bogus-kind", str(caught.exception))

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


class TestStamping(LedgerIsolationMixin, unittest.TestCase):
    """new_decision stamps the time and the running version onto every decision."""

    def test_records_the_current_local_time(self):
        """
        Given a decision built without an explicit timestamp
        When new_decision returns
        Then recorded_at is an ISO timestamp of roughly now
        """
        stamped = dl.new_decision("custom", "f", "t", "reject", "", "project")
        self.assertLess(
            abs(datetime.fromisoformat(stamped.recorded_at) - datetime.now()),
            timedelta(minutes=5),
        )

    def test_an_explicit_timestamp_wins(self):
        """
        Given an explicit recorded_at
        When new_decision returns
        Then that value is used verbatim rather than the clock
        """
        stamped = dl.new_decision(
            "custom",
            "f",
            "t",
            "reject",
            "",
            "project",
            recorded_at="2020-01-02T03:04:05",
        )
        self.assertEqual(stamped.recorded_at, "2020-01-02T03:04:05")

    def test_records_the_installed_distribution_version(self):
        """
        Given an installed toolguard distribution
        When a decision is built
        Then toolguard_version is that distribution's version
        """
        with mock.patch.object(dl.metadata, "version", return_value="9.9.9-probe"):
            self.assertEqual(dl._toolguard_version(), "9.9.9-probe")
            stamped = dl.new_decision("custom", "f", "t", "reject", "", "project")
        self.assertEqual(stamped.toolguard_version, "9.9.9-probe")

    def test_an_explicit_version_wins(self):
        """
        Given an explicit toolguard_version
        When new_decision returns
        Then that value is used rather than the installed distribution's
        """
        with mock.patch.object(dl.metadata, "version", return_value="9.9.9-probe"):
            stamped = dl.new_decision(
                "custom", "f", "t", "reject", "", "project", toolguard_version="0.0.1"
            )
        self.assertEqual(stamped.toolguard_version, "0.0.1")

    def test_version_is_unknown_when_the_package_is_not_installed(self):
        """
        Given toolguard running from a source tree with no installed distribution
        When a decision is built
        Then toolguard_version is 'unknown' rather than raising
        """
        with mock.patch.object(
            dl.metadata, "version", side_effect=metadata.PackageNotFoundError
        ):
            stamped = dl.new_decision("custom", "f", "t", "reject", "", "project")
        self.assertEqual(stamped.toolguard_version, "unknown")


class TestLevelPaths(LedgerIsolationMixin, unittest.TestCase):
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

    def test_user_level_ignores_the_project_directory(self):
        """
        Given a project directory that has its own ledger location
        When the user level's path is resolved for it
        Then it is the user ledger, not that project's
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            self.assertEqual(dl.ledger_path_for_level("user", root), self.user_ledger)
            self.assertNotEqual(
                dl.ledger_path_for_level("user", root), dl.project_ledger_path(root)
            )

    def test_user_ledger_sits_in_the_toolguard_namespace_under_home(self):
        """
        Given the user-level ledger path
        When its location is inspected
        Then it is ~/.toolguard/decisions.json -- toolguard's own namespace, not ~/.claude
        """
        self.assertEqual(
            REAL_USER_LEDGER_PATH, Path.home() / ".toolguard" / "decisions.json"
        )

    def test_unknown_level_has_no_path(self):
        """
        Given a level that is neither project nor user
        When a ledger path is requested for it
        Then a LedgerError naming the level is raised rather than a path returned
        """
        with self.assertRaises(dl.LedgerError) as caught:
            dl.ledger_path_for_level("global", Path("."))
        self.assertIn("global", str(caught.exception))


class TestRecordAndLoad(LedgerIsolationMixin, unittest.TestCase):
    """Recording is idempotent by id; loading round-trips faithfully."""

    def test_record_then_load_roundtrips(self):
        """
        Given a decision recorded to a fresh project ledger
        When the ledger is loaded back
        Then the single decision compares equal to the one recorded, field for field
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
            self.assertEqual(dl.load_ledger(path), (dec,))

    def test_persisted_entry_carries_its_stable_id(self):
        """
        Given a recorded decision
        When the raw JSON entry is inspected
        Then it carries the kind::family::target id that --ledger-show reports
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            dec = dl.new_decision("custom", "fam", "tgt", "reject", "", "project")
            path = dl.record_decision(root, dec)
            entry = json.loads(path.read_text())["decisions"][0]
            self.assertEqual(entry["id"], dl.decision_id("custom", "fam", "tgt"))

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

    def test_a_replacement_is_written_last(self):
        """
        Given three decisions recorded and then the first one re-recorded
        When the ledger is loaded
        Then the other two keep their order and the replacement is at the end
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            for family in ("a", "b", "c"):
                dl.record_decision(
                    root,
                    dl.new_decision("custom", family, "t", "reject", "", "project"),
                )
            path = dl.record_decision(
                root, dl.new_decision("custom", "a", "t", "reject", "again", "project")
            )
            self.assertEqual(
                [d.family_id for d in dl.load_ledger(path)], ["b", "c", "a"]
            )

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
            self.assertEqual(data["schema"], "toolguard-decision-ledger/1")
            self.assertEqual(data["schema"], dl.LEDGER_SCHEMA)
            self.assertEqual(data["level"], "project")
            self.assertNotIn("level", data["decisions"][0])

    def test_user_level_record_writes_the_user_ledger_tagged_user(self):
        """
        Given a decision whose level is 'user'
        When it is recorded from within a project
        Then it lands in the user ledger and that file is tagged level 'user'
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            dec = dl.new_decision("custom", "fam", "t", "reject", "", "user")
            path = dl.record_decision(root, dec)
            self.assertEqual(path, self.user_ledger)
            self.assertFalse(dl.project_ledger_path(root).exists())
            self.assertEqual(json.loads(path.read_text())["level"], "user")


class TestQuery(LedgerIsolationMixin, unittest.TestCase):
    """The suppression query only silences a matching ``reject``."""

    def _decisions(self):
        """One rejected consolidation and one accepted promotion, at different levels."""
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

    def test_find_decision_returns_the_matching_record(self):
        """
        Given a pool of decisions
        When one is looked up by kind, family and target
        Then that decision is returned, and an unknown target returns None
        """
        pool = self._decisions()
        self.assertIs(
            dl.find_decision(pool, "reject-promotion", "rm", "promote:user"), pool[1]
        )
        self.assertIsNone(dl.find_decision(pool, "reject-promotion", "rm", "other"))


class TestMerge(LedgerIsolationMixin, unittest.TestCase):
    """load_merged concatenates project then user ledgers."""

    def test_merged_includes_both_levels(self):
        """
        Given a project ledger and a user ledger each with one decision
        When load_merged runs
        Then both decisions are returned, project first, each labelled with its level
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "proj"
            (root / ".git").mkdir(parents=True)
            dl.record_decision(
                root, dl.new_decision("custom", "p", "t", "reject", "", "project")
            )
            dl.record_decision(
                root, dl.new_decision("custom", "u", "t", "reject", "", "user")
            )
            self.assertTrue(self.user_ledger.exists())
            merged = dl.load_merged(root)
            self.assertEqual([m.family_id for m in merged], ["p", "u"])
            self.assertEqual([m.level for m in merged], ["project", "user"])


class TestLevelAttribution(LedgerIsolationMixin, unittest.TestCase):
    """Which ledger a decision came from decides its level -- not what the file claims."""

    def test_a_project_ledger_claiming_user_level_cannot_redirect_the_write(self):
        """
        Given a project ledger file whose body claims level 'user'
        When its decisions are loaded and re-recorded
        Then the claim is rejected or ignored, and nothing is written to the user ledger
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            path = dl.project_ledger_path(root)
            path.parent.mkdir(parents=True)
            path.write_text(
                json.dumps(
                    {
                        "schema": dl.LEDGER_SCHEMA,
                        "level": "user",
                        "decisions": [
                            {
                                "kind": "custom",
                                "family_id": "x",
                                "target": "t",
                                "decision": "reject",
                            }
                        ],
                    }
                )
            )
            try:
                loaded = dl.load_ledger(path)
            except dl.LedgerError:
                return  # rejecting the mismatched claim outright also closes the redirect
            self.assertEqual([d.level for d in loaded], ["project"])
            self.assertEqual(dl.record_decision(root, loaded[0]), path)
            self.assertFalse(self.user_ledger.exists())

    def test_a_user_ledger_without_a_level_key_is_not_labelled_project(self):
        """
        Given a hand-written user ledger with no 'level' key
        When it is merged
        Then its decisions are labelled 'user', the level of the file they were found in
        """
        self.user_ledger.parent.mkdir(parents=True)
        self.user_ledger.write_text(
            json.dumps(
                {
                    "schema": dl.LEDGER_SCHEMA,
                    "decisions": [
                        {
                            "kind": "custom",
                            "family_id": "hand-written",
                            "target": "t",
                            "decision": "reject",
                        }
                    ],
                }
            )
        )
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            merged = dl.load_merged(root)
        self.assertEqual([m.level for m in merged], ["user"])


class TestCorruptLedger(LedgerIsolationMixin, unittest.TestCase):
    """A present-but-corrupt ledger fails loud rather than silently dropping decisions."""

    def _ledger(self, tmpdir, payload):
        """Write *payload* (already-encoded text) as a ledger file and return its path."""
        path = Path(tmpdir) / "toolguard_decisions.json"
        path.write_text(payload)
        return path

    def test_invalid_json_raises(self):
        """
        Given a ledger file that is not valid JSON
        When it is loaded
        Then a LedgerError is raised (settled decisions must never be silently lost)
        """
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, "{ not json"))

    def test_unreadable_ledger_raises(self):
        """
        Given a ledger path that exists but cannot be read as a file
        When it is loaded
        Then a LedgerError is raised rather than the OS error escaping
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_decisions.json"
            path.mkdir()
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(path)

    def test_non_object_json_raises(self):
        """
        Given a ledger file holding a bare JSON scalar
        When it is loaded
        Then a LedgerError is raised rather than a TypeError escaping
        """
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, "5"))

    def test_missing_decisions_array_raises(self):
        """
        Given a JSON ledger with no 'decisions' array
        When it is loaded
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            payload = json.dumps({"schema": dl.LEDGER_SCHEMA, "level": "project"})
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, payload))

    def test_decisions_not_a_list_raises(self):
        """
        Given a ledger whose 'decisions' value is not an array
        When it is loaded
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            payload = json.dumps(
                {"schema": dl.LEDGER_SCHEMA, "level": "project", "decisions": {}}
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, payload))

    def test_entry_missing_any_required_field_raises(self):
        """
        Given a ledger entry missing one of kind, family_id, target or decision
        When it is loaded
        Then a LedgerError is raised whose message shows the malformed entry
        """
        complete = {
            "kind": "custom",
            "family_id": "x",
            "target": "t",
            "decision": "reject",
        }
        for field in complete:
            with self.subTest(missing=field):
                entry = {k: v for k, v in complete.items() if k != field}
                with tempfile.TemporaryDirectory() as d:
                    payload = json.dumps(
                        {
                            "schema": dl.LEDGER_SCHEMA,
                            "level": "project",
                            "decisions": [entry],
                        }
                    )
                    with self.assertRaises(dl.LedgerError) as caught:
                        dl.load_ledger(self._ledger(d, payload))
                self.assertIn(repr(entry), str(caught.exception))

    def test_entry_that_is_not_an_object_raises(self):
        """
        Given a ledger whose 'decisions' array holds something other than objects
        When it is loaded
        Then a LedgerError is raised rather than a TypeError escaping
        """
        with tempfile.TemporaryDirectory() as d:
            payload = json.dumps(
                {
                    "schema": dl.LEDGER_SCHEMA,
                    "level": "project",
                    "decisions": ["not an object"],
                }
            )
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, payload))

    def test_entry_invalid_enum_from_file_raises(self):
        """
        Given a persisted ledger entry whose 'decision' value is not recognised
        When it is loaded (the file-read validation path, not just construction)
        Then a LedgerError is raised
        """
        with tempfile.TemporaryDirectory() as d:
            payload = json.dumps(
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
            with self.assertRaises(dl.LedgerError):
                dl.load_ledger(self._ledger(d, payload))


if __name__ == "__main__":
    unittest.main()
