---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-8
- coder-implementation-report
- hierarchical-config
- phase-5
---

# TOO-8 Phase 5 -- Implementation Report (non-permission config cross-level)

Status: COMPLETE. Suite 682 tests OK WITH and WITHOUT CLAUDE_SETTINGS_PATH. ruff clean.
Files compile. NOTHING committed (Arnon does all git). Permission/hard_deny/log-taxonomy
behavior unchanged.

## What was implemented

### 1. Scalars -> more-specific-wins (flipped from Phase-1 user-wins)
- `Configuration.scalar(name, default)` now returns the value from the MOST-SPECIFIC level
  that defines it. Layers are most-specific-first, so it returns on the FIRST defining
  toolguard_hook layer (project beats ancestor beats user). Native layers ignored.
- `config_sync_settings()` (auto_migrate/backup_dir/auto_sort_on_migrate) follows as a
  consequence (uses scalar()).
- Pin test renamed `test_config_sync_conflict_is_user_wins_phase1` ->
  `test_config_sync_conflict_is_project_wins`; expectations flipped to project-wins; G/W/T
  updated. `test_scalar_dotted_last_wins` -> `test_scalar_dotted_more_specific_wins` (flipped).
- Removed the `# FIXME(TOO-8 Phase 2 ... decision #4)` markers in config.py::scalar and the
  test. (The legacy `config_sync_settings_from_sources` helper used ONLY by
  auto_migrate.load_config_sync_settings still uses last-occurrence-wins -- out of Phase 5
  scope; its 8 committed tests pass arbitrary config_files lists and changing it would alter
  test intent. The runtime hook path uses config_sync_settings() which IS more-specific-wins.)

### 2. no_match_fallback -> more-specific-wins
- Resolved inside the rewritten takeover_mode() (first level that sets it wins; default 'deny').

### 3. governed_tools + takeover pattern lists -> UNION across N levels
- `governed_tools()` reimplemented to UNION over self.layers (hierarchical, N-level),
  de-dup most-specific-first, default ('Bash',). Replaces delegation to the legacy 2-level
  `_load_governed_tools` (kept for its own direct tests + no other prod caller). Now also
  consistent under CLAUDE_SETTINGS_PATH mode.
- takeover ignored_allow_patterns / additional_ignored_patterns remain UNION across all
  levels; ignored_allow_patterns seeded with blanket defaults (new module constants
  `_DEFAULT_IGNORED_ALLOW_PATTERNS`, `_DEFAULT_NO_MATCH_FALLBACK`).

### 4. takeover_mode.enabled -> single-owner with fail-safe-on-conflict
- `Configuration.takeover_mode()` REWRITTEN to resolve over self.layers (was delegating to
  legacy 2-level load_takeover_mode_config). Detects levels that EXPLICITLY set
  `takeover_mode.enabled` (key present in parsed content) with value+provenance.
  - 0 set => OFF; >=1 all same => that value; differ => CONFLICT: enabled forced False
    (fail-safe OFF) + attach `TakeoverEnabledConflict`.
- New `TakeoverEnabledConflict` frozen dataclass (sources: tuple of (bool, Provenance),
  most-specific first; .describe()). `TakeoverConfig` gained `conflict: Optional[...] = None`.
- `_resolve_takeover_enabled` static helper encapsulates the policy.
- Replaced the OR-based enabled merge. Legacy `load_takeover_mode_config` UNCHANGED (still
  used by _load_permissions, migrate_permissions, log_writer, and its direct tests).

### 5. Hook wiring (hook.py main)
- New module flag `_takeover_conflict_logged` (once-per-session).
- New helper `_log_takeover_enabled_conflict(conflict, log_dir)` writes an error_log.log_conflict
  entry citing the disagreeing levels' values+provenance and that fail-safe OFF was applied.
- main(): added `elif takeover.conflict is not None:` branch -> once-per-session
  log_conflict + issue_takeover_warning (reuses session-marker mechanism). enabled already
  OFF so downstream is the safe path.

## Files changed (production)
- toolguard/config.py: scalar more-specific-wins; config_sync_settings docstring; governed_tools
  union-over-layers; TakeoverEnabledConflict (new); TakeoverConfig.conflict field; takeover_mode
  rewritten over layers; _resolve_takeover_enabled (new); default-patterns constants.
- toolguard/hook.py: _takeover_conflict_logged flag; _log_takeover_enabled_conflict (new);
  takeover enabled-conflict branch in main.
- technical-notes.md: new "Non-permission cross-level resolution (TOO-8 Phase 5)" section.

## Files changed (tests, all G/W/T docstrings)
- test/unit/test_configuration.py: flipped+renamed 2 scalar pin tests; rewrote
  test_takeover_mode_shape to build from layers; new TestTakeoverEnabledResolution class
  (none-set=OFF, one=ON, agreement=no-conflict, disagree=fail-safe-OFF+conflict, 3-level
  pattern-list union, no_match_fallback more-specific-wins); governed_tools tests
  (default, 3-level union, non-list tolerated, ignores-native).
- test/unit/test_hook.py: import TakeoverEnabledConflict; new TestTakeoverEnabledConflictWiring
  (end-to-end: conflict logs+warns+fail-safe allow on safe path; once-per-session no re-log;
  helper no-op guards).

## Coverage (stdlib trace via tools/coverage_stdlib.py)
All changed executable lines covered. Verified per-line hit counts:
- config.py scalar (all branches incl bare-key + default), takeover_mode body (52 hits),
  _resolve_takeover_enabled (all 3 branches: no-explicit/agreement/conflict), governed_tools
  (incl non-list guard), TakeoverEnabledConflict.describe.
- hook.py elif-conflict branch, once-per-session gate, _log_takeover_enabled_conflict body
  + both no-op guards.
Remaining `>>>>>>` lines in changed files are non-executable signature continuations or
pre-existing unrelated branches (takeover.enabled notice, fail-closed, exception handlers).
Effectively >90% on changed code (changed lines fully exercised).

## Self-review
- No async/threading/local-imports in production files. Doc comments on all new
  functions/classes. Single resolution path (takeover_mode + governed_tools now both go
  through self.layers). Immutable surface preserved (frozen dataclasses, tuples).
- Out-of-scope respected: no permission/hard_deny/log-stream changes; Phase-6
  session-START prior-conflict alert NOT implemented (conflict is only WRITTEN now).
- Scope: 2 production files, 1 docs, 2 test files modified. Well within limits.

## Follow-ups / notes for Arnon
- `config_sync_settings_from_sources` (legacy, auto_migrate path) still last-occurrence-wins;
  intentionally left (out of Phase 5 scope, would change committed migration-test intent).
  Consider aligning when migrate_permissions migrates onto the Configuration API (existing
  Phase 2 follow-up).
- `_load_governed_tools` now has no production caller (only its own direct tests). Candidate
  for privatisation/removal in a later cleanup, same as other transitional loaders.
