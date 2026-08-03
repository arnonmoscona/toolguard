---
title: TOO-19 deny-side rule fabrication fix
type: note
permalink: toolguard/too-19/too-19-deny-side-rule-fabrication-fix
tags:
- task-memory
- TOO-19
---

## Summary

Fixed the deny-side counterpart of the TOO-19 m5 rule-fabrication bug. `toolguard/hook.py::_log_non_allow_decision` recovered a deny's `Violated Rules` audit-log field via a blind `reason.split(": ", 1)[1]`. When the deny came from the `undecidable_fallback = "deny"` escape hatch (foreign inline/heredoc code, or an undecomposable segment like process substitution) rather than a matched deny rule, the text after that colon is a truncated *display command*, not a rule -- the log recorded a rule ("`python -c`") that exists in no config file.

The `ask` side was audited and found NOT affected: `_log_non_allow_decision`'s `ask` branch never splits the reason -- it logs the full text verbatim as `note`, so there is no extraction step to fabricate a rule from.

## Reproduction (before/after)

Config: `Bash(ls)` + `Bash(python *)` allow only, `undecidable_fallback = "deny"`. Command: `python -c "print(1)"`.

Real reason produced by the resolver (unchanged by this fix -- only the log-extraction logic changed):
```
Denied by undecidable_fallback=deny (inline/heredoc foreign code, unable to safely verify): python -c
```

- **BEFORE** (pre-fix `reason.split(": ", 1)[1]`): `violated_rules = ['python -c']` -- fabricated; no such rule exists.
- **AFTER** (fixed extraction): `violated_rules = ['[fallback deny -- no rule matched]']`

End-to-end confirmation, driving the real `toolguard.hook.main()` over stdin/stdout with `TOOLGUARD_LOG_DIR` and `TOOLGUARD_PROJECT_ROOT` pointed at a temp directory and reading the real markdown log file it wrote:
```
hook stdout: {"hookSpecificOutput": {..., "permissionDecision": "deny", "permissionDecisionReason": "Denied by undecidable_fallback=deny (inline/heredoc foreign code, unable to safely verify): python -c"}}
Violated Rules line: - **Violated Rules**: `[fallback deny -- no rule matched]`
```
Reproduction script: `coder-test/too19_deny_fabrication_repro.py` (not part of the formal suite; kept for reference, writes only under `tempfile.TemporaryDirectory()`, never the real repo `logs/`).

## Root-cause analysis (why this is a SINGLE fix site, unlike the allow side)

The allow-side m5 fix needed TWO fix sites: `compound.py::_combine_strictest`'s multi-leaf "cmd -> pattern" summary builder (which re-parses/reformats leaf reasons) AND `hook.py`'s single-leaf extraction. The deny side only needed ONE: `_combine_strictest`'s deny branch (`compound.py` ~752-756) always forwards the FIRST denied leaf's raw reason **verbatim** -- there is no summary-building/reformatting step for deny (strictest-wins picks one reason, doesn't combine several), so the only fabrication point is the final blind split in `hook.py::_log_non_allow_decision`.

Two deny reason shapes built by `compound.py` for `undecidable_fallback=deny` both end in `": <display command>"` and both carry the marker substring `undecidable_fallback=deny`:
1. `_resolve_leaf_detailed`'s ASK-floor branch: `"Denied by undecidable_fallback=deny (inline/heredoc foreign code, unable to safely verify): {display_cmd}"`
2. `resolve_compound_permission_detailed`'s `UndecidableSegment` branch: `"Undecidable segment denied by undecidable_fallback=deny ({element.reason}): {display}"`

`no_match_fallback=deny`'s reason (`"Command does not match any allow patterns"`, built by `config.py`) has **no colon at all**, so it was never at risk and needed no marker.

File-path tools (Read/Write/Edit) have no `undecidable_fallback` concept (no bash grammar) -- not affected, not in scope.

## Fix (one mechanism, not two)

**`toolguard/compound.py`**: generalized the EXISTING allow-side mechanism rather than adding a parallel one.
- Added `FALLBACK_DENY_PLACEHOLDER = "[fallback deny -- no rule matched]"`, the deny counterpart of `FALLBACK_ALLOW_PLACEHOLDER`.
- Extended `_FALLBACK_REASON_MARKERS` with a 3rd tuple element (the decision each marker is valid evidence for) and a new entry `("undecidable_fallback=deny", "denied", "deny")`.
- Broadened `fallback_kind_for_reason`'s decision gate from `!= "allow"` to `not in ("allow", "deny")`, and gated the marker loop on `applies_to == decision` -- so folding deny into the same function/table cannot let an allow marker misclassify a deny or vice versa, even in a hypothetical substring collision (defense in depth beyond "the marker text just happens to be decision-specific").

**Chose ONE function over a parallel `fallback_kind_for_deny_reason`** because the marker table, the longest-marker-first ordering concern, and the "classify this reason string" contract are identical between the two decisions -- a second function checking a second marker tuple is exactly the drift risk that made `fallback_kind_for_reason` public in the first place (per its own docstring rationale). The per-decision `applies_to` tag is what makes this safe rather than just convenient.

**`toolguard/hook.py`**:
- Imported `FALLBACK_DENY_PLACEHOLDER`.
- Extracted the shared extraction logic (previously inline in `_matched_rule_for_single_command`) into a new private helper `_reason_suffix_or_placeholder(decision, reason, placeholder)`, used by BOTH `_matched_rule_for_single_command` (allow, unchanged behavior, now a thin wrapper) and the new deny-side extraction in `_log_non_allow_decision` -- one extraction mechanism at the hook.py layer too, not two copies of the same split-guard logic.
- `_log_non_allow_decision`'s deny branch now calls the helper and falls back to the FULL reason (not `None`) when there is no `": "` at all, preserving pre-fix behavior for reasons like `"No commands to evaluate"`.

## Ask-side check

Confirmed unaffected and pinned with a test (`test_ask_side_is_unaffected_full_reason_is_always_the_note`): `_log_non_allow_decision`'s `ask` branch passes `note=reason` with the full, unsplit text; `log_command` is never given `violated_rules` for `ask` at all. No fix needed there.

## Tests added (`test/unit/test_resolve.py`, new class `TestAuditLogViolatedRuleNeverFabricated`, 6 tests -- no existing test modified)

1. `test_single_leaf_undecidable_deny_logs_the_placeholder_not_a_command` -- the ticket's exact repro shape, single-leaf ASK-floor deny.
2. `test_compound_leaf_undecidable_deny_logs_the_same_placeholder` -- same escape hatch as one leaf of a two-leaf compound (`ls && python -c "print(1)"`).
3. `test_undecidable_segment_deny_logs_the_placeholder_not_the_command` -- the OTHER deny reason shape, via a process-substitution command (`diff <(sort a) <(sort b)`), confirming both shapes are covered by the one marker.
4. `test_a_genuine_deny_still_records_its_real_pattern` -- regression guard: a real `Bash(rm -rf *)` deny match still logs its real pattern text (fix cannot degrade into "never record anything").
5. `test_no_match_fallback_deny_has_no_colon_and_is_unaffected` -- the *other* fallback that can produce a deny; uses the file-path resolver specifically because `resolve_bash_permission_detailed` wraps even a lone command in "Compound command contains denied sub-command: ..." (re-introducing a colon from real data), so the truly unwrapped, colon-free `config.py` reason is only reachable through the file-path path, which has no such wrapping.
6. `test_ask_side_is_unaffected_full_reason_is_always_the_note` -- pins the "ask never splits" finding above.

All 6 pass individually and as part of the full suite.

## Verification results

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- baseline (before this session's changes) **2169 tests, OK**; after this fix + new tests, **2175 tests, OK** (up by exactly the 6 new tests, as required).
- `uv run ruff check .` -- clean repo-wide (one `F401` in my own scratch repro script, fixed).
- `uv run ruff format --check .` -- clean repo-wide (repro script reformatted).
- `uv run python tools/check_doc_links.py` -- exits 0, "All internal documentation links resolve."
- Real repo `logs/` untouched: file count bracketed at **59 before / 59 after** the final full suite run; confirmed no leaked `Violated Rules` line or fabricated-command text was ever written there by the repro script (which explicitly isolates `TOOLGUARD_LOG_DIR`/`TOOLGUARD_PROJECT_ROOT`/`HOME`/`XDG_CONFIG_HOME` to a `tempfile.TemporaryDirectory()`) or by the test suite.

## Important context: working tree already carried uncommitted allow-side (m5) work

Before this session started, `toolguard/compound.py` and the `TestAuditLogMatchedRuleNeverFabricated` class in `test/unit/test_resolve.py` already existed in the *working tree*, uncommitted -- this is the "allow-side equivalent... fixed earlier today" the ticket refers to. The `git status` snapshot embedded in my launch context was stale (taken before that earlier work landed on disk) and did not list `compound.py`/`test_resolve.py` as modified; the live files on disk already had it when I read them. `git diff HEAD` therefore shows a combined diff of that earlier uncommitted work plus my additions. My own additions are precisely: in `compound.py`, the `FALLBACK_DENY_PLACEHOLDER` constant, the `applies_to`-tagged marker table, and the broadened `fallback_kind_for_reason` gate; in `hook.py`, the `_reason_suffix_or_placeholder` helper and the `_log_non_allow_decision` deny-branch rewrite; in `test_resolve.py`, the `FALLBACK_DENY_PLACEHOLDER`/`_log_non_allow_decision` imports and the entire `TestAuditLogViolatedRuleNeverFabricated` class (test/unit/test_resolve.py lines ~1349-1573). Nothing else in either file was touched by me. No commits were made (not asked to).

## Files touched this session

- `toolguard/compound.py` (edited, on top of pre-existing uncommitted allow-side work)
- `toolguard/hook.py` (edited, on top of pre-existing uncommitted allow-side work)
- `test/unit/test_resolve.py` (edited -- new tests only, nothing existing modified)
- `coder-test/too19_deny_fabrication_repro.py` (new, scratch reproduction script, not part of the formal suite)

## Self-review notes

- No `async`/`await`, no `threading`, no function-level imports introduced.
- Docstrings updated on every touched function/class, including doc-drift sweep on the shared `fallback_kind_for_reason` docstring and the module-level marker-table comment (both now describe both decisions).
- Did not widen `resolve_one`'s 3-tuple contract, per the ticket's explicit constraint.
- Did not touch `test/unit/test_compound.py` or any other existing test file.
- Elapsed time this session: roughly 25-30 minutes wall clock (reading conventions/source ~10 min, implementation ~8 min, tests + repro + verification ~10-12 min), based on real-log timestamps bracketing the session (21:1x-21:34 local). Estimated cost: well under $1 (Sonnet 5, a few hundred KB of file reads/greps plus a handful of short edits and test runs -- no large generations).
