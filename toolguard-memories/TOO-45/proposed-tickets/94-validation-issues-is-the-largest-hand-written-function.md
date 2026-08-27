---
title: Configuration.validation_issues is the largest hand-written function and is still growing
tags:
- TOO-45
- proposed-ticket
- maintainability
permalink: toolguard/too-45/proposed-tickets/94-validation-issues-is-the-largest-hand-written-function
---

# `Configuration.validation_issues` — cyclomatic 35, and TOO-45 made it bigger

**Measured 2026-08-21** by `pyscn check toolguard/` during TOO-45's wrap-up.

`toolguard/config.py:Configuration.validation_issues` scores **cyclomatic 35** against a threshold of 10. It is **the largest hand-written function in the package** — of the 39 functions over threshold, 28 are in canopy-generated `bash_parser.py` and do not count, leaving 11, and this one leads them by 10 points.

## TOO-45 added to it, and that is the point

Ticket 52 put the wrong-shaped-permissions-list checks here, because this is where per-layer validation lives. **The fix was right and the function is now larger.** Five phase-3 commits touched this file.

**This is the "where comments cluster is a refactoring signal" rule in numeric form** — except nobody had to notice the commentary, because a threshold reported it.

## Why it matters more than a score

`validation_issues` is what turns a malformed config into the parse failures that trip the ask-floor. It is on the path that decides whether a user's configuration is trusted at all, and it now carries: section-shape checks, list-shape checks, per-layer `[hard_deny]` entry validation, the looked-past-assignment checks, and the merge-loop that ticket 52 found iterating a string character by character.

**Every one of those is a different question about a different part of the config.** They share a function because they share a caller, not because they share a subject.

## Suggested direction, not a design

Split by subject rather than by size: one checker per section shape, one per list shape, one per entry kind, with `validation_issues` becoming the composition. That makes each independently testable, which matters here because ticket 42 found `[hard_deny]` entries had **no validation at all** and nobody noticed — a gap that is much harder to have when each check is its own named thing.

**Do not split to hit a number.** If a genuine subject boundary does not exist, say so and leave it; the metric is a prompt to look, not a verdict.

## Do NOT do this before

Ticket 52's and 42's changes are recent and their tests are new. **Give them time in the field before restructuring the function they live in** — this is the only validation path a broken config takes, and a refactor that loses one branch silently loses a safety floor.
