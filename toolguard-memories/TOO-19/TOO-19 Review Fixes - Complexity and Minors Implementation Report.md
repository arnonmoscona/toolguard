---
title: TOO-19 Review Fixes - Complexity and Minors Implementation Report
type: note
permalink: toolguard/too-19/too-19-review-fixes-complexity-and-minors-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Implemented ITEMS 1-8 of the TOO-19 review-fix dispatch (safety gap + 7
complexity/cleanliness refactors) on branch `too-19`. Baseline was 1744 tests
green; final state is **1757 tests green**, `ruff format`/`ruff check` clean
across the whole repo. No git write operations performed.

## ITEM 1 (SAFETY GAP): installer.py config writes now go through the write guard

Routed all 5 flagged `_atomic_write_text` call sites in
`toolguard/tools/installer.py` through
`toolguard.config_write_guard.verified_write_config`:

- `cmd_write_config` (~420): syntax-only (no `expected_patterns`) -- this
  always renders a FRESH minimal file with no rules at all, even on `--force`
  overwrite, so there is no prior pattern set to preserve.
- `cmd_register_hooks` / settings.json (~533): syntax-only (`json` format) --
  this is Claude's `settings.json` (hooks/matchers), not a toolguard
  permissions/hard_deny config, so the pattern-preservation check has no
  meaning here; JSON round-trip verification is still the correct minimum bar.
- `cmd_seed_self_perms` hard_deny write (~736): `expected_patterns` = patterns
  already in the file right before this specific write (permissions,
  including anything just added, plus pre-existing hard_deny) unioned with
  the full new hard_deny deny/allow lists.
- `cmd_enable_takeover` (~853): `expected_patterns` = every pattern in the
  file before the edit (this edit only touches `[takeover_mode]`).
- `cmd_seed_hard_deny` (~1485): `expected_patterns` = every pre-existing
  pattern unioned with the full new deny/allow lists.

Added a public `patterns_in_config_text(text, file_format)` helper to
`config_write_guard.py` (parses text, returns the pattern set) since
installer.py needs to compute `expected_patterns` from an already-on-disk
file, not from an in-memory structure like `write_toml_config`'s callers do.

Found and fixed a real bug while wiring this up: `config_write_guard._atomic_write`
did not create the destination's parent directory, unlike installer.py's own
`_atomic_write_text` it replaces -- this broke every "first write into a
fresh `.claude/`" test. Fixed by adding `directory.mkdir(parents=True,
exist_ok=True)` to `_atomic_write` (verified via existing + one new test that
the guard creates a missing parent directory).

Widened `installer.py main()`'s exception handling to also catch
`ConfigWriteVerificationError` (previously only `InstallerError`), so a
refused write reports cleanly (`error: ...`, exit 2) instead of an uncaught
traceback.

Tests added: `test/unit/test_tools_installer.py` -- new
`TestConfigWriteGuardWiring` class (3 tests: write-config syntax refusal
creates no file, enable-takeover syntax refusal preserves original bytes,
seed-hard-deny content-loss refusal preserves original bytes).
`test/unit/test_config_write_guard.py` -- new `TestPatternsInConfigText` (3
tests) and `TestVerifiedWriteConfigCreatesParentDirectory` (1 test).

Journal/README writes (~152, ~270, ~317, ~327) deliberately left on
`_atomic_write_text` unchanged -- not config, as instructed.

## ITEM 2: migrate() complexity

File: `toolguard/scripts/migrate_permissions.py`. Extracted into: a
`_MigrationSources` dataclass + `_load_migration_sources()` (load/discover
phase), `_find_skipped_ungoverned_patterns` / `_print_skipped_ungoverned`,
`_print_divergent_report`, `_print_redundant_report`,
`_resolve_target_config_path`, `_print_similar_pattern_warnings`,
`_print_dry_run_summary`, `_build_merged_permissions` (merge/resolve
permissions), and `_apply_migration` (write + report, the former try/except
body). `migrate()` itself now only sequences these phases plus the
early-exit "nothing to do" cases.

Measured (pyscn): CC 47 -> **6**, cognitive 122 -> **6**, nesting 6 -> **1**.
No test edits were needed -- all pre-existing migration tests pass unchanged,
confirming behaviour is identical (output text, ordering, return values all
byte-for-byte the same).

## ITEM 3: split_array_elements complexity

File: `toolguard/rule_sort.py` (later moved to `toolguard/toml_scan.py` by
ITEM 8). Introduced a mutable `_ArrayScanState` dataclass and delegated the
per-character dispatch to a new `_scan_array_char(text, i, ch, state)`
function; `split_array_elements` is now just the driving loop plus
end-of-input finalization.

Measured (pyscn): `split_array_elements` itself dropped out of the
"functions worth flagging" list entirely (previously CC 25 / cognitive 71);
`_scan_array_char` now carries CC 23 / cognitive 38 ("high" risk) -- expected
and judged the right trade: the character-dispatch logic needed to live
SOMEWHERE, and giving it its own name, docstring, and unit-testable surface
is a genuine readability improvement over one giant function, not just
metric-shuffling. Did not attempt a dict-dispatch table instead -- the
branches are priority-ordered and mutually exclusive with early returns
(newline > comment > in-quote > structural chars), which a dict dispatch
would obscure, not clarify. Kept the existing extensive docstring on both
functions.

Added one docstring sentence documenting the (pre-existing, not fixed)
triple-quoted-string mis-split limitation, as instructed -- no functional
change.

## ITEM 4: normalize_entry duplicated rejection blocks

File: `toolguard/rule_entry.py`. Added a `_reject(level, message,
corrective_steps)` helper returning normalize_entry's `(None, (Issue(...),))`
shape, and used it at all 5 sites that had this exact structural clone (the
task description said "four"; there are actually 5 -- empty string, native
dict, missing pattern key, invalid wrapper, unsupported type -- all
identical in shape, so all 5 were converted). Exact Issue level/message/
corrective_steps text is byte-for-byte unchanged at every site; verified
against the full existing `test_rule_entry.py` suite (all green, no edits
needed).

## ITEM 5: config_validation double iteration

File: `toolguard/config_validation.py`. Merged the two `for tool in
tools_in_permissions` loops into one `if/elif` (the two conditions are
mutually exclusive by construction). Checked for order dependence first:
`tools_in_permissions` is a plain `set`, and Python's default per-process
string-hash randomization means its iteration order was never stable across
runs to begin with -- so no caller could have relied on the previous
two-pass (grouped) emission order, and no test does either (all existing
tests use `any(...)` membership checks, not positional assertions). Added a
code comment documenting this reasoning. No test edits needed.

## ITEM 6: is_tool_wrapper accepts embedded newlines

File: `toolguard/rule_entry.py`. `_TOOL_WRAPPER_RE` used `re.DOTALL`, so a
pattern like `"Bash(a)\nEvil(b)"` would wrongly fullmatch (greedy `.*`
consumes through the embedded newline to the LAST `)`), letting what looks
like two concatenated tool-wrapper expressions pass what is supposed to be
strict, single-line structured-entry validation. Fixed by dropping
`re.DOTALL` entirely -- re-examining the original comment, DOTALL was never
actually needed for its stated purpose (nested-parens support, e.g.
`Bash(foo(bar))`, works fine without it; `.` already matches parens). Added
tests: `test_dict_with_embedded_newline_in_match_is_rejected` in
`TestNormalizeEntryStructured`, and a new `TestIsToolWrapper` class (5 tests)
directly exercising `is_tool_wrapper`.

Security note included in the code comment: without this fix, a pattern
carrying an embedded newline could smuggle what looks like a second,
unreviewed tool-wrapper expression past structured-entry validation --
low real-world exploitability today (nothing currently interprets a
pattern's content line-by-line), but worth closing since it defeats the
"strict, single wrapper" contract the regex exists to enforce, and a future
consumer (logging/display/mining tooling) could plausibly split on
newlines.

## ITEM 7: session_start.py double config load

File: `toolguard/session_start.py`. Widened `_detect_conflicts` and
`_detect_broken_config_files` to both take an already-loaded `Configuration`
instead of a `cwd` string (removing their own `load_configuration()` calls).
`main()` now loads configuration exactly once and passes the same instance
to both. Updated `test/unit/test_session_start.py`'s `TestDetectConflicts`
and `TestDetectBrokenConfigFiles` classes to build/pass a `Configuration`
double directly instead of patching `load_configuration` (BDD docstrings
updated to match). `TestMain` tests needed no changes (they already patch
`load_configuration` with a fixed `return_value`, which is called once now
instead of twice -- no test asserted call count).

## ITEM 8: config.py hot-path coupling with rule_sort

Extracted the pure, `RuleEntry`-independent TOML section/array boundary
scanning primitives out of `toolguard/rule_sort.py` (~1300 lines, imports
`toolguard.rule_entry`) into a new leaf module, **`toolguard/toml_scan.py`**
(stdlib-only: `re`, `dataclasses`, `typing`). Moved: `_ANY_SECTION_HEADER_RE`,
`_section_header_re`, `find_section_boundaries`, `_find_array_close`,
`_locate_subsection`, `ArrayElement`, `_build_array_element`,
`_ArrayScanState`, `_scan_array_char`, `split_array_elements`,
`find_multiline_structured_entry_line` -- confirmed via full dependency
analysis that none of these reference `RuleEntry`/`PATTERN_KEY` or anything
else from `toolguard.rule_entry`, so the extraction is a true leaf split, not
a partial one.

`toolguard/rule_sort.py` re-imports and re-exports every name external
consumers need (`ArrayElement`, `find_section_boundaries`,
`find_multiline_structured_entry_line`, `split_array_elements`, plus the
private `_locate_subsection` it still calls internally in
`parse_permissions_section_with_comments`) -- every existing external import
site (`annotate.py`, `config_access.py`, `maintenance.py`,
`migrate_permissions.py`, `installer.py`, `test_rule_sort.py`) needed ZERO
changes. `toolguard/config.py` now imports `find_multiline_structured_entry_line`
directly from `toolguard.toml_scan`, so the hook hot path no longer
transitively pulls in `rule_sort.py`.

Given the size (~700 lines across 5 non-contiguous blocks), used a small,
disposable Python script (in the session scratchpad, not committed) to do
the extraction via exact marker-string slicing rather than manual retyping,
specifically to eliminate transcription-error risk on a byte-for-byte code
move; verified with `py_compile` and the full test suite before and after.

Updated `test/unit/test_architecture.py`'s `LAYERS` tuple: added
`("toolguard.toml_scan", frozenset())` and widened `rule_sort`'s allowed set
to include it. All architecture tests pass.

Pre-existing (not newly introduced, out of this item's scope) complexity
noted by this same pyscn run: `_find_array_close` (now living in
`toml_scan.py`) is CC 16 / cognitive 30 ("high" risk) and
`reassemble_permissions_section` (still in `rule_sort.py`) is CC 16 /
cognitive 40 ("high" risk) -- neither was flagged in the original dispatch;
flagging here for awareness, not fixed.

## Test count and quality gates

- Baseline: 1744 tests green (confirmed before any change).
- Final: **1757 tests green** (13 new: 3 installer config-write-guard tests,
  4 config_write_guard tests, 6 rule_entry tests for the newline fix).
- `uv run ruff format .` / `uv run ruff check .`: clean, no findings.
- No anti-patterns introduced: no `async`/`await`, no `threading`, no new
  local (function-body) imports, no unused imports.
- Every new/changed test carries a Given/When/Then BDD docstring.

## pyscn: before/after

Overall health score after all changes: **80/100 (Grade B)** -- Complexity
50/100 (avg 8.3, 22 high-risk functions), Dead Code 100/100, Duplication
55/100 (13.1% cloned, 43 groups -- pre-existing, not addressed by this
dispatch), Coupling 95/100, Cohesion 100/100. No "before" whole-repo run was
captured (this dispatch continues a branch with substantial prior uncommitted
work already mixed in, so a repo-wide before/after health-score delta would
not isolate this session's changes); per-function before/after for the three
functions the task named explicitly:

| Function | Before (CC / cognitive / nesting) | After (CC / cognitive / nesting) |
|---|---|---|
| `migrate()` | 47 / 122 / 6 | 6 / 6 / 1 |
| `split_array_elements()` | 25 / 71 / (n/a) | not flagged (trivial) -- logic now in `_scan_array_char`: 23 / 38 / 5 |
| `normalize_entry()` | not numerically given (flagged for clone duplication only) | 7 / 10 / 2 |

## Deliberately NOT done / partial work, with reasoning

- ITEM 3: did not attempt a dict-dispatch rewrite of the character scanner --
  judged it would reduce clarity given the priority-ordered, mutually
  exclusive branches (see ITEM 3 section above). Kept the straightforward
  extract-to-helper-function approach instead.
- ITEM 3: did not add TOML triple-quoted-string support, per explicit
  instruction -- only documented the limitation.
- ITEM 8: left `_find_array_close` and `reassemble_permissions_section`'s own
  pre-existing high complexity unaddressed -- out of this dispatch's named
  scope; flagged for a future ticket/pass.
- Did not touch the pre-existing 43 duplication groups / 13.1% clone rate
  pyscn reports at the whole-repo level -- out of scope for this dispatch.
- Noticed (but did not investigate or touch) unrelated uncommitted changes
  to `.gitignore` and a new `.claude/commands/documentation-review.md` file
  that appeared in `git status` during this session but were not made by any
  action in this session -- flagging for Arnon's awareness only, not part of
  this report's work.

## Elapsed time and estimated cost by phase

- Phase 1 (planning, requirements capture, file reading): ~13:49-13:51, ~2 min.
- Phase 2 (implementation, ITEMS 1-8, including the ITEM 8 extraction script
  and all intermediate test runs): ~13:51-14:22, ~31 min.
- Phase 3 (self-review: final format/lint/full-suite runs, pyscn analysis,
  this report): ~14:22-14:30, ~8 min.
- Total elapsed: ~41 minutes.

Cost estimate (approximate, based on token volume for a session with heavy
file reads of several ~700-1700 line files, many edits, and ~15 full
test-suite runs): roughly 400-700K total tokens (input+output combined)
at Sonnet 5 pricing, estimated **$3-6 total** for this session. This is a
rough order-of-magnitude estimate, not a metered figure.
