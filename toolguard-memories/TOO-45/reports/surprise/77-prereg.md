---
title: TOO-45 surprise factor - ticket 77 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/77-prereg
---

# Pre-registration, proposed ticket 77 (a leading env assignment evades a deny rule)

Written **before** the estimate was opened and before implementation.

## The estimator was told the chosen design, and that is deliberate

Ticket 77 lists three candidate fix directions. Arnon chose a fourth shape: strip a leading assignment for **deny/hard_deny/ask** as an **additional variant alongside the raw spelling**, and for **allow** match raw only *except* for assignments in a configured safe-list. Predicting a touch set for a design nobody will build measures nothing, so the estimator was given the chosen one. **This is a deliberate leak of design, not of files** — it names no module, and the interesting question is what the design *implies*.

## CONTAMINATION — now specific, and worse than "context arrived unbidden"

The 80 estimator noted its system prompt carried project context. **The 77 estimator itemised it and said it changed the estimate:**

- the project `CLAUDE.md` — the PEG-grammar constraint, and the `TG_INTENT=1` / `TG_ATTEST_READONLY=1` markers **quoted verbatim**, which are precisely this ticket's subject matter
- the global `CLAUDE.md` — the "prose is output, not a data structure" incident, which it reasoned from
- the project **auto-memory index**, which **named modules and rules it would otherwise not have known existed**
- a **git status listing untracked filenames** under `toolguard-memories/TOO-45/`

The baseline is therefore not "a competent person who read the ticket and skimmed the tree". It is **"a competent person who read the ticket, skimmed the tree, and has read the project's conventions, its architectural constraints and an index of its own campaign notes."**

### The part that breaks trend analysis, not just calibration

**The contamination is not constant across the series — it grows.** Auto-memory accumulates as the campaign proceeds and it names modules; the git status lists more files each week. So a later item's estimator is better informed than an earlier one's **by an amount nobody chose or measured.**

Any comparison of recall *across* items therefore confounds "the estimator got better at predicting" with "the estimator was told more". **The aggregate must not read a rising trend as instrument improvement**, and the ablation partitions cannot correct for it, because the contaminant is correlated with item order rather than randomly distributed.

Two honest options, both for the aggregate to choose: report only within-item findings and refuse the trend, or record each item's contamination surface and treat the series as observational rather than controlled. **There is no version where the trend line means what it appears to mean.**

Not fixable from inside the protocol — the harness injects this and the Agent tool has no lever for it.

## Ordering discipline

The estimator wrote to `77-estimate-predictions.md` and `77-estimate-uncertainties.md` and returned only `DONE` plus its declaration. Neither file is opened until the ticket is implemented and green.