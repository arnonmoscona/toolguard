---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- coder-task-recall
- TOO-8
- hard_deny
---

# Coder Task Recall -- TOO-8 Phase 3 (hard_deny)

Date: 2026-06-17. Acting as feature-coder. Project: toolguard. NO git writes.

## Objective
Implement `[hard_deny]` safety valve: an unoverridable hard-deny. A (typically less-specific)
config declares rules that NO more-specific config can override.

## Semantics (this phase; document + flag for Arnon)
- `[hard_deny]` = section with two optional pattern lists: `deny` and `allow`. toolguard
  extension -- read ONLY from toolguard_hook config (TOML/JSON), NOT native settings*.json.
- Collected from ALL levels into ONE pool (union across hierarchy) per decision #3. Not
  per-level propagation.
- Checked FIRST, before more-specific-wins cascade:
  - If matches any hard_deny.deny AND does NOT match any hard_deny.allow -> DENY (hard-deny
    reason). Cannot be overridden by any level's normal allow.
  - Otherwise fall through to Phase 2 cascade unchanged.
- hard_deny.allow is ONLY a carve-out exception to hard_deny.deny. NOT a forced allow; does
  NOT affect normal cascade.
- Patterns support extended syntax ([regex]/[glob]/[native]) + tool wrappers (Bash(...),
  Read(...), etc.), same matchers as normal perms.
- Apply to: Bash commands, EACH sub-command of compound (compound hard-denied if any
  sub-command is), and file-path tools (Read/Write/Edit, tool-scoped like normal patterns).

## Implementation
- Parse `[hard_deny]` in config layer model; expose via `Configuration.hard_deny(tool_name)`
  returning pooled (deny, allow) tool-scoped patterns, relative paths anchored to project
  root (reuse Phase 2 anchoring `_anchor_file_pattern`).
- Integrate into resolver: hard_deny evaluated before cascade for bash/compound/file-path
  uniformly. Matching stays in permissions.py/compound.py.
- Single resolution path. No behavior change when no `[hard_deny]` configured.

## Tooling rules (CRITICAL)
- Green BOTH: `uv run python -m unittest discover -s test -t .` AND
  `env -u CLAUDE_SETTINGS_PATH uv run python -m unittest discover -s test -t .`
- Do NOT `ruff format` (corrupts repo). Use `ruff check`. Coverage:
  `uv run python tools/coverage_stdlib.py`. Don't hand-edit parser/bash_parser.py.
- Tests are unittest (NOT pytest). Every test fn needs Given/When/Then docstring.

## Tests required (BDD docstrings)
- hard_deny.deny denies even when MORE-SPECIFIC level allows (unoverridable)
- hard_deny.allow carve-out exempts matching command
- hard_deny at ancestor/user level blocks project-level allow
- compound: one hard-denied sub-command denies whole compound
- file-path (Read/Write/Edit) hard_deny
- no [hard_deny] => Phase 2 unchanged (regression)
- hard_deny pooled across multiple levels
- relative path in hard_deny pattern anchors to project root

## DoD
1. hard_deny: checked first, unoverridable, single resolution path
2. Suite green both ways; ruff check clean; files compile
3. New tests w/ G/W/T; coverage >90% on changed code (report numbers)
4. technical-notes.md documents hard_deny briefly
5. Report to implementation/coder-latest-implementation-report.md

## Out of scope
Phases 4-7 (logging, non-perm cross-level, SessionStart, docs restructure).

Stop+report if design contradiction, ambiguous allow-exception vs existing test, or scope
exceeds Phase 3.


---

# TOO-8 Phase 4 -- Dead-code removal + config-loader consolidation [task recall 2026-06-18]

Folds into uncommitted Phase 4 changeset. No behavior change except de-dup + memoization.

## Part A -- remove confirmed dead code (all re-confirmed: zero non-test prod caller)
1. Delete toolguard/validation.py (byte-for-byte dup of config_validation.py; zero importers).
2. Remove Configuration._toolguard_permissions_from_sources (config.py:1737); test refs in test_configuration.py (2 sites + import).
3. Remove check_file_path_permission (hook.py:239); ~30 sites in test_hook.py -> re-point to resolve_file_path_permission_detailed, preserve intent.

## Part B -- consolidate config-file loading
- ONE memoized loader keyed on (path, st_mtime_ns). Inner @functools.lru_cache _parse(path, mtime_ns); public computes mtime. cache_clear() for tests.
- Adopt at config.py format-dispatch sites: 329 (_load_permissions_from_file, strict toggle), 414 (_load_governed_tools_from_file, silent []), 507 (takeover, silent continue), 1616 (_parse_source, warn+None). PRESERVE each site's error semantics (loader raises; wrappers keep their except).
- Supersede load_toml_config / toml_config.py -> delete once unreferenced; re-point test_toml_config.py TestTomlConfigLoader to new loader.
- Anti-pattern guard: loader must have prod callers (it will).

## Tooling
- Suite green BOTH: `uv run python -m unittest discover -s test -t .` AND `env -u CLAUDE_SETTINGS_PATH ...`. Baseline = 672 OK both.
- NO ruff format. `uv run ruff check`. coverage: tools/coverage_stdlib.py. Don't touch bash_parser.py. NO git ops.
- Python 3.14; tomllib always available -> hoist to top-level import.
