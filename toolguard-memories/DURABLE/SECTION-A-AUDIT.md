---
title: Section A audit — coder task recalls, pre-deletion safety check
type: note
tags:
- TOO-45
- durable
permalink: toolguard/durable/section-a-audit
---

# Section A audit — "Coder task recalls", untracked subset

**Read-only audit. Nothing was deleted, moved, or modified. This file is the only write.**

## Scope, verified independently

Section A of `PROPOSED-DELETE-LIST.md` was re-parsed from the file and each path compared against `git ls-files toolguard-memories/` (222 tracked paths at time of audit). **Measured: 129 files in section A, 44 git-tracked, 85 untracked, 0 missing from disk.** This matches the brief's figure of 85. Total size of the 85: **411,689 bytes**.

Section B files were not opened.

## Verdict

**80 of the 85 untracked files are safe to delete. 3 to rescue. 2 uncertain, both low-value.**

Method: all 85 were screened by regex twice (a deliberately loose pass flagging 82, then a high-precision pass flagging 27), plus a third pass over section headings that indicate original coder observation rather than brief restatement. **31 files were deep-read.** The third pass mattered — it surfaced one file the precision screen had marked clean (see UNCERTAIN U1), which is the honest measure of the screen's recall.

---

# RESCUE — 3 files

## R1. `TOO-45/TOO-45 governed_tools default change - coder task recall.md` (7,858 bytes)

**What is lost:** the only surviving statement of Arnon's rationale for the governed-tools default change.

> Arnon: "it actually is better that the default governed list would be {Bash, Read, Write, Edit}. I think Bash only is a forgotten remnant."

**Where I checked.** `grep -rn "forgotten remnant"` across the whole repo excluding `.git` → **one hit, this file.** `grep -rn -i "governed_tools|governed tools" toolguard-memories/DURABLE/` → two hits, both incidental (a delete-list line naming this very file, and an unrelated `config_validation.py:59` finding in `SECTION-C-AUDIT.md`); **neither carries the rationale.** `TOO-45/TOO-45 decision log.md` (KEPT) mentions `governed_tools` only in a fixture-bug anecdote at line 294 and does not record this decision. No file under `TOO-45/proposed-tickets/` covers it — this was a direct Arnon decision that never became a ticket. The *change* is in code and in `docs/install.md` / `docs/takeover-mode.md`; the *reason* exists nowhere but here.

The file also carries the analysis that the golden corpus splits into an in-process half unaffected by `governed_tools()` and a ~30-case e2e half that is, with the instruction that every changed e2e golden be individually justified rather than bulk-regenerated. That reasoning is not obviously elsewhere either, though I did not chase it to a conclusion.

## R2. `implementation/TOO-45 punch-list 04 error reporter — Reporter class refactor — coder task recall.md` (10,588 bytes)

**What is lost:** a 130-word verbatim Arnon design objection, under a heading that says `## Arnon's objection, verbatim`. It is the most reusable piece of design philosophy I found in the whole 85, and it is general — it is about globals and singletons, not about this repo.

> "I don't like keeping changing state in private globals. It's not wrong per-se, but it smells. It is definitely less testable and when there are multiple state variables like this - it's even more smelly. What it really is: an undeclared singleton pattern or an undeclared global service pattern. If that is what you mean - then don't hide it. Make it explicit. But since you have absolutely no callers at the time of writing this and you would likely only have hook.py as a caller by the time you finish, then even a singleton is not yet justified. Instantiate an object at the start of hook.py, thread it inside hook.py and you don't even have a singleton but a regular class. Note that singletons are frowned upon in many quarters. I am not religious about it, but singletons do produce problems, so better avoid them unless they cause extra function parameters everywhere."

**Where I checked.** `grep -rl "I don't like keeping changing state in private globals"` and `grep -rl "singletons are frowned upon"` across the repo excluding `.git` → **one hit each, this file.** In `DURABLE/` I grepped for `singleton`, `private global`, `undeclared global service`, `threading state`, `invocation-scoped`, `Reporter class` across `*.md` and `intermediate/*.md`: `singleton`, `private global` and `undeclared global service` return **zero files**; `Reporter class` appears only as a filename in `PROPOSED-DELETE-LIST.md`. The quote is not represented in any summary.

The file also records the constraint that *defeats* the naive reading of the objection — the fault buffer needs no global at all, but the resolved log directory is read at 8 sites across 4 config-layer modules, so threading it would change `get_env_config()`'s signature repo-wide, which is the "extra function parameters everywhere" case Arnon's own wording carves out. That pairing (principle plus the measured exception the principle itself anticipates) is what makes it worth keeping.

## R3. `implementation/TOO-45 punch-list 04 error reporter follow-up - coder task recall.md` (6,137 bytes)

**What is lost:**

> His words: "fold it before commit, and there is no rational reason to keep a known defect."

**Where I checked.** `grep -rl "fold it before commit"` → 2 files: this recall **and** `implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md`. `grep -rl "no rational reason to keep a known defect"` → **1 file, this recall.** So the report holds the instruction but not the principle. **And the report is itself proposed for deletion** — `PROPOSED-DELETE-LIST.md:400`, section B, 60,500 bytes. If section B deletes it, both halves go.

The file also carries the clearest statement in the 85 of the `main()` fail-open mechanism: the three `except` handlers built a correct deny verdict, printed it to **stderr**, and `sys.exit(0)` — so Claude, which reads stdout only, saw empty stdout plus exit 0, read it as "no opinion", and fell through to native permission handling. *"Catch-all exists to fail closed on anything unforeseen and instead fails open."* This is the campaign's signature failure mode stated in one sentence about a specific shipped defect. `grep -rn -i` for it in `DURABLE/` finds nothing.

**Rescue R3 unconditionally, or make it conditional on section B keeping the paired report.** I recommend unconditional: R3 is 6 KB.

---

# SAFE — 80 files, and the patterns that make them safe

Task recalls in this campaign are a brief restatement written *before* the work: assignment, scope fences, forbidden files (concurrency), baseline test counts, gate commands, and a report destination. The post-work record lives in the paired implementation report. That structure holds across the 80.

| pattern | count | why safe |
|---|---|---|
| Pure brief restatement + gates, no original observation | ~52 | The brief is gone either way; the outcome is in the paired report and, for every case I chased, in the code |
| "Clarifications from discussion: none / task arrived fully specified" | 9 | Explicitly empty by the agent's own account (`Item 95`, `review-44 round5`, `ticket 78 follow-up`, `ticket 78 tilde variant`, `Item 97 step 3`, `ticket 85 chunk C`, `spike B`, `review-18-round4`, `review-44 round4`) |
| Design decision recorded that then landed in code | ~11 | Verified in the tree, see below |
| Out-of-band "Auto Mode Active" record | 7 of the 8 | Each is quoted with file, date and line number in `DURABLE/03-out-of-band-instruction-records.md` |

**Out-of-band records — checked file by file, not by pattern.** Eight of the 85 record an injected instruction. `DURABLE/03` cites seven of them **by exact path with line numbers and verbatim quotes**: `punch-list 39 round 3` (03:188), `punch-list 39 round 4` (03:200), `review-18-round5 repair` (03:151), `review-74 round1 blocking fixes` (03:169), `ticket 79 command substitution ASK floor` (03:210), `F1 dollar-paren depth guard` (03:229), `ticket 70 punch-list item` (03:237). The eighth, `review-39-round1 repair`, is **not** an injection at all — it records a legitimate *coordinator* mid-task correction, which is the brief, not an out-of-band channel. All eight are safe. Note that 03 itself flags `TOO-45 repair round - review-18-round3 fixes - coder task recall.md` (also in these 85) as a secondary account that *"should not be deleted before this file is checked against them"* — 03 quotes it, so that condition is satisfied.

**Design decisions verified as landed in code**, so the recall adds nothing the tree does not carry:

- `ticket 44 ambient facts` — the `AmbientFacts` / `active()` / one-door design is `toolguard/ambient.py`. Its deliberate exception (`tools/decision_ledger.USER_LEDGER_PATH` import-time `Path.home()`) is closed: `decision_ledger.py:249` now reads `ambient.home()`.
- `ticket 80 ambient routes` — its unasked-for measurement (*"`resolve()`/`absolute()` call `os.getcwd()` ONLY for a relative receiver … The brief does not say this"*) is in the tree twice, at `tools/architecture_fitness.py:3893` and `:4326`. Its deferred item (*"`expanduser` move is blocked … reporting as a decision for Arnon"*) is closed: `toolguard/path_utils.py:39`.
- `ticket 81` — "Gap B still open re: receiver-relative" is closed: `test/unit/_relative_receiver_resolve_guard.py` exists and is asserted by `test/unit/test_zz_real_log_dir_guard.py:546`.
- `punch-list #01 suppression store (pass 4)` — the SQLite path-interpolation defect (a raw `?` truncates the filename and silently drops `mode=rw`; a `%` is mis-decoded) is fixed in `toolguard/once_per_store.py:265` via `Path.as_uri()`, and the reasoning survives in that function's docstring at `:253-257`.
- `phase 2 prefix-match boundary` — "the 10 'second unrelated path' subtests are NOT fixed by either … This is a separate decision" is resolved. I ran `test.unit.test_tools_uninstall_readiness.TestUninstallReadinessOverGrant`: 3 tests, OK.
- `phase 2 unit 1 follow-up` — the coder's stop-and-report on a "fifth location" is recorded in its paired report at line 183, and the pin itself is now `["[regex]^git (diff|log|status)(?=\\s|$)"]` in `test/unit/test_tools_maintenance.py`, so the decision was taken.
- `ticket 22` — its explicitly-unfiled carve-out (*"a corpus finding also names the covering rule as redundant … needs its own ticket"*) is written into `TOO-45/proposed-tickets/22-…md:27`, which is **not** in any delete-list section.
- `ticket 105` — Arnon's question (*"why do we need it in the first place?"*) is duplicated verbatim at `TOO-45/proposed-tickets/105-…md:9` and `:72`, both surviving.
- `ticket 108` — "Arnon's request (verbatim)" is duplicated in `TOO-45/proposed-tickets/108-…md` and in `DURABLE/intermediate/{open-questions,VERIFIED-open-questions}.md`.
- `ticket 38` — Arnon's *"no prose-parsing should be present in the code base. Should be fixed."* also appears in `TOO-45/TOO-45-punch-list-2026-08-20.md`, which is **rescue R7** and therefore survives.
- `ticket 100` / `ticket 104` — the only Arnon content is the single word `"fix"`.

**One measured null worth recording: there is no cost data in section A at all.** I grepped all 85 for `$N`, token counts, `token budget`, `N minutes` / `N hours`, `elapsed`, `wall clock` and `context window`: **zero hits, across all 85 files.** This is structural rather than lucky — a task recall is written before the work, so it cannot contain the work's cost. `DURABLE/02-campaign-cost-data.md` loses nothing to this deletion.

---

# UNCERTAIN — 2 files

## U1. `implementation/TOO-45 review-18-round4 repair - coder task recall.md` (2,625 bytes) — safe *iff* section B keeps one file

This file was marked **clean by both regex screens** and was caught only by the section-heading pass. It records a real, self-reported data-loss incident:

> "a self-reported mistake: a wildcard `rm *.py` in the shared session scratchpad deleted prior-round evidence files (`probe_counterexample.py`, `probe_guidance.py`, `probe_old_vs_new.py`, `scan_rules.py`) cited by review-18-round4.md. Unrecoverable"

**Where I checked.** The paired report `TOO-45/reports/TOO-45 review-18-round4 repair - coder implementation report.md:17-35` carries the incident **in far more detail** than the recall — including the confirmation `find`, the mitigating factors, and the recommendation (*"`ls` the scratchpad before any wildcard delete there"*). So the recall is a pointer and the report is the content. **But that report is in section B.** `grep -rn -i "scratchpad.*delet|delet.*scratchpad|destroyed evidence" DURABLE/` returns one adjacent-but-different record (`intermediate/deletion-triage.md:121`, about `build_estimator_briefing.py` being *"destroyed three times by scratchpad cleanup"*) — the same hazard, a different incident.

**Recommendation: delete U1, and tell the section-B auditor that this specific report carries a shared-scratchpad destruction incident that exists nowhere in `DURABLE/`.** If section B is going to delete it, the incident belongs in `DURABLE/01` first — it is a clean instance of an agent destroying another agent's evidence in shared state, which is a failure mode `01` does not currently name.

## U2. Two files holding a unique but thin Arnon approval

- `TOO-45/TOO-45 punch-list 94 validation_issues split - coder task recall.md` — *"definitely fix. Easy... Decomposition into multiple smaller functions is trivial."* `grep -rl "Decomposition into multiple smaller functions is trivial"` → **1 hit, this file.**
- `implementation/TOO-45 proposed ticket 96 - coder task recall.md` — *"not urgent but might as well fix now - as described"*. `grep -rl "not urgent but might as well fix now"` → **1 hit, this file.**

Both are genuinely unique quotations from Arnon and both are, in substance, approvals with no rationale attached — closer to `"fix"` than to R1 or R2. I am calling them uncertain rather than safe because the rescue criterion as written is "a verbatim quotation from the user", which they satisfy on the letter and arguably not on the spirit. **My recommendation is delete; the cost of being wrong is two sentences of approval language, and the cost of the alternative is diluting the rescue list.** Total 6.3 KB if Arnon prefers to keep them.

---

# Ticket candidates

**None from section A.** Every unresolved item I found had been resolved, and I verified each against the tree rather than against a later document: the `expanduser` move, ticket 81's Gap B, the prefix-match "separate decision", the suppression-store `as_uri` defect, the fifth-location pin, and ticket 22's carve-out. That is a real finding in itself — the "still open" language in these recalls is almost entirely *brief-time* state that the work then closed, which is the strongest argument the corpus offers for treating recalls as disposable.

**One process observation, not a ticket.** `DURABLE/03` counts the "Auto Mode Active" system-reminder across **25 distinct agents and 25 distinct tasks in TOO-45, with 24 refusals and 1 compliance**. That reminder is **present in this audit session's own context right now**, instructing me to prefer raw Bash over the dedicated Read/Edit/Write tools. The phenomenon `03` documents is ongoing rather than historical, and `03` is written in the past tense throughout. Worth a one-line note at the top of `03` saying so, since a reader in six months will otherwise read it as a closed episode.

---

# What this audit did not do

I did not verify the 44 **tracked** section A files — they are recoverable from git by construction and the brief scoped them out. I did not open section B. Where a recall's content depends on its paired implementation report surviving, I said so explicitly rather than assuming; that dependency affects R3 and U1 and is the only interaction between this audit and section B's.