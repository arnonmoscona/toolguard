---
title: TOO-45 R3 implementation report
type: note
permalink: toolguard/too-45/too-45-r3-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

## Summary

R3 ("decisions carry structured data; prose is rendered, never parsed") completed for the
remaining work: population of `BashResolution.matched_rule` / `FileResolution.matched_rule` at
their construction sites, and conversion of the 6 listed parse sites. `config.py` /
`config_types.py` were already done before this session started (green baseline confirmed:
2279 tests).

## Files touched this session

- `toolguard/resolve.py` -- populated `FileResolution.matched_rule` (both branches),
  `BashResolution.matched_rule` (new `_deciding_sub_match_rule` helper), deleted the
  bracket-stripping + marker-prefix parse in `_resolve_one`.
- `toolguard/hook.py` -- converted `_reason_suffix_or_placeholder`,
  `_matched_rule_for_single_command`, `_log_non_allow_decision`, and the
  `_handle_file_path_tool` allow branch to consume structured `matched_rule` instead of
  parsing `reason`. **`_parse_compound_match_details` was NOT deleted** -- see "Pushback"
  below.
- `test/unit/test_hook.py`, `test/unit/test_resolve.py` -- updated call sites and one rewritten
  test, listed in full below.

**Production files touched this session: 2** (`resolve.py`, `hook.py`). Combined with the 2
already done before this session (`config.py`, `config_types.py`), **R3's total production
file count is 4** -- matching the delta note's "adding one structured field costs ~6 production
files today" measurement closely enough to still make the R1 argument in numbers (4, not 6,
likely because two of the originally-estimated sites turned out to share one edit block in
resolve.py).

## Final R3 site count

`tools/architecture_fitness.py --predicates` now reports exactly **1** R3 site:

```
resolve:588 in resolve_file_path_permission_detailed(): if reason.startswith(_no_match_prefix):
```

This is the "Command" -> "Path" no-match reword the ticket explicitly put out of scope
(section C). Left untouched, exactly as instructed.

## Pushback: `_parse_compound_match_details` could not be deleted as instructed

The ticket instruction (item 3) was to delete this function and have `_log_allowed_command`
consume `BashResolution.sub_matches` instead. I implemented that first, and it broke two
existing TOO-19 m5 regression tests the moment I ran them
(`test_compound_escape_hatch_leaf_logs_the_same_placeholder`,
`test_single_leaf_and_compound_agree_for_the_silent_allow_value`) plus a KeyError in a third.

Root cause, confirmed by tracing `compound.py::_resolve_leaf_detailed`'s ask-floor branch: for
a foreign inline-code / heredoc leaf (e.g. `python -c "print(1)"`), `resolve_one` is called
with the TRUNCATED outer-command stub (`python -c`, via `_extract_outer_command`), not the
leaf's real text. If that stub happens to match a real allow rule (e.g. a broad
`Bash(python *)`), the per-sub-command `SubMatch` genuinely has a non-`None` `matched_rule` --
but `_resolve_leaf_detailed` unconditionally overrides ANY non-deny outcome for an ask-floor
leaf with the undecidable-fallback escape hatch anyway, because matching the stub never
verifies the unread inline payload. So `SubMatch.matched_rule is None` is NOT equivalent to
"this leaf is an escape hatch" for ask-floor leaves specifically -- and `SubMatch.sub_command`
for the same leaf is also the wrong (truncated) text for the audit log.

This classification (`fallback_kind` in compound.py's terms) is computed entirely inside
`compound.py`, AFTER `resolve_one` (and therefore `SubMatch` construction) already returned,
and is never threaded back through the `resolve_one` 3-tuple contract. Closing this properly
would mean widening that contract -- exactly the change `BashResolution.fallback_warning`'s own
docstring already documents was judged disproportionate once, for a structurally identical
case. I judged doing that here, inside a "mechanical conversion" step, as scope inflation, and
reverted to keeping `_parse_compound_match_details` (same name, docstring rewritten to record
this investigation and why it survives). The single-leaf case DID convert cleanly (see below)
since for a lone leaf `BashResolution.reason` IS the leaf's own final, floored reason, so the
existing `fallback_kind_for_reason` guard in `_reason_suffix_or_placeholder` already covers it
correctly with no change needed there.

Net effect: 5 of the 6 listed sites converted to structured data; the 6th
(`_parse_compound_match_details` / `_log_allowed_command`'s compound branch) stays
reason-driven, now with a docstring explaining why, and a regression test
(`test_multi_leaf_reason_round_trips_through_hooks_own_log_breakdown` in test_resolve.py)
updated to record the finding.

## Was the deciding sub-match rule for a compound `BashResolution` cleanly recoverable?

Yes, for deny/ask (first sub-match whose own decision equals the compound's). For a
genuinely multi-leaf all-allow compound there is no single decider by design (matches
`_combine_strictest`'s own logic) and it deliberately returns `None`. This part of the ticket's
plan held up exactly as described; only the SEPARATE hook.py compound-logging site (item 3) hit
the gap above.

## Prose differences accepted

None. `test.unit.test_verdict_corpus` (`test_tracked_fields_unchanged_or_acknowledged`,
`test_no_verdict_changed`, and the two e2e equivalents) all pass clean -- no
`TOOLGUARD_CORPUS_ACCEPT_PROSE=1` was needed.

## One discovered, uncaught, non-corpus-tracked log-content difference

For a file-path (Read/Write/Edit) tool hard-denied via the pooled `[hard_deny]` rule,
`_check_file_path_hard_deny` computes the matched pattern internally but returns only a
3-tuple that never exposes it separately (only baked into `reason`). Per the ticket's explicit
instruction, `FileResolution.matched_rule` stays `None` for this branch. Consequence:
`_log_non_allow_decision`'s "Violated Rules" log entry for this case now records the FULL
reason text (`"Path matches hard_deny pattern: X (cannot be overridden)"`) rather than the OLD
colon-split extraction (`"X (cannot be overridden)"`) -- more verbose, not fabricated, and
outside the corpus's tracked fields (reason/context/provenance in the hook's JSON response, not
the audit LOG file's matched-rule field), so no test caught it and none was pinning the old
value either. No verdict or JSON-response change. Bash hard-deny is unaffected and in fact
slightly improved (its `SubMatch.matched_rule` already carried the real pattern via
`check_hard_deny`'s own m3 fix, so the logged value is now the clean pattern instead of the old
extraction's trailing `"(cannot be overridden)"` fragment). Left as the ticket instructed;
flagging for Arnon to decide whether it's worth a follow-up (widening
`_check_file_path_hard_deny`'s return, mirroring `check_hard_deny`'s Bash-side convention).

## Test changes (all mechanical propagation of the signature change; no test weakened)

- `test/unit/test_resolve.py`: `_logged_rules` and the standalone
  `test_no_match_fallback_allow_also_records_the_placeholder` call now pass
  `matched_rule=result.matched_rule` to `_log_allowed_command` (required -- without it the
  single-leaf branch has nothing to render for a genuine match). `_log_and_capture` and the two
  standalone `_log_non_allow_decision` calls now pass `result.matched_rule` as the 8th
  positional arg (required for the deny genuine-match test; the ask-side one didn't strictly
  need it but was updated for consistency). `test_multi_leaf_reason_round_trips_through_hooks_own_log_breakdown`
  is unchanged in what it asserts, with its docstring extended to record the sub_matches
  investigation above.
- `test/unit/test_hook.py`: `test_simple_command_logs_matched_rule` now passes
  `matched_rule="git *"` explicitly (required -- the function no longer derives it from
  `reason`). `TestParseCompoundMatchDetails` and the rest of `TestLogAllowedCommand` are
  unchanged in behaviour, docstrings updated to note the R3 investigation.

No test was deleted and no test's assertions were weakened; every change either supplies data a
now-thinner function signature requires, or documents an investigation.

## Verification (final)

- `uv run python -m unittest discover -s test -t .` -- 2279 tests, OK (same count as baseline).
- `uv run python -m unittest test.unit.test_verdict_corpus` -- 6/6 OK, no acknowledgements needed.
- `uv run python tools/architecture_fitness.py --guard` -- PASS, 12/12 canaries.
- `uv run python tools/architecture_fitness.py --predicates` -- R3 down to the 1 sanctioned
  out-of-scope site.
- `uv run python tools/corpus_build.py --verify` -- OK, no differences (5389 in-process + 30
  e2e).
- `uv run ruff format .` / `uv run ruff check .` on all touched files -- clean.

## Anti-pattern scan

No async/await, no threading, no function-local imports introduced. All new/changed functions
and classes carry docstrings. Stdlib only.

## Elapsed time / cost estimate

- Phase 1 (read memory, plan, requirements capture): ~15 min.
- Phase 2 (implementation, including the ask-floor investigation and revert): ~55 min.
- Phase 3 (self-review, verification loops): ~15 min.
- Phase 4 (this report): ~5 min.
- Total: ~90 min. Estimated cost (Sonnet, this session's token volume): roughly $3-5.
