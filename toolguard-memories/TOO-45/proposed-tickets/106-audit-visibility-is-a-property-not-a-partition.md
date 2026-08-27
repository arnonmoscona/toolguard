---
title: 106-audit-visibility-is-a-property-not-a-partition
type: note
permalink: toolguard/too-45/proposed-tickets/106-audit-visibility-is-a-property-not-a-partition
---

# 106 - `CommandUnit` splits one concept into two fields by a REPORTING property

**Filed 2026-08-22 at Arnon's request**, from the concept-map diagnostic in `reports/103-compound-concept-map.md`. He asked for the fix written up as a ticket precisely because I described it and then declined to propose it: *"create #106 describing the proposed fix (which you chose not to propose). I'll review it and decide."*

**Fair. I hedged.** I named the candidate and then wrote "I am NOT proposing a rewrite", which let me have the finding without owning a recommendation. The finding is specific enough to act on, so here it is as a proposal with its costs stated.

## The finding

`CommandUnit` carries two fields for substitutions that must be resolved:

- **`audit_parts`** — substitutions that are themselves foreign inline code. Deny-checked, **and** itemised in the audit breakdown.
- **`deny_check_parts`** — *"every OTHER substitution... minus `text` itself and minus `audit_parts`"*, behaving *"the same as `audit_parts`, but never itemised."*

**They are checked identically.** A `deny` or `ask` in either decides the unit outright, both routed through `_pick_strictest`. The sole difference is whether the entry appears in the audit breakdown and folds into the reason text.

So this is **one concept — substitutions to resolve — partitioned by a reporting property.** The second field's definition is the first field's complement plus "same behaviour, different visibility", which is why no shorter wording for it exists. `CommandUnit`'s docstring runs ~80 lines for 7 fields, and a large share of that is spent explaining how field 6 differs from field 5.

The split propagates into `judge_unit`, which takes **three parallel verdict sequences** — `part_verdicts`, `audit_part_verdicts`, `deny_check_verdicts` — each of which must match the length of its corresponding tuple, each guarded by its own `ValueError`. Three (tuple, verdicts) pairs the caller must keep in lockstep.

## Proposed fix

**Make visibility a property of an element, not a partition between fields.**

One collection of substitutions to resolve, each carrying whether it is itemised in the breakdown — a small frozen dataclass, per this project's stated preference over tuples:

```python
@dataclass(frozen=True)
class Substitution:
    text: str
    itemised: bool   # appears in the audit breakdown and folds into reason text
```

Then `CommandUnit` loses `deny_check_parts`, and `judge_unit` collapses two of its three parallel sequences into one.

**What this buys**, in order of value:

1. The two fields can no longer disagree about what "checked" means, because there is one code path. This project's repeated defect is two shapes that cannot disagree loudly.
2. The paragraph whose only job is explaining the difference between two fields disappears — the compression resistance Arnon flagged goes away because the thing it was describing is gone.
3. `judge_unit`'s signature loses one length-matched pair, and one `ValueError` guard with it.

**What it does NOT buy**: nothing about structure, decidability, policy or combination changes. Those four concepts are cleanly owned already (see the concept map), and `_pick_strictest` in particular is the module's best-factored piece.

## Cost — ESTIMATED, NOT MEASURED

**Stated as an estimate deliberately, because I have not measured it and the ticket should not read as though I had.**

Touched: `CommandUnit`'s definition; `_unit_for`'s construction of it; `judge_unit`'s signature and its `inline_code` branch; whatever in `resolve.py` builds the three verdict sequences; every test that constructs a `CommandUnit` directly.

**Measure before scheduling**, per `.claude/rules/evidence-before-fixing.md`. In particular count the direct `CommandUnit(...)` constructions in tests — that number, not the production diff, is likely to dominate, as it did on ticket 100.

## Alternatives considered

- **Keep the two fields, improve the docstring.** Rejected: the prose is long because the design is split, so this treats the symptom. It is also what the current state already attempts.
- **Merge the two fields and drop the distinction entirely** (itemise everything). Rejected: the distinction is real and load-bearing — an unrelated allowed `$(mktemp -d)` must not change what an all-allow leaf's reason and breakdown show. That requirement is the reason the split exists; the proposal keeps it and moves it.
- **Do nothing.** Legitimate. Nothing here is a defect: no wrong decision, no fail-open, no field evidence. This is comprehensibility work on a module that is correct, and it should be ordered below anything with a live failure mode.

## Reachability / severity

**Zero.** No behaviour changes. This is a readability and drift-resistance proposal, not a bug fix, and it must not be scheduled as though it were one.

---

# DECISION 2026-08-23 (Arnon): NOT DOING IT

> *"I agree about not doing 106, now that I understand it."*

**Closed, and the outcome is the one the concept map was FOR.** `reports/103-compound-concept-map.md` was written as a diagnostic on an explicit bargain: if the map turned out easy to write, ship it and stop; if hard, the difficulty is the refactor spec. It came out hard in exactly one place, that place got named and costed here, and the decision was then made on the evidence — to leave it alone.

**A ticket declined on a clear understanding is a success of the diagnostic, not a wasted one.** The finding stands recorded if the module is ever reopened: `audit_parts` and `deny_check_parts` are checked identically and differ only in audit visibility.
