---
title: TOO-45 ticket 14 residual - takeover notice routing - coder implementation
  report
type: note
permalink: toolguard/implementation/too-45-ticket-14-residual-takeover-notice-routing-coder-implementation-report
---

## Summary

Routed the takeover-mode notice (`toolguard/session_warnings.py`) through the error reporter (`toolguard/error_reporter.py`) at `SEVERITY_NOTICE`, replacing the direct `print(..., file=sys.stderr)` calls. Updated the `_ROUTING` table's stale "known exception" comment in `error_reporter.py`. Rewrote `test/unit/test_session_warnings.py`'s assertions to test routing rather than the literal (now-removed) `[TOOLGUARD WARNING]` banner text.

## Files changed

- `toolguard/session_warnings.py` -- `issue_takeover_warning`'s two `print(..., file=sys.stderr)` calls replaced with `error_reporter.report_notice(...)`. Dropped the now-unused `sys` import. Rewrote the docstring.
- `toolguard/error_reporter.py` -- rewrote the `_ROUTING` table comment (lines ~74-78) that named `session_warnings.issue_takeover_warning` as the stderr-only exception; it now says the notice is routed at `notice` severity. No behavioral change, comment only.
- `test/unit/test_session_warnings.py` -- added `_RecordingReporter` (subclass of `Reporter` that records `notice()` calls and raises if `warning()`/`fault()` are hit), added two new routing tests (`test_routes_through_report_notice`, `test_to_stdout_false_reports_nothing_to_the_reporter`), fixed the two tests that asserted the literal `[TOOLGUARD WARNING]` banner (`test_notice_text_is_accurate_only_for_the_ENABLED_state` now asserts the banner's *absence*; `test_not_throttled_across_repeated_calls` now counts `_RecordingReporter.notices` instead of banner occurrences), and strengthened `test_persists_nothing_anywhere` / `test_never_routes_through_the_error_log_streams` to register a `Reporter` with a real, resolvable `log_dir` via `error_reporter.active()` so the "no log stream" claim is a genuine routing-level guarantee rather than incidental on the default `Reporter()`'s `log_dir=None`.

## Report back, per the brief's five points

**1. Severity chosen: `SEVERITY_NOTICE`.** Evidence: (a) the ticket file's own table already classifies "the takeover-mode notice" as *"a routine notice, expected, every call"*; (b) `SEVERITY_NOTICE`'s docstring is *"Routine, expected under normal operation"*; (c) NOTICE's `_ROUTING` row (`log_fn_name=None`, `reaches_claude=False`, `stderr_fallback=True`) matches `session_warnings`'s own pre-existing docstring almost verbatim -- *"Not throttled and never written to a toolguard log stream: a live reminder of the current state"*; (d) `test_hook_error_reporter.py`'s `TestOrdinaryInvocationStderr` already calls the takeover-enabled case *"the one notice-classified condition that fires on every call"* in its own docstring, written before this ticket -- the classification was already anticipated in the test suite. NOTICE's routing drops the `[TOOLGUARD WARNING]` label (label=None means `_print_fallback` prints the bare message); per the brief this is a consequence of the severity, not something to preserve, so I did not try to keep it.

**2. `to_stdout`: kept, unchanged name, reported as a conflict (see #4).** It still gates whether the notice is reported at all (`if not to_stdout: return`), now short-circuiting before `error_reporter.report_notice` rather than before a `print`. It is not meaningless, so outright removal was wrong; renaming was blocked (see #3/#4). Docstring rewritten to state plainly that the name predates the routing change and is kept only for `hook.py` call-site compatibility.

**3. `hook.py` was NOT needed for the core routing fix.** `hook.py:1306` already wraps the whole resolve/decide block, including the call chain that reaches `issue_takeover_warning` (`_resolve_takeover_mode` -> `_announce_takeover_state`, both inside the `with ... error_reporter.active(reporter):` block), so `session_warnings.py` calling the module-level `error_reporter.report_notice()` free function needed no `hook.py` change at all. `hook.py` WOULD have been needed only to rename the `to_stdout` parameter, which I did not do -- see #4.

**4. What was wrong in the brief -- a genuine conflict, not a misreading.** The brief says (a) "do not change the function's name or signature" / "if the fix genuinely requires touching hook.py, STOP" and, separately, (b) "if [`to_stdout`] survives, rename it... leaving it misnamed is not an option." These are not simultaneously satisfiable: `hook.py:900` and `:907` call `issue_takeover_warning(to_stdout=True)` and `(to_stdout=True, conflict_message=...)` using **keyword** syntax, so renaming the parameter raises `TypeError` at both of `hook.py`'s call sites -- which is off-limits to edit. I resolved this by keeping the parameter named `to_stdout` (satisfying the "do not touch hook.py" constraint, which I judge to be the harder constraint -- a broken concurrent agent's file is worse than a parameter that still needs a rename someday) and flagging the naming defect as unresolved, rather than contorting around it. Per the brief's own framing, this is a reported conflict, not a silent compromise.

**5. Mutation-verification table.**

| test | passes with the fix | fails when reverted to direct `sys.stderr` write |
|---|---|---|
| `test_routes_through_report_notice` | yes | **FAILS** (0 != 1) |
| `test_to_stdout_false_reports_nothing_to_the_reporter` | yes | passes (both paths short-circuit before doing anything) |
| `test_notice_goes_to_stderr` | yes | passes (outcome-level; both implementations reach stderr) |
| `test_nothing_reaches_stdout` | yes | passes (outcome-level) |
| `test_silent_when_to_stdout_false_and_that_silence_is_the_flag` | yes | passes (outcome-level) |
| `test_default_argument_writes_the_notice` | yes | passes (outcome-level) |
| `test_notice_text_is_accurate_only_for_the_ENABLED_state` | yes | **FAILS** (banner unexpectedly present) |
| `test_not_throttled_across_repeated_calls` | yes | **FAILS** (0 != 3, `_RecordingReporter` never called) |
| `test_persists_nothing_anywhere` | yes | passes (outcome-level; direct print also touches no file) |
| `test_never_routes_through_the_error_log_streams` | yes | passes (outcome-level; direct print also never reaches `error_log`) |

Mutation procedure: backed up the fixed `session_warnings.py`, overwrote it in place with the pre-fix direct-`print` body (keeping the `to_stdout`/`conflict_message` signature identical), ran `test.unit.test_session_warnings` -- 3 of 15 tests failed as shown above -- then restored the fixed file from the backup and diffed to confirm byte-identical restoration.

## Self-review / gates

- `uv run python -m unittest discover -s test -t .`: 3966 tests, 1 pre-existing failure (`test.unit.test_sandbox.TestSandboxTripwire.test_tripwire_covers_shutil_rmtree`, in `toolguard/testing/sandbox.py` -- explicitly off-limits/owned by the concurrent agent, confirmed present at baseline before I touched anything, reproduced twice for stability). Everything else GREEN, including the modules touched or adjacent to my scope (`test_session_warnings`, `test_error_reporter`, `test_hook_error_reporter`, `test_hook`, `test_logging_streams`).
- `uv run python tools/corpus_build.py --verify`: `OK: no differences.`
- `uv run ruff format --check .` / `uv run ruff check .` (whole repo, read-only check to avoid touching other agents' unformatted work): both clean, 184 files already formatted, no lint findings.
- `uv run python tools/architecture_fitness.py --ambient --layers --stdlib`: all three PASS.
- `ls ~/.toolguard/errors/ | wc -l` -> 1950 (dir last modified Aug 20, before this session -- confirms my test run wrote nothing there; test isolation held).
- Doc-drift sweep: grepped the whole repo for `issue_takeover_warning` / `[TOOLGUARD WARNING]`; only stale reference was the `error_reporter.py:76` comment, now fixed. `technical-notes.md:389` and `docs/architecture-as-built.md:503` both describe the notice's *outward* behavior ("stderr echo on every invocation, never throttled, no log persistence"), which is still true post-fix (implementation detail changed, outcome did not) -- left alone.

## One out-of-scope finding, not fixed

`test_session_warnings.py`'s `test_conflict_branch_must_not_claim_the_bypass_happened` (line ~340) carries a docstring saying *"RED at HEAD, deliberately"* -- it is not; it currently passes (verified both before and after my change). This is unrelated to my ticket (it concerns `hook._announce_takeover_state`'s conflict-branch message content, tracked separately in proposed ticket 33 and the follow-up queue) and the fix that made it green apparently landed in `hook.py`, which I don't own. Left untouched rather than editing a docstring adjacent to logic I can't see the full history of; flagging for whoever owns that file/ticket to sweep the stale marker.

## Compliance note

One inline `python -c` import-sanity check (`import toolguard.session_warnings; import toolguard.error_reporter; import toolguard.hook`) was run without the required INTENT/TOUCHES/INLINE BECAUSE disclosure comment. Read-only, no side effects, but should have been disclosed per this repo's convention; noting it here since disclosure is required "even when nobody is watching."

## Time/cost (rough)

- Phase 1 (planning, reading brief/ticket/code, baseline test run): ~10 min.
- Phase 2 (implementation): ~15 min.
- Phase 3 (self-review, gates, mutation-verify, doc sweep): ~15 min.
- Phase 4 (this report): ~5 min.
- Total: ~45 min wall clock. Estimated cost: small task, low token volume relative to context loaded (mostly reading, few large edits) -- rough estimate under $1 at current Sonnet pricing.
