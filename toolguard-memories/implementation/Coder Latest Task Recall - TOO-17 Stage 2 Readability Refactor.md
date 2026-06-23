---
title: Coder Latest Task Recall - TOO-17 Stage 2 Readability Refactor
type: note
permalink: toolguard/implementation/coder-latest-task-recall-too-17-stage-2-readability-refactor
tags:
- TOO-17
- task-memory
- readability-refactor
- stage-2
---

# TOO-17 Stage 2 Readability Refactor

## Task
Behavior-preserving readability refactor of toolguard. TDD refactor step.
No test changes allowed. Keep suite GREEN (724 tests).

## Task A: Collapse triplicated strictest-wins logic in compound.py

### What to do
Extract ONE strictest-wins combinator. Currently duplicated in:
- `_resolve_leaf` inner loop (lines 82-115): combines sub-commands within a leaf
- `_combine_strictest` (lines 168-207): combines leaves from resolve_compound_permission

### Strategy
Route `_resolve_leaf`'s inner combination through `_combine_strictest`:
1. For each sub-cmd, build (decision, formatted_reason, cmd) triple:
   - deny: reason = "Compound command contains denied sub-command: {cmd} ({original_reason})"
   - ask: reason = "Compound command contains sub-command requiring approval: {cmd} ({original_reason})"
   - allow: reason = original reason from resolve_one (pass-through)
2. Call `_combine_strictest(triples)` and return its result

### Reason string constraints (from tests in test_hook.py)
- `"All N sub-commands allowed: [cmd -> pattern, ...]"` IS tested (lines 1202, 1212, 1264, 1281)
- `"Compound command contains denied sub-command: ..."` NOT directly tested
- `_COMPOUND_MATCH_PATTERN` in hook.py = `r"All \d+ sub-commands allowed: \[(.+)\]"` must match

### After refactor
- `_resolve_leaf` becomes thin: build sub-cmd triples, call `_combine_strictest`
- `_combine_strictest` becomes the ONE combinator (unchanged or minimally changed)
- `check_compound_permission` already thin (just delegates)
- `resolve_compound_permission` also thin (unchanged)

## Task B: Finish IR isolation in command_extractor.py

### What to do
`_extract_from_ctrl_body` still touches raw Canopy nodes:
- `hasattr(body_node, "elements")` (line 399)
- `body_node.elements` (line 403)
- `hasattr(rest_list, "elements")` (line 406)
- `rest_list.elements` (line 406)

`_extract_from_ctrl_stmt` also touches:
- `hasattr(stmt_node, "text")` (line 441) in CASE_STMT branch

Also `_extract_from_if_stmt_ir` touches:
- `cond.text.strip() if hasattr(cond, "text") else ""` (line 550)

### Strategy
Extend `IRControlStructure` in command_model.py to carry pre-built body statement IR nodes.
Add a new field to `IRControlStructure`:
- `body_ir_stmts: List` = pre-built list of IR nodes for body statements

Move the ctrl_body walking logic into `_build_control_structure` in command_model.py.
Then `_extract_from_ctrl_body` in command_extractor.py just iterates over `ctrl.body_ir_stmts`.

For the CASE_STMT text: use `ctrl.node_text` from IRControlStructure (already computed).
For the ctrl_condition text: add `ctrl_condition_text: str` field to IRControlStructure.

### Goal: ZERO raw-Canopy access outside command_model.py
Verify with grep after implementation.

## Hard Constraints
- NO behavior change
- Suite: 724 tests green WITH and WITHOUT CLAUDE_SETTINGS_PATH
- NO test file changes
- Format only changed files
- Preserve public contracts

## Files to Modify
- `toolguard/compound.py` (Task A)
- `toolguard/parser/command_model.py` (Task B - add IR body stmt fields)
- `toolguard/parser/command_extractor.py` (Task B - remove raw Canopy access)
