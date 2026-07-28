---
title: TOO-19 Phase 0a increment 6 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-0a-increment-6-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Implemented TOO-19 Phase 0a increment 6: fixed the confirmed `_config_without_allow`
matching defect (Part 1), implemented `merge_entries()` (Part 2), and audited
`consolidate.py`/`redundancy.py`/`takeover_audit.py`/`installer.py` for the same defect
class (Part 3). Suite went from 1593 to 1606 tests, all green.

## Part 1 -- `_config_without_allow` fix

`toolguard/tools/redundancy.py`: the layer-selection loop used
`if wrapped_target in allow_list:` (a `str in list` check), always `False` against a
structured (`dict`) element, so the removal silently no-opped for structured entries.

Fixed to mirror `config_access.with_layer_rules_replaced`'s exact idiom: normalize each
element via `normalize_entry(element, is_native=layer.is_native)` and compare
`entry.pattern == wrapped_target`. An element that fails to normalize is simply not a
match (never raises). Added a one-line "which of the three RuleEntry comparisons" comment
at the call site (uses `.pattern` -- "same RULE").

**Important correction to the ticket's stated defect narrative** (see "Contradicts spec"
below): empirically verified via throwaway probe scripts that the "false REDUNDANT report"
framing does not reproduce as literally described. The pre-existing
`if config_without is config: continue` guard in `find_corpus_redundant_allows`
intercepts the pure no-op case (single structured occurrence, no duplicate elsewhere) and
SKIPS it rather than reporting it redundant. The real, confirmed consequence at the
`find_redundancy` level is a **coverage gap**: a structured entry could NEVER be detected
as corpus-redundant, genuinely redundant or not, because `_config_without_allow` could
never produce a modified config for one. Tests were written to match this verified
behavior rather than the ticket's literal framing.

### Tests added
- `test/unit/test_tools_consolidate.py::TestConfigWithoutAllowDelegation::test_removes_structured_entry_by_pattern`
  -- unit-level: structured entry is actually removed, returned config is `is not` the input.
- `test/unit/test_tools_redundancy.py::TestCorpusRedundancy::test_structured_entry_detected_as_corpus_redundant_once_fixed`
  -- the positive regression test (RED before fix, GREEN after): a structured entry
  genuinely covered by a broader same-layer rule is now correctly flagged corpus-redundant.
- `test/unit/test_tools_redundancy.py::TestCorpusRedundancy::test_structured_entry_not_falsely_flagged_redundant`
  -- complementary negative test: a structured entry that is the SOLE rule covering a
  corpus command is NOT flagged (proves the fix doesn't overcorrect).

## Part 2 -- `merge_entries()`

Added to `toolguard/rule_entry.py` (kept the module a leaf, per its existing design note).

### `MergeOutcome` shape chosen and why

```python
@dataclass(frozen=True)
class MergeConflict:
    pattern: str
    key: str
    entries: Tuple["RuleEntry", ...]

@dataclass(frozen=True)
class MergeOutcome:
    entries: Tuple["RuleEntry", ...]
    conflicts: Tuple[MergeConflict, ...]

def merge_entries(entries: Sequence["RuleEntry"]) -> MergeOutcome: ...
```

- `MergeConflict` is per contended KEY, not per entry pair -- if 3 entries share a pattern
  and 2 disagree on one key, that's a single conflict record naming every entry in the
  group that carries that key, so a caller sees the whole picture at once rather than
  reconstructing it from N pairwise records.
- `MergeOutcome.entries` uses the SAME flattening for both the "clean merge" and "conflict"
  cases: one synthesized entry per resolved group, or every original structured entry from
  an unresolved (conflicted) group, in original order. This means a caller can always just
  iterate `outcome.entries` to get "what the config should contain" without special-casing
  conflicts, while `outcome.conflicts` is purely diagnostic/alerting.
- Kept as two small frozen dataclasses (not a single flat structure) so the "did anything
  need a human decision" question is a single `bool(outcome.conflicts)` check.

### Case discriminator: `bool(entry.metadata)`, not `entry.is_structured`

Found during TDD (tests initially failed for a subtle, informative reason): `RuleEntry.is_structured`
reflects `isinstance(raw, dict)` -- a round-trip/source-format concern, NOT "has metadata".
A `merge_entries()`-produced union-merge result is itself built with `raw=None` (so
`is_structured` would read `False`) despite carrying real metadata. Using `entry.is_structured`
as the case-1/2/3 discriminator would silently misclassify merge_entries's own output if fed
back into a second pass. Switched to `bool(entry.metadata)`, which is self-consistent across
chained calls. Documented both in the function docstring and an inline comment.

### The three RuleEntry comparisons (naming discipline)

- `.pattern` -- "same RULE" (grouping key in `merge_entries`, and the fix in Part 1).
- `identity()` -- "literally the same entry" (kept as the internal fast-path dedup inside
  `merge_entries`, before the bare/structured/conflict logic runs).
- `merge_entries()` itself -- the new consolidation semantics on top of both.

Extended `RuleEntry.identity()`'s docstring to point at `merge_entries` now that it exists
(previously said "a future merge_entries(), not implemented here").

### Tests added (`test/unit/test_rule_entry.py::TestMergeEntries`, 10 tests)

All 5 ticket-mandated scenarios plus: identity-fast-path dedup, different-patterns-never-merge,
first-appearance group/entry ordering, empty input, and `MergeConflict`'s frozen-dataclass
shape. All carry Given/When/Then docstrings.

## Part 3 -- Audit results

Grepped both files for `layer.content` and `permissions.get(`/`permissions[`:

- `consolidate.py`: **zero** raw-content reads. Confirmed the spot-check claim holds
  file-wide -- every pattern access goes through `per_layer_rules()` -> `LayerRules.allow`
  (wrapper-free, already `normalize_entry`-derived via `Configuration.permission_layers`).
- `redundancy.py`: **exactly one** site, `redundancy.py:258` (was `:257` pre-fix) inside
  `_config_without_allow` -- Part 1's defect, now fixed. No other raw-content site exists.

`takeover_audit.py` (3 raw-content sites: `_is_toolguard_hook_registered` at line 137,
`_get_blanket_allows_in_native` at 200, `_has_any_blanket_allow_in_native` at 233) --
**confirmed no changes needed**. All three are guarded by `if not layer.is_native: continue`
BEFORE reading `permissions`/`allow`, and `normalize_entry` unconditionally rejects `dict`
elements when `is_native=True` (structured entries are a toolguard extension, never valid
in native Claude settings). So these functions only ever see native layers, where a
structured element is out of scope by design; the existing `isinstance(perm, str)` guards
already skip any malformed non-string element safely. Verified: existing tests unchanged,
suite green.

`installer.py` -- **found a same-shaped latent issue, NOT fixed (out of scope), flagging
for a follow-up.** `cmd_seed_self_perms` (line ~697) does
`if pattern in permissions[list_type]:` and, for hard_deny, `if protection.pattern in hard_deny_patterns:`
(line ~706) -- both raw `str in list` membership checks against a list that CAN contain
structured entries. If a user has already structured-ified one of toolguard's own
self-permission or self-integrity hard_deny patterns (added `additionalContext` etc. to
it), the idempotency check would miss the match and append a duplicate bare-string entry.
**Assessed as non-security** (worst case: a harmless duplicate ALLOW/DENY rule, and for the
`permissions` case it's self-healing since `find_static_duplicates` already detects the
resulting bare+structured duplicate pair via `per_layer_rules`). Did not touch
`installer.py` -- this is new work outside this increment's explicit scope, and the ticket
says to report rather than expand scope.

## Contradicts spec

1. **Part 1's "R is reported REDUNDANT" framing does not empirically reproduce** in the
   minimal single-occurrence case -- see the throwaway probe scripts run during
   implementation (not committed; scratchpad only). The pre-existing `config_without is
   config` identity guard in `find_corpus_redundant_allows` intercepts it into a silent
   SKIP instead. The underlying defect and its severity are both real and confirmed (a
   structured entry could never be evaluated for corpus-redundancy at all), just not via
   the exact mechanism described. Tests were written against the verified behavior. Flagged
   here per "anything contradicting this spec."
2. **`installer.py` does NOT need "no changes"** as confidently as the ticket assumed --
   see Part 3 above. Not fixed (scope discipline), but the "confirm... needs no changes"
   framing should be corrected to "confirmed non-critical, follow-up recommended."

## Files touched (no new production files)

- `toolguard/tools/redundancy.py` -- Part 1 fix (~15 net lines + 1 import)
- `toolguard/rule_entry.py` -- Part 2: `MergeConflict`, `MergeOutcome`, `merge_entries()`
  (~190 lines), `identity()` docstring update, typing import additions
- `test/unit/test_tools_consolidate.py` -- +1 regression test
- `test/unit/test_tools_redundancy.py` -- +2 regression tests
- `test/unit/test_rule_entry.py` -- +1 import block, +1 test class (`TestMergeEntries`, 10 tests)

5 touched files total, 0 new production files -- well inside the scope-inflation guard.

## Self-review results

- `uv run ruff format` on touched files: 3 reformatted (whitespace/wrapping only), 2
  unchanged; `uv run ruff check` on touched files: all checks passed.
- Anti-pattern scan (`async def`, `await`, `threading`, `Thread(`, local imports) on both
  touched production files: zero hits.
- `test/unit/test_architecture.py`: 7/7 green, including the leaf-layering test --
  `rule_entry.py` still imports nothing from `toolguard.config`.
- Full suite: `uv run python -m unittest discover -s test -t .` -- 1606 tests, OK (1593
  baseline + 13 new: 3 in Part 1's tests, 10 in Part 2's `TestMergeEntries`).
- Requirements re-verified against the task-recall memory line by line before writing this
  report; every explicit ask (fix, tests, docstring extension, comment discipline, audit,
  no-wiring constraint) is accounted for above.

## Timing / cost estimate

- Phase 1 (planning, reading context/source files): ~10 min, ~$0.35
- Phase 2 (implementation, including TDD red/green cycles, the probe-script investigation
  that corrected Part 1's test design, and the `is_structured` vs `bool(metadata)` fix):
  ~35 min, ~$1.20
- Phase 3 (self-review: ruff, architecture test, full suite, audit greps): ~8 min, ~$0.25
- Phase 4 (this report): ~5 min, ~$0.15
- **Total: ~58 min, ~$1.95** (rough token-based estimate for Sonnet 5, not precise)
