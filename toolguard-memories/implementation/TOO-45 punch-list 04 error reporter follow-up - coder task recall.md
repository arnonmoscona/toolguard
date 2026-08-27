---
title: TOO-45 punch-list 04 error reporter follow-up - coder task recall
type: note
permalink: toolguard/implementation/too-45-punch-list-04-error-reporter-follow-up-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Continuation of TOO-45 punch-list #04: fold hook.py's fail-open into this item

Arnon reversed the scope boundary that excluded `hook.py`'s three `main()` error handlers.
His words: "fold it before commit, and there is no rational reason to keep a known defect."
Rationale: routing a message through the reporter and fixing the fail-open are the same work
-- the fail-open exists because a stream decision was made at a call site, and taking stream
decisions away from call sites is the entire purpose of the reporter.

Spec: `toolguard-memories/TOO-45/TOO-45 punch-list 04 error reporter - coder task spec.md` --
its "Explicitly NOT in scope" section is superseded for `hook.py` only. Everything else in
that list (other modules' stderr writes, `Issue.level`, takeover notice channel) stays out.

Existing implementation report (append, don't replace):
`implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md`

### 9 stderr sites in hook.py, three groups

**Group 1 -- THE DEFECT.** `main()`'s three except handlers (json.JSONDecodeError, ValueError,
catch-all Exception, ~lines 1303-1336). They build a correct deny verdict, print to **stderr**,
`sys.exit(0)`. Claude reads stdout only -> empty stdout + exit 0 = "no opinion" = falls through
to native permission handling. Catch-all exists to fail closed on anything unforeseen and
instead fails open.

Fix: decision payload -> stdout unconditionally, exactly like the normal paths. Keep
`sys.exit(0)`. Belt-and-braces: if the stdout write itself raises, fall back to `sys.exit(2)`
with the reason on stderr (only case with no decision to deliver).

Key distinction to keep visible in code: decision payload (stdout, unconditional) is NOT an
error report. The diagnostic ("toolguard crashed while deciding") goes through `report_fault`
-- this is what finally gives `report_fault` a real production caller.

**Group 2** -- `_print_not_a_standalone_command_message`: routine notice for a stray manual
invocation -> route through `report_notice`. `notice` severity already renders as a bare
message to stderr with no active invocation required (safe default), matching current output
exactly -- clean 1:1 swap, called both before any invocation exists (TTY guard) and inside the
outer invocation (EmptyStdinError handler).

**Group 3** -- `_run_eval_mode`'s own handlers: `--eval`'s documented contract is errors as a
deny decision on stderr -- deliberate, DO NOT change destination. `test_hook_eval.py::
test_eval_malformed_stdin_fails_safe` does `json.loads(mock_stderr.getvalue())` -- stderr must
contain ONLY the JSON decision, nothing else. There is no separate "diagnostic about toolguard"
in this code today (no log_crash call here at all), so there is nothing to route through the
reporter without violating that pinned test and the "no logging" contract in the docstring.
Decision: leave `_run_eval_mode` untouched; state the reasoning in the report.

### Verification requirements (assert the STREAM, not just "a deny was produced")

- Each of the 3 Group-1 handlers: test that decision JSON lands on stdout, stdout non-empty.
- A test that stdout-write failure exits 2.
- A test that each handler also produces a fault report reaching the Claude buffer
  (additionalContext), through the real call site.
- Golden verdict corpus: structurally blind here, keep green, don't cite as evidence.
- Full suite green (baseline 2680), `tools/architecture_fitness.py --layers` clean, ruff
  format/check clean.
- Behaviour change to call out explicitly: malformed hook input now produces a real deny
  instead of silently falling through to native handling -- user-visible, must be in the report
  plainly (before/after).

### Isolation gotcha discovered during investigation

The OUTER `error_reporter.invocation(config=None)` (active during these 3 except handlers,
since the inner config=env_config invocation has already exited via LIFO restore by the time
control reaches an except clause) resolves its log dir via
`log_writer._log_dir_from_environment()` -> `path_utils.require_project_root()`, which
deliberately ignores `TOOLGUARD_LOG_DIR` (documented in that function's own docstring). The
repo's real `logs/` directory exists on this dev machine, so a naive new test would trip
`test/unit/_real_log_dir_guard.py`'s leak guard (suppressed + recorded -> fails
`test_zz_real_log_dir_guard.py`). New tests must patch
`toolguard.error_reporter.resolve_log_dir` to return `None` (or similar) rather than relying on
`TOOLGUARD_LOG_DIR`/`isolate_log_dir_for_module()`, which does not reach this path.

### Plan

1. `hook.py`: add `_emit_decision(output)` (stdout print, exit(2) fallback on write failure),
   `_report_crash_fault(error_reason)` (wraps `report_fault` with a shared corrective-steps
   constant). Use `_emit_decision` at all decision-print sites in `main()` (not-governed-tool
   early exit, success path, and the 3 Group-1 handlers) for literal consistency ("exactly as
   the normal paths do"). Remove the redundant extra `print(f"Error: ...")` line in the
   catch-all handler (now superseded by report_fault).
2. `_print_not_a_standalone_command_message`: swap to `report_notice(...)`.
3. Leave `_run_eval_mode` alone.
4. Update hook.py's module docstring and `main()`'s docstring (exit codes section) to reflect
   the real 0/2 contract.
5. New/updated tests in `test/unit/test_hook.py` (TestHookCrashCapture area) covering the
   verification list above. Do not modify existing pinned tests
   (`test_unexpected_exception_writes_crash_report` etc. currently assert stderr -- these MUST
   be updated since they assert the OLD, buggy stream; per CLAUDE.md rules, changing an
   existing test to fix a defect it was pinning to is allowed when the defect itself is being
   fixed -- confirm this reasoning in the report explicitly since it's changing existing tests).
6. Full verification loop before reporting.
