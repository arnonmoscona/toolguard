---
title: 19-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/19-estimate-predictions
---

# TOO-45 proposed-ticket 19 — blinded touch-set estimate (heredoc bypasses P2/P3 only)

## Reasoning

Scope is P2 (an earlier bash-family token on the same line steals the sink classification of a
later *foreign* heredoc, silently dropping the ASK floor) and P3 (two heredocs on one line
mis-assign their bodies to the wrong sink, and a terminator leaks out as a command). Both are
explicitly attributed in the ticket text to the *lexical pre-pass* module — `multiline.py`'s own
docstring is quoted as claiming "no structural parsing happens here," and the ticket calls this
false, naming `_classify_pipeline_sink` / `_extract_pipeline_sink` (P1/P2 discussion) and, by
strong inference from placement and the shared "heredoc segmentation model" language,
`_process_heredocs` (P3) as living in the same module. This is a pre-pass that runs *before* the
PEG grammar ever sees the text — it exists specifically to swap heredoc bodies out and classify
sinks so the grammar doesn't have to know about heredocs at all — so I treat the whole defect
class as belonging to one cost centre: the hand-rolled segmentation logic inside
`toolguard/parser/multiline.py`.

Second cost centre: consumers of that pre-pass. `command_extractor.py` is named as the site of
the (already-fixed) P1 patch and of the `__HEREDOC_TO_<sink>__` sentinel contract the ticket
calls out as "undeclared... spanning three files." If the sink-classification fix changes what
`multiline.py` hands back, something downstream that builds `LeafCommand(ask_floor=...)` from
that classification may need a matching edit. I rate this lower confidence than the pre-pass
module itself because the ticket's own P2 reproduction calls `extract_structured(...)` as a black
box and never says the defect is in the consumer — only in the segmenter.

Third cost centre: tests. The ticket is unusually explicit that the existing test files are
largely non-adversarial (13/18 unfalsifiable parser tests, 12/223 unfalsifiable compound tests)
and demands direct tests for P1-P5 plus a general per-construct coverage assertion. The natural
home for pre-pass-level heredoc defects is `test_multiline_bash.py` (already the TOO-17
multi-line/heredoc test file). P2 is specifically about the foreign-heredoc ASK floor, which is
the declared subject of `test_command_extractor_inline_code.py`. P1 got its regression test in
`test_compound_resolve_seam.py` (the file that owns `RuntimeVerdict.sub_matches`/`ask_floor`
content) precisely because the defect was an ask-floor bypass; P2 is the same shape of bug, so I
give that file medium confidence too.

Fourth cost centre: the grammar. The ticket repeatedly signals that P1, P4, P5 "look like
extractor-side fixes" that don't touch the `.peg`, and heredoc handling is described as a
pre-pass specifically *because* the grammar doesn't parse heredocs — the pre-pass exists to keep
heredoc bodies out of the grammar's view. That argues strongly against a grammar change for P2/P3
as well: the defect is in how the pre-pass segments a line into heredoc-bearing chunks, which is
Python string/token work over the raw line, not something the PEG grammar participates in at all.

## Production — modified

| file | reason | confidence |
|---|---|---|
| `toolguard/parser/multiline.py` | Owns `_classify_pipeline_sink`/`_extract_pipeline_sink` (P2: segments only on `\|`, needs to also stop segments at `&&`, `\|\|`, `;`) and, inferred, `_process_heredocs` (P3: mis-assigns bodies when two heredocs share one line) | high |
| `toolguard/parser/command_extractor.py` | Consumer of the sink classification / `__HEREDOC_TO_<sink>__` sentinel; already touched for the sibling P1 fix and for the awk flag fix (P6) named in the ticket's "already fixed" note, so it's a plausible second edit site if the classification's shape changes | medium |
| `toolguard/parser/command_model.py` | Only if `LeafCommand`/`ask_floor` construction needs a new field or a different sink value threaded through it | low |

## Production — added

None expected. Both bypasses look like corrections to existing functions' segmentation logic, not new capability.

## Test — modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_multiline_bash.py` | Direct owner of pre-pass/heredoc behaviour (already the TOO-17 multi-line test file); the natural home for both P2's segmentation fix and P3's dual-heredoc-per-line fix | high |
| `test/unit/test_command_extractor_inline_code.py` | Declared subject is foreign inline-code/heredoc detection; P2 is exactly "a foreign heredoc's ASK floor gets dropped" | medium |
| `test/unit/test_compound_resolve_seam.py` | P1 (the sibling ask-floor bypass) got its regression test here because the file owns `sub_matches`/`ask_floor` content; P2 is the same shape of defect | medium |
| `test/unit/test_compound.py` | Ticket calls this file out at length for 12 unfalsifiable tests and demands better P1-P5 coverage generally, but P2/P3 are pre-pass-level, one layer below what this file exercises | low |
| `test/unit/test_bash_parser.py` | Only relevant if a regression test is added to assert the *grammar* still accepts the corrected pre-pass output; not expected since no grammar change is predicted | low |

## Test — added

None expected — existing files (`test_multiline_bash.py` especially) already own this territory closely enough that new cases probably land as additional test methods, not new files.

## Deleted

None expected.

## Concentration set

`toolguard/parser/multiline.py` (production) and `test/unit/test_multiline_bash.py` (test) should hold the large majority of changed lines. Everything else in the tables is a secondary, smaller touch or a coverage add-on.

## Layer prediction (scored separately)

**Predicted: entirely Python, no `.peg` grammar change.** Heredoc recognition is explicitly a
hand-rolled *pre-pass* that runs before the grammar sees the line — that's the whole reason the
ticket can accuse `multiline.py`'s docstring of lying about containing no structural parsing.
Both P2 and P3 are defects in how that pre-pass segments/reassigns text, which is a string/token
problem over the raw command line, not a construct the grammar needs to recognize differently.
The ticket's own fix-ordering note groups P2/P3 with P1/P4/P5 as *not* needing the two-phase
grammar procedure, only naming the `.peg` path as conditional ("if it touches the .peg"). I
predict it does not.

## Scope prediction (scored separately)

**Predicted: one coordinated fix, not two independent ones**, matching the ticket's own text:
"P2/P3, which share the heredoc segmentation model and probably want fixing together." I expect
this lands as edits to two related functions in the same file/model (segment-boundary detection
for P2, body-to-sink assignment for multiple heredocs for P3) delivered together, rather than a
literal single one-line patch — the shared root cause is the segmentation model, not a single
function, so I'd expect two nearby diffs in `multiline.py` in the same change rather than a
one-line fix covering both.