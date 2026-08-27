---
title: Command substitution runs foreign inline code with no ASK floor, and the verdict
  corpus is structurally blind to it
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/79-command-substitution-runs-foreign-code-with-no-ask-floor
---

# `echo $(python -c "import os; ...")` gets no floor

**Found 2026-08-14 by A/B measurement**, driving two trees that differed only in `command_extractor.py`. Not one of the 137 phase-1 reds.

`$( ... )` command substitution containing an interpreter invocation with inline code does not raise the inline foreign-code ASK floor. The code inside the substitution runs.

## The old behaviour was noise, not policy — which is why this surfaced now

Before the unit-5 rewrite, the floor fired on **some** substitutions and not others, and the discriminator was accidental:

| command | old | new |
|---|---|---|
| `PKG=$(uv run python -c ...)` | ASK-floored | not floored |
| `echo $(python -c "import os")` | **not** floored | not floored |

The old detector floored a substitution only when the interpreter token happened to survive a `str.split()` scan of the raw command text. That is a coincidence of spelling, not a rule. The rewrite made behaviour **uniform**, which is an improvement in consistency and a wash in coverage — nothing coherent was lost, because nothing coherent was there. But the gap is now clearly visible and worth closing on purpose.

Closing it is a **new capability**, not a regression fix: the extractor must descend into command substitutions the way it now descends into `if`/`while` conditions. It interacts with ticket 77 (nothing is stripped before matching), because a substitution can also carry a leading assignment.

## The part that matters beyond this ticket: the corpus cannot see this

`test_no_verdict_changed` passed across ~2,500 real commands throughout the unit-5 rewrite, and that reads like strong safety evidence. **It is much weaker than it reads.**

The `realistic` fixture sets `undecidable_fallback = "allow_with_no_warnings"`, so an `inline_code` unit resolves to `allow` with `matched_rule: None` — **the same verdict it would have without any floor at all.** A corpus configured that way is structurally incapable of distinguishing "the floor fired" from "the floor did not exist", so no change to the floor can ever move its verdict count.

This is the third instance of the same family in this campaign — proposed tickets 29, 68 and 73 all record an instrument whose evidence is strongest exactly where it has checked least. **Recommendation: add a corpus tier whose fallback is `ask`, so floor changes are observable at all.** Until then, "no verdict changed" should not be quoted as evidence about the ASK floor, and I have quoted it that way once already.