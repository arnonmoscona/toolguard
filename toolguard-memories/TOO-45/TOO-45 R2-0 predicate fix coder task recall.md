---
title: TOO-45 R2-0 predicate fix coder task recall
type: note
permalink: toolguard/too-45/too-45-r2-0-predicate-fix-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Instrument-only fix in /home/arnon/projects/toolguard, branch too-45, TOO-45 step R2-0. DO NOT CHANGE toolguard/ production code -- only tools/ and test/.

Full prompt requirements (verbatim intent):

A. Detect the R2 hazard (parallel arrays related by index) structurally, not by hardcoded class name (`ToolPatternLayer`) or `_entries` field-name suffix. Must fire on all 9 scout-built synthetic gaming variants that carry the hazard and none that don't: X/X_entries annotations, X/X_rules, dict-of-lists keyed by kind, properties, renamed class, sibling class, unpaired names, __init__ assignment, and the real fix (entries-only + derived property, must NOT fire).

B. Must catch the method-pair instance: `Configuration.hard_deny`/`hard_deny_entries`, consumed by index at resolve.py:294. Old detector is structurally blind to it (it's methods, not annotated fields on ToolPatternLayer).

C. Be explicit about what the predicate cannot mechanically check: "stripped patterns are a derived property of RuleEntry" and "no prose-defended index-alignment invariant remains" are not mechanically checkable as literally stated. Either find a real proxy (trace suggests: presence of a drift guard comparing two lengths is a machine-visible fingerprint of a prose-defended invariant) or print explicitly as unchecked/judged-by-review, following the R1/R5 out_of_scope_excluded idiom already in the file.

D. Add a regression test proving renaming the field suffix or the class does not change R2's verdict (like R5a-0's pin on the .pyscn.toml relabelling exploit).

Report the honest new baseline: R2 will presumably still FAIL with MORE instances than today's 3. List any newly discovered instances.

## Required reading before work

basic-memory `TOO-45/TOO-45 R2 scoping trace.md` in project `toolguard` -- READ, not re-derived. Executed evidence:
- `find_parallel_arrays` (tools/architecture_fitness.py:1577) AST-parses for hardcoded class name `ToolPatternLayer`, reports `X`/`X_entries` AnnAssign field pairs. Fires on exactly 1 of 9 synthetic hazard variants.
- Real hazard use-sites in production code (measured): `toolguard/config.py:1505` `entries[candidates.index(pattern)]` inside `Configuration.entry_for_pattern`, guarded by `if len(entries) != len(candidates): return None` (config.py ~1503). `toolguard/resolve.py:294` `deny_entries[deny_patterns.index(matched_pattern)]` inside `_hard_deny_additional_context`, guarded by a length+membership check at resolve.py ~292.
- 4 prose invariant statements: config_types.py:161-165 (ToolPatternLayer docstring), config.py:1221-1224 (hard_deny_entries docstring), config.py:1461-1470 (entry_for_pattern docstring), resolve.py:268-272.
- Drift guard at resolve.py:292 is pinned by ZERO tests (measured: deleting it broke nothing). Drift guard at config.py:1503 is pinned by exactly 2 synthetic tests in `TestEntryForPatternDrift` and nothing else.
- Recommended replacement (not to be implemented in this stage -- R2-0 is INSTRUMENT ONLY): RuleEntry.stripped_pattern property; ToolPatternLayer keeps only *_entries storage with allow/deny/ask as derived properties.

## My own additional finding during investigation (not in the scoping trace)

A THIRD real index-parallel-access instance: `toolguard/config.py:1341` inside `Configuration.permission_layers`, takeover-mode allow filtering: `zip(allow, allow_entries)` then rebuilds both tuples from the same `kept` list -- the docstring says "keeping them index-aligned" (config.py:1310). This is a genuine additional gaming-proof instance the scoping trace's grep for `.index(` did not surface (it only searched for `.index(`, not `zip(`). Confirmed by direct read of config.py:1298-1364.

Grep confirms these are the ONLY `.index(` / `zip(` call sites in toolguard/ that are candidates (excluding parser/bash_parser.py, generated): permission_migration.py and tools/config_access.py/pattern_overlap.py hits are all same-object slice bounds (`pattern[: pattern.index("(")]`), not two-different-object subscript-by-index -- correctly excluded by an A != B check.

## Design decided

Primary NEW structural detector: `find_index_parallel_access` -- AST use-site detector, class/field-name agnostic, looks for:
1. `A[B.index(x)]` shape: Subscript whose slice is directly a Call to `.index()`, where the subscripted expr A and the `.index()` receiver B are syntactically different (not literally the same expression) -- this alone is invariant to container shape/property/dict/naming since it inspects USE not DECLARATION.
2. `zip(A, B)` with 2+ syntactically-different sequence args.

This satisfies clause A (fires on all real gaming variants because usage code is adapted per-variant in the fixtures) and clause B for free (method-pair instance is caught because detection is about usage, not about where the two arrays are declared).

Secondary/proxy detector: `find_drift_guards` -- proxy for clause C's prose-invariant clause, per the trace's own suggestion: `if len(A) != len(B)` (or similar mismatched-length guard) is a machine-visible fingerprint of a prose-defended index invariant. Gates R2 pass alongside the index-access detector.

Clause C's "stripped patterns are a derived property of RuleEntry" clause: NOT mechanically checkable -- will be printed explicitly as an unchecked clause in the R2 report output, following the `out_of_scope_excluded`/`sanctioned_exclusions` idiom already used by R1/R3.

Old `find_parallel_arrays` (name-based) kept as-is, still reported for continuity/comparison, but NO LONGER the sole gate for R2["pass"].

Fixtures: build 9 synthetic modules reproducing the scout's variants (as real files under a tempdir in the test, following existing `TestFindParallelArrays` conventions with `_write` helper), each carrying BOTH the declaration shape AND a companion function performing an index-parallel lookup/zip adapted to that variant's shape -- except: variant 6 (unpaired names, prose-only) needs the invariant still expressed as actual index-correlated usage code (with non-suffix-matching names) to be a real hazard, distinct from a true "no invariant at all" negative control which should also be added.

Rename-invariance regression test: build near-identical fixtures differing only in field-name suffix / class name, assert detector output unaffected (satisfies clause D).

## Hard rules

- Never touch toolguard/. Only tools/, test/.
- Back up originals to /tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r2-0-backups/ BEFORE any edit, verify restore via sha256sum if ever needed.
- No git write ops.
- uv run python, unittest not pytest, ruff check --no-cache.

## Acceptance commands

```
uv run python -m unittest discover -s test -t .           # expect OK (2368 + new tests)
uv run python tools/corpus_build.py --verify               # expect: no differences
uv run python tools/architecture_fitness.py --guard        # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates   # corrected R2 reading
uv run ruff format . && uv run ruff check --no-cache .
```

## Report destination

basic-memory project `toolguard`, `TOO-45/TOO-45 R2-0 predicate fix report.md`, tagged task-memory + TOO-45. Lead with corrected R2 baseline and newly-discovered instances. Do not hard-wrap paragraphs.
