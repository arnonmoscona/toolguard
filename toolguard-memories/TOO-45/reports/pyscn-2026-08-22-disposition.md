---
title: pyscn-2026-08-22-disposition
type: note
permalink: toolguard/too-45/reports/pyscn-2026-08-22-disposition
---

# pyscn on `toolguard/`, 2026-08-22 — read, triaged, NOT acted on

Run after item 105 landed. **Health 72/100 (grade C).** Nothing here was changed; every line below is a recommendation for Arnon.

| dimension | score | |
|---|---|---|
| Dead code | **100** | 0 issues |
| Cohesion (LCOM) | **100** | 0 of 117 high |
| Coupling (CBO) | **95** | 1 of 76 high, avg 1.6 |
| Architecture | 82 | 82% compliant |
| Dependencies | 70 | **no cycles**, depth 11 |
| Complexity | **55** | 21 high-risk, avg 7.8 |
| Duplication | **45** | 15.9% cloned, 61 groups |

Dead code at 100 is worth noting: item 100 deleted the two orphans and `--orphans` reports zero, and pyscn independently agrees.

## RESOLVED — pyscn scores a FILTERED SUBSET, not the package

I first recorded this as an unexplained anomaly. Measured properly:

| | files | functions |
|---|---|---|
| **actually in `toolguard/`** (AST census) | **79** | **951** |
| **reported by pyscn** | 49 | **213** |

**pyscn's complexity analysis covers 22% of this package's functions**, and it is *function-level filtering, not file skipping* — for files it does report, it reports a subset:

| file | pyscn | AST |
|---|---|---|
| `config.py` | 19 | 58 |
| `command_extractor.py` | 15 | 48 |
| `maintenance.py` | 8 | 33 |
| `compound.py` | 8 | 21 |

Almost certainly a minimum-complexity floor, which is sensible tool design. **But it changes what every headline number means:**

- **"avg complexity 7.8" is the average over non-trivial functions only.** The package average is far lower. Quoting 7.8 as "this codebase's average complexity" would be wrong.
- **"Health Score 72/100 (C)" is computed over that same filtered set** — it is not a package-level health measure, and should never be put in a README badge as though it were.
- `toolguard/parser/bash_parser.py` (182 generated functions) is **absent entirely**, which the floor alone does not obviously explain. Whatever the cause, it means the generated parser is outside every number in this report.

**And it corrects my own note.** I had recorded "28 of 39 complexity offenders are in the canopy-generated parser, recommend excluding it." That is not the current situation, and the earlier reading was probably taken from a run with different settings. **Date every tool measurement and re-take it rather than carrying it forward.**

**Practical rule: use pyscn's per-function findings, which are real and checkable. Do not quote its aggregate scores.** The 21 high-risk functions below are genuine; the grade is not a fact about the package.

## (superseded) An anomaly I cannot explain, stated rather than glossed

**`toolguard/parser/bash_parser.py` does not appear anywhere in the results.** 78 files analysed, **0 skipped**, `ignore_patterns = []`, and the file is present at 297 KB. Yet none of its functions are among the 213 analysed, and 213 is far fewer functions than this package contains.

**This matters for interpretation.** My own earlier note claimed "28 of 39 complexity offenders are in the canopy-generated parser" and recommended excluding it. That is **not** the situation now — but I do not know whether the parser is being deliberately skipped, silently failing to parse, or whether `Functions` is a filtered list. **Do not read "Dead code: 0 issues" or the complexity average as covering the generated parser.** Worth one question to pyscn's behaviour before trusting any aggregate here.

## Complexity — 21 high-risk. My triage

**Fix, and they are the ones that matter:**
- **`permissions.match_command` (22)** and **`patterns.match_pattern` (15)** — the core matching path. Highest complexity on the most security-critical code in the project, and the place where a subtle branch error is silent. If anything on this list earns work, it is these two.
- **`command_model.node_kind` (15)** — grew as construct kinds accumulated, and item 105 added `COMMENT`. It is a flat ordered-choice dispatch whose ordering is load-bearing and documented; complexity here is honest rather than tangled. **Watch, do not refactor** — the ordering comments are the asset and a restructure risks them.

**Defer — high by nature, low by risk:**
- `installer.py` × 5 (`cmd_seed_self_perms` 24, `cmd_skills_status` 18, `cmd_register_hooks` 15, ...) — CLI entry points. Branchy because they handle flags and user error, run once interactively, and fail loudly.
- `toml_scan._scan_array_char` (23), `_find_array_close` (16) — character-level scanners; the complexity is the domain.
- `rule_apply._apply_to_file` (25) — the highest single number, and maintenance-tool code rather than the permission path.

**Ignore:** the rest sit at 10-13 and are ordinary.

## Duplication — 45/100, 15.9% cloned across 61 groups

**Not triaged, and I am not recommending anything on it.** This project has been bitten before by acting on duplication counts without reading the fragments — the earlier campaign found the conclusion changed three times once the actual clones were read. 36 pyscn "suggestions" exist in the JSON, mostly clone extractions marked `severity: critical, effort: easy`; **severity from a clone detector is not severity in this codebase's sense**, and several are likely test fixtures or the deliberate per-kind helpers item 95 created.

**Recommendation: treat duplication as its own scoped task**, read the fragments, and expect the honest number to be well below 15.9%.

## What I would actually do, if asked

1. **`match_command` and `match_pattern`** — the only two I would schedule on merit.
2. **Duplication** — a separate task that starts by reading fragments, not by extracting.
3. **Resolve the `bash_parser.py` anomaly** before quoting any pyscn aggregate as a project health number.

Everything else is defer or ignore. **A grade of C here is not evidence of a problem** — it is one threshold-based instrument, and by this project's own rule (`.claude/rules/evidence-before-fixing.md`) a threshold check is a signal to look, not a verdict.

---

# ARNON'S STANDING POSITION 2026-08-23 — stronger than what I wrote

> *"pyscn health score - like any other aggregate 'architecture metric' we discussed - it is pretty useless, even as a directional measure. With pyscn I care about individual findings and widely accepted metrics like cognitive complexity cyclomatic complexity etc. And even then the thresholds are reason to review rather than absolute."*

I had written "use the per-function findings, do not quote the aggregate". **His position is stronger on both halves and it is the rule to follow:**

1. **The aggregate is useless even DIRECTIONALLY.** Not "imprecise", not "needs context" — a composite of unrelated dimensions with invented weights carries no information about whether the codebase got better. Do not track it over time, do not put it in a badge, do not mention it as a trend.
2. **Individual findings and standard metrics are what count** — cyclomatic and cognitive complexity, per function, because they are widely understood and mean the same thing everywhere.
3. **Even those are a reason to REVIEW, not a verdict.** A function over a threshold is a place to go look. `judge_unit` at 20 was worth splitting; `node_kind` at 15 is a flat ordered dispatch whose ordering is documented and load-bearing, and splitting it would destroy the thing that makes it readable. **Same number, opposite conclusions** — which is precisely why the threshold cannot decide.

This matches `.claude/rules/evidence-before-fixing.md`'s instrument rule: a check is strong when it measures conformance to a declared intent, and a threshold declares nothing. It is a signal to look, and looking is the whole value.

**Consequence for this report**: the 22%-coverage finding above is not a reason to distrust one number and trust the rest — the grade should not be used at all. The per-function list stands on its own.
