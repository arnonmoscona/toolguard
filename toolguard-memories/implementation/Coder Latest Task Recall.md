---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- TOO-8
- task-memory
- coder-task
---

# TOO-8 Follow-up: Loader Deletion and Takeover Coverage

## Task Summary
Two code follow-ups to finish TOO-8 (hierarchical config) in toolguard.

## Task 1: Migrate migrate_permissions.py off legacy loader, then delete it

### Current state
- `toolguard/scripts/migrate_permissions.py` line 906 calls `load_takeover_mode_config(project_root)`
- This is the ONLY production caller of the legacy loader
- The script already builds a `Configuration` two lines above (lines 897-899)
- `load_configuration(project_root, ignore_env_override=True)` is already called

### What to do
1. Rework migrate_permissions.py to reuse a SINGLE Configuration object
2. Read takeover via `.takeover_mode()` on the existing config object
3. `ignored_patterns` = union of `ignored_allow_patterns + additional_ignored_patterns` when enabled
4. Remove `load_takeover_mode_config` import from migrate_permissions.py line 22ish
5. Keep `discover_config_files` import (still needed for write-target selection at line 903)
6. DELETE `load_takeover_mode_config` from `toolguard/config.py` entirely
7. Clean up stale comment in config.py docstring (line ~20) referencing it
8. Reword comment at line ~48 ("Shared between the legacy load_takeover_mode_config...") 
9. Keep `_DEFAULT_IGNORED_ALLOW_PATTERNS` constant (still used by hierarchical resolver)
10. Verify with `grep -rn load_takeover_mode_config` that no references remain

### Key insight on ignored_patterns behavior
- Old code: `ignored_patterns = ignored_allow_patterns + additional_ignored_patterns` when enabled
- New `TakeoverConfig`: has `.ignored_allow_patterns` and `.additional_ignored_patterns` as tuples
- Preserved behavior: only populated when takeover enabled

## Task 2: Rework test/unit/test_takeover_mode.py

### Tests currently in test_takeover_mode.py (16 references to load_takeover_mode_config):
- `TestTakeoverModeConfig`:
  - `test_default_config_when_no_files` - defaults when no files
  - `test_load_takeover_mode_from_toml` - reads TOML
  - `test_load_takeover_mode_from_json` - reads JSON
  - `test_merge_takeover_mode_from_multiple_files` - merges from project + user level
  - `test_takeover_mode_not_loaded_from_claude_settings` - ignores settings.json
- `TestNoMatchFallback`:
  - `test_deny_fallback_silent` - deny fallback
  - `test_warn_deny_fallback` - warn_deny fallback
- `TestBackwardCompatibility`:
  - `test_no_takeover_mode_section_uses_defaults` - no section uses defaults
- `TestFilePathToolTakeoverFiltering`: (uses `load_file_path_patterns` from hook - KEEP these)
  - `test_filters_blanket_read_pattern`
  - `test_filters_blanket_write_pattern`
  - `test_does_not_filter_file_patterns_when_disabled`
  - `test_never_filters_toolguard_hook_file_patterns`
  - `test_file_deny_patterns_not_filtered`

### Strategy for porting:
- Re-point tests at `load_configuration(project_dir, ignore_env_override=True).takeover_mode()`
- Where a scenario is ALREADY covered equivalently by test_hierarchical.py or test_configuration.py, DROP it
- Do not weaken any assertion
- Keep `TestFilePathToolTakeoverFiltering` tests as-is (use hook, not legacy loader)

### What's covered in other test files:
- test_configuration.py:783 covers `takeover_mode_shape` (TakeoverConfig fields)
- test_configuration.py:233 covers takeover filtering native layer (Read)
- Various tests in test_configuration.py cover enabled/conflict/default resolution

## Task 3: Confirm live Bash takeover filtering coverage

### Key question
With takeover enabled and a NATIVE settings allow of Bash(*), does a test prove that:
1. The native blanket allow is suppressed at the live resolve path
2. A toolguard deny still fires
3. toolguard_hook allow entries are NOT filtered

### Live path
config.py:1131: `if takeover.enabled and layer.is_native and pattern in ignored:`

## Success criteria
1. `uv run python -m unittest discover -s test -t .` fully green
2. `uv run ruff check .` clean
3. `grep -rn load_takeover_mode_config .` shows zero references in code/comments/tests
4. No git operations
