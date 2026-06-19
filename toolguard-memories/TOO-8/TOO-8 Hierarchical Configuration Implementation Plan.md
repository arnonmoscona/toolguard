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


## STATUS UPDATE (2026-06-18) -- supersedes the stale header

Phases 1-5 are COMMITTED. (The top-of-note "Status:" block is stale -- it predates the
Phase 4/5 commits.) Phase 6 is IN PROGRESS.

### Phase 5 outcome (2026-06-18) -- COMMITTED
Non-permission cross-level resolution + folded-in code-review fixes + an approved legacy
dead-code sweep. Delivered:
- `Configuration.scalar()` -> MORE-SPECIFIC-WINS (first defining layer wins); config_sync
  + no_match_fallback follow. Pin test renamed to `test_config_sync_conflict_is_project_wins`;
  Phase-2 FIXMEs cleared.
- `governed_tools()` + takeover pattern lists stay UNION across all layers.
- `takeover_mode.enabled` -> single-owner + fail-safe-on-conflict: 0 set => OFF; all agree
  => that value; disagree => fail-safe OFF + `TakeoverEnabledConflict` (values+provenance).
  Hook logs the conflict once/session (`log_conflict`) + session warning.
- Non-bool `takeover_mode.enabled` no longer coerced (fail-safe security toggle): it does
  not vote, and `validation_issues()` reports it as an error.
- DRY: `_CONFIG_SYNC_DEFAULTS` centralizes config_sync defaults.
- Legacy dead-code REMOVED (no production callers, confirmed with grep -rn incl.
  toolguard/scripts/): `Configuration.bash_permissions()`, the `_load_governed_tools`
  cluster, and the `_load_permissions`/`_load_permissions_from_file`/`_merge_permissions`
  cluster + all their tests. `load_takeover_mode_config()` was KEPT (scripts/migrate_permissions.py
  still calls it) and documented as transitional. (Near-miss: an `ag` sweep returned empty
  for load_takeover_mode_config; not reproducible / not an ag ignore behavior; `grep -rn`
  caught the caller. Lesson: confirm negative "no callers" results with grep before deleting.)
- 645 tests green WITH and WITHOUT CLAUDE_SETTINGS_PATH; ruff clean.
- Reports: basic-memory `implementation/phase-5-review-fixes-implementation-report`.

### Phase 6 -- IN PROGRESS (design decided with Arnon 2026-06-18)
SessionStart conflict-alert hook. Decisions: SEPARATE entry point
`toolguard-session-start = "toolguard.session_start:main"`; ALL conflict detection at
SessionStart (NO tool-use-time markers); nag every session while conflicts remain
("until resolved"); brief summary emitted to STDOUT so Claude ingests it as context.
Detection sources at startup: STATIC takeover conflict recomputed live from
`takeover_mode().conflict` (self-clears when fixed) + DYNAMIC/recorded conflicts surfaced
by reading the `toolguard-conflict-*.md` log (dynamic allow-over-deny can't be recomputed
statically). Delegated to feature-coder.

### Phase 7 -- IN PROGRESS (scope decided with Arnon 2026-06-19)
Docs restructure + doc-debt. Decisions:
- **Docs split into `docs/` files** (thin README index + topic files): README.md (index),
  docs/quickstart.md, docs/configuration.md, docs/patterns.md, docs/takeover-mode.md,
  docs/config-sync.md, docs/security.md, docs/agent-guides.md (NEW few-shot agent guides),
  docs/architecture.md. technical-notes.md stays as dev/TOO-8 internals.
- **run_hook.sh: DOCUMENT-ONLY, do NOT retire** (retirement = TOO-16 per distribution-model
  memory). Phase 7 only adds a forward-looking note to the future uv-tool-install model.
- **Docs-only phase**: the "confirm hierarchical Bash takeover-filtering coverage" check is
  tracked as a SEPARATE follow-up, NOT done here.
- Execution: main agent inline (Arnon's choice).
- STALE doc-debt items (overtaken by Phases 4/5, do NOT action): `bash_permissions`
  "legacy off live path" note (removed in P5), `_load_permissions` stderr diagnostics
  (removed in P5), code-review M1 both-formats warning consolidation (done in P4),
  config.py module-docstring "Privatisation notes" cleanup (already trimmed).
- STILL-VALID doc-debt: name `resolve_compound_permission` + note `check_compound_permission`
  retained but OFF the live path (technical-notes.md + docs/architecture.md).

### Phase 7 outcome (2026-06-19) -- UNCOMMITTED, pending Arnon's review
Docs restructure done by main agent inline. README (was 1570 lines) is now a thin index
(description, motivation/goals, doc nav table, requirements/install/testing). Content split
into docs/: quickstart.md, configuration.md (config ref + env vars + hierarchy), patterns.md,
takeover-mode.md, config-sync.md (+ session warnings), security.md, agent-guides.md (NEW
few-shot agent recipes), architecture.md. technical-notes.md kept as dev internals + new
paragraph naming `resolve_compound_permission` (live) and `check_compound_permission`
(retained, OFF live path). Doc-debt folded: TOO-16 distribution/`toolguard` entry-point note
added document-only (run_hook.sh NOT retired). Stale items confirmed obsolete and skipped
(bash_permissions/_load_permissions removed in P5, M1 done in P4, docstring already trimmed).
Fixed stale facts while migrating: Python >=3.14 (pyproject), 683 tests, 4 log streams
(warnings now toolguard-warning-*.md), package/test file lists, removed nonexistent
toml_config.py/validation.py from structure. All internal doc links/anchors verified.
No .py changes; suite still 683 OK. Nothing committed; Arnon does git.

Follow-up (Arnon, same day): pulled the uv-tool-install/entry-point hook docs forward from
the "document-only" stance into concrete instructions (Arnon's explicit request). README
Installation now leads with `uv tool install` (-> `~/.local/bin/toolguard` +
`~/.local/bin/toolguard-session-start`, bin dir confirmed via `uv tool dir --bin`) and
stresses that installing != working (hooks must be registered). quickstart.md gained a
"0. Install" step + a "Register the hooks" step covering BOTH PreToolUse (`toolguard`) and
the recommended SessionStart (`toolguard-session-start`), with a wrapper-based alternative
(run_hook.sh for PreToolUse; `.venv/bin/python -m toolguard.session_start` for SessionStart).
configuration.md Step 1 note de-staled (dropped the "future TOO-16" framing). run_hook.sh
still NOT retired. NOTE vs distribution-model memory: the uv-tool hook-wiring docs that were
slated for TOO-16 are now partly in TOO-8 Phase 7 docs; TOO-16 still owns packaging/testing
and actual run_hook.sh retirement.

Follow-up 2 (Arnon, same day): grounded setup docs in real config
(/home/arnon/projects/flowers/featherhill/.claude/). Changes: quickstart Step 1 now registers
PreToolUse hooks for ALL governable tools (Bash, mcp__jetbrains__execute_terminal_command,
mcp__local-tools__checked_bash, Read, Write, Edit) not just Bash; Step 2 now shows full
governed_tools + additional_supported_tools (with the "custom MCP tools need it / built-ins
don't" explanation). agent-guides.md gained a leading "install and register from scratch"
recipe (same full multi-tool setup). README: added prominent "AI agents start here" callout
pointing to docs/agent-guides.md (was just a table row -- insufficient). Agent-entry
convention (Arnon chose BOTH): created root llms.txt (llmstxt.org doc map) + AGENTS.md (broad
coding-agent auto-pickup), both routing agents to docs/agent-guides.md first; AGENTS.md also
splits "configuring toolguard for a user" (-> agent-guides) vs "modifying the repo"
(-> CLAUDE.md). All links verified. Still docs-only; nothing committed.

Follow-up 3 (Arnon, same day): (a) Added GLOBAL/user-level setup option throughout. quickstart
Step 1 gained "One project, or all projects" (hooks in project `.claude/settings.local.json`
vs global `~/.claude/settings.json`); Step 2 gained per-project vs `~/.claude/toolguard_hook.toml`
baseline (least-specific level, projects layer on top). agent-guides setup recipe steps 2 & 3
updated likewise. (b) README Installation section SLIMMED to a 3-step map (base install / hook
config / governed-tools config) that links into quickstart anchors -- removed all the
duplicated uv-tool/editable verbiage to kill drift; quickstart Step 0 is now the canonical
install reference (absorbed the editable-install alternative + upgrade note). All links/anchors
re-validated via python. Still docs-only; nothing committed.

Follow-up 4 (Arnon, same day): replaced the defunct/personal `mcp__local-tools__checked_bash`
example everywhere (quickstart, agent-guides, configuration). Web research finding: there is
NO canonical stable equivalent to `mcp__jetbrains__execute_terminal_command` -- JetBrains
ships an official MCP server with that fixed tool name; VS Code command tools come from
varied third-party MCP servers, and Cursor's `run_terminal_cmd` is a built-in (not an MCP
tool Claude Code sees). So docs now keep Bash + jetbrains as the two CONCRETE command-tool
examples and represent "other editors' tools" generically: naming convention
`mcp__<server>__<tool>`, name VS Code/Cursor terminal MCP servers as the category, and tell
the reader to run `/mcp` for the real name. TOML examples use a commented-out
`# "mcp__your_terminal_server__run_command"` placeholder in both additional_supported_tools
and governed_tools (no fabricated tool string). JSON blocks re-validated. Still docs-only.

Follow-up 5 (Arnon, same day): SHIFT from earlier "keep run_hook.sh as editable alt" --
Arnon now wants the `toolguard`/`toolguard-session-start` ENTRY POINTS as the single best
practice everywhere; scrub run_hook.sh + `python -m toolguard.hook/session_start` from all
USAGE docs. New uniform rule: uv-tool install -> `~/.local/bin/toolguard[-session-start]`;
editable install -> `<checkout>/.venv/bin/toolguard[-session-start]` (console scripts exist
in the venv too -- no wrapper, no `python -m`). Edited: configuration.md (JSON x5 + Important
note), takeover-mode.md (JSON x4), quickstart.md (Step 0 editable note + Step 1 section
renamed "Alternative: editable install", anchor now #alternative-editable-install, JSON uses
.venv/bin entry points), agent-guides.md (editable rule). architecture.md: hook-flow diagram
node run_hook.sh->`toolguard`/`toolguard.hook:main`; package-structure run_hook.sh line KEPT
but recomment'd as "Legacy hook wrapper" (file still exists; not retired -- retirement is
TOO-16). Only surviving run_hook.sh mention = that legacy listing line. `python -m
toolguard.scripts.migrate_permissions` refs are the migration CLI (correct, untouched). JSON
+ links + anchors all validate. Still docs-only; nothing committed.

Follow-up 6 (Arnon, same day): (a) quickstart Step 2 now links to the recognition-vs-governance
distinction (configuration.md#declaring-additional-supported-tools), softened "must"->"should".
(b) Documented `ignored_allow_patterns` properly wherever takeover/bypass mode is covered,
VERIFIED against code first. Verified facts: 5 built-in defaults (Bash(*)/Read(*)/Write(*)/
Edit(*)/mcp__jetbrains__execute_terminal_command(*)) ALWAYS seeded when takeover enabled
(_DEFAULT_IGNORED_ALLOW_PATTERNS config.py:50); both ignored_allow_patterns +
additional_ignored_patterns are ADDITIVE unions over defaults (cannot remove a default;
config.py:946,967-972); filtering applies ONLY to NATIVE settings.json/.local.json allow
entries (layer.is_native, config.py:1108), NOT toolguard_hook files; allow-only (not deny);
EXACT match after wrapper strip; only when takeover.enabled. Edits: takeover-mode.md (precise
"how it works" filter sentence + new "### Ignored allow patterns" subsection + corrected the
misleading "default list shown"/"beyond defaults" comments); configuration.md reference block
takeover comments corrected likewise. All TOML/JSON/links/anchors validate. Docs-only.

Follow-up 7 (Arnon, same day): explained WHY divergence is natural/unavoidable. Mechanism:
Claude Code hits an "ask", user picks "Yes, don't ask again", Claude writes a new allow into
its own settings.local.json -- it knows nothing about toolguard, so it diverges from
toolguard_hook.toml. Cannot be turned off (how Claude's prompts work); goal is to MANAGE not
prevent (tooling now, more automation later, or manual). Added "### Divergence is normal --
you cannot prevent it" subsection to config-sync.md, and a matching "Expect this -- it is
unavoidable" note to the agent-guides clean-up recipe (user wanted users AND agents to know).
Docs-only; links/anchors validate.

Follow-up 8 (Arnon, same day): renamed docs/patterns.md -> docs/permission-patterns.md
(clearer in a bare dir listing; "patterns" too generic). Chose permission-patterns over
command-matching-patterns because the file ALSO covers file-path patterns + normalization +
compound commands (command-only name would under-scope). Updated H1 "Pattern Reference" ->
"Permission Patterns" and all 6 referring links (README, llms.txt, agent-guides, quickstart,
configuration x2) + their link text. NOTE: docs/ is now git-TRACKED (Arnon committed it some
point), so the rename was a plain `mv` (filesystem) -- Arnon stages/commits the rename
(git will detect it); I did NOT run git mv. Links/anchors validate.

Follow-up 9 (Arnon, same day): expanded security.md with two new sections. (a) "Ongoing
security review" -- routine of reviewing resolution/error/warning/conflict logs + divergence,
as a cadence table mapping each review task to its supporting facility (log streams + matched-
rule provenance, session warnings, SessionStart conflict-alert hook, migrate_permissions
--dry-run), plus an automated-vs-on-you split and a quick-pass command block. (b) "Maintaining
your toolguard configuration" -- best practices: keep rules sorted (auto_sort_on_migrate),
consolidate similar rules into fewer regex/glob (with a critical-thinking caution: consolidate
scope not breadth -- don't collapse to Bash(git:*)), manage divergence, promote shared rules
up to user level + keep project level lean, use Claude to review rules ("report, don't edit";
human owns final call), and watch for stray rules from hasty "always allow" answers. All
links/anchors validate. Docs-only. NOTE: security.md multi-line guarantee is still TOO-17's
to add (not done here).
Follow-up 10 (Arnon, same day): added 4 more maintenance best practices to security.md
(now 10 bullets): comment rules to record intent; version-control config + review diffs
(settings.local.json gitignored, never commit secrets/~/.claude); defense-in-depth explicit
denies/hard_deny (don't rely on absence-of-allow); use the `ask` tier for impactful-but-
reversible ops. (Candidates 5 prune-obsolete, 6 test-denies-fire/re-verify-after-upgrade,
7 single-owner-for-takeover/hard_deny were offered but NOT added -- available if wanted.)
Links/anchors validate.

Follow-up 11 (Arnon, same day): removed the "Alpha" designation from takeover mode (it has
been in real use and works). Edits: takeover-mode.md H1 (-> "# Takeover Mode") + intro callout
(dropped "alpha", kept the read-security-warnings/test-first caution); README doc-nav row
("alpha" removed). Only remaining "alpha" = config-sync.md "alphabetically" (unrelated).
Done via the JetBrains MCP replace_text_in_file (new workflow: edit IDE-open docs through the
IDE so changes show immediately; recorded as auto-memory feedback edit-via-ide-mcp).

### !! SECURITY FINDING (2026-06-19) -> TICKET TOO-17 (show-stopper)
TOO-17 created by Arnon for the multi-line Bash fail-open bypass below. Folded into the
current effort: it BLOCKS publishing the updated TOO-8 docs and will be done before release.
Expected to be LARGE -- non-trivial parser change (PEG grammar + extractor) plus extensive
unit tests. When starting TOO-17 implementation, use the feature-coder subagent (non-trivial).
The multi-line DOC discussion (permission-patterns.md compound section + security.md) is part
of TOO-17 scope, NOT this docs pass. Ticket draft source: /tmp/too-multiline-bash-bypass-ticket.md.

#### Original finding -- multi-line Bash fail-OPEN bypass
Discovered while documenting compound commands. VERIFIED end-to-end:
- Grammar parses only a SINGLE logical line: `spacing=[ \t]*` (no newline), no newline
  control_op. Newline-separated command => parse FAILS => command_extractor safety net
  returns the WHOLE blob as ONE command (logs "Parse failed"); NOT split.
- fnmatch is DOTALL, so DEFAULT allow `git status:*`(->`git status*`) matches across the
  newline; DEFAULT/glob/native deny is start-anchored so it misses later lines.
- NET: with allow `Bash(git status:*)` + deny `Bash(rm -rf:*)`, input "git status\nrm -rf /"
  => ALLOW (rm -rf runs). Single-line "git status && rm -rf /" correctly => DENY. FAIL-OPEN.
- Backslash continuation parses but stays one undecomposed command (same one-unit effect).
- Mitigation that works TODAY: `[regex]` deny (re.search scans whole string incl. newlines)
  e.g. `Bash([regex]rm\s+-rf)` => denies the blob. Start-anchored deny does not.
Files: toolguard/parser/bash_parser.peg (spacing/control_op), parser/command_extractor.py
(fallback returns [whole]), permissions.py match_command (fnmatch DOTALL).
STATUS (2026-06-19): Arnon's call -> draft ticket as a SHOW-STOPPER; he files it. Ticket
markdown drafted + copied to clipboard (source /tmp/too-multiline-bash-bypass-ticket.md):
title "Multi-line Bash commands bypass permission checks (fail-open)", with repro, root
cause (3 factors), fix options (A decompose-by-line recommended + C no-DOTALL backstop + B
fail-closed fallback), acceptance criteria w/ tests, and DOCS-update requirements folded IN.
DECISION: fix this BEFORE publishing the updated TOO-8 docs. The multi-line doc discussion
(permission-patterns.md compound section + security.md) is DEFERRED to that new ticket -- do
NOT document multi-line in this docs pass. This is a security item: do NOT drop/compact it.

### !! PRE-COMMIT REMINDER (Arnon, 2026-06-19)
Arnon is still REVIEWING the Phase 7 docs. He asked to be REMINDED, before any commit of
this work, to decide whether to pick up the two open follow-ups below first
(migrate_permissions off load_takeover_mode_config; hierarchical-Bash takeover-filtering
coverage check). => When Arnon signals he is about to commit / ready to commit, surface
these open items BEFORE he commits.

### Follow-ups still open
- Migrate `scripts/migrate_permissions.py` off `load_takeover_mode_config` onto
  `Configuration.takeover_mode`, then drop the last legacy loader (TOO-8 follow-up).
- Confirm the live hierarchical Bash takeover-filtering path is covered by newer tests
  (the removed legacy tests exercised it via `_load_permissions`) -- Phase 7 / coverage pass.
- Phase 7: README restructure + doc-debt (resolve_compound_permission naming, TOO-16
  distribution model, run_hook.sh retirement).
