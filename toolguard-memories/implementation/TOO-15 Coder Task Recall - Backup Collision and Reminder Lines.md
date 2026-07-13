---
title: TOO-15 Coder Task Recall - Backup Collision and Reminder Lines
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-backup-collision-and-reminder-lines
---

## Ticket
TOO-15 (install-runbook hardening). Real bug found during live install test (attempt #5).

## Mandated workflow (hard requirement)
TDD RED-then-checkpoint. Write/extend tests FIRST. Run full suite, confirm ONLY the intended
new tests fail (for the right reason), confirm nothing else regresses. STOP and report the red
state. Do NOT implement the fix yet. Wait for explicit approval before writing production code.

## Bug 1 (main): backup filename collision can silently destroy an earlier backup
File: toolguard/scripts/migrate_permissions.py, function `create_backup(file_path: Path,
backup_dir: Path) -> Path` (~line 88).
Filename built as `{stem}.{timestamp}{suffix}`, timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
(second granularity). Two calls resolving to the same backup filename within the same second ->
second write silently overwrites first backup (destroys restore point).

Reused by toolguard/tools/installer.py (`from toolguard.scripts.migrate_permissions import
create_backup, ...`) for every mutating installer subcommand's backup step (write-config,
register-hooks, seed-self-perms, enable-takeover). Same risk there.

### Required fix design (exact, do not substitute)
Disambiguate with a SEQUENCE NUMBER, not finer timestamp granularity. After building candidate
`backup_name` as today, if a file already exists at that exact `backup_path`, append a suffix
disambiguator and increment until path does not exist:
`{stem}.{timestamp}{suffix}` -> if taken -> `{stem}.{timestamp}-2{suffix}` -> `-3{suffix}` etc.
Exact separator/format is coder's call, but must be self-explanatory when listing backups/ dir,
and monotonic/stable (never reuse a number, never overwrite). Must work for both "has extension"
and "no extension" branches of existing function.

### Tests required (test/unit/test_migrate_permissions.py - search first, may already exist)
- Two create_backup calls for same source file, forced to collide on identical timestamp (mock
  datetime.now, not real wall-clock sleep) -> TWO DISTINCT files on disk, FIRST backup's content
  unchanged after second call (prove old content survives - this is the actual regression).
- Third collision on same timestamp -> third distinct file (disambiguator keeps incrementing,
  not just handles exactly two).
- Normal (no-collision) case still produces current filename shape unchanged (no regression;
  existing tests may already cover, just ensure they still pass).
- Every test function needs Given/When/Then BDD docstring per project CLAUDE.md convention (look
  at test/unit/test_toml_config.py for style).

## Bug 2 (secondary): installer.py subcommands don't remind agent of remaining checklist steps
File: toolguard/tools/installer.py.
Real-world observation: guided installs following docs/install.md skip later checklist phases
(Phase 8 security-audit offer, Phase 9 maintenance-pass offer, MANDATORY Phase T.1 trace-dump
offer) even though runbook states them.

Add a short one-line stdout reminder to END of two subcommands' existing print-summary output
(after everything already printed - do not remove/reorder existing output; existing installer
tests likely assert on parts of it):

- `cmd_register_hooks` ("go-live" step): remind that Phase 5 skills, Phase 6 validation, Phases
  7-10 plus wrap-up still ahead. Example:
  `print("  reminder: still ahead per docs/install.md -- skills (5), validate (6), and later "
         "phases 7-10 + wrap-up; the session-trace dump offer (Phase T.1) is MANDATORY before "
         "you end the conversation")`
- `cmd_enable_takeover` (last mechanical step in takeover install): remind that Phase 10.4
  re-validation, Wrap-up summary, MANDATORY trace-dump offer still needed. Example:
  `print("  reminder: still ahead per docs/install.md -- 10.4 re-validate under takeover, then "
         "Wrap-up; the session-trace dump offer (Phase T.1) is MANDATORY before you end the "
         "conversation")`

Keep wording short (1-2 lines each), consistent with file's existing print style (check
surrounding print(...) calls for tone/format before writing).

### Tests required (test/unit/test_installer.py or similar - search first)
Add/extend tests asserting these reminder lines appear in the two subcommands' stdout. Follow
existing test structure/naming. New/changed test functions need Given/When/Then BDD docstrings.

## Workflow steps mandated
1. Search repo first to confirm exact current file/test locations and existing test patterns.
2. Write tests for BOTH bugs first. Run FULL suite
   (`uv run python -m unittest discover -s test -t .`). Confirm (a) new tests fail for the RIGHT
   reason, (b) nothing else regresses vs current passing state.
3. STOP. Report: new tests added (file + test names), full suite before/after pass count,
   confirmation new tests fail only because fix isn't written yet (not a test-code typo/import
   error). Do NOT implement fix yet - wait for review/approval of red state.
4. Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples here) - `uv run
   ruff check .` for linting is fine.
5. Use `uv run python ...` always, never bare python.
6. Write short memory/report summarizing what was done + where, at
   /tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-backup-collision-report.md
   with exact file paths, function/test names, full-suite pass counts before/after test additions.

## Success criteria
- New tests exist covering both bugs, fail for the right (expected) reason pre-fix.
- Full suite run before and after test additions, counts reported, no other regressions.
- No production code changes yet (RED state only, awaiting approval).
- Report file written to scratchpad path above.


## RED-phase status (as of this update)

Tests written, full suite run, STOPPED per mandated workflow. Awaiting approval before
implementing the fix. Full details in scratchpad report:
/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-backup-collision-report.md

- Baseline: 1393 tests, OK.
- After adding 5 new tests: 1398 tests, FAILED (failures=4) -- exactly the 2 collision
  tests + 2 reminder tests fail for the right reason; 1 new no-collision test passes
  (no regression); all 1393 baseline tests still green.
- Files touched: test/unit/test_migration.py (TestBackupCreation, +4 tests, +1 import),
  test/unit/test_tools_installer.py (TestSummaryOutput, +2 tests). No production code
  changed yet.
- Lint clean (ruff check), py_compile clean, no anti-patterns.


## GREEN-phase status (approved and implemented)

Coordinator independently verified the RED state and approved. Implemented both fixes:

1. `toolguard/scripts/migrate_permissions.py::create_backup` -- sequence-number
   disambiguator. No-collision filename unchanged
   (`{stem}.{timestamp}{suffix}`); collisions get `-2`, `-3`, ... appended before the
   suffix (e.g. `settings.local.2026-02-05-143022-2.json`). Works for both
   has-extension and no-extension branches via a shared `base_name`/`suffix` split.
2. `toolguard/tools/installer.py` -- one reminder `print()` line appended (after all
   existing output, before `return 0`) to both `cmd_register_hooks` and
   `cmd_enable_takeover`, each naming remaining docs/install.md phases and flagging
   the Phase T.1 trace-dump offer as MANDATORY.

Full suite: 1398 tests, OK (0 failures) -- up from RED's 4 failures, matching the
1398-test total from the RED-phase run exactly (no new tests added or removed during
the fix). `uv run ruff check .` clean project-wide. No anti-patterns introduced.

Full detail in scratchpad report:
/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-backup-collision-report.md

Not committed/pushed -- left to coordinator per instructions.
