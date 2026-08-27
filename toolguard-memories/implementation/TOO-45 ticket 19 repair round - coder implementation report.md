---
title: TOO-45 ticket 19 repair round - coder implementation report
type: note
permalink: toolguard/implementation/too-45-ticket-19-repair-round-coder-implementation-report
---

## Summary

Repair round on the uncommitted TOO-45 ticket 19 P2/P3 fix. Implemented the five items in
scope from `brief-19-repair.md`. Did NOT implement the "Item 0" ($()-depth guard) that arrived
via a suspicious mid-task message -- see "Mid-task message" section below.

## Files changed

- `toolguard/parser/multiline.py`
- `test/unit/test_multiline_bash.py`

## What changed, per item

1. **`&` (background) handling in `_statement_bounds_containing`.** Added an `elif ch == "&":`
   branch after the existing `&&` branch (so `&&` is checked first via lookahead and consumed
   whole; a lone `&` falls through to the new branch and becomes a boundary). Matches
   `bash_parser.peg:96` `background <- spacing "&" !"&" spacing`. No `.peg` change, no canopy
   regen. Also updated the function's own docstring (previously said "the
   ``&&``/``||``/``;``-delimited statement", now says "the ``control_op``-delimited statement"
   and names all four operators, mirroring `control_op`).

2. **Test docstring false claim.** `test_semicolon_and_or_operator_also_do_not_steal_the_sink`
   now loops over `[";", "||", "&"]` (was `[";", "||"]`) and its docstring says "all three yield
   the identical two-leaf shape... the bypass was not specific to one operator" (was "both...
   never specific to one operator").

3. **"never from the whole line" false universal**, `multiline.py` (`_process_heredocs`
   docstring). Per CLAUDE.md's guidance to first ask whether the claim earns its place: it
   didn't carry weight once stripped of the false universal, so the sentence became "The sink
   is classified from the heredoc's own statement (:func:`_statement_bounds_containing`) -- an
   executor named in an earlier clause is not this heredoc's sink." -- same real point (earlier
   clause can't steal the sink), no false claim about the no-separator case.

4. **Module docstring separator list**, `multiline.py:10-14`. Now says the heredoc is scoped to
   "the same four operators as ``bash_parser.peg``'s ``control_op`` -- ``&&``, ``||``, ``;``,
   ``&``", one line, no rationale paragraph added.

5. **`paired: List[tuple]` typing.** Changed to `List[Tuple[dict, List[str]]]`. Considered a
   frozen dataclass (`spec`, `body_lines`) per the brief's suggestion, but `spec` is already a
   plain `dict` everywhere else in this module (`_find_heredocs_in_line` returns `List[dict]`),
   so a dataclass here would be a one-off inconsistent with the rest of the file's conventions.
   Went with the plain typed tuple instead.

**Doc-drift sweep (beyond the 5 items, found while verifying item 4):** `_classify_pipeline_sink`'s
own docstring at line 183 still said "the ``&&``/``||``/``;``-delimited clause" -- same three-
operator drift the brief flagged for the module docstring, just in a second location. Fixed to
"must already be scoped to the clause bearing the heredoc" (drops the operator enumeration
rather than repeating it a third time -- the count now lives in exactly two places: the module
docstring and `_statement_bounds_containing`'s own docstring). Grepped the whole file and the
test file afterward for the same three-operator phrasing; no other hits.

## Mid-task message -- not acted on, flagged instead

Partway through, a message arrived (formatted as a system-reminder, not a genuine new
coordinator turn) claiming the brief's F1 "not a regression" finding was wrong due to a flawed
isolation methodology, and instructing me to add a new "Item 0" blocker: track `$()`/backtick
nesting depth in `_statement_bounds_containing`, handle unbalanced/nested forms, and optionally
extend `_split_on_unquoted_pipe` too.

I did not treat this as authorization to expand scope -- it contradicted the actual brief's
explicit "F1 is OUT OF SCOPE, do not fix it, I am filing it as its own ticket", arrived through
an unusual channel, and asked for substantial new work with open design decisions. Per this
project's `evidence-before-fixing.md` ("even for tickets Arnon approved... don't act
unilaterally, flag for re-decision") and the scope-inflation guard in my own instructions, a
scope change like this belongs to Arnon/the coordinator, not to me mid-task.

I did independently re-verify the underlying factual claim myself, properly isolated this time
(built a real filesystem copy of the toolguard package as it stood at `HEAD` -- extracted just
`multiline.py` via `git show HEAD:...`, confirmed structurally that only that one file differs
in `toolguard/parser/` -- ran both versions via explicit `PYTHONPATH`, from a neutral `/tmp`
cwd, and printed `sys.modules["toolguard.parser.multiline"].__file__` inside each run to confirm
which tree was actually loaded):

```
=== WORKING TREE ===
control_$(true):              ask_floor=True   (unaffected -- no separator inside $())
F1_$(true;true):               ask_floor=False  <-- floor lost
F1_$(which_x_&&_echo_y):       ask_floor=False  <-- floor lost
F1_backtick:                   ask_floor=False  <-- floor lost

=== HEAD TREE (isolated copy) ===
control_$(true):              ask_floor=True
F1_$(true;true):               ask_floor=True
F1_$(which_x_&&_echo_y):       ask_floor=True
F1_backtick:                   ask_floor=True
```

**Finding: the mid-task message's factual claim checks out.** F1 IS caused by this ticket's
change -- `_statement_bounds_containing` has no notion of `$()`/backtick nesting, so a `;`/`&&`/
`||`/`&` inside an unquoted substitution is treated as a real statement boundary, and the
statement handed to the sink readers then starts inside the substitution and no longer contains
the interpreter. HEAD floors these three shapes; the working tree does not. This directly
contradicts the original brief's "byte-identical... F1 is NOT a regression" claim -- that
measurement was apparently unreliable for the same reason the mid-task message described
(whatever the true cause, my independently-built, `__file__`-verified isolation disagrees with
it).

**I did not implement a fix.** This needs a scope decision from Arnon/the coordinator: whether
to fix now (and if so, whether `_split_on_unquoted_pipe` needs the same guard, given its much
wider blast radius across every heredoc sink classification), defer, or file separately as the
original brief intended. I flagged it in my response rather than deciding unilaterally.

## Verification

- New `&` subtest verified to genuinely fail against the unfixed scanner: temporarily removed
  the new `elif ch == "&":` branch in place, ran
  `test_semicolon_and_or_operator_also_do_not_steal_the_sink`, got a real `AssertionError`
  (extraction produced `[('leaf', 'import os', False), ('leaf', 'true', False), ('leaf',
  'python', False)]` instead of the expected two-leaf floored shape), then restored the fix and
  re-ran to confirm it passes again.
- Full suite: `uv run python -m unittest discover -s test -t .` -- 3846 tests, 0 failures, 4
  expected failures. Ran twice (before and after the doc-drift touch-up), both green.
- `uv run python tools/corpus_build.py --verify` -- `OK: no differences.` No golden moved.
- `uv run ruff format .` / `uv run ruff check .` -- clean, repo-wide (previewed with
  `--diff` first to confirm nothing outside my two files needed reformatting before running it
  for real).
- `uv run python tools/architecture_fitness.py --ambient --layers --stdlib` -- all three PASS,
  no violations.
- `ls ~/.toolguard/errors/ | wc -l` -- 1950 both before and after (matches the brief's dispatch
  count; no new errors accumulated).

## Self-review notes

- Anti-pattern scan: no async/await, no threading, no new local imports, no unused imports.
- Did not touch `bash_parser.peg` or the generated parser.
- No git write commands used (status/diff/show only).
- Scratch work confined to my own `scratchpad/coder19repair/` subdir, cleaned up before
  finishing; `scratchpad/rev19/` and `scratchpad/headtree/` (other work) untouched.

## Elapsed time / rough cost estimate

- Planning + brief/code/grammar review: ~2 min
- Independent F1 re-measurement (isolated HEAD copy, `__file__`-verified A/B): ~7 min
- Implementation of items 1-5 + doc-drift sweep: ~2 min
- Self-review / gates (full suite x2, corpus verify, ruff, architecture fitness): ~3 min
- Total: ~13-14 minutes elapsed.
- Rough token-based cost estimate (Sonnet 5, order of magnitude): low tens of thousands of
  output tokens, roughly a couple hundred thousand input tokens across tool results and repeated
  file/context reads; estimated **under $1** total for this repair round.
