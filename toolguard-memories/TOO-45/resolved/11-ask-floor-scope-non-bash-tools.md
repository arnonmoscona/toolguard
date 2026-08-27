---
title: 11-ask-floor-scope-non-bash-tools
type: note
permalink: toolguard/too-45/proposed-tickets/11-ask-floor-scope-non-bash-tools
---

**PARTIALLY FIXED in `05f786d`.** Measured and found benign — the ASK floor already applies to Bash and MCP terminal alike, by construction (`toolguard/api.py:68-72`), pinned by `test/unit/test_ask_resolution.py:390`; still open: one doc sentence at `docs/configuration.md:507` still claims Bash-only.

> **ANSWERED BY MEASUREMENT 2026-08-12, test-repair campaign. The open question was "is the inline/heredoc foreign-code ASK floor Bash-only?" It is NOT. There is no enforcement gap — this is a documentation bug.**
>
> Executed under a blanket `Bash(*)` allow:
>
> - `python -c "import os"` → **`ask`**, reason `ASK floor applied (inline/heredoc foreign code): ...` — for `Bash` **and** for `mcp__jetbrains__execute_terminal_command`
> - `ls -la` → `allow` for both
>
> **Structural reason:** `api._decide_bash` routes every non-file tool through `resolve_bash_permission_detailed`, so the floor is shared by construction rather than by a per-tool decision.
>
> **What is actually wrong is `docs/configuration.md`**, which describes it as *"the Bash-only inline/heredoc-foreign-code floor"*. That wording should be corrected; the code needs no change.
>
> Now pinned by `test_ask_resolution.test_inline_foreign_code_is_floored_for_bash_and_for_an_mcp_terminal`, which fails under `inline_floor_disabled`. **The mechanism previously had zero detection.**
>
> Note for anyone reading this ticket alongside the campaign notes: the coordinator briefly conflated this floor with the TOO-19 **parse-failure** floor. They are different mechanisms that share the name "ask floor".

# Proposed: settle whether the ASK floor covers non-Bash command tools

**Status:** deferred from TOO-45. **Security-relevant. Settle by measurement, not by reading.**

## The question

Toolguard applies an ASK floor to inline code and heredoc payloads fed to recognised interpreters. `docs/configuration.md` calls it "the Bash-only inline/heredoc-foreign-code floor".

But `mcp__jetbrains__execute_terminal_command` and custom MCP command tools are documented as **command tools that share the `Bash(...)` pattern namespace** and, by implication, the same compound decomposition. `hook.py:54` lists all three in `COMMAND_TOOLS`.

**If `python -c "..."` issued through the JetBrains terminal is not floored, that is an enforcement gap, not a documentation gap.** No page states the answer either way.

## Why it matters here specifically

This project's own governance depends on the floor. The intent-disclosure rules treat inline foreign code as requiring an ASK, and the floor is described as overriding allow rules by design. A command tool that routes around it defeats that.

Found by a blind reader who could not determine current behaviour from the documentation — which is itself the finding: if a careful reader cannot tell, neither can a user configuring the tool.

## Proposed

**One measurement first, before any code changes.** Feed the same inline-code payload through `Bash` and through `mcp__jetbrains__execute_terminal_command` under an identical broad-allow config, and compare verdicts. `toolguard.testing.sandbox` exists for exactly this and needs no live IDE.

Three possible outcomes:

- **Floored for both** — documentation bug only; fix the wording.
- **Not floored for the MCP tool** — real enforcement gap; fix the code, then document.
- **Depends on configuration** — worst case, needs a stated policy.

## Size

Measurement: under an hour. The fix depends entirely on what it says, so estimating further would be guessing.

## Decision needed

None until the measurement is run. **Recommend running it before push regardless of what else is deferred** — it is cheap, and it is the only open item with a plausible security consequence.