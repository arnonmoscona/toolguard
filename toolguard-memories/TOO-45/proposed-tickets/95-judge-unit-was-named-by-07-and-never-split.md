---
title: compound.judge_unit was named as ticket 07's worked example and was never split
tags:
- TOO-45
- proposed-ticket
- maintainability
permalink: toolguard/too-45/proposed-tickets/95-judge-unit-was-named-by-07-and-never-split
---

# `compound.judge_unit` — cyclomatic 20, named by ticket 07, still unsplit

Ticket 07 (the doc-comment sweep) named this function specifically:

> *"**Comments compensating for complexity.** `compound.judge_unit()` is the named example — high cognitive complexity, not helped by verbose commentary explaining it. **Where this is the cause, split the function rather than trimming the comment.**"*

The sweep trimmed comments across the package. **The split never happened.** Measured 2026-08-21: cyclomatic **20**.

## What TOO-45 did to it

Two phase-3 commits touched `compound.py` around it — ticket 79 (the ASK floor inside command substitutions) and ticket 38 (removing the prose-parsing). Ticket 79's work is instructive: it took **eleven agent runs and four review rounds**, and three separate security weakenings were introduced and caught during them. The campaign's own note on that ticket reads:

> *"Every time a new category of verdict was added, something enumerating the old categories silently stopped covering everything."*

**That is what a function of this complexity does to the people changing it.** The `all_parts` extraction fixed the immediate instance; the shape that produced four hand-written enumerations in one function is still there.

## Why this is not urgent

It is on the decision path, it is well covered, and it has just been through the most adversarial review of the campaign. **Splitting it now trades a known-good function for an unknown-good one**, immediately after the reviews that made it known-good.

## Suggested trigger rather than a date

**Do it the next time a new verdict category or fallback kind has to be added.** That is the change this function makes dangerous, it is when the cost is being paid anyway, and it is when the seams will be obvious — the enumerations that have to be taught the new category are the split points.
