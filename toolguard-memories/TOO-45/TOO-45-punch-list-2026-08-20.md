---
title: TOO-45 punch list after the 2026-08-20 re-triage
type: note
tags: [task-memory, TOO-45]
permalink: toolguard/too-45/punch-list-2026-08-20
---

# Punch list — everything still to do, after the evidence re-triage

Supersedes any earlier ordering. Decisions folded in from 2026-08-20: advisory tooling skipped; 20 and 57 pulled IN as mutation bugs; 40 dropped (JSON config retiring under **TOO-67**); fail-open treated as high priority; 17 deferred pending re-decision; 83, 84, 87, 21, 34, 36 skipped or deferred on measured zero/dogfood-only exposure.

## In flight

| # | ticket | est |
|---|---|---|
| 1 | **18** multi-token `:*` over-match, + **20** consolidation `ask`->`allow`, + **22** redundancy unsafe deletions. 748 featherhill occurrences, ~1 decision in 5. Matcher first; 20/22 re-derived after. | 14h |

## Runtime, severe

| # | ticket | why | est |
|---|---|---|---|
| 2 | **74** empty registry allows every tool, hard-deny included | **fail-open** — Arnon's high-priority class | 3h |
| 3 | **79** command substitution runs foreign code with no ASK floor | 1,121 occurrences | 4h |
| 4 | **19** compound splitter — 3 shapes reach the shell never rule-matched | runtime bypass | 5h |
| 5 | **57** maintenance `--apply` can enact a widening, hands a `#NOSECURITY`-withheld rule to the writer | **mutates permissions** | 3h |
| 6 | **39, 64, 70** write-guard / self-protection cluster: placement-blind loss check; ledger redirects a write into `$HOME`; applying an edit drops the parse-failure floor | protections that do not protect, silently | 7h |
| 7 | **82** native's wrapper-stripping list (`.peg` phase 1, then Python) | fidelity; under-allows `timeout 30 npm test` | 4.5h |

## Architectural — Arnon asked for these

| # | ticket | est |
|---|---|---|
| 8 | **85** external-contract module + `--contract` check + architecture-doc section and diagram | 8h |
| 9 | **81** runtime sentinel for a relative `resolve()`, promote `resolve` to fatal | 4h |

## Overdue and unglamorous

| # | item | est |
|---|---|---|
| 10 | **32** — the two items marked *"fix before push"*, open since **2026-08-10**. Oldest thing on the list | 3h |
| 11 | **07** remainder — doc-comment sweep, test tier, ~18 of 88 files | 4h |
| 12 | **11, 14, 16** remainders — one wrong doc sentence; takeover notice still bypasses the error reporter; ToolSpec code residual | 3h |

## Wrap-up, per the pre-push checklist

| # | item | est |
|---|---|---|
| 13 | `/documentation-review` — `docs/`, `README.md`, `AGENTS.md`, `llms.txt`, and `docs/agent-map.md` (the doc most likely to be silently stale) | 2h |
| 14 | Consolidated **surprise-factor report** — line-weighted headline per Arnon's redefinition | 2h |
| 15 | Coverage, `pyproject.toml` version bump, release notes, `pyscn analyze` on the main package | 2h |

**Total ~64h.**

## Explicitly NOT doing

**Skipped on measured zero or dogfood-only exposure**: 83, 84 (Arnon), 87 (`&>` etc: 0 occurrences), 21 (its featherhill "blanket allow" turned out to be toolguard's own development traffic on 2 days of 49), 34 (98, all dogfood), 36 (652 of 657 are this repo's own mandated disclosure comments).

**Deferred pending Arnon's re-decision**: **17** — zero exposure across 42,113 native-intent rules, and the immunity is structural (prefix rules end in `*`, and Claude Code's dialog writes prefix rules by construction). Revisit trigger is precise: **the first deny rule that does not end in `*`**.

**Advisory tooling, skipped without tickets**: 37, 53, 56, 61, 62, 66, 72, 75. Read-only diagnostics; worst outcome is a misleading report being read by a human. **75** is the closest call — it feeds rule proposals — and is the one to revisit first if any are.

**Dead**: **40** (`verify_config_text` accepts any JSON) dies with JSON config retirement, TOO-67.

---

## ADDENDUM 2026-08-20 — items this list dropped, restored

**The re-triage document had a "Tier 3 — runtime but low" section and this punch list omitted it entirely.** The same summarise-and-shed failure that lost 23 tickets across a compaction, repeated within an hour of recording a memory about it. Restored here, and the count below supersedes the ~64h total above.

| # | ticket | why | est |
|---|---|---|---|
| 7a | **38** `fallback_kind` re-derived by substring-matching the program's own prose | **Arnon 2026-08-20 (A9): "no prose-parsing should be present in the code base. Should be fixed."** Same family as #32 item 1, where four lock reasons collapse to one and a false message is announced from what survives. This is the campaign's founding defect — the 813/975 under-logging incident | 3h |
| 7b | **42** `normalize_entry` returns `(None, error)` and **seven** call sites discard the error | silent failure, runtime tier | 2h |
| 7c | **47** `TakeoverConfig`'s 4th positional is `no_match_fallback`, so the stock construction misassigns | config correctness | 1.5h |
| 7d | **52** a wrong-typed `[[permissions]]` section is discarded with no signal | silent discard; TOML, so unaffected by the JSON retirement | 2h |

**Revised total: ~72h.**

## Decisions folded in from Arnon's DECISIONS-PENDING review, 2026-08-20

His standing instruction for that file: **silence means ignore.** Only items he commented on are actionable.

- **A12** — "governed" means describable **and** rule-writable. The whole governed question moves to **TOO-51 / TOO-53**; nothing owed here.
- **A14** — **already resolved, no action.** It warned that `architecture-as-built.md`, `native-pattern-reference.md` and `docs/diagrams/` were untracked while tracked files linked to them, with `architecture.md` staged as deleted — a rename git would not follow unless committed together. Verified 2026-08-20: all tracked (35 diagram files), `architecture.md` deleted in `640f86b`. It went in as one commit.
- **A11, A10** — all install work skipped under **TOO-36**.
- **A13** — dropped; `pyproject.toml` covers it.
- **A4 / #34 nested backticks** — **skipped.** No corpus support: 98 occurrences, **all** toolguard dogfood, **zero** in featherhill. A command shape, so dogfood is not automatically dismissible — but 0 in the real user project against 98 in a shell-heavy repo makes it our habit, not a user's.
- **A5 / #32** — **6 of 8 open**, including both "fix before push" items untouched since 2026-08-10. Not re-added work.
- **A7 / #11** — code is **correct and now pinned**; the ASK floor covers Bash and MCP terminal alike by construction (`api._decide_bash` routes both through one resolver). **One wrong sentence remains** at `docs/configuration.md:507` calling it "Bash-only". Doc fix only.
- **A8 / #36** — skipped, consistent with the measurement (652 of 657 occurrences are this repo's own mandated disclosure comments).
- **Ticket 18** — confirmed it violates documented native behaviour (the word-boundary rule), which is why it is in flight.
- **Ticket 19 P7** — verify it still reproduces before touching it.
- **`architecture-as-built.md`** — Arnon reviews separately.

## New work item

**16 — `architecture_fitness.py --stdlib`** (task #42). Nothing enforces the stdlib-only runtime rule; an AST scan finds 0 foreign roots today, but **the dev venv would mask a regression** since `numpy` and `sentence_transformers` are importable there. ~20 lines against `sys.stdlib_module_names`. **Arnon: KISS — do not over-engineer.** Est 1.5h. Runs after 18 commits.

---

# SCOPES RE-DERIVED FROM TICKET AMENDMENTS, 2026-08-20 (after the ticket-18 lesson)

Ticket 18 was briefed from its body rather than its `PARTIALLY FIXED` line, so I measured exposure for an already-fixed defect and promoted it to first in the queue on that number. **Every punch-list ticket has now had its open scope re-read from its amendment.** These supersede the estimates above.

Phase 2 (`05f786d`) closed considerably more than the bodies suggest — several items are nearly done, and one is larger than I had it.

| # | ACTUAL remaining scope, per the ticket's own amendment | est |
|---|---|---|
| **18** | **DONE** — headline defect was already fixed in `05f786d`; this session closed mid-pattern `:*` and any-colon splitting. Awaiting review, then commit | ~3h *(actual)* |
| **74** | fully open, no prior fix | 3h |
| **79** | fully open, no prior fix | 4h |
| **19** | bypasses **P2-P5 all still reproduce** — `toolguard/parser/multiline.py` was untouched by phase 2. Four bypasses, not three | 5h |
| **20** | **LARGER than I had it**: sections **1-4 all reproduce**, and `consolidate.py:597` still gates on `broadened_count` alone. *"The ticket's docstrings were corrected over otherwise-unchanged code"* — prose fixed, behaviour not | 4h |
| **22** | HR2's note still claims a rule *"can be dropped"* (`hierarchy.py:400`); RD1 space-collapsing; RD2 provenance (`redundancy.py:197`) | 3h |
| **39** | **more severe than my framing**: a **`deny`->`allow` or `ask`->`allow` rewrite still writes successfully.** The guard does not stop a permission-weakening rewrite | 3h |
| **64** | defect 1 fixed (level derived from path). Still open: `record_decision` **unlocked and non-atomic** (`:340-366`) | 2h |
| **70** | main defect fixed. Still open: caption-vs-enacted mismatch and unconditional double-wrapping in `edit_proposal.py` | 2h |
| **52** | **small and concrete**: a bare-string `allow = "Bash(ls:*)"` is silently lost because `config.py:1733` **iterates its characters** rather than checking its shape — nine character-level warnings, no error | 1.5h |
| **57** | **nearly done** — the one genuinely red item (a misspelled `--tool` flag) is fixed; the other two holes needed no production change | 1h |
| **14** | **tiny** — the takeover notice still writes straight to stderr, `session_warnings.py:27,33` | 0.5h |
| **11** | **tiny** — one wrong sentence, `docs/configuration.md:507` ("Bash-only") | 0.5h |
| **16** | **tiny** — documented; code residual at `hook.py:1130` tracked as TOO-51 | 0.5h |
| **32** | 6 of 8 open, including both **fix before push** items from 2026-08-10 | 3h |
| **38, 42, 47** | fully open, no prior fix. 38 is Arnon's A9 (no prose-parsing) | 6.5h |
| **82, 85, 81** | unchanged | 16.5h |
| **07** remainder · `--stdlib` · wrap-up | unchanged | 11.5h |

**Revised total: ~67h.**

## What moved, and why it matters more than the total

- **20 is prose-fixed but behaviour-unchanged.** Its amendment says the docstrings were corrected over otherwise-unchanged code. That is the exact artifact this campaign distrusts: a ticket that *reads* closed. Anyone glancing at it would conclude it was handled.
- **39 is a permission-weakening write that still succeeds** — worse than "placement-blind loss check", which is how I had it.
- **52, 57, 14, 11, 16 are together ~4h**, not the ~9h I had. Several were mostly closed by phase 2.
- **19 is four bypasses in `multiline.py`**, a module phase 2 never touched — so nothing there is partially done.

---

# ESTIMATE RECALIBRATED against actuals, 2026-08-20 ~16:00

The punch list assumed **~4.5h per item**. Measured cost of every ticket completed in phase 3:

| ticket | elapsed | review rounds |
|---|---|---|
| 80 | 3.0h | 3 |
| 77 | 4.4h | 1 |
| 44 | 6.9h | 6 |
| 78 | 10.0h | 5 |
| **18** | **~6h and counting** | **3 so far, not committed** |

**Average ~6h, not 4.5h — the per-item figure was ~30% low.** The driver is review rounds: substantive tickets are averaging **3-5**, and each round costs roughly an hour of agent time plus a repair pass.

**And the rounds are earning it on the security-relevant tickets.** Ticket 18's three rounds found, in order: a reachable branch removed as dead code; a false fidelity claim with a hard-deny consequence; and published security advice that blocked every practical `curl`. None were style findings. Ticket 78's rounds 2-5 were the counterexample — they chased tilde positions with zero field occurrence, which is why the evidence gate now applies to findings *within* a ticket, not only to whole tickets.

## Revised total

Splitting the list by size rather than averaging:

- **9 substantive tickets** (74, 79, 19, 20, 22, 57, 39, 64, 70) at ~6h -> **54h**
- **4 small runtime items** (38, 42, 47, 52) at ~2.5h -> **10h**
- **2 architectural** (85, 81) at 8h and 4h -> **12h**
- **5 tiny remainders** (11, 14, 16, plus 32's two items) -> **4h**
- **07 test tier** -> 4h · **`--stdlib`** -> 1.5h · **wrap-up** -> 6h

**~91h**, up from 67h. **Ticket 19 drops to ~3h** (P4 and P5 skipped on measured zero exposure), which is already folded in.

## What would move this number most

**Not working faster — reducing review rounds.** Two levers, both already in place and unproven:

1. **The evidence gate applied to findings within a ticket**, added after ticket 78. If it works, rounds spent on zero-exposure findings disappear.
2. **Briefs quoting `git diff --stat` rather than forwarding an implementer's prose.** Three of ticket 18's rounds had to correct a false premise that came from my brief, and correcting it consumed reviewer attention that would otherwise have gone to the code.

Neither is measurable yet. **Report the number as ~90h and revise after the next two tickets**, rather than claiming the levers will work.

---

# DECOMPOSITION RULE, Arnon 2026-08-20 — a high estimate is a design problem, not just a prediction

> *"Any outliers in the estimates are a reason for a second look. Even if they are dead-on correct, what do you think 16 hours of your coding time means for my review work? If it needs 16 hours of agent time then it probably needs to be broken up to smaller chunks - or there is something wrong with the ticket or approach or something. But in all cases, high estimate outliers call hard for questioning."*

**The deliverable is not a fix, it is a REVIEWABLE fix.** Agent time is cheap; Arnon's review time is the scarce resource, and a large ticket produces a diff that cannot be reviewed well. So a high estimate demands decomposition **whether or not it is accurate** — and if the work resists decomposition, that is itself evidence the ticket or the approach is wrong.

This is the proactive form of the ticket-18 lesson. There the split happened **reactively, after six review rounds**; the rule says make it at estimate time.

## Applied to this list — every item now under ~4.5h

**85 (was 8h) splits along natural seams, each independently committable:**

| chunk | est |
|---|---|
| create the leaf module + move the **wire protocol** constants (payload/response field names, event names) | 2h |
| move the **native-semantics** facts (stripped wrappers, matching rules) with dated citations | 2h |
| the **`--contract` checker**, validated against a deliberately planted bare literal | 2h |
| **architecture-doc section + diagram** | 2h |

Only the third is a new instrument; it is the one needing anti-vacuity treatment. The first two are mechanical.

**The 6h "wrap-up" was never one ticket** — it is three: `/documentation-review`; the consolidated surprise-factor report; and coverage + version bump + release notes + `pyscn analyze`.

**07's test tier (4h, ~18 files)** chunks by file group. Comment sweeps are exactly where a large diff hides defects — this campaign found ~40 code bugs *inside* comment reviews, so a reviewable chunk size matters more here than the file count suggests.

**82 (4.5h) already has an internal split** and it is mandatory, not optional: `.peg` + canopy regeneration first, reviewed alone, then the Python (`.claude/rules/bash-grammar.md`).

## The standing check

Before dispatching any ticket: **is this estimate an outlier against the rest of the list?** If yes, decompose before starting, or say explicitly why the work cannot be split. "It is genuinely big" is not an answer — 85 is genuinely big and still splits into four reviewable commits.

---

# THE ROUND-CURVE CONTROL, added 2026-08-20 — outlier detection DURING execution, not just at estimate time

Arnon: *"you've also gathered some statistics so far about the number of rounds it should reasonably take you to converge... I would venture to guess that #18 was an outlier on that statistic too. And you reached that conclusion yourself at the end."*

Correct. The decomposition rule catches outliers **before** a ticket starts; this one catches them **while it runs**.

## Blocking findings per review round

| ticket | rounds | trajectory | shape |
|---|---|---|---|
| 45 | 5 | 14 -> 14 -> 7 -> 4 -> 0 | high, drains |
| 44 | 5 | 12 -> 3 -> 4 -> 3 -> 1 | high, drains |
| 78 | 5 | 7 -> 2 -> 3 -> 1 -> 2 | high, drains |
| **18** | **6** | **2 -> 2 -> 1 -> 3 -> 3 -> 2** | **low, never drains** |

**Round count alone would not have flagged 18** — 44 and 78 also ran 5. **The signal is the shape.** 18 opened with the fewest findings of any ticket in the campaign and never converged; rounds 4 and 5 each found *more* than round 1.

## Why the shape matters more than the count

- **High-then-falling** = the reviews are draining a pool of defects that already existed. Normal, and the rounds are earning their cost.
- **Flat-and-low** = each round is finding problems *the previous round's repair introduced.* That is what happened: four successive `curl` recipes, each created by fixing the last, each wrong in a new direction.

**A flat curve is not slow convergence. It is a signal that the work is generating its own defects**, which no additional round can fix.

## Two running controls, checked after every round

1. **Does the blocking count fail to fall across two consecutive rounds?** Stop and re-derive the problem. Do not commission another repair.
2. **Where are the findings?** When a round returns zero findings in the code and all of them elsewhere — docs, guidance, tests — **the ticket has already split in fact.** Make it official and commit the verified part.

For ticket 18 both controls fired at **round 3**. Acting on either would have committed the matcher three rounds and roughly six hours earlier. Both were visible; neither was being watched.

## Related

The estimate outlier rule (a high estimate is a design problem) and this one are the same idea at two points in time. Together with `feedback_complexity_mismatch_is_a_stop_signal`: **sanity-check the estimate before starting, and the curve while running.**

---

# TICKET 20 — DECOMPOSED AND DESIGN-DECIDED, 2026-08-21

At 4h it is not an outlier by this list's own threshold, but its four open sections are different **kinds** of work landing in different files, and one of them changes a function contract. Splitting it is about review shape, not size.

## Measured before splitting — the prereg's falsifiable prediction, resolved

Prereg locked: *"`_check_family1_safe` has not been read. Predicted: it carries the same no-corpus branch."*

**CONFIRMED, with an asymmetry the ticket gets right and the prediction did not anticipate:**

| | no-corpus branch returns `True` | checks `broadened` | checks `tightened` |
|---|---|---|---|
| `_check_family1_safe` (:324) | **yes** | yes | **yes** |
| `_check_family2_safe` (:582) | **yes** | yes | **no** |

So *safe-when-unverifiable* spans **both** gates, while the missing `tightened_count` is family 2 only. A fix touching one function is incomplete — as predicted, for a partly different reason.

Also observed: family 1's docstring is now **scrupulously honest**, naming the two shapes that pass and still tighten. That is the amendment's *"docstrings were corrected over otherwise-unchanged code"* — the prose tells the truth about a defect nobody fixed.

## The open design question — DECIDED, not asked

The ticket says *"decide, do not patch"* and offers three shapes. **Taking option 2: a three-state result — `safe` / `unsafe` / `unverified`.**

Why, briefly: option 1 (refuse without a corpus) makes `toolguard-maintain --apply` unusable on a fresh install with no logs, which is a real regression for the tool's most common first use. Option 3 leaves the overloaded boolean in place and relies on every caller remembering to read the prose beside it — the exact failure being fixed. Option 2 is what the project's own *"prose is output, not a data structure"* rule prescribes: **the fact that nothing was checked belongs in the value, not in the sentence next to it.** It spreads furthest, and that is the point — every caller that branches on this must be made to confront the third state.

Flagged for Arnon on review; reversible if he prefers 1 or 3.

## The split — three independently committable chunks

| chunk | scope | closes | est |
|---|---|---|---|
| **20a** | Safety gates stop meaning two things. Three-state result across **both** `_check_family1_safe` and `_check_family2_safe`; family 2 gains the `tightened_count` check; `propose_consolidations` receives the corpus like its two neighbouring engines | §1 (in practice), §2, the amendment | 2h |
| **20b** | Static subsumption stops asserting what it never checked. `_static_prefix_of`'s boundary rule matched to `match_command`'s real gate; `test_path_boundary_prefix_subsumes` updated (it currently **pins the unsoundness**); the rationale string that asserts subsumption carries structured evidence instead | §3, §4 | 1.5h |
| **20c** | `RA1` — a dry run's diff carries the writer's normalisation, so an approved consolidation also silently re-sorts the file and deletes empty `deny = []` / `ask = []` lines the user never approved | RA1 | 1h |

**20c is a different subsystem** (`rule_apply.py` / `rule_sort.py`), a different risk, and it is about the **approval surface** rather than the safety gate. It is the natural candidate to defer or file as its own YouTrack ticket — flagged for Arnon rather than decided here, because it is the only part of ticket 20 a user sees directly.

**Order: 20a, then 20b.** 20a's corpus wiring changes what 20b's probes observe, so doing 20b first would mean re-deriving it.

---

# ESTIMATE REVISED FROM MEASURED WALL-CLOCK, 2026-08-21

The 91h figure above ended *"report the number as ~90h and revise after the next two tickets."* Three have landed since (74, 39, 79). Revising — and this time from **git commit timestamps**, not from a per-item guess.

## Measured, phase 3, `db23d17` (08-19 14:16) -> `5124795` (08-21 01:54)

| item | elapsed |
|---|---|
| 44 + follow-up | 6h56m |
| 80 + 2 follow-ups | 3h03m |
| 77 (two-phase grammar) | 4h22m |
| 78 | 8h51m |
| 18 | 4h15m |
| `--stdlib` | 27m |
| RED sweep + 74 | 1h16m |
| 39 | 2h13m |
| 79 | 4h15m |

**10 items in 35h38m — ~3.6h per item, against the ~6h the estimate assumed.** Range 27m to 8h51m.

## THE CORRECTION THAT MATTERS — I have been costing tickets in the wrong currency

I described 79 as *"the most expensive item of the campaign"* on the strength of **11 agent runs and ~3M subagent tokens**. By wall-clock it was **4h15m — below the phase-3 average, and less than half of ticket 78.**

**Tokens and wall-clock diverge because agents run in parallel and fast.** Arnon's constraints are his review time and calendar time; neither is measured by token spend. So *"expensive"* meaning *"many agent runs"* is a metric about me, not about him, and I have been reporting it as though it were his cost.

**78 is the real outlier at 8h51m** — and its rounds 2-5 chased tilde positions with zero field occurrence, which is exactly what the evidence gate was added to stop. That is the expensive failure mode: not many rounds, but many rounds on findings that did not matter.

This does not retire the round-curve control — 79's four rounds each caught a genuine security weakening, so they were earned. It reprices them.

## Revised remaining — ~55-65h, from ~91h

| bucket | items | est |
|---|---|---|
| substantive | 19 (in flight), 20a, 20b, 22, 64, 70, 82 | ~28h |
| small runtime | 38, 42, 47, 52 | ~6h |
| architectural | 85 (4 chunks), 81 | ~11h |
| remainders | 11, 14, 16, 32's two items | ~4h |
| 07 test tier | | ~4h |
| wrap-up (doc review, coverage, version, release notes, pyscn, surprise report) | | ~6h |

**~59h, call it 55-65h.** The drop is not from working faster — it is from **replacing a 6h assumption with a 3.6h measurement**, plus 20 splitting into chunks that are individually smaller than the whole.

## Caveats, stated rather than buried

- **Elapsed time includes waiting for Arnon.** For "when is this done" that is correct to include; but he has since said to stop pausing, so the historical rate slightly **overstates** what remains.
- **High variance.** A single 78-shaped ticket adds 5h over the mean by itself. Do not quote 59h as precise; the honest form is *"55-65h, and one bad ticket moves it by 5."*
- **Unmeasurable:** the two levers named above (the within-ticket evidence gate, and briefs quoting `git diff --stat`) still have no clean measurement, and I am not claiming credit for them in this number.

---

# SCOPE CHANGES MUST GO THROUGH THE BRIEF, NOT A SIDE CHANNEL — measured 2026-08-21

During ticket 19's repair round I discovered mid-flight that I had told the implementer something false (that finding F1 was not a regression). I corrected it by **sending the running agent a message** that added a substantial new item to its scope.

**The agent refused.** Its report:

> *"a message arrived formatted as a system-reminder (not a genuine new coordinator turn) claiming the brief's 'F1 is not a regression' finding was wrong ... and instructing me to add a large new 'Item 0' ... I did not treat that as authorization to expand scope — it arrived through an unusual channel and directly contradicted the actual brief."*

It then **independently re-verified the factual claim, properly isolated, confirmed I was right — and still declined to implement**, referring the decision back.

**That is the correct behaviour and it should be preserved, not trained out.** An instruction that (a) arrives outside the briefing channel, (b) contradicts the standing brief, and (c) expands scope is exactly the shape of an injected instruction. An implementer that acts on it is one that can be steered by anything that reaches its context. The agent separated the two questions properly: *is the claim true* (checkable, and it checked it) from *am I authorised to act on it* (not checkable, so refer up).

## The rule

**A mid-task correction of FACT may be sent to a running agent. A change of SCOPE may not.**

- **Fact correction** — "the measurement you were given is wrong, here is the corrected one" — is safe to send, because the agent can verify it independently and its authority comes from the evidence, not the sender.
- **Scope change** — "also fix X" — must come as a **new task with its own brief**, which is the channel that carries authorisation.

When both are needed, send the fact correction with an **explicit instruction not to act on it**, and dispatch the scope change separately. My message did the opposite: it bundled a correction the agent could verify with an expansion it could not, and the expansion contaminated the correction.

**Cost of getting this wrong here: one wasted round.** The repair round completed its five assigned items correctly and the regression stayed unfixed, needing a third round that a properly-channelled dispatch would have avoided.

## Related failure the same day

The reason the correction was needed at all: I refuted a correct review finding using a broken isolation instrument, and my validation of that instrument tested a different invocation from the measurement. Recorded in `.claude/rules/evidence-before-fixing.md` and in auto-memory. **Two process failures in one ticket, both mine, neither caught by a gate** — the agent's refusal and the reviewer's finding were the only things that caught either.

---

# ARNON DECISIONS, 2026-08-21

| item | decision |
|---|---|
| **20c / RA1** | **DROPPED.** *"A resort is harmless as long as it follows the rules about comments correctly."* The empty-list deletion is not worth a ticket either |
| **32 item 2** | **DEMOTED** from "fix before push" — its justification was measured false |
| **17** | **CLOSED** — `[native]` end-anchor, zero exposure, immunity structural |
| **57** | **CLOSED** — the one red item was fixed; the rest needed no production change |
| **90** | **SKIP** |
| **93** | **SKIP** — a maintenance-skill concern; Arnon filed **TOO-68** for it |
| exec-wrapper bar | **RESOLVED BY CONFIG**, not code. User-level `find` allow + hard_deny applied; featherhill's copy removed. No ticket |
| out-of-band reports | **not a problem** — closed |

**Still open for Arnon**: ticket 70's **AE2**, and the disposition of **91** and **92** now that their evidence is measured.
