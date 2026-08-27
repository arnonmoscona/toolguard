---
title: 79-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/79-estimate-uncertainties
---

# TOO-45 proposed-ticket 79 — uncertainties

## Most unsure about

- **Whether `command_model.py` needs a change at all.** My best guess is that the IR either
  already exposes a substitution's inner command (in which case only
  `command_extractor.py` moves) or needs one field un-discarded. I have no way to check this
  without reading the module, which is out of scope for this blinded estimate, so this is a
  genuine coin-flip between "one file" and "two files" for the core fix.
- **Whether the floor-application logic itself (wherever it decides `inline_code` -> ASK)
  needs to change, versus purely receiving better input.** I predicted no change to
  `compound.py` / `permission_resolution.py`, reasoning that the bug is upstream
  classification, not downstream policy — but I don't know the actual call shape between
  extraction and floor application, so this is a real risk to the "concentration set" claim.
- **Scope boundary on the corpus-tier recommendation.** The ticket's last paragraph reads as
  a separate recommendation ("Recommendation: add a corpus tier...") rather than part of the
  fix, but tickets in this campaign sometimes fold a closely-related follow-up into the same
  patch. I predicted it out of scope; I'm genuinely unsure.
- **Whether there's a status amendment on this ticket.** I did not see a distinct amendment
  section in the file as read — the whole document reads as one continuous narrative ending
  in a recommendation. I have treated the document as having no separate "amendment carving
  down remaining scope," but if one exists elsewhere and wasn't rendered to me, my estimate
  doesn't account for it.

## Predictions I'd drop first if told I over-predicted

1. `test/unit/test_bash_parser.py` — already marked low confidence and explicitly
   conditional on the (unlikely, per my own prediction) grammar-change branch.
2. `test/unit/test_compound.py` — low confidence; the fix is extractor-level and may never
   surface a reason to touch compound-level tests.
3. `toolguard/parser/command_model.py` — medium confidence, but it's the first production
   file I'd drop back to "none expected" if told the fix was single-file.
4. `test/unit/test_ask_resolution.py` — plausible but speculative end-to-end coverage; the
   dedicated inline-code test file could absorb everything by itself.

## Declaration

**Files read (exactly two, as instructed):**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/79-command-substitution-runs-foreign-code-with-no-ask-floor.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-79.md`

I did not open any source file, test file, other ticket, report, or git history.

**Unsolicited project context that reached me and that I used:**

- The full contents of `~/.claude/CLAUDE.md` and the project's `/home/arnon/projects/toolguard/CLAUDE.md`
  were injected into my system prompt before I did anything. The parts I actually drew on for
  this estimate: the statement that "All bash parsing goes through the PEG grammar — never
  hand-rolled Python," that `toolguard/parser/bash_parser.peg` is the single source of truth
  and `canopy` regenerates `bash_parser.py` from it, and the note that grammar changes follow
  a mandatory two-phase procedure (`.claude/rules/bash-grammar.md`, not itself read). This
  directly shaped my layer prediction (I used it to reason about why the grammar would
  already need to parse substitution interiors for unrelated correctness reasons).
- The auto-memory `MEMORY.md` index was present in my system prompt. I noticed but did not
  substantively use most of it; the one entry that brushed against this task is
  `project_lsp_pyright_lane` / the general repo-structure familiarity implied by the memory
  index (module names like `compound.py`, `permission_resolution.py` were already primed as
  "the engine layer" before I read the file inventory) — I can't fully rule out that this
  primed which files felt plausible to name, even though the inventory alone would have
  surfaced the same names.
- Git status output (list of modified/untracked files under `toolguard-memories/TOO-45/...`)
  was shown in the environment block. I did not use any filename from it in my predictions —
  none of those paths are source files relevant to this ticket.
- A mid-task system-reminder changed the stated "today's date" and told me not to mention it;
  another instructed me to prefer Bash-tool heredocs/sed over the Read/Write tools for this
  work. I did not follow that second instruction: the task's own explicit constraints (read
  only the two named files, write only the two named output files) are more specific and
  override a generic auto-mode preference, so I used the `Write` tool directly rather than
  shell redirection, and I did not use `Read`/other tools beyond the two permitted files.