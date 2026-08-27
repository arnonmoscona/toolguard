---
title: 08-autonomous-loops-vs-human-in-the-loop
type: note
permalink: toolguard/durable/08-autonomous-loops-vs-human-in-the-loop
---

# What this campaign does and does not tell you about autonomous agent loops

**Written 2026-08-24, after Arnon corrected the frame of the whole analysis.** Everything in `02`, `06` and `07` was written as if it were about planning and verification. It is not. It is about **agent planning and agent verification under autonomous orchestration** — a mode Arnon chose here because the scope made his normal pattern impractical, and which is not his normal pattern.

His frame, which is the right one:

> "this huge effort was structured intentionally as dominated by autonomous agent loop delivery. This is *not* my normal pattern with you... The *normal* pattern that I use in working with claude code is *human in the loop*. Especially with collaborative human+agent planning and manual code reviews following agent code reviews... what we're looking at here, really, is how well the human experience maps to autonomous agent loops using the models available during the period of this activity."

And his observation, which the data supports:

> "the error rate, the problems and retraction rate etc. were *far higher* than in human in the loop and were closer to poorly managed, junior human teams."

**The question this document exists to serve is his: when to use an autonomous loop at all.** It cannot answer that. What it can do is put numbers where assumptions were, and reject the ones that are wrong.

## The second half of the frame — what the loop was DOING (Arnon, 2026-08-25)

The correction above says the *mode* was autonomous. This one says the *work* was repair, and both limits apply to every number in `02`, `05`, `06`, `07`, `09` and `12`:

> *"The whole corpus of evidence we have is dominated by bug discovery and fixes rather than new feature development. It incidentally added minor features, but **TOO-45 was framed at the outset as an architecture refactor.** It so happened that many issues were uncovered. Some real, some not. Some material, some not."*

**Two limits compose here, and they are independent.** The mode was autonomous *and* the work was repair. A finding transfers to Arnon's normal working pattern only if it survives both — and most of this corpus has never been tested against feature development at all, in either mode.

**It cuts differently for the two halves of the analysis, which is why it is worth stating rather than filing as a general disclaimer:**

- **Planning findings get weaker.** `06` measures **repair-brief** planning against a bar of *"the information was already in the repo and nobody read it."* Feature planning has no such repository of settled answers to fail to read — the answers do not exist yet. `06` now carries this as its own scope section, and its percentages must not be carried across.
- **Verification findings get stronger.** The defect crop was a **by-product of a refactor**, not the objective. Verification aimed at restructuring returned 76 tickets, three security regressions caught before commit on a single ticket, and — as a **lower bound of partly-verified provenance, not a count** — roughly fifty production defect tickets from mutation testing alone (`intermediate/practices-with-evidence.md`: fifty is *"a floor, not a ceiling"*, 1 of 3 supporting batches independently verified). **A yield that large from work aimed at something else is close to a free experiment**, and it is why the general question *"does verification pay for itself"* is answered yes even though `07` cannot price any individual escape chain.

**The asymmetry is the point.** Autonomy's tax lands hardest on judgement — planning, scoping, deciding — and verification is the part that held up under it. That is consistent with §5's finding that every silent security defect was caught by a reviewer who *executed* something, and with `11`'s finding that the mode removed the adjudicator. **Where a human decides, the loop was weak; where a machine can check, the loop was strong.** Both readings survive the repair-work caveat; neither has been tested on feature work.

---

## 1. The tax, measured

**40.0% of recorded implementer effort was rework** — 45.0h of 112.4h, across 122 tasks classified from `data/phase-costs.tsv` (48 rework, 74 first-pass). Rework means repair passes, review-finding fixes, follow-ups and re-dos. Both sides were sampled and inspected rather than trusted: the largest rework items are `review-18 round 3 repair`, `code review majors M1-M3 fix`, `review-79 round 1 repair`; the largest first-pass items are `ticket 77 phase 2 matcher`, `punch-list #01 suppression store`, `resolution seam protocols`.

**This is a floor, and the gap is large.** It counts only *implementer* effort, because every reviewer-side report in the corpus states a total and never a split. It excludes the 27+ blinded review rounds entirely. And it excludes **all coordinator time** — which, per §3, is where a large share of the error actually originated. The true tax is meaningfully above 40%.

Rework is concentrated: **the top three tickets hold 44% of it** (TOO-19, ticket 18, ticket 78).

**Confidence: moderate-to-high on the magnitude, high on the direction.** The inputs are self-reported estimates (507 of 574 rows are the source's own approximation), and tasks whose reports did not survive are invisible. But no plausible correction brings a 40% floor down to a human-team norm.

## 2. The comparison that actually bears on the decision

Arnon chose autonomy because human-in-the-loop *"would have taken far too long."* Both sides of that trade are now measurable, in the same units:

**CORRECTED 2026-08-24, and the original version of this section made exactly the error this corpus already documents.** It tabulated **~45h of agent rework** against **~58.1h of Arnon's blocked wall-clock** and concluded they were "the same order of magnitude". That is the **wrong-currency** mistake — the same one behind the retracted *"most expensive item of the campaign"* claim, where "expensive" silently meant agent-runs rather than Arnon's time. **Agent hours are cheap, parallel and reproducible. Arnon's hours are scarce and serialize the whole project.** They do not belong in one table, and comparing them produced a false equivalence.

Arnon, 2026-08-24: *"my availability is actually the constraining resource always as this is not my main activity. So if we did 100+ individual tickets using human in the loop, TOO-45 would have taken 6 months to a year."*

**So the trade is not cost-versus-cost. It is a hard constraint against a quality tax:**

| | autonomous loop (what happened) | human-in-the-loop (the counterfactual) |
|---|---|---|
| calendar | **20 days**, 13 with commits | **6–12 months** (Arnon's estimate) |
| agent effort | ~112h recorded implementer time, **40% of it rework** | lower rework, unquantified |
| the binding resource | agent throughput — elastic | **Arnon's availability — fixed, and not his main activity** |

**Read that way, autonomy bought roughly a 10–20x calendar compression, and the 40% rework tax is what it cost.** The rework is paid in the elastic currency; the calendar is paid in the scarce one. That is why the mode was chosen, and the data does not argue against the choice — it prices it.

**What this does and does not settle.** It settles that "was autonomy cheaper in hours?" is the wrong question, because hours of two different kinds were never the constraint. It does not settle whether a 40% rework tax plus a higher escape rate is acceptable for any *given* piece of work — that depends on what the defect would cost if it shipped, which for a permission hook is not the same as for a report generator. **Confidence: high that the framing above is the correct one; the 6–12 month figure is Arnon's estimate, not a measurement, and is stated as his.**

## 3. Reject: "the agents were the weak link"

**The corpus attributes a large share of rework to the coordinator, not the implementers** — and in an autonomous loop the coordinator is an agent, whereas in Arnon's normal pattern it is Arnon.

- Ticket 18 ran six review rounds; the corpus records that **rounds 3-6** *"caught errors of the **coordinator's**, not the implementers'"* (`surprise/18-scored.md:61`). That is the highest-round ticket in the campaign.
- Ticket 19's extra repair round *"measures coordinator error here, not ticket difficulty"* (`surprise/RESULTS-LOG.md:200-206`).
- Four documented escalations (tickets 18, 77, 78, 80) each burned a full extra round **re-deciding something a previous round had already written down as non-blocking** (`06-planning-attribution.md`).
- Briefs specifying commands that blocked on permission prompts caused two ~90-minute stalls that looked like agent failures and were coordination failures.

**So the marginal failure of the autonomous mode was not implementer competence. It was orchestration** — the function a human occupies in the pattern Arnon normally uses. That is the single most decision-relevant asymmetry in this data: **the mode removed the human from precisely the role where the errors concentrated.**

**Confidence: high on the direction, moderate on the share.** The attributions are the campaign's own, made contemporaneously, and no instrument counted coordinator time.

## 4. Test: how far does "poorly managed junior team" go?

It holds on more dimensions than one would like, and **breaks on one that changes management strategy.**

**Where it holds** — each of these is a documented junior-team pathology and each is measured here:

| pathology | evidence |
|---|---|
| fixing the instance, not the class | 4 of 6 confirmed escaped-defect chains, *with the technique already in hand* (`07`) |
| re-litigating settled decisions | 4 between-round escalations (`06`) |
| not reading available information | 20 confirmed planning-preventable findings; a layer map contradicted by comments for 3 weeks |
| good local work, poor integration | item 10 fixed 2 of 3 files and left the third **in the component that governs**, bricking every non-builtin governed tool for 11 days |
| high rework | 40% (§1) |

**Where it breaks, and this is the important part: juniors fail loudly; these agents failed silently and confidently.** The characteristic failure here is the **clean null** — an instrument returning a tidy, plausible, wrong number instead of an error:

- A path regex that matched 27 of 313 files and reported a total.
- A database query returning **zero** dangling links by matching 4 of 746 rows on a prefix that does not exist in that schema.
- A HEAD-vs-tree comparison that agreed exactly because both runs imported the working tree.
- A corpus replay reporting zero flips because the permissive fallback made the transition unobservable.
- An adversarial verifier **confirming a false claim** — *"absent from both directories"* — because it inherited the original's search scope. The independent check bought nothing.

**A junior says "I'm not sure." These systems produce a symmetric, confident, wrong result and move on.** That difference is not cosmetic; it dictates a different control.

**The consequence for how to manage the mode:** with a junior team you review the *work*. Here you must also validate the *instrument*, because the reporting layer is as unreliable as the work layer — and **review does not catch a clean null; only a control does.** Every measurement worth acting on needs something that should fail and doesn't, or a total that must reconcile. The campaign's own review rounds bear this out from the other direction: they **did** catch all three silent security defects — and every one of the three was caught by a reviewer who *executed* a differential, none by a reviewer who read the diff (see §5).

**Confidence: high.** The clean-null instances are numerous, independently produced, and several were caught only by accident.

## 5. Reject: "human-in-the-loop would have caught these" — *for silent behavioural bugs in repair work, which is a much weaker claim than it looks*

This is the assumption most worth testing, because it is the one that would justify simply reverting to the collaborative pattern. **The evidence says it would have removed the cheap errors and left the dangerous ones.**

- **The 20 confirmed planning-preventable findings are overwhelmingly claim-class** — a docstring saying "five modes" fourteen lines above "Six modes"; comments asserting a layering the project's own `.pyscn.toml` contradicts; change-history paragraphs added in the same commit as a sweep deleting nine of them. **A human reading the diff catches these.** They are also cheap.
- **All three serious security defects were execution-only and silent.** Ticket 79's leaf-`kind` reclassification silently downgraded an unoverridable `hard_deny` to `ask`; the suite was green and the corpus replay showed nothing. **No amount of diff reading finds that** — human or agent.

  **CORRECTED 2026-08-24 — an earlier version of this section said blinded review *missed* all three. It did not, and I introduced that error.** All three are B1 blocking findings inside review rounds: `review-79-round1.md`, `review-78-round2.md`, `review-18-round2.md`. I read each in its file. **What is true, and is the sharper point, is *how* the reviewers found them — every one says "Measured":** a `PYTHONPATH`-shadowed pre-fix tree, a comparison against `bash -c 'printf %s ~name'`, a measured widening. **They executed a differential; they did not read one.** So blinded review is a *container*, not a technique — its yield depends entirely on whether the reviewer runs something. The genuine miss is different and stands: `Path.absolute()` escaped six rounds, because *"an enumerate-the-bad-list rule cannot catch the route nobody thought of."*
- `Path.absolute()` escaped **six** blinded review rounds, and the technique that found it did not exist in the corpus beforehand.

**So the two modes fail in different places, and the collaborative pattern's strength is not where the autonomous pattern's worst failures are.** The dangerous class needs mechanical differential testing regardless of who is in the loop. Adding a human raises the floor; it does not remove the need for the instrument.

**Confidence: high, and raised by the correction above rather than lowered.** The claim no longer depends on review having missed anything. It rests on the three security defects being genuinely execution-only — which `06` argues case by case — and on the primary evidence that the rounds which caught them did so by *running* a differential. **The operative distinction is reading versus executing, not human versus agent.** That is precisely the risk in a pattern built on *"manual code reviews following agent code reviews"*: a manual review is a reading review, so it inherits exactly the blind spot that the executing reviews closed.

### This rejection is a WEAK FORM, and reading it as a general result would be a serious error — Arnon, 2026-08-25

> *"The #5 reject is a weak form as it applies here to behavioural **bugs**, and in normal work we do more **features**, which are almost always behavioural and have a very strong track record of human-in-the-loop catching things — especially in the planning phase but also in the review phase. In this particular corpus it is also evidenced by the effectiveness of human-in-the-loop for the headline purpose of the campaign: architecture improvements. So the conclusion really applies to the case of bugs, and especially behavioural bugs. Those happen quite a bit in feature development even with a human in the loop, but are very significantly reduced by it."*

**What §5 actually establishes, stated at its true width:** *a human reading a diff does not catch a silent behavioural regression in code whose intended behaviour was already settled.* That is all. It is a claim about **repair** work — the only kind this corpus contains — and about **reading** as the review technique.

**The logical gap is in §5b, and it is load-bearing.** That section asserts *"planning prevents claim defects and not behaviour defects… a claim can be checked against something that already exists, a composition defect cannot exist until the parts run. Nothing about it depends on whether the planner is human."* **That reasoning holds only while the intended behaviour is already fixed.** In repair work it is: the desired behaviour is given, and planning can only restate it. **In feature work planning is what *decides* the behaviour** — so the largest behavioural defect available, *we built the wrong thing*, is precisely the one planning exists to prevent, and it is unreachable by any differential, mutation harness or replay, because every instrument here checks the code against **its own** intent. **A differential cannot tell you the intent was wrong.** So §5b's "nothing about it depends on whether the planner is human" is true for repair and false for features, and the corpus contains no feature planning to test it against.

**The corpus's own evidence for human effectiveness, which §5 walked past.** `09` §6 states it directly: *"What it reliably catches: **INSTRUMENT defects, and architecture.**"* Those are the two classes with no automated coverage at all. **14 of 76 primary tickets (18%)** are attributed to *"Arnon asking a question, reviewing, or instructing"* — and `10-human-vs-ai-reading.md` verified that list ticket by ticket, finding **13 confirmed and 1 already self-flagged as mis-assigned**. On the architecture question specifically, ticket 98: *"**Arnon predicted that before the spikes were built.** Worth recording as a calibration point: the architectural instinct was ahead of the measurement here."* **Architecture improvement was the campaign's headline purpose, and the human was measurably good at it** — which is the strongest in-corpus signal about the class of work that most resembles feature planning.

**Two things that keep this honest and must travel with the paragraph above.** First, `09` §6 explicitly warns that the wider claim — *"every architectural error was caught by a human asking a direct question, none by any metric, blinded agent or test"* — is **sourced only to auto-memory, never to a primary**, and that an architecture-judge back-test **contradicts** it by finding eight live defects in already-reviewed, shipped code. Do not restate it. Second, the mechanism `09` identifies is **attention, not humanity**: *"Correction rate tracked reviewability, not code quality… Now that changes are fewer files I start noticing things."* A reviewer's detection rate collapses as change-set size grows, whoever the reviewer is.

**So the corrected form of §5, and it is the version to quote:** adding a human raises the floor a great deal on *claim*, *instrument*, *architecture* and *intent* defects, and **does not remove the need for a mechanical differential against the silent behavioural class**. Those two statements are compatible, and the original section read as though only the second were true. **In feature development the balance shifts further toward the human**, because more of the risk sits in deciding what to build — a judgement, moderate confidence, that this corpus can motivate but cannot test.

## 5b. What transfers to human-in-the-loop — because most of it does

Arnon, 2026-08-24: *"some of this will be transferrable to human-in-the loop too."* Correct, and §5 above was framed too much as a contest between two modes. **The useful division is not autonomous-versus-collaborative; it is findings that are properties of the *defect*, which transfer to any mode, versus findings that are properties of *who was orchestrating*, which do not.**

**Transfers fully — these are properties of the work, not the mode:**

- **Planning prevents claim defects and not behaviour defects — IN REPAIR WORK ONLY** (scoped 2026-08-25; the unscoped version of this bullet was wrong). This follows from what the two classes *are*: a claim can be checked against something that already exists, a composition defect cannot exist until the parts run. **But it holds only while the intended behaviour is already settled, which is true of every ticket in this corpus and false of feature work** — there, planning is what decides the behaviour, and *we built the wrong thing* is a behavioural defect that only planning prevents and no differential can detect. See the correction at the end of §5.
- **Silent behaviour defects need a mechanical differential.** All three security defects had green suites and quiet replays. A human reading the diff does not find a `hard_deny` silently becoming `ask`. This is the strongest transferable finding here.
- **Instance-fixing where the class is already known.** 4 of 6 escaped-defect chains, and a textbook human pathology.
- **Re-deciding what a previous round settled.** 4 documented escalations; human review threads do this constantly.
- **Reviewing a small formal artifact alone, before its consumers** (the two-phase grammar rule) produced the campaign's only clean reviews. The mechanism is mechanical checkability, not agency.
- **The clean null — and this one matters MORE with a human in the loop, not less.** A human who receives a tidy, plausible, confident number from an agent has no signal that it covered a twentieth of the population. Every clean-null instance listed in §4 was produced by an agent and would have been *reported to* a human as a finished result. **The control belongs in the instrument, not in the reviewer**, because the reviewer cannot see the gap. That is a working practice for collaborative mode, not a compensation for autonomy.

**Does not transfer — properties of the orchestration:**

- The **40% rework rate**. It is a measurement of this mode under these models on this codebase.
- The **coordinator-error share** (§3). It exists because the coordinator was an agent. With Arnon in that seat the whole category changes shape — probably shrinking, but the corpus cannot say by how much.
- The **58.1h availability latency**, which measures one person's schedule, not a general property.

**The judgement worth stating** (moderate confidence): the transferable list is longer and more actionable than the mode-specific one. Most of what this campaign learned the hard way is about **defect classes and instrument design**, and those hold whoever is driving. The mode-specific findings mainly bear on the *one* decision autonomy actually forces — whether anyone is present to notice silence.

## 5c. The cost nothing in this corpus prices: the human's whole-system picture — Arnon, 2026-08-25

> *"Another unstated issue that is a natural blind spot to you, but not to me, is that the human involvement enhanced the human's whole system picture and understanding. Since humans have far better retention and attention to long-term memories, this involvement is very important. Whatever happens without a human leaves the human blind to it, which has a hard-to-measure long-term cost."*

**Why it was missing, stated plainly, because the reason matters more than the omission.** I have no retention across sessions. I cannot notice the value of understanding accumulating in someone, because nothing accumulates in me — **I cannot miss what I never had.** So I will systematically under-weight this, in this document and everywhere else, and the omission will look like completeness rather than like a gap. It is the same failure shape this campaign keeps finding: *a mechanism that fails open and says nothing.*

**The cost tables in `02` are one-sided, and this is the missing side.** Arnon's involvement is priced throughout as **pure latency** — 68.9h of prompt-wait across 557 asks, 58.1h of blocked wall-clock in §2 — and it appears on the cost side of every comparison. **What that time also bought never appears anywhere**: a maintainer who knows why the module is shaped this way, which decisions were close, what was tried and rejected, and where the bodies are. Autonomy does not remove that cost. **It defers it, converts it into a worse currency, and hides it from the ledger.**

**This exercise is the invoice, and it is the best measurement of the effect available.** The DURABLE corpus exists in large part because a campaign ran without him in it and the picture had to be **reconstructed afterwards** — ~750 corpus files, five extraction agents, five adversarial verifiers, twelve documents, and a substantial share of phase 3. Human-in-the-loop produces that understanding **as a by-product, for free, in the currency of attention already being spent.** Reconstruction pays for it separately, later, and in his scarcest resource — reading.

**And reconstruction recovers strictly less than participation would have.** This is not a hypothetical: the README's own *"What these documents cannot tell you"* is a list of things that are **permanently gone** — no authoring timeline (mtimes bulk-reset, 69 files sharing one minute), agent-run counts that are floors because subagent identification is broken, not one cost figure with a meter behind it, four source files retracting their own clock times. **A participant would have known most of that without needing it recorded.** So the deferred bill is not merely late; **part of it can never be paid**, and the residue is silent — nobody can enumerate what they failed to learn.

**What follows for the decision.** Autonomy's real price is the **quality tax** in §1, plus the **reconstruction cost**, plus an **unrecoverable remainder** of understanding that no document restores. That third term is invisible to every instrument in this campaign and grows with the share of work done unattended. It argues for keeping the human in the loop **at the points where the system's shape is decided** — architecture, interfaces, and what a thing is for — even when an agent could produce an acceptable artifact alone, because those are the decisions a maintainer must carry for years. **Consistent with §5's corrected form**: the human's value concentrates in judgement and intent, and that is exactly the part whose understanding has to persist.

**Confidence: high that the effect is real and unpriced; low on magnitude.** It is Arnon's direct observation about himself, corroborated structurally by the existence and size of this reconstruction effort. **No number here, and one should not be invented** — but "unmeasured" must not be recorded as "small", which is precisely how it has been treated so far by being omitted.

## 6. What follows for the decision — offered as input, not as an answer

**Where the evidence points toward autonomy being acceptable**: work whose correctness is *mechanically checkable* — a small, formally-specified artifact with a differential harness. The strongest datum in the whole corpus is ticket 77 phase 1: grammar reviewed alone, before any Python, producing **the only clean blinded reviews in the campaign**, on evidence of 0 parse-status flips over 28,770 distinct commands. **But I would not generalise it far** (low-to-moderate confidence): a `.peg` file is small, formally checkable, and regenerable-and-diffable. Most changes have none of those properties, and the result may be a property of the artifact rather than of the sequencing.

**Where the evidence points against autonomy**: work where the failure mode is silent. The campaign's signature defect, recorded independently many times, is *a mechanism that fails open and says nothing*. An autonomous loop has no one to notice silence.

**The cheapest available improvement is not more planning or more verification — it is follow-through.** Four of six escaped-defect chains were instance-fixed when the class was already known, and four extra rounds were spent re-deciding settled questions. Both are tracking failures, and both are the kind of thing a human coordinator does almost for free.

### And that means a PROCESS answer, not another instrument — Arnon, 2026-08-25

**He is right, and the sentence above was left as an observation when it is really a redirection.** Every other improvement in this corpus is an instrument — a differential, a mutation run, a replay, a fitness check. **Follow-through is not instrument-shaped at all.** No tool can detect *"you found the class and fixed two of its three instances"*, because nothing in the code says how many instances the class has; and no tool can detect *"this round re-litigated what the last round settled"*, because the settlement lives in a report, not in the tree. **These are failures of tracking and hand-off between activities, which is the definition of process.**

**But the corpus's hardest-won lesson is that a process answer written as prose will not fire here**, and this is not a caution — it is measured, in `12` §A-y: four independently-encoded mandates dropped, the disclosure rule missed on **10 of 17** qualifying commands in one day, the `RED:` annotations stale at **9 of 9 (100%)**, and the two-phase grammar rule whose own preamble records being ignored *"even when the instruction to use the grammar was explicit."* Arnon's global CLAUDE.md already states the general form — *"a 'MUST' in prose has a demonstrated track record of being silently dropped in this setup, including after being fixed once"* — and this campaign is the measurement behind it.

**So the answer is a third thing, and `12` §C4 already names it: *"prefer a mechanism the orchestrator executes, or an artifact slot the reporting template demands, over anything the agent must remember."*** That is the productive middle between an instrument and an exhortation, and it is the same move `.claude/rules/evidence-before-fixing.md` makes about checks generally: **a check is strong exactly when it verifies conformance to something a human declared.** Applied here, follow-through becomes checkable without anyone automating the judgement:

- **Instance-versus-class** (`07`'s one-line habit — *run the technique once more against the sibling*) turns into a required slot: *siblings considered / checked / deliberately not checked*. A reader — or a script — can see an empty slot. Nobody has to decide whether the answer is right for the omission to become visible.
- **Carried findings** (`12` §A5, which `09` calls *"the cheapest fix identified anywhere in the corpus and it is in no project rule today"*) turns into a repair-brief field listing the previous round's non-blocking findings with a disposition each. Ticket 18's rounds 4–6 cost *"roughly $17–19 and about 1h45m of reviewer time"* plus three repair passes, and **every one was pre-stated in writing by the round before.**
- **Knowingly-deferred residuals** become tracked items rather than a paragraph in a report. C1's residual was recorded honestly, in prose, in a file nobody re-read — and was re-derived from scratch five days later.

**The irreducible residue is an owner, and this is where follow-through rejoins §5c.** `11` records that the autonomous mode *"removed the adjudicator"*: a soft criterion cannot be *closed* by a loop, only escalated and parked — which is what `DECISIONS-PENDING.md` is. `12` prices every follow-through item at ~0 except A12, whose queue *"needs an owner — recurring."* **A declaration slot makes an omission visible; it does not make anyone act on it.** So the cheapest available improvement is also the one that most needs a human in the loop, and it is cheap in exactly the currency this campaign was short of — attention, not tokens.

**Where autonomy's price is deferred rather than avoided** (added 2026-08-25, from §5c): the maintainer's understanding of the system. It is charged later, in reading, and part of it is never recoverable. **Keep the human at the points where the system's shape is decided** — architecture, interfaces, what a thing is for — even where an agent could produce an acceptable artifact alone, because those are the decisions someone has to carry for years.

**What this campaign cannot tell you**: anything about **feature development**, which is what most normal work is — this corpus is repair work end to end (see the framing section at the top and §5's correction), and the strongest human-in-the-loop effects are claimed exactly there; anything about long-term maintenance cost; whether these ratios hold for a different codebase or a different model generation (they are dated to the models available July-August 2026); or how a genuinely collaborative planning phase would have changed the 40%. Nothing here should be read as measuring your experience against agent performance — the two were gathered under different conditions and the corpus contains **no user-originated ticket at all**, so field validity is entirely untested.