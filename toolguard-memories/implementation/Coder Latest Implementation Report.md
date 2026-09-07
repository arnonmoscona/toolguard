---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-28
- implementation-report
---

# TOO-28 Phase 2 -- two independent auto-mode fallbacks -- implementation report

Brief: `toolguard-memories/TOO-28/brief-phase2.md` (validated, 5/5 slots).

## Summary

Added `no_match_fallback_in_auto_mode` and `undecidable_fallback_in_auto_mode`, two
independently configurable top-level `toolguard_hook` keys that resolve in place of
`no_match_fallback`/`undecidable_fallback` when Claude Code's own `permission_mode` is its
auto mode. Unset means "defer to the base setting" (not a fixed literal), so the feature is
inert until explicitly configured -- proven by corpus equivalence with the new keys unset.
Ships together with the already-verified `fallback_kind` -> `fallback_outcome` rename that was
carried in uncommitted from the prior round.

## Files touched (this phase; the rename's own 9 files are untouched and carried forward)

**Source (7):**
- `toolguard/config_types.py` -- `AUTO_PERMISSION_MODE` constant (config layer, so both the
  engine and runtime can import it); `permission_mode: Optional[str]` added to
  `ResolutionContext`; `resolved_no_match_fallback_in_auto_mode`/
  `resolved_undecidable_fallback_in_auto_mode` added to `ResolutionConfig`/`ResolveConfig`;
  `UnrecognizedFallbackSetting` gained a `falls_back_to: str = "'ask'"` field so its message
  can name a non-'ask' fallback for the new keys.
- `toolguard/config.py` -- the two new `Configuration` resolver methods (each one call to the
  existing `_resolve_fallback_setting`, `default` set to the dynamically-computed base value);
  `unrecognized_fallback_settings()` extended to scan the two new keys too, with a
  `falls_back_to_by_key` map naming the actual base value in each warning.
- `toolguard/permission_resolution.py` -- `_effective_no_match_fallback(context)` helper,
  shared by `resolve_command_permission`/`resolve_file_path_permission`, branching on
  `context.permission_mode == AUTO_PERMISSION_MODE`.
- `toolguard/resolve.py` -- the same branch, inline, for `undecidable_fallback` in
  `resolve_bash_permission_detailed` (computed once before the per-unit loop, not per-unit).
- `toolguard/hook.py` -- `AUTO_PERMISSION_MODE` now imported from `config_types` instead of
  defined locally (one definition, not two that can drift); the comment above
  `permission_mode = hook_data.permission_mode` corrected (it used to say "recorded for
  diagnosis, it never affects the verdict" -- now false, and rewritten).
- `toolguard/session_start.py` -- the unrecognized-fallback session-start banner no longer
  asserts a blanket "falls back to 'ask'"; it renders each entry's own `falls_back_to`.
- `toolguard/tools/takeover_audit.py` -- two new findings, `loose-no-match-fallback-in-auto-mode`
  (LOW) and `loose-undecidable-fallback-in-auto-mode` (HIGH), firing only when the auto-mode
  value is both configured (differs from the deferred-to base) and loose -- so an unset auto
  key never duplicates the existing base-setting finding.

**Tests (4, all new test classes/methods; no existing test modified):**
- `test/unit/test_configuration.py` -- `TestResolvedFallbacksInAutoMode` (8 tests: unset
  defers to base, explicit overrides, unrecognized defers to base not 'ask', alias
  normalization, independence) and `TestUnrecognizedFallbackSettingsAutoMode` (2 tests, incl.
  a control proving the base keys' own `falls_back_to` is unchanged).
- `test/unit/test_permission_resolution.py` -- `TestAskFloorInvariantAcrossFallbackValues`
  (the step-6 enumerating invariant, over the no_match_fallback value domain) and
  `TestNoMatchFallbackAutoMode` (4 tests: mode-gating, unset-is-inert, broken-config-still-asks,
  cross-setting independence).
- `test/unit/test_resolve.py` -- `TestUndecidableFallbackThreading` gained one enumerating
  invariant test; new `TestUndecidableFallbackAutoMode` (3 tests, mirroring the no-match side).
- `test/unit/test_tools_takeover_audit.py` -- `_toolguard_layer` widened via
  `**top_level_fallback_keys` (PLR0913 forced this over two more named params); new
  `TestLooseFallbackInAutoMode` (5 tests).

New test count: 4067 (was 4043; +24).

**Docs (4):**
- `docs/configuration.md` -- new "Fallback settings in auto mode" section (framed as handoff
  points, per spec section 2, not "auto-mode variants"); the two keys added (commented, since
  their real default is absence) to the Configuration reference TOML block; Contents ToC entry.
- `docs/auto-mode.md` -- the recommended configuration now prefers
  `no_match_fallback_in_auto_mode` over loosening the base setting globally; the stale
  "diagnostic only today -- it does not change enforcement" claim about `permission_mode`
  corrected; checklist items 3/5 rewritten (nothing to remember to tighten back up).
- `docs/security.md` -- one paragraph added to "Loosening the undecidable fallback" noting the
  auto-mode counterpart carries the identical risk/mitigation story.
- `docs/agent-map.md` -- the stale Q&A about the old recommendation corrected; one new Q&A;
  one new ToC anchor for `configuration.md`'s new section.

## Judgements made, not fully dictated by the brief

1. **`AUTO_PERMISSION_MODE` moved to `config_types.py`, not left in `hook.py`.** The engine
   layer (`permission_resolution.py`/`resolve.py`) cannot import the runtime layer
   (`hook.py`) per `.pyscn.toml`; `config_types.py` is already imported by both. `hook.py`'s
   own local definition (used by the Phase 5 trace gate) now imports the same constant --
   one definition, not two that could silently drift apart (CLAUDE.md's "literal strings with
   semantic meaning belong in constants" rule, applied across module boundaries too).
2. **Design for "unset vs unrecognized"**: rather than changing `_resolve_fallback_setting`'s
   body (confirmed unnecessary), each new resolver method passes the BASE setting's own
   resolved value as `_resolve_fallback_setting`'s `default` parameter, computed dynamically
   per call. Unset and unrecognized therefore both defer to the base value -- the same "safe
   direction, not the risky one" property the base settings already have (deferring is never
   the parse-failure-floor-relaxing direction), just with a different concrete fallback target.
3. **`unrecognized_fallback_settings()` extended, not left alone.** The base settings' typo
   diagnostic already existed and disambiguates "unset" from "set to garbage" (that
   distinction is answered there, not inside the resolver -- see Finding 2 below). Extending it
   to the two new keys, with a corrected non-hardcoded `falls_back_to` message, was the
   consistent choice; leaving the new keys undiagnosed would have been a silent regression in
   diagnostic coverage relative to the base settings.
4. **`takeover_audit.py`'s two new findings fire only when the auto value both differs from
   AND is looser than the base value** -- not on every configured auto-mode value. Firing
   unconditionally would duplicate the base finding whenever the auto value merely equals an
   already-loose base value (the common, boring case); this design surfaces exactly the new
   information the base findings cannot see (a strict base with a loose auto override) without
   adding noise to every audit run that touches either setting.
5. **Genuine RED/GREEN demonstrated by temporary revert, not literal step-ordering.**
   Implementation and tests were written together rather than test-first; RED was then proven
   honestly by temporarily reverting the two mode-selection branches (in `resolve.py` and
   `permission_resolution.py`) and confirming the relevant new tests fail, then restoring and
   re-confirming green -- pasted in the session transcript. The Configuration-level and
   takeover_audit-level tests (simple new-method wiring, not branch logic) were not put through
   this cycle; they passed on first run, which is expected for straightforward new-method tests
   with no prior behaviour to regress against.
6. **Markdown line-wrapping**: `docs/configuration.md` and `docs/auto-mode.md` are, in their
   pre-existing entirety, hard-wrapped at ~90-100 columns throughout (a long-standing local
   convention, not something I introduced). CLAUDE.md's "never hard-wrap a paragraph" rule is
   stated as unconditional, so my own new/modified paragraphs in both files (and in
   `docs/security.md`) were written as single lines regardless of the surrounding file's
   convention -- flagged here since it makes my additions visually inconsistent with 100% of
   the surrounding prose, which was a deliberate choice to follow the stated rule rather than
   local style, not an oversight.

## Verification performed

- Baseline (before any change): `Ran 4043 tests` / `OK (expected failures=4)`; `ruff check .`
  -> `All checks passed!`.
- Final: `Ran 4067 tests` / `OK (expected failures=4)`; `ruff check .` -> `All checks passed!`;
  `ruff format --check .` -> `199 files already formatted`.
- RED evidence (pasted in transcript): reverting `resolve.py`'s undecidable mode-branch to the
  base-only call made `TestUndecidableFallbackAutoMode.test_auto_mode_setting_applies_only_under_auto_permission_mode`
  fail (`'ask' != 'allow'`); reverting `permission_resolution.py`'s
  `_effective_no_match_fallback` similarly made 2 of
  `TestNoMatchFallbackAutoMode`'s 4 tests fail. Both reverts undone immediately after.
- Architecture fitness: `--stdlib` PASS, `--ambient` PASS (82 files, 8 os imports, 40 Path
  ambient-member reads, all owned), `--layers` PASS (81 modules, completeness and direction
  both clean).
- Entry-point smoke test: all 8 console-script modules
  (`toolguard.hook`, `.session_start`, `.update_check`, `.tools.security_audit`,
  `.tools.maintenance`, `.tools.installer`, `.scripts.migrate_permissions`,
  `.tools.update_skills`) imported cleanly.
- Corpus equivalence (new settings UNSET, proving inertness): `OK: no differences` at
  `6401`/`61`, both before and after the calibration probe.
- Calibration: planted `_DEFAULT_NO_MATCH_FALLBACK = "allow"  # TOO-28 PHASE 2 CALIBRATION
  PROBE` in `config.py`; `--verify` FAILED (pasted diff); reverted; `--verify` passed again;
  `git status --porcelain -- toolguard/config.py` showed only the legitimate Phase 2 diff (91
  insertions / 22 deletions), no trace of the probe (`grep -n "CALIBRATION PROBE"` -> no match).
- Live end-to-end (real `toolguard.hook:main`, piped synthetic `PreToolUse` JSON, scratch
  project config, cleaned up after): under a config with `no_match_fallback = "deny"` and
  `no_match_fallback_in_auto_mode = "allow"`, an unmatched command resolved `"allow"` under
  `permission_mode: "auto"` and `"deny"` under `permission_mode: "default"` -- both pasted in
  the transcript. Repeated for `undecidable_fallback`/`undecidable_fallback_in_auto_mode`
  against a foreign-inline-code command (`python3 -c "import os"`): `"allow"` under auto,
  `"deny"` under default -- also pasted. Confirms `permission_mode` genuinely arrives from the
  wire payload and reaches the resolver, not just from a mode handed to it directly in a test.
- `takeover_audit.py`'s two new findings demonstrated directly (not only via unit test) against
  a hand-built `Configuration`: both fired with the exact rendered description/remediation text
  pasted in the transcript.
- Sibling sweep: grepped every production call site of
  `resolved_no_match_fallback()`/`resolved_undecidable_fallback()` in `toolguard/`; every
  non-internal call site (`permission_resolution.py`, `resolve.py`, `takeover_audit.py`) is
  accounted for above; internal call sites (inside the new `_in_auto_mode` methods themselves,
  and inside the new diagnostic's `falls_back_to` text) are intentional. Checked
  `toolguard/testing/sandbox.py` and `tools/corpus_build.py`: neither constructs a mode-aware
  `Invocation` today (sandbox explicitly passes `permission_mode=None`), which is correct,
  existing, out-of-scope behaviour, not a gap this phase needs to close.

## Findings against the brief's own flagged uncertainties

- **"That `_resolve_fallback_setting` handles the new keys with no changes"** -- CONFIRMED,
  zero changes to its body; achieved by passing the dynamically-computed base value as its
  existing `default` parameter.
- **"That 'unset means use the base setting' is cleanly expressible... may or may not
  distinguish unset from unrecognized"** -- the resolver itself does NOT distinguish them (by
  design, matching the base settings' own behaviour), but a separate diagnostic
  (`unrecognized_fallback_settings`) already exists for exactly this purpose for the base
  settings and has been extended to the new ones with a corrected message. This is not a gap;
  see judgement 2/3 above.
- **"That adding permission_mode to ResolutionContext is behaviour-neutral by itself"** --
  CONFIRMED: `Invocation`'s existing `permission_mode: Optional[str] = None` default satisfies
  the widened Protocol unchanged; full suite green at each step with no test-construction
  breakage anywhere (many hand-built test doubles pass a bare `Invocation` and never set this
  field explicitly).
- **"That takeover_audit only needs a non-auto reading"** -- addressed by adding two NEW
  findings alongside the existing non-auto ones, rather than changing what the existing two
  report; the existing two remain a faithful non-auto reading, and the audit doc/module
  docstring now says explicitly that it reports what the setting WOULD resolve to, not a live
  read.
- **"That the two settings are genuinely independent in the code"** -- CONFIRMED by test
  (`test_no_match_and_undecidable_auto_mode_settings_are_independent` in both
  `test_permission_resolution.py` and `test_configuration.py`) and by construction: they are
  resolved by two entirely separate call sites (`permission_resolution.py`'s helper for
  no-match; `resolve.py`'s inline branch for undecidable), sharing no code path.

## Self-review notes

- No async/await, no threading, no local imports introduced.
- All new/changed docstrings state what the setting/method IS, not what this ticket changed.
- No existing test was modified or deleted; all additions are new test classes/methods, or (in
  `test_tools_takeover_audit.py`) a widened helper signature that is additive for existing
  callers (new params/kwarg, all optional, defaulting to prior behaviour).
- `test/verdict_corpus/` untouched this phase (only read via `--verify`).
- No git write operations performed.

## Non-blocking findings for the next round

- `technical-notes.md` documents the `no_match_fallback`/`undecidable_fallback` asymmetry in
  depth but was not updated with the two new settings -- in scope only if a future phase wants
  the deep rationale recorded there too; the brief's docs scope was `docs/` specifically.
- `toolguard/testing/sandbox.py` has no CLI flag to simulate `permission_mode` for interactive
  testing of the new settings -- a reasonable usability follow-up, explicitly out of this
  phase's scope (the brief says "reading permission_mode for anything other than these two
  settings" is out of scope, and this would be a sandbox feature, not a resolver change).
  Judgement 5 above.
- A basic-memory tooling quirk (documented in an earlier round's report too): two physical
  files in `toolguard-memories/implementation/` were bound to the same permalink
  (`toolguard/implementation/coder-latest-task-recall`) -- `Coder Latest Task Recall.md`
  (untouched, committed) and a second one this session renamed to
  `coder-latest-task-recall-stale-too28-phase2-precursor.md` (git sees this as a delete of the
  old committed filename plus an add of the new one, though no content was lost -- verified via
  `git show` against the prior commit). Not resolved; flagged for Arnon to consolidate, since
  guessing which of the two is authoritative risks destroying the wrong one.
- `/documentation-review` (the project's own pre-push doc-drift check) was not run this phase;
  I made a manual, more limited pass (fixing the one stale claim I found in `agent-map.md` and
  cross-linking the new section) rather than the full skill invocation, since this is a
  mid-ticket phase, not the pre-push point CLAUDE.md's checklist targets.
- Before push, still pending per the project's own checklist: version bump in
  `pyproject.toml`, release notes, `pyscn analyze`, coverage, and the `<TEMPORARY>` fence
  keep/drop decision in `.claude/toolguard_hook.toml` -- none of these were in this phase's
  brief and none were touched.


## Correction round: section 8 invariant, per coordinator review

**Finding accepted as correct.** The original two tests (`test_broken_config_still_asks_despite_allow_no_match_fallback_in_auto_mode` / `..._undecidable_fallback_in_auto_mode`) enumerated *values* for two *named* settings, not settings themselves -- a third fallback-shaped setting added later would pass both untouched. Fixed as directed:

1. **Hoisted the registry.** `Configuration.unrecognized_fallback_settings`'s local `valid_by_key`/`alias_by_key` dicts (plus the ad hoc `falls_back_to_by_key`) are replaced by a module-level `_FallbackSetting` dataclass and a `_FALLBACK_SETTINGS` tuple in `config.py` (four entries: `key`, `valid_values`, `alias_map`, `resolver_method`, `defers_to`, `kind`, `auto_only`). `unrecognized_fallback_settings` now iterates this registry; its `falls_back_to` text is computed generically from `defers_to`/`resolver_method` rather than a hand-listed per-key string. Verified behaviour-identical: `test_configuration`/`test_tools_takeover_audit`/`test_session_start` (305 tests covering this path) all green unchanged.
2. **New registry-driven test**: `test_permission_resolution.TestParseFailureFloorHoldsForEveryRegisteredFallbackSetting`. Iterates `_FALLBACK_SETTINGS`, and for each setting, each of its valid values, and every `permission_mode` where that setting's value is actually consulted (both modes for a base setting; only `'auto'` for an `auto_only` one -- testing an auto-only setting under the mode where it's never read asserts nothing about it), drives the real command through `resolve_bash_permission_detailed` under a recorded parse failure and asserts the decision floors to `'ask'` (or stays `'deny'`, the already-deny exemption). One test, 24 subTest combinations, zero settings named by string.
3. **Genuine RED, twice**, both reverted immediately after:
   - Disabling only `_apply_ask_floor` (the per-sub-command floor) left the test GREEN -- the compound-level second floor at `resolve.py:400` (shared `apply_parse_failure_floor`) covers it independently, confirming the documented "double floor, defense in depth" property empirically rather than assuming it.
   - Disabling the shared `apply_parse_failure_floor` function itself (used by both call sites) failed **12 of 24** subTests -- every non-`'deny'` value, across all four registered settings. Restored; suite green again.
4. **Deleted, as subsumed** (all four were tests I added earlier in this same phase, not pre-existing baseline tests):
   - `test_permission_resolution.TestAskFloorInvariantAcrossFallbackValues` (whole class, one method) -- covered `no_match_fallback` only, default mode only.
   - `test_permission_resolution.TestNoMatchFallbackAutoMode.test_broken_config_still_asks_despite_allow_no_match_fallback_in_auto_mode` -- one value (`'allow'`), one setting.
   - `test_resolve.TestUndecidableFallbackThreading.test_ask_floor_holds_across_every_undecidable_fallback_value` -- covered `undecidable_fallback` only, default mode only.
   - `test_resolve.TestUndecidableFallbackAutoMode.test_broken_config_still_asks_despite_allow_undecidable_fallback_in_auto_mode` -- one value (`'allow'`), one setting.
   Each is a strict subset of what the registry test now asserts (same command shapes, same floor assertion, superset of values/modes/settings); a one-line pointer comment was left at each deletion site naming the replacement. Nothing else in those classes (mode-gating, unset-inertness, cross-setting independence) was touched.
5. **Two bugs found and fixed while building the replacement test**, both in the test itself, not production code:
   - Passing `"permissions": {...}` through `_layer(..., **content)` silently discarded the intended allow rules, since `_layer` always rebuilds `content["permissions"]` from its own `allow=`/`deny=` parameters (defaulting to empty) regardless of anything smuggled in via `**settings`. Fixed by passing `allow=[...]` as a real keyword argument.
   - My first draft asserted every setting's value under *both* modes uniformly, which is wrong for an `auto_only` setting under the mode where it is never consulted -- the assertion was really testing the (unset) base setting's default, not the setting under test. Fixed by restricting the mode loop per `setting.auto_only`.

Full suite: `Ran 4064 tests` / `OK (expected failures=4)` (4067 -> 4064: -4 deleted methods, +1 new method with 24 subTests). `ruff check`/`format --check` clean. All three architecture-fitness checks pass. Corpus `OK: no differences` at 6401/61, re-calibrated against the registry itself (planted `_DEFAULT_NO_MATCH_FALLBACK = "allow"`, confirmed `--verify` FAILS, reverted, confirmed passes, `git diff --stat` shows only the legitimate registry-refactor diff). All 8 entry points import cleanly.


## Correction round: brittle setting-name literals, per Arnon's review

**Accepted.** Each new setting name was typed four times in code, plus `resolver_method`
(a method name as a string) and `defers_to` (a raw cross-reference to another entry's
`key=`). Fixed:

1. **Four module-level constants in `config.py`**, public by design (the module docstring's
   "everything else is underscore-prefixed" note updated to say why these are the exception):
   `NO_MATCH_FALLBACK_KEY`, `UNDECIDABLE_FALLBACK_KEY`, `NO_MATCH_FALLBACK_IN_AUTO_MODE_KEY`,
   `UNDECIDABLE_FALLBACK_IN_AUTO_MODE_KEY` -- the base pair included, per instruction. Used
   for `_FALLBACK_SETTINGS`' `key=`/`defers_to=`, at all four `_resolve_fallback_setting(...)`
   call sites (the two new methods AND the two original ones), and in the legacy
   `[takeover_mode].no_match_fallback` alias lookup inside `takeover_mode()` (pre-existing
   code, touched because it's the same literal and the fix was one line).
2. **`resolver_method: str` removed entirely**, not just tested-around. `_FallbackSetting`
   now carries `resolver: Callable[["Configuration"], str]`, bound directly to
   `Configuration.resolved_no_match_fallback` etc. -- a plain function reference, not a name.
   This forced moving `_FALLBACK_SETTINGS`'/`_FALLBACK_SETTINGS_BY_KEY`'s construction from
   before the `Configuration` class to immediately after it (the class must exist for its
   methods to be referenced as values); the dataclass shape and the four key constants stay
   near the top with their sibling constants, since method bodies resolve module-level names
   at call time regardless of file order. A typo'd/renamed resolver method now fails at
   **import time** (`AttributeError` building the registry) rather than silently at a call
   site -- confirmed by import smoke test.
3. **`takeover_audit.py` imports and interpolates the four constants** in every place a
   setting name appeared in finding/impact/remediation text -- 8 embedded occurrences across
   the two new findings, more than the coordinator's representative one-per-field citation
   (their table cited one description + one remediation occurrence per finding; each finding's
   text actually names the setting 2-3 times, in description, impact, AND remediation, and I
   fixed all of them). Byte-for-byte message output confirmed unchanged by re-running the same
   hand-built-`Configuration` demonstration from the prior round and diffing by eye against
   the earlier transcript -- identical.
4. **Sweep findings, reported as instructed:**
   - **The instances I found beyond the coordinator's table, both TOO-28-introduced**: the
     embedded BASE-setting-name references inside my own new invariant 6/7 text (impact text
     saying "...no_match_fallback reading above", remediation saying "...defer to
     no_match_fallback"/"...defer to undecidable_fallback") -- these reference the *base*
     setting's name, not the auto one the coordinator's table centered on, and there are
     multiple per finding. All now use the constants.
   - **Found, left alone (pre-existing, not TOO-28-introduced, matching the project's own
     decision-value carve-out logic)**: `config.py`'s `_unexpected_key_issues`-style message at
     the rules-directory validator (`"...governed_tools, no_match_fallback, [takeover_mode]..."`,
     illustrative prose, not TOO-28's), `hook.py:855` and `tools/security_audit.py:774`
     (both build a legacy plain-dict/JSON-output view of `TakeoverConfig.no_match_fallback`,
     predating this ticket), and `takeover_audit.py`'s pre-existing invariant 4/5 message text
     (I only read the variables those invariants already compute; I did not touch their own
     wording). None of these are TOO-28's own additions, so none were changed, consistent with
     the explicit "leave the pre-existing ~60 decision-value comparisons alone" carve-out
     extended to the same reasoning for pre-existing setting-name literals.
   - **Deliberately NOT constant-ified**: test-file fixture data and test-assertion literals
     (e.g. `assertEqual(found[0].key, "no_match_fallback_in_auto_mode")`,
     `_toolguard_layer(no_match_fallback_in_auto_mode=...)`) -- these are input/expected-value
     literals in the existing project convention (hundreds of pre-existing
     `assertEqual(..., "ask")`-style test assertions follow the same pattern), not
     "a conditional, comparison, or dispatch" in shipped production code.

Verification: suite `Ran 4064 tests` / `OK (expected failures=4)` (unchanged, no tests
added, per the constraint); `ruff check`/`format --check` clean; all three architecture-fitness
checks pass; all 8 entry points import cleanly; corpus `OK: no differences` at 6401/61,
calibrated twice more this round -- once via the pre-existing `_DEFAULT_NO_MATCH_FALLBACK`
probe (confirmed sensitive to `config.py` generally) and once by deliberately mistyping
`NO_MATCH_FALLBACK_KEY` itself (confirmed `--verify` FAILS on this repo's own
`no_match_fallback = "allow_with_no_warnings"` setting silently stopping being read, reverted,
confirmed passes again, `git status --porcelain` clean of any probe residue).


## New task: decision-value literals -> constants (allow/deny/ask sweep)

Arnon overruled the earlier deferral: pre-existing `== "allow"`/`"deny"`/`"ask"` comparisons
are now in scope, project-wide, not just TOO-28-introduced ones.

**Re-measured myself** (instructed to, since the coordinator's own scans had been wrong
twice): grepped every production `.py` file for the three vocabularies, then read each hit's
context individually to classify decision vs. collision -- see below.

### Constants added, `toolguard/constants.py`

```python
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_ASK = "ask"
FALLBACK_ALLOW_WITH_WARNING = "allow_with_warning"
FALLBACK_ALLOW_WITH_NO_WARNINGS = "allow_with_no_warnings"
FALLBACK_OUTCOME_WARNED = "warned"
FALLBACK_OUTCOME_SILENT = "silent"
FALLBACK_OUTCOME_DENIED = "denied"
```

`DECISION_*` used for both the decision vocabulary and the fallback-setting values that
share the exact spelling (a fallback setting resolving to `'ask'` literally means the
resolver returns the decision `'ask'`) -- `FALLBACK_ALLOW_WITH_WARNING`/`_NO_WARNINGS` cover
the two fallback-setting-only spellings that have no decision equivalent, per the brief's
own split. `STATUS_*` untouched.

### Files converted (16, this round)

`compound.py`, `permission_resolution.py`, `resolve.py`, `hook.py`, `file_matching.py`,
`permissions.py`, `config.py` (including its own `_DEFAULT_NO_MATCH_FALLBACK`/
`_VALID_*_FALLBACKS`/`_ALLOW_NO_WARNINGS_ALIAS`/`_ACCEPTED_FALLBACK_SPELLINGS` constants, and
the `"warn_deny"` alias-map value), `tools/self_permission.py`, `tools/mining.py`,
`tools/replay.py`, `tools/uninstall_readiness.py`, `tools/consolidate.py`,
`tools/takeover_audit.py` (including its PRE-EXISTING invariant 4/5 wording this time --
that carve-out was specific to the prior round's setting-*name* work, not this round's
decision-*value* scope, which the coordinator explicitly widened), `tools/installer.py`
(the `--no-match-fallback` argparse `choices=`/`default=`). `test/unit/test_architecture.py`
updated (three exact per-module import allow-lists -- `permissions`, `file_matching`,
`permission_resolution` -- each gained `"toolguard.constants"`, matching the new import each
module needed; module docstrings updated to match).

Two catches from my own re-measurement, not in the coordinator's list:
1. `permissions.py`'s `check_permission`/`resolve_allow_ask` return bare
   `("allow"|"deny"|"ask", reason)` tuples -- missed by a `decision="..."`-shaped grep, since
   these are bare returns, not keyword construction.
2. `tools/installer.py`'s `--no-match-fallback` CLI flag: `choices=(...)` and `default=` were
   a second, literal copy of `_VALID_NO_MATCH_FALLBACKS`' value set, outside `config.py`
   entirely.

### Deliberately NOT converted -- vocabulary collisions (same spelling, different meaning)

- **`list_type`** (`self_permission.py`, `danger.py`, `consolidate.py`, `uninstall_readiness.py`,
  `rule_apply.py`, `hierarchy.py`, `installer.py`'s candidate tuples): "which permissions
  LIST a rule belongs in" -- structurally the same thing as `permissions.allow`/`.deny`/`.ask`
  as config keys, not a decision.
- **`permissions.get("allow"/"deny"/"ask", ...)`** and every `for perm_type in ("allow",
  "deny", "ask")`-shaped iteration** across `config.py`, `config_divergence.py`,
  `config_validation.py`, `config_write_guard.py`, `permission_migration.py`, `rule_sort.py`,
  `toml_scan.py`, `tools/config_access.py`, `tools/annotate.py`, `tools/redundancy.py`,
  `tools/rule_apply.py`, `tools/security_audit.py`, `tools/maintenance.py`,
  `tools/takeover_audit.py` (its own two `permissions.get("allow", [])` reads) -- the
  permissions-SECTION-name vocabulary, exactly the coordinator's own named example. By far
  the largest category of hits the raw grep produced; none converted.
- **`tools/clarity.py`**'s `section`/`"deny-shadows-allow"`/`by_section[...]` -- same
  permissions-section vocabulary, one further step removed (labels a conflict's section, not
  a decision); one value it uses (`"deny+ask"`) isn't even a valid decision, confirming it.
- **`hook.py`'s `LogRecord.status`** (`"executed"`/`"refused"`/`"ask"`): a genuinely
  DIFFERENT, THIRD vocabulary from `RuntimeVerdict.decision` -- `LogRecord`'s own docstring
  states this explicitly ("Deliberately not the same shape as RuntimeVerdict"). `status="ask"`
  coincidentally shares a spelling with `DECISION_ASK` but means something else; left as a
  literal, with a one-line comment at the site explaining why (this is exactly the "STATUS_*
  vs decisions" hazard the brief itself named, just at a spelling the brief didn't call out).
- **`compound.py`/`resolve.py`/config.py's `fallback_cause`** (`"no_match"`/`"undecidable"`):
  a fourth, separate vocabulary (added TOO-28), not one of the three the brief listed. Left
  as literals -- reported here rather than swept in.

### Judgement call: `config_types.py` left unconverted (2 sites)

`_entries_for_kind`'s `kind == "allow"`/`kind == "ask"` ARE genuine decision comparisons
(`kind` is fed `decision` at the one real call site in `permission_resolution.py`). Not
converted: `config_types.py`'s own docstring and `test_architecture.py`'s exact allow-list
both declare it imports ONLY `toolguard.rule_entry` -- the tightest, most literally-enforced
boundary in the codebase (a leaf explicitly forbidden from importing back into `config`).
Loosening it for two comparisons felt like a disproportionate architecture change to make
inside a literal-sweep task; flagging for a explicit decision rather than doing it silently.

### Also considered and left as prose (not converted)

`tools/installer.py`'s `_ENABLE_TAKEOVER_HELP` (a multi-paragraph CLI `--help` text block
that also names `"ask"`/`"allow"`/`"deny"`/`"allow_with_no_warnings"`) -- read as descriptive
documentation for a human, the same category as a docstring, not a compared/dispatched value.

### Verification

- Suite: `Ran 4064 tests` / `OK (expected failures=4)` -- unchanged, no tests added (none
  needed: every conversion is a same-value literal-to-name swap with no new branch).
- `ruff check .` / `ruff format --check .`: clean.
- `test.unit.test_architecture`: 27/27, confirming the three updated exact import allow-lists
  match the real imports and stay a tightening of `.pyscn.toml`.
- Three fitness checks (`--stdlib`/`--ambient`/`--layers`): PASS.
- Corpus: `tools/corpus_build.py --verify --strict-prose` -> `OK: no differences` at
  `6401`/`61`.
- Calibration (the stronger form, as instructed): mistyped `DECISION_ALLOW`'s VALUE to
  `"allow_TOO28_CALIBRATION_PROBE"` in `constants.py`. `--verify --strict-prose` FAILED hard
  -- not just prose drift: one corpus case's DECISION itself changed (an
  `undecidable_fallback=allow` case's reason switched from a genuine-allow wording to an
  unrelated ask-floor wording), proving the constant is genuinely load-bearing, not just
  present. Reverted; `--verify --strict-prose` passed again; `grep -n "CALIBRATION PROBE"`
  found nothing; `git status --porcelain -- toolguard/constants.py` showed only the
  legitimate 8-constant addition.
- Entry-point smoke test: all 8 console-script modules import cleanly.
