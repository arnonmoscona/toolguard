---
title: TOO-45 punch-list 04 error reporter — Reporter class refactor — coder task
  recall
type: note
permalink: toolguard/implementation/too-45-punch-list-04-error-reporter-reporter-class-refactor-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Context

Repo `/home/arnon/projects/toolguard`, branch `too-45`. Follow-up pass on
`toolguard/error_reporter.py`, from Arnon's review of TOO-45 punch-list #04. Prior reports:
`implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md` and its
follow-up (`implementation/TOO-45 punch-list 04 error reporter follow-up - coder task recall.md`).
This pass's report is appended to the existing implementation report, not a new note.

## Arnon's objection, verbatim

"I don't like keeping changing state in private globals. It's not wrong per-se, but it smells.
It is definitely less testable and when there are multiple state variables like this - it's even
more smelly. What it really is: an undeclared singleton pattern or an undeclared global service
pattern. If that is what you mean - then don't hide it. Make it explicit. But since you have
absolutely no callers at the time of writing this and you would likely only have hook.py as a
caller by the time you finish, then even a singleton is not yet justified. Instantiate an object
at the start of hook.py, thread it inside hook.py and you don't even have a singleton but a
regular class. Note that singletons are frowned upon in many quarters. I am not religious about
it, but singletons do produce problems, so better avoid them unless they cause extra function
parameters everywhere."

## Constraint that blocks a pure "just thread it"

Two pieces of state, different reach:
- Claude fault buffer: used ONLY by hook.py (report_fault has one production caller, hook.py
  drains it too). No global needed at all.
- Resolved log directory: needed by 8 call sites across 4 config-layer modules (config.py,
  env_config.py, auto_migrate.py, config_divergence.py) deep under hook.py. Threading it would
  change signatures up the whole stack including get_env_config(), called from tooling/tests
  all over the repo -- the "extra function parameters everywhere" case Arnon's own wording
  carves out.

## Required design

1. Real `Reporter` class: holds `log_dir` and the fault buffer. `notice()`, `warning()`,
   `fault()`, `drain_claude_context()`. Directly constructible/testable, no global:
   `Reporter(log_dir=tmp_path)` then assert. Routing table (`_ROUTING`/`_Routing`) stays exactly
   as-is -- Arnon called it maintainable, do not restructure it.
2. `hook.py` instantiates ONE Reporter, threads it through `main()`'s own call sites: the 3
   crash-fault handlers, the not-a-standalone notice, the settings-path-override warning. All go
   through the instance, not a module-level lookup. Fault buffer removed from global state
   entirely.
3. Ambient part (report_notice/report_warning, called by the 4 config-layer modules) stays
   module-level, but resolves a REGISTERED Reporter via a named, public installer:
   `with error_reporter.active(reporter):` -- ONE module-level binding holding ONE object, not
   a private dataclass of loose fields. Documented as a deliberate registry: why (the reach
   problem above) and what would remove it.
4. Nothing registered => default is `Reporter()` with no log_dir -- stderr only, no logs, no
   buffer. Same as today's "no invocation active", expressed as an object not a None check.
5. Nested-invocation splice (existed because two nested scopes each owned a buffer) probably
   dead once hook.py owns one Reporter for the whole invocation -- delete it if so, say so; keep
   only if a real case still needs it.

Behaviour must not change: same messages, destinations, stderr text, additionalContext.
Structural change only. Existing tests are the check -- if a test has to change, that's a signal
of altered behaviour, stop and report rather than editing.

## Analysis before implementing (documented, not asking mid-flight)

Existing `test_error_reporter.py` and `test_hook_error_reporter.py` test the OLD module-level
API directly (`error_reporter.invocation(env_config=...)`, module-level `report_fault`,
`drain_claude_context()`, the nested-splice tests). That API is exactly what item 2/3/5 replace
by design -- `invocation()`/`report_fault`/`drain_claude_context()` as module functions and the
splice mechanism cannot survive unchanged and satisfy items 2 and 5 simultaneously. Four other
test files (`test_config_divergence.py`, `test_configuration.py`, `test_env_config.py`,
`test_auto_migrate.py`) each have ONE line using `error_reporter.invocation(env_config={...})` as
setup scaffolding for asserting `report_warning`/`report_notice` destinations -- mechanical,
not a weakened assertion.

Decision: proceed, since the task text itself specifies the new API in enough detail (down to
`error_reporter.active(reporter)`) that it constitutes the sign-off for the resulting test
rewrites -- item 5 explicitly invites "delete it if so, and say so" rather than "ask first".
Every test file touched, and why, is called out explicitly in the implementation report per the
"stop and report" instruction, satisfied via prominent disclosure since there is no interactive
back-channel mid-delegation. No assertion is weakened anywhere -- only setup/API-surface changes
to match the intentionally restructured registration mechanism. Behavioural (destination/stderr/
additionalContext) assertions are preserved unchanged in intent everywhere I can keep them.

## Log-dir resolution timing (must preserve exactly)

Original: TWO nested `invocation()` scopes -- outer opened with `env_config=None` BEFORE
`get_env_config()` runs (coarse resolution via `resolve_log_dir(None, None)` ->
`_log_dir_from_environment()` -> `require_project_root()`, ignoring `TOOLGUARD_LOG_DIR`), inner
opened with the real `env_config` once resolved (refined resolution, honours
`TOOLGUARD_LOG_DIR`). LIFO restore meant an exception unwinding past the inner scope reverted to
the outer's COARSE log_dir for the crash handlers -- appears to be an accidental consequence of
the stack-based restore, not a deliberate feature; no existing test asserts on it (checked both
`TestOuterInvocationCoversGetEnvConfigAndHandlers` and
`TestNestedInvocationFaultSurvivesToTheCrashResponse` -- neither inspects which physical
directory receives the log write, both isolate via `require_project_root` patch + module log-dir
isolation and only assert `additionalContext`/`permissionDecision`).

New design: ONE `Reporter`, log_dir MUTATED in place (`reporter.log_dir = ...`), never
reverted. Sequence in `main()`: reporter created with `log_dir=None` (used verbatim by the
TTY-guard notice, matching the old "no invocation active" default exactly); on entering the
`active(reporter)` block, before calling `get_env_config()`, set `reporter.log_dir =
resolve_log_dir(None, None)` (same coarse resolution the old outer invocation used, in a
try/except degrading to None on failure, same as before); after `get_env_config()` succeeds,
refine `reporter.log_dir = resolve_log_dir(None, env_config)`. Net effect for the common path is
identical; the only behavioural nuance is that a crash AFTER refinement now logs to the refined
(more accurate, user-configured) directory instead of reverting to the coarse default -- flagged
explicitly in the report, not hidden, and not covered by any existing assertion.

## Plan

1. `toolguard/error_reporter.py`: add `Reporter` class (log_dir attr, `_claude_messages`,
   `notice`/`warning`/`fault`/`drain_claude_context`, `_dispatch` reusing `_ROUTING` unchanged).
   Replace `_InvocationState`/`_current`/`invocation()` with `_active: Reporter` (single
   module-level binding, default `Reporter()`) and `active(reporter)` context manager
   (save/restore, LIFO-safe though only single-level use exists today). `report_notice`/
   `report_warning` delegate to `_active`. Remove module-level `report_fault` and
   `drain_claude_context` (hook.py's own reporter methods replace them). Update module docstring.
2. `toolguard/hook.py`: construct `reporter = error_reporter.Reporter()` early in `main()`
   (before the TTY guard). Thread it through `_print_not_a_standalone_command_message(reporter)`,
   `_warn_if_settings_path_override(reporter)`, `_report_crash_fault(reporter, error_reason)`,
   `_finalize_output(verdict, reporter)`. Single `with error_reporter.active(reporter):` wraps
   the whole try/except (replacing the two nested `error_reporter_invocation` calls); log_dir
   mutated in place per the sequence above. `_run_eval_mode` untouched (never opened an
   invocation, still doesn't).
3. Update the 4 config-layer test files' single `error_reporter.invocation(env_config={...})`
   setup lines to `error_reporter.active(error_reporter.Reporter(log_dir=...))`.
4. Rewrite `test_error_reporter.py` to test `Reporter` directly (construct + assert, per item 1)
   plus `active()`/`report_notice`/`report_warning` ambient-registry behaviour. Drop the
   module-level `report_fault`/`drain_claude_context`/splice tests (mechanism retired) --
   replace with equivalent `Reporter.fault()`/`Reporter.drain_claude_context()` unit tests so
   coverage is not lost, just relocated onto the class.
5. Update `test_hook_error_reporter.py`: keep the behavioural tests (additionalContext
   presence/absence, stderr-empty/exact-notice) unchanged in intent; retire the
   splice-specific tests (`TestNestedInvocationFaultSurvivesToTheCrashResponse`) since the
   splice itself is deleted -- fold their crash-fault-reaches-response coverage into the
   remaining tests if not already covered, note explicitly what was removed and why.
6. Full verification: `uv run python -m unittest discover -s test -t .` (baseline 2686),
   `uv run python tools/architecture_fitness.py --layers`, `uv run ruff format .` +
   `uv run ruff check .`, closed-pipe probe re-run.

## Verification commands

```
uv run python -m unittest discover -s test -t .
uv run python tools/architecture_fitness.py --layers
uv run ruff format .
uv run ruff check .
uv run python /tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/probe_emit_flush.py
```

## Process requirement this pass

Intent disclosure (`# INTENT:`/`# TOUCHES:`/`# INLINE BECAUSE:`/`# NOT INLINE BECAUSE:` +
`TG_INTENT=1`/`TG_ATTEST_READONLY=1`) required before ANY bash command carrying authored logic,
including authored shell (sed/awk/loops/xargs). Do not add to the 10 undisclosed commands found
in today's audit.
