---
title: TOO-45 surprise factor - ticket 22 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/22-prereg
---

# Pre-registration, proposed ticket 22 (redundancy analyzer reports unsafe deletions)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation. Headline: **line-weighted recall against the final committed diff**.

Coordinator measurements are in `measurements/22.md` and are **not** appended to the ticket file — the contamination route that voided items 20, 39, 57, 64 and 70.

## Remaining scope, per the ticket's amendment

**HR2** (`hierarchy.py:~400`), **RD1** space-collapsing, **RD2** provenance (`redundancy.py:~197`).

## THE PREDICTION THAT MATTERS — is the fix prose, or structure?

HR2's finding note says a rule *"is redundant and can be dropped."* The ticket's counterexample shows dropping it flips `git push` from `allow` to `deny`. **So the sentence is false.**

There is a cheap fix and a correct one, and which is chosen is the whole interest of this item:

- **Cheap**: reword the sentence. The analyzer still cannot tell a safe drop from an unsafe one; it just stops claiming it can.
- **Correct**: carry a structured fact — *is this copy safe to remove* — and render prose from it at the edge. That is this project's own *"prose is output, not a data structure"* rule, and the founding defect of the whole campaign.

**Predicted: a correct fix is structural, and the touch set therefore reaches `maintenance.py`**, because the note reaches an operator through the maintenance report (`maintenance.py:~193`) and the report is what must learn the distinction. **A diff confined to `hierarchy.py` and `redundancy.py` is evidence the cheap fix was taken.**

Locked now so it cannot be judged after the fact.

## The cross-ticket constraint — 22 must NOT invent a second vocabulary

Ticket 22 §5 (*"a never-exercised rule is indistinguishable from a genuinely covered one"*) is **the same defect as ticket 20a**, not an analogy: both cannot separate *"checked and clean"* from *"never looked."* 20a introduces `safe` / `unsafe` / `unverified` as named constants.

**Predicted finding if it goes wrong**: 22 introduces its own parallel set. That would be *one concept, many enumerations* — the failure that has now cost this campaign three times, most expensively in ticket 79's four hand-written verdict enumerations. **The implementer must be told 20a's constants exist and required to justify any new state.**

This also means **20a must land before 22**, which is the current queue order and must not be reshuffled for convenience.

## Three deliberate non-pins — do not let an implementer resolve these silently

The ticket left three things unasserted **on purpose**, because a test either way would preempt an undecided fix direction: HR2's note wording, RD1's normalisation policy (normalise like the matcher, or relabel findings as spelling duplicates), and RD2's layer attribution.

**An implementer that picks one and pins it with a test, without stating the choice, is a finding regardless of which option it picks.**

## Anti-vacuity — there is NO decision replay here, and that must be said

The redundancy and cross-layer engines **only report**; `--apply` enacts consolidation findings alone (ticket 20's subject). So **a corpus replay cannot validate this ticket** — no verdict moves, by construction. A clean replay here is vacuous, not reassuring.

**The instrument is the report's content**, which means the test obligation is on what the analyzer *says* and what it marks *actionable*, not on what any command decides. Predicted: this makes the test-side diff proportionally larger than the production-side one, unlike most items in this series.

## The finding that outranks the ticket's own three

From `measurements/22.md`: a corpus finding names **the covering rule as redundant too**, so an operator who acts on the report by deleting everything it lists **removes the coverage entirely.** That is the analyzer being individually right and collectively dangerous.

**Predicted: this is not fixed by this ticket** and will need its own — it is a change to what a report *is*, not to any one finding. If the implementation does address it, that is scope growth worth flagging rather than praising.

## Ordering discipline

The estimator writes `22-estimate-predictions.md` and `22-estimate-uncertainties.md` and returns **only** the token `DONE`. Items 05 and 19 leaked a summary through the return value and were discarded; item 20 held under wording that names the consequence. **Use the item-20 wording.** If it leaks again, mark 22 contaminated rather than scoring it.

## 22 IS THE FIRST FULLY-CLEAN RUN IN THE SERIES — recorded before the estimate exists

Both known contamination routes are closed for this item, and this is the first time that is true of either channel simultaneously:

- **Coordinator appendix**: ticket 22's file carries **zero** measurement text — grepped and confirmed at dispatch. Its measurements live in `measurements/22.md`, which the estimator cannot read. Items 20, 39, 57, 64 and 70 all failed this.
- **Return channel**: dispatched with the item-20 wording, which names the consequence rather than merely stating the rule. That is the only wording that has held (items 05 and 19 leaked under weaker text).

**So 22 is the series' cleanest data point, and should be weighted accordingly in the aggregate** — most other items carry a named exception.

**One deliberate addition to the instrument**: the estimator is asked, in its own section, to predict **prose versus structure** — will HR2's false note be reworded, or will the fix carry a fact the message is rendered from? It must answer plainly, not hedge across both. This is the first time the series has asked an estimator to predict the *character* of a fix rather than its file set, and it is the question the coordinator independently pre-registered above. **Both predictions now exist and were recorded before either was known** — mine in this file, the estimator's in its own, neither having seen the other.

## Return-channel outcome — PARTIAL compliance, ZERO informational leak. 22 stays in the series.

The estimator returned:

> *"Both files are written.*
>
> *DONE"*

The instruction said *"Not even one sentence of preamble or 'I've written both files.'"* — so this is **literally a violation**, and it is the exact sentence the instruction named.

**But it leaks nothing.** Contamination in this series means *the coordinator learns the predictions before the work is done*. "Both files are written" carries no prediction, no file, no scope call, no prose-versus-structure answer. Items 05 and 19 were discarded because they leaked **substance**.

**Disposition: 22 remains a valid, uncontaminated data point.** Both files were written unread (127-line and 114-line equivalents confirmed present by size only).

**The finding worth carrying to the aggregate is the split**: the item-20 wording is now **2 for 2 at preventing substantive leaks** (items 20 and 22) and **1 for 2 at preventing preamble** (item 20 returned bare `DONE`; item 22 did not). So the wording controls the thing that matters and not the thing that does not — which is the right failure mode, but it means the rule should be **restated by consequence rather than by form**: forbid *disclosing any prediction*, and stop trying to forbid *any sentence at all*. A rule that bans a harmless sentence invites partial compliance and then has to adjudicate it, which is what I am doing here.

Report it in the aggregate as **"substantive leaks: 2 of N under weak wording, 0 of M under consequence-naming wording; one cosmetic preamble"** — not as a clean sweep, and not as a third contamination.
