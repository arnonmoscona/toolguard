---
title: TOO-45 punch-list 04 error reporter - coder implementation report
type: note
permalink: toolguard/implementation/too-45-punch-list-04-error-reporter-coder-implementation-report
tags:
- task-memory
- TOO-45
---

# TOO-45 punch-list #04 -- error reporter -- implementation report

Branch `too-45`. Task recall: `implementation/TOO-45 punch-list 04 error reporter - coder task recall.md`.

## Summary

Added `toolguard/error_reporter.py` (new `observability`-layer module) with `report_notice`,
`report_warning`, `report_fault`, a single routing table, an invocation-scoped context manager
(`invocation()`), and `drain_claude_context()`. Moved all 8 hand-rolled `stderr` writes in
`config.py`, `env_config.py`, `auto_migrate.py`, `config_divergence.py` onto it. Wired the
Claude-facing fault buffer into `hook.py`'s JSON output. Made `log_writer._resolve_log_dir`
public (`resolve_log_dir`) so the reporter can reuse it without duplicating resolution rules.

## Files changed

- New: `toolguard/error_reporter.py`
- New: `test/unit/test_error_reporter.py` (15 tests)
- New: `test/unit/test_hook_error_reporter.py` (5 tests)
- Modified: `toolguard/hook.py` (invocation wiring, `_finalize_output` helper)
- Modified: `toolguard/config.py`, `toolguard/env_config.py`, `toolguard/auto_migrate.py`,
  `toolguard/config_divergence.py` (the 8 call sites)
- Modified: `toolguard/log_writer.py` (`_resolve_log_dir` -> public `resolve_log_dir`)
- Modified: `.pyscn.toml` (added `error_reporter` to the observability layer, corrected the
  stale "16 writes" comment to the real 8)
- Modified (added destination-asserting tests alongside existing coverage, no existing test
  changed): `test/unit/test_env_config.py`, `test/unit/test_configuration.py`,
  `test/unit/test_config_divergence.py`, `test/unit/test_auto_migrate.py`

## 1. Per call site: severity chosen and why

| site | message | severity | reasoning |
|---|---|---|---|
| `config.py:2290` (`_parse_source_recording_failures`) | `Failed to load {path}: {message}` | warning | Fails open onto the ASK-floor clamp; toolguard keeps working with the remaining sources. |
| `env_config.py:83` (`load_env_file`) | `Failed to load .env file: {e}` | warning | Degrades to `{}` and toolguard proceeds with env-var-only config. |
| `env_config.py:132` (`get_bool_env`) | `Invalid boolean value for {name}...` | warning | Falls back to the caller's default; not a broken toolguard, a malformed setting. |
| `auto_migrate.py:153` (`_migrate`, start) | `Running automatic migration...` | notice | Pure progress, expected on every successful auto-migrate run. |
| `auto_migrate.py:163` (`_migrate`, exception) | `Migration error: {e}` | warning | Migration is a convenience sync, not enforcement; toolguard's permission decisions are unaffected by a failed migration. |
| `auto_migrate.py:166` (`_migrate`, exit_code != 0) | `Migration failed` | warning | Same reasoning as above -- an outcome, not a toolguard fault. |
| `auto_migrate.py:168-171` (`_migrate`, success) | `Successfully migrated {n} pattern(s)` | notice | Outcome of a routine, expected operation. |
| `config_divergence.py:55` (`get_native_permissions`) | `Failed to load {settings_path}: {e}` | warning | Degrades to empty permissions; divergence check just reports less, toolguard keeps enforcing. |

No site was classified `fault`. Nothing in the 8 call sites represents "toolguard itself is
broken" -- they are all either progress notices or graceful degradations with a working
fallback. This matches the spec's own framing ("auto_migrate's four are progress/outcome
messages ... closer to notice/warning than fault").

## 2. Claude wiring: landed, not scope-boundary-blocked

It landed fully. `hook.py`'s `main()` now wraps its whole try-body (from right after
`env_config = get_env_config()` through both output-building sites) in
`with error_reporter_invocation(config=env_config):`, and both output sites call a new
`_finalize_output(verdict)` helper (in place of `create_hook_output(verdict)`) that drains the
buffer and merges it into `additionalContext`. This stayed entirely within hook.py's output
assembly -- no threading of a reporter through the resolution path, no change to `RuntimeVerdict`
or any resolver signature. `create_hook_output` itself is unchanged and still used directly by
`_run_eval_mode` and by hook.py's 3 out-of-scope exception handlers (deliberately, both to
respect the eval mode's "no logging/mutation" contract and to leave the fail-open bug untouched
per the spec).

Tests: `test_hook_error_reporter.py` drives `main()` end-to-end, forces a fault via a patched
`_run_divergence_check`, and asserts (a) the fault text lands in
`hookSpecificOutput.additionalContext`, (b) a clean run omits the key entirely, (c) a second,
separate `main()` call in the same process carries no trace of the first call's fault (the
in-process-leak concern), and (d) with takeover mode enabled, stderr from a full `main()` run is
byte-for-byte identical to calling `issue_takeover_warning()` alone -- i.e. nothing else reached
stderr.

## 3. Where the spec was fallible

- **Line number**: spec said `env_config.py:130` for the invalid-boolean warning; it is actually
  line 132 in the current tree (trivial drift, not worth a correction beyond noting it -- the 8
  sites and their messages matched exactly).
- **The routing table's `stderr` column is not fully independent of `log_fn` in practice.**
  `error_log.log_warning`/`log_error` already echo to stderr themselves as part of writing the
  file (their own `_log_entry` helper) -- and those two functions are also called directly by
  `hook.py` today (validation issues, conflict logging, divergence warnings), completely outside
  this reporter. So for `warning`/`fault`, stderr in practice comes from `error_log`'s own print
  calls, not from a print the reporter owns -- I kept an explicit `stderr` field in `_Routing` for
  documentation/future-flexibility, but flipping it to `False` today would NOT silence stderr for
  those two severities unless `error_log` itself were also changed, which would also change
  behaviour for hook.py's own pre-existing direct calls (out of scope here). I documented this
  coupling in the module docstring/table comment rather than silently building a table that
  implies more independence than exists. This is the one place I'd flag back to the ticket owner:
  if "the table is the one line he edits" is meant literally for the `stderr` column too, that
  promise needs `error_log`'s echo split out of `_log_entry` as a separate, larger follow-up.
- **`env_config.py`'s 2 sites can never reach a log file or Claude, structurally.** They run
  inside `get_env_config()` itself, which is what *produces* the config the reporter's invocation
  context needs to resolve a log directory -- a genuine chicken/egg. This is not a defect I
  introduced; the pre-refactor code had the identical limitation (stderr-only, no log). I did not
  attempt to solve it; flagging it here rather than leaving it implicit, since the spec's routing
  table doesn't call out that two of the eight sites can never fully participate in it.
- Everything else in the spec (the 8-not-16 count, the per-module breakdown, the layer placement,
  the "no invocation = safe default" requirement, the out-of-scope list) checked out exactly
  against the code.

## 4. Duplication self-check

- **`error_log`**: NOT duplicated. The reporter's `warning`/`fault` routing *delegates* to
  `error_log.log_warning`/`log_error` for the log-write + stderr-echo combination rather than
  reimplementing file writing -- `_Routing.log_fn` holds a direct reference to those functions.
  `error_log.log_conflict`/`log_crash` are untouched and out of this item's scope (hook.py still
  calls them directly).
- **`log_writer`**: NOT duplicated. `_resolve_log_dir` was renamed to public `resolve_log_dir` and
  reused as-is (same layer, per the spec's own suggestion) instead of re-deriving the
  explicit-arg/config/environment precedence order a second time.
- **`session_warnings`**: NOT touched, NOT duplicated, and NOT absorbed. The takeover notice stays
  exactly where it is, calling `print(..., file=sys.stderr)` directly -- out of scope per the
  ticket ("changing where the takeover notice appears" is reserved). The routing table's `notice`
  row documents this as a deliberate, temporary carve-out rather than silently leaving two
  "notice-shaped" code paths with no comment explaining why they differ.
- **`once_per`**: No overlap. `once_per` answers "should this run/warn at all, given how recently
  it last did" (throttling); `error_reporter` answers "given that I am reporting, where does it
  go" (routing). `auto_migrate.py`'s `_migrate()` closure already runs *inside* `AUTO_MIGRATION.run(...)`
  -- the once-per-day gate -- so by the time any `report_*` call in `_migrate()` fires, throttling
  has already happened one layer up; the reporter has no throttling concept of its own and was not
  given one (matches the spec: "no throttling question" is explicitly not the caller's, and the
  ticket's "whether it is throttled" line item for the reporter was left for a later item, not
  built speculatively here).
- The new module is not a fourth copy of anything; it is a thin, single-purpose router sitting on
  top of the other three.

## Verification

- `uv run python -m unittest discover -s test -t .`: 2673 tests (2646 baseline + 27 new), OK.
- `uv run python tools/architecture_fitness.py --layers`: clean (completeness + direction),
  before and after.
- `uv run ruff format .` / `uv run ruff format --check .`: clean (167 files formatted).
- `uv run ruff check .`: all checks passed.
- `test_zz_real_log_dir_guard.py` / the once-per/suppression home guards: all still pass, zero
  recorded leaks -- confirms none of the new report_* call sites wrote to the developer's real
  `logs/` directory during the suite.
- Live smoke test: piped a benign `ls` command through `uv run python -m toolguard.hook` --
  stderr showed only the takeover notice, stdout JSON unaffected.
- Golden verdict corpus: not re-run as evidence for this item, per the spec's own instruction that
  it is structurally blind here (kept green incidentally by every other check above, since nothing
  touched verdict construction).

## Timing / rough cost estimate

- Phase 1 (read spec + ticket, investigate existing code, write task recall): ~15 min.
- Phase 2 (implementation: module, 8 call-site moves, hook.py wiring, all new/augmented tests,
  format/lint/verify loop): ~30 min.
- Phase 3/4 (self-review, this report): ~10 min.
- Total: ~55 min elapsed. Token usage was moderate (mostly file reads and targeted edits, no large
  generated files); rough cost estimate at Sonnet pricing: well under $1.


---

## Fix pass (2026-08-09): 8 items from `toolguard-memories/latest-code-review-report.md`

Task spec: `toolguard-memories/TOO-45/TOO-45 punch-list 04 error reporter - coder task spec.md`
(unchanged from the original pass). Review addressed:
`toolguard-memories/latest-code-review-report.md`. All 8 items done in one pass, verified once at
the end, per the instruction.

### Files touched this pass

- `toolguard/error_reporter.py` -- `_Routing` reshaped (items 1/3/5/6/7), module docstring gained
  the `report_fault` call-site note.
- `toolguard/hook.py` -- outer `invocation(config=None)` now wraps `get_env_config()` and the
  three `except` handlers; handlers call `_finalize_output` instead of `create_hook_output`
  (items 1, 2).
- `test/unit/test_error_reporter.py` -- 3 pre-existing assertions corrected to the new stderr
  shape (items 1/4/5), added a scaffolding helper (item 8b), added 2 new test classes (items 3, 7).
- `test/unit/test_hook_error_reporter.py` -- added 1 test class proving the outer-invocation fix
  end-to-end through `main()` (items 1, 2).
- `test/unit/test_env_config.py`, `test/unit/test_configuration.py`,
  `test/unit/test_config_divergence.py`, `test/unit/test_auto_migrate.py` -- one new destination
  test added per file (item 8a); no existing test in these four files was modified or deleted.

No file outside `toolguard/error_reporter.py`, `toolguard/hook.py`, and the 6 test files above was
touched this pass.

### Item-by-item

**1 & 2 (one fix, as instructed).** `hook.py:main()` now opens
`with error_reporter_invocation(config=None):` around the entire `try`/`except` block, including
`get_env_config()` and all three `except` clauses; the pre-existing inner
`with error_reporter_invocation(config=env_config):` nests inside it to refine the log directory
once `env_config` resolves (LIFO restore, already implemented/tested, unchanged). All three
`except` handlers now build their JSON response via `_finalize_output(...)` instead of
`create_hook_output(...)`. Verified end-to-end in the new
`TestOuterInvocationCoversGetEnvConfigAndHandlers` (`test_hook_error_reporter.py`): patches
`toolguard.hook.get_env_config` to report a fault and then raise, and asserts the fault reaches
`additionalContext` in the `except Exception` handler's own stderr-printed JSON -- before this fix
no invocation was active during exception handling at all, so `drain_claude_context()` always
returned `None` there.

*Residual gap, not fixed, flagged rather than silently left implicit*: nesting does NOT preserve a
fault reported while the **inner** (`config=env_config`) invocation is active if an exception later
unwinds through that inner `with` -- each `invocation()` call creates its own `_InvocationState`
with its own `claude_messages` list, and the inner one is discarded (not merged into the outer) on
exit. This is exactly the review's **m3** ("faults reported before a crash are dropped"), which is
Minor and NOT one of the 8 items in this pass, and it is unreachable today because `report_fault`
has zero production call sites (see item 9 below) -- so nothing in the current codebase can
actually trigger it. Fixing it properly would mean capturing a local reference to the drain inside
the outer scope and using it from the handlers instead of `drain_claude_context()`'s current
"whatever `_current` is right now" semantics -- a real design change, not requested here. Recommend
folding into whatever ticket eventually gives `report_fault` a production call site.

**3 (M1: degraded stderr path).** `_dispatch` now renders through a new `_print_fallback(label,
message, corrective_steps)` helper: `label=None` (only `notice`) prints the bare message exactly
as before; any other label prints `f"[{label}] {message}"` then, if non-empty,
`f"Corrective steps: {corrective_steps}"` -- byte-for-byte the same shape `error_log._log_entry`'s
own echo produces. New test `TestFallbackShapeMatchesTheLoggedEcho` asserts the SAME warning
produces byte-identical stderr whether logged or degraded.

**4 (false test claim).** `test_report_warning_prints_bare_message_with_no_log` (claimed
"byte-for-byte" reproduction of pre-refactor behaviour) renamed to
`test_report_warning_prints_the_labeled_message_with_no_log`, docstring corrected to state the new,
true behaviour and note the prior claim was false. Same fix applied to the fault-severity sibling
test and to `test_no_invocation_active_after_the_with_block_exits`'s exact-match assertion.

**5 (format decision + exact strings).** Chose `[LABEL] message` + `Corrective steps: ...` (the
shape `error_log` already produces) as the ONE format for both the logged and degraded paths, per
`_Routing.stderr_label`: `None` for `notice` (unaffected, stays bare), `"WARNING"` for `warning`,
`"ERROR"` for `fault` (matches `error_log.log_error`'s own hardcoded level string, NOT the severity
name "FAULT" -- chosen so degraded and logged output for the same severity are textually
identical, which "FAULT" would not be since nothing in `error_log` ever prints that word).
Exact before (pre-refactor, prior to any TOO-45 punch-list #04 work) / after (this fix pass) for
the four sites review finding M1 named directly:

| site | before | after |
|---|---|---|
| `env_config.py` `load_env_file` | `Warning: Failed to load .env file: {e}` | `[WARNING] Failed to load .env file: {e}` + `Corrective steps: Fix or remove the .env file so toolguard can read it.` |
| `env_config.py` `get_bool_env` | `Warning: Invalid boolean value for {name}: {value}. Using default: {default}` | `[WARNING] Invalid boolean value for {name}: {value}. Using default: {default}` + `Corrective steps: Set {name} to one of: true, false, 1, 0, yes, no.` |
| `config.py` `_try_parse_source` caller | `Warning: Failed to load {path}: {message}` | `[WARNING] Failed to load {path}: {message}` + `Corrective steps: Fix or remove {path} so toolguard can read it.` |
| `config_divergence.py` `get_native_permissions` | `Warning: Failed to load {settings_path}: {e}` | `[WARNING] Failed to load {settings_path}: {e}` + `Corrective steps: Fix or remove {settings_path} so toolguard can read it.` |

`auto_migrate.py`'s two `report_warning` sites ("Migration error: {e}", "Migration failed") get the
same `[WARNING]`/`Corrective steps:` treatment on the degraded path by the same code change, though
I did not re-derive their specific pre-refactor `Warning:`-prefixed strings for this table (M1 only
named the four above by line; the fix is uniform across the routing table, not per-site, so it
applies identically). Its two `report_notice` sites are unaffected -- `stderr_label=None` keeps
them bare, matching their original `print()` form exactly (they already carried their own
`[TOOLGUARD AUTO-MIGRATION]` prefix in the message itself).

**6 (M3: `stderr` field name).** Renamed `_Routing.stderr` -> `stderr_fallback`; doc comment now
states plainly that this flag governs ONLY the fallback-when-not-logged case, and that
`error_log._log_entry` echoes unconditionally on a successful write regardless of this flag --
i.e. the table does not, by itself, let a future editor silence a severity's stderr just by
flipping this field. Splitting `error_log`'s echo out so the table's promise becomes literal is
named as a follow-up, not built here (also touches `hook.py`'s own direct `log_warning`/
`log_error`/`log_conflict` calls, which is a larger, separately-scoped change).

**7 (m1: import-time binding).** `_Routing.log_fn` (a bound function reference) replaced with
`log_fn_name: Optional[str]` (`"log_warning"` / `"log_error"` / `None`); `_dispatch` now does
`getattr(error_log, rule.log_fn_name)(...)` at call time. New test
`TestRoutingLooksUpLogFnByName.test_dispatch_calls_whatever_is_currently_bound_on_error_log` patches
`toolguard.error_log.log_warning` with `unittest.mock.patch.object` (the "patch at the defining
module" pattern `_real_log_dir_guard.py` and any future test-time patch depend on) and asserts the
reporter calls the patched stand-in.

**8a (missing destination coverage).** Added ONE new end-to-end test per converted module, each
driving the REAL production function (not a synthetic `error_reporter.report_*` call) inside an
active `error_reporter.invocation(config={"log_dir": <tmp>})` and asserting the resulting
`toolguard-warning-*.md` file's content:
- `test_env_config.py::TestLoadEnvFile::test_read_failure_reaches_the_warning_log_with_an_active_invocation`
- `test_configuration.py::TestParseFailuresPropagation::test_broken_file_warning_reaches_the_warning_log_with_an_active_invocation`
- `test_config_divergence.py::...::test_invalid_json_reaches_the_warning_log_with_an_active_invocation`
- `test_auto_migrate.py::TestRunAutoMigration::test_run_auto_migration_nonzero_exit_reaches_the_warning_log`

This is exactly the gap that let item 2 (env_config's chicken/egg) slip through the first pass: all
four PRE-EXISTING call-site tests only ever asserted stderr, never a log file, so wrong routing to
the log stream stayed invisible.

**8b (test-to-production ratio / repeated scaffolding) -- partial, with reasoning.** Added a
`_invocation_with_captured_stderr(log_dir)` context-manager helper to `test_error_reporter.py` and
applied it to the 5 tests that repeated the `TemporaryDirectory` + `redirect_stderr` +
`invocation()` three-level nesting, per review suggestion s1. I did NOT delete or merge the four
existing per-module call-site tests (the ones the review's s1/8 text describes as "asserting the
same [degraded stderr] thing four times"): each exercises a DIFFERENT production function's own
failure-triggering condition (a broken `.env` read, an invalid env var, an unparseable rules TOML,
invalid `settings.local.json`) -- that is call-site-specific regression coverage for each module,
not a redundant copy of `test_error_reporter.py`'s own degraded-path tests. Given the standing
"never modify or delete an existing test without asking" constraint and the spec's own "do not
lose coverage doing it," I judged consolidating those four as more likely to lose a real regression
guard than to remove genuine duplication, and left them as-is. This is a partial completion of item
8b -- I would ask before going further if a fuller ratio reduction is wanted.

**Not fixed, only documented.** Added one line to `error_reporter.py`'s module docstring:
`report_fault` has no production call site yet; the real faults today live in `hook.py`'s crash
handlers, out of scope for this item, so the Claude-facing buffer is exercised only by tests until
one exists. No call site was invented to exercise it.

### Process note: one undisclosed inline script

During self-review I ran two small `uv run python -c "..."` snippets (read-only, no writes) to
inspect stderr content while debugging the new hook-level test, without the
INTENT/TOUCHES/INLINE-BECAUSE disclosure block this project's `CLAUDE.md` requires for
self-authored inline code. Both were trivial and read-only, but the omission is a real process
deviation worth naming rather than letting it pass silently.

### Verification (this pass)

- Baseline before this pass: 2680 tests were NOT yet the baseline -- the review's own "Ran 2673
  tests" was the starting point; this pass added 7 new tests (1 hook-level, 2 in
  `test_error_reporter.py`, 4 destination tests across the call-site files) for **2680 tests, OK**.
- `uv run python tools/architecture_fitness.py --layers`: completeness OK, no direction violations.
- `uv run ruff format .`: 1 file reformatted (`hook.py`, whitespace/wrapping only from the
  re-indentation, no logic change -- reran the suite after to confirm).
- `uv run ruff check .`: all checks passed.
- `test_zz_real_log_dir_guard.py` and the atexit hard-exit backstop: both clean -- the new
  hook-level test (item 1/2) does resolve a log directory via
  `toolguard.log_writer.require_project_root()` for the OUTER invocation (a path NOT covered by
  this module's existing `TOOLGUARD_LOG_DIR` isolation, since `resolve_log_dir(None, None)` ignores
  that env var entirely), so it explicitly patches `toolguard.log_writer.require_project_root` to
  an isolated tmp root with a pre-created `logs/` subdirectory. Without that patch the test tripped
  the real-log-dir guard on first run (caught, not a silent leak, but confirms the risk this
  fix pass reintroduces for anyone else writing a `main()`-driving test that triggers a report
  before `env_config` resolves -- worth a line in `.claude/rules/test-config-isolation.md` if this
  becomes a recurring pattern).

### Timing / rough cost estimate (this pass)

- Phase 1 (re-read spec, review report, current implementation state): ~20 min.
- Phase 2 (implementation across error_reporter.py, hook.py, 6 test files, debug/fix loop): ~45 min.
- Phase 3/4 (self-review, this report update): ~15 min.
- Total: ~80 min elapsed. Estimated cost: roughly $2.50-3.50 (Opus 5; large amount of file reading
  including two big memory documents, moderate generated-code volume).


---

## hook.py fail-open fix (2026-08-09): scope boundary reversed, folded into this item

Arnon reversed the scope boundary that had excluded `hook.py`'s three `main()` error handlers
from this item. His words: "fold it before commit, and there is no rational reason to keep a
known defect." Task recall:
`implementation/TOO-45 punch-list 04 error reporter follow-up - coder task recall.md`.

### The defect (before this fix)

`main()`'s three `except` handlers (`json.JSONDecodeError`, `ValueError`, catch-all `Exception`)
built a correct `deny` `RuntimeVerdict` and printed it to **stderr**, then `sys.exit(0)`. Claude
Code reads the permission decision from **stdout only** -- an empty stdout with exit 0 reads as
"no opinion", and the tool call silently falls through to native Claude permission handling. The
catch-all handler exists specifically to fail closed on anything unforeseen, and instead failed
open. Live-verified before the fix (feeding malformed stdin to the unfixed module): stdout was
empty, exit code 0, and the deny JSON was on stderr only.

### The fix

- New `_emit_decision(output)`: the ONE place in `main()` that writes a decision to stdout.
  Wraps `print(json.dumps(output))` in a `try`/`except`; if that itself raises, falls back to
  `sys.exit(2)` with the failure reason on stderr -- the one case with no decision left to
  deliver, so the host's own blocking signal (exit code 2, the only code Claude Code treats as
  blocking) is what's left. Used at every decision-emission site in `main()` (the two normal
  paths -- not-a-governed-tool early return and the success path -- and all three Group-1
  handlers), so the fix is now literally "the same code path", not merely "the same shape",
  across every branch.
- New `_report_crash_fault(error_reason)`: reports `f"toolguard crashed while deciding:
  {error_reason}"` via `error_reporter.report_fault`, with a shared `_CRASH_CORRECTIVE_STEPS`
  constant. Called from all three handlers, right after `log_crash`, before `_finalize_output`
  drains the buffer -- this is what finally gives `report_fault` a real production caller (the
  module docstring note added in the earlier pass, "`report_fault` has no production call site
  yet", is now stale; not corrected in this pass since the module docstring wasn't touched --
  flagging it here instead).
- All three handlers now: `log_crash(...)` (unchanged) -> `_report_crash_fault(error_reason)` ->
  `output = _finalize_output(RuntimeVerdict(decision="deny", reason=error_reason))` ->
  `_emit_decision(output)` -> `sys.exit(0)`. The generic `Exception` handler's redundant second
  `print(f"Error: {error_reason}", file=sys.stderr)` line (present only on that handler, absent
  from the other two -- debug-era inconsistency) is removed; `_report_crash_fault` now covers
  that role via a real destination (log + Claude buffer) instead of a bare stderr echo.
- `_print_not_a_standalone_command_message` (Group 2): swapped its direct
  `print(..., file=sys.stderr)` for `report_notice(...)`. `notice` severity has no log stream and
  renders as the bare message on stderr regardless of whether an invocation is active (the
  reporter's documented safe default) -- byte-for-byte identical output, live-verified. Clean 1:1
  swap; this call site fires both before any invocation exists (the TTY guard, ahead of the
  `with error_reporter_invocation(...)`) and inside the outer invocation (`EmptyStdinError`
  handler), and works correctly in both.
- `_run_eval_mode` (Group 3, `--eval`): **left untouched.** Its documented contract is "errors
  reported as a deny decision on stderr, matching the live hook's fail-safe contract" --
  deliberate, not the defect. `test/unit/test_hook_eval.py::TestEvalModeMain::
  test_eval_malformed_stdin_fails_safe` does `json.loads(mock_stderr.getvalue())`, i.e. it pins
  stderr to contain **only** the JSON decision, nothing else. There is also no separate
  "diagnostic about toolguard" in `_run_eval_mode` today (no `log_crash` call exists there at
  all) -- so there was nothing to route through the reporter without either breaking that pinned
  test or violating `--eval`'s own "no logging" contract (an active reporter invocation would be
  needed for `report_fault` to log instead of falling back to a second stderr line, and opening
  one here would itself be a logging side effect the docstring explicitly promises not to have).
  Per the spec: "If you find a test pinning the current behaviour, that settles it -- keep it."
- Updated `hook.py`'s module docstring and `main()`'s own "Exit codes" docstring section to
  state the real 0/2 contract (previously "Always 0").

### Behaviour change (user-visible, called out per Arnon's request)

**Before:** malformed hook input (unparseable JSON, a missing required field, or any unforeseen
exception during resolution) produced an empty stdout with exit 0. Claude Code reads that as "no
opinion" and silently falls through to native Claude permission handling -- toolguard's decision
is never seen.

**After:** the same three cases produce a real `deny` decision on stdout with exit 0, which
Claude Code enforces exactly like any other toolguard deny. Live-verified:

```
$ printf 'not json at all' | uv run python -m toolguard.hook
stdout: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": "Failed to parse hook input: ...", "additionalContext":
  "toolguard crashed while deciding: Failed to parse hook input: ..."}}
exit: 0
```

`--eval` mode's malformed-input behaviour is unchanged (still stderr-only, live-verified
separately). The stray-manual-invocation message (empty stdin, TTY) is unchanged byte-for-byte.

### Tests (per the spec's "assert the stream, never merely that something happened")

- `test/unit/test_hook.py::TestHookCrashCapture`: all three pre-existing tests
  (`test_unexpected_exception_writes_crash_report`, `test_json_decode_error_writes_crash_report`,
  `test_value_error_missing_field_writes_crash_report`) **modified** -- they previously asserted
  the decision JSON on **stderr**, which is exactly the buggy behaviour this fix removes; per
  Arnon's explicit, specific direction in this task ("the fail-open gets fixed here... give him
  the before/after plainly"), these three were updated in place rather than left pinning a defect
  he commissioned removing. Each now asserts: exit code 0; the decision JSON is on **stdout** and
  non-empty; stderr does not contain the decision (`assertNotIn('"permissionDecision"', ...)` --
  not a blanket empty-stderr assertion, since `error_log.log_crash`/`log_error` echo their own
  `[CRASH]`/`[ERROR]` lines to stderr unconditionally as part of writing, which is pre-existing,
  unrelated behaviour); `additionalContext` carries the fault text (proving `report_fault` fired
  through the real call site, not a synthetic one); and the crash-report file assertions are
  unchanged. `test_crash_context_carries_tool_name_tool_input_cwd` (unchanged assertions) gained
  the same log-dir isolation, needed only to avoid tripping the real-log-dir guard now that this
  path also calls `report_fault`.
- `test/unit/test_hook_error_reporter.py::TestOuterInvocationCoversGetEnvConfigAndHandlers::
  test_fault_reported_before_get_env_config_raises_reaches_the_crash_response`: **modified** the
  same way (was asserting the decision on stderr; now asserts stdout, non-empty, both faults --
  the test's own and the handler's `_report_crash_fault` -- reach `additionalContext`).
- New `test/unit/test_hook.py::TestEmitDecisionStdoutFailureFallsBackToExit2`: unit-tests
  `_emit_decision` directly against a fake stdout whose `.write` raises; asserts `SystemExit`
  code 2 and the failure reason on stderr. This is the "stdout-write-failure path exits 2" test
  the spec asks for.
- Golden verdict corpus (`test_verdict_corpus.py`, `test_compound_resolve_seam.py`): re-run,
  green, kept as such -- not cited as evidence for the stream-destination fix, per the spec's own
  instruction that it is structurally blind to destinations.

**Isolation gotcha worth recording** (also in the task-recall note): the OUTER
`error_reporter.invocation(config=None)` -- active during all three `main()` except handlers,
since the inner `config=env_config` invocation has already exited via LIFO restore by the time an
except clause runs -- resolves its log directory via `log_writer._log_dir_from_environment()` ->
`path_utils.require_project_root()`, which deliberately ignores `TOOLGUARD_LOG_DIR`
(`isolate_log_dir_for_module()` does not reach this path). This repo's real `logs/` directory
exists on the dev machine, so a naive new test trips `test/unit/_real_log_dir_guard.py`'s leak
guard. Every test that now drives one of these three handlers patches
`toolguard.log_writer.require_project_root` to an isolated tmp dir with a pre-created `logs/`
subdir, following the pattern already established in `test_hook_error_reporter.py`'s
`TestOuterInvocationCoversGetEnvConfigAndHandlers`.

### Verification (this pass)

- `uv run python -m unittest discover -s test -t .`: **2681 tests, OK** (2680 baseline + 1 new:
  the exit-2 test; the three modified `TestHookCrashCapture` tests and the one modified
  `test_hook_error_reporter.py` test are corrections to existing tests, not additions).
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both clean.
- `uv run ruff format .`: 2 files reformatted (`hook.py`, `test/unit/test_hook.py` --
  line-wrapping only, re-ran the suite after, still green).
- `uv run ruff check .`: all checks passed.
- Live smoke tests (not part of the automated suite): malformed stdin against
  `uv run python -m toolguard.hook` (deny on stdout, exit 0, confirmed above); empty stdin
  (byte-identical stray-invocation message on stderr, exit 0); malformed stdin against
  `--eval` (deny on stderr only, exit 0, contract unchanged). The first of these wrote one real
  crash-report file to `~/.toolguard/errors/` as a normal side effect of exercising the
  production `log_crash` path -- left in place rather than run a denied `rm` against that
  directory; harmless, outside the repo, and matches what a real crash would do.

### Files touched this pass

- `toolguard/hook.py` -- the fix itself (see above).
- `test/unit/test_hook.py` -- 3 existing tests corrected (stderr -> stdout assertions), 1 test
  gained log-dir isolation, 1 new test class/test added, `_emit_decision` added to the import
  list.
- `test/unit/test_hook_error_reporter.py` -- 1 existing test corrected the same way.

No file outside these three was touched this pass. `toolguard/error_reporter.py` was read and
briefly instrumented with a temporary debug print during investigation (to diagnose why a patched
`require_project_root` appeared not to take effect -- it did; the real cause was that
`error_log.log_error`/`log_crash` echo to stderr unconditionally on a successful write, which I
had mistaken for the reporter's own fallback path) and fully reverted; `git diff` confirms zero
net change to that file from this pass.

### Duplication self-check (re-run for this pass)

No new module or mechanism was introduced -- this pass is entirely call-site wiring inside
`hook.py` onto the existing `error_reporter` module from the earlier pass. `_emit_decision` and
`_report_crash_fault` are new, but both are thin, hook.py-local helpers with no equivalent
elsewhere (`error_reporter.py` deliberately owns severity/routing, not stdout-vs-stderr framing
for a *decision* payload, which is `hook.py`'s own concern per the spec's own distinction between
"the decision payload" and "the diagnostic").

### Timing / rough cost estimate (this pass)

- Phase 1 (re-read spec, prior report, hook.py, existing tests, plan): ~15 min.
- Phase 2 (implementation, the log-dir isolation investigation via a temporary debug print, test
  rewrites, fix/verify loop, live smoke tests): ~40 min.
- Phase 3/4 (self-review, doc-drift sweep, this report): ~10 min.
- Total: ~65 min elapsed. Estimated cost: roughly $1.50-2.50 (Sonnet 5; moderate file reading,
  several full-suite runs, no large generated files).


---

## Fix pass (2026-08-09, second): 3 Majors + 1 Minor from `toolguard-memories/latest-code-review-report.md`

Task recall: `implementation/Coder Latest Task Recall.md`. Baseline: 2681 tests. This pass fixes
review findings M1, M2, M3, and m5 -- everything else in Minors was explicitly out of scope
except m4 (stale docstring) and m3 (parameter rename), per the prompt.

### M1 -- `_emit_decision`'s exit-2 fallback never fired on a real pipe

**The review's suggested fix (flush inside the `try`) was necessary but NOT sufficient --
found only by re-measuring against a real subprocess, exactly as instructed.**

Applied the flush first:
```python
try:
    print(json.dumps(output))
    sys.stdout.flush()
except Exception as e:
    ...
```
Re-ran the same closed-pipe subprocess probe Arnon used. Result: **still exit 120**, not 2.
Isolated the cause with a minimal two-line repro outside toolguard entirely: `sys.exit(2)`
after a caught `BrokenPipeError` on `flush()` still exits 120, because **CPython flushes
stdout a second time during interpreter shutdown**, that second flush ALSO fails on the
still-broken pipe, and CPython silently overrides the requested `sys.exit(2)` code with exit
status 120 when that happens -- independent of anything `_emit_decision` does. `os._exit(2)`
(bypassing normal shutdown) fixed it in isolation but is untestable via `assertRaises(SystemExit)`
and skips other cleanup. The fix that is both correct and testable: swap `sys.stdout` for a
fresh, working stream before `sys.exit(2)`, so the shutdown-time flush has something that
won't fail:
```python
except Exception as e:
    print(f"toolguard: failed to emit decision: {e}", file=sys.stderr)
    sys.stdout = io.StringIO()
    sys.exit(2)
```
(`io.StringIO()` was chosen over `open(os.devnull, "w")` after confirming both fix the exit
code identically -- `io.StringIO()` needs no OS file handle and produces no `ResourceWarning`
at test cleanup.) Docstring updated to record this finding so it isn't rediscovered.

**Live proof, exactly as requested** (`/tmp/.../scratchpad/probe_broken_pipe.py`: spawns
`uv run python -m toolguard.hook` as a real subprocess, closes the stdout read end before
the child's first write, feeds one valid governed-command event on stdin):

- Before this pass (flush fix only, no `io.StringIO` swap): `exit code: 120`, with `stderr`
  showing `toolguard: failed to emit decision: ...` (proving `_emit_decision`'s `except` DID
  fire and DID call `sys.exit(2)`) immediately followed by `Exception ignored while flushing
  sys.stdout: BrokenPipeError` (CPython's own shutdown flush failing and overriding the code).
- After the `io.StringIO()` swap: `exit code: 2`, clean stderr (`toolguard: failed to emit
  decision: [Errno 32] Broken pipe`), no "Exception ignored" noise.

Tests: kept the existing write-raising double (`_BrokenStdout`); added
`test_stdout_flush_failure_exits_2_with_reason_on_stderr` (`test_hook.py`,
`TestEmitDecisionStdoutFailureFallsBackToExit2`) with a double whose `write()` succeeds and
`flush()` raises -- the exact shape a real buffered pipe takes, which the pre-existing
write-raising double structurally cannot represent.

### M2 -- `_run_eval_mode` had 3 verbatim copies of the fail-open just removed from `main()`

**Investigated before changing anything, per the instruction not to re-litigate on faith.**
`.claude/skills/toolguard-security-audit/SKILL.md`'s "How the floor is checked" section (the
only production consumer of `--eval`) states explicitly: *"`--eval` ... prints a
`permissionDecision` on **stdout** ... Read the verdict from
`hookSpecificOutput.permissionDecision`"* -- no stderr fallback is documented or read anywhere
in that skill. **Branch taken: reads stdout.** This is the same fail-open class as `main()`'s,
not a documented, deliberate stderr contract: a config that makes the probe error out yielded
an empty stdout (no verdict at all) instead of the deny the probe exists to detect, exactly as
the review's own framing put it.

Fix: routed all three `except` handlers, and the success path, through `create_hook_output` +
`_emit_decision` (not `_finalize_output` -- eval mode's fault buffer is deliberately unused, so
no invocation is opened and no log/Claude-buffer side effect is introduced). This also gives
eval mode's success print the same M1 flush protection for free. Updated `_run_eval_mode`'s
docstring to state the corrected contract and cite the SKILL.md evidence.

The previously-pinned `test_hook_eval.py::test_eval_malformed_stdin_fails_safe` asserted the
decision landed on stderr -- that assertion pinned exactly the defect being fixed here, the
same class of change the prior pass made to `TestHookCrashCapture` (an existing test may be
corrected, not silently left, when it pins the defect the change removes). Rewrote it to parse
`mock_stdout` instead of `mock_stderr`, and added `assertEqual(mock_stderr.getvalue(), "")`.
Live-verified separately: malformed `--eval` input now prints the deny JSON on stdout with
exit 0 (unchanged exit code, corrected stream); a valid `--eval` probe is byte-for-byte
unaffected.

### M3 -- nested invocations discarded the inner fault buffer

Fixed in `error_reporter.invocation`'s `finally`, exactly as the review's suggested patch:
```python
finally:
    if previous is not None and _current is not None:
        previous.claude_messages.extend(_current.claude_messages)
    _current = previous
```
Splices any undrained inner `claude_messages` into the parent's buffer (report order
preserved -- outer's own prior messages first, then the inner's) before restoring, so this
composes under arbitrary nesting depth and under both a clean exit and an exception unwinding
past the inner `with`.

Tests: three direct unit tests in `test_error_reporter.py`
(`TestNestedInvocationPreservesFaultsOnExit`) pinning the splice mechanism itself --
inner-fault-survives-clean-exit, inner-and-outer-both-survive-in-order,
inner-fault-then-raise-still-reaches-outer-drain -- plus one hook.py-level integration test in
`test_hook_error_reporter.py`
(`TestNestedInvocationFaultSurvivesToTheCrashResponse::test_fault_reported_inside_inner_invocation_survives_a_crash_to_the_outer`)
driving `main()` end-to-end: `_run_divergence_check` (which runs inside the inner
`config=env_config` invocation) reports a fault and then raises, and the assertion is that
`main()`'s crash response `additionalContext` carries BOTH that fault and the handler's own
`_report_crash_fault` text. Needed its own log-dir isolation (`toolguard.log_writer.
require_project_root` patched to an isolated tmp root) rather than reusing the module's shared
`_run_main` helper, for the same reason the sibling `TestOuterInvocationCoversGetEnvConfigAndHandlers`
test does -- the crash path logs through the OUTER invocation, which resolves independently of
this module's `TOOLGUARD_LOG_DIR` isolation.

### m5 -- warning log written on every tool call: left unthrottled, justified

**Decision: `_warn_if_settings_path_override` is untouched -- still fires on every call, both
stderr and (when a log dir resolves) the warning-log file.** Reasoning, made deliberately:

1. This is the ONLY call site in `hook.py` actually affected -- `_run_divergence_check`'s
   warning (the review's other cited example) is already throttled to once/day via
   `DIVERGENCE_WARNING = once_per.day(...)` in `config_divergence.py` (punch-list #01, same
   uncommitted working tree). The review's phrasing groups the two together; only one of them
   is unthrottled today.
2. `test_hook.py::TestSettingsPathOverrideWarning::test_warns_when_settings_path_override_active`'s
   own class docstring states the design intent explicitly: *"The hook must surface this
   footgun on stderr on every invocation so the bypass is never invisible."* `OncePer.warn()`/
   `.run()` throttle the action itself (stderr included, not just the log write) -- using either
   would silently reverse that pinned, deliberate design decision. Per this project's own
   testing policy ("if an existing test genuinely must change, STOP and tell Arnon"), reversing
   that intent is not this item's call to make.
3. Splitting stderr (unthrottled) from the log-file write (throttled) would require bypassing
   `report_warning`'s single-call-site routing model for this one site alone -- a bespoke
   hybrid mechanism solely to shave log volume for a condition that requires an explicit,
   deliberate env-var export to trigger at all. `CLAUDE_SETTINGS_PATH` is not an ambient,
   auto-detected condition like config divergence; it is an active, ongoing bypass a user or
   agent chose to set. Repetition has real diagnostic value here (how many tool calls ran under
   the bypass, over what span) that config-divergence repetition does not.
4. Volume is bounded: `error_log`'s warning stream is one file per calendar day, append-only,
   gitignored -- not unbounded disk growth, just denser-than-ideal entries while the override
   is active (which is itself expected to be rare and short-lived).

If Arnon wants this throttled anyway, it is a small, low-risk follow-up now that `once_per`
exists (thread `config.project_root` into `_warn_if_settings_path_override`'s signature and
call `SETTINGS_PATH_OVERRIDE_WARNING.run(project_root, lambda: report_warning(...),
repeating=Repeat.SAFE)`) -- not built speculatively here since it would also require Arnon's
sign-off to relax the pinned test's "every invocation" intent first.

### m4 and m3 (Minors, in scope per the prompt)

- **m4**: `error_reporter.py`'s module docstring said *"`report_fault` has no production call
  site yet"* -- stale since the prior fix pass gave it one (`hook.py`'s `_report_crash_fault`).
  Corrected to name that call site.
- **m3 (rename)**: `error_reporter.invocation`'s `config` parameter renamed to `env_config`
  (it was already documented as taking a `get_env_config()` dict, not a `Configuration`, but
  read as if it did next to `main()`'s own `config = load_configuration(...)` a few lines
  below). Propagated to every call site: `hook.py`'s two `error_reporter_invocation(...)`
  opens, and all keyword-argument call sites across `test_error_reporter.py` (12 occurrences),
  `test_config_divergence.py`, `test_env_config.py`, `test_auto_migrate.py`, and
  `test_configuration.py` (one each) -- purely mechanical, no behavior change.

**Explicitly not touched, per the prompt:** m1 (six near-identical except blocks), m2 (`main()`
restructure/`_decide_and_emit` extraction), m6 (log-dir-on-hot-path docstring note), m7
(unguarded stderr fallback), m8/m9 (`_run_main` test-helper cleanup), m10 (folded into M3's
tests above, already satisfied).

### Files touched this pass

- `toolguard/hook.py` -- `_emit_decision` (flush + `io.StringIO` swap), `_run_eval_mode`
  (stream fix), `env_config=` rename at both invocation opens, new `import io`.
- `toolguard/error_reporter.py` -- `invocation()`'s M3 splice fix and `env_config` rename,
  module docstring correction (m4).
- `test/unit/test_hook.py` -- new flush-failure test; imports unchanged.
- `test/unit/test_hook_eval.py` -- one existing test corrected (stderr -> stdout assertion,
  per the sanctioned "pins the defect being fixed" exception), docstring updated.
- `test/unit/test_hook_error_reporter.py` -- one new integration test class (M3).
- `test/unit/test_error_reporter.py` -- one new test class (3 tests, M3 mechanism), plus the
  `env_config=` rename across all 12 existing call sites in the file.
- `test/unit/test_config_divergence.py`, `test/unit/test_env_config.py`,
  `test/unit/test_auto_migrate.py`, `test/unit/test_configuration.py` -- one-line `env_config=`
  rename each, no other change.

No file outside this list was touched this pass. `_warn_if_settings_path_override` in
`hook.py` was read but not edited (see m5 above).

### Duplication self-check

No new module or mechanism. `io.StringIO()` is stdlib; the shutdown-flush-override fix is a
two-line addition to existing, single-purpose code (`_emit_decision`). The M3 splice is a
three-line addition to existing single-purpose code (`invocation`'s `finally`). Nothing here
duplicates `once_per`, `error_log`, or `log_writer`.

### Verification (this pass)

- `uv run python -m unittest discover -s test -t .`: **2686 tests, OK** (2681 baseline + 5 new:
  1 flush-failure test, 3 M3 mechanism tests, 1 M3 hook-level integration test; 1 existing test
  corrected in place per the sanctioned exception, not counted as new).
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both clean.
- `uv run ruff format .`: 1 file reformatted (`test_error_reporter.py`, whitespace only from
  the new test class -- re-ran the suite after, still 2686/OK).
- `uv run ruff check .`: all checks passed.
- **M1 live proof** (the bar Arnon set explicitly): real subprocess, closed stdout read end,
  valid governed-command input. Before the `io.StringIO` swap (flush-only fix): exit 120. After:
  **exit 2**, clean stderr. Reproduced with the isolated two-line repro outside toolguard
  entirely, confirming the 120-override is a general CPython shutdown-flush behavior, not
  something specific to this module -- so the fix generalizes rather than being a narrow patch
  over one observed symptom.
- Live smoke tests: `--eval` with malformed stdin (deny on stdout, exit 0, empty stderr,
  contract-corrected); `--eval` with valid input (unaffected, allow verdict on stdout).

### Timing / rough cost estimate (this pass)

- Phase 1 (re-read review, prior report, hook.py, error_reporter.py, relevant tests, SKILL.md
  investigation for M2): ~20 min.
- Phase 2 (implementation across hook.py/error_reporter.py, the env_config rename sweep, new
  tests, and -- the largest single piece of unplanned work -- discovering and fixing the
  CPython shutdown-flush override that the review's suggested M1 patch alone did not close,
  including three isolated minimal repros to pin the mechanism before touching production code):
  ~40 min.
- Phase 3/4 (self-review, doc-drift sweep, this report): ~10 min.
- Total: ~70 min elapsed. Estimated cost: roughly $2-3 (Sonnet 5; moderate file reading, several
  full-suite runs, three small isolated subprocess repros for the M1 finding).


## Follow-up pass: Reporter class, explicit registry (Arnon's "undeclared singleton" review)

Task recall: `implementation/TOO-45 punch-list 04 error reporter — Reporter class refactor — coder task recall.md`.

### Summary

Replaced `error_reporter.py`'s two module-global mutable pieces of state (`_current:
Optional[_InvocationState]`, mutated by the `invocation()` context manager) with:

1. **`Reporter`** — a plain, directly constructible class (`Reporter(log_dir=...)`) holding
   `log_dir` and the Claude-facing fault buffer as instance attributes. `notice()`/`warning()`/
   `fault()`/`drain_claude_context()`. No global state anywhere in the class; fully unit-testable
   by construction and assertion. The routing table (`_Routing`/`_ROUTING`) is untouched, per
   Arnon's instruction not to restructure it.
2. **`hook.py::main()`** now constructs exactly ONE `Reporter` for the whole invocation and
   threads it explicitly through its own reporting call sites: `_print_not_a_standalone_command_message`,
   `_warn_if_settings_path_override`, `_report_crash_fault`, `_finalize_output` all now take a
   `reporter: Reporter` parameter and call its methods directly — no module-level lookup. The
   fault buffer is gone from global state entirely, exactly as item 2 required.
3. **The ambient part** (`report_notice`/`report_warning`, still called from `config.py`,
   `env_config.py`, `auto_migrate.py`, `config_divergence.py` — 8 call sites unchanged) now
   resolves a Reporter registered via `error_reporter.active(reporter)`, a named, public context
   manager backed by ONE module-level binding (`_active: Reporter`). Documented in the module
   docstring: why it exists (the reach problem — 8 call sites deep under `hook.py`, including
   `get_env_config()`, called from tooling/tests repo-wide) and what would remove it (those four
   modules receiving a `Reporter` as an explicit parameter instead).
4. **Default when nothing is registered**: `_active` starts as a plain `Reporter()` (no `log_dir`)
   — same stderr-only/no-logs/no-buffer behaviour as the old "no invocation active" `None` check,
   now expressed as an object.
5. **The nested-invocation splice is deleted.** `hook.py` no longer opens two nested
   `error_reporter.invocation()` scopes; it owns one `Reporter`, mutates `.log_dir` in place once
   `env_config` resolves (`reporter.log_dir = resolve_log_dir(None, env_config)`, imported
   directly from `log_writer` — `error_reporter.py` no longer imports `log_writer` at all, only
   `error_log`), and there is exactly one buffer, so no splice-on-exit logic is needed.

### Behavioural nuance flagged explicitly (not hidden)

The old two-invocation design meant a crash AFTER the inner (env_config-refined) invocation
opened, but caught by the OUTER except handlers, logged through the OUTER invocation's COARSE
log directory (LIFO restore reverted `.log_dir` on the inner scope's exit). The new design mutates
one `Reporter.log_dir` in place and never reverts it, so a crash after refinement now logs to the
REFINED (actually-configured, more accurate) directory instead. I judge this an accidental
consequence of the old stack-based restore, not a deliberate feature — no existing assertion
(checked both `TestOuterInvocationCoversGetEnvConfigAndHandlers` and
`TestNestedInvocationFaultSurvivesToTheCrashResponse` in the pre-refactor test file) inspects
which physical directory receives the write; both only assert `additionalContext`/
`permissionDecision` and non-leakage into the real repo's `logs/`. Flagged here per the "existing
tests are the check" instruction, since it is a real (if inconsequential and arguably improved)
behavioural difference outside what any test pins.

### Test changes — every one called out, per "if a test has to change, stop and report"

The task text itself specifies the new public API in exact detail (`error_reporter.active(reporter)`,
`Reporter(log_dir=tmp_path)` directly constructible, item 5's "delete it if so, and say so"), which
I read as sign-off for the resulting test rewrites since `invocation()`/module-level `report_fault`/
`drain_claude_context()`/the splice cannot survive unchanged and simultaneously satisfy items 2 and
5. No assertion was weakened anywhere — every change below is either a mechanical API-surface
rename (setup scaffolding only) or a relocation of coverage onto the new class/mechanism it now
belongs to.

- **`test/unit/test_error_reporter.py`** — fully rewritten (20 tests, same count as before).
  Tests `Reporter` directly (construct + assert, per item 1: `TestDefaultReporterHasNoLogDir`,
  `TestReporterRoutesWarning/Fault/Notice`, `TestLogDirectoryUnresolvable`,
  `TestLogWriteFailureDegradesToStderr`, `TestReportersDoNotShareState`,
  `TestFallbackShapeMatchesTheLoggedEcho`, `TestRoutingLooksUpLogFnByName`), plus a new
  `TestActiveRegistersTheAmbientReporter` (6 tests) covering `active()`'s registration/restore/
  nesting/exception-safety and `report_notice`/`report_warning`'s default-fallback behaviour. One
  behavioural difference is deliberately test-visible: `test_fault_still_reaches_claude_with_no_log_dir`
  documents that a `Reporter`'s buffer is now unconditional instance state (present regardless of
  `log_dir`), where the old design gated Claude-reachability on "an invocation is active" — a
  distinction with no production effect since `hook.py` always has exactly one `Reporter` for its
  own fault-reporting, but real and worth a named test.
- **`test/unit/test_hook_error_reporter.py`** — rewritten (7 → 6 tests). `TestOrdinaryInvocationStderr`
  and the no-fault/leak-across-invocations tests carry over with the SAME intent and mostly
  unchanged bodies. **`TestNestedInvocationFaultSurvivesToTheCrashResponse` (1 test) is deleted
  outright** — it pinned the splice mechanism itself, which no longer exists. The remaining tests
  that used to trigger a fault via a monkeypatched `error_reporter.report_fault(...)` side effect
  (simulating "some other module reports a fault") were adapted to trigger it via a real raised
  exception instead — `report_fault`/`fault()` now has exactly one production caller
  (`_report_crash_fault`, from `main()`'s own except handlers), so "an arbitrary call site reports
  a fault without crashing" is no longer a representable production scenario, and testing it would
  mean reaching into `error_reporter._active` from outside the module, which I chose not to do.
  Full detail in the task recall note above.
- **`test/unit/test_config_divergence.py`, `test_configuration.py`, `test_env_config.py`,
  `test_auto_migrate.py`** — one line each, purely mechanical:
  `error_reporter.invocation(env_config={"log_dir": log_dir})` →
  `error_reporter.active(error_reporter.Reporter(log_dir=log_dir))`. Test names and docstrings
  touched only where they referenced "invocation" by name. No assertions changed.

### Doc-drift swept

- `.pyscn.toml`'s observability-layer comment said `error_reporter imports error_log and
  log_writer, both same-layer` — no longer true (`log_writer` import moved to `hook.py`); corrected.
- `log_writer.py`'s `resolve_log_dir` and `_log_dir_from_environment` docstrings referenced "the
  outer reporter invocation" / ":mod:`toolguard.error_reporter` reuses this" — updated to describe
  `hook.py::main`'s `Reporter` resolution instead.
- Grepped the whole repo (`toolguard/`, `test/`, `docs/`, `*.md`) for `error_reporter.invocation`,
  `error_reporter_invocation`, `drain_claude_context()`, `report_fault(` outside the reporter's own
  class — no remaining stale references.

### Verification

- `uv run python -m unittest discover -s test -t .` — 2685 passed (baseline was 2686; the delta is
  exactly the one deleted splice test, reconciled and confirmed via test-count arithmetic before
  accepting the result).
- `uv run python tools/architecture_fitness.py --layers` — clean (completeness + direction).
- `uv run ruff format .` / `uv run ruff check .` — clean.
- Closed-pipe probe (`.../scratchpad/probe_emit_flush.py`) — exit code 2 confirmed (fallback still
  fires correctly; unaffected by this refactor, re-run as requested).

### Files touched this pass

- `toolguard/error_reporter.py` — `Reporter` class + `active()` registry (rewritten).
- `toolguard/hook.py` — `main()` constructs and threads one `Reporter`; `_print_not_a_standalone_command_message`,
  `_warn_if_settings_path_override`, `_report_crash_fault`, `_finalize_output` take `reporter` as a
  parameter; new `_resolve_reporter_log_dir` helper; import order fixed.
- `toolguard/log_writer.py` — two docstring updates (doc-drift only, no logic change).
- `.pyscn.toml` — one comment correction (doc-drift only).
- `test/unit/test_error_reporter.py`, `test/unit/test_hook_error_reporter.py` — rewritten as above.
- `test/unit/test_config_divergence.py`, `test_configuration.py`, `test_env_config.py`,
  `test_auto_migrate.py` — one mechanical line each.

### Self-review

- Anti-pattern scan: no async/await, no threading, no function-local imports introduced (`from
  pathlib import Path` added at module level in `hook.py`); ruff's `PLC0415` confirms.
- No new runtime dependency; `Reporter` and `active()` are stdlib-only (`dataclasses`, `contextlib`).
- Re-read the task recall note before reporting; every numbered item (1–5) in Arnon's spec is
  addressed and cross-referenced above.
- No existing test's *assertion* was weakened — every test-file change is either a class-relocation
  (unit tests of the retired module-level API become unit tests of the class) or a mechanical
  rename of setup scaffolding. The one deleted test class is called out by name, with the mechanism
  it pinned identified as deleted-by-design.

### Time / cost estimate

- Phase 1 (requirements capture, reading prior memory + code): ~12 min.
- Phase 2 (implementation — error_reporter.py, hook.py, 6 test files, doc-drift sweep): ~20 min.
- Phase 3 (verification — full suite x4, architecture fitness, ruff, closed-pipe probe): ~5 min.
- Phase 4 (this report): ~4 min.
- Total: ~41 min elapsed. Estimated cost (Sonnet 5, this session's token volume — several full-file
  reads of `hook.py`/test files plus rewrites): roughly $2–3.
