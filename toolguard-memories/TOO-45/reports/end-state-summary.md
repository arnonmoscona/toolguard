---
title: TOO-45 end-state summary
type: note
permalink: toolguard/too-45/reports/end-state-summary
tags:
- task-memory
- TOO-45
- report
---

# TOO-45 — end-state summary

Written 2026-08-06, after Arnon committed the ticket as `a3e3f27`. This is the orientation document: what state the codebase is in now, what changed, what is verified, and what is deliberately left. The deeper analyses live in sibling reports in this directory.

## Table of contents

- [Verified state](#verified-state)
- [Scope: what was done, step by step](#scope-what-was-done-step-by-step)
- [The result that matters most](#the-result-that-matters-most)
- [What the numbers say](#what-the-numbers-say)
- [What is deliberately left](#what-is-deliberately-left)
- [What is newly true about this codebase](#what-is-newly-true-about-this-codebase)
- [Known weaknesses in the end state](#known-weaknesses-in-the-end-state)
- [Sibling reports](#sibling-reports)

## Verified state

Every number below was re-run by me against the committed tree, not taken from an implementing agent's report.

```
R1: PASS   R2: PASS   R3: PASS   R5: PASS   R6: FAIL (its own ticket, agreed)

suite                    2,387 tests OK
golden corpus            6,401 in-process + 61 end-to-end, no differences
--guard                  PASS, 12 canaries through the live hook binary
--layers                 completeness 100%, 1 direction violation (deliberate, R6)
ruff (--no-cache)        clean, with 4 new rules in force
doc links                all internal documentation links resolve
hook smoke test          responds correctly on installed copy AND working tree
```

Commits: `d5bdab3`, `d4123f4`, `11d1fd0`, then `a3e3f27` (the bulk, squashed). Pre-ticket baseline is `532de02`.

## Scope: what was done, step by step

| step | what it did |
|---|---|
| **prerequisites** | built the 6,401-case golden verdict corpus and `tools/architecture_fitness.py`; both became load-bearing for everything after |
| **R3** | zero production sites read structured data back out of rendered reason prose |
| **D4** | one undecidable floor, not two — proven by a mutation that flipped MISSED to CAUGHT |
| **D1a** | decision orchestration moved out of `Configuration` into `permission_resolution`, an engine-layer module that imports only `config_types` and never `toolguard.config` |
| **R1** | one runtime verdict type; 2 `__iter__` shims and 13 bare verdict tuples removed; `log_command` 12 params to 4; the compound audit trail fixed |
| **R5** | entry points are leaves; two console scripts split from the libraries they had become; `hook <-> tools.decision` cycle gone |
| **R2** | index-parallel access 3 to 0; prose invariant statements 4 to 0; both drift guards deleted; misaligned `ToolPatternLayer` state now unconstructible |

Beyond the plan: a ruff configuration was adopted (4 rules, with an explicit rejected list), and seven measuring-instrument defects were found and fixed.

## The result that matters most

**It is not a predicate. The compound audit trail was 83% lossy.**

`hook.py` recovered the per-sub-command audit breakdown by running a regex over the *reason prose*, keeping only segments containing `" -> "`. A `no_match_fallback`-allowed leaf produces no such segment, so those sub-commands executed and were **never written to the audit log**.

| | before | after |
|---|---:|---:|
| compound-allow cases that under-logged | 813 of 975 (83%) | **0 of 978** |
| sub-commands with no audit entry | 1,943 | **0** |
| logged `matched_rule` values with a stray trailing `]` | 79 | 0 |

811 of the 813 were in the real-traffic fixture — this was happening in ordinary use, not on synthetic edge cases. Worst observed: ten sub-commands executed, one entry written.

For a tool whose purpose is governing what an agent may run, an audit trail that silently omits 83% of compound decisions is a defect of a different character from anything else in this ticket. Closing it also exposed a **second, independent bug**: `resolve._deciding_sub_match` and `tools.decision._decide_bash` both attributed provenance using heuristics that only worked *because* escape-hatch leaves were missing from `sub_matches`. The first defect had been masking the second.

## What the numbers say

Against the true pre-ticket baseline `532de02`, production code only (`toolguard/`): **23 files changed, 4,143 insertions, 3,088 deletions**. Including tooling and tests: 52 files, 15,704 insertions, 10,946 deletions — the bulk of that being the corpus and the fitness tool, which are new infrastructure rather than churn.

| measure | before | after |
|---|---:|---:|
| tests | 2,186 | 2,387 |
| `config.py` lines | 2,905 | 2,509 |
| bare `(decision, reason, ...)` verdict tuples | 13 | 0 |
| `__iter__` tuple-compatibility shims | 2 | 0 |
| index-parallel array access sites | 3 | 0 |
| drift guards defending an index invariant | 2 | 0 |
| prose-parsing sites | 7 | 0 |
| live index-alignment prose invariant statements | 12 | 0 |
| `log_command` parameters | 11 | 4 |
| console-script lines that were secretly library code | 1,840 | 175 |
| layer direction violations | 3 | 1 |
| import cycles (in scope) | 1 | 0 |

**Four of these numbers were wrong when I first wrote this summary**, and were corrected by an independent measurement pass: prose-parsing sites are 7 not 3, live prose invariant statements 12 not 4, `log_command` was 11 parameters not 12, and `config.py` was 2,905 lines not 2,913. Two of the four were under-counts in the refactor's favour and two were over-claims. They came from reading step reports rather than measuring the trees — the ticket's own central failure mode, committed while writing the summary of that ticket.

### Wasteful computation eliminated, measured over the 6,401-case corpus replay on both trees

| | before | after |
|---|---:|---:|
| materialised parallel pattern strings | 2,298,537 | 0 |
| parallel tuples built | 119,400 | 0 |
| `_strip_tool_wrapper` calls | 2.38 M | 1.90 M (−20.2%) |
| reason render-then-re-parse round trips | 8,304 | 0 |
| literal-prefix comparisons over prose | 17,223 | 0 |
| drift-guard evaluations / times it fired | 3,996 / **0** | 0 / 0 |

**There is no CPU win.** Wall clock across the replay went 9.03 s to 8.76 s, which is noise. The gain is that ~2.4 M redundant string operations and every prose round trip are gone as *reasoning* burden, not as measurable time. Saying otherwise would be overselling it.

**No verdict changed at any point.** The corpus replays 6,401 in-process and 61 end-to-end cases; every step was gated on it reporting no differences. The hook's emitted JSON — an external contract with Claude Code — is unchanged.

## What is deliberately left

**One layer violation: `hook -> tools.decision`**, at `hook.py:697`, as a *local* import. This is deferred to R6 and the reason it stays local is a real constraint, not laziness: the hook is a per-process, per-tool-call binary, and hoisting that import to module level would load the entire tooling layer on the hot path of **every single invocation**. Demonstrated by execution that `decide()` is not on the live path at all — `toolguard.tools.decision` reaches `sys.modules` only under `--eval`. R6's proper fix is an `api` layer both callers can reach.

**One sanctioned prose-parse exclusion: `compound.py::fallback_kind_for_reason`.** Re-earned on evidence rather than grandfathered — both call sites were assessed by execution, prose and structural classification always agree, and site 1's real fix is blocked by 20 test closures hand-built against the narrow 3-tuple `resolve_one` contract.

**R6 itself**, as its own ticket. See `r6-reassessment.md` in this directory — it was scoped before five other steps happened, so its predicate describes a codebase that no longer exists.

**The audit-log format change** (R3 added a `Provenance` field and narrowed `Matched Rule`; R1e added per-sub-command entries and provenance) is logged as an additional step after the main refactor, per Arnon's standing call, along with the maintenance-skill question and release notes.

## What is newly true about this codebase

Things that were not possible or not true a week ago:

- **The engine's dependency on configuration is a measurable quantity.** Before D1a the decision walk was a method on `Configuration`, so `self` was the surface and "what does the engine need from config?" was not a well-formed question. It is now four config-query members plus two pure functions, established by instrumenting attribute access across the whole corpus.
- **Misaligned `ToolPatternLayer` state is unconstructible** — a `TypeError` — rather than guarded by a runtime length check. There is nothing left for a guard to defend, which is why both guards were deleted.
- **A second implementation of the decision cascade was found and removed, and it lived in the test suite.** `test_hook.py`'s fake config hand-implemented `resolve_permission_detailed` in ~35 lines whose own comment admitted it was "API-sync" with the real thing. Those hook tests were exercising a copy, not the product; the real engine is now entered 10 times through the double where it was previously entered zero times.
- **Four rules of lint are enforced** where prose conventions previously were not: no function-level imports, no `threading`/`asyncio`/`multiprocessing`/`concurrent.futures`, `max-args = 8`, and unused-noqa detection that makes every suppression self-cleaning.

## Known weaknesses in the end state

Stated plainly, because a summary that only lists wins is not useful.

- **The change-cost instrument is compromised.** The enrichment footprint counts identifiers, so it is blind to positional coupling and *rises* when tuple slots become named fields. It was TOO-45's pre-registered acceptance metric and it physically could not register R1's success. See `canary-before-after.md`.
- **The co-change metric is now poisoned for this repo.** `--metrics` reports `config.py` with 71 co-change partners and 134 fully-coupled pairs. The tool groups history by `TOO-nn` ticket token — deliberately, to remove a commit-splitting gaming vector — so one large refactor ticket collapses into a single logical change in which everything co-changes with everything. The anti-gaming design is exactly what breaks it. This needs a fix before co-change is trusted again.
- **`config.py` is still 2,509 lines** and still the largest module. D1a took the orchestration out; the load-vs-query split (the "candidate step" in the plan) was never done.
- **Seven instrument defects were found in one day**, six caught only by execution. There is no reason to believe the eighth does not exist.

## Sibling reports

| report | subject |
|---|---|
| `dependencies-before-after.md` | static and runtime dependency pictures, and where they disagree |
| `layer-separation-before-after.md` | layer map, measured and judged, including how gameable it is |
| `canary-before-after.md` | both canaries — the 12 guard cases and the change-cost metric — and what should replace the latter |
| `core-types-and-clarity.md` | the types introduced, the altitude argument, and what wasteful computation was eliminated |
| `canary-automode-experiment.md` | the tougher test: implementing a mode-dependent verdict enrichment in both trees |
| `retrospective.md` | lessons, principles, and how to prevent the rot next time |
| `r6-reassessment.md` | whether R6 is still worth doing, and in what shape |
