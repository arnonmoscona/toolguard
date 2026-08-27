---
title: TOO-45 surprise factor - ticket 80 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/80-prereg
---

# Pre-registration, proposed ticket 80 (`Path.resolve()` as a fifth route to cwd)

Written **before** the estimate was opened and before implementation. Protocol: `surprise-factor-protocol.md`.

## Leak status — HEAVY, and this item's raw score is close to worthless

The ticket names modules directly (`path_utils`, `ambient`, `decision_ledger`, `env_config`, `auto_migrate`), gives a **site count** (17), names the five `Path` members, and — because the design was settled with Arnon in conversation and written into the ticket — **specifies the intended shape in detail**: `ambient` stays a facts module, `expanduser` moves to `path_utils`, no `ambient.resolve()`, and the checker lands in `tools/architecture_fitness.py`.

An estimator handed that is largely transcribing. **Only the leak-discounted set carries signal here**, and even that is weak, since a named design implies files the ticket does not name. Recorded now so the discount is not argued afterwards.

**This makes ticket 80 a poor member of the findings set and a reasonable member of a tuning set** — worth remembering when the ablation partitions are drawn.

## Blinding — weaker than the two-file rule states, by the estimator's own disclosure

The estimator was told to read exactly two files and declared it did. It also volunteered that **the global and project `CLAUDE.md` files and the auto-memory index arrived in its system prompt unbidden**, and said it did not act on them beyond general project conventions.

That is a real contamination channel and it applies to **every** item in this series, not just this one: the harness injects project context the protocol assumes the estimator does not have. Auto-memory in particular contains observations about this very campaign. The declaration is evidence, not proof, and the honest position is that the "lazy human who skimmed the tree" baseline is really "lazy human who skimmed the tree *and has read the project conventions*".

Not fixable from inside the protocol. Recorded so the aggregate can say so.

## Ordering discipline

Estimator wrote to `80-estimate-predictions.md` and `80-estimate-uncertainties.md` and returned only `DONE` plus its declaration, so nothing reached the coordinator's context via the completion notification. Neither file is opened until the ticket is implemented and green.