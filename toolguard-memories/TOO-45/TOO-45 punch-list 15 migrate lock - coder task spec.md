---
title: TOO-45 punch-list 15 migrate lock - coder task spec
type: note
permalink: toolguard/too-45/too-45-punch-list-15-migrate-lock-coder-task-spec
tags:
- task-memory
- TOO-45
---

# TOO-45 punch-list #15 — `migrate()` serialises itself

Ticket: `toolguard-memories/TOO-45/proposed-tickets/15-migrate-needs-its-own-cross-process-lock.md`. Read it first.

## Facts established before writing this spec, so you don't re-derive them

| question | answer |
|---|---|
| Any existing OS lock in the package? | **None.** `fcntl`, `msvcrt`, `flock`, `O_EXCL` appear nowhere. `once_per_store` has `BEGIN IMMEDIATE`, but that is a sqlite transaction, not a lock held across a long operation. |
| Shared `~/.toolguard` resolver? | **No — five independent derivations** (`once_per_store`, `decision_ledger`, `error_log`, `config`, `testing/sandbox`). See "Do not fix this here" below. |
| `migrate()`'s return shape? | `-> int`, an exit code. Callers branch on `!= 0`. |
| Real concurrent-process test harness? | **Yes** — `test/unit/test_once_per_store.py` already spawns real processes; follow it. |
| Platform-gating pattern (`sys.platform`)? | **None anywhere.** This is new ground. |
| Does anything enumerate `~/.toolguard` by filename? | **No.** `self_integrity` matches the `.toolguard` substring, so a new file needs no registration. |
| Project keying in `once_per_store`? | `_project_key` is `str(project)` — no `.resolve()`, no hash. See below. |

## 1. `toolguard/file_lock.py` — new module, `foundation` layer

Declare it in `.pyscn.toml`'s foundation packages list. The completeness check fails if you forget.

One public context manager:

```python
with file_lock.exclusive(path, timeout_seconds=...):
    ...
```

- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`, polled until the timeout expires. **`flock`, never `lockf`** — POSIX record locks are released when *any* descriptor for that file is closed anywhere in the process, so an unrelated `open()`/`close()` silently drops the lock. `flock` is bound to the descriptor.
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)`. Import gated so a missing module on either platform is not an import-time crash.
- Released by closing the descriptor, so the OS releases it if the process dies. **Do not** hand-roll an `O_EXCL` lockfile — that strands on a crash, which is the whole reason to use the OS.

**One failure mode, and it fails closed.** Raise `LockUnavailable(reason)` when the lock cannot be *guaranteed*, whatever the cause: the timeout expired, `fcntl` and `msvcrt` are both absent, the directory is unwritable, `Path.home()` cannot be resolved. Do not distinguish "busy" from "broken" in the exception type — a caller that must not proceed cannot act on the difference, and offering it invites someone to proceed on the wrong branch. That mistake is what punch-list #01 had to unwind.

Carry the reason as **structured data on the exception**, not only in its message. The caller renders prose; it must not parse it.

## 2. `migrate()` takes the lock around its read-modify-write

Lock path: `~/.toolguard/locks/migrate-<key>.lock`, where `<key>` is a filesystem-safe digest of the **resolved** project root (`Path.resolve()` then hash, first 16 hex chars is plenty). Create `locks/` on demand; that is toolguard's own directory, so creating it is fine — unlike a project's `logs/`.

**Note the deliberate divergence and document it in one line:** `once_per_store._project_key` uses `str(project)` with no `.resolve()`, so two spellings of the same project key differently there. The lock resolves, because mutual exclusion is about the real directory. This is the lock being more correct, not an inconsistency to copy. Flag it in your report as a possible defect in `once_per_store`; **do not change `once_per_store` here.**

Scope the lock to the read-modify-write only — the phase that loads sources and the phase that writes. A dry run does not write and should not need the lock; decide and state which.

## 3. Expressing "declined because another migration holds the lock"

`migrate()` returns an `int`. Add a **named module-level constant** for this outcome — not a bare literal, and not a message string a caller has to parse. It must be distinguishable from ordinary failure: a caller that treats every non-zero as failure stays correct, and one that wants to say "someone else is already migrating" can.

Report it through `error_reporter` (`report_warning`), never a bare stderr write.

## 4. Fix the stale layer-order comment in `.pyscn.toml`

Line ~157 reads:

```
#   foundation  <-  config  <-  engine  <-  api  <-  runtime  <-  tooling  <-  support
```

`observability` is missing. The machine-readable `[[architecture.rules]]` stanzas in the same file *do* include it, so the prose contradicts the config beside it. Found by the blind estimator from the file inventory alone. One-line fix; you are editing this file anyway.

## 5. Do NOT fix these here — report them instead

- **The five independent `~/.toolguard` derivations.** Your lock will be the sixth. Converting the others touches the test-isolation seams that guard the developer's real home — the machinery that caught real bugs in #01 — and that is not a change to make as a side effect of a locking ticket. Derive it locally like its neighbours and name the consolidation as a follow-up.
- `once_per_store._project_key`'s missing `.resolve()`.
- Anything else you trip over.

## Constraints

- **Stdlib only.** No new runtime dependency.
- `unittest` under `test/`, run with `uv run python -m unittest discover -s test -t .`. Not pytest.
- `uv run ruff format .` and `uv run ruff check .` before reporting.
- Doc comments 1-5 lines. No ticket narrative in code.
- Any string or number the code **branches on** is a named constant.

## Verification — a single-process happy-path test proves nothing

- **Two real concurrent processes migrating the same project, both writing: assert no lost update.** Follow `test/unit/test_once_per_store.py`'s existing subprocess harness rather than inventing one.
- Two processes migrating **different** projects do not block each other.
- The lock is released on an exception inside the block, not only on success.
- The lock is released when the holding process **dies** (kill it and show a second process can acquire).
- `LockUnavailable` is raised, and `migrate()` returns the declined code, when the lock is already held.
- The Windows branch cannot run here. Exercise it by patching, and keep that scaffold as small as you can — an elaborate patching harness is usually the most fragile new code in a change like this.
- Existing suite green (2685 at last count), `uv run python tools/architecture_fitness.py --layers` clean.

## Process

This repo's CLAUDE.md — and now the global one — require an intent disclosure before any Bash command carrying logic **you** authored: heredocs, `python -c`, scratch scripts, **and authored shell** (`sed -e`/`-i`, `awk`, `for`/`while` loops). Emit the `# INTENT:` / `# TOUCHES:` / `# INLINE BECAUSE:` block and prefix with `TG_INTENT=1`, or `TG_ATTEST_READONLY=1` when every leaf is read-only. Required even when the command will be blocked — the disclosure feeds after-the-fact analysis, not just the approval prompt.

## Report

Include: the dry-run decision from §2; whether the lock scope is the whole of `migrate()` or a narrower phase, and why; the follow-ups from §5; and a duplication self-check against `once_per_store`, `error_log` and `path_utils` confirming the lock is not a fourth copy of something.
