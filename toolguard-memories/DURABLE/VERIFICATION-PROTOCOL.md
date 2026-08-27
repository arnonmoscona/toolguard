---
title: VERIFICATION-PROTOCOL
type: note
permalink: toolguard/durable/verification-protocol
---

# Verification protocol for the DURABLE summaries

**Why this exists, and why it cannot be skipped:** these summaries are being written so that ~658 source files can be deleted. **After the deletion, every claim in them becomes unfalsifiable** — the evidence that could refute it will be gone. This is the only window in which verification is possible at all.

A second reason, specific to this project's measured history: the recurring failure here is not an obviously wrong claim. It is **a plausible claim with a real citation attached**, which nobody re-checks. Four separate instances were measured during TOO-45 alone.

## The stance

**Try to REFUTE each claim. Default to REFUTED or UNVERIFIABLE when uncertain.** A summary that survives an adversarial pass is worth keeping; one that survives a sympathetic reading is worth nothing. The verifier must not be the agent that wrote the document.

## Per-claim verdict, one of

| verdict | meaning |
|---|---|
| **CONFIRMED** | the cited source says this, and any number re-measures to the same value |
| **REFUTED** | the source says something different, or the number does not reproduce |
| **MISATTRIBUTED** | the claim is true, but not for the reason or from the source given |
| **UNVERIFIABLE** | no source given, or the source no longer exists, or it cannot be re-measured |
| **TRUE BUT MISLEADING** | literally accurate, and the reader will draw a false conclusion |

That last category is not padding. It is this project's signature defect — *green for the wrong reason* — and a summary is exactly where it survives, because prose has no controls.

## What to check, in priority order

1. **Every number.** Re-measure where the data still exists: counts of files, commits, tickets, occurrences, percentages. A number copied from another summary rather than from the source is **transitive citation** — flag it, because the chain usually has one unmeasured link.
2. **Every citation.** Open the cited file and confirm it contains the claim. A real filename attached to an invented claim is the failure mode this protocol exists for.
3. **Every "measured", "verified", "confirmed".** These words assert a measurement happened. Find it. If there is no record of the measurement, the word is wrong even if the claim is right.
4. **Every generalisation from a single instance.** "This pattern recurs" needs more than one case. Check the count.
5. **Every claim about what the user decided.** Quotes attributed to Arnon must be verbatim from a source. A paraphrase presented as a decision is a fabricated mandate.

## What is NOT a finding

- Prose you would have worded differently.
- A judgement or recommendation, as long as it is *labelled* as one and not dressed as a measurement.
- An omission, unless the omission makes what remains misleading.

## Output

For each document verified, write a companion file listing every claim checked with its verdict, and the evidence for any REFUTED / MISATTRIBUTED / TRUE BUT MISLEADING finding. **Lead with the failures.** A verification report whose headline is "mostly fine" buries the only part anyone needs.

**Report the count of claims checked.** A verifier that checked 6 claims in a 90-line document has not verified it, and the count is the only way to see that.

## Scope

Every document under `toolguard-memories/DURABLE/`, **including `01-claude-failure-modes-and-mitigations.md`, which the coordinator wrote.** It is not exempt; it is the most likely to be believed without checking, and it makes the most numeric claims.