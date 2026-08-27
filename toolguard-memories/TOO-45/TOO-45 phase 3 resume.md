---
title: TOO-45 phase 3 resume
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/too-45-phase-3-resume
---

# Phase 3 resume

> **READ THE LAST SECTION OF THIS FILE FIRST. Sections are appended, never rewritten, so the top is the OLDEST state and the bottom is current.**
>
> **And the authority for what remains is not this file at all — it is `TOO-45-punch-list-2026-08-20.md`**, which enumerates every open item. This file carries reasoning and corrections; the punch list carries the queue.
>
> Everything in the sections between here and the last one is superseded. Known-stale above: the errors baseline is **1950** not 1949; the suite is **3787** (with ticket 18 uncommitted) not 3760; ticket 78 is **committed** at `8867367` after five review rounds; and the queue order has changed twice since.

## Committed, nine commits on `too-45` (as of ~08:30)

`640f86b` phase 2 · `db23d17` ticket 45 · `e047bf2` ticket 44 · `6242e6d` 44 follow-up · `a2cf3f3` + `6e3fe6a` + `0f7066f` ticket 80 · `20e4964` + `1dfda8e` ticket 77 (grammar, then matcher).

Suite **3760, OK, 4 expected failures**. `ruff` clean, `--ambient` exit 0, `--layers` clean, `--mocks` exactly 1 finding (`test_session_warnings.py:159`, known and left advisory). `~/.toolguard/errors/` steady at 1949 — **that count is a leak detector; if it grows across a suite run, a test isolation seam has broken.**

## IN FLIGHT — ticket 78

Implemented and uncommitted. Round-1 blinded review **FAILED with 7 blocking**; a repair pass was running when this was written. Report: `reports/review-78-round1.md`.

**One of the seven is a code change, not prose**: `~<thisuser>` must expand (`~arnon` *is* this user's home, so `cat ~arnon/.ssh/id_rsa` currently walks past a deny rule written absolutely). `~root` correctly does not expand.

**Ticket 78's fix is deliberately one-directional** — absolute-rule-vs-tilde-command is closed for all four pattern types; the reverse is open for the extended types, recorded as ticket 83. Prose claiming symmetry is false, and four of the seven findings were exactly that.

**On resume**: check the repair landed, run the gate, run a round-2 blinded review, commit 78 on its own.

## Then

**17** (`[native]` under-matches — deny rules that do not fire), **18-remainder** (mid-pattern over-match), then batches 2–4 from `TOO-45 status 2026-08-14 - phase 2.md`.

## New tickets filed overnight — 81, 82, 83, 84

- **82 — SUPERSEDED, see the 2026-08-20 update below. Both claims in the sentence this replaced were wrong**: `sudo`/`env` are not native-stripped so toolguard is faithful there, and "the allow side must never strip" was 77's *assignment* rule imported into the wrong place. Do not act on the original wording.
- **84**: a `[regex]` deny rule ending in escaped whitespace **silently never fires** — `.strip()` leaves a dangling backslash, `re.error` is swallowed as a non-match. Prospective, zero exposure today.
- **81**: `--ambient` is module-granular for `resolve()`; carries a deferred decision (assert `findings == []` vs `fatal_findings == []`) that is **Arnon's call**.
- **83**: the tilde asymmetry's mirror image, on file paths *and* on `~`-spelled extended-type command rules.

## A correction that must not be lost

I told Arnon repeatedly that native "strips assignments for allow rules only and leaves the deny bypass open". **False.** The published doc says *"A deny or ask rule matches past any leading assignment."* Native has no such bypass; toolguard did. The two policies have the **same shape**, differing only in who owns the known-safe list. Recorded on ticket 77.

**How it survived**: a research subagent's aside four weeks ago omitted the sentence following the one it quoted, and **two blinded reviews could not catch it, because reviewers check prose against *this repository's* code and nothing re-reads external sources.** That is a standing gap in the review gate — when a claim is about a system outside the repo, fetch the source.

## Two git mechanics that each bit once

- **`git commit -- <pathspec>` silently skips untracked files.** `a2cf3f3` shipped without its new test file; a fresh checkout ran 3707 tests and passed. Recovered in `0f7066f`.
- **A plain `git commit` sweeps whatever else is staged.** `0f7066f` carried a doc deletion its message never mentions.

**So: `git add` the exact files, then `git commit -- <those same paths>`.** Belt and braces.

## Standing rules for this phase

- **Commit per ticket, and do not wait for Arnon** (he reviews diffs after the fact). Clean tree for source and tests at the start of each ticket.
- **A blinded comment review must PASS before each commit.** It has caught a code defect on every ticket so far, not just prose. Reviews now **write their report to `toolguard-memories/TOO-45/reports/review-<ticket>-round<N>.md`** and return only a summary — previously they left no trace.
- **New behaviour needs new tests.**
- **Pre-register a blinded surprise-factor estimate BEFORE implementing each ticket.** Regenerate the briefing per ticket with the builder in the session scratchpad (rebuild it if the scratchpad is gone — it has been lost twice). The estimator writes to files and returns only `DONE`. Score after the ticket is green, record **primitives** not derived metrics, in `reports/surprise/`. **Do not report intermediate results to Arnon** — aggregate at the end.
- **`.claude/rules/` and `.claude/skills/` are editable in this repo** (standing grant). `~/.claude/` global still needs a per-edit ask.
- **A repo-wide grep does NOT see `.claude/`** — symlink plus gitignore. Search it by explicit path.

## Usage discipline

Check **before** each dispatch, and **do not extrapolate between checks** — the rate is not stable. Measured 2026-08-19 evening: ~1,334k subagent tokens consumed 28% of a window, i.e. **1% ≈ 48k tokens**, so a typical implementation agent is ~3% and a large one ~5%. An earlier window that day measured ~18k per 1%. **Nearly a 3x spread between windows**, and extrapolating from the pessimistic figure nearly ended burst 1 at 28% believing it was at 78%. Running `claude-usage` costs nothing; guessing costs a burst.

- below 70%: dispatch normally
- 70–80%: small work only (a review, a targeted fix) — not a new implementation ticket
- at 80%: stop dispatching, finish what is in flight, report, wait for the reset

## What keeps going wrong, so watch for it

- **A mechanical substitution refreshes stale paragraphs**, so a recently-edited sentence is not evidence of a current one.
- **"Zero bypasses" from an instrument that cannot see one of the routes.** `expanduser` survived four rounds, `resolve` five, `absolute` six — each invisible to the instrument used to clear the previous one.
- **My own briefs are wrong at a steady rate.** Every repair pass this week found at least one false claim in mine. Tell agents the brief is unverified and to report errors in it; that instruction has paid for itself repeatedly.
---

# Update 2026-08-20 ~10:40

## Ticket 78 repair landed; round-2 blinded review in flight

Suite **3771 OK / 4 expected failures**, ruff clean, `--ambient` 0, `--layers` clean, `--mocks` 1 (known), `corpus_build --verify` no differences, `~/.toolguard/errors/` **unchanged at 1949** (no isolation leak). Blast radius: 26,530 real commands x 2 package trees, **0 decision changes, 0 matched-rule changes, 0 digest differences**. Deny direction constructed deliberately (562 commands) because this repo has no absolute-home *deny* rule to exercise.

`~<current user>` now expands via a new `AmbientFacts.user` fact from `getpass.getuser()`. **Open flag for the review**: `getpass.getuser()` reads `$USER` before passwd, paired with `Path.home()` reading `$HOME`.

**Do NOT sweep these into 78's commit** — `README.md`, `llms.txt`, `docs/config-sync.md`, `docs/install.md` are unrelated parked doc work (the "once per session" correction and an `architecture.md` link rename). 78's files are `toolguard/{ambient,normalization,permissions,path_utils}.py`, `test/unit/test_{ambient,normalization,permissions}.py`, `docs/{permission-patterns,architecture-as-built}.md`.

## Arnon set the rest of the queue

**81, 83, 84 to fix**, priority mine. Order: **78 -> 83 -> 82 -> 17 -> 84 -> 81 -> 18-remainder.** 83 after 78 and 82 after 77 are the "do it while the seam is warm" placements; the rest is cheapest-first, with 18 last so it rebases onto a settled matcher.

**Ticket 81's deferred decision is TAKEN** (not escalated): promote `resolve` to `PATH_AMBIENT_FATAL_MEMBERS` *and* keep the suite on `fatal_findings == []`. Tool and suite then agree, zero findings today, and the "the suite is stricter on purpose" failure message is unnecessary. Gap B still needs the runtime sentinel.

## TICKET 82'S PREMISE WAS WRONG — and I was the one who was wrong

Arnon challenged it: *"that's simply how claude works, no? ... I would buy your argument only on compatibility grounds. Otherwise those cases should be framed in a regex rule."* He was right.

Native's stripped wrapper list, fetched from `code.claude.com/docs/en/permissions.md`: `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, bare `xargs`. **`sudo` and `env` are not in it**, so toolguard not matching them is faithful. Both halves closed as won't-fix.

**The real defect is the opposite one**: measured **9/9 divergent** on the stripped list (toolguard strips nothing) and 11/11 agreement on the not-stripped list — right by accident, since there is no list at all. Not mainly a safety story: `allow Bash(npm test *)` under-allows `timeout 30 npm test`, the native docs' own worked example. Rescoped, and **applied symmetrically to allow and deny** — 77's allow/deny asymmetry is documented for *assignments* only and must not be imported.

**I also marked that wrong asymmetry "not to be re-derived"**, which would have carried it into the implementation unexamined. A note that forbids re-derivation had better be right.

## New standing rule, because this gap has now bitten twice in one day

`.claude/rules/native-fidelity-claims.md`, pointed at from `CLAUDE.md`. **Any claim about native's semantics must be fetched and quoted with a date.** A blinded review structurally cannot catch these: reviewers check prose against *this* repo, and native is not in it. Both failures came from a quote that stopped one sentence early — so read the sentences *around* the one you want. Round-2's brief carries the requirement explicitly.

## Surprise factor

Pre-registrations locked for **17** and **83**, both before any implementation. **17 is severely leaked** (names nearly its whole touch set with line numbers) and **83 is barely leaked** — same subsystem, same week, opposite leak levels, so they form an accidental **leak-controlled pair** that the aggregate should exploit. Cause is structural: 17 came from the citation-driven #07 sweep, 83 from a behavioural probe. Candidate tuning: score only behaviourally-derived tickets and treat citation-derived ones as unscoreable.

---

# Update 2026-08-20 ~12:40 — SUPERSEDES the ~10:40 section above

## The queue was RE-TRIAGED against field evidence, and the order changed

Arnon, 2026-08-20: *"even for the tickets that I approved to fix - before fixing any of them - spend a bit of time looking at the toolguard logs... to measure the evidence of how relevant a ticket actually is."* Procedure now standing in **`.claude/rules/evidence-before-fixing.md`**.

**Corpora**: `~/projects/flowers/featherhill/logs` (49 daily logs, 4,722 decisions — **a real user project, the one that counts**), `toolguard/logs` (51, 52,191 — dogfood), `~/projects/instagram-downloader/logs` (7, 235). **57,148 decisions total.**

| ticket | exposure | disposition |
|---|---|---|
| **18-remainder** | **752** multi-token `:*` (748 featherhill, ~1 decision in 5) | **PROMOTED from last to FIRST** |
| 82 wrappers | 106 (103 dogfood, 3 featherhill) | keep, low |
| 17 `[native]` end-anchor | **0** of 42,113 native-intent rules | **DEFERRED — Arnon to re-decide** |
| 83 | **0** — no rule is both extended-type AND tilde | **SKIPPED by Arnon** |
| 84 | **0** | **SKIPPED by Arnon** |

**Order now: 78 (in flight) -> 18 -> 82 -> 85 -> 81.** Then doc review, then the surprise-factor aggregate.

**Ticket 17's zero is structural, not accidental**: the natural rule shape is a prefix rule, `:*` **is** the trailing wildcard, and Claude Code's permission dialog emits prefix rules by construction — so the dominant rule-generating mechanism produces the immune shape every time. **But** the corpora are almost entirely *allow* decisions, and end-anchored patterns are what *deny*-rule authors hand-write. Revisit trigger: **the first deny rule that does not end in `*`**.

## A MEASUREMENT ERROR OF MINE, on the record

I first reported "38,390 end-anchored rules" in the toolguard corpus. **Wrong.** toolguard's newer log format appends a provenance suffix — `` `grep *  [project: .../toolguard_hook.toml]` `` — so the count was of rules ending in `]`. featherhill's older format has no suffix, so featherhill-derived numbers (including 18's 748) are unaffected. The wrong number was large and the right one is zero, i.e. the error pointed toward doing unnecessary work.

## `~/.toolguard/errors/` BASELINE IS NOW 1950, and the extra file is a real defect

Not a test-isolation leak. The **live** hook crashed at 11:20 with `RuntimeError: Could not determine home directory` — `hook.py:1252 -> get_env_config() -> env_config.py:185 -> path_utils.expanduser`. An agent testing with `HOME` unset hit the real hook. **Fails closed** (the catch-all emits `deny`), so no security hole, but every tool call is denied with a Python exception string, and it is logged as *unexpected*, so a misconfigured environment writes one crash report per call. **Filed as ticket 86.** The detector worked — it caught a real defect, just not the class it watches for.

## Ticket 78 status — FOUR review rounds, still uncommitted

Blocking counts: **7 -> 2 -> 3 -> 1**. Not monotone, matching ticket 45's 14->14->7->4->0.

Round 4 verified all five repair claims TRUE (dead-line removal correct, all four pattern types plus Read/Write/Edit still reached, doc counts right, new test fails under simulated revert). Suite **3771**, green 3/3, the known flake did not reproduce.

**Round 4's one blocking finding is UNREPRODUCED.** It reports `echo hi >~/.ssh/authorized_keys` allowed while the spaced form denies. With `deny = ["Bash(/home/arnon/.ssh/*)"]` + `allow = ["Bash(echo:*)"]` through `sandbox.evaluate`, **all six spellings come back `allow` via `echo:*`** — no differential. The reviewer has been asked for its exact rule set. **If the no-space form evades regardless of tilde, this is a redirect-tokenisation defect in the PEG grammar — a separate ticket under the mandatory two-phase procedure, not part of 78.**

## Corrections to carry forward

- **`except (A, B)` parens really are absent** from `patterns.py` — `raw.count(b'except (')` is **0**, `raw.count(b'except ValueError,')` is **1**. A reviewer called it a tool display artifact; it is not. Valid under **PEP 758** (Python 3.14). ruff is what strips them.
- **A subagent ran `git checkout -- <file>`** — a git write operation Arnon reserves entirely to himself. Flagged by the agent itself, not repeated. **Every dispatch from here carries an explicit prohibition on git write commands.**
- **My briefs carry a false claim at a steady rate — four consecutive, all caught by the agent, none by me.** Cause diagnosed: I forward agent reports as current state. *A report is a session delta; a review measures HEAD.* See auto-memory `feedback_agent_reports_are_deltas_not_state`. Keep the "this brief is unverified, trust the code and say so" instruction in every dispatch — it is what caught all four.

## Surprise factor

**Eleven pre-registrations locked**, one per queued ticket — 17, 18, 44, 77, 78, 80, 81, 82, 83, 84, 85. **77 and 80 are now SCORED** (`77-scored.md`, `80-scored.md`); findings and a protocol gap are in `RESULTS-LOG.md`. Do not report intermediate results.

**Ticket 85 is exempt from anti-vacuity** (Arnon): a refactor he decided on is warranted by the decision, and the diff shows whether it happened. **The `--contract` checker it may build is NOT exempt** — validate it against a deliberately planted bare literal before believing its silence.

---

# Update 2026-08-20 ~14:20 — SUPERSEDES all sections above

## Committed

**Ten commits.** Latest: `8867367` **ticket 78** (tilde-spelled command vs absolute rule). Suite **3787** with 18's uncommitted work; **3773** at `8867367`. `~/.toolguard/errors/` baseline is **1950** (not 1949 — a live-hook crash on 2026-08-20, filed as ticket 86).

## IN FLIGHT — ticket 18, repair pass after a FAIL review

Round-1 blinded review: **FAIL, 2 blocking, 9 non-blocking**. Report `reports/review-18-round1.md`.

- **B1** — the "explicit args" branch removed as dead code **was fully reachable**: `git commit:-m *`, `git push:--force *`, `rm:-rf /tmp/*`, `docker run:--privileged *`, `npm run:test`, `git commit: *` all went `True -> False`. Native-faithful, but a **silent loss of deny-rule reach** reported as a cleanup, with no test, no doc row, no release note.
- **B2** — `split_default_body`'s unconditional `body.replace("**","*")` corrupts `**/secrets/**` -> `*/secrets/*`; `match_command` handles that shape *before* normalising, so `consolidate.py:641` gets tokens that do not name the pattern.
- **9 of 14 new tests pass with the production change reverted**, including the headline differential — its 12 patterns all end in `:*`, the one shape this change leaves alone.

## THE INSTRUMENT FINDING — read this before quoting any replay

**A verdict-only corpus replay cannot see a rule going from not-matching to matching** when the fallback already permits. This repo sets `no_match_fallback = "allow_with_no_warnings"` (`.claude/toolguard_hook.toml:4`, TEMPORARY pending **TOO-28**). Measured instance: `Bash(\obsidian search:context *)` matched nothing at HEAD and matches now.

**Arnon's fix, and it is better than mine**: re-score the corpus **as if the fallback were `ask`** — a no-match then scores `ask` and a newly-matching rule shows a real `ask -> allow` flip. Provenance already distinguishes the two; the log writes `[fallback allow -- no rule matched]`.

**Measured scope — much narrower than first feared:** featherhill **0 fallbacks in 3,675 (0%)**; toolguard **9,848 of 51,918 (19%)**; instagram 0. **featherhill-based evidence was never masked.** Ticket 78's replay compared `matched_rule` and is sound. Ticket 18's was verdict-only over toolguard's logs and is not.

Full analysis: `reports/replay-instrument-blind-spot.md`. Rule updated: `.claude/rules/evidence-before-fixing.md`.

## THE PUNCH LIST IS THE AUTHORITY — `TOO-45-punch-list-2026-08-20.md`

**Enumerated, not pointed at.** I lost 23 of 28 tickets across a compaction by writing *"then batches 2-4 from <file>"*; see auto-memory `feedback_punch_lists_must_enumerate`.

**Order**: 18 (finishing) -> `--stdlib` -> **74** and **39** (the fail-open pair) -> 79 -> 19 -> 20 -> 22 -> 64 -> 70 -> 82 -> 38/42/47/52 -> 85 -> 81 -> 32 -> 07/11/14/16 -> wrap-up. **~64h remaining.**

**Scopes were re-derived from each ticket's `PARTIALLY FIXED` amendment**, not its body — the error that cost ticket 18. Notably: **20 is prose-fixed and behaviour-unchanged** (sections 1-4 all reproduce); **39 is a `deny`->`allow` rewrite that still writes successfully**; **52, 57, 14, 11, 16 total ~4h**, mostly closed by phase 2.

## Skipped / deferred, with reasons

**Skipped**: 83, 84 (Arnon), 87 (`&>` etc, 0 occurrences), 21 (its featherhill "blanket allow" was toolguard's own dev traffic on 2 of 49 days), 34 (98, all dogfood), 36 (652 of 657 are our own disclosure comments), advisory tooling 37/53/56/61/62/66/72/75. **Dead**: 40, dies with JSON retirement under **TOO-67**.

**Deferred pending Arnon**: **17** — 0 exposure across 42,113 native-intent rules; immunity is structural. Revisit trigger: **the first deny rule not ending in `*`**.

## Standing corrections

- **Read a ticket's amendment, not its body.** I measured 748 occurrences for ticket 18's *already-fixed* defect and promoted it to first on that number.
- **My briefs carry a false claim at a steady rate** — seven consecutive, every one caught by the agent. Keep the "this brief is unverified, trust the code" instruction in every dispatch.
- **A subagent ran `git checkout --`.** Every dispatch now forbids git write commands explicitly.
- **`except (A, B)` parens really are absent** from several files — verified at byte level, valid under PEP 758, `requires-python = ">=3.14"`. Not a display artifact.

---

# Update 2026-08-20 ~18:30 — SUPERSEDES all sections above

## Committed: twelve

Latest three: `8867367` ticket 78 · `c5e50a5` **ticket 18** · `1deb328` **`--stdlib` check**. Suite **3800** (with 74 uncommitted); baseline before 74 was 3798. `~/.toolguard/errors/` steady at **1950**.

## IN FLIGHT

- **74** — implemented, in blinded review. 3 files, 213/45. Narrow scope.
- **39** — blinded estimate **locked**; implementation waits for 74 to commit.

## Ticket 18 closed at ~11h / 6 rounds. The lessons are the deliverable.

Two new controls, both now standing in `TOO-45-punch-list-2026-08-20.md`:

1. **A high estimate is a DESIGN problem, not a prediction** (Arnon). Agent time is cheap; his review time is scarce, and a large diff cannot be reviewed well. Decompose before starting *whether or not the estimate is accurate*; work that resists decomposition is evidence the ticket or approach is wrong. **85 was split into 4 reviewable chunks on this basis.**
2. **The round-curve control.** 45/44/78 all ran 14->…->0, 12->…->1, 7->…->2 — high then draining. **18 ran 2->2->1->3->3->2: it opened with the FEWEST findings of any ticket and never converged.** A flat-low curve means each round is finding problems the previous repair introduced. **Two running checks: does the blocking count fail to fall across two consecutive rounds? and are the findings still in the code?** Both fired at 18's round 3; acting on either would have saved ~6h.

Also: **the `curl` recipe was split out (ticket 88) and the `\b` TOML fail-open filed (ticket 89).** `"[regex]\bcurl\b"` parses to `\x08curl\x08` with **no error** and the deny goes inert — and it is the shape our own security-audit skill recommends. Invalid escapes (`\s`) fail LOUDLY; valid ones (`\b`, `\f`, `\r`, `\n`, `\t`) fail SILENTLY and open.

## Ticket 39's scope is MEASURED, not inferred

`hard_deny.deny -> permissions.allow` is **REFUSED**; `permissions.deny -> permissions.allow` and `permissions.ask -> permissions.allow` both **WRITE OK**. The guard already computes `_hard_deny_patterns(original) - _hard_deny_patterns(new)` and has no equivalent one tier down. **Narrow fix, no matcher, no layer inversion.** Watch: step 3 is guarded by `if path.exists()` and tolerates an unparseable original — **a rewrite of a currently-broken config must still be allowed**, or the guard makes a corrupted file unfixable.

## My briefs — the failure is now precisely characterised

**Ten of eleven contained a false claim.** One cause, three faces: forwarding an implementer's *session delta* as HEAD; forwarding a *ticket body* as current state; and **writing probes against APIs I had not read** (three today — a `deny`+`allow` pair that cannot override, a TOML config that silently did not load, and `verify_config_text` when the logic is in `verified_write_config`).

The 74 brief claimed a RED test existed; **it was green at HEAD**, already fixed by `640f86b`, and the live defect was in `_handle_command_tool` — a different function, on `main()`'s path — which the ticket did not name. The agent also found **`main()` carries its own independent copy of the governed-tools check.**

**Fixes now in force**: quote `git diff --stat` in briefs rather than prose; read a signature before writing a probe; and keep the "this brief is unverified, trust the code" instruction, which has caught every one.

## Queue

**39 -> 79 -> 19 (P2/P3 only) -> 20 -> 22 -> 57 -> 64 -> 70 -> 82 -> 38/42/47/52 -> 85 (x4 chunks) -> 81 -> 32 -> remainders -> wrap-up (x3).** ~90h on the recalibrated ~6h/ticket average. **The punch list is the authority**, not this file.

---

# Update 2026-08-20 ~22:40 — SUPERSEDES all above

## Fifteen commits

Since the last update: `982e550` (nine stale `RED:` annotations removed) · `c335e22` **ticket 74** · `7d0646d` **ticket 39**. Suite **3826**, `~/.toolguard/errors/` steady at **1950**.

## IN FLIGHT — ticket 79

ASK floor inside `$(...)` and backticks. Implemented; **the suite has 2 failures and that is the current state.**

The floor fix is correct — grammar already parsed substitutions recursively (verified by reading the `.peg`, so **ticket 77's precedent repeated**: no two-phase needed), backticks and 3-level nesting compose for free, `echo $(ls -la)` correctly unfloored, and **exactly 2 of 26,425 real commands newly ask** rather than the 981 that merely contain a substitution.

**But it dropped entries from the compound sub-command breakdown** — two verdict-corpus cases lost inner commands from `sub_matches` while verdicts stayed identical. That trips a HARD invariant (`test/verdict_corpus/README.md:41`: *"ANY change is a test failure, full stop, and is NEVER 'fixed' by regenerating a goldens file"*).

**This is the campaign's founding defect in miniature** — the floor now fires on content inside a substitution while the log stops recording that content. The founding incident was 1,943 sub-commands reaching the audit trail with no record. **Invisible to a decision-level replay**: every verdict was unchanged.

Repair in flight. **Do not regenerate goldens; do not set the acknowledgement env var.** The floor decision stays in `_apply_leaf_policy` (one authority); `sub_matches` must regain inner entries where it is actually built. A first attempt adding them as top-level leaves duplicated `compound.decompose` and broke 4 tests — do not retry that.

## Tickets measured, not inferred — three changed disposition

- **57 — CLOSED, no production work.** Its one red item was already fixed; the other two "holes" needed no code change (behaviour already correct, only detection missing, now test-guarded). **Was queued at ~1h.** Third instance of cause `I`.
- **64** — `record_decision` is a read-modify-write with **no lock and no atomic replace**; the module imports neither. **Both primitives already exist** (`file_lock.py` from item 15, `_atomic_write` in the config guard). Adoption, not design. Do not copy `migrate()`'s `LockUnavailable` collapsing — ticket 32 records it as defective.
- **70 — outranks its title.** The safety-floor half is fixed. What remains: `edit_proposal.py` stores the change twice — `RuleEdit` (applied) versus `EditProposal.tool/action/rationale` (displayed) — free to diverge. Measured: a caption reading *"tighten Bash"* enacted a **`Read` broadening to `/**`**. Fix by deriving the caption, not by testing the duplication.

## A CONTAMINATION ROUTE I CREATED

**Measuring a ticket before briefing it is this campaign's best habit — and I was appending the measurements to the ticket files, which are the estimator's only permitted reading.** Ticket 39's estimator predicted the scope correctly by quoting my own appendix back.

**Affected: 20, 39, 57, 64, 70.** Plus return-channel leaks on **05** and **19**. The aggregate must report a partially-blinded series with named exceptions, not a controlled experiment. **Fix next series**: measurements go in a coordinator-only file; the estimator gets the ticket *as filed* plus the inventory.

## Scored so far

44, 77, 78, 80, 18, 74, 39. **74 was the first perfect touch set** (100% by lines, 0 surprises) and the first correct *unleaked* prediction — it called the scope by reading what the ticket **excluded**. **39 was 99.1% by lines** with a 7-line comment-only surprise; that is the case line-weighting exists for, since by file count it reads as 67%.

---

# Update 2026-08-21 ~01:20 — SUPERSEDES all above

## Still fifteen commits. Ticket 79 is uncommitted and on its FOURTH review round.

Suite **3839**, 0 failures, 4 expected. `corpus_build --verify` clean. `~/.toolguard/errors/` **1950**.

## Ticket 79's arc — nine agent runs, ~2.6M subagent tokens, for 2 commands newly asking out of ~26,400

**The gain is real and small**: foreign inline code inside `$(...)`/backticks now raises the ASK floor. The grammar already parsed substitutions recursively (verified by reading the `.peg`) — **ticket 77's precedent, third confirmation**: expect Python, not grammar.

**Three weakenings were introduced and caught before commit**, each by a different instrument:

1. inner commands vanished from the audit breakdown — caught by the corpus HARD invariant, invisible to a verdict-level replay
2. **`deny` -> `ask`** — an unoverridable `hard_deny` downgraded when foreign code shared the line
3. **`ask` -> `allow`** — an explicit ask lost, because `judge_unit` promoted only `deny`

**Root cause of 2 and 3 was one thing**: a hand-rolled resolution running parallel to the project's strictest-wins machinery. Fixed by extracting `_pick_strictest` and routing both `_combine_strictest` and the `inline_code` branch through it. **Round 3 then failed to construct a fourth**: 19 shapes x 4 fallback settings, no decision-level weakening.

**Round curve 5 -> 4 -> 3**, with severity falling faster than count.

### The causal chain worth remembering

The floor fix alone was small and correct — `command_extractor.py` only. **Raising the floor reclassifies a leaf from `kind='plain'` to `kind='inline_code'`, and `kind` also drives decomposition**, so the audit breakdown collapsed. Restoring it meant touching `sub_matches`, which verdict derivation also reads. Everything followed from that one coupling. **Option never priced: mark the leaf floored via a separate flag, leaving `kind` alone** — recorded in `measurements/79-cost-assessment.md`.

## I regenerated `goldens.jsonl` — 2 lines, reviewed, and half my justification was wrong

HARD tiers passed (`test_no_verdict_changed`, `test_no_sub_command_breakdown_changed`), the failing tier was TRACKED prose, and `README.md:65` documents regeneration as the remediation *"after reviewing the diff once the change is confirmed intentional."*

Decisive check: **`hook.py:534` logs one entry per `verdict.sub_matches` and reads it structurally**, so simplified prose costs no audit detail — the founding fix paying off directly.

**But my claim that the new output is "clean" was half false.** Line 1107 went 4/5 -> 3/3 brackets (fixed); **line 2807 went 14/16 -> 11/12 and is still unbalanced**, because `_combine_strictest` still re-parses a `'plain'` unit's own rendered summary via `r.split(" -> ", 1)[-1]`. The fix **masks** the re-parse for `inline_code`; it does not remove it. **Filed as proposed ticket 90.** Backup of the pre-regeneration goldens is in the session scratchpad.

## A pattern that fired three times on this one ticket

**Every time a new category of verdict was added, something enumerating the old categories silently stopped covering everything.** The fabrication guard twice, and the `no_match_fallback` WARNING once (`judge_unit`'s `warned` any() excluded `deny_check_verdicts`). Round 4 is specifically hunting a fourth.

## Contamination fix APPLIED, not deferred

Coordinator measurements now go in **`toolguard-memories/TOO-45/measurements/`**, keyed by ticket — **not** appended to ticket files, which are an estimator's only permitted reading. First use: `22.md`. See that directory's README for why. Already-contaminated: 20, 39, 57, 64, 70 (appendix) and 05, 19 (return channel).

## Next

**19** — implementation, no estimator step (its measurement is void). Scope is **P2/P3 only**; P4 and P5 skipped on measured evidence (1 and 0 occurrences in 58,096 commands). Hypothesis recorded in `reports/surprise/19-prereg.md`: `_classify_pipeline_sink` segments on `|` only while the grammar already knows `&&`, `||`, `;` — **the third instance of "the grammar already knows, the Python discards it"** if it holds.

---

# STATE AT 2026-08-21 — 79 COMMITTED, 19 IN FLIGHT, 20 DECOMPOSED

**This is now the last section. The punch list remains the authority for what remains.**

## Committed

`5124795` — **ticket 79** (foreign code inside `$(...)` raises the ASK floor). Sixteen commits on `too-45`. Suite 3840, corpus verify clean, all fitness checks pass.

Final round found a **fourth** instance of the enumerate-by-hand pattern, exactly where round 4 was told to hunt. Fixed by extracting one authority, `all_parts = (stub, *audit_part_verdicts, *deny_check_verdicts)`, consumed by `_pick_strictest`, the context accumulation and the `warned` check. **`reason` is a deliberate non-consumer** — the implementer verified in code that `_combine_inline_code_reason` only ever folded stub+audit_parts, and correctly **refused my brief's claim** that it needed the same treatment. Round curve **5 -> 4 -> 3 -> 1**. Ticket **91** filed (substitution body still matched as one leaf).

## 79 scored — `79-scored.md`, findings 13-15 in RESULTS-LOG

- **15.2% line-weighted recall, the series' worst, on its most expensive ticket.** Not two facts: one coupling (`kind` drives both the floor and audit decomposition) produced 79% of the diff *and* the eleven agent runs. **Low recall may be a leading indicator of cost** — test at the aggregate.
- **The uncertainties file beat the predictions file.** The estimator named `compound.py` and the exact governing question, said it could not resolve it under blinding, then predicted against it. Proposed: **treat a flagged high-leverage uncertainty as the estimate** — the coordinator is not blinded and can resolve it in seconds.
- `P` (prose coupling) recurred a **third** consecutive time. No estimator has yet predicted the right doc file.

## In flight

**19** — `feature-coder`, scope **P2/P3 only**. Measured at HEAD before dispatch: **P1 confirmed fixed**; P2-P5 all still reproduce. **P2 is wider than filed** — the ticket names `&&`; `;` and `||` bypass identically. No `.peg` change (this code deliberately runs *before* the grammar, because heredoc bodies must be lifted out first). Brief also requires correcting `multiline.py`'s module docstring, which currently **denies** containing hand-rolled parsing while containing it, and the `_classify_pipeline_sink` docstring that **documents the bypass as expected behaviour**.

## Ticket 20 — DECOMPOSED, design decided, estimator sealed

Split into **20a** (safety gates), **20b** (static-subsumption soundness), **20c/RA1** (approval-surface diff — flagged for Arnon, candidate defer). Order 20a then 20b; 20a's corpus wiring changes what 20b observes.

**Measured before splitting:** both `_check_family1_safe` and `_check_family2_safe` return `True` with **no corpus**; family 1 checks `broadened or tightened`, family 2 checks **only broadened**. So the shared defect is *safe-when-unverifiable*, and the missing tightening check is family-2-only. The ticket's amendment is partly wrong: `broadened_count` **does** classify `ask -> allow` correctly — the hole is coverage, not classification.

**Design decision taken, not asked** (ticket says *"decide, do not patch"*): **three-state `safe` / `unsafe` / `unverified`**, as named constants, applied to both gates. Refusing without a corpus would break `toolguard-maintain` on a fresh install; keeping the boolean leaves the defect. Flagged for Arnon, reversible.

Estimator ran and returned **exactly `DONE`** — first clean return channel after 05 and 19 leaked. Both files written and **unread**; scoring basis locked in `20-prereg.md` as the **union of 20a+20b**, with 20c as cause `X`. Brief for 20a is written at `scratchpad/brief-20a.md`.

## Two methodology findings recorded this session

1. **The dogfood corpus inflates evidence for the defects being investigated.** Ticket 19's P4 measured 10 hits against an earlier "measured zero"; printing the lines showed nearly all were this campaign's own probes, logged because toolguard governs this repo. featherhill is immune. Rule updated (`.claude/rules/evidence-before-fixing.md`): **at counts under ~50, print the lines — never report the count alone**, and prefer the earliest measurement taken before work began. The original zero was right; P4/P5 stay skipped.
2. **Ticket 22 §5 is the same defect as 20a, not an analogy.** Its corpus-redundancy finding cannot distinguish *"proven covered"* from *"never exercised"*. **22 must reuse 20a's states, not invent a parallel set.** Recorded in `measurements/22.md`.

## Next, in order

**19** lands -> commit -> dispatch **20a** (brief ready) -> **20b** -> **22** -> 64 -> 70 -> 82 -> 38/42/47/52 -> 85 (4 chunks) -> 81 -> 32 -> remainders (07 test tier, 11, 14, 16) -> wrap-up.

## Still awaiting Arnon

Ticket **17** re-decision (deferred, zero exposure); ticket **57** closure confirmation; **20c** defer-or-do; **20a**'s three-state choice; whether 39's `deny`->`ask` exemption should be folded differently.

---

# STATE AT 2026-08-21 (later) — 19 COMMITTED, 20a IN FLIGHT

**This is now the last section.** Punch list remains the authority for what remains.

## Committed

`2e53d42` — **ticket 19** (a heredoc is classified by the statement it belongs to). **Seventeen commits** on `too-45`. 3854 tests, corpus verify clean, two goldens (sentinel-label corrections only, verdicts byte-identical).

Final HEAD-vs-tree comparison, properly isolated: the **only** differences are gains — `&&`, `&`, `;` gain the ASK floor; F1's substitution shapes match HEAD exactly; quoted `"$(a; b)"`, pipe data-flow, bash bodies and the bare control are identical. No weakening.

**Scope delivered**: P2 (all four separators — the ticket named only `&&`) and P3. **Deferred, each measured pre-existing**: `_split_on_unquoted_pipe`'s substitution blindness (wider blast radius — governs every heredoc sink classification); P4; P5. **Ticket 92 filed** for a foreign heredoc piped to a shell keeping no floor.

**The distinction worth keeping**, from the implementer overruling my brief: `|` is **data-flow**, so "last segment wins" is right for it; `&&`/`||`/`;`/`&` are **control-flow**, where clauses are independent. My suggested fix would have broken `python3 - <<HD 2>/dev/null || true`, which is real traffic. Also: the grammar's `control_op` has **four** alternatives and the hand-rolled scanner had three — the scanner now mirrors it and says so.

## My two process failures on this ticket — both caught by others, neither by a gate

1. **Broken isolation instrument.** I refuted the review's F1 regression finding by comparing HEAD against the working tree — but the comparison script lived outside the tree under test, so `sys.path[0]` pointed at the script's directory and **both runs imported the working tree.** My "validation" used `python -c` (cwd on path), a different invocation from the script-file measurement. Clean symmetric null, read as proof. **Fix, now standard: pin `PYTHONPATH` and print `module.__file__` inside the run that produces the numbers.** In `.claude/rules/evidence-before-fixing.md` and auto-memory.
2. **Scope change over a side channel.** I sent the correction to the running agent, bundling a verifiable fact with an unverifiable scope expansion. It refused. **Rule: fact corrections may be sent mid-task; scope changes need a new brief.** In the punch list.

## Three agents refused out-of-band instructions — preserve this

Across 19's rounds: a scope expansion outside the brief (mine); an auto-mode directive conflicting with the agent's system prompt; and **a message claiming a file was externally modified and telling the agent to conceal it from me** — false, and the agent said so. Tree verified clean independently. **Each separated "is this true" (checked it) from "am I authorised" (referred up).** Flagged to Arnon; source unknown.

## In flight

**20a** — consolidation safety gates. Three-state `safe`/`unsafe`/`unverified` across **both** gate functions, family 2 gains `tightened_count`, corpus wired into `propose_consolidations`. Brief requires **mutation-verifying every test**, because the module's 38 tests cannot currently detect the gate being stubbed to always pass.

## Measurement state

- **19 EXCLUDED** from the touch-set series (estimator leaked; declared void pre-implementation). Recorded in RESULTS-LOG, not skipped.
- **20** estimator sealed and unread; scoring basis locked as the **union of 20a+20b**, 20c as cause `X`.
- **22 prereg written** — three falsifiable predictions, chiefly *does HR2 get a reworded string or a structured fact?* A diff confined to `hierarchy.py`+`redundancy.py` means the cheap fix was taken.
- **82** measured against fetched native docs (2026-08-21): toolguard strips **none** of native's nine wrappers (restrictive divergence, zero field basis), **and** a second unimplemented mechanism found — native bars `watch`/`setsid`/`ionice`/`flock` and `find -exec`/`-delete` from prefix auto-approval, where toolguard allows `find . -delete` under `Bash(find *)`. Permissive divergence on a destructive command, but needs a rule shape absent from every corpus. **Recommend filing separately, not widening 82.**

## Usage, measured

Session **7%**, week **19%**. Nowhere near a threshold.

## Next

20a lands -> commit -> **20b** -> **22** -> 64 -> 70 -> 82 -> 38/42/47/52 -> 85 (4 chunks) -> 81 -> 32 -> remainders -> wrap-up.

## Awaiting Arnon

17 re-decision; 57 closure; **20c** defer-or-do; 20a's three-state choice; 39's `deny`->`ask` exemption; **the exec-wrapper bar as its own ticket**; and the out-of-band-instruction observation above.

---

# STATE AT 2026-08-21 (later still) — 19, 20a, 20b COMMITTED; 22 IN FLIGHT

**This is now the last section.** Punch list remains the authority.

## Committed — nineteen on `too-45`

- `2e53d42` **ticket 19** — a heredoc is classified by the statement it belongs to
- `bf87629` **ticket 20a** — a consolidation says whether it was actually verified
- `44845c8` **ticket 20b** — static subsumption stops asserting what it never checked

3875 tests, corpus verify clean, all fitness checks pass, `~/.toolguard/errors/` steady at 1950.

## Ticket 20 SCORED — `20-scored.md`, findings 19-21

**95.0% line-weighted recall — the series' best** (89.3% discounting two wrong-reason hits). Contrast ticket 79 at 15.2%, the worst.

**The finding that reframes the whole experiment**: leak level predicts recall, monotone across three points — 79 (extractor only) 15.2%, 18 (files with line numbers, defect site only) 52%, 20 (nearly every file named by function) 95.0%. **The measure tracks transcription far more than foresight; the aggregate must LEAD with leak-discounted recall.**

Also: a hit for the wrong reason is not a hit and the metric cannot tell (`rule_apply.py`, 55 lines, predicted for RA1 which was descoped, touched for rendering instead) — visible only because the estimator records a reason per row. And both misses were **review-driven**, not code-driven: `edit_proposal.py` was touched because the review found the three-state never reached the operator. No estimator could predict that.

## What 20a/20b actually changed

`SafetyResult` (`SAFE`/`UNSAFE`/`UNVERIFIED`) across both gates; family 2 gained `tightened_count`; corpus wired into `propose_consolidations`; **the state now reaches the operator** — `[UNVERIFIED]` in the default `--apply` preview and in JSON `edit_proposals` — and the `--apply` help no longer claims "replay-verified". `_static_prefix_of` no longer treats `/` as a boundary and now requires the covering candidate's `args_part == "*"`.

**Two ticket sections were already closed**: §1 was never an automatic escalation (it comes from the broadening half, documented as gating nothing and never auto-applying), and its false docstring was fixed earlier including the test copy its amendment claims survives.

**The broadening dispute, resolved**: the docstring's *"a pure removal can never broaden"* is FALSE, but not for the reason anyone gave. `ask -> allow` by removal genuinely cannot happen; **an emptied allow list leaves the fallback path for a "no rules configured" branch that yields `ask`, and `replay.py:10` classifies `deny -> ask` as broadening.** Reviewer right on the verdict, implementer right on the example, ticket right about the mechanism it named. **When two careful parties disagree about whether X can happen, ask what path nobody has described.**

## Filed this stretch

- **92** — foreign heredoc piped to a shell keeps no ASK floor (pre-existing)
- **93** — corpus replay runs once per candidate; 0.03s -> 2.20s at 500 entries against a real corpus of 61,208, which pushes users onto the `UNVERIFIED` path

## Measured ahead of their turn (coordinator-only, in `measurements/`)

- **64** — `file_lock` has exactly ONE adopter (`migrate()`); `config_write_guard` takes no lock, so **a lock only one writer takes is not a lock**. Also two atomic-write implementations. Verify lock *identity* before implementing.
- **70** — both open defects reproduce. **20a added a `verification` field to `EditProposal`, enlarging the very caption surface 70 is about** — sequence 70 after 20a and tell the implementer why `verification` is a different kind of field.
- **32 item 1** — HALF fixed: `migrate()`'s prose branches on the reason, but the enum still collapses four `LockUnavailable` reasons, so `auto_migrate` still announces a false cause **and burns the day's claim**. On a platform with no advisory-lock primitive that is a **permanent silent disable**. Earns its "fix before push".
- **32 item 2** — **defer candidate**: the defect is real but its justification is false. `log_warning`/`log_error` have **four** static callers in `hook.py`, not zero. One missing call-graph edge, not an invisible mechanism.

## In flight

**22** — HR2/RD1/RD2. Brief deliberately presents prose-vs-structure **neutrally** so it does not bias the pre-registered prediction (mine: a correct fix is structural and reaches `maintenance.py`; a diff confined to `hierarchy.py`+`redundancy.py` means the cheap fix was taken). **22 is the series' first fully-clean estimator run** — no coordinator appendix in the ticket, and the return channel held on substance.

## Next

22 lands -> commit + score -> 64 -> 70 -> 82 -> 38/42/47/52 -> 85 (4 chunks) -> 81 -> 32 -> remainders -> wrap-up.

## Awaiting Arnon

17 re-decision; 57 closure; **20c** defer-or-do; 20a's three-state choice; 39's `deny`->`ask`; the **exec-wrapper bar** as its own ticket; **32 item 2 demotion**; ticket 70's **AE2 design decision** (*"half a narrowing is a broadening"*, currently pinned as characterization); and the **out-of-band instruction reports** — four agents now, concealment the recurring theme, tree verified clean each time.

---

# FINAL STATE, 2026-08-21 — 38 commits, queue exhausted, three decisions open

**This is the last section.**

## Committed since the previous entry

`931ab12` rename `to_stdout` -> `enabled` · `b9e8592` item 96 · `dd59c24` item 94 · plus 85a-d, 81, 14, 42, 52, 82, 32.1, 38, and the 07 test tier.

**38 commits on `too-45`.** Suite **3966**, corpus verify clean, ruff clean, `--ambient --layers --stdlib` all PASS, `~/.toolguard/errors/` steady at **1950** throughout. Version **0.6.0**, release notes written.

## Wrap-up complete

Doc review pending (user-invoked). Coverage measured — the new contract module is 100%. `pyscn` read and dispositioned **per item** with the recommendation to exclude canopy-generated `bash_parser.py` from the complexity metric (28 of its 39 offenders). Duplication measured **down to named fragments**, which changed the conclusion three times. Consolidated surprise report written, then amended with the source-only cut and Arnon's decision.

## Open — ALL need Arnon, none are blocked on work

1. **Ticket 98 — pick a spike.** Three built, all 16/16, all verified independently by the coordinator, in `scratchpad/spikes/{A,B,C}/`. **Case 17 (`if true; then cat <<HD`) is the one that separated them**: shipped, A and B all answer `then` confidently; only **C** answers `<unresolved>`. Recommendation **C**, on failure mode rather than size.
2. **Ticket 97 — approve the plan.** Diagnosis corrected during planning: `audits_as_one` already exists and `resolve.py` already prefers it; the collapse is only at construction. Four steps, the first small and carrying the safety-relevant change.
3. **Ticket 95 — HELD deliberately.** Approved by Arnon, not dispatched: `judge_unit`'s branches **are** the `kind` cases, and 97 step 3 moves that seam. Doing 95 first cuts `compound.py` twice.

Then: `/documentation-review`, the push, and afterwards `uv tool upgrade toolguard` **plus the smoke test** — a hook that cannot launch fails SILENTLY, since Claude Code treats only exit code 2 as blocking.

## Tickets filed during phase 3, still open

**88** (deny-with-exception recipe), **89** (word-boundary regex in double-quoted TOML), **90** (prose re-parse for `plain` units — Arnon: skip), **91** (substitution body as one leaf — no genuine field evidence), **92** (heredoc piped to a shell — **both spikes fix this**), **93** (corpus replay per candidate — Arnon filed TOO-68), **95**, **97**, **98**.

## The experiment's own state

Arnon's decisions, recorded in the consolidated report: **continue until at least 20 human-authored tickets** have gone through the normal process (plan first, reviewed, then implement), and **switch the headline metric to production files only**. Two-estimate protocol agreed — a **raw** estimate against the ticket and an **informed** estimate against the plan, with the 2x2 between them as the actual instrument, and tickets killed at plan stage counted as a headline rather than as missing data.

---

# STATE AT 2026-08-21 (evening) — 46 COMMITS, 98 CHUNK 2 IN FLIGHT

**This is now the last section.** Supersedes "FINAL STATE, 2026-08-21 — 38 commits".

## Committed since the previous entry — eight

`f8c373a` 98 chunk 1 (blind heredoc lift behind an unforgeable placeholder) · `f816fea` docs: hard_deny carve-outs + TOML literal-string trap + 0.6.0 lock · `f11ba43` 97 step 3 · `b2c6f83` 95 (judge_unit 20 → 8, four per-kind judges) · `4d62339` 99 items 1+3 (PreToolUseEvent/PreToolUseResponse; key imports hook 12→6, sandbox 4→1) · `52be738` 89 (inert `[regex]` warning) · `2648423` 88 (find replaces curl; enumerability rule published)

## In flight

**98 chunk 2** — AST attribution. Verified read-only from the working tree at 16:42: both hand-rolled scanners (`_statement_bounds_containing`, `_split_on_unquoted_pipe`) are **gone**; case 15 `allow`, case 16 `ask` with the body no longer leaking as a leaf, case 17 `ask` **even under a blanket `allow = ["Bash(*)"]`**. All three targets met and the unresolved policy is correct. Not yet committed; agent still verifying.

## OWED BEFORE ANY PUSH — do not skip

- [ ] **Full suite + `corpus_build.py --verify` clean.** Neither has run clean since 98 chunk 2 started; 89 and 99 were committed on independently-verified attribution, not on a green corpus. **Corpus goldens WILL need regenerating** for chunk 2's three corrected cases — every diff must be named before regenerating.
- [ ] `/documentation-review` (user-invoked) — `docs/agent-guides.md`, `docs/configuration.md`, `docs/security.md` all changed.
- [ ] `uv run python tools/architecture_fitness.py --stdlib --ambient --layers`
- [ ] After push: `uv tool upgrade toolguard` **plus the smoke test** — a hook that cannot launch fails SILENTLY.

## NEEDS ARNON — none blocked on work

1. **Two commits in `dot_files`**, a different repo, outside my standing grant. `.claude/` is a symlink, so these are invisible to this repo's `git status`:
   - `claude/projects/toolguard/.claude/skills/toolguard-security-audit/SKILL.md` — items 88 **and** 89 both edited it
   - `claude/projects/toolguard/.claude/skills/toolguard-maintenance/passes/2-consolidate-and-group.md` — item 89
   - (`bash-grammar.md`, `test-config-isolation.md`, `toolguard_hook.toml`, pass 3 are also dirty there from **earlier** work — deliberately excluded rather than guessed at.)
2. **Ticket 99 item 2** — `parse_hook_input()` returning a class instead of `Dict[str, Any]`. Held back deliberately: it touches every caller and several mocking tests. The six contract keys still in `hook.py` are all consumed by it.
3. **Ticket 100** — two orphaned module-private functions, measured and bounded at exactly 2 of 383. Pick a direction; repointing `_resolve_leaf`'s ~30 tests at the real production path is right but costly.
4. **Ticket 101** — grammar rejects a bare `{}`. Fails safe to `ask`; the cost is auto-mode friction, NOT security. Do not schedule it as a security fix.

## Tickets filed during this stretch

**100** (orphaned privates), **101** (bare `{}` unparseable).

## Measurement state

Pre-registered and scored this stretch: **95, 99, 89, 88** (`NN-prereg.md` / `NN-scored.md`). 98 chunk 2 pre-registered, unscored.

**Two structural findings about the INSTRUMENT, both in RESULTS-LOG.md:**

- **The touch-set metric cannot see `.claude/`.** It is a symlink into another repo, so any ticket touching a rule or skill file under-counts silently. Items 88 and 89 both did. Every earlier such ticket has the same hole.
- **Eligibility is destroyed by whoever MEASURES the target first, not by whoever notices the problem.** 98 and 99 are Arnon's findings and would have been human-authored data points; my own spike-and-plan work spent them. To reach 20 eligible tickets the estimate must be locked **at filing time, before investigation**.

Two proposed cause codes: **`N`** (defect introduced by the change itself — chunk 1's placeholder forgery) and **`S`** (scope-conditioning failure — predicting the whole ticket while dispatching part of it, ticket 99's U3).

---

# HANDOFF 2026-08-21 end of day — 50 COMMITS, TICKET 98 COMPLETE, NOTHING PUSHED

**This is now the last section.** Supersedes the "46 COMMITS" entry above. Arnon: *"We'll continue next week."*

## Green state, verified at handoff

Suite **3990 OK** (expected failures=4) · `corpus_build.py --verify` **OK: no differences** · ruff format + check clean · `--stdlib --ambient --layers` all PASS. Version 0.6.0, release notes current.

## Committed today — ten

`f8c373a` 98 chunk 1 · `f816fea` docs: hard_deny carve-outs + TOML trap + 0.6.0 lock · `f11ba43` 97 step 3 · `b2c6f83` 95 · `4d62339` 99 items 1+3 · `52be738` 89 · `2648423` 88 · `b8947a4` 98 chunk 2 · `4509665` 98 chunk 3 · `726fd09` 98 chunk 4 · `4b59f68` release notes

**Ticket 98 is DONE, all four chunks.** `multiline.py` 683 -> 794 -> 522 lines; four independent quote models -> three; both hand-rolled scanners deleted; an unattributable heredoc answers `ask` even under a blanket `allow = ["Bash(*)"]`.

## NEEDS ARNON — five decisions, ZERO blocked on work

1. **Two commits in `dot_files`** (a different repo, outside my standing grant; `.claude/` is a symlink so they are invisible to this repo's `git status`):
   ```
   git -C ~/projects/dot_files add \
     claude/projects/toolguard/.claude/skills/toolguard-security-audit/SKILL.md \
     claude/projects/toolguard/.claude/skills/toolguard-maintenance/passes/2-consolidate-and-group.md
   git -C ~/projects/dot_files commit -m "toolguard skills: single-quote [regex] examples; ask for curl, find as the worked recipe"
   ```
   `bash-grammar.md`, `test-config-isolation.md`, `toolguard_hook.toml` and pass 3 are ALSO dirty there from EARLIER work — deliberately excluded, not forgotten.
2. **Ticket 99 item 2** — `parse_hook_input()` returning a class instead of `Dict[str, Any]`. Held deliberately: touches every caller plus several mocking tests. The six contract keys still in `hook.py` are all consumed by it.
3. **Ticket 100** — two orphaned module-private functions, bounded at exactly 2 of 383. Pick a direction; repointing `_resolve_leaf`'s ~30 tests is right and costly.
4. **Ticket 101** — grammar rejects a bare `{}`. Fails SAFE to `ask`; cost is auto-mode friction. **NOT a security fix.**
5. **Ticket 102** — here-strings misparsed as heredocs. Exposure ZERO in all corpora. The fix earns its place on silent leaf corruption, **not** on the deny bypass (that half needs deliberate evasion, outside the threat model).

## OWED BEFORE PUSH — checklist, tick these

- [ ] `uv run python tools/coverage_stdlib.py` — new code from 89, 98, 99 unmeasured
- [ ] `uv run python tools/pyscn analyze` (or the project's invocation) — read report, then discuss fix/defer/ignore
- [ ] **`/documentation-review`** — USER-INVOKED, I cannot run it. `docs/` changed a lot: new `heredoc-parsing-design.md`, plus edits to `agent-guides.md`, `configuration.md`, `security.md`, `permission-patterns.md`, `agent-map.md`, `technical-notes.md`, `install.md`
- [ ] The push itself (Arnon does all git writes)
- [ ] AFTER the push: `uv tool upgrade toolguard` **and the smoke test** — a hook that cannot launch fails SILENTLY, since Claude Code treats only exit code 2 as blocking:
      ```
      echo '{"session_id":"t","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"'$PWD'"}' | ~/.local/bin/toolguard
      ```

## Tickets filed today

**100** (orphaned privates), **101** (bare `{}`), **102** (here-strings). All three have measured exposure recorded IN the ticket, per `.claude/rules/evidence-before-fixing.md`.

## Measurement state

Scored this session: **95, 99, 89, 88, 98 chunks 2/3/4** — `NN-scored.md` alongside each `NN-prereg.md`. Chunk 1 recorded unscored (no prereg existed).

**Three findings about the INSTRUMENT, all in RESULTS-LOG.md:**
- The touch-set metric **cannot see `.claude/`** (symlink into another repo). Items 88 and 89 both under-counted. Every earlier ticket touching a rule or skill file has the same hole.
- **Eligibility is destroyed by whoever MEASURES first, not whoever NOTICES.** 98 and 99 were Arnon's findings and would have been human-authored data points; my spike-and-plan work spent them. **Lock the estimate at filing time, before investigation.**
- **The corpus cannot see rare shapes.** 98 chunk 2 fixed three real defects and the corpus reported ZERO decision changes — because none of the 6,401 cases contains any of the three shapes. A clean replay is not evidence a fix did nothing.

**Two proposed cause codes**: `N` (defect introduced by the change itself — two instances, both caught pre-commit, both unpredictable by any touch-set estimate) and `S` (scope-conditioning failure — predicting the whole ticket while dispatching part of it).

**One estimation rule worth adopting**: for a behaviour-changing ticket, ask **"what did this make false?"** not "what needs describing?" Chunk 4 touched 5 files against my predicted 2, and the three I missed were documents that an EARLIER chunk had silently invalidated.

## Loose thread, NOT investigated — `tmp/scratch_annotations.py`

Arnon had this open at end of day and the harness surfaced it; he did not ask for work on it. Recording so it is not lost to compaction.

It explores **runtime access-control annotations** — `PUBLIC` / `PRIVATE` / `PACKAGE_PRIVATE` constants, a `package_private()` class decorator writing into `cls.__annotations__[ACCESS_CONTROL_ANNOTATION]`, and `annotationlib.get_annotations` reading them back at runtime.

Plausibly relevant to two live threads, but **this is inference, not something he said**: the API-visibility criterion (*"privatize by whether non-test code should call it"*), and ticket **100**, where the leading underscore is the only declaration of internal-use intent and `architecture_fitness --orphans` was proposed to check conformance to it. An explicit annotation would be a stronger declaration than a naming convention.

**One observation, offered rather than acted on**: the decorator is named `package_private()` but assigns `PUBLIC`. The print's trailing comment says `# => "access:public"`, so it may be deliberate scratch behaviour rather than a slip — worth one question before assuming either way.

**Ask before doing anything with this.** It is in `tmp/` (gitignored) and was never a task.

---

# STATE AT 2026-08-22 — 73 COMMITS, second approved batch nearly done

**This is now the last section.** Supersedes the 2026-08-21 handoff.

Arnon approved a second batch on 2026-08-22 (verbatim): *"#103 writeup on compound.py · #100 fix · #101 fix only with concrete evidence in the toolguard logs · #102 check logs, if no evidence report it · #104 fix · #105 fix"* and *"Work non-stop until all the fix items are done."*

## Committed this batch — six

`da09faa` 105 doc half (multiline flow note + diagram) · `b63257c` 100 (two orphans deleted, ~30 tests repointed) · `61ecd7b` 104 (`parse_hook_input` returns `PreToolUseEvent`) · `e32d3da` 100+104 shared (`--orphans`, `--undeclared-types`) · `03d922c` 101 (bare `{}` word + the 17-construct deny guard)

Gates green at `03d922c`: suite **4002 OK** (expected failures=4), corpus verify clean, ruff clean, `--stdlib --ambient --layers --orphans --undeclared-types` all pass.

## In flight
**#105 phase 1** — grammar makes `comment` a real node. Two-phase rule applies; phase 2 (command_model `NodeKind.COMMENT`, extractor representation, client-facing discard choice, deleting `_strip_comments`) is a SEPARATE reviewed step and has not started.

## NEEDS ARNON — five, none blocked on work

1. **#102** — measured NO EVIDENCE (featherhill 0, instagram 0, toolguard 3 raw of which 2 are false positives and 1 is a benchmark feeding JSON). He said he would defer it as a YouTrack ticket.
2. **#106** — `audit_parts`/`deny_check_parts` are checked identically and differ only in audit visibility. Proposal: make visibility a property, not a partition. Cost labelled ESTIMATED, not measured. Do-nothing listed as legitimate.
3. **Four `--undeclared-types` findings**, reported and unfixed by instruction: `config.load_config_file`, `config.config_sync_settings_from_sources`, `rule_sort.parse_permissions_section_with_comments`, `subagent.identify_current_agent`.
4. **Two `dot_files` commits** still outstanding from 2026-08-21 (the audit skill and maintenance pass 2). `.claude/` is a symlink into another repo, outside my standing grant.
5. **#105 phase 2** scope, once phase 1 lands.

## THE FINDING OF THIS BATCH — a near-miss deny bypass, caught pre-commit

Ticket 101's first attempt removed `{`/`}` from the shared `delimiter` class. Target cases parsed; `{ rm -rf /tmp/zz; }` went **deny -> allow**, because `brace_group <- "{" spacing compound_command spacing "}"` and an un-delimited `}` gets swallowed by `compound_command`, so the group never closes and extraction falls through to `simple_command` with the leaf `{ rm -rf /tmp/zz`.

**The corpus would not have caught it — it contains no brace groups.** Third measured instance of that blind spot.

Permanent answer now in the tree: **`test/unit/test_deny_penetrates_constructs.py`** — a denied command in all 17 supported constructs, one subTest each so a regression names the construct, plus a benign-command control so it cannot pass by denying everything. Measured against `e32d3da`: all 17 already denied correctly.

**Rules established, and they bind the next `.peg` change:** never widen or narrow a shared character class to admit one token — prefer an explicit alternative at the specific position (`unquoted_word <- (escaped_char / var_ref / "{}" / !delimiter .)+`); and diff a grammar change construct-by-construct against the previous commit with `PYTHONPATH` pinned and provenance printed, not against the corpus.

## Canopy workflow — use bare `npx canopy`, NOT `npx canopy@latest`
```
CANOPY=/home/arnon/.npm/_npx/fb17767105d1bb2a/node_modules/.bin/canopy
cd toolguard/parser && node "$CANOPY" --lang python bash_parser.peg
cd /home/arnon/projects/toolguard && uv run ruff format toolguard/parser/bash_parser.py
```
Run canopy FROM the parser directory; from the repo root the generated header changes and the diff explodes. canopy is not on `PATH` — it lives in the npx cache and in featherhill's `node_modules`. With the `.peg` unchanged this round-trips byte-identically.

**UPDATE 2026-08-22, after Arnon added a rule — and the rule does NOT cover the form that was failing.** He added `Bash(npx canopy *)` (`.claude/toolguard_hook.toml:60`). Measured in the sandbox:

| command | decision |
|---|---|
| `npx canopy bash_parser.peg --lang python` | **allow** |
| `npx canopy@latest bash_parser.peg --lang python` | **ask** |
| `npx canopy@1.0.0 ...` | **ask** |
| `npx canopyXX ...` (control) | ask — boundary working correctly |

The wildcard follows a space, so `canopy@latest` was a different word and did not match. **RESOLVED 2026-08-22 18:06** -- Arnon added `"Bash(npx canopy@latest *)"` at `.claude/toolguard_hook.toml:61`, and re-measurement confirms `canopy`, `npx canopy` and `npx canopy@latest` all ALLOW, while `npx canopyXX` and `npx something-else` still ask. Only a pinned version (`npx canopy@1.0.0`) remains unmatched, which nothing uses. Use the bare form, which the rule allows; `@latest` buys nothing here since canopy is cached and the committed parser round-trips byte-identically against it. Widening to `Bash(npx canopy@* *)` is the alternative and is Arnon's call.

**COMMANDS THAT PROMPT WILL BLOCK AN AGENT INDEFINITELY — Arnon is away most of the time.** Measured 2026-08-22:
- `npx canopy@latest` fetches from the network and **prompts**. Two grammar agents sat blocked on it for 90+ minutes each. I misread both as stalled and took the work over; the second had been working correctly the whole time.
- `git worktree` prompted until **2026-08-22**, when Arnon added `"Bash(git worktree *)"` at `.claude/toolguard_hook.toml:62`. Re-measured: `add`, `remove`, `list` and `prune` all ALLOW. The `git -C <path> worktree ...` form still asks, and the Agent tool may use it -- so `isolation: "worktree"` is no longer categorically unsafe, but has not been proven safe either.
- `Bash(canopy *)` **is** on the allow list (`.claude/toolguard_hook.toml:59`) — but `canopy` is **not on `PATH`**, not even in a login shell, so the bare form is allowed and would simply fail. A symlink putting it on `PATH` would make the existing rule usable; that is a write outside the project and needs Arnon.

**Before putting any command in a brief, ask whether it prompts.** A blocked agent is indistinguishable from a stalled one and cannot tell you which it is.

## Still owed before any push
Coverage · `pyscn analyze` · **`/documentation-review`** (user-invoked) · the push · then `uv tool upgrade toolguard` **plus the smoke test**, since a hook that cannot launch fails silently.

---

# FINAL STATE 2026-08-22 — 76 COMMITS, SECOND BATCH COMPLETE, NOTHING PUSHED

**This is the last section.** Every item Arnon approved on 2026-08-22 is done. The punch list is exhausted; everything remaining needs a decision from him.

## Gates, all green at `ef37418`
Suite **4008 OK** (expected failures=4) · `corpus_build.py --verify` clean · `ruff format`/`check` clean · `--stdlib --ambient --layers --orphans --undeclared-types` all pass · coverage measured · `pyscn` read and triaged · release notes current · version 0.6.0 (unreleased, correct as-is).

## The second batch, in order

`da09faa` 105 doc half · `b63257c` 100 orphans deleted · `61ecd7b` 104 `parse_hook_input` returns a type · `e32d3da` 100+104 shared checks · `03d922c` 101 bare `{}` + the 17-construct guard · `63644a7` 105 phase 1 grammar · `2ca11b2` 105 phase 2 · `ef37418` release notes

**Item 105's arc is the one worth remembering.** Its original premise — that `_strip_comments` was redundant — was mine and was FALSE. Arnon suspected the pre-pass was masking a PEG gap, I told him it wasn't, and he was right. Corrected, it retired the third of four disagreeing quote scanners: only continuation joining remains.

## NEEDS ARNON — six, none blocked on work

1. **#102** — measured NO EVIDENCE (featherhill 0, instagram 0, toolguard 3 raw of which 2 false positives). He said he would defer it as a YouTrack ticket.
2. **#106** — `audit_parts`/`deny_check_parts` are checked identically and differ only in audit visibility. Do-nothing listed as legitimate.
3. **#107** — `_is_proc_subst` identifies a node by characters; 31 of 33 identity tests in that module use labels. Low priority, not a defect.
4. **Four `--undeclared-types` findings** — `config.load_config_file`, `config.config_sync_settings_from_sources`, `rule_sort.parse_permissions_section_with_comments`, `subagent.identify_current_agent`. Reported, unfixed by instruction.
5. **Two `dot_files` commits** from 2026-08-21 — the audit skill and maintenance pass 2. `.claude/` is a symlink into another repo, outside my standing grant.
6. **`/documentation-review`** (user-invoked), then the push, then `uv tool upgrade toolguard` **and the smoke test** — a hook that cannot launch fails SILENTLY.

## Two findings that outlive this batch

**`pyscn` scores a FILTERED SUBSET.** AST census: 79 files, 951 functions. pyscn reports 49 files, **213 functions — 22%** — and it filters per file (`config.py` 19 of 58). So "avg complexity 7.8" is the average over non-trivial functions only and **"Health 72/100" is not a package-level measure.** `bash_parser.py` (182 functions) is absent entirely. **Use its per-function findings; never quote its aggregate.** This also corrects an older note of mine claiming most offenders were canopy-generated — no longer true. **Date every tool measurement; re-take rather than carry forward.**

**Four instrument errors of mine in one day, every one caught by CONTRADICTION rather than care**: a golden comparison keyed on fields that do not exist (false "zero verdict changes"); a brace check run against 90-char truncated prefixes; a coverage run piped through `tail -40` that silently dropped every core module; and a glob that matched a *test* file's `.cover` instead of the module's. **The practice that caught all four was having a second number that disagreed with the first.** That is cheaper and more reliable than resolving to be more careful.

## Where the campaign stands on the estimator
`reports/surprise/CONSOLIDATED-BATCH-2.md` has the full table. Production recall is near 100% almost everywhere — and that is **not** evidence the estimator works, because I now write the tickets, the briefs and the estimates. **This batch added ZERO human-authored tickets** toward Arnon's count of 20.

---

# STATE 2026-08-23 evening — 79 COMMITS · MEMORY EXTRACTION VERIFIED · NOTHING DELETED

**This is the last section.** Written at ~86% session usage as a durable handoff.

## Code state — all green
79 commits on `too-45`. Suite **4008 OK** (expected failures=4) · corpus verify clean · ruff clean · `--stdlib --ambient --layers --orphans --undeclared-types` all pass · `check_doc_links` **passing again** (it had been failing at HEAD since `715cdbd`; fixed in `305caa3`).

Landed since the previous entry: `9b4ff1d` item 108 (reading a hook event moves to the contract, takes a source) · `715cdbd` items 88/89 ported to the **distributed** skills in `skills/` · `305caa3` the link that port broke.

## THE MEMORY-EXTRACTION EXERCISE — where it actually stands

**Backup exists and is verified**: `~/tmp/toolguard-memories.tgz`, **743 files in, 743 on disk**, 4.2 MB, taken by Arnon 2026-08-23 17:01. The three highest-value rescues were spot-checked as present.

**Five summaries written, all five adversarially verified.** Roughly **460 claims checked, ~24 refuted or misattributed, ~35 true-but-misleading.**

| document | state |
|---|---|
| `DURABLE/01-claude-failure-modes-and-mitigations.md` | written by me, **corrections folded in** |
| `intermediate/practices-with-evidence.md` | verified — 176 claims, 7 refuted |
| `intermediate/rejected-methods-and-metrics.md` | verified — 74 claims, 4 refuted |
| `intermediate/defect-taxonomy.md` | verified — 32 claims, census wrong by 15 |
| `intermediate/open-questions.md` | verified — 133 claims, 9 refuted |
| `intermediate/deletion-triage.md` | verified — **NOT SAFE AS-IS**, 12 additional rescues |
| `DURABLE/02-campaign-cost-data.md` | **extraction was in flight** — check whether it landed |
| `DURABLE/03-out-of-band-instruction-records.md` | **extraction was in flight** — check whether it landed |

## THREE CLAIMS I RELAYED TO ARNON THAT VERIFICATION OVERTURNED

1. **The challenge to his aggregate-metrics position was manufactured by misquoting him.** He said *"like any other aggregate 'architecture metric' **we discussed**"* — bounded. The report re-quoted him with an ellipsis eating "we discussed", then objected to the unbounded universal it had created. Its premise (no other aggregate was tracked) is also false — its own section reproduces three that were. **His position stands; delete that block.**
2. **"Blinded recall predicts cost" is REFUTED.** It rests on ticket 79 being the most expensive item; the corpus retracts that under *"I have been costing tickets in the wrong currency"* — 4h15m, below average. The quoted recall range also mixes production-only and all-files scoring under one label.
3. **The deletion counts do not reproduce** — 739 files not 733, 324 delete not 323, and "9 files carry cost tables" is really **104**.

## NEXT STEPS, in order
1. Check whether the two extractions landed; if not, re-dispatch (briefs are in this session's history).
2. **Rebuild the delete list from the VERIFIED triage**, not the original — at minimum add the 12 rescues and fix the two that point at the wrong file (the nested-directory swap: the *task recall* holds the content, the *report* is a 1 KB pointer).
3. Get Arnon's acceptance of the corrected summaries **before** deleting anything.
4. Deletion method matters: `toolguard-memories/` **is** the basic-memory `toolguard` store (741 entity rows). A plain `rm` leaves a stale index — use `delete_note` or force a re-sync.

## STILL NEEDS ARNON — unchanged
#102 deferral · #106 declined (recorded) · #107 reframed round the package boundary, low priority · four `--undeclared-types` findings · **two `dot_files` commits still uncommitted** (audit skill + maintenance pass 2 — note these are the `.claude/` INSTALL copies; the distributed source is already fixed in `skills/`) · `/documentation-review` · the push · then `uv tool upgrade toolguard` **and the smoke test**.

## IDE, resolved as far as it can be
Windows-side: project index works (find usages, navigation, `search_symbol`, structural inspections) but **no SDK** — so `analyze_calls` is dead, `include_external` search returns nothing, and **type inspections emit FALSE ERRORs on correct code** (measured: `Optional[Tuple[str, Optional[str]]]` flagged "Invalid type argument"). Remote Development reaches the interpreter but cannot map paths for tooling. Long-open unfixed JetBrains tickets; web advice is stale. **Do not build a Windows venv** — it would resolve POSIX path code against Windows semantics. pyright is the semantic lane and `LSP incomingCalls` was verified working (7 callers, resolves unittest methods individually).
