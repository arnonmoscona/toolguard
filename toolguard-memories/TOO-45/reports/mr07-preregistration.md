---
title: TOO-45 MR-07 pre-registration
type: note
permalink: toolguard/too-45/reports/mr07-preregistration
tags:
- task-memory
- TOO-45
- canary
- prereg
---

# MR-07 pre-registration

Written 2026-08-06, **after the three agents were launched and before any of them reported.** Nothing below has been revised.

## Setup

| label | commit | what it is |
|---|---|---|
| A | `532de02` | pre-TOO-45 master |
| B | `708a720` | post-R6 branch |

**Label caveat, recorded as a defect in my own procedure**: A/B here maps to old/new in alphabetical order, which is a guessable convention if it repeats across canaries. It does not affect this pilot — implementers see one tree only and never compare, and the predictor predicts each independently — but **subsequent canaries must randomise the label-to-commit mapping**, and the mapping must be recorded out of the agents' reach.

MR-07 is **neutral ground**: project-root resolution is not code TOO-45 touched.

## Predictions

**1. Footprint.** The blind author predicted one irreducible place — wherever the upward search decides which filenames count as markers. I agree, and I predict **1-2 production files plus 1 test file in each tree**.

**2. Which tree wins: neither.** I predict **no meaningful difference.** Both trees should carry essentially the same project-root module; TOO-45 did not restructure it. If a difference appears, the most likely cause is not the refactor but an accident of which consumers each tree happens to have.

This is deliberately a prediction of a null. A pilot that predicts a null and finds one has validated the pipeline; a pilot that predicts a null and finds a difference has found something I did not expect, on ground where I claimed the refactor had no reach. Either is informative, and the prediction is on record so I cannot claim afterwards to have expected whichever arrives.

**3. The risk that would falsify prediction 2**: the blind author flagged that project root is consumed by log placement, environment-file loading, relative-path anchoring, and operator tooling. If any consumer re-implements the upward walk rather than calling one primitive, the cost rises in whichever tree has the duplicate. I rate this **unlikely in both** — the inventory shows a dedicated `project_root` module — but it is the specific thing that would make this requirement discriminate.

**4. Prediction quality.** I expect the predictor to find this **easy in both trees**, because the module's self-description names the concept directly. If the predictor reports low confidence on either tree, that is a finding about that tree's self-description and is worth more than the implementation result.

**5. What the pilot is actually for.** Validating the process, not measuring the trees. Success is: the predictor could predict from the inventory alone; the implementers worked without contaminating each other; the artefacts are adjudicatable by a blinded judge. **If the process fails, that is the pilot's result, and MR-07's outcome is irrelevant.**

## Scoring rule, fixed in advance

- Two implementations differing by more than one production file, or by more than roughly a factor of two in changed lines, counts as **a difference** and falsifies prediction 2.
- Anything either implementer reports under "surprised me" or "should not have needed touching" is **evidence regardless of the counts**, and is the part of this pilot I expect to be most informative.
- Subjective difficulty reports are recorded but carry the least weight, since they are unblinded self-assessment.
