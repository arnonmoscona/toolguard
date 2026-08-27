---
title: TOO-45 surprise factor - ticket 20 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/20-prereg
---

# Pre-registration, proposed ticket 20 (consolidation can escalate `ask` to `allow`)

Written **before** the briefing is regenerated and before the estimator runs. Headline: **line-weighted recall against the final committed diff**.

## THE TICKET'S OWN DIAGNOSIS IS WRONG, and that is recorded before any estimate

The amendment says the defect is that `consolidate.py:597` *"still gates on `broadened_count` alone."* **Measured 2026-08-20, that is not the defect.**

`replay.py:10` defines broadened as *"B is looser (deny -> ask, deny -> allow, **ask -> allow**)"* — so `ask -> allow`, the ticket's headline escalation, **is** classified correctly and the gate **does** catch it when a corpus is supplied.

The real hole is coverage, at `consolidate.py:594-605`:

```python
if corpus:
    diff = replay(corpus, config, config_b)
    if diff.broadened_count > 0:
        return False, ...
    evidence = "... 0 broadened"
else:
    evidence = f"{len(probes)} positive probes pass; no corpus"
return True, evidence
```

**With no corpus there is no broadening check at all, and the function returns `True`.**

## What this means for the measurement

**The estimator will be given the ticket, which contains a wrong diagnosis.** That is deliberate and it is the interesting part: this is a controlled instance of cause **`I` (inherited staleness)**, the category added after ticket 18. Two outcomes, both informative:

- **The estimate follows the ticket** and predicts a touch set around the `broadened_count` classification -> confirms that an estimator faithfully reproduces a bad input, as 18's did, and that `I` is a real and recurring error mode rather than a one-off.
- **The estimate reasons past the ticket** to the coverage question -> evidence that a good estimator does more than transcribe, which no item in the series has yet shown on a *wrong* input.

**Recorded now so neither outcome can be claimed as expected afterwards.**

## The design question, which is genuinely open

The evidence string is scrupulously honest — it literally says `no corpus` — while the boolean the caller branches on is `True`. **The fact is in the prose and not in the value**, which is precisely the project's own "prose is output, not a data structure" defect, occurring inside a safety gate.

Three shapes, differing by an order of magnitude in touch set:

1. **Refuse without a corpus** — one branch, one test. Safest; may make the tool unusable on a fresh install with no logs.
2. **Return a third state** (`safe` / `unsafe` / `unverified`) — changes the function's contract and reaches every caller that branches on it.
3. **Keep `True`, require the caller to surface "no corpus"** — pushes the change into the reporting tier.

The estimator is not told which. **Shape 2 is the one that fits the project's own rule**, and also the one that spreads furthest — so a correct scope call here is worth more than the file list.

## Falsifiable, locked now

**`_check_family1_safe` (`consolidate.py:324`) has not been read.** If it carries the same no-corpus branch, the touch set doubles and a fix touching only `_check_family2_safe` is incomplete. **Predicted: it does.** If the implementation touches only one of the two, that is a finding regardless of what the estimator said.

## Ordering discipline

The estimator writes to `20-estimate-predictions.md` and `20-estimate-uncertainties.md` and returns only `DONE`. **Two items have already been contaminated by a summary attached to that return value (05, 19)** — if it happens again, mark 20 contaminated rather than scoring it.

---

## THIS EXPERIMENT IS ALREADY DEAD — recorded 2026-08-20, before the estimator ran

The design above was: give the estimator a ticket whose **diagnosis is wrong**, and see whether it transcribes the error (confirming cause `I`) or reasons past it. That was to be the series' only controlled test of `I`.

**It cannot run, because I corrected the ticket.** On 2026-08-20 I measured the defect and appended a section to `20-consolidation-safety-claims-are-false.md` titled *"MEASURED — the gate has a hole the amendment does not name"*, which states plainly that `broadened_count` is **not** the defect and that the real hole is the no-corpus branch returning `True`.

The estimator's only permitted reading now contains the right answer. **There is no wrong input left to test against.**

### The same act, two opposite effects

Measuring before briefing has been this campaign's highest-yield habit — it closed ticket 57 with zero work and grounded 39, 64 and 70. **Appending the result to the ticket file is what destroys the measurement**, and it took destroying a purpose-built experiment to make that visible.

Ticket 39's estimate was contaminated the same way and I noticed only while scoring it. Here I am noticing before the estimator runs, which is the only improvement.

### Disposition

**Score 20 for touch set only.** The scope and diagnosis predictions are void — the answer was in the file. **Do not present 20 as evidence about cause `I` in the aggregate.**

The `I`-cause question now has only its two natural instances — ticket 18 (cost ~11h) and ticket 74 (cost nothing, because the implementer ran the test). Two points, no control, and that is the honest state of it.

---

## ADDENDUM 2026-08-21 — ticket decomposed AFTER this design, scoring basis locked before the estimator runs

Ticket 20 has been split into **20a** (safety gates: three-state result, family 2's missing `tightened_count`, corpus wired into `propose_consolidations`), **20b** (static subsumption soundness and its false rationale string), and **20c** (`RA1`, the dry-run diff carrying unrequested normalisation).

The estimator is still given **ticket 20 as filed, whole** — it is not told about the split.

**Scoring basis, locked now:** line-weighted recall against the **union of the 20a and 20b commits**. **20c is descoped -> cause `X`**, not counted as a miss. Recording this before the estimate exists so the boundary cannot be drawn afterwards to flatter the result.

**One prereg prediction already resolved, before the estimator ran** (so it is mine, not its): `_check_family1_safe` was predicted to carry the same no-corpus branch. **It does.** But family 1 checks `broadened_count or tightened_count` while family 2 checks only `broadened_count`, so the two gates are wrong in *different* ways — the shared defect is *safe-when-unverifiable*, not the missing tightening check. The prediction was right; its stated reason was half wrong.

## RETURN CHANNEL HELD - 2026-08-21, first clean run after two leaks

Item 20's estimator returned **exactly `DONE`**, nothing else. Both files written (127 and 114 lines), neither opened by the coordinator.

Items 05 and 19 both leaked a summary through the return value and had to be discarded. The instruction those runs were given said, in effect, *"write to files and return only a token"* - and the RESULTS-LOG's conclusion at the time was that **"an instruction is not a mechanism"**.

**That conclusion now looks too strong.** The difference here was not a mechanism - it was still only an instruction. What changed was that the instruction **named the failure, its history, and its consequence**: that two prior items were discarded, that the reader must stay ignorant until the work is independently complete, and explicitly that *obeying the file-writing half does not compensate for a summary in the reply*. The earlier wording stated the rule; this one stated why breaking it destroys something.

**One clean run is not proof** - N=1 against two failures, and the model may simply have differed. But it is the cheapest possible intervention and it is worth carrying for the rest of the series, then reporting in the aggregate as *"leaked 2 of N under weak wording, 0 of M under wording that names the consequence."*

This also mirrors the campaign's own recurring finding in the codebase - a value that means two things, and prose beside it that nobody reads. Here the fix was to make the prose say what the violation costs, which is the same move as putting the fact in the value: **make the important thing impossible to skim past.**
