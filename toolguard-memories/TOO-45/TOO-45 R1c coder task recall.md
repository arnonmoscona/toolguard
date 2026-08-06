---
title: TOO-45 R1c coder task recall
type: note
permalink: toolguard/too-45/too-45-r1c-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Implement TOO-45 R1c on branch `too-45`: collapse `ResolvedDecision` (config_types.py),
`BashResolution` and `FileResolution` (resolve.py) into ONE runtime verdict type carrying
`tool`/`target`. Rename `SubMatch` -> `UnitVerdict`. Refine the R1 architecture-fitness
predicate to gate on exactly one RUNTIME verdict type, with the unit (UnitVerdict) and
tooling (`tools.decision.Decision`) altitudes derived structurally and reported with reasons
-- not hand-coded by class name.

Full brief was at `/tmp/claude-1000/.../scratchpad/r1c_brief.md` (ephemeral). Source of the
measurements: basic-memory `TOO-45/TOO-45 R1 scoping trace.md` -- do not re-derive.

Out of scope: `log_command`/`create_hook_output` signatures (R1d), compound audit breakdown
(R1e), unifying `tools.decision.Decision` (R6).

## Design decisions made before coding

**Type name: `RuntimeVerdict`** (config_types.py), replacing ResolvedDecision/BashResolution/
FileResolution. Matches the "runtime verdict" altitude language from the scoping trace
exactly, and is deliberately parallel to `UnitVerdict` (unit altitude) and `Decision`
(tooling altitude, unrenamed).

**Home: config_types.py**, not resolve.py. permission_resolution.py must only import
config_types (never resolve.py -- resolve.py imports permission_resolution, so the reverse
would be circular). Since permission_resolution.py constructs the per-level/per-sub-command
raw verdict directly, the merged type has to live where it already lives (config_types.py
already held Provenance/ConflictOverride, so no more `Any`-typed fields needed for
provenance/overrides -- an incidental typing improvement over the old BashResolution/
FileResolution which used `Any` to dodge a circular import with config.py).

`UnitVerdict` (renamed SubMatch) also moves to config_types.py for the same reason: it needs
no circular-import-avoiding `Any` either once there.

resolve.py re-exports both (`from toolguard.config_types import RuntimeVerdict as
RuntimeVerdict, UnitVerdict as UnitVerdict`) so `from toolguard.resolve import
RuntimeVerdict/UnitVerdict/resolve_bash_permission_detailed/resolve_file_path_permission_detailed`
keeps working -- resolve.py's docstring "Result dataclasses" section gets rewritten to explain
the split-home. config.py's existing `ResolvedDecision as ResolvedDecision` re-export line
becomes `RuntimeVerdict as RuntimeVerdict` (same convention, continuing the pre-existing
re-export).

**overrides field reconciliation** (Q3 of the scoping trace: "a unified type has to pick, and
the list generalises"): `overrides: List[Tuple[Optional[str], ConflictOverride]]` uniformly.
- Bash compound (resolve_bash_permission_detailed): identifier = sub_command string (unchanged
  behavior from today's `List[Tuple[str, ConflictOverride]]`).
- File path (resolve_file_path_permission_detailed): identifier = file_path (== target),
  0-or-1 entries.
- Internal single-level (permission_resolution.py's `_resolve_unclamped`): identifier = None
  (no sub_command/target in scope at that layer); re-paired with the real identifier by
  resolve.py's two public wrapper functions.
hook.py's file-path handler changes from a single `_log_conflict_override(log_target,
result.override, ...)` call to `for _, override in result.overrides:
_log_conflict_override(log_target, override, ...)` -- behaviourally identical (0 or 1
iterations; old code's None-override call was already a no-op inside `_log_conflict_override`).
hook.py's Bash handler loop (`for sub_command, override in result.overrides:`) is UNCHANGED,
already matches the new shape.

**tool/target population**: fields default `Optional[str] = None`. Only resolve.py's two
public entry points populate them (`tool="Bash", target=command` /
`tool=tool_name, target=file_path`) -- permission_resolution.py's internal single-level
verdict leaves them None, since it never has the target string in scope (decide_detailed
closures capture it, resolve_permission_detailed's own signature doesn't receive it). Matches
"nothing consumes them yet" from the brief -- R1d is the consumer.

**Predicate altitude classification (tools/architecture_fitness.py)**: add
`classify_verdict_altitudes()` on top of the existing structural `find_verdict_types()`
(unchanged detector). Two structural, DERIVED rules, no hand-listed class names:
- UNIT altitude: a verdict-ish class referenced via a `List[X]` field type (searched via
  `ast.unparse` on each field's annotation, substring/regex match) inside ANOTHER verdict-ish
  class. Catches UnitVerdict (nested in both RuntimeVerdict.sub_matches and
  Decision.sub_matches).
- TOOLING altitude: package-derived, `first_segment(module) in R1_TOOLING_PACKAGES =
  ("tools",)` -- mirrors the already-accepted `R1_OUT_OF_SCOPE_PACKAGES` precedent (single
  hand-declared PACKAGE name with a printed reason, not a per-class list). Catches
  `tools.decision.Decision`.
- Runtime = everything else structurally verdict-ish. Gate: `pass = len(runtime) == 1 and
  len(iter_shims) == 0`.
Each excluded entry must print its reason in `--predicates` text output (container+field for
unit; package for tooling).

## Files expected to touch (production)

- toolguard/config_types.py -- define RuntimeVerdict + UnitVerdict, remove ResolvedDecision
- toolguard/resolve.py -- remove SubMatch/BashResolution/FileResolution defs, import+re-export
  from config_types, update both resolver functions' construction sites, docstring rewrite
- toolguard/permission_resolution.py -- import RuntimeVerdict instead of ResolvedDecision,
  rewrite all construction call sites to kwargs + new overrides shape
- toolguard/hook.py -- file-path override call site loop change; doc comment renames
  (BashResolution/FileResolution/ResolvedDecision/SubMatch -> RuntimeVerdict/UnitVerdict)
- toolguard/tools/decision.py -- import UnitVerdict instead of SubMatch; type annotation update
- toolguard/config.py -- re-export line rename
- toolguard/log_writer.py, toolguard/compound.py -- doc comment renames only
- tools/architecture_fitness.py -- classify_verdict_altitudes, R1 predicate gate change,
  render_predicates_text R1 section rewrite

## Test files expected to touch

- test/unit/test_resolve.py (~80, mostly import/isinstance renames)
- test/unit/test_logging_streams.py (~25 -- includes REAL shape adaptation: `.override` ->
  `.overrides` list, not just import renames, since it tests
  `permission_resolution.resolve_permission_detailed` directly)
- test/unit/test_architecture.py (TestReExportIdentity: RE_EXPORTED_TYPES tuple entry rename)
- test/unit/test_tools_decision.py (SubMatch -> UnitVerdict import + isinstance)
- test/unit/test_architecture_fitness.py (TestFindVerdictTypes real-tree assertions update to
  new names; ADD new tests for classify_verdict_altitudes -- additive, per testing policy)
- test/unit/test_hierarchical.py, test/unit/test_hook.py, test/unit/test_configuration.py --
  comment-only references, doc-drift sweep

## Hard rules reminder

No git writes. No repo copies. Backups to
`/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1c-backups/`
verified with sha256sum. uv run python only. unittest not pytest. ruff check --no-cache. No
verdict may change (corpus_build.py --verify must be clean).

## Report destination

basic-memory `toolguard`, `TOO-45/TOO-45 R1c implementation report.md`, tags task-memory +
TOO-45.
