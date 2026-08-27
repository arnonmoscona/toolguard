---
title: 16 - Where to apply the conclusions
type: note
permalink: toolguard/durable/16-where-to-apply
tags:
- TOO-45
- durable
- recommendations
---

# 16 — What to change, and where

> **STATUS: DRAFT, NOT REVIEWED, NOT APPLIED.** Every item is a proposal. Nothing has been written into `CLAUDE.md`, any skill, or any agent definition. Companion to `15`, which classifies the conclusions this document places.

**Assumptions, per Arnon 2026-08-27**: new artifacts are **user-level** and will live in **a separate git repo** for development and versioning; the analysis set will be copied there as-is, so **no absolute paths** are used here.

---

## 0. The governing principle — and it points the opposite way from "add guidance"

**The single most-repeated finding in this corpus is that prose guidance does not fire.** Four independently-encoded mandates were measured being dropped: the disclosure rule missed on **10 of 17** qualifying commands in one day; `RED:` annotations stale at **9 of 9**; the grammar rule ignored *"even when the instruction to use the grammar was explicit"*; the TDD refactor step absent from **all three** reports. Arnon's own global `CLAUDE.md` already states it: *"a 'MUST' in prose has a demonstrated track record of being silently dropped in this setup, including after being fixed once."*

**So the recommendation that governs all seven sections below is:**

> **Prefer, in this order: (1) a mechanism the harness executes — hook, script, validator; (2) a slot in an artifact template that makes an omission visible; (3) a skill loaded on demand; (4) prose in `CLAUDE.md`. Reach for (4) only when the item is a *value* rather than a *step*.**

**The consequence is uncomfortable and I think correct: `CLAUDE.md` should get SHORTER, not longer.** It is currently carrying material that belongs in mechanisms and skills, and every line it carries dilutes the lines that matter. Most of §1 below is therefore *moves and deletions*, with only three genuine additions.

---

## 1. User-level `CLAUDE.md` and adjacent files

### 1.1 Add — three items, all values rather than steps

| # | add | why prose is right here | source |
|---|---|---|---|
| U1 | **"My own assertions are not an oracle. Verify them like any other claim — especially anything I state from memory, relay second-hand, or asserted more than a few weeks ago."** Two sentences, in *Critical thinking* | It is a standing permission, not a procedure. No mechanism can grant it | `15` V9 |
| U2 | **"In unattended stretches, run an anti-stall cron. A punch list does not replace it."** One sentence | A value-level default that decides whether a mechanism gets used at all | `15` P11 |
| U3 | **"Convert any non-trivial sequence into a punch list, enumerated inline. A cross-reference is for detail, never for membership."** Two sentences | The habit must precede the tooling; the enumerate-inline clause is the part that fails silently | `15` P3, P4 |

### 1.2 Modify — two sections

**U4 — *Encoding rules as guidance vs. enforcing them*.** This section is right and under-powered: it *asserts* that prose gets dropped without the evidence that now exists. Add the four measured droppings and, more importantly, the **preference order in §0 above**, so it becomes a decision procedure rather than a warning. This is the highest-value single edit to the file.

**U5 — *git*.** Move `git worktree` from `ask` to `allow` (decided 2026-08-25, deferred to pre-push), and make the prose agree: the current list forbids *"checkouts, merges, branches"*, which an agent can reasonably read as covering `git worktree add`. Name worktrees explicitly as permitted so rules and prose stop disagreeing.

### 1.3 Move out — this is where the real gain is

| # | move | to | why |
|---|---|---|---|
| U6 | ***Tool-capability reviews*** (~15 lines of measured JetBrains/`analyze_calls` state) | the existing `reference/ide-mcp.md` | It is dated measurement, re-measured on a cadence. It is already duplicated there. `CLAUDE.md` needs the one-line rule — *never restate a tool's capabilities from memory* — and nothing else |
| U7 | ***Disclose code you wrote before you run it*** — keep the authorship framing and the four triggers | a **hook** that inspects the command, plus a short skill for the format | It is the best-evidenced rule in the file (98.7% on 77 real commands) **and it is still missed ~59% of the time.** That gap is the argument: the framing is proven, the delivery is not. A `PreToolUse` hook that flags an undisclosed heredoc/`-c`/scratch-script run is mechanism, not memory |
| U8 | ***Comments and doc comments*** (~30 lines) | a skill invoked when writing or reviewing comments | The longest section in the file, applying to a specific activity. Prime candidate for on-demand loading |

**Net effect: roughly 45 lines out, 5 in.**

### 1.4 A note on partitioning `01` and `04`

Arnon: *"01 and 04 are useful — but need to be partitioned by project-specific vs. user-level."* **Agreed, and `15` §2 is the first pass at it** — the Scope column does exactly that partition for the conclusions those documents carry. Recommendation: rather than splitting the documents, **add a scope column to each table in `01` and `04`**, and let `15` be the index. Splitting would duplicate the failure modes that are genuinely both.

---

## 2. Project-level `CLAUDE.md` (toolguard)

### 2.1 Add

| # | add | source |
|---|---|---|
| T1 | **A pre-push item: re-run `--ambient`, `--stdlib`, `--layers` AND ask the what-vs-how question explicitly.** A green layer check cannot see a facade of thin pass-throughs | `15` A6, A8 |
| T2 | **A pointer to the architecture axis config** once the plugin exists (§4), so this repo's axis list is a declared artifact rather than a brief written fresh each time | `15` A2, A7 |

### 2.2 Modify

**T3 — the "Announce intent before code the hook cannot see" section.** It is ~60 lines and is the project's largest piece of prose. Once U7 lands as a hook, this collapses to a pointer plus the toolguard-specific env-var markers (`TG_INTENT`, `TG_ATTEST_READONLY`). **Do not delete the measured evidence** — move it to `technical-notes.md`.

**T4 — the *Testing* section.** Add Arnon's 2026-08-27 finding as a standing rule: *"tests should largely reflect requirements, not coding choice."* Tell-tale: **tests of private functions** — either the function should not be private, or the test pins an implementation detail. This needs a survey before it becomes a rule (see §6, S4).

### 2.3 Remove

**T5 — the TOO-19 open commitment** (*"after pushing TOO-19, remove the hooks and config that are no longer needed"*). Auto-memory records both commitments as **CLOSED**, and the cleanup *"found almost nothing to clean."* It is a stale instruction in a live file — the exact `RED:`-marker failure the campaign measured at 9 of 9.

---

## 3. How to package this without repeated context — the answer to your question

Arnon: *"much of this section speaks to how a coordinator should structure subagent briefs and how it should look at the results and required reports. It sounds a lot like a skill. But it is not clear to me how to package it such that it is automatically repeatable without creating a lot of repeated context material. Need a suggestion on that."*

**The suggestion: do not package the knowledge. Package the artifact and the check.** Three parts, and only the third ever enters context repeatedly.

**(a) A brief TEMPLATE, emitted as a file — not remembered as prose.** The coordinator runs a command; it writes `brief-<task>.md` pre-populated with the required slots. The knowledge lives in the template generator, which is code. The invariants become **slots**: scope and whether widening is authorised (P10); previous round's non-blocking findings with a disposition each (P5); completion artifact per mandated step (P6); judgements acted on, not only deferred (P7); siblings considered/checked/not (P1). **Context cost: the filled brief, which you were going to write anyway.**

**(b) A VALIDATOR script the harness runs — the part that makes it automatic.** ~100 lines of Python: read a brief or a report, check every required slot exists and is non-empty, exit non-zero naming what is missing. **This is what converts a discipline into a mechanism**, and it is the whole reason this works where prose does not: nothing has to be remembered, and an empty slot is a build failure rather than an omission nobody sees.

**(c) One line in `CLAUDE.md`** — *"when briefing a subagent, run `/brief`"*. That is the only permanently-resident context.

**Why this beats a skill containing the guidance.** A skill body enters context when invoked — fine for occasional use, expensive for something done at every delegation. The template-plus-validator pays the cost **once per brief, in the artifact**, and the validator pays **zero context** because the harness runs it and only failures surface. It is `12` §C4 applied to itself: *prefer a mechanism the orchestrator executes, or an artifact slot the reporting template demands, over anything the agent must remember.*

**Falsifier, stated so this is testable**: if briefs come back with slots filled by empty ritual (*"siblings: none"* on work that plainly had siblings), the template is being satisfied rather than used, and the diagnosis is wrong.

---

## 4. New plugins and skills

**Arnon's instinct that this is a plugin rather than a skill is right**, and for the reason he gave: it needs *actual scripts*, and it contains *several* skills. Three plugins, in priority order.

### 4.1 Plugin: `arch-review` — the highest-value new artifact

**Why a plugin**: it needs a config parser, a fitness script, and a back-test harness — none of which is expressible as a skill body.

| component | kind | contents |
|---|---|---|
| `architecture-review` | skill | The judge brief from `13` §4, parameterised by the project's axis config. Two-judge setup and the both-must-agree rule (`13` §3). Prefers proposals over diffs (`13` §6) |
| `architecture-declare` | skill | Generate/maintain the project's axis config and layer map; asks the what-vs-how question per interface (`13` §5) |
| `architecture-backtest` | skill | Run the validation from `13` §7 — arms A/B, pre-registered scoring key, one subject per judge |
| `arch_axes.py` | script | Parse and validate a project-specific axis config. **This answers Arnon's `13` §4.2 point directly**: the twelve axes here fit a stdlib-only tool; a single-host web app and a large AWS app need different lists. Ship a **base set plus profiles**, with the config declaring which apply |
| `architecture_fitness.py` | script | **Moved out of the toolguard repo**, per Arnon 2026-08-27. Generalise the modes: `--layers` and `--orphans` are general; `--stdlib` and `--ambient` are instances of a general *declared-constraint check* and should be re-expressed as config-driven rather than toolguard-specific |

**Carry the limitations with it** (`13` §9), especially: the axis list was not blind, n=4, and **the control arm was never run**.

### 4.2 Plugin: `agent-process` — the brief/report machinery from §3

| component | kind | contents |
|---|---|---|
| `brief` | skill | Emit the brief template with the required slots |
| `punch-list` | skill | Create/refresh an enumerated punch list; **enumerate inline, never point** |
| `validate_brief.py` | script | The validator in §3(b) — required slots present and non-empty |
| `validate_report.py` | script | Same for implementation reports: completion artifact per mandated step; judgements acted on; siblings considered |
| hooks | config | `SessionStart` matcher `compact` → print the punch list back into context (`15` P12); anti-stall cron for unattended runs (`15` P11) |

### 4.3 Plugin: `prediction-scoring` — the surprise-factor experiment, moved to user level

Arnon: *"it was started in toolguard — but it applies to any agent-assisted project I develop. We should move its method, memory, criteria, statistics and fact records collection, and guidance to a user level."*

Contents: the pre-registration protocol; the blinded-estimator brief; the scoring script; the cause-code taxonomy; **and the accumulated record**, since the experiment's stated continuation condition is 20 human-authored tickets through the normal plan-first process and **none of those 20 exist yet**. Moving it is what makes reaching 20 possible across projects rather than in this one.

**Carry `05` §7's framing with it**: the value test is whether outlier reviews yield corrective action, at roughly a 50% bar — not predictive accuracy.

---

## 5. Changes to existing user-level skills — scope only

| skill | change |
|---|---|
| `code-review` | **Make executing a differential a standing instruction to the reviewer, not an optional technique.** This is the single highest-value change in this table: all three silent security defects were found by reviewers who ran something. Add the recipe — two isolated trees, `PYTHONPATH` pinned, **provenance printed from inside the measurement**, diffing decision *and* matched rule |
| `code-review` | Add: **a read-only "nothing substantive" verdict must state what it did NOT examine** |
| `documentation-review` | Add: **ask what the change made FALSE**, not what needs documenting |
| `development-process-review` | Add the `15` §4 weakness/mitigation table as its checklist spine |
| `reduce-complexity` | Add the **what-vs-how test** — an extraction that adds a thin pass-through reduces complexity and worsens architecture |
| `toolguard-maintenance`, `toolguard-security-audit` | No change from this analysis |

## 6. Changes to existing user subagents — scope only

| subagent | change |
|---|---|
| `feature-coder` | **Report template gains the slots from §3(a)** — completion artifact per mandated step (incl. *"refactoring performed while green — or none, and why"*), judgements acted on, siblings considered. **This is the highest-value subagent change and it is where the refactor-step failure gets fixed.** Also: **TOO-69** — package/module docstrings stating purpose and reasoning, to raise architectural conformance |
| `feature-coder` | Add: **the brief is unverified — including its architectural premises.** Two tickets' justifications were measurably wrong |
| `code-reviewer` | Mirror the `code-review` skill change: execute a differential |
| all with Bash | **Repair the dangling `mcp__jetbrains__*` allowlist entries** — six removed tools are still named, and a dangling entry fails silently |

## 7. New general tooling — scripts worth building

| # | script | what it does | evidence |
|---|---|---|---|
| S1 | `validate_brief.py` / `validate_report.py` | §3(b). **Build this first** — it is the mechanism the rest depends on | `15` P2, P6, P7 |
| S2 | `arch_axes.py` | project-specific axis profiles | `13` §4.2 |
| S3 | generalised `architecture_fitness.py` | declared-constraint checks, config-driven | `15` A7, A8 |
| S4 | **test-intent survey** | flag tests that exercise private functions, as candidates pinning implementation rather than requirement. **A heuristic reported as a heuristic**, never a verdict — per `15` I4 | Arnon 2026-08-27 |
| S5 | disclosure hook | flag an undisclosed heredoc / `-c` / scratch-script run | U7 |

**Not worth building**: anything producing an aggregate architecture score (`15` A10, A11).

---

## 8. Arnon's own process — the two modes, separately

### 8.1 Human-in-the-loop

| # | change | why |
|---|---|---|
| H1 | **Review proposals, not diffs** — and expect the architectural review to happen there | `15` A4. Your own finds came from proposals and from small change sets, never from merged code |
| H2 | **Cap the change set you accept for review.** Trigger on files-and-lines changed, not time | `15` P8. *"Now that changes are fewer files I start noticing things"* |
| H3 | **Voice unformed smells at quarter-confidence** | measured negative cost — one sentence instead of a sweep |
| H4 | **Say per ticket whether widening is authorised**, and whether a message is education or specification | `15` P10, I7 |
| H5 | **Do not let a manual review substitute for an instrument.** A reading review inherits exactly the blind spot the executing reviews closed | `15` V1 |
| H6 | **Own the filed-findings queue** — it is the cost side of the scope guard, and it is recurring | `15` P15 |
| H7 | **Expect to be verified.** U1 makes this explicit, and it needs your standing permission to work | `15` V9 |

### 8.2 Autonomous loops

| # | change | why |
|---|---|---|
| A1 | **Anti-stall cron, always** | `15` P11 — no substitute demonstrated, and a punch list does not close it |
| A2 | **Set a service level on the decisions queue before starting**, not after. The missing adjudicator is the binding constraint | `15` P15 |
| A3 | **Nothing prompt-blocking in any brief** — a blocked subagent looks exactly like a stalled one | `15` I6 |
| A4 | **Require the completion artifact** — this is where unobserved steps vanish, and there is no human to notice | `15` P6 |
| A5 | **Decide the fail-open policy up front.** The campaign's signature defect is a mechanism that fails open and says nothing; an autonomous loop has nobody to notice silence | `08` |
| A6 | **Budget for the understanding you will not acquire.** Autonomy defers that cost into a later reconstruction, and part of it is never recoverable | `08` §5c |

---

## 8.5 Conclusions that had no landing place — added 2026-08-27

**Found by auditing this document against `15`**: 22 register IDs are cited here and all resolve, but a set of **high-value** conclusions had no recommendation attached. Several turned out to be covered by content without a citation; the ones below were genuinely missing. **The first is the most serious, because Arnon flagged it himself.**

| # | conclusion | where it should land |
|---|---|---|
| **W1** | **`15` P9 — "prohibiting the fix increases the yield."** Arnon, 2026-08-27: *"a very important process finding."* A scope boundary that forbids fixing forces documenting — the #07 sweep produced **17 proposed defect tickets** under a brief that banned code changes | **A brief-template slot and a coordinator pattern.** Add to §3(a): a brief states whether the agent may fix, and *"document only"* is a first-class mode rather than a degenerate one. Also §6 `feature-coder`: a no-fix brief should be expected to return findings, not an empty diff |
| **W2** | `15` V3 — **in-process mutation testing** finds test blindness coverage cannot (per-module survival 47–58% before repair) | §7 as a script, and §5 as a `code-review` option for the mechanism a change touches. Currently the highest-value verification mechanism with **no recommendation at all** |
| **W3** | `15` I9 — **decouple behaviour-pinning from unit tests** | §6 `feature-coder` and §8.1. It is *"the only intervention that changes the **answer** rather than the instruction"* — if an agent keeps declining to restructure, the tests may be making the right call the expensive one |
| **W4** | `15` V7 — **prefer a runtime sentinel to an enumerated bad-list** | §4.1 `arch-review` scripts, and §7. Four escapes from one enumeration; the sentinel that closed the class **already existed in the repo 18 days before the ticket that needed it** |
| **W5** | `15` P14 — **a debt register: count workarounds, not their justifications** | §8.1 (Arnon owns it) — *"because each justification is individually sound, the count is the only visible signal"* |
| **W6** | `15` P13 — **schedule synthesis as its own step** | §8.1 and §8.2. *"Synthesis has to be scheduled as a step with its own moment in the process, not trusted to fall out of doing enough narrow checks."* Applies to both modes |

**Method note, because it cuts both ways.** The audit first reported *"26 high-value conclusions unplaced"*. Checking each against `16`'s content rather than its citations showed several were covered without a `15 XN` marker (A3's two-judge setup, A12's back-test, V8, P5, I8, P17, V5, V6, I1). **A citation-based coverage check over-reports; a phrase-based one under-reports.** The six above survived both. **Traceability is still a real defect even where content is covered**: a reader cannot tell which conclusions landed where, and `16` is meant to be actionable *from* `15`.

## 9. Sequencing — what to do first

1. **`validate_brief.py` / `validate_report.py`** (S1). Everything in §3 and most of §6 depends on it, and it carries its own falsifier.
2. **The `feature-coder` report slots** (§6). Cheapest test of the highest-frequency failure.
3. **The `code-review` differential instruction** (§5). One edit, addresses the worst defect class in the corpus.
4. **`CLAUDE.md` moves** (U6–U8) — subtraction, no new mechanism needed.
5. **The `arch-review` plugin** (§4.1) — the largest build; do it once the cheap items have shown whether the slot mechanism works.
6. **`prediction-scoring`** (§4.3) — move it when a non-toolguard project is available to run it on.

**Do not do all of these at once.** Items 1–3 are independently falsifiable; the value of doing them first is that they will tell you whether §0's governing principle is right before you build a plugin on top of it.
