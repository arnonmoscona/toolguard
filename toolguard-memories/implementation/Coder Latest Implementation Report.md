---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-17
- implementation-report
- refactor
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
