---
title: TOO-45 surprise factor - ticket 18 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/18-scored
---

# Ticket 18 scored (a colon is only a wildcard at the end of a pattern)

Actual from `git diff --numstat 8867367..c5e50a5`. Scored under Arnon's redefined metric: **line-weighted recall against the final committed diff** is the headline.

## Actual — 7 files, 552 changed lines

| file | +/- | lines | predicted? | confidence |
|---|---|---|---|---|
| `test/unit/test_pattern_overlap.py` (**NEW**) | 205/0 | 205 | **no — surprise** | — |
| `test/unit/test_permissions.py` | 195/0 | 195 | yes | high |
| `toolguard/permissions.py` | 31/30 | 61 | yes | high |
| `toolguard/tools/pattern_overlap.py` | 15/14 | 29 | yes | low-medium |
| `test/unit/test_hard_deny.py` | 26/0 | 26 | **no — surprise** | — |
| `docs/native-pattern-reference.md` | 16/3 | 19 | **no — surprise** | — |
| `toolguard/tools/consolidate.py` | 11/6 | 17 | **no — surprise** | — |

**Line-weighted recall: 285 / 552 = 52%.** File recall: 3/7 = 43%.

Unlike ticket 78 (where line-weighting cut apparent surprise six-fold), weighting barely helps here — because the largest single surprise is also the largest single file.

## THE DOWNSTREAM PREDICTION SCORED SEPARATELY — and this is the result

The pre-registration required the downstream tier be scored apart from the defect site, calling it *"the part of this estimate that actually matters."*

The estimator predicted **seven** downstream files: `test_patterns.py`, `test_tools_consolidate.py`, `test_tools_maintenance.py`, `test_api.py`, `test_tools_redundancy.py`, `test_tools_edit_proposal.py`, `test_verdict_corpus.py`.

**Zero were touched. The actual downstream set is empty.**

**But this is not estimator failure, and scoring it as such would be wrong.** The ticket's stated blast radius — *"the fix breaks 20 tests, none in test_permissions.py or test_patterns.py"* — was measured against the **headline defect that `05f786d` had already fixed**. The estimator faithfully reproduced a stale ticket claim, exactly as instructed. So did the coordinator, who briefed the implementer to expect ~20 failures that could not occur.

**New cause needed: `I` (inherited staleness)** — the estimate was wrong because its *input* was wrong. Distinct from `E` (estimator ignorance), `A` (a seam absorbed it) and `X` (descoped): nobody was ignorant, nothing was absorbed, nothing was descoped. The ticket described a tree that no longer existed.

This is the second time the same root cause has been measured in this campaign, and both times it was the ticket's own `PARTIALLY FIXED` line that carried the truth while its body carried the stale claim.

## The pre-registered hypothesis was confirmed, in the sharpest possible form

The pre-registration predicted: *"A high score on part 1 with a low score on part 2 is the outcome that would most clearly show the measure tracks transcription rather than foresight."*

**That is exactly what happened.** All three hits — `permissions.py`, `pattern_overlap.py`, `test_permissions.py` — were named in the ticket **with line numbers**. Every unleaked prediction missed. On this item the measure recorded transcription and nothing else.

## Surprises, with causes

| file | lines | cause | evidence |
|---|---|---|---|
| `test/unit/test_pattern_overlap.py` (new) | 205 | **E** | `pattern_overlap.py` had **no dedicated test module**. Ticket 80's estimator made exactly this inference for `path_utils` and predicted a new file correctly; this one did not make it for `pattern_overlap`. A repeatable inference, available and unused. |
| `test/unit/test_hard_deny.py` | 26 | E | the hard-deny carve-out consequence was not foreseeable from the ticket |
| `docs/native-pattern-reference.md` | 19 | E | the estimator predicted no documentation at all — a third instance of doc files being under-predicted (77 and 78 both predicted `README.md` and were wrong) |
| `toolguard/tools/consolidate.py` | 17 | E | followed `split_default_body`'s change |

**0 alarms** (`C`, `P`, `D`). All four are `E`, plus the separate `I` finding on the downstream set.

## Cost, recorded outside the protocol

**~11 hours and six blinded review rounds for 552 lines.** Every blocking finding across all six rounds was a false claim in documentation, not a defect in code, and rounds 3-6 caught errors of the **coordinator's**, not the implementers'. The production change was verified correct from round 1.

Arnon's diagnosis, which is the durable lesson: *"this looked simple and it still looks simple - so why is it taking me so long?"* A prefix match is the canonical pattern; a 14-hour estimate for one should have been questioned before any work started. See auto-memory `feedback_complexity_mismatch_is_a_stop_signal`.
