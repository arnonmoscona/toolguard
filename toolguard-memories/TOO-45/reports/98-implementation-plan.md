---
title: TOO-45 ticket 98 - chunked implementation plan
type: note
tags: [task-memory, TOO-45, architecture, plan]
permalink: toolguard/too-45/reports/98-implementation-plan
---

# Ticket 98 — implementation plan

Direction chosen: **spike C**, with Arnon's three constraints — the sentinel stays, the AST-based work moves out of `multiline.py`, and the documentation is part of the ticket.

Chunked because his review takeaway on this campaign was: *"each commit involved few production files and was pretty focused. Confirms need to chunk tickets to meaningful chunks or phases that each is easy to review and each gets committed separately."*

## The invariant every chunk must hold

**No golden moves except for cases 15 and 17.** Case 16 was already fixed by the ticket-19 repair; 15 (P4 escaped apostrophe) and 17 (control-structure keyword) are behaviour *changes*, and each moved golden needs justifying individually. The corpus replay is the only real proof of equivalence, read with `matched_rule` and not just the decision.

---

## Chunk 1 — the blind lift, behind the existing interface

Replace the heredoc lift with the spike's line-scanning version, emitting an **internal placeholder** and a body side-table. Sink classification stays exactly where it is for now, reading the placeholder instead of the raw text.

**Nothing moves between modules. No behaviour changes.** One quote scanner replaces the lift's share of the current four.

**Why first**: it is the only chunk that is purely additive-then-substitutive, and it de-risks everything after it by proving the lift is faithful before anything depends on it.

**Acceptance**: corpus clean, no golden moves, the 17 cases unchanged in outcome.

---

## Chunk 2 — attribution from the AST, and the sentinel rewritten

Parse the cleaned text, walk the IR to find the `simple_command` owning each placeholder, and **rewrite the placeholder into `__HEREDOC_TO_<sink>__`**.

**This is where cases 15, 16 and 17 change**, and where `_statement_bounds_containing` and `_split_on_unquoted_pipe` are deleted.

**`<unresolved>` needs its policy decided here, and the default must not be a guess.** Recommendation: treat an unattributable heredoc as **undecidable**, which routes it to the ASK floor — the behaviour toolguard already has for a segment it cannot decompose. That is the whole reason spike C was chosen over A and B, so it must not quietly become a fallback to "last token wins".

**Acceptance**: 17/17 cases (case 16 CORRECTED 2026-08-21 -- this plan claimed the ticket-19 repair had already fixed it; a live probe against chunk 1 shows `python <<HD | bash` emits NO sentinel and leaks the body line `import os` into the leaf list as if it were a command, so it is chunk 2's to fix); every moved golden justified; a test that an unattributable heredoc reaches `ask` rather than any concrete sink.

---

## Chunk 3 — the module boundary

Move AST attribution and sentinel rewriting out of `multiline.py` into `command_extractor.py` / `command_model.py`.

`multiline.py` keeps only lexical work: line endings, backslash joins, the blind lift, comment strip, whitespace. Its docstring's claim that *"structural parsing is the grammar's job"* becomes true without a deviation clause.

**Pure move, no behaviour change.** The seam is *"text in; cleaned text plus a body side-table out"*.

**Watch**: `--layers` may object, since this changes which module imports the IR. That is the check working; give it a layer-map entry rather than an exemption.

---

## Chunk 4 — the documentation, per Arnon

A page under `docs/` carrying:

- **the motivation** — four quote scanners that the module's own docstring admitted disagreed, and the defects that came from the disagreement
- **what is genuinely forced** — body extraction must precede the grammar, because the terminator is context-sensitive and a PEG has no backreferences
- **the rejected alternatives, with reasons**: extend the grammar (impossible); a second line-scoped grammar (spike B — elegant, but a second artifact to keep in step, and it still guesses); full recursive descent (a bigger exception than the rule it replaces)
- **why the sentinel exists** — it carries a fact into rule matching that no regex over the raw command can reach, because the body is gone by then
- **a reader's guide** to the resulting code

Referenced from the module docstring and from `technical-notes.md`.

**The rejected alternatives are the most valuable part and the part that usually goes unwritten.** Without them the next reader re-proposes spike B. The spikes exist so that conversation happens once.

---

## What could go wrong, stated up front

**The second parse.** A bash-family sink means splicing the body back and parsing again. Bounded at 0-1 nesting in observed traffic, same shape as the existing `bash -c` recursion — but the bound belongs in the code as a limit, not in a comment as an assumption.

**IR coupling.** Chunk 2 makes sink attribution depend on the IR's shape, so a grammar change can move it. That is the correct dependency — it is structural work depending on the structure — but it is new, and the two-phase grammar rule now applies to a second consumer.

**Chunk 2 is the only risky one.** Chunks 1, 3 and 4 are a substitution, a move, and prose. If the ticket has to stop early, stopping after chunk 1 still leaves the codebase better than it found it.
