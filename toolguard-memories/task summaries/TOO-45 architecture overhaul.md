---
title: TOO-45 architecture overhaul
type: note
permalink: toolguard/task-summaries/too-45-architecture-overhaul
tags:
- task-summary
- TOO-45
---

# TOO-45 architecture overhaul

**What it is.** Sequenced, judge-gated refactor of toolguard's core, executed largely by an
autonomous agent loop. Diagnosis: `config` + `permissions` + `compound` + `hook` + `log_writer`
+ `migrate_permissions` behave as one module filed into six files with no interface, with the
~30-module operator tooling consuming their internals. Hard invariant: no command may change
verdict.

**Status (2026-08-03).** Plan drafted and awaiting approval:
[[TOO-45 architecture overhaul execution plan]]. Branch `too-45`. Nothing implemented yet.

**Key decisions.**
- TOO-28 dropped as a precondition — Arnon set both fallbacks to `allow_with_no_warnings`,
  accepting the risk, mitigated by a safety inspector.
- Git writes relaxed for branch `too-45` only (`add`/`commit`; no push/checkout/stash/reset/...).
- Two checkpoints: CP1 after prerequisites (hard stop), CP2 after the first refactor step.
- **R0 demoted** to a prerequisite (it is an instrument, not a step).
- **R7 added** — directives as data, not hand-threaded fields. Nothing else in the step list
  could move the canary; `additionalContext` spans 14 production files today.
- **R1 promoted** from fifth to second — the internal/external seam must be replaceable under
  emergency time pressure when the Claude Code hook spec changes.
- **Two judges**, because "blinded" and "holds the big picture" contradict: a blinded reviewer
  whose value is its ignorance, plus a non-blinded architect judge for direction.
- Canary run by a fresh agent every time; no parallel agents on the working tree.

**Open.** Corpus privacy (17,167 real logged commands, public repo); final step order pending
the as-is picture; whether R6 needs its own ticket; whether config load/query splits.
