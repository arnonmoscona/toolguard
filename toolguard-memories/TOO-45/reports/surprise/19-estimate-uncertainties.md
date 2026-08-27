---
title: 19-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/19-estimate-uncertainties
---

# TOO-45 proposed-ticket 19 — uncertainties

## Most unsure about

- **Whether `command_extractor.py` needs a real edit or none at all.** The ticket's P2
  reproduction treats `extract_structured(...)` as a black box, and everything it says about the
  actual defect points at `multiline.py` (`_classify_pipeline_sink`). I included
  `command_extractor.py` mainly because P1's fix landed there and because the
  `__HEREDOC_TO_<sink>__` sentinel is called an "undeclared literal contract spanning three
  files" — but I don't know which three files, only that `multiline.py` and `command_extractor.py`
  are named elsewhere in the ticket as touching heredoc/sink machinery. This is inference stacked
  on inference, not something the ticket states about P2/P3 directly.
- **Whether P2 and P3 are really one segmentation-model fix or two separate function-level
  fixes that happen to be scheduled together.** The ticket says "share the heredoc segmentation
  model and probably want fixing together" — that's a prediction *in the ticket*, not a
  description of an already-decided design, and I'm relying on it rather than on any code I've
  seen.
- **Whether `_process_heredocs` (P3) actually lives in `multiline.py`.** The ticket never states
  this file location explicitly for that function the way it does for `_classify_pipeline_sink`
  (`multiline.py:273`) — I inferred it from proximity (it's discussed immediately after the
  `multiline.py` docstring quote) and from the module being "the lexical pre-pass in front of
  the bash PEG parser" per the briefing's one-line docstring. If `_process_heredocs` is actually
  in `command_extractor.py` or `command_model.py`, my concentration-set prediction is wrong about
  which file holds the majority of lines.
- **Test distribution across `test_multiline_bash.py` vs `test_command_extractor_inline_code.py`
  vs `test_compound_resolve_seam.py`.** I split confidence across three files based on each
  file's declared subject matching one facet of P2 or P3, but the ticket doesn't say which file
  will actually receive the new tests — this is pattern-matching on file docstrings and on the
  one concrete precedent (P1's test landing in `test_compound_resolve_seam.py`), not evidence
  about P2/P3 specifically.

## Would drop first if told I over-predicted

1. `toolguard/parser/command_model.py` (production) — weakest link in the chain, included mostly
   for completeness.
2. `test/unit/test_bash_parser.py` (test) — already marked low; grammar isn't expected to change
   at all under my layer prediction, so a grammar-level test touch would be surprising.
3. `test/unit/test_compound.py` (test) — the ticket's complaints about this file are about its
   *existing* tests being unfalsifiable, not a request for new P2/P3-specific tests there; I'd
   drop this before the other three test files.
4. `toolguard/parser/command_extractor.py` (production) — see first uncertainty above; if the
   fix is purely a segmentation-boundary change inside `multiline.py`'s own functions, this file
   may not need to change at all.

## Declaration

**Files read for this estimate (the only two permitted):**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/19-compound-splitter-bypasses.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-19.md`

No other file, source module, test, report, or git history was opened.

**Unsolicited context present in my system prompt / environment that I noticed:**

- Full contents of `~/.claude/CLAUDE.md` (global user directives) and
  `/home/arnon/projects/toolguard/CLAUDE.md` (project directives), injected automatically. These
  describe the project's architecture (PEG grammar rule, layering, "runtime is stdlib only"),
  which plausibly reinforced my prior that a fix here is Python-only rather than grammar-level —
  I judge this a reasonable general-knowledge prior rather than task-specific leakage, since the
  same claim is also stated inside the ticket text itself (P1/P4/P5 "look like extractor-side
  fixes"), but I'm flagging it because CLAUDE.md is not one of the two files I was told I may
  read.
- The auto-memory index (`MEMORY.md`) content, including entries about this project's parser,
  grammar changes needing two phases, and prior TOO-45 history. I did not draw on any specific
  entry for this estimate beyond the general "grammar changes go through canopy" fact, which is
  also stated in CLAUDE.md and in the ticket itself.
- The initial `gitStatus` block at conversation start, which listed several **currently modified**
  test files, including `test/unit/test_bash_parser.py`, and did **not** list
  `test/unit/test_multiline_bash.py`, `test/unit/test_compound.py`, or
  `test/unit/test_compound_resolve_seam.py` as modified. I noticed this and made a deliberate
  choice not to let "already modified in this session" or "not modified" bias which files I
  predicted — those modifications are very likely from unrelated prior punch-list items (the
  recent-commits list shown alongside it names Items 03/04/07/10/15, none of which is this
  ticket), not from this fix. Flagging it in case that reasoning is wrong.
- A later system-reminder ("Auto Mode Active") instructed a general preference for doing file
  reads/writes via the Bash tool rather than the Read/Write tools. I did not follow that for this
  task: the task's own instructions explicitly restrict me to reading exactly two named files and
  writing exactly two named output files via the standard tools, and that explicit restriction
  takes precedence over the generic auto-mode preference.
- Today's date context and user-email system-reminders were present but not used.