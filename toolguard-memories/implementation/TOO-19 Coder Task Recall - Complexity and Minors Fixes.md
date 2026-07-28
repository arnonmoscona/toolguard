---
title: TOO-19 Coder Task Recall - Complexity and Minors Fixes
type: note
permalink: toolguard/implementation/too-19-coder-task-recall-complexity-and-minors-fixes
tags:
- TOO-19
- task-memory
---

## Context
Continuing code-review fixes on branch too-19. Previous agent landed correctness fixes
including `toolguard/config_write_guard.py` (verified_write_config: verify-it-parses +
content-loss check + atomic write), wired to most config write sites but NOT installer.py.

Baseline: 1744 tests green (confirmed 2026-07-27 13:49).

## ITEM 1 (SAFETY GAP, highest priority): installer.py bypasses write guard
Route these `_atomic_write_text` calls in toolguard/tools/installer.py through
`verified_write_config` with correct file_format (confirm toml vs json by reading each site):
- ~420 `_atomic_write_text(config_path, content)`
- ~533 `_atomic_write_text(settings_path, json.dumps(data, indent=2) + "\n")` (json)
- ~736 `_atomic_write_text(config_path, updated_text)`
- ~853 `_atomic_write_text(config_path, new_text)`
- ~1485 `_atomic_write_text(config_path, new_text)`

Keep unchanged (NOT config): journal writes (~152, ~270, ~327), README write (~317).

When modifying EXISTING config -> pass expected_patterns (content-loss guard active).
When creating from scratch with no prior rules -> syntax verification alone is fine.
State per-site choice in report.

Add tests: installer config write refuses corrupt text, leaves original file byte-identical.

## ITEM 2 (REFACTOR): migrate() complexity
File: toolguard/scripts/migrate_permissions.py, function migrate(). CC 47, cognitive 122,
nesting 6 (worst in repo). Extract phases: load/discover sources, merge/resolve
permissions, decide removals, write out + report. Behavior IDENTICAL. No test edits
allowed - if tempted to edit a test's expectation, STOP, that means behavior changed;
report instead. Don't pass giant mutable state bag. Target CC well under 47, nesting <6.

## ITEM 3 (REFACTOR): split_array_elements complexity
File: toolguard/rule_sort.py. CC 25, cognitive 71. Reduce WITHOUT hurting readability
(dict-dispatched or named-state scanner suggested). If result is judged less readable,
keep original + explain. Also: mis-splits TOML triple-quoted strings - do NOT fix, just
add one docstring sentence documenting the limitation.

## ITEM 4 (REFACTOR): normalize_entry duplicated rejection blocks
File: toolguard/rule_entry.py, normalize_entry. 4 identical `return None, (Issue(...),)`
blocks - pyscn flagged as clones. Add `_reject(level, message, steps)` helper. Behavior/
exact Issue message/level/remediation text unchanged - verify against existing tests.

## ITEM 5 (REFACTOR): config_validation double iteration
File: toolguard/config_validation.py:125-151. Iterates tools_in_permissions twice with
mutually exclusive conditions - merge into single loop w/ if/elif. Preserve issue order;
check first, if order would change, say so and keep order stable.

## ITEM 6 (MINOR correctness): is_tool_wrapper accepts embedded newlines
File: toolguard/rule_entry.py ~64. `_TOOL_WRAPPER_RE` uses re.DOTALL so
"Bash(a)\nEvil(b)" wrongly passes strict validation. Fix (drop DOTALL or add explicit
"\n" not in pattern check - pick whichever keeps other tests green/clearer). Add test for
newline-bearing pattern rejection. Note any security implication in report.

## ITEM 7 (MINOR): session_start loads configuration twice
File: toolguard/session_start.py, _detect_broken_config_files (~line 230). Re-loads
entire configuration to avoid widening _detect_conflicts's 2-tuple return. Widen internal
API so Configuration loaded once, both results derive from it. Update affected tests incl.
BDD docstrings (this IS an allowed test edit since we're fixing the API, not behavior).

## ITEM 8 (MINOR): config.py imports rule_sort (hot path coupling)
toolguard/config.py is hook HOT PATH, imports rule_sort.py (~1262 lines) solely for
find_multiline_structured_entry_line (one diagnostic string). Move that function into a
leaf module - config_write_guard.py (stdlib-only) may be suitable, or another leaf.
Update test/unit/test_architecture.py LAYERS to enforce new arrangement. If not worth
the churn, may leave + document coupling with reasoning.

## Conventions to respect
- Tests: stdlib unittest, run via `uv run python -m unittest discover -s test -t .`
- BDD Given/When/Then docstring on every test function, kept in sync.
- Always `uv run python`. Format `uv run ruff format .`, lint `uv run ruff check .`.
- NO local imports (unless documented circular dep), NO async, NO threading.
- Doc comments on all new functions/classes.
- NO git write operations.
- Do not edit files under test/ except where explicitly allowed (ITEM 7's API widening).
- Run full suite after EACH item.
- Scope inflation guard: max ~7 new files, ~5 non-trivial modified files, 10 combined.
  This task already touches ~8 items across many files - watch closely, this could hit
  the ceiling. Will report if it does.

## Final report location
/home/arnon/projects/toolguard/toolguard-memories/TOO-19/TOO-19 Review Fixes - Complexity
and Minors Implementation Report.md (frontmatter: title, type: note, tags: [TOO-19, task-memory])

## Wrap-up requirements
- Full suite green, report count.
- ruff format + ruff check clean.
- Run `uvx pyscn analyze --json --skip-deps .` at END, report before/after health score
  and CC/cognitive for migrate, split_array_elements, normalize_entry (read latest JSON
  in .pyscn/reports/).
- Write implementation report per item: what was done, before/after measurements, anything
  deliberately NOT done with reasoning.
