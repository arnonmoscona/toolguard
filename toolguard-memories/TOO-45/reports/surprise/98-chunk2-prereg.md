---
title: 98-chunk2-prereg
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk2-prereg
---

# Ticket 98 chunk 2 pre-registration - attribution from the AST

**Locked 2026-08-21, AFTER dispatch, BEFORE any result was seen.** Same caveat as 95: informed estimate, not a raw one.

**Eligibility: NOT eligible for the blinded series, and this one is not close.** I built three spikes (A/B/C), wrote a chunked implementation plan, and personally probed the case matrix. An estimate from me here is a memory test, not a prediction. Recorded only so the chunk is not a silent gap.

## Production files predicted

1. `toolguard/parser/multiline.py` -- attribution replaced; `_statement_bounds_containing` and `_split_on_unquoted_pipe` deleted.
2. `toolguard/parser/command_extractor.py` -- **possible**, if reaching the IR requires an accessor that does not exist yet. I predict a read-only import rather than an edit.

**Predicted production count: 1, with 2 as the realistic upside.**

## Test files predicted

1. `test/unit/test_multiline_bash.py`
2. Corpus goldens -- **will** change, by design: three cases are being corrected.

## What I expect NOT to move

- No `.peg` grammar change. If one is needed the two-phase rule applies and the agent was told to STOP rather than work around it. A grammar change appearing here is a **failed prediction and a process alarm**, not a small surprise.
- No move into `command_model.py` -- that is chunk 3.

## Named uncertainties

- **U1**: the `<unresolved>` policy. I specified ASK-floor/undecidable. If the agent finds the IR cannot distinguish unattributable from attributable, this chunk gets materially harder.
- **U2**: corpus diff size. I predict exactly three changed decisions. **More than three is the thing to look at**, because it means attribution moved for cases nobody was examining -- the highest-value signal this chunk can produce.
- **U3**: whether deleting `_split_on_unquoted_pipe` orphans callers outside the heredoc path.