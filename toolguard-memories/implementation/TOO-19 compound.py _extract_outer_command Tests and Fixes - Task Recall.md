---
title: TOO-19 compound.py _extract_outer_command Tests and Fixes - Task Recall
type: note
permalink: toolguard/implementation/too-19-compound.py-extract-outer-command-tests-and-fixes-task-recall
---

## Task
Add missing unit tests and fix bugs in `toolguard/compound.py::_extract_outer_command`.

Baseline: 1795 tests, all green (confirmed via `uv run python -m unittest discover -s test -t .`).

## Constraints
- No live config edits anywhere (toolguard_hook.toml, settings.json, ~/.toolguard, ~/.config/toolguard, ~/.claude)
- Validate ONLY via unit tests in test/unit/ -- no ad-hoc python -c probes
- stdlib unittest, BDD Given/When/Then docstrings on every test, kept in sync
- ruff format only touched files, ruff check . at end
- No local imports/async/threading

## Task 1: characterization tests for `_extract_outer_command`
Cases: `uv run python -c "print(1)"` -> `uv run python -c`; heredoc sentinel form; multiline
inline code (no embedded newline in result); `-e`/`-r` flags; ATTACHED-flag forms
(`-c'code'`, `-cimport os`, `-uc "code"`); no-inline-flag leaf (fallback case).
Run tests BEFORE fixing, report failures = real bug inventory.

## Task 2: fix bugs
(a) attached inline-flag forms not recognized (loop never breaks)
(b) unbounded fallback returns entire leaf whitespace-collapsed when no break hit
Fix without weakening deny detection: resolve_one(outer_cmd) must still match explicit
deny patterns. May need to separate "matching string" (complete) from "display string"
(bounded) if there's tension.

## Task 3: bound the reason string at compound.py:71
Cap ~120 chars with ellipsis marker for the reason string, keep executor+flag visible,
never introduce newline. Applies specifically to display, independent of matching.

## Report location
/home/arnon/projects/toolguard/toolguard-memories/TOO-19/TOO-19 compound.py _extract_outer_command Tests and Fixes.md
frontmatter: title, type: note, permalink: toolguard/too-19/too-19-compound-extract-outer-command-tests-and-fixes, tags: [TOO-19, task-memory]
Verify no nested toolguard-memories/toolguard-memories/ dir created.
