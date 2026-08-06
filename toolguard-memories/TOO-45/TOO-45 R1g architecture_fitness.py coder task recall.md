---
title: TOO-45 R1g architecture_fitness.py coder task recall
type: note
permalink: toolguard/too-45/too-45-r1g-architecture-fitness.py-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task (R1g, instrument-only fix, delegated to feature-coder)

Branch too-45. Constraint: do NOT change any production code under `toolguard/`. Only `tools/` and `test/`.

### Problem

`tools/architecture_fitness.py --predicates` reports R1 PASS with "RUNTIME verdict types (1)" but `LevelMatch` (`toolguard/config_types.py` ~line 341) is invisible to the report entirely. It is invisible because its own docstring admits the implementer deliberately named its field `matched_pattern` instead of `matched_rule` so `find_verdict_types`' structural detector (decision-like field + >=2 of {reason, provenance, matched_rule, additional_context}) would not count it -- LevelMatch has (decision, reason, matched_pattern) = only 1 aux hit, under the threshold of 2. That is predicate gaming via field-name choice.

### What's actually true

LevelMatch carries (decision, reason, matched_pattern), returned by `permissions.check_hard_deny`, `permissions.decide_command_at_level_detailed`, `resolve._decide_file_path_at_level_detailed`, `resolve._check_file_path_hard_deny`. It's ONE HIERARCHY LEVEL's raw match, before provenance is resolved one layer up -- genuinely a fourth, lower altitude than unit/runtime/tooling (it can't carry provenance, no Provenance object exists in scope at that point). Type is probably right; REPORTING was wrong.

### Task

Add a fourth declared altitude "LEVEL" to `classify_verdict_altitudes()` so LevelMatch is detected, classified, PRINTED with its reason -- same visibility unit/tooling already get. R1 gate unchanged: still requires exactly 1 RUNTIME type; LEVEL excluded from that count but must be visible.

Two hard requirements:
1. Classification must be STRUCTURAL, stated in code, never a hardcoded class name or hand-maintained list (two such lists already caught drifting on this ticket). Evaluate candidates: (a) carries matched pattern but no provenance/tool/target, (b) returned Optional from per-level decide callback contract, (c) only altitude with no reference to a Provenance type. Must evaluate more than one, say what was rejected.
2. Detector must catch LevelMatch regardless of whether its field is `matched_pattern` or `matched_rule`. Must PROVE this (rename in scratch/synthetic fixture, show classification unchanged). If rename changes the answer, criterion is still name-based -- unacceptable.

Add unit tests with synthetic types: one LEVEL-altitude type that must classify LEVEL, one runtime verdict that must not.

### Acceptance commands (paste real output)

```
uv run python -m unittest discover -s test -t .           # expect OK (2351 + new tests)
uv run python tools/corpus_build.py --verify               # expect: no differences
uv run python tools/architecture_fitness.py --guard        # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates   # LevelMatch VISIBLE under LEVEL heading with its reason
uv run ruff format . && uv run ruff check --no-cache .
```

Report whether R1 still passes and whether that PASS is honest. If analysis says LevelMatch should actually COUNT toward the gate instead of being excluded, say so and argue it plainly -- prefer a true FAIL over a technicality PASS.

### Hard rules

- Never run git checkout/restore/stash/reset or any git write (denied by permission rule, hangs indefinitely).
- Back up original bytes to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1g-backups/` BEFORE editing, verify with sha256sum. Done: `architecture_fitness.py.orig`, `test_architecture_fitness.py.orig`, `SHA256SUMS.before`.
- Don't disturb the substantial uncommitted work across 9 prior stages. Don't commit. Don't copy the repo.
- `uv run python`, never bare python. `unittest`, not pytest. Always `ruff check --no-cache`.
- Don't edit anything outside the repo.

### Report destination

Write final report to basic-memory `toolguard` project at `TOO-45/TOO-45 R1g level altitude report.md`, tagged task-memory + TOO-45. No hard-wrapped paragraphs.

## Design decided during investigation (before coding)

Probed every decision-bearing class tree-wide (read-only scratch script, `/tmp/.../scratchpad/probe_classes.py`):

- `LevelMatch`: aux={reason} (1 hit), provenance_field=False, tool_or_target=False
- `UnitVerdict`/`RuntimeVerdict`/`Decision`: aux>=2 (includes `provenance` itself as a hit), provenance_field=True
- `LedgerDecision`/`SingleDecision`: aux=0, provenance_field=False (already excluded by decision+aux>=1 requirement, unaffected)

Chosen structural signal: **presence/absence of a field whose TYPE ANNOTATION references `Provenance`** (checked via `_class_field_type_sources`, already used for List[...] nesting detection -- not a new detection technique). Every genuine unit/runtime/tooling verdict type on this tree declares a field typed `Optional["Provenance"]`; LevelMatch structurally cannot (no Provenance object is in scope at that call site -- this is architecturally load-bearing, not incidental). This is invariant to the `matched_pattern`/`matched_rule` rename because it inspects the TYPE of every field, not any one field's name.

Rejected candidates (documented in code + report):
- "no tool/target field": insufficient alone -- `UnitVerdict` (already correctly UNIT-altitude) also has no tool/target fields, so this alone would misclassify UnitVerdict as LEVEL too.
- "returned Optional from the per-level decide callback contract": requires enumerating specific function names (`check_hard_deny`, `decide_command_at_level_detailed`, etc.) -- exactly the hand-maintained-list anti-pattern this ticket has caught drifting twice already; also requires call-graph/return-type tracing this AST-only tool doesn't do reliably.

Implementation approach: factor `find_verdict_types`' inner scan into a shared `_scan_decision_classes(toolguard_dir, min_aux_fields)` helper parameterized by aux-field threshold. `find_verdict_types` keeps threshold=2 (`_VERDICT_MIN_AUX_FIELDS`, UNCHANGED, its own tests untouched). `classify_verdict_altitudes` additionally scans at a new lower threshold `_LEVEL_MIN_AUX_FIELDS = 1` to build its full candidate pool (a superset), then classifies: **provenance-field absence checked FIRST, before nesting/tooling-package checks** -- any candidate lacking a Provenance-typed field is LEVEL regardless of aux-field spelling; only candidates that DO have a Provenance-typed field go through the existing nested-in / tooling-package / runtime logic unchanged.

Known accepted limitation, out of scope to fix (production code off-limits): `LevelMatch`'s own docstring in `toolguard/config_types.py` will become stale after this fix lands -- it currently claims the `matched_pattern` naming "keeps it out of that count" and that renaming to `matched_rule` "would fail R1's gate." Both claims become false once this detector ships. Cannot edit `toolguard/` per hard constraint; flagged for a follow-up doc fix.
