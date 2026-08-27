---
title: VERIFIED — defect-taxonomy.md, adversarial pass
tags:
- TOO-45
- durable
- verification
permalink: toolguard/durable/intermediate/verified-defect-taxonomy
---

# Verification of `defect-taxonomy.md`

**Verifier scope, stated first so the rest can be weighted.** I re-read **all 77 numbered ticket files plus `00-INDEX.md`** in `toolguard-memories/TOO-45/proposed-tickets/` — the complete primary corpus, in full, not sampled. I did **not** read the 31 files in `resolved/` (I read the three `15-*` headers and the filenames only), which is the same limitation the document under test declares for itself. **32 claims checked**, listed in the table below.

**Headline: the document's outcome census is wrong, and its single sharpest interpretive sentence is wrong. Its most striking claim — the one flagged as most likely to be inflated — survives.**

---

## Lead with the failures

### F1. REFUTED — "35 open" is wrong by at least 15, and the error runs in the flattering direction

**At least 15 of the 35 tickets the document counts as "open / awaiting a decision" have a dedicated, named TOO-45 commit on this branch, every one of them landed BEFORE the taxonomy file was written.**

The taxonomy's mtime is `2026-08-23 16:11`. Measured against `git log master..too-45`:

| ticket | commit | committed |
|---|---|---|
| 42 | `618a19b` Item 42 — a rejected permission entry stops vanishing | 08-20 |
| 45 | `db23d17` ticket 45 — a static check for inert mocks | 08-19 |
| 74 | `c335e22` Item 74 — the hook honours the tool registry | 08-20 |
| 81 | `5577f9d` Item 81 — a sentinel that watches the receiver | 08-21 |
| 88 | `2648423`, `715cdbd` Items 88 and 89 | 08-21, **08-23 15:51** |
| 89 | `52be738`, `715cdbd` | 08-21, **08-23 15:51** |
| 94 | `dd59c24` Item 94 — the config validator becomes nine questions | 08-21 13:55 |
| 96 | `b9e8592` Item 96 — the file-path handler stops inlining | 08-21 13:37 |
| 97 | `efe7847` steps 1-2, `f11ba43` step 3 | 08-21 |
| 98 | `f8c373a`, `b8947a4`, `4509665`, `726fd09` chunks 1-4 | 08-21 |
| 99 | `4d62339` Item 99 — the contract module gains the shapes | 08-21 15:52 |
| 100 | `b63257c`, `e32d3da` | 08-22 |
| 101 | `03d922c` Item 101 — a bare `{}` is a word | 08-22 |
| 104 | `61ecd7b`, `e32d3da` | 08-22 |
| 108 | `9b4ff1d` Item 108 — reading a hook event moves to the contract | **08-23 16:07** |

Every commit subject matches its ticket's stated ask (94 = split `validation_issues`; 96 = call `_log_allowed_command`; 97 = steps 1-3 of the corrected plan; 100 = delete the two orphans; 108 = `read_pre_tool_use_event(source)`). The latest, Item 108, landed **four minutes** before the taxonomy was written.

**So "fixed and closed = 14" is an undercount of at least 15, and "open = 35" an overcount of at least 15.** The corrected shape is roughly **29 fixed, ~20 open**, not 14 and 35.

**Why this matters beyond arithmetic.** The document's own §"Outcome" paragraph praises the corpus's trustworthiness *because* the 2026-08-19 status audit stamped every ticket against what `05f786d` closed, and quotes the index's warning that *"several `Status:` lines are stale in the misleading direction."* **The taxonomy then reproduces exactly that defect** — it derived outcome from ticket-file text, and the ticket files were not updated when the 08-21/08-22/08-23 commits landed. It is the staleness failure it cites as the reason to trust the corpus.

**And the method was applied inconsistently, which rules out "it only read files."** Tickets 95, 80 and 85 are classified `fixed` although none of their files says so — so the author *did* consult outside knowledge for some tickets and not for others. There is no stated rule for which.

### F2. REFUTED — "Corrections run almost uniformly in the direction of the ticket having OVERSTATED its case"

I classified the direction of every explicit correction I found (30 of them, see C1). The split is roughly **13–15 overstated, 9–11 understated, 5–7 misattribution-or-mixed**. "Almost uniformly" is not supportable at 2:1 at best.

The understating corrections are not marginal — several are the campaign's most consequential:

| ticket | the correction | direction |
|---|---|---|
| **18** | *"the result is worse than the ticket described"* — three divergences, not one; *"the ticket's `git logfoo` example understates it"*; **PROMOTED from last to first** | **understated** |
| **19** | *"SCOPE CORRECTION — P1 is a DISCLOSURE-FLOOR bypass as well as a deny-rule bypass, **and this ticket does not say so**"* | **understated** |
| **56** | *"I wrote 'equal provenances merge'. **That is wrong, and the truth is worse** … I recorded only the harmless one"* | **understated** |
| **66** | *"Ticket 30 undercounts"*; *"6 across 4 files and 23 … not 3 and 22"*; *"TICKET 30's FIX DIRECTION IS MEASURABLY WRONG"*; *"the queue's standing note is wrong in BOTH halves"* | **understated** |
| **70** | *"the title understates it"* — the remaining defect outranks the one the ticket is named for | **understated** |
| **75** | a read-only pass judged the file's defects to be *"three deny-vs-ask Givens"*; mutation found **20** | **understated** |
| **80** | `Path.absolute()` found by enumeration, *"appears in neither this ticket's original body nor … six review rounds. Add it to scope"* | **understated** |
| **85** | Arnon corrected the draft's claim that a structural diagram was *"nearly worthless here"* | **understated** |
| **98** | the module docstring *"asserts the deviation is forced. Only part of it is"* | **understated** |
| **31** | headline `~65` inflated — **but** `test_compound.py`'s cluster is *"16, not 12"* and the parser's is *"14 of 18 … not 13"* | **mixed** |
| **37** | *"my wording was too strong"* — **but** *"a second instance this ticket did not name"* | **mixed** |
| **82** | premise wrong (overstated) — **but** the refutation found *"a real defect in the opposite direction"*, 9 divergences | **mixed** |

**The document contains its own counter-evidence and does not reconcile it.** It reports that ticket 18 was *"PROMOTED from last to first"* by measurement, and quotes 56's *"I recorded only the harmless one"* — both in the same file as the uniformity claim.

The safe restatement, which the evidence does support: *corrections were roughly twice as likely to shrink a ticket as to grow it, and the ones that grew it were among the most consequential.* That is a materially different conclusion, because "uniformly overstated" invites a reader to discount the corpus's severities across the board.

### F3. REFUTED — the "22 vs 8" split does not reconcile with the document's own subject table

Interpretation #1 (*"This was a bug hunt in the instruments, not in the product"*) and the note under the subject table both assert **22** tickets are about *"tests, dev tools, audit analyzers and checkers."*

The table's two matching rows are `maintenance and audit tooling` = **10** and `dev instruments and the test suite itself` = **9**. **10 + 9 = 19, not 22.** No row combination naturally produces 22 for that description (adding `documentation and comments` gives 23; adding `audit trail, logging, error routing` gives 25). The number is not derivable from the evidence offered for it.

**The subject table carries no ticket lists at all** — alone among the four axes — so the classification behind the report's main interpretive conclusion is **UNVERIFIABLE** as published.

### F4. TRUE BUT MISLEADING — "only 8 tickets are about matching" does not support "a bug hunt in the instruments, not in the product"

Even granting the table, the product/instrument split it implies is not 8:22. Taking the table at face value, the **product** rows are parser/grammar 12 + matching 8 + config/write-guards/ledger 10 + compound 5 = **35**, against **19** instrument rows. My own reading of the 77 files agrees: the extractor and grammar tickets (19, 34, 79, 87, 91, 92, 98, 101, 102, 105) are permission bypasses and floor losses **in the product**, not in an instrument. Ticket 19 is explicit that extractor defects are *"different layer, and worse"* than matcher defects.

The honest version of the finding is narrower and still interesting: *matching narrowly construed produced few tickets; the parser and the instruments produced most of them.* The published version invites the reader to conclude toolguard's enforcement path was largely clean, which the corpus does not say.

### F5. REFUTED — resolved/ tickets are silently mixed into primary-corpus counts, and the stated limitation does not travel with them

The document declares its `resolved/` limitation in three places, all in the framing or the closing section. **It is absent everywhere the numbers are actually used in the main body:**

- **"The instrument failures — the largest coherent cluster … Nine tickets"** opens with **29** (`run_guard`). **29 is in `resolved/`.** Within the 76-ticket corpus the cluster is **eight**, not nine.
- **"The self-inflicted measurement errors"**: *"**62** and **65** and **60** and **69** are findings where production was correct…"* — **60, 65 and 69 are all in `resolved/`.** Only 62 is primary.
- **Interpretation #7**: *"**Nine** tickets are 'the code is correct, only detection was missing' — 60, 62, 65, 69, 45, 12, 100, 81, 96 — … **I filed them under 'neither'**."* Three of the nine are not in the corpus at all and therefore cannot have been filed under `neither` in a 76-ticket census. The true figure is **six**.

This is precisely the failure the task asked to look for, and it happens three times.

### F6. REFUTED (with a timing caveat stated honestly) — tickets 36 and 92 are marked CLOSED and fixed in their own files

Both carry a trailing section headed **`# CLOSED 2026-08-23 — RE-MEASURED, fixed`** with a measurement table. The taxonomy counts both as **open**, and further presents 36 as a live problem in *"The one that trained the agent out of the right behaviour — 36."*

**Caveat, because it cuts the other way:** both files' mtimes are `2026-08-23 16:11` — the same minute as the taxonomy itself. I cannot establish which was written first, so this may be a race rather than a misreading. **F1's 15 tickets have no such excuse.** But the document asserts *"Each was read to the bottom"*, and for these two the bottom now says the opposite of the classification.

### F7. TRUE BUT MISLEADING — "8 of 76 tickets carry an explicit numeric exposure measurement **against the three log corpora**"

Two of the eight are not corpus measurements:

- **100** — *"zero field reachability by construction"*, from an AST sweep of 383 module-private functions. No corpus involved.
- **106** — *"Reachability / severity: **Zero.** No behaviour changes."* A statement that the proposal is a refactor, not a measurement of anything.

**Corpus-measured tickets: six (18, 101, 83, 84, 92, 102). Of those, four measured zero, not six.** The published "six of eight measured zero" is arithmetically right over a set that includes two non-measurements, and it is used to carry the conclusion *"Only one … had mass real exposure"* — which the narrower, honest set states equally well.

### F8. TRUE BUT MISLEADING (transitive) — "748 … ~1 in 5 real decisions"

The row reads **"752 rules, 748 of them in featherhill — ~1 in 5 real decisions."** Ticket 18's amendment gives featherhill as **4,722 decisions** and separately says *"748 of featherhill's 3,675 matched rules."* 748 / 3,675 = 20%; 748 / 4,722 = **15.8%**. The unit being counted is **rules**, and "1 in 5 real decisions" is obtained by dividing by matched rules. The conflation originates in ticket 18 and is inherited unflagged — a textbook transitive citation. The claim's substance (mass real exposure, concentrated in the real user project) is unaffected.

### F9. TRUE BUT MISLEADING — "eleven findings from executing docstrings, of which **six** are visible here"

The eleven are tickets 17–27. Of those, 17 has no file, 23–27 are in `resolved/`, and **five** (18, 19, 20, 21, 22) are in this corpus. The sixth in the discovery-method list is **33**, which is the sweep's *residue* ticket and is **not one of the eleven**. The correct sentence is *"eleven findings, of which five survive here, plus a separate residue ticket."*

### F10. TRUE BUT MISLEADING — "field evidence — it actually happened" (2 tickets)

Both instances are toolguard's own development environment, not a user:

- **86** — a crash written by the live hook *"while a subagent was running tests with `HOME` unset"* — this repo's own agent.
- **36** — *"Found … by a test-repair agent, incidentally, while trying to comply with the disclosure rule"* — this repo's own agent, and arguably belongs in the mutation/test-repair bucket by the document's own rule.

The prose describes both accurately; the **table row label** does not, and a count of "2" under "it actually happened" will be read as user exposure. Per the project's own `evidence-before-fixing.md`, dogfood is the corpus that counts least — so the honest statement is **zero tickets originate from a user**, and two from the agent that develops toolguard.

---

## Claim-by-claim table — 32 claims checked

| # | claim | verdict | note |
|---|---|---|---|
| 1 | 78 files: 77 numbered + `00-INDEX.md` | **CONFIRMED** | `ls` gives 78 top-level files |
| 2 | `04-config-layer-stderr-consolidation` is superseded; count 76 distinct | **CONFIRMED** | 04b: *"Supersedes `04-config-layer-stderr-consolidation.md`"*, verbatim. 77 − 1 = 76; the union of all four axis lists is exactly the 76 filename numbers, no dupes, no gaps |
| 3 | `resolved/` holds 31 files, 29 distinct subjects, three `15-*` are one chain | **CONFIRMED** | 31 files counted; all three `15-*` files cross-reference each other as one chain; 31 − 3 + 1 = 29 |
| 4 | Tickets 11, 16, 17, 57 referenced by the index have no file anywhere | **CONFIRMED — AND THE CONFIRMATION WAS WRONG (2026-08-24)** | all four are in `TOO-45/resolved/`, a third directory neither the author nor this verification searched. **This is the clearest instance in the corpus of independent verification inheriting the original's scope and so buying nothing.** Previously read: 57 is cited as an existing ticket by 64 and 70, which reinforces the point |
| 5 | Failure-direction counts 31 / 5 / 39 / 1 = 76 | **CONFIRMED (arithmetic)** | lists sum correctly |
| 6 | *"Six tickets are bidirectional and are counted once, under fails-open: 20, 22, 61, **72**, 77, 102"* | **REFUTED** | **72 appears in the fails-CLOSED list** (`Fails closed: 36, 72, 86, 87, 101`) and not in the fails-open list. Prose and data contradict; the count follows the list |
| 7 | Discovery-method counts sum to 76, lists partition cleanly | **CONFIRMED (arithmetic)** | 18+15+14+8+8+6+5+2 = 76; union = the 76 files exactly |
| 8 | *"Arnon asking = 14"* | **CONFIRMED, 13 of 14** | 07, 09, 38, 44, 45, 85, 98, 99, 103, 104, 105, 106, 108 all open with a verbatim Arnon quote or *"you asked for this"*. **06 does not** — the agent found it (files swept in by a `git add -A`); only the *deferral* was Arnon's. The ±3 admission covers this |
| 9 | *"field evidence = 2"* (36, 86) | **TRUE BUT MISLEADING** | see F10 |
| 10 | Mutation/test-repair = 18 | **CONFIRMED** | every ticket in the list carries *"Found … by the test-repair campaign"* or an equivalent RED-test provenance |
| 11 | *"eleven findings from executing docstrings, of which six are visible here"* | **TRUE BUT MISLEADING** | see F9 |
| 12 | *"Only 8 of 76 carry an explicit numeric exposure measurement against the three log corpora"* | **TRUE BUT MISLEADING** | see F7 — six are corpus measurements |
| 13 | *"Six of the eight measured zero or effectively zero"* | **TRUE BUT MISLEADING** | four of six, on the corpus-measured set |
| 14 | Ticket 18: 752 rules, 748 in featherhill, ~1 in 5 decisions, PROMOTED | **TRUE BUT MISLEADING** | see F8; the promotion and the 748 are verbatim from the ticket |
| 15 | Corpus sizes: featherhill ~4,722, toolguard ~52,191, instagram 235 | **CONFIRMED** | verbatim in the 18/83/84 amendments |
| 16 | 101: 19 raw → ~9 genuine; 102: 3 raw → 0 genuine | **CONFIRMED** | 101: 7+12+0 = 19 raw, 1+~8 genuine; 102's DISPOSITION: 3 raw, 1 genuine, and that one is JSON-on-stdin, not the dangerous shape |
| 17 | *"no defer was taken unilaterally — 83, 84 and 102 were all flagged back to Arnon"* | **CONFIRMED** | 83 *"DEFER CANDIDATE … flagged for Arnon"*; 84 *"PARTIAL DEFER CANDIDATE — flagged for Arnon"*; 102 carries Arnon's verbatim instruction |
| 18 | Outcome counts 21/35/14/3/1/1/1 = 76 | **REFUTED** | see F1 — arithmetic is internally consistent, the classification is not |
| 19 | *"fixed and closed = 14"* | **REFUTED** | at least 29 |
| 20 | *"open / awaiting a decision = 35"* | **REFUTED** | at most ~20 |
| 21 | 36 and 92 are open | **REFUTED** | both files end `# CLOSED … RE-MEASURED, fixed`; timing caveat in F6 |
| 22 | 82 = "refuted" | **TRUE BUT MISLEADING** | the premise was refuted, but the corrected scope shipped as `221eba9` *"Item 82 — toolguard strips the wrappers Claude Code strips"*. Filing it under a bare "refuted" hides that it produced a real security fix |
| 23 | Subject counts sum to 76 | **CONFIRMED (arithmetic)** but **UNVERIFIABLE (substance)** | no ticket lists are given for this axis |
| 24 | *"only 8 are about matching; 22 about tests, dev tools and audit analyzers"* | **REFUTED** | see F3 — the table gives 19 |
| 25 | *"a bug hunt in the instruments, not in the product"* | **TRUE BUT MISLEADING** | see F4 |
| 26 | *"Nine tickets are about a checker that certified something it never examined"* (29, 66, 73, 20, 56, 21, 37, 72, 79) | **REFUTED** | 29 is in `resolved/`; eight within the corpus. The eight substantive descriptions all check out verbatim against their tickets |
| 27 | *"Nine tickets are 'the code is correct, only detection was missing' … I filed them under 'neither'"* | **REFUTED** | six; 60, 65, 69 are in `resolved/` (F5) |
| 28 | *"62 and 65 and 60 and 69 are findings where production was correct"* | **MISATTRIBUTED** | true of the tickets, but three are outside the corpus being characterised |
| 29 | **"~30 of 76 (≈39%) carry an explicit correction, refutation or reframing"** | **CONFIRMED** | **I recounted independently and strictly.** See C1 — I get exactly **30**, and a looser reading gets ~50. This claim survived a hostile recount |
| 30 | *"Two premises wholly wrong (82, 105); nine materially reframed"* | **CONFIRMED** | 82 *"THIS TICKET'S PREMISE IS WRONG"*, 105 *"REFUTED … THE PREMISE ABOVE IS WRONG"*, both verbatim; the nine reframes are all identifiable in their files |
| 31 | Verbatim quotes: 85's *"every architectural error in TOO-45 was caught by a question from Arnon, never by a metric"*; 97's *"eleven agent runs, four review rounds … three security weakenings"*; 36's *"a leading comment does not affect rule matching"*; 105's *"fires zero times"*; 75's *"eleventh confirmed instance"*; 79's `undecidable_fallback = "allow_with_no_warnings"`; 82's nine wrappers; 51's 4.84% | **CONFIRMED, all eight** | every quotation checked is verbatim and in the cited ticket. **This is the document's strongest area** — no fabricated citation found anywhere |
| 32 | *"the corpora contaminate themselves … 102 overstated by 3x; 101's featherhill count by 7x"* | **CONFIRMED** | 102: 3 raw → 1 genuine; 101 featherhill: 7 raw, 6 probes discarded, 1 genuine |

---

## C1 — my independent recount of the corrections claim, because it is the one the task expected to break

I applied a **strict** test: the file must explicitly say that something previously asserted was wrong, false, overstated, miscounted, misattributed, or must be reframed. Ordinary updates, new sub-findings, and status stamps do **not** count.

**Thirty tickets qualify:** 13, 14, 18, 19, 20, 21, 31, 37, 38, 42, 45, 52, 56, 61, 64, 66, 70, 74, 75, 77, 80, 81, 82, 83, 85, 88, 97, 98, 105, 107.

Representative markers, all verbatim:

- 13 — *"A correction to an earlier claim in this ticket: I asserted there was no syntax for 'anywhere'. That was wrong."*
- 31 — *"THE ~65 FIGURE IS INFLATED, and the cause is a systematic conflation … it is a correction to my counting method"*
- 37 — *"CORRECTION 2026-08-13 — my wording was too strong and a reader checking it would find it false."*
- 38 — *"CORRECTION 2026-08-13 — the 'silently' claim is FALSE, measured"*
- 42 — *"CORRECTION … the count is SEVEN, not eight."*
- 61 — *"I told the agent ticket 59 … lands on this module. It does not."*
- 77 — *"this ticket's native comparison was false, and so was the decision built on it"*
- 81 — *"two claims in the first draft were wrong and are corrected below"*
- 97 — *"The original framing — 'kind answers two questions' — is directionally right and imprecise."*
- 107 — *"REFRAMED … This is a better criterion than the one I filed under, and it changes the ticket."*

A further ~20 (04b, 32, 36, 39, 44, 47, 62, 73, 79, 84, 86, 90, 92, 93, 96, 100, 101, 102, 103, 104, 106, 108) carry weaker corrections that a looser reading would admit.

**30 / 76 = 39.5%. The published figure reproduces exactly.** Given the document itself hedges it (*"a judgement call … treat ~39% as approximate"*), it is if anything conservative. **The claim the task flagged as most likely inflated is the one claim that best survives adversarial recount** — which is worth recording, because the failures above are all in numbers the document presented with more confidence.

---

## What I could not check

- **The 31 `resolved/` bodies.** Everything in the secondary section, and the eight/29 and ten/29 splits inside it, rests on headline framing I did not open. The document says so; I am repeating it so this report is not read as covering them.
- **The subject-axis classification** — no lists were published, so I could re-measure nothing beyond the arithmetic and the two named figures (8 and 22), one of which fails.
- **Whether the 15 commits in F1 fully close their tickets.** I matched commit subject to ticket ask, which establishes the work landed, not that no residual remains. Several may be "partially fixed" rather than "fixed". Either way they are not "open".
- **The order of writing between the taxonomy and the `CLOSED` sections of 36 and 92** (F6).

## What is solid, stated plainly so the document is not discarded whole

Every **quotation** I checked is verbatim and correctly attributed — eight of eight, across seven tickets. Every **mechanism description** in "The cases worth carrying forward" that I could check against its ticket (18, 20, 21, 29, 37, 56, 66, 72, 73, 79, 82, 96, 97, 105, 106, 107) is accurate. The **failure-direction and discovery-method lists partition the 76 exactly**, with one internal contradiction (72). The **corrections figure survives a hostile recount.**

The defects are concentrated in exactly two places: **the outcome census, which was derived from stale ticket text against a branch that had moved past it**, and **three interpretive sentences that reach further than the counts underneath them.**
