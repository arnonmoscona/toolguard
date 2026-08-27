---
title: Consolidation replays the whole corpus once per candidate, pushing users onto the unverified path
tags:
- TOO-45
- proposed-ticket
- performance
permalink: toolguard/too-45/proposed-tickets/93-consolidation-corpus-replay-runs-once-per-candidate
---

# The corpus replay is per-candidate, and the cost defeats the fix that introduced it

**Found 2026-08-21** during the review of ticket 20a, which wired the corpus into `propose_consolidations` so its safety gates would actually check something.

Before 20a, `run_maintenance` passed `corpus=None`, so the gates did **zero** replays. Every candidate now triggers a full corpus replay — two `decide()` calls per entry per candidate.

## Measured

Against **this repo's real config**, `propose_consolidations` for `Bash` alone:

| corpus | time |
|---|---|
| `None` (what HEAD passed) | 0.03s |
| 500 real entries | 2.20s |

Synthetic, 9-proposal config: 0.07s (no corpus) -> 6.49s (1k) -> 32.68s (5k). **Linear in corpus size, multiplied by candidate count.**

This repo's real corpus is **61,208 entries** at `max_age_days=None`; 14,072 at 7 days; 6,144 at 1 day. Extrapolating the real-config figure puts the full corpus at roughly **4-5 minutes for `Bash` alone**, on top of corpus work that was already slow — a `--corpus --max-age-days 1` baseline run exceeded **600s** before this change.

## Why this is a correctness problem, not just a slow tool

**The cost pushes users onto exactly the path 20a exists to warn about.**

`skills/toolguard-maintenance/passes/1-gather-and-target.md` already passes `--corpus` only if the user asks, and runs `--apply --format json` without it regardless. Making `--corpus` slower entrenches that default. On the no-corpus path every consolidation is `UNVERIFIED` — proposals gated by synthetic probes alone, on the one analyzer whose output `--apply --write` enacts into the user's permission config.

So the second-order effect is that **the verification 20a added is the thing users will now most reliably skip.** A safety check nobody can afford to run is a safety check that does not exist.

## Fix direction

Hoist the replay: one per `(tool, config_b)` rather than one per candidate, or memoize on `config_b`. The candidates within a tool share most of their work.

**This changes control flow in the gate path, so it wants its own review** — which is why it was deliberately kept out of 20a's repair round rather than folded in.

**Check before implementing**: whether `config_b` is genuinely identical across candidates or merely similar. Memoizing on a key that is not actually the same configuration would silently reuse a verdict from a different proposal — a far worse defect than the slowness, and precisely the shape this campaign keeps finding.

## Related

- Ticket **20a** — introduced the corpus wiring and the `SafetyResult` three-state.
- The sibling observation that **safety evidence is strongest exactly when it is emptiest**: `replay()` does not filter by tool, so corpus size counts entries that can never affect the verdict. Being fixed in 20a's repair round; it also means any per-tool hoist should filter first, which would shrink the replay set as a side effect.
