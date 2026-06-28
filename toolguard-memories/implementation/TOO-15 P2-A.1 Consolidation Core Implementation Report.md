---
title: TOO-15 P2-A.1 Consolidation Core Implementation Report
type: report
permalink: toolguard/implementation/too-15-p2-a.1-consolidation-core-implementation-report
tags:
- TOO-15
- TOO-11
- toolguard
- consolidation
- implementation-report
---

# TOO-15 P2-A.1 Consolidation Core Implementation Report

## Summary

Implemented the P2-A.1 keystone slice of toolguard's config-maintenance tooling:
a library-only module that proposes probe-verified consolidation of allow rules.

## Files Created

- `toolguard/tools/consolidate.py` -- main new module (291 lines)
- `test/unit/test_tools_consolidate.py` -- 26 BDD-docstring unit tests

## Files Modified

- `toolguard/tools/config_access.py` -- added `with_layer_allow_replaced()` primitive
  and required imports (`MappingProxyType`, `ConfigLayer`)
- `toolguard/tools/redundancy.py` -- refactored `_config_without_allow()` to delegate
  to the new primitive; removed now-unused `MappingProxyType` and `ConfigLayer` imports

## What Was Implemented

### Step 0: Synthetic-config primitive

`with_layer_allow_replaced(config, tool, provenance, removed, added) -> Configuration`
added to `config_access.py`. Uses MappingProxyType content-rebuild technique (same as
the old inline code in redundancy.py). `_config_without_allow` now delegates to this.
Notable refinement: `with_layer_allow_replaced` only modifies the FIRST matching layer
(tracked via `modified` flag), which matches the original redundancy behavior.

### Step 1: Family 1 -- Literal-alternation consolidation

Groups DEFAULT `:*` patterns that are token-count-equal and token-identical except at
exactly ONE position (varying over literal, wildcard-free values). Builds a
`[regex]^...(alt1|alt2|...)\b` replacement. Strict acceptance:
(a) positive probes all get `allow` under both original and consolidated configs
(b) negative probes (synthetic near-miss token) see no broadening
(c) when corpus supplied, `replay().broadened_count == 0`

### Step 2: Family 2 -- Static subsumption elimination

Detects DEFAULT `:*` pattern pairs where one command portion is a conservative
word/path-boundary structural prefix of another (via `_static_prefix_of`). Proposes
the smaller as a pure drop (added_pattern=None). Positive probe + optional corpus guard.

### Data model

```python
@dataclass(frozen=True)
class ConsolidationProposal:
    kind: str
    tool: str
    list_type: str
    layer_provenance: Provenance
    removed_patterns: Tuple[str, ...]
    added_pattern: Optional[str]
    rationale: str
    replay_summary: str
```

## Key Decisions

1. **Duplication avoidance**: `consolidate.py` imports `decide()`, `replay()`,
   `classify_change()`, `parse_pattern()`, `per_layer_rules()`, and
   `with_layer_allow_replaced()` -- zero reimplementation of existing logic.

2. **Alembic landmine**: token-count equality requirement naturally prevents
   cross-arity groupings (5-token vs 4-token patterns can't be grouped).
   The negative-probe check provides a second guard.

3. **re.escape in regex**: `re.escape()` is applied to all alternation tokens
   (e.g. `ls-files` becomes `ls\-files`). Tests check for the escaped form.

4. **Conservative subsumption**: only three boundary cases are claimed:
   `small.startswith(large + " ")`, `small.startswith(large + "/")`, or
   `large.endswith(("/", " ")) and small.startswith(large)`.
   git vs git-annex correctly produces no proposal.

5. **No corpus required**: both families work corpus-free; corpus adds a
   secondary replay gate when available.

## Self-Review Results

- No `async def`, `await`, `threading`, or local imports
- All imports at module level
- `ruff check` passes on all modified/created files
- `uv run python -m py_compile` passes on all files
- No reimplemented matching/replay/config-building logic
- Anti-pattern scan: clean

## Test Results

- Baseline: 1009 tests
- After: 1035 tests (26 new)
- All 1035 pass

## Deviations from Plan

None material. One test assertion adjusted: `test_same_token_count_different_positions_no_broadening`
checks `"positive probes pass" in replay_summary` instead of `"0 broadened"` since
the latter only appears when a corpus is passed; the test does not pass a corpus.

## Phase Timing

- Phase 1 (Planning/review): ~15 min
- Phase 2 (Implementation): ~35 min (split across two sessions due to context compaction)
- Phase 3 (Self-review): ~10 min
- Total: ~60 min

## Estimated Cost

- Session 1: ~$0.40 (heavy reading/planning, partial implementation)
- Session 2 (this session): ~$0.25 (completion + tests + fixes)
- Total: ~$0.65

## Addendum: equivalence-preserving fix (main agent, 2026-06-28)

Main-agent review found family-1 SILENTLY TIGHTENED: the trailing `\b` in the generated regex
dropped prefix-extension commands (consolidating `git diff:*`,`git status:*` ->
`[regex]^git (diff|status)\b` flipped `git difftool`/`git diffstat` from allow->deny), because
DEFAULT `cmd:*` is a PREFIX fnmatch while the `\b` regex is a strict subset. Safe direction but
violated the "strict family-1 = verified-EQUIVALENT" contract, and the probes/gate neither caught
nor disclosed it. (The follow-up subagent dispatch stalled on the monthly spend limit, so the fix
was applied directly in the main agent.)

Changes to `toolguard/tools/consolidate.py`:
- `_build_alternation_regex`: DROP the trailing `\b` -> `[regex]^git (diff|status)` mirrors DEFAULT
  `cmd:*` prefix semantics exactly (equivalence-preserving).
- `_check_family1_safe`: hardened from "no broadened" to **NO CHANGED DECISION** (reject on ANY probe
  whose verdict differs A vs B; corpus reject on broadened OR tightened). Self-protects edge arg-forms.
- New `_generate_extension_probes`: prefix-extension near-misses (`git diff` -> `git diffx`,
  `git difftool`) that expose tightening / exact-vs-prefix widening.
- Family-1 grouping restricted to prefix forms `:*`/`**` (no-colon EXACT excluded: a plain prefix
  regex can't preserve exact semantics without end-anchoring; deferred).
- Dropped now-unused `classify_change` import; reframed module/`propose_consolidations` docstrings
  (real safety basis = no-changed-decision gate + regex subset-or-equal of DEFAULT prefix union,
  NOT token-count).

Tests (`test/unit/test_tools_consolidate.py`): updated `test_added_pattern_is_regex_alternation`
(assert NO `\b`); `test_proposal_passes_with_corpus` (-> "0 changed"); renamed alembic class to
`TestFamily1EquivalenceAndLandmine` and reframed docstrings; ADDED
`test_consolidation_preserves_prefix_extension_commands` (difftool/diffstat stay allow) and
`test_gate_rejects_decision_changing_consolidation` (gate returns False for an over-broad body --
the previously-untested rejection path). Module 28 tests, **full suite 1037 OK, ruff clean**.
Verified functionally: difftool/diffstat/diff-index stay allow, `git push` stays deny.
NOT committed (repo intentionally dirty during TOO-15).
