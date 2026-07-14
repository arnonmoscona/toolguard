---
title: TOO-15 Coder Task Recall - Downgrade loose-no-match-fallback to LOW
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-downgrade-loose-no-match-fallback-to-low
---

## Ticket
TOO-15

## Task
Downgrade the `loose-no-match-fallback` audit finding in `toolguard/tools/takeover_audit.py`
from `AuditSeverity.MEDIUM` to `AuditSeverity.LOW`. This finding fires when `no_match_fallback`
is set to anything other than `'deny'` (i.e. `'ask'`, `'allow_with_warning'`, or the deprecated
`'warn_deny'` alias).

## Rationale (already agreed, not to re-litigate)
The project's own guided-install runbook (docs/install.md Phase 10) recommends enabling takeover
with `no_match_fallback = "allow_with_warning"` as the deliberate default posture. Tightening to
`deny` is framed as optional for max strictness. MEDIUM severity on the tool's own recommended
state is internally inconsistent / noisy. LOW still surfaces it, doesn't suppress it.

## Required production changes (DO NOT MAKE YET - RED phase first)
In `toolguard/tools/takeover_audit.py`:
1. Change `severity=AuditSeverity.MEDIUM` -> `severity=AuditSeverity.LOW` for the
   `loose-no-match-fallback` finding (invariant-4 block, ~line 429).
2. Update module docstring section describing invariant 4 (search "4. **MEDIUM /
   loose-no-match-fallback**" near top of file, ~line 29) -> "4. **LOW / loose-no-match-fallback**".
   Adjust prose minimally if it asserts MEDIUM-specific claims.
3. Update inline comment `# Invariant 4: Loose no_match_fallback (MEDIUM)` right above the
   AuditFinding(...) call -> `(LOW)`.
4. Grep whole toolguard/ package for "loose-no-match-fallback" / "loose_no_match_fallback" for
   other MEDIUM-severity claims; update only if explicit.

## RED phase tests to update FIRST (test/unit/test_tools_takeover_audit.py)
- Module-level docstring summary line ~line 9 ("Loose no_match_fallback yields MEDIUM finding")
- Section comment ~line 540 ("# Loose-no-match-fallback (MEDIUM)")
- Test class docstring ~line 545 ("Tests for the loose-no-match-fallback MEDIUM invariant.")
- Test function ~line 551-567: BDD docstring "Then a MEDIUM 'loose-no-match-fallback' finding is
  returned" -> LOW; assertion `self.assertEqual(fallback_findings[0].severity,
  AuditSeverity.MEDIUM)` -> `AuditSeverity.LOW`
- Grep whole test/ dir for "loose-no-match-fallback" for any other test file (integration-style,
  --strict exit-code tests) that might assert severity or rely on it for "highest severity" calc.

## Workflow (hard requirement - RED-then-checkpoint)
1. Read takeover_audit.py in full first.
2. Read test_tools_takeover_audit.py relevant sections + grep test/ for "loose-no-match-fallback".
3. Make TEST changes ONLY first. Run full suite:
   `uv run python -m unittest discover -s test -t .`
   Confirm ONLY the intended tests now fail (red), for the right reason (prod code still MEDIUM,
   test now expects LOW). Baseline: 1431 tests, all passing before changes.
4. STOP. Report exactly which files/tests changed, before/after full-suite counts, and why tests
   fail. Do NOT touch takeover_audit.py's production severity yet. Wait for explicit approval.
5. Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples) - `uv run ruff
   check .` is fine.
6. Use `uv run python ...` always, never bare python.
7. Write report file at
   /tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-fallback-severity-report.md

## Success criteria
- RED phase: only intended tests fail after test-only edits, baseline test count unaffected
  otherwise.
- After approval (GREEN phase): production change made, all tests pass, full suite count restored
  (same total, all green).

## RED phase status (2026-07-14)

Test-only edits complete in `test/unit/test_tools_takeover_audit.py` (5 locations:
module docstring line 9, section comment line 540, class docstring line 545, test
docstring + assertion in `test_warn_deny_fallback_flagged`). Production code in
`toolguard/tools/takeover_audit.py` NOT touched yet.

Full suite: baseline 1431 tests OK -> after test edit, 1431 tests, FAILED (failures=1),
exactly `test_warn_deny_fallback_flagged` failing with
`AssertionError: <AuditSeverity.MEDIUM: 2> != <AuditSeverity.LOW: 1>`. This is the
correct RED state -- STOPPED here per RED-then-checkpoint workflow, awaiting explicit
approval to proceed to the GREEN (production code) phase.

Full report written to
`/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-fallback-severity-report.md`.

## GREEN phase status (2026-07-14) - COMPLETE

Coordinator independently verified the RED state and approved. Made the three
production edits in `toolguard/tools/takeover_audit.py` (module docstring line 29,
inline comment line 424, `severity=AuditSeverity.LOW` at line 430). Full suite:
1431 tests, OK (0 failures/errors) -- restored to green, same total count as baseline.
`uv run ruff check .` -> All checks passed. `ruff format` intentionally skipped (project
convention). Not committed/pushed. Report file updated with GREEN results at the same
path as before.
