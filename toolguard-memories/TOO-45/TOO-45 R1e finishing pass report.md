---
title: TOO-45 R1e finishing pass report
type: note
permalink: toolguard/too-45/too-45-r1e-finishing-pass-report
tags:
- task-memory
- TOO-45
---

## Lead: the five records are restored (three genuinely, two correctly stay None), and under-logging is 0

**Corpus `--verify`: zero tracked-field regressions, verdicts unchanged.** Of the five cases the brief named:

- `diff <(cat a) <(cat b) && ls -la` -- `matched_rule` and `provenance` both **restored** to `'ls *'` / the project layer's provenance.
- `ls -la | diff - <(pwd)` -- `matched_rule` **restored** to `'ls *'`.
- `grep -n 'ls && python -c' .../test_resolve.py` -- `matched_rule` and `provenance` **stay `None`, correctly** -- see "Why the grep case does not restore" below. This is the brief's own escape valve ("if some case cannot carry a value because none exists, say precisely which and why, with the execution that shows it"), not a quiet acknowledgement.

Re-running the audit-loss measurement after all fixes: **0 of 978 compound-allow cases (>=2 sub_matches) under-log; 0 sub-commands have no audit entry** (was 813 of 975, 83%, 1,943 missing, per the R1 scoping trace). Stray-trailing-`]` check: **0 genuine artifacts** -- every bracket-ending `matched_rule` in 7,980 examined log entries is the deliberate `FALLBACK_ALLOW_PLACEHOLDER`/`FALLBACK_DENY_PLACEHOLDER` constant, not the old regex's fabrication.

## Starting state (handed off by the previous, killed agent)

Suite 2,349 tests, 4 failures: the 3 stale test pins plus `test_tracked_fields_unchanged_or_acknowledged` (the 5-case regression). `compound.py`'s six bare verdict tuples were already converted; `_log_allowed_command` already read `sub_matches`; the audit-trail fix's *mechanism* (record_unit/resolve_outer plumbing) was already correct and complete for what it touched. The gap was one level up.

## Defect 1 -- root cause and fix

The five regressions were **not** a gap in what `sub_matches` records (that part was already fixed) -- they were a gap in how the TOP-LEVEL `RuntimeVerdict.matched_rule`/`.provenance` (and, separately, `tools.decision.Decision.provenance`) picks ONE entry out of `sub_matches` to attribute the compound to.

`resolve.py::_deciding_sub_match`'s ALLOW branch used `len(sub_matches) == 1` as its proxy for "there is a single decider". That heuristic was accidentally correct before this step's audit-loss fix, because an escape-hatch leaf/segment (an `UndecidableSegment`, or an ask-floor leaf that allowed via the floor) previously produced **no** `sub_matches` entry at all -- so a two-leaf compound with one genuine match and one escape-hatch companion had `len(sub_matches) == 1` by omission, not by having a single decider. Once R1e correctly started recording those escape-hatch entries too (closing the audit-loss gap), the same compounds now have `len(sub_matches) == 2`, and the old test broke -- attributing `None` even though exactly one entry was a genuine, attributable rule match.

Fix: replaced the `len() == 1` test with "exactly one entry with `matched_rule is not None`" -- every escape-hatch entry always records `matched_rule=None` at the source (structural, not text-derived), so an ambient escape-hatch companion never competes for attribution, while two-or-more genuine matches (e.g. `git status && ls -la`, no escape hatch) still correctly return `None` (no single decider), exactly as before.

**A second, independent bug in the same shape**, found by tracing `provenance` specifically: `tools/decision.py::_decide_bash` re-derived `Decision.provenance` on its own, as `sub_matches[0].provenance` (literally "the first sub-command's provenance") instead of reusing `RuntimeVerdict.provenance` (which `resolve_bash_permission_detailed` already computes correctly via `_deciding_sub_match`). This is why `diff <(cat a) <(cat b) && ls -la`'s `provenance` stayed lost even after the `_deciding_sub_match` fix alone: the `diff` segment extracts FIRST, so `sub_matches[0]` was the escape-hatch entry (`provenance=None`), regardless of what the real `ls -la` leaf's provenance was. `ls -la | diff - <(pwd)`'s provenance was accidentally already right (its genuine leaf sorts first) -- extraction order is exactly why the corpus didn't flag it as a sixth regression. Fixed by deleting the independent re-derivation and reusing `result.provenance` directly.

**Why the grep case does not restore.** `grep -n 'ls && python -c' .../test_resolve.py` is a SINGLE ask-floor leaf (the whole command), resolved entirely through the escape hatch (`undecidable_fallback=allow_with_no_warnings`) -- confirmed by direct execution: `extract_structured()` returns one `LeafCommand(ask_floor=True)`, and its outer-command probe's own `'grep *'` match is deliberately discarded (this is the escape-hatch branch, not the deny branch, of `_resolve_leaf_detailed`). The OLD (pre-this-step) value `'grep *'` was the truncated stub's own match, attributed to a compound whose ACTUAL decision came from the fallback, not the rule -- this is precisely the fabrication class `_combine_strictest`'s own "Fabrication guard" docstring names (`python -c "print(1)" -> python -c` for a rule that never verified the real content). Restoring it would reintroduce that bug. `None` is the honest value: nothing in this compound was ever attempted against, and matched, a real rule.

**Verification, not assertion**: both fixes were confirmed by temporarily reintroducing the old logic (`len(sub_matches)==1` in `resolve.py`, `sub_matches[0].provenance` in `tools/decision.py`), re-running the new regression tests, watching them fail with the exact old symptom, then restoring the fix (byte-verified with `sha256sum` against a pre-edit backup) and confirming green again.

## Defect 2 -- LeafOutcome/UnitVerdict merged

`LeafOutcome` (`compound.py`) and `UnitVerdict` (`config_types.py`) both described exactly one leaf's outcome. `LeafOutcome`'s docstring argument for staying separate from `RuntimeVerdict` (per-leaf `fallback_kind` vs. `RuntimeVerdict.fallback_warning`'s aggregate boolean) is correct -- and irrelevant to `UnitVerdict`, which is *also* per-leaf. Every `LeafOutcome` construction site lives inside `_resolve_leaf_detailed`, which already has the leaf's real `sub_command` text (`leaf.text`) in scope at every one of them -- there was never a genuine "no sub_command yet" site to justify keeping two types.

Merged `reason`/`additional_context` onto `UnitVerdict` (both now required fields, positioned before the existing `fallback_kind` default). `_resolve_leaf_detailed` now builds ONE `UnitVerdict` per branch (previously two near-duplicate constructions -- one for `record_unit`, one for the `LeafOutcome` return -- were built separately with occasionally inconsistent `fallback_kind` values that happened to be harmless because `_combine_strictest` discards `fallback_kind` for non-allow decisions); calls `record_unit` with it if given, and returns the same object. `LeafOutcome` is deleted. Updated 8 production `UnitVerdict(...)` construction sites (`resolve.py`'s `_resolve_one`, `compound.py`'s 7) to supply the two new required fields -- all had `reason`/`additional_context` already in local scope.

`--predicates`: **RUNTIME verdict types back to 1** (`RuntimeVerdict`); `UnitVerdict` correctly classified as the excluded UNIT altitude.

## Defect 3 -- stale test pins

- `test_real_tree_has_exactly_one_runtime_verdict_type` -- already passes again once `LeafOutcome` was removed; content was still accurate, left unchanged.
- `test_r1_gate_fails_on_the_real_tree_because_of_bare_verdict_tuples` -- updated to assert exactly 4 remaining bare tuples (`permissions.check_hard_deny`, `permissions.decide_command_at_level_detailed`, `resolve._decide_file_path_at_level_detailed`, `resolve._check_file_path_hard_deny`), zero in `compound`, R1 `pass` still `False` because of the 4 (out of scope for this step).
- `test_real_tree_flags_all_six_compound_functions` -- renamed to `test_real_tree_no_longer_flags_any_compound_function_after_r1e`, asserts `compound.py` contributes zero hits now (mirrors the existing `..._after_r1d` hook.py test one stage later).

Given/When/Then docstrings updated in the same edit for both changed tests.

## New regression tests (main suite, not scratch)

Both logic fixes above are now pinned by a test in the main suite, each verified by mutation (see above):

- `test_resolve.py::TestUndecidableFallbackMultiLeafWarningParity.test_multi_leaf_matched_rule_attributes_the_sole_genuine_match` -- `ls && python -c "print(1)"` under `allow_with_warning`: `RuntimeVerdict.matched_rule == 'ls'`, `provenance` non-None, project level.
- `test_tools_decision.py::TestProvenanceRegression.test_bash_compound_mixed_escape_hatch_provenance_matches_matched_rule` -- `python -c "print(1)" && ls` (escape-hatch leaf extracts FIRST, the order that exposes the bug): `Decision.provenance` non-None and consistent with `Decision.matched_rule == 'ls'`.

No existing test was weakened or deleted. Six pre-existing, unrelated `F841` (`reason` assigned-but-unused) violations in `test_compound.py` were fixed by renaming the unused local to `_reason` at exactly those six lines -- confirmed pre-existing (not introduced by this session) by running `ruff check --select F841` against the `git show HEAD` version of the file (clean) versus the working tree (6 hits); no assertion touched. One genuinely-unused `UnitVerdict` import removed from `test_hook.py`; one genuinely-unused `dataclass` import removed from `compound.py` (after `LeafOutcome`'s removal made it dead).

## Files changed this session (finishing pass only; the previous agent's earlier, larger diff is separate)

- `toolguard/resolve.py` -- `_deciding_sub_match` allow-branch fix + docstring; `_resolve_one`'s `UnitVerdict(...)` gains `reason`/`additional_context`.
- `toolguard/tools/decision.py` -- `_decide_bash` reuses `result.provenance` instead of re-deriving; `Decision.provenance` docstring updated.
- `toolguard/compound.py` -- `LeafOutcome` deleted; `_resolve_leaf_detailed` returns `UnitVerdict` directly (8 construction sites consolidated to build one object each); `resolve_compound_permission_detailed`'s `UndecidableSegment` branch's `UnitVerdict(...)` gains `reason`/`additional_context`; unused `dataclass` import removed.
- `toolguard/config_types.py` -- `UnitVerdict` gains `reason: str`, `additional_context: Optional[str]` fields + docstrings; class docstring documents the merge and why `LeafOutcome`'s own argument didn't apply to it.
- `test/unit/test_architecture_fitness.py` -- 2 stale pins updated (Given/When/Then included).
- `test/unit/test_resolve.py` -- 1 new regression test.
- `test/unit/test_tools_decision.py` -- 1 new regression test.
- `test/unit/test_compound.py` -- 6 `F841` fixes (`reason` -> `_reason`), no behavior change.
- `test/unit/test_hook.py` -- 1 unused import removed.
- `test/verdict_corpus/goldens.jsonl`, `test/verdict_corpus/e2e_goldens.jsonl` -- regenerated via `tools/corpus_build.py --generate` after both logic fixes landed; reviewed programmatically before regenerating (238 `None -> value` newly-populated fields, 76 `value -> None` all independently confirmed as cases where `matched_rule` was ALREADY `None` in the pre-regen golden -- i.e. bringing `provenance` into consistency with an already-correct `matched_rule`, not new loss -- plus the 1 grep `matched_rule` case discussed above).

No new files created. No test deleted or weakened.

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2351 tests in 23.760s
OK

$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.20s. End-to-end: 61 cases in 3.12s.
OK: no differences.

$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook

$ uv run python tools/architecture_fitness.py --predicates   (R1 section)
RUNTIME verdict types (1): RuntimeVerdict
UNIT verdict types, excluded (1): UnitVerdict
bare verdict-tuple returns (4): permissions x2, resolve x2 -- compound: 0

$ uv run ruff format . && uv run ruff check --no-cache .
148 files left unchanged
All checks passed!
```

## Enrichment footprint before/after

Coupled-file count **unchanged at 9** (same files: `compound`, `config_types`, `hook`, `log_writer`, `permission_resolution`, `resolve`, `rule_entry`, `testing.sandbox`, `tools.decision`). Total identifier-level occurrences: brief's "currently 53" (measured before this finishing pass started) -> **72 now**. The increase is legitimate, not new coupling: the `UnitVerdict`/`LeafOutcome` merge added `reason`/`additional_context` fields and their docstrings inside the already-coupled `compound.py`/`config_types.py`/`resolve.py`, and the `_deciding_sub_match`/`_decide_bash` fixes added explanatory prose in the same already-coupled files -- no NEW file joined the coupled set.

## Not done / explicitly out of scope

R2 (`ToolPatternLayer` parallel arrays), R3's one remaining sanctioned `reason.startswith` site, R5 (import-layer violations), R6 (`tools.takeover_audit` private import) all still `FAIL` in `--predicates` -- unrelated to R1e, not touched, matches the brief's scope.

## Time and cost (estimated)

- Phase 1 (read brief, decision log, RESUME HERE, backups): ~12 min.
- Phase 2 (root-cause investigation for Defect 1 -- the longest phase, required direct execution probes against `extract_structured`/`resolve_bash_permission_detailed`/fixture configs to distinguish "genuine gap" from "correct new behavior" for all 5 named cases plus discovering the second, independent `tools/decision.py` bug): ~35 min.
- Phase 2 continued (Defect 2 merge across `config_types.py`/`compound.py`, all 8 construction sites): ~20 min.
- Phase 2 continued (Defect 3 test updates, ruff cleanup, corpus regeneration + review): ~15 min.
- Phase 3 (self-review: 2 new regression tests, mutation-verified each, full suite re-runs, final acceptance checklist): ~20 min.
- Phase 4 (this report): ~8 min.
- Total: ~110 minutes. Estimated cost (Sonnet 5, this session's token usage): roughly $3-5 -- the session involved substantial code reading (compound.py, resolve.py, config_types.py, decision.py, several test files) plus ~15 direct-execution probes and 2 mutation-verification cycles, but no long-running builds; this is a rough order-of-magnitude estimate, not a precise accounting.
