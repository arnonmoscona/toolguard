---
title: TOO-45 surprise factor - ticket 84 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/84-prereg
---

# Pre-registration, proposed ticket 84 (`.strip()` truncates a regex body; the error is swallowed)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## LEAK STATUS: LIGHT on files, HEAVY on mechanism

The ticket names one function, `parse_pattern`, and no module path, no line numbers, no test files. But it states the mechanism completely — `.strip()`, dangling backslash, `re.error` swallowed as non-match — so there is nothing to diagnose. **This is a prediction task about blast radius only**, which makes it a cleaner instrument than it looks: the estimator cannot score by transcribing a diagnosis it was handed, because the diagnosis is not the touch set.

## The two open questions ARE the measurement

The ticket declines to answer them, and they drive the file count directly:

1. **Is `.strip()` wrong for other pattern types too?** Plausibly for `[glob]`, and for a DEFAULT pattern with a meaningful trailing space. A regex-only fix touches one branch; a general one touches the parse path and every pattern type's tests.
2. **Where else is a compile failure swallowed?** The ticket is explicit that *"the bug here is the swallow, not the strip"*, so a fix confined to `.strip()` leaves every other malformed regex silently inert. Whether the implementation follows that instruction is the single biggest determinant of the touch set — and it is a scope decision, not a technical one.

**A narrow fix and a faithful fix differ by an order of magnitude in files**, and the ticket contains the argument for the wider one without mandating it. If the estimator predicts wide and the implementation goes narrow, that is `X` (descoped), not estimator error — a distinction the protocol currently cannot express and which was just added as a gap in `RESULTS-LOG.md`. **84 is therefore a live test of that new cause vocabulary**, on an item where the ambiguity was pre-registered rather than discovered afterwards.

## Prediction worth recording, since it is falsifiable

The ticket names this as an instance of the campaign's most common defect — *a mechanism that fails open and says nothing* — alongside `log_crash` throwing out of the hook's own except clause, the corpus that could not observe the ASK floor, and the checkers that reported PASS having examined nothing. **If the fix surfaces the failure rather than merely correcting the strip, it must reach an error/reporting path**, which means `error_reporter` or the config-validation tier, not just the matcher. An estimator that predicts only `patterns.py` has read the defect and not the ticket.

## Anti-vacuity, and it is unusually pointed here

**Exposure is zero today** — no rule in this repository ends in escaped whitespace. So every instrument this project uses to prove a matching change safe (corpus replay, verdict corpus, before/after digest comparison) will report "no differences" **and mean nothing at all**. The evidence has to be constructed: a rule of the failing shape, asserted to deny before and after, plus a malformed-regex rule asserted to be *surfaced* rather than silently inert. A clean replay here is not weak evidence, it is zero evidence.

## Ordering discipline

The estimator writes `84-estimate-predictions.md` and `84-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
