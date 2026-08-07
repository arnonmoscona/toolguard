---
title: TOO-45 compound-resolve cycle - implementation report
type: note
permalink: toolguard/too-45/reports/compound-cycle-implementation
tags:
- task-memory
- TOO-45
- report
---

# TOO-45 compound/resolve cycle removal -- implementation report

Implemented Plan B (`compound-cycle-plan-B.md`) with all five refinements from the blind judgment (`compound-cycle-judgment.md`), in seven steps, each verified green before moving on. The abandon gate at step 3 was NOT triggered -- the relocation was mechanical.

## Files changed

- `toolguard/compound.py` -- the core rewrite. Added `CommandUnit` (frozen dataclass, with `audits_as_one: bool` per judgment R1), `_unit_for`, `decompose`, `_unit_from_tuple`, and `judge_unit` (the old `_resolve_leaf_detailed` body plus the `UndecidableSegment` branch, unified, with every callback parameter removed). `_combine_strictest` now takes `List[UnitVerdict]` instead of a 5-tuple list. `_resolve_leaf_detailed` is deleted. `_resolve_leaf` now drives `_unit_for` + `judge_unit` directly. `resolve_compound_permission_detailed` lost its `resolve_outer`/`record_unit` parameters and is now a ten-ish-line convenience driver over `decompose`/`judge_unit`/`_combine_strictest` for the ~40 tests and `check_compound_permission` that have no `UnitVerdict`-producing resolver of their own. The `ResolveOuterProbe`/`RecordUnitVerdict` type aliases and their ~25-line doc blocks are deleted outright. Module docstring gained a short "Shape" section naming the three functions.
- `toolguard/resolve.py` -- `resolve_bash_permission_detailed`'s `_decide` closure now returns a strict `(UnitVerdict, Optional[ConflictOverride])` pair instead of a 7-tuple. `_resolve_one`/`_resolve_outer`/`_record_unit` are deleted. The function now drives `compound.decompose`/`compound.judge_unit`/`compound._combine_strictest` directly in an explicit loop, populating `sub_matches`/`overrides` by ordinary `append`/`extend`, gated on `unit.audits_as_one` (not `unit.kind == "plain"`, per judgment R1). Docstring sweep: `_deciding_sub_match`, `resolve_bash_permission_detailed`, and `_decide`'s own docstrings updated to stop naming the deleted mechanism, and to stop repeating a previously-retracted "pure" claim about `_decide` (see "What turned out wrong" below).
- `toolguard/hook.py` -- two docstring fixes: `_log_allowed_command` no longer names `resolve_outer`/`record_unit`; `_log_fallback_allow_warning` now correctly says `fallback_warning` is computed structurally in `resolve.py`'s own `_decide` (not via a text-marker check in `compound.py`, which is what production actually did before this refactor and stopped doing at step 4). No hook.py *logic* was touched.
- `toolguard/config_types.py` -- four `UnitVerdict` docstring references to the deleted `_resolve_leaf_detailed` repointed at `judge_unit`/`CommandUnit`.
- `test/unit/test_compound_resolve_seam.py` -- new file, written at step 0 before any production code moved, and kept afterward as ordinary regression coverage. 17 tests in 5 classes: `TestSubMatchesCharacterization` (the 7 shapes from Plan B step 0 -- `sub_matches` order/content is NOT corpus-tracked, so this is the actual safety net for that field), `TestAskFloorFallbackMatrix` (judgment R3's {stub decision} x {undecidable_fallback} grid, 3 tests covering all 12 cells via subTest), `TestAskFloorStubOverrideNeverLeaks` (judgment R3 / Plan A's A4 test -- an ask-floor stub's own allow-over-deny override must never reach `RuntimeVerdict.overrides`), `TestUnitFromTuple` (judgment R5's explicit ask for this adapter's own test), `TestJudgeUnitInvariants` (judgment R5's two new failure modes -- length mismatch and unrecognized `kind` both raise `ValueError` -- plus two `decompose`/`_unit_for` shape checks).

Not touched: `toolguard/permission_resolution.py::_resolve_leaf` reference (still names the still-live `_resolve_leaf`, correct as-is), `toolguard/config.py`, `toolguard/permission_resolution.py` (these two show as modified in `git status` but from a **concurrent session** -- see "Housekeeping note" below).

## Is the cycle actually gone?

Yes, verified two ways, not just asserted:

**Structural.** `judge_unit`'s signature is `judge_unit(unit, part_verdicts, undecidable_fallback="ask")` -- no `Callable` parameter at all. The only `Callable[[str], ...]`-typed parameters left in `compound.py` are `resolve_one` on `_resolve_leaf`/`check_compound_permission`/`resolve_compound_permission[_detailed]` -- the legacy driver family, supplied by test closures or `check_compound_permission`'s own closure over `permissions.check_permission`, never by `resolve.py`. `resolve.py` no longer imports or calls `resolve_compound_permission_detailed` at all; it imports `decompose`, `judge_unit`, `_combine_strictest`, `cap_context_words` and calls them with plain data.

**Dynamic.** Ran a `sys.settrace` probe (disclosed, read-only) across three real `resolve_bash_permission_detailed` calls exercising a multi-leaf plain compound, an ask-floor leaf under `allow_with_warning`, and a mixed undecidable+plain compound, recording every function call crossing the `toolguard.compound` <-> `toolguard.resolve` module boundary:

```
resolve.py -> compound.py calls observed: 14
  ('toolguard.resolve', 'toolguard.compound', '_combine_strictest')
  ('toolguard.resolve', 'toolguard.compound', 'cap_context_words')
  ('toolguard.resolve', 'toolguard.compound', 'decompose')
  ('toolguard.resolve', 'toolguard.compound', 'judge_unit')
compound.py -> resolve.py calls observed (THE CYCLE, must be ZERO): 0
```

Re-ran this exact probe again after the docstring sweep and the R5 test additions (no production code changed in between) to confirm nothing regressed -- same result.

## Abandon gate

Not taken. Step 3 (extracting `judge_unit`) was mechanical: the driver resolves `unit.parts` first via `resolve_one`/`resolve_outer`, builds `UnitVerdict`s via two small adapters (`_unit_from_tuple`, `_unit_from_probe` -- the latter deleted again at step 5 once `resolve_outer` itself was removed), and hands them to `judge_unit`, which never called back into anything. No new conditional keyed on `kind` past the four that already existed, and no branch ever needed a second look at a resolver. The full suite (2,597 tests at that point) stayed green on the first run after the extraction.

## Concept count

**Before: 10** (per the judgment's count -- the walk, the isinstance dispatch, the second PEG split, the lossy `resolve_one` 3-tuple with a hidden side effect, the `resolve_outer` 5-tuple probe that must NOT have that side effect, `record_unit` as a third callback, `_combine_strictest` used at two altitudes, `fallback_kind` computed two ways for the same sub-command, the emergent cross-module invariant that made `sub_matches` correct only because three callbacks interlocked, and the runtime cycle itself).

**After: 7**, exactly what the judge projected: (1) `decompose -> [CommandUnit]`, four kinds, pure; (2) `parts` = "strings a rule engine must decide on this unit's behalf"; (3) `judge_unit(unit, part_verdicts, fallback) -> UnitVerdict`, pure, owns both floors; (4) `_combine_strictest([UnitVerdict]) -> RuntimeVerdict`; (5) the driver loop in `resolve.py`, including the recording rule -- now `unit.audits_as_one`, read as data, not re-derived from `unit.kind`; (6) the positional invariant `part_verdicts` matches `unit.parts` in order and length, enforced with a loud `ValueError` rather than left as a silent-misattribution risk; (7) the legacy 3-tuple adapter (`_unit_from_tuple`) for the off-production-path API. Nothing is a callback; nothing is a side channel; concepts 1, 3, and 4 are independently unit-testable with literals, which none of the pre-refactor pieces were.

## Where the ASK floor ended up, and why

Unmoved in substance, relocated in file position: it now lives in `compound.judge_unit`'s `'inline_code'` branch, verbatim in wording and branch order from the old `_resolve_leaf_detailed`, with only the source of `decision`/`reason`/`additional_context`/`matched_rule`/`provenance` changed from `probe(outer_cmd)`'s five return values to `part_verdicts[0]`'s five attributes. Three reasons, matching the judgment's own ranking:

1. `compound` has a second caller (`check_compound_permission`, and ~40 tests through `resolve_compound_permission[_detailed]`) that never touches `resolve.py`. Moving the floor there would either duplicate it (the exact defect TOO-45 D4 already fixed once) or leave that surface unfloored.
2. The floor is triggered by a parser fact (`LeafCommand.ask_floor`, set in `command_extractor._apply_leaf_policy`), which `compound` reads and `resolve.py` has no reason to know about.
3. The floor never needed the *ability* to resolve the stub, only the *result* -- `probe()` was called exactly once, and once `decompose` publishes that stub as `unit.parts[0]`, the caller resolves it and hands the result in. The callback was load-bearing only for *timing*, never for the decision itself.

## What turned out to be wrong in the plan/judgment, verified against the real code

Both documents were themselves careful about noting where they might be wrong, and mostly held up. Three things I had to correct while implementing:

1. **The judgment's own B3 finding recurred in code I had to touch, not just in the plan's prose.** The judgment flagged that Plan B's text called `_decide` "already factored out, already pure" -- a claim the `resolve.py` module docstring had already retracted once (TOO-45 R6-S2: pattern matching reads live filesystem state). What I found on actually reading `resolve.py`'s pre-refactor `_decide` closure is that its OWN docstring, predating this ticket, already opened with the literal words "Pure per-sub-command decision" -- the retracted claim was not just in the plan document, it was already sitting in the codebase itself, and I would have silently carried it forward by copying the old docstring's opening line verbatim (which I did, in the first draft of step 4). Caught and fixed during the docstring sweep: `_decide`'s docstring now says "Side-effect-free... but NOT pure in the strict sense" and names the retraction explicitly, so a future reader who goes looking for why won't rediscover B3 from scratch.
2. **Plan B's own driver pseudocode gated `overrides` recording on `unit.kind == "plain"`, not `unit.audits_as_one`.** The judgment's R1 explicitly asked only for the `sub_matches` recording rule to move onto `CommandUnit` as data; it did not mention the parallel `overrides` recording check in the same loop. I used `not unit.audits_as_one` for that check too (rather than leaving one `unit.kind` comparison in place next to the `audits_as_one` one), since it is the identical concept (only a unit whose own parts are real per-part decisions can have a real allow-over-deny override to report) and leaving a second, differently-spelled version of the same distinction in the same function is exactly the kind of drift risk R1 exists to close. Verified behaviourally identical either way (only `'plain'` units ever have non-empty `parts` among the kinds where `audits_as_one` is `False`), and pinned by `TestAskFloorStubOverrideNeverLeaks`.
3. **My own assumption while writing step-0 characterization tests was wrong, and the plan's own worked example papered over it.** I initially wrote a test asserting `git status && ls` decomposes into ONE `CommandUnit` with two PEG-split `parts`. It does not: `extract_structured` already splits `&&` into two separate top-level leaves before `compound.py` ever sees them, so it decomposes into TWO `'plain'` units, each with exactly one part. The genuine "one leaf, multiple PEG sub-commands" case only happens when a single `LeafCommand`'s own *text* still contains an unsplit compound (constructed directly, not by grammar output at the top level) -- I added a dedicated test for that case (`test_unit_for_peg_splits_a_plain_leaf_into_multiple_parts`) using a hand-built `LeafCommand`. Neither plan document states this distinction wrongly outright (Plan B's own step-0 example, `diff <(cat a) <(cat b) && ls -la` -> two entries, is accurate -- it just doesn't happen to be a "multiple parts in one leaf" example either), but it is easy to read Plan B's "quads" language and assume the multi-part-per-leaf case is the common one; on this grammar, for the operators Claude Code actually emits, it appears not to be.

## Full gate results

```
uv run python -m unittest discover -s test -t .
  Ran 2604 tests in 37.082s -- OK
  (2,587 baseline + 10 step-0 characterization tests + 7 judgment-R5 tests)

uv run python tools/corpus_build.py --verify
  In-process: 6401 cases in 9.12s. End-to-end: 61 cases in 3.67s.
  OK: no differences.

uv run python tools/architecture_fitness.py --layers
  completeness: All modules map to exactly one layer.
  direction: No cross-layer direction violations.

uv run python tools/architecture_fitness.py --predicates
  R1: PASS (0 bare verdict-tuple returns anywhere in scope)
  R2: PASS
  R3: PASS
  R5: PASS
  R6: PASS

uv run ruff check .
  All checks passed!
```

No golden was ever regenerated. No pre-existing test was modified or deleted.

## Housekeeping note (not my work, flagged for awareness)

`git status` also shows `toolguard/config.py`, `toolguard/permission_resolution.py`, and several `test/verdict_corpus/*`/`test/unit/test_*.py` files as modified, plus two other coder-task-recall memory notes I did not write ("TOO-45 corpus sub-verdict extension", "TOO-45 resolution seam Protocols"). File mtimes confirm all of those last changed at 10:16-10:22, before my session's own edits began (10:44 onward) -- a **concurrent coder-subagent session** working other TOO-45 sub-tasks in the same working tree, not something this task touched or should touch. My own baseline (10:38) and every verification since already ran against that state, consistently, so it does not affect this task's correctness -- but it is worth knowing two sessions had uncommitted work in the same tree at once.

## Subjective difficulty

Moderate, and cheaper than either plan predicted (Plan B: 3-5h; judgment's corrected estimate: 5-7h). The design being simple paid off exactly as the owner's heuristic predicts: every step left the suite green on the first or second try, the one real mid-implementation bug (the "quads" list feeding `_combine_strictest` inside `_resolve_leaf_detailed`'s plain-path, which I initially missed in step 1's first pass) was caught immediately by the test suite rather than by inspection, and the abandon gate was never close to triggering. The hardest part was not the code -- it was keeping straight, across seven steps, which of the two drivers (the still-alive legacy one vs. the new production one) a given docstring paragraph was describing, since both exist simultaneously by design and describing one while thinking about the other is the easiest way to introduce a NEW stale reference while sweeping the old ones.
