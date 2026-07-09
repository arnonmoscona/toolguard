---
title: 'Future idea (shelved): pluggable security classifiers / stateful tightening-only
  toolguard'
type: idea
permalink: toolguard/too-15/parking-lot/future-idea-shelved-pluggable-security-classifiers-stateful-tightening-only-toolguard
tags:
- toolguard
- future
- parking-lot
- security
---

# Future idea (shelved): pluggable security classifiers / stateful tightening-only toolguard

Raised by Arnon 2026-07-04 during the featherhill maintenance dry-run, while discussing
`#NOSECURITY: dev convenience` on `uv run python:*` (ungoverned arbitrary code execution).
**Shelved -- discuss AFTER TOO-15 to decide if it has merit. A separate ticket if pursued.**

## The gap this addresses

`#NOSECURITY` on a code-execution allow (e.g. `uv run python:*`) is a blanket, standing
exception. Today toolguard cannot analyze what such a script actually does, and an agent
that hits a deny rule can route around it by writing a throwaway script. No current
facility catches that.

## The idea

- **Pluggable security classifiers** over a **stateful** version of toolguard that detects
  situations where an agent encounters a DENY and then tries to work around it with
  permitted scripting.
- **Tightening-always approach:** never loosens deny rules; may *block* or *convert allows
  to ask/deny* based on a soft evaluation of submitted scripts. (Soft/heuristic -- "never
  fully reliable, ever" per Arnon.)
- Related but distinct: a possible **toolguard auto-mode** with pluggable classifiers +
  proper logging -- things Claude's native auto-mode lacks. NB: the current toolguard hook
  effectively BLOCKS Claude's auto-mode anyway, since the hook intercepts and governs those
  tool uses.

## Constraints / caveats already stated

- Never fully reliable -- do not imply the tooling will catch a bad script.
- Separate future ticket; not TOO-15 scope. Revisit as a discussion post-TOO-15.

Relates to [[conversational-multi-pass-maintenance-redesign-design]].
