---
title: 15-once-per-period-cannot-express-must-not-run
type: note
permalink: toolguard/too-45/proposed-tickets/15-once-per-period-cannot-express-must-not-run
---

**FIXED in `05f786d` (TOO-45 phase 2).** A design ticket, folded into #01's once-per redesign and self-declared closed — see `toolguard/once_per.py` and `toolguard/once_per_store.py`.

# The once-per-period mechanism cannot express "this must not run without the guarantee"

**Status:** rewritten 2026-08-08 to Arnon's framing. **Folded into punch-list #01's redesign** — recorded here because the reasoning is worth keeping, and because a residual remains.

## What I got wrong twice

First I titled this *"`migrate()` has no cross-process lock"*. That named the damage, not the defect. Arnon: *"I am not sure why you label this as a migrate issue."* Correct — `migrate()` never had its own mutual exclusion; it **borrowed** it from a primitive built for warnings.

Then I called it a failure-direction issue. Closer, still mechanical. Arnon's framing is the right one:

> Client code needs to signal intent, severity, things like that. It does not need to know about mechanics. So what you're saying is that we have two situations that need different signaling of intent and severity. The ticket then needs to say exactly that: the existing mechanisms do not support expressing and executing the intent in this use case. So we need to build those and fix the problem that way.

## The defect, stated properly

**Two callers have genuinely different intent, and the mechanism had no vocabulary for the difference — so both silently inherited one behaviour.**

| caller | intent | correct behaviour when the guarantee is unavailable |
|---|---|---|
| a divergence or takeover **warning** | "don't repeat this at the user" | **emit anyway.** A repeated warning is noise; a missed one is a lost signal. |
| **auto-migration**, which rewrites `settings.local.json` and the toolguard config | "do this at most once" | **do not run.** Without the guarantee, concurrent processes all run it, and last-writer-wins can silently discard another's migration of the permission rules. |

The primitive returned `True` on any storage error — right for the first row, wrong for the second — and neither call site said which it wanted, because there was nothing to say it with.

## The fix

**Build the expression, and execute it.** The interface names the intent; the mechanism honours it. In #01's redesigned shape that is the difference between `once_per_day.warn(...)` — proceeds when the guarantee is unavailable — and `once_per_day.run(...)` for an action that must not proceed without it, with a skip reported through the normal reporting path rather than swallowed.

This is not an extra feature bolted on. It is what the ticket asked for all along: the previous design centred on a lock-shaped `claim()`, and a lock has exactly one failure policy for everybody.

## Severity, honestly

I overstated this when it was a separate ticket. It requires the store to be **persistently** broken, not merely contended — ordinary contention is handled, and the measured worst wait inside a claim was 0.63 s at 16 concurrent processes. The loss also requires the racing processes to be migrating **different** things; identical concurrent migrations converge harmlessly.

## Residual after #01 — small, and worth one line somewhere

`migrate()` still has no mutual exclusion **of its own**. It is safe because its only caller now declines to run it without the once-per-day guarantee. A future caller invoking `migrate()` outside that path would reintroduce the race with nothing to catch it.

**SUPERSEDED — ACCEPTED FOR IMPLEMENTATION (Arnon, 2026-08-08):** *"let's do it, not so much because it's very urgent, but because I think that it's the right size for the other things we're trying to learn here (about dev process, metrics for change etc.)"*

So the lock gets built. The priority reasoning below still stands on its own terms — the risk is genuinely low — and the justification is **methodological**: this item is a near-ideal specimen for the surprise-factor measure and the review-cadence work, in a way neither earlier item was. #05's ticket named its own target files, so its prediction was partly transcription; #01 moved through five passes and two requirement reversals, so its touch set was a moving target. **#15 is narrow, well-specified, unlikely to reverse, and has a known blast radius.** It is the control case the series lacks.

Runs after #01 lands, since #01 is currently rewriting `auto_migrate`.

## Earlier reasoning, retained

**Previously decided: low priority, docstring only, no lock.** His reasoning: the scenario needs `migrate()` to be *"triggered mechanically and automatically"*, and a person running two parallel sessions that both migrate is possible but not likely.

Worth recording why that holds. The mechanically-and-automatically triggered path is precisely the one that **did** exist — the hook calls auto-migration on every tool call — and that is the path #01's redesign now gates. What remains is the manual route, which is the unlikely one. **The residual is the leftover of a closed risk, not a live one.**

Action: one sentence in `migrate()`'s docstring saying callers are responsible for serialising it. That is the honest contract, rather than one implying a safety it does not have. Nothing else.

**Verified**: `permission_migration.migrate()` has exactly two callers — `auto_migrate.run_auto_migration` (the hook path, now gated) and `scripts/migrate_permissions.py` (the CLI path the maintenance skill drives, human-initiated and therefore serialised by being one person). They share the function and nothing else, so the docstring sentence belongs on `migrate()` and covers both.

### If it ever does need a real lock

Arnon's suggestion, and it is the right size: an **OS file lock**. Advisory locking is sufficient here because every participant is toolguard — the weakness of Linux advisory locks is that they do not stop a non-cooperating process, and there isn't one. `~/.toolguard/` already exists as the natural home for the lockfile.

**Use `fcntl.flock`, not `fcntl.lockf`.** POSIX record locks (`lockf`) are dropped when *any* descriptor for that file is closed anywhere in the process, so an unrelated `open()`/`close()` of the same path silently releases the lock. `flock` is bound to the descriptor and has no such behaviour. Both are stdlib, so neither adds a runtime dependency. (`flock` over NFS is historically unreliable; irrelevant for a local `~/.toolguard`.)

Scope if built: one lock around a known pair of writes for a single project — not a general migration-concurrency problem.

**Portability, decided (Arnon, 2026-08-08):** `fcntl` is stdlib but Unix-only; the Windows stdlib equivalent is `msvcrt.locking`, which is mandatory rather than advisory. His call: *"it's a one function wrapper to support both, so it's a non-issue... We can support Windows for locking without declaring that we're windows-compatible."* So a two-branch wrapper, and no change to the project's tested-on-Linux-only claim.

## Decision needed

None. Closed.
