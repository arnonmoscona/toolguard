---
title: coder-latest-implementation-report
type: report
permalink: toolguard/implementation/coder-latest-implementation-report-1
tags:
- TOO-8
- hierarchical-config
- implementation-report
---

# TOO-8 Phase 2 Implementation Report

Path: implementation/coder-latest-implementation-report.md

## Summary
Implemented TOO-8 Phase 2: hierarchical config discovery (walk project_root up to ~ inclusive), more-specific-wins permission resolution (bash, compound sub-commands, file-path tools), project-root-relative path anchoring, and the Phase-2 cleanup. Single resolution path; no file/format/location logic outside config.py. Baseline 601 tests -> 630 tests, all green (clean env). ruff check clean.

## What changed (files)
Production:
- toolguard/config.py: `_strip_tool_wrapper` rewritten as single STRUCTURAL strip (`_TOOL_WRAPPER_RE = re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)')`); removed `_TOOL_PREFIXES` and the legacy `_tool_prefixes` list in `load_permissions` (resolved the tool-prefix FIXME). Added `_LEVEL_CANDIDATES`, `_discover_in_dir`, `_hierarchical_toggle`, `_discover_levels` (hierarchical walk + specificity + toggle). `Provenance.specificity` field; `ConfigLayer.specificity` property. `Configuration.project_root` property + `resolve_config_path` (project-root anchoring rule). `Configuration.permission_levels(tool)` (group layers per level) + `resolve_permission(tool, decide)` (more-specific-wins cascade). `load_configuration` now builds layers from `_discover_levels` carrying specificity.
- toolguard/permissions.py: added `decide_command_at_level` (deny-first within a level, None on no match) + `make_command_level_decider`.
- toolguard/compound.py: added `resolve_compound_permission(command, resolve_one)` (each sub-command cascades independently; allowed iff all allowed). Legacy `check_compound_permission` retained (still covered by its own tests; no longer on the live path).
- toolguard/hook.py: migrated off `find_project_root` to `config.project_root`. Bash branch + file-path branch now use the more-specific-wins cascade (`resolve_permission`/`resolve_compound_permission`/`resolve_file_path_permission`). Added `_anchor_file_pattern` (project-root anchoring of relative file patterns, prefix-aware, [regex] left untouched), `_decide_file_path_at_level`, `resolve_file_path_permission`. Fail-closed checks use `config.allow_deny_for`.
- toolguard/config_divergence.py: `get_native_permissions` uses a structural `Tool(...)` matcher (removed `governed_tool_prefixes`). `get_toolguard_permissions(config)` now takes a Configuration; `check_and_warn_divergence` uses `load_configuration` (off `discover_config_files`).
- toolguard/auto_migrate.py: `run_auto_migration` uses `load_configuration` + `get_toolguard_permissions(config)`; backup_dir anchored via `config.resolve_config_path(...).expanduser()`.
- toolguard/scripts/migrate_permissions.py: toolguard perms via `get_toolguard_permissions(load_configuration(project_root))`; kept `discover_config_files` only for target-file selection.

Tests:
- test/unit/test_hierarchical.py (NEW, 29 tests): traversal (N levels; toggle on/off/explicit; project outside ~; always-include user; stop at ~; within-level TOML-over-JSON), conflict matrix, project-root-relative backup_dir + Read patterns at project/intermediate/user, [glob]/[regex]/absolute anchoring, ConfigLayer.specificity, resolve_config_path empty, compound empty/ask edge cases.
- test/unit/test_hook.py: `_fake_config` extended with `permission_levels`/`resolve_permission`/`resolve_config_path`/`project_root`; re-pinned 3 file-path tests (Read allowed, Write denied, Edit deny-pattern) to provide patterns via `file_patterns=` instead of patching the removed live use of `load_file_path_patterns`; removed obsolete `find_project_root` patch.
- test/unit/test_config_divergence.py: re-pinned 4 `get_toolguard_permissions` tests to the new Configuration-based signature via a `_config_from_layers` helper (intent preserved).

## Conflict-matrix tests (in test_hierarchical.py::TestMoreSpecificWinsResolution)
- test_child_allow_overrides_parent_deny
- test_child_deny_overrides_parent_allow
- test_no_match_at_child_falls_through_to_parent
- test_no_match_anywhere_is_deny
- test_deny_first_within_a_single_level
- test_three_level_cascade_first_match_wins
- test_compound_each_subcommand_cascades_independently
- test_compound_allowed_iff_all_subcommands_allowed

## Coverage (tools/coverage_stdlib.py, clean env)
Whole-file %: config 95.0, hook 80.5, compound 86.4, permissions 91.2, config_divergence 87.4, auto_migrate 87.7. NEW/CHANGED code has NO unexecuted lines (verified by grepping >>>>>> against the new functions): discovery, resolver, project_root/resolve_config_path, anchoring, deciders, compound resolver all fully covered. Whole-file gaps are PRE-EXISTING legacy paths (CLAUDE_SETTINGS_PATH branches, legacy load_permissions/check_compound_permission still covered by their own tests).

## Key decisions / deviations
1. config_sync user-wins LEFT AS-IS. The FIXME at config.py scalar() is about scalar resolution flipping to project-wins = Phase 5 (decision #4), NOT the tool-prefix cleanup. Per instructions, left untouched along with its pin test test_config_sync_conflict_is_user_wins_phase1. ONLY the tool-prefix FIXME was resolved.
2. Underscore-renaming of legacy config functions (find_project_root, discover_config_files, load_permissions, load_*, merge_*, *_from_sources) NOT done aggressively. They are referenced as PUBLIC by ~7 formal test modules (50+ patch sites) and by external modules log_writer.py and scripts/migrate_permissions.py. Renaming would be pure mechanical churn the prompt elsewhere warns against, and risks breaking live imports. hook.py WAS fully migrated off find_project_root (the named requirement) via Configuration.project_root. Remaining legacy names stay public because they retain genuine out-of-module callers. Flagged for Arnon.
3. ENV CAVEAT: 2 migration tests (test_migration_creates_new_toml_config, test_migration_removes_redundant_patterns) FAIL when CLAUDE_SETTINGS_PATH is set in the shell, because routing migration through load_configuration now honors that override (the old discover_config_files did not). The dev shell has CLAUDE_SETTINGS_PATH=.../featherhill/.claude/settings.local.json set. Tests pass cleanly with `env -u CLAUDE_SETTINGS_PATH`. Test harness does not set the var, so canonical CI is green. Worth deciding whether migration should ignore CLAUDE_SETTINGS_PATH.

## Self-review
- No async/await/threading; no local imports added except pre-existing lazy imports inside functions (left as-is). New module-level imports: re (config, config_divergence), Callable (permissions, compound), make_command_level_decider/resolve_compound_permission (hook).
- Docstrings on all new functions/classes/methods; Given/When/Then on every new test.
- ruff check clean across toolguard/ and test/.
- Documented the hierarchy/resolution model and the project-root-relative-path rule in technical-notes.md.

## Tests command
`uv run python -m unittest discover -s test -t .` (use `env -u CLAUDE_SETTINGS_PATH` in this dev shell to avoid the env artifact). 630 OK.
</content>
</invoke>


---

# TOO-8 Phase 2 -- FIX PASS addendum (2026-06-17)

Fix pass addressing the code-review (latest-code-review-report.md) + verification findings.
Suite: 630 -> 634 tests, GREEN both WITH and WITHOUT ambient `CLAUDE_SETTINGS_PATH`.
`uv run ruff check` clean on all changed files. Coverage on every changed production line:
100% (verified per-line via tools/coverage_stdlib.py annotated `cover/` output).

## P1 -- Suite green regardless of ambient CLAUDE_SETTINGS_PATH (DONE)
- `test/unit/test_hierarchical.py`: added base class `_IsolatedEnvTestCase(unittest.TestCase)`
  whose `setUp` does `patch.dict(os.environ, {}, clear=False)` + `os.environ.pop('CLAUDE_SETTINGS_PATH', None)`
  + `addCleanup(stop)` -- mirrors `test_configuration.py`. All 7 existing classes now inherit it.
- The 2 `test_migration.py` failures were NOT fixed by editing the (committed, formal) tests --
  they are fixed AT THE SOURCE by P2 (migration read path now ignores the env override). Confirmed
  reproduction before (5 failures with var set) and 0 after.

## P2 -- Migration tool internally consistent w.r.t. CLAUDE_SETTINGS_PATH (DONE)
- `config.load_configuration` gained `ignore_env_override: bool = False`. Default False = runtime
  hook single-file behaviour UNCHANGED. When True it skips the `CLAUDE_SETTINGS_PATH` branch and
  always discovers the project hierarchy.
- Read paths switched to `ignore_env_override=True`: `scripts/migrate_permissions.migrate`,
  `auto_migrate.run_auto_migration`, `config_divergence.check_and_warn_divergence`. Now the
  migration/divergence tooling ignores `CLAUDE_SETTINGS_PATH` end-to-end (consistent with its
  project-based write-target selection). Each call site has an explanatory comment.
- New pin tests (in test_hierarchical.py, class `TestMigrationIgnoresEnvOverride`, NOT env-isolated
  on purpose): `test_load_configuration_ignores_env_override_when_requested` (env points at an
  unrelated project; analysis reflects the analysed project, not the env file) and
  `test_load_configuration_honours_env_override_by_default` (default path still honours the override).

## P3 -- Cleanup (PARTIALLY DONE; privatisation BLOCKED by committed formal tests)
- DONE: module-docstring privatisation note in `config.py` -- documents that `find_project_root`
  and `discover_config_files` stay PUBLIC (genuine callers: log_writer.py, migrate_permissions.py)
  pending a separate follow-up to migrate migrate_permissions.py onto the Configuration API; and
  that the from-sources helpers stay public for now because the committed formal suite exercises
  them directly.
- DELIBERATELY NOT DONE (blocked -- would require editing committed formal tests; STOP condition):
  * `auto_migrate` off `config_sync_settings_from_sources`: `auto_migrate.load_config_sync_settings(config_files)`
    has NO live caller in toolguard/ (the hook uses `config.config_sync_settings()` directly), but
    8 committed tests in `test_auto_migrate.py` call it with a `config_files` LIST and assert
    resolution. `Configuration.config_sync_settings` takes no `config_files`, so the body cannot be
    swapped without breaking those tests. Therefore the `config_sync_settings_from_sources` import
    in auto_migrate could not be removed cleanly. NOT cleanly reachable.
  * Privatising `load_permissions` -> `_load_permissions`: referenced by committed
    test_config.py / test_takeover_mode.py / test_permissions.py / test_configuration.py.
  * Privatising `toolguard_permissions_from_sources` / `config_sync_settings_from_sources`:
    imported by committed test_configuration.py.
  All three privatisation targets are blocked by COMMITTED (commit d1e50d7), unmodified formal
  tests. Per the global directive (no changes to the main test directory) + the task STOP rule,
  these renames were left undone and are reported here for Arnon to decide (e.g. authorise a
  test-author/agent pass to update the import/patch sites).
- migrate_permissions.py large migration: NOT attempted (explicitly out of scope this pass).

## P4 -- Minor review items (DONE)
- Unified tool-wrapper recognizer: added public `config.is_tool_wrapper(pattern)` sharing the
  single `_TOOL_WRAPPER_RE` with `_strip_tool_wrapper`. `config_divergence.py` now imports it and
  dropped its own `import re` + local `_TOOL_WRAPPER_RE`. One source of truth.
- Negative `_anchor_file_pattern` regression tests (test_hierarchical.py, TestAnchorFilePattern):
  `test_tilde_pattern_left_untouched` (`~`-patterns NOT anchored) and
  `test_relative_pattern_does_not_match_same_name_outside_project` (a relative `Read(src/**)`
  anchored to project root DENIES a same-named `src/x.py` in an ancestor). [regex]/absolute cases
  were already covered.
- technical-notes.md: extended the "Project-root-relative paths" section with the behaviour-change
  note (relative patterns match only inside project root; same-named ancestor paths no longer match)
  and `[regex]` exclusion; updated the tool-wrapper section to reference the shared `is_tool_wrapper`.
- compound.py `resolve_compound_permission`: added a comment documenting the implicit coupling to
  `permissions.decide_command_at_level`'s `...: <pattern>` reason format (and `hook._COMPOUND_MATCH_PATTERN`),
  noting the `'?'` fallback degrades only the cosmetic detail, never the decision.

## P5 -- Artifacts
- `.gitignore`: appended `.coverage` and `cover/` under a "Coverage artifacts" comment.
- `coder-test/test_configuration_abstraction.py` (the `AD` entry): INVESTIGATED. The file is
  ALREADY ABSENT from the working tree (coder-test/ is empty on disk); the `AD` is a
  staged-add-with-worktree-delete that lives only in the git INDEX (it was `git add`-ed but never
  committed -- no commit touches it). There was nothing to `rm` on the filesystem. Clearing the
  staged add requires a git index operation (`git rm --cached` / `git reset -- coder-test/...`),
  which is a git WRITE -- left for Arnon. Reporting so he can unstage it.

## Files changed this fix pass
Production: toolguard/config.py, toolguard/config_divergence.py, toolguard/auto_migrate.py,
toolguard/compound.py, toolguard/scripts/migrate_permissions.py. Docs: technical-notes.md,
.gitignore. Tests (untracked, part of in-flight Phase 2): test/unit/test_hierarchical.py.
NO committed/formal test files were modified.

## Self-review
- ruff check clean; py_compile clean on all changed files.
- No async/await/threading. New test-method-local imports match the pre-existing style in
  test_hierarchical.py (lines 236/455/518...). Docstrings on `is_tool_wrapper`; Given/When/Then on
  all 4 new tests.
- Suite GREEN 634 tests both with and without `CLAUDE_SETTINGS_PATH`.
