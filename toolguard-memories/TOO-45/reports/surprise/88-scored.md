---
title: 88-scored
type: note
permalink: toolguard/too-45/reports/surprise/88-scored
---

# Ticket 88 scored - deny-with-exception recipe

Commit `2648423`. Prediction locked in `88-prereg.md` before implementation.

## Production files

| predicted | actual |
|---|---|
| **zero** | **zero** |

**Hit.** Recorded because it is the series' first deliberate zero-production ticket, and it is the case the production-only metric exists to handle: the raw file count (2 committed + 1 uncommittable) would have made this look like ordinary implementation work. It is entirely guidance.

## Files predicted vs actual

| predicted | actual |
|---|---|
| `docs/agent-guides.md` | yes |
| `docs/configuration.md` | yes |
| `.claude/skills/toolguard-security-audit/SKILL.md` | yes -- **but in a different git repo, so not in the commit** |

3/3, with the same cross-repository caveat ticket 89 surfaced: `.claude/` is a symlink into `dot_files`, so that third file is edited but uncommitted and invisible to this repo's history.

## Two unpredicted findings, both from insisting on measuring rather than citing

The ticket body already carried a measured claim -- *"5/5 ordinary invocations permitted; 5/5 dangerous excluded."* I re-verified rather than quoting it, and both surprises came out of that.

**1. My first verification run reported 0/7 ordinary uses permitted.** The recipe appeared to block everything -- the exact failure this ticket exists to correct. **The cause was my own test harness**: I put the deny and the allow in the *same* level, where deny beats allow. The recipe requires the deny at a less-specific level and the allow at a more-specific one, which is the whole mechanism. Correctly levelled: **7/7 ordinary, 6/6 dangerous, 2/2 controls.**

Worth keeping because the failure was *indistinguishable from a broken pattern* by its output alone. A recipe that blocks everything and a harness that blocks everything produce the same table. **The level structure is part of the recipe, not context for it.**

**2. Two of the six "dangerous excluded" results were not excluded by the pattern.** `find ... -exec ... {} \;` and `-ok` came back `ask`, not `deny`, with a grammar parse failure. Isolating the cause -- rather than accepting a passing row -- showed the grammar rejects a **bare `{}` word** anywhere: `echo {}` fails, `echo "{}"` parses, `xargs -I{}` fails. So the `exec|execdir|ok|okdir` terms in the published lookahead are **insurance, not what currently blocks those commands**; the ASK floor is. Filed as ticket **101**, exposure measured and triaged (featherhill 1 genuine of 7, six being the documented probe cluster).

**Both findings share a shape worth naming: a green row that is green for the wrong reason.** The six-of-six exclusion looked like the pattern working. Two of those six would have stayed excluded if the lookahead were deleted entirely. This is the same class as the corpus-replay blind spot recorded earlier -- an instrument reporting a pass that is real but unrelated to what is being tested.

## Cause code

`D` (latent defect uncovered) for the `{}` finding. No `E`/`C`/`P` miss on the file set itself.