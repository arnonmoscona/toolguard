---
title: TOO-78 implementation plan
tags:
- task-memory
- TOO-78
permalink: toolguard/too-78/too-78-implementation-plan
---

# TOO-78 -- reorganize modules into layer packages

**Ticket**: refactor to organize modules in layer packages. "We now have quite a few modules in toolguard, and it's not as easy to find what I want. Reorganize modules in packages. Each package corresponds to one architecture layer."

**Branch**: `too-78`. **Sealed commit for the prediction experiment**: `1cfd318`.

## Decisions taken with Arnon, 2026-09-09

1. **Pragmatic 1:1**, not strict layer names. New packages only for layers that are currently loose modules. Pre-existing packages keep their names.
2. **`hook.py`, `session_start.py` and `subagent.py` stay flat** at `toolguard/` top level. The whole runtime layer stays where it is; its entry points remain visible and the console scripts and `python -m` forms are untouched.
3. **`parser/`, `tools/`, `scripts/`, `testing/` are untouched.** No module moves out of them.
4. **`install` becomes its own layer** (Arnon): installation support is not foundation noise, and nothing except install processes should reach it. This is an architectural-correctness decision, not tidying.
5. **`update_check.py` moves into `install/`.** Nothing imports it -- it is a console-script entry point whose only job is reporting install/update state.
6. **`config.py` -> `config/loading.py`** is the only module rename. Its own docstring already calls it "Configuration loading for toolguard".
7. **`config/__init__.py` and `api/__init__.py` re-export** their layer's public surface, so `from toolguard.config import Configuration` and `toolguard.api.decide` keep working unchanged.
8. **`api.py` -> `api/api.py`** plus a re-exporting `__init__.py`, mirroring `config/`. An IDE Move cannot turn a module into an `__init__.py`, and this shape can be moved by the refactoring tool.
9. **The layer model is a DAG, declared as data**, in a new `[architecture.dag]` table in `.pyscn.toml`. Measured 2026-09-09: pyscn 1.24.3 tolerates the unknown table (exit 0, architecture still 100% compliant), so one file serves both consumers.
10. **The DAG expresses what is LEGITIMATE, not what the code does today** (Arnon). Any layer may reach `foundation` whether or not it does so now. Edges are declared, not derived by closure.
11. **Reworking `architecture_fitness.py --layers` is in TOO-78**, not a follow-up. It is the one place in this ticket with real logic changes.
12. **Arnon performs the module moves in the JetBrains UI.** Measured 2026-09-09 against the freshly upgraded IDE: `execute_tool` enumerates 58 tools and `rename_refactoring` is the only refactoring among them -- there is no move-file or move-module tool over MCP. The IDE's Move refactoring updates imports and, with the option enabled, string and comment references, which removes most of the hand-edit risk.

## Target layout

```
toolguard/
  __init__.py            unchanged
  hook.py                stays flat   (runtime)
  session_start.py       stays flat   (runtime)
  subagent.py            stays flat   (runtime)

  foundation/            NEW  12 modules
  install/               NEW   3 modules
  observability/         NEW   7 modules
  config/                NEW  10 modules + __init__.py
  engine/                NEW   5 modules
  api/                   NEW   api.py + __init__.py

  parser/                UNTOUCHED  (engine layer)
  tools/                 UNTOUCHED  (tooling layer)
  scripts/               UNTOUCHED  (tooling layer)
  testing/               UNTOUCHED  (support layer)
```

## The moves, enumerated

**`foundation/` -- 12, all pure moves**: `_git.py`, `ambient.py`, `claude_code_contract.py`, `constants.py`, `file_lock.py`, `invocation.py`, `issues.py`, `normalization.py`, `path_utils.py`, `patterns.py`, `toml_scan.py`, `tool_spec.py`

**`install/` -- 3, all pure moves**: `install_provenance.py`, `install_update.py`, `update_check.py`

**`observability/` -- 7, all pure moves**: `auto_mode_trace.py`, `error_log.py`, `error_reporter.py`, `log_writer.py`, `once_per.py`, `once_per_store.py`, `session_warnings.py`

**`config/` -- 10 + `__init__.py`**: `auto_migrate.py`, `config_divergence.py`, `config_types.py`, `config_validation.py`, `config_write_guard.py`, `env_config.py`, `permission_migration.py`, `rule_entry.py`, `rule_sort.py` as pure moves, and `config.py` -> `config/loading.py` as the single rename. `__init__.py` re-exports `load_configuration`, `find_project_root`, `discover_config_files`, `load_config_file`, `wrap_tool_pattern`, `is_tool_wrapper`, `config_sync_settings_from_sources`, `Configuration`, `ConfigLayer`, `Provenance`, `Issue`.

**`engine/` -- 5, all pure moves**: `compound.py`, `file_matching.py`, `permission_resolution.py`, `permissions.py`, `resolve.py`

**`api/`**: `api.py` -> `api/api.py`, plus `__init__.py` re-exporting `decide`.

38 modules move. 3 stay flat. 4 packages untouched. 41 top-level modules accounted for.

## The declared DAG

```toml
[architecture.dag]
foundation    = []
install       = ["foundation"]
observability = ["foundation"]
config        = ["foundation", "observability"]
engine        = ["foundation", "observability", "config"]
api           = ["foundation", "observability", "config", "engine"]
runtime       = ["foundation", "observability", "config", "engine", "api", "install"]
tooling       = ["foundation", "observability", "config", "engine", "api", "runtime", "install"]
support       = ["foundation", "observability", "config", "engine", "api", "runtime", "tooling", "install"]
```

Same-layer imports remain legal. `install` is reachable only from `runtime`, `tooling` and `support`, which is the enforcement of decision 4.

**Verified importers of the install modules at `1cfd318`**, so the DAG's in-edges are grounded rather than assumed:

| module | production importers |
|---|---|
| `install_provenance` | `session_start.py` (runtime, the stale-install gate); `tools/environment_audit.py` (tooling) |
| `install_update` | `update_check.py` (moves into the same layer); `tools/installer.py` (tooling) |
| `update_check` | nothing -- console-script entry point only |

`session_start` -> `install_provenance` is the one genuine exception to "only install processes use these". It is legitimate: the stale-install gate is an install concern surfaced at startup. It is recorded here rather than assumed away.

## Punch list

1. Create the six new packages with `__init__.py` files -- `foundation/`, `install/`, `observability/`, `config/`, `engine/`, `api/`. Claude does this.
2. Arnon moves the 38 modules in the JetBrains UI, with reference and string/comment updating enabled. `config.py` is moved and renamed to `loading.py`; `api.py` is moved to `api/api.py`.
3. Write `config/__init__.py` and `api/__init__.py` re-exports.
4. Repoint every `mock.patch` target that names a moved module at its DEFINING module, never at the `__init__` re-export. Roughly 110 string literals; the `toolguard.hook.*` cluster (~181) and the `tools`/`testing`/`parser` clusters are unaffected because those modules do not move.
5. Update `.claude/rules/test-config-isolation.md`, which documents `patch("toolguard.config.…")` and `patch("toolguard.env_config.…")` targets in about ten places.
6. Add the `[architecture.dag]` table to `.pyscn.toml` and update `[[architecture.layers]]` to the new package names.
7. Rework `tools/architecture_fitness.py --layers`: read the DAG, validate it is acyclic (there is a Tarjan SCC implementation in the file to reuse, around line 523), check every import against the declared edges, and cross-check that `[[architecture.rules]]` allow/deny lists agree with the DAG.
8. Update `R6_GUARDED_LAYERS` / `R6_CHECKED_LAYERS` and the R1/R5 out-of-scope package constants for the new first segments.
9. Update `test/unit/test_architecture.py` and `test/unit/test_static_analysis_coverage.py`.
10. Run the full suite: `uv run python -m unittest discover -s test -t .`
11. Run all three fitness checks: `--stdlib`, `--ambient`, `--layers`.
12. Live hook smoke test, because a hook that cannot launch fails silently.
13. `uv run ruff format .` and `uv run ruff check .`
14. Update docs naming moved modules: `README.md`, `AGENTS.md`, `llms.txt`, `technical-notes.md`, `docs/agent-map.md`. Then `/documentation-review`.
15. Ask the what-vs-how question out loud for `config/__init__.py` and `api/__init__.py` -- both are re-export facades, which is exactly the thin-pass-through shape the pre-push checklist exists to catch. They are justified by import-site stability; that justification has to survive being said out loud.

## Open items

- Whether `pyproject.toml` needs any change: expected none. `[tool.hatch.build.targets.wheel] packages = ["toolguard"]` already covers subpackages, and no console-script target names a moved module.
- Whether the IDE's Move updates references inside `.md` files. If not, docs are hand-edited at step 14 anyway.

## Clarifications from discussion

- Arnon's framing of the architectural-fitness consequence, which corrected mine: the check does not get weaker when the directory becomes the declaration. Completeness losing its teeth is not a loss, because "you forgot to declare a module" stops being constructible rather than stopping being detected. And package boundaries make a class of check possible that is not expressible today.
- The DAG must express legitimacy, not current usage. Encoding the current import graph would make the declaration a description of the code, which is the thing that cannot fail.
## Status, 2026-09-09

**Done (punch-list 1, plus a transitional slice of 6):**

- Created `toolguard/foundation/`, `toolguard/install/`, `toolguard/observability/`, `toolguard/engine/`, each with a one-line layer docstring in `__init__.py`.
- NOT created: `toolguard/config/` and `toolguard/api/`. A package of either name would shadow the existing `config.py` / `api.py` module and break every import immediately. The IDE's Move dialog creates the destination package, so these come into being with their first move.
- `.pyscn.toml`: added the four new package names to their layers, added the `install` layer, and added `install` to the allow/deny lists. Transitional -- each layer's `packages` list currently holds BOTH the new package name and the old module names, and collapses to a single entry once the modules land.
- `docs/architecture-as-built.md` layer table and `test_every_layer_allow_list_is_pinned_against_a_silent_loosening` updated to match. Both are deliberate pins: the suite asserts `report.unmapped == []` against the real tree, so an unmapped package is a hard failure, and the allow-list pin makes a loosening a two-file change.
- Suite green: 4132 tests, `OK (expected failures=4)`. `--layers` exit 0, all modules mapped, no direction violations.

**Measured, so it does not have to be re-derived:**

- The live permission hook runs `/home/arnon/.local/bin/toolguard` with `PYTHONPATH` unset, so a transient broken working tree during the moves cannot disable it. The dogfood-shadowing hazard needs `PYTHONPATH` set and it is not set in this session.
- pyscn 1.24.3 tolerates an unknown `[architecture.dag]` table in `.pyscn.toml`: exit 0, architecture still 100% compliant.
- The upgraded JetBrains MCP exposes 58 tools and `rename_refactoring` is the only refactoring among them. No move-file or move-module tool. `projectPath` must be the WSL UNC form.

## Amendment: the DAG shape is deferred

Arnon, 2026-09-09: *"every edge should have, theoretically, a conceptual justification about why it should be there. We can start with this, but maybe we should analyze a bit deeper after the refactoring."*

So the DAG currently in `.pyscn.toml` is the **existing dependency relation re-expressed, not a justified design**. The refactoring preserves the actual dependencies exactly, so nothing about the final shape is foreclosed by landing it.

**Added to the punch list, at the end: justify every edge, or delete it.** This matters more than it looks. A declaration that merely describes the code cannot fail -- it is the failure mode `.claude/rules/evidence-before-fixing.md` names, where the map matched the code and a zero-violation report could not show that the layering was being routed around rather than obeyed. An edge nobody can justify survives forever precisely because nothing contradicts it.

## Protocol error: the informed estimate

**My error.** I created the packages while the informed estimate was still running. It then failed on an infrastructure condition (no record written), and the tree is no longer clean within `clean_scope`, so it cannot be re-sealed as things stand:

```
ESTIMATE BLOCKED. These are modified and are code or in scope:
  .pyscn.toml
  toolguard/{engine,foundation,install,observability}/__init__.py
```

The raw estimate is unaffected: sealed and validated at `1cfd318` before any of this, with `estimator.tree` recording only the two memory files as ignored-dirty.

Options put to Arnon, in the order recommended:

1. Stash, seal, pop -- restores the protocol exactly. The informed estimate then measures the same scope as the raw one, which is what makes the pair an instrument.
2. Commit the work so far, seal the informed estimate against the new commit, and record that it predicts a smaller scope than the raw estimate did.
3. Drop the informed stage for TOO-78 deliberately, keeping only the raw estimate, recorded as a decision rather than as missing data.

Awaiting his decision.

## The refactor landed, 2026-09-09

Final layout differs from the plan in four ways, all Arnon's calls: the config package is `configuration/` (avoiding the name collision outright, so `config.py` keeps its name and there is no re-export facade); `api.py` stays flat; `install/` gained `_git.py`; `once_per`/`once_per_store` moved to `foundation`; and `claude_code_contract` moved to a new `integration/` SINK layer.

**Four layer placements inherited from `.pyscn.toml` turned out to be wrong**, and Arnon found all four by inspection. I had treated the existing layer map as the specification because the ticket said "each package corresponds to one architecture layer" -- transcribing a map written before packages existed instead of pressure-testing it. The measurements that settled them:

| module | evidence |
|---|---|
| `_git` | production importers are `install.install_update` and `install.install_provenance` and nothing else -- `install`, not `foundation` |
| `once_per`, `once_per_store` | `once_per_store` imports only `ambient` + stdlib; `once_per` imports only `once_per_store`; neither touches observability -- primitives, not services |
| `claude_code_contract` | 8 importers across 5 layers INCLUDING `foundation`, so `integration` must be a sink below foundation. This is ticket 85's shape |
| `permission_migration` | its own docstring records that TOO-45 R5b put it in `config` deliberately; moving it to `tools` would re-create the violation R5b fixed |

**The IDE's Move refactoring is broken in 2026.2.2.** It moved files, updated NO references, rewrote some imports into bare `from install import x`, and mangled file-path strings inside historical notes and docs into broken relative paths. 18 files under `toolguard-memories/` plus two docs were reverted. Arnon is clearing caches and reindexing.

## Auto-migration moved off the hook path

**Defect, reproduced with a passing control**: `hook.py` called `run_auto_migration` with no stdout guard, and `permission_migration._run_migration` prints a human report with bare `print()`. On the hook path stdout carries the JSON decision, so a firing auto-migration produced prose-then-JSON. Claude Code cannot parse that, and per `docs/architecture-as-built.md` §1 an exit-0 hook it cannot parse reads as "no opinion" and falls through to native permission handling with nothing warning. Rare -- it needs `auto_migrate` enabled, something to migrate, and a free daily slot -- and silent.

**Arnon's judgement on the trade**, which settled the design: a delayed migration costs almost nothing, because the rules still take effect from Claude's own settings; they are merely not yet visible to someone reading the toolguard config, and they get migrated eventually.

Done under TDD from a green suite: 6 new tests in `test/unit/test_auto_migration_placement.py` went RED (4 of 6, with both controls passing), then green.

- `configuration/auto_migrate.run_auto_migration_for_config(project_root, config)` -- new. Owns the `auto_migrate` gate and the `TakeoverConfig` -> legacy-dict conversion, so nothing outside `configuration` needs to know that dict's shape.
- `hook._run_divergence_check` still warns, never migrates.
- `session_start` calls it through `_run_checker`, so a failure there cannot take the session-start hook down.
- The once-a-day throttle is untouched -- it lives in `run_auto_migration`, so it travelled with the call.

Relocated tests: `TestAutoMigrationGate` (hook_eval) became `TestTheDivergenceCheckNeverMigrates`, with the gate itself now tested in `test_auto_migrate.TestRunAutoMigrationForConfig`; the two once-per-day claim tests in `test_logging_streams` now drive `run_auto_migration_for_config`. The `--eval` read-only assertions now patch the real `auto_migrate.run_auto_migration` rather than a hook-local alias, which is a stronger claim than before.

**Note for review**: the two `test_logging_streams` claim tests now measure nearly the same thing. Their separation existed because the divergence_warning claim and the auto_migration claim masked each other on the hook path; that masking is gone by construction. Worth deciding whether to merge them -- I did not delete coverage unilaterally.

## Verification at this point

- Suite: **4141 tests, OK** (4 expected failures).
- `--stdlib`, `--ambient`, `--layers`: all exit 0. 87 modules mapped, **zero direction violations**.
- `ruff format` + `ruff check`: clean.
- Live hook smoke test matches the installed 0.7.0 build's decision exactly on the same event.
- The original probe now reports NOT REPRODUCED.

## Still open

1. **Justify every DAG edge, or delete it.** The declared DAG is still the existing relation re-expressed.
2. **Rework `--layers`**: read the DAG, validate acyclicity (Tarjan SCC already in the file), cross-check `[[architecture.rules]]` equals it. Strict TDD from green.
3. **Revisit `permission_migration`'s home.** Moving auto-migration off the hook removed `configuration`'s only runtime caller, so `tools` may now be legal after all -- the opposite conclusion from the one the R5b docstring forced earlier today.
4. Split the migration workflow's report rendering from its logic (the `_print_*` functions), per "prose is output, not a data structure".
5. Docs: `README.md`, `AGENTS.md`, `llms.txt`, `technical-notes.md`, `docs/agent-map.md`, then `/documentation-review`.
6. `git mv` was not used, so 5 paths show as untracked adds rather than renames.

## Two findings from the dependency-graph review, 2026-09-09

### Cross-module private imports: 9 in production, unchecked

Arnon, on seeing `config_types` import `_strip_tool_wrapper`: *"we do have direct imports of underbar functions. That's not legit. Either those imports should not exist or those should not be underbar."*

| site | reaches |
|---|---|
| `configuration/rule_sort.py:36` | `foundation.toml_scan._locate_subsection` (crosses a package) |
| `engine/compound.py:34` | `parser.command_extractor._detect_foreign_inline_code` (crosses a package) |
| `configuration/config_types.py:15` | `configuration.rule_entry._strip_tool_wrapper` |
| `engine/resolve.py:21` | `engine.compound._combine_strictest` |
| `install/update_check.py:12` | `install.install_update._check` |
| `parser/multiline.py:63` | `parser.command_extractor._LiftedHeredocs`, `_UnattributableHeredocError`, `_attribute_and_substitute` |
| `tools/hierarchy.py:30` | `tools.redundancy._normalised_body` |

All nine are called by non-test code, so by the standing visibility criterion -- "should non-test code call it?" -- each resolves by making the name public, unless the dependency itself is the smell.

**Nothing checks this.** `architecture_fitness.scan_private_reaches` covers only tooling/runtime reaching into configuration/engine, so the other seven routes are invisible. A general "no cross-module private import in production" check is **strong** by the evidence-before-fixing taxonomy: binary, total, no threshold, and it checks a declaration a human made (the underscore) rather than supplying a judgement of its own.

### `config_types` is a mixed bag, and the cut runs through it

Measured: `engine/` and `parser/` import from `configuration/` **ten times, every one of them `config_types`** -- nothing else. Their complete set of outward imports is `configuration.config_types` (10), `foundation.*` (11), `integration.claude_code_contract` (1). No observability, no install, no api, no runtime.

`config_types` defines 21 public names. `engine` uses 13, `parser` 1, and the 8 nobody below touches are exactly the config-structure ones:

- **decision vocabulary (used)**: `RuntimeVerdict`, `UnitVerdict`, `LevelMatch`, `CommandSpellings`, `ResolutionContext`, `ResolveContext`, `FilePathResolutionContext`, `PathAnchoring`, `ConflictOverride`, `ToolPatternLayer`, `AUTO_PERMISSION_MODE`, `entry_for_pattern`, `provenance_for_pattern`
- **config structure (unused below)**: `ConfigLayer`, `Provenance`, `TakeoverConfig`, `TakeoverEnabledConflict`, `UnrecognizedFallbackSetting`, `ResolutionConfig`, `ResolveConfig`, `FilePathResolutionConfig`

`rule_entry` comes along rather than staying: `ToolPatternLayer` and `entry_for_pattern`, both engine-used, are typed on `RuleEntry`. So the rule model IS decision vocabulary. Fixing the `_strip_tool_wrapper` private import does NOT sever the dependency -- `RuleEntry` is used throughout `config_types`.

**If the decision half plus `rule_entry` moved to a low package**, `engine -> configuration` and `parser -> configuration` disappear entirely, and the DAG becomes:

```toml
[architecture.dag]   # transitive; minimal edges only
integration   = []
foundation    = ["integration"]
model         = ["foundation"]
install       = ["foundation"]
observability = ["foundation"]
configuration = ["model", "observability"]
engine        = ["model"]
api           = ["engine", "configuration"]
runtime       = ["api", "install"]
tooling       = ["runtime"]
support       = ["tooling"]
```

`engine` then has **no path to `configuration` at all**, which is the property Arnon was reaching for: a future `from toolguard.configuration.config import load_configuration` inside `engine/` becomes a hard failure instead of a legal import nobody notices.

Not started. Arnon's call, and larger than the remaining TOO-78 scope.

## Scope extension, approved and landed 2026-09-09

Arnon: *"All these sound like good improvements to do right now. We'll end up with better, more resilient code. Well worth the scope creep."*

### A. Cross-module private imports -- all nine resolved

New `--privates` mode in `architecture_fitness.py`, written test-first and RED at 9. Eight names made public; the ninth was not a rename at all -- `config_types` was importing `rule_entry._strip_tool_wrapper` when a public `strip_tool_wrapper` delegate already existed two lines below it, so it was simply calling the wrong one.

The check is **total over the package**, unlike `scan_private_reaches`, which only asks R6's narrower tooling/runtime-into-guarded question. It compares against a declaration a human made -- the underscore -- rather than supplying a judgement of its own, which is what makes it strong rather than a heuristic.

`_check` needed file-scoped treatment: `testing/sandbox.py` has an unrelated `_Tripwire._check` method, so a word-bounded global rename would have caught it.

### B. `--layers` reworked around a transitive DAG

Arnon's simplification: treat edges as transitive and declare only the minimal set. Verified the reduction preserves the relation exactly before adopting it.

- `[architecture.dag]` is now **nine edges** rather than ~40.
- `--layers` validates **acyclicity** (the hard gate), computes the **closure**, and **cross-checks** that `[[architecture.rules]]` -- the expanded form pyscn reads -- equals closure-plus-self. The cross-check earned itself immediately: when `model` landed it named all seven stale rules precisely, including `engine: extra configuration, observability`.
- The closure is **printed**, because transitivity's cost is that one new edge grants everything below its target at once. `configuration = ["runtime"]` would hand configuration `install` and `api` in the same stroke.
- The allow-list pin now pins the **DAG** rather than the expanded lists: with the cross-check enforcing agreement, the DAG is both the smaller literal and the one that matters.

### C. The `model` package

Computed the split rather than guessing: starting from the 13 names engine/parser import and closing over references inside `config_types`, **18 of 22 names move and 4 stay, with no blockers**. `Provenance` and the three `*Config` protocols get pulled in, which is right -- they describe what the engine needs.

- `toolguard/model/` = `rule_entry.py` + `decision_types.py`.
- `configuration/config_types.py` keeps four genuinely structural types: `ConfigLayer`, `TakeoverConfig`, `TakeoverEnabledConflict`, `UnrecognizedFallbackSetting`.
- **`engine` and `parser` now import nothing from `configuration`.** Enforced twice: `test_engine_and_parser_import_nothing_from_configuration`, and the DAG giving `engine` no path to `configuration`.
- `model` joined `R6_GUARDED_LAYERS`. Moving `rule_entry` out of `configuration` would otherwise have silently dropped it from R6's guarded set -- caught by two existing fixtures failing, which is the check doing its job.
- `RE_EXPORTED_TYPES` became a name-to-defining-module map, since the re-exports now come from two modules.

### D. Docs

47 stale module paths rewritten across `technical-notes.md` and `docs/architecture-as-built.md` -- these had been reverted to HEAD after the IDE mangled them, so they still described the pre-TOO-78 flat layout. Section 6's prose rewritten for eleven layers, the transitive DAG, and the engine/configuration seal. The stale layer-chain comment in `.pyscn.toml` replaced.

`/documentation-review` still to run.

## Verification at the end of the extension

- Suite: **4156 tests, OK** (4 expected failures).
- `--stdlib`, `--ambient`, `--layers`, `--privates`: all exit 0.
- `ruff format` + `ruff check`: clean.
- Live hook matches the installed 0.7.0 build's decision exactly.
- **Zero import cycles** at module level: whole package, from the hooks, and within `tools/`.

## Still open

1. `/documentation-review`, per the pre-push checklist.
2. `tools/` is still an unlayered pile -- deliberately deferred. `toolguard-memories/TOO-78/dependency-graphs.md` has its latent structure; `sorters` has no intra-`tools` edges at all.
3. `permission_migration`'s home. Moving auto-migration off the hook removed `configuration`'s only runtime caller, so `tools` may now be legal -- the opposite of what the R5b docstring forced earlier. Not re-measured since.
4. `docs/architecture-as-built.md` still says "As of 2026-09-07 -- toolguard 0.7.0" and "all 77 modules"; the tree now has 89. The date/version line is advanced by the pre-push checklist.
5. `git mv` was not used anywhere, so moved files show as delete+add rather than renames.

## Rename and diagram, 2026-09-10

`model/` -> **`decision_model/`**, `decision_types.py` -> **`vocabulary.py`** (Arnon: "model" is too generic to explain intuitively). Call sites read `from toolguard.decision_model.vocabulary import RuntimeVerdict`.

**Two things the rename surfaced**, both the same shape -- a check or a rewrite driven by one syntactic form missing the others:

- `test_the_documented_layer_table_matches_the_architecture_config` matched layer names with `[a-z]+`, so `decision_model` was **skipped rather than failed**. That check exists because the table silently went stale twice before; an underscore in a name would have reopened the hole. Widened to `[a-z_]+`.
- The dotted-path rewrite missed `from toolguard.model import decision_types as X`. Same class as the parenthesized-import miss earlier in the ticket.

**Semantic check of the split, done after the fact** (Arnon asked whether all semantically-decision types moved, not just the currently-used ones). They did. The four staying types are consumed only by `configuration`, `hook.py`, `session_start.py` and `tools` -- never below. The interesting one is `TakeoverConfig`: the engine does care about `no_match_fallback`, but receives it as a plain string through `ResolutionConfig.resolved_no_match_fallback()`, the protocol, which moved. So the seam is **protocol in the decision model, implementation-side config type in configuration** -- a better justification than "not used below", and the one worth stating. Recorded because I reached it by accident: the split was driven by usage plus reference closure, not by asking what each type IS.

**Diagram**: the hooks graph now groups `decision_model/`, `engine/` and `parser/` in a "decision machinery" box, and pins layer order with invisible `~~~` links. Both are drawing decisions only -- the layer map knows nothing about the box, and `configuration -> decision_model` is still a real, drawn edge. `parser/` is inside the box because it is engine-layer; dropping it is a one-line change to `CLUSTERS`.

**The analysis scripts are preserved** in `toolguard-memories/TOO-78/scripts/` because the session scratchpad does not survive a restart:

| script | what it answers |
|---|---|
| `import_graph.py` | the two Mermaid views, cycle detection, transitive reduction |
| `classify_changes.py` | which changed files carry real edits versus move/rename churn |
| `private_imports.py` | cross-module private imports (superseded by `--privates`, kept as the independent instrument) |
| `config_types_surface.py` | what config_types contained versus what engine/parser used |
| `split_config_types.py` | the AST extraction that performed the split |

`import_graph.py` is worth promoting to the repo's `tools/` if the graphs are wanted again -- not done unilaterally.

## State at the session restart, 2026-09-10

Suite **4156 OK**, ruff clean, `--stdlib`/`--ambient`/`--layers`/`--privates` all exit 0, hook decision matches the installed 0.7.0 build, zero import cycles. Nothing is half-applied.

Open, in order:

1. `/documentation-review` (pre-push checklist).
2. `tools/` is still unlayered -- deliberately deferred.
3. `permission_migration`'s home: moving auto-migration off the hook removed `configuration`'s only runtime caller, so `tools` may now be legal. Not re-measured.
4. `docs/architecture-as-built.md` still says "As of 2026-09-07 -- toolguard 0.7.0" and "all 77 modules"; the tree has 89.
5. Nothing used `git mv`, so moved files are delete+add unless staged with rename detection (they are staged, and `git diff --cached -M` pairs them).
6. Arnon's code review has not happened yet.

## Code review, 2026-09-10 -- passed

Arnon: `architecture_fitness.py` is "complex and long, but it's really not part of toolguard proper. It's a development helper script and I wouldn't spend time optimising it just for the sake of it." Everything else: "nice simple changes. No real comments."

### The one architecture surprise, and what surfaced it

Arnon: *"There was only one small architecture surprise, which was the new package and the split we discovered -- and I attribute this to the visual nature of good diagrams. That is what made it jump for me."*

**This is evidence for the surprise-factor experiment, and of the kind it exists to find** -- see [[project_surprise_factor_purpose]]: the objective is tail-driven review yield, not predictor accuracy. The finding was that `engine` and `parser` touched `configuration` at exactly one point, which nothing in the ticket, the plan, or either estimate anticipated. It was cheap to act on and it improved the architecture.

What actually surfaced it is worth being precise about, because the credit is easy to misassign:

- The **diagram** made it jump out. Arnon saw `config_types` sitting alone with one thin connection and asked about it.
- The **measurement** confirmed it: 10 imports from `engine`/`parser` into `configuration`, every one of them `config_types`.
- **Neither the layer map nor any fitness check would have raised it**, because `engine -> configuration` was a legal edge. Nothing was broken; the structure was merely looser than it needed to be.

So the mechanism is: a visual artifact surfaced a question that no rule could have asked, and measurement then answered it. That is an argument for putting diagrams in front of a human early, not for building another checker.

The cost split is also worth recording honestly: the refactor itself was cheap, and nearly all the elapsed time went into tuning the diagramming approach -- which is now a reusable `diagramming` skill rather than sunk cost.

## Prediction record: raw only

Only `raw-estimate.json` exists. The informed estimate was prepared (its sandbox and inputs are archived under `inputs/informed`) but the run failed on an infrastructure error, and by the time that was noticed the tree already carried the first package stubs, so it could no longer be sealed against a clean tree. The three options put to Arnon -- stash/seal/pop, commit-then-seal, or drop the stage deliberately -- were never resolved, and work continued.

**So scoring this ticket has the raw estimate and no informed one.** That is a gap in the 2x2, and it is mine: I began implementing while the informed estimate was still in flight.
