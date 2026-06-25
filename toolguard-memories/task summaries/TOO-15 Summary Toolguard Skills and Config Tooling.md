---
title: TOO-15 Summary Toolguard Skills and Config Tooling
type: note
permalink: toolguard/task-summaries/too-15-summary-toolguard-skills-and-config-tooling
tags:
- task-summary
- TOO-15
- TOO-11
---

# TOO-15 Summary - Toolguard Skills and Config Tooling

**What:** Design + build a set of skills around toolguard (TOO-11 = the config-maintenance
subset). Six artifacts: (1) bootstrap install doc, (2) project wiring + native->toolguard
migration, (3) config maintenance/analysis = TOO-11, (4) personal new-project setup, (5)
addendum assembly, (6) NEW security-risk flagging. General -> bundled `skills/`; personal ->
`tmp/skills/` staging.

**Status:** Explore/discuss converged; requirements + plan written, awaiting Arnon's review.
No code yet.

**Key decisions:** Thin skills over testable deterministic core. Allow/deny asymmetry.
Decision-replay diff as safety keystone (free, pure-Python; corpus scope is user's cost
knob). Human-in-the-loop edits. 4 consolidation families (3 strict + 1 agent-judged).
Takeover-mode awareness is critical for #6. Autonomous, interruption-tolerant test harness.

**Discovered defect:** bare/DEFAULT matcher over-broadens Read/Write/Edit single-`*`
(fnmatch crosses `/`; Claude gitignore `*` is single-segment). Fix in migrator; engine fix
likely separate ticket.

Full detail: [[TOO-15 Toolguard Skills and Config Tooling - Requirements and Plan]]
