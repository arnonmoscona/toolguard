---
title: TOO-45 boundary canaries pre-registration
type: note
permalink: toolguard/too-45/reports/boundary-canaries-preregistration
tags:
- task-memory
- TOO-45
- canary
- prereg
---

# Boundary canaries — pre-registration

Written 2026-08-07, **after the five agents were launched and before any of them reported.** Not revised since.

Three canaries, chosen for expected discrimination rather than by the earlier home/neutral stratification. The pilot (MR-07) showed why: if TOO-45's reach stops at the decision path, neutral ground is null by construction and home ground is circular, so the informative requirements are the ones on the **boundary** — where the decision path meets another concern.

Label-to-commit mapping is randomised per canary and held in the session scratchpad, deliberately outside `toolguard-memories/` because agents can read that directory.

## Predictions

**MR-10 — NotebookEdit as a first-class file-path tool. Predicted: near-null, largest absolute footprint of the three.**

TOO-45 introduced an `api` layer and unified the verdict types; it did **not** restructure tool recognition. So I expect both trees to answer "is this a supported tool / a file-path tool / where is its path in the payload" in roughly the same number of places. I predict **2-4 such sites in each tree, within one of each other**, and a total footprint of 4-8 files either side. If a difference appears it should be in *where* the change lands, not how much of it there is.

**MR-12 — number compound sub-command log entries. Predicted: the branch wins, and clearly. This is the one I expect to discriminate.**

Master reconstructs the compound breakdown by regex over reason prose — the defect that left 83% of compound-allow cases under-logged. The branch carries structured sub-verdicts. "Part N of M" needs the **total known at write time**, which is a genuinely new demand rather than the one D1 already fixed, so this is not merely re-testing the repair. I predict master must either buffer results it currently streams or count the parts twice, and that its implementer says so unprompted under "surprised me".

Caveat recorded in advance: this is home ground. A win here is weaker evidence than a win elsewhere, and I will not report it as generalising.

**MR-08 — `TOOLGUARD_LOG_FORMAT`. Predicted: small-to-moderate branch edge.**

Cost is entirely a function of how many places write a resolution entry. TOO-45's work on `hook.py` and the verdict types consolidated some of that. I predict **the branch has fewer write sites**, and that the difference is real but smaller than MR-12's.

## Ranking, on record

Expected discrimination, strongest first: **MR-12 > MR-08 > MR-10**. If MR-10 discriminates most, my model of what this refactor touched is wrong, and that is worth more than a confirmation.

## Meta-prediction

**At least one of the three implementers will surface a pre-existing product defect**, as MR-07 did with the two disagreeing marker tuples. Rate it likely: these requirements probe exactly the seams where duplication hides.

## Scoring, fixed in advance

- A **difference** means: more than one production file apart, or roughly a factor of two in changed lines, or a different count of membership/extraction sites.
- **Implementer prose outweighs counts.** After the proofs that per-location counts cannot compare trees of differing granularity, what an implementer says under "where were you surprised" and "what shouldn't have needed touching" is the better evidence. Counts are context, not verdict.
- Subjective difficulty ratings are recorded but weakest — unblinded self-assessment.
- **A null on all three is a permitted and meaningful outcome**: it would mean the refactor's value is confined to the code it targeted, which is the conclusion I have said all along I would bet on.
