"""Tests for ``tools/touch_set_score.py`` (TOO-45 M2).

This is also the committed HAZARD SUITE for the D-series defects found by the
2026-08-06 adversarial review (``toolguard-memories/TOO-45/reports/
touch-set-adversarial-report.md``): duplicate JSON keys (D6), abstention vs.
mismatch (D4), location-set disagreement between two judges (D9), cosmetic
location variance (D8), and the empty-after-normalisation hole (D10).

This tool computes NO score/rate/ratio -- tests assert on the evidence LISTS
(``EvidenceResult``'s buckets) directly.
"""

import contextlib
import dataclasses
import io
import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from tools import touch_set_score as tss


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
        self.assertNotEqual(nfc, nfd)  # sanity: genuinely different byte sequences
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
        Then a fatal error names the entry and the duplicated key -- the real (first) location
        never silently vanishes in favour of the second
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            _write_raw(
                path,
                '[{"location": "pkg/a.py::f", "location": "pkg/z.py::gone", "kind": "decide"}]',
            )
            entries, errors = tss.parse_entries_json(path.read_text(), path)
            self.assertTrue(
                any("location" in e and "duplicate" in e.lower() for e in errors)
            )

    def test_duplicate_kind_key_is_fatal(self):
        """
        Given an entry with two "kind" keys
        When parsed
        Then a fatal error is reported -- a judge's first verdict must never be silently
        discarded in favour of the second
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actuals.json"
            _write_raw(
                path, '[{"location": "a.py", "kind": "decide", "kind": "transport"}]'
            )
            entries, errors = tss.parse_entries_json(path.read_text(), path)
            self.assertTrue(errors)

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
        Then it is a fatal schema error -- that string is this tool's own reserved sentinel
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
    """The redesign's core claim: build_evidence produces LISTS, and there is no rate/score
    anywhere in EvidenceResult or the report built from it."""

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
        When its top-level and evidence keys are inspected
        Then no key name contains "rate", and the only "ratio"-named field is the plain,
        undivided display string next to location_counts (not a numeric score)
        """
        predictions = [_entry("a.py", "decide", index=0)]
        actuals = [_entry("a.py", "decide", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        report = tss.build_report(
            Path("preds.json"),
            {"mode": "single_judge", "file": "actuals.json"},
            1,
            1,
            [],
            [],
            evidence,
        )
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
        Then the matched pair is kind_abstained, not a disagreement (both saying "I don't know"
        is not the same finding as two judges giving different real answers)
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actual = tss.LocationEntry(
            "mod.py", "mod.py", tss.KIND_UNKNOWN, None, 0, kind_2=tss.KIND_UNKNOWN
        )
        evidence = tss.build_evidence(predictions, [actual])
        self.assertEqual(len(evidence.kind_abstained), 1)
        self.assertEqual(evidence.kind_disagreements, [])

    def test_dual_judge_one_abstains_one_answers_is_a_disagreement_not_abstention(self):
        """
        Given a reconciled dual-judge entry where one judge gave a real kind and the other
        abstained
        When evidence is built
        Then it is a kind_disagreement (the judges did not converge), not an abstention -- an
        abstention means NEITHER judge could tell
        """
        predictions = [_entry("mod.py", "decide", index=0)]
        actual = tss.LocationEntry(
            "mod.py", "mod.py", "decide", None, 0, kind_2=tss.KIND_UNKNOWN
        )
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
        # It still matched normally on the kind axis (only one judge, that judge agreed).
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
        Given two predictions for the exact same location with different kinds
        When evidence is built
        Then the location is listed in ambiguous_predictions, and the FIRST (by file order) is
        used
        """
        predictions = [
            _entry("mod.py", "decide", index=0),
            _entry("mod.py", "record", index=1),
        ]
        actuals = [_entry("mod.py", "decide", index=0)]
        evidence = tss.build_evidence(predictions, actuals)
        self.assertIn("mod.py", evidence.ambiguous_predictions)
        self.assertEqual(len(evidence.predicted_and_changed), 1)
        self.assertEqual(evidence.predicted_and_changed[0].prediction.kind, "decide")


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
    """Exercises main() itself for both single- and two-judge modes, and the mutually-exclusive
    argument validation."""

    def test_single_judge_mode_runs_and_exits_zero(self):
        """
        Given a valid predictions file and a valid single actuals file
        When main() runs with --predictions/--actuals
        Then it exits 0
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            actuals = Path(tmp) / "actuals.json"
            _write_entries(preds, [{"location": "a.py", "kind": "record"}])
            _write_entries(actuals, [{"location": "a.py", "kind": "record"}])
            exit_code = tss.main(
                ["--predictions", str(preds), "--actuals", str(actuals)]
            )
            self.assertEqual(exit_code, 0)

    def test_two_judge_mode_runs_and_exits_zero(self):
        """
        Given a valid predictions file and two valid judge actuals files
        When main() runs with --actuals-judge-1/--actuals-judge-2
        Then it exits 0
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            j1 = Path(tmp) / "j1.json"
            j2 = Path(tmp) / "j2.json"
            _write_entries(preds, [{"location": "a.py", "kind": "record"}])
            _write_entries(j1, [{"location": "a.py", "kind": "record"}])
            _write_entries(j2, [{"location": "a.py", "kind": "record"}])
            exit_code = tss.main(
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

    def test_actuals_and_two_judge_flags_together_is_an_error(self):
        """
        Given --actuals combined with --actuals-judge-1
        When main() parses arguments
        Then it exits non-zero rather than silently picking one mode
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            actuals = Path(tmp) / "actuals.json"
            j1 = Path(tmp) / "j1.json"
            _write_entries(preds, [{"location": "a.py", "kind": "record"}])
            _write_entries(actuals, [{"location": "a.py", "kind": "record"}])
            _write_entries(j1, [{"location": "a.py", "kind": "record"}])
            exit_code = tss.main(
                [
                    "--predictions",
                    str(preds),
                    "--actuals",
                    str(actuals),
                    "--actuals-judge-1",
                    str(j1),
                ]
            )
            self.assertNotEqual(exit_code, 0)

    def test_no_actuals_flag_at_all_is_an_error(self):
        """
        Given neither --actuals nor the two-judge flags
        When main() parses arguments
        Then it exits non-zero
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            _write_entries(preds, [{"location": "a.py", "kind": "record"}])
            exit_code = tss.main(["--predictions", str(preds)])
            self.assertNotEqual(exit_code, 0)

    def test_json_output_is_valid_json(self):
        """
        Given a valid single-judge run
        When --json is passed
        Then stdout is valid, parseable JSON with no rate/ratio-scored field
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            actuals = Path(tmp) / "actuals.json"
            _write_entries(preds, [{"location": "a.py", "kind": "record"}])
            _write_entries(actuals, [{"location": "a.py", "kind": "record"}])
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                exit_code = tss.main(
                    ["--predictions", str(preds), "--actuals", str(actuals), "--json"]
                )
            self.assertEqual(exit_code, 0)
            parsed = json.loads(buf.getvalue())
            self.assertNotIn("rates", parsed)


if __name__ == "__main__":
    unittest.main()
