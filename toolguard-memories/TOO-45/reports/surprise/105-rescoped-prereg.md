---
title: 105-rescoped-prereg
type: note
permalink: toolguard/too-45/reports/surprise/105-rescoped-prereg
---

# Ticket 105 RE-SCOPED pre-registration - comments belong in the PEG

Locked 2026-08-22, before dispatch. The original 105 prereg is void: its premise was refuted (see `105-scored.md`). This is a fresh estimate for the work Arnon actually approved.

> *"Comments are a real thing and should be properly represented in the PEG and handled with appropriate representation in command_extractor and command_model. Discarding them should be a choice of the clients of these modules via the appropriate functions or arguments, not an intrinsic property of the underlying PEG parser."*

## Production files predicted

**Phase 1 (grammar, reviewed alone):**
1. `toolguard/parser/bash_parser.peg` — make `comment` reachable in command position, not only via `line_ws_char`
2. `toolguard/parser/bash_parser.py` — canopy-regenerated

**Phase 2 (Python):**
3. `toolguard/parser/command_model.py` — a `COMMENT` variant in `NodeKind`
4. `toolguard/parser/command_extractor.py` — represent comment nodes; a client-facing include/discard choice
5. `toolguard/parser/multiline.py` — delete `_strip_comments`, its quote scanner, and its pipeline step

**Predicted production count: 5 across both phases**, 2 in phase 1.

## Test files predicted
`test/unit/test_multiline_bash.py`; whichever module owns grammar cases; likely a new test for the client-facing include/discard option.

## Named uncertainties

- **U1 — THE BIG ONE, and today's near-miss is why.** A grammar change's blast radius is not visible in the corpus. Ticket 101's first attempt removed `{`/`}` from the `delimiter` class, which made the target cases parse **and silently opened a deny bypass on brace groups** — `{ rm -rf /tmp/zz; }` went deny -> allow. The corpus contains no brace-group commands, so `--verify` would have come back clean. **I predict the comment change will also touch more than comments**, because the `word` production is the shared surface, and I want that predicted rather than discovered. `test/unit/test_deny_penetrates_constructs.py` now exists as the standing guard.
- **U2**: whether `_strip_comments` can actually be deleted in phase 2, or whether the leading-whole-line case (`# only a comment` → currently `""` → benign `[]`, but **ParseError** at the grammar) needs handling somewhere. I predict the grammar must accept a comment-only line for the deletion to be safe.
- **U3**: `_attribute_sinks` re-parses text that has not been comment-stripped. I predict this is where phase 2 gets awkward, and it is the part most likely to force a rethink.
- **U4**: whether "discarding is a client choice" lands as a function argument, a separate function, or a node-filter helper. I have no prediction; it is a design call for the implementer to propose.

## What must NOT happen
- No Python in phase 1. No special-casing in the extractor to avoid a grammar change.
- **No widening of a shared character class as a shortcut.** That is exactly what went wrong on 101 today.
- `test_deny_penetrates_constructs.py` must stay green. If a case in it looks wrong, argue it — do not edit it.