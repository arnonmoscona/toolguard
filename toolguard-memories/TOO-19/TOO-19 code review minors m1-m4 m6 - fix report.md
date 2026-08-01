---
title: TOO-19 code review minors m1-m4 m6 - fix report
type: note
permalink: toolguard/too-19/too-19-code-review-minors-m1-m4-m6-fix-report
tags:
- task-memory
- TOO-19
---

## Scope
Fixed minor findings m1, m2, m3, m4, m6 from `toolguard-memories/latest-code-review-report.md`
(2026-07-31), per Arnon's explicit per-finding direction. m5 untouched (confirmed below).
m7/m8 not done (per instructions). Majors M1/M2/M3 not revisited (already fixed/verified).

## Files changed
- `toolguard/compound.py` -- m1
- `toolguard/config.py` -- m2, m4
- `toolguard/permissions.py` -- m3 (check_hard_deny signature)
- `toolguard/resolve.py` -- m3 (call site)
- `toolguard/hook.py` -- m6
- `test/unit/test_compound.py` -- m1 tests (3 new)
- `test/unit/test_configuration.py` -- m4 tests (3 new, new class `TestEntryForPatternDrift`)
- `test/unit/test_hard_deny.py` -- m3 call-site updates (2-tuple -> 3-tuple unpack)
- `test/unit/test_hook.py` -- m6 tests (3 new)
- `test/unit/__init__.py` -- small item (reinforcing comments; mechanism unchanged)

10 files touched, all within scope-inflation guardrails. No new files created.

## m1 -- fixed
`compound.py::_resolve_leaf`, ASK-floor branch (`floored == "ask"`): added
`if decision == "ask": return "ask", reason, additional_context` BEFORE the rewrite, so an
explicit `ask` rule whose reason/context the floor did not actually change (`floored ==
decision`) is no longer overwritten with "ASK floor applied" and its context is no longer
dropped. Scoped narrowly:
- The `deny` case returns early already (untouched, unaffected).
- The `floored == "deny"` branch is untouched: floored always != decision there (deny is
  strictly stricter than both ask and allow, so it's always a genuine floor raise) --
  verified this is unreachable as `decision == "deny"` any other way.
- The `floored == "allow"` (allow_with_warning escape hatch) branch is DELIBERATELY untouched:
  existing test `test_allow_with_warning_reason_names_undecidable_fallback` requires it to
  always name `undecidable_fallback=allow_with_warning` even when floored==decision=="allow",
  because that warning is about using the escape hatch on unverifiable inline/heredoc content,
  not a floor-decided verdict -- distinguishing this from the ask case was the reasoning
  worked out with Arnon's task instructions before implementing.

Added 3 tests to `TestResolveLeafAskFloor` (or nearby, see test_compound.py near line 2119):
explicit-ask-rule pass-through, genuine-floor-still-names-floor (contrast case), and
explicit-ask-raised-to-deny (undecidable_fallback=deny; floored != decision even though
decision was already 'ask', so this is correctly still a genuine-floor rewrite).

## m2 -- refactored, 4-setting-ready
Extracted two new `Configuration` methods:
- `_first_toplevel_str_setting(key)` -- the shared layer-scan (most-specific non-native layer
  wins), replacing the duplicated loop body verbatim.
- `_resolve_fallback_setting(key, valid_values, default, legacy_alias=None,
  deprecated_aliases=None)` -- the shared resolve+validate body. `legacy_alias` is a **zero-arg
  callable** (not a fixed attribute name), so it can wrap ANY future legacy-lookup mechanism,
  not just `takeover_mode()`. `deprecated_aliases` is a `{old: canonical}` dict.

`resolved_no_match_fallback()` now calls it with
`legacy_alias=lambda: self.takeover_mode().no_match_fallback`,
`deprecated_aliases={"warn_deny": "allow_with_warning"}`.
`resolved_undecidable_fallback()` calls it with neither parameter.

This is designed so TOO-28's `no_match_fallback_auto_mode` / `undecidable_fallback_auto_mode`
can each add a THIRD/FOURTH call to `_resolve_fallback_setting` with their own key/defaults,
without touching the shared body -- satisfies Arnon's "design for four settings, not two"
instruction. Both settings still ignore native `settings.json` layers (in the shared
`_first_toplevel_str_setting` body) and resolve more-specific-wins (layer scan order
unchanged). All existing `TestResolvedNoMatchFallback` / `TestResolvedUndecidableFallback`
tests pass UNCHANGED -- no test edits were needed for m2 itself (only m4 tests were added to
the same file).

## m3 -- fixed
`permissions.check_hard_deny` now returns `('deny', reason, matched_pattern)` (3-tuple) instead
of `('deny', reason)`, so `resolve.py`'s `_resolve_one` no longer recovers `matched_rule` by
stripping a fixed prefix/suffix off the reason string -- it unpacks the pattern directly.
Updated the 3 call sites in `test_hard_deny.py` that unpacked the old 2-tuple shape (the
`_resolve` helper and 1 direct unit test), added an assertion on the returned pattern in
`test_denies_on_deny_match_without_carveout`. No other consumers found (grepped the whole repo).

## m4 -- fixed, proof included
`config.py::_entry_for_pattern`: moved the `len(entries) == len(candidates)` alignment check
so a misaligned layer returns `None` immediately instead of falling through to the next
(less-specific) layer.

**Verdict-equivalence proof** (per Arnon's hard gate): ran a scratchpad harness (not committed)
building a `Configuration` with a deliberately drifted `ToolPatternLayer` (2 allow patterns, 1
allow_entries) at the winning (project) layer, plus a less-specific (user) layer containing the
SAME pattern string aligned, and resolved via the real
`Configuration.resolve_permission_detailed` with the OLD `_entry_for_pattern` monkeypatched in
vs. the CURRENT (fixed) one:

```
=== drifted layer (git *, ls *) ===
cmd='git status'
  BEFORE: decision='allow' reason='Command matches allow pattern: git *  [project: /project.toml]' context='USER context'
  AFTER:  decision='allow' reason='Command matches allow pattern: git *  [project: /project.toml]' context=None
  verdict_equal=True (context_changed=True)
cmd='ls -la'
  BEFORE: decision='allow' reason='Command matches allow pattern: ls *  [project: /project.toml]' context=None
  AFTER:  decision='allow' reason='Command matches allow pattern: ls *  [project: /project.toml]' context=None
  verdict_equal=True (context_changed=False)
--- drifted layer (git *, ls *): ALL VERDICTS EQUAL = True ---

=== clean single layer ===
cmd='git status'  verdict_equal=True (context_changed=False)
cmd='rm -rf /'    verdict_equal=True (context_changed=False)
cmd='whoami'      verdict_equal=True (context_changed=False)
--- clean single layer: ALL VERDICTS EQUAL = True ---

OVERALL VERDICT-EQUIVALENCE: True
```

The `git status` case exactly reproduces the bug (BEFORE misattributes "USER context" -- the
LESS-specific layer's entry -- to the winning PROJECT-layer rule) and confirms decision/
reason/provenance/override are byte-identical before and after in every case; only
`additional_context` changes, and only in the direction of correctness (a wrong attribution
becomes `None` rather than being fixed forward to the right one, since there IS no reliable
entry once the winning layer's own lists have drifted). No verdict changed in any tested case,
so the fix proceeded per Arnon's conditional approval. Locked in with 3 new unit tests in
`test_configuration.py::TestEntryForPatternDrift` (drift -> None; aligned -> normal resolution;
end-to-end verdict-equality through `resolve_permission_detailed`).

## m6 -- fixed, channel chosen: the WARNING log stream
Added `hook._log_fallback_allow_warning(reason, log_dir)`: detects either fallback setting's
stable, already-tested marker substring (`"no_match_fallback=allow_with_warning"` /
`"undecidable_fallback=allow_with_warning"`) in an 'allow' decision's reason, and when found,
calls `error_log.log_warning(reason, corrective_steps, log_dir)`. Wired into BOTH the
file-path/Read-Write-Edit allow branch and the Bash allow branch of `hook.main()` -- confirmed
BOTH `no_match_fallback` (file-path + Bash) and `undecidable_fallback` (Bash-only, since it's a
Bash/compound-specific setting) reach this. Chose the log_warning stream over "reword the docs"
per Arnon's explicit "if we call it allow_with_warning then that's what it should do" -- the
docs promise "log a warning", which only the dedicated WARNING stream keeps. Substring
detection (not prefix/suffix extraction) was chosen deliberately to avoid repeating the m3
fragility pattern -- nothing is RECOVERED from the reason, only detected, and the markers are
exact, already-tested wording shared by 3 existing call sites (config.py's no_match_fallback
path, compound.py's ask-floor path, compound.py's UndecidableSegment path) with zero risk of a
false negative from independent wording drift (a change to any of the three would need to also
change the shared marker text, at which point the substring check and the existing wording
tests would both need updating together).

Added 3 tests to `test_hook.py::TestNoMatchFallbackThroughMain`: no_match_fallback reaches
log_warning; an ordinary explicit allow does NOT reach log_warning (negative control); and
undecidable_fallback (via a heredoc-into-python compound) also reaches log_warning.

NOTE: this fix is now live in this session's own dogfooded toolguard install (`which toolguard`
resolves to this repo's own `.venv/bin/toolguard`), so my own subsequent Bash tool calls that
fell to `no_match_fallback=allow_with_warning` started writing real
`logs/toolguard-warning-2026-08-01.md` entries mid-session -- direct, unplanned validation that
the fix works, not a bug.

## Additional small item -- `_real_log_dir_guard.py` / `test/unit/__init__.py`
Kept the `os._exit(1)` mechanism as-is (it already flushed stdout/stderr before exiting).
Added explicit comments: one above `atexit.register(...)` stating the backstop is confined to
this test-harness package (never imported by `toolguard/`), and that atexit callbacks run only
after every test method/tearDown/tearDownModule/unittest's own summary have already completed;
one above the `os._exit(1)` call itself reinforcing why the flush must precede it.

Verified the guard still fails correctly: ran a throwaway subprocess harness (not committed)
that imports `test.unit` (installing the guard), injects a synthetic leak event directly into
the in-memory registry, and lets the process exit normally. Result: **returncode 1**, and the
full diagnostic banner (including the synthetic leak line) printed to stderr in full. Confirms
the atexit backstop still fires correctly after the reinforcing-comment edit.

## Verification (all required, all passed)
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -- **Ran 2034 tests ... OK** (baseline was 2025; +9 net new
  tests: 3 m1 + 3 m4 + 3 m6, m3's test changes were edits not additions).
- `uv run ruff check .` -- All checks passed.
- `uv run ruff format --check .` -- 134 files already formatted (ran `ruff format .` once mid-
  task, which reformatted `test_configuration.py`; reran the full suite after, still OK).
- `uv run python tools/check_doc_links.py` -- All internal documentation links resolve.
- Real repo `logs/` delta around the full-suite run itself: **0** (57 files before, 57 after,
  confirmed via `diff` on a sorted file listing, both at the start of the session and again
  after all code changes were complete). Separately, and NOT part of this gate: this session's
  own interactive Bash tool calls, governed live by this repo's own dogfooded toolguard
  install, grew the pre-existing resolution/warning logs over the course of the session --
  expected normal operation of working in this repo, unrelated to and not caused by the test
  suite (the guard mechanism's zero-leak result is what actually gates test-suite safety).

## m5 confirmation
Not touched. Grepped and reviewed only; no edits made to any code or test path specific to m5
(the JSONL discovery-log size-guard degradation, already noted as fixed under M3 for its
substantive over-engineering concern, separate from m5's own remaining scope which Arnon wants
run as a deliberate two-approach experiment later).

## Time / cost (rough estimate, Sonnet 5)
- Phase 1 (read review, rules, source, plan, task-recall memory): ~15 min, ~$0.60
- Phase 2 (implementation across 5 findings + small item + all tests): ~75 min, ~$3.50
- Phase 3 (self-review, verdict-equivalence proof, guard re-verification, full-suite runs,
  ruff/doc-link checks): ~20 min, ~$0.80
- Phase 4 (this report, memory writes): ~5 min, ~$0.20
- **Total: ~115 min, ~$5.10 estimated** (token-usage-based estimate, not exact).
