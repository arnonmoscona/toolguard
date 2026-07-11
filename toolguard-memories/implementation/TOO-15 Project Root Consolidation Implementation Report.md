---
title: TOO-15 Project Root Consolidation Implementation Report
type: note
permalink: toolguard/implementation/too-15-project-root-consolidation-implementation-report
tags:
- TOO-15
- task-memory
- implementation-report
---

# TOO-15 project-root marker consolidation -- Implementation Report

Completed 2026-07-11 (session started 08:19, GREEN landed ~08:37).

## Summary

Consolidated three near-duplicate "find project root" walk-ups
(`toolguard.config.find_project_root`, `toolguard.env_config.find_project_root`,
`toolguard.tools.project_root.resolve_project_root`) onto a single canonical
primitive, and added `.claude` (dir) / `CLAUDE.md` (file) as first-class,
same-trust-tier project-root markers alongside `.git`/`.hg`/`.jj` everywhere.

## Final design

The canonical implementation (marker constants, `RootStatus`/`RootCandidate`/
`ProjectRootResolution` dataclasses, and `resolve_project_root`) now lives in
**`toolguard/path_utils.py`** -- a stdlib-only leaf module -- rather than in
`toolguard/tools/project_root.py` as originally suggested. Reason: `toolguard/tools/__init__.py`
documents that package as deliberately segregated from the runtime
permission-evaluation path, and `toolguard/hook.py` (the live hook) imports
`toolguard.config`/`toolguard.env_config` directly. Putting the shared primitive in
`toolguard.tools` would have made the hook's import graph depend on the tools/automation
package. `path_utils.py` was already the shared leaf module all three call sites
imported from, so it is the correct home. This relocation was explicitly reviewed and
approved by the coordinator mid-task.

`resolve_project_root(start_dir=None, *, strict=False, override=None, indicators=DEFAULT_INDICATORS)`
now has two resolution shapes:
- `strict=False` (default, unchanged behaviour): tiered -- climb fully for the
  strong-anchor tier first (nearest anchor across the WHOLE walk-up wins,
  regardless of a nearer weak marker); only if no anchor exists anywhere does
  it fall back to the weaker build-manifest tier as `AMBIGUOUS` candidates;
  `NONE` if nothing found. Used by `migration_gate.py`/`corpus.py` (unchanged
  call sites, zero code changes needed there).
- `strict=True` (new): flat -- a single walk-up treating every marker in
  `indicators` as equally trusted, returning the nearest match of any kind as
  `RESOLVED_ANCHOR` (never `AMBIGUOUS`). Used by `config.py`/`env_config.py`,
  called with the narrower `CONFIG_ROOT_INDICATORS` tuple (anchors +
  `pyproject.toml` only -- NOT the full weak tier of `package.json`/`go.mod`/etc,
  preserving those two loaders' existing scope).

`toolguard/tools/project_root.py` is now a thin re-export shim (docstring
explains why) so `migration_gate.py`/`corpus.py` and their existing tests
continue to import `resolve_project_root`, `ProjectRootResolution`, `RootStatus`
from the same path, unchanged.

## Rename mapping (old -> new)

| Old (toolguard/tools/project_root.py) | New (toolguard/path_utils.py) |
|---|---|
| `VCS_MARKERS = (".git", ".hg", ".jj")` | `STRONG_PROJECT_ANCHORS = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")` (no separate alias -- used directly, one module now) |
| `RootCandidate.is_vcs` | `RootCandidate.is_anchor` |
| `RootStatus.RESOLVED_VCS` / `"resolved_vcs"` | `RootStatus.RESOLVED_ANCHOR` / `"resolved_anchor"` |
| `_nearest_vcs` | `_nearest_anchor` (private, moved) |
| `_all_non_vcs_candidates` | `_all_non_anchor_candidates` (private, moved) |
| (new) | `CONFIG_ROOT_INDICATORS = STRONG_PROJECT_ANCHORS + ("pyproject.toml",)` -- single shared tuple for config.py/env_config.py, eliminates the two hardcoded duplicate tuples |
| `DEFAULT_INDICATORS` | unchanged contents, now composed from `STRONG_PROJECT_ANCHORS` |

Verified via grep across the whole repo (production + tests) that no other
symbol (`VCS_MARKERS`, `is_vcs`, `RESOLVED_VCS`, `_nearest_vcs`,
`_all_non_vcs_candidates`) remains anywhere after the change.

## Files changed (8 total -- 4 production, 4 test; migration_gate.py/corpus.py untouched)

Production:
- `toolguard/path_utils.py` -- canonical implementation added (marker constants,
  dataclasses, `resolve_project_root` with `strict` param); `iter_dirs_upward`/
  `find_nearest_marker` unchanged, still used internally.
- `toolguard/config.py` -- `find_project_root` now a thin wrapper around
  `resolve_project_root(start, strict=True, indicators=CONFIG_ROOT_INDICATORS)`;
  same RuntimeError contract/message. (Note: this file also carries unrelated,
  pre-existing uncommitted WIP from a prior session -- a config-cache key change
  adding `st_size` alongside `st_mtime_ns` -- not part of this task, left as-is.)
- `toolguard/env_config.py` -- same pattern, returns `.root` (None-safe).
- `toolguard/tools/project_root.py` -- reduced to a re-export shim of the
  path_utils symbols, with an updated module docstring explaining the
  segregation rationale and the strict/non-strict split.

Tests:
- `test/unit/test_config.py` -- new `TestFindProjectRoot` class (7 tests: git,
  pyproject.toml, .claude, CLAUDE.md, .hg, .jj, raises-when-nothing-found).
  This closed a real pre-existing gap: no test anywhere exercised
  `config.find_project_root`'s real (unmocked) marker walk before this change.
- `test/unit/test_env_config.py` -- 4 new tests in the existing
  `TestFindProjectRoot` class (.claude, CLAUDE.md, .hg, .jj, each alone).
- `test/unit/test_tools_project_root.py` -- renamed `RESOLVED_VCS` ->
  `RESOLVED_ANCHOR` in 2 existing tests; added 5 new tests: `.claude` alone,
  `CLAUDE.md` alone, nearest-anchor-wins-regardless-of-kind (.claude nearer than
  farther .git), and the 2 tests added after coordinator review specifically
  proving the strict-vs-tiered semantic differentiator:
  - `test_strict_mode_nearest_marker_wins_over_tiered_default` -- farther `.git`
    + nearer `pyproject.toml`: `strict=True` returns the nearer pyproject dir,
    the tiered default returns the farther `.git` root, asserted in one test.
  - `test_strict_mode_never_returns_ambiguous` -- weak marker only, no anchor:
    `strict=True` resolves directly (`RESOLVED_ANCHOR`), never `AMBIGUOUS`.
- `test/unit/test_tools_migration_gate.py` -- renamed helper `_resolved_vcs` ->
  `_resolved_anchor`, `RESOLVED_VCS` -> `RESOLVED_ANCHOR`, updated 2 BDD
  docstrings.

## 9-file trace (fixture-safety audit)

Traced (read every usage, not just grepped) all 9 files named in the task:
`test_config.py`, `test_configuration.py`, `test_env_config.py`,
`test_hard_deny.py`, `test_hierarchical.py`, `test_migration.py`,
`test_takeover_mode.py`, `test_toml_config.py`, `test_tools_decision_ledger.py`.

**Only `test_env_config.py`** exercises the real (unmocked) `find_project_root`
walk (its `TestFindProjectRoot` class). Confirmed safe: no stray `.claude`/
`CLAUDE.md` exists at `/` or `/tmp` on the dev machine (checked directly), and
the one test that climbs unbounded (`test_returns_none_when_not_found`
[env_config] / equivalent) never reaches the real `~` (which does have a
`.claude` symlink) because `TemporaryDirectory()` roots are under `/tmp`, not
under `/home/arnon`, so the walk-up terminates at filesystem root first.
`test_stops_at_home_directory` already isolates via a mocked `Path.home()`.

**All other 8 files mock `find_project_root` (or `resolve_project_root`)
directly at every call site** -- confirmed by reading every occurrence, not
counting greps. None of them call `get_env_config` or otherwise exercise
`env_config.find_project_root` for real either (zero matches). **Zero fixture
fixes were needed in any of the 8** -- the real walk-up algorithm is never
exercised by them, so adding new markers cannot change their outcomes.

## Process notes

- Followed strict RED-GREEN with a checkpoint: wrote RED tests first, stopped,
  reported to the coordinator (including the path_utils.py relocation
  decision), got explicit approval plus one requested addition (the
  strict-vs-tiered differentiator tests), added those, confirmed RED for the
  right reason (`TypeError: unexpected keyword argument 'strict'`), then
  implemented GREEN in one pass.
- GREEN passed the full suite on the first implementation attempt (no
  iteration needed).
- `uv run ruff check .` -- all checks passed.
- Anti-pattern scan (async/await, threading, local imports) on all 4 changed
  production files -- none found.
- Coverage: ran `uv run python tools/coverage_stdlib.py`; the only "missed"
  lines reported in `path_utils.py` are multi-line `def` signature
  continuation lines (a known `trace`-module line-tracking artifact, not real
  gaps -- the function bodies themselves show full execution counts).

## Test counts

- Before (baseline): 1377 tests, all passing.
- After RED (initial): 1391 tests, 15 failing (11 errors + 4 failures) --
  exactly the touched/new set.
- After RED (coordinator-requested addition): 1393 tests, 17 failing (13
  errors + 4 failures) -- the 2 new strict-mode tests added to the failing set,
  both `TypeError` for the missing `strict` param (red for the right reason).
- After GREEN: **1393 tests, all passing.** `uv run ruff check .` clean.

## Not touched (per instructions)

`docs/*.md`, and no module outside the 8 listed above. The tree also carries
unrelated pre-existing uncommitted WIP (installer.py, docs/install.md,
docs/uninstall.md, pyproject.toml, test_toml_config.py, an unrelated
config.py cache-key change) from a prior session -- confirmed via `git diff
--stat` that none of it was touched or altered by this work.

## Cost/time (rough estimate)

- Planning + investigation (reading source, tracing 9 test files, designing
  the path_utils.py relocation): ~10 min.
- RED phase (writing test changes, running suite, memory writes): ~10 min.
- Coordinator gap-fix (2 new tests, re-run, memory update): ~3 min.
- GREEN implementation (path_utils.py, config.py, env_config.py,
  tools/project_root.py, full suite, ruff, coverage, self-review): ~7 min.
- Total elapsed: ~30 min. Estimated cost (Sonnet 5, this session's token
  volume -- moderate-size file reads/edits, several full-suite runs): roughly
  $1.50-$2.50 total, dominated by the investigation/tracing phase's file reads.