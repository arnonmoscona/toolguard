---
title: TOO-45 surprise factor - ticket 83 pre-registration
type: note
tags:
- task-memory
- TOO-45
- measurement
permalink: toolguard/too-45/reports/surprise/83-prereg
---

# Pre-registration, proposed ticket 83 (a `~`-spelled rule does not match an absolute path)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## LEAK STATUS: LIGHT — the best item in the series so far, and worth saying why

Ticket 83 names **no module in `path/module.py` form and no line numbers.** It refers to its subject functionally: *"file-path matching is a different path through the matcher"*, `[regex]`, `[native]`, `[glob]`, DEFAULT, and the fact that 78 handled commands.

That is a real prediction task. An estimator must work out *which* modules implement file-path matching versus command matching, and whether the fix lands in one, two or three of them — none of which the ticket discloses.

**The contrast with ticket 17, pre-registered an hour earlier, is the point.** 17 names `patterns.py:132-135`, `permissions.py:118`, `file_matching.py:101-102,113`, `test_patterns.py` with class *and* test names, and `docs/permission-patterns.md:115-118` — very nearly its whole touch set. Both tickets are in the same series and describe defects of comparable size in the same subsystem, so **they form a natural leak-controlled pair**: same domain, same implementer, same week, opposite leak levels. If recall is similar on both, the measure is not detecting foresight. That pairing should be called out explicitly in the aggregate; it is the closest thing to a controlled comparison this series will produce, and it arose by accident rather than design.

The cause of the difference is structural, not editorial. 17 came from the **#07 doc-comment sweep**, whose method was to execute a claim and cite where it failed — a ticket written that way *cannot* avoid naming its files, because the citation is the finding. 83 was written from a **behavioural probe** (`rule` versus `path`, evades / does not evade), which names no code at all.

**A tunable candidate for the aggregate, recorded now so it is not a post-hoc rationalisation**: the protocol may be worth running only on behaviourally-derived tickets, and formally excluding citation-derived ones as unscoreable rather than scoring them and discounting.

## What is genuinely open

1. **How many subsystems the fix touches.** The ticket asserts the command side and the file side are different paths through the matcher. Whether the fix is one shared helper or two parallel edits is the estimator's call and the architectural question.
2. **Whether the fix is written as symmetry or as a second one-directional patch.** The ticket argues for symmetry from 78's identity argument (`~/x` and `/home/arnon/x` are the same file, so the transformation applies to granting and restricting rules alike — unlike 77's assignment stripping, where `LD_PRELOAD=evil ls` genuinely is not `ls`). The estimator is **not** told which is chosen.
3. **Blast radius into the consolidation/redundancy/golden-corpus tier**, which is built on the matcher's current answers. A `C` (hidden coupling) surprise here is a genuine architectural finding.

## Evidence obligation carried from 78, and it is the part most likely to be skipped

**This repository's own rules cannot demonstrate the deny direction** — every rule it has naming an absolute home path is an `allow` rule. A corpus replay over this config will therefore come back clean while proving nothing about the case that matters. 78 hit exactly this and built the deny-direction evidence deliberately (562 constructed commands). **83 must do the same; a clean replay is not evidence here.** This is the project's anti-vacuity rule: a null result over a path nothing exercises is meaningless.

## Contamination and blinding, unchanged

Same as items 44 onward: blinding is **honour-system**, and the estimator's system prompt carries project context nobody chose to give it — both `CLAUDE.md` files, the auto-memory index (which names modules), and a git status listing untracked filenames. **On this item that contamination matters more than usual**, precisely because the ticket itself leaks so little: the ambient context may now be the estimator's *main* source of module names, which would show up as unearned recall. The estimator must declare every file it read, and the declaration should be read sceptically against how specific its predictions are.

## Ordering discipline

The estimator writes `83-estimate-predictions.md` and `83-estimate-uncertainties.md` and returns only `DONE`. Neither file is opened until the ticket is green.
