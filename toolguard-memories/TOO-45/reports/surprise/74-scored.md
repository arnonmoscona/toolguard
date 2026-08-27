---
title: TOO-45 surprise factor - ticket 74 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/74-scored
---

# Ticket 74 scored (hook bypasses the registry; empty registry fails open)

Actual from `git diff --numstat 982e550..c335e22`. Headline: **line-weighted recall against the final committed diff**.

## Actual — 3 files, 261 changed lines

| file | +/- | lines | predicted? | confidence |
|---|---|---|---|---|
| `toolguard/hook.py` | 85/35 | 120 | yes | high |
| `test/unit/test_hook.py` | 108/5 | 113 | yes | high |
| `test/unit/test_tool_spec.py` | 14/14 | 28 | yes | low |

**Line-weighted recall: 261 / 261 = 100%. File recall 3/3. ZERO surprises — the first in the series.**

Predicted-but-untouched (5): `tool_spec.py` (medium), `error_reporter.py`, `permission_resolution.py`, `config.py`, `test_hard_deny.py` (medium). Precision 3/8 = 38%, which under the redefined metric is an integrity figure only — over-prediction costs Arnon nothing.

## The scope prediction — scored separately, and CORRECT

The estimator predicted **NARROW**, reasoning from the ticket's own scope fencing: findings 3-5 are each explicitly excluded by the ticket ("this needs Arnon's decision, not a fix"; "cosmetic today"; "defensible").

**The implementation was narrow** — and reached that independently, from the code: the other two registry consumers already comply, so enforcing an invariant they satisfy buys an architecture test at most.

**This is the first item where an UNLEAKED prediction came out right.** Contrast ticket 18, whose unleaked downstream prediction was 0/7 while its leaked defect site scored 3/3. Same pattern of leak, opposite result on the part that matters.

## Why this one worked, and it is not luck

The defect site was leaked as usual — the ticket names `hook.py` and the test files. That explains the recall and is worth nothing.

**What the estimator got right was the scope question, which was genuinely open**, and it got it right by reading what the ticket *excluded* rather than what it named. That is a different and better inference than transcription: exclusions are the part of a ticket that constrains the answer without giving it away.

**Candidate for the aggregate**: whether estimators do systematically better on scope questions than on file membership. If so, the protocol should ask for scope predictions explicitly on every item rather than only where the coordinator happens to notice the question — as it now does for 39 and 79.

## An `I`-class near-miss worth recording

The ticket named a RED test as evidence for finding 1. **It was green** — `640f86b` had already fixed `_resolve_event`, and the live defect was in `_handle_command_tool`. The coordinator's brief repeated the ticket's claim; the implementer ran the test and found otherwise.

**This is the second measured instance of cause `I` (inherited staleness)**, after ticket 18. Both times the ticket's own text described a tree that no longer existed. Unlike 18, it cost nothing here — the implementer checked before working.

## Cost

**One implementation pass, two review rounds, ~4h.** Round curve 5 -> 1 -> commit: high then draining, the healthy shape. Against ticket 18's 2 -> 2 -> 1 -> 3 -> 3 -> 2 over ~11h.

First ticket run entirely under the three controls added after 18 (estimate-outlier check, round-curve check, measure-before-briefing). One data point, not a trend.
