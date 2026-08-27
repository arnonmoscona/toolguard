---
title: CommandUnit.kind decides both whether a leaf is floored and how it is decomposed
tags:
- TOO-45
- proposed-ticket
- architecture
permalink: toolguard/too-45/proposed-tickets/97-unit-kind-answers-two-questions
---

# `unit.kind` answers two questions, and ticket 79 paid for it

**Found 2026-08-21** while diagnosing why ticket 79 was the campaign's worst surprise — 13.8% source-only recall, 370 missed production lines, the second-largest miss in the series.

## The coupling

`CommandUnit.kind` is read in `compound.py` at three branches — `'undecidable'`, `'inline_code'`, `'plain'` — and it decides **two unrelated things**:

1. **whether the ASK floor applies** to this leaf, and
2. **how the leaf is decomposed** for the audit breakdown.

Raising the floor for a leaf therefore reclassifies it from `'plain'` to `'inline_code'`, which **silently changes its decomposition**.

## What that cost

Ticket 79's actual fix — descend into command substitutions and floor foreign code — was small and correct in `command_extractor.py`: **59 lines**. Restoring the audit breakdown that the reclassification collapsed took **357 lines** across `compound.py` and `resolve.py`, and required touching `sub_matches`, which verdict derivation also reads.

**Eleven agent runs, four review rounds, and three security weakenings** — an unoverridable `hard_deny` downgraded to `ask`, an explicit `ask` lost entirely, and a `no_match_fallback` warning silently dropped — **each introduced by the fix for the previous one.** All three were caught before commit, none by the suite.

## The option never priced

**Mark the leaf floored via a separate flag, leaving `kind` alone.**

The extractor **already does this**: `LeafCommand` carries `ask_floor` as its own field alongside the text. That flag is then collapsed into `kind` when the unit is built, at which point one field is carrying two facts.

So the fix is not to invent a mechanism — it is to **stop discarding one that already exists** one layer up. That is this campaign's founding shape, arriving for the fifth time.

## This is "one structure, two questions"

Recorded in this project as having caused two prior defects, one of which **silently downgraded an unoverridable `hard_deny` to `ask` with a green suite**. Ticket 79 is the third, and the most expensive.

## Why it is not urgent

`compound.py` has just been through the campaign's most adversarial review, the current behaviour is correct, and the fix touches the decision path. **Splitting the field now trades a known-good implementation for an unknown-good one immediately after the reviews that made it known-good.**

## The trigger

**Do it the next time a leaf needs a new `kind`, or the next time the floor needs to apply to a leaf shape it does not currently cover.** Either change forces the same collision, at which point the separation pays for itself in the same commit — and the enumerations that must be taught the new case are exactly the split points.

**Related**: ticket 95 (`judge_unit`, complexity 20, in the same file) carries the same trigger for the same reason. Consider doing them together; they are one seam viewed from two directions.

---

# CORRECTED DIAGNOSIS AND PLAN, 2026-08-21 — the separation already exists at the read site

Arnon approved this with: *"This 'kind' naming bothered me before and I expressed this to you. What I didn't catch at the time is this confounding, which validates the 'smell' — although in an indirect way. Fix — but do a detailed plan for this first as it's an opportunity to clean up the abstraction."*

Planning it produced a **sharper and smaller** diagnosis than the one above. The original framing — *"`kind` answers two questions"* — is directionally right and imprecise.

## What is actually there

`CommandUnit` **already carries a second field**, `audits_as_one`, and **`resolve.py` already reads it in preference to `kind`, deliberately**:

```
# unit.audits_as_one (set by _unit_for) rather than unit.kind: a
# ... audits_as_one, so this driver cannot silently under-audit it ...
if unit.audits_as_one:
```

**Somebody already saw this coupling and separated it at the consumption point.** That is half the fix, already done and commented.

## Where it is still collapsed

**At construction.** `_unit_for` sets both from one decision, and the pairing is rigid:

| kind | audits_as_one |
|---|---|
| `undecidable` | True |
| `inline_code` | True |
| `plain` | False |
| `unknown` | False |

So `audits_as_one` is **derivable from `kind`** — which means the two can never disagree, and **the case ticket 79 needed is inexpressible**: a unit that takes the floor's policy *and* still decomposes per-part for the audit.

**That is the whole defect, stated precisely.** Not "one field, two questions" but *"two fields, one of them derived, and the case that needs them to differ is the one that arose."*

## What `kind` still conflates

Three facts are in play; `audits_as_one` owns the third:

1. **which policy applies** — floor / fallback / normal
2. **what `parts` means** — parts to resolve, versus nothing to resolve (`undecidable`/`unknown` carry empty parts)
3. **audit granularity** — `audits_as_one`

`kind` drives 1 **and** 2. Those are genuinely different: *"a floor decided this"* and *"there is nothing here to match a rule against"* are unrelated statements that happen to co-occur today.

## Plan

**Step 1 — make `audits_as_one` a real input, not a derivation.** Have `_unit_for` decide it on its own evidence rather than from `kind`. No behaviour change: today's pairings stay. **This is the whole safety-relevant change**, and it is small.

**Step 2 — verify the newly-expressible case is inert.** Construct a unit with `kind='inline_code', audits_as_one=False` and confirm the driver decomposes per-part while the floor still applies. If any consumer breaks, it is reading `kind` where it means audit granularity — a fifth read site to fix.

**Step 3 — split fact 2 out of `kind`.** Introduce a separate `parts_are_resolvable` (or make empty `parts` the sole signal, if that is already true — check, do not assume). Then `kind` means only *"which policy applies"*, which is what its name suggests.

**Step 4 — then, and only then, split `judge_unit` (ticket 95).** Its four branches are `kind` branches. Splitting them before step 3 cuts along a boundary step 3 dissolves, and the file gets restructured twice.

## Sequencing note — 95 waits for this

Ticket 95 was approved independently, but **`judge_unit`'s case-specific functions are exactly the `kind` cases.** Doing 95 first means splitting along a seam this ticket moves. **Recommend 97 steps 1-3, then 95.**

## Acceptance

The corpus replay is the only real proof of equivalence, and this campaign has shown it must be read with `matched_rule` and not just the decision. Steps 1 and 3 must move **no** verdict and **no** golden.
