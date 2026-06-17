---
title: latest-code-review-report.md
type: note
permalink: toolguard/implementation/latest-code-review-report.md
tags:
- code-review
- TOO-8
---

# Code Review Report — TOO-8 Phase 1 Config Abstraction

Date: 2026-06-16
Scope: `changed` (working-tree diff vs HEAD)
Reviewer context: TOO-8 Phase 1 "config abstraction refactor (behavior-preserving)"

Files reviewed:
- `toolguard/config.py` (new public `Configuration` abstraction)
- `toolguard/config_divergence.py` (delegate to config module)
- `toolguard/auto_migrate.py` (delegate to config module)
- `toolguard/hook.py` (consume the new abstraction)
- `test/unit/test_configuration.py` (new test module)

## Summary

High-quality, well-documented refactor that cleanly pulls file/format/discovery
concerns behind a single immutable `Configuration` facade, exactly per the Phase 1
plan. Full suite (600 tests) passes. One genuine behavior divergence breaks the
"behavior-preserving" contract for config_sync scalar resolution, plus a few minor
cleanups.

## Findings

### Major

**M1. config_sync scalar resolution direction changed (project-wins vs user-wins).**
`toolguard/config.py:447` `scalar()` iterates `reversed(self.layers)` with last-wins,
so the **most-specific (project) layer wins**. The legacy resolution used by
`hook.main` previously went through `auto_migrate.load_config_sync_settings` ->
`config_sync_settings_from_sources` (`config.py:770`), which iterates `config_files`
in discovery order (project first, user last) with last-wins, so the
**least-specific (user) layer wins**.

Result: in `hook.py:330` (`config.config_sync_settings()`), a project+user conflict on
`auto_migrate` / `backup_dir` / `auto_sort_on_migrate` now resolves to the project
value, whereas before it resolved to the user value. This is a behavior change in a
phase explicitly documented as behavior-preserving, and the two code paths now
disagree with each other (the still-present `config_sync_settings_from_sources` keeps
user-wins; `Configuration.scalar` uses project-wins).

Note the new direction (project/most-specific wins) is what TOO-8 decision #4 wants as
the *eventual* Phase 2+ semantic — so the logic is the right end state, just landed a
phase early and inconsistent with its sibling helper. Recommend either: (a) make
`scalar()` match legacy user-wins for Phase 1 and defer the flip to Phase 2, or
(b) consciously accept the change, note it in the task memory / README, and align
`config_sync_settings_from_sources` to project-wins so the two paths agree. Add a test
pinning the chosen direction (current tests only cover single-level or same-direction
cases, so this divergence is untested).

### Minor

**m1. `_level_for_path` ignores its `start_dir` parameter.** `config.py:616`. The
parameter is unused; level is derived purely from whether the path is under
`~/.claude`. Harmless today (project paths are never under `~/.claude`), but the unused
arg is misleading. Drop the parameter or document why it is reserved.

**m2. Stale module docstring claims.** `config.py:17-20` says the legacy loaders "are
retained for backward compatibility but new clients should prefer `load_configuration`."
In practice `Configuration.governed_tools/takeover_mode/bash_permissions` still delegate
straight to the legacy `load_governed_tools` / `load_takeover_mode_config` /
`load_permissions`, so those remain the real implementation, not deprecated. Wording is
slightly aspirational vs reality; fine for Phase 1 but worth revisiting in Phase 2.

**m3. Now-unused imports / dead branches in delegating clients.**
`config_divergence.py` still imports `json` and uses `sys` only for unrelated warnings;
the delegated `get_toolguard_permissions` no longer parses files. Confirm `json` is
still used elsewhere in the module (it is, in `get_native_permissions`), so no removal
needed — but `auto_migrate.py` should be checked for a now-orphaned `sys`/`json`/
`tomllib` import after the body was deleted. Quick `ruff check` will catch any.

### Suggestions

**s1. Broad `except Exception` with `# noqa: BLE001`.** `config.py:611` (`_parse_source`)
mirrors legacy tolerance, which is appropriate for "skip unreadable source," but it will
also swallow programming errors (e.g. a bad `file_format`). Consider catching
`(OSError, json.JSONDecodeError, tomllib.TOMLDecodeError)` for tighter intent. Low
priority — preserves legacy behavior as-is.

**s2. `governed_tools()`/`takeover_mode()` re-discover config.** Each call re-invokes the
legacy loaders, which re-run discovery and re-parse files, even though the
`Configuration` already holds parsed `layers`. `permission_layers()` calls
`takeover_mode()` per invocation too. In `hook.main` this means several redundant
discovery passes per hook call. Acceptable for Phase 1 (correctness over speed; plan
defers perf), but a natural Phase 2 cleanup is to resolve these from `self.layers`.

## Verification

- `uv run python -m unittest discover -s test -t .` -> Ran 600 tests, OK.
- New `test_configuration.py` covers layering, takeover filtering, scalar single-level,
  validation issues, immutability, and the delegating helpers. Gap: no test for the
  project-vs-user scalar conflict direction (see M1).
