---
title: TOO-45 R1g level altitude report
type: note
permalink: toolguard/too-45/too-45-r1g-level-altitude-report
tags:
- task-memory
- TOO-45
---

## Summary

Fixed the predicate-gaming defect: `LevelMatch` (`toolguard/config_types.py`) was completely invisible to `tools/architecture_fitness.py --predicates`' R1 report -- not merely excluded-with-a-reason, simply never discovered, because its own docstring records that its winning-pattern field was deliberately spelled `matched_pattern` (not `matched_rule`) specifically so `find_verdict_types`' 2-aux-field structural threshold would never count it. Added a fourth declared altitude, LEVEL, to `classify_verdict_altitudes()` so `LevelMatch` is now detected, classified, and printed with its reason -- exactly the visibility UNIT and TOOLING already had. R1's gate is unchanged: still requires exactly one RUNTIME verdict type; LEVEL is excluded from that count but is now always visible.

No production code under `toolguard/` was touched, per the hard constraint. Only `tools/architecture_fitness.py` and `test/unit/test_architecture_fitness.py` changed.

## Files changed

- `/home/arnon/projects/toolguard/tools/architecture_fitness.py` -- 296 lines changed (diffed against my own pre-edit backup, not git HEAD, since the tree already carried 9 prior uncommitted stages)
- `/home/arnon/projects/toolguard/test/unit/test_architecture_fitness.py` -- 145 lines changed (4 new tests + one ruff reformat pass)

Backups of both files' pre-edit bytes, plus SHA256SUMS, are at `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1g-backups/` (populated and verified before any edit, per the hard rule).

## Design

### The structural signal chosen: provenance-capability, checked by field NAME "provenance" OR by field TYPE referencing "Provenance"

New helper `_is_provenance_capable(fields, field_types)`:

```python
return "provenance" in fields or any(
    "Provenance" in type_src for type_src in field_types.values()
)
```

Every genuine unit/runtime/tooling verdict type on the real tree (`UnitVerdict`, `RuntimeVerdict`, `tools.decision.Decision`) declares a field literally named `provenance`, typed `Optional["Provenance"]`. `LevelMatch` structurally cannot have either -- it is built one layer below where any `Provenance` object exists in scope at all (its own docstring: "before any provenance lookup ... is attached one layer up"). This is not an incidental difference the detector happens to exploit; it is the architectural reason the type is a genuinely different, lower altitude.

This is invariant to the `matched_pattern`/`matched_rule` rename (TOO-45 R1g's hard requirement #2) because the check never inspects the winning-pattern field at all -- only whether a *provenance* field/reference exists. **Proved, not just asserted**: added `test_level_classification_is_invariant_to_matched_pattern_vs_matched_rule_rename`, which builds two synthetic trees differing ONLY in that field's spelling and asserts both classify LEVEL, neither RUNTIME. Renaming to `matched_rule` pushes the synthetic class over `find_verdict_types`' own 2-aux-field bar (2 aux hits instead of 1), so if LEVEL classification were still keyed off that field this test would fail loudly.

### Why the check is name-OR-type, not type-only

Type-annotation-only was the first design (checking only whether any field's type text contains "Provenance"), and it is the more "pure" structural signal in isolation. It broke 3 pre-existing tests in `TestClassifyVerdictAltitudes` (`test_nested_list_field_class_is_unit_not_runtime`, `test_class_under_tooling_package_is_tooling_not_runtime`, `test_unrelated_verdict_ish_class_is_runtime`), whose synthetic fixtures spell their provenance-bearing field `provenance: object` -- a placeholder type, since those fixtures predate this function and were only ever exercising `_class_field_names`' NAME-based aux-field counting. Per the hard rule against modifying existing tests, I did not touch those fixtures; instead I widened the detector to accept the field-NAME signal too (which is also how `_VERDICT_AUX_FIELD_NAMES` already treats `"provenance"` elsewhere in this module -- not a new technique, just applied here). Since "provenance" as a field name is architecturally unrelated to the `matched_pattern`/`matched_rule` field this ticket is about, this doesn't reopen the gaming vector the ticket exists to close.

### Candidates evaluated and rejected

Per the hard requirement to evaluate more than one signal:

1. **"No `tool`/`target` field"** -- REJECTED. Insufficient alone: `UnitVerdict` (already correctly UNIT-altitude) also declares no `tool`/`target` fields, so this signal doesn't distinguish LEVEL from UNIT and would misclassify `UnitVerdict` too if used by itself. Verified against the real tree with a probe script before writing any code.
2. **"Returned `Optional` from the per-level `decide_detailed` callback contract"** -- REJECTED. Would require enumerating the specific function names that construct a `LevelMatch` (`check_hard_deny`, `decide_command_at_level_detailed`, `_decide_file_path_at_level_detailed`, `_check_file_path_hard_deny`) -- exactly the hand-maintained-list anti-pattern this ticket has already caught drifting twice. This AST-only tool also has no reliable cross-function return-type/call-graph tracing to derive it structurally instead.
3. **"No reference to a Provenance type"** (CHOSEN, widened to name-or-type as above) -- structural, derived from re-parsing field declarations the same way `_class_field_type_sources` already does for UNIT's `List[...]`-nesting detection; not a new detection technique, not a hardcoded class-name list.

### Implementation mechanics

- Factored `find_verdict_types`' inner AST-walk loop into a new shared `_scan_decision_classes(toolguard_dir, min_aux_fields)`, parameterized by aux-field-count threshold. `find_verdict_types` now delegates to it at the UNCHANGED `_VERDICT_MIN_AUX_FIELDS = 2` -- its own calibration and its own tests are untouched.
- `classify_verdict_altitudes` now builds its candidate pool from `_scan_decision_classes` at a new, lower `_LEVEL_MIN_AUX_FIELDS = 1` -- a superset of `find_verdict_types`' own pool, so `LevelMatch` (1 aux field under today's spelling) gets a chance to be classified even though it never reaches `find_verdict_types`' own threshold. Verified this doesn't reintroduce `LedgerDecision`/`SingleDecision` (the two false positives the threshold=2 calibration exists to keep out): both declare **zero** aux fields, not one, confirmed by a tree-wide probe before implementation.
- Classification order in `classify_verdict_altitudes`: provenance-capability is checked FIRST, before the nesting/tooling-package checks -- documented as deliberate, since "can this class attach a provenance at all" is the more fundamental fact and takes priority over which container/package a provenance-capable class happens to live in.
- `--predicates`' text renderer and the JSON output both now include a `level` key/section, printed the same way `unit`/`tooling` already are, each entry carrying its `reason`.

## Known limitation, out of scope by hard constraint

`LevelMatch`'s own docstring in `toolguard/config_types.py` (production code, off-limits per this task) currently states: "this class declares `matched_pattern`, not `matched_rule`, the one deliberate naming choice that keeps it out of that count... Renaming this field to `matched_rule` would silently reintroduce a second RUNTIME-altitude verdict type and fail R1's gate." Both claims are now FALSE -- this fix makes classification invariant to that rename, proved by the new test. I could not edit this docstring; flagging it as a follow-up doc fix for whoever next touches `toolguard/config_types.py`.

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2355 tests in 23.790s
OK
```

(2351 baseline + 4 new tests = 2355; matches the ticket's "expect OK (2351 + your new tests)".)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.40s. End-to-end: 61 cases in 3.19s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --predicates
=== R1: PASS ===
  RUNTIME verdict types (1) -- must be exactly 1:
    - RuntimeVerdict (config_types:551)
  UNIT verdict types, excluded (1) -- one decidable unit inside a compound, not a standalone verdict:
    - UnitVerdict (config_types:436) -- nested inside: RuntimeVerdict.sub_matches, Decision.sub_matches
  TOOLING verdict types, excluded (1) -- the replay/analysis layer's own DTO, unified only in R6:
    - Decision (tools.decision:46) -- package 'tools'
  LEVEL verdict types, excluded (1) -- a raw match at one hierarchy level, not a standalone verdict:
    - LevelMatch (config_types:341) -- no field named or typed as a Provenance reference -- this is the raw match at one hierarchy level or hard-deny pool, before any provenance lookup is attached one layer up (see the class's own docstring). The winning-pattern field is never inspected by this check, so classification is unchanged whether it is spelled matched_pattern or matched_rule.
  __iter__ shims (0):
  bare verdict-tuple returns (0) -- functions returning a (decision, reason, ...) tuple, never a class, grouped by module:
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan: parser, parser.bash_parser, parser.command_extractor, parser.command_model, parser.multiline)
```

```
$ uv run ruff format . && uv run ruff check --no-cache .
148 files left unchanged
All checks passed!
```

## Does R1 still pass, and is that PASS now honest?

R1 still PASSes (`RUNTIME verdict types (1)`, unchanged gate condition). I believe this PASS is now honest, not a technicality, and here is the argument -- if this reasoning is wrong I'd rather know now than have it stand unchallenged:

`LevelMatch` is architecturally, not incidentally, a different altitude from `RuntimeVerdict`. It represents one hierarchy level's raw match, constructed inside `check_hard_deny` / `decide_command_at_level_detailed` / `_decide_file_path_at_level_detailed` / `_check_file_path_hard_deny` -- none of which have a `Provenance` object in scope yet; provenance is resolved exactly one layer up, in `permission_resolution._resolve_unclamped`, which is what turns a `LevelMatch` into (part of) a `RuntimeVerdict`. Forcing `LevelMatch` to carry a `provenance` field would mean either fabricating a value it cannot know, or making it `Optional` and populating it `None` at every real construction site -- which is exactly the shape UNIT and TOOLING were already correctly excluded for representing a genuinely different concern, not a shirked one.

The difference between this PASS and the one before the fix is not the underlying architecture -- I agree with the ticket's own framing that "the type is probably right; the REPORTING was wrong." What changed is that the exclusion is now (a) structurally derived and proven rename-invariant rather than resting on a field-name choice, and (b) fully visible in both the text and JSON output with an explicit reason, the same standing rule every other R1 exclusion (`out_of_scope_excluded`, UNIT's `nested_in`, TOOLING's `package`) already followed. An operator reading `--predicates` output today sees all four altitudes and can independently judge whether the exclusion reasoning holds; before this fix, they could not see `LevelMatch` at all, so they could not even ask the question. That is the honest-PASS bar this ticket set, and I believe it is met.

## Self-review notes

- Full unit test suite, `corpus_build --verify`, `--guard`, `--predicates`, and `ruff format`/`ruff check --no-cache` all run clean as pasted above.
- Anti-pattern scan: no `async`/`await`, no `threading`, no new local (in-function) imports introduced.
- Confirmed via `git status`/`stat` that `tools/corpus_build.py`'s pre-existing modified state (mtime 10:18, well before this session started at ~16:28) is unrelated prior-stage work I never touched -- did not disturb it.
- Scope: 2 existing files modified, 0 new files (besides these basic-memory notes). Well inside the scope-inflation guard.
- JSON output validated by parsing (`--predicates --json`) and confirming the `level` key round-trips correctly.
- `--layers` and `--metrics` smoke-tested to confirm no collateral effect from this change (their pre-existing violations/output are unrelated prior-stage state).
