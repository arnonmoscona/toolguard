---
title: The file-path hard-deny discards its deciding pattern, and the comment defending
  that choice is wrong about the corpus it cites
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/68-the-file-path-hard-deny-discards-its-deciding-pattern-on-a-false-premise
---

**FIXED in `05f786d` (TOO-45 phase 2).** The file-path hard-deny now reports its deciding pattern (`matched_rule=hard.matched_pattern`); all four file-tool goldens are attributed — see `toolguard/resolve.py:105`.

# A design choice justified by a claim that does not hold

**Found 2026-08-13. Measured against the corpus itself, not read. One RED test in the tree.**

## The defect

`toolguard/resolve.py:105-109`, on the file-path hard-deny branch:

```python
# Deliberately left None, unlike the Bash hard-deny path, which
# does attribute matched_rule -- populating it would change a
# value the golden verdict corpus tracks under "no verdict may
# change".
matched_rule=None,
```

So on a file-path hard deny, **which pattern denied is discarded.** It survives only inside the prose `reason` — the "prose is output, not a data structure" pattern, on the deny path, in the tool's own core.

## The justification is false, and that is the point of this ticket

The corpus has **two tiers**, and the comment conflates them.

- `matched_rule` is in **`TRACKED_FIELDS`** — the reviewable, regenerable tier.
- It is **not** in the hard tier, which is what "no verdict may change" actually names.

**Measured by mutating toward the fix**: populating `matched_rule` on this branch produces **4 tracked diffs and zero hard failures** — four golden lines, in the tier the corpus README says a refactor may legitimately update.

**The corpus does not require what the comment says it requires.** The comment is not merely inaccurate; it is the reason nobody has fixed this, which makes it more expensive than the missing field.

## Why the corpus cannot catch it either

The corpus's HARD tier genuinely does pin attribution — for **Bash**. A mutant that attributed a Bash hard-deny to the wrong pattern (decision unchanged, attribution wrong) was caught with 10 mismatches, so shape 25 is defeated on that side by a tier no environment variable can silence.

**File-path verdicts always have `sub_matches == []`**, so that breakdown tier is **structurally blind** to them. And all **4** file-tool denies in the entire 6,401-case corpus are hard-denies, all unattributed; **zero file-path cascade denies exist**. The one tier that could have held this contract cannot see this branch at all.

## Fix

Populate `matched_rule` from `hard.matched_pattern`, regenerate the 4 tracked golden lines, and delete the comment. The RED test `TestFilePathHardDenyAttribution.test_a_file_path_hard_deny_golden_records_the_deciding_pattern` names all four cases and their deciding patterns, and was proven to go **green** under the fix.

## Related

- **63** — the canonical protection set, same branch, different defect.
- **38** — `fallback_kind` re-derived from prose. Same anti-pattern, different code.
- **31** — shape 25: asserting `deny` cannot distinguish a real rule match from a fail-closed path. `matched_rule` is the standard remedy, and this branch is the one place it is unavailable **by choice**.
