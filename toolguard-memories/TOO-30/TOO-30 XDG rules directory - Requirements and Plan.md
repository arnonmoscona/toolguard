---
title: TOO-30 XDG rules directory - Requirements and Plan
type: task
permalink: toolguard/too-30/too-30-xdg-rules-directory-requirements-and-plan
tags:
- task-memory
- TOO-30
---

## Ticket

TOO-30: Support a `~/.config/toolguard/rules/` directory of split user-level config files.

Add an optional discovery step: scan `$XDG_CONFIG_HOME/toolguard/rules/` (default
`~/.config/toolguard/rules/`) for any number of `*.toml`/`*.json` files, flat/non-recursive.
Each uses the toolguard_hook schema. All files merge into the existing **user level**
(least-specific tier) -- no new hierarchy tier. Restricted to `[permissions]` and
`[hard_deny]` sections only (not scalars like `governed_tools`, `no_match_fallback`,
`[takeover_mode]`, `[config_sync]`). Provenance must name the specific file. Explicitly out
of scope for v1: project-level equivalent, recursive scanning, config_sync writing into the
directory.

Full description: see YouTrack TOO-30 (`~/projects/youtrack_api/get-issue.sh TOO-30`).

## Architecture findings (from reading toolguard/config.py)

- The layer/specificity model already supports "multiple layers, one level" (that's how
  `.local` + regular files coexist today at one `.claude` dir). Rules-dir files just need to
  be appended as `ConfigLayer`s carrying the SAME specificity int as `~/.claude`'s layers
  (`len(level_dirs) - 1` in `_discover_levels()`), computed unconditionally so it's stable
  even if `~/.claude` itself has no files.
- `hard_deny()` and `Configuration.toolguard_permissions()` (used by
  `migrate --dry-run` duplicate/superset detection via `config_divergence.get_toolguard_permissions`)
  both already iterate `self.layers` generically with no level-awareness -- these two
  checklist items come for free once discovery produces the right layers, no separate code
  needed.
- `[regex]`/`[glob]`/`[native]` extended syntax is a string-prefix convention INSIDE
  individual permission pattern strings, not a TOML top-level table -- confirmed via
  docs/configuration.md examples. No collision with the top-level-section restriction.
- Legacy `discover_config_files()` (2-level, used only by `migrate_permissions.py`'s
  target-file selection) intentionally NOT changed.

## Clarifications from discussion (2026-07-23)

1. **Invalid rules-file (unexpected top-level section) handling**: apply the valid
   `[permissions]`/`[hard_deny]` sections normally, flag the unexpected key(s) as an
   error-level `Issue` (fail-loud, not a hard crash, not a whole-file reject).
2. **CLAUDE_SETTINGS_PATH interaction**: rules directory is NOT scanned when
   `CLAUDE_SETTINGS_PATH` is set (that mode bypasses the hierarchy entirely, automatic side
   effect of where the discovery step was integrated -- no special-case code needed).
3. Rules-dir entries ordered AFTER the four primary `~/.claude` candidates, sorted
   lexicographically by stem among themselves.
4. No feature toggle to disable the rules dir -- missing/empty directory is just a no-op.
5. No PEG/bash-grammar involvement.

## TDD process (2026-07-23) -- COMPLETE

- **RED**: feature-coder wrote 27 tests in `test/unit/test_configuration.py` (4 new
  classes) against an explicit design contract. Reviewed personally: found + fixed one real
  test bug (a path-prefix filter that could never match the rules-dir path, would never
  have gone green even with correct implementation). Verified independently: 16 genuinely
  red, 11 legitimately green (exercise existing generic code), `ruff check` clean.
- **Test-isolation detour**: Arnon flagged real risk of tests depending on this machine's
  real dogfooded `~/.claude` config. Confirmed real via a full-suite scan: 5 of 8 files
  touching config discovery have ZERO `Path.home()` isolation (test_hierarchical.py: 18
  unguarded calls). Fixed only the 2 tests that were ACTUALLY failing
  (`test_takeover_mode.py`, via `patch.object(Path, "home", ...)`). Full retrofit
  deliberately deferred -- see
  [[TOO-30 pre-push follow-up: suite-wide test isolation cleanup]] for the investigation,
  decision (stdlib redirect pattern via a shared mixin/helper, NOT pyfakefs -- all
  config.py filesystem access is reachable from exactly 3 anchors: Path.home(),
  find_project_root(), XDG_CONFIG_HOME), and the **required pre-push action item**.
- **GREEN**: feature-coder implemented `toolguard/config.py` (+221/-11) against the
  contract: `_rules_dir()`, `_discover_rules_files()` (built on shared
  `_group_rules_files_by_stem()`), `_discover_levels()` appending rules-dir entries at user
  specificity, `_level_for_path()` recognizing the rules dir, `ConfigLayer.unexpected_keys`,
  `load_configuration()` content-filtering, `validation_issues()` new error check. Plus
  docs/configuration.md (+48) and docs/architecture.md (+13).
  **One reviewed-and-accepted deviation**: added a second `ConfigLayer` field
  `duplicate_format: bool = False`, populated at discovery time. Necessary because the
  existing "both TOML/JSON formats" warning has ALWAYS relied on a live re-check of the
  filesystem at `validation_issues()`-call time (pre-existing design, not TOO-30-introduced);
  one RED-phase test calls `validation_issues()` after its tempdir is torn down, which the
  live re-check can't see. Scoped only to `toolguard_hook_rules` layers; both new fields
  default falsy so no other call site is affected. Deliberately did NOT extend this fix to
  `~/.claude` layers (same latent issue, but out of scope, not currently exercised by any
  real usage pattern).
- **Final verification** (done independently, not just trusting the subagent report):
  `uv run python -m unittest discover -s test -t .` -> 1511 tests, 0 failures, 0 errors.
  `uv run ruff check .` clean. Confirmed no test file appears in the config.py-phase diff.

## Status

Implementation COMPLETE and green. Not yet committed (per CLAUDE.md, commits are
Arnon's call). Remaining before this ticket can be considered fully closed:
- Arnon's final review/commit decision.
- The pre-push test-isolation follow-up (see linked note) -- must happen before pushing,
  not necessarily before committing.
- Standard pre-push checklist (coverage, pyscn, toolguard-maintenance, version bump,
  release notes) not yet run for this ticket.
