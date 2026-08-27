---
title: Surprise factor - item 01 (consolidate the suppression mechanisms)
type: note
permalink: toolguard/too-45/reports/surprise/01-suppression-store
tags:
- task-memory
- TOO-45
- measurement
---

# Item 01 — consolidate the four warning-suppression mechanisms

Protocol: [[surprise-factor-protocol]]. Estimate pre-registered in [[01-estimate]], written to file and returned as a bare token — **blinding held on both sides this time**, and I did not open it until the implementation was green.

## Actual touch set — 15 files

| group | files |
|---|---|
| production, added | `suppression.py` |
| production, modified | `session_warnings.py`, `auto_migrate.py`, `config_divergence.py`, `hook.py` |
| config | `.pyscn.toml` |
| docs | `technical-notes.md` |
| tests, added | `test_suppression.py` |
| tests, modified | `test_session_warnings.py`, `test_auto_migrate.py`, `test_config_divergence.py`, `test_hook.py`, `test_logging_streams.py`, `_real_log_dir_guard.py`, `test_zz_real_log_dir_guard.py` |

Verified: 2,592 tests OK, golden corpus unchanged, `--layers` clean, ruff clean. **Net −718 lines** (483 inserted, 1,201 deleted).

## Scoring

`|P| = 28`, `|A| = 15`, **hits = 10**.

| | value |
|---|---|
| **recall** (`hits/|A|`) | **67%** |
| precision (`hits/|P|`) | 36% |
| Jaccard | 30% |
| surprise ratio `|A|/|P|` | **0.54** |

### FINDING 1 — the ratio has now been wrong in BOTH directions, on consecutive items

| item | ratio | recall | what the ratio said | what was true |
|---|---|---|---|---|
| 05 | **0.90** | 46% | near-perfect prediction | fewer than half the files foreseen |
| 01 | **0.54** | **67%** | large under-prediction | the best recall of the series so far |

On 05 the ratio flattered; on 01 it penalises. **The better-predicted item scored the worse ratio.** Two data points, opposite directions, and the ranking is inverted between the two measures — that is as clean a refutation as this instrument is going to produce. The ratio is not a weak signal, it is an actively misleading one, because a cautious estimator that over-lists is punished and a lucky one that names few files is rewarded.

**Recommendation, now on evidence rather than argument: drop `|A|/|P|` and report recall as the headline with precision alongside.**

### FINDING 2 — the estimator predicted 5 of its own 5 misses, by mechanism

This is the real result of item 01.

| surprise | what section 4 said, before implementation |
|---|---|
| `auto_migrate.py` | *"The single most likely surprise in this ticket is that one of the 'three copies' is in a module whose docstring gives no hint of warning behaviour."* `auto_migrate.py`'s docstring is about migration. |
| `test_auto_migrate.py` | consequence of the above |
| `_real_log_dir_guard.py` | *"Expect either an isolation edit or a new guard file"* — right reason, predicted the sibling file `_config_isolation.py` instead |
| `test_zz_real_log_dir_guard.py` | same |
| `test_logging_streams.py` | *"behaviour is tested where the feature lives (`test_takeover_mode.py`, `test_logging_streams.py`), not where the module lives"* — it named this exact file in its uncertainties while omitting it from its predictions |

**Five for five.** Every miss was described in advance, by mechanism, by the thing that missed it.

It also handed over the search that would have closed the largest gap: *"the mechanism that would settle it in ten seconds is a grep for `strftime("%Y-%m-%d")` or `-warned-` across `toolguard/`."* That grep finds all three copies immediately.

**Section 4 is worth more than section 1.** The prediction table is the thing being scored; the uncertainty list is the thing worth acting on.

### PROTOCOL CHANGE — split the estimate into a sealed half and an open half

On item 05 I resolved four of eight uncertainties before implementing, and it made the work better. On item 01 I could not, because sealing the estimate sealed the checklist with it — and the checklist turned out to be the valuable part.

**From item 04: the estimator writes two files.**

- `NN-estimate-predictions.md` — sections 1-3. **Sealed** until the implementation is green. This is what gets scored.
- `NN-estimate-uncertainties.md` — section 4. **Read before implementing, and treated as a to-do list.**

Section 4 names mechanisms and searches, not files, so reading it does not leak the touch set. This keeps the measurement honest and stops throwing away its most useful output.

### Cause assignment

| cause | count |
|---|---|
| **E** — estimator ignorance | 5 |
| **P** — prose coupling | 0 |
| **C** — hidden coupling | 0 |
| **D** — latent defect | 0 (see below — the category has a blind spot) |
| **S** — scope creep | 0 |

Zero prose coupling, against 8 on item 05. The difference is that item 05 *deleted a named module*, so every docstring citing it went stale at once. Nothing was renamed here, so nothing went stale. That is a useful contrast: prose coupling is triggered by rename and delete, not by change.

**Abandon-gate status: two items, all surprises classed `E`.** The gate says three consecutive all-`E` items means the briefing is too thin to support the measure. Item 04 decides it. My reading is that the gate should NOT fire, because Finding 2 shows the instrument producing real value through section 4 — but the rule was pre-registered and I am not going to quietly reinterpret it. If 04 is all-`E` too, the *prediction* half is what should be dropped, keeping the uncertainty half.

## A latent defect the measure cannot see

**The takeover-mode "once per day" suppression never suppressed the warning.** The pre-change code:

```python
if to_stdout:
    print(warning_message, file=sys.stderr)   # unconditional, every invocation
if marker_exists_for_today(logs_dir):
    return
create_marker_file(logs_dir)                   # the marker gates only itself
```

The marker gated marker creation and cleanup — nothing else. One of the four "mechanisms" was **suppressing only its own housekeeping.** The docstring was honest about it (*"The stderr echo always fires"*); the module name and the ticket's framing were not.

My implementation spec asserted "a takeover warning still appears at most once per day per project" as an invariant to preserve. **That was wrong**, and the implementer correctly kept the real, tested behaviour instead of changing it to match my spec. Preserved and now documented explicitly.

**This is a `D` that produced no file surprise**, because the defect lived inside a file the change was always going to touch. A touch-set measure is structurally blind to it. Worth knowing about the instrument: it detects surprises in *where* work lands, never in *what was found once you got there*.

## RESCORED after five passes — and the headline changed

The numbers above were taken after pass 1. The item went through **five implementation passes and four adversarial reviews**, ending at **20 files** and 2,635 tests.

`|P| = 28`, `|A| = 20`, **hits = 12**. **Recall 60%**, precision 43%.

Recall fell from 67% to 60% as the item grew — but the interesting part is *which* predictions changed status.

### THE FINDING: the blind estimator got the design right and I overrode it

Its very first prediction row proposed the new store as *"stdlib-only (`sqlite3` or a single keyed file under `~/.toolguard/`)"*.

**It assumed `~/.toolguard` from the start.** I specified per-project storage instead, reasoning that a global store would let one project silence another. Arnon reversed that on architectural grounds — the store is toolguard's own state, not project data — and the code moved to exactly where the estimator had put it.

Two consequences the score can see:

- `docs/uninstall.md` and `toolguard/tools/self_integrity.py` were scored as **overshoots** at pass 1 and became **hits** by pass 3. They were only ever wrong because *my* design was wrong. The estimator predicted them for the correct reason: a new persistent file under `~/.toolguard` is a new thing to uninstall and a new thing the self-integrity guard covers.
- Its stated uncertainty — *"a store under `$HOME` almost always acquires an env override for tests/sandboxing"* and *"expect either an isolation edit or a new guard file; a new guard file would be entirely unpredicted from the ticket text"* — described `_real_suppression_home_guard.py`, which is exactly what got written.

**An agent that saw only filenames, line counts and one docstring line each made a better storage-location call than I did with the whole codebase.** Recorded plainly because it is the strongest evidence in this series that the exercise has value beyond its score, and because the score itself would have hidden it: at pass 1 those two rows counted *against* the estimator.

### Cause assignment, final

| cause | count | notes |
|---|---|---|
| **E** — estimator ignorance | 5 | unchanged from pass 1 |
| **R** — requirement reversal | 3 | `test/unit/__init__.py`, `installer.py`, `_real_suppression_home_guard.py` — all consequences of moving the store mid-flight |
| **P** — prose coupling | 0 | |
| **C** / **D** / **S** | 0 | |

**New category `R` — requirement reversal.** Files touched only because the requirement changed after implementation began. Not an estimator failure and not an architecture failure; it is the cost of deciding late. It needs its own name because it is the dominant cause on any item whose spec moves, and pooling it with `E` would make the instrument look worse than it is while hiding the real driver.

**The honest caveat on this item's numbers: #01 measured a moving target.** Two of the five passes were driven by requirement changes (store location, per-feature degraded-mode warnings) and two by defects found in review. A touch-set prediction made against the original ticket cannot score well against that, and it would be misleading to read 60% as an estimator failure.

**Abandon gate: does not fire.** Three items were the trigger, and #01's surprises are no longer all `E`.

## What five passes actually cost, and what they bought

Bought: **two defects that would have silently disabled governance entirely** (a module-level `Path.home()` making the hook unimportable; a `ValueError` escaping into a handler that writes its deny to stderr and exits 0), plus a claim leak that silenced warnings for a day, plus directories created inside user repositories, plus a schema self-heal that destroyed a newer build's store.

Cost: five implementation passes and four reviews on a ticket scoped as "consolidate four copies of one idea", and **I declared the item green twice before it was**.

The reviews were right every time. The estimate that was wrong every time was mine.

## Complexity ratings

- **Blind judge**: recorded separately when it returns.
- **Arnon**: pending review.

## Modified co-change `n/(n-1)`

`n = 15`, `n/(n-1) = 1.07`. Item 05 was 1.04 on `n = 26`. The measure moves *opposite* to size — the smaller change scores higher — which is arithmetic, not signal. Two items in, it carries nothing the file count does not already say. Flagging early rather than at the end of the series.
