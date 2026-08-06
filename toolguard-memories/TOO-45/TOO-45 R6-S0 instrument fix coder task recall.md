---
title: TOO-45 R6-S0 instrument fix coder task recall
type: note
permalink: toolguard/too-45/too-45-r6-s0-instrument-fix-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Implement step S0 of the R6 replacement plan (TOO-45, branch too-45, repo /home/arnon/projects/toolguard). INSTRUMENT-ONLY: change only `tools/` and `test/`, never `toolguard/`. This is deliberate isolation so no refactor can tune the measurement it's scored on.

Source docs (read in full, not re-derived here):
- `toolguard-memories/TOO-45/reports/_shared-context.md`
- `toolguard-memories/TOO-45/reports/r6-reassessment.md` -- S0 spec is section 6's table row + the "Why S0 must come first" prose.

## What S0 requires

Fix `tools/architecture_fitness.py`'s `find_private_imports` (R6 detector, currently at line ~2216-2254):

1. Derive the guarded module set from `.pyscn.toml`'s `[[architecture.layers]]` map (config + engine layers) instead of the hardcoded `R6_GUARDED_MODULES = {"config","permissions","compound","resolve"}`. Reuse existing `parse_architecture_config()` / `ArchitectureConfig.package_to_layer()` -- do not write a second TOML parser.
2. Catch private ACCESS via 3 routes: `from mod import _x` (existing), module-attribute access (`mod._x`, including aliased/dotted `toolguard.config._x`), and `getattr(mod, "_x")` with a string-literal name. Track import aliases (`import x as y`, `from pkg import x as y`) to resolve the base expression of an attribute/getattr call back to a toolguard module.
3. Follow re-exports to the defining module: for any private-name reach, walk the target module's own top-level AST bindings; if the name is itself imported (re-exported) from elsewhere, recurse to find where it's actually `def`/`class`/assigned. Flag based on the DEFINING module's layer, not just the immediately-named module. This is what makes the `takeover_audit` -> `rule_entry` re-point (Defect C in the reassessment) still get caught -- though note: since `rule_entry` is itself in the config layer per `.pyscn.toml`, deriving the guarded set from the layer map ALSO independently defeats that specific gaming move, even without re-export following. Re-export following is still required generally (per spec) for the case where a re-export passes through a module OUTSIDE the guarded set (e.g. a foundation-layer pass-through).
4. Cover `runtime` layer (hook.py etc.) as well as `tooling` (tools/scripts) as the "reach-from" scope -- derive this from the layer map too (tooling + runtime layers), not a hardcoded directory-name check. This is what inverts `test_ignores_private_import_outside_tools_and_scripts`.
5. Report what it CANNOT check, explicitly, in the `--predicates` output, following R1/R5/R2's existing `out_of_scope_excluded`/`sanctioned_exclusions` idiom (see `R1_OUT_OF_SCOPE_PACKAGES` and `r1_out_of_scope_modules()`).

Design decision (mine, to record): `toolguard/parser/` is explicitly out-of-scope for the WHOLE TOO-45 ticket (per R1/R5's `R1_OUT_OF_SCOPE_PACKAGES` precedent, both already exclude it with a documented reason). Under the OLD hardcoded guarded set, R6 never reached `parser/` "regardless" (per a comment at line ~694-696 that is now stale). Under the NEW layer-derived guarded set, `parser` is literally in the engine layer's package list in `.pyscn.toml`, so without an explicit exclusion R6 would newly start reaching into an out-of-scope package. I am applying the same `R1_OUT_OF_SCOPE_PACKAGES` exclusion to R6's guarded set for consistency with its siblings, and updating the now-stale comment to explain this is now an explicit exclusion, not an accidental non-reach.

## Required test fixtures (6 evasion routes, from the reassessment's probe)

Must build fixtures and require the detector to catch each:
1. `from mod import _x` -- baseline (already worked).
2. `from mod import _x as y` -- aliased from-import (already worked structurally, verify).
3. Module attribute access: `import toolguard.config as cfg; cfg._x` / `toolguard.config._x`.
4. `getattr(mod, "_x")` with string literal.
5. Reach via a post-D1a engine module not in the old hardcoded set: `from toolguard.permission_resolution import _x` (Defect A).
6. Reach via re-export laundering through a module outside the guarded set (tests requirement 3 above generally, not just the specific artefact).

PLUS the mandatory regression test: re-pointing the `takeover_audit`-shaped import at `rule_entry` directly must NOT flip the verdict from FAIL to PASS (Defect C, the specific artefact named in the ticket).

PLUS: `test_ignores_private_import_outside_tools_and_scripts` must be INVERTED (not deleted) to prove hook.py-shaped runtime reaches ARE now caught (Defect B).

## Acceptance commands (paste real output in the report)

```
uv run python -m unittest discover -s test -t .           # expect OK (2387 + new tests)
uv run python tools/corpus_build.py --verify               # expect: no differences
uv run python tools/architecture_fitness.py --predicates   # corrected R6 reading
uv run ruff format . && uv run ruff check --no-cache .
```

## Report the honest new baseline

R6 will likely FAIL with MORE instances than today's single reported one. Reassessment measured 5 real private reaches (1 tooling: `takeover_audit`/`_strip_tool_wrapper`; 4 runtime: `hook.py`'s 4 `noqa: F401` re-exports of `resolve` privates -- 2 dead, 2 kept alive by 5 test import lines). List them precisely in the report; they become S1's work list. Note these numbers were measured against the PRE-S0 (broken) detector by hand; my job is to get the FIXED detector to report the true count on the real tree and reconcile against this expectation, explaining any difference.

## Hard rules

- No git write ops (checkout/restore/stash/reset/commit/push) -- read-only git only.
- Backup originals to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r6-s0-backups/` BEFORE editing anything.
- `uv run python`, never bare `python`. `unittest`, not pytest. `ruff check --no-cache` always.
- INTENT/TOUCHES disclosure block + `TG_INTENT=1`/`TG_ATTEST_READONLY=1` env prefix on any Bash command carrying authored code (heredocs, `python -c`, scratch scripts).
- Do not touch `/tmp/toolguard-master-copy` or `/tmp/toolguard-branch-copy`.
- Do not edit anything outside the repo.
- Report to basic-memory `TOO-45/TOO-45 R6-S0 instrument fix report.md`, tagged task-memory + TOO-45, leading with the corrected baseline and precise list of real private reaches. No hard-wrapped paragraphs.

## Existing infra found (reuse, don't reinvent)

- `parse_architecture_config()` / `ArchitectureConfig.package_to_layer()` / `.allow_for()` -- already parses `.pyscn.toml`'s `[architecture]` block via `tomllib`.
- `check_layers()` -- shows the exact `first_segment(rel) -> layer` matching pattern to mirror.
- `resolve_toolguard_import(module_name, level, importer_rel)` -- resolves an import node to a toolguard-relative dotted path.
- `iter_source_files()` -- already excludes generated files (banner-detected), used by every style/debt predicate.
- `relative_module_path()`, `first_segment()`.
- `R1_OUT_OF_SCOPE_PACKAGES = ("parser",)`, `r1_out_of_scope_modules()` -- the exclusion-reporting idiom to mirror for R6's "cannot check" report.

Existing R6 tests live in `test/unit/test_architecture_fitness.py`, class `TestFindPrivateImports`, lines ~2233-2315. `compute_predicates()` wires `r6_sites = find_private_imports(toolguard_dir)` at line ~2403 and builds the `"R6"` dict at line ~2508. `render_predicates_text()` has the R6 rendering branch at line ~2649.
