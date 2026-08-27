---
title: 99-scored
type: note
permalink: toolguard/too-45/reports/surprise/99-scored
---

# Ticket 99 scored - contract module semantic seams

Commit `4d62339`. Scored against the commit. Informed estimate (ineligible for the blinded series).

## Production files - the headline metric

| predicted | actual |
|---|---|
| `claude_code_contract.py` | yes |
| `hook.py` | yes |
| `testing/sandbox.py` | yes |
| `session_start.py` | **NO - declined** |

**Production recall 3/3 = 100%** of what was actually touched. **Precision 3/4 = 75%**: I predicted a file that correctly did not move.

## Uncertainties, resolved - one clean hit, one clean miss

**U2 HIT, and it is the most useful datum in this ticket.** I pre-registered: *"I predict the agent will push back on item 4 (SessionStartEvent for a single cwd field), and I want that recorded as a prediction rather than discovered as a surprise."* It did, for exactly the reason predicted: one `CWD_KEY` read, no construction/parsing pair, so a wrapper prevents no drift.

That is worth more than the recall number. **A predicted refusal converts a would-be surprise into a confirmation** -- and it only worked because the brief invited pushback explicitly. Cheap to do, and it turns the estimator into something that tests the *plan* rather than only the implementer.

**U3 MISS, with a nameable cause.** I predicted hook.py's surviving key imports at **0-2**; actual is **6**.

The cause is not a modelling error about the code. Every one of the six -- `CWD_KEY`, `HOOK_EVENT_NAME_KEY`, `PERMISSION_MODE_KEY`, `TOOL_INPUT_KEY`, `TOOL_NAME_KEY`, `TRANSCRIPT_PATH_KEY` -- is read through `hook_data.get(...)` or a required-field list, i.e. entirely on the **parsing** side. That is plan **item 2**, which I deliberately cut from scope in the same document that carried the prediction.

**I predicted the outcome of the whole ticket while dispatching only part of it.** Proposed cause code **`S` (scope-conditioning failure)**: the estimate was right about the code and wrong about which code was in play. Distinct from `B` (brief-constrained), where the brief forbids a route the estimate assumed; here the brief was correct and the *estimate* failed to condition on it.

**Practical fix, and it is trivial**: when an estimate accompanies a partial dispatch, restate the metric as *"of the dispatched scope"*. I had the scope cut written three paragraphs above the prediction and still did not apply it.

## Unpredicted, favourable

`_finalize_output()` was mutating the wire dict to merge fault context. Rewriting it to use `dataclasses.replace()` on the `RuntimeVerdict` removed two further keys the plan never anticipated reaching -- and is the better shape anyway, since it keeps the structured verdict authoritative instead of editing its rendered form. That is this project's "prose is output, not a data structure" rule applying to a dict rather than to prose.

## Flagged by the implementer, accepted

`sandbox.run_hook()` now defaults all 7 event fields where it previously defaulted 3. Zero behavioural impact measured on suite and corpus. Recorded because it is a semantic widening of test tooling, and this project has twice been bitten by a shared structure quietly widening for one consumer.

## Gate note

Full-suite and corpus verification could not be run clean at commit time: `test_verdict_corpus.py` was failing from concurrent, uncommitted `multiline.py` work. Attribution verified independently rather than accepted -- that module imports none of `claude_code_contract`, `hook` or `sandbox`. Ticket 99's own surface (196 tests across contract/hook/hook_eval/sandbox) passed clean. **Full-suite verification is owed once ticket 98 chunk 2 lands.**