---
title: 06-measurement-tools-keep-or-remove
type: note
permalink: toolguard/too-45/proposed-tickets/06-measurement-tools-keep-or-remove
---

# Proposed: git rm the measurement tools, or justify keeping them

**Status:** deferred from TOO-45 at your request, for discussion before push.

## How this got decided by accident

`tools/change_role_classifier.py`, `tools/touch_set_inventory.py`, `tools/touch_set_score.py` and four test files are **tracked** — they were swept in by a `git add -A` in a commit command I supplied, rather than chosen. Worth correcting deliberately either way.

## The case for removing

- They are **experiment instrumentation, not product**. Nothing in toolguard calls them.
- Two of the three were **proven biased** by adversarial testing. The role classifier's headline number was anti-correlated with code quality — factored code scored worse than copy-paste. The touch-set scorer's counts and rates were shown mathematically non-comparable across trees of differing granularity.
- **Neither contributed to any conclusion** in this ticket. Every canary finding came from implementer prose and direct verification.
- They carry roughly **90 tests** that must keep passing forever, for tools nobody runs.

## The case for keeping

- The classifier's **occurrence finding** was independently proven exact twice — 82/82, and 394 occurrences against an AST oracle. That part works.
- The inventory's **blindness guarantee** was audit-verified: 170 file opens, none outside the tree, no subprocess, no VCS access. That is the reusable piece if perturbation testing becomes a standing pre-push activity.
- Rebuilding them later costs more than keeping them.

## The caveat if kept

They must be **re-attacked before any reuse**. The last adversarial pass ended with residual silent loss in 13 of 24 implementation styles — a value bound to an intermediate local vanishes with every honesty bucket reading zero. Reusing them as-is would import that blind spot into whatever they measure next.

## Decision needed

Remove all three; or keep the inventory and delete the two scorers; or keep all three with a README stating they are unvalidated instruments.