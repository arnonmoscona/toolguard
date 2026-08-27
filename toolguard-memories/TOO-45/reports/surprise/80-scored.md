---
title: TOO-45 surprise factor - ticket 80 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/80-scored
---

# Ticket 80 scored (`Path.resolve()` is a fifth route to cwd)

Actual set from `git diff --numstat 6242e6d..0f7066f`. **Primitives only.**

## Actual — production (9 files)

| file | +/- | predicted? | confidence given |
|---|---|---|---|
| `tools/architecture_fitness.py` | 518/7 | yes | high (named as the centre) |
| `toolguard/path_utils.py` | 44/8 | yes | high |
| `toolguard/ambient.py` | 6/14 | yes | high |
| `toolguard/env_config.py` | 13/8 | yes | medium |
| `toolguard/install_provenance.py` | 3/2 | yes | medium |
| `toolguard/tools/decision_ledger.py` | 17/7 | **no — surprise** | — |
| `toolguard/auto_migrate.py` | 3/2 | **no — surprise** | — |
| `toolguard/tools/environment_audit.py` | 2/2 | **no — surprise** | — |
| `toolguard/tools/security_audit.py` | 2/2 | **no — surprise** | — |

Predicted-production not touched (13), including three at **high** confidence: `config.py` (high), `normalization.py` (high), `file_matching.py`, `log_writer.py`, `hook.py`, `config_write_guard.py`, `testing/sandbox.py`, `tools/installer.py`, `tools/config_access.py`, `tools/working_tree.py`, `session_start.py`, `tools/project_root.py`, `tools/comment_hygiene.py`.

## Actual — test (7 files)

| file | +/- | predicted? | confidence |
|---|---|---|---|
| `test/unit/test_architecture_fitness.py` | 335/1 | yes | high |
| `test/unit/test_architecture.py` | 88/3 | yes | high |
| `test/unit/test_ambient.py` | 75/44 | yes | high |
| `test/unit/test_path_utils.py` (**new**) | 70/0 | **yes, as ADDED** | medium |
| `test/unit/test_env_config.py` | 50/0 | yes | medium |
| `test/unit/test_tools_decision_ledger.py` | 9/9 | **no — surprise** | — |
| `test/unit/test_tools_maintenance.py` | 5/7 | **no — surprise** | — |

## Actual — other (2 files)

`CLAUDE.md` 5/0 — not predicted. `docs/diagram-path-test.md` 0/53 (deleted) — not predicted, and unrelated housekeeping swept in (see the git-mechanics note in the resume file).

## Surprises by cause — 6 production+test, plus 2 other

| file | cause | evidence |
|---|---|---|
| `toolguard/tools/decision_ledger.py` | E | an unowned `resolve()` site; membership was discoverable only by running the checker, which is what the ticket built |
| `toolguard/auto_migrate.py` | E | as above |
| `toolguard/tools/environment_audit.py` | E | as above |
| `toolguard/tools/security_audit.py` | E | as above |
| `test/unit/test_tools_decision_ledger.py` | E | follows its module |
| `test/unit/test_tools_maintenance.py` | E | follows its module |
| `CLAUDE.md` | S | pre-push checklist entry for the new `--ambient` mode; a coordinator addition beyond the ticket |
| `docs/diagram-path-test.md` | S | unrelated deletion swept into the commit by a plain `git commit`; a process defect, already recorded |

**0 alarms.** All six substantive surprises are `E`.

## THE RESULT THAT MATTERS: the estimator predicted the wrong tier with high confidence

It named the **heavy path-handling modules** — `config.py` and `normalization.py` at *high* confidence, plus `file_matching`, `log_writer`, `hook`, `config_write_guard`, `installer`. None were touched. The actual unowned sites were in the **tools tier**: `decision_ledger`, `environment_audit`, `security_audit`, `auto_migrate`.

The reasoning was sound and the answer was wrong, for a reason worth keeping: **the heavy path modules already had owner entries.** They are where path work visibly lives, so they had already been examined in tickets 44 and 80's predecessors. What was left unowned was the tier nobody thinks of as path-handling code. That is the same shape as the campaign's recurring finding — the residue is wherever the previous instrument was not pointed.

## The single strongest positive result in the series so far

**`test/unit/test_path_utils.py` was predicted as a NEW file and created.** The estimator reasoned from the inventory that a 318-line `path_utils` module had no dedicated test module, and that relocated `expanduser` tests would need a home. That is genuine foresight — it cannot be transcription, because the file did not exist to transcribe. It is the concrete precedent for the analogous prediction pre-registered for ticket 82 (`claude_code_contract.py`).

## Comparison to ticket 77, scored the same day

| | 77 | 80 |
|---|---|---|
| design leaked to estimator | **yes, deliberately** | no |
| production recall | 9/9 | 5/9 |
| production surprises | 0 | 4 |
| alarms | 1 (`P`) | 0 |

Two points do not make a trend, but the confound is now measured: **the item where the design was given had perfect production recall, the item where it was not had 56%.** The aggregate must control for design leak separately from file leak — they are different exposures and this series has both.
