---
title: 98-chunk3-prereg
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk3-prereg
---

# Ticket 98 chunk 3 pre-registration - the module boundary

**Locked 2026-08-21, before dispatch.** Informed estimate; ineligible for the blinded series.

Chunk 3 moves AST attribution and sentinel rewriting out of `multiline.py` into `command_extractor.py` / `command_model.py`, leaving `multiline.py` with only lexical work: line endings, backslash joins, the blind lift, comment strip, whitespace.

## Production files predicted

1. `toolguard/parser/multiline.py` -- loses the attribution code
2. `toolguard/parser/command_extractor.py` -- gains it
3. `toolguard/parser/command_model.py` -- **possible**; I predict the attribution lands in `command_extractor` and `command_model` is untouched

**Predicted production count: 2**, with 3 as the upside.

## Test files predicted

1. `test/unit/test_multiline_bash.py` -- imports move
2. Possibly a new `test/unit/test_command_extractor*.py` addition

## What must NOT happen

- **No behaviour change.** `corpus_build.py --verify` must stay clean and `test_no_verdict_changed` must report 0. This is a pure move; any diff at all means it was not.
- No new re-exports to preserve import paths. That is the trap this ticket family has now hit twice (85c, and the two I removed in chunk 2) -- a re-export destroys the import edge that makes the move meaningful. Callers should be repointed.

## Named uncertainties

- **U1**: `--layers` will likely speak, since this changes which module imports the IR. **That is the check working**; the answer is a layer-map entry, not an exemption. I predict it fires.
- **U2**: whether `multiline.py`'s docstring claim that *"structural parsing is the grammar's job"* can finally drop its deviation clause. I predict yes, and that is the readable evidence the move succeeded.
- **U3**: whether the `LeafCommand` re-export in `multiline.py` -- the one real consumer being `tools/mining.py` -- should be repointed at `command_extractor` as part of this. I predict the agent will leave it and I would rather it were repointed.