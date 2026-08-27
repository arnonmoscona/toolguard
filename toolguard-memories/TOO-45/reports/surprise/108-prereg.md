---
title: 108-prereg
type: note
permalink: toolguard/too-45/reports/surprise/108-prereg
---

# Ticket 108 pre-registration - reading a hook event moves to the contract

Locked 2026-08-23, before dispatch. **Arnon-authored** — the observation and the proposed shape are both his, verbatim. But I have now read the function and written the ticket, so this is an informed estimate, not a blind one (see the eligibility rule in RESULTS-LOG.md).

## Production files predicted
1. `toolguard/claude_code_contract.py` — `read_pre_tool_use_event(source=sys.stdin)`
2. `toolguard/hook.py` — thin call; `parse_hook_input` becomes a wrapper or goes away

**Predicted production count: 2.**

## Test files predicted
1. `test/unit/test_hook.py` — roughly a dozen sites stop patching `sys.stdin` and pass `io.StringIO`
2. `test/unit/test_hook_eval.py` — **possible**; it mocks `load_configuration` and may not touch this at all. I predict it is untouched.

## Named uncertainties
- **U1 — the seam question, flagged in the ticket.** Moving the function moves required-field validation into the contract, which reverses an instruction I wrote for ticket 104. I have proposed shape-in-contract / response-in-hook. **I predict the implementer accepts it**; if it argues the other way I want the argument, since I may be rationalising a reversal rather than resolving one.
- **U2**: whether `sys` and `json` imports can drop from `hook.py` entirely. I predict `json` yes, `sys` no — `sys.exit` and stderr handling almost certainly remain.
- **U3**: test churn versus production churn. Ticket 104's lesson was that *type migrations are production-heavy and deletions/repointings are test-heavy*. This is a **move plus a signature change**, so I predict **test-heavy** — roughly a dozen call sites stop patching a global.
- **U4**: whether `EmptyStdinError` follows the function into the contract. I predict **yes** — "the source was empty" is a property of reading, not a policy — and that its name should lose `Stdin`, since the source is now a parameter. **A class named for stdin, taking any source, would be exactly the kind of stale name this campaign keeps finding.**

## What must NOT happen
- No behaviour change: suite stays at **4008 OK**, `corpus_build.py --verify` stays clean.
- The contract must not gain a dependency; it is a stdlib-only foundation leaf.