---
title: TOO-45 punch-list 03 stages 2+4 - coder implementation report
type: note
permalink: toolguard/implementation/too-45-punch-list-03-stages-2-4-coder-implementation-report
tags:
- task-memory
- TOO-45
- coder
- implementation-report
---

## Summary

Implemented TOO-45 punch-list #03, stages 2 and 4 (stage 1 already in the working tree; stage 3
cancelled). Removed the `permission_resolution <-> resolve` runtime cycle by making
`permission_resolution` import its per-level matchers directly from `permissions`/`file_matching`
instead of receiving one back as an injected callable from `resolve.py`, and exposed the cascade
as a pure fold over already-computed `LevelMatch | None` values per the judge's extra requirement.
Full suite green (2733 tests), golden corpus byte-identical (9/9 corpus tests including
`test_no_verdict_changed`), pyright clean on `toolguard/` and touched tests, ruff clean, all
architecture-fitness predicates (R1-R6) PASS including R5 (import cycles) and R2 (parallel arrays).

## Protocols: deleted / survived / new

- **DELETED**: `DecideDetailed` (config_types.py) -- no injected callable exists any more, so
  there is no callback shape left to type. Its docstring and the "runtime cycle static analysis
  cannot see" header block above it were deleted outright, not rewritten (per the judge's
  instruction to take B's call on this) -- keeping a rewritten version of a defect description
  after the defect is gone is how a codebase accumulates archaeology.
- **SURVIVED unchanged**: `ResolutionConfig` (still exactly 4 members -- `permission_levels_with_provenance`,
  `has_any_rules`, `resolved_no_match_fallback`, `parse_failures`).
- **SURVIVED unchanged in shape**: `ResolveConfig` (still `resolve_config_path`, `hard_deny`,
  `hard_deny_entries`, `resolved_undecidable_fallback` on top of `ResolutionConfig` -- `resolve.py`'s
  own entry points still need this wider surface, and `file_matching.check_file_path_hard_deny`
  now also types its `config` param against it, since it needs both anchoring and `hard_deny`).
- **NEW**: `PathAnchoring(Protocol)` -- one member, `resolve_config_path`. Types
  `file_matching.anchor_file_pattern`/`decide_file_path_at_level_detailed`'s `config` param --
  the narrowest statement of what those functions actually touch.
- **NEW**: `FilePathResolutionConfig(ResolutionConfig, PathAnchoring, Protocol)` -- types
  `resolve_file_path_permission`'s `config` param (the cascade surface plus anchoring, since the
  file-path cascade forwards `config` one layer down for project-root anchoring; the Bash cascade
  never needs it, hence `resolve_command_permission` stays on the narrower `ResolutionConfig`).

## Before/after call topology

**Before** (the cycle): `resolve.py` imports `permission_resolution` (real import edge);
`permission_resolution.resolve_permission_detailed` receives a `decide_detailed` callable built
as a closure INSIDE `resolve.py` and calls back into it -- `resolve -> permission_resolution ->
resolve` at runtime, invisible to any import-graph tool.

**After**: `permission_resolution` imports `permissions.decide_command_at_level_detailed` and
`file_matching.decide_file_path_at_level_detailed` directly (both engine-layer siblings, neither
imports back). `resolve_command_permission`/`resolve_file_path_permission` build the eager
per-level match list, then call the pure fold `resolve_permission_cascade`. `resolve.py`'s two
call sites became one-line calls passing plain data (command string / file path), no closures.
Every arrow points down; `resolve -> permission_resolution -> {permissions, file_matching}`, and
`resolve -> file_matching` directly for the hard-deny-first check. Verified with a one-off
`sys.setprofile` probe (see below): 28 module-pair edges recorded across two real decisions
(one Bash compound, one file-path), zero cycles, and critically **no `permission_resolution ->
resolve` edge exists** (the edges into `config` from `permission_resolution`/`file_matching` are
runtime-only, from calling `Configuration`'s methods through the Protocol surface -- not an
import edge, and not part of any cycle).

## The pure fold (the requirement neither designer proposed)

`resolve_permission_cascade(levels, tool_name, parse_failures, has_any_rules, no_match_fallback,
subject="Command") -> RuntimeVerdict` in `permission_resolution.py`. `levels` is
`Sequence[Tuple[Optional[LevelMatch], Tuple[ToolPatternLayer, ...]]]` -- a STRICT PAIR per level
(match + its contributing layers), not two parallel sequences, specifically to avoid the
`find_parallel_arrays` (R2) trap design B itself flagged as the cost of "matches as data". No new
record type was needed; a `Tuple` pair is fine per this project's own convention ("strict pairs
are fine"). It wraps the raw fold (`_resolve_unclamped`, rewritten to take `levels` instead of
`config` + a callable) and the unchanged `_apply_ask_floor`. `_detect_override` was rewritten the
same way -- it now just reads `result.decision` on the precomputed tail of `levels`; the old
`if not deny: continue` skip is gone since it was a pure optimisation against a callable that no
longer exists, and dropping it changes nothing observable (a level with no deny patterns could
never have yielded `decision == 'deny'` anyway).

Production entry points (`resolve_command_permission`, `resolve_file_path_permission`) build the
eager per-level list by calling the real matcher for every level, then call the fold -- this is
where the measured +0.58% eager-matching cost comes from, exactly as both designers measured and
the brief said not to re-measure. I did not re-measure it; the shape is materially the same as
both designs (eager per-level list, then fold), so there is no reason to expect a different number.

## Test call-site migration

- **13 "adapter" call sites** (bind a command string to the real per-level matcher, across
  `test_hierarchical.py` x3, `test_hard_deny.py` x1, `test_takeover_mode.py` x1,
  `test_logging_streams.py` x6, `test_permission_resolution.py` x2) now call
  `resolve_command_permission(config, "Bash", command)` directly; the adapter closures
  (`_detailed_decider`, inline `_decide` bound to a command) were deleted. This count differs
  from design B's estimate ("5 adapters / 15 call sites") -- the actual count in
  `test_permission_resolution.py` was 2 call sites, not 4, confirmed by exhaustive grep both
  before and after; every design report's counts were estimates, not authoritative.
- **26 call sites / 6 hand-written `LevelMatch` stubs**, all in `test_configuration.py`, converted
  to the pure fold via a new local helper `_resolve_via_cascade(config, tool_name, decide,
  subject="Command")` that builds `[(decide(allow, deny, ask), layers) for ...]` and calls
  `resolve_permission_cascade`. The stub functions themselves (`_decide`, `_decide_allow_git`,
  `_decide_deny_rm`) are UNCHANGED -- they still fake-match on literal patterns, still never touch
  the real matcher, still isolate the cascade from matching exactly as before. Only the last line
  of each test changed from passing the stub AS A CALLBACK to using it to build data.
- 4 `_anchor_file_pattern` imports in `test_hierarchical.py` and 1
  `_decide_file_path_at_level_detailed` import in `test_hook.py` updated to the new public names.
- **No assertion was weakened or deleted anywhere** -- verified by diffing every touched test file
  for removed `assert*` lines (zero found) and confirming the pre/post test count is identical
  (2733 both times). One test method was renamed (`test_resolve_permission_detailed_reason_cites_rules_dir_file_path`
  -> `test_resolve_command_permission_reason_cites_rules_dir_file_path`) to match the function it
  exercises; its body is untouched.

## Doc-drift sweep (explicitly required, not deferred)

Fixed stale cross-references to `resolve_permission_detailed`/`DecideDetailed`/the old private
file-matching names in: `config.py` (3), `session_start.py` (1), `hook.py` (2), `compound.py` (3),
`permissions.py` (1), `tools/architecture_fitness.py` (1, a historical-example comment, name only),
`test_resolve.py` (2 prose-only), `test_hook_eval.py` (1 prose-only, found during the final sweep,
not originally listed), `test_hook.py` (1 comment, found during the final sweep). Also updated
`test_architecture.py`'s `LAYERS` allowlist to add `toolguard.permissions`/`toolguard.file_matching`
to `permission_resolution`'s allowed imports -- this is the intended, reviewed new edge the whole
refactor exists to create, not a weakened check.

**Deliberately left alone** (deferred to punch-list #07 per the task): `test_recommended_protections.py`,
`test_architecture_fitness.py`'s content, `technical-notes.md`. Confirmed zero diff on all three.

## Verification

- Full suite: `Ran 2733 tests ... OK` (matches baseline exactly, both before and after every
  round of changes).
- Golden corpus: `test.unit.test_verdict_corpus`, 9/9 tests pass, including
  `test_no_verdict_changed` (in-process, ~5,000 cases) and the two end-to-end hook-subprocess
  tests -- byte-identical verdicts confirmed.
- `pyright toolguard/` and `pyright` on every touched test file: 0 errors, 0 warnings.
- `ruff format --check .` / `ruff check .`: clean, whole repo.
- `tools/architecture_fitness.py --layers`: completeness and direction both clean; `file_matching`
  was already registered in the `engine` layer's `.pyscn.toml` packages list by stage 1.
- `tools/architecture_fitness.py --predicates`: R1 PASS, R2 PASS (no parallel arrays -- the
  `LevelOutcome` strict-pair design avoided this), R3 PASS, R5 PASS (no import cycles), R6 PASS.
- **Cycle-proof** (one-off, `sys.setprofile`, scratch script under `coder-test/`, deleted after
  running): traced 28 module-pair edges across two real decisions (a Bash compound command and a
  file-path read) driven through `toolguard.api.decide()`. DFS cycle detection over the resulting
  graph: **no cycle found**. Edge list confirmed the expected shape --
  `resolve -> permission_resolution`, `permission_resolution -> permissions`,
  `permission_resolution -> file_matching`, `resolve -> file_matching` -- and, critically, **no
  `permission_resolution -> resolve` edge**, which is the whole point.

## Corrections from the brief, both respected

1. Did NOT "fix" the Bash `extended_syntax` non-bug -- `resolve_command_permission` threads it
   through exactly as `resolve.py`'s old closure did (as a required positional).
2. Used the corrected test-double split (5 adapters / 13 actual call sites in production terms --
   see above for the exact recount -- and 6 stubs / 26 call sites) rather than design B's original
   undercount, and did not treat the 26-site work as "mostly mechanical" the way the wrong split
   would have suggested; the stub-rewrite work (building `_resolve_via_cascade`) was the
   substantive part of stage 4.

## Anything found wrong beyond the two corrections already given

Nothing beyond what's noted above. One minor thing worth flagging for the record: an early check I
ran (an unused-import/local-import scan) was an undisclosed inline `python -c`/heredoc, a process
violation of this project's own intent-disclosure convention -- caught and corrected mid-task; no
repeat.

## Files touched

**Production** (10, several trivial doc-only): `toolguard/config_types.py`,
`toolguard/file_matching.py`, `toolguard/permission_resolution.py`, `toolguard/resolve.py`,
`toolguard/permissions.py` (1 doc line), `toolguard/config.py` (3 doc lines),
`toolguard/session_start.py` (1 doc line), `toolguard/hook.py` (2 doc lines),
`toolguard/compound.py` (3 doc lines), `tools/architecture_fitness.py` (1 doc line).

**Tests** (10): `test/unit/test_configuration.py`, `test/unit/test_hard_deny.py`,
`test/unit/test_hierarchical.py`, `test/unit/test_hook.py`, `test/unit/test_hook_eval.py` (1 doc
line), `test/unit/test_logging_streams.py`, `test/unit/test_permission_resolution.py`,
`test/unit/test_resolve.py` (2 doc lines), `test/unit/test_takeover_mode.py`,
`test/unit/test_architecture.py` (allowlist).

No new files created (`file_matching.py` was already created by stage 1; I only modified it).

## Not committed

Per instructions, no git write operations performed. Ready for Arnon to review and commit
together with stage 1.

## Elapsed time / cost estimate

- Phase 1 (read design docs, plan, memory): ~25 min, ~$0.9
- Phase 2 (implementation across 20 files): ~55 min, ~$2.6
- Phase 3 (self-review: pyright, ruff, corpus, cycle-proof, assertion-diff audit): ~15 min, ~$0.6
- Phase 4 (report, memory, IDE opens): ~5 min, ~$0.2
- **Total: ~1h40m, ~$4.3** (Sonnet 5 pricing estimate from token usage; approximate, not precise).

## Follow-up: fix pass on the code review (2026-08-09, ~20:48-21:00)

Code review at `toolguard-memories/latest-code-review-report.md` (0 Critical, 2 Major, 4 Minor) came
back after this report was written. Arnon asked for three of the findings fixed, one finding
recorded in a docstring, and everything else (including the eager-matching cost, the cascade's
shape, and #07's general stale-prose sweep) explicitly left alone.

### MAJ-2: 16 stale BDD docstrings in `test_configuration.py`

Confirmed the review's diagnosis: my earlier rename above (`test_resolve_permission_detailed...`
-> `test_resolve_command_permission...`) picked the WRONG successor. Every test in this file goes
through `_resolve_via_cascade`, which calls `resolve_permission_cascade` (the pure fold), never
`resolve_command_permission` (the real-matcher orchestrator these tests deliberately avoid).
Fixed all 16: 15 `When resolve_command_permission('Bash', ...) ...` docstring lines, 1 class
docstring ("the engine's resolve_command_permission" at `TestRulesDirectoryMergeSemantics`), and
renamed the test method itself (`test_resolve_command_permission_reason_cites_rules_dir_file_path`
-> `test_resolve_permission_cascade_reason_cites_rules_dir_file_path`). Confirmed via grep this was
exhaustive and that `test_permission_resolution.py`/`test_hierarchical.py` (which correctly call
the real `resolve_command_permission`) were untouched -- their docstrings were already accurate.

### MAJ-1: `technical-notes.md` naming a deleted function, 6 references

Fixed the 6 flagged lines (244, 328, 373, 385, 391, 404), each renamed to the current accurate
symbol rather than banner-flagged:
- L244: `resolve_permission_detailed` -> `resolve_command_permission`/`resolve_file_path_permission`
  (the level cascade is now orchestrated by two entry points, not one).
- L328, L385: `hook._check_file_path_hard_deny` / `hook._decide_file_path_at_level_detailed` ->
  `file_matching.check_file_path_hard_deny` / `file_matching.decide_file_path_at_level_detailed`
  (both module AND name were stale; the review's "doubly stale" framing was right).
- L373: `resolve_permission_detailed` -> `resolve_permission_cascade` (that's where
  `_detect_override` is actually invoked from now, inside `_resolve_unclamped`).
- L391: same rename -- `resolve_permission_cascade` is what actually constructs and returns
  `RuntimeVerdict`.
- L404: `resolve_permission_detailed` -> `resolve_command_permission` in the 3-item list; left
  `hook.resolve_bash_permission_detailed` on that same line untouched even though it's ALSO
  wrong-module (it lives in `resolve.py`) -- that specific staleness wasn't named in MAJ-1 and
  falls under #07's sweep, per Arnon's explicit "leave the rest alone."
Repo-wide grep after the edit: zero remaining hits for `resolve_permission_detailed` or the two
`hook._*` names anywhere in `.py`/`.md` outside `toolguard-memories`.

### MIN-2: `match_file_path_pattern` / `anchor_file_pattern` de-privatised on a false rationale

Measurement confirmed (git diff against the pre-stage-1 base, which had these as `_anchor_file_pattern`/
`_match_file_path_pattern` already-private helpers in `resolve.py`): stage 2's mechanical move made
them public in `file_matching.py` on a rationale ("both cross a module boundary") that was true for
`decide_file_path_at_level_detailed`/`check_file_path_hard_deny` but not these two. Restored the
leading underscore on both. Updated every reference:
- `file_matching.py`: definitions, 4 internal call sites, and the module docstring's visibility
  rationale (narrowed to the 2 names that actually cross a boundary; also deleted the adjacent
  false claim "`resolve.py` re-exports every name below" -- MIN-1's fix, directly in the same
  sentence I was already touching for MIN-2, not a separate sweep).
- `test_hierarchical.py`: 4 local imports + call sites in `TestAnchorFilePattern` (all local
  imports inside test methods, an existing pattern in that file -- untouched otherwise).
- `config_types.py`: 2 docstring cross-references (`ResolveConfig.resolve_config_path`,
  `PathAnchoring`'s own docstring).
- `resolve.py`: 1 docstring list of what stage 1 moved out.
Repo-wide grep after the edit: zero remaining unprefixed hits. Left `test_recommended_protections.py`
alone -- it already says `_anchor_file_pattern` (coincidentally correct on the name) but names the
wrong module (`resolve.py`); that's pre-existing #07-scope staleness, not something this fix touched.

### Recorded, not fixed: the narrowed-not-eliminated seam

Added one paragraph to `permission_resolution.py`'s module docstring, right after the "import graph
stays a DAG" sentence: states plainly that the DAG claim is import-graph-only, that
`permission_resolution`/`file_matching` still call `Configuration`'s methods at runtime through the
Protocol-typed `config` parameter, that this is the same invisibility class as the callable this
punch-list removed, and that it's currently acyclic but nothing here would notice a future
`Configuration` method calling back in. No design change, no test added -- record only, as asked.

### Verification

- `uv run ruff format .` / `uv run ruff check .`: clean, whole repo, both before and after.
- `uv run python -m unittest discover -s test -t .`: **Ran 2733 tests, OK** -- byte-identical count
  to the review baseline and to the original implementation report above.
- `uv run python tools/architecture_fitness.py --layers`: completeness and direction both clean.
- Golden verdict corpus: covered by `test.unit.test_verdict_corpus` inside the same full-suite run
  (no separate corpus-only invocation needed; already 9/9 inside the 2733).
- Self-review scope check: 6 files touched this pass (`test_configuration.py`, `test_hierarchical.py`,
  `technical-notes.md`, `file_matching.py`, `config_types.py`, `resolve.py`) plus one new paragraph
  in `permission_resolution.py` -- well inside scope-inflation guardrails, all edits textual
  (renames, docstring corrections, one added paragraph), no new files, no behaviour change.
- No git write operations performed, per instructions.

### Files touched this pass

`test/unit/test_configuration.py`, `test/unit/test_hierarchical.py`, `technical-notes.md`,
`toolguard/file_matching.py`, `toolguard/config_types.py`, `toolguard/resolve.py`,
`toolguard/permission_resolution.py`.

### Elapsed time / cost estimate (this pass only)

- Phase 1 (read review report + affected files, plan): ~7 min, ~$0.35
- Phase 2 (implementation: 16 docstrings, 6 technical-notes.md refs, 2 renames + cross-refs, 1
  recorded-seam paragraph): ~8 min, ~$0.5
- Phase 3 (self-review: format, lint, full suite, architecture fitness, targeted diff review): ~5 min, ~$0.3
- Phase 4 (this report): ~3 min, ~$0.15
- **Total this pass: ~23 min, ~$1.3** (Sonnet 5 pricing estimate from token usage; approximate).
