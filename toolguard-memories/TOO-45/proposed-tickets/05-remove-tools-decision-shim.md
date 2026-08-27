---
title: 05-remove-tools-decision-shim
type: note
permalink: toolguard/too-45/proposed-tickets/05-remove-tools-decision-shim
---

# Proposed: delete tools/decision.py and import toolguard.api directly

**Status:** deferred from TOO-45, awaiting your call (you said you would look closely before push).

## Problem

R6-S2 moved `decide()` into `toolguard/api.py` and left `tools/decision.py` as a 38-line re-export. `hook.py` now imports from `toolguard.api` directly, so the layer graph is clean — but **six production modules and about eleven test files still import `decide` from the shim**:

```
toolguard/tools/uninstall_readiness.py    toolguard/tools/mining.py
toolguard/tools/self_permission.py        toolguard/tools/consolidate.py
toolguard/tools/replay.py                 toolguard/testing/sandbox.py
```

The import statements do not say what the architecture means. A reader tracing the decision path lands in a tooling module and has to discover it is a forwarding stub.

## Why it is a shim for a break we control

Backward-compatible re-exports earn their keep when external callers exist. There are none — this is a single repo, and every caller is in it. The compatibility being preserved is with ourselves.

## Proposed

Re-point all importers at `toolguard.api`, delete `tools/decision.py`, keep no alias. Mechanical: ~17 edits, all one-line, guarded by the golden corpus and 2,600 tests.

## Counter-argument, stated fairly

`tools/decision.py` is a name that appears in documentation and possibly in user-facing guidance. Deleting it invalidates those references. That is an argument for a doc sweep alongside, not for keeping the stub.

## Decision needed

Do the sweep, or keep the shim? If keeping, it should carry a comment saying why it exists, because "backward compatibility" is not currently true of anything.