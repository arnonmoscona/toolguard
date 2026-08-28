---
title: Recommendations punch list 2026-08-27
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/recommendations-punch-list
---

# Punch list — 2026-08-27 deliverables

**Every item spelled out inline. Do not replace an item with a pointer to another file.**

Source: Arnon's accumulated reading comments, 2026-08-27. He is away; anti-stall cron every 27 min; check `~/bin/claude-usage` each tick and pause if the 5-hour window is nearly spent.

| # | item | state |
|---|---|---|
| 1 | **Fix `12` Part C, C10** — Arnon: *"you have NOT demonstrated a reliable ability to prevent stalling without a cron reminder."* The rejection is wrong; cron was re-adopted after stalls, even with a punch list open | DONE |
| 2 | **Write `15-conclusions-register.md`** — every conclusion classified on his six axes (project-specific/general; process/tooling/metrics; autonomous/HITL; bugs/features/architecture; transferability; value) plus the agent strengths/weaknesses table with mitigations | DONE |
| 3 | **Write `16-where-to-apply.md`** — the seven asks: user CLAUDE.md, project CLAUDE.md, new skills/plugins + supporting scripts, existing user skills, existing user subagents, new general tooling, and Arnon's own process split HITL vs autonomous | DONE |
| 4 | **Documentation review** — `/documentation-review`, with close attention to `docs/architecture-as-built.md` and its diagrams: correctness first, then value and clarity. Unchanged diagrams are a reason to look deeper, NOT a defect | DONE — findings in tmp/doc-review-2026-08-27.md, awaiting per-item direction |
| 5 | **Cleanup pass** after the doc review | BLOCKED — needs per-finding direction (fix/defer/ignore) |

**Constraints that apply to items 2-3:**

- **No absolute paths.** The analysis set is being copied to a new git repo; cross-references between documents must survive, absolute paths will not.
- **Recommend, do not apply.** Arnon: *"I do not want to apply any of the conclusions immediately to any existing guidance documents."* Items 2 and 3 are proposals; nothing is edited into `CLAUDE.md`, skills, or agent definitions.
- **Assume new artifacts are user-level** and will live in a separate git repo for development and versioning.

**Deferred, not in this batch** (recorded so they are not lost):

- Partition `01` and `04` by project-specific vs user-level.
- Re-derive the delete list against the FINAL analysis set — cleared to proceed now that the set is at a good point and the backup is verified (765/765, 2026-08-27).
- Move the surprise-factor experiment (method, memory, criteria, statistics, fact records, guidance) to user level — it applies to any agent-assisted project.
- Move `tools/architecture_fitness.py` out to a separate AI-tooling repository.
- TOO-69: package/module docstrings stating purpose and reasoning, to raise architectural conformance.
- Trim tests that pin implementation decisions rather than required behaviour; tell-tale is tests of private functions.
## Added 2026-08-27 (anti-stall tick — item 5 blocked, took cleared work instead)

| # | item | state |
|---|---|---|
| 6 | **Re-derive the delete list against the FINAL analysis set** — Arnon cleared this: *"the analysis document set is now at a good point and this means that it clears the way to reassessing the delete list."* Result appended to `DURABLE/PROPOSED-DELETE-LIST.md` as ADDENDUM 2026-08-27 | DONE |

**Item 5 remains blocked** and correctly so: `/documentation-review` mandates per-finding direction (fix/defer/ignore) before any doc is edited, and Arnon is away. Findings are in `tmp/doc-review-2026-08-27.md`.

| # | item | state |
|---|---|---|
| 7 | **Portability audit of the analysis set** before the copy to the new repo — absolute paths, home paths, and whether internal cross-references survive. Result in `DURABLE/README.md` under PORTABILITY | DONE |

**Finding worth carrying**: zero markdown links point outside `DURABLE/`, so the copy needs no rewriting — and the absolute paths must **not** be stripped mechanically, because 6 of the 10 are quoted security evidence where the literal path is the finding.

| # | item | state |
|---|---|---|
| 8 | **Advance the deletion preconditions** — investigate the stray `toolguard-memories/toolguard-memories/` nest and confirm the five basic-memory-linked files | DONE |

**Material correction found.** The delete list described the nest as *"holding a 1 KB stale pointer"*. It actually holds **4 files, ~28 KB, two of which exist nowhere else** — ticket 104's coder task recall and implementation report. All four untracked. Corrected in `DURABLE/PROPOSED-DELETE-LIST.md` §3. Recommendation unchanged (both fall in sections A and B, and both are in the verified backup), but the framing was wrong and pointed at an unlisted `rm`.

The five basic-memory-linked files were already resolved in the delete list's `U4 RESOLVED` section — that precondition needs a keep/accept-dangling decision from Arnon, not more investigation.

| # | item | state |
|---|---|---|
| 9 | **Pre-push checklist gates** — `--stdlib`, `--ambient`, links, suite, version. All PASS. One new MEDIUM finding: release notes miss items 88/89 (user-visible) and 108 | DONE — Finding 6 in `tmp/doc-review-2026-08-27.md` |

| # | item | state |
|---|---|---|
| 10 | **`pyscn analyze` on the main package** (pre-push checklist) — score reported as noise per project policy; 0 dead code, 0 cycles, clean coupling/cohesion. One standout: `match_command` (`permissions.py`) cognitive 69, highest in the package, on the security-critical matching path | DONE — Finding 7 |

| # | item | state |
|---|---|---|
| 11 | **Adversarial verification pass over `13`-`16`** — every other DURABLE document had one; these were written 2026-08-27 with none | DONE |

**Result: all load-bearing claims verified.** `13`'s quotes check against **primaries** (`architecture-judge-backtest.md`, `architecture-sweep-practices.md`): *"Eight blind judges, one brief, one subject each"* is exact primary wording; `flat on 8 of 12`, `2 of 4`, `46,481`, `100/100`, `71 → 134`, and *"five one-line edits… three erased it"* all confirmed. `14`-`16`'s numbers (`10 of 17`, `9 of 9`, `23 of 28`, `14 of 76`, `planning 20 / implementation 32`, the eleven-day brick) all trace to source — **but to DURABLE siblings, one level removed from primaries**, which is the same limitation `09` warns about.

**One real gap found and fixed**: `14` §1.1 stated the refactor-step finding **without its counter-example**. `11` records ~10 tickets whose *subject* was a refactor, done competently — *"the capability and the willingness are both present"* — so the finding is about a missing completion criterion, not motivation. Without that, `14` read as "agents do not refactor", which the primary refutes. Now carried inline, with an instrument note.

| # | item | state |
|---|---|---|
| 12 | **Coverage audit of `16` against `15`** — do all cross-references resolve, and does every high-value conclusion have a landing place? | DONE |

**All 22 `15`-row citations in `16` resolve — no fabricated IDs.** But six high-value conclusions had **no recommendation attached**, now added as `16` §8.5: **P9 "prohibiting the fix increases the yield"** (which Arnon explicitly called *"a very important process finding"* — the worst of the misses), V3 in-process mutation testing, I9 decouple behaviour-pinning, V7 runtime sentinel, P14 debt register, P13 schedule synthesis.

**Method note**: a citation-based coverage check reported 26 gaps and **over-reported**; a phrase-based content check **under-reported** (it missed the two-judge setup, which `16` does cover). Only six survived both. Recorded in `16` §8.5.

---

## QUEUE EXHAUSTED pending Arnon — 2026-08-27

Everything not requiring his input is done. What remains, all blocked on him:

1. **Seven doc-review findings** need fix/defer/ignore — `tmp/doc-review-2026-08-27.md`. Findings 1 (suite declared red, is green) and 2 (dev-only invocation form) are factually unambiguous; 6 (release notes miss user-visible items 88/89) is the one with user impact.
2. **Deletion** — reassessed and backed up; needs his go-ahead, plus dispositions for the 5 basic-memory-linked files, the ticket-104 nest, and `13`-`16`.
3. **`13`-`16` themselves** await his review; he asked for them explicitly as review candidates.
4. **The worktree `ask` -> `allow` change** — decided, deferred to pre-push, needs his go-ahead (his global config).

## Arnon's decisions executed — 2026-08-27

| # | item | state |
|---|---|---|
| 13 | **Doc findings 1, 3, 4, 6 fixed**; 5 and 7 left alone per his call; **finding 2 RETRACTED** — the doc was already correct and the prescribed grep fired on the one legitimate use of the string | DONE |
| 14 | **`15` notation** — all 50 register rows converted from one-letter codes to spelled-out names with colour markers on value | DONE |
| 15 | **Deletion executed** — 300 deleted, 30 rescued, nest resolved. Reconciled 313 − 13 = 300 before any `rm`; all 300 verified present in the backup | DONE |
| 16 | **Worktree `ask` -> `allow`** — live file is deny-protected against me, so a reviewable copy went to `tmp/git.rules.toml`; Arnon applied it; verified by sandbox that it resolves to `allow` | DONE |
| 17 | **Opinion on making the TEMPORARY git rules permanent** — `tmp/git-rules-opinion.md`. Recommend permanent **except `restore`**, which destroys uncommitted work with no recovery path | DONE — awaiting his call |
| 18 | **basic-memory reindex** | IN FLIGHT (background) |

**Four pre-flight failures caught before the deletion ran, worth keeping as method evidence**: wrong path base (301 false "missing"); Section C's rescue uses a different heading format (29 vs 30); Section D's two entries are `.txt` not `.md` (311 vs 313); and **my own `norm()` collapsed nest paths onto their top-level namesakes** — treating two files I had already measured as *differing* as one. The reconcile-or-abort gate is what caught all four.

**The nest conflict resolved rather than needing a decision**: O5 and R10 are rescues that lived inside the nest, so both were moved out and the other two deleted.

---

# CONTINUATION STATE — end of 2026-08-27

**Tree is clean at `03f5089`** (except this file, updated after that commit). Everything from Arnon's decision batch is executed.

## Done today

Doc findings 1/3/4/6 fixed, 5/7 left alone, **2 retracted** (the doc was already correct; the prescribed grep fired on the one legitimate use of the string). `15` converted to spelled-out names + colour. **300 files deleted, 30 rescued**, nest resolved, basic-memory reindexed and reconciled at **468 entities = 468 files**. Worktree `ask` -> `allow` applied by Arnon and verified live through the sandbox. All supporting TOO-45 material now committed (`03f5089`), so the DURABLE analysis no longer cites untracked evidence.

## Open, nothing blocked on me

1. **`tmp/git-rules-opinion.md`** — recommend making the TEMPORARY git allow block permanent **except `restore`** (it destroys uncommitted work with no reflog and no recovery path). Plus two cleanups the block's own comment asks for: tighten the prefix convention, delete the dead `<TEMPORARY-COMMENT-OUT>` fence. **Awaiting Arnon's call.**
2. **TOO-71** (analysis `13`, architectural reviewer construction) and **TOO-72** (analysis `14`, conformance patterns) — Arnon invited comments on both. **Not yet written.**
3. **`15` and `16`** — Arnon reading. `16` §0's claim that `CLAUDE.md` should get SHORTER is the one most worth pushing back on.

## Pre-push checklist — three items not done

- **Coverage** — on the global wrap-up list, not run.
- **`install.md`** — not checked against this branch's code changes (item 108 moved `read_pre_tool_use_event` into the contract; internal, but unverified).
- **toolguard maintenance skill** — interactive, needs Arnon at the keyboard.

## Post-push, and it fails SILENTLY if skipped

`uv tool upgrade toolguard`, then smoke-test — Claude Code treats only exit 2 as blocking, so a broken hook registration means **no permission hook at all**, with no error anywhere:

```bash
echo '{"session_id":"t","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"'$PWD'"}' | ~/.local/bin/toolguard
```

## Notes for whoever picks this up

- **Anti-stall cron was deleted** at Arnon's word. Re-arm it before any unattended stretch — `12` C10's rejection was withdrawn today because no substitute has ever been demonstrated, and a punch list does not close the gap.
- **Backup**: `~/backup/claude/toolguard-memories-2026-08-27.tgz`, verified 765/765 pre-deletion.
- **The deletion pre-flight failed four times before reconciling.** If a similar operation comes up: reconcile counts against the stated totals and abort on mismatch. It caught a bug of mine that would have merged two genuinely different files.
