---
title: rejected-methods-and-metrics
type: note
permalink: toolguard/durable/intermediate/rejected-methods-and-metrics
tags: [TOO-45, DURABLE, measurement]
---

# What TOO-45 measured and then threw away

Negative space for the "what worked" companion. Every entry names **what was tried**, **why it failed or misled**, **the evidence with its source**, and **what to use instead**. Citations are relative to the repo root and are live only until `toolguard-memories/TOO-45/` is deleted.

Three failure classes are kept apart throughout, because the notes conflate them and the consequences differ completely:

| class | meaning | consequence |
|---|---|---|
| **(a) invalid** | the instrument cannot measure what it claims, by construction | never use it for that purpose again; a "fixed" version needs re-proving from zero |
| **(b) misapplied** | the instrument is sound; the target, the harness or the reading was wrong | keep the instrument, fix the wiring, and add the control that would have caught it |
| **(c) not worth acting on** | the instrument is valid and cheap and the finding it produced did not earn work | keep running it; record the disposition so nobody re-derives the same triage |

**Labels below**: `[MEASURED]` = a number in the cited source, taken from something that ran. `[JUDGEMENT]` = an assessment, mine or the source's, with no number behind it.

---

## Class (a) — instruments that cannot measure what they claim

### A1. Aggregate "architecture health" scores — pyscn's grade specifically, and the general form by extension

**Tried**: `pyscn analyze toolguard/` reports a composite Health Score out of 100 with a letter grade over seven weighted dimensions. It was read as a project health number and considered for tracking over the campaign.

**Why it fails, three independent defects, each sufficient on its own:**

1. **The noise band exceeds any plausible signal.** Across **86 archived reports** the score ranges **61–73**; it was **73** when the campaign started (2026-08-13) and **72** at the last whole-package reading (2026-08-22); **readings from a single day span 61 to 72**. (**Corrected 2026-08-23:** an earlier version said *"71 at the end"*, verbatim from a source written 2026-08-22; re-measuring all archived reports puts 71 on 2026-08-21 and 72 on 2026-08-22. The difference sits inside the noise band this very entry declares, so nothing turns on it — but a stale "end" figure in a document that will outlive the archive is worth pinning to a date.) A ±5 movement inside that band means nothing, so neither improvement nor regression can be claimed from it. `[MEASURED]` — `toolguard-memories/TOO-45/reports/pyscn-wrap-up-assessment.md`
2. **The denominator is undeclared and small.** pyscn's complexity analysis covers **213 of 951 functions (22%)** across **49 of 79 files**, and it is *function-level* filtering, not file skipping — for files it does report it reports a subset (`config.py` 19 of 58, `command_extractor.py` 15 of 48, `maintenance.py` 8 of 33, `compound.py` 8 of 21). `toolguard/parser/bash_parser.py` (182 generated functions) is absent entirely. So "avg complexity 7.8" is the average over non-trivial functions only, and the grade is computed over that same filtered set. `[MEASURED]` — `reports/pyscn-2026-08-22-disposition.md`
3. **It reports perfect health for a file it could not read.** `uvx pyscn analyze tools/architecture_fitness.py` prints `Warning: Failed to parse file ... syntax errors found in source code` **and then reports Health Score 100/100, Grade A, all five metrics 100/100.** The cause was a three-name bare `except` clause. `[MEASURED]` — `toolguard-memories/TOO-45/proposed-tickets/66-the-architecture-fitness-tool-passes-over-nothing-and-cannot-see-a-loosened-map.md`

**Arnon's standing position, verbatim, 2026-08-23** (`reports/pyscn-2026-08-22-disposition.md`):

> *"pyscn health score - like any other aggregate 'architecture metric' we discussed - it is pretty useless, even as a directional measure. With pyscn I care about individual findings and widely accepted metrics like cognitive complexity cyclomatic complexity etc. And even then the thresholds are reason to review rather than absolute."*

**Use instead**: per-function cyclomatic and cognitive complexity, as a **reason to review, never a verdict**. The worked pair is in the same file: `judge_unit` at 20 was worth splitting; `node_kind` at 15 is a flat ordered-choice dispatch whose ordering is load-bearing and documented, and splitting it would destroy the thing that makes it readable. **Same number, opposite conclusions** — which is precisely why the threshold cannot decide. This matches `.claude/rules/evidence-before-fixing.md`'s instrument rule: a check is strong when it measures conformance to a *declared* intent; a threshold declares nothing.

**Second-order consequences worth keeping**: because a parse failure scores 100, *every* pyscn number is conditional on the file having parsed; and `.pyscn.toml` excludes `**/test_*.py`, so **no pyscn-based guard can ever cover the test suite** — which is why the replacement guard is AST-based. `[MEASURED]` — ticket 66.

**Class: (a)** for the aggregate. **(c)** for most of the per-function findings (see C2).

> **DISAGREEMENT — WITHDRAWN. Corrected 2026-08-23, on adversarial verification.** An earlier version of this block argued that the general claim was an unmeasured extrapolation, on the premise that *"no other aggregate architecture metric was tracked over time during TOO-45"*. **That premise is false, and this document is its own counter-example.** `reports/retrospective.md` §3.1 is a before/after table of aggregate architecture metrics taken across TOO-45 (`master 532de02` -> `branch a3e3f27`), and section A2 below reproduces four of its rows: 100%-coupled co-change pairs **71 -> 134 (+89%)** while the architecture demonstrably improved (anti-directional); **max co-change partners**, `config.py` 68 -> 71, which §9.4 calls *"noise"* and recommendation 4 retires as a headline number; **% of logical changes confined to one zone**, 40.0 -> 36.4, which moved for a purely arithmetic reason; and A6's **M1 role-ratio / M2 touch-set rate**, scored across two trees and proven biased by Monte Carlo. `reports/dependencies-before-after.md` adds a further before/after aggregate table (layer violations 3 -> 1, import cycles 2 -> 1, longest chain 12 -> 11, import edges 166 -> 173). Three of those four were measured directionally and found directionally useless — precisely the measurement the objection claimed was never taken. The objection also **mis-quoted Arnon to manufacture the universal it objected to**: his words at line 38 are *"like any other aggregate 'architecture metric' **we discussed**"* — a bounded claim over the set the campaign actually measured — and the earlier re-quote's ellipsis deleted `we discussed`, converting it into an unbounded universal he never asserted. **The one fair residual**: two of the tracked aggregates — import cycles and longest dependency chain — did track direction correctly, so the position is not proven exhaustively either; that is the real caveat, and it is not the one the earlier block made. A1 above stands as written and needs no hedge.

### A2. Co-change coupling as acceptance evidence for the refactor being made — and the per-ticket grouping that produced it

**Tried**: `tools/architecture_fitness.py --metrics` counts file pairs that change together 100% of the time, grouping history by `TOO-nn` **ticket** rather than by commit, deliberately, so nobody can game the count by splitting commits. It was read before and after the refactor.

**Why it fails**: the refactor is inside the metric's own sample, and is an outlier there by construction — untangling means touching things that do not normally change together. `[MEASURED]`, `reports/retrospective.md` §3:

- 100%-coupled pairs went **71 → 134 (+89%)** across TOO-45, while the architecture genuinely improved (a cycle gone, a dependency hop shorter, 2,387 tests OK).
- **Mechanism pinned to 63 of 63 newly-reported pairs**: all 63 have both files inside TOO-45; all 63 had `min-touch` exactly 2 before and exactly 3 after; all 63 went from `co_changes` 2 to 3; 0 pairs were lost. A pair is reported when `co_changes == min(touch_a, touch_b)` and `min(touch) >= MIN_COUPLING_OBSERVATIONS` (3) — a coincidence filter. **One change touching both files of a pair increments numerator and denominator together**, preserving the ratio and clearing the guard.
- **The real culprit is sample size**, not commit-splitting. Per-commit grouping over the identical change moves **39 → 42 (+7.7%)** — a 12-fold difference in sensitivity, from 43→46 changes instead of 10→11. TOO-45 shipped as one squashed commit, so the two groupings treat it identically; **under squash-merge the ticket grouping buys nothing and costs 7x the sample size.**
- **Do not tune the threshold.** `min_obs = 4` looks excellent (+5.1%) and then inverts violently: 5 → **+136%**, 6 → **+1300%**. That is not a parameter finding a sweet spot; it is 10 data points producing noise.
- **Do not exclude by label.** Excluding TOO-45 restores the master numbers exactly and is a complete fix — and a bad one, because *"is this a refactor ticket?"* becomes an editable field and the gaming vector moves from how you split commits to how you label them. Same shape as the `.pyscn.toml` relabelling that passed a whole step with zero Python changed.
- **Two more casualties in the same table.** *"Max co-change partners"* is not salvageable as a count — one change touching `n` files gives every file `n−1` partners at a stroke, so `config.py`'s 71 partners out of ~67 modules cannot discriminate anything; **retire it as a headline number**. And *"% of logical changes confined to one zone"* moved 40.0 → 36.4 for a purely arithmetic reason: at N=11 every percentage has a resolution of 9 percentage points.

**What is NOT rejected, and this is the important half**: co-change was the **only** instrument that ever saw the defect motivating the whole ticket. The `config -> engine` callback inversion has **zero import edge**; `--layers`, pyscn layer compliance and ruff were all green on it before and after. Co-change saw it as *"`compound.py` has never been changed without also changing both `config.py` and `permissions.py` — 100% coupling, 6 observations each."* `[MEASURED]` — `reports/retrospective.md` §5.1 defect 10 and §9.5. So the campaign's sharpest structural result is that **the one instrument capable of seeing this class of defect is the one the act of fixing it degrades.**

**Use instead**:
1. **Measure direction before you start and not again until well after you ship.** Including the in-flight ticket in its own denominator is a category error, not a tuning problem.
2. **Named instances with observation counts, not aggregates.** The aggregate provokes questions; the named claim does the work.
3. **Size-weighted pair coupling, `1/(n−1)` per pair per logical change** — a two-file change is strong evidence about those two files, a 23-file change is weak evidence about any pair inside it.

> **DISAGREEMENT — the recommended replacement has not passed the campaign's own instrument gate.** Size-weighting was validated by **top-20 rank overlap 18/20 vs 14/20 unweighted**, measured on *the same single before/after pair that revealed the defect* (`reports/retrospective.md` §3.4) — fitting a fix to the instance that motivated it — and **no control was run on it**. The retrospective also records honestly that weighting **does nothing for the per-file metric**, which degenerates: a file's total weighted coupling equals the number of logical changes that touched it (`hook.py` 8.0 across 8 changes, `config.py` 7.0 across 7). Treat size-weighting as **a proposal with one favourable measurement**, not a validated instrument.
>
> **Corrected 2026-08-23:** the measured core above stands, but two rhetorical moves in the earlier version of this block are withdrawn on verification. (1) It called this *"the `min_obs = 4` trap's own shape one level up"*, which **misdescribes the mechanism**: the `min_obs` trap is a **free tunable parameter** whose neighbouring values invert violently (5 -> +136%, 6 -> +1300%) and whose instability *is* the diagnosis, whereas `1/(n−1)` size-weighting has **no free parameter to be unstable at** — it is fixed by the mining-software-repositories literature, and its arithmetic is stated and checkable in §3.4 (`1/22 = 0.045` per pair; every untouched pair unchanged to three decimals). (2) It said the campaign *"wrote down the four controls this should have to clear"*. `reports/canary-before-after.md` §4.3 is scoped to **the change-cost canary's replacement** and labels its own controls asymmetrically: controls 1 and 2 (positive, negative) are *"the general form"*, while 3 and 4 are *"the domain-specific hazards this ticket discovered"* — neutrality's test case is a tuple-to-dataclass conversion and game-resistance's is renaming the enrichment field, and neither has a co-change analogue. So the gate size-weighting actually owes is **two general controls, not four**. And §3.5 gives it an **independent gaming-resistance argument** that *"one favourable reading"* did not acknowledge: *"You cannot reduce a pair's weight by splitting your commits… the one way to dilute a pair — padding a change with unrelated files — is self-defeating and visible in review."* Reasoned, not run — so *"no control was run"* stands, but *"one reading"* understated the case for it.

### A3. A corpus replay that compares only the decision

**Tried**: replay every logged command through the package before and after a change and compare `allow` / `deny` / `ask`. Reported as *"zero flips across 53,112 logged decisions"* for ticket 18 and read as safety.

**Why it fails**: it **cannot see a rule going from not-matching to matching when the fallback already permits**. This repo sets `no_match_fallback = "allow_with_no_warnings"` (`.claude/toolguard_hook.toml:4`, TEMPORARY pending TOO-28), so an unmatched command was already a silent `allow`; after a change makes a rule match it, the decision is still `allow`. No flip, no warning, nothing in the log. **Measured instance, not hypothetical**: this repo's own `Bash(\obsidian search:context *)` matched nothing at HEAD and matches now, and the real command appears 5 times in `logs/`. `[MEASURED]` — `reports/replay-instrument-blind-spot.md`

**Zero flips is evidence of neither safety nor inertness** — it is a null over a transition the instrument cannot observe.

**Scope of the damage, measured, and it is narrower than first feared**: featherhill **0 fallback verdicts in 3,675 decisions (0%)**; toolguard **9,848 of 51,918 (19%)**; instagram 0 of 28. Claims measured over featherhill were never masked. Ticket 78's replay **did** compare `matched_rule` (26,530 commands × 2 trees, 0 matched-rule changes) and is sound; ticket 18's was verdict-only and is not.

**Use instead**, in Arnon's order of preference (verbatim, `reports/replay-instrument-blind-spot.md`):

> *"since you do collect provenance - it should be easy for you to see whether the verdict was a fallback or not. And for the corpus estimation - you can assume the fallback is always ask even if in this repo it is temporarily an allow."*

**Re-score the corpus as if `no_match_fallback` were `ask`** — a command matching no rule then scores `ask` and a newly-matching rule shows a genuine `ask -> allow` flip. That makes the *instrument* sensitive rather than requiring a second field to be eyeballed, and it models the default configuration rather than this repo's temporary one. Comparing `matched_rule` is the weaker half and still worth doing. Provenance already distinguishes them: the log writes `[fallback allow -- no rule matched]`.

**The related and separately-measured limit of the corpus itself**: *a clean corpus is not evidence of no regression*, **three measured instances** (`reports/surprise/CONSOLIDATED-BATCH-2.md`) — ticket 18 (fallback masking); ticket 98 chunk 2 (three real defects fixed, zero corpus decision changes, because none of the 6,401 cases contained the shapes); ticket 101 (a brace-group deny bypass would have passed `--verify` cleanly, because the corpus contains **no brace groups**). The corpus is harvested from real logs, so it measures what the agent *has* emitted — excellent for regression detection, structurally blind to anything rare. The permanent answer is in the tree: `test/unit/test_deny_penetrates_constructs.py`, a denied command in all 17 constructs with a benign control so it cannot pass by denying everything.

**Class: (a)** for verdict-only comparison as a safety oracle. **(b)** for the corpus, which is sound and was being asked a question it cannot answer.

### A4. The change-cost canary / enrichment footprint

**Tried**: count files and identifier occurrences coupled to the `additional_context` enrichment field, before and after, as the acceptance metric for step R1 — with a pre-registered "flat = failure" criterion.

**Why it fails — three distinct defects, and the notes merge them** (`reports/canary-before-after.md` Part 3):

- **Defect A: the file count is bounded below and cannot register success.** All nine coupled files have a structural reason to name the field even in an ideal design (declare, parse, produce, render, persist, replay, harness). **It read 9 on master, 9 on the final branch, and 9 at every point in between**, across a ticket that provably removed 13 bare verdict tuples, took `log_command` from 11–12 parameters to 4, and cut `hook.py`'s enrichment references 26 → 14. An instrument reading identically before and after a change of that size is not measuring the change. The pre-registered criterion **would have scored R1d — the step that actually delivered — as a FAILURE**; it did not only because a scout checked what the metric could express *before* the step ran.
- **Defect B: the occurrence count moves, in the wrong direction on the one transformation it was registered to score.** It counts identifiers, so it is blind to positional (tuple) coupling and **rises when positional coupling is converted into named fields** — 53 → **72**, worse than R1's starting point, on a genuine improvement (14 of `compound.py`'s occurrences are now `additional_context=` keyword arguments where the values previously rode in tuple positions).
- **Defect C: it is keyed to a spelling and therefore gameable.** R1f named a field `matched_pattern` rather than `matched_rule` **specifically so a sibling detector would not count it** — and disclosed doing so in its own report. `[MEASURED]` — `reports/retrospective.md` §5.1 defect 6.

Separately, the **fresh-naive-agent** variant of the change-cost canary produced a headline of "7 files after R3" that was later recorded as unreconstructable and abandoned (`reports/retrospective.md` §4.7).

**Use instead**: a **trial-edit probe** — add one new independent enrichment key end-to-end on a throwaway tree copy and report `F` production files edited, `H` diff hunks, `S` signatures changed, `G` green/not-green. Spelling-agnostic, representation-agnostic, not bounded below, and it has an existing oracle in the enrichment e2e goldens. Run it at **phase** boundaries, not step boundaries, because it is an edit. Keep the naive agent for its **qualitative** read — it independently reported that the enrichment value is *"threaded positionally through five separate tuple/dataclass shapes across three modules"*, which is the ticket's central diagnosis arrived at from scratch — but **never treat its file count as a metric**.

**And keep the four controls that this failure produced**, because they generalise past this instrument (`reports/canary-before-after.md` §4.3): before any step is scored on a new instrument, run a **positive** control (can it register success?), a **negative** control (can it register failure?), a **neutrality** control (is it representation-agnostic?), and a **game-resistance** control (is it spelling-proof?). The one-minute version costs nothing: *write down what reading would be failure and what would be success, and check both are physically attainable.* The file count fails that on inspection alone.

### A5. Rename-and-count as a risk or cost measure

**Tried**: rename a symbol repo-wide, run the suite, and quote the failure count as blast radius.

**Why it fails**: it measures **how many places spell a name**, which is rarely the question. `[MEASURED]` — `reports/retrospective.md` §5.3:

- Renaming `hard_deny` breaks **106** tests. The actual change to the same code — different behaviour, no rename — breaks **0**.
- Two further estimates, **88** and **180**, both resolved to **zero net suite change**.
- Contaminated in both directions by ordinary English module names: `subagent` word-rename damage **684**, actual module-move damage **1**; `error_log` word-rename **798**, actual move damage **2,357**.
- A single test-infrastructure monkeypatch makes a whole class of modules unprobeable: `log_writer.log_command` and three `error_log` functions are patched at test-package import time, so touching either takes the suite to **0 tests run and 1 collection error** — not a partial number at all.
- **And low blast radius is not low risk**: `subagent`'s move broke exactly 1 test — *"not 'cheap', it is 'there is nothing here to catch a mistake'"*.

**Use instead**: the **physical module-move probe** (rename the file, rewrite in-package paths only) — the honest version, barely more work than the rename that misleads. Report mechanical and behavioural damage **separately**, or do not report the number. And Arnon's framing retires the objection entirely: blast radius is a **cost estimate, not an argument against doing the work**, except where shape is part of an external contract.

### A6. Any measure normalised by "number of code locations", for comparing differently-factored trees

**Tried**: two instruments, built independently by different agents from different specifications, to score whether the refactored tree absorbed change better — **M1** counted roles per code location and divided conduits by decisions; **M2** counted predicted-vs-actual locations and divided by the total.

**Why it fails — and this is the campaign's strongest (a), because it was *proved* rather than observed** (`reports/micro-canary-protocol.md`, "The denominator trap" and "STOP"):

Both failed the same way. Each had a denominator that moves with **the exact property under test**: a monolith implementing a requirement in one function has one location and one chance to surprise anyone; a well-factored tree with four small functions has four. Both consequently flattered the less-factored tree. Formally, for `n` locations, predictor accuracy `p` and `L` genuine leaks: `surprises = L + n(1−p)` (the **count** carries noise proportional to n) and `surprises/n = L/n + (1−p)` (the **rate** divides the signal by n). **Verified by Monte Carlo, 3,000 draws per cell across n=1..12 and p=1.0..0.4**: the rate is flat to two decimals across the entire grid and the count rises linearly with n. Head to head with leaks held equal at exactly one, 3 locations against 8, **the count picks the coarse tree in 64.7% of draws at p=0.8 and 90.9% at p=0.5**. The two published numbers disagree at every realistic prediction quality — and the coordinator had promoted the biased one on a confidently-stated intuition.

A related and equally general trap one level up: **an AST-level count of "where the logic lives" systematically rewards duplication**, because factoring a predicate behind a name moves the logic out of syntactic view. Inline a condition four times and a syntactic instrument sees four decisions; name it once and call it four times and it sees four conduits and no decision at all. M1 demonstrated this end to end.

**The conclusion is structural, not fixable**: there is no per-location common unit between two codebases that decompose a problem differently. The invariant unit is the *conceptual work item*, and no static tool can see it, because deciding what counts as one item is the same judgement the measurement was trying to avoid making.

**Use instead**: **count discrete qualitative events; do not compute rates over locations.** A *surprise* — "a location changed that no careful reader of the requirement would have expected" — is a countable event needing no denominator. Where a number is still wanted it is a count of **adjudicated leaked concepts**, with the concept mapping fixed and recorded **before unblinding**. Mechanical tools gather evidence; they do not score. Rates survive only where the denominator is agreed by both sides and independent of granularity.

**Cost, and why it is recorded as a result**: four agents and no implementations. The alternative was twelve requirements implemented twice and scored by two instruments that both — independently, for different reasons — preferred monoliths, producing a respectable-looking table in favour of whichever tree was less factored. **Both instruments passed their own hazard suites. Both were validated on real data. Every check short of a dedicated adversary said they were fine.**

### A7. Surprise ratio `|A| / |P|`

**Tried**: as the headline of the surprise-factor protocol.

**Why it fails**: it rewards **naming few files** rather than naming the right ones. Four items in, ranked by ratio the order was 05, 15, 04, 01; ranked by recall it was 04, 15, 01, 05 — **the extremes inverted every time**, and the ratio never once agreed with whether the change surface was actually foreseen. `[MEASURED]` — `reports/surprise-factor-protocol.md`, dropped 2026-08-09 on Arnon's acceptance.

**Use instead**: **recall** (`hits / |A|`) as the headline, with **precision** carried only so a predictor cannot win by naming everything. Production and test files scored separately, never pooled.

**Also dropped from the same protocol** (`reports/surprise/RESULTS-LOG.md`): cause code **`T` (transient)** — a prediction that was genuinely modified mid-ticket and reverted before commit, zero net diff. It measures **effort**, which is explicitly not the constraint. Cause **`A` (absorbed)** was demoted from headline to side observation and then **un-demoted by Arnon**, verbatim: *"Absorbed is not a bad classification as it goes. I wouldn't drop it so easily. Not yet at least. We'll see after we have stats on this large list."*

**And the meta-rule the drop established**: the instrument is tunable and the aggregate is where tuning happens — but changing the scoring **while results are arriving** lets the measure be steered toward whatever looks good. Within a series the definitions hold; revising from the aggregate is ordinary instrument development.

### A8. Self-rated implementer difficulty

**Tried**: ask each blinded implementer how hard the change was, as a comparative signal between trees.

**Why it fails**: it was pre-registered as the weakest evidence in the set and turned out **actively inverted**. On MR-08 the implementer who **introduced a layering violation** rated the work *straightforward*; the one who **avoided it** rated it *fiddly* — and rated it easier **because nothing stopped them**. `[MEASURED]` — `reports/canary-results.md`.

**Use instead**: nothing, on its own. A low difficulty rating is **unexplained until the correctness question is settled separately**.

### A9. `tools/change_role_classifier.py` and `tools/touch_set_score.py` headline metrics

**Tried**: two of the three dev-only measurement scripts built for the canary comparison.

**Why they fail**: both were **proven biased by adversarial testing** — the role classifier's headline number was **anti-correlated with code quality** (factored code scored worse than copy-paste), and the touch-set scorer's counts and rates were shown mathematically non-comparable across trees of differing granularity (A6). **Neither contributed to any conclusion in the ticket**; every canary finding came from implementer prose and direct verification. They carry **300 tests** that must keep passing forever for tools nobody runs — `test_change_role_classifier.py` **131** and `test_touch_set*.py` **169**. `[MEASURED]` — re-measured 2026-08-23 by running both suites. **Corrected 2026-08-23:** an earlier version said *"roughly 90 tests"*, stamped `[MEASURED]` and cited `toolguard-memories/TOO-45/proposed-tickets/06-measurement-tools-keep-or-remove.md:20`. The citation was faithful — the ticket does say "roughly 90" — but the number does not reproduce, and this document passed a source's figure through unexamined under a `[MEASURED]` label. The same ticket also says "three tools and **four** test files"; `git ls-files` shows **three**. Nothing in the argument turns on the correction except this document's reliability: the case for removal is **stronger** at 300 tests, not weaker.

**What to salvage rather than delete blindly**: the classifier's **occurrence matching** was independently proven exact twice (82/82, and 394 occurrences against an AST oracle), and the inventory's **blindness guarantee** was audit-verified (170 file opens, none outside the tree, none under `.git`, no subprocess, no VCS path). Those are the reusable pieces if perturbation testing becomes a standing pre-push activity. **If reused, re-attack first**: the last adversarial pass ended with residual silent loss in **13 of 24** implementation styles.

**Status**: the keep/remove decision is **still open** — the files were swept into git by a `git add -A`, not chosen.

### A10. Ruff `PLC2701` (import-private-name) as the enforcement mechanism for cross-module private access

**Tried**: adopted-in-principle as the natural lint for step R6, which is entirely about cross-module private access.

**Why it fails**: it fires only on private imports from a module **external to the importing file's package**, and everything under `toolguard/` is internal to `toolguard`. Two runs, same file, same line, opposite verdicts `[MEASURED]` — `reports/retrospective.md` §7.1:

```
uv run ruff check --no-cache --preview --select PLC2701 toolguard/tools/takeover_audit.py
  -> All checks passed!
uv run python tools/architecture_fitness.py --predicates
  -> R6: FAIL - tools.takeover_audit:87 imports private _strip_tool_wrapper from config
```

Its only live surface in this repo is `test/` (69 hits) — and the project's own visibility criterion explicitly sanctions tests importing privates, so configuring it correctly makes it report **zero across the repo, permanently, by construction**.

**The generalisation, which is the durable part**: *a lint rule can be structurally incapable of seeing the violation you adopted it for, and adopting it is then worse than adopting nothing, because it converts a known gap into apparent coverage.* **Before adopting an instrument, confirm it fires on a violation you have already found by other means.** An instrument that never fails is a decoration.

### A11. pydocstyle (`D` family) as a docstring-quality instrument

**Tried**: considered for the docstring-bloat problem the campaign was actually fighting.

**Why it fails**: **11,010 findings repo-wide**, of which **D212 + D205 + D415 + D400 + D413 = 10,744 (97.6%)** are pure punctuation and placement of docstrings that already exist; missing-docstring rules D100–D107 total about 150. **Not one `D` rule measures verbosity, redundancy or restatement** — the only docstring problem this repo has. Enabling it produces ~3,965 autofixes' worth of churn and a large red-to-green event that says nothing about the concern, **while creating the impression that docstring quality is under lint control**. `[MEASURED]` — `toolguard-memories/TOO-45/TOO-45 ruff configuration proposal.md`

**Use instead**: it is a **metric, not a lint** — a docstring-lines-to-executable-lines ratio per module, over the AST pass the fitness tool already has. **Proposed and never built** (verified 2026-08-23: no `docstring_ratio` symbol in `tools/architecture_fitness.py`), and D1a's 55%-docstring module (202 docstring lines of 370, AST-measured) is exactly what it would have caught.

### A12. Ruff `TID251` as enforcement of the stdlib-only runtime constraint

**Tried**: TID251 bans `threading`/`asyncio`/`multiprocessing`/`concurrent.futures` — a free ratchet on a stated hard rule, and it was correctly adopted **for that**. It was also considered as the mechanism for the broader stdlib-only architectural constraint.

**Why it fails for the broader job**: TID251 is a **denylist** and the constraint needs an **allowlist**. A denylist standing in for a security property fails in the worst direction — a dependency added tomorrow is permitted by default and the lint stays green through the regression. `[JUDGEMENT]`, with the reasoning in `TOO-45 ruff configuration proposal.md`; the retrospective calls the allowlist version *"the highest-value unbuilt instrument identified on the ticket"*.

**Status correction**: the retrospective's open question 4 (*"the stdlib-only constraint is enforced by nothing"*) is **stale**. `check_stdlib()` and the `--stdlib` mode exist in `tools/architecture_fitness.py` (verified 2026-08-23, `tools/architecture_fitness.py:4341-4396`), membership from `sys.stdlib_module_names | STDLIB_ALLOWED_ROOTS`, and `CLAUDE.md`'s pre-push checklist runs it. The unbuilt one is A11's docstring ratio.

### A13. Any target number for comment or docstring quality

**Tried**: driving the comment sweep by a countable proxy — specifically a ticket-reference count.

**Why it fails**: *"a first attempt driven by a ticket-reference count deleted the IDs, left the useless prose in place, satisfied its own metric, and made the codebase worse."* `[MEASURED]` — `toolguard-memories/TOO-45/TOO-45 comment standard.md`, which then states the rule flatly: **there is no target number — not of lines, words, ratios, or ticket references. Any number here gets optimised instead of the thing it stands for.** Measurement has one legitimate use: finding files worth looking at. It never says a file is done, and **the reviewer must never check whether any count went down.**

**Use instead**: the standard's own discriminators — *would a competent reader re-derive this from the code?* (cut) / *does it record something unrecoverable — a negative result, a rejected alternative and why, a non-obvious edge case?* (keep) — and the structural tell: **where comments cluster is a refactoring signal**, numbered or not.

---

## Class (b) — sound instruments, wrong target or wrong harness

### B1. `--guard PASS 12/12` pointed at the installed release for the whole ticket

`run_guard_canaries` defaults to `~/.local/bin/toolguard` — the `uv tool install` copy, **v0.5.1 built from master and byte-identical to the pre-TOO-45 tree**. So `--guard PASS 12/12`, quoted as a safety result in **every recorded step's** acceptance block, never executed a line of the refactored code. (**Corrected 2026-08-23:** the earlier *"fifteen stages"* is verbatim from `reports/retrospective.md` §5.1, but `reports/canary-before-after.md` §1.3 says *"sixteen step reports"* and then lists seventeen. Three numbers for one fact, so the count is dropped rather than silently picked.) **Measured sensitivity to TOO-45: 0 of 12** — the twelve cases were run through both binaries and disagreed on nothing. `[MEASURED]` — `reports/canary-before-after.md` Part 1.2, `reports/retrospective.md` §5.1 defect 9.

**Two facts make it more than an erratum**: nothing was actually missed (the 6,401-case corpus was the real oracle and was sufficient) — so *"corpus clean AND guard clean"* was **one result stated twice**, two believed safety nets where there was one. And **the warning fired correctly and was not connected**: the SessionStart hook printed `INSTALLED COPY IS STALE` in the first message of the session. *A warning that is correct but temporally and surface-wise distant from the reading it invalidates is, in practice, not a warning.*

**Fixes**: default to the working tree; **print the target and its version in `--guard`'s own output**. The retrospective calls this the single cheapest fix in the report — *make every instrument print what it just measured, not only the verdict.*

**Root cause worth naming separately**: two entirely different instruments were both called *canary* — the 12 permission expectations replayed through a binary, and the fresh-agent change-cost probe. They share no purpose, oracle, failure mode or target binary. *"The canaries are green"* was a sentence that felt informative while being ambiguous, for a whole ticket. **Never let two instruments share a name.**

> **DISAGREEMENT — the notes conflate (a) and (b) here, and the retrospective's framing is the one that would mislead a future reader.** The retrospective lists this under "ten instrument defects" and instructs that every `--guard PASS` be read as a statement about the shipped release. That is right. But `reports/canary-before-after.md` Part 5 makes the opposite case on measured grounds and it is the better-supported one: the guard canaries answer a **different question the corpus structurally cannot** — *are the fences protecting this unattended loop still loaded on this machine right now?* Both rule files live outside the repository (one a symlink into a dotfiles repo, one in no repository at all), and under `allow_with_no_warnings` **a missing deny rule silently becomes a permission**. The instrument was also proven able to move in both directions before being trusted, via an inverted test (flip a canary's expectation to disagree with the live config, confirm exit 1 and a named diagnostic) — because the guards make the obvious experiment impossible by construction. **So this is class (b): a sound instrument reported against the wrong claim, not a bad instrument.** The transferable rule is *"for every green reading, ask which artifact this measured"* — not *"the canaries were worthless"*. **Corrected 2026-08-23:** an earlier version of this block closed by warning that *"retiring it ... would remove the only check on a silent, permission-widening failure"* — a rebuttal to a position **no source holds**. Nothing in the record proposes retiring the guard canaries, and `reports/retrospective.md` §4.7 already lands where this block lands: *"The inverted-test **pattern** is still sound — it correctly demonstrated the detection mechanism — but the instance demonstrated it against a binary that was not under change. **Read every `--guard PASS 12/12` in the ticket record accordingly: it says the shipped release is intact, not that the refactor is.**"* The retrospective's *heading* (*"Two practices whose reputation exceeds the evidence"*) and its flat *"the 12 guard canaries themselves did not work"* do read as condemnation, so the tension is not invented — but it is a difference in emphasis, not a disputed verdict, and the earlier version inflated it into one. The class-(b) reclassification and the naming diagnosis below are the parts that carry.

### B2. The architecture fitness tool reporting PASS over nothing, and a layer map that grades itself

The most valuable custom artifact of the campaign and the home of nearly every instrument defect in it — and those two facts are not in tension. *"Writing the claim down as executable code is what converted nine unknowable beliefs into nine findings."* (`reports/retrospective.md` §8.1.) The defects, all `[MEASURED]` in `proposed-tickets/66-...md` unless noted:

- `run_guard(only_canaries=True)` with an **empty canary set** returns `ok=True, failures=[], warnings=[]` and prints `=== --guard: PASS === (no violations)` — a clean, **un-skipped** run of zero cases.
- `check_layers` reports `ok=True` over a tree with **zero modules**; `compute_predicates` reports **R2, R3, R5 and R6 all `pass=True`** over the same empty tree.
- **The layer map is gameable and the checker cannot tell the difference by construction.** Demoting `once_per` manufactures a violation; adding `"observability"` to foundation's allow-list **erases it**, and `render_layers_text` prints the identical *"No cross-layer direction violations"* either way. There is no signal distinguishing *fixed the import* from *loosened the rule*. **Only `api`'s allow-list was pinned by any test**; loosening the map, deleting a row, emptying `LAYERS` entirely and inverting the layer order each failed **zero** tests. A live bypass existed too — `from . import config` and `from .config import x` were completely undetected, and `permissions.py`'s imports read as **empty** to the extractor.
- A separate probe found **five one-line edits tried against the one remaining violation; three erased it with nothing catching the edit** (`reports/architecture-sweep-practices.md`).
- **A declared package with no module behind it is never reported**, and `[architecture].enabled` is parsed by nothing.

**Partially fixed in `05f786d`**: the empty-tree guard landed; a loosened map is still invisible in production and is closed only by a test pin.

**The general rule this produced** (`.claude/rules/evidence-before-fixing.md`, and `reports/architecture-sweep-practices.md`): **any check whose configuration lives in the same repository as the code it grades can be edited to pass without the underlying property becoming true.** *"The map is simultaneously the specification and the thing being satisfied."* **Read facts, not labels** — derive the entry-point set from `pyproject.toml [project.scripts]`, a fact about what ships, rather than from an editable layer file.

**And the durable design lessons from the same tool's successes**: print every exclusion with its reason; **print the clauses you cannot check** rather than inventing a proxy for them; carry a standing caveat where a number is known to mislead; **detect at use sites, not definition sites** (`find_parallel_arrays` matched a class name and an `_entries` suffix and was defeated by a `sed`; its use-site replacement caught a method-versus-field variant with zero special-casing).

### B3. An import graph as the only structural lens

**Why it misleads**: an import graph measures **declared** dependency. Inversion of control, callbacks, dependency injection, registries, string-keyed dynamic dispatch and monkeypatching all create real dependencies that carry no import edge — and they are exactly the constructs a mature codebase accumulates. **A layer checker built on imports is systematically blind to the most sophisticated coupling in the system, and its green is loudest precisely where the design is worst.** `[MEASURED]`:

- The `config -> engine` callback inversion — the defect the whole ticket was built on — has **zero import edge**, and `--layers`, pyscn layer compliance and ruff were all green on it before and after (`reports/retrospective.md` §5.1 defect 10).
- Runtime says the opposite of static: before the fix, `config` and `resolve` — **zero import edges between them** — called each other **46,481 times** over a 6,401-case replay, entirely through the injected callback. After the fix, `config`-layer execution on the decision path fell **87%**, ~2.9M → ~380k calls, **while `config`'s static fan-in went *up* by one.** A tool measuring only import edges would have called the change neutral to slightly worse (`reports/architecture-sweep-practices.md`, `reports/dependencies-before-after.md`).
- A second instance found later by the architecture judge: `once_per` re-introduced an invisible upward runtime edge — `auto_migrate` (config layer) hands `_migrate` to `OncePer.run`, whose body is `return action()`, so an observability module executes config-layer code at runtime with no import edge and `--layers` reports clean (`reports/architecture-judge-backtest.md`).
- And **dynamic dispatch hides call edges from the repo's own semantic tooling**: `_ROUTING` stores `log_fn_name: str` and `_dispatch` does `getattr(error_log, name)`, so pyright's `incomingCalls` and the graph's `callers_of` both see **zero** callers for `log_warning`/`log_error` — indirection introduced to keep a `patch(...)` working, i.e. test mechanics driving production shape (same source).

**Use instead**: pair every import-based check with a **runtime or historical** instrument, and treat their disagreement as the finding rather than reconciling it. Arnon's framing (`reports/review-conclusions.md`): *"It is easy to hide from static analysis and hard to hide from observed runtime behaviour."* Find problems by execution and tracing; then fix them so the **next** violation of that class is catchable statically — Protocols and type annotations at duck-typed seams, not prose comments.

### B4. Mutation testing — the method is the campaign's best return per line, and the harnesses lied constantly

Every item below produced a **confident wrong number**, usually a **false zero-detection**, which is worse than no reading because it manufactures a finding that does not exist. All `[MEASURED]` in `toolguard-memories/TOO-45/TOO-45 test-repair plan.md` unless noted:

| trap | mechanism | tell / fix |
|---|---|---|
| mutation landed in a **docstring** | `source.replace(old, new, 1)` hits the first match, often prose above the code | **print the mutant diff**; generalised: it can also hit the wrong *branch* — measured twice in one module |
| **masking guard pairs** | `apply_parse_failure_floor` and `_apply_ask_floor` both carry the already-deny exemption; one returns first | mutating one site of a duplicated mechanism over-reports coverage |
| **by-value imports** | patching the defining module no-ops when the consumer imported the name | patch every holder; find them by **identity scan over `sys.modules`**, not grep — and treat the count as a **lower bound**, because a scan sees only what is loaded (two agents got 10 vs 14, 6 vs 8, 3 vs 6 on the same constants hours apart) |
| compiled against a **snapshot** of the module dict | mutant resolves globals against frozen copies; a second implementation elsewhere still runs | `exec(compile(src), live_module.__dict__)` — the live dict |
| **module-level state pollution** across repeat runs | one test passes on run 1 and fails on run 2 **under every mutation including the null one** | establish a **null-mutation baseline across repeated runs** first |
| **persistent artifact state** | `logs/toolguard-discovery.log` *is* `log_discovery`'s state; the first mutant that lets a write through makes every later one look correct | reset state between mutants; the whole sweep had to be re-run |
| **`TimeoutError` watchdog** | it has been an `OSError` subclass since 3.3, so `except OSError` swallows the alarm — a deadlocking mutant read as a clean survivor with zero failures | derive any watchdog from `BaseException`; **40 `except OSError` sites across 19 production files** |
| **`unittest` subTest** | failures route through `addSubTest`, not `addFailure`, so a callback-counting harness under-reports every subtest detection | override `addSubTest`, or diff test IDs from the runner's output |
| a **mutant that agrees with the original** | a stub returning `sorted(roles)[0]` coincidentally matched the real precedence on the tested input | confirm the mutant changes the **output on your fixtures**; a symmetric fixture hides a swap the way defaults hide hardcoding |
| **fixtures built from defaults** | a mutant that *hardcodes* a field is invisible when the correct value and the hardcoded one coincide | one fixture repair killed **seven** mutants at once; a tidy-looking fixture is a warning sign |
| **wrong measurement tier** | a naive sweep mutates the production copy only; every mirror-comparison test dies and the module reads as fully covered | tier C (drop expected-name equality, keep the behavioural assertion) found **six weakenings surviving** — leaving `~/.ssh/id_ed25519`, `~/.ssh/config` and live AWS SSO tokens readable and writable |
| **identical failing-test sets** | four *mutually contradictory* mutants failing the same one test reads as detection and is not — the suite can tell *something* changed and nothing about *what* | **diff failing-test SETS, not counts**; record `(test_id, failure_reason)` |
| **a small sample generalised** | *"detection rate good (3 of 5 mutations caught)"* on a module later measured at **58% survival over 81 mutants**, where **34 zero-detection mutants shared one signature — the empty set** | the misleading part is the reassuring summary line, not a missed finding |
| **the mutant was never live** | restoring class identity after a re-exec silently undid **20 method-level mutants**, all reported surviving; a `sys.modules` identity scan rebound the harness's own `original` variable so the restore anchor *became* the mutant | assert per-mutant that the live object differs as intended; **exclude `__main__` from identity scans**; pre-import consumers (a whole ten-mutant battery bound the first mutant permanently and reported it for all ten — *identical results across different mutants is the tell*) |
| **snapshot cannot see a rewrite** | `(name, size, mtime_ns)` is insufficient on WSL2 tmpfs — a 4-byte in-place rewrite with different bytes came back **byte-identical**, because the kernel's coarse timestamp put both writes in one tick | snapshot `(name, size, sha256)`, and **prove it fires** against a planted file, a same-length rewrite and a deletion before trusting a clean result |

**Direction of the error matters and is recorded honestly**: the `TimeoutError` and `subTest` traps **inflate apparent coverage gaps** rather than hiding defects, so no filed ticket was at risk of being falsely severe from them. The fixture and masking traps run the other way.

**None of this is an argument against mutation.** It is the campaign's clearest discovery instrument — *a mutation that refuses to change behaviour is pointing at a second implementation*, which is how the duplicated undecidable floor was found and how its unification was proved (a MISSED→CAUGHT flip). The standing rule is **a mutation run must state its target**: a mutation reported MISSED against the corpus may be fully pinned by unit tests, and without knowing which oracle was consulted the result is uninterpretable.

### B5. Read-only review as a statement about what is wrong with a file

**Tried**: the follow-up queue — a read-only pass recording per-module findings — was used to decide which modules could be skipped.

**Why it fails**: **measured six times in one evening**, the queue's verdict was *accurate about what it examined* and silent about everything else `[MEASURED]` — `toolguard-memories/TOO-45/DECISIONS-PENDING.md`:

| module | queue said | mutation found |
|---|---|---|
| `edit_proposal` | *"Nothing substantive… its fixtures build exactly what its Givens describe"* — called it the best of five | **16** zero-detection mechanisms |
| `self_permission` | one redundant test | **13 of 25** mechanisms at zero detection |
| `migration_gate` | *"nothing substantive… no stale claims, no vacuous assertions"* | **11 of 22** mutants surviving (50%) |
| `sandbox` | 2 defects (both correct) | **4 more**, plus 16 pieces of API with no coverage |
| `file_lock` | 3 comment-level findings | **5** mechanisms at zero detection |
| `recommended_protections` | — | 6 weakenings invisible except at the right tier |

The `edit_proposal` entry is the one to remember: *"its fixtures build exactly what its Givens describe"* was **true**, and was precisely the defect — the Givens described **defaults**. **A statement can be correct and still name the problem it is dismissing.**

**Use instead**: read the queue as *a list of things someone noticed*. **A row saying "nothing substantive here" carries no information, and must never be used to decide a module can be skipped** — that is the one inference it cannot support and the one its phrasing invites.

### B6. Blinded-estimator recall (the surprise-factor protocol) read as a grade

**Tried**: a blinded estimator reads only the ticket and a file inventory (path, line count, first docstring line) and predicts the touch set; recall against the committed diff is the score.

**Why the number misleads — confounds, all `[MEASURED]` in `reports/surprise/CONSOLIDATED-REPORT.md`:**

- **Ticket leak.** Some tickets name the files they will touch. Item 03 scores **64.4% raw and 12.0% unleaked**; item 18's unleaked downstream was **0/7**. Recall on those measures transcription, not foresight.
- **Design leak, a separate exposure.** Item 77 was given the chosen design: production recall **9/9**. Item 80, scored the same day without it: **5/9**.
- **Scope purity.** Item 10's commit carries an unrelated `.gitignore` fix and a folded-in default change; only **12 of 620** unpredicted lines are attributable to the estimator. Its 45.8% is mostly not about prediction at all.
- **Repository properties mislabelled as estimator error.** Doc-file identity (predicted `README.md`, change went to topic files under `docs/`) — three times. Test-file identity — same shape, and an estimator's high-confidence inference from *"one test file per production module, with no exceptions I could find"* was **sound reasoning on a false premise**: **11 of 39 modules have none**. *An inventory is bad evidence for absence, because a missing file is not a row.*
- **Contamination, two routes, seven items.** Return channel: 05, 19 (both voided). Coordinator appendix: 20, 39, 57, 64, 70 — measurements appended to ticket files, which are the estimator's only permitted reading. *"Measuring before briefing was the campaign's highest-yield habit; writing the result into the ticket is what destroyed the measurement."*
- **Cause `B` (brief-constrained), which is the coordinator measuring itself.** On item 64 the coordinator predicted reuse rather than a third atomic-write, then wrote a brief forbidding every route to that outcome. The estimator does not have this problem because it never writes the brief.
- **Population validity, the largest threat and the last one noticed.** *"Almost every ticket in this series was written by me, as a side-effect of other work"* — agent-authored, long, heavily argued, solution inferred, straight to implementation. Arnon's own tickets differ on every axis. Batch 2's near-100% production recall is therefore **evidence that an author predicts their own scope well**, not that the estimator works (`reports/surprise/CONSOLIDATED-BATCH-2.md`).
- **And a mid-campaign law that was not one.** A claim that leak level predicts recall *monotonically* held on three ordered points and **broke in both directions** at seven: item 10 is the most leaked and scores worst; item 15 is moderately leaked, scores best, and its leak discount is inert.

**What survives, and it is worth more than the headline** (`reports/surprise/CONSOLIDATED-REPORT.md` addendum, `reports/surprise/BAD-SURPRISES-DIAGNOSIS.md`):

- **Ask for the CHARACTER of the fix, not its file list.** The file list is usually leaked; the character rarely is. Item 22: the estimator said *prose*, the coordinator said *structure*, and the estimator was right, reasoning from what a previous commit had already done. Item 85a, asked move-or-re-export, said **move**, because *"a re-export facade… the dependency would point the wrong way"* — and **chunk C then made exactly that mistake and had to be repaired.** One paragraph of protocol, the highest-value change in the series.
- **The single sharpest question**: *does this change carve out a new module, or relocate control flow?* **3 of 32 missed production files carry 811 of 958 missed lines (85%)**, and **every large under-scope had that one shape** — never a call-site sweep, which never cost more than 37 lines. That question recovers ~85% of the missing mass and supersedes the file list entirely.
- **The uncertainties file is sometimes the better instrument.** Item 79's estimator named `compound.py` and the exact binary question governing **79% of the diff**, said it could not resolve it under blinding, and predicted against it. **When an estimator flags a binary uncertainty that would move a large share of the touch set, treat the flag as the estimate** — the coordinator is not blinded and can resolve it by reading one call site.
- **Over-scoping is normal and nearly free; under-scoping is rare and expensive** — 54 inert production predictions against 32 missed files.

**Arnon's reframing, verbatim, which is what makes the instrument keepable**: *"The estimator is not the objective here - it's a means to an end. The value is in surfacing what we really need to look at so that we catch problems early and don't let them slide."* **A low recall is a prompt to investigate, not a grade** — and judged as a trigger, the confounds matter far less.

**Class: (b)** — the readings are confounded and the instrument was being asked to be a predictor when its value is as an alarm.

### B7. Ticket 30's fix for the pyscn parse blindness — correct diagnosis, self-reverting fix

The stated fix was *"`ruff format` will leave a three-name parenthesised tuple alone (it only strips the two-name form), so the fix is stable."* **Measured false on ruff 0.15.14**: `except (ValueError, TypeError, OSError):` is reformatted **straight back to the bare form**, so anyone applying the fix has it silently reverted by the project's own mandated `uv run ruff format .`, re-blinding pyscn with no signal at all. Two forms measured to survive ruff **and** let pyscn parse: a parenthesised tuple with a **magic trailing comma** exploded across lines, or the tuple **hoisted to a named constant**. `[MEASURED]` — `proposed-tickets/66-...md`

Two more from the same measurement: the generated parser does **not crash** pyscn, it **hangs** it past six minutes (so any guard reaching it needs a timeout, and the previous `timeout=600` would have stalled the suite for ten minutes); and pyscn writes an unbounded ~112 KB HTML report per `analyze` into `<cwd>/.pyscn/reports/` — gitignored, so **40 files (~4.5 MB) accumulated invisibly**, written by the guard's own test runs.

---

## Class (c) — valid, cheap, and the finding did not earn work

The governing rule is `.claude/rules/evidence-before-fixing.md`: measure exposure before fixing, **including for tickets already approved** — *"approval is not evidence."* Its counterweight matters as much: **zero occurrences plus accidental reachability plus silent failure is still a fix**; zero occurrences plus deliberate-evasion-only is a defer.

| finding | disposition and why | source |
|---|---|---|
| pyscn **duplication 45/100, 15.9–16.2% cloned, 61–62 groups** | **not triaged, no recommendation.** *"Severity from a clone detector is not severity in this codebase's sense."* The campaign both removed clones (`_pick_strictest`, `all_parts`, `_corpus_verdict`) and deliberately created one (a third `_atomic_write`, named in its own docstring for later consolidation). *"62 groups is a number, not a finding"* — expect the honest number well below 15.9% once fragments are read | `reports/pyscn-2026-08-22-disposition.md`, `reports/pyscn-wrap-up-assessment.md` |
| most of the **21 high-risk complexity functions** | **defer or ignore.** `installer.py` ×5 are CLI entry points — branchy because they handle flags and user error, run once interactively, fail loudly. `toml_scan._scan_array_char` (23) and `_find_array_close` (16) are character-level scanners where the complexity *is* the domain. `rule_apply._apply_to_file` (25) is the highest single number and is maintenance-tool code, not the permission path. The rest sit at 10–13 and are ordinary. **Only `match_command` (22) and `match_pattern` (15) were scheduled on merit** — highest complexity on the most security-critical code | `reports/pyscn-2026-08-22-disposition.md` |
| `command_model.node_kind` at 15 | **watch, do not refactor** — a flat ordered-choice dispatch whose ordering is load-bearing and documented; the ordering comments are the asset and a restructure risks them | same |
| second-level decomposition of `judge_unit` | **not worth it, and the numbers say so rather than taste**: after the first split complexity landed at **8**, and the largest helper — the security-sensitive `inline_code` branch, ~145 lines — came out at **6** | `reports/surprise/95-scored.md` |
| `file_lock`'s unguarded outer `os.close(fd)` | a close failure escapes as a bare `OSError`, defeating the module's one-exception-type contract — but only **after** the critical section completes. *"Recorded, judged not worth pinning"* | `DECISIONS-PENDING.md` |
| the **`test/` tier of the comment sweep** | **Corrected 2026-08-23 — it was NOT abandoned, and this row previously said it was.** It was **paused** on budget mid-morning 2026-08-12 (weekly limit at **88%**, **~2,780 requests** left), **resumed 40 minutes later**, and completed the same day: `7460ffb` (2026-08-12 13:11) sweeps **86 `test/` files** alongside 72 under `toolguard/`, and `549abc3` (2026-08-21) is a later `test/` pass that found *"seven tests that could not tell success from failing open"*. The **~342/hour** burn rate quoted earlier as `[MEASURED]` is superseded inside its own source, which came from a 24h average: the two-agent marginal rate is **~165/hour**, *"which roughly doubles what the remaining budget buys"*, and the source concludes *"the tier can probably finish inside this budget, which the 24h-average extrapolation said was impossible."* What survives is the **yield asymmetry for comment-reading specifically** — all six defect tickets came from `toolguard/` and `tools/`, and comment-reading in `test/` produced **zero product defects across 62 files**, which the source itself qualifies as *"real value, but not worth the week's remaining budget"*. **This is not a verdict on the `test/` tier**: mutating those same files (B5) found 16, 13, 11, 5 and 6 zero-detection mechanisms | `TOO-45 punch-list 07 work queue.md:72, :112, :117, :149-158`; `git show --stat 7460ffb`; `git show 549abc3` |
| ruff **RUF022, ERA001, TID252, SLF001, C901/PLR0912/PLR0915, Bandit/ANN/PLR2004/FBT/TC** | rejected for having **no mapped objective**, not for being wrong. Notable specifics: `TC` would *contradict* a stated convention (no `TYPE_CHECKING` guard without a real circular import); `TID252`'s one load-bearing argument was **tested and false** (TID251 resolves relative imports and flags them under the absolute name); the three complexity rules are *"a fourth complexity opinion — tool collecting"*, and 53 of 88 `C901` hits are in the generated parser anyway; `SLF001` is rejected **for now**, worth reconsidering once a real `api` module makes "reached around the surface" mean something | `TOO-45 ruff configuration proposal.md` |
| the **anti-stall cron** | **retire**: ~25 of 210 turns, about **12% of the transcript**, for a mechanism better served by ending each turn with a pending agent or a scheduled wakeup. *"The corpus is measurably noisier for it"* | `reports/corrections-analysis.md` |

---

## The rules that came out of the wreckage

Ordered by how much they cost when skipped. All are stated in the sources; the citations are where each is argued.

1. **An instrument that never fails is a decoration — hand it a known positive before trusting it.** Verified by construction, not by a clean run. The ruff adoption did exactly this: a probe file with one deliberate violation of each of the four adopted rules, confirmed all four fire, then deleted. (`reports/retrospective.md` §7.1, §10.2)
2. **Before pre-registering a criterion, show the instrument can express *success*.** A pre-registered criterion against an instrument that cannot move is not rigour — it is a false failure carrying all the authority of advance commitment. This is the campaign's sharpest methodological lesson. (`reports/retrospective.md` §5.2)
3. **Count the defect, not a correlate of the defect.** Every R1 claim that survived scrutiny counts *instances of the defect* — audit under-logging 813/975 → 0/978, `log_command` 12 parameters → 4, bare verdict tuples 13 → 0, index-parallel access sites 3 → 0, prose-parse sites 6 → 1, `__iter__` shims 2 → 0. Every claim that collapsed counts a *proxy* — files that mention a thing, identifiers that appear, names that match. (`reports/retrospective.md` §9.3)
4. **Direction, acceptance and diagnosis are three different jobs and cannot be one instrument** — different sample units, time constants differing by three orders of magnitude, incompatible Goodhart pressure, and only acceptance must be falsifiable in both directions for a specific step. **Diagnostic probes produced more findings per unit cost than either metric class and were the least planned for.** Budget for them explicitly; they will not appear on a metrics plan. (`reports/retrospective.md` §9)
5. **Make every instrument print what it just measured, not only the verdict** — target, version, exclusions with reasons, and the clauses it *cannot* check. (`reports/retrospective.md` §8.1, §10.2)
6. **Prototype a measurement on ONE case before building it properly.** Four instruments were built to specifications that turned out wrong, adversarially tested, then discarded; a one-case throwaway would have exposed the requirement-coupling problem at roughly a tenth of the cost. (`reports/corrections-analysis.md`)
7. **Assume the cheapest path to satisfying a predicate is not the work, and that an honest agent will find it anyway.** Defect 6 was disclosed by the agent that committed it. This is a property of goal-directed optimisation, not a discipline problem — so **the predicate must be checked against the thing it proxies for, adversarially, by someone who is not being scored on it.** (`reports/retrospective.md` §5.1)
8. **Perturbation testing is the replacement that worked** — small change-requirements implemented by blinded agents, as a pre-push fishing expedition. Four canaries surfaced **four pre-existing product defects while not looking for one**, in code already read by seven directed report agents, one blind reviewer, pyscn, ruff and 2,586 passing tests. *"High-coverage unit testing is necessary but mainly guards against regressions and rarely uncovers dormant bugs"*; this does the opposite, and it is **uniquely practical with agents and too labour-intensive to do manually**, which is why it is thin in the SDLC literature. (`reports/review-conclusions.md`, `reports/canary-results.md`)
9. **The reviewer's detection rate is a function of change-set size and collapses below some threshold** — the heaviest architectural objections arrived near the end, from code that had been present throughout, when the diffs got small. Arnon: *"Now that changes are fewer files I start noticing things. Even things that are not from this change set."* A large change set is not merely harder to review; **it is reviewed ineffectively while appearing to be reviewed.** So the review-cadence trigger fires on **change volume**, not elapsed time or step boundaries. (`reports/corrections-analysis.md`)
10. **Line coverage is the wrong shape for guarding a refactor.** The orchestration was at 100% line coverage with a **savagely skewed hit distribution**: distinct cases reaching each `no_match_fallback` branch were `allow` **2,336** : `ask` **34** : `allow_with_warning` **6** : `deny` **6**, with three defensive lines reached **zero** times. Corpus strengthening was gated on **mutation-based acceptance** — mutate each branch, prove the corpus catches it — rather than on case counts. (`TOO-45 delta - as-is against ideal.md`)

---

## A contradiction inside the source set, left unresolved

`reports/architecture-sweep-practices.md` closes by quoting the surprise-factor protocol's own admission that **"every architectural error caught in this ticket was caught by a human asking a direct question, and none by any metric, blind agent, or automated test"** — and draws from it that *architectural correctness, on this ticket, was caught by attention, not measurement.*

`reports/architecture-judge-backtest.md`, dated later (2026-08-10), reports the opposite for its own arm: a dedicated blinded architecture judge found **eight live defects in committed, reviewed code**, four of them verified against HEAD rather than taken on the judge's word, and caught **2 of 4** known architectural errors from proposals alone. It also records a **near-miss that only silent non-compliance saved**: the #10 spec instructed a coder to point the fitness canary at the new registry and delete the comment explaining why it was deliberately *not* imported — which would have destroyed an independent oracle by making probe and probed agree. The judge: *"This is the one instruction I would reject outright; the duplication there is an oracle, not drift."* **No review caught it.**

The reconciliation the backtest itself proposes is the actionable part and is worth carrying: **the judge sees architectural defects in proposals and not in diffs** — both hits and the near-miss were in the proposal arm, and the one committed subject carrying a known defect missed it. *"It did not find them by being cleverer — it found them by having nothing else to do."* So **run architectural review on proposals, not on diffs**, and read the sweep's "attention, not measurement" line as true of *diff-stage* instruments specifically. `[JUDGEMENT]` — this reconciliation is mine; neither source states it against the other.
