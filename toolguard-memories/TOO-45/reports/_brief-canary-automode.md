---
title: _brief-canary-automode
type: note
permalink: toolguard/too-45/reports/brief-canary-automode
---

# Brief: the tougher canary — a mode-dependent verdict enrichment

Read `_shared-context.md` in this directory first.

**You are the only author permitted to modify code.** You work in `/tmp/toolguard-master-copy` (before) and `/tmp/toolguard-branch-copy` (after). **Do not touch `/home/arnon/projects/toolguard`.**

## Why this experiment exists

TOO-45's existing change-cost canary tracks `additionalContext` — an enrichment that rides *alongside* a verdict without ever changing it. Arnon's judgement is that this is too easy a test, for two specific reasons:

1. **A mode-dependent rule changes the verdict itself**, so its effect and evaluation land in at least two different places in the code.
2. **It must know something about the input payload at a later phase of hook execution** — the permission mode arrives in the hook event and has to reach the decision point.

It is also **a case the refactor never optimised against**, which makes it a defence against over-fitting. Arnon has said the immediate future holds enrichments close to this in concept, so the answer matters practically, not just as a score.

## The feature to implement, identically in both trees

A permission rule entry may carry a new attribute — call it **`allow_in_auto_mode`** (boolean, default false).

Semantics: when such a rule matches AND Claude Code is running in an automatic permission mode, the resulting decision becomes **allow**; otherwise the rule's normal decision applies unchanged. So a rule that would normally produce `ask` yields `allow` when the agent is running unattended, and `ask` when a human is present to answer.

Determine the real permission-mode values from the codebase — `permission_mode` arrives in the `PreToolUse` hook event and toolguard already reads it (grep for `permission_mode`). Do not invent values; use what Claude Code actually sends. Decide and state which modes count as "auto".

**Implement the same feature, to the same standard, in both trees.** Same semantics, same level of care, tests in both. This is a controlled comparison: if you implement it well in one and sloppily in the other, the experiment is worthless. Write it the way you would if it were the real ticket, in each tree's idiom.

Do NOT try to make the two implementations structurally similar. Let each tree pull the change into whatever shape that tree wants. **The shape it pulls toward is the actual finding.**

## What to measure — per tree, by execution

- **files touched** (`git diff --stat` in each tree)
- **LOC touched** — added/removed/modified, production and test separately
- **code locations touched** — the number of distinct functions/methods/classes changed, counted from the AST, not by eyeball
- **layers/modules crossed** — which architectural layers the change had to reach into
- **co-change spread** — how far apart the touched sites are: same function, same module, adjacent modules, or scattered
- **how many places had to learn about permission mode** that did not know about it before
- **whether the existing test suites still pass** in each tree, and how many tests you had to change versus add

Use the same counting method on both trees and say what it is.

## What to judge — argue it, with evidence

- **Concerns separation.** In each tree, is "what mode are we in" cleanly separated from "what does this rule decide"? Or do they interleave?
- **Natural change or shoehorn?** Does the new structure make this feature a natural extension — an obvious place to put it, obvious to find later — or does it still have to be forced in? Be specific about which parts felt natural and which fought back. **This is the central question of the report.**
- **Reviewability.** After the fact, how hard is the diff to review and reason about in each tree? Would a reviewer be able to convince themselves it is correct? Where would they have to hold several files in their head at once?
- **Did TOO-45 do enough?** Given this result, is the current branch in a reasonable state for the enrichments coming next, or is more work needed first? If more, say precisely what — that becomes the next ticket.
- **Over-fitting check.** Did the refactor help *generally*, or only on the shapes it was tuned against? This case was never optimised for; say honestly whether the benefit transferred.

**A finding of "the refactor did not help much here" is a completely acceptable and valuable result.** Do not manufacture an improvement. If the branch made it worse in some respect, say so and show it.

## Method notes

- Implement in the **master copy first**, before you know what the branch makes easy. Anchoring on the branch's shape first would bias the comparison.
- Keep the two implementations behaviourally equivalent. Write a small scenario list up front (rule matches + auto mode, rule matches + interactive mode, rule does not match, compound command with one such leaf, etc.) and verify both trees behave identically on all of them. **A compound-command scenario is essential** — that is where the branch's `UnitVerdict`/`sub_matches` structure would either help or not.
- `git diff` in each tree gives you exact measurement; both copies have full `.git`.
- **Never run a git write** — no checkout/restore/stash/reset/commit, in any tree. They hang waiting for a human. If you need to undo something, back the file up first and copy it back.

## Deliverable

`toolguard-memories/TOO-45/reports/canary-automode-experiment.md` in the REAL repo (that is a report file, not code — writing it there is expected), tagged `task-memory` and `TOO-45`.

Lead with the verdict: natural change or shoehorn, and did TOO-45 do enough. Then the measurement table for both trees side by side, then the judgement sections, then the two diffs summarised (not pasted in full — link to the trees and give `git diff --stat` output). Include at least one small focused diagram contrasting where the change lands in each tree; PlantUML preferred, rendered to `img/` and embedded.

Do not hard-wrap paragraphs.