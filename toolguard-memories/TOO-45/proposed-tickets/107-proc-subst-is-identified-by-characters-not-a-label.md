---
title: 107-proc-subst-is-identified-by-characters-not-a-label
type: note
permalink: toolguard/too-45/proposed-tickets/107-proc-subst-is-identified-by-characters-not-a-label
---

# 107 - `proc_subst` is the only node identified by its characters rather than by a grammar label

**Found 2026-08-22** while checking whether ticket 105's new comment node could be identified semantically. **Pre-existing; nothing in 105 caused it.**

## The convention, measured

`command_model.node_kind`'s own docstring states the rule: *"Canopy names its generated node classes ``TreeNodeN``, so a node's type carries no meaning and the only identity it has is which grammar labels it exposes."*

AST sweep of `toolguard/parser/command_model.py`:

| identity test | count |
|---|---|
| **by grammar label** (`hasattr(node, "for_kw")`, `"compound_command"`, `"control_op"`, ...) | **31** |
| **by text character** | **2** |

Both text tests are the same function, `_is_proc_subst` (lines 97 and 99):

```python
node.text[0] in ("<", ">")
node.text[1] == "("
```

## Why it is that way, and why that is fixable

The existing comment explains it: `<(...)`, `>(...)`, `subshell`, `brace_group` and both command-substitution forms **all carry a `compound_command` label**, so the label alone cannot separate them and only the leading two characters can.

That is a symptom of the grammar not distinguishing them, not a fact about process substitution. `proc_subst` is its own production in `bash_parser.peg`; giving it a label of its own — as `for_loop` has `for_kw`, `if_stmt` has `if_kw` — would make `hasattr(node, "<label>")` sufficient and let those two character tests go.

## Why it is worth doing, stated honestly

**Not a defect.** No wrong decision, no fail-open, and the two tests are correct for the shapes they were written for. This is convention conformance: **31 of 33 identity tests read a declaration the grammar makes; 2 re-read the characters the grammar already consumed.**

It matters because of what it invites. While reviewing ticket 105 phase 1, the natural way to identify the new comment node was `text.startswith("#")` — and `_is_proc_subst` is the precedent that would have justified it. **One exception is a wart; two is a pattern, and the next person cites the pattern.** Fixing the wart is cheaper than arguing against it each time.

Arnon's framing on 105 applies directly: *"the parser is the absolute foundation of the whole tool. It should lift everything it needs to lift."* A node the consumer recognises by re-reading its characters was not lifted; it is being re-parsed one level up.

## Scope, and the rule that binds it

**Two-phase, per `.claude/rules/bash-grammar.md`.** Phase 1 is a `.peg` label plus canopy regeneration, reviewed alone; phase 2 replaces the two character tests in `command_model.py`.

**Verify with `test/unit/test_deny_penetrates_constructs.py`** — process substitution shares `compound_command` with subshell, brace group and command substitution, so a label change there is exactly the kind of edit that can move a neighbouring construct. That guard exists because ticket 101 did move one.

## Priority

**Low.** Schedule below anything with a live failure mode. It is a two-line cleanup whose value is preventing a third instance, not fixing a second.

---

# REFRAMED 2026-08-23 (Arnon) — the criterion is the PACKAGE BOUNDARY, not correctness

> *"107 is indeed a low priority, and while the check to see whether the first character is '#' is strictly 'wrong'. As far as parsing goes, it's just about the simplest parsing one can think of. So the grammar here does not pass into the higher level a parsing responsibility that is hard to reason about. So as long as such things remain constrained within the parsing package, we can live with it. But even this should not leak outside the parsing package, which should expose a semantic interface to the rest of toolguard. It's tangentially related to a future idea expressed in TOO-69... We have plenty of future work before we do get into subtle things like this."*

**This is a better criterion than the one I filed under, and it changes the ticket.**

I framed it as *31 of 33 identity tests read a declaration; 2 re-read characters* — a consistency argument. The sharper question is **what the parsing package hands outward.** A single-character test is the simplest parsing there is; it passes no hard-to-reason-about parsing responsibility up. What would matter is a *consumer outside* `toolguard/parser/` having to inspect characters to learn what the grammar already knew.

**By that criterion the current state is acceptable**: `_is_proc_subst` is entirely inside `command_model`, and nothing outside the package sniffs text.

**And it means the thing I actually cared about was already achieved elsewhere.** Ticket 105 phase 2 identifies comments by a grammar label (`hasattr(node, "hash")`), so `NodeKind.COMMENT` is part of the package's semantic interface rather than a character test leaking outward. That was the real risk; the `proc_subst` wart is not.

**Disposition: keep filed, priority LOW, and re-read it against the boundary criterion rather than the consistency one.** Related to **TOO-69** (explicit module and package usage boundaries). Not scheduled — Arnon: *"We have plenty of future work before we do get into subtle things like this."*
