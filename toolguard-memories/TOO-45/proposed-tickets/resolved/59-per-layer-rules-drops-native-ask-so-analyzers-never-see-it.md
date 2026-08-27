---
title: per_layer_rules drops every native ask rule, so no analyzer ever sees one
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/59-per-layer-rules-drops-native-ask-so-analyzers-never-see-it
---

**FIXED in `05f786d` (TOO-45 phase 2).** `per_layer_rules` no longer drops native `ask` entries, so analyzers see them, including the provenance-collapse hazard — see `toolguard/tools/config_access.py:118-123`.

# The analyzers' shared view discards native `ask`

**Found 2026-08-13. A RED test is in the tree. This is queue row CA1, now executed — and the test that should have caught it carried a FALSE premise in its own docstring.**

## The defect

`config_access.per_layer_rules` has a `not layer.is_native` guard that **drops native `permissions.ask` entirely.**

Measured:

- `Configuration.permission_layers("Bash")` → the native layer has `ask=('git push:*',)`
- `per_layer_rules` → `()`

`per_layer_rules` is the **shared input to every analyzer** — danger, redundancy, consolidation, clarity. So **no analyzer can see a native ask rule.** A user's `settings.json` ask rules are invisible to every safety check toolguard offers.

**Phase-2 fix**: delete the guard. `LayerRules.ask` and `per_layer_rules`' docstrings need updating in the same change, since they currently describe the wrong behaviour.

### Confirmed downstream at the analyzer, with the loss isolated to `ask`

A second RED test now exists in `test_tools_clarity.py` — `test_native_ask_overlapping_a_native_allow_is_flagged` — and it makes the strictly stronger statement:

- **Mutating toward the fix** (deleting the `not layer.is_native` guard) turns it green **with no other change anywhere.**
- Its sibling `test_native_deny_overlapping_a_native_allow_is_flagged` **passes**, which proves the fixture reaches the analyzer and **isolates the loss to `ask` specifically** rather than to native layers generally.

So the defect is confirmed from both ends: the view drops it, and the analyzer downstream returns `[]` because of it.

### The same module also could not tell WHICH tool it was examining

Hardcoding `"Bash"` inside `find_confusing_interactions` was **undetected** — all 11 pre-existing tests used Bash. That is ticket 56's family at the analyzer level rather than the aggregator level, and it is now pinned with a two-tool layer.

## The test that should have caught it asserted the opposite, on a false premise

`test_per_layer_rules_native_layer_has_no_ask` carried the Given *"native settings have no ask concept."*

**That is false.** Claude Code's `settings.json` has an `ask` list, `permission_layers` extracts it, and the resolver decides on it. The test encoded a misunderstanding as a specification and then verified it.

It also **could not have failed anyway**, for **two independent reasons**, and the working queue recorded only one:

1. the fixture wrote no `ask` key at all, and
2. the assertion sat inside `for lr in native_layers:` with **no population check** — a zero-iteration loop (shapes 21/22).

Now rewritten as the correct claim, and RED.

## Related, in the same module and same family

**A rejected entry makes a governed tool vanish from every analyzer while the summary still says a layer was read.** Measured: a layer whose only Bash rule is `{"no_match": "Bash(rm -rf /)"}` gives `discover_tools() == ()` and `audit_context().tools == []`, while `config_summary().layer_count == 1`.

That is proposed ticket 42's silent-`None` meeting ticket 29's empty-verdict shape, in one call. **Deliberately not pinned** — ticket 42 leaves the fix direction open (raise / filter / sentinel) and any assertion here would pick one.

Also measured: **`"Bash(ls:*"` — an unclosed wrapper — is ACCEPTED by `normalize_entry` with zero issues.** Only `discover_tools`' `endswith(")")` check stops it naming a tool for the body `"ls:"`. That check is on ticket 31's repo-wide zero-detection list; it now has a test.

## Three dead branches and one misleading failure count, recorded so nobody re-derives them

- **`per_layer_rules`' three `tl is not None` guards are dead.** `permission_layers` appends unconditionally — one `ToolPatternLayer` per layer, no guard — so a layer's provenance is never absent from the lookup. Proven across distinct provenances, equal provenances, and a layer with no `[permissions]` section. They would become live only if the equal-`Provenance` fix zips sequences of unequal length.
- `audit_context`'s `if takeover.enabled:` is a **redundant fast path** — `neutralized_by_takeover` returns `False` for every pattern when disabled.
- `_layer_comment_map`'s `start == -1` guard is likewise a fast path — the slice is `''` and parses to `{}` either way.

**And a warning about reading counts**: removing `_layer_comment_map`'s `OSError` guard fails **12 tests, only one of which is about that guard** — because `audit_context` re-reads each layer file once per (tool, layer) pair. **A failure count of 12 reads as thorough coverage; the tracebacks say the opposite.**

## What the module could not see

`test_load_config_returns_configuration` **passed with project-level discovery entirely disabled** — its `assertGreater(len(config.layers), 0)` was satisfied by the developer's own `~/.claude`, not by its fixture. `TestLoadConfig` patched nothing and read 6 real user layers.

Mutation score: **18 of 38 survivors → 6**, all six accounted for (three proven equivalent, two are the mutate-toward-the-fix pair, one deliberately unpinned).