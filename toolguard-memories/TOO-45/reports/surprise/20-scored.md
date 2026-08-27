---
title: TOO-45 surprise factor - ticket 20 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/20-scored
---

# Ticket 20 scored — union of 20a (`bf87629`) and 20b (`44845c8`)

Basis locked in `20-prereg.md` **before** the estimate existed. 20c descoped -> cause `X`, not counted as a miss. Diffstat total **966 changed lines across 8 files**.

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **918 / 966 = 95.0%** |
| file recall | 6 / 8 = 75% |
| precision (integrity guard only) | 6 / 11 = 55% |
| scope prediction | **void** — the ticket carried the answer (see prereg) |
| diagnosis prediction | **void** — same reason |

**Highest line-weighted recall in the series.** For contrast, ticket 79 scored **15.2%**, the lowest.

## Per-file

| file | lines | predicted? | confidence | note |
|---|---|---|---|---|
| `test/unit/test_tools_consolidate.py` | 403 | **yes** | high | hit |
| `toolguard/tools/consolidate.py` | 250 | **yes** | high | hit |
| `test/unit/test_tools_maintenance.py` | 180 | **yes** | medium | hit |
| `test/unit/test_tools_rule_apply.py` | 47 | **yes** | low | **right file, WRONG reason** |
| `test/unit/test_tools_edit_proposal.py` | 36 | no | — | `C` |
| `toolguard/tools/maintenance.py` | 30 | **yes** | high | hit, right reason |
| `toolguard/tools/edit_proposal.py` | 12 | no | — | `C` |
| `toolguard/tools/rule_apply.py` | 8 | **yes** | low | **right file, WRONG reason** |

False positives (5, cost nothing): `permissions.py`, `pattern_overlap.py`, `rule_sort.py`, `test_rule_sort.py`, `test_pattern_overlap.py`.

## FINDING 19 — a hit for the wrong reason is not a hit, and this measure cannot tell

`rule_apply.py` and `test_tools_rule_apply.py` (**55 lines**) were predicted at low confidence **because of RA1**, the dry-run normalisation finding. **RA1 was descoped.** Those files were touched for an unrelated reason — rendering the new `verification` state.

**The file-set metric scores this as two hits.** Discounting them: **863 / 966 = 89.3%**, still the series' best.

**Report both figures in the aggregate.** A predictor naming plausible neighbouring files will accumulate coincidental hits, and line-weighted recall alone cannot distinguish foresight from adjacency. This is the first measured instance, and it is only visible because the estimator wrote its *reason* per row — the strongest argument yet for keeping that column.

## FINDING 20 — the miss came from work the TICKET NEVER DESCRIBED

Both misses (`edit_proposal.py` + its test, **48 lines, 5%**) exist because the **review** found the fix incomplete: the three-state was computed and then discarded at the call site, so it never reached the operator. Carrying it through required `EditProposal`.

**No estimator could have predicted this.** The ticket's scope was the gate; the requirement that the *result* reach the user emerged from reviewing the fix. Cause `C` (hidden coupling), but with a trigger worth distinguishing: **the touch set grew because a review raised the bar, not because the code was more entangled than it looked.**

Worth asking at the aggregate: how much of every ticket's unpredicted diff is *review-driven* rather than *code-driven*? Those are different facts about the codebase, and the current cause codes conflate them.

## FINDING 21 — leak level predicts recall, and this is the high-end confirmation

Ticket 18 gave the low-end evidence: hits only where the ticket named files **with line numbers**, unleaked downstream 0/7. Ticket 79 gave the middle: the ticket named only the extractor, and recall was **15.2%**.

**Ticket 20 names nearly every file it touches** — `consolidate.py` by function, `maintenance.py` as *"the compounding factor"*, `test_path_boundary_prefix_subsumes` by name — and recall is **95.0%**.

Three points, monotone in leak level. **The measure is tracking transcription quality far more than foresight**, and the aggregate must lead with leak-discounted recall rather than report it beside the headline.

## What the estimator got genuinely right

`maintenance.py` at **high** confidence with the correct reason — the corpus-threading call site — and it correctly predicted **no new test files**, reasoning that the campaign's own earlier amendment had added methods to existing files rather than creating one. That inference is the same *kind* the ticket-80 estimator made (predicting a new file from an absent test module), applied in the opposite direction and right again.

## Cause tally

`C` x2 (48 lines, review-driven), `X` x1 (20c descoped, excluded by pre-registration). No `E`, no `I`, no `P` — **the first item in the series with no documentation-file miss**, because both chunks were code-and-test only.
