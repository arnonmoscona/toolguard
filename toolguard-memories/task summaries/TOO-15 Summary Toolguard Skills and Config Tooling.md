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


## **Status:**
**Status:** Phasing P0->P4. P0 (deterministic foundation) committed (b10f6aa). P1
(security-flagging skill #6) DONE, awaiting Arnon review/commit. P1 delivers:
toolguard/tools/security_audit.py aggregator (danger()+audit_takeover() -> ranked
SecurityReport, render(), toolguard-audit CLI json/markdown/text + --strict);
two-pass bundled skills/toolguard-security-audit/SKILL.md (Pass1 deterministic;
Pass2 opt-in AI-assisted, separate same-style section, ordinal HIGH/MED/LOW
confidence); audit_context()/`--with-context` exporting the consolidated full
hierarchy (toolguard + Claude-native rules per layer) + takeover state +
neutralized ignore-list so the AI pass sees the same material and consumes the
takeover verdict; shared helpers discover_tools/neutralized_by_takeover extracted
from danger() (drift removal). Review fixes: exec detection hole, M2 CLI uses
load_config (ignore_env_override), blanket-allow docstring CRITICAL, --help
audience lines on all entry points. 1009 tests green, ruff clean.
Next: P2 = config maintenance/analysis (#3, TOO-11) incl. deferred transcript
harvesting; see plan note for the auto-mode-log forensic idea (likely separate).
