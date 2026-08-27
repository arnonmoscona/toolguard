---
title: TOO-45 surprise factor - item 04 scored (line-weighted)
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/04-scored
---

# Item 04 scored — commit `ee9aa94`

Retro-scored 2026-08-21 under the **line-weighted** rubric adopted at item 18. A file-count scoring already existed in `04-error-reporter.md` (recall 79%, precision 52%); this supersedes it and **corrects its touch set** — see "Reconciliation".

**Basis**: the commit diff minus two auto-generated agent bookkeeping files (`toolguard-memories/implementation/Coder Latest Task Recall.md`, `toolguard-memories/latest-code-review-report.md`, 513 lines). That leaves **18 files / 2,222 changed lines**.

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **1,703 / 2,222 = 76.6%** |
| line-weighted recall if `hook.py` is discounted as wrong-reason | **1,277 / 2,222 = 57.5%** (see finding B — the honest figure is a range) |
| file recall | 12 / 18 = 66.7% |
| precision (integrity guard only) | 12 / 21 = 57.1% |
| leak | **heavy** — 4 files named by path with per-file counts, a 5th mentioned, and the new module promised |

**Best line-weighted recall of the four items rescored in this batch, and the ticket did most of the work.**

## Per-file — 18 files

| file | lines | predicted? | confidence | note |
|---|---|---|---|---|
| `toolguard/hook.py` | 426 | **yes** | medium | **[mentioned]** — reason explicitly excluded what dominated it |
| `test/unit/test_error_reporter.py` (new) | 439 | **yes** | high | |
| `test/unit/test_auto_migrate.py` | 254 | **yes** | high | |
| `test/unit/test_hook_error_reporter.py` (new) | 243 | no — **miss** | — | `E` |
| `toolguard/error_reporter.py` (new) | 222 | **yes** | high | ticket promises the module |
| `test/unit/test_hook.py` | 168 | **yes** | medium | |
| `test/unit/_real_once_per_home_guard.py` (new) | 131 | no — **miss** | — | `E` |
| `test/unit/test_env_config.py` | 76 | **yes** | medium | |
| `test/unit/test_configuration.py` | 58 | no — **miss** | — | `E` (naming trap) |
| `CLAUDE.md` | 53 | no — **miss** | — | `S` |
| `test/unit/test_config_divergence.py` | 46 | **yes** | high | |
| `toolguard/auto_migrate.py` | 25 | **yes** | high | **[named]** |
| `toolguard/log_writer.py` | 21 | no — **miss** | — | `E` |
| `.pyscn.toml` | 20 | **yes** | high | |
| `toolguard/env_config.py` | 13 | **yes** | high | **[named]** |
| `test/unit/test_hook_eval.py` | 13 | no — **miss** | — | **`D`** |
| `toolguard/config.py` | 7 | **yes** | high | **[named]** |
| `toolguard/config_divergence.py` | 7 | **yes** | high | **[named]** |

**False positives (9, cost nothing):** `session_warnings.py`, `test_session_warnings.py`, `error_log.py`, `tools/architecture_fitness.py`, `test_architecture_fitness.py`, `test_architecture.py`, `test_config.py`, `docs/architecture.md`, `technical-notes.md`.

Most of those nine are **`X` (descoped)**, not estimator error — the ticket invited a `session_warnings` reclassification and a stderr-ban fitness predicate, and the coordinator cut both, taking four files with them (`session_warnings.py`, `test_session_warnings.py`, `tools/architecture_fitness.py`, `test_architecture_fitness.py`) plus the two doc files. The commit message confirms the second is still open: *"nothing prevents a new hand-rolled stderr write from appearing. A fitness predicate is the durable answer; prose has not been."*

`04-error-reporter.md` counts this descoped group as **5**, listing 6 files; the ambiguity is in the original and is not resolved here. Precision excluding descoped predictions is therefore **12/16 = 75%** or **12/15 = 80%** depending on that count.

## Cause tally — 6 misses, 519 lines

| cause | files | lines |
|---|---|---|
| `E` — estimator ignorance | 4 | 453 |
| `S` — coordinator scope creep | 1 | 53 |
| `D` — latent defect found by the work | 1 | 13 |

## FINDING A — the series' first `D`, and it is 13 lines

`test/unit/test_hook_eval.py` changed because `--eval` mode printed its deny verdict to **stderr with an empty stdout**, and the security-audit skill reads `permissionDecision` from stdout only. The existing test asserted the stderr behaviour, so **the test was pinning the bug**. From the commit message: *"the contract was fiction and the pinned test was pinning the bug."*

Cause `D`. Nothing in the ticket or the briefing exposed it; it surfaced only because the item forced someone to ask where an error report actually goes. It is also the campaign's signature failure mode — *a mechanism that fails open and says nothing* — found here in a **second** location beyond the one the ticket described.

This matters for the abandon gate. `04-error-reporter.md` recorded this item as **3 misses, all `E`, zero alarms**. Scored from the commit rather than from a mid-flight `git status`, it is 6 misses with a `D` in it. **The instrument reported "no alarms" on an item that contained one.**

## FINDING B — the biggest hit in the item is a hit whose reason was explicitly ruled out

`hook.py` is 426 lines, 19% of the diff, and the estimator's stated reason for predicting it is:

> *"The catch-all handler is a fault-and-a-decision; classifying it is in scope **even though the fail-open fix is not**."*

The fail-open fix is what the commit is largely about. The commit message gives it a heading — **FAIL-OPEN FIXED** — and it accounts for the three rewritten error handlers, the stdout/stderr split, the exit-2 last resort, and the buffered-stdout discovery. The classification work the estimator *did* predict is real and present, but it is the smaller half.

So this is **the file-granular scoring limitation of finding 19, at maximum leverage**: the metric scores 426 lines as foresight for a file the estimator named while writing down that it expected the opposite change. There is no honest way to split the 426 lines, so the result is a range:

- credit `hook.py` in full: **76.6%**
- discount it in full: **57.5%**

The true value is inside that interval and closer to the top of it. **Report the range; do not pick.**

## FINDING C — `E` here means "right mechanism, wrong module", three times out of four

None of the four `E` misses is a blind spot. Each is a one-hop naming error:

| miss | what the estimator predicted instead |
|---|---|
| `log_writer.py` (21) | `error_log.py`, for exactly this mechanism — *"the reporter routes to the warning/error log; likely needs a callable seam"*. `_resolve_log_dir` → `resolve_log_dir` is that seam, in the other of the two modules |
| `test_hook_error_reporter.py` (243) | growing `test_hook.py`; a new file was written rather than adding to a 3,146-line module (and `test_hook.py` grew anyway, so both) |
| `test_configuration.py` (58) | `test_config.py`. Both files exist; `config.py`'s tests live in the 3,982-line one |
| `_real_once_per_home_guard.py` (131) | nothing — but its concentration set names *"the throttle store is the thing that broke"*, so it knew the store existed and did not know it is `~`-anchored with no directory argument, which is what forces a structural test guard |

**Four independent instances of the same failure: the estimator has the mechanism and picks the wrong file for it.** Three of the four could be fixed by giving the estimator a file inventory that pairs each production module with the test module that actually exercises it — which is a cheap, checkable briefing change, and unlike the ambient-call-sites proposal from item 44 it does not hand over any part of the answer.

## FINDING D — the ticket's headline number was wrong, and the estimator transcribed it

The ticket claimed **16 hand-rolled stderr writes across four modules**, broken down per file. There were **8**, AST-counted: item 01 had removed the rest as a side effect. The estimator's high-confidence rows quote the ticket's per-file counts verbatim (*"Named in the ticket: 6 of the 16 stderr writes"*).

The predictions survived — all four files did change — so this cost no recall. But it is cause `I` (inherited staleness) sitting harmlessly inside four hits, and it is the same shape as item 10, whose ticket also miscounted in the same direction. **Two consecutive tickets whose evidence did not survive measurement, both undercounting the true spread while overstating the headline.**

## Reconciliation with the contemporaneous scoring

`04-error-reporter.md` records `|A| = 14`. The commit contains **18** scored files. Four are missing from that list: `test/unit/test_hook.py` (a hit, 168 lines), `CLAUDE.md`, `test/unit/_real_once_per_home_guard.py`, and `test/unit/test_hook_eval.py`. Same mechanism as item 03 — the list was taken from a working tree before the commit closed. It cost one uncounted hit and, more seriously, **one uncounted `D`**.

## Leak

**Heavy.** The ticket names `config.py`, `env_config.py`, `auto_migrate.py`, `config_divergence.py` by path with per-file write counts, and mentions `hook.py`. Those five are 478 of 2,222 lines.

- recall on the 13 unnamed files: **1,225 / 1,744 = 70.2%**
- also excluding the promised new module and its test (`error_reporter.py` + `test_error_reporter.py`, 661 lines — the ticket does not name the path but does promise the module, so predicting it is transcription): **564 / 1,083 = 52.1%**

The second figure is the one to compare across items.
