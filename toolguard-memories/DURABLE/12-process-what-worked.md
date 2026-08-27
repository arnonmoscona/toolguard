---
title: 12-process-what-worked
type: note
permalink: toolguard/durable/12-process-what-worked
tags:
- TOO-45
- durable
- process
- retro
---

# 12 — Process: what this campaign actually validated

**This is an evidence document, not a runbook.** Nothing here is written as an instruction. Each element states what it is, the primary that evidences it, its cost in **agent time/tokens** and in **Arnon's attention** — separately — and a recommendation. **Adopt-list at the bottom.** Decide before anything is encoded into a skill or a rule file.

## Two evidence bases, and they are not equivalent

| base | what it records | weight |
|---|---|---|
| `toolguard-memories/` (TOO-45) | **an autonomous agent loop**, explicitly *"not my normal working pattern"* | measured, dense, mode-specific |
| `~/.claude/CLAUDE.md`, `.claude/rules/*`, auto-memory `feedback_*` | corrections made during **normal human-in-the-loop work**, TOO-8 / 15 / 17 / 19 era onward | fewer numbers, but the right mode |

**Where they agree, that is the strongest signal available**, because one mode is autonomous and one is collaborative. **Where they disagree, the guidance file generally wins for the mode Arnon will be in** — with one flagged exception below, where the corpus ran an experiment the memory predates. Both are cross-referenced per element.

## Currencies and confidence

Arnon, 2026-08-24 (`08-autonomous-loops-vs-human-in-the-loop.md:39`): *"my availability is actually the constraining resource always as this is not my main activity."* `08:37` records an earlier draft tabulating 45h of agent rework against 58.1h of his blocked wall-clock and calling them comparable — *"That is the **wrong-currency** mistake."* The two never share a column here.

**high** = re-measured, or two independent primaries agree. **moderate** = one primary, nothing contradicts it. **low** = judgement. **n=1 is flagged separately** — a result can be high-confidence *and* a single instance.

**The limit on everything below** (`09:464`): *"**Zero of 76 primary tickets originate from a user.** … **74 of 76 were manufactured by looking.**"*

---

# PART A — process for the orchestrating agent

## A-0 — the sequence the evidence supports

Derived from what was measured, not from any prior sketch. Steps marked **[normal-work]** are validated by the guidance files rather than by TOO-45.

| step | what | why this step exists |
|---|---|---|
| **0. Probe before briefing** | few-line throwaway probe answering "is this ticket real, and is its diagnosis right?" | *"Measuring a ticket before briefing it is this campaign's highest-yield habit. It closed ticket 57 with zero work, corrected ticket 20's diagnosis, and grounded 39, 64 and 70."* Result goes in the brief, **never into the ticket file** |
| **1. Write the proposal, then REVIEW THE PROPOSAL** | one architecture-only round, aimed at the plan/spec | the back-test's sharpest result: same defect **hit in the proposal arm, missed in the diff arm**. This is the gate that does not exist anywhere in the current guidance |
| **2. Implement** — two-phase if a formal artifact is involved | `.peg` + regeneration alone first, reviewed, then Python | **[normal-work]** `feedback_grammar_changes_two_phase` (TOO-17) **and** TOO-45's only two clean PASSes. Strongest cross-mode agreement in this document |
| **3. Implementer self-check before reporting** | inventory existing code for duplication / reimplementation / drift | **[normal-work]** `feedback_impl_selfcheck_dup_drift` (TOO-15). TOO-45 measures nothing here — this is a normal-work element the corpus is blind to |
| **4. ONE review round whose reviewer EXECUTES a differential** | two isolated trees, `PYTHONPATH` pinned, provenance printed inside the run, diffing `decision` *and* `matched_rule` | all three serious security defects were found this way, each round says *"Measured"*. A reading round returns claims |
| **5. Mutation on the mechanism just built** (when the change *is* a mechanism, and headroom allows) | rebind a live attribute to a wrong-but-plausible value; diff failing test **sets** | 2,314 tests stayed green through a swap that corrupts every audit entry |
| **6. Repair brief carries forward every non-blocking finding**, marked fixed / deferred-with-a-reason / rejected | — | four escalations each burned a full round re-litigating something already written down |
| **7. Re-review only because the REPAIR is new code** | fresh blinded reviewer, not one handed the prior findings list | *"Eleven agent runs, four review rounds, and three security weakenings — **each introduced by the fix for the previous one**"* |
| **8. Phase-end gate before the commit** | review of the phase's changes + coverage state | **[normal-work]** `feedback_phase_end_gate` (TOO-15). See the coverage divergence in A-x below |
| **9. Hand over** — small change set; focused reports + small diagrams if the ticket is hard | — | **[normal-work]** `feedback_reports_and_diagrams_for_hard_tickets`; trigger is *"sentiment, not a phrase"* |

**The dial the evidence supports is KIND, not COUNT.** Steps 1, 4 and 5 are three different instruments against three different defect classes. Nothing in the corpus measures the marginal yield of a *second reviewer of the same kind on the same artifact*. What it does measure is that later rounds paid **because the repair created new defects** — and that when they did not, they caught the coordinator: ticket 18's *"rounds 3-6 caught errors of the **coordinator's**, not the implementers'"* (`surprise/18-scored.md`), and ticket 19's extra round *"measures coordinator error here, not ticket difficulty"* (`surprise/RESULTS-LOG.md`).

**Independence, not duplication, is the validated property.** Arnon, turn 229: *"We **validated** the method we chose to look at things from multiple *independet* angles."* Two reads of the same diff are one angle twice.

## A-1 — comparison with the illustrative gate sequence

His illustration: *"let feature-coder implement, then run an automated two different blinded judge reviews, fix outcomes and give me material for manual review only when all gates pass."*

| his illustration | what the evidence supports | why |
|---|---|---|
| starts at **implement** | **a proposal review comes first** | T3 (the #10 spec) hit / T4 (the identical defect in the committed diff) missed. *"the judge sees architectural defects in proposals and not in diffs."* n=4 — flagged |
| **"two different blinded judge reviews"** | **one round whose reviewer executes**, plus rounds that differ in *kind* | the discriminating variable is execute-vs-read, not count. `09:77`: *"**Blinded review is a container, not a technique**"* — a container being the point, since it lets each reviewer bring a method nobody specified. A second *reading* round adds a second reading blind spot; two rounds differing in kind do not |
| **"fix outcomes"** as a single step | the repair pass is a **process element with its own documented failure mode** | four escalations re-litigating prior non-blocking findings; and the repair is where several of the worst defects were *introduced* |
| **"when all gates pass"** | **gate on the CONVERGING SHAPE, not on a clean round** | 28 of 30 artifacts report findings, so an all-clear trigger never fires. That is not a defect in the rounds — a round returning findings is a round yielding. The stop signal the evidence supports is the drain curve: counts falling round over round, with what remains small enough that the manual review carries it. See the note below |
| manual review **last** | **agreed, and the strongest thing he can bring to it is a small change set** | but manual review is a *reading* review and inherits the blind spot the executing round closes (`08:106`) |
| — | **his illustration has no probe step and no exposure measurement** | probes are *"the least planned for"* and best per unit cost |

**What matches exactly:** blinding; agents doing the review; the human reading only when the automated work is done; and treating the repair-then-recheck loop as normal rather than exceptional.

### The stop condition, stated properly — Arnon, 2026-08-24

An earlier version of this document, and of `05` and `09`, described rounds returning findings as rounds that *failed*, and described reviewers using different methods as a comparability problem. **Both framings were wrong and are corrected.**

> *"The blinded reviewers are not there to produce predictability. They are there to uncover blind spots — just like the mutation method does. It's the surprises that we're actually looking for, not confirmation. And it's the converging shape that signals that we're getting to a reasonable stop point. This is exactly how QA teams should, and often do (if management allows the time), assess whether product quality is approaching 'ready for release' state."*

Three things follow, and they change how the table above should be read.

1. **Variation between reviewers is the product, not noise.** The three serious security defects were found by three differentials that differ from each other and none of which was briefed — a `PYTHONPATH`-shadowed HEAD tree, a `bash -c 'printf %s ~name'` oracle, a 38 × 39 grid loading the old matcher from a git blob. Specifying one method would have found one defect. So the rule is **require that something be run; do not require that the same thing be run.**
2. **The unit of judgement is the series, not the round.** A round is an observation. Release readiness is a property of the trend across rounds plus what the human finds at the end. Individual rounds do not need to be comparable to each other for the trend to be readable, any more than successive QA cycles need identical test plans.
3. **Not clearing every item is a normal, successful outcome.** Arnon: *"If it doesn't waste my time, even small improvements that I would not care about are still improvements. Even if we don't end up clearing every single thing by the stop decision — but the manual review passed — then you have success."* The residue is a backlog, not a failure of the gate.

**And the non-converging case is the mechanism's best result, not its worst.** Ticket 18 ran 2 → 2 → 1 → 3 → 3 → 2 and never drained. Its matcher fix was verified correct from round 1; what kept regenerating findings was a `curl` carve-out recipe whose guidance contradicted itself, so each repair created the next finding. The suite was green throughout and the production diff was small and right. **A flat curve was the only instrument that could see this** — no per-round verdict, and no clean-gate trigger, would have shown anything. Detail in `05-campaign-statistics.md` §6.

## A-summary

| # | element | agent cost | Arnon cost | conf. | verdict |
|---|---|---|---|---|---|
| A1 | **Reviewer EXECUTES a differential** | +0 (same round; cheapest 13m16s / ~$4) | ~0 | **high** | **ADOPT — highest value** |
| A2 | **Architecture-only review of the PROPOSAL** | 1 round (~54 min / ~$7 mean) | ~0 | moderate (**n=4 + n=1**) | **ADOPT** |
| A3 | **Mutation testing, in-process** | **~161k tok/agent (n=12)** — the one measured token figure | ~0 | high | **ADOPT selectively** — rate-limit-bound |
| A4 | **Probes budgeted; measure a ticket before briefing it** | **lowest of any mechanism** — minutes | ~0 | mod-high | **ADOPT** |
| A5 | **Carry last round's non-blocking findings into the repair brief** | ~0 | ~0 | high | **ADOPT — cheapest fix in the corpus** |
| A6 | **"The brief is unverified — verify it"** | **~0** | ~0 | high | **ADOPT** |
| A7 | **A control that should fail, inside the run; provenance printed by the measurement** | low | ~0 | high | **ADOPT** |
| A8 | **Two-phase change for a formal artifact** | moderate | ~0 | **low-mod on generalising** | **ADOPT for formal artifacts only** |
| A9 | **Measure exposure before fixing** | low | low | moderate | **ADOPT, with the rule's own caveat** |
| A10 | **Name the declaration; prefer a runtime sentinel to an enumerated bad-list** | low | low | high | **ADOPT** |
| A11 | **Every mandated step needs a completion artifact** | ~0 | ~0 | mod-high | **ADOPT** |
| A12 | **Keep the scope-inflation guard; fix the queue instead** | ~0 | **real (B10)** | high | **ADOPT** |
| A13 | **Re-score replays as if `no_match_fallback` were `ask`** | one flag | ~0 | high | **ADOPT** |
| A14 | Staff prose rounds differently from behaviour rounds | saves money | ~0 | **low — judgement** | **DO NOT adopt yet** — run the cheap experiment |

## A1 — the reviewer executes

`09:67-77` re-reads all three security-defect rounds in their own files. `review-79-round1.md` B1: *"A `deny` — and an unoverridable `hard_deny` — inside a substitution is downgraded to `ask`"*, evidenced *"Measured post-fix vs a pre-fix shadow tree… **`PYTHONPATH`-shadowed**"*. `review-78-round2.md` B1: *"Measured, comparing against **`bash -c 'printf %s ~name'`**"*. `review-18-round2.md` B1: measured *"over a 38 × 39 pattern/command grid"*. Conclusion: *"Its yield against the silent class is entirely attributable to reviewers who executed something. Where a round only read, it returned claims."*

**Cost.** No extra round; review-78 round 2 was **13m16s / ~$4** and caught one of the three. Arnon reads a two-line before/after table.

**It does not go away with a human in the loop** (`08:115`): *"A human reading the diff does not find a `hard_deny` silently becoming `ask`. This is the strongest transferable finding here."*

## A2 — architecture-only, on the proposal

**Two runs, both n-limited.** The back-test (`TOO-45/reports/architecture-judge-backtest.md`: 8 blind judges, one architecture-only brief — *"If you find a bug, ignore it"* — one subject each, pre-registered key) found **8 live architectural defects in already-written, already-reviewed, already-committed code**, including *"`is_builtin` conflates structural description with enforcement policy"* — the campaign's signature shape, found by an AI. Its ground truth: *"**2 of 4 — and both hits are in arm B.** T4 is literally T3 in a different substrate and was missed there… **the judge sees architectural defects in proposals and not in diffs.**"* The report labels itself *"n = 4 positives. Establishes existence, not a rate."*

The confirming run (`10:343-369`, 2026-08-24): a fresh blind agent given `3bb21b7` with an architecture-only brief produced **7 findings on a diff 30 rounds already had; 3 of 3 spot-checks CONFIRMED at HEAD** — three Protocols written as *"a structural contract pyright actually checks"* while `pyrightconfig.json` has `"typeCheckingMode": "off"`; production importing the private `_combine_strictest`; two pipeline drivers already diverged with ~40 tests pinning the one with no production callers. **n=1, and the commit was chosen because it is architectural.**

**Why it works is a scope finding, not a capability finding.** `11:73`: of 30 review rounds, **0** were given the system, a layer map or a module inventory. `10:367` names what differed between the two runs: *"this brief named the defect classes to look for and pointed at a declared layer map (`.pyscn.toml`); the back-test asked for judgement against pre-registered axes."*

## A3 — mutation testing

**The contrast that carries it** (`rejected-methods-and-metrics.md` B5, six modules in one evening): read-only review said `edit_proposal` had *"Nothing substantive… its fixtures build exactly what its Givens describe"* and called it the best of five — mutation found **16** zero-detection mechanisms; `self_permission` **13 of 25**; `migration_gate` **11 of 22**. *"A statement can be correct and still name the problem it is dismissing."* Ticket 35: production's Bash hard-deny check was bypassed entirely and `test_hard_deny.py` gave *"**exactly one failure**… **All ten tests in `TestHardDenyCommand` — the class named for the mechanism, in the file named for the mechanism — detected nothing.**"*

**Cost:** ~161k tokens/agent, range 142k–197k, **n=12**; twelve agents = 1.93M tokens, 94%→99% of the weekly limit, ~2.5h to exhaust a session window. Arnon ~0. **Expensive in the elastic currency, free in the binding one.**

**Caveat that must travel with it:** B4 catalogues **fifteen** harness traps, *"every one of which produced a confident wrong number, usually a **false zero-detection**"*. Rules earned: **diff the failing test *sets*, never counts**; **a mutation run must state its target**.

**Yield, settled** (`09:130-134`): **18 of 76 primary tickets; ~38 of 105 distinct subjects.** The much-quoted *"roughly fifty"* is unsubstantiated at that magnitude.

## A4 — probes, and measuring before briefing

`practices-with-evidence.md` §3, headed *"The most valuable practice nobody planned for"*: *"They do not trend, do not gate, and cannot be dashboarded; they answer one question decisively and are discarded. On this ticket they produced more findings per unit cost than either metric class and were the least planned for."*

`TOO-45/measurements/README.md`: *"**Measuring a ticket before briefing it is this campaign's highest-yield habit.** It closed ticket 57 with zero work, corrected ticket 20's diagnosis, and grounded 39, 64 and 70."* — and, from the same file, *"**Appending those measurements to the ticket files destroyed the blinding.** … Contaminated by this route: 20, 39, 57, 64, 70."*

**One line of config attached:** give every agent its own scratch directory. A cleanup that ran `rm -rf *.py` in a shared scratchpad deleted *"exactly the four files review-18-round4.md cites as 'Evidence:'"*.

## A5 — carry the previous round's non-blocking findings forward

Four consecutive rounds of ticket 18 measured the same axis and got a worse or equal answer each time — r3 *"too narrow to be usable"* → r4 **1 of 15** ordinary variants exempt → r5 **11 of 22** permitted → r6 **1 of 16** realistic invocations allowed. Rounds 4-6 cost *"roughly **$17–19 and about 1h45m of reviewer time**"* plus three repair passes. Three more instances (77, 78, 80). *"**Every one was pre-stated in writing by the round before, as a non-blocking finding the repair brief did not carry forward.**"* `09:444` calls it *"**the cheapest fix identified anywhere in the corpus and it is in no project rule today.**"*

## A6 — "the brief is unverified"

One paragraph per brief; roughly **thirty** caught false claims, *"including the same figure wrong three times."* It has **negative controls** — three sampled reports record *"Nothing in the brief was false. Every one of B1-B7 reproduced exactly as described."* Diagnosed cause: *"A report is a session delta; a review measures HEAD."* It catches false claims, **not omissions**.

**Cross-mode:** `feedback_agent_reports_are_deltas_not_state` states the same mechanism from normal work and adds the coordinator's half — *"**Before writing any factual claim into a brief, measure it against HEAD**"* — and notes *"The saving grace so far is the standing instruction described below, not my accuracy."* Sharpest contrast in the corpus: tickets 74 and 18 share the same cause; **18 cost ~11 hours, 74 cost one command.**

**Author-blind, and this was missed until 2026-08-25.** The instruction must not be scoped to agent-written briefs — **it is a property of assertions, not of authors.** A human assertion has the same failure modes plus a far longer staleness clock, and four instances are documented in this project's own rule files. See `09` §12 and **B12** below.

## A7 — a control, inside the instrument

`08:82-88` lists five clean nulls: a path regex matching 27 of 313 files and reporting a total; a query returning zero dangling links by matching 4 of 746 rows on a nonexistent prefix; a HEAD-vs-tree comparison agreeing because both runs imported the working tree; a replay reporting zero flips because the fallback made the transition unobservable; an adversarial verifier **confirming a false claim** by inheriting the original's search scope. *"**A junior says 'I'm not sure.' These systems produce a symmetric, confident, wrong result and move on.**"*

**The half that gets skipped is naming which wrong answer the control catches** (ticket 105): *"**I DID run a control, and it passed, and that is why I was confident.** The control caught a real bug… Catching it made the instrument feel validated — **for a different class of error than the one I was actually making.**"*

**The specific mechanic:** print module provenance from inside the measurement, same process. Validating isolation separately via `python -c` proves isolation for an invocation that never happened. It happened **twice independently** — coordinator-side on ticket 19, where the symmetric null was used to override a correct security finding, and reviewer-side on ticket 77, caught by the reviewer.

**For Arnon** (`08:119`): *"**The control belongs in the instrument, not in the reviewer**, because the reviewer cannot see the gap."*

## A8 — two-phase change for a formal artifact

Of 30 review artifacts, **28 FAIL and 2 PASS — both PASSes are the `.peg`-only grammar reviews.** Verified against the primaries: `review-77-grammar-phase1.md:16` — *"**PASS.** The generated parser is byte-identical to a fresh canopy regeneration… no real command's parse changed across 23,594 distinct commands"*, with `raw-grammar parse failures: old=506 new=506`. `review-77-grammar-phase1-delta.md:18` — *"**PASS.** … 0 differences over 28,770 corpus commands and 88 adversarial cases… 3710 tests green"*, and it **built the rejected variant grammars and measured them**.

**Why it works** (`09:402`): *"the phase separation hands the reviewer an artifact that is *mechanically checkable end to end* — regenerate, diff, replay a corpus — where every other review round in the corpus asked a judge to decide whether a change was correct."*

**Cross-mode, and this is the strongest agreement in the document.** `feedback_grammar_changes_two_phase` was written in **TOO-17, from normal work**, for a different reason — *"to stop it from hand-rolling regex/state-machine parsing (which it did once and Arnon rejected)"* — and it independently specifies the exact gate the TOO-45 reviewers then ran: *"the regenerated parser is BYTE-IDENTICAL to a fresh canopy run (NO manual edits to the generated file)."* Two modes, two motivations, one mechanism.

**Two corrections that travel with it.** Neither PASS was clean — the first raised M1, *"four bypasses that defeat the ticket's purpose"*, forcing a second phase-1 round. And it does not immunise phase 2: ticket 101's brace grammar passed isolated validation then produced **19 unexpected failures** on the real tree, including `{ ls; }` decomposing to `['{ ls', '}']`, *"a real deny-bypass."*

**Generalisation: low-to-moderate, and the primary says so.** *"a `.peg` file is small, formally specified, and has a mechanical differential… the two clean PASSes may be a property of *the artifact* rather than of the sequencing. **What would change my mind**: one clean review round on a two-phase change to a non-generated artifact. The corpus contains none."*

## A9-A13 — briefly

**A9 exposure-before-fixing.** Already a project rule and it worked in both directions: the `sudo` ticket was approved and then found to be faithful behaviour whose evading command cannot execute; ticket 78's fix produced **0 decision changes over 26,530 real commands**. **But `09:267-271` corrects how that null is quoted**: the primary says the config *"can only be widened by the change and cannot show the direction the ticket is about. **So I synthesized it.**"* Keep the rule's strongest clause: *"zero occurrences plus accidental reachability plus silent failure is still a fix."*

**A10 declaration-or-heuristic.** *"**A check is unambiguous exactly when it measures conformance to intent a human declared, rather than inferring whether the intent is any good.**"* `--ambient`'s hand-written member list has been escaped **four** times (`expanduser`, `resolve`, `absolute`, `pwd.getpwnam`); `--orphans` and `--undeclared-types` are strong because their declaration is a syntactic convention in the code. And the sentinel result: the instrument that closed the class was **already in the repo eighteen days before the ticket that needed it** (`test/unit/_real_log_dir_guard.py`, `51045fe`).

**A11 completion artifact per mandated step.** `11:265-292`: **0** files in `toolguard-memories/` carry a phase-shaped *refactor* line — control fires (`planning` 20, `implementation` 32); **0** reports describe refactoring after reaching green. The TOO-19 plan mandates **four** steps *"…minimal code to pass, **refactor while green**"*; **all three** TOO-19 implementation reports restate it as **three**, `refactor` surviving only inside the methodology's name. *"The agent tracked the steps that could be checked… and did not perceive the one that could not."* **Not refusal, not eagerness — not encoded.** Counter-evidence that sharpens it: ~10 tickets whose *subject* was a refactor were done competently. Cheapest fix: a required report section, *"Refactoring performed while green (say 'none, and why' if none)"*.

**A12 keep the scope guard.** `transferable-practices-evidence.md` C.4: *"**A scope boundary that forbids fixing forces documenting.**… 'prohibiting the fix increases the yield.'"* The #07 sweep, whose brief **forbade code changes**, produced seventeen proposed defect tickets. The failure is at the other end — item 10's fix landed in 2 of 3 files, leaving the third **in `hook.py`, the component that governs**, bricking every non-builtin governed tool for **eleven days**.

**A13 replay under an `ask` fallback.** Arnon: *"you can assume the fallback is always ask even if in this repo it is temporarily an allow."* Without it, verdict-only comparison is blind to a rule that starts matching when the fallback already permits — featherhill **0 fallbacks in 3,675 decisions**, toolguard **9,848 of 51,918 (19%)**.

## A-x — where the guidance files and the corpus disagree

**1. Coverage at the phase-end gate.** `feedback_phase_end_gate` (TOO-15, normal work) makes two gates mandatory before a phase closes: the code-reviewer subagent, and *"Check the **state of code coverage** for the changed code."* TOO-45 measured that coverage predicts nothing about detection here — 100% line coverage on the orchestration with a *"savagely skewed hit distribution"* (`allow` 2,336 : `ask` 34 : `allow_with_warning` 6 : `deny` 6, **three defensive lines reached zero times**), and *"Assertion count, coverage and a green suite all fail to detect this; one mutation detects it in a minute."*
**Resolution:** keep the gate; read coverage as a **floor / regression check**, never as a quality predictor. The question it does not answer — *what does this suite catch?* — is answered only by mutation (A3).

**2. "No metric ever caught an architectural error; Arnon caught them all."** `feedback_stop_at_first_working_boundary` (2026-08-09, five items into TOO-45) states it: *"the metrics we built caught bugs; they never once caught an architectural error. He caught all of those, and always with a single question."*
`09:255`: the circulating version of that claim is *"sourced **only to auto-memory, never to a primary artifact**, and the architecture-judge back-test contradicts it by finding **eight live defects in already-reviewed, already-shipped code**."*
**This is the one place the corpus should win**, because it ran an experiment on 2026-08-10 and 2026-08-24 that the memory predates. **The reconciliation, and it does not embarrass the memory**: the metrics genuinely never caught one, and no review round had ever been *asked* for architecture — 0 of 30. The memory's own corollary survives intact and is the durable half: *"**ease of review is not a nicety — it is the control that works.** Small, focused, single-concern change sets are what make it possible."*

**3. Everything else agrees.** Cross-mode agreement is recorded in place above: two-phase grammar (A8), unverified briefs (A6), controls and provenance (A7 ↔ `project_green_for_the_wrong_reason`, `project_isolation_instrument_provenance`), execution-over-reading (A1 ↔ `project_comment_review_finds_code_bugs`: *"There were many instances of a comment review catching code bugs… I think the count is something like 40 or so by now"*), and prompt-free briefs (B8).

## A-y — already encoded, demonstrably not firing

These are process elements that exist **in prose today** and were measured being dropped. They are the argument for C4, not for restating them.

| already in guidance | measured non-compliance |
|---|---|
| Global CLAUDE.md, *Critical thinking*: *"pressure-test the requirements before writing code"* + the four standing review questions | `corrections-analysis.md`: *"**None of these was run during TOO-45** — the ticket about architecture never checked itself against them."* |
| Global + project CLAUDE.md disclosure rule (itself the product of a scored experiment over 77 real commands) | *"of 17 qualifying commands in one day, 7 were disclosed and 10 were not"* — a ~59% miss rate on an explicitly-encoded prose rule |
| `.claude/rules/bash-grammar.md` | the rule's own preamble: *"grammar changes have repeatedly been implemented as Python instead, **even when the instruction to use the grammar was explicit**"* |
| TOO-19's four-step TDD mandate | the refactor step vanished from all three implementation reports (A11) |
| `RED:` test annotations | **all 9 were stale — a 100% failure rate**, and one propagated into a brief and misdirected an implementer |

`feedback_condition_estimates_on_own_constraints` states the general form from normal work: *"a corrective recorded only in a per-ticket artifact is inert. **It has to live where it will be re-encountered.**"*

## A-z — validated by normal work, invisible to this corpus

Worth keeping precisely because TOO-45 cannot speak to them: **implementer self-check for duplication/drift before reporting** (`feedback_impl_selfcheck_dup_drift`, TOO-15 — *"the feature-coder subagent repeatedly rebuilt code that already existed and was tested… Arnon caught these, not me"*); **delegate coding to feature-coder, not general-purpose**; **don't over-ask on small phases** — *"PICK the simplest defensible design, STATE it in prose, and proceed"*; **punch lists enumerate inline, never point** — a pointer lost **23 of 28** open tickets across one compaction; **aggregate the small surprises** — three "smaller than expected" signals on one task is a stop-and-re-derive trigger, not three local corrections.

---

# PART B — process for Arnon

| # | element | Arnon cost | agent cost | conf. | verdict |
|---|---|---|---|---|---|
| B1 | **Cap the change set; trigger review on change volume** | **the main ask** | ~0 | high on the effect; **no threshold ever quantified** | **ADOPT — the number must be found by experiment** |
| B2 | **Review proposals, not only diffs** | shifts attention earlier; likely net cheaper | ~0 | moderate (n=4) | **ADOPT** |
| B3 | **State per ticket whether widening is authorised** | one line | ~0 | high | **ADOPT** |
| B4 | **Declare architecture in machine-readable form** | one-off, then low | moderate to build | high | **ADOPT** |
| B5 | **Voice unformed smells at quarter-confidence** | **negative** — one sentence instead of a sweep | ~0 | moderate | **ADOPT — cheapest item here** |
| B6 | **Prototype a measurement on ONE case before building it** | small | saves large | moderate | **ADOPT** |
| B7 | **Say whether a message is education or specification** | one clause | ~0 | moderate (n=1, explicit) | **ADOPT** |
| B8 | **No commands in a brief that can hit a permission prompt** | ~0 | avoids 90-min stalls | high | **ADOPT** |
| B9 | **A FACT correction may go to a running agent; a SCOPE change may not** | ~0 | ~0 | high | **ADOPT** |
| B10 | **Own the filed-findings queue** | **real, recurring** | ~0 | high | **ADOPT — the cost side of A12** |
| B11 | **Say what a change made FALSE, not what needs documenting** | ~0 | small | moderate | **ADOPT** |
| B12 | **Your assertions are unverified too — date them, and let agents check them** | ~0 (a clause) | ~0 | high — 4 documented instances | **ADOPT — added 2026-08-25** |
| B13 | **Announce an imminent compact or exit, so a continuation note gets written** | ~0 (one line) | ~0 | **effect: subjective only. The failure it guards is measured** | **ADOPT — and automate the receiving half, which is already possible** |

## B1 — change-set size, and the number nobody measured

`TOO-45/reports/corrections-analysis.md`, over ~210 human turns (~80 with content): *"**Correction rate tracked reviewability, not code quality.**"* The heaviest architectural objections — the `permission_resolution ↔ resolve` cycle, the `rule_entry` phantom edge, the `log_writer` layering — arrived at turns 357-359. He named the mechanism at turn 374: *"Now that changes are fewer files I start noticing things. Even things that are not from this change set."*

*"Those defects were present the whole time. They had survived seven directed report agents, a blind reviewer, `pyscn`, `ruff`, and 2,600 passing tests. What changed was not the code but the size of the diff in front of a human."* And: *"**the reviewer's detection rate is a function of change-set size, and below some threshold it collapses to near zero.** A large change set is not merely harder to review; it is reviewed *ineffectively while appearing to be reviewed*. Every one of those reviews reported success."*

**Cross-mode confirmation, from normal work.** `feedback_stop_at_first_working_boundary`: *"since manual review is what catches these, **ease of review is not a nicety — it is the control that works**. Small, focused, single-concern change sets are what make it possible. **That is worth more than any metric refinement.**"*

**Was a threshold quantified? No.** Searched across `toolguard-memories/` for this document: the *parameter* is named — *"files changed and lines changed in existing files, not time and not step count"* — and the number does not exist. Arnon at turn 330: *"We cannot know the thresholds without experimenting a bit. The thresholds are mostly driven by my subjective experience and my sensitivity must be measured by experimenting. No other way I know."* The attached design note: *"Start the threshold deliberately low and log every firing with whether the review found anything — a threshold that fires and finds nothing is wrong and will prove itself wrong with data."*

**Scale context** (`05:80-84`): six commits are **74.6% of all lines touched** (155,595 of 208,667); `3bb21b7` alone is 24,099 lines. That is the regime where the collapse was observed.

**His own caveat (turn 329):** the rule *"does not apply to a deliberately autonomous ticket like TOO-45, which is reviewed by documents and stress tests instead."*

## B2-B11 — briefly

**B2 proposals over diffs.** `10:201`: *"**The dividing line the evidence actually supports is substrate, not reader.** A proposal states intent, so a boundary error is a sentence you can disagree with. A diff states edits, so the same error is distributed across changed lines and reads as normal."* n=4 on ground truth. **Note the unresolved tension**: the back-test says his own finds came *"from proposals, never from reading merged code"*; `corrections-analysis.md` says they came from small change sets at turns 357-359. Both primary. They agree only on artifact size — which is why B1 and B2 are both adopted.

**B3 authorised scope, per ticket.** The campaign both penalised widening in writing and elsewhere relied on it. An implementer refused a correct out-of-band finding: *"a scope change like this belongs to Arnon/the coordinator, not to me mid-task."* The coordinator wrote it up as policy: *"**That is the correct behaviour and it should be preserved, not trained out.**"* The other side (DC2): an agent widened on exactly the judgement Arnon calls hard, because *"The coordinator's message explicitly allowed relocation… **so I proceeded rather than blocking**"*. **The determinant was the licence, not the effort.**

**B4 declare the architecture.** `evidence-before-fixing.md`: *"Declaring a decision in an explicit, machine-readable form is what converts a mushy architectural question into a checkable one. The tool does not get smarter; the intent gets declared."* Caveat measured in the same corpus: *"any check whose configuration lives in the same repository as the code it grades can be edited to pass without the underlying property becoming true"* — demoting `once_per` manufactures a violation, adding a name to an allow-list erases it, and **zero tests fail** either way.

**B5 voice unformed smells.** Three of the five most-escalated themes were noticed early and raised late. On docstring bloat: *"that smelled. But I didn't raise it yet"* — by the time it was raised the language had reached *"do I need to change the output style?"*. *"**This is the cheapest fix in this whole document.** A smell voiced at quarter-confidence costs one sentence and I can go check it. The same smell voiced fifty files later costs a sweep."* Reciprocal for the agent: at boundaries, ask *"is there anything bugging you that you haven't said"*, not *"does this look right"*.

**B6 prototype the measurement.** *"**I built four measuring instruments to a specification that turned out to be wrong.**… A one-case throwaway prototype would have exposed the requirement-coupling problem at roughly a tenth of the cost."* Eight self-reversals are recorded, two against instructions given in the same ticket (PlantUML, specified turn 292 and dropped 370; the canary measurement design, specified 292 and rejected 329). Reversal on evidence is correct — the implication is only *validate the design cheaply first*.

**B7 education vs specification.** Turn 197: *"my comment was not a set of directives or specific instructuins. It's to educate you about how to think about a problem like this… those are just ideas from a very experienced engineers - but they are not absolute nor are they infallable. You should think about them independently, creatively, and most important critically."* One clause resolves it. Compare turn 208: *"Any observations I make based on your comments in the terminal are just incidental impressions."*

**B8 no prompt-blocking commands in a brief.** `feedback_briefs_must_avoid_prompting_commands` (normal-work capture): *"**A subagent waiting on a permission prompt is indistinguishable from a stalled one**"*, two ~90-minute stalls caused by `npx canopy@latest` in a brief the coordinator wrote. Known prompters measured: `npx <pkg>@latest`, `git worktree` (*"that will always prompt"*). And: *"**Allowed, installed, and on PATH are three different questions.**"*

**B9 FACT vs SCOPE mid-task.** *"**A mid-task correction of FACT may be sent to a running agent. A change of SCOPE may not.**"*

**B10 own the queue.** A12's yield is only banked if filed findings get actioned. **79 open + 31 resolved** proposed-ticket files exist. Measured cost of not doing it: item 10's eleven-day brick, *"then re-derived from scratch by ticket 74 five days later with no reference to the earlier finding."*

**B11 what did this make false.** `feedback_ask_what_a_change_made_false` (normal work): a documentation chunk estimated at 2 files touched 5; the three missed asserted behaviour *"an **earlier chunk had silently invalidated three commits before**, and which neither that chunk nor the next one noticed."* At estimate time, list the documents asserting the old behaviour and count them in the touch set.

**B13 announce an imminent compact or exit** (Arnon, 2026-08-25): *"At some point I started telling you every time I was about to either exit the session or compact the session. Once I started doing that you started responding by writing down continuation memories… subjectively, it felt as though things were smoother after starting this habit."*

**It is not a verification mechanism** — it verifies nothing. It is **context preservation across a discontinuity**, and it belongs next to `01` §9 because the compaction boundary is where that failure mode actually bites: **the 23-of-28 ticket loss happened across a compaction**, and it is the one measured instance of what an unmanaged boundary costs.

**Effectiveness is not measurable from this corpus and he says so himself** — *"I doubt that you can put numbers to this."* Correct: there is no counterfactual, and compliance (did a note get written?) is not effect (did it prevent a loss?). **Record it as a dated subjective assessment, corroborated only by the fact that the single worst tracking loss in the campaign was compaction-caused.** Do not manufacture a figure.

**But his second claim is wrong, and this is the actionable part.** *"I don't think there is a mechanism for pre- and post-compaction hooks in Claude Code."* **Fetched from the hooks documentation, 2026-08-25 — there are three relevant events:**

| event | fires | can it help? |
|---|---|---|
| `PreCompact` | before compaction; matcher `manual` \| `auto` | **detects** the boundary automatically — no announcement needed. Can block compaction. **Cannot inject context** |
| `PostCompact` | after compaction completes | **no** — its stdout is not added to context |
| **`SessionStart`, matcher `compact`** | after a compaction-initiated start | **YES — this is the one.** Verbatim: *"the exceptions are `UserPromptSubmit`, `UserPromptExpansion`, and `SessionStart`, where Claude Code adds plain-text stdout as context that Claude can see and act on"* |

**The plumbing is already installed and proven in this repo**: a `SessionStart` hook fires here on compaction today — it currently reports toolguard install staleness. So the automation is a change to what an existing, working hook prints, not new machinery.

**The two halves automate asymmetrically, and that is the whole design point.** The *announcement* is fully automatable (`PreCompact` fires on manual and auto alike, so it also covers the auto-compactions Arnon never sees coming). The *authoring* is not — a hook runs a command, it cannot make an agent write a note. **So do not automate the writing side; automate the receiving side.** Keep the continuation state in a file that is maintained anyway — **the punch list already is that file** — and have `SessionStart:compact` print it back into context. That removes the dependence on either party remembering, which is exactly the C4 form: a mechanism the harness executes, not something an agent must recall.

**B12 your assertions are unverified too** (Arnon, 2026-08-25): *"human assertions should not be considered an oracle and must be checked just like any AI assertion."* Four causes — faulty memory, misreading, relaying an unverified report, and **time-decay** (*"correct at the time it was written, but no longer correct at the time the work started… up to years"*). **The last two are the dangerous ones: the assertion was never wrong when made, so care by the speaker does not prevent it.** Four documented instances, all in this project's own files: ticket 82's approved-then-refuted `sudo`/`env` premise (**"Approval is not evidence"**); the native trailing-wildcard recollection, *"correct **for an earlier version**"*; the *"4 of 425 links"* figure ruled *"an **unsourced recollection, not a measurement**"*; and a recollection about reviewer quality in tension with the measurement. **A6 is the same instruction and must be read author-blind.** Cost: a clause — attach a date and a basis to a load-bearing claim, and say when it is memory rather than measurement. **The pattern to generalise is already written author-blind in `.claude/rules/native-fidelity-claims.md`**: fetch and quote with a date, *"not restated from memory, from another agent's summary, or from this repository's code."* Full treatment in `09` §12.

---

# PART C — what NOT to re-adopt

| # | mechanism | why it does not pay | evidence |
|---|---|---|---|
| C1 | **Aggregate "architecture health" scores** (pyscn's grade, and the general form) | noise band exceeds any signal; undeclared denominator; **scores 100/100 for a file it could not parse** | 86 archived reports span **61–73**; one day spans **61 to 72**; complexity covers **213 of 951 functions (22%)**. Arnon: *"like any other aggregate 'architecture metric' **we discussed** — it is pretty useless, even as a directional measure."* Use per-function cognitive/cyclomatic complexity **as a reason to review, never a verdict** |
| C2 | **Corpus replay quoted as a safety signal** | verdict-only comparison is blind by construction, and the famous null was structurally guaranteed | *"all 7 live rules naming an absolute path under home are `allow`, so this config… cannot show the direction the ticket is about. **So I synthesized it.**"* Keep replay; never quote a null from it as safety. Fix in A13 |
| C3 | **Enumerated bad-lists where a runtime sentinel is possible** | *"An enumerate-the-bad-list rule cannot catch the route nobody thought of."* | 4 escapes from `PATH_AMBIENT_MEMBERS`; `Path.absolute()` also escaped **six** review rounds |
| C4 | **Adding another prose requirement to general guidance and expecting it to fire** | it is silently dropped, and the drop leaves no trace | The whole of **A-y**: four independently-encoded mandates measured being dropped, one at a ~59% rate and one at 100%. Arnon's own global CLAUDE.md already says it — *"a 'MUST' in prose has a demonstrated track record of being silently dropped in this setup, **including after being fixed once**… propose a **hook** instead of stronger wording"* — and this campaign supplies the measurement. **Prefer a mechanism the orchestrator executes, or an artifact slot the reporting template demands, over anything the agent must remember** |
| C5 | **Coverage as a quality or defect-discovery predictor** | no repo-wide figure exists anywhere in the corpus, and nothing needed one | 100% line coverage with hit distribution `allow` 2,336 : `ask` 34 : `allow_with_warning` 6 : `deny` 6, **three defensive lines reached zero times**. Test blindness *"clusters in exactly the layers where toolguard's defects were found"* — the correlation runs **opposite** to what coverage predicts. (Keep it as a floor check — see A-x #1) |
| C6 | **A read-only review's "nothing substantive" used to decide a module can be skipped** | the verdict is accurate about what it examined and silent about everything else | six modules, one evening; `edit_proposal`, *"the best of five"*, had **16** zero-detection mechanisms. *"**A row saying 'nothing substantive here' carries no information**"* |
| C7 | **Co-change measured across the refactor that is inside its own sample** | the fix degrades the only instrument that could see the defect | 100%-coupled pairs **71 → 134 (+89%)** while the architecture demonstrably improved; mechanism pinned to **63 of 63** newly-reported pairs. Do not tune the threshold (`min_obs` 5 → +136%, 6 → +1300%); do not exclude by label. **Not rejected as a lens** — co-change was the only instrument that ever saw the `config → engine` callback inversion, which has zero import edge |
| C8 | **Prompt-level exhortations against eagerness** ("think about the wider picture") | the disposition they target is not supported as a cause | `11:50`: H1a *"is NOT SUPPORTED as an independent cause"*; brief-obedience is ~60%. *"the corpus contains no instance where narrow fixing was chosen over a known-cheaper wide fix"* |
| C9 | **A second blinded READING round on the same artifact** | it adds a second reading blind spot, not a second angle | the discriminating variable is execute-vs-read; ticket 18's rounds 3-6 *"caught errors of the **coordinator's**, not the implementers'"*; ticket 19's extra round *"measures coordinator error here, not ticket difficulty"*. **Independence of angle was validated; duplication of kind was not** |
| C10 | ~~**The anti-stall cron**~~ **REJECTION WITHDRAWN 2026-08-27 — see below.** It costs ~25 of 210 turns (~12% of the transcript) and **it is still the only thing that reliably works** | Arnon: *"you **have not** demonstrated a reliable ability to prevent stalling without a cron reminder. After you concluded that they are ineffective, we had to resort to them again due to stalls of long tasks. **Even when there was an incomplete punch list.**"* |
| C11 | **`PLC2701`, and any lint rule adopted without a known positive** | it fires only on private imports from a module *external to the importing file's package*, so it reports clean on the exact line the project's own predicate flags | considered and rejected; `pyproject.toml` ships the rejection. **Hand every candidate rule a known positive before adopting it** |
| C12 | **A present-tense marker with no enforcement** (`RED:`, `TEMPORARY`, `FIX after`) | **all 9 `RED:` annotations were stale — 100%** — and one propagated into a brief and misdirected an implementer | `project_temporary_markers_expire_silently`. The enforceable form is `@unittest.expectedFailure`; a prose paragraph is not |

## C10 WITHDRAWN — the anti-stall cron works and its replacement does not (Arnon, 2026-08-27)

**This is the one Part C entry that was refuted by events rather than by argument, and the refutation is worth more than the entry was.**

The rejection reasoned from *cost* — ~12% of a transcript — and asserted a cheaper substitute: *"ending each turn with a pending agent or a scheduled wakeup"* (`feedback_keep_work_in_flight`). **The substitute was never validated; it was inferred.** What happened next:

> *"You **have not** demonstrated a reliable ability to prevent stalling without a cron reminder. After you concluded that they are ineffective, we had to resort to them again due to stalls of long tasks. **Even when there was an incomplete punch list.**"*

**Three things follow, and the third is the general one:**

1. **The cron is re-adopted.** Its 12% overhead buys the one property that matters in an unattended stretch — the loop restarts without a human noticing it stopped. Against a stall during a long unattended task, 12% is cheap.
2. **A punch list does not close this gap**, and that is a genuine limit on `09` §13. An open, enumerated punch list was present and the stall happened anyway. **The punch list makes the *work* visible; it does not make the *agent* resume.** They address different failures and are not substitutes — recorded here because `09` §13 could otherwise be read as covering this.
3. **The general error: I retired a working mechanism in favour of an untested replacement, on cost grounds.** The measured cost was real and the measured *substitute* did not exist — I reasoned that ending a turn with pending work would suffice and never tested whether it did. **A rejection whose justification is "there is a cheaper way" needs the cheaper way demonstrated first.** This is the same shape as `13` §8's rejected approaches, except here the substitution ran in the wrong direction and the campaign paid for it in stalls.

**Consequence for the recommended set**: C10 moves out of "do not re-adopt" and into the adopted set for **autonomous operation specifically**. Under human-in-the-loop it matters far less, because the human is the stall detector.

---

# The recommended set, and what it costs

**The follow-through group is the highest return per unit cost in this table, and it needs a different delivery form from everything else** (added 2026-08-25). **A5** (carry the previous round's non-blocking findings), **A12** (guard + queue) and `07`'s sibling sweep are all priced at ~0 here, and they address what `02` §1 and `08` §6 both identify as **the largest recoverable cost in the campaign**. They are also the items most likely to evaporate, because they are process rather than instrument — and **C4 below is the measurement of what happens to process written as prose.** So do not ship them as guidance. **Ship each as an artifact slot the reporting template demands** — *siblings considered / checked / not checked*; *previous round's non-blocking findings, with a disposition each*; *deferred residuals, as tracked items rather than a paragraph.* A slot makes an omission visible without anyone automating the judgement, which is the same principle `.claude/rules/evidence-before-fixing.md` states for checks: **a check is strong exactly when it verifies conformance to something a human declared.** The residue that no slot covers is an **owner** for the queue — recurring, and named in B10.

**These are one mechanism, not four tips, and it has a name: the punch list** (added 2026-08-25, on Arnon's observation; full treatment in `09` §13, failure mode in `01` §9). **A5, A11, A12 and `07`'s sibling sweep are all instances of converting a non-trivial sequence into enumerated, individually checkable items that both parties can review against what was delivered.** The class it addresses — *work declared finished that was not done* — is invisible to every other mechanism in `09`, because a differential, a mutation run and a replay all check the code that exists against intent, and none of them can observe a step never taken. Measured here: **0 of 3** reports carrying the mandated refactor step, item 10's fix landing in **2 of 3** files (11-day brick), and **23 of 28** open tickets lost across one compaction to a punch list that pointed instead of enumerating. **Precondition, from that last one: enumerate every item inline; a cross-reference is for detail, never for membership.**

**Adopt:** A1-A13 (A3 selectively, A8 for formal artifacts only) and B1-B12.
**Do not adopt yet:** **A14** — run the cheap experiment first: one cheap-model prose round scored against the CONFIRMED-tier findings the Opus rounds produced.
**Do not re-adopt:** all twelve of Part C.

## Cost of the recommended set, per ticket

| | agent time / tokens | Arnon's attention |
|---|---|---|
| **A0/A4** probe before briefing | minutes | ~0 |
| **A2** architecture round on the proposal | +1 round: **~54 min / ~$7** mean over 19 self-reported rounds; cheapest 13m / ~$4 | reads one report |
| **A1** differential inside the review round | **+0** — same round | reads a before/after table |
| **A3** mutation, on the mechanism changed | **~161k tokens/agent (n=12)** — the dominant line item, rate-limit-bound | ~0 |
| **A5, A6, A7, A10, A11, A13** | **~0 each** — a paragraph, a flag, a report section, a scratch dir, a control | ~0 |
| **A8** two-phase, when a formal artifact changes | +1 round on the artifact alone | ~0 |
| **A9** exposure measurement | minutes | occasionally a re-decision |
| **A12** guard + queue | ~0 to guard | **the queue needs an owner — recurring (B10)** |
| **B1** smaller change sets | ~0 for agents; more commits | **the binding cost of the whole set** |
| **B2-B12** | ~0 | one clause per ticket; a sentence when something smells; a date on a remembered fact |

**Read that as: everything except A3 and B1 is nearly free.** A3 is expensive only in the elastic currency. **B1 is the whole bill** — it converts one large review into many small ones, and it is the item his availability actually constrains.

**Baselines for sizing.** Blinded review across 19 self-reported rounds: **~17h02m and ~$137**, mean **~54 min / ~$7.2**; extrapolated over 27 rounds, *"roughly 24h / $195 — **an extrapolation, not a measurement**"*. Implementer effort recorded: **112.4h across 122 tasks, 40.0% of it rework** — a floor, since it excludes reviewers and all coordinator time. Arnon was consulted on **196 of 61,946 tool calls (0.3%)**, 90.5% of the work in `auto` mode.

**Every dollar figure here is an unmetered self-report** (`09:472`): *"No source in the corpus queried a billing or usage API… every token count but one (~161k/agent, n=12, mutation) is a reconstruction; four source files retract their own clock times."*

## Recommendations resting on n=1 or a small sample

| element | what n actually is |
|---|---|
| **A2 / B2** architecture-only review on the proposal | ground truth **n=4 positives** (*"Establishes existence, not a rate"*); the confirming run is **n=1 commit**, chosen because it is architectural, 3 of 7 findings verified |
| **A8** two-phase formal artifact | **n=1 artifact, 2 rounds.** The primary explicitly says the result may belong to the artifact, not the sequencing. *Partially offset by the independent TOO-17 normal-work origin of the same mechanism* |
| **A11** completion artifact per step | one worked case, measured thoroughly; the **fix** is untested — *"if agents fill it with 'none' while shipping code they would have restructured, the diagnosis is wrong"* |
| **A3** yield figure | ~38 of 105 subjects is one classification pass by one agent. **Mechanism** high-confidence; **number** moderate |
| **B1** change-set threshold | the **effect** is high-confidence and cross-mode; the **number does not exist** |
| **B7** education-vs-specification | one explicit turn (197). Cheap enough that n=1 is fine |

## Two open contradictions, flagged rather than resolved

1. **Where Arnon's architectural finds come from.** `architecture-judge-backtest.md`: *"from proposals, never from reading merged code."* `corrections-analysis.md`: from small change sets at turns 357-359. Both primary. B1 and B2 are both adopted; which is doing the work is unknown.
2. **Whether agent architecture review is good or poor.** `10:367`: he recalls reviewers *"asked and repeatedly produced poor results"*, while the back-test scored 2/4 on pre-registered ground truth and the fresh run 3/3 on spot-checks. The proposed reconciliation — *"Conformance to a declared intent is the thing this system does well; forming the intent is not"* — is a hypothesis, not a measurement.

## What this document cannot tell you

- **Whether any of it reduces field defects.** Zero user-originated tickets; 74 of 76 defects were manufactured by looking.
- **Whether the mechanisms' yields are comparable.** They were never run against a common population. The one exception — reading vs mutation on the same six modules — covers exactly one pair.
- **Whether a human in the loop changes the ranking.** No controlled comparison. `08:110` divides it: properties of the *defect* transfer; properties of *who was orchestrating* (the 40% rework rate, the coordinator-error share, the 58.1h latency) do not.
- **How the normal-work guidance would score if measured.** The `feedback_*` files are single-instance corrections with no denominator. They are the right *mode*; they are not a sample.

**The rule to apply to this file itself** (`09:500`): *"the recurring failure here is not an obviously wrong claim — it is a plausible claim with a real citation attached, which nobody re-checks. … **for any claim resting on what a note SAYS, check what the repo DID.**"*
