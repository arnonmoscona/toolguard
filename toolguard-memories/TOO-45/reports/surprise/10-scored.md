---
title: TOO-45 surprise factor - item 10 scored (line-weighted)
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/10-scored
---

# Item 10 scored — commit `2113d02`

Retro-scored 2026-08-21 under the **line-weighted** rubric adopted at item 18. `10-tool-spec.md` carries two earlier file-count scorings (80% on a 10-file set, rescored to 63% on a 16-file set); this supersedes both, and the commit turns out to be **36 files**, not 16.

**Basis**: the commit diff minus three auto-generated agent bookkeeping files (1,127 lines). That leaves **36 files / 1,144 changed lines**.

**This item needs a second basis, and the reason is a genuine finding.** The commit fixes an unrelated `.gitignore` defect — an unanchored `.claude` pattern that had silently excluded ten verdict-corpus fixture files from git — so **352 lines of the diff are pre-existing files becoming tracked, not work anyone did.** Both figures below.

## Headline

| metric | full basis (36 files) | gitignore-recovery excluded (26 files) |
|---|---|---|
| **line-weighted recall (headline)** | **524 / 1,144 = 45.8%** | **524 / 792 = 66.2%** |
| wrong-reason discounted | 483 / 1,144 = **42.2%** | 483 / 792 = **61.0%** |
| file recall | 13 / 36 = 36.1% | 13 / 26 = 50.0% |
| precision (integrity guard only) | 13 / 25 = 52% | 13 / 25 = 52% |
| leak | **heavy** — the ticket names five files with line numbers | |

**Worst of the four items rescored in this batch on either basis**, and the reason is not estimator quality — it is that the commit carries three bodies of work the ticket contained none of.

## Per-file — 36 files

### Predicted and changed (13 files, 524 lines)

| file | lines | confidence | reason check |
|---|---|---|---|
| `test/unit/test_tool_spec.py` (new) | 172 | medium | right |
| `toolguard/tool_spec.py` (new) | 125 | **low** | right — and the low-confidence alternative beat the high-confidence one (below) |
| `test/unit/test_hook.py` | 62 | high | right (payload key read from the registry) |
| `test/unit/test_tools_transcript_harvest.py` | 29 | low | right |
| `toolguard/constants.py` | 26 | high | **[named]** right |
| `test/unit/test_configuration.py` | 24 | medium | **wrong reason** |
| `toolguard/tools/transcript_harvest.py` | 21 | high | **[named]** right |
| `toolguard/hook.py` | 18 | high | **[named]** right |
| `test/verdict_corpus/fixture_loader.py` | 14 | low | right |
| `toolguard/config_validation.py` | 14 | high | **[named]** right |
| `technical-notes.md` | 10 | medium | **wrong reason** |
| `toolguard/config.py` | 7 | medium | **wrong reason** |
| `.pyscn.toml` | 2 | low | right (new module needs a layer entry) |

### Changed and not predicted (23 files, 620 lines)

| file | lines | cause |
|---|---|---|
| `test/verdict_corpus/configs/realistic/project/...toml` | 107 | `D` (gitignore recovery) |
| `docs/configuration.md` | 71 | `R` |
| `test/verdict_corpus/configs/realistic/home/...toml` | 60 | `D` (recovery) |
| `test/verdict_corpus/configs/override_breadth/project/...toml` | 60 | `D` (recovery) |
| `test/unit/test_hook_eval.py` | 52 | `R` (review-driven seam pinning) |
| `test/unit/test_verdict_corpus.py` | 46 | `R` (review-driven seam pinning) |
| `test/verdict_corpus/configs/ask_provenance/project/...toml` | 34 | `D` (recovery) |
| `test/verdict_corpus/configs/override_breadth/home/...toml` | 33 | `D` (recovery) |
| `test/verdict_corpus/README.md` | 26 | `R` |
| `test/verdict_corpus/configs/ask_provenance/home/...toml` | 20 | `D` (recovery) |
| `test/verdict_corpus/configs/parse_failure/project/...toml` | 13 | `D` (recovery) |
| `toolguard/tools/maintenance.py` | 13 | `R` (rename from review) |
| `test/verdict_corpus/configs/hierarchy_conflict/project/...toml` | 11 | `D` (recovery) |
| `test/verdict_corpus/configs/hard_deny.toml` | 11 | `R` |
| `docs/install.md` | 11 | `R` |
| `tools/architecture_fitness.py` | 9 | `E` |
| `test/verdict_corpus/configs/hierarchy_conflict/home/...toml` | 9 | `D` (recovery) |
| `AGENTS.md` | 9 | `R` |
| `.gitignore` | 7 | **`D`** |
| `test/verdict_corpus/configs/pattern_forms.toml` | 6 | `R` |
| `test/verdict_corpus/configs/parse_failure/home/...toml` | 5 | `D` (recovery) |
| `toolguard/tools/security_audit.py` | 4 | `R` (rename from review) |
| `toolguard/tools/installer.py` | 3 | **`C`** |

**False positives (12, cost nothing):** `tools/danger.py` (high — already fixed before the ticket was written), `rule_entry.py` (high), `resolve.py`, `permissions.py`, `api.py`, `config_types.py`, `testing/sandbox.py`, `tools/takeover_audit.py`, `test_architecture.py`, `test_tools_danger.py`, `test_rule_entry.py`, `test_api.py`.

## Cause tally — 23 misses, 620 lines

| cause | files | lines | what |
|---|---|---|---|
| `D` — latent defect and its consequences | 11 | 359 | the `.gitignore` anchoring bug (7 lines) plus the 352 lines of fixture it had been hiding |
| `R` — requirement added after the estimate | 10 | 249 | the `governed_tools` default change (6 files) and review-driven work (4 files) |
| `C` — hidden coupling | 1 | 3 | `tools/installer.py`'s fifth hardcoded tool tuple |
| `E` — estimator ignorance | 1 | 9 | the dev instrument's canary set |

**Only 12 of 620 unpredicted lines are attributable to the estimator at all.** That is the real result of this item, and no file-count or line-count recall figure shows it.

## FINDING A — 98% of the unpredicted diff is work the ticket did not contain, in three separable bodies

1. **The `.gitignore` defect (`D`, 359 lines).** `.claude` was unanchored, so it matched at every depth and excluded ten multi-file corpus fixtures under `test/verdict_corpus/configs/*/{home,project}/.claude/`. *"A fresh clone got 14 of the 24 corpus configs."* Fixing it added 352 lines of already-existing fixture to git. **A real and valuable find — the corpus was partly fictional on any clone — and completely unrelated to making a supported tool a described thing.**
2. **The `governed_tools` default change (`R`, ~180 lines across `docs/configuration.md`, `docs/install.md`, `AGENTS.md`, `test/verdict_corpus/README.md`, two fixture `.toml` files, and inside three of the hits).** The default moved from `('Bash',)` to `('Bash','Read','Write','Edit')`. That was a separate coder task folded into this commit; the commit message does not mention it at all.
3. **Review-driven work (`R`, ~115 lines).** The `GOVERNED_TOOLS` → `BUILTIN_TOOLS` rename reaching `maintenance.py` and `security_audit.py`, and the two seam-pinning test modules the review demanded after measuring the test-to-production ratio at 0.8:1 against a repo norm of 1.9:1.

Together those three account for **608 of the 620 unpredicted lines (98%)**. The first two are unrelated to the ticket entirely — **493 lines, 80% of the unpredicted diff, and 47% of the whole scored diff once the governed-tools edits sitting inside three of the hits are counted.** Only the third is downstream of this ticket.

**The scoring consequence is structural, not a detail.** A touch-set estimate is a prediction about *one ticket*. When two unrelated bodies of work land in the same commit, recall measures commit hygiene rather than foresight. **Recommend the aggregate carry a "scope purity" column** — what fraction of the scored diff is the ticket's own work. For item 10 that is **610 / 1,144 = 53%**, and it, not 45.8%, is what explains this item's rank.

## FINDING B — the low-confidence prediction beat the high-confidence one, and the estimator had said which evidence would decide

Its **high**-confidence bet was that the registry lands in `constants.py`. Its **low**-confidence alternative was a new `tool_spec.py`, reasoned as *"matching the project's recent habit of promoting a concept into its own described thing."* The registry landed in `toolguard/tool_spec.py`, 125 lines, and `constants.py` became a 26-line set of derived re-exports.

It also predicted `.pyscn.toml` at low confidence **conditionally** — *"required only if the registry lands in a new module"* — which is a correctly-conditioned prediction, and it resolved the way the low branch said. This is the same ratchet-file awareness that finding 25 credits at item 85, arriving earlier in the series than that finding assumes.

**What the confidence column measured here was familiarity, not likelihood.** `constants.py` is the obvious home from a file inventory; a new module is the habit of this codebase, which the estimator named and then under-weighted.

## FINDING C — three hits changed for the `governed_tools` default, not for the ticket

| file | predicted reason | what actually changed |
|---|---|---|
| `technical-notes.md` (10) | *"the design rationale for a new described concept"* | the documented default going from `('Bash',)` to four tools |
| `test/unit/test_configuration.py` (24) | *"supported-tool validation and `additional_supported_tools` behaviour"* | four assertions on the new default, plus a fixture rewritten because its `governed_tools` value stopped being distinguishable from the default |
| `toolguard/config.py` (7) | *"loads `additional_supported_tools` and indexes rules per tool"* | `governed_tools()` returning `DEFAULT_GOVERNED_TOOLS` |

All three are hits by file and all three changed for work the ticket never contained. Discounting them: **42.2%** full basis, **61.0%** adjusted.

`config.py` is the closest call — the registry import does land there, and "the supported-tool question is answered here at load time" is broadly true of the line that changed. Flagged as wrong-reason rather than resolved generously, because the *specific* claim (`additional_supported_tools`, per-tool rule indexing) is not what moved.

## FINDING D — the `C` is 3 lines and it is the item's own thesis

`tools/installer.py` built `("Read", "Write", "Edit")` from a bare tuple wired to no constant, in a module the ticket never mentions. **The ticket's premise is that tool membership is scattered; the ticket's own inventory missed an instance of exactly that.** The estimator predicted the *mechanism* precisely — *"the enumeration method that produced 'four' is the same method that already missed two"* — and could not name the file.

Same shape as item 04's finding D: **two consecutive tickets whose evidence did not survive measurement.** Here the ticket claimed four membership sets; measurement found three live, one dead with zero readers, and three further copies plus a look-alike. The cheap fix stands: **count when writing the ticket, not when writing the code.**

## Reconciliation with the contemporaneous scoring

`10-tool-spec.md` records `|A| = 10`, rescored to 16. The commit contains 36 scored files. The gap is the `.gitignore` recovery (11 files), the `governed_tools` default work (6 files), and `test/unit/test_hook.py`/`test/unit/test_configuration.py`/`test/verdict_corpus/README.md`/`docs/*`. Third item in this batch where the contemporaneous touch set was taken from a working tree rather than the commit.

## Leak

**Heavy.** The ticket names five files with line numbers; four of them changed, for 79 lines.

- recall on the 31 unnamed files: **445 / 1,065 = 41.8%**
- on the adjusted basis (21 unnamed files): **445 / 713 = 62.4%**

Unusually, the leak discount barely moves this item — because the named files are small and the unpredicted mass is unrelated work. **This is the first item in the series where leak level is not the dominant explanation of recall**, and it should be flagged as such in the leak table, not fitted to the curve.
