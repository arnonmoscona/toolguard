---
title: 04-config-layer-stderr-consolidation
type: note
permalink: toolguard/too-45/proposed-tickets/04-config-layer-stderr-consolidation
---

# Proposed: route config-layer warnings through the real warning path

**Status:** deferred from TOO-45. The layering that blocked this has been fixed; the cleanup was left separate.

## Problem

**16 hand-rolled `stderr` writes across four config-layer modules** — `config.py` 3, `env_config.py` 2, `auto_migrate.py` 6, `config_divergence.py` 5. Engine has zero.

They exist because `log_writer`, `error_log` and `session_warnings` used to sit in the `runtime` layer, above `config`, so config-layer code could not legally import them. The layering was not being obeyed there; it was being routed around.

TOO-45 moved those four modules into a new `observability` layer below `config`, so the imports are now legal. **The bypasses remain.**

## Why it is worth doing

- Those warnings do not reach the warning log stream, so they are invisible to anyone auditing a session after the fact.
- They are not suppressed by the once-per-invocation machinery, so they can repeat noisily.
- The count is the visible evidence of the old layering error; leaving it invites someone to conclude the bypass is the convention.

## Why it is a decision, not just work

It is a **user-visible behaviour change**: text that currently goes to the terminal starts going to a log file, or to both. That affects what an operator sees during a broken-config situation — exactly the moment the message matters most. The right answer may be "both", per warning kind, rather than a blanket move.

## Size

Small-to-medium. 16 call sites, mechanical once the policy is decided. The policy is the work.

## Decision needed

What should a config-layer warning do — stderr only, warning log only, or both? Likely differs by kind: a broken config file wants to be loud and repeated; a deprecation notice does not.