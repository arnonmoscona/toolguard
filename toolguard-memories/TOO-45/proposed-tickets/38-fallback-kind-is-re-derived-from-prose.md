---
title: fallback_kind is re-derived by substring-matching the reason text the program
  just rendered
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/38-fallback-kind-is-re-derived-from-prose
---

# The prose-parsing anti-pattern is still live, one level below where it was fixed

**Found 2026-08-13, from Arnon's question: "could `reason` distinguish a real deny from a fail-closed one?" It could — and finding out why we should not do that surfaced the same defect already in the code.**

## The defect

`compound.fallback_kind_for_reason(decision: str, reason: str)` classifies an outcome by **substring-matching the prose the program itself just built**:

```python
_FALLBACK_REASON_MARKERS = (
    ("no_match_fallback=allow_with_warning", "warned", "allow"),
    ("undecidable_fallback=allow_with_warning", "warned", "allow"),
    ("no_match_fallback=allow", "silent", "allow"),
    ("undecidable_fallback=allow", "silent", "allow"),
    ("undecidable_fallback=deny", "denied", "deny"),
)
```

This is the **exact** shape TOO-45 already measured and fixed once at the audit-trail level, where the cost was **813 of 975 compound-allow decisions under-logged and 1,943 sub-commands with no audit record at all.** Nothing failed and nothing warned; the log simply looked complete.

## CORRECTION 2026-08-13 — the "silently" claim is FALSE, measured

I wrote this ticket around the docstring's own warning that a reword *"stops classifying it, silently"*. **Measured: it does not.**

Rewording every marker in `_FALLBACK_REASON_MARKERS` (`no_match_fallback=allow` → `no_match fallback -> allow`, etc. — exactly the silent failure the docstring predicts) produces **5 failures above baseline**, including `test_hook.test_escape_hatch_deny_logs_placeholder_and_no_provenance` — the deny-side audit path this ticket names — plus 3 in `test_resolve` and 1 in `test_compound_resolve_seam`.

**So the marker text is pinned. A reword breaks tests.** The ticket's central alarm was inherited from a docstring rather than measured, and the docstring is wrong about its own module.

**What survives, and it is still worth fixing:**

- The design objection stands on its own: structure is re-derived from rendered prose, which is the pattern this project has already paid 813-of-975 for. Fragility that happens to be test-covered is still fragility.
- **The genuine blindness is the one in "What is lost today" below**: a plain `no_match_fallback=deny` has **no marker at all**, so it is indistinguishable from a genuine rule-match deny. That is real, unpinned, and unaffected by the correction above.

Downgrade the urgency; keep the ticket.

## The code already knows, and says so

The constant's own docstring:

> *"reword either reason string without keeping that substring and this stops classifying it, **silently**."*

And the function's:

> *"Structured detection ... is preferred wherever available. This text-based fallback exists for the two places that cannot use it."*

**A mechanism that documents its own silent-failure mode and is kept anyway is a design decision that has outlived its justification.** The docstring is doing the work a type should be doing.

## The two sites, and why each is fixable

1. **`resolve_one`'s 3-tuple result** — *"whose contract has no room for a `fallback_kind` field"*. It has no room because it is a **tuple**. Widening it is a local change, and it lands squarely on the standing preference: a frozen dataclass instead of a positional tuple, which is trivially cheap and removes the mis-indexing hazard as a side effect.
2. **`hook.py`'s deny-side audit-log path** — *"classifies from the final reason string alone"*, because `RuntimeVerdict` has no field to read. Its fields are `decision, reason, provenance, overrides, sub_matches, additional_context, fallback_warning, matched_rule, tool, target`. There is a `fallback_warning: bool` but no kind — a boolean where an enum is needed.

## What is lost today, beyond fragility

- **A plain `no_match_fallback=deny` is indistinguishable from a genuine rule-match deny.** The markers table has no entry for it (its reason carries no `": "`), so both return `None`. The audit trail cannot tell "denied by your rule" from "denied because nothing matched".
- **The fail-closed empty-extraction deny is likewise unclassified.** That is the discrimination problem that started this: catalogue shape 25.

## Fix direction

Carry the kind, do not re-derive it:

- add an explicit kind field to `RuntimeVerdict` (and to `resolve_one`'s result), set at the point the outcome is decided — where the fact is already known
- `hook.py` and the audit writer read the field
- `fallback_kind_for_reason` and `_FALLBACK_REASON_MARKERS` are then deletable, along with their careful ordering rules, the decision-scoping, and the prefix-shadowing caveat — **all of which exist only to make substring matching safe**
- the reason string stays exactly as it is, for display

This is the general corollary applied: *a function that returns prose and whose caller needs a fact from that prose should return both — the fact as data, the prose for display.*

## Consequence for the test suite

Catalogue shape 25 currently has a one-line workaround: `matched_rule is None` happens to distinguish a fail-closed deny from a real one. **That works by accident.** An explicit kind makes it a contract, and makes the assertion say what it means.

## Scope note

This is a real refactor across a decided type, not a comment fix. It should not be folded into the test-repair campaign, which is forbidden from touching production code.