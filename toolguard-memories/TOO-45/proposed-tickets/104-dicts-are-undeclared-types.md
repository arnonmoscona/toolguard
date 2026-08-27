---
title: 104-dicts-are-undeclared-types
type: note
permalink: toolguard/too-45/proposed-tickets/104-dicts-are-undeclared-types
---

# 104 - the repeating literal-string problem is really under-modelling, and it is checkable

**Arnon, 2026-08-21**: *"There are repeated literal strings that should have been constants. We had a whole ticket just to clean up this pattern, and in every new module it comes up again. E.g. `log_dir`, `extended_syntax`... But the problem is probably deeper - there is prevalent use of dicts where there should be proper modeling. So the problem is not so much the string literals but the under-modeling pattern overall."*

**He is right, and the reason it recurs is that every previous fix treated the symptom.**

## The mechanism

**A dict crossing a module boundary is a type nobody declared.** Every `d["key"]` at the far end is a field access on that undeclared type. So:

- the key must be spelled correctly at every site, with nothing checking it
- the set of keys is not discoverable -- there is no definition to read
- adding or removing a key is invisible to static analysis
- the literals proliferate **because there is no type to hang them on**

Naming the literals as constants makes the spelling safe and leaves the modelling gap untouched. That is why the cleanup ticket did not stop it recurring, and why it will recur again in the next new module.

## Measured, 2026-08-21

- `hook_data` is subscripted or `.get()`-ed at **8 sites** in `hook.py` (`TOOL_NAME_KEY`, `TOOL_INPUT_KEY`, `CWD_KEY`, `TRANSCRIPT_PATH_KEY`, `PERMISSION_MODE_KEY`). All flow from `parse_hook_input()` returning `Dict[str, Any]`.
- `"log_dir"` as a literal: **10 sites**. `"extended_syntax"`: **4 sites**.

**`parse_hook_input()` is the clearest instance and is already identified**: it belongs to the contract seam, not to `hook.py`, and should return a `PreToolUseEvent` -- the class ticket 99 already added and which `testing/sandbox.py` already uses for the inverse direction. Ticket 99 item 2 is exactly this and was deliberately held back for its blast radius.

## What makes this different from the previous cleanup: it can be CHECKED

Per `.claude/rules/evidence-before-fixing.md`, an instrument must name the declaration it tests against. **This one has a declaration: the return annotation.**

Proposed `architecture_fitness.py --undeclared-types`: flag any **public** function annotated `-> Dict[str, Any]` (or returning an un-annotated dict) whose result crosses a module boundary. It never judges whether a dataclass is the right shape -- only that a type was declared where one is owed. That puts it in the **strong** column with `--layers` completeness, not with the heuristics.

Known exemptions to state up front, not discover: JSON serialisation boundaries where a dict IS the wire format (`to_json_dict()` legitimately returns one), and genuinely open-ended mappings such as a parsed TOML table.

**This is the version worth doing.** A third literals-cleanup pass would buy another few months.