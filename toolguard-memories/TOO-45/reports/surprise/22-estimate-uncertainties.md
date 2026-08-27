---
title: 22-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/22-estimate-uncertainties
---

# TOO-45 Ticket 22 — Blinded Touch-Set Estimate: Uncertainties

## What I'm most unsure about, and why

1. **Whether RD1's policy decision (normalise-like-matcher vs. label-as-spelling-duplicate) touches
   `hierarchy.py` at all, beyond inheriting the behaviour change for free.** The ticket says
   hierarchy "imports `_normalised_body` and inherits this, while saying nothing about it" — that
   sentence could mean the fix is silent from hierarchy's side (behaviour changes, no lines change
   there), or it could mean hierarchy needs to start saying something about it once RD1 is decided
   (e.g. propagate a "spelling duplicate" label into its own findings). I hedged this as a
   secondary, unconfirmed touch in the predictions file. I have no strong signal either way from
   the two files I was given.

2. **Whether `test_tools_maintenance.py` is touched.** I based this only on the pin note stressing
   that these findings "reach an operator... via `maintenance.py:193`" for a different, already-fixed
   finding (HR1). I don't know whether maintenance's own tests pin exact note text for the three
   still-open finding types (HR2/RD1/RD2), or only exercise maintenance's aggregation/formatting
   logic against fixture findings with arbitrary note strings. This is a genuine coin-flip, not a
   confident medium.

3. **Whether the RD1 decision changes shape rather than just behaviour.** "Label the findings
   explicitly as spelling duplicates that may not be behavioural ones" (fix direction #4, option B)
   reads to me like it could add a new field or finding subtype, which would break my "no new
   structural elements" prediction for that piece specifically — even though I predicted no new
   fields for HR2. I did not fully reconcile this tension: my "Prose or structure" answer is scoped
   to HR2 only, and I did not extend the same confidence to RD1, which could go either way (reword
   only vs. add a label field) depending on which of the two RD1 options is chosen.

4. **Line-count magnitude.** I have file lengths but no diff history and no view of the actual
   functions (`_config_without_allow`, `_normalised_body`, the note-generating call site at
   `hierarchy.py:400`), so I cannot estimate whether this is a 20-line fix or a 150-line fix. My
   "concentration set" claim is about *where* the lines land, not *how many* there are.

## What I would drop first if told I over-predicted

In order:

1. **`test/unit/test_tools_maintenance.py`** — this was my lowest-confidence row and the one most
   likely to be padding; I included it mainly because the pin note foregrounds the maintenance
   consumer, not because I have direct evidence its tests assert note text.
2. **The "secondary touch" hedge on `hierarchy.py`** for the RD1 label-propagation scenario — if
   told the RD1 decision went the "normalise like the matcher" way (not the "label explicitly"
   way), this touch disappears entirely and `hierarchy.py`'s only change is the HR2 string.
3. **Any expectation of line volume in `redundancy.py` beyond the two named functions** —
   if the actual fix is narrower than I assumed (e.g. RD1's decision turns out to be "keep the
   coarse key, do nothing structural, just add one sentence to the docstring"), my prediction that
   `redundancy.py` is the single largest file by changed lines would be the first magnitude claim
   to fall.

## Declaration

**Files actually read (exactly two, as instructed):**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/22-redundancy-analyzers-report-unsafe-deletions-as-safe.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-22.md`

No source file, test file, other ticket, report, git history, or directory listing was opened.

**Unsolicited context that reached me, and whether I used it:**

- A large `<system-reminder>` block containing the user's global `CLAUDE.md`, this project's
  `CLAUDE.md`, and two project rule files (`native-fidelity-claims.md`, `evidence-before-fixing.md`),
  plus `MEMORY.md` auto-memory content, was present in the system prompt before the task
  instructions arrived. This included substantial TOO-45 project history (e.g. the "Prose is
  output, not a data structure" section, which cites this same redundancy-analyzer investigation as
  its motivating example, and the "evidence-before-fixing" rule referencing sudo/ticket-78/ticket-18
  measurement work). **I used the "Prose is output, not a data structure" section** as part of my
  reasoning for the "Prose or structure" answer — both to explain what the *general pattern* would
  look like if it applied, and to explain why I judged it did *not* apply here (the fact doesn't
  need to survive a round-trip through prose to reach a second consumer, unlike the cited
  compound-allow logging case). I did not use any ticket-numbered specifics from that memory (e.g.
  ticket 78's replay counts, ticket 18's curl-colon defect) since they concern unrelated tickets.
  I did not use the `evidence-before-fixing` corpus-counting procedure, since this task explicitly
  said not to fix anything and not to open logs.
- A later system reminder announced a date change ("today's date is now 2026-08-21") and instructed
  me not to mention it. Not used in any prediction; noted here only because the instructions asked
  me to log unsolicited context that reached me.
- Two further system reminders listed available subagent types and MCP server instructions
  (code-review-graph, context7). Not used — the task instructions barred me from any tool beyond
  reading the two named files and writing the two output files, and I did not invoke any agent, MCP
  tool, or search.
- A system reminder listing available skills (code-review, denied-summary, critical-thinking, etc.)
  was present. Not invoked; none apply to a read-two-files-write-two-files measurement task.

I did not open `hierarchy.py`, `redundancy.py`, `maintenance.py`, or either test file directly —
everything above about their likely content is inference from the two files read plus the
memory/CLAUDE.md context disclosed above, not direct observation.