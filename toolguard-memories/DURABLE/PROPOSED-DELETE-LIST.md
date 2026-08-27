---
title: PROPOSED-DELETE-LIST
type: note
permalink: toolguard/durable/proposed-delete-list
---

# PROPOSED DELETE LIST — `toolguard-memories/`

**PROPOSAL ONLY. Nothing was deleted, moved, or edited to produce this file.** Every number below was measured against the live filesystem on 2026-08-23; no count is carried over from `deletion-triage.md` or `VERIFIED-deletion-triage.md`. Reproduction scripts are named at the end.

## Headline

| | files | bytes | MiB |
|---|---|---|---|
| corpus now | **746** | 9,750,543 | 9.30 |
| mechanical rule set (rules 1-5) | 330 | 2,865,452 | 2.73 |
| rescued (not deleted) | 17 | 188,410 | 0.18 |
| **PROPOSED DELETE** | **313** | **2,677,042** | **2.55** |
| **KEPT** | **433** | **7,073,501** | **6.75** |

**Paths verified: 313 of 313 exist right now. Zero dropped for non-existence.** Two enumerated paths in the source triage were wrong (see DISAGREEMENTS D1) — both were relocated, not dropped, because the named files do exist elsewhere in the tree.

The reclaim is 27% of the bytes and 42% of the files. **The file count is the point, not the disk**: 313 fewer notes in the basic-memory index and in every future search result.

## Deletion method

`toolguard-memories/` is the basic-memory `toolguard` project store. Delete through `mcp__basic-memory__delete_note`, or `rm` and then force a re-sync. The verification pass found the SQLite index already running ahead of the files on disk, so "a sync will reconcile it" is an assumption about a mechanism that is currently not keeping up. Inbound wikilink relations break at the far end regardless of method.

---

## Delete proposal, by category

Categories are the source triage's rules 1-5, re-run against the live tree, minus the 17 rescues. Counts are post-rescue.

**A. Coder task recalls — 129 files, 651,391 bytes.** An implementer's pre-flight notes to itself: scope restatement, files it intends to touch, gates it intends to run, transient concurrency warnings. Written before the work and superseded by it. *Caveat: this rationale is not universally true — see rescues R10 and R15, both task recalls appended to after the work.*

**B. Implementation / coder / fix / documentation reports — 139 files, 1,449,895 bytes.** Per-task process detail for code that is now committed; this project's TOO-45 commit messages carry the measurements verbatim, so the conclusions survive the reports. What the reports uniquely hold is gate output and before/after counts, spent once merged.

**C. Blinded review rounds — 29 files, 443,634 bytes.** Reviewer findings, each with a paired repair report; both halves are inputs to committed code. *Caveat: R11 and R14 are both from this category, so the claim that "the declines are the only residue" understates it.*

**D. Superseded state / resume / queue snapshots — 8 files, 76,364 bytes.** Point-in-time coordinator state, superseded by `TOO-45 phase 3 resume.md` and `TOO-45 punch-list 2026-08-22.md`, both KEPT. *Three of the original eleven turned out not to be snapshots at all (R7, R9, R12) and are rescued.*

**E. Superseded rolling-pointer files — 7 files, 52,920 bytes.** Stale copies of a named file that also exists, or the state of a finished task.

**F. Named one-offs — 1 file, 2,838 bytes.** `implementation/TOO-15 P0 Keystone Implementation Task.md`. The second file in this rule, `TOO-45/lessons.md`, is rescued (R8).


---

# RESCUES HONOURED — 17 files

All 17 paths were checked individually: **every one exists, and every one was inside the mechanical rule set**, so each is a real rescue rather than a no-op. Sizes are measured.

| # | file | bytes | rule that would have caught it | why rescued |
|---|---|---|---|---|
| O1 | `implementation/TOO-45 ticket 20a repair round - coder implementation report.md` | 12,951 | R2 | Primary record of three injected `system-reminder` blocks, one instructing concealment of the agent's own `cp` restore |
| O2 | `implementation/TOO-45 F1 dollar-paren depth guard - coder implementation report.md` | 9,033 | R2 | Second independent observation of the same concealment reminder, different agent, different task |
| O3 | `TOO-45/reports/TOO-45 review-18-round3 repair - coder implementation report.md` | 13,425 | R2 | Two unfiled follow-ups (N8 load-time enforcement, N6 live hook config) plus the drafted user-facing release-note prose for the 0.5.1 `:*` fidelity fix |
| O4 | `implementation/TOO-45 ticket 44 broken isolation seam - coder implementation report.md` | 6,165 | R2 | The `~/.toolguard/errors/` census breakdown (1768 files, 133 pre-session, 806 on 2026-08-12), which exists nowhere else |
| O5 | `toolguard-memories/TOO-45/TOO-45 ticket 104 - dicts are undeclared types - coder implementation report.md` | 16,092 | R2 | Measured `--undeclared-types` run, four findings explicitly not fixed pending Arnon, a self-caught `re.match` anchoring bug |
| R7 | `TOO-45/TOO-45-punch-list-2026-08-20.md` | 28,727 | R4state | Not a snapshot: eight sections of durable campaign analysis, including two rules Arnon authored, absent from the newer punch list |
| R8 | `TOO-45/lessons.md` | 3,763 | R5 | The "wholly contained in the 21 KB file" claim is false; sole home of three Arnon-quoted architectural decisions |
| R9 | `TOO-45/TOO-45-retriage-2026-08-20.md` | 4,492 | R4state | Only copy of the 10-shape corpus exposure table over 57,448 commands, split featherhill/toolguard and mapped to tickets |
| R10 | `toolguard-memories/implementation/Coder Latest Task Recall.md` | 6,093 | R1 | **Swap correction.** Holds the cold-review round, six corrected false claims, and a new defect found on re-verification. See D2 |
| R11 | `TOO-45/reports/review-78-round5.md` | 13,529 | R3 | Sole record of an undated deliberate `[native]` divergence. **Re-verified open today** — see D4 |
| R12 | `TOO-45/TOO-45 status 2026-08-14 - phase 2.md` | 10,999 | R4state | Audit trail of five deliberate overrides of the "agents never edit `test/`" rule, naming the files and pins changed |
| R13 | `implementation/TOO-45 ticket 19 repair round - coder implementation report.md` | 8,690 | R2 | Fourth injection class (correct finding bundled with unauthorised scope expansion) plus the only raw before/after output of the pinned-`PYTHONPATH` run now enshrined in `.claude/rules/evidence-before-fixing.md` |
| R14 | `TOO-45/reports/review-74-round1.md` | 15,772 | R3 | A reviewer, not an implementer, refusing the same reminder, with the sharpest statement of why |
| R15 | `implementation/TOO-45 ticket 20a repair round - coder task recall.md` | 5,412 | R1 | The contemporaneous record of the concealment reminder, written during the session; O1 is the retrospective one |
| R16 | `TOO-19/TOO-19 Phase 0a increment 1 - implementation report.md` | 13,947 | R2 | The only refutation of a queued widening of `technical-notes.md`. **Re-verified live** — see D4 |
| R17 | `TOO-45/reports/TOO-44 ambient prose repair pass 2 - coder implementation report.md` | 4,753 | R2 | The only correction to `follow-up-queue.md` item 23, which still overstates its own contents. **Re-verified live** — see D4 |
| R18 | `TOO-19/TOO-19 Review Fixes - Complexity and Minors Implementation Report.md` | 14,567 | R2 | The only prior point on the duplication trend (43 groups / 13.1%), without which today's 15.9% has no baseline |

## Two one-line edits that make R16 and R17 unnecessary

Both fix a live defect in a KEPT file and are worth doing regardless of the deletion:

- **R16**: strike *"anywhere in the codebase"* from the queued `technical-notes.md` replacement at `follow-up-queue.md:150`. Measured: `grep -n "anywhere in the codebase"` returns that line, and `grep -rn "_TOOL_WRAPPER_RE = " toolguard/` returns **two** definitions with different patterns (`rule_entry.py:59`, `tools/log_harvest.py:62`). The widened claim would be false on application.
- **R17**: mark item 23's first string closed at `follow-up-queue.md:200`. Measured: `grep -rc "Searched for" toolguard/path_utils.py` → **0** (fixed); `grep -rn "bounded walk-up" toolguard/ --include='*.py'` → **`path_utils.py:279`** (still open, and the queue cites line 242, so its line numbers have drifted).

---

# DISAGREEMENTS

Where the two source documents conflict, or where a source document conflicts with the live filesystem. **The verified document supersedes the original wherever they disagree**; these are the places I had to make a call.

**D1. Two enumerated rule-4 paths in the original do not resolve.** The original lists `phase-2-baseline-reds.txt` and `commit-message-03.txt` without directories; the verified document says all eleven "exist, all found" without stating where. Measured: both live at `TOO-45/`, not `TOO-45/reports/` where a reader would put them. Likewise the original's rolling-pointer entry `implementation/coder-latest-{implementation-report,task-recall}.md` is the lowercase-hyphen spelling, which is a **different pair of files** from `implementation/Coder Latest Implementation Report.md` / `Coder Latest Task Recall.md`. **Chose**: relocate rather than drop, since the named files demonstrably exist. Zero paths dropped for non-existence. This is the spelling-sensitivity hazard the verified document warns about, showing up in its own confirmation.

**D2. The R10 swap — verified independently, and the verified document is right.** Measured byte sizes in `toolguard-memories/toolguard-memories/implementation/`:

```
1,027  Coder Latest Implementation Report.md
6,093  Coder Latest Task Recall.md
```

I read the 1,027-byte report in full. It is explicitly a pointer: *"Full detail ... is in the final chat response to the calling agent, per its 'do not write report files' instruction — this note is the short pointer for continuity, not a duplicate of that content."* **Chose**: rescue the task recall (6,093 B, content), delete the report (1,027 B, stub). The original's rescue #5/#6 is backwards for this pair. For the *other* pair in that directory, ticket 104, the original is right and the **report** (16,092 B) is the substantial file — so the two pairs go opposite ways, which is exactly why a pattern could not have decided this.

**D3. Counts — I reproduce neither document's headline, and both are now stale.** Measured today: **746** files (original 733, verified 739); **330** mechanical (verified 330 — this one reproduces exactly); **313** proposed delete (original 323, verified 324, the difference being the 13 additional rescues). The per-category counts confirm the verified document against the original: task recalls **131** not 133, the implementation-report family **148** not 143. **Chose**: the live measurement in every case. The tree is being written to *while this is being analysed* — the corpus total moved from 9,712,032 to 9,750,543 bytes over roughly fifteen minutes of this session. Treat every byte figure here as accurate to the minute it was taken, not to the day.

**D4. The cost/elapsed count — the original's "nine" is wrong by more than an order of magnitude, and I measured it a third way.** The verified document says 104 (heading-based) and cites a separate sweep agent at 124 (figure-based). My instrument counted files in the **surviving 313-file delete set** that contain an actual dollar or elapsed figure, not merely the word:

```
STRICT cost-record files (a $ figure OR an elapsed figure): 117
  $ figure but no elapsed figure : 69
  files with cost/elapsed in a markdown TABLE row : 15
review-NN-roundN files in delete set: 25; carrying a cost record: 17
```

**117**, against the original's 9. Three instruments (104, 117, 124) disagree in detail and agree that the original is out by 10x. The 15-table figure reproduces exactly, which supports the verified document's diagnosis that the "9" was an imperfect enumeration of the markdown-table subset. **Of the nine files the original named, four are now rescued for unrelated reasons, so at most five were ever at risk.** And the reviewer-side population the original never looked at is real: **17 of the 25 surviving review rounds carry a cost record**, in a format absent from every implementer report. **Chose**: the verified document's framing, with my own number.

**D5. But the cost-extraction blocker is already discharged, which neither document could know.** The verified document's Part 3 item 3 says to correct the extraction step to 104 files *or* admit the cost record will be lost. Measured against the live tree: `DURABLE/02-campaign-cost-data.md` exists, is 50,129 bytes, contains **164 dollar figures**, and names **142 of the 330** mechanical-delete files as sources. **Chose**: treat the precondition as satisfied. The extraction that both documents were waiting on has happened.

**D6. Same for the out-of-band register.** The verified document's item 4 says extract all 21 records first. Measured: **35** files outside `DURABLE/` record such an observation, **25** are in the mechanical set, **6** are rescued, so **19 would still be lost** after honouring every rescue. But `DURABLE/03-out-of-band-instruction-records.md` (43,771 bytes) **cites all 19 by name — 19 of 19**. **Chose**: proceed. The rescues preserve the primary evidence; the register preserves the rest. Note this makes the verified document's "21" my "35" — a third instrument, a third number, same conclusion that the original's "two" was an order of magnitude low.

**D7. Rescues 1-4, scope correction.** The verified document narrows three of the original's four claims and I have adopted the narrowed versions in the rescue table above. Specifically: **O1's** *"not in any commit, ticket, or report"* is misattributed — `TOO-45 phase 3 resume.md` (KEPT) carries a consolidated summary, so the correct claim is that only the *primary* records are in the delete pile. **O3's** *"I did not find this draft's warning text elsewhere"* is over-cautious — `docs/native-pattern-reference.md` carries the substance; what is unique is the drafted user-facing prose and the two unfiled items. **O4** is half-closed: I verified the re-drift guard **did** land (`TestDecisionReachesStdoutWhenCrashLoggingFails` at `test/unit/test_hook.py:3337`, cross-referenced from `test_hook_error_reporter.py:274`), so only the errors-directory census justifies the rescue. All four stay rescued; none of the corrections removes the unique content.

**D8. `build_estimator_briefing.py` is not at risk from these rules.** The original calls it *"at risk from exactly this deletion pass"*; the verified document refutes that. Confirmed: it does not appear in the 330-file mechanical set, because rules 1-5 match `.md`/`.txt` name patterns only. **Chose**: the verified document. It remains at risk from a *directory-level* deletion, and the recommendation to move it to the repo's `tools/` still stands on its own merits.

---

# UNRESOLVED

Things I could not determine. Stated as open rather than guessed.

**U1. Whether the extraction agents are finished.** Both source documents make this the binding sequencing condition. `DURABLE/` now holds three numbered outputs (01, 02, 03), a `VERIFICATION-PROTOCOL.md`, and ten files under `intermediate/` — which looks complete for the cost and out-of-band strands (D5, D6). I cannot tell from the filesystem whether a fourth strand is still running or whether the outputs have been reviewed. **Do not execute until a human confirms this.**

**U2. Two live rolling pointers are in the delete set and I am not sure they should be.** `implementation/Coder Latest Implementation Report.md` (26,645 B) and `implementation/Coder Latest Task Recall.md` (2,867 B) are swept by rules 1-2, not by the rolling-pointer rule. They are the files the `feature-coder` workflow writes to, and both are currently modified in the working tree. Their content is ticket 108 and ticket 105 phase 2, both of which are committed (`9b4ff1d`, `2ca11b2`), so the material is not lost — but the 26,645-byte report also carries a preserved earlier report below a horizontal rule, and I did not diff that tail against the named per-ticket reports. **Deleting them is probably harmless and probably churn.** Flagging rather than deciding.

**U3. Category B was not exhaustively read, and this is the same residual risk the original flagged.** I verified the 17 rescues individually and re-measured the two content classes the verification identified as escaping (cost data, out-of-band records). I did **not** read the remaining 139 reports or 129 recalls. The verified document's finding that defect residue *does* get written back into surviving tickets is reassuring but is a sample, not a census. If that residual risk is unacceptable, the cheap mitigation is to delete categories D, E and F now (16 files) and hold A, B and C — **but note the original's version of this mitigation, "delete only the task recalls", is the wrong half**: R10 and R15 are both task recalls.

**U4. Relations and inbound links.** The verified document reports 149 outgoing relations in the basic-memory index and warns that deleting a relation *target* leaves a dangling reference that neither `rm` nor `delete_note` repairs at the far end. **I did not query the index** — it is a live SQLite store and reading it is outside what this task needs. So I cannot say how many of the 313 are relation targets. The original notes `phase-2-baseline-reds.txt` is the most-cited target in the tree and is in the delete set. Worth one query before executing.

**U5. `TOO-45/spikes/` (13 files).** Both documents lean keep-and-fix-the-doc-sentence and neither re-verified it. Not in the mechanical set, so this proposal does not touch it. Unresolved and harmless.

**U6. mtimes are not authoring dates and I used one before I was told.** The tree was bulk-touched in batches (69 files share one mtime, 49 share another). I read `ls -la` output early and described one file as the "current" rolling pointer on the strength of its timestamp; that inference is withdrawn, and U2 above now rests on the file's *content* and on the CLAUDE.md workflow instead. **No entry in the delete list or the rescue list was decided by mtime** — the rules are name-based, the R10 swap is a byte-size question, and every rescue was checked by reading or grepping content. I re-derived nothing else, because there was nothing else to re-derive.

---

## Reproduction

Three read-only scripts in the session scratchpad produced every number above:

- `build_delete_list.py` — re-runs the source triage's rules 1-5 against the live tree and emits the 330-file mechanical set with sizes.
- `check_rescues.py` — asserts each of the 17 rescue paths exists and lies inside that set, then emits the 313-file proposal.
- `cost_probe.py` — the strict cost/elapsed instrument behind D4.

None of them writes to `toolguard-memories/`.

---

# THE 313 FILES

Sizes in bytes, paths relative to `toolguard-memories/`.

## A. Coder task recalls — 129 files, 651391 bytes
    3444  TOO-19/TOO-19 Coder Task Recall - test log-dir isolation leak fix.md
    4793  TOO-19/TOO-19 Phase 1 Increment 9 - coder task recall.md
    3484  TOO-19/TOO-19 Phase 1 increment 2 coder task recall.md
    5613  TOO-19/TOO-19 Phase 1 increments 6 and 7 - coder task recall.md
    9295  TOO-19/TOO-19 code review Majors M1-M3 - coder task recall.md
    5372  TOO-19/TOO-19 code review minors m1-m4 m6 - coder task recall.md
    6073  TOO-19/TOO-19 deny-side rule fabrication fix - coder task recall.md
    4681  TOO-19/TOO-19 discovery log change-detection task recall.md
    4620  TOO-19/TOO-19 documentation review fixes 2026-08-01 - coder task recall.md
    4569  TOO-19/TOO-19 parse-failure floor bypass via undecidable segments - task recall.md
    10553  TOO-19/TOO-19 shadowing detection and install hardening - coder task recall.md
    4951  TOO-19/TOO-19 undecidable_fallback - audit finding and docs task recall.md
    5909  TOO-19/TOO-19 undecidable_fallback - coder task recall.md
    3004  TOO-45/TOO-44 ambient prose repair pass 2 - coder task recall.md
    2260  TOO-45/TOO-45 Item 97 Step 3 - kind means only fact 1 - coder task recall.md
    7858  TOO-45/TOO-45 governed_tools default change - coder task recall.md
    3459  TOO-45/TOO-45 mocks prose repair pass 3 - coder task recall.md
    3950  TOO-45/TOO-45 patterns.py comment rewrite - coder task recall.md
    2644  TOO-45/TOO-45 phase 2 prefix-match boundary - coder task recall.md
    5839  TOO-45/TOO-45 phase 2 unit 1 follow-up - coder task recall.md
    4062  TOO-45/TOO-45 phase 2 unit 6 - coder task recall.md
    4386  TOO-45/TOO-45 phase 2 unit 8 remaining maintenance analyzers - coder task recall.md
    4145  TOO-45/TOO-45 phase 2 work unit 2 - coder task recall.md
    3982  TOO-45/TOO-45 phase 2 work unit 3 - coder task recall.md
    4240  TOO-45/TOO-45 phase 2 work unit 4 - coder task recall.md
    8230  TOO-45/TOO-45 phase 2 work unit 7 (tools-hierarchy, tools-mining) - coder task recall.md
    7549  TOO-45/TOO-45 punch-list 03 stages 2+4 - coder task recall.md
    6873  TOO-45/TOO-45 punch-list 07 test tier - coder task recall.md
    6500  TOO-45/TOO-45 punch-list 39 round 3 - coder task recall.md
    4377  TOO-45/TOO-45 punch-list 39 round 4 - coder task recall.md
    5108  TOO-45/TOO-45 punch-list 94 validation_issues split - coder task recall.md
    7123  TOO-45/TOO-45 repair round - review-18-round3 fixes - coder task recall.md
    5048  TOO-45/TOO-45 revert redirect-glued tilde extension - coder task recall.md
    5365  TOO-45/TOO-45 review-18-round5 repair - coder task recall.md
    5935  TOO-45/TOO-45 review-39-round1 repair - coder task recall.md
    2647  TOO-45/TOO-45 review-44 round4 repair - coder task recall.md
    4364  TOO-45/TOO-45 review-44 round5 repair - coder task recall.md
    5450  TOO-45/TOO-45 review-74 round1 blocking fixes - coder task recall.md
    3589  TOO-45/TOO-45 review-77 round1 repair - coder task recall.md
    3940  TOO-45/TOO-45 review-78 round1 repair - coder task recall.md
    4393  TOO-45/TOO-45 review-79-round2 fix - coder task recall.md
    4101  TOO-45/TOO-45 review-80 round1 prose repair - coder task recall.md
    2663  TOO-45/TOO-45 review-80 round3 prose repair - coder task recall.md
    5547  TOO-45/TOO-45 suppression store follow-up - coder task recall.md
    6097  TOO-45/TOO-45 ticket 108 - coder task recall.md
    7235  TOO-45/TOO-45 ticket 32 item 1 - MigrationOutcome reason carrying - coder task recall.md
    3304  TOO-45/TOO-45 ticket 44 ambient facts - coder task recall.md
    3521  TOO-45/TOO-45 ticket 44 round6 prose repair - coder task recall.md
    6790  TOO-45/TOO-45 ticket 74 (hook payload-key + empty-registry fail-open) - coder task recall.md
    3016  TOO-45/TOO-45 ticket 77 grammar phase 1 M1+L1 - coder task recall.md
    3686  TOO-45/TOO-45 ticket 77 grammar phase 1 delta fold-in (M1 +=, L1, L2, L3) - coder task recall.md
    2843  TOO-45/TOO-45 ticket 77 leading env assignment - coder task recall.md
    4057  TOO-45/TOO-45 ticket 77 phase 2 matcher - coder task recall.md
    5805  TOO-45/TOO-45 ticket 78 follow-up (three remaining pattern types) - coder task recall.md
    4416  TOO-45/TOO-45 ticket 78 tilde-expanded variant - coder task recall.md
    6568  TOO-45/TOO-45 ticket 79 command substitution ASK floor - coder task recall.md
    2330  TOO-45/TOO-45 ticket 80 ambient routes - coder task recall.md
    4878  TOO-45/TOO-45 ticket 81 follow-up - coder task recall.md
    6243  TOO-45/TOO-45 ticket 89 - word-boundary regex silently inert in double-quoted TOML - coder task recall.md
    10006  TOO-45/TOO-45 tickets 42 and 47 - coder task recall.md
    3333  implementation/Coder Latest Task Recall - TOO-16 Distribution Tooling.md
    3425  implementation/Coder Latest Task Recall - TOO-17 Stage 2 Readability Refactor.md
    4133  implementation/Coder Latest Task Recall - TOO-30 GREEN Phase Implementation.md
    6741  implementation/Coder Latest Task Recall - TOO-30 RED Phase Tests.md
    2867  implementation/Coder Latest Task Recall.md
    8071  implementation/TOO-15 Coder Task Recall - Backup Collision and Reminder Lines.md
    6281  implementation/TOO-15 Coder Task Recall - Crash Capture (log_crash).md
    5177  implementation/TOO-15 Coder Task Recall - Downgrade loose-no-match-fallback to LOW.md
    3740  implementation/TOO-15 Coder Task Recall - Hard Deny Anchoring (8 to 16 patterns) RED phase.md
    9616  implementation/TOO-15 Coder Task Recall - discover-projects, install-skills, seed-hard-deny (RED phase).md
    4606  implementation/TOO-15 Coder Task Recall - no_match_fallback default ask.md
    4503  implementation/TOO-15 P1 Audit Context Export - Coder Task Recall.md
    3667  implementation/TOO-15 P2-A.1 Coder Task Recall.md
    5762  implementation/TOO-15 coder task recall- skills-status subcommand.md
    4589  implementation/TOO-15 coder task recall.md
    3732  implementation/TOO-17 Grammar-First Rework Task Recall.md
    5603  implementation/TOO-19 Coder Task Recall - Complexity and Minors Fixes.md
    5655  implementation/TOO-19 Coder Task Recall - M1 and M2 Review Fixes.md
    6793  implementation/TOO-19 Coder Task Recall.md
    6187  implementation/TOO-19 Phase 1 increments 3 and 5 coder task recall.md
    4698  implementation/TOO-19 Round 2 Review Fixes Coder Task Recall.md
    5563  implementation/TOO-19 allow and allow_with_no_warnings fallback values - coder task recall.md
    2102  implementation/TOO-19 compound.py _extract_outer_command Tests and Fixes - Task Recall.md
    5843  implementation/TOO-19 s1 SessionStart invariant and m3 wrapper false-positive - coder task recall.md
    3316  implementation/TOO-44 follow-up - re-drift guard for TestDecisionReachesStdoutWhenCrashLoggingFails - coder task recall.md
    5164  implementation/TOO-45 F1 dollar-paren depth guard - coder task recall.md
    3050  implementation/TOO-45 Item 95 - split judge_unit - coder task recall.md
    4593  implementation/TOO-45 R3 review-fix coder task recall.md
    4673  implementation/TOO-45 R3 second review-fix coder task recall.md
    3248  implementation/TOO-45 ambient repair pass - coder task recall.md
    11702  implementation/TOO-45 canary-automode coder task recall.md
    7492  implementation/TOO-45 compound-resolve cycle - coder task recall.md
    4954  implementation/TOO-45 corpus sub-verdict extension - coder task recall.md
    4599  implementation/TOO-45 phase 2 cleanup task - coder task recall.md
    5421  implementation/TOO-45 phase 2 work unit 9 - coder task recall.md
    6584  implementation/TOO-45 proposed ticket 18 - multitoken prefix over-match - coder task recall.md
    3432  implementation/TOO-45 proposed ticket 45 inert-mock static check - coder task recall.md
    2770  implementation/TOO-45 proposed ticket 96 - coder task recall.md
    5394  implementation/TOO-45 punch-list #01 final pass coder task recall.md
    12445  implementation/TOO-45 punch-list #01 suppression store — coder task recall (pass 4).md
    6400  implementation/TOO-45 punch-list 04 error reporter - coder task recall.md
    6137  implementation/TOO-45 punch-list 04 error reporter follow-up - coder task recall.md
    10588  implementation/TOO-45 punch-list 04 error reporter — Reporter class refactor — coder task recall.md
    3872  implementation/TOO-45 punch-list 15 migrate lock - coder task recall.md
    6052  implementation/TOO-45 resolution seam Protocols - coder task recall.md
    2625  implementation/TOO-45 review-18-round4 repair - coder task recall.md
    3516  implementation/TOO-45 review-78 B1 tilde-after-redirect fix - coder task recall.md
    5682  implementation/TOO-45 review-78 round3 repair - coder task recall.md
    3241  implementation/TOO-45 review-79-round3 repair - coder task recall.md
    5036  implementation/TOO-45 spike B - coder task recall.md
    2827  implementation/TOO-45 spike C - coder task recall.md
    3746  implementation/TOO-45 statement_bounds_containing table refactor - coder task recall.md
    5286  implementation/TOO-45 ticket 100 - coder task recall.md
    5180  implementation/TOO-45 ticket 101 bare-brace grammar fix - coder task recall.md
    2177  implementation/TOO-45 ticket 105 - coder task recall.md
    5838  implementation/TOO-45 ticket 14 residual - takeover notice routing - coder task recall.md
    3269  implementation/TOO-45 ticket 19 repair round - coder task recall.md
    3897  implementation/TOO-45 ticket 22 - redundancy report unsafe deletions - coder task recall.md
    5823  implementation/TOO-45 ticket 38 fallback_kind prose-parsing fix - coder task recall.md
    2639  implementation/TOO-45 ticket 44 broken isolation seam in test_hook.py - coder task recall.md
    5676  implementation/TOO-45 ticket 70 punch-list item - coder task recall.md
    4888  implementation/TOO-45 ticket 81 - coder task recall.md
    6888  implementation/TOO-45 ticket 85 chunk A - coder task recall.md
    5785  implementation/TOO-45 ticket 85 chunk B - coder task recall.md
    2492  implementation/TOO-45 ticket 85 chunk C - coder task recall.md
    3673  implementation/TOO-45 ticket 98 chunk 3 - module boundary move - coder task recall.md
    4684  implementation/TOO-45 ticket 99 - coder task recall.md
    4192  implementation/TOO-8 Phase 2 Coder Task Recall.md
    4975  toolguard-memories/TOO-45/TOO-45 ticket 104 - dicts are undeclared types - coder task recall.md

## B. Implementation / coder / fix / documentation reports — 139 files, 1449895 bytes
    5111  TOO-15/TOO-15 P1 Security Audit Aggregator Implementation Report.md
    4185  TOO-16/TOO-16 update-check feature implementation report.md
    16593  TOO-19/TOO-19 Corrective Change Implementation Report.md
    17768  TOO-19/TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report.md
    8054  TOO-19/TOO-19 Phase 0a - RuleEntry.raw sentinel fix + coverage - Implementation Report.md
    15611  TOO-19/TOO-19 Phase 0a increment 0 - Coder Implementation Report.md
    8575  TOO-19/TOO-19 Phase 0a increment 2 implementation report.md
    8232  TOO-19/TOO-19 Phase 0a increment 4 implementation report.md
    5620  TOO-19/TOO-19 Phase 0a increment 5 implementation report.md
    10928  TOO-19/TOO-19 Phase 0a increment 6 implementation report.md
    13646  TOO-19/TOO-19 Phase 0a increment 8 implementation report.md
    10000  TOO-19/TOO-19 Phase 0a increments 7 and 9 implementation report.md
    11229  TOO-19/TOO-19 Phase 0b Increments 3-4 Implementation Report.md
    10309  TOO-19/TOO-19 Phase 0b Increments 5-6 Implementation Report.md
    9989  TOO-19/TOO-19 Phase 0b increments 1-2 implementation report.md
    8469  TOO-19/TOO-19 Phase 1 increment 2 implementation report.md
    10293  TOO-19/TOO-19 Phase 1 increment 9 documentation report.md
    9251  TOO-19/TOO-19 Phase 1 increments 3 and 5 implementation report.md
    10086  TOO-19/TOO-19 Phase 1 increments 6 and 7 implementation report.md
    23692  TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md
    7540  TOO-19/TOO-19 Review Fixes - M1 and M2 Implementation Report.md
    10611  TOO-19/TOO-19 Review Fixes - M3 and M5 Implementation Report.md
    12061  TOO-19/TOO-19 code review Majors M1-M3 - fix report.md
    12432  TOO-19/TOO-19 code review minors m1-m4 m6 - fix report.md
    6174  TOO-19/TOO-19 config_types.py extraction implementation report.md
    14422  TOO-19/TOO-19 discovery log change-detection implementation report.md
    8608  TOO-19/TOO-19 increment 3 - hard_deny entries - implementation report.md
    8836  TOO-19/TOO-19 parse-failure floor bypass via undecidable segments - fix report.md
    14616  TOO-19/TOO-19 test log-dir isolation leak - fix report.md
    12114  TOO-19/TOO-19 undecidable_fallback - config and threading implementation report.md
    7413  TOO-30/TOO-30 Coder Implementation Report - GREEN Phase.md
    11116  TOO-30/TOO-30 Coder Implementation Report - RED Phase Tests.md
    8970  TOO-30/TOO-30 Test Isolation Cleanup - Implementation Report.md
    6270  TOO-45/TOO-45 Item 97 Step 3 - kind means only fact 1 - coder implementation report.md
    13477  TOO-45/TOO-45 phase 2 config loading and untruths - coder report.md
    10480  TOO-45/TOO-45 phase 2 follow-up unit 5 (golden adjudication) - coder report.md
    9195  TOO-45/TOO-45 phase 2 inline foreign-code ASK floor - coder report.md
    10801  TOO-45/TOO-45 phase 2 last actionable reds - coder report.md
    6370  TOO-45/TOO-45 phase 2 log writer+harvest - coder report.md
    10233  TOO-45/TOO-45 phase 2 prefix-match boundary - coder report.md
    13379  TOO-45/TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md
    14889  TOO-45/TOO-45 phase 2 unit 1 follow-up - coder report.md
    10058  TOO-45/TOO-45 phase 2 unit 6 - coder report.md
    11968  TOO-45/TOO-45 phase 2 unit 6 follow-up - coder report.md
    10363  TOO-45/TOO-45 phase 2 unit 8 remaining maintenance analyzers - coder report.md
    8921  TOO-45/TOO-45 phase 2 work unit 2 - coder report.md
    9303  TOO-45/TOO-45 phase 2 work unit 3 - coder report.md
    9536  TOO-45/TOO-45 phase 2 work unit 9 - coder report.md
    9921  TOO-45/TOO-45 punch-list 94 validation_issues split - coder implementation report.md
    7785  TOO-45/TOO-45 ticket 32 item 1 - MigrationOutcome reason carrying - coder implementation report.md
    7958  TOO-45/TOO-45 ticket 44 ambient facts - coder implementation report.md
    8775  TOO-45/TOO-45 ticket 80 ambient routes - coder implementation report.md
    9273  TOO-45/TOO-45 ticket 81 follow-up - coder implementation report.md
    10299  TOO-45/TOO-45 ticket 89 - word-boundary regex silently inert - coder implementation report.md
    9553  TOO-45/TOO-45 tickets 42 and 47 - coder implementation report.md
    10132  TOO-45/reports/Review 79 round 4 blocking fix - coder implementation report.md
    20522  TOO-45/reports/TOO-45 proposed ticket 18 - default multitoken prefix over-match - coder implementation report.md
    16063  TOO-45/reports/TOO-45 proposed ticket 79 - command substitution ASK floor - coder implementation report.md
    14575  TOO-45/reports/TOO-45 punch-list 39 round 3 - coder implementation report.md
    12393  TOO-45/reports/TOO-45 punch-list 39 round 4 - coder implementation report.md
    8557  TOO-45/reports/TOO-45 revert redirect-glued tilde extension - coder implementation report.md
    18951  TOO-45/reports/TOO-45 review-18 round1 repair - coder implementation report.md
    9781  TOO-45/reports/TOO-45 review-18-round4 repair - coder implementation report.md
    17239  TOO-45/reports/TOO-45 review-18-round5 repair - coder implementation report.md
    11463  TOO-45/reports/TOO-45 review-39-round1 repair - coder implementation report.md
    6259  TOO-45/reports/TOO-45 review-44 round4 repair - implementation report.md
    12306  TOO-45/reports/TOO-45 review-44 round5 repair - coder implementation report.md
    10838  TOO-45/reports/TOO-45 review-77 round1 repair - coder implementation report.md
    10540  TOO-45/reports/TOO-45 review-78 round1 repair - coder implementation report.md
    10613  TOO-45/reports/TOO-45 review-78 round2 repair - coder implementation report.md
    8284  TOO-45/reports/TOO-45 review-78 round3 repair - coder implementation report.md
    8837  TOO-45/reports/TOO-45 review-79-round3 repair - coder implementation report.md
    6934  TOO-45/reports/TOO-45 review-80 round1 prose repair - implementation report.md
    5260  TOO-45/reports/TOO-45 review-80 round3 prose repair - implementation report.md
    7827  TOO-45/reports/TOO-45 ticket 44 round6 prose repair - implementation report.md
    10687  TOO-45/reports/TOO-45 ticket 74 (hook payload-key + empty-registry fail-open) - coder implementation report.md
    11241  TOO-45/reports/TOO-45 ticket 77 grammar phase 1 M1+L1 - coder implementation report.md
    10768  TOO-45/reports/TOO-45 ticket 77 grammar phase 1 delta fold-in (M1 +=, L1, L2, L3) - coder implementation report.md
    8807  TOO-45/reports/TOO-45 ticket 77 leading env assignment - phase 1 grammar - coder report.md
    11739  TOO-45/reports/TOO-45 ticket 77 phase 2 matcher - coder implementation report.md
    17500  TOO-45/reports/TOO-45 ticket 78 follow-up (three remaining pattern types) - coder implementation report.md
    12241  TOO-45/reports/TOO-45 ticket 78 tilde-expanded variant - coder implementation report.md
    9738  TOO-45/reports/TOO-45 ticket 79 sub-command breakdown regression fix - coder implementation report.md
    7252  TOO-45/reports/TOO-45 ticket 80 finish (3 licensed test edits) - coder implementation report.md
    3529  TOO-45/reports/TOO-45 ticket 81 residual re-measure - coder report.md
    17972  TOO-45/reports/review-18-round2 repair - coder implementation report.md
    12981  TOO-45/reports/review-79-round1 repair - coder implementation report.md
    14990  TOO-45/reports/review-79-round2 fix - implementation report.md
    26645  implementation/Coder Latest Implementation Report.md
    3747  implementation/Phase 5 review-fixes implementation report.md
    1985  implementation/TOO-15 Coder Implementation Report - Crash Capture RED Phase.md
    3098  implementation/TOO-15 Coder Implementation Report - Hard Deny Anchoring RED Phase.md
    2562  implementation/TOO-15 Coder Implementation Report - Helper Subcommands GREEN Phase.md
    2802  implementation/TOO-15 Coder Implementation Report - Helper Subcommands RED Phase.md
    7265  implementation/TOO-15 No-Match Semantics Implementation Report.md
    7689  implementation/TOO-15 P0 Analyzers Implementation Report.md
    5351  implementation/TOO-15 P0 Keystone Implementation Report.md
    6444  implementation/TOO-15 P1 Audit Context Export Implementation Report.md
    6883  implementation/TOO-15 P2-A.1 Consolidation Core Implementation Report.md
    10156  implementation/TOO-15 Project Root Consolidation Implementation Report.md
    5906  implementation/TOO-16 Distribution Tooling Enhancement Implementation Report.md
    9656  implementation/TOO-17 Implementation Report.md
    7853  implementation/TOO-45 Item 95 - split judge_unit - coder implementation report.md
    12672  implementation/TOO-45 R3 review-fix implementation report.md
    9885  implementation/TOO-45 R3 second review-fix implementation report.md
    5852  implementation/TOO-45 ambient repair pass - implementation report.md
    3783  implementation/TOO-45 mocks prose repair pass 3 - implementation report.md
    10413  implementation/TOO-45 proposed ticket 45 inert-mock static check - implementation report.md
    8362  implementation/TOO-45 proposed ticket 96 - coder implementation report.md
    12081  implementation/TOO-45 punch-list #01 suppression store - implementation report.md
    6717  implementation/TOO-45 punch-list #01 suppression store follow-up - implementation report.md
    12612  implementation/TOO-45 punch-list #01 suppression store — implementation report (pass 4).md
    19556  implementation/TOO-45 punch-list 03 stages 2+4 - coder implementation report.md
    60500  implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md
    7404  implementation/TOO-45 punch-list 07 test tier - coder implementation report.md
    26851  implementation/TOO-45 punch-list 15 migrate lock - coder implementation report.md
    8670  implementation/TOO-45 review-78 B1 tilde-after-redirect fix - coder implementation report.md
    6000  implementation/TOO-45 spike B - coder implementation report.md
    4601  implementation/TOO-45 spike C - coder implementation report.md
    9018  implementation/TOO-45 statement_bounds_containing table refactor - coder implementation report.md
    13779  implementation/TOO-45 ticket 100 - coder implementation report.md
    6737  implementation/TOO-45 ticket 101 bare-brace grammar fix - coder implementation report.md
    11771  implementation/TOO-45 ticket 105 - coder implementation report.md
    8140  implementation/TOO-45 ticket 105 phase 1 - coder implementation report.md
    9734  implementation/TOO-45 ticket 14 residual - takeover notice routing - coder implementation report.md
    9932  implementation/TOO-45 ticket 19 P2+P3 - coder implementation report.md
    10942  implementation/TOO-45 ticket 22 - redundancy report unsafe deletions - coder implementation report.md
    12869  implementation/TOO-45 ticket 38 fallback_kind prose-parsing fix - coder implementation report.md
    4959  implementation/TOO-45 ticket 70 punch-list item - coder implementation report.md
    3974  implementation/TOO-45 ticket 80 ambient real-tree test - coder report.md
    9433  implementation/TOO-45 ticket 81 - coder implementation report.md
    8076  implementation/TOO-45 ticket 85 chunk A - coder implementation report.md
    13095  implementation/TOO-45 ticket 85 chunk B - coder implementation report.md
    8039  implementation/TOO-45 ticket 85 chunk C - coder implementation report.md
    9810  implementation/TOO-45 ticket 85 chunk D - coder implementation report.md
    8501  implementation/TOO-45 ticket 98 chunk 3 - module boundary move - coder implementation report.md
    10208  implementation/TOO-45 ticket 99 - coder implementation report.md
    7670  implementation/TOO-8 Follow-up- Loader Deletion and Bash Takeover Coverage Implementation Report.md
    1027  toolguard-memories/implementation/Coder Latest Implementation Report.md

## C. Blinded review rounds — 29 files, 443634 bytes
    13229  TOO-45/reports/review-18-round1.md
    18639  TOO-45/reports/review-18-round2.md
    14147  TOO-45/reports/review-18-round3.md
    15823  TOO-45/reports/review-18-round4.md
    17168  TOO-45/reports/review-18-round5.md
    14873  TOO-45/reports/review-18-round6.md
    13550  TOO-45/reports/review-39-round1.md
    15184  TOO-45/reports/review-39-round2.md
    13761  TOO-45/reports/review-39-round3.md
    9742  TOO-45/reports/review-44-redrift-guard.md
    17620  TOO-45/reports/review-44-round4.md
    20893  TOO-45/reports/review-44-round5.md
    19275  TOO-45/reports/review-44-round6.md
    12719  TOO-45/reports/review-74-round1-repair.md
    11528  TOO-45/reports/review-74-round2.md
    17379  TOO-45/reports/review-77-grammar-phase1-delta.md
    16549  TOO-45/reports/review-77-grammar-phase1.md
    15654  TOO-45/reports/review-77-round1.md
    14877  TOO-45/reports/review-78-round1.md
    14612  TOO-45/reports/review-78-round2.md
    18418  TOO-45/reports/review-78-round3.md
    11916  TOO-45/reports/review-78-round4.md
    17286  TOO-45/reports/review-79-round1.md
    14659  TOO-45/reports/review-79-round2.md
    10600  TOO-45/reports/review-79-round3.md
    16021  TOO-45/reports/review-79-round4.md
    19267  TOO-45/reports/review-80-round1.md
    13637  TOO-45/reports/review-80-round2.md
    14608  TOO-45/reports/review-80-round3.md

## D. Superseded state / resume / queue snapshots — 8 files, 76364 bytes
    6086  TOO-19/TOO-19 RESUME HERE - state after Phase 0 commit.md
    12446  TOO-45/TOO-45 RESUME HERE.md
    13854  TOO-45/TOO-45 campaign resume 2026-08-13.md
    9772  TOO-45/TOO-45 phase 2 shared brief.md
    5204  TOO-45/TOO-45 punch-list 07 doc comments - coder state for recovery.md
    7424  TOO-45/TOO-45 session resume.md
    4253  TOO-45/commit-message-03.txt
    17325  TOO-45/phase-2-baseline-reds.txt

## E. Superseded rolling-pointer files — 7 files, 52920 bytes
    6732  TOO-15/latest-code-review-report.md
    9788  implementation/TOO-15 Project Root Consolidation RED State.md
    4116  implementation/TOO-45 coder-latest-implementation-report.md
    3700  implementation/TOO-45 coder-latest-task-recall.md
    13867  implementation/coder-latest-implementation-report.md
    3771  implementation/coder-latest-task-recall.md
    10946  implementation/latest-code-review-report.md.md

## F. Named one-offs — 1 file, 2838 bytes
    2838  implementation/TOO-15 P0 Keystone Implementation Task.md
---

# ADDENDUM 2026-08-23 — 102 of the 313 are GIT-TRACKED, and that changes the decision

**The whole exercise has been framed around "509 unversioned files". That framing is wrong: 222 files under `toolguard-memories/` are tracked by git**, and 102 of them sit in this delete list. For a tracked file, deleting is recoverable from history — `git checkout` brings it back. The "extract the value before it is lost forever" argument does not apply to those at all.

| section | proposed | **tracked (recoverable)** | **untracked (permanent)** |
|---|---:|---:|---:|
| A. Coder task recalls | 129 | 44 | 85 |
| B. Implementation / coder / fix / documentation reports | 139 | 50 | 89 |
| C. Blinded review rounds | 29 | **0** | **29** |
| D. Superseded state / resume / queue snapshots | 8 | 2 | 6 |
| E. Superseded rolling-pointer files | 7 | 5 | 2 |
| F. Named one-offs | 1 | 1 | 0 |
| **TOTAL** | **313** | **102** | **211** |

All 313 paths resolved on disk; none missing.

**What follows from this.**

1. **The 102 tracked deletions are low-stakes and need no further extraction review.** They will show up as ordinary git deletions requiring a commit, and are restorable indefinitely. Any residual worry about them is misplaced effort.
2. **The risk is concentrated in the 211 untracked files, and disproportionately in section C.** Every one of the 29 blinded review rounds is untracked, so all 29 are permanent losses. That is the same set the cost sweep found carries **reviewer-side cost records in 17 of 25 surviving rounds** — a category no earlier triage examined at all. Section C deserves the closest read before anything is removed.
3. **It also changes what "the corpus" means for every count in this campaign.** Statements of the form "N unversioned files" have been over-counting by up to 222, and the extraction effort was priced against the wrong denominator.

**Instrument note, recorded because it nearly went the other way.** The first attempt at this measurement regexed backticked paths across the whole document and returned 27 paths, 6 of them tracked — quietly including RESCUE rows and missing roughly 90% of the list. It produced a plausible, clean-looking number that was wrong by an order of magnitude. The figures above come from reparsing the authoritative sections A-F, which reconciles to exactly 313 with zero unresolved paths. **A total that reconciles to the expected count is the check that caught it; a percentage alone would not have.**

---

# U4 RESOLVED 2026-08-23 — basic-memory inbound relations

The delete-list author flagged as unresolved whether any proposed deletion is a basic-memory relation target whose inbound links would break. Measured against the index directly (`~/.basic-memory/memory.db`, opened read-only, project id 3 = `toolguard`, 746 indexed entities):

| quantity | value |
|---|---|
| proposed-delete paths found in the index | **313 of 313** |
| delete-set files with any inbound relation | 10 (15 edges) |
| **delete-set files linked from a note that SURVIVES** | **5 (6 edges)** |

The five that would leave a dangling link at the far end:

- `TOO-19/TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report.md` (2 edges)
- `implementation/TOO-15 P0 Keystone Implementation Report.md`
- `implementation/TOO-15 P0 Analyzers Implementation Report.md`
- `implementation/TOO-15 P2-A.1 Consolidation Core Implementation Report.md`
- `TOO-45/TOO-45 RESUME HERE.md`

**This is a small, cheap problem** — six edges. Either rescue those five, or accept six dangling references and fix the linking notes. It is not a reason to hold up the deletion.

**But note the second finding, which is operational: all 313 files are indexed.** Deleting them from disk leaves 313 stale rows in the SQLite index, which will keep answering searches with files that no longer exist. **A resync is required after any deletion**, not optional.

**Instrument note — this measurement was wrong the first time, and the wrong answer looked clean.** The first run matched `file_path LIKE 'toolguard-memories/%'` and returned **4 entity rows and zero dangling relations**. Zero was false: basic-memory stores `file_path` relative to the project root, and the project root *is* `toolguard-memories`, so paths carry no such prefix. The 4 "matches" were the nested `toolguard-memories/toolguard-memories/` files that happen to start with that literal string. **A clean null from a query that silently matched 4 of 746 rows.** The corrected run adds a control — a path known to be indexed and known not to be in the delete set — and reconciles to 313 of 313, which is what makes the result trustworthy.

---

# FINAL STATE after per-section audits of the 211 untracked files, 2026-08-23

The 102 tracked files need no audit — deletion is recoverable from git. The 211 untracked ones were audited section by section, because those are the only permanent losses. **All four audits are complete.**

| section | untracked | safe | **rescue** | uncertain | report |
|---|---:|---:|---:|---:|---|
| A. Coder task recalls | 85 | 80 | **3** | 2 (both low-value; recommendation delete) | `SECTION-A-AUDIT.md` |
| B. Implementation / reports | 89 | 78 | **9** | 2 (explicitly not verified, labelled) | `SECTION-B-AUDIT.md` |
| C. Blinded review rounds | 29 | 28 | **1** | 0 | `SECTION-C-AUDIT.md` |
| D. Superseded state / snapshots | 6 | 6 | 0 | 0 | audited inline, below |
| E. Superseded rolling pointers | 2 | 2 | 0 | 0 | audited inline, below |
| **TOTAL** | **211** | **194** | **13** | **4** | |

**Revised proposal: 300 files to delete (313 minus 13 new rescues); 30 rescued in total (17 original + 13).**

## What the 13 rescues have in common

Almost all are **a sentence that exists in exactly one place on disk**, and the audits proved uniqueness by grepping every surviving file, not by assertion. The recurring genres:

- **A decision of Arnon's that never became a ticket.** The `governed_tools` default (*"Bash only is a forgotten remnant"*) shipped in code and docs; the reasoning survives in one file.
- **A verbatim Arnon design objection** — the 130-word globals/undeclared-singleton passage, with the measured exception it anticipates.
- **An agent declaring a deviation from an explicit instruction**, with its evidence and a reversal recipe (*"Arnon's brief said 'pass it down. Not a module global.'"*).
- **A finding that is fixed but whose framing is not recorded** — e.g. *"Disclosure currently costs you your allow rule and sends the command to `ask`. That is a direct incentive against complying with CLAUDE.md."* The bug landed with ticket 77; the incentive analysis exists nowhere else.
- **An internally unsatisfiable brief** (ticket 14 residual) — a failure mode the summaries do not cover, since they cover briefs that were *false*, not briefs that could not be satisfied.

## Sections D and E, audited inline

All 8 untracked files are **safe**. Three carried flags, all resolved by checking rather than assuming: `session resume.md`'s TOO-51 finding is captured verbatim in `open-questions.md:204`; `campaign resume 2026-08-13` points at `punch-list 09 plan.md`, which survives; `commit-message-03.txt`'s "out-of-band" hit was a false positive (*injected callable* = dependency injection). The one genuine loss — a phase-resolved cost split in `implementation/TOO-45 coder-latest-implementation-report.md` — has been **transcribed into `02-campaign-cost-data.md`**, so that file may go.

## Two findings the audits produced that are not about deletion at all

1. **An agent destroyed another agent's evidence** with `rm -rf *.py` in the shared campaign scratchpad, deleting the four probe scripts a prior round cited by name. Now recorded in `01`. **The hazard is live** — that directory is still in use and still shared.
2. **The decision vocabulary is unnamed and its strictness order is triplicated** (`compound.py:55`, `replay.py:35`, `mining.py:62`). Recorded in `TOO-45/DECISIONS-PENDING.md` with a safe/risky split. Both files that recorded it are on the delete list, so it would have been lost.

## Delete mechanics — three things that must happen

1. **Resync basic-memory after deleting.** All 313 are indexed; deleting from disk leaves stale rows that keep answering searches.
2. **Five files are linked from surviving notes** (6 edges) — rescue them or accept six dangling references. See the U4 section.
3. **`toolguard-memories/toolguard-memories/` is a stray doubled-path directory** — **CORRECTED 2026-08-27, and the original description was wrong in the dangerous direction.** It does **not** hold "a 1 KB stale pointer". It holds **4 files, ~28 KB**, and **2 of them exist nowhere else in the corpus**:

| file | bytes | status |
|---|---|---|
| `implementation/Coder Latest Implementation Report.md` | 1,027 | stale copy — **differs** from the live `implementation/` counterpart |
| `implementation/Coder Latest Task Recall.md` | 6,093 | stale copy — **differs** from its counterpart |
| `TOO-45/TOO-45 ticket 104 - dicts are undeclared types - coder task recall.md` | 4,975 | **UNIQUE — no counterpart anywhere** |
| `TOO-45/TOO-45 ticket 104 - dicts are undeclared types - coder implementation report.md` | 16,092 | **UNIQUE — no counterpart anywhere** |

**Ticket 104's implementation record lives only here.** Outside the nest the corpus has `proposed-tickets/104-dicts-are-undeclared-types.md` and the two surprise-experiment files (`104-prereg.md`, `104-scored.md`) — the ticket and the prediction, but **not the coder's task recall or implementation report.** All four nested files are **untracked**, so before the 2026-08-27 backup they were one `rm -rf` from gone.

**This does not change the recommendation** — the two unique files are a coder task recall (section A) and an implementation report (section B), both categories already proposed for deletion, and both are now in the verified backup. **What it changes is the framing**: this is not "clear out an empty nest", it is "delete 21 KB of the only surviving record of ticket 104's implementation." Decide it as that.

**Why this correction matters beyond the files.** The original line is exactly the failure this campaign documents repeatedly — *a confident characterisation of what a directory contains, written without listing it*, attached to an instruction to remove it. `01`'s own record contains an agent that deleted another agent's evidence with a glob scoped to a file type rather than to what it had authored. **Before removing any directory, list it.**

---

# ADDENDUM 2026-08-27 — RE-DERIVED against the FINAL analysis set

**Why this exists.** The README makes this mandatory rather than optional: *"this list was built against **earlier drafts**, and every revision round adds citations. A file that was a safe delete when the list was written becomes load-bearing the moment a document starts quoting it — and the list cannot know that."* The analysis set has since gained documents `13`, `14`, `15`, `16` and heavy revisions to `01`, `05`, `06`, `07`, `08`, `09`, `12`. Arnon cleared the reassessment on 2026-08-27.

**The backup is verified and this changes the stakes.** `~/backup/claude/toolguard-memories-2026-08-27.tgz` — **765 files in archive = 765 on disk**, all 543 untracked covered, 35/35 blinded review rounds present, positive and negative controls both behaved. Nothing below is irreversible.

## The measurement

Every proposed deletion's filename was matched against the full text of the 26 substantive analysis documents. **The deletion-admin documents (`SECTION-*-AUDIT.md`, `README.md`, this file) were excluded** — they enumerate filenames by design and would inflate the count. That correction moved the result only from 53% to 49%, so it is not what drives it.

| section | category | cited / total |
|---|---|---|
| **A** | coder task recalls | **15 / 129** |
| **B** | implementation reports | **98 / 139** |
| **C** | blinded review rounds | **29 / 29** |
| **D** | state/resume snapshots | 6 / 6 |
| **E** | rolling pointers | 5 / 7 |
| **F** | named one-offs | 1 / 1 |
| | **total** | **154 / 311 (49%)** |

## What this does NOT mean

**It does not mean rescue 154 files.** A citation here is *provenance*, not *dependency* — and the whole purpose of the DURABLE extraction was to lift the substance out before deleting the source.

**Checked, not assumed**: sampled citations carry the quoted text inline. `06-planning-attribution.md` alone contains **14 `**Verbatim finding**` blocks**, each followed by the quotation itself. Deleting the source does not falsify the analysis; it makes the quote **uncheckable**, which is a weaker loss.

*(A first pass reported "18 bare pointers" from a line-scoped heuristic. That was an artifact — the quotes sit on the following lines. Recorded so the same heuristic is not trusted next time.)*

## The decisive point, and it comes from outside this list

**Arnon is copying the analysis set — but not the supporting evidence — into a new git repo.** So in that repo **every one of these 154 citations dangles regardless of what is deleted here.** The citation density therefore argues for making quotes self-sufficient (they already largely are), **not** for rescuing files. Keeping the evidence in *this* repo would preserve a chain that the new repo cannot use anyway.

## Recommendation — Arnon's call, stated as a proposal

| section | files | recommendation | reasoning |
|---|---|---|---|
| **A** | 129 | **delete** | **88% uncited** — the largest category and the cleanest cut. Lowest value, highest noise |
| **B** | 139 | **delete** | 73% cited, but cited as cost-table provenance and quoted findings that travel with their text |
| **C** | 29 | **delete, and this is the one to think about** | 100% cited and the highest-regret category if the backup is ever lost. Against that: 443 KB of review rounds is exactly the "noise in the git repo" being avoided, and the quotes are verbatim. **If any category is kept, keep this one** |
| **D/E/F** | 14 | **delete**, less rescues already honoured | unchanged from the original proposal |

**Net: unchanged from 300 delete / 30 rescue.** The re-derivation did not move the recommendation — but it was not free, because it is what establishes that the 49% is provenance rather than dependency. **A null that was checked, not assumed.**

## Still required before deleting

- [x] Full backup taken and **verified** (2026-08-27)
- [ ] basic-memory resynced — all 313 are indexed and stale rows keep answering searches
- [ ] The five files linked from surviving notes handled
- [ ] Disposition for `DECISIONS-PENDING-archive-2026-08-25.md` (new, untracked, no entry on this list)
- [ ] Dispositions for `13`, `14`, `15`, `16` (new since the list was written — all are DURABLE deliverables, so presumably keep)
- [ ] Remove the stray `toolguard-memories/toolguard-memories/` nest
