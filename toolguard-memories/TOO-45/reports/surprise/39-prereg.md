---
title: TOO-45 surprise factor - ticket 39 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/39-prereg
---

# Pre-registration, proposed ticket 39 (the write guard does not stop a permission-weakening rewrite)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation. Headline metric: **line-weighted recall against the final committed diff**.

## Scope taken from the AMENDMENT, not the body

Ticket 39's first line: *"PARTIALLY FIXED in `05f786d`. A hard-deny egress check was added (`toolguard/config_write_guard.py:336-352`); **still open: a `deny`->`allow` or `ask`->`allow` rewrite still writes successfully.**"*

**That is a narrower and more serious statement than the ticket title** ("the content-loss check is placement-blind"). What remains is not a placement subtlety — it is that **the guard protecting toolguard's own configuration does not stop a rewrite that weakens a permission.** Reading the body instead of this line is the error that cost ticket 18 a mispriced fourteen-hour estimate.

## No log signature, and that is not a mitigation

The write guard runs when toolguard's config is **written**, not when a command is decided, so nothing in the decision corpus can speak to it. Per `.claude/rules/evidence-before-fixing.md` a zero count measures observability, not absence — and this failure is silent by construction: the write **succeeds**.

**It belongs in Arnon's fail-open class alongside ticket 74** and is scheduled with it for that reason. 74 is the hook failing open; 39 is the write path failing open. Same shape, different subsystem.

## The genuinely open question

**Does the guard need to understand permission SEMANTICS, or only detect a category change?**

- **Narrow**: compare the decision tier of each rule before and after (`deny`/`ask`/`allow`), and refuse a write that moves any rule toward `allow`. No pattern semantics needed — only the section a rule sits in.
- **Wide**: a rule can weaken without changing section, by broadening its pattern (`rm -rf /tmp/*` -> `rm:*` inside `deny` narrows *coverage* while staying `deny`). Detecting that needs the matcher, which drags `permissions.py` into the write path and inverts a layer relationship.

**The estimator is not told which.** This is the item's real architectural question, and the wide answer would show up as exactly the expensive surprise the redefined metric measures: unexpected files, in a subsystem the ticket never names.

## Falsifiable, locked now

1. **A refusal must say what it refused and why.** A guard that silently declines a write is the same defect wearing the opposite face — this campaign has found `run_guard` reporting `ok=True` over zero cases, checkers reporting PASS having examined nothing, and a swallowed `re.error`. **If the fix rejects the write without a message naming the weakened rule, that is a finding.**
2. **The hard-deny egress check added in `05f786d` must not be duplicated.** A second, parallel mechanism where the first could be extended is the `_command_variants`-feeds-DEFAULT-only lesson repeating.

## Anti-vacuity — a new instrument, so it applies in full

The fix *is* a check. A check that passes over a rewrite it cannot see is indistinguishable from a clean tree. **Validate it against a deliberately constructed `deny`->`allow` rewrite before believing any green result**, and state that the validation ran. This is not the ticket-85 refactor exemption: nothing here is warranted by an Arnon decision, and the whole deliverable is an instrument.

## Ordering discipline

The estimator writes `39-estimate-predictions.md` and `39-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
