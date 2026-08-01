---
title: TOO-19 code review minors m1-m4 m6 - coder task recall
type: note
permalink: toolguard/too-19/too-19-code-review-minors-m1-m4-m6-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task
Fix minor findings m1, m2, m3, m4, m6 from `toolguard-memories/latest-code-review-report.md`
(2026-07-31). Explicitly OUT OF SCOPE: m5 (leave alone, Arnon experiment), m7/m8 (not doing).
M1/M2/M3 (majors, capitalized) already fixed/verified -- do not revisit.

## Per-finding decisions (Arnon's, not mine)

**m1** (compound.py `_resolve_leaf`, ask-floor branch): explicit `ask` rule misattributed to
"ASK floor applied" when floor made no change. Fix: only rewrite reason/drop context when
`floored != decision`. Scoped to the `floored == "ask"` branch only -- add
`if decision == "ask": return "ask", reason, additional_context` before the rewrite. Do NOT
touch the `floored == "allow"` (allow_with_warning escape hatch) branch: existing test
`test_allow_with_warning_reason_names_undecidable_fallback` requires it to ALWAYS say
"undecidable_fallback=allow_with_warning" even when floored==decision=="allow", because that's
a deliberate warning about using the escape hatch, not a floor-decided verdict. `deny` branch
returns early already (unaffected). Add tests distinguishing explicit-ask-rule vs genuine-floor
cases, asserting reason string + context survival.

**m2** (config.py `resolved_no_match_fallback` / `resolved_undecidable_fallback`): duplicate
layer-scan loop. Extract ONE parameterized resolver taking (key, valid_values, default,
legacy_alias=None [callable returning raw legacy value], deprecated_aliases=None [dict]) so
TOO-28's `no_match_fallback_auto_mode` / `undecidable_fallback_auto_mode` can reuse it without
redoing a 2-way dedup. `no_match_fallback` keeps `[takeover_mode]` alias + `warn_deny`->
`allow_with_warning` normalization as parameters, not special-cased in the shared body.
`undecidable_fallback` passes neither. Both already ignore native settings.json layers
(shared body handles this). Existing tests must pass unchanged.

**m3** (resolve.py hard-deny pattern recovery by reason-string parsing): `check_hard_deny`
(permissions.py) should return matched pattern as a 3rd tuple element instead of resolve.py
stripping fixed prefix/suffix off the reason string. Touches: permissions.py signature,
resolve.py call site (~line 606-630), test_hard_deny.py call sites (2-tuple unpack at line
~374, ~568) which need updating to 3-tuple.

**m4** (config.py `_entry_for_pattern`): the `len(entries)==len(candidates)` alignment check
is inside the per-layer loop instead of gating an early return, so a misaligned layer falls
through to the NEXT (less-specific) layer instead of stopping. Fix: return None as soon as
pattern found in a misaligned layer. HARD GATE: must not change any verdict (allow/ask/deny) --
only feeds `winning_entry.additional_context` at config.py:~1648, never the decision itself, so
analytically safe. Must still empirically prove via `toolguard.testing.sandbox` before/after
verdict diff on representative configs, per Arnon's explicit instruction. If any verdict
changes, STOP and report instead of proceeding.

**m6** (`allow_with_warning` doesn't write a warning anywhere): both `no_match_fallback` and
`undecidable_fallback` only put "warning" in the reason string, never reach
`error_log.log_warning`'s WARNING stream. Fix: in hook.py, after decision=="allow" in BOTH the
file-path and Bash branches, detect the marker substrings "no_match_fallback=allow_with_warning"
/ "undecidable_fallback=allow_with_warning" (already-stable, already-tested wording) in `reason`
and route to `log_warning(reason, corrective_steps, log_dir)`. Chosen channel: the warning log
stream (error_log.log_warning), per Arnon's "if we call it allow_with_warning then that's what
it should do" -- reason-string-only doesn't satisfy the doc promise "log a warning". Check BOTH
no_match_fallback and undecidable_fallback are covered (review only found one may have been
checked).

## Additional small item
`test/unit/_real_log_dir_guard.py` / `test/unit/__init__.py` `os._exit(1)` atexit hard exit:
keep mechanism (already flushes stdout/stderr before os._exit, already has substantial
docstring rationale). Add explicit reinforcing comments: why hard exit, why confined to test
harness, why only after all test code completed. Verify by reintroducing a leak, confirming
nonzero exit + full diagnostic printed, then restoring.

## Hard constraints
- unittest not pytest. BDD Given/When/Then docstrings on every new test. No function-level
  imports. Docstrings on every function/class.
- Never bare python/python3 -- always `uv run python`. Never edit outside repo. No git writes.
- Never write to real repo `logs/` -- assert delta 0 (baseline: 56 files, confirmed 0 delta
  after baseline full-suite run).
- Baseline: `Ran 2025 tests ... OK` (confirmed, empty-HOME run).

## Verification required (all)
- Empty-HOME full suite -> OK, 2025 tests (may increase with new tests, must not decrease/fail)
- ruff check . / ruff format --check . clean
- uv run python tools/check_doc_links.py exits 0
- real logs/ delta 0
- m4 verdict-equivalence proof (before/after diff via sandbox)

## Report destination
basic-memory project `toolguard`, path `TOO-19/TOO-19 code review minors m1-m4 m6 - fix
report.md`, tagged `task-memory` and `TOO-19`.
