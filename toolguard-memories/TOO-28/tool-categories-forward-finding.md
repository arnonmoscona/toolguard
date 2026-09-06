---
title: Tool categories - a missing concept, surfaced by TOO-28
type: note
tags:
- task-memory
- TOO-28
- TOO-53
- TOO-51
- TOO-23
- design
permalink: toolguard/too-28/tool-categories-forward-finding
---

# Tool categories: a concept toolguard does not have, surfaced by TOO-28 Phase 1

**Not work for TOO-28.** Arnon, 2026-09-05: *"That will come into play when we deal with TOO-53 and TOO-51 - at that point we'll probably have to establish a 'Bash-like' thing and other broader tool categories like that. This can also apply when we implement TOO-23. But we don't have to deal with any of that right now."* Recorded so it is not re-derived.

## What surfaced it

Threading `Invocation` into the resolver exposed that `resolve_bash_permission_detailed` cannot simply use `invocation.tool_name`. The Bash cascade **always** resolves against the literal `"Bash"` permission pool, even when the invoking tool was an MCP terminal tool with its own name. Round 3 handled it with a per-call `dataclasses.replace(invocation, tool_name="Bash")`, and `api._decide_bash` restores the caller's real tool name onto the returned verdict afterwards.

That works, and it is the right local fix. But **it is a workaround for an absent concept**: there is no way to say "these several concrete tools are governed by one rule set". The knowledge lives as a hardcoded `"Bash"` in one function plus a name-restoration step in another.

## Why it matters beyond this ticket

**TOO-23 is proposing the same thing from the reading side.** Its `ClaudeReaders` pseudo-tool — one name covering `Read`, `Grep`, `Glob` and whatever else reads — is a tool category. So is "Bash-like" (Bash plus MCP terminal tools). They are two instances of one mechanism:

> a named category, a set of concrete tools that map into it, and a rule set resolved against the category rather than the tool.

**If TOO-23 ships `ClaudeReaders` as a special case, the mechanism gets invented twice** — once for readers, once again for Bash-like when TOO-53/TOO-51 need it — and the second one will not be able to reuse the first. Worth deciding the general shape when the first of them is built, even if only one category ships initially.

## What a future ticket should check

- The current Bash-like mapping is implicit: `constants.FILE_TOOLS` separates file-path tools, and everything else routes to the Bash cascade by *default*, not by declaration. A category mechanism makes that a declaration, which is the difference between a checkable intent and a convention (the `--layers` completeness argument, applied to tools).
- `api._decide_bash` restoring the real tool name onto the verdict is the visible seam. If a category concept existed, the verdict would carry both the category it resolved under and the tool that invoked it, and nothing would need restoring.
- Whether a category should be user-declarable or built in. TOO-23's evidence principle applies: build it for the categories there is evidence of needing, not for a general extension mechanism nobody has asked for.