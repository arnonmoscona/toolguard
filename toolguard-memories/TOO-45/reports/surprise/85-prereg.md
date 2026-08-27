---
title: TOO-45 surprise factor - ticket 85a pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/85-prereg
---

# Pre-registration, ticket 85 chunk A (the external-contract module)

Written before the estimator runs and before implementation. Scored against **chunk A's commit only**; chunks B/C/D are separate items.

## Coordinator predictions, locked

1. **The wire protocol is `hook.py`'s alone, so chunk A is small.** Measured: `tool_name`, `tool_input`, `hookSpecificOutput`, `permissionDecision`, `permissionDecisionReason` appear in **`hook.py` only**. The outlier is `additionalContext` — `hook.py`, `rule_entry.py`, `rule_sort.py`, `testing/sandbox.py`. **Predicted touch set: the new module, `hook.py`, those three, and tests.** Falsifier: any change to `config.py` or the parser, which would mean the move over-reached.

2. **The implementer will be tempted to move too much, and the criterion is precise.** Arnon: *"Functions that mix references to external contract **structures** but have toolguard-specific logic **should not** be moved."* `payload_key()` moves; `hook.py`'s request handling does not. **Predicted: at least one judgement call gets reported rather than silently taken.**

3. **`constants.py` will be left alone in chunk A** even though it mixes contract and non-contract, because splitting it is chunk B. Falsifier: `constants.py` in the diff.

## The character-of-fix question — asked of the estimator too

**Is chunk A a *move* or a *re-export*?** A move rewrites every call site; a re-export leaves callers untouched and creates the module as a facade. **My prediction: a genuine move for the `hook.py` literals** (they are inline strings, not imports, so there is nothing to re-export), **and this is what makes the import edge exist** — which is the whole deliverable per Arnon: *"the whole function would end up directly referencing the contract but not expressing it. Just that dependency alone is useful for static analysis."*

## What would make this cost more than it should

Any attempt to also **check** the new edge (an `architecture_fitness --contract` mode) inside chunk A. That is a separate instrument and belongs after the module exists and has settled. If it appears in the diff, that is scope growth, not thoroughness.

## Return channel — the SAME partial compliance as item 22, which makes it a pattern rather than a one-off

Returned *"Both files are written.\n\nDONE"* — identical in shape to item 22. **Zero predictive content**; both files written and unread.

**The consequence-naming wording is now 3 for 3 on substance** (items 20, 22, 85) **and 1 for 3 on preamble** (only item 20 returned a bare `DONE`).

That is a stable, repeatable split, and it settles the design question: **the rule should forbid *disclosing a prediction*, not *emitting a sentence*.** Two independent estimators produced the same harmless preamble under wording that bans "not even one sentence" — so the ban on sentences is simply not being followed, while the ban on substance is followed perfectly. A rule that is routinely half-obeyed teaches the reader to judge which half matters, which is exactly the adjudication I have now done twice.

**For the aggregate**: report as *"substantive leaks: 2 of N under weak wording, 0 of 3 under consequence-naming wording; 2 cosmetic preambles, no information disclosed."* Do not report 85 or 22 as contaminated.
