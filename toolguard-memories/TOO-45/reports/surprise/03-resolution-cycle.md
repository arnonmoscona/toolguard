---
title: Surprise factor - item 03 (permission_resolution/resolve cycle)
type: note
permalink: toolguard/too-45/reports/surprise/03-resolution-cycle
tags:
- task-memory
- TOO-45
- measurement
---

# Item 03 — remove the `permission_resolution` <-> `resolve` runtime cycle

Protocol: [[surprise-factor-protocol]]. Estimate pre-registered in [[03-estimate-predictions]] (sealed) and [[03-estimate-uncertainties]] (read before design). **Blinding held.** First item to use the **two designers + blind judge** pattern.

## Actual touch set — 22 files

| group | files |
|---|---|
| production, added | `file_matching.py` |
| production, modified | `permission_resolution.py`, `resolve.py`, `config_types.py`, `permissions.py`, `compound.py`, `config.py`, `hook.py`, `session_start.py` |
| dev instrument | `tools/architecture_fitness.py` |
| config / docs | `.pyscn.toml`, `docs/architecture.md` |
| tests, modified | `test_permission_resolution.py`, `test_configuration.py`, `test_hierarchical.py`, `test_hard_deny.py`, `test_takeover_mode.py`, `test_logging_streams.py`, `test_hook.py`, `test_hook_eval.py`, `test_resolve.py`, `test_architecture.py` |

Verified: 2,733 tests OK, **golden verdict corpus byte-identical**, `--layers` clean, ruff clean, and the cycle proven gone by independent measurement (below).

## Scoring

`|P| = 12`, `|A| = 22`, **hits = 8**, surprises = 14, overshoots = 4.

| | value |
|---|---|
| **recall** | **36%** — worst of the series |
| **precision** | **67%** — best of the series |

**Leak discount:** the ticket names three files. On the 19 unnamed, **recall is 26%**.

### FINDING 1 — the scoring rubric changed the estimator's behaviour

This is the most important result and it is about the instrument, not the code.

Item 10 scored **80% recall / 32% precision**. Item 03 scored **36% / 67%** — an almost exact inversion. And the estimator said what it was doing, in the prediction file:

> Deliberately **not** predicted, despite plausibility: `compound.py`, `api.py`, `hook.py`, `permissions.py`, `fixture_loader.py`, any corpus fixture, `.pyscn.toml`. All of these should be invariant if the refactor genuinely preserves what a decision *is*; **predicting them would be hedging, and hedging is what precision scoring punishes.**

Five of those seven were touched.

**I told it precision was scored, and it narrowed its list to protect that number.** The measurement changed the thing being measured — textbook Goodhart, produced by my own brief. Item 10's estimator cast 25 predictions at a 10-file change; this one cast 12 at a 22-file change. Same instrument, opposite failure, driven by what it was told mattered.

**Consequence for the protocol:** recall and precision cannot both be reported to the estimator as scored quantities without steering it. Either tell it neither, or tell it the one we actually care about. Given Arnon's framing — the estimate exists to align with *his* prior about size and shape, and a surprise is a trigger to ask why — **recall is the quantity that matters and precision should stop being advertised**. An over-broad list costs a little reading; a narrow one hides the surprises the instrument exists to surface.

### FINDING 2 — a design phase makes the estimate answer a different question

Two of the surprises (`file_matching.py` and its `.pyscn.toml` entry) exist because the **designers invented a stage the ticket never mentions**: extracting the file-path matching cluster out of `resolve.py` first. That was a good call — it stands on its own and made the rest reviewable — but no estimate made from the ticket could have contained it.

So on any item that goes through a design phase, the touch-set estimate is measuring *"what would this ticket touch"* while the actual set answers *"what did the design decide to touch"*. Those diverge by however much design freedom the ticket leaves. **Record which items had a design phase, and do not pool them with the mechanical ones when looking for a calibration multiplier.**

### FINDING 3 — prose coupling is back, at 5 files

`compound.py`, `config.py`, `hook.py`, `permissions.py` and `session_start.py` were touched **only** for docstring cross-references made stale by renaming `resolve_permission_detailed` -> `resolve_command_permission` and the private->public moves. Same category that was 31% of item 05's touch set, and the same trigger: **rename and delete cause prose coupling; change does not.**

### Cause assignment

| cause | count | files |
|---|---|---|
| **E** — estimator ignorance | 7 | the seven test modules holding adapter/stub call sites |
| **P** — prose coupling | 5 | the five doc-reference-only production files |
| **R** — requirement changed after the estimate | 2 | `file_matching.py`, `.pyscn.toml` — the design phase's added stage |
| **C** / **D** / **S** | 0 | |

The seven `E` files are the 13 adapter call sites plus the 26 fold sites. Worth noting the asymmetry in what each agent was told: **the designers were given the test-double count as a measured fact; the estimator was not.** That is a briefing choice I made, and it accounts for half the surprises on this item.

## The bake-off earned its cost

**The judge found two factual errors in the winning design, one of which was its headline risk:** B claimed the Bash closure silently drops `extended_syntax` and built a proposed simplification on it. Verified false at `resolve.py:798`, which passes it as the fourth positional. A single designer would have shipped that reasoning unchallenged.

It also corrected B's test accounting — B said 9 of 11 closures were trivial adapters and ~5 were genuine doubles; the real split is 5 adapters over 15 call sites and 6 hand-written stubs over 26 — which meant B had budgeted the *wrong half* as the risky work.

**Both designers independently measured the laziness question and agreed**: eager evaluation costs **+0.58%** matcher invocations across all 6,025 realistic cases (17,264 -> 17,364), because override detection already re-scans lower deny-bearing levels on an allow. One counted calls, one timed; same conclusion.

**The requirement neither designer proposed** — expose the cascade as a pure fold — came from asking why the judge wanted to defer the test migration. Without it the 26 cascade tests either strand on a seam production abandoned, or become slow integration tests. With it they are a subtraction.

## Independent verification of the actual claim

The whole item is "remove a cycle no import graph shows", so a green suite proves nothing about it. Measured directly with `sys.setprofile` across one live decision:

```
toolguard modules on the decision path: 13
inter-module edges recorded:            22
permission_resolution <-> resolve:      one direction only (resolve -> permission_resolution)
2-cycles anywhere on the path:          0
```

**No permanent test or fitness predicate was added.** Arnon's decision: the code-review process checks for runtime cycles by measurement per change instead, and that instruction now lives in the reviewer's own definition — *"an import graph does not show a cycle created by an injected callable... measure the runtime call topology rather than inferring it."*

## Complexity ratings

- **Blind judge: `medium`** — **the first non-`low` under the corrected brief, after three consecutive `low`s.** Counts: ~15 trivial/mechanical against 3-4 substantive. Its mechanism: *"the equivalence argument is not local — confirming eager evaluation is safe means checking that the matchers are pure, that `has_any_rules()`/`resolved_no_match_fallback()` are side-effect-free in `config.py`, and that dropping `_detect_override`'s `if not deny: continue` skip is only an optimisation. That is three modules held together for one substantive check."* Not `high`, because the shape is textbook and an import-set assertion mechanises the cycle claim.
- **Arnon**: pending review.

**This is the discrimination test the instrument had not yet passed.** Items 15, 10 and 05 were small-to-medium and mostly mechanical, and all came out `low` with Arnon agreeing. #03 is the first structural change, and the brief moved — with a stated reason that is about reading cost rather than size. It also correctly declined to go to `high`.

**Size, recorded separately per the confound Arnon identified:** 22 files, ~19 changed locations, of which the judge classified 15 as trivial. Note that 22 files at `medium` sits above 16 files at `low` (#10) and 11 at `low` (#15) — consistent with size, so **this single item does not disentangle shape from size either.** What does help: the judge's *stated reason* was locality of the equivalence argument, not volume, and it explicitly counted the largest block of the diff (~330 lines) as mechanical.

The judge also caught a defect I introduced: a block comment in `resolve.py` still claiming the moved cluster was re-exported "so existing importers keep working unchanged", after I removed those re-exports. Fixed.
