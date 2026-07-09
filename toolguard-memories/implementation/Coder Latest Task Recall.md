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
