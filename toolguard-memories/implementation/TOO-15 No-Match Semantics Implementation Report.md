---
title: TOO-15 No-Match Semantics Implementation Report
type: note
permalink: toolguard/implementation/too-15-no-match-semantics-implementation-report
tags:
- TOO-15
- implementation-report
---

## Summary

Implemented the TOO-15 permission-decision semantics change per the approved spec:
governed tools with NO rules configured at all now resolve to `ask` (was `deny`,
which bricked fresh installs); tools WITH rules that simply don't match a given
command/path are governed by `no_match_fallback` (default `deny`, unchanged; `warn_deny`
now actually ALLOWS with a warning reason instead of just rewording a deny).
`no_match_fallback` is now a top-level `toolguard_hook` key, with the legacy
`[takeover_mode].no_match_fallback` honoured as a backwards-compatible alias
(top-level wins when both are set, regardless of relative specificity), and applies
in both takeover and non-takeover modes.

## Decision paths mapped and where centralized

- `toolguard/hook.py` (`main()`) -- live hook entry point.
- `toolguard/tools/decision.py` (`decide()`) -- used by `self_permission.py`,
  `consolidate.py`, `mining.py`, `replay.py`, and audit tooling to evaluate what the
  hook WOULD decide.
- `toolguard/resolve.py` (`resolve_bash_permission_detailed`,
  `resolve_file_path_permission_detailed`) -- the actual shared resolver both
  `hook.py` and `decision.py` delegate to.
- `toolguard/config.py` (`Configuration.resolve_permission_detailed`) -- the single
  per-tool cascade function both resolvers call into; this is where the fail-closed
  default lived and where the new semantics are centralized.

**Key finding:** `decision.py`'s `decide()` is PURE delegation to
`resolve_bash_permission_detailed`/`resolve_file_path_permission_detailed` -- it does
NOT reimplement any "no allow configured" pre-check. That pre-check only existed as
an early-exit optimization duplicated in `hook.py` (lines ~644-660 and ~719-733),
producing a slightly different reason string than the shared resolver's own
fail-closed default would have produced for the same outcome. Removing those two
early-exit blocks and letting `hook.py` always call the real resolvers means
`hook.py` and `decide()` now share ONE code path with zero duplication -- confirmed
by the new anti-drift tests in `test_resolve.py`. **No changes were needed in
`decision.py` itself** (it already had zero special-casing to update).

### Production files changed
1. **`toolguard/config.py`** (+82 lines) -- in `Configuration`:
   - Added `has_any_rules(tool_name) -> bool`: true if ANY allow/deny/ask/hard_deny
     pattern is configured for the tool at any level.
   - Added `resolved_no_match_fallback() -> str`: top-level `no_match_fallback` key
     (most-specific layer that sets it wins), falling back to the legacy
     `takeover_mode().no_match_fallback` alias only when NO layer sets the
     top-level key; defaults to `'deny'`.
   - Modified the fail-closed branch at the end of `resolve_permission_detailed`:
     `not has_any_rules` -> `ResolvedDecision('ask', ...)`; else
     `resolved_no_match_fallback() == 'warn_deny'` -> `ResolvedDecision('allow', ...)`
     with a reason noting the auto-allow; else unchanged
     `ResolvedDecision('deny', "Command does not match any allow patterns", ...)`
     (exact original text preserved for back-compat with existing exact-match tests).
2. **`toolguard/resolve.py`** (+5/-6) -- generalized the file-path "Command"->"Path"
   reason rename in `resolve_file_path_permission_detailed` from an exact-string
   equality check to a `startswith` check (preserving any suffix), so it also covers
   the new warn_deny-allow reason, not just the plain deny reason.
3. **`toolguard/hook.py`** (+28/-48) -- removed both early "if not all_allow: deny"
   short-circuits (file-path and Bash) so `main()` always calls the real resolvers;
   removed the now-redundant takeover-gated warn_deny reason-rewrite block (it only
   reworded a deny and never actually allowed -- the exact bug the ticket described);
   added an `elif decision == "ask":` logging branch (status `"ask"`) alongside the
   existing allow/deny branches for both the file-path and Bash blocks, so `ask`
   verdicts are logged accurately instead of falling into the `"refused"` bucket.
   `TakeoverConfig.no_match_fallback` (the legacy field) is still read for the
   divergence/auto-migration tooling's own dict -- untouched, separate concern.

**Intentionally untouched:** `toolguard/tools/takeover_audit.py` /
`security_audit.py` -- `TakeoverConfig.no_match_fallback` (legacy-only value)
keeps auditing ONLY the `[takeover_mode]` section's own hygiene, a narrower and
separate concern from the new effective/top-level resolution.

## Red state (recap) -> Green result

RED: 1308 tests, `FAILED (failures=8, errors=14)` -- exactly the 22 new/changed
tests from the approved RED-phase plan.

GREEN: 1308 tests, `OK`. `uv run ruff check .` passes clean. `py_compile` passes on
all changed files. No anti-patterns introduced (no async/threading; the one local
import in `hook.py` line 416 is pre-existing/unrelated, not part of this change).

## Self-test-fix during GREEN (flagged per instructions)

One PRE-EXISTING test (not part of my RED-phase set) broke as a genuine, correct
downstream consequence of the approved semantics change, and required updating:

- `test/unit/test_tools_self_permission.py::test_unconfigured_config_flags_both_as_needed`
  -- renamed to `test_unconfigured_config_flags_audit_as_needed`. With
  `Configuration(layers=())` (fully empty), both self-permission probes
  (`toolguard-audit`, `toolguard-maintain`) now resolve to `'ask'` instead of
  `'deny'`. For the mutating `toolguard-maintain` permission, `_status_for()`'s
  existing classification logic treats verdict `'ask'` as `needs_action=False`
  ("Already ask -- no action needed") -- which is actually CORRECT: `ask` is
  exactly the desired per-invocation-consent posture for a mutating tool, so no
  rule needs to be suggested. Only `toolguard-audit` (read-only, needs `'allow'`)
  still needs action. This is a genuine oversight in my RED-phase test-impact
  inventory (I audited `test_tools_decision.py` and `test_hierarchical.py` etc. for
  fully-empty-config assumptions but missed `test_tools_self_permission.py`, whose
  fixture is `Configuration(layers=(), start_dir=None)` passed straight to
  `missing_self_permissions`). I updated the assertions and docstring to match the
  new (correct) behavior rather than reverting the production semantics.

## Edge cases / decisions

- `has_any_rules` counts `[hard_deny]` patterns (either side) as "configured",
  matching the spec's literal list (allow/deny/ask/hard_deny) -- a hard-deny-only
  tool with a non-matching command falls into the fallback branch (deny by
  default), not `ask`.
- Top-level `no_match_fallback` precedence is confirmed-as-intended per the
  coordinator: top-level always wins over the legacy alias regardless of which
  layer/specificity set which -- covered by
  `test_top_level_wins_even_when_set_at_a_less_specific_level`.
- The `'ask'` and `'warn_deny'`-allow reason strings are new; the default-deny
  reason text is byte-for-byte unchanged from before, so no other test needed
  updating for reason-string equality.
