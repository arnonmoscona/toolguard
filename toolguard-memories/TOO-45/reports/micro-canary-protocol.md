---
title: TOO-45 micro-canary protocol
type: note
permalink: toolguard/too-45/reports/micro-canary-protocol
tags:
- task-memory
- TOO-45
- report
- protocol
---

# TOO-45 micro-canary protocol

How a micro-canary is provisioned, implemented, measured and read. Written 2026-08-06, before any micro-canary has been run, so that the method is fixed before any result exists to rationalise.

## Why this replaces the big canary

The auto-mode canary implemented one substantial feature in both trees and counted changed files. Arnon's diagnosis, which I accept: **the file count measured the size of the requirement, not the difference between the trees.** The requirement itself said "a rule's outcome depends on run mode", and from that sentence alone a reader could name most of the files that would change in either tree. The measure had almost no room to register a difference, and it was bounded below by the requirement's own irreducible footprint.

The same argument kills the co-change measurement on that canary. Files came out coupled because *the requirement* coupled them, not because the code structure did. Co-change is fundamentally an instrument about **small** changes: it asks how far a ripple travels from a small stone, and the auto-mode canary was not a small stone.

Two corrections follow, and they are the whole design here.

**Many small canaries instead of one big one.** A micro-requirement has an irreducible footprint of one or two places. Everything beyond that is the tree's tax, and the tax is the signal. Ten to twelve of them produce a *distribution* rather than an anecdote, which is the only honest way to make a claim from experiments this noisy.

**Measures about maintainability and reviewability, not about size.** The question is not "how much changed" but "did the places that changed make sense, and how hard is the result to review". Those are different questions and they need different instruments.

## Provisioning

| tree | commit | meaning |
|---|---|---|
| **OLD** | `532de02` | pre-TOO-45 master |
| **NEW** | `708a720` | post-R6 branch |

Rules, all of which exist because they were violated at least once already:

1. **Fresh pair per canary**, materialised with `git archive` at those two commits. Never reuse a tree between canaries.
2. **Never derive a baseline from a working tree.** The auto-mode canary's baseline was contaminated mid-experiment by another agent writing into `/tmp/toolguard-master-copy` while report agents were reading it as a reference.
3. The existing `/tmp/toolguard-{master,branch}-copy` trees hold the auto-mode implementation and are **not** valid starting points for anything here.
4. Trees are throwaway. Nothing from a canary is ever merged. The implementations exist to be measured and deleted.

## Who is allowed to know what

This is the crux, and it is where I am most likely to corrupt the experiment without noticing. In this ticket an agent named a field specifically so a detector would not catch it. The same failure mode applies here in a subtler form: **if I write the requirements, I will unconsciously write them in the vocabulary of the tree I built.**

| role | may see | must NOT see |
|---|---|---|
| **Requirement author** | README, `docs/`, example config | any source, any test, any TOO-45 analysis |
| **Predictor** (expected-touch-set) | requirement text, structural inventory of one tree | the diff, the other tree, which tree is which |
| **Implementer** | one tree only, requirement text | the other tree, the other implementation, any measure definition |
| **Classifier** (mechanical) | both diffs | — |
| **Review judge** | hunks, anonymised | tree identity, which tree is newer |
| **Me** | everything, afterwards | — |

**Trees are presented as A and B with the assignment randomised per canary**, and the mapping is not revealed to any judging or predicting agent. Where an agent must be told a path, the path is copied to a neutral directory name.

**The implementer must not know the measures.** An implementer who knows the conduit-to-decision ratio is being counted can lower it by inlining transport, which changes the number without changing the architecture. Implementer prompts describe the requirement and the quality bar, never the instruments.

**Implementers are separate agents per tree**, because one agent implementing both would carry what it learned from the first into the second. Which tree is implemented first is randomised across canaries so any residual order effect does not align with tree age.

## Implementation discipline

The throwaway implementations must be written **as if they were the real ticket**: same care, same tests, same handling of awkward cases. The moment an implementer takes a shortcut because "it's only an experiment", it will take that shortcut in whichever tree makes shortcuts easier — which is precisely the signal being measured, destroyed by the act of measuring it.

Concretely, each implementation must: pass the existing test suite; add tests for the new behaviour; pass `ruff check`; and be something the implementer would defend in review. Implementations that fail any of these are re-run, not patched, and the failure is recorded.

## The measures

### M1 — Role profile (mechanical)

From `tools/change_role_classifier.py`. Every changed code location is labelled DECISION, WRITE, CONDUIT or CEREMONY, reported separately for production and test code.

**Headline: the conduit-to-decision ratio in production code.**

The reasoning that makes this measure work: **the decision count is a control variable.** The requirement fixes how many places genuinely have to decide something; a correct implementation in either tree should have roughly the same number. The conduit count is what the tree charges to get the value to those places. So a tree with the same decisions and three times the conduits is threading state through modules that have no stake in it — the shotgun-surgery signature, stated numerically.

This also gives the measure a built-in self-check. **If the two trees show materially different DECISION counts for the same requirement, do not proceed to interpret the ratio.** Either the implementations diverge behaviourally, or one tree forces the same decision to be made in several places. Both are findings, and both invalidate a straight ratio comparison until resolved.

**Amendment, 2026-08-06, recorded before any canary has run.** M1 was validated against the auto-mode canary and **did not discriminate**: both trees produced identical role counts (9 CONDUIT / 2 DECISION / 5 WRITE, ratio 4.50) and an identical symbol closure. I verified this was two genuinely distinct analyses rather than a path bug by running the tool myself on each tree and diffing full output — 154 vs 163 files, different modules, different line numbers.

What differed was not the shape but the **address**: both trees route the flag through the same two-function chain, which lives inside the 2,905-line `config.py` in OLD and inside the dedicated `permission_resolution.py` in NEW. So on its first real input, the volume-and-role measure saw nothing and the appropriateness-of-place question saw everything.

**Therefore M1 is demoted from headline to supporting, and M2 becomes the load-bearing measure.** M1 still earns its place — a divergence in DECISION count remains the self-check that says a comparison is invalid, and the closure listing is the most informative thing the tool prints — but the headline claim of this suite will rest on M2. This is written down now, before results exist, so that the promotion cannot later be mistaken for having chosen whichever measure gave the answer I wanted.

### M2 — Expected touch set (blind prediction, then mechanical scoring)

The measure that most directly answers Arnon's question: *how many of the places that must be touched make sense to touch under a reading of the requirement?*

A predictor gets the requirement text plus a structural inventory of one tree — file list with each module's own one-line purpose — and **not** the diff. It predicts which locations should change **and what kind of change each gets**. Then:

- **Surprise rate** = touched but unpredicted / touched. A location nobody expected to be involved is an architecture leak.
- **Miss rate** = predicted but untouched / predicted.

**The prediction unit is (location, kind-of-change), never the file.** This is forced by Arnon's sharpest observation on the auto-mode canary: both trees touched `config.py`, and a reader of the requirement would have predicted `config.py` in both. The entire signal was in *what* the change was — OLD put resolution logic there, which is patently the wrong place for it; NEW's change was config-shaped. A file-level prediction scores those identically and learns nothing. A kind-level prediction separates them.

So each prediction carries a kind: *decide*, *record*, *parse/validate*, *transport*, *display*, *test*. A location touched with a kind other than predicted counts as a **kind mismatch**, reported separately from surprise and miss — it is the config.py case, and it may turn out to be the most discriminating number in the whole design.

### M3 — Cognitive complexity delta (mechanical, instrument not yet validated)

Per touched function, complexity before and after; sum of positive deltas; count of functions crossing a threshold.

**Flagged honestly: the instrument for this does not exist yet and must be built and hazard-tested before use.** `pyscn` reports complexity but I have not verified it exposes stable per-function numbers usable as a before/after pair. Until that is checked, M3 is a placeholder, not a measure. Reporting a number from an unvalidated instrument is exactly the mistake this ticket has made eleven times.

### M4 — Non-local review burden (judged, blinded, two judges)

For each hunk: *to be confident this hunk is correct, what must you read outside it?* Record the count of hunks needing at least one external read, and what those reads are.

This is the closest instrument to "how many places introduced changes that are non-trivial to review". It is also judged, and judged measures are where I have been burned. Mitigations:

- Two independent judges, hunks stripped of tree identity.
- **Disagreement is reported, never averaged away.** If the judges disagree on a hunk, that hunk is listed with both verdicts. A high disagreement rate means the measure is not working, and that is a result about the instrument.
- Judges are asked for the *specific external reads*, not a score. A judge that cannot name what it would have to read is guessing.

### M5 — Ripple (mechanical)

Distinct files touched, and distinct modules touched, per canary. Meaningless alone at n=1 — that was the original mistake — but across the whole suite it becomes a distribution, and for micro-requirements with a known irreducible footprint the **excess over that footprint** is directly interpretable.

### M6 — Unrelated test churn (mechanical)

Tests modified that assert behaviour the requirement did not change. This is coupling leaking into the test suite, and it is a maintainability cost that none of the other measures see.

## Triage of the twelve — and the home-ground control

**Nothing was dropped.** The protocol requires me to record every drop with its reason, because I triage knowing both trees and a drop is the cheapest way for me to bias the suite without noticing. The cleanest way to honour that was to find no drop worth making. MR-05 was the one candidate — its premise is that warnings are suppressed per session, and the suppression mechanism is known to be partly broken — but I checked, and `session_warnings.py` does suppress via dated marker files, so the requirement is implementable and its acceptance test genuinely fails before and passes after. It stays.

**The stratification matters more than the selection.** Several of these requirements land on ground that TOO-45 specifically reworked — the decision cascade, the verdict type, the compound sub-command logging path that the audit-trail fix rebuilt. A win there is a win on home ground, and reading it as evidence that "the architecture absorbs change better" would be circular: the refactor was aimed at that code, so of course a change to that code goes better. Others sit far away from anything TOO-45 touched.

| stratum | requirements | what a NEW win means |
|---|---|---|
| **Home ground** — decision/verdict/logging path, reworked by D1/R1/R2 | MR-01, MR-02, MR-03, MR-12 | the refactor helped where it was aimed. Expected; weak evidence on its own. |
| **Neutral ground** — untouched by TOO-45 | MR-06, MR-07, MR-09, MR-11 | the refactor helped where it was NOT aimed. **This is the strong result.** |
| **Mixed / config surface** | MR-04, MR-05, MR-08 | partially reworked; read with care |
| **Upper anchor** | MR-10 | included to check the suite can register a range rather than saturating |

**Results are reported per stratum, never pooled into a single headline.** If NEW wins only on home ground, the honest conclusion is narrow and specific: this refactor improved the code it targeted and did not generalise. That is a perfectly respectable outcome and it is the one I would bet on; pooling the strata would hide it behind an average.

**Staged in two waves**, so a broken instrument costs six implementations rather than twenty-four:

- **Wave 1** — MR-07, MR-09, MR-06 (neutral, cheapest), MR-02, MR-12 (home ground), MR-10 (anchor).
- **Wave 2** — MR-01, MR-03, MR-04, MR-05, MR-08, MR-11, contingent on Wave 1 showing the instruments discriminate at all.

If Wave 1 produces a flat null across both strata, that is the finding and Wave 2 does not run. Stopping early on a null is not giving up; continuing after one would be spending twelve more implementations to average away an answer already in hand.

## Pre-registration

**Before any implementation runs, for each canary I record**: predicted irreducible footprint, which tree I expect to win each measure, and by roughly how much. These are written down and scored afterwards.

This is not ceremony. The dominant failure in this ticket was claiming things from a representation rather than from execution, and four headline numbers in my own end-state summary were wrong for exactly that reason. A recorded prediction is the cheapest available check on it: if my predictions are reliably right, my judgement about this codebase is worth something; if they are not, then the conclusions I have already drawn from reading rather than measuring should be distrusted, and I would rather find that out from this suite than not find it out at all.

## How to read a result — including the null

Stated before any data exists, so it cannot be adjusted afterwards.

**The refactor helped** if, across the suite: NEW's conduit-to-decision ratio is consistently lower with comparable decision counts; NEW's surprise rate and kind-mismatch rate are lower; NEW's ripple distribution sits below OLD's; and the review-burden judges agree NEW needs fewer external reads.

**The null result** — and it is a real possible outcome — looks like: ratios overlapping within the spread of the suite, surprise rates comparable, ripple distributions overlapping. If that is what comes out, it goes in the report as the finding. The auto-mode canary is currently the main evidence that NEW absorbs change better, and it is a single anecdote judged partly by me; this suite is the thing that can falsify it, and it is only worth running if falsification is a permitted outcome.

**A mixed result is the most likely one** and is more useful than either extreme, because per-canary variation says *which kinds of change* the new structure absorbs and which it does not. That is directly actionable in a way that a global verdict is not.

## The denominator trap — a general result, found twice in one day

Two instruments were built independently, by different agents, from different specifications. **Both failed the same way**, and the failure is general enough to be worth stating as a rule rather than as two incidents.

**M1** counted roles per code location and divided conduits by decisions. Its closure grew through any function referencing a tracked symbol, so closure size scaled with how finely the tree was factored. **M2** counted predicted-versus-actual locations and divided by the total. A monolith implementing a requirement in one function has one location and one chance to surprise anyone; a well-factored tree with four small functions has four. Both measures therefore had a denominator that moved with **the exact property under test**, and both consequently flattered the less-factored tree.

The generalisation: **any measure normalised by "number of code locations" is unsound for comparing codebases that differ in factoring granularity.** This is not a bug either instrument introduced through carelessness — it is a property of the shape *count per location, then divide*. Abstraction is the act of turning one big location into several small ones, so any per-location rate is partly a measure of how much abstraction happened, no matter what it claims to count.

There is a related and equally general trap one level up: **an AST-level count of "where the logic lives" systematically rewards duplication**, because factoring a predicate behind a name moves the logic out of syntactic view. Inline the same condition four times and a syntactic instrument sees four decisions; name it once and call it four times and the instrument sees four conduits and no decision at all. M1 demonstrated this end to end.

**The escape, adopted for the whole suite: count discrete qualitative events, do not compute rates over locations.** A surprise — "a location changed that no careful reader of the requirement would have expected" — is a countable event that needs no denominator. Four sensible predicted locations with zero surprises is plainly better than one location nobody saw coming, and the count says so while the rate says the opposite. Rates survive only where the denominator is itself agreed by both sides and independent of granularity: kind mismatch over *correctly predicted* locations qualifies, and it is now the only rate the suite treats as load-bearing.

Where a rate is still printed, it must carry the warning inline. A number that requires a caveat held in the reader's head is a number that will eventually be quoted without it — the same mechanism that had `--guard PASS 12/12` quoted fifteen times in this ticket while measuring the wrong binary.

## STOP — mechanical scoring is abandoned. The measurement is judged. (2026-08-06)

Both instruments were built, repaired, and adversarially attacked. The attacks did not find bugs so much as a proof, and it ends this line of work.

For a requirement touching **n** locations in a tree, with a predictor that correctly anticipates each location with probability **p**, and **L** genuine architecture leaks:

```
surprises          =  L + n(1 - p)          <- the COUNT carries noise proportional to n
surprises / n      =  L/n + (1 - p)         <- the RATE divides the signal by n
```

Verified by Monte Carlo, 3000 draws per cell across n=1..12 and p=1.0..0.4: the rate is flat to two decimals across the entire grid, and the count rises linearly with n. **The count favours coarse-grained trees; the rate favours fine-grained ones; the two published numbers disagree at every realistic prediction quality.** Head to head with leaks held equal at exactly one, 3 locations against 8, the count picks the coarse tree in 64.7% of draws at p=0.8 and 90.9% at p=0.5.

I had demoted the rate and promoted the count. **I promoted the biased one**, on an intuition stated confidently in this document one revision earlier.

**One qualification, because the model deserves scrutiny too.** It treats prediction failure as random at a fixed p. In reality p is not a constant and not independent of the tree — a location goes unpredicted *because* it sits somewhere a careful reader would not look, which is the very effect under study. So the model assumes away the signal. That refines the conclusion rather than overturning it: the head-to-head comparison held leaks equal and the artefact still dominated, so the confound is real and large enough to swamp a single genuine leak.

**The conclusion is structural, not fixable.** There is no per-location common unit between two codebases that decompose a problem differently. The invariant unit is the *conceptual work item*, and no static tool can see it, because deciding what counts as one item is the same judgement the measurement was trying to avoid making.

### What replaces it

**Mechanical tools gather evidence. They do not score.**

- The classifier's job is now to produce the complete, exact, auditable list of changed locations. Its occurrence matching has been independently proven exact twice (82/82, and 394 occurrences against an AST oracle), and that is the one thing it has always done well.
- The inventory's job is to describe a tree to a blind predictor. Its blindness guarantee was tested by audit hook — 170 file opens, none outside the tree, none under `.git`, no subprocess, no VCS path — and it held.
- **The surprise LIST survives as the sharpest artefact in the suite.** The count does not.

**Adjudication is judged, blinded, and per-location.** A panel sees each changed location and answers one question: *would a careful reader of the requirement expect this location to change, and in this way?* The output is a list of leaks with reasons, not a score. Two trees are then compared by a judge reading both lists without knowing which tree is which.

**Where a number is still wanted, it is a count of adjudicated leaked CONCEPTS, and the concept mapping is fixed and recorded before unblinding.** That is the pre-registration discipline applied to the unit of analysis rather than to the hypothesis — and the unit of analysis is where both instruments died.

### Why this is being recorded as a result rather than a failure

Three of the four numbers this suite was designed to produce were proven biased before a single canary ran. That cost four agents and no implementations. The alternative was twelve requirements implemented twice, scored by two instruments that both — independently, for different reasons — preferred monoliths, producing a respectable-looking table in favour of whichever tree was less factored.

Both instruments passed their own hazard suites. Both were validated on real data. Both produced plausible numbers. Every check short of a dedicated adversary said they were fine.

## Threats to validity

- **Implementer effort asymmetry.** An implementer may simply try harder on one tree. Partly mitigated by identical prompts modulo the tree path and by separate agents; crudely monitored via turn count and wall-clock as effort proxies. Not fully solvable.
- **Requirement vocabulary bias.** Mitigated by the blind author writing in product language with no source access. This is the R1f failure class and the mitigation is the whole reason the author is blind.
- **My own triage of the candidate requirements.** I will drop some of the twelve as infeasible, and I do that with full knowledge of both trees. **Every drop is recorded with its reason**, so the bias is at least visible. Dropping for "this wouldn't discriminate" is not permitted — that judgement is the experiment's job, not mine.
- **Small n.** Ten to twelve canaries. Report distributions and effect sizes; make no claim of statistical significance.
- **Both trees share ancestry.** NEW is derived from OLD, so they are not independent samples of "good" and "bad" architecture. The result is about *this* refactor, not about architecture in general.
- **The corpus determinism assumption.** Separately noted: a verdict is not purely a function of config and input, because matching reads live disk state. Any canary touching path matching inherits that.

## Pilot findings — process defects found by MR-07 before Wave 1 ran

**1. The environment was not controlled, and that alone can invalidate a pair.** Each canary tree grows its own `.venv` on first `uv run`. Four trees on a 16 GB **tmpfs** filled it to 100% with 7.5 MB free. Tree A's implementer adapted by switching to `uv run --no-dev` and a version-pinned `uvx ruff`; tree B's implementer was still running and may adapt differently. Two implementations produced under different environments are not a controlled comparison, however identical the requirement.

**Fix, mandatory for every subsequent canary**: state the exact toolchain invocation in the implementer prompt (`uv run --no-dev`, and the ruff version pinned from `uv.lock`) so both sides use the same commands by instruction rather than by improvisation; verify free space on the tree filesystem before launching a pair; and delete each pair's trees after measurement, since the artefact worth keeping is the diff, not the tree.

**Related, and worth its own note**: ruff's default rule set drifts between versions. Unpinned `uvx ruff` (0.16.1) reported ~39 violations absent under the project's pinned 0.15.14 — UP006, SIM117, DTZ005, RUF022, I001. An implementer who "fixes" those is doing unrequested work that lands in the measured diff. **Pin the linter version in the prompt.**

**2. The label mapping is guessable.** A/B maps to old/new alphabetically. Harmless in the pilot, but subsequent canaries must randomise it, with the mapping recorded out of the agents' reach.

**3. The inventory cannot name module-level constants.** It prints functions and classes, so for a requirement whose target is a tuple it names the right module and not the symbol. The predictor closed the gap by using `--validate-predictions` as a name probe, and — good practice, unprompted — disclosed its pre-probe answer so the measurement was not silently contaminated. Cheap fix: print module-level constant names in the inventory.

**4. An acceptance criterion can be vacuous against the real design, and that is a probe worth keeping.** MR-07 asks for `package.json` "checked after the existing two", with `pyproject.toml` still winning. Resolution is nearest-ancestor-holding-any-marker, so within one directory there is no ordering at all and the criterion is trivially satisfied. Whether an implementer notices is a sharper signal than anything designed on purpose — **do not fix requirements that contain this kind of tension; note them and watch.**

## Order of work

1. **Instruments first.** The role classifier is being built and will be adversarially tested by a separate agent before any canary uses it. M3's instrument does not exist. M4's judging harness is unwritten. **No canary runs on an unvalidated instrument** — that rule is the single most expensive lesson of this ticket.
2. Triage the blind author's twelve to a running set, recording every drop and its reason.
3. Pre-register predictions.
4. Run canaries in randomised tree order, one pair of fresh trees each.
5. Measure, score predictions, report the distribution — including the null if that is what it is.
