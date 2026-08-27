---
title: The hard-deny test class re-implemented production's ordering and so detected
  nothing
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/35-hard-deny-tests-tested-themselves
---

**FIXED in `05f786d` (TOO-45 phase 2).** Hard-deny tests now drive production's real entry point instead of re-implementing its ordering — see `test/unit/test_hard_deny.py:340-345` (`bdb7c95`); one dead guard remains at `toolguard/permissions.py:247`.

# `test_hard_deny.py`'s main class was testing itself

**The single most alarming measurement of the test-repair campaign so far**, found 2026-08-12.

## The measurement

Production's Bash hard-deny check was bypassed **entirely** — `if hard is not None:` → `if False:` in `resolve.resolve_bash_permission_detailed`. That removes the unoverridable-refusal mechanism completely.

`test/unit/test_hard_deny.py` produced **exactly one failure**: the end-to-end `main()` test.

**All ten tests in `TestHardDenyCommand` — the class named for the mechanism, in the file named for the mechanism — detected nothing.**

## The cause

The class's `_resolve` helper re-implemented production's hard-deny-first ordering in a local `_resolve_one` closure. The tests exercised the helper's copy of the logic, not production's. A faithful re-implementation in a test fixture is indistinguishable from correct behaviour until production drifts from it — at which point the tests keep passing and pin nothing.

Catalogue shapes 14 and 12 together, at class scale.

## Repaired

`_resolve` now calls `resolve.resolve_bash_permission_detailed(...)` — the same entry point `api.py` and `hook.py` use. Proven by two mutations:

- total hard-deny bypass: **0 failures before, 5 after**
- run the cascade first so an `ask` verdict beats the hard-deny pool: **0 before, 1 after** — the exact weakening the test's own Then names

## Why this one deserves its own ticket rather than a line in 31

`[hard_deny]` is the mechanism documented as absolute: pooled across all hierarchy levels, unoverridable by any allow rule. It is what a user reaches for when the cost of being wrong is high. **It was the least-tested mechanism in the file that exists to test it**, and the suite was green throughout.

The generalisable rule, worth more than the fix: **a test helper that re-implements the logic under test converts the whole class into a tautology.** Grep for other fixtures that reproduce production ordering rather than calling it. This is a mechanical check and a good candidate for the TOO-52 skill.

## Also found in the same module

- `test_hard_deny_non_list_deny_value_tolerated` used a **string** fixture where only a non-iterable could exercise the guard. Changed to an int; the guard is now load-bearing.
- `test_hard_deny_native_layer_structured_entry_contributes_nothing` — two mechanisms masking each other (shape 19); now observable via a `normalize_entry` spy.
- `test_hard_deny_and_hard_deny_entries_are_index_aligned` computed its expected value with the same helper the production path delegates to (shape 8). Replaced with literals.
- A dead `_build_config` helper, five parameters, called by nothing. Deleted.
- **One production dead-guard**, not repairable from the test side: `permissions.py`'s `if not deny_patterns:` early return cannot be pinned, because `match_command(cmd, [], ...)` returns the same answer anyway. Delete the guard or label the test a characterization — a production decision.