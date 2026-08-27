---
title: 14 - Coordinator patterns for architectural conformance
type: note
permalink: toolguard/durable/14-architectural-conformance-patterns
tags:
- TOO-45
- durable
- architecture
- method
---

# 14 — Getting a subagent to conform to architectural guidance in the first place

> **STATUS: DRAFT, NOT REVIEWED, NOT ADOPTED. Arnon, 2026-08-25: *"I do not want to apply any of the conclusions immediately to any existing guidance documents because these new documents should go through rigorous reviews themselves."*** Nothing here has been folded into `CLAUDE.md`, the `feature-coder` guidance, or any skill. It is a candidate for those, later, after its own review.

**The question this answers**: what can a coordinator do so the work *does not fail the architectural review in the first place* — human or AI?

**Why it is a separate document from `13`.** TOO-45 improved **detection** and did not improve **conformance**. Arnon: *"when let loose it still does not follow architectural guidance as well as it should and needs the architectural separate review."* The campaign's own record agrees, and the sharpest instance is uncomfortable: the #10 spec instructed a coder to destroy an independent test oracle, and *"**the coder's silent non-compliance is the only thing that saved it. No review caught it.**"* **Finding defects and not creating them are different capabilities. This campaign worked on the first.**

**Confidence note up front**: `13` rests on one designed experiment. **This document rests on inference across the corpus and has no experiment behind it at all.** Treat every pattern below as a candidate with evidence, not as a validated practice.

---

## 1. Why conformance fails — three mechanisms, all measured

**These are not carelessness, and the distinction matters because it rules out the obvious fix.**

**1.1 A criterion with no completion signal does not register as outstanding work at all.** The TOO-19 plan mandates four TDD steps ending *"refactor while green."* **All three implementation reports restate it as three**, and **0** files corpus-wide carry a phase-shaped refactor line while the control fires (planning 20, implementation 32). The finding, verbatim: *"It is not that the unmeasurable step is deprioritised, deferred, or traded away — **it does not register as outstanding work at all.** … the step vanished from the agent's own restatement of the instruction that mandated it, in a report otherwise meticulous about protocol compliance."*

**The counter-example must travel with this finding, because without it the claim reads as "agents do not refactor" — which the primary explicitly refutes** (added 2026-08-27, on verifying this document's own claims). `11` records *"roughly ten tickets whose **subject** is a refactor"* — `Item 95 - split judge_unit`, `punch-list 94 validation_issues split`, `punch-list 04 error reporter`, `Project Root Consolidation`, `config_types.py extraction` — all done competently. **"So the capability and the willingness are both present. What is absent is refactoring as a *step inside a cycle*. It occurred only when it was itself the objective, with its own brief and its own definition of done."** That sharpens the diagnosis rather than weakening it: the missing ingredient is a **completion criterion**, not motivation — which is exactly why §3.1 is a report slot and not an exhortation.

**Instrument note, worth carrying.** `11`'s own measurement records that *"row (1)'s first run produced a false zero from a failed regex"*, and it carries controls (`tidy`/`restructur` **0/0**, `cleanup` **1**, against `planning` 20 / `implementation` 32). **A re-measurement attempted on 2026-08-27 with a different regex failed to reproduce the numbers** — which is an instrument difference, not a refutation, and precisely the trap the primary had already hit and fixed. **Do not treat a failed reproduction of this row as counter-evidence without using its stated pattern**: a bulleted or tabled item pairing the word with a duration.

**1.2 An underspecified criterion is applied correctly and yields the wrong answer.** The back-test's T1 miss: *"The brief said an exclusion is a finding 'unless justified by something other than effort', and a named successor item reads as exactly such a justification. **The judge applied an underspecified rule correctly.**"* Diagnosed explicitly as *"a specification defect, not eagerness."*

**1.3 A judgement exercised silently is indistinguishable from one never made.** The canary case again — the coder was *right*, and nothing in the process could tell that apart from an instruction quietly skipped.

**What all three share**: the failure is in what the instruction *made observable*, not in the agent's disposition or capability. That is why the intuitive fixes do not work.

## 2. What does NOT work — measured, so do not spend effort here

| approach | evidence |
|---|---|
| **Prompt-level exhortation** — *"think about the wider picture"*, *"don't just fix the symptom"* | the disposition it targets *"is NOT SUPPORTED as an independent cause"*, and **the corpus contains no instance where narrow fixing was chosen over a known-cheaper wide fix** |
| **Adding another prose requirement to general guidance** | four independently-encoded mandates measured being dropped; the disclosure rule missed on **10 of 17** qualifying commands in one day; `RED:` annotations stale at **9 of 9** |
| **Aggregate architecture scores as a gate** | noise band exceeds signal; **100/100 for a file it could not parse** |
| **Trying to make the agent "better at soft criteria" in the abstract** | *"It is not obviously worse at them — F2-DC1 is a soft judgement that beat every measurable signal pointing the other way."* |
| **Inviting generalisation in the brief** | when a brief *invited* it, the agent generalised and **broke a security floor** — *"misclassifying a genuine foreign-executor heredoc as a harmless generic sink and losing its ask_floor."* Caught by corpus replay, not inspection. **Widening is not free and is not automatically safer** |

**The last row is the one most likely to be got wrong**, because "tell it to think more broadly" feels like the obvious remedy and has a measured regression behind it.

## 3. The patterns that have evidence

Ordered by expected return. Every one is **structural** — it changes what is declared, what is produced, or what is looked at, never what the agent is urged to feel.

### 3.1 Give every step in a mandated sequence a completion artifact

**The highest-return item, because it is cheap, mechanical, and addresses a failure exhortation demonstrably cannot reach** — the instruction was already explicit and already mandatory.

Start with the cheapest form: **a required report section**. For the TDD case, *"Refactoring performed while green (say 'none, and why' if none)"* — one line in the template, and it *"converts an invisible omission into a visible claim somebody can dispute."*

**It carries its own falsifier, which is why it is the right first move**: add the section, and *"if agents fill it with 'none' while shipping code they would have restructured, the diagnosis is wrong"* and the cause is closer to disposition than this analysis concludes.

### 3.2 Declare the architecture in a machine-readable form

A layer map, an owner list, a declared vocabulary. **The principle**: *"a check is unambiguous exactly when it measures conformance to intent a human declared, rather than inferring whether the intent is any good."* A declaration converts a mushy question into a checkable one — and it is the thing a subagent can conform *to*.

**With the anti-gaming caveat from `13` §5**: a map is *"simultaneously the specification and the thing being satisfied"*, and **three of five one-line edits erased the remaining violation with nothing catching it.** Pin completeness with a test; direction needs the what-vs-how question asked explicitly.

### 3.3 Review the proposal, not the diff — and do it before implementation

The cheapest conformance intervention available, and `13` §6 is the evidence: the same defect was **found in the spec and missed in the commit**. A proposal-stage architectural round costs one round before any code exists. **Conformance failures caught here have not yet been built on.**

### 3.4 Cap the change set

Detection collapses as change size grows, *for both readers* — and a review of a large diff **still reports success**, which is the dangerous part. The design parameter is stated: the trigger is *"**files changed and lines changed in existing files**, not time and not step count."* Note this applies to the human too; it is not an agent-management item.

### 3.5 State per ticket whether widening is authorised

One clause, ~0 cost. It removes the guess that produces both failure directions — narrow-fixing when widening was wanted, and the ticket-19 regression when it was not.

### 3.6 Require judgements ACTED ON to be surfaced, not only deferred ones

Directly from the canary near-miss. A brief slot: *"decisions you took that the brief did not specify, and why."* **Without it, a correct silent deviation and a skipped instruction are the same artifact.**

### 3.7 Carry the previous round's non-blocking findings forward, with a disposition each

*"The cheapest fix identified anywhere in the corpus and it is in no project rule today."* Four documented escalations each burned a full extra round on something already written down; ticket 18's oscillation alone cost *"~$17–19 and ~1h45m of reviewer time plus three repair passes."*

### 3.8 Tell the subagent the brief is unverified — including its architectural premises

~30 caught false claims campaign-wide, with negative controls. **Two tickets' own architectural justifications were measurably wrong** once someone counted: one claimed sixteen hand-rolled error-output sites where there were **eight**; another claimed four sets tracking governed tools where there were **three live plus one dead, plus three undocumented copies the ticket never mentioned.** Both were *"written from a code reading rather than a count."* **An architectural instruction derived from a miscount produces conforming work on a false premise.**

### 3.9 Put a control inside every instrument the work will be judged by

*"A human who receives a tidy, plausible, confident number from an agent has no signal that it covered a twentieth of the population. **The control belongs in the instrument, not in the reviewer**, because the reviewer cannot see the gap."* This one matters *more* with a human in the loop, not less.

### 3.10 Count workarounds, not their justifications

A debt register with an owner and a budget, triggered by *"the third workaround for the same missing abstraction."* **Because each justification is individually sound, the count is the only visible signal.**

### 3.11 Decouple behaviour-pinning from unit tests early

**The only intervention here that changes the *answer* rather than the *instruction*.** *"The reason each local judgement came out 'disproportionate' is that the tests pinned the shape. An equivalence oracle … changes which cleanups are affordable, and therefore **which local judgements come out right**."* If a subagent keeps declining to restructure, the tests may be making the right call the expensive one.

## 4. The ceiling — how much this can buy

**Roughly a quarter of the narrow-fixing cases are ones where the agent's local judgement was *correct*.** Briefs will not reach that quarter, and pushing there produces *"either compliance against its own correct reasoning, or the ticket-19 regression."*

**So the realistic target is not zero architectural findings.** It is: remove the failures caused by things being unobservable (§1.1), underspecified (§1.2), or invisible (§1.3), and leave the residue for the review in `13`. **The separate architectural review does not become unnecessary** — Arnon's own framing is that it is still needed.

## 5. What this document needs before it is used

1. **An experiment.** `13` has a back-test; this has none. The §3.1 falsifier is the cheapest one available and should be run first.
2. **A control for §3.3.** Proposal-review is inferred from a 4-point ground truth in a different experiment.
3. **Separation of effects.** These eleven patterns were never run as a set, and several overlap.
4. **A check against normal (non-repair) work.** The whole corpus is repair; conformance in feature development is unmeasured — see `08`'s framing section.

**Until then this is a hypothesis list with citations, not a practice.**
