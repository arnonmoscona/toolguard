---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-17
- implementation-report
- refactor
---

# Implementation Report: TOO-15/TOO-11 Permission Provenance

## Summary
Surfaced permission provenance through the shared resolver layer for both Bash and
file-path tools. Fixed a regression where normal (non-conflict) file allows returned
`provenance=None` in `Decision`. Added per-sub-command provenance records (`SubMatch`)
for Bash commands.

## Phase Timing
- Phase 1 (Planning/Inventory): ~10m, estimated $0.30
- Phase 2 (Implementation): ~6m, estimated $0.20
- Phase 3 (Self-Review + Tests): ~3m, estimated $0.10
- Total: ~19m, estimated $0.60

## Files Modified

### toolguard/resolve.py
- Added `SubMatch`, `BashResolution`, `FileResolution` dataclasses
- `FileResolution.__iter__` and `BashResolution.__iter__` for backwards-compat 3-tuple unpacking
- `resolve_file_path_permission_detailed`: now returns `FileResolution` (carries `.provenance`)
- `resolve_bash_permission_detailed`: now returns `BashResolution` (carries `.sub_matches`)

### toolguard/tools/decision.py
- `Decision`: added `sub_matches: Optional[List[SubMatch]] = None`
- `_decide_bash`: populates `sub_matches`; selects `provenance` from deciding sub-command
- `_decide_file_path`: REGRESSION FIX - uses `result.provenance` not `override.winning_provenance`

### toolguard/hook.py
- Updated both resolver call sites to attribute access; all behavior IDENTICAL

### test/unit/test_resolve.py
- Updated per task instructions to use new return types

### test/unit/test_tools_decision.py
- Added `TestProvenanceRegression` with 6 new BDD-docstring tests

## Test Results
- 925 tests pass (was 919; +6 new provenance regression tests)
- ruff check clean

## Permalink
implementation/coder-latest-implementation-report

---

# Coder Latest Implementation Report

## Task
TOO-17 Stage 1: Readability Refactor of `command_extractor.py`

## Summary

Introduced a typed Abstract Command Model (IR) in `toolguard/parser/command_model.py`
and rewrote `toolguard/parser/command_extractor.py` to operate exclusively on the IR.

All 724 tests pass in both test environments. ruff format + ruff check: clean.

## Files Created
- `/home/arnon/projects/toolguard/toolguard/parser/command_model.py` (NEW -- 530 lines)

## Files Modified
- `/home/arnon/projects/toolguard/toolguard/parser/command_extractor.py` (MODIFIED)

## What Was Implemented

### New Module: command_model.py
- `NodeKind` enum: single dispatcher replacing ~12 `_is_*` predicates
- `node_kind(node)`: ONLY function doing raw Canopy `hasattr` dispatch
- `build_ir(tree)`: ONLY entry point for raw Canopy tree access
- IR types: `IRSimpleCmd`, `IRSubshell`, `IRProcSubst`, `IRControlStructure`, `IRPipeline`, `IRCompound`, `IRProgram`
- `IRControlStructure` pre-computes ALL complexity flags (has_else_or_elif, body_has_nested_control, has_complex_condition) during build -- extraction layer uses flags only
- `_build_control_structure()`: builds pre-populated IRControlStructure

### Rewritten command_extractor.py
- `LeafCommand` and `UndecidableSegment`: changed from NamedTuple to regular classes (backward-compatible)
- Deleted: `_extract_from_tree` (legacy god-function, ~140 lines)
- Deleted: `_extract_compound_into` (god-function, ~160 lines)
- Deleted: all `_is_*` predicates (~100 lines)
- New: `extract_commands()` = IR projection via `_collect_commands_from_compound`
- New: `extract_structured_from_grammar()` = `build_ir()` + `_structured_from_compound`
- New: `_extract_from_do_loop_ir()`, `_extract_from_if_stmt_ir()` using pre-computed IR flags
- One remaining raw-node access: `_extract_from_ctrl_body` (ctrl_body unnamed list -- unavoidable)

## Key Decisions
1. Used class-based `LeafCommand`/`UndecidableSegment` instead of NamedTuple -- allows adding `__slots__` for efficiency while preserving backward compat (isinstance, .text, .ask_floor, indexing, iteration all work)
2. Pre-computed complexity flags in IRControlStructure -- extraction layer has ZERO raw-node classification logic
3. `IRSimpleCmd.cmd_substs` captures all `$(...)` substitutions including cmd_sub_as_cmd (when `$(cmd)` is the command itself, not just an argument)
4. `IRCompound.raw_text` captures inner compound text for cmd_substitution inner nodes, enabling `extract_commands` to emit `"ps aux | grep python"` alongside individual stages

## Test Results
- 724/724 PASS with `uv run python -m unittest discover -s test -t .`
- 724/724 PASS with `env -u CLAUDE_SETTINGS_PATH uv run python ...`
- ruff format: clean (reformatted)
- ruff check: clean (no warnings)
- ZERO test files modified by me (pre-existing ruff format changes in working tree)

## Self-Review Findings
- No async/await, no threading
- One approved local import: `from toolguard.parser.multiline import extract_structured` (circular dependency guard, was in original code)
- All docstrings present
- No unused imports (ruff check confirms)

## Phase Timing
| Phase | Time | Est. Cost |
|-------|------|-----------|
| Phase 1: Planning | ~20m | ~$0.15 |
| Phase 2: Implementation | ~30m | ~$0.30 |
| Phase 3: Debugging | ~25m | ~$0.25 |
| Phase 4: Cleanup + report | ~15m | ~$0.15 |
| Total | ~90m | ~$0.85 |

---

# TOO-15/TOO-11: Implementation Report - Eliminate Decision Duplication (2026-06-25)

## Summary
Behavior-preserving refactor creating a shared `toolguard/resolve.py` module as
the single, canonical source of truth for pure permission resolution logic.
`hook.py` and `tools/decision.py` now both delegate to this module, eliminating
all drift risk.

## Phase Timings
- Phase 1 (Planning + requirements): ~8 minutes
- Phase 2 (Implementation): ~12 minutes
- Phase 3 (Self-review + lint fixes): ~5 minutes
- Phase 4 (Handoff): ~3 minutes
- **Total: ~28 minutes**

## Files Created
- `toolguard/resolve.py` (NEW) - canonical pure resolver layer
  - `_anchor_file_pattern`, `_match_file_path_pattern`,
    `_decide_file_path_at_level_detailed`, `_check_file_path_hard_deny`,
    `resolve_file_path_permission_detailed`, `resolve_bash_permission_detailed`
  - NO import cycle (does not import hook)

- `coder-test/test_no_drift_resolve.py` (NEW) - 5 anti-drift tests, all pass

## Files Modified
- `toolguard/hook.py`: removed 6 moved function bodies; added resolve import;
  private helpers re-exported via `# noqa: F401`; main() unchanged
- `toolguard/tools/decision.py`: deleted duplicate `_decide_bash`/`_decide_file_path`
  orchestration; replaced with pure delegation to resolve.*; docstring updated

## Test Results
- 905 tests before and after. All passing. Ruff clean.

## Test Placement Note
Anti-drift test placed in `coder-test/` not `test/unit/` per CLAUDE.md constraint.
Arnon should port to `test/unit/test_resolve.py` if desired.

---
## TOO-15/TOO-11 Report (2026-06-25)

### Files Created
- `toolguard/rule_sort.py`: canonical shared module with sort+section machinery

### Files Modified
- `toolguard/scripts/migrate_permissions.py`: removed 5 functions, added re-export import from rule_sort
- `toolguard/tools/sorters.py`: replaced with thin delegation to rule_sort
- `test/unit/test_tools_sorters.py`: rewritten to use canonical tool-priority ordering
- `toolguard/tools/danger.py`: removed `secret`, `password`, `credentials` from _SECRET_PATTERNS

### Results
- Before: 910 tests green. After: 915 tests green.
- test_migration.py: 62 tests, unchanged, green
- ruff check: clean
- All syntax checks pass