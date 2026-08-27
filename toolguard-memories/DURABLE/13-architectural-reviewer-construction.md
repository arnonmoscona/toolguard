---
title: 13 - Constructing an architectural reviewer that actually works
type: note
permalink: toolguard/durable/13-architectural-reviewer-construction
tags:
- TOO-45
- durable
- architecture
- method
---

# 13 — How to construct and guide an architectural reviewer that actually works

> **STATUS: DRAFT, NOT REVIEWED, NOT ADOPTED. Arnon, 2026-08-25: *"I do not want to apply any of the conclusions immediately to any existing guidance documents because these new documents should go through rigorous reviews themselves."*** Nothing here has been folded into `CLAUDE.md`, the `feature-coder` guidance, or any skill. This is a candidate artifact awaiting its own review.

**What this is.** TOO-45 produced one architectural review setup that worked. This is that setup written down as a recipe, with **what it cost to get there and what still does not work** — because the recipe without the failure history reads as *"AI reviews architecture well"*, which is false.

**The one-sentence version.** *An ordinary agent assessing architecture failed for weeks. A purpose-built apparatus — two judges with deliberately asymmetric information, a single-task brief, a pre-registered axis list, and a back-test to validate the judge itself — found eight live defects in already-reviewed committed code. Every qualifier in that sentence was bought with a failed experiment.*

**Do not read the judge brief alone as the method.** `TOO-45/reports/architecture-judge-brief.md` is one of four components and is the easiest to mistake for the whole thing.

---

## 1. The mechanism is attention, not capability

The back-test's hypothesis, which is the load-bearing claim of the whole approach:

> *"A judge whose only task is architecture will weight the architecture training data more heavily than a coder or a general reviewer does, because **the dominant causes of the weakness are attention dilution and task focus rather than capability.**"*

Its verdict: *"**It did not find them by being cleverer — it found them by having nothing else to do.**"*

**Every design choice below follows from that.** You are not making the reviewer smarter. You are removing everything competing for its attention, and converting an unanswerable question (*is this good architecture?*) into answerable ones (*what moved, on this named axis, at this site?*).

**Corollary for expectations**: a capability that needs a dedicated harness to appear is a weakness being worked around. Do not expect it from a general reviewer, and budget for the harness.

## 2. The apparatus has four components

| # | component | what it supplies | primary artifact |
|---|---|---|---|
| **A** | **A declared architecture to stand on** | ground truth the judge can measure conformance *against*, instead of inventing a standard | `.pyscn.toml` layer map; the as-is and ideal pictures; `tools/architecture_fitness.py` |
| **B** | **Two judges with asymmetric information** | one blinded to intent, one holding the whole plan — and a closing rule that needs both | execution plan §8 |
| **C** | **A single-task judge brief** | exclusive scope, pre-registered axes, delta-not-conformance, measurement, output format | `reports/architecture-judge-brief.md` |
| **D** | **A back-test of the judge itself** | evidence the reviewer detects anything, with a pre-registered scoring key | `reports/architecture-judge-backtest.md` |

**Component D is the one most likely to be skipped and the one that makes the rest trustworthy.** Without it you have a reviewer that produces confident reports and no evidence it detects anything.

## 3. Component B — two judges, and why one cannot do it

This is the piece the brief does not contain, and it is where the design's core insight lives:

> *"The ticket requires the judge **not** be told what the step was meant to achieve — **give a reviewer the goal as a pass condition and you get a reviewer that confirms it was met.** Arnon also wants a judge holding the big picture and nudging the orchestrator. Both are right; **one agent cannot do both.**"*

| | **Blinded reviewer** | **Architect judge** |
|---|---|---|
| sees | before/after **and nothing else** — no goal, no predicate, no metrics, no plan | everything: ideal picture, as-is picture, plan, interface drafts, wargames, decision log, predicates, diff |
| asks | *is this easier to review, and why?* | is the **direction and reasoning** right? |
| value | *"comes entirely from its ignorance"* | can say *"this landed, but for the wrong reason, and the next step will suffer"* |

**The closing rule is the mechanism, not the roles.** *"A step closes when both agree."* And each disagreement is diagnostic rather than ambiguous:

- **Blinded satisfied + architect unconvinced** = locally tidy, strategically wrong. Keep going.
- **Architect satisfied + blinded unconvinced** = right in principle, not yet real. Keep going.

**Two further design notes, both deliberate:**

- **Separate context windows are a feature** (Arnon): *"each judge has a focused task, so the context-rot exposure of a long-running loop is lower than with one omniscient judge."*
- **An iteration guard, stated explicitly**: both judges receive *iterations since this step opened* as an input to their recommendation. This catches the failure a no-progress limit misses — *"a step that is progressing steadily and still running too long."*

## 4. Component C — the judge brief, ingredient by ingredient

Arnon named four — *"a focused task (just architecture — nothing else), clearer criteria, judge blinding, and some other ingredients."* The full set, with evidence:

**4.1 One job, stated exclusively, with an explicit discard instruction.** *"You are not reviewing for bugs, style, test coverage, performance, or correctness. Another reviewer does that. **If you find a bug, ignore it.**"* The final clause does real work — without it, attention leaks straight back to the local layer, which is where it goes by default. Naming the other reviewer makes discarding safe rather than negligent.

**4.2 A pre-registered axis list — the biggest single lever.** Twelve axes fixed before any subject is seen: information hiding, single responsibility, coupling surface, indirection depth, dependency direction and layering, cycles, data boundary integrity, failure-mode architecture, type boundaries, declared vs hidden state, locality of change, single source of truth. **This is the declaration principle applied to a judgement** — *a check is unambiguous exactly when it measures conformance to intent a human declared.* **Tune the list to the system**: these fit a stdlib-only permission hook, and the back-test warns this codebase *"cannot exercise most architectural axes"*.

**4.3 Score a DELTA at a site, never conformance to a principle.** *"Architectural principles cannot be satisfied perfectly and simultaneously… **You are not scoring conformance to a principle. You are scoring a delta at a specific site, and you are expected to name the cost alongside the benefit.** … A change that improves one axis and claims no cost is a change you have not looked at hard enough."* **Measured**: *"Two-sidedness held. Every judge reported degraded axes alongside improved ones, including on the axis each change was proudest of."*

**4.4 Make "nothing here" the expected answer.** *"Flat is the expected default… **Do not manufacture a finding to fill a row.**"* **Measured**: the smallest subject returned *"flat on 8 of 12 axes"*, and *"the flat rate tracked change size, which is what it should do."*

**4.5 Blinding, in two directions.** *"Do not read anything under `reports/` except this brief… Do not read other judges' output."* **Measured payoff**: *"Convergence across independent judges. A5 and B3 arrived at the same behaviour change from opposite directions without either seeing the other."* Two blind judges agreeing is evidence; two briefed judges agreeing is an echo. **Blind the reviewer to prior conclusions, not to the system** — `CLAUDE.md`, `docs/` and the source tree are expected reading.

**4.6 Require measurement, and give it the tools.** *"Where a claim is countable, count it… do not estimate them."* **Measured payoff, and it is large**: *"B1 independently re-derived the stderr census and confirmed the ticket's '16' was stale and the spec's corrected '8' was right."* The judge corrected the artifact it was judging. This matches the campaign's strongest cross-cutting finding — **reviewers who executed something found what readers missed.**

**4.7 Deduplicate to one primary axis.** *"One real defect that shows on four axes is **one** finding with a named primary axis, not four."* Without this, a twelve-axis structure inflates one defect into a crisis and buries the ranking.

**4.8 A prescribed output format** — per-axis table, findings in severity order, verdict *"of the kind a reviewer would say out loud"*, with three worked examples of the register. This is *prescribed method beats general guidance* applied to the output, and it is why reports are comparable across judges.

**4.9 The scope-completeness rule — and the fix a failure produced.** *"A change that introduces a mechanism and then declines to apply it at a site that plainly needs it is an architectural finding… unless the exclusion is justified by something other than effort."* **This rule as first written caused the back-test's clearest miss (T1)**: the spec deferred to a named successor item, and *"a named successor item reads as exactly such a justification. **The judge applied an underspecified rule correctly.**"* The fix now in the brief: *"'That gets its own item' answers **when**, not **whether they are the same item**."* **Keep this as the worked example of how to repair a judge — the failure was a criterion, not the reasoning.**

## 5. The what-vs-how test — the acceptance question a green check cannot answer

Recorded separately because it is *"the thing most likely to be lost to a passing layer check"*. Arnon's framing:

> *"For each function or class ask: is this about the **what to do** or about the **how to do**? Is this something that has a chance to be stable under ongoing maintenance, or is it too thin, such that it would change every time the underlying code changes?"*
>
> *"Designing layers is not about aesthetics. It is about maintainability and preventing concept leaks. A layer's external interface is much like a system's public API…"*

**Operational consequence, verbatim**: *"'Does it pass the layer check' is necessary and nowhere near sufficient. **A facade of thin pass-throughs passes the check and fails this test.** … The distinction between a designed surface and an accumulated one lives in judgement, so it must be **asked explicitly** at every review, not inferred from a green check."*

**This is the anti-gaming clause for component A.** A declared layer map can be satisfied by structure that means nothing; only this question catches it.

## 6. Run it on PROPOSALS — the most actionable operational finding

From the back-test's pre-registered ground truth:

| id | subject | result |
|---|---|---|
| T3 | the **#10 spec** — closed registry cannot describe a user-declared MCP tool | **hit** |
| T4 | the **#10 commit** — *the same defect, still in the code* | **miss** |

> *"T4 is literally T3 in a different substrate and was missed there… **the judge sees architectural defects in proposals and not in diffs.**"*

**Why, and it is not a property of the reader**: a proposal states intent, so a boundary error is a sentence you can disagree with. A diff states edits, so the same error is distributed across changed lines and reads as normal. **Both readers in this campaign did better on proposals.** It is also the cheap finding to act on — a proposal-stage review costs one round before any code exists, and catches the defect before anything is built on it.

## 7. Component D — back-test the judge before trusting it

**Design as run**: eight blind judges, one brief, **one subject each**; **arm A** = five committed diffs (false-positive control), **arm B** = three pre-implementation specs; **scoring key pre-registered before any report was read.**

**What each part buys**: one-subject-per-judge prevents cross-contamination and gives independent convergence its meaning; the diff arm is the false-positive control; pre-registration is what stops the scoring key drifting to fit the reports.

**What to look for beyond hit rate** — all four were more informative here than the 2-of-4:

- **Two-sidedness** — does every judge name costs, or do some produce improvement narratives?
- **Flat rate tracking change size** — a small change should return mostly flat.
- **Independent convergence** — two blind judges reaching one conclusion from opposite directions.
- **Judges beating their subjects** — *"B2 named the concrete mechanism where the original human catch was a one-line prompt to look."*

## 8. What failed — the part that makes the above meaningful

**Weeks of ordinary architectural assessment.** Arnon: *"We spent weeks with the agent failing badly in any architectural assessment."* That is the baseline, and it is why *"an agent can review architecture"* is the wrong summary.

**Adjacent approaches tried and rejected, all with measurements:**

| approach | why it failed |
|---|---|
| **Aggregate architecture health scores** (pyscn grade, and the general form) | noise band exceeds any signal; **reports 100/100 for a file it could not parse.** Arnon: *"pretty useless, even as a directional measure"* |
| **Co-change coupling as a headline metric** | 100%-coupled pairs rose **71 → 134 (+89%)** while the architecture demonstrably improved. The anti-gaming design (group by ticket, not commit) is what produced the false signal |
| **Import-graph-only layer checking** | `config` and `resolve` — **zero import edges between them — called each other 46,481 times** through an injected callback. `--layers` reports clean |
| **A declared layer map, trusted alone** | the map is *"simultaneously the specification and the thing being satisfied."* **Five one-line edits were tried against the one remaining violation; three erased it with nothing catching the edit.** Only completeness is pinned by a test; direction has no anchor — which is what §5 exists to cover |
| **Prompt-level exhortation** (*"think about the wider picture"*) | the disposition it targets *"is NOT SUPPORTED as an independent cause"* |

**The pattern across all five**: each substitutes a *number* or an *exhortation* for a *judgement at a site*. The apparatus works because it does neither.

## 9. Known limitations — quote these whenever the method is cited

1. **One-sided blinding.** *"The judges were blind; the axis list was not — three of twelve axes map onto known defects… **A clean replication needs axes chosen by someone who has not seen the corrections.**"*
2. **n = 4 positives.** *"Establishes existence, not a rate."*
3. **This codebase cannot exercise most architectural axes.**
4. **The control arm was never run.** *"Comparing against the general `/code-review` reports for the same five commits is the direct test of 'focused beats general' and remains to be done."* **So even "focused beats general" is untested against its control** — it rests on the contrast with weeks of failure, which is weaker.
5. **Detection improved; conformance did not.** See `14`.
6. **The two-judge design was specified in the execution plan; the back-test validated the single judge.** How much the blinded/architect pairing contributes is **not separately measured.**

## 10. If this becomes a skill

The brief is close to a skill body, but a skill needs the apparatus, not just the brief:

- **Axis-list selection** for the target system.
- **Subject selection** — proposal preferred; if a diff, say so and expect a lower hit rate.
- **The two-judge pairing and the both-must-agree closing rule**, with the iteration count passed in.
- **Blinding and output paths** as mechanical setup rather than prose instruction.
- **The what-vs-how question** as a required output section, so a green layer check cannot stand in for it.
- **A control arm by default**, so limitation 4 stops being open.
- **A stated expectation of mostly-flat results**, so a quiet report is not read as a failed run.

**Do not ship it as guidance text.** This campaign measured four independently-encoded prose mandates being silently dropped. A skill is a mechanism the harness invokes, which is the form that survives.
