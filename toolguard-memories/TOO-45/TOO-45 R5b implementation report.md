---
title: TOO-45 R5b implementation report
type: note
permalink: toolguard/too-45/too-45-r5b-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Split `toolguard/scripts/migrate_permissions.py` (the `toolguard-migrate` console script) into
a thin CLI wrapper and a new library module, `toolguard/permission_migration.py`, which now
holds all the importable logic. Repointed the three external importers
(`toolguard.auto_migrate`, `toolguard.tools.installer`, `toolguard.tools.rule_apply`) at the
new module. `scripts.migrate_permissions` is now gone from R5's `--predicates` violation list;
only the deliberately-deferred `update_check` remains.

## Why `config` layer, and why this name

Per `.pyscn.toml`'s layer-allow rules: `config` may import `{config, foundation}`; `tooling`
may import `{tooling, runtime, engine, config, foundation}`. `auto_migrate` lives in `config`;
`tools.installer`/`tools.rule_apply` live in `tooling`. The **only** layer both can legally
reach is `config` (or `foundation`, but this logic needs `config`'s own machinery --
`load_configuration`, `discover_config_files`, `config_write_guard`, `rule_entry`, `rule_sort`
-- so it cannot be foundation). This matches the R5 scoping trace's own inference: "the writers
belong beside `config_write_guard`."

Named `toolguard/permission_migration.py` rather than reusing `migrate_permissions` (that name
stays on the CLI script) or overloading `auto_migrate.py` (a different concern: marker-file
scheduling, not the merge/write logic itself). No naming collision in the package.

## What moved

Everything migrate() needs, including its own private helpers, so the CLI script has zero
residual dependents importing from it and `migrate()` itself doesn't need to reach back into
`scripts/` (which would just relocate the violation and additionally break the layer rule,
since `config` cannot import `tooling`):

`create_backup`, `extract_pattern_key`, `is_superset`, `find_redundant_patterns`,
`extract_meaningful_prefix`, `detect_similar_patterns`, `generate_permissions_section`,
`_patterns_from_permissions`, `write_toml_config`, `write_json_config`, `update_settings_file`,
`_MigrationSources`, `_load_migration_sources`, `_find_skipped_ungoverned_patterns`,
`_print_skipped_ungoverned`, `_print_divergent_report`, `_print_redundant_report`,
`_resolve_target_config_path`, `_print_similar_pattern_warnings`, `_print_dry_run_summary`,
`_build_merged_permissions`, `_apply_migration`, `migrate`.

Function bodies are byte-identical to the original (only cross-reference comments/docstrings
naming the old module path were updated). `toolguard/scripts/migrate_permissions.py` keeps
only `parse_args()` and `main()`, now importing `find_project_root` from `toolguard.config`
and `migrate` from `toolguard.permission_migration`.

The backward-compat re-export block in the old module (`from toolguard.rule_sort import (...)
# noqa: F401 -- re-exported for backward compat`, there solely so `test_migration.py` could
import `get_tool_priority`/`sort_patterns` from the script module) is gone -- I rewrote the one
consumer to import those two names directly from `toolguard.rule_sort`, which is where they
actually live.

## `auto_migrate.py`'s local import

`auto_migrate.py:172-174` carried:
```python
# Sanctioned circular-import escape: migrate_permissions imports this module.
# TOO-45 R5 targets this cycle; the marker comes off when R5 breaks it.
from toolguard.scripts.migrate_permissions import migrate  # noqa: PLC0415
```
This became a normal top-level `from toolguard.permission_migration import migrate`. The cycle
that justified the local import never actually existed the other way in this case --
`toolguard/scripts/migrate_permissions.py` never imported `auto_migrate` -- so once `migrate`
lived in a module `auto_migrate` can import at module scope, the local import had no remaining
purpose. `test.unit.test_architecture.TestNoNewLocalImports` (the project's own ratchet against
undocumented local imports) still passes since there's simply no local import left to flag.

## Doc-drift sweep

Grepped the whole tree for `migrate_permissions` and checked every hit. Fixed every place that
made a precise, now-false claim about where a moved function lives (`:func:`/`:mod:`
cross-references and one literal file-path mention):

- `toolguard/tools/installer.py` (3 docstring refs + 1 code comment ref to
  `_build_merged_permissions`)
- `toolguard/tools/rule_apply.py` (2 docstring refs)
- `toolguard/rule_sort.py` (2 docstring refs to `generate_permissions_section`)
- `toolguard/error_log.py` (1 docstring ref to `create_backup`'s collision-fix precedent --
  also corrected the accompanying rationale, since "avoid a runtime-path dependency on that
  CLI-script module" was true when the target was a `tooling`-layer module but is no longer the
  actual reason now that the target is `config`-layer and layer-legal from `runtime`; the real
  reason -- not pulling in config-resolution machinery from a path that must survive config
  resolution itself failing -- is what the docstring says now)
- `test/unit/test_error_log.py` (same collision-fix precedent, found via the doc-drift sweep
  after fixing `error_log.py` -- this is the "grep the whole repo for the same string" case
  CLAUDE.md calls out)

Left unchanged, deliberately: `toolguard/config.py:207`, `toolguard/rule_entry.py:14`,
`toolguard/config_write_guard.py:23`, `toolguard/tools/sorters.py:15`,
`test/unit/test_toml_config.py:200`, `test/unit/test_rule_sort.py:1484`, and
`toolguard/tools/installer.py:1228`. All of these use "migrate_permissions" as a conceptual
name for the migration *operation* / CLI step (which still exists and is still correctly named
that), not as a precise module-path claim -- none of them became false.

## Test changes (blast radius: predicted ~88, actual: same test count, zero deletions)

- `test/unit/test_migration.py` (84 tests): import block repointed to
  `toolguard.permission_migration` for the 9 moved functions actually used, and to
  `toolguard.rule_sort` for `get_tool_priority`/`sort_patterns` (which never belonged to the
  script module in the first place). Five `patch("toolguard.scripts.migrate_permissions.X")`
  targets (3x `datetime`, 2x `verified_write_config` -- 5 distinct patch call sites, 5 more
  `verified_write_config` sub-cases) and two local `from toolguard.scripts.migrate_permissions
  import extract_meaningful_prefix` became `toolguard.permission_migration.X`. No test logic,
  assertion, or Given/When/Then changed -- every one of these tests exercises the same function
  bodies unchanged, just imported from their new home, so there was nothing behavioural to
  rewrite. **Zero tests deleted.**
- `test/unit/test_auto_migrate.py`: 3x `@patch("toolguard.scripts.migrate_permissions.migrate")`
  became `@patch("toolguard.auto_migrate.migrate")`. This is a real, necessary change in
  *where* the patch targets, not just a string swap for its own sake: `auto_migrate.py` now
  binds `migrate` at module import time via a top-level `from ... import migrate`, so per
  `unittest.mock`'s "patch where it's looked up, not where it's defined" rule, patching the
  defining module's `migrate` would no longer intercept the call `run_auto_migration()` makes --
  the local-import version genuinely needed the old patch target, the top-level-import version
  genuinely needs the new one. Verified by running the suite (these 3 tests are in it and pass).
- `test/unit/test_architecture.py`: rewrote the stale
  `GRANDFATHERED_LOCAL_IMPORTS` history comment (not a test body) that documented
  `auto_migrate -> scripts.migrate_permissions` as one of two "genuine circular-import escapes
  ... carrying the PLC0415 marker" -- that's no longer true, the marker is gone because the
  cycle that justified it is gone, not relocated.
- `test/unit/test_architecture_fitness.py`: one docstring fix in
  `TestSmokeAgainstRealTree.test_check_layers_runs_on_real_tree` -- updated "3 pre-existing
  DIRECTION violations" to "2", with a note explaining R5b closed the third. The test's own
  assertions (`report.unmapped == []`) were already count-independent and needed no code change
  -- confirmed by running it.

## `.pyscn.toml`

Added `permission_migration` to the `config` layer's `packages` list (one list entry). Without
this the module would be silently unmapped and stop being validated by `--layers`, exactly the
failure mode the R5 scoping trace's I-1 finding warned about.

## Verification

All commands run for real, verbatim output below.

```
$ uv run python -m unittest discover -s test -t .
...
Ran 2367 tests in 28.536s

OK
```

```
$ uv run python tools/corpus_build.py --verify
...
In-process: 6401 cases in 8.26s. End-to-end: 61 cases in 3.17s.

OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (2):
  - config_divergence (config) -> error_log (runtime) at line 16
  - hook (runtime) -> tools.decision (tooling) at line 697 [local import]
```
(Both pre-existing and explicitly out of scope for R5b -- `config_divergence -> error_log` is
R5d's job, `hook -> tools.decision` is deliberately left open for R6. Down from 3 violations to
2, as expected.)

```
$ uv run python tools/architecture_fitness.py --predicates
=== R5: FAIL ===
  entry point modules (7, from pyproject.toml [project.scripts]): hook,
  scripts.migrate_permissions, session_start, tools.installer, tools.maintenance,
  tools.security_audit, update_check
  - update_check (entry_point) imported by: tools.installer
  (out of scope -- toolguard/parser/ ...)
```
`scripts.migrate_permissions` is gone from the violation list. R5 still reports FAIL overall
because `update_check` is the deliberately deferred second violation (R5c, ~180 tests, not this
task's job).

```
$ uv run ruff format . && uv run ruff check --no-cache .
149 files left unchanged
All checks passed!
```

## Console-script smoke test (not mocked)

Built a throwaway fixture project under scratchpad (`.claude/settings.local.json` with two
allow patterns, no toolguard config yet), then ran the real installed `toolguard-migrate`
console script against it via `uv run --project /home/arnon/projects/toolguard toolguard-migrate`:

- `--dry-run`: correctly previewed "Found 2 pattern(s) to migrate", the backup/create/add/remove
  plan, no files touched.
- Real run (no flags): created `.claude/toolguard_hook.toml` with the two patterns rendered and
  sorted, backed up `settings.local.json`, and pruned both migrated patterns out of it (verified
  by `cat`-ing both files afterward -- `toolguard_hook.toml` had the two `Bash(...)` allow
  entries, `settings.local.json`'s `allow` list was empty).

This exercises the full path: `pyproject.toml [project.scripts]` entry-point resolution ->
`migrate_permissions.main()` -> `permission_migration.migrate()` ->
`create_backup`/`write_toml_config`/`update_settings_file`, with real file I/O, no mocks.
Fixture directory removed afterward.

## Files touched

New (1):
- `toolguard/permission_migration.py`

Modified, substantive (2):
- `toolguard/scripts/migrate_permissions.py` (trimmed from 1263 lines to a ~100-line CLI wrapper)
- `toolguard/auto_migrate.py` (import + local-import/marker removal)

Modified, mechanical import-path fix + doc-drift (10):
- `toolguard/tools/installer.py`, `toolguard/tools/rule_apply.py`, `toolguard/rule_sort.py`,
  `toolguard/error_log.py`, `.pyscn.toml`, `test/unit/test_migration.py`,
  `test/unit/test_auto_migrate.py`, `test/unit/test_architecture.py`,
  `test/unit/test_architecture_fitness.py`, `test/unit/test_error_log.py`

No files deleted, no tests deleted, no files touched outside the repository. No git write
operations were issued (`git status`/`diff`/`show` read-only only).

## Reuse check (no reimplementation)

This task is a pure relocation of existing, working code -- verbatim function bodies moved to
a new module, three import statements repointed, docstrings corrected. No new logic was
written that could have duplicated stdlib, an existing dependency, or existing project code.

## Backups / rollback

Original bytes of every file this task edited were copied to
`/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r5b-backups/`
before any edit, with a sha256 manifest (`_MANIFEST.sha256`). `toolguard/permission_migration.py`
is new, so rollback for it is simply deleting the file. Restoring any of the other 11 files is a
copy-back from that directory, verifiable against the manifest.

## Self-review

- Anti-pattern scan: no async/await, no threading, no local imports introduced in any touched
  file (checked by grep + `test.unit.test_architecture`'s own ratchet, which passed).
- `uv run python -m py_compile` on every touched production file: clean.
- `uv run ruff format .` / `uv run ruff check --no-cache .`: clean, one file reformatted
  (`test_migration.py`, pure line-length reflow from the shorter module name), re-verified
  green after.
- Diffed every touched file against its pre-edit backup individually (not just `git diff`,
  since the working tree carries nine other uncommitted TOO-45 stages) to confirm each edit was
  exactly the intended change and nothing incidental slipped in.
- Requirements re-checked line by line against this note and the original prompt before writing
  this report; every acceptance command above was actually run for this report, not recalled
  from memory.

## Elapsed time / cost estimate

Tool-execution wall time observed via `date` calls: roughly 17:31 to 17:48 (~17 minutes),
though this undercounts think/generation time between tool calls that `date` doesn't capture.
Rough phase breakdown:
- Planning/reading (scoping trace, source files, all doc-reference sites): largest share,
  most of it spent reading rather than executing commands.
- Implementation (writing the new module, trimming the script, updating 3 importers, 6 test/doc
  files, `.pyscn.toml`): moderate, mostly mechanical given the plan was precise going in.
- Verification (suite runs x4, corpus verify, guard/layers/predicates, ruff x2, live smoke test,
  per-file backup diffs): the rest.

Estimated cost: this ran on Sonnet 5 at typical subagent token volumes for a task of this size
(several large file reads, one ~750-line file write, ~15 edits, several multi-minute test-suite
runs). Rough order of magnitude: low single-digit dollars total; not tracked precisely since
this environment doesn't expose token counts directly to the agent.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 R5 scoping trace]]
