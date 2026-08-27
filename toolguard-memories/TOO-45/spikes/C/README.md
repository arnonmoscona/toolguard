---
title: README
type: note
permalink: toolguard/too-45/spikes/c/readme
---

# Spike C -- lift blind, parse, then ask the tree

## Files

- `heredoc_sink.py` -- the spike itself: `lift_heredocs()` (step 1) and `sinks()` (step 2,
  wraps `bash_parser.parse` + `command_model.build_ir`, both unmodified repo code).
- `run_cases.py` -- runs the 16 cases from `../CASES.md` and prints pass/fail.

## Results

```
$ uv run --project /home/arnon/projects/toolguard python run_cases.py
16/16 passed
```

Every case passes, including #5 (bare `&`) and #6 (separator inside `$(...)`) -- the two
that were shipped as defects once. Neither required a single line of new code in this
spike: they pass because `heredoc_sink.py` never implements a notion of "statement
boundary" at all. It hands the grammar text with the heredoc bodies removed and a plain
word standing in for each redirection, and the grammar's own `control_op`/`compound_command`
rules do the rest.

## How it works, in two steps

1. **`lift_heredocs`** -- line-oriented scan, no structural knowledge. For each physical
   line it finds every *unquoted* `<<`/`<<-` (via `_quoted_positions`, the one quote-aware
   function in this file), reads the body off the following lines up to the terminator, and
   replaces the **whole redirection** -- not just the body -- with an opaque word,
   `__HD0__`, `__HD1__`, ... in left-to-right, top-to-bottom order. It makes no sink
   decision; nothing here even knows what a "sink" is.
2. **`sinks`** -- parses the cleaned text with `bash_parser.parse`, builds the existing IR
   (`command_model.build_ir`), and walks `IRCompound -> IRPipeline -> IRSimpleCmd` looking
   for placeholder text inside `IRSimpleCmd.text`. Whichever simple command's text contains
   `__HD<n>__` is that heredoc's sink, by construction of the grammar's own
   `simple_command <- command_name (proc_subst / redirection / cmd_substitution /
   command_arg)*` rule -- the placeholder is textually inside that command's argument list
   because that's where it was in the source.

Case 12 (`bash <<A <<B`) needs no special-casing: both placeholders land in the same
`IRSimpleCmd.text` (`"bash __HD0__ __HD1__"`), `_walk_element` finds both via one regex
`finditer`, and the body-to-placeholder mapping is by index, not by encounter order during
the walk -- so it doesn't matter that the walk could in principle visit them in any order.

## What is new code here, and what is reused

| concern | this spike's code | existing repo code (unmodified) |
|---|---|---|
| finding an unquoted `<<` | `_quoted_positions`, `_find_heredoc_specs` | -- |
| reading a heredoc body off following lines | `lift_heredocs` | -- |
| what a quote is (for parsing proper) | -- | `bash_parser.peg`: `single_quoted`, `double_quoted`, `escaped_char` |
| what a statement/pipe/control-op boundary is | -- | `bash_parser.peg`: `compound_command`, `control_op`, `pipe`, `cmd_substitution` |
| which command a token belongs to | -- | `command_model.build_ir` (`IRSimpleCmd.text`) |
| naming the sink from a command's text | `_sink_name` (one `.split()[0]`, basename) | -- |

## The two counts asked for

**How many places in this design encode "what a quote is"?** One: `_quoted_positions`
(31 lines), used only to decide whether a `<<` is inside a string. It does not need to
agree with the grammar's own quote rules on anything except "is this `<<` real" -- if it
is ever wrong, the grammar either parses the leftover `<<...` as a redirection anyway
(usually harmless) or fails to parse, which surfaces as a `ParseError`, not a silent
wrong answer.

Contrast with `multiline.py`, which has **five** independently-written quote scanners --
`_join_backslash_continuations`, `_find_heredocs_in_line` (parity-count, the one that
shipped case-15's defect), `_split_on_unquoted_pipe`, `_statement_bounds_containing`, and
`_strip_comments` -- and says so itself: *"The quote scanners across steps 2-4 do not
agree; each documents its own model."*

**How many places encode "what a statement boundary is"?** Zero, in this spike's own
code. `lift_heredocs` never looks at `&&`, `||`, `;`, `&`, `|`, or `$(...)`/backtick
nesting. All of that is `bash_parser.peg`, used as-is.

Contrast with `multiline.py`'s `_statement_bounds_containing` (70 lines, hand-tracking a
`control_op` table *and* a `$(`/backtick nesting stack) and `_split_on_unquoted_pipe`
(52 lines, a second, independent pipe-splitter) -- both of which exist only so heredoc
sink classification can happen before the grammar runs, and both of which the file's own
comments flag as needing to be kept in lockstep with the grammar by hand: *"Deliberately
mirrors `bash_parser.peg`'s `control_op` alternation ... so a drift between the two
grammars shows up as a missing or extra table entry rather than a missing `elif` branch."*
That's an explicit, permanent synchronization burden this design has no equivalent of,
because there is only one implementation of "statement boundary" in the whole pipeline.

## Where would a reader look first if case 5 or case 6 came out wrong?

**`bash_parser.peg`** -- specifically the `control_op`/`background` rule for a bare `&`
(case 5), or `dollar_paren_sub`/`cmd_substitution`'s nesting inside `compound_command` for
a separator swallowed by `$(...)` (case 6). Not `heredoc_sink.py`: that file has no code
path that could be responsible, because it never reasons about either construct. That is
this design's main claim -- a structural bug is a grammar bug, full stop, with one place
to look and one place to fix, instead of a grammar rule and a hand-rolled Python model
that are supposed to agree with it.

## What this design makes EASY

- **Structural bugs have exactly one home.** No parallel Python model of statement
  boundaries to keep in sync with the grammar, so the class of defect that produced cases
  5 and 6 (a separator handled correctly by the grammar but differently, or not at all, by
  the hand-rolled splitter) cannot recur here by construction, not by discipline.
- **Multiple heredocs on one line "just work"** (case 12) -- the grammar already collects
  every `redirection`/`command_arg` into the same `simple_command`'s element list; this
  spike didn't have to think about it, and the mapping-by-index means the walk order
  doesn't even need to match the lift order.
- **Pipe-attached heredocs need no special-casing** (cases 10 and 16). The OLD code has to
  explicitly split on `|` and read the LAST segment to classify a heredoc's sink
  (`_split_on_unquoted_pipe` + `_classify_pipeline_sink`), because it decides the sink
  before parsing. Here the placeholder is textually part of whichever `pipeline_element`'s
  `simple_command` it was written next to, so the grammar scopes it correctly with zero
  extra code.
- **Reducing the quote-scanner count from five to one** shrinks the surface a case-15-style
  bug (an apostrophe inside double quotes miscounted as a real single quote) can hide in.

## What this design makes AWKWARD -- honestly

- **`sinks()` only identifies the sink; it does not decompose a bash-family heredoc's
  body.** `bash <<HD\ncat /etc/passwd\nHD` correctly reports `sinks() == ["bash"]`, but
  getting *`cat /etc/passwd`* itself as a leaf command -- what the real pipeline needs to
  do anything useful with a bash-family sink -- requires a **second, recursive parse of
  the spliced body text** (`bodies[i]`), which can itself contain another heredoc,
  requiring its own `lift_heredocs` pass. This spike does not hide that cost, and it is
  not new: it is the same shape as the existing `_apply_leaf_policy`'s `<bash-family> -c
  "..."` recursion (`extract_structured(inner_bash)`), which already re-enters the whole
  pre-pass + grammar pipeline once per nested bash payload. The bound is one extra
  full parse per bash-family heredoc actually present in the input, recursing only as deep
  as heredocs are nested inside heredocs -- which in real Claude Code traffic is 0 or 1
  levels, not unbounded. This design doesn't eliminate that cost; it just doesn't add any
  cost beyond what the existing recursive pattern already pays.
- **Error locality degrades.** A malformed command surfaces as a `ParseError` against the
  *placeholder-laden* cleaned text, not the user's original text. Translating that error
  back through the placeholder-to-body mapping for a real (non-spike) implementation is
  extra work this prototype doesn't do.
- **The placeholder scheme leans on an implicit grammar property**: that any bare word is
  accepted wherever a redirection could have been (`command_arg <- word spacing`), so
  swapping in `__HD0__` for `<<HD` is always grammatically legal. True today, but nothing
  declares that dependency -- a future grammar change narrowing where a word is legal
  would break this silently until a parse failure surfaced it.
- **The redirection's own shape is discarded, not preserved.** Because the placeholder
  replaces the *whole* `<<DELIM`, not just the body, the tree never contains a `heredoc`
  node for it -- only an ordinary word. A consumer that needs to know "this argument was a
  heredoc, specifically" (as opposed to some other word) has to go through the side table
  (`bodies`, keyed by the index in the placeholder), not the tree itself.

## Honest verdict

The two counts above are the real result: **one quote scanner, zero boundary scanners**,
against `multiline.py`'s five and two (one of which is explicitly flagged as needing
hand-synchronization with the grammar). That is the whole reason cases 5 and 6 pass here
without any code written for them. The tradeoff is that this design answers a narrower
question than the full pipeline needs -- *who owns this heredoc* -- and getting from there
to *what does a bash-family heredoc's body actually run* still costs a second parse,
which this spike shows but does not implement.