---
title: TOO-19 Phase 1 increments 3 and 5 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-1-increments-3-and-5-implementation-report
tags:
- task-memory
- TOO-19
---

## Summary

Implemented TOO-19 Phase 1 increments 3 and 5 combined: threaded `additionalContext`
through the Bash/compound resolution path (`toolguard/compound.py`) and surfaced the
accumulated result on `resolve.py::resolve_bash_permission_detailed` /
`BashResolution`. Full suite green (1923 tests, up from the 1909-test baseline),
`ruff check .` clean, `ruff format` applied only to touched files.

## Files changed

Production (2 files):
- `toolguard/compound.py` -- `resolve_one`'s contract grown from
  `Callable[[str], Tuple[str, str]]` to `Callable[[str], Tuple[str, str, Optional[str]]]`.
  `_resolve_leaf`, `_combine_strictest`, `resolve_compound_permission`,
  `check_compound_permission` all now thread/return a 3rd `additional_context` element.
  `_accumulate_contexts` (already landed, increment 4) is called from
  `_combine_strictest`'s all-allow branch -- not reimplemented.
- `toolguard/resolve.py` -- `BashResolution` gains `additional_context: Optional[str] = None`
  (mirroring `FileResolution`'s pattern from increment 2), NOT yielded by `__iter__`.
  `resolve_bash_permission_detailed`'s internal `_resolve_one` closure now returns
  3-tuples, sourcing the context from `ResolvedDecision.additional_context` (already
  populated by increment 2's `Configuration._resolve_permission_detailed_unclamped`).

Tests (5 files):
- `test/unit/test_compound.py` -- new `TestAdditionalContextThreading` class (9 tests,
  see below) plus fixed every existing `check_compound_permission`/`_resolve_leaf`
  call site's unpacking (20 `check_compound_permission` 2-tuple unpacks -> 3-tuple via
  sed; 9 `_resolve_leaf` call sites -> 3-tuple, `resolve_one` closures updated to
  return 3-tuples).
- `test/unit/test_resolve.py` -- new `TestBashAdditionalContext` class (5 tests).
- `test/unit/test_hard_deny.py` -- `TestHardDenyCommand._resolve` helper updated
  internally to unpack the new 3-tuple and discard the context (its 8 callers all
  expect a 2-tuple and don't exercise `additionalContext`, so the discard happens
  inside the helper rather than touching all 8 call sites).
- `test/unit/test_hierarchical.py` -- 4 call sites of `resolve_compound_permission`
  (2 inline `_resolve_one` closures, 2 in `TestResolveCompoundEdgeCases`) updated to
  3-tuple.
- `test/unit/test_multiline_bash.py` -- 1 call site (`_resolve` module helper).

No changes to `hook.py`: it calls `resolve_bash_permission_detailed` and accesses the
result via `bash_result.decision` / `.reason` / `.overrides` attribute access (not
tuple unpacking), so the new field on `BashResolution` and the changed
`resolve_compound_permission` signature don't touch it at all. Confirmed via grep --
`hook.py` never calls `resolve_compound_permission`/`check_compound_permission`
directly.

## ASK-floor decision (item 2)

Implemented exactly as directed in the task prompt, with the reasoning restated in
`_resolve_leaf`'s docstring:
- **deny branch** (`leaf.ask_floor` and `resolve_one(outer_cmd)` returns `deny`):
  passes the outer command's `additional_context` through unchanged. A deny IS the
  deciding match here, and an explanation is most valuable at a deny.
- **clamp-to-ask branch** (allow or ask, clamped to `ask` by the floor): returns
  `additional_context=None`. The floor, not the rule match, now determines the
  verdict -- exactly mirroring `Configuration._apply_parse_failure_ask_floor`'s
  choice to clear `provenance`/`override`/`additional_context` when it overrides a
  decision. Tested explicitly both ways:
  `test_ask_floor_deny_passes_context_through` and
  `test_ask_floor_clamp_to_ask_drops_context`.

No reason found to deviate from the directed behaviour -- it's the same principle
already codified at the config level in increment 2, just applied at the
compound-level ASK floor instead.

## `_combine_strictest` semantics (item 3)

- deny/ask branches: exactly one deciding leaf (`denied[0]`/`asked[0]`), its context
  passed through unchanged, no accumulation -- covered by
  `test_deny_in_compound_passes_denying_leafs_context_only` and
  `test_ask_in_compound_passes_asking_leafs_context_only` (each also asserts the
  OTHER leaf's context is NOT present in the result, the case flagged as most likely
  to be got wrong).
- all-allow branch: every allowed leaf's context routed through
  `_accumulate_contexts`, including the single-allowed-leaf case (a lone allowed leaf
  still surfaces its context -- `test_single_allowed_leaf_surfaces_its_context`).
  Verified: 2+ distinct enriched rules produce the joined paragraph text exactly
  (`test_multi_leaf_all_allow_accumulates_distinct_contexts` asserts the literal
  joined string, not just non-None); the same rule matching two leaves dedupes to one
  paragraph (`test_same_enriched_rule_matching_two_leaves_dedupes`); no enrichment
  anywhere yields `None` (`test_all_allow_compound_with_no_enrichment_yields_none`).
- `UndecidableSegment` (process substitution etc.) and the unknown-element-type
  branch both contribute `None` context -- verified with a real
  `diff <(sort a) <(sort b)` command
  (`test_undecidable_segment_yields_none_context`), not a hand-constructed
  `UndecidableSegment` object.

## `resolve_bash_permission_detailed` / `BashResolution` (item 5)

`BashResolution.additional_context` is populated straight from the 3rd element of
`resolve_compound_permission`'s return, which in turn is sourced per-sub-command from
`ResolvedDecision.additional_context` (already wired by increment 2 through
`Configuration._resolve_permission_detailed_unclamped`/`_entry_for_pattern`). NOT
yielded by `BashResolution.__iter__` (still a fixed 3-tuple
`decision, reason, overrides`), matching `FileResolution`'s precedent exactly --
verified with `test_bash_resolution_three_tuple_unpacking_still_works`.

One deliberate scope note: the Bash **hard_deny** path (`check_hard_deny` in
`permissions.py`, used inside `resolve_bash_permission_detailed`'s `_resolve_one`)
has no `additionalContext` lookup, unlike the file-path hard-deny path
(`_check_file_path_hard_deny` in `resolve.py`, which uses
`config.hard_deny_entries()`). The task prompt's item 5 only asked to source context
from `ResolvedDecision.additional_context`; it did not ask for a Bash-side
`hard_deny_entries`-style lookup, and I did not add one -- I return `None` for a Bash
hard-deny match and left a comment noting the asymmetry with the file-path path.
Flagging this explicitly since Arnon's plan note lists structured-entry parity as a
locked-in decision ("allow/deny/ask all support structured entries uniformly") --
this specific gap (Bash hard_deny context) is out of THIS increment's stated scope
but may be worth a follow-up if hard_deny context matters for Bash specifically.

## Duplication/drift self-check

- `_accumulate_contexts` (increment 4) was called, not reimplemented -- single call
  site added in `_combine_strictest`'s all-allow branch (`toolguard/compound.py:311`),
  confirmed via grep that no second definition or copy-pasted accumulation logic
  exists anywhere in `compound.py`, `resolve.py`, or `permissions.py`.
- No new pattern-matching, provenance-lookup, or entry-lookup logic was added --
  `resolve_bash_permission_detailed` reuses the already-populated
  `ResolvedDecision.additional_context` field (increment 2's
  `Configuration._entry_for_pattern`), exactly mirroring how
  `resolve_file_path_permission_detailed` already consumes it.
- `permissions.py` (`check_permission`, `check_hard_deny`,
  `decide_command_at_level_detailed`) was NOT modified, per the task's explicit
  instruction (many other callers) -- `check_permission`'s 2-tuple output is padded
  with `None` at the one call site (`check_compound_permission`'s lambda) rather than
  changing the function.

## Out of scope, not touched

- `hook.py` (increment 6: wiring `additionalContext` into the hook's JSON output) --
  confirmed via grep it needed NO fix either, since it uses attribute access on
  `BashResolution`, not tuple unpacking.
- `log_writer.py` (increment 7).
- Bash-side `hard_deny` context lookup (see note above under item 5) -- flagged as a
  possible gap, not implemented.

## Verification

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run
  python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- **1923 tests,
  OK** (baseline was 1909; +14 new tests: 9 in `test_compound.py`, 5 in
  `test_resolve.py`).
- `uv run ruff check .` -- all checks passed.
- `uv run ruff format` -- applied only to the 7 touched files (2 production, 5 test);
  no unrelated repo files reformatted.

## Elapsed time / cost estimate (rough)

- Planning (reading CLAUDE.md, plan note, source files, task recall write): ~10 min,
  ~$0.30 (mostly large file reads).
- Implementation (compound.py, resolve.py edits + fixing 5 test-file call sites): ~10
  min, ~$0.30.
- New test authoring (14 tests across 2 files) + verification runs: ~8 min, ~$0.25.
- Report writing: ~3 min, ~$0.05.
- **Total: ~30 min, ~$0.90** (Sonnet 5, rough token-based estimate -- not precise).
