---
title: Surprise factor - item 05 (delete tools/decision.py)
type: note
permalink: toolguard/too-45/reports/surprise/05-decision-shim
tags:
- task-memory
- TOO-45
- measurement
---

# Item 05 — delete the `tools/decision.py` shim

Protocol: [[surprise-factor-protocol]]. Estimator ran blind on the briefing only and confirmed it opened no repository file.

## INSTRUMENT DEFECT, first run — my half of the blinding failed

The protocol says I do not read the estimate until implementation is complete. **The estimate was delivered into my context automatically as a background-task notification**, in full, while I was still mid-implementation. I could not decline it.

Facts as they stand:

- My own enumeration of every reference site was already done and is in the transcript **before** the estimate arrived, so the production and test import sets were fixed independently.
- **Not yet decided when it arrived**: the test-file question. The estimator names that as its #1 concentration item. So my resolution of it is contaminated and cannot be scored.

**Item 05's score is therefore flagged CONTAMINATED and does not count toward the abandon gate.**

**Fix applied for items 04, 01, 10, 03, 07, 09**: the estimator writes its answer to a file and returns only a completion token, so the notification carries no content. Blindness then holds on both sides.

## Ticket-named files (the free part of the estimate)

The ticket names `toolguard/tools/decision.py` and six importers. Per protocol those are discounted: the honest signal is the surprise set **restricted to files the ticket did not name**.

## Pre-registered estimate

### Predicted touch set

| path | action | conf | provenance |
|---|---|---|---|
| `toolguard/tools/decision.py` | deleted | high | ticket |
| `toolguard/tools/uninstall_readiness.py` | modified | high | ticket |
| `toolguard/tools/mining.py` | modified | high | ticket |
| `toolguard/tools/self_permission.py` | modified | high | ticket |
| `toolguard/tools/consolidate.py` | modified | high | ticket |
| `toolguard/tools/replay.py` | modified | high | ticket |
| `toolguard/testing/sandbox.py` | modified | high | ticket |
| `toolguard/tools/maintenance.py` | modified | medium | reasoning |
| `toolguard/tools/security_audit.py` | modified | low | reasoning |
| `toolguard/tools/installer.py` | modified | low | reasoning |
| `test/unit/test_tools_decision.py` | modified or deleted | high | ticket-derived |
| `test/unit/test_api.py` | modified | high | reasoning |
| `test/unit/test_architecture.py` | modified | high | reasoning |
| `test/unit/test_resolve.py` | modified | high | reasoning |
| `test/unit/test_tools_replay.py` | modified | medium | reasoning |
| `test/unit/test_sandbox.py` | modified | medium | reasoning |
| `test/unit/test_tools_consolidate.py` | modified | medium | reasoning |
| `test/unit/test_tools_mining.py` | modified | medium | reasoning |
| `test/unit/test_tools_self_permission.py` | modified | medium | reasoning |
| `test/unit/test_tools_uninstall_readiness.py` | modified | medium | reasoning |
| `test/unit/test_architecture_fitness.py` | modified | medium | reasoning |
| `tools/architecture_fitness.py` | modified | medium | reasoning |
| `.pyscn.toml` | modified | medium | reasoning |
| `test/unit/test_static_analysis_coverage.py` | modified | low | reasoning |
| `test/verdict_corpus/fixture_loader.py` | modified | low | reasoning |
| `docs/architecture.md` | modified | high | ticket-licensed |
| `docs/agent-map.md` | modified | medium | ticket-licensed |
| `docs/agent-guides.md` | modified | low | reasoning |
| `test/unit/__init__.py` | modified | low | reasoning |

### Concentration set

1. `test/unit/test_tools_decision.py` — 894 lines named for a 38-line stub; cannot be testing 38 lines of re-export. "The single biggest judgement call in this ticket."
2. `test/unit/test_architecture.py` + `.pyscn.toml` — where a clean refactor can silently de-validate a layer.
3. `toolguard/tools/replay.py` — the keystone, and the safety argument runs through it.
4. `tools/architecture_fitness.py` — 4,112 lines measuring the graph being changed.

### Expected counts

Production 6 modified (up to 9), 1 deleted. Tests 6 modified (range 3–11), 0–1 deleted. Docs/config 3 (range 1–5). **Total ~16 files, range 11–24. Lines changed: 120–250, order of magnitude hundreds** — with the explicit note that if the 894-line test file is merged rather than renamed the number goes to 900+.

**The estimator contradicted the ticket**, which is the most interesting thing it did: *"The ticket says 17 edits; I predict ~16 files but materially more than 17 changed lines, because it counts import statements and not the test module named after the thing being deleted."*

### Named uncertainties, verbatim in substance

1. **String-literal references** — `patch("toolguard.tools.decision.decide")` is invisible to an import-graph reasoner and fails at *call* time, not import time. Called this "the single most probable source of a mechanical change taking an afternoon."
2. Whether `.pyscn.toml` lists modules individually or by package prefix — differs by two files.
3. Whether `test_tools_decision.py` is a real behaviour suite or a stub. "The largest single variance in my estimate and unresolvable from the inventory."
4. Whether importers use `from x import decide` or qualified `import ... as decision` — the latter multiplies the edit by every call site.
5. **Docs are entirely opaque** — and it flagged that `README.md`, `AGENTS.md`, `llms.txt`, `technical-notes.md` are absent from the inventory it was given, so its doc prediction came from a knowingly incomplete list.
6. **Skill bodies and `.claude/` config are not in the inventory** — "if a skill body names `tools/decision.py` as an entry point, deleting it breaks a user-facing workflow with no test coverage at all."
7. Whether `api.py` must grow, if the shim re-exported more than `decide`.
8. Whether the golden corpus imports through the shim — in which case it does not independently guard this change.

Uncertainties 5 and 6 are a defect in **my briefing generator**, not in the estimator: `build_estimator_briefing.py` scans `toolguard/`, `tools/`, `test/`, `docs/` and omits repo-root markdown and `.claude/`. Fixed before the next run.

## Verified before implementation

- **No string-path patches exist** — greped for `patch("toolguard.tools.decision...` and `import_module`: zero hits. Uncertainty 1 resolves clean.
- **`.pyscn.toml` lists layers by package, not module** (`packages = ["tools", "scripts"]`), so no map edit is needed. Uncertainty 2 resolves clean — the estimator's `.pyscn.toml` prediction is an overshoot.
- **The shim re-exports exactly one name**, `decide`. Uncertainty 7 resolves clean.
- **No `docs/` file and no `.claude/` file references the module.** Only `technical-notes.md` and `test/verdict_corpus/README.md` do.

## Actual touch set

**26 files** (memory notes excluded — they are records, not code). Verified green: 2,601 tests OK, golden corpus no differences, `--layers` complete with no direction violations, ruff clean.

| group | files |
|---|---|
| production, code changed | `tools/mining.py`, `tools/replay.py`, `tools/self_permission.py`, `tools/uninstall_readiness.py`, `tools/consolidate.py`, `testing/sandbox.py` |
| production, **prose only** | `api.py`, `hook.py`, `permission_resolution.py`, `resolve.py`, `tools/__init__.py` |
| production, deleted | `tools/decision.py` |
| dev tooling, prose only | `tools/corpus_build.py` |
| docs, prose only | `technical-notes.md`, `test/verdict_corpus/README.md` |
| tests | `test_api.py` (merge target), `test_tools_decision.py` (deleted), `test_ask_resolution.py`, `test_hook_eval.py`, `test_resolve.py`, `test_self_integrity.py`, `test_symlink_hierarchy.py`, `test_tools_consolidate.py`, `test_tools_installer.py`, `test_verdict_corpus.py`, `verdict_corpus/fixture_loader.py` |

Prose-only classification is **measured, not judged**: `scratchpad/prose_only_check.py` parses the HEAD and working-tree versions, strips every docstring, and compares ASTs. Equal AST means the diff touched only comments and docstrings.

## Scoring

`|P| = 29`, `|A| = 26`, **hits = 12**.

| group | predicted | actual | hits | surprises | overshoot |
|---|---|---|---|---|---|
| production | 10 | 12 | 7 | 5 | 3 |
| tests | 14 | 11 | 5 | 6 | 9 |
| docs + dev tooling | 5 | 3 | 0 | 3 | 5 |
| **total** | **29** | **26** | **12** | **14** | **17** |

### FINDING 1 — the ratio as specified is nearly blind, and this run proves it

**Surprise ratio `|A|/|P|` = 26/29 = 0.90.** Read on its own that is a near-perfect estimate.

The sets overlap on **12 of 43 distinct files. Precision 41%, recall 46%, Jaccard 28%.** The estimator got fewer than half the files right in each direction and the ratio still reported 0.90, because misses and overshoots cancel.

This is a defect in the measure as literally specified, not in this estimator. Two sets of similar size can share almost nothing. **The ratio must be replaced by, or at minimum reported alongside, the overlap.** Recommendation: lead with recall (`hits/|A|` — what fraction of the real change was foreseen), because that is the quantity the process cares about, and carry precision so a predictor cannot win by naming everything.

Cheap to have caught, and worth noting it was caught on item one of seven rather than after all seven.

### FINDING 2 — prose coupling was 31% of the change, and it doubled the production touch set

**8 of 26 files were edited only because a comment or docstring named a deleted module.** No executable line changed in any of them.

The production number is the sharp one: **6 modules had to change code; 12 production files changed in total.** Documentation references doubled it. Every one was invisible to the import graph, to `--layers`, to ruff, to pyright, and to the estimator.

This is a measured argument for item **#07** that the doc-comment sweep did not previously have. The verbose cross-referencing style does not merely cost reading time — it creates a maintenance coupling with a file count attached. `hook.py`'s was the clearest case: a comment explaining why a cycle was broken, describing modules that no longer exist in that relationship.

**New cause category `P` — prose coupling.** It is not estimator ignorance (the coupling is real and it made the change bigger) and it is not hidden coupling in the architectural sense (a competent reader would expect docstring references to exist). It deserves its own name because the remedy is different from both: shorter comments, not better architecture and not a thicker briefing.

### FINDING 3 — the estimator's model of the test suite was systematically wrong, and so is the suite's naming

It predicted the tests **named after the importing modules** — `test_tools_mining`, `test_tools_self_permission`, `test_tools_uninstall_readiness`, `test_tools_replay`, `test_sandbox`. **None of those import `decide`.** The files that actually did were `test_ask_resolution`, `test_hook_eval`, `test_self_integrity`, `test_symlink_hierarchy`, `test_tools_installer`, `test_verdict_corpus`.

9 overshoots and 6 misses from one wrong assumption: that a test module named for a production module is the module that exercises it. That assumption is reasonable. **It does not hold in this repo**, and that is a fact about the test suite worth knowing independently of this measurement.

### Cause assignment

| cause | count | alarm |
|---|---|---|
| **P** — prose coupling | 8 | **yes** (new category, see Finding 2) |
| **E** — estimator ignorance | 6 | no |
| **C** — hidden coupling | 0 | — |
| **D** — latent defect | 0 | — |
| **S** — scope creep | 0 | — |

Zero `C` and zero `D`: after the TOO-45 rework, deleting a module in the tooling layer had no structural surprises at all. The whole surprise budget went to prose and to a wrong model of the test suite. For a change of this kind that is the good outcome.

**Contamination caveat**: I had seen the estimate before resolving the test-file merge question. The test-group numbers should be treated as soft. The production and prose numbers were determined by a grep that predates the contamination and stand.

### Modified co-change `n/(n-1)`

`n = 26`, `n/(n-1) = 1.04`. Recorded per protocol; no interpretation until there are enough items to compare. First observation: it is a function of `n` alone, so on this item it carries no information the file count does not.
