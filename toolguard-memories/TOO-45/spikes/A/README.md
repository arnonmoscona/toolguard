---
title: README
type: note
permalink: toolguard/too-45/spikes/a/readme
---

# Spike A -- one lexer, four consumers

`lexer.py` is a single left-to-right scanner (`scan`) that walks the text once
and emits `Span` objects, each a run of characters sharing one `(state,
depth)` pair. `state` is one of `PLAIN` / `SINGLE` / `DOUBLE` / `ESCAPED`.
`depth` is `$(...)`/backtick nesting, tracked only while `state == PLAIN`
(inside a quote, depth is frozen at whatever it was on entry -- matches how
the module being replaced already treats it).

`prepass.py` expresses the four pre-pass steps as consumers of that stream:

- `join_continuations` -- reads the `ESCAPED` label; drops a backslash+`\n`
  pair whenever the escaped character is a newline.
- `strip_comments` -- reads `PLAIN`; a `#` at a word boundary in a `PLAIN`
  span starts a comment.
- heredoc finding (`_find_heredocs_in_line`) -- accepts a `<<` match only
  when the shared scan reports `PLAIN` at that offset.
- `_statement_bounds_containing` / `_pipe_segment_containing` -- read
  `PLAIN` + `depth == 0` to find control-operator and pipe boundaries.
- sink classification (`_classify_sink`) -- plain Python string handling on
  the already-segmented text; this is the one step that stays hand-written by
  design (see "what this makes awkward" below).

Result: `python run_cases.py` -- **16/16 cases pass**.

## Counts

**Places that encode "what a quote is": 1.** `lexer._char_states` is the only
function with an `in_single`/`in_double`/backslash state machine anywhere in
the spike. Every other function calls `scan`/`expand` and reads the result;
none of them re-implements quote toggling. (The module being replaced has
four: `_join_backslash_continuations`, `_find_heredocs_in_line`'s parity
count, `_split_on_unquoted_pipe`, and `_statement_bounds_containing`, and its
own docstring says they disagree.)

**Places that encode "what a statement boundary is": 2**, and they are
adjacent, not accidentally so: `_statement_bounds_containing` (the
`&&`/`||`/`;`/`&` table) and `_pipe_segment_containing` (`|`, with `||`
excluded). They are two because a statement boundary and a pipe boundary are
genuinely different things in bash -- a `;` starts a new command with its own
stdin, a `|` does not -- and case 16 depends on telling them apart (the
heredoc's *segment*, not the statement's *last* segment, is the sink). Both
functions share the same shape (`expand(scan(...))`, then a `PLAIN`+`depth==0`
scan for a token table) on purpose, so that shape, once read once, explains
both.

## Where to look if case 5 or case 6 came out wrong

**Case 5 (bare `&`)**: `prepass._CONTROL_OP_TABLE` and
`_statement_bounds_containing`. The table is four lines; if `&` were missing
from it or ordered after a prefix of itself, that is the only place it could
be missing from, because nothing else in the file scans for control
operators.

**Case 6 (separator inside `$(...)`)**: `lexer._char_states`, specifically
the three `elif` branches for `$(`, `)`, and `` ` ``, and the `depth`
variable they maintain. `_statement_bounds_containing` itself has no
`$`/backtick handling at all -- it just refuses to treat a position as a
boundary candidate unless `depth == 0`, which is a one-line check. So a case
6 failure is a lexer bug, not a consumer bug, and there is exactly one place
in the file that could produce a wrong `depth`. That separation -- consumers
trust `depth`, only the lexer computes it -- is the main thing this design
buys: a wrong answer on nesting is never a "which of four scanners disagreed"
investigation, it is "read `_char_states`."

## What this design makes easy

- **Adding a fifth consumer costs nothing to the existing four.** It reads
  `scan`/`expand` like the others; it cannot get quoting subtly wrong in a
  way the others don't already share, because there is no second
  implementation to drift from the first.
- **Case 15's defect (an embedded apostrophe hiding every heredoc after it)
  disappears without a special-case fix.** The original heredoc finder had
  its own quote-parity counter that didn't distinguish an apostrophe inside
  a double-quoted string from a real single-quote toggle. Spike A's heredoc
  finder has no counter of its own to be wrong -- it asks the shared scan,
  which already got double-quoting right for every other consumer.
- **Reasoning about depth is uniform.** Because `_statement_bounds_containing`
  and `_pipe_segment_containing` share the same "PLAIN and depth == 0" guard,
  seeing one explains the other; there's no need to check whether the pipe
  splitter happens to track substitution nesting the way the statement
  splitter does (in the original module, `_split_on_unquoted_pipe` does not
  track it at all -- a latent gap this design closes as a side effect of
  centralizing depth, not as a deliberate fix).

## What this design makes awkward -- honestly

- **Two-pass-per-consumer cost, paid in code shape, not stated as a
  performance concern.** Nearly every consumer calls `scan(text)` fresh on
  its own slice of text (a line, a statement, a segment) rather than being
  handed one global annotation once. That's fine for correctness -- each
  slice is quote-context-free at its own start, by construction of how the
  pipeline carves it out -- but it means a reader has to notice that `scan`
  is being called several times on overlapping text and convince themselves
  that's intentional (cheap re-derivation of a fact already implied by
  scope) rather than four consumers quietly reinventing the wheel again in a
  new shape. The comment on `expand` tries to head this off, but it's the
  one place in this design where "one lexer" is more of a slogan than a
  literal call count.
- **The comment/quote layering question becomes visible instead of
  disappearing.** `strip_comments` runs the shared lexer over a `#` that, in
  real bash, starts an inert comment -- but the lexer doesn't know what a
  comment is, so a `'` appearing *after* a `#` on the same line is still
  seen as a real quote-open by `_char_states`, potentially throwing off
  quote state for the rest of that scan. The module being replaced has
  exactly the same gap (comments are stripped in their own pass, after
  heredocs, with no coordination), so this isn't a regression -- but
  unifying the quote model doesn't make the ordering question go away, and a
  reader who assumes "one lexer" means "one lexer that understands
  everything" will be surprised here. None of CASES.md exercises this, so it
  wasn't chased further for the spike.
- **Sink classification is still hand-written token-splitting, not span
  consumption in any deep sense.** `_classify_sink` takes a plain Python
  string (the already-carved-out pipe segment) and does `.split()` on it.
  That's honest about what "sink classification stays in Python" means for
  this spike, but it also means the shared lexer's value stops one layer
  before the part of the problem (recognizing an executor name, a wrapper
  like `uv run`, a version suffix like `python3.13`) that the real module
  spends the most code on. This spike doesn't attempt that layer at all --
  CASES.md doesn't require distinguishing bash-family from foreign, just
  naming the sink -- so it's not a fair comparison of how much the "stays in
  Python" part would cost in a full port.