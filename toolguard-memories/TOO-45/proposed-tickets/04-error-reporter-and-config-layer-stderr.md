---
title: 04-error-reporter-and-config-layer-stderr
type: note
permalink: toolguard/too-45/proposed-tickets/04-error-reporter-and-config-layer-stderr
---

# A toolguard error reporter, and the config-layer stderr writes moved onto it

**Status:** ACCEPTED, in scope for TOO-45. **Merges proposed #04 into the core of proposed #14** (Arnon, 2026-08-09). Supersedes `04-config-layer-stderr-consolidation.md`; `14-toolguard-error-reporter.md` is retained for its measurements and for the parts deliberately left out.

## Why they merged

#04's open decision was *"should a config-layer warning go to stderr, to the warning log, or both, per kind?"* — and #14 already answers it: **callers state severity and what happened; the reporter decides where it goes.** Answering #04 on its own terms would mean making a routing decision at each of 16 call sites and then unmaking it when the reporter arrived. The 16 sites get touched once.

## Problem

**16 hand-rolled `stderr` writes across four config-layer modules** — `config.py` 3, `env_config.py` 2, `auto_migrate.py` 6, `config_divergence.py` 5. The engine layer has zero.

They exist for a layering reason that no longer holds. `log_writer`, `error_log` and `session_warnings` used to sit in the `runtime` layer, above `config`, so config-layer code could not legally import them; the layering was not obeyed there, it was routed around. TOO-45 moved those modules into an `observability` layer below `config`, making the imports legal. **The bypasses remain**, and left alone they read as the convention.

Consequences today: those warnings never reach the warning log stream, so a session cannot be audited after the fact; and nothing throttles them, so they can repeat.

## Requirement (Arnon, 2026-08-08)

> All stderr indicating issues with toolguard itself should be visible to Claude — perhaps as additional context or any other feedback mechanism. Both Claude and the user should be made aware that there is a serious error. Under normal conditions, nothing should be in stderr; everything goes in the normal logs, warning logs etc. This stderr behaviour should be encapsulated as some kind of toolguard error reporter, so it is easier to change what its behaviour is in the future — does it only report back to Claude? Does it also dump to a log file? Does it still emit stderr? None of that should matter to whatever calls the internal error reporter.

> That's the idea behind an error reporter — it communicates intent. Noise suppression is not a concern of the code that calls it. It's an implementation and requirement question for the error reporter. The calling code just wants to say "hey, I got this serious problem". It's all it needs to know.

**The caller's contract is severity and what happened. Nothing else.** Not the stream, not the audience, not whether it has been said before.

## What the reporter owns

- which of stderr / the warning log / the error log / Claude receives it, per severity
- whether it is throttled, and over what period — building on the once-per-period facade from punch-list #01, with the caveat that the reporter cannot depend on that store when the store itself is what failed
- whether the message affects the permission decision

Callers must not branch on any of it. The whole point of the encapsulation is that every one of the above can change later in one place.

## The premise is false today, and that is part of the work

"Under normal conditions nothing should be in stderr" is not true now. A perfectly ordinary allowed command emits the takeover-mode notice on stderr on every single tool call, by design. Three different things are the same `print(..., file=sys.stderr)` today:

| what it is | example |
|---|---|
| a routine notice, expected, every call | the takeover-mode notice |
| a genuine toolguard fault | a config file that failed to parse |
| a fault **and** a decision | the deny from the catch-all exception handler |

The reporter can only route correctly if that distinction exists at the call sites. Making callers declare **what kind of thing they are reporting** is therefore the first piece of work, not the routing.

## Deliberately NOT in this item

- **The hook error-path fail-open** (`hook.py`'s three error handlers print the deny JSON to stderr and exit 0, so Claude Code sees an empty stdout and falls through to native handling). That is a correctness bug in a permission tool, not a routing cleanup, and it deserves its own change and its own tests. It stays in `14-toolguard-error-reporter.md`.
- Deciding the final channel for the takeover notice (Claude vs stderr vs log). Classifying it correctly is in scope; changing where the user sees it is a behaviour change to decide separately.

## Verification this needs

- A test that a normal, uneventful invocation writes **nothing** to stderr beyond what is deliberately classified as a routine notice.
- Per-severity tests asserting the destination, not merely that something was emitted. Asserting "a warning was produced" is exactly what passes while routing is wrong.
- The golden verdict corpus is structurally blind here: it compares verdict objects, so it guards what a decision *is* and never where anything *goes*.

## Size

Medium. One new module and a policy, plus 16 mechanical call-site moves once the policy exists. The policy is the work.
