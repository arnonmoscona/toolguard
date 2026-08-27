---
title: 98-chunk2-scored
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk2-scored
---

# Ticket 98 chunk 2 scored - AST attribution

Commit `b8947a4`. Informed estimate, ineligible for the blinded series (I built three spikes and the plan first).

## Production files

| predicted | actual |
|---|---|
| `toolguard/parser/multiline.py` (1), upside 2 if the IR needed a new accessor | `toolguard/parser/multiline.py` (1) |

**1/1 = 100%.** The upside case did not fire: `command_model.build_ir` already exposed what attribution needed, so no accessor had to be added. Predicting the upside and having it *not* fire is the correct outcome, not a miss.

## Uncertainties, resolved

- **U1** (the IR cannot distinguish unattributable from attributable, making the chunk materially harder) -- **did not fire.** The unresolved policy went in as specified: undecidable, ASK floor, never a guessed sink. Verified independently at `ask` under a blanket `allow = ["Bash(*)"]`.
- **U3** (deleting `_split_on_unquoted_pipe` orphans callers) -- **fired, in a form I did not predict.** No function callers were orphaned; two `# noqa: F401` **re-exports** were, `BASH_FAMILY` and `FOREIGN_EXECUTORS`, along with a comment still asserting they were partly used. **I found these, not the agent, and not ruff** -- the `noqa` silences exactly the check that would have caught it. Right uncertainty, wrong mechanism.

## U2 MISSED, and the miss is the most informative result here

I predicted **"exactly three changed decisions"** in the corpus and flagged that more than three would be the high-value signal.

**Actual: ZERO decision changes.** `test_no_verdict_changed` is clean. The three diffs that appeared are `sub_matches`/`reason` text, not verdicts.

The reason is worth carrying into the consolidated report: **the corpus does not contain the three shapes this ticket fixed.** 6,401 cases, and none of them is a quoted heredoc marker, a heredoc piped onward, or a heredoc inside an `if/then`. So the ticket corrected three real defects and the corpus could not see any of them.

That is a **coverage finding about the instrument**, not about the fix. The corpus is harvested from real logs, so it measures what Claude actually emitted -- which is a good property for regression detection and a poor one for confirming a fix aimed at rare shapes. **A corpus replay showing zero changes is not evidence the fix did nothing.** This is the third distinct way this campaign has produced a null that looked like proof, after the `matched_rule` blind spot and the `sys.path` isolation failure.

## Cause `N` again - the second instance

The first implementation introduced a whole-text-parseability coupling: every heredoc in a blob became unattributable if any unrelated construct in it failed to parse. **Caught before commit, and caught by the agent itself**, which stopped and asked rather than regenerating goldens past the `sub_matches` HARD invariant.

I measured it before deciding: no decision changed, because unattributable and attributed-to-a-foreign-interpreter both reach `ask`. Fixed anyway, on the grounds that **the floor was holding by configuration rather than by construction** -- ticket 28 plans to configure those apart, at which point the coupling becomes a live hole.

This is the second `N` in this ticket (chunk 1's placeholder forgery was the first) and it reinforces why `N` should be reported separately: **both were introduced by careful work, found before shipping, and unpredictable by any touch-set estimate.** Counting them against recall would penalise exactly the behaviour that caught them.

## Process note worth keeping

The agent ran ~3h05m and went 76 minutes without a file write. I checked whether it was stuck by measuring the working tree read-only rather than waiting or killing it, then messaged it with a specific question. It was mid-investigation and its answer contained the design finding above. **A silent agent is not necessarily a stalled one, and the cheap check is to read its output, not to interrupt it.**