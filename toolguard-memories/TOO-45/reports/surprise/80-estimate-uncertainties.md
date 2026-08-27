---
title: 80-estimate-uncertainties
type: note
tags:
- TOO-45
- surprise-measurement
permalink: toolguard/too-45/reports/surprise/80-estimate-uncertainties
---

# Named uncertainties — ticket 80 prediction

Ordered by how much a single observation would move the prediction.

## 1. Where the 17 sites actually live — the largest single source of error

The ticket gives a **count** and no distribution. My module list for the migration half is inference from docstrings alone, and the distribution is the thing that decides the production count. Two failure shapes, in opposite directions:

- **Clustered**: if 12 of the 17 sit in `config.py`, `path_utils.py` and `normalization.py` — plausible, since those are the path-heavy modules and path code tends to funnel — then my production count of 12 is roughly double the truth and most of my `medium`/`low` production rows are false positives.
- **Scattered**: if the sites are one-per-module across the `tools/` package (installer, config_access, replay, log_harvest, working_tree, migration_gate, …), the count could be 20+ and I will have missed most of them, because I only named the `tools/` modules whose docstrings mention paths explicitly.

**What would resolve it:** a per-file count of relative `Path(...).resolve()` and `.absolute()` calls. One `grep -c` per module is the whole answer.

I lean clustered, which means my most likely quantitative error is **over-prediction of production modified**.

## 2. Whether the checker is a new mode or a new tool

I placed the AST check inside `tools/architecture_fitness.py` because the ticket says it "rides on the import graph `--layers` already walks" — that phrasing points at an existing walker. But `architecture_fitness.py` is already 4002 lines with 4175 lines of tests, and this campaign has repeatedly split large modules. If the check lands as a **new** `tools/stdlib_surface_check.py` (or similar) plus a **new** `test/unit/test_stdlib_surface_check.py`, my production-added and test-added counts are both short by one, and `test/unit/test_architecture_fitness.py` becomes a false positive.

**What would resolve it:** the CLI surface of `architecture_fitness.py` — whether its modes are pluggable or hardcoded, and whether the repo has a convention of one instrument per concern.

This is the uncertainty I would most like removed, because it is worth up to four files and it is binary.

## 3. Whether the `os` import ban is enforced-and-fixed, or enforced-with-a-whitelist

The ticket says `os` outside the facade is "a short nameable whitelist" (`os.replace`, `os.fsync`). Two readings:

- **Whitelist in the checker**: the banned-import rule carries an exemption table, and *no production module changes* for the `os` half. Cheap.
- **Ban and migrate**: `import os` genuinely disappears from non-facade modules, and every file-op site moves behind some new seam. That would pull in `file_lock.py`, `once_per_store.py`, `log_writer.py`, `rule_sort.py`, `config.py`, `config_write_guard.py` and more — and would blow my production count well past 16.

I predicted the first reading. If it is the second, this is my single biggest recall miss, and the missed files are exactly the atomic-write modules (`file_lock`, `once_per_store`, `rule_sort`) which I named nowhere.

**What would resolve it:** whether the ticket's authors intend `os` to be reachable at all outside `ambient` — and how many modules currently do `import os` for a genuine file operation. A count of `import os` across `toolguard/` decides it.

## 4. The `expanduser` blast radius

I know the move happens; I do not know how many callers `ambient.expanduser()` has. Ticket 44 introduced it recently, which cuts both ways: a fresh accessor could have two callers, or the ticket-44 migration could have routed a dozen sites through it. If it has many callers, my `medium`-confidence production rows (`env_config`, `log_writer`, `config`) are right for the wrong reason, and I have probably missed several `tools/` modules that expand `~` in user-supplied config paths.

## 5. Whether `test_path_utils.py` already exists under another name

My most interesting non-obvious prediction is the **addition** of `test/unit/test_path_utils.py`, resting entirely on its absence from the inventory. But `path_utils` primitives are re-exported by `tools/project_root.py`, and `test/unit/test_tools_project_root.py` exists at 488 lines — so path_utils may already be tested *through* that module. If so, the expanduser tests will land there instead and my test-added count of 1 goes to 0.

This is a case where the inventory's shape misled me in a specific, checkable way: absence of a test file is not absence of test coverage when a re-export module exists.

## 6. Whether the two guard tests share a file

I split them: enumeration guard and version pin both into `test/unit/test_architecture.py`. They could equally be one new module, since the version pin is not an *architecture* invariant — it is a stdlib-assumption invariant, and this campaign has been careful about exactly that kind of conflation (see the layer map's own note about "entry points AND side-effecting concerns"). If the authors apply that same discipline here, a new test module appears and `test_architecture.py` may not be touched at all.

## 7. Whether `Path.absolute()` adds sites I have not counted

The ticket adds `absolute()` to scope *after* the 17 were measured, and says it appeared in no prior route table. So the 17 is a floor, not a total, and I have no basis at all for estimating the `absolute()` count. It could be zero (it is a rarely-used method) or it could be several. I assumed near-zero, which is a guess, not an inference.

## 8. Documentation

I gave the doc files `low` and excluded them from the counts. The ticket calls the route table "the durable artifact" and says to extend it rather than rediscover it — which is an instruction to write it down somewhere. If this project's convention is to land that in `technical-notes.md` or `docs/`, and if `docs/agent-map.md` then needs syncing, that is 1–3 non-Python files I under-weighted.

## What I think I am most likely to be wrong about, in one line

**The production modified count, on the high side, because I distributed the 17 sites across modules by docstring plausibility when path code almost certainly funnels through three or four modules** — with the compensating risk that the `os`-import ban is enforced literally rather than whitelisted, which would push the true count far above even my estimate. Those two errors point in opposite directions, so the count could look accidentally correct while both component judgements are wrong; the per-file recall/precision is the honest read, not the total.
