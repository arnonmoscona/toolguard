"""Tests for ``tools/touch_set_score.py`` (TOO-45 M2)."""

import contextlib
import dataclasses
import io
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools import touch_set_inventory as tsi
from tools import touch_set_score as tss


def _run_main(argv: list[str]) -> tuple[int, str, str]:
    """Runs main() with stdout and stderr captured, returning (exit_code, stdout, stderr).

    Capturing is not decoration: main() prints a full evidence report, and the four CLI tests
    that let it through were contributing 101 lines to the suite's own output."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        exit_code = tss.main(argv)
    return exit_code, out.getvalue(), err.getvalue()


def _text_report(report: dict) -> str:
    """Renders print_text_report to a string."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        tss.print_text_report(report)
    return buf.getvalue()


def _report_for(
    predictions: list[tss.LocationEntry],
    actuals: list[tss.LocationEntry],
    disagreements: list[tss.LocationSetDisagreement] | None = None,
) -> dict:
    """build_evidence + build_report over hand-built entries, with a fixed single-judge
    description."""
    evidence = tss.build_evidence(predictions, actuals, disagreements)
    return tss.build_report(
        Path("preds.json"),
        {"mode": tss.MODE_SINGLE_JUDGE, "file": "actuals.json"},
        len(predictions),
        len(actuals),
        [],
        [],
        evidence,
    )


def _entry(
    location: str, kind: str, index: int = 0, rationale: str | None = None
) -> tss.LocationEntry:
    """Builds a LocationEntry directly, bypassing file I/O and normalisation."""
    return tss.LocationEntry(
        location=location,
        raw_location=location,
        kind=kind,
        rationale=rationale,
        index=index,
    )


def _write_entries(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries))


def _write_raw(path: Path, raw_text: str) -> None:
    path.write_text(raw_text)


class TestNormalizeLocation(unittest.TestCase):
    def test_leading_dot_slash_stripped(self):
        """
        Given a location with a leading "./"
        When normalized
        Then the "./" is stripped from the path half
        """
        self.assertEqual(tss.normalize_location("./mod.py"), "mod.py")

    def test_repeated_leading_dot_slash_stripped(self):
        """
        Given a location with a repeated "./" prefix
        When normalized
        Then every leading "./" segment is stripped
        """
        self.assertEqual(tss.normalize_location("././mod.py"), "mod.py")

    def test_qualname_half_whitespace_collapsed(self):
        """
        Given a "path::Qual. Name" location with internal whitespace around a dot
        When normalized
        Then the whitespace around '.' is collapsed
        """
        self.assertEqual(
            tss.normalize_location("pkg/mod.py::Outer. inner"),
            "pkg/mod.py::Outer.inner",
        )

    def test_backslash_path_separator_normalized_to_forward_slash(self):
        """
        Given a location with a backslash path separator (D8)
        When normalized
        Then it is converted to a forward slash, matching the POSIX-style twin
        """
        self.assertEqual(tss.normalize_location("pkg\\mod.py::f"), "pkg/mod.py::f")

    def test_nfd_unicode_normalizes_to_same_string_as_nfc(self):
        """
        Given the same identifier spelled in NFC and in NFD Unicode normal form (D8)
        When both are normalized
        Then they produce the IDENTICAL string, so they match each other
        """
        nfc = "pkg/a.py::" + unicodedata.normalize("NFC", "café")
        nfd = "pkg/a.py::" + unicodedata.normalize("NFD", "café")
        self.assertNotEqual(nfc, nfd)
        self.assertEqual(tss.normalize_location(nfc), tss.normalize_location(nfd))

    def test_case_is_not_folded(self):
        """
        Given two locations differing only in case
        When normalized
        Then they remain distinct -- Python identifiers are case-sensitive and folding case
        would hide a real mismatch, not a cosmetic one
        """
        self.assertNotEqual(
            tss.normalize_location("pkg/A.py::f"), tss.normalize_location("pkg/a.py::f")
        )

    def test_slash_only_location_normalizes_to_empty_string(self):
        """
        Given a location of "/" (D10)
        When normalized
        Then it produces the empty string -- the caller (load_entries) is responsible for
        rejecting an empty result, which this function itself does not do
        """
        self.assertEqual(tss.normalize_location("/"), "")


class TestParseEntriesJsonDuplicateKeys(unittest.TestCase):
    """D6: a duplicate JSON key within one entry must be fatal, never silently last-wins."""

    def test_duplicate_location_key_is_fatal(self):
        """
        Given an entry with two "location" keys
        When parsed
        Then a fatal error names the entry NUMBER and the duplicated KEY, and the entry is
        excluded outright -- neither the first nor the last-wins location survives into the
        returned entries
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_raw(
                path,
                '[{"location": "pkg/a.py::f", "location": "pkg/z.py::gone", "kind": "decide"}]',
            )
            entries, errors = tss.parse_entries_json(path.read_text(), path)
            self.assertEqual(len(errors), 1)
            self.assertIn("entry #0", errors[0])
            self.assertIn("['location']", errors[0])
            self.assertIn("duplicate", errors[0].lower())
            self.assertEqual(entries, [])

    def test_duplicate_kind_key_is_fatal(self):
        """
        Given an entry with two "kind" keys
        When parsed
        Then a fatal error names 'kind' and the entry is excluded -- a judge's first verdict is
        never silently discarded in favour of the second
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actuals.json"
            _write_raw(
                path, '[{"location": "a.py", "kind": "decide", "kind": "transport"}]'
            )
            entries, errors = tss.parse_entries_json(path.read_text(), path)
            self.assertEqual(len(errors), 1)
            self.assertIn("['kind']", errors[0])
            self.assertEqual(entries, [])

    def test_no_duplicate_key_parses_normally(self):
        """
        Given a well-formed entry with no duplicate keys
        When parsed
        Then it loads with zero errors
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_raw(path, '[{"location": "a.py", "kind": "decide"}]')
            entries, errors = tss.parse_entries_json(path.read_text(), path)
            self.assertEqual(errors, [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].data["location"], "a.py")

    def test_duplicate_key_via_load_entries_end_to_end(self):
        """
        Given a predictions file with a duplicate "location" key, loaded via load_entries
        When loaded
        Then it is fatal -- confirms the fix reaches the real entry point, not just the
        lower-level parser
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_raw(
                path, '[{"location": "a.py", "location": "b.py", "kind": "decide"}]'
            )
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)


class TestLoadEntries(unittest.TestCase):
    def test_valid_predictions_file_loads_with_no_errors(self):
        """
        Given a well-formed predictions file
        When loaded
        Then entries are returned with zero errors and zero warnings
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(
                path, [{"location": "mod.py", "kind": "record", "rationale": "why"}]
            )
            entries, errors, warnings = tss.load_entries(path, kind_required=True)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].kind, "record")

    def test_predictions_missing_kind_is_fatal(self):
        """
        Given a prediction with no "kind" key
        When loaded with kind_required=True
        Then a fatal error is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(path, [{"location": "mod.py"}])
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)

    def test_actuals_omitted_kind_maps_to_kind_unknown(self):
        """
        Given an actuals entry with "kind" omitted
        When loaded with kind_required=False
        Then it loads successfully with kind mapped to KIND_UNKNOWN
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actuals.json"
            _write_entries(path, [{"location": "mod.py"}])
            entries, errors, _ = tss.load_entries(path, kind_required=False)
            self.assertEqual(errors, [])
            self.assertEqual(entries[0].kind, tss.KIND_UNKNOWN)

    def test_literal_kind_unknown_string_rejected(self):
        """
        Given an entry that writes the literal string "kind_unknown"
        When loaded
        Then it is a fatal schema error, by the same "not in WRITABLE_KINDS" check that rejects
        any other unrecognised kind -- there is no sentinel-specific branch. The property that
        KIND_UNKNOWN stays OUT of WRITABLE_KINDS is held by the module-level assert, not here;
        this test documents the reserved string
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(path, [{"location": "mod.py", "kind": "kind_unknown"}])
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)

    def test_invalid_kind_is_a_fatal_error(self):
        """
        Given an entry whose "kind" is not one of the six allowed values
        When loaded
        Then a fatal error names the offending entry and the invalid value
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(path, [{"location": "mod.py", "kind": "does_something"}])
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(any("kind" in e for e in errors))

    def test_missing_location_is_a_fatal_error(self):
        """
        Given an entry with no "location" key
        When loaded
        Then a fatal error is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(path, [{"kind": "record"}])
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)

    def test_slash_only_location_rejected_after_normalization(self):
        """
        Given a "location" of "/" (D10)
        When loaded
        Then it is a fatal error -- rejected AFTER normalisation collapses it to empty, not
        silently accepted and then coincidentally matching another empty-after-normalisation
        entry
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(path, [{"location": "/", "kind": "record"}])
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)

    def test_non_list_top_level_is_a_fatal_error(self):
        """
        Given a file whose top level is a JSON object, not an array
        When loaded
        Then a fatal error is reported and no entries are returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text(json.dumps({"location": "mod.py", "kind": "record"}))
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)

    def test_unknown_extra_key_is_a_warning_not_an_error(self):
        """
        Given an entry with an unexpected extra key
        When loaded
        Then it still loads (a warning, not a fatal error) with the extra key ignored
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_entries(
                path, [{"location": "mod.py", "kind": "record", "confidence": "high"}]
            )
            entries, errors, warnings = tss.load_entries(path, kind_required=True)
            self.assertEqual(errors, [])
            self.assertTrue(warnings)
            self.assertEqual(len(entries), 1)

    def test_malformed_json_is_a_fatal_error_not_a_crash(self):
        """
        Given a file that is not valid JSON at all
        When loaded
        Then a fatal error is reported instead of raising
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text("{not valid json")
            entries, errors, _ = tss.load_entries(path, kind_required=True)
            self.assertEqual(entries, [])
            self.assertTrue(errors)


class TestBuildEvidenceNoScoring(unittest.TestCase):
    """build_evidence produces LISTS, and there is no rate/score anywhere in EvidenceResult or
    the report built from it."""

    def test_evidence_result_has_no_rate_field(self):
        """
        Given the EvidenceResult dataclass
        When its field names are inspected
        Then none of them contain the word "rate" -- this is a structural guard against the
        exact regression this redesign exists to prevent
        """
        field_names = {f.name for f in dataclasses.fields(tss.EvidenceResult)}
        self.assertFalse(any("rate" in name for name in field_names))

    def test_report_has_no_rate_or_ratio_key_except_the_documented_one(self):
        """
        Given a built report
        When its keys are inspected at every depth
        Then no key name contains "rate", and location_counts carries exactly three keys, of
        which predicted_to_actual_ratio is the only "ratio"-named one. That field IS produced
        by a division (the module's single quotient) -- it is a display string rather than a
        numeric score, which is a different claim from "undivided"
        """
        predictions = [_entry("a.py", "decide", index=0)]
        actuals = [_entry("a.py", "decide", index=0)]
        report = _report_for(predictions, actuals)
        self.assertNotIn("rates", report)
        self.assertNotIn("confusion_matrix", report)

        def walk_keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from walk_keys(v)
            elif isinstance(obj, list):
                for item in obj:
                    yield from walk_keys(item)

        all_keys = set(walk_keys(report))
        self.assertFalse(any("rate" in k.lower() for k in all_keys))
        # "except the documented one" is only checkable as an exact key set: a SECOND
        # ratio-named field would satisfy every assertion above.
        self.assertEqual(
            set(report["location_counts"]),
            {"predicted_unique", "actual_unique", "predicted_to_actual_ratio"},
        )
        self.assertIsInstance(
            report["location_counts"]["predicted_to_actual_ratio"], str
        )


class TestHazardGuessedFunctionName(unittest.TestCase):
    def test_never_actually_touched_location_is_predicted_but_not_changed(self):
        """
        Given a prediction naming a location that appears nowhere in actuals
        When evidence is built
        Then it is reported in predicted_but_not_changed (never falsely matched)
        """
        predictions = [_entry("mod.py::totally_made_up_fn", "decide", index=0)]
        actuals = [_entry("mod.py::real_fn", "record", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(evidence.predicted_and_changed, [])
        self.assertEqual(
            {p.location for p in evidence.predicted_but_not_changed},
            {"mod.py::totally_made_up_fn"},
        )


class TestHazardUnpredictedActualIsChangedButNotPredicted(unittest.TestCase):
    def test_actual_with_no_matching_prediction_is_listed(self):
        """
        Given an actual location with zero predictions naming it
        When evidence is built
        Then it appears in changed_but_not_predicted
        """
        evidence = tss.build_evidence([], [_entry("mod.py::fn", "record", index=0)])
        self.assertEqual(len(evidence.changed_but_not_predicted), 1)
        self.assertEqual(evidence.changed_but_not_predicted[0].location, "mod.py::fn")


class TestHazardKindMismatch(unittest.TestCase):
    def test_correct_location_wrong_kind_is_a_kind_mismatch(self):
        """
        Given a matching location predicted as "decide" but judged as "record"
        When evidence is built
        Then the pair appears in kind_mismatches, and NOT in kind_agreements
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actuals = [_entry("mod.py", "record", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(len(evidence.kind_mismatches), 1)
        self.assertEqual(evidence.kind_agreements, [])


class TestHazardFileMatchButNotFunction(unittest.TestCase):
    """The central design constraint: a prediction matching by FILE but not by FUNCTION must
    never be reported as any kind of match."""

    def test_wrong_function_in_right_file_never_matches(self):
        """
        Given actuals showing only other_fn changed in mod.py, and a prediction naming a
        DIFFERENT function (helper) in that same file
        When evidence is built
        Then helper is predicted_but_not_changed, other_fn is changed_but_not_predicted, and
        NEITHER appears in predicted_and_changed
        """
        predictions = [_entry("mod.py::helper", "transport", index=0)]
        actuals = [_entry("mod.py::other_fn", "decide", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(evidence.predicted_and_changed, [])
        self.assertEqual(
            {p.location for p in evidence.predicted_but_not_changed}, {"mod.py::helper"}
        )
        self.assertEqual(
            {a.location for a in evidence.changed_but_not_predicted},
            {"mod.py::other_fn"},
        )
        self.assertEqual(evidence.kind_agreements, [])
        self.assertEqual(evidence.kind_mismatches, [])

    def test_qualname_that_is_a_prefix_of_the_actual_one_never_matches(self):
        """
        Given a prediction naming the enclosing class and an actual naming a method inside it,
        so one location string is a strict PREFIX of the other
        When evidence is built
        Then they do not match -- the nearest thing to a fuzzy fallback that exact equality
        could accidentally admit
        """
        predictions = [_entry("mod.py::Outer", "decide", index=0)]
        actuals = [_entry("mod.py::Outer.inner", "decide", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(evidence.predicted_and_changed, [])
        self.assertEqual(
            {p.location for p in evidence.predicted_but_not_changed}, {"mod.py::Outer"}
        )
        self.assertEqual(
            {a.location for a in evidence.changed_but_not_predicted},
            {"mod.py::Outer.inner"},
        )


class TestHazardModuleLevelChange(unittest.TestCase):
    def test_module_level_prediction_matches_module_level_actual_only(self):
        """
        Given actuals listing a bare-path (module-level) location and a function-level location
        in the same file, and a prediction for the bare path only
        When evidence is built
        Then the bare-path location matches, and the function-level one is a surprise
        """
        predictions = [_entry("mod.py", "record", index=0)]
        actuals = [
            _entry("mod.py", "record", index=0),
            _entry("mod.py::fn", "transport", index=1),
        ]
        evidence = tss.build_evidence(predictions, actuals)
        matched_locations = {
            m.prediction.location for m in evidence.predicted_and_changed
        }
        self.assertEqual(matched_locations, {"mod.py"})
        self.assertEqual(
            {a.location for a in evidence.changed_but_not_predicted}, {"mod.py::fn"}
        )


class TestD4AbstentionOwnBucket(unittest.TestCase):
    """D4: a judge abstention must never be scored as the predictor being wrong."""

    def test_single_judge_abstention_on_matched_location_is_kind_abstained_not_mismatch(
        self,
    ):
        """
        Given a matched location where the single judge could not determine a kind
        When evidence is built
        Then the pair lands in kind_abstained, NOT in kind_mismatches or kind_agreements
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actuals = [_entry("mod.py", tss.KIND_UNKNOWN, index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(len(evidence.kind_abstained), 1)
        self.assertEqual(evidence.kind_mismatches, [])
        self.assertEqual(evidence.kind_agreements, [])

    def test_dual_judge_both_abstain_is_kind_abstained(self):
        """
        Given a reconciled dual-judge entry where BOTH judges abstained
        When evidence is built
        Then the matched pair is kind_abstained, and the entry does not read as a disagreement
        (both saying "I don't know" is not the same finding as two judges giving different real
        answers). The property is asserted directly: build_evidence tests is_abstention FIRST,
        so an empty kind_disagreements is guaranteed by branch order under ANY implementation of
        has_disagreement and cannot carry that claim on its own
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actual = tss.LocationEntry(
            "mod.py", "mod.py", tss.KIND_UNKNOWN, None, 0, kind_2=tss.KIND_UNKNOWN
        )
        self.assertFalse(actual.has_disagreement)
        self.assertTrue(actual.is_abstention)
        evidence = tss.build_evidence(predictions, [actual])
        self.assertEqual(len(evidence.kind_abstained), 1)
        self.assertEqual(evidence.kind_disagreements, [])

    def test_dual_judge_one_abstains_one_answers_is_a_disagreement_not_abstention(self):
        """
        Given a reconciled dual-judge entry where one judge gave a real kind and the other
        abstained -- tested in BOTH orientations, since only the judge-1-answers orientation
        can be reached without consulting kind_2
        When evidence is built
        Then it is a kind_disagreement (the judges did not converge), not an abstention -- an
        abstention means NEITHER judge could tell
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        judge_1_answered = tss.LocationEntry(
            "mod.py", "mod.py", "decide", None, 0, kind_2=tss.KIND_UNKNOWN
        )
        judge_2_answered = tss.LocationEntry(
            "mod.py", "mod.py", tss.KIND_UNKNOWN, None, 0, kind_2="decide"
        )
        for actual in (judge_1_answered, judge_2_answered):
            with self.subTest(kind=actual.kind, kind_2=actual.kind_2):
                self.assertFalse(actual.is_abstention)
                evidence = tss.build_evidence(predictions, [actual])
                self.assertEqual(len(evidence.kind_disagreements), 1)
                self.assertEqual(evidence.kind_abstained, [])


class TestD9LocationSetDisagreement(unittest.TestCase):
    """D9: two judges must be able to disagree about WHICH locations changed, not just kind."""

    def test_location_listed_by_only_one_judge_is_a_location_set_disagreement(self):
        """
        Given two judges' actuals lists where judge 2 lists a location judge 1 never mentions
        When reconciled
        Then it appears in location_set_disagreements tagged judge_2, and is STILL included in
        the combined actuals (so it can still be matched against predictions)
        """
        judge1 = [_entry("mod.py::a", "decide", index=0)]
        judge2 = [
            _entry("mod.py::a", "decide", index=0),
            _entry("mod.py::b", "record", index=1),
        ]
        reconciled, disagreements = tss.reconcile_two_judges(judge1, judge2)
        self.assertEqual(len(disagreements), 1)
        self.assertEqual(disagreements[0].location, "mod.py::b")
        self.assertEqual(disagreements[0].judge, "judge_2")
        self.assertIn("mod.py::b", {e.location for e in reconciled})

    def test_location_only_judge_1_saw_is_tagged_judge_1(self):
        """
        Given judge 1 lists a location judge 2 does not
        When reconciled
        Then the disagreement is tagged judge_1
        """
        judge1 = [_entry("mod.py::only1", "decide", index=0)]
        judge2 = []
        _, disagreements = tss.reconcile_two_judges(judge1, judge2)
        self.assertEqual(disagreements[0].judge, "judge_1")

    def test_location_only_one_judge_saw_does_not_spuriously_become_a_kind_disagreement(
        self,
    ):
        """
        Given a location only one judge listed
        When reconciled and fed into build_evidence
        Then it does NOT appear in kind_disagreements (nothing to disagree about on the kind
        axis if only one judge even considered the location) -- it belongs in
        location_set_disagreements only
        """
        judge1 = [_entry("mod.py::only1", "decide", index=0)]
        judge2 = []
        reconciled, set_disagreements = tss.reconcile_two_judges(judge1, judge2)
        predictions = [_entry("mod.py::only1", "decide", index=0)]
        evidence = tss.build_evidence(predictions, reconciled, set_disagreements)
        self.assertEqual(evidence.kind_disagreements, [])
        self.assertEqual(len(evidence.location_set_disagreements), 1)
        self.assertEqual(len(evidence.kind_agreements), 1)

    def test_location_both_judges_saw_with_different_kinds_is_a_kind_disagreement(self):
        """
        Given both judges list the SAME location with different kinds
        When reconciled
        Then it is NOT a location-set disagreement (both saw it) -- it is a kind disagreement
        instead, handled exactly as before
        """
        judge1 = [_entry("mod.py::shared", "decide", index=0)]
        judge2 = [_entry("mod.py::shared", "transport", index=0)]
        reconciled, set_disagreements = tss.reconcile_two_judges(judge1, judge2)
        self.assertEqual(set_disagreements, [])
        shared = next(e for e in reconciled if e.location == "mod.py::shared")
        self.assertTrue(shared.has_disagreement)


class TestAmbiguousPredictionsAndActuals(unittest.TestCase):
    def test_duplicate_prediction_location_reported_ambiguous_first_wins(self):
        """
        Given three predictions for the exact same location with different kinds
        When evidence is built
        Then the location is listed in ambiguous_predictions carrying EVERY occurrence in file
        order (later duplicates are named, never merged away), while only the FIRST is scored
        """
        predictions = [
            _entry("mod.py", "decide", index=0),
            _entry("mod.py", "record", index=1),
            _entry("mod.py", "transport", index=2),
        ]
        actuals = [_entry("mod.py", "decide", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(set(evidence.ambiguous_predictions), {"mod.py"})
        self.assertEqual(
            [e.kind for e in evidence.ambiguous_predictions["mod.py"]],
            ["decide", "record", "transport"],
        )
        self.assertEqual(len(evidence.predicted_and_changed), 1)
        self.assertEqual(evidence.predicted_and_changed[0].prediction.kind, "decide")
        self.assertEqual(evidence.predicted_but_not_changed, [])

    def test_duplicate_actual_location_reported_ambiguous_in_single_judge_mode(self):
        """
        Given one judge's actuals file listing the same location twice with different kinds
        When evidence is built
        Then ambiguous_actuals names it with both kinds in file order, and only the first is
        matched against the prediction
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actuals = [
            _entry("mod.py", "decide", index=0),
            _entry("mod.py", "record", index=1),
        ]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertEqual(set(evidence.ambiguous_actuals), {"mod.py"})
        self.assertEqual(
            [e.kind for e in evidence.ambiguous_actuals["mod.py"]], ["decide", "record"]
        )
        self.assertEqual(len(evidence.kind_agreements), 1)

    def test_unique_entries_keep_source_file_order_not_sorted_order(self):
        """
        Given entries whose locations sort in the opposite order to their file positions
        When deduplicated
        Then the unique list follows FILE order -- "first occurrence in file order wins" is
        only meaningful if file order is what is preserved
        """
        predictions = [
            _entry("z.py", "decide", index=0),
            _entry("a.py", "record", index=1),
            _entry("z.py", "transport", index=2),
        ]
        evidence = tss.build_evidence(predictions, [])
        self.assertEqual(
            [p.location for p in evidence.unique_predictions], ["z.py", "a.py"]
        )
        self.assertEqual(
            [p.kind for p in evidence.unique_predictions], ["decide", "record"]
        )


class TestGrainingCheck(unittest.TestCase):
    def test_bare_and_qualname_counts_reported_separately(self):
        """
        Given a mix of bare-path and qualname-suffixed locations
        When the graining check is computed
        Then bare and qualname counts are reported separately, not combined
        """
        entries = [
            _entry("a.py", "record", index=0),
            _entry("a.py::f", "decide", index=1),
            _entry("a.py::g", "decide", index=2),
        ]
        result = tss._graining_check(entries)
        self.assertEqual(result, {"bare_path_count": 1, "qualname_count": 2})


class TestEndToEndCLIModes(unittest.TestCase):
    """Exercises main() itself for both single- and two-judge modes, and each argument-validation
    guard SEPARATELY -- a fixture that trips two guards at once cannot detect either."""

    def _files(self, tmp: str) -> tuple[Path, Path, Path, Path]:
        """Writes one valid predictions file and three interchangeable valid actuals files."""
        preds = Path(tmp) / "preds.json"
        actuals = Path(tmp) / "actuals.json"
        j1 = Path(tmp) / "j1.json"
        j2 = Path(tmp) / "j2.json"
        for path in (preds, actuals, j1, j2):
            _write_entries(path, [{"location": "a.py", "kind": "record"}])
        return preds, actuals, j1, j2

    def test_single_judge_mode_runs_and_exits_zero(self):
        """
        Given a valid predictions file and a valid single actuals file
        When main() runs with --predictions/--actuals
        Then it exits 0 and prints the single-judge mode in its report header
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, actuals, _, _ = self._files(tmp)
            exit_code, out, _ = _run_main(
                ["--predictions", str(preds), "--actuals", str(actuals)]
            )
            self.assertEqual(exit_code, 0)
            self.assertIn(tss.MODE_SINGLE_JUDGE, out)

    def test_two_judge_mode_runs_and_exits_zero(self):
        """
        Given a valid predictions file and two valid judge actuals files
        When main() runs with --actuals-judge-1/--actuals-judge-2
        Then it exits 0 and prints the dual-judge mode in its report header
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, _, j1, j2 = self._files(tmp)
            exit_code, out, _ = _run_main(
                [
                    "--predictions",
                    str(preds),
                    "--actuals-judge-1",
                    str(j1),
                    "--actuals-judge-2",
                    str(j2),
                ]
            )
            self.assertEqual(exit_code, 0)
            self.assertIn(tss.MODE_DUAL_JUDGE, out)

    def test_actuals_and_two_judge_flags_together_is_an_error(self):
        """
        Given --actuals combined with a COMPLETE two-judge pair
        When main() parses arguments
        Then it exits 2 naming the mutual exclusion. The pair is complete deliberately: with
        --actuals-judge-2 omitted, the both-judges-together guard rejects the same input on its
        own, so this assertion could not observe the mutual-exclusion guard at all
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, actuals, j1, j2 = self._files(tmp)
            exit_code, _, err = _run_main(
                [
                    "--predictions",
                    str(preds),
                    "--actuals",
                    str(actuals),
                    "--actuals-judge-1",
                    str(j1),
                    "--actuals-judge-2",
                    str(j2),
                ]
            )
            self.assertEqual(exit_code, 2)
            self.assertIn("cannot be combined", err)

    def test_judge_1_without_judge_2_is_an_error(self):
        """
        Given --actuals-judge-1 alone, with no --actuals and no --actuals-judge-2
        When main() parses arguments
        Then it exits 2 naming the pairing requirement -- this input trips ONLY the
        both-judges-together guard, so it isolates it from the mutual-exclusion guard
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, _, j1, _ = self._files(tmp)
            exit_code, _, err = _run_main(
                ["--predictions", str(preds), "--actuals-judge-1", str(j1)]
            )
            self.assertEqual(exit_code, 2)
            self.assertIn("must both be given together", err)

    def test_judge_2_without_judge_1_is_an_error(self):
        """
        Given --actuals-judge-2 alone
        When main() parses arguments
        Then it exits 2 naming the pairing requirement -- the mirror orientation, since
        two_judge is computed from either flag being present
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, _, _, j2 = self._files(tmp)
            exit_code, _, err = _run_main(
                ["--predictions", str(preds), "--actuals-judge-2", str(j2)]
            )
            self.assertEqual(exit_code, 2)
            self.assertIn("must both be given together", err)

    def test_no_actuals_flag_at_all_is_an_error(self):
        """
        Given neither --actuals nor the two-judge flags
        When main() parses arguments
        Then it exits 2 saying an actuals source is required
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, _, _, _ = self._files(tmp)
            exit_code, _, err = _run_main(["--predictions", str(preds)])
            self.assertEqual(exit_code, 2)
            self.assertIn("is required", err)

    def test_missing_predictions_file_is_an_error_not_an_empty_comparison(self):
        """
        Given a --predictions path that does not exist, with a valid actuals file
        When main() runs
        Then it exits 2 naming the unreadable file, and prints NO report -- a tree that was
        never opened must not yield a clean "nothing was predicted" result
        """
        with tempfile.TemporaryDirectory() as tmp:
            _, actuals, _, _ = self._files(tmp)
            missing = Path(tmp) / "absent.json"
            exit_code, out, err = _run_main(
                ["--predictions", str(missing), "--actuals", str(actuals)]
            )
            self.assertEqual(exit_code, 2)
            self.assertIn("cannot read", err)
            self.assertEqual(out, "")

    def test_missing_actuals_file_is_an_error_not_an_empty_comparison(self):
        """
        Given a valid predictions file and an --actuals path that does not exist
        When main() runs
        Then it exits 2 naming the unreadable file and prints no report
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, _, _, _ = self._files(tmp)
            missing = Path(tmp) / "absent.json"
            exit_code, out, err = _run_main(
                ["--predictions", str(preds), "--actuals", str(missing)]
            )
            self.assertEqual(exit_code, 2)
            self.assertIn("cannot read", err)
            self.assertEqual(out, "")

    def test_json_output_is_valid_json_and_carries_the_documented_ratio(self):
        """
        Given a valid single-judge run
        When --json is passed
        Then stdout is valid, parseable JSON whose location_counts carries the documented
        predicted_to_actual_ratio display string -- the report DOES contain a ratio field, and
        the earlier Then denying it was contradicted by the payload it parsed
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds, actuals, _, _ = self._files(tmp)
            exit_code, out, _ = _run_main(
                ["--predictions", str(preds), "--actuals", str(actuals), "--json"]
            )
            self.assertEqual(exit_code, 0)
            parsed = json.loads(out)
            self.assertNotIn("rates", parsed)
            self.assertEqual(
                parsed["location_counts"]["predicted_to_actual_ratio"],
                "1.00x actual count",
            )


class TestReportNumbersAreDerivedFromTheComparison(unittest.TestCase):
    """Every number in the report must come from the match set it is printed beside. The fixture
    is deliberately larger than the buckets it fills (8 raw predictions, 7 raw actuals, every
    bucket non-empty and no two buckets the same size) so a hardcoded or capped count cannot
    coincide with the right answer."""

    def _fixture(self) -> tuple[list, list]:
        predictions = [
            _entry("agree.py", "record", index=0),
            _entry("mismatch.py", "decide", index=1),
            _entry("disagree.py", "decide", index=2),
            _entry("abstain.py", "decide", index=3),
            _entry("miss.py", "transport", index=4),
            _entry("dup.py", "record", index=5),
            _entry("dup.py", "display", index=6),
            _entry("dup.py", "test", index=7),
        ]
        actuals = [
            _entry("agree.py", "record", index=0),
            _entry("mismatch.py", "transport", index=1),
            tss.LocationEntry(
                "disagree.py", "disagree.py", "decide", None, 2, "record"
            ),
            _entry("abstain.py", tss.KIND_UNKNOWN, index=3),
            _entry("surprise.py", "test", index=4),
            _entry("dup.py", "record", index=5),
            _entry("surprise.py", "display", index=6),
        ]
        return predictions, actuals

    def test_every_bucket_holds_exactly_the_locations_the_comparison_puts_in_it(self):
        """
        Given a mixed fixture with an agreement, a mismatch, a disagreement, an abstention, a
        miss, a surprise and duplicates on both sides
        When evidence is built
        Then each bucket holds exactly its own locations -- asserted as exact sets, since a
        length check alone cannot see two entries swapping buckets
        """
        predictions, actuals = self._fixture()
        e = tss.build_evidence(predictions, actuals)
        self.assertEqual(
            {m.prediction.location for m in e.predicted_and_changed},
            {"agree.py", "mismatch.py", "disagree.py", "abstain.py", "dup.py"},
        )
        self.assertEqual({p.location for p in e.predicted_but_not_changed}, {"miss.py"})
        self.assertEqual(
            {a.location for a in e.changed_but_not_predicted}, {"surprise.py"}
        )
        self.assertEqual(
            {m.prediction.location for m in e.kind_agreements}, {"agree.py", "dup.py"}
        )
        self.assertEqual(
            {m.prediction.location for m in e.kind_mismatches}, {"mismatch.py"}
        )
        self.assertEqual(
            {m.prediction.location for m in e.kind_disagreements}, {"disagree.py"}
        )
        self.assertEqual(
            {m.prediction.location for m in e.kind_abstained}, {"abstain.py"}
        )
        self.assertEqual(set(e.ambiguous_predictions), {"dup.py"})
        self.assertEqual(set(e.ambiguous_actuals), {"surprise.py"})

    def test_reported_counts_are_conserved_against_the_match_set(self):
        """
        Given the same fixture rendered through build_report
        When the report's own numbers are cross-checked
        Then predicted_unique = matched + predicted_but_not_changed, actual_unique = matched +
        changed_but_not_predicted, and matched = the four kind buckets summed -- so a number
        cannot be re-derived from anything other than the comparison it is printed beside
        """
        predictions, actuals = self._fixture()
        report = _report_for(predictions, actuals)
        counts = {k: v["count"] for k, v in report["evidence"].items()}
        location_counts = report["location_counts"]
        self.assertEqual(
            location_counts["predicted_unique"],
            counts["predicted_and_changed"] + counts["predicted_but_not_changed"],
        )
        self.assertEqual(
            location_counts["actual_unique"],
            counts["predicted_and_changed"] + counts["changed_but_not_predicted"],
        )
        self.assertEqual(
            counts["predicted_and_changed"],
            counts["kind_agreements"]
            + counts["kind_mismatches"]
            + counts["kind_disagreements"]
            + counts["kind_abstained"],
        )
        self.assertEqual(
            (location_counts["predicted_unique"], location_counts["actual_unique"]),
            (6, 6),
        )

    def test_every_bucket_count_equals_the_length_of_the_list_printed_with_it(self):
        """
        Given a built report
        When each evidence bucket's count is compared with its own items list
        Then they are equal for every bucket -- the count is a length, never a separately
        maintained number
        """
        predictions, actuals = self._fixture()
        report = _report_for(predictions, actuals)
        for name, bucket in report["evidence"].items():
            with self.subTest(bucket=name):
                self.assertEqual(bucket["count"], len(bucket["items"]))

    def test_ratio_is_computed_from_the_unique_counts_printed_beside_it(self):
        """
        Given a fixture whose RAW entry counts (8 and 7) differ from its unique counts (6 and 6)
        When the report is built
        Then predicted_to_actual_ratio agrees with the two unique counts it is printed beside,
        not with the pre-dedupe totals -- a quotient over different variables from the ones
        displayed would read as 1.14x here
        """
        predictions, actuals = self._fixture()
        report = _report_for(predictions, actuals)
        location_counts = report["location_counts"]
        expected = (
            f"{location_counts['predicted_unique'] / location_counts['actual_unique']:.2f}"
            "x actual count"
        )
        self.assertEqual(location_counts["predicted_to_actual_ratio"], expected)
        self.assertEqual(
            location_counts["predicted_to_actual_ratio"], "1.00x actual count"
        )


class TestDegenerateComparisonArithmetic(unittest.TestCase):
    """The single quotient in the tool, driven to each degenerate corner. A confident number on
    an empty denominator is the failure this class exists to detect."""

    def _counts(self, n_predictions: int, n_actuals: int) -> dict:
        predictions = [
            _entry(f"p{i}.py", "record", index=i) for i in range(n_predictions)
        ]
        actuals = [_entry(f"a{i}.py", "record", index=i) for i in range(n_actuals)]
        return _report_for(predictions, actuals)["location_counts"]

    def test_zero_actual_locations_reports_undefined_never_a_number(self):
        """
        Given zero actual locations, with and without predictions
        When the report is built
        Then the quotient is the explicit "undefined" string rather than any number, and no
        ZeroDivisionError escapes
        """
        for n_predictions in (0, 2):
            with self.subTest(predictions=n_predictions):
                counts = self._counts(n_predictions, 0)
                self.assertEqual(
                    counts["predicted_to_actual_ratio"],
                    "undefined (0 actual locations)",
                )
                self.assertEqual(counts["actual_unique"], 0)
                self.assertEqual(counts["predicted_unique"], n_predictions)

    def test_zero_predictions_against_real_actuals_reports_zero_not_undefined(self):
        """
        Given no predictions at all and two actual locations
        When the report is built
        Then the quotient is 0.00x -- a predictor that named nothing is a real, reportable
        result, distinct from the undefined case where there was nothing to divide by
        """
        counts = self._counts(0, 2)
        self.assertEqual(counts["predicted_to_actual_ratio"], "0.00x actual count")

    def test_over_and_under_prediction_scale_the_quotient(self):
        """
        Given prediction volumes above and below the actual count
        When the report is built
        Then the quotient tracks them, which is the whole reason the field exists
        """
        self.assertEqual(
            self._counts(7, 2)["predicted_to_actual_ratio"], "3.50x actual count"
        )
        self.assertEqual(
            self._counts(1, 2)["predicted_to_actual_ratio"], "0.50x actual count"
        )

    def test_all_wrong_fills_both_surprise_buckets_and_leaves_no_match(self):
        """
        Given three predictions and three actuals sharing no location at all
        When evidence is built
        Then nothing matches, both surprise buckets hold all three, and every kind bucket is
        empty -- there is no kind verdict to give without a location match
        """
        predictions = [_entry(f"p{i}.py", "record", index=i) for i in range(3)]
        actuals = [_entry(f"a{i}.py", "record", index=i) for i in range(3)]
        e = tss.build_evidence(predictions, actuals)
        self.assertEqual(e.predicted_and_changed, [])
        self.assertEqual(len(e.predicted_but_not_changed), 3)
        self.assertEqual(len(e.changed_but_not_predicted), 3)
        self.assertEqual(e.kind_agreements, [])
        self.assertEqual(e.kind_mismatches, [])


class TestComparedNothing(unittest.TestCase):
    """Ticket 29's family: a result produced from inputs that were never really compared must not
    read like a real one."""

    def test_empty_versus_empty_is_distinguishable_from_a_perfect_prediction(self):
        """
        Given an empty comparison and a comparison where three of three predictions were right
        When both reports are built
        Then location_counts tells them apart (0/0 vs 3/3) even though every SURPRISE bucket is
        empty in both -- the surprise lists alone cannot distinguish them, which is why the
        counts are printed above them
        """
        empty = _report_for([], [])
        perfect_predictions = [_entry(f"m{i}.py", "record", index=i) for i in range(3)]
        perfect = _report_for(perfect_predictions, list(perfect_predictions))

        for report in (empty, perfect):
            self.assertEqual(
                report["evidence"]["changed_but_not_predicted"]["count"], 0
            )
            self.assertEqual(
                report["evidence"]["predicted_but_not_changed"]["count"], 0
            )

        self.assertNotEqual(empty["location_counts"], perfect["location_counts"])
        self.assertEqual(
            empty["location_counts"],
            {
                "predicted_unique": 0,
                "actual_unique": 0,
                "predicted_to_actual_ratio": "undefined (0 actual locations)",
            },
        )
        self.assertEqual(
            perfect["location_counts"]["predicted_to_actual_ratio"],
            "1.00x actual count",
        )
        self.assertEqual(empty["evidence"]["predicted_and_changed"]["count"], 0)
        self.assertEqual(perfect["evidence"]["predicted_and_changed"]["count"], 3)

    def test_two_empty_files_run_clean_and_say_so_in_the_counts(self):
        """
        Given a predictions file and an actuals file that both parse to zero entries
        When main() runs
        Then it exits 0 and reports zero locations on both sides with an undefined quotient.
        BOUNDARY, stated as measured: no warning is raised for a file that named nothing, so the
        only signal that nothing was compared is the pair of zero counts in the report body
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            actuals = Path(tmp) / "actuals.json"
            _write_raw(preds, "[]")
            _write_raw(actuals, "[]")
            exit_code, out, _ = _run_main(
                ["--predictions", str(preds), "--actuals", str(actuals), "--json"]
            )
            self.assertEqual(exit_code, 0)
            parsed = json.loads(out)
            self.assertEqual(parsed["location_counts"]["predicted_unique"], 0)
            self.assertEqual(parsed["location_counts"]["actual_unique"], 0)
            self.assertEqual(
                parsed["location_counts"]["predicted_to_actual_ratio"],
                "undefined (0 actual locations)",
            )
            self.assertEqual(parsed["prediction_warnings"], [])
            self.assertEqual(parsed["actual_warnings"], [])

    def test_unreadable_entries_file_yields_no_entries_and_an_error(self):
        """
        Given a path that does not exist
        When load_entries reads it
        Then it returns no entries AND a fatal error naming the path -- never an empty,
        error-free result that a caller could treat as "the file said nothing changed"
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.json"
            entries, errors, warnings = tss.load_entries(missing, kind_required=True)
            self.assertEqual(entries, [])
            self.assertEqual(warnings, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("cannot read", errors[0])
            self.assertIn(str(missing), errors[0])


class TestTwoJudgeKindLabels(unittest.TestCase):
    def test_both_judges_giving_the_same_kind_is_an_agreement_not_a_disagreement(self):
        """
        Given two judges who both list the same location with the SAME kind
        When reconciled and compared against a matching prediction
        Then the entry does not read as a disagreement, and the pair lands in kind_agreements --
        the half of has_disagreement that compares the two kinds is only reachable here
        """
        judge1 = [_entry("mod.py", "record", index=0)]
        judge2 = [_entry("mod.py", "record", index=0)]
        reconciled, set_disagreements = tss.reconcile_two_judges(judge1, judge2)
        self.assertEqual(set_disagreements, [])
        self.assertEqual(reconciled[0].kind_2, "record")
        self.assertFalse(reconciled[0].has_disagreement)
        evidence = tss.build_evidence(
            [_entry("mod.py", "record", index=0)], reconciled, set_disagreements
        )
        self.assertEqual(len(evidence.kind_agreements), 1)
        self.assertEqual(evidence.kind_disagreements, [])
        self.assertEqual(evidence.kind_mismatches, [])

    def test_disagreed_kind_is_labelled_DISAGREEMENT_in_the_report(self):
        """
        Given a location whose two judges gave different real kinds, both matched and unmatched
        When the report is built
        Then its actual_kind is the DISAGREEMENT sentinel in both places -- never either judge's
        own answer, which would be a silent guess at which judge is right
        """
        actual = tss.LocationEntry("d.py", "d.py", "decide", None, 0, kind_2="record")

        matched = _report_for([_entry("d.py", "transport", index=0)], [actual])
        item = matched["evidence"]["predicted_and_changed"]["items"][0]
        self.assertEqual(item["actual_kind"], tss.KIND_DISAGREEMENT)
        self.assertNotEqual(item["actual_kind"], actual.kind)
        self.assertNotEqual(item["actual_kind"], actual.kind_2)

        unmatched = _report_for([], [actual])
        surprise = unmatched["evidence"]["changed_but_not_predicted"]["items"][0]
        self.assertEqual(surprise["actual_kind"], tss.KIND_DISAGREEMENT)
        self.assertNotEqual(surprise["actual_kind"], actual.kind)
        self.assertNotEqual(surprise["actual_kind"], actual.kind_2)

    def test_agreed_kind_is_reported_as_that_kind_not_as_a_sentinel(self):
        """
        Given a location whose two judges agreed
        When the report is built
        Then actual_kind is the kind itself -- the control proving the DISAGREEMENT label is a
        branch and not a constant
        """
        actual = tss.LocationEntry("d.py", "d.py", "record", None, 0, kind_2="record")
        report = _report_for([_entry("d.py", "record", index=0)], [actual])
        item = report["evidence"]["predicted_and_changed"]["items"][0]
        self.assertEqual(item["actual_kind"], "record")


class TestPublishedLimitationBoundaries(unittest.TestCase):
    """KNOWN_LIMITATIONS is documentation, not evidence. Each test here either pins a deliberate
    scope boundary or fails because the published claim is not what the code does."""

    def test_nfkc_normalisation_applies_to_the_qualname_half_only(self):
        """
        Given a fullwidth character in the path half and the same character in a qualname half
        When both are normalised
        Then only the qualname half is folded to ASCII. BOUNDARY: the module docstring states
        this correctly; KNOWN_LIMITATIONS[5] still attributes NFKC to "(path, qualname)", so two
        actuals files spelling one directory in different normal forms would NOT match
        """
        self.assertEqual(tss.normalize_location("ａ.py"), "ａ.py")
        self.assertEqual(tss.normalize_location("m.py::ａ"), "m.py::a")
        self.assertEqual(tss.normalize_location("a b.py"), "a b.py")
        self.assertEqual(
            tss.normalize_location("m.py::Outer. inner"), "m.py::Outer.inner"
        )

    def test_two_judge_duplicate_locations_are_reported_not_silently_merged(self):
        """
        Given judge 1 listing the same location twice with different kinds, in two-judge mode
        When the report is built
        Then ambiguous_actuals names it, exactly as KNOWN_LIMITATIONS[6] promises for both modes
        ("never silently merged away without being named"). The single-judge control below shows
        the same input IS reported when only one judge is passed
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            j1 = Path(tmp) / "j1.json"
            j2 = Path(tmp) / "j2.json"
            _write_entries(preds, [{"location": "dup.py", "kind": "record"}])
            _write_entries(
                j1,
                [
                    {"location": "dup.py", "kind": "record"},
                    {"location": "dup.py", "kind": "decide"},
                ],
            )
            _write_entries(j2, [{"location": "dup.py", "kind": "record"}])

            _, single_out, _ = _run_main(
                ["--predictions", str(preds), "--actuals", str(j1), "--json"]
            )
            self.assertEqual(
                set(json.loads(single_out)["ambiguous_actuals"]), {"dup.py"}
            )

            _, dual_out, _ = _run_main(
                [
                    "--predictions",
                    str(preds),
                    "--actuals-judge-1",
                    str(j1),
                    "--actuals-judge-2",
                    str(j2),
                    "--json",
                ]
            )
            self.assertEqual(set(json.loads(dual_out)["ambiguous_actuals"]), {"dup.py"})

    def test_text_report_does_not_deny_computing_the_quotient_it_prints(self):
        """
        Given a run whose predicted and actual counts differ, so a quotient is printed
        When the text report is rendered
        Then it does not also carry the blanket claim that no ratio is computed. The quotient is
        deliberate (KNOWN_LIMITATIONS[2] exists to make prediction volume visible), so the two
        statements are printed within four lines of each other and one of them is false
        """
        report = _report_for(
            [_entry("x.py", "record", index=0), _entry("y.py", "record", index=1)],
            [_entry("x.py", "record", index=0)],
        )
        text = _text_report(report)
        self.assertIn("2.00x actual count", text)
        self.assertNotIn("NO SCORE, RATE, OR RATIO IS COMPUTED HERE", text)

    def test_gitignore_pointer_promise_is_met_by_the_module_it_points_at(self):
        """
        Given KNOWN_LIMITATIONS[7], which sends the reader to tools/touch_set_inventory.py's own
        KNOWN_LIMITATIONS for "exactly what subset of gitignore syntax is and is not supported"
        When an anchored pattern containing a wildcard is matched
        Then either it excludes the file, or the inventory's published list names the gap. It
        currently does neither: docs/*.py leaves docs/a.py in the inventory a blind predictor is
        shown, and the pointer's target says nothing about anchored patterns or wildcards. Goes
        green under EITHER fix, so it does not prejudge which module should change
        """
        anchored_wildcard_leaks = not tsi._is_gitignored(
            Path("docs/a.py"), ["docs/*.py"]
        )
        published = " ".join(tsi.KNOWN_LIMITATIONS).lower()
        self.assertTrue(
            (not anchored_wildcard_leaks)
            or "anchored" in published
            or "wildcard" in published,
            "touch_set_score.KNOWN_LIMITATIONS[7] promises the inventory documents exactly "
            "what gitignore syntax is unsupported, but the anchored-wildcard gap is neither "
            "fixed nor listed there",
        )


if __name__ == "__main__":
    unittest.main()
