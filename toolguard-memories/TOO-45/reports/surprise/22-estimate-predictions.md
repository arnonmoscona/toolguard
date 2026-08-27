---
title: 22-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/22-estimate-predictions
---

# TOO-45 Ticket 22 — Blinded Touch-Set Estimate: Predictions

## Reasoning

The ticket's own pin note narrows scope sharply. Of the original findings (HR1–HR4, RD1, RD2, plus
the "zero corpus diff" prose bug), everything except three items is already fixed in `05f786d`,
entirely inside `toolguard/tools/hierarchy.py`. What remains open is explicitly enumerated:

1. **HR2** — the cross-layer finding's `note` string still asserts "can be dropped" at
   `hierarchy.py:400`, even though HR1's underlying logic bug (allow-only cover test) is already
   fixed. This is a leftover false claim in a string literal, not a behavioural bug.
2. **RD1 space-collapsing** — case-folding in `_normalised_body` was fixed; the space-collapsing
   half of the same normalisation function was not. Fix direction #4 frames this as an undecided
   policy choice (normalise like the matcher vs. label findings as spelling duplicates), so the
   change is more than a one-line tweak — it is a decision that also has to be applied consistently.
3. **RD2 provenance** — `_config_without_allow` (redundancy.py:197) re-discovers the owning layer
   by searching raw `layer.content` instead of using the `provenance` the caller already holds.
   Fix direction #1 names the fix directly: pass `provenance` in, delete the search loop. This also
   removes the "candidate dead branch" noted at the end of the ticket
   (`if config_without is config: continue` in `find_corpus_redundant_allows`), since that branch
   only exists to guard against the same layer-discovery approach being replaced.

`_normalised_body` lives in `redundancy.py` and is imported by `hierarchy.py` (line 73 of the
ticket body: "`hierarchy.py` imports `_normalised_body` and inherits this, while saying nothing
about it"). So the RD1 decision, whichever way it goes, changes behaviour visible from both
modules even though the function itself has one home.

Ticket 20 (consolidation/apply) is explicitly called out as separate scope — I am treating
`consolidate.py` and `rule_apply.py` as out of scope even though the ticket mentions them, because
it says so directly: "Ticket 20 covers the consolidation engine, which is separate."

## Production — Modified

| file | reason | confidence |
|---|---|---|
| `toolguard/tools/redundancy.py` | RD2: `_config_without_allow` takes `provenance` instead of searching; removes the now-dead `if config_without is config: continue` guard. RD1: space-collapsing removed or replaced with an explicit "spelling duplicate" label in `_normalised_body` / the finding it feeds. Note strings for corpus and static findings reworded away from "can be dropped" per fix direction #2. | high |
| `toolguard/tools/hierarchy.py` | HR2: the note string at/near line 400 reworded from "the more-specific copy is redundant and can be dropped" to a statement of what was actually tested (e.g. naming the covering layer). Possible secondary touch if the RD1 policy decision requires hierarchy's cross-layer findings to carry the same "spelling duplicate" label it inherits from `_normalised_body`. | high |

## Production — Added

None expected. This is a targeted fix inside two existing modules and two existing functions; the
ticket does not describe new capability, only correcting existing note text and one layer-lookup
mechanism. No new file, class, or module is implied by anything in the ticket body.

## Production — Deleted

None expected. The "candidate dead branch" callout (`if config_without is config: continue`) is a
few lines removed from an existing function in `redundancy.py`, not a file deletion.

## Test — Modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_tools_hierarchy.py` | HR2's fix is pinned by a RED test already in the tree per the ticket's own note ("pinning its wording would fight the fix. The substance is carried by the RED test instead, which uses the note as its failure message") — that test's expected string/behaviour will flip from failing to passing once `hierarchy.py:400` changes. | high |
| `test/unit/test_tools_redundancy.py` | RD1 (space-collapsing) and RD2 (provenance) both have measured reproductions in the ticket; both need assertions updated or added to match the fixed behaviour of `_normalised_body` and `_config_without_allow`. | high |
| `test/unit/test_tools_maintenance.py` | Only if maintenance's report snapshots assert the literal note text of an affected finding type. Plausible since the pin note stresses these findings "reach an operator" via `maintenance.py:193`, but the ticket gives no direct evidence maintenance tests pin exact note strings. | medium |

## Test — Added

None expected as a new *file*. Given the ticket references RED tests already present for HR2 and
the RD1/RD2 reproductions are already "measured and reproduced" per the pin note, I expect this
work to complete existing red-to-green tests and add a handful of new cases inside the two files
above, not stand up a new test module.

## Concentration set

`toolguard/tools/redundancy.py` and `toolguard/tools/hierarchy.py` should hold the large majority
of changed production lines — likely with `redundancy.py` slightly larger, since it carries two of
the three open items (RD1, RD2) versus hierarchy's one (HR2), plus the dead-branch removal.
`test/unit/test_tools_redundancy.py` and `test/unit/test_tools_hierarchy.py` should hold the large
majority of changed test lines, mirroring the production split.

## Scope prediction

**In scope**: the three explicitly-still-open items — HR2 (note wording, `hierarchy.py`), RD1
space-collapsing (`_normalised_body` in `redundancy.py`, and its behavioural echo in
`hierarchy.py`), and RD2 provenance (`_config_without_allow` in `redundancy.py`). All three are
named as open in the pin note at the top of the ticket file, which is the authoritative "current
state" per this repo's own convention (amendments over body).

**Out of scope**: HR1, HR3, HR4, the zero-corpus-diff docstring/prose correction, and RD1's
case-folding half — all explicitly marked fixed in `05f786d`. Also out of scope: ticket 20's
consolidation/apply engine (`consolidate.py`, `rule_apply.py`), explicitly disclaimed as separate
in the "Relationship to the other tickets" section, and tickets 17/18 (matcher under/over-matching),
named as upstream dependencies but not this ticket's own work.

## Prose or structure

**Prediction: (a) a reworded message**, specifically for HR2 — the cross-layer finding whose note
claims "the more-specific copy is redundant and can be dropped."

Reasoning: HR1's underlying logic bug (the cover test reading only allow lists) is already fixed
in `05f786d`. What's left for HR2 is purely the sentence generated once that (now-correct) cover
test has run — the fact needed to write an honest sentence (which layer covers, at what
specificity) is the same fact the already-fixed cover-test logic already computes and already
threads into the finding. HR1/HR3/HR4 were fixed in the same commit without the ticket describing
any new field or data-shape change — only "docstrings are corrected" and note-text left as the one
deliberately unpinned string. That is strong evidence the surrounding finding structure already
carries what's needed, and HR2 is the same kind of fix applied to the one string the prior commit
left alone on purpose.

This implies the change stays inside `toolguard/tools/hierarchy.py` (the string literal near line
400) plus the assertion in `test/unit/test_tools_hierarchy.py` that currently pins the old wording
as a RED test. It does NOT imply a new dataclass field, a new Finding attribute, or any change to
how `maintenance.py` consumes or renders findings — the note is already a string field on an
existing finding type, and this fix changes its content, not its shape.

(If I'm wrong, the fix that would falsify this is a new field such as `verified: bool` or
`basis: str` added to the cross-layer finding type, with the note then rendered from it — the
"prose is output, not a data structure" pattern applied prospectively rather than retrospectively.
I judge this unlikely here specifically because the fact is already computed at the point of note
generation and doesn't need to survive a round-trip through prose to reach another consumer, which
is what the referenced TOO-45 lesson evidence actually turned on.)