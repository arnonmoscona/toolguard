---
title: TOO-45 R3 review-fix implementation report
type: note
permalink: toolguard/implementation/too-45-r3-review-fix-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

## Summary

Fixed all five review findings from `implementation/TOO-45 R3 review-fix coder task recall.md`,
plus the low-risk half of item 6 (Attributes docstring completeness). Deferred the
function-collapse half of item 6 as explicitly authorized ("lower priority, only if above are
solid"). Full suite green throughout (2314 tests at completion, up from 2300 at session start),
verdict corpus green with zero accepted prose differences, `architecture_fitness.py --guard`
PASS (12/12 canaries), `corpus_build.py --verify` OK, ruff format/check clean.

## Item 1 -- mutation test (the acceptance criterion)

Mutated `toolguard/config.py:1727` from `matched_rule=matched_pattern` to
`matched_rule=reason_with_prov` (carrying the WRONG, prose-derived value). Before my new
assertions existed this mutation passed all tests; **after** adding exact-equality assertions it
now **FAILS with 6 test failures**:
`test_hook.TestLogAllowedCommand.test_simple_command_logs_matched_rule`,
`test_resolve.TestAuditLogMatchedRuleNeverFabricated.{test_a_genuine_rule_match_still_records_its_pattern,
test_single_leaf_escape_hatch_raw_matched_rule_is_the_misleading_stub_match}`,
`test_resolve.TestAuditLogViolatedRuleNeverFabricated.test_a_genuine_deny_still_records_its_real_pattern`,
`test_resolve.TestFileResolutionMatchedRuleExact.{test_allow_matched_rule_is_exactly_the_configured_pattern,
test_deny_matched_rule_is_exactly_the_configured_pattern}`. Reverted the mutation
(`git diff` on `config.py` is now empty); full suite back to 2314 OK.

New/tightened exact-equality assertions added:
- `ls` allow -> `matched_rule == "ls"` (was `assertIn`/`assertIsNotNone`)
- `rm -rf *` deny -> `violated_rules == ["rm -rf *"]` and `result.matched_rule == "rm -rf *"`
  (was `assertIn`/`assertNotEqual`)
- New: Bash hard-deny `curl:*` -> `result.matched_rule == "curl:*"`,
  `call.args[2] == ["curl:*"]`, `result.provenance is None` (pooled, by design)
- New: `TestFileResolutionMatchedRuleExact` (3 tests) -- file-path allow/deny exact pattern,
  hard-deny `None`/`None`
- New: escape-hatch single-leaf allow `result.matched_rule == "python *"` (the RAW, misleading
  stub match -- proves the log-time guard is doing real suppression, not just forwarding an
  already-None value) vs. escape-hatch single-leaf deny `result.matched_rule is None` (the raw
  field itself, distinct mechanism -- see item 4)
- Strengthened the existing multi-leaf divergence test
  (`test_compound_leaf_undecidable_deny_logs_the_same_placeholder`) with
  `result.matched_rule is None` and an assertion that both `sub_matches` say `'allow'` while the
  compound is `'deny'` -- this is the literal scenario `_deciding_sub_match`'s docstring now
  describes.

## Item 2 -- provenance regression

- `resolve.py`: added `provenance: Optional[Any] = None` to `BashResolution`, sourced from the
  same deciding `SubMatch` as `matched_rule` (refactored `_deciding_sub_match_rule` ->
  `_deciding_sub_match`, now returns the whole `SubMatch` so both fields come from one lookup,
  eliminating duplicate logic).
- `log_writer.py`: added `provenance: Optional[str]` param to `log_command()` and `_LogRecord`;
  rendered as its own `**Provenance**` markdown line (after Matched Rule, before Violated Rules)
  and its own `"provenance"` JSONLines key (after `matched_rule`). Omitted when falsy in both
  formats, matching every other optional field's convention.
- `hook.py`: added `_provenance_brief()` helper (`Provenance -> Optional[str]` via
  `describe_brief()`); threaded `provenance` through `_log_allowed_command` and
  `_log_non_allow_decision`, with the SAME fallback-escape-hatch suppression guard already
  applied to `matched_rule` (`single_provenance = provenance if single_matched_rule ==
  matched_rule else None`, and the deny-side mirror) -- a placeholder must never be paired with a
  real provenance from the leaf whose rule it replaced. Verified this guard is load-bearing: the
  escape-hatch allow case's raw `matched_rule` is a REAL "python *" match with a REAL provenance,
  which the guard correctly suppresses at log time.
- Compound (multi-sub-command) allow logging still cannot attribute per-sub-command provenance,
  for the SAME reason `_parse_compound_match_details` can't use `sub_matches` for matched_rule
  either (ask-floor leaf text/attribution mismatch, already documented) -- noted explicitly in
  `_log_allowed_command`'s docstring as a known scope boundary, not a regression (compound never
  had structured provenance before or after R3).
- New tests: `test_log_writer.TestProvenanceLogging` (6 tests: markdown allow/deny, hard-deny
  absence, jsonlines present/absent, field ordering) and
  `test_resolve.TestAuditLogProvenanceThreading` (3 tests: allow, deny, hard-deny, driven through
  the real `resolve.py -> hook.py -> log_command` pipeline, not just the renderer).
- Docs: updated `docs/architecture.md`'s Logging section and both markdown/JSONLines examples to
  show the new separate Provenance field; updated `toolguard/tools/log_harvest.py`'s module
  docstring examples (previously showed the OLD bracketed-suffix format, now stale); updated
  `Provenance.describe_brief()`'s docstring (now has two call sites, not one).

## Item 3 -- weakened test

Rewrote `test_hook.py::test_simple_command_logs_matched_rule` to build a real `Configuration`
(`Bash(ls)` allow), call `resolve_bash_permission_detailed("ls", ...)`, and assert
`_log_allowed_command` logs the resolver's OWN `matched_rule`/`provenance` (`"ls"` /
`"project: /p/toolguard_hook.toml"`), verified by direct probe before writing the assertion
(not guessed).

## Item 4 -- false docstring invariant

Renamed `_deciding_sub_match_rule` -> `_deciding_sub_match` (now returns the `SubMatch` itself,
not just its `.matched_rule` -- also serves item 2's provenance need). Removed the "mirrors
`_combine_strictest` EXACTLY" / "can never diverge" claims; replaced with an accurate statement
that it does NOT always agree with `_combine_strictest`'s surfaced reason, with the concrete
`ls && python -c "print(1)"` divergence example (verified live via probe, not just described)
and why it's still SAFE (returns `None` rather than mis-attributing). Grepped the whole repo for
any other reference to the old name or to the invariant language -- none found.

## Item 5 -- docstring policy

Trimmed, with line counts (before -> after, approx):
- `config_types.py::ResolvedDecision.matched_rule` Attributes entry: 9 -> 4 lines
- `resolve.py`'s comment before `sub_matched_rule = resolved.matched_rule`: 7 lines -> deleted
  (inlined `resolved.matched_rule` directly into the `SubMatch(...)` call, no longer needed)
- `hook.py::_reason_suffix_or_placeholder` docstring: 52 -> 28 lines (dropped the two verbatim
  reason-string code examples down to one inline example, dropped "historical implementation"
  narration)
- `hook.py::_matched_rule_for_single_command` docstring: 20 -> 15 lines (dropped the
  "even though... TOO-45 R3... no longer parsed" clause)
- `hook.py::_log_non_allow_decision` docstring: ~55 -> ~30 lines (same treatment, same reasoning
  as the allow-side function, cross-referenced instead of re-explained)
- `resolve.py::BashResolution.fallback_warning` Attributes entry: fixed the stale
  `resolve.py:128` reference to `_bash_result_is_fallback_warning` (function no longer exists --
  confirmed by grep, it was ALSO the actual mechanism description that was wrong, not just the
  name: rewrote to correctly say it's propagated directly from
  `resolve_compound_permission_detailed`'s structured return, matching what the code actually
  does and what `resolve_bash_permission_detailed`'s own docstring already said)
- Found and fixed a SECOND instance of the same dangling `_bash_result_is_fallback_warning`
  reference in `compound.py` (not caught by the original review, found via repo-wide grep per
  the doc-drift-sweep rule) -- replaced with "(since removed)" rather than a broken `:func:`
  pointer, keeping the historical narrative (real value: explains a real prior bug) without the
  dangling link.
- KEPT unchanged: `_parse_compound_match_details`'s docstring (negative-result content, explicit
  instruction), the hard-deny asymmetry comment in `resolve_file_path_permission_detailed`.

Rough total: ~90 docstring/comment lines removed net across `resolve.py`, `hook.py`,
`config_types.py`, `compound.py`.

## Item 6 (lower priority)

Done (cheap, low-risk): added `matched_rule` to the `Attributes:` blocks of both
`BashResolution` and `FileResolution` (was missing; `provenance` too since it's new).

Deferred (as explicitly authorized): collapsing `_reason_suffix_or_placeholder` +
`_matched_rule_for_single_command` into one function. Both are now short and correctly
documented after the item-5 trim; the collapse would touch call-site signatures across
`hook.py` and ripple into `test_resolve.py`'s helper functions for a purely cosmetic gain, and
risk was judged to outweigh benefit at this point in a session already touching 10 files.

## Files changed (this session, beyond what was already modified before I started)

Production: `toolguard/resolve.py`, `toolguard/hook.py`, `toolguard/log_writer.py`,
`toolguard/config_types.py`, `toolguard/compound.py`, `toolguard/tools/log_harvest.py`.
Tests: `test/unit/test_hook.py` (1 test rewritten, imports added), `test/unit/test_resolve.py`
(2 tests tightened to exact-equality, 1 test strengthened with a raw-field assertion, 5 new
tests added: 1 hard-deny, 1 escape-hatch raw-value, 3 FileResolution exact-match, 3 provenance
threading), `test/unit/test_log_writer.py` (6 new provenance tests). Docs:
`docs/architecture.md`.

`config.py` was touched only for the mutation-test exercise and is unchanged in the final diff
(`git diff toolguard/config.py` is empty).

## Tests modified (full list, per the "list every test you modified" instruction)

1. `test_resolve.py::TestAuditLogMatchedRuleNeverFabricated.test_a_genuine_rule_match_still_records_its_pattern`
   -- `assertIn`/`assertIsNotNone` -> `assertEqual(matched_rule, "ls")`. Pinned code changed
   (item 1).
2. `test_resolve.py::TestAuditLogViolatedRuleNeverFabricated.test_a_genuine_deny_still_records_its_real_pattern`
   -- `assertIn`/`assertNotEqual` -> `assertEqual(violated_rules, ["rm -rf *"])` +
   `assertEqual(result.matched_rule, "rm -rf *")`. Pinned code changed (item 1).
3. `test_resolve.py::TestAuditLogViolatedRuleNeverFabricated.test_compound_leaf_undecidable_deny_logs_the_same_placeholder`
   -- added `assertIsNone(result.matched_rule)` and the sub_matches-all-'allow' assertion. Pinned
   code changed (item 4's divergence claim).
4. `test_hook.py::TestLogAllowedCommand.test_simple_command_logs_matched_rule` -- fully rewritten
   to drive a real resolution instead of a hand-passed value. Pinned code changed (item 3).

All other test changes in this session are NEW tests (additions), not modifications of existing
pinned behavior.

## Corpus / prose

No `TOOLGUARD_CORPUS_ACCEPT_PROSE` needed -- `corpus_build.py --verify` reports zero differences
throughout, including after every meaningful edit (`test_verdict_corpus` run repeatedly, always
green: 6/6).

## Self-review / anti-pattern scan

No async/await, no threading, no function-local imports introduced. `uv run ruff format .` and
`uv run ruff check .` both clean. Full suite 2314/2314 OK. No git write operations performed
(the config.py mutation was applied/reverted via `sed`/file copy, not committed).

## Elapsed time / cost (rough estimate)

- Phase 1 (planning, reading resume notes + all relevant source, probing exact values): ~19:03
  -> ~19:15, ~12 min. Est. cost: ~$0.6 (heavy file reads, several targeted greps/probes).
- Phase 2 (implementation across resolve.py/hook.py/log_writer.py/config_types.py/compound.py/
  log_harvest.py/docs, plus all test additions): ~19:15 -> ~19:28, ~13 min. Est. cost: ~$0.9
  (many edits, moderate file re-reads).
- Phase 3 (mutation test, full-suite runs x9, corpus/guard/ruff checks): ~19:28 -> ~19:30 (checks
  interleaved with Phase 2 throughout, not a separate block) -- folded into Phase 2's estimate
  above; test runs are fast (~15s each) so the cost is dominated by tool-call overhead, not
  wall-clock.
- Phase 4 (this report, memory writes, IDE opens): ~19:30 -> ~19:33, ~3 min. Est. cost: ~$0.2.
- **Total elapsed**: ~30 min. **Total estimated cost**: ~$1.7 (Sonnet 5 pricing, rough token-count
  based estimate -- not precise).
