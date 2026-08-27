---
title: 07-doc-comment-cleanup-sweep
type: note
permalink: toolguard/too-45/proposed-tickets/07-doc-comment-cleanup-sweep
---

# Proposed: doc-comment and comment cleanup sweep

**Status:** you asked for this explicitly — "a dedicated sweep after the next commit to specifically clean up doc comments across the board."

## Problem

Comments and docstrings across the project are too long, and much of the added material has a short shelf life. Your words: "Opus5 is way too verbose."

Three distinct defects, worth separating because they need different treatment:

1. **Ticket narrative in code.** "TOO-45 R1e changed this because..." is useful for weeks and misleading thereafter. A bare ticket reference is a fine pointer; the story is not.
2. **Length for its own sake.** Docstrings that argue a case rather than state a contract. Long rationale belongs in technical documentation with a reference left behind.
3. **Comments compensating for complexity.** `compound.judge_unit()` is the named example — high cognitive complexity, not helped by verbose commentary explaining it. **Where this is the cause, split the function rather than trimming the comment.**

Global guidance now carries the rule, so new code should not reproduce it. This sweep is about existing code.

## Proposed approach

Scope to `toolguard/` production modules first; `tools/` and tests second. Work module by module, not by a global regex — this is judgement, not a transformation.

Explicitly *not* a goal: removing comments that explain **why**. The target is narrative, restatement of what the code plainly says, and ticket archaeology.

**Risk worth naming**: an agent told to shorten comments will shorten the useful ones too. The measure of success is a reader's comprehension, not a line count — so no line-count target should be set, and a sample should be reviewed by you before the sweep runs wide.

## Size

Medium, and mostly unreviewable in bulk — which argues for doing it in module-sized batches you can actually check.

## Decision needed

Timing (you said after the next commit), and whether `compound.judge_unit()` gets split as part of it or separately.