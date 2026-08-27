---
title: TOO-45 re-triage 2026-08-20 - evidence and severity
type: note
tags: [task-memory, TOO-45]
permalink: toolguard/too-45/retriage-2026-08-20
---

# Re-triage of the open queue, 2026-08-20

Arnon: *"reevaluate and reprioritize tickets based on log evidence and severity judgement... Assume that we're only going to add new findings if they are both severe and have support in log evidence."*

## The structural finding that drives everything below

**Only about a third of the open tickets have a log signature at all.** A ticket fires in the logs when its trigger is a *command or rule shape*. Most of what remains is internal correctness — analyzers, config writers, tests, docs — where no corpus can speak and severity judgement is the only axis.

Second and more useful split: **runtime hook vs operator tooling.** The hook governs permissions on every tool call. The tooling (`consolidate`, `redundancy`, `clarity`, `maintenance`, `security_audit`, `takeover_audit`, `mining`) is advisory — Arnon runs it deliberately and reads the output. **A defect in an advisory analyzer cannot silently permit anything.** That is a severity difference of a whole tier, and roughly half the open list sits on the advisory side.

## Log evidence, 57,448 commands

| shape | featherhill | toolguard | total | ticket |
|---|---|---|---|---|
| command substitution `$(...)` | 5 | 1,115 | **1,121** | **79** |
| multi-token `:*` rules | 748 | 1 | **752** | **18** |
| blanket allow rule (`*`) | **60** | 6 | 66 | **21** |
| backticks | 0 | 98 | 98 | 34 |
| disclosure comment `#` | 5 | 652 | 657 | 36 |
| wrapper prefix | 3 | 103 | 106 | 82 |
| `&>` / `>|` / `<>` | **0** | **0** | **0** | 87 |
| `[native]` end-anchored | **0** | **0** | **0** | 17 |
| tilde+extended-type rule | **0** | **0** | **0** | 83 |
| regex ending in escaped ws | **0** | **0** | **0** | 84 |

**Read the featherhill column, not the total.** `36` and `34` are almost entirely toolguard's own dogfood — 652 of 657 disclosure comments are the agent's own mandated markers, which is a fact about this repo's process, not about users.

## TIER 1 — runtime, severe, do these

| # | why | evidence |
|---|---|---|
| **78** | in flight, 5 review rounds | committing now |
| **79** | **foreign inline code runs with no ASK floor** | **1,121** occurrences |
| **18** (+**20**, **22** downstream) | over-grant on the shape users actually write; index says schedule as one unit | **752**, 1 decision in 5 |
| **74** | **an empty registry allows every tool, hard-deny included** — the safety net fails open | code-reachable, not user-reachable |
| **19** | compound splitter — 3 shapes reach the shell never rule-matched | runtime bypass |
| **40, 39, 64, 70** | the **config-write / self-protection cluster**: any JSON passes verification; a hard deny moved into an allow passes; a ledger redirects a write into `$HOME`; applying an edit drops the parse-failure floor | no log signature — severity judgement |
| **21** | danger analyzer blind to 6 blanket-allow forms, and **featherhill has a live `*` rule** | 60 in featherhill |

## TIER 2 — Arnon asked for these explicitly

**85** (external-contract module, high priority per Arnon) and **81** (relative-`resolve` sentinel). Neither is defect-driven; both are architectural work he chose.

## TIER 3 — runtime but low, or fidelity only

**82** wrappers (fidelity, 3 real occurrences), **47** `TakeoverConfig` positional, **42** `normalize_entry` error discarded at 7 sites, **52** wrong-typed section discarded silently. Real, small, no urgency.

## TIER 4 — DEFER, zero or dogfood-only evidence

**87** (0), **17** (0), **83** (0, skipped), **84** (0, skipped), **34** (98, all dogfood), **36** (652 of 657 dogfood; Arnon already said skip absent evidence — the evidence that exists is our own process, not a user's).

## TIER 5 — advisory tooling remainder

**37, 53, 56, 57, 61, 62, 66, 72, 75.** All in the operator tier. None can silently permit anything. Batch them after Tier 1-2 or defer wholesale to a follow-up ticket.

## TIER 6 — meta, and one item that is overdue

**32's two items marked "fix before push" have been open since 2026-08-10** — the oldest thing on the list, and the index itself notes this is the *second* time the largest findings were left in a working queue. Do these regardless of tier.

Also: **07** remainder (~18 test files), **11**, **14** (takeover notice still bypasses the reporter), **16**, **31**, **33**.
