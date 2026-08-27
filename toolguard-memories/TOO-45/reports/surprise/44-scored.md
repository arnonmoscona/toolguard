---
title: TOO-45 surprise factor - ticket 44 scored
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/44-scored
---

# Ticket 44 — scored. Primitives first; every metric below is derived from them.

Estimate written blind and unread until implementation was complete and green. Estimator declared it read exactly the two permitted files.

## Primitives — production

**Actual, from `git status` (13 modified counting `.pyscn.toml`, which the estimator counted as production; 1 added):** `config.py`, `env_config.py`, `error_log.py`, `hook.py`, `install_update.py`, `normalization.py`, `once_per_store.py`, `path_utils.py`, `permission_migration.py`, `session_start.py`, `tools/installer.py`, `tools/transcript_harvest.py`, `.pyscn.toml`; **added** `toolguard/ambient.py`.

| file | predicted | confidence | actual | leak (ticket named it) |
|---|---|---|---|---|
| `path_utils.py` | yes | high | **hit** | **YES** |
| `env_config.py` | yes | high | hit | no |
| `hook.py` | yes | high | hit | no |
| `config.py` | yes | high | hit | no |
| `session_start.py` | yes | high | hit | no |
| `once_per_store.py` | yes | medium | hit | no |
| `error_log.py` | yes | medium | hit | no |
| `install_update.py` | yes | medium | hit | no |
| `tools/installer.py` | yes | medium | hit | no |
| `.pyscn.toml` | yes | medium | hit | no |
| `error_reporter.py` | yes | high | overshoot | no |
| `log_writer.py` | yes | high | overshoot | no |
| `auto_migrate.py` | yes | medium | overshoot | no |
| `install_provenance.py` | yes | medium | overshoot | no |
| `config_divergence.py` | yes | low | overshoot | no |
| `subagent.py` | yes | low | overshoot | no |
| `testing/sandbox.py` | yes | low | overshoot | no |
| `testability.py` (add) | yes | medium | overshoot | **YES** |
| `normalization.py` | no | — | **surprise** | no |
| `permission_migration.py` | no | — | **surprise** | no |
| `tools/transcript_harvest.py` | no | — | **surprise** | no |
| `ambient.py` (add) | no | — | **surprise** | no |

## Primitives — test

**Actual (3 modified, 1 added):** `test_architecture.py`, `test_error_log.py`, `test_hook_error_reporter.py`; **added** `test/unit/test_ambient.py`.

| file | predicted | confidence | actual |
|---|---|---|---|
| `test_hook_error_reporter.py` | yes | medium | **hit** |
| `test_architecture.py` | yes | medium | hit |
| `test_hook.py` | yes | high | overshoot |
| `test_error_reporter.py` | yes | high | overshoot |
| `test_env_config.py` | yes | high | overshoot |
| `test_configuration.py` | yes | high | overshoot |
| `test_auto_migrate.py` | yes | high | overshoot |
| `test_config.py` | yes | medium | overshoot |
| `test_session_start.py` | yes | medium | overshoot |
| `test_log_writer.py` | yes | medium | overshoot |
| `test_hook_eval.py` | yes | medium | overshoot |
| `test_once_per_store.py` | yes | medium | overshoot |
| `_config_isolation.py` | yes | medium | overshoot |
| `test_hierarchical.py` | yes | low | overshoot |
| `test_sandbox.py` | yes | low | overshoot |
| `test_install_provenance.py` | yes | low | overshoot |
| `test_path_utils.py` (add) | yes | medium | overshoot |
| `test_testability.py` (add) | yes | low | overshoot |
| `test_error_log.py` | no | — | **surprise** |
| `test_ambient.py` (add) | no | — | **surprise** |

## Each surprise, with its cause and evidence

| file | cause | evidence |
|---|---|---|
| `normalization.py` | **E** | reads home to collapse `~`; the briefing gives one docstring line and no import graph, so nothing in it could reveal the read |
| `permission_migration.py` | **E** | same — an ambient read invisible to a path/docstring inventory |
| `tools/transcript_harvest.py` | **E** | a **near miss, not a blind spot**: the estimator predicted `subagent.py` for exactly this reason ("transcript lookup under `~/.claude/projects`"). Right concept, wrong module |
| `ambient.py` (add) | **E** | the ticket reserved the name `testability.py`; the implementer created `ambient.py` instead. A naming choice, not a coupling fact |
| `test_error_log.py` | **E** | follows the production change to `error_log.py`, which *was* predicted; the estimator paired that production file with the wrong test |
| `test_ambient.py` (add) | **E** | consequence of the naming choice above |

**Alarms (`C` hidden coupling, `P` prose coupling, `D` latent defect): ZERO.** Every surprise is estimator ignorance.

## Derived metrics — recomputable from the primitives above under any future rule

| | production | test |
|---|---|---|
| |P| | 18 | 18 |
| |A| | 14 | 4 |
| hits | 10 | 2 |
| **recall** | **71%** | **50%** |
| precision | 56% | 11% |
| leak-discounted recall | **69%** (9/13) | 50% (unchanged; no test file was named) |

## What this item says, kept separate from what the series will say

**The estimator was far better on production than on test, and wrong in an interesting direction.** It named 18 test files; 4 changed. It assumed a refactor touching a dozen production modules would ripple through the suite — and it did not, because the refactor was behaviour-preserving: existing `patch.object(Path, "home")` and `patch.dict(os.environ)` calls still work, since an accessor with nothing bound falls through to the live call. **That is a property of the design, and arguably the most useful thing this measurement surfaced** — the suite was better insulated from a foundation change than a competent reader would predict.

**Zero alarms is itself worth watching.** The protocol's abandon gate says that if, after three items, every surprise classifies as `E`, the briefing is too thin to support the measure. This is item 1 of the phase-3 series. One item proves nothing; three would.

**A cheap briefing change is already implied**, and should be decided from the tuning subset rather than adopted now: three of six surprises were ambient reads invisible to a path/docstring inventory. Adding a per-module list of stdlib call sites — `Path.home`, `os.environ`, `Path.cwd` — would have converted all three to hits. Whether that is a fairer "lazy human" baseline or simply feeding the estimator the answer is exactly the kind of question the ablation is for.