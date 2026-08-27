---
title: The installer reports "already present, no changes needed" when it seeded zero
  self-integrity hard-deny rules
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/37-installer-reports-success-when-it-seeds-zero-self-integrity-rules
---

**PARTIALLY FIXED in `05f786d`.** `cmd_seed_self_perms` is now guarded (`toolguard/installer.py:799-804`); still open: `cmd_seed_hard_deny` remains unguarded at `toolguard/installer.py:1675-1689`.

# Zero seeded rules reports as "already present"

**Found 2026-08-13 by the test-repair campaign. Same shape as proposed ticket 29, but in the install path, which makes it worse.**

## The defect

`required_self_integrity_hard_deny_patterns()` carries **no population guarantee**. If it returns an empty table, `installer.py:868-888` iterates nothing, leaving both `hard_deny_added == []` and `hard_deny_already_present == []` — and then reaches:

```
if not added and not hard_deny_added:
    print("already present, no changes needed")
```

**Seeding zero self-integrity rules is reported to the user as "already present, no changes needed."**

**CORRECTION 2026-08-13 — my wording was too strong and a reader checking it would find it false.** I wrote that the two states are "indistinguishable in the output". Measured: they are **not byte-identical**. With the real table a second run also lists two `-> hard_deny` lines; with an empty table those lines are simply absent.

The accurate statement is **"a verdict with no count"**: the states differ only by the *absence of lines the user has no way to count*, and the verdict — "already present, no changes needed" — is identical and wrong. That is still the defect, and it is still ticket 29's family. But the overstated version invites dismissal, which is worse than a weaker true claim.

**A second instance this ticket did not name:** `cmd_seed_hard_deny` (`installer.py:1673-1678`) has the identical shape over `required_hard_deny_patterns()`. `cmd_seed_self_perms` and `cmd_seed_hard_deny` are near-duplicate ~50-line bodies — **a single count-reporting seeder fixes both at once.**

**On the fix shape:** the RED test deliberately asserts the *exit code*, not a count phrase, because any count assertion has to name a phrase or shape and would invent the API this ticket is still choosing between. Its docstring says that if the chosen fix is "report counts, keep exit 0", the test must be **rewritten to assert the count, not deleted**.

## Why this one matters more than ticket 29's instance

These are the rules that stop toolguard from deleting **itself** — the hard-deny patterns covering `~/.toolguard`. The failure is silent, reassuring, and lands at exactly the moment a user is least able to check: first install.

Auto-memory records that `~/.toolguard` was **wiped four times** during TOO-15 install testing, and that doc-only mitigation was proven insufficient each time. That is why TOO-29 exists. This is a mechanism by which the seeding could report success and protect nothing.

## Evidence

Setting `_SELF_INTEGRITY_HARD_DENY_PATTERNS = ()` at HEAD:

- three of the four `TestSelfIntegrityTable` tests **passed vacuously**
- the fourth **errored** with `IndexError` (an error, not a failure — no failure count records it)

The table class alone certified nothing. Note the honest calibration: the *file* as a whole did notice — `TestSelfIntegrityHardDenyBehavior` produced 8 failures — so this is **not** as blind as ticket 29's `run_guard`. The test side is now fixed; the production guarantee is not.

## Fix direction

Not fixable from the test side. Options:

- assert a non-empty table at the point of use, so an empty table is a startup error rather than a quiet no-op
- have the seeding path report **counts** rather than a verdict — "seeded 0 of 0" is visibly different from "seeded 0 of 4"

The second generalises: it is the same remedy ticket 29 needs, and the same one `danger()` needs (a clean audit and an empty audit currently return the same `[]`).

## Related, found alongside

`sudo rm -rf ~/.toolguard`, `/bin/rm -rf ~/.toolguard`, `sudo find ~/.toolguard -delete` and `rmdir ~/.toolguard/backups` all resolve to **`ask`, not `deny`**. The module docstring names the first two as known escapes; `sudo find` and `rmdir` were undocumented. All four are now pinned as characterisation tests, so the coverage is visible rather than assumed.