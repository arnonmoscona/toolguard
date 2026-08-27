---
title: TOO-45 surprise factor - ticket 18 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/18-prereg
---

# Pre-registration, proposed ticket 18-remainder (multi-token `:*` over-match, any-colon split)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## Why this item is now first, and why that matters to the measure

18 was scheduled **last** on cost grounds and promoted to **first** on 2026-08-20 after field exposure was measured: **748 of featherhill's 3,675 matched rules** are the multi-token `:*` shape, roughly one decision in five, against **zero** for tickets 17, 83 and 84. It is the only queued ticket with mass real-world exposure.

**Recorded because the promotion happened after the estimate protocol was designed and before this estimate was taken** — the ordering change is not itself a leak, but it is the kind of context that can drift into a briefing. The estimator is told the ticket, not the triage.

## LEAK STATUS: SEVERE on files, and UNIQUELY HONEST about blast radius

The ticket names `toolguard/permissions.py` with line numbers (158, 163), `toolguard/tools/pattern_overlap.py`, `toolguard/file_matching.py`, `toolguard/tools/uninstall_readiness.py`, `consolidate.py:856`, `clarity.py:221,286`, and the test modules `test_permissions.py`, `test_patterns.py`, `test_tools_consolidate.py`, `test_tools_uninstall_readiness.py`, `test_api.py` with a specific test name.

So file membership is heavily leaked, as with ticket 17 — same cause, the citation-driven #07 sweep.

**But this ticket does something no other item in the series does: it states that its own blast-radius measurement is UNRELIABLE, and says so explicitly.** Two independent runs both got 20 failures and **disagreed about which files**; a third run reported "22 above the floor" while its own breakdown summed to 20. The ticket's instruction is *"Re-measure before scheduling; do not trust either list below."*

**That makes 18 the best blast-radius prediction task in the series**, despite the file leak. The named files are the *defect site*; the disputed 20 are the *consequence*, and nobody knows them. The interesting prediction is not "where is the bug" — the ticket gives that away — but **"which tier moves when you fix it."**

## The scoring split this item requires

Score the touch set in **two disjoint parts**, and do not pool them:

1. **The defect site** — leaked, expect high recall, near-worthless as signal.
2. **The downstream tier** — `consolidate`, `redundancy`, `clarity`, `pattern_overlap`, the golden corpus, `test_api`'s hard-deny carve-out. **This is the measurement.** The ticket predicts the breakage lands here and cannot say where.

A high score on part 1 with a low score on part 2 is the outcome that would most clearly show the measure tracks transcription rather than foresight.

## Falsifiable predictions, locked now

1. **The verdict corpus / golden corpus WILL need regeneration.** The ticket says the corpus was built against a matcher that behaves this way.
2. **`test_api.TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command` will change or be deleted.** The ticket establishes that a hard-deny carve-out is reachable **only** through the over-match: `Bash(rm -rf /tmp:*)` matches `rm -rf /tmp/foo` solely because of the glued `*`. Boundary-guarded, the verdict flips `allow` -> `deny`. If this test does *not* move, either the fix is narrower than the ticket describes or that analysis was wrong — both worth knowing.
3. **`prefixes_overlap`'s docstring becomes true.** Its "exactly when" claim currently has 315 measured counterexamples; the ticket argues a correct matcher removes them. **If the fix lands and the 315 do not go to zero, the ticket's model of the defect is incomplete.** This is the cheapest single falsifier available and should be run before and after.

## The trap this ticket sets for its own implementer, recorded so the estimate is not scored against a mistake

`test_tools_consolidate.test_consolidation_preserves_prefix_extension_commands` **documents the over-match as intended behaviour** in its Given/Then. The ticket warns: *"whoever fixes this must read that docstring as a description of the bug, not of the contract."* It was deliberately left standing, because the sweep does not launder false prose.

**If the implementation preserves the over-match to keep that test green, the ticket is not done** — and the touch set would look small and clean while being wrong. Flagging it here so a small actual set is not mistaken for a well-contained change.

## Anti-vacuity — inverted for this item

Unlike 17/83/84, **the corpus replay here is real evidence rather than a null**, because 752 real rules have the affected shape. A before/after replay should show **non-zero** changes. **A clean replay would be evidence the fix did not work**, which is the opposite of every other ticket in this queue and the reason to run it first rather than last.

## Ordering discipline

The estimator writes `18-estimate-predictions.md` and `18-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
