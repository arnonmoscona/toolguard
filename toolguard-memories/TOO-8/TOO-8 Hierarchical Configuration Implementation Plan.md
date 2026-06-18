---
title: TOO-8 Hierarchical Configuration Implementation Plan
type: note
permalink: toolguard/too-8/too-8-hierarchical-configuration-implementation-plan
tags:
- task-memory
- TOO-8
- hierarchical-config
---

# TOO-8 Hierarchical Configuration -- Implementation Plan (v2)

Status: Phases 1-3 COMMITTED. Phase 4 (logging streams + conflict logging + rule
provenance) IMPLEMENTED + code-reviewed + green (672 tests, with AND without
CLAUDE_SETTINGS_PATH), UNCOMMITTED as of 2026-06-17. The provenance-in-logs enhancement was
delivered as part of Phase 4.
Next phases: 5 (non-permission cross-level: scalar more-specific-wins + takeover
special-case), 6 (SessionStart "last run had conflicts" alert), 7 (docs restructure).
See "Phase 4 outcome" at end.

## Objective

Let shared toolguard rules live in an ancestor `.claude/` directory instead of being
copied into every project. Walk from the project root up to `~`, layering configs, with
**more-specific-level-wins** conflict resolution and a `[hard_deny]` safety valve.

## Current architecture (verified 2026-06-16)

- `config.find_project_root` (config.py:17) -- climbs to first `pyproject.toml`/`.git`.
- `config.discover_config_files` (config.py:51) -- ordered flat list of
  `(Path, source_type, format)` for **two levels**: project then user. TOML preferred.
- `config.load_permissions` (config.py:426) -- loads all, takeover-filters `claude`
  files, then **flattens via `merge_permissions` (config.py:193) into a single union**,
  discarding level info.
- `permissions.check_permission` (permissions.py:198), `compound.check_compound_permission`,
  `hook.check_file_path_permission` (hook.py:312) -- **global deny-first**.
- Leaky clients of discovery: `hook._run_startup_validation` (walks files, inspects
  `path.stem`, hand-rolls TOML+JSON warning), `hook.load_file_path_patterns` (opens files,
  branches on format), `load_governed_tools`, `load_takeover_mode_config`, divergence,
  auto-migrate.
- `CLAUDE_SETTINGS_PATH` forces single-file mode; keep it bypassing hierarchy.

### Key insight
Current "flatten -> global deny-first" is exactly the model being replaced. More-specific-
wins needs level grouping carried through to evaluation. AND: discovery leaks file/format/
location concerns into many clients -- a broken abstraction to fix first (Phase 1).

## Resolved decisions

1. **Resolution granularity:** traverse levels most-specific -> least-specific; FIRST
   level with any match decides (deny-first within the level). Pattern precision does not
   cross levels. (Agreed.)
2. **Conflict logging:** ON by default. Human/LLM-readable, NOT structured/machine-readable.
   Dedicated conflict log file; the high-volume resolution log emits only a warning entry
   pointing to it. Session-start alert if previous session logged a conflict -> own phase.
3. **hard_deny:** single mechanism `[hard_deny]` section (allow/deny). Collected from ALL
   levels, checked first, cannot be overridden. (Agreed.)
4. **Non-permission merge:** governed_tools = union; takeover pattern lists = union;
   no_match_fallback = more-specific-wins; scalars (backup_dir, auto_sort_on_migrate) =
   more-specific-wins. **takeover_mode.enabled = special (see below).**
5. **Toggle read location:** `hierarchical_configuration` read ONLY from project-level
   config; default true. Fixed bootstrap rule breaks circularity (an ancestor cannot vote
   on whether ancestors are read). Toggle now controls ONLY traversal breadth, not a
   resolution mode.
6. **.local at every level:** yes.
7. **TOML+JSON within a level:** TOML wins, warn. No change.
8. **Monorepo:** start at project root; do not descend into sub-dir `.claude/`. Out of
   scope; no sub-project `.claude/` expected.
9. **Include directive:** OUT (separate ticket).

### takeover_mode conflict handling (decided)
Single-owner policy (typically user level). Do NOT merge `enabled` per level. If `enabled`
is set to conflicting values across levels => misconfiguration. Response: **fail-safe to
takeover OFF** (native Claude prompts stay active; nothing silently bypassed) + a
high-visibility conflict warning (dedicated conflict log + session-start alert). Rejected:
less-specific-wins (would keep bypassing against a project's more-cautious OFF) and
deny-everything (bricks session for a benign override; disproportionate). A configurable
strict/deny-all escalation may be added later, not in v1. Future permission-mover should
help consolidate takeover to one level (the real cure).

### No backward-compat machinery
One resolver only. Single-config users are unaffected (one level => more-specific-wins
equals deny-first). No dual path. Behavior change for the rare existing project+user
conflict case is accepted and documented in a topic README, not code-gated.

## Phase 1 abstraction design (PENDING SIGN-OFF)

Goal: make the config module expose conceptual hierarchy + coarse semantic operations;
hide files/format/location. No client outside config opens a file or names a format.

Three internal concerns, one public model:
1. Sourcing/parsing (internal): only code that knows files, `.claude/` layout, TOML/JSON,
   `.local`, traversal, `CLAUDE_SETTINGS_PATH`. Produces raw dicts.
2. Modeling (exposed): raw dicts -> ordered `ConfigLayer`s, most-specific first, each with
   provenance (display-only origin) + typed content (permissions per tool, governed_tools,
   takeover_mode, scalars).
3. Resolution/validation (coarse public ops): semantic questions, not file questions.

Public API (the only surface clients use):
- `load_configuration(start_dir) -> Configuration`
- `Configuration.governed_tools() -> list[str]`
- `Configuration.takeover_mode() -> TakeoverConfig` (resolved + conflict detection)
- `Configuration.permission_layers(tool_name) -> [...]` (per-layer allow/deny/hard_deny,
  ordered; feeds Phase 2 resolver)
- `Configuration.validation_issues() -> [Issue]` (replaces `_run_startup_validation` walk)
- `Configuration.conflicts() -> [Conflict]`
- `Configuration.scalar(name, default)`

Moves INTO config: all discovery, JSON/TOML parsing, `load_permissions*`, `merge_*`,
`hook.load_file_path_patterns`, the validation file-walk, takeover load/merge, TOML+JSON
warning. STAYS OUT: pattern matching (permissions.py/compound.py receive typed lists,
return decisions); logging routing (config returns Issues/Conflicts, hook writes them --
config stays I/O-side-effect-free beyond reading).

Provenance: each layer/entry retains origin (level + opaque physical source) to enable the
future permission-mover. Build provenance now; do NOT build mutation now.

Critical-thinking caveat: design to ALLOW non-file sources but implement files ONLY. No
pluggable backends/provider interface (YAGNI; URL sources are out of scope). Win is the
seam, not generality.

API immutability (Arnon, agreed): prefer immutable structures in the public API where the
stdlib makes it easy/cheap -- tuples instead of lists, frozen/read-only mappings (e.g.
`types.MappingProxyType`) instead of dict, frozen dataclasses for `ConfigLayer`/
`Configuration`/`TakeoverConfig`. Goal: accidental mutation raises rather than silently
corrupting config. Do NOT over-engineer deep read-only wrappers everywhere; use it only
where the standard library provides an easy facility.

Phase 1 is BEHAVIOR-PRESERVING: still 2 levels, still union + global deny-first, so the
existing test suite is the safety net. Traversal and more-specific-wins both move to
Phase 2.

## Phased plan
Standing exit criterion for every phase: unit tests with >90% coverage for the phase's
changes; existing tests still pass WITH and WITHOUT `CLAUDE_SETTINGS_PATH` set. Full design
and results for completed phases live in the "Phase N outcome" sections below.

- **Phase 0 -- Finalize spec.** DONE.
- **Phase 1 -- Config abstraction refactor (behavior-preserving).** DONE + COMMITTED.
- **Phase 2 -- Traversal + more-specific-wins (+ caller migration / dedup cleanup).** DONE + COMMITTED.
- **Phase 3 -- hard_deny safety valve.** DONE + COMMITTED.
- **Phase 4 -- Logging streams + conflict logging + rule provenance.** DONE (committed with folded-in dead-code cleanup + config-loader consolidation).
- **Phase 5 -- Non-permission config cross-level.** NEXT. Scalars (config_sync, backup_dir, auto_sort_on_migrate) + no_match_fallback resolve more-specific-wins -- flip config_sync from the Phase-1 user-wins pin and clear its FIXME. governed_tools and takeover pattern lists stay union. takeover_mode.enabled special-cased on cross-level conflict (see "takeover_mode conflict handling" decision).
- **Phase 6 -- SessionStart conflict-alert hook.** Surface "last run had conflicts" at startup.
- **Phase 7 -- Docs restructure + doc-debt.** Split the oversized README (thin index + beginner quick-start + agent-oriented few-shot guides); fold in deferred doc-debt (resolve_compound_permission naming, TOO-16 distribution model + run_hook.sh retirement).

## Risks (per Arnon)
- Existing 2-level users: not a concern; address in a topic README.
- Per-hook traversal cost: not a concern now; revisit only if it becomes material.
- No dual path / no backward compat needed.

## Out of scope
Include directive; sub-project `.claude/` descent; remote/URL config sources.

## Key files
`toolguard/config.py`, `permissions.py`, `compound.py`, `hook.py`, `config_validation.py`,
`auto_migrate.py`, `log_writer.py`, `error_log.py`, `session_warnings.py`, tests under `test/`.

## Phase 1 outcome (2026-06-16) -- UNCOMMITTED, pending Arnon's review

Behavior-preserving config-abstraction refactor landed and verified.

Done:
- New public abstraction in `config.py`: `load_configuration()` + frozen dataclasses
  (`Configuration`, `ConfigLayer`, `ToolPatternLayer`, `Provenance`, `TakeoverConfig`,
  `Issue`); accessors `bash_permissions`/`allow_deny_for`/`permission_layers`/
  `governed_tools`/`takeover_mode`/`scalar`/`config_sync_settings`/`validation_issues`.
  Immutable surface (tuples, MappingProxyType, frozen dataclasses). Provenance retained
  per layer for the future permission-mover.
- `hook.py` fully migrated: no file/format/location concerns remain (only stdin
  `json.loads`). `_run_startup_validation` consumes `validation_issues()`;
  `load_file_path_patterns` is a thin adapter over `allow_deny_for()`.
- Tests: `test/unit/test_hook.py` re-pointed at `load_configuration` (intent preserved,
  no assertion weakened); 34 abstraction tests promoted to `test/unit/test_configuration.py`.
  Full suite 601 OK. `ruff check` clean. config.py coverage 93%.
- Code review (code-reviewer subagent) done. Report:
  basic-memory `implementation/latest-code-review-report.md` (note doubled `.md.md`).
- M1 (review): `scalar()` had flipped config_sync to project-wins; HEAD behavior is
  USER-WINS (verified via `git show` + harness). Reverted to user-wins for Phase 1; added
  pin `test_config_sync_conflict_is_user_wins_phase1` + `# FIXME(TOO-8 Phase 2, decision #4)`
  marking the intentional Phase-2 flip to project-wins. Minor cleanups done.

Consciously deferred to Phase 2 (NOT done in Phase 1):
- `config_divergence.py` (`check_and_warn_divergence`) and `auto_migrate.py` still call
  `discover_config_files` and open settings directly. Deferred because they consume the
  discovery layer that changes in Phase 2 (hierarchical traversal); migrating now = rework.
- All Phase-2 behavior: directory traversal up to ~, more-specific-wins resolution.

Implementation reports: basic-memory `implementation/coder-latest-implementation-report.md`.
Changed files: `toolguard/config.py`, `toolguard/hook.py`, `toolguard/config_divergence.py`,
`toolguard/auto_migrate.py`, `test/unit/test_hook.py`, `test/unit/test_configuration.py` (new).
Nothing committed -- Arnon performs all git writes.

## Phase 2 outcome (2026-06-17) -- UNCOMMITTED, pending Arnon's review

Implemented + code-reviewed (code-reviewer: no production correctness bugs) + green:
634 tests pass WITH and WITHOUT CLAUDE_SETTINGS_PATH set; ruff clean; ~100% coverage on
changed lines.

Delivered:
- Hierarchical discovery: `_discover_levels` walks project root -> ~, each `.claude/` level
  with a specificity index (0 = project, most specific); `~/.claude` always included; stop
  at ~. `hierarchical_configuration` toggle read only from project level, default true;
  false => project+user only.
- More-specific-wins resolution: `Configuration.permission_levels` + `resolve_permission`
  cascade most-specific->least, deny-first within a level, first matching level decides,
  fail-closed if none. Applied to Bash, each compound sub-command independently, and
  Read/Write/Edit. Single resolution path (no legacy/dual path).
- NEW requirement: relative config paths always resolve against the PROJECT ROOT regardless
  of declaring level (`Configuration.resolve_config_path` / `_anchor_file_pattern`);
  absolute and ~ paths unaffected; `[regex]` not rewritten. Covered by tests at project /
  intermediate / user levels (backup_dir + Read patterns). Documented in technical-notes.md.
- Cleanup: unified `is_tool_wrapper`/`_strip_tool_wrapper` structural matcher (3 drifted
  lists collapsed); config_divergence migrated to Configuration; tool-prefix FIXME removed.
- CLAUDE_SETTINGS_PATH policy: runtime hook keeps single-file mode; the migration/divergence
  tooling now passes `load_configuration(..., ignore_env_override=True)` so it is
  project-scoped end-to-end (decision made on Arnon's behalf; flag if you disagree).
- Tests isolate CLAUDE_SETTINGS_PATH via `_IsolatedEnvTestCase` in test_hierarchical.py.

Changed files: config.py, permissions.py, compound.py, hook.py, config_divergence.py,
auto_migrate.py, scripts/migrate_permissions.py, technical-notes.md, .gitignore; tests
test_hierarchical.py (new), test_hook.py, test_config_divergence.py, test_migration.py.

P3 underscore-privatisation: DONE (2026-06-17, Arnon authorised editing formal tests).
Privatised 7 functions: `_load_permissions`, `_load_permissions_from_file`,
`_merge_permissions`, `_load_governed_tools`, `_load_governed_tools_from_file`,
`_merge_governed_tools`, `_toolguard_permissions_from_sources`. ~55 references + 2
`patch('toolguard.config.X')` string targets updated across 4 test modules. Suite green
both ways; config.py coverage 95%.
Left public (genuine production callers): `find_project_root`, `discover_config_files`,
`load_takeover_mode_config` (all used by log_writer.py / scripts/migrate_permissions.py),
and `config_sync_settings_from_sources` (only caller `auto_migrate.load_config_sync_settings`,
whose 8 committed tests pass arbitrary config_files lists -- migrating would change test
intent). FOLLOW-UP: migrate the large `scripts/migrate_permissions.py` onto the
Configuration API; that unblocks privatising the remaining four.
- Git housekeeping (Arnon's domain): `coder-test/test_configuration_abstraction.py` is a
  staged-add living only in the index (absent from worktree); unstage it
  (`git rm --cached coder-test/test_configuration_abstraction.py`).

Reports: basic-memory `implementation/coder-latest-implementation-report.md` (+ addendum),
review `implementation/latest-code-review-report.md`. Nothing committed; Arnon does git.

## Phase 3 outcome (2026-06-17) -- UNCOMMITTED, pending Arnon's review

Implemented the `[hard_deny]` unoverridable safety valve. Code-reviewed (no Critical/Major
findings). 654 tests green WITH and WITHOUT CLAUDE_SETTINGS_PATH; ruff clean; coverage
config.py 95.6%, permissions.py 90.4%, hook.py 83.8%.

Semantics (DEFINED ON ARNON'S BEHALF -- confirm on review): `[hard_deny]` is a toolguard
extension (toolguard_hook files only, never native settings) with `deny` and `allow` lists,
pooled as a union across ALL levels, checked FIRST before the Phase 2 cascade. Match a
`deny` AND no `allow` carve-out => unoverridable DENY; else fall through unchanged. `allow`
is ONLY an exception to hard_deny `deny` (e.g. hard-deny all curl except curl localhost),
NOT a forced allow. Same extended syntax/wrappers/matchers; relative file-path patterns
anchored to project root (reuses Phase 2). Applies to Bash, each compound sub-command
(compound denied if any sub is), and Read/Write/Edit.

Changed: config.py (`Configuration.hard_deny(tool)`), permissions.py (`check_hard_deny`),
hook.py (file-path + Bash resolve check hard_deny first), technical-notes.md (new section),
test/unit/test_hard_deny.py (NEW, 20 tests), test/unit/test_hook.py (added no-op
`hard_deny` to the `_FakeConfig` test double -- API-sync only, no intent change).

Minor review follow-ups (NOT blocking; deferred):
- M1: the "both .toml and .json exist" warning exists twice -- a stderr print in
  `_discover_in_dir` (the one that fires) and an Issue-based copy in `validation_issues()`
  that can't fire via load_configuration. Consolidate -- naturally folds into Phase 4
  (logging streams / Issue routing).
- M2: stale docstrings -- `bash_permissions()` / module docstring still call it "the
  command-tool entry point," but post-Phase-2 the hook resolves Bash via
  `resolve_permission`+`allow_deny_for`; `bash_permissions()` has no production caller
  (tests only), so the legacy `_load_permissions` stderr discovery diagnostics no longer
  fire at runtime. Update docstrings; decide in Phase 4 whether to re-emit those diagnostics
  through the new logging.

Reports: basic-memory `implementation/coder-latest-implementation-report.md`; review
`implementation/latest-code-review-report.md`. Nothing committed; Arnon does git.

## Docs debt to fold into Phase 7 (deferred 2026-06-17, agreed with Arnon)

User-facing docs are current enough to use now (README got the hierarchy/resolution model,
project-root-relative paths, and a `[hard_deny]` config-reference section + notes bullet;
technical-notes.md has full Phase 2/3 sections). Deferred minor polish for the Phase 7
consolidated docs pass (README restructure + technical-notes):
- technical-notes.md describes the compound cascade behaviorally and names
  `resolve_permission`, but does NOT name `resolve_compound_permission`, nor note that the
  legacy `check_compound_permission` is retained but OFF the live path. Add both.
- Same "legacy retained but off live path" note for `bash_permissions` and the
  `_load_permissions` stderr discovery diagnostics (code-review M2) -- and decide whether
  to re-emit those discovery diagnostics through the Phase 4 logging.
- Code-review M1: consolidate the duplicated "both .toml and .json exist" warning
  (stderr print in `_discover_in_dir` vs the unreachable Issue-based copy) -- naturally a
  Phase 4 logging-streams item.
- Full README audience-split restructure (beginner quick-start + agent-oriented few-shot
  guides) remains the core Phase 7 deliverable; README is still partly stale elsewhere.

## Phase 4 enhancement: matched-rule PROVENANCE in the resolution log (raised by Arnon 2026-06-17)

Confirmed gap: `resolve_permission` (config.py) consumes `permission_levels()`, which STRIPS
provenance (collapses layers to bare `(allow, deny)` tuples). The `decide` callables
(`decide_command_at_level`, etc.) return reasons containing only the matched PATTERN
(e.g. "Command matches allow pattern: git *"), never its origin. So the resolution log does
NOT tell a reader which file/level the effective rule came from -- a real loss under the
hierarchy (same pattern can exist at multiple levels).

Fold into Phase 4: thread provenance so a decision's reason/log cites the winning rule's
origin, e.g. "matches allow pattern: git *  [project: .claude/toolguard_hook.toml]". For
exact-file precision, have the decider report which pattern matched and map it back to its
`ToolPatternLayer` (which carries `provenance`). Pairs with conflict logging (a conflict
entry should cite BOTH sides' provenance). Likely needs a provenance-carrying variant of
`permission_levels` (specificity -> representative/again per-layer provenance).

## Comment cleanup decided (config.py module docstring)
The "Privatisation notes" enumeration (config.py:25-42) + the `bash_permissions`
"byte-for-byte identical / stderr diagnostics" rationale (lines ~19-22) are drift-prone and
the latter is already STALE (bash_permissions is off the live path post-Phase 2). Plan:
keep the durable "Public abstraction" paragraph; replace the rest with one sentence noting a
few loaders stay public only for not-yet-migrated non-test callers (transitional; tracker
holds specifics). Pending Arnon's go-ahead.

## Phase 4 outcome (2026-06-17) -- UNCOMMITTED, ready for review

Implemented + code-reviewed (no critical/major) + green: 672 tests with AND without
CLAUDE_SETTINGS_PATH; ruff clean; >90% on changed code.

Delivered (per the decided design):
- Four log streams: resolution (`toolguard-*`), errors-only (`toolguard-error-*`),
  warnings (`toolguard-warning-*`), conflicts (`toolguard-conflict-*`). `error_log.py`
  routes each via `log_error`/`log_warning`/new `log_conflict`.
- Takeover notice removed from logs (stderr + once-per-session marker only).
- Conflict logging (allow-over-deny overrides only): `resolve_permission_detailed` +
  `_detect_override`; decision stays the more-specific allow; conflict entry cites both
  provenances + command. hard_deny denials stay in the resolution log (not conflicts).
- Rule provenance in reasons: `permission_levels_with_provenance` + `_provenance_for_pattern`,
  appended as bracketed `[level: path]` suffix (preserves existing reason-substring
  assertions). Bash + compound + Read/Write/Edit.
- Once-per-session discovery diagnostic (`log_writer.log_discovery`) in the resolution log.
- M1: single source for the both-`.toml`/`.json` warning (`validation_issues` -> warning
  stream); legacy stderr print removed from `discover_config_files`.
- Fix pass: validation Issues route by `issue.level` (error->error stream, else->warning);
  docstring/comment nits (log_discovery, match_command coupling note); `issue_takeover_warning`
  `to_stdout` kept (12 test call sites) with a clarified docstring (writes stderr).

Coder choices accepted: kept `resolve_permission`/`resolve_file_path_permission` as 2-tuples
(cascade tests pin them) and added `*_detailed` variants the hook drives; removed dead
`_decide_file_path_at_level`.

Changed: error_log.py, session_warnings.py, log_writer.py, permissions.py, config.py,
hook.py, technical-notes.md; tests test_logging_streams.py (NEW), test_session_warnings.py,
test_toml_config.py, test_hook.py. Reports in basic-memory `implementation/`. Nothing
committed; Arnon does git.