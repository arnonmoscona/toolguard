---
title: latest-code-review-report
type: report
permalink: toolguard/latest-code-review-report
tags:
- code-review
- TOO-30
---

Date: 2026-07-23
Scope: changed (branch too-30, TOO-30 -- XDG rules directory)

## Note on how this report was produced

The `/code-review` skill was invoked twice against this scope. Both subagent runs
could not persist their own report (`mcp__basic-memory__write_note` was unavailable in
that subagent context) and returned findings directly instead. The two runs
disagreed on one point -- the first found and reproduced a crash bug that the
second's summary did not mention. The main agent (not a subagent) independently
verified the crash claim by reproducing it, then fixed it and added regression
tests before writing this consolidated report. Both runs otherwise converged:
no other correctness or security issues, only minor/suggestion-level points.

## Summary

TOO-30's implementation (the optional `$XDG_CONFIG_HOME/toolguard/rules/` split-file
user-level config directory) is clean and well-integrated: new rules layers reuse the
existing layer/specificity model and flow through the generic `self.layers`
iterations (hard_deny pooling, migrate-dedup detection, provenance, extended-syntax
patterns) with no per-consumer special-casing needed, while content-filtering keeps
disallowed scalars out of the resolvers. One real bug was found and fixed during this
review (a crash on a malformed rules file); everything else is minor/suggestion-level.

## Findings

### Major (found and FIXED during this review)

**A syntactically-valid-but-wrong-shape config file crashed the entire hook.**
`toolguard/config.py`, `_parse_source()` (now ~line 1821). A `.json` file whose top
level is an array/scalar instead of an object (e.g. `[1, 2, 3]`) parsed successfully
via `json.load`, but the caller's dict-only logic then raised an uncaught
`AttributeError` (`'list' object has no attribute 'items'`) inside the
`toolguard_hook_rules` content-filtering branch of `load_configuration()` --
propagating out of `load_configuration()` and crashing permission resolution for
every command in the session, not just skipping the one bad file. The pre-existing
`~/.claude/toolguard_hook.json` path shared the identical latent fragility (crashes
one line later at `MappingProxyType(list)`), but TOO-30 extends it to a
higher-risk surface: the whole point of the rules directory is inviting *more*,
smaller, hand-authored files, raising the odds of a shape mistake.

Reproduced independently before fixing (see conversation). **Fix applied**:
`_parse_source()` now validates `isinstance(content, dict)` after parsing and raises
inside the existing try/except, so a wrong-shape file is treated exactly like an
unparseable one -- skipped with a `Warning: Failed to load ...` stderr message,
non-fatal, matching the already-tested `test_unparseable_file_skipped` behavior.
Fixes both the rules-dir case and the pre-existing `~/.claude` fragility in one
change. Two regression tests added:
`TestLoadConfigurationHierarchy.test_non_dict_top_level_json_skipped_not_crashed` and
`TestRulesDirectoryDiscovery.test_rules_dir_non_dict_top_level_skipped_not_crashed`
(`test/unit/test_configuration.py`). Full suite verified green after the fix: 1513
tests (was 1511), 0 failures; `ruff check` clean.

### Minor

- **`load_configuration()`'s per-layer loop body has grown busy**
  (`toolguard/config.py`, the `source_type == "toolguard_hook_rules"` branch, ~1948-1975).
  Stripping unexpected keys, computing `unexpected_keys`, and lazily computing
  `duplicate_format` all live inline in the discovery loop. Consider extracting a
  helper (e.g. `_rules_layer_fields(content, path, dup_stems) -> (content,
  unexpected_keys, duplicate_format)`) to keep the loop flat. Not acted on this pass
  -- pure readability, no behavior change, low risk to defer.

### Suggestions (not acted on -- low impact / consistent with existing convention)

- The rules directory is walked twice per load: once by `_discover_rules_files`
  (via `_discover_levels`), once by `_group_rules_files_by_stem` for duplicate-stem
  detection, plus `validation_issues()`'s existing per-layer on-disk `.exists()`
  checks. Negligible I/O for a directory of hand-authored rule files; the
  already-computed `by_stem` mapping could be threaded through to avoid the second
  scan if this ever becomes a hot path.
- Docs show `~`-abbreviated example paths while `Provenance.describe_brief()` emits
  absolute paths at runtime -- consistent with the existing convention elsewhere in
  the docs, no action needed.
- The flat rules-dir scan picks up dotfiles matching `*.toml`/`*.json` (e.g. a stray
  `.gh.toml`). Low impact, arguably correct (any `*.toml`/`*.json` file should be
  eligible), not flagged as a defect.

### Design point -- CONFIRMED intentional, not a defect

A rules file with an unexpected top-level key alongside a valid
`[permissions]`/`[hard_deny]` block has its valid sections applied normally while the
unexpected key is reported as an error-level `Issue` -- the file is NOT wholly
rejected. Both review runs flagged this as worth confirming was intended (an operator
might expect an "error"-flagged file to be inert). This was an explicit, deliberate
design decision made earlier in this ticket's development (see basic-memory
project='toolguard', "TOO-30 XDG rules directory - Requirements and Plan", decision
#1): matches the precedent already set for a non-boolean `takeover_mode.enabled`
elsewhere in the same module. No change needed.

### Verified positives (both runs independently confirmed)

- `hard_deny()` pooling, `Configuration.toolguard_permissions()` (feeding
  `migrate --dry-run`'s duplicate/superset detection), and provenance
  (`describe_brief()` naming the specific rules file) all work correctly with zero
  changes needed in those methods -- they already iterate `self.layers` generically.
- `migrate_permissions.py`'s target-*write*-selection filter
  (`source_type != "toolguard_hook"`) correctly excludes rules-dir layers from ever
  being a migration write target -- matches the ticket's explicit out-of-scope item
  (no project-level / auto-write into the rules dir for v1).
- User-level specificity (`len(level_dirs) - 1`) is stable even when `~/.claude`
  itself has no files.
- `CLAUDE_SETTINGS_PATH` correctly bypasses the rules directory scan entirely (the
  explicit-mode branch returns before `_discover_levels()` is ever called).
- `ConfigLayer.duplicate_format`, recorded at discovery time rather than re-checked
  against disk later, correctly handles `validation_issues()` running after a test's
  tempdir has been torn down.
- The test-isolation retrofit (`ConfigIsolationMixin` +
  `test/unit/CLAUDE.md`) is a genuine improvement, consolidating ad hoc
  `Path.home()`/`find_project_root`/env patching that had already caused two real,
  machine-state-dependent test failures.
