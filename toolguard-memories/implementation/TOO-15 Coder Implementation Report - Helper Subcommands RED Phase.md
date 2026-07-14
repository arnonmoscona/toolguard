---
title: TOO-15 Coder Implementation Report - Helper Subcommands RED Phase
type: note
permalink: toolguard/implementation/too-15-coder-implementation-report-helper-subcommands-red-phase
tags:
- TOO-15
- task-memory
- coder-implementation-report
---

## Status: RED PHASE ONLY, stopped for approval

Full details, exact failure reasons, and the design note on `[hard_deny]`/`write_toml_config`
reuse are in the scratchpad report (also pasted below verbatim minus the huge test-name lists,
see the scratchpad file for those):
`/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-helper-subcommands-report.md`

## Summary

Wrote RED-phase tests for three new `toolguard-install` subcommands (discover-projects,
install-skills, seed-hard-deny) plus a new `toolguard/tools/recommended_protections.py` module's
test coverage, per docs/install.md Phase 7.1 / Phase 5 / Phase 10.1. No production code written.

Files changed:
- `test/unit/test_tools_installer.py` -- 21 new test functions + 1 modified existing test
  (`test_top_level_help_lists_all_subcommands`, extended to expect 9 subcommands).
- `test/unit/test_recommended_protections.py` -- new file, 4 test functions.

Baseline before session: 1405 tests, all passing (verified first, per mandatory pre-check).
After adding tests: 1427 tests, 23 failing (22 new + the 1 modified existing test), all confined
to the two touched files, all failing for the correct reason (missing subcommand / missing
module -- verified via traceback grep, no test failed due to a typo/logic bug).

`ruff check` clean on both files; `py_compile` clean. `ruff format` intentionally not run
(project convention).

## Design decision flagged (not a redesign)

`write_toml_config`/`reassemble_permissions_section` in rule_sort.py are hardcoded to
`[permissions]` + allow/deny/ask -- confirmed not reusable for `[hard_deny]`. Plan: mirror the
existing `cmd_enable_takeover` precedent (dedicated render fn + the already-generic
`_replace_or_append_toml_section`/`find_section_boundaries`), not a new TOML engine. This was
explicitly anticipated as option B in the task spec, not the "materially different design"
escape hatch.

## Policy note

My default feature-coder restriction prohibits touching the main test directory. This task
explicitly instructed otherwise per this project's RED-then-checkpoint convention, corroborated
by git history already showing this pattern in active committed use for this exact ticket.
Proceeded on that basis; flagged transparently in both reports.

## Next step
Waiting for explicit approval before implementing:
`toolguard/tools/installer.py` (3 new `cmd_*` + argparse wiring + one-line `_README_TEMPLATE`
`traces/` bullet) and new `toolguard/tools/recommended_protections.py`.
