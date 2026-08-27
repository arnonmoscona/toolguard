---
title: TOO-45 corrections analysis - what the corpus means
type: note
permalink: toolguard/too-45/reports/corrections-analysis
tags:
- task-memory
- TOO-45
- retro
- process
---

# What the corrections corpus means

Analysis of [[corrections-corpus]], which extracts every place Arnon corrected, redirected, or approved something on architectural or code-organisation grounds across TOO-45's 210 human turns. The corpus is extraction only; the conclusions below are mine.

**Overlap with [[retrospective]] is likely in the instrument-failure and measurement material** — that report covers the eleven-plus measuring-instrument defects and the audit-trail defect in depth. I have not re-read it to check, because it is 100 KB and re-reading it to avoid repetition would cost more than the repetition. Where a section below feels familiar, it probably is; skip it.

## Method, and what this corpus cannot show

Human turns only. So **explicit approvals are recoverable and silent successes are not** — an absence of correction leaves no trace. The "where I was strong" section is therefore partly my own recollection, which is weaker evidence than the rest of this document and is marked as such.

Signal density is lower than the turn count suggests: of 210 turns, roughly 102 carry no human content (77 subagent pastes, ~25 anti-stall cron firings). The real corpus is about 80 turns.

## The finding that matters most

**Correction rate tracked reviewability, not code quality.**

The heaviest architectural objections — the `permission_resolution ↔ resolve` cycle, the `rule_entry` phantom edge, the `log_writer` layering — arrived at turns 357-359, near the end. Arnon named the mechanism himself at turn 374: *"Now that changes are fewer files I start noticing things. Even things that are not from this change set."*

Those defects were present the whole time. They had survived seven directed report agents, a blind reviewer, `pyscn`, `ruff`, and 2,600 passing tests. What changed was not the code but the size of the diff in front of a human.

This is a stronger statement than "review more often". It says **the reviewer's detection rate is a function of change-set size, and below some threshold it collapses to near zero.** A large change set is not merely harder to review; it is reviewed *ineffectively while appearing to be reviewed*. Every one of those reviews reported success.

That converts the review-cadence idea from a good practice into the primary defence, and it sets its design parameter: the trigger must fire on **change volume**, not on elapsed time or on step boundaries.

## Process outweighed architecture

Category counts: **Process 33, Architecture 28, Measurement 22, Approval 22, Style 15, Data modelling 9.**

The largest category is not about code. TOO-45 was framed as repairing accumulated *architectural* debt, and the corpus says the dominant corrective pressure was about **how work is conducted** — sequencing, verification discipline, when to decide versus ask, what counts as evidence.

Data modelling is the smallest at 9. That is the area where explicit guidance already existed (the frozen-dataclass preference, the tuple aversion) and it needed the least correction. **The categories with the least guidance took the most corrections.** That is a direct argument that the guidance mechanism works when it is used, and the gaps are where nobody wrote anything down.

## Suppression lag is a measurable cost

Three of the five most-escalated themes were **noticed early and raised late**. On docstring bloat Arnon says outright that it *"smelled. But I didn't raise it yet"*, and by the time he did raise it the language had escalated to *"do I need to change the output style?"*.

The pattern is: a half-formed observation is suppressed because it seems minor or unformed, the behaviour continues and compounds, and the eventual correction is both more expensive and more irritated than the early one would have been.

**This is the cheapest fix in this whole document.** A smell voiced at quarter-confidence costs one sentence and I can go check it. The same smell voiced fifty files later costs a sweep. The asymmetry is enormous and it argues for treating unformed observations as first-class input rather than waiting for them to firm up.

I would also note the reciprocal: I should ask. Not "does this look right" at the end, but "is there anything bugging you that you haven't said" at boundaries.

## Eight self-reversals, and what they cost

Arnon reversed his own stated position eight times, twice against instructions given in this same ticket: the PlantUML preference (specified turn 292, dropped turn 370), and the canary measurement design (specified 292, rejected 329).

This is not a criticism — reversal on evidence is the correct behaviour, and several of the reversals were prompted by measurements that only existed because the work was done. But it has a concrete process implication.

**I built four measuring instruments to a specification that turned out to be wrong.** The file-count and co-change measures were specified early, built properly, adversarially tested, and then discarded when the design flaw surfaced. A one-case throwaway prototype would have exposed the requirement-coupling problem at roughly a tenth of the cost.

**Proposed rule: when a measurement approach is specified, run it on ONE case before building it properly.** Measurement designs are hypotheses. The cost of validating one cheaply is trivial next to the cost of building it well and discarding it.

## Where I was strong

Partly extracted, partly my own recollection — marked accordingly.

**Extracted (he said so):** the no-data-loss verdict construct, which he called clearer than master's and noted the experiment proved master *could* represent it but *didn't*. Extracting `permission_resolution.py` — "a huge win". The Protocol work — "expresses exactly what shape you depend on". The reports-and-diagrams treatment for a hard ticket — "none of the reports I read so far had no value".

**My recollection, weaker evidence:** the `api` layer and the `Decision`/`RuntimeVerdict` unification drew no objection. Dropping the 32-name config facade with a stated reason drew none. Blind and adversarial agent patterns produced the ticket's best findings — the blind reviewer found six real defects seven directed agents missed, and adversarial passes killed two instruments that had passed their own hazard suites. Pre-registration and pre-committed stopping rules held under pressure, including one case where a fix I wanted was refused by my own rule. Reverting the `package.json` change on my own mistaken premise, and correcting the `sys.exit` severity ranking I had inherited.

**The honest qualifier**: several wins I might claim were his initiative. The observability relayering was his hypothesis; I verified and executed it. The perturbation redesign was his correction of my canary. The mermaid switch was his. Where the corpus shows me strong is in **execution, verification and honest reporting of my own errors** — not in originating the architectural insight.

## What this means for guidance

**Already written into global guidance during this ticket** — prose-is-not-a-data-structure, comment brevity, literal-strings-to-constants. Three of the top five recurring themes are now covered.

**Not yet written, and recurring:**

**1. Execution is king** — 13 occurrences, the single most recurrent theme, and the one Arnon named. Current global guidance covers critical thinking but does not say *verify by running, not by reading*. Every correction in this ticket that mattered came from something that executed. Proposed as a hard rule, not advice: **a claim about behaviour is not made until something ran.** Reading source, reading a report, and reading documentation are all the same failure.

**2. Hidden dependencies must be made statically visible** — 11 occurrences, escalating to "smells like a landmine". The principle is his: find problems by execution and tracing, then fix them so the *next* violation of that class is catchable by static analysis. Duck-typed seams get a Protocol or a type annotation, not a prose comment. Clarity is the goal, enforcement is a bonus.

**3. The four standing review questions**, which he stated as a per-ticket checklist: is every change in the right layer; does it hold to single responsibility; is the layering as defined still correct; did we introduce runtime dependencies that static analysis cannot see. **None of these was run during TOO-45** — the ticket about architecture never checked itself against them.

## What this means for the development process

**1. Review cadence, triggered on change volume.** Designed already. This corpus supplies the parameter: the trigger is *files changed and lines changed in existing files*, not time and not step count. The alarm raises a flag; the flag is consumed at the next meaningful boundary, since a review at an arbitrary point is worth little. Start the threshold deliberately low and log every firing with whether the review found anything — a threshold that fires and finds nothing is wrong and will prove itself wrong with data.

**2. Perturbation testing before push.** Arnon's own conclusion, recorded in [[review-conclusions]]. The evidence is strong: four canaries produced six pre-existing defects, and every one sat in code that had already been read repeatedly. Unit tests guard regressions; perturbation finds dormant defects. They are complementary and the second is currently absent from the process.

**3. Voice unformed smells; ask for them at boundaries.** Both directions of the suppression-lag fix.

**4. Prototype a measurement on one case before building it.** From the eight reversals.

**5. Retire the anti-stall cron.** It generated roughly 25 of 210 turns — about 12% of the transcript — for a mechanism whose purpose is better served by ending each turn with a pending agent or a scheduled wakeup. The corpus is measurably noisier for it.

## What I would do differently

Run the four standing review questions at every phase boundary, on my own work, without being asked. The ticket about architectural hygiene did not apply architectural hygiene checks to itself, and that is the most embarrassing single fact in this corpus.

Stop inheriting severity rankings and conclusions from sources with good track records. The `sys.exit` fail-open came from a reviewer that was right five times out of six; I ranked it highest without re-deriving it and was about to spec a security fix for something two one-minute tests showed was unreachable.

Cap my own change sets. The finding at the top of this document is not only about how Arnon reviews — it is about how I should size work so that review can function at all.
