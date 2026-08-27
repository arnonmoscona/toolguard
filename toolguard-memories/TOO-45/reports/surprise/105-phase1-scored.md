---
title: 105-phase1-scored
type: note
permalink: toolguard/too-45/reports/surprise/105-phase1-scored
---

# Ticket 105 phase 1 scored - comments become real nodes

Commit `63644a7`. Scored against `105-rescoped-prereg.md`.

## Production files
| predicted (phase 1) | actual |
|---|---|
| `bash_parser.peg` | yes |
| `bash_parser.py` (regenerated) | yes |

**2/2 = 100%.**

## U1 MISS — in the favourable direction, and the reason matters

I predicted, citing the `{}` near-miss the day before: *"I predict the comment change will also touch more than comments, because the `word` production is the shared surface."*

**It did not.** Measured construct-by-construct against `03d922c`: **exactly one behaviour changed** — a comment-only line, `ParseError -> []`. Brace group, subshell, pipeline, and-list, command substitution, `${VAR}`, `xargs -I{}`, if/then, redirect, quoted and double-quoted `#`, `#` mid-word, plain commands: all byte-identical.

**Why it did not fire is the useful part.** The implementer generated a simpler first design — `compound_command:statement?` in place — and *rejected it* after finding it silently accepted a previously-invalid leading `;` AND broke `tree.compound_command` for every command, confirmed by reading the generated `TreeNode1` class rather than assuming. So the blast radius I predicted was real and was avoided by someone checking, not by luck. **A prediction that fails because the work was careful is a good outcome; it should not be recorded as a bad prediction.**

## U2 HIT
Predicted the grammar would need to accept a comment-only line before `_strip_comments` could be deleted safely. Confirmed: `program <- comment_only_program / command_program` is exactly that, and without it `# only a comment` raises ParseError.

## UNPREDICTED, and it is the substantive contribution: the LABEL

I predicted nothing about how a consumer would *identify* a comment node. The first implementation produced a comment node that was reachable only by reading its text, because canopy nodes carry identity solely through grammar labels — `node_kind` uses `hasattr` 31 times and text-character tests exactly twice.

Without a label, phase 2 would have been pushed into `text.startswith("#")` — **the parsing this ticket exists to remove, relocated one level up.** Fixed with `comment <- hash:"#" body:(![\n] .)*`.

**The estimate had no line for "can the consumer identify what the grammar produced?"** That is a general gap: a grammar change is not done when the text parses; it is done when the *consumer* can act on the result without re-deriving it. Worth adding to the prereg template for any future `.peg` work.

Also produced item **107** — `_is_proc_subst` is the one pre-existing instance of the same pattern.

## Process finding, and I had it wrong

Two grammar agents went 90+ minutes without a write. I diagnosed "the agent went quiet" and took both over. **Arnon: they were blocked on a permission prompt, and he was away.** My own briefs specified `npx canopy@latest`, which fetches from the network and prompts; running canopy myself I used the cached local path and was never prompted, so I never saw what I had handed them.

**Both takeovers were unnecessary, and the second agent had been working correctly throughout.** Recorded in auto-memory and in the resume runbook: check for a pending prompt before concluding an agent stalled, and never put a prompting command in a brief.