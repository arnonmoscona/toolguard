---
title: RESUME-2026-08-23-evening
type: note
permalink: toolguard/too-45/resume-2026-08-23-evening
---

# Resume state — 2026-08-23 evening (unattended stretch COMPLETE)

**Superseded the original queue. Everything in it is done.** Updated 2026-08-23 ~23:00 so a resumed session is not misdirected by a stale to-do list.

## Standing instructions (still in force)

- **Self-monitor usage** with `~/bin/claude-usage`. Pause and re-schedule at **90-95%** of the session window. Weekly limit is not the binding concern.
- **Never end a turn with only a stated plan** — end with a pending agent or a scheduled wakeup.
- **Do not delete anything** from `toolguard-memories/`. Arnon has not accepted the summaries.
- No commits beyond the standing `too-45` exception; no pushes; no YouTrack filings without his approval.

## What was completed

**The extraction deliverable is finished. Start at `DURABLE/README.md`** — it indexes everything below.

1. **Delete list rebuilt** from the verified triage → `DURABLE/PROPOSED-DELETE-LIST.md`. **300 to delete, 30 rescued.** R10 swap confirmed by byte size.
2. **All 211 untracked (permanent) files audited** section by section → `SECTION-A/B/C-AUDIT.md`, D and E inline. 194 safe, 13 rescued, 4 uncertain. The 102 tracked files were deliberately not audited — git recovers them.
3. **Four intermediate summaries corrected** from their `VERIFIED-*` companions: defect-taxonomy (16), open-questions (18), practices-with-evidence (36+4), rejected-methods (7).
4. **Two missing categories written**: `04-implementation-and-abstraction-habits.md` and `05-campaign-statistics.md`. Both were absent and both were on Arnon's original list.
5. **Cost document**: prompt-wait addendum (68.9h / 557 asks; 96.8% before 2026-08-03), C2/C3/C5 resolved, phase-resolved cost splits transcribed.
6. **`DURABLE/README.md`** written as the entry point, with Mermaid diagrams.

## Waiting on Arnon — do not act unilaterally

**Four findings in `DECISIONS-PENDING.md`, none filed, all verified at HEAD `305caa3`:**

1. `//` path spelling evades a deny rule (20 accidental occurrences in featherhill); `../` and `./` measure zero and are a defer.
2. `pwd.getpwnam` invisible to `--ambient` — fourth instance of that weak spot.
3. Decision vocabulary unnamed; strictness order triplicated. Naming is safe, merging is not.
4. `--contract` R3 passes over a live prose re-parse — stale exclusion plus name-based detector.

Also: acceptance of the summaries (gates all deletion), #102 deferral, #107, four `--undeclared-types` findings, `/documentation-review`, the push, then `uv tool upgrade toolguard` + smoke test, and two `dot_files` commits.

## If deletion is approved, three mechanics first

1. **Resync basic-memory** — all 313 are indexed; deleting leaves stale rows that keep answering searches.
2. **Five files are linked from surviving notes** (6 edges) — rescue or accept dangling refs.
3. **`toolguard-memories/toolguard-memories/`** is a stray doubled-path directory; remove the nest, not just the files.

## Two things a resumed session should know

- **A shared scratchpad hazard is live.** `/tmp/claude-1000/.../19b5a95c-.../scratchpad` is shared across the whole campaign; an agent once ran `rm -rf *.py` there and destroyed four evidence files another round cited by name. Never wildcard-delete in it. Recorded in `DURABLE/01`.
- **A clean null is the result to distrust.** Four instruments failed clean during this stretch, producing tidy wrong numbers rather than errors. Every measurement here that reconciles to an expected total says so.

## State

**All of the following was re-measured at `305caa3` on 2026-08-23 evening, not carried forward from an earlier session.** Tree clean on `too-45`; 79 commits; **suite `Ran 4008 tests` / `OK (expected failures=4)`** in 57s; `uv run ruff check .` clean; `tools/check_doc_links.py` reports all internal links resolve.

`tools/architecture_fitness.py` — **every arm below verified PASS individually**: `--stdlib`, `--ambient`, `--layers`, `--orphans`, `--undeclared-types`, `--predicates`. The complete flag set is `--layers --predicates --metrics --mocks --ambient --stdlib --orphans --undeclared-types --guard --guard-canaries-only --since --json --no-lint`. **There is no `--contract` flag** — I invented it earlier this evening, it errors with `unrecognized arguments`, and the mistake reached two documents before being caught. R3 lives under `--predicates`.

**Zero uncommitted source changes** — all work this stretch was in `toolguard-memories/`, which is unversioned apart from 222 tracked files.