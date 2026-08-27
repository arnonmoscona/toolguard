---
title: 99-prereg
type: note
permalink: toolguard/too-45/reports/surprise/99-prereg
---

# Ticket 99 pre-registration - contract module semantic seams

**Locked 2026-08-21, before dispatch, AFTER I wrote the plan.** Informed estimate. Ineligible for the blinded series (see the eligibility table in RESULTS-LOG.md): Arnon authored the substance, I measured the target before estimating.

**Scope dispatched: plan items 1, 3 and 4 only.** Item 2 (changing `parse_hook_input`'s return type from `Dict[str, Any]` to a class) is held for Arnon -- it is the wide-blast-radius change and belongs in its own commit and its own decision.

## Production files predicted, for the dispatched scope

1. `toolguard/claude_code_contract.py` -- gains `PreToolUseEvent` and `PreToolUseResponse`.
2. `toolguard/hook.py` -- `create_hook_output` delegates the envelope; 12 key imports drop toward zero.
3. `toolguard/testing/sandbox.py` -- constructs via the class; 4 key imports drop.
4. `toolguard/session_start.py` -- `SessionStartEvent`; `CWD_KEY` import drops.

**Predicted production count: 4.**

## Test files predicted

1. `test/unit/test_hook.py`
2. `test/unit/test_sandbox.py`
3. A new test that the two directions agree -- construct an event, parse it back, assert round-trip. **This is the point of the ticket**: today the parse and the construct are independent hand-translations of one protocol.

## What I expect NOT to move

- `tool_spec.py`, `installer.py`, `takeover_audit.py`, `command_extractor.py` -- these hold contract values as **data**, not as translation. Churning them would be the failure mode, not the goal.
- `constants.py` -- item 5 was **withdrawn** after I misread a derived policy default as an alias re-export.
- No validation in the contract module. Rejecting a malformed event is `hook.py`'s policy call.

## Named uncertainties

- **U1**: whether `--layers` objects to the contract leaf gaining classes. I predict not, but it is the check most likely to speak.
- **U2**: whether `session_start.py`'s single `CWD_KEY` justifies a whole `SessionStartEvent` class, or whether that is ceremony for one field. **I predict the agent will push back on item 4**, and I want that recorded as a prediction rather than discovered as a surprise.
- **U3**: how many of `hook.py`'s 12 key imports actually survive. I predict 0-2.