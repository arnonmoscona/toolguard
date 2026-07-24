---
title: TOO-30 Coder Implementation Report - RED Phase Tests
type: note
permalink: toolguard/too-30/too-30-coder-implementation-report-red-phase-tests
tags:
- TOO-30
- implementation
- red-phase
---

## Summary

TDD phase 1 (RED) for TOO-30. Added 27 new unit test methods (4 new `TestCase`
classes) to `test/unit/test_configuration.py` only. No production code
(`toolguard/config.py` or any other file) was touched. Full requirements text and
exact API contract were captured to
`implementation/Coder Latest Task Recall - TOO-30 RED Phase Tests.md` before
starting.

## Files changed

- `test/unit/test_configuration.py` (only file modified):
  - Added `from contextlib import contextmanager` and
    `import toolguard.config as config_module` to the top-of-file import block
    (both always succeed today; only specific not-yet-existing *attributes* on
    `config_module`, referenced inside test method bodies, fail in isolation).
    The existing `from toolguard.config import (...)` block itself was left
    completely unchanged (no lines added or removed).
  - Added two module-level test helpers: `_toml_permissions_block(...)` (builds
    a minimal `[permissions]` TOML block) and `_isolated_hierarchy(tmp,
    xdg_config_home=None)` (a contextmanager that patches `Path.home()` to a
    fresh empty tmp dir, clears `os.environ`, and patches
    `find_project_root()` -- necessary because this repo dogfoods toolguard on
    itself, so a real `~/.claude/toolguard_hook.toml` and possibly a real
    `~/.config/toolguard/rules/` exist on the dev machine and would otherwise
    leak into layer counts/exact scalar assertions).
  - Added 4 new `TestCase` classes at the end of the file (after
    `TestExplicitModeAdjacentToml`): `TestRulesDirectoryDiscovery` (13 tests),
    `TestRulesDirectoryMergeSemantics` (7 tests),
    `TestRulesDirectoryValidationAndProvenance` (6 tests),
    `TestRulesDirectoryExplicitModeBypass` (1 test).

## Test methods added, mapped to ticket scenarios

**Discovery (`TestRulesDirectoryDiscovery`)**
- `_rules_dir()` white-box: `test_rules_dir_uses_xdg_config_home_when_set`,
  `test_rules_dir_defaults_to_home_config_when_xdg_unset`,
  `test_rules_dir_falls_back_to_default_when_xdg_config_home_is_empty` (extra
  edge case beyond the spec: empty-string XDG_CONFIG_HOME treated as unset).
- `_discover_rules_files()` white-box:
  `test_discover_rules_files_missing_directory_returns_empty`,
  `test_discover_rules_files_empty_directory_returns_empty`,
  `test_discover_rules_files_sorted_lexicographically_by_stem`,
  `test_discover_rules_files_same_stem_toml_wins_over_json`,
  `test_discover_rules_files_ignores_other_extensions_and_subdirectories`.
- End-to-end via `load_configuration()`:
  `test_missing_rules_dir_produces_no_extra_layers_end_to_end`,
  `test_empty_rules_dir_produces_no_extra_layers_end_to_end`,
  `test_rules_dir_files_become_layers_in_lexicographic_order_end_to_end` (also
  asserts `provenance.level == "user"`),
  `test_rules_dir_files_appended_after_primary_user_candidates_end_to_end`,
  `test_rules_dir_duplicate_toml_json_only_toml_layer_and_warning_end_to_end`
  (also asserts the existing "both formats" `validation_issues()` warning
  fires for rules-dir files).

**Merge semantics (`TestRulesDirectoryMergeSemantics`)** -- mostly hand-crafted
`ConfigLayer`s with `source_type="toolguard_hook_rules"`, exercising the
EXISTING generic `Configuration` methods directly (per ticket item 9, no new
code needed here):
`test_rules_dir_permissions_merge_into_same_user_level_as_claude_hook`,
`test_project_level_deny_still_overrides_rules_dir_allow`,
`test_rules_dir_deny_beats_claude_allow_within_user_level`,
`test_rules_dir_hard_deny_pooled_with_claude_hard_deny`,
`test_toolguard_permissions_includes_rules_dir_patterns`,
`test_extended_regex_pattern_passes_through_from_rules_dir_layer`. Plus one
end-to-end test that DOES require new code:
`test_rules_dir_scalars_have_zero_effect_end_to_end` (governed_tools /
no_match_fallback / takeover_mode.enabled must NOT be affected by a rules-dir
file setting them -- includes a positive-control assertion that the file's own
valid permissions DID load, so the test cannot pass vacuously just because the
file failed to load at all).

**Validation/provenance (`TestRulesDirectoryValidationAndProvenance`)**:
`test_config_layer_unexpected_keys_defaults_to_empty_tuple`,
`test_config_layer_accepts_unexpected_keys_field`,
`test_level_for_path_returns_user_for_rules_dir_path`,
`test_level_for_path_still_returns_project_for_unrelated_path` (regression pin
for the unchanged case), `test_resolve_permission_detailed_reason_cites_rules_dir_file_path`,
`test_unexpected_key_reported_as_error_and_permissions_still_resolve_end_to_end`.

**CLAUDE_SETTINGS_PATH (`TestRulesDirectoryExplicitModeBypass`)**:
`test_claude_settings_path_bypasses_rules_dir_scan`.

## Red-state tally (`uv run python -m unittest discover -s test -t .`)

`Ran 1511 tests` (1484 pre-existing + 27 new). `FAILED (failures=8, errors=10)`.

- **10 ERROR** (AttributeError/TypeError -- helper/field not implemented yet):
  `test_discover_rules_files_empty_directory_returns_empty`,
  `test_discover_rules_files_ignores_other_extensions_and_subdirectories`,
  `test_discover_rules_files_missing_directory_returns_empty`,
  `test_discover_rules_files_same_stem_toml_wins_over_json`,
  `test_discover_rules_files_sorted_lexicographically_by_stem`,
  `test_rules_dir_defaults_to_home_config_when_xdg_unset`,
  `test_rules_dir_falls_back_to_default_when_xdg_config_home_is_empty`,
  `test_rules_dir_uses_xdg_config_home_when_set`,
  `test_config_layer_accepts_unexpected_keys_field`,
  `test_config_layer_unexpected_keys_defaults_to_empty_tuple`.
- **6 FAIL** (assertion failure -- feature not wired):
  `test_rules_dir_duplicate_toml_json_only_toml_layer_and_warning_end_to_end`,
  `test_rules_dir_files_appended_after_primary_user_candidates_end_to_end`,
  `test_rules_dir_files_become_layers_in_lexicographic_order_end_to_end`,
  `test_rules_dir_scalars_have_zero_effect_end_to_end`,
  `test_level_for_path_returns_user_for_rules_dir_path`,
  `test_unexpected_key_reported_as_error_and_permissions_still_resolve_end_to_end`.
- **11 new tests currently PASS** -- these are the intentionally-decoupled
  "existing generic code needs no change" confirmatory tests (item 9's hand-crafted
  `ConfigLayer` tests) plus two genuinely-trivial no-op tests
  (`test_missing_rules_dir_produces_no_extra_layers_end_to_end`,
  `test_empty_rules_dir_produces_no_extra_layers_end_to_end`) and the
  `CLAUDE_SETTINGS_PATH` bypass test -- all of these pass today for a
  legitimate reason (either the code path they exercise is already generic/
  unchanged, or "nothing happens" is trivially true before discovery exists)
  and are expected to REMAIN green after phase 2 lands, serving as regression
  pins. Flagged for GREEN-phase verification: `test_missing_rules_dir_...` and
  `test_empty_rules_dir_...` currently pass only because no code calls the
  rules-dir discovery path at all yet (not because missing/empty-dir handling
  was verified) -- worth a quick sanity glance once discovery is implemented,
  though no test change is needed (the assertions are already the correct
  ones for the no-op scenario).
- **2 pre-existing, UNRELATED failures** (confirmed via `git stash` baseline
  before any TOO-30 changes): `test_default_config_when_no_files` and
  `test_takeover_mode_not_loaded_from_claude_settings` in
  `test/unit/test_takeover_mode.py`, both failing with
  `AssertionError: True is not false` on `tc.enabled`. Root cause: those two
  tests call `load_configuration(..., ignore_env_override=True)` without
  isolating `Path.home()`, so they read this machine's REAL
  `~/.claude/toolguard_hook.toml`, which (per the "dogfood via global
  install" memory) apparently has `takeover_mode.enabled = true` set. Not
  caused by my changes and out of scope (I did not touch this file per
  instructions). All 1484 pre-existing tests other than these two continue to
  pass; collection succeeded.

## `ruff check`

`uv run ruff check .` -- clean (`All checks passed!`). One `E402` was hit
during development (module-level import not at top) from initially placing
`import toolguard.config as config_module` near the new test section as the
prompt suggested; fixed by moving it to the top-of-file import block instead
(safe per hygiene rules -- importing the module itself never fails, only
specific attributes on it referenced inside method bodies can fail). Did NOT
run `uv run ruff format` per the CLAUDE.md project-specific override.

## Self-review notes

- AST-scanned the diff: no `async def`/`await`, no `threading`/`Thread`, no
  local (in-function) imports introduced.
- Verified every new test method has a BDD Given/When/Then docstring
  (project CLAUDE.md requirement) via an AST check.
- `uv run python -m py_compile test/unit/test_configuration.py` succeeds.
- Confirmed via `git diff` that the original
  `from toolguard.config import (...)` block has zero added/removed lines --
  only new, purely-additive imports/classes were introduced.
- Confirmed via `git status`/`git diff --stat` that `test/unit/test_configuration.py`
  is the only toolguard code file touched (the two `toolguard-memories/`
  changes are basic-memory MCP writes: one new report/recall note I created,
  and a pre-existing uncommitted "Current Task Context" switch from TOO-15 to
  TOO-30 that predates this session -- not something I edited directly).
- Caught and fixed one test-design bug during self-review: my first draft of
  `test_rules_dir_scalars_have_zero_effect_end_to_end` passed today for the
  wrong reason (the rules-dir file isn't discovered at all yet, so of course
  its scalars had "zero effect" -- trivially, not meaningfully). Added a
  positive-control assertion (the file's own valid `Bash(gh *)` allow pattern
  must be present) so the test is genuinely RED now and will only go GREEN
  once both discovery AND section-filtering are correctly implemented
  together.

## Elapsed time / cost estimate

- Phase 1 (planning: read ticket, memory, CLAUDE.md, explored config.py/test
  file conventions): ~16:48-16:52, ~4 min.
- Phase 2 (implementation: wrote 27 test methods + 2 helpers, iterated on
  test runs): ~16:52-17:07, ~15 min.
- Phase 3 (self-review: ruff fix, anti-pattern AST scan, tally verification,
  bug fix for the vacuous-pass test): ~17:07-17:15, ~8 min.
- Phase 4 (this report): ~2 min.
- Total elapsed: ~29 min.
- Estimated cost: roughly $0.70-$1.00 (Sonnet 5; dominated by reading
  `config.py`/`test_configuration.py` in large chunks -- combined input reads
  on the order of 100-150K tokens across the session -- plus ~15-20K output
  tokens generating the ~740-line test addition and this report).

## Constraints honored

- Did not touch `toolguard/config.py` or any other production file.
- Did not modify any file other than `test/unit/test_configuration.py` (plus
  basic-memory notes, which are outside the "production code" constraint).
- Did not run `uv run ruff format` (project-specific override).
