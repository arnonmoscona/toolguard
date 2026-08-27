---
title: 95-scored
type: note
permalink: toolguard/too-45/reports/surprise/95-scored
---

# Ticket 95 scored - split judge_unit

Commit `b2c6f83`. Scored against the commit, not a working tree.

## Production files - the headline metric

| | |
|---|---|
| predicted | `toolguard/compound.py` (1) |
| actual | `toolguard/compound.py` (1) |
| **production recall** | **1/1 = 100%** |
| **production precision** | **1/1 = 100%** |

## Test files

| | |
|---|---|
| predicted | `test/unit/test_compound.py` |
| actual | **none** |

**Over-predicted by one file.** Cause: I assumed a refactor of this size would need at least a test touch-up. It did not, because the extraction was a verbatim relocation and every existing test addressed `judge_unit` through its unchanged signature. Worth noting as a small systematic bias: *I expect refactors to disturb tests, and a clean relocation does not.*

## Uncertainties, resolved

- **U1** (~50%: mutation-verify finds a coverage gap and pulls in tests) -- **did not fire.** All four helpers were caught by existing tests; two by their named pinning tests. This is the first ticket in the recent run where mutation-verify found nothing, after 97 and 98 chunk 1 both found gaps.
- **U2** (extraction reaches `resolve_compound_permission`) -- **predicted no, correct.**

## Unpredicted outcome, favourable

Complexity landed at **8**, and the largest helper -- the security-sensitive `inline_code` branch, ~145 lines -- came out at **6**. That is the evidence for Arnon's instinct that the second decomposition level was not worth it: it is not a matter of taste, the numbers say the first level was sufficient. Recorded because the *reason* a prediction held is worth as much as the fact that it did.

## Cause code `D` - a latent defect found while verifying, not by the agent

Verifying the commit, I followed a pyright "not accessed" warning on `_resolve_leaf` and found it is **called by roughly 30 tests and by no production code**. It is a single-leaf wrapper around `_unit_for` + `judge_unit`; production does the same work per-unit inside `resolve_compound_permission_detailed` and then combines via `_combine_strictest`.

**Pre-existing at HEAD** (line 768 there), so not attributable to this ticket, and **not counted against this ticket's score.** Filed separately.

**Stated precisely, because the dramatic version is wrong**: those tests are not worthless -- they exercise `_unit_for` and `judge_unit`, which *are* the live production logic. What is orphaned is the thin wrapper, and the real cost is that the tests reach that logic by a route production never takes, skipping the combining step.

**The methodological point**: this came from a pyright warning I nearly dismissed as a transient mid-edit artifact, because three other agents were writing to the tree at the time. Concurrency makes diagnostics noisy, and noisy diagnostics get ignored wholesale. **Check whether a warning is pre-existing at HEAD before attributing it to concurrent work** -- one `git show HEAD:file | grep` settles it.