---
title: 101-the-grammar-cannot-parse-a-bare-brace-word
type: note
permalink: toolguard/too-45/proposed-tickets/101-the-grammar-cannot-parse-a-bare-brace-word
---

# 101 - the PEG grammar rejects a bare `{}` word, so `find -exec` and `xargs -I{}` always reach ASK

**Found 2026-08-21** while verifying ticket 88's `find` recipe. Not a security hole -- it fails safe -- but it has a real workflow cost in auto mode.

## The defect

`toolguard/parser/bash_parser.peg` has no production matching a bare `{}` word. Measured, isolating the cause rather than guessing:

| command | parses? |
|---|---|
| `echo {}` | **NO** |
| `echo "{}"` | yes |
| `echo '{}'` | yes |
| `python -c "d = {}; print(d)"` | yes |
| `find . -exec echo hi` | yes |
| `find . -exec echo hi +` | yes |
| `find . -exec echo {} \;` | **NO** |
| `find . -exec echo {} +` | **NO** |
| `xargs -I{} echo hi` | **NO** |

**It is the brace word itself, not the `\;` terminator, not `+`, and not `-exec`.** Quoted braces are fine, which matters because it means the common `python -c "... {} ..."` shape is unaffected.

A command that fails to parse becomes undecidable and takes the hardcoded ASK floor.

## Severity: fails safe, but ASK is not free here

Failing to parse yields `ask`, never `allow`, so **this is not a bypass.** The cost is elsewhere:

- **`ask` is enforced under toolguard/takeover, including in auto mode.** So every `find ... -exec ... {}` and every `xargs -I{}` stops an unattended agent, regardless of any allow rule the user wrote.
- A `deny` rule aimed at these commands **also** cannot match, since matching never happens. The ASK floor covers it, but the user's rule is not what is doing the work -- and they are not told that.

## Exposure - measured, and triaged line by line per `.claude/rules/evidence-before-fixing.md`

| corpus | raw hits | probes discarded | **genuine** |
|---|---|---|---|
| **featherhill** | 7 | 6 | **1** |
| toolguard | 12 | 4 | ~8 |
| instagram | 0 | -- | **0** |

**featherhill's six discards are the documented `find` probe cluster** in `toolguard-2026-05-11.md` -- `-exec echo {}` repeated with one token varied, plus an `-execdir` variant. That is a matrix, not work. The single genuine case is `find flowers/test -name "*.py" -exec grep -l "class.*unittest.TestCase" {} \;` on a different date in a different file.

toolguard's four discards are **this campaign's own scratchpad probes** (recognisable by the `.../scratchpad/t77` paths), the self-inflation effect this project has already measured twice.

**Reading**: uncommon but idiomatic, and present in genuine work in both corpora. `xargs -I{}` in particular is the standard spelling; there is no other way to write it.

## Fix direction - the two-phase rule applies, and this is exactly what it is for

`.claude/rules/bash-grammar.md` is mandatory here. **Phase 1 is a `bash_parser.peg` change plus canopy regeneration, reviewed on its own. Phase 2 is any Python.** Do NOT special-case `{}` in `command_extractor.py`; a brace word is a lexical fact and belongs in the grammar.

Likely a one-line addition to whatever production covers bare words. Worth checking at the same time whether other unquoted punctuation words are missing -- `+` alone parses, so the gap may be narrow.

## Before scheduling

Weigh against the ASK-noise argument, not a security argument. If Arnon runs unattended sessions that use `xargs -I{}`, this is a live irritant; if not, it is cosmetic. **It should not be sold as a security fix.**