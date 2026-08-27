---
title: 05-campaign-statistics
type: note
permalink: toolguard/durable/05-campaign-statistics
tags:
- TOO-45
- durable
- statistics
- measurement
---

# TOO-45 campaign statistics

Written 2026-08-23, ahead of the unversioned-note deletion. **Cost is deliberately out of scope here** — wall-clock, tokens and dollars live in `02-campaign-cost-data.md` and are not repeated. This document covers everything else that can be counted: the branch, the tickets, the defects, the review process, the measurement experiments, the corpus and the agent's own traffic through the hook.

## How to read the provenance tags

| tag | meaning |
|---|---|
| **MEASURED-HERE** | I counted it myself in this session, from `git`, `find`, `grep`, `wc` or a test run. The method is stated inline. |
| **MEASURED-SOURCE** | a source in the corpus states it and says how it was measured. |
| **ESTIMATED** | the source itself calls it approximate. |
| **RECALLED** | the source quotes a figure it did not measure, or whose origin it does not give. |
| **DISPUTED** | two sources give different numbers for the same quantity. Both are shown; neither is chosen unless a source adjudicated it. |

**Rule applied throughout: where a source hedges, the hedge is kept.** Several counts in `DURABLE/intermediate/defect-taxonomy.md` were corrected on 2026-08-23 by `VERIFIED-defect-taxonomy.md`; the corrected figures are used, and the original is shown beside them so the size of the error stays visible.

---

# 1. Scale — the branch

Everything in this section is **MEASURED-HERE** from `git log`, `git diff` and `git ls-tree` against the merge-base `532de02` (`master`) and the branch tip `305caa3` (`too-45`).

| quantity | value |
|---|---|
| commits on `master..too-45` | **79** |
| first commit | `d5bdab3`, 2026-08-04 21:04 |
| last commit | `305caa3`, 2026-08-23 16:59 |
| calendar span | 20 days |
| days carrying at least one commit | **13** |
| version bump | `0.5.1` → `0.6.0` (`pyproject.toml`) |

## Commits per day

| date | commits | | date | commits |
|---|---|---|---|---|
| 08-04 | 3 | | 08-14 | 2 |
| 08-06 | 3 | | 08-19 | 5 |
| 08-07 | 2 | | 08-20 | 9 |
| 08-08 | 2 | | **08-21** | **36** |
| 08-09 | 4 | | 08-22 | 8 |
| 08-10 | 1 | | 08-23 | 3 |
| 08-12 | 1 | | | |

**46% of the campaign's commits landed on one day.** There is a four-day hole at 08-15 → 08-18 with no commits and no hook log file at all.

## Lines and files

Cumulative diff `master..too-45`:

| scope | files | insertions | deletions |
|---|---|---|---|
| **everything** | 367 | 109,588 | 24,049 |
| everything **except** `toolguard-memories/` | 279 | 94,877 | 23,346 |
| `test/` | 124 | 66,640 | 9,416 |
| `toolguard/` (the product package) | 78 | 15,118 | 13,282 |
| `toolguard-memories/` | 88 | 14,711 | 703 |
| `tools/` (dev instruments) | 9 | 10,989 | 33 |
| `docs/` | 56 | 1,571 | 527 |

**Gross churn is 1.56x the net diff.** Summing each commit's own `--shortstat` gives **147,103 insertions and 61,564 deletions — 208,667 lines touched** against a cumulative diff of 133,637. Roughly 37,500 insertions were written and then rewritten or removed inside the branch.

## The six commits that are most of the campaign

| commit | date | lines changed | subject |
|---|---|---|---|
| `a3e3f27` | 08-06 | 36,084 | architecture cleanup overhaul |
| `bdb7c95` | 08-14 | 33,718 | phase 1 — repair the test suite |
| `7460ffb` | 08-12 | 31,137 | Item 07 — doc-comment sweep |
| `3bb21b7` | 08-07 | 24,099 | remove the compound/resolve runtime cycle |
| `d5bdab3` | 08-04 | 19,659 | verdict corpus + architecture fitness tool |
| `e46900b` | 08-07 | 10,898 | move cross-cutting observability below config |

**Those six commits are 74.6% of all lines touched on the branch** (155,595 of 208,667). The remaining 73 commits share 25%.

## Module inventory

| | master | too-45 |
|---|---|---|
| `.py` files under `toolguard/` | 68 | **79** |
| total `.py` lines under `toolguard/` | 38,257 | **40,037** |
| `.py` files under `test/` | 69 | **96** |
| files under `docs/` | 14 | **60** |

Twelve production modules were added — `ambient.py`, `api.py`, `claude_code_contract.py`, `error_reporter.py`, `file_lock.py`, `file_matching.py`, `install_update.py`, `once_per.py`, `once_per_store.py`, `permission_migration.py`, `permission_resolution.py`, `tool_spec.py` — and one deleted (`toolguard/tools/decision.py`).

**The package was rewritten, not grown.** 15,118 insertions and 13,282 deletions produced a net gain of 1,780 lines: **+4.7%**. Roughly a third of the package's lines were replaced in place. `config.py` alone went 670 in / 1,320 out (net **−650**) and `resolve.py` 317 in / 660 out (net **−343**), which is the measurable form of Arnon's 2026-08-07 review note that *"`config.py` being large is not itself the problem — the thing to guard is entanglement"*.

---

# 2. Scale — the test suite

**MEASURED-HERE.** `git grep -E "^\s+def test"` at each branch commit; the count at the tip was cross-checked against an actual run.

| point | tests | test classes |
|---|---|---|
| `master` (`532de02`) | **2,186** | 425 |
| first branch commit (`d5bdab3`, 08-04) | 2,321 | — |
| plateau (`2113d02` → `7460ffb`, 08-09 → 08-12) | 2,733 | — |
| after phase 1 (`bdb7c95`, 08-14) | **3,628** | — |
| branch tip (`305caa3`, 08-23) | **4,008** | 804 |

Verification of the tip: `uv run python -m unittest discover -s test -t .` reports `Ran 4008 tests in 58.097s / OK (expected failures=4)`. The grep proxy and the runner agree **exactly** at 4,008, which is why the same proxy is trusted for `master`.

- **Suite growth over the campaign: +83.3%** (2,186 → 4,008). Test classes +89%.
- **895 of those tests — 22% of the final suite — arrived in one commit**, `bdb7c95` (77 files, 28,865 insertions, 4,853 deletions). That is the phase-1 test-repair commit. `methodology/in-process-mutation-testing.md` states the same transition as *"77 test modules, 2,733 -> 3,628 tests"* (**MEASURED-SOURCE**), and it reconciles exactly with the branch history.
- 56 test files were added. There is a run of **ten consecutive commits on 08-21 at a flat 3,966 tests** — the wrap-up items, which changed production code and added no tests.
- Phase 1 deliberately left **137 red tests** for phase 2 to triage (**MEASURED-SOURCE**, `TOO-45 status 2026-08-14 - phase 2.md`). Four expected failures remain at the tip.

---

# 3. Where the lines actually went

**MEASURED-HERE**, from `git diff --numstat`. This is the accounting that changes how the campaign reads.

| body of work | insertions | share of the 94,877 non-memory insertions |
|---|---|---|
| product code (`toolguard/`) | 15,118 | 15.9% |
| **new dev instruments (`tools/`)** | **10,989** | 11.6% |
| **tests for those instruments** | **10,104** | 10.7% |
| **verdict-corpus fixtures (`test/verdict_corpus/`)** | **15,548** | 16.4% |
| product tests (`test/` minus the two above) | 40,988 | 43.2% |
| docs | 1,571 | 1.7% |

Six instruments were built during the campaign: `architecture_fitness.py` (4,978), `change_role_classifier.py` (2,493), `touch_set_score.py` (1,102), `corpus_build.py` (1,007), `touch_set_inventory.py` (792), `comment_hygiene.py` (563), plus `generated_files.py` (34). Their four dedicated test modules are `test_architecture_fitness.py` (4,735), `test_change_role_classifier.py` (2,299), `test_touch_set_inventory.py` (1,730), `test_touch_set_score.py` (1,340).

**Instruments plus their tests come to 21,093 insertions — 39% more than the entire product package received.** Adding the verdict corpus (`cases.jsonl` and `goldens.jsonl`, 6,401 lines each, plus a 1,165-line fixture loader) puts **38.6% of all non-memory insertions into measuring apparatus, its tests and its fixtures.**

This is worth holding against the defect taxonomy's headline interpretation, *"this was a bug hunt in the instruments, not in the product."* `VERIFIED-defect-taxonomy.md` refuted that on ticket counts (F3/F4: the claimed 22 instrument tickets is not derivable from the table, which yields 19, against 35 product rows). **By tickets the claim is false; by lines written it is close to true.** Both facts are real and they are about different things — what was *found* versus what was *built to find it*.

---

# 4. Scale — tickets

## The numbering

**MEASURED-HERE**, by listing `TOO-45/proposed-tickets/` and its `resolved/` subdirectory.

| quantity | value |
|---|---|
| ticket numbers allocated | 1 – **108** |
| numbers with at least one file | **104** |
| ~~numbers referenced but with no file anywhere~~ | **0 — REFUTED 2026-08-24.** All four (11, 16, 17, 57) are in `TOO-45/resolved/`, a sibling of the searched directory. See §"what could not be counted". |
| files in `proposed-tickets/` | 78 (77 numbered + `00-INDEX.md`) |
| files in `proposed-tickets/resolved/` | 31 |
| distinct ticket *subjects* | **105** (76 primary + 29 resolved, after collapsing the `04` pair and the `15` trio) |

Three numbering collisions are documented in `00-INDEX.md`, all confined to 01–33: `04` (a pair, one superseding the other), `14` (a pair with two different subjects, which is why 104 numbers yield 105 subjects), and `15` (a chain of three files, one subject). Numbers 34–108 are collision-free.

**Ticket 17 is the notable absence.** It is cited as a peer of 18 and 19 throughout the corpus — a `[native]` end-anchor under-match, i.e. deny rules that do not fire — and no file for it exists. `82-prereg.md`-era work pre-registered an estimate for it; nothing was ever scored.

## Coverage by commit

**MEASURED-HERE**, by extracting `Item N` / `ticket N` / `punch-list N` from commit subjects on `master..too-45`:

- **59 of 79 commits** name a numbered item.
- **42 distinct ticket numbers** have at least one dedicated, named commit: 01, 03, 04, 05, 07, 10, 14, 15, 18, 19, 20, 22, 32, 38, 39, 42, 44, 45, 52, 64, 70, 74, 77, 78, 79, 80, 81, 82, 85, 88, 89, 94, 95, 96, 97, 98, 99, 100, 101, 104, 105, 108.

## Outcome census

The taxonomy's first-published census was refuted the same day it was written. Both are shown.

| outcome | **as first published** | **corrected 2026-08-23** |
|---|---|---|
| fixed and closed | 14 | **at least 29** |
| open / awaiting a decision | 35 | **at most ~20** |
| partially fixed | 21 | 21 (unchanged) |
| deferred with evidence | 3 | 3 |
| refuted (premise wrong) | 1 | 1 — but 82's corrected scope shipped as `221eba9` |
| refuted then redirected | 1 | 1 |
| declined by Arnon | 1 | 1 |

Source: `DURABLE/intermediate/defect-taxonomy.md` (**as published**) and `VERIFIED-defect-taxonomy.md` finding F1 (**corrected**, **MEASURED-SOURCE** against `git log master..too-45`). The verification found **at least 15** tickets classified as "open" that had a named commit *before the taxonomy was written* — the last of them, Item 108, landing **four minutes** earlier. Denominator throughout is 76 primary tickets; the 29 subjects in `resolved/` are excluded.

**My independent count of 42 commit-named tickets is consistent with the corrected shape** (~29 fully fixed plus 21 partially fixed = 50 tickets with work landed, of which 42 got a commit that names them). It is not consistent with the published 14.

**Caveat carried from the verification, and it matters**: matching a commit subject to a ticket's ask establishes that the work landed, not that no residual remains. Several of the 15 may belong under "partially fixed" rather than "fixed", and the individual re-classification was never done.

---

# 5. Defects

All counts in this section are **MEASURED-SOURCE** from `defect-taxonomy.md`, over **76 primary tickets**, with the 2026-08-23 corrections applied. The `resolved/` tier (29 subjects) was never classified, so *every distribution below is over the tickets that stayed open longest* — a bias the taxonomy declares about itself.

## Failure direction

| direction | count | share |
|---|---|---|
| **fails open** — permits, or fails to block, or an instrument certifies what it never examined | **31** | 41% |
| **fails closed** — blocks or asks where it should not | **5** | 7% |
| neither — structure, docs, tests, dead code | 39 | 51% |
| refuted before a direction could be assigned | 1 | 1% |

**Roughly six fails-open findings for every fails-closed one.** The taxonomy's own reading, worth preserving: this is a property of what is *findable*, not of toolguard. A fails-closed defect produces a prompt somebody notices; a fails-open defect produces silence.

## Discovery method

| method | count | share |
|---|---|---|
| mutation testing / the test-repair campaign | **18** | 24% |
| direct measurement or probing | 15 | 20% |
| Arnon asking a question, reviewing, or instructing | 14 | 18% |
| a tool reported it (pyscn, pyright, architecture judge, AST sweep) | 8 | 11% |
| static analysis / code reading alone | 8 | 11% |
| executing the code's own comments and docstrings | 6 → **5 corrected** | 8% |
| a blinded review round on another ticket's fix | 5 | 7% |
| field evidence | 2 | 3% |

**DISPUTED — mutation's yield.** `methodology/in-process-mutation-testing.md` states *"the campaign filed roughly fifty production defect tickets, several security-shaped, from mutations alone"* (**ESTIMATED**, the source says "roughly"). The taxonomy attributes **18 of 76** primary tickets to mutation. The two can only be reconciled if nearly every one of the 29 `resolved/` subjects was also mutation-found — 18 + 29 = 47 — which nobody has checked, because `resolved/` was never classified. **Report both; do not average them.**

## Field evidence — the number that should lead

**Zero of 76 tickets originate from a user.** Two originate from something actually going wrong, and both happened to this repository's own agent:

- **86** — `HOME` unset makes the hook deny every tool call; a real crash report written by the live hook while a subagent ran the test suite here.
- **36** — a `# INTENT:` disclosure comment containing backticks makes toolguard reject the command it describes; hit by an agent complying with this repo's own disclosure rule.

Everything else — 74 of 76 — was manufactured by looking. Per the project's own `evidence-before-fixing.md`, dogfood is the corpus that counts least, so the honest statement is **zero field tickets, two dogfood incidents**.

## How much exposure was actually measured

Only **8 of 76 tickets carry a numeric exposure statement**, and the 2026-08-23 verification cut that further: only **6 are measurements against the log corpora** (100 is an AST sweep, 106 is a claim about a change). Of those six, **four measured zero or effectively zero** — 83, 84, 92, 102.

| ticket | measured exposure | disposition |
|---|---|---|
| **18** — multi-token prefix over-grant | **752 rules, 748 in featherhill** | **PROMOTED** from last to first |
| 101 — grammar rejects a bare `{}` | 19 raw → ~9 genuine after discarding probes | committed |
| 83 — tilde-spelled extended-type rules | **0** | defer candidate, flagged to Arnon |
| 84 — regex ending in escaped whitespace | **0** | partial defer |
| 92 — heredoc piped to a shell | **0** | **fixed anyway** — accidental and silent |
| 102 — here-strings misparsed | 3 raw → **0** genuine | deferred by Arnon |

**One ticket in seventy-six had mass real exposure, and it had been scheduled last on cost grounds until the measurement reversed the ordering.** Note also that the "measure exposure before fixing" rule was instituted on 2026-08-20, roughly two-thirds of the way in; everything committed before `05f786d` (08-19) was fixed without one.

Ticket 18's headline number carries a **unit correction** worth repeating because it propagated: the 752 are **rules**, not decisions, and the widely-quoted "1 in 5" divides by featherhill's 3,675 *matched* rules (20%), not its 4,722 decisions (15.8%).

## The re-triage corpus

**MEASURED-SOURCE**, `TOO-45-retriage-2026-08-20.md`, over **57,448 commands**:

| shape | featherhill | toolguard | total | ticket |
|---|---|---|---|---|
| command substitution `$(...)` | 5 | 1,115 | 1,121 | 79 |
| multi-token `:*` rules | **748** | 1 | 752 | 18 |
| blanket allow rule (`*`) | **60** | 6 | 66 | 21 |
| backticks | 0 | 98 | 98 | 34 |
| disclosure comment `#` | 5 | **652** | 657 | 36 |
| wrapper prefix | 3 | 103 | 106 | 82 |
| `&>` / `>|` / `<>` | 0 | 0 | 0 | 87 |
| `[native]` end-anchored | 0 | 0 | 0 | 17 |
| tilde + extended-type rule | 0 | 0 | 0 | 83 |
| regex ending in escaped whitespace | 0 | 0 | 0 | 84 |

**Only about a third of the open queue had any log signature at all** — a ticket fires in the logs only when its trigger is a command or rule shape. And the corpus's own biggest number is an artifact: 652 of 657 disclosure-comment hits are this repo's mandated markers.

**DISPUTED — toolguard corpus size.** `defect-taxonomy.md` cites ~52,191 toolguard decisions; `evidence-before-fixing.md` cites 51,918 (of which 9,848 were fallbacks, 19%). featherhill is quoted as 3,675 matched rules and 4,722 decisions in different places; instagram as 235. Nobody reconciled these.

## Suite blindness

**MEASURED-SOURCE**, ticket 31 — described in `00-INDEX.md` as *"the sweep's largest quantitative finding"*:

| measurement | method | result |
|---|---|---|
| tests whose assertions **cannot fail** | read, then run the fixture or mutate the named mechanism | **~65 across ~78 files** (the ticket's own amendment says this figure was inflated) |
| mechanisms with **zero test detection** | delete in an out-of-tree copy, run all 2,733 tests, subtract a 2-error environmental floor | **~50** |

- **22 distinct shapes** of un-failable assertion catalogued (19 found during the sweep, 3 folded in late).
- Per-module mutation survival **before** repair: 47% (14 of 30), 55% (23 of 42), 58% (over 81 mutants). Largest single run: **42 mutations, 23 survivors**.
- Largest single cluster: `test_compound.py`, **12 of 223 tests** satisfied by a fail-open safety net rather than by correct behaviour.
- On one module a careful read-only review reported *"one minor redundancy"*; mutation found **13 of 25 mechanisms at zero detection**.

---

# 6. Process — blinded review rounds

## What survives as files

**MEASURED-HERE**, counting `reports/review-<n>-round<k>.md`:

| ticket | surviving round files |
|---|---|
| 18 | **6** |
| 78 | 5 |
| 79 | 4 |
| 39 | 3 |
| 44 | 3 (numbered 4, 5, 6) |
| 80 | 3 |
| 74 | 2 |
| 77 | 1 |
| **total** | **27** |

`02-campaign-cost-data.md` counts **35** files under `reports/review-*.md` and reports that 25 of them carry a cost figure. The larger number includes repair reports and the two grammar-phase reviews; the 27 above are review rounds proper. **Both are right about different populations.**

## The finding that stands out

**MEASURED-HERE: all 27 surviving review-round files report at least one blocking finding.**

**Read that as yield, not as failure.** Arnon, 2026-08-24: *"In the cases where we measured the shape of draining the issue counts of multiple review rounds, you got exactly what we wanted from them — continuous discovery and improvement without needing human intervention. If it doesn't waste my time, even small improvements that I would not care about are still improvements. Even if we don't end up clearing every single thing by the stop decision — but the manual review passed — then you have success."*

A round reporting blocking findings is a round doing its job. The unit under evaluation is the **series**, not the round: the question is whether counts drain and whether the manual review at the end passes, not whether any individual round came back empty. Under that reading, 27 of 27 rounds returning something is the gate producing continuously at a cost that never reached Arnon.

What is a genuine gap is narrower: **the only zero-blocking round anywhere in the record is ticket 45's round 5, and it has no surviving file** — it exists solely as the terminal entry of a table. So the drain shape is well attested in its descent and thinly attested at its floor.

## Blocking findings per round

Two sources, and they do not fully agree.

**From `TOO-45-punch-list-2026-08-20.md`** (**RECALLED** — the table states counts without citing the files):

| ticket | rounds | trajectory | shape |
|---|---|---|---|
| 45 | 5 | 14 → 14 → 7 → 4 → **0** | high, drains |
| 44 | 5 | 12 → 3 → 4 → 3 → 1 | high, drains |
| 78 | 5 | 7 → 2 → 3 → 1 → 2 | high, drains |
| **18** | **6** | **2 → 2 → 1 → 3 → 3 → 2** | **low, never drains** |

**From the round files themselves** (**MEASURED-HERE**, reading each file's headline count):

| ticket | trajectory |
|---|---|
| 18 | 2 → 2 → 1 → 3 → 3 → 2 (matches the table exactly) |
| 78 | (round 1 has no headline count) → 2 → 3 → 1 → 2 (matches from round 2 on) |
| 79 | 5 → 4 → 3 → 1 |
| 39 | 3 → 4 → 2 |
| 74 | 5 → 1 |
| 77 | 3 |
| 80 | (rounds 1–2 have no headline) → 2 |
| **44** | rounds 4, 5, 6 report **1 → 4 → 1** |

**DISPUTED — ticket 44.** The table's last three entries are 4 → 3 → 1; the three surviving files report 1 → 4 → 1, and they describe themselves as *prose-only* reviews with a narrow scope (comments, docstrings, message strings). Ticket 44 therefore ran at least two distinct review series, and the campaign's most-quoted round-curve table cannot be reconciled with the only files that survive for it.

**Elsewhere in the corpus, 79's curve is quoted as "5→4→3"** (`TOO-45 phase 3 resume.md`). The files show a fourth round at 1 blocking. Both statements were true when written; only one is true now.

## Convergence

The round-curve control (Arnon, 2026-08-20) is the campaign's own reading of this data, and it is a shape argument rather than a count argument: *"round count alone would not have flagged 18 — 44 and 78 also ran 5. The signal is the shape."* Ticket 18 opened with the fewest findings of any ticket and never converged; rounds 4 and 5 each found more than round 1. Both stop-conditions the control names fired at **round 3**; acting on either would have committed the matcher three rounds earlier.

**And the non-convergence was itself a correct detection, which is the strongest thing this section can say about the mechanism.** Ticket 18's matcher fix was verified correct from round 1. What kept generating findings was documentation of a `curl` carve-out recipe, and that recipe was contradicting itself: a pattern verified against nine attack shapes and never against ordinary use, so it rejected `curl -sS http://localhost:8080/health` (`feedback_test_what_a_rule_permits`); a `SKILL.md` claim about a DEFAULT trailing `*` sitting beside the ticket's own new finding that a hand-written trailing ` *` behaves differently, *"so the skill and row 18 cannot be read as contradicting"* (`review-18-round3.md`, N4); and a docstring recommending the exact-invocation form that the same diff's documentation names as the **rejected** alternative (`review-18-round5.md`). The guidance the rounds were repairing was inconsistent with itself, so each repair created the next finding. **A flat, non-draining curve was the only instrument that saw this** — the suite was green throughout, the production diff was small and right, and no per-round verdict would have revealed it. The control fired on exactly the case it exists for.

## Implementation passes

Where a source counts them (**ESTIMATED** unless noted):

| item | passes / rounds |
|---|---|
| punch-list #01 suppression store | 5 implementation passes + 4 reviews |
| punch-list #04 error reporter | 5 implementation passes |
| ticket 39 | 4 implementation passes + 3 review rounds |
| punch-list #15 migrate lock | 3 passes |
| ticket 74 | 1 implementation pass + 2 review rounds |
| ticket 79 | **7, 9 or 11 agent runs — three incompatible counts** (see §9) |
| phase 2 (08-14) | 137 reds triaged into 10 production defects, fixed by **11 agent runs** |

---

# 7. Process — the touch-set (surprise-factor) experiment

A blinded estimator read exactly two files per ticket — the ticket as filed and a file inventory — wrote predictions to sealed files, and returned a token. Scoring is line-weighted recall against the final committed diff.

**MEASURED-HERE**, counting `reports/surprise/`:

| artifact | files | distinct tickets |
|---|---|---|
| pre-registrations (`*-prereg.md`) | 33 | 29 |
| scored items (`*-scored.md`) | 29 | 25 |
| `*-estimate-predictions.md` | 16 | — |
| `*-estimate-uncertainties.md` | 16 | — |

- Pre-registered but **never scored**: 17, 19, 64, 81, 82, 83, 84, 108 (8 tickets).
- Scored **without** a pre-registration: 03, 04, 10, 15 — the retro-scored batch, opened after their work was long committed.

## Recall — and what it is and is not for

**Recall is not the output of this experiment.** Arnon, 2026-08-24: *"The purpose of the surprise-factor quasi-measure is not to get good predictions. It's to draw attention to where you need to review in retrospect why we got surprised. For that you do not need a great predictor. You need an OK predictor with fairly stable performance."*

So recall answers one narrow question — is the predictor good enough, and steady enough, to rank a tail — and the property that matters for that is **tail rank stability**, not level and not variance. That was measured and never framed as such: recomputing production-only moved pooled recall 87.8% → 84.2% and the standard deviation only 26.4 → 24.1, **and the bottom two ranks are invariant** — 79 and 39 stay worst under both definitions, and all the reshuffling is in the middle. The metric cannot rank the middle. It does not need to.

Line-weighted recall, **MEASURED-SOURCE** from `CONSOLIDATED-REPORT.md`, spanning **15.2% to 100%**:

| item | recall | note |
|---|---|---|
| 22, 85a, 74 | **100%** | 74 is the first perfect touch set; 22 the first fully-clean run |
| 39 | 99.1% | contaminated by a coordinator appendix |
| 20 | 95.0% | 89.3% discounting wrong-reason hits |
| 15 | 87.8% | leak discount **inert** — genuine foresight |
| 04 | 76.6% | honestly a range, 57.5–76.6 |
| 44 | 71% | 6 surprises, 0 alarms |
| 03 | 64.4% | but **12.0%** unleaked |
| 80 | 56% | no design leak |
| 18 | 52% | unleaked downstream **0/7** |
| 10 | 45.8% | mostly a scope-purity artifact — only 12 of 620 unpredicted lines are attributable to the estimator |
| 79 | **15.2%** | the worst |

Batch 2 (95, 99, 89, 88, 98 chunks 2–4, 100, 104, 103, 101, 105) scored **at or near 100% production recall almost everywhere** — and the batch's own report says why that is *less* impressive than it looks: *"I now write the tickets AND the briefs… an author predicts their own scope well."*

**Contamination: 7 items, two routes.** Return channel — 05, 19 (both excluded). Coordinator appendix — 20, 39, 57, 64, 70, where measurements were appended to the ticket file that is the estimator's only permitted reading. The corpus's own verdict: *"measuring before briefing was the campaign's highest-yield habit; writing the result into the ticket is what destroyed the measurement."*

**Return-channel wording, measured:** substantive leaks were 2 of N under weak wording and **0 of 3** under wording that names the consequence.

**Cause codes in play:** `E` (estimator ignorance), `P` (prose coupling), `C` (hidden coupling), `D` (latent defect), `R`, `S` (scope-conditioning), `X` (descoped), `A` (absorbed), `I` (inherited staleness), `N` (defect introduced by the change), `B` (brief-constrained). `T` (transient) was proposed and dropped. Only `C`, `P` and `D` are alarms.

**Prose coupling (`P`) recurred on five consecutive items** — 77, 78, 79, 05, 03 — making it the most *frequent* under-prediction in the series and, per the log, the cheapest to fix.

## Value delivered — did the "review me" signals pay?

**This is the question the experiment exists to answer, and no earlier version of this section addressed it.** The test, per Arnon: a low score is worth its cost if the retrospective it triggers tends to end in a correction — to code, architecture, or process — and if enough of those corrections are actually adopted. A signal that yields only noise gets ignored and is worth nothing.

**MEASURED-HERE**, 2026-08-24, by tracing every conclusion recorded in `reports/surprise/` forward to a commit, a durable memory, a prereg template change, or nothing.

| conclusion | trigger | acted on? |
|---|---|---|
| Named uncertainties belong **in** the pre-registration, with explicit predictions | 79 (15.2%, worst) | **yes** — a standing prereg section from item 100 onward (100, 101, 103, 104, 105-p2, 108) |
| `sub_matches` is the audit trail *and* the input to verdict derivation — one structure, two questions | 79's 806-line coupling | **yes** — code, plus the durable memory, where it is 1 of 2 instances |
| A green row can be green for the wrong reason | 88 (100%) | **yes** — durable memory, now 4 instances |
| In-band sentinels are forgeable by the input | 98 chunk 1 (unscored, cause `N`) | **yes** — fix, 3 regression tests, durable memory |
| The metric and `git status` cannot see `.claude/` | 88, 89 (both 100%) | **yes** — durable memory, and the caveat in §11 of this document |
| Eligibility is destroyed by whoever *measures* first — lock the estimate at filing time | 98, 99 | **yes** — protocol change, cited in `108-prereg.md` |
| Score the ticket's own work, not the commit | 10 (45.8%) | **partial** — 100 and 104 split a shared commit; the diff basis is still the commit |
| "Leak level predicts recall" | 18 (52%) | **retracted** — `CORRECTION TO FINDING 21` |
| Every large under-scope is a new module or a control-flow relocation; ask for the *shape* of the change, not a file list | 03, 44, 79 pooled | **no** — absent from all six later pre-registrations |
| The two-estimate protocol: raw vs informed, and the 2×2 | Arnon's decision, 2026-08-21 | **no — decided, never executed once**; no item carries a paired raw and informed estimate |
| "The residue is wherever the previous instrument was not pointed" | 80 (56%) | **no** — restated four times for `--ambient`; a fifth instance (`pwd.getpwnam`) is open in `DECISIONS-PENDING.md` |
| Prose coupling `P`, five consecutive items | 77, 78, 79, 05, 03 | **no** — documentation was excluded from the metric instead |

### The split, which is the finding

It is not outliers versus the rest. It is **findings about the code versus findings about the process.**

- **Code and architecture findings: 4 of 4 adopted.** One of them came from the single worst-scoring item, and was located precisely *because* 79% of that diff traced back to one coupling.
- **Process and instrument findings: 1 adopted, 1 partial, 1 retracted, 3 dead** — including the two the experiment itself nominated as its best output.

Findings with a code owner and a commit-shaped ending were acted on without exception. Findings about how to work next time died at roughly the same rate, and died the same way each time: written down, restated on later items, never encoded anywhere a later run would load them. That is the red-green-refactor truncation applied to the experiment's own retrospectives. `--ambient` is the cleanest case — four confirmations of a known blind spot, no change to the instrument, and a fifth instance now waiting.

### Yield per outlier, against the stated bar

Six items scored at or below 72%. Their retrospectives produced: **two corrective actions** (79, both substantive), **one partial** (10), **one refutation** — 18's leak-level hypothesis examined and found not to hold, which is the *"it's actually ok"* outcome — and **three cases of something real that was identified and then not acted on** (80, 03, 44).

Arnon, 2026-08-24: *"even if you end up with around 50% of the outlier reviews yielding corrective action — you have yourself a pretty damn good signal that would not get ignored. It is perfectly normal that some of the reviews yield 'it's actually ok' and that some yield 'there's something there, but for whatever reason we chose not to act on it or to defer action.'"*

**On that bar the signal passes.** Every outlier produced at least one named conclusion; none produced noise; the worst-scoring item produced the two most valuable ones. The failure being measured in the table above is not the signal's — it is the absence of any mechanism that carries a process conclusion into the next run.

### What weakens this attribution

- **Pooled conclusions are not per-item attributions.** For 79 the causation is direct: the report's own reasoning starts from the line count. For 03, 44 and 80 the individual score triggered a look, but the conclusion came from pooling across items, so the score cannot be credited alone.
- **The estimator named the largest miss and then predicted against it.** Item 79's uncertainties file identified the exact file governing 79% of the diff and explained why it could not resolve the question. The whole first row of the table exists because of that near-miss, not because the score revealed something unknown.
- **The population is unrepresentative**, for the reason recorded in `CONSOLIDATED-REPORT.md`: almost every ticket here was agent-authored mid-campaign, and that batch predicts its own scope well for reasons that have nothing to do with foresight.

### Disposition — Arnon, 2026-08-24

**The experiment continues. This is an intermediate reading, and nothing here is a conclusion.**

> *"The experiment is far from over and needs to continue under the normal human-in-the-loop development process before we can conclude anything. This intermediate analysis tells me 'so far so good — we don't want to abandon the experiment.'"*

That matches the standing decision recorded in `CONSOLIDATED-REPORT.md` on 2026-08-21: **run until at least 20 human-authored tickets have been completed through the normal process** — plan first, reviewed and discussed, then implement — scoring production files only. None of those 20 exist yet, and the weaknesses listed just above are all properties of the batch this analysis had available, not of the instrument.

**The economics under which it is being judged are explicit and are not per-experiment.** TOO-45 abandoned several candidate signals; that is the expected outcome of a search, and the search is scored on the handful that survive, not on the ones that do not. So the question this document must keep answering is *did a signal produce durable practice* — not *did this experiment pay for itself*.

---

# 8. The corpus itself

**MEASURED-HERE**, `find` and `git ls-files` over `toolguard-memories/` on 2026-08-23.

| quantity | value |
|---|---|
| files | **750** |
| `.md` files | **692** |
| total bytes | **9,893,979** |
| git-tracked | **222 (29.6%)** |
| untracked | **528 (70.4%)** |

### By directory

| directory | files | bytes | tracked |
|---|---|---|---|
| **TOO-45/** | **501** | **7,168,293** | 75 (15%) |
| implementation/ | 131 | 942,042 | 53 |
| TOO-19/ | 60 | 689,669 | — |
| DURABLE/ | 18 | 653,390 | **0** |
| TOO-15/ | 9 | 155,842 | — |
| everything else | 31 | ~284,743 | — |

**TOO-45 is 67% of the files and 72% of the bytes of the entire project memory**, and **only 15% of it ever entered git** — which is the whole reason a deletion triage was needed.

### Inside TOO-45/

| subdirectory | files |
|---|---|
| (top level) | 100 |
| reports/ | 108 |
| reports/surprise/ | 110 |
| proposed-tickets/ | 78 |
| reports/img/ | 46 |
| proposed-tickets/resolved/ | 31 |
| measurements/ | 10 |
| spikes/ (A, B, C) | 13 |
| resolved/ | 4 |
| tools/ | 1 |

443 `.md`, 58 non-`.md`. The 46 files under `reports/img/` are 21 `png`, 12 `puml`, 5 `mmd`, 4 `dot`, 4 `svg`.

### Cost-data coverage

**MEASURED-SOURCE**, `02-campaign-cost-data.md`, whose own scope statement is itself a corpus statistic: 685 `.md` files searched, **179** carrying a cost/elapsed/token heading, **43** more carrying a figure with no heading, **222** candidates opened, **152** cited as the source of a row, **170** rows extracted. That document also records that an earlier triage put the figure at **9** — an error of more than an order of magnitude, corrected twice (to 104, then to 152/179).

Coverage gaps it measured: **29%** of blinded review rounds carry no cost figure, **83%** of scored items, and **97% of proposed tickets** — the last being the population every scheduling decision was made from.

---

# 9. Agent activity

## Reports in the corpus

**MEASURED-HERE:**

- 57 files under `TOO-45/` whose name contains *implementation report* or *coder report*.
- 47 files under `TOO-45/` whose name contains *task recall*.
- 131 files under `implementation/`, of which **84** name TOO-45.

These are a **lower bound on agent runs**, not a count: an agent that produced no report leaves no file, and several rounds are known to have run without one.

## What the hook itself recorded

**MEASURED-HERE**, from `logs/toolguard-2026-08-*.md` — the campaign's own permission hook, governing the agent that did the work.

| quantity | value |
|---|---|
| entries, all of August 2026 | **61,946** |
| entries in the campaign window (08-04 → 08-23) | **58,287** |
| `EXECUTED` | 60,765 |
| `ASK` | **196** |
| `REFUSED` | 140 |
| entries with no parseable `Status` line | 845 |
| `Agent: main` | **61,178 — 100%** |
| permission mode `auto` | 56,065 (90.5%) |
| permission mode `default` | 5,053 |
| `acceptEdits` / `plan` | 3 / 1 |

Busiest logging days: 08-11 (7,314), 08-12 (6,607), 08-21 (5,859), 08-20 (4,982), 08-13 (4,581). **No log file exists for 08-15 through 08-18** — the same four-day hole as the commit history.

**Arnon was consulted on 0.3% of tool calls** (196 asks in 61,946 decisions), and 90.5% of the campaign ran in `auto` permission mode. This is the strongest single number on how the work was actually supervised.

**Agent attribution is uniformly `main`.** Every one of 61,178 entries. Subagent identification is a known-broken feature, so **the logs cannot be used to count subagent runs at all** — see §11.

---

# 10. Findings that contradict the campaign's own account of itself

Ordered by how much they change the story.

### 1. The drain curve's floor is attested by one number with no file behind it

**MEASURED-HERE.** All 27 `review-<n>-round<k>.md` files report at least one blocking finding. The one zero on record — ticket 45, round 5 — has no file behind it. The round-curve control's central claim, that a healthy curve *drains*, is well attested in its descent and rests at its floor on a terminal zero that cannot be checked, plus a table for ticket 44 that the three surviving files contradict (1 → 4 → 1 against the table's 4 → 3 → 1).

**An earlier version of this entry was headed "Every surviving blinded review round failed", and that framing was wrong** — corrected 2026-08-24 after Arnon challenged it. A round returning blocking findings is a round working; a `FAIL` verdict is its output, not its verdict on itself. Nothing here contradicts the campaign's account of review; the checkable gap is only about the floor of the curve and about ticket 44's two irreconcilable series.

### 2. More lines were written to measure the product than to change it

**MEASURED-HERE.** The product package received 15,118 insertions. The six new dev instruments plus their four test modules received **21,093** — 39% more. Adding the verdict corpus, **38.6% of every non-memory line inserted on this branch is measuring apparatus, its tests, or its fixtures.** The taxonomy's "bug hunt in the instruments" reading was refuted on ticket counts and is close to true on line counts; nobody in the corpus states both.

**The number is a measurement, not a verdict, and the verdict is Arnon's.** Recorded 2026-08-24: *"we've abandoned plenty of experiments in TOO-45 in search of good signals. And it's fine. A search for signals needs to uncover only a small handful of good ones. The experiments are not expensive in my book if some are successful. Yes it costs a lot of lines of code, as you observed. But we are uncovering process changes and signals with long-term value. For me — that's success."* **So 38.6% is the price of a signal search, entered deliberately**, and the thing to judge it against is the yield of durable practice — not the ratio itself. Where an instrument does turn out to be dead, the cost that matters is its ongoing one: `intermediate/rejected-methods-and-metrics.md` names two abandoned tools carrying **300 tests** that must keep passing for code nobody runs, and recommends removal. Abandoning cleanly is the discipline this figure calls for; spending less on the search is not.

### 3. The diagrams the review called load-bearing were never drawn again

**MEASURED-HERE.** All 46 diagram artifacts under `reports/img/` share one mtime day, **2026-08-06**, and arrived in one commit, `152515f`. Arnon's review conclusions the next day say *"issues were often noticed from the diagrams before the text… diagrams are load-bearing here, not decoration"* and record a standing preference for Mermaid. **Zero diagram files were added in the following 17 days**, during which tickets 34–108 were filed and the campaign's hardest work was done. The practice was endorsed and then abandoned in the same week, and no document notices.

### 4. The product barely grew; the test suite nearly doubled

**MEASURED-HERE.** `toolguard/` went from 38,257 to 40,037 lines — **+4.7%** — on 15,118 insertions and 13,282 deletions. The suite went from 2,186 to 4,008 tests — **+83.3%** — with 895 of them in a single commit. A campaign filed as an *architecture overhaul* is, by line accounting, a test and instrumentation campaign that rewrote a third of the package in place without growing it.

### 5. Zero tickets came from a user

**MEASURED-SOURCE, corrected.** Two of 76 primary tickets originate from something going wrong, and both happened to this repository's own agent. The original row was labelled "field evidence"; the 2026-08-23 correction notes that per the project's own evidence rule, dogfood is the corpus that counts least. **74 of 76 defects were manufactured by looking.** Set against the finding that only one ticket in seventy-six had mass real exposure, this is the campaign's most uncomfortable pair of numbers.

### 6. Mutation's yield is stated two ways, four-fold apart

**DISPUTED.** The methodology note says *"roughly fifty production defect tickets… from mutations alone"*; the taxonomy attributes **18 of 76**. They reconcile only if nearly all 29 `resolved/` subjects were also mutation-found, which nobody checked, because `resolved/` was never classified. The larger figure is the one that circulates.

### 7. "The most expensive item of the campaign" was joint-fourth

**Already adjudicated in the corpus, and the retraction did not propagate.** Ticket 79 was called the campaign's most expensive item on the strength of 11 agent runs and ~3M subagent tokens; by measured wall-clock it is **4h15m — below the phase-3 average and less than half of ticket 78's 8h51m**. Six documents state the pre-correction sentence flatly. Its agent-run count is itself stated three incompatible ways — **7 runs / ~1.8M tokens**, **9 / ~2.6M**, **11 / ~3M** — most likely three points in time on a still-running ticket, but nothing in the six later documents says so.

### 8. The consolidated report's own item count does not match its own table

**MEASURED-HERE.** `CONSOLIDATED-REPORT.md` is headed *"Results — 15 items scored"* and its table lists **13** rows. The directory holds **29** scored files covering **25** distinct tickets. The report was written before the last batch and never restated; `CONSOLIDATED-BATCH-2.md` covers the remainder separately, so no single document states the series size.

### 9. The index that exists to prevent staleness went 43 tickets stale

**MEASURED-SOURCE**, and the file says it about itself: *"This index was 43 tickets stale, which is the defect it exists to prevent."* It stops at ticket 84; tickets 85–108 were filed after it and never added. The taxonomy then repeated the same failure at a larger scale — deriving outcome from ticket text that 08-21/08-22/08-23 commits had already invalidated, four minutes after the last one landed.

### 10. Ticket 17 is cited constantly and does not exist

**REFUTED 2026-08-24 — this measurement was wrong, and its scope is why.** Four numbers — 11, 16, 17, 57 — were reported as referenced in the index with no file anywhere in the corpus. **All four exist in `TOO-45/resolved/`**, a sibling of the `proposed-tickets/` directory that was searched. The original sentence follows, struck through, because what it says about ticket 17 remains interesting once relocated: ~~ Ticket 17 (`[native]` end-anchor under-match — deny rules that do not fire) is quoted as a peer of 18 and 19 throughout, was pre-registered for the touch-set series, was measured at **zero** log occurrences in the re-triage, and has no ticket document. It is the only *matcher* ticket in that state.

---

# 11. What could NOT be counted, and why

An honest account of the limits is part of the deliverable. Each item below blocked a statistic somebody would reasonably want.

### File mtimes are not authoring dates

**MEASURED-HERE.** Across 692 `.md` files there are only 479 distinct minute-stamps, and the distribution is visibly bulk-reset: **69 files share the exact minute 2026-08-03 09:56**, and **49 share 2026-08-19 11:29**. Whole directories moved at once (a basic-memory sync, a reorganisation). No per-file timeline can be built from mtimes, and any "when was this written" question about an untracked note is unanswerable — which is most of the corpus, since 70% of it never entered git.

### Subagent runs are unattributable

**MEASURED-HERE.** All 61,178 hook-log entries carrying an `Agent` field say `main`. Subagent identification is a known-broken feature of this setup, so the campaign's total agent-run count, the implementer/reviewer split, and any per-agent command profile are all uncomputable from the logs. The 57 implementation reports and 47 task recalls in `TOO-45/` are a floor, not a count.

### Elapsed time is mostly self-reported, and four sources disclaim their own clocks

`02-campaign-cost-data.md` records that only the ten phase-3 items timed from **git commit timestamps** (C-1 through C-10) form a cross-comparable series. Everything else is a session's self-report. Four files explicitly retract their own timings — one says its progress notes *"were fabricated and are wrong by about eight hours"*; another says *"a `date` check partway through showed a different timezone"*. Several report per-phase timestamps were never captured and were reconstructed from message order or file mtimes, which §11.1 has just shown to be unusable.

### Tokens and dollars have no meter behind them

**No source in the corpus queried a billing or usage API.** Every dollar figure is a token-volume guess times a remembered price; every token count but one is a reconstruction. The single exception is ~161k tokens per mutation-repair agent, range 142k–197k, n=12. Nothing in this document sums them.

### Review rounds 1–3 of ticket 44 have no files

Only rounds 4, 5 and 6 survive, and they are prose-only reviews with a scope that excludes logic and design. Whether the punch-list's 12 → 3 → 4 → 3 → 1 curve describes a different series, or the same one renumbered, cannot be resolved from what remains. Ticket 78's round 1 and ticket 80's rounds 1–2 similarly carry no headline count.

### `.claude/` is invisible to every measurement here

It is a symlink into `~/projects/dot_files`, so edits to rule and skill files do not appear in this repo's history or in `git status`. The surprise series noticed this at tickets 88 and 89 — for 89 the edited skill file was *the ticket's named root cause* — and concluded that **every earlier ticket touching a rule or skill file has the same silent under-count**. Every file and line figure in §1 and §3 is a lower bound for that reason.

### The `resolved/` tier was never classified

29 ticket subjects — the ones that were actually fixed — sit outside every distribution in §5. The taxonomy declares this and its consequence: the classified corpus is biased toward what stayed open. It is also why the mutation-yield dispute in §10.6 cannot be settled.

### The subject axis has no ticket lists

Alone among the taxonomy's four axes, the subject table publishes counts with no membership. The verification could check its arithmetic and nothing else, and the campaign's single most-quoted interpretive claim rests on it. Treat every row in that table as unverifiable.

### The corpus was in motion while it was being counted

`02-campaign-cost-data.md` counted 685 `.md` files; I count 692 today. Three documents in `DURABLE/intermediate/` were rewritten on 2026-08-23 with corrections, and two ticket files acquired `# CLOSED 2026-08-23` sections in the same minute the taxonomy was written — so the verification could not tell a misreading from a race. **Every count in this document is a snapshot dated 2026-08-23 of a tree that was still being edited.**

### What a commit subject proves

Matching `Item N` in a commit subject to ticket N establishes that work landed under that name. It does not establish that the ticket is closed, that no residual remains, or that the commit contains only that ticket's work — item 10's commit is the worked counter-example, where **608 of 620 unpredicted lines belong to three bodies of work the ticket does not contain**. The 42 in §4 should be read as *tickets with a named commit*, never as *tickets fixed*.
