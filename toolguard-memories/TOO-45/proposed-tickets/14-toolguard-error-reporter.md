---
title: 14-toolguard-error-reporter
type: note
permalink: toolguard/too-45/proposed-tickets/14-toolguard-error-reporter
---

**PARTIALLY FIXED in `05f786d`.** The error reporter is built (`toolguard/error_reporter.py`) and symptom 1 is pinned; still open: the takeover notice still writes straight to stderr — see `toolguard/session_warnings.py:27,33`.

# Proposed: a toolguard error reporter — one place that decides where toolguard's own problems go

**Status:** rewritten 2026-08-08 to Arnon's framing, which is broader and better than the original. The original ticket was "the deny JSON goes to the wrong stream"; that is one symptom.

## Arnon's requirement

> All stderr indicating issues with toolguard itself should be visible to Claude — perhaps as additional context or any other feedback mechanism. Both Claude and the user should be made aware that there is a serious error. Under normal conditions, nothing should be in stderr; everything goes in the normal logs, warning logs etc. This stderr behaviour should be encapsulated as some kind of toolguard error reporter, so it is easier to change what its behaviour is in the future — does it only report back to Claude? Does it also dump to a log file? Does it still emit stderr? None of that should matter to whatever calls the internal error reporter.

## Symptom 1 — an error deny never reaches Claude Code. MEASURED.

```
$ echo 'not valid json' | uv run python -m toolguard.hook
exit=0
STDOUT: (empty)
STDERR: {"hookSpecificOutput": {... "permissionDecision": "deny" ...}}
```

Normal paths print the decision to **stdout** (`hook.py` ~1228, ~1254). Three error handlers print it to **stderr** and exit 0 (~1272 `JSONDecodeError`, ~1284 `ValueError`, ~1294 `Exception`). Claude Code reads the decision from stdout, so an empty stdout with exit 0 means "no opinion" and the call falls through to native handling.

The `except Exception` handler is the catch-all for every unanticipated internal error. Its entire purpose is to fail closed. It fails open.

## Symptom 2 — the premise "nothing is in stderr under normal conditions" is FALSE today. MEASURED.

A perfectly ordinary allowed command:

```
$ echo '{... "tool_name":"Bash","tool_input":{"command":"ls"} ...}' | uv run python -m toolguard.hook
exit=0
stdout: 251 bytes (the decision)
stderr: [TOOLGUARD WARNING] Takeover mode is active. Claude's native permission
        prompts are bypassed. ...
```

**The takeover notice is written to stderr on every single tool call**, unconditionally and by design (`session_warnings.issue_takeover_warning`; its once-per-day marker only ever gated its own housekeeping — see punch-list #01).

**Arnon's correction to my first reading of this (2026-08-08):** I argued that routing stderr to Claude would inject that sentence into every tool call's context. He pointed out this is only true *"if the implementation of an error reporter allowed it to"* — a reporter that classifies simply would not route a routine notice to Claude. That is right, and it dissolves the objection as stated.

**What survives is the requirement it implies.** The reporter can only route correctly if the distinction exists at the **call sites**, and today it does not. All three of these are the same `print(..., file=sys.stderr)`:

| what it is | example |
|---|---|
| a routine notice, expected, every call | the takeover-mode notice |
| a genuine toolguard fault | a config file that failed to parse |
| a fault **and** a decision | the deny from the catch-all exception handler |

So the first piece of work is not the routing — it is making callers declare **what kind of thing they are reporting**, never where it goes.

**Arnon, sharpening this further (2026-08-08):** *"That's the idea behind an error reporter — it communicates intent. Noise suppression is not a concern of the code that calls it. It's an implementation and requirement question for the error reporter. The calling code just wants to say 'hey, I got this serious problem'. It's all it needs to know."*

So the caller's contract is **severity and what happened. Nothing else.** Not the stream, not the audience, not whether it has been said before. Every one of these is the reporter's requirement, changeable in one place:

- does it reach Claude, a log, stderr, or several
- is it deduplicated, and over what period
- does it affect the permission decision

Note the consequence for the caller side of #01: I initially had callers deciding "this should reach Claude", which is the same mistake one level up — an audience is still a mechanism.

Note the shape: this is the same defect as punch-list #01's, where call sites talked about claims instead of about intent. Here they talk about a stream instead of about severity.

## What the reporter should own

One module, one call, callers say **what happened** and never **where it goes**:

- routing to Claude — as `additionalContext`, as a decision reason, or another mechanism
- routing to the error/warning logs
- whether stderr is still written at all
- deduplication, so a repeated fault does not repeat forever (note the dependency on punch-list #01's once-per-period work — and note that if the store itself is the thing that failed, the reporter cannot rely on it)
- severity: a fault that should fail closed versus a notice that should not affect the decision

Callers should not branch on any of it. The point of the encapsulation is that all of the above can change later in one place.

## Verification this needs

- A test per error handler asserting the decision lands on **stdout**. Asserting "a deny was produced" is exactly what passes while this is broken — **the assertion must be on the stream**.
- A test that a normal, uneventful invocation writes **nothing** to stderr, so symptom 2 cannot come back.
- Consider whether the error paths should exit 2 as well. Exit 2 is the host's own blocking signal and would fail closed even if the JSON were malformed — belt and braces for the handler that exists precisely for the unforeseen.

## Why nothing caught this

The golden corpus compares verdict **objects**. These paths construct a correct verdict and send it to the wrong stream, so the corpus is structurally blind to it — as are 2,635 tests, ruff, pyright and the layer checker. Worth recording next to the existing note that the corpus does not guard `hook.py`'s write loop (ticket #12): **the corpus guards what a decision is, never where it goes.**

## Decision needed

Scope. The stream fix is small and is a fail-open in a permission tool. The reporter abstraction and the takeover-notice channel question are a design, and they are what makes the fix durable.
