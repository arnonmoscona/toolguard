---
title: 14-hook-error-paths-fail-open
type: note
permalink: toolguard/too-45/proposed-tickets/14-hook-error-paths-fail-open
---

**FIXED in `05f786d` (TOO-45 phase 2).** The hook's deny decisions now reach Claude Code via stdout `additionalContext` instead of stderr — see `test/unit/test_hook_error_reporter.py:452`.

# Proposed: the hook's error paths emit their deny on stderr, so it never reaches Claude Code

**Status:** found 2026-08-08 while verifying an adversarial review of punch-list #01. **Pre-existing — not introduced by TOO-45.** Security-relevant. Needs Arnon's decision on when, not whether.

## Measured

```
$ echo 'not valid json' | uv run python -m toolguard.hook
exit=0
--- STDOUT (what Claude Code reads) ---
[end stdout]
--- STDERR ---
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", ...}}
```

**Stdout is empty. Exit code is 0. The deny is on stderr.**

Claude Code reads the `permissionDecision` from **stdout**. Empty stdout with exit 0 means "this hook has no opinion", so the call falls through to native permission handling. The hook believes it denied; nothing was denied.

## Where

`toolguard/hook.py` — the normal paths print to stdout (lines ~1228, ~1254); **three error handlers print to stderr and exit 0**:

| handler | line |
|---|---|
| `except json.JSONDecodeError` | ~1272 |
| `except ValueError` | ~1284 |
| `except Exception` | ~1294 |

Three more at ~705/710/717 need checking for the same shape.

## Why it matters more than it looks

The generic `except Exception` handler is the catch-all for **every unanticipated internal error**. Its whole purpose is to fail closed when something unexpected happens. It currently fails open, and does so silently — a crash report is written, the agent sees nothing, and the tool call proceeds under native rules.

Under **takeover mode** that is the worst case, and the product already says so in its own warning text: *"If toolguard fails or is misconfigured, blanket allows in native config will be exposed."* The failure mode is known and documented — what is new is that a path intended to deny reaches it.

## How it surfaced

An adversarial reviewer traced a `ValueError` from a malformed timestamp in the new suppression store through `hook._run_divergence_check` (no handler) into `main()`'s `except ValueError`, and predicted the fail-open. I checked the mechanism directly with a JSON parse error, which reaches the sibling handler. Confirmed.

**Item #01 did not create this.** It created one new route to it. The route is being closed inside #01; the handlers are this ticket.

## Fix

Print the decision JSON to **stdout** on every path that produces a decision, error paths included. Keep the human-readable diagnostics on stderr.

Worth deciding at the same time: should these paths exit 2 instead of 0? Exit 2 is the host's own blocking signal and would fail closed even if the JSON were malformed. Belt and braces for the one handler that exists precisely for the unforeseen.

## Verification this needs

A test per handler asserting the decision lands on **stdout** — asserting "a deny was produced" is exactly what would have passed while this was broken. The check must be on the stream, not on the content.

Also worth a golden-corpus thought: the corpus compares verdicts, and these paths produce a verdict object that is simply sent to the wrong place. **The corpus cannot see this class of defect**, which is worth recording alongside the existing note that it does not guard `hook.py`'s write loop (ticket #12).

## Decision needed

Now, inside TOO-45, or a ticket of its own? It is small and it is a fail-open in the catch-all error handler of a permission tool.
