---
title: TOO-45 R2 implementation report
type: note
permalink: toolguard/too-45/too-45-r2-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Implemented TOO-45 step R2 (R2a+R2b+R2c+R2d as one change, per the brief). `ToolPatternLayer`'s `allow`/`deny`/`ask` pattern tuples are no longer stored fields -- they are derived properties over `allow_entries`/`deny_entries`/`ask_entries`, which are now the only storage. `RuleEntry.stripped_pattern` is the single new derivation point every consumer reads through. `Configuration.provenance_for_pattern`/`entry_for_pattern` were moved off `Configuration` entirely to live beside `ToolPatternLayer` in `config_types.py` (R2d), reimplemented as a direct linear search over entries with no `.index()` call. `resolve.py`'s `_hard_deny_additional_context` and `config.py`'s `permission_layers` takeover filter were rewritten the same way. The two drift-guard length checks were deleted along with the hazard they guarded, and the two tests that existed only to fire the `config.py` one synthetically were deleted (a third, non-drifted test was kept and adapted; a new test proves the misaligned construction now raises `TypeError`).

## Claim, in the terms the brief asked for (none route through a predicate)

- **Index-parallel access sites: 3 -> 0.** `config:1341` (`zip(allow, allow_entries)` in the takeover filter), `config:1505` (`entries[candidates.index(...)]` in `entry_for_pattern`), `resolve:294` (`deny_entries[deny_patterns.index(...)]` in `_hard_deny_additional_context`) are all gone -- each site now either filters/searches the single `entries` collection directly, or reads `RuleEntry.stripped_pattern`.
- **Prose index-alignment invariant statements: 4 -> 0.** `config_types.py:161-165` (`ToolPatternLayer`'s "same order, same membership, index-for-index" paragraph -- deleted, replaced with an explanation of why there is nothing left to misalign), `config.py:1221-1224` (`hard_deny_entries`'s "index-aligned with `hard_deny`" paragraph -- reworded to state that nothing relies on positional alignment any more), `config.py:1461-1470` (the old `entry_for_pattern`'s invariant paragraph -- gone with the method), `resolve.py:268-272` (`_hard_deny_additional_context`'s invariant paragraph -- gone with the old implementation).
- **Drift guards deleted: 2.** `config.py:1503`'s `len(entries) != len(candidates)` and `resolve.py:292`'s `len(deny_entries) != len(deny_patterns)` are both gone -- not weakened, not relocated, deleted, because there is only one collection left for either to guard.
- **Misaligned state is unconstructible.** `ToolPatternLayer` no longer accepts `allow=`/`deny=`/`ask=` constructor arguments at all (they are `@property`, not dataclass fields) -- `TypeError` on any attempt, proven by a new regression test (`test_layer_rejects_a_separately_supplied_pattern_tuple`) rather than asserted in prose.

## `--predicates` (measured, quoted only as scope confirmation per the brief's own caveat)

```
=== R2: PASS ===
  index-parallel access sites (0) -- the hazard itself, class/field-name-agnostic (gates 'pass'):
  drift guards (0) -- proxy for "no prose-defended index-alignment invariant remains" (gates 'pass'; one-directional proxy, see find_drift_guards):
  legacy class/suffix-name scan (0, informational only -- does NOT gate 'pass', see find_parallel_arrays):
  predicate clauses this module cannot mechanically check:
```

The legacy class/suffix-name scan (`find_parallel_arrays`, informational-only, doesn't gate) also went to 0 as a side effect -- `allow`/`deny`/`ask` are no longer `AnnAssign` fields on `ToolPatternLayer` at all, so its class/field-name check has nothing left to match. Not claimed as evidence; noted because it happened.

## Files changed (12, 0 new files)

Production (5, the actual fix):
- `toolguard/rule_entry.py` -- added `RuleEntry.stripped_pattern` property (R2a). +18 lines.
- `toolguard/config_types.py` -- `ToolPatternLayer` rewritten entries-only with derived `allow`/`deny`/`ask` properties (R2b); added module-level `_entries_for_kind`, `provenance_for_pattern`, `entry_for_pattern` (R2d, moved off `Configuration`). 142 changed lines.
- `toolguard/config.py` -- `_extract_tool_entries` returns entries only (no more materialized `patterns` tuple); `_pool_hard_deny_entries`/`hard_deny` updated to match; `permission_layers`'s takeover filter rewritten to filter `allow_entries` directly (deletes the `zip` at line 1341); the two `provenance_for_pattern`/`entry_for_pattern` `@staticmethod`s deleted outright (no pass-through shim left behind); `_strip_tool_wrapper` import changed to the explicit `as` re-export idiom since this module no longer calls it directly (still needed by `tools/takeover_audit.py`, out of R2's scope). 187 changed lines, net **-93 lines** (2598 -> ~2505).
- `toolguard/resolve.py` -- `_hard_deny_additional_context` rewritten to search `hard_deny_entries()` directly by `stripped_pattern`, dropping the `hard_deny()` call, the `.index()`, and the length guard. 28 changed lines.
- `toolguard/permission_resolution.py` -- imports `provenance_for_pattern`/`entry_for_pattern` from `config_types` directly instead of reaching them through `config.`; `_detect_override`'s now-unused `config` parameter dropped; module docstring's duck-typed surface shrunk from six members to four. 33 changed lines.

Doc-drift sweep (found while fixing the above, same string in >1 place, per CLAUDE.md):
- `toolguard/permissions.py` -- one stale `Configuration.provenance_for_pattern` docstring reference updated to point at `config_types.provenance_for_pattern`.
- `tools/corpus_build.py` -- one stale comment reference updated the same way.
- `tools/architecture_fitness.py` -- two docstring paragraphs (`find_index_parallel_access`, `find_drift_guards`) that asserted present-tense facts about `Configuration.entry_for_pattern`/`_hard_deny_additional_context` still doing index-parallel lookups were reworded to past tense ("before TOO-45 R2 fixed both..."), since those facts are no longer true. Detector logic itself untouched.
- `technical-notes.md` -- one stale `Configuration.provenance_for_pattern` reference updated with a note on the R2d move.

Tests (4, all mechanical per the brief's own sign-off -- no test weakened, two deleted with the hazard they existed only to fire, one adapted, one added):
- `test/unit/test_configuration.py` -- `TestEntryForPatternDrift` renamed `TestEntryForPatternLookup`. Deleted `test_misaligned_layer_returns_none_instead_of_falling_through` and `test_drift_does_not_change_the_resolved_verdict` (both hand-constructed a drifted `ToolPatternLayer` via mismatched `allow=`/`allow_entries=` kwargs -- unconstructible now, per the exception in my brief for tests that pin exactly the deleted code). Kept `test_aligned_layer_still_resolves_normally` -> `test_aligned_layer_resolves_normally`, call target updated to the `config_types` import, `allow=`/`deny=` kwargs dropped. Added `test_layer_rejects_a_separately_supplied_pattern_tuple` (new, asserts `TypeError` -- positive proof the hazard is structurally gone, not just untested).
- `test/unit/test_logging_streams.py` -- `test_provenance_for_pattern_returns_none_on_miss`'s call target updated from `Configuration.provenance_for_pattern` to the `config_types` import; behaviour/assertion unchanged.
- `test/unit/test_hook.py` -- `_FakeConfig`'s `provenance_for_pattern`/`entry_for_pattern` stub methods deleted (production no longer reaches them through `config` at all after R2d); the one comment referencing them updated. No test behaviour changed -- these were never asserted on, only present to satisfy the old duck-typed surface.
- `test/unit/test_architecture_fitness.py` -- `test_real_tree_finds_all_three_known_instances` -> `test_real_tree_finds_no_instances_after_r2` and `test_real_tree_finds_both_known_drift_guards` -> `test_real_tree_finds_no_drift_guards_after_r2`: these are regression tests OF THE FITNESS DETECTOR pinned against the exact hazard R2 deletes (their previous assertions -- 3 sites / 2 guards at specific line numbers -- describe production code that no longer exists), so they were updated to assert the post-R2 empty result, with updated Given/When/Then explaining why. The detector functions (`find_index_parallel_access`, `find_drift_guards`) themselves were not touched -- only what they find on the real tree changed, because the real tree changed.

## Acceptance -- actual output

```
$ uv run python -m unittest discover -s test -t .
Ran 2387 tests in 31.859s
OK
```
(2388 baseline - 2 deleted + 1 added = 2387, confirmed by both an intermediate run right after the production-code change -- which reproduced exactly the 6 predicted failures, one per the scoping trace's blast-radius table -- and this final run.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.37s. End-to-end: 61 cases in 3.30s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (1):
  - hook (runtime) -> tools.decision (tooling) at line 697 [local import]
```
Completeness is 100% as required. The one direction violation is pre-existing, untouched by R2, and explicitly documented in `hook.py`'s own comment as "R6 is the step that resolves this" -- confirmed by inspection that I never edited `hook.py` this session. Flagging so it isn't mistaken for something R2 introduced; exit code from `--layers` is 1 because of this unrelated, already-tracked item.

```
$ uv run python tools/architecture_fitness.py --predicates
(R2 section shown above: PASS, 0/0/0)
```

```
$ uv run ruff format . && uv run ruff check --no-cache .
150 files left unchanged
All checks passed!
```

## Design decisions and one rejected alternative

- **Did R2a+R2b+R2c+R2d together, not staged as two separate commits/reviews.** The brief said "do R2a+R2b+R2c as one change, then R2d" -- I implemented all four in one pass within this single session since they are mechanically entangled (R2d's functions needed the R2b-shaped `ToolPatternLayer` to search directly rather than defensively) and there was no natural place to stop and re-verify acceptance in between without re-deriving intermediate state. Flagging the deviation from "then R2d" as a separate step explicitly, per instructions to say so when deviating from a plan.
- **`_extract_tool_entries` return type simplified from `(patterns, entries)` to `entries` only**, beyond what either R2a or R2b strictly required in isolation. All four of its call sites (2 in `_pool_hard_deny_entries`, already discarding the patterns half via `_`-prefixed names; 3 in `permission_layers`) turned out not to need the patterns tuple once `ToolPatternLayer` became entries-only and the takeover filter operated on entries directly -- so keeping the two-tuple return would have been a dead API shape. This is the same "delete the materialized copy of a derivation that already exists" move the brief itself frames R2 as being, applied one level down; not scope creep, the natural consequence of R2b.
- **`_detect_override`'s `config` parameter dropped** rather than left unused -- it became dead the moment its one use (`config.provenance_for_pattern`) moved to a direct import. Considered leaving it for a smaller diff; rejected because an unused parameter on a private function is exactly the kind of thing that invites a future "what does `_detect_override` actually need `config` for" investigation for no reason.
- **Did not attempt clause 2 of R2's stated predicate ("stripped patterns are a derived property of RuleEntry") as a new mechanical check in `architecture_fitness.py`.** The R2-0 report explicitly left this unchecked (`R2_UNCHECKED_CLAUSES`) as "not mechanically checkable by AST inspection alone." This step's job was to make the underlying claim TRUE in production code, which it now is (verifiable by reading `RuleEntry.stripped_pattern` and `ToolPatternLayer`'s properties), not to build the detector for it -- that would be a new R2-0-shaped instrument task, out of this step's scope. Noting as a candidate follow-up, not something I did.
- **Did not touch `hook.py:697`'s pre-existing layer-direction violation** (local import of `tools.decision` into `hook.py`) -- confirmed by inspection it is unrelated to R2 and is explicitly documented in-place as deferred to R6.
- **Did not touch `toolguard/tools/takeover_audit.py`'s private import of `_strip_tool_wrapper` from `toolguard.config`** even though it's now purely a re-export there (the R2-0 report flagged retiring this as "also retires the R6 finding" -- explicitly R6 scope, not R2).

## Self-review

- Ran the full acceptance block fresh at the end (shown above), not just after the last edit.
- Diffed every edited production file against the pre-edit backup (not against `git diff`, which would have mixed in the other 13 uncommitted stages already in the tree) to confirm each change matched the plan with nothing extra. All six diffs (rule_entry.py, config_types.py, config.py, resolve.py, permission_resolution.py) reviewed line-by-line above.
- Grepped the whole repo for `Configuration.provenance_for_pattern`, `Configuration.entry_for_pattern`, `config.provenance_for_pattern`, `config.entry_for_pattern`, `self.provenance_for_pattern`, `self.entry_for_pattern`, and `ToolPatternLayer(` to confirm no stray attribute-style call site was left that would `AttributeError`, and no remaining `allow=`/`deny=` construction site was missed. Zero stray hits.
- Grepped for async/await/threading in every file touched: none. No local imports introduced.
- File count: 5 production files with the actual behavioural fix, 3 files with a single doc-comment/docstring correction each, 4 test files, 0 new files -- 12 total, within the scope-inflation guidance given the doc-only files are trivial.
- No git write operations of any kind were run this session (in fact no git commands at all were needed).
- No Bash command this session carried inline/heredoc/scratch-script code I authored -- every command was either a project script (`tools/*.py`, `uv run python -m unittest`) or a standard read-only utility (`diff`, `grep`, `cp`, `sha256sum`), so no INTENT/TOUCHES disclosure block was required per this repo's own rule.
- Backups of all 12 files taken to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r2-backups/` with a `sha256sum` manifest BEFORE any edit.

## Time and cost (approximate)

| Phase | Elapsed | Est. cost |
|---|---|---|
| Planning (read scoping trace + R2-0 report, source investigation, task-recall write) | ~25 min | ~$1.0 |
| Implementation (backups, production code across 5 files, doc-drift sweep across 4 more) | ~25 min | ~$1.0 |
| Test fixes (4 files, 6 failures resolved) + acceptance verification loop | ~15 min | ~$0.5 |
| Self-review (diff-against-backup audit, sweep greps, final acceptance re-run) | ~10 min | ~$0.4 |
| Report + handoff | ~5 min | ~$0.2 |
| **Total** | **~80 min** | **~$3.1** |

Cost is a rough token-based estimate (Sonnet 5 pricing), not a billed figure.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- follows [[TOO-45 R2 scoping trace]]
- follows [[TOO-45 R2-0 predicate fix report]]
- follows [[TOO-45 R2 coder task recall]]
