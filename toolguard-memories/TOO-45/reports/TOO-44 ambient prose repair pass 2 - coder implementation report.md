---
title: TOO-44 ambient prose repair pass 2 - coder implementation report
type: note
permalink: toolguard/too-45/reports/too-44-ambient-prose-repair-pass-2-coder-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

# TOO-44 ambient prose repair pass 2 -- implementation report

Prose-only repair pass answering a blinded review's FAIL. 11 edits across 9 files, no behaviour change except one user-facing error message (B2). **Nothing committed.**

## Verification (all green)

| Check | Baseline | After |
|---|---|---|
| `unittest discover -s test -t .` | Ran 3677, OK (expected failures=4) | Ran 3677, OK (expected failures=4) |
| `ruff format .` | -- | 177 files left unchanged |
| `ruff check .` | -- | All checks passed |
| `architecture_fitness.py --mocks` | 1 finding | 1 finding (same one) |

## Findings addressed

- **B1** `test/unit/test_hook_error_reporter.py:83-86` -- deleted "Measured: 2 files per run" and "accumulated 1,622". Mechanism sentence kept.
- **B2** `toolguard/path_utils.py:313-315` -- message now derives the marker list from `CONFIG_ROOT_INDICATORS`. Verified by triggering the real failure path: `Project root not found. Searched from /tmp/.../a/b upward for any of: .git, .hg, .jj, .claude, CLAUDE.md, pyproject.toml. Something is badly wrong.`
- **B3** `toolguard/hook.py:1241` -- adopted verbatim.
- **B4** `test/unit/test_ambient.py:2-3`, **B5** `toolguard/ambient.py:5`, **B7** `error_log.py:148`, **B8** `permission_migration.py:125`, **B9** `normalization.py:40`, **B10** class renamed `TestConsumersReachHomeThroughTheOneDoor` -> `TestConsumerReachesHomeThroughTheOneDoor` -- all adopted as specified.
- **B6** `toolguard/once_per_store.py:152-160` -- 14 doc lines -> 6. **One deviation, see below.**
- **Non-blocking (judgement)** -- deleted the module docstring's copy of the `None`-falls-through rule (`ambient.py:9-11`), keeping the "unbound, each accessor reads live" half. `resolve()` and `active()` retain the full statement.

## Deviation from the review's text (B6)

The proposed closing clause was *"callers must fail soft, never raise"*. **False**: `_connect` (`once_per_store.py:241`) deliberately converts a `None` path into `OSError`, and documents that its own callers catch it. That is the false-universal failure mode the global comment rules warn compression about. Written instead: *"``None`` means the store is unavailable because home does not resolve; no caller may let that reach the user as a crash."* Everything else in the condensation was verified accurate and adopted.

## Verified true before adopting

- `CONFIG_ROOT_INDICATORS` is exactly `('.git', '.hg', '.jj', '.claude', 'CLAUDE.md', 'pyproject.toml')` -- the review's list and order were right.
- All three B4 bypassers are real: `tools/decision_ledger.py:37` (module scope, `Path.home()`), `install_provenance.py:346` (`os.environ`), `testing/sandbox.py` (both).
- B3's structural claim holds: the handlers are inside the `with`, and the ambient binding matters to them too (every handler calls `log_crash`, which resolves `ambient.home()`).
- The *other* measured claim in B1's docstring -- "both its tests fail" for `TestOrdinaryInvocationStderr` -- is still accurate; that class has exactly 2 tests. Left alone.
- No test asserts on the old B2 message, and the class renamed in B10 had exactly one reference.
- `except OSError, RuntimeError:` in `normalization.py` is valid, not a defect: PEP 758, Python 3.14.

## Flagged, deliberately not fixed

`toolguard-memories/TOO-45/reports/follow-up-queue.md` item 23 covers **two** bad strings in `path_utils.py`. B2 fixed the first (`:313`). The second is untouched: `resolve_project_root`'s strict-miss reason at `path_utils.py:242-244` still says *"within the bounded walk-up to the home directory"*, which the queue records as wrong -- the walk stops at home only if it reaches it. Item 23 is now half-stale. Out of scope for a prose pass and it changes a `reason` value, so it is Arnon's call.

## Rollback

Pre-edit snapshot of all 9 files with SHA1s at `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/backup/`. `diff -ru` against it confirms these 11 edits and nothing else. Exact rollback available.

## Self-review

Anti-pattern scan clean: no async, no threading, no local imports, no new imports (all prose plus one f-string and one class rename). `py_compile` clean on all 9. Directly affected modules re-run green (41 tests).

## Cost and elapsed

| Phase | Elapsed | Est. cost |
|---|---|---|
| Planning + verification of claims | ~12m | ~$1.10 |
| Implementation (11 edits) | ~8m | ~$0.55 |
| Self-review (suite x2, fitness, sweeps) | ~7m | ~$0.60 |
| **Total** | **~27m** | **~$2.25** |
