---
title: TOO-45 item 39 -- blinded touch-set estimate (uncertainties and declaration)
tags:
- TOO-45
- proposed-tickets
- surprise-estimate
permalink: toolguard/too-45/reports/surprise/39-estimate-uncertainties
---

# 39 -- write guard loss check is placement-blind: uncertainties

## What I was most unsure about

1. **Whether the generalization changes `verified_write_config`'s signature or return shape.**
   The original filing said the "real" fix needs `expected_patterns` to carry
   `(list_identity, pattern)` pairs and that this "touches every caller." The amendment reads
   to me as retiring that plan in favour of a narrower, same-signature fix, but it doesn't say
   in so many words "the signature does not change" -- I inferred that from "needs no pattern
   semantics and no matcher" plus the absence of any caller in the amendment's own measurement
   table. If the refusal message needs to name *which* tier lost a pattern (a plausible UX
   improvement bundled into the same fix), that's still an internal string change, not a
   signature change, but I could be wrong about where that line falls.

2. **How much of the diff lands in tests vs. production.** I don't know the internal shape of
   `_hard_deny_patterns` or step 3 well enough (I did not read the file) to know whether
   generalizing it is a 5-line change or a 40-line change with a new small helper type. I
   predicted the test file carries more lines than the production file, but that's a guess
   about test-writing style in this repo, not something I measured.

3. **Whether a doc file gets touched.** `config_write_guard.py`'s own docstring is very likely
   edited (the amendment quotes step 3's docstring language directly: "a hard deny turned into
   an allow is a loss even though nothing looks missing" -- generalizing the code without
   updating that sentence would leave the docstring narrower than the behaviour). That's
   already folded into my "modified" prediction for the one file. What I could not assess is
   whether this warrants a `docs/` or `technical-notes.md` update, since the file inventory I
   was given only covers `toolguard/`, `tools/`, and `test/` -- I have no docstring or content
   for anything under `docs/`. I left it out of the formal touch-set tables since I have no
   evidence either way, but flag it here as a real gap in my instrument, not a considered "no."

## Which predictions I would drop first if told I over-predicted

Nothing in my touch-set tables is speculative padding -- I predicted exactly two files. If told
the actual diff is even narrower than that, the thing I'd reconsider first is whether the test
file needed *new* test methods at all, versus just editing the one pinned characterization test
in place (fewer added lines, same file). That's a within-file granularity question, not a
different file, so it wouldn't change the table -- but it's the softest part of the estimate.

## Declaration

**Files read, in full:**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/39-write-guard-loss-check-is-placement-blind.md`
   -- the ticket, including the original filing and the 2026-08-20 status amendment.
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-39.md`
   -- the file inventory (path, line count, first docstring line for every module in
   `toolguard/`, `tools/`, `test/`) and the declared `.pyscn.toml` layer map.

No other file was opened. I did not read `config_write_guard.py`, `test_config_write_guard.py`,
any other source or test file, any other ticket, any report, or git history.

**Context that reached me without being deliberately given, and that I used:**

- The full project `CLAUDE.md` and global `~/.claude/CLAUDE.md` were present in my system
  prompt (architectural constraints: stdlib-only runtime, PEG-grammar-only bash parsing;
  testing conventions; comment-brevity conventions; disclosure rules). I did not use the
  bash-grammar or stdlib-only constraints directly since this ticket has nothing to do with the
  parser, but I did lean on the general shape of "prefer the narrow, same-layer fix, don't
  invert architecture" as a prior when reading the amendment's own argument for the narrow
  scope -- that prior was already present in my training/system context independent of this
  ticket, and I can't fully separate "the amendment argues this" from "CLAUDE.md's layering
  fitness-check culture primed me to find that argument persuasive."
- The `MEMORY.md` auto-memory index was present, including a toolguard-project section. I
  noticed `[Grammar changes in two phases]`, `[no_match_fallback + undecidable]`, and other
  toolguard-specific entries but none of them named `config_write_guard.py` or this defect, so I
  don't believe they biased the specific prediction. I did notice
  `[Comment review finds CODE bugs, ~40 so far]`, which primed an expectation that this campaign
  (test-repair / comment-review) tends to find placement/scope bugs rather than deep semantic
  ones -- consistent with, and possibly reinforcing, my narrow-scope prediction rather than an
  independent check on it.
- The git status block at the session start listed modified test files (`test_hard_deny.py`,
  `test_permissions.py`, `test_rule_sort.py`, etc.) and new memory/report files under
  `toolguard-memories/TOO-45/`. I did not use any filename from that list in my predictions --
  none of the listed modified files is `config_write_guard.py` or its test, so if anything this
  is mild evidence *against* my own prediction being contaminated by "what's already dirty in
  the tree," but I'm declaring it since it was present and visible.
- `currentDate` (2026-08-20) matched the amendment's own dated measurement, which I used only to
  confirm I was reading the current amendment rather than a stale one -- not as independent
  evidence about scope.

I did not use code-review-graph, LSP/pyright, or any search tool against the source tree for
this task.