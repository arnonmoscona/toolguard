---
title: 74-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/74-estimate-predictions
---

# TOO-45 Item 74 — blinded touch-set prediction

## Reasoning

The ticket reports two production findings, presented by its own title as one fix: (1)
`hook._resolve_event` / `hook._handle_command_tool` read a command tool's target from a literal
`"command"` key instead of calling `payload_key()` on the tool_spec registry, while the
file-path branch and two other consumers (`transcript_harvest`, `test.verdict_corpus.fixture_loader`)
already honour it; (2) an empty registry makes `governed_tools()` return empty, and the hook's
current logic apparently treats "not in governed set" as "allow", which also lets a hard-denied
command through. Both findings are located, by the ticket's own wording, inside the hook's
resolution path — `_resolve_event` is named directly in both.

I decomposed the predicted change into cost centres:

1. **The key-read bug.** Fixing this means making the command branch call the same
   `payload_key()`-based lookup the file-path branch already uses. This is a small, local change
   inside `hook.py` — most plausibly collapsing the two branches onto one shared lookup rather
   than adding a second special case.
2. **The empty-registry / hard-deny bypass.** The ticket frames this as "nothing reports
   'governed nothing'" and stresses that hard-deny must survive an empty or misconfigured
   governed set. The natural fix is a control-flow change in the same resolution function: check
   hard-deny (or otherwise fail closed) independently of governed-set membership, rather than
   short-circuiting to allow when the tool isn't found in an empty governed set. This is still
   `hook.py`-local unless hard-deny evaluation itself is know to live in `permission_resolution.py`
   or be invoked via `config.py` — I can't confirm that boundary without reading source, so I
   carry it as a lower-confidence secondary possibility rather than a primary target.
3. **The registry itself (`tool_spec.py`).** `_REGISTRY` and `governed_tools()` look, by naming
   convention and by the module's declared role ("static registry of the tools toolguard knows
   how to govern"), like they live in `tool_spec.py`. If the fix adds any validation/guard at the
   registry boundary (e.g. treating an empty registry as a startup-time error rather than a silent
   empty set), that lands here. I rate this medium confidence — the alternative is that the guard
   is purely a hook-side "don't trust an empty governed set" check, needing no registry change.
4. **Tests.** This campaign's established pattern (visible in the ticket's own text — RED test
   already named, "characterizations pinned... not endorsed", heavy mutant-driven test repair
   elsewhere in the item-10 family) makes me expect the test delta to be the largest single mass
   of changed lines, concentrated in `test/unit/test_hook.py` (the RED test's declared home) and
   plausibly `test/unit/test_hard_deny.py` (the hard-deny-bypass characterization belongs to that
   module's declared scope: "pooling, carve-outs, and enforcement").
5. **Collateral / wide-scope risk.** The ticket explicitly separates out three further findings
   (#3 Bash's vacuous fallback, #4 the harvester's `BUILTIN_TOOLS` gate, #5 `rule_sort`'s hardcoded
   priority table) and just as explicitly declines to fix two of them now ("needs Arnon's decision,
   not a fix" for #4; "cosmetic today" for #5; #3 is called "defensible" as-is). That reads as a
   deliberate scope fence around this ticket, so I weight against `transcript_harvest.py`,
   `rule_sort.py`, and `tools/sorters.py` being touched by *this* fix, even though they are named
   in the same document.

## Production — modified

| file | reason | confidence |
|---|---|---|
| `toolguard/hook.py` | Both named findings live in `_resolve_event`/`_handle_command_tool`: route the command branch through `payload_key()`, and stop treating an empty/non-membership governed-set result as blanket allow (hard-deny must still apply). | high |
| `toolguard/tool_spec.py` | Registry/`governed_tools()` may gain a guard or validation for the empty-registry case, if the fix is placed at the registry boundary rather than purely at the call site. | medium |
| `toolguard/error_reporter.py` | Ticket says "nothing reports 'governed nothing'" — if the fix adds a reported warning/notice rather than only a code guard, the call site is new but the reporter's public surface may need a new severity/message hook. | low |
| `toolguard/permission_resolution.py` | Only if hard-deny evaluation is centralized there and the hook currently bypasses calling into it for out-of-registry tools; can't confirm the boundary without reading source. | low |
| `toolguard/config.py` | Only if the fix touches how `governed_tools` config values interact with the registry default (ticket separately characterizes `governed_tools = []` falling back to a default four) — but that's flagged as an already-pinned characterization, not this ticket's fix target. | low |

## Production — added

none expected

## Test — modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_hook.py` | Declared home of the named RED test (`test_the_hook_reads_a_command_tools_target_from_the_registered_key`); largest expected test mass, including the empty-registry/hard-deny-bypass end-to-end test the ticket describes as already written. | high |
| `test/unit/test_hard_deny.py` | Its declared scope ("pooling, carve-outs, and enforcement") is the natural home for a characterization/regression test asserting hard-deny survives an empty governed set. | medium |
| `test/unit/test_tool_spec.py` | Only if `tool_spec.py` itself gains a guard/validation that needs direct unit coverage separate from the hook-level behavioural test. | low |

## Test — added

none expected — the ticket already names an existing RED test and describes the empty-registry case as already pinned, so I expect modification of existing modules rather than a new test file.

## Deleted

none expected

## Concentration set

`toolguard/hook.py` and `test/unit/test_hook.py` are expected to hold the large majority of
changed lines. The production fix itself should be small (a handful of lines reshaping two
functions); the bulk of the diff is more likely to be test code exercising the previously-blind
hard-deny-bypass path and the registered-key lookup.

## Scope prediction (scored separately)

**Predicted shape: NARROW.**

The ticket's own text draws a scope fence around this specific fix: findings #3, #4, and #5 (the
Bash-fallback vacuity, the harvester's `BUILTIN_TOOLS` gate, and `rule_sort`'s hardcoded priority
table) are each explicitly called out as *not* this ticket's fix — #4 says outright "this needs
Arnon's decision, not a fix," #5 is labelled "cosmetic today," and #3's fallback is called
"defensible." The title and the two numbered findings under it are the only material framed as
something to fix now. `transcript_harvest.py` and `test.verdict_corpus.fixture_loader` are named
specifically as consumers that *already* honour the contract — i.e., as the standard the hook
should be brought up to, not as files needing their own change.

Predicted touch set for the narrow shape (repeating the tables above, condensed):

- `toolguard/hook.py` (primary, high confidence)
- `toolguard/tool_spec.py` (possible registry-side guard, medium confidence)
- `test/unit/test_hook.py` (primary test mass, high confidence)
- `test/unit/test_hard_deny.py` (secondary test mass, medium confidence)

If the shape turns out to be **wide** instead (an enforced "every consumer reads through the
registry" invariant, e.g. a new architecture-fitness rule), I'd expect it to additionally reach:
`test/unit/test_architecture.py` and/or `tools/architecture_fitness.py` (a new structural check),
plus touches to `toolguard/tools/transcript_harvest.py` and `toolguard/rule_sort.py` even though
the ticket currently describes both as either compliant or explicitly deferred. I consider this
shape less likely given how pointedly the ticket fences off findings #3-#5, but it is the
higher-cost alternative if the campaign decided to close the whole drift-surface in one pass
rather than filing it as a follow-up.