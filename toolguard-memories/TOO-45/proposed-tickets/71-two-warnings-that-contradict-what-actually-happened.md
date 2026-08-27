---
title: Two warnings that contradict what actually happened -- a spurious governed_tools
  complaint on the default config, and "Logging disabled" printed while logging works
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/71-two-warnings-that-contradict-what-actually-happened
---

# Two messages that say the opposite of what the code did

**Found 2026-08-13 while measuring `toolguard.testing.sandbox`. Both reproduce on every sandboxed hook run. Both sites verified directly in the source, not inferred from the report.**

These are grouped because they are one family: **a message asserting a state the code is not in.** Neither changes a decision; both erode the signal value of warnings, which is the only channel a silent hook has.

## 1 — `governed_tools` is warned about on the DEFAULT configuration

Every `run_hook` prints:

```
Tool "Bash" appears in permissions but is not in governed_tools list
```

**Cause, confirmed at both sites:**

- `config.py:1689-1692` seeds the merged view with `"governed_tools": []`.
- `config_validation.py:59` then does `config.get("governed_tools", ["Bash"])`.

The key is **always present**, so the `["Bash"]` fallback is **dead code** and `governed_tools` is `[]` whenever the user did not set it explicitly. Every tool named in `permissions` therefore trips the warning.

**Decisions are unaffected** — `Configuration.governed_tools()` correctly returns `DEFAULT_GOVERNED_TOOLS` — so this is purely a false alarm, on the most common config shape there is.

**Worth checking against the punch-list**: item *"governed_tools default change"* touched exactly this default. If the seeded `[]` predates it, this is long-standing; if not, it is a regression from that change. The `[]` seed and the `["Bash"]` fallback disagree about what "unset" means, which is the actual defect — **one of them should go**.

## 2 — "Logging disabled" is printed while logging is working

Every `run_hook` child prints:

```
Warning: Logging directory does not exist: <sandbox>/project/logs. Logging disabled.
```

and then **logs correctly** into `TOOLGUARD_LOG_DIR` — `Sandbox.trace()` returns 20 lines.

The check looks at one path and the write goes to another, so the message asserts a consequence that does not follow. This is ticket 31's "fifth isolation anchor" surfacing from the inside, with a wrong message attached.

## Why these are worth one ticket rather than none

A permission hook that has no UI communicates through exactly two channels: the decision, and warnings on stderr. **Both of these warnings are false on ordinary runs**, which trains the reader to skip them — and the same stream carries `Warning: Failed to write to log file`, which ticket 23 established is *the only trace a dropped log entry leaves anywhere*.

The cost is not the two messages. It is that the channel they share stops being read.

## A third, smaller one from the same measurement

`sandbox._is_benign_write` matches `"__pycache__"` as a **substring anywhere in the path**, so `~/.claude/__pycache__evil.toml` passes the tripwire. Test-infrastructure only, and the tripwire is not a security boundary — recorded so it is not rediscovered.
