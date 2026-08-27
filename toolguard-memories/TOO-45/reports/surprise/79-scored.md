---
title: TOO-45 surprise factor - ticket 79 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/79-scored
---

# Ticket 79 scored - command substitution ASK floor

Commit `5124795`. Diffstat total **1,021 changed lines across 8 files**.

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **155 / 1,021 = 15.2%** |
| file recall | 2 / 8 = 25% |
| precision (integrity guard only) | 2 / 7 = 28.6% |
| layer prediction | **CORRECT** |
| scope prediction | correct on corpus-tier exclusion |

**Lowest line-weighted recall in the series**, on the ticket with the highest actual cost (11 agent runs, ~3M subagent tokens, four review rounds). Those two facts are the same fact, and that is the finding.

## Per-file

| file | lines | predicted? | confidence | cause |
|---|---|---|---|---|
| `test/unit/test_resolve.py` | 436 | no | - | `C` |
| `toolguard/compound.py` | 283 | **no - explicitly predicted AGAINST** | - | `C` |
| `test/unit/test_command_extractor_inline_code.py` | 96 | **yes** | high | hit |
| `toolguard/resolve.py` | 74 | no | - | `C` |
| `toolguard/parser/command_extractor.py` | 59 | **yes** | high | hit |
| `technical-notes.md` | 56 | no | - | `P` |
| `toolguard/config_types.py` | 13 | no | - | `C` |
| `test/verdict_corpus/goldens.jsonl` | 4 | no | - | `C` |

False positives (5, cost nothing): `command_model.py`, `test_assignment_prefix.py`, `test_ask_resolution.py`, `test_compound.py`, `test_bash_parser.py`.

**One cause accounts for 806 lines - 79% of the entire diff**: raising the floor reclassifies a leaf's `kind`, and `kind` also drives audit decomposition, so restoring the breakdown pulled in `compound.py`, `resolve.py`, `config_types.py` and a 436-line test file. Cause `C`, hidden coupling, in its purest measured form.

## Leak analysis

The ticket named the extractor and the `if`/`while` precedent in one sentence, so `command_extractor.py` is a **transcription hit**. `test_command_extractor_inline_code.py` is a weaker name-inference hit off the file inventory.

**Unleaked production recall: 0 of 806 lines.** Consistent with item 18 (unleaked 0/7) and against item 74 (the one clean unleaked call).

## NEW FINDING 13 - the uncertainty file beat the prediction file

The estimator's **second listed uncertainty** was:

> *"Whether the floor-application logic itself needs to change, versus purely receiving better input. I predicted no change to `compound.py` / `permission_resolution.py` ... but I don't know the actual call shape between extraction and floor application, so this is a real risk to the concentration set claim."*

It named the exact miss, named the exact file, named why it could not resolve it - **and then predicted against it.** This is not cause `E` (ignorance). The estimator knew precisely which question governed 79% of the diff.

That makes the uncertainties file a **better instrument than the predictions file** on this item, and it suggests a protocol change that costs nothing: when an estimator flags a binary uncertainty that would move a large fraction of the touch set, treat that flag as the estimate. The coordinator is not blinded and can resolve it by reading one call site in seconds.

Worth testing at the aggregate: score the uncertainties files retroactively across all items and ask whether flagged-uncertainty resolution outperforms the prediction it contradicts.

## Confirmations

- **`P` (prose coupling) recurs a third time.** 77 and 78 each predicted `README.md` and hit topic files under `docs/`; 79 predicted no doc file and changed `technical-notes.md` (56 lines). Still the most systematic under-prediction in the series, still small per occurrence.
- **The layer prediction was right, with the right reasoning** - that a grammar handling compound splitting must already parse substitution interiors or top-level splitting itself breaks. Third correct instance of "the grammar already knows; the Python discards it". This inference is now reliable enough to state as a project fact rather than a per-ticket bet.
