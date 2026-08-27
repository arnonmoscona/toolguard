---
title: 'session_start scans the wrong log directory: TOOLGUARD_LOG_DIR silently disables
  the conflict nag'
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/26-session-start-conflict-scan-misses-the-real-log-dir
---

**FIXED in `05f786d` (TOO-45 phase 2).** `session_start`'s conflict scan now resolves the log directory via `env_config` instead of a hardcoded wrong path — see `toolguard/session_start.py:288-293`.

> **CONFIRMED 2026-08-13, and worse than recorded. A RED test is in the tree.**
>
> **Mutating toward the fix produced 0 failures at HEAD** — the suite saw neither the bug nor its correction. So the fix could have landed, or silently regressed later, with nothing noticing.
>
> **RED test:** `test_session_start.TestDetectConflicts.test_scan_honours_the_log_directory_the_writer_actually_uses`. It carries a fixture self-guard that asserts `env_config.get_env_config(project_root)["log_dir"]` really *is* the directory the test calls "the writer's" — so a fixture mistake cannot masquerade as the defect. It goes green under the fix, and the existing project-relative tests still pass under it, so **the fix has no collateral**.
>
> **A wrinkle in the fix direction — and my first statement of it was wrong.** I wrote that `env_config.find_project_root` and `config`'s equivalent "agree by luck". **Measured over a six-fixture matrix (`.git`, `pyproject.toml`, `CLAUDE.md`, and a nested `.git`-above / `pyproject`-below layout): they cannot disagree on a resolved root.** Both wrap `path_utils.resolve_project_root(strict=True, indicators=CONFIG_ROOT_INDICATORS)` — same resolver, same indicators, same strictness.
>
> **The only divergence is the not-found case**: `env_config`'s returns `None`, `config`'s raises `RuntimeError` via `require_project_root`. So the fix is safer than I implied, and "unify the two implementations" is not a precondition for it.
>
> **What IS true and worth carrying:** each side's behaviour is pinned individually, and **the relationship between them is pinned nowhere.** No test imports both, and `require_project_root` appears in `test/` only as a patch target, never under `assertRaises`. So the *equivalence* the fix relies on is real but unguarded — a future edit to either could break it silently. One test asserting they agree would close that.
>
> The working queue's row S1 makes the same overstatement I did — *"whenever the two root-finders disagree"* — and should be corrected there too. Its `TOOLGUARD_LOG_DIR` half is the real content of that row and is accurate.

# `session_start` scans the wrong log directory

**Severity: a diagnostic that silently stops working, with no trace.** Not a permission defect -- a monitoring one.

## The defect

`toolguard/session_start.py`'s `_detect_conflicts` scans:

```python
config.project_root / "logs"
```

The hook that **writes** those logs resolves its directory through `env_config.get("log_dir")`, which honours `TOOLGUARD_LOG_DIR` **and uses a different root-finder** (`env_config.find_project_root`, reading the real process `cwd` and `TOOLGUARD_PROJECT_ROOT` -- a separate function from `toolguard.config`'s, as `.claude/rules/test-config-isolation.md` documents at length for the test-isolation case).

So: **set `TOOLGUARD_LOG_DIR` and the dynamic-conflict nag never fires again.** It does not error, does not warn, and does not report zero conflicts differently from "no conflicts exist". It scans an empty or nonexistent directory and reports nothing, indefinitely.

## How it was found, and why that matters

The divergence had exactly one trace in the codebase: a comment claiming `_detect_conflicts` used *"the same logic as the PreToolUse hook."* That comment was **false**, so the #07 sweep deleted it -- correctly, by the sweep's own rules.

**Deleting it would have removed the only surviving evidence of the divergence.** The defect was caught only because the editor verified the claim before cutting it, rather than cutting it as obvious boilerplate. Worth remembering when weighing whether verification-before-deletion is worth its cost: here it was the entire value of the pass.

## Confirmed: real gap, accurate prose

Checked during the `test_session_start.py` sweep. The divergence is real in the source, and **no Given/Then in the test file frames the project-relative scan as matching the writer** -- each describes what the code does, accurately. So this is a plain coverage gap, not a laundered claim. Nothing has to be un-taught.

No test exercises the conflict scan against the writer's actual log directory.

## Fix direction

`_detect_conflicts` should resolve its scan directory the same way the writer does -- through `env_config`, honouring `TOOLGUARD_LOG_DIR`. Two functions named `find_project_root` in two modules, disagreeing, is the underlying hazard; whether that is worth unifying is a larger question than this ticket.

Minimum: make the scan read the writer's directory. Better: make it impossible to ask for "the log directory" and get two different answers.

## Test obligation

Set `TOOLGUARD_LOG_DIR` to a temp directory, write a conflict-bearing log there, run the session-start check, assert the conflict is reported. That test fails today.

## Provenance

Found in the `session_start.py` module sweep; coverage gap confirmed in the `test_session_start.py` sweep, TOO-45 #07. `reports/follow-up-queue.md` section `SST`.
