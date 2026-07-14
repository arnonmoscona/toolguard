---
title: TOO-15 Coder Implementation Report - Hard Deny Anchoring RED Phase
type: note
permalink: toolguard/implementation/too-15-coder-implementation-report-hard-deny-anchoring-red-phase
---

## Status: RED and GREEN phases both complete (GREEN approved by coordinator 2026-07-13)

## Summary
Expanded the canonical `[hard_deny]` "Sensitive files" pattern set from 8 to 16 entries
(8 original relative `**/...` patterns + 8 home-anchored `~/...` siblings), matching
docs/security.md's "Recommended deny patterns" section exactly, in order. This closes a
real security gap: relative patterns are anchored to the active project root by
`resolve.py`'s `_anchor_file_pattern`, so they never protected e.g. `~/.ssh/id_rsa`
while working in an unrelated project.

## Files changed

### Tests (RED phase)
- `test/unit/test_recommended_protections.py`: `_EXPECTED_PATTERNS` 8 -> 16 entries;
  renamed `test_contains_exactly_the_eight_canonical_patterns` ->
  `test_contains_exactly_the_sixteen_canonical_patterns` (docstring updated); added new
  `test_every_relative_pattern_has_a_home_anchored_sibling` (structural invariant test,
  derives `~/` sibling from each `**/` pattern via substring replace, asserts presence).
- `test/unit/test_tools_installer.py`: `_EXPECTED_HARD_DENY_PATTERNS` 8 -> 16 entries
  (same order); `test_adds_full_canonical_list_in_one_call` docstring "8" -> "16".

### Production (GREEN phase)
- `toolguard/tools/recommended_protections.py`: `_RECOMMENDED_HARD_DENY_PATTERNS`
  expanded from 8 to 16 `RecommendedProtection` entries -- 8 new home-anchored
  siblings appended in docs/security.md order, each with its own rationale (mirrors
  existing tone, notes it protects "regardless of which project is active"). Updated
  the comment above the tuple to describe the 8+8 structure; no other stale "8"
  references found (installer.py reads the list generically, no hardcoded counts).

## Test results
- Pre-existing baseline: 1430 tests, OK.
- RED (test-only edits): 1431 tests, FAILED (failures=4) -- all 4 for the correct
  reason (production still had only 8 patterns).
- GREEN (production fix applied): 1431 tests, OK (0 failures, 0 errors).
- `uv run ruff check .` (repo-wide): clean, both before and after GREEN.
- `uv run python -m py_compile` clean on the changed production file.
- `ruff format` intentionally NOT run (corrupts `except (A, B):` tuples in this repo).

## Full detailed report
/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-hard-deny-anchoring-report.md
(includes RED tracebacks, GREEN verification, and the exact 16-pattern list with
rationale summaries)

Run logs also in the same scratchpad dir: `baseline_run.txt`, `red_run.txt`,
`green_run.txt`.

## Scope
Single production file changed (`recommended_protections.py`), two test files updated.
Well within scope-inflation guard-rails. No async/threading/local-import
anti-patterns introduced.

## Not done / out of scope
Not asked to commit or push -- coordinator explicitly said not to. No further action
pending unless requested.
