---
title: 103-prereg
type: note
permalink: toolguard/too-45/reports/surprise/103-prereg
---

# Ticket 103 pre-registration - compound.py concept map

Locked 2026-08-22, before implementation.

**This item's output is a JUDGEMENT, not a fix**, so the touch-set metric is close to meaningless for it. Recorded anyway, because the protocol says not to skip an item for being small, and because the *interesting* prediction here is not the file count.

## Production files predicted
**Zero.** Third deliberate zero-production item, after 88 and 98 chunk 4.

## Files predicted
1. One new page under `docs/` or `toolguard-memories/TOO-45/reports/`
2. `docs/agent-map.md` if it lands in `docs/`

## THE PREDICTION THAT MATTERS

The map is a **diagnostic**. Arnon accepted that framing: *"I accept your proposal. Do the writeup on compound.py and we'll see what we do from there."*

**I predict the map will be HARD to write** -- specifically, that the four concepts (structure, decidability, policy, combination) cannot be described without describing each other, and that `CommandUnit` will turn out to own pieces of at least three of them.

The basis is not intuition: ticket 97 already found `kind` answering two questions, and ticket 95's split of `judge_unit` followed `kind` -- so the four helpers sit on a seam that may itself be conflated.

**If I am wrong and the map is easy, the correct outcome is to ship the map and stop.** That is a real possible result, not a face-saving one, and I should not manufacture difficulty to validate the prediction. Recording the prediction here is what makes that check honest.

## Named uncertainties
- **U1**: whether the map should live in `docs/` (durable, drifts) or in `toolguard-memories/` (a working artifact, no drift obligation). I lean memories until Arnon decides what to do with the result.
- **U2**: whether writing it surfaces a defect. Comment-review on this codebase has found ~40 code bugs by judging whether comments were true; a concept map applies the same pressure to a whole module.