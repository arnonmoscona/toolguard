---
title: TOO-45 D1a debts implementation report
type: note
permalink: toolguard/too-45/too-45-d1a-debts-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Implemented all ten items (A-J) of the TOO-45 D1a review-debt brief on branch `too-45`. Nothing here changes any verdict; `tools/corpus_build.py --verify` reports `OK: no differences` at the end, and is byte-identical across two regenerations run at different wall-clock times. `toolguard/permission_resolution.py` remains staged (new file, D1a) and was never unstaged; nothing was committed; no git write operations were run.

## Files touched

New:
- `test/unit/test_permission_resolution.py` -- the module's own test home (item G), hosting item A's and a negative-control test.

Modified (production/test code):
- `toolguard/permission_resolution.py` -- item A comment, item F docstring addition, item H trim (55.6% -> 39.0% docstring share), item I fix.
- `toolguard/tools/decision.py` -- item E, `matched_rule` threaded onto `Decision`.
- `test/verdict_corpus/fixture_loader.py` -- item E, widened tracked fields + e2e conflict-message capture with timestamp normalization.
- `test/unit/test_architecture.py` -- item B, `LAYERS` tuple entry.
- `test/unit/test_architecture_fitness.py` -- item C strengthened assertion; item J updated/added tests.
- `tools/architecture_fitness.py` -- item J, tokenize-based `find_enrichment_footprint`.
- `tools/corpus_build.py` -- one stale comment fix (renamed helper reference).
- `docs/architecture.md` -- item D.
- `test/verdict_corpus/README.md` -- item E schema docs.
- `test/unit/test_verdict_corpus.py` -- item E docstring/message-text sync.

Regenerated data (mechanical, not hand-authored):
- `test/verdict_corpus/goldens.jsonl`, `test/verdict_corpus/e2e_goldens.jsonl` -- regenerated per item E; confirmed byte-identical across two regenerations at different wall-clock times (sha256 matched).

`.pyscn.toml` was touched only for item C's demonstration mutation and restored byte-identical (sha256 verified) -- it shows as pre-existing D1a-modified in `git status`, not further changed by me.

I did not read report-only memory files from other concurrent agents active in this repo (several untracked `toolguard-memories/TOO-45/*.md` files exist that I did not write -- e.g. "TOO-45 R3 ..." and "TOO-45 ruff configuration proposal.md" -- these are other sessions' artifacts, left untouched).

## Item-by-item notes

**A (highest value).** New test `test_permission_resolution.TestDenyUnderBrokenConfigKeepsProvenance.test_deny_under_parse_failure_retains_provenance_context_and_matched_rule` builds a `Configuration` with a deny rule carrying `additionalContext` AND a `parse_failures` entry, asserts all three (`provenance`, `additional_context`, `matched_rule`) survive. A negative-control sibling test confirms the floor still clamps a non-deny normally under the same broken config. Demonstrated: deleting `or resolved.decision == "deny"` from `_apply_ask_floor` makes the new test FAIL (`provenance` unexpectedly `None`) while the rest of the 2323-test suite (baseline + 2 new tests) stays green except that one failure -- confirming the brief's claim that nothing else catches it. Restored, re-verified green (sha256 of restored file matches original).

**B.** Added `("toolguard.permission_resolution", frozenset({"toolguard.config_types"}))` to `test_architecture.py`'s `LAYERS`. Demonstrated: adding `from toolguard.config import Configuration` to `permission_resolution.py` fails both `test_leaf_modules_do_not_import_config` and `test_each_leaf_imports_only_from_layers_below_it`. Restored, re-verified green.

**C.** Strengthened `test_check_layers_runs_on_real_tree` to assert `report.unmapped == []`, with a docstring explaining why `report.ok` is deliberately NOT asserted (3 pre-existing direction violations, out of scope). Demonstrated: removing `permission_resolution` from `.pyscn.toml`'s engine-layer `packages` list makes the test fail with `['permission_resolution'] != []`. Restored (sha256 verified), re-verified green.

**D.** Fixed the `config.py` line (now "Configuration loading and hierarchy (query object; see permission_resolution.py...)") and added a `permission_resolution.py` entry to `docs/architecture.md`'s package inventory, worded to match `technical-notes.md`'s established tone. Checked both docs for other D1a-falsified statements (grepped for `Configuration.resolve_permission_detailed`, `_detect_override`, `_apply_ask_floor`, `apply_parse_failure_floor`, `_provenance_for_pattern`) -- found none beyond what the pre-existing unstaged diff had already fixed. Note: `docs/architecture.md`'s test-file listing (lines ~70-91) is incomplete (missing `test_resolve.py`, `test_verdict_corpus.py`, `test_architecture.py`, etc.) but this predates D1a and is not something D1a falsified, so left untouched -- out of this item's scope, flagged here for visibility.

**E.** Two widenings:
1. `matched_rule` added to `Decision` (sourced from `BashResolution.matched_rule`/`FileResolution.matched_rule`, which were already computed but never threaded through), to `decision_to_golden`, and to `TRACKED_FIELDS`.
2. The overridden deny's provenance is only ever observable via the e2e corpus's conflict-log side effect (confirmed from `fixture_loader.py`'s own design docs and `hook._format_conflict_message`). Replaced the old presence-only `_count_stream_log_entries` with `_stream_log_snapshot`/`_new_stream_log_text`, which captures the actual newly-appended conflict-log TEXT (not just a count). Added `conflict_message` to the e2e golden (present only when a conflict was logged) and to `compare_e2e_goldens`'s tracked-field comparison (parallel to `additionalContext`'s text). **Had to add timestamp normalization** (`_normalize_log_timestamps`, replacing `## YYYY-MM-DD HH:MM:SS - CONFLICT` with `## <TIMESTAMP> - CONFLICT`) because the raw conflict-log text embeds a real wall-clock timestamp, which would otherwise break the corpus's documented byte-identical-across-regenerations guarantee. Verified byte-identical across two regenerations run ~8 minutes apart (different real timestamps), confirming the normalization works.

Regenerated corpus: `--verify` before regeneration correctly reported differences (`KeyError: 'matched_rule'` on the very first run against stale goldens, since the old goldens lacked the new key entirely -- then, after adding the field to the golden schema but before adding it to the comparison correctly, genuine tracked-field diffs). After `--generate`, `--verify` reports `OK: no differences`.

Demonstrated both mutations against the regenerated corpus:
- `matched_rule=None` at its source (`_resolve_unclamped`): 13 existing unit tests fail (e.g. `test_resolve.py`'s matched-rule pins), AND `corpus_build.py --verify --strict-prose` now FAILs with ~dozens of `matched_rule` tracked-field diffs (previously, per the brief, this reported `OK: no differences`).
- `overridden_provenance=None` in `_detect_override`: 2 failures + 2 errors in the unit suite, AND `--verify --strict-prose` FAILs with `conflict_message` diffs showing `[user: <FIXTURE_HOME>/...]` (expected) vs `[unknown]` (mutated) for every `override_breadth` case.

Both mutations restored (sha256 verified); `--verify` clean again.

**F.** Added a "Caller obligation" paragraph to `apply_parse_failure_floor`'s docstring: `parse_failures` must be the real, complete value, never `()` or a filtered subset. Signature unchanged.

**G.** New file `test/unit/test_permission_resolution.py`. Did not relocate the ~28 existing cascade call sites in `test_configuration.py`/`test_hard_deny.py`/`test_hierarchical.py`/`test_logging_streams.py`/`test_takeover_mode.py`.

**H.** Before: 202/363 docstring lines = 55.6% (AST-measured, matches the brief's claim exactly). After: 108/277 = 39.0%. Kept: the HARD INVARIANT block on `apply_parse_failure_floor` (verbatim), the TOO-15 unconfigured-tool-vs-no-match inline comment block in `_resolve_unclamped` (untouched -- it was never a docstring), and added the item-A explanatory comment on `_apply_ask_floor`'s guard. Cut: Args/Returns restatement, extraction history narration, and other duplication of what the code already says.

**I.** Module docstring now says a double implementing the six-member surface is sufficient "for THIS module's own functions", and explicitly calls out that a double driven through `toolguard.resolve` additionally needs `resolve_config_path` and `resolved_undecidable_fallback` (confirmed both are called directly on `config` in `resolve.py`).

**J.** `find_enrichment_footprint` now tokenizes (`tokenize.generate_tokens`) instead of doing a raw substring scan: a `NAME` token spelled `additional_context`/`additionalContext` counts as real coupling; a `STRING`/`COMMENT` token mention counts as prose-only (reported separately, not dropped). Returns a new `EnrichmentFootprint` dataclass (`coupled`, `prose_only`); `compute_predicates`/`render_predicates_text` updated to report both counts. Updated the two pre-existing `TestFindEnrichmentFootprint` tests to match the corrected (deliberately, ticket-authorized) semantics -- one of them (`b.py`, a dict-key string mention) moved from the coupled bucket to the prose bucket, which is exactly the over-reporting behavior item J exists to fix; documented this as a deliberate, ticket-authorized change in the test's own docstring. Added a new synthetic-docstring-only test per the brief's explicit ask. **Corrected number for the current tree: 9 files coupled (real code), 6 files prose-only (15 total mentions)** -- matches the brief's own claim exactly (`compound`, `config_types`, `hook`, `log_writer`, `permission_resolution`, `resolve`, `rule_entry`, `testing.sandbox`, `tools.decision` are coupled; `config`, `config_write_guard`, `rule_sort`, `toml_scan`, `tools.config_access`, `tools.installer` are prose-only). Not tuned to hit any target -- this is the tree's actual current state.

## Acceptance output (verbatim, final run)

```
$ uv run python -m unittest discover -s test -t .
...
Ran 2325 tests in 18.463s

OK
```

```
$ uv run python tools/corpus_build.py --verify
...
In-process: 6401 cases in 8.44s. End-to-end: 61 cases in 3.34s.

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
VIOLATIONS (3):
  - auto_migrate (config) -> scripts.migrate_permissions (tooling) at line 172 [local import]
  - config_divergence (config) -> error_log (runtime) at line 16
  - hook (runtime) -> tools.decision (tooling) at line 697 [local import]
```

```
$ uv run python tools/architecture_fitness.py --predicates
...
=== enrichment footprint (tracked, not a predicate): 9 coupled (real code), 6 prose-only ===
  [coupled] compound
  [coupled] config_types
  [coupled] hook
  [coupled] log_writer
  [coupled] permission_resolution
  [coupled] resolve
  [coupled] rule_entry
  [coupled] testing.sandbox
  [coupled] tools.decision
  [prose]   config
  [prose]   config_write_guard
  [prose]   rule_sort
  [prose]   toml_scan
  [prose]   tools.config_access
  [prose]   tools.installer
```

```
$ uv run ruff format . && uv run ruff check .
2 files reformatted, 146 files left unchanged
All checks passed!
```

```
$ uv run python tools/check_doc_links.py
All internal documentation links resolve.
```

(Re-ran the full unit suite again after `ruff format` reformatted 2 files -- still `Ran 2325 tests ... OK`.)

## Fail/pass demonstrations (items A, B, C) -- condensed; full transcripts are in the session, key lines below

**Item A** (deleted `or resolved.decision == "deny"` guard):
```
FAIL: test_deny_under_parse_failure_retains_provenance_context_and_matched_rule
AssertionError: unexpectedly None   (resolved.provenance)
-- full suite: Ran 2325 tests, FAILED (failures=1) -- exactly the one new test
```
Restored (sha256 match) -> `Ran 2325 tests ... OK`.

**Item B** (added `from toolguard.config import Configuration`):
```
FAIL: test_leaf_modules_do_not_import_config
AssertionError: 'toolguard.config' unexpectedly found in {...}
FAIL: test_each_leaf_imports_only_from_layers_below_it
AssertionError: False is not true : ... imports ['toolguard.config'], which is not below it in the layering
```
Restored (sha256 match) -> `Ran 7 tests ... OK`.

**Item C** (removed `permission_resolution` from `.pyscn.toml` engine-layer packages):
```
FAIL: test_check_layers_runs_on_real_tree
AssertionError: Lists differ: ['permission_resolution'] != []
```
Restored (sha256 match) -> `OK`.

**Item E mutation 1** (`matched_rule=None` at source): unit suite `FAILED (failures=13)`; `corpus_build.py --verify --strict-prose` exits 1 with many `matched_rule: expected 'X' actual None` diffs (previously `OK: no differences`, per the brief). Restored -> `OK: no differences`.

**Item E mutation 2** (`overridden_provenance=None`): unit suite `FAILED (failures=2, errors=2)`; `--verify --strict-prose` exits 1 with `conflict_message` diffs showing `[unknown]` in place of the real provenance. Restored -> `OK: no differences`.

## Self-review results

- No async/await, no threading, no new local (function-body) imports anywhere I touched -- confirmed by grep and by `test_architecture.TestNoNewLocalImports` passing.
- No new runtime dependency (only stdlib `tokenize`/`io`/`re` used, already-approved stdlib-only discipline for `tools/`).
- `uv.lock`/`pyproject.toml` untouched by me (the 1-line `uv.lock` diff is pre-existing D1a work).
- Every new/changed test carries a Given/When/Then docstring, kept in sync with what the test does (including the two item-J tests whose assertions changed -- their docstrings explicitly explain and justify the change as ticket-authorized, not a weakening).
- No existing test was weakened -- the two `TestFindEnrichmentFootprint` tests I changed reflect a deliberately, ticket-mandated (item J) behavior change to production code (`find_enrichment_footprint`'s counting semantics), not a loosened assertion protecting unrelated code; this is called out explicitly in the affected test's own docstring per the ticket's "authorized" carve-out, not decided unilaterally.
- All temporary files/scratch work stayed under the designated scratchpad backup directory; nothing was left in a `coder-test/` directory (none was created -- all new tests landed directly in the main suite as instructed).
- Never ran `git checkout`/`restore`/`stash`/`reset`; all reversibility was via scratchpad-backed `cp` + `sha256sum` verification, confirmed for every mutation demonstrated.
- Did not copy the repository.
- Did not commit; `toolguard/permission_resolution.py` remains staged exactly as it was (never unstaged).

## Timing / rough cost estimate

Total wall-clock: ~10:01 to ~10:30 (about 30 minutes), single continuous session, no interruptions.

- Planning/investigation (reading brief, existing code, memory setup): ~10:01-10:09 (~8 min).
- Implementation (items A-J, all demonstrations, corpus regeneration): ~10:09-10:26 (~17 min).
- Self-review (final full-suite reruns, ruff, guard/layers/predicates, doc-link check, diff review): ~10:26-10:29 (~3 min).
- Report + memory writeup: a few more minutes.

Rough token-based cost estimate for this session (Sonnet 5 pricing, approximate): on the order of $1-2 total, given the volume of file reads and tool calls involved. This is a rough order-of-magnitude estimate, not a precise accounting.
