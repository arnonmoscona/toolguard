---
title: TOO-15 Coder Implementation Report - Crash Capture RED Phase
type: note
permalink: toolguard/implementation/too-15-coder-implementation-report-crash-capture-red-phase
tags:
- task-memory
- TOO-15
- coder-implementation-report
---

## Status: GREEN -- complete, approved and implemented

Full details: `/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-error-capture-report.md`

## Summary
- `log_crash(exc, context, caught_as) -> Optional[Path]` added to
  `toolguard/error_log.py`: writes a per-crash Markdown file to
  `~/.toolguard/errors/toolguard-error-<timestamp>.md` (lazy mkdir, local -2/-3
  collision suffix, never raises, returns None on write failure).
- Wired into all three except clauses of `toolguard/hook.py`'s `main()` via a new
  `_build_crash_context(locals())` helper (safely handles vars not yet assigned
  when the exception fires early). `_run_eval_mode()`'s except clauses were
  intentionally left untouched (out of ticket scope).
- `toolguard/tools/installer.py`'s `_README_TEMPLATE` got a 2-line `errors/`
  bullet; `init-state` still does NOT create it (lazy only).
- Tests: NEW `test/unit/test_error_log.py` (4 tests), extended
  `test/unit/test_hook.py` with `TestHookCrashCapture` (3 tests). All 7 pass.
- Full suite: 1405/1405 passing (1398 baseline + 7 new), 0 failures/errors.
  `uv run ruff check .` clean repo-wide. `ruff format` skipped per project
  convention.
- Self-review caught and fixed one docstring line-wrap glitch and one slightly
  long line; re-verified full suite + lint after.
- Scope: 5 files touched (1 new, 4 modified) -- within guardrails.

## Note for reviewer
`toolguard/tools/installer.py`'s working tree also carries two unrelated
uncommitted hunks (reminder print statements in `cmd_register_hooks`/
`cmd_enable_takeover`) left over from a PRIOR session's work -- not part of this
change, flagged in the scratchpad report so they aren't misattributed.
