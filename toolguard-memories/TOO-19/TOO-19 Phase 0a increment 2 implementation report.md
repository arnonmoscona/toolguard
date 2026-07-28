---
title: TOO-19 Phase 0a increment 2 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-0a-increment-2-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Wired `toolguard/rule_entry.py`'s `normalize_entry`/`entries_for_tool`/`RuleEntry` into
`Configuration.permission_layers()` and `ToolPatternLayer`, fixing the silent-drop bug
where a structured (`{match = "...", ...}`) allow/deny/ask entry never appeared in the
extracted pattern lists -- most dangerously for `deny`. Scope held exactly to
`permission_layers()`/`ToolPatternLayer`; `hard_deny()`, `toolguard_permissions()`,
`config_validation.py`, and all write paths were not touched (confirmed via `git diff`
hunk inspection -- zero hunks touch those functions/files).

## Files changed (this increment only)

- `toolguard/config.py`
  - Import block: added `from toolguard.rule_entry import RuleEntry, entries_for_tool, normalize_entry`
    (plain, non-aliased -- all three are used directly in this module, unlike
    `is_tool_wrapper`'s pure-re-export alias trick).
  - `ToolPatternLayer`: added `allow_entries`/`deny_entries`/`ask_entries: Tuple[RuleEntry, ...] = ()`
    fields, and documented the index invariant (`allow[i]` == stripped `allow_entries[i].pattern`)
    in the class docstring.
  - New `Configuration._extract_tool_entries` (`@staticmethod`, mirrors the existing
    `_provenance_for_pattern`/`_resolve_takeover_enabled` `@staticmethod`-on-Configuration
    pattern already used in this file): normalizes a raw list via `normalize_entry`,
    scopes via `entries_for_tool`, strips via `_strip_tool_wrapper`, returns
    `(patterns, entries)` index-aligned. Issues from `normalize_entry` are collected and
    explicitly discarded with a comment explaining why (increment 4 will surface them via
    `validation_issues()`) -- the entry itself is never dropped when it parses
    successfully, which is the actual bug fix.
  - `Configuration.permission_layers()`: rewritten to call `_extract_tool_entries` for
    allow/deny/ask instead of the old inline `isinstance(perm, str) and perm.startswith(prefix)...`
    scan; takeover filtering (native-layer-only, compares the STRIPPED pattern against
    `ignored`) now filters `allow`/`allow_entries` together via a single `zip`+list-comprehension
    pass, preserving index alignment. Docstring updated to describe entries and the
    filtering-of-both-lists behavior.
- `test/unit/test_configuration.py`
  - Added `from toolguard.rule_entry import _strip_tool_wrapper`.
  - Added 6 new tests to `TestPermissionLayers` (existing 5 tests were NOT modified --
    verified they still pass unchanged):
    1. `test_structured_entry_appears_in_deny_not_silently_dropped` -- the core deny-side
       regression guard.
    2. `test_mixed_plain_and_structured_allow_entries_populated` -- asserts `allow`/
       `allow_entries` order+membership match and explicitly checks the
       `_strip_tool_wrapper(entry.pattern) == pattern` index invariant, plus metadata
       survives.
    3. `test_structured_entry_in_native_layer_ignored` -- a dict entry in a native
       (`claude`) layer is rejected, only the plain string survives.
    4. `test_takeover_filters_native_allow_entries_too` -- blanket ignored allow removed
       from both `allow` and `allow_entries` under takeover.
    5. `test_entries_scoped_to_requested_tool_only` -- a structured entry for a different
       tool is excluded from both `allow` and `allow_entries`.
    6. `test_malformed_entries_do_not_raise_and_are_excluded` -- a dict missing `match`
       and a bare `int` neither raise nor appear in output.
  - Per `test/unit/CLAUDE.md`'s checklist, `TestPermissionLayers` builds `Configuration`
    directly from hand-built `ConfigLayer`/`Provenance` with zero file I/O, so
    `ConfigIsolationMixin` is correctly NOT used (confirmed by reading the checklist, not
    assumed).

## Stripping mechanism chosen: `_strip_tool_wrapper` (not a re-derived slice)

Spec asked to verify which of the two candidate mechanisms -- the pre-existing inline
slice `perm[len(prefix):-1]`, or `rule_entry._strip_tool_wrapper`'s regex -- reproduces
today's output exactly, and to use whichever does. I wrote a throwaway verification
script (`/tmp/.../scratchpad/verify_strip.py`, not committed) that ran both over 8
patterns satisfying `entries_for_tool`'s scoping guard (`startswith(f"{tool}(")` and
`endswith(")")`), including edge cases: nested parens (`Bash(foo(bar))`,
`Bash(a(b(c)))`), an empty body (`Bash()`), and a malformed extra trailing paren
(`Bash(foo))`). All 8 cases matched exactly between the two mechanisms. Reasoning: once
an entry has already passed the `startswith(prefix)`/`endswith(")")` guard, the greedy
`(.*)`-with-DOTALL regex in `_TOOL_WRAPPER_RE`, anchored via `fullmatch`, is forced to
consume everything between the first `(` and the last `)` -- identical to what the slice
does structurally. I chose `_strip_tool_wrapper` (the module's public, already-imported
helper and, per its own docstring, "the single source of truth for that unwrapping")
over re-deriving the slice inline, to avoid a second implementation of the same
unwrapping logic living in `config.py`.

## Confirmation: no existing `TestPermissionLayers` test needed modification

All 5 pre-existing tests (`test_allow_deny_union_dedup`, `test_only_requested_tool_extracted`,
`test_takeover_filters_native_allow_only`, `test_per_layer_provenance_preserved`,
`test_non_dict_permissions_tolerated`) pass byte-for-byte unmodified against the new
implementation.

## Self-review results

- Full suite: 1557 (baseline, confirmed green before starting) -> 1563 (baseline + 6 new),
  green throughout -- ran after every meaningful edit (import, `ToolPatternLayer`, the
  static helper, the rewired `permission_layers`, each test batch).
- `uv run ruff check toolguard/config.py test/unit/test_configuration.py toolguard/rule_entry.py`:
  clean.
- `uv run ruff format --diff` on only the two touched files: no changes needed (already
  compliant) -- did NOT run repo-wide format per project CLAUDE.md's explicit warning
  (56/117 files drifted from ruff defaults with no `[tool.ruff]` config; a repo-wide
  format would bury this diff).
- `uv run python -m py_compile` on both touched files: OK.
- Anti-pattern scan (async/await, threading, local imports) over both touched files: none
  found.
- Inventory/dup check: grepped for any pre-existing `_extract_tool_entries`-equivalent
  helper or any other `normalize_entry`/`entries_for_tool` call site -- none found; this
  is genuinely the first (and, per spec, only) consumer wired in this increment. The new
  `@staticmethod` follows the exact existing precedent of `_provenance_for_pattern` /
  `_resolve_takeover_enabled` already in this class, rather than introducing a new
  pattern.
- Confirmed via `git diff toolguard/config.py` hunk inspection that no hunk touches
  `hard_deny()`, `toolguard_permissions()`, or any line inside them; confirmed via
  `git diff --stat` that `config_validation.py` and all write-path modules
  (`consolidate.py`, `clarity.py`, `rule_apply.py`, `takeover_audit.py`, `installer.py`,
  `config_access.py`) have zero changes.

## Deviations from spec / things worth flagging

- Spec estimated "~10 existing tests" in `TestPermissionLayers`; there were actually only
  5. Not a contradiction, just an estimate off by a factor of 2 -- noted for the record,
  no action needed.
- Everything else in the spec (back-compat field shapes/defaults, takeover semantics,
  is_native gating, issue-discarding-with-comment, non-dict/non-list tolerance) was
  followed exactly as written; no other contradictions found.

## Timing / cost estimate

- Phase 1 (read rule_entry.py, config.py sections, test file, CLAUDE.md, plan, verify
  stripping mechanism, write task-recall memory): ~4 minutes.
- Phase 2 (write failing tests, confirm red, implement production change, confirm green):
  ~2 minutes.
- Phase 3 (self-review: ruff, py_compile, anti-pattern scan, diff-scope confirmation,
  dup-check): ~1 minute.
- Phase 4 (this report + reply): in progress.
- Total elapsed: ~6-7 minutes wall clock (18:02:47 start -> ~18:09).
- Estimated cost: this was a small, well-scoped increment with modest tool-call volume
  (roughly 30-35 tool calls, mostly small reads/greps/edits, one short bash test run
  loop). At Sonnet-5 pricing this is on the order of a few cents to ~$0.10 -- not
  precisely measurable from here, but this was a light task well under the 30-minute
  scope-inflation threshold.
