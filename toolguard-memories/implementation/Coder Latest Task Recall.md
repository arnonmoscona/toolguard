---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- TOO-17
- task-memory
- refactor
---

# Coder Latest Task Recall

## Task
TOO-17 Stage 1: Readability Refactor of `command_extractor.py`

## Context
The file `toolguard/parser/command_extractor.py` became hard to reason about after 
TOO-17 added multi-line Bash handling. This is a TDD refactor step - behavior must
be perfectly preserved.

## Root Problems Being Fixed
1. TWO parallel raw-canopy-tree walkers:
   - `_extract_compound_into` (~158 lines)
   - `_extract_from_tree` (~140 lines, nested closures)
   Both duplicate TreeNodeN/`hasattr` navigation.

2. `_extract_compound_into` is a god-function mixing:
   - raw-tree navigation
   - node-kind classification
   - business policy (control-structure decompose, proc-subst->undecidable, bash-`-c` recursion, foreign-inline ask_floor, heredoc-sentinel ask_floor)
   - dedup

## Scope
ONLY `command_extractor.py` (+ a new `command_model.py`). 
Do NOT touch: `compound.py`, grammar `.peg`, `bash_parser.py`, `multiline.py`.

## What To Do
1. New `toolguard/parser/command_model.py`: small dataclasses for Abstract Command Model:
   - `Sequence`, `Pipeline`, `SimpleCommand(text, substitutions)`, 
   - `ControlStructure(kind, is_complex, condition, body)`, `ProcSubst`/`Undecidable`
   - SINGLE builder that walks the canopy parse tree ONCE into the IR
   - This builder is the ONLY code allowed to touch raw canopy nodes (TreeNodeN / `hasattr` / element lists)
   - Dispatch via single `node_kind(node)` classifier that collapses the ~12 `_is_*` predicates

2. In `command_extractor.py`, reimplement structured extraction + classification as 
   SIMPLE RECURSION over IR - NOT the raw tree. Centralize dedup in one place.

3. DELETE the legacy `_extract_from_tree` walker; make `extract_commands(command_line) -> List[str]`
   a trivial projection of the IR (flatten leaves). `parse_command_line` stays thin wrapper.

## Hard Constraints
- NO behavior change. All 724 tests green (both with and without env var)
- Do NOT modify any file under test/
- Preserve all public import paths:
  - `toolguard.parser.multiline.extract_structured`
  - `toolguard.parser.multiline.LeafCommand`
  - `toolguard.parser.multiline.UndecidableSegment`
  - `toolguard.parser.command_extractor.extract_commands`
  - `toolguard.parser.command_extractor.parse_command_line`
- NO hand-rolled / regex structural bash parsing
- Runtime stdlib-only
- `ruff format . && ruff check .` clean

## Report Back
- IR module + types introduced
- Confirm ALL raw-canopy-tree access is in single builder
- Legacy `_extract_from_tree` is gone
- `extract_commands` is IR projection
- Both-env test counts (expect 724) + ruff
- ZERO test files changed
- Append "Stage 1 readability refactor" section to `toolguard-memories/implementation/TOO-17 Implementation Report.md`

## Current State
- 724 tests pass before refactoring

## Key Insight About `extract_commands` vs `_extract_from_tree`
The legacy `_extract_from_tree` has DIFFERENT semantics from `_extract_compound_into`:
- It includes subshell/brace group WRAPPER text as well as inner commands
- This means `extract_commands` cannot just call `extract_structured_from_grammar` without
  potentially breaking the tests.
- Need to understand what behavior `extract_commands` produces vs `extract_structured_from_grammar`.
