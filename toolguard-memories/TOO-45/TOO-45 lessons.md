---
title: TOO-45 lessons
type: note
permalink: toolguard/too-45/too-45-lessons
tags:
- task-memory
- TOO-45
- lessons
---

# TOO-45 lessons

Transferable lessons from running an architecture overhaul as a judge-gated agent loop. Kept
deliberately separate from [[TOO-45 decision log]]: that records *what happened*, this records
*what generalises*. Written during, because Arnon's point is that the value is in what going
through it teaches, not only in what he says about it.

Reviewed at the end for what to keep and in what form. The English sense of "skill" matters more
than the Claude-skill sense.

Candidate general form is noted per lesson, since most of these are not toolguard-specific.

---

## 1. A guard pointed at the wrong target is indistinguishable from a working guard

`tmp/git_rules_check.py` validated a stale copy of the permission rules while toolguard loaded a
different file. It passed 145 cases cleanly and told us nothing. Worse than absent: the file's
own header instructed re-running it after every edit, so following the instruction *manufactured
confidence* rather than merely failing to provide it.

**Generalises to:** any check that names its own target. Verifying a guard means verifying what
it reads, not that it passes. Ask "what would this have caught?" before trusting a green result.

**Cheap detection:** when two files share a name and only one is loaded, that is the smell.

---

## 2. Counting by proxy over-counted by 41%

I quoted "17,167 recorded decisions" twice, from `grep -c "^## "` over the logs. Headings are not
decisions — 7,010 of them were Discovery entries. The real figure was 9,896, found only by
parsing the actual record structure.

**Generalises to:** measure the thing, not a shape correlated with the thing. This is the second
instance in this project of the same error (TOO-19's doc review: a prefix-assumption regex, then
a formatter-defeated regex, resolved only by AST). The recurring form: **a proxy that is right on
the examples you looked at.**

**Cheap detection:** a parser that can account for 100% of records (9,896 + 7,010 = 16,906) is
self-validating. A count that cannot say what it excluded is not.

---

## 3. Reading a framing sketch as a specification produces architecture by inference

Arnon described the tool's central flow in eleven numbered steps to show how an experienced
engineer frames a problem *before* deciding on structure. I turned "some directives apply at
evaluation time, some later" into a proposed formal `phase` attribute on rule entries.

The tell that it was wrong was available without any argument from authority: the only existing
directive, `additionalContext`, is already multi-phase. **An abstraction contradicted by its own
sole instance is a guess.**

**Generalises to:** distinguish a problem framing from a design. A framing is meant to be argued
with; a design is meant to be implemented. Converting the former into the latter silently skips
the step where you were supposed to think.

**Cheap detection:** before formalising an inferred concept, check it against every instance that
exists today. One is enough to falsify.

---

## 4. Under a permissive fallback, absence is not prohibition

With `no_match_fallback = "allow_with_no_warnings"`, removing a rule from `allow` does not stop a
command — it falls through to the fallback and is silently allowed. Stopping something requires
an explicit `deny`.

**Generalises to:** any default-open system. "I removed the permission" and "I denied it" are the
same edit in a default-closed system and opposite edits in a default-open one. Know which you are
in before reasoning about a removal.

---

## 5. Delegation is safe exactly when the acceptance gate is independent of the delegate

The verdict corpus is the load-bearing guard for the whole overhaul, which argues against handing
it to a subagent. But its acceptance gate is a mutation test — seed deliberate behaviour changes,
confirm the corpus catches every one — and that gate does not care who wrote the code.

**Generalises to:** the question is not "is this too important to delegate?" but "can I verify it
without re-deriving it?" Where an independent gate exists, importance is an argument *for*
delegation, since it frees the reviewer's attention for the gate.

**Corollary:** if no such gate exists, building one is the higher-value task, and delegating the
artifact before the gate exists is the actual mistake.

---

## 6. (open) Does the two-judge split survive contact?

Prediction, recorded before evidence: separating the blinded reviewer (no goal, judges
reviewability) from the architect judge (full context, judges direction) will produce
disagreements that a single judge would have resolved silently, and those disagreements will be
the most informative output of the loop.

Falsifiable: if the two always agree, the split is ceremony and one judge plus a checklist would
do. Revisit at CP2.

---

## 7. Mutating one site of a duplicated concept proves nothing

Two of my five seeded mutations came back MISSED and I briefly concluded the corpus was weak. It
was not. Both mutations produced **no behaviour change**, because each targeted one of two
independent implementations of the same idea — a strictness table that the consolidation function
deliberately does not use, and an undecidable floor applied at two separate sites.

**Generalises to:** a mutation test measures the *test suite* only if the mutation actually
changes behaviour. On a codebase with duplicated logic — exactly the kind you are most likely to
be testing before a refactor — a single-site mutation silently becomes a no-op, and reads as a
coverage hole.

**Cheap detection:** before believing a MISSED result, confirm the mutation changes observable
behaviour at all. Grep for other references to the constant or helper you touched. Duplication is
the default hypothesis in code you are refactoring *because* it is duplicated.

**Second-order value:** the failed mutations located the duplication faster than reading would
have. A mutation that refuses to change behaviour is pointing at something.

---

## 8. Do not report a gate as passed on one sample

The subagent that built the corpus reported success partly on the strength of a single seeded
mutation it had run itself. That mutation did pass — and two of the four in the real battery
initially appeared not to, with one genuine structural blind spot behind them.

**Generalises to:** "I tested it and it worked" from the party that built it is a coverage claim
of sample size one, made by the least independent available observer. The gate has to be run by
someone who did not write the artifact, over a battery chosen to span the failure modes.

**Related:** this is why delegation was safe here at all (lesson 5) — the independence of the
gate is what buys the delegation, so collapsing the gate into the delegate destroys the reason
for the arrangement.

---

## 9. I stated a conclusion one measurement too early

Between the first gate run and the diagnosis I told Arnon "the corpus is not ready — two
mutations it should have caught went undetected." That was wrong, and the evidence needed to know
it was wrong was one grep away.

**Generalises to:** when a guard reports a surprising failure, the first hypothesis to eliminate
is that the *probe* is broken, not the thing being probed. Especially when I wrote the probe
minutes earlier and the thing being probed has been under review for hours.

**Cheap detection:** an unexpected result that makes my own recent work look good (a gate I built
catching a corpus someone else built) deserves more scrutiny than one that does not, not less.

---

## 10. Mutation is a discovery instrument, not only a gate

Built the mutation battery as the CP1 acceptance gate — "does the corpus catch behaviour
changes?" It also found something no reading had: the undecidable floor is implemented at two
sites, revealed when a change that should have altered behaviour altered nothing.

**Generalises to:** reading finds duplication that *looks* alike. Mutation finds duplication that
*behaves* alike, which is the kind that survives review — two implementations of one rule, written
differently, neither visibly redundant. A mutation that refuses to change behaviour is pointing at
a second implementation.

**Why it matters here specifically:** the instruments used so far (call-site reading, method
inventory, import graph, co-change) all find structure that is visible somewhere. Semantic
duplication is invisible to all of them. On an overhaul, that is exactly the class of problem
that bites late.

**Practice to adopt:** when a step claims to have unified something, mutate the unified site. If
behaviour does not change, the unification did not happen — something else still implements it.
This is a cheap, direct test of the thing predicates are worst at detecting (hollow satisfaction).

---

## 11. Watch the bias of whichever instrument is currently working

Both large findings so far (C1: verdict rendered twice from loose parameters; C2: config as
decision orchestrator) came from reading call sites and method inventories. That method is cheap
and has been productive — which is precisely the reason to name what it cannot see.

**Generalises to:** a productive instrument creates a survivorship illusion. The problems you
find are the problems that instrument finds, and their apparent cheapness is a property of the
instrument, not of the codebase. Early wins arriving cheaply is weak evidence that the remaining
work is cheap.

**Practice:** for each finding, ask which instrument found it, then ask what that instrument is
structurally blind to — and schedule a different instrument against that blind spot rather than
waiting to be surprised. Here: mutation (lesson 10) against semantic duplication, and co-change
against coupling that imports cannot express.

---

## 12. Fossil signatures, and why I am a generator rather than merely a poor detector

Arnon's term (not industry standard): a **fossil signature** is a function signature that grew
organically across requirements, bugs and debugging sessions until it no longer makes sense — an
ancient city street plan. `log_writer.log_command()` with eleven parameters is one.

His observation, and I think it is right: **humans catch these early because they hurt.** Holding
eleven parameters in your head is uncomfortable, and the discomfort is the feedback loop that
triggers a refactor. LLMs are far more resilient to emerging complexity, so the signal never
fires and the rot stays under the radar.

**Evidence from this very session, both directions:**

- *Detection failure.* I read `log_command`'s eleven parameters and used them as evidence for a
  COUPLING finding ("the interface is spread the verdict out by hand"). I did not flag the
  signature itself as a defect. In the same file, on the same read, I did spot the callback
  inversion — because that is *structurally* odd. Eleven parameters are not odd to me. They are
  just eleven parameters.
- *Generation failure, worse.* My original plan for the R3 fix was to add a **twelfth**
  parameter to `_log_allowed_command`. I avoided it only by noticing that `sub_matches` already
  carried the data. A human writing that parameter would have hesitated. I did not.

**So the framing that matters: this is a generator problem, not only a detector problem.** The
missing pain signal is a *write-time* signal. Detection thresholds in a fitness tool are
post-hoc — they catch the fossil after I have added a layer to it.

**The habit that actually fits the failure mode** is a question about the DELTA, asked before the
edit, all three parts mechanically answerable without needing to feel anything:

1. Does this change **widen a signature**?
2. Does it **add another type** to a concept that already has several?
3. Does it **add a parse** of something already held as structured data?

**Interpretation rule for parameter count** (it is a diffuse signal on its own — Arnon's point —
so it needs a discriminator): look at where the arguments come from AT THE CALL SITE. Mostly
`result.x`, `result.y`, `result.z` => a missing parameter object, decisively. Many unrelated
sources => the function does too much. Same symptom, opposite fixes, one glance to tell apart.

Applied to `log_command`, the eleven fall into three coherent groups — verdict-derived (6),
environment (3), invocation context (2) — so it is **three missing types**, not one bloated
function, and the first of them is the verdict type R1 creates.

**Caveat if this becomes a metric:** parameter count is trivially gameable by bundling arguments
into an untyped dict, which is strictly worse than the disease. Diagnostic, never target — the
standing rule for every metric in this ticket.

**One contrast worth keeping.** The `Configuration` inversion was invisible to fan-in, the import
graph and layer compliance — three instruments, all blind. Parameter count is trivially visible
to static analysis, and points at the same underlying defect. The cheap signal and the expensive
one converge. Where a cheap instrument exists for a defect I cannot feel, use it — my not
noticing is not evidence of absence.

---

## 13. Mutate what you just built, not only what you are protecting

I built a mutation battery as the CP1 gate and pointed it at the *engine*, to ask "does the
corpus catch behaviour changes?" I never pointed it at the field R3 introduced.

A blinded reviewer did, and found the finding of the step: mutating
`matched_rule=matched_pattern` to a WRONG value (`reason_with_prov`) left **all 2,300 tests
passing**. Mutating it to `None` failed 2. The suite caught *absent* attribution and not *wrong*
attribution — for a change whose entire premise was carrying that value correctly.

**Generalises to:** a test suite that passes when a new value is wrong is not testing that value.
The cheapest way to find out is to make it wrong on purpose. Assertion count, coverage and a
green suite all fail to detect this; one mutation detects it in a minute.

**Why I missed it:** I was thinking of mutation as a *gate* on someone else's artifact (does the
corpus work?) rather than as a *probe* of my own. The technique was in hand and aimed elsewhere.

**Practice:** when a step introduces a new field, type or invariant, mutate it to a plausible
wrong value before declaring the step done. "Does anything fail?" is the acceptance criterion —
not "did I add assertions".

**Related:** lesson 10 said mutation is a discovery instrument, not only a gate. This is the same
lesson arriving a second time from the other direction, which suggests I under-applied it the
first time rather than failing to record it.

---

## 14. Two judges disagreeing was worth more than either judgement

Recorded as a prediction in lesson 6, before evidence. Result on the first real step:

- The **architect judge** (full context) said close R3 with tails into R1.
- The **blinded reviewer** (diff only, no goal) said "worth doing, but not finished."

They disagreed on the decision that mattered, and the blinded one was right — it had
mutation-tested the new field and found it unpinned, which the architect (reasoning about
direction) did not check.

**Both independently found the same fabrication defect** in `_deciding_sub_match_rule`, one by
reasoning from the ideal picture, the other by measuring `python -c` under
`undecidable_fallback=deny`. Two blind hits on one defect is much stronger evidence than one
confident report.

**What the split bought, specifically:** the architect could not have found the unpinned-value
problem, because it was judging *direction*. The blinded reviewer could not have found that R3's
remaining site is *blocked on R1 rather than wrong*, because it did not know R1 existed. Neither
lens sees the other's finding. A single judge given both remits would have had to hold both, and
the evidence from this ticket is that a reviewer told the goal grades against the goal.

**Cost:** roughly $3 and ten minutes for the blinded pass. Against a step that would otherwise
have closed with a silently-unpinned field and a silent audit-log regression.

**Keep the split.** Revisit only if they agree on several consecutive steps, which would make the
second lens ceremony rather than instrument.

---

## 15. I cannot feel prose bloat either

Arnon noticed the docstrings growing and that it "smelled" before raising it. I wrote most of that
prose and did not notice. Same shape as lesson 12: a quality signal humans get through discomfort
and I do not get at all.

The measured cost is local and concrete: this step ran roughly **50:1 prose to code**, and
`resolve.py:128` documents `fallback_warning` as computed by a function that **no longer exists**,
with the correct description 580 lines below. The module has already demonstrated that it cannot
keep that volume of prose in sync — and I added 200+ more lines of it inches away.

**Arnon's rule:** comments earn their space by carrying what the code cannot — a genuinely complex
algorithm, an edge case, a subtle requirement. Not what is inferable from the code. This is
explicitly NOT "good code needs no comments" ("a young man's pipe dream") — duplicating the
obvious creates confusion and divergence drift.

**The discriminator I will use:** would a competent reader re-derive this by reading the code? If
yes, cut it. Does it record something unrecoverable — a negative result, a rejected alternative
and why, a non-obvious edge case? If yes, keep it.

By that test the `_parse_compound_match_details` docstring (what was tried, why it broke, the
mechanism) is the best thing in the change set, and the `matched_rule` field entry — nine lines
mostly about what it replaced — is the worst. **Autobiography is the failure mode**: prose
explaining why the code is not something else, rather than what it is.

## Structural steps buy little; say so BEFORE the measurement, not after

Arnon, 2026-08-05: *"I actually expect the initial wins to be quite small. When you try to disentangle a messy code base, you typically have to slug through work that buys only little before you get the really big improvements. It's par for the course."*

Correct, and it reframes the flat canary after R3, D4 and D1a as the expected shape of untangling rather than as bad news. I had been scoring it as a disappointment.

**The trap, which is the transferable part.** "Early wins are small" explains a flat acceptance reading equally well whether the step was a necessary prerequisite or simply ineffective. Applied after the fact it is unfalsifiable, and it turns the ticket's only acceptance test into something that can never fail — the same Goodhart failure as targeting a metric, arriving from the opposite direction.

**The fix, adopted: classify each step in advance as STRUCTURAL or CHANGE-COST, and record the classification with the step's prediction.**

- **Structural** — buys separation, layering, or the ability to *measure* something. Predicted flat on the canary. A flat reading confirms the prediction; a moving one is a bonus worth investigating. R3, D4, D1a were all structural, and my prediction 5 (D1a moves the canary) was wrong precisely because I had not drawn this distinction.
- **Change-cost** — its entire justification is a change-cost delta. A flat canary after such a step is a **genuine failure** and must be treated as one, never absorbed into "par for the course". **R1 is the first of these.**

This keeps the expectation true and the instrument falsifiable at the same time. Related: predicates scope work but are not evidence, and metrics are instruments never targets.

## `uv run ruff check .` can report clean FROM CACHE while the tree has an error

Found incidentally during the ruff-configuration investigation, 2026-08-05: two `--no-cache` baselines taken seconds apart disagreed (an `F821` in `session_start.py` appeared, vanished, reappeared) while the cached form reported clean against a tree that genuinely had an error.

**Every acceptance run this session used the cached form.** Standing change: use `uv run ruff check --no-cache .` whenever the result is being relied on as evidence — acceptance gates, before/after comparisons, anything recorded in a report. The cached form is fine for a quick working check.

Same family as the mutation-target trap: an instrument that answers a slightly different question than the one asked, and answers it confidently.

## A lint rule can be structurally incapable of seeing the violation you bought it for

PLC2701 (import-private-name) looked like a natural enforcement mechanism for step R6, which is about cross-module private access. It is not: it fires only on private imports from a module **external to the importing file's package**. Everything under `toolguard/` is internal to `toolguard`, so it cannot ever see an R6 violation — verified by construction on a synthetic tree, then confirmed against the real one (`ruff check --preview --select PLC2701 toolguard/tools/takeover_audit.py` is clean on the exact violation R6 reports).

Enabling it would have produced a permanent green light on a boundary it never inspects. **A rule that reports clean on a violation you already know about is worse than no rule**, because it converts a known gap into apparent coverage.

The general lesson: before adopting an instrument, confirm it fires on a violation you have already found by other means. Same discipline as the mutation gate — an instrument that never fails is a decoration, and the way to find out is to hand it a known positive.
