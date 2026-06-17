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

Status: Phase 1 IMPLEMENTED + code-reviewed + green (2026-06-16), UNCOMMITTED.
Next: revisit Phases 2+ against the real abstraction. See "Phase 1 outcome" at end.

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

Standing exit criterion for every phase: full unit tests with >90% coverage for the
phase's changes; existing tests still pass.

- **Phase 0 -- Finalize spec (no code).** Sub-decisions resolved; Phase 1 design sign-off
  outstanding. Update auto-memory.
- **Phase 1 -- Config abstraction refactor (behavior-preserving).** Implement the model +
  internal sourcing/parsing; migrate ALL clients (hook, validation, file-path patterns,
  governed_tools, takeover, divergence, auto-migrate) to the public API. Keep 2 levels and
  current resolution. Success: existing tests pass unchanged; no client outside config
  touches files/formats. THEN revisit Phases 2+ against the real abstraction.
- **Phase 2 -- Traversal + more-specific-wins.** Sourcing walks project_root -> ~ collecting
  `.claude/toolguard_hook{,.local}.{toml,json}` + `settings{,.local}.json` per dir (toggle-
  gated). Level-aware resolver: most-specific first, first matching level decides, deny-first
  within level. Wire command + file-path paths. Should be simpler given Phase 1.
  Phase 2 also includes this cleanup (do AFTER external callers are migrated so nothing
  imported elsewhere gets renamed out from under it):
  - Migrate `config_divergence.py` (`check_and_warn_divergence`) and `auto_migrate.py`
    off `discover_config_files`/direct file opens onto the `Configuration` abstraction
    (the Phase 1 deferral).
  - **Eliminate the tool-prefix duplication.** Today the `Tool(...)` wrapper-strip list is
    hand-maintained in THREE places that have already drifted: `config.py:478`
    `_tool_prefixes` (legacy shim), `config.py:597` `_TOOL_PREFIXES`, and
    `config_divergence.py:131` `governed_tool_prefixes` (only 4 entries -- omits the
    jetbrains tool). Collapse to one: prefer a STRUCTURAL strip
    (`re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)', pattern)`, which needs no known-tool list and
    still handles inner parens like `Bash(foo(bar))`), or a single source of truth derived
    from the governed/known tool set. Route all call sites through `_strip_tool_wrapper`.
  - **Underscore-prefix strictly-internal config.py functions** once they have no
    out-of-module callers, e.g. `find_project_root` -> `_find_project_root`,
    `discover_config_files` -> `_discover_config_files`, and the legacy loaders
    (`load_permissions*`, `merge_*`, `load_governed_tools*`, `load_takeover_mode_config`,
    `config_sync_settings_from_sources`). Keep only `load_configuration` + the public
    dataclasses unprefixed. Update any test imports/patches accordingly.
- **Phase 3 -- hard_deny.** `[hard_deny]` per level; collected across all; checked first;
  unoverridable.
- **Phase 4 -- Logging streams + conflict logging.** Separate error / warning / conflict /
  resolution logs. Error log = real errors only. Reclassify takeover "informational" message
  out of warnings (it is a notice). Resolution log emits a warning pointing to conflict log
  when a conflict occurs. (Non-error-noise cleanup is independent; may be pulled earlier.)
- **Phase 5 -- Non-permission config cross-level.** Apply decision 4 semantics on the model;
  implement takeover special-case (fail-safe OFF + loud conflict). Smaller after Phase 1.
- **Phase 6 -- SessionStart conflict-alert hook.** New hook surfacing prior-session conflicts
  at startup.
- **Phase 7 -- Docs restructure.** Split oversized README into: thin index README; beginner
  opinionated quick-start; agent-oriented token-efficient few-shot guide (likely split by
  topic: initial setup / Claude->toolguard migration / maintaining config / hierarchy setup).

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