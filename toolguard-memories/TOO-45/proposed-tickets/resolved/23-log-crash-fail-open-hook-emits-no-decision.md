---
title: 'log_crash is a fail-open: the hook can exit with no decision on stdout'
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/23-log-crash-fail-open-hook-emits-no-decision
---

**FIXED in `05f786d` (TOO-45 phase 2).** `log_crash`'s `Path.home()` call moved inside the try, so a home-lookup failure no longer leaves the hook without a decision — see `toolguard/error_log.py:145-148`.

> **CONFIRMED, LOCALIZED, AND THE FIX IS PROVEN 2026-08-13. Three RED tests are in the tree.**
>
> **Exact site: `toolguard/error_log.py:142`** — `errors_dir` is built above its own `try`. Call sites: `hook.py:1311`, `:1322`, `:1335`, one per top-level `except`, each running `log_crash` before `_emit_decision`.
>
> **The stdout contract had NO test at all.** Measured, not read: driving `main()` with `Path.home()` raising produced `stdout == ""` and a `RuntimeError` escaping `main()` — while the module still reported **89/89 OK**. This ticket's original observation was right and understated: the 9 errors were incidental, and the reason nothing caught it is that **no test in the module ever asserted what lands on stdout.**
>
> **Now covered** by `TestDecisionReachesStdoutWhenCrashLoggingFails` — three tests, one per `except` clause (`json.JSONDecodeError`, `ValueError`, catch-all). Each asserts nothing escapes `main()` **and** that stdout carries parseable JSON with a `deny`.
>
> **Mutate toward the fix — the fix is one line.** Moving `errors_dir` inside `log_crash`'s own `try` takes the module from **89 pass / 3 fail to 92 pass**. Red for the defect, green for its correction, which is the strictly stronger statement. (Rebound in both `error_log` and `hook`'s by-value import, with both patches asserted to have taken effect.)
>
> ## UPDATES 2026-08-13 (evening) — three corrections and a unit-level RED
>
> **1. The leak described below is FIXED and this ticket's numbers are stale.** `test_hook_error_reporter.py` was repaired earlier the same day and now patches `toolguard.error_log.Path` in `setUpModule()`. Re-measured from inside the test process: **0 deltas.** `~/.toolguard/errors/` stands at **1,628** files (this ticket says 1,616 and 1,614 — both superseded). The accumulated files remain; nothing was deleted.
>
> **2. A UNIT-LEVEL RED test now exists, and it is not a duplicate.** `test_error_log.TestLogCrash.test_log_crash_returns_none_when_no_home_directory_resolves` asserts `log_crash`'s **own contract**, failing at `error_log.py:142` exactly. The three `test_hook.py` reds assert stdout and `additionalContext` through `main()` — a different altitude. **Mutating toward the proven one-line fix turns it green with 62/62 passing** across `test_error_log` + `test_logging_streams` + `test_error_reporter`.
>
> **3. Reachability is narrower than the ticket implies.** On Linux, an **unset `HOME` does NOT make `Path.home()` raise** — there is a `pwd` fallback. So the failure is only reachable via a patched `Path` or a genuinely broken passwd entry. That does not make the defect less real (the fix is one line and the code is wrong either way), but it should temper the urgency, and the RED test's fixture asserts it can produce the negative case rather than assuming it.
>
> ## FIVE mechanisms in this module had ZERO detection across the whole 3,136-test suite
>
> All measured by identical failing-ID sets, not counts:
>
> - `caught_as` replaced by `type(exc).__name__`
> - `traceback.format_exc()` emptied
> - the `[CRASH] Full details written to <path>` echo removed
> - the crash-write-failure warning removed
> - **`_log_entry`'s `Warning: Failed to write to log file ...` removed** — and that line is **the only trace a dropped log entry leaves anywhere**
>
> The pre-existing tests could not see any of it: `assertIn("Traceback")` matched only the section **heading**, so an empty traceback passed.
>
> **A near-miss worth recording**: two patches were live but **unasserted**. With a fixed timestamp and an inert patch, `test_log_crash_colliding_timestamp_writes_distinct_files` **would have written into the developer's real `~/.toolguard/errors/` and still passed.** All five are now detected; the redirect is now asserted.
>
> ## An obligation for whoever fixes EL2
>
> Moving `_log_entry`'s `mkdir` inside its `try` (EL2's fix direction) **breaks exactly one test** — `test_error_reporter.TestLogWriteFailureDegradesToStderr.test_write_failure_still_produces_stderr_and_does_not_raise`, whose "log dir is a regular file" fixture *relies* on `_log_entry` raising so `Reporter._print_fallback` runs. **That test must be repaired in the same change.** Deleting the `mkdir` outright is well covered (6 detectors); only the asymmetry is unheld.
>
> **THE ROOT CAUSE WAS ALSO LEAKING INTO THE DEVELOPER'S HOME — now fixed, see update 1 above.** `log_crash` hard-codes `Path.home()`, which makes it **unisolatable by design** — and `test/unit/test_hook_error_reporter.py::TestInvocationStateDoesNotLeakBetweenCalls` drives `main()` through a crash without patching it. Measured: **2 genuine crash reports written into `~/.toolguard/errors/` per run of that module** (1,614 → 1,616 in a single observation). `test_hook.py` writes none.
>
> That directory now holds **1,616 files**, and grows every time the suite runs. It is the same family as the 19 stray reports already cleaned up during this campaign — and it means **the one-line fix below is not only a correctness fix; it is what makes the function testable at all.** Whoever takes ticket 23 should fix `log_crash`'s `Path.home()` dependency (inject the directory, per proposed ticket 44's wrapper argument) rather than only moving the `try`.
>
> `test_hook_error_reporter.py` also needs repair; it is not yet in the campaign's completed list.
>
> **Two side findings from the same probe:**
>
> - **`toolguard.once_per_store` is unreachable from `hook.main()`** — measured by wrapping all eight of its public callables with recorders and replaying the scenario twice, with a fake log dir and a real one: **zero calls**. A test patching `once_per_store.sqlite3` to `None` is therefore mocking a path the code never takes.
> - **The working queue's account of the related vacuous test was right but incomplete, for the reason this project keeps re-learning.** It found that `if log_files:` is never entered. It missed a **second, independent** vacuity: the glob is `toolguard-error-*.md`, but validation issues are `level="warning"` and land in `toolguard-warning-<date>.md`. Two reasons, one recorded — because the finding came from reading rather than executing. It also cites the wrong shape number.

# `log_crash` is a fail-open: the hook can exit with no decision on stdout

**Severity: the highest single finding in the TOO-45 #07 sweep.** Same class as the fail-open punch-list item #04 fixed, in a different place.

## The defect

`toolguard/error_log.py`, `log_crash`:

```python
errors_dir = Path.home() / ".toolguard" / "errors"      # <- ABOVE the try
try:
    ...
except ...:
    ...
```

`Path.home()` sits **outside** the `try`. It raises `RuntimeError` when no home directory can be resolved -- an unset/empty `$HOME`, a deleted home, a container or launchd/systemd context with no passwd entry.

## Why that is a fail-open rather than a logging bug

`log_crash` runs **inside `hook.py`'s three top-level `except` clauses**, and it runs **before** `_report_crash_fault` and `_emit_decision`. So the sequence is:

1. Something raises anywhere in the hook.
2. The top-level handler catches it and calls `log_crash` to record the crash.
3. `log_crash` itself raises, because `Path.home()` is above its own guard.
4. The exception escapes the handler. `_emit_decision` never runs.
5. **The hook exits with nothing on stdout.**

Claude Code treats only exit code 2 as blocking. A hook that emits no decision is not a denial -- it is no permission hook at all, silently, with no error anywhere. That is precisely the failure mode `CLAUDE.md`'s pre-push section warns about for a hook that cannot launch, reached here by a different route.

The irony is exact: **the code that exists to record a crash is what converts a recoverable crash into an ungoverned tool call.**

## Fix

Move the two lines inside the `try`. It is a one-line-effective change.

Then check the same shape elsewhere: any `Path.home()`, path construction, or environment read that sits above the `try` in a function reachable from a top-level `except` handler. `log_crash` was found by reading; the class deserves a grep.

## Confirmed by mutation — and the coverage is worse than a failure count suggests

Injecting an unconditional raise into `log_crash`, in an out-of-tree copy, produced **9 new test errors, 3 of them in `test_hook.py`**. A naive reading records that as "detected."

**Traceback inspection says otherwise.** Those 3 fail only because the raw `OSError` breaks an `assertRaises(SystemExit)` -- **no assertion ever reached the point of checking stdout.** Nothing anywhere asserts *"stdout still carries a verdict when `log_crash` itself fails"*, which is the entire contract at risk. Three control mutations (breaking `_emit_decision`'s print, `create_hook_output`'s additionalContext branch, and `FILE_PATH_TOOLS`) were all detected as designed, so the harness was working -- the gap is real.

**Method note worth keeping beyond this ticket: a mutation that produces failures is not necessarily detected.** Read the tracebacks and confirm the failures are for the right reason. Incidental breakage looks identical to coverage in a failure count, and here it would have hidden the sweep's highest-severity finding.

## Test obligation

A test that patches `Path.home()` to raise and drives `hook.main()` through a crashing path, asserting **a decision still reaches stdout**. Note what the assertion must be: not "log_crash did not raise", but "stdout carries a verdict". The first passes with the bug present in a different arrangement; the second is the actual contract.

## Provenance

Found in the `error_log.py` module sweep, TOO-45 #07. Recorded as row `EL1` in `reports/follow-up-queue.md` and repeatedly flagged in the work queue as the highest-severity single row, but never promoted to a ticket until now.
