---
title: 105-scored
type: note
permalink: toolguard/too-45/reports/surprise/105-scored
---

# Ticket 105 scored - REFUTED, a new outcome category

Commit `da09faa` (doc half only). **The code half was never implemented, because the ticket's premise — which I wrote and measured — was false.**

## Production files
| predicted | actual |
|---|---|
| `command_extractor.py`, `multiline.py` (2) | **0** |

**Recall 0/0, precision 0/2.** The metric cannot express what happened here, which is the point of recording it.

## A new outcome the series has not had before: PREMISE REFUTED

Every prior item in the series either landed, or was deferred on measured exposure. This one was **dispatched, investigated, and returned unbuilt because the ticket was wrong** — and the implementer was right to return it.

I claimed the grammar recognised comments and the extractor merely failed to trim them from leaf text. **Measured refutation, which I verified myself:**

| probe | result |
|---|---|
| `comment` rule fires while parsing `echo hi # trailing comment` | **zero times** (memoization cache instrumented by the agent) |
| `echo hi # trailing comment` vs `echo hi zz trailing comment` | **identically-shaped leaves** — `#` is treated exactly like the word `zz` |
| `# whole line only` handed to the grammar | **ParseError** — `_strip_comments` reduces it to `""` first |

So `_strip_comments` is **load-bearing**, not redundant, and deleting it regresses whole-line comments to a crash.

## The estimation lesson is not about the touch set

**I treated "the parse succeeded" as "the parse was correct."** That is the *green for the wrong reason* pattern — which I had written into a memory note **hours earlier the same day**.

The control I needed was one line: compare `#` against an ordinary word in the same position. I *did* run controls that session, and one caught a real bug (passing a string where a tree was wanted, which returned empty for everything). **That is precisely what made the instrument feel validated.** A control that catches one class of error does not validate the instrument for another class — and the passing control made me more confident, not less.

**Arnon suspected the pre-pass was masking a PEG gap and I told him it was not.** He was right. Recording that because the estimator series is meant to measure where confidence outruns evidence, and this is the cleanest instance in it.

## Disposition
Doc half shipped. Code half **re-scoped by Arnon** into grammar work: the PEG must represent comments, `command_model` needs a `COMMENT` node kind, and discarding must become a client choice rather than an intrinsic parser property. Two-phase rule applies. Tracked in the ticket file.