---
title: 108-parse-hook-input-belongs-to-the-contract
type: note
permalink: toolguard/too-45/proposed-tickets/108-parse-hook-input-belongs-to-the-contract
---

# 108 - reading a hook event belongs to the contract, and should take a source

**Arnon, 2026-08-23**: *"hook.parse_hook_input() looks like part of the contract. Also, it uses sys.stdin directly, which is less testable. It should be better to have a function in the contract that takes a source that defaults to sys.stdin."*

Both halves are right and they are the same fix.

## Current state

`toolguard/hook.py:parse_hook_input()` reads `sys.stdin` directly, JSON-decodes it, checks three required fields, and returns a `PreToolUseEvent` — the dataclass that already lives in `claude_code_contract`. So the *shape* is already in the contract and only the *reading* is not.

Hard-wiring `sys.stdin` means every test of it patches a module global rather than passing an input. `test/unit/test_hook.py` does exactly that at roughly a dozen call sites.

## Proposed

A contract-side function taking a source that defaults to `sys.stdin`:

```python
def read_pre_tool_use_event(source: TextIO = sys.stdin) -> PreToolUseEvent
```

`hook.py` keeps a thin call. Tests pass `io.StringIO(...)` instead of patching.

## The seam question this raises — FLAGGED, not silently decided

`parse_hook_input`'s own docstring says: *"Validating that the required fields are present is this module's policy call (the contract only describes shape)."* And ticket 104's brief said explicitly: **"DO NOT add validation to the dataclass. Describing what Claude Code sends is the contract's job; rejecting a malformed event is hook.py's policy call."**

Moving the function moves that validation with it, which looks like a reversal.

**Proposed resolution, which preserves the original distinction rather than abandoning it:**

- **The contract RAISES on a missing required field.** That is not policy — an event with no `tool_name` is not a `PreToolUseEvent`; it is a shape violation, and the contract is what defines the shape.
- **`hook.py` decides what the raise MEANS**: crash-deny, what to log, what exit code. That is the policy, and it stays.

So: shape in the contract, response in the hook. If Arnon disagrees, the alternative is for the contract to parse leniently and `hook.py` to validate — but then the contract can return an object that does not satisfy its own documented shape, which seems worse.

## Scope
`claude_code_contract.py` (the new function), `hook.py` (thin call, `sys`/`json` imports likely drop), `test/unit/test_hook.py` (pass a source instead of patching), possibly `test_hook_eval.py`.

**Behaviour-preserving.** `corpus_build.py --verify` must stay clean and the suite must stay at 4008.