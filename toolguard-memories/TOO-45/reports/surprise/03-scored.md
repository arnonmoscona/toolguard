---
title: TOO-45 surprise factor - item 03 scored (line-weighted)
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/03-scored
---

# Item 03 scored — commit `19299d9`

Retro-scored 2026-08-21 under the **line-weighted** rubric the series adopted at item 18. A file-count scoring already existed inside `03-resolution-cycle.md` (recall 36%, precision 67%); this supersedes it and **corrects it** — see "Reconciliation" below.

**Basis**: the commit diff minus three auto-generated agent bookkeeping files (`toolguard-memories/implementation/Coder Latest Implementation Report.md`, `.../Coder Latest Task Recall.md`, `toolguard-memories/latest-code-review-report.md`, 1,038 lines between them). That leaves **23 files / 1,540 changed lines** (insertions + deletions).

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **991 / 1,540 = 64.4%** |
| line-weighted recall, wrong-reason discounted | **974 / 1,540 = 63.2%** |
| file recall | 9 / 23 = 39.1% |
| precision (integrity guard only) | 9 / 12 = 75% |
| leak | **moderate** — the ticket names 3 files, no line numbers |

**The gap between 64% by lines and 39% by files is the whole story of this item**: the estimator got the three big production modules and missed a long tail of small, prose-driven touches.

## Per-file — 23 files

| file | lines | predicted? | confidence | note |
|---|---|---|---|---|
| `toolguard/resolve.py` | 384 | **yes** | high | **[named in ticket]** |
| `toolguard/permission_resolution.py` | 305 | **yes** | high | **[named in ticket]** |
| `toolguard/file_matching.py` (new) | 278 | no — **miss** | — | `R` |
| `toolguard/config_types.py` | 227 | **yes** | med-high | **[named in ticket]** |
| `test/unit/test_configuration.py` | 95 | no — **miss** | — | `E` |
| `test/unit/test_logging_streams.py` | 49 | no — **miss** | — | `E` |
| `test/unit/test_hierarchical.py` | 45 | no — **miss** | — | `E` |
| `test/unit/test_permission_resolution.py` | 39 | **yes** | high | |
| `test/unit/test_takeover_mode.py` | 26 | no — **miss** | — | `E` |
| `test/unit/test_hard_deny.py` | 16 | no — **miss** | — | `E` |
| `test/unit/test_architecture.py` | 15 | **yes** | medium | reason partly wrong (below) |
| `technical-notes.md` | 13 | **yes** | medium | **wrong reason** |
| `test/unit/test_hook.py` | 12 | no — **miss** | — | `E` |
| `toolguard/compound.py` | 6 | no — **miss** | — | `P` |
| `toolguard/config.py` | 6 | no — **miss** | — | `P` |
| `toolguard/permissions.py` | 6 | no — **miss** | — | `P` |
| `test/unit/test_resolve.py` | 4 | **yes** | low-med | |
| `toolguard/hook.py` | 4 | no — **miss** | — | `P` |
| `.pyscn.toml` | 2 | no — **miss** | — | `R` |
| `docs/architecture.md` | 2 | **yes** | low-med | **wrong reason** |
| `toolguard/session_start.py` | 2 | no — **miss** | — | `P` |
| `tools/architecture_fitness.py` | 2 | **yes** | med-low | **wrong reason** |
| `test/unit/test_hook_eval.py` | 2 | no — **miss** | — | `P` |

**False positives (3, cost nothing):** `test/unit/test_permission_resolution_seam.py` (add, medium), `test/unit/test_compound.py` (low), `test/unit/test_architecture_fitness.py` (low).

## Cause tally — 14 misses, 549 lines

| cause | files | lines | what |
|---|---|---|---|
| `E` — estimator ignorance | 6 | 233 | six test modules that call the injected seam directly |
| `P` — prose coupling | 6 | 26 | docstring cross-references made stale by the rename |
| `R` — requirement added after the estimate | 2 | 280 | the `file_matching.py` extraction and its layer entry |

(`R` is not in the standard code list; it is carried over from the contemporaneous item write-ups, which all use it.)

## FINDING A — the estimator named the mechanism of every `E` miss and predicted none of the files

Its uncertainty **U10** asks, verbatim: *"do tests, the sandbox, the replay tooling, or the public decision interface substitute their own implementation of the injected callable? ... if test doubles rely on the injection point, removing it deletes their seam and the test rewrite dominates the work."*

That is exactly what happened. `test_hierarchical.py`, `test_logging_streams.py`, `test_hard_deny.py`, `test_takeover_mode.py` and `test_hook.py` each built their own `_detailed_decider` closure over `decide_command_at_level_detailed` and passed it in; all five had to be rewritten to call `resolve_command_permission(config, "Bash", command)` directly. **233 lines, 15% of the diff, mechanism correctly named and zero files predicted.**

This is a fourth data point for the protocol change already proposed at finding 13 of `RESULTS-LOG.md`: **when the uncertainties file flags a mechanism that would move a large share of the touch set, the flag should be scored as an estimate.** Here it would have converted the single largest cause bucket.

Its own warning #3 in the same document — *"a test file's name does not predict what it tests here ... anyone scoping 'the tests for this change' from filenames will scope it wrong in both directions"* — is the same finding stated in advance. It named the trap and then fell in it, because the prediction half is a list of filenames and the filenames were exactly what it had just declared unreliable.

## FINDING B — six files changed for docstring cross-references, and nothing else

`compound.py`, `config.py`, `permissions.py`, `hook.py`, `session_start.py` and `test_hook_eval.py` (26 lines total) were touched **only** to repoint `:func:` references from `resolve_permission_detailed` to `resolve_command_permission` / `resolve_permission_cascade`. `technical-notes.md` (13 lines) is the same repair at doc scale — six stale symbol references, found in review, not the design write-up the estimator predicted.

The estimator explicitly and deliberately declined to predict four of these five production files: *"all of these should be invariant if the refactor genuinely preserves what a decision is; predicting them would be hedging, and hedging is what precision scoring punishes."* **The reasoning was correct about behaviour and wrong about prose.** A rename does not change what a decision is, and it still touched every file that talks about it.

**The lesson is about the scoring rubric, not the estimator.** Precision scoring taught it to suppress exactly the cheap, near-certain, low-line-count predictions that a rename guarantees. Line-weighting is the right corrective: these six misses cost 1.7% of the headline, which is roughly what they are worth.

## FINDING C — three hits for the wrong reason, all at the small end

The estimator records a reason per row, so this is checkable:

| file | predicted reason | what actually happened |
|---|---|---|
| `tools/architecture_fitness.py` | *"if it carries a known-runtime-cycle registry ... the pair drops out of it"* | one docstring line renaming a moved function. The commit message says outright **"No fitness predicate was added."** |
| `technical-notes.md` | *"the sibling cycle removal is the kind of thing that got written up there"* | six stale symbol references repaired; no write-up |
| `docs/architecture.md` | *"a dependency graph a reader can trust ... this is the doc that would assert it"* | two lines adding `file_matching.py` to a directory listing — a consequence of the extraction it did **not** predict |

Discounting all three moves the headline from 64.4% to **63.2%**. Small, but the direction matters: all three are files where the estimator reasoned about *architecture machinery* and the real cause was *text*.

**Ambiguous, not discounted:** `test/unit/test_architecture.py` was predicted on the theory that a known-cycle exception would be recorded there and need inverting. No such exception existed; what actually changed is `permission_resolution`'s allowed-import frozenset, widened to admit `permissions` and `file_matching`. Same file, same class of artifact (a declared architectural invariant that a structural change forces you to edit), different assertion. Scored as a hit; flagged rather than resolved generously.

## FINDING D — the largest single miss is a stage the ticket never contained

`file_matching.py` (278 lines) plus its `.pyscn.toml` layer entry (2 lines) — **18% of the diff** — exist because the design phase decided to extract the file-path matching cluster out of `resolve.py` first, byte for byte. Cause `R`: no estimate made from the ticket could have contained it.

Worth noting against it: the estimator's uncertainties file **did** name a third design shape the ticket did not offer — *"decompose into a pure per-level matcher plus a pure decision fold, with a thin driver above both ... it costs one more module"* — and the implementation did take a decomposition that costs one more module. That is not the same decomposition (the fold landed inside `permission_resolution`, and the extracted module is the file-path cluster), so it is not a hit. It is a second instance of the finding-A pattern: **the shape was anticipated in prose and absent from the file list.**

## Reconciliation with the contemporaneous scoring

`03-resolution-cycle.md` records `|A| = 22`, hits = 8. The actual commit contains **23** scored files: it omits `technical-notes.md`, which was both changed and predicted. So the original numbers understate hits by one. Corrected file recall is 9/23 = 39%, against the 36% recorded then.

The likely mechanism — and it applies to items 04 and 10 as well — is that the touch-set lists were assembled from a `git status` taken before the commit was finalised, then never re-derived from the commit. **Score from the commit, not from a working tree.**

## Leak

**Moderate.** The ticket names `permission_resolution.py`, `resolve.py` and `config_types.py` — the three largest files in the diff, 916 of 1,540 lines (59.5%). **Recall on the 20 unnamed files is 75 / 624 = 12.0% by lines.**

That is the sharpest leak split in the series so far, and it belongs in the leak table with items 79/18/20/22: transcribing three named modules bought 59.5 points of the 64.4-point headline, and everything the estimator worked out for itself bought 4.9.
