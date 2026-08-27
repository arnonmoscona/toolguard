---
title: 79-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/79-estimate-predictions
---

# TOO-45 proposed-ticket 79 — blinded touch-set estimate

Ticket: "Command substitution runs foreign inline code with no ASK floor, and the verdict
corpus is structurally blind to it"

## Reasoning

The ticket describes a **detection gap**, not a **policy gap**. The ASK floor for inline
foreign code (an interpreter fed code via `-c`/`-e`/heredoc) already exists and already
fires correctly for top-level leaf commands. What it misses is a leaf command that is
*nested inside a `$( ... )` command substitution* rather than sitting at the top level or
inside an `if`/`while` condition. The ticket's own framing makes the shape of the fix
explicit: "the extractor must descend into command substitutions the way it now descends
into `if`/`while` conditions." That sentence names both the cost centre (traversal logic in
the extractor) and the precedent for how it should be shaped (whatever mechanism already
walks into conditional bodies).

I decomposed the problem into these cost centres:

1. **Traversal/detection** — teaching the leaf-command walker to descend into a command
   substitution and classify what it finds inside using the same inline-foreign-code
   classifier used elsewhere. This is very likely one function/branch in one file, mirroring
   an existing `if`/`while` descent path already present in that file.
2. **IR representation** — whether the abstract command model already carries "this word
   contains a command substitution with an inner command" as a field, or whether that field
   needs to be added. Bash grammars generally must parse the *interior* of `$(...)`
   structurally regardless of downstream policy, because failing to do so breaks
   top-level splitting itself (an unquoted `;`, `&&`, or `#` inside the substitution must not
   be mistaken for a top-level separator). That structural need is orthogonal to this ticket
   and almost certainly already satisfied — which is exactly the shape of the earlier,
   directly-referenced case: the grammar parsed the construct; the Python layer discarded
   the field it didn't yet have a consumer for.
3. **Interaction with the assignment-prefix ticket (77)** — the ticket flags that a
   substitution can itself carry a leading `NAME=value` assignment (its own worked example,
   `PKG=$(uv run python -c ...)`), so whatever "strip a leading assignment before matching"
   logic exists must not swallow a substitution's inner command along with the assignment
   token. I expect this to be handled in the same traversal code, not a separate module.
4. **Downstream consumers of the floor** — once a nested leaf command is correctly emitted
   and classified as `inline_code`, the floor-application logic that already governs
   top-level `inline_code` units should apply unmodified. I don't expect the floor's
   decision logic itself to change; only what reaches it.
5. **Tests** — a dedicated inline-foreign-code test file already exists by name
   (`test_command_extractor_inline_code.py`), which is the obvious home for new cases
   (`echo $(python -c "...")`, `PKG=$(uv run python -c ...)`, nested substitutions, a
   substitution inside an `if` condition). Secondary coverage is plausible at the
   ask-resolution and compound levels, since those exercise the floor end-to-end against the
   real decision engine.
6. **Corpus-tier recommendation** — the ticket's closing paragraph proposes a new corpus
   tier with `undecidable_fallback = "ask"` so future floor regressions are observable. This
   reads as a recommendation for a *follow-up* ticket, not a requirement of this fix (it is
   phrased as "Recommendation:", separate from the bug description), so I am not predicting
   it as part of this ticket's touch set, only flagging it as a plausible scope-creep risk.

## Production — modified

| file | reason | confidence |
|---|---|---|
| `toolguard/parser/command_extractor.py` | Primary fix location: the leaf-command walker gains descent into `$( ... )` command substitutions, paralleling existing `if`/`while` descent, and must classify inline-foreign-code hits found inside. | high |
| `toolguard/parser/command_model.py` | If the IR node for a word/substitution doesn't yet expose an inner command list to the extractor, it needs a field added or un-discarded. Given the campaign's precedent (grammar already parses it, Python drops it), I lean toward a small change here rather than none. | medium |

## Production — added

none expected

## Test — modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_command_extractor_inline_code.py` | Named-for-purpose home for the new substitution cases; almost certainly the majority of new test lines. | high |
| `test/unit/test_assignment_prefix.py` | Ticket explicitly calls out the assignment-prefix interaction (ticket 77) as a case the fix must not break. | medium |
| `test/unit/test_ask_resolution.py` | End-to-end regression coverage of the floor firing through the real decision engine for a substitution case, matching this test file's stated purpose. | low |
| `test/unit/test_compound.py` | Possible integration-level case if compound-command splitting tests assert on substitution behavior, but the fix is extractor-level so this may not need touching at all. | low |
| `test/unit/test_bash_parser.py` | Only if AST-shape assertions change; if the grammar itself is untouched (my prediction), this file likely doesn't need to change either. | low |

## Test — added

none expected — the existing dedicated inline-code test file is the natural target, so I
don't expect a new test file.

## Deleted

none expected

## Concentration set

`toolguard/parser/command_extractor.py` and `test/unit/test_command_extractor_inline_code.py`
should hold the large majority of changed lines. This is a narrow, single-capability
addition ("descend into one more syntactic construct"), not a cross-cutting policy change,
so I expect the diff to be small and concentrated rather than spread across the engine layer.

## Layer prediction (scored separately)

**Prediction: this lands entirely in the Python that consumes the parse tree. No `.peg`
grammar change, and no `bash_parser.py` regeneration.**

Reasoning: a PEG grammar that already handles compound-command splitting correctly around
`$( ... )` must already parse the substitution's interior as a structured sub-command,
because getting this wrong breaks something more basic than this ticket — top-level
splitting itself (an internal `;`/`&&`/`#`/quote inside the substitution must not leak out
and mis-split the outer command). Given the project already added deliberate descent into
`if`/`while` bodies (per the ticket's own analogy) and this project's compound-command
support is fairly mature (`compound.py` is 1100+ lines, `test_compound.py` is 2800+ lines),
I expect `$(...)` interior parsing to already exist in the grammar as a matter of necessity,
not as a gap. The ticket's own wording — "descend into command substitutions the way it now
descends into if/while conditions" — treats this as adding a traversal, not adding a grammar
production, which supports the same conclusion.

If I'm wrong and a grammar change *is* required, I'd expect the touch set to instead include:

| file | reason | confidence |
|---|---|---|
| `toolguard/parser/bash_parser.peg` | Grammar source of truth; would need a new/extended production for command-substitution interiors if one doesn't already exist. | low (contingent) |
| `toolguard/parser/bash_parser.py` | Canopy-regenerated from the `.peg` change; large mechanical diff, not hand-edited. | low (contingent) |
| `test/unit/test_bash_parser.py` | New AST-shape assertions for the new/extended production. | low (contingent) |

My primary bet is against this branch — I expect zero lines changed in `bash_parser.peg` or
`bash_parser.py` for this ticket.