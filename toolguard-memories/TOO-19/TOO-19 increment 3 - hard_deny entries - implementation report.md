---
title: TOO-19 increment 3 - hard_deny entries - implementation report
type: note
permalink: toolguard/too-19/too-19-increment-3-hard-deny-entries-implementation-report
tags:
- task-memory
- TOO-19
- implementation-report
---

## Summary

Implemented TOO-19 Phase 0a, increment 3: fixed the silent-drop bug where a structured
(`{match=..., additionalContext=...}`) entry in `[hard_deny].deny`/`.allow` was invisible
to `Configuration.hard_deny()` (only plain strings were recognised), and added a companion
`hard_deny_entries()` accessor that exposes the wrapper-intact `RuleEntry` objects
(carrying enrichment metadata) for Phase 1's future injection use.

Strict TDD: wrote 8 failing tests first, confirmed each failed for the expected reason
(missing method / silently-empty tuple), then implemented the minimal fix, then re-ran
the full suite green.

## Files changed

- `toolguard/config.py` -- `Configuration.hard_deny()` rewritten; new
  `Configuration._pool_hard_deny_entries()` (shared private helper) and new
  `Configuration.hard_deny_entries()` (public companion accessor) added. No other method
  touched.
- `test/unit/test_hard_deny.py` -- added one import (`_strip_tool_wrapper` from
  `toolguard.rule_entry`, used only inside the new index-alignment test) and one new test
  class `TestHardDenyStructuredEntries` with 8 new test methods. All 21 pre-existing tests
  in the file are byte-for-byte unchanged.

No other files were touched. (Note: `toolguard/config.py`, `test/unit/test_configuration.py`,
`test/unit/_config_isolation.py`, and `test/unit/CLAUDE.md` already carried unrelated,
uncommitted increment-2/TOO-30 changes in the working tree before this session started --
those are pre-existing state, not something this session added to.)

## Shared-helper structure (no-drift guarantee)

```
Configuration._pool_hard_deny_entries(tool_name)
    -> (deny_entries, allow_entries)   # Tuple[RuleEntry, ...] each, wrapper-intact

Configuration.hard_deny(tool_name)
    = strip-wrapper-map(_pool_hard_deny_entries(tool_name))
    -> (deny_patterns, allow_patterns)  # Tuple[str, ...] each, wrapper-stripped

Configuration.hard_deny_entries(tool_name)
    = _pool_hard_deny_entries(tool_name)  # returned directly, no further transform
```

`_pool_hard_deny_entries` is the single walk over `self.layers` (skip native, defend
non-dict `hard_deny` section, run each raw `deny`/`allow` list through the existing
`Configuration._extract_tool_entries` staticmethod -- the same shape-normalization /
tool-scoping chokepoint `permission_layers()` already uses -- then pool into
insertion-ordered `dict[str, RuleEntry]` keyed on `entry.pattern`). Both public methods
call this exactly once and do nothing else that could diverge: `hard_deny()` only maps
`_strip_tool_wrapper` over the two tuples; `hard_deny_entries()` returns the tuple pair
verbatim. There is no second walk anywhere, so the two methods cannot disagree on which
entries were pooled, in what order, or which occurrence won a duplicate -- only on
whether the wrapper is present.

## De-dup comparison used, and why

Keyed on `entry.pattern` (the wrapper-INTACT pattern string), per the spec's default.
This is `RuleEntry`'s "same RULE" comparison (as documented on
`RuleEntry.identity()`'s docstring, contrasted with full `identity()` -- pattern +
metadata -- and a future `merge_entries()`), so an entry with metadata on one side and a
plain string with none on the other are still treated as the same rule, and the
FIRST (most-specific, since `self.layers` is already most-specific-first) occurrence's
metadata is what survives the pool -- exactly matching the pre-existing pooling
semantics for plain patterns. Because `entries_for_tool` has already scoped every entry
to one tool's `Tool(...)` prefix before `_pool_hard_deny_entries` sees it, wrapped-pattern
de-dup and (the old code's) stripped-pattern de-dup are provably equivalent within a
single tool's pool -- two distinct wrapped patterns can never collapse to the same
stripped pattern, and vice versa. No case was found that would justify a different
comparison (`identity()` or a merge) -- did not invent a fourth semantics.

## Test coverage added (test/unit/test_hard_deny.py, class TestHardDenyStructuredEntries)

1. `test_hard_deny_structured_deny_entry_contributes_pattern` -- the silent-drop
   regression guard for `deny` (security-critical case).
2. `test_hard_deny_structured_allow_entry_contributes_pattern` -- same for the `allow`
   carve-out.
3. `test_hard_deny_entries_returns_metadata_and_wrapper_intact_pattern` -- metadata and
   wrapper-intact pattern reachable via `hard_deny_entries()`.
4. `test_hard_deny_and_hard_deny_entries_are_index_aligned` -- `hard_deny()[i]` is the
   stripped form of `hard_deny_entries()[i].pattern`, for both deny and allow.
5. `test_hard_deny_pooling_dedup_first_occurrence_metadata_wins` -- two levels share a
   pattern, only the more-specific carries metadata; pool keeps exactly one entry, the
   metadata-carrying one.
6. `test_hard_deny_native_layer_structured_entry_contributes_nothing` -- native layer
   skipped wholesale, before normalization.
7. `test_hard_deny_malformed_entry_does_not_raise` -- an `int` element in the list is
   silently ignored, no exception, a following valid string still contributes.
8. `test_hard_deny_non_list_deny_value_tolerated` -- a scalar `deny` value (not a list)
   is tolerated as empty.

Each carries a Given/When/Then BDD docstring. All were confirmed RED (failing for the
expected reason: `AttributeError: no attribute 'hard_deny_entries'` for 5 of them,
`AssertionError: () != (...)` for the 2 silent-drop tests) before the implementation, and
GREEN after.

## Confirmations

- **No existing test in `test_hard_deny.py` was modified.** `git diff` shows only
  additions (`+`) in that file -- zero removed/changed lines among the pre-existing 21
  tests.
- **All ~18 `hard_deny()` call sites compile and pass unchanged**: `toolguard/hook.py:807`,
  `toolguard/tools/decision.py:173`, `toolguard/resolve.py:369`,
  `toolguard/config.py:1719` (an internal caller, `has_any_permission_configured`), plus
  12 call sites in `test/unit/test_resolve.py` and the pre-existing 6 in
  `test/unit/test_hard_deny.py` itself -- none needed edits; the full suite runs green
  without touching any of them.
- Full suite: 1563 -> 1571 tests (8 added), all green
  (`uv run python -m unittest discover -s test -t .`).
- `uv run ruff check .` (repo-wide): clean.
- `uv run ruff format` run ONLY on `toolguard/config.py` and `test/unit/test_hard_deny.py`
  (the two touched files) -- not repo-wide, per the "no ruff config, 56/117 files drifted"
  constraint. `test_hard_deny.py` was reflowed (line-wrap only, no logic change); the
  suite was re-run green after.
- Doc comments: `_pool_hard_deny_entries`, `hard_deny` (docstring extended, not
  replaced), and `hard_deny_entries` all carry full docstrings explaining behaviour,
  pooling, de-dup key, and the native-skip/`is_native` threading rationale.
- No `async`/`await`, no threading, no imports inside function bodies introduced
  (verified by grep over the diff).
- Existing-helper inventory before implementing: read `toolguard/rule_entry.py` in full
  and `Configuration._extract_tool_entries`/`permission_layers` before writing any code.
  Reused `_extract_tool_entries` directly rather than re-normalizing entries by hand --
  no reimplementation of shape-normalization or tool-scoping logic.

## Nothing found that contradicts the spec

The spec's four "must not regress" items, the API shape, and the de-dup rule were all
directly implementable as specified with no ambiguity encountered; no deviation was
needed.

## Elapsed time / cost estimate

- Phase 1 (planning: read CLAUDE.md/addendum context already loaded, read
  `rule_entry.py`, `config.py` hard_deny/`_extract_tool_entries`/`ToolPatternLayer`,
  `test_hard_deny.py`, `test/unit/CLAUDE.md`, baseline test run): ~10 min.
- Phase 2 (write 8 red tests, confirm red, implement, confirm green, re-run full suite,
  ruff check/format): ~12 min.
- Phase 3 (self-review: diff scoping check, call-site grep, anti-pattern grep, final
  full-suite + ruff re-run): ~5 min.
- Phase 4 (this report + task recall note): ~5 min.
- Total elapsed: ~32 min.
- Estimated cost: small/medium task, mostly Read/Bash/Edit tool calls with moderate
  file sizes (config.py ~2300 lines read in slices, test file ~500 lines) --
  roughly 60-90K input + 8-12K output tokens on a Sonnet-class model, order of
  $0.30-$0.60 total. This is a rough estimate, not a billed figure.
</content>
