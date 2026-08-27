---
title: The architecture fitness tool reports PASS over an empty tree, cannot tell
  a loosened layer map from a fixed import, and is itself excluded from static analysis
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/66-the-architecture-fitness-tool-passes-over-nothing-and-cannot-see-a-loosened-map
---

**PARTIALLY FIXED in `05f786d`.** (a) the empty-tree guard and (c) the ruff/ticket-30-safe form are fixed; still open: (b) a loosened map is still invisible in production, closed only by a test pin, and `[architecture].enabled` is still parsed by nothing.

# The instrument that certifies the architecture

**Found 2026-08-13. Five RED tests in the tree. Consolidates tickets 29 and 30 with three new findings, because they are one tool and one fix owner.**

## 1 — Ticket 29 reproduces exactly, and in four more sub-commands than it names

`run_guard(only_canaries=True)` with `GUARD_CANARIES` empty returns `ok=True, failures=[], warnings=[], canary_results=[]`, and `render_guard_text` prints:

```
=== --guard: PASS === (no violations)
```

A clean, **un-skipped** run of zero cases. RED: `test_run_guard_does_not_pass_with_an_empty_canary_set` and `test_run_guard_canaries_does_not_report_a_clean_unskipped_empty_run`.

**Newly measured, same shape, four more places:**

- `check_layers` reports **`ok=True` over a tree with zero modules**
- `compute_predicates` reports **R2, R3, R5 and R6 all `pass=True`** over the same empty tree

RED: `test_check_layers_does_not_pass_over_a_tree_with_no_modules`, `test_compute_predicates_does_not_pass_every_step_over_an_empty_tree`.

## 2 — Ticket 30 undercounts, and the file it misses is this one

`uvx pyscn analyze tools/architecture_fitness.py` prints

```
Warning: Failed to parse file tools/architecture_fitness.py: syntax errors found in source code
```

**and then reports Health Score 100/100, Grade A, all five metrics 100/100.**

So the static analyser the pre-push checklist depends on **reports perfect health for a file it could not read** — ticket 29's shape inside the measuring instrument.

The cause is `tools/architecture_fitness.py:3175`'s three-name `except json.JSONDecodeError, KeyError, TypeError:`. **Ticket 30 misses this file entirely** — and it is the tool that certifies the architecture.

Corrections to ticket 30's enumeration: `comment_hygiene.py` has **three** such clauses (106, 351, 427), not one; repo-wide the totals are **6 three-name clauses across 4 files** and **23 unparenthesized clauses**, not 3 and 22.

### TICKET 30's FIX DIRECTION IS MEASURABLY WRONG, AND THIS TICKET INHERITED IT

**Measured 2026-08-14 on ruff 0.15.14.** Ticket 30 states: *"`ruff format` will leave a three-name parenthesised tuple alone (it only strips the two-name form), so the fix is stable."*

**False.** `except (ValueError, TypeError, OSError):` is reformatted **straight back to the bare form**. So anyone applying ticket 30's fix will have it **silently reverted by this project's own mandated `uv run ruff format .`**, re-blinding pyscn with no signal at all.

**Two forms measured to survive ruff AND make pyscn parse:**

1. a parenthesised tuple with a **magic trailing comma**, exploded across lines;
2. the tuple hoisted to a **named constant**.

The failing test carries this in its message, so whoever fixes it sees it at the point of failure.

### Two more measured facts that change the fix's shape

- **The generated parser does not crash pyscn — it HANGS it.** `pyscn analyze` on an unexcluded copy of `bash_parser.py` ran past **six minutes** with no output and had to be killed. `.pyscn.toml` calls it *"hits a bug in pyscn"*; the exclusion is far more load-bearing than that. **Any guard that could reach that file needs a timeout** — the previous `timeout=600` would have stalled the suite for ten minutes.
- **`.pyscn.toml` excludes `**/test_*.py`, so no pyscn-based guard can EVER cover the test suite.** That is why the repaired guard is **AST-based** rather than a widened pyscn run — widening the pyscn target to `test/` would still see nothing.

### The current census, verified at HEAD rather than trusted

**7 three-name clauses across 5 files, all of them OUTSIDE `toolguard/`** — which is exactly the tree the guard was scanning:

`tools/architecture_fitness.py:3175` · `tools/change_role_classifier.py:1909` · `tools/comment_hygiene.py:{106,351,427}` · `test/unit/_real_log_dir_guard.py:114` · `test/unit/test_tools_hierarchy.py:282`

The last is a **concurrent sibling agent's working-tree edit, not in HEAD** — attributed by path and reported as live evidence, not filed as a defect. So **this ticket's "6 across 4" and "23 total" are correct at HEAD.**

**And pyscn also writes an unbounded ~112 KB HTML report per `analyze` into `<cwd>/.pyscn/reports/`** — gitignored, so **40 files (~4.5 MB) had accumulated invisibly**, written by the guard's own test runs.

**A further site found 2026-08-13, and it is the worst-placed one yet**: `test/unit/_real_log_dir_guard.py:114` carries `except TypeError, ValueError, OSError:`. That is **the suite's central safety machinery** — the guard every "no files written outside the fixture" claim in this campaign leans on — and by the same mechanism it is silently excluded from `pyscn`. The repo's own `test_static_analysis_coverage.py` is the tool that names this pattern, which makes it three levels of instrument failing to see itself.

## 3 — The layer map is gameable, and `check_layers` cannot tell the difference BY CONSTRUCTION

Demoting `once_per` to `foundation` manufactures a violation (`once_per (foundation) -> once_per_store (observability)`). Adding `"observability"` to foundation's allow-list **erases it**: `ok=True`, zero violations.

`check_layers`' report carries only `unmapped / multiply_mapped / module_layer / violations`, and `render_layers_text` prints the identical *"No cross-layer direction violations"* either way. **There is no signal that distinguishes fixing the import from loosening the rule.**

Measured: **only `api`'s allow-list was pinned by any test in `test/`. The other seven were free.** Now closed by `test_every_layer_allow_list_is_pinned_against_a_silent_loosening`, which under the loosened map is **the only failing test in the module**.

Three further gaps in the same check:

- **a declared package with no module behind it is never reported** — dead map entries are invisible (RED: `test_check_layers_reports_a_declared_package_with_no_module_behind_it`)
- **`[architecture].enabled` is parsed by nothing** — `enabled = false` changes no result
- **`--guard` does not reference `check_layers` or `layers` at all**

## 3b — THE TEST-SIDE GUARD WAS WORSE, and one bypass is live

**Measured 2026-08-14 in `test_architecture.py` (7 -> 25 tests, 30 of 31 mutants now detected, no REDs needed — every gap was closable inside the test file).**

**The layer map could be LOOSENED with the suite green.** Adding `permission_resolution -> toolguard.config`, adding `config_types -> toolguard.permissions`, **deleting a row**, **emptying `LAYERS` entirely**, and **inverting the layer order** each failed **zero tests**. Seven of nine map mutants were invisible. The only canary was *wrongly tightening* the map — and wrong-tightening and a genuine upward import failed a **byte-identical single-test set**, so the one detector fires only when map and code disagree, never when the map is loosened toward the code.

**The queue's standing note — *"only completeness is pinned, direction is not"* — is wrong in BOTH halves.** `LAYERS` covered **7 of 37** top-level modules and *nothing* asserted that set, so completeness was unpinned too. Direction was worse than unpinned: the Gherkin claimed *"imports only from layers strictly below its own"* while the body tested set membership against a hand-written allow-list, and **two allow-list targets (`permissions`, `file_matching`) were not in the ordering at all**, so "below" was undefined for them.

### The bypass is a live import-syntax gap, not a hypothetical

Planting an upward import of `toolguard.config` into `issues.py` in six syntactic forms:

| form | detected at HEAD? |
|---|---|
| `import toolguard.config`, `from toolguard.config import x`, `import ... as` | yes |
| `from toolguard import config` | **missed by the test whose entire stated purpose is that import** (AST records `node.module == "toolguard"`); caught only incidentally |
| `from . import config`, `from .config import x` | **completely undetected — zero tests** |

**The package genuinely uses these forms**: relative imports at `permissions.py:18-20` and `patterns.py:16`, and `from toolguard import X` at 8 sites. **`permissions.py`'s imports read as EMPTY to the old extractor**, so a module added to the map would have been governed by nothing.

Same class of gap as ticket 74's: a detector that handles the form its author had in mind.

### Drift had already happened, and OP4 is closed

`config_types` declared an allow-edge to `toolguard.issues` **that it does not import** — a dead pre-authorisation, with nothing reconciling the three declarations of one model (`.pyscn.toml`, `architecture_fitness.py`, `test_architecture.py`). All three are now reconciled in three directions, and neutering `_architecture_config()` fails 4 tests.

This also closes queue item **OP4**: `file_lock`'s *"foundation, no toolguard imports"* property was enforced by **nothing** — grep returned zero hits across all three files.

Also unpinned: `RE_EXPORTED_TYPES` omitted **`UnrecognizedFallbackSetting`** (`config.py` re-exports 8 types from `config_types`; the guard covered 7), and the hardcoded leaf re-export test covered 3 of the 5 names from `rule_entry`.

**And this module's own detectors had no tests at all**: `_module_imports` and `_local_imports`, the two functions everything here rests on, were untested. Nine tests added.

## 4 — A FIFTH inert-mock shape: a constant bound as a DEFAULT ARGUMENT

`parse_architecture_config(pyscn_toml_path: Path = PYSCN_TOML)` binds the module constant **as a default argument at import time**, and all three call sites call it with no arguments. **So `mock.patch.object(af, "PYSCN_TOML", ...)` is provably inert.**

Falsified: `check_layers()` under the patch returns `ok=True, 76 mapped` — byte-identical to baseline — while `check_layers(arch=parse_architecture_config(gamed))` returns `ok=False, 76 unmapped`.

This is **distinct from the import-time-constant shape** already recorded (`USER_LEDGER_PATH`): there the constant is read at import; here it is *captured into a signature*. **The same shape applies to `TOOLGUARD_DIR` and `REPO_ROOT` across most of that module — any future test patching those constants will be silently inert.**

It produced two cannot-fail tests, one of which asserted that R5 was *unchanged* under a patch that changed nothing. Compounding it, **two of that test's three "gamed" string replacements no longer matched the real `.pyscn.toml`** — only one still fired.

Both repaired to patch `parse_architecture_config` itself, each with an **assert-the-patch-took-effect** differential, and both repairs falsified by reverting to the inert form.

## 5 — Two renderers, ~190 lines, zero calls

Measured by wrapping with counters over a full module run: **`render_predicates_text` — 0 calls. `render_metrics_text` — 0 calls.** The predicates smoke test uses `--json`, which skips the renderer entirely, and no `--metrics` text-mode test exists.

## Two more queue claims that were false

- **AFT: *"Assertions that cannot fail: none found as a defect in the test file itself. Read every method body in the unread remainder."* FALSE** — two cannot-fail tests sit in that range, one of them in `TestComputePredicates`, the very class whose docstring that pass corrected.
- **AF4: *"Mitigated as a side effect of this sweep."* FALSE** — `--help` still prints `Dev instrument for the TOO-45 architecture-refactoring loop: four modes over this`, ending mid-phrase.

## Method note worth keeping — an ambient delta correctly refused

In-process snapshots showed the repo's `logs/` growing by ~1,200 bytes across full module runs. Rather than record a leak, the agent ran a **22-second idle control** (no writes), then **per-test attribution across all 189 tests** (zero writes), and identified the cause: **the dev machine's own live toolguard hook, logging the agent's Bash calls into the same file.**

The instinct to explain rather than report is the same one that turned a "4-failure environmental floor" into a real fixture defect earlier in this campaign — applied here in the opposite direction, to *avoid* filing a false one.