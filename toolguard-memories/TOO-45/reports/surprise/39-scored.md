---
title: TOO-45 surprise factor - ticket 39 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/39-scored
---

# Ticket 39 scored (a rule can be demoted out of every restricting list)

Actual from `git diff --numstat c335e22..7d0646d`. Headline: **line-weighted recall against the final committed diff**.

## Actual — 3 files, 785 changed lines

| file | +/- | lines | predicted? | confidence |
|---|---|---|---|---|
| `test/unit/test_config_write_guard.py` | 513/17 | 530 | yes | high |
| `toolguard/config_write_guard.py` | 210/38 | 248 | yes | high |
| `toolguard/tools/installer.py` | 4/3 | 7 | **no — surprise** | — |

**Line-weighted recall: 778 / 785 = 99.1%.** File recall 2/3. The single surprise is a **7-line comment-only edit** — 0.9% of the diff.

**This is the case line-weighting exists for.** By file count the estimate looks 67% accurate; by review burden it is 99%. Arnon reviews the 7 lines in seconds.

## THE SCOPE PREDICTION IS CONTAMINATED — and by me

The estimator predicted **NARROW**, correctly. **That is not foresight, and recording it as such would be dishonest.**

Its own reasoning names the source: *"matching the ticket amendment's own framing... The amendment states this directly: the fix is 'the same comparison generalised to the ordinary tier', it 'needs no pattern semantics and no matcher', and it explicitly rejects dragging `permissions.py` into the write path."*

**I wrote those words into the ticket.** On 2026-08-20 I measured the defect myself and appended a section titled *"REMAINING DEFECT MEASURED — and the fix shape follows from it"*, which states the narrow conclusion in exactly those terms. The estimator read my answer and repeated it.

### This is systemic, not a one-off, and it affects items not yet run

Measuring a ticket before briefing it has been **the single most productive habit of this campaign** — it closed ticket 57 with no work, corrected ticket 20's diagnosis, grounded 64 and 70. It is also, when appended to the ticket file, **a leak straight into the estimator's only permitted reading.**

**Tickets already carrying my measured conclusions: 20, 39, 57, 64, 70.** Any estimate taken against those after the appendix was written is reading my answer.

### The fix, for the aggregate rather than mid-series

Separate the two artifacts. **Measurements belong in a coordinator-only file the estimator is not given** — the estimator gets the ticket as filed plus the inventory, nothing else. That preserves both the habit and the blinding.

**Not changing it mid-series**, per the rule that scoring definitions hold while results arrive. Recorded so the aggregate can discount the affected items rather than discover the leak afterwards.

## Cost

**Four implementation passes, three review rounds.** Estimated 3h; the round curve ran **3 -> 4 -> 2**, falling after the second, so the round-curve control held rather than firing.

The passes were not churn: each round found a genuinely different way to weaken a permission — into `hard_deny.allow`, into an unrecognised sub-list, alongside a surviving `deny`, and via a broader carve-out. **One conceptual defect with four distinct shapes.** Declaring the ceiling after round 2 is what let round 3 distinguish a real gap (same-string move to `hard_deny.allow`) from the accepted limitation.
