---
title: 18-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/18-estimate-uncertainties
---

# TOO-45 proposed-ticket 18 — uncertainties (BLINDED)

## What I was most unsure about

1. **The 20 indirect test failures are the crux of this estimate, and the ticket itself says its
   two measurements disagree.** I have no independent way to arbitrate between run A and run B —
   I ranked by cross-run corroboration and by named evidence in the prose (the
   `test_consolidation_preserves_prefix_extension_commands` docstring, the precisely-located
   `test_api.py` case), but for the files named in only one run
   (`test_tools_redundancy.py`, `test_tools_edit_proposal.py`, `test_verdict_corpus.py`) I am
   essentially guessing which of two internally-inconsistent lists is closer to the eventual
   truth, or whether the real answer is a third list neither run produced. The ticket also
   flags that "That run reported '22 above the floor' while its own breakdown sums to 20" — so
   even the most-trusted run has an internal count that doesn't add up, which lowers my
   confidence in treating any of its numbers as precise.

2. **Whether downstream breakage requires production-code changes or only test/fixture changes.**
   I inferred "test-only" from the ticket's language ("indirect," "the matcher's own tests do not
   notice," failures detected "through effect on higher-level analysers, not through any assertion
   about matching"), but this is an inference from prose framing, not something I could check
   against the actual modules. If `consolidate.py`, `redundancy.py`, `maintenance.py`, or
   `edit_proposal.py` hard-code any expectations derived from the old over-match behaviour (not
   just their tests), my "production — modified: none expected [beyond permissions.py]" call is
   wrong in a way I can't currently detect.

3. **Whether a verdict-corpus *data* artifact exists outside the file inventory I was given.**
   The ticket instructs "Replay the verdict corpus before and after" and separately mentions
   "corpus regeneration" as a consequence. The inventory lists `test/verdict_corpus/__init__.py`
   and `fixture_loader.py` (both `.py`) plus a dev-only `tools/corpus_build.py` that "builds and
   verifies" the corpus, but the inventory is Python-module-only, so if the corpus itself lives in
   a non-`.py` data file (JSON/TOML/similar) under `test/verdict_corpus/` or elsewhere, I have no
   visibility into it and could not predict its path. I did not include such a file in either
   output because I couldn't name it, not because I think it's unlikely to change.

4. **Whether `pattern_overlap.py` and `uninstall_readiness.py` are in-scope for *this* ticket or a
   follow-on.** The ticket hedges both ("fix in the same ticket or immediately after," and the
   uninstall-readiness docstring claim arguably becomes *true* once the matcher is fixed, needing
   no edit at all). I kept both at low/low-medium confidence rather than dropping them, but I
   would not be surprised either way.

## What I would drop first if told I over-predicted

In order:

1. `test/unit/test_tools_edit_proposal.py` and `test/unit/test_tools_redundancy.py` — each is
   corroborated by only one of the two disagreeing runs, with no independent supporting detail in
   the ticket prose the way `test_api.py` and `test_tools_consolidate.py` have.
2. `test/unit/test_verdict_corpus.py` — plausible on general grounds (the ticket does say to
   replay the corpus) but not named by either failure-count run as a *test* that fails; it may be
   that the corpus data changes without any assertion in this specific file breaking.
3. `toolguard/tools/pattern_overlap.py` and `toolguard/tools/uninstall_readiness.py` — both
   explicitly hedged as maybe-deferred or maybe-already-correct-post-fix in the ticket itself.
4. `test/unit/test_patterns.py` — included on the "two files that test matching" pairing, but the
   defect is entirely inside `permissions.py`'s branch, and `patterns.py` is a different module
   (GLOB/NATIVE-flavoured); it's plausible the new coverage lands entirely in
   `test_permissions.py` and `test_patterns.py` isn't touched at all.

The one prediction I would **not** drop is `toolguard/permissions.py` (defect site, stated
explicitly by line number) and `test/unit/test_api.py` (the one downstream failure the ticket
traces to a specific test by name and mechanism).

## Declaration

**Files read, in full, per the task's explicit allowance:**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/18-default-multitoken-prefix-over-match.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-18.md`

No other file, source module, test, ticket, report, or git history was opened. I ran one `Bash`
command, `mkdir -p .../reports/surprise`, to ensure the output directory existed — it did not read
or reveal any file content.

**Unsolicited project context that reached me and that I noticed:**

- A large `CLAUDE.md`-derived system prompt (global `~/.claude/CLAUDE.md` and project
  `/home/arnon/projects/toolguard/CLAUDE.md`) was present in my context before I read anything.
  I did not use its ticket-workflow or coding-convention content to inform the touch-set
  prediction itself, but I was aware, from this general background, that toolguard has a layered
  architecture (`.pyscn.toml`/`architecture_fitness.py`) and that `permissions.py` sits in the
  "engine" layer per the layer map given in the briefing file — that layer-map awareness came
  from the briefing file itself (an allowed read), not the CLAUDE.md, but the CLAUDE.md's
  description of "Two architectural constraints" (stdlib-only runtime, PEG-grammar-only bash
  parsing) primed me to expect the fix would *not* touch `toolguard/parser/*` even though the
  ticket's own text gave no reason to suspect the parser either. I don't believe this changed any
  specific file prediction, but I flag it because the instructions ask me to declare priming I
  can't fully rule out.
- A memory index (`MEMORY.md`) with entries specific to this project and this ticket family was
  present, including entries about TOO-45 test-repair work, ruff/pyscn quirks, and prior TOO-45
  punch-list items. I did not use any of it as evidence for file predictions — none of those
  entries mention this specific defect (multi-token prefix over-match) — but its mere presence
  told me this is a mature, actively-worked codebase with an established test-repair rhythm
  (`test-repair plan.md` is visible in the git-status listing below), which may have made me more
  willing to predict a wide test-file blast radius than I would in an unfamiliar codebase.
- The initial `gitStatus` block (shown automatically, not something I requested) listed modified
  and untracked files, including `test/unit/test_ask_resolution.py`, `test/unit/test_bash_parser.py`,
  `test/unit/test_compound.py`, `test/unit/test_hard_deny.py`, `test/unit/test_hierarchical.py`,
  `test/unit/test_multiline_bash.py`, `test/unit/test_patterns.py`, `test/unit/test_permission_resolution.py`,
  `test/unit/test_permissions.py`, `test/unit/test_rule_sort.py`, `test/unit/test_tools_danger.py`,
  `test/unit/test_tools_redundancy.py` as already modified (`M`) in the working tree, plus a long
  list of untracked `toolguard-memories/TOO-45/...` files. **This is a genuine leak risk**: several
  of these already-modified files (`test_permissions.py`, `test_patterns.py`,
  `test_tools_redundancy.py`, `test_hard_deny.py`) overlap with files I predicted above. I want to
  be explicit that I cannot fully separate "I predicted this from the ticket's own reasoning" from
  "I predicted this partly because git status already showed it as dirty before I started." The
  ticket's own text independently supports my predictions for `test_permissions.py` (explicit
  "Test obligation" section) and `test_tools_redundancy.py` (named in run A), so those two don't
  depend on the leak. But I cannot rule out that seeing `test_patterns.py` and `test_hard_deny.py`
  already flagged as modified in git status raised my prior on them before I'd finished reasoning
  from the ticket text alone — for `test_patterns.py` this is consistent with (not contradicted
  by) my medium confidence there; for `test_hard_deny.py` I predicted the opposite (explicitly
  NOT touched), so if the leak biased me at all here, it biased me toward a prediction I
  ultimately rejected on the ticket's own explicit disclaimer, not toward one I accepted.
- No other files were opened via the memory index, and I did not follow any basic-memory link,
  did not run `git log`/`git diff`/`git show`, and did not open any file under
  `toolguard-memories/` beyond the one ticket file named in the task.