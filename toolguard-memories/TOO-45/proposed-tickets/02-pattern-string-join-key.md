---
title: 02-pattern-string-join-key
type: note
permalink: toolguard/too-45/proposed-tickets/02-pattern-string-join-key
---

# Proposed: replace the pattern-string join key

**Status:** deferred from TOO-45, needs a design decision.

## Problem

The join key between a match result and its rule entry is **the pattern string itself**, and it is known non-unique — `merge_entries` exists precisely to handle same-pattern entries carrying contradictory metadata.

TOO-45's R2 removed the index-parallel arrays that used to pair patterns with entries, which was the sharper hazard. The string join survived because nothing forced it into view.

## Why it matters

Two entries with the same pattern text from different levels or files can be conflated at lookup. The symptom would be **wrong provenance or wrong `additionalContext` attached to a correct verdict** — plausible-looking output, no error.

Not currently known to misbehave. It is a latent correctness hazard, not an observed bug.

## Options

1. **Give `RuleEntry` a stable identity** (source file + level + ordinal) and join on that. Cleanest; touches every construction site.
2. **Carry the entry itself** through the match path instead of re-looking it up by pattern. Possibly free now that `LevelMatch` and `UnitVerdict` are structured types — worth checking whether the entry is already in scope where the join happens.
3. **Leave it, and add a test** pinning the behaviour when two levels declare the same pattern with different metadata, so the conflation becomes visible if it ever bites.

Option 2 is the one to scope first. If the entry is already available, this stops being a design question and becomes a small edit.

## Decision needed

Whether to scope option 2 now (an hour of investigation), or file for later.