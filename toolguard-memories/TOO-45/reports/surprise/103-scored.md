---
title: 103-scored
type: note
permalink: toolguard/too-45/reports/surprise/103-scored
---

# Ticket 103 scored - compound.py concept map

Artifact: `reports/103-compound-concept-map.md`. Follow-up filed as ticket **106** at Arnon's request.

## Production files
| predicted | actual |
|---|---|
| **zero** | **zero** |

Hit. Third deliberate zero-production item, after 88 and 98 chunk 4.

## Files
Predicted one new page plus `docs/agent-map.md` if it landed in `docs/`. Actual: one file in `toolguard-memories/`, **no agent-map entry** — consistent with U1, which leaned toward memories until Arnon decides what to do with the result.

## THE PREDICTION THAT MATTERED - partially right, and the wrong half is instructive

I predicted the map would be **hard to write**, specifically that *"the four concepts cannot be described without describing each other, and `CommandUnit` will turn out to own pieces of at least three of them."*

**Hard: correct. Broad: wrong.** Three of the four named concepts — structure, decidability, policy — are **cleanly owned**, and combination (`_pick_strictest`) is the best-factored thing in the module. The difficulty is real but **localised to a fifth concept I had not named in the prediction at all: audit.**

So the shape of my prediction was wrong in the direction that flatters the prediction: "everything is tangled" is unfalsifiable-ish and would have been scored a hit on the strength of the word "hard". **The specific claim — `CommandUnit` owns pieces of at least three of the four — is FALSE.** It owns structure cleanly and policy cleanly; what it does badly is carry an unnamed audit concern across two fields.

I am scoring this a **miss on the substance and a hit on the headline**, and noting that if I had only recorded "the map will be hard", I would have scored myself a clean hit on a wrong model. **That is an argument for pre-registering the mechanism, not just the outcome.**

## U2 hit
Predicted that writing the map might surface something; it surfaced that `audit_parts` and `deny_check_parts` are checked identically and differ only in reporting — which became ticket 106.

## Process note
Arnon: *"create #106 describing the proposed fix (which you chose not to propose)."* Fair. I described the candidate and then wrote "I am NOT proposing a rewrite", which kept the finding without owning a recommendation. 106 now states it as a proposal with costs, alternatives including do-nothing, and the cost labelled ESTIMATED rather than measured.