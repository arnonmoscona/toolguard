---
title: 105-phase2-prereg
type: note
permalink: toolguard/too-45/reports/surprise/105-phase2-prereg
---

# Ticket 105 phase 2 pre-registration - comment representation and the client choice

Locked 2026-08-22, at dispatch. Informed estimate.

## Production files predicted
1. `toolguard/parser/command_model.py` — `COMMENT` NodeKind, recognised via `hasattr(node, "hash")`
2. `toolguard/parser/command_extractor.py` — represent comment nodes; the client-facing include/discard choice
3. `toolguard/parser/multiline.py` — delete `_strip_comments`, its quote scanner, its pipeline step, and correct the docstring

**Predicted production count: 3.**

## Test files predicted
`test/unit/test_multiline_bash.py`; likely a new test for the client choice; possibly `test_command_extractor_inline_code.py`.

## Named uncertainties
- **U1**: `_attribute_sinks` re-parses text that has not been comment-stripped. The phase-1 implementer flagged it as the likely awkward spot and I agree. **I predict this is where phase 2 either gets ugly or forces a rethink** — and a reported block there is a correct outcome, not a failure.
- **U2**: the shape of the client choice. I deliberately did not specify it; a keyword argument defaulting to today's behaviour is the obvious candidate. **I predict the implementer proposes exactly that**, and I would rather be surprised by something better.
- **U3**: corpus movement. Comment handling moves from the pre-pass into the extractor, so a diff is possible. I predict **zero or very few**, all on commands containing `#`, because the default must preserve today's behaviour. Any diff on a `#`-free command is the alarm.
- **U4 — the one I got wrong last time, restated properly:** *can the consumer act on what the grammar produces without re-deriving it?* Phase 1 needed a label added for exactly this. **I predict no further grammar change is needed** — the label is sufficient — and a request for one is a signal phase 1 was incomplete rather than a phase-2 problem.

## What must NOT happen
- No `text.startswith("#")`. There are 31 label tests and 2 text tests in `command_model`; do not add a third.
- No silent behaviour change: today's behaviour must remain the DEFAULT.
- `test_deny_penetrates_constructs.py` stays green and unedited.