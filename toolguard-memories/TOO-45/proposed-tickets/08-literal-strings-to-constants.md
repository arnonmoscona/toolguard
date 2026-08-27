---
title: 08-literal-strings-to-constants
type: note
permalink: toolguard/too-45/proposed-tickets/08-literal-strings-to-constants
---

# Proposed: replace semantic string literals with constants

**Status:** deferred from TOO-45. Global guidance now carries the rule; this is the sweep of existing code.

## Problem

The project branches on bare string literals throughout. Your example: `if unit.kind == "inline_code":` — the same literal appears twice in one module and again in tests. Nothing catches a typo, nothing finds the other sites, and renaming means grepping prose.

**The worse offenders are the decision vocabulary** — `"allow"`, `"deny"`, `"ask"` — which appear across the engine, the config layer, the hook, the tooling, and the entire test suite. `LOG_FORMAT_MARKDOWN` / `LOG_FORMAT_JSONLINES` show the project already knows the pattern in places.

## Why it matters more than it looks

A verdict string is the single most load-bearing value in this product. A typo in a comparison against `"deny"` fails **open** and silently — the branch simply does not fire. That is the failure direction that matters here.

## Proposed approach

Highest value first, and each is independently shippable:

1. **Decision vocabulary** — `allow` / `deny` / `ask` / `allow_with_warning`. Almost certainly belongs in `constants.py` (foundation), which every layer may import.
2. **Unit kinds** — `plain` / `inline_code` / `undecidable`, introduced by the recent compound refactor. Small and fresh; cheapest to do now.
3. **Format, status and source-type names** — smaller populations, mechanical.

Not in scope: log messages, format strings, one-off text. The rule is about values the code **branches on**.

## Risk

A mechanical find-and-replace will hit string literals inside test fixtures, golden corpus data and documentation examples, where the literal is *data* and must stay literal. The golden corpus in particular contains thousands of `"allow"` / `"deny"` values that are records, not code. **This cannot be done with sed.**

## Size

Medium. Step 2 alone is under an hour and worth doing regardless.

## Decision needed

All three steps or just the decision vocabulary? And now, or after the doc-comment sweep — they touch the same files and interleaving them would make review harder.