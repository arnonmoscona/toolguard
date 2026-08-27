---
title: Ticket 79 — cost assessment and fallback options (coordinator only)
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/measurements/79-cost-assessment
---

# Written 2026-08-21 during the fifth pass, so the decision material exists before it is needed

## What 79 has cost

**Seven agent runs** — one implementation, four repairs, two blinded reviews — roughly **1.8M subagent tokens**. Three separate weakenings introduced and caught:

1. inner commands vanished from the audit breakdown (corpus HARD invariant)
2. **`deny` -> `ask`** — an unoverridable `hard_deny` downgraded when foreign inline code shared the line
3. **`ask` -> `allow`** — under this repo's real `undecidable_fallback` setting

## What 79 buys

**Two commands out of ~26,400 newly ask.** That is the measured gain, and it is the correct number — the floor fires on *content*, so the 981 commands merely containing a substitution are untouched.

The gap is real: foreign inline code running with no ASK floor, and this project's disclosure regime depends on that floor. But the ratio is poor on its face and worth stating plainly rather than defending.

## The causal chain, which is the useful part

**The floor fix alone was small and correct.** `command_extractor.py` only; it raised the floor and gained the 2 commands.

**Everything after came from one consequence**: raising the floor reclassifies a leaf from `kind='plain'` to `kind='inline_code'`, and that **collapses the compound sub-command breakdown**. Restoring the breakdown meant touching `sub_matches` — which is also what verdict derivation reads — and every subsequent weakening followed from that.

So: **one small fix, one structural side effect, three regressions chasing it.**

## Options if the fifth pass does not converge

1. **Continue** — the current re-derivation routes sub-parts through the existing strictest-wins resolver, which should make every decision type work by construction rather than by enumeration. If it holds, this is the right shape and it ends here.
2. **Raise the floor WITHOUT reclassifying the leaf kind.** Mark the leaf as floored via a separate flag, leaving decomposition and `sub_matches` untouched. **This is the option worth pricing before spending another pass** — it would have avoided the entire cascade, since the breakdown collapse is what forced everything else. Unknown whether the floor machinery can act on a flag rather than on `kind`.
3. **Revert 79 entirely**, file the gap as known-and-unfixed with the measurement attached. Defensible: 2 commands, and the shape needs deliberate spelling by an agent that is not adversarial.

## Recommendation

**Option 2 deserves a look before a sixth pass.** The cascade traces to a single design coupling — floor status is expressed by changing the leaf's *kind*, and kind also drives decomposition. Decoupling those is a smaller change than what has been built on top of the coupling.

**Do not present this as a failure of the review process.** Every weakening was caught before commit, two of them by cases the coordinator had not constructed. The process is what makes option 3 survivable.
