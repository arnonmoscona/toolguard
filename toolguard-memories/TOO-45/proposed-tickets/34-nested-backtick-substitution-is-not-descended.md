---
title: Nested backtick substitution is not descended into, so an inner command never
  becomes a matchable leaf
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/34-nested-backtick-substitution-is-not-descended
---

# Nested backticks bypass per-leaf matching

**Severity: this is a permission bypass, same class as proposed ticket 19's P1.** Found 2026-08-12 by the test-repair campaign, by making a vacuous test real — not by looking for it.

## The defect

`extract_commands`' own docstring says it "descends into command substitutions (`$(...)` and backticks)". For the POSIX *nested* backtick form it stops one level short.

```
extract_commands("echo `echo \\`rm -rf /\\``")
  -> ['echo `echo \\`rm -rf /\\``', 'echo \\`rm -rf /\\`']
```

`rm -rf /` never becomes a leaf. The identical `$(...)` form does yield it:

```
extract_commands("echo $(echo $(rm -rf /))")   ->  ... 'rm -rf /'
```

## Why it matters

Permission matching is per-leaf. If the dangerous command never becomes a leaf:

- an allow rule on `echo*` **matches the surviving leaf** and the command is permitted
- a deny rule on `rm -rf*` **never sees the inner command** and does not fire

So the two substitution syntaxes, which bash treats as equivalent, resolve to different permission outcomes. Only one of them is governed.

## Why the tests did not catch it

`TestCommandSubstitutionAdvanced.test_nested_backticks` existed and passed. Its assertion was in catalogue shape 20 — satisfied by the fail-open safety net (`extract_commands` returns `[original.strip()]` on any parse error), so `assertGreater(len(result), 0)` could not distinguish successful extraction from failure.

**The test is now repaired and left deliberately FAILING**, per the campaign rule that a test exposing a real defect is a finding, not something to fix by weakening. Its docstring carries a do-not-weaken note.

## Fix direction, NOT yet decided

This is grammar territory. Per `.claude/rules/bash-grammar.md` the change is **two-phase: `.peg` plus canopy regeneration first, reviewed, then Python** — never hand-rolled parsing. Do not let the shape of this bug tempt a regex.

Open question for Arnon: whether the correct behaviour is to descend (governing the inner command) or to treat an unparseable nesting as **undecidable** and let the ask-floor take it. The second is cheaper and arguably safer, and connects to proposed ticket 11.

## Status

`test/unit/test_compound.py` currently has **1 failing test** in the working tree because of this. That is intentional and must not be "fixed" by weakening the assertion.