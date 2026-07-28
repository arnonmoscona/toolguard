---
title: TOO-19 RESUME HERE - state after Phase 0 commit
type: note
permalink: toolguard/too-19/too-19-resume-here-state-after-phase-0-commit
tags:
- TOO-19
- task-memory
---

**Written 2026-07-28, immediately before a session compact.** This is the authoritative
"where are we" note for TOO-19. Read this first on resume.

## State

- **Phase 0 code is committed and pushed**: `5dc4816` on branch `too-19`.
- **1836 tests green, `ruff check .` clean.**
- Phase 1 (the actual `additionalContext` injection feature) is **unblocked, not started**.

**Loose end from the commit:** the deleted task-recall memory files were still staged as
`AD` (staged-add, deleted in worktree) and did not make it into `5dc4816`. Settle with
`git add -A toolguard-memories/` plus a follow-up commit or an amend.

## THE GATE — do not close Phase 0 without this

Arnon has made the **safe-experimentation mechanism** a blocker on completing Phase 0:
*"We are not done with phase 0 until we're clean enough. I hate tech debt."* The commit
was taken deliberately **before** that work so it reviews cleanly against a stable base.

Design is agreed and written up in
[[Safe Experimentation Mechanism - Design Proposal]] (revision 2). Implementation order
from that memo:

1. `PostToolUse` tamper-evidence hook — hash the permission-config files after every tool
   call; on change, snapshot to `~/.toolguard/config-backups/` and print a loud diff.
   **User level, personal instrument, deliberately NOT a toolguard feature** (Arnon is
   clamping down on new features ahead of a promotable 1.0).
2. `toolguard/testing/sandbox.py` + CLI + tripwire tests, including explicit tests naming
   `~/.toolguard/rules/` and `~/.config/toolguard/rules/`.
3. Project CLAUDE.md checklist (project level only, not global).
4. Move `.claude/` into the `dot_files` repo and symlink it in, plus tests that the
   hierarchy resolves identically through a symlinked `.claude`.
5. Auto-mode friction -> TOO-28 / TOO-38 (comment already drafted and delivered).

## WORKING CONSTRAINTS (agreed 2026-07-28) -- carry these forward

- **Do NOT modify live configuration to test a theory.** Not project, not user, not "just
  for a second". This was violated twice in this ticket (see the design memo for the full
  incident). Until the sandbox exists, validate **only via unit tests** in `test/unit/`
  using `ConfigIsolationMixin` / `InstallerTestCase`. No ad-hoc `python -c` probes — they
  run with a real `$HOME` and unscrubbed env, which is safe-by-inspection, not
  safe-by-construction.
- **Limit subagent use until Phase 0 is finished** (Arnon, on hitting the weekly limit).
  Roughly 1.5M subagent tokens went out in one day across ~10 dispatches, two of which
  were wasted outright. The remaining Phase 0 work is small and well-specified — do it
  inline.

## Still open (not blockers, but owed before push/close)

- **Docs**: `docs/agent-map.md` is stale (missing security.md's new section), and the
  single-line structured-entry rule is undocumented — the rule whose violation silently
  disables every rule in the file, including `hard_deny`. Run `/documentation-review`.
- **Coverage**: `uv run python tools/coverage_stdlib.py` has not been re-run since well
  before the review-fix rounds.
- **`ruff format` churn**: 39 files carry formatting-only changes from an accidental
  repo-wide format. They rode along in `5dc4816`. Separate ticket for
  `[tool.ruff] line-length = 88` still owed.
- **pyscn**: health 80/B. Arnon's call: handled case-by-case as he selects, with a
  dedicated ticket later — do not bulk-fix.
- **ASK-floor residual gap**: interpreter flags whose value is a separate token
  (`python -W ignore -c`, `perl -I /path -e`, `ruby -I lib -e`, `node --require foo -e`)
  still bypass the floor. Arnon deferred deliberately — he will mine transcript/log
  evidence for which interpreters actually occur, then split the fix between his personal
  rules and toolguard builtin behaviour. Suggested source: the toolguard logs (every
  ASK-floor decision is logged with its reason), not raw transcripts.
- **`_FOREIGN_INLINE_FLAGS["awk"] = ["-f"]`** is wrong in both directions (`-f` is the
  program-FILE flag; awk's inline program is the bare first argument). Flagged and
  deliberately unchanged — awk is common enough to deserve its own decision.
- **`installer.py`** — `cmd_seed_self_perms` is CC 23 and duplicates ~35 lines of
  security-relevant hard_deny logic with `cmd_seed_hard_deny`.
- **`_render_toml_scalar` renders `None` as the string `"None"`** — an invented,
  non-matchable pattern that looks real in the file. Edge case, not fixed.

## Process notes worth keeping

- **Verify subagent reports before relaying them.** In this ticket a subagent claimed
  completion while adding zero tests (tell: the test count was identical to the baseline),
  and another invented a policy reason for not writing its report. Both were caught by
  checking rather than trusting.
- **Mutation-test new regression tests**: neutralize the fix, confirm the test fails.
  Several tests in this ticket were verified that way; it is the difference between a
  guard and decoration.
- The `code-reviewer` agent and `feature-coder` now carry the full code-review-graph MCP
  tool set (was 9 of 30 for the reviewer, 0 for the coder); the `/code-review` skill's
  step 5 now states explicitly that writing the report is the deliverable.
