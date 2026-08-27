---
title: 20-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/20-estimate-predictions
---

# TOO-45 proposed-ticket 20 — blinded touch-set prediction

## Reasoning

The ticket's own "Fix direction" section names four concrete changes, all
scoped to the consolidation-proposal engine:

1. Make the family-1/family-2 safety gates verdict-aware rather than
   decision-count-aware (currently a bare `bool`, collapsing "checked and
   clean" into "not checked" — the 2026-08-20 amendment sharpens this to a
   three-way decision: refuse-without-corpus / tri-state return /
   surface-to-user).
2. Thread the corpus into `propose_consolidations`, which `run_maintenance`
   already does for the two neighbouring engines (redundancy, cross-layer)
   but not for consolidation.
3. Fix `_static_prefix_of`'s `/`-boundary unsoundness to match
   `match_command`'s actual gate, and update the test that currently pins
   the unsound behaviour as correct (`test_path_boundary_prefix_subsumes`).
4. Stop emitting a rationale **string** that asserts a safety property the
   code did not check (the "equivalence-preserving" mislabeling, which also
   leaked into `maintenance.py` in three places per the ticket's own
   side-note).

All four of these live conceptually inside `toolguard/tools/consolidate.py`
(`_check_family1_safe` at `:324`, `_check_family2_safe` at `:582-596`,
`_static_prefix_of`, `BroadeningProposal.overlaps_guard_rules`, the
`propose_consolidations` entry point and its docstrings/rationale strings).
The one cross-module edge named explicitly is the `run_maintenance` call
site in `toolguard/tools/maintenance.py`, which needs a one-argument change
(pass the corpus) plus correction of the "equivalence-preserving" claims it
copied from `consolidate.py`'s failure-message wording.

Everything else mentioned in the ticket file — `match_command`'s
over-matching (ticket 18, explicitly stated as already fixed and upstream
of this one), and the "approval surface" / `rule_sort` diff-normalisation
finding (labelled `RA1` and recorded separately in
`reports/follow-up-queue.md`) — reads as adjacent but out of *this*
ticket's stated fix direction.

Test changes should mirror production changes almost 1:1: the bulk of test
churn lands in `test/unit/test_tools_consolidate.py` (already the file
where the amendment's own campaign added 2 detection tests, 38 -> 40), with
a smaller, secondary concentration in `test/unit/test_tools_maintenance.py`
for the call-site and wording fixes.

## Production modified

| file | reason | confidence |
|---|---|---|
| `toolguard/tools/consolidate.py` | Houses every mechanism named in the ticket: `_check_family1_safe`, `_check_family2_safe`, `_static_prefix_of`, `BroadeningProposal.overlaps_guard_rules`, the false "structurally proven safe" / "EQUIVALENCE-PRESERVING" docstrings, the rationale-string generation, and `propose_consolidations`'s corpus-less signature | high |
| `toolguard/tools/maintenance.py` | `run_maintenance` calls `propose_consolidations(config, tool)` without the corpus while passing it to the two neighbouring engines — named explicitly as "the compounding factor"; also the three places the wrong positive "equivalence-preserving" reading was copied in | high |
| `toolguard/permissions.py` | Only touched if the `_static_prefix_of` fix is done by delegating to `match_command`'s real boundary logic rather than re-deriving it locally; possible but not required by the stated fix | low |
| `toolguard/tools/pattern_overlap.py` | Plausible home for prefix/overlap helpers `consolidate.py`'s family-1 overlap logic could lean on, but the ticket attributes all named functions to `consolidate.py` itself | low |
| `toolguard/tools/rule_apply.py` | The "approval surface" finding (unrequested `rule_sort` normalisation appearing in the diff) is in the ticket text but is separately labelled `RA1` in the follow-up queue, suggesting its own ticket rather than this one's scope | low |
| `toolguard/rule_sort.py` | Same RA1 finding — `reassemble_permissions_section`'s `if not entries: continue` dropping empty `ask`/`deny` lists — same low-confidence, same reasoning as above | low |

## Production added

No new production files predicted. This reads as a bug-fix ticket against
one existing module (plus one call site), not a scope that needs a new
module — e.g. a tri-state safety-verdict type is more likely added as a
small enum/dataclass inline in `consolidate.py` than split out.

| file | reason | confidence |
|---|---|---|
| *(none predicted)* | — | — |

## Test modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_tools_consolidate.py` | Primary test file for every mechanism above; already the file the campaign amendment touched (38 -> 40 tests) to *detect* the bugs — the fix itself should land more changes here, including updating `test_path_boundary_prefix_subsumes` per §4, which the ticket says explicitly "will have to change with the code" | high |
| `test/unit/test_tools_maintenance.py` | Covers `run_maintenance`'s call sites and aggregate wording; needs updates for the corpus-threading call-site change and the corrected "equivalence-preserving" claims | medium |
| `test/unit/test_tools_rule_apply.py` | Only in scope if RA1 is fixed alongside this ticket rather than separately | low |
| `test/unit/test_rule_sort.py` | Same RA1 dependency as above | low |
| `test/unit/test_pattern_overlap.py` | Only relevant if `pattern_overlap.py` ends up touched | low |

## Test added

| file | reason | confidence |
|---|---|---|
| *(none predicted)* | Expect new test *methods* inside the existing consolidate/maintenance test files rather than new test files — the ticket's own campaign amendment added tests to the existing file, not a new one, for the same class of gap | — |

## Files expected DELETED

None predicted.

## Concentration set

The large majority of changed lines should land in two files, with a
distant secondary pair:

1. **`toolguard/tools/consolidate.py`** — the module under audit; every
   named defect (§1-§4, plus the 2026-08-20 gate-hole amendment) is a
   function inside it.
2. **`test/unit/test_tools_consolidate.py`** — the corresponding test file,
   already shown to be the locus of test churn in the campaign's own
   diagnostic pass.
3. `toolguard/tools/maintenance.py` and `test/unit/test_tools_maintenance.py`
   — secondary, small and localized (a call-site argument plus wording
   fixes), not comparable in volume to the pair above.

## Scope prediction

**IN scope:**
- `_check_family1_safe` / `_check_family2_safe` becoming verdict-aware
  (not a bare bool that conflates "checked-safe" with "unchecked").
- Threading the corpus into `propose_consolidations` from `run_maintenance`.
- Fixing `_static_prefix_of`'s `/`-boundary unsoundness and the test that
  pins the old, wrong behaviour.
- No longer emitting a rationale string asserting an unchecked safety
  property (the "equivalence-preserving" mislabeling, in both
  `consolidate.py`'s own docstrings and its copy in `maintenance.py`).

**OUT of scope (predicted deferred to other tickets):**
- `match_command`'s multi-token DEFAULT-prefix over-matching — this is
  ticket 18, and the ticket text states it is upstream and already fixed
  ("Fix 18 first, then re-derive").
- The "approval surface" / diff-normalisation finding (`RA1`) in
  `rule_apply.py` and `rule_sort.py` — the ticket text itself files this
  under a separate label (`RA1`) in `reports/follow-up-queue.md`, distinct
  from the `C1-C7` findings this ticket's "Fix direction" section addresses.