---
title: TOO-45 ruff configuration proposal
type: note
permalink: toolguard/too-45/too-45-ruff-configuration-proposal
tags:
- task-memory
- TOO-45
- ruff
- architecture
---

Investigation and proposal, 2026-08-05. No repository file was modified: every measurement below was taken with a throwaway config under the session scratchpad and `uv run ruff check --config <scratchpad>/x.toml`, never `--fix`. Companion notes: [[TOO-45 ideal picture]], [[TOO-45 delta - as-is against ideal]], [[TOO-45 architecture overhaul execution plan]].

**The tree was being edited by another agent while this ran.** Two consecutive `--no-cache` baseline runs seconds apart disagreed (an `F821 Undefined name ShadowStatus` in `session_start.py` appeared, vanished, and reappeared). Every count here is a moving snapshot; the commands are given so any of them can be re-run. Also note ruff caches aggressively — `uv run ruff check .` reported clean from cache while the live tree had an error, so use `--no-cache` when the number matters.

## Recommendation in one paragraph

Four rules, all additive to the stock defaults, plus two prepared blocks that get pasted when R5 and R6 land. The four are **PLC0415** (the no-local-imports convention, which the repo already enforces by hand in `test_architecture.py` and already marks with `# noqa: PLC0415` for a rule ruff was not running), **TID251 banned-api on `threading`/`asyncio`/`concurrent.futures`/`multiprocessing`** (a true zero-hit ratchet on a stated hard prohibition), **PLR0913 with `max-args = 8`** (which lands on `log_writer.log_command`'s twelve parameters — R1's named target — and turns the prose NOTE already sitting above that signature into something a machine checks), and **RUF100** (which is what would have caught the `# noqa: PLC0415` markers pointing at an unenabled rule). The two prepared blocks are TID251 module bans that encode R5's "runtime and scripts are leaves" and R6's "tooling consumes only the api" — both are DEBT-REVEALING today (11 and 20 sites) and become clean ratchets exactly when their step closes, which makes them the right way to prevent those steps from silently regressing.

Everything else measured was rejected, and the two most interesting rejections are **PLC2701**, which is structurally incapable of seeing the violation R6 already knows about (section "The instrument disagreement", below — this is the load-bearing part), and the **pydocstyle `D` family**, which enforces docstring presence and format and has no rule at all for the thing Arnon actually wants, which is restraint.

## The proposed configuration

Ready to paste into `pyproject.toml`. Verified against the live tree: with this config the whole repo reports **3 findings** (plus whatever the other agent is mid-edit on), all three of them intentional and listed under "What lands with it".

```toml
[tool.ruff.lint]
# Stock defaults (E4, E7, E9, F) stay on. Everything here is additive.
extend-select = [
    # ~/.claude/rules/python.md bans function-level imports outside a documented
    # circular-import escape. The convention already exists, already uses
    # "# noqa: PLC0415" as its marker, and was enforced by a hand-rolled AST
    # walker in test/unit/test_architecture.py because the rule was never enabled.
    "PLC0415",
    # Bans specific modules by name. Used here for the stated concurrency
    # prohibition; see [tool.ruff.lint.flake8-tidy-imports.banned-api] below.
    # This is also the mechanism that will lock in R5 and R6 -- see the
    # prepared blocks in the TOO-45 ruff proposal note.
    "TID251",
    # TOO-45 R1. log_writer.log_command takes 12 parameters and carries a prose
    # comment asking that no more be added. A comment cannot enforce that.
    "PLR0913",
    # Keeps the noqa markers honest: a "# noqa: XXX" for a rule that is not
    # enabled is a convention that silently does nothing, which is exactly how
    # the PLC0415 markers ended up decorative.
    "RUF100",
]

# BLE001 is deliberately not selected, but two sites carry an explanatory
# "# noqa: BLE001 - ..." comment worth keeping. Listing it here stops RUF100
# from demanding their deletion. (Verified: `external` suppresses RUF100 for
# codes ruff knows but does not have selected.)
external = ["BLE001"]

[tool.ruff.lint.pylint]
# 8, not the default 5. The default fires 21 times and mostly on ordinary
# 6-argument helpers; 8 fires 4 times and one of them is R1's actual target.
# Tighten toward 5 after R1, not before.
max-args = 8

[tool.ruff.lint.flake8-tidy-imports.banned-api]
# ~/.claude/rules/python.md: async/await and threading are prohibited without
# explicit approval. Zero hits repo-wide today -- a free ratchet.
"threading".msg = "threading is prohibited (~/.claude/rules/python.md); ask before introducing concurrency"
"asyncio".msg = "async/await is prohibited (~/.claude/rules/python.md); ask before introducing concurrency"
"concurrent.futures".msg = "concurrency is prohibited (~/.claude/rules/python.md)"
"multiprocessing".msg = "concurrency is prohibited (~/.claude/rules/python.md)"

[tool.ruff.lint.per-file-ignores]
# Tests use function-level imports for import-time isolation and for keeping a
# fixture's dependencies next to it. 139 sites, none of them a production
# concern. test/unit/test_architecture.py's own detector scans production code
# only, for the same reason.
"test/**" = ["PLC0415"]

# TOO-45 R1 baseline. This is the debt list, not an exemption policy: R1 is done
# when the log_writer.py line is deleted from it. The other three are unrelated
# wide signatures, recorded so the rule can be green today.
"toolguard/log_writer.py" = ["PLR0913"]                  # log_command, 12 params -- R1's target
"toolguard/hook.py" = ["PLR0913"]                        # 9 params
"toolguard/scripts/migrate_permissions.py" = ["PLR0913"] # 9 params
"toolguard/tools/consolidate.py" = ["PLR0913"]           # 9 params
```

`ruff format` is untouched by all of this — `ruff format --check` under the proposed config still reports 148 files already formatted. Nothing above sets a docstring convention, a line length, or a quote style, which is where format fights normally start.

### What lands with it

Three things need doing at the same time as the paste, and all three are one-line edits the project's own conventions already prescribe:

1. `toolguard/auto_migrate.py:172` and `toolguard/hook.py:697` get `# noqa: PLC0415`. Both are function-level imports of the documented circular-import kind — `hook.py:697` already carries a three-line prose comment saying exactly that, and `test_architecture.py` already grandfathers both by name. The noqa is the marker the project chose; it was just never load-bearing.
2. `test/unit/test_architecture_fitness.py:30` has a genuinely stale `# noqa: E402` (RUF100 says *unused*, not *non-enabled* — E402 is on and the directive matches nothing). Delete it.
3. `test/unit/test_architecture.py::test_production_code_adds_no_undocumented_local_imports` and its `_local_imports` helper (~60 lines of AST walking, plus `GRANDFATHERED_LOCAL_IMPORTS`) become redundant and should be retired. Ruff does the same walk natively, respects the same noqa marker, and does not need a grandfather set once the two sites are marked. Worth noting the grandfather set has three entries and one of them (`log_writer.py` importing `json` locally) no longer exists — the hand-rolled version had already drifted.

### Prepared block: paste when R5 closes

R5's predicate is "no runtime or scripts module appears as a non-leaf". TID251 encodes that directly, and encoding it is what stops it from re-rotting. Measured today: **11 non-test violation sites**, which is the same set `architecture_fitness --predicates` reports for R5 (`config_divergence -> error_log`, `tools.decision -> hook`, `tools.installer -> {update_check, migrate_permissions}`, `tools.rule_apply -> migrate_permissions`, `tools.transcript_harvest -> subagent`, `auto_migrate -> migrate_permissions`, plus `hook`'s own four).

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"toolguard.hook".msg = "runtime entry point; must stay a leaf (TOO-45 R5)"
"toolguard.log_writer".msg = "runtime; must stay a leaf (TOO-45 R5)"
"toolguard.session_warnings".msg = "runtime; must stay a leaf (TOO-45 R5)"
"toolguard.error_log".msg = "runtime; must stay a leaf (TOO-45 R5)"
"toolguard.subagent".msg = "runtime; must stay a leaf (TOO-45 R5)"
"toolguard.update_check".msg = "runtime; must stay a leaf (TOO-45 R5)"
"toolguard.scripts.migrate_permissions".msg = "script; must stay a leaf (TOO-45 R5)"

[tool.ruff.lint.per-file-ignores]
"toolguard/hook.py" = ["TID251"]   # hook sits above runtime and composes it
```

### Prepared block: paste when R6 closes

R6's replacement predicate from the delta note is "no `tools/` or `scripts/` module imports from `config`, `permissions`, `compound` or `resolve` at all — only from the declared `api` module". That is exactly a TID251 ban with an exemption list, and it is checkable by ruff today. Measured now: **20 modules under `toolguard/tools/` and `toolguard/scripts/`**, plus 10 under `toolguard/` itself, which matches the delta's "21 of 33" within tree drift.

```toml
[tool.ruff.lint.flake8-tidy-imports.banned-api]
"toolguard.config".msg = "engine internals; consume toolguard.api (TOO-45 R6)"
"toolguard.permissions".msg = "engine internals; consume toolguard.api (TOO-45 R6)"
"toolguard.compound".msg = "engine internals; consume toolguard.api (TOO-45 R6)"
"toolguard.resolve".msg = "engine internals; consume toolguard.api (TOO-45 R6)"

[tool.ruff.lint.per-file-ignores]
# Only the engine itself and the api surface may reach these.
"toolguard/api.py" = ["TID251"]
"toolguard/config.py" = ["TID251"]
"toolguard/permissions.py" = ["TID251"]
"toolguard/compound.py" = ["TID251"]
"toolguard/resolve.py" = ["TID251"]
"test/**" = ["TID251"]
```

Two properties of this worth knowing before relying on it. **It catches relative imports too** — verified by construction: with `pkg.config` banned, `from .config import PUBLIC` inside `pkg/` is flagged with the resolved absolute name. And **it catches attribute access, not just the import** — `import pkg.config` plus `pkg.config.PUBLIC` produces two findings. So it cannot be evaded by import style, which is more than the private-name predicate can say.

The limitation, stated plainly: **`per-file-ignores` disables the whole rule for a file, and every ban shares the code TID251.** A file exempted so it may import `config` is thereby also exempted from importing `resolve`. That is harmless here because the exemption set for the R6 bans is the same set for all four modules, and likewise for R5. It is precisely why ruff cannot express the general layer map — see "What this cannot do".

## The instrument disagreement: R6 says one violation, PLC2701 says zero

This mattered enough to settle by construction rather than by reading docs, because a lint rule that reports clean on a violation the ticket already knows about is worse than no rule.

**What the R6 predicate does.** `tools/architecture_fitness.py:find_private_imports` walks every file whose first path segment under `toolguard/` is `tools` or `scripts`, resolves each `ImportFrom` (handling relative levels), keeps those targeting `{config, permissions, compound, resolve}`, and reports any imported alias starting with a single underscore. Live result: one site, `toolguard/tools/takeover_audit.py:87`, `from toolguard.config import (Configuration, Provenance, TakeoverConfig, _strip_tool_wrapper)`.

**What PLC2701 does.** Its own message gives it away: *"Private name import `_x` from **external module** `y`"*. It only fires when the imported module lies outside the importing file's own package, where "package" is found by walking up while `__init__.py` exists.

**Verified by construction**, in a synthetic tree under the scratchpad mirroring this repo's shape — `pkg/{__init__,config}.py` defining `_SECRET`, `pkg/tools/audit.py` and `pkg/sibling.py` and `test/unit/test_a.py` all containing the identical `from pkg.config import _SECRET`:

```
test/unit/test_a.py:1:24: PLC2701 Private name import `_SECRET` from external module `pkg.config`
Found 1 error.
```

`pkg/tools/audit.py` and `pkg/sibling.py`: silent. The importer's package is what decides. And directly on the real file: `uv run ruff check --preview --select PLC2701 toolguard/tools/takeover_audit.py` → `All checks passed!`.

**So the two instruments are not measuring the same boundary.** The R6 predicate measures a *module* boundary inside one distribution. PLC2701 measures a *distribution/package* boundary. Every module under `toolguard/` is internal to `toolguard`, so PLC2701 is structurally incapable of ever seeing an R6 violation — not tuned wrong, incapable.

**Which leaves PLC2701 pointing at exactly the wrong 69 lines.** Its only live surface in this repo is code outside the `toolguard` package: `test/` (69 hits) and the top-level `tools/` (0 hits — those modules import nothing from `toolguard` at all; `architecture_fitness.py` and `corpus_build.py` are stdlib-only AST tools). The project's API-visibility criterion is *"should non-test code call it? If not, privatize — but tests importing privates is fine."* PLC2701 fires only on the sanctioned half. Configure it correctly per that criterion — `"test/**" = ["PLC2701"]` — and it reports **zero across the repo, permanently, by construction**. Verified. That is the "green lint run mistaken for architectural health" failure mode in its purest form, so PLC2701 is rejected outright.

**The near-miss worth recording: SLF001 gets half of it.** SLF001 *does* cross package boundaries and *does* flag module-level private attribute access — verified by construction that `pkg.config._SECRET` and `from pkg import config as cfg; cfg._SECRET` are both flagged from inside `pkg/`. It misses `takeover_audit.py:87` only because that violation uses the `from ... import _name` form, which binds the name locally and leaves no attribute access to see. So SLF001 covers the attribute half of R6's criterion and nothing in ruff covers the import half.

**Verdict: `architecture_fitness.py`'s predicate is measuring the thing R6 cares about; keep it, and add no private-name lint rule.** The ratchet that genuinely serves R6 is the TID251 block above, which sidesteps the whole public/private question by banning the module wholesale — a strictly stronger statement, and the one the delta note already proposed in prose.

## Measurements

Snapshot 2026-08-05 on branch `too-45`, tree actively changing. Re-run any row with `uv run ruff check --no-cache --select <RULE> --output-format concise .` (add `--preview` where marked). Areas: `toolguard/` is the shipped package including `toolguard/tools/`, `toolguard/scripts/`, `toolguard/testing/`, `toolguard/parser/`; `tools/` is the top-level dev-only directory.

| rule | toolguard/ | tools/ | test/ | class | note |
|---|---:|---:|---:|---|---|
| TID251 concurrency bans | 0 | 0 | 0 | **RATCHET** | enforces a stated hard prohibition at zero cost |
| PLC0415 | 2 | 0 | 139 | **RATCHET** (package) / ignore in test | the 2 are the documented circular-import escapes, already grandfathered by name in `test_architecture.py` |
| PLR0913 `max-args=8` | 4 | 0 | 0 | **DEBT-REVEALING** | one of the four is `log_command` (12), R1's named target |
| PLR0913 default (5) | 15 | 1 | 5 | DEBT-REVEALING | too blunt: mostly ordinary 6-arg helpers, would bury the signal |
| RUF100 (with defaults on) | 4 | 0 | 1 | **DEBT-REVEALING**, ~1 residual | 2 of the 4 are the decorative `# noqa: PLC0415` markers; drops to 1 once PLC0415 is on and `external = ["BLE001"]` is set |
| TID251 R5-shaped bans | 11 non-test sites | 0 | 45 | DEBT-REVEALING, **ratchet after R5** | reproduces `--predicates` R5 output |
| TID251 R6-shaped bans | 20 under tools+scripts, 10 elsewhere | 0 | 60 | DEBT-REVEALING, **ratchet after R6** | matches the delta's "21 of 33" within drift |
| PLC2701 (preview) | 0 | 0 | 69 | **REJECT** | cannot see intra-package violations; see the reconciliation |
| SLF001 | 3 | 0 | 103 | **REJECT for now** | the 3 are `testing/sandbox.py` poking a config cache and its own classmethod — deliberate, and `testing/` is the support layer |
| TID252 `ban-relative-imports="all"` | 6 | 0 | 0 | REJECT | see rejected list |
| TID252 default (`"parents"`) | 0 | 0 | 0 | REJECT | zero hits, and nothing to prevent |
| D (pydocstyle, all) | 1,399 | — | — (11,010 repo-wide) | **REJECT** | see rejected list |
| C901 (>10) | 66 (53 in the generated `bash_parser.py`) | 7 | 2 | REJECT | |
| PLR0912 (>12) | ~62 | some | few | REJECT | |
| PLR0915 (>50) | ~40 | some | few | REJECT | |
| ERA001 | 2 | 0 | 8 | REJECT | |
| RUF022 (preview) | 3 | 0 | 0 | REJECT | |
| BLE001 | 20 | — | — | REJECT | measured only to price the `external` decision |

## Considered and rejected

**PLC2701 (import-private-name).** Rejected on the reconciliation above: it measures a package boundary, not a module boundary, so it is silent on the one production violation R6 knows about and fires only on the 69 test imports the project explicitly sanctions. Configured per the project's own visibility criterion it reports zero forever.

**SLF001 (private-member-access).** Rejected *for now*, not on principle. Only 3 non-test hits and all three are in `toolguard/testing/sandbox.py`, which exists to reach into internals (`toolguard_config._parse_config_file_cached.cache_clear()` — clearing a cache the sandbox must invalidate, plus two calls to its own `Sandbox._invalidate_config_cache` classmethod, which is arguably a false positive since it is same-class access via the class name). Enabling it means `"test/**" = ["SLF001"]` and either three noqas or a `toolguard/testing/**` exemption, in exchange for guarding a boundary the `from ... import _x` form walks straight past anyway. Worth reconsidering after R6, when a real `api` module makes "reached around the surface" mean something specific.

**The pydocstyle `D` family.** Rejected, and it would actively hurt. 11,010 findings, of which **D212 + D205 + D415 + D400 + D413 account for 10,744 (97.6%)** — all pure format of docstrings that already exist: summary line placement, blank line after summary, trailing period, section punctuation. Missing-docstring rules (D100–D107) total about 150. So the family would generate 3,965 autofixes' worth of churn to standardise punctuation, and **not one `D` rule measures verbosity, redundancy, or restatement**, which is the only docstring problem this repo has. Enabling `D` would produce a large green-to-red-to-green event that says nothing about whether docstrings got terser, and would create the impression that docstring quality is under lint control when the actual concern is untouched. If docstring bloat needs an instrument, it is a metric not a lint: a docstring-lines-to-executable-lines ratio per module, reported by `architecture_fitness --metrics`, which already excludes generated files and already has the AST pass. A ratio trending down across TOO-45 is evidence; `D400` compliance is not.

**C901 / PLR0912 / PLR0915 (complexity, branches, statements).** Rejected. Three reasons, in order of weight. First, they do not point at R1: R1 is about *parameter count and type multiplicity* (twelve loose arguments, seven verdict-ish types), and these three measure function *body* size, which R1 does not change. PLR0913 is the rule aimed at R1's actual shape. Second, 53 of the 88 C901 hits are inside `toolguard/parser/bash_parser.py`, which is canopy-generated, explicitly out of scope, and already excluded by `architecture_fitness`'s generated-file detector — ruff would need its own exclusion to say anything, and the ~40 remaining are ordinary large functions (`config.validation_issues` at 28, `toml_scan._scan_array_char` at 23). Third, this ground is covered: `pyscn analyze` reports complexity in the pre-push checklist and the `reduce-complexity` skill exists for it. Adding a fourth complexity opinion is tool collecting.

**TID252 (relative imports).** Rejected. Default setting is already clean; `"all"` finds 6 relative imports in 2 files (`patterns.py`, `permissions.py`). The one argument that would have made it load-bearing — that the R5/R6 TID251 bans might be evaded by writing `from .config import x` — was tested and is false: TID251 resolves relative imports and flags them under the absolute name. That leaves a purely stylistic 6-line change, and `architecture_fitness.resolve_toolguard_import` already handles `node.level` correctly. No objective, no rule.

**RUF022 (`__all__` not sorted).** Rejected. 3 auto-fixable hits, and sorting `__all__` serves no TOO-45 objective. `F822` (undefined name in `__all__`) is the one that catches a real defect and is already on by default.

**ERA001 (commented-out code).** Rejected. 10 hits, no mapped objective, and it is a heuristic with a known appetite for structured comments.

**BLE001 (blind except).** Rejected as a rule (20 hits, and several are deliberate — `session_start` and the hook must never raise), but named in `external` so RUF100 does not demand the deletion of two explanatory noqa comments.

**Bandit (`S`), annotations (`ANN`), magic values (`PLR2004`), booleans (`FBT`), `TC` type-checking blocks.** Rejected without full measurement. `TC` deserves a specific mention because it would *contradict* a stated convention: `~/.claude/rules/python.md` says no `TYPE_CHECKING` guard without a real circular import, and the `TC` family exists to push imports into exactly such guards. The others have no mapping to a TOO-45 objective or a project convention.

## What this cannot do

**The stdlib-only runtime constraint — ruff has no mechanism, and the near-miss is a trap.** TID251 is a denylist. Enforcing "imports nothing outside the standard library" needs an allowlist, and ruff has no `allowed-imports` setting. Banning today's dev dependencies (`ruff`, `flake8`, `isort`, `code-review-graph`) would be a denylist standing in for a security property, which fails in the worst direction: a dependency added tomorrow is permitted by default until someone remembers to ban it, and the lint stays green through the regression. **What could do it:** roughly fifteen lines over the AST import graph `architecture_fitness` already builds — collect the top-level root of every import in the shipped tree and assert it is in `sys.stdlib_module_names | {"toolguard"}`. Home is a new fitness predicate, or a test in `test_architecture.py` beside the existing layering tests. One scoping detail that is easy to get wrong: `[tool.hatch.build.targets.wheel] packages = ["toolguard"]`, so **`toolguard/tools/` and `toolguard/scripts/` ship** and are bound by the constraint; only the top-level `tools/` and `test/` are dev-only.

**The six-layer map.** Ruff can express "nobody may import module M, except this list of files". It cannot express a partial order. Encoding `foundation < config < engine < api < runtime < tooling < support` would need a ban per module with a per-module exemption list, and since every ban shares the code TID251 while `per-file-ignores` disables whole rules per file, the exemption lists would union into "everything is allowed". The two cases where the exemption set happens to be constant across all banned modules — R5's leaves and R6's api-only — are expressible and are the two blocks proposed above. `pyscn analyze` does the real layer validation and should keep doing it; ruff duplicating it partially would be worse than nothing.

**D1, the largest divergence in the delta, is invisible.** `Configuration` orchestrating the decision through a callback passed as a value is not an import and not an attribute access. Ruff is blind to it for the same reason the import graph and pyscn's layer compliance are — the delta already records that only co-change history saw it. No lint configuration changes this.

**R1, R2, R3 and claims C1, C3, C5, C6 have no lint expression.** "Exactly one type represents a verdict end-to-end", "no parallel arrays on `ToolPatternLayer`", "zero production sites read structured data out of a reason string", "undecidable is a unit kind" — these are project-specific structural assertions and `architecture_fitness.py --predicates` is their instrument. PLR0913 is the single point of contact between ruff and this list, and it touches one symptom of R1 (the twelve-parameter signature), not R1.

**The concurrency ban catches the import, not the syntax.** `async def` and bare `await` with no `asyncio` import would pass. There are zero `async def` in the tree today and no ruff rule bans the syntax; if it ever matters, it is one more line in the fitness tool's AST pass, which already walks every function definition.

**A green ruff run means four narrow things.** No new function-level import in production, no concurrency import, no signature above eight parameters outside the recorded debt list, no decorative noqa. It says nothing about layering, verdict multiplicity, rule representation, prose parsing, the stdlib constraint, or the config/engine inversion. That list is the point of writing this section: the value of the proposal is that it is small enough for its green to mean something specific.

## Relations

- relates_to [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 delta - as-is against ideal]]
- relates_to [[TOO-45 ideal picture]]
- relates_to [[TOO-45 decision log]]
