---
title: Coder Latest Task Recall
type: note
permalink: toolguard/toolguard-memories/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
---

# Task: comment/docstring rewrite of `toolguard/error_reporter.py`

Single-file pass under the TOO-45 comment standard (`TOO-45 comment standard.md`).
Comments and docstrings only — no code-shape changes, no string changes. Only
`toolguard/error_reporter.py` and `toolguard-memories/TOO-45/reports/follow-up-queue.md`
may be touched. `technical-notes.md` is off-limits (concurrent agents) — no pointers
into it; propose additions verbatim in the report instead (none were needed here).

Two known-and-flagged issues in this module, told not to fix and not to describe as
already fixed:
- `_ROUTING`'s `stderr_fallback` column does not control stderr on the logged path —
  `error_log._log_entry` echoes unconditionally.
- `_dispatch` uses `getattr(error_log, rule.log_fn_name)`, so those calls have no
  static caller. Not to be documented as a virtue.

Acceptance: `tools/comment_hygiene.py --compare-against HEAD` zero drift for this
file; full suite (2733 tests) green; golden verdict corpus byte-identical; ruff
format/check clean; no git writes.

## Outcome
Rewrote module docstring, `_Routing`/`_ROUTING`, `Reporter` class docstring,
`_dispatch`'s except-branch comment, `_print_fallback` docstring, and `active()`'s
docstring. Cut all TOO-45/punch-list/item-N ticket narrative. Removed a stale,
outward-reaching claim (module docstring said "four config-layer modules, 8 call
sites" — actual count verified as five modules, twelve call sites, so cut the
enumeration entirely per Rule 0 rather than correcting it to a number that will
drift again). Fixed a false universal in `_print_fallback`'s docstring (claimed
the fallback and logged echo "render identically" — false when `corrective_steps`
is empty, since `error_log._log_entry` always prints that line and `_print_fallback`
only does when truthy). Corrected the `_ROUTING` table's "the one thing to read or
edit to change policy" claim, which is false for the reason the task flagged.
Verified true and kept: `patch.object(error_log, "log_warning", ...)` test-patching
claim (confirmed against `test_error_reporter.py::test_dispatch_calls_whatever_is_currently_bound_on_error_log`),
the takeover-mode-notice/`session_warnings.py` asymmetry (confirmed against that
module).

Full suite green (2733), comment_hygiene zero drift for this file (only
`tools/architecture_fitness.py` differs, pre-existing/unrelated), ruff clean.

Follow-up queue: added item 7 — `permission_migration.py`'s `_EXIT_CODES` comment
quotes `_ROUTING`'s old (now-corrected) "one table, one place to change" framing;
now a stale cross-file analogy, out of scope for this single-file pass.

## Follow-up round: cold-review fixes (2026-08-11)

Coordinator sent judge report `R-error-reporter-1.md`, section 6, items 1-5 and 7
(item 6 is `permission_migration.py` — out of scope, recorded only). Applied:

1. (2.1) Module docstring: dropped "no throttling question" — false; throttling is
   `once_per`'s and the caller's job, not this module's, verified via `config_divergence.py`/`auto_migrate.py` `once_per.day(...)` gates.
2. (2.2) `stderr_fallback` first sentence: was wrong-half ("or the write itself
   failed" named the case where the fallback does NOT fire — `error_log._log_entry`
   catches its own write failure internally and returns normally). Rewrote to the
   three real firing conditions: no log stream, log call didn't run (no `log_dir`),
   or it raised.
3. (2.3 + §3) `notice` TEMPORARY paragraph: cut to the one load-bearing clause
   (deliberate, no log stream, don't tidy). Removed the false "on every tool call"
   universal (takeover notice only fires in takeover-mode projects) along with the
   rest of the planning narrative.
4. (§4, the one restoration) Module docstring: restored the real reason for the
   ambient registry — `get_env_config()` entered from many places besides the hook
   (verified: 8 files call it, not just `hook.py`) — and dropped the false "only"
   from "reached only through several layers".
5. (2.5) `_dispatch` docstring: "Never raises into the caller" overclaimed past what
   `except Exception` guarantees (BaseException, unguarded `print` calls). Softened
   to "Swallows a failing log write rather than propagating it".
7. (2.6/§3, optional) "no process-wide state" -> "no shared/global state" (exact,
   per judge). Removed the duplicated output-shape fact from `stderr_label`,
   pointing to `_print_fallback` as its single home instead.

**New finding during the mandated full re-verify pass (not on the judge's list):**
`Reporter`'s own docstring claimed `log_dir=None` means "no Claude buffer" — false.
`_dispatch`'s `reaches_claude` check is unconditional on `log_dir`; the named test
`test_fault_still_reaches_claude_with_no_log_dir` proves `fault()` still populates
the Claude buffer with no `log_dir` set. Fixed: the safe-fallback sentence now
covers logging only, with a separate clause stating the Claude buffer is
independent state that still accumulates `fault()` calls regardless of `log_dir`.

Item 6 (`permission_migration.py:94-96`) — not touched, recorded for the
coordinator to route: the `_EXIT_CODES` comment quotes `_ROUTING`'s old "one table
to read, one place to change" phrasing, which this pass corrected away as false.
The quoted phrase now exists nowhere in the repo and the parenthetical re-asserts
a claim already found wrong, plus a second rule-1 "mirrors Z" violation. Fix belongs
in that file: drop the parenthetical; `_EXIT_CODES`'s own `DECLINED_LOCKED != 2`
rationale stands alone.

Also worth queuing per the judge (outside this file, not actioned): the same stale
"four config-layer modules" figure survives at `hook.py:1239` and
`test/unit/test_error_reporter.py:331` (actual count is five).

Verification after this round: `tools/comment_hygiene.py --compare-against HEAD`
zero drift for `error_reporter.py`; `ruff format`/`ruff check` clean; full suite
2733 tests, OK.
