---
title: TOO-45 RESUME HERE
type: note
permalink: toolguard/too-45/too-45-resume-here
tags:
- task-memory
- TOO-45
- resume
---

# TOO-45 RESUME HERE

Rewritten at each stop. **Read this first**, then the reports in `toolguard-memories/TOO-45/reports/` and [[TOO-45 decision log]]. Written 2026-08-06, just before Arnon commits R6 and compacts the session.

## FIRST, ON A COLD RESTART

**Remind Arnon that this session must be put back into auto-mode.** A restart drops it, it is easy to forget, and unattended progress depends on it. Say it before anything else. Re-create an anti-stall cron if the session will run unattended — cron jobs are session-only and do not survive a restart. **Telegram MCP is DOWN**; the terminal is the only channel.

## State: R6 COMPLETE. Everything green. Awaiting Arnon's review of the reports.

```
R1 PASS   R2 PASS   R3 PASS   R5 PASS   R6 PASS
suite 2,409 OK          corpus 6,401 in-process + 61 e2e, no differences
--layers  0 violations, completeness 100%      ruff clean (--no-cache)
pyscn     73/100 (C), all 59 files parsed, no warnings
```

Arnon is committing R6 now. Before that commit the tree held: the four R6 stages, plus two disclosed production edits beyond R6's scope (`_PYPROJECT_READ_ERRORS` in `install_provenance.py`; the `resolve.py` false-purity docstring correction), plus a new `test/unit/test_static_analysis_coverage.py`, plus the reports directory.

## What R6 actually was

**The plan was replaced, on evidence.** R6-as-scoped was satisfiable by re-pointing a single import at the module where the symbol actually lives, with encapsulation unchanged — its one reported violation was an artefact. See [[r6-reassessment]]. What was done instead:

| stage | outcome |
|---|---|
| **S0** | rewrote the private-reach detector: derives its guarded set from `.pyscn.toml` instead of a hardcoded list, follows re-exports so an import re-point cannot launder a violation, catches attribute access and `getattr`, and **publishes a known-limitations block** naming four things it cannot see |
| **S1** | deleted all 5 real private reaches. `takeover_audit` got a new public `strip_tool_wrapper` rather than the `RuleEntry.stripped_pattern` I suggested — the agent checked and was right: those call sites handle raw native settings strings that are never `RuleEntry`s |
| **S3** | unified `Decision` into `RuntimeVerdict`; `_verdict_from_decision` deleted outright. `Decision` was 7/8 fields verbatim plus one rename — a copy that drifted, not an altitude |
| **S2** | `decide()` moved into a new `toolguard/api.py` in a new `api` layer between `engine` and `runtime`; both `hook.py` and `tools/` consume it; the last layer violation is gone |

**S4 (the 32-name config facade) was dropped deliberately** — no measured pain, and it is not what R6 described.

## OPEN — needs Arnon

**1. `tools/decision.py` is now a 38-line re-export**, and ~8 production modules still import `decide` from it rather than from `toolguard.api`. The layer graph is clean (tooling -> api is downward) and identity is pinned by tests, but the import statements do not say what the architecture means. Arnon said he will look closely and get back before push. My recommendation: do the ~15-edit sweep.

**2. pyscn reports `Architecture: 84% compliant` while our own checker reports 0 violations and 100% completeness.** Unresolved on purpose — Arnon warned against rat-holing, and the two are probably not measuring the same thing. Logged as an open question, not a blocker.

## Reports delivered — Arnon is partway through reading them

In `toolguard-memories/TOO-45/reports/`:

| file | subject |
|---|---|
| `end-state-summary.md` | orientation; **note it self-corrects four numbers I originally got wrong** |
| `dependencies-before-after.md` | static AND runtime dependency pictures, and where they contradict |
| `layer-separation-before-after.md` | measured + judged, including how gameable the map is |
| `canary-before-after.md` | both canaries, and what should replace the change-cost one |
| `core-types-and-clarity.md` | types introduced, the altitude argument, waste eliminated |
| `canary-automode-experiment.md` | the controlled before/after feature experiment |
| `retrospective.md` | 100 KB, 12 sections, TOC — lessons and principles |
| `r6-reassessment.md` | why R6 was replaced |
| `change-challenges.md` | 8 future-change tests, by an agent kept **blind** to this ticket |
| `follow-up-queue.md` | **what happens next — read this one with the summary** |

## 2026-08-06 (later): the micro-canary suite, and what it produced instead

Arnon's feedback on the reports identified the big canary's measures as wrong — file count measured the SIZE OF THE REQUIREMENT, not the difference between the trees, and co-change was poisoned because the requirement itself coupled the files. Agreed and acted on. The replacement design is `reports/micro-canary-protocol.md`: many small requirements instead of one big one, measures about maintainability and reviewability rather than volume.

**Twelve micro-requirements were authored by an agent kept blind to all source** (`reports/micro-requirements-blind.md`). Nothing was dropped in triage; the suite is stratified into **home ground** (code TOO-45 reworked) and **neutral ground** (code it never touched), reported separately and never pooled, because a win on home ground is circular.

**No canary has been run.** Four measuring instruments were built and adversarially attacked first, and the attacks produced two results that ended the mechanical approach:

1. **Any per-location rate is unsound for comparing codebases that differ in factoring granularity** — the denominator moves with the variable under test. And **any AST-level count of "where the logic lives" rewards duplication**, because abstraction moves logic out of syntactic view. Demonstrated end to end: the same requirement inlined four times scored perfect; factored behind one predicate scored worst-possible.
2. **`surprises = leaked_concepts + n(1-p)`.** The count carries noise proportional to n; the rate divides the signal by n. Verified by Monte Carlo. Neither is granularity-invariant, and they disagree at every realistic prediction quality. **I had promoted the count and demoted the rate — I promoted the biased one.**

**Mechanical scoring is therefore abandoned. Tools gather evidence; judges score.** The surviving artefacts are the surprise LIST (adjudicated blind, one question per location), the classifier as an exact occurrence finder (identity matching independently proven exact twice), and the inventory's blindness guarantee (audit-hook verified: 170 opens, none outside the tree, no subprocess, no VCS path). Where a number is still wanted it is a count of adjudicated leaked CONCEPTS, with the concept mapping fixed before unblinding.

**Cost and worth**: four agents, zero implementations. The alternative was twelve requirements implemented twice and scored by two instruments that both, independently and for different reasons, preferred monoliths. Both passed their own hazard suites. Both were validated on real data. Both produced plausible numbers. **I accepted a result from one of them before the adversary ran.**

Tools now in the tree, all evidence-only: `tools/change_role_classifier.py`, `tools/touch_set_inventory.py`, `tools/touch_set_score.py`, plus their tests. Suite verified at **2,586 OK**.

## NEXT, in order

1. **Wait for Arnon's report feedback.** He is mid-review and pausing overnight. Do not start new work on his behalf without it.
2. **Bug-fix ticket** (accepted, ticket not yet created): `log_writer`'s `sys.exit(1)` fail-open first, then the pattern-string join key, the three failed once-per-session attempts, the `docs/config-sync.md` marker-path mismatch. Detail in [[follow-up-queue]].
3. **Change challenges** — CC-1 and CC-4 as a pair, then CC-2 immediately after CC-1 as a **controlled contrast**, plus the semver calibration control. These are **throwaway measuring instruments**, implemented in copies and discarded, never merged.
4. **Pre-push checklist — deferred by Arnon until much closer to a push.** Coverage (done, numbers in the log), version bump, release notes, `/documentation-review`, the maintenance/security-audit skill questions, `install.md`, the audit-log format change step, and the post-push `uv tool upgrade` + smoke test.

## Standing failures of mine, with this ticket's evidence

1. **Claims from a representation rather than execution.** Every correction all day came from something that ran — including four wrong numbers in my own end-state summary, written *about* this very lesson.
2. **I fix instances, not classes.**
3. **A turn that ends with intentions ends.** Unattended stretches need a pending agent or a scheduled wakeup.
4. **I trusted instruments without checking they could express the outcome.** Eleven instrument defects now. The worst was mine: **`--guard PASS 12/12` was quoted as a safety signal after every step and was measuring the INSTALLED v0.5.1 binary, i.e. master, the whole time.** The SessionStart hook printed "INSTALLED COPY IS STALE" in the first message of the session.
5. **Rename-and-count measures NAME COUPLING, not work.** Renaming `hard_deny` breaks 106 tests; the real change to the same code breaks 0.
6. **NEW: blindness beat context.** An agent forbidden from reading this ticket's analysis found six real defects that seven directed agents missed. Deliberately un-brief at least one reviewer on any long effort.
