---
title: TOO-45 expected-touch-set harness - implementation report
type: note
permalink: toolguard/too-45/reports/touch-set-harness-report
tags:
- task-memory
- TOO-45
- report
---

## UPDATE 2 (adversarial review response, same session) -- scoring removed entirely

An adversarial review (`toolguard-memories/TOO-45/reports/touch-set-adversarial-report.md`) proved, with a Monte Carlo sweep, that the count/rate demotion in UPDATE 1 above was backwards: it promoted the granularity-BIASED number and demoted the granularity-INVARIANT one. `surprises = leaked_concepts + n*(1-p)` -- the count carries a noise term proportional to `n` (a tree's own actual-location count, which scales directly with how finely that tree factors its logic); the rate divides the one real signal by that same `n`. Two trees with an IDENTICAL single genuine architecture leak, one graining the requirement into 3 locations and the other into 8, showed the surprise COUNT picking the 3-location tree as "better" in 64.7% of 20,000 paired draws at a plausible per-location recall of 0.8 -- pure denominator noise, no architecture difference. The RATE is not the fix either: at PERFECT recall, where the count correctly reports a tie, the rate calls the trees different (0.333 vs 0.125) when they are provably identical. Neither number is safe. This is a direct instance of the same defect shape that broke a different TOO-45 instrument, now confirmed in this one before it shipped.

**Response: mechanical scoring is abandoned entirely, not re-tuned.** `tools/touch_set_score.py` computes no rate, ratio, score, or cross-tree comparison of any kind -- not even a demoted one. It is now a pure set comparator producing auditable LISTS for a human judge to adjudicate: `predicted_and_changed`, `changed_but_not_predicted`, `predicted_but_not_changed`, `kind_agreements`, `kind_mismatches`, `kind_disagreements`, `kind_abstained` (new), `location_set_disagreements` (new), and the existing ambiguity buckets. A `len()` of each list is printed alongside it (an input count, not a derived score) plus `location_counts` (predicted/actual unique counts and their plain ratio, printed prominently so a disparity is visible on sight) and a best-effort `graining_check`. `KNOWN_LIMITATIONS` #1 states the retraction explicitly: the earlier claim that surprise/miss counts were "immune to this bias" was false, and is replaced by the formula and the Monte Carlo citations above, plus the honest statement that no per-location number -- count or rate -- compares two trees fairly. If a single number is ever wanted, the report names the one quantity that survives re-factoring: the count of distinct *leaked concepts*, obtained by mapping each `changed_but_not_predicted` entry onto the requirement's own work items before the trees are unblinded -- a judged step this tool does not perform.

### Defects fixed (all corrupted the evidence itself, independent of the scoring question)

- **D6 (duplicate JSON keys, silent last-wins)**: `parse_entries_json` now parses with `object_pairs_hook` and treats a repeated key within one entry as fatal, on both predictions and every actuals file. Three lines of stdlib mechanism, exactly as the adversarial report estimated.
- **D7 (duplicate actuals location silently reconciling a real disagreement)**: resolved as a CONSEQUENCE of the D9 redesign below, not a separate patch -- the vulnerable mechanism (`kind_1`/`kind_2` coexisting in one raw JSON entry, collapsed by `_dedupe`) no longer exists once two judges are two separate files.
- **D8 (cosmetic location variance costs a phantom surprise+miss pair)**: `normalize_qualname_text` now applies NFKC Unicode normalisation and collapses whitespace around `.`; `normalize_path_text` converts backslashes to forward slashes. Case is deliberately left alone (Python is case-sensitive; folding it would hide a real mismatch).
- **D5 (validator rejects real locations)**: `_collect_qualnames` now also walks class-level and module-level `AnnAssign`/`Assign` targets (dataclass fields, module constants, module-level lambda assignments) -- deliberately scoped to class/module level only, never inside a function body. The hard exit-1 gate is removed: `--validate-predictions` now always exits 0 for a well-formed file and reports invalid locations as advisory, with `difflib`-based nearest-real-location suggestions, since the false-negative cost (rejecting a real location a static walk cannot see, e.g. a runtime-generated name) was found to exceed the false-positive cost.
- **D4 (judge abstention scored as the predictor being wrong)**: a matched pair whose actual kind is an abstention (`LocationEntry.is_abstention`, checked before disagreement) now lands in its own `kind_abstained` list, never in `kind_mismatches` or `kind_agreements`. The old, misleadingly-named `matched_with_known_kind` field (which subtracted disagreements but never abstentions) is gone along with the rate it fed.
- **D9 (two-judge format cannot express location-SET disagreement, only kind disagreement)**: the single-file `kind_1`/`kind_2` schema is REMOVED and replaced with two independent, ordinary (single-kind) actuals files (`--actuals-judge-1`/`--actuals-judge-2`), reconciled by `reconcile_two_judges`. A location listed by only one judge is real evidence -- it still participates in matching against predictions AND is reported explicitly in the new `location_set_disagreements` bucket, tagged with which judge saw it.
- **D10 (`"/"`/`"./"` normalising to the empty string and matching each other)**: the non-empty check in `load_entries` now runs AFTER normalisation, not before.
- **D11 (unguarded reads crash on a broken symlink, a directory named `*.py`, a permission-denied file)**: `_safe_read_text` catches `OSError`/`UnicodeError` around every tree read in `touch_set_inventory.py` and reports the failure by name instead of crashing the whole run. A module reachable through more than one path via a file symlink is now de-duplicated by resolved real path in `discover_python_files`.
- **D12 ("the worst of these" -- gitignored files leaked to the blind predictor, including a filename that hinted at the requirement's subject)**: `_load_gitignore_patterns`/`_is_gitignored` implement a best-effort, stdlib-only, root-`.gitignore`-only matcher, wired into `discover_python_files`. **No subprocess is used** -- `git` is never invoked, preserving the blindness guarantee an adversarial audit-hook run had just verified (170 file opens, zero outside the tree, zero under `.git`, zero subprocess/socket/exec events) and which the coordinator explicitly said not to weaken. Verified on the real repo: `tmp/apply-guidance.py` (an actual file in the throwaway tree used for smoke-testing) is correctly excluded from the inventory.
- **D3 (unbounded prediction volume)**: per the coordinator's explicit instruction, no code change -- under judged adjudication a predictor naming thousands of locations is visibly not predicting to a human reading the list. Documented in `KNOWN_LIMITATIONS`, with the predicted/actual ratio printed next to `location_counts` so it is visible without computation.
- **D2 (nothing validates predictions/actuals grain at the same level)**: a best-effort `graining_check` (bare-path vs. qualname-suffixed location counts on each side) is printed for a human to notice a gross mismatch; this tool no longer gates or refuses to run on anything, so there is no "refuse to score" mechanism to add -- documented as a limitation instead.

### Test suite

Both test files were substantially rewritten. `test_touch_set_score.py` (42 tests) now asserts on `EvidenceResult`'s lists directly and includes a structural guard (`TestBuildEvidenceNoScoring`) that fails if any field name containing "rate" is ever reintroduced into `EvidenceResult` or the JSON report. `test_touch_set_inventory.py` (47 tests) adds dedicated classes for D5 (`TestD5WidenedQualnameCollection`, `TestNearestLocationSuggestions`), D11 (`TestD11SafeReadText`), and D12 (`TestD12Gitignore`, including a test that the module never imports `subprocess`). Full project suite: 2586 tests, clean.

## UPDATE (second course correction, same session)

After the report below was written, the coordinator approved the redesign and requested three further changes, all implemented within the same four files. This section supersedes anything below that conflicts with it; the sections below remain accurate for everything else (predictions/actuals file format basics, location-matching decisions, the hazard suite mechanism).

### 1. Counts are primary, rates are demoted and annotated

The report's own `location_counts` (`predicted_unique`, `actual_unique`) is now printed first, prominently, so a large disparity between two trees is visible immediately. `surprises` and `ordinary_misses` (misses) are primary output as a COUNT plus the full LIST of locations -- this is the fix for exactly the bias identified in this session's own KNOWN LIMITATIONS #2 (location-count denominators scale with how finely a tree factors its logic, exactly the defect that broke a different TOO-45 instrument). `surprise_rate`/`miss_rate` are still computed and printed, but demoted to a `"tier": "secondary"` section with an explicit one-line warning attached to each: comparing them across trees with materially different location counts is unsound. `kind_mismatch_rate` stays `"tier": "primary"`, undemoted, with its own one-line note explaining why its denominator (locations both sides already agree changed, excluding judge disagreements) does not have the same scaling problem -- it is the measure expected to discriminate most. KNOWN LIMITATIONS #2 was upgraded from "documented" to "DOCUMENTED AND PARTIALLY MITIGATED", stating plainly that the demotion reduces the harm (a reader of primary output is not misled) without eliminating the underlying sensitivity (a reader who uses the demoted rate anyway is still exposed to it).

### 2. Prediction-existence validation moved to touch_set_inventory.py, at authoring time

New CLI mode: `uv run python tools/touch_set_inventory.py --tree TREE --validate-predictions preds.json`. Checks every predicted location against the FULL location set of the tree -- every function/class at any nesting depth, any visibility (deliberately broader than the public-top-level-only symbols the plain inventory shows a blind predictor, since a real private helper or method is not a "guess" just because it was never named to the predictor). Exits non-zero when any prediction is invalid, so it can gate authoring before scoring. This required reintroducing AST span-collection logic (`_collect_qualnames`, `all_locations_for_validation`) into the inventory tool -- kept structurally separate from the ModuleEntry/SymbolEntry machinery that feeds the printed/JSON inventory, so the two purposes (what a blind predictor sees vs. what genuinely exists) can never be conflated. `tools/touch_set_score.py`'s KNOWN LIMITATIONS #1 (formerly "not mitigated") was updated to state the mitigation is a workflow step upstream, not a new capability in the scorer itself, which remains completely tree-agnostic.

One deliberate cross-import: `touch_set_inventory.py` now imports `normalize_location` from `touch_set_score.py` (a pure, side-effect-free string function) rather than re-duplicating it a third time -- explicitly reasoned through in the code as a different case from the change_role_classifier avoidance elsewhere in the same file, since the dependency is one-way and touch_set_score has zero awareness of touch_set_inventory.

### 3. Two-judge actuals support, disagreement never silently reconciled

Actuals entries may use `"kind"` (single-judge, unchanged/backward-compatible) OR `"kind_1"`+`"kind_2"` (dual-judge) -- the WHOLE FILE's mode is detected from whichever style any entry uses, and mixing styles across entries in one file is a fatal schema error. Either judge may independently abstain (kind_1/kind_2 each optionally null/omitted -> KIND_UNKNOWN for that judge specifically, never both fields required together). When the two agree (including both abstaining), scoring proceeds exactly as single-judge. When they disagree, the pair is EXCLUDED from `kind_mismatches` and from `kind_mismatch_rate`'s denominator, and is instead counted + listed with BOTH verdicts in a new `kind_disagreements` bucket; the confusion-matrix column for such a location is a new `DISAGREEMENT` sentinel, never a guess at which judge is right. The report states `"actuals_mode": "single_judge"|"dual_judge"` explicitly. Predictions never support kind_1/kind_2 -- using those keys in a predictions file is a fatal schema error (a predictor is one entity, not two judges), not a silently-ignored extra key.

### Verification

Naive-vs-real hazard demonstration re-run against the updated tool: identical 6/7 fail-then-pass result (H4 "plain" still the one naive gets right by luck; H4b still the realistic variant that breaks it). New tests added: `TestValidatePredictions` + 3 supporting classes in `test_touch_set_inventory.py` (12 new tests, 27 total, up from 15), `TestDualJudgeActuals` + demoted-rates coverage in `test_touch_set_score.py` (8 new tests, 36 total, up from 28). Full project suite: 2547 tests, clean. Two pre-existing local imports (`import inspect`, `import ast`, both inside test methods, present since the first version of `test_touch_set_inventory.py`) found and fixed during this pass -- moved to module level, per the project's no-function-local-imports rule; not something introduced by either course correction, just found on a closer self-review pass while touching that file again.

## Summary

Built the two tools for TOO-45's M2 "expected touch set" measure: `tools/touch_set_inventory.py` (the blind-predictor input, one tree only, never a diff) and `tools/touch_set_score.py` (the scorer). Mid-implementation, the coordinator withdrew the original directive to derive ACTUAL kinds mechanically from `tools/change_role_classifier.py`, after an independent adversarial review found that classifier's role labels anti-correlated with code quality. `touch_set_score.py` was redesigned as a pure comparator between two hand/judge-authored files -- predictions and actuals, same shape -- with zero dependency on any tree, diff, or AST-based classifier. `touch_set_inventory.py`'s incidental reuse of two tiny helpers from the classifier module was also dropped and reimplemented locally, closing a real `reportMissingImports` finding and removing all coupling to a module now under adversarial fire.

## Predictions file format (and the symmetric actuals file format)

Both files share one schema: a JSON array of objects, each `{"location": str, "kind": str, "rationale": str|null}`.

`location` is either a bare path (module-level, e.g. `"toolguard/config.py"`) or a dot-joined qualname suffix (e.g. `"toolguard/config.py::RuleEntry.allow_in_auto_mode"`). Matching between the two files is exact string equality on this value -- never fuzzy, never file-only.

`kind` is one of `decide` / `record` / `parse_validate` / `transport` / `display` / `test`. In the predictions file it is REQUIRED (a predictor unwilling to commit to a kind is not making a prediction). In the actuals file it may be `null` or omitted, meaning the judge could not determine a kind -- the tool assigns the internal sentinel `kind_unknown` itself in that case, never guessing one. The literal string `"kind_unknown"` is rejected by schema validation on BOTH files: it is the tool's own reserved sentinel, not a value either a predictor or a judge is allowed to write, and this is enforced both by the loader and by a module-load `assert KIND_UNKNOWN not in WRITABLE_KINDS` so a future edit cannot silently reintroduce the collision.

`rationale` is optional free text, carried into the report for a human reader, never scored.

Any unrecognised extra key on an entry is a non-fatal warning (reported, entry still loads). Any violation of a required field -- wrong top-level JSON shape, a non-object entry, a missing/invalid `location`, a missing (predictions) or invalid (either file) `kind` -- is FATAL: the whole file is rejected (exit code 2) rather than silently scoring a subset. Both files are documented in full, with worked examples, in each tool's own `--help` output, not only in the module docstring.

## The redesign, and why it happened mid-task

The original spec said: "Take the kind of an actual changed location from `tools/change_role_classifier.py` where it can supply one, and where it cannot, report the location as `kind_unknown`." I built exactly that first -- `touch_set_score.py` took `--old`/`--new` or `--repo`/`--base`/`--head` tree arguments, computed changed lines via `change_role_classifier.compute_changed_lines`, resolved them to (path, qualname) locations via my own AST span-walker, and derived a kind by feeding every identifier on a changed line through `change_role_classifier`'s DECISION/WRITE/CONDUIT role engine (reusing its `_analyze_tree` tree-reuse entry point, per that module's own documented precedent for avoiding a double parse).

Partway through, the coordinator withdrew this. An independent adversarial agent had shown the classifier's `_governing_role` walk stops at call/attribute boundaries and never reaches the governing `if` -- so the SAME logic, copy-pasted inline at four call sites, is classified DECISION at each site, while the identical logic factored behind one predicate function called from those four sites is classified pure CONDUIT. Sourcing "the ground truth kind" from an engine with that bias would have baked a preference for unfactored code directly into M2's headline measure -- exactly the kind of corruption M2 exists to catch in the trees being compared, now imported into the instrument itself.

The fix was not a patch to the kind-derivation logic; it was to stop deriving kind mechanically at all. "What kind of change is this" is a judgement call, and the redesigned tool treats it that way on BOTH sides: a blinded human judge produces the actuals file from the real diff, in the exact same shape a predictor produces the predictions file. `touch_set_score.py` now imports nothing from `change_role_classifier`, parses no AST, reads no tree, and runs no subprocess. This also, incidentally, FIXES a real limitation of the mechanical design: a human judge can assign `parse_validate` or `display`, which the classifier's role vocabulary could never produce at all.

`touch_set_inventory.py` was never involved in kind derivation (it has no notion of "kind"), but it had reused two small structural helpers (`discover_python_files`, `is_test_path`) from the classifier module. Since the coordinator's instruction was to drop the dependency "entirely," and since pyright had independently flagged `reportMissingImports` on `tools.change_role_classifier` in both files, I reimplemented those two functions locally (about 25 lines total) rather than leave any coupling to a module now under adversarial review.

## Location-matching decisions (and why)

- **Granularity is file + function/class qualname, never line.** A location is `"<path>"` or `"<path>::<Qual.Name>"`, dot-joined for nesting (e.g. `Outer.inner`). This is the whole point of the instrument -- see the module docstring.
- **Matching is exact string equality, no fuzzy or file-only fallback.** A prediction naming the right file but the wrong function is BOTH an ordinary miss (for what it named) and a surprise (for what actually changed) -- never a partial match. This is the central design constraint carried over unchanged from the original spec, and the coordinator explicitly confirmed it was "the hard part" and unaffected by the kind-sourcing redesign.
- **A changed location inside a function that did not exist before**: needs no special handling under the actuals-file design. The judge simply lists the new location like any other; a correct prediction for it matches like any other location. Covered by `TestHazardNewlyIntroducedFunction`.
- **A function that moved between files**: a judge looking at the real diff naturally lists only where the function NOW lives (its arrival), not the vacated old spot -- so a prediction of the old location is always an ordinary miss, never a false match, with no special-case code required. Covered by `TestHazardFunctionMovedBetweenFiles`.
- **A function that was renamed**: same mechanism as "moved" -- the old name is simply absent from actuals if the judge doesn't mention it; the new name is matched like any other location.
- **A change at module level, outside any function**: resolves to the bare path (no `::` suffix). Tested directly against a same-file function-level location to confirm the two are never conflated (`TestHazardModuleLevelChange`).
- **A predicted location that does not exist in the tree at all (the predictor guessed a name)**: this is the one case where the redesign genuinely LOST a capability the original spec asked for. The pre-redesign tool checked a predicted location against the union of every real location in the old and new tree, via full AST parses of both, and reported a distinct `guessed_name_misses` bucket. With zero tree access remaining, this distinction is undecidable -- a guessed name and a real-but-untouched location both land in one `ordinary_misses` bucket now. This is stated as KNOWN LIMITATION #1 in the tool's own output, not silently dropped, and `TestHazardGuessedFunctionName` pins that the case still shows up honestly (as a miss) rather than a false match or a silent omission.
- **Duplicate locations on either file**: reported explicitly (`ambiguous_predictions` / `ambiguous_actuals`), first-occurrence-by-file-order used for scoring. The pre-redesign version raised an `AssertionError` on a duplicate ACTUAL location instead of reporting it; changed after the exposure review below, because refusing to score adversarial input outright is a denial-of-service vector, not a report.

## Hazard suite and results

Six hazards were required by the spec; I ran seven scenarios (H4 split into a "plain" and a realistic "H4b" variant, explained below) through a deliberately naive comparator (file-level matching, kind-blind, no surprise concept -- never committed, lived only in scratchpad) alongside the real tool.

| # | Scenario | Naive verdict | Real tool verdict | Fail-then-pass? |
|---|---|---|---|---|
| H1 | Prediction names a function absent from actuals entirely | HIT (wrong -- file happened to appear elsewhere in actuals) | ORDINARY MISS + separate SURPRISE for the real location | YES |
| H2 | Changed location present in actuals, zero predictions at all | silent (no surprise concept -- reports nothing) | SURPRISE | YES |
| H3 | Location matches, predicted kind wrong | HIT (kind ignored) | MATCH flagged `is_kind_mismatch=true`, counted in `kind_mismatches` | YES |
| H4 | Moved function, "plain" (old file mentioned nowhere in actuals) | correctly MISS/HIT | correctly ordinary miss / match | NO -- naive coincidentally correct here |
| H4b | Moved function, old file ALSO has an unrelated real change nearby | HIT for the moved-away function (file-level collision) | ORDINARY MISS for it, SURPRISE for the real unrelated change | YES |
| H5 | Module-level change, prediction names an untouched function in the same file | HIT (file-level collision) | ORDINARY MISS + SURPRISE for the real module-level location | YES |
| H6 | File matches, function does not (two functions, only one changed) | HIT for the untouched one | ORDINARY MISS for it, SURPRISE for the one that changed, never a match | YES |

**Hazard pass rate: 6/7 (86%).** The one non-discriminating case (H4 plain) is reported honestly, not hidden: it is a scenario where the naive scorer's own bug (file-level matching) happens not to manifest because the vacated old file, under this design, is entirely absent from actuals with nothing else to collide against. H4b is the realistic variant of the same hazard (a moved function's old file usually still has SOMETHING else worth mentioning) and it does trip the naive scorer, so I count H4/H4b together as one required hazard with a demonstrated failure mode, satisfying the spec's demand for this specific case.

All seven scenarios are also pinned as committed unit tests in `test/unit/test_touch_set_score.py` (asserting the REAL tool's correct behaviour, independent of the throwaway naive comparison), so this suite is regression-protected going forward, not just a one-time demonstration.

## Adversarial exposure review (requested by the coordinator)

The same three shapes that broke a different TOO-45 instrument, checked against this one before calling it done:

**(a) A headline number a one-line sed could move from worst to best.** Largely closed by the redesign. The pre-redesign design's single point of leverage was the `DECISION > WRITE > CONDUIT` precedence tuple -- a one-line reorder there would have silently reclassified every location project-wide. That entire class of risk is gone now that kind is externally supplied, not computed. The residual risk I found and closed: if `KIND_UNKNOWN` ever collided with a real writable kind string, an actual entry with no real kind could silently "match" any prediction using that string, corrupting the kind-mismatch rate with no visible symptom. Closed with a module-load assertion (`assert KIND_UNKNOWN not in WRITABLE_KINDS`), not just prose, plus the literal string `"kind_unknown"` being rejected by schema validation on both files so neither a predictor nor a judge can ever write it in the first place.

**(b) Silent loss where a real location vanishes with no honesty-bucket entry.** The confusion matrix is built directly FROM the same `matched`/`ordinary_misses`/`surprises` lists the rest of the report reads -- there is no separate code path that could diverge from what is actually reported. Every unique prediction and every unique actual is guaranteed to land in exactly one of those three buckets by construction of `score_predictions`, and duplicates on either side are reported (not silently merged or crashed on) via the `ambiguous_predictions`/`ambiguous_actuals` buckets.

**(c) A growth rule whose output scales with how finely the code is factored, putting two trees on different scales.** NOT closed, and I want to be explicit about that rather than claim otherwise. Location granularity is still function/class-based: a tree that expresses a requirement as one function has one location; a tree that expresses the identical requirement as four small functions has four, inflating that tree's actual-location count and shifting its miss/surprise-rate denominators for reasons that have nothing to do with prediction quality. This is the exact shape flagged in the adversarial review of the OTHER instrument, transplanted into this one via the location concept both tools share. The tool cannot correct for it mechanically -- it can only ask whoever authors `actuals.json` to grain locations at a consistent CONCEPTUAL level across trees (one entry per genuinely distinct decision, not one entry per physical function), which is a documentation recommendation, not something code can verify or enforce. Recorded as KNOWN LIMITATION #2 in the tool's own output.

## Known limitations (as printed in the tool's own output, not just this doc)

1. No independent tree access -- cannot distinguish a guessed-name miss from an ordinary miss (see "Location-matching decisions" above).
2. Location granularity scales with how finely a tree factors its logic (exposure (c) above, unmitigated).
3. Kind determination is now entirely human judgement on both sides -- the tool cannot detect a judge who is inconsistent, biased toward one tree, or simply wrong. Moving kind determination out of a MACHINE's bias does not remove bias; it changes whose bias it is, and this tool cannot see a human judge's.
4. `test` is whatever the actuals author calls `test` -- there is no independent per-file heuristic backing it any more (the pre-redesign version used `change_role_classifier.is_test_path` as a structural override; gone along with every other tree-derived signal).
5. Exact-string matching only, no fuzzy/file fallback -- restated because it is the central design constraint, not an edge case.
6. Duplicate-location handling, restated with the reasoning for reporting rather than crashing.

## Synthetic demonstration data

All numbers shown in this report and during development (the `preds2.json`/`actuals2.json` smoke test, the seven hazard scenarios) are SYNTHETIC, constructed by me to exercise the tool. No real predictions exist yet -- the requirement set is still being triaged and no blind predictor has run. `touch_set_inventory.py` was exercised against the real read-only throwaway tree at `/tmp/toolguard-master-copy` (154 modules, zero parse failures) purely to confirm it produces sane output on real code; that run produced no score and is not presented as a result. `touch_set_score.py` no longer reads any tree at all, so this concern is structurally smaller than it was in the original design -- there is nothing left in it that could accidentally be pointed at a real tree and mistaken for a real score.

## Full test suite note

The project's full suite (`uv run python -m unittest discover -s test -t .`) showed intermittent failures during this session, always confined to `test_change_role_classifier.py`'s git-subprocess and filesystem-based test classes, with a DIFFERENT specific test failing each time. Root cause identified: `tools/change_role_classifier.py` and its test file are both untracked (`git status`) with a very recent mtime -- another agent is actively developing M1 concurrently in this same working tree. The failures reproduce even with my two new test files held out, and disappear when `test_change_role_classifier.py` is run alone, confirming this is a race against a concurrent external writer, not a regression from this work. `touch_set_score.py` and `touch_set_inventory.py` both have zero import dependency on `change_role_classifier.py` after the redesign, so they cannot be affected by it either way. My own 43 tests pass reliably across every isolated run performed.

## Files

- `tools/touch_set_inventory.py` (new)
- `tools/touch_set_score.py` (new)
- `test/unit/test_touch_set_inventory.py` (new, 15 tests)
- `test/unit/test_touch_set_score.py` (new, 28 tests, doubles as the committed hazard suite)

No existing files modified. The naive comparator used for the fail-then-pass demonstration lived only at `/tmp/.../scratchpad/naive_touch_set_score.py` and was never committed.

## Self-review

- `uv run ruff format` / `uv run ruff check` clean on all four files.
- No async/await, no threading, no function-local imports in any new file.
- One process anti-pattern violation to disclose: an early sanity check used an undisclosed `python -c` pipe (before I had re-read the project's intent-disclosure convention closely enough); every script execution after that point used the proper `# INTENT` / `# TOUCHES` / `# NOT INLINE BECAUSE` disclosure block.
- `git status` confirms only the four intended files were created; no existing file was touched.

## Time and cost (estimated)

- Phase 1 (reading conventions, protocol doc, M1 for precedent, planning, task-recall memory): ~18:39-18:47, ~8 min.
- Phase 2 (initial implementation of both tools + tests, pre-redesign): ~18:47-19:03, ~16 min.
- Mid-task redesign (dropping the classifier dependency, rewriting `touch_set_score.py`, `touch_set_inventory.py`'s import, both test files, the naive demo, exposure review): ~19:03-19:17, ~14 min.
- Self-review, flakiness investigation, report: ~19:17 onward, ~10 min.
- Total elapsed: roughly 50 minutes end to end, most of it inside a single continuous coding phase with one significant architecture pivot partway through.
- Estimated cost: Sonnet 5 pricing, moderate-length session with several large file writes/rewrites and one full redesign; rough order of magnitude USD 3-6 for the full session (token-based estimate, not measured precisely).