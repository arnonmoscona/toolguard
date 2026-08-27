---
title: 03-permission-resolution-resolve-cycle
type: note
permalink: toolguard/too-45/proposed-tickets/03-permission-resolution-resolve-cycle
---

# Proposed: remove the permission_resolution <-> resolve runtime cycle

**Status:** deferred from TOO-45. The sibling cycle (`compound <-> resolve`) was removed; this one was typed but not removed.

## Problem

`resolve.py` imports `permission_resolution`; `permission_resolution` calls back into `resolve._decide_detailed` through an injected callable. Profiling one real decision: `permission_resolution -> resolve` 4 calls, `resolve -> permission_resolution` 3. A bidirectional runtime cycle no import graph shows.

TOO-45 made the shape explicit — `ResolutionConfig`, `ResolveConfig` and `DecideDetailed` Protocols in `config_types` — so a reader can now see what each side depends on, and pyright checks it. **The cycle itself is unchanged.**

## Why removal may be easier than it was for compound

The `compound` cycle existed because `compound` owned *policy* (the ASK floor). Removing it meant moving that policy, which was the hard part. This cycle is a narrower case: `permission_resolution` needs per-level matching, and `_decide_detailed` supplies it.

Likely shapes: pass the level matches as data rather than as a callable, or invert the iteration so `resolve` drives and `permission_resolution` becomes a pure cascade over supplied matches. Same "decompose then decide" move that worked for compound.

## Precedent worth reusing

The compound removal was designed by two independent authors, judged blind, and implemented with an abandon gate — and the judge's effort estimate was the most informative signal about which design was simpler. Cheap to repeat.

## Size

Estimate 3-6 hours by analogy, unvalidated. The compound work came in at the low end of its estimate once the design was right.

## Decision needed

Now, or a future ticket? The Protocols already deliver most of the *comprehensibility* win; removal buys a graph a reader can trust without running a profiler.