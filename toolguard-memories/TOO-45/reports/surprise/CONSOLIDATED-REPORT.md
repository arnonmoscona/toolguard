---
title: TOO-45 surprise factor - consolidated report
type: note
tags: [task-memory, TOO-45, measurement, report]
permalink: toolguard/too-45/reports/surprise/consolidated-report
---

# The surprise-factor experiment: what it measured, and what it is worth

**Question**: before a ticket is implemented, can a blinded estimator predict which files it will touch — and does the gap between prediction and outcome tell us anything about the ticket, the codebase, or the estimator?

**Method**: for each ticket, an estimator read **exactly two files** — the ticket as filed, and a file inventory (path, line count, first docstring line only). It wrote its predictions to two sealed files and returned a token. The coordinator did not open them until the work was committed. Scoring is **line-weighted recall against the final committed diff**: of the lines a reviewer must read, what fraction landed in a file somebody predicted.

**Why line-weighted**: Arnon redefined the metric mid-campaign — *"what I care about is expected and final complexity of the task... The final outcome reflects the human time to review."* A 2-line surprise and a 300-line surprise are not the same review. Recomputed for item 78: surprise is 29% by file count and **5% by lines**. File-counting overstated review burden six-fold.

## Results — 15 items scored

| item | line-weighted recall | note |
|---|---|---|
| 22 | **100%** | first fully-clean run; character-of-fix also correct |
| 85a | **100%** | predicted both ratchet files unprompted |
| 74 | **100%** | first perfect touch set; correct scope call from exclusions |
| 39 | 99.1% | contaminated by a coordinator appendix |
| 20 | 95.0% | 89.3% discounting wrong-reason hits |
| 15 | 87.8% | leak discount **inert** — genuine foresight |
| 04 | 76.6% | honestly a range (57.5–76.6); see below |
| 44 | 71% | |
| 03 | 64.4% | but **12.0%** unleaked |
| 80 | 56% | no design leak |
| 18 | 52% | unleaked downstream **0/7** |
| 10 | 45.8% | mostly an artifact — see scope purity |
| 79 | **15.2%** | the worst, on the most expensive ticket |

Excluded: **19** (estimator leaked its predictions through the return channel; declared void before implementation).

## What the experiment actually established

### 1. The measure is confounded, and the confounds are the finding

**Ticket leak.** Some tickets name the files they will touch, sometimes with line numbers. Recall on those measures **transcription**, not foresight. Item 03 scores 64.4% raw and **12.0% unleaked**; item 18's unleaked downstream was **0/7**.

**I overstated this.** A mid-campaign finding claimed leak level predicts recall *monotonically* across three points. Scoring four more broke it in both directions — item 10 is the most leaked and scores worst; item 15 is moderately leaked, scores best, and its leak discount is inert. **Three ordered points looked like a law; seven look like a correlation with large residuals.** The error was mine and its shape is this campaign's own recurring one: confidence from an absence of counterexamples in a set I had not finished measuring.

**Design leak.** Item 77's chosen design was given to the estimator; production recall was **9/9**. Item 80, scored the same day without it, was **5/9**. A separate exposure from file leak, and the aggregate must control for both.

**Scope purity.** Item 10's commit carries an unrelated `.gitignore` fix and a folded-in default change. Only **12 of 620** unpredicted lines are attributable to the estimator. Its 45.8% is mostly not about prediction at all.

### 2. Repository properties get mislabelled as estimator error

**Doc-file identity**: estimators predicted `README.md`; the change went to topic files under `docs/`. Two for two, then a third. That is a fact about this repo's documentation layout, not an estimator failing.

**Test-file identity**: same shape. And item 85a predicted a new test file at high confidence from *"one test file per production module, with no exceptions I could find"* — measured, **11 of 39 modules have none**, all constant- or type-holding leaves. **The inference was sound and the premise was false**: an inventory is bad evidence for absence, because a missing file is not a row.

**Fitness ratchets**: this repo has machine-checked declarations (`.pyscn.toml` layers, `PATH_AMBIENT_OWNERS`, an import manifest) that make certain one-line fixes touch a second file **by construction**. That falsified one of my own predictions on item 64 — and an estimator predicted both ratchet files unprompted on item 85a.

### 3. The uncertainties file is sometimes the better instrument

Item 79's estimator named `compound.py` and the exact question governing **79% of the diff** — *"whether the floor-application logic needs to change, versus purely receiving better input"* — said it could not resolve it under blinding, and predicted against it. Item 03's uncertainties named its largest miss in advance and its own briefing critique named the trap it then fell into.

**Proposal**: when an estimator flags a binary uncertainty that would move a large share of the touch set, treat the flag as the estimate. The coordinator is not blinded and can resolve it by reading one call site.

### 4. Asking for the CHARACTER of a fix beats asking for its file list

Added at item 22: *will this be a reworded message, or a structural change?* The file list is usually leaked; the character of the fix rarely is.

- Item 22: the estimator said **prose**; I said **structure**. It was right, reasoning from what a *previous commit* had already done. **A blinded estimator beat the coordinator on the only unleaked question.**
- Item 85a: asked move-or-re-export, it said **move**, because *"a re-export facade... the dependency would point the wrong way."* **Chunk C then made exactly that mistake** and had to be repaired. It named a later chunk's defect while estimating an earlier one.

**This is the single highest-value change to the protocol**, and it costs one paragraph.

### 5. Recall correlates with cost, and low recall is a decomposition signal

Item 79: **worst recall (15.2%) on the most expensive ticket** — eleven agent runs, four review rounds, three security weakenings caught pre-commit. Both facts have one cause: `kind` drove the ASK floor *and* audit decomposition, so a small correct fix reclassified a leaf and collapsed the breakdown.

If that holds, a low predicted recall is a signal to **decompose before starting** — Arnon's outlier rule arrived at from the other direction.

## What went wrong with the instrument

**Contamination, two routes, seven items.** Return channel: items **05, 19** leaked predictions in the reply. Coordinator appendix: items **20, 39, 57, 64, 70** — I appended measurements to ticket files, which are the estimator's only permitted reading. **Measuring before briefing was the campaign's highest-yield habit; writing the result into the ticket is what destroyed the measurement.** Fixed mid-campaign with a `measurements/` directory.

**The return-channel wording is now measured.** Substantive leaks: 2 of N under weak wording, **0 of 3** under wording that names the consequence. Two of those three still emitted a harmless preamble, which settles a design question: **forbid disclosing a prediction, not emitting a sentence.** A rule routinely half-obeyed teaches the reader to judge which half matters.

**Three of four backfilled items had been scored against a working tree, not the commit.** That hid a real alarm: item 04's write-up says *"zero alarms"*, but an omitted file changed because `--eval` printed its verdict to the wrong stream and the existing test was pinning the bug — cause `D`, the series' first. **Score against the commit; what is unstaged is disproportionately what surprised you.**

**Cause `B` (brief-constrained), new.** On item 64 I predicted the implementer would reuse or extract rather than write a third atomic-write — then wrote a brief forbidding every route to that outcome. The prediction was not wrong about the world; it was **incompatible with the instructions issued alongside it**. Any item where the coordinator both predicts and instructs can produce a "miss" that measures the coordinator's own inconsistency. **The estimator does not have this problem, because it never writes the brief** — an argument for separating the roles that has nothing to do with blinding.

## Verdict

**As a predictor of review burden, the measure is weak and heavily confounded.** Raw recall spans 15% to 100% and most of that spread is explained by how much the ticket gave away, how pure the commit's scope was, and whether the design was pre-decided — not by estimator skill.

**As an instrument for finding out things about the codebase, it earned its cost.** It produced: the doc-file and test-file identity findings; the fitness-ratchet property; the observation that this repo's tickets are frequently stale (**six items in phase 3 needed no work once measured**); and, through the character-of-fix question, two cases where a blinded estimator saw something the coordinator missed — one of them predicting a defect that shipped two chunks later.

**Recommendation for a future series**: keep the character-of-fix question and the uncertainties file; drop the file-list recall headline or report it only leak-discounted and scope-pure; separate estimation from briefing; and never let a measurement touch the artifact being measured.

---

# ADDENDUM — the source-only cut, and the finding it produced

Added after the report above, at Arnon's request: recompute over **source files only** (`toolguard/`, `tools/`), excluding tests and documentation, focused on **scope**. Full working in `PRODUCTION-ONLY-SCORING.md`.

Rationale: two of the confounds named above — doc-file identity and test-file identity — are **repository properties**, not estimator error. Removing them should leave a cleaner signal.

## Result: cleaner in level, not in signal

**Pooled 84.2%** (82.5% excluding canopy-generated `bash_parser.py`), median item **96.0%** against 87.8% all-files. But the **standard deviation barely moves** (26.4 -> 24.1), and **the bottom two ranks are invariant**: item 79 gets *worse* (15.2% -> 13.8%) and item 39 too, because their failures were entirely in production. All the reshuffling is in the middle.

**The interesting variance was never in tests or docs.** The gains are real but were already argued for: item 10 gains 42 points purely because its commit carried unrelated `.gitignore` recovery; item 77 gains 39 because its whole loss was the `docs/` topic-file confusion.

## The scope asymmetry — the most useful thing the whole experiment produced

**Over-scoping is the normal failure and is nearly free. Under-scoping is rare and expensive.**

54 inert production predictions against 32 missed production files — but **3 of the 32 carry 811 of the 958 missed lines (85%)**. The remaining twelve items miss an average of 12 lines each.

**And every large under-scope has one shape: a new module, or a control-flow relocation. Never a call-site sweep.**

| miss | lines | what it was |
|---|---|---|
| `file_matching.py` (item 03) | 278 | an extraction out of `resolve.py` |
| `compound.py` + `resolve.py` (item 79) | 357 | ASK-floor plumbing the estimator explicitly reasoned would **not** move |
| `ambient.py` (item 44) | 120 | an extraction, predicted as `testability.py` inside `path_utils.py` |

Call-site sweeps — what estimators over-predict most — never cost more than 37 lines.

**So the single question worth asking an estimator is: does this change carve out a new module, or relocate control flow?** An estimator that could answer it would recover ~85% of the missing mass. Nothing else on the list would move the number materially.

**This supersedes the file-list question entirely**, and it is the same lesson as the character-of-fix finding above, sharpened: ask about the *shape* of the change, not its inventory.

## A ceiling artifact this cut introduces

Five of fifteen items now sit at exactly **100%**, separable only on precision (20%-64%). On the source-only view **precision carries more information than recall for the top third** — which inverts the rubric adopted at item 18, where precision was demoted to an integrity guard.

## Revised recommendation

Report the **source-only** figure, since it stops charging the estimator for two repo properties and for commit hygiene it did not control. But it is a cheap proxy for the correction the numbers actually argue for: **score the ticket's own work, not the commit.** Item 10's number is still 47% an artifact of one unrelated fix folded into its commit; excluding tests does not fix that, and only scoping the diff to the ticket would.

---

# ARNON'S DECISION, 2026-08-21 — the experiment continues, with a corrected purpose

## The purpose I had wrong

I evaluated this as *"is the estimator accurate?"*, with recall as the output. **That is not the objective.** Arnon:

> *"The estimator is not the objective here - it's a means to an end. The value is in surfacing what we really need to look at so that we catch problems early and don't let them slide."*

Under that framing the experiment is already succeeding: items 03, 44 and 79 were flagged by the number, the second look graded the architecture, and it produced transferable conclusions — about **authoring tickets so the estimator does better and execution stays focused**, not about estimators.

**A low recall is a prompt to investigate, not a grade.** Judged as a trigger rather than a predictor, the confounds I catalogued matter far less: it does not have to be precise to be worth looking at.

## The validity problem I failed to name

**Almost every ticket in this series was written by me, as a side-effect of other work.** Arnon's own tickets differ on every axis that matters:

| this batch | normal operations |
|---|---|
| written by the agent, mid-campaign | written by Arnon |
| long, heavily argued | far less text |
| bugs found by analysis | features mostly; bugs only when hit in production |
| solution often inferred by the agent | solution specified by Arnon when he has one |
| certainty rarely qualified | **explicitly flags when he is unsure of a solution** |
| straight to implementation | **plan authored, reviewed and discussed first** |

**So almost no ticket here represents the normal development process.** I recorded seven contaminated items across two routes and never noticed that the *population itself* was unrepresentative — a larger threat to the conclusions than anything on that list.

## Decisions

1. **Continue until at least 20 human-authored tickets have been completed through the normal process** — plan first, reviewed and discussed, then implement.
2. **Switch the headline metric to production files only** (`toolguard/`, `tools/`).

## One thing the new process adds that the old one did not have

With a plan authored and discussed before implementation, there are **two** predictive artifacts, not one: the **ticket** and the **agreed plan**. They answer different questions.

- Estimating from the **ticket** measures *how well-specified the request was.*
- Estimating from the **plan** measures *whether we understood the work before starting.*

**The second is the one that catches problems early**, which is the stated goal — a plan whose touch set is wrong is a plan to revisit before any code is written, and that is the cheapest possible moment.

**Recommendation: estimate from the plan, and keep the ticket-only estimate only where a ticket is implemented without one.** Where both exist, the gap between them is itself informative: it measures what the planning conversation added.

## What to expect from the shift

**Under-scoping should fire more often, and that is the signal working, not degrading.** Feature work creates modules; the diagnosis found that every large under-scope in this series was a new module or a control-flow relocation, never a call-site sweep. A feature-heavy population will trip that more, which is precisely the class worth catching before implementation rather than during it.

## The two-estimate protocol, per Arnon 2026-08-21

Score **both**: a **raw estimate** against the ticket, and an **informed estimate** against the agreed plan. Both against production files only.

> *"If we assume that planning [is] cheaper, and that during planning we may change scope up or down or even decide whether or not to bother with the ticket at all, then measuring both will give us also an idea of where we should take more care than we do."*

### What each measures

| | measures |
|---|---|
| **raw** (ticket) | how well-specified the request was |
| **informed** (plan) | whether we understood the work before starting |
| **raw -> informed** | what the planning conversation added |
| **informed -> actual** | what planning still could not see |

The last one is the one that matters for catching problems early: **a plan whose touch set is wrong is a plan to revisit before any code exists.**

### The 2x2, which is the actual instrument

| raw | informed | reading |
|---|---|---|
| bad | good | **planning earned its keep** — the ticket was underspecified and the plan repaired it |
| bad | bad | **planning did not help.** Either the problem is invisible until code is touched, or **the plan inherited the ticket's frame.** Ticket 44 is the warning: its own last section had the right architecture and its first section had the wrong prescription — a plan built from the prescription would have been confidently wrong |
| good | good | well-specified ticket, confirmatory plan. Cheap and fine — but if this is most items, the planning step is buying less than it costs |
| **good** | **bad** | **planning made it worse.** A plan can ADD scope error by committing to an approach that turns out to be the wrong shape. **Nobody looks for this cell**, and it is the one that would justify planning *less* on some ticket classes |

### Two things that must be recorded or the numbers lie

**1. Tickets killed during planning.** If planning kills a ticket there is no commit to score, so it vanishes from the data — **while being planning's single clearest win.** Count them separately as a headline: *"N tickets killed at plan stage"* is evidence for the planning step, not missing data. In this campaign six tickets needed no work once measured, and measuring happened to be cheap; under the normal process that discovery moves into planning, where it belongs.

**2. Scope changed during planning, with direction.** If planning halves the scope, the informed estimate scores against a smaller actual and looks better *for the wrong reason*. Record up / down / killed explicitly, so a good informed score is not confused with a shrunken target.

### The raw estimate has a second use, and it is free

An agent reading a ticket is cheap, and the raw estimate can be run on **every** ticket — including ones never implemented. **A ticket the raw estimator scopes as very large is a triage signal before planning starts**: either it needs decomposition, or it is a candidate to kill. That is the estimate paying for itself before the expensive step rather than after it.

**Corollary**: run the raw estimate *before* the planning conversation, never after. An estimate made after planning is contaminated by it and measures nothing.
