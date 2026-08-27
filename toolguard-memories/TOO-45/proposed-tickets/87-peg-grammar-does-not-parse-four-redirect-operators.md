---
title: The PEG grammar does not parse &>, &>>, >| or <>, so those commands never decompose
tags:
- TOO-45
- proposed-ticket
- parser
permalink: toolguard/too-45/proposed-tickets/87-peg-grammar-does-not-parse-four-redirect-operators
---

# Four redirect operators are unknown to the grammar

**Found 2026-08-20** by the agent implementing ticket 78's redirect-tilde fix, as a side observation while probing which redirect forms `bash` expands `~` after. Flagged rather than silently absorbed into that ticket.

`toolguard/parser/bash_parser.peg` does not parse **`&>`, `&>>`, `>|`, or `<>`**. A command using one fails to decompose and lands on **`ask`** — before and after the ticket-78 change, so this is pre-existing and independent of it.

## Severity: LOW — it fails closed

An undecomposable command hits the ASK floor rather than being allowed, which is the safe direction and the designed behaviour for a parse failure. **This is not a bypass.** The cost is a spurious prompt on a legitimate command shape.

## Why it is worth a ticket anyway

- `&>` in particular is common — `cmd &> /dev/null` is an ordinary idiom, so a user with a perfectly good allow rule gets prompted anyway and has no way to tell why.
- It is a **silent** shortfall in the sense that matters here: nothing reports "I could not parse this"; the command simply takes the floor. The user sees an unexplained prompt.
- The grammar is the single source of truth for bash parsing, so the gap belongs there rather than being worked around.

## Procedure — MANDATORY two-phase

`.claude/rules/bash-grammar.md` applies in full: **phase 1 is `bash_parser.peg` plus the canopy regeneration ONLY, reviewed on its own; phase 2 is the consuming Python.** This project has repeatedly implemented grammar changes as Python instead, which is why the rule exists.

## Before scheduling — measure exposure

Per `.claude/rules/evidence-before-fixing.md`, count occurrences of these four operators across the three log corpora (featherhill first) before deciding. A shape that never appears is a defer candidate; `&>` may well appear and the other three may not, in which case the fix is smaller than the ticket title suggests.
