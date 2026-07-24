---
title: TOO-30 Test Isolation Cleanup - Implementation Report
type: note
permalink: toolguard/too-30/too-30-test-isolation-cleanup-implementation-report
tags:
- TOO-30
- implementation
- testing
- pre-push
---

## Summary

Implemented the pre-push follow-up: a shared `ConfigIsolationMixin` (per the
agreed, fixed design) plus retrofit of all 8 scoped test files. This is a pure
test-isolation-mechanism swap -- no production code touched, no test
assertions/BDD intent changed. Full suite: 1511 tests, 0 failures/errors,
confirmed stable across 3 consecutive runs (checked specifically for
isolation-induced ordering flakiness). `ruff check .` clean repo-wide.

## Files created

- `test/unit/_config_isolation.py` -- `ConfigIsolationMixin` with
  `isolate_config_environment(*, xdg_config_home=None, extra_env=None)`,
  exactly as specified in the task (class/method name, signature, return
  shape `(home, project)` unchanged). Leading underscore so `unittest
  discover`'s `test*.py` pattern skips it; confirmed test count stayed at
  1511 (mixin adds zero tests of its own).

## Files retrofitted (isolate_config_environment call counts)

| file | calls added | notes |
|---|---|---|
| test_configuration.py | 11 | Retired `_isolated_hierarchy` entirely (7 real usages, not the ~9 originally estimated). Also closed 2 pre-existing gaps in `TestLoadConfigurationHierarchy` (its own comments admitted "real user-level ~/.claude may leak in"), 1 hidden gap inside `TestRulesDirectoryMergeSemantics` (one end-to-end test lived in an otherwise memory-only class), and consolidated 1 more manual `patch.object(Path,"home")`. Removed now-dead `_make_project` helper. |
| test_takeover_mode.py | 7 | 2 inline patches replaced (as flagged). Audit of the "~2 other call sites" found 5, not 2 (`TestFilePathToolTakeoverFiltering` has 5 methods, all previously missing Path.home isolation despite an env-clearing decorator) -- all fixed. |
| test_hierarchical.py | 11 | Highest call-site count (18 total identified, matching the original scope-check exactly: 11 converted + 7 left as justified exceptions -- see below). |
| test_hard_deny.py | 5 | `TestHardDenyFilePath` (4) + `TestHardDenyThroughMain` (1); all previously used a correct but hand-rolled nested-home dance that didn't actually need nesting (only project-vs-user distinction mattered), so all cleanly fit the mixin's sibling shape. |
| test_toml_config.py | 2 | Matches scope exactly. |
| test_logging_streams.py | 1 | Matches scope exactly; also dropped a now-unneeded `pyproject.toml` marker file once the mixin's own `find_project_root` patch made real-walk discovery unnecessary. |
| test_config.py | 4 | 1 was the flagged ad hoc patch (`test_raises_when_nothing_found`). Found 3 MORE gaps in `TestConfigDiscovery` (calls `discover_config_files()`, which also reads `Path.home()` -- previously only `find_project_root` was patched there). |
| test_migration.py | 11 | 4 were the flagged ad hoc patches (`TestMigrationTargetLevel`). Found 7 MORE gaps: `TestMigration` (6 tests) and `TestMigrationWithRedundantPatterns` (1 test) patched the WRONG attribute path (`toolguard.scripts.migrate_permissions.find_project_root`, which `discover_config_files()`'s internal call never goes through) and had zero `Path.home()` isolation -- confirmed via an early diagnostic run that dumped this repo's own real dogfooded `toolguard_hook.toml` patterns (`git push:*`, `uv run ruff format:*`) into migration-tool stdout output. Investigated further: those patterns turned out to belong to the test's OWN inline `settings.local.json`/`toolguard_hook.toml` fixtures (not a real leak from this machine) -- migrate()'s target-selection logic already filters discovered files down to project_root's own `.claude` dir (that's literally what TOO-15 fixed), so the gap was real but inert for these particular assertions. All 6+1 pass identically before and after isolation -- no behavior change, so nothing is flagged as a latent bug, but the isolation gap itself was real and worth closing per the mission. |

Total: 52 `isolate_config_environment()` call sites across 8 files, plus the 1
new shared module.

## Justified exceptions (NOT converted to the mixin)

1. **`test_hierarchical.py`, 7 call sites** (`TestHierarchicalTraversal`'s
   `test_walk_collects_multiple_ancestor_levels`,
   `test_toggle_off_uses_only_project_and_user`,
   `test_toggle_on_explicit_walks_full_hierarchy`, `test_walk_stops_at_home`;
   `TestProjectRootRelativePaths._resolve_backup` helper (3 test methods);
   `TestRelativeFilePathPatterns._resolve_read` helper (3 test methods);
   `TestAnchorFilePattern.test_relative_pattern_does_not_match_same_name_outside_project`).
   All of these test the ancestor-walk feature itself and genuinely need
   `project` NESTED several levels under `home` (or, in `test_walk_stops_at_home`'s
   case, a directory ABOVE `home`) -- the mixin's fixed, agreed API always
   returns `home`/`project` as siblings, so it cannot represent these layouts.
   They were already correctly isolated by hand (`patch("toolguard.config.Path.home", ...)`
   + `patch("toolguard.config.find_project_root", ...)`), just not through the
   shared mixin. Left as-is rather than forcing an awkward mixin-plus-re-patch
   shape that would add boilerplate instead of reducing it (the task's own
   stated criterion for using the mixin).
2. **`test_config.py`, `TestFindProjectRoot`, 6 of 7 methods.** The class
   docstring explicitly states "Real (unmocked) tests of ...
   find_project_root's marker walk" -- deliberately testing the real function
   against real filesystem structure, independent of any `Path.home()` state
   (markers are found immediately near `start`, before the walk would ever
   reach a real home boundary). Only the 7th method
   (`test_raises_when_nothing_found`) had an actual ad hoc `Path.home` patch
   (needed to bound the walk for the RuntimeError scenario) and was migrated.
3. **`test_configuration.py`, `TestRulesDirectoryExplicitModeBypass`,
   `TestLoadConfigurationHierarchy`'s 2 `CLAUDE_SETTINGS_PATH` tests,
   `TestExplicitModeAdjacentToml`.** `load_configuration()`'s explicit
   `CLAUDE_SETTINGS_PATH` branch returns before ever calling `_discover_levels()`
   / `Path.home()` (confirmed by reading `toolguard/config.py` lines
   1892-1932) -- these are immune to the leak by construction. Per Arnon's
   explicit instruction, `TestRulesDirectoryExplicitModeBypass` WAS still
   migrated to the mixin anyway (named as one of "the 4 TOO-30 classes");
   the other 3 were left alone since they weren't named and the mixin adds
   no defensive value there.
4. **`test_hard_deny.py`, `TestHardDenyAccessor`, `TestHardDenyCommand`,
   `TestCheckHardDenyUnit`; `test_hierarchical.py`,
   `TestMoreSpecificWinsResolution`, `TestResolveCompoundEdgeCases`,
   `TestConfigLayerSpecificity.test_specificity_reflects_provenance`;
   `test_configuration.py`, `TestRulesDirectoryMergeSemantics` (all but one
   test) -- construct `Configuration` directly from hand-built layers, zero
   filesystem I/O, no isolation needed (matches the task's own stated
   exception for the last one).
5. **`test_hard_deny.py` dead helper `_build_config`** (pre-existing, defined
   but never called) -- left untouched; out of scope for an isolation-only
   refactor, flagging here for visibility only.

## Latent-bug check (hard constraint from the task)

No test's pass/fail behavior changed once properly isolated. Every retrofitted
test was re-run individually and as part of the full suite; all passed both
before (via the ad hoc/absent isolation) and after (via the mixin), for the
same reasons. No test is flagged as a suspected latent bug.

## Verification

1. `uv run python -m unittest discover -s test -t .` -- 1511 tests, 0
   failures/errors, run 3x consecutively (checked for the isolation-swap's
   most likely failure mode: order-dependent state leakage) -- all 3 runs
   identical (1511, OK).
2. `uv run ruff check .` -- clean, repo-wide.
3. Did NOT run `uv run ruff format` (explicit project-specific override in
   the task and CLAUDE.md).
4. `uv run python -m py_compile` on all 9 touched/created files -- all OK.
5. `git diff --stat` -- confirmed only the 8 scoped test files + the 1 new
   file changed by me. `toolguard/config.py`, `docs/architecture.md`,
   `docs/configuration.md` also show as modified, but these are PRE-EXISTING
   changes from TOO-30's feature phase (confirmed via `git status` at session
   start, before any of my edits) -- I only ever used the Read tool on
   `toolguard/config.py`, never Edit/Write.

## Time/cost estimate

- Phase 1 (planning, reading all 8 files + task memory): ~35 min, ~$1.20
- Phase 2 (implementation across 9 files): ~70 min, ~$3.50
- Phase 3 (self-review, stability reruns, ruff/compile checks): ~10 min, ~$0.30
- Phase 4 (report + handoff): ~5 min, ~$0.15
- Total: ~2h, ~$5.15 (rough token-based estimate for Sonnet 5, not precise
  billing)
