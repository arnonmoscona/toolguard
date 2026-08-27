---
title: TOO-45 surprise factor - production-only scoring
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/production-only-scoring
---

# Production-only scoring: expected versus outcome, SCOPE

Recomputation of the TOO-45 surprise series over **source files only**. "Source" = paths under `toolguard/` or `tools/`. Excluded: everything under `test/` and `docs/`, plus `README.md`, `llms.txt`, `.pyscn.toml`, `uv.lock`, `pyproject.toml`, `release-notes/`, `CLAUDE.md` and agent bookkeeping notes.

**Why this cut.** `RESULTS-LOG.md` records two confounds that are properties of the repository rather than estimator error: doc-file identity was mispredicted 3 times out of 3 (estimators reason "user-visible behaviour -> `README.md`"; this repo keeps topic files under `docs/`), and test-file identity the same way (estimators distribute tests across existing suites by subject; this repo adds one dedicated test module per feature). `78-scored.md` recommended in terms: *"treat doc-file identity separately, or exclude doc files from recall entirely."* This is that exclusion, applied to both.

**Line convention.** Insertions + deletions, summed per commit via `git show --numstat --format= <sha> -- toolguard tools`. For multi-commit items this is the **sum over commits**, not `git diff A..B`, which collapses lines added by one commit and rewritten by the next. That is why item 80's production total here (684) exceeds what `80-scored.md` derived from a collapsed range diff (its `tools/architecture_fitness.py` row reads 518/7 where the per-commit sum is 549). **All 15 totals supplied by Arnon were verified against git and all 15 match.**

---

## Headline

| item | prod files | prod lines | prod line recall | prod file recall | prod precision | scope verdict | under (lines) | over (files) |
|---|---|---|---|---|---|---|---|---|
| 03 | 10 | 1,220 | **75.2%** | 4/10 | 4/4 = 100% | **UNDER-SCOPED** | 302 | 0 |
| 04 | 7 | 721 | **97.1%** | 6/7 | 6/9 = 67% | BOTH (mild) | 21 | 3 |
| 10 | 10 | 240 | **87.9%** | 6/10 | 6/14 = 43% | BOTH | 29 | 8 |
| 15 | 4 | 369 | **93.5%** | 3/4 | 3/4 = 75% | BOTH (mild) | 24 | 1 |
| 18 | 3 | 107 | **84.1%** | 2/3 | 2/3 = 67% | BOTH (mild) | 17 | 1 |
| 20 | 4 | 300 | **96.0%** | 3/4 | 3/6 = 50% | BOTH (mild) | 12 | 3 |
| 22 | 2 | 63 | **100%** | 2/2 | 2/2 = 100% | **ACCURATE** | 0 | 0 |
| 39 | 2 | 255 | **97.3%** | 1/2 | 1/1 = 100% | UNDER (trivial) | 7 | 0 |
| 44 | 14 | 275 | **49.5%** | 10/14 | 10/17 = 59% | **BOTH (severe)** | 139 | 7 |
| 74 | 1 | 120 | **100%** | 1/1 | 1/5 = 20% | **OVER-SCOPED** | 0 | 4 |
| 77 | 9 | 1,030 | **100%** | 9/9 | 9/14 = 64% | **OVER-SCOPED** | 0 | 5 |
| 78 | 3 | 119 | **100%** | 3/3 | 3/7 = 43% | **OVER-SCOPED** | 0 | 4 |
| 79 | 4 | 429 | **13.8%** | 1/4 | 1/2 = 50% | **UNDER-SCOPED (severe)** | 370 | 1 |
| 80 | 9 | 684 | **94.6%** | 5/9 | 5/18 = 28% | BOTH | 37 | 13 |
| 85 | 5 | 118 | **100%** | 5/5 | 5/9 = 56% | **OVER-SCOPED** | 0 | 4 |

**Pooled production line recall: 5,092 / 6,050 = 84.2%.** Median item: **96.0%**. Mean item: 85.9%.

Scope verdicts collapse to: 5 pure OVER-SCOPED, 2 pure UNDER-SCOPED, 1 ACCURATE, 7 BOTH — of which five are BOTH only because a single small file was missed alongside a handful of inert predictions.

**Two items carry essentially all the under-scoping in the series: 79 (370 lines) and 03 (302 lines), followed at a distance by 44 (139).** Those three account for **811 of the 958 missed production lines (85%)**. The other twelve items miss 147 lines between them — an average of 12 lines each.

---

## Comparison against the all-files recall

| item | all-files line recall | production-only | delta | source of the all-files figure |
|---|---|---|---|---|
| 03 | 64.4% | 75.2% | **+10.8** | recorded, `03-scored.md` |
| 04 | 76.6% | 97.1% | **+20.5** | recorded, `04-scored.md` |
| 10 | 45.8% | 87.9% | **+42.1** | recorded, `10-scored.md` |
| 15 | 87.8% | 93.5% | +5.7 | recorded, `15-scored.md` |
| 18 | 52.0% | 84.1% | **+32.1** | recorded, `18-scored.md` |
| 20 | 95.0% | 96.0% | +1.0 | recorded, `20-scored.md` |
| 22 | 100% | 100% | 0 | recorded, `22-scored.md` |
| 39 | 99.1% | 97.3% | **-1.8** | recorded, `39-scored.md` |
| 44 | 44.0% | 49.5% | +5.5 | **computed here** (`44-scored.md` records file recall only) |
| 74 | 100% | 100% | 0 | recorded, `74-scored.md` |
| 77 | 61.1% strict / 90.1% concept | 100% | **+38.9** / +9.9 | **computed here** (`77-scored.md` records primitives only) |
| 78 | 91.6% | 100% | +8.4 | **computed here** |
| 79 | 15.2% | 13.8% | **-1.4** | recorded, `79-scored.md` |
| 80 | 91.1% | 94.6% | +3.5 | **computed here** |
| 85 | 100% | 100% | 0 | recorded, `85-scored.md` |

Mean delta **+11.0 pp**; median delta +5.5 pp. Median across items rises 87.8% -> 96.0%.

**Caveat on comparability.** The all-files column is not one instrument. Items 03/04/10/15 were scored against a basis that already excluded auto-generated agent bookkeeping files; 44/77/78/80 record file-level primitives and their line-weighted figures are computed here for the first time. So the delta column mixes "what the cut removes" with "which scorer drew the boundary." The direction is robust; the exact magnitudes are not.

---

## Does the cut give a cleaner signal, or just a different one?

**It removes a real, documented, systematic bias — and it does not change the thing the experiment is about.**

**What it does buy.** The three largest gains are 10 (+42.1), 77 (+38.9) and 18 (+32.1), and each has a named cause already in the record. Item 10's all-files diff carried 352 lines of unrelated gitignore-recovery work; `10-scored.md` computed its scope purity at 53% and recommended a scope-purity column precisely so that "recall measures commit hygiene rather than foresight." Cutting to production does most of that job for free. Item 77's all-files loss is entirely the four `docs/` files the estimator called `README.md`; item 18's is the downstream test set the ticket predicted and which turned out empty. In all three the recovered points are ones the series had already argued should not have been charged.

**What it does not buy — and this is the honest answer to the question.** Dispersion barely moves. Standard deviation across items goes **26.4 -> 24.1**. The distribution shifts up by ~11 points and stays about as wide, because the two items that were bad are still bad:

- **79: 15.2% -> 13.8%.** Slightly *worse*. The estimator predicted the fix was extractor-local ("I don't expect the floor's decision logic itself to change; only what reaches it"). It landed 283 lines in `compound.py` and 74 in `resolve.py`. That is a hidden-coupling finding (`C` in the original scoring), 100% production, and no exclusion touches it.
- **44: 44.0% -> 49.5%.** The estimator predicted the ambient accessor would land in `path_utils.py` and separately reserved a new module named `testability.py`. The work created `toolguard/ambient.py`, 120 lines — 44% of the item's production diff — and the miss is pure production.
- **39: 99.1% -> 97.3%.** Also slightly worse, because its only surprise (a 7-line comment edit in `tools/installer.py`) is production and its denominator shrank.

So: **the bottom two ranks are invariant under the cut, the top five all saturate at 100%, and the reshuffling is entirely in the middle.** Excluding tests and docs raises the level and compresses the top, but the interesting variance was never in tests or docs to begin with.

**A ceiling artifact the cut introduces.** Five of fifteen items now score exactly 100%, versus three before. A measure that saturates on a third of its cases is discriminating less, not more. Items 74, 77, 78 and 85 are now indistinguishable on recall and separable only on precision — where they range from 20% to 64%. On the production-only view, **precision carries more information than recall for the top third of the series**, which inverts the rubric the series adopted at item 18 (line-weighted recall as headline, precision as an integrity guard only).

**One figure to distrust.** Item 77 has the largest production denominator (1,030 lines) and 574 of them — 56% — are `toolguard/parser/bash_parser.py`, which is canopy-generated from the `.peg`. The estimator did predict it, at medium confidence, with the correct reason ("regenerated by canopy if the `.peg` changes at all"). But it is one prediction earning 574 line-credits, and it makes 77 the single heaviest item in the pooled figure. Pooled recall excluding generated code is **4,518 / 5,476 = 82.5%** rather than 84.2%.

**Verdict: cleaner in level, not in signal.** The cut is worth keeping as the *reported* figure, because it stops charging the estimator for two repository properties it cannot know and for commit hygiene it did not control. It is not a sharper instrument: it does not separate the items any better, it saturates more, and it leaves the series' two real failures exactly where they were. The correction the numbers actually argue for is the one `10-scored.md` already asked for — score the ticket's own work, not the commit — and the production cut is a cheap partial proxy for that, not a substitute.

---

## Scope error, per item, with the cause of each production miss

Cause codes: **(a)** a coupling the estimator could not see; **(b)** a file the ticket never mentioned; **(c)** scope impurity — work folded into the commit that the ticket never described.

### 03 — UNDER-SCOPED, 302 lines across 6 files. Precision 100%.
The only item in the series with perfect production precision, and it under-scoped by a quarter of the diff.
- `file_matching.py` **278 lines, new module** — **(a)**. `resolve.py` lost 320 lines and this gained 278: an extraction the ticket never proposed. The estimator predicted `resolve.py` would change heavily and was right about the pressure, wrong about where it went.
- `compound.py` 6, `permissions.py` 6, `config.py` 6, `hook.py` 4, `session_start.py` 2 — **(a)**, and *deliberately declined*: "predicting them would be hedging, and hedging is what precision scoring punishes." A rename ripples through import lines regardless of behaviour preservation. 24 lines, 2% of the diff — the estimator's judgement was cheap to be wrong about and `03-scored.md` already records it.

### 04 — BOTH, mild. Under 21 lines, over 3 files.
- `log_writer.py` 21 — **(a)**, right concept and wrong module: the estimator predicted `error_log.py` ("the reporter routes *to* the warning/error log") at medium. `error_log.py` did not change; `log_writer.py` did.
- Inert predictions: `session_warnings.py` (high confidence), `error_log.py`, `tools/architecture_fitness.py`.

### 10 — BOTH, over-scoping dominant. Under 29 lines / 4 files, over 8 files.
- `tools/maintenance.py` 13, `tools/architecture_fitness.py` 9, `tools/security_audit.py` 4, `tools/installer.py` 3 — **(b)**. The ticket enumerated four membership sets; these are further consumers of the tool vocabulary that its inventory did not list.
- The over-scoping is the interesting half. The estimator reasoned correctly that the tools tier held extra copies and named `tools/danger.py` (**[named] in the ticket**, high confidence) and `tools/takeover_audit.py`. Neither changed; four *other* tools-tier modules did. **Right tier, wrong modules — the same shape as item 80's headline finding.**
- Also inert: `rule_entry.py` (the estimator's flagged "main non-transcribed bet"), `resolve.py`, `permissions.py`, `api.py`, `config_types.py`, `testing/sandbox.py`.

### 15 — BOTH, mild. Under 24 lines, over 1 file.
- `auto_migrate.py` 24 — **(a)**. The estimator called it "the already-safe caller" and predicted only its *test* would need isolation wiring. In fact the caller had to learn the new decline outcome. Ticket-denied coupling, already recorded as `S`/`C` in `15-scored.md`.
- Inert: `constants.py` (low confidence, correctly hedged).

### 18 — BOTH, mild. Under 17 lines, over 1 file.
- `tools/consolidate.py` 17 — **(a)**, and *identified then declined*. The estimator wrote it out explicitly under "Uncertain / not predicted," arguing the analyzers' logic was unaffected and only their test expectations would move. Half right: the logic did move, by 17 lines.
- Inert: `tools/uninstall_readiness.py` (listed "for completeness, not because I expect it" — an honest low-confidence row).

### 20 — BOTH, mild. Under 12 lines, over 3 files.
- `tools/edit_proposal.py` 12 — **(b)**. A downstream consumer of the rationale strings; the ticket named `consolidate.py` and `maintenance.py` only.
- Inert: `permissions.py`, `tools/pattern_overlap.py`, `rule_sort.py` — all predicted at *low* confidence with the correct reason (the RA1 finding was filed separately and indeed stayed out).

### 22 — ACCURATE. The only clean item.
Two production files predicted, two changed, nothing else. `22-scored.md` correctly notes this is transcription: the ticket names `hierarchy.py:400`, `_config_without_allow` and `_normalised_body` directly.

### 39 — UNDER-SCOPED, 7 lines. Precision 100%.
- `tools/installer.py` 7 — **(c)**. `39-scored.md` records it as a comment-only edit. Nothing in the ticket asks for it; it rode along. The narrow-shape scope call was otherwise exactly right.

### 44 — BOTH, severe. Under 139 lines / 4 files, over 7 files.
The worst production result after 79, and the cause is module identity, not coupling.
- `ambient.py` **120 lines, new module** — **(a)**. The estimator predicted the `home()`/`cwd()` accessor would go into `path_utils.py` (which did change, 24 lines) and separately reserved a *different* new module, `testability.py`, per the ticket's own naming. It predicted that a new module would exist and got its name and role wrong. Scored strictly this is a miss; scored by claim it is a partial hit, and it is 44% of the item's production diff either way.
- `normalization.py` 8, `permission_migration.py` 8, `tools/transcript_harvest.py` 3 — **(b)**. Ambient readers the ticket's census did not enumerate.
- Inert (7): `error_reporter.py` and `log_writer.py` at **high** confidence, plus `install_provenance.py`, `config_divergence.py`, `subagent.py`, `testing/sandbox.py`, `testability.py`.

### 74 — OVER-SCOPED. 100% line recall, precision 20%.
One production file predicted at high confidence, one changed, 120/120 lines. The four inert predictions (`tool_spec.py` medium, `error_reporter.py`, `permission_resolution.py`, `config.py` low) were all hedges the estimator flagged as contingent on boundaries it could not verify without reading source. Zero surprises — still the series' cleanest unleaked call.

### 77 — OVER-SCOPED. 100% line recall, precision 64%.
All 9 changed production files were predicted, including both parser files and `command_model.py` at *low* confidence. Inert: `compound.py`, `constants.py`, `config_validation.py`, `hook.py`, `env_prefix.py` (new). `77-scored.md` attributes the perfect recall to design leak — the design was handed to the estimator — and that reading survives the production-only cut unchanged. Note the generated-code weighting above.

### 78 — OVER-SCOPED. 100% line recall, precision 43%.
Three predicted, three changed. Inert: `ambient.py`, `file_matching.py`, `compound.py`, `tools/architecture_fitness.py`. `78-scored.md`'s two refinements both apply here and neither is visible in the numbers: `ambient.py` was touched mid-flight and reverted (`T`, transient), and `file_matching.py` was a correct *claim* about reach delivered through a different mechanism.

### 79 — UNDER-SCOPED, severe. 370 lines across 3 files. Worst in the series.
- `compound.py` **283 lines** and `resolve.py` **74** — **(a)**, hidden coupling. The estimator's explicit cost-centre analysis concluded the ASK floor's decision logic would not change, "only what reaches it." The floor's plumbing lives in `compound.py` and `resolve.py`, and the fix rewrote it.
- `config_types.py` 13 — **(a)**, a new type the estimator did not anticipate needing.
- Inert: `parser/command_model.py`.
- This is the one item where the production-only cut makes the result *worse*, and it is the right answer: the failure was entirely in production code and nothing about tests or docs was ever mitigating it. It remains the series' strongest data point that the estimate tracks what the ticket transcribed rather than what the work required.

### 80 — BOTH, over-scoping dominant. Under 37 lines / 4 files, over 13 files.
- `tools/decision_ledger.py` 24, `auto_migrate.py` 5, `tools/environment_audit.py` 4, `tools/security_audit.py` 4 — **(b)**. `80-scored.md` puts it exactly: membership was discoverable only by running the checker the ticket built.
- The over-scoping is the finding. Thirteen inert predictions including `config.py` and `normalization.py` at **high** confidence. The estimator named the heavy path-handling tier; the residue was in the tools tier, because the heavy modules had already been cleaned in item 44. Precision 28%, the lowest in the series.

### 85 — OVER-SCOPED. 100% line recall, precision 56%.
Five predicted, five changed, including the new `claude_code_contract.py`. Inert: `testing/sandbox.py` (high), `log_writer.py`, `subagent.py`, `api.py` — all four inferred from one-line docstrings in the inventory, which is exactly where over-prediction should be expected and costs nothing.

---

## Cross-item patterns visible only in the production cut

**1. Over-scoping is the normal failure and it is nearly free; under-scoping is rare and expensive.** Predicted-but-inert production files: 54 across the series. Missed production files: 32. But the 54 inert predictions cost zero lines by construction, while 3 of the 32 misses account for 85% of all missed lines. **The distribution of cost is far more skewed than the distribution of errors** — a point the file-count scorings could not show.

**2. Every large under-scope is a new module or a control-flow relocation, never a call-site sweep.** The three big misses are `file_matching.py` (278, extraction), `compound.py`+`resolve.py` (357, relocation) and `ambient.py` (120, extraction). Call-site sweeps — the thing estimators over-predict most — never cost more than 37 lines. **An estimator that can predict where a new module will be carved would recover ~85% of the missing mass; nothing else on this list would move the number.**

**3. Both new-module misses were half-predicted.** Item 44 predicted a new module and named it `testability.py`; item 03 predicted heavy change in `resolve.py` and did not see the extraction out of it. Meanwhile item 85 predicted `claude_code_contract.py` correctly (the ticket named it) and item 80 predicted a new *test* file that did not exist to transcribe — the series' single strongest positive. So new-module prediction is not uniformly hard; it is hard exactly when the ticket does not name the module.

**4. Precision degrades with the breadth of the ticket's census, not with its difficulty.** The three lowest precisions are 80 (28%), 10 (43%) and 78 (43%). All three are census tickets — "find every site of X." An estimator handed a census enumerates plausible sites and is wrong about most of them, while a defect-site ticket lets it name two files and stop. This is a property of the ticket genre and the aggregate should carry it as a covariate rather than as an estimator score.
