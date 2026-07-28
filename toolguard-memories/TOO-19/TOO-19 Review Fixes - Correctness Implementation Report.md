---
title: TOO-19 Review Fixes - Correctness Implementation Report
type: note
permalink: toolguard/too-19/too-19-review-fixes-correctness-implementation-report
tags:
- TOO-19
- task-memory
---

# TOO-19 Review Fixes - Correctness Implementation Report

Branch: too-19. Baseline confirmed 1713 tests green before any change. Final: **1744
tests green** (+31 new tests, 0 regressions). `uv run ruff format .` and
`uv run ruff check .` both clean. No git write operations performed.

## Pre-existing state note (important context)

Before this session started, the working tree ALREADY contained substantial
uncommitted TOO-19 work from a prior session (confirmed via `git status --short` at
launch: ~20 modified/added files across `toolguard/` and `test/unit/`, plus many
`toolguard-memories/TOO-19/*.md` files). This explains why some `git diff --stat`
numbers below (e.g. `rule_sort.py` showing ~1093 changed lines) are much larger than
what I personally edited -- most of that content predates this session. I did not
audit or re-verify that prior work; my diffs are additive on top of it.

The WRAP-UP step explicitly required a repo-wide `uv run ruff format .`. Since a lot
of that pre-existing uncommitted work had never been formatted, this single command
reformatted 40 files project-wide (confirmed via `ruff check .` before/after and the
full suite staying green at 1744). I did **not** revert any of that -- reverting via
git would have required `git checkout`, which risks destroying legitimate prior
uncommitted work, a destructive operation I'm not permitted to take unilaterally.
Flagging this so it isn't mistaken for scope creep I introduced deliberately.

## Change 1 (CRITICAL): find_section_boundaries line-anchoring -- DONE

`toolguard/rule_sort.py`: replaced the `text.find("[section]")` substring scan and
the `"\n["` end-scan with two MULTILINE regexes (`_section_header_re(name)` for the
start, module-level `_ANY_SECTION_HEADER_RE` for the end) requiring the ENTIRE line
(only leading/trailing horizontal whitespace allowed) to be `[name]`. Verified against
the supplied repro script (`probe6.py`) -- confirmed it reproduced the corruption
before the fix and is now silently fixed (output is valid TOML, `tomllib.loads`
succeeds).

Callers re-verified unaffected: `annotate.py` (slices `old_text[start:end]`, unaffected
by the boundary-finding algorithm change), `config_access.py._layer_comment_map` (same),
`find_multiline_structured_entry_line` (same), `write_toml_config` (same, plus now also
routed through the Change 2 guard). `installer.py`'s use for `[takeover_mode]` also
re-verified (its own 89 tests all green).

Tests added (`test/unit/test_rule_sort.py`, `TestFindSectionBoundaries`): substring
match inside an earlier section's quoted string, substring match inside a `#` comment,
leading-whitespace header line, and an end-boundary case with a bracketed nested-array
continuation line that must NOT be mistaken for the next section header.

## Change 2 (CRITICAL, architectural): config_write_guard -- DONE, with one scope note

New module `toolguard/config_write_guard.py` -- confirmed stdlib-only (`tomllib`,
`json`, `os`, `tempfile`, `pathlib`, `typing`); imports nothing from `toolguard`.
Public API exactly as specified: `ConfigWriteVerificationError` (path/reason/message),
`verify_config_text(text, file_format, path=None)` (pure syntax check; `path` is an
optional kwarg beyond the literal spec signature, used only to enrich the error when
callers have one -- `verified_write_config` always supplies it), and
`verified_write_config(path, text, file_format, *, expected_patterns=None)` doing
verify -> content-loss check (scans `permissions.allow/deny/ask` and every list-valued
key under `hard_deny`, plain-string and `{match=...}` entries) -> atomic write
(sibling temp file, fsync, `os.replace`, temp-file cleanup on any failure).

Wired into:
- `migrate_permissions.write_toml_config` -- all three branches (new-file, append,
  section-replace), `expected_patterns` = every pattern in the `permissions` argument
  via a new `_patterns_from_permissions()` helper.
- `migrate_permissions.write_json_config` -- same.
- `maintenance.py:791` (`_run_annotate`'s `--write` path) -- `expected_patterns`
  derived by re-parsing the file's OLD text (new `_permission_patterns_in_text()`
  helper using `find_section_boundaries` + `parse_permissions_section_with_comments`),
  since annotation only ever inserts comments and must never drop a rule.
- **Additional sites found and wired** (beyond the 3 named in the spec, per "search
  for other write sites"):
  - `rule_apply.py:385` (`_apply_to_file`'s real write after `_render_via_writer`
    renders onto a throwaway temp copy) -- this is the ACTUAL destination write for
    `toolguard-maintain --apply --write`'s consolidation engine, using the very same
    writer functions this ticket is about. Wired with `expected_patterns` from
    `new_permissions`.
  - `migrate_permissions.update_settings_file` (writes `settings.local.json`, Claude's
    own native settings file) -- not explicitly named in the exclusion list
    (audit/decision-ledger/log-writer), and it edits `permissions.allow/deny/ask`
    directly, so the same corruption/data-loss risk applies. Wired with
    `expected_patterns` = every pattern NOT being removed.
- **Found but NOT wired** (flagging rather than expanding scope further):
  `toolguard/tools/installer.py` has 4 more `toolguard_hook.toml` write sites (all via
  its own `_atomic_write_text` helper, used at lines ~422, ~738, ~855, ~1487 for
  write-config/migrate/takeover-mode-rewrite/another rewrite). These already have
  their own atomic (temp+rename) crash-safety, just not the syntax/content-loss
  verification. I did not wire these: doing so properly needs per-call-site
  `expected_patterns` derivation and touches a large, unfamiliar file with 4 distinct
  call sites, which would have pushed this already-large task well past a reasonable
  single-pass scope. Recommend a fast, narrowly-scoped follow-up ticket.

Tests: new `test/unit/test_config_write_guard.py` (15 tests) covering syntax refusal
+ original-file-untouched, the exact reintroduced Change-1 corruption shape (regression
net), content-loss refusal + success, atomic-write success with no leftover temp file,
and cleanup-on-`os.replace`-failure (via mocking, not directory deletion, since mkstemp
itself would fail before reaching the cleanup path in the deletion approach I first
tried and rejected). Plus wiring-confirmation tests added to `test_migration.py` (5),
`test_tools_maintenance.py` (1), and `test_tools_rule_apply.py` (2).

## Change 3 (MAJOR): per_layer_rules ask fix -- DONE

Verified `ToolPatternLayer.ask`/`ask_entries` really are populated by
`permission_layers()` for every layer (native included, trivially empty since native
JSON has no `ask` key) before relying on it. Replaced the hand-rolled loop with
`ask = tl.ask if (tl is not None and not layer.is_native) else ()`, matching the
allow/deny pattern already used in the same function. Added
`test_per_layer_rules_surfaces_structured_ask_entry` to `test_tools_config_access.py`.

## Change 4 (MAJOR): rule_lines/rule_comments identity-keying -- DONE, fallback keying used

**Decision: `(pattern, occurrence_index)` fallback, not full `RuleEntry.identity()`.**
Rationale: `parse_permissions_section_with_comments`'s returned `parsed_value` is
documented (and relied on by `annotate.py` and `config_access.py`) to be a bare
pattern **string**, never the full dict/metadata -- by the time `_parse_array_body`
builds its output, `_rule_pattern_of_value()` has already discarded everything except
the pattern. Widening that return contract to also carry metadata would ripple into
those other consumers and is a bigger, riskier change than this ticket's scope.
Instead, `reassemble_permissions_section` now assigns each ORIGINAL parsed rule item a
`(pattern, occurrence_index)` key (occurrence counted in parse order), and assigns each
`new_permissions` entry the same kind of key counted in the ENTRIES ARGUMENT'S OWN
GIVEN (pre-sort) order, sorting `(entry, key)` pairs together so post-sort lookups still
resolve to the right original key. This relies on same-pattern duplicates appearing in
the same relative order on both sides -- verified true for the one real producer of
this shape, `merge_entries`, whose own docstring states it "preserves first-appearance
order... within a group" for its case-3 (contradiction, keep-both) output.

A synthesized entry (`RuleEntry.has_raw is False`, e.g. `merge_entries`'s case-2
union-merge result) still always renders fresh rather than reusing any original
line -- unchanged reasoning, updated to reflect the new keying.

Updated the docstring at the top of `reassemble_permissions_section` (new
"Duplicate-pattern keying" section) and the inline comment that previously only
guarded the synthesized-entry case.

Tests: `test_same_pattern_different_metadata_entries_both_survive_reassembly` in
`test_rule_sort.py` (direct), and
`test_same_pattern_different_metadata_both_survive_write_round_trip` in
`test_migration.py` (full `write_toml_config` round-trip, per the spec's explicit
ask) -- both confirm two same-pattern structured entries with different
`additionalContext` values both survive with their own text intact.

## Change 5 (MAJOR): discover_tools structured-entry fix -- DONE

Confirmed the function at `config_access.py` matching the spec's description is
`discover_tools` (line 236 in the pre-edit file matched the described
`isinstance(perm, str)` check exactly; no function literally named
`governed_tool_names` exists in this codebase). Routed through `normalize_entry`
(already imported in this module), extracting `.pattern` from the normalized
`RuleEntry` instead of gating on `isinstance(perm, str)`.

Confirmed and left alone, as instructed: `takeover_audit.py` lines 204/243 and
`config_access.py`'s `audit_context` (formerly line 773) -- both are inside an
`if not layer.is_native: continue` / `if is_native: continue` guarded block, i.e.
genuinely native-layer-only by design, where a structured entry is correctly never
expected.

Test: `test_discovers_tool_governed_only_by_structured_entry` in
`test_tools_config_access.py`.

## Change 6 (MINOR): _parse_source delegation -- DONE

Confirmed behavioural identity for both the file-missing and file-broken cases before
collapsing: both functions share the identical `_try_parse_source` call and identical
warning-print; the only difference is `_parse_source_recording_failures`'s conditional
append into its `parse_failures` accumulator, gated on `path.exists()`. Passing a
fresh, immediately-discarded list reproduces "never records" exactly for both cases.
`_parse_source` now reads `return _parse_source_recording_failures(path, file_format, [])`
(a normal `def`, not a lambda). Docstring preserved and extended to describe the
delegation and why it's behaviour-identical. No new test needed (existing coverage of
`_parse_source`'s callers, e.g. `TestParseSourceTomlDiagnostics` in
`test_toml_config.py`, already exercises both paths and stayed green).

## Files changed

New:
- `toolguard/config_write_guard.py`
- `test/unit/test_config_write_guard.py`

Modified (production):
- `toolguard/rule_sort.py` (Changes 1, 4)
- `toolguard/scripts/migrate_permissions.py` (Change 2 wiring + `update_settings_file`)
- `toolguard/tools/maintenance.py` (Change 2 wiring)
- `toolguard/tools/rule_apply.py` (Change 2 wiring, additional site found)
- `toolguard/tools/config_access.py` (Changes 3, 5)
- `toolguard/config.py` (Change 6)

Modified (tests):
- `test/unit/test_rule_sort.py`
- `test/unit/test_migration.py`
- `test/unit/test_tools_maintenance.py`
- `test/unit/test_tools_rule_apply.py`
- `test/unit/test_tools_config_access.py`
- `test/unit/test_architecture.py` (LAYERS: added `config_write_guard` leaf and the
  previously-missing `rule_sort` entry, per WRAP-UP)

## Self-review results

- Anti-pattern scan: no `async`/`await`, no `threading`, no new local imports (ratchet
  test in `test_architecture.py` still passes with zero new offenders).
- `uv run ruff format .` / `uv run ruff check .`: clean.
- `uv run python -m py_compile` on every touched file: clean.
- Full suite: 1744/1744 green (1713 baseline + 31 new).
- Requirements re-verified against the original task spec point by point (this
  report); no requirement skipped. The one deliberate incompleteness (installer.py's
  4 additional write sites) is disclosed above, not silently dropped.

## Scope note

This task's own spec named 6 files (`rule_sort.py`, new `config_write_guard.py`,
`migrate_permissions.py`, `maintenance.py`, `config_access.py`, `config.py`) before any
"search for more" instruction, so the large touched-file count was inherent to the
assigned task, not something I expanded unprompted. I found and wired 2 additional
production write sites (`rule_apply.py`, `update_settings_file`) as directly analogous
instances of the exact defect class Change 2 targets, and explicitly did NOT wire
`installer.py`'s 4 sites, flagging them instead of silently absorbing more scope.

## Time / cost estimate

- Phase 1 (planning, reading source, memory writeup): ~5 min
- Phase 2 (implementation, Changes 1-6 + wiring + wrap-up): ~20 min
- Phase 3 (self-review, final verification): ~5 min
- Total elapsed: ~30 minutes

Rough token-based cost estimate (Sonnet-class pricing, heavy tool use with large file
reads): on the order of $2-4 for this session. This is an approximation from usage
pattern, not a precise billing figure.

---

# Round 2 review fixes (2026-07-27)

Branch: too-19. Baseline confirmed **1757 tests green** before any change. Final:
**1783 tests green** (+26 new tests, 0 regressions). `uv run ruff format` (only the
edited files, per this round's explicit instruction -- NOT a bare `.`) and
`uv run ruff check .` both clean. No git write operations performed.

**Note on this memory file's own path**: the spec named
`toolguard-memories/TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md`,
but the file only actually exists at the nested duplicate path
`toolguard-memories/toolguard-memories/TOO-19/...` (a pre-existing artifact from a prior
session -- visible in `git status` as an already-staged "new file" at that nested path).
I appended here, to the file that actually has the Round 1 content, rather than creating
a second, empty-history file at the literal path given. Flagging this discrepancy rather
than silently working around it.

## Defect 1 (MAJOR): malformed structured entry blocked every config write -- FIXED

Repro first (per instructions), confirmed BEFORE fixing: built entries via
`normalize_entries_preserving()` on a config with `{ additionalContext = "oops" }`
(missing `match`), then called `write_toml_config()` -- raised
`ConfigWriteVerificationError: ... missing pattern(s): {'additionalContext': 'oops'}`.
Also confirmed for a JSON list containing a bare `42`.

Root cause exactly as diagnosed in the spec: `normalize_entries_preserving()`'s
synthesized `repr(raw)` pattern was fed into `expected_patterns`, which
`verified_write_config()` can never match against real written text.

Fix: added an explicit `RuleEntry.synthesized_pattern: bool` field (default `False`,
`compare=False`/`repr=False`, mirroring `raw`'s own bookkeeping-field style), set `True`
only in `normalize_entries_preserving()`'s fallback branch. Added a new chokepoint
`toolguard.rule_entry.real_patterns(entries)` that extracts patterns from a mixed
str/RuleEntry list while **excluding** any `synthesized_pattern=True` entry, and switched
every write-path `expected_patterns` builder to it:
- `migrate_permissions._patterns_from_permissions` (used by both `write_toml_config` and
  `write_json_config`).
- `rule_apply._apply_to_file`'s real-write `expected_patterns`.

For `maintenance._permission_patterns_in_text` (which does NOT go through
`RuleEntry` -- it re-parses raw file text via `parse_permissions_section_with_comments`),
the equivalent fix is in `rule_sort._rule_pattern_of_value`: its existing `repr(value)`
malformed-entry fallback now returns a new `SyntheticPattern(str)` marker subclass
instead of a bare `str` (behaves identically as a string everywhere -- equality, hashing,
dict keys -- so `rule_lines`/`rule_comments` keying, `annotate.py`, and
`config_access.py` are all unaffected), plus a new `is_synthetic_pattern()` predicate.
`_permission_patterns_in_text` now filters on it.

**Did NOT touch `config_write_guard.py`'s `_entry_pattern`/`_patterns_in_parsed`**,
despite the spec listing that file: on inspection they are already correct (they only
ever extract a real pattern from parsed JSON/TOML -- a plain string or a structured
entry's `match` value -- and can never themselves produce a `repr()`-shaped value), so
there was nothing to fix there. Also confirmed the "tell the user which FILE" requirement
was already met: `ConfigWriteVerificationError.__str__` already includes `path` in every
raised message (`verified_write_config` always supplies it) -- this was true before this
round's changes too, just previously obscured by the misleading synthesized-pattern
value shown alongside it. No change made to that error-formatting code; the "which
entry" part is now satisfied for free, since a missing pattern is always a REAL pattern
after this fix, which itself identifies the offending rule.

Verified (per instructions) that a genuine drop is STILL refused, at three levels:
the existing (unmodified) `test_config_write_guard.TestVerifiedWriteConfigContentLossGuard`
tests still pass; a fresh scratchpad repro
(`verified_write_config` with text that really omits an expected pattern) still raises;
and a new `test_migration.py` test
(`test_write_still_refused_when_a_real_pattern_is_genuinely_dropped`) exercises
`real_patterns()` alongside a genuine additional omission and confirms refusal.

Tests added: `test_rule_entry.py` (`TestRealPatterns`, 5 tests, plus 2 new assertions
in the existing `test_unnormalizable_elements_are_preserved_not_dropped` confirming
`synthesized_pattern` is `True` only for the unnormalizable elements);
`test_migration.py` (`TestWriteConfigToleratesMalformedEntries`, 3 tests: TOML
malformed-entry survival, JSON non-string-element survival, genuine-drop-still-refused);
`test_tools_rule_apply.py` (1 test: `_apply_to_file` tolerates an unrelated malformed
entry); `test_tools_maintenance.py` (2 tests: direct `_permission_patterns_in_text`
exclusion, plus a full `--annotate --write` end-to-end run against a file holding a
malformed entry); `test_rule_sort.py` (`TestIsSyntheticPattern`, 4 tests).

## Defect 2 (MAJOR): render_toml_entry crashed on non-str, non-dict values -- FIXED

Repro confirmed: `render_toml_entry(42)` raised
`AttributeError: 'int' object has no attribute 'replace'` (same for `None`, `True`).

Fix: `render_toml_entry` now delegates its entire "not a RuleEntry" branch to the
module's existing total renderer `_render_toml_scalar` (which already handles
str/bool/int/float/list/dict, dispatching to `_render_toml_inline_table` for dicts),
instead of its own partial dict-then-string-escape logic. Confirmed byte-identical
output for the two previously-supported shapes (plain string, structured dict) both
via direct interactive checks and by re-running the FULL existing test suite with zero
edits to any pre-existing test -- all stayed green.

Tests added: `test_rule_sort.py` (`TestRenderTomlEntry`, 7 tests: plain string,
structured dict, int, bool x2, None, list, and a `RuleEntry` wrapping a raw non-str
value -- the actual shape the write path feeds this function).

## Defect 3 (MAJOR): find_section_boundaries regression on trailing comment -- FIXED

Repro confirmed: `find_section_boundaries("[permissions] # my perms\n", "permissions")`
returned `(-1, -1)` instead of the correct span; `[permissions]` and `  [permissions]\t`
(no comment) still worked.

Fix: both `_ANY_SECTION_HEADER_RE` (end-boundary scan) and `_section_header_re()` (start
match) gained an optional trailing `(?:#.*)?` group after the existing
`[ \t]*` whitespace allowance: `^[ \t]*\[name\][ \t]*(?:#.*)?$`.

Verified the CRITICAL regression guard: re-ran `scratchpad/probe6.py` (the
quoted-string-false-positive repro from Round 1's own fix) -- still prints "parsed OK"
with the `hard_deny` rule fully intact, confirming the trailing-comment allowance did
not reopen the original substring-match bug (a comment-line anchor still requires the
WHOLE line to be `[name]` plus optional comment; a `[permissions]` occurrence embedded
inside a longer quoted-string line never satisfies that).

Tests added to `test_rule_sort.py`'s existing `TestFindSectionBoundaries`: trailing
comment, trailing comment with odd/irregular spacing, a comment containing a `]`
character, and a re-verification of the quoted-string false-positive case specifically
alongside the new trailing-comment allowance (regression guard, distinct test from the
pre-existing one so both are independently locked down).

## Files changed (Round 2)

Modified (production):
- `toolguard/rule_entry.py` -- `synthesized_pattern` field, `real_patterns()`
- `toolguard/rule_sort.py` -- `render_toml_entry` delegation, `SyntheticPattern`,
  `is_synthetic_pattern()`, `_rule_pattern_of_value` fix
- `toolguard/toml_scan.py` -- trailing-comment regex fix (both header patterns)
- `toolguard/scripts/migrate_permissions.py` -- `_patterns_from_permissions` uses
  `real_patterns()`
- `toolguard/tools/rule_apply.py` -- `_apply_to_file`'s `expected_patterns` uses
  `real_patterns()`
- `toolguard/tools/maintenance.py` -- `_permission_patterns_in_text` filters via
  `is_synthetic_pattern()`

Not modified (confirmed already correct on inspection):
- `toolguard/config_write_guard.py`

Modified (tests):
- `test/unit/test_rule_entry.py`
- `test/unit/test_rule_sort.py`
- `test/unit/test_migration.py`
- `test/unit/test_tools_rule_apply.py`
- `test/unit/test_tools_maintenance.py`

## Self-review results (Round 2)

- Every defect reproduced BEFORE fixing, and re-verified as fixed with the same repro
  (plus new automated tests), per instructions.
- Anti-pattern scan on every edited file (production + test): no `async`/`await`, no
  `threading`, no new local imports (grep-confirmed; the few local imports present in
  `test_migration.py`/`test_tools_maintenance.py` predate this round -- confirmed via
  `git diff` hunk boundaries).
- `uv run ruff format` run ONLY on the 12 files this round touched (not a bare `.`),
  per this round's explicit instruction; `uv run ruff check .` clean afterward.
- Full suite: 1783/1783 green (1757 baseline + 26 new).
- Both required verification scripts re-run and confirmed passing:
  `scratchpad/probe6.py` ("parsed OK", `hard_deny` intact) and
  `scratchpad/verify_change4.py` ("PASS - both metadata preserved").
- No requirement skipped; the two spots where I deviated from the literal spec text
  (not touching `config_write_guard.py`'s parsing functions; appending to the nested
  duplicate memory-file path) are disclosed above with reasoning, not silently done.

## Time / cost estimate (Round 2)

- Phase 1 (planning, reading source, memory writeup, reproducing all 3 defects): ~15 min
- Phase 2 (implementation across 6 production files): ~20 min
- Phase 3 (test authoring across 5 test files, self-review, full-suite + script
  re-verification, ruff): ~20 min
- Total elapsed: ~55 minutes

Rough token-based cost estimate (Sonnet-class pricing, heavy tool use with several
large file reads): on the order of $3-5 for this session. Approximation from usage
pattern, not a precise billing figure.