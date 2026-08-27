---
title: TOO-45 surprise factor - ticket 82 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/82-prereg
---

# Pre-registration, proposed ticket 82 (implement native's wrapper-stripping list)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## This item is unlike every other in the series, and that is why it is worth scoring

**The ticket's original premise was refuted and the ticket was rewritten** (2026-08-20). It claimed `sudo rm -rf x` and `env rm -rf x` evading `deny Bash(rm:*)` were toolguard defects; the published Claude Code documentation lists the stripped wrappers exactly, `sudo` and `env` are not among them, and toolguard was faithful. The real defect is the mirror image: native strips nine prefixes and toolguard strips none.

So the estimate is made against a **corrected** ticket. Recorded because it changes what the item measures — this is no longer "predict the touch set of a described defect" but "predict the touch set of a defect whose *direction* was inverted after filing." If the estimate lands well here, that is evidence the measure tracks the change rather than the ticket's framing.

## LEAK STATUS: MODERATE, and asymmetric between production and test

The rewritten ticket names `_command_variants` (a function, not a module) and states that it feeds DEFAULT matching alone. It names the `.peg` grammar and ticket 77 phase-1's `assignment_prefix` / `command_word` seam. It names **no module paths and no line numbers**.

So the estimator gets strong hints about *mechanism* and almost none about *file membership*, which is the better half to leak. Between ticket 17 (severe leak) and ticket 83 (light), this sits in the middle and adds a third point to that comparison.

## THE HARD PREDICTION, and it is genuinely hard

The coordinator has proposed — **not yet accepted by Arnon** — that the wrapper list live in a **new module that does not exist today**, `toolguard/claude_code_contract.py`, holding facts owned by Claude Code rather than by toolguard: the stripped and not-stripped wrapper lists, the matching semantics toolguard mirrors, the hook wire-protocol field names, each with a source URL and a verification date.

**An estimator cannot transcribe a file that does not exist.** Predicting it requires reasoning from the ticket's demand that the list be dated and externally sourced to the conclusion that it needs a home of its own. This is the single most informative prediction in the series so far, and it is scoreable in both directions:

- predicted and created -> real foresight, the strongest positive evidence the protocol has produced
- not predicted but created -> `E` if the estimator had no basis, but arguably `S` (scope creep) if the module is judged a coordinator addition beyond the ticket
- predicted but not created -> a precision miss, and a useful one: it would mean the design question has a defensible answer the coordinator did not take

**The cause assignment here is unusually contestable**, which makes 82 a good candidate for the protocol's required **separate blind adjudicator**. Choosing it now, before results, satisfies the protocol's "choose before seeing which ones look good."

## Design decisions NOT leaked to the estimator

1. Whether the new module is created at all, or the tuple goes into the existing `constants.py`.
2. Whether stripping is applied **symmetrically to allow and deny**. It must be — native's own wrapper example is an allow rule — but the estimator is not told, because the wrong answer (importing 77's assignment asymmetry) is exactly the error the coordinator already made once, and whether an independent estimator reproduces it is worth knowing.
3. Whether recognition lands in the `.peg` grammar or in Python. The two-phase rule requires the grammar first, which the estimator may or may not infer.

## Evidence obligation

Anti-vacuity applies with force. **The eleven not-stripped prefixes currently return the correct answer for the wrong reason** — toolguard has no wrapper list at all, so nothing can be on the wrong side of one. A post-fix run showing those eleven still unmatched therefore proves nothing unless it also shows the nine stripped ones now matching. Both halves of the table are the evidence; neither alone is.

## Ordering discipline

The estimator writes `82-estimate-predictions.md` and `82-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
