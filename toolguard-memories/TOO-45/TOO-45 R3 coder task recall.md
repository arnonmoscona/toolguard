---
title: TOO-45 R3 coder task recall
type: note
permalink: toolguard/too-45/too-45-r3-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

## Task

TOO-45 branch `too-45`, project toolguard. Step R3: "decisions carry structured data; prose is
rendered, never parsed" -- mechanical conversion, analysis already done (see delta note).

State on entry: `ResolvedDecision.matched_rule`, `config.py`'s population of it, and
`BashResolution.matched_rule`/`FileResolution.matched_rule` field declarations (empty, not yet
populated at construction sites) were ALREADY done and green (2279 tests). My job: populate the
two resolution types at their construction sites (section A), and convert 6 parse sites to read
structured data instead of parsing prose (section B).

## Section A -- populate

1. `resolve.py` `FileResolution` normal path (~578-585): add `matched_rule=resolved.matched_rule`.
2. `resolve.py` `FileResolution` hard-deny path (~550-556): leave `matched_rule=None` explicitly
   with a comment (`_check_file_path_hard_deny` returns no pattern to attribute).
3. `resolve.py` `BashResolution` (~744-763): derive `matched_rule` from `sub_matches` matching
   `compound.py::_combine_strictest`'s own tie-break: single sub-match -> that one's rule; deny ->
   first sub-match with decision=='deny'; ask -> first with decision=='ask'; multi-sub-match allow
   -> no single decider, leave None. Compute AFTER `apply_parse_failure_floor` using the final
   `decision`.

## Section B -- convert 6 parse sites

1+2 (same block). `resolve.py` `_resolve_one` inner function (~696-709): delete the `"  ["`
   provenance-suffix strip AND the marker-prefix loop; replace both with
   `sub_matched_rule = resolved.matched_rule` (already populated by config.py's
   `_resolve_permission_detailed_unclamped`).
3. `hook.py` -- DELETE `_parse_compound_match_details` and `_COMPOUND_MATCH_PATTERN`. Rewrite
   `_log_allowed_command` to take `sub_matches: List[SubMatch]` and `matched_rule: Optional[str]`
   params (both default None/empty). Compound branch (`len(sub_matches) > 1`): log one entry per
   `SubMatch`, using `sub_match.matched_rule` or `FALLBACK_ALLOW_PLACEHOLDER` when None. Single
   branch: use `_matched_rule_for_single_command(reason, matched_rule)`.
4. `hook.py` `_matched_rule_for_single_command` -- add a `matched_rule: Optional[str]` param,
   delegate to `_reason_suffix_or_placeholder("allow", reason, FALLBACK_ALLOW_PLACEHOLDER,
   matched_rule)`.
5. `hook.py` `_reason_suffix_or_placeholder` -- add `matched_rule: Optional[str]` param; KEEP the
   `fallback_kind_for_reason` guard (returns placeholder when it fires); when it does NOT fire,
   return `matched_rule` directly instead of `reason.split(": ", 1)[1]`. This function is shared
   by the allow side (`_matched_rule_for_single_command`) and the deny side
   (`_log_non_allow_decision`), so `_log_non_allow_decision` also gains a `matched_rule` param and
   both its call sites (`_handle_command_tool`, `_handle_file_path_tool`) must pass
   `result.matched_rule`.
6. `hook.py` `_handle_file_path_tool` (~977-979): replace
   `result.reason.split(": ", 1)[1] if ": " in result.reason else None` with `result.matched_rule`
   directly (no `_reason_suffix_or_placeholder` involved here -- this branch never had the
   fallback-escape-hatch guard to begin with, matching prior behaviour).

`_handle_command_tool`'s `_log_allowed_command` call site must additionally pass
`sub_matches=result.sub_matches, matched_rule=result.matched_rule`.

## Explicitly out of scope

`resolve.py:~563` "Command does not match..." -> "Path does not match..." reword. Do not touch.

## Hard invariant

`permissionDecision` must not change anywhere. Run
`uv run python -m unittest test.unit.test_verdict_corpus` after every meaningful edit. Full suite
+ `tools/architecture_fitness.py --guard` + `--predicates` + `tools/corpus_build.py --verify`
before finishing. `matched_rule` only feeds the AUDIT LOG (`log_command`'s `matched_rule` kwarg),
never the hook's JSON response to Claude, so it cannot affect `permissionDecision` -- but prose
differences (log text) still need investigating per the ticket's rule before accepting any
`TOOLGUARD_CORPUS_ACCEPT_PROSE=1`.

## Known test surface that pins the removed parse sites (must be updated, not silently left broken)

- `test/unit/test_hook.py`: `TestParseCompoundMatchDetails` (5 tests) directly tests the deleted
  `_parse_compound_match_details` -- must be deleted (function no longer exists). Import at top
  needs the same removal.
- `test/unit/test_hook.py`: `TestLogAllowedCommand` (3 tests) call `_log_allowed_command` with
  hand-written reason strings and NO `sub_matches`/`matched_rule` -- must be rewritten to
  construct `SubMatch` objects (or pass `matched_rule` directly for the single-command test) since
  the function no longer parses `reason` for the rule.
- `test/unit/test_resolve.py`: imports `_parse_compound_match_details` -- remove.
  `test_multi_leaf_reason_round_trips_through_hooks_own_log_breakdown` tests the deleted function
  directly -- rewrite against `result.sub_matches` or delete (decide during implementation,
  document choice).
  `TestAuditLogMatchedRuleNeverFabricated._logged_rules` helper (5 tests) must pass
  `sub_matches=result.sub_matches, matched_rule=result.matched_rule` to `_log_allowed_command`.
  `TestAuditLogViolatedRuleNeverFabricated._log_and_capture` helper (4 tests) and 2 standalone
  `_log_non_allow_decision` calls (`test_no_match_fallback_deny_has_no_colon_and_is_unaffected`,
  `test_ask_side_is_unaffected_full_reason_is_always_the_note`) must pass
  `matched_rule=result.matched_rule` (the ask-side one is not strictly required to pass, but
  update for consistency).

Every one of these is a mechanical propagation of the signature change, i.e. directly pins a
parse site being removed -- in scope per the ticket's test-modification rule. Will list the exact
final diff in the implementation report.

## Conventions

`uv run python`, `unittest` not pytest, docstrings on every function/class, stdlib only, no
async/threading/local imports, `ruff format`/`ruff check` clean, no git writes, do not touch
`test/verdict_corpus/`, `tools/corpus_build.py`, `tools/architecture_fitness.py`.

Report goes to basic-memory `TOO-45/` tagged `task-memory` + `TOO-45`.
