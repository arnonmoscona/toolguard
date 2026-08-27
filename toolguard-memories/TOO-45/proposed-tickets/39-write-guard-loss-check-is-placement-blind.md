---
title: The write guard's content-loss check is placement-blind, so a hard deny rewritten
  into an allow reads as "nothing lost"
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/39-write-guard-loss-check-is-placement-blind
---

**PARTIALLY FIXED in `05f786d`.** A hard-deny egress check was added (`toolguard/config_write_guard.py:336-352`); still open: a `deny`->`allow` or `ask`->`allow` rewrite still writes successfully.

# A hard deny inverted into an allow passes verification

**Found 2026-08-13 by the test-repair campaign. Highest-severity finding in `config_write_guard.py`.**

## The defect

The content-loss check compares a **flat set of pattern strings**. It never records which list a pattern came from.

Measured against live code:

```
before:  hard_deny.deny      = ["Bash(rm -rf /)"]
after:   permissions.allow   = ["Bash(rm -rf /)"]
```

with `expected_patterns` computed from the original — **the write SUCCEEDS.** The pattern is still "present", so nothing was "lost".

## Why this is the worst case it could miss

`config_write_guard` exists because *"valid output is not the same as correct output"* — a file can parse perfectly and still have lost a rule. It catches deletion. It cannot see **inversion**.

And inversion is strictly more dangerous than deletion. Deleting `Bash(rm -rf /)` from `hard_deny` leaves the command unmatched, so it falls through to the cascade and most likely lands on `ask`. **Moving** it into `permissions.allow` makes the same command *allowed*. The single edit that most needs catching is the one the check is structurally blind to.

Every writer funnels through this guard: the maintenance skill, `toolguard-migrate`, `toolguard-install`, auto-migration.

## Status in the tree

Pinned as a **characterization test** — `test_pattern_moved_between_lists_is_not_treated_as_loss` — with a docstring saying loudly that it records a defect, not a specification. It was not made red-asserting-correct because the fix requires an API change (see below), and inventing a signature in a test would preempt that design.

## Fix direction

Make `expected_patterns` **list-aware**: carry `(list_identity, pattern)` rather than a bare pattern string, so a move is a loss from one list and an addition to another.

That is an API change to `verified_write_config`'s contract and touches every caller, so it is a real piece of design work, not a patch.

Cheaper interim option worth considering: verify `hard_deny` membership separately and refuse any write where a pattern leaves `hard_deny`, regardless of where it lands. That covers the dangerous direction without redesigning the whole signature.

## Related, same module, same campaign

See the companion ticket on `verify_config_text` accepting non-object JSON. Both are cases of the guard checking something narrower than the promise its docstring makes.
---

## REMAINING DEFECT MEASURED 2026-08-20, and the fix shape follows from it

Executed against `verified_write_config` (**not** `verify_config_text`, which is a pure syntax/shape check and does no content comparison — an easy and unhelpful mistake):

| rewrite | result |
|---|---|
| `hard_deny.deny` -> `permissions.allow` | **REFUSED** -- *"write would move pattern(s) out of hard_deny"* |
| `permissions.deny` -> `permissions.allow` | **WRITES OK** |
| `permissions.ask` -> `permissions.allow` | **WRITES OK** |
| pattern deleted outright *(control)* | REFUSED -- *"write would drop existing rule pattern(s)"* |

**The guard already performs exactly the right comparison, and applies it to one tier only.** Step 3 of `verified_write_config` computes `_hard_deny_patterns(original) - _hard_deny_patterns(new)` and refuses on a non-empty difference. There is no equivalent for `permissions.deny` or `permissions.ask`, so a pattern that was restricting silently becomes granting and the write succeeds.

### Consequence for scope — this is NARROW

The fix is the same comparison generalised to the ordinary tier: a pattern present in `permissions.deny` or `permissions.ask` before must not appear only in `permissions.allow` after. **It needs no pattern semantics and no matcher**, so it does not drag `permissions.py` into the write path or invert a layer relationship — the wide branch considered in the pre-registration is not required.

Watch for one thing the existing check gets right and a generalisation could lose: step 3 is guarded by `if path.exists()` and tolerates an unparseable original by setting `original_parsed = None`. **A rewrite of a config that is currently broken must still be allowed**, or the guard makes a corrupted file unfixable.

### Note on the two-tier asymmetry

Nothing marks the ordinary tier as deliberately unguarded, and the docstring's step 3 explains the `hard_deny` case in terms that apply equally to `deny` and `ask` — *"a hard deny turned into an allow is a loss even though nothing looks missing."* The same sentence is true one tier down. This reads as an unfinished generalisation rather than a decision.
