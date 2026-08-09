---
title: latest-code-review-report
type: report
tags:
- code-review
- TOO-45
permalink: latest-code-review-report
---

# Code review — TOO-45 punch-list #15 (migrate cross-process lock)

**Date: 2026-08-09, 14:0x local.** Scope: `toolguard/file_lock.py` (new), `toolguard/permission_migration.py` (modified), `test/unit/test_file_lock.py` (new), `test/unit/test_migration.py` (modified). Reviewer: code-reviewer subagent, isolated context.

## Summary

The lock primitive itself is well built and, unusually for concurrency code, actually proven: `flock` is chosen over `lockf` with the reason recorded, release-on-process-death is tested with a real `SIGKILL`, cross-process contention is exercised with real processes rather than asserted, and the Windows branch is reached by patching. The layer registration was done and `tools/architecture_fitness.py --layers` is clean. The problems are all on the *seam*, not the mechanism: `migrate()` now returns a third exit code, and the one library caller that branches on `!= 0` was not updated — which converts a "someone else is busy, try again" into a reported failure that burns the day's auto-migration slot. Two related seam issues (hook-path latency, a decline message that asserts a cause the reason may contradict) share the same root: the new outcome was given a code and a message but not a *place in the callers' vocabulary*.

Suite green (103 tests in the two modules, 4.7 s), `ruff check` and `ruff format --check` clean, architecture fitness clean.

---

## Critical

None.

---

## Major

### M1. `auto_migrate` reports a lock decline as a migration failure, and burns the day's slot

**File**: `/home/arnon/projects/toolguard/toolguard/auto_migrate.py:166-171` (caller not updated by this change)

`_migrate()` does `if exit_code != 0: report_warning("[TOOLGUARD AUTO-MIGRATION] Migration failed", "Check the migration's backup and settings.local.json, then retry.")`. With `MIGRATE_DECLINED_LOCKED = 2` this now fires when *nothing was attempted*:

- The message is wrong — nothing failed.
- The corrective step is unactionable — it points at a backup that was never created and a `settings.local.json` that was never touched.
- Worse, per `auto_migrate`'s own docstring (lines 77-85), **the once-per-day claim is deliberately not released on failure**, and `AUTO_MIGRATION.run(...)` claims the slot immediately before `_migrate()`. So a transient decline — e.g. the user happens to be running `toolguard-migrate` by hand at that moment — suppresses auto-migration for the rest of the day, with a message telling them to inspect a nonexistent backup.

This is not an oversight in scope: the coder task recall lists *"`migrate()` returns `int` exit code; callers branch on `!= 0`"* as a **given fact**, and `MIGRATE_DECLINED_LOCKED`'s own docstring says it exists so that *"a caller that wants to say 'someone else is already migrating' can"*. The code path was defined and then left unused by the only caller that could use it.

**Fix**: branch explicitly in `_migrate()`:

```python
if exit_code == MIGRATE_DECLINED_LOCKED:
    report_notice("[TOOLGUARD AUTO-MIGRATION] Another migration is in progress; skipping.")
    return False
```

and, because nothing was attempted, this is the one outcome where the day's claim *should* be released (or never taken) so the next invocation retries. That is a deliberate change to the D4 rule, not an accident — D4's argument was about a *failed* migration having no later same-day caller to retry against, which does not apply to a migration that never ran.

### M2. A 10-second lock wait now sits in the synchronous PreToolUse hook path

**File**: `/home/arnon/projects/toolguard/toolguard/permission_migration.py:62, 1194-1201`

`MIGRATE_LOCK_TIMEOUT_SECONDS = 10.0` is a module constant with no per-caller override. The path `hook._run_divergence_check` → `auto_migrate.run_auto_migration` → `migrate()` is the live permission hook, so under contention a user's tool call can stall for ten seconds before the hook decides anything. Ten seconds of patience is right for an interactive `toolguard-migrate`; it is wrong for an unattended daily migration whose correct response to contention is "not now".

**Fix**: `def migrate(..., lock_timeout_seconds: float = MIGRATE_LOCK_TIMEOUT_SECONDS)` and have `auto_migrate` pass something sub-second. Note the tests already need this knob and currently get it by `patch.object(permission_migration_module, "MIGRATE_LOCK_TIMEOUT_SECONDS", 0.2)` — patching a module constant to make a test fast is usually the design telling you the value wants to be a parameter.

### M3. The decline message asserts a cause that three of four reasons contradict

**File**: `/home/arnon/projects/toolguard/toolguard/permission_migration.py:1202-1208`

```python
except file_lock.LockUnavailable as e:
    report_warning(
        "Migration declined: another migration is already in progress "
        f"for this project ({e.reason}).",
        "Wait for the other migration to finish, then retry.",
    )
```

`LockUnavailable` has four reasons. Only `REASON_TIMEOUT` means another migration is in progress. For `REASON_NO_PRIMITIVE` (no `fcntl`, no `msvcrt`), `REASON_DIRECTORY_UNAVAILABLE` (`~/.toolguard/locks/` not creatable — read-only home, quota, a file in the way) and `REASON_FILE_UNAVAILABLE`, the lead sentence is simply false and the corrective step is unactionable: waiting will never help, and on `REASON_NO_PRIMITIVE` migration is *permanently* impossible on that machine while reporting a transient-sounding condition.

The structured `.reason` attribute exists precisely so the caller can branch, and here it is used only as decoration inside a sentence that has already asserted the wrong cause — the shape the project's own "prose is output, not a data structure" rule is aimed at.

**Fix**:

```python
if e.reason == file_lock.REASON_TIMEOUT:
    report_warning("Migration declined: another migration is already in progress for this project.",
                   "Wait for the other migration to finish, then retry.")
else:
    report_warning(f"Migration declined: exclusive access could not be guaranteed ({e.reason}).",
                   "Resolve the underlying condition, then retry; no files were modified.")
```

Also worth deciding deliberately whether `REASON_NO_PRIMITIVE` should decline at all, or proceed with a warning. Declining (fail closed) is defensible and is probably right — but it means a platform without either primitive can never migrate, and that deserves a sentence in the docs rather than being an emergent consequence.

---

## Minor

### N1. Exit code `2` collides with argparse's usage-error code in the same CLI

`toolguard/scripts/migrate_permissions.py` uses `argparse`, which exits **2** on an unrecognised flag. `MIGRATE_DECLINED_LOCKED = 2` therefore makes `toolguard-migrate --bogus` and "declined, locked" indistinguishable to any script branching on the exit code — which is the exact use case the constant's docstring names. Prefer `3`, or `os.EX_TEMPFAIL` (75), whose meaning is precisely "temporary failure, retry later".

### N2. The real timeout carries no `detail`, and the test pins the shape by hand

`file_lock.py:160` raises `LockUnavailable(path, REASON_TIMEOUT)` with no detail, while `test_file_lock.py:183-196` (`test_reason_is_structured_and_message_carries_detail`) constructs the exception itself with `"waited 10.0s"`. That test therefore verifies the constructor, not any behaviour the module produces — a shape test standing in for a behaviour test. Passing `f"waited {timeout_seconds}s"` at the raise site costs nothing, makes the operator-facing message actually useful, and lets the test observe real output.

### N3. Windows acquire/release asymmetry

`_release_windows` (`file_lock.py:96-102`) explicitly seeks to 0 before unlocking; `_try_acquire_windows` (87-93) relies on the offset being 0 implicitly. That holds today (fresh `os.open`, and `msvcrt.locking` does not move the pointer), so this is not a live bug — but the asymmetry reads as though one of the two knows something the other doesn't. Seek in both, or in neither with a one-line comment saying why.

### N4. Lock file and directory permissions

`file_lock.py:144,149` — `mkdir()` and `os.open(..., O_CREAT|O_RDWR)` take default modes, so the lock lands at `0o644` in a `0o755` directory. For state under `~/.toolguard/` a `0o600` file in a `0o700` directory is the conventional choice. This matches `once_per_store`'s existing behaviour, so it is a project-wide nit rather than a regression introduced here — but the new module is the natural place to set the precedent.

### N5. `REASON_*` values are English sentences used as machine-stable keys

`file_lock.py:43-46`. They are correctly named constants (per the project rule), but the *values* are display prose, which is why M3's message reads awkwardly when interpolated. Short tokens (`"timeout"`, `"no_primitive"`, ...) plus a separate display mapping at the edge would carry the same information, make branching read better, and make M3's fix fall out naturally.

### N6. The concurrency test can silently degrade to a sequential run

`test_migration.py:1560` — `time.sleep(0.3)` then `barrier.touch()` assumes both children have started and reached the polling loop within 300 ms. If one child is slow to import (cold cache, loaded machine), the barrier already exists when it arrives and it simply runs alone. The assertions are on the *end state*, which holds either way, so the test passes without ever having exercised contention. Not flaky — worse, quietly vacuous under load.

Consider having each child print how long its lock acquisition blocked and asserting that at least one waited a non-trivial interval; that turns "both patterns survived" into "both patterns survived *and* the lock actually did something".

### N7. Test patches the shared module attribute

`test_migration.py:1414` patches `permission_migration_module.file_lock.exclusive` — that is the attribute on the shared `toolguard.file_lock` module object, not a `permission_migration`-local name, so the patch is global for its duration. Harmless in this suite; `patch("toolguard.permission_migration.file_lock.exclusive")` reads the same and has the same effect, so this is really a note that the module-object import style makes the scope ambiguous at a glance.

---

## Suggestions

### S1. Fourth copy of the subprocess test harness

`test_once_per_store.py:307`, `test_config_divergence.py:991`, `test_file_lock.py:244`, `test_migration.py:1551,1641,1649` all hand-roll the same pattern: build a child script as a string, `subprocess.Popen([sys.executable, "-c", script, ...], cwd=repo_root, ...)`, poll a marker/barrier file with a monotonic deadline, `communicate(timeout=...)`, assert `returncode == 0` with `stderr` as the message. `test_file_lock.py` even documents that it is "following `test_once_per_store.py`'s harness" — the duplication is deliberate and acknowledged, which is the right moment to extract it.

A small `test/unit/_subprocess_harness.py` with `run_child(script, *args, env=None)` and `wait_for_marker(path, timeout)` would remove the copies and give one place to fix the deadline/timeout constants. The child scripts themselves stay per-test, as they should.

### S2. `~/.toolguard` derivations are now at seven, and one of them is import-time

The spec correctly told the coder not to consolidate, and this review is not reopening that. But the count is now: `error_log.py:169`, `once_per_store.py:199`, `permission_migration.py:98`, `tools/decision_ledger.py:44`, `tools/installer.py:163`, `config.py:444`, `testing/sandbox.py:322,345`.

Worth pulling out for the follow-up ticket: **`tools/decision_ledger.py:44` evaluates `Path.home()` at module import** (`USER_LEDGER_PATH = Path.home() / ".toolguard" / "decisions.json"`). That is exactly the failure `_migration_lock_path`'s docstring warns against ("resolved here, at call time, never at module import"), and it is the one derivation that would silently ignore a `HOME` set for a subprocess or a patched `Path.home()` in a test. The new module documents the rule; the ticket should name the one site that breaks it.

### S3. The lock excludes migrate-vs-migrate only

`tools/rule_apply.py:195-197` and `tools/maintenance.py:844` write the same toolguard config files without participating in this lock. That is faithful to the ticket, which was scoped to `migrate()`'s own read-modify-write, so it is not a defect. But the lock is *named and keyed* `migrate-<sha>`, which makes widening it later a rename-and-migrate rather than a one-line change. If widening is plausible, `config-<sha>` costs nothing today.

### S4. Two notions of "project identity" now coexist, and they are observably different

`_migration_lock_path` keys on `sha256(str(project_root.resolve()))`; `once_per_store._project_key` keys on `str(project)` unresolved. Both choices are individually defensible and the divergence is documented in the docstring and pinned by a test — good. The consequence worth writing into the follow-up ticket is that these two mechanisms **guard the same operation**: reaching `migrate()` through a symlinked project path yields the *same* lock but a *different* daily claim. The combination is the only place the divergence is visible, and it is precisely the auto-migration path.

---

## Architectural drift pass

A ticket ID was given, so this pass ran; the change set is small, and nothing here is alarming.

- **Blast radius vs. conceptual size**: one concept ("migrate needs mutual exclusion") landed in 1 new production file + 1 modified production file + 1 config line. Proportionate; no smearing across unrelated modules.
- **Architectural home for the new file**: `file_lock` is declared in `.pyscn.toml`'s `foundation` layer, and `tools/architecture_fitness.py --layers` reports both completeness ("All modules map to exactly one layer") and direction clean. This is the check that most often degrades silently, and it was done.
- **Boundary crossings**: none. `config` → `observability` (`error_reporter`) and `config` → `foundation` (`file_lock`) are both downward and legal.
- **Test cost trend**: this change is ~675 test lines to ~275 production lines (2.45:1) against a repo standing ratio of ~64.7k test to ~34.3k production (1.9:1). Above the norm but justified — the extra weight is real multi-process tests, which is the only way to test this at all, not representation-pinning. Not a flag.
- **Logical coupling**: not computed; two files is below the threshold where co-change analysis says anything.

The one drift signal worth naming is not structural but *vocabulary*: `migrate()`'s return type is an `int` exit code that three call sites interpret differently (CLI passthrough, `auto_migrate`'s `!= 0`, and now a third value with its own meaning). M1 is the first bug caused by that, and it will not be the last. A small result object or `enum` — `MigrationOutcome.{OK, FAILED, DECLINED_LOCKED}` — rendered to an exit code only at the console-script edge would make the caller's `!= 0` impossible to write by accident. That is the project's own "carry structured data, render at the edge" rule applied to a return value rather than a message.

---

## What is good here, specifically

Worth saying, because these are the parts that usually get skipped:

- **`flock` over `lockf`, with the reason in the docstring.** The record-lock footgun (any `close()` on the path in the process drops the lock) is real, obscure, and would have been found only in production. Naming it in the module docstring is what stops someone "simplifying" it later.
- **Release on process death is tested, not asserted.** `test_lock_released_when_holding_process_dies` actually `SIGKILL`s a holder and re-acquires. That is the entire justification for not using an `O_EXCL` lockfile, and it is verified rather than argued.
- **The dry-run exclusion and the lock's span are both justified in the docstring**, including the specific reason locking only the write would be insufficient (stale read → overwrite). That is the non-obvious part, and it is the part that got written down.
- **The Windows branch is exercised**, on a Linux-only suite, by a small deliberate fake rather than being left as an untested platform assumption.