---
title: TOO-45 R6-S0 instrument fix report
type: note
permalink: toolguard/too-45/too-45-r6-s0-instrument-fix-report
tags:
- task-memory
- TOO-45
---

Implements S0 of the R6 replacement plan from `toolguard-memories/TOO-45/reports/r6-reassessment.md`. INSTRUMENT-ONLY: `tools/architecture_fitness.py` and `test/unit/test_architecture_fitness.py` only, `git diff --stat` confirms nothing else touched. Companion: [[TOO-45 R6-S0 instrument fix coder task recall]].

## Corrected R6 baseline (real output, `uv run python tools/architecture_fitness.py --predicates`)

```
=== R6: FAIL ===
  guarded layers: config, engine (14 modules, derived from .pyscn.toml)
  checked layers: tooling, runtime
  - hook:37 reaches private `_anchor_file_pattern` via resolve [from_import] (engine)
  - hook:38 reaches private `_check_file_path_hard_deny` via resolve [from_import] (engine)
  - hook:39 reaches private `_decide_file_path_at_level_detailed` via resolve [from_import] (engine)
  - hook:40 reaches private `_match_file_path_pattern` via resolve [from_import] (engine)
  - tools.takeover_audit:91 reaches private `_strip_tool_wrapper` via config [from_import] -- actually defined in rule_entry (config)
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan (the same exclusion R1/R5 apply); it is excluded from R6's guarded set explicitly, not by accident of an incomplete module list: parser, parser.bash_parser, parser.command_extractor, parser.command_model, parser.multiline)
  known limitations of this detector: [4 items, see full text below]
```

`unresolvable` is empty on the real tree -- zero false ambiguities. This is exactly the reassessment's predicted count (5 real private reaches, 1 tooling + 4 runtime), now produced by the fixed instrument instead of hand-verified. R6 goes from "FAIL on 1 artefact site" to "FAIL on 5 real sites" -- worse-looking, correctly, because the detector can now see what was always there.

### The five real private reaches (precise list -- this is S1's work list)

| # | site | reach | route | notes |
|---|---|---|---|---|
| 1 | `tools.takeover_audit:91` | `config._strip_tool_wrapper` (actually defined in `rule_entry`) | from_import | config.py:49 re-exports it from rule_entry; R2 already exposed the same logic publicly as `RuleEntry.stripped_pattern` |
| 2 | `hook:37` | `resolve._anchor_file_pattern` | from_import | `# noqa: F401` re-export; kept alive by 4 test import lines (`test_hierarchical.py:522,535,548,562`) |
| 3 | `hook:38` | `resolve._check_file_path_hard_deny` | from_import | `# noqa: F401` re-export; **zero importers -- dead** (only docstring/prose mentions in `config_types.py`, confirmed by grep) |
| 4 | `hook:39` | `resolve._decide_file_path_at_level_detailed` | from_import | `# noqa: F401` re-export; kept alive by 1 test import line (`test_hook.py:28`) |
| 5 | `hook:40` | `resolve._match_file_path_pattern` | from_import | `# noqa: F401` re-export; **zero importers -- dead** (confirmed by grep) |

Verified by grep against `test/` and `toolguard/` for each of the four hook.py names, cross-checked against the reassessment's own table -- identical conclusion, now instrument-verified rather than hand-verified. Line numbers drifted slightly from the reassessment's (87->91 for takeover_audit) because the file has moved a few lines since that pass; not a discrepancy.

## What changed and why

`find_private_imports` (R6's detector) was rewritten as `scan_private_reaches` (new full report: violations + what couldn't be checked), with `find_private_imports` kept as a thin violations-only wrapper so every existing caller's signature is unchanged.

1. **Guarded set now derived, not hand-maintained.** `_r6_guarded_modules(arch)` returns every top-level module in the `config`+`engine` `.pyscn.toml` layers, minus `parser` (see below). Reused the existing `parse_architecture_config()`/`ArchitectureConfig.package_to_layer()` infra rather than writing a second TOML parser. This alone fixes Defect A (`permission_resolution` now guarded) and independently defeats the specific `takeover_audit`->`rule_entry` gaming move (Defect C), since `rule_entry` is itself in the config layer.
2. **Checked (reach-from) scope now derived too.** `_r6_checked_modules(arch)` = every module in `tooling`+`runtime` layers, replacing the hardcoded `seg in ("tools", "scripts")` check. Fixes Defect B -- `hook.py` is now in scope.
3. **Three reach routes, one code path.** `from mod import _x` (existing), module-attribute access (`mod._x`, `import toolguard.config as cfg; cfg._x`, `toolguard.config._x`), and `getattr(mod, "_x")` with a string-literal name. Attribute/getattr resolution (`_bind_module_aliases` + `_resolve_expr_to_module`) traces import aliases back to a real module path, and multi-hop chains are only followed when the accumulated path corresponds to an actual file on disk -- this specifically prevents a false positive from an expression like `resolve.public_thing._private` (an instance attribute of a public object, not a module) being misread as a fabricated sub-module reach.
4. **Re-export following.** `resolve_defining_module` walks a module's top-level AST bindings and, when the name is itself re-exported (`from X import Y as name`), recurses into `X`/`Y` until it finds the real `def`/`class`/assignment, or gives up with an explicit reason. A private reach is judged by the layer of the DEFINING module, not the immediately-named one. This is the general mechanism the ticket asked for (not just the one artefact) -- proven separately by `test_follows_reexport_through_unguarded_module_to_guarded_origin`, where a foundation-layer pass-through module launders a reach into a guarded config-layer name and is still caught.
5. **`parser` explicitly excluded from R6's guarded set.** Design decision made during implementation, not in the original spec text: `parser` is in the engine layer's `.pyscn.toml` package list, so the layer-derived guarded set would otherwise start reaching into a package the whole TOO-45 ticket puts out of scope (the same reason R1/R5 already exclude it via `R1_OUT_OF_SCOPE_PACKAGES`). Under the old hardcoded set this exclusion held by accident (`parser` was simply never listed); it now holds on purpose, reported the same way R1/R5 report it (`out_of_scope_excluded`, reusing `r1_out_of_scope_modules()` rather than a second scan -- proven identical by `test_r6_out_of_scope_module_list_matches_r1s`). The stale comment that used to justify the old accidental exclusion was rewritten to explain the new deliberate one.
6. **"Cannot check" reporting**, following the R1/R2/R5 idiom (`out_of_scope_excluded`/`R2_UNCHECKED_CLAUSES`):
   - `unresolvable`: per-site list for things the scan tried and could not resolve -- a `getattr()` call with a non-literal name (detected but unverifiable), a re-export cycle, a re-export target with no source file, or a name not found in a re-export target.
   - `known_limitations` (`R6_KNOWN_LIMITATIONS`, 4 fixed entries): what the scan never even attempts -- values flowing through a non-import intermediate variable, fully dynamic access (`__dict__`/`vars()`/`globals()`/`importlib.import_module`), re-export bindings created inside a function/`if`/`try` body, and modules `.pyscn.toml` doesn't map to any layer.
   - Both are wired into `--predicates`' JSON and text output (`render_predicates_text`'s R6 branch), never silently dropped.

## Test fixtures added (test/unit/test_architecture_fitness.py, class `TestFindPrivateImports` + new `TestR6GuardedAndCheckedModules`)

15 new tests, all passing. Covers the required 6 evasion routes (from-import baseline, aliased from-import, attribute access via aliased dotted import, attribute access via bare dotted import, attribute access via `from toolguard import X`, `getattr` with a literal, private import from `permission_resolution`) plus: the mandatory regression test (`test_repointing_import_at_reexport_origin_does_not_clear_violation`, reproducing the exact `config`/`rule_entry`/`_strip_tool_wrapper` shape and asserting both the re-export-routed AND the re-pointed-direct import still report a violation), re-export laundering through an unguarded pass-through module, dynamic-`getattr`-is-unresolvable-not-a-violation, re-export-cycle-is-unresolvable, parser exclusion, and the guarded/checked module derivation itself against the real `.pyscn.toml`.

**`test_ignores_private_import_outside_tools_and_scripts` was INVERTED, not deleted**, per the ticket's requirement -- renamed `test_flags_private_import_from_runtime_module`, same `hook.py` fixture, assertion flipped from "not reported" to "reported", docstring rewritten to explain why (Defect B).

`TestComputePredicates.test_assembles_all_predicate_keys` gained assertions for the new R6 keys (`unresolvable`, `guarded_layers`, `guarded_modules`, `checked_layers`, `checked_modules`, `out_of_scope_excluded`, `known_limitations`) and their real-tree content (permission_resolution present, parser absent, hook present). New `test_r6_out_of_scope_module_list_matches_r1s` proves the exclusion isn't a second, potentially-drifting scan.

No existing test was weakened or deleted (the "exclusion" case was inverted per the explicit instruction, not softened).

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2402 tests in 32.273s
OK
```
(2387 baseline + 15 new; baseline run confirmed green BEFORE any edit, 2387/OK, log saved.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.30s. End-to-end: 61 cases in 3.36s.
OK: no differences.
```

```
$ uv run ruff format .
150 files left unchanged   (1 file reformatted on the first pass, re-run clean after)
$ uv run ruff check --no-cache .
All checks passed!
```

`uv run python -m py_compile` clean on both touched files. `--json` output verified well-formed and correctly nested (`predicates.R6.*`).

## Self-review notes

- No async/await, no threading, no function-local imports introduced -- confirmed both by manual read and by ruff's `PLC0415` (banned local imports) and `F` (unused imports) rules passing clean.
- Reused existing infra everywhere reuse was possible: `parse_architecture_config`/`ArchitectureConfig`, `resolve_toolguard_import`, `iter_source_files`, `relative_module_path`, `first_segment`, the `R1_OUT_OF_SCOPE_PACKAGES`/`r1_out_of_scope_modules()` exclusion idiom, the `R2_UNCHECKED_CLAUSES` "cannot check" idiom. Did not reimplement TOML parsing, generated-file detection, or the layer map.
- `alias.lineno` (not `node.lineno`) is used for from-import sites so each name in a multi-line `from X import (a, b, c, ...)` gets its own accurate line number -- caught this during self-review when the first pass reported all four `hook.py` re-exports at line 34 (the `from` keyword's line) instead of their real lines 37-40; `ast.alias` has carried its own `lineno` since Python 3.10.
- One untracked file, `toolguard-memories/TOO-45/lessons.md`, appeared in `git status` during this session that I did not create (timestamped ~15:20, mid-session) -- content is about a validation-canary discussion unrelated to R6-S0, almost certainly written by a parallel session/agent working the same ticket concurrently (the shared-context note anticipates multiple report authors). Left untouched, not in my scope.

## Time and cost (estimated)

| phase | elapsed | est. cost |
|---|---|---|
| Phase 1: read shared-context/reassessment, investigate existing detector/infra, write task-recall memory | ~30 min (14:32-15:02) | ~$0.90 |
| Phase 2: implementation (detector rewrite, test fixtures, iteration on 2 test failures, ruff/lint fixes, lineno precision fix) | ~24 min (15:02-15:26) | ~$1.10 |
| Phase 3: self-review (diff read-through, JSON output check, grep verification of the 5 real sites) | ~included above | -- |
| Phase 4: report + memory writes | ~2 min | ~$0.10 |
| **Total** | **~56 min** | **~$2.10** |

(Sonnet-class pricing assumed; rough token-based estimate, not a billing record.)
