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
Behavior-preserving refactor: eliminate near-verbatim duplication between `toolguard/tools/decision.py` and `hook.py` resolver functions by creating a shared `toolguard/resolve.py` module.

TICKET: TOO-15/TOO-11 P0 Clean-up
DATE: 2026-06-25

## Files Involved
- `toolguard/hook.py` - source of pure resolver functions to move
- `toolguard/tools/decision.py` - currently duplicates/reimplements logic
- `toolguard/resolve.py` - NEW module to create with moved pure functions

## What to Move from hook.py to resolve.py
Functions to move (pure, no logging/exit):
- `resolve_bash_permission_detailed` (lines 535-589)
- `resolve_file_path_permission_detailed` (lines 417-467)
- `_check_file_path_hard_deny` (lines 368-414)
- `_decide_file_path_at_level_detailed` (lines 251-285)
- `_anchor_file_pattern` (lines 193-225)
- `_match_file_path_pattern` (lines 228-248)

## Do NOT Move
- `load_file_path_patterns` - has optional param loading, keep in hook
- `FILE_PATH_TOOLS` constant - keep in hook, re-export from resolve.py if needed
- `_format_conflict_message` (references override/provenance objects in hook context)
- `_log_conflict_override` (has logging)
- `_log_takeover_enabled_conflict` (has logging)
- `_log_allowed_command` (has logging)
- `_parse_compound_match_details` (utility for logging)
- `main()` and all its supporting infra

## Key Requirements
1. Create `toolguard/resolve.py` with moved pure functions
2. Update `hook.py` to import from `toolguard.resolve` (keep re-exports for backwards compat)
3. Refactor `decision.py` to DELETE duplicated `_decide_bash`/`_decide_file_path` and DELEGATE to `resolve.*` instead
4. No import cycles - resolve.py may import config, permissions, compound, patterns, normalization
5. All 905 tests must still pass
6. Add one anti-drift test in test/unit/test_tools_decision.py or test_resolve.py

## Backwards Compatibility
- Keep moved names importable from `hook` via re-exports
- Check test files for `hook.<name>` references to underscore-prefixed helpers

## Testing
- Run: `uv run python -m unittest discover -s test -t .`
- Must remain at 905 passing
- Add anti-drift test in test/unit/

## Out of Scope
- Do NOT move fail-closed-when-nothing-configured pre-checks from main()
- Do NOT change any decision semantics
- Do NOT run ruff format

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


---
## TOO-15 P0 Analyzers Slice (2026-06-25)

Four new modules: redundancy.py, danger.py, takeover_audit.py, sorters.py
Pre-implementation baseline: 833 tests passing.
Featherhill corpus at /home/arnon/projects/flowers/featherhill/ used for realistic tests.

## TOO-15/TOO-11 Task (2026-06-25)
Two P0-end cleanups in toolguard project.

### PART 1: Unify duplicate sort logic
- Create `toolguard/rule_sort.py` with canonical functions moved from migrate_permissions.py
- Update migrate_permissions.py to import from rule_sort (re-export for backward compat)
- Replace sorters.py to delegate to rule_sort
- Update test_tools_sorters.py to reflect canonical (tool-priority) order

### PART 2: Trim danger.py secrets detector
- Remove `secret`, `password`, `credentials` from `_SECRET_PATTERNS`
- Keep file-indicator patterns only

### Baseline: 910 tests all passing


# Feature Coder Task Recall
# Feature Coder Task Recall - TOO-15/TOO-11 Provenance

## Task
P0-end cleanup: Surface permission PROVENANCE through shared resolver layer for both Bash and file tools.
Baseline: 919 tests, started 14:46.


# Coder Task Recall
# Coder Task Recall - TOO-15 P1 Security Audit Aggregator

## Ticket
TOO-15, Phase P1

## Task Summary
Create a thin deterministic aggregator module `toolguard/tools/security_audit.py` that
combines output from two already-tested modules:
- `toolguard/tools/danger.py`
- `toolguard/tools/takeover_audit.py`

## Critical Anti-Duplication Constraint
MUST NOT reimplement, re-derive, or copy any detection logic.
ONLY calls existing public functions and reshapes their output.

## Deliverables: See implementation plan captured at start of session.

## Start Time
06:46 local time
