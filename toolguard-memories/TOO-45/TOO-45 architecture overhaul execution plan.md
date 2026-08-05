---
title: TOO-45 architecture overhaul execution plan
type: note
permalink: toolguard/too-45/too-45-architecture-overhaul-execution-plan
tags:
- task-memory
- TOO-45
- architecture
- plan
---

# TOO-45 execution plan

Draft 1, 2026-08-03. Supersedes the loop protocol in `tmp/architecture-remediation-plan.md`
(which remains valid as the diagnosis and the metric design). Written after re-measuring the
baseline and after Arnon's first-principles comment on the ticket.

Decisions already taken by Arnon and treated as settled:

- Git writes are **relaxed for the `too-45` branch only** (see S4 for the exact boundary).
- R6's scope (one ticket or two) is **decided after the as-is picture exists**, not now.
- Two checkpoints: **CP1** after prerequisites, **CP2** after the first refactoring step closes.
- The canary is run by a **fresh agent every time**.
- No parallel agents touching the working tree. Subagents for fresh-context roles only.
- Workflow and `/loop` usage is Claude's call; Arnon reviews.
- TOO-28 is NOT a precondition any more: Arnon set both fallbacks to `allow_with_no_warnings`
  temporarily, accepting the risk knowingly, mitigated by a safety inspector (S4).

---

## 0. What re-measurement changed

Measured 2026-08-03 on `too-45` at `532de02`.

| | ticket says | actual today | consequence |
|---|---|---|---|
| `config.py` LOC | 2,727 | **2,905** | drift continued during TOO-19; re-baseline everything |
| `hook.py` LOC | 1,131 | **1,235** | same |
| reason-parse sites | 6 | **3** | R3 is roughly half the size budgeted |
| `additionalContext` footprint | ~9 files (as a change) | **14 files (as a concept)** | see S1 |

The reason-parse sites remaining are `resolve.py:563`, `hook.py:461`, `hook.py:978`. TOO-19's
review fixes removed the rest. R3 is now a small step, which is good — it is the first real
refactor and therefore the one that has to teach us whether the loop works.

---

## 1. The plan change proposed, and why

### The old step list cannot move the acceptance test

The programme's stated acceptance test is the canary: *add a new enrichment key end-to-end,
from TOML parse to hook output to log*, counting production files touched. Target <=4.

The six planned steps are R0 (layer checker), R3 (no prose parsing), R5 (scripts are leaves),
R6 (tooling consumes an interface), R1 (one verdict type), R2 (one rule representation).

**None of them is about enrichment being a pluggable concept.** Measured today:

```
additional_context / additionalContext -> 14 production files
compound 36 | hook 32 | resolve 29 | log_writer 16 | rule_entry 9 | config 9
tools/decision 8 | testing/sandbox 5 | rule_sort 5 | toml_scan 2 | config_types 2
tools/installer 1 | tools/config_access 1 | config_write_guard 1
```

`additionalContext` is a **named field threaded by hand through every pipeline stage**. R1 and
R3 are necessary preconditions for fixing that — you cannot carry directives as data through
four verdict types, and you cannot render them cleanly while reasons are parsed — but they are
not sufficient. All six steps could close with the canary unchanged.

Arnon's comment names the missing concept directly:

> advanced directives are an evolving thing and future changes are likely to add more. Some of
> those are applied at rule evaluation time and some are applied later in the process all the
> way to the end. The design should be flexible enough to make this evolution adaptation easy
> and natural for the code.

### Proposed: R0 becomes a prerequisite, R7 becomes a step

**R0 is demoted.** Its exit condition is "the checker exists and reports" — that is an
instrument, not a refactoring step. Calling it a step inflates the step count and invites
treating instrument-building as progress. It belongs in prerequisites, where its quality gates
CP1.

**R7 is added: directives are data with declared phases, not hand-threaded fields.** This is the
step the canary measures. Its predicate and its risk are in S3.

### Candidate step, pending the as-is picture

**Config load and config query are one thing today, and probably should not be.** Arnon's flow
step 4 (discover, parse, order by authority, produce a structured representation) is a *load
phase*; steps 5-8 (match, decide, consolidate) are a *request phase*. `config.py` at 2,905 LOC
with fan-in 25 of 68 modules is what you get when one module is both. Not proposed as a step
yet — P3 (the as-is picture) either supports it or kills it.

### Re-ordering hypothesis

Not a decision. P3 settles it. Current best guess:

```
P (prerequisites)  ->  CP1
R3   no prose parsing              small, and it de-risks everything after it
                   ->  CP2   <-- the "is this loop working" assessment
R1   one verdict type              enabler for R7 and for the external seam
R7   directives are data           the step the canary measures
R5   entry points and scripts are leaves
R6   engine interface for tooling  size and ticket-split decided after P3
R2   one rule representation
```

The change from the ticket's order is that **R1 moves from fifth to second**. Justification is
Arnon's own framing of flow step 11: the internal-to-external seam must be independently
maintainable because a Claude Code spec change can be an *emergency*. The ticket justified R1 as
tidiness ("four types for one concept"). Emergency maintainability is a much stronger reason and
it puts R1 upstream of R7 where it is needed anyway.

---

## 2. Prerequisites (the P phase) — all gate CP1

### P1. Verdict-equivalence corpus. The load-bearing guard.

Everything else in this programme is defensible only because this exists. Build it first, and
prove it works before trusting it.

**Sources, in order of value:**

1. **Real traffic.** `logs/toolguard-*.md` holds 17,167 recorded decisions over 50 days —
   commands Claude actually issued in this project. That is a real distribution, not an
   imagined one, and it covers compound commands, heredocs, and shapes no one would think to
   write by hand.
2. **Synthetic edge cases**, hand-built to cover what real traffic under-samples: every fallback
   value, both ASK floors, hard-deny, parse failure, undecidable segments, each config level and
   authority-ordering conflict, glob/regex/native pattern forms, `additionalContext` present and
   absent.
3. **The existing test suite's config fixtures**, harvested for configs rather than assertions.

**Critical design point: goldens come from HEAD, not from the logs.** The logged verdicts were
produced by older code under configs that were not recorded. Verdict equivalence means *before
vs after this refactor*, not *matches history*. So: extract commands from the logs, pin a set of
configs, and generate goldens by replaying through `toolguard.testing.sandbox` at the refactor's
start commit.

**Privacy — a real problem the ticket missed.** The repo is public (`uv tool install
git+https://github.com/arnonmoscona/toolguard` resolves without auth). Those 17,167 commands are
real commands from Arnon's machine: absolute home paths, project names, tool arguments, possibly
credentials or tokens in command text. **Committing raw log-derived commands to a public repo is
a leak.** Mitigation, to be confirmed before P1 starts:

- Normalise paths (`/home/arnon` -> `$HOME`, project root -> `$PROJECT`) — required regardless,
  since the corpus must replay on any machine.
- Scan for secret-shaped tokens and drop those entries entirely rather than redacting them.
- Manual review of the extracted set before it is committed. Non-negotiable.
- Fallback if review is too expensive: keep the log-derived half of the corpus **untracked**
  and commit only the synthetic half. Weakens the guard; better to pay for the review.

**Proving the corpus, not assuming it.** A corpus that passes is worthless unless it can fail.
Before CP1, **mutation-test it**: seed deliberate behaviour changes (flip a strictness
comparison, drop a floor, swap an authority order, silently drop `additionalContext`) and
confirm the corpus catches each one. The mutation results are the CP1 evidence. If it catches
fewer than all of them, the corpus is not done.

**Make it permanent.** This should live in `test/` and run as part of the suite, not as a
TOO-45 scratch artifact — it is a behavioural regression guard worth having forever. Caveat to
state plainly: golden files pin current behaviour *including any current bugs*. Fixing a bug
later means deliberately updating goldens, which is fine as long as the update is explicit and
reviewed. That is a feature of golden testing, not a defect, but it must be documented next to
the corpus or someone will "fix" a failing golden by regenerating it.

### P2. `tools/architecture_fitness.py`

Stdlib-only, committed. Reads `.pyscn.toml` as the single source of truth for the layer map.
Four jobs:

- `--layers` — every module under `toolguard/` maps to exactly one layer; exits non-zero naming
  offenders. Also reports modules pyscn cannot see, closing the unmappable-module hole
  (`toolguard.testing.sandbox` today).
- `--predicates --json` — every step's predicate as true/false plus diagnostics. This is the
  loop's progress signal, and it is what survives a compaction.
- `--metrics` — the history-based metrics, computed per logical change (ticket), not per commit.
- `--guard` — the deterministic half of the safety inspector. See S4.

### P3. The as-is picture, at the same altitude as the ideal picture

Arnon's comment asks for this explicitly and it is the item that most changes what follows:

> create the "actual high level picture" of the code organization working backwards from the
> concrete code base and its recent history. This will give you two high level pictures — what
> you actually have vs what you putatively want to have.

Deliverables: the ideal picture (derived from the eleven-step flow in Arnon's comment, drawn as
modules/layers/seams), the as-is picture at the same altitude, and **the delta** — for each ideal
boundary, where it is currently smeared and across which files.

The step order in S1 is a hypothesis until this exists. So is the config load/query split. So is
R6's size, and therefore whether it needs its own ticket.

### P4. Guardrails as rules, not prose

TOO-28 is not in place, so the fallbacks are `allow_with_no_warnings` and toolguard is enforcing
**only explicit deny rules**. Invariant 6 (never touch `logs/`, outside the repo, `.env`,
permission config) currently exists only as prose in a prompt, and this project's documented
lesson is that prose "MUST" language gets dropped.

So: write invariant 6 as **deny rules**, plus deny rules bounding the git relaxation (S4). Cheap,
deterministic, and exactly the half of the problem that needs no semantic judgement.

### P5. Decision log and interface drafts

Decision log appended every iteration: what was tried, what the judge said, which interface
drafts survived contact, which predicates turned out wrong, spend-to-date. A methodology guide
written from memory afterwards is fiction; written from a decision log it is evidence.

### Already done, not re-litigated

Ticket deliverable 2 (cross-ticket architectural-drift detection in the code-review guidance)
landed during TOO-19 — `~/.claude/skills/code-review/SKILL.md:64`, "Architectural drift — a
separate pass, looking past this change set".

---

## 3. Steps and predicates

Unchanged from the ticket except as noted. Predicates **scope** the work; they do not close it.

### R3 — Decisions carry structured data; prose is rendered, never parsed
Predicate: zero production sites read structured information out of a reason string.
Baseline: 3 sites. Gaming move to watch: consolidating three parse sites into one helper.

### R1 — One verdict type
Predicate: exactly one type represents a permission verdict end-to-end; the `__iter__`
tuple-compatibility shims are gone along with their callers.
Real justification: the internal-to-external seam must be replaceable under emergency time
pressure when the hook spec changes.

### R7 — Directives are data with declared phases (NEW)
Predicate: adding a new enrichment key requires touching only (a) a directive declaration
including its validation, (b) its accumulation policy if it needs a non-default one, and (c)
nothing else. `additionalContext` is expressed as one directive under that scheme, not as a
named field on five dataclasses.
Evidence it matters: 14 production files today.
Risk: this is the step most likely to be over-designed. A plugin registry with hooks at eleven
phases would be worse than what exists. The wargame (S5) is mandatory here, and the judge should
be explicitly asked whether the abstraction earns its weight — one directive is not evidence
that a directive *framework* is warranted. If the wargame says a simpler shape (a typed
`directives` mapping carried on the single verdict type, rendered in one place) gets the canary
to <=4, take the simpler shape and record that the framing was too grand.

### R5 — Entry points and scripts are leaves
Predicate: no `runtime` or `scripts` module appears as a non-leaf; the `hook <-> tools.decision`
cycle is gone.

### R6 — The engine has a public interface and the tooling consumes only that
Predicate: no `tools/` or `scripts/` module imports a private name from `config`, `permissions`,
`compound`, or `resolve`.
Scope decision deferred to P3.

### R2 — One rule representation
Predicate: no parallel arrays on `ToolPatternLayer`; stripped patterns are a derived property of
`RuleEntry`; no prose-defended index-alignment invariant remains.

### Out of scope, unchanged
R4 (unify the two resolution pipelines) — separate ticket. `toolguard/parser/` including the
generated parser. Individual `tools/*` analysers except where R6 changes their imports. Any
behaviour change.

---

## 4. Safety: deterministic first, semantic second

Arnon suggested a separate safety inspector to offset running without TOO-28. Taking it, and
splitting it the same way this project splits toolguard from auto-mode guidance — **the
deterministic half must not be delegated to judgement.**

**Deterministic (`architecture_fitness.py --guard`, every iteration, cheap):**

- any file touched outside the repo, or under `logs/`, `.env`, `.claude.env`, or permission
  configuration
- any test file deleted, or a test count that went down
- any new entry in `pyproject.toml` dependencies
- any git operation outside the allowlist
- `ruff check` / `ruff format --check` / `check_doc_links.py`

**Semantic (safety-inspector subagent, cheap model, every iteration or two):**
Sees only the iteration's diff and a fixed prohibition checklist. Answers one question: *did
this iteration do anything it must not?* Its remit is the part a script cannot see — a test
weakened rather than deleted, a predicate satisfied hollowly, an invariant honoured in letter
and broken in spirit, scope creep into R4 or the parser.

It is **not** the judge. It has no opinion on quality or direction. Cheap enough to run
constantly, which is the point: it catches deviations early rather than at a step boundary.

**The git boundary, stated exactly.** Allowed on branch `too-45` only: `git add`, `git commit`,
and all read-only commands. Prohibited without a fresh explicit request, whatever the reason:
`push`, `checkout`, `switch`, `branch`, `merge`, `rebase`, `stash`, `reset`, `revert`, `clean`,
`tag`, `worktree`, `cherry-pick`, and any `--force` anything. Branch is verified before every
commit. This goes into deny rules in P4, not just into this document — a subagent already
violated the git rule once during TOO-19 with `stash`/`stash pop`.

---

## 5. The loop, per iteration

```
orchestrator frames the cycle: objective, expected size, what would falsify it
  |
  +- draft or revise the interface for the modules in scope        (conceptual first)
  +- optionally wargame it in a throwaway playground               (mandatory for R7 and R6)
  +- make ONE coherent change
  +- deterministic guard  -> fail: revert, record why
  +- invariants           -> fail: revert, record why
  +- verdict corpus       -> any changed verdict: revert, no exceptions
  +- safety inspector     -> flagged: stop, escalate
  +- predicates + metrics as evidence, not exit criteria
  +- append to decision log
```

**A wargame that invalidates an interface draft is a success of the method.** Record it and
revise; do not push through.

**No-progress limit:** three consecutive changes leaving the predicate false and moving no
diagnostic -> stop and escalate.

**Anti-gaming prohibitions, stated to every agent in the loop:** do not split or merge commits to
influence a measurement; do not split a module solely to reduce fan-in; do not delete or weaken a
test; do not introduce a pass-through module solely to break a cycle. If a predicate can only be
satisfied that way, **stop** — the predicate is wrong.

---

## 6. Two judges, because "blinded" and "keeps the big picture" contradict

The ticket says the judge must **not** be told what the step was meant to achieve — give a
reviewer the goal as a pass condition and you get a reviewer that confirms it was met. Arnon also
wants the judge to hold the big picture and nudge the orchestrator on task.

Both are right and they cannot be the same agent. So, two roles:

**The blinded reviewer.** Sees before/after and nothing else. No goal, no predicate, no metrics,
no plan. Answers one question: *is this easier to review, and why?* This is the anti-confirmation
instrument and its value comes entirely from its ignorance.

**The architect judge.** Sees everything — the ideal picture, the as-is picture, the plan, the
interface drafts, the wargames, the decision log, the metrics, the diff. Judges *direction* and
*reasoning*, not just result. This is the one that can say "this landed, but for the wrong
reason, and the next step will suffer", nudge the orchestrator's framing, and propose plan
changes. Per Arnon: the plan is not holy, but changing it often is a symptom, so a plan change
must be argued in the decision log, not made silently.

**A step closes when both agree**: the blinded reviewer finds it genuinely easier to review, and
the architect judge finds it the right direction. Blinded reviewer satisfied but architect judge
unconvinced means the step is locally tidy and strategically wrong — keep going. The reverse
means it is right in principle but not yet real — also keep going.

---

## 7. Mechanism: what runs where

| work | mechanism | why |
|---|---|---|
| the refactoring itself | main session, prompted | sequential, stateful, one working tree. Parallelism is the failure mode, not the speedup |
| safety inspector | subagent, cheap model, every 1-2 iterations | needs fresh eyes and low cost; wrong job for the main context |
| blinded reviewer | subagent, fresh every time | its value *is* its ignorance; a warm context cannot be blinded |
| architect judge | subagent, capable model, step boundaries | needs the full artifact set; too expensive per iteration |
| canary | subagent, fresh every time, step boundaries | measures a newcomer's cost; reuse destroys the measurement |
| step-boundary review | **workflow** | blinded reviewer + architect judge + canary in parallel, all read-only. Genuine independent-perspective fan-out — the one place a workflow earns its keep |
| unattended continuation | **`/loop`**, after CP2 only | before CP2 Arnon gates every step anyway, so self-pacing buys nothing |

State lives in durable artifacts (this note, the decision log, the predicate JSON, the corpus)
precisely so that a compaction or a fresh session loses nothing. That is an operating
requirement, not a nicety — this run will span many contexts.

---

## 8. Checkpoints and budget

**CP1 — after prerequisites. Hard stop regardless of budget.**
Evidence presented: mutation-test results for the corpus (must catch every seeded change), the
fitness script's first full report, the as-is/ideal/delta picture, the guardrail deny rules, and
a proposed final step order. If the corpus does not catch every seeded mutation, the programme
does not start.

**CP2 — after R3 closes.** The "is this loop working" assessment. R3 exercises the entire
machinery once — interface draft, change, invariants, corpus, guard, inspector, both judges,
canary — on a step now known to be small. Good information per unit spend.

**On budget.** No sound basis exists for a token estimate up front, and inventing one would
create a false anchor. Instead: every iteration appends spend-to-date and elapsed wall-clock to
the decision log, so the trend is visible and Arnon can call it at any point. If a number is
wanted up front, set a soft ceiling at CP1 and revise it with real data.

---

## 9. Open items for the CP1 review

1. Corpus privacy handling — normalise-and-review, or synthetic-only? (S2/P1)
2. Final step order, after the as-is picture. (S1)
3. R6 as its own ticket. (deferred by decision)
4. Whether the config load/query split becomes a step. (S1)

---

## Clarifications from discussion

- Arnon, 2026-08-03: *"Metrics are a guide, not an objective. The deciding factor is
  judgement."* Carried forward from the TOO-45 planning session; the judge is the gate,
  predicates only scope.
- Arnon, 2026-08-03: the orchestrator frames objective/size/effort per cycle; the judge both
  decides stopping points **and** keeps everyone on task with the big picture in mind, nudging
  the orchestrator as the effort unfolds. This is what forced the two-judge split in S6.
- Arnon, 2026-08-03: *"the plan itself is not holy... no battle plan survives the first shot of
  battle."* Plan changes are fair play but must be argued and recorded; frequent changes are a
  symptom of bad planning, not adaptability.
- Arnon, 2026-08-03: aware of the risk of proceeding without TOO-28; accepted, to be mitigated
  by judge guidance and/or a separate safety inspector at reasonably low cost.
- Arnon, 2026-08-03: no parallel agents ("that would hopelessly tangle up the yarn"); subagents
  approved; workflow and `/loop` design delegated to Claude with review.

## Relations

- relates_to [[TOO-19 Structured Rule Entries - Rule-Match Enrichment]]
