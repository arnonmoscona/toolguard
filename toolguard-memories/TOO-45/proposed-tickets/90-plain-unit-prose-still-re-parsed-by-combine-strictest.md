---
title: A 'plain' unit's own multi-part summary is still re-parsed as prose by _combine_strictest's outer combine
tags: [TOO-45, proposed-ticket]
permalink: toolguard/too-45/proposed-tickets/90-plain-unit-prose-reparse
---

# The ticket-79 fix masks this for `'inline_code'` units; it does not remove it

Found 2026-08-21 by the ticket-79 round-3 reviewer, reviewing the regenerated
`test/verdict_corpus/goldens.jsonl`. Of the two golden lines the ticket-79 fix changes:

```
line 1107 OLD open=4  close=5   ->  NEW open=3  close=3   (fixed)
line 2807 OLD open=14 close=16  ->  NEW open=11 close=12  (still unbalanced)
```

The survivor at line 2807 is (one sub-command inside a 17-sub-command compound):

```
echo " checked_bash remaining in agents/: $(grep -l checked_bash *.md | wc -l) files"
```

This substitution carries no foreign inline code, so the leaf stays a `'plain'`
`CommandUnit`, not an `'inline_code'` one -- the escape-hatch fabrication guard ticket-79
added to `judge_unit`'s `'inline_code'` branch never runs for it. A `'plain'` leaf's own
multiple sub-commands are still combined into one already-rendered `"cmd -> pattern"`-joined
summary string. When the WHOLE compound (all 17 top-level leaves) is combined a second time,
`_combine_strictest`'s own multi-unit branch re-parses that summary as if it were a single
match:

```python
if " -> " in r:
    pattern_part = r.split(" -> ", 1)[-1]
```

(`toolguard/compound.py:1111`, in `_combine_strictest`). The leaf's own inner join already
contains ` -> `, so this split takes only the text after the LAST arrow and drops everything
before it -- an extra unmatched `]` survives into the final reason
(`... wc -l -> [fallback allow -- no rule matched]], grep -o 'Bash' ...`).

## Why this is the same defect ticket-79 fixed, one scope narrower

This is a direct instance of the project's founding defect -- "never build a prose string
and then parse it back within the same runtime" (global `CLAUDE.md`, "Prose is output, not a
data structure"). Ticket 79 fixed exactly this shape for `'inline_code'` units, by forcing
the unit's own `fallback_kind` (a structured tag) so the outer combine never has to guess
from text. It did not touch the `'plain'`-unit path, where the same re-parse still runs on a
different unit kind's own summary.

## Scope

`verdict`/`sub_matches` are unaffected -- confirmed unchanged by `tools/corpus_build.py
--verify` across the whole corpus. Only the TRACKED-tier prose (the human-readable
`reason` string) is garbled for compounds combining a multi-sub-command `'plain'` leaf with
other allowed leaves. Not a gate on ticket 79 -- pre-existing, and fixing it means changing
`'plain'`-unit summarisation, which is out of that ticket's scope.

## Fix direction

Give a `'plain'` unit's own already-combined summary the same structured escape ticket-79
gave `'inline_code'`: either tag it so the outer combine never re-parses it as a single
match, or have the outer combine work from structured per-unit data (`UnitVerdict` fields)
rather than splitting rendered text on `" -> "`.
