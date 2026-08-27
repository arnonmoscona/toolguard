---
title: Surprise factor - item 15 (migrate cross-process lock)
type: note
permalink: toolguard/too-45/reports/surprise/15-migrate-lock
tags:
- task-memory
- TOO-45
- measurement
---

# Item 15 — `migrate()` serialises itself with an OS file lock

Protocol: [[surprise-factor-protocol]]. Estimate pre-registered in [[15-estimate-predictions]] (sealed until green) and [[15-estimate-uncertainties]] (read before implementing). **Blinding held.** Designated in advance as the series' **control case**: narrow, well-specified, unlikely to have its requirements reversed.

## Actual touch set — 11 files

| group | files |
|---|---|
| production, added | `file_lock.py` |
| production, modified | `permission_migration.py`, `auto_migrate.py`, `scripts/migrate_permissions.py` |
| config | `.pyscn.toml` |
| tests, added | `test_file_lock.py`, `_subprocess_harness.py` |
| tests, modified | `test_migration.py`, `test_auto_migrate.py`, `test_once_per_store.py`, `test_config_divergence.py` |

Verified: 2,706 tests OK across three consecutive runs, `--layers` clean, ruff clean, and the lock's cross-process behaviour confirmed independently — contention declines with a structured reason, a different lock path stays free, and the lock is released after `SIGKILL` of the holder.

## Scoring

`|P| = 13`, `|A| = 11`, **hits = 7**, surprises = 4, overshoots = 6.

| | raw | production only | test only |
|---|---|---|---|
| **recall** | **64%** | **80%** (4/5) | 50% (3/6) |
| precision | 54% | 67% (4/6) | 43% (3/7) |
| surprise ratio `|A|/|P|` | 0.85 | | |

**Leak discount.** The ticket names `permission_migration.migrate()`, `auto_migrate.run_auto_migration` and `toolguard/scripts/migrate_permissions.py`. Excluding those three, honest recall on the 8 unnamed files is **63%** (5/8) — essentially identical to the raw figure, which is the first time the discount has barely moved a result.

### FINDING 1 — the first `C`, and it is exactly the class the measure was built to catch

**`toolguard/auto_migrate.py` was not predicted, and the ticket is the reason.** The ticket asserts, in bold, that this caller is *"**Already safe**: an earlier item made it decline to run at all unless it holds a once-per-day claim."* The estimator believed it — correctly, on the evidence — and predicted only its *test* file, at low confidence.

The assertion was wrong, through a coupling nothing in the ticket or the briefing exposed: **`migrate()`'s integration contract is a bare `int` exit code, and every caller branches on `!= 0`.** Adding a new outcome therefore silently changed the meaning of an existing branch. `auto_migrate` began reporting `"Migration failed"` — with advice to inspect a backup that was never created — for a benign "someone else is migrating right now". And because punch-list #01 deliberately does not release the day's claim on failure, that decline also consumed the day.

**This is `C` — hidden coupling — and it is the first one in four items.** It is worth stating plainly what it cost to find: two independent blind reviewers found it, the full 2,704-test suite did not, and neither did I when I wrote the spec listing *"callers branch on `!= 0`"* as an established fact. I recorded the coupling and still failed to draw the conclusion from it.

The root cause is the one the reviewer named as a suggestion: an `int` exit code is not an outcome type. Deferred to its own ticket, because converting it reaches every caller.

### FINDING 2 — zero `E`, for the first time

| cause | count | files |
|---|---|---|
| **C** — hidden coupling | 1 | `auto_migrate.py` |
| **S** — scope creep (mine) | 3 | `_subprocess_harness.py`, `test_once_per_store.py`, `test_config_divergence.py` |
| **E** — estimator ignorance | **0** | — |
| **P** / **D** / **R** | 0 | — |

**Every miss is either a real coupling or my own scope decision. None is instrument noise.** The three `S` files are one change: the review found the subprocess test harness in its fourth copy, I asked for it to be extracted, and two unrelated test modules were retrofitted onto the shared helper. The ticket did not ask for that.

This is the cleanest result the instrument has produced, and it is the control case, which is what a control case is for. **Abandon gate: does not fire, decisively** — it required three consecutive all-`E` items, and this item has none.

### FINDING 3 — the ratio, four items in

| item | ratio | recall |
|---|---|---|
| 05 | 0.90 | 46% |
| **15** | **0.85** | **64%** |
| 04 | 0.67 | 79% |
| 01 | 0.54 | 60% |

Ranked by ratio: 05, 15, 04, 01. Ranked by recall: 04, 15, 01, 05. The extremes are still inverted — the item with the best ratio has the worst recall, and the item with the best recall has the second-worst ratio. Four items, and `|A|/|P|` has not once agreed with the measure of whether the change surface was actually foreseen. **Recommend dropping it outright rather than continuing to report it "for continuity".**

### The uncertainties half, again

Four of ten questions changed the spec before implementation, and one found a defect in a file the item would otherwise never have opened:

- **`.pyscn.toml`'s layer-order comment was stale** — it read `foundation <- config <- engine <- ...`, omitting `observability`, and therefore contradicted the machine-readable `[[architecture.rules]]` stanzas *in the same file*. Found by an agent explicitly forbidden from reading any code, purely from the discrepancy between the briefing's excerpt and the framing it was given. Fixed here.
- **No shared `~/.toolguard` resolver exists** — five independent derivations. The lock is a sixth; consolidation deferred rather than done as a side effect of a locking ticket.
- **`migrate()` returns a bare `int`** — which drove the named-constant design, and which is also the root of Finding 1.
- **A real concurrent-process test harness already existed** in `test_once_per_store.py`, so the verification did not need inventing.

Its self-flagged blind spot was accurate too: it noted the briefing omits the `toolguard-memories/` tree entirely, so any per-item notes are structurally invisible to it. That is a measurement artefact, not an estimation error, and the scoring excludes them.

## Complexity ratings

- **Blind judge: `low`** — first run of the corrected brief. Reported **9 trivial locations against 2 substantive**; noted the mechanism is one self-contained 167-line module with no toolguard imports, and that the 108-line churn in `permission_migration.py` is almost entirely additive (`git diff -U0` shows the only removed lines are eight docstring lines, so the `migrate` → `_run_migration` extraction moved no code and needed no re-indent).
- **Arnon: `low`.** *"Review was easy for the same reasons as the previous ones. Small scope, focused change helps that too."*

**Judge and owner agree, on the first item under the corrected brief.** Against item 04's maximum disagreement (`high` vs `low`) under the old one. One item is not calibration, but the direction is right and the judge's stated reasoning matched Arnon's: trivial locations dominate, substance is concentrated.

**Arnon added a variable the protocol was not tracking: scope size as a cause, not just a correlate.** *"Small scope, focused change helps that too."* The complexity anchors describe the shape of a change; they say nothing about how much of it there is. Two of the three `low` ratings so far are on deliberately small items, and the series has not yet produced a large one to test whether shape or size is doing the work. Worth separating before drawing any conclusion — a trigger that fires on size would be trivial to build and might explain most of the variance on its own.

**Unprompted, and the point of the exercise:** *"The concurrency subject matter and the permission-tool stakes are pressure toward medium/high that I am deliberately not applying, since neither is reading cost."* That is precisely the failure mode Arnon diagnosed on item 04 — rating the topic's reputation and the stakes rather than the diff.

**It rated `low` and still found Finding 1's defect.** So the corrected brief did not buy calibration by making the judge less attentive. `high` on item 04 was never a proxy for "review this carefully"; it was simply the wrong answer to the question asked.

**Caveat on `n`:** one item, and the one deliberately chosen as the easy control. A `low` here is weak evidence. The brief earns its keep only if it also separates a genuinely expensive change from a cheap one — items #03 and #10 are the real tests.

## Modified co-change `n/(n-1)`

`n = 11`, `n/(n-1) = 1.10`. Series: 05 `1.04`, 01 `1.07`, 04 `1.077`, 15 `1.10`. It is `1 + 1/(n-1)` by construction and has never carried information the file count did not. **Drop it.**
