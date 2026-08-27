---
title: TOO-45 surprise factor - item 15 scored (line-weighted)
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/15-scored
---

# Item 15 scored — commit `caa83e7`

Retro-scored 2026-08-21 under the **line-weighted** rubric adopted at item 18. `15-migrate-lock.md` carries a file-count scoring (recall 64%, precision 54%); this supersedes it. **It is the only one of the four rescored items whose contemporaneous touch set matches the commit exactly** — 11 files, both times.

**Basis**: the commit diff minus two auto-generated agent bookkeeping files (366 lines). That leaves **11 files / 1,422 changed lines**.

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **1,249 / 1,422 = 87.8%** |
| line-weighted recall, wrong-reason discounted | **1,150 / 1,422 = 80.9%** |
| file recall | 7 / 11 = 63.6% |
| precision (integrity guard only) | 7 / 13 = 53.8% |
| leak | **moderate** — 3 files named, and the discount changes nothing |

**Best line-weighted recall of the four rescored items, and the cleanest.** It is also the item where the file-count and line-weighted figures diverge most (64% vs 88%) — every miss is small and every large file was called.

## Per-file — 11 files

| file | lines | predicted? | confidence | note |
|---|---|---|---|---|
| `test/unit/test_migration.py` | 427 | **yes** | high | |
| `test/unit/test_file_lock.py` (new) | 374 | **yes** | high (path: medium) | path called exactly |
| `toolguard/file_lock.py` (new) | 167 | **yes** | high (path: medium) | path called exactly |
| `toolguard/permission_migration.py` | 166 | **yes** | high | **[named]** |
| `test/unit/test_auto_migrate.py` | 99 | **yes** | **low** | **wrong reason** |
| `test/unit/_subprocess_harness.py` (new) | 83 | no — **miss** | — | `S` |
| `test/unit/test_config_divergence.py` | 33 | no — **miss** | — | `S` |
| `test/unit/test_once_per_store.py` | 33 | no — **miss** | — | `S` |
| `toolguard/auto_migrate.py` | 24 | no — **miss** | — | **`C`** |
| `toolguard/scripts/migrate_permissions.py` | 12 | **yes** | medium | **[named]** |
| `.pyscn.toml` | 4 | **yes** | high | |

**False positives (6, cost nothing):** `test/unit/test_architecture.py` (medium), `test/unit/_migration_lock_isolation.py` (add, medium), `test/unit/__init__.py` (medium), `technical-notes.md` (medium), `test/unit/_real_migration_lock_home_guard.py` (add, low), `toolguard/constants.py` (low).

## Cause tally — 4 misses, 173 lines

| cause | files | lines |
|---|---|---|
| `S` — coordinator scope decision | 3 | 149 |
| `C` — hidden coupling | 1 | 24 |
| `E` — estimator ignorance | **0** | **0** |

**Zero `E` on the line-weighted rescoring as well as the file-count one.** Every unpredicted line is either a real coupling the ticket actively denied, or work the coordinator added mid-flight. The abandon gate does not fire, and this remains the series' control case.

## FINDING A — the one `C` is 24 lines, and it swallowed a 99-line hit with it

`toolguard/auto_migrate.py` was not predicted because **the ticket asserted, in bold, that it was already safe**: *"an earlier item made it decline to run at all unless it holds a once-per-day claim."* The estimator believed it on the evidence and predicted only its test file, at **low** confidence, with this stated reason:

> *"the already-safe caller now runs through a lock in tests too; **may need isolation wiring even with no behaviour change**."*

There was a behaviour change, and it was a live defect. `migrate()`'s integration contract is a bare `int` exit code and every caller branches on `!= 0`, so adding a decline outcome silently changed the meaning of an existing branch: `auto_migrate` began reporting `"Migration failed"`, advising inspection of a backup that was never created, for a benign "someone else is migrating right now" — and because item 01 deliberately does not release the day's claim on failure, that decline **consumed the day**.

So `test_auto_migrate.py` is scored a hit and is **right for the wrong reason**: 99 lines predicted as isolation plumbing, changed because the file under test had a real bug. Discounting it takes the headline from 87.8% to **80.9%**, and that is the more honest number for this item.

Worth restating what the `C` cost to find: two independent blind reviewers found it, the full 2,704-test suite did not, and the coordinator's own spec listed *"callers branch on `!= 0`"* as an established fact without drawing the conclusion. **The coupling was written down and the inference was not made** — the same failure recorded at item 22 as coordinator-committed cause `I`.

## FINDING B — the estimator predicted the isolation-helper convention and got the wrong three files

Its six false positives are dominated by one correct instinct applied to the wrong artifacts: it predicted `_migration_lock_isolation.py` (new), `_real_migration_lock_home_guard.py` (new), `test/unit/__init__.py`, and `test/unit/test_architecture.py` — a coherent theory that *a new module writing under `~/.toolguard` gets a shared isolation helper and a real-home guard registered in package setup*.

None of those was created. What **was** created is `_subprocess_harness.py` (83 lines) — a shared test helper, extracted at the coordinator's request when the review found the subprocess harness in its fourth copy, and then retrofitted onto `test_once_per_store.py` and `test_config_divergence.py`.

**The estimator was right that this change would produce a shared test helper and wrong about which problem it would solve.** It predicted a helper for *path isolation* (the convention it could see in the inventory) where the real one is for *process orchestration* (the thing this ticket uniquely needed). Not scored as a hit, but it is the closest a false-positive cluster has come to being one, and it is a better result than precision 54% suggests.

## FINDING C — the two new-module paths were called exactly, at medium path-confidence

`toolguard/file_lock.py` and `test/unit/test_file_lock.py` were predicted by exact path, hedged as *"high (path: medium)"*, and both landed with those names. Together they are 541 lines — **38% of the diff** — from a ticket that names neither.

The estimator's stated grounds were convention (*"a small new leaf module is the obvious home"*, *"new production module gets its own test module by convention"*). At item 85 the same convention argument produced a **false** positive (`test_claude_code_contract.py`, which was correctly not created, because constant-holding leaves in this repo have no test module). **The convention is real and its scope is not what either estimator assumed**: a module with behaviour gets a test file; a module holding only constants or types does not. `file_lock.py` has behaviour, so the inference held here and failed there — and neither estimator stated the distinguishing condition.

That is a concrete, cheap correction for the briefing: **state the test-file convention with its actual boundary**, rather than leaving each estimator to infer a universal from an inventory that cannot show absence.

## Leak

**Moderate, and it is the series' one item where the discount is inert.** The ticket names `permission_migration.migrate()`, `auto_migrate.run_auto_migration` and `toolguard/scripts/migrate_permissions.py` — 202 of 1,422 lines, one of which (`auto_migrate.py`) was named and still missed.

- recall on the 8 unnamed files: **1,071 / 1,220 = 87.8%**

Identical to the raw figure to one decimal place. The file-count scoring found the same thing (63% unnamed vs 64% raw) and called it *"the first time the discount has barely moved a result"*; the line-weighted rescoring confirms it rather than being an artifact of small counts.

**This is the strongest single data point against finding 21's leak-explains-recall curve.** Item 15 has the highest line-weighted recall of the four rescored items and the least helpful ticket of the four. What it had instead was a **narrow, self-contained mechanism** — a lock, a wrapper, a caller — which is exactly the property finding 14 predicts should correlate with low cost. It did: this item ran clean.
