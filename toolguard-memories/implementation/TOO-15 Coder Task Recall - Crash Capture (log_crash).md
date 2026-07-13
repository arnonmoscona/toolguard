---
title: TOO-15 Coder Task Recall - Crash Capture (log_crash)
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-crash-capture-log-crash
tags:
- task-memory
- TOO-15
- coder-task-recall
---

## Ticket
TOO-15, toolguard project. Follow RED-then-checkpoint workflow: write tests FIRST, confirm
ONLY new tests fail, STOP, report red state, wait for approval before production code.

## Task: capture full crash detail to ~/.toolguard/errors/

Problem: toolguard/hook.py `main()` has three except clauses (json.JSONDecodeError,
ValueError, generic Exception) around lines 787-807 that swallow ALL detail down to a
one-line stderr message. No traceback, no durable record.

### Required production code (NOT yet written -- RED phase only for now)

1. **New function `toolguard/error_log.py::log_crash(exc: BaseException, context: Dict[str,
   Any], caught_as: str) -> Optional[Path]`**
   - Writes ONE markdown file per crash to `~/.toolguard/errors/toolguard-error-<timestamp>.md`,
     timestamp format `%Y-%m-%d-%H%M%S` (matches `create_backup` in
     toolguard/scripts/migrate_permissions.py).
   - Collision-safe: same `-2`, `-3`... suffix scheme as `create_backup`, implemented locally
     (no cross-module dependency on migrate_permissions.py).
   - Creates `~/.toolguard/errors/` on demand (`mkdir(parents=True, exist_ok=True)`). Must NOT
     require `init-state` to have run first.
   - Content: timestamp, `caught_as`, `type(exc).__name__`, `str(exc)`, full
     `traceback.format_exc()`, and `context` dict rendered readably.
   - Never raises -- catches write failures, warns to stderr (mirrors `_log_entry`'s existing
     pattern), returns `None`.
   - Full docstring.
   - Design decision (mine, for testability): compute `Path.home() / ".toolguard" / "errors"`
     INSIDE the function at call time (not a module-level constant computed at import), so tests
     can patch `pathlib.Path.home` per-call (matches the established pattern already used in
     test/unit/test_env_config.py's `test_stops_at_home_directory`). Internally use
     `crash_file.write_text(content, encoding="utf-8")` (assumed for the write-failure test that
     patches `pathlib.Path.write_text`).
   - Do NOT import from `toolguard.tools.installer` -- hook.py must stay segregated from
     `toolguard.tools.*` (project architectural constraint, confirmed: hook.py currently imports
     nothing from toolguard.tools).

2. **Wire into hook.py's three except clauses in `main()`** (NOT the separate `_run_eval_mode()`
   except clauses around line 448-473 -- ticket only targets `main()`'s at ~787-807). Call
   `log_crash` before `sys.exit(0)` in each. Context dict built from whatever is in scope at
   that point (early failures won't have `tool_name`/`tool_input` yet -- `hook_data` is assigned
   at line 535, inside the try, AFTER `env_config = get_env_config()` at line 532 and BEFORE
   `parse_hook_input()` fully returns). `caught_as` values: `"json.JSONDecodeError"`,
   `"ValueError"`, `"unexpected Exception"`. Import `log_crash` into hook.py's existing
   `from toolguard.error_log import log_conflict, log_error, log_warning` line.

3. **installer.py `_README_TEMPLATE`** (lines 78-96 currently): add one line describing
   `errors/` alongside existing `backups/`/`stage/` bullets, matching existing tone. Do NOT
   make `init-state` create it (lazy creation only).

## RED-phase test plan (this session's actual deliverable)

### test/unit/test_error_log.py (NEW FILE -- none existed before)
Class `TestLogCrash`, 5 tests, using `patch("pathlib.Path.home", return_value=<tmpdir Path>)`
(same pattern as test_env_config.py's `test_stops_at_home_directory`) and
`patch("toolguard.error_log.datetime")` for collision test (same pattern as
test_migration.py's `TestBackupCreation` collision tests):
1. `test_log_crash_writes_file_with_full_detail` -- file written, contains exception type,
   message, caught_as, "Traceback", and context dict values.
2. `test_log_crash_creates_errors_dir_when_toolguard_absent` -- `~/.toolguard` doesn't exist
   at all beforehand; still works.
3. `test_log_crash_colliding_timestamp_writes_distinct_files` -- forced identical
   `datetime.now()` twice -> two distinct files, first's content untouched by second.
4. `test_log_crash_write_failure_returns_none_without_raising` -- patch
   `pathlib.Path.write_text` to raise OSError -> returns `None`, does not raise.
(Only 4 -- decided NOT to add the "no collision keeps plain filename shape" 5th test from
migrate_permissions parity, to stay tight to the ticket's explicit ask. Revisit if reviewer
wants it.)

### test/unit/test_hook.py (existing file, adding new class at end)
Class `TestHookCrashCapture`, 3 tests, added `from tempfile import TemporaryDirectory` to
imports. Reuses existing `_fake_config` helper and `patch("pathlib.Path.home", ...)`:
1. `test_unexpected_exception_writes_crash_report` -- patches
   `toolguard.hook.resolve_bash_permission_detailed` to raise RuntimeError; proves the
   generic `except Exception` path.
2. `test_json_decode_error_writes_crash_report` -- stdin is non-JSON text; proves the
   `except json.JSONDecodeError` path.
3. `test_value_error_missing_field_writes_crash_report` -- valid JSON missing
   `hook_event_name`; proves the `except ValueError` path (raised inside
   `parse_hook_input`).

All assert: `main()` still exits 0 (unchanged existing behavior) AND exactly one
`toolguard-error-*.md` file appears under `<mocked home>/.toolguard/errors/` with the
expected exception type/message/traceback substrings.

## Success criteria
- New tests fail cleanly (ImportError for `log_crash` not existing, or NameError for
  `patch("toolguard.hook.resolve_bash_permission_detailed", ...)` still resolving fine since
  that symbol DOES exist today -- only the crash-file assertions should fail).
- Full suite count unchanged for all previously-passing tests; only new tests are red.
- STOP after reporting red state -- wait for explicit approval before writing log_crash,
  wiring hook.py, or touching installer.py.

## Clarifications from discussion
(none needed -- ticket description was fully self-contained; all file-layout questions
answered by grep/read before writing tests, per the ticket's own "search first" instruction)
