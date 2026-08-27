---
title: 15-migrate-has-no-cross-process-lock
type: note
permalink: toolguard/too-45/proposed-tickets/15-migrate-has-no-cross-process-lock
---

**FIXED in `05f786d` (TOO-45 phase 2).** Superseded by `15-migrate-needs-its-own-cross-process-lock`, whose lock (`toolguard/file_lock.py`) closes the gap this ticket discovered.

# Proposed: `migrate()` rewrites the permission config with no cross-process lock

**Status:** found 2026-08-08 by the final adversarial review of punch-list #01. **Pre-existing.** Deferred out of #01 deliberately — the fix is a locking design, not a docstring.

## The defect

`auto_migrate.run_auto_migration` gates `migrate()` on `suppression.claim(...)`. That claim is the **only** thing serializing a read-modify-write of `.claude/settings.local.json` and the toolguard config across concurrent hook processes.

`claim()` returns `True` on **any** storage error — by design, because a broken suppression store must never block a permission decision. So a *persistently* unhealthy store (corrupt database, full disk, read-only `~/.toolguard`, `sqlite3` absent) makes every concurrent process's claim fail open **at the same time**. They all run `migrate()`.

`verified_write_config` is atomic per write — temp file, `fsync`, `os.replace` — so there is no torn file. But there is no lock across the read-modify-write, so **last writer wins and another process's migration of the permission rules is silently discarded.**

## Why this is the one that touches enforcement

Every other consequence of a broken suppression store is noise: a warning repeats, housekeeping doesn't run. This one ends with the permission configuration missing rules the user believes were migrated. Decisions are then made against an incomplete rule set, and nothing reports it.

Note the coupling that makes it worse: the claim failing open is *correct* behaviour for warnings and *wrong* behaviour for a config rewrite. One primitive, two callers, opposite safe directions. That is the design smell worth fixing, more than the lock itself.

## Not reachable by contention alone

Ordinary lock contention is handled — `timeout=5.0`, and the measured worst case inside `claim()` was 0.63 s at 16 concurrent processes. This requires the store to be *persistently* broken, not merely busy.

## Options

1. **A real lock around the migrate read-modify-write** — an `O_EXCL` lockfile or `fcntl.flock`, independent of the suppression store. Correct, and it stops conflating "have I already warned today" with "am I allowed to write the config".
2. **Make the migrate gate fail CLOSED.** If the suppression store cannot be reached, do not auto-migrate; warn instead. Auto-migration is a convenience, and declining to run it is safe. Cheapest option, and probably right.
3. Detect a persistently unhealthy store and disable auto-migration with a warning — the per-feature degraded-mode treatment already built in #01, extended to cover "store present but unusable" rather than only "sqlite3 missing".

My recommendation is **2**, possibly with **3** for the reporting. Option 1 is the most correct and the most work.

## Related

- `suppression.py` states its own caveat honestly. `auto_migrate.run_auto_migration`'s docstring did not, and is being corrected inside #01 — a docstring fix only, not a behaviour change.
- The same "store exists but is unusable" blind spot means `available()` reports healthy for a corrupt database, so no degraded-mode warning fires. Worth folding into whichever option is chosen.

## Decision needed

Which option, and whether it goes in TOO-45 or afterwards.
