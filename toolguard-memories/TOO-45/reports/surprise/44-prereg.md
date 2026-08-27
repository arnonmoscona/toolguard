---
title: TOO-45 surprise factor - ticket 44 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/44-prereg
---

# Pre-registration, proposed ticket 44 (ambient state read at point of use)

Written **before** the estimate is generated and before implementation. Protocol: `surprise-factor-protocol.md`.

## Leak status — PARTIAL, and it must discount the raw score

The ticket names **three modules by name**: `testability.py` (4 mentions, as a *proposed new* module), `path_utils.py`, and `test_auto_migrate.py`. It names **no paths** in `package/module.py` form.

So the estimator is partly transcribing rather than predicting for those three. Per the protocol, two surprise sets are reported: the raw one, and the one restricted to files the ticket did not name. **The second is the honest signal.**

The ticket also names patch *targets* (`sys.stdin`, `sys.stdout`) and gives aggregate counts — 23 `Path.home()` calls across 10 files, 19 `os.environ` reads across 8, 485 `patch(` across 33 test files — **without naming which files**. Those counts are a genuine hint at the size of the touch set while leaking nothing about its membership, which makes this a better item for the measure than 05 or 10 were.

## Weakening of the blinding, recorded rather than hidden

The original builder wrote the inventory inline into the estimator's prompt, so the estimator had no repository access and blinding was **mechanical**. That script did not survive its session scratchpad. It has been rebuilt, but the briefing is now passed as a *file path* the estimator is instructed to read, alongside the ticket — and nothing prevents it reading more.

**Blinding for this item is therefore honour-system, not mechanical**, and that is strictly weaker. It is the same class of defect this protocol already recorded once ("enforceable only by my own good intentions"). The estimator is asked to declare every file it read; a declaration that lists only the two permitted files is evidence, not proof.

## Ordering discipline

The estimator writes to `44-estimate-predictions.md` and `44-estimate-uncertainties.md` and returns **only a completion token**, so its answer cannot arrive in the coordinator's context via the completion notification. The files are not opened until implementation is complete and green.

## Note on ticket 45

**Ticket 45 was implemented without a pre-registration** — the protocol was not resumed until after it was done. It is excluded from the series rather than scored retroactively, since a retrofitted estimate is not blind.