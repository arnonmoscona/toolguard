---
title: 105-phase2-scored
type: note
permalink: toolguard/too-45/reports/surprise/105-phase2-scored
---

# Ticket 105 phase 2 scored - comment representation and the client choice

Commit `2ca11b2`. Scored against `105-phase2-prereg.md`.

## Production files
| predicted | actual |
|---|---|
| `command_model.py` | yes |
| `command_extractor.py` | yes |
| `multiline.py` | yes |

**3/3 = 100% recall and precision.**

## Uncertainties

- **U1 MISS — the predicted awkward spot never materialised.** I predicted `_attribute_sinks`, which re-parses text that has not been comment-stripped, was *"where phase 2 either gets ugly or forces a rethink"*, and the phase-1 implementer had flagged the same. It did neither: the implementer re-examined it and reported it needed no change. **Two independent people predicted the same trouble spot and both were wrong.** Worth recording, because agreement between predictors felt like corroboration and was not evidence.
- **U2 HIT.** Predicted the client choice would land as *"a keyword argument defaulting to today's behaviour"*. It did: `extract_structured(..., include_comments=False)`.
- **U3 HIT, with the number tighter than predicted.** Predicted "zero or very few, all on commands containing `#`". Actual: **exactly 2**, both `#`-bearing, both diagnostic text only, `test_no_verdict_changed` green throughout. The alarm condition — a diff on a `#`-free command — did not fire.
- **U4 HIT.** Predicted no further grammar change would be needed and that a request for one would mean phase 1 was incomplete. No `.peg` or generated-parser file was touched.

## The result worth keeping

**17 shapes, byte-identical end to end**, measured against `63644a7` with `PYTHONPATH` pinned and provenance printed — including this repo's own `# INTENT:` disclosure block, which is the shape that would actually hurt if it broke. Comment handling moved from a hand-rolled quote scanner into the grammar and the extractor, and **nothing observable changed**.

That is the strongest available evidence for a foundation refactor, and notably it is *not* the corpus — the corpus contributed 2 diagnostic diffs and would not have caught a regression in most of those 17 shapes.

## What this ticket closed, across its whole arc

`multiline.py` began this ticket family admitting in its own docstring that **four quote scanners disagreed**. Now:

| scanner | fate |
|---|---|
| `_statement_bounds_containing` | deleted (98 chunk 2 — attribution moved to the parse tree) |
| `_split_on_unquoted_pipe` | deleted (98 chunk 2) |
| `_strip_comments` | **deleted here** |
| continuation joining | remains — the only one left |

**Four disagreeing models became one**, and the module is down to four lexical steps. The original 105 premise — that `_strip_comments` was redundant — was false; the corrected one, that the grammar should own comments, was Arnon's, and it is what actually retired the scanner.

## Cause codes
None. No `N` (nothing introduced), no `D` (nothing latent uncovered). **The first item in several to produce neither** — which, after three `N`s in this campaign, is worth noting as the shape of a clean change rather than passing over in silence.