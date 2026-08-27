---
title: TOO-44 follow-up - re-drift guard for TestDecisionReachesStdoutWhenCrashLoggingFails
  - coder-latest-implementation-report
type: note
permalink: toolguard/implementation/too-44-follow-up-re-drift-guard-for-test-decision-reaches-stdout-when-crash-logging-fails-coder-latest-implementation-report
---

## Summary

Added a re-drift guard to `TestDecisionReachesStdoutWhenCrashLoggingFails._drive_main` in
`test/unit/test_hook.py`. The class's fixture patches `toolguard.ambient.home` to raise, but
previously never checked that `log_crash` actually reads that patched accessor and actually
fails -- so a future refactor moving `log_crash` off `ambient.home()` (exactly what happened in
TOO-44 itself) could silently defeat the whole class while every test kept passing.

## File changed

`/home/arnon/projects/toolguard/test/unit/test_hook.py` -- one file, minimal diff (see below).

## What was added

1. Import `log_crash` from `toolguard.error_log` (needed so the spy can call the real
   implementation through).
2. Inside `_drive_main`, a `_spy_log_crash` closure that calls the real `log_crash`, appends its
   return value to a `crash_results` list, and returns it -- patched in as
   `patch("toolguard.hook.log_crash", side_effect=_spy_log_crash)`, alongside the fixture's other
   patches (patch target confirmed correct: `toolguard/hook.py:36` binds `log_crash` by value via
   `from toolguard.error_log import ... log_crash ...`, so `toolguard.error_log.log_crash` would
   be inert here -- there's already a precedent for this exact target,
   `test_crash_context_carries_tool_name_tool_input_cwd`, a few classes above in the same file).
3. After `main()` returns/raises, two assertions: `crash_results` is non-empty (log_crash was
   reached at all) and `crash_results[0] is None` (it failed, matching `log_crash`'s documented
   `except Exception: return None` contract). Deliberately not asserting on a stderr message --
   confirmed `log_crash` writes no "failed to write crash report" string on that path, only a
   short warning inside its own internal fallback branches that isn't reached here.
4. One added sentence in the class docstring and an expanded `_drive_main` docstring, both
   describing the new self-check -- no other prose was stale.

## Design decision: side_effect closure over `MagicMock(wraps=)`

Measured empirically (see task-recall note) that `MagicMock(wraps=log_crash).return_value` stays
`sentinel.DEFAULT` after a call, even though the call itself returns the real result -- `wraps`
does not populate `.return_value` retroactively. A `side_effect` closure that calls through and
appends to a list is the correct, minimal way to capture the real per-call return value with
stdlib `unittest.mock`. No existing precedent in the repo does this (other `wraps=` uses only
assert on `call_count`/`call_args`, not on return values), so this is new but follows the
existing spy style in the same file.

## Verification (all against the brief's checklist)

- **New assertion fails when defeated**: wrote a throwaway script under `/tmp/.../scratchpad`
  (deleted after use, never part of the repo) that monkeypatches `test_hook.log_crash` in-memory
  to a fake that always "succeeds" (returns a fake `Path`, never touches the filesystem) --
  simulating a refactor that moved `log_crash` off the patched `ambient.home()`. Ran the target
  test class against that: **all 3 tests failed**, each with
  `AssertionError: PosixPath('/nonexistent/fake-crash-report.md') is not None : log_crash did
  not fail under this fixture, ...`. Restored (subprocess exit undid the monkeypatch); re-ran the
  class normally: **3/3 pass**.
- **Full suite**: `uv run python -m unittest discover -s test -t .` -> `Ran 3684 tests ... OK
  (expected failures=4)`. Matches the stated baseline exactly.
- **`~/.toolguard/errors/` file count**: 1768 before, 1768 after a full-suite run. Unchanged,
  nothing deleted or added there.
- **ruff**: `uv run ruff format --check .` -> 177 files already formatted. `uv run ruff check .`
  -> all checks passed. Both repo-wide, not just the changed file.
- **`tools/architecture_fitness.py --mocks`**: still exactly 1 finding, and it is the
  pre-existing, unrelated `test_session_warnings.py:159` one -- this task's new patch
  (`toolguard.hook.log_crash`) is a correct target and does not add a finding.

## Discrepancy found in the brief (per instruction to report rather than adopt)

The brief stated "The tree is clean and committed at `e047bf2`." That was false at the time I
started: `git status` showed a large set of already-modified tracked files (`README.md`,
`docs/*.md`, `.pyscn.toml`, several `test/unit/test_*.py` files unrelated to this task) and many
untracked `toolguard-memories/**` files, evidently left over from a prior, unrelated TOO-45
session. I did not touch any of those files -- `git diff test/unit/test_hook.py` shows only the
change described above, and no other tracked file changed as part of this task. Flagging this
because the brief's "clean tree" claim does not hold, not because it affected the work.

## Self-review

- Anti-pattern scan: no async/await, no threading, no local imports introduced.
- Requirements re-checked against the brief point by point above; all satisfied.
- Kept the edit to the single fixture method plus two short docstring additions, as instructed
  ("keep the edit minimal").
- No production code touched -- test-only change, well within the "adding tests" allowance
  (this is an addition to an existing test's fixture, not a weakening of any assertion).

## Not committed

Per instruction, no git write operations were performed. The working tree still has this and
the pre-existing unrelated changes uncommitted.

## Time / cost (approximate)

- Phase 1 (read conventions, locate test, understand `log_crash`/patch-target semantics, capture
  requirements to memory): ~10 minutes, tool-heavy but simple, ~$0.05.
- Phase 2 (implementation, two `Edit` calls): ~5 minutes, ~$0.02.
- Phase 3 (self-review: full suite x2, target-class runs, ruff, `--mocks`, the in-memory
  defeat-demonstration script and its run): ~20 minutes, the most expensive phase since it
  included a 52s full-suite run twice plus a scratch-script round-trip, ~$0.10.
- Phase 4 (this report, memory writes): ~5 minutes, ~$0.02.
- Total: roughly 40 minutes elapsed, estimated cost under $0.20 (Sonnet 5, moderate token usage,
  no large file dumps).
