---
title: The file-path handler inlines the allowed-logging the command handler already factored out
tags:
- TOO-45
- proposed-ticket
- maintainability
permalink: toolguard/too-45/proposed-tickets/96-file-path-handler-inlines-what-the-command-handler-factored-out
---

# `_handle_file_path_tool` inlines `_log_allowed_command`

**Measured 2026-08-21** during TOO-45's wrap-up, from pyscn's clone report — but **not** the thing the clone report said.

## What the tool reported, and why it was wrong

pyscn flagged `hook.py:1067` and `hook.py:1149` as an **80-line group at 0.98 similarity** — the highest-confidence clone in the package.

**Stripping the docstrings, the code is not 98% similar.** The two handlers genuinely differ: different payload-key accessor, different resolver (`resolve_file_path_permission_detailed` versus `resolve_bash_permission_detailed` plus the hard-deny pool), and different conflict-logging shape (a file-path result carries 0 or 1 overrides; a compound carries one per sub-command).

**The similarity is mostly the docstrings**, which are long, parallel, and part of the AST that APTED compares. This is the third time in this campaign that printing a metric's members changed its conclusion.

## The real duplication, which is smaller and genuine

The **allowed** branch:

- `_handle_command_tool` calls **`_log_allowed_command(result, command, agent_info, env_config, permission_mode)`**
- `_handle_file_path_tool` **inlines the same thing** — an 11-line `log_command(LogRecord(...))` block building status, matched rule, provenance, extra info, permission mode and additional context by hand.

Code-line counts confirm it: **55 lines versus 44**, and the 11-line gap is exactly that block.

## Why it matters

`_log_allowed_command` exists because this is a shape worth having once. The file-path path predates it or was never migrated, so **a change to what an allowed decision records has to be made twice**, and the second site does not look like a caller of the first.

**This campaign has now paid four times for one concept with several hand-written copies** — `_pick_strictest`, `all_parts`, `_corpus_verdict`, and the third `_atomic_write`. This is a fifth instance, sitting on the permission-decision path.

## Fix

Have `_handle_file_path_tool` call `_log_allowed_command`, passing its `log_target` (`f"{tool_name}({file_path})"`) where the command handler passes `command`.

**Check first that the helper records nothing command-specific.** If it does, the right fix is to widen it deliberately rather than to inline a second copy — and that widening is the ticket, not a detail of it.

## Not urgent

It is on the permission path, it is well covered, and the duplication is a maintenance cost rather than a defect: both copies currently agree. **Do it when something needs to change about what an allowed decision logs** — that is when the cost of two copies is actually paid, and when the correct shape will be obvious.
