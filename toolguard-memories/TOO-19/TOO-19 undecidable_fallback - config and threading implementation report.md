---
title: TOO-19 undecidable_fallback - config and threading implementation report
type: note
permalink: toolguard/too-19/too-19-undecidable-fallback-config-and-threading-implementation-report
---

## Summary

Added a new, independently-configurable `undecidable_fallback` setting (TOO-19), mirroring
`no_match_fallback` but answering a different question: "I could not safely read this command
at all" (foreign inline code/heredoc sinks, complex control structures, process substitution)
rather than "I read the command and no rule matched it". Config layer + threading only, per
scope (no docs, no `toolguard/tools/danger.py`).

All verification passed: 1988/1988 unit tests (baseline 1949 + 39 new), `ruff check .` clean,
`ruff format` applied only to touched files, stdlib coverage runner shows every new branch
(all 3 floored outcomes x both undecidable shapes) executed, and the sandbox tool confirms
correct end-to-end behavior under all three settings.

## Files touched

**Source (3 files):**
- `toolguard/config.py` -- `_DEFAULT_UNDECIDABLE_FALLBACK`, `_VALID_UNDECIDABLE_FALLBACKS`
  constants; `Configuration.resolved_undecidable_fallback()` method (top-level key only, no
  legacy alias, no `warn_deny` spelling, more-specific-wins, native layers ignored, unset/bad
  value -> 'ask'); exemption comment added to `_apply_parse_failure_ask_floor`'s docstring
  (HARD INVARIANT).
- `toolguard/compound.py` -- floor helper `_apply_undecidable_floor` + two lookup tables
  (`_DECISION_STRICTNESS`, `_UNDECIDABLE_FLOOR_DECISION`); `undecidable_fallback: str = "ask"`
  parameter threaded through `_resolve_leaf`, `resolve_compound_permission`,
  `check_compound_permission`; both call sites (ask_floor leaf branch, UndecidableSegment
  branch) updated to apply/consult the floor and build a reason naming
  `undecidable_fallback=<value>` for non-ask outcomes.
- `toolguard/resolve.py` -- `resolve_bash_permission_detailed` now sources
  `config.resolved_undecidable_fallback()` and passes it to `resolve_compound_permission`;
  docstring updated. No signature change (config was already a parameter), so `hook.py` and
  `tools/decision.py` needed zero changes.

**Tests (4 files):**
- `test/unit/test_configuration.py` -- new `TestResolvedUndecidableFallback` class (10 tests:
  default, explicit values, more-specific-wins, native-layer-ignored, invalid-value,
  no-legacy-alias, independence from `no_match_fallback`); one new test added to
  `TestParseFailureAskFloor` for the HARD INVARIANT (allow_with_warning + broken config still
  asks).
- `test/unit/test_compound.py` -- three new classes: `TestApplyUndecidableFloor` (full 3x3
  matrix, 10 tests, unit-level on the pure helper), `TestUndecidableFallbackAskFloorLeaf` (6
  tests: 3 settings + explicit-deny-never-weakened + 2 reason-wording checks),
  `TestUndecidableFallbackSegment` (6 tests: 3 settings on process substitution + a second
  undecidable shape (nested while/if-else) across all 3 settings + 2 reason-wording checks),
  `TestCheckCompoundPermissionUndecidableFallback` (2 tests confirming the public wrapper
  threads the parameter and defaults correctly).
- `test/unit/test_resolve.py` -- new `TestUndecidableFallbackThreading` class (6 tests):
  ask_floor leaf under each setting, UndecidableSegment under each setting, default-config
  regression guard, the no_match_fallback/undecidable_fallback independence test (both set in
  one config, each governs only its own command), and the end-to-end HARD INVARIANT test
  (broken config + allow_with_warning still asks, going through the real
  `Configuration.resolve_permission_detailed` parse-floor path).
- `test/unit/test_hook.py` -- one method added to the pre-existing `_FakeConfig` test double
  (`resolved_undecidable_fallback` returning `"ask"`), required because `resolve_bash_permission_detailed`
  now calls it and the fake previously had no such method. This was a necessary compatibility
  fix to an existing test double's API surface, not new test-writing scope creep -- three
  hook tests were failing with `AttributeError` before this fix.

Total: 3 source files, 4 test files (one of which is a one-method compatibility fix). Well
under the scope-inflation thresholds.

## Floor-helper design and `_combine_strictest` reuse decision

`_apply_undecidable_floor(decision, undecidable_fallback)` is a small pure function: two module-level
lookup tables (`_DECISION_STRICTNESS = {allow:0, ask:1, deny:2}` and
`_UNDECIDABLE_FLOOR_DECISION` mapping each fallback value to the decision it floors to,
with `allow_with_warning -> allow` meaning "no floor") plus a 3-line strictest-of-two body.

**Considered reusing `_combine_strictest`** (which already ranks deny>ask>allow) instead of a
separate table. Decided against it:
- `_combine_strictest` combines a LIST of already-decided sub-command results, with its own
  reason-building rules (single-allow passthrough vs "cmd -> pattern" summary for multiple
  allows) and `additional_context` accumulation semantics for ties. The floor here clamps a
  SINGLE decision (or, for `UndecidableSegment`, supplies one outright with no prior decision
  at all) against a configured minimum -- a different question with different tie-breaking
  needs (the floor never needs to build a multi-item summary).
- Faking a 4-tuple "combine with the floor" call into `_combine_strictest` to reuse its
  ranking would couple two independent concerns (per-leaf floor application vs multi-leaf
  combination) for the sake of sharing a two-line lookup table, and would make
  `_combine_strictest`'s reason-formatting logic (which assumes real matched rules with
  parseable `" -> "`/`": "` reason shapes) responsible for synthesizing floor-only reasons it
  was never designed to produce.
- The actual duplication is minimal (one dict literal, `{"allow": 0, "ask": 1, "deny": 2}`)
  and is documented in `_apply_undecidable_floor`'s neighboring comment explaining exactly
  why it's a separate table. I judge this the right tradeoff: two lines of duplicated
  ranking data vs. coupling two independently-evolving concerns.

The `UndecidableSegment` branch does NOT call `_apply_undecidable_floor` at all -- per spec,
that segment was never resolved against any rule, so there is no underlying decision to floor;
it looks up `_UNDECIDABLE_FLOOR_DECISION` directly.

## Sandbox observations

Ran `uv run python -m toolguard.testing.sandbox --config <file> --command "python -c 'import os'"`
under all three settings (config allowed the outer `python -c` command):

- `undecidable_fallback = "ask"` (default): `verdict: ask`, reason
  `"ASK floor applied (inline/heredoc foreign code): python -c"` -- byte-for-byte the
  pre-TOO-19 wording, confirming zero behavior change for existing installs.
- `undecidable_fallback = "deny"`: `verdict: deny`, reason
  `"Denied by undecidable_fallback=deny (inline/heredoc foreign code, unable to safely
  verify): python -c"`.
- `undecidable_fallback = "allow_with_warning"`: `verdict: allow`, reason
  `"Allowed with a warning by undecidable_fallback=allow_with_warning (inline/heredoc foreign
  code, unable to safely verify): python -c"`.

Also checked the `UndecidableSegment` path with `diff <(sort a) <(sort b)` (config allowed
`diff:*`) under `undecidable_fallback = "deny"`: `verdict: deny`, reason
`"Undecidable segment denied by undecidable_fallback=deny (command contains process
substitution <(...) or >(...)): diff <(sort a) <(sort b)"`. Confirms the direct
(non-strictest-wins) fallback-taking for segments works end to end.

## Hard invariant verification

Added an explicit unit test (`test_undecidable_fallback_allow_with_warning_does_not_relax_parse_failure_floor`
in `TestParseFailureAskFloor`) and an end-to-end test
(`test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback` in the new
`TestUndecidableFallbackThreading` class) proving `undecidable_fallback = "allow_with_warning"`
plus a recorded parse failure still resolves to `ask`. Added a comment at
`_apply_parse_failure_ask_floor`'s docstring explaining why no future setting may ever
parameterize this clamp.

**One judged-out-of-scope observation on this invariant**: the parse-failure floor protects
every case that routes through `Configuration.resolve_permission_detailed` -- which covers the
`ask_floor` leaf case (foreign inline code/heredoc), since its outer-command check calls
`resolve_one` -> `resolve_permission_detailed`. It does NOT reach the `UndecidableSegment`
case (control structures, process substitution), because that segment is synthesized directly
in `compound.py` without ever calling `resolve_one`/`Configuration` at all -- by design, per
the ticket's own note that "this segment was never resolved against any rule". If a project's
config is broken (parse failure) in one file while a DIFFERENT, valid file sets
`undecidable_fallback = "allow_with_warning"`, a complex control-structure/process-substitution
command could resolve to `allow` even though the config is otherwise broken. Threading `config`
(or a "config is broken" boolean) into `compound.py` to close this would violate the ticket's
explicit "compound.py is config-free by design" architecture note and was not requested by the
hard-invariant section (which names `_apply_parse_failure_ask_floor` specifically, and that
method is untouched and unaffected). I did not fix this; flagging it for Arnon's judgment as a
narrow, double-failure-mode residual gap, not something I silently expanded scope to patch.

## Duplication/drift self-check

Searched the existing codebase before implementing for any existing "strictest-wins floor"
helper besides `_combine_strictest` (see reuse discussion above) and for any existing
"resolved_X_fallback" pattern besides `resolved_no_match_fallback` (used it as the direct
model, per the ticket's own instruction, deliberately diverging on the two named points: no
legacy alias, no `warn_deny`). No other implementation existed to reuse for the floor
semantics; `_apply_undecidable_floor` is new and necessary.

## Anti-pattern scan

No `async def`, no `threading` import, no function-level imports introduced in any touched
file. Docstrings present on every new function/class/method. `uv run ruff format` applied only
to the 7 files this task touched (not the 5 pre-existing unformatted repo files).

## Verification commands run

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- **OK, 1988 tests** (baseline 1949
  + 39 new).
- `uv run ruff check .` -- **All checks passed.**
- `uv run python tools/coverage_stdlib.py` then `grep '>>>>>>' cover/toolguard.compound.cover`
  / `cover/toolguard.config.cover` -- confirmed every new branch (all three floored outcomes on
  both the leaf and segment paths, plus `resolved_undecidable_fallback`'s native-layer-skip
  branch) is exercised; the only `>>>>>>` lines remaining in `compound.py` are pre-existing,
  unrelated dead-code guards (`elif kind == "ask"` never-hit defensive branches, empty-leaf
  guard, "unknown extraction type" guard) that predate this change.

## Elapsed time and estimated cost

- Phase 1 (planning: reading CLAUDE.md/rules, exploring config.py/compound.py/resolve.py,
  surveying existing tests): ~17:05-17:07, ~2 minutes.
- Phase 2 (implementation: config.py, compound.py, resolve.py edits, fixing the pre-existing
  `_FakeConfig` test double, writing ~39 new tests across 3 test files): ~17:07-17:15, ~8
  minutes.
- Phase 3 (self-review: full suite runs, ruff, coverage inspection, sandbox checks, this
  report): ~17:15-17:19, ~4 minutes.
- Total: ~14 minutes, well under the 30-minute scope-inflation guard.
- Estimated cost: this session used a moderate number of tool calls (file reads, greps, a
  dozen or so test runs) with Sonnet-class token pricing; rough estimate ~$0.30-$0.60 total
  based on typical input/output token volumes for a session of this length and file-read
  footprint. No unusually large files were read in full (config.py/compound.py were read in
  targeted slices).
