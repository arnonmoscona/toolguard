---
title: TOO-45 surprise factor - ticket 22 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/22-scored
---

# Ticket 22 scored — commit `ba81a64`

**The series' first fully-clean run** (no coordinator appendix in the ticket; return channel held on substance) **and its best result.**

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **298 / 298 = 100%** |
| file recall | 4 / 4 = 100% |
| precision (integrity guard only) | 4 / 5 = 80% |
| **prose-or-structure call** | **CORRECT** — and unleaked |
| concentration set | **correct**, including the relative ordering |

## Per-file — every file predicted, at high confidence

| file | lines | predicted? | confidence |
|---|---|---|---|
| `test/unit/test_tools_redundancy.py` | 192 | **yes** | high |
| `toolguard/tools/redundancy.py` | 57 | **yes** | high |
| `test/unit/test_tools_hierarchy.py` | 43 | **yes** | high |
| `toolguard/tools/hierarchy.py` | 6 | **yes** | high |

One false positive: `test_tools_maintenance.py` (medium) — costs nothing.

The concentration set was right down to the ordering: *"redundancy.py slightly larger, since it carries two of the three open items versus hierarchy's one"* — 57 vs 6.

## FINDING 22 — THE BLINDED ESTIMATOR BEAT THE COORDINATOR ON THE UNLEAKED QUESTION

Both of us answered *prose or structure* independently, sealed, neither having seen the other.

**Mine (`22-prereg.md`): structure.** *"A correct fix is structural, and the touch set therefore reaches `maintenance.py`. A diff confined to `hierarchy.py` and `redundancy.py` is evidence the cheap fix was taken."*

**Its:** *"(a) a reworded message"* — staying inside `hierarchy.py` plus its test, explicitly **not** implying a new field or any change to how `maintenance.py` renders findings.

**It was right. I was wrong.** And the fix is confined to exactly the two modules I nominated as the tell-tale of a shortcut — when it was in fact the complete and correct remaining fix.

**The mechanism of the difference is the finding.** It reasoned from the ticket's own history:

> *"HR1/HR3/HR4 were fixed in the same commit without the ticket describing any new field or data-shape change ... That is strong evidence the surrounding finding structure already carries what's needed."*

Verified: `_intervening_deny_or_ask` landed in `640f86b`, and this change touched **only the note string**.

**I reasoned from a principle** — *prose is output, so the fix must be structural* — **without checking whether the structure already existed.** That is cause `I` (inherited staleness) committed by the coordinator, and it is the same failure that cost ~11h on ticket 18. It cost nothing here only because the implementer measured first.

**It also named its own falsifier in advance** — *"a new field such as `verified: bool` ... rendered from it"* — which is the discipline I was not applying to my own prediction.

## What this says about the instrument

**22 splits cleanly along the leak line, and that is the most useful thing in it:**

- **File set: heavily leaked** — the ticket names `hierarchy.py:400`, `_config_without_allow`, `_normalised_body`, and the RED test. 100% recall is **transcription**, consistent with finding 21.
- **Prose-or-structure: NOT leaked** — the ticket states neither option. Getting it right required inferring, from what a *previous* commit did, what this one would need. **That is foresight, and it is the first clean instance in the series.**

**So the character-of-fix question is worth more per token than the file list**, and should be asked on every remaining item. It was added to this item specifically to test that, and the test came back positive on its first use.

## Cause tally

`0` misses. One false positive. **The only item in the series with a perfect touch set on a diff larger than 3 files.**
