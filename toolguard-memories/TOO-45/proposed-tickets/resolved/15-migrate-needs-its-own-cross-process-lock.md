---
title: 15-migrate-needs-its-own-cross-process-lock
type: note
permalink: toolguard/too-45/proposed-tickets/15-migrate-needs-its-own-cross-process-lock
---

**FIXED in `05f786d` (TOO-45 phase 2).** `migrate()` now takes a per-project OS file lock (flock/msvcrt) — see `toolguard/file_lock.py:69-105` and `test/unit/test_file_lock.py`.

# `migrate()` needs mutual exclusion of its own

**Status:** ACCEPTED for TOO-45 (Arnon, 2026-08-08). The implementable ticket; the reasoning that produced it is in `15-once-per-period-cannot-express-must-not-run.md`.

## Problem

`permission_migration.migrate()` performs a read-modify-write across two files — `.claude/settings.local.json` and the project's toolguard config. Each individual write is atomic (temp file, `fsync`, `os.replace`), so there is no torn file, but **nothing serialises the read-modify-write**. Two concurrent migrations of the same project can each read the pre-migration state and each write a result, and last-writer-wins silently discards one process's migration of the permission rules.

It has **two callers**:

- `auto_migrate.run_auto_migration` — the automatic path, reached from the hook. **Already safe**: punch-list #01 made it decline to run at all unless it holds a once-per-day claim, so it is serialised by something else.
- `toolguard/scripts/migrate_permissions.py` — the CLI path the maintenance skill drives. **Not serialised by anything.**

So `migrate()` is safe today by accident of who calls it, not by any property of its own. A future caller reintroduces the race with nothing to catch it, and the function's contract promises a safety it does not have.

## Requirement

`migrate()` serialises itself. A caller should not have to know that concurrent migration is unsafe, and should not have to arrange the exclusion — the current arrangement is exactly the "mechanism has no vocabulary, so the caller improvises" shape this ticket series keeps finding.

**An OS advisory file lock.** Advisory is sufficient because every participant is toolguard; the classic weakness of advisory locks is a non-cooperating process, and there isn't one.

**Stdlib only** — this is a runtime dependency-free project.

- POSIX: **`fcntl.flock`, not `fcntl.lockf`.** POSIX record locks (`lockf`) are released when *any* descriptor for that file is closed anywhere in the process, so an unrelated `open()`/`close()` of the same path silently drops the lock. `flock` is bound to the descriptor and has no such behaviour.
- Windows: `msvcrt.locking`, which is mandatory rather than advisory.
- **One wrapper function over both.** Arnon: *"it's a one function wrapper to support both, so it's a non-issue... We can support Windows for locking without declaring that we're windows-compatible."* The project's tested-on-Linux-only claim does not change.

**Lockfile under `~/.toolguard/`** — toolguard's own state, not project data, consistent with where the once-per store landed in #01.

The lock is **per project**: two different projects migrating at once is fine and must not block.

## Severity, stated honestly

**Low.** Reaching the damage requires two concurrent *manual* migrations of the *same* project, migrating *different* things — identical concurrent migrations converge harmlessly. Arnon's own assessment: *"possible, yes. Likely — not very."*

**It is being built anyway, and the reason is methodological.** It is narrow, well-specified, unlikely to have its requirements reversed mid-flight, and has a known blast radius — which makes it the control case this measurement series has been missing. #05's ticket named its own target files, so predicting them was partly transcription; #01 and #04 both moved under their own estimates.

## Failure behaviour to decide and state

What happens when the lock cannot be acquired is part of the design, not an afterthought:

- Another process holds it — the honest answer is almost certainly "wait briefly, then decline and say so", not "wait forever" and not "proceed anyway".
- The lock cannot be created at all (no `~/.toolguard`, read-only home, `fcntl` and `msvcrt` both absent on some exotic platform). Note that "proceed without the guarantee" is the wrong default for this caller specifically — it is the exact failure direction #01 had to correct.

Whatever is chosen, the caller learns about it through the error reporter built in #04, not through a bare stderr write.

## Verification

- Two real concurrent processes, both migrating the same project, both writing — assert no lost update. A test that only exercises the lock's happy path in one process proves nothing.
- Two processes migrating *different* projects do not block each other.
- The lock is released on exception, not only on success.
- The lock is released when the process dies (this is why `flock` and not a hand-rolled `O_EXCL` lockfile, which strands on a crash).
