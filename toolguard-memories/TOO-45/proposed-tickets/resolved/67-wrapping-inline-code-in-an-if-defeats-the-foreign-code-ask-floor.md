---
title: Wrapping foreign inline code in an if or while defeats the ASK floor entirely
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/67-wrapping-inline-code-in-an-if-defeats-the-foreign-code-ask-floor
---

**FIXED in `05f786d` (TOO-45 phase 2).** Wrapping foreign inline code in `if`/`while` no longer defeats the ASK floor; both bare and `if`-wrapped forms floor, no grammar change was needed — see `toolguard/parser/command_extractor.py:513-527`.

# The floor the disclosure rule depends on is lost inside a control structure

**Found 2026-08-13. RED test in the tree. Confirmed end to end through `toolguard.testing.sandbox`, not inferred.**

## The bypass

Under `Bash(*)` with takeover on:

```
python -c "import os"                        ->  ask    (ASK floor applied: inline/heredoc foreign code)
if python -c "import os"; then :; fi         ->  allow
```

`command_extractor.py:482` builds the **if-condition leaf directly** instead of routing it through `_apply_leaf_policy`, so the floor is never applied.

**Extraction is not the problem — the sub-command is even named in the resulting reason.** Only the policy flag is dropped. So the command is seen, understood, and then allowed.

## And ticket 19's P1 defeats it completely

```
while python -c "import os"; do :; done      ->  [LeafCommand(':')]   ->  allow
```

The `while` condition is never extracted at all, so there is nothing to apply a floor to.

**Ticket 19 names `rm -rf` as its example and does not state that the inline-code ASK floor is among the casualties.** That understates its scope: P1 is not only a deny-rule bypass, it is a **disclosure-floor bypass**.

## Why this one matters more than its size

This floor is the mechanism `CLAUDE.md`'s entire disclosure rule is built around — the reason `python -c` and heredocs prompt even under a blanket allow. Its measured history in this project is that **agents skip disclosure most often on exactly these forms**.

So the two shapes that defeat it are the two shapes a command takes when it is doing something conditional — which is to say, when it is least predictable.

**Owner note**: the `while` half belongs to ticket 19 and `test_compound.py`; only the `if` half is new here. Reported rather than duplicated.

## Six missed forms and one over-detection, all measured, all now RED

| command | floored? | should be |
|---|---|---|
| `python -uBIc "import os"` | no | **yes** — a 3-flag bundle exceeds the regex's `{0,2}` |
| `perl -E 'say 1'` | no | **yes** — the inline-flag letter class is case-sensitive |
| `node --eval "..."` | no | **yes** — the table and regex are short-form only |
| `python -X dev -c "..."` | no | **yes** — a value-taking flag before `-c` stops the scan |
| `awk '{print $1}' f` | no | yes (P6) |
| `awk -f prog.awk f` | **yes** | **no** — P6's inversion |
| `gawk -f` vs `awk -f` | disagree | must agree (P14) |
| **`grep python -c file`** | **yes** | **no** — benign; `python` is grep's *pattern* and `-c` its count flag |

The last is the **false-positive** direction, and the module previously had **no fixture that could detect over-flooring at all** — its Baseline class docstring claimed to guard it while none of its five fixtures could fail on the over-detection that actually exists. Two green wrapper tests (`timeout 5 python -c`, `env X=1 python -c`) now sit beside the RED one, so a naive "anchor the executor to position 0" fix fails loudly rather than silently trading one error for another.

## A pinned defect removed

`python -X dev -c` was recorded as a `KNOWN_LIMITATION` — i.e. **the defect was pinned green as expected behaviour**. Flipped to RED under hard rule 6. That is the first pinned-defect removal of the campaign.

## An equivalent mutant that is also the fix

`scan_drop_exact_flag_check` was proven equivalent by an **exhaustive sweep of the whole flag table**: the exact check and the regex branch disagree on exactly one `(owner, flag)` pair — `awk`/`-f`.

**That single disagreement is P6's fix.** Applying it turns two of the RED tests green and breaks nothing — the "mutate toward the fix" property, now held by this module.

## A masking pair

The two basename strips in the executor check mask each other: neither is detectable alone, and **removing both** fails `test_absolute_path_to_interpreter_detected`, their sole detector.

Mutation: **8 of 20 survivors → 2**, both proven equivalent.

## Method note

An unexplained `.pyscn/reports/analyze_*.html` appeared mid-run. Rather than report a leak, the agent checked timestamps and found **`pyscn analyze` running externally about every 45 seconds** — five reports in eight minutes. Explained, not subtracted, and not attributed to the tests.