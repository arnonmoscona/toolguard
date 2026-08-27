---
title: TOO-45 surprise factor - ticket 81 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/81-prereg
---

# Pre-registration, proposed ticket 81 (runtime sentinel for a relative `resolve()`)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## LEAK STATUS: SEVERE, and this item is close to unscoreable

The ticket names `PATH_AMBIENT_OWNERS`, `PATH_AMBIENT_FATAL_MEMBERS`, `test/unit/_real_log_dir_guard.py` as the pattern to copy, `test/unit/__init__.py` as the file needing the registration, `TestAmbientRoutesOnTheRealTree`, `test_main_ambient_flag_smoke`, and **enumerates all ten owner modules by name**. It also states the fix shape for both gaps.

**Design is additionally leaked on purpose**: the coordinator has already taken the deferred decision — promote `resolve` to `PATH_AMBIENT_FATAL_MEMBERS` *and* keep the suite asserting `fatal_findings == []`, so tool and suite agree — and that will be given to the estimator, because predicting the touch set of a design nobody will build measures nothing (the ticket-77 precedent).

So this is the **most leaked item in the series**, on both axes at once: file membership *and* design. Recorded plainly, before results: **expect high recall that means very little.** If the aggregate wants one item to demonstrate what an unscoreable ceiling looks like, this is it — and it pairs with ticket 83 (light leak, same week) exactly as 17 does.

**Recommendation, made now rather than after seeing the number**: report 81 as **not scoreable** for recall, and use it only for the two things below, which the leak does not touch.

## What is genuinely open despite the leak

1. **How wide the runtime sentinel's blast radius is.** `_real_log_dir_guard.py` is the template, and the ticket notes the guard needed both a registration in `test/unit/__init__.py` *and* an `atexit` hook so it did not depend on discovery order. A sentinel wrapping `Path.resolve` and `Path.absolute` **for the duration of the whole suite** touches every test that resolves a relative path — and this repo has ~3,769 tests. Whether that comes out as two files or twenty is not in the ticket.
2. **Whether the sentinel finds anything.** This is the real question and it is a *result*, not a touch set. The ticket's own route history is the reason to expect something: `expanduser` escaped four blinded review rounds and was a **live isolation hole**, `resolve` escaped five, `absolute` escaped six — each invisible to the instrument used to clear the round before it. A sentinel is the first instrument in that sequence that observes the property directly rather than a proxy for it.

## The prediction that matters more than recall

**If the sentinel is genuinely the first direct observation, it should find at least one relative-receiver `resolve()` that all prior static instruments missed.** Recorded as a falsifiable expectation, before it runs.

- **Finds something** -> confirms the campaign's recurring shape, that the residue is wherever the previous instrument was not pointed.
- **Finds nothing** -> the honest reading is *not* "the tree is clean". Per the ticket, gap B is invisible to AST by construction, so a null result means the sentinel is a **negative result over a path nothing exercised** unless the suite is first shown to execute relative-receiver `resolve()` calls at all. **The sentinel must be validated against a deliberately planted relative `resolve()` before its silence is believed.** This project has been misled by exactly this substitution more than once — an instrument's silence read as coverage of something it never examined.

## Ordering discipline

The estimator writes `81-estimate-predictions.md` and `81-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
