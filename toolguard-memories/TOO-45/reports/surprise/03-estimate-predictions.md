---
title: Blind estimate (predictions) - item 03 resolution cycle
type: note
permalink: toolguard/too-45/reports/surprise/03-estimate-predictions
tags:
- task-memory
- TOO-45
- measurement
---

## 1. Predicted touch set

| path | add/modify/delete | prod/test | confidence | reason |
|---|---|---|---|---|
| `toolguard/permission_resolution.py` **[named]** | modify | production | high | The callback-receiving side; either becomes a pure cascade over supplied matches or loses the injected callable entirely. 364 lines, so likely a large fraction of it. |
| `toolguard/resolve.py` **[named]** | modify | production | high | `_decide_detailed` is the injected callable; it either stops being injected or becomes the driver of the iteration. |
| `toolguard/config_types.py` **[named]** | modify | production | medium-high | Holds `DecideDetailed`; if the callable seam goes, that Protocol goes with it, and a new data type for per-level matches most plausibly lands here (config is below engine, so both engine modules may import it). |
| `test/unit/test_permission_resolution.py` | modify | test | high | 168 lines directly targeting the module whose signature changes; existing tests almost certainly construct the injected callable. |
| `test/unit/test_permission_resolution_seam.py` (or similarly named seam file) | add | test | medium | Direct analogy with `test_compound_resolve_seam.py` (494 lines), which the sibling cycle removal produced. Same team, same ticket series, same "characterization then refinement" method. |
| `test/unit/test_architecture.py` | modify | test | medium | 302 lines of "architectural invariant tests for module layering". If the typed-but-unremoved cycle was recorded anywhere as a known/expected exception, this is where the assertion lives and it must be inverted once removed. |
| `tools/architecture_fitness.py` | modify | production (dev tool) | medium-low | The per-iteration fitness instrument. If it carries a known-runtime-cycle registry or a per-iteration count, the pair drops out of it. Only if such a registry exists. |
| `technical-notes.md` | modify | production (doc) | medium | 1180 lines of design rationale; the sibling cycle removal is the kind of thing that got written up there, and this is the closing half of that story. |
| `test/unit/test_resolve.py` | modify | test | low-medium | 2855 lines, but its docstring says it is an `api.decide()` anti-drift contract test, not a `resolve` unit test — so it should be *insensitive* to an internal reshuffle. Predicted only because a signature change to `_decide_detailed` may still be referenced by name here. |
| `docs/architecture.md` | modify | production (doc) | low-medium | 382 lines; a "dependency graph a reader can trust" is the stated payoff, and this is the doc that would assert it. |
| `test/unit/test_compound.py` | modify | test | low | 3005 lines and the largest indirect exerciser of the resolution path; likely to need touch-ups only if internal helper names leak into it. |
| `test/unit/test_architecture_fitness.py` | modify | test | low | 3975 lines; only touched if `architecture_fitness.py` is. Paired by construction. |

Deliberately **not** predicted, despite plausibility: `toolguard/compound.py` (its side of the seam was already resolved), `toolguard/api.py`, `toolguard/hook.py`, `toolguard/permissions.py`, `test/verdict_corpus/fixture_loader.py`, any `test/verdict_corpus/configs/*` fixture, `.pyscn.toml`. All of these should be invariant if the refactor genuinely preserves what a decision *is*; predicting them would be hedging, and hedging is what precision scoring punishes.

## 2. Concentration set

The substance is in **two production modules and one type module**: `permission_resolution.py`, `resolve.py`, `config_types.py`. Everything else is consequence.

Within those, the substance is narrower still: **the boundary object**. Today the boundary is a function (`DecideDetailed`); after the change it is either a value (per-level matches) or a control-flow inversion (resolve drives, permission_resolution folds). The entire design risk sits in what that boundary object is required to carry — matches only, or matches *plus* provenance, issues and warning side effects. If it turns out to carry more than matches, the touch set widens to whatever produces those extras, and my prediction is wrong in shape, not just in count.

Second concentration: **test rewriting is likely to exceed production line change.** A 168-line dedicated test file plus a probable new ~400-500 line seam file, against maybe 150-250 changed production lines.

## 3. Expected counts

| | modified | added | deleted |
|---|---|---|---|
| production (incl. dev tools + docs) | 5 | 0 | 0 |
| test | 4 | 1 | 0 |

Totals: 9 modified, 1 added, 0 deleted. Of the modified production files, 3 are code (`permission_resolution.py`, `resolve.py`, `config_types.py`) and 2 are docs/tooling.
