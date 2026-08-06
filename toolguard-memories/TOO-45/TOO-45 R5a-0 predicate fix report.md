---
title: TOO-45 R5a-0 predicate fix report
type: note
permalink: toolguard/too-45/too-45-r5a-0-predicate-fix-report
tags:
- task-memory
- TOO-45
---

## Corrected R5 baseline (lead)

R5 still **FAILs** after this step, honestly and as predicted -- this step changed only the instrument (`tools/architecture_fitness.py`), not one line of `toolguard/` production code. Real output on the current tree:

```
=== R5: FAIL ===
  entry point modules (7, from pyproject.toml [project.scripts]): hook, scripts.migrate_permissions, session_start, tools.installer, tools.maintenance, tools.security_audit, update_check
  - hook (entry_point) imported by: tools.decision
  - scripts.migrate_permissions (scripts_package) imported by: auto_migrate, tools.installer, tools.rule_apply
  - update_check (entry_point) imported by: tools.installer
  - cycle: tools.decision <-> hook
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan (the same exclusion R1 applies); an intra-parser import cycle is not evidence toward or against R5's leafness/cycle predicate: parser, parser.bash_parser, parser.command_extractor, parser.command_model, parser.multiline)
```

Three real, honest findings, matching the R5 scoping trace's predictions exactly:

1. `hook` (declared console-script entry point) is imported by `tools.decision` -- the alias-leak cycle (R5a's job).
2. `scripts.migrate_permissions` (declared entry point AND `scripts/` package member) is imported by `auto_migrate`, `tools.installer`, `tools.rule_apply` -- the library-in-a-script-module defect (R5b's job).
3. `update_check` (declared entry point) is imported by `tools.installer` -- the same defect, deferred (R5c, per the trace's recommendation).

Zero false positives now. `hook -> {log_writer, error_log, session_warnings, subagent}` -- the four intra-`runtime` service edges the OLD, layer-label-driven predicate wrongly flagged -- are **gone from the report entirely**, because none of those four modules is a declared entry point or a `scripts/` package member. `session_start` (a genuine entry point, but a leaf) is not flagged either, correctly. `parser.command_extractor <-> parser.multiline` no longer appears; it is named explicitly in `out_of_scope_excluded` instead. `--layers` (a separate, untouched mode) still reports its pre-existing 3 direction violations unchanged.

**This is not a false PASS and not a no-op instrument change presented as progress**: R5 genuinely still fails, on genuine violations, and the fix's only effect was removing false positives and making the previously-unpassable state passable in principle. R5a/R5b/R5c (the in-scope code fixes) are still real, separate, not-yet-done work.

## What changed (tools/architecture_fitness.py only, plus its test file)

Per the ticket's hard rule, **zero lines of `toolguard/` production code were touched**. Both edited files are in `tools/` and `test/`:

- `/home/arnon/projects/toolguard/tools/architecture_fitness.py`
- `/home/arnon/projects/toolguard/test/unit/test_architecture_fitness.py`

### A. Out-of-scope filter on the cycle check, printed explicitly

- Added `R5_OUT_OF_SCOPE_PACKAGES = R1_OUT_OF_SCOPE_PACKAGES` (same tuple, `("parser",)`) with a docstring explaining it's ticket-wide, not R1-specific.
- Rewrote the false claim in `R1_OUT_OF_SCOPE_PACKAGES`'s own docstring (previously: "R5's cycle check ... [has its] own, different reasons to look at (or past) parser/" with no reason ever stated). The new docstring states plainly that measurement found no such reason -- the omission simply made R5 unpassable -- and that R5 now applies the same exclusion via `R5_OUT_OF_SCOPE_PACKAGES`. Also states, correctly, why R6 does *not* need this filter (it only ever scans `tools/`/`scripts/` importers, so it structurally never reaches `parser/`).
- `find_import_cycles(graph, out_of_scope_packages=())` gained an optional parameter (default `()` reproduces the original unfiltered behaviour exactly -- the pre-existing test with no argument still passes unmodified). New helper `_drop_packages_from_graph` removes a package's nodes and every edge to/from them before running Tarjan's algorithm, mirroring how `iter_source_files` already drops generated files for every other detector.
- `compute_predicates` now calls `find_import_cycles(graph, out_of_scope_packages=R5_OUT_OF_SCOPE_PACKAGES)` and adds an `out_of_scope_excluded` dict to R5's report, shaped exactly like R1's (`modules`, `reason`), reusing `r1_out_of_scope_modules()` (same package list, so no duplicate scan). `render_predicates_text` prints it under R5 the same way it already does for R1.

### B. Entry points derived from pyproject.toml, not the .pyscn.toml layer label

- New `parse_entry_point_modules(pyproject_toml_path=PYPROJECT_TOML)`: parses `[project.scripts]` via `tomllib`, strips the leading `toolguard.` and the `:function` suffix from each target, returns a `frozenset` of toolguard-relative module paths. Silently skips (does not crash on) a target outside the `toolguard` package -- none exists today, but a future one shouldn't crash this scan.
- `find_non_leaf_entry_points(graph, entry_point_modules, ...)` rewritten: no longer takes `arch`/`layer_names` at all. A module is judged (for fan-in > 0) if it is in `entry_point_modules` OR its first path segment is `scripts` (package membership kept as a second, independent criterion, matching the original design intent). This is deliberate and structural, not just a default-arg change -- the function literally cannot be influenced by `.pyscn.toml` content any more, which is what closes the labelling exploit, not merely discourages it.
- Result dict's key renamed `layer_or_package` -> `reason`, values `"entry_point"` / `"scripts_package"` (not tested/pinned anywhere previously, safe rename for honesty -- the old name was inaccurate once layers stopped being consulted).
- `compute_predicates` gained an `entry_point_modules: Optional[FrozenSet[str]] = None` parameter (defaults to `parse_entry_point_modules()`), and **no longer calls `parse_architecture_config()` at all** -- that call, and the `arch` variable, existed in `compute_predicates` only to feed the old R5 logic; nothing else in the function ever used it. R5's report now also carries `entry_point_modules` (sorted list) for full transparency.

### C. Regression test that the `.pyscn.toml` gaming move no longer works

Two layers of proof, both in `test/unit/test_architecture_fitness.py`:

1. **Structural**: `TestFindNonLeafEntryPoints.test_relabeling_the_pyscn_toml_layer_map_has_no_effect` asserts (via `inspect.signature`) that `find_non_leaf_entry_points` no longer even accepts an `ArchitectureConfig`/`arch` parameter, then calls it twice with the same graph/entry-points -- a "gamed" `.pyscn.toml` is parsed alongside (to prove it *could* be built) but is never passed in, and the two results are asserted identical.
2. **End-to-end, at the exact site that was vulnerable**: `TestComputePredicates.test_relabeling_pyscn_toml_layer_map_does_not_change_r5_verdict` takes the real `.pyscn.toml`, applies the *exact* 3-line edit the R5 scoping trace used to demonstrate the exploit (moves `error_log`/`session_warnings`/`subagent`/`update_check` out of `runtime` into `foundation`, and `log_writer` into `config`), writes it to a temp file, patches `af.PYSCN_TOML` to point there (never touching the real file on disk -- fully reversible via `mock.patch.object`, no backup/restore needed), and asserts `compute_predicates()["R5"]` (`pass`, `non_leaf_entry_points`, `cycles`) is byte-identical to the un-gamed baseline. A sanity assertion (`gamed_text != real_toml_text`) guards against the string-replace silently matching nothing and the test passing vacuously.

Also added, for completeness/regression coverage of everything this step touched: `TestParseEntryPointModules` (3 tests, including one pinned against the real `pyproject.toml`'s 7 declared entry points -- catches drift if a script target is ever added/removed without updating this list's expectation), 3 more `TestFindNonLeafEntryPoints` cases (entry-point flagged, `scripts/`-package-only module flagged, and the critical **intra-runtime service module NOT flagged** case that pins the I-3 fix), 2 `find_import_cycles` out-of-scope-filter tests (filtered case + default-unfiltered-behaviour case), and 3 more `TestComputePredicates` cases (`out_of_scope_excluded` present and names parser modules with no all-parser cycle surviving; `entry_point_modules` matches `parse_entry_point_modules()`; `R5_OUT_OF_SCOPE_PACKAGES == R1_OUT_OF_SCOPE_PACKAGES`).

**Modified, not just added, in the existing test file**: the old `TestFindNonLeafEntryPoints.test_flags_runtime_module_imported_by_another` and `test_leaf_runtime_module_not_flagged` were rewritten (their fixture called `find_non_leaf_entry_points(graph, arch)`, a signature this step deliberately removed -- there was no way to keep them passing unmodified once the function's whole point changed). This is the direct, necessary consequence of fixing the function these two tests exist to test, not a weakening -- both were replaced with equivalent-or-stronger versions against the new signature (renamed to make clear they test the entry-point criterion specifically). `test_assembles_all_predicate_keys`'s docstring/comment, which asserted the by-then-false "R5/R6 helpers need SOME layer map", was also corrected.

Net test count: 140 -> 152 in this file (2 old rewritten in place, 14 new). Full suite: 2355 -> 2367 OK.

## Acceptance commands -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2367 tests in 28.060s
OK

$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.33s. End-to-end: 61 cases in 3.20s.
OK: no differences.

$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook

$ uv run python tools/architecture_fitness.py --predicates   (R5 section, full)
=== R5: FAIL ===
  entry point modules (7, from pyproject.toml [project.scripts]): hook, scripts.migrate_permissions, session_start, tools.installer, tools.maintenance, tools.security_audit, update_check
  - hook (entry_point) imported by: tools.decision
  - scripts.migrate_permissions (scripts_package) imported by: auto_migrate, tools.installer, tools.rule_apply
  - update_check (entry_point) imported by: tools.installer
  - cycle: tools.decision <-> hook
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan (the same exclusion R1 applies); an intra-parser import cycle is not evidence toward or against R5's leafness/cycle predicate: parser, parser.bash_parser, parser.command_extractor, parser.command_model, parser.multiline)

$ uv run python tools/architecture_fitness.py --layers   (unchanged, untouched mode)
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (3):
  - auto_migrate (config) -> scripts.migrate_permissions (tooling) at line 174 [local import]
  - config_divergence (config) -> error_log (runtime) at line 16
  - hook (runtime) -> tools.decision (tooling) at line 687 [local import]

$ uv run ruff format . && uv run ruff check --no-cache .
148 files already formatted
All checks passed!
```

## Restoration / safety record

- Backed up both files before any edit to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r5a0-backups/` (`architecture_fitness.py.orig`, `test_architecture_fitness.py.orig`, `SHA256SUMS.orig`) -- populated and verified before the first edit, per the hard rule.
- Confirmed no other file in the repo references the two functions whose signatures changed (`find_non_leaf_entry_points`, `find_import_cycles`) or the removed `layer_or_package` key -- repo-wide grep, clean.
- Ran a repo-wide `ruff format --check .` dry run before running the real `ruff format .`, to confirm nothing outside my two files would be touched (148 files already formatted both times).
- No `git add`/commit/checkout/restore/stash/reset issued at any point. `git status --porcelain` line count went from a pre-existing 80 (per the R5 scoping trace's own final check) to 81 at the end of this session -- confirmed the extra line is unrelated to my edits (both `tools/architecture_fitness.py` and `test/unit/test_architecture_fitness.py` were already tracked-and-modified ("M") before I started, consistent with the tree's 9 prior completed stages; my edits added content to already-`M` files, which does not change the porcelain line count for them).
- Checked my additions for prohibited patterns (async/await, `import threading`, new local imports): none found, via grep.

## Self-review notes

- No new runtime dependency; both new/changed functions are stdlib-only (`tomllib`, already imported).
- No `toolguard/` file touched, confirmed by diffing against the pre-edit backups (250 changed lines in `architecture_fitness.py`, 344 in its test file, both fully accounted for by the changes described above) and by grep.
- Considered whether to also rename `R1_OUT_OF_SCOPE_PACKAGES` itself to a ticket-wide name (e.g. `TOO45_OUT_OF_SCOPE_PACKAGES`) rather than adding a second constant that aliases it. Rejected: that would touch every docstring in the file that already names `R1_OUT_OF_SCOPE_PACKAGES` (R1's verdict-type/shim/bare-tuple detectors), a much larger and riskier diff for a cosmetic gain: this task's own scope-inflation guard argues for the smaller, additive change.
- Did not add a companion detector for `importlib.import_module`/`__import__` string-literal gaming (scoping-trace item 3, "companion detector for the gaming surface") -- out of scope for this instruction, which named only items A/B/C. Flagging this explicitly rather than silently doing partial work under a different label: it remains open for whichever future step needs it.

## Elapsed time / cost (estimate)

- Phase 1 (read scoping trace + existing instrument code + pyproject.toml + tests): ~20 min, ~$0.35 (mostly large-file reads).
- Phase 2 (implementation, code + tests): ~25 min, ~$0.45.
- Phase 3 (self-review, acceptance runs, sweeps): ~15 min, ~$0.20.
- Phase 4 (this report, IDE opens): ~5 min, ~$0.05.
- **Total: ~65 min, ~$1.05** (Sonnet 5 pricing estimate based on token usage; rough, not precise).

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 R5 scoping trace]]
- relates_to [[TOO-45 decision log]]
