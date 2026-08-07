---
title: TOO-45 compound-resolve cycle - coder task recall
type: note
permalink: toolguard/implementation/too-45-compound-resolve-cycle-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

## Task

Implement approved refactor of `toolguard/compound.py` <-> `toolguard/resolve.py` runtime cycle, in `/home/arnon/projects/toolguard`, branch `too-45`.

Source docs (read in full before starting):
- `toolguard-memories/TOO-45/reports/compound-cycle-plan-B.md` (the plan)
- `toolguard-memories/TOO-45/reports/compound-cycle-judgment.md` (blind judge that selected Plan B with refinements R1-R5)

## What's being fixed

`compound.py` calls back into `resolve.py` via injected callables (`resolve_one` 3-tuple, `resolve_outer` 5-tuple probe, `record_unit` callback that mutates caller's list). Plan B replaces this with: `decompose(command) -> List[CommandUnit]` (pure structure), caller resolves `unit.parts` itself, `judge_unit(unit, part_verdicts, fallback) -> UnitVerdict` (owns ASK floor, pure), `_combine_strictest(List[UnitVerdict]) -> RuntimeVerdict`. `resolve.py` drives the loop directly and populates `sub_matches`/`overrides` by ordinary append/extend.

## Mandatory refinements from the judgment (R1-R5)

- **R1 (most important)**: put `audits_as_one: bool` field on `CommandUnit` (set by `decompose`), NOT `if unit.kind == "plain"` in resolve.py. True for 'inline_code'/'undecidable' (floor decided -> ONE audit entry), False for 'plain'/'unknown' (audit entries are the unit's own parts). Driver: `sub_matches.append(judged) if unit.audits_as_one else sub_matches.extend(part_verdicts)`. This also fixes Plan B's one behaviour change (B5, the `unknown` kind).
- R2: step 1 (`_combine_strictest` -> `List[UnitVerdict]`) first and mandatory; two collapses: UndecidableSegment branch's duplicate construction (compound.py:1134+:1150) -> one object; LeafCommand branch's unpack-and-repack (:1168-1176) -> `all_results.append(outcome)`.
- R3: relocate the 5 ask-floor branches in `_resolve_leaf_detailed` VERBATIM. Do not tidy/table-drive them (security-sensitive). Add 12-cell test matrix over {stub decision} x {ask,deny,allow_with_warning,allow} against `_apply_undecidable_floor`'s documented table BEFORE moving anything, plus a test that an ask-floor stub allow-via-more-specific-allow-over-less-specific-deny produces ZERO entries in `RuntimeVerdict.overrides`.
- R4: re-budget to 5-7h; step 6 (docstring sweep) is non-negotiable. 44 references under toolguard/ (compound.py 38, resolve.py 5, hook.py 495 x1), plus config_types.py `_resolve_leaf_detailed` refs at ~570/589/641/788, permission_resolution.py:124 `_resolve_leaf`. Two dense doc blocks (ResolveOuterProbe, RecordUnitVerdict, compound.py:32-56) are DELETIONS not rewrites.
- R5 (minor): `judge_unit` raises on unrecognized `kind` (not just length-mismatch, which Plan B already has). Add `_unit_from_tuple`'s own unit test. Drop `--strict-prose` claim to plain instruction (any prose diff = defect until proven otherwise; never regenerate goldens to fix).

## ABANDON GATE (pre-authorised, at Plan B step 3)

If extracting `judge_unit` needs anything beyond mechanical relocation (a new conditional keyed on kind past the 4 that exist, or a branch wanting a second look at a resolver) -> STOP, revert to end of step 2, ship fallback instead: keep injection, rename param to `resolution_strategy: Callable[[str], UnitVerdict]`, document strategy pattern explicitly. This IS legitimate, not failure.

## Step order (Plan B, 7 steps + R2 reordering), verify suite green at each step

0. Characterization test for `sub_matches` order/content (test-only) - shapes: single plain command; multi-part plain leaf (`git status && ls`); multi-leaf multi-line; ask-floor leaf x 4 fallback values; `diff <(cat a) <(cat b) && ls -la` (2 entries); hard-denied sub-command. PLUS R3's 12-cell matrix + zero-overrides test. Keep afterward.
1. `_combine_strictest` -> `List[UnitVerdict]` (mandatory first per R2).
2. Add `CommandUnit` (with `audits_as_one` field per R1) + `decompose`. Rewrite `resolve_compound_permission_detailed` to iterate `decompose`, dispatch by kind, still using resolve_one/resolve_outer/record_unit (callbacks intact) - riskiest step, isolated.
3. Extract `judge_unit` (ABANDON GATE HERE). No callbacks - driver resolves unit.parts first, passes results in.
4. `resolve.py` drives directly. `_decide` returns `(UnitVerdict, Optional[ConflictOverride])` strict pair. Delete `_resolve_one`/`_resolve_outer`/`_record_unit`. Cycle gone at end of this step - verify.
5. Delete `resolve_outer`/`record_unit` params from compound's public functions; legacy driver becomes 10-line adapter loop.
6. Docstring sweep (non-negotiable, R4). ~44 refs across toolguard/, plus config_types.py, permission_resolution.py:124, hook.py:495.
7. Full verify gate (see below).

## Full gate before declaring done

```
uv run python -m unittest discover -s test -t .              # currently 2,587, all passing
uv run python tools/corpus_build.py --verify                  # currently OK, no differences
uv run python tools/architecture_fitness.py --layers          # completeness 100%, 0 violations
uv run python tools/architecture_fitness.py --predicates      # R1 R2 R3 R5 R6 all PASS
uv run ruff check .                                           # clean
```

Never regenerate goldens to make a failure go away. If corpus --verify fails: either fix behaviour change, or if intended, STOP and report before regenerating.

Known residual gap: corpus guards `decide()`'s construction of sub_matches, NOT hook.py's `_log_allowed_command` write loop. Should not need to touch hook.py's CODE (only its docstring at ~495 mentioning resolve_outer/record_unit, per R4 sweep). If work needs touching hook.py logic, that's a signal to report.

## Key facts verified from source before starting

- `_decide_file_path_at_level_detailed` in resolve.py has an odd `except ValueError, TypeError:` at line 186 - this is a known repo quirk (ruff strips except-tuple parens on this 3.14 project per project memory), NOT something to fix.
- Zero test files reference `resolve_outer`/`record_unit` (confirmed via grep) - only compound.py/resolve.py/hook.py (hook.py only in docstring at ~495).
- `check_compound_permission` has zero production callers (only tests + its own definition) - confirmed by judgment section 5.
- Strict pairs (2-tuples) are NOT flagged by `find_bare_verdict_tuples` - pinned by test_architecture_fitness.py:1066/1284.
- LeafCommand has `.text`/`.ask_floor`; UndecidableSegment has `.original`/`.reason` (command_extractor.py, re-exported via multiline.py).

## Report requirements (final message must contain)

1. Every file changed + what changed.
2. Whether cycle is ACTUALLY gone - verify (no injected production callback in compound.py into resolve), say how checked.
3. Whether abandon gate was taken, and trigger if so.
4. Concept count before/after (judge counted 10 -> 7).
5. Where ASK floor ended up + why.
6. Anything in plan/judgment that was WRONG about real code (both agent-written, not run).
7. Full gate results.
8. Subjective difficulty.

Also write implementation report to `toolguard-memories/TOO-45/reports/compound-cycle-implementation.md` with specified frontmatter (title, type: note, permalink: toolguard/too-45/reports/compound-cycle-implementation, tags: task-memory/TOO-45/report).

Markdown style: never hard-wrap paragraphs - one paragraph one line, blank line between blocks.
