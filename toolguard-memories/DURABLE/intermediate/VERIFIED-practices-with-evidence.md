---
title: VERIFIED-practices-with-evidence
type: note
permalink: toolguard/durable/intermediate/verified-practices-with-evidence
---

# Verification of `practices-with-evidence.md`

Verified 2026-08-23 by an agent that did not write the target, per `DURABLE/VERIFICATION-PROTOCOL.md`. Stance: try to refute; default to REFUTED or UNVERIFIABLE when uncertain.

**Claims checked: 176**, enumerated in the table below. Verdicts: **140 CONFIRMED, 7 REFUTED, 6 MISATTRIBUTED, 20 TRUE BUT MISLEADING, 3 UNVERIFIABLE.**

**Read in full**: the target (303 lines); `VERIFICATION-PROTOCOL.md`; `TOO-45/reports/review-conclusions.md`; `TOO-45/reports/canary-results.md`; `TOO-45/reports/architecture-judge-backtest.md`; `TOO-45/reports/retrospective.md` §§4.1-4.7, 5.1-5.5, 6.1, 9.6; `TOO-45/reports/review-44-round4.md`; `TOO-45/reports/PRODUCTION-ONLY-SCORING.md`; `TOO-45/measurements/79-cost-assessment.md`; `implementation/TOO-45 ticket 101 bare-brace grammar fix - coder implementation report.md`; `TOO-45/TOO-45 ruff configuration proposal.md` (PLC2701 reconciliation and the rejected list); the header and verdict block of all 35 `TOO-45/reports/review-*.md` files. **Sampled by targeted grep**: everything else under `toolguard-memories/`. **Delegated to two read-only sub-verifiers**: the numeric claims of §5 and of §§1.2/1.4/3. Their four strongest findings (twelve-vs-thirty files, 29-mutations, nine-vs-fifteen stages, PLC2701) I re-verified myself against the primary sources before recording them here. **Cross-checked against the repo, not only the notes**: `git log --oneline master..too-45` (78 commits), `git show` on four Item-98 and Item-101 commits, and `pyproject.toml`.

---

## Lead: the seven failures that matter

### 1. REFUTED — §1.8: "Ticket 101 ... stood down mid-task with zero net change shipped"

**Git says it shipped.** `03d922c` (2026-08-22 16:02) — *"TOO-45 Item 101 - a bare {} is a word, and brace groups still decompose"* — lands the grammar fix (`unquoted_word` admits `{}` while `{`/`}` stay in `delimiter`), and adds `test/unit/test_deny_penetrates_constructs.py`, a new regression suite covering a denied command in all 17 supported constructs.

What stood down was **one coder run**, not the ticket. `implementation/TOO-45 ticket 101 bare-brace grammar fix - coder implementation report.md:11` reads *"Status: STOOD DOWN mid-task at the coordinator's explicit instruction. No net changes shipped"* — and step 7 records that the coder *"had independently converged on the same narrower fix they specify"*, which is exactly the fix the commit contains.

This is the sister document's failure mode reproduced: an outcome derived from what a note says, contradicted by what the repo did. The consequence is not cosmetic — the target offers "zero net change shipped" as **the cost** of the two-phase practice's phase-2 limits. The real cost was one aborted agent run inside a ticket that landed a correct fix and a new test file the same day.

### 2. REFUTED — §1.4: "Across roughly thirty files" — the source says **twelve**

Target: *"Across roughly thirty files, **every falsehood an editor newly introduced was a claim about what a mechanism guarantees**"*, cited to `TOO-45/TOO-45 punch-list 07 work queue.md`.

That file, line 308: *"Across **twelve files**, *every* falsehood an editor newly introduced was a claim about what a mechanism **guarantees** — never about what it does."*

"roughly 30 files" exists in exactly one place — `TOO-45/reports/transferable-practices-evidence.md:79` — where it is presented **inside quotation marks as a quote of the work queue**. The dossier misquoted its own source by 2.5x; the target inherited the inflated number while citing the file that contradicts it. A universal ("every falsehood") over twelve files is a different claim from the same universal over thirty.

### 3. REFUTED — §5.6: PLC2701 was **not** adopted; it was considered and rejected

Target: *"PLC2701 was **adopted as the enforcement mechanism** for a step entirely about cross-module private access"*, filed under §5 "Tried and did not work".

`TOO-45/TOO-45 ruff configuration proposal.md:157`: *"so PLC2701 is **rejected outright**"*; its measurement table marks it **REJECT**; it appears under the heading *"Considered and rejected"*. `TOO-45/TOO-45 lessons.md:366`: *"PLC2701 (import-private-name) **looked like a natural** enforcement mechanism for step R6 ... **It is not**."*

And the repo settles it: `pyproject.toml:41-45` ships the rejection as a comment — *"Considered and REJECTED, so nobody re-litigates them from scratch: PLC2701 -- ... A rule that is green on a known violation is worse than no rule."*

The lesson the target draws is correct and is quoted almost verbatim from the shipped file. Its **placement is inverted**: this is the same shape as §5.4 ("killed before use, and that is the success"), a rule handed a known positive and dropped before adoption. Filed as "tried and did not work" it teaches a process failure that did not occur.

### 4. REFUTED — §5.11: "Fifteen stages left uncommitted" — the primary says **nine**

`TOO-45/TOO-45 decision log.md:1141`, contemporaneous: *"**Nine stages** of verified-green work sit **uncommitted**, so when R1e half-failed there was no clean rollback point."*

"Fifteen" is §5.1's guard-canary figure (*"quoted as a safety result after every step for fifteen stages"*). The contamination did not start here — `retrospective.md:329` already titles the section *"5.5 Fifteen stages left uncommitted"* while its body says only "D1a through R1d" — but the target reproduces the heading number without checking the decision log one link down the chain. This is the transitive-citation failure the protocol asks to be flagged, with the unmeasured link identified.

Two riders: **"four earlier stages" appears in no source** (both sources say "D1a through R1d" and give no count, and four does not reconcile with nine); and the source's **point-in-time** framing (the working tree at the moment R1e half-failed) is lost, so a reader of a flat sentence about a 78-commit branch will take it as an end-state fact.

### 5. REFUTED — §1.2: "a blinded reviewer ran 29 mutations and **6 survived**"

`implementation/TOO-45 R3 second review-fix coder task recall.md:12`: *"A BLINDED reviewer ran 29 mutations against R3's FINAL state ... **5 new findings**, all defects introduced by R3 itself."* The "**6 mutations survive**" at line 21 is scoped to **finding #1 alone** (the unpinned production wiring), not to the battery.

The target's own sentence gives it away: *"29 mutations and 6 survived, **both gaps** then fixed and re-verified"* — six cannot be both. The implementation report verifies exactly two mutations against the acceptance criterion and says the other four were *"not independently re-verified by hand"*.

### 6. REFUTED — §2.2: "ticket 79 is also the campaign's **most expensive item**"

The corpus retracts this in terms. `TOO-45/TOO-45-punch-list-2026-08-20.md:311`, under a heading reading *"THE CORRECTION THAT MATTERS — I have been costing tickets in the wrong currency"*:

> *"I described 79 as **"the most expensive item of the campaign"** on the strength of 11 agent runs and ~3M subagent tokens. By wall-clock it was **4h15m — below the phase-3 average, and less than half of ticket 78.** ... So "expensive" meaning "many agent runs" is a metric about me, not about him, and I have been reporting it as though it were his cost."*

**The same contradiction bites a second claim.** §1.3's *"Ticket 18 cost ~11 hours"* is well sourced (`surprise/18-scored.md:61` and five other places), but the wall-clock table immediately above that correction (`punch-list-2026-08-20.md:295`) lists **item 18 at 4h15m**. The corpus keeps two incompatible cost currencies — agent runs and tokens on one side, wall-clock on the other — and the target quotes whichever is larger without naming which currency it is in. Any future use of these figures should state the unit.

The target quotes the pre-correction sentence from `RESULTS-LOG.md:192` and carries none of the correction — then builds on it: *"Recall is therefore not independent of cost — it is a leading indicator of it"* and *"the cheapest early warning in this entire corpus."* If the cost ranking is wrong, the correlation that rests on it (n=1) is not evidence of anything. **78 is the real wall-clock outlier at 8h51m**, and the same correction names *why* it was expensive: rounds chasing findings with zero field occurrence.

### 7. REFUTED — §2.2: "Scored line-weighted **production** recall ... 100% (74, 22, 85a) down to **15.2%** (79)"

Two instruments, one label. `TOO-45/reports/surprise/PRODUCTION-ONLY-SCORING.md` is the production-only recomputation, and on it:

- 79 scores **13.8%**, not 15.2% (*"79: 15.2% -> 13.8%. Slightly *worse*"*).
- **Five** items score 100% — 22, 74, 77, 78, 85 — not the three the target lists.

15.2% and the three-item 100% list are the **all-files** column. The target labels an all-files range as production recall, and the mislabelling matters in the direction of its own argument: the production cut is the figure that file recommends reporting, and under it the headline number is worse and the top of the range is saturated (*"A measure that saturates on a third of its cases is discriminating less, not more"*).

---

## Second tier: misattribution and misleading framing

### 8. MISATTRIBUTED — §1.9: "roughly half of review yield is defects the *repair* created ... **Independently measured twice**"

Neither cited source is a measurement of a proportion of review yield.

- **Source (a)**, `punch-list 07 work queue.md:352`: *"Reviews are catching about as many defects the editor newly wrote as ones it carried through."* It sits under a heading that says "measured", and no count follows — six file names, no numerator, no denominator. It is about a **prose-comment sweep**, not about security code review. And it is **the same sentence the target already uses in §1.4**, so it is not independent of the document's own other section.
- **Source (b)**, ticket 79: *"three security weakenings — each introduced by the fix for the previous one."* Three is a count, not a ratio; nothing in it says "half" of anything.

"Roughly half", "measured", and "twice, from opposite ends of the campaign" are all the document's own construction over one qualitative sentence and one count of three. The underlying phenomenon is real and well evidenced. The **quantification** is not.

Rider: the "Concretely," examples that follow the ticket-79 quote are drawn from **tickets 78 and 39**, not 79, and read as if they instantiate 79's three weakenings.

### 9. MISATTRIBUTED — §6: "The surprise-factor protocol's own closing admission"

The protocol document does not close with it. `TOO-45/reports/surprise-factor-protocol.md` ends on the Q1/Q2 split and the per-item record; its only nearby line (193) is the weaker *"Manual review is the control that works for architectural error ... Bugs, by contrast, *are* being caught by process improvements."*

The chain is: auto-memory (`feedback_stop_at_first_working_boundary`) → `TOO-45 session resume.md:70` → `architecture-sweep-practices.md:67`, which is where the "surprise-factor protocol's own closing admission" characterisation is added → the target. Ticket 85 carries an independent version, so the claim is not fabricated — but the attribution to the protocol's closing is not, and **the target's own §7 lists this claim as sourceable only to auto-memory and says it "should not be carried forward."** §6 then presents it as one of two "well-supported statements ... both should survive."

### 10. MISATTRIBUTED — §3: the runtime-census numbers are cited to a section that does not contain them

*"3 of 7 'verdict types' ... `SubMatch` is constructed 8,314 times"* and *"`config` and `resolve` ... called each other 46,481 times"* are cited to `retrospective.md` §9.6. §9.6 contains neither number. Primaries: `TOO-45/TOO-45 decision log.md:1019` and `TOO-45/reports/architecture-sweep-practices.md:23`. Both numbers re-measure exactly; only the pointer is wrong — which is precisely the "real filename attached to the wrong claim" shape the protocol exists for.

### 11. MISATTRIBUTED — §1.2: "2,314 tests stayed green" cited to `TOO-45 lessons.md` §13

§13 does not contain it. It is at `retrospective.md:211` and `TOO-45 decision log.md:731`. Two separate measurements (the 2,300-green mutation and the 2,314-green swap) are merged under one citation.

### 12. MISATTRIBUTED — §4.2: the ticket-98-chunk-2 row cites `DURABLE/01-...`

A sibling summary, not a primary artifact — and one that is itself inside the verification scope. Transitive citation into an unverified document. The primary for that measurement was not located in this pass.

### 13. TRUE BUT MISLEADING — §1.6 carries a number §7 disqualifies

§1.6's cost line: *"The whole #07 sweep: 158 files, ~9,100 lines of prose removed, two days, **roughly 90 agents**."*

§7: *"**"roughly 90 agents"** for the #07 sweep — never cross-checked against a batch count"*, under a heading saying anything listed *"should not be carried forward."*

Same document, two pages apart. The 158 files and ~9,100 lines both re-measure (`transferable-practices-evidence.md:15`); the agent count is the one figure in that line the document has already condemned, and it is the one a reader will quote when pricing a sweep. Same defect for §6 and §7 (finding 9).

### 14. TRUE BUT MISLEADING — §1.8: the two `.peg` PASSes were not clean passes

The section's headline is *"zero clean passes in ~24 code-and-prose review rounds — and the only two PASSes in the entire corpus are the two `.peg`-only reviews"*, and the section is titled around the gate holding.

`review-77-grammar-phase1.md` is a **PASS that raised four findings**, including M1 at line 112: *"`$(...)` in an assignment value, and `$(...)` as the command word, **both defeat the ticket's purpose**; a verified grammar fix exists and belongs in phase 1"* — with *"Decision needed, and it needs to be made now, not in phase 2."* Plus L1, L2, L3. A **second** phase-1 round (`review-77-grammar-phase1-delta.md`) was needed, and its own PASS says *"all four M1 bypasses are now recognised."*

So the two-phase gate's evidence is: a first phase-1 artifact that passed the mechanical checks while leaving four bypasses open, caught by the reviewer's judgement — not by the byte-diff the section credits. That is a *better* story about reviewing, and a weaker one about "no judgement required".

### 15. TRUE BUT MISLEADING — §1.8: the census does not reproduce

I enumerated every `TOO-45/reports/review-*.md`: **35 files**, of which 4 are coder repair/fix reports and 1 is `review-conclusions.md`, leaving **30 review rounds**. Verdicts: **2 PASS** (both `.peg`), **27 explicit FAIL**, 1 with no verdict line but two false-assertion findings (`review-44-round4.md`). So the non-peg count is **28**, not "~24", and the corpus is **30**, not "~26".

The claim's *direction* is confirmed and in fact understated. The census itself does not reproduce, and "~26 genuine review rounds" is presented as a count someone performed.

### 16. TRUE BUT MISLEADING — §1.6: "The `test/` tier — **86 files** ... produced zero product-code defects"

Two numbers spliced. **86** is `git diff --stat test/`'s changed-file count (`work queue.md:25`); the tier is **88 files**. The zero-product-defect measurement was taken **mid-sweep at 62 of 88 files**, and the evidence dossier flags exactly this at line 101: *"that figure was mid-sweep at 62-of-88 files done ... ~78 is the denominator ticket 31 uses for the assertions-that-cannot-fail count, **not necessarily 'all files examined for product defects'**."*

The conclusion survives (no filed ticket traces to the test tier), but the target attaches a hedged mid-sweep zero to a file count from a different instrument and drops the hedge.

### 17. TRUE BUT MISLEADING — §4.2: "blind exactly where it mattered, **four measured times**" over a **six-row** table

The source of "four" is `follow-up-queue.md:83` (*"the corpus's blind spots now number four"*). The table lists six. Either the count or the table is wrong, and a reader will quote the count.

### 18. TRUE BUT MISLEADING — §4.2: "**three instances** of a green row that is green for the wrong reason"

At least four are in the record: the corpus-replay blind spot, the isolation-instrument symmetric null, the `find`-rule case (`surprise/88-scored.md:39`), **and** `surprise/105-scored.md:34` / `DURABLE/01-...` §1 (*"the parse succeeded" read as "the parse was correct"*). Auto-memory records four. The class is real; the count is an undercount, and it is presented as "the campaign named this as a class — three instances."

### 19. TRUE BUT MISLEADING — §5.3: "a low blast radius is not low **safety**"

`retrospective.md:317`: *"a low blast radius is not low **risk**."* `retrospective.md:369` (the do-not-assume table): *"A low blast radius indicates safety | `subagent`'s move broke 1 test — meaning nothing was there to catch a mistake."*

As written, "not low safety" says the opposite of the explanation that follows it. A compression that inverted the claim — the exact failure the campaign's own comment standard names (*"compression adds quantifiers"*, and here, negations).

### 20. TRUE BUT MISLEADING — §5.8: "the layer map's **own correctness** masked 16 stderr writes"

`canary-results.md:62`: *"It was clean because **the map encoded the wrong boundary**."* The general sentence the target quotes (*"a map that matches the code always shows zero violations"*) is verbatim and correct; the diagnosis of *this* incident is inverted from the source's.

### 21. TRUE BUT MISLEADING — §5.9 promotes a narrowly-scoped null into a standing rule

The quote is faithful and the retrospective scopes it to four named artifacts (decision log, lessons, scoping traces, ruff proposal). Elsewhere in the same corpus, pyright and code-review-graph **did** contribute findings: `surprise/95-scored.md:40` (a pyright "not accessed" warning that found `_resolve_leaf` called by ~30 tests and no production code); `architecture-judge-backtest.md:40`, defect A3, evidenced by *"pyright's `incomingCalls` and `callers_of` both see zero"* and escalated to **fix-before-push** in `follow-up-queue.md:78`; `resolution-seam-protocols-report.md:114` (the pyright loop *"found two real, unrelated pre-existing bugs"*). The target repeats the scoped null and then bolds a general rule the wider record weakens.

### 22. TRUE BUT MISLEADING — the `[LOG]` qualifier is transmitted selectively

The retrospective marks contemporaneous-log figures `[LOG]` and lists several under *"Taken from the decision log and **not independently re-verified**"* (`retrospective.md:738`), including the 106-vs-0 rename result and the three drifted exception lists. The target **applies** the caveat in §2.1 (*"These figures are `[LOG]` in the retrospective's own labelling"*) and **drops** it in §5.3, §5.7 and §5.10, where the source marks it identically. Selective transmission makes the un-caveated ones read as re-measured.

### 23. TRUE BUT MISLEADING — §5.3 omits the counter-example in the same paragraph

The source pairs `subagent` (rename 684 / move 1) with `error_log` (**rename 798 / actual move damage 2,357**) and says the numbers are *"contaminated in **both** directions."* The target keeps only the direction that supports "rename-and-count overstates", making a two-directional contamination look like a one-directional bias.

### 24. TRUE BUT MISLEADING — §2.2's "cheapest early warning in this entire corpus"

Everything the corpus says about this measure at the aggregate is more hedged than the target: `open-questions.md:27` — *"As a predictor the measure is **weak and heavily confounded**"* (by ticket leak, design leak, and scope impurity); `phase 3 resume.md:347` — *"Low recall **may** be a leading indicator of cost — **test at the aggregate**"*; and the target's own §2.2 records that the leak-level law was **retracted at 7 points**. Item 79 is also the *lowest-leak* item in the series, so its low recall is the shape the retracted law would have predicted from leak alone. n=1, confounded, unhedged.

### 25. TRUE BUT MISLEADING — §4.1 drops the back-test's declared limitation

*"8 blinded judges, ground truth pre-registered"* is exact. `architecture-judge-backtest.md:64` declares: *"**One-sided blinding.** The judges were blind; the axis list was not — three of twelve axes map onto known defects ... A clean replication needs axes chosen by someone who has not seen the corrections."* The 2-of-4 hit rate is steered by design, by the source's own account. (The proposals-vs-diffs asymmetry survives, since both arms shared the axes — which is why the target's narrowed recommendation still holds.)

### 26. TRUE BUT MISLEADING — smaller dropped qualifiers

- **§5.4**: *"Head to head at 3 locations against 8"* drops the source's condition *"with leaks held equal at exactly one"* (`micro-canary-protocol.md:185`), the thing that makes the comparison meaningful. One citation covers wording from three files.
- **§1.2**: *"Roughly fifty production defect tickets ... from mutations alone"* drops `transferable-practices-evidence.md:61`'s record that the figure is *"a floor, not a ceiling"* and that only 1 of its 3 supporting batches was independently verified.
- **§1.4**: calibration *"took 4-5"* drops *"4-5 editor passes, **4 reviews each**"* (`work queue.md:385`), roughly halving the stated calibration cost — in a sentence whose job is to price the practice.
- **§1.1**: the cost sentence is quoted with quotation marks but is trimmed mid-sentence (source: *"Call it a few hundred dollars ... and **understand that** most of the spend..."*), and a third data point (~10 min / ~$3 for a blinded review pass) is dropped.
- **§1.3**: *"Two **independent** runs of consecutive counting"* — both are the same coordinator's self-observation in the same running note, `phase 3 resume.md:158` and `:209`.
- **preamble**: the co-change indictment (71 → 134) drops §3.3's qualifier that under **per-commit** grouping the same change moved 39 → 42, and that the source attributes the distortion to a 7x sample-size loss from ticket grouping.

---

## Systematic gap: cost is mostly unsourced, and the document knows it

The brief for this verification asked whether each practice's cost is sourced. It largely is not.

| practice | cost line | status |
|---|---|---|
| 1.1 execute the claim | ~100k tok/round; ~27min/$2.25; ~40min/$4-6 | **sourced**, quote trimmed (finding 26) |
| 1.2 mutation | ~161k tok/repair agent, range 142-197k, n=12 | **sourced, exact** |
| 1.3 tell the subagent to verify | none — "cheapest item" | asserted |
| 1.4 second review pass | 2-3 passes + 2 reviews per file | **sourced**, calibration halved (finding 26) |
| 1.5 blind implementation | "two implementations per requirement, n=4" | **not a cost** — no time, no tokens |
| 1.6 exhaustive sweep | 158 files / 9,100 lines / two days / ~90 agents | files+lines sourced; agents disqualified by §7 |
| 1.7 forbid the fix | **no cost line** | — |
| 1.8 two-phase | **no cost line**; the one cost offered (ticket 101) is refuted | — |
| 1.9 review to exhaustion | round counts only | rounds are not cost |
| 2.1 fix the instrument first | *"No cost was recorded for any of the four"* | **honest** |
| 2.2 pre-register | none | — |
| 2.3 scoping traces | *"none of the three traces records its own wall-clock or token cost"* | **honest** |
| 4.1 two judges | ~$3 and ten minutes for the blinded pass | **sourced, exact** |
| 4.2 golden corpus | none | — |
| 4.3 blind comparison as scoring | none | — |

**Three of fifteen carry a re-measurable cost.** Two more state honestly that no cost was recorded. The rest recommend a practice with no price attached — and the document itself names the reason in §2.3: *"none of the three traces records its own wall-clock or token cost, so the return on investment is qualitative."* That admission applies far more widely than the section it sits in.

Rider on §2.3: the source says *"Used on D1, R1, R5 and R2"* (four) in the same paragraph as *"none of the **three** traces"*. The target faithfully carries both. The inconsistency is the source's, not the target's — but the "four steps" figure should not be quoted as though it were counted.

---

## Full claim-by-claim table

Verdict key per the protocol. **C** = confirmed, **R** = refuted, **M** = misattributed, **TM** = true but misleading, **U** = unverifiable.

| # | § | claim | verdict | note |
|---|---|---|---|---|
| 1 | pre | co-change 71 → 134 fully-coupled pairs, one 23-file ticket | **TM** | numbers exact (`retrospective.md:77`, `:102`); per-commit grouping (39 → 42) and the sample-size cause dropped |
| 2 | pre | direction / acceptance / diagnosis are three jobs | C | §9.1-9.6, labelled as a conclusion |
| 3 | 1.1 | comment sweep filed 16 defect tickets it was not looking for | C | dossier reconciles 17 total minus ticket 32 (judge back-test) = 16 |
| 4 | 1.1 | 4 of the first 6 open with near-identical sentences by different agents | C | dossier §B |
| 5 | 1.1 | 7,623 pattern/command pairs | C | verbatim in 4 places incl. `resolved/17-...md:63` |
| 6 | 1.1 | 416 mismatches across 46 patterns, all false negatives | C | verbatim |
| 7 | 1.1 | all on patterns not ending in `*`; docs recommend that shape | C | verbatim |
| 8 | 1.1 | 15 existing tests pass with the branch rebound to the wrong impl | C | verbatim |
| 9 | 1.1 | reading found "one minor redundancy"; mutation found 13 of 25 at zero detection | C | `in-process-mutation-testing.md:33` |
| 10 | 1.1 | on another module reading found nothing, mutation found five | C | same line |
| 11 | 1.1 | "execution is king" = 13 occurrences, most recurrent theme | C | `corrections-analysis.md:80` |
| 12 | 1.1 | across 210 human turns | C | `corrections-corpus.md:15`; note ~80 carry human content |
| 13 | 1.1 | cost: ~100k tok/round, five rounds, ~27min/$2.25, ~40min/$4-6 | **TM** | numbers exact; quote trimmed mid-sentence, third data point dropped |
| 14 | 1.1 | when not worth doing: cheap-to-re-derive prose, concurrency claims, "spend it deleting" | C | stated in source, as claimed |
| 15 | 1.2 | two of five seeded mutations MISSED; each hit one of two implementations | C | `lessons.md:115` |
| 16 | 1.2 | after unification the identical mutation flipped MISSED → CAUGHT | C | `retrospective.md:209` |
| 17 | 1.2 | removing all escaping → 16 failures; the actual fix → 0 | C | dossier §E |
| 18 | 1.2 | wrong-value mutation left all 2,300 tests green; `None` failed 2 | C | `lessons.md:264` |
| 19 | 1.2 | swapping `matched_rule`/`provenance` → 2,314 tests green | **M** | true; not in the cited `lessons.md` §13 — it is `retrospective.md:211` |
| 20 | 1.2 | survival 47% (14/30), 55% (23/42), 58% over 81 mutants | C | `in-process-mutation-testing.md:29` |
| 21 | 1.2 | ~fifty production defect tickets from mutations alone | **TM** | verbatim, but "a floor, not a ceiling" and 1-of-3 batch verification dropped |
| 22 | 1.2 | the mechanism a module is named for was its least-tested part | C | verbatim |
| 23 | 1.2 | item 95: 4 mutations, 30 / 20 / exactly 1 / exactly 1 | C | implementation report, incl. the revert method |
| 24 | 1.2 | "Every mutation was caught by an existing test..." | C | verbatim |
| 25 | 1.2 | R3: blinded reviewer ran 29 mutations, 6 survived | **R** | 29 mutations → **5 findings**; "6 survive" is finding #1 only; only 2 re-verified |
| 26 | 1.2 | R3 first review-fix: `matched_rule=matched_pattern` passed all tests | C | implementation report |
| 27 | 1.2 | cost ~161k tokens/repair agent, 142-197k, n=12 | C | exact, two sources |
| 28 | 1.2 | four contradictory mutations failed the identical single test | C | verbatim |
| 29 | 1.2 | worst instance: 34 zero-detection mutants sharing one signature | C | verbatim |
| 30 | 1.2 | "the same failing set ... is a *worse* signal than zero failures" | C | verbatim |
| 31 | 1.2 | crash-logger finding: 9 failures, 3 in the hook's own test file | C | source says "errors"; the mechanism (OSError vs `assertRaises`) matches |
| 32 | 1.3 | briefs carried a false claim at a steady rate — roughly thirty corrections | C | `campaign resume 2026-08-13.md:144`; never enumerated anywhere (see #90) |
| 33 | 1.3 | "four consecutive, all caught by the agent, none by me" | C | `phase 3 resume.md:158`, verbatim |
| 34 | 1.3 | "seven consecutive, every one caught by the agent" | C | `phase 3 resume.md:209`, verbatim |
| 35 | 1.3 | "two independent runs of consecutive counting" | **TM** | same coordinator, same running note, two moments |
| 36 | 1.3 | fifteen-plus briefs contained mistakes editors caught; two reached tickets | C | dossier §G — and correctly uses fifteen-plus, not §7's disqualified "17" |
| 37 | 1.3 | "A report is a session delta; a review measures HEAD" | C | verbatim |
| 38 | 1.3 | three negative controls ("Nothing in the brief was false" ×3) | C | all three located verbatim in the named reports |
| 39 | 1.3 | ticket 98 chunk 3 — `mining.py` "the one real consumer" refuted by grep | C | `98-chunk3-scored.md:25` |
| 40 | 1.3 | ticket 74 — "already a RED test"; coder got `Ran 4 tests in 0.001s / OK` | C | implementation report:39 |
| 41 | 1.3 | ticket 19 — brief's *fix shape* wrong; caught via corpus replay | C | located |
| 42 | 1.3 | review-18 round 6 — "correct change, wrong description" | C | `review-18-round6.md:31`, verbatim |
| 43 | 1.3 | ticket 18 cost ~11 hours; ticket 74 cost one command | **TM** | "~11h" is well sourced (`surprise/18-scored.md:61` and five other places) but the wall-clock table at `punch-list-2026-08-20.md:295` lists item **18 at 4h15m** — the same table whose next paragraph re-prices ticket 79. The corpus contradicts itself on cost currency and the target picks the larger figure without saying so |
| 44 | 1.4 | "Reviews are catching about as many defects the editor newly wrote..." | C | `work queue.md:352`, verbatim |
| 45 | 1.4 | four files: newly-written defects on three, headline refuted on the fourth | C | `work queue.md:470` |
| 46 | 1.4 | "Across roughly thirty files, every falsehood ... guarantees" | **R** | source says **twelve** (`work queue.md:308`); 30 is a dossier misquote |
| 47 | 1.4 | findings per round 14, 14, 7, 4, 0 and 12+, 3, 4 | C | `verifying-claims-finds-bugs.md:95`, verbatim |
| 48 | 1.4 | only a round returning nothing is a reliable finish line | C | source |
| 49 | 1.4 | cost: 2-3 editor passes + 2 reviews + delta check; calibration 4-5 | **TM** | steady state exact; calibration drops "4 reviews each" |
| 50 | 1.5 | four requirements, both trees, blinded implementers | C | `canary-results.md` |
| 51 | 1.5 | four for four surfaced a pre-existing product defect | C | verbatim, all four named and matching |
| 52 | 1.5 | file-tools list found by both implementers, only by grepping literal tuples | C | verbatim |
| 53 | 1.5 | code already read by 7 report agents, 1 blind reviewer, pyscn, ruff, 2,586 tests | C | verbatim |
| 54 | 1.5 | Arnon: "a well-understood way to conduct a fishing expedition" | C | `review-conclusions.md`, verbatim |
| 55 | 1.5 | Arnon: uniquely practical with agents, too labour-intensive manually | C | verbatim |
| 56 | 1.5 | cost: two implementations per requirement, n=4 | **U** | not a cost; no time or token figure exists |
| 57 | 1.6 | five-rule over-match found via an advisory analyzer's docstring | C | `transferable-practices.md` |
| 58 | 1.6 | heaviest architectural objections arrived at turns 357-359 | C | `corrections-analysis.md:28` |
| 59 | 1.6 | Arnon: "Now that changes are fewer files I start noticing things" | C | verbatim (turn 374) |
| 60 | 1.6 | detection rate collapses "above some threshold" | C | source says "below some threshold"; the target's wording is the coherent one |
| 61 | 1.6 | cost: 158 files, ~9,100 lines, two days, roughly 90 agents | **TM** | files/lines exact; "~90 agents" is disqualified by the document's own §7 |
| 62 | 1.6 | test tier: 86 files, largest tier, zero product-code defects | **TM** | 86 = diff-stat; tier is 88; the zero was measured mid-sweep at 62 of 88 |
| 63 | 1.6 | its yield was ~65 unfailable assertions, ~50 undetected mechanisms | C | ticket 31 |
| 64 | 1.7 | two scope rules; both converted silent fixes into written findings | C | dossier §C.4, §H |
| 65 | 1.7 | five editors independently refused to launder a false Given/Then | C | verbatim |
| 66 | 1.7 | "prohibiting the fix increases the yield" | C | verbatim |
| 67 | 1.7 | largest findings sat for days in a 2,200-line file; "functioned as a burial" | C | `work queue.md:53-55`, verbatim |
| 68 | 1.8 | census: ~26 genuine rounds, zero clean passes in ~24 | **TM** | actual: 30 rounds, 2 PASS, 28 non-peg — direction confirmed, census does not reproduce |
| 69 | 1.8 | the only two PASSes are the two `.peg`-only reviews | C | enumerated all 35 files; true |
| 70 | 1.8 | ...and the gate therefore held with no judgement required | **TM** | the first PASS raised M1 (four bypasses, "defeat the ticket's purpose") plus L1-L3 |
| 71 | 1.8 | regenerated with canopy, diffed against the committed parser — 0 lines | C | verbatim |
| 72 | 1.8 | 23,594 distinct commands, `differing=0`, parse failures 506 → 506 | C | verbatim, `review-77-grammar-phase1.md:37` |
| 73 | 1.8 | delta review built the rejected variant: 0 differences over 28,770 + 88 adversarial | C | verbatim, `-delta.md:18` |
| 74 | 1.8 | parse failures 4349 → 4349 | C | verbatim |
| 75 | 1.8 | reports record correctly deciding the procedure did not apply (19; statement_bounds) | C | `19-prereg.md:34`; no Item-98 commit touches the `.peg` (checked 4 commits) |
| 76 | 1.8 | ticket 101: 19 unexpected failures; `{ ls; }` → `['{ ls', '}']`; "a real deny-bypass" | C | implementation report:47, verbatim |
| 77 | 1.8 | "the ticket stood down mid-task with zero net change shipped" | **R** | `03d922c` shipped Item 101 the same day; the coder run stood down, not the ticket |
| 78 | 1.9 | round counts: 18→6, 78→5, 79→4, 39 and 80→3 | C | enumerated the files; exact |
| 79 | 1.9 | ticket 18 blocking per round: 2, 2, 1, 3, 3, 2 | C | read all six verdict lines; exact |
| 80 | 1.9 | review-78 r5: `bash -c 'dd if=~/.ssh/id_rsa'` past an absolute deny rule | C | B1, verbatim |
| 81 | 1.9 | review-18 r6: `[regex]\bcurl\b` parsing to `\x08curl\x08` | C | located |
| 82 | 1.9 | "roughly half of review yield is defects the repair created", measured twice | **M** | neither source is a proportion; one is the document's own §1.4 sentence |
| 83 | 1.9 | r5 caught an ask→allow loosening r4's repair introduced on `echo hi >~/notes.txt` | C | round 4 B1 → redirect-glued repair → round 5 B2 → reverted; chain confirmed |
| 84 | 1.9 | punch-list 39 r4 caught a `ConfigWriteVerificationError` regression | C | located |
| 85 | 1.9 | ...offered as "concretely" instantiating **ticket 79's** three weakenings | **TM** | both examples are tickets 78 and 39 |
| 86 | 1.9 | review-74 r1: five blocking findings, zero code defects | C | verbatim |
| 87 | 1.9 | ticket 19's round curve measures coordinator error, not difficulty | C | verbatim |
| 88 | 2.1 | four instrument fixes (R5a-0, R2-0, R1b, R1b2); three deleted more than they created | C | `retrospective.md:52`, verbatim |
| 89 | 2.1 | R5's cycle detector had no out-of-scope filter; a ~34-test stage was never a violation | C | §4.1, verbatim |
| 90 | 2.1 | these figures are `[LOG]`; no cost recorded for any of the four | C | honest and correct |
| 91 | 2.1 | ten instrument defects; defect 6 disclosed by the agent that did it | C | §5.1 table + note, verbatim |
| 92 | 2.2 | five predictions before D1a: two won, three lost; the losses were informative | C | §4.5 |
| 93 | 2.2 | canary predictions: 3 of 4 directionally right; the most confident right for the wrong reason | C | `canary-results.md` |
| 94 | 2.2 | R1 pre-registered against a metric bounded below at ~7 | C | §5.2, verbatim |
| 95 | 2.2 | Goodhart: estimator narrowed 25 predictions to 12, "hedging is what precision scoring punishes" | C | `RESULTS-LOG.md:295`, verbatim |
| 96 | 2.2 | `|A|/|P|` inverted against recall wherever both were computed, and was dropped | C | protocol |
| 97 | 2.2 | two of seven items' justifications measurably wrong (16 vs 8 call sites; 4 vs 3+1 sets) | C | located |
| 98 | 2.2 | production recall ranged 100% (74, 22, 85a) down to 15.2% (79) | **R** | production-only: 100% for five items, floor **13.8%**; 15.2% is the all-files figure |
| 99 | 2.2 | ticket 79 the campaign's most expensive item | **R** | retracted at `punch-list-2026-08-20.md:311`: 4h15m, below average, half of 78 |
| 100 | 2.2 | "11 agent runs, ~3M subagent tokens" | **U** | the only cost *measurement* is 7 runs / ~1.8M (`measurements/79-cost-assessment.md`); ~3M is an estimate |
| 101 | 2.2 | "Recall ... is a leading indicator of cost" / "cheapest early warning in this corpus" | **TM** | n=1, on a cost ranking that is refuted; sources hedge to "may be" and "weak and heavily confounded" |
| 102 | 2.2 | predictions leaked twice through the same guard; "An instruction is not a mechanism" | C | `RESULTS-LOG.md:172`, verbatim |
| 103 | 2.2 | measure-before-briefing leaked into five tickets | C | located |
| 104 | 2.2 | protocol steps silently skipped on two tickets | C | located |
| 105 | 2.2 | three of four early scorings taken from a working tree; item 04 hid a real alarm | C | located |
| 106 | 2.2 | the leak-level law was explicitly retracted at 7 points | C | `RESULTS-LOG.md:338`, verbatim |
| 107 | 2.3 | traces used on four steps; changed the plan every time; twice deleted more work | C | §4.1, verbatim ("D1, R1, R5, R2") |
| 108 | 2.3 | R1's "free deletion" broke 10 tests; R2 gained a second and third instance | C | verbatim |
| 109 | 2.3 | drift guard: 3,996 lookups under replay, fired 0 times | C | located |
| 110 | 2.3 | `subagent` rename damage 684, move damage 1 | C | verbatim |
| 111 | 2.3 | "none of the three traces records its own wall-clock or token cost" | C | verbatim — note the source's own four-vs-three inconsistency |
| 112 | 2.3 | the byte-copy/sha256/`git status` discipline, and one near-miss | C | located |
| 113 | 3 | diagnostic probes: most findings per unit cost, least planned for | C | §9.6, verbatim |
| 114 | 3 | 3 of 7 verdict types never constructed; `SubMatch` 8,314 times | **M** | numbers exact (`decision log:1019`); §9.6 does not contain them |
| 115 | 3 | `config`/`resolve`: zero import edges, 46,481 calls over a 6,401-case replay | **M** | verbatim in `architecture-sweep-practices.md:23`; §9.6 does not contain it |
| 116 | 3 | structure said isolated leaves (fan-in 2); history said one module in three files | C | `retrospective.md:552` |
| 117 | 4.1 | on R3 the two judges disagreed and the blinded one was right | C | §4.3 |
| 118 | 4.1 | "the two lenses overlapped on almost nothing" on D1a | C | verbatim |
| 119 | 4.1 | ~$3 and ten minutes for the blinded pass | C | verbatim |
| 120 | 4.1 | "the split happened by accident before it was designed"; designed split untested | C | verbatim |
| 121 | 4.1 | back-test: 8 blinded judges, ground truth pre-registered | **TM** | exact — but the source declares the axis list was *not* blind (3 of 12 map to known defects) |
| 122 | 4.1 | 2 of 4 known defects found, both hits in the proposals arm | C | verbatim |
| 123 | 4.1 | the one defect in both a proposal and its diff: caught in the proposal, missed in the diff | C | T3 hit / T4 miss, verbatim |
| 124 | 4.1 | eight live defects in already-shipped code; flat on 8 of 12 axes | C | verbatim |
| 125 | 4.1 | the near-miss the coder saved by silently not complying | C | verbatim |
| 126 | 4.2 | ~20 tests stubbed the 3-tuple contract; widening judged disproportionate three times | C | §4.6 |
| 127 | 4.2 | "Building the oracle is what converted the refactor from unaffordable to mechanical" | C | verbatim |
| 128 | 4.2 | the output-seam gap closed by replaying 30 cases through the real hook binary | C | located |
| 129 | 4.2 | "blind exactly where it mattered, four measured times" | **TM** | six rows follow |
| 130 | 4.2 | goldens the JSON response, not the log lines; 1,943 sub-commands passed the corpus | C | §4.6 + decision log:1031 |
| 131 | 4.2 | `fixture_loader.py:679` holds a sixth hardcoded copy of the tool→key map | C | `architecture-judge-backtest.md:45`, verbatim |
| 132 | 4.2 | ticket 98 chunk 2: none of its 6,401 cases contained the three shapes | **M** | cited to a sibling DURABLE summary, not a primary artifact |
| 133 | 4.2 | CLI exit status more permissive than the suite; 22 reason differences | C | §4.6 |
| 134 | 4.2 | ticket 77 phase 2: "I am not offering that as proof" | C | verbatim |
| 135 | 4.2 | ticket 101: "clean is not evidence of no regression for a construct the corpus doesn't contain" | C | verbatim |
| 136 | 4.2 | "three instances of a green row that is green for the wrong reason" | **TM** | at least four in the record; auto-memory counts four |
| 137 | 4.2 | ticket 79: exactly 2 of 6,401 changed; the coder refused to regenerate goldens | C | verbatim in the coder report |
| 138 | 4.3 | one clear win, two nulls, one outright reversal | C | `canary-results.md` |
| 139 | 4.3 | refactored tree's implementation not smaller (13 files/~1,000 vs 12/<1,000) | C | located |
| 140 | 4.3 | the implementer who introduced a layering violation rated the work easier | C | verbatim |
| 141 | 5.1 | `--guard PASS 12/12` after every step for fifteen stages, against the installed v0.5.1 | C | §5.1 defect 9, verbatim |
| 142 | 5.1 | measured sensitivity to TOO-45: zero; still nothing when pointed at the branch | C | verbatim ("0 of 12 canaries disagree") |
| 143 | 5.1 | this is the ticket's own lesson 1, written day one, violated for fifteen stages | C | verbatim |
| 144 | 5.1 | `INSTALLED COPY IS STALE` printed in the session's first message | C | verbatim |
| 145 | 5.1 | cheapest fix: make every instrument print what it measured | C | `retrospective.md:611`, verbatim |
| 146 | 5.2 | two instruments both called "canary" | C | `retrospective.md:612`, verbatim |
| 147 | 5.3 | rename `hard_deny` = 106 tests; behaviour change = 0; 88 and 180 → zero net | C | `[LOG]` qualifier dropped (finding 22) |
| 148 | 5.3 | "a low blast radius is not low safety" | **TM** | source: "not low **risk**"; as written it inverts its own explanation |
| 149 | 5.3 | (omitted) `error_log`: word-rename 798, actual move damage 2,357 | **TM** | the counter-direction in the same source paragraph is dropped |
| 150 | 5.4 | Monte Carlo, 3,000 draws/cell, n=1..12, p=1.0..0.4; 64.7% at p=0.8, 90.9% at p=0.5 | C | exact; condition "leaks held equal at exactly one" dropped |
| 151 | 5.4 | three of four planned numbers unusable, for four agents and zero implementations | C | wording merged from three files under one citation |
| 152 | 5.4 | "run it on ONE case before building it properly" | C | `corrections-analysis.md:62`, verbatim |
| 153 | 5.5 | change-cost metric: flat everywhere, rose 53 → 72, defeatable by rename | C | verbatim |
| 154 | 5.5 | "a compromised instrument; must be replaced" | C | verbatim |
| 155 | 5.6 | PLC2701 was **adopted** as the enforcement mechanism | **R** | rejected in the proposal, in lessons, and in shipped `pyproject.toml:41` |
| 156 | 5.6 | it reports clean on the exact line the predicate flags, permanently by construction | C | two source facts merged; both true |
| 157 | 5.6 | pydocstyle: 11,010 findings, 97.6% punctuation/placement; no D rule measures verbosity | C | verbatim |
| 158 | 5.7 | 3-line `.pyscn.toml` edit passed a step, non-leaves 7 → 2, 147 tests green | C | `[LOG]` dropped |
| 159 | 5.7 | five one-line edits tried, three erased the violation with nothing catching it | C | two different probes merged into one sentence; both real |
| 160 | 5.8 | the `config → engine` inversion has zero import edge, no `--layers` movement | C | defect 10, verbatim |
| 161 | 5.8 | three static instruments all blind, all green, on the motivating defect | C | verbatim |
| 162 | 5.8 | 16 hand-rolled `stderr` writes across four config-layer modules | C | ticket 04; corroborated by commit `e46900b`'s message |
| 163 | 5.8 | "the layer map's **own correctness** masked" them | **TM** | source: the map "encoded the wrong boundary" |
| 164 | 5.9 | neither pyright/LSP nor code-review-graph contributed a finding | **TM** | quote faithful and scoped to four artifacts; contributions exist elsewhere (95-scored, back-test A3 → fix-before-push, resolution-seam report) |
| 165 | 5.10 | three exception lists, all drifted, all over-claiming; one from this ticket | C | `retrospective.md:689`; `[LOG]` dropped |
| 166 | 5.10 | over-claiming produces no failure so nothing notices; RUF100 is the pattern | C | source |
| 167 | 5.11 | "Fifteen stages left uncommitted" | **R** | decision log:1141 says **nine**; fifteen is 5.1's figure, via the retrospective's heading |
| 168 | 5.11 | reverting one step would have taken **four** earlier stages | **U** | no source gives a count; both say "D1a through R1d" |
| 169 | 5.11 | a commit was offered once and never re-offered | C | "offered after D1a", verbatim |
| 170 | 6 | back-test found eight live defects in shipped code, two fix-before-push | C | verbatim |
| 171 | 6 | "every architectural error ... caught by a human asking a direct question" | **M** | not the protocol's closing; chain originates in auto-memory; §7 of this same document disqualifies it |
| 172 | 6 | synthesis gap observed at four scales | C | all four located (two guards; two tests; three audit modules; the coordinator's own queue) |
| 173 | 6 | "Synthesis ... has to be a step in the skill, not a hope" | C | verbatim |
| 174 | 6 | "voice unformed smells at quarter-confidence"; "it smelled. But I didn't raise it yet" | C | `corrections-analysis.md`, verbatim |
| 175 | 7 | the six unsourceable figures | C | all six present in dossier §L/§N — except that the sixth is in §I, not §L/§N as cited |
| 176 | 7 | "should not be carried forward" | **TM** | §1.6 and §6 carry two of the six forward anyway (findings 13, 9) |

---

## What I could not refute, and how hard I tried

The document's factual spine holds up unusually well. Every verbatim quotation I chased — and I chased about forty — was in the file it was attributed to, with the wording intact. The `.peg` replay figures (23,594 / `differing=0` / 506 → 506; 28,770 / 0 / 4349 → 4349) reproduce character for character, including the harvest descriptions that explain why the two parse-failure baselines differ. The guard-canary story, the architecture-judge back-test, the blast-radius numbers, the item-95 mutation run, the pydocstyle census, the 3-line `.pyscn.toml` edit, the 16 stderr writes, the four-for-four canary result, the ticket-18 per-round blocking counts, defect 6, and every Arnon quotation all re-measure exactly. Where the document says a number could not be sourced (§7) it was right, and §2.1 and §2.3 volunteer their own missing costs.

The failures cluster in three places and they are worth naming as a class, because they are all the same mechanism:

1. **A number taken one link up the chain instead of from the primary.** Thirty-vs-twelve files, fifteen-vs-nine stages, the §9.6 citations, ticket 98's `DURABLE/01` citation. In every case the intermediate said it confidently and the primary said something else. Two of the four are exactly the shape the protocol calls transitive citation.
2. **A note read as an outcome where git records a different one.** Ticket 101 shipped. PLC2701's rejection is in `pyproject.toml`. Ticket 79's cost was re-priced in the corpus itself and the re-pricing was not carried.
3. **A qualitative sentence promoted to a measurement.** "About as many" became "roughly half, independently measured twice". "May be a leading indicator — test at the aggregate" became "the cheapest early warning in this entire corpus".

**None of these is a fabricated citation, and none makes a practice's core recommendation wrong.** What they change is what a reader will *quote* — the agent count, the file count, the recall figure, the cost of the two-phase gate — and quoting is the whole point of a document written so its sources can be deleted.
