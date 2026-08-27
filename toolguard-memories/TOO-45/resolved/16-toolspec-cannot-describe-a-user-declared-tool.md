---
title: 16-toolspec-cannot-describe-a-user-declared-tool
type: note
permalink: toolguard/too-45/proposed-tickets/16-toolspec-cannot-describe-a-user-declared-tool
---

**PARTIALLY FIXED in `05f786d`.** Documented at `docs/configuration.md:186-212`; still open: the code residual at `toolguard/hook.py:1130`, now tracked separately as TOO-51.

# `ToolSpec` describes built-ins only, so governing any other tool silently denies it

**PROMOTED TO `TOO-51`** (Arnon, 2026-08-09), for future consideration after RC1. **The ticket is the live copy; this file is the working note it was drafted from.** Do not edit this one expecting it to matter — change `TOO-51`.

**Status:** found by Arnon at the manual review of punch-list #10, 2026-08-09. Confirmed empirically. **#10 made this look solved without solving it**, which is the part that matters.

Two things worth tidying in `TOO-51` itself whenever it is next opened, both my doing: its summary is the draft filename rather than a title, and it still carries a trailing *"original notes, superseded"* section that the adapter framing above replaced. Neither affects the content.

**One residual left in the code deliberately**, recorded so it is not mistaken for an oversight: punch-list #10's review flagged half-converted dispatch — reading the payload key from the registry on one branch and hardcoding it on the other — as *worse than no conversion, because it looks finished*. That was fixed in `fixture_loader.py` and `transcript_harvest.py` and **left in `hook.py` itself**, which is where the pattern originates. It is not a one-line fix: the else branch would need a default for tools absent from the registry, which is the adapter question in miniature. Nothing observable changes for any registered tool today.

## Measured, not argued

A throwaway project governing `WebFetch` and a custom MCP tool, with an allow rule written for each, run against the real hook:

```
Bash                  -> allow   Command matches allow pattern: ls*
WebFetch              -> deny    No command provided in tool input
mcp__acme__fetch_doc  -> deny    No command provided in tool input
```

**Governing such a tool does not restrict it — it bricks it.** Every call is denied, the message names a payload key the tool never had, and the user's `WebFetch(https://example.com/*)` allow rule is never evaluated.

## Why

`hook.py:731`:

```python
if tool_name in FILE_PATH_TOOLS:
    key = _tool_payload_key(tool_name)     # registry lookup
    target = tool_input.get(key, "")
else:
    target = tool_input.get("command", "") # hardcoded
    if not target:
        return deny("No command provided in tool input")
```

**The registry is authoritative on the file branch and ignored on every other.** Punch-list #10 converted the file-path reads and left the command read as a literal — the same half-converted dispatch its own review flagged in two other files, present in the hook itself and missed by everyone.

`mcp__jetbrains__execute_terminal_command` works only because its payload happens to use the key `command`.

## The deeper gap Arnon identified

> An MCP tool can be a command tool, a file tool, or something else entirely (like a URL prefix). So there is some partial abstraction there that does not seem fully formed, fully explained, and perhaps not fully thought through.

Two distinct problems:

**1. `additional_supported_tools` and `ToolSpec` describe different things.** `ToolSpec` carries name, kind, payload key, is-builtin. `additional_supported_tools` carries **a name and nothing else**, and its only effect is to silence a config-validation warning (`config_validation.py:90`). It does not make a tool governed, and it gives the dispatch nothing. So a user who wants to govern a custom tool must add it in two places and it still only works if the payload key is literally `command`. The module docstring says `additional_supported_tools` is out of the registry's scope, which is accurate and is exactly the problem: the two halves of "what tools exist" do not meet.

**2. `kind` conflates two different facts.** Today it answers *where is the subject in the payload*. It is also being used to decide *how to match the subject* — bash parsing for command-kind, glob for file-kind. A URL-subject tool needs a third matcher, and neither field can say so. That conflation is why `WebFetch` is inexpressible rather than merely unregistered.

## A registered, shipped tool already breaks the model — measured 2026-08-09

The `WebFetch` case above is hypothetical. This one is not: it is `mcp__jetbrains__execute_terminal_command`, which is in `KNOWN_SUPPORTED_TOOLS` and has a `ToolSpec` entry today.

Its live MCP schema confirms `command` is the required parameter, so the registry's payload key is **right**. But the schema carries five more parameters the registry cannot express, and one of them changes the meaning of `command` completely:

```
executeInShell omitted (defaults to false)      -> exit 1
  "error: unexpected argument '&&' found"          the string is argv to ONE process
executeInShell: true                            -> exit 0
  "/home/arnon/projects/toolguard\n...ok"          real shell, compound works
```

**toolguard parses that string with the PEG bash grammar and splits compounds. That model is correct only when `executeInShell` is true, and toolguard never sees the flag.**

The dangerous direction is under-enforcement, not over-: the parser deliberately discards comments, so `some-command # rest` is evaluated as `some-command`. In process mode `#` and everything after it are ordinary argv elements that really do reach the program. toolguard would then evaluate strictly less than what runs.

**This has never bitten because the tool is not actually governed in the current setup** — two live invocations produced no log entry at all. So a registry entry, a `KNOWN_SUPPORTED_TOOLS` membership, and a documented payload key have all been carrying an untested assumption about execution semantics.

**Which sharpens the design point:** `kind` does not merely conflate "where the subject lives" with "how it is matched". It also silently assumes **what the subject means** — that a `command` string is a shell command. For this tool that is true only conditionally, and the condition is a sibling field in the same payload.

## DECISION (Arnon, 2026-08-09): deferred until after RC1

> As for the terminal command — I think we can defer this, just documenting it as a currently known limitation. Probably requiring an adapter, and some kind of additional tool configuration for things like this and like WebFetch. I won't worry about this till after RC1.

So this ticket is **not scheduled**. Two things follow from that:

1. **The limitation gets documented now**, in user-facing docs, as a known limitation — governing a tool whose subject is not a shell-command string does not work, and governing the JetBrains terminal tool models it as a shell even when it is not one. Cheap, honest, and it stops a user discovering it by having a tool silently bricked.
2. **The design below is the shape, recorded so it is not re-derived.** It is not a work order.

## Shape of the fix — an adapter per tool, declarable in config

The recurring mistake in every version of this so far is treating a tool as **a name plus a payload key**. Three measured cases say that is not enough:

| tool | what breaks |
|---|---|
| `WebFetch` | subject is a URL. There is no shell command to parse and no path to glob; the matcher itself is wrong, not just the key. |
| `mcp__jetbrains__execute_terminal_command` | subject *is* a command string, but whether it is a **shell** command depends on `executeInShell`, a sibling field. One payload key, two languages. |
| any user MCP tool | has no entry at all, so it inherits "command", is parsed as bash, and is denied when the key is absent. |

What a tool actually needs to be governable is an **adapter**: given a tool payload, produce the governed subject *and* say how to match it. Concretely that is at least

- **where the subject lives** — today's payload key, possibly conditional on other fields;
- **what the subject is** — shell command, argv, filesystem path, URL, opaque string;
- **how to match it** — the PEG bash parser and compound splitting, glob matching, URL/prefix matching, or exact match;
- **what to do when the payload does not fit** — which must be a loud config-time error, never a runtime deny with a misleading reason.

The third bullet is the one that makes this an adapter rather than a wider dataclass: **matching is behaviour, not data.** A URL matcher and the compound-command splitter have nothing in common but their signature.

**And it must be declarable in configuration**, because the interesting cases are user-installed MCP servers that toolguard has never heard of. `additional_supported_tools` is the natural place — extended from a list of names to a list of specs, with the bare-name form kept as shorthand for "shell command under `command`".

**Sequencing note:** the `executeInShell` case is the cheapest possible proof that the adapter needs to be conditional on the payload, not just keyed by tool name. Worth keeping as the worked example when this is picked up.

## Shape of the fix (original notes, superseded by the adapter framing above)

- **A user-declared tool must be able to carry a full spec** — name, kind, payload key — not a bare name. Keep the bare-name form as shorthand for the common case, but stop making it the only form.
- **Separate "where the subject lives" from "how the subject is matched."** They are independent, and only splitting them makes a URL-subject tool expressible.
- **The dispatch must read the payload key from the registry on every branch**, not just the file one.
- **An unknown or unmatched kind must fail loudly at config load**, not silently deny at runtime. Today the failure surfaces as a per-call deny with a misleading reason, which is the worst available option in a permission tool.
- Documentation must explain the relationship, because the current split is not discoverable from either half.

## Note on scope

This is a design item, not a patch. The dispatch one-liner could be fixed immediately and would turn "bricked" into "correctly matched, if the key is right" for tools whose subject is a plain string. The matcher question is the real work.

Whether the immediate fix should ship ahead of the design is Arnon's call.
