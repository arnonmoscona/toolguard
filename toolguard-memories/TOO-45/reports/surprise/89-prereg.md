---
title: 89-prereg
type: note
permalink: toolguard/too-45/reports/surprise/89-prereg
---

# Ticket 89 pre-registration - a word-boundary regex in double-quoted TOML goes inert

**Locked 2026-08-21, before dispatch and BEFORE examining where the check belongs.** State of knowledge at lock time, precisely:

- I had verified the **premise** only: `tomllib` turns `"Bash([regex]\bcurl\b)"` into `Bash([regex]\x08curl\x08)`. Measured, not recalled.
- I had verified that `.claude/skills/toolguard-security-audit/SKILL.md` recommends this shape at lines 367, 370, 376 and 377.
- I had **not** read `config.py`'s validation structure with this ticket in mind, nor looked for where `[regex]` bodies are compiled.

So this is closer to a genuine blind estimate than 95/98/99 were: I measured the *defect*, not the *fix site*. **Eligibility: filed by the ticket-18 round-6 reviewer, not by me** -- the closest thing in this batch to an externally-authored ticket. Counting it as provisionally eligible, flagged for Arnon to rule on.

## Production files predicted

1. `toolguard/config.py` -- a tenth named checker alongside the nine that ticket 94 split out of `validation_issues`. This is where a load-time warning belongs.

**Predicted production count: 1.** Upside 2 if the `[regex]` body is compiled somewhere that also needs to know.

## Test files predicted

1. `test/unit/test_config.py` (or whichever module owns `validation_issues` coverage)

## What I expect NOT to move

- **No change to matching behaviour.** The rule as written genuinely is a backspace regex; toolguard should *warn*, not silently "fix" the user's pattern by guessing they meant `\b`. Rewriting the pattern would be toolguard inventing intent.
- No `[hard_deny]`-specific path -- the check is about the regex body, wherever it appears.

## Named uncertainties

- **U1**: whether the check is "raw control character in a `[regex]` body" (what the ticket proposes, and a **strong** conformance check per the instruments rule) or something broader. I predict the narrow one, because it needs no judgement.
- **U2**: whether the audit **skill** must change too, since it publishes the offending shape. I predict yes, and that it is documentation rather than production -- which matters for the production-only metric Arnon selected.
- **U3**: whether any *existing* rule in this repo's own configs is already inert this way. **If the check finds a live dead rule on Arnon's machine, that is a finding in its own right**, not a test artifact.