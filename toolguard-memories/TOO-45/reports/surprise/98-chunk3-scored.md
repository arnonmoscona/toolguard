---
title: 98-chunk3-scored
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk3-scored
---

# Ticket 98 chunk 3 scored - the module boundary

Commit `4509665`. Informed estimate, ineligible for the blinded series.

## Production files

| predicted | actual |
|---|---|
| `toolguard/parser/multiline.py` | yes |
| `toolguard/parser/command_extractor.py` | yes |
| `toolguard/parser/command_model.py` -- *"possible; I predict untouched"* | **untouched, as predicted** |

**Predicted 2, upside 3. Actual 2. Recall 2/2 = 100%, precision 2/2.** The upside was named and correctly predicted not to fire: `command_extractor.py` needed one existing type imported, not a new accessor.

## Uncertainties

- **U1 MISS.** I predicted `--layers` would object, since the move changes which module imports the IR, and framed it as "the check working". **It did not object** -- both files live in the `parser` package, same `engine` layer, so no cross-layer edge changed. My model of the check was wrong: `--layers` polices edges *between* layers, and this move was entirely *within* one. A prediction about an instrument, wrong about the instrument's granularity.
- **U2 HIT.** The docstring's deviation clause became deletable and was deleted. I verified the result rather than accepting the claim: the module now says structural parsing is the grammar's job and *"hand-rolling any of it in this module is out of bounds"* with no escape hatch following it. Its remaining admission that the quote scanners disagree maps exactly to the three surviving models at lexical steps 2-4, so it is still accurate rather than stale.
- **U3 HIT on the outcome, but MY BRIEF WAS WRONG ON THE FACT.** I predicted the agent would leave the `LeafCommand` re-export and said I would rather it were repointed. It left it -- and corrected me: my brief asserted `tools/mining.py` was "the one real consumer", and a grep found **`compound.py` imports it too**. Repointing one consumer would not make the re-export deletable, so leaving it was right and my preference was based on a false premise.

**That is the fourth time this campaign an implementer has corrected a factual claim in my brief.** The pattern is consistent: I state a *count* or a *sole-consumer* claim from partial reading, and it is wrong in the direction of being too tidy. Same shape as the `DEFAULT_COMMAND_PAYLOAD_KEY` misread and the case-16 "already fixed" claim. **The cheap countermeasure is already in every brief -- "do not take my word for it" -- and it keeps working.**

## Cause `D` - a real coverage gap, found by mutation-verify

Mutation-verify on `_resolve_sink` found **no test caught a deliberate break**. Investigation showed a genuine gap: the mid-pipeline case `python <<HD | bash` -- *the ticket's own case 16* -- had no test pinning which command wins.

**The ticket that fixed case 16 did not leave a test that would catch case 16 regressing.** Chunk 2 corrected the behaviour and verified it by hand and by corpus; neither is a unit test. Added `test_bearer_interpreter_wins_outright_over_pipeline_last_stage`.

Worth carrying to the consolidated report: **mutation-verify has now found a real gap in 3 of the 5 tickets it was run on this session** (97, 98 chunk 1, 98 chunk 3), and found nothing on 95 and 98 chunk 2. It is not ceremony.

## The measurement chunk 3 makes possible

`multiline.py`: **683 lines pre-98 -> 794 after chunk 2 -> 522 now.** The middle number is the one worth keeping: attribution off a parse tree is *more* code than a token scan, and the file only got smaller once that code moved to where it belonged. A reader told only "683 -> 522" would conclude the rewrite was a simplification. It was a relocation.