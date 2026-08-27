---
title: 02-campaign-cost-data
type: note
permalink: toolguard/durable/02-campaign-cost-data
tags:
- TOO-45
- durable
- cost
- measurement
---

# Campaign cost data — extracted before deletion

Extracted 2026-08-23 from `toolguard-memories/` ahead of the unversioned-note deletion. **Nothing here is normalised, converted, summed or ranked across currencies.** Wall-clock, tokens, dollars and agent-run counts are four different things and sit in four different columns; where two sources disagree, both rows are present and the disagreement is listed in the "Conflicts" section.

---

# SUMMARY — read this instead of the tables

**Added 2026-08-24 after Arnon's critique: *"When I ask for statistics I care about meaningful summary stats, not for long tables that do not help to make decisions."* He was right. Everything below the horizontal rule further down is a filing cabinet. This section is the part that answers a question.**

## Where the time actually goes

Extracted from **574 phase rows across 122 tasks and 43 tickets** (`data/phase-costs.tsv`); **119 tasks** record both a planning and an implementation figure and are the basis for every number here.

| phase | median share of recorded effort | p25–p75 |
|---|---|---|
| implementation | **40.7%** | 28.6–52.9 |
| planning | **29.6%** | 23.1–39.1 |
| quality (verification + self-review) | **14.7%** | 0–25.0 |
| report | 7.0% | 0–10.0 |

**Planning + quality + report is 53.5% of recorded effort; implementation is 40.7%.** The median planning:implementation ratio is **0.77**, and its interquartile range is **0.45–1.33** — planning is routinely *larger* than implementation.

**Three caveats that bound every figure above.** Per-phase minutes are **effort shares, not a partition of elapsed time**: all eight tasks whose parts fail to match their stated total overshoot it, and the sources self-diagnose why (*"they do not sum to wall clock because four full suite runs at ~52s each ran inside them"*). So shares are computed against the sum of parts, never the stated total. `verification` and `self_review` are **the same activity under two house names** and are combined. And **every reviewer-side report gives a total only** — this is the shape of *implementer* effort and says nothing about how review time divides. 507 of 574 rows are the source's own estimate; 67 are clock-derived.

## The finding that bears on how to spend

| | median size | planning | implementation | quality |
|---|---|---|---|---|
| smaller half (n=59) | 31 min | 30.8% | 34.8% | 15.4% |
| larger half (n=60) | 70 min | **28.2%** | **47.7%** | 14.3% |

**Planning share does not rise with task size — it falls slightly, while implementation share grows 13 points. Quality effort is flat at ~15% regardless of size.** In absolute minutes planning roughly doubles, but sub-linearly against implementation. The bigger, riskier tasks received proportionally *less* of both the things that are supposed to de-risk them. **Qualified, moderate confidence**: the pattern is consistent across 119 tasks, but "size" here is self-reported effort, which is partly an *outcome* of how well the task was planned — so some of this could be reversed causation.

## Did the expensive phases pay for themselves?

Arnon's hypothesis, from experience rather than from this data: planning makes implementation cheaper and errors rarer; verification is the quality backstop; both reduce long-term maintenance cost. The corpus can speak to the first two in part, and **cannot speak to the third at all** — task-scoped records cannot see maintenance cost, and no claim here should be read as trying.

**The evidence splits the hypothesis rather than confirming or refuting it** (full cases in `06-planning-attribution.md`, 82 findings across 30 rounds, and `07-escaped-defects.md`, 23 chains):

- **Planning strongly reduces the cost of *claims*.** All 20 confirmed planning-preventable findings concern something a change asserts — about another file, a project rule, a count, or its own diff. Cleanest instance: ticket 74 round 2, whose *only* blocking finding cost **~1h05m / ~$9–12** and was three change-history paragraphs added to test docstrings **in the same commit as a sweep deleting nine of them under a rule the project had written down verbatim.**
- **Planning is close to worthless for *behaviour under composition*.** 39% of findings were execution-only, and that class contains **all three serious security defects, every one of which failed silently.** Ticket 79 round 1 — a leaf `kind` reclassification silently downgrading an unoverridable `hard_deny` to `ask` — was found only by a HEAD-vs-tree differential. The suite was green; the corpus replay showed nothing.
- **So the two are not substitutes: planning buys down the cost of what you assert, verification buys down the cost of what the code does.** Each is documented failing in the other's domain.
- **The strongest single datum is a planning intervention, and it is a within-ticket contrast** — immune to the difficulty confounding that makes every cross-ticket comparison here unusable. Ticket 77 phase 1 (grammar reviewed **alone**, before any Python, per the project's two-phase rule) produced **the only clean blinded reviews in the entire corpus** — two PASSes, zero blocking, on differential evidence over 23,594 then 28,770 distinct commands. Ticket 77 phase 2, the combined change, drew 3 blocking findings.
- **Verification's cost when skipped is demonstrated but small in this sample.** Six confirmed escaped-defect chains total **~4–8 hours of recoverable agent time against a 35h38m phase**; two cost essentially nothing; none reached a user, because the corpus contains **no user-originated ticket at all**.
- **The counterweight, which should be weighted heavily**: `Path.absolute()` escaped **six** blinded review rounds, and the technique that found it appears nowhere in the corpus beforehand. Six competent reviews is not a weak instrument, and against that defect it produced nothing.

## The two findings neither hypothesis predicted

**1. The recoverable cost is in follow-through, not in the phases.** In four of six confirmed escaped-defect chains the failure was **instance-fixing rather than class-fixing, with the technique already in hand.** Chain C1 is explicitly not a verification failure: item 10's review found the right class and fixed two of three files, leaving the third **in `hook.py`, the component that governs.** Every governed non-builtin tool was bricked for eleven days; ticket 74 re-derived it from scratch five days later without reference to it; the residual is still open as TOO-51.

**2. The largest recoverable planning cost is *between* rounds, not before implementation.** Four documented escalations — ticket 18's curl recipe across four rounds, 80's "most modules", 78's dead variant, 77's `+=` grammar gap — each burned a full extra round on something **a previous round had already written down as non-blocking.** The information existed, in the campaign's own files, and was walked past. No project rule covers this today.

## What this cannot tell you

Long-term maintenance cost. Whether the two-phase rule generalises beyond grammar work — **my own judgement, low-to-moderate confidence, is that it partly does not**: a `.peg` file is small, formally checkable, and has a mechanical differential (regenerate and diff over a corpus), and most changes have none of those properties. Any cross-ticket correlation, because n is 8 usable tickets and the corpus itself records that the highest-round ticket's extra rounds *"caught errors of the coordinator's, not the implementers'."* And the true review yield: the "27 of 27 rounds found something blocking" figure is a floor, not a rate — the one round recorded as clean has no surviving file.

---

## Search scope, stated plainly

| quantity | count |
|---|---|
| `.md` files under `toolguard-memories/` | **685** |
| files carrying a cost / elapsed / timing / token / budget **heading** | **179** |
| further files carrying a figure with **no** such heading | **43** |
| candidate files opened and inspected | **222** |
| distinct files cited as the source of at least one row below | **152** |
| rows extracted | **170** — 124 implementer-side (table A), 22 reviewer-side (table B), 24 campaign/aggregate (table C) |

**On the "104" figure in `VERIFIED-deletion-triage.md`.** That number was measured over the *delete pile* only, by heading. Measured over the whole tree, by heading, the count is **179**; adding figure-bearing files with no heading gives **222** candidates, of which **152** are cited below as the source of at least one row. So 104 was not wrong — it was scoped to the delete set and to one detection method. The convergence note in the same document reports a second agent measuring **124 files carrying a cost figure**; this sweep's 152 is the same order and the difference is again the detector and the scope. **All three are an order of magnitude above the triage's original "9".**

## Provenance key

| tag | meaning |
|---|---|
| **M** | MEASURED — read from a clock, from file timestamps, or from git commit timestamps, and the source says so |
| **E** | ESTIMATED — the source itself calls it approximate / rough / "not a metered figure" |
| **M/E** | elapsed measured from timestamps, cost estimated (the most common shape) |
| **R** | RECALLED — the source quotes a figure it did not itself measure |

**Every dollar figure in this document is E.** No source in the corpus queried a billing or token-usage API; the phrase *"not a metered figure"* or equivalent appears in most of them. Token counts marked E are the author's own reconstruction from tool-call volume; the two token figures marked M (`in-process-mutation-testing.md`, n=12) are the only ones stated as a measured range.

---

# Table A — implementer / coder side

Model column records what the source names. Where the source says "Sonnet-class" or "Sonnet pricing" without a version, that is what appears.

| # | ticket / task | wall-clock | tokens (whose) | $ (whose) | model | runs / rounds | prov | source file |
|---|---|---|---|---|---|---|---|---|
| A1 | TOO-8 follow-up — loader deletion + Bash takeover coverage | ~22 min | ~120k in / ~15k out (implementer) | ~$0.80 | Sonnet 4.6 | 1 | E | `implementation/TOO-8 Follow-up- Loader Deletion and Bash Takeover Coverage Implementation Report.md` |
| A2 | TOO-15 P0 keystone | ~32 min | ~80k in / ~15k out (impl) | ~$0.50-0.75 | claude-sonnet-4-6 | 1 | E | `implementation/TOO-15 P0 Keystone Implementation Report.md` |
| A3 | TOO-15 P0 analyzers | ~60 min | ~90k in / ~25k out (impl) | ~$0.80-1.10 | claude-sonnet-4-6 | 1 | E | `implementation/TOO-15 P0 Analyzers Implementation Report.md` |
| A4 | TOO-15 P1 audit context export | ~25 min (sum of phases; no stated total) | — | ~$0.48 | — | 1 | E | `implementation/TOO-15 P1 Audit Context Export Implementation Report.md` |
| A5 | TOO-15 P1 security audit aggregator | ~9 min (06:46→06:54) | — | ~$0.08-0.12 | Sonnet 4.6 | 1 | M/E | `TOO-15/TOO-15 P1 Security Audit Aggregator Implementation Report.md` |
| A6 | TOO-15 P2-A.1 consolidation core | ~60 min | — | ~$0.65 (S1 $0.40 + S2 $0.25) | — | 2 sessions (context compaction) | E | `implementation/TOO-15 P2-A.1 Consolidation Core Implementation Report.md` |
| A7 | TOO-15 project-root consolidation | ~30 min | — | ~$1.50-2.50 | Sonnet 5 | 1 + coordinator gap-fix | E | `implementation/TOO-15 Project Root Consolidation Implementation Report.md` |
| A8 | TOO-16 distribution tooling enhancement | ~30 min | ~100-150k total (impl) | ~$0.50-0.75 | claude-sonnet-4-6 | 1 | E | `implementation/TOO-16 Distribution Tooling Enhancement Implementation Report.md` |
| A9 | TOO-17 IR design + implementation | ~90 min | — | ~$0.85 | — | 1 | E | `implementation/TOO-17 Implementation Report.md` |
| A10 | TOO-17 continuation after compaction | ~15 min | ~40k (impl) | ~$0.08 | — | 1 | E | `implementation/TOO-17 Implementation Report.md` |
| A11 | TOO-19 Phase 0a increment 0 | ~65 min | — | ~$2-4 | Sonnet-class | 1 | E | `TOO-19/TOO-19 Phase 0a increment 0 - Coder Implementation Report.md` |
| A12 | TOO-19 Phase 0a increment 1 | ~9 min (12:08→12:16) | — | ~$0.25-0.30 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 Phase 0a increment 1 - implementation report.md` |
| A13 | TOO-19 Phase 0a increment 2 | ~6-7 min (18:02:47→~18:09) | ~30-35 tool calls | few cents to ~$0.10 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 Phase 0a increment 2 implementation report.md` |
| A14 | TOO-19 Phase 0a increment 4 | ~11 min (19:51→20:01) | — | ~$0.75 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 Phase 0a increment 4 implementation report.md` |
| A15 | TOO-19 Phase 0a increment 6 | ~58 min | — | ~$1.95 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Phase 0a increment 6 implementation report.md` |
| A16 | TOO-19 Phase 0a increment 8 | **active ~1h45m-2h; wall-clock ~6h11m** (see conflict C6) | — | ~$4.50-5.20 | Sonnet 5 | 1 | E (both) | `TOO-19/TOO-19 Phase 0a increment 8 implementation report.md` |
| A17 | TOO-19 Phase 0a increments 7 and 9 | ~41 min | — | ~$1.15 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Phase 0a increments 7 and 9 implementation report.md` |
| A18 | TOO-19 Phase 0a RuleEntry.raw sentinel fix + coverage | ~8 min (08:55→09:02) | — | well under $1 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 Phase 0a - RuleEntry.raw sentinel fix + coverage - Implementation Report.md` |
| A19 | TOO-19 Phase 0b increments 1-2 | ~43 min | ~150-250k incl. context (impl) | ~$1-2 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Phase 0b increments 1-2 implementation report.md` |
| A20 | TOO-19 Phase 0b increments 3-4 | ~1h55m | — | ~$3-5 | Sonnet-class | 1 | E | `TOO-19/TOO-19 Phase 0b Increments 3-4 Implementation Report.md` |
| A21 | TOO-19 Phase 0b increments 5-6 | ~26 min | — | ~$0.75 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Phase 0b Increments 5-6 Implementation Report.md` |
| A22 | TOO-19 Phase 1 increments 3 and 5 | ~30 min | — | ~$0.90 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Phase 1 increments 3 and 5 implementation report.md` |
| A23 | TOO-19 Phase 1 increment 9 (documentation) | ~45 min | "mid five-figure" for phase 1 reads (impl) | ~$0.60-1.00 | Sonnet | 1 | E | `TOO-19/TOO-19 Phase 1 increment 9 documentation report.md` |
| A24 | TOO-19 config_types.py extraction | ~10 min | light | well under $1 | Sonnet | 1 | E | `TOO-19/TOO-19 config_types.py extraction implementation report.md` |
| A25 | TOO-19 compound.py `_extract_outer_command` tests + fixes | ~17 min | — | ~$0.33 | Sonnet-class | 1 | E | `TOO-19/TOO-19 compound.py _extract_outer_command Tests and Fixes.md` |
| A26 | TOO-19 corrective change | ~28-30 min | — | ~$1.05-1.30 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Corrective Change Implementation Report.md` |
| A27 | TOO-19 fail-open config-parse ASK floor | ~41 min | — | ~$1.50-1.90 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report.md` |
| A28 | TOO-19 undecidable_fallback config + threading | ~14 min (17:05→17:19) | — | ~$0.30-0.60 | Sonnet-class | 1 | M/E | `TOO-19/TOO-19 undecidable_fallback - config and threading implementation report.md` |
| A29 | TOO-19 increment 3 — hard_deny entries | ~32 min | ~60-90k in / ~8-12k out (impl) | ~$0.30-0.60 | Sonnet-class | 1 | E | `TOO-19/TOO-19 increment 3 - hard_deny entries - implementation report.md` |
| A30 | TOO-19 discovery-log change detection | ~31 min | — | ~$1.55 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 discovery log change-detection implementation report.md` |
| A31 | TOO-19 deny-side rule fabrication fix | ~25-30 min (21:1x→21:34, from log timestamps) | — | well under $1 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 deny-side rule fabrication fix.md` |
| A32 | TOO-19 shadowing detection + install hardening | ~90 min (11:07→12:33) | — | ~$3-6 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 shadowing detection and install hardening.md` |
| A33 | TOO-19 s1 SessionStart invariant + m3 wrapper FP | ~40 min | — | ~$1-2 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 s1 SessionStart invariant and m3 wrapper false-positive.md` |
| A34 | TOO-19 review fixes — correctness (round 1) | ~30 min | — | ~$2-4 | Sonnet-class | round 1 | E | `TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md` |
| A35 | TOO-19 review fixes — correctness (round 2) | ~55 min | — | ~$3-5 | Sonnet-class | round 2 | E | `TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md` |
| A36 | TOO-19 review fixes — complexity + minors | ~41 min (13:49→14:30) | ~400-700k in+out (impl) | ~$3-6 | Sonnet 5 | 1 | M/E | `TOO-19/TOO-19 Review Fixes - Complexity and Minors Implementation Report.md` |
| A37 | TOO-19 review fixes — M1 and M2 | ~60 min | — | ~$2-4 | Sonnet-class | 1 | E | `TOO-19/TOO-19 Review Fixes - M1 and M2 Implementation Report.md` |
| A38 | TOO-19 code review majors M1-M3 (fix report) | ~2h10m | — | ~$3.4 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 code review Majors M1-M3 - fix report.md` |
| A39 | TOO-19 code review 2026-08-02 majors M1-M3 | ~1h48m | — | **~$11** | **Opus 5** | 1 | E | `TOO-19/TOO-19 code review 2026-08-02 majors M1-M3.md` |
| A40 | TOO-19 code review minors m1-m4, m6 (fix report) | ~115 min | — | ~$5.10 | Sonnet 5 | 1 | E | `TOO-19/TOO-19 code review minors m1-m4 m6 - fix report.md` |
| A41 | TOO-30 RED-phase tests | ~29 min (16:48→17:15) | ~100-150k in / ~15-20k out (impl) | ~$0.70-1.00 | Sonnet 5 | 1 | M/E | `TOO-30/TOO-30 Coder Implementation Report - RED Phase Tests.md` |
| A42 | TOO-30 GREEN phase | ~53 min | — | ~$2-3 | Sonnet 5 | 1 | E | `TOO-30/TOO-30 Coder Implementation Report - GREEN Phase.md` |
| A43 | TOO-30 test-isolation cleanup | ~2h | — | ~$5.15 | Sonnet 5 | 1 | E | `TOO-30/TOO-30 Test Isolation Cleanup - Implementation Report.md` |
| A44 | TOO-44 follow-up — re-drift guard | ~40 min | — | under $0.20 | Sonnet 5 | 1 | E | `implementation/TOO-44 follow-up - re-drift guard for TestDecisionReachesStdoutWhenCrashLoggingFails - coder-latest-implementation-report.md` |
| A45 | TOO-44 ambient prose repair, pass 2 | ~27 min | — | ~$2.25 | — | pass 2 | E | `TOO-45/reports/TOO-44 ambient prose repair pass 2 - coder implementation report.md` |
| A46 | TOO-45 spike B (second grammar) | ~43 min | ~80-100k (impl) | ~$1-2 | Sonnet | 1 | E | `implementation/TOO-45 spike B - coder implementation report.md` |
| A47 | TOO-45 R3 review-fix | ~30 min (19:03→19:33) | — | ~$1.7 | Sonnet 5 | 1 | M/E | `implementation/TOO-45 R3 review-fix implementation report.md` |
| A48 | TOO-45 R3 second review-fix | ~40 min (19:55→20:35) | — | ~$2.1 | Sonnet 5 | 2nd fix pass | M/E | `implementation/TOO-45 R3 second review-fix implementation report.md` |
| A49 | TOO-45 coder-latest (4 findings) | ~35 min | — | well under $1 | Sonnet-class | 1 | E | `implementation/TOO-45 coder-latest-implementation-report.md` |
| A50 | TOO-45 "Coder Latest Implementation Report" §1 | ~57 min | — | ~$1.15 | Sonnet 5 | 1 | E | `implementation/Coder Latest Implementation Report.md` |
| A51 | TOO-45 "Coder Latest Implementation Report" §2 | ~70-80 min (start not clocked; only 18:31 EDT end is hard) | ~60-70 tool calls | ~$1.50-3 | Sonnet 5 | 1 | E | `implementation/Coder Latest Implementation Report.md` |
| A52 | TOO-45 statement_bounds_containing table refactor | ~26 min (11:44→12:02) | — | ~$2-4 | Sonnet 5 | 1 | M/E | `implementation/TOO-45 statement_bounds_containing table refactor - coder implementation report.md` |
| A53 | TOO-45 F1 dollar-paren depth guard | ~60 min | — | ~$2.4 | Sonnet 5 | 1 | E | `implementation/TOO-45 F1 dollar-paren depth guard - coder implementation report.md` |
| A54 | TOO-45 punch-list #01 suppression store (main) | ~2h30m | — | ~$4.10 | Sonnet 5 | 1 | E | `implementation/TOO-45 punch-list #01 suppression store - implementation report.md` |
| A55 | TOO-45 punch-list #01 suppression store, pass 4 | ~85 min | — | ~$5.20 | Sonnet-class | pass 4 of 5 | E | `implementation/TOO-45 punch-list #01 suppression store — implementation report (pass 4).md` |
| A56 | TOO-45 punch-list 03 stages 2+4 | ~1h40m | — | ~$4.3 | Sonnet 5 | 1 | E | `implementation/TOO-45 punch-list 03 stages 2+4 - coder implementation report.md` |
| A57 | TOO-45 punch-list 03 stages 2+4, review pass | ~23 min | — | ~$1.3 | Sonnet 5 | 2nd pass | E | `implementation/TOO-45 punch-list 03 stages 2+4 - coder implementation report.md` |
| A58 | TOO-45 punch-list 04 error reporter, pass 1 | ~55 min | — | well under $1 | Sonnet | pass 1 | E | `implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md` |
| A59 | TOO-45 punch-list 04 error reporter, pass 2 | ~80 min | — | **~$2.50-3.50** | **Opus 5** | pass 2 | E | same file |
| A60 | TOO-45 punch-list 04 error reporter, pass 3 | ~65 min | — | ~$1.50-2.50 | Sonnet 5 | pass 3 | E | same file |
| A61 | TOO-45 punch-list 04 error reporter, pass 4 | ~70 min | — | ~$2-3 | Sonnet 5 | pass 4 | E | same file |
| A62 | TOO-45 punch-list 04 error reporter, pass 5 | ~41 min | — | ~$2-3 | Sonnet 5 | pass 5 | E | same file |
| A63 | TOO-45 punch-list 07 test tier | ~38 min | — | ~$1.10 | Sonnet 5 | 1 | E | `implementation/TOO-45 punch-list 07 test tier - coder implementation report.md` |
| A64 | TOO-45 punch-list 15 migrate lock, pass 1 | ~85 min | — | ~$2-3 | Sonnet 5 | pass 1 | E | `implementation/TOO-45 punch-list 15 migrate lock - coder implementation report.md` |
| A65 | TOO-45 punch-list 15 migrate lock, pass 2 | ~65 min | — | ~$1.5-2.5 | Sonnet 5 | pass 2 | E | same file |
| A66 | TOO-45 punch-list 15 migrate lock, pass 3 | ~60 min | — | ~$1-2 | Sonnet 5 | pass 3 | E | same file |
| A67 | TOO-45 punch-list 94 validation_issues split | ~40 min | — | under $2 | Sonnet 5 | 1 | E | `TOO-45/TOO-45 punch-list 94 validation_issues split - coder implementation report.md` |
| A68 | TOO-45 Item 95 — split `judge_unit` | ~70 min | — | ~$1.10 | Sonnet 5 | 1 | E | `implementation/TOO-45 Item 95 - split judge_unit - coder implementation report.md` |
| A69 | TOO-45 proposed ticket 45 — inert-mock static check | ~60 min | — | **~$11.5** | not stated | 1 | E (elapsed from file mtimes) | `implementation/TOO-45 proposed ticket 45 inert-mock static check - implementation report.md` |
| A70 | TOO-45 proposed ticket 96 | ~36 min | — | ~$0.60-1.00 | Sonnet 5 | 1 | E | `implementation/TOO-45 proposed ticket 96 - coder implementation report.md` |
| A71 | TOO-45 ticket 14 residual — takeover notice routing | ~45 min | — | under $1 | Sonnet | 1 | E | `implementation/TOO-45 ticket 14 residual - takeover notice routing - coder implementation report.md` |
| A72 | TOO-45 ticket 19 repair round | ~13-14 min | low tens of k out / ~few hundred k in (impl) | under $1 | Sonnet 5 | repair round | E | `implementation/TOO-45 ticket 19 repair round - coder implementation report.md` |
| A73 | TOO-45 ticket 20a repair round | ~1h50m | — | ~$3.10 | Sonnet | repair round | E | `implementation/TOO-45 ticket 20a repair round - coder implementation report.md` |
| A74 | TOO-45 ticket 32 item 1 — MigrationOutcome reason carrying | ~70 min | few hundred k in+out (impl) | ~$1-2 | Sonnet-class | 1 | E | `TOO-45/TOO-45 ticket 32 item 1 - MigrationOutcome reason carrying - coder implementation report.md` |
| A75 | TOO-45 ticket 38 — fallback_kind prose-parsing fix | ~62 min | ~60-70 tool calls | ~$3-5 | Sonnet | 1 | E | `implementation/TOO-45 ticket 38 fallback_kind prose-parsing fix - coder implementation report.md` |
| A76 | TOO-45 ticket 39 — write-guard ordinary-tier check | ~15-17 min (19:40→19:55 EDT) | — | ~$0.30-0.60 | Sonnet | 1 | M/E | `TOO-45/reports/TOO-45 proposed ticket 39 - write guard ordinary-tier check.md` |
| A77 | TOO-45 ticket 39 round 3 | ~20 min (20:32→~20:52) | ~150k in incl. cache / ~12k out (impl) | ~$3 | Sonnet 5 | round 3 | M/E | `TOO-45/reports/TOO-45 punch-list 39 round 3 - coder implementation report.md` |
| A78 | TOO-45 ticket 39 round 4 | ~90 min | — | ~$2-3 | Sonnet 5 | round 4 | E | `TOO-45/reports/TOO-45 punch-list 39 round 4 - coder implementation report.md` |
| A79 | TOO-45 review-39 round 1 repair | ~50 min (session 20:01→~20:20 plus pre-session reading — see conflict C7) | ~60-80k (impl) | ~$1-1.50 | Sonnet-class | repair | M/E | `TOO-45/reports/TOO-45 review-39-round1 repair - coder implementation report.md` |
| A80 | TOO-45 ticket 42 + 47 | ~62 min | — | ~$5.20 | Sonnet (implied) | 1 | E | `TOO-45/TOO-45 tickets 42 and 47 - coder implementation report.md` |
| A81 | TOO-45 ticket 44 — broken isolation seam | ~27 min | — | ~$3.80 | — | 1 | E | `implementation/TOO-45 ticket 44 broken isolation seam - coder implementation report.md` |
| A82 | TOO-45 review-44 round 5 repair | **18 min (18:31→18:49, clock-read)** | ~25k out (impl) | ~$3-4 | **Opus 5** | round 5 | **M** / $ E | `TOO-45/reports/TOO-45 review-44 round5 repair - coder implementation report.md` |
| A83 | TOO-45 ticket 44 round 6 prose repair | ~62 min | — | **~$22** | not stated | round 6 | E | `TOO-45/reports/TOO-45 ticket 44 round6 prose repair - implementation report.md` |
| A84 | TOO-45 ticket 74 — hook payload-key + empty-registry fail-open | ~40 min | — | ~$1.50-2.50 | Sonnet | 1 | E | `TOO-45/reports/TOO-45 ticket 74 (hook payload-key + empty-registry fail-open) - coder implementation report.md` |
| A85 | TOO-45 review-74 round 1 repair | ~50 min | — | ~$10-13 | Sonnet 5 | round 1 repair | E | `TOO-45/reports/review-74-round1-repair.md` |
| A86 | TOO-45 ticket 77 phase 1 grammar (leading env assignment) | ~44 min | — | ~$4.00 | — | phase 1 | E | `TOO-45/reports/TOO-45 ticket 77 leading env assignment - phase 1 grammar - coder report.md` |
| A87 | TOO-45 ticket 77 phase 1 M1+L1 | ~46 min | — | **~$8** | **Opus** | 1 | E | `TOO-45/reports/TOO-45 ticket 77 grammar phase 1 M1+L1 - coder implementation report.md` |
| A88 | TOO-45 ticket 77 phase 1 delta fold-in (M1 +=, L1-L3) | ~34 min | — | ~$5.30 | — | delta pass | E | `TOO-45/reports/TOO-45 ticket 77 grammar phase 1 delta fold-in (M1 +=, L1, L2, L3) - coder implementation report.md` |
| A89 | TOO-45 ticket 77 phase 2 matcher | **~3h05m** (self-flagged as far over the 30-min guidance) | — | **~$15.30** | — | phase 2 | E | `TOO-45/reports/TOO-45 ticket 77 phase 2 matcher - coder implementation report.md` |
| A90 | TOO-45 review-77 round 1 repair | ~1h28m | — | ~$6.80 | — | round 1 repair | E | `TOO-45/reports/TOO-45 review-77 round1 repair - coder implementation report.md` |
| A91 | TOO-45 ticket 78 — tilde-expanded variant | ~65 min | — | ~$5.40 | — | 1 | E | `TOO-45/reports/TOO-45 ticket 78 tilde-expanded variant - coder implementation report.md` |
| A92 | TOO-45 ticket 78 follow-up — three remaining pattern types | ~100 min | — | ~$7.90 | — | follow-up | E | `TOO-45/reports/TOO-45 ticket 78 follow-up (three remaining pattern types) - coder implementation report.md` |
| A93 | TOO-45 review-78 round 1 repair | ~89 min | — | ~$9 | — | round 1 repair | E | `TOO-45/reports/TOO-45 review-78 round1 repair - coder implementation report.md` |
| A94 | TOO-45 review-78 round 2 repair | ~55 min | ~180k in (cached) / ~15k out (impl) | ~$1.20-1.60 | Sonnet 5 | round 2 repair | E | `TOO-45/reports/TOO-45 review-78 round2 repair - coder implementation report.md` |
| A95 | TOO-45 review-78 round 3 repair | ~34 min (11:28→12:02) | — | ~$2-4 | Sonnet 5 | round 3 repair | M/E | `TOO-45/reports/TOO-45 review-78 round3 repair - coder implementation report.md` |
| A96 | TOO-45 ticket 79 — command-substitution ASK floor | ~2h | — | ~$3-5 | Sonnet 5 | 1 | E | `TOO-45/reports/TOO-45 proposed ticket 79 - command substitution ASK floor - coder implementation report.md` |
| A97 | TOO-45 review-79 round 1 repair | ~2h | — | **~$17** | Sonnet 5 | round 1 repair | E | `TOO-45/reports/review-79-round1 repair - coder implementation report.md` |
| A98 | TOO-45 review-79 round 2 fix | ~80 min | — | **~$16** | **Opus 5** | round 2 fix | E | `TOO-45/reports/review-79-round2 fix - implementation report.md` |
| A99 | TOO-45 review-79 round 3 repair | ~55 min | — | under $2 | Sonnet-class | round 3 repair | E | `TOO-45/reports/TOO-45 review-79-round3 repair - coder implementation report.md` |
| A100 | TOO-45 review-79 round 4 blocking fix | ~1h10m | — | ~$6-9 | Sonnet 5 | round 4 fix | E | `TOO-45/reports/Review 79 round 4 blocking fix - coder implementation report.md` |
| A101 | TOO-45 ticket 18 — default multi-token prefix over-match | ~33 min (13:32→14:05) | — | ~$1.50-3 | Sonnet | 1 | M/E | `TOO-45/reports/TOO-45 proposed ticket 18 - default multitoken prefix over-match - coder implementation report.md` |
| A102 | TOO-45 review-18 round 1 repair | ~28 min (14:12→14:40) | — | ~$2.40 | Sonnet-class | round 1 repair | M/E | `TOO-45/reports/TOO-45 review-18 round1 repair - coder implementation report.md` |
| A103 | TOO-45 review-18 round 2 repair | ~58 min | — | ~$2-4 | Sonnet 5 | round 2 repair | E | `TOO-45/reports/review-18-round2 repair - coder implementation report.md` |
| A104 | TOO-45 review-18 round 3 repair | ~2h10m | — | ~$3-4 | Sonnet 5 | round 3 repair | E | `TOO-45/reports/TOO-45 review-18-round3 repair - coder implementation report.md` |
| A105 | TOO-45 review-18 round 4 repair | ~53 min | — | ~$3.30 | Sonnet 5 | round 4 repair | E | `TOO-45/reports/TOO-45 review-18-round4 repair - coder implementation report.md` |
| A106 | TOO-45 review-18 round 5 repair | ~85 min | ~180k in (cached) / ~25k out (impl) | ~$2.50-3.50 | Sonnet 5 | round 5 repair | E | `TOO-45/reports/TOO-45 review-18-round5 repair - coder implementation report.md` |
| A107 | TOO-45 review-80 round 1 prose repair | ~20 min (22:18→22:38, from file timestamps + `date`) | — | ~$2.20 | — | round 1 repair | M/E; **file self-corrects fabricated in-terminal clock times** | `TOO-45/reports/TOO-45 review-80 round1 prose repair - implementation report.md` |
| A108 | TOO-45 review-80 round 3 prose repair | ~26 min | — | ~$1.8 | — | round 3 repair | E | `TOO-45/reports/TOO-45 review-80 round3 prose repair - implementation report.md` |
| A109 | TOO-45 ticket 81 follow-up | ~1h40m | — | ~$3.45 | Sonnet 5 | follow-up | E | `TOO-45/TOO-45 ticket 81 follow-up - coder implementation report.md` |
| A110 | TOO-45 ticket 85 chunk A | ~50-60 min | few hundred k (impl) | well under $1 | Sonnet | chunk A | E (no start timestamp) | `implementation/TOO-45 ticket 85 chunk A - coder implementation report.md` |
| A111 | TOO-45 ticket 85 chunk B | ~34 min | modest | well under $1 | Sonnet 5 | chunk B | E | `implementation/TOO-45 ticket 85 chunk B - coder implementation report.md` |
| A112 | TOO-45 ticket 85 chunk C | ~20-25 min | light | well under $1 | Sonnet-class | chunk C | E | `implementation/TOO-45 ticket 85 chunk C - coder implementation report.md` |
| A113 | TOO-45 ticket 85 chunk D | ~55 min | moderate | under $1.50 | Sonnet-class | chunk D | E | `implementation/TOO-45 ticket 85 chunk D - coder implementation report.md` |
| A114 | TOO-45 ticket 98 chunk 3 — module boundary move | ~65 min | — | ~$1.60 | Sonnet 5 | chunk 3 | E | `implementation/TOO-45 ticket 98 chunk 3 - module boundary move - coder implementation report.md` |
| A115 | TOO-45 ticket 99 | ~22 min (15:33→15:50) | — | ~$1.50-2.50 | Sonnet | 1 | M/E | `implementation/TOO-45 ticket 99 - coder implementation report.md` |
| A116 | TOO-45 ticket 100 | ~65 min | — | ~$2-4 | Sonnet-class | 1 | E (per-phase timestamps NOT captured; author flags the gap) | `implementation/TOO-45 ticket 100 - coder implementation report.md` |
| A117 | TOO-45 ticket 101 — bare-brace grammar fix | ~55 min before stand-down | — | ~$1-2 | Sonnet | 1 (interrupted, not completed) | E | `implementation/TOO-45 ticket 101 bare-brace grammar fix - coder implementation report.md` |
| A118 | TOO-45 ticket 104 — dicts are undeclared types | ~50 min | — | "low single-digit dollars" | Sonnet 5 | 1 | E (start not clocked) | `toolguard-memories/TOO-45/TOO-45 ticket 104 - dicts are undeclared types - coder implementation report.md` |
| A119 | TOO-45 ticket 105 | ~35-40 min | — | ~$1-2 | Sonnet | 1 | E (start not clocked) | `implementation/TOO-45 ticket 105 - coder implementation report.md` |
| A120 | TOO-45 Item 97 step 3 — kind means only fact 1 | ~45 min | — | ~$0.70 | Sonnet 5 | 1 | E | `TOO-45/TOO-45 Item 97 Step 3 - kind means only fact 1 - coder implementation report.md` |
| A121 | TOO-45 revert redirect-glued tilde extension | ~45-55 min | well under 100k (impl) | under $1 | Sonnet | 1 | E | `TOO-45/reports/TOO-45 revert redirect-glued tilde extension - coder implementation report.md` |
| A122 | TOO-45 phase 2 tools-hierarchy / tools-mining | ~75-95 min (sum of phases) | — | "low-to-mid single-digit dollars" | Sonnet-class | 1 | E; **session clock explicitly unreliable, no total stated** | `TOO-45/TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md` |
| A123 | TOO-45 resolution-seam protocols | ~130 min | — | ~$3-5 | Sonnet 5 | 1 | E | `TOO-45/reports/resolution-seam-protocols-report.md` |
| A124 | code review report (older, implementation/) | — | — | ~$1.50 | Sonnet 4.6 | 1 | E | `implementation/latest-code-review-report.md.md` |

---

# Table B — reviewer side (blinded review rounds)

**This population is absent from every implementer report** and was the half the deletion triage omitted entirely. Almost all of it is priced at Opus.

| # | ticket / round | wall-clock | tokens (reviewer) | $ (reviewer) | model | files reviewed | findings | prov | source file |
|---|---|---|---|---|---|---|---|---|---|
| B1 | 18 round 1 | 47 min | — | ~$5 | Opus 5 | 6 | 2 blocking / 9 non-blocking | E | `TOO-45/reports/review-18-round1.md` |
| B2 | 18 round 2 | 1h14m | — | ~$9-13 | Opus 5 | 6 | 2 / 9 | E | `TOO-45/reports/review-18-round2.md` |
| B3 | 18 round 3 | ~14 min (15:23→15:37) | ~250k in / ~15k out | ~$4 | Opus 5 | 10 | 1 / 9 | M/E | `TOO-45/reports/review-18-round3.md` |
| B4 | 18 round 4 | ~55 min | ~260k in (cached) / ~27k out | ~$7 | Opus 5 | 10 | 3 / 4 | E | `TOO-45/reports/review-18-round4.md` |
| B5 | 18 round 5 | 35 min | ~250k in (cached) / ~35k out | ~$6 | Opus 5 | 9 | 3 / 7 | E | `TOO-45/reports/review-18-round5.md` |
| B6 | 18 round 6 | ~14 min | ~250k in / ~25k out | ~$4-6 | Opus 5 | 13 | 2 / 5 | E | `TOO-45/reports/review-18-round6.md` |
| B7 | 39 round 1 | 1h14m | — | ~$4.50 | Opus | 2 (+6 supporting) | 3 / 7 | E | `TOO-45/reports/review-39-round1.md` |
| B8 | 39 round 2 | ~1h10m | ~280k in (incl. cache) / ~30k out | ~$7 | Opus 5 | 2 (+8 read) | 4 / 8 | E | `TOO-45/reports/review-39-round2.md` |
| B9 | 44 round 4 | ~16 min | ~190k in / ~14k out | ~$3.20 | Opus 5 | 17 py + 2 | 3 blocking | E | `TOO-45/reports/review-44-round4.md` |
| B10 | 44 round 5 | **21m40s (18:18→18:39, clock-read)** | ~300k in (cache-heavy) / ~28k out | ~$4 | Opus 5 | 18 | 4 / 6 | **M** / $ E | `TOO-45/reports/review-44-round5.md` |
| B11 | 74 round 1 | ~17 min (in-flight elapsed figures explicitly disavowed) | — | ~$9-12 | Opus 5 | 3 + context | 5 / 8 | E | `TOO-45/reports/review-74-round1.md` |
| B12 | 74 round 2 | ~1h05m | — | ~$9-12 | Opus | 11 | 1 / 8 | E | `TOO-45/reports/review-74-round2.md` |
| B13 | 77 grammar phase 1 | 33 min | — | ~$5 | Opus | 2 (+3 generated variants) | 0 crit / 0 high / 1 med / 3 low | E | `TOO-45/reports/review-77-grammar-phase1.md` |
| B14 | 77 grammar phase 1 delta | 42 min | — | ~$7 | Opus | 2 | 1 med / 3 low / 1 info | E | `TOO-45/reports/review-77-grammar-phase1-delta.md` |
| B15 | 78 round 2 | **13m16s (10:36→10:50, clock-read)** | ~170k in (cached) / ~28k out | ~$4 | Opus 5 | 9 | 2 / 7 | **M** / $ E | `TOO-45/reports/review-78-round2.md` |
| B16 | 78 round 3 | ~2h00m (14:22→16:22) | ~450k in (cache reuse) / ~35k out | ~$9-12 | Opus 5 | 9 + context | 3 / 11 | M/E | `TOO-45/reports/review-78-round3.md` |
| B17 | 78 round 5 | ~31 min | — | ~$4 | Opus | 8 | 2 / 8 | E | `TOO-45/reports/review-78-round5.md` |
| B18 | 79 round 1 | ~1h25m | — | **~$15** | Opus 5 | 6 | — | E | `TOO-45/reports/review-79-round1.md` |
| B19 | 79 round 2 | 2h05m | — | ~$11 | Opus 5 | 7 + context | 4 / 7 | E | `TOO-45/reports/review-79-round2.md` |
| B20 | 79 round 4 | **1h59m (14:21→16:20, clock-read)** | ~300k cumulative in (cache reuse) / ~35k out | ~$9-13 | Opus 5 | 5 | 1 / 5 | **M** / $ E | `TOO-45/reports/review-79-round4.md` |
| B21 | 80 round 3 | ~26 min | ~130k in / ~16k out | ~$4 | Opus | 16 | 2 / 12 (+3 info, 12 verified-clean) | E | `TOO-45/reports/review-80-round3.md` |
| B22 | latest code review (post-85) | 16 min (20:36→20:52) | — | ~$3.10 | Opus 5 | 8 in scope + ~12 context | 0 crit / 2 major / 4 minor / 6 suggestions | M/E | `toolguard-memories/latest-code-review-report.md` |

**Review rounds with NO cost data at all (10 of 35 review reports)**: `review-39-round3`, `review-44-round6`, `review-44-redrift-guard`, `review-77-round1`, `review-78-round1`, `review-78-round4`, `review-79-round3`, `review-80-round1`, `review-80-round2`, `review-conclusions`.

---

# Table C — campaign-level and per-ticket aggregates

These are a **different unit of account** from Tables A and B: they roll up multiple agent runs, and several were derived from git commit timestamps rather than from any agent's self-report. Do not add them to A or B.

| # | scope | wall-clock | tokens | $ | runs / rounds | prov | source file |
|---|---|---|---|---|---|---|---|
| C-1 | **Phase 3, 10 items, `db23d17` (08-19 14:16) → `5124795` (08-21 01:54)** | **35h38m total; ~3.6h per item; range 27m–8h51m** | — | — | 10 items | **M — from git commit timestamps** | `TOO-45/TOO-45-punch-list-2026-08-20.md` |
| C-2 | ↳ item 44 + follow-up | 6h56m | — | — | — | M | same |
| C-3 | ↳ item 80 + 2 follow-ups | 3h03m | — | — | — | M | same |
| C-4 | ↳ item 77 (two-phase grammar) | 4h22m | — | — | — | M | same |
| C-5 | ↳ item 78 | **8h51m — the wall-clock outlier** | — | — | — | M | same |
| C-6 | ↳ item 18 | 4h15m | — | — | — | M | same |
| C-7 | ↳ `--stdlib` | 27m | — | — | — | M | same |
| C-8 | ↳ RED sweep + item 74 | 1h16m | — | — | — | M | same |
| C-9 | ↳ item 39 | 2h13m | — | — | — | M | same |
| C-10 | ↳ item 79 | 4h15m | — | — | — | M | same |
| C-11 | ticket 79, assessed 2026-08-21 during the 5th pass | — | **~1.8M subagent tokens** | — | **7 agent runs** (1 impl, 4 repairs, 2 blinded reviews) | E | `TOO-45/measurements/79-cost-assessment.md` |
| C-12 | ticket 79, phase-3 resume note | — | **~2.6M subagent tokens** | — | **9 agent runs**; round curve 5→4→3 | E | `TOO-45/TOO-45 phase 3 resume.md` |
| C-13 | ticket 79, later post-mortems | — | **~3M subagent tokens** | — | **11 agent runs, 4 review rounds, 3 security weakenings** | R | `TOO-45/proposed-tickets/97-unit-kind-answers-two-questions.md`; `reports/surprise/79-scored.md`; `reports/surprise/RESULTS-LOG.md:192`; `reports/surprise/BAD-SURPRISES-DIAGNOSIS.md`; `proposed-tickets/95-...md`; `DURABLE/intermediate/defect-taxonomy.md`; `DURABLE/intermediate/practices-with-evidence.md` |
| C-14 | ticket 18 | **~11 hours** for 552 lines | — | — | **6 blinded review rounds**; round curve 2→2→1→3→3→2 | E/R | `TOO-45/reports/surprise/18-scored.md` |
| C-15 | ticket 74 | **~4h** | — | — | 1 implementation pass, 2 review rounds; round curve 5→1→commit | E | `TOO-45/reports/surprise/74-scored.md` |
| C-16 | ticket 78 | **~10 hours** | — | — | **5 blinded review rounds** | E/R | `TOO-45/reports/surprise/78-scored.md` |
| C-17 | ticket 39 | estimated 3h | — | — | 4 implementation passes, 3 review rounds; round curve 3→4→2 | E | `TOO-45/reports/surprise/39-scored.md` |
| C-18 | punch-list #01 suppression store | — | — | — | **5 implementation passes, 4 reviews** | E | `TOO-45/reports/surprise/01-suppression-store.md` |
| C-19 | ticket 98 chunk 2 (single agent run) | **~3h05m**, incl. 76 min with no file write | — | — | 1 | M (observed by coordinator) | `TOO-45/reports/surprise/98-chunk2-scored.md` |
| C-20 | mutation-testing repair agents | — | **~161k tokens per repair agent, range 142k–197k, n=12** | — | 12 agents | **M — the only stated measured token range in the corpus** | `methodology/in-process-mutation-testing.md`; echoed in `DURABLE/intermediate/practices-with-evidence.md:50` |
| C-21 | claim-verification review rounds | repair passes ~27 min and ~40 min; blinded review pass ~10 min | **~100k tokens per review round** | ~$2.25 and ~$4-6 (repairs); ~$3 (blinded pass) | 5 rounds on one ticket | E | `methodology/verifying-claims-finds-bugs.md`; `TOO-45/TOO-45 lessons.md:308` |
| C-22 | phase 1 → phase 2 (2026-08-14 status) | "phase 2 ran all day" | — | — | 77 test modules repaired; 137 reds triaged into 10 defects fixed by **11 agent runs** | E | `TOO-45/TOO-45 status 2026-08-14 - phase 2.md` |
| C-23 | 2026-08-12 budget pacing (weekly limit) | ~8h to exhaustion at then-current pace | 8,204 requests in 24h ≈ 342/hr; ~232 requests per 1% weekly; ~2,780 requests remaining at 88% | — | ~1 weekly tick per 2-3 completed one-file batches | **M — read from `~/bin/claude-usage`** | `TOO-45/TOO-45 punch-list 07 work queue.md` |
| C-24 | remaining-work estimate, revised 2026-08-21 | **~55-65h remaining, revised down from ~91h** | — | — | — | E, but rebased on C-1's measurement | `TOO-45/TOO-45-punch-list-2026-08-20.md` |

---

# INTERPRETATION — everything below this line is judgement, not extracted data

## 1. The heading the brief asked for, quoted in full

`TOO-45/TOO-45-punch-list-2026-08-20.md` carries a section headed:

> **## THE CORRECTION THAT MATTERS — I have been costing tickets in the wrong currency**
>
> I described 79 as *"the most expensive item of the campaign"* on the strength of **11 agent runs and ~3M subagent tokens**. By wall-clock it was **4h15m — below the phase-3 average, and less than half of ticket 78.**
>
> **Tokens and wall-clock diverge because agents run in parallel and fast.** Arnon's constraints are his review time and calendar time; neither is measured by token spend. So *"expensive"* meaning *"many agent runs"* is a metric about me, not about him, and I have been reporting it as though it were his cost.
>
> **78 is the real outlier at 8h51m** — and its rounds 2-5 chased tilde positions with zero field occurrence, which is exactly what the evidence gate was added to stop. That is the expensive failure mode: not many rounds, but many rounds on findings that did not matter.
>
> This does not retire the round-curve control — 79's four rounds each caught a genuine security weakening, so they were earned. It reprices them.

`grep -rl "wrong currency"` returns three files: this one, `DURABLE/intermediate/VERIFIED-deletion-triage.md`, and `DURABLE/intermediate/VERIFIED-practices-with-evidence.md`. **The primary is in the delete pile** (it is rescue R7 in the verification).

## 2. Which tickets were expensive — by each currency separately

**By measured wall-clock (git commit timestamps, C-1 through C-10 — the only cross-ticket measured series):**

1. **78** — 8h51m
2. **44** (+ follow-up) — 6h56m
3. **77** — 4h22m
4. **18** — 4h15m and **79** — 4h15m (tied)
6. **80** (+ 2 follow-ups) — 3h03m
7. **39** — 2h13m
8. RED sweep + **74** — 1h16m
9. `--stdlib` — 27m

**By single-agent-run elapsed (Table A):** ticket 77 phase 2 matcher (~3h05m, self-flagged as over guidance), ticket 98 chunk 2 (~3h05m), punch-list #01 suppression store (~2h30m), TOO-19 code review majors M1-M3 (~2h10m), review-18 round 3 repair (~2h10m), ticket 79 implementation (~2h), review-79 round 1 repair (~2h), TOO-30 test-isolation cleanup (~2h).

**By reviewer elapsed (Table B):** 79 round 2 (2h05m), 78 round 3 (2h00m), 79 round 4 (1h59m), 79 round 1 (1h25m), 18 round 2 (1h14m), 39 round 1 (1h14m), 39 round 2 (1h10m), 74 round 2 (1h05m).

**By estimated dollars, implementer side:** ticket 44 round 6 prose repair (~$22), review-79 round 1 repair (~$17), review-79 round 2 fix (~$16, Opus), ticket 77 phase 2 matcher (~$15.30), review-74 round 1 repair (~$10-13), proposed-ticket-45 inert-mock check (~$11.5), TOO-19 code review 2026-08-02 majors (~$11, Opus), review-78 round 1 repair (~$9).

**By estimated dollars, reviewer side:** 79 round 1 (~$15), 18 round 2 (~$9-13), 79 round 4 (~$9-13), 74 round 1 (~$9-12), 74 round 2 (~$9-12), 78 round 3 (~$9-12), 79 round 2 (~$11).

**By reviewer input tokens:** 78 round 3 (~450k), 79 round 4 (~300k), 44 round 5 (~300k), 39 round 2 (~280k), 18 round 4 (~260k), 18 rounds 3/5/6 (~250k each).

**By agent runs / review rounds:** 79 (7, 9 or 11 runs depending on source — see C-11/12/13), 18 (6 review rounds), 78 (5 review rounds), punch-list #01 (5 implementation passes + 4 reviews), punch-list 04 error reporter (5 implementation passes), 39 (4 implementation passes + 3 review rounds), punch-list 15 migrate lock (3 passes).

**The four rankings do not agree, and that is the point of the correction quoted in §1.** 79 is first by agent runs and tokens, joint fourth by measured wall-clock. 78 is first by wall-clock and second-ish by rounds. 44 is second by wall-clock and does not appear in the runs/rounds ranking at all, but holds the single most expensive dollar figure in the corpus.

## 3. Conflicting figures found — every one

| id | subject | figure A | figure B | figure C | comment |
|---|---|---|---|---|---|
| **C1** | **ticket 79 agent runs** | **7 agent runs, ~1.8M subagent tokens** — `measurements/79-cost-assessment.md`, written 2026-08-21 during the 5th pass | **9 agent runs, ~2.6M subagent tokens** — `TOO-45 phase 3 resume.md` | **11 agent runs, ~3M subagent tokens** — six later documents (C-13) | **Three incompatible counts of the same quantity.** They are most likely three points in time on a still-running ticket, but nothing in any of the six later documents says so; they all state 11 flatly. The 11/3M figure is the one that propagated into `DURABLE/`. |
| **C2** | **ticket 79 "most expensive item"** | *"the most expensive item of the campaign"* / *"the highest actual cost"* — `surprise/79-scored.md`, `RESULTS-LOG.md:192`, `practices-with-evidence.md:169` | **4h15m — below the phase-3 average, less than half of 78** — `punch-list-2026-08-20.md` under "wrong currency" | — | Already adjudicated in the corpus (§1) but the retraction did **not** propagate: `DURABLE/01-claude-failure-modes-and-mitigations.md:125` flags exactly this, and `VERIFIED-practices-with-evidence.md:67` notes the target *"quotes the pre-correction sentence from `RESULTS-LOG.md:192` and carries none of the correction"*. **PROPAGATED 2026-08-23**: `practices-with-evidence.md:169` now carries the retraction plus the three other defects in the same inference (wrong recall column, unsourced agent count, promoted hedge). |
| **C3** | **ticket 18 total cost** | **~11 hours**, 6 blinded review rounds — `surprise/18-scored.md:61` and, per the verification, five other places | **4h15m** — `punch-list-2026-08-20.md:295` wall-clock table (git timestamps) | — | A **2.6x** discrepancy on the same ticket, both figures in hours. Flagged independently at `VERIFIED-practices-with-evidence.md:65`. The 4h15m is the measured one; the ~11h is unsourced in the file that states it. **RESOLVED 2026-08-23 in favour of 4h15m** — see the prompt-wait addendum. Ask waits were the only plausible mechanism for inflating a git-timestamp figure into a stated one, and the entire phase-3 window contains **one ask lasting two minutes**. The gap is not wall-clock; the ~11h figure is in the agent-runs/tokens currency or is simply unsupported. |
| **C4** | **ticket 78 total cost** | **~10 hours**, 5 blinded review rounds — `surprise/78-scored.md:57` | **8h51m** — `punch-list-2026-08-20.md` wall-clock table | — | Close enough to be the same event rounded differently, but they are not the same measurement and should not be quoted interchangeably. |
| **C5** | **ticket 74 total cost** | **~4h**, 1 implementation pass + 2 review rounds — `surprise/74-scored.md:48` | **1h16m** for "RED sweep + 74" — `punch-list-2026-08-20.md` wall-clock table | — | A **3x** gap. The wall-clock row bundles 74 with the RED sweep, so it should be the *larger* of the two if the units matched; it is the smaller. **RESOLVED 2026-08-23 in favour of 1h16m**, same reasoning as C3: phase-3 prompt-wait is two minutes total, so no amount of blocking on Arnon can account for a 3x gap. The two figures are in different currencies, and only the 1h16m is measured. |
| **C6** | **TOO-19 Phase 0a increment 8** | **active effort ~1h45m-2h** | **wall-clock between session start/end ~6h11m** | — | Both stated in the same file, honestly, with the gap attributed to idle/queue time. Recorded because a downstream reader taking "the elapsed figure" gets a 3x difference depending on which they take. |
| **C7** | **review-39 round 1 repair elapsed** | "Total elapsed: ~50 min wall clock" | session timestamps quoted in the same sentence are "20:01 → ~20:20" (~19 min) | — | The file reconciles them with *"plus the pre-session reading of the review report before the first timestamp"*. Recorded because the two numbers sit in one bullet. |
| **C8** | **ticket 39 cost** | estimated 3h — `surprise/39-scored.md` | 2h13m measured — `punch-list-2026-08-20.md` | — | Estimate vs measurement, in the direction of over-estimating. Minor; listed for completeness. |
| **C9** | **`--predicates` enrichment footprint** | "15 files, up from 14" (raw substring scan) | "9 of the 15 have real code coupling" → true footprint 9 before, 9 after | — | Not a cost-of-work figure, but it is the corpus's own worked example of a cost *metric* disagreeing with itself. `TOO-45/TOO-45 decision log.md`. |

**Two files disclaim their own figures outright**, and both disclaimers should travel with the numbers:

- `TOO-45/reports/TOO-45 review-80 round1 prose repair - implementation report.md`: *"the in-terminal progress notes carried clock times (14:22, 14:34, ...) that I stated without reading the clock. They were fabricated and are wrong by about eight hours."*
- `TOO-45/reports/review-74-round1.md`: *"the in-flight progress notes used a miscalibrated clock base; disregard their elapsed figures."* Same pattern at `TOO-45/reports/TOO-45 review-44 round5 repair - coder implementation report.md` (*"Interim elapsed figures I printed mid-run were estimates and were wrong; only start and end were read from the clock"*) and at `TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md` (*"a `date` check partway through showed a different timezone/offset... absolute wall-clock timestamps in my running commentary are not reliable"*).

**Four sources report per-phase timestamps were never captured** and reconstruct from message order or file mtimes: A51, A69 (file mtimes), A110, A116, A118, A119.

## 4. Coverage — what fraction of the work has NO cost data

Counted over the units of work that plausibly *should* carry a figure, not over all 685 files.

| population | total | with a cost/elapsed figure | without |
|---|---|---|---|
| blinded review rounds (`reports/review-*.md`) | 35 | 25 | **10 (29%)** |
| TOO-45 `proposed-tickets/` | 78 | **2**, and both say the cost is estimated, not measured (`106-audit-visibility...` says so under a heading reading *"Cost — ESTIMATED, NOT MEASURED"*) | **76 (97%)** |
| `surprise/*scored*.md` items | 29 | 5 carry a cost note (18, 39, 74, 78, 79) | **24 (83%)** |
| files under `toolguard-memories/` overall | 685 | 152 cited below | **533 (78%)** |

The 78% figure is not meaningful on its own — most of those files are tickets, designs and analyses that never were a unit of work. The **29% of review rounds**, the **83% of scored items** and the **97% of proposed tickets** are the meaningful gaps: the first two populations were supposed to be uniformly instrumented, and the third is the population every scheduling decision was made from.

`DURABLE/intermediate/VERIFIED-practices-with-evidence.md` measured the same gap from the other direction and reached: **"Three of fifteen [recommended practices] carry a re-measurable cost. Two more state honestly that no cost was recorded. The rest recommend a practice with no price attached."**

## 5. Things worth carrying forward

- **The only genuinely cross-comparable series in the corpus is C-1** — ten phase-3 items timed from git commit timestamps. Everything else is a self-report from inside the session that produced it, and the sessions disagree about what a clock is.
- **The only measured token figure is C-20** (~161k per repair agent, n=12, range given). Every other token count is a reconstruction.
- **No source in the corpus queried a billing API.** Every dollar figure is a token-volume guess multiplied by a remembered price. They are internally consistent enough to rank within a currency and should not be summed into a campaign total.
- **The reviewer-side population is priced ~2-4x the implementer side per unit of elapsed time**, because reviews ran on Opus and implementations mostly on Sonnet. Any aggregate that drops Table B under-reports the campaign badly — which is precisely what the deletion triage's proposed 9-file extraction would have done.

---

## Addendum, 2026-08-23 — wall-clock deflated for prompt waits

Arnon: *"wall clock time measurements can be distorted by waiting for ask prompts... you can probably compensate for that by estimating their length from the toolguard logs."*

**Method.** Every `logs/toolguard-*.md` entry carries a `## YYYY-MM-DD HH:MM:SS` header and a `Status`. The gap from an `ASK` entry to the next entry is time the agent spent blocked on Arnon. The gap after an `EXECUTED` entry is the control — ordinary agent latency, with no human in the loop. Gaps over 24h are dropped; cross-midnight gaps are attributed to the day the ask fired. Script: `scratchpad/askwait.py`, `scratchpad/askwindow.py`.

**The control validated itself in an unplanned way.** `REFUSED` (149 entries) behaves like `EXECUTED`, not like `ASK` — median 5s, max 110s. `REFUSED` is toolguard denying by rule, not Arnon declining, so it carries no human wait. Had the model been "any non-EXECUTED status means a human was consulted", REFUSED would have looked like ASK. It did not.

| status | n | median gap | mean gap | max gap |
|---|---|---|---|---|
| EXECUTED | 66,584 | 3.0s | 15.5s | 5h39m |
| **ASK** | **555** | **25.0s** | **374.9s** | **8h29m** |
| REFUSED | 149 | 5.0s | 7.2s | 110s |

**Total prompt-wait across the campaign: 68.9h over 557 asks.** The median ask was answered in 25 seconds; the mean is 15x that, so the total is dominated by a few overnight waits.

### The 2026-08-03 transition

| period | asks | ask rate (% of decisions) | prompt-wait |
|---|---|---|---|
| 2026-07-23 → 08-02 | **539** | 2.1% – 14.8% | **58.1h** |
| 2026-08-03 → 08-23 | **18** | 0.00% – 0.69% | 10.8h (8.8h of it on just 08-07 and 08-22) |

**96.8% of all prompt-wait predates 2026-08-03**, which is where the permissive fallback took effect. Worst single days: 07-27 (17.5h), 07-30 (11.7h), 08-02 (7.4h, and 154 asks — the highest count).

### What this does and does not reconcile

**It does not rescue C3 or C5, and it makes them worse.** The phase-3 window the wall-clock table measures — `db23d17` 08-19 14:16 → `5124795` 08-21 01:54 — contains **one ask, lasting two minutes**. Phase-3 wall-clock is therefore undistorted:

- **35h38m phase-3 total deflates to 35h36m.** Effectively unchanged.
- Ticket 18's **4h15m**, ticket 78's **8h51m**, ticket 79's **4h15m** and RED+74's **1h16m** are clean git-timestamp measurements.

So the unsourced `~11h` for ticket 18 (C3, a 2.6x gap) and `~4h` for ticket 74 (C5, a 3x gap) **cannot be explained by prompt waits**. This removes the one plausible mechanism that would have reconciled them, and the measured figure should be preferred in both cases.

**Where it does matter: everything before 08-03.** Any elapsed-time claim covering TOO-15 or TOO-19 carries up to 58.1h of prompt-wait that no document accounts for. None of Table A's ticket-level rows fall in that window, so the per-ticket costs above are unaffected — but campaign-wide elapsed-time statements spanning July are inflated by an unrecorded amount, and the inflation is not uniform across days (0.16h to 17.5h).

**Scope limit — this measures the governed agent, not the session.** The logs record tool calls, so a prompt-wait is visible only when it sits between two governed calls. Waiting on a plain conversational turn, or on a permission prompt from a tool toolguard does not govern, leaves no trace. 68.9h is a lower bound.

### What the instrument cannot resolve — C6, and why

**C6 (TOO-19 Phase 0a increment 8: ~1h45m-2h active vs ~6h11m wall-clock) is exactly the shape prompt-wait should explain**, and it falls in the high-ask July window where 58.1h of waiting is unaccounted for. It cannot be tested, for a reason worth recording on its own:

**The report states no absolute timestamps** — only "session start/end" as a duration — and **file mtimes across `toolguard-memories/` are not authoring dates.** They are bulk-reset in batches: 69 files share `2026-08-03 09:56`, 49 share `2026-08-19 11:29`, 13 share `2026-07-24 12:29`. So the increment cannot be located in the log timeline, and the 4h26m gap stays attributed to "idle/queue time" as the report has it.

**Two consequences beyond C6.** Any future attempt to date corpus files by mtime will produce confident wrong answers, and any elapsed-time claim in the corpus that does not carry absolute timestamps is permanently unauditable against the logs. **Cost measurements should record wall-clock start and end as absolute local timestamps**, not durations — durations cannot be cross-checked against anything.

---

## Phase-resolved cost splits — transcribed 2026-08-23 before deletion

Tables A-C record per-task **totals**. Two files in the delete set carry a breakdown *within* a task, which nothing else in the corpus does. Transcribed here so those files can go.

**`implementation/TOO-45 coder-latest-implementation-report.md`** (untracked; total already recorded as row **A49**, ~35 min / well under $1, Sonnet-class, 4 findings):

| phase | elapsed |
|---|---|
| Planning — read rules, verify all 4 findings against code | ~15 min |
| Implementation — 4 edits | ~5 min |
| Verification — baseline + post-edit test runs, ruff, `--mocks` count | ~10 min |
| Report + memory writes | ~5 min |
| **total** | **~35 min** |

Cost basis stated in the source: two full-suite test runs at ~50s each; *"estimated well under $1 in API cost for a Sonnet-class"* model.

**`TOO-45/reports/review-74-round1-repair.md`** (untracked; identified by the section-C audit as the only phase-resolved split among the review rounds; `02` otherwise records only its `~50 min / ~$10-13` total):

| phase | elapsed | cost |
|---|---|---|
| Planning | ~10 min | ~$1.50-2 |
| Implementation | ~25 min | ~$5-7 |
| Self-review | ~10 min | ~$2-3 |
| Report | ~5 min | ~$1 |

**Why these two are worth keeping when the totals were already recorded.** Every scheduling decision in this campaign was made against totals, and the totals hide that **planning plus verification plus reporting is roughly 60% of elapsed time in the first case and about half the cost in the second** — the implementation edit itself is the small part. Both remain **E** (the sources call them estimates); neither is metered. n=2, from two different task genres, so treat the shape as suggestive rather than as a measured ratio.
