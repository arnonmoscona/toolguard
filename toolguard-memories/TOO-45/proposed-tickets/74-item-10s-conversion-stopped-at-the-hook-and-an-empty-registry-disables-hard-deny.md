---
title: Item 10's conversion stopped at the hook's command branch, and an empty registry
  silently disables the hook including hard-deny
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/74-item-10s-conversion-stopped-at-the-hook
---

# The table that decides what a tool IS

**Found 2026-08-14. One RED test in the tree. Two production findings, consolidated — one owner, one table.**

Punch-list item **#10, "a supported tool becomes a described thing"**, replaced scattered tool literals with `tool_spec`'s registry. These are the two places the conversion did not reach.

## 1 — The hook hardcodes `"command"`; only the file-path branch consults the registry

`hook._resolve_event` and `_handle_command_tool` read the target from a literal `"command"` key and call `payload_key()` **only on the file-path branch**. Meanwhile `transcript_harvest` and `test.verdict_corpus.fixture_loader` honour the registry for command tools.

**So the contract exists, two consumers follow it, and the hook does not.** A command tool registered with any other `payload_key` is read from the wrong field by the component that actually governs.

Measured consequence in the tests: **`payload_key` hardcoded to return `"command"` survived the whole module** at the behaviour tier, because nothing drove the hook through a registered key.

RED test: `test_the_hook_reads_a_command_tools_target_from_the_registered_key`. Same family as follow-up-queue rows 18 and LH1.

## 2 — An empty registry silently disables the hook, hard-deny included

With `_REGISTRY = ()`, `governed_tools()` returns empty and `_resolve_event` **allows every tool — including a hard-denied `rm -rf`.**

Nothing reports "governed nothing". This is ticket 29's family (twelve confirmed instances) in the most consequential place available, and it compounds ticket 65, where `config.hard_deny(tool)` could stop applying to MCP terminals with 0 of 27 tests failing.

**And the test that should have caught it was vacuous**: `for spec in _REGISTRY: assertTrue(spec.payload_key)` passes trivially on an empty table — shape 22. Now pinned by explicit population counts plus an end-to-end test that drives the empty case and shows the hard-deny bypass.

## The related drift surface, measured rather than grepped

An **identity scan over `sys.modules`** — not a grep — found how widely these values are aliased:

| value | holders (scan 1) | holders (scan 2) |
|---|---|---|
| `FILE_KIND_TOOLS` | 10 | **14** |
| `BUILTIN_TOOLS` | 6 | **8** |
| `KNOWN_TOOL_NAMES` | 3 | **6** |
| `LogEntry` | — | **17** |
| `TOOLS_BY_NAME` | 5 | 4 |
| `payload_key` | also aliased as `hook._tool_payload_key` | |

**The two scans disagree, and the reason is the useful part: an identity scan over `sys.modules` sees only what has already been IMPORTED, so every count is a LOWER BOUND.** Two agents scanned the same constants hours apart and differed purely by which consumers were loaded. Import the consumers you care about first, then scan. Recorded in the plan's tier note.

`hook.FILE_PATH_TOOLS` / `hook.FILE_TOOLS` / `api.FILE_TOOLS` are **three names for one object** — ticket 65's drift warning, now pinned by `assertIs`. The `MappingProxyType` suggestion at queue row 19 remains open and is the obvious answer for `TOOLS_BY_NAME`.

`hook.FILE_PATH_TOOLS` / `hook.FILE_TOOLS` / `api.FILE_TOOLS` are **three names for one object** — ticket 65's drift warning, now pinned by `assertIs`. The `MappingProxyType` suggestion at queue row 19 remains open and is the obvious answer for `TOOLS_BY_NAME`.

## 3 — The registry's guarantee for `Bash` is currently vacuous

**Added 2026-08-14 from `test_tools_transcript_harvest.py`.** `_command_for_tool` falls back to a literal `"command"` when the registry lookup fails — and `Bash`'s declared `payload_key` **is** `"command"`. Proven by an equivalent mutant: **deleting Bash's entire registry entry is unobservable.**

So every "we consult the registry" guarantee is, for the tool that matters most, indistinguishable from not consulting it. The fallback is defensible; what it costs is the ability to detect a corrupted or missing `ToolSpec` for `Bash`.

## 4 — The harvester's gate is `BUILTIN_TOOLS`, not the registry — and it drops a governable tool

`harvest_transcript_file` gates on `BUILTIN_TOOLS` while `_command_for_tool` resolves through `TOOLS_BY_NAME`. Consequence, measured with two now-separated tests:

- an **unregistered** tool (`mcp__basic-memory__search`) is dropped — correct;
- a **registered, non-builtin, `ToolKind.COMMAND`, `payload_key="command"`** tool (`mcp__jetbrains__execute_terminal_command`) is **also dropped**, because the gate asks the wrong question.

The prior test could not tell those apart, and its Given called builtin-membership "governance". **This one needs Arnon's decision, not a fix** — see `DECISIONS-PENDING.md` A12; the fix's blast radius reaches `replay`, `redundancy` and `consolidate`. Pinned green with a test asserting all four discriminating facts, so it fires the moment the gate changes.

## 5 — A THIRD divergence from the registry: the sort priority table

**Added 2026-08-14 from `test_tools_sorters.py`.** `rule_sort.get_tool_priority` hardcodes `{"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}`, while `tool_spec.TOOLS_BY_NAME` declares **five** tools. The fifth is **`mcp__jetbrains__execute_terminal_command`** — the same tool that finding 4 shows being dropped from the transcript harvest — and it silently buckets into rank 4 **alongside genuinely unknown tools**.

Two hand-maintained lists edited independently, and dispatch literals that per `CLAUDE.md` belong in constants. Cosmetic today, since the sort only orders a written config file — but it is the third place item #10's single description of a tool has not actually become single, and **all three findings name the same MCP tool**.

## Two behaviours pinned as characterizations, not endorsed

- **`governed_tools = []` is silently treated as *unset*** and falls back to the default four.
- An empty governed set bypasses `hard_deny`.

Both are labelled as characterizations in their docstrings so phase 2 can decide them deliberately.

## The test module: 16 -> 35 tests

**At HEAD, 10 of 19 mutants produced zero failures, and 9 more were caught only by literal-set pins** — the module noticed a constant had changed and nothing checked the consequence. Repaired: **18 of 19 detected behaviourally**, 19 of 19 by the full module.

The sharpest survivor: **`Read.is_builtin: True -> False`** removes `Read` from `BUILTIN_TOOLS` and `DEFAULT_GOVERNED_TOOLS` while leaving it fully described — **zero failures at HEAD.** Nothing in the module ever checked that `Read` is *governed*, only that it is *listed*.

**Three cannot-fail tests**, all confirmed by execution: `assertEqual(x, x)` on a bare alias (never failed under any of 19 mutants at any tier — queue row TX1 confirmed), the `TOOLS_BY_NAME` count test, and the vacuous-on-empty loop above.

## A METHOD REFINEMENT that corrects this campaign's own tier guidance

The recipe said tier A = "mutate the production value only". **That is not a realistic state**: a real edit is re-imported everywhere, so leaving the *test module's* by-value imports bound to the original makes `assertIs` mirror tests fire **spuriously** — a false detection, in the opposite direction from the usual failure.

**Rebind every holder, including the test module's, and then measure behaviour.** Find holders by identity scan over `sys.modules`, not by grep. Recorded in `TOO-45 test-repair plan.md`.

**Anchored on behaviour**: a deliberately equivalent reimplementation — every `ToolSpec` rebuilt as a new object, all five derived views rebuilt through different expressions — leaves both modules fully green.
