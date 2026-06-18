---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- TOO-8
- task-memory
- phase-5-review-fixes
---

# Phase 5 Review Fixes - Task Recall

## Task
Fix pass on three MINOR code-review findings from TOO-8 Phase 5 (hierarchical configuration).
Do NOT expand scope beyond these three items.

## Finding 1: Remove test-only dead code
- `Configuration.bash_permissions()` in `toolguard/config.py` (around line 1594) delegates to legacy 2-level `_load_permissions()`. Runtime Bash path now resolves hierarchically via `resolve_permission_detailed('Bash', ...)` / `allow_deny_for('Bash')`, so `bash_permissions()` has NO production caller (only its own unit test).
- Action: CONFIRM there is no non-test caller, then REMOVE `bash_permissions()` and its unit test.
- Same situation for `_load_governed_tools()` -- CONFIRM, then REMOVE it and its test.
- If `_load_permissions()` becomes unused after these removals, check and REMOVE it too.

## Finding 2: Fail-loud on non-bool `enabled`
- Around `toolguard/config.py:1269`, `takeover_mode.enabled` is parsed via `bool(section['enabled'])`, which silently coerces non-bool (e.g. string "false" becomes True).
- Since `enabled` is a fail-safe SECURITY toggle, non-bool should NOT be coerced.
- Fix: when `enabled` is present but not a real bool, treat that level as NOT explicitly setting enabled (so it does not participate as a True/False vote) AND emit a validation Issue.
- Follow existing validation-Issue pattern in the file.
- Do not change behavior for valid bool values.

## Finding 3: DRY -- centralize config_sync defaults
- `config_sync` default values are duplicated in three places: `config_sync_settings()`, `config_sync_settings_from_sources()`, and a test fake.
- Centralize them into a module-level `_CONFIG_SYNC_DEFAULTS` dict.
- Mirror how `_DEFAULT_IGNORED_ALLOW_PATTERNS` / `_DEFAULT_NO_MATCH_FALLBACK` were centralized.
- All three sites should reference it. Keep resolved values identical to today.

## Constraints
- Tests use stdlib unittest NOT pytest. Run: `uv run python -m unittest discover -s test -t .`
- Suite MUST pass both with env and with `env -u CLAUDE_SETTINGS_PATH uv run python -m unittest discover -s test -t .`
- Every unit test function must carry BDD (Given/When/Then) docstring
- Always run `uv run ruff check .` (must be clean). Do NOT run `ruff format`.
- No git operations.
- Generate doc comments for new/changed functions.
- No async/await, no threading, no imports inside function bodies.

## After Implementing
1. `uv run ruff check .` (clean)
2. Run suite both ways (with env, and without CLAUDE_SETTINGS_PATH). Both must be green.
3. Verify coverage if practical.
4. Write implementation report to basic-memory project='toolguard', under `implementation/` folder, tagged `TOO-8`.

## Files to modify
- `toolguard/config.py` - main changes
- `test/unit/test_configuration.py` - remove unit tests for dead code
