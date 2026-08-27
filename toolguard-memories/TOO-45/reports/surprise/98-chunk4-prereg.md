---
title: 98-chunk4-prereg
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk4-prereg
---

# Ticket 98 chunk 4 pre-registration - the documentation page

**Locked 2026-08-21, before implementation.** Informed estimate; ineligible for the blinded series.

Arnon's requirement: a docs page carrying the motivation, what is genuinely forced, the **rejected alternatives with reasons**, and a **reader's guide**.

## Production files predicted

**Zero.** Documentation only. Second deliberate zero-production ticket in the series, after 88.

## Files predicted

1. `docs/` -- one new page (name TBD; likely `heredoc-handling.md` or similar)
2. `docs/agent-map.md` -- **summarises every other doc and has no other mechanism keeping it in sync**, so a new page must be added there or it goes stale silently. The project CLAUDE.md names this as the most likely thing to rot.

**Predicted count: 2.** I expect the agent-map entry to be the one that gets forgotten, and I am pre-registering that prediction.

## Content that must be right, and one thing that must NOT be written

- **The scanner count is 4 -> 3, not 4 -> 1.** Measured in `98-scanner-count-measured.md`. The flattering version is available and false. The honest framing is that the two scanners deciding a *security-relevant* question were replaced by the grammar, while two doing lexical bookkeeping remain.
- **The file got bigger**, 683 -> 794 lines after chunk 2. Take the final figure after chunk 3, which moves attribution out.
- **What is genuinely forced**: heredoc body extraction must precede the grammar, because the terminator is context-sensitive -- it depends on a delimiter captured earlier -- and a PEG has no backreferences. canopy has none. This is the load-bearing justification for the whole pre-pass existing, and it is the part a future reader will most want.
- **Rejected alternatives, with reasons**: extending the grammar to handle heredocs (impossible, per the above); a second line-scoped grammar (spike B -- elegant, but a second generated artifact to keep in step, and it still guesses); full recursive descent (a bigger exception than the rule it replaces).
- **Case 17 is the case that separated the spikes** -- `if true; then cat <<HD`. A and B both answer `then` confidently; only C answers unresolved. That is the concrete reason C was chosen, and it belongs in the page.

## Named uncertainties

- **U1**: whether `docs/agent-map.md` gets updated. I predict it will be missed unless the brief names it explicitly, so the brief will name it.
- **U2**: whether the page ends up too long. This project's comment rules are strict about volume, and a design-rationale page is exactly where a "long is thorough" failure lands. I predict the first draft will be too long and will need cutting.