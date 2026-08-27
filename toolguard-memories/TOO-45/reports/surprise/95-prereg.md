---
title: 95-prereg
type: note
permalink: toolguard/too-45/reports/surprise/95-prereg
---

# Ticket 95 pre-registration - split judge_unit

**Locked 2026-08-21, AFTER dispatch, BEFORE any result was seen.** Stating that plainly: this is not a clean blind estimate. The agent was already running when I wrote this. It is still a valid *prediction*, because I had seen nothing of the outcome -- no file list, no diff, no report -- but it is an **informed estimate against my own brief**, not a raw estimate against the ticket. Scored as such.

**Eligibility**: ticket filed by me, approved by Arnon in code review ("There are several clear case-specific functions there"). Under the rule at the foot of RESULTS-LOG.md this is coordinator-filed, so it does **not** count toward the 20 human-authored tickets. Recorded for the methodology series only.

## Production files predicted

1. `toolguard/compound.py` -- the only one. `judge_unit` and the helpers extracted from it.

**Predicted production count: 1.**

## Test files predicted

1. `test/unit/test_compound.py`

## What I expect NOT to move

- No new module. The extracted helpers are private to `compound.py`; a new file would be over-decomposition, and Arnon flagged skepticism about a second level.
- No `CommandUnit` field added. The brief forbids it explicitly.
- No corpus golden changes -- this is a pure refactor, so `corpus_build.py --verify` should stay clean.

## Named uncertainties

- **U1**: whether mutation-verify finds a coverage gap and pulls in extra tests. Ticket 97 and 98 chunk 1 both did. Probability I would put at ~50%, and it would add test files, not production ones.
- **U2**: whether the extraction reaches beyond `judge_unit` into `resolve_compound_permission`. I predict not, but the two share the verdict vocabulary.