---
title: TOO-45 punch-list 15 migrate lock - coder implementation report
type: note
permalink: toolguard/implementation/too-45-punch-list-15-migrate-lock-coder-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Implemented an OS advisory file lock (`toolguard/file_lock.py`, new foundation-layer module) and wired `permission_migration.migrate()` to hold it around its read-modify-write, closing the concurrent-migration lost-update race named in TOO-45 punch-list #15.

## Files changed

New:
- `toolguard/file_lock.py` -- `exclusive(path, *, timeout_seconds=)` context manager. POSIX `fcntl.flock(LOCK_EX|LOCK_NB)` polled to timeout; Windows `msvcrt.locking(LK_NBLCK, 1)` with explicit unlock before close (POSIX release is a documented no-op -- flock is bound to the fd and releases on close/process death). Single exception `LockUnavailable(path, reason, detail="")` -- one failure mode, `reason` is a named `REASON_*` constant (structured data, not just message text), matching `config_write_guard.ConfigWriteVerificationError`'s `.reason`/detail convention.
- `test/unit/test_file_lock.py` -- 14 tests: in-process acquire/release/timeout/exception-release, every `LockUnavailable` failure mode (no primitive, unwritable directory, lock path is a directory), the Windows branch via a small `_FakeMsvcrt` double, and 3 real-subprocess tests (contention/decline, independent paths, release on `SIGKILL`).

Modified:
- `toolguard/permission_migration.py` -- added `MIGRATE_LOCK_TIMEOUT_SECONDS`, `MIGRATE_DECLINED_LOCKED = 2`, `_migration_lock_path(project_root)` (`~/.toolguard/locks/migrate-<sha256(resolve())[:16]>.lock`). Split `migrate()`'s body into `_run_migration(...)`; `migrate()` itself now only handles the early "nothing to migrate" exit and the lock. Reports a decline via `error_reporter.report_warning`, never stderr.
- `test/unit/test_migration.py` -- added `TestMigrationLocking` (3 in-process tests: dry run never locks, declines with the named code + reports via `report_warning` + settings untouched, lock key uses `.resolve()`) and `TestMigrationLockingAcrossProcesses` (2 real-subprocess tests: two processes migrating *different* patterns concurrently both land correctly with neither lost, and a second process declines while a first holds the lock).
- `toolguard/scripts/migrate_permissions.py` -- one-line docstring fix on `main()`'s `Returns:` (now mentions `MIGRATE_DECLINED_LOCKED`; was stale "0 or 1" after this change, doc-drift sweep item).
- `.pyscn.toml` -- added `file_lock` to the foundation layer's `packages` list; fixed the stale layer-order comment (was missing `observability` between `foundation` and `config`, contradicting the `[[architecture.rules]]` stanzas right below it).

## Report items requested by the spec

**1. Dry-run lock decision:** dry runs never take the lock. `migrate()` branches before acquiring: `dry_run=True` calls `_run_migration(...)` directly. Justification: a dry run performs no write, so there is nothing to protect from a lost update, and taking the lock anyway would only add contention with zero safety benefit. Verified with `test_dry_run_never_takes_the_lock`, which patches `file_lock.exclusive` to raise if called at all.

**2. Lock scope:** the whole read-modify-write inside `_run_migration` -- load (`_load_migration_sources`) through write (`_apply_migration`) -- not just the write. Locking only the write would still let a second process's `find_divergent_patterns`/`find_redundant_patterns` compute against a first process's now-stale read, then overwrite what the first process just wrote (the first process's write-time re-read in `_build_merged_permissions` closes that specific race only when it happens *after* the other writer released the lock; without the lock spanning the load too, two writers can each read stale state before either writes). Confirmed empirically: I temporarily made the lock key process-specific (defeating cross-process exclusion) and re-ran `test_two_concurrent_migrations_of_different_patterns_lose_neither` -- it failed exactly as expected (`Bash(p2:*)` missing from the written config), then reverted the change and confirmed the suite passes again. This is in the report rather than left as a comment because it was a throwaway validation step, not a permanent test.

**3. Follow-ups reported, not fixed (per spec's explicit instruction):**
- The lock is the **6th** independent `~/.toolguard` derivation (`once_per_store`, `decision_ledger`, `error_log`, `config`, `testing/sandbox`, now `file_lock`/`permission_migration._migration_lock_path`). All resolve `Path.home() / ".toolguard" / ...` independently. A shared resolver would be a reasonable follow-up but touches the test-isolation seams (`ConfigIsolationMixin`, the real-log-dir/real-once-per-home guards) that caught real bugs during punch-list #01 -- not something to fold into a locking ticket.
- `once_per_store._project_key` still uses `str(project)` with no `.resolve()` -- confirmed unchanged (`git status` shows no diff to `once_per_store.py`). The lock's own key deliberately DOES resolve (documented in `_migration_lock_path`'s docstring) since mutual exclusion is about the real directory, not a string spelling.
- Nothing else new was tripped over during this change.

**4. Duplication self-check:**
- `once_per_store`: different mechanism (sqlite claim store for "once per period" throttling with expiry), not a mutual-exclusion primitive -- confirmed via `grep -rl "def exclusive\|flock\|LOCK_EX\|msvcrt"` across `toolguard/` and `tools/`: only the new `file_lock.py` matches. No existing OS lock anywhere, matching the spec's stated fact.
- `error_log`/`decision_ledger`: both just resolve `Path.home() / ".toolguard" / <name>` for a *file path*; neither provides locking. `file_lock.py` is a new capability, not a re-implementation of an existing one.
- `path_utils`: project-root resolution only, no relation to locking; `_migration_lock_path` uses `project_root.resolve()` directly rather than routing through `path_utils`, since it needs the literal resolved directory of an already-known `project_root`, not root *discovery*.
- No stdlib module already provides cross-process advisory locking as a portable one-liner (the `fcntl`/`msvcrt` split genuinely needs the wrapper the spec asked for).

## Self-review

- `uv run ruff format .` / `uv run ruff check .`: clean.
- `uv run python -m unittest discover -s test -t .`: 2704 tests, OK (2685 baseline + 19 new: 14 in `test_file_lock.py`, 5 in `test_migration.py`).
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both clean.
- Anti-pattern scan: no async/await, no threading, no local (in-function) imports in any new/changed production file. The `try: import fcntl / except ImportError` pattern in `file_lock.py` is a module-level conditional import (matches `once_per_store`'s `try: import sqlite3` convention exactly), not a local-import violation.
- No `.py` syntax errors (`py_compile` on all 4 touched/new files).
- Confirmed via `git status` that `once_per_store.py` and all other pre-existing `~/.toolguard` derivations were left untouched, per the spec's explicit "do not fix here" instruction.

## Deviations from the spec

None. One thing worth flagging: the spec's own fact table said "no `sys.platform` gating pattern exists anywhere" -- confirmed, and I didn't introduce one either; the platform selection in `file_lock.py` is via `try/except ImportError` on `fcntl`/`msvcrt` (feature detection), never `sys.platform`, which is also what makes the Windows branch testable via patching on Linux.

## Elapsed time / cost (estimated)

- Phase 1 (planning: read spec, ticket, surveyed `permission_migration.py`, `once_per_store.py`, `error_reporter.py`, `path_utils.py`, `.pyscn.toml`, `architecture_fitness.py`, test harness precedent): ~25 min.
- Phase 2 (implementation: `file_lock.py`, `.pyscn.toml` edits, `permission_migration.py` split + lock wiring, smoke test): ~20 min.
- Phase 2b (test writing: `test_file_lock.py` 14 tests, `test_migration.py` 5 tests, the regression-validation exercise): ~25 min.
- Phase 3 (self-review: full suite runs, ruff, architecture fitness, doc-drift sweep, duplication check, report writing): ~15 min.
- Total: roughly 85 minutes of wall-clock work.
- Cost estimate (Sonnet 5, this session's token volume -- moderate: several large file reads, two new files, two edited files, one full test-suite run per verification pass at ~45-48s each): roughly $2-3 in API-equivalent terms. This is a rough order-of-magnitude estimate, not a metered figure.


---

## Fix pass (2026-08-09, code review follow-up)

Full review: `toolguard-memories/latest-code-review-report.md`. This pass addressed every Major
and the two Minor items the punch-list prompt named explicitly, all on the seam between
`file_lock`/`permission_migration` and their callers -- the lock primitive itself was not
touched and needed no changes.

### What changed, by item

**1. `auto_migrate._migrate()` no longer reports a lock decline as a failure.**
`exit_code == MIGRATE_DECLINED_LOCKED` is now branched explicitly, before the generic
`!= 0` check: reports via `report_notice` ("Another migration is already running for this
project; skipping"), not `report_warning`, and returns `False` without the misleading
"check the backup" advice. Per the punch-list prompt's explicit instruction (which overrides
the review's own M1 suggestion), the once-per-day claim is **deliberately not released** --
the other process holding the lock is doing the work, so there is nothing to retry. That
decision is now a one-line doc comment at the branch, not left implicit.

**2. `migrate()` gained a `lock_timeout_seconds` parameter** (default
`MIGRATE_LOCK_TIMEOUT_SECONDS = 10.0`, unchanged, for the interactive CLI).
`toolguard.auto_migrate` now defines its own `AUTO_MIGRATE_LOCK_TIMEOUT_SECONDS = 1.0` and
passes it explicitly, with a one-line justification: the hook path is synchronous and
user-facing, so a contended lock should decline fast rather than stall the tool call.

**3. The decline message now branches on `LockUnavailable.reason`.** Only
`REASON_TIMEOUT` gets "another migration is already in progress" + "wait and retry"; the
other three reasons (`REASON_NO_PRIMITIVE`, `REASON_DIRECTORY_UNAVAILABLE`,
`REASON_FILE_UNAVAILABLE`) get "exclusive access could not be guaranteed (\<reason\>)" +
"resolve the underlying condition, then retry; no files were modified" -- no longer asserting
a cause the reason contradicts.

**4. `MIGRATE_DECLINED_LOCKED` changed from `2` to `3`.** `2` collided with argparse's own
usage-error exit code in the same CLI (`migrate_permissions.py`). Picked a plain int rather
than `os.EX_TEMPFAIL` (75) because that constant is POSIX-only and this module has a real
Windows branch.

**5. The cross-process migration test's barrier release is now deterministic**, not a
`sleep(0.3)` guess. Each child touches its own "ready" marker immediately before entering its
busy-wait loop on the barrier; the parent waits for ALL ready markers (via the new harness's
`release_barrier_when_ready`) before touching the barrier, so a slow-to-start child can no
longer make the test silently degrade to a sequential run while still passing. Applied to
`test_migration.py`'s `test_two_concurrent_migrations_of_different_patterns_lose_neither`
(the one the review named).

**6. Extracted `test/unit/_subprocess_harness.py`** (`run_child`, `wait_for_path`,
`release_barrier_when_ready`) and retrofitted **all four** duplicate sites the review named:
`test_file_lock.py`, `test_migration.py`, `test_once_per_store.py`, and
`test_config_divergence.py`. The latter two had the identical `sleep(0.3)`-then-touch
degradation risk as item 5's flagged test, not individually named by the review but sharing
the same fix mechanically as part of the same extraction -- touching those exact lines for
dedup and leaving the same latent flakiness in place would have missed the point of
extracting a shared, correct primitive. Child scripts themselves stayed per-test (they run in
a separate process; the shared module only handles launch/poll/communicate plumbing).

**Also fixed (the two named one-liners):**
- **N2**: the real `LockUnavailable(path, REASON_TIMEOUT)` raise now carries
  `detail=f"waited {timeout_seconds}s"`, so `test_file_lock.py`'s
  `test_nested_acquire_on_same_path_times_out` observes real output instead of only the
  hand-constructed-exception test pinning the shape.
- **N3**: `_try_acquire_windows` now seeks to 0 before `msvcrt.locking(..., LK_NBLCK, ...)`,
  matching `_release_windows`'s existing explicit seek -- acquire and release are symmetric.

### Explicitly not done (per the prompt's "Do NOT do" list)

- No conversion of `migrate()`'s `int` exit code to an outcome enum -- confirmed still
  returns a plain `int`; recorded as a follow-up, not implemented.
- `tools/decision_ledger.py:44`'s import-time `Path.home()` -- confirmed untouched
  (`git diff --stat -- tools/decision_ledger.py` is empty).

### New/changed tests

- `test_auto_migrate.py`: new
  `test_run_auto_migration_declined_locked_reports_a_notice_not_a_failure` -- asserts a
  notice (not "Migration failed") reaches stderr, `False` is returned, and the day's claim
  remains held (`HELD_BY_SOMEONE_ELSE` on a follow-up `claim()` call) -- i.e. genuinely
  verifies the claim was NOT released. `test_run_auto_migration_custom_backup_dir`'s
  `assert_called_once_with` updated to include the new `lock_timeout_seconds=` kwarg (the
  production call site legitimately changed shape; the test's own expectations were not
  weakened, just kept in sync).
- `test_migration.py`: new
  `test_declined_message_names_the_real_reason_for_a_non_timeout_decline` (item 3);
  `test_declines_with_named_code_when_lock_already_held` and
  `test_second_process_declines_while_first_holds_the_lock` updated to pass
  `lock_timeout_seconds=` explicitly instead of `patch.object(module, "MIGRATE_LOCK_TIMEOUT_SECONDS", ...)`
  -- that patch pattern silently stopped working once the value became a function-default
  parameter (Python binds defaults at def time, not per-call), which is exactly the design
  smell the review named; the fix is the parameter itself plus updating the two tests that
  relied on the old patch.
- `test_file_lock.py`: `test_nested_acquire_on_same_path_times_out` now also asserts the
  detail/message carry the real wait duration (N2);
  `test_successful_lock_calls_locking_and_unlocking_before_close` now also asserts
  `os.lseek` was called at least twice (N3, acquire+release symmetry).
- New `test/unit/_subprocess_harness.py` (item 6).

### Verification

- `uv run python -m unittest discover -s test -t .`: **2706 tests, OK** (was 2704; +2 new
  regression tests, no existing test weakened or deleted).
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both
  clean.
- `uv run ruff format .` / `uv run ruff check .`: clean.
- **Re-validated item 5's fix genuinely detects the race it claims to**: temporarily made
  `_migration_lock_path` PID-specific (defeating cross-process exclusion) and reran
  `test_two_concurrent_migrations_of_different_patterns_lose_neither` 8 times --
  5 of 8 failed (a lost-update race is not deterministic every run; the earlier pass's own
  validation saw the same pattern). Reverted, confirmed `git diff` clean of the temporary
  change, then reran the same test plus its sibling 5 times each with the real lock --
  100% pass, no flakiness introduced by the new deterministic barrier release.
- Also reran the two retrofitted concurrency tests (`test_once_per_store.py`,
  `test_config_divergence.py`) 3 times each for stability after the harness swap -- all
  passed.

### Self-review

- Anti-pattern scan (async/await, threading, function-local imports) across all touched
  files: none found. `file_lock.py`'s existing `try: import fcntl` / `try: import msvcrt`
  are module-level conditional imports (pre-existing from the prior pass, matching
  `once_per_store`'s own convention), not function-local imports.
- `py_compile` clean on all touched files.
- Doc-drift sweep: grepped the whole repo (code, `technical-notes.md`, `docs/*.md`,
  `README.md`) for stale references to the old `MIGRATE_DECLINED_LOCKED = 2` value or
  "declined... in progress" wording. The only hit outside this session's own memory notes
  and the review report (both historical records, left as-is) was `technical-notes.md:1137`,
  which is Claude Code's own `PreToolUse` hook exit-code-2 contract -- a genuinely different
  "2", unrelated to this constant. No doc changes needed.

### Files touched this pass

Modified: `toolguard/auto_migrate.py`, `toolguard/permission_migration.py`,
`toolguard/file_lock.py`, `test/unit/test_auto_migrate.py`, `test/unit/test_migration.py`,
`test/unit/test_file_lock.py`, `test/unit/test_once_per_store.py`,
`test/unit/test_config_divergence.py`. New: `test/unit/_subprocess_harness.py`. Nothing under
`toolguard/scripts/migrate_permissions.py` or `.pyscn.toml` needed further changes this pass
(both already correct from the prior pass; docstrings there don't cite a literal exit-code
number).

### Elapsed time / cost (estimated)

- Phase 1 (read review, task spec, prior report, surveyed current `file_lock.py`,
  `permission_migration.py`, `auto_migrate.py`, and all 4 test files' existing subprocess
  patterns; wrote task recall): ~20 min.
- Phase 2 (implementation: items 1-6, N2, N3, across 8 modified files + 1 new harness
  module): ~30 min.
- Phase 3 (verification: full suite runs x3, ruff, architecture fitness, the lock-defeat
  re-validation with 13 extra subprocess-test runs, doc-drift sweep, report writing):
  ~15 min.
- Total: roughly 65 minutes of wall-clock work.
- Cost estimate (Sonnet 5, moderate token volume -- several large file reads across 4 test
  files with duplicated patterns, multiple full-suite runs at ~47s each, one 13-run
  subprocess validation loop): roughly $1.5-2.5 in API-equivalent terms. Rough
  order-of-magnitude, not metered.


---

## Final item (2026-08-09): migrate() outcome-type refactor

The prior fix pass explicitly deferred converting `migrate()`'s bare `int` return to an
outcome type ("recorded as a follow-up, not implemented"). Arnon asked why it was being
deferred; the deferral reasoning didn't hold up, so this pass does it, folded into
punch-list #15 rather than a new ticket.

### What changed

**`toolguard/permission_migration.py`**: added `MigrationOutcome(Enum)` --
`SUCCEEDED` / `FAILED` / `DECLINED_LOCKED`, one member per `return` statement `migrate()`
actually had (no invented outcomes). Its `.exit_code` property looks up a single module-level
`_EXIT_CODES: Dict[MigrationOutcome, int]` table, in the same shape as
`error_reporter._ROUTING` (Arnon's own named precedent for "one table to read, one place to
change"). `DECLINED_LOCKED` keeps its numeric value **3** in that table, carrying forward the
prior pass's reasoning (avoids colliding with argparse's usage-error code 2 in the same CLI)
unchanged -- only its representation moved from a bare module constant
(`MIGRATE_DECLINED_LOCKED = 3`) to a mapping entry. `migrate()`'s signature now returns
`MigrationOutcome`; its three `return` sites were updated to return enum members, with a new
2-line private helper `_outcome_from_run_migration_result(result: int) -> MigrationOutcome`
converting `_run_migration`'s still-`int` 0/1 return at the two call sites that delegate to
it. `_run_migration` and `_apply_migration` themselves were **not touched** -- confirmed via
`git diff` showing zero changes inside either function -- per the explicit "do not restructure
migrate()'s internals" instruction; the int-to-enum translation lives entirely in `migrate()`
and the one helper next to it.

**`toolguard/auto_migrate.py`**: `_migrate()`'s local var renamed `exit_code` -> `outcome`;
both branches now compare by identity against `MigrationOutcome` members
(`outcome is MigrationOutcome.DECLINED_LOCKED`, `outcome is not MigrationOutcome.SUCCEEDED`)
instead of `== MIGRATE_DECLINED_LOCKED` / `!= 0`. Behaviour unchanged -- same two branches,
same notice/warning wording, same "claim stays consumed" comment.

**`toolguard/scripts/migrate_permissions.py`**: `main()`'s final `return migrate(...)` gained
`.exit_code` -- now the *only* place in the whole call chain where an outcome becomes an int.
Docstring updated to describe the conversion explicitly instead of describing `migrate()` as
if it already returned an int.

### Tests

`test/unit/test_migration.py`: import swapped `MIGRATE_DECLINED_LOCKED` -> `MigrationOutcome`.
15 `exit_code = migrate(...)` / `self.assertEqual(exit_code, 0)` sites renamed
`outcome` / `MigrationOutcome.SUCCEEDED` (done via a small, disclosed, line-targeted rewrite
script -- reviewed via `git diff` after, no duplication). 2 sites comparing against
`MIGRATE_DECLINED_LOCKED` converted to `MigrationOutcome.DECLINED_LOCKED`. Given/When/Then
docstrings that named `MIGRATE_DECLINED_LOCKED` by identifier updated to name the enum member
instead; docstrings that just said "exits 0" were left alone since that's still literally true
and not stale.

**The trap found during planning, not in the ticket text**: `TestMigrationLockingAcrossProcesses`
has two tests that run `migrate()` inside a **child process** (a string-literal script passed to
`run_child`) and `print()` its raw return value, with the **parent** test asserting on the
captured stdout string (`"0"` / `str(MIGRATE_DECLINED_LOCKED)`). Once `migrate()` returns an
enum, `print(exit_code)` in the child would print `MigrationOutcome.SUCCEEDED`, not `"0"` --
silently breaking the string comparison with no traceback pointing at the real cause. Fixed by
changing the embedded script text to `print(outcome.exit_code)` /
`print(pm.migrate(...).exit_code)`, and the parent's expectation to
`str(MigrationOutcome.DECLINED_LOCKED.exit_code)`. Re-ran both subprocess tests 4 times total
(once in the full suite, three standalone) with no flakiness.

`test/unit/test_auto_migrate.py`: import swapped; 8 `mock_migrate.return_value = <int>` sites
converted to the matching `MigrationOutcome` member (line-targeted rewrite, same review
process); 3 Given/When/Then docstrings that named `MIGRATE_DECLINED_LOCKED` or said "a
non-zero exit code" updated to name `MigrationOutcome.FAILED` / `.DECLINED_LOCKED`.

**New tests added** (per the spec's explicit ask to pin the mapping and verify the CLI
boundary directly, not just through unit-level mocks):
- `TestMigrationOutcomeExitCodes.test_exit_code_mapping` -- pins `SUCCEEDED.exit_code == 0`,
  `FAILED.exit_code == 1`, `DECLINED_LOCKED.exit_code == 3` directly, since that mapping is
  now the sole thing standing between the enum and the shell.
- `TestMigratePermissionsMainExitCodes` (3 tests) -- calls the real
  `migrate_permissions.main()` with `find_project_root` and `migrate` mocked (returning each
  `MigrationOutcome` member in turn) and asserts the **int** `main()` returns is exactly 0, 1,
  3. This is the direct CLI-boundary check the existing subprocess tests didn't cover (they
  exercise `permission_migration.migrate()` directly, never `scripts.migrate_permissions.main`)
  -- no existing test file imported that module at all before this pass.

No existing test was weakened, deleted, or had an assertion loosened -- every change above is
either a rename (same assertion, different spelling) or an addition.

### Verification

- `uv run python -m unittest discover -s test -t .`: **2710 tests, OK** (2706 baseline + 4
  new: 1 mapping-pin test + 3 CLI exit-code tests).
- `uv run python -m unittest test.unit.test_migration test.unit.test_auto_migrate -v`: 116
  tests, OK.
- `TestMigrationLockingAcrossProcesses` (the two real-subprocess concurrency tests) run 4
  times total (once via the full-suite pass, three standalone reruns): all green, no
  flakiness -- confirms the declined-locked path still works end to end through a real second
  OS process, not just a mock.
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both
  clean.
- `uv run ruff format .` / `uv run ruff check .`: clean (ruff reformatted 2 files it
  auto-fixed whitespace-only; no semantic change).
- `py_compile` clean on all 5 touched files.
- Anti-pattern scan (async/await, threading, function-local imports): none in any touched
  production file.
- Doc-drift sweep: `grep -rn "MIGRATE_DECLINED_LOCKED"` across the whole repo (excluding
  `cover/`, `__pycache__`, `.git/`, and prior memory notes which are historical records) --
  zero remaining hits. Checked `technical-notes.md`, `docs/*.md`, `README.md` for any
  description of `migrate()`'s int-return contract -- none exists, so no doc update needed.
  Grepped for other production callers of `migrate(` -- confirmed only the two named ones.

### Scope

5 files touched this pass: `toolguard/permission_migration.py`, `toolguard/auto_migrate.py`,
`toolguard/scripts/migrate_permissions.py`, `test/unit/test_migration.py`,
`test/unit/test_auto_migrate.py`. No new files. Matches the plan exactly; well under the
scope-inflation guardrails.

### Deviations from the spec

None. The two "trap" items (the subprocess-print sites, and adding a direct CLI-boundary test
for `migrate_permissions.main()`) were both anticipated by the spec's own instructions
("verify end-to-end... directly, not just through unit tests" and "if some assertion
genuinely can't be expressed against the enum, stop and report") rather than deviations from
them.

### Elapsed time / cost (estimated)

- Phase 1 (planning: read spec, prior report/task-recall for context, surveyed
  `permission_migration.py`, `auto_migrate.py`, `migrate_permissions.py`, all 16+ test
  assertion sites across both test files including the subprocess-embedded ones, `once_per`/
  `once_per_store`/`error_reporter` for enum-and-table style precedent, wrote task recall):
  ~20 min.
- Phase 2 (implementation: enum + mapping + `migrate()` return-type change in
  `permission_migration.py`; `auto_migrate.py` and `migrate_permissions.py` call-site updates;
  two disclosed line-targeted rewrite scripts for the two test files' ~23 mechanical renames;
  hand-edits for the subprocess-script print sites and stale docstrings; two new test
  classes): ~25 min.
- Phase 3 (self-review: full suite x3, targeted module run, 4x concurrency-test reruns, ruff,
  architecture fitness, doc-drift sweep, report writing): ~15 min.
- Total: roughly 60 minutes of wall-clock work.
- Cost estimate (Sonnet 5, moderate token volume -- several large file reads across 2 large
  test files, two full-suite runs at ~47s each, multiple targeted reruns): roughly $1-2 in
  API-equivalent terms. Rough order-of-magnitude, not metered.
