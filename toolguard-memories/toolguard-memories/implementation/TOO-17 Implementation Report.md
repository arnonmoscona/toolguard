---
title: TOO-17 Implementation Report
type: note
permalink: toolguard/toolguard-memories/implementation/too-17-implementation-report
tags:
- TOO-17
- implementation-report
---

# TOO-17 Implementation Report: Grammar-First Multi-Line Bash Parsing

## Summary

Reworked the TOO-17 multi-line Bash bypass fix to be GRAMMAR-FIRST. A previous attempt
was REJECTED because it hand-rolled a ~1,186-line quote-aware/regex parser in
`toolguard/parser/multiline.py` instead of using the PEG grammar.

This implementation satisfies the hard constraint: ALL structural parsing (splitting
statements, pipes, recognizing control structures, quoting) is done by the PEG grammar
(`bash_parser.peg`), regenerated with canopy, consumed by tree-walking in
`command_extractor.py`. `multiline.py` is now a NARROW LEXICAL PRE-PASS only.

## Files Created or Modified

### Modified (major rewrites)
- `toolguard/parser/bash_parser.peg` -- Extended to multi-statement programs and control structures
- `toolguard/parser/bash_parser.py` -- Regenerated with canopy + backward-compat patch
- `toolguard/parser/command_extractor.py` -- Major rewrite: now houses type definitions and all grammar-based tree walking
- `toolguard/parser/multiline.py` -- Complete rewrite: narrow pre-pass only + re-exports from command_extractor
- `toolguard/compound.py` -- Updated `_combine_strictest` to 3-tuple format for "cmd -> pattern" combined reasons

## Grammar Changes (bash_parser.peg)

Top-level changed from `command_line <- spacing compound_command spacing` to:

```peg
program <- spacing statement rest_stmts line_ws
rest_stmts <- (statement_sep statement)*
statement <- compound_command
statement_sep <- (line_ws_char / ";")+
```

New control structures: `for_loop`, `while_loop`, `until_loop`, `if_stmt`, `case_stmt`

Key grammar design decisions:
- `body_end <- (line_ws_char / ";")*` absorbs trailing `;` before done/fi/esac keywords
- `command_name <- cmd_sub_as_cmd / !ctrl_keyword word spacing` -- keywords only blocked in command-name position, NOT argument position
- `command_arg <- word spacing` -- no keyword blocking for arguments; allows `echo done`, `grep for x`, etc.
- `cmd_sub_as_cmd <- cmd_substitution spacing` -- allows `$(which python) --version` to parse
- `proc_subst <- ("<" / ">") "(" spacing compound_command spacing ")" spacing`
- `input_redirect <- "<" !"<" !"(" ...` -- excludes `<(` from being parsed as heredoc
- `spacing <- [ \t]*` -- horizontal-only; newlines are statement separators
- `kw_end <- ![a-zA-Z0-9_]` -- proper identifier boundary that works at EOI

## Required Manual Patch to bash_parser.py

After every canopy regeneration, TreeNode1 must be patched to add backward-compat shim:

```python
class TreeNode1(TreeNode):
    def __init__(self, text, offset, elements):
        super(TreeNode1, self).__init__(text, offset, elements)
        self.line_ws = elements[3]
        self.first_stmt = elements[1]
        self.statement = elements[1]
        self.rest_stmts = elements[2]
        # Backward-compatibility shim: existing code accesses tree.compound_command
        self.compound_command = elements[1]
```

## Architecture: Pre-Pass vs Grammar Boundary

**Pre-pass (multiline.py) handles ONLY:**
- CRLF -> LF normalization
- Backslash-continuation line joining
- Heredoc body extraction (replaced with `__HEREDOC_TO_<sink>__` sentinel)
- Full-line comment stripping (lines starting with `#` after whitespace collapse)
- Whitespace collapse (multiple newlines -> single newline)

**Grammar (bash_parser.peg) handles:**
- ALL statement splitting (newline and semicolon)
- ALL pipe/operator/control structure recognition
- ALL quoting (single-quoted, double-quoted, backtick-quoted strings)
- Process substitution detection

**Tree-walker (command_extractor.py) handles:**
- Walking `_walk_program()` -> `_walk_statement()` -> `_extract_compound_into()`
- Control structure body extraction via `_extract_from_ctrl_body()`
- `bash -c "..."` inner bash decomposition
- Foreign inline code detection -> ASK floor
- Heredoc sentinel detection -> ASK floor for foreign sinks
- Process substitution -> UndecidableSegment(ASK)

## Key Implementation Details

### compound.py changes
`_combine_strictest` now takes 3-tuples `(decision, reason, leaf_text)`:
- Single leaf: returns the raw `resolve_one` reason (contains "allow")
- Multiple leaves: reformats to `"cmd -> pattern"` per entry in combined summary
- This satisfies both `test_simple_allowed_command` (needs "allow" in reason) and
  `test_compound_allowed_includes_match_details` (needs "git status -> git *" format)

### extract_commands() backward compatibility
`extract_commands()` restored to use `_extract_from_tree()` (legacy tree-walker).
The legacy walker was extended to also process `rest_stmts` from the new program node,
fixing `test_adjacent_subshells`: `(cmd1) (cmd2)` now extracts both `cmd1` and `cmd2`.

## Test Results

- `test/unit/test_multiline_bash.py`: 23/23 PASS
- `test/unit/test_bash_parser.py`: 18/18 PASS
- `test/unit/test_compound.py`: 146/146 PASS
- Full suite: **706/706 PASS**

## Self-Review

- No async/await, no threading, no local imports (except approved circular-dependency guards)
- ruff format + ruff check: clean
- py_compile: clean
- Security: no bypasses, all validation preserved
- Parse failures are fail-SAFE (return UndecidableSegment) not fail-OPEN

## Phase Timing and Cost Estimate

| Phase | Time | Notes |
|-------|------|-------|
| Phase 1 (setup from compaction summary) | ~2m | Context recovery |
| Phase 2 (fix test_simple_allowed_command) | ~5m | _combine_strictest 3-tuple refactor |
| Phase 3 (fix test_adjacent_subshells) | ~3m | _extract_from_tree rest_stmts extension |
| Phase 4 (final validation + report) | ~5m | ruff, full suite, report |
| Total | ~15m | |

Estimated cost: ~$0.08 (continuation session, ~40K tokens)

## Known Limitations

1. Nested `$( $( ) )` command substitutions: not fully supported by grammar (existing
   limitation). Test `test_nested_substitution` is skipped via `self.skipTest()`.
2. Grammar regeneration requires the manual TreeNode1 patch (documented above).
   This is a canopy limitation -- generated node attributes must be manually named.
3. `extract_commands()` is preserved for backward compat but uses the legacy tree walker.
   New code should use `extract_structured()` + `resolve_compound_permission()`.

---

## Stage 1 Readability Refactor

**Date**: 2026-06-22
**Status**: Complete
**Tests**: 724/724 PASS (both with and without CLAUDE_SETTINGS_PATH env var)

### Summary

Introduced a typed Abstract Command Model (IR) in a new module `toolguard/parser/command_model.py`. Rewrote `toolguard/parser/command_extractor.py` to operate exclusively on the IR. The legacy `_extract_from_tree` god-function is gone; `extract_commands` is now an IR projection.

### New Module: `toolguard/parser/command_model.py`

IR types introduced:
- `NodeKind` (Enum) -- single dispatcher collapsing the ~12 `_is_*` predicates
- `IRSimpleCmd(text, has_proc_subst, cmd_substs)` -- leaf command with substitutions
- `IRSubshell(wrapper_text, inner_text, inner)` -- subshell/brace group
- `IRProcSubst(text)` -- process substitution
- `IRControlStructure(kind, raw_node, node_text, has_else_or_elif, has_complex_condition, body_has_nested_control, do_clause, ctrl_body, ctrl_condition, then_clause)` -- control structure with pre-computed complexity flags
- `IRPipeline(elements)` -- pipe-separated elements
- `IRCompound(pipelines, raw_text)` -- &&/||/; separated pipelines
- `IRProgram(statements)` -- top-level program

Key functions:
- `node_kind(node)` -- SINGLE raw-tree dispatcher (no `_is_*` scattered around)
- `build_ir(tree) -> IRProgram` -- ONLY function allowed to access raw Canopy nodes
- `_build_control_structure(node, kind)` -- pre-computes all complexity flags during IR build

### Changes to `toolguard/parser/command_extractor.py`

- `LeafCommand` and `UndecidableSegment` changed from `NamedTuple` to regular classes with `__slots__` (backward-compatible: `isinstance`, attribute access, iteration, and index access all preserved)
- Legacy `_extract_from_tree` and all `_is_*` predicates deleted (~300 lines removed)
- All `_extract_compound_into` logic replaced by simple IR traversal
- `extract_commands()` is now an IR projection via `_collect_commands_from_compound`
- `extract_structured_from_grammar()` is now `build_ir()` + `_structured_from_compound()`
- Control-structure handlers now accept `IRControlStructure` and use pre-computed flags
- Only remaining raw-node access: `_extract_from_ctrl_body` (body-statement list walking)
  and `_extract_from_if_stmt_ir` (condition text extraction) -- both minimized, documented

### Confirmed: No hasattr/TreeNodeN outside command_model.py (except)
The two allowed exceptions are:
1. `_extract_from_ctrl_body`: accesses `body_node.elements` to walk the unnamed ctrl_stmt list -- unavoidable, grammar-internal unnamed nodes
2. `_extract_from_if_stmt_ir`: accesses `ctrl.ctrl_condition.text` -- pre-fetched raw node, one-line access

### Files Changed
- NEW: `toolguard/parser/command_model.py` (IR types + builder)
- MODIFIED: `toolguard/parser/command_extractor.py` (IR-based extraction, ~300 lines removed)
- NOT CHANGED: test files, compound.py, multiline.py, grammar, bash_parser.py

### Phase Timing
| Phase | Time | Est. Cost |
|-------|------|-----------|
| Phase 1: Planning + requirements capture | ~20m | ~$0.15 |
| Phase 2: IR design + initial implementation | ~30m | ~$0.30 |
| Phase 3: Debugging + test fixes | ~25m | ~$0.25 |
| Phase 4: Self-review + hasattr cleanup | ~15m | ~$0.15 |
| Total | ~90m | ~$0.85 |
