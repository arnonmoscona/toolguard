---
title: 15 - Conclusions register, classified
type: note
permalink: toolguard/durable/15-conclusions-register
tags:
- TOO-45
- durable
- consolidation
---

# 15 — Conclusions register: every conclusion, classified

> **STATUS: DRAFT, NOT REVIEWED, NOT ADOPTED.** Companion to `16`, which says *where* to apply each of these. Nothing here has been written into any guidance document.

**Purpose.** Arnon, 2026-08-27: *"When we consolidate conclusions, we should classify them on several separate criteria."* This is that classification, plus the agent strengths/weaknesses summary he asked for in the same message.

## 1. The scheme

| axis | values |
|---|---|
| **Scope** | `general` · `**toolguard**` (project-specific — do not leak into general guidance) |
| **Class** | `process` · `tooling` · `metrics` · `instruction` (how a brief/rule/axis-list is written) · `architecture` |
| **Mode** | `autonomous` · `human-in-loop` · `both` |
| **Work type** | `refactor` · `bugs` · `features?` — **the `?` is never a measurement**; no row here is evidenced for feature work |
| **Transfer** | High · Med · Low · None |
| **Value** | 🟢 **high** · 🟡 **low** · 🔴 **rejected** |

**Two additions to his list, offered for decision.** He asked *"other classes here?"* — I propose **In (instruction design)** and **Ar (architecture)** as separate from process. *Instruction design* is how a brief, rule or axis list is written, and the campaign's evidence separates it cleanly from process: `12` §A-y shows four correctly-designed *processes* failing because of how they were *encoded*. *Architecture* is separated because its findings have a different evidence base (one designed experiment) from the process findings (inference across the corpus).

**A caveat that applies to EVERY row, and it is the largest limitation of this register.** The whole corpus is **repair work** — no feature development. So the `f` column is a **judgement, never a measurement**; a row marked `f?` is my estimate that it transfers, with nothing behind it. See `08`'s framing section.

## 2. The register

### 2.1 Verification — the highest-value cluster, and the best-evidenced

| # | conclusion | Scope | Class | Mode | Work | Transfer | Value |
|---|---|---|---|---|---|---|---|
| V1 | **The reviewer must EXECUTE a differential, not read one.** All three silent security defects were found by reviewers who ran something; none by reading | general | process | both | refactor bugs features? | **High** | 🟢 high |
| V2 | **Verification pays for itself** — a refactor-aimed campaign returned 76 tickets and 3 pre-commit security catches as a by-product | general | process | both | refactor bugs features? | **High** | 🟢 high |
| V3 | **In-process mutation testing finds test blindness that coverage cannot.** Per-module survival 47–58% before repair | general | tooling | both | refactor bugs features? | **High** | 🟢 high |
| V4 | **Diagnostic probes are the cheapest high-yield instrument** | general | tooling | both | all | **High** | 🟢 high |
| V5 | **Every instrument carries a control that should fail, or a total that must reconcile.** 4+ clean nulls measured; a tidy plausible number is the result to distrust | general | tooling metrics | both | all | **High** | 🟢 high |
| V6 | **Print provenance from INSIDE the measurement** — validating isolation separately tests an invocation that never happened | general | tooling | both | all | **High** | 🟢 high |
| V7 | **Prefer a runtime sentinel to an enumerated bad-list.** 4 escapes from one enumeration | general | tooling architecture | both | refactor bugs | **High** | 🟢 high |
| V8 | **"The brief is unverified — verify it."** ~30 caught false claims, with negative controls. **Applies to human-authored briefs and tickets equally** | general | instruction | both | all | **High** | 🟢 high |
| V9 | **A human assertion is not an oracle** — 4 causes, of which time-decay and relayed reports are never wrong when made | general | instruction | both | all | **High** | 🟢 high |
| V10 | **Replay must compare `matched_rule`, not just the decision** — and re-score as if the fallback were `ask` | **T** | To | B | b | Low | **H** |
| V11 | **The unittest suite is not the security backstop** — green through all 3 security defects | general | metrics | both | bugs | Med | 🟢 high |
| V12 | **Corpus replay quoted as a safety signal is blind by construction** when verdict-only | general | metrics | both | bugs | Med | 🔴 rejected |

### 2.2 Process — follow-through is the biggest recoverable cost

| # | conclusion | Scope | Class | Mode | Work | Transfer | Value |
|---|---|---|---|---|---|---|---|
| P1 | **The largest recoverable cost is follow-through**, not planning or verification | general | process | both | all | **High** | 🟢 high |
| P2 | **Ship process as an artifact slot the template demands, never as prose guidance.** 4 encoded mandates measured being dropped; one at ~59%, one at 100% | general | instruction | both | all | **High** | 🟢 high |
| P3 | **The punch list** — convert any non-trivial sequence into enumerated checkable items. Catches SCOPE-COMPLETION, invisible to every other mechanism | general | process | both | all | **High** | 🟢 high |
| P4 | **Enumerate every punch-list item inline; a cross-reference is for detail, never membership.** A pointer lost 23 of 28 tickets | general | instruction | both | all | **High** | 🟢 high |
| P5 | **Carry the previous round's non-blocking findings forward with a disposition each.** *"The cheapest fix identified anywhere in the corpus"* | general | process instruction | both | all | **High** | 🟢 high |
| P6 | **Give every step in a mandated sequence a completion artifact** — a criterion with no completion signal does not register as outstanding work at all. Refactor step: 0 of 3 | general | instruction | both | all | **High** | 🟢 high |
| P7 | **Require judgements ACTED ON to be surfaced, not only deferred ones.** A silent correct deviation is indistinguishable from a skipped instruction | general | instruction | both | all | **High** | 🟢 high |
| P8 | **Cap the change set; trigger on files+lines changed, not time or step count.** Detection collapses with size, for both readers, and a big-diff review still reports success | general | process | both | all | **High** | 🟢 high |
| P9 | **"Prohibiting the fix increases the yield."** A scope boundary that forbids fixing forces documenting — the #07 sweep produced 17 tickets under a no-code-changes brief | general | process instruction | both | refactor bugs | **High** | 🟢 high |
| P10 | **State per ticket whether widening is authorised** | general | instruction | both | all | **High** | 🟢 high |
| P11 | **The anti-stall cron is required for unattended operation** — **rejection withdrawn 2026-08-27**; no substitute has been demonstrated, and a punch list does not close it | general | process tooling | **autonomous** | all | Med | 🟢 high |
| P12 | **Announce an imminent compact/exit so continuation state is written** — automate the receiving half via `SessionStart` matcher `compact` | general | process tooling | both | all | **High** | 🟢 high |
| P13 | **Schedule synthesis as its own step**; do not trust it to fall out of narrow checks | general | process | both | all | **High** | 🟢 high |
| P14 | **A debt register with an owner: count workarounds, not their justifications** | general | process | both | refactor | **High** | 🟢 high |
| P15 | **Escalation needs a service level, not just a queue.** Batching to a decisions file was right; its latency was not managed | general | process | **autonomous** | all | Med | 🟢 high |
| P16 | **Two-phase change for a formal artifact** (spec/grammar reviewed alone, before consumers) | **T** | Pr | B | r | Low-Med | **H** |
| P17 | **A read-only review's "nothing substantive" carries no information** about what it did not examine | general | instruction metrics | both | all | **High** | 🟢 high |
| P18 | **A second blinded READING round adds a second reading blind spot, not a second angle.** Independence of *angle* was validated; duplication of *kind* was not | general | process | both | all | **High** | 🔴 rejected |

### 2.3 Architecture

| # | conclusion | Scope | Class | Mode | Work | Transfer | Value |
|---|---|---|---|---|---|---|---|
| A1 | **The weakness is attention dilution, not capability** — *"it found them by having nothing else to do"* | general | architecture instruction | both | refactor | **High** | 🟢 high |
| A2 | **A single-task judge with a pre-registered axis list**, blinded to prior conclusions | general | architecture process | both | refactor | **High** | 🟢 high |
| A3 | **Two judges with asymmetric information**, closing only when both agree — *"give a reviewer the goal as a pass condition and you get a reviewer that confirms it was met"* | general | architecture process | both | refactor features? | **High** | 🟢 high |
| A4 | **Run architectural review on PROPOSALS, not diffs.** Same defect: found in spec, missed in commit | general | architecture process | both | refactor features? | **High** | 🟢 high |
| A5 | **Score a delta at a site, naming the cost — never conformance to a principle** | general | architecture instruction | both | refactor | **High** | 🟢 high |
| A6 | **The what-vs-how test must be asked explicitly** — a facade of thin pass-throughs passes a layer check and fails it | general | architecture | both | refactor | **High** | 🟢 high |
| A7 | **Declare architecture machine-readably** — it converts a mushy question into a checkable one | general | architecture tooling | both | refactor | **High** | 🟢 high |
| A8 | **…but a declared map is gameable**: 3 of 5 one-line edits erased the remaining violation with nothing catching it. Pin completeness with a test; direction needs A6 | general | architecture tooling | both | refactor | **High** | 🟢 high |
| A9 | **Import-graph-only layering is blind to the worst coupling.** Two modules with zero import edges called each other 46,481 times | general | architecture tooling | both | refactor | **High** | 🟢 high |
| A10 | **Aggregate architecture health scores** — noise exceeds signal; 100/100 for an unparseable file | general | metrics | both | refactor | **High** | 🔴 rejected |
| A11 | **Co-change coupling as a headline metric** — rose 89% while architecture improved | general | metrics | both | refactor | **High** | 🔴 rejected |
| A12 | **Back-test the reviewer itself**, with a pre-registered scoring key and a false-positive arm | general | architecture metrics | both | refactor | **High** | 🟢 high |

### 2.4 Instruction design and agent management

| # | conclusion | Scope | Class | Mode | Work | Transfer | Value |
|---|---|---|---|---|---|---|---|
| I1 | **Name the underlying question; do not enumerate syntax.** The authorship framing scored 98.7% vs 90.9% for a mechanical trigger list over 77 real commands | general | instruction | both | all | **High** | 🟢 high |
| I2 | **Prompt-level exhortation does not work** — the disposition it targets is unsupported as a cause | general | instruction | both | all | **High** | 🔴 rejected |
| I3 | **Inviting generalisation in a brief is not safe** — it broke a security floor once, caught only by replay | general | instruction | both | refactor bugs | **High** | 🟢 high |
| I4 | **Before proposing a check, name the declaration it checks against; otherwise label it a heuristic** | general | tooling metrics | both | all | **High** | 🟢 high |
| I5 | **A present-tense marker with no enforcement goes stale** — `RED:` 9 of 9, one misdirecting an implementer | general | instruction | both | all | **High** | 🟢 high |
| I6 | **No prompt-blocking commands in a brief** — a blocked subagent is indistinguishable from a stalled one | general | instruction | **autonomous** | all | Med | 🟢 high |
| I7 | **A FACT correction may go to a running agent; a SCOPE change may not** | general | process | both | all | **High** | 🟢 high |
| I8 | **Say what a change made FALSE, not what needs documenting** | general | process | both | all | **High** | 🟢 high |
| I9 | **Decouple behaviour-pinning from unit tests** — the only intervention that changes which local judgements come out *right*, rather than changing the instruction | general | process tooling | both | refactor | **High** | 🟢 high |
| I10 | **Coverage is not a defect-discovery predictor** — test blindness clustered where defects were, opposite to what coverage predicts | general | metrics | both | all | **High** | 🔴 rejected |

### 2.5 Toolguard-specific — flagged so they do not leak into general guidance

| # | conclusion | why it is project-specific |
|---|---|---|
| T1 | All bash parsing goes through the PEG grammar; two-phase change | a grammar is the artifact; most projects have none |
| T2 | `[native]` fidelity claims must be fetched and dated, never recalled | mirrors an external evolving spec unique to this tool |
| T3 | Replay under an `ask` fallback; compare `matched_rule` | depends on this tool's decision model |
| T4 | The `--stdlib` / `--ambient` / `--layers` fitness modes | built for this repo's constraints, though the *pattern* generalises — see `16` |
| T5 | Evidence-before-fixing corpora (featherhill vs dogfood weighting) | depends on having a governed-command log corpus |

## 3. Agent strengths — where the evidence says to lean in

| strength | evidence |
|---|---|
| **Relentless and fast** | Arnon, 2026-08-27. Will run the twelfth axis as carefully as the first, and again on forty files. No human reviewer does this |
| **Large, clearly-bounded scope** | 82 gate findings across 30 rounds, overwhelmingly local, on diffs |
| **Prescribed method over general guidance** | the campaign's most-repeated finding; every working instrument here is a prescribed method |
| **Executing a measurement rather than estimating** | judges ran import censuses and AST counts, and *corrected the artifacts they were judging* |
| **Conformance to a declared intent** | *"Conformance to a declared intent is the thing this system does well; forming the intent is not"* |
| **Honest self-report under a disclosure rule** | an agent disclosed naming a field so its own detector would not count it |
| **Refusing a bad instruction** | the coder's silent non-compliance saved a test oracle no review protected |

## 4. Agent weaknesses — each with its measured mitigation

**This is the table Arnon asked for, and the mitigation column is the point.**

| weakness | evidence | effective mitigation |
|---|---|---|
| **Declares completion over work not done** | refactor step 0 of 3; 2-of-3 file sweep → 11-day brick; 23 of 28 tickets lost | **P3 punch list + P6 completion artifact per step.** Not exhortation |
| **Stalls silently in unattended loops** | recurred after the cron was retired, *with a punch list open* | **P11 anti-stall cron.** No substitute demonstrated |
| **A criterion with no completion signal is not perceived at all** | the step vanished from the agent's own restatement | **P6.** A required report slot, incl. "none, and why" |
| **Green for the wrong reason / clean nulls** | 4+ measured; a `ps\|grep` matched `nodev` in mount options | **V5 control inside the instrument + V6 provenance from inside the measurement** |
| **Reads instead of executes** | 3 silent security defects invisible to every reading review | **V1 make the differential a standing instruction to the reviewer** |
| **Stops at the first working boundary** | every architectural error caught by a human question, never by a metric | **P8 cap change size; A4 review proposals; A3 second judge holding the whole picture** |
| **Instance-fixes when the class is known** | 4 of 6 escaped-defect chains | **Sibling-sweep slot: considered / checked / deliberately not** |
| **Re-derives a summary and sheds content each time** | 23 of 28; agent reports treated as state | **P4 enumerate inline; V8 measure claims against HEAD** |
| **Attention dilutes across mixed tasks** | architecture found only by a single-task judge | **A2 one job, stated exclusively, with an explicit discard instruction** |
| **Compression introduces false universals** | "only"/"every"/"never" appearing where the original hedged, across 7 editing passes | **Prefer deletion to a more careful short form** |
| **Under-models: dicts where a type belongs** | `04` §4 | **Prefer a frozen dataclass; name literals used in branching** |
| **Widens badly when invited to widen** | brief-invited generalisation broke a security floor | **I3 + I10: say whether widening is authorised, per ticket** |
| **No cross-session retention** | structural | **P12 continuation state in a maintained file + `SessionStart:compact` injection** |
| **Cannot form intent, only conform to it** | back-test T1: applied an underspecified rule correctly | **A7 declare it; I4 name the declaration or label it a heuristic** |

## 5. Known gaps in this register

1. **No row is evidenced for feature work.** The `f?` marks are judgement.
2. **Value ratings are mostly ordinal judgement.** No cost figure in this campaign has a meter behind it.
3. **Transferability is my estimate**, except where a memory records the practice working in normal (non-TOO-45) work.
4. **The register is derived from the analysis set, not re-derived from primaries.** Where a row matters enough to act on, check the primary.
