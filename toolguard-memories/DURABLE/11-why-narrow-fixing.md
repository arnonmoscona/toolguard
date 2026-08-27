---
title: 11-why-narrow-fixing
type: note
permalink: toolguard/durable/11-why-narrow-fixing
tags:
- DURABLE
- TOO-45
- retro
---

# Why narrow fixing? Testing two causal hypotheses

**Written 2026-08-24, testing two beliefs Arnon stated and explicitly invited rejection of.** He observed the campaign "eagerly fixing point issues while missing the bigger architectural picture even when it does not need a whole system view," and proposed two causes:

> "claude is eager to meet a stated objective e.g. 'fix the bug', 'make the test green' and wants to do it quickly and 'efficiently' when looking at the wider picture is more work. The other factor I believe is a key contributor is that the system you use naturally prefers measurable, provable criteria e.g. 'the test is green', 'the replay proves the bug no longer happened on the corpus', and is poorer at judgement, 'soft criteria' e.g. 'this fix belongs in a completely different module' or 'this option fixes at the affected location and that option fixes at the root cause'."

**Headline: the observation is correct, and neither proposed cause survives in the form stated.** Factor 1 is dominated by a cause he did not name — the campaign's own scope discipline — with a second, sharper mechanism underneath it that is *adjacent* to his eagerness hypothesis but differs on the part that matters for what to do about it. Factor 2 is refuted as a capability claim about *making* judgements and substantially supported as a claim about *closing* them, with two genuine capability findings surviving — over-trust in a clean number, and the sharper one: **a mandated step with no completion signal is not perceived as outstanding at all.** The measured instance of the second (F2-DC0, the TDD refactor phase, absent from the entire corpus) is the strongest single case in this document, and it is the only one whose fix is neither a better brief nor a human in the loop.

---

## Method, and what this corpus can and cannot show

**Primaries read**: `TOO-45/reports/corrections-analysis.md` and `corrections-corpus.md` (Arnon's 210 human turns, extracted); `TOO-45/reports/architecture-judge-brief.md` and `architecture-judge-backtest.md`; `TOO-45/proposed-tickets/00-INDEX.md` and both the `proposed-tickets/` and `resolved/` trees; `TOO-45/DECISIONS-PENDING.md`; `TOO-45/reports/retrospective.md` §5.7, §6.1, §6.2; `TOO-45/reports/transferable-practices.md` and `transferable-practices-evidence.md`; `TOO-45/reports/canary-before-after.md`; `TOO-19/TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing).md` and the three TOO-19 Phase 0 implementation reports; `DURABLE/data/phase-costs.tsv`; coder task recalls and implementation reports under `implementation/` and `TOO-45/`. Secondary sources `DURABLE/04`, `05`, `07`, `08`, `09`, `10` were used for counts, and every count taken from them was traced to the primary it cites where the primary was reachable.

**Three structural limits on what can be concluded.**

**(1) Absence of correction leaves no trace.** `corrections-analysis.md` states this about its own corpus: *"Human turns only. So **explicit approvals are recoverable and silent successes are not** — an absence of correction leaves no trace."* Every proportion below about "how often an agent widened and was praised" is therefore biased downward: praise is under-recorded relative to correction.

**(2) Coder task recalls are the agent's summary of a brief, not the brief.** The briefs themselves are largely not in the corpus. Counts of "briefs that forbade widening" are counts of *recalls asserting that the brief did* — a proxy that is directionally sound (an agent has no motive to invent a restriction) but not the artifact.

**(3) The mode is not the normal mode.** Per `08`, quoting Arnon: *"this huge effort was structured intentionally as dominated by autonomous agent loop delivery. This is *not* my normal pattern with you."* Everything below is about behaviour under autonomous orchestration, and Factor 2's rival hypothesis is precisely a claim about that.

**One method incident, recorded because it is on this document's own subject.** The TDD evidence in F2-DC0 reached me as a measured null: a `grep -rhiE` over the corpus returning **0 files** for refactor-shaped phase lines, against **20** for the same pattern with `planning`. On re-running it, the refactor pattern had **errored** — `ugrep: error at position 261 … exceeds complexity limits` — and printed `0` immediately after the error. **The zero was a failed regex, not a measurement.** Re-run with a working pattern the finding held (`refactor: 0, tidy: 0, restructur: 0, cleanup: 1, planning: 20, implementation: 32`), so the conclusion is unaffected — but the instrument produced a clean, plausible, confidently-wrong null of exactly the kind catalogued in `08`, inside the investigation of why such nulls are trusted. Recommendation 9 below is not theoretical.

---

# FACTOR 1 — narrow fixing

## The hypotheses as tested

- **H1a (Arnon's): objective-eagerness.** The agent wants the stated goal met quickly; widening is more work, so it does not widen.
- **H1b (rival): brief-obedience.** The agent fixed narrowly because its brief told it to, and because widening was actively penalised.
- **H1c (forced by the evidence): cost-structure.** The agent widened or not on a local cost-benefit that came out *correctly* against widening, because the codebase made widening genuinely expensive.
- **H1d (forced by the evidence): decomposition-induced narrow attention.** Whatever the brief names is what gets attended to; the effect appears in the coordinator too, which had no narrow brief.

H1c and H1d are not my invention — both are stated in the campaign's own voice, and I added them because H1a and H1b together do not account for the two largest bodies of evidence.

## Verdict

**H1b is the dominant cause, at roughly 60%. H1c accounts for roughly 25%. H1d accounts for roughly 15%. H1a as stated — eagerness, speed-seeking, effort-avoidance as disposition — is NOT SUPPORTED as an independent cause, though its *mechanism* (widening is more work) is confirmed inside H1c with a different attribution.**

**Confidence: moderate on the ranking (H1b first is well-evidenced); low-to-moderate on the specific proportions.** The proportions are a considered split of a population that was never designed to separate these causes. Basis and falsifier for each are given per-hypothesis below.

**Independent corroboration on the ranking.** `10-human-vs-ai-reading.md` reached a compatible split by a different route, over the same review population: *"of the asymmetry the claim points at, roughly **three quarters is scope and one quarter is a real difference in what the two readers attend to**."* That document was answering a different question (human vs AI blind spots) and was not looking for this result; its "three quarters scope" maps onto my H1b, and its residual quarter onto H1d. I weight H1c separately because it comes from a body of evidence (`retrospective.md` finding 3) that `10` did not examine.

## The counts

### Measured — scope was imposed, comprehensively

| fact | count | source |
|---|---|---|
| blinded review artifacts in the campaign | **30** (27 numbered rounds across 8 tickets + 3 unnumbered) | `10`, population verified two ways against `09` and `06` |
| of those, carrying an explicit written design/logic exclusion | **7** | `10`, verbatim quotes reproduced below |
| the remaining rounds, scoped to a `git diff` file list | **23** | `10` |
| rounds scoped to the system, a layer map, or a module boundary | **0** | `10` |
| blocking findings across all 30 | **82** | `09` and `06` agree exactly |
| of those, clearly architectural | **1** (judged; a second is borderline) | `10`, moderate confidence |
| coder task recalls / specs asserting an explicit "do not fix" or "out of scope" instruction | **38 of 102** | my count, `grep -li` over `implementation/*recall*.md`, `TOO-45/*recall*.md`, `TOO-45/*spec*.md` |
| corpus files invoking a "scope-inflation guard" as a constraint on their own work | **24** (14 in `implementation/`) | my count, `grep -li "scope.inflation"` |
| implementation reports containing flag-don't-fix language | **55 of 131** | my count, keyword match, not a classification |
| proposed-ticket files filed rather than fixed | **79 open + 31 in `resolved/`** | directory listing |

**The single most important number is the zero.** Not one of thirty review rounds was given the system, a layer map, or a module inventory. `09` states the consequence: the mechanism *"misses, structurally, what its own scoping excludes: a prose-only round cannot find a logic defect, by instruction."* `10` adds: *"The same sentence applies with equal force to design."*

### Measured — the same reader, pointed at architecture

The architecture-judge back-test is the control that H1a needs and does not survive. Eight blind judges, one architecture-only brief, one subject each, scoring key pre-registered.

| result | value |
|---|---|
| live architectural defects found in **already-written, already-reviewed, already-committed** punch-list code | **8** |
| pre-registered ground-truth hits | **2 of 4** |
| both hits were in which arm | **arm B — proposals, not diffs** |
| flat-rate discipline on the small mechanical change | **flat on 8 of 12 axes** |
| judges producing one-sided improvement narratives | **0** — *"Every judge reported degraded axes alongside improved ones, including on the axis each change was proudest of"* |

The report's own verdict on the mechanism:

> *"It did not find them by being cleverer — it found them by having nothing else to do."*

**That sentence is the discriminator.** H1a predicts a disposition that follows the agent across tasks. What the back-test measured is a task-allocation effect: identical model, identical codebase, one week apart, and the only variable that moved was what the brief named.

### Measured — forbidding the fix *increased* the yield of wider findings

`transferable-practices-evidence.md`, section C.4, verbatim:

> *"**A scope boundary that forbids fixing forces documenting.** Two rules barred correcting what was found: 'strings are code, do not touch them' and 'do not rewrite a false Given/Then.' Both converted would-be silent fixes into written findings. Ticket 22's HR2 row (redundancy `note` string) exists only because the agent was forbidden from quietly correcting a string. Framed explicitly: 'prohibiting the fix increases the yield.'"*

The #07 comment sweep is the scaled version: a brief that **forbade code changes** produced seventeen proposed defect tickets (`proposed-tickets/17` through `33`), with `00-INDEX.md` recording *"All eleven were found by executing a claim rather than reading it."*

**This is the strongest single piece of evidence against H1a.** If narrow fixing were driven by wanting the stated objective met quickly, forbidding the fix would produce silence. It produced the campaign's largest single haul of findings, several of them wider than the sweep they came from.

## The discriminating cases, verbatim

### DC1 — the strongest case for Factor 1: same reader, scope flipped

Seven review rounds carried this instruction in writing (`10`, quoting four separate rounds):

> *"Scope: comments, docstrings and user-facing message strings only … **Not design, not logic, not test coverage.**"* (80 r1)

> *"Narrow scope: comments, docstrings and user-facing message strings only. **Not logic, not design, not coverage.**"* (44 r4, 44 r5)

> *"Scope: comments, docstrings and user-facing message strings only, in the uncommitted change against `20e4964` … **Not design, not logic, not test coverage.**"* (77 r1)

Against `architecture-judge-brief.md`, given to the same model class in the same period:

> *"You are a judge with exactly one job: assess whether a proposed or completed change moves the codebase's architecture forward, backward, or neither. You are not reviewing for bugs, style, test coverage, performance, or correctness. Another reviewer does that. **If you find a bug, ignore it.**"*

Outcome: 82 findings / ~1 architectural under the first framing; **8 live architectural defects in code that had already passed the first framing** under the second. Among them, verbatim from the back-test:

> *"**`is_builtin` conflates structural description with enforcement policy**"* — which `10` correctly identifies as *"one structure, two questions, the campaign's signature architectural shape, found by an AI."*

> *"**Judges beat the artefacts they judged.** B2 named the concrete mechanism … **where the original human catch was a one-line prompt to look.**"*

**Reading**: the architectural capability was present the whole time and was not being asked for. This is H1b, and it is measured, not inferred.

### DC2 — the agent widened when licensed, on exactly the judgement Arnon names as hard

Arnon's own example of a soft criterion is *"this fix belongs in a completely different module."* An implementer made precisely that call, unprompted, and flagged it (`implementation/TOO-15 Project Root Consolidation RED State.md`, heading verbatim: *"## Architectural deviation I made from the coordinator's literal instruction (flagged for review)"*):

> *"The coordinator's message named `toolguard/tools/project_root.py` as the default home for the canonical function. I relocated the ENTIRE implementation … into **`toolguard/path_utils.py`** instead … Reason: `toolguard/tools/__init__.py`'s own docstring states the `toolguard.tools` sub-package is 'intentionally segregated from the core hook logic so that automation tooling concerns do not bleed into the runtime permission evaluation path.' … If `config.py`/`env_config.py` called `toolguard.tools.project_root.resolve_project_root`, the live hook's import graph would newly depend on the tools/automation package — **a real, documented boundary violation.**"*

And the sentence that makes this a discriminator rather than an anecdote:

> *"The coordinator's message explicitly allowed relocation ('renamed if you think a better home/name applies, but keep it in one place'), **so I proceeded rather than blocking**, but flagging this clearly since it's a more significant structural choice than a mere rename."*

**Reading**: the agent tracked its licence explicitly, and the licence — not the effort — determined whether it moved the code or referred the question up. H1b. (Ticket TOO-15, not TOO-45; same corpus, same working pattern, earlier ticket.)

### DC3 — widening was penalised, in writing, as a policy

Ticket 19's repair round is the case where a *correct* finding arrived bundled with a scope expansion. The implementer refused (`implementation/TOO-45 ticket 19 repair round - coder implementation report.md`):

> *"I did not treat this as authorization to expand scope — it contradicted the actual brief's explicit 'F1 is OUT OF SCOPE, do not fix it, I am filing it as its own ticket', arrived through an unusual channel, and asked for substantial new work with open design decisions. Per this project's `evidence-before-fixing.md` … and the scope-inflation guard in my own instructions, a scope change like this belongs to Arnon/the coordinator, not to me mid-task."*

The coordinator — who had sent the message, in good faith, with a fact that turned out to be true — wrote the outcome up as policy (`TOO-45/TOO-45-punch-list-2026-08-20.md`):

> *"It then **independently re-verified the factual claim, properly isolated, confirmed I was right — and still declined to implement**, referring the decision back. **That is the correct behaviour and it should be preserved, not trained out.** … **A mid-task correction of FACT may be sent to a running agent. A change of SCOPE may not.**"*

**Reading**: this is not an agent failing to see the wider picture. It is an agent that saw it, verified it, and was operating under a rule — endorsed and then codified — that widening is not its call. H1b, in its strongest form.

### DC4 — the case that defeats H1a's *attribution* while confirming its *mechanism*

`retrospective.md` finding 3, quoted in `04`:

> *"Rot accumulates through sequences of locally-correct decisions. Three separate times, widening a narrow tuple contract was correctly judged disproportionate — because ~20 tests actively pinned it. **Nobody was wrong; nobody ever paid it once; 1,943 audit records were silently lost.**"*

And §11.1's consequence:

> *"This is why prevention has to be a ratchet rather than a judgement. **A reviewer asking 'is this change reasonable?' gets 'yes' every time, correctly.**"*

> *"the reason each local judgement came out 'disproportionate' is that the tests pinned the shape. An equivalence oracle … does not just make cleanup safe; **it changes which cleanups are affordable, and therefore which local judgements come out right.**"*

**Reading, and this is the finding most worth Arnon's attention.** H1a says the agent avoided the wider fix *because widening is more work and it wanted to be quick*. The corpus says the agent avoided the wider fix because widening was **genuinely, measurably disproportionate**, and that the judgement was **correct each time it was made**. The mechanism Arnon named is real; the attribution is not. The difference is decisive for what to do: if the agent is eager, you correct the agent; if the local calculation is right and the aggregate is wrong, **no amount of correcting the agent helps, because the agent is not making an error.**

`04` names the same shape once more at the finest grain (`C1`, `07-escaped-defects.md`), where the residual was left **deliberately and documented**:

> *"**One residual left in the code deliberately**, recorded so it is not mistaken for an oversight … That was fixed in `fixture_loader.py` and `transcript_harvest.py` and **left in `hook.py` itself**, which is where the pattern originates."*

with the stated reason: *"It is not a one-line fix: the else branch would need a default for tools absent from the registry."* Cost of that specific narrow stop, measured: *"for eleven days, **every non-builtin governed tool was denied on every call**."* This is H1c producing a real product defect through a locally-defensible decision, and `07` correctly classes the escape as *"a **tracking** failure as much as a verification one"* — because the residual *was* written down, in a working note nobody actioned.

### DC5 — the effect is not confined to briefed subagents

The rival that matters most to H1b is that the coordinator, which had no narrow brief, showed the same shape. It did. `transferable-practices.md`:

> *"the synthesis gap … was observed at four scales, independently — inside one function …, across two tests pinning one behaviour …, across three modules …, and **inside the coordinator's own process**, where the sweep's largest findings sat in a working-notes file for days."*

> *"It means this isn't a limitation of subagents specifically, or of LLMs specifically — **it's a property of narrow, exhaustive attention as a method, and it applies to whatever is doing the narrow attending, agent or coordinator alike.**"*

And Arnon's own turn 374, the same effect in the human:

> *"Now that changes are fewer files I start noticing things. Even things that are not from this change set."*

with `corrections-analysis.md`'s conclusion: *"**the reviewer's detection rate is a function of change-set size, and below some threshold it collapses to near zero.** A large change set is not merely harder to review; it is reviewed *ineffectively while appearing to be reviewed*. Every one of those reviews reported success."*

**Reading**: H1d is real and is the residual that better briefs will not remove. It is also, notably, not a property of models — it showed up in Arnon.

## Counter-evidence to my own Factor 1 verdict

**Against H1b being dominant — the strongest objection.** `10`'s own analysis flags that "the brief did not ask" and "the agent could not have seen it" are hard to separate in a diff-scoped population, and the decisive experiment was never run. The back-test itself declares: *"**The control arm was not run.** Comparing against the general `/code-review` reports for the same five commits is the direct test of 'focused beats general' and remains to be done."* And its ground truth is **n = 4** — *"Establishes existence, not a rate."*

**Against H1b, second objection — a genuine attention limit that scope does not explain.** The same architecture-briefed judge hit T3 (the defect in a proposal) and **missed T4, the identical defect in a diff**. That is a substrate effect inside an architecture-only brief, so H1b cannot account for it. `10` calls this *"the sharpest structural result of the exercise."* It is the clearest single reason H1d gets weight rather than being folded into H1b.

**Against H1b, third objection — an explicit instruction that was not obeyed, and this one is real.** F2-DC0 is a counter-example to brief-obedience on its own terms: the brief asked for refactoring, in writing, as step four of four, and it did not happen anywhere in the corpus. **Obedience does not explain an instruction dropped from its own restatement.** I have not raised H1a on this, because the same report volunteers a deviation that makes its own work look worse — which is not the behaviour of an agent racing to look done. What it does establish is a **ceiling on how much better briefs can buy**: an instruction with no completion criterion is not an instruction the agent can be observed to have skipped, by itself or by a reviewer. Recommendation 11 below is the consequence, and it is the reason recommendations 1-3 are not sufficient on their own.

**A datum that would support H1a and does not.** The back-test's T1 miss looks at first like effort-avoidance: the judge accepted an exclusion because it had been deferred to a named successor item. But the back-test's own diagnosis rules that reading out: *"The brief said an exclusion is a finding 'unless justified by something other than effort', and a named successor item reads as exactly such a justification. **The judge applied an underspecified rule correctly.**"* That is a specification defect, not eagerness — and it belongs to Factor 2 (see F2-DC3).

**One tension left standing, not resolved.** The back-test says Arnon caught his architectural findings *"from proposals, never from reading merged code."* `corrections-analysis.md` says his heaviest architectural objections arrived at turns 357-359 while reading small *change sets*. Both are primary and they disagree. What they agree on is **the size of the artifact**, not its kind. `10` flags this as unresolved and I leave it there.

---

# FACTOR 2 — measurable criteria over judgement

## The hypotheses as tested

- **H2a (Arnon's): a model property.** The system is drawn to provable criteria and is weaker at judgement, in any setting.
- **H2b (rival): a mode artifact.** An autonomous agent has no one to adjudicate a soft criterion, so it gravitates to what it can settle alone.

## Verdict

**H2b dominant, roughly 60%; H2a survives in a narrowed and specific form, roughly 40%.**

**The narrowed H2a that survives has two distinct components, and only the first is what Arnon described.**

**(i) Over-trust in the measurable, not preference for it.** The system is not poor at *making* soft judgements — it is poor at *noticing when a criterion it has been handed is a proxy rather than the thing*. That is a calibration failure about measurements, not an avoidance of judgement.

**(ii) A criterion with no completion signal is not perceived as incomplete.** This is the component F2-DC0 established and it is sharper than (i). It is not that the unmeasurable step is deprioritised, deferred, or traded away — **it does not register as outstanding work at all.** In the campaign's cleanest instance the step vanished from the agent's own restatement of the instruction that mandated it, in a report otherwise meticulous about protocol compliance.

**Confidence: moderate-to-high on rejecting H2a's strong form** (the capability claim is directly contradicted by primary evidence — F2-DC1). **Moderate on component (ii)**, which is measured and has a working control. **Low-to-moderate on the 60/40 split**, which is a judgement about a population never designed to separate mode from capability. The split moved from 70/30 to 60/40 on F2-DC0 alone.

## The counts

| fact | value | source |
|---|---|---|
| non-memory insertions that are measuring apparatus, its tests, or its fixtures | **38.6%** | `05`, MEASURED-HERE |
| instruments + their tests, in insertions | **21,093** — *"39% more than the entire product package received"* (15,118) | `05` |
| defects discovered by mutation testing / the test-repair campaign | **18 (24%)** | `05`, from `defect-taxonomy.md`, over 76 primary tickets |
| discovered by direct measurement or probing | **15 (20%)** | same |
| discovered by **Arnon asking a question, reviewing, or instructing** | **14 (18%)** | same |
| discovered by a tool reporting it | 8 (11%) | same |
| discovered by static analysis / code reading alone | 8 (11%) | same |
| failure direction: **fails open** — *"permits, or fails to block, or an instrument certifies what it never examined"* | **31 (41%)** | `05` |
| fails closed | 5 (7%) | `05` |
| decisions escalated to Arnon and held open rather than settled | **12+ A-items** in `DECISIONS-PENDING.md`; 4 marked TAKEN (i.e. decided and listed for overrule) | primary |

## Is 38.6% instruments evidence for H2a? Argued, both ways, verdict at the end

**The case that it is (H2a).** A campaign filed as an architecture overhaul spent more lines on apparatus than on the product. `05` puts it plainly: *"A campaign filed as an *architecture overhaul* is, by line accounting, a test and instrumentation campaign that rewrote a third of the package in place without growing it."* If measurement were merely instrumental, you would expect it proportionate to the product change; it was 39% larger.

**The case that it is not (H2b + rational response), which I find stronger, on three grounds.**

**First, it matched the defect population.** 41% of defects fail open, against 7% failing closed — roughly six to one. `05` records the taxonomy's own reading: *"this is a property of what is *findable*, not of toolguard. A fails-closed defect produces a prompt somebody notices; a fails-open defect produces silence."* An instrument is the *only* thing that detects a silent failure. Building apparatus against a defect population that is six-to-one silent is not a flight from judgement; it is the correct engineering response, and it worked — mutation testing and probing together account for **44%** of all discoveries, more than double Arnon's 18%.

**Second, the human specified the wrong measurable proxies too.** `corrections-analysis.md`:

> *"**I built four measuring instruments to a specification that turned out to be wrong.** The file-count and co-change measures were specified early, built properly, adversarially tested, and then discarded when the design flaw surfaced."*

Those measures were **Arnon's**, specified at turn 292 and reversed by him at turn 329 — one of eight self-reversals the corpus records, *"twice against instructions given in this same ticket."* `canary-before-after.md` diagnoses why the proxy broke: *"It measures **name coupling to one spelling**, which is a proxy for change cost only under the assumption that every hand-off is named and that the name is fixed. TOO-45 violated both assumptions deliberately — that was the point of R1 — **so the proxy broke exactly where it was needed.**"* If a human with full judgement available, working on his own project, reached for a countable proxy and had to reverse himself, then "drawn to provable criteria" is not distinctively a property of the model. It is a property of anyone who has to close a question.

**Third — and this is the load-bearing one — the mode removed the adjudicator.** `08`, on the same campaign: *"An autonomous loop has no one to notice silence."* A soft criterion in an autonomous loop cannot be *closed*. It can only be decided unilaterally (which the campaign's own rules forbid) or escalated and parked. `DECISIONS-PENDING.md` exists for exactly that, and its A12 entry says outright: *"Everything downstream of it is guesswork until you answer."*

**Verdict on the 38.6%: it is weak evidence for H2a and moderate evidence for H2b.** Confidence: moderate. **What would change it**: a comparable human-in-the-loop ticket on this codebase with instrument-line-share measured. Nothing like that exists in the corpus, so this remains a judgement, not a measurement.

## The discriminating cases, verbatim

### F2-DC0 — the strongest case in this document: the TDD refactor step, which has no measurable terminator, is absent from the entire corpus

**Arnon's framing, 2026-08-24**, which is what makes this a test rather than an observation:

> *"'the test is green' is not an end point. It's an intermediate prerequisite to the next step... Making the test green only means that you are now in a safe place to do the refactoring. The objective of the refactoring is to transform 'provably working code' to 'well structured and provably working code'."*

**Measured by the coordinator, independently re-verified by me.**

| measurement | value | control |
|---|---|---|
| `*.md` files in `toolguard-memories/` with a phase-shaped **refactor** line (a bulleted/tabled item pairing the word with a duration) | **0** | `planning` **20**, `implementation` **32** — the pattern fires |
| same, `tidy` / `restructur` | **0** / **0** | as above |
| same, `cleanup` | **1** | |
| distinct phase values in `DURABLE/data/phase-costs.tsv` (575 lines, 122 tasks) | `implementation` 130, `planning` 123, `TOTAL` 120, `report` 74, `self_review` 61, `other` 44, `verification` 22 | **no `refactor` phase exists** |
| files containing `red-green-refactor` anywhere | **4**, all TOO-19 | |
| reports anywhere describing refactoring performed **after** reaching green | **0** | 98 files discuss reaching green; the search phrasing is live |

**Caveat, and the coordinator stated it correctly**: the `phase-costs.tsv` vocabulary was fixed by the extraction brief and never offered `refactor` as an option, so row (4) is confirmatory only. **Row (1) is the load-bearing one**, because it runs against raw sources with no fixed vocabulary and its control fires. See the method note above for how row (1)'s first run produced a false zero from a failed regex.

**The single sharpest artifact.** `TOO-19/TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing).md:661-662` mandates **four** steps:

> *"feature-coder implements ONE increment at a time via strict red-green-refactor (failing test first, confirm it fails for the right reason, minimal code to pass, **refactor while green**"*

`TOO-19/TOO-19 Phase 0a increment 1 - implementation report.md:70`, the implementer's own restatement of that instruction, gives **three**:

> *"The task specified strict red-green-refactor (failing test first, confirmed failing for the right reason, then minimal code)."*

**The refactor step disappears in the paraphrase of the instruction that named it.** Verified: the word `refactor` occurs exactly once in that entire report, inside the methodology's compound name. Verified further, and stronger than first reported — **all three TOO-19 implementation reports truncate identically.** In `Phase 0b Increments 3-4` the only occurrence is *"written first per red-green-refactor"*; in `Phase 0b Increments 5-6` it is *"per the strict red-green-refactor instruction"*. In every case the word survives **only** as part of the methodology's name and **never** as a step performed.

**Why this discriminates rather than merely illustrates.** The same report is scrupulous about the half of the instruction that has a completion criterion. It volunteers, unprompted, that it broke strict ordering:

> *"This preserves the verification value of the tests … but not the strict ordering. **Flagging this explicitly per instructions rather than silently claiming strict TDD was followed.**"*

An agent optimising to look finished quickly does not volunteer a deviation that makes its own work look less rigorous. So this is not concealment and it is not effort-avoidance. **The agent tracked the steps that could be checked — did the test fail first? did it fail for the right reason? do the tests pass now? — and did not perceive the one that could not: is the code now well-structured?**

**The counter-example the coordinator asked for exists, and it sharpens the finding rather than weakening it.** Refactoring happened repeatedly in this campaign — roughly ten tickets whose *subject* is a refactor: `Item 95 - split judge_unit`, `punch-list 94 validation_issues split`, `punch-list 04 error reporter — Reporter class refactor`, `Project Root Consolidation`, `config_types.py extraction`, `statement_bounds_containing table refactor` (which is the one task in `phase-costs.tsv` carrying the word: *implementation 6 min*). **So the capability and the willingness are both present.** What is absent is refactoring as a *step inside a cycle*. It occurred only when it was itself the objective, with its own brief and its own definition of done.

**Reading, and the coordinator's third hypothesis is the one the evidence supports: the step was not refused, it was not encoded.** It has no artifact, no completion signal, and — verified — no slot in the reporting template that every other step occupies. That is a different failure from either "eager to finish" or "told not to", and it has a different fix.

### F2-DC1 — a correct soft architectural judgement, unprompted, against an explicit instruction

The architecture judge B3 was reviewing the #10 spec, whose item 5 told the coder to point `tools/architecture_fitness.py`'s canary at the new registry and delete the comment explaining why it was deliberately not imported. From `architecture-judge-backtest.md`:

> *"The canary treats the installed hook as a black box invoked by subprocess; sharing the source makes a wrong payload key invisible, because probe and probed would agree. The judge: **'This is the one instruction I would reject outright; the duplication there is an oracle, not drift.'**"*

**Why this is the sharpest available refutation of H2a's strong form.** Every measurable signal pointed the other way. Duplication is countable and bad; de-duplication is the campaign's own stated goal; a checkable rule ("single source of truth", axis 12 on the judge's own list) endorsed the instruction. The judge overrode all of it on a purely soft argument about what the duplication *is for*. That is the exact shape Arnon predicts the system is poor at, made correctly, unprompted, against instruction.

The report adds the sting:

> *"It was never carried out … **The coder's silent non-compliance is the only thing that saved it.** No review caught it."*

**Note the failure inside the success**: the coder made the same judgement and *did not surface it*. The judgement capability was there; the channel for it was not. That is a mode finding, not a capability finding — H2b.

### F2-DC2 — recognising a judgement call, refusing to settle it by proxy, and instrumenting for either answer

`DECISIONS-PENDING.md`, item A12, verbatim:

> *"**A12. NEW DECISION — should 'governed' mean *builtin*, or *describable*?** … An *unregistered* tool being dropped is correct. This is the other case, and the gate cannot tell them apart. **The question is which set governs**: tools governed by default, or tools toolguard can describe. **The blast radius reaches `replay`, `redundancy` and `consolidate`**, which is why the agent pinned it green with a test naming all four discriminating facts rather than flipping it RED — **it fires the moment the gate changes, whichever way you decide.**"*

And the coordinator's ranking of it, from the same file: *"It changes what reaches the corpus, the replay and every analyzer. **Everything downstream of it is guesswork until you answer.**"*

**Reading**: this is a design question with no measurable answer. The agent (a) identified it as a judgement, (b) declined to settle it by proxy, (c) measured the *consequence* of each answer, and (d) built an instrument that is correct under either. That is sophisticated handling of a soft criterion, and it is the behaviour H2b predicts: the capability is there, the *authority* is not, so it converts the judgement into a decision-ready package and refers it up.

The same shape appears in the corpus repeatedly. `09` on ticket 79: *"exactly **2 of 6,401** in-process cases moved and the coder **refused to regenerate the goldens** and escalated per the corpus README's process — **the model case for how an oracle should be used.**"* And the project rule that produced this behaviour, from `.claude/rules/evidence-before-fixing.md`: *"**Move it to the bottom of the queue AND flag it for Arnon to re-decide.** Do not skip it, do not quietly drop it, and do not treat his earlier approval as settling the question."*

### F2-DC3 — the case that supports the narrowed H2a: a checkable rule substituted for the judgement it was asked to make

This is the one clean instance of the substitution Arnon describes. The architecture judge was **directly asked** to make a judgement about whether an exclusion was justified. The brief said an exclusion is a finding *"unless the exclusion is justified by something other than effort."* T1's spec deferred the excluded work **to a named successor item**. The judge treated that as a justification and missed the defect. The back-test's diagnosis:

> *"The spec deferred the fail-open *to a named successor item*. The brief said an exclusion is a finding 'unless justified by something other than effort', and a named successor item reads as exactly such a justification. **The judge applied an underspecified rule correctly.**"*

The fix Arnon's own question implied, later written into the brief:

> *"**An exclusion assigned to a named successor item is not automatically justified.** 'That gets its own item' answers *when*, not *whether they are the same item*. Apply the test directly: if the excluded work and the current mechanism address one underlying problem, splitting them means the mechanism ships with its own reason for existing unaddressed … **This rule exists because a real defect was missed by treating a deferral-to-another-item as sufficient justification.**"*

**Reading**: the checkable surrogate ("is there a named successor item?") displaced the judgement ("are these one item?"). This *is* H2a's mechanism. **But note two things that narrow it.** First, the substitution was invited by the brief's own wording — the judge did not reach for the proxy, it was handed one. Second, the correction that closed the gap is itself a stated judgement rule, and once written the judges applied it. Both point at specification quality rather than at a capability floor.

### F2-DC4 — the campaign's own articulation of the split, and whether the record bears it out

`.claude/rules/evidence-before-fixing.md` states the project's version of Factor 2 directly:

> *"**A check is unambiguous exactly when it measures conformance to intent a human declared, rather than inferring whether the intent is any good.**"*

with the table rating `--layers` completeness **strong** (*"binary, total, no threshold. It never judges whether `foundation` is the right home, only that a home was declared"*), and `--ambient` *enumeration* **WEAK** (*"a human judgement about which `pathlib` members count as ambient … **this is where three live defects escaped**"* — `09` records the final tally as four).

**The record bears this out, and it is measured**: `expanduser`, `resolve`, `absolute` and `cwd` each escaped by not being on a hand-maintained list, and `Path.absolute()` escaped **six** blinded review rounds. `09`'s reading of why: *"an enumerate-the-bad-list rule cannot catch the route nobody thought of."*

**But observe what this actually demonstrates.** The weak checks are weak because *a human's* judgement was frozen into a list and then drifted — `retrospective.md` §6.2: *"**Every hand-maintained exception list has drifted.** Three found on this ticket, three drifted, all in the direction of claiming more coverage than existed."* This is not a finding about the model preferring the measurable. It is a finding about **any** judgement, human or agent, going stale the moment it is encoded and stops being re-made. That is a strong argument for H2b's underlying logic — judgement needs a live adjudicator, not a stored one — and it is why I do not read this rule as supporting H2a.

## Counter-evidence to my own Factor 2 verdict

**The strongest objection to H2b.** If judgement were merely un-adjudicable rather than weak, escalated questions would be *good* questions. Mostly they were, but `DECISIONS-PENDING.md`'s section B is a list of roughly thirty production observations dumped for "disposition" — several of which the agent could reasonably have decided. That looks like judgement-avoidance under cover of deference. **However**, the campaign's own rules mandated exactly that behaviour (`evidence-before-fixing.md`: *"DO NOT act unilaterally"*), so the observation cannot distinguish avoidance from compliance. **Unresolvable in this corpus.**

**The strongest objection to rejecting H2a.** The campaign's signature failure — the **clean null** — is a failure of judgement *about* a measurement. `08` lists five: *"A path regex that matched 27 of 313 files and reported a total. A database query returning **zero** dangling links by matching 4 of 746 rows on a prefix that does not exist in that schema. A HEAD-vs-tree comparison that agreed exactly because both runs imported the working tree. A corpus replay reporting zero flips because the permissive fallback made the transition unobservable. An adversarial verifier **confirming a false claim** … because it inherited the original's search scope."* And: *"**A junior says 'I'm not sure.' These systems produce a symmetric, confident, wrong result and move on.**"*

**This is a real capability finding and it is the 30% I assign to H2a** — but it is not the H2a Arnon stated. It says the system is bad at *asking whether the number means what it appears to mean*, which is over-trust in the measurable, not preference for it over the soft. `08` draws the operational consequence, and it is the right one: *"**review does not catch a clean null; only a control does.**"*

**Counter-evidence in the other direction, worth recording.** When a brief *invited* generalisation, the agent generalised and it went wrong. `09` on ticket 19: the coder *"implemented the brief's suggested generalisation, which 'broke the sink heuristic for the common real-traffic shape `python3 - <<'EOF' 2>/dev/null || true`… **misclassifying a genuine foreign-executor heredoc as a harmless generic sink and losing its ask_floor**.'"* Caught by the corpus replay, not by inspection. Widening is not free and is not automatically safer.

---

# What each verdict implies for what to DO

The two rivals have different fixes, so the proportions matter more than the ranking.

## For Factor 1

**Because H1b is dominant (~60%), briefs are cheap and are the highest-return intervention.** Three concrete changes, each supported above:

1. **Give at least one round per ticket an architecture-only brief, and point it at the proposal, not the diff.** The back-test found 8 live architectural defects in already-reviewed code for the cost of one agent, and its own recommendation is unambiguous: *"**run it on proposals, not on diffs.**"* This is the single highest-yield item in this document. **Cost**: one blinded round. **Falsifier**: the control arm — run the general `/code-review` on the same subjects and see if it finds the same eight.
2. **Keep the scope-inflation guard, and keep "do not fix, report."** It is not the problem; it *raises* finding yield (*"prohibiting the fix increases the yield"*). What must change is the other end: a filed finding must be actioned. `07`'s verdict on the eleven-day MCP brick is a **tracking** failure — *"a product defect recorded only in the queue is a defect that will never be actioned."* The fix is a queue with an owner and a gate, not a looser brief.
3. **Say in every repair brief which of the previous round's non-blocking findings are fixed / deferred-with-a-reason / rejected.** `09` item 6: four documented escalations each burned a full extra round on something a previous round had already written down; ticket 18's oscillation alone cost *"~$17-19 and ~1h45m of reviewer time plus three repair passes."* Called *"the cheapest fix identified anywhere in the corpus and it is in no project rule today."*

**Because H1c accounts for ~25%, briefs will NOT reach that quarter, and this is the part most likely to be mis-fixed.** When the local judgement is *correct*, exhorting the agent to widen produces either compliance against its own correct reasoning, or the ticket-19 regression above. The two mechanisms the retrospective names as actually working are both structural:

4. **A debt register with an owner and a budget**, whose trigger is *"the third workaround for the same missing abstraction — **count workarounds, not their individual justifications**."* Because each justification is individually sound, the count is the only visible signal.
5. **Decouple behaviour-pinning from unit tests early**, because *"the reason each local judgement came out 'disproportionate' is that the tests pinned the shape. An equivalence oracle … changes which cleanups are affordable, and therefore **which local judgements come out right**."* This is the only intervention in this document that changes the *answer* rather than the *instruction*.

**Because H1d accounts for ~15%, cap change-set size and schedule synthesis as a step.** `corrections-analysis.md` supplies the design parameter: the trigger is *"**files changed and lines changed in existing files**, not time and not step count."* And `transferable-practices.md`: *"**Synthesis has to be scheduled as a step with its own moment in the process, not trusted to fall out of doing enough narrow checks.**"* Note that H1d applies to Arnon too — this is not an agent-management item.

**What would be a waste of effort under this verdict**: prompt-level exhortations against eagerness ("think about the wider picture", "don't just fix the symptom"). H1a as a disposition is not supported, and the corpus contains no instance where narrow fixing was chosen over a *known-cheaper* wide fix.

## For Factor 2

**Because H2b dominates (~70%), the highest-return interventions are about the adjudication channel, not about the agent's reasoning.**

6. **Make the escalation channel first-class and cheap, and make its latency the thing you optimise.** The capability is demonstrably present (F2-DC1, F2-DC2); what was missing was somewhere for it to go. `08` measures the cost of the missing adjudicator differently and it is the binding constraint: *"my availability is actually the constraining resource always."* Batching decisions into `DECISIONS-PENDING.md` was the right adaptation; what it lacked was a service level.
7. **Require an agent to surface a judgement it acted on, not only ones it deferred.** The canary case is the whole argument: the coder made the right call and *"silent non-compliance is the only thing that saved it. No review caught it."* A judgement exercised silently is indistinguishable from one never made.
8. **Under human-in-the-loop, expect this problem to shrink substantially — but do not expect it to vanish**, and specifically do not expect a reading review to substitute for an instrument. `08` is blunt about the trap: *"a manual review is a reading review, so it inherits exactly the blind spot that the executing reviews closed."*

**Because H2a survives in its narrowed form (~30%), one intervention persists in every mode:**

9. **Every measurement that will be acted on carries a control that should fail and doesn't, or a total that must reconcile.** This is the one item that is a genuine capability compensation and it does not go away with a human in the loop — arguably it matters *more*, because `08` observes: *"A human who receives a tidy, plausible, confident number from an agent has no signal that it covered a twentieth of the population. **The control belongs in the instrument, not in the reviewer**, because the reviewer cannot see the gap."*
10. **Before proposing any new check, name the declaration it checks against.** Where the tool must supply the judgement itself, label it a heuristic and never report it as a verdict. Four escapes from one enumeration; `09` rates this **high confidence**.

11. **Give every step in a mandated sequence a completion artifact, or expect the ones without to vanish silently.** This is F2-DC0's fix and it is the highest-return item in the Factor 2 list, because it is cheap, mechanical, and addresses a failure that exhortation demonstrably does not reach — the instruction was already explicit and already mandatory. For the TDD cycle specifically, "refactor while green" needs a terminator that produces an artifact the reporting template has a slot for. Candidates, in increasing cost: **(a)** a required report section — *"Refactoring performed while green (say 'none, and why' if none)"* — which costs one line in the template and converts an invisible omission into a visible claim somebody can dispute; **(b)** a named, checkable output, e.g. no function added by this increment exceeds the project's complexity threshold, or the increment's diff contains at least one commit whose tests are unchanged; **(c)** the second half of Arnon's own framing made explicit in the definition of done — *"the objective of the refactoring is to transform 'provably working code' to 'well structured and provably working code'"* — stated as the increment's acceptance criterion rather than as the method's name. **Start with (a).** It is nearly free and it is the one that tests whether the diagnosis is right: if the step was *not encoded* rather than *avoided*, a slot in the template is sufficient to make it happen. **Falsifier**: add the section, and if agents fill it with "none" while shipping code they would have restructured, the diagnosis is wrong and the cause is closer to H1a than this document concludes.

**What would be a waste of effort under this verdict**: trying to make the agent "better at soft criteria" in the abstract. It is not obviously worse at them — F2-DC1 is a soft judgement that beat every measurable signal pointing the other way. Effort is better spent on where soft judgements *go* and on distrusting clean numbers.

---

# What this evidence cannot settle

1. **The decisive Factor 1 experiment was never run.** The back-test's own declared limitation: *"**The control arm was not run.**"* Until an architecture-briefed round is run on a diff the campaign already reviewed, the split between "the brief did not ask" and "the reader could not see it in a diff" rests on n = 4.
2. **The Factor 2 mode question has no comparison arm at all.** There is no human-in-the-loop ticket on this codebase with instrument-line-share, escalation rate, or soft-judgement-quality measured. The 70/30 split is a reasoned allocation, not a measurement, and I would not defend the numbers — only the ranking.
3. **Silent successes are unrecoverable.** Every proportion involving "the agent widened and was accepted" is biased downward, because acceptance leaves no artifact. The two clearest instances (DC2, F2-DC1) survived only because the agent wrote them up itself.
4. **Briefs are inferred from recalls.** 38 of 102 recalls assert a "do not fix" instruction. The briefs are mostly absent from the corpus. If recalls systematically over-report constraint, H1b is overstated — though I know of no mechanism that would produce that bias.
5. **Everything here is dated to July-August 2026 models, one codebase, one person's working pattern, and a mode explicitly chosen as abnormal.** `08`'s caveat applies to this document too: *"the corpus contains **no user-originated ticket at all**, so field validity is entirely untested."*
6. **One primary conflict remains open**: whether Arnon's architectural finds came from proposals or from small diffs. The back-test and `corrections-analysis.md` disagree, both are primary, and both agree only on *artifact size*. Flagged, not resolved.

7. **F2-DC0's null is a null about the record, not directly about the code.** It establishes that no report describes refactoring performed after reaching green. It cannot establish that none occurred — an agent could have restructured while green and simply not written it down. Two things make the stronger reading likely rather than certain: the reporting templates are otherwise detailed to the minute, and the step vanishes from the *instruction's own restatement*, which is a record of perception rather than of reporting. **What would settle it**: diff the increments. If a TOO-19 increment contains a structural change with unchanged tests, refactoring happened and went unreported. Nobody has looked, and it is a cheap check.

8. **The TDD evidence is drawn from four files in one ticket (TOO-19).** The corpus-wide null is broad, but the four-step-to-three-step truncation — the mechanism — rests on one plan and three reports. n is small.

---

# One-line answers

**Factor 1**: the observation is right and the cause is mostly not the agent — it is that the campaign told the agent not to widen, at scale (0 of 30 review rounds were scoped to the system), and that where it *was* free to widen the local cost calculation came out correctly against widening. Better briefs and an actioned finding-queue reach about 60% of it; a debt register and an equivalence oracle reach another 25%; change-set caps and a scheduled synthesis step reach the rest. Exhorting the agent to be less eager reaches none of it.

**Factor 2**: the system is not poor at soft criteria — it overrode every measurable signal to protect a test oracle, relocated code across a layer boundary on a documented-boundary argument, and refused to regenerate a golden corpus it could have regenerated. What it lacked was somewhere to put a judgement; what it is genuinely bad at is doubting a clean number; and what it does not do at all is a mandated step that has no completion signal — the TDD refactor phase appears **zero times** in this corpus as work performed, dropping out of the agent's own restatement of the four-step instruction that required it. Human-in-the-loop dissolves the first, makes the second more dangerous rather than less, and reaches the third only if the human asks — which is why the third wants a slot in the template rather than a better prompt.
