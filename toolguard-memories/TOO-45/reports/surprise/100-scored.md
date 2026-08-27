---
title: 100-scored
type: note
permalink: toolguard/too-45/reports/surprise/100-scored
---

# Ticket 100 scored - two orphaned module-private functions

Commits `b63257c` (deletions + test repointing) and `e32d3da` (`--orphans`, shared with 104).

## Production files
| predicted | actual |
|---|---|
| `toolguard/compound.py` | yes |
| `toolguard/config.py` | yes |
| `tools/architecture_fitness.py` | yes |

**3/3 = 100% recall and precision.**

## Test files
Predicted `test_compound.py`, `test_compound_resolve_seam.py`, "possibly a test for the new check". Actual: those two, plus `test_architecture_fitness.py` (the "possibly", so a hit), **plus `test_configuration.py` — unpredicted.**

That miss is **my brief's fault, not the estimate's**: I wrote that `_discover_rules_files` had zero callers. **Five tests called it directly.** The agent proved `_discover_rules_files_multi((rules_dir,))` equivalent for a single directory before repointing them. Fourth time this campaign an implementer has corrected a factual claim in my brief, and the same shape every time: a *count* or *sole-consumer* claim, wrong in the tidy direction.

## Uncertainties
- **U1 — half right, and the half I got wrong is the interesting one.** I predicted at least one test's expectations would legitimately change once `_combine_strictest` entered the path. **No test's expectations changed** — but a real behavioural difference WAS found: the single-unit path now carries a real `fallback_kind` on the deny floor and a real `fallback_warning` on the allow floor, where the deleted wrapper left both at defaults. **No test asserted on either field, which is exactly why the drift survived.** I predicted the right phenomenon and the wrong symptom.
- **U2 hit**: `--orphans` reports zero.
- **U3 hit**: I predicted a collision with the concurrent 104 agent in the shared tool file. One "file modified since read" occurred and was reapplied cleanly.

## Churn, measured
Tests **177** lines changed; production **65**. **Test churn 2.7x production churn** — the deletion was small and the repointing was the work.