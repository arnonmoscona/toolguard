---
title: TOO-45 review conclusions (Arnon)
type: note
permalink: toolguard/too-45/reports/review-conclusions
tags:
- task-memory
- TOO-45
- process
---

# Review conclusions — Arnon, 2026-08-07

Arnon's own conclusions from reading the TOO-45 report set. Recorded verbatim in substance so they survive into the retrospective discussion and the process changes that follow it. **The retrospective discussion happens at or after the push, not before** — there will be more material by then.

## Perturbation testing is the headline takeaway

The change-cost instrument was not thought through. That co-change was coupled to a heavy requirement was noticed far too late. **Replacing it with perturbation — small change-requirements implemented by blinded agents — was a big win.**

**The value is in the surprises.** Most perturbations did not produce the anticipated result; sometimes they did. A method with a proclivity to produce unexpected, real, and resolvable feedback carries more than its weight.

The contrast that matters: **high-coverage unit testing is necessary but mainly guards against regressions, and is well known to rarely uncover dormant bugs.** Randomized perturbation by blinded agents does the opposite — it surfaces issues nobody thought of, not by design but by stress-testing the system against changing requirements.

**Carry forward as a pre-push activity: a well-understood way to conduct a fishing expedition.**

Also worth naming: this technique is **uniquely practical with agents and too labour-intensive to be worth doing manually**, which is why it does not appear much in SDLC literature. Analogues exist in other engineering disciplines.

## Co-change needs an expected-surface baseline

Co-change as a stand-alone metric is only useful **against the apparent expected change surface of the requirement**. Forming that expectation from the requirement and file names alone — deliberately blind to file contents — is a good gauge for scoring after-the-fact co-change. Also a candidate pre-push activity.

**But subjective ease of review remains the strongest signal**, and the review-cadence methodology is a good start on capturing it.

## `config.py` being large is not itself the problem

Toolguard's configuration semantics are by construction rich, layered, and require provenance and complete logging. Size follows from that. **The thing to guard is entanglement between config code and decision code**, which is what the pre-TOO-45 state had.

Standing review questions, to be applied per ticket:

- Is every change in this ticket done in the right layer?
- Are we holding to the single responsibility principle?
- Is the layering as defined still correct, or does it need tweaking?
- Did we introduce runtime dependencies that are not statically resolvable and not enforceable by static analysis tooling?

## Execution is king

To hold a first-class place in the development process. To be gone into deeply in the retrospective, with the process and its guidance amended according to the conclusions.

## On gameability, and the detect/enforce split

Any metric or rule is gameable; the real questions are **how you detect issues and how you enforce them**.

**It is easy to hide from static analysis and hard to hide from observed runtime behaviour.** So: find problems by execution and tracing, then fix them not only by reorganising code but by **making new violations of the same class discoverable by static analysis**. Still gameable, but it improves at every step.

That is exactly what was done here — runtime tracing found the upward and circular dependencies, the fix removed one cycle outright, and Protocol classes now express the remaining seam formally and statically discoverably.

## On the report-and-diagram pattern

Writing multiple ticket-specific reports illustrated with small focused diagrams **paid off for a large ticket, and is probably unnecessary for small ones**. No report in the set was without value.

**The trigger is "this one is tough"** — when Arnon judges he does not understand a set of changes well enough, this effort helps a great deal.

**Issues were often noticed from the diagrams before the text**, which then drove closer reading of the associated prose. Diagrams are load-bearing here, not decoration.

## Diagram tooling: prefer Mermaid

**Drop the PlantUML preference.** On reflection it was an old habit rather than a real advantage; Mermaid looks plainly superior. (Recorded in auto-memory so it applies across projects.)

## Open experiment: Sankey diagrams

Untried, worth experimenting with **at the end**. Candidate subjects:

- old versus new: code sizes, counts of things introduced, extracted, deleted or moved; old versus new complexity; movement between layers
- payoffs: which areas or files map to which payoffs, and by how much
- other ideas welcome
