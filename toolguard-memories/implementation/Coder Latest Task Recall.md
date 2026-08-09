---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
---

# TOO-45 punch-list #15 final item -- migrate() outcome-type refactor

Repo `/home/arnon/projects/toolguard`, branch `too-45`. Folded into punch-list #15 (not a
new ticket) at Arnon's direction: he asked why the root fix was being deferred, measurement
showed the earlier "defer" reasoning was wrong, so doing it now.

## The root defect

`permission_migration.migrate()` returns a bare `int` exit code; callers branch on `!= 0`.
Adding `MIGRATE_DECLINED_LOCKED` in the prior pass silently changed the meaning of an
existing `!= 0` branch in `auto_migrate` (a lock decline started being reported as
"Migration failed" with backup-restore advice that made no sense for a benign decline). That
call site was already patched in the prior pass; this task fixes the root cause so the next
new outcome can't do the same thing again.

**Blast radius (measured, do not over-scope):** two production callers --
`toolguard/auto_migrate.py` (~line 161, `_migrate()` inner function) and
`toolguard/scripts/migrate_permissions.py` (~line 101, `main()`, a 4-line wrapper) -- and 16
test assertions across `test/unit/test_migration.py` and `test/unit/test_auto_migrate.py`.

## What to build

1. An `Enum` (matches `once_per.Repeat` / `once_per_store.ClaimStatus` style already in this
   codebase) with one member per outcome `migrate()`'s own `return` statements actually
   produce today -- read the code, don't invent: SUCCEEDED, FAILED, DECLINED_LOCKED. Do not
   add outcomes no current path produces.
2. **Exit code lives on the enum**, as a property or single mapping table declared in one
   place -- same shape as `error_reporter._ROUTING` (Arnon named that one as the maintainable
   precedent). Do not scatter `return 0` / `return 1` through the function.
3. `migrate()` returns the enum, not an int.
4. `toolguard/scripts/migrate_permissions.py` converts enum -> int at the CLI boundary --
   the ONLY place an exit code should appear.
5. `auto_migrate._migrate()` branches on enum members (`is` comparison), not integers.
6. Keep `MIGRATE_DECLINED_LOCKED`'s CURRENT NUMERIC VALUE (3) in the mapping -- chosen to
   avoid colliding with argparse's usage-error exit code 2 in the same CLI. That reasoning
   still holds; only its representation moves.

## What this must NOT become

- Do not restructure `migrate()`'s internals (its early-exit / dry-run / lock branches).
  Pure return-type change and call sites only.
- Do not add outcomes no current code path produces.
- Do not convert `run_auto_migration`'s own `bool` return -- different question, different
  callers, out of scope.
- Do not touch `once_per_store._project_key` or the `~/.toolguard` derivation follow-ups --
  still separate follow-ups, confirmed untouched in the prior pass too.

## Tests

- 16 existing assertions move to the enum. `== 0` -> `== MigrationOutcome.SUCCEEDED` etc. is
  the same assertion, shape change only -- nothing weakened, nothing deleted.
- If some assertion genuinely can't be expressed against the enum: STOP, report it (would
  mean the enum is missing a distinction the code makes). Not expected here based on the
  read-through, but checking for it while editing.
- **Trap found during planning, not in the ticket text**: two tests in
  `TestMigrationLockingAcrossProcesses` (`test_migration.py`, ~line 1526 and ~1622) run
  `migrate()` inside a CHILD PROCESS script (string literal) and `print()` its raw return
  value, then the PARENT test asserts on the captured stdout string (`"0"` /
  `str(MIGRATE_DECLINED_LOCKED)`). Once `migrate()` returns an enum, the child script's
  `print(exit_code)` must print the enum's exit-code property instead, or the string
  comparison silently breaks (prints `MigrationOutcome.SUCCEEDED` instead of `"0"`). This is
  the same shape-not-behavior change as the other 16 -- update the print statement in the
  embedded child script, and the parent's expected string, consistently.
- Add one test pinning the exit-code mapping itself (enum member -> int), since that mapping
  is now what stands between the enum and the shell.
- Behaviour identical end to end: CLI exit codes for success/failure/declined unchanged.
  Verify directly (existing `TestMigrationLockingAcrossProcesses` subprocess tests already do
  this for two of the three outcomes at the library level; `migrate_permissions.main()`'s
  int conversion needs its own direct check too if not already covered).

## Baseline

`uv run python -m unittest discover -s test -t .`: 2706 tests, OK (confirmed before starting).

## Process reminders

- Intent disclosure before any Bash command carrying logic I authored (heredocs, `python -c`,
  scratch scripts, authored shell loops/sed/awk): `# INTENT:` / `# TOUCHES:` /
  `# INLINE BECAUSE:` block plus `TG_INTENT=1` or `TG_ATTEST_READONLY=1`.
- Append (not overwrite) the basic-memory report to the EXISTING report note:
  `implementation/TOO-45 punch-list 15 migrate lock - coder implementation report`.
- Do not commit -- Arnon does all git write operations himself.
- `uv run ruff format .` / `uv run ruff check .` before declaring done.
- `uv run python tools/architecture_fitness.py --layers` clean.

## Files expected to touch

- `toolguard/permission_migration.py` (enum + mapping + `migrate()` return type)
- `toolguard/auto_migrate.py` (branch on enum)
- `toolguard/scripts/migrate_permissions.py` (enum -> int at boundary)
- `test/unit/test_migration.py` (16 assertions incl. 2 subprocess print sites, + new mapping
  test)
- `test/unit/test_auto_migrate.py` (mock return_values -> enum members)

5 files -- well within scope-inflation guardrails.