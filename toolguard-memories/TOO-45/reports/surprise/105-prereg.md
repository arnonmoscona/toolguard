---
title: 105-prereg
type: note
permalink: toolguard/too-45/reports/surprise/105-prereg
---

# Ticket 105 pre-registration - delete _strip_comments

Locked 2026-08-22, after dispatch, before any result seen. Informed estimate -- and a weak one, since I did the measurement myself.

## Production files predicted
1. `toolguard/parser/command_extractor.py` -- exclude `comment` nodes when rebuilding leaf text
2. `toolguard/parser/multiline.py` -- delete `_strip_comments`, its quote scanner, its pipeline step, and update the docstring

**Predicted production count: 2.**

## Test files + docs predicted
`test/unit/test_multiline_bash.py`; a new technical note under `docs/`; `docs/agent-map.md`.

## What must NOT happen
- No `bash_parser.peg` change. The `comment` production already exists. A `.peg` edit here is a process alarm, not a small surprise.
- No corpus diff. The pre-pass strips comments before the grammar today, so moving the work should be neutral. **A diff means the two implementations disagreed somewhere -- a finding, not a golden to regenerate.**

## Named uncertainties
- **U1**: whether trailing-comment trimming in the extractor is genuinely neutral. I predict yes but this is the crux; a corpus diff falsifies it.
- **U2**: whether this repo's `# INTENT:` disclosure convention creates a case I have not thought of. Leading whole-line comments already work; only trailing is at issue.
- **U3**: whether the agent agrees that making `extract_structured`'s pipeline explicit in code is worth doing. I predict it will agree and I have told it NOT to do it here.