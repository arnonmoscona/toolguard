---
title: latest-code-review-report.md
type: report
permalink: toolguard/implementation/latest-code-review-report.md
tags:
- code-review
- TOO-8
---

## Code Review Report -- TOO-8 Phase 4 (log streams, conflict logging, provenance)

Review date: 2026-06-17
Scope: changed (working tree) -- Python source + tests for TOO-8 Phase 4.

Files reviewed:
- /home/arnon/projects/toolguard/toolguard/config.py
- /home/arnon/projects/toolguard/toolguard/hook.py
- /home/arnon/projects/toolguard/toolguard/permissions.py
- /home/arnon/projects/toolguard/toolguard/log_writer.py
- /home/arnon/projects/toolguard/toolguard/error_log.py
- /home/arnon/projects/toolguard/toolguard/session_warnings.py
- /home/arnon/projects/toolguard/test/unit/test_logging_streams.py (new)
- test_hook.py, test_session_warnings.py, test_toml_config.py (test updates)
- technical-notes.md (doc)

(Memory/task-artifact .md files under toolguard-memories/ were excluded from review.)

### Summary

Solid, well-documented implementation. The provenance-aware resolver, conflict
(allow-over-deny) detection, and per-concern log-stream separation are cleanly
designed and well tested (105 tests pass; ruff clean). The decision algorithm
(more-specific-wins, deny-first within level, hard-deny-first) is preserved and
the new `resolve_*_detailed` functions correctly thread matched-pattern -> provenance.
A few correctness/consistency gaps remain, none critical.

### Findings

#### Critical
None.

#### Major
None.

#### Minor

1. **Validation issues ignore `Issue.level` -- error-level issues misrouted to the
   warning stream.**
   File: hook.py:84-85 (`_run_startup_validation`).
   The loop calls `log_warning(...)` for every issue regardless of `issue.level`.
   `Issue.level` can be `'error'` (config.py:1628 -- `warning.get('level','warning')`),
   so an error-level validation issue would land in the WARNING stream, defeating the
   Phase 4 stream separation. Currently LATENT: `validate_permissions`
   (validation.py / config_validation.py) only emits `'warning'` today, so no error
   issue is produced. Still a robustness gap given the field exists specifically to
   distinguish.
   Fix: branch on `issue.level` -- `log_error(...)` when `issue.level == 'error'`,
   else `log_warning(...)`.

2. **Duplicate, un-migrated "both .toml and .json" stderr print in legacy discovery.**
   File: config.py:151-155 (`discover_config_files`).
   The diff removed the equivalent print from `_discover_in_dir` (the hierarchical
   path) and routed the warning to the WARNING stream via `validation_issues()`,
   claiming a "single source of truth." But `discover_config_files` -- still used by
   config.py:497/577/682 and the migration script -- retains the old
   `print(... 'Using TOML ...', file=sys.stderr)`. It fires during the test run
   (visible in unittest output). Not a bug in the new path, but contradicts the
   stated single-source-of-truth goal and can double-surface the warning for callers
   that go through both paths.
   Fix: remove the legacy print too, or add a comment noting it is intentionally
   retained for the legacy/non-hierarchical code path.

#### Suggestions

3. **Doc mismatch in `log_discovery`.**
   File: log_writer.py docstring for `log_discovery`. The Args note says
   `source_descriptions` is "the output of `Configuration.describe_sources()`", but
   the actual caller (hook.py:612) passes `config.describe_levels()` (the brief
   `level: path` form). Update the docstring to reference `describe_levels()`.

4. **`to_stdout` parameter now misnamed.**
   File: session_warnings.py `issue_takeover_warning`. The parameter `to_stdout`
   now gates writing to STDERR (the print goes to `sys.stderr`). The name is
   misleading; the docstring already clarifies, but consider renaming to
   `to_stderr` (or `echo`) in a follow-up. Low priority -- it is a public-ish kwarg
   and renaming touches callers/tests.

5. **`_format_conflict_message` / `_detect_override` provenance lookup relies on
   string identity of patterns.**
   `_provenance_for_pattern` matches by `pattern in candidates` against the same
   layer lists passed to `match_command`, and `match_command` returns the exact
   list element it iterated. Verified consistent (the returned `matched_pattern` is
   an element of the level's allow/deny list, prefixes and all), so this is correct.
   Noted only because it is a subtle coupling: if a future change makes
   `match_command` return a normalized/wrapper-stripped pattern instead of the raw
   list element, provenance lookup would silently return None. A short comment at
   the `match_command` return site would harden this.

### Positives
- Backward-compatible reason suffix design (`reason  [level: path]`) preserves
  existing `reason.split(': ', 1)` and substring assertions -- good.
- Deny-first / hard-deny-first ordering preserved; hard_deny correctly excluded
  from conflict logging (verified by test).
- New test file has strong branch coverage (override skip-empty-middle-level,
  no-provenance default deny, hard_deny -> resolution-not-conflict, M1 single warning).
- All diagnostic/log writes are wrapped so logging never fails the hook.
