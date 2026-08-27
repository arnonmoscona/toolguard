---
title: deletion-triage
type: note
permalink: toolguard/durable/intermediate/deletion-triage
tags:
- TOO-45
- durable
---

# Deletion triage of `toolguard-memories/`

**Proposal, not an action. Nothing was deleted, moved, or edited by this triage.** Measured 2026-08-23 against 733 files / 8.81 MB (`du` reports 11 MB because of block rounding; the byte total is 8.81 MB).

**Read in depth: 31 files.** Classified by pattern from filename, directory, size, date, first headings and targeted greps: the remaining 702. Every category verdict below was set after reading at least two members of that category end to end or in substantial part.

## Headline

| | files | MB |
|---|---|---|
| proposed DELETE | **323** | **2.65** |
| KEEP | 411 | 6.20 |

The MB saving is small because the delete pile is made of many small files while the keep pile contains the few very large ones (`follow-up-queue.md` alone is 0.80 MB, `reports/img/` is 1.67 MB). **The value of the deletion is the file count, not the disk** — 323 fewer notes in the basic-memory index and in every future search result.

## One structural fact that changes how the deletion should be done

**`toolguard-memories/` IS the basic-memory `toolguard` project store** (`~/.basic-memory/config.json` maps project `toolguard` to this exact path). 675 of the 733 files carry basic-memory frontmatter with a `permalink`. Deleting with `rm` leaves the SQLite index (`~/.basic-memory/memory.db`) holding entries for files that no longer exist until a sync reconciles them. Either delete through `mcp__basic-memory__delete_note`, or `rm` and then force a re-sync. Worth deciding before the first file goes.

---

## Category verdicts

### DELETE

**`*coder task recall*` — 133 files, 0.64 MB. DELETE (minus 0 rescues; see below).**
Read in full: 3 (tickets 108, 99, and the F1 depth guard). These are an implementer's pre-flight notes to itself: scope restatement, files it intends to touch, gates it intends to run, concurrency warnings about other agents editing the same file. They are written *before* the work and are superseded by the work. Where they contain real analysis — ticket 108's argument about why the required-field check must move with the function — the same argument appears in the implementation report, in the shipped docstring, and in the commit. Their one genuinely unique content class is **transient coordination** ("do not touch `compound.py`, two other agents are editing it live"), which has no value after the fact.

**`*implementation report*` / `*coder report*` / `*fix report*` — 143 files, ~1.42 MB. DELETE, minus 4 rescues listed below.**
Read in full or near-full: 6. **The decisive check was the commit messages.** This project's TOO-45 commits are unusually long and carry the measurements verbatim — commit `63644a7` records "the `comment` rule fired ZERO times"; `2ca11b2` records the 17-shape byte-identical verification with pinned `PYTHONPATH`; `ef37418` records the 9 measured field occurrences of `{}`. The reports' conclusions are in the commits. What the reports carry that commits do not is *process* detail — gate output, before/after counts, declined non-blocking review findings — and that is spent once the code is merged.

**Blinded review rounds `TOO-45/reports/review-NN-roundN.md` — 27 files, 0.40 MB. DELETE.**
These are the reviewer's findings; each has a paired repair report saying what was fixed and what was declined. Both halves are inputs to code that is now committed. The declines are the only residue, and they are handled by the rescue list.

**Superseded state / resume / queue snapshots — 12 files. DELETE all but the newest of each chain.**
Deleting: `TOO-45 RESUME HERE.md` (08-08), `TOO-45 session resume.md` (08-10), `TOO-45 campaign resume 2026-08-13.md`, `TOO-45 status 2026-08-14 - phase 2.md`, `TOO-45-punch-list-2026-08-20.md`, `TOO-45-retriage-2026-08-20.md`, `TOO-45 phase 2 shared brief.md`, `TOO-45 punch-list 07 doc comments - coder state for recovery.md`, `TOO-19 RESUME HERE - state after Phase 0 commit.md`, `phase-2-baseline-reds.txt`, `commit-message-03.txt`.
Keeping: **`TOO-45 phase 3 resume.md`** (08-22, and its own internal sections are marked "SUPERSEDES all sections above" — it is self-consolidating) and **`TOO-45 punch-list 2026-08-22.md`** (newest, "approved by Arnon").

**Superseded rolling-pointer files — 7 files. DELETE.**
`implementation/coder-latest-{implementation-report,task-recall}.md` (TOO-8, June), `implementation/TOO-45 coder-latest-{implementation-report,task-recall}.md` (08-19), `implementation/latest-code-review-report.md.md` (TOO-8), `TOO-15/latest-code-review-report.md`, `implementation/TOO-15 Project Root Consolidation RED State.md`. Each is a stale copy of a named file that also exists, or the state of a task that finished.

**TOO-19 per-increment reports — 44 of 60 files. DELETE.**
TOO-19 is closed and pushed. `Phase 0a increment 1/2/4/5/6/8`, `Phase 0b increments 1-2/3-4/5-6`, the review-fix reports, and the matching task recalls are increment-level bookkeeping for shipped code.

**`TOO-30` (3 report files) and `TOO-16` (1) — DELETE.** Both tickets closed; the reports are per-phase RED/GREEN bookkeeping.

### KEEP

**`TOO-45/reports/surprise/` — 110 files, 0.73 MB. KEEP, all of it.**
This is the strongest keep in the tree and the one most at risk of looking like clutter. `RESULTS-LOG.md` states the retention requirement explicitly: the experiment's planned analysis is **ablation** — partition the scored set, derive a candidate scoring rule on subset A, test on subset B — and *"ablation can only re-score under rules that do not exist yet."* That requires the per-ticket **primitives**: predicted set with confidences, actual set with per-file line counts, each surprise with its individually assigned cause, leak status per file. `CONSOLIDATED-REPORT.md` carries derived recall figures; **derived numbers cannot be un-derived.** Deleting the per-ticket `NN-prereg.md` / `NN-scored.md` pairs would end the experiment, not archive it. The experiment is also still running: `108-prereg.md` is dated 2026-08-23 and unscored.

**`TOO-45/proposed-tickets/` (78) + `resolved/` (31) — 109 files, 0.59 MB. KEEP.**
`00-INDEX.md` reconciles ticket status against `git log` and states that individual status lines are stale *in the misleading direction*. It lists a substantial open set (02, 06, 07, 08, 09, 12, 13, 21, and 17-22 partially fixed). Tickets 106, 107, 108 are dated 2026-08-23. `resolved/` is a deliberate archive whose files are cross-referenced from `00-INDEX.md`.

**`TOO-45/reports/follow-up-queue.md` — 0.80 MB, one file. KEEP.**
Over 60 sections of *"code-level defects found during #07 — flagged, deliberately NOT fixed there"*, per module. This is the largest single register of known-unfixed defects in the project. It is cited from four other memories files.

**`TOO-45/DECISIONS-PENDING.md` (80 KB) — KEEP.** "Decisions waiting on Arnon", and cited from `docs/architecture-as-built.md`.

**`TOO-45/measurements/` — 10 files. KEEP.** Its `README.md` states the directory exists to hold coordinator measurements *out of* ticket files to preserve estimator blinding, and names the five tickets already contaminated by the other arrangement. Deleting it would either lose the measurements or push them back into the ticket files and re-break the blinding.

**Campaign-level analysis in `TOO-45/reports/` — ~40 files. KEEP.** `retrospective.md`, `transferable-practices{,-evidence}.md`, `architecture-sweep-{evidence,practices}.md`, `surprise-factor-protocol.md`, `replay-instrument-blind-spot.md`, `corrections-{analysis,corpus}.md`, `canary-*`, `change-challenges.md`, `micro-*`, `r6-reassessment.md`, `end-state-summary.md`, the `98-*`/`99-*`/`103-*` design plans, `pyscn-2026-08-22-disposition.md`. These are the source material the DURABLE extraction is drawing on; **do not delete any of them until the four extraction agents have finished and their output has been reviewed.**

**`TOO-45/reports/img/` — 46 files, 1.67 MB. KEEP.** No overlap with `docs/diagrams/` (checked by basename: zero common files), so these are the only copies, and they are referenced from the reports that are being kept. This is the largest single block of disk in the tree; if disk mattered it would be the place to look, but it does not.

**`TOO-45/{decision log, lessons, ideal picture, delta, architecture overhaul execution plan, comment standard, test-repair plan, punch-list 07 work queue, punch-list 09 plan, ruff configuration proposal, ticket-status-audit-2026-08-19, transcript-evidence-34-36-67}.md` — KEEP.** Campaign-level, cross-referenced, several still open.

**`methodology/` (2), `tooling/` (1), `notes/` (2), `task summaries/` (3) + `task-summaries/` (1) — KEEP.** `notes/Current Task Context.md` is live per the global CLAUDE.md. Task summaries are mandated by CLAUDE.md. Note the two summary directories differ only by a space/hyphen — worth merging, not deleting.

**`TOO-15` (7 of 9), `TOO-17` (2), `TOO-8` (2), `TOO-14` (1) — KEEP.** These are requirements/design documents for shipped features, not per-task bookkeeping, and they are small.

**`TOO-19` design documents (16 of 60) — KEEP.** In particular `Intent-disclosure phrasing experiment - winning wording and results.md`, which **the global `~/.claude/CLAUDE.md` cites by name** as the evidence for the disclosure rule's wording. Also `Safe Experimentation Mechanism - Design Proposal.md` (41 KB, a design never built) and `Deferred - parser comment preservation for intent disclosure.md`.

### UNCERTAIN

**`TOO-45/spikes/` — 13 files, 0.16 MB.** Spike C won and `docs/heredoc-parsing-design.md` carries the rejected-alternatives rationale, which is the part the `98-implementation-plan.md` says matters (*"without them the next reader re-proposes spike B"*). So the prototypes are logically superseded. **But that doc says the spikes were "not committed — `tmp/` is gitignored", which is wrong: these are the only surviving copies.** Two options, both defensible: delete them and fix that sentence in the doc, or keep 0.16 MB. I lean keep-and-fix-the-doc, because the doc sentence is a factual error either way.

**The 9 files carrying per-task cost/elapsed tables.** These are the only quantitative record of what agent work cost, and the tables are per-phase (`| Phase | Elapsed | Est. cost |`). Nothing aggregates them. If anyone ever wants "what did TOO-45 cost", it has to come from here. **Extract the 9 tables into one row-per-task table before deleting these files**; that is a ten-minute job and the data is unrecoverable afterwards. The files: `TOO-19/TOO-19 Phase 0a increment 1 - implementation report.md`, `TOO-19/TOO-19 Phase 0a increment 4 implementation report.md`, `TOO-45/TOO-45 tickets 42 and 47 - coder implementation report.md`, `TOO-45/reports/TOO-44 ambient prose repair pass 2 - coder implementation report.md`, `TOO-45/reports/TOO-45 review-80 round1 prose repair - implementation report.md`, `implementation/TOO-45 R3 review-fix implementation report.md`, `implementation/TOO-45 R3 second review-fix implementation report.md`, `implementation/TOO-45 ticket 20a repair round - coder implementation report.md`, `implementation/TOO-45 ticket 44 broken isolation seam - coder implementation report.md`.

**`latest-code-review-report.md` at the memories root** (08-09, TOO-45 punch-list 03). CLAUDE.md's code-review workflow opens a file by this name after every review, so this is a live pointer whose *content* is stale. Keep the path, expect it to be overwritten.

---

## Rescued from the delete pile

Six files that match a DELETE pattern and must not be deleted. **Four are genuine unique content; two are location bugs.**

### 1. `implementation/TOO-45 ticket 20a repair round - coder implementation report.md`

**Section: "Suspicious injected instructions (NOT acted on) — flag for Arnon".** An implementer recorded three mid-session `system-reminder` blocks it judged illegitimate, including one that falsely attributed the agent's own `cp` restore to "the user or a linter" **and instructed the agent not to tell the user**. The agent refused and disclosed. This is a record of a harness behaviour that instructs concealment, written down at the moment it happened. It is not in any commit, ticket, or report — I grepped the whole repo. **This is the single most valuable thing in the delete pile.**

### 2. `implementation/TOO-45 F1 dollar-paren depth guard - coder implementation report.md`

**Section: "Out-of-band messages flagged (not adopted)".** The *second independent observation* of the same concealment-instruction reminder, by a different agent on a different task. One instance is an anecdote; two is a pattern, and the second one is what makes the first credible. Its paired task recall carries a shorter version.

Items 1 and 2 together are a finding in their own right and should be written up in `DURABLE/` before either file is deleted. Note the third leg: the "Auto Mode Active" reminder that instructs preferring raw Bash over Read/Edit/Write was flagged by both agents as conflicting with their system prompts — and the same reminder was active during this triage.

### 3. `TOO-45/reports/TOO-45 review-18-round3 repair - coder implementation report.md`

**Section: "Not done / deferred"** — two items flagged for Arnon and, as far as I can tell, never filed: N8's "reject or warn at load time" (documented instead of enforced, explicitly marked "candidate follow-up ticket if Arnon wants it enforced") and N6's fix to the live `.claude/toolguard_hook.toml`, skipped as out of file scope. **Plus a full release-note draft for the 0.5.1 `hard_deny` / `:*` fidelity fix**, including the user-facing warning that a `curl http://localhost:*` carve-out now spans arguments. `docs/native-pattern-reference.md` carries the reference rows but I did not find this draft's warning text elsewhere.

### 4. `implementation/TOO-45 ticket 44 broken isolation seam - coder implementation report.md`

**Section: "Recommended, deliberately not done"** — a named, concrete re-drift guard for the repaired fixture, with the reason the obvious shape does not work here (the fixture's home *raises*, so no crash report lands anywhere to assert on) and the workable alternative (assert stderr carries `log_crash`'s own warning). A later `TOO-44 follow-up - re-drift guard` note exists, so this may be closed — **verify before deleting.** The same file also holds a `~/.toolguard/errors/` census (1768 files, 133 predating the session, 806 on 2026-08-12 alone) that appears nowhere else and that a later note treats as a baseline.

### 5 and 6. The two files in `toolguard-memories/toolguard-memories/`

`toolguard-memories/toolguard-memories/` is a **path bug** — an agent wrote a repo-relative path while already inside the memories directory. It holds 4 files: ticket 104's recall and report, and the `error_reporter.py` comment-rewrite recall and report. The two reports are the only copies of their content. **Fix the location before applying any rule to them**, then treat them as ordinary implementation reports. Do not delete the directory blind.

## Things that belong in the repo proper, not in memories

- **`TOO-45/tools/build_estimator_briefing.py`** — a working script whose own docstring says *"Lives here rather than in the session scratchpad because it has been destroyed three times by scratchpad cleanup."* It hardcodes `/home/arnon/projects/toolguard`. If the surprise experiment continues, this belongs in `tools/`, where it is version-controlled and where cleanup cannot reach it. **It is at risk from exactly this deletion pass.**
- **`TOO-45/reports/img/`** — 46 diagrams with no overlap with `docs/diagrams/`. If any are still current, they belong under `docs/diagrams/`; if none are, they are history and can stay in memories.
- **`methodology/in-process-mutation-testing.md`** and **`methodology/verifying-claims-finds-bugs.md`** — both read as project methodology rather than task memory. Candidates for `docs/` or `.claude/rules/`.

## Referenced files — deleting these breaks a documented pointer

All six are already in the KEEP set; listed so a later widening of the delete rules does not catch them.

| file | cited from |
|---|---|
| `TOO-45/DECISIONS-PENDING.md` | `docs/architecture-as-built.md` |
| `TOO-45/proposed-tickets/00-INDEX.md` | `docs/architecture-as-built.md` |
| `TOO-45/proposed-tickets/85-consolidate-the-external-contract-into-one-module.md` | `docs/architecture-as-built.md` |
| `TOO-45/reports/98-scanner-count-measured.md` | `docs/heredoc-parsing-design.md` |
| `TOO-45/reports/dependencies-before-after.md` | `docs/architecture-as-built.md` |
| `TOO-45/reports/end-state-summary.md` | `docs/architecture-as-built.md` |
| `TOO-19/Intent-disclosure phrasing experiment - winning wording and results.md` | `~/.claude/CLAUDE.md`, by note title |

Within the tree, the most-cited targets are `phase-2-baseline-reds.txt` (17 citations, and it is in the DELETE set — the citations are from files also being deleted, but check), `follow-up-queue.md` (4), `[[TOO-45 decision log]]` (7), `[[surprise-factor-protocol]]` (8). All except `phase-2-baseline-reds.txt` are kept.

## The deletion rules, as rules

Applied in order; the rescue list wins over everything.

1. Any file whose name matches `*task recall*` or `*Task Recall*`.
2. Any file whose name matches `*implementation report*`, `*Implementation Report*`, `*coder report*`, `*fix report*`, `*documentation report*`.
3. `TOO-45/reports/review-[0-9]*-round[0-9]*.md`, plus `review-77-grammar-phase1.md`, `review-77-grammar-phase1-delta.md`, `review-44-redrift-guard.md`, `review-74-round1-repair.md`.
4. The 12 superseded state/resume/queue files and the 7 rolling-pointer files, both enumerated in their sections above.
5. `implementation/TOO-15 P0 Keystone Implementation Task.md`, `TOO-45/lessons.md` (3.7 KB, wholly contained in the 21 KB `TOO-45 lessons.md`).

**Minus the 6 rescued files.** Result: 323 files, 2.65 MB.

To regenerate the exact list without deleting anything, the rules above are mechanical; run them as a `find`/`grep` producing a file list, review it, and only then delete. **Do not pipe the rules straight into `rm`.**

## What I am unsure about

- **Whether the four extraction agents still need the delete pile.** They are reading now. Several are almost certainly reading implementation reports for measurements. **Do not execute this deletion until they are done and their output is reviewed** — that is the one sequencing risk that could lose something.
- **How thoroughly the 143 implementation reports were sampled for unique content.** I read 6 in full and grepped all 143 for eleven markers of unactioned content (`declined`, `deferred`, `not fixed`, `flagged for Arnon`, `worth flagging`, `out-of-band`, `recommended, deliberately not done`, and similar). 77 files matched at least one marker; I opened the 11 whose *heading* matched, which is where the substantive residue was. **A marker-negative file could still hold a unique measurement in prose.** If that risk is unacceptable, the cheap mitigation is to keep the category and delete only the task recalls (133 files) — the recalls are the category I am confident about.
- **TOO-19's 44 deletions.** The ticket is closed and pushed, so I applied the rule; but I read only 1 TOO-19 file in depth and classified 59 by pattern. It is the weakest-evidence block in the proposal.
- **Whether `no rescue is needed from the surprise directory's superseded prereg files`** — `105-prereg.md` and `105-rescoped-prereg.md` coexist, as do `105-phase1-scored.md` / `105-phase2-*`. Under the ablation argument the superseded ones are still primitives and I kept them all.
