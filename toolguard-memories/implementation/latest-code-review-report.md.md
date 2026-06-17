---
title: latest-code-review-report.md
type: note
permalink: toolguard/implementation/latest-code-review-report.md
tags:
- TOO-8
- code-review
---

# Code Review Report -- TOO-8 Phase 2/3 (hierarchical config + more-specific-wins + hard_deny)

Date: 2026-06-17
Scope: changed (working-tree) source files for TOO-8.
Files reviewed: toolguard/config.py, permissions.py, compound.py, hook.py,
config_divergence.py, auto_migrate.py, scripts/migrate_permissions.py, plus new tests
test/unit/test_hierarchical.py and test/unit/test_hard_deny.py.

## Summary

High-quality, well-documented refactor. The hierarchical discovery, more-specific-wins
cascade, project-root path anchoring, hard_deny pool, and tool-wrapper consolidation are
correct and well-tested. Full suite 654 tests pass WITH and WITHOUT CLAUDE_SETTINGS_PATH
set; ruff clean; coverage on changed modules is good (config.py 95.6%, permissions.py
90.4%, hook.py 83.8%). No critical or major correctness bugs found. Findings are minor /
maintainability only.

## Critical
None.

## Major
None.

## Minor

### M1. Duplicate TOML/JSON warning logic is split and the Issue variant is unreachable in production
- config.py `Configuration.validation_issues()` (config.py:1363-1383) detects a "Both
  X.toml and X.json exist" warning by scanning for two layers sharing (parent, base_name)
  with different formats. But the real discovery path `_discover_in_dir` (config.py:210-225)
  picks TOML over JSON per base and NEVER emits both layers; it emits the duplicate warning
  itself via a stderr `print`. So via `load_configuration` the Issue branch can never fire
  -- it is only exercised by a hand-built Configuration in
  test_configuration.py:test_duplicate_toml_json_issue.
- Net effect: the duplicate-file warning exists in two forms with different delivery
  (stderr print in discovery vs. logged Issue), and the logged-Issue form is dead in the
  real flow. Not user-facing-incorrect, but confusing and a maintenance trap.
- Recommended fix: make discovery surface the duplicate as an Issue (so it is logged via
  the hook like other validation issues) and drop the stderr print, OR document explicitly
  that the Issue branch covers only externally-constructed Configurations. Pick one source
  of truth.

### M2. Stale docstring: bash_permissions() described as the command-tool entry point
- config.py module docstring (lines 20-23) and `bash_permissions` docstring (config.py:1224-1237)
  state it is "the command-tool entry point so the hook never opens files itself." After
  Phase 2 the hook resolves Bash via `resolve_permission('Bash', ...)` + `allow_deny_for('Bash')`
  and no longer calls `bash_permissions()` (confirmed: no production caller; only tests
  reference it). The legacy `_load_permissions` stderr diagnostics ("Discovered config
  files...", "Loaded N allow patterns") therefore no longer fire at runtime.
- Recommended fix: update the docstrings to note `bash_permissions()`/`_load_permissions`
  are retained for the CLAUDE_SETTINGS_PATH-parity tests and legacy single-file diagnostics
  but are not on the runtime decision path. Consider whether the lost stderr discovery
  diagnostics matter for debugging; if so, route equivalent output through the new path.

## Suggestions

### S1. Compound match-detail format coupling
compound.py:resolve_compound_permission (lines 152-162) reconstructs matched patterns by
splitting the reason on ": " and re-emits "cmd -> pattern", which hook._COMPOUND_MATCH_PATTERN
later re-parses. The coupling is already called out in an in-code comment and degrades only
cosmetically (falls back to '?'). Acceptable; a small structured return (list of
(cmd, pattern)) would remove the round-trip if this is touched again.

### S2. Recall-note vs. actual diff drift (housekeeping, not code)
The Phase 2 recall note lists test_migration.py as a changed file, but git shows it
unchanged. coder-test/test_configuration_abstraction.py is a staged-add with no worktree
file (recall note already flags unstaging it). No action for the code; just confirming the
notes slightly overstate the change set.

## Verification performed
- `uv run python -m unittest discover -s test -t .` => Ran 654 tests, OK.
- Same with `CLAUDE_SETTINGS_PATH` set => Ran 654 tests, OK.
- `uv run ruff check toolguard/` => All checks passed.
- Spot-checked `_strip_tool_wrapper`/`is_tool_wrapper` on edge cases (blanket, MCP double-
  underscore names, nested parens, extended-syntax bodies, bare patterns) -- all correct.
- Verified `_hierarchical_toggle` .local-over-regular precedence and break logic via an
  ad-hoc temp hierarchy -- correct.
