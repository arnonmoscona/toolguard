---
title: TOO-15 P0 Keystone Implementation Report
type: note
permalink: toolguard/implementation/too-15-p0-keystone-implementation-report
tags:
- TOO-15
- TOO-11
- implementation
---

# TOO-15 P0 Keystone Implementation Report

**Date:** 2026-06-25
**Duration:** ~30 minutes (13:06 - 13:40 EDT)
**Status:** COMPLETE - all tests pass

## Summary

Built the `toolguard/tools/` sub-package (4 modules + `__init__.py`) implementing
the P0 keystone slice for TOO-15 skills and config tooling. All modules are
side-effect-free for evaluation purposes and reuse existing core APIs faithfully.

## Files Created

### New package files
- `toolguard/tools/__init__.py` - Package docstring and module inventory
- `toolguard/tools/config_access.py` - Thin facade over Configuration
- `toolguard/tools/decision.py` - Side-effect-free evaluation primitive
- `toolguard/tools/log_harvest.py` - Daily log file parser
- `toolguard/tools/replay.py` - THE KEYSTONE: decision diff for config changes

### New test files
- `test/unit/test_tools_config_access.py` - 11 tests
- `test/unit/test_tools_decision.py` - 14 tests
- `test/unit/test_tools_log_harvest.py` - 17 tests
- `test/unit/test_tools_replay.py` - 17 tests
- Total: 59 new tests, all pass

## Test Results
- Pre-implementation: 774 tests, OK
- Post-implementation: 833 tests, OK (774 + 59 new)
- ruff check: all clean
- py_compile: all clean

## Key Design Decisions

### 1. Side-effect isolation in `decision.py`

The hook's top-level functions (`resolve_bash_permission_detailed`,
`resolve_file_path_permission_detailed`) write logs and have side effects.
**Solution:** Replicate their logic using the same PURE building blocks:
- `permissions.decide_command_at_level_detailed` (pure per-level decider)
- `permissions.check_hard_deny` (pure hard-deny evaluator)
- `config.Configuration.resolve_permission_detailed` (pure more-specific-wins cascade)
- `compound.resolve_compound_permission` (pure compound splitter)
- `hook._check_file_path_hard_deny` (pure file hard-deny, imported from hook)
- `hook._decide_file_path_at_level_detailed` (pure file level decider, imported from hook)

The `_` prefix hook helpers are imported from `toolguard.hook` within the same
package. This is intentional product code, not test code.

### 2. config_access.load_config uses `ignore_env_override=True`
Skills/tooling always want the project-rooted hierarchy, not a stale
`CLAUDE_SETTINGS_PATH`. This matches what `auto_migrate` does.

### 3. replay.classify_change uses strictness ordering
`allow=0, ask=1, deny=2`. Higher = stricter. B stricter than A = tightened.
B looser than A = broadened. Simple, correct, well-tested.

### 4. log_harvest robustness
Malformed sections (no Status, no Command, bad date headers, Discovery entries)
are silently skipped. Unknown status values pass through as-is. Time window
filtering works at both file-level (date in filename) and entry-level (timestamp).

### 5. pyproject.toml unchanged
`packages = ["toolguard"]` automatically picks up `toolguard/tools/` as a
sub-package. Verified by import test.

## Reuse Points (exact functions)

For `decision.decide`:
- Bash path: `compound.resolve_compound_permission` -> (per sub-command)
  `permissions.check_hard_deny` + `config.resolve_permission_detailed` with
  `permissions.decide_command_at_level_detailed` as the level decider
- File path: `hook._check_file_path_hard_deny` + `config.resolve_permission_detailed`
  with `hook._decide_file_path_at_level_detailed` as the level decider

These are exactly the functions the hook uses, just without the surrounding
logging/exit scaffolding.

## Recommended Core Refactors (for later)

1. **Move file-path helper functions from hook.py to a pure module**
   (`_anchor_file_pattern`, `_check_file_path_hard_deny`,
   `_decide_file_path_at_level_detailed`). Currently they live in `hook.py` which
   is designed to have side effects. They are pure functions and would be better
   in `permissions.py` or a new `file_permissions.py`. This would make the
   boundary cleaner.

2. **add `ask` patterns to `config.permission_layers`**
   Currently `permission_layers` only returns allow/deny. The `ask` patterns
   require reading raw layer content directly. A proper extension of
   `ToolPatternLayer` to include `ask` would simplify `config_access.per_layer_rules`.

## Known Limitations

- `decision.decide` for Bash does not return per-sub-command provenance (compound
  commands may match from multiple rules). The `provenance` field is `None` for
  Bash decisions. For file-path tools, provenance IS returned when available.
- `log_harvest` only parses daily logs, not transcripts (deferred to later as
  specified in scope).
- `replay_single.matches_observed` treats `ask` same as `deny` for REFUSED entries,
  which is slightly imprecise but correct for practical purposes (both mean "not
  executed without user intervention").

## Phase Timing (approximate)
- Phase 1 (Planning + reading context): ~8 minutes
- Phase 2 (Implementation): ~18 minutes
- Phase 3 (Self-review + test fixes): ~4 minutes
- Phase 4 (Report): ~2 minutes
- Total: ~32 minutes

## Estimated Cost
Using claude-sonnet-4-6, approximately:
- Input tokens: ~80K (large due to reading config.py, hook.py, permissions.py, etc.)
- Output tokens: ~15K (implementation code + tests)
- Estimated cost: ~$0.50-0.75 USD
