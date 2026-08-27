---
title: claude_code_contract is a bag of constants, not a boundary - the crossing functions never moved
tags:
- TOO-45
- proposed-ticket
- architecture
permalink: toolguard/too-45/proposed-tickets/99-the-contract-module-is-constants-not-a-boundary
---

# The contract module holds the vocabulary but not the translation

**Arnon, 2026-08-21, reviewing ticket 85:**

> *"`claude_code_contract.py` is basically only constants. I am not sure that this is the right organization. for instance in hook.py you have `create_hook_output()` which actually constructs the whole output - building a dict that is later converted to json - all that seems like a semantic seam that converts toolguard-specific state into an outside contract consumable. So this kind of function really should belong in the contract module. Same holds for parts of `_run_eval_mode()`. And `parse_hook_input()` which returns a dict, not only expresses the input contract but instead of returning a well structured class - it makes a less clear and less maintainable dict."*

> *"The current implementation of the contract ends up causing multiple imports of individual keys whereas a clean implementation would cause you to import classes, semantic structures, and semantic functions (any plausible mix)."*

## This is a gap in ticket 85's execution, not a new requirement

Arnon's original instruction for 85 said: *"all stand-alone functions whose sole purpose is dealing with the external contract(s) should move there too."*

That was applied to `payload_key()` and then never revisited. Chunk A was scoped to field names; chunk B looked only at `tool_spec`/`constants`; chunk C moved a fetched-spec constant. **The functions that actually cross the boundary were never considered.**

## Why "a module of constants" is the weaker abstraction

A constants module makes every caller **assemble the contract itself**. `hook.py` imports eleven individual keys and builds the response dict by hand. The import edge then means *"this module mentions a key"*.

A module of **structures and functions** means a caller hands over toolguard state and receives a contract-shaped object. The edge means *"this module talks to Claude Code"* — which is what makes it worth having, and it is a stronger version of Arnon's own argument for the module:

> *"the whole function would end up directly referencing the contract but not expressing it. Just that dependency alone is useful for static analysis and review purposes."*

**As built, `hook.py` still expresses the contract** — it just spells it with imported names. That is the thing the ticket set out to stop.

## The three named sites

1. **`create_hook_output()`** — builds the response dict that becomes the JSON Claude Code reads. **This is the semantic seam**: toolguard state in, contract-consumable out. It is the clearest case in the codebase.
2. **`parse_hook_input()`** — returns a **dict**. It expresses the input contract *and* hands every caller an untyped mapping to index by key. It should return a structured class, so the payload's shape is stated once and checked, rather than restated at each access.
3. **Parts of `_run_eval_mode()`** — the portion that renders a decision into contract form.

## The test to apply, and the trap

**Does this function exist to translate between toolguard's world and Claude Code's?** If yes, it belongs in the contract module — regardless of whether it also touches toolguard types, because a translator necessarily touches both sides.

**The trap is the mirror of ticket 85's**: there, the risk was moving too much (a function that *mentions* the contract). Here the risk is moving too little by applying that same guard to a function whose *purpose* is the crossing. `create_hook_output()` reads toolguard's `RuntimeVerdict` — that does not disqualify it, it is what a seam looks like.

## Scope note

`parse_hook_input()` returning a class rather than a dict is **the biggest single change here** and touches every caller that indexes the payload. It is worth doing — an untyped dict at the system's input boundary is where a contract change arrives silently — but it should be **its own chunk**, after the two output-side moves, which are smaller and self-contained.

## Not urgent

Nothing is broken; the constants are correct and dated. This is about whether the module earns the architectural claim made for it. **Do it before the next Claude Code contract change**, since that is when a real boundary pays for itself and a bag of constants does not.

---

# THE GENERAL RULE, and the triage it produces

Arnon, 2026-08-21:

> *"basically anywhere that imports the keys from the contract module is suspect and should be looked at with the guidance being 'what is the semantic seam here?'"*

**That turns the import list into a to-do list.** Every importer of a bare key is a candidate seam — but not all of them are one, and the distinction is worth drawing before the work starts.

## Every importer today, triaged

| module | imports | verdict |
|---|---|---|
| **`hook.py`** | **12 keys** | **SEAM — the largest.** The whole PreToolUse request/response cycle: `parse_hook_input()` reading it, `create_hook_output()` writing it |
| **`testing/sandbox.py`** | 4 keys | **SEAM, and the INVERSE direction** — it *constructs* an event Claude Code would send. "Build me a hook event" belongs beside "read a hook event" |
| **`session_start.py`** | `CWD_KEY` | **SEAM** — `_parse_session_start_input()` is a second input parser with the same shape as `parse_hook_input()`, for a different event |
| `tools/installer.py` | 2 event names | **legitimate.** It *names* events to register toolguard for. Naming is not translating |
| `tools/takeover_audit.py` | `PRE_TOOL_USE_EVENT` | **legitimate**, same reason — it probes a project's hook registration |
| `tool_spec.py` | 2 payload keys | **legitimate.** The registry is a data table mapping a tool to its payload key; the keys are its values |
| `parser/command_extractor.py` | `STRIPPED_WRAPPERS` | **legitimate.** A matching rule consumed as data |
| `constants.py` | 1 payload key | **NEITHER — delete the indirection.** `DEFAULT_COMMAND_PAYLOAD_KEY = _COMMAND_PAYLOAD_KEY` is a pure alias re-export. It is not a seam, and it hides the real edge from every consumer that imports it |

## What the triage says

**Three genuine seams**, and they are the same two operations in both directions: *read a Claude Code event* (`hook.py`, `session_start.py`) and *write one* (`hook.py`, `sandbox.py`).

**`sandbox.py` is the one I would have missed.** It builds a synthetic PreToolUse event for testing, which is the contract in the *outbound* direction — and a contract module that can only parse, not construct, is half a boundary. It is also the best possible consumer to design against, because a test harness that can build a valid event is proof the structure is usable.

**Four legitimate uses**, and the distinction that makes them legitimate: **naming an event, or holding a key as a data value, is not translating between two worlds.** `installer.py` writing `"PreToolUse"` into a settings file is not converting toolguard state into a contract consumable; it is spelling a name.

**One case that is neither** — `constants.py`'s alias — and it is worth naming because it is the opposite failure. It does not translate *and* it does not hold data; it forwards a name, which means every consumer importing `DEFAULT_COMMAND_PAYLOAD_KEY` has an edge to `constants` and none to the contract. **That is the re-export trap from ticket 85 chunk C, still in the tree.**

## The sharpened test

Not *"does this import a contract key?"* but:

**Does this function convert between toolguard's representation and Claude Code's?** Reading a payload into toolguard's own types, or rendering toolguard's decision into Claude Code's response shape — those are seams. Spelling a name, or storing a key as a table value, is not.
