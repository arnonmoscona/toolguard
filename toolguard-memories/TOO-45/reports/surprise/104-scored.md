---
title: 104-scored
type: note
permalink: toolguard/too-45/reports/surprise/104-scored
---

# Ticket 104 scored - dicts are undeclared types

Commits `61ecd7b` (hook.py) and `e32d3da` (`--undeclared-types`, shared with 100).

## Production files
| predicted | actual |
|---|---|
| `toolguard/hook.py` | yes |
| `tools/architecture_fitness.py` | yes |
| `claude_code_contract.py` — *"possible; I predict it needs no change"* | **untouched, as predicted** |

**2/2 = 100% recall and precision**, with the upside correctly predicted not to fire: `PreToolUseEvent` already existed from ticket 99 and needed nothing added.

## Test files
Predicted `test_hook.py` **and** `test_hook_eval.py`. Actual: `test_hook.py` only, plus `test_architecture_fitness.py`. **`test_hook_eval.py` never needed touching** — I assumed both mocked `parse_hook_input`; only one did.

## U1 MISS, and it inverted
I predicted *"the test churn exceeds the production churn... the first item in the series where that is true by a wide margin."*

**Measured: production 53 lines, tests 33. Production churn exceeded test churn.** And `hook.py` got **smaller** — replacing dict subscripting with attribute access deletes code rather than adding it.

The irony worth recording: **that prediction was correct for ticket 100 instead**, where tests moved 2.7x production. I attached it to the wrong ticket. The generalisable version is *deletions and repointings are test-heavy; type migrations are production-heavy* — the opposite of what I assumed, because a type migration removes accessor noise at the call site.

## U2 hit
Predicted 3-30 `--undeclared-types` violations, "I genuinely do not know". **Actual 4**, all manually verified as genuine cross-module calls, none fixed per instruction.

## U3 MISS - cause `S` AGAIN, second instance in the same ticket family
Predicted **0-1** surviving contract KEY imports in `hook.py`. **Actual 4.**

All four sit at two sites, and both are **raw-dict validation BEFORE the event is constructed**: a required-fields check on the parsed JSON, and a crash-report echo of whichever fields were present. Raw key names are exactly right there, because no type exists yet.

**The cause is that my brief said "DO NOT add validation to the dataclass", and validation is the thing that needs raw keys.** I wrote the constraint and then predicted a number that required violating it — the identical error as ticket 99's U3, which is also where cause `S` was first named. **Twice now, in the same ticket family, three days apart.** The fix I proposed then ("state the metric as *of the dispatched scope*") did not fire because I never re-read it. That is a lesson about where lessons have to live, not about estimation.

## Unpredicted, favourable
The agent caught a **regex-anchoring bug in its own first draft** of the `to_...dict` exemption — it silently exempted nothing. Self-caught before reporting.