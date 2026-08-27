---
title: 101-prereg
type: note
permalink: toolguard/too-45/reports/surprise/101-prereg
---

# Ticket 101 pre-registration - grammar must accept a bare `{}` word

Locked 2026-08-22, BEFORE dispatch. Arnon gated this on evidence and I measured it before he approved, so the *decision* was evidence-led; the touch-set estimate below is still informed rather than blind.

## Production files predicted

**Phase 1 (grammar, reviewed alone):**
1. `toolguard/parser/bash_parser.peg`
2. `toolguard/parser/bash_parser.py` -- canopy-regenerated, not hand-edited

**Phase 2 (Python), predicted to be EMPTY.** If the grammar accepts a bare `{}` word, the extractor should need no change: `{}` becomes an ordinary argument token like any other.

**Predicted production count: 2, all in phase 1.**

## Test files predicted
`test/unit/test_bash_parser.py` or whichever module owns grammar cases; possibly `test/unit/test_multiline_bash.py`.

## What must NOT happen
- **No special-casing of `{}` in `command_extractor.py`.** That is the hand-rolled-parsing failure this project has a rule against, and it would be the wrong fix even if it worked.
- No corpus regeneration without naming every diff. **Some diffs ARE expected here** -- commands that were undecidable will now decompose, which is the point. Each must be a bare-`{}` command.

## Named uncertainties
- **U1**: whether phase 2 really is empty. I predict yes. If the extractor needs changes, my model of the gap was wrong.
- **U2**: whether other unquoted punctuation words are missing too. `+` alone parses, so I predict the gap is narrow -- but I have not checked `%`, `@`, `^`, `!`.
- **U3**: corpus diffs. I predict a SMALL number, all bare-`{}` commands moving from `ask` to a real decision. **More than a handful, or any diff on a command without `{}`, means the grammar change was broader than intended** -- that is the high-value signal.
- **U4**: canopy regeneration is a dev-only tool. I predict it is installed and works; if it is not, phase 1 is blocked and that is a report, not a workaround.