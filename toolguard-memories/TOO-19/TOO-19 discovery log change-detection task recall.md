---
title: TOO-19 discovery log change-detection task recall
type: note
permalink: toolguard/too-19/too-19-discovery-log-change-detection-task-recall
tags:
- task-memory
- TOO-19
---

## Task
Fix log noise from the config-discovery diagnostic in `toolguard/hook.py` /
`toolguard/log_writer.py`. The module-level `_discovery_diagnostic_done` guard can never
fire because toolguard is a fresh process per PreToolUse invocation. Measured: 940/2051 log
entries on 2026-07-31 were Discovery, 868 byte-identical.

## Required design (from orchestrator prompt, verbatim intent)
1. New dedicated log `<log_dir>/toolguard-discovery.jsonl`, append-only JSONL, NOT
   date-partitioned (reasoning must go in module docstring: a dated file would re-log every
   morning, defeating the fix).
2. The JSONL log IS the state -- no separate marker file. Compute current signature (derive
   from levels list, no separate signature field), compare to last matching entry.
3. Key by project root (`env_config["project_root"]`), so a shared `TOOLGUARD_LOG_DIR` across
   projects does not flap. Compare against the most recent JSONL entry whose `project_root`
   field matches this invocation's.
4. On change (or no prior entry for this root): append JSONL record AND write the
   `**Discovery**` entry to the main dated log (byte-identical format to today's). On no
   change: write NOTHING to either log.
5. Main-log format must stay exactly:
   `- **Discovery**: discovered {count} config levels: {joined}` under `## {timestamp}`.
   `log_harvest.py` depends on this (skips no-Status sections) -- do not break its tests.
6. Delete `_discovery_diagnostic_done` global + guard from hook.py. Fix log_discovery's
   docstring (it currently falsely says "the caller is responsible for the once-per-session
   guard").
7. Suggested JSONL fields: ISO timestamp, project_root, level_count, levels list. No separate
   signature field -- derive comparison from levels list directly.

## Constraints
- Runs on every tool call -- latency matters. Read the JSONL file once, with a size guard
  (pathologically large file -> degrade to "no prior entry", don't raise).
- Diagnostic logging must never fail the hook (match log_writer.py's try/except + stderr
  warning pattern).
- No locking for the append race; duplicate lines are harmless. Comment the decision.
- Malformed/truncated final line tolerated, not a crash -- treated as no prior entry found at
  that point in the backward scan (skip and keep scanning backward for other matches).

## Tests to add/extend (test/unit/test_logging_streams.py::TestDiscoveryDiagnostic exists)
- first call writes BOTH files
- immediate identical second call writes NOTHING to either file (byte-unchanged assertion)
- different levels -> writes to both again
- changing back to a previously-seen value still logs (compare against LAST entry only, not
  whole history)
- two project roots sharing one log dir: A,B,A,B logs each time; A,A does not
- corrupt/truncated final line tolerated, treated as no prior entry
- main-log entry format unchanged -- exact string assertion
- log_harvest existing tests still pass (skips Discovery sections)

## Verification checklist
- Full unittest suite with isolated HOME/XDG_CONFIG_HOME, baseline 2004 tests, must stay OK
  (count will grow with new tests).
- `uv run ruff check .` and `uv run ruff format --check .` clean.
- End-to-end demo via `toolguard.testing.sandbox.run_hook` (isolated TOOLGUARD_LOG_DIR),
  invoke several times with unchanged config, show discovery-entry count 1 not N.
- Confirm /home/arnon/projects/toolguard/logs/ untouched -- report entry count before/after.

## Investigation notes (coder's own findings)
- `log_writer.py::log_command` jsonlines branch has a local `import json` -- violates the
  project's no-local-imports rule. In scope to fix since I'm editing this file anyway (moving
  to top-level import).
- `env_config["project_root"]` (from `toolguard/env_config.py::get_env_config`) is exactly the
  project-root value to key by -- already computed by the hook's existing `get_env_config()`
  call, no new resolution needed.
- `log_discovery` is called ONLY from `hook.py` (one call site) and from
  `test_logging_streams.py::TestDiscoveryDiagnostic` (one test, needs updating for new
  signature: add `project_root` positional arg).
- `toolguard.testing.sandbox.run_hook` runs the hook as a real subprocess with
  `TOOLGUARD_LOG_DIR` set to a sandbox-local temp dir -- ideal for the end-to-end demo without
  touching real logs.

## Report location
basic-memory project `toolguard`, path
`TOO-19/TOO-19 discovery log change-detection implementation report.md`, tags
`task-memory`, `TOO-19`.
