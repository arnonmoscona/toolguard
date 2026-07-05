---
title: 'TOO-15 P2 #8 Cross-Project Security Audit + Safety Floor - agreed design'
type: note
permalink: toolguard/too-15/too-15-p2-8-cross-project-security-audit-safety-floor-agreed-design
tags:
- TOO-15
- task-memory
- design
- safety-floor
---

# #8 Cross-Project Security Audit + Safety Floor - agreed design (2026-07-02)

Constraint (Arnon): keep it MINIMAL. Changes mainly in the SKILL, only minor code.
Accept lower initial reliability; harden later.

## What #8 is
- Cross-project audit: run the audit across several projects and consolidate.
  ALREADY SOLVED by existing tooling: `toolguard-audit --dir <proj>` loads config
  from any dir; project identification is a resolved strategy; proposed-migration
  context is already encoded/available to the skill. => pure AI directives, NO code.
- SAFETY FLOOR (the only new concept): the audit today is REACTIVE (flags dangerous
  ALLOWS). The floor is PROACTIVE: assert a baseline of protections MUST be present
  and flag their ABSENCE. Applies to current AND as-if-enacted config (migration/edits
  already in context), so it doubles as a gate: "would this change drop below floor?"

## Floor check mechanism (Arnon chose: precise probe)
For each floor item's canonical dangerous command C, EVALUATE C against the project's
config through the REAL resolver; verdict != "deny" => BREACH. "ask" counts as breach
(a catastrophic op that merely prompts is below floor). Using the real resolver means
[hard_deny] is consulted automatically -> no need to expose hard_deny in context.

## The ONE code change: `toolguard --eval` flag (~15 lines in hook.main())
WHY: the bare hook is NOT read-only when probed:
  1. run_auto_migration can WRITE config (backups, settings.local.json, toolguard
     config) on first invocation/day when a project has divergent native<->toolguard
     patterns + auto_migrate on. (run_auto_migration is an OLD blunt native->toolguard
     cleanup script, not security-aware -- must never fire during a security audit.)
  2. log_command pollutes each project's toolguard log with synthetic dangerous cmds.
`--eval` behavior when set: load env config + load_configuration, parse stdin hook
event, resolve via resolve_bash_permission_detailed / resolve_file_path_permission_detailed,
print the same `permissionDecision` JSON, exit 0. SKIP: startup validation, divergence,
auto-migration, logging, session warnings. Guaranteed read-only, no log noise.
Output shape identical to normal hook => skill parses verdict the same way.
Dir resolution: minimal = honor cwd (skill cd's into project); optional `--dir` nicety.

## Everything else = AI directives in SKILL.md (toolguard-security-audit skill)
- Floor table (data, not code): id | title | severity | canonical command(s) |
  suggested deny/hard_deny rule. v1 curated set (accept incompleteness):
  recursive-root-delete (rm -rf / ~ /*), disk-wipe (dd of=/dev/*, mkfs*),
  fork-bomb, pipe-to-shell (curl|sh, wget|bash), perms-on-root (chmod/chown -R /),
  secret-exfil (.env / key material via Read/Write/Edit), self-weakening (edits
  removing the hook / weakening toolguard config).
- Per-project loop: for each project, for each floor cmd -> `printf '<event>' |
  toolguard --eval` -> parse verdict -> BREACH if != deny.
- Consolidate into a projects x floor-items matrix + per-project severity.
- FLAG-ONLY: suggest the rule, never auto-add (consistent with suggest-never-auto-grant).

## Critical-thinking note / successor ticket
Audit-based floor DETECTS missing protection but does not PROVIDE it. The "right"
long-term design is shipping the floor as ALWAYS-ON default hard_deny rules
(protection by default > detecting absence) -- but that's behavioral + code-heavy,
correctly deferred to a future ticket. v1 = detect + suggest only.

## Status: DESIGN AGREED. Not yet implemented. Remaining before build:
- Confirm the v1 floor content list.
- Then implement: (1) `--eval` flag + tests; (2) SKILL.md directives.

## STATUS: BUILT (2026-07-02)
Code: `toolguard --eval` flag added to hook.py (`_resolve_event` read-only helper
mirroring main()'s dispatch + `_run_eval_mode`; uses load_configuration(cwd,
ignore_env_override=True) so a stale CLAUDE_SETTINGS_PATH can't divert the probe).
Tests: test/unit/test_hook_eval.py (7) - anti-drift vs decide(), fail-closed/not-governed
edges, and read-only (main() with --eval never calls log_command / run_auto_migration).
Suite 1242 green, ruff+ASCII clean. E2E smoke-tested: correct deny/allow verdicts,
correct project-rooted provenance, no logs written.
Skill: toolguard-security-audit/SKILL.md gained "Pass 3 -- Safety floor and
cross-project sweep" (floor table, --eval probe, verdict!=deny=BREACH, cross-project
matrix, applies to proposed state too) + intro/hard-constraint/when-to-use updates.
Learning: governed_tools() defaults to ('Bash',); a project that doesn't govern
Read/Write/Edit will breach file-tool floor items -> that's a REAL finding
("unprotected tool"), documented in the skill.
NOT YET: commit; optional code-review of the hook change; real-world dry-run on Arnon's
machine (he has ~2 active projects for validation).

## CODE REVIEW (code-reviewer subagent, 2026-07-03) + FIXES
Review found 1 High, 1 Medium, 2 Low. All addressed:
- HIGH (real bug, fixed): `get_env_config()` derived project_root from process cwd, so
  `extended_syntax` came from the WRONG project during a cross-project probe (rule
  hierarchy was correct via load_configuration(cwd), but env/.env axis wasn't). A project
  relying on [regex]/[glob] hard_deny + its own TOOLGUARD_EXTENDED_SYNTAX would get a wrong
  verdict. FIX: added `get_env_config(start_dir=None)` that anchors project_root to start_dir
  (bypassing TOOLGUARD_PROJECT_ROOT); `_run_eval_mode` passes the event cwd. E2E-verified
  (regex allow flips deny/allow with the PROBED project's .env). Regression tests in
  test_env_config.py (2).
- MEDIUM (fixed): `_resolve_event` had hand-copied main()'s dispatch (3rd copy). Refactored to
  delegate to `toolguard.tools.decision.decide` (the canonical side-effect-free primitive that
  DOES enforce hard_deny). Needs a LOCAL import (decision.py imports FILE_PATH_TOOLS from hook
  -> top-level import = circular; local import is the sanctioned documented-cycle exception).
  Verified both import orders work.
- LOW (fixed): `--eval` bypassed the TTY guard -> a human typing `toolguard --eval` would hang.
  Moved the --eval branch AFTER the TTY guard (skill pipes = not a TTY = passes; human = guard
  message). Zero extra code.
- LOW (fixed): added malformed-stdin --eval fail-safe test.
Suite 1245 green, ruff+ASCII clean. Confirmed-correct by reviewer: read-only guarantee,
decision fidelity, config hierarchy loading, conventions.
