---
title: TOO-45 surprise factor - ticket 17 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/17-prereg
---

# Pre-registration, proposed ticket 17 (`[native]` end-anchor false negatives)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## LEAK STATUS: SEVERE — the worst in the series so far, and it is systematic

Ticket 17 names, in `path:line` form or as bare module names: `toolguard/patterns.py` (with line numbers 132-135), `toolguard/permissions.py` (line 118), `toolguard/file_matching.py` (lines 101-102, 113), `test/unit/test_patterns.py` (with the class names `TestNativePattern` and `TestPatternTypeComparison` and the test name `test_glob_vs_native_wildcard_semantics`), and `docs/permission-patterns.md` (lines 115-118).

That is very nearly the entire plausible touch set, handed over. **Raw recall on this item is close to meaningless** — an estimator that transcribes the ticket scores high without predicting anything. Only the leak-discounted set carries signal, and it may be nearly empty.

## This is not bad luck on one ticket — it is a property of the ticket family

Tickets 17, 18 and the rest of the 17-33 band were produced by the **#07 doc-comment sweep**, whose method was to *execute a claim and cite where it failed*. A ticket written that way cannot help naming its own files with line numbers; the citation **is** the finding. The measure is therefore weakest exactly where the tickets are best evidenced.

**Recorded now, before results, so it cannot be mistaken for an after-the-fact excuse for a poor score.** For the aggregate this is a finding about the instrument, not about the architecture: *the surprise factor measures foresight only on tickets that describe a defect without locating it*, and this series contains two populations that should probably never be pooled — the punch-list items (01, 03, 04, 05, 10, 15) and 44/77/78/80, which named few or no files, versus the sweep-derived band, which names nearly all of them.

If the leak-discounted actual set for 17 turns out to be empty, the honest report is **"not scoreable"**, not a recall of 1.0 over a set of size zero.

## What is genuinely NOT leaked, and is therefore the whole measurement

Three things the ticket does not settle, where an estimator can still be right or wrong:

1. **Which fix is taken.** The ticket offers two (patch the end anchor; translate to a regex under `re.fullmatch`). Option 2 removes the defect class and is the smaller conceptual surface but the larger rewrite of the branch. The estimator is not told which is chosen — unlike ticket 77, where design was leaked deliberately because the candidates implied different files. Here both options land in the same function, so the design leak buys nothing and withholding it preserves one real prediction.
2. **Whether the blast radius stays inside the matcher.** Ticket 18 measured that *its* fix breaks 20 tests, none of them in `test_permissions.py` or `test_patterns.py` — the consolidation/redundancy/golden-corpus tier is built on the matcher's current answers. Ticket 17's fix makes NATIVE match **more**, so the same tier may move. **This is the item's real question**, and a `C` (hidden coupling) surprise here would be a genuine architectural finding rather than estimator ignorance.
3. **Whether the three "also worth deciding" items are taken in scope** — the dead DEFAULT branch, the duplicated `except`, and the two non-`str` inputs that raise outside the guard.

## Contamination, carried forward

The 77 and 80 estimators both reported that their system prompt carried project context they had not been given deliberately — both `CLAUDE.md` files, the auto-memory index (which names modules), and a git status listing untracked filenames. **Nothing has been done to remove that**, so 17 inherits it. On this item it matters less than usual, since the ticket leaks more than the ambient context does.

Blinding remains **honour-system** from item 44 onward: the estimator is told to read only the ticket and the briefing, and to declare everything it read. A declaration is evidence, not proof.

## Ordering discipline

The estimator writes `17-estimate-predictions.md` and `17-estimate-uncertainties.md` and returns only `DONE`, so the estimate cannot reach the coordinator through a completion notification — the defect that contaminated item 05. Neither file is opened until the ticket is green.
