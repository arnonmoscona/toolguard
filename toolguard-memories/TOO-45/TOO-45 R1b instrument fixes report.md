---
title: TOO-45 R1b instrument fixes report
type: note
permalink: toolguard/too-45/too-45-r1b-instrument-fixes-report
tags:
- task-memory
- TOO-45
---

## Corrected R1b baseline (the number to pre-register R1 against)

Measured on the current tree with ONLY the instrument fixed -- no R1 work started. Full raw output: `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/NEW_predicates_output.txt`.

| item | old instrument said | corrected instrument says |
|---|---|---|
| A: verdict-ish types | 7: `ResolvedDecision`, `ProjectRootResolution`, `BashResolution`, `FileResolution`, `Decision`, `LedgerDecision`, `SingleDecision` | **5**: `ResolvedDecision`, `SubMatch`, `BashResolution`, `FileResolution`, `Decision` (4 genuine runtime verdicts + `SubMatch`, the phase-6 unit verdict; the 3 false positives are gone) |
| B: `__iter__` shim callers | `BashResolution`: 0. `FileResolution`: 0 | `BashResolution`: 0 total (production=0, test=0, tools=0 -- see caveat below). `FileResolution`: **8 total** (production=0, test=8, tools=0), all in `test/unit/test_hard_deny.py` (6) and `test/unit/test_hierarchical.py` (2) |
| C: enrichment footprint | 9 coupled / 6 prose-only, no occurrence count | 9 coupled / 6 prose-only (unchanged -- confirms the brief's prediction that the file count wouldn't move) / **69 total identifier-level occurrences**: hook 26, resolve 10, compound 11, log_writer 8, tools.decision 5, testing.sandbox 4, permission_resolution 3, config_types 1, rule_entry 1 |

Numbers for A and B are higher-fidelity than the R1 scoping trace's own figures in a few spots (e.g. hook.py's occurrence count is 26 here vs. the scoping trace's ~21) because real R1-adjacent work (`permission_resolution.py`'s extraction, D1a debts, R3) has landed on this branch since that trace was written two commits ago. That is expected and correct -- item D asks for the baseline on *today's* tree, not a reproduction of an older trace.

**Caveat on `BashResolution`'s 0-test-callers count, stated rather than silently left implicit**: the widened scan is a real fix (proven on `FileResolution`, whose count jumped from a false "0" to a true 8), but it is still a single-statement-unpack heuristic (`x, y = producer_fn(...)` in one `Assign`/`For` node) -- the same class of limitation the module's own docstring already states for the original algorithm. `BashResolution`'s real test callers construct it directly (`BashResolution(decision=..., ...)`) and iterate/unpack it in a *separate* statement, which no static AST heuristic without dataflow tracking will see. This is why the R1 scoping trace's "10 tests break on deletion" number is bigger than what either instrument version can enumerate by caller-counting alone: 8 are visible now (`FileResolution`'s), 2 are tests that exist solely to pin the shims' `__iter__` behaviour directly. Both existing and new tests are honest about this; do not read `BashResolution`'s `0` here as "provably has no test dependents" -- it means "this heuristic finds none," which R1 should treat as a caveat, not a green light.

## What changed, and why (item A)

`find_verdict_types` (`tools/architecture_fitness.py`) replaced its NAME-substring rule (`"decision"`/`"resolution"`/`"verdict"` in the class name, lowercased) with a STRUCTURAL rule: a class counts as a verdict type iff it declares a field named `decision` or `verdict` **and** at least 2 of `{reason, provenance, matched_rule, additional_context}`. This is not a hand-maintained allowlist -- it is a field-shape test run over the AST every time, so it can't silently drift the way the two allowlists this ticket has already caught did.

The exact field lists that justify the threshold (read from source, not assumed -- see the recall note for the full per-class table): `SubMatch` = `decision` + `matched_rule` + `provenance` (2 aux fields, included); `LedgerDecision` and `SingleDecision` both have a field literally named `decision` but **zero** aux fields (excluded); `ProjectRootResolution` has no `decision`/`verdict` field at all (excluded on the first condition alone). `tools.decision.Decision` spells its own verdict field `verdict`, not `decision` -- confirmed by reading the dataclass body, not the docstring, which is why the decision-field set is `{decision, verdict}` rather than just `decision`.

Demonstration (the brief's explicit ask): the new regression test `TestFindVerdictTypes.test_submatch_included_and_false_positives_excluded_on_real_tree` runs against the REAL tree and asserts `SubMatch` is present, all four genuine types are present, and all three false positives are absent. I ran this test (and the new synthetic-fixture test) against the unedited production code first and captured a genuine failure (`RED_new_tests_against_old_code.log` in scratchpad) before writing the fix, then re-ran green after. Both the "before" and "after" `--predicates` outputs were captured independently of the test suite too (see the diff below).

```diff
 === R1: FAIL ===
-  verdict-ish types (7):
+  verdict-ish types (5):
     - ResolvedDecision (config_types:329)
-    - ProjectRootResolution (path_utils:167)
+    - SubMatch (resolve:68)
     - BashResolution (resolve:98)
     - FileResolution (resolve:182)
     - Decision (tools.decision:46)
-    - LedgerDecision (tools.decision_ledger:95)
-    - SingleDecision (tools.replay:140)
```

## What changed, and why (item B)

`find_iter_shims` gained an additive `extra_caller_dirs: Sequence[Tuple[str, Path]] = ()` parameter. Default is an empty tuple, which reproduces the ORIGINAL toolguard_dir-only scan exactly -- every pre-existing caller of this function, and every pre-existing test of it, needed zero modification. `compute_predicates` now calls it with `extra_caller_dirs=(("test", test_dir), ("tools", tools_dir))`, defaulted to this repo's real `test/`/`tools/` directories. Each caller site now carries an `"area"` tag, and each shim gets a `caller_counts_by_area` dict (every known area present with an explicit `0`, never silently absent).

Demonstration: `TestFindIterShims.test_shims_with_callers_only_in_test_area_on_real_tree` runs against the real tree with `test/` wired in and asserts `FileResolution` shows 0 production callers and >0 test callers -- this assertion is a `TypeError` against the ORIGINAL function (no `extra_caller_dirs` parameter existed at all), captured in the same red-run log before the fix landed.

```diff
   __iter__ shims (2):
-    - BashResolution (resolve:98), callers: 0
-    - FileResolution (resolve:182), callers: 0
+    - BashResolution (resolve:98), callers: 0 (production=0, test=0, tools=0)
+    - FileResolution (resolve:182), callers: 8 (production=0, test=8, tools=0)
+        [test] test/unit/test_hard_deny.py:633 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hard_deny.py:657 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hard_deny.py:660 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hard_deny.py:694 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hard_deny.py:701 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hard_deny.py:727 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hierarchical.py:478 via resolve_file_path_permission_detailed(...)
+        [test] test/unit/test_hierarchical.py:586 via resolve_file_path_permission_detailed(...)
```

## What changed, and why (item C)

`EnrichmentFootprint` gained two additive members: `occurrences_by_file: Dict[str, int]` (only for coupled files -- a prose-only file has zero identifier-level occurrences by definition) and a `total_occurrences` property. `find_enrichment_footprint` now counts `NAME`-token hits per file instead of a boolean "has at least one". `coupled`/`prose_only` membership logic is byte-for-byte identical to before (still "count > 0" vs. "prose mention only"), so every existing test on those two buckets needed zero changes. `compute_predicates`'s `enrichment_footprint` dict gained `occurrences_by_file` and `total_occurrences`; the existing `coupled_count`/`coupled_files`/`prose_only_count`/`prose_only_files` keys are untouched, per the brief's explicit "do not remove or rename" instruction.

## Item D: acceptance run, exact output

```
$ uv run python -m unittest discover -s test -t .
Ran 2335 tests in 21.513s
OK
```
(Baseline before this task: 2,325. Net +10: 2 new tests replaced 1 old one in `TestFindVerdictTypes` for +2, +4 in `TestFindIterShims`, +2 in `TestFindEnrichmentFootprint`, +2 in `TestComputePredicates`.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.47s. End-to-end: 61 cases in 3.23s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --predicates
```
Full output in the baseline table above and in `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/NEW_predicates_output.txt`.

```
$ uv run ruff format . && uv run ruff check --no-cache .
148 files left unchanged
All checks passed!
```
(Whole-repo `ruff format --check .` was run first, non-mutating, and already reported all 148 files clean -- so the mutating `ruff format .` pass was a verified no-op and did not touch any of the substantial pre-existing uncommitted work outside my scope.)

## Files touched

Exactly two, both already tracked, both purely within `tools/architecture_fitness.py`'s own dev-tooling scope:
- `/home/arnon/projects/toolguard/tools/architecture_fitness.py`
- `/home/arnon/projects/toolguard/test/unit/test_architecture_fitness.py`

Nothing under `toolguard/` was read for editing purposes beyond looking up field definitions (read-only) to ground the structural criterion in real data. `git diff --stat -- toolguard/` was checked before and after and shows only the pre-existing, unrelated uncommitted work that was already there when this session started.

## One deliberate exception to "never modify an existing test," disclosed rather than silent

`test/unit/test_architecture_fitness.py::TestFindVerdictTypes::test_finds_decision_and_resolution_classes` pinned the OLD name-substring contract directly: its fixture was `class FileResolution: pass` / `class Decision: pass` / `class Foo: pass`, asserting the first two were returned purely because of their names. Every one of those classes has zero fields, so no structural rule can ever satisfy that assertion -- this is exactly the "test that must genuinely change" case, not a weakening. I replaced it with `test_finds_verdict_types_by_structure_not_by_name`, which asserts the corrected contract on a fixture built specifically to cover both directions the brief asked for (a fieldless class whose OLD name would have matched; a real, structurally-verdict-ish class whose name says nothing) -- so this single edit also satisfies the brief's separate "add a unit test covering both directions" requirement rather than needing yet another new test for the same point.

I left two adjacent, structurally-similar tests in the same class untouched even though the fix diminishes their value: `test_excludes_generated_files` and `test_excludes_r1_out_of_scope_packages` both use fieldless fixture classes (`class FileResolution: pass` / `class SomeResolution: pass`), so they still pass under the new rule, but only because the fixture classes were never going to match anyway (not because the generated-file/out-of-scope exclusion is doing anything meaningful in that specific test). They did not "genuinely need to change" (they still pass), so per the hard rule I left them alone rather than silently improving them. Flagging as a natural, low-risk follow-up: give those two fixtures real matching fields so the exclusion logic is actually exercised, not just coincidentally satisfied.

No other existing test was modified or deleted. 10 new tests were added; 1 was replaced as described above.

## Self-review

- `uv run python -m py_compile` on both touched files: clean.
- Anti-pattern scan (AST-based, not grep) on both touched files: zero `async`/`await`, zero `threading`, zero function-local imports.
- `uv run ruff format .` / `uv run ruff check --no-cache .`: clean, whole repo, verified non-mutating first via `--check`.
- Existing-code reuse check: the new `_class_field_names` helper deliberately mirrors the AnnAssign-scanning technique `find_parallel_arrays` (R2's detector) already uses in this same file, rather than reinventing field extraction; no dataclass/NamedTuple field-introspection helper existed elsewhere in the repo to reuse (checked `toolguard/` and `tools/` first).
- Full suite: 2,335 OK (was 2,325). Corpus verify: no differences. Guard: PASS, 12/12 canaries. Whole-repo ruff format/check: clean.

## Time and cost (estimated)

| phase | elapsed | approx cost (Sonnet 5 pricing, rough token estimate) |
|---|---|---|
| Phase 1: read brief, R1 scoping trace, source field definitions for every candidate class | ~15 min | ~$0.45 |
| Phase 2: write red-state tests, capture old baseline, implement items A/B/C, debug 2 real bugs found by my own tests (label computation outside repo root; over-asserted BashResolution test-caller count) | ~10 min | ~$0.60 |
| Phase 3: self-review, full acceptance run, ruff, scope verification | ~5 min | ~$0.20 |
| Phase 4: this report + task recall | ~5 min | ~$0.20 |
| **Total** | **~35 min** | **~$1.45** |

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- extends [[TOO-45 R1 scoping trace]]
- informs [[TOO-45 decision log]]
