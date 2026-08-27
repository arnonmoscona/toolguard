---
title: With HOME unset the hook crashes in get_env_config and denies every tool call
tags:
- TOO-45
- proposed-ticket
- robustness
permalink: toolguard/too-45/proposed-tickets/86-no-home-makes-the-hook-deny-everything
---

# `HOME` unset -> every tool call is denied with a cryptic RuntimeError

**Observed in production, not constructed.** A crash report was written by the *live* hook at 2026-08-20 11:20:00 while a subagent was running tests with `HOME` unset — the agent's environment leaked into the real hook governing its commands.

```
RuntimeError: Could not determine home directory.
  hook.py:1252 in main  ->  get_env_config()
  env_config.py:185     ->  log_dir = expanduser(log_dir_str)
  path_utils.py:49      ->  expanded.expanduser()
  pathlib/__init__.py:1249 raise RuntimeError("Could not determine home directory.")
```

## Severity: LOW, and the reason is worth stating

**It fails closed.** `main`'s catch-all emits `RuntimeVerdict(decision="deny", ...)` on stdout and exits 0, so nothing is wrongly permitted. That is the correct direction for a permission tool and the design working as intended.

What is wrong is everything else about it:

- **Every governed tool call is denied**, so Claude Code is fully blocked rather than degraded.
- The user-facing reason is `Unexpected error in hook: Could not determine home directory` — a Python exception string standing in for the one-line diagnosis, *"toolguard needs `HOME` to be set."*
- It is logged as an **unexpected** exception and writes a crash report per invocation, so a misconfigured environment produces one crash file per tool call. The 1,950 files in `~/.toolguard/errors/` are partly this class.

## Where it happens matters

`get_env_config()` is the **first** thing in `main`'s try block — before the hook input is parsed, before configuration is loaded. So this is not a matching or rule defect at all; it is startup refusing to start. Any environment without `HOME` is affected: some CI runners, minimal containers, and anything invoked through `env -i`.

## Scope

1. **Decide whether `HOME`-less operation should work at all, or be refused cleanly.** Refusing cleanly is defensible — toolguard's config discovery, log directory and rule hierarchy are all home-anchored — but it should be a *deliberate* refusal with a clear message, not a `RuntimeError` escaping `pathlib`.
2. **`path_utils.expanduser` is not non-throwing**, and at least one caller assumes it is. Audit the other call sites for the same assumption; this is the same "a mechanism throws where its caller expects a value" shape found repeatedly in this campaign.
3. If a clean refusal is chosen, the deny reason should name the variable and the fix, and it should not be classified as an *unexpected* exception — an anticipated misconfiguration writing a crash report per tool call is noise that will bury real crashes.

## Note on the errors-directory baseline

`~/.toolguard/errors/` is used in this campaign as a **test-isolation leak detector** — a count that grows across a suite run means a seam broke. This crash moved the count from 1,949 to **1,950 for a legitimate reason**, and briefs quoting 1,949 are stale. The detector behaved correctly; it flagged a real defect, just not the class it was watching for.
