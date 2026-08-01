---
title: TOO-19 Coder Task Recall - test log-dir isolation leak fix
type: note
permalink: toolguard/too-19/too-19-coder-task-recall-test-log-dir-isolation-leak-fix
---

tags: task-memory, TOO-19

## Task
Repo: /home/arnon/projects/toolguard (branch too-19). Test-isolation defect: the unit suite
writes into the developer's REAL log directory (/home/arnon/projects/toolguard/logs/).

## The defect (measured by requester)
Running the suite appends real entries to logs/toolguard-<today>.md. Measured delta of 5
discovery entries per full-suite run, with test-fixture content leaking (e.g. `/fake/0/...`,
`/tmp/tmpXXXX/...` paths).

Attribution given (partial, must verify and find the rest):
- test.unit.test_hook -> 3
- test.unit.test_hook_eval -> 1
- (at least one more elsewhere, total was 5)

Root cause: log_dir defaults to <project_root>/logs (env_config.py ~line 203). Tests that
exercise hook/main() path without overriding TOOLGUARD_LOG_DIR resolve find_project_root()
from real cwd -> write to real repo logs/.

History: hook.py used to have `_discovery_diagnostic_done` module global suppressing all but
first discovery write per process. Removed correctly (production runs per-process so guard
was dead code); removal revealed pre-existing leak (1->5 writes in long-lived test process).
DO NOT restore the guard.

## Required work
1. Find every leaking test (not just the 4 attributed). Method: run each test module with
   HOME, XDG_CONFIG_HOME, TOOLGUARD_LOG_DIR pointed at temp dirs; inspect temp log dir after.
   Check ALL log streams: log_command, conflict logs, crash reports - not just discovery.
2. Fix isolation at the right level:
   - Extend isolate_config_environment() in test/unit/_config_isolation.py (ConfigIsolationMixin)
     to ALSO isolate TOOLGUARD_LOG_DIR into the temp tree; return/expose that path.
   - Retrofit leaking tests to use it.
   - Update .claude/rules/test-config-isolation.md to document new behavior + checklist item.
3. Add structural regression guard:
   - A test that FAILS if the suite writes to the real project logs dir.
   - Must be reliable, not depend on machine state.
   - Verify it actually fails: temporarily reintroduce a leak, confirm guard fails, restore,
     report the observed failure output.

## Verification required
- TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX" -- must report OK. Baseline 2010 tests.
- uv run ruff check . and uv run ruff format --check . both clean.
- Headline proof: count discovery entries in logs/toolguard-<today>.md before/after FULL
  suite run, delta must be 0.
  BASELINE MEASURED (read-only, before any test run): grep -c '\*\*Discovery\*\*'
  logs/toolguard-2026-07-31.md = 1001 lines (2026-07-31).

## Report
basic-memory project toolguard, path TOO-19/TOO-19 test log-dir isolation leak - fix report.md
tagged task-memory, TOO-19. Must include: full list of leaking tests found, other log streams
affected, guard design + verification it fails when leak returns, delta-0 proof.

## Hard constraints
- Never bare python/python3 -- always uv run python.
- Never edit anything outside this repo.
- No git write operations.
- Do NOT edit/prune/delete any file under logs/ -- Arnon's live data. Read-only access fine.
- unittest not pytest. BDD Given/When/Then docstrings. No function-level imports. Docstring on
  every function/class.
