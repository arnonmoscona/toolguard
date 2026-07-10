---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-15
- task-memory
- implementation-report
---

## Summary

TOO-15 permission-fallback semantics + naming change: changed `no_match_fallback`'s
default from `deny` to `ask` (both takeover and non-takeover modes) and renamed its
values to `ask`/`deny`/`allow_with_warning`, retiring `warn_deny` as a deprecated but
still-accepted input alias that normalizes to `allow_with_warning`. Implemented via
strict RED-GREEN with two coordinator checkpoints (approved RED state; approved
extension after an unplanned 20-test gap was found and traced in GREEN).

## Files changed

Production (2 functional, 4 comment-only):
- `toolguard/config.py` -- the only file with a functional change (see below).
- `toolguard/permissions.py`, `toolguard/hook.py`, `toolguard/resolve.py`,
  `toolguard/tools/takeover_audit.py` -- terminology-only docstring/comment updates
  (warn_deny -> allow_with_warning as canonical, warn_deny kept as documented
  deprecated alias). No functional change in these four.

Tests (12 files):
- `test/unit/test_configuration.py`, `test/unit/test_resolve.py`, `test/unit/test_hook.py`,
  `test/unit/test_hook_eval.py` -- RED-phase edits (approved checkpoint 1): new/renamed
  tests for default-is-ask, deny explicit, allow_with_warning, warn_deny legacy alias,
  and a dedicated --eval-vs-live-hook anti-drift test across all five fallback values.
- `test/unit/test_ask_resolution.py`, `test/unit/test_hard_deny.py`,
  `test/unit/test_hierarchical.py`, `test/unit/test_logging_streams.py`,
  `test/unit/test_takeover_mode.py`, `test/unit/test_tools_decision.py`,
  `test/unit/test_tools_mining.py`, `test/unit/test_tools_replay.py` -- GREEN-phase
  extension (approved checkpoint 2): 20 pre-existing tests that implicitly relied on the
  old `deny` default, discovered only after the config.py change was applied (missed by
  the RED-phase string-based grep audit). Fixed per-test judgment (assert 'ask' where
  incidental, add explicit `no_match_fallback='deny'` where the test's real focus
  requires deny) plus one separately-fixed latent glob-pattern test bug.

## Key decisions

1. **Centralization confirmed, not built**: an earlier TOO-15 phase had already
   centralized ALL decision paths (`main()`, `--eval`/`_resolve_event`,
   `toolguard.tools.decision.decide()`) through
   `Configuration.resolve_permission_detailed()`/`resolved_no_match_fallback()`. This
   ticket's items #2 (keep hook/decide consistent) and #4 (--eval matches live hook) were
   therefore structurally already satisfied; I verified this by code tracing rather than
   assuming, and added a dedicated anti-drift test to lock it in going forward.
2. **Alias normalization is single-sourced**: `warn_deny` -> `allow_with_warning`
   normalization happens once in `resolved_no_match_fallback()`, covering both the
   top-level key and the legacy `[takeover_mode]` alias through the same code path (no
   duplicated special-casing).
3. **`TakeoverConfig.no_match_fallback` stays RAW, unnormalized** -- it's the legacy
   per-audit-tool field (`takeover_audit.py`'s "loose-no-match-fallback" invariant reads
   it directly); normalization is a `resolved_no_match_fallback()`-only concern. Verified
   the takeover audit's `!= "deny"` invariant needs no code change: it already correctly
   flags 'ask' as "not deny" once the default flips.
4. **20-test gap, found and fixed via a second approval gate**: my RED-phase audit
   grepped for the literal strings `no_match_fallback`/`warn_deny`, missing 20
   pre-existing tests that exercise the same shared fail-closed branch without
   mentioning either string. Rather than silently patch them, I traced every one to its
   underlying mechanism (not just grepped), found zero hidden production bugs, one
   genuine latent test bug (a glob pattern that never actually matched, masked by the old
   default coincidence), and reported back for explicit approval before touching any of
   them -- per the "don't edit tests in GREEN without approval" constraint.
5. **Per-test ask-vs-explicit-deny judgment**: for each of the 20, asserted `'ask'` when
   the test's real focus was incidental to the fallback value (anchoring, cascade
   mechanics, structural checks, anti-drift agreement); added an explicit
   `no_match_fallback='deny'` to the fixture when the test's real focus specifically
   required deny to make its point (mining's SIGNAL_DENIED bucket test, and the two
   `TestReplayBroadening` "CRITICAL safety check" / "landmine" tests). Full per-test
   rationale, including the two coordinator-flagged security-sensitive files
   (`test_hard_deny.py`, `test_takeover_mode.py`), is recorded in
   `implementation/coder-latest-task-recall.md`.

## Deviations from the original plan

- Original plan (RED-phase report) said "no other production file needs a functional
  change" -- this held true (only `config.py` changed functionally), but the RED-phase
  audit itself was incomplete, requiring the second GREEN-phase extension described
  above. Flagged and approved before proceeding.
- Fixed one latent pre-existing test bug (`test_file_path_deny_pattern_blocks_path`'s
  glob pattern) that was unrelated to TOO-15 but unmasked by it, per explicit coordinator
  instruction to fix the pattern rather than the expected value.

## Known limitations / follow-ups

- None identified for this slice. `docs/*.md` and `migrate_permissions` were explicitly
  out of scope per the task instructions and were not touched.

## Self-review results

- `uv run python -m unittest discover -s test -t .`: **Ran 1326 tests ... OK** (1312
  baseline + 14 net new).
- `uv run ruff check .`: **All checks passed!** (never ran `ruff format`).
- Anti-pattern scan (async/await, threading, local imports) on all 17 changed `.py`
  files: clean.
- `uv run python -m py_compile` on all 17 changed `.py` files: clean.
- Every new/renamed test carries a Given/When/Then BDD docstring in sync with its
  assertion.
- No git commits made; tree left dirty for review.

## Elapsed time / cost estimate

- Phase 1 (Planning: requirements capture, code archaeology, ticket-scope discovery):
  ~25 min.
- Phase 2 (RED: test edits across 4 files, verification): ~35 min.
- Checkpoint 1 wait (coordinator review): not counted.
- Phase 3 (GREEN part 1: config.py production change, first full-suite run, 20-test gap
  discovery + full investigation of every one): ~30 min.
- Checkpoint 2 wait (coordinator review): not counted.
- Phase 3 (GREEN part 2: 20-test extension edits, latent bug fix, comment touch-ups,
  final verification): ~35 min.
- Phase 4 (self-review, reports, handoff): ~10 min.
- Total active working time: ~2h15m.
- Estimated cost (Sonnet 5, this session's token volume -- heavy on file reads/greps for
  code archaeology and per-test tracing, moderate on edits): roughly $3-5 USD. This is a
  rough order-of-magnitude estimate, not a precise accounting.
