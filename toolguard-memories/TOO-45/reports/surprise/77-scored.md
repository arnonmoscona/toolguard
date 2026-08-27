---
title: TOO-45 surprise factor - ticket 77 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/77-scored
---

# Ticket 77 scored (leading env assignment evades a deny rule)

Actual set from `git diff --numstat 0f7066f..1dfda8e`. **Primitives only** — every metric is derived at analysis time.

## Actual — production (9 files)

| file | +/- | predicted? | confidence given |
|---|---|---|---|
| `toolguard/config.py` | 82/0 | yes | high |
| `toolguard/config_types.py` | 36/1 | yes | high |
| `toolguard/parser/bash_parser.peg` | 39/7 | yes | medium |
| `toolguard/parser/bash_parser.py` | 507/67 | yes | medium |
| `toolguard/parser/command_extractor.py` | 65/1 | yes | medium |
| `toolguard/parser/command_model.py` | 75/32 | yes | low |
| `toolguard/permission_resolution.py` | 9/0 | yes | high |
| `toolguard/permissions.py` | 79/19 | yes | high |
| `toolguard/resolve.py` | 9/2 | yes | medium |

**Production hits 9 of 9.** Zero production surprises.

Predicted-production not touched (8): `compound.py`, `constants.py`, `config_validation.py`, `hook.py`, `README.md`, `technical-notes.md`, `pyproject.toml`, `env_prefix.py` (new).

## Actual — test (2 files)

| file | +/- | predicted? | note |
|---|---|---|---|
| `test/unit/test_assignment_prefix.py` (**new**) | 490/0 | **concept yes, path no** | estimator predicted a new file `test/unit/test_env_prefix.py` for exactly this primitive |
| `test/unit/test_hook.py` | 3/0 | yes | low |

Predicted-test not touched (10): `test_permissions.py`, `test_configuration.py`, `test_compound.py`, `test_hard_deny.py`, `test_ask_resolution.py`, `test_permission_resolution.py`, `test_toml_config.py`, `test_bash_parser.py`, `test_api.py`, `test_resolve.py`.

**Score the new-file case both ways and keep both**, since collapsing it destroys the distinction: strict path-match = miss; concept-match = hit. The estimator predicted that a new focused module would be created for the strip/variant primitive, and one was — under a different name.

## Actual — docs (4 files), all surprises

| file | +/- | cause | evidence |
|---|---|---|---|
| `docs/agent-map.md` | 53/21 | **P** | Changed *because other docs changed*, not because code did. `CLAUDE.md` states it "summarizes every other doc with no other mechanism keeping it in sync, so it is the most likely thing to go stale silently." A documented prose coupling with no enforcement. |
| `docs/configuration.md` | 43/14 | E | estimator named `README.md` as the home of configurable-key documentation; this project keeps it here |
| `docs/permission-patterns.md` | 25/4 | E | estimator did not know this file exists |
| `docs/native-pattern-reference.md` | 7/1 | E | as above |

## Surprises by cause

**1 alarm (`P`), 3 `E`.** The alarm is `docs/agent-map.md` and it is a real architectural finding: a hand-maintained index of every other document, with the project's own guidance already naming it as the most likely thing to go stale. It is a prose analogue of the very defect this campaign keeps finding in code — a derived artifact re-derived by hand.

## Two findings that generalise beyond this ticket

**1. Design leak buys production recall.** 77's chosen design was deliberately given to the estimator (the ticket listed three candidate directions and Arnon picked a fourth). Production recall came out **9/9**. Compare ticket 80, scored the same day with no design leak: **5/9**. One pair is not evidence, but it is the confound the aggregate must control for, and it is now measured rather than hypothesised.

**2. Test-side precision is structurally low, and the cause is a project convention.** The estimator distributed predicted tests across ten existing suites by subject. The implementation put **490 of 493 new test lines in one new module**. This project adds a dedicated test module per feature rather than amending existing suites — so any estimator reasoning "tests change where the code changes" will over-predict test files systematically. **This is a property of the codebase, not an estimator error**, and scoring it as `E` would mislabel it. Recommend the aggregate treat test-file identity separately from test-file count.
