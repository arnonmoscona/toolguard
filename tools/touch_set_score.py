#!/usr/bin/env python
"""
Dev-only instrument: the M2 "expected touch set" comparison built for the
TOO-45 architecture experiment (see
``toolguard-memories/TOO-45/reports/micro-canary-protocol.md``). It compares a
hand-written PREDICTIONS file -- what a blind predictor, given the requirement
text and :mod:`tools.touch_set_inventory`'s output for one tree, guessed would
change -- against one or two ACTUALS files, in which a judge reading the real
diff says what actually changed and what kind of change it was.

Evidence, not scoring
------------------------
The output is auditable LISTS for a human to adjudicate: predicted-and-
changed, changed-but-not-predicted, predicted-but-not-changed, kind
agreements, kind mismatches, kind disagreements between judges, kind
abstentions, location-set disagreements between judges, and the duplicate-
location buckets. The single quotient anywhere in the output is
``location_counts.predicted_to_actual_ratio``, printed so that prediction
VOLUME is visible without the reader computing it.

:data:`KNOWN_LIMITATIONS` #1 is the reason for that shape, and is the full
statement of it: no per-location number, count or rate, compares two trees
fairly, because a tree's own factoring granularity moves the denominator.

The prediction unit is (location, kind) -- NEVER the file
------------------------------------------------------------
A location is ``"<path>"`` (module level) or ``"<path>::<Qual.Name>"``
(dot-joined nesting, e.g. ``toolguard/config.py::RuleEntry.allow_in_auto_mode``).
Locations are matched by exact string equality after normalisation, with no
fuzzy and no file-only fallback: a prediction naming the right file but the
wrong function is BOTH an entry in predicted-but-not-changed (for what it
named) and an entry in changed-but-not-predicted (for whatever actually
changed), never a match. KIND takes no part in matching: a location whose two
kinds differ is still a match, and the kinds are compared afterwards, into the
agreement/mismatch/disagreement/abstention buckets.

Location normalisation
--------------------------
The path half is stripped of surrounding whitespace, has backslashes turned
into forward slashes, and loses any leading ``./`` repetitions and any
leading ``/``. The qualname half -- which exists only after a ``::`` -- is in
addition NFKC-normalised (so an identifier spelled with different combining-
character sequences compares equal, matching CPython's own identifier
normalisation) and has whitespace around its ``.`` separators collapsed. Case
is left alone in both halves: Python identifiers are case-sensitive, so
folding case would hide a real mismatch rather than a cosmetic one.

Predictions file format
--------------------------
A JSON array of objects, hand-writable::

    [
      {"location": "toolguard/config.py", "kind": "record",
       "rationale": "optional one-line reason, never scored"},
      {"location": "toolguard/config.py::ConfigLoader.load", "kind": "decide"}
    ]

Required keys: ``location`` (a non-empty string after normalisation) and
``kind`` (one of ``decide``/``record``/``parse_validate``/``transport``/
``display``/``test``). Optional: ``rationale``. Any other key is a warning,
not fatal. A repeated JSON key within one object (e.g. two ``"location"``
keys in the same entry) is a FATAL schema error -- ordinary ``json.loads``
keeps only the last occurrence, which would make the earlier value vanish
with no trace (see :func:`parse_entries_json`).

Actuals -- one judge or two independent files
--------------------------------------------------
Symmetric with the predictions file: same schema, ``kind`` optional
(``null``/omitted means the judge could not tell -> :data:`KIND_UNKNOWN`,
assigned by this tool, never guessed).

Two judges are expressed as two separate, ordinary actuals files: pass
``--actuals-judge-1``/``--actuals-judge-2`` instead of ``--actuals`` (see
:func:`reconcile_two_judges`). A location listed by only one judge is real
evidence -- it counts toward the actuals for matching AND is reported in
``location_set_disagreements``, distinct from a kind disagreement on a
location both judges listed.

ANY schema violation on a required field, on any file, is FATAL: this tool
refuses to produce evidence from a partially valid file.

Usage::

    uv run python tools/touch_set_score.py --predictions preds.json --actuals actuals.json
    uv run python tools/touch_set_score.py --predictions preds.json \\
        --actuals-judge-1 judge1.json --actuals-judge-2 judge2.json --json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import unicodedata
from pathlib import Path
from typing import Sequence

# --------------------------------------------------------------------------
# Kind vocabulary
# --------------------------------------------------------------------------

KIND_DECIDE = "decide"
KIND_RECORD = "record"
KIND_PARSE_VALIDATE = "parse_validate"
KIND_TRANSPORT = "transport"
KIND_DISPLAY = "display"
KIND_TEST = "test"
KIND_UNKNOWN = "kind_unknown"

#: Every kind a predictions or actuals file may write explicitly. KIND_UNKNOWN is absent by
#: design -- it is this tool's own sentinel for "the judge gave no kind", so a file naming it
#: is rejected like any other unrecognised kind.
WRITABLE_KINDS = frozenset(
    {
        KIND_DECIDE,
        KIND_RECORD,
        KIND_PARSE_VALIDATE,
        KIND_TRANSPORT,
        KIND_DISPLAY,
        KIND_TEST,
    }
)

assert KIND_UNKNOWN not in WRITABLE_KINDS, (
    "KIND_UNKNOWN must never collide with a writable kind string -- a collision here would let "
    "an actual entry with no real kind silently 'match' any prediction that happened to use the "
    "same string. Pinned as a hard assertion, not just prose."
)

#: The ``actual_kind`` reported for a location whose two judges gave different kinds -- never
#: written by an author, never a guess at which judge is right.
KIND_DISAGREEMENT = "DISAGREEMENT"

assert KIND_DISAGREEMENT not in WRITABLE_KINDS and KIND_DISAGREEMENT != KIND_UNKNOWN, (
    "KIND_DISAGREEMENT must never collide with a writable kind string or with KIND_UNKNOWN."
)

KNOWN_LIMITATIONS = [
    "NO PER-LOCATION NUMBER -- COUNT OR RATE -- COMPARES TWO TREES FAIRLY. Formally: "
    "surprises = leaked_concepts + n*(1-p), where n is a tree's own actual-location count and p "
    "is per-location predictor recall. The count carries a noise term proportional to n, which "
    "is exactly the variable a tree's own factoring granularity controls; the rate divides the "
    "one real signal by that same n, diluting it. Monte Carlo verification (TOO-45 adversarial "
    "report, 20,000 paired draws): two trees with an IDENTICAL single genuine architecture leak, "
    "one graining the requirement into 3 locations and the other into 8, show the surprise COUNT "
    "picking the 3-location tree as 'better' in 64.7% of draws at a plausible per-location "
    "recall of 0.8 -- pure denominator noise. The RATE fares no better: at PERFECT recall, where "
    "the count correctly reports a tie, the rate calls the trees different (0.333 vs 0.125) when "
    "they are provably identical. An earlier version of this tool claimed surprise/miss COUNTS "
    "were 'immune to this bias' and promoted them for exactly that reason -- that claim was "
    "FALSE and has been retracted. This tool computes no rate, ratio, or score of any kind. It "
    "produces lists (predicted-and-changed, changed-but-not-predicted, predicted-but-not-"
    "changed, kind agreements/mismatches/disagreements/abstentions, location-set disagreements) "
    "for a human to read and adjudicate. If a single number is wanted, the only quantity that "
    "does not move under re-factoring is the count of DISTINCT LEAKED CONCEPTS, obtained by "
    "mapping each changed-but-not-predicted entry onto the requirement's own work items BEFORE "
    "the trees are unblinded -- that mapping is a judged step this tool does not perform.",
    "Nothing bounds how many locations a predictions file may name. A predictor who names every "
    "location in a tree (thousands, on a real package) trivially empties changed-but-not-"
    "predicted while flooding predicted-but-not-changed. This tool does not detect or bound "
    "prediction volume mechanically -- a list with thousands of entries is visibly not a "
    "prediction to a human judge reading it, which is the check this relies on. The predicted/"
    "actual location-count ratio is printed next to location_counts specifically so this is "
    "visible without the reader computing it themselves.",
    "Nothing validates that a predictions file and an actuals file grain locations at the same "
    "conceptual level (function-level vs. file-level, for instance). This tool prints a "
    "best-effort graining_check (the fraction of bare-path vs. qualname-suffixed locations on "
    "each side) so a gross mismatch is visible, but does not refuse to run or otherwise gate on "
    "it -- this tool no longer scores or gates anything, only presents evidence.",
    "Kind determination is entirely a human judgement call, on every file. Two-judge mode makes "
    "a SINGLE judge's individual bias visible by disagreement, on both the kind axis and now "
    "(via reconcile_two_judges) the location-set axis -- but it cannot detect two judges who "
    "share the same blind spot, and single-judge mode has no check of either kind at all.",
    "'test' is whatever an actuals author calls 'test' -- there is no independent per-file "
    "heuristic backing it up; a judge who forgets to mark a test file's locations as kind='test' "
    "will simply have them treated under whatever kind the change looks like instead.",
    "Location matching is exact string equality on (path, qualname) AFTER normalisation (NFKC, "
    "internal-whitespace collapse around '.', backslash-to-forward-slash) -- there is "
    "deliberately no fuzzy or file-only fallback beyond that normalisation. A prediction naming "
    "the right file but the wrong function lands in BOTH predicted-but-not-changed (for what it "
    "named) and changed-but-not-predicted (for what actually changed), never a match. Case is "
    "deliberately NOT folded -- Python identifiers are case-sensitive, and folding case would "
    "hide a real mismatch, not a cosmetic one.",
    "Duplicate locations across separate entries in one file (as opposed to a duplicate KEY "
    "within a single entry, which is a fatal error -- see parse_entries_json) are reported "
    "explicitly in the ambiguous_* buckets and scored using only the FIRST occurrence (file "
    "order) -- later duplicates are never silently merged away without being named.",
    "The gitignore-awareness in tools/touch_set_inventory.py (which this tool's evidence "
    "ultimately depends on for what a blind predictor was shown) is a best-effort, root-level-"
    "only implementation -- see that module's own KNOWN_LIMITATIONS for exactly what subset of "
    "gitignore syntax is and is not supported.",
]

# --------------------------------------------------------------------------
# Location normalisation
# --------------------------------------------------------------------------


def normalize_path_text(raw: str) -> str:
    """Path-half normalisation: strips surrounding whitespace, converts backslashes to forward
    slashes, strips leading ``./`` repetitions, and strips any leading ``/`` -- so ``./mod.py``
    and ``/mod.py`` both normalise to ``mod.py``."""
    text = raw.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def normalize_qualname_text(raw: str) -> str:
    """Qualname-half normalisation: NFKC (so NFC and NFD spellings of ``café`` compare equal,
    matching CPython's own identifier normalisation) plus collapsed whitespace around ``.``
    separators (``Outer. inner`` -> ``Outer.inner``). Case is deliberately left untouched."""
    normalized = unicodedata.normalize("NFKC", raw.strip())
    parts = [p.strip() for p in normalized.split(".")]
    return ".".join(parts)


def normalize_location(raw: str) -> str:
    """Normalises a hand-typed location string end to end -- a bare path (module level) through
    :func:`normalize_path_text`, or ``path::Qual.Name`` through both halves' own function.

    May return the empty string: ``"/"`` does. Callers must reject that on the RESULT rather
    than on the raw input, or two different non-empty inputs both normalising to ``""`` match
    each other."""
    stripped = raw.strip()
    if "::" in stripped:
        path_part, qual_part = stripped.split("::", 1)
        return f"{normalize_path_text(path_part)}::{normalize_qualname_text(qual_part)}"
    return normalize_path_text(stripped)


# --------------------------------------------------------------------------
# JSON parsing with duplicate-key detection
# --------------------------------------------------------------------------


class _RawObject:
    """One JSON object's raw ``(key, value)`` pairs IN DOCUMENT ORDER, duplicates included --
    an ``object_pairs_hook`` value. Ordinary ``json.loads`` collapses a repeated key to a plain
    dict keeping only the LAST occurrence; this wrapper exists to make that collapse visible
    before it happens, since a duplicated ``location`` key makes a real location vanish with no
    bucket at all."""

    __slots__ = ("pairs",)

    def __init__(self, pairs: list[tuple[str, object]]) -> None:
        self.pairs = pairs


@dataclasses.dataclass(frozen=True)
class _RawEntry:
    """One accepted JSON object from the top-level array, tagged with its ORIGINAL array index
    so error messages point at the author's own entry number even when earlier entries were
    rejected."""

    index: int
    data: dict


def parse_entries_json(
    raw_text: str, path: Path
) -> tuple[list[_RawEntry] | None, list[str]]:
    """Parses *raw_text* as a JSON array of flat objects. Returns ``(entries, errors)``;
    *entries* is ``None`` only when the top-level JSON is itself invalid or is not an array. A
    per-entry problem -- wrong type, a nested object, a duplicate key -- is recorded in *errors*
    and that entry is absent from the returned list."""
    try:
        raw = json.loads(raw_text, object_pairs_hook=_RawObject)
    except json.JSONDecodeError as exc:
        return None, [f"{path} is not valid JSON: {exc}"]

    if not isinstance(raw, list):
        return (
            None,
            [
                f"{path} must contain a JSON array at the top level, got {type(raw).__name__}"
            ],
        )

    errors: list[str] = []
    result: list[_RawEntry] = []
    for i, item in enumerate(raw):
        if not isinstance(item, _RawObject):
            type_name = "null" if item is None else type(item).__name__
            errors.append(f"{path} entry #{i}: expected an object, got {type_name}")
            continue

        seen: dict[str, object] = {}
        duplicate_keys: list[str] = []
        for key, value in item.pairs:
            if key in seen and key not in duplicate_keys:
                duplicate_keys.append(key)
            seen[key] = value
        if duplicate_keys:
            errors.append(
                f"{path} entry #{i}: duplicate key(s) {sorted(duplicate_keys)} in the same "
                "JSON object -- refusing to silently keep only the last occurrence"
            )
            continue

        for key, value in seen.items():
            if isinstance(value, _RawObject):
                errors.append(
                    f"{path} entry #{i}: '{key}' must be a plain value, got a nested object"
                )
                break
        else:
            result.append(_RawEntry(index=i, data=seen))

    return result, errors


# --------------------------------------------------------------------------
# Entry file (predictions and actuals share this exact schema and loader)
# --------------------------------------------------------------------------

MODE_SINGLE_JUDGE = "single_judge"
MODE_DUAL_JUDGE = "dual_judge"


@dataclasses.dataclass(frozen=True)
class LocationEntry:
    """One (location, kind) entry from a predictions or actuals file. ``kind_2`` is ``None`` for
    an ordinary single-judge entry; :func:`reconcile_two_judges` populates it when combining two
    independently-authored files."""

    location: str
    raw_location: str
    kind: str  # one of WRITABLE_KINDS, or KIND_UNKNOWN if the source file omitted it
    rationale: str | None
    index: int  # position in the source file, for deterministic dedup ordering
    kind_2: str | None = None

    @property
    def has_disagreement(self) -> bool:
        """True only when a second judge's kind is present and differs from the first's."""
        return self.kind_2 is not None and self.kind_2 != self.kind

    @property
    def is_abstention(self) -> bool:
        """True when the resolved kind carries no information: a single judge's KIND_UNKNOWN,
        or, post-reconciliation, both judges independently KIND_UNKNOWN."""
        return self.kind == KIND_UNKNOWN and (
            self.kind_2 is None or self.kind_2 == KIND_UNKNOWN
        )


_ALLOWED_ENTRY_KEYS = {"location", "kind", "rationale"}


def load_entries(
    path: Path, *, kind_required: bool
) -> tuple[list[LocationEntry], list[str], list[str]]:
    """Parses and schema-validates *path* as ONE entries file -- the predictions file, or one
    judge's actuals. Returns ``(entries, errors, warnings)``. A non-empty *errors* is fatal: the
    entries that did validate are still returned, but no evidence may be built from them.

    *kind_required* separates predictions (``kind`` always required) from actuals, where an
    omitted or null ``kind`` means "the judge could not tell" -> :data:`KIND_UNKNOWN`."""
    errors: list[str] = []
    warnings: list[str] = []

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"cannot read {path}: {exc}"], []

    raw_entries, parse_errors = parse_entries_json(raw_text, path)
    if raw_entries is None:
        return [], parse_errors, []
    errors.extend(parse_errors)

    entries: list[LocationEntry] = []
    for raw_entry in raw_entries:
        i, item = raw_entry.index, raw_entry.data
        extra_keys = sorted(set(item) - _ALLOWED_ENTRY_KEYS)
        if extra_keys:
            warnings.append(
                f"{path} entry #{i}: unexpected key(s) {extra_keys} (ignored)"
            )

        location = item.get("location")
        kind_raw = item.get("kind")
        rationale = item.get("rationale")

        if not isinstance(location, str):
            errors.append(
                f"{path} entry #{i}: 'location' must be a string, got {location!r}"
            )
            continue
        normalized_location = normalize_location(location)
        if not normalized_location:
            errors.append(
                f"{path} entry #{i}: 'location' is empty after normalisation "
                f"(raw value: {location!r})"
            )
            continue

        if kind_raw is None:
            if kind_required:
                errors.append(
                    f"{path} entry #{i}: 'kind' is required and was omitted/null"
                )
                continue
            kind = KIND_UNKNOWN
        elif not isinstance(kind_raw, str) or kind_raw not in WRITABLE_KINDS:
            errors.append(
                f"{path} entry #{i}: 'kind' must be one of {sorted(WRITABLE_KINDS)} or "
                f"null, got {kind_raw!r}"
            )
            continue
        else:
            kind = kind_raw

        if rationale is not None and not isinstance(rationale, str):
            errors.append(
                f"{path} entry #{i}: 'rationale' must be a string or omitted, got {rationale!r}"
            )
            continue

        entries.append(
            LocationEntry(
                location=normalized_location,
                raw_location=location,
                kind=kind,
                rationale=rationale,
                index=i,
            )
        )

    return entries, errors, warnings


def _dedupe(
    entries: list[LocationEntry],
) -> tuple[list[LocationEntry], dict[str, list[LocationEntry]]]:
    """Splits *entries* into (unique-by-location, first-occurrence-wins) and an explicit
    ambiguous-locations map for anything that appeared more than once."""
    by_location: dict[str, list[LocationEntry]] = {}
    for e in entries:
        by_location.setdefault(e.location, []).append(e)
    ambiguous = {loc: es for loc, es in by_location.items() if len(es) > 1}
    unique = sorted((es[0] for es in by_location.values()), key=lambda e: e.index)
    return unique, ambiguous


# --------------------------------------------------------------------------
# Two-judge reconciliation
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class LocationSetDisagreement:
    """One location that only ONE of the two judges listed as having changed at all -- a
    different finding from the two judges disagreeing about a location's KIND."""

    location: str
    judge: str  # "judge_1" | "judge_2"
    kind: str


def reconcile_two_judges(
    judge1: list[LocationEntry], judge2: list[LocationEntry]
) -> tuple[list[LocationEntry], list[LocationSetDisagreement]]:
    """Combines two independently-authored actuals lists, each already deduplicated by the
    caller, into one actuals list plus the location-set disagreements between them.

    A location BOTH judges listed becomes one entry with ``kind`` from judge 1 and ``kind_2``
    from judge 2, feeding :attr:`LocationEntry.has_disagreement`. A location only ONE judge
    listed is still real evidence -- one judge says it changed -- so it goes into the actuals
    list too, with ``kind_2`` left ``None`` so it can never read as a KIND disagreement, and is
    recorded in the second return value."""
    j1_by_loc = {e.location: e for e in judge1}
    j2_by_loc = {e.location: e for e in judge2}
    all_locations = sorted(set(j1_by_loc) | set(j2_by_loc))

    reconciled: list[LocationEntry] = []
    set_disagreements: list[LocationSetDisagreement] = []
    for i, loc in enumerate(all_locations):
        e1 = j1_by_loc.get(loc)
        e2 = j2_by_loc.get(loc)
        if e1 is not None and e2 is not None:
            reconciled.append(dataclasses.replace(e1, index=i, kind_2=e2.kind))
        elif e1 is not None:
            set_disagreements.append(LocationSetDisagreement(loc, "judge_1", e1.kind))
            reconciled.append(dataclasses.replace(e1, index=i))
        else:
            assert e2 is not None
            set_disagreements.append(LocationSetDisagreement(loc, "judge_2", e2.kind))
            reconciled.append(dataclasses.replace(e2, index=i))

    return reconciled, set_disagreements


def detect_actuals_mode(used_two_judges: bool) -> str:
    return MODE_DUAL_JUDGE if used_two_judges else MODE_SINGLE_JUDGE


# --------------------------------------------------------------------------
# Evidence building -- set comparison, no scoring
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class MatchedPair:
    prediction: LocationEntry
    actual: LocationEntry


@dataclasses.dataclass
class EvidenceResult:
    unique_predictions: list[LocationEntry]
    unique_actuals: list[LocationEntry]
    ambiguous_predictions: dict[str, list[LocationEntry]]
    ambiguous_actuals: dict[str, list[LocationEntry]]
    predicted_and_changed: list[MatchedPair]
    changed_but_not_predicted: list[LocationEntry]
    predicted_but_not_changed: list[LocationEntry]
    kind_agreements: list[MatchedPair]
    kind_mismatches: list[MatchedPair]
    kind_disagreements: list[MatchedPair]
    kind_abstained: list[MatchedPair]
    location_set_disagreements: list[LocationSetDisagreement]


def build_evidence(
    predictions: list[LocationEntry],
    actuals: list[LocationEntry],
    location_set_disagreements: list[LocationSetDisagreement] | None = None,
) -> EvidenceResult:
    """Compares *predictions* against *actuals* by EXACT location string equality -- see the
    module docstring's "Location normalisation". Produces lists, not a score.

    Every matched pair lands in exactly one of kind_agreements / kind_mismatches /
    kind_disagreements / kind_abstained. Abstention is tested first: an abstained pair has
    ``has_disagreement`` False, so it would otherwise fall through to the agreement comparison,
    where KIND_UNKNOWN never equals a predicted kind and the pair would be recorded as a
    mismatch -- scoring the predictor against a kind nobody gave."""
    unique_predictions, ambiguous_predictions = _dedupe(predictions)
    unique_actuals, ambiguous_actuals = _dedupe(actuals)

    actuals_by_location = {a.location: a for a in unique_actuals}

    predicted_and_changed: list[MatchedPair] = []
    predicted_but_not_changed: list[LocationEntry] = []
    for p in unique_predictions:
        actual = actuals_by_location.get(p.location)
        if actual is not None:
            predicted_and_changed.append(MatchedPair(p, actual))
        else:
            predicted_but_not_changed.append(p)

    predicted_locations = {p.location for p in unique_predictions}
    changed_but_not_predicted = [
        a for a in unique_actuals if a.location not in predicted_locations
    ]

    kind_agreements: list[MatchedPair] = []
    kind_mismatches: list[MatchedPair] = []
    kind_disagreements: list[MatchedPair] = []
    kind_abstained: list[MatchedPair] = []
    for m in predicted_and_changed:
        if m.actual.is_abstention:
            kind_abstained.append(m)
        elif m.actual.has_disagreement:
            kind_disagreements.append(m)
        elif m.prediction.kind == m.actual.kind:
            kind_agreements.append(m)
        else:
            kind_mismatches.append(m)

    return EvidenceResult(
        unique_predictions=unique_predictions,
        unique_actuals=unique_actuals,
        ambiguous_predictions=ambiguous_predictions,
        ambiguous_actuals=ambiguous_actuals,
        predicted_and_changed=predicted_and_changed,
        changed_but_not_predicted=changed_but_not_predicted,
        predicted_but_not_changed=predicted_but_not_changed,
        kind_agreements=kind_agreements,
        kind_mismatches=kind_mismatches,
        kind_disagreements=kind_disagreements,
        kind_abstained=kind_abstained,
        location_set_disagreements=location_set_disagreements or [],
    )


def _actual_kind_label(actual: LocationEntry) -> str:
    """The kind reported for an actual: KIND_DISAGREEMENT if its two judges disagreed on kind
    (never a guess at which is right), else its resolved kind, which may be KIND_UNKNOWN."""
    return KIND_DISAGREEMENT if actual.has_disagreement else actual.kind


def _graining_check(locations: list[LocationEntry]) -> dict:
    """Counts how many of *locations* are bare paths (module level) and how many are
    qualname-suffixed (function level). Comparing the two sides is how a reader notices that a
    predictions file and an actuals file were not authored at the same granularity, before
    mis-reading a long surprise list as an architecture finding rather than an authoring
    mismatch. Advisory only: nothing gates on it."""
    bare = sum(1 for e in locations if "::" not in e.location)
    qualified = len(locations) - bare
    return {"bare_path_count": bare, "qualname_count": qualified}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def _entry_dict(e: LocationEntry, *, kind_field: str = "kind") -> dict:
    return {"location": e.location, kind_field: e.kind, "rationale": e.rationale}


def build_report(
    predictions_path: Path,
    actuals_description: dict,
    raw_prediction_count: int,
    raw_actual_count: int,
    prediction_warnings: list[str],
    actual_warnings: list[str],
    evidence: EvidenceResult,
) -> dict:
    """Builds the full structured report, shared by the text and ``--json`` presentations.

    ``location_counts.predicted_to_actual_ratio`` is the one field anywhere in the report
    derived by division, and it is a display string rather than a number, present so prediction
    volume is visible (see :data:`KNOWN_LIMITATIONS` #2)."""
    total_actual = len(evidence.unique_actuals)
    total_predictions = len(evidence.unique_predictions)
    ratio = (
        f"{total_predictions / total_actual:.2f}x actual count"
        if total_actual
        else "undefined (0 actual locations)"
    )

    def matched_dict(m: MatchedPair) -> dict:
        return {
            "location": m.prediction.location,
            "predicted_kind": m.prediction.kind,
            "actual_kind": _actual_kind_label(m.actual),
            "rationale_prediction": m.prediction.rationale,
            "rationale_actual": m.actual.rationale,
        }

    return {
        "predictions_file": str(predictions_path),
        "actuals": actuals_description,
        "prediction_warnings": prediction_warnings,
        "actual_warnings": actual_warnings,
        "location_counts": {
            "predicted_unique": total_predictions,
            "actual_unique": total_actual,
            "predicted_to_actual_ratio": ratio,
        },
        "graining_check": {
            "predictions": _graining_check(evidence.unique_predictions),
            "actuals": _graining_check(evidence.unique_actuals),
        },
        "evidence": {
            "predicted_and_changed": {
                "count": len(evidence.predicted_and_changed),
                "items": [
                    matched_dict(m)
                    for m in sorted(
                        evidence.predicted_and_changed,
                        key=lambda m: m.prediction.location,
                    )
                ],
            },
            "changed_but_not_predicted": {
                "count": len(evidence.changed_but_not_predicted),
                "items": [
                    {
                        "location": a.location,
                        "actual_kind": _actual_kind_label(a),
                        "rationale": a.rationale,
                    }
                    for a in sorted(
                        evidence.changed_but_not_predicted, key=lambda a: a.location
                    )
                ],
            },
            "predicted_but_not_changed": {
                "count": len(evidence.predicted_but_not_changed),
                "items": [
                    {
                        "location": p.location,
                        "predicted_kind": p.kind,
                        "rationale": p.rationale,
                    }
                    for p in sorted(
                        evidence.predicted_but_not_changed, key=lambda p: p.location
                    )
                ],
            },
            "kind_agreements": {
                "count": len(evidence.kind_agreements),
                "items": [
                    matched_dict(m)
                    for m in sorted(
                        evidence.kind_agreements, key=lambda m: m.prediction.location
                    )
                ],
            },
            "kind_mismatches": {
                "count": len(evidence.kind_mismatches),
                "items": [
                    matched_dict(m)
                    for m in sorted(
                        evidence.kind_mismatches, key=lambda m: m.prediction.location
                    )
                ],
            },
            "kind_disagreements": {
                "count": len(evidence.kind_disagreements),
                "items": [
                    {
                        "location": m.prediction.location,
                        "predicted_kind": m.prediction.kind,
                        "judge_1_kind": m.actual.kind,
                        "judge_2_kind": m.actual.kind_2,
                    }
                    for m in sorted(
                        evidence.kind_disagreements, key=lambda m: m.prediction.location
                    )
                ],
            },
            "kind_abstained": {
                "count": len(evidence.kind_abstained),
                "items": [
                    {
                        "location": m.prediction.location,
                        "predicted_kind": m.prediction.kind,
                    }
                    for m in sorted(
                        evidence.kind_abstained, key=lambda m: m.prediction.location
                    )
                ],
            },
            "location_set_disagreements": {
                "count": len(evidence.location_set_disagreements),
                "items": [
                    {"location": d.location, "listed_by": d.judge, "kind": d.kind}
                    for d in sorted(
                        evidence.location_set_disagreements, key=lambda d: d.location
                    )
                ],
            },
        },
        "ambiguous_predictions": {
            loc: [
                {"kind": e.kind, "rationale": e.rationale, "index": e.index} for e in es
            ]
            for loc, es in sorted(evidence.ambiguous_predictions.items())
        },
        "ambiguous_actuals": {
            loc: [
                {
                    "kind": e.kind,
                    "kind_2": e.kind_2,
                    "rationale": e.rationale,
                    "index": e.index,
                }
                for e in es
            ]
            for loc, es in sorted(evidence.ambiguous_actuals.items())
        },
        "known_limitations": KNOWN_LIMITATIONS,
    }


def print_text_report(report: dict) -> None:
    print(f"touch-set EVIDENCE -- predictions: {report['predictions_file']}")
    a = report["actuals"]
    print(f"                      actuals mode: {a['mode']}")
    if a["mode"] == MODE_SINGLE_JUDGE:
        print(f"                      actuals file: {a['file']}")
    else:
        print(f"                      judge 1 file: {a['judge_1_file']}")
        print(f"                      judge 2 file: {a['judge_2_file']}")
    print()
    print(
        "NO SCORE, RATE, OR RATIO IS COMPUTED HERE. See KNOWN LIMITATIONS #1 for why. Every "
        "number below is either a plain input count or the length of the list printed with it."
    )
    print()

    if report["prediction_warnings"]:
        print(f"PREDICTIONS FILE WARNINGS ({len(report['prediction_warnings'])}):")
        for w in report["prediction_warnings"]:
            print(f"  - {w}")
        print()

    if report["actual_warnings"]:
        print(f"ACTUALS FILE WARNINGS ({len(report['actual_warnings'])}):")
        for w in report["actual_warnings"]:
            print(f"  - {w}")
        print()

    lc = report["location_counts"]
    print("=" * 70)
    print("LOCATION COUNTS")
    print("=" * 70)
    print(f"  predicted locations (unique): {lc['predicted_unique']}")
    print(f"  actual locations (unique)   : {lc['actual_unique']}")
    print(f"  predicted/actual            : {lc['predicted_to_actual_ratio']}")
    print()

    gc = report["graining_check"]
    print(
        "GRAINING CHECK (bare module-level vs. qualname-suffixed locations, each side -- a "
        "large mismatch usually means the two files were authored at different granularity, "
        "not that the trees differ architecturally):"
    )
    print(f"  predictions: {gc['predictions']}")
    print(f"  actuals    : {gc['actuals']}")
    print()

    ev = report["evidence"]

    def print_list(key: str, title: str, line_fn) -> None:
        bucket = ev[key]
        print(f"{title} ({bucket['count']}):")
        for item in bucket["items"]:
            print(f"  - {line_fn(item)}")
        if not bucket["items"]:
            print("  (none)")
        print()

    print_list(
        "changed_but_not_predicted",
        "CHANGED, NOT PREDICTED",
        lambda i: f"{i['location']} (kind={i['actual_kind']})",
    )
    print_list(
        "predicted_but_not_changed",
        "PREDICTED, NOT CHANGED",
        lambda i: f"{i['location']} (kind={i['predicted_kind']})",
    )
    print_list(
        "kind_mismatches",
        "KIND MISMATCHES (location matched, kind did not)",
        lambda i: (
            f"{i['location']}: predicted={i['predicted_kind']} actual={i['actual_kind']}"
        ),
    )
    print_list(
        "kind_disagreements",
        "KIND DISAGREEMENTS (two judges gave different kinds for this location)",
        lambda i: (
            f"{i['location']}: judge1={i['judge_1_kind']} judge2={i['judge_2_kind']}"
        ),
    )
    print_list(
        "kind_abstained",
        "KIND ABSTAINED (matched, but no judge could determine a kind)",
        lambda i: f"{i['location']} (predicted={i['predicted_kind']})",
    )
    print_list(
        "location_set_disagreements",
        "LOCATION-SET DISAGREEMENTS (only one judge listed this location at all)",
        lambda i: (
            f"{i['location']}: listed by {i['listed_by']} only (kind={i['kind']})"
        ),
    )
    print_list(
        "kind_agreements",
        "KIND AGREEMENTS (matched, kind agreed)",
        lambda i: f"{i['location']} (kind={i['actual_kind']})",
    )
    print_list(
        "predicted_and_changed",
        "PREDICTED AND CHANGED (full match list, all outcomes combined)",
        lambda i: (
            f"{i['location']} (predicted={i['predicted_kind']}, actual={i['actual_kind']})"
        ),
    )

    if report["ambiguous_predictions"]:
        print(
            f"AMBIGUOUS PREDICTIONS ({len(report['ambiguous_predictions'])} locations "
            "predicted more than once -- first occurrence used):"
        )
        for loc, entries in report["ambiguous_predictions"].items():
            kinds = ", ".join(e["kind"] for e in entries)
            print(f"  - {loc}: kinds predicted = [{kinds}]")
        print()

    if report["ambiguous_actuals"]:
        print(
            f"AMBIGUOUS ACTUALS ({len(report['ambiguous_actuals'])} locations listed more "
            "than once in one file -- first occurrence used; BOTH judges' kinds shown for each "
            "duplicate so a real disagreement buried in a duplicate is never invisible):"
        )
        for loc, entries in report["ambiguous_actuals"].items():
            pairs = ", ".join(
                f"{e['kind']}" + (f"/{e['kind_2']}" if e["kind_2"] is not None else "")
                for e in entries
            )
            print(f"  - {loc}: kinds given = [{pairs}]")
        print()

    print("KNOWN LIMITATIONS (what this tool structurally cannot fairly show):")
    for i, limitation in enumerate(report["known_limitations"], start=1):
        print(f"  {i}. {limitation}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

_FORMAT_HELP = """
Every file (predictions, and each actuals file) shares ONE schema -- a JSON
array of objects, hand-writable:

  [
    {"location": "toolguard/config.py", "kind": "record",
     "rationale": "optional, never scored"},
    {"location": "toolguard/config.py::ConfigLoader.load", "kind": "decide"}
  ]

location: "<path>" (module level) or "<path>::<Qual.Name>" (dot-joined
  nesting for a function/class, e.g. "pkg/mod.py::Outer.inner"). Matched by
  exact string equality AFTER normalisation (NFKC, whitespace-around-'.'
  collapse, backslash-to-forward-slash) between files.
kind: one of decide / record / parse_validate / transport / display / test.
  Required in --predictions. In an actuals file, may be null/omitted to mean
  "the judge could not tell" -- reported in its own kind_abstained list, never
  counted as a mismatch. The literal string "kind_unknown" is rejected
  everywhere (this tool's own reserved sentinel).
rationale: optional free text, carried into the report, never affects
  anything.

A repeated JSON key within one entry (e.g. two "location" keys in the same
object) is FATAL -- ordinary JSON parsing would silently keep only the last
one.

TWO JUDGES: pass --actuals-judge-1 and --actuals-judge-2 instead of
--actuals -- each is an ORDINARY actuals file (same schema as above, one
judge's opinion). A location only one judge lists appears in
location_set_disagreements. A location both list, with different kinds,
appears in kind_disagreements.

This tool computes NO score, rate, or ratio. It prints lists.
"""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a hand-written predictions file against one or two judge-written actuals "
            "files, at (location, kind) granularity. Produces auditable LISTS for a human to "
            "adjudicate -- no score, rate, or ratio of any kind. See "
            "tools/touch_set_inventory.py for the blind-predictor input and its "
            "--validate-predictions mode."
        ),
        epilog=_FORMAT_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        required=True,
        help="Path to the predictions JSON file.",
    )
    parser.add_argument(
        "--actuals", type=Path, default=None, help="Single-judge actuals JSON file."
    )
    parser.add_argument(
        "--actuals-judge-1",
        type=Path,
        default=None,
        help="Judge 1's actuals JSON file (use with --actuals-judge-2, instead of --actuals).",
    )
    parser.add_argument(
        "--actuals-judge-2",
        type=Path,
        default=None,
        help="Judge 2's actuals JSON file (use with --actuals-judge-1, instead of --actuals).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the machine-readable report as JSON."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)

    two_judge = args.actuals_judge_1 is not None or args.actuals_judge_2 is not None
    if args.actuals is not None and two_judge:
        print(
            "--actuals cannot be combined with --actuals-judge-1/--actuals-judge-2",
            file=sys.stderr,
        )
        return 2
    if two_judge and (args.actuals_judge_1 is None or args.actuals_judge_2 is None):
        print(
            "--actuals-judge-1 and --actuals-judge-2 must both be given together",
            file=sys.stderr,
        )
        return 2
    if args.actuals is None and not two_judge:
        print(
            "one of --actuals or (--actuals-judge-1 and --actuals-judge-2) is required",
            file=sys.stderr,
        )
        return 2

    predictions, pred_errors, pred_warnings = load_entries(
        args.predictions, kind_required=True
    )
    fatal = list(pred_errors)

    if two_judge:
        j1_entries, j1_errors, j1_warnings = load_entries(
            args.actuals_judge_1, kind_required=False
        )
        j2_entries, j2_errors, j2_warnings = load_entries(
            args.actuals_judge_2, kind_required=False
        )
        fatal.extend(j1_errors)
        fatal.extend(j2_errors)
        actual_warnings = j1_warnings + j2_warnings
        actuals_description = {
            "mode": MODE_DUAL_JUDGE,
            "judge_1_file": str(args.actuals_judge_1),
            "judge_2_file": str(args.actuals_judge_2),
        }
    else:
        actuals, actual_errors, actual_warnings = load_entries(
            args.actuals, kind_required=False
        )
        fatal.extend(actual_errors)
        actuals_description = {"mode": MODE_SINGLE_JUDGE, "file": str(args.actuals)}

    if fatal:
        if pred_errors:
            print(f"predictions file {args.predictions} is invalid:", file=sys.stderr)
            for err in pred_errors:
                print(f"  - {err}", file=sys.stderr)
        if two_judge:
            if j1_errors:
                print(
                    f"judge 1 actuals file {args.actuals_judge_1} is invalid:",
                    file=sys.stderr,
                )
                for err in j1_errors:
                    print(f"  - {err}", file=sys.stderr)
            if j2_errors:
                print(
                    f"judge 2 actuals file {args.actuals_judge_2} is invalid:",
                    file=sys.stderr,
                )
                for err in j2_errors:
                    print(f"  - {err}", file=sys.stderr)
        elif actual_errors:
            print(f"actuals file {args.actuals} is invalid:", file=sys.stderr)
            for err in actual_errors:
                print(f"  - {err}", file=sys.stderr)
        return 2

    if two_judge:
        # Discarding each judge's ambiguous map here means a location duplicated within one
        # judge's file is never reported: reconcile_two_judges emits unique locations, so
        # build_evidence's own _dedupe finds nothing left to flag and ambiguous_actuals comes
        # out empty in two-judge mode. Single-judge mode does report it.
        j1_unique, _ = _dedupe(j1_entries)
        j2_unique, _ = _dedupe(j2_entries)
        actuals, location_set_disagreements = reconcile_two_judges(j1_unique, j2_unique)
        raw_actual_count = len(j1_entries) + len(j2_entries)
    else:
        location_set_disagreements = []
        raw_actual_count = len(actuals)

    evidence = build_evidence(predictions, actuals, location_set_disagreements)
    report = build_report(
        args.predictions,
        actuals_description,
        len(predictions),
        raw_actual_count,
        pred_warnings,
        actual_warnings,
        evidence,
    )

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
