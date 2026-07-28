---
title: TOO-19 config_types.py extraction implementation report
type: note
permalink: toolguard/too-19/too-19-config-types.py-extraction-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Pure structural move, no behaviour change. Created `toolguard/config_types.py`
holding 7 `@dataclass(frozen=True)` types (`Provenance`, `ConfigLayer`,
`ToolPatternLayer`, `TakeoverEnabledConflict`, `TakeoverConfig`,
`ConflictOverride`, `ResolvedDecision`) moved verbatim (docstrings/comments
intact) out of `toolguard/config.py`. `Configuration` stays in `config.py`,
unmoved and unsplit, as instructed.

## Files touched

- Created: `toolguard/config_types.py` (302 lines)
- Modified: `toolguard/config.py` (2108 lines, down from 2365)

No other files touched. (`toolguard/issues.py` and `toolguard/rule_entry.py`
were pre-existing untracked files from an earlier TOO-19 increment, not
touched in this session.)

## Dependency graph -- verified DAG, no cycle

```
toolguard.issues        -> (none)
toolguard.rule_entry    -> toolguard.issues
toolguard.config_types  -> toolguard.rule_entry
toolguard.config        -> toolguard.config_types, toolguard.config_validation,
                            toolguard.issues, toolguard.path_utils, toolguard.rule_entry
```

Matches the required graph exactly. `config_validation.py` and `path_utils.py`
were also checked and import nothing from `toolguard` themselves (also leaves).

Proof script: `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/no_cycle_proof.py`
(AST-derived static import graph + isolated one-at-a-time runtime import of
each module). Output:

```
Static toolguard.* import graph (AST-derived, no execution):
  toolguard.issues -> (none)
  toolguard.rule_entry -> ['toolguard.issues']
  toolguard.config_types -> ['toolguard.rule_entry']
  toolguard.config -> ['toolguard.config_types', 'toolguard.config_validation', 'toolguard.issues', 'toolguard.path_utils', 'toolguard.rule_entry']

Cycle check: does config_types import (directly or transitively) toolguard.config?
  toolguard.config_types transitively imports toolguard.config: False

Runtime import (isolation): importing each module fresh, one at a time.
  imported toolguard.issues OK -> /home/arnon/projects/toolguard/toolguard/issues.py
  imported toolguard.rule_entry OK -> /home/arnon/projects/toolguard/toolguard/rule_entry.py
  imported toolguard.config_types OK -> /home/arnon/projects/toolguard/toolguard/config_types.py
  imported toolguard.config OK -> /home/arnon/projects/toolguard/toolguard/config.py
```

## Key decisions

1. **Import list correction from the task brief.** The brief said the two
   `rule_entry` import lines in `config.py` "may become unused" once
   `ToolPatternLayer`/`TakeoverConfig` moved. I verified this BEFORE editing:
   `RuleEntry`, `entries_for_tool`, `normalize_entry`, `_strip_tool_wrapper`
   are all still directly used by `Configuration`'s own methods (lines
   1245/1301-1302/1368-1369/1451/1455-1456 in the original file), not just by
   the 7 moved dataclasses. `is_tool_wrapper` was already a pure re-export.
   Result: **none** of the 5 `rule_entry` imports in `config.py` needed
   removal. The only actually-unused import after the move was
   `dataclasses.field` (only `ConfigLayer` used it) -- removed that one,
   confirmed by `ruff check` before and after.

2. **`Issue` is not a dependency of the 7 moved classes.** The brief
   suggested they reference `Issue`; grepped the exact line range (767-1039)
   in the original file and found zero references. `config_types.py` imports
   only stdlib + `toolguard.rule_entry` (`RuleEntry`, `_strip_tool_wrapper`),
   not `toolguard.issues`.

3. **Re-export idiom**: used the same explicit `import x as x` form already
   established in `config.py` for `Issue`/`is_tool_wrapper`, for all 7 new
   re-exports, plus one new explanatory comment paragraph appended to the
   existing comment block (matching its style) documenting the move.

4. Every docstring/comment inside the 7 classes is byte-identical to the
   original (verified by inspection during the move; no wording changed).

## No "move verbatim not possible" cases

None. All 7 classes moved with zero adaptation beyond the necessary import
statements at module level (the classes' bodies are untouched).

## Verification performed

- `uv run ruff check .` (repo-wide): all checks passed.
- `uv run ruff format toolguard/config.py toolguard/config_types.py` (touched
  files only): both left unchanged (already formatted correctly on write).
- `uv run python -m py_compile toolguard/config.py toolguard/config_types.py`: OK.
- `uv run python -m unittest discover -s test -t .`: **1571 tests, OK** --
  identical to the pre-change baseline (also captured at session start).
- Grepped both files for indented `import `/`from ` lines: only docstring
  prose matches (e.g. "from this record plus..."), no actual local imports.
- 69-site import-stability check: `grep -rn "from toolguard.config import"
  toolguard/ test/` before vs after, diffing sorted output with the two
  touched files (`config.py`, `config_types.py`) excluded from the comparison
  (since those necessarily gained new explanatory comment lines mentioning
  the pattern). The remaining **68** real cross-file call sites are
  byte-identical, zero changed. The 69th site counted by the original grep
  was `config.py`'s own pre-existing self-referential comment line (not a
  real import site); it shifted line number only because new comment lines
  were added above it in the same file.

## Elapsed time / rough cost estimate

- Phase 1 (planning, reading source files, memory capture, baseline test run):
  ~4 min.
- Phase 2 (implementation: writing config_types.py, editing config.py imports
  and re-exports): ~2 min.
- Phase 3 (self-review: ruff, py_compile, full test run, no-cycle proof
  script, import-site diff verification): ~3 min.
- Phase 4 (this report): ~1 min.
- Total: ~10 minutes wall clock. Token usage was light (a well-scoped,
  mechanical move with no exploratory back-and-forth); rough cost estimate
  well under $1 at current Sonnet pricing.
