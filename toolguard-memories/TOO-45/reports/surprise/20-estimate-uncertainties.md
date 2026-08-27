---
title: 20-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/20-estimate-uncertainties
---

# TOO-45 proposed-ticket 20 — uncertainties

## What I'm most unsure about, and why

1. **Whether `_static_prefix_of` actually lives in `consolidate.py`.** The
   ticket text never states its module — it's used without a qualified
   name, unlike `_check_family2_safe (consolidate.py:582-596)` and
   `_literal_prefix_specificity (permissions.py:276)`, both of which are
   given explicit locations. I inferred `consolidate.py` because the
   surrounding family-2 gate is located there and the module is described
   as the one under audit, but `toolguard/tools/pattern_overlap.py`'s
   docstring ("Command-prefix overlap tests for DEFAULT `cmd:*`/`cmd:**`
   patterns") is a plausible alternative home I cannot rule out from the
   inventory line alone (I only have its first docstring line, not its
   contents).

2. **Whether the RA1 "approval surface" finding is in or out of scope.**
   It's physically part of the ticket 20 markdown file (same document,
   under `## The approval surface shows more than what was approved`), but
   it's explicitly cross-referenced as its own tracking label (`RA1`) in a
   different report. I read that as "documented here, fixed elsewhere," but
   the ticket file doesn't say so outright — it's an inference from the
   labelling convention, and I have no visibility into how `follow-up-queue.md`
   actually scopes tickets since I wasn't allowed to open it.

3. **Whether the fix changes the gate's return type (bool -> tri-state) or
   just its logic.** The 2026-08-20 amendment lays out three "defensible
   answers" and says "the ticket should state which and why" — meaning even
   the ticket's own author hadn't decided at the time this snapshot was
   written. If the actual implementation picks option 1 (refuse without a
   corpus) rather than option 2 (tri-state return), the blast radius is
   smaller and more localized to `consolidate.py`'s branching, with less
   ripple into whatever consumes the gate's return value elsewhere in the
   same file.

4. **Whether `maintenance.py`'s three "equivalence-preserving" sites are a
   substantial edit or a one-line-each wording fix.** I have no line
   numbers for them, only "three places" and "positive property" — could be
   docstring sentences or could be user-facing report text with more
   surface area than I'm predicting.

## What I'd drop FIRST if told I over-predicted

In order of how readily I'd retract them:

1. `toolguard/permissions.py` and `toolguard/tools/pattern_overlap.py` in
   "Production modified" — both are already flagged low-confidence and
   exist mainly as hedges against not knowing exactly where
   `_static_prefix_of` lives.
2. `toolguard/tools/rule_apply.py` and `toolguard/rule_sort.py` (and their
   test counterparts) — the RA1 speculative inclusion. My own scope
   reasoning already argues these are out of scope; I'd drop them first if
   the actual diff confirms RA1 was filed as a separate ticket.
3. `test/unit/test_pattern_overlap.py` — entirely conditional on
   `pattern_overlap.py` being touched at all.
4. The secondary concentration claim on `maintenance.py` /
   `test_tools_maintenance.py` — if the actual fix threads the corpus with
   a smaller change than I expect (e.g. a default-parameter shim instead of
   updating the call site's arguments), this pair could see near-zero
   lines changed rather than "small but real."

I would NOT drop `consolidate.py` or `test_tools_consolidate.py` from the
concentration set without being told the whole approach changed — every
named defect in the ticket text traces back to that one module.

## Declaration

**Files actually read** (exactly the two assigned, nothing else):

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/20-consolidation-safety-claims-are-false.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-20.md`

**Unsolicited context that reached me, and whether I used it:**

- A large `CLAUDE.md`-derived system-reminder block (global user directives
  plus this project's own CLAUDE.md, plus two rule files:
  `native-fidelity-claims.md` and `evidence-before-fixing.md`) was present
  in my context before I read either assigned file. I did not use any of
  its ticket-specific or code-specific content in forming the predictions
  above — it's process/workflow guidance, not information about ticket 20's
  actual file scope. It did shape *how* I wrote the two output files (e.g.
  using tables, avoiding hard-wrapped prose per the markdown-authoring
  rule) but not *what* I predicted.
- A `gitStatus` block was present, showing modified/untracked files on the
  current branch (`too-45`), including several already-modified test files
  (`test_ask_resolution.py`, `test_bash_parser.py`, `test_compound.py`,
  `test_hard_deny.py`, `test_hierarchical.py`, `test_multiline_bash.py`,
  `test_patterns.py`, `test_permission_resolution.py`, `test_permissions.py`,
  `test_rule_sort.py`, `test_tools_danger.py`, `test_tools_redundancy.py`)
  and a long list of untracked memory/report files. **I deliberately did
  not use this to inform predictions** — none of those modified files
  overlap with what I predicted for ticket 20 except `test_rule_sort.py`,
  and I flagged that file as low-confidence for reasons internal to the
  ticket text (the RA1 dependency), not because I saw it was already
  dirty. I'm noting this explicitly because seeing `test_rule_sort.py`
  already modified on the branch could have biased me toward or away from
  including it, and I want that risk on the record rather than silently
  absorbed.
- Two "current date" system-reminders (one saying 2026-08-13, a later one
  correcting to 2026-08-21) — irrelevant to file-scope prediction, not used.
- A long list of available tools/skills/agents and MCP server instructions
  — not used; no tool beyond Read (for the two assigned files) and Write
  (for these two outputs) was invoked.
- A mid-conversation system-reminder instructing me to "do your work
  through the Bash tool wherever it can accomplish the job" (auto-mode
  guidance) — I did not follow this for the deliverable files, since the
  task instructions explicitly said "Use the Write tool for both files."
  I treated the explicit task instruction as authoritative over the
  generic auto-mode nudge.