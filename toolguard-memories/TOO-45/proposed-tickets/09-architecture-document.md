---
title: 09-architecture-document
type: note
permalink: toolguard/too-45/proposed-tickets/09-architecture-document
---

# Proposed: write docs/architecture-as-built.md

**Status:** you asked for this — "a new human-consumable well documented code architecture document."

## Why

Several TOO-45 reports contain foundational architecture material that is currently buried in ticket memory, where nobody will look in six months. The reports were written to explain a *change*; the project needs a document that explains the *state*.

## Proposed shape

Assembled from the branch-side material in `core-types-and-clarity`, `dependencies-before-after` and `layer-separation-before-after`, with every before/after diagram **redrawn as after-only** — the "before" stops mattering once this ships.

Content:

- The layer model and what each layer is for, including `observability` and why cross-cutting concerns sit low
- The verdict altitudes (`LevelMatch` / `UnitVerdict` / `RuntimeVerdict`) and why there are three
- The decision path end to end, as a diagram
- **The runtime dependencies that no import graph shows** — the `permission_resolution <-> resolve` cycle and the Protocols that describe it. This is the section a reader cannot derive from the code, and it is the reason the document is worth having.

Diagrams in **Mermaid**, small and focused.

## Staleness handling

**Stamped `As of <date> — toolguard <version> — commit <sha>` at the top.** A stamped stale document is useful; an unstamped one is a trap.

Two things make drift cheaper than it looks: the layer map is machine-checked, so that section cannot silently rot; and the runtime-edge section can be **regenerated from the profiler probe** rather than hand-maintained, so the part most likely to drift is the part that is measured.

**Not on a cadence.** Tie it to the same trigger as the review-cadence idea: when a ticket changes the layer map, adds or removes a module, or changes a runtime edge, updating this document is part of that ticket.

## Size

A writing job, not an engineering one. Needs your review more than my verification.

## Decision needed

Scope — is the four-section outline above right, and does it live in `docs/` (user-facing, linked from `llms.txt`) or somewhere internal?