---
title: VERIFIED-rejected-methods
type: note
permalink: toolguard/durable/intermediate/verified-rejected-methods
tags: [TOO-45, DURABLE, verification]
---

# Adversarial verification of `rejected-methods-and-metrics.md`

**Target**: `toolguard-memories/DURABLE/intermediate/rejected-methods-and-metrics.md` (369 lines, 64 KB).
**Protocol**: `toolguard-memories/DURABLE/VERIFICATION-PROTOCOL.md`. Stance: refute.
**Verifier**: not the author. **Date**: 2026-08-23.

**Claims checked: 74.** Of those — **4 REFUTED**, **5 TRUE BUT MISLEADING**, **65 CONFIRMED**, **0 UNVERIFIABLE**.

**Overall**: the document's *catalogue* is unusually accurate. Every number I could re-measure independently reproduced, every Arnon quote is verbatim, and every repo claim about what exists or does not exist checks out against the working tree and against `git log --oneline master..too-45` (78 commits — the brief's figure, confirmed). **The failures are concentrated in the parts where the document argues with its own sources**, which is exactly where the brief predicted they would be, and one of them is the same defect the sister document found in `defect-taxonomy.md`: a conclusion derived from note text while git history says otherwise.

---

## LEAD WITH THE FAILURES

### F1 — REFUTED. The aggregate-metrics DISAGREEMENT rests on a premise the document itself disproves three sections later

**The claim** (line 46): *"No other aggregate architecture metric was tracked over time during TOO-45, so 'like any other aggregate architecture metric ... useless even as a directional measure' is not backed by a measurement of any other aggregate."*

**This is false, and the document is its own counter-example.** `reports/retrospective.md` §3.1 is a before/after table of aggregate architecture metrics taken across TOO-45 (`master 532de02` → `branch a3e3f27`), and the document reproduces four of its rows in section A2:

| aggregate | tracked over TOO-45 | what the campaign concluded |
|---|---|---|
| 100%-coupled co-change pairs | 71 → 134 (+89%) | **anti-directional** — rose 89% while the architecture demonstrably improved |
| max co-change partners | `config.py` 68 → 71 | *"cannot discriminate anything"*; retrospective §9.4: *"is noise"*; recommendation 4: **retire as a headline number** |
| % logical changes confined to one zone | 40.0 → 36.4 | moved for a **purely arithmetic** reason (9pp resolution at N=11) |
| M1 role-ratio / M2 touch-set rate (A6) | scored across two trees | **proven biased by Monte Carlo**, 3,000 draws per cell — both preferred the less-factored tree |

Three of those four are aggregates that were measured directionally and found directionally useless — which is precisely the measurement the disagreement says was never taken. `dependencies-before-after.md` adds a further before/after aggregate table (layer violations 3→1, import cycles 2→1, longest chain 12→11, import edges 166→173).

**Verdict: REFUTED.** The objection does not survive its own document. Note the shape: an unverified universal negative ("no other X was ever…") deployed to complain about an unverified universal. **This is the trap the brief warned about, and the document walked into it.**

*(A fair residual: two of those aggregates — import cycles and longest dependency chain — did track direction correctly, so Arnon's position is not proven exhaustively either. That is a real caveat, and it is not the one the document made.)*

---

### F2 — REFUTED / MISATTRIBUTED. The same DISAGREEMENT manufactures the universal it objects to, by truncating the quote

The document quotes Arnon **correctly and verbatim at line 38** (confirmed against `reports/pyscn-2026-08-22-disposition.md:88`):

> *"pyscn health score - like any other aggregate 'architecture metric' **we discussed** - it is pretty useless, even as a directional measure."*

Eight lines later, the disagreement **re-quotes it with the scoping clause removed**:

> *"like any other aggregate architecture metric ... useless even as a directional measure"*

The ellipsis eats `'` … `we discussed`. **"Any other aggregate we discussed" is a bounded claim over a set the campaign actually measured** (the four in F1). **"Any other aggregate architecture metric" is an unbounded universal.** The document then objects to the unbounded version — a claim Arnon did not make.

Per the protocol's rule 5 ("every claim about what the user decided"): the verbatim quote at line 38 is CONFIRMED; the re-quote at line 46 is **MISATTRIBUTED**, and it is load-bearing, because it is the entire basis of the disagreement.

**Action**: delete the DISAGREEMENT block at line 46. The A1 entry above it is excellent and needs no hedge.

---

### F3 — REFUTED. Class (c)'s `test/`-tier row says the sweep stopped; git says it shipped the same afternoon

**The claim** (line 340): *"the `test/` tier of the comment sweep — **stopped on budget**: the weekly limit was at 88% with ~2,780 requests left and a burn rate of ~342/hour, 100% of it this sweep."*

Every number is verbatim from `TOO-45 punch-list 07 work queue.md:149-158`. **The problem is that the cited block is explicitly labelled "Earlier:" and is superseded twice inside the same file, and by git.**

| evidence | says |
|---|---|
| work queue :72 (`08-12 09:50`) | **"resumed"** — 40 minutes after the pause |
| work queue :117 | *"Earlier extrapolation of ~342 req/hour came from a 24h average… The two-agent marginal rate looks closer to **~165/hour**, which roughly doubles what the remaining budget buys. **Refine it from this table, not from the 24h counter.**"* |
| work queue :112 | *"**The tier can probably finish inside this budget**, which the 24h-average extrapolation said was impossible."* |
| work queue "EXACT remaining list, measured 2026-08-12 ~13:15" | *"two big files and one batch of small ones, and `test/` is done"* |
| `git show --stat 7460ffb` (2026-08-12 **13:11**) | **86 `test/` files** swept, alongside 72 `toolguard/` files |
| `git show 549abc3` (2026-08-21) | a later `test/`-tier pass: **"seven tests that could not tell success from failing open"** — real findings |

**Verdict: REFUTED.** The tier was paused on budget, resumed the same morning, and committed. The document quotes a superseded burn rate as `[MEASURED]` and reports a pause as an abandonment.

**This is the sister document's failure mode reproduced exactly**: a conclusion read off note prose, with the git history that contradicts it two commands away.

**Second-order damage**: the row also drops the source's own qualifier — *"its output is cannot-fail assertions and undetected mechanisms. **Real value**, but not worth the week's remaining budget."* Read alongside B5 in the same document (mutating those same test files found 16, 13, 11, 5 and 6 zero-detection mechanisms), the surviving row invites exactly the inference the brief feared: *`test/` is low value*. The document keeps the two activities technically apart — B5 is mutation, the (c) row is comment-reading — but nothing in the (c) row tells a future reader that.

**Action**: rewrite the row as *"paused on budget mid-morning 2026-08-12, resumed the same day and completed (`7460ffb`); comment-reading yield in `test/` was zero product defects, unlike mutating the same files (see B5)."*

---

### F4 — REFUTED. `[MEASURED] ~90 tests` re-measures to 300

**The claim** (A9, line 158): the two rejected measurement tools *"carry roughly **90 tests** that must keep passing forever for tools nobody runs. `[MEASURED]` — `proposed-tickets/06-...md`"*.

The citation is faithful — ticket 06:20 says "roughly 90 tests". **The number does not reproduce:**

```
uv run python -m unittest ... test_change_role_classifier.py   -> Ran 131 tests, OK
uv run python -m unittest ... test_touch_set*.py               -> Ran 169 tests, OK
                                                                  = 300
```

Also: ticket 06 says "three tools and **four** test files"; `git ls-files` shows **three** test files. The error originates in the cited source, but the document stamps it `[MEASURED]` and passes it on unexamined — the protocol's **transitive citation** case. The argument gets *stronger* with the real number (300 tests, not 90), so nothing turns on it except the document's reliability.

---

### F5 — TRUE BUT MISLEADING. The co-change DISAGREEMENT's `min_obs = 4` analogy does not transfer

Facts CONFIRMED: 18/20 vs 14/20 (`retrospective.md` §3.4), same before/after tree pair, none of the four controls run, per-file degeneracy (`hook.py` 8.0/8, `config.py` 7.0/7, §3.6).

The framing — *"That is fitting a fix to the instance that motivated it, which is the `min_obs = 4` trap's own shape one level up"* — **misdescribes the mechanism**. The `min_obs` trap is a **free tunable parameter** whose neighbouring values invert violently (5 → +136%, 6 → +1300%); the instability *is* the diagnosis. `1/(n−1)` size-weighting has **no free parameter** to be unstable at — it is fixed by the mining-software-repositories literature, and its arithmetic is stated and checkable in §3.4 (`1/22 = 0.045` per pair, every untouched pair unchanged to three decimals).

The document also omits `retrospective.md` §3.5, which gives size-weighting an **independent gaming-resistance argument** the disagreement's *"one favourable reading"* verdict does not acknowledge: *"You cannot reduce a pair's weight by splitting your commits… the one way to dilute a pair — padding a change with unrelated files — is self-defeating and visible in review."* Reasoned, not run — so "no control was run" stands — but it is not "one reading" either.

**Action**: keep *"a proposal with one favourable measurement, not a validated instrument"*. Delete the `min_obs` comparison.

---

### F6 — TRUE BUT MISLEADING. The four-control gate is over-extended past its stated scope

The disagreement says the campaign *"wrote down the four controls this should have to clear — positive, negative, neutrality, game-resistance"* and that none was run on size-weighting.

`reports/canary-before-after.md` §4.3 is scoped to **the change-cost canary's replacement**, and it labels its own controls asymmetrically: *"Controls 1 and 2 together are the general form… **Controls 3 and 4 are the domain-specific hazards this ticket discovered**… they generalise to any codebase where a refactor changes *how* a value is carried rather than *whether* it is."* Neutrality's test case is a tuple→dataclass conversion; game-resistance's is renaming the enrichment field. Neither has a co-change analogue.

So "four controls it should have to clear" is **two general controls plus two the source itself scoped elsewhere.** Literally accurate about what §4.3 lists; misleading about what §4.3 requires.

---

### F7 — TRUE BUT MISLEADING. The guard-canary DISAGREEMENT rebuts a retirement nobody proposed

Everything substantive in the B1 disagreement is CONFIRMED (see D3 below). The framing is not.

It says: *"Retiring it because the retrospective's summary reads as a condemnation would remove the only check on a silent, permission-widening failure."* **No source proposes retiring the guard canaries.** `retrospective.md` §4.7 already lands where the disagreement wants it to land: *"The inverted-test **pattern** is still sound — it correctly demonstrated the detection mechanism — but the instance demonstrated it against a binary that was not under change. **Read every `--guard PASS 12/12` in the ticket record accordingly: it says the shipped release is intact, not that the refactor is.**"*

The retrospective's *heading* ("Two practices whose reputation exceeds the evidence") and its flat *"the 12 guard canaries themselves did not work"* do read as condemnation, so the disagreement is not inventing a tension — it is inflating a difference in emphasis into a disputed verdict. The reclassification to class (b) is right and worth keeping; the "would remove the only check" hypothetical should go.

---

### F8 / F9 — minor, recorded for completeness

- **F8 (TRUE BUT MISLEADING, minor)**: B1's *"fifteen stages"* is verbatim from `retrospective.md` §5.1, but `canary-before-after.md` §1.3 says *"**Sixteen** step reports"* and then **lists seventeen**. The document picked one source silently. Three numbers, one fact; say "every recorded step" and drop the count.
- **F9 (TRUE BUT MISLEADING, minor)**: A1's *"**71** at the end"* is verbatim from a source written 2026-08-22 ("is 71 now"). Re-measured today across all 88 archived reports, the last whole-package reading is **72** (2026-08-22); 71 is a 2026-08-21 reading. Inside the noise band the entry itself declares, so harmless — but it is a stale "end" in a document that will outlive the archive.

---

## The four disagreements — direct verdicts

| # | the document's position | verdict |
|---|---|---|
| **D1** | The aggregate-metrics rejection is over-generalised; no other aggregate was tracked over time | **THE REPORT IS WRONG.** Premise false (F1) and quote mis-truncated (F2). At least four other aggregates were tracked across TOO-45, three of them catalogued in this very document, all three found directionally useless. **The objection collapses. Delete it.** |
| **D2** | The size-weighting replacement fails the campaign's own instrument gate | **STANDS ON ITS FACTS, OVER-REACHES IN ITS FRAMING.** 18/20 vs 14/20 ✔, same before/after pair ✔, controls not run ✔, per-file degeneracy ✔. But the `min_obs` analogy is mechanically wrong (F5) and the four-control gate is over-extended (F6). **Keep the caution, cut the two rhetorical moves.** |
| **D3** | The 12 guard canaries are class (b), not (a), and retiring them would be wrong; the real defect is two instruments sharing the word "canary" | **THE REPORT IS RIGHT — this is its best contribution.** Both apparently-contradictory claims are true **of different things**, exactly as it says: *sensitivity to the TOO-45 refactor* is 0/12 (measured, both binaries, all twelve `SAME`), while *sensitivity to the live rule files* was proven in both directions by the inverted test (`canary mismatch: Bash 'git clean -fdx' expected 'allow', got 'deny'`). `canary-before-after.md` Part 5 states the naming diagnosis outright: *"the appearance of redundancy comes entirely from the shared word 'canary'."* Both rule files outside the repo ✔ (one a dotfiles symlink, one in no repo); `no_match_fallback = "allow_with_no_warnings"` ✔ at `.claude/toolguard_hook.toml:4`; a lost deny silently widening permission ✔. **Do not retire the guard canaries.** Only the "retirement" framing needs cutting (F7). |
| **D4** | *"`test/` tier is low value" conflates comment-reading with mutating test files* | **THIS DISAGREEMENT DOES NOT EXIST IN THE DOCUMENT.** There are exactly three `DISAGREEMENT` blocks (lines 46, 68, 221). The `test/` tier appears only as a bare class (c) table row with no disagreement attached — and **that row is itself REFUTED** (F3): it reports a resumed-and-completed sweep as stopped, and quotes a burn rate its own source supersedes. The conflation the brief describes is a real hazard, and the document does *not* guard against it. B5's mutation numbers are separately CONFIRMED verbatim (16 / 13-of-25 / 11-of-22 / 4+16 / 5 / 6, six modules, `DECISIONS-PENDING.md:292-299`). |

---

## Full claim-by-claim table

Re-measured independently where marked ✱.

| # | claim | verdict |
|---|---|---|
| 1 | pyscn health 61–73 across 86 archived reports | **CONFIRMED** ✱ — 88 reports today; all whole-package readings fall 61–73; three 92/93 outliers are single-file runs (`compound.py`), not package runs |
| 2 | 73 at campaign start (2026-08-13) | **CONFIRMED** ✱ — 72 of 88 reports read exactly 73; all 08-13/08-14 readings are 73 |
| 3 | 71 at the end | **TRUE BUT MISLEADING** — F9 |
| 4 | single day spans 61 to 72 | **CONFIRMED** ✱ — 2026-08-20: 61, 63, 65, 66, 67, 67, 68, 72 |
| 5 | 213 of 951 functions (22%), 49 of 79 files | **CONFIRMED** — disposition :29-32 |
| 6 | per-file subsets (config 19/58, extractor 15/48, maintenance 8/33, compound 8/21) | **CONFIRMED** |
| 7 | `bash_parser.py` (182 generated functions) absent entirely | **CONFIRMED** — disposition :45, :53 |
| 8 | 100/100 Grade A on a file pyscn failed to parse | **CONFIRMED** — ticket 66 :38-41 |
| 9 | cause was a three-name bare `except` | **CONFIRMED** — ticket 66 :45; ✱ no such clause survives in `toolguard/` or `tools/` today |
| 10 | Arnon's pyscn quote verbatim, 2026-08-23 | **CONFIRMED** — `pyscn-2026-08-22-disposition.md:88`, under a heading dated 2026-08-23 |
| 11 | the same quote re-used inside the disagreement | **MISATTRIBUTED** — F2 |
| 12 | `judge_unit` 20 vs `node_kind` 15, same number opposite conclusions | **CONFIRMED** |
| 13 | `.pyscn.toml` excludes `**/test_*.py`, so no pyscn guard covers tests | **CONFIRMED** ✱ — `.pyscn.toml:126`; replacement is AST-based (`test/unit/test_static_analysis_coverage.py`) |
| 14 | "no other aggregate tracked over time" | **REFUTED** — F1 |
| 15 | *"three ordered points looked like a law…"* citation | **CONFIRMED** — `CONSOLIDATED-REPORT.md:42` verbatim |
| 16 | co-change 100%-coupled pairs 71 → 134 (+89%) | **CONFIRMED** — retrospective §3.1 |
| 17 | 2,387 tests OK across the same reading | **CONFIRMED** — §3.1 `[EXEC]` |
| 18 | mechanism pinned to **63 of 63** pairs; min-touch exactly 2 → 3; co_changes 2 → 3; 0 lost | **CONFIRMED** — §3.2, all four figures |
| 19 | reported when `co == min(touch)` and `min(touch) >= 3`; a coincidence filter | **CONFIRMED** ✱ — `MIN_COUPLING_OBSERVATIONS = 3`, `tools/architecture_fitness.py:2887` |
| 20 | per-commit 39 → 42 (+7.7%); 43→46 changes; 12-fold sensitivity gap | **CONFIRMED** — §3.3 |
| 21 | TOO-45 squash-merged, so ticket grouping buys nothing and costs 7x sample | **CONFIRMED** — §3.3 |
| 22 | `min_obs` 4 → +5.1%, 5 → +136%, 6 → +1300% | **CONFIRMED** — §3.4 |
| 23 | exclude-by-label is a complete fix and a bad one; same shape as the `.pyscn.toml` relabel | **CONFIRMED** — §3.5 |
| 24 | max co-change partners unsalvageable; `config.py` 71 of ~67 modules | **CONFIRMED** — §3.6 |
| 25 | % confined to one zone 40.0 → 36.4; 9pp resolution at N=11 | **CONFIRMED** — §3.6 |
| 26 | co-change was the only instrument to see the `config -> engine` inversion (6 observations) | **CONFIRMED** — §9.4, §9.5 |
| 27 | size-weighting: top-20 overlap 18/20 vs 14/20 | **CONFIRMED** — §3.4 |
| 28 | …measured on the same before/after pair that revealed the defect | **CONFIRMED** — §3.1 defines the pair; §3.4 uses it |
| 29 | four controls written down and none run on size-weighting | **TRUE BUT MISLEADING** — F6 |
| 30 | *"the `min_obs = 4` trap's own shape one level up"* | **TRUE BUT MISLEADING** — F5 |
| 31 | weighting degenerates per-file: `hook.py` 8.0/8, `config.py` 7.0/7 | **CONFIRMED** — §3.6 |
| 32 | ticket 18 replay: "zero flips across 53,112 logged decisions" | **CONFIRMED** — `replay-instrument-blind-spot.md:24` |
| 33 | **measured** instance, not hypothetical: `Bash(\obsidian search:context *)`, 5 real occurrences in `logs/` | **CONFIRMED** — same line, stated as *"Measured instance, not hypothetical"* |
| 34 | fallback scope: featherhill 0/3,675; toolguard 9,848/51,918 (19%); instagram 0/28 | **CONFIRMED** — :63-65 |
| 35 | ticket 78 compared `matched_rule`: 26,530 × 2 trees, 0 changes | **CONFIRMED** — :30 |
| 36 | Arnon's re-scoring preference, verbatim | **CONFIRMED** |
| 37 | three measured instances of "clean corpus ≠ no regression" (18, 98 chunk 2, 101) | **CONFIRMED** |
| 38 | `test/unit/test_deny_penetrates_constructs.py`: denied command in all 17 constructs + benign control | **CONFIRMED** ✱ — 17 constructs in `_CONSTRUCTS`, control test present |
| 39 | enrichment footprint read 9 files on master, 9 on branch, 9 throughout | **CONFIRMED** — `canary-before-after.md` Part 3 / retrospective §5.2 |
| 40 | 13 bare verdict tuples removed; `log_command` 11–12 params → 4; `hook.py` 26 → 14 | **CONFIRMED** |
| 41 | occurrence count 53 → 72; 14 `compound.py` keyword args | **CONFIRMED** — §5.2 |
| 42 | `matched_pattern` named to dodge the detector, disclosed by its own author | **CONFIRMED** — §5.1 defect 6 |
| 43 | naive-agent "7 files after R3" unreconstructable and abandoned | **CONFIRMED** — §4.7, quote verbatim |
| 44 | the four controls exist at `canary-before-after.md` §4.3 | **CONFIRMED** |
| 45 | rename `hard_deny` = 106 tests; real change = 0 | **CONFIRMED** — §5.3 |
| 46 | 88 and 180 both resolved to zero net suite change | **CONFIRMED** |
| 47 | `subagent` 684 vs 1; `error_log` 798 vs 2,357 | **CONFIRMED** |
| 48 | monkeypatch makes modules unprobeable: 0 tests run, 1 collection error | **CONFIRMED** |
| 49 | low blast radius is not low risk | **CONFIRMED** — §5.3 verbatim |
| 50 | M1/M2 denominator trap; `surprises = L + n(1−p)` | **CONFIRMED** — `micro-canary-protocol.md:160-185` |
| 51 | Monte Carlo 3,000 draws/cell, n=1..12, p=1.0..0.4; 64.7% at p=0.8, 90.9% at p=0.5 | **CONFIRMED** — :185 |
| 52 | cost: four agents, no implementations; both passed their own hazard suites | **CONFIRMED** — :207-209 |
| 53 | surprise ratio: 05,15,04,01 by ratio vs 04,15,01,05 by recall; dropped 2026-08-09 | **CONFIRMED** — `surprise-factor-protocol.md:48` verbatim |
| 54 | cause `T` dropped (measures effort); cause `A` un-demoted by Arnon, quote verbatim | **CONFIRMED** — `RESULTS-LOG.md:129,139` |
| 55 | MR-08: violation-introducer rated *straightforward*, avoider rated *fiddly* | **CONFIRMED** — `canary-results.md:44,77` |
| 56 | the two tools "carry roughly 90 tests" `[MEASURED]` | **REFUTED** ✱ — F4, 300 |
| 57 | occurrence matching proven exact twice (82/82; 394 vs AST oracle) | **CONFIRMED** — ticket 06:24 |
| 58 | blindness guarantee audit-verified (170 opens, none outside tree) | **CONFIRMED** — ticket 06:25 |
| 59 | residual silent loss in 13 of 24 implementation styles | **CONFIRMED** — ticket 06:30 |
| 60 | keep/remove still open; swept in by `git add -A` | **CONFIRMED** ✱ — all six files still tracked |
| 61 | PLC2701: two runs, same file/line, opposite verdicts; only live surface is `test/` (69 hits) | **CONFIRMED** — retrospective §7.1 :420-429 |
| 62 | pydocstyle 11,010 findings; D212+D205+D415+D400+D413 = 10,744 (97.6%); D100–107 ≈ 150; ~3,965 autofixes | **CONFIRMED** — ruff proposal :194 |
| 63 | docstring ratio **proposed and never built** (no `docstring_ratio` symbol) | **CONFIRMED** ✱ — 0 occurrences in `tools/architecture_fitness.py` |
| 64 | `check_stdlib()` / `--stdlib` **do** exist at `architecture_fitness.py:4341-4396`; retrospective's open question 4 is stale | **CONFIRMED** ✱ — section header :4338, `def check_stdlib` :4348, `STDLIB_ALLOWED_ROOTS` present, pre-push checklist runs it |
| 65 | ticket-reference count deleted the IDs, left the prose, made the codebase worse | **CONFIRMED** — `TOO-45 comment standard.md:18` verbatim |
| 66 | guard canaries ran against `~/.local/bin/toolguard` v0.5.1, byte-identical to master | **CONFIRMED** — `canary-before-after.md` §1.2 |
| 67 | measured sensitivity to TOO-45: **0 of 12**, both binaries | **CONFIRMED** — §1.2 |
| 68 | quoted across "fifteen stages" | **TRUE BUT MISLEADING** — F8 (sources say 15 / 16 / list 17) |
| 69 | `INSTALLED COPY IS STALE` fired at SessionStart and was never connected | **CONFIRMED** — §5.1 defect 9 |
| 70 | guard canaries are class (b); the defect is two instruments sharing a name | **CONFIRMED** — Part 5: *"the appearance of redundancy comes entirely from the shared word 'canary'"* |
| 71 | …but "retiring it" rebuts a position no source holds | **TRUE BUT MISLEADING** — F7 |
| 72 | empty canary set returned `ok=True` / `--guard: PASS (no violations)`; empty tree passed R2/R3/R5/R6 | **CONFIRMED** — ticket 66 |
| 73 | **partially fixed in `05f786d`**; loosened map still invisible in production, closed only by a test pin | **CONFIRMED** ✱ — `05f786d` adds both the empty-tree guard (:160) and *"canary case set is empty: zero cases were evaluated"* (:242-248); `test/unit/test_architecture.py:382-534` is the only `LAYERS` pin |
| 74 | 46,481 runtime calls with zero import edges; 2.9M → 380k (−87%); static fan-in +1 | **CONFIRMED** — `dependencies-before-after.md:88`, `architecture-sweep-practices.md:23` |

**Additionally spot-checked and CONFIRMED** (folded into the counts above where they duplicate a row): `40 except OSError sites across 19 production files` (✱ re-measured 41 / 19 today — reproduces); `34 zero-detection mutants sharing the empty set` and `58% survival over 81 mutants` against a `3 of 5` summary line (`test-repair plan :321`); B5's six-module table verbatim (`DECISIONS-PENDING.md:292-299`); `file_lock`'s outer `os.close` — *"Recorded, judged not worth pinning"* verbatim (:145); duplication 45/100 at 15.9%/61 groups **and** 16.2%/62 groups (two dated readings, both cited files correct) and *"severity from a clone detector is not severity in this codebase's sense"* verbatim; the 21 high-risk complexity triage (`installer.py` ×5, `_scan_array_char` 23, `_find_array_close` 16, `_apply_to_file` 25, only `match_command` 22 and `match_pattern` 15 scheduled on merit); `judge_unit` landing at 8 with the `inline_code` branch (~145 lines) at 6 (`95-scored.md:36`); the anti-stall cron at ~25 of 210 turns / ~12% (`corrections-analysis.md:22,96`); rule 8's 2,586 tests and seven directed report agents (`canary-results.md:71,90`); rule 10's `allow` 2,336 : `ask` 34 : `allow_with_warning` 6 : `deny` 6 (`delta - as-is against ideal.md:343-346`); B6's full confound set (03 at 64.4%/12.0%, 18 at 0/7, 77 at 9/9 vs 80 at 5/9, 12 of 620, 11 of 39 modules, contamination items 05/19 and 20/39/57/64/70, 3 of 32 carrying 811 of 958 lines, 54 inert vs 32 missed, item 79's 79% binary uncertainty, item 85a's *"move"* and chunk C's repair) and Arnon's *"the estimator is not the objective here"* verbatim (`CONSOLIDATED-REPORT.md:145`); the judge backtest's eight live defects, 2 of 4, and *"the duplication there is an oracle, not drift"* verbatim.

---

## What this verification did NOT find

Worth stating, because a report that only lists failures reads as a demolition and this is not one:

- **No invented citation.** Every file path resolves and every cited line contains the claim.
- **No fabricated Arnon quote.** All five direct quotations are verbatim. The only quotation defect is the truncation in F2 — of a quote the document had already reproduced correctly.
- **No number failed to reproduce except F4 (90 → 300).** Four independent re-measurements (pyscn score range and per-day spread, `MIN_COUPLING_OBSERVATIONS`, `except OSError` census, `_CONSTRUCTS` count) all landed on the source's figure.
- **No stale "never built" claim except F3.** A11's docstring ratio really is absent; A12's `check_stdlib` really does exist and the document correctly flags the retrospective as stale on it; B2's `05f786d` partial fix is exactly as described. The document already did the git/repo check the sister document's target skipped — everywhere except the `test/` tier.

## Recommended edits, in priority order

1. **Delete the DISAGREEMENT block at line 46** (F1, F2). Keep A1 as written.
2. **Rewrite the class (c) `test/`-tier row** (F3) — paused and resumed and completed, with the `~165/hour` correction, and an explicit pointer to B5 so the comment-reading yield is not read as a verdict on the tier.
3. **Correct "roughly 90 tests" to 300** (F4), with the re-measurement, and note that the cited ticket is where the wrong number came from.
4. **Trim the line-68 disagreement** to its measured core; drop the `min_obs` analogy and the four-control gate (F5, F6).
5. **Trim the line-221 disagreement's** retirement hypothetical (F7); keep the class-(b) reclassification and the naming diagnosis, which is the document's single most useful contribution.
6. Replace "fifteen stages" with "every recorded step" (F8); drop "71 at the end" or date it (F9).
