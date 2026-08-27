---
title: 105-strip-comments-compensates-for-the-extractor
type: note
permalink: toolguard/too-45/proposed-tickets/105-strip-comments-compensates-for-the-extractor
---

# 105 - `_strip_comments` exists to compensate for the extractor, not because the grammar cannot do it

**Arnon, 2026-08-21**: *"`_strip_comments()` is another hand-rolled parser that should be cleaned up. Yes, it's much shorter, and plausibly understandable. But why do we need it in the first place?"*

**Measured the same day, and the answer is: not for the reason the code implies.**

## What the grammar already does

`bash_parser.peg` HAS a comment production (line 67), and its own note at line 64 reads: *"the pre-pass already strips comments, so this is mainly a safety net."* Measured against the generated parser, with the pre-pass bypassed entirely:

| input | grammar parses? | extractor's leaf text |
|---|---|---|
| `ls -la` (control) | yes | `ls -la` |
| `ls && echo hi` (control) | yes | `ls`, `echo hi` |
| `# INTENT: disclosure`⏎`ls -la` | yes | `ls -la` -- **whole-line comment correctly dropped** |
| `echo hi # trailing comment` | yes | `echo hi # trailing comment` -- **comment RETAINED in the leaf** |
| `echo '# not a comment'` | yes | preserved as an argument, correctly |
| `ls # c1`⏎`echo hi # c2` | yes | `ls # c1`, `echo hi # c2` -- retained |

## The finding

The grammar **parses comments correctly and distinguishes a quoted `#` from a real one** -- the exact discrimination `_strip_comments` hand-rolls a quote scanner to perform. It also already drops whole-line comments.

What it does not do is **trim a trailing comment out of the leaf's TEXT**. And leaf text is what permission rules match against, so `Bash(echo hi)` would not match `echo hi # trailing comment`.

**So `_strip_comments` is not compensating for a grammar limitation. It is compensating for the EXTRACTOR including comment tokens when it rebuilds leaf text** -- from a tree that already knows which tokens are comments.

## Fix direction

Have the extractor exclude `comment` nodes when reconstructing a leaf's text, then delete `_strip_comments` and its quote scanner. That removes the **third** hand-rolled quote model from `multiline.py`, leaving only continuation joining.

**This is extractor work, not grammar work** -- the production already exists, so the two-phase rule in `.claude/rules/bash-grammar.md` does not apply. Verify no golden moves: the pre-pass currently strips comments *before* the grammar sees them, so a correct change should be behaviour-neutral, and any corpus diff means the two implementations disagreed somewhere.

**Caveat measured honestly**: this repo's own disclosure convention puts `# INTENT:` comments before commands, so comment handling is load-bearing here in a way it may not be elsewhere. The whole-line case already works; only the trailing case is at issue.

## Companion item: a technical note for `multiline.py`'s flow

Arnon: *"The new functions on their own are easier individually to understand... but the overall flow is less so... I do want to put it to bed, so another doc explaining the logic and the flow - at risk of drifting is easier and better than nothing."*

**Accepted as a decision.** One note, worth recording rather than relitigating: `extract_structured` is a five-step pipeline whose steps are currently implicit in a function body. Making that sequence explicit in code would make the flow self-documenting and could not drift. If the doc is written first, prefer one that a later refactor would delete rather than contradict.
---

# REFUTED 2026-08-22 — THE PREMISE ABOVE IS WRONG. `_strip_comments` is load-bearing, not redundant.

Found by the implementing agent, which stopped rather than building on a false premise. **I verified its refutation independently and it holds.**

## What I got wrong

I measured that the grammar "parses" `echo hi # trailing comment` and concluded it recognised the comment and merely failed to trim it from the leaf text. **It does not recognise it at all.**

The `comment` rule (`bash_parser.peg:67`) is reachable only through `line_ws_char`, and `simple_command`'s argument loop never invokes that -- it uses horizontal-only `spacing`. The agent instrumented the rule's memoization cache: while parsing `echo hi # trailing comment`, **`comment` fires zero times.** The parse succeeds because `#`, `trailing` and `comment` are absorbed as ordinary `command_arg` word tokens.

Two checks settle it:

| probe | result |
|---|---|
| `echo hi # trailing comment` vs `echo hi zz trailing comment` | **identically-shaped leaves.** `#` is treated exactly like the ordinary word `zz` |
| `# whole line only` handed to the grammar | **ParseError.** Today `_strip_comments` reduces it to `""` first, short-circuiting to a benign `[]` |

So `echo '# not a comment'` looked correct for a trivial reason: *everything* in argument position is a word, so of course a quoted `#` survives. There was no discrimination to admire.

**And the leading whole-line case that DOES work is handled by a different mechanism** -- the top-level `line_ws`, outside the `compound_command` the extractor reads. Not the same rule reaching a different position.

## The corrected answer to Arnon's question

He asked: *"why do we need it in the first place?"*

**Because the grammar genuinely cannot handle a comment in command position.** `_strip_comments` is not compensating for the extractor. It is compensating for a real gap in the grammar, and deleting it regresses whole-line comments to a ParseError. It is load-bearing.

## How the error happened, since it is the campaign's own signature

I treated **"the parse succeeded"** as **"the parse was correct"** -- the *green for the wrong reason* pattern, which I had written into a memory note hours earlier. The control I needed was one line: compare `#` against an ordinary word in the same position. I ran controls that session and they caught a different bug (passing a string where a tree was wanted), which made the instrument feel validated. **A control that catches one class of error does not validate the instrument for another.**

## Disposition

- **Doc half: DONE** and committed (`da09faa`) -- the flow note Arnon asked for is unaffected by any of this.
- **Code half: RE-SCOPE, do not implement as written.** Removing `_strip_comments` requires the grammar to recognise a comment in command position, which is a **`bash_parser.peg` change under the mandatory two-phase rule**, not extractor work. It is also entangled with `_attribute_sinks`, which re-parses text that has not been comment-stripped yet.
- Worth doing eventually, because it would remove a hand-rolled quote scanner and the project's standing rule is that all bash parsing goes through the grammar. **Needs Arnon's decision on scope**, and it is naturally adjacent to ticket 101, which is also a `.peg` word-token change.

---

# DECISION 2026-08-22 (Arnon) — FIX IT AT THE SOURCE. The grammar owns comments.

> *"I did suspect that this extra parsing is masking some PEG problem. You said otherwise, and I wasn't exactly surprised either. Turns out that it is. Comments are a real thing and should be properly represented in the PEG and handled with appropriate representation in command_extractor and command_model. Discarding them should be a choice of the clients of these modules via the appropriate functions or arguments, not an intrinsic property of the underlying PEG parser. So the right fix is fixing it at the source - the parsing package and the PEG grammar underlying it. Worth doing. The parser is the absolute foundation of the whole tool. It should lift everything it needs to lift for the rest of the code as long as it is not limited by PEG or by the Canopy implementation of PEG."*

**He suspected the extra parsing was masking a PEG gap. I measured and told him it was not. He was right.**

## The principle this establishes, beyond comments

**The parser must lift everything it can lift.** A gap in the grammar must not be quietly compensated for downstream — because the compensation looks like a design choice, and the gap becomes invisible. `_strip_comments` looked like a pre-pass convenience for two years; it was a grammar hole wearing a pre-pass costume.

**And discarding is a CLIENT decision, not a parser property.** The grammar should produce comments as nodes. Whether a caller wants them is expressed at the call — a function or an argument — not baked into a lexical pre-pass that no caller can opt out of. Today no client *can* see a comment, because none survives to be seen.

The only legitimate reason to keep work out of the grammar is a genuine PEG or canopy limitation. That is the test to apply, and it is the same one that justified the heredoc pre-pass in ticket 98: a heredoc terminator is context-sensitive and a PEG has no backreferences. **Comments have no such excuse.**

## Scope, and the two-phase rule applies

**Phase 1 — `bash_parser.peg` + canopy regeneration, reviewed ALONE.** Make `comment` reachable where comments actually occur, including in command position after arguments. Today it is reachable only via `line_ws_char`, which `simple_command`'s argument loop never invokes.

**Phase 2 — Python.** A `COMMENT` variant in `command_model.NodeKind`; `command_extractor` representing comment nodes rather than absorbing them as `command_arg` words; a client-facing way to include or discard them. Then `_strip_comments` and its quote scanner can go, which removes the third hand-rolled quote model from `multiline.py`.

**Also re-examine `_attribute_sinks`**, which re-parses text that has not been comment-stripped — the entanglement the implementing agent flagged.
