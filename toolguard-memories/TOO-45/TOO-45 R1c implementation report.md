---
title: TOO-45 R1c implementation report
type: note
permalink: toolguard/too-45/too-45-r1c-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Implemented TOO-45 R1c on branch `too-45`: collapsed `ResolvedDecision`, `BashResolution`, and
`FileResolution` into one runtime verdict type, `RuntimeVerdict`, carrying `tool`/`target`.
Renamed `SubMatch` to `UnitVerdict`. Refined the R1 architecture-fitness predicate to gate on
exactly one RUNTIME verdict type, with the unit and tooling altitudes derived structurally
(never hand-listed by class name) and reported with their exclusion reason in `--predicates`
output.

## Chosen type name and why

**`RuntimeVerdict`**. The R1 scoping trace's own language names three altitudes -- "unit
verdict", "runtime verdict", "tooling verdict" -- and the brief asked for a name that makes the
collapsed type's altitude visible, the same reasoning behind the `SubMatch` -> `UnitVerdict`
rename. `RuntimeVerdict` says exactly what it is (the type every governed-tool resolution
returns at runtime) and reads naturally alongside its siblings: `UnitVerdict` (nested inside
it), and `tools.decision.Decision` (the tooling altitude, deferred to R6, left unrenamed since
renaming it is R6's decision to make).

## Where the collapsed types live, and why

Both `RuntimeVerdict` and `UnitVerdict` are defined in `toolguard/config_types.py`, not
`toolguard/resolve.py` (where `BashResolution`/`FileResolution`/`SubMatch` used to live).
`toolguard/permission_resolution.py` constructs the per-level/per-sub-command verdict directly
and is architecturally forbidden from importing `toolguard.resolve` (that module imports FROM
`permission_resolution`, so the reverse would be circular). `config_types.py` is the shared leaf
both modules can import. `resolve.py` re-exports both (`from toolguard.config_types import
RuntimeVerdict as RuntimeVerdict` / `UnitVerdict as UnitVerdict`) so every existing `from
toolguard.resolve import ...` call site keeps working.

Incidental improvement: `Provenance` and `ConflictOverride` are also defined in
`config_types.py`, so `RuntimeVerdict.provenance`/`.overrides` are now typed precisely instead
of falling back to `Any` the way `BashResolution`/`FileResolution` had to, to dodge a circular
import with `toolguard.config`.

## `overrides` field reconciliation

`BashResolution.overrides` was a `List[(sub_command, ConflictOverride)]`; `FileResolution`/
`ResolvedDecision.override` was a single `Optional[ConflictOverride]`. Per the scoping trace's
Q3 ("a unified type has to pick, and the list generalises"), `RuntimeVerdict.overrides` is now
uniformly `List[Tuple[Optional[str], ConflictOverride]]`:

- Bash compound (`resolve_bash_permission_detailed`): identifier = the sub_command string,
  unchanged from the old shape.
- File path (`resolve_file_path_permission_detailed`): identifier = the file path itself
  (`== target`); 0 or 1 entries.
- The internal per-level verdict (`permission_resolution.resolve_permission_detailed`):
  identifier = `None` (no sub_command/target string is in scope at that layer -- `decide_detailed`
  closures capture the target privately and the function signature never receives it). The two
  public `resolve.py` entry points re-pair the bare override with the real identifier once they
  have one.

`hook.py`'s file-path handler changed from a single `_log_conflict_override(log_target,
result.override, ...)` call to `for _, override in result.overrides:
_log_conflict_override(log_target, override, ...)` -- behaviourally identical (0 or 1
iterations; the old call with `override=None` was already a no-op inside
`_log_conflict_override`). The Bash handler's loop was already list-shaped and needed no change.
This was verified not just by reasoning but by the corpus (`--verify`, no differences) and by
`test_logging_streams.py`'s conflict-logging assertions (all still passing).

## `tool`/`target` population

Both fields default `Optional[str] = None`. Only `resolve.py`'s two PUBLIC entry points
populate them (`tool="Bash", target=command` / `tool=tool_name, target=file_path`), since only
they have the actual command/file_path string in scope. The internal per-level verdict built by
`permission_resolution.resolve_permission_detailed` leaves both `None`. Nothing consumes them
yet, per the brief -- that is R1d's job.

## Predicate refinement: how the altitude split is structural, not hand-coded

Added `classify_verdict_altitudes()` in `tools/architecture_fitness.py`, layered on top of the
existing (unchanged) structural `find_verdict_types()` detector. Two DERIVED rules, no class
name hard-listed anywhere:

- **UNIT altitude**: a verdict-ish class embedded via a `List[...]` field type INSIDE another
  verdict-ish class. Detected by re-parsing every verdict-ish class's own field annotations
  (`ast.unparse`) and regex-searching each for another verdict-ish class's name inside a
  `List[...]` subscript. This catches `UnitVerdict` because it is referenced by
  `RuntimeVerdict.sub_matches: List[UnitVerdict]` AND (independently) by
  `Decision.sub_matches: Optional[List[UnitVerdict]]` -- being nested in TWO different
  containers is itself corroborating structural evidence that it is a shared leaf record, not a
  top-level verdict.
- **TOOLING altitude**: a verdict-ish class whose module lives under `R1_TOOLING_PACKAGES =
  ("tools",)` -- a single hand-declared PACKAGE name with a printed reason, the identical shape
  to the already-accepted `R1_OUT_OF_SCOPE_PACKAGES` precedent (one name, not a per-class list),
  and the package boundary itself is not invented for this predicate -- `resolve.py`'s own
  module docstring already names it: "the replay / tooling layer
  (`toolguard.tools.decision`)". This catches `tools.decision.Decision`.
- **RUNTIME altitude**: everything `find_verdict_types` found that is neither of the above.

Verified live on the real tree: runtime = `[RuntimeVerdict]` (exactly 1), unit = `[UnitVerdict]`
(nested inside both `RuntimeVerdict.sub_matches` and `Decision.sub_matches`), tooling =
`[Decision]` (package `tools`). The R1 gate is now `len(altitudes["runtime"]) == 1 and
len(iter_shims) == 0`. `--predicates` text output prints each excluded class with its reason
(`nested inside: ...` / `package '...'`), matching `r1_out_of_scope_modules`'s existing pattern
of printing the parser exclusion.

I considered and rejected a name-based exclusion list (`{"UnitVerdict", "Decision"}` hardcoded)
-- that is exactly the "loosening a predicate by declaring exclusions" trap the brief warned
against. The nesting rule and the package rule both generalize: a future class embedded in
another verdict's collection field is unit-altitude regardless of its name; a future class added
under `toolguard/tools/` is tooling-altitude regardless of its name. Both rules were added as
NEW tests in `test_architecture_fitness.py` (`TestClassifyVerdictAltitudes`, 4 tests) using
synthetic fixture trees with deliberately unrelated class names (`Container`/`Leaf`,
`ToolingThing`) specifically to prove the rules are structural, not keyed to the real class
names -- plus a real-tree acceptance test.

## Test count and enrichment footprint (before/after)

- Suite: 2333 -> 2337 tests, all OK. +4 are the new `TestClassifyVerdictAltitudes` tests
  (additive, per testing policy). Zero tests deleted, zero weakened -- confirmed by diffing
  every edited test file against its pre-edit backup.
- Corpus: 6,401 in-process + 61 end-to-end, **no differences**, both before and after.
- Enrichment footprint (the R1 pre-registered acceptance instrument): **69 -> 68** total
  identifier-level occurrences. `resolve.py` dropped from 10 to 8 (the two classes'
  `additional_context` mentions that used to be duplicated across `BashResolution`'s and
  `FileResolution`'s separate docstrings are now stated once, in `RuntimeVerdict`'s single
  docstring in `config_types.py`). `permission_resolution.py` rose from 3 to 4 (one new mention
  in the `_apply_ask_floor` rewrite explaining which fields reset to their defaults). Net -1.
  This is a small, explainable move consistent with what the brief anticipated -- most of the
  R1c work is renaming/restructuring types, not touching `additionalContext` handling itself,
  so the footprint was expected to move little if at all until R1d.

## Acceptance output (verbatim, final run)

```
$ uv run python -m unittest discover -s test -t .
Ran 2337 tests in 25.456s
OK

$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 9.73s. End-to-end: 61 cases in 3.68s.
OK: no differences.

$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook

$ uv run python tools/architecture_fitness.py --predicates
=== R1: PASS ===
  RUNTIME verdict types (1) -- must be exactly 1:
    - RuntimeVerdict (config_types:386)
  UNIT verdict types, excluded (1) -- one decidable unit inside a compound, not a standalone verdict:
    - UnitVerdict (config_types:341) -- nested inside: RuntimeVerdict.sub_matches, Decision.sub_matches
  TOOLING verdict types, excluded (1) -- the replay/analysis layer's own DTO, unified only in R6:
    - Decision (tools.decision:46) -- package 'tools'
  __iter__ shims (0):
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan: ...)
enrichment footprint: 9 coupled (real code), 6 prose-only, 68 total identifier-level occurrences

$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.
(3 pre-existing DIRECTION violations, unrelated to this stage, unchanged from baseline)

$ uv run ruff format . && uv run ruff check --no-cache .
148 files already formatted
All checks passed!
```

## Files changed

Production:
- `toolguard/config_types.py` -- `RuntimeVerdict` + `UnitVerdict` defined; `ResolvedDecision`
  removed
- `toolguard/resolve.py` -- `SubMatch`/`BashResolution`/`FileResolution` removed; import +
  re-export from `config_types`; both resolver functions' construction sites rewritten
- `toolguard/permission_resolution.py` -- `RuntimeVerdict` construction throughout, converted
  to keyword args, `overrides` reconciliation
- `toolguard/hook.py` -- file-path override-logging call site adapted to the list shape; doc
  comment sweep
- `toolguard/tools/decision.py` -- imports `UnitVerdict` instead of `SubMatch`; doc sweep
- `toolguard/config.py` -- re-export line renamed; doc comment sweep
- `toolguard/log_writer.py`, `toolguard/compound.py` -- doc comment sweep only
- `tools/architecture_fitness.py` -- `classify_verdict_altitudes()` added;
  `R1_TOOLING_PACKAGES`; R1 gate and `--predicates` rendering updated
- `technical-notes.md` -- doc-drift sweep (one reference)

Tests:
- `test/unit/test_resolve.py` (79 tests, pure rename + one test class renamed to
  `TestFilePathMatchedRuleExact`)
- `test/unit/test_logging_streams.py` (26 tests, includes REAL shape adaptation:
  `.override` -> `.overrides` list in `TestConflictDetection`, not just import renames)
- `test/unit/test_architecture.py` (`RE_EXPORTED_TYPES` entry renamed)
- `test/unit/test_tools_decision.py` (26 tests, `SubMatch` -> `UnitVerdict`)
- `test/unit/test_architecture_fitness.py` (124 tests: 1 renamed/updated for the collapse,
  4 NEW for `classify_verdict_altitudes`)
- `test/unit/test_hierarchical.py`, `test/unit/test_hook.py`, `test/unit/test_configuration.py`
  -- single comment-only doc-drift fixes each

No files were deleted. No new files were created. High file-touch count (18 files) was
pre-measured and pre-authorized by the R1 scoping trace's blast-radius table before this stage
started ("~110 gross, dominated by one import cascade... high gross count, low real risk").

## Backups / rollback

Every touched file's original bytes are under
`/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1c-backups/`,
with a `SHA256SUMS.orig` manifest captured before any edit. No git write of any kind was issued.

## What surprised me

- The `overrides` reconciliation turned out more structurally interesting than "just rename a
  field" -- it exposed that `BashResolution` and `FileResolution`/`ResolvedDecision` disagreed
  not just on shape but on WHETHER an identifier is even meaningful (compound sub-commands need
  one; a single non-compound target doesn't). Solving it with an `Optional[str]` identifier,
  `None` at the layer that doesn't know one, kept the type honest about what each layer actually
  has in scope, rather than inventing a fake identifier.
- `UnitVerdict` being nested inside BOTH `RuntimeVerdict` and `Decision` turned out to make the
  "unit" structural rule MORE robust, not less -- multiple containers embedding the same class is
  positive evidence it is a shared leaf, which is exactly the intuition "unit altitude" is meant
  to capture.
- The enrichment-footprint move (69 -> 68) was smaller than I expected going in, given how much
  docstring text was rewritten -- most of the churn was moving/merging existing enrichment
  mentions rather than adding or removing them, which is a reasonable signal that this stage
  really was a type-shape collapse and not a behavior change.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- follows [[TOO-45 R1 scoping trace]]
- follows [[TOO-45 R1b instrument fixes report]]
- follows [[TOO-45 R1a shim removal report]]
