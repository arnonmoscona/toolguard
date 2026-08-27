---
title: TOO-45 surprise factor - ticket 79 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/79-prereg
---

# Pre-registration, proposed ticket 79 (command substitution runs foreign code with no ASK floor)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation. Scored under the redefined metric: **line-weighted recall against the final committed diff** is the headline.

## Evidence, and how to read it

`$(...)` appears **1,121 times** across the corpora — 1,115 in toolguard (2.1% of commands), 5 in featherhill (0.1%), 1 in instagram. This is a **command shape**, i.e. agent behaviour rather than project configuration, so per `.claude/rules/evidence-before-fixing.md` both corpora carry information. The **20x gap** between them estimates how much is task-specific: toolguard development is shell-heavy in a way flower-shop development is not.

Even discounted to featherhill's rate, this is the highest-exposure runtime ticket remaining.

## The sibling that must be checked FIRST

**Ticket 67 — *"wrapping foreign inline code in `if` or `while` defeats the ASK floor entirely"* — is already FIXED** and in `resolved/`. That is the same floor, defeated by a different wrapper.

**So the first question is not "how do we build this" but "does 67's mechanism already generalise?"** If 67 taught the decomposition to descend into a construct, command substitution may be one more construct rather than a new design. An implementation that builds a second, parallel mechanism when the first could be extended is a finding, not a fix — and this project already carries the `_command_variants`-feeds-DEFAULT-only lesson about exactly that.

## The prediction that matters

**Does this land in the PEG grammar, or in the Python that consumes it?**

The `.peg` may already parse `$(...)` — ticket 77's experience is the precedent: I expected a grammar change for `if`/`while` conditions and **the grammar already parsed them; the consuming Python discarded the field.** If that repeats here, the fix is in `command_extractor` / `command_model` and the two-phase grammar procedure does not apply. If the grammar genuinely cannot see `$(...)`, phase 1 is `.peg` + canopy regeneration ONLY, reviewed alone.

**The estimator is not told which.** This is the cleanest test in the series of whether it reasons about the parse pipeline or only about the defect's symptom.

## Falsifiable, locked now

1. **Nesting must be handled or explicitly declined.** `$( ... $(...) ... )` is the same open-recursion problem as ticket 34's nested backticks — which was *skipped* on zero real evidence. If this fix descends one level and stops, **that must be stated**, not left as an accident that reads like completeness.
2. **The floor must reach the substituted command's *content*, not merely notice that a substitution exists.** Flagging `$(...)` as "contains a substitution -> ask" would raise the ask rate on 2.1% of commands while checking nothing. That is the vacuity failure in its most tempting form here: a mechanism that fires often, looks protective, and examines nothing.

## Anti-vacuity — this one is a REAL replay, like 18 and unlike most

1,121 real commands carry the shape, so a before/after corpus replay **should show non-zero movement**. A clean replay is evidence the fix did not work. Run it early.

**But watch the direction.** This fix makes more commands hit `ask`, so the movement is `allow -> ask`. **Measure how much**: if 2.1% of toolguard's commands start prompting, that is a real change in daily friction, and Arnon should see the number before it lands rather than discover it in use.

## Ordering discipline

The estimator writes `79-estimate-predictions.md` and `79-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
