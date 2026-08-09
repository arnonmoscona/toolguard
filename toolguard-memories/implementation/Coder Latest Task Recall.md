---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

## Ticket / context

TOO-45 punch-list #04, fix pass on the `hook.py` work. Repo `/home/arnon/projects/toolguard`,
branch `too-45`. Code review at `toolguard-memories/latest-code-review-report.md` (read in
full). This is a fix pass on three Major findings (M1, M2, M3) plus one Minor (m5) from that
review, all quoted/compressed into Arnon's prompt. Append to the existing implementation report:
`implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md` (do not
replace it -- it already has two prior "---" sections from earlier passes on this same item).

## The 4 items (verbatim intent, compressed)

**1. M1 -- `_emit_decision`'s exit-2 fallback never fires on a real pipe.** CONFIRMED BY
MEASUREMENT, do not re-litigate. `print()` returns without raising on a block-buffered pipe;
the actual write happens at flush/interpreter shutdown, past the `try/except`. Real subprocess
run with closed stdout: exit 120, not caught. Fix: `sys.stdout.flush()` INSIDE the `try`. Keep
the existing write-raising test; ADD a new test whose double raises on `flush` (not `write`).
Must re-prove with a real subprocess + closed pipe: exit code must become 2, not 120. Put that
evidence in the report.

**2. M2 -- `_run_eval_mode` still has 3 verbatim copies of the fail-open just removed from
`main()`.** Deny JSON to stderr, `exit 0`, empty stdout. Previous guidance (leave `--eval`
alone, stderr is documented/pinned) must be RE-ESTABLISHED, not repeated on faith:
- Find what actually consumes `--eval` (review says security-audit skill's ASK-floor probe).
  Read that consumer, determine which STREAM it reads (stdout or stderr).
- If stderr: internally consistent, not a fail-open. Fix ONLY the now-stale docstring (it
  claims a contract `main()` no longer shares). State this finding + evidence in the report.
- If stdout: same defect, same fix as `main()` (route through `_emit_decision`, i.e.
  `create_hook_output` + `_emit_decision`, NOT `_finalize_output` -- eval mode doesn't want the
  fault buffer). The pinned test (`test_hook_eval.py::test_eval_malformed_stdin_fails_safe`,
  which does `json.loads(mock_stderr.getvalue())`) is then pinning a bug -- correct it, and say
  so explicitly (this is the "existing test pins a defect we are fixing" carve-out, same as the
  prior pass's `TestHookCrashCapture` precedent).
- Report which branch was taken and the evidence. Do not guess.

**3. M3 -- nested invocations discard the inner fault buffer.** `drain_claude_context()` reads
only current `_current` state; `invocation()`'s `finally` throws away the inner
`_InvocationState.claude_messages` on restore. A fault reported inside an inner invocation,
followed by an exception unwinding to the outer handler, is lost. Fix in
`error_reporter.invocation`: on exit, splice any undrained `claude_messages` into the parent
before restoring `_current = previous`:
```python
finally:
    if previous is not None and _current is not None:
        previous.claude_messages.extend(_current.claude_messages)
    _current = previous
```
Add a test: report a fault inside the inner invocation, raise, assert it appears in the crash
response's `additionalContext` alongside the handler's own fault.

**4. Minor m5 -- warning log written on every tool call.** Converted config-layer warnings
(e.g. divergence / settings-path-override) now append to the warning log every time, not just
echo to stderr, for as long as the condition holds (potentially every single tool call
indefinitely). Assess real-world volume. Either throttle via `toolguard/once_per.py` (same
layer, exists for exactly this) or justify in the report why unthrottled is correct. Make the
call deliberately, state reasoning.

**Everything else in Minors: fix ONLY the stale `error_reporter` docstring (m4, "`report_fault`
has no production call site yet") and the `invocation(config=...)` parameter rename if it is
in fact a rename (m3: rename to `env_config` to stop reading as if it takes a `Configuration`).
Do NOT restructure `main()` (m2), do NOT collapse the six except blocks (m1), do NOT touch m6-m10
(log-dir-on-hot-path docstring note, stderr-fallback unguarded, `_run_main` SystemExit-code
check, `_run_main` patches-list simplification, missing M3-crossing test is now covered by item
3 above).**

## Constraints (from CLAUDE.md, both global and project)

Stdlib only for runtime. `unittest`, not pytest (`uv run python -m unittest discover -s test -t
.`). No git write ops. No async/await, no threading, no local imports unless justified. Comments
short, no ticket narrative in code (a bare TOO-45 pointer is fine, the story is not). Must NOT
modify or delete an existing test unless it pins a defect being fixed (M2's stderr-parsing test
is the candidate case here -- confirm which branch first). Disclose inline/heredoc code per this
repo's INTENT/TOUCHES/INLINE-BECAUSE block + `TG_INTENT=1`/`TG_ATTEST_READONLY=1` -- Arnon
called out that I self-flagged two undisclosed `python -c` snippets last pass; same expectation
this pass, no repeat.

## Verification bar

- Full suite green, was 2681 tests before this pass.
- `uv run python tools/architecture_fitness.py --layers` clean.
- `uv run ruff format .` and `uv run ruff check .` clean.
- For M1 specifically: real subprocess with closed pipe read-end must exit 2, not 120 -- prove
  it the way Arnon did, put the evidence in the report.

## Do not commit

Arnon does all git write operations himself. Append to the implementation report; do not
replace prior sections.