---
title: TOO-45 item 39 -- blinded touch-set estimate (predictions)
tags:
- TOO-45
- proposed-tickets
- surprise-estimate
permalink: toolguard/too-45/reports/surprise/39-estimate-predictions
---

# 39 -- write guard loss check is placement-blind: touch-set predictions

## Reasoning

I decomposed this into three cost centres: (1) where the comparison logic itself lives, (2)
what calls that logic and whether the fix changes its contract, and (3) what tests exist
already versus what a correct fix requires to be added.

**Where the logic lives.** The status amendment pins the defect to one function,
`verified_write_config`, and one step inside it, "step 3" -- a set-difference over
`_hard_deny_patterns(original)` vs `_hard_deny_patterns(new)`. The amendment's own framing of
the fix is "the same comparison generalised to the ordinary tier": a pattern present in
`permissions.deny` or `permissions.ask` before must not appear only in `permissions.allow`
after. That is a same-function, same-module change -- there is no indication a new module, a
new public type, or a new cross-module data flow is needed. The file inventory confirms
`config_write_guard.py` is a single 356-line module in the "config" layer, small enough that a
second per-tier check plausibly lives right next to the existing one.

**Callers and contract.** The original filing (before the amendment) described a fix that
would change `expected_patterns` to carry `(list_identity, pattern)` pairs -- an API change
that "touches every caller." The amendment explicitly retires that shape: the remaining defect
needs "no pattern semantics and no matcher," which reads to me as "no signature change either"
-- the generalization is an internal step inside `verified_write_config`, not a new parameter
threaded through its callers. If that reading holds, none of the four listed callers (the
maintenance skill, `toolguard-migrate`, `toolguard-install`, auto-migration) need source
changes, because they already call the same entry point and receive the same pass/refuse
signal. I flag this as the single biggest swing factor in the estimate: if I'm wrong and the
generalization does turn out to need a signature change (e.g. to report *which* tier lost a
pattern, for a better refusal message), the caller list from the original filing becomes live
again. I still predict no caller changes, because the amendment's "no matcher, no pattern
semantics" language reads as scoping down to a same-shape, same-signature fix, and because nothing
in the amendment suggests the refusal message needs new information to stay correct -- "write
would drop existing rule pattern(s)" already covers a same-tier deletion, and a differently-worded
refusal for "moved out of a restrictive tier into allow" reads as an achievable string change
inside the same function, not a caller-visible contract change.

**Tests.** `test_config_write_guard.py` already contains a named characterization test,
`test_pattern_moved_between_lists_is_not_treated_as_loss`, explicitly pinned as recording the
defect rather than specifying correct behaviour, with a docstring saying so "loudly." A fix
that closes the gap for `permissions.deny`/`permissions.ask` must flip at least this test from
characterizing-the-bug to asserting-the-fix, and very likely needs siblings for the two
specific rewrites the amendment measured (`permissions.deny -> permissions.allow`,
`permissions.ask -> permissions.allow`) plus a regression guard for the "unparseable original
must still be writable" behaviour the amendment calls out by name as something a naive
generalization could break. I don't expect a new test *file* -- the existing 721-line
`test_config_write_guard.py` is clearly the home for this, matching module-to-test naming
throughout the inventory (`config_write_guard.py` <-> `test_config_write_guard.py`).

**What I ruled out.** The amendment is explicit that the fix "does not drag `permissions.py`
into the write path" and needs no matcher -- so I am not predicting changes to
`toolguard/permissions.py`, `toolguard/patterns.py`, `toolguard/rule_entry.py`, or anything in
the "engine" layer. I'm also not predicting changes to `config_validation.py` (a separate,
narrower syntax/shape check the amendment itself distinguishes from `verified_write_config`) or
to `config_types.py` (the parsed structures already give `verified_write_config` access to all
three tiers, since the existing flat "drop existing pattern" check already spans them -- it
just doesn't yet track provenance per tier).

## Production -- modified

| file | reason | confidence |
|---|---|---|
| `toolguard/config_write_guard.py` | Home of `verified_write_config` and the step-3 comparison the amendment says needs generalising from `hard_deny` to `permissions.deny`/`permissions.ask`. | high |

## Production -- added

none expected

## Test -- modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_config_write_guard.py` | Already holds the pinned characterization test for this exact defect (`test_pattern_moved_between_lists_is_not_treated_as_loss`); a fix must convert it and add cases for the two measured rewrites (`deny->allow`, `ask->allow`) plus the "unparseable original stays writable" regression guard the amendment flags by name. | high |

## Test -- added

none expected

## Deleted

none expected

## Concentration set

`toolguard/config_write_guard.py` and `test/unit/test_config_write_guard.py` should hold the
large majority of changed lines between them. I'd guess production changes land mostly as a
second, tier-aware variant of the existing `_hard_deny_patterns`-style helper plus a few lines
in step 3 to call it and merge refusal reasons; test changes are likely the larger line count
of the two, since flipping one characterization test and adding 2-4 new cases (two measured
rewrite directions, plus the "leaves hard_deny still refused" non-regression, plus the
unparseable-original carve-out) is naturally more lines than the production fix itself.

## Scope prediction (this is the part that matters)

**I predict the narrow shape**, matching the ticket amendment's own framing rather than the
original filing's. The amendment states this directly: the fix is "the same comparison
generalised to the ordinary tier," it "needs no pattern semantics and no matcher," and it
explicitly rejects dragging `permissions.py` into the write path or inverting a layer
relationship -- calling the wide branch from the pre-registration "not required." Structurally
this also fits the declared layer map: `config_write_guard` sits in the "config" layer, and
`permissions`/`patterns` sit two layers up in "engine." A same-layer, same-module, set-based
fix respects that boundary; a semantic "is this rule now weaker" check would need to import
matcher logic from "engine" into "config," which is exactly the inversion the amendment says
is not needed.

**Touch set for the narrow shape** (this is my full prediction, not a hedge against the wide
one): `toolguard/config_write_guard.py` modified (high confidence), `test/unit/test_config_write_guard.py`
modified (high confidence), nothing else. No new files, no caller changes, no changes outside
the `config` layer.

If I'm wrong and the wide shape is what actually gets built (detecting a weakening without a
section change, e.g. a pattern narrowed or generalized within the same tier in a way that
changes its practical reach), I would expect it to pull in `toolguard/permissions.py` and/or
`toolguard/patterns.py` for matcher access, plus their test files
(`test/unit/test_permissions.py`, `test/unit/test_patterns.py`), and possibly a new
cross-layer helper module if the project's architecture-fitness check refuses a direct
downward-then-up import. I consider this the low-probability branch given how explicitly the
amendment argues against it.