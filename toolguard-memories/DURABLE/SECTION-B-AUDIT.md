---
title: SECTION-B-AUDIT
type: note
permalink: toolguard/durable/section-b-audit
---

# SECTION B AUDIT — implementation / coder / fix / documentation reports

**Scope**: section B of `PROPOSED-DELETE-LIST.md`. Verified against the repo, not copied from the list: section B contains **139 files, all present on disk; 50 are git-tracked and 89 are untracked**. Only the 89 untracked ones are audited here — the tracked 50 are recoverable from git after deletion. (First attempt at the tracked/untracked split returned "0 tracked" from an `and`/`or` bug in my own script; re-run with a corrected comparison and `git ls-files -z -c core.quotepath=off` for the non-ASCII paths.)

**Method**: all 89 screened by regex battery for six marker classes (verbatim Arnon quotation, unresolved defect, cost/token/elapsed figure, out-of-band or injected instruction, implementer pushback against a brief, deliberate divergence from a documented standard). **45** produced a flagged section, whose bodies I read. **14** were deep-read at length. Every "already represented" claim below names the exact string I grepped for and where.

**One methodological correction made mid-audit**: an earlier representation check ran as `grep -rn X file TOO-45/proposed-tickets/*46*`, and zsh aborted the whole command on the failed glob — so the grep never ran and would have produced a false "not represented" verdict for `config_divergence.py`. Re-run separately, the finding turned out to be recorded three times in the surviving follow-up queue. Any negative result in this document was produced by a command that actually executed.

---

## VERDICT

| outcome | count |
|---|---|
| **SAFE to delete** | **78** |
| **RESCUE** | **9** |
| **UNCERTAIN** | **2** |
| total untracked in section B | 89 |

---

## RESCUE — 9 files

### R1. `implementation/TOO-45 punch-list 04 error reporter - coder implementation report.md`

The only file in the corpus carrying these verbatim Arnon instructions:

> Arnon reversed the scope boundary that had excluded `hook.py`'s three `main()` error handlers from this item. His words: **"fold it before commit, and there is no rational reason to keep a known defect."**

> per Arnon's explicit, specific direction in this task (**"the fail-open gets fixed here... give him the before/after plainly"**), these three were updated in place rather than left pinning a defect he commissioned removing.

Also the only record of the **"undeclared singleton" review** — Arnon's own framing that drove `error_reporter`'s module-global state into a constructible `Reporter` class — and of his instruction *not* to restructure the routing table while doing it.

**Checked**: grepped all 379 surviving files (DURABLE + everything else that outlives the deletion) for `no rational reason to keep a known defect`, `give him the before/after`, `undeclared singleton`, `Reporter class` — **zero hits outside `PROPOSED-DELETE-LIST.md` itself**. Also grepped `DURABLE/01-claude-failure-modes-and-mitigations.md`, `02-campaign-cost-data.md`, `03-out-of-band-instruction-records.md` and all ten `DURABLE/intermediate/` files.

The one technical finding in this file that is *not* at risk: the CPython exit-120 behaviour (`sys.exit(2)` after a `BrokenPipeError` is overridden to 120 by the shutdown flush) is preserved in the code at `toolguard/hook.py:169`. Cost data is preserved in `02`.

### R2. `TOO-45/TOO-45 ticket 44 ambient facts - coder implementation report.md`

A declared deviation from an explicit Arnon instruction, with evidence and a reversal recipe — the cleanest instance of that shape in section B:

> **Deviation: the facts reach their readers through a scoped binding, not through explicit threading.** Arnon's brief said **"pass it down. Not a module global."**

> **It reverses cheaply if Arnon disagrees**: delete `active` and `_active`, drop the three lines in `hook.main()`, and the accessors fall back to a live read on every call. Everything else stays.

The reasoning it gives is load-bearing and unrecorded elsewhere: explicit threading would have needed a new parameter on ~25 functions across 12 modules, including `error_log.log_crash()`, which runs from `hook.main()`'s except clauses — *"Adding a dependency to the crash path is the wrong direction."*

**Checked**: grepped the 379 survivors for `scoped binding`, `reverses cheaply`, `pass it down`, `AmbientFacts` — the first three return **zero hits anywhere**; `AmbientFacts` appears in three survivors, none of which record the deviation or the reversal.

### R3. `TOO-45/TOO-45 phase 2 unit 1 follow-up - coder report.md`

The measurement that turned into ticket 77, and the one sentence in the corpus that connects toolguard's matching semantics to this project's own compliance rules:

> **The allow-side divergence is the one Arnon predicted**, and it is worse than a nuisance: this project *mandates* `TG_INTENT=1` / `TG_ATTEST_READONLY=1` on exactly the commands where an agent has done the right thing. **Disclosure currently costs you your allow rule and sends the command to `ask`. That is a direct incentive against complying with CLAUDE.md.**

It carries the full measured allow-side and deny-side tables (`FOO=1 ls -la` → ask/None; `FOO=1 rm -rf /tmp/x` → allow via `*`, defeating `deny Bash(rm:*)`), plus four enumerated errors found in its own brief.

**Checked**: grepped the survivors for `costs you your allow`, `incentive against complying`, `TG_ATTEST_READONLY=1 ls`, `fifth location` — **zero hits**. The underlying defect *is* represented (surviving `proposed-tickets/77-...md` and `82-...md`), and **verified fixed at HEAD** — `Configuration.assignments_looked_past_when_granting` exists (`toolguard/config_types.py:718`, used at `toolguard/resolve.py:238`) and the wrapper list is in `toolguard/claude_code_contract.py:225-235`. What is unique here is the incentive framing and the measurement tables, not the bug.

### R4. `implementation/TOO-45 ticket 14 residual - takeover notice routing - coder implementation report.md`

A distinct failure mode not present anywhere else: **a brief whose two instructions could not both be satisfied**, resolved by ranking them and reporting the conflict rather than silently picking one.

> **What was wrong in the brief -- a genuine conflict, not a misreading.** The brief says (a) "do not change the function's name or signature" / "if the fix genuinely requires touching hook.py, STOP" and, separately, (b) "if [`to_stdout`] survives, rename it... leaving it misnamed is not an option." These are not simultaneously satisfiable [...] I resolved this by keeping the parameter named `to_stdout` [...] and flagging the naming defect as unresolved, rather than contorting around it. Per the brief's own framing, this is a reported conflict, not a silent compromise.

**Checked**: `DURABLE/intermediate/practices-with-evidence.md:66` catalogues briefs carrying *false claims* (ticket 98 chunk 3, ticket 74, ticket 19) — that is a different shape. Grepped survivors for `genuine conflict` (one hit, `reports/change-challenges.md`, unrelated — it is about `_takeover_conflict_logged` in a resident-process scenario) and `contradictory brief|brief contradicts itself|mutually exclusive` (two hits, neither this incident). The naming defect itself is moot: `to_stdout` no longer exists in `toolguard/session_warnings.py` at HEAD.

### R5. `TOO-45/TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md`

Carries a defect that **I verified still reproduces at HEAD** and that no surviving file records:

> **Triplicated verdict-strictness vocabulary.** `{"allow":0,"ask":1,"deny":2}` now exists independently in `toolguard/compound.py` (`_DECISION_STRICTNESS`), `toolguard/tools/replay.py` (`_STRICTNESS`), and now my new `toolguard/tools/mining.py` (`_VERDICT_STRICTNESS`). A shared constant would remove the drift risk [...]

Verified at HEAD: `toolguard/compound.py:55`, `toolguard/tools/replay.py:35`, `toolguard/tools/mining.py:62` — three independent literals.

**Checked**: `reports/follow-up-queue.md` mentions `_STRICTNESS` twice (rows about `classify_change`'s unknown-verdict default and an inverted docstring) but **never the triplication**; `DECISIONS-PENDING.md` and all DURABLE files return nothing for `_VERDICT_STRICTNESS|_DECISION_STRICTNESS`. **Cross-section warning**: the only other record is `TOO-45/TOO-45 phase 2 work unit 7 (tools-hierarchy, tools-mining) - coder task recall.md:61`, which is **also on the delete list, in section A**. Deleting both sections loses it entirely — the section-A agent should be told.

### R6. `implementation/TOO-45 punch-list 15 migrate lock - coder implementation report.md`

The corpus's clearest instance of a deferral being overturned when challenged:

> The prior fix pass explicitly deferred converting `migrate()`'s bare `int` return to an outcome type ("recorded as a follow-up, not implemented"). **Arnon asked why it was being deferred; the deferral reasoning didn't hold up**, so this pass does it, folded into punch-list #15 rather than a new ticket.

It also records the design precedent Arnon named — *"`error_reporter._ROUTING` (Arnon's own named precedent for 'one table to read, one place to change')"* — which is the justification for `MigrationOutcome.exit_code`'s lookup table.

**Checked**: grepped survivors for `deferral reasoning didn't hold|deferral reasoning did not hold` — **zero hits**. This matters because auto-memory already carries *"Count the blast radius before writing 'deferred'"*; this is the worked instance behind that instinct.

### R7. `implementation/TOO-45 ticket 99 - coder implementation report.md`

> **Declined plan item 4** (`SessionStartEvent`) with reasoning below, **per Arnon's pre-registered permission to refuse.**

A *pre-registered licence to refuse a plan item* is a delegation mechanism, and this is the record that it was granted and exercised — with the refusal recorded as a decision, not a deferral (*"resolved as a reasoned refusal above (not deferred -- decided)"*, in the sibling ticket-98-chunk-3 report).

**Checked**: grepped for `permission to refuse|licen[cs]e to refuse|reasoned refusal|Declined plan item`. `pre-registered` has 24 surviving hits but every one I inspected in `DURABLE/intermediate/practices-with-evidence.md` (lines 170, 172, 224) is about **pre-registered measurement criteria** in the surprise-factor protocol — a different mechanism. `reasoned refusal` and `Declined plan item` return **zero**.

### R8. `implementation/TOO-45 punch-list 03 stages 2+4 - coder implementation report.md`

Two things, both unrecorded elsewhere. An agent self-reporting its own breach of a project rule:

> One minor thing worth flagging for the record: an early check I ran (an unused-import/local-import scan) was an undisclosed inline `python -c`/heredoc, **a process violation of this project's own intent-disclosure convention -- caught and corrected mid-task; no repeat.**

And Arnon's scope direction on the code review that followed: *"Arnon asked for three of the findings fixed, one finding recorded in a docstring, and everything else (including the eager-matching cost, the cascade's shape, and #07's general stale-prose sweep) explicitly left alone"* — with the record of what a "record only, no design change" instruction actually produced (a paragraph in `permission_resolution.py`'s module docstring about the narrowed-not-eliminated runtime seam).

**Checked**: grepped survivors for `undisclosed inline|process violation|disclosure violation` — six hits, none an agent self-report of a breach (they are ticket 36/45/105 and the TOO-19 phrasing experiment). Notable because the disclosure rule's own measured-compliance sections in `CLAUDE.md` are built from log analysis, never from a self-report.

### R9. `TOO-45/reports/TOO-45 ticket 78 follow-up (three remaining pattern types) - coder implementation report.md`

An evidence-quality caveat about this repo's own rule set, of exactly the kind `.claude/rules/evidence-before-fixing.md` collects:

> Recounted from the live config: **190 live Bash rules; 7 name the absolute home path; all 7 are `allow`. So this configuration can only be widened, never tightened, and the deny direction is unobservable in it.**

And a refusal with its reasoning, on the project's hardest-held rule:

> **I did not suppress it, and here is the reasoning to check.** Suppressing it correctly requires knowing which bytes are quoted, which is word-level bash structure. `command_extractor` exposes leaf command *text*, not words, so the information is not available at this layer; deriving it in Python is exactly the hand-rolled parsing the project forbids.

**Checked**: `190 live Bash rules` appears in exactly three files — this one, `TOO-45/reports/TOO-45 ticket 78 tilde-expanded variant - ...` (section B, doomed) and `TOO-45/reports/review-78-round1.md` (section C, doomed, and `SECTION-C-AUDIT.md:125` records that round 1's findings were superseded, not that this measurement was transcribed). `evidence-before-fixing.md` has the adjacent *unobservable transition* lesson at line 83 but not this measurement. Its third finding — `parse_pattern`'s `.strip()` truncating a regex ending in escaped whitespace — **is** safely represented, as `TOO-45/proposed-tickets/84-strip-truncates-a-regex-body-into-a-silent-non-match.md`, which survives.

---

## SAFE — 78 files

Verified safe, not assumed. The pattern, with the check that established it in each case:

**~40 review-repair and per-ticket implementation reports** (`review-18-round{1,2,4,5}`, `review-39-round1`, `review-44-round{4,5,6}`, `review-77-round1`, `review-78-round{1,2,3}`, `review-79-round{1,2,3}` and `Review 79 round 4`, `review-80-round{1,3}`, punch-list 39 rounds 3-4, tickets 22, 32, 38, 42/47, 70, 74, 77 phase 1 and 2, 78 tilde-variant, 79 and its regression fix, 80, 81 and follow-up, 85 chunks A-D, 89, 94, 95, 96, 97, 98 chunk 3, 100, 101, 105 and phase 1, 19 P2+P3, spikes B and C, Item 95, the ambient/mocks prose passes, the suppression-store trio, punch-list 07, and the redirect-glued-tilde revert). Each follows the same shape — fix N named findings, verify with a mutation table, list what was out of scope — and each element is separately preserved:

- **Cost data**: 59 of the 89 carry a real money/elapsed figure. I matched their filenames against `DURABLE/02-campaign-cost-data.md`: **57 of 59 are named there**. The two that are not (`phase 2 follow-up unit 5 (golden adjudication)`, `phase 2 inline foreign-code ASK floor`) carry **no** cost figure — their screen hits were `awk '{print $5}'`-style false positives. Cost coverage for section B is therefore complete.
- **Out-of-band / prompt-injection incidents**: every one is transcribed verbatim, with file path and line numbers, in `DURABLE/03-out-of-band-instruction-records.md` — including `ticket 74` (lines 155-161, with the register's own note that the word *"fabricated"* overstates), `punch-list 39 round 3` (182-186) and `round 4` (194-198), `ticket 79 sub-command breakdown` (215-219), `proposed ticket 79` (204-208), `review-18-round4` (143-145) and `round5` (147-149), and `Review 79 round 4` (221-227). I read that document rather than trusting the delete list.
- **Ticket 101's stand-down** is in `DURABLE/01-claude-failure-modes-and-mitigations.md:121` — and corrected there ("*Ticket 101 stood down mid-task with zero net change shipped*" is false; commit `03d922c` shipped Item 101).
- **The ticket-79 verdict-corpus tripwire** (2 of 6,401 cases changing their `sub_matches` shape, the coder refusing to regenerate goldens and escalating) is in `DURABLE/intermediate/practices-with-evidence.md:251`, held up as the model case.
- **Spikes B and C** keep their substance in `TOO-45/spikes/B/README.md`, `spikes/C/README.md` and `spikes/CASES.md`, none of which are on the delete list.
- **"Not fixed" findings**: I extracted every such section from all 45 flagged files and checked each named defect against HEAD and against the survivors. Almost all are closed or tracked — `config-sync.md`'s `/tmp/toolguard-warnings/` fiction is gone from the doc; `permission-patterns.md`'s "up to 3 iterations" symlink claim is gone; `decision_ledger`'s import-time `Path.home()` is now `ambient.home()` at call time (`toolguard/tools/decision_ledger.py:249`); `_static_prefix_of`'s docstring was rewritten; `to_stdout` no longer exists; `judge_unit` was split (`b2c6f83`); `arr[0]=$(id)` and the stdin gap (`cat prog | python`) are documented in the code itself (`toolguard/parser/command_extractor.py:720`); `config_divergence.py:47`'s `except (json.JSONDecodeError, IOError, Exception)` is recorded **three times** in the surviving `reports/follow-up-queue.md` (rows V3, EL6, OP6).
- **One rolling-pointer artifact**: `toolguard-memories/implementation/Coder Latest Implementation Report.md` — note the doubled path segment; this is a stray nested `toolguard-memories/toolguard-memories/` directory. 1,027 bytes, a pointer to content that was returned in chat and never written. Nothing to lose.

---

## STILL OPEN — one item worth a ticket

**The verdict-strictness vocabulary exists in three independent copies.** `{"allow": 0, "ask": 1, "deny": 2}` is spelled out at `toolguard/compound.py:55` (`_DECISION_STRICTNESS`), `toolguard/tools/replay.py:35` (`_STRICTNESS`) and `toolguard/tools/mining.py:62` (`_VERDICT_STRICTNESS`).

**I verified this reproduces at HEAD** by reading the three files; I did **not** write a test or attempt a drift scenario. The reporting coder's own reason for not fixing it stands and should go in the ticket: unifying them means touching `compound.py`, the engine layer, which was outside its unit. Worth noting alongside the project's "literal strings with semantic meaning belong in constants" rule — this is that rule's most-replicated violation, and `TOO-45 decision log.md:161` records a related trap (a mutation of `_DECISION_STRICTNESS` came back MISSED because `_combine_strictest` deliberately does *not* use that ordering), so any unification has to establish which consumers genuinely share the semantics.

Two further items I did **not** verify, recorded so nobody mistakes them for checked facts:

- **`match_command` has no matcher-level test of the token boundary.** Reported twice (in the prefix-match-boundary report and again in unit 1 follow-up), with a proposed cheapest fix (`match_command("git logfoo", ["git log:*"])` assertions in `test_permissions.py`). **Not verified by me** — I did not read the test tree.
- **`tools/change_role_classifier.py`'s `--old`/`--new` and `--repo` modes silently analyse zero files for a nonexistent path**, the same gap that was fixed only for `--tree`. **Not verified by me.** Dev tooling, low stakes.

One item verified present but *deliberately documented*, so not a defect to file: `toolguard/error_log.py:90` still calls `log_dir.mkdir()` above its own `try`, so a `log_dir` that cannot be created raises into the caller — and lines 78-80 of the same docstring now say exactly that.

---

## UNCERTAIN — 2 files

### U1. `TOO-45/TOO-45 phase 2 unit 6 follow-up - coder report.md`

Carries a judgement call the coder explicitly flagged for reversal — widening the recommended `[hard_deny]` set from 22 to 24 patterns for symmetry, with the stated cost that `.env.example`, `.env.sample` and `.env.template` become write-denied for anyone who seeds it, and *"Trimming back to 22 is a two-line revert if Arnon prefers it."* The 24-pattern set shipped and `docs/security.md:637` now carries the rationale and points at the `hard_deny.allow` carve-out — so the substance is preserved. What is not preserved is that this was a coder's unilateral widening awaiting an overrule that (as far as I can tell) was never explicitly given. **Uncertain** because the docs may constitute the ratification. It also holds a row marked **NEEDS A DECISION** (absolute-spelled rule vs `~`-spelled command) whose underlying defect *is* covered by the surviving `proposed-tickets/78-an-absolute-spelled-rule-never-matches-a-tilde-spelled-command.md`.

### U2. `TOO-45/TOO-45 phase 2 work unit 9 - coder report.md`

Two flagged-not-fixed items — the `change_role_classifier` silent-zero above, and `tools/touch_set_score.py`'s `KNOWN_LIMITATIONS[0]` repeating the self-contradiction that was fixed only in the printed banner. `tools/touch_set_score.py:152` at HEAD contains the retraction text, but I could not tell from a grep whether that is the banner or the limitations entry, and I did not read enough of the file to say. `touch_set_score` and `change_role_classifier` both appear in surviving files (`proposed-tickets/06-measurement-tools-keep-or-remove.md`, `reports/pre-push-punch-list.md`, `DURABLE/intermediate/rejected-methods-and-metrics.md`), but for the keep-or-retire question, not for these two defects. **An honest "I did not check" rather than a verdict.**