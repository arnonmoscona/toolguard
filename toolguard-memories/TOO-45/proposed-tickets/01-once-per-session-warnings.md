---
title: 01-once-per-session-warnings
type: note
permalink: toolguard/too-45/proposed-tickets/01-once-per-session-warnings
---

# Proposed: implement real once-per-session warning suppression

**Status:** deferred from TOO-45, needs a design decision.

## Problem

"Once per session" has been wanted three times and implemented zero times. The codebase carries **three copy-pasted date-marker mechanisms** plus module globals in `hook.py` whose own docstrings concede they cannot work — toolguard is a fresh interpreter per tool call, so a module global is a no-op guard.

`toolguard/session_warnings.py` is the fourth instance: named for a session semantic, implements per-day suppression via `.toolguard-warned-YYYY-MM-DD` files. TOO-45 fixed its *description*; the semantic gap remains.

This is the exact trap already recorded in long-term memory, sitting in the codebase in quadruplicate.

## What a fix requires

Key on `session_id`, which **is** present on every `PreToolUse` payload and is currently read by nothing on the decision path. Marker files would become `.toolguard-warned-<session_id>` or an equivalent keyed store.

Open questions that make this a decision rather than an edit:

- **Cleanup.** Session-keyed markers accumulate with no natural expiry. Date markers self-expire by being named for a date. Needs a reaping rule.
- **Scope.** Does every warning become per-session, or only some? `config-sync.md` documents both frequencies and never says which warning uses which.
- **Is per-day actually wrong?** For a broken-config warning, per-day may be the better behaviour and only the *name* was misleading. Worth settling before building machinery.

## Size

Small if per-session is genuinely wanted (one keyed store, one call site per warning kind). Medium if the three existing mechanisms are consolidated at the same time, which is the real prize — four implementations of one idea is the actual defect.

## Decision needed

Do we want per-session semantics at all, or do we want to consolidate the three duplicate mechanisms and keep per-day? Consolidation is worth doing either way.