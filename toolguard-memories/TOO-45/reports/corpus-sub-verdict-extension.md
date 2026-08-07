---
title: TOO-45 corpus sub-verdict extension - implementation report
type: note
permalink: toolguard/too-45/reports/corpus-sub-verdict-extension
tags:
- task-memory
- TOO-45
- report
---

# TOO-45 corpus sub-verdict extension - implementation report

## What this closes

The golden verdict corpus (`test/verdict_corpus/`) did not capture the compound sub-command breakdown (`RuntimeVerdict.sub_matches`/`overrides`) -- exactly the structural data whose loss was TOO-45's headline audit-trail defect: `hook.py` used to reconstruct which sub-commands of an allowed compound ran by regex-parsing the combined `reason` string, silently dropping 813 of 975 compound-allow corpus cases' audit entries (1,943 sub-commands with no log record at all). `_log_allowed_command` now reads `verdict.sub_matches` structurally instead (TOO-45 R1e), but nothing pinned that fix against a future regression reintroducing the loss. This extension is that pin.

## Schema added

Two new keys on every in-process golden record (`test/verdict_corpus/goldens.jsonl`), always present as a list (never omitted; empty when there's nothing to record):

- `"sub_matches"`: one dict per `UnitVerdict` in `decision.sub_matches`, in order -- `{"sub_command", "decision", "matched_rule", "provenance"}`. Deliberately narrower than the full `UnitVerdict` (excludes `reason`/`additional_context`, which are per-unit prose already covered by the top-level TRACKED fields, and `fallback_kind`, a log-rendering aid) -- exactly the four fields specified in the launching task.
- `"overrides"`: one dict per `(identifier, ConflictOverride)` pair in `decision.overrides`, in order -- `{"identifier", "winning_pattern", "winning_provenance", "overridden_pattern", "overridden_provenance"}`.

Both keys use `RuntimeVerdict`'s own attribute names for discoverability, matching the existing convention (`matched_rule`, `provenance` already mirror attribute names). Paths inside `provenance` are sanitized through the same `sanitize()` ephemeral-path replacement used everywhere else in the module.

**Empty vs omitted, decided**: always emit the key as a list, `[]` when empty, never omitted. Rationale (also documented in `README.md`): a verdict with a structurally-empty breakdown (every file-path tool case; the common case for `overrides`) and a regression that *drops* a genuinely non-empty compound's breakdown down to zero must both be representable, and the diff between "was `[...N entries...]`, now `[]`" is what actually needs to be visible -- an omitted key would work too, but would require asymmetric `dict.get` handling everywhere for no benefit over a uniformly-present list. Every golden record now has both keys, keeping the schema uniform and `json.dumps(..., sort_keys=True)` stable.

**Hard, not tracked -- this is the one non-obvious design call.** The existing corpus splits fields into HARD (verdict; must never change, ever) and TRACKED (reason/additional_context/provenance/matched_rule; may legitimately reword during a refactor, reported but not exit-1-failing without `--strict-prose`). `sub_matches`/`overrides` are new HARD fields (a new `CompoundBreakdownMismatch` class / `ComparisonResult.breakdown_mismatches`, folded into `has_hard_failures`), not added to the existing TRACKED tier. Reasoning: none of the four captured sub-verdict fields is prose a legitimate refactor has reason to reword -- they are the structural identity of "what happened to this sub-command" -- and the entire point of the extension is to catch structural loss (a dropped, reordered, or garbled entry), which is exactly the failure class of the historical defect. Making this tier TRACKED would have meant plain `--verify` (no `--strict-prose`) would NOT fail on the very regression this extension exists to catch, which would have undermined the "prove it detects a regression" requirement. `toolguard/config_types.py::RuntimeVerdict`'s own top-level `provenance`/`matched_rule` stay TRACKED -- unchanged, for the reasons already documented there (a past bug nulling them needed to be visible without blocking legitimate rewording).

## Regeneration results

`uv run python tools/corpus_build.py --generate` regenerated `goldens.jsonl` (6,401 records). Verified programmatically (scratch script, not committed) that the regeneration is **purely additive**: every pre-existing field is byte-identical for every one of the 6,401 cases; the only diff per record is the two new keys appearing.

Population counts, computed from the regenerated goldens:

| | count |
|---|---|
| Total in-process cases | 6,401 |
| Bash cases (tool == 'Bash') | 5,631 |
| File-path tool cases (Read/Write/Edit) | 770 |
| Cases with non-empty `sub_matches` | 5,631 (100% of Bash cases, 0% of file-path cases -- exactly as the type's own contract promises: `sub_matches` is populated for every Bash resolution, single-leaf or compound, and always empty for file paths) |
| Cases with `len(sub_matches) > 1` (genuine multi-sub-command compounds) | 1,066 |
| Cases with non-empty `overrides` | 33 |

This is not "surprisingly low" -- did not need further investigation. 1,066 genuine compounds (~19% of Bash cases) is consistent with "compound commands are common" in a corpus weighted toward real traffic plus the dedicated `enrichment`/`hierarchy_conflict`/`override_breadth` synthetic fixtures, several of which exist specifically to exercise multi-leaf compounds.

`e2e_goldens.jsonl` (61 cases) is **byte-identical**, unchanged -- see "End-to-end corpus" below for why.

## Regression-detection proof (the part that mattered most)

**Breakage introduced**: a temporary, clearly-marked edit to `toolguard/resolve.py::resolve_bash_permission_detailed`'s inner `_resolve_one` closure -- a call counter that skips appending to `sub_matches` on every second invocation (`if _mutation_call_count[0] % 2 != 0: sub_matches.append(...)`), while leaving the function's actual `(decision, reason, additional_context)` return value untouched. This directly matches one of the two example breakages named in the launching task ("drop every second entry") and mirrors the real historical defect's shape (partial, not total, loss).

**`tools/corpus_build.py --verify` with the mutation in place**:

```
exit code: 1
992 SUB-COMMAND BREAKDOWN MISMATCH(ES) -- STOP AND INVESTIGATE, do not regenerate:
  [empty] Bash('echo a; echo b').sub_matches:
    expected: [{'decision': 'ask', ..., 'sub_command': 'echo a'}, {'decision': 'ask', ..., 'sub_command': 'echo b'}]
    actual  : [{'sub_command': 'echo a', 'decision': 'ask', 'matched_rule': None, 'provenance': None}]
  [empty] Bash('false || true').sub_matches: ... (second entry dropped)
  [empty] Bash('ls -la && pwd').sub_matches: ... (second entry dropped)
  [empty] Bash('ls | grep foo').sub_matches: ... (second entry dropped)
  ... (988 more, one line per affected case, each naming the exact dropped sub-command)

FAIL: hard verdict/output/data-integrity differences found.
```

`uv run python -m unittest test.unit.test_verdict_corpus.TestVerdictCorpus.test_no_sub_command_breakdown_changed -v` with the same mutation: **FAILED (failures=1)**, same 992-case list, same per-case expected/actual detail.

**Revert**: the mutation was removed (git diff of `toolguard/resolve.py` confirmed to contain zero lines related to `_resolve_one`/`sub_matches.append`/the mutation counter after revert -- the file's only remaining diff is pre-existing, unrelated work from a different in-flight session, described below). `--verify` re-run: `OK: no differences.` Full suite re-run: green again (see "Suite status" below).

This demonstrates the extension catches a **partial** structural loss (not just total loss), names every affected case precisely enough to debug from, and does so on a plain `uv run python tools/corpus_build.py --verify` invocation -- no `--strict-prose` flag needed, because the new fields are HARD.

## End-to-end corpus (61 cases): NOT extended, gap documented explicitly

The hook's real JSON response (what `e2e_decision_to_golden` golds) never carries `sub_matches`/`overrides` in any form -- only `permissionDecision`/`permissionDecisionReason`/`additionalContext`. There is nothing in the existing e2e golden shape to widen additively for this. Closing the gap would mean genuinely new instrumentation: snapshotting the main decision-log stream (`toolguard-YYYY-MM-DD.md`) before/after each `run_hook` call, parallel to the existing `conflict`-stream mechanism (`_stream_log_snapshot`/`_new_stream_log_text`), which currently observes only the `conflict` stream.

I decided not to build that. Two reasons: (1) it is new instrumentation, not an additive schema widening -- a materially larger change than the rest of this task, and the launching task explicitly offered "state explicitly why it is not" as a legitimate alternative to doing it; (2) the residual gap it would close is narrower than it first looks -- `_log_allowed_command` now reads `verdict.sub_matches` directly (no more regex reconstruction), so a *future* regression can only happen two ways: (a) `sub_matches` itself becomes wrong at construction time -- now directly guarded by this extension, at the root; or (b) `_log_allowed_command`'s own write loop mishandles an otherwise-correct `sub_matches` (e.g., skips an entry while writing). Only (b) remains unguarded by any corpus. This is a real gap and is documented prominently in `test/verdict_corpus/README.md`'s new "Sub-command breakdown" section (see "What this does NOT guard"), not left implicit.

## Files changed

- `test/verdict_corpus/fixture_loader.py`: `unit_verdict_to_dict`, `override_to_dict` (new helpers); `decision_to_golden` extended (+ docstring rewritten in place, no longer describes the exclusion it now reverses); `CompoundBreakdownMismatch` dataclass; `ComparisonResult.breakdown_mismatches` + `has_hard_failures`/`has_prose_diffs` updated; `BREAKDOWN_FIELDS` constant; `compare_goldens` extended.
- `tools/corpus_build.py`: `_print_comparison` prints breakdown mismatches; module docstring's `--verify` description updated.
- `test/unit/test_verdict_corpus.py`: new `TestVerdictCorpus.test_no_sub_command_breakdown_changed`; module docstring updated to name it alongside the other two HARD-invariant tests.
- `test/verdict_corpus/README.md`: layout section schema updated; two-tier comparison section updated; new "Sub-command breakdown" section (rationale, what's guarded, the explicit e2e gap).
- `test/verdict_corpus/goldens.jsonl`: regenerated (data only; verified purely additive).
- `toolguard/resolve.py`: temporarily mutated for the regression-detection proof, then fully reverted (confirmed via `git diff` showing zero lines touching the mutated region).

No production code changes ship. `toolguard/resolve.py`, `toolguard/config.py`, `toolguard/config_types.py`, `toolguard/permission_resolution.py`, and two `test/unit/` files show as modified in `git status`, but that is **pre-existing, uncommitted work from a different in-flight session** ("resolution seam Protocols" -- present on disk before this task started, confirmed by reading the files at the start of this task and by the diff content itself, e.g. added type hints on `_decide_detailed` closures). Not touched, not reviewed, not part of this change.

## Suite status

- `uv run python -m unittest discover -s test -t .`: **2,587 tests, 2,586 pass, 1 error** -- `test.unit.test_logging_streams.TestDiscoveryDiagnostic.test_oversized_file_no_longer_degrades_to_permanent_append_mode`, failing with `OSError: [Errno 28] No space left on device`. This is an **environment issue, not a regression**: `/tmp` (a 16G tmpfs) is at 100% capacity, consumed almost entirely by `/tmp/toolguard-master-copy/` and `/tmp/toolguard-branch-copy/` (5.4G each, dated 2026-08-06 -- from a different, unrelated prior session), plus roughly a hundred smaller scratch files/dirs from other sessions going back to mid-July. I removed the two small leftover `toolguard-sandbox-*` dirs that were genuinely mine (freed ~0), but did not touch the large unrelated directories -- deleting data outside this task's scope without asking is exactly what the security guidance says not to do. Confirmed this is not caused by my change: `test.unit.test_verdict_corpus` (all 7 tests, including the new one) passes cleanly in isolation, and this session's own baseline run (before any edits) was fully green at 2,586/2,586. **Recommend Arnon either clean `/tmp` or confirm it's safe for me to remove `toolguard-master-copy`/`toolguard-branch-copy` specifically.**
- `uv run python tools/corpus_build.py --verify`: OK, no differences (6,401 in-process + 61 end-to-end).
- `uv run python tools/architecture_fitness.py --layers`: 0 violations, completeness 100%.
- `uv run python tools/architecture_fitness.py --predicates`: 0 violations.
- `uv run ruff format .` / `uv run ruff check .`: clean, whole repo.

## Nothing looked like a pinned bug

Regenerating did not surface any verdict, sub_matches, or overrides change from what the previously-committed goldens already recorded -- the extension is purely additive data, nothing about current behaviour needed re-examination.
