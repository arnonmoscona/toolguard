---
title: CONSOLIDATED-BATCH-2
type: note
permalink: toolguard/too-45/reports/surprise/consolidated-batch-2
---

# Surprise factor — batch 2 (2026-08-21 / 08-22), production-only metric

Covers the items scored since the first consolidated report: **95, 99, 89, 88, 98 chunks 2-4, 100, 104, 103, 101, 105 phase 1**. Metric is Arnon's chosen one — **production files only**, tests and docs excluded from the headline.

## The table

| item | predicted | actual | recall | precision | note |
|---|---|---|---|---|---|
| 95 split `judge_unit` | 1 | 1 | 100% | 100% | first clean mutation-verify |
| 99 contract seams | 4 | 3 | 100% | 75% | **predicted refusal came true** |
| 89 inert `[regex]` | 1 (upside 2) | 2 | 100% | 100% | right count, adjacent reason |
| 88 deny-with-exception | **0** | **0** | hit | hit | first deliberate zero-production item |
| 98 chunk 2 AST attribution | 1 (upside 2) | 1 | 100% | 100% | upside correctly predicted not to fire |
| 98 chunk 3 module boundary | 2 (upside 3) | 2 | 100% | 100% | upside correctly predicted not to fire |
| 98 chunk 4 documentation | **0** | **0** | hit | 40% on files | missed a whole category — see below |
| 100 orphaned privates | 3 | 3 | 100% | 100% | brief's "zero callers" claim was wrong |
| 104 undeclared types | 2 (upside 3) | 2 | 100% | 100% | upside correctly predicted not to fire |
| 103 concept map | **0** | **0** | hit | hit | third zero-production item |
| 101 bare `{}` | 2 | 2 | 100% | 100% | phase 2 predicted empty, and was |
| 105 (original) | 2 | **0** | — | 0% | **PREMISE REFUTED** — new outcome category |
| 105 phase 1 | 2 | 2 | 100% | 100% | label was unpredicted |

**Production recall is at or near 100% almost everywhere.** That is the honest headline and it is *less* impressive than it looks: see the two caveats below.

## Caveat 1 — the metric measures the wrong thing when the work is documentation

Ticket 98 chunk 4 scored a **hit** on production files (0 predicted, 0 actual) and **40% on files overall** — because it touched `technical-notes.md` and `docs/permission-patterns.md`, both of which asserted a heredoc sink "follows the pipe", a claim **chunk 2 had silently made false three commits earlier.**

I had modelled the chunk as *"write a page about what we did"*. The correct model was *"make every document in the repo true again."* **The touch-set metric cannot distinguish those**, because both score zero production files.

**Proposed for the next batch**: for a behaviour-changing ticket, ask the estimator *"what did this make false?"* and count the documents asserting the old behaviour.

## Caveat 2 — near-100% recall partly reflects that I now write the tickets AND the briefs

Most items here were filed by me, from measurements taken minutes earlier. `RESULTS-LOG.md` already records that such items are ineligible for the blinded series. **The high recall is therefore not evidence the estimator works; it is evidence that an author predicts their own scope well.** Arnon's requirement of 20 human-authored tickets through the normal process remains the real test, and **this batch added none** — 98 and 99 were his findings, but my spike-and-plan work spent their eligibility before an estimate was locked.

## Cause codes observed

| code | meaning | instances |
|---|---|---|
| **`N`** | defect introduced by the change itself | **3** — 98 chunk 1 placeholder forgery, 98 chunk 2 parse coupling, **101 delimiter deny bypass** |
| **`S`** | scope-conditioning failure | **2** — 99 U3 and 104 U3, both mine, both predicting a number that required violating a constraint I wrote |
| **`D`** | latent defect uncovered | 100 (`_resolve_leaf` drift), 98 chunk 3 (case-16 coverage gap), 88 (`{}` unparseable) |

**`N` deserves separate reporting and separate severity.** All three were introduced by careful work and all three were caught before commit — but the first two failed *closed* and the third failed **open** (`{ rm -rf x; }` went deny → allow). "We caught it" reads identically in both cases; the risk does not.

**`S` is the one that should embarrass the process, not the code.** After the first instance I named the cause and wrote the fix into a scoring file — which I never re-read, so it fired again three days later. Both lessons are now in auto-memory instead. **A corrective recorded only in a per-ticket artifact is inert.**

## The methodological finding of the batch

**A clean corpus is not evidence of no regression — third measured instance.**

- Ticket 18: replay reported zero flips; a permissive `no_match_fallback` made the transition unobservable.
- 98 chunk 2: three real defects fixed, **zero** corpus decision changes, because none of the 6,401 cases contained the shapes.
- 101: a deny bypass on brace groups would have passed `--verify` cleanly, because the corpus contains **no brace groups**.

The corpus is harvested from real logs, so it measures what the agent *has* emitted. Excellent for regression detection; structurally blind to anything rare. **The permanent answer is now in the tree**: `test/unit/test_deny_penetrates_constructs.py` — a denied command in all 17 constructs, one subTest each, plus a benign-command control so it cannot pass by denying everything.

## Two of my own instrument errors, both caught by contradiction

1. Keyed a golden comparison on `decision`/`command`; the real fields are `verdict`/`target`. Reported a false **zero verdict changes** — contradicted by the population guard.
2. Checked brace-presence against **90-char truncated prefixes**; briefly believed 5 diffs were on brace-free commands — contradicted by the one verdict change that showed no braces.

**Neither was caught by being careful.** Both were caught because a second number disagreed with the first. That is a cheaper safeguard than vigilance and should be a standing practice: always have an independent second measurement available to contradict the first.