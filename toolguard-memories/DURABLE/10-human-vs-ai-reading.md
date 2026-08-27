---
title: 10 - Human reading vs AI reading
type: note
permalink: toolguard/durable/10-human-vs-ai-reading
tags:
- TOO-45
- durable
- process
---

# 10 — Human reading and AI reading: do they have different blind spots?

**The claim under test**, Arnon, 2026-08-24, answering an assertion that human review and AI review are both merely "reading" and therefore share their blind spots:

> "A human reading is materially different than an AI reading. They catch completely different things and have different blind spots. The strongest evidence is that all key architectural problems were caught by human reading and were not noticed by AI reading, while AI reading caught many more bugs than I would have anticipated a human reading to catch."

Split into two testable halves:

- **(A)** The key architectural problems were found by Arnon and were **not** found by AI review.
- **(B)** AI review caught **many more** local/mechanical bugs than a human reviewer would plausibly have caught.

**Verdicts up front.**

| | verdict | confidence |
|---|---|---|
| **(A)** as stated — *AI review did not notice architectural problems* | **REFUTED as stated. The weaker version — *the AI review rounds that were actually run did not find architectural problems* — is CONFIRMED, and it is explained by scope, not by capability.** | **high** on the refutation (a primary artifact records eight architectural defects found by AI in already-reviewed committed code); **high** on the weaker version (30 review artifacts, none producing an architectural finding, and most explicitly instructed "not design") |
| **(B)** | **CONFIRMED, with the counterfactual stated as judgement rather than measurement** | **high** that AI review produced 82 gate findings of overwhelmingly local kind across 30 rounds; **moderate** that a human reviewer would not have produced them — there is no human-review arm in this campaign, so the comparison is a judgement, not a measurement |

## THE COMPETITION FRAMING IS NOT DECIDABLE — AND SETTING ONE UP WAS THE WRONG MOVE (Arnon, 2026-08-25)

**Read this before the verdict table above.** Splitting the claim into (A) and (B) and scoring them was a reasonable instinct and an unreachable goal. Arnon:

> *"You tried to make my assertion into a testable proposition. That's fair. But the reality is that it is impossible for you to do so, especially based on the accumulated data in TOO-45… setting up a competition to decide whether my claim is true or not is futile and pointless."*

**His reasons are not about sample size, which is what a "needs more data" hedge would imply. They are about the two readers not being commensurable in the first place:**

- **Humans are biological; AI is mechanical.**
- **Humans learn innately and continuously from experience. AI has a frozen learning phase** and does not learn after it — every session restarts from that frozen state unless a memory harness is built, and *"those only function [well] for short term memory in most cases."*
- **Humans weight long-, medium- and short-term learning against each other instinctively and continuously.** Arnon: *"A human like me has 62 years of learning behind them with constant feedback from the environment every single second."*
- **The training corpus is unclassified.** *"An AI has a learning corpus of trillions of examples — but they are not classified, i.e. bad code examples weigh the same as good code examples."*
- **And the information needed to classify it does not exist in it.** *"In general the outcome of choices made by the examples in the learning corpus are not represented in the learning data, so even if the learning algorithm was to be improved such that it would be able to classify inputs by their short and long term outcomes — for a vast majority of the available data that information is simply not there."*

**That last point is the strongest and it is worth stating as a general principle**, because it bounds more than this document: **code in the corpus carries no outcome label.** Whether a pattern shipped and held for a decade, or shipped and caused an incident, is mostly absent from the data. So "the model has seen a lot of code" does not mean "the model has seen a lot of *consequences*" — and architecture is precisely the discipline whose entire subject matter is long-horizon consequence. A human with decades of feedback is not a better reader of the same kind; **they are reading a different, outcome-labelled corpus that no training set contains.**

**What survives, and it is the part worth keeping.** The verdicts below should be read as findings about **scope, substrate and method** — not as a scoreboard:

1. **AI does markedly better when the scope is large and clearly bounded** — a diff, a file set, an enumerated axis list.
2. **AI does markedly better under a prescribed method than under general guidance.** This is the single most actionable finding in the document and it recurs everywhere in the corpus.
3. **AI is relentless and fast** — Arnon's addition, not previously stated here, and it is a real compensating property: it will run the twelfth axis as carefully as the first, and run it again on forty files, which no human reviewer will do.
4. **Substrate beats reader**: proposals expose architectural error, diffs conceal it. Both readers did better on proposals.

**So the honest one-line answer is not "who wins."** It is: *these are different instruments with different failure modes, and the useful question is what harness makes each one productive.* That is what `13` and `14` were written to answer.

---

**The real finding, and it is not either sub-claim**: the asymmetry in the record is mostly **a scope difference that was chosen, not a blind spot that was discovered**. Every AI reviewer in the campaign was pointed at a diff; seven of them were told in writing *"Not design, not logic, not coverage."* Arnon was the only reader looking at the whole system. When an AI reader **was** pointed at architecture — the architecture-judge back-test — it produced eight architectural defects in code that had already been written, reviewed and committed. That experiment also found the sharper boundary: the same AI judge saw an architectural defect in a **proposal** and missed the identical defect in a **diff**.

---

## What was read

| source | what it gives |
|---|---|
| `TOO-45/proposed-tickets/` — 77 numbered files + index (**76 distinct subjects**) | ticket bodies, most stating how they were found |
| `TOO-45/proposed-tickets/resolved/` — 31 files (**29 distinct subjects**) | the mutation/test-repair batch |
| `TOO-45/resolved/` — 4 files (11, 16, 17, 57) | **the directory a previous analysis missed**; ticket 16 is the single strongest counter-example in this document |
| `TOO-45/reports/review-*.md` — **30 blinded review artifacts** | every gate finding heading, read verbatim; a sample of bodies |
| `TOO-45/reports/architecture-judge-backtest.md` + ticket 32 | the one AI reading exercise scoped to architecture |
| `TOO-45/reports/corrections-analysis.md` and `review-conclusions.md` | Arnon's corrections and his own conclusions |
| `DURABLE/06`, `07`, `09`, `intermediate/defect-taxonomy.md` | prior classifications, **checked against primaries, not trusted** |

**One prior figure verified.** `05-campaign-statistics.md` and `defect-taxonomy.md` both attribute **14 of 76** primary tickets to *"Arnon asking a question, reviewing, or instructing"* and name them: 06, 07, 09, 38, 44, 45, 85, 98, 99, 103, 104, 105, 106, 108. I re-read the head of each. **13 of 14 open with a verbatim Arnon quote or an explicit "you asked for this"** — 06 does not, and the taxonomy already flags that (*"06 was found by the agent … and only its deferral was Arnon's"*). So the 14 is really **13 confirmed + 1 mis-assigned**, and the taxonomy says so itself. **MEASURED.**

**One figure corrected.** The taxonomy's count excludes `resolved/`. Sweeping both resolved directories for the same attribution language adds exactly one more Arnon-originated subject: **ticket 16** (*"found by Arnon at the manual review of punch-list #10, 2026-08-09"*). Nothing in `proposed-tickets/resolved/` — the 2026-08-13 mutation batch — is Arnon-originated; every one of those files opens with *"Found 2026-08-13"* and a RED test. **So the corrected count is 14 of 105 distinct subjects (13.3%), not 14 of 76 (18%).** **MEASURED.**

---

## Classification 1 — the findings attributable to Arnon

Taxonomy: **ARCH** = a structure, boundary, layering, coupling, abstraction, or measurement-design problem. **LOCAL** = a bug in a function, a wrong literal, a missed call site, a bad test. **PROCESS** = how work is conducted. A finding can be ARCH+LOCAL when a local symptom is filed with its structural cause.

| # | subject | class | attribution, verbatim |
|---|---|---|---|
| 38 | prose-parsing anti-pattern still live one level below where it was fixed | **ARCH** | *"Found 2026-08-13, from Arnon's question: 'could `reason` distinguish a real deny from a fail-closed one?'"* |
| 44 | ambient state read at point of use, so every read site is a mock point (485 patches, zero autospec) | **ARCH** | *"Written 2026-08-13 in answer to Arnon's question: does the code's structure make mocking harder and more error-prone than it needs to be?"* |
| 45 | detecting inert mocks | **ARCH** (instrument design) | *"Written 2026-08-13 in answer to Arnon's second question: should every module that mocks carry a test verifying the mock actually works?"* … *"This is Arnon's idea in its strongest form"* |
| 85 | consolidate every external-contract structure into one module | **ARCH** (boundary) | *"Filed 2026-08-20 at Arnon's instruction. 'Make a ticket to consolidate all structures related to external contract into this new module…'"* |
| 98 | `_statement_bounds_containing` is a hand-rolled parser | **ARCH** (violates the project's own single-parser constraint) | *"Raised by Arnon, 2026-08-21, reviewing commit `2e53d429`: 'multiline.py `_statement_bounds_containing()` is a hand-rolled parser. This needs serious justification. I don't like it at all.'"* |
| 99 | the contract module is constants, not a boundary | **ARCH** (boundary) | *"'`claude_code_contract.py` is basically only constants. I am not sure that this is the right organization… `create_hook_output()` … seems like a semantic seam…'"* |
| 103 | `compound.py` is hard to follow; a doc would postpone the question | **ARCH** (abstraction) | *"'compound.py became a bit hard to read and understand. At the root - it solves a rather convoluted problem…'"* |
| 104 | repeated literal strings are really under-modelling; dicts are undeclared types | **ARCH** (data modelling) | *"'There are repeated literal strings that should have been constants… But the problem is probably deeper'"* |
| 105 | `_strip_comments` compensates for the extractor | **ARCH** | *"'`_strip_comments()` is another hand-rolled parser… But why do we need it in the first place?'"* |
| 106 | `CommandUnit` splits one concept into two fields by a reporting property | **ARCH** (one structure, two questions) | *"Filed 2026-08-22 at Arnon's request… 'create #106 describing the proposed fix (which you chose not to propose). I'll review it and decide.'"* |
| 108 | reading a hook event belongs to the contract, and should take a source | **ARCH** (boundary + testability) | *"'hook.parse_hook_input() looks like part of the contract. Also, it uses sys.stdin directly, which is less testable.'"* |
| 09 | write `docs/architecture-as-built.md` | **PROCESS** (architecture documentation) | *"you asked for this — 'a new human-consumable well documented code architecture document.'"* |
| 07 | doc-comment and comment cleanup sweep | **PROCESS** | *"you asked for this explicitly — 'a dedicated sweep after the next commit to specifically clean up doc comments across the board.'"* |
| 16 | `ToolSpec` describes built-ins only, so governing any other tool silently denies it | **LOCAL + ARCH** | *"found by Arnon at the manual review of punch-list #10, 2026-08-09"* |
| *(06)* | *git rm the measurement tools, or justify keeping them* | *not Arnon-originated* | taxonomy's own correction: *"06 was found by the agent … only its deferral was Arnon's"* |

**Counts (MEASURED, over the 14 confirmed):** **ARCH 11 · PROCESS 2 · LOCAL 1** (ticket 16, which carries an architectural root as well).

**Judged, not measured:** the ARCH/PROCESS boundary on 09 and 07 is my call. 09 asks for an architecture document, which is architecture work but not an architectural *defect*; 07 asks for a comment sweep, which is quality work. Reclassifying both as ARCH moves the count to 13/14 and does not change any verdict.

### Arnon findings that never became tickets but changed a conclusion

These matter for (A) because they are the "reading" that reversed a direction rather than opening a file.

| what | class | verbatim |
|---|---|---|
| refuted ticket 82's whole premise | **INSTRUMENT / premise** | *"Arnon challenged the premise and was right. 'You are talking specifically about the native syntax rule. That is simply how claude works, no? What does the claude documentation say?'"* — `sudo`/`env` turned out to be **faithful** native behaviour; the taxonomy lists 82 as the campaign's one refuted ticket |
| reframed ticket 15 from damage to defect | **ARCH** | *"First I titled this '`migrate()` has no cross-process lock'. That named the damage, not the defect. Arnon: 'I am not sure why you label this as a migrate issue.'"* |
| killed a precondition on ticket 24 | **LOCAL** | *"PRECONDITION CHECKED 2026-08-13, after Arnon asked 'what newline in `additionalContext`? Those are not allowed in the first place.'"* |
| corrected ticket 48's threat framing as overstated | **PROCESS** | *"Correction, Arnon 2026-08-13: I first wrote this up as a shared-machine test-integrity hole. That framing was overstated."* |
| settled ticket 17 by fetching the spec | **PROCESS / claim** | *"CLARIFICATION 2026-08-13, from Arnon's question 'does native syntax even support an end-anchored rule like `*id_rsa`?'"* |
| reframed ticket 107's criterion | **ARCH** | *"REFRAMED 2026-08-23 (Arnon) — the criterion is the PACKAGE BOUNDARY, not correctness"* |
| reframed the whole cost analysis | **INSTRUMENT** | *"When I ask for statistics I care about meaningful summary stats, not for long tables that do not help to make decisions."* (`09-verification-mechanisms.md` §6) |

**The category structure here is the substantive result on the human side.** Arnon's findings are almost entirely about **what a thing is for** — whether a module is a boundary or a bag, whether a field carries one fact or two, whether a name describes the damage or the defect, whether a measurement answers the question asked. **Confidence: high** — 11 of 14 tickets and 4 of 7 non-ticket corrections carry that shape, and the quotes are verbatim.

---

## Classification 2 — the AI blinded review rounds

**Population, verified two ways.** `09-verification-mechanisms.md` re-counted the census independently and reconciles: 27 `review-<n>-round<k>.md` files across 8 tickets (18, 39, 44, 74, 77, 78, 79, 80), plus 3 unnumbered artifacts = **30**; blocking findings 78 + 2 redrift + 2 grammar mediums = **82**, matching `06-planning-attribution.md`'s independent population exactly. I re-derived the per-round heading counts from the files and land in the same place (±2 on rounds whose headings use prose rather than `B<n>` labels). **MEASURED.**

**All 27 numbered rounds report at least one blocking finding. Zero clean rounds.** Of 30 artifacts, 28 FAIL and 2 PASS.

### What the findings are, on the architectural-vs-local axis

I classified afresh from the finding headings, spot-checking bodies. Representative headings, verbatim:

- *"`split_default_body` now corrupts the `**/<component>/**` shape, and its new docstring's agreement claim is false for it"* (18 r1 B2)
- *"`hard_deny.deny -> hard_deny.allow` still writes, and flips the runtime decision to `allow`"* (39 r1 B1)
- *"a `RED:` annotation on a test that is green, describing a defect that does not exist"* (74 r1 B1)
- *"`~<name>` is expanded to `$HOME`, not to the named account's home"* (78 r2 B1)
- *"A `deny` -- and an unoverridable `hard_deny` -- inside a substitution is downgraded to `ask`"* (79 r1 B1)
- *"`tools/architecture_fitness.py:3` -- 'five modes', fourteen lines above 'Six modes'"* (80 r1 B1)

| class | my count | share | basis |
|---|---|---|---|
| **LOCAL** — a false claim in a comment/docstring/doc, a logic regression in the diff, a test that does not discriminate, a missed spelling, a crash | **~76** | ~93% | heading classification of all 82 |
| **INSTRUMENT-DESIGN** — the granularity or opt-out structure of a *checker* is wrong | **4** | 5% | 80 r2 B1 (*"Ownership stated per module, where it is per (module, member)"*), 39 r2 B3 (*"Both placement checks are silently opt-out via `expected_patterns=None`"*), and two grammar `M1`s |
| **ARCHITECTURAL** — a structure, boundary or design-rule problem in production code | **1–2** | 1–2% | see below |
| style | 1 | 1% | |

**Independent corroboration on a different axis, which is the strongest thing in this section.** `09-verification-mechanisms.md` classified the same 82 findings with a free hand and produced four classes: **CLAIM 52 (63%), COMPOSITION 13 (16%), SILENT 12 (15%), INSTRUMENT 4 (5%), style 1 (1%)**. A classifier with no stake in this question, given 82 findings and free choice of buckets, **did not need an "architecture" bucket at all.** That is stronger evidence than my own re-classification, because it was not looking for this result. **MEASURED, high confidence.**

### The architectural findings the blinded rounds did produce

There are one or two, and they are worth naming precisely because they are the counter-examples.

**1. Ticket 79 round 2, B2, third consequence — verbatim:**

> *"The outer summary is built by re-parsing the inner summary's prose."*

`06-planning-attribution.md` classifies this (J4) as a design-rule violation, not an instance bug:

> *"the design decision to render a reason string and later split it on `\" -> \"` was made against an explicit, project-authored prohibition on exactly that"* — the *prose is output, not a data structure* rule, itself written **from this project's** 813-of-975 under-logging measurement.

**This is an AI blinded reviewer catching a violation of an architectural rule, in a diff, unprompted.** It is buried as the third bullet under a blocking finding whose headline is a local claim defect (*"the unit's reason and the audit log now name a rule that did not decide"*) — which is itself informative about how such findings surface in a diff-scoped round: as a sub-consequence of a local symptom, never as the headline.

**2. Ticket 44 round 6, blocking 1 — verbatim heading:**

> *"BLOCKING -- false assertion: 'One read point per fact' (`toolguard/ambient.py:1-12`)"*, refuted by *"two shipped call sites the repo's own tests already document"* (06 C8).

Whether this counts is a judgement. It is filed as a false-claim finding, and its subject is an architectural property (was the consolidation actually complete?). I count it as **borderline** and would not build an argument on it.

**Judged, moderate confidence:** the honest number of clearly-architectural findings out of 82 blinded-round findings is **one**.

### What the rounds were told to look at — this is the crux

Seven of the thirty artifacts carry an explicit scope exclusion. Verbatim, from four separate rounds:

> *"Scope: comments, docstrings and user-facing message strings only … **Not design, not logic, not test coverage.**"* (80 r1)

> *"Narrow scope: comments, docstrings and user-facing message strings only. **Not logic, not design, not coverage.**"* (44 r4, 44 r5)

> *"Scope: comments, docstrings and user-facing message strings only, in the uncommitted change against `20e4964` … **Not design, not logic, not test coverage.**"* (77 r1)

Every remaining round is scoped by a `git diff` file list. Not one of the thirty is scoped to the system, to a layer map, or to a module boundary. `09` states the consequence plainly: the mechanism *"misses, structurally, what its own scoping excludes: a prose-only round cannot find a logic defect, by instruction."* The same sentence applies with equal force to design.

**So the weaker version of (A) is confirmed and is nearly a tautology.** AI review did not find architectural problems in the campaign's blinded rounds, and the campaign's blinded rounds were, in seven cases explicitly and in the remaining twenty-three by construction, not looking for them.

---

## The architecture-judge back-test — and the context this document stripped off it

**CORRECTED 2026-08-25. The earlier heading called this "the decisive counter-example" and presented the result as evidence that AI reading finds architectural defects. That is the result with its history removed, and the history is the finding.** Arnon:

> *"Your example of the agent being able to find architectural issues is taken out of its real context. **We spent weeks with the agent failing badly in any architectural assessment**, and when let loose it still does not follow architectural guidance as well as it should and needs the architectural separate review. The architectural review that started working is the result of numerous experiments — **most of them failed.** What helped to get there is creating a focused task (just architecture — nothing else), creating clearer criteria, judge blinding, and some other ingredients."*

**So the claim this experiment supports is much narrower than "AI can find architectural defects."** It is: *a purpose-built, single-task, blinded judge, given a pre-registered axis list and pointed at a proposal, found eight live defects.* **Every qualifier in that sentence was bought with a failed experiment**, and the unqualified version — an ordinary agent, or a general reviewer, assessing architecture — is what failed for weeks.

**The back-test's own text says the same thing and this document quoted around it.** Its hypothesis is explicitly about attention, not capability: *"a judge whose only task is architecture will weight the architecture training data more heavily than a coder or a general reviewer does, because **the dominant causes of the weakness are attention dilution and task focus rather than capability.**"* And its verdict: *"**It did not find them by being cleverer — it found them by having nothing else to do.**"* A weakness that needs a dedicated harness to work around is a weakness, not a capability.

**Two further things that were true and omitted here:**

- **The control arm was never run.** The back-test's own limitation 4: *"Comparing against the general `/code-review` reports for the same five commits is the direct test of 'focused beats general' and remains to be done."* So even the focused-beats-general claim is untested against its control.
- **Conformance is a separate problem from detection, and it did not improve.** Arnon's *"when let loose it still does not follow architectural guidance as well as it should"* is corroborated by the near-miss recorded in the same report: the #10 spec instructed the coder to destroy an independent test oracle, and *"**the coder's silent non-compliance is the only thing that saved it. No review caught it.**"* Finding defects and not creating them are different capabilities; this campaign improved the first.

**Both consequences are now written up as their own artifacts, because they are what is reusable here:** `13-architectural-reviewer-construction.md` (how to build the reviewer, including what failed) and `14-architectural-conformance-patterns.md` (how to get a subagent to conform in the first place).

The experiment itself is a primary artifact (`TOO-45/reports/architecture-judge-backtest.md`, 2026-08-10, promoted to ticket 32).

**Design**: eight blind judges, one architecture-only brief, one subject each. Arm A = five committed punch-list diffs. Arm B = three pre-implementation specs. Scoring key pre-registered.

**Result, verbatim from ticket 32:**

> *"**Two are marked 'fix before push' and have been sitting in a working queue since 2026-08-10.** … What makes this set different from the #07 tickets: **every item is in code that was already written, reviewed and committed** as part of this ticket's own punch-list. The back-test was run to see what a judge would find in work believed finished."*

The eight defects are architectural by any reasonable definition. Verbatim, abbreviated:

1. *"`migrate()` discards the structured decline reason, and `auto_migrate` then states a false cause … **This is the project's own prose-is-output rule, one level up from where TOO-45 removed it.**"*
2. *"**Dynamic dispatch hides a call edge from the repo's own semantic tooling** … Directly contrary to Arnon's stated principle that what static analysis cannot see, a reader cannot either. … **test mechanics driving production indirection.**"*
3. *"`hook.py` builds the Reporter and keeps four hand-rolled `log_error`/`log_warning` calls … **The mechanism's own owner is the largest remaining instance of the problem it was built to remove.**"*
4. *"**`once_per` re-introduced an invisible upward runtime edge** … an observability module executes config-layer code at runtime with no import edge. `--layers` reports clean. Same class as the cycle #03 removed."*
5. *"**`is_builtin` conflates structural description with enforcement policy**"* — this is *one structure, two questions*, the campaign's signature architectural shape, found by an AI.
6. *"**`TOOLS_BY_NAME` is a live mutable public dict; its derived frozensets are import-time snapshots** … so [tests] exercise a state production can never be in."*
7. *"**The golden verdict corpus is structurally blind to payload-key changes** … a *sixth* hardcoded copy of the tool→key map"* — an instrument-design defect in the campaign's own oracle.
8. *"`hook.COMMAND_TOOLS` is dead code"* — the one local item in the set.

**And the judges beat the human on depth on at least one item, stated by the report itself:**

> *"**Judges beat the artefacts they judged.** B2 named the concrete mechanism (`auto_migrate` collapsing declined into failed, wrong remediation text, burned day-claim) **where the original human catch was a one-line prompt to look.**"*

**This refutes (A) as stated.** `09-verification-mechanisms.md` reaches the same conclusion about a near-identical claim already in circulation:

> *"A related claim in wide circulation should NOT be carried forward. 'Every architectural error caught on this ticket was caught by a human asking a direct question — none by any metric, blinded agent, or automated test' is sourced **only to auto-memory, never to a primary artifact**, and the architecture-judge back-test contradicts it by finding **eight live defects in already-reviewed, already-shipped code.**"*

### But the same experiment draws the real boundary, and it is not "human vs AI"

The back-test's pre-registered ground truth is the sharpest result in this whole document:

| id | subject | result |
|---|---|---|
| T3 | B3 — the **#10 spec** — closed registry cannot describe a user-declared MCP tool | **hit** |
| T4 | A5 — the **#10 commit** — *same defect, still present in committed code* | **miss** |

Verbatim:

> *"**2 of 4 — and both hits are in arm B.** T4 is literally T3 in a different substrate and was missed there, which is the sharpest structural result of the exercise: **the judge sees architectural defects in proposals and not in diffs.** That matches where Arnon caught all of his — from proposals, never from reading merged code."*

**The dividing line the evidence actually supports is substrate, not reader.** A proposal states intent, so a boundary error is a sentence you can disagree with. A diff states edits, so the same error is distributed across changed lines and reads as normal. Both readers in this campaign performed better on the first substrate. **Confidence: moderate** — n = 4 on the back-test's ground truth, which the report itself labels *"n = 4 positives. Establishes existence, not a rate."*

**One tension in the record, stated rather than resolved.** The back-test says Arnon caught his findings *"from proposals, never from reading merged code."* `corrections-analysis.md` says the heaviest architectural objections — the `permission_resolution ↔ resolve` cycle, the `rule_entry` phantom edge, the `log_writer` layering — arrived at turns 357–359 while reading *change sets*. Both are primary; they disagree on whether Arnon's architectural finds came from proposals or from small diffs. What they agree on is the size of the artifact. **Unresolved. Flagged.**

---

## Scope limit vs blind spot — the analysis the question turns on

**A blind spot** is a defect a reader was pointed at and did not see. **A scope limit** is a defect the reader was told not to look at, or was handed an artifact that does not contain it.

| observation | blind spot or scope limit? | evidence |
|---|---|---|
| 30 blinded rounds, ~1 architectural finding | **Scope limit, dominantly** | 7 rounds say *"Not design"* in writing; the other 23 are scoped to a `git diff` file list. No round was given a layer map, a module inventory, or the system |
| An AI reader pointed at architecture found 8 architectural defects in reviewed, committed code | **Refutes a capability blind spot** | back-test, ticket 32 |
| The same AI judge hit T3 (proposal) and missed T4 (the identical defect in a diff) | **A genuine, measured limit — and it is about substrate, not about being an AI** | back-test ground truth, n=4 |
| `Path.absolute()` escaped **six** rounds; `expanduser` four; `resolve` five | **Blind spot, and a shared one** | `09`: *"This is not 'six lazy reviews' — the technique that found `absolute` appears nowhere in the corpus beforehand"* |
| Arnon's heaviest architectural objections arrived late, after *"seven directed report agents, a blind reviewer, `pyscn`, `ruff`, and 2,600 passing tests"* | **Scope/attention limit that applies to BOTH readers** | see below |

**The attention finding is the one that should survive this document, and it is not about humans or models.** `corrections-analysis.md`, primary, Arnon's own words at turn 374:

> *"Now that changes are fewer files I start noticing things. Even things that are not from this change set."*

and the analysis's conclusion:

> *"Those defects were present the whole time. They had survived seven directed report agents, a blind reviewer, `pyscn`, `ruff`, and 2,600 passing tests. What changed was not the code but the size of the diff in front of a human. … **the reviewer's detection rate is a function of change-set size, and below some threshold it collapses to near zero.** A large change set is not merely harder to review; it is reviewed *ineffectively while appearing to be reviewed.* Every one of those reviews reported success."*

`09-verification-mechanisms.md` draws the correct inference and I endorse it: *"That is a statement about attention, not about humans; it applies to whatever is doing the attending."*

**So my judgement on the split, stated as judgement:** of the asymmetry the claim points at, roughly **three quarters is scope and one quarter is a real difference in what the two readers attend to**. Basis: 30 of 30 AI artifacts were diff-scoped and 7 were explicitly design-excluded (that is the scope share); the residual is the T3/T4 substrate result and the shape difference in Classification 1 (Arnon's findings are about *what a thing is for*; the AI rounds' findings are about *whether a statement is true*). **Confidence: low-to-moderate on the fraction** — it is a considered split of a population that was never designed to separate the two causes. **What would change it**: run one blinded review round with an architecture-only brief on a diff the campaign already reviewed, and see whether it finds anything the round missed. That is a cheap experiment and nobody ran it. The back-test's own declared limitation names the same gap: *"The control arm was not run."*

---

## Testing (B) — did AI review catch more local bugs than a human plausibly would?

**Measured side.** 30 rounds, 82 gate findings, zero clean rounds, ~93% local by my classification and 94% non-instrument/non-style by `09`'s independent one. Beyond the gate findings, three defects `06` singles out:

> *"The three most serious defects found anywhere in these thirty rounds (79 r1's `hard_deny`→`ask` downgrade, 78 r2's `~name` fail-open, 18 r2's `hard_deny` carve-out widening) were all found by differential measurement, and all three were **silent**: green suites, clean replays, no warnings."*

And a fourth, from 78 round 5, verbatim: *"`dd if=~/.ssh/id_rsa` walks past an absolute deny rule … and returning `PRIVATE-KEY-MATERIAL`"* — which also caught an `ask→allow` loosening *round 4's own repair had just introduced*.

**Why a human plausibly would not have caught these — judgement, with its basis.** `06` measures that **39% of gate findings (32 of 82) were execution-only**: *"reachable by no amount of reading — they were found by differential execution against `HEAD`, by running real `bash`, by building rejected grammar variants and measuring them, or by driving the real hook subprocess."* `09` names the economics: *"an agent reviewer will run a differential for the price of a round, and a human reviewer usually will not."* A human reviewer given 30 diffs would not build 30 HEAD-vs-working-tree harnesses, and Arnon's own budget was **196 of 61,946 tool calls (0.3%)**, with 68.9h of prompt-wait measured across the campaign.

**Where (B) is weaker than it sounds.** A large share of the AI yield is not "bugs a human would have missed" but **bugs the AI pipeline itself created**:

> *"a large share of review yield is defects the *repair* created"* — and ticket 79's post-mortem: *"**Eleven agent runs, four review rounds, and three security weakenings** — each introduced by the fix for the previous one."*

`08-autonomous-loops-vs-human-in-the-loop.md`'s framing correction from Arnon applies directly: this campaign was *"structured intentionally as dominated by autonomous agent loop delivery,"* with an error and retraction rate *"far higher than in human in the loop and closer to poorly managed, junior human teams."* **A human-in-the-loop run would have generated fewer of these defects for the AI reviewer to find.** So (B) is true as an observation about this campaign's record and partially self-inflicted as a comparison.

**And the prose rounds are the weakest part of the AI yield.** `06`, measured: **20 of 82 (24%) were preventable by a step costing under a minute** — a grep, opening one named file, counting a constant's references. Its cleanest instance: *"ticket 74 round 2's only blocking finding cost ~1h05m / ~\$9–12 and was three change-history paragraphs added to test docstrings in the same commit as a sweep deleting nine of them under a rule the project had written down verbatim."* A human reading that same diff would plausibly have caught several of the 20.

**Verdict on (B): CONFIRMED for the execution-derived and composition findings — the ~39% that no reading of any kind reaches — and NOT ESTABLISHED for the claim-class findings, where 24% were a grep away and a human might well have caught them.** Confidence: **high** on the measured half, **moderate** on the counterfactual, because **there is no human-review arm anywhere in this campaign.** That is the single biggest limit on (B).

---

## Blind-spot map — stated as what this evidence shows, not as a generalisation

**What Arnon's reading caught that the AI rounds did not:**

- **Whether a module is a boundary or a bag of names** (99: *"basically only constants… `create_hook_output()` … seems like a semantic seam"*). The AI implemented ticket 85 through the full pipeline and left the crossing functions where they were; 99 records this as *"a gap in ticket 85's execution, not a new requirement."*
- **Whether one field carries one fact or two** (106, and the smell behind 97).
- **Whether a mechanism should exist at all** (105: *"But why do we need it in the first place?"*; 98: *"This needs serious justification. I don't like it at all."*).
- **Whether the title names the damage or the defect** (15).
- **Whether the premise of a whole ticket is true** (82, the campaign's one refuted ticket, refuted by a question).
- **Whether a measurement answers the question that was asked** (the cost-analysis reframing).

**What the AI rounds caught that Arnon's reading did not:**

- **Silent security regressions introduced by the repair of the previous round** — three named, all with green suites and clean replays.
- **Differential behaviour against HEAD**, e.g. 18 r1's six-row old-vs-new table showing a "dead branch removal" was a semantic narrowing of deny reach.
- **Shell-oracle findings** — `dd if=~/.ssh/id_rsa` returning `PRIVATE-KEY-MATERIAL` past a deny rule.
- **Falsity of claims in comments, docstrings and documentation, at volume** — 52 of 82 findings, verified by execution rather than by reading.
- **Tests that do not discriminate the change they were written for** (79 r1 B5: *"1 of 3, not 3 of 3"*).

**What neither caught** — worth stating because it undercuts a clean two-column story:

- `Path.absolute()` escaped six review rounds *and* was not raised by Arnon; it was found by **enumerating pathlib's surface**. `expanduser` escaped four; `resolve` five. `09`: *"anything reachable only by a route nobody enumerated."*
- The near-miss in the back-test: an instruction that would have destroyed an independent test oracle *"was never carried out — the coder silently declined, and nothing in review caught it. So the safeguard held by luck rather than by process."*
- `09`, on the human mechanism: *"what he demonstrably does not catch is the silent security class — none of the three was found by a question."*

---

## Counter-examples, both directions

**Against (A) — architectural problems AI reading did catch:**

1. **The architecture-judge back-test's eight defects in committed, already-reviewed code** (ticket 32). Strongest available. Includes a layering violation (*"an invisible upward runtime edge … `--layers` reports clean"*) and a one-structure-two-questions defect (*"`is_builtin` conflates structural description with enforcement policy"*). **Caveat, declared by the report itself**: *"One-sided blinding. The judges were blind; the axis list was not — three of twelve axes map onto known defects."* And *"n = 4 positives. Establishes existence, not a rate."*

2. **Ticket 97 — `unit.kind` answers two questions.** *"Found 2026-08-21 while diagnosing why ticket 79 was the campaign's worst surprise."* The defect taxonomy attributes 97 to **"static analysis / code reading alone"**, i.e. an agent, not Arnon. Arnon's own approval is the sharpest sentence in the corpus on this question:

   > *"This 'kind' naming bothered me before and I expressed this to you. What I didn't catch at the time is this confounding, which validates the 'smell'"*

   **The human had the smell and not the mechanism; the AI had the mechanism.** This is a direct counter-example to "completely different things", because it is the *same* finding reached from two sides — and the ticket's own framing (*"That is this campaign's founding shape, arriving for the fifth time"*) makes it an architectural finding by an AI reader.

3. **Ticket 79 round 2 B2**, third consequence — a blinded diff reviewer naming a *prose is output, not a data structure* violation unprompted.

**Against (B) — a local defect only Arnon caught, and it is a serious one:**

**Ticket 16**, `07-escaped-defects.md`'s tier-1 case C1, which that document calls *"the strongest case in the corpus"*:

> ```
> Bash                  -> allow   Command matches allow pattern: ls*
> WebFetch              -> deny    No command provided in tool input
> mcp__acme__fetch_doc  -> deny    No command provided in tool input
> ```
>
> **"Governing such a tool does not restrict it — it bricks it."**

And the mechanism, verbatim:

> *"Punch-list #10 converted the file-path reads and left the command read as a literal — **the same half-converted dispatch its own review flagged in two other files, present in the hook itself and missed by everyone.**"*

**The AI review found the class, named it precisely** (*"worse than no conversion, because it looks finished"*), **fixed two of three instances, and stopped one file short — in the file that governs.** The third was *"found by Arnon by hand the same day."* This is not a subtle architectural insight; it is a missed call site. It is the cleanest evidence in the corpus that the two readers fail differently rather than one being uniformly better: the AI review had the concept and lost the enumeration; the human had neither the concept nor a tool, and found the instance by running the thing and reading three lines of output.

Two more, weaker:

- **Ticket 24's precondition** — killed by *"what newline in `additionalContext`? Those are not allowed in the first place."* A factual point about the external contract that a diff reviewer had no reason to question.
- **Ticket 82** — a whole ticket refuted by one question about the documentation, after the false premise had *"survived two blinded review rounds"* (`.claude/rules/native-fidelity-claims.md`, on the sibling ticket 77 case). Note the rule's own explanation, which is a scope statement and not a capability one: *"A blinded review **cannot** catch an error here. Reviewers check prose against *this repository's* code, and native's behaviour is not in this repository."*

---

## What the evidence cannot settle

1. **There is no human-review arm.** Nobody ran a human reading of the same diffs the 30 AI rounds read. Every claim about what a human "would have caught" — including half of (B) — is counterfactual. This is the single largest gap and it is cheap to close: hand Arnon one already-reviewed diff cold and count.

2. **The AI arm was never given the human's scope.** No blinded round was pointed at the system. The back-test is the only architecture-scoped AI reading in the campaign, it ran once, on n=4 ground truth, with one-sided blinding, and *"the control arm was not run."* Until it is, "AI reading does not find architectural problems" is untested for the configuration the claim is about.

3. **Silent successes leave no trace.** `corrections-analysis.md` states its own limit: *"explicit approvals are recoverable and silent successes are not — an absence of correction leaves no trace."* We can count what Arnon corrected. We cannot count what he read and correctly passed, so his precision is unmeasurable.

4. **Round files are missing.** `06`: *"ticket 44's rounds 1–3, ticket 78's round 1 headline count, and ticket 80's rounds 1–2 headline counts have no surviving files"*, and *"an agent that found nothing may simply have left no file."* The 82 is a floor over surviving evidence, biased toward rounds that found something.

5. **The two primaries disagree about where Arnon's architectural finds came from** — proposals (back-test) or small diffs (corrections-analysis, turns 357–359). Nobody has reconciled them, and the answer changes what the substrate finding means.

6. **The campaign's autonomy shape contaminates the comparison.** Arnon, 2026-08-24, on the whole corpus: this was *"structured intentionally as dominated by autonomous agent loop delivery,"* not his normal human-in-the-loop pattern. A meaningful share of what AI review caught, AI implementation had created.

---

## The one-line answer

**The claim's conclusion is right and its stated reason is wrong.** Human reading and AI reading did catch different things in this campaign — the shapes in Classification 1 and Classification 2 barely overlap, and that part is measured. But the record does **not** show that AI reading fails to notice architectural problems; it shows that **every AI reader in the campaign was pointed at a diff and seven were told in writing not to look at design**, while the one AI reading that *was* pointed at architecture found eight architectural defects in code that had already passed review. The durable finding underneath both is neither about humans nor about models: **detection rate is a function of the size and the kind of the artifact in front of the reader, and a reader looking at too much reports success.**

---

# THE EXPERIMENT THIS DOCUMENT ASKED FOR — run 2026-08-24

This document's own "what would change my mind" said: *"run one blinded review round with an architecture-only brief on a diff the campaign already reviewed, and see whether it finds anything the round missed. That is a cheap experiment and nobody ran it."*

**It has now been run.** A fresh agent, blind to this analysis and to the original review rounds, was given commit **`3bb21b7`** ("remove the compound/resolve runtime cycle", 24,099 lines — one of the six commits that are 75% of the campaign) with an **architecture-only** brief: module boundaries, layering, coupling, one-structure-two-questions, leaky abstractions, untestable seams. Local bugs, tests, style and documentation were declared out of scope. It was told explicitly that a clean report was a valid result and that manufacturing findings was worse than silence.

## Result: 7 findings on an already-reviewed diff

The three most falsifiable were **independently verified at HEAD** by the coordinator:

| # | finding | verified? |
|---|---|---|
| 5 | The three new Protocols were written to be *"a structural contract pyright actually checks"* — but `pyrightconfig.json` sets **`"typeCheckingMode": "off"`**, there is no CI, and no test references them. A declaration nothing reads. | **CONFIRMED** |
| 2 | Production now imports the **private** `_combine_strictest` from `compound` (`resolve.py:22`), converting a public-API dependency into a private-name one in the decision path. R6 cannot see it because both modules are in the `engine` layer. | **CONFIRMED** |
| 1 | Two independent pipeline drivers exist and **have already diverged** on `fallback_kind` derivation (text heuristic vs structural); ~40 tests pin the one with **no production callers**. | **CONFIRMED** — the only non-test call is from `check_compound_permission`, which itself has none |

Four further findings were not independently verified, and the judgement-heavy ones should be read as the agent's opinion: **#4** flags `audits_as_one` as one boolean answering two questions (audit granularity *and* conflict-log eligibility) — **the same shape recorded in auto-memory as having previously downgraded an unoverridable `hard_deny` to `ask` with a green suite**, found here unprompted; **#3** finds the prose-parse antipattern surviving on the deny path because `RuntimeVerdict` never grew a `fallback_kind` field; **#6** argues `config_types` is becoming a junk drawer holding engine vocabulary in the config layer; **#7** notes `judge_unit`'s positional invariant is checked only by length.

It also recorded a "Not findings" section — five things it examined and declined to flag, including endorsing the cycle removal itself.

## What this settles, and what it does not

**It supports the scope-limit reading strongly.** An AI reader pointed at architecture, on a diff 30 previous rounds had access to, produced specific, measured, largely-true architectural findings. The near-absence of such findings in those 30 rounds is therefore **not** evidence that the reader cannot see architecture.

**It is in tension with Arnon's recollection that reviewers were "asked and repeatedly produced poor results."** Both can be true — the back-test scored 2 of 4 on pre-registered ground truth while this run scored 3 of 3 on spot-checks — but they are not the same kind of asking, and the difference may be the whole lesson: **this brief named the defect classes to look for and pointed at a declared layer map (`.pyscn.toml`); the back-test asked for judgement against pre-registered axes.** Conformance to a declared intent is the thing this system does well; forming the intent is not.

**Limits, stated plainly.** **n = 1.** The commit was chosen *because* it is architectural, which favours the agent. Only 3 of 7 findings were verified. And whether any of them is worth acting on is a judgement the experiment does not make. **This establishes existence, not a rate** — the same limitation the back-test declared about itself.
