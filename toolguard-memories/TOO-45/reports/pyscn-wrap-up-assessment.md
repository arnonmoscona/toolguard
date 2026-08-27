---
title: TOO-45 wrap-up - pyscn assessment, fix/defer/ignore
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/pyscn-wrap-up-assessment
---

# pyscn at the end of TOO-45, and what to do about it

`uv run pyscn analyze toolguard/`, 2026-08-21: **Health 71/100 (C)**.

| component | score | |
|---|---|---|
| Dead code | 100 | clean |
| Cohesion (LCOM) | 100 | clean |
| Coupling (CBO) | 95 | 1 of 76 high |
| Architecture | 82 | 82% compliant |
| Dependencies | 70 | **no cycles**, depth 11 |
| **Complexity** | **50** | avg 8.2, 23 high-risk |
| **Duplication** | **45** | 16.2% cloned, 62 groups |

## The headline score cannot answer "did the campaign help"

Across **86 archived reports** the health score ranges **61-73**. It was **73** when the campaign started (2026-08-13) and is **71** now. Readings from a single day span 61 to 72.

**A ±5 movement inside that band means nothing**, so neither an improvement nor a regression can be claimed from it. Recorded so nobody later reads 73 -> 71 as damage.

## Complexity — 28 of the 39 offenders are GENERATED code

`pyscn check` lists **39** functions over the threshold of 10. **28 are in `toolguard/parser/bash_parser.py`**, which canopy generates from the `.peg` grammar. Nobody wrote `Grammar._read_reserved_word` (complexity **80**) and nobody should refactor it — it is build output, and the grammar is the source.

**That leaves 11 hand-written functions**, which is a very different picture from "23 high-risk functions":

| function | complexity | phase-3 commits touching the file |
|---|---|---|
| `config.Configuration.validation_issues` | **35** | 5 |
| `tools/rule_apply._apply_to_file` | 25 | — |
| `tools/installer.cmd_seed_self_perms` | 24 | — |
| `toml_scan._scan_array_char` | 23 | — |
| `permissions.match_command` | 22 | — |
| `compound.judge_unit` | 20 | 2 |
| `parser/multiline._statement_bounds_containing` | 19 | 1 |
| `tools/security_audit.main` | 18 | — |
| `tools/installer.cmd_skills_status` | 18 | — |
| `rule_entry.merge_entries` | 18 | — |
| `tools/consolidate._find_literal_alternations` | 17 | — |

**Recommend excluding `bash_parser.py` from the complexity metric** in `.pyscn.toml`. It is generated, it dominates the count, and leaving it in makes the number uninformative — every reading is 70% noise about a file nobody edits.

## Two of these are this campaign's own work — stated rather than buried

**`Configuration.validation_issues` at 35 is the worst hand-written function in the package, and ticket 52 added to it.** The bare-string shape checks landed there because that is where per-layer validation lives. The fix was right; the function was already the largest and is now larger. **This is the "comments cluster where a function should be split" signal, in numeric form.**

**`_statement_bounds_containing` at 19 was created by ticket 19.** Its reviewer flagged it at **12** and suggested collapsing three near-identical separator branches into a table; it then grew to 19 when `&` and the `$(...)` depth guard were added. The reviewer's specific observation was that a table would have made the missing `&` case *"visible as an absent table entry rather than an absent branch"* — which is exactly the defect that later shipped and had to be repaired.

**`compound.judge_unit` at 20** is named by ticket 07 as the worked example of *"comments compensating for complexity — where this is the cause, split the function rather than trimming the comment."* It was not split.

## Duplication — 16.2%, and the campaign both created and removed clones

Not investigated per-group. Known from review: this campaign **removed** several by extracting `_pick_strictest`, `all_parts` and `_corpus_verdict`, and **created** at least one (the third `_atomic_write`, deliberately, with the duplication named in its docstring for a later consolidation).

## Recommendation

| item | disposition |
|---|---|
| `bash_parser.py` in the complexity metric | **FIX the metric** — exclude generated code, one config line |
| `validation_issues` (35) | **FIX, own ticket** — largest hand-written function, actively growing, and the split is the real remedy |
| `_statement_bounds_containing` (19) | **FIX, small** — collapse the separator branches to a table, as its reviewer proposed before the defect it predicted actually shipped |
| `judge_unit` (20) | **DEFER with a ticket** — named by 07, untouched, and splitting it touches the decision path |
| the other 8 hand-written | **IGNORE for now** — mostly CLI entry points and installer commands, low blast radius |
| duplication 16.2% | **MEASURE before deciding** — 62 groups is a number, not a finding, and this campaign has repeatedly shown that printing the members changes the conclusion |
