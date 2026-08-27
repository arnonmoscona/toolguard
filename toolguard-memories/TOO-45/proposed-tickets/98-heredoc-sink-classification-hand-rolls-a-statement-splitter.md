---
title: Heredoc sink classification hand-rolls a statement splitter the grammar could supply
tags:
- TOO-45
- proposed-ticket
- architecture
permalink: toolguard/too-45/proposed-tickets/98-heredoc-sink-classification-hand-rolls-a-statement-splitter
---

# `_statement_bounds_containing` is a hand-rolled parser, and only half of it is forced

**Raised by Arnon, 2026-08-21, reviewing commit `2e53d429` (item 19):** *"multiline.py `_statement_bounds_containing()` is a hand-rolled parser. This needs serious justification. I don't like it at all."*

**He is right, and the justification in the module docstring is weaker than it reads.** It asserts the deviation is forced. Only part of it is.

## What IS genuinely forced

A heredoc body cannot be handed to the PEG parser. Its terminator is **context-sensitive** — the delimiter is captured earlier in the same input and must be matched later — which a PEG cannot express without backreferences, and canopy has none. The grammar acknowledges this directly:

```
# The heredoc body is removed by the pre-pass (replaced with a sentinel);
heredoc <- "<<" "-"? spacing heredoc_delimiter spacing heredoc_content?
heredoc_content <- (![\n\r] .)*      # same-line content only
```

So **body extraction must precede the grammar.** That is a real constraint and not the thing being questioned.

## What is NOT forced

**Deciding which command a heredoc belongs to is a structural question, and the grammar answers it.** `redirection` is part of `simple_command`; once parsed, the AST says exactly which command owns each `<<`. `_statement_bounds_containing` re-derives that in Python, splitting on `&&`, `||`, `;`, `&` — which is `control_op`, a rule the grammar already has.

The pre-pass conflates two jobs:

| job | needs structure? | must precede the grammar? |
|---|---|---|
| find `<<WORD`, find the terminator line, lift the body | **no** — purely lexical, line-oriented | **yes** |
| decide which command receives it | **yes** | **no** |

**Only the first is forced. The second is done early because the first had to be, not because it must be.**

## The alternative shape

1. **Lexically** lift each heredoc body to a side table, replacing the redirection with a sentinel. No statement knowledge — find `<<`, find the terminator line, cut. Quoted delimiters and `<<-` are lexical details.
2. **Parse with the grammar.**
3. **Ask the AST which `simple_command` owns each sentinel.** That is the sink, from the one component whose job it is.
4. **Then** decide per sink: bash-family, splice the body back as shell; foreign, keep the sentinel and raise the floor.

**This deletes `_statement_bounds_containing` and `_split_on_unquoted_pipe` outright** — the two hand-rolled scanners in the module — and removes the class of defect they have already produced twice: the missing `&` separator, and the `$(...)`-internal separator that split a statement it should not have.

## Why it was not built this way

Step 4 needs the sink *before* deciding what to do with the body, and the original implementation read that as "so the sink must be known before parsing." **It does not follow** — the body can be lifted provisionally and the decision deferred until after the parse, which is the whole point of a side table.

**This is the third time in this campaign that "the grammar already knows and the Python re-derives it" has been the finding.** The first two were the `if`/`while` condition and the command substitution.

## Cost and risk

Not small. It restructures the pre-pass and moves the sink decision after parsing, which changes when the floor is computed. It touches the most defect-dense function in the module and the corpus is the only real proof of equivalence.

**Recommend a plan-first ticket**, with the corpus replay as the acceptance test and the two known bypasses (`&` and `$(...)`) as explicit regression cases. **Do not attempt it as a refactor-in-place.**

## Interim

If it is not done, the module docstring must stop claiming the whole deviation is forced. **It should say plainly that body extraction is forced and sink classification is a shortcut** — the current wording invites the next reader to accept both.

---

# THREE SPIKES BUILT AND MEASURED, 2026-08-21

Arnon asked for working options rather than a paper argument: *"you can implement on the side a couple of options that I can look at and decide from my perspective what's easier for me and what I think would be more maintainable."*

Built in `scratchpad/spikes/{A,B,C}/`, each exposing `sinks(text) -> list[str]`, each run independently by the coordinator against the shared 16-case set in `spikes/CASES.md`.

| | architecture | lines | quote scanners | statement-boundary code | 16 cases |
|---|---|---|---|---|---|
| **shipped** | four ad-hoc scanners | 683 | **5** | 2 | **14/16** |
| **A** | one lexer, four consumers | 453 | 1 | 1 (shared) | 16/16 |
| **B** | small line-scoped `.peg` + code | 109 (peg) + code | 1 | 0 (in the grammar) | 16/16 |
| **C** | lift blind -> full grammar -> ask the tree | 250 | **1** | **0** | 16/16 |

**All three fix cases 15 and 16, which the shipped module fails** — P4's escaped apostrophe and ticket 92's `python <<HD | bash`. Neither was targeted; the architectures simply lack those failure modes. **That is the strongest evidence that the structure, not its bugs, is the problem.**

## The 16 cases did not separate the designs. Case 17 did.

`if true; then cat <<HD` — a control-structure keyword on the heredoc's own line:

- **shipped, A and B** all answer `then`. **Confidently wrong.**
- **C** answers `<unresolved>`.

**Two of the three candidates reproduce this campaign's defining failure mode — a mechanism that fails open and says nothing.** C cannot: the grammar either attributes the placeholder to a `simple_command` or it does not, so an unattributable heredoc surfaces as unknown rather than as a plausible token.

**Found by spike B probing beyond its brief**, and reported as B's own weakness. It is A's too, and the shipped module's.

## Recommendation: C, on failure mode rather than size

B's `.peg` is the most readable single artifact of the three and its line-scoped insight is Arnon's own. But it buys a **second grammar to keep in step with the first** — this campaign's recurring defect is two artifacts drifting — **and it still guesses when out of its depth.**

C's costs, stated plainly: a bash-family sink still needs a **second recursive parse** of the spliced body (bounded 0-1 in practice, the same shape as the existing `bash -c` recursion), and it depends on the main grammar's IR, so a grammar change can move it.

## Two things the plan must settle

1. **`<unresolved>` needs a policy.** The natural one: treat it as undecidable and let the ASK floor take it — which is what toolguard already does for a segment it cannot decompose. **Do not let it default to a guess.**
2. **Case 17 joins the permanent case set.** It is the only case that separated the designs, and none of the original sixteen did.

---

# ARNON'S DECISIONS ON THE SPIKES, 2026-08-21

## Spike C is the direction. Three constraints on top of it.

> *"It's much easier to read and is more maintainable than the original. I wouldn't call it 'easy' exactly, but it's 'digestible' - as in not causing stomach pain."*

### 1. The sentinel STAYS — and my "open question" was wrong

I had asked whether `__HEREDOC_TO_<sink>__` could become an opaque placeholder once the sink comes from the AST. **No.** Arnon:

> *"I think that `__HEREDOC_TO_<sink>__` still needs to exist. I know it hasn't been used much yet. but it's a really neat way to capture meaning that is simply not possible with regex matching rules or any of the dialects we have."*

**The sentinel is a semantic carrier, not an implementation detail.** It lets a permission rule express *"a heredoc fed to python"* — a fact no regex over the raw command text can reach, because the body has been lifted out by then. Low current usage is not evidence against it; it is a capability the rule dialects do not otherwise have.

**Consequence for the design**: spike C's opaque placeholder becomes an *internal* stage, not the output. Lift blind -> parse -> attribute from the AST -> **rewrite the placeholder into `__HEREDOC_TO_<sink>__`**. The sentinel is what the extractor emits; the placeholder is what the lifter emits. Two names for two stages, and the distinction is the point.

### 2. The code does not belong in `multiline.py`

> *"Most of that code I am not sure belongs in multiline.py. It looks and feels like code that should be in parser/command_extractor.py and parser/command_model.py with a nice, clean external interface."*

**Right, and it follows from the design rather than being a preference.** `multiline.py` is the *lexical* pre-pass. Once sink attribution is answered by walking the parse tree, it is no longer lexical work — it is extraction and model work, and it belongs with the other code that reads the IR.

So the port has a **module-boundary component**, not just a rewrite:

- `multiline.py` keeps the genuinely lexical steps — line endings, backslash joins, comment strip, whitespace, and the **blind** heredoc lift.
- `command_extractor.py` / `command_model.py` take AST-based sink attribution and sentinel rewriting.
- The seam between them is *"text in, cleaned text plus a body side-table out"* — which is a far narrower interface than today's.

**This is what makes it worth doing beyond the defect count**: the current module is hard to place *because* it does two kinds of work, and the split names them.

### 3. Documentation is part of the ticket, not an afterthought

> *"A detailed explanation of this code, its motivation, the rejected alternatives (mostly reworked README.md that you already provided) should be in the docs directory and referenced from a docstring comment and from the technical note documentation - including a 'reader's guide'."*

So: a `docs/` page carrying the motivation, the **rejected alternatives** (extend the grammar — impossible without backreferences; a second line-scoped grammar — spike B, a second artifact to keep in step; full recursive descent — a bigger exception than the rule it replaces), and a **reader's guide** to the resulting code. Referenced from the module docstring and from the technical notes.

**The rejected alternatives are the most valuable part** and the part that normally goes unwritten — without them the next reader re-proposes spike B, and the spikes exist precisely so that conversation happens once.

## Not a surprise, and worth recording as calibration

> *"I actually suspected that these two existing bugs would be fixed by creating a better structure. Not surprised about this."*

Cases 15 and 16 — P4's escaped apostrophe and ticket 92's piped heredoc — fall out of every candidate design. **Arnon predicted that before the spikes were built.** Worth recording as a calibration point: the architectural instinct was ahead of the measurement here, and the spikes confirmed rather than discovered it.
