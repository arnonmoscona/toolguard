---
title: latest-code-review-report.md
type: report
permalink: toolguard/implementation/latest-code-review-report.md
tags:
- code-review
- TOO-8
date: 2026-06-18
---

# Code Review Report: TOO-8 Phases 4-6

**Date**: 2026-06-18  
**Scope**: All changed Python source files across TOO-8 Phases 4, 5, and 6 (last 4 commits)  
**Files reviewed**: toolguard/config.py, toolguard/hook.py, toolguard/permissions.py, toolguard/session_start.py, toolguard/error_log.py, toolguard/log_writer.py, test/unit/test_configuration.py, test/unit/test_hook.py, test/unit/test_session_start.py (new)  
**Test suite**: 683 tests, all passing. ruff check: clean.  
**Review duration**: ~25 minutes  
**Estimated cost**: ~$1.50 (Sonnet 4.6, large context)

---

## Summary

The TOO-8 Phase 4-6 implementation is of high quality. The hierarchical configuration, more-specific-wins resolver, hard_deny safety valve, logging streams, provenance tracking, conflict detection, and SessionStart hook are all well-designed and well-implemented. The public API surface is immutable and clearly separated from internal concerns. Test coverage is strong and BDD docstrings are present and consistent.

No critical or major correctness bugs were found. The findings below are all Minor or Suggestion grade.

---

## Findings

### Minor

**M1 -- `_detect_override` may false-positive when a less-specific deny is already shadowed by an allow at that same level**  
File: `toolguard/config.py`, lines 1245-1262  

When `_detect_override` scans less-specific levels for a deny, it calls `decide_detailed(allow, deny)` -- which is deny-first. If a less-specific level has BOTH a deny and an allow that match the same command, `decide_detailed` returns `deny` (because deny-first), so `_detect_override` records an override. But no real conflict exists at that less-specific level: the deny is locally shadowed by the allow within that same level. The override would be spurious.

Example: project level allows `git *`; user level has BOTH `deny: [git *]` AND `allow: [git *]`. The user level is self-consistent (deny-first means git is denied at user level), so there IS an override from a semantic standpoint -- but it may surprise users who wrote both rules intentionally at the user level to express "git is normally denied here but the project overrides it."

**Assessment**: The current behavior is technically correct under the deny-first model (the user level does deny git), but the corrective message may confuse users in this edge case. No test covers this scenario. The risk is low (pathological config), but it is worth noting.

**Recommended fix**: At minimum, add a comment in `_detect_override` documenting the deny-first evaluation semantic and why this is correct. Optionally add a test for the edge case. A more sophisticated fix (checking whether the same level would allow the command independently of the winning level) would be over-engineering for now.

---

**M2 -- `_check_dynamic_conflicts` only inspects the MOST RECENT conflict log file**  
File: `toolguard/session_start.py`, lines 101-131  

`_check_dynamic_conflicts` finds the most-recent `toolguard-conflict-*.md` by lexicographic sort and inspects only that file. If the most recent conflict log is empty (a new day's file was created with zero entries) but yesterday's file has entries, the function returns None (no conflicts found) -- silently missing recorded conflicts.

The `_find_most_recent_conflict_log` function returns the file with the latest date regardless of whether it has entries. `_count_conflict_entries` correctly returns 0 for an empty file, but then `_check_dynamic_conflicts` returns None without checking older files.

This is a real behavioral gap: conflicts recorded yesterday would be invisible if today's conflict log exists but is empty (e.g. if a session ran that triggered the log creation but had no conflicts yet).

**Recommended fix**: Walk the sorted list of conflict log files from most-recent to least-recent and return the first one with a non-zero entry count, rather than stopping at the most-recent file unconditionally.

```python
def _find_most_recent_conflict_log(log_dir: Path) -> Optional[Path]:
    # (keep existing signature)
    if not log_dir.exists():
        return None
    candidates = sorted(log_dir.glob('toolguard-conflict-*.md'), reverse=True)
    return candidates[0] if candidates else None

# In _check_dynamic_conflicts, change to:
for log_file in sorted(log_dir.glob('toolguard-conflict-*.md'), reverse=True):
    count = _count_conflict_entries(log_file)
    if count > 0:
        ...
        return str(display_path), count
return None
```

Note: The current test `test_picks_most_recent_file_with_entries` passes because both files have entries; it does not catch the empty-latest-file case. A regression test for this scenario is missing.

---

**M3 -- `load_takeover_mode_config` legacy logic diverges from `Configuration.takeover_mode` in `enabled` semantics**  
File: `toolguard/config.py`, lines 422-501  

The legacy `load_takeover_mode_config` uses `enabled = OR(any file enables it)` (line 481-483: `if takeover_mode.get('enabled', False): merged_config['enabled'] = True`). The new `Configuration.takeover_mode` uses single-owner / fail-safe-on-conflict. `scripts/migrate_permissions.py` still calls the legacy version, so its view of `enabled` may differ from the production hook's view when configs disagree across levels.

This is documented as a known follow-up (migrate scripts/migrate_permissions.py off the legacy loader), so it is not new information -- but noting it here ensures it stays visible. The risk is low because `migrate_permissions.py` uses `enabled` only to determine takeover filtering during migration, not as a security gate.

**Recommended fix**: Tracked as TOO-8 follow-up (already in task memory). No immediate action required.

---

**M4 -- `_run_startup_validation` falls back to `project_root / 'logs'` as a log directory, then passes it to log_error/log_warning which will create the directory (via `mkdir(parents=True, exist_ok=True)` in `_log_entry`)**  
File: `toolguard/hook.py`, lines 76-92; `toolguard/error_log.py`, line 88  

When `env_config` provides no `log_dir`, the code falls back to `config.project_root / 'logs'`. If this directory does not exist, `log_error` / `log_warning` will create it automatically (via `log_dir.mkdir(parents=True, exist_ok=True)`). This is probably the intended behavior, but it is an implicit side-effect not documented in `_run_startup_validation`'s docstring.

For consistency with the main hook path (which does NOT auto-create the log dir via `env_config` -- it only creates when `create_log_dir` is True), this could surprise users running startup validation in environments without a logs/ directory.

**Recommended fix**: Document the mkdir side-effect in `_run_startup_validation`'s docstring, or gate the fallback on whether the directory already exists (matching the stricter env-config path).

---

### Suggestions

**S1 -- The `_parse_compound_match_details` regex is fragile against reason strings with provenance suffixes**  
File: `toolguard/hook.py`, lines 439-462  

`_COMPOUND_MATCH_PATTERN` matches `All N sub-commands allowed: [...]` to extract `cmd -> rule` pairs. The reason string from `resolve_compound_permission` now contains provenance suffixes like `[project: /path]`. If a compound reason ever embeds these brackets inside the match group, the `', '.join` + `' -> '` parsing could break.

Current review shows the compound reason comes from `resolve_compound_permission` which aggregates reasons from `_resolve_one`, which in turn returns `resolved.reason` including the provenance suffix. The pattern match extracts the bracketed list content, but the inner `', '.join` parsing at line 458 splits on `', '` -- a provenance suffix like `[project: /path/.claude/toolguard_hook.toml]` contains no `, ` inside brackets, so the current test suite is green. However, if a path ever contained `, ` this could split incorrectly.

**Recommended fix**: This is a low-risk fragility. Consider adding a test that exercises a compound command where provenance paths contain commas.

**S2 -- `_parse_source` prints to stderr on failure but `load_configuration` callers cannot suppress it**  
File: `toolguard/config.py`, line 1531  

`_parse_source` prints `Warning: Failed to load {path}: {e}` to stderr. During test runs this produces noise (e.g. the `test_unparseable_file_skipped` test likely generates output). The stderr output cannot be suppressed by callers. This was inherited from pre-Phase-1 code and is not new.

**Recommended fix**: Consider routing this through the error log or making it silently-skippable (return None without printing) and instead capturing the failure as a `validation_issues()` entry. Low priority.

**S3 -- `session_start._detect_conflicts` log_dir derivation differs from hook.py**  
File: `toolguard/session_start.py`, lines 194-195; `toolguard/hook.py`, line 81  

Both files derive `log_dir = project_root / 'logs'` independently. If the log directory convention ever changes, it must be updated in two places. Consider extracting a shared `_resolve_log_dir(config)` helper in a shared utility.

**S4 -- Module-level mutable globals in hook.py are not reset between tests**  
File: `toolguard/hook.py`, lines 41-45  

The module-level booleans `_validation_done`, `_divergence_check_done`, `_discovery_diagnostic_done`, `_takeover_conflict_logged` persist across test invocations within a process. Tests that exercise `main()` multiple times may encounter state bleed. The test suite appears to work around this with fresh process-level patching, but explicit teardown (or using a different isolation pattern) would be cleaner and more robust.

---

## Positive Observations

- The frozen-dataclass hierarchy (`Provenance`, `ConfigLayer`, `ToolPatternLayer`, `Configuration`, `TakeoverConfig`, `ResolvedDecision`, `ConflictOverride`) is an excellent design choice that prevents accidental mutation and makes the public API contract very clear.
- The `_detect_override` algorithm correctly restricts conflict detection to allow-over-deny overrides only; hard_deny denials are excluded.
- The takeover mode fail-safe-on-conflict (OFF when levels disagree) is the correct security default.
- BDD docstrings on all test methods: present and accurate.
- Single source of truth for `_CONFIG_SYNC_DEFAULTS` shared between the hierarchical resolver and the legacy `config_sync_settings_from_sources`.
- The `session_start.py` module correctly treats itself as must-not-block: all paths exit 0 and exceptions are caught at the outermost level.
- `_count_conflict_entries` uses a lightweight line scan (no full parse) which is efficient.
- The `lru_cache` on config file parsing keyed on `(path, format, mtime_ns)` is a sound approach to in-process caching with automatic invalidation on file change.

