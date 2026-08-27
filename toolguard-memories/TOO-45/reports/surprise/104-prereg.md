---
title: 104-prereg
type: note
permalink: toolguard/too-45/reports/surprise/104-prereg
---

# Ticket 104 pre-registration - dicts are undeclared types

Locked 2026-08-22, after dispatch, before any result seen. Informed estimate.

## Production files predicted
1. `toolguard/hook.py` -- `parse_hook_input` returns `PreToolUseEvent`; the 8 `hook_data[...]` sites become attribute access
2. `toolguard/claude_code_contract.py` -- **possible**; `PreToolUseEvent` already exists, so I predict it needs no change
3. `tools/architecture_fitness.py` -- new `--undeclared-types` mode

**Predicted production count: 2**, with 3 as the upside if the dataclass needs a field.

## Test files predicted
`test/unit/test_hook.py`, `test/unit/test_hook_eval.py` -- both mock `parse_hook_input` directly, so both must change.

## Named uncertainties
- **U1**: **this is the widest-blast-radius item in the batch** and the reason it was held back once. I predict the test churn exceeds the production churn, which would be the first item in the series where that is true by a wide margin.
- **U2**: how many `--undeclared-types` violations exist package-wide. **I genuinely do not know** -- somewhere between 3 and 30. I have told the agent to report the count and fix only `parse_hook_input`, because fixing them all is Arnon's decision, not a subagent's.
- **U3**: contract KEY imports in `hook.py` were 12 before ticket 99, 6 after. I predict **0-1** after this.