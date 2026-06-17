---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- implementation
- TOO-8
- coder-report
---

# Coder Implementation Report -- TOO-8 Phase 1 (Config Abstraction) -- COMPLETE

Status: COMPLETE. hook.py migrated to the config abstraction; formal tests updated
(intent preserved); 34 abstraction tests promoted into test/. Tree GREEN: 600 tests OK.

## Summary
Finished the remaining Phase 1 work now that test/ edits were authorized. The hook is
fully decoupled from files/formats/locations: it obtains a Configuration once via
`load_configuration(cwd)` and uses only semantic accessors. All discovery/parsing lives
in the config module.

## Files changed (this session)
- `toolguard/hook.py` (heavily reworked; ~225 lines changed vs HEAD):
  - Imports: dropped `discover_config_files`, `load_permissions`, `load_governed_tools`,
    `load_takeover_mode_config`, `load_toml_config`, `validate_permissions`,
    `load_config_sync_settings`. Now imports `load_configuration`, `find_project_root`
    (still used only for log_dir fallback + divergence project_root) and `run_auto_migration`.
  - `_run_startup_validation(env_config, start_dir, config=None)`: replaced the hand-rolled
    file walk + path.stem inspection + TOML/JSON dual-warn + per-file load/merge with a loop
    over `config.validation_issues()`, logging each Issue. New optional `config` param lets
    `main` pass the already-loaded Configuration; falls back to `load_configuration` if None.
  - `load_file_path_patterns(tool_name, start_dir, config=None)`: now a trivial adapter over
    `Configuration.allow_deny_for(tool_name)` (returns lists). No file opening, no format
    branching, no takeover-filter code (filtering happens in permission_layers).
  - `main`: loads `config = load_configuration(cwd)` once; uses `config.takeover_mode()`
    (TakeoverConfig dataclass; attribute access replaces dict keys), `config.config_sync_settings()`,
    `config.governed_tools()`, `config.bash_permissions()`, and `load_file_path_patterns(..., config)`.
    Builds a `takeover_dict` from the TakeoverConfig to feed the still-dict-based
    `check_and_warn_divergence` / `run_auto_migration` (those clients unchanged).
- `test/unit/test_hook.py` (updated, intent preserved): added `_fake_config()` helper that
  exposes the Configuration accessors `main` consumes. Re-pointed:
  - TestHookToolGovernance (3): patch `load_configuration` -> fake with governed/bash; assert
    same allow/deny + "Not a governed tool" outcomes.
  - TestLoadFilePathPatterns (2): build a real one-layer Configuration and pass via `config=`;
    assert only the requested tool's patterns are returned (no Write/Bash leakage). Same intent.
  - TestFilePathToolsInMain (5): patch `load_configuration` (governed Read/Write/Edit) + keep
    patching `load_file_path_patterns` for the pattern outcomes; assert same allow/deny/missing.
  - TestStartupValidation: builds a real Configuration (native + hook layers), calls
    `_run_startup_validation(env, dir, config)`; asserts native tools (WebSearch/WebFetch/
    mcp__unknown__tool) never appear in the log -- same OUTCOME as before.
  - Added 3 coverage tests: validation logs Issues from config; validation auto-loads config
    when None; load_file_path_patterns auto-loads config when None.
- `test/unit/test_configuration.py` (NEW): the 34 abstraction tests promoted from coder-test,
  docstring updated for the formal run command. coder-test copy left in place.

## Definition of done -- all met
1. hook.py migrated; grep confirms NO `open(`, no config `json.load`/`tomllib`, no `.toml`/
   `.json`/`path.stem`/format branching (only `json.loads` on stdin + a user-facing message
   mentioning toolguard_hook.toml + a docstring). "NO LEAKS".
2. test/unit/test_hook.py updated (intent preserved); 34 abstraction tests promoted into
   test/unit/test_configuration.py.
3. `uv run python -m unittest discover -s test -t .` => 600 tests OK. `ruff check` clean.
   Changed files compile.
4. Coverage: config.py 93% (all misses pre-existing legacy loader lines 59-572; new
   abstraction fully covered). hook.py 78%; new wiring + new `_run_startup_validation` /
   adapter branches covered. Remaining hook misses (327-329 takeover-warning w/ log_dir;
   352-363 auto-migration sub-branch; 430-498 command/file deny + error paths) are
   integration-only branches that were untested at HEAD too -- not a regression.

## Key decisions
- Kept `_run_startup_validation` and `load_file_path_patterns` signatures backward-compatible
  by adding an optional `config=None` param (auto-loads if absent). This preserves the
  function-level contract while letting `main` load once.
- Built a `takeover_dict` adapter in `main` rather than changing `config_divergence` /
  `auto_migrate` signatures (those expect dicts; out of Phase 1 hook scope).
- TestLoadFilePathPatterns now passes a real Configuration instead of mocking open(); this
  better matches the new abstraction and still pins per-tool extraction intent.

## Anti-pattern scan: clean
No async/await, no threading, no local imports added (a couple of `import toolguard.hook as`
inside test methods are pre-existing test-local style, left as-is). Docstrings present on all
new/changed functions.

## Not done (correctly out of Phase 1 scope)
- config_divergence.check_and_warn_divergence still calls discover_config_files for its own
  sourcing (local import). That client was "already migrated" only for get_toolguard_permissions;
  full divergence sourcing migration is not in the hook-focused Phase 1 DoD. Flag for Phase 2.
- No traversal, no more-specific-wins (Phase 2). Behavior preserved: 2 levels, union, global
  deny-first.

## Tooling notes
- unittest only (no pytest). Ran `uv run python -m unittest discover -s test -t .`.
- Did NOT run `ruff format` (known to churn quotes + corrupt except-clauses here). `ruff check`
  only, clean.


## Addendum: TOO-8 Phase 1 surgical fix (config_sync M1 + minor cleanups)

### HEAD behaviour found (config_sync conflict direction)
Verified empirically and by reading source. At HEAD the legacy resolver
`auto_migrate.load_config_sync_settings` filters `discover_config_files()` output
(ordered project-first, user-last) and iterates forward with last-occurrence-wins.
Because the user file is LAST, **HEAD resolves config_sync conflicts USER-wins**.
(The current refactor delegates this to `config.config_sync_settings_from_sources`,
which preserves the same forward-iteration / user-wins semantics.)

The uncommitted Phase-1 `Configuration.scalar()` iterated `reversed(self.layers)` with
last-wins, which made PROJECT win -- a behaviour divergence (project-wins). Confirmed
with a side-by-side harness: scalar()=PROJECT_DIR vs legacy=USER_DIR before the fix;
both USER_DIR after.

### Fix
`Configuration.scalar()` (toolguard/config.py) now iterates `self.layers` in forward
(discovery) order so the user (least-specific, last) layer wins -- matching HEAD. Added
a `# FIXME(TOO-8 Phase 2, decision #4)` noting Phase 2 will intentionally flip
config_sync + other scalars to more-specific-wins (project-wins), made test-visible.

### Tests
- Added `test_config_sync_conflict_is_user_wins_phase1` in `test/unit/test_configuration.py`
  pinning the user-wins direction for both `scalar()` and `config_sync_settings()`, with a
  Phase-2 FIXME.
- IMPORTANT (flagged to caller): the pre-existing new test `test_scalar_dotted_last_wins`
  in the SAME uncommitted Phase-1 changeset asserted project-wins (the buggy direction).
  Since it is untracked (part of the work under review, not a prior committed test) and
  encoded the very divergence being fixed, its assertion was corrected to user-wins.

### Minor cleanups
- Removed unused `start_dir` parameter from `_level_for_path` and updated the single caller.
- Reworded the `config.py` module docstring: legacy loaders are internal implementation
  retained for Phase 1 (governed_tools/takeover_mode/bash_permissions delegate to them),
  not "deprecated".

### Verification
- `uv run python -m unittest discover -s test -t .`: 601 passed (was 600 + new pin), OK.
- `uv run ruff check` on changed files: clean. py_compile: clean.
- Coverage: config.py 93%; all changed regions (scalar loop ~930-960, _level_for_path
  ~1095-1115) fully covered.
