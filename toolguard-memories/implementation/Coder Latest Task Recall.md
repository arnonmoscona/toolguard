---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- TOO-8
- task-memory
- coder-task
---

## Ticket
TOO-15 (permission-decision semantics change)

## Problem
When toolguard governs a tool (Bash/Read/Write/Edit) but that tool has NO allow rules
configured, the hook currently DENIES everything unconditionally
(`toolguard/hook.py` around lines 648 for file-path tools and 721 for Bash).
This bricks a fresh install. Also `no_match_fallback="warn_deny"` currently only
rewrites the deny reason string (`hook.py` ~line 751-761) and never actually allows;
and that fallback logic is wired only for Bash, not for Read/Write/Edit.

## Required new semantics (spec, implement exactly)
For a governed tool, the decision resolves as:
1. Command/path matches a deny or hard_deny rule -> deny (unchanged).
2. Matches an allow rule (more-specific-wins over deny) -> allow (unchanged).
3. NO rules at all for the tool (no allow AND no deny AND no ask AND no hard_deny
   patterns at ANY config level for that tool) -> return "ask" (KEY CHANGE; was deny).
   This is ALWAYS ask; NOT affected by no_match_fallback. Do NOT add a config item to
   override this -- a user wanting fail-closed-on-empty writes their own catch-all deny
   rule (flows through path #1).
4. Rules exist but none match -> apply no_match_fallback: default "deny";
   "warn_deny" -> ALLOW the operation but surface a warning (fix: must actually allow,
   not just reword a deny); "deny" -> deny. Must work for BOTH Bash and file-path tools.
5. no_match_fallback raised to a top-level config key, AND still accepted under
   existing [takeover_mode] section as backwards-compatible legacy alias, identical
   semantics. Now applies in BOTH takeover and non-takeover modes (previously gated on
   takeover enabled). If both top-level and [takeover_mode] set, top-level wins.
   Default "deny". See toolguard/config.py (_DEFAULT_NO_MATCH_FALLBACK, takeover/config
   parsing ~lines 654-921).

## CRITICAL: keep all decision paths consistent
hook.py is not the only decision path. toolguard/tools/decision.py (decide()) is used
by toolguard/tools/self_permission.py and audit tooling to evaluate what hook WOULD
decide. Must map every decision path first (hook.py, decision.py,
resolve_bash_permission_detailed, resolve_file_path_permission_detailed, and anything
in config.py / compound.py). Apply new semantics in shared/source-of-truth layer so
hook.py and decide() AGREE -- do NOT duplicate divergent logic. compound.py:71 already
emits "ask", create_hook_output passes permissionDecision straight through -- "ask" is
already fully supported.

## Process -- STRICT RED-GREEN (explicit requirement)
1. RED phase FIRST. Edit existing tests asserting OLD behavior (deny-on-empty,
   warn_deny-still-denies) to assert NEW behavior. ADD new tests for every changed
   behavior:
   - empty-config -> ask (Bash + each file tool)
   - rules-exist-no-match -> deny by default (Bash + file)
   - warn_deny -> allow+warn (Bash + file)
   - takeover + no_match_fallback="deny" still fail-closed
   - top-level no_match_fallback honored
   - legacy [takeover_mode].no_match_fallback still honored, same semantics
   - top-level wins when both set
   Run FULL suite, CONFIRM ONLY touched/added tests fail (intended red), nothing
   unrelated broke. Record exact red state -- required checkpoint.
2. GREEN phase. Only now modify production code (hook.py, decision.py/resolution
   layer, config.py) until ENTIRE suite passes. Do NOT edit tests during green (except
   genuine mistakes in own new tests -- call those out explicitly).
3. Run full suite: uv run python -m unittest discover -s test -t .

## Hard constraints
- Do NOT run any git write operations, do NOT commit. Leave tree dirty.
- Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples). May run
  `uv run ruff check .`.
- Always `uv run python ...`, never bare python.
- Every new/edited test function MUST carry Given/When/Then BDD docstring, kept in sync.
- No async, no threading, no imports inside functions.
- Add doc comments to any new/changed functions.

## PROCESS CHECKPOINT (added mid-task by coordinator)
HARD CHECKPOINT before GREEN phase. Complete RED phase fully (edit/add tests, run full
suite), confirm ONLY touched/added tests fail and nothing else broke. Then STOP --
do NOT modify any production code yet. Report red state back to coordinator (list of
every test file/function added or changed, one-line note of new behavior each asserts,
exact set of failing tests + failure reasons). WAIT for explicit approval before
starting GREEN phase.

## Report requirements
Write implementation report to basic-memory (project 'toolguard', tag TOO-15) covering:
decision paths found and where centralized; red state achieved (failing tests list)
before green; final green result (test counts); config precedence handling
(top-level vs legacy takeover_mode alias); decisions/edge cases hit. Give report
path/permalink in final message, don't ask to read inline.

If spec genuinely ambiguous or blocker found, STOP and report specific question rather
than guessing.


## RED-phase checkpoint reached (awaiting approval before GREEN)

Baseline before any test edits: 1282 tests, all passing (`uv run python -m unittest
discover -s test -t .`).

After RED-phase test edits: 1308 tests total (+26 new/changed test methods).
Result: `FAILED (failures=8, errors=14)` -- exactly 22 of the 26 touched tests fail;
the other 4 are regression-guard tests asserting UNCHANGED behavior (rules-exist,
no-match -> deny by default) which already pass today and must stay green after
GREEN too.

### Files touched (tests only, no production code changed)
1. `test/unit/test_configuration.py` -- two new classes:
   - `TestHasAnyRules` (7 tests) -- for a new `Configuration.has_any_rules(tool_name)`
     method (does not exist yet -> AttributeError/ERROR).
   - `TestResolvedNoMatchFallback` (7 tests) -- for a new
     `Configuration.resolved_no_match_fallback()` method (does not exist yet ->
     AttributeError/ERROR).
2. `test/unit/test_resolve.py` -- new class `TestNoMatchSemanticsNoDrift` (9 tests),
   anti-drift style (decide() vs resolve_bash/file_permission_detailed()), real
   Configuration objects via existing `_make_config` helper.
3. `test/unit/test_hook.py`:
   - Renamed/changed `test_read_no_allow_patterns_denied` ->
     `test_read_no_allow_patterns_asks` (expects 'ask' instead of 'deny').
   - Added `test_bash_no_allow_patterns_asks` (new).
   - Added new class `TestNoMatchFallbackThroughMain` (2 tests) using REAL
     `Configuration`/`ConfigLayer` objects (not the hand-rolled `_FakeConfig`)
     driven through `main()`.
   - Updated the `_FakeConfig.resolve_permission_detailed` test double in
     `_fake_config()` to model the new "tool entirely unconfigured -> ask" case
     (previously hardcoded unconditional deny).

### Exact RED state (22 failing before GREEN)
ERRORS (14, all `AttributeError` -- methods don't exist yet):
- test_configuration.TestHasAnyRules: test_false_when_tool_fully_unconfigured,
  test_false_when_no_layers_at_all, test_true_when_allow_configured,
  test_true_when_only_deny_configured, test_true_when_only_ask_configured,
  test_true_when_only_hard_deny_configured, test_false_is_tool_scoped
- test_configuration.TestResolvedNoMatchFallback: test_defaults_to_deny_when_nothing_set,
  test_top_level_key_honored, test_legacy_takeover_alias_honored_when_no_top_level_key,
  test_top_level_wins_over_legacy_alias_when_both_set,
  test_top_level_wins_even_when_set_at_a_less_specific_level,
  test_top_level_more_specific_layer_wins_among_top_level_setters,
  test_native_layer_top_level_key_ignored

FAILURES (8, assertion mismatches -- old value returned instead of new):
- test_hook.TestFilePathToolsInMain.test_bash_no_allow_patterns_asks (got 'deny', want 'ask')
- test_hook.TestFilePathToolsInMain.test_read_no_allow_patterns_asks (got 'deny', want 'ask')
- test_hook.TestNoMatchFallbackThroughMain.test_bash_warn_deny_fallback_allows_via_main
  (got 'deny', want 'allow')
- test_resolve.TestNoMatchSemanticsNoDrift.test_bash_fully_unconfigured_resolves_to_ask_no_drift
  (got 'deny', want 'ask')
- test_resolve.TestNoMatchSemanticsNoDrift.test_read_fully_unconfigured_resolves_to_ask_no_drift
  (got 'deny', want 'ask')
- test_resolve.TestNoMatchSemanticsNoDrift.test_bash_warn_deny_fallback_allows_no_drift
  (got 'deny', want 'allow')
- test_resolve.TestNoMatchSemanticsNoDrift.test_read_warn_deny_fallback_allows_no_drift
  (got 'deny', want 'allow')
- test_resolve.TestNoMatchSemanticsNoDrift.test_legacy_takeover_alias_warn_deny_honored_no_drift
  (got 'deny', want 'allow')

PASSING already (4, regression guards for behavior that must NOT change):
- test_resolve.TestNoMatchSemanticsNoDrift.test_bash_rules_exist_no_match_denies_by_default_no_drift
- test_resolve.TestNoMatchSemanticsNoDrift.test_read_rules_exist_no_match_denies_by_default_no_drift
- test_resolve.TestNoMatchSemanticsNoDrift.test_top_level_no_match_fallback_wins_over_legacy_alias_no_drift
- test_resolve.TestNoMatchSemanticsNoDrift.test_takeover_enabled_no_match_fallback_deny_still_fails_closed_no_drift
- test_hook.TestNoMatchFallbackThroughMain.test_bash_takeover_enabled_deny_fallback_still_fails_closed_via_main

Nothing else in the suite is affected: 1282 - 0 changed = all still pass (verified
via failures+errors totalling exactly 22, all within the touched/added set).

### Planned GREEN-phase design (not yet implemented)
- `toolguard/config.py`: add `Configuration.has_any_rules(tool_name)` and
  `Configuration.resolved_no_match_fallback()`; modify the fail-closed branch at the
  end of `resolve_permission_detailed` to consult both instead of unconditionally
  returning deny.
- `toolguard/resolve.py`: extend the file-path "Command"->"Path" reason rename to a
  `startswith` check (covers the new warn_deny-allow reason too); no other change
  needed (resolve_bash_permission_detailed/resolve_file_path_permission_detailed
  already just propagate whatever ResolvedDecision comes back).
- `toolguard/hook.py`: remove the two early "if not all_allow: deny" pre-checks
  (~644-660, ~719-733) and the now-redundant takeover-gated warn_deny reason-rewrite
  block (~751-761); add an `elif decision == "ask":` logging branch (status "ask")
  alongside the existing allow/deny branches for both the file-path and Bash
  resolution blocks.
- No changes planned to `toolguard/tools/takeover_audit.py` or
  `toolguard/tools/security_audit.py` (TakeoverConfig.no_match_fallback keeps
  resolving ONLY the legacy `[takeover_mode]` section, unchanged, for audit purposes
  -- this is intentionally a separate, narrower concept from the new
  `resolved_no_match_fallback()`).

STATUS: Awaiting explicit approval from coordinator before starting GREEN phase
(hard checkpoint per mid-task process-change instruction).


## RED-phase checkpoint reached (awaiting approval before GREEN) -- 2026-07-09

Baseline before any test edits: 1312 tests, all passing.

After RED-phase test edits: 1326 tests total (+14 new test methods; several
existing tests renamed in place, which does not change the count).
Result: `FAILED (failures=23)` -- exactly 23 of the touched/added tests fail;
the rest of the touched/added tests are regression-guard tests asserting
behavior that is unaffected by this change (explicit 'deny', top-level-wins
cases, the structural --eval-vs-live-hook no-drift property) and already pass
today.

Production code UNTOUCHED. Only these decision points were investigated and
confirmed to require NO code changes because they always pass an explicit
`no_match_fallback` value in their test fixtures (never rely on the
`_DEFAULT_NO_MATCH_FALLBACK` constant): test_takeover_mode.py,
test_tools_security_audit.py, test_tools_takeover_audit.py,
test_tools_config_access.py, test_tools_danger.py, test_session_start.py,
test_migration.py. Also confirmed: `toolguard/tools/takeover_audit.py`'s
"loose-no-match-fallback" MEDIUM invariant (hardcoded `expected_fallback =
"deny"`) needs NO code change -- it already flags "anything other than
'deny'" and 'ask' correctly falls into that bucket once the default changes;
none of its tests rely on the implicit default either.

### Files touched (tests only, no production code changed)

1. `test/unit/test_configuration.py` -- class `TestResolvedNoMatchFallback`:
   renamed/updated 8 existing tests (default-is-ask, top-level-key with
   'allow_with_warning', legacy-alias normalizes to 'allow_with_warning',
   native-layer default, invalid-value-falls-back-to-ask x2, more-specific
   top-level-setter normalizes); added 3 new tests (`test_value_ask_explicit_is_returned_as_is`,
   `test_value_deny_is_returned_as_is`, `test_legacy_alias_warn_deny_via_top_level_key_normalizes`).
   Two tests left UNCHANGED (top-level-wins-over-legacy-alias, top-level-wins-
   at-less-specific-level) since both already used non-legacy 'deny' as the
   winning value.

2. `test/unit/test_resolve.py` -- class `TestNoMatchSemanticsNoDrift`:
   renamed 2 "denies by default" tests to "asks by default" (the core
   default-flip anti-drift tests, Bash + Read); added 2 new explicit-deny
   anti-drift tests (Bash + Read) to preserve deny-path coverage now that it's
   no longer the default; renamed the 2 'warn_deny' tests to
   '..._legacy_alias_...' and updated their reason-string assertions from
   'warn_deny' to 'allow_with_warning'; added 2 new canonical
   'allow_with_warning' anti-drift tests (Bash + Read); updated the legacy
   [takeover_mode] alias test's reason assertion; added 2 new
   takeover-mode-specific tests (default-flip applies in takeover mode too;
   explicit allow_with_warning under takeover). Class docstring updated.

3. `test/unit/test_hook.py`:
   - `_FakeConfig.resolve_permission_detailed`'s no-match branch (hand-rolled
     test double): flipped its hardcoded fallback from "deny" to "ask" to
     stay in sync with the new real-Configuration default (this is test
     infrastructure, not production code).
   - Renamed `test_write_tool_denied` -> `test_write_tool_asks_on_no_match_by_default`
     (exercises the fake's no-match branch; now asserts 'ask'). This test
     already passes post-edit since the fake and assertion were updated
     together -- it is NOT one of the 23 RED failures.
   - Class `TestNoMatchFallbackThroughMain` (drives `main()` with a REAL
     Configuration): renamed `test_bash_warn_deny_fallback_allows_via_main` ->
     `test_bash_warn_deny_legacy_alias_allows_via_main` (reason assertion
     'warn_deny' -> 'allow_with_warning'); added 3 new tests: default-is-ask
     via main() (non-takeover), default-is-ask via main() with takeover
     enabled, and canonical 'allow_with_warning' via main(). Class docstring
     updated.

4. `test/unit/test_hook_eval.py`:
   - Renamed `test_eval_denies_floor_command` -> `test_eval_asks_on_unmatched_command_by_default`
     (the default-flip case for --eval) and added a new
     `test_eval_denies_floor_command_with_explicit_deny_fallback` to preserve
     deny-path coverage for --eval.
   - Added new class `TestEvalMatchesLiveHookUnderFallback` with
     `test_eval_matches_live_hook_for_every_fallback_value`: drives BOTH
     `main()` (no --eval) and `main() --eval` over the SAME Configuration for
     every no_match_fallback value (None/default, 'ask', 'deny',
     'allow_with_warning', 'warn_deny') and asserts identical verdicts. This
     satisfies ticket item 4 ("--eval must match the live hook", "add an
     anti-drift-style test"). This test ALREADY PASSES pre-GREEN (not one of
     the 23) because `_resolve_event`/`decide()` and `main()` already
     delegate to the exact same `Configuration.resolve_permission_detailed`
     primitive -- confirmed by code reading that items #2 and #4 of the
     ticket are structurally already satisfied; no separate reason-rewrite
     step exists anywhere to drift. This test guards that invariant going
     forward.

### Exact RED state (23 failing, all AssertionError -- no ERRORs)

test_configuration.py (9):
test_defaults_to_ask_when_nothing_set, test_invalid_legacy_alias_value_falls_back_to_ask,
test_invalid_top_level_value_falls_back_to_ask, test_legacy_alias_warn_deny_via_top_level_key_normalizes,
test_legacy_takeover_alias_honored_when_no_top_level_key, test_native_layer_top_level_key_ignored,
test_top_level_key_honored, test_top_level_more_specific_layer_wins_among_top_level_setters,
test_value_ask_explicit_is_returned_as_is

test_hook.py (4):
test_bash_allow_with_warning_fallback_allows_via_main, test_bash_default_no_match_fallback_asks_via_main,
test_bash_takeover_enabled_default_no_match_fallback_asks_via_main, test_bash_warn_deny_legacy_alias_allows_via_main

test_hook_eval.py (1):
test_eval_asks_on_unmatched_command_by_default

test_resolve.py (9):
test_bash_allow_with_warning_fallback_allows_no_drift, test_bash_rules_exist_no_match_asks_by_default_no_drift,
test_bash_warn_deny_legacy_alias_allows_no_drift, test_legacy_takeover_alias_warn_deny_honored_no_drift,
test_read_allow_with_warning_fallback_allows_no_drift, test_read_rules_exist_no_match_asks_by_default_no_drift,
test_read_warn_deny_legacy_alias_allows_no_drift, test_takeover_enabled_allow_with_warning_no_drift,
test_takeover_enabled_default_no_match_fallback_asks_no_drift

All failures are the expected value mismatch (old default 'deny' / old raw
'warn_deny' string vs new expected 'ask' / 'allow_with_warning'). Count
reconciles exactly: 1312 baseline + 14 new tests = 1326; 23 fail, 1303 pass
(1326 - 23 = 1303, all pre-existing plus the 14 new-but-already-true tests
minus the 9 renamed-in-place ones... reconciled precisely via the file-by-file
breakdown above).

### Planned GREEN-phase design (not yet implemented)

`toolguard/config.py` ONLY (no other production file needs a functional
change; `hook.py`/`resolve.py` get comment-only touch-ups for terminology):

- Line ~56-59: `_DEFAULT_NO_MATCH_FALLBACK = "ask"`;
  `_VALID_NO_MATCH_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning"})`
  (warn_deny deliberately excluded from this set -- it's normalized as a
  special case, not "valid" going forward).
- `resolved_no_match_fallback()` (~line 1277): after resolving `raw` (top-level
  key, else legacy `[takeover_mode]` alias, else None), special-case
  `if raw == "warn_deny": return "allow_with_warning"` BEFORE the
  valid-set membership check; unrecognized/unset still falls back to
  `_DEFAULT_NO_MATCH_FALLBACK` (now "ask"). Update docstring.
- `resolve_permission_detailed`'s fail-closed branch (~line 1220-1251):
  replace the single `if resolved_no_match_fallback() == "warn_deny"` check
  with a 3-way branch on the (now-normalized) `resolved_no_match_fallback()`
  return value: `"allow_with_warning"` -> allow with the new reason string
  ("...allowed with a warning by no_match_fallback=allow_with_warning (add an
  explicit rule to silence this)"); `"ask"` -> ask with a new reason
  mentioning `no_match_fallback=ask`; else (`"deny"`) -> the existing plain
  deny reason (unchanged, no suffix, so `resolve.py`'s prefix-rewrite for
  file-path tools keeps working unmodified).
- `TakeoverConfig` docstring (~line 664) and `takeover_mode()` docstring
  (~line 880-881): update "'deny' or 'warn_deny'" / "defaults to 'deny'"
  wording -- NO functional change (TakeoverConfig.no_match_fallback stays the
  RAW configured value; normalization happens only in
  `resolved_no_match_fallback()`).
- `hook.py` comments at ~line 401 and ~735 (docstring/comment prose
  mentioning "TOO-15 warn_deny"): reworded to name 'allow_with_warning' as
  canonical with 'warn_deny' noted as the deprecated legacy alias. No
  functional change (hook.py already fully delegates).
- `resolve.py` comment at ~line 419: reworded similarly, no functional change.

No changes planned to `toolguard/tools/takeover_audit.py` or
`toolguard/tools/security_audit.py` (confirmed above: their hardcoded
'deny'-expected invariant and raw `TakeoverConfig.no_match_fallback` usage
already behave correctly with the new default with no code or test changes
needed). No changes to `docs/*.md` or `migrate_permissions` per explicit
instruction.

STATUS: Awaiting explicit approval before starting GREEN phase (hard
checkpoint per strict red-green process instruction).


## GREEN phase: production change done, but 20 UNPLANNED pre-existing test failures found -- STOPPED, awaiting direction

### Production change (complete, exactly as approved)
`toolguard/config.py` only:
- `_DEFAULT_NO_MATCH_FALLBACK = "ask"`; `_VALID_NO_MATCH_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning"})`.
- `resolved_no_match_fallback()`: added `if raw == "warn_deny": return "allow_with_warning"` special case
  (before the valid-set membership check), applied to BOTH the top-level-key raw value and the
  legacy-alias raw value (single code path, so both sources are covered identically). Docstring updated.
- `resolve_permission_detailed()`'s fail-closed tail branch: replaced the single
  `if resolved_no_match_fallback() == "warn_deny"` check with a 3-way branch on
  `fallback = self.resolved_no_match_fallback()`: `"allow_with_warning"` -> allow with reason
  "...allowed with a warning by no_match_fallback=allow_with_warning (add an explicit rule to
  silence this)"; `"ask"` -> ask with reason "...awaiting a decision (no_match_fallback=ask)";
  else (`"deny"`) -> the original unchanged plain-deny reason (no suffix), so `resolve.py`'s
  prefix-based Command->Path reason rewrite for file-path tools needed NO change.
- `TakeoverConfig`/`takeover_mode()` docstrings updated for terminology (no functional change --
  `TakeoverConfig.no_match_fallback` stays the RAW configured value).
- `ruff check toolguard/config.py`: All checks passed.

This alone made ALL 23 originally-approved RED-phase failures pass, with 0 regressions among the
1312+14=1326 tests I had accounted for in RED.

### THE PROBLEM: 20 additional, PRE-EXISTING tests (never touched in RED) now fail

Running the full suite after the config.py change surfaced 20 failures in files I never touched
and never identified during RED-phase planning, because my RED-phase audit searched the test tree
for the literal strings `no_match_fallback`/`warn_deny` -- these 20 tests exercise the exact same
central fail-closed branch (`Configuration.resolve_permission_detailed`'s tail) WITHOUT ever
mentioning either string; they just assert the literal old default value `'deny'` for a
"rules-are-configured-but-nothing-matches" scenario, with no `no_match_fallback` key set anywhere.
This is a real gap in my original RED-phase audit that the coordinator's approval did not (and
could not) cover, since the approval was for the specific 23-test RED state reported.

Full list (20, all `AssertionError`, no new `ERROR`s):
- test_ask_resolution.py: test_blanket_ask_with_no_allow_collapses_to_deny,
  test_blanket_file_ask_collapses_to_deny
- test_hard_deny.py: test_edit_hard_deny_relative_pattern_anchors_to_project_root
- test_hierarchical.py: test_relative_pattern_does_not_match_same_name_outside_project,
  test_no_match_anywhere_is_deny
- test_logging_streams.py: test_default_deny_has_no_provenance
- test_resolve.py (TestNoDrift, a DIFFERENT class than the one I edited in RED):
  test_read_deny_no_drift
- test_takeover_mode.py: test_default_config_when_no_files
- test_tools_decision.py: test_compound_one_denied_yields_deny,
  test_file_path_deny_pattern_blocks_path, test_read_denied_when_no_allow_pattern_matches,
  test_decide_does_not_call_sys_exit, test_no_allow_pattern_yields_deny,
  test_bash_compound_denied_sub_identifiable_in_sub_matches,
  test_file_deny_provenance_is_none_for_failclosed
- test_tools_mining.py: test_denied_without_execution_is_denied,
  test_deny_then_executed_is_allow_candidate
- test_tools_replay.py: test_adding_allow_rule_broadens_decisions,
  test_alembic_landmine_broadening_detected, test_removing_allow_rule_tightens_decisions

### Investigation verdict (read every one, not just grepped): all confirmed SAFE / mechanical, ONE latent pre-existing test bug found

I traced each to its underlying mechanism before proposing anything, specifically hunting for a
genuine hidden security-floor regression:

1. **test_ask_resolution.py's two "blanket ask collapses to deny" tests** looked like they might be
   a SEPARATE, deliberately-hardcoded security floor independent of no_match_fallback (the module
   docstring says "cannot punch through the fail-closed floor"). Traced it to
   `permissions.py:decide_command_at_level_detailed` / `resolve.py` (`non_blanket_ask = [p for p in
   ask_patterns if not is_universal_pattern(p)]`): a blanket `ask=["*"]` with no allow/deny is
   deliberately EXCLUDED from level-matching, so the level returns `None` and the cascade falls
   through to the SAME shared fail-closed tail branch I already modified. CONFIRMED: not a separate
   mechanism -- it was always riding the old hardcoded 'deny' default coincidentally. Now correctly
   resolves via `no_match_fallback` (default 'ask') like every other no-match case. Safe to update
   (mechanical rename + assert 'ask', reword the "collapses to deny" prose to "collapses to the
   no_match_fallback default").
2. **test_tools_mining.py's two tests**: `mining.py::_classify()` ALREADY has first-class handling
   for `current_verdict == "ask"` as `SIGNAL_ASKED` (distinct from `SIGNAL_DENIED`), and already
   treats `current_verdict in ("ask", "deny")` uniformly for the EXECUTED-anyway
   `SIGNAL_ALLOW_CANDIDATE` case. This logic clearly already anticipated 'ask' as a possible verdict
   (from the earlier TOO-15 phase) and needs NO changes. The two failures are pure expected-string
   updates (one test's classification bucket flips from "denied" to "asked"; the other's
   `current_verdict` field flips from "deny" to "ask", classification unchanged).
3. **test_tools_replay.py's three tests**: `replay.py` already implements a full 3-level ordering
   (documented: "tightened: allow->ask, allow->deny, ask->deny"; "broadened: deny->ask, deny->allow,
   ask->allow") -- NOT a binary allow/deny check. The tool's classification logic is unaffected and
   correct; only the literal expected verdict string in each test needs updating.
4. **test_tools_decision.py's test_file_path_deny_pattern_blocks_path**: found a LATENT PRE-EXISTING
   TEST BUG, unmasked (not caused) by this change. It asserts `Read(deny=["[glob]*/.env"])` blocks
   `/home/user/project/.env`, but I confirmed by direct execution that this glob does NOT actually
   match that path (single `*` doesn't span the multiple directory levels) -- the test was passing
   only because BOTH the (non-matching) deny path and the old fail-closed default gave 'deny'
   coincidentally. Now that the default is 'ask', the coincidence is exposed. This test's glob
   pattern needs fixing (e.g. `[glob]**/.env`) to actually exercise what its docstring claims
   ("deny-first within a level"), not just a value-string update -- flagging this explicitly rather
   than silently patching it to 'ask' and leaving the underlying pattern bug in place.
5. All remaining ones (test_hard_deny, test_hierarchical x2, test_logging_streams,
   test_resolve.TestNoDrift, test_takeover_mode, and the other test_tools_decision.py entries) are
   plain instances of the exact category already approved in RED: a rules-exist/no-match scenario
   with no `no_match_fallback` set, asserting the literal old default 'deny'.

### Why I stopped instead of just fixing them

This is a genuine, if benign, gap in my own RED-phase audit -- these are pre-existing tests I never
touched or reported, so editing them now would be outside both (a) the explicit "don't edit tests
in GREEN except to fix your own new test's mistake" instruction, and (b) the specific RED state the
coordinator approved. Recommend: extend the same already-approved pattern to these 20 (rename +
assert 'ask' where it's the new no-match default, preserve 'deny' coverage via an explicit
no_match_fallback='deny' add where a test's core intent is about something else, e.g. hard_deny
anchoring), PLUS fix the one latent glob-pattern bug in test_tools_decision.py separately (flagged,
not silently folded in). Awaiting explicit go-ahead before touching any of these 20 files.

STATUS: config.py production change is complete and correct and left in place (ruff clean).
Suite currently: 1326 tests, 20 failing (all pre-existing, all diagnosed above), 0 errors.


## GREEN phase COMPLETE -- all 1326 tests pass, ruff clean

After the coordinator's second approval (extend the pattern to the 20 pre-existing
failures, per-test judgment, plus fix the latent glob bug), all 20 were resolved and the
full suite is green: `uv run python -m unittest discover -s test -t .` -> `Ran 1326 tests
... OK`. `uv run ruff check .` -> `All checks passed!`. Anti-pattern scan (async/await,
threading, local imports) on every changed .py file: clean. `py_compile` on every changed
.py file: clean.

### Per-test disposition for the two security-sensitive files (as requested)

**test_hard_deny.py** (1 test): `test_edit_hard_deny_relative_pattern_anchors_to_project_root`
-- asserted **'ask'** for the OUTSIDE-project-root path only. Rationale: this test has TWO
assertions -- `inside_decision` (the actual hard_deny MATCH, security-relevant, left
UNCHANGED at 'deny', unoverridable) and `outside_decision` (anchoring-correctness check:
proves the relative pattern does NOT leak outside the project root -- the resulting verdict
is incidental to that point, and the test's own comment already said "with no allow match
either, it is a normal fail-closed deny -- but crucially not via the hard_deny path", i.e.
the security assertion is `assertNotIn("hard_deny", outside_reason)`, unaffected). No
enforcement weakening: the hard_deny mechanism itself is fully untouched by TOO-15.

**test_takeover_mode.py** (1 test): `test_default_config_when_no_files` -- asserted
**'ask'** for `tc.no_match_fallback`. Rationale: this is a broad "what does a from-scratch
config resolve to" snapshot test where `takeover.enabled` is asserted `False` in the SAME
test (takeover is off in this scenario, so no_match_fallback isn't even live
security-wise here) -- it's purely documenting the new default RAW value, not a
fail-closed enforcement assertion.

### All 20 dispositions (ask vs explicit deny), by file

ASSERTED 'ask' (incidental to the test's real focus -- anchoring, cascade mechanics,
structural provenance/sub_matches checks, anti-drift agreement, generic decide() no-match,
mining's ALLOW_CANDIDATE bucket which already treats ask/deny identically):
- test_ask_resolution.py: test_blanket_ask_with_no_allow_collapses_to_no_match_fallback
  (renamed from ..._collapses_to_deny), test_blanket_file_ask_collapses_to_no_match_fallback
  (renamed). Traced to permissions.py/resolve.py: blanket ask='*' is excluded from
  level-matching entirely, so it was ALWAYS riding the same shared fail-closed tail branch
  -- not a separate hardcoded floor.
- test_hard_deny.py: test_edit_hard_deny_relative_pattern_anchors_to_project_root
  (outside_decision only; inside_decision/hard_deny match untouched).
- test_hierarchical.py: test_relative_pattern_does_not_match_same_name_outside_project;
  test_no_match_anywhere_falls_through_to_no_match_fallback (renamed from
  ..._is_deny).
- test_logging_streams.py: test_default_no_match_fallback_has_no_provenance (renamed from
  test_default_deny_has_no_provenance; reason text updated to match the new 'ask' string).
- test_resolve.py (TestNoDrift, a DIFFERENT class than the RED-phase
  TestNoMatchSemanticsNoDrift): test_read_no_match_no_drift (renamed from
  test_read_deny_no_drift).
- test_takeover_mode.py: test_default_config_when_no_files.
- test_tools_decision.py: test_no_allow_pattern_yields_no_match_fallback (renamed),
  test_read_asks_when_no_allow_pattern_matches (renamed), test_decide_does_not_call_sys_exit
  (also fixed a stale docstring -- it claimed "config with deny patterns" but the fixture
  actually has none), test_compound_one_unmatched_yields_ask (renamed;
  compound-strictness propagation verified: any deny->deny else any ask->ask else allow, so
  an unmatched sub-command now correctly propagates 'ask'),
  test_bash_compound_unmatched_sub_identifiable_in_sub_matches (renamed; sub_matches[1]
  .decision now 'ask').
- test_tools_mining.py: test_deny_then_executed_is_allow_candidate (current_verdict field
  only -- 'ask' now; the ALLOW_CANDIDATE classification bucket itself is unaffected since
  mining.py's `_classify()` already treats `current_verdict in ("ask", "deny")` identically
  for the EXECUTED-anyway case).
- test_tools_replay.py: test_removing_allow_rule_tightens_decisions (decision_b.verdict
  'ask'; the 'tightened' classification is unaffected -- replay.py's documented ordering
  already has 'allow -> ask' as tightened).

ADDED EXPLICIT `no_match_fallback='deny'` TO THE FIXTURE (test's real focus requires deny
specifically to make its point):
- test_tools_decision.py: test_file_path_deny_pattern_blocks_path -- NOT actually a
  no_match_fallback case at all; see the separate latent-bug fix below.
- test_tools_mining.py: test_denied_without_execution_is_denied -- specifically exercises
  the SIGNAL_DENIED classification bucket (distinct from SIGNAL_ASKED, which mining.py
  already handles and which has dedicated coverage in
  TestSignalClassification.test_classify_signal_mappings); added
  `no_match_fallback: "deny"` to the layer content so this test keeps testing SIGNAL_DENIED
  specifically rather than losing that coverage to the new default.
- test_tools_replay.py: test_adding_allow_rule_broadens_decisions AND
  test_alembic_landmine_broadening_detected -- BOTH in `TestReplayBroadening`, explicitly
  headed "Tests that broadening permissions is detected -- this is the CRITICAL safety
  check" in the class docstring; the alembic test's own docstring calls itself "the critical
  landmine test". Added `"no_match_fallback": "deny"` to every config in both tests
  (config_a and config_b) so the deny->allow broadening narrative these tests were written
  to demonstrate is preserved EXACTLY as authored, independent of TOO-15's default change.
  (Note: the 'broadened' classification itself would have remained correct either way --
  replay.py's ordering has both 'deny->allow' and 'ask->allow' as broadened -- but given the
  explicit "CRITICAL safety check" framing and detailed prose narrative in these two tests,
  preserving the literal deny->allow scenario was judged the safer, more legible choice.)

### Latent pre-existing test bug fixed separately (not folded into an ask/deny choice)

`test_tools_decision.py::test_file_path_deny_pattern_blocks_path`: the deny pattern
`Read([glob]*/.env)` is RELATIVE (gets anchored to the project root by
`_anchor_file_pattern`); against the bare `_make_config` Configuration (no real project
root), it never actually matched `/home/user/project/.env` -- confirmed by direct
execution before AND after the fix. The test only ever passed because the (non-matching)
deny path and the old fail-closed default both produced 'deny' coincidentally; TOO-15's
default flip to 'ask' exposed the coincidence. Fixed the PATTERN (not the expected value)
to `Read([glob]/home/*/project/.env)` -- an ABSOLUTE glob pattern (starts with '/', so
`_anchor_file_pattern` returns it unchanged, not anchored to any project root), verified by
direct execution to genuinely match and produce a real deny-pattern match. The test still
asserts 'deny' -- unchanged -- but now for the RIGHT reason (an actual deny-pattern match,
per its own docstring "deny-first within a level"), not a coincidental fallback default.

### Final production diff summary

`toolguard/config.py` (the only functional change):
- `_DEFAULT_NO_MATCH_FALLBACK`: `"deny"` -> `"ask"`.
- `_VALID_NO_MATCH_FALLBACKS`: `{"deny", "warn_deny"}` -> `{"ask", "deny",
  "allow_with_warning"}` (warn_deny deliberately excluded -- normalized before reaching
  this set).
- `resolved_no_match_fallback()`: added `if raw == "warn_deny": return
  "allow_with_warning"` (covers BOTH the top-level key and the legacy `[takeover_mode]`
  alias, since both funnel through the same `raw` variable); docstring updated.
- `resolve_permission_detailed()`'s fail-closed tail: replaced the single
  `warn_deny`-specific branch with a 3-way branch on the now-normalized
  `resolved_no_match_fallback()`: `allow_with_warning` -> allow + new reason string;
  `ask` -> ask + new reason string; else `deny` -> unchanged plain reason (so
  `resolve.py`'s Command->Path prefix rewrite needed no change).
- `TakeoverConfig`/`takeover_mode()` docstrings updated for terminology (no functional
  change -- `TakeoverConfig.no_match_fallback` still returns the RAW configured value,
  unnormalized).

`toolguard/permissions.py`, `toolguard/hook.py`, `toolguard/resolve.py`,
`toolguard/tools/takeover_audit.py`: comment/docstring-only terminology touch-ups
(warn_deny -> allow_with_warning as canonical, warn_deny noted as deprecated alias). Zero
functional changes in these four files -- confirmed by the full suite staying green
before and after.

### Final counts
- Tests: 1312 baseline -> 1326 final (+14 net new test methods; several more renamed
  in-place across the 20-test extension, no further count change since renames don't add
  tests).
- `uv run python -m unittest discover -s test -t .`: **Ran 1326 tests ... OK**.
- `uv run ruff check .`: **All checks passed!**
- Anti-pattern scan (async/await, threading, local imports) + `py_compile` on all 17
  changed .py files: clean.
- No git commits made (per instructions); tree left dirty for review.

STATUS: TASK COMPLETE. Awaiting final review.
