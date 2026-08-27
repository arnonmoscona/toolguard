---
title: TOO-45 punch-list 07 work queue
type: note
permalink: toolguard/too-45/too-45-punch-list-07-work-queue
tags:
- task-memory
- TOO-45
---

# #07 work queue — the unattended run

## COMPLETE 2026-08-12 ~15:00 ET — every tier swept and verified

**`toolguard/`, `tools/` and `test/` are all done.** Cron `4f317fc6` deleted. Nothing in flight.

### Final verification, run by the coordinator after the last agent landed

| gate | result |
|---|---|
| `comment_hygiene --compare-against HEAD` | **only** `toolguard/__init__.py` and `tools/architecture_fitness.py` — the two known non-sweep changes |
| `ruff format --check .` | 175 files already formatted |
| `ruff check .` | All checks passed |
| full suite | **`Ran 2733 tests` / `OK`** |
| `git diff --stat toolguard/` | 72 files, 5,383 insertions / 10,282 deletions — all comment churn |
| `git diff --stat test/` | 86 files, 1,557 insertions / 5,798 deletions |

**Net: roughly 9,100 lines of prose removed** across the package, the dev instruments and the suite, with **zero code-shape drift anywhere**.

Two files -- `test/__init__.py` and `test/verdict_corpus/__init__.py` -- show no diff because they were read and found already minimal. That is a swept-and-unchanged result, not a gap.

### What #07 actually produced

The comments were the smaller half.

- **14 proposed tickets** (17-30), every one found by *executing* a claim rather than reading it. Six against the permission engine and its analyzers, five promoted out of this queue when Arnon noticed they had never been written up, one synthesis-only finding, two dev-instrument fail-opens.
- **~65 tests whose assertions cannot fail**, across ~78 files, with a catalogue of **19 distinct shapes**.
- **~50 mechanisms with zero test detection**, measured by out-of-tree mutation.
- Four method rules that did not exist when the sweep started: *verify a hazard note before keeping it* (keep / delete / **correct**); *ticket narrative goes, a product runbook pointer stays*; *a mutation that produces failures is not necessarily detected — read the tracebacks*; and *mutate toward the fix, not only away from correctness*.

### Still open, and NOT part of #07

- The 14 tickets are written and **unfiled to YouTrack** — Arnon reviews 16-and-later.
- **TOO-52** (claim-falsification review skill) carries the method findings.
- The queue's per-file rows below are the raw material; `reports/follow-up-queue.md` has ~60 lettered sections of detail.
- **Before Arnon commits #07**, note that the "has working-tree changes ⇒ swept" method used to track progress stops working. The finished list is recorded above.

## STANDING RULE: this file is MY scratch. Arnon's decisions live in `proposed-tickets/`

Arnon, 2026-08-12: *"the queue is for you not me"* -- and the defect memories are what he reviews and decides on.

**So a product defect recorded only here is a defect that will never be actioned.** Promote it to `proposed-tickets/` the same day it is found. Do not wait for it to be "complete": a ticket with an open question in it still reaches him; a queue row does not.

This was caught by Arnon, not by me. Between tickets 22 and 23 **five product defects sat in this file for days** -- the `log_crash` fail-open among them, which this queue itself repeatedly called the highest-severity single row. Every one had a note saying it "needs a ticket, not this sweep", which read as a decision and functioned as a burial. Filed as 23-27 once he asked.

The failure is the same one this sweep keeps documenting: a finding recorded in a 2,200-line queue is invisible to anyone reading row by row. **I wrote that about the agents and then did it myself.**

## RESUMED 2026-08-12 ~9:50am ET — budget-gated, cron `4f317fc6` hourly at :47

Arnon's instruction: keep going, but **check usage every heartbeat and pause before the limit**, leaving room for the heartbeat itself. *"I don't mind if you have to pause for some hours. I just want you to not be interrupted by limits as the cost of recovery is wasteful."*

**Stop rule: dispatch nothing at weekly >= 95%.** The 5% reserve covers in-flight agents finishing, the heartbeat, and Arnon's own work. Under-spending is the correct error.

### Pacing log — read the weekly % every heartbeat, differences give the per-batch cost

The request counters (`Last 24h`, `Last 7d`) are **sliding windows**, so differencing them mixes new requests with old ones ageing out — on 08-12 the 24h window still contained the twelve-agent period. **The weekly percentage is the only cumulative, unconfounded signal.** Coarse (one tick ~232 requests), but a tick is a tick.

| time (ET) | weekly | note |
|---|---|---|
| 08-12 09:05 | 88% | pause decided |
| 08-12 09:40 | 88% | all agents finished; tree verified |
| 08-12 09:45 | 88% | ~40 min of pure conversation moved it < 1% — **talk is cheap, batches cost** |
| 08-12 09:50 | 88% | resumed: `test_log_writer.py`, `test_rule_entry.py` |
| 08-12 10:05 | 88% | `test_log_writer.py` **done** — a full one-file batch did not tick the weekly |

| 08-12 10:25 | 88% | `test_rule_entry.py` **done** — two full one-file batches, still no tick |

| 08-12 10:45 | **89%** | FIRST TICK — `test_session_start.py` done; `test_change_role_classifier.py` out |
| 08-12 11:05 | 89% | `test_rule_sort.py` done; `test_tools_security_audit.py` out |
| 08-12 11:47 | 89% | heartbeat — two alive (`change_role_classifier` 15m, `security_audit` 5m), nothing dispatched |
| 08-12 12:25 | 89% | `test_change_role_classifier.py` done; `test_migration.py` (2820) out. **Second full hour inside one tick** |
| 08-12 12:55 | 90% | second tick — `security_audit` + `migration` done |
| 08-12 13:15 | 91% | third tick — `compound`, `hook`, `resolve` done; exact remaining list measured |
| 08-12 13:47 | 91% | heartbeat — two alive (`installer` 3m, `configuration` 45s), nothing dispatched |

**Steady state, three ticks in: roughly one tick (~232 requests) per two to three completed one-file batches.** From 91%, the 4% before the stop line buys ~9 more batches; four files remain. **The tier finishes inside this budget with room to spare** — the original 8-hour horizon was wrong by a wide margin because it averaged over the twelve-agent period.

### Ticket narrative goes; a PRODUCT RUNBOOK POINTER stays — new rule, earned

The `test_tools_installer.py` batch cut `(Phase 7.1 encapsulation)` labels as ticket narrative, then **grepped `docs/install.md`, found Phases 3-10 with sub-phases 7.1 and 10.1 genuinely documented, and restored them.** A `TOO-15` label stayed cut, because no runbook section matched it.

So the test is not *"does it look like a reference"* but **"does the thing it points at exist, and is it product documentation rather than development history?"** Same string shape, opposite disposition, and only a grep separates them. Notably the agent caught this **mid-sweep, on its own work** — the loop working inside a single pass rather than across passes.

### A false hazard note is worse than none — new rule, earned

`test_change_role_classifier.py` carried a comment claiming a `chmod` restore was needed *"so tempdir cleanup can remove it."* The editor **executed `shutil.rmtree` against a `0o000` file**, watched it succeed, and deleted the comment. Keeping it would have taught every future reader to preserve a pointless step.

So the hazard carve-out is not "keep anything that looks like a warning" -- it is **verify, then keep**. Both directions of that check have now paid: one batch restored a real hazard note it had over-deleted, another removed a fake one it could have kept for free.

### The TOO-52 shape now has three independent instances — worth a comment on that ticket

*A Given/Then that is TRUE about what the code does and WRONG about what it is for.* It passes every probe, so no amount of falsification finds it; it is only visible by reading the claim against an independent statement of purpose.

| file | the sentence | the defect it blesses |
|---|---|---|
| `test_tools_consolidate.py` | frames the DEFAULT multi-token over-match as the baseline consolidation must preserve | proposed ticket 18 |
| `test_rule_sort.py` | describes a comment silently re-attributing to a different rule after a sort, and calls it **"not a bug"** | `rule_sort` lead #2 |
| `test_rule_entry.py` (near-miss) | a docstring **justifying its own weak decoy** with a reason that is false | the dead `endswith` check |

The third is a variant worth naming separately: not "this defect is intended" but "this test is weak **for a good reason**" -- where the reason does not hold. Same effect, since both stop the next reader from looking.

**The tick priced it.** One tick (~232 requests) covered **three completed one-file batches plus a fourth dispatched, plus ~6 coordinator turns** — roughly **65-70 requests per one-file batch**. At that rate the remaining 11% (~2,550 requests) buys on the order of 35 batches against ~20 remaining files. **The tier can probably finish inside this budget**, which the 24h-average extrapolation said was impossible.

Caveat on precision: an integer-percent boundary is coarse. Crossing 88 -> 89 means one boundary was passed, not that exactly 232 requests elapsed since the previous reading. Treat 65-70/batch as an order-of-magnitude figure and refine it at the next two ticks; the giants (`test_configuration.py` 4063, `test_hook.py` 3340) will cost more per file than the 1,200-line ones measured here.

**First real per-batch datum: one 1,200-line file at one agent costs well under 232 requests** (under a tick). Combined with "40 minutes of conversation also cost under a tick", the budget buys considerably more than the 8-hour horizon extrapolated from the 24h average. Keep sampling — the tick boundary is what will actually price it.

Earlier extrapolation of ~342 req/hour came from a 24h average spanning 12-, 6-, 1- and 2-agent periods. The two-agent marginal rate looks closer to **~165/hour**, which roughly doubles what the remaining budget buys. Refine it from this table, not from the 24h counter.

### EXACT remaining list, measured 2026-08-12 ~13:15 (not from bookkeeping)

Derived as the set difference between `git ls-files test/` and the files with working-tree changes. **Everything else in `test/` is swept.**

| file | state |
|---|---|
| `test_configuration.py` (4063) | **dispatched** |
| `test_tools_installer.py` (3329) | **running** |
| `test_architecture_fitness.py` (3975) | to do — the last big one |
| `test_tools_rule_apply.py` | to do — small |
| `test/__init__.py`, `test/unit/__init__.py` | to do — trivial |
| `_config_isolation.py`, `_once_per_isolation.py`, `_real_log_dir_guard.py`, `_real_once_per_home_guard.py`, `_subprocess_harness.py` | to do — helpers, one batch |
| `test/verdict_corpus/__init__.py`, `fixture_loader.py` | to do — trivial |

**So: two big files and one batch of small ones, and `test/` is done.**

A caution about the method, since it will be reused: "has working-tree changes" is a proxy for "swept", and it was briefly wrong. Several files were modified by *earlier* punch-list items and looked swept; those modifications were then **committed**, which reset them to clean and made them correctly appear as remaining. The proxy only holds because the sweep's own changes are all uncommitted. **Once Arnon commits #07, this method stops working** -- record the finished list before that happens.

### Earlier estimate, superseded by the list above

13 files over 1,200 lines, ~32k lines total: `test_log_writer.py` (1204), `test_rule_entry.py` (1212), `test_session_start.py` (1328), `test_rule_sort.py` (1568), `test_change_role_classifier.py` (1733), `test_tools_security_audit.py` (2103), `test_migration.py` (2820), plus the giants already carrying pre-sweep modifications from other punch-list items: `test_resolve.py` (2855), `test_compound.py` (3005), `test_tools_installer.py` (3329), `test_hook.py` (3340), `test_architecture_fitness.py` (3975), `test_configuration.py` (4063). **One file per agent at this size.** The current budget will not finish this; that is expected and accepted.

## Earlier: PAUSED 2026-08-12 ~9:15am ET on the WEEKLY budget, not on a stall

Cron `cba7d004` deleted. Batches 18 and 19 were left to finish; **no new batches dispatched.**

Measured with `~/bin/claude-usage` (a capability I did not know I had until Arnon pointed at it — see auto-memory `reference_self_usage_monitoring`):

| quantity | value |
|---|---|
| weekly used | 88%, resets Aug 13 10am ET (~25h away) |
| requests per 1% | 20,408 req / 88% = ~232 |
| remaining budget | ~2,780 requests |
| burn rate | 8,204 req in 24h = ~342/hour, **100% of it this sweep** |
| time to exhaustion at current pace | **~8 hours**, i.e. mid-afternoon |
| rate that survives to reset | ~111/hour = **one third of current** |

The risk is not that the sweep stalls -- an interrupted comments-only editor leaves valid code either way, proven twice. The risk is that Arnon has **no Claude Code at all** for the last 17 hours of the week, spent on the lowest-yield tier of the sweep.

**Yield asymmetry that makes this an easy call**: all six defect tickets came from `toolguard/` and `tools/`. The `test/` tier has produced **zero product defects across 62 files** -- its output is cannot-fail assertions and undetected mechanisms. Real value, but not worth the week's remaining budget.

### Verified quiescent 2026-08-12 ~9:40am ET — all agents finished, nothing in flight

Batches 18 and 19 completed after the pause and were not replaced. Final gate:

- `comment_hygiene --compare-against HEAD`: **only** `toolguard/__init__.py` and `tools/architecture_fitness.py` — zero drift on all 72 swept `toolguard/` files, which is what rules out a left-behind mutation.
- `git diff --stat toolguard/`: 5,383 insertions / 10,282 deletions, **all comment churn** (~4,900 net lines of prose removed from the package).
- Full suite 2733 OK and ruff clean, run independently by both final batches.

**Open coordinator item raised by batch 19**: three Given/Then clauses in `test_tools_maintenance.py` carry TOO-19 ticket-narrative parentheticals *inside* the Then text. The settled precedent forbids rewriting a **false** GWT to match the assertions; it says nothing about trimming a ticket reference out of a **true** one. That is a different question and needs a decision before any pass claims authority to edit inside GWT prose.

Resume after the reset. ~28 files remain, all tail: `test_log_writer.py` (1204), `test_rule_entry.py` (1212), `test_session_start.py` (1328), `test_rule_sort.py` (1568), `test_change_role_classifier.py` (1733), `test_tools_security_audit.py` (2103), `test_migration.py` (2820), plus helpers.

## TOO-52 exists — the sweep's method is now its own ticket (2026-08-12)

Arnon filed **TOO-52** to design a specialised claim-falsification review skill, from the observation that #07 keeps finding defects it was not looking for. **Standing permission to add comments to TOO-52 as findings accrue** (granted 2026-08-12; applies to that ticket only). First comment posted: *prose that documents a defect as the contract* — a finding class discovered after the description was written.

Anything in the rest of this queue that is about **method** rather than about toolguard belongs in TOO-52, not here.

## FOR THE POST-#07 DISCUSSION (Arnon, 2026-08-12) — read this section first

### The finding that only appears when the queue is read whole

**`issue_takeover_warning` has two tests and neither can fail.**

- `test_logging_streams.TestTakeoverNoticeNotPersisted` globs a `logs/` directory **nothing in the test ever creates**, guarded by `if log_dir.exists() else []`. The "no log file" half passes unconditionally.
- `test_session_warnings.test_does_not_call_log_warning` patches `toolguard.error_log.log_warning` — but `session_warnings.py` imports **only `sys`** and never reaches that module. Deleting the function body leaves it green.

Two different batches found these, hours apart, neither agent aware of the other. Each was filed as "here is one weak test". Side by side they say something else: **this behaviour is unpinned.** The individual rows systematically understate the picture, so the queue needs reading as a whole before any of it is actioned.

Batch 15 later confirmed both halves from inside `test_logging_streams.py` and queued them together — but only because its brief named the sibling. Left to itself it would have filed the same single row a third time. **The synthesis has to be a step, not a hope.**

### The measurement that reframes the tier

Mutation testing — copy the repo out of tree, delete one mechanism, run all 2,733 tests — has become the sweep's sharpest instrument. Latest full run: **42 mutations, 23 survived. A 55% survival rate.**

Undetected mechanisms now number ~46 and include: `danger()`'s entire `findings.sort()`; `_is_blanket_allow`'s GLOB branch; the NATIVE pattern type rebound to GLOB (confirmed independently from two different test files); `iter_dirs_upward`'s home stop; `.env`'s whole-line `#` skip; `run_git`'s `timeout` **and** `GIT_TERMINAL_PROMPT=0` — the exact mechanism `install_update.py` credited with *"no git subprocess here can hang"*, a claim this sweep had already narrowed.

### Three tickets have a matching "and here is why the tests missed it"

| ticket | defect | why it survived |
|---|---|---|
| 17 | `[native]` under-matches | 15 tests pass with NATIVE rebound to GLOB |
| 19 | splitter drops commands | 13 of 18 parser tests assert only "does not raise" |
| 22 | redundancy calls unsafe deletions safe | that file has no takeover layer at all |

These were **not** found by looking for test gaps. Each fell out of asking, in a comment sweep, *is this sentence true?*

### A live code defect found through a test's docstring

**The config cache can return stale data.** Key is `(path, format, st_mtime_ns, st_size)`. A test docstring claimed a same-mtime rewrite still invalidates; it does not — that test passes only because its fixture grows 26 -> 79 bytes. Constructed: `["Bash"]` -> `["Read"]`, both 26 bytes, mtime restored -> second read returns `['Bash']`. Narrow reachability (one process per hook call), but `--apply`/`--annotate` are long-lived read-modify-write callers and **produce exactly the equal-length rewrites**.

### My own errors, corrected by agents

Fifteen-plus briefs contained mistakes that editors caught and refused. Two reached filed tickets: a **five-vs-four** miscount of the over-granting seeded rules, and a **`test_hard_deny` mis-attribution** that was a name collision with `test_api.TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command`. Ticket 18 now carries two disagreeing 20-failure breakdowns from two runs, deliberately unreconciled — they most likely applied **different repairs**, which means the blast radius depends on the fix chosen.

### Verification hole worth fixing

The post-stall check (zero code-shape drift, ruff, 2733 tests) assumes **comments-only** edits. Mutation testing breaks that assumption deliberately. An agent that mutates the tree and dies before reverting leaves a deleted mechanism that the check passes — because a deleted guard changes no comment shape, and the suite is exactly what proved it has no coverage. The cron now also requires `git diff --stat` on `toolguard/`.

## STATUS 2026-08-12: `toolguard/` and `tools/` COMPLETE; `test/` tier in progress

**Swept and verified**: all of `toolguard/` (top level, `parser/` hand-written, `scripts/`, `testing/`, and all 30 `tools/` modules), plus all 10 `tools/*.py` dev instruments. Zero code-shape drift throughout, 2733 tests green at every checkpoint, ruff clean.

**`test/` tier**: 56 of 88 files done across 15 batches. ~32 files remain, weighted heavily in the tail (nine files over 1,000 lines; `test_migration.py` is 2,820). Batch 16 (`test_tools_consolidate.py`, `test_tools_takeover_audit.py`) in flight.

### Six tickets filed, all from `toolguard/` and `tools/` — none from `test/`

| # | Layer | Failure |
|---|---|---|
| 17 | matcher | `[native]` under-matches — deny rules that do not fire |
| 18 | matcher | DEFAULT multi-token over-matches — **live in five seeded self-permission rules** |
| 19 | extractor | commands never reach a verdict (3 bypasses) — **and the parser's own tests cannot fail** |
| 20 | analyzer | consolidation escalates `ask`->`allow`; `--apply` writes it; the approval diff carries unrequested normalisation |
| 21 | analyzer | danger detector: 4 of 6 categories dead, 6 blanket-allow forms invisible |
| 22 | analyzer | redundancy engines report unsafe deletions as safe |

Plus `EL1` in the queue: `error_log.log_crash`'s `Path.home()` above the `try` — a fail-open that can make the hook exit with **no decision on stdout**. Highest severity single row.

### What the `test/` tier is producing

**~25 tests whose assertions cannot fail, across 56 files** — roughly one per two files. No new product tickets; this tier buys test-suite quality, not defects.

Two more undetected mechanisms from batch 15, both zero failures above the floor: `api._decide_bash`'s tool override rebuilt as `dataclasses.replace(result, tool=tool, reason="", matched_rule=None, provenance=None)` — it can destroy `reason`/`matched_rule`/`provenance` on **every MCP-terminal decision** and nothing notices; and `config_divergence.check_and_warn_divergence`'s once-per-day **pre-check** disabled, which makes an already-warned day re-run `load_configuration` + `find_divergent_patterns` on every PreToolUse call.

The catalogue of shapes is the durable artifact and is worth keeping independently of this ticket:

1. Absence asserted against a fixture that cannot produce the presence.
2. A mock on a path the code never takes.
3. `assertIs` defeated by interning (`"toolguard"` is identifier-shaped; `10` is small-int cached).
4. The asserted value is what **every** alternative also produces.
5. The subject is stripped upstream before reaching the code under test.
6. Equal frozen-dataclass fixtures collapse into one dict key.
7. The failure case makes the module fail to **import** — errors on collection, never fails.
8. `assertEqual(x, x)`, or both sides computing the same thing.
9. `assertIsNotNone(x)` where the function raises rather than returning `None`.
10. `hasattr(node, "label")` where the label came from the rule that produced the node.
11. `assertIn(literal, node.text)` where `node.text` IS the input literal.
12. The Then names a mechanism the assertions never check; the outcome is what a tie-break produces anyway.
13. `assertRaises(Exception)`, which a typo'd attribute also satisfies.
14. **The fixture's own setup provides an alternative route to the outcome**, so the named subject is irrelevant.
15. **A "control" test that never takes the comparison its name promises.**
16. **A dead assertion that can only fail after the line above it already failed.**
17. **A decoy row expired-on-write**, so "was it deleted?" and "is it expired?" are indistinguishable.
18. **Two tests differing by one flag, same expected verdict, neither observing the flag.**

19. **Two mechanisms that mask each other.** Each is undetected when deleted *alone*, because the single test that exercises them trips **both** at once. `touch_set_score.main`'s mutual-exclusion guard and its pairing guard: the one argument-validation test passes `--actuals --actuals-judge-1` and omits `--actuals-judge-2`, so either guard alone rejects it. Neither mutation is a finding by itself; the pair is.

Shapes 14-18 are not "vacuous" — they assert something real about the **wrong subject**, which is why they read as thorough in review.

Shape 19 is different again, and it is the **synthesis gap in miniature**: it is invisible to any process that scores mutations independently, exactly as the double-vacuous `issue_takeover_warning` finding is invisible to any process that reads queue rows independently. Same structure at two scales, found by two unrelated batches. That is now the strongest single argument that synthesis must be a step rather than a hope.

### Settled precedent, applied by five editors independently

**Do not rewrite a false or vague Given/Then to match what the assertions actually check.** An accurate rewrite leaves a green test that pins nothing, behind a Then nobody re-reads. Flag the mismatch; do not launder it.

### Open coordinator items

- **CLOSED 2026-08-12.** All eight `test/unit/CLAUDE.md` sites corrected to `.claude/rules/test-config-isolation.md`: `test_rule_entry.py` x2, `test_resolve.py`, `test_rule_sort.py`, and `test_configuration.py` x4 (three became corrected one-line pointers; the fourth went with the 40-line stale RED-phase block it was embedded in). Original entry below, kept for the record.
- **`test/unit/CLAUDE.md` is cited in 8 comment sites and does not exist.** The real file is `.claude/rules/test-config-isolation.md` (verified, and it has the checklist those comments reference). Sites: `test_configuration.py` x4, `test_resolve.py`, `test_rule_sort.py`, `test_rule_entry.py` x2. All four files are unswept — their sweep batches should fix it. (The `test/verdict_corpus/cases.jsonl` hits are fixture data, not citations — leave them.)
- **Six tickets are written and unfiled.** Filing to YouTrack is a write; Arnon's call.

## SLOW MODE from 2026-08-11 ~9pm: pool of ONE

Second session-limit stall (resets 11pm ET). Arnon: *"use only one subagent at a time, hoping that this would work without being interrupted."* Cron now fires hourly at :19 and dispatches **at most one** agent, preferring small files. A unit that completes beats six that die mid-file.

**Tree verified clean after the stall**: `comment_hygiene --compare-against HEAD` reports only `toolguard/__init__.py` and `tools/architecture_fitness.py` (both intentional non-sweep changes), ruff clean, 2733 tests OK.

### Interrupted, to re-dispatch one at a time

| unit | state when killed |
|---|---|
| `tools/danger.py` **pass 2** | had caught a false universal in its own new text and was fixing it |
| `tools/config_access.py` | at the verification gates |
| `tools/takeover_audit.py` + `clarity.py` | had only read the standard |
| `tools/uninstall_readiness.py` + `self_permission.py` + `recommended_protections.py` | verifying the `cd` command-substitution claim |
| `tools/rule_apply.py` + `redundancy.py` | reading the exemplars |
| `tools/log_harvest.py` + `transcript_harvest.py` | not started |

**Closed since the last stall**: `installer.py` (2326), `maintenance.py` (1299), `consolidate.py` (962), `security_audit.py` (826), the three parser modules, `rule_sort.py` (668), `once_per`/`file_lock`/`env_config`, `toml_scan`/`config_validation`, `error_log`/`auto_migrate`, `install_update`, and the `tools/` small-file batch.

### Still unstarted in `toolguard/tools/`

`decision_ledger.py` (388), `mining.py` (376), `hierarchy.py` (346), `replay.py` (274), `edit_proposal.py` (214), `annotate.py` (182), `corpus.py` (112), `environment_audit.py` (105), `migration_gate.py` (97). Then `tools/*.py` (10 files), then `test/**` (88).

## The rule every editor brief now carries

**When you replace a claim about safety or coverage, state what the code DOES and stop. Do not state what that MEANS.**

Across twelve files, *every* falsehood an editor newly introduced was a claim about what a mechanism **guarantees** — never about what it does. Four worked examples, all from editors doing the right thing procedurally:

- *"deliberately crude in the safe direction"* over five predicates — measurably false; crude in the **unsafe** direction.
- `"equivalence-preserving"` — sourced from the codebase, but the phrase appears **only inside a failure message**. Failing proves non-equivalence; passing proves nothing. Inverted into three docstrings.
- *"the `> 5` cutoff bounds `$( $( ) )` layers"* — the cutoff is inert.
- A **true** sentence whose colon made a logged defect read as **intent**.

`uninstall_readiness.py`'s module docstring is the same failure written by the original author, untouched by this sweep: *"not a wildcard grant"* (fair) *"so it can only do the one thing it is scoped to"* (false). Evidence that this is not an artifact of how editors are briefed — it is what people write about a safety mechanism they believe in.

## Five tickets filed against the permission engine and its analyzers

| # | Layer | Failure |
|---|---|---|
| 17 | matcher | `[native]` under-matches — deny rules that do not fire |
| 18 | matcher | DEFAULT multi-token over-matches — **live in the seeded self-permission rules** |
| 19 | extractor | commands never reach a verdict at all (3 bypasses) |
| 20 | analyzer | consolidation escalates `ask`→`allow`; `--apply` writes it; family 2 tightens even with a corpus |
| 21 | analyzer | danger detector: 4 of 6 categories dead, 6 blanket-allow forms invisible |

Plus `error_log.log_crash`'s `Path.home()` above the `try` — a fail-open that can make the hook exit with **no decision on stdout** (queue row EL1, highest severity).

## Earlier: RESUMED at a pool of ~6 (Arnon halved it after the first stall)

**All of `toolguard/` top level is now closed.** Every module through the editor -> review -> pass 2 loop, zero code-shape drift throughout, 2733 tests green, ruff clean.

Two files earned a plain **"nothing substantive"** from their reviewer: `update_check.py` and `config_divergence.py`. Those are the only two in the whole sweep.

Remaining: `toolguard/tools/` (~21 files), `tools/*.py` (10), `test/**` (88).

### The two findings that outrank everything else in this sweep

Neither is a comment defect. Both are in `reports/follow-up-queue.md`.

1. **`error_log.log_crash` is a fail-open in the hook.** `errors_dir = Path.home() / ".toolguard" / "errors"` sits *above* the `try`, and `log_crash` runs inside `hook.py`'s three top-level `except` clauses **before** `_report_crash_fault` and `_emit_decision`. An exception escaping it means the hook exits **with no decision on stdout** — the same class as the fail-open #04 fixed. One-line fix; needs a ticket, not this sweep.
2. **`rule_sort` can render a config file that no longer parses.** `_escape_toml_string` escapes only `\\` and `"`, so an `additionalContext` containing `\n` emits the multi-line inline table the module docstring exists to forbid. Since a parse failure clamps every governed decision to `ask`, one enrichment string bricks the config into permanent prompting. Reachable from a JSON config's `"additionalContext": "line1\nline2"`.

Also: a comment reading *"NEVER remove: this is what blocks the force push"* **silently re-attributes to a different rule** after a sort — the first rule's leading block anchors to the top of the sub-list rather than travelling.

### The false claim that had four homes

*"A config-layer module must not depend on `error_log`, a runtime-layer module."* `.pyscn.toml:202` puts `error_log` in `observability`, and line 253 explicitly permits `config` -> `observability`. There was never a violation to avoid. Two copies cut by the `config_divergence`/`config_validation` editor; `hook.py` and `test/unit/test_logging_streams.py:786` fixed by hand.

### What the loop is actually buying, measured

Reviews are catching about as many defects the **editor newly wrote** as ones it carried through. **Sharpening a vague-but-true sentence into a crisp-and-false one is the single most common failure** — `install_update`, `normalization`, `session_start`, `rule_sort`, `env_config`, `tool_spec`. A single-pass sweep would have shipped all of it.

Three times an agent caught an error in **the coordinator's own brief**: `file_lock`'s caller (it is `permission_migration.migrate`, not `auto_migrate`), a proposed `retention > period` hazard that a boundary sweep **refuted** (`days=1` satisfies the invariant exactly), and a proposed restoration that would have asserted provenance `merge_entries` does not supply on that call path. **An editor that rejects a proposed sentence with evidence is doing the job correctly** — say so in every brief.

## Earlier: STOPPED 2026-08-11 on the session token limit

Eight agents died mid-work. **The tree is consistent** — verified after the fact: zero code-shape drift on every swept file, `ruff check` clean, 2733 tests OK. The comments-only constraint is what makes an interrupted editor safe: it leaves valid Python either way.

### To resume, dispatch these — they are the interrupted units, not new work

| unit | what it was doing |
|---|---|
| `install_update.py` **pass 2** | had the full findings list; got as far as reading. Re-dispatch from scratch. |
| `once_per.py`/`file_lock.py`/`env_config.py` **review** | was in Phase 2 |
| `rule_sort.py` **review** | had key results, was on follow-up probes |
| `toml_scan.py`/`config_divergence.py`/`config_validation.py` **review** | was writing its verification harness |
| `parser/{command_extractor,command_model,multiline}.py` editor | partway; **never touch `bash_parser.py`** |
| `testing/sandbox.py` + `scripts/migrate_permissions.py` editor | had verified the CLAUDE.md sandbox claim holds; was recording follow-ups |
| `tools/installer.py` editor | was verifying outward claims |
| `tools/{project_root,self_integrity,working_tree,sorters,pattern_overlap,__init__}.py` editor | `project_root.py` done, was starting `self_integrity.py` |

### Also queued, never started

`error_log.py`/`auto_migrate.py` **pass 2** — the review is complete and its findings are in this session's transcript. **The most consequential item in the whole sweep is here**: `log_crash`'s `Path.home()` sits above the `try`, and `log_crash` runs inside `hook.py`'s three top-level `except` clauses *before* `_report_crash_fault` and `_emit_decision`. An exception escaping it means **the hook exits without emitting a decision on stdout** — a fail-open of the same class as the one #04 fixed. One-line fix (move two lines inside the `try`), but it is a code change, so it belongs in a ticket, not in #07.

Then: the rest of `toolguard/tools/` (~23 files), `tools/*.py` (10), `test/**` (88).

Arnon approved unattended execution 2026-08-11, after reviewing and accepting `config.py` and `compound.py`. He spot-checks the result; he does not review each file.

**The standard is [[TOO-45 comment standard]]. The accepted exemplars are `toolguard/config.py` and `toolguard/compound.py` in the working tree.**

## Per-file loop

Editor pass → cold review (read cold, verify every checkable claim, then diff-check for losses) → editor → … until a reviewer returns nothing substantive. Observed cost on the two calibration files: **4–5 editor passes, 4 reviews each.** Small files should converge faster.

## Two mechanics that make concurrency safe

1. **No editor touches `technical-notes.md`.** It is the one shared file and two concurrent agents would collide in it. Editors that judge something worth relocating put the proposed text in their report; the coordinator applies them serially at the end.
2. **One file per agent, no overlap.** Different files never conflict.

## Progress

| file | state |
|---|---|
| `config.py` | **accepted by Arnon** — frozen, do not touch |
| `compound.py` | **accepted by Arnon** — frozen, do not touch |
| `api.py`, `constants.py` | done — review 2 found no false claims; two presentation fixes applied by hand |
| `resolve.py` | 673 -> 347; three editor passes, two reviews, "ready" |
| `config_types.py` | 1079 -> ~745; three passes, two reviews + delta **clean** — DONE |
| `log_writer.py` | three passes, two reviews + delta; one antecedent fix applied by hand — DONE |
| `once_per_store.py` | three passes, two reviews + delta **clean** (ASTs byte-identical) — DONE |
| `install_provenance.py` | two passes, two reviews — **accept**; one de-enumeration applied by hand — DONE |
| `config_write_guard.py` | two passes, two reviews — **accept**, loss check empty twice — DONE |
| `hook.py` | 1447 -> ~1345; three passes, two reviews + delta; four fixes by hand — DONE |
| `error_reporter.py` | two passes, one review + delta; two fixes by hand — DONE |
| `file_matching.py` | two passes, one review + delta **clean** — DONE |
| `permission_resolution.py` | 444 lines; two passes, one review + delta; one fix by hand — DONE |
| `permissions.py` | two passes, one review + delta; two fixes by hand — DONE |
| `tool_spec.py`, `issues.py` | two passes, one review + delta **clean** — DONE |
| `patterns.py` | two passes, one review; **delta running** |
| `normalization.py` | two passes, one review; **delta running** |
| `session_start.py` | two passes (557 -> 445), one review; delta pending |
| `rule_entry.py` | pass 1 done, review found 6 defects; **pass 2 running** |
| `install_update.py`, `update_check.py` | pass 1 done (549->435, 68->46); **review running** |
| `auto_migrate.py`, `error_log.py` | pass 1 done; **review running** |
| `path_utils.py`, `_git.py`, `session_warnings.py`, `__init__.py` | pass 1 done (403->317, 70->51, 39->25, 10->3); **review running** |
| `rule_sort.py` | editor pass 1 running |
| `toml_scan.py` | editor pass 1 running |
| `config_divergence.py`, `config_validation.py` | editor pass 1 running |
| `once_per.py`, `file_lock.py`, `env_config.py` | editor pass 1 running |
| `parser/{command_extractor,command_model,multiline}.py` | editor pass 1 running — **never touch `bash_parser.py`, it is generated** |
| `testing/sandbox.py`, `scripts/migrate_permissions.py` | editor pass 1 running |
| `tools/installer.py` (2483 ln) | editor pass 1 running |
| `tools/{project_root,self_integrity,working_tree,sorters,pattern_overlap,__init__}.py` | editor pass 1 running |

**Seventeen of ~30 `toolguard/` top-level modules closed; every remaining one is in flight.** Zero code-shape drift throughout, 2733 tests green, corpus byte-identical.

Still unstarted: the rest of `toolguard/tools/` (~23 files, ~11k lines), `tools/*.py` (10 files), `test/**` (88 files).

## Three defects found by execution, none of them comment defects

The sweep's real output. Each was found by *running* a claim that had survived years of careful reading.

1. **`patterns.py` NATIVE end-anchor false negatives** — filed as `proposed-tickets/17-...md`. 416 false negatives in 7,623 brute-forced pairs, never a false positive; a trailing `*` immunises. `docs/permission-patterns.md:115-118` advertises two examples in the failing class. On a deny rule this is a silent bypass.
2. **`rule_entry.py` silent inert deny** — `normalize_entry("Bash(rm -rf /)\nBash(dd *)")` is accepted with no issue, scoped to Bash, displayed as configured, and matches nothing: the fullmatch that would strip the wrapper is the same one the newline defeats. No bypass (`permissions.py:111-125` independently excludes newline-bearing commands), but an inert **deny** is a rule the operator believes is in force, with no warning at any level.
3. **`session_start.py` log-dir divergence** — `_detect_conflicts` scans `config.project_root / "logs"`; the hook that *writes* those logs uses `env_config.get("log_dir")`, honouring `TOOLGUARD_LOG_DIR` and a **different** root-finder. Set that env var and the dynamic-conflict nag silently never fires. Its only trace was a comment saying "same logic as the PreToolUse hook" — which was false, so deleting it was right, and the divergence would have gone with it.

Also: `toolguard/__init__.py` declared `__version__ = "0.1.0"` against `pyproject.toml`'s `0.5.1`, undetected because nothing reads it.

## A wording correction worth keeping

Ticket 17's first characterisation — *"whose final literal also occurs earlier in the command"* — is **necessary but not sufficient**, and was corrected before filing. As a predicate it under-fired 0 times but **over-fired on 204 pairs**: `NATIVE 'a*a'` vs `'aa'` matches correctly, because the earlier `a` was consumed by a preceding segment and so was never in the final segment's search window. The condition is about the cursor, not the string. Caught by an editor re-verifying a reviewer's proposed sentence instead of pasting it — which is the loop working in the direction it is usually needed least.

## Two behavioural defects the sweep found in the matching layer

Neither is a comment defect. Both were found by **executing** a claim instead of reading it, and neither would have been found by reading.

1. **`permissions.py`** — the GLOB and NATIVE branches bypass the DEFAULT newline guard, and *any* colon triggers the `cmd:args` split.
2. **`patterns.py`** — NATIVE's segment search is **first-occurrence via `str.find`, not greedy**. `match_pattern(NATIVE, "a*a", "aXaYa")` returns `False`. A `[native]` **deny** pattern can therefore fail to match a command it should match. This is security-relevant and wants a ticket of its own.

Also: NATIVE's documented "matches any sequence of non-whitespace characters" is false — it crosses whitespace and word boundaries freely. And `match_pattern`'s DEFAULT branch has no live caller anywhere.

## The recurring false claim, found three separate times

"A broken config file clamps **every** toolguard decision to `'ask'`." It does not — an already-`'deny'` decision is exempt. The corrected, hedged form is at `config.py:1526`; use that framing anywhere the claim appears at all. Found in `config.py`, in `session_start.py`'s docstring, and in a `session_start.py` **string** (left alone — strings are code — and logged in `follow-up-queue.md`).

**`docs/configuration.md:460` carries the same unhedged overclaim.** Out of #07 scope (comments only), in scope for `/documentation-review` before the push.

### How to run one file — the loop that works

Editor pass -> cold review -> editor pass -> ... -> **delta check** (narrow: verify only the last pass's edits, plus "did a deletion strand anything"). Observed cost, steady state: **2-3 editor passes and 2 reviews plus a delta check.** The two calibration files took more only because the rules were still being discovered.

Dispatch each editor with the standard, the two accepted exemplars (`config.py`, `compound.py`), and the emphasis list. Dispatch each reviewer with: read cold -> **verify every checkable claim, weighting outward ones** -> only then diff for losses. **The loss check is non-delegable to Arnon** — he reads the final file, never the diff, so a deleted fact is invisible to him.

**Never send an editor a correction while its reviewer is running.** That race happened once and cost a re-read.

### The review pass is not optional, and here is the measurement

On the four files reviewed since the unattended run began, the reviewer found defects **the editor itself newly wrote** on three of them, and on `tool_spec.py` it **refuted the editor's headline finding** outright — the editor had invented a second meaning for a field in order to criticise the field for having both meanings. On `normalization.py` the editor replaced an old wrong claim (`max 3 iterations to prevent infinite loops`) with a *new* wrong claim (`the loop rarely runs more than once`) that reads as verified. Measurement says it never runs more than once.

**Writing prose to fill a gap is as dangerous as leaving stale prose in place**, and it is worse in one respect: new text reads as freshly checked. A single-pass sweep would have shipped all of it.

### What the reviews actually find, in order of yield

1. **Claims that reach outside the file** (rule 0) — by far the largest category, every module.
2. **Prose the pass never touched** — on several files, *every* finding was in text carried through unexamined. "Shortening was done carefully; verifying was not done at all."
3. **Prose the pass wrote to fill a gap** — on `file_matching.py`, every defect came from new text and none from the cuts.
4. **`Args:`/`Returns:`/`Raises:` blocks** — the least-read prose in a module and consistently the last place a falsehood survives.
5. **Pattern/matching semantics** — must be *executed*, not read. Two false claims in one file survived careful reading.

### Open question for Arnon, found in the code and removed as prose

`hook.py`'s interactive guard (TTY with no piped JSON) carried a note addressed to Arnon directly:

> *"Exit code 0: informational, not an error (Arnon: change to non-zero if preferred)."*

Deleted as prose because a question to a specific person is not documentation, but it is **unresolved** and would otherwise be lost. The guard currently exits 0 when someone runs `toolguard` by hand in a terminal. Decide whether that should be non-zero; if it changes, it is a code change, not a comment one.

### Two items flagged for Arnon, not defects

- `once_per_store._STORAGE_ERRORS` keeps a pre-existing over-broad pyscn clause (the pyscn half does not bite for a two-name tuple). No worse than before the sweep.
- `once_per_store`'s lazy-path consequence lost the "*silently, with no exit code 2*" half. The agent declined to restore it on rule-0 grounds — this file cannot verify Claude Code's exit-code semantics. Defensible; Arnon's call.

## Cross-file comment fixes found en route — apply when that file's turn comes

Found while verifying another module; each is a comment defect in a file not yet swept. Do **not** fix them out of turn (concurrent agents), but do not lose them either.

- **`technical-notes.md:378` and `:441-446`** point at "the module docstring in `log_writer.py`" for "NOT date-partitioned, never size-capped/rotated". The module docstring contains neither fact; both live in the constant doc-comments. Coordinator's own file to fix.
- **`toolguard/tools/log_harvest.py:25-33`** claims per-sub-command entries fold provenance back into `Matched Rule` in a bracketed format. Stale — `hook._unit_matched_rule_for_log` and `log_writer`'s rendering keep provenance as its own field. `log_writer` is correct.
- **`toolguard/_git.py`'s module docstring** claims it "imports nothing else from `toolguard`" one line above `from toolguard.constants import GIT_TIMEOUT_SECONDS`.
- **`technical-notes.md`** names `toolguard/tools/installer.py` as a consumer of `install_provenance.py`; it is not.
- **`permission_resolution._resolve_unclamped`** carries the same stale "per-level `RuntimeVerdict`" phrase corrected in `config_types.py` — there is no per-level verdict; the per-level unit is `LevelMatch`/`LevelOutcome`.
- **`hook.py:1122`** and **`test/unit/test_logging_streams.py:201`** carry a stray "reconciliation" word from a deleted ticket narrative.

## Ordering — worst first, by prose-to-code ratio

Ratio is a **locator only**. It never says a file is done; the test is whether the module makes sense.

| batch | files | ratio |
|---|---|---|
| 1 | `config_types.py` (1079 ln), `api.py`, `constants.py`, `resolve.py` (672 ln) | 10.9x, 10.4x, 12.7x, 7.3x |
| 2 | `log_writer.py`, `once_per_store.py`, `install_provenance.py`, `config_write_guard.py` | 3.4–3.9x |
| 3 | `hook.py` (1447 ln), `error_reporter.py`, `config_divergence.py`, `file_matching.py` | 2.6–3.0x |
| 4 | `auto_migrate.py`, `error_log.py`, `normalization.py`, `config_validation.py`, `once_per.py` | 1.9–2.4x |
| 5 | `install_update.py`, `file_lock.py`, `env_config.py`, `permission_resolution.py`, `permissions.py`, `rule_entry.py`, `rule_sort.py`, `session_start.py`, `session_warnings.py`, `tool_spec.py`, `toml_scan.py`, `path_utils.py`, `update_check.py`, `issues.py`, `_git.py`, `__init__.py` | remainder |
| 6 | `toolguard/tools/*`, `toolguard/parser/*` (hand-written only — never generated parser code), `toolguard/scripts/*`, `toolguard/testing/*` | |
| 7 | `tools/*.py` — dev instruments, production rules | |
| 8 | `test/**` — **different, simpler rule**: keep the Given/When/Then, verify it describes what the test actually does, delete every other comment. Verification is local to the test body. | |

## Invariants for every file

- Comments and docstrings only. **Strings are code** and do not change even when wrong — flag them in `reports/follow-up-queue.md`.
- `tools/comment_hygiene.py --compare-against HEAD` reports **zero** code-shape drift for the file.
- Full suite green (2733), golden verdict corpus byte-identical, ruff clean.
- No git write commands. Arnon commits.
- Never touch an already-accepted file: `config.py`, `compound.py`.

## Refactor candidates go to the queue, never into the code

`reports/follow-up-queue.md` has the table. Two found so far (`validation_issues`, `judge_unit`), both spotted because **the comments clustered**.
