---
title: TOO-45 ticket 98 - plan for the heredoc pre-pass
type: note
tags: [task-memory, TOO-45, architecture, plan]
permalink: toolguard/too-45/reports/98-prepass-plan
---

# Plan: stop hand-rolling the pre-pass four times

Arnon, 2026-08-21: *"we need to use what the grammar already provides. The plan should consider alternative parsing strategies for when you believe that PEG (or specifically canopy) cannot express properly. Whatever the plan is - it needs to produce an easier to reason about construct... Perhaps a state-machine representation would be easier. Not sure."*

## The real problem is not that it is hand-rolled. It is that it is hand-rolled four times.

`multiline.py` contains **four independent quote scanners**:

| scanner | exists for |
|---|---|
| `_join_backslash_continuations` | joining `\`+LF outside single quotes |
| `_strip_comments` | `#`-to-EOL outside quotes |
| `_split_on_unquoted_pipe` | **sink classification only** |
| `_statement_bounds_containing` | **sink classification only** |

And the module's own docstring concedes: *"The quote scanners across steps 2-4 do not agree; each documents its own model."*

**Four models of the same fact, none authoritative.** That is why it resists reasoning, and it is also why its defects have been *disagreements* rather than outright bugs: the missing `&`, the `$(...)`-internal separator, and P4/P5's escaped-apostrophe cases are each one scanner knowing something another does not.

## What is genuinely forced, and what is not

**Forced: heredoc body extraction must precede the grammar.** The terminator is context-sensitive — the delimiter is captured earlier and must match later — which a PEG cannot express without backreferences, and canopy has none. The grammar says so itself: `heredoc_content <- (![\n\r] .)*`, same-line only, with the comment *"The heredoc body is removed by the pre-pass."*

**Not forced: deciding which command owns a heredoc.** `redirection` is part of `simple_command`; after parsing, the AST answers it exactly. Two of the four scanners exist solely to re-derive that.

**So half the hand-rolled parsing deletes itself by asking the grammar.**

## Proposal: an honest lexer, then the grammar

**This is the standard shape for exactly this problem** — heredocs are the classic reason real shells split lexing from parsing — and it is what Arnon's state-machine instinct is pointing at. A PEG is usually scannerless; putting a lexer in front is not a workaround, it is the normal architecture when the input has a context-sensitive layer.

### Step 1 — one scanner, replacing four

A single left-to-right pass emitting **spans annotated with quote state** (`plain` / `single` / `double` / `escaped`), plus line boundaries. One state machine, one model, tested in isolation against a table of cases.

The three surviving lexical steps become **consumers of that stream** rather than independent scanners:

- backslash-continuation join -> join across spans whose state is not `single`
- comment strip -> drop from a `#` span in state `plain` to end of line
- heredoc body lift -> find `<<`/`<<-` spans, take the delimiter span, cut to the terminator line

**Disagreement between steps becomes impossible by construction**, which is the property the current design lacks.

### Step 2 — lift bodies to a side table, provisionally

Replace each heredoc redirection with a sentinel and park the body. **No sink decision yet.** This is purely lexical and needs no statement knowledge.

### Step 3 — parse, then ask the AST for the sink

The owning `simple_command` is the sink. **Delete `_statement_bounds_containing` and `_split_on_unquoted_pipe`.**

### Step 4 — decide per sink, after the parse

Bash-family sink: splice the body back as shell and re-parse that fragment. Foreign sink: keep the sentinel and raise the floor.

**The re-parse is the one real cost of this design** and must be stated up front: splicing a bash body back means parsing again. It is bounded (bodies do not nest heredocs in any observed traffic) but it is not free, and a depth limit belongs in the design rather than being discovered later.

## Alternatives considered

| option | verdict |
|---|---|
| **Extend the grammar to consume bodies** | Not possible. Needs a backreference to a captured delimiter; canopy has none. This is the constraint, and it is real. |
| **Two grammars — a line-structure grammar, then the command grammar** | Plausible but worse: a second `.peg` is a second thing to keep in step with the first, and the campaign's recurring defect is exactly two artifacts drifting. |
| **Keep the pre-pass, unify only the quote model** | The cheap half. Fixes the disagreement class but leaves two scanners re-deriving what the grammar knows. **A valid fallback if step 3 proves too invasive** — and it is the part that carries most of the reasoning benefit. |
| **Hand-written recursive-descent for the whole thing** | Rejected. Replaces a rule ("all bash parsing goes through the grammar") with a bigger exception. |

## Sequencing, and the honest recommendation

**Steps 1 and 2 are separable from 3 and 4, and carry most of the clarity win.** If the plan has to be cut, cut after step 2: four inconsistent scanners become one, `_statement_bounds_containing` survives but now consumes a shared model instead of inventing its own.

**Do not attempt this as a refactor-in-place.** The corpus replay is the only real proof of equivalence, read with `matched_rule` and not just the decision — and the two known bypasses (`&`, and the `$(...)`-internal separator) become explicit regression cases.

## Open question for the planning discussion

**Is the sentinel still needed after step 3?** Today `__HEREDOC_TO_<sink>__` exists so the sink survives into the parse. If the sink is read from the AST afterwards, the sentinel may only need to be an opaque placeholder — which would remove an undeclared literal contract that currently spans three files.
