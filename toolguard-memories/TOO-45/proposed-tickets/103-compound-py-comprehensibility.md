---
title: 103-compound-py-comprehensibility
type: note
permalink: toolguard/too-45/proposed-tickets/103-compound-py-comprehensibility
---

# 103 - compound.py is hard to follow, and a doc would postpone the question

**Arnon, 2026-08-21**: *"compound.py became a bit hard to read and understand. At the root - it solves a rather convoluted problem... We can fix that through a document on the side, or we may be able to fix it via a cleaner abstraction of the compound notions involved. Just the amount of comments that strongly resisted compression is evidence that a lot is going on there."*

## Where I agree, and where I want to push back

**Agreed on the symptom and the evidence.** Comments that resist compression are a real signal, and it is his own rule: *"where comments cluster is a refactoring signal."*

**I want to challenge the diagnosis that the problem is intrinsically convoluted.** There is direct evidence pointing the other way: **ticket 97 found `CommandUnit.kind` was answering two different questions** -- which policy applies, and whether there is anything to resolve. That is not intrinsic complexity. That is one name carrying two concepts, and it is the same "one structure, two questions" defect this campaign has now found repeatedly.

Four concepts appear to be interleaved through one pipeline:

| concept | question it answers |
|---|---|
| **structure** | what is this text made of -- leaves, segments, substitutions |
| **decidability** | can we reason about it at all |
| **policy** | what floor or rule applies to it |
| **combination** | how do several verdicts merge into one |

`judge_unit` was cyclomatic 20 before ticket 95 split it, and the split was along `kind` -- which means the split followed a name that was itself conflated. It is now four helpers, but they are four helpers over a seam that may be in the wrong place.

## Proposal: use the document as a DIAGNOSTIC, not as a substitute

Rather than choosing between "write a doc" and "refactor", write **a concept map first** -- one page naming these concepts, their relationships, and which type owns each. Then read the result:

- **If the map is easy to write**, the abstraction already exists and only the code obscures it. Ship the map; no refactor needed. Cheap outcome.
- **If the map is hard to write** -- if concepts keep needing to be described in terms of each other -- that difficulty **is** the refactor specification, and it names precisely which concepts are conflated.

This costs one page either way and cannot produce a wrong answer. A flow document, by contrast, describes the code as it is and therefore locks in whatever conflation exists -- and drifts.

**Not scheduled.** Arnon: *"It's probably an issue we need to tackle another day."*