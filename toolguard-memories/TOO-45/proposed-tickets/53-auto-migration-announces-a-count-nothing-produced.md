---
title: Auto-migration reports "Successfully migrated 1 pattern(s)" for a run that
  wrote nothing
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/53-auto-migration-announces-a-count-nothing-produced
---

**PARTIALLY FIXED in `05f786d`.** The visible symptom was patched (`toolguard/auto_migrate.py:145`); still open: the root cause — `migrate()` still returns a countless `MigrationOutcome`.

# A success notice derived from data discarded before the write

**Found 2026-08-13. A RED test is in the tree. I owed this ticket — the red test existed for several hours without one, which would have made it un-actionable in phase 2.**

## The defect

Two things combine:

- `MigrationOutcome.SUCCEEDED` **includes the "nothing to migrate" no-op** (`permission_migration.py:81`).
- `run_auto_migration` announces its **own pre-analysis count**, not what `migrate()` actually wrote.

Measured with the real `migrate()`: a run that wrote **nothing** and a run that migrated **one pattern** produce **byte-identical stderr** — `Successfully migrated 1 pattern(s)` — and both return `True`.

## Why it matters

Auto-migration writes the user's configuration **without being asked**. Its stderr line is the only report of what happened. A user reading "migrated 1 pattern" has no way to learn that nothing moved, and no way to distinguish a working migration from one that silently did nothing.

It is also the **"prose is output, not a data structure"** pattern in the config-writing path: the notice is built from data thrown away before the write, so the message and the outcome have no shared source of truth. Same family as proposed ticket 38.

## Fix direction

**`migrate()` must return what it wrote** — a count, or the entries — and `run_auto_migration` must report that rather than its own earlier estimate.

Not fixable from the test side; the information does not survive the call today.

## Related, from the same root

`run_auto_migration` and `migrate()` each **independently recompute** divergence, ignored patterns and governed tools, from separately-obtained inputs, with no lock spanning the gap. They can disagree — and when they do, the user is told a count nothing produced.

## Status in the tree

`test_auto_migrate.test_success_notice_must_not_claim_a_count_migrate_never_confirmed` is deliberately RED.