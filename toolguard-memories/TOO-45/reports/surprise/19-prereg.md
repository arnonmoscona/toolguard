---
title: TOO-45 surprise factor - ticket 19 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/19-prereg
---

# Pre-registration, proposed ticket 19 (commands reach the shell without ever being rule-matched)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation. Headline metric: **line-weighted recall against the final committed diff**.

## Scope from the AMENDMENT

*"PARTIALLY FIXED in `05f786d`. Bypass P1 is closed (`command_extractor.py:513-528`), along with P6-awk; **still open: bypasses P2-P5 all still reproduce, since `toolguard/parser/multiline.py` was untouched by phase 2.**"*

So: **four bypasses, all in one module phase 2 never opened.** Nothing here is half-done, which makes this a cleaner prediction target than most of the remaining queue — no partially-migrated state to reason about.

## Severity: the highest class in the campaign

A bypass here means **a command reaches the shell having never been matched against any rule.** Not a rule that fails to fire — no rule is consulted at all. Every deny, ask and hard_deny is bypassed simultaneously, and the log records nothing suspicious.

This is strictly worse than the matcher defects (17, 18, 78, 82), where a rule is consulted and gives a wrong answer. It sits with **74** (empty registry allows everything) as the "governance did not run" class.

## Exposure — and the honest position is that I have not measured it

Unlike 18 and 79, **I have no corpus count for P2-P5**, because I have not read what the four shapes are. Multi-line constructs are plausible in the corpus (heredocs appear 8 times in toolguard's logs, 0 in featherhill), but that is a guess about which shapes P2-P5 name, not a measurement.

**Recorded as a gap, not glossed.** Per `.claude/rules/evidence-before-fixing.md` the exposure question must be answered *before* implementation — so the first act of this ticket is to read P2-P5, extract their shapes, and count them across the three corpora. If they measure zero in featherhill the way 83, 84 and 87 did, this ticket is a defer candidate **despite its severity class**, and that tension should be resolved by Arnon rather than by me. Fail-open severity has so far overridden zero exposure (ticket 74); whether "never rule-matched" does the same is his call.

## The genuinely open prediction

**Does the fix stay in `multiline.py`, or does it reach the PEG grammar?**

Ticket 77's precedent cuts both ways and is the reason this is interesting: I expected a grammar change for `if`/`while` conditions and **the grammar already parsed them — the consuming Python discarded the field.** If the same holds, the fix is Python in `multiline.py` / `command_extractor.py` and the two-phase procedure does not apply. If the grammar genuinely cannot see these constructs, **phase 1 is `.peg` + canopy regeneration ONLY, reviewed alone**, per `.claude/rules/bash-grammar.md` — a rule that exists because grammar changes have repeatedly been implemented as Python instead.

The estimator is not told which. A wrong answer here is the expensive kind: the grammar path drags a generated file of several hundred lines into the diff.

## Falsifiable, locked now

1. **Each of P2-P5 gets its own test, and each must fail before the fix.** Four bypasses closed by one change with one test would leave three unpinned — the shape of ticket 31's finding (~65 assertions that cannot fail).
2. **The replay must be re-scored treating a no-match as `ask`**, per Arnon 2026-08-20. A bypassed command currently produces *no rule match*, so under this repo's `allow_with_no_warnings` it looks identical to an ordinary allow. **A verdict-only replay is exactly blind to the defect this ticket fixes** — the strongest instance yet of the blind spot found on ticket 18.

## Ordering discipline

The estimator writes `19-estimate-predictions.md` and `19-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.

---

## EXPOSURE MEASURED 2026-08-20 — and P2/P3 are NOT measurable from logs

| shape | featherhill | toolguard | total |
|---|---|---|---|
| heredoc (P2/P3) | **0** | 8 | 8 |
| 2+ heredocs on one line (P3) | 0 | 3 | 3 |
| escaped apostrophe (P4) | 0 | **1** | 1 |
| backslash continuation (P5) | **0** | **0** | **0** |
| any apostrophe *(not the trigger — P4 needs `\'`)* | 129 | 4,393 | 4,536 |

### The instrument is worst at the shape being counted

Ticket 51 measured that **4.84% of audit-log `Command` fields cannot be parsed back, and heredocs hit hardest.** So the corpus systematically under-records heredocs — **8 is a floor, not a count.** This is the same family as ticket 73 (*"the corpus-replay safety evidence is strongest exactly when it is emptiest"*): a null result produced by an instrument that cannot see the positive case.

**So the evidence gate returns "unmeasurable" for P2/P3, not "zero".** Those are different answers and must not be collapsed — collapsing them is how a defer gets justified by an instrument's blind spot.

### Recommended split, for Arnon

- **P5 — skip.** Zero backslash continuations across 58,096 commands, and unlike heredocs this shape is not lossy in the log, so the zero is real.
- **P4 — skip.** One occurrence, in dogfood. Cheap (*"a one-character regex fix"*) but unjustified on evidence. **Note the ticket's own argument for it — *"apostrophes are common"* — does not survive measurement**: P4 needs an **escaped** apostrophe, and the 4,536 plain apostrophes are not the trigger.
- **P2 / P3 — FIX, despite the low count.** Not because 8 is large, but because the count is a floor from a known-lossy instrument, and because **P2 drops the ASK floor on a foreign heredoc** — the mechanism this project's entire disclosure regime depends on, and the same floor tickets 67 and 79 concern. A bypass there means foreign code runs unprompted with no rule consulted.

**This is the first item in the campaign where the honest verdict is "the corpus cannot tell us."** Every prior defer (83, 84, 87, 17, 34, 36) rested on a zero the instrument was capable of contradicting.

---

## CONTAMINATED 2026-08-20 — the estimate reached the coordinator through the completion channel

**Ticket 19's surprise-factor measurement is void.** The estimator was instructed, in bold, to *"Return only the single word `DONE`. Nothing else — no summary, no file list, no findings"*, with the reason given explicitly (an earlier item was invalidated this way). It returned `DONE` — **preceded by a full summary of its predictions.**

The coordinator now knows, before implementation:

- the concentration set (`toolguard/parser/multiline.py`, `test/unit/test_multiline_bash.py`, both high confidence)
- the secondary files (`command_extractor.py`, `command_model.py`, and four test modules)
- **the layer prediction**: no `.peg` change, fix lands in the Python lexical pre-pass
- **the scope prediction**: one coordinated fix across two functions, not two independent fixes

Those last two were the *point* of this item. They cannot be scored now.

**Disposition: exclude ticket 19 from the series**, as item 05 was. Do not score it. The files remain on disk as a record of what the estimator said, not as data.

## The instruction is not sufficient, and that is the finding

**This is the second occurrence of the same failure with the same guard in place.** After 05, the fix was to instruct the estimator to write to files and return a token. That instruction was followed *and* violated in the same message — the token was returned, with the content attached to it.

**An instruction is not a mechanism.** The protocol's own recurring lesson, applied to itself: a rule with no enforcement gets dropped, and this one has now been dropped twice. Options for the aggregate write-up:

1. **Have the estimator write to a file the coordinator does not read until scoring, and accept that the return channel is unreliable** — i.e. treat any summary in the notification as expected and design around it. This means the coordinator must *stop reading completion notifications* for estimator agents, which is not currently possible.
2. **Run the estimator in a session the coordinator cannot observe**, and have a third party confirm completion.
3. **Accept contamination as a known error term** and report the series with contaminated items flagged, as here and for 05.

Option 3 is what is actually happening. It should be stated as a limitation in the aggregate rather than presented as a controlled experiment.

---

## MECHANISM READ 2026-08-20, and a hypothesis worth testing first

**P2**: `_classify_pipeline_sink` **segments on `|` only** — `&&`, `||` and `;` do not end a segment. So in `bash -c "true" && python <<EOF`, the earlier bash-family token captures the sink classification and the later foreign heredoc loses its floor. The heredoc body is then emitted **as an ordinary shell command**.

**P3**: `_process_heredocs(['bash <<A <<B', 'echo from-A', 'A', 'echo from-B', 'B', ''])` yields `['echo from-A', 'A', 'echo from-B', 'bash']` — the terminator `A` becomes a **command**, and bodies attach to the wrong sinks.

### Hypothesis: this is the third "the grammar already knows, the Python discards it"

`_classify_pipeline_sink` is hand-rolled segmentation that does not know `&&`, `||` or `;`. **The PEG grammar does** — compound decomposition is built on exactly those operators, and `.claude/rules/bash-grammar.md` exists because bash parsing keeps getting reimplemented in Python.

Two precedents, both confirmed by execution rather than assumed:

- **Ticket 77**: expected a grammar change for `if`/`while` conditions; the grammar already parsed them and the consuming Python had discarded the field.
- **Ticket 79**: expected possibly a grammar change for `$(...)`; **the grammar already parsed substitutions recursively.** Python-only fix.

**So check the grammar before touching it, and check whether the existing decomposition already yields the segment boundaries `_classify_pipeline_sink` is re-deriving.** If it does, the fix is to consume what exists rather than to extend a hand-rolled scanner — and the two-phase procedure does not apply.

### Sequencing note

**P2 is the same defect family as ticket 79** — foreign inline code evading the ASK floor. 79's fix landed in `_apply_leaf_policy`, described as the module's single floor-decision authority. **Do 19 while that machinery is fresh**, and establish whether P2 belongs in the same place or genuinely in the segmenter. Two floor mechanisms would be the `_command_variants`-feeds-DEFAULT-only mistake again.

### And apply ticket 79's hardest-won lesson

79 restored audit entries and, in doing so, **downgraded an unoverridable `hard_deny` to `ask`** — because `sub_matches` served both the audit trail and verdict derivation. P3 changes what appears as a command (`A` should stop being one). **Verify that changing the leaf set does not change any verdict**, with a case carrying a deny or hard_deny alongside the heredoc. A green suite did not catch it on 79.
