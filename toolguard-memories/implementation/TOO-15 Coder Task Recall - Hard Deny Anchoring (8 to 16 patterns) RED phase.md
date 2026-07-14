---
title: TOO-15 Coder Task Recall - Hard Deny Anchoring (8 to 16 patterns) RED phase
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-hard-deny-anchoring-8-to-16-patterns-red-phase
---

## Ticket
TOO-15

## Context
`toolguard/tools/recommended_protections.py` is the single source of truth for a curated
`[hard_deny]` "Sensitive files" pattern set written verbatim by `toolguard-install seed-hard-deny`.
Current canonical set has 8 patterns (all relative `**/...` forms):

```
Read(**/.env)
Read(**/.env.*)
Read(**/.aws/**)
Read(**/.ssh/**)
Write(**/.env)
Write(**/.aws/**)
Write(**/.ssh/**)
Edit(**/.env)
```

## Root cause of security gap
`toolguard/resolve.py`'s `_anchor_file_pattern`: any file-path pattern not starting with `/` or `~`
gets anchored (path-joined) to the ACTIVE PROJECT ROOT before matching. So `Read(**/.ssh/**)`
only ever protects `.ssh` paths INSIDE the currently active project -- not `~/.ssh/id_rsa` while
working elsewhere. Patterns starting with `~` are left unmodified and always resolve to the real
home dir. So both forms are needed: relative (project-local protection) + home-anchored (universal
protection).

## Fix already done (docs side)
`docs/security.md` "Recommended deny patterns" -> "Sensitive files" section now lists 16 patterns
(8 original relative + 8 home-anchored siblings). This is the SOURCE OF TRUTH for order and wording
-- must copy verbatim, not compose own variant.

## Required work (THIS SESSION = TESTS ONLY, RED phase)
1. (NOT YET -- future phase) Expand `_RECOMMENDED_HARD_DENY_PATTERNS` in
   `toolguard/tools/recommended_protections.py` from 8 to 16 entries, each with rationale.
   Update docstring/comments referencing "8".
2. (THIS SESSION) Update tests only:
   - `test/unit/test_recommended_protections.py`:
     - `_EXPECTED_PATTERNS`: update to full 16-pattern list (copy from docs/security.md).
     - Rename `test_contains_exactly_the_eight_canonical_patterns` ->
       `test_contains_exactly_the_sixteen_canonical_patterns` (or accurate name), update BDD
       docstring to match.
     - Add new test: for every relative pattern in the set, its home-anchored sibling is also
       present (structural invariant test, not just literal list match).
   - `test/unit/test_tools_installer.py`:
     - `_EXPECTED_HARD_DENY_PATTERNS` (duplicated 8-pattern tuple in `TestSeedHardDeny`, deliberately
       separate so that test module doesn't import recommended_protections). Update to 16-pattern
       list, same order.
     - Check for hardcoded counts like "8 patterns added" and update to 16.
3. Run full suite before and after. Baseline: 1430 tests, all green (per prompt; must verify).
   Confirm modified/new tests fail for the RIGHT reason (stale 8-entry expectation vs not-yet-
   updated 8-entry production list). Nothing else should regress.
4. STOP after tests are red. Report exact diff, before/after counts, why tests fail. Do NOT touch
   recommended_protections.py production code yet -- wait for explicit approval.

## Constraints
- Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples here). `uv run ruff
  check .` is fine.
- Use `uv run python ...` always.
- BDD Given/When/Then docstrings must stay in sync with what test actually does.
- Write report to
  /tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-hard-deny-anchoring-report.md

## Success criteria
- Only new/changed tests fail after edit; rest of suite unchanged (green).
- Failures are due to stale expectations, not typos/bugs in test code itself.
- 16-pattern list matches docs/security.md exactly, same order.
- New structural test proves "both forms present" invariant directly.
