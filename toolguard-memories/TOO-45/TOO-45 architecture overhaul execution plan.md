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

Draft 2, 2026-08-04. Supersedes draft 1 and the loop protocol in
`tmp/architecture-remediation-plan.md` (which remains valid as the diagnosis and the metric
design). Revised after Arnon's review of draft 1.

## Settled

- Git writes **relaxed for branch `too-45` only**; enforced in
  `~/.toolguard/rules/git.rules.toml`, not just in prose. **Applied and verified** (S4).
- **R0 demoted** to a prerequisite. **R1 promoted** to the first step after R3.
- **R7 is not a step** — it is a tracked outcome with a trigger (S1).
- Corpus privacy: **closed**, logs are not on GitHub; sanitise anything committed (S2/P1).
- Two checkpoints: **CP1** after prerequisites (hard stop), **CP2** after R3 closes.
- Canary run by a **fresh agent every time**. No parallel agents on the working tree.
- Workflow and `/loop` design delegated to Claude, reviewed by Arnon.
- TOO-28 is **not** a precondition: both fallbacks are temporarily
  `allow_with_no_warnings`, risk accepted, mitigated by a safety inspector (S4).
- R6 scope (one ticket or two) decided **after** the as-is picture.

---

## 0. What re-measurement changed

Measured 2026-08-03/04 on `too-45` at `532de02`.

| | ticket says | actual | consequence |
|---|---|---|---|
| `config.py` LOC | 2,727 | **2,905** | drift continued during TOO-19; re-baseline everything |
| `hook.py` LOC | 1,131 | **1,235** | same |
| reason-parse sites | 6 | **3** | R3 is roughly half the size budgeted |
| `additionalContext` footprint | ~9 files (as a change) | **14 files (as a concept)** | S1 |

Remaining reason-parse sites: `resolve.py:563`, `hook.py:461`, `hook.py:978`. TOO-19's review
fixes removed the rest. R3 is now small — good, because it is the first real refactor and
therefore the one that has to teach us whether the loop works.

---

## 1. Organising principle: isolate what changes on someone else's schedule

Draft 1 justified R1 as "one verdict type", which is a statement about tidiness. The better
statement came out of Arnon's review, and it covers three things rather than one.

**Three external seams, all driven by specifications we do not control:**

1. **Input** — the hook event shape. Changes often (per the Claude Code hooks documentation).
2. **Output** — the hook response shape. Changes, and a breaking change is an *emergency*:
   it must be absorbable without touching internal mechanics.
3. **Native rule syntax** — the Claude permission syntax toolguard accepts as a drop-in.
   Changed at least once in ~4 months. Frequent for a public interface.

The unifying property is not "these are I/O". It is that **all three change on someone else's
schedule**, so each needs a seam we own, thin enough to re-fit under time pressure.

**Constraint on the third seam (Arnon):** migration from native settings to toolguard settings
must stay a *shallow* script that **does not need to parse** native rules — toolguard accepts
the syntax as a drop-in, so migration is transport, not translation.

That yields a falsifiable hypothesis for P3: **if `scripts/migrate_permissions.py` currently
parses native rule syntax, that explains why it is a top-five co-change hub** (15 partners,
co-changing with `hook.py` 80% of the time). A transport script should be a rarely-touched leaf.
It is not.

**Post-overhaul idea (Arnon, not in scope now):** give the migration a small helper that
verifies what it migrated actually *parses*, and raises an alarm if not — e.g. Anthropic
introduced new pattern syntax. It must **not** try to edit entries; the alarm is the feature.
Keeps the script shallow while making a silent drift loud.

---

## 2. Enrichment: a tracked outcome, not a step

Draft 1 proposed "R7: directives are data with declared phases". Arnon pushed back on both
halves and was right on both.

**"Declared phases" is dropped.** Beyond Arnon's argument that phases are an internal
implementation artifact and not a documented concept, there is a decisive concrete reason:
`additionalContext` is **already multi-phase** — accumulated across command parts, then
rendered into the hook response *and* into the decision log. The first and only directive would
falsify a single-phase tag. An abstraction contradicted by its only instance is a guess. It also
leaks an implementation word into the config surface, where it would become documented and then
load-bearing.

**Not a step, either.** Arnon: the real abstraction will emerge as a byproduct of the
refactoring iterations rather than being declared up front. Agreed — declaring it now means
designing against 14 grep hits instead of against code that has actually been read. Also,
Arnon's flow sketch was a way of *framing the problem before committing to structure*, not a
blueprint; reading it as a specification is exactly the error that produces
architecture-by-inference.

**But the failure mode is named rather than assumed away.** The canary is the acceptance test.
If nothing targets the enrichment footprint, every step can close with the canary flat. So:

- the **enrichment footprint** (14 production files today) is a first-class diagnostic reported
  alongside the canary;
- a **flat canary at a step boundary is a finding that drives the next iteration**, not a
  neutral observation;
- if the step list is exhausted with the footprint materially unchanged, that becomes a
  declared step at that point, with evidence.

---

## 3. Steps and predicates

Predicates **scope** the work; they do not close it. The judges close it.

Order (hypothesis until P3 settles it):

```
P (prerequisites)  ->  CP1
R3   no prose parsing              small, and it de-risks everything after it
                   ->  CP2   <-- the "is this loop working" assessment
R1   one verdict type              the output seam; see S1
R5   entry points and scripts are leaves
R6   engine interface for tooling  size and ticket-split decided after P3
R2   one rule representation
```

**R3 — decisions carry structured data; prose is rendered, never parsed.**
Predicate: zero production sites read structured information out of a reason string.
Baseline 3. Gaming move: consolidating three parse sites into one helper.

**R1 — one verdict type.**
Predicate: exactly one type represents a permission verdict end-to-end; the `__iter__`
tuple-compatibility shims are gone along with their callers. Justification is the output seam
(S1), not tidiness.

**R5 — entry points and scripts are leaves.**
Predicate: no `runtime` or `scripts` module appears as a non-leaf; the `hook <-> tools.decision`
cycle is gone.

**R6 — the engine has a public interface and the tooling consumes only that.**
Predicate: no `tools/` or `scripts/` module imports a private name from `config`, `permissions`,
`compound`, or `resolve`.
**Enforcement (Arnon's suggestion, accepted and extended):** make the interface its own module
and its own declared pyscn layer, so a violation floats predictably in every code review —
`foundation < config < engine < api < runtime < tooling < support`.
**Extension: `runtime` (hook.py) must consume the same interface, not just `tools/`.** An
interface used only by tooling drifts from what the engine really does, because its primary
consumer bypasses it. Making the main path use it keeps it honest.
**Caveat:** given pyscn's unmappable-module hole, `architecture_fitness.py` must confirm the
`api` layer is actually *seen*, not silently unknown.

**R2 — one rule representation.**
Predicate: no parallel arrays on `ToolPatternLayer`; stripped patterns are a derived property of
`RuleEntry`; no prose-defended index-alignment invariant remains.

**Candidate step, pending P3:** config **load** and config **query** are one thing today and
probably should not be. Discovery/parse/authority-ordering is a load phase; match/decide/
consolidate is a request phase. `config.py` at 2,905 LOC with fan-in 25 of 68 is what one module
being both looks like.

**Out of scope, unchanged.** R4 (unify the two resolution pipelines) — separate ticket.
`toolguard/parser/` including the generated parser. Individual `tools/*` analysers except where
R6 changes their imports. Any behaviour change.

---

## 4. What makes an interface layer real (the judge's test)

Arnon's framing, recorded because it is the actual acceptance test for R6 and the thing most
likely to be lost to a passing layer check:

> For each function or class ask: is this about the **what to do** or about the **how to do**?
> Is this something that has a chance to be stable under ongoing maintenance, or is it too thin,
> such that it would change every time the underlying code changes?

> Designing layers is not about aesthetics. It is about maintainability and preventing concept
> leaks. A layer's external interface is much like a system's public API — it should strive to
> be stable, to evolve in a backward-compatible and non-breaking fashion most of the time, and
> to focus on **what** the layer does for everybody outside it while encapsulating **how** it is
> done.

Operational consequence: "does it pass the layer check" is necessary and nowhere near
sufficient. A facade of thin pass-throughs passes the check and fails this test, and it is also
the anti-gaming prohibition on pass-through modules wearing a different hat. The distinction
between a designed surface and an accumulated one lives in judgement, so it must be **asked
explicitly** at every R6 review, not inferred from a green check.

---

## 5. Prerequisites (the P phase) — all gate CP1

### P1. Verdict-equivalence corpus. The load-bearing guard.

**Sources:** (1) real traffic — `logs/toolguard-*.md`, 17,167 recorded decisions over 50 days,
covering compound commands and heredocs nobody would invent by hand; (2) synthetic edge cases
for what real traffic under-samples — every fallback value, both ASK floors, hard-deny, parse
failure, undecidable segments, each config level and authority conflict, glob/regex/native
pattern forms, `additionalContext` present and absent; (3) the existing suite's config fixtures,
harvested for configs rather than assertions.

**Goldens come from HEAD, not from the logs.** Logged verdicts came from older code under
configs that were never recorded. Verdict equivalence means *before vs after this refactor*, not
*matches history*. Extract commands, pin configs, generate goldens at the start commit.

**Privacy: closed.** Arnon: the logs are not on GitHub, and transmission to Anthropic is no
different from any other Claude Code activity. Anything that lands in committed tests gets
sanitised so it is not machine- or account-specific; ephemeral corpora carry no meaningful risk.
Path normalisation stays anyway — the corpus must replay on any machine. **Standing duty:** if
anything genuinely secret-shaped shows up in the logs, alert Arnon.

**Prove it, do not assume it.** Before CP1, mutation-test: seed deliberate behaviour changes
(flip a strictness comparison, drop a floor, swap an authority order, silently drop
`additionalContext`) and confirm the corpus catches each. Those results are CP1's evidence. A
corpus that has never failed is a decoration, not a guard.

**Make it permanent**, in `test/`, running with the suite. Golden files pin current behaviour
*including current bugs*; fixing a bug later means deliberately updating goldens, which is fine
if explicit and reviewed — but it must be documented next to the corpus or someone will "fix" a
failing golden by regenerating it.

### P2. `tools/architecture_fitness.py`

Stdlib-only. Reads `.pyscn.toml` as the single source of truth for the layer map.

- `--layers` — every module under `toolguard/` maps to exactly one layer; exits non-zero naming
  offenders; reports modules pyscn cannot see (closing the unmappable-module hole).
- `--predicates --json` — **component diagnostics, not just the compound boolean.** Arnon: the
  compound predicates are artificial; the individual scores have concrete meaning, and the judge
  must evaluate those independently. Emit components; the boolean is a convenience.
- `--metrics` — history-based metrics, per logical change (ticket), not per commit.
- `--guard` — the deterministic half of the safety inspector (S6).

**Where it lives (Arnon's constraint).** Verified: `[tool.hatch.build.targets.wheel]
packages = ["toolguard"]`, so repo-root `tools/` is already outside the wheel, alongside
`check_doc_links.py` and `coverage_stdlib.py`. It is therefore already not part of the product —
but *incidentally*, and Arnon wants it enforced. Add a test asserting no module under
`toolguard/` imports from repo-root `tools/`. Intermediate commits may carry it freely.

**Naming hazard found while checking this:** `tools/` (repo root, dev-only, not shipped) and
`toolguard/tools/` (operator tooling, shipped) are two different things with the same name and
opposite shipping status. A standing confusion hazard and a plausible small contributor to the
layering muddle. Worth renaming during the overhaul.

### P3. The as-is picture, at the same altitude as the ideal picture

Deliverables: the ideal picture, the as-is picture at the same altitude, and **the delta** — for
each ideal boundary, where it is currently smeared and across which files.

**How to treat Arnon's flow sketch.** It is not a set of directives and not an architecture. It
is an illustration of how an experienced engineer frames a problem *before* deciding on any
structure, offered so the same habit can be copied. So: think about it independently,
creatively, and critically. Those are ideas from an experienced engineer, not infallible ones.
Large deviations from it are a signal to investigate — either the code is badly organised, or
the framing needs restating — not automatically a fault in the code.

Falsifiable hypotheses to carry into P3:

1. **`migrate_permissions.py` parses native rule syntax** (S1) — would explain a 15-partner
   co-change hub in a file that should be a leaf.
2. **`hook.py` and `log_writer.py` are 100% co-coupled because the decision is rendered twice
   from scratch** rather than rendered once and consumed twice. Under the ideal flow, logging
   and externalising are two consumers of one internal verdict. If the hypothesis holds it is
   the same shape as the enrichment problem and has a concrete fix. If it fails, the ideal
   picture needs revising — useful either way.

P3 settles: the step order, the config load/query split, and R6's size and ticket-split.

### P4. Guardrails as rules, not prose — DONE for git

Applied to `~/.toolguard/rules/git.rules.toml` 2026-08-04 and verified end-to-end (S6).

**Still to do:** `Write`/`Edit` denies for `logs/**`, `**/.env`, `**/.claude.env`,
`~/.toolguard/rules/**`, `~/.claude/settings.json`, and both `toolguard_hook.toml` files.
Honest limit: those cover the file tools well, but Bash-side writes (`>`, `tee`, `rm`, `mv` into
those paths) cannot be caught exhaustively by patterns. That gap is what `--guard` is for — it
checks what was actually touched, after the fact, instead of predicting every spelling.

### P5. Decision log, resume note, lessons note

- **Decision log** — appended every iteration: what was tried, what each judge said, which
  interface drafts survived contact, which predicates turned out wrong, spend and elapsed time.
- **`TOO-45 RESUME HERE`** — rewritten (not appended) at each step boundary, ~one page.
- **Lessons note** — separate from the decision log and written *during*. The decision log is
  what happened; lessons are what transfers. Arnon's framing: this overhaul should teach how to
  tackle problems of this kind, how to avoid creating them, and what works — from going through
  it, not only from his comments. Reviewed at the end for what to keep and in what form
  (possibly, but not necessarily, a Claude skill; the English sense matters more).

### Already done, not re-litigated

Ticket deliverable 2 (cross-ticket architectural-drift detection in code-review guidance) landed
during TOO-19 — `~/.claude/skills/code-review/SKILL.md:64`.

---

## 6. Safety: deterministic first, semantic second

Arnon suggested a separate safety inspector to offset running without TOO-28. Accepted, split
the same way this project splits toolguard from auto-mode guidance — **the deterministic half
must not be delegated to judgement.**

**Deterministic (`architecture_fitness.py --guard`, every iteration, cheap):** any file touched
outside the repo or under `logs/`, `.env`, `.claude.env`, or permission configuration; any test
file deleted or test count reduced; any new `pyproject.toml` dependency; any git operation
outside the allowlist; `ruff check`, `ruff format --check`, `check_doc_links.py`.

**Semantic (safety-inspector subagent, cheap model, every 1-2 iterations):** sees the
iteration's diff and a fixed prohibition checklist. One question: *did this iteration do
anything it must not?* Its remit is what a script cannot see — a test weakened rather than
deleted, a predicate satisfied hollowly, an invariant honoured in letter and broken in spirit,
scope creep into R4 or the parser. It is **not** a judge and has no opinion on quality.

### The git boundary, as enforced

Applied in `~/.toolguard/rules/git.rules.toml` inside `<TEMPORARY>` fences (revert = delete the
fences). Verified end-to-end via `toolguard --eval` and via `tmp/git_rules_check.py`
(145 cases, 0 failures) on 2026-08-04.

| verdict | commands |
|---|---|
| allow | `status` and all read-only forms, `add`, `commit`, `rm <file>`, `mv`, `restore`, `revert`, `stash list`, `bisect log` |
| ask | `checkout` `switch` `reset` `merge` `cherry-pick` `rebase` `am` `push` `fetch` `pull` `branch` `tag` `worktree` |
| deny | `clean` `stash` (non-read) `bisect` (non-read) `rm -r` `commit --amend` `config` `init` `clone` `bisect run` `-c k=v` |

**Mechanic worth remembering:** with `no_match_fallback = "allow_with_no_warnings"`, *removing*
a rule from `allow` does not stop a command — it falls through and is silently allowed. Anything
that must be stopped needs an explicit **deny**. This inverts the usual instinct and is a direct
consequence of the TOO-28 waiver.

**Why `clean` and `stash` are denied.** `git clean` deletes untracked and (with `-x`) ignored
files: `toolguard-memories/` (this plan and the decision log), `logs/`, `tmp/`. `git stash` is
redundant now that the loop may commit, and its failure mode is silent — a stashed change leaves
a tree that no longer matches what the loop believes it is testing, so the invariants and the
corpus pass against the wrong state. Arnon is right that damage cannot leak off the branch;
containment was not the concern, silent desync was. A subagent already ran `stash`/`stash pop`
on a dirty tree during TOO-19.

**Drift found and fixed:** `tmp/git_rules_check.py` validated `tmp/git.rules.toml` (the pristine
copy) while toolguard reads `~/.toolguard/rules/git.rules.toml`. The harness the file's own
header tells you to re-run after every edit had never seen any of them. Now points at the
governing file.

**Left deliberately unchanged:** the TEMPORARY allow rules use the ANY prefix where every other
allow rule in the file uses the stricter RO whitelist (they were lifted verbatim from `ask`).
Low risk — section 14 still denies `-c`, `--config-env`, `--exec-path` — but worth tightening if
that block ever becomes permanent. Noted in the file.

---

## 7. The loop, per iteration

```
orchestrator frames the cycle: objective, expected size, what would falsify it
  |
  +- draft or revise the interface for the modules in scope        (conceptual first)
  +- optionally wargame it in a throwaway playground               (mandatory for R6)
  +- make ONE coherent change
  +- deterministic guard  -> fail: revert, record why
  +- invariants           -> fail: revert, record why
  +- verdict corpus       -> any changed verdict: revert, no exceptions
  +- safety inspector     -> flagged: stop, escalate
  +- predicate COMPONENTS + metrics as evidence, not exit criteria
  +- append to decision log; leave the tree in a resumable state
```

**A wargame that invalidates an interface draft is a success of the method.** Record and revise;
do not push through.

**No-progress limit:** three consecutive changes leaving the predicate false and moving no
diagnostic -> stop and escalate.

**Anti-gaming prohibitions, stated to every agent:** do not split or merge commits to influence
a measurement; do not split a module solely to reduce fan-in; do not delete or weaken a test; do
not introduce a pass-through module solely to break a cycle. If a predicate can only be satisfied
that way, **stop** — the predicate is wrong.

---

## 8. Two judges

The ticket requires the judge **not** be told what the step was meant to achieve — give a
reviewer the goal as a pass condition and you get a reviewer that confirms it was met. Arnon also
wants a judge holding the big picture and nudging the orchestrator. Both are right; one agent
cannot do both. (Arnon's clarification: "big picture" means the objectives and ideas driving the
refactoring **as a whole**, not a step-specific picture.)

**Blinded reviewer.** Sees before/after and nothing else — no goal, no predicate, no metrics, no
plan. One question: *is this easier to review, and why?* Its value comes entirely from its
ignorance.

**Architect judge.** Sees everything — ideal picture, as-is picture, plan, interface drafts,
wargames, decision log, predicate components, diff. Judges *direction and reasoning*, not just
result. Applies the what-vs-how test in S4. Can say "this landed, but for the wrong reason, and
the next step will suffer", nudge the orchestrator's framing, and propose plan changes.

**A step closes when both agree.** Blinded satisfied + architect unconvinced = locally tidy,
strategically wrong; keep going. The reverse = right in principle, not yet real; keep going.

**Iteration guard (explicit, not implied):** both judges receive *iterations since this step
opened*, as an explicit input to their recommendation. This is a different failure from the
no-progress limit: that fires when diagnostics stall, this fires on a step that is progressing
steadily and still running too long.

**Separate context windows are a feature** (Arnon): each judge has a focused task, so the
context-rot exposure of a long-running loop is lower than with one omniscient judge.

**On plan changes** (Arnon): the plan is not holy — no battle plan survives the first shot — but
changing it often is a symptom of bad planning and lack of focus. A plan change must be argued
in the decision log, not made silently.

---

## 9. Mechanism: what runs where

| work | mechanism | why |
|---|---|---|
| the refactoring itself | main session, prompted | sequential, stateful, one working tree. Parallelism is the failure mode, not the speedup |
| safety inspector | subagent, cheap model, every 1-2 iterations | fresh eyes, low cost |
| blinded reviewer | subagent, fresh every time | its value *is* its ignorance |
| architect judge | subagent, capable model, step boundaries | needs the full artifact set |
| canary | subagent, fresh every time, step boundaries | measures a newcomer's cost; reuse destroys it |
| step-boundary review | **workflow** | blinded reviewer + architect judge + canary in parallel, all read-only — the one place a workflow earns its keep |
| unattended continuation | **`/loop`**, after CP2 only | before CP2 Arnon gates every step anyway |

### Context degradation, and crashes

The main session degrades in cost and quality as context grows. Two defences: compaction, and a
deliberately maintained condensed state artifact (the RESUME note) rather than reliance on the
transcript.

**Arnon's addition:** the RESUME note also guards against a **crash midway**. Session resume
papers over interruption; it does not survive total context loss. So the note is also a test of
**"what is too little"** — the minimum that makes the work recoverable from nothing — which is a
different question from the size limit's "what is too much". Both bounds matter.

**Every iteration must end in a resumable state:** invariants green, tree not mid-change,
decision log written, RESUME note current at step boundaries.

---

## 10. Checkpoints and budget

**CP1 — after prerequisites. Hard stop regardless of budget.** Evidence: corpus mutation-test
results (must catch every seeded change), the fitness script's first full report with
components, the as-is/ideal/delta picture, the remaining guardrail rules, and a proposed final
step order. **If the corpus does not catch every seeded mutation, the programme does not start.**

**CP2 — after R3 closes.** The "is this loop working" assessment. R3 exercises the whole
machinery once — interface draft, change, invariants, corpus, guard, inspector, both judges,
canary — on a step now known to be small.

**Budget.** Arnon is on the max plan; there is no sound basis for a token estimate up front and
inventing one would create a false anchor. Real constraint is **session limits** (5-hour
windows, up to ~34/week; weekly limits at most once a week). Interruptions mid-thought cause
confusion and sometimes rework.

**Policy: slow down only on hard evidence.** Record every interruption in the decision log.
Arnon's point: the evidence tells us not only *whether* to pace but *how much* — measured
interruption frequency sizes the pause. Designing for cheap interruption (S9) comes first.

---

## 11. Open items for the CP1 review

1. Final step order, after the as-is picture.
2. R6 as its own ticket (deferred by decision).
3. Whether the config load/query split becomes a step.
4. Whether `tools/` (repo root) should be renamed to end the collision with `toolguard/tools/`.

---

## Clarifications from discussion

- 2026-08-03: *"Metrics are a guide, not an objective. The deciding factor is judgement."*
  The judge is the gate; predicates only scope.
- 2026-08-03: the orchestrator frames objective/size/effort per cycle; the judge decides
  stopping points **and** keeps everyone on task with the big picture in mind. Forced the
  two-judge split (S8).
- 2026-08-03: *"the plan itself is not holy... no battle plan survives the first shot of
  battle."* Changes are fair play but must be argued and recorded.
- 2026-08-03: risk of proceeding without TOO-28 accepted knowingly; mitigate with judge guidance
  and/or a separate safety inspector at low cost.
- 2026-08-03: no parallel agents ("that would hopelessly tangle up the yarn").
- 2026-08-04: the flow sketch is **not** directives or architecture — it illustrates how to
  frame a problem before committing to structure. Think about it independently and critically;
  the ideas are experienced but not infallible.
- 2026-08-04: layer design is about **maintainability and preventing concept leaks**, not
  aesthetics; a layer interface is a public API — stable, backward-compatible, *what* not *how*
  (S4).
- 2026-08-04: "phases" are an internal implementation artifact, not a documented concept; do not
  formalise them into rule semantics (S2).
- 2026-08-04: git relaxation is contained to the branch, so leakage is not the risk; stash was
  denied for silent desync and redundancy instead.
- 2026-08-04: corpus privacy is a non-issue — logs are not on GitHub; sanitise anything
  committed; ephemeral corpora carry no meaningful risk.

## Relations

- relates_to [[TOO-19 Structured Rule Entries - Rule-Match Enrichment]]
