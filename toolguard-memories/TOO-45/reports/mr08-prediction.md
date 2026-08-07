---
title: TOO-45 MR-08 blind prediction
type: note
permalink: toolguard/too-45/reports/mr08-prediction
tags:
- task-memory
- TOO-45
- canary
---

# MR-08 blind prediction: `TOOLGUARD_LOG_FORMAT`

## What I read, and what I did not

I read exactly three things: the output of `tools/touch_set_inventory.py --tree /var/tmp/tg-pristine-P1`, the same for `/var/tmp/tg-pristine-P2`, and a handful of documentation sections **from the working repo at `/home/arnon/projects/toolguard`** (`docs/configuration.md` around the environment-variable table, `docs/architecture.md` around the resolution-log format section, and greps for `TOOLGUARD_LOG`/`jsonl`/`log_format` across `docs/`, `README.md`, `llms.txt`, `AGENTS.md`, `technical-notes.md`).

I did not open, grep, glob or read a single `.py` file in either pristine tree; I did not read either tree's docs, tests, `toolguard-memories/`, release notes or config files; I ran no `git log`, `git diff` or `git blame` anywhere; and I did not modify anything in either tree. The only commands pointed at the pristine trees were `touch_set_inventory.py --tree ...` and `touch_set_inventory.py --tree ... --validate-predictions ...`.

**Probe disclosure.** The task requires validating the predictions files, and that validation is itself a name probe. My answers were fixed and written to `/var/tmp/mr08-P1-predictions.json` and `/var/tmp/mr08-P2-predictions.json` *before* any validation ran, and validation changed nothing: every Python location I named was reported valid in its tree (7/7 in P1, 8/8 in P2). The only "invalid" rows were `docs/configuration.md` and `docs/architecture.md`, which the validator flags because it indexes `.py` files only — I kept both, because the acceptance criterion explicitly demands the documented environment-variable table. I did not run any additional constant-name probe, so nothing about module-level constants entered my reasoning. One incidental note: the validator rejects the `{"entries": [...]}` envelope the task specifies and demands a bare top-level array, so I validated array-form copies in my scratchpad while leaving the deliverables in the requested shape.

## The one documentation fact that dominated this prediction

`docs/architecture.md` in the working repo says, in so many words, that `log_writer` can already emit JSONLines "via an internal `log_format` parameter", that every production caller uses markdown, that the old selector (`CHECKED_BASH_LOGGING_FORMAT`) was removed in TOO-19, and that the renderer is retained so that "a future `TOOLGUARD_LOG_FORMAT` setting can expose them deliberately". That is the requirement, pre-written, naming the variable. If the pristine trees carry the same paragraph — and both inventories show a `log_writer.py` with a single public `log_command` writer, so structurally they should — then MR-08 is not a design problem in either tree. It is: resolve a new value in `env_config.get_env_config`, feed it to the parameter that already exists on `log_command`, and rewrite the paragraph that says you can't.

## Predictions

Both files are in the requested `{"entries": [...]}` shape.

### P1 — `/var/tmp/mr08-P1-predictions.json` (9 locations)

| location | kind |
|---|---|
| `toolguard/env_config.py::get_env_config` | parse_validate |
| `toolguard/env_config.py::get_bool_env` | parse_validate |
| `toolguard/log_writer.py::log_command` | decide |
| `toolguard/hook.py::_log_allowed_command` | transport |
| `docs/configuration.md` | display |
| `docs/architecture.md` | display |
| `test/unit/test_env_config.py::TestGetEnvConfig` | test |
| `test/unit/test_log_writer.py::TestLogging` | test |
| `test/unit/test_log_writer.py::TestLogFormatGoldenFile` | test |

### P2 — `/var/tmp/mr08-P2-predictions.json` (10 locations)

Same nine, plus `toolguard/log_writer.py::LogRecord` (transport). P2's `log_writer` exposes a public `LogRecord` — "the fields of a single resolution-log entry, in one value" — which P1 does not have. If the two renderers are expressed as serialisers over that record, the JSONLines path is reached through it and it is the plausible carrier of a format-agnostic accessor; P1 has no such value type, so its renderers must consume the parameter list directly.

### Were they predicted independently, and why they overlap

Yes, independently, and they came out nearly identical — because the two inventories genuinely say the same thing about this requirement's surface. `env_config.py` is byte-for-byte the same size in both (212 lines) with the same four public symbols in the same order; `log_writer.py` is 676 lines in P1 and 671 in P2 with the same two public functions plus P2's `LogRecord`; `hook.py`'s public surface is identical and both trees' `test_hook.py` still contains `TestLogAllowedCommand`. P2's large structural differences — `api.py`, `permission_resolution.py`, `install_update.py`, `permission_migration.py`, the collapse of `resolve.py`'s `BashResolution`/`FileResolution` into `config_types.RuntimeVerdict`, `tools/architecture_fitness.py` — are all upstream of the logging boundary and none of them touch which stream gets written in which format. The single MR-08-relevant divergence is `LogRecord`, and it is the one entry that differs.

## Confidence

**P1: high (about 0.85) for the two code locations, moderate for the rest.** `env_config.get_env_config` is the only symbol in either tree whose self-description claims to load *all* configuration from environment variables and `.env`; `log_writer.log_command` is the only public writer of the resolution stream. Neither required inference. What I am less sure of is `get_bool_env` (an enum-valued variable may get a new sibling helper rather than an edit to this one — I named it because that is where the "unrecognised value falls back to the default" convention is enforced today, and either a change or a neighbouring addition lands at that spot) and `hook.py::_log_allowed_command`, which changes only under a threading design.

**P2: high (about 0.85), essentially the same, with one extra unknown.** The `LogRecord` entry is the deliberate speculation: I would rate it about 50/50, and it is the only entry I would expect a scorer to charge me for as a false positive in P2 but not P1.

**Which inventory made it easier to locate?** Effectively a tie, with a slight edge to **P2**. Both point at the same two functions with no ambiguity, so neither is harder. P2 is marginally more informative because `LogRecord` tells me, without reading code, that a resolution-log entry is a single value in that tree — which is exactly the fact that answers this requirement's cost question (it makes a per-call-site format hardcode structurally unlikely). P1's inventory is silent on that; I had to infer centralisation from "there is only one public writer", which is weaker evidence. The inventory's known blind spot — module-level constants — cost me nothing here, because the natural home for a `("markdown", "jsonlines")` tuple is inside whichever function I already named.

## Surprises, and one self-description that could point a reader wrong

The genuine surprise was not in the inventories but in the docs: the requirement's variable name is already written into `docs/architecture.md` as a planned future setting. That converts a "where does this belong?" question into a "do what the doc already promised" question, and it is worth flagging for the measurement, because it means MR-08 is an unusually *easy* instance for anyone who reads documentation before code — and the inventory alone would not have handed me the name `log_format` for the existing parameter.

Two self-descriptions could mislead a reader here. First, `toolguard/error_log.py` describes itself as "Error, warning, conflict, **and crash** logging" — a reader skimming for "logging" may land there first and start adding a format switch to the wrong module; the requirement's carve-out ("the error, warning and conflict streams stay as they are") is precisely a fence around that file, and the inventory gives no hint that the resolution stream lives elsewhere except by the process of elimination that `log_writer.log_command` exists. Second, `toolguard/tools/log_harvest.py::parse_log_file` is described as parsing "a single daily log file" — i.e. it is a *reader* of the exact stream MR-08 reformats. I deliberately did **not** predict it, because the requirement says nothing about round-tripping and acceptance does not test it, but a JSONLines-configured installation silently breaks corpus harvesting, mining, replay and the maintenance skill downstream of it. If the actual implementation does touch `log_harvest`, that is a recall miss I am taking knowingly, and it is the most interesting thing about this requirement that the acceptance criteria do not mention. The same caveat applies more weakly to `toolguard/testing/sandbox.py`, which isolates the config/log environment and may need to neutralise a new variable.

## How many places write a resolution log entry?

Answered before seeing any implementation.

**One, in both trees — plus a small number of call sites into it.** Concretely: I expect exactly **one** function that formats and writes a resolution entry (`log_writer.log_command`) in each tree, reached from an estimated **2 to 4** call sites in `hook.py` — an allow/EXECUTED path through `_log_allowed_command`, at least one deny/ask path, and (given both trees' `hook.py` separates the Bash path from the Read/Write/Edit path, which P2's `TestHandleCommandToolAuditWiring` / `TestHandleFilePathToolAuditWiring` names outright) plausibly one per tool family. My central estimate is **3 call sites in P1 and 2–3 in P2**.

So the failure mode the question anticipates — the command path, the file-path path, the compound sub-command path and a fallback path each hardcoding the format, with one path quietly ignoring the setting — **should not occur in either tree**, for a structural reason rather than a lucky one: the format is already a parameter of the writer, not a decision made by the callers. Every caller passes facts; exactly one function turns facts into bytes. The compound case reinforces this: a compound command produces one entry with per-sub-command detail folded into it, not one entry per sub-command, so there is no fourth writer hiding in `compound.py`.

The one place I would look for an inconsistency is the `--eval` path (`hook_eval`'s `_resolve_event`), which is documented as side-effect-free and must therefore *not* start emitting JSONLines or anything else; and, in P2, `config_divergence`, whose `DivergenceCheckResult` and the `TestDivergenceWarningLogging` test say it stopped writing its own log entries — a change that, if anything, reduces the number of writers in P2 relative to P1. Neither is a resolution-stream writer.

## Does environment configuration have a natural home?

**Yes for this variable, in both trees, and it is the same home.** `env_config.get_env_config` is a single resolver that returns one object holding every `TOOLGUARD_*` value, and the documented table in `docs/configuration.md` reads as a one-to-one listing of its keys (`TOOLGUARD_LOGGING_ENABLED`, `TOOLGUARD_LOG_DIR`, `TOOLGUARD_EXTENDED_SYNTAX`, `TOOLGUARD_PROJECT_ROOT`, `TOOLGUARD_SOURCE_ROOT`, `TOOLGUARD_CREATE_LOG_DIR`). A new logging-family variable slots straight in, with `get_bool_env` sitting right there as the precedent for case-insensitive coercion with a default. That is as clean a home as this requirement could ask for, and it is why I rate the core prediction high in both trees.

The picture is only tidy for the `TOOLGUARD_*` family, though. The same documented table also lists `CLAUDE_SETTINGS_PATH` and `XDG_CONFIG_HOME`, and neither of those can plausibly be resolved by `env_config` — the first drives single-file config discovery and the second drives the split rules directory, both of which live in `config.py`, and both trees' test inventories confirm direct-lookup behaviour there (`TestExplicitModeAdjacentToml`, `TestRulesDirectoryExplicitModeBypass`, `TestSettingsPathOverrideWarning`, `TestMigrationIgnoresEnvOverride`). `TOOLGUARD_LOG_DIR` is also read directly enough that both trees carry dedicated test-isolation machinery for it (`_config_isolation.isolate_log_dir_for_module`, plus module-level `setUpModule` redirects in `test_hook.py` and `test_hook_eval.py`). So the honest characterisation is **hybrid, and identically hybrid in both trees**: one resolved object for the logging/pattern family, scattered direct `os.environ` lookups for the discovery family, and a documentation table that presents both as one thing. MR-08 lands squarely in the well-homed half — which is fortunate, and not something the requirement's author had to arrange.
