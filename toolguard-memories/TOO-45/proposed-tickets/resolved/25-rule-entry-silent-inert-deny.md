---
title: A newline in a rule produces a silent inert deny -- accepted, displayed, matching
  nothing
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/25-rule-entry-silent-inert-deny
---

**FIXED in `05f786d` (TOO-45 phase 2).** A newline-containing deny rule is now rejected as an error-level Issue instead of being accepted and matching nothing — see `toolguard/rule_entry.py:358-367`.

# A newline in a rule produces a silent inert deny

**Severity: an operator believes a deny rule is in force when it can never fire.** No bypass, but no warning either, at any level.

## The defect

```python
normalize_entry("Bash(rm -rf /)\nBash(dd *)")
```

is **accepted with no issue raised**, is scoped to `Bash`, is **displayed as configured**, and **matches nothing**.

The mechanism: the fullmatch that would strip the `Bash(...)` tool wrapper is defeated by the embedded newline, so the wrapper is never stripped and the resulting pattern cannot match any command.

## Why this is not a bypass, and why it still matters

`permissions.py:111-125` independently excludes newline-bearing commands from matching, so no command sneaks through because of this. The damage is entirely in the operator's model:

- The rule appears in the config.
- It appears in any listing of configured rules.
- Nothing warns at parse time, at load time, or at decision time.
- It is a **deny**, so the belief it creates is a belief about protection.

A deny rule that silently does nothing is worse than a missing one. A missing rule gets noticed the first time something dangerous is allowed; an inert one is invisible until the same moment, and then looks like a toolguard failure rather than a config error.

## Confirmed: no test covers it

Measured during the `test_rule_entry.py` sweep. **No test in the file exercises `normalize_entry` on a plain string with an embedded newline.** The two nearby tests cover different paths -- structured-entry rejection, and `is_tool_wrapper` directly -- and neither reaches this case.

Worth stating explicitly because it is the good outcome of the check: **no docstring frames the untested case as safe.** This is a plain coverage hole, not a laundered claim, so nothing has to be un-taught before it is fixed.

## Fix direction

Raise a validation issue when an entry's command portion contains a newline. The entry is not merely unmatched -- it is malformed, and `rule_entry` already has an issue channel for saying so.

Decide separately whether the correct handling is *reject the entry* or *accept and warn*. Rejection is cleaner but changes load behaviour for configs that currently load silently; a warning preserves that but relies on someone reading it. Given the rule is a deny, rejection seems right -- a config error is better than a false sense of protection.

## Test obligation

The one-line case above, asserting an issue is raised. And a sibling asserting the entry does not appear as an active, matchable rule.

## Provenance

Found in the `rule_entry.py` module sweep, coverage gap confirmed in the `test_rule_entry.py` sweep, TOO-45 #07. `reports/follow-up-queue.md` sections covering `rule_entry` and `REN`.
