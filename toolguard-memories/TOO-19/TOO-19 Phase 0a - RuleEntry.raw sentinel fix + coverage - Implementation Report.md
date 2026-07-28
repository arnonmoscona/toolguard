---
title: TOO-19 Phase 0a - RuleEntry.raw sentinel fix + coverage - Implementation Report
type: note
permalink: toolguard/too-19/too-19-phase-0a-rule-entry.raw-sentinel-fix-coverage-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Fixed a confirmed data-corruption bug in `RuleEntry.to_source()` (Part 1) and closed
the three genuinely-uncovered lines in `toolguard/rule_entry.py` (Part 2), with tests
added only to `test/unit/test_rule_entry.py`. Branch `too-19`, working tree left green
throughout (never broke the 1624-test baseline). No refactor beyond spec.

## Part 1: the sentinel fix

**Approach taken:** module-level sentinel object, as the spec's default suggestion.

```python
_UNSET = object()
```

used as `RuleEntry.raw`'s default (`field(default=_UNSET, compare=False, repr=False)`),
plus a new public `has_raw` property (`self.raw is not _UNSET`) so every call site tests
presence via the property rather than reaching for the private sentinel directly. Chose
the property over exposing `_UNSET` itself: it reads better at call sites
(`if entry.has_raw`) and keeps the sentinel an implementation detail. Considered a
separate boolean field instead (the spec's suggested alternative) but rejected it: it
would need to be kept in sync with `raw` at every one of the 6 construction sites,
whereas the sentinel makes "not recorded" self-evidently a distinct value with no
separate invariant to maintain. Dataclass stays frozen and hashable (`raw` still
`compare=False`, `__hash__` unaffected -- it hashes `identity()`, which never touched
`raw`).

`to_source()` now reads `if self.has_raw: return self.raw`, so a genuine `raw=None`
(e.g. a parsed JSON `null` element) round-trips as `None`, not the string `"None"`.

**Every `.raw`-inspecting / `RuleEntry(`-constructing site, and whether it needed changing:**

| Site | Needed change? | Why |
|---|---|---|
| `rule_entry.py` `to_source()` | YES (the bug) | `raw is not None` -> `has_raw` |
| `rule_entry.py` `is_structured` (`isinstance(self.raw, dict)`) | No | Unaffected either way per spec; `_UNSET` is never a dict |
| `rule_entry.py` `merge_entries()` case-2 union-merge construction | YES | Was explicit `raw=None`, which under the sentinel scheme now means "has_raw=True, value None" -- WRONG for a synthesized entry with no original to preserve. Removed the explicit arg so the default (`_UNSET`) applies. |
| `rule_sort.py:524` `is_synthesized = ... entry.raw is None` | YES (2nd instance of the identical bug class) | Same conflation: a merge-produced `RuleEntry` with a genuine `raw=None` would have been wrongly treated as "synthesized" (losing its preserved formatting) before this fix in the sentinel world. Changed to `not entry.has_raw`. |
| `scripts/migrate_permissions.py:915` `RuleEntry(pattern=pattern, raw=pattern)` | No | Always a concrete non-None string |
| `tools/rule_apply.py:240` `RuleEntry(pattern=added_wrapped, raw=added_wrapped)` | No | Always a concrete non-None string |
| `normalize_entry()` / `normalize_entries_preserving()` construction sites | No | Already pass `raw=raw` explicitly in every branch (including the unnormalizable-element preservation branch) -- correct already, the bug was purely in the *reading* side |

**Existing tests updated, and why unavoidable:** none needed a logic/assertion change --
grepped for `entry.raw is None` assertions across the test suite and found none; every
existing `.raw` assertion checks an explicit non-None value or relies on `compare=False`
equality (unaffected). Two test docstrings in `test_rule_entry.py`
(`test_to_source_synthesizes_for_constructed_entry_with_metadata` and
`test_to_source_synthesizes_bare_string_for_constructed_entry_without_metadata`) said
"constructed directly (raw=None)" -- now misleading since `raw=None` is a distinct,
valid state under the sentinel. Reworded to "constructed directly with no raw recorded
(the default sentinel, has_raw is False)". No test code changed, docstring wording only.

## Part 2: coverage

Ran `uv run python tools/coverage_stdlib.py` before and after.

**`toolguard/rule_entry.py`: 94.8% -> 96.6%.**

Real gaps closed (confirmed via `grep -n '>>>>>>' cover/toolguard.rule_entry.cover`):
- `normalize_entries_preserving`'s `return ()` for a non-list `raw_list`.
- The unnormalizable-element preservation fallback (`RuleEntry(pattern=repr(raw), ...)`).
- `merge_entries`'s `continue` when a key is already in `conflicting_keys` (a 3rd+
  structured entry sharing an already-flagged contended key).

Remaining gaps after the fix are exactly the three multi-line function-signature
continuation-line artifacts the spec said to ignore (now at shifted line numbers ~238-239,
~398-399, ~432-433 after the sentinel additions moved everything down) -- confirmed these
are the same three signatures (`normalize_entry`, `entries_for_tool`,
`normalize_entries_preserving`), not new gaps.

New tests added to `test/unit/test_rule_entry.py` (all with Given/When/Then docstrings,
no `ConfigIsolationMixin` -- confirmed via `test/unit/CLAUDE.md`'s checklist that these
are pure hand-constructed-data unit tests with zero file I/O / config discovery):
- `TestRuleEntryTypeContract`: `test_has_raw_false_for_entry_with_no_raw_recorded`,
  `test_has_raw_true_when_raw_is_explicitly_none`,
  `test_to_source_round_trips_a_genuine_raw_none_value_faithfully` (the direct Part-1
  regression guard, independent of `normalize_entries_preserving`).
- New `TestNormalizeEntriesPreserving` class: `test_non_list_input_returns_empty_tuple`
  (covers the `return ()` gap, parameterized over `None`/dict/int/str),
  `test_unnormalizable_elements_are_preserved_not_dropped` (mixed list of valid string,
  valid structured entry, malformed dict, int, `None`, nested list -- asserts
  length-preservation and per-element identity/pattern for the preservation branch),
  `test_all_elements_round_trip_through_to_source_faithfully` (asserts every element,
  including `None`, reproduces exactly via `to_source()`).
- `TestMergeEntries`: `test_third_entry_sharing_an_already_conflicting_key_is_skipped`
  (three structured entries, same pattern, same key, three different values -- covers
  the `continue` at the "already conflicting" branch; asserts the conflict record still
  names all three entries).

Suite: 1624 baseline + 7 new = 1631, all green throughout every incremental run.
`test/unit/test_architecture.py`: 7/7 green. `uv run ruff check .`: clean (whole
project). `uv run ruff format` run on only the 3 touched files (`rule_entry.py`,
`rule_sort.py`, `test_rule_entry.py`) -- no changes needed (already ruff-clean).
Anti-pattern scan (async/await, threading, local imports) on the touched files: clean.

## Deviations / anything contradicting the spec

None. Note: `git diff`/`git status` on this branch shows many other files as
modified/staged from the prior 10 landed-but-uncommitted increments (e.g. `rule_sort.py`
shows as `MM`); my own edits to `rule_sort.py` were exactly the `is_synthesized` block
described above -- confirmed by re-reading the file before and after, not by relying on
`git diff` (which mixes in the pre-existing uncommitted state on this branch).

## Elapsed time and estimated cost

- Phase 1 (planning: read CLAUDE.md/addenda, read rule_entry.py + rule_sort.py in full,
  grep every construction/inspection site, read test/unit/CLAUDE.md, write task-recall
  memory, baseline test run + baseline coverage run): 08:55 - 08:59, ~4 min.
- Phase 2 (implementation: sentinel + has_raw + to_source fix, rule_sort.py fix, doc
  updates, 7 new tests): 08:59 - 09:01, ~2 min.
- Phase 3 (self-review: full suite reruns after each change, ruff format/check,
  anti-pattern scan, coverage re-run, doc-drift grep sweep): 09:01 - 09:02, ~1 min.
- Phase 4 (this report + IDE handoff): ~1 min.
- Total elapsed: ~8 minutes.
- Estimated cost: small, well-scoped task (2 production files touched, 1 test file
  extended, ~250 lines of diff including comments/docstrings) on Sonnet 5 -- estimated
  well under $1 in API cost for this session.
