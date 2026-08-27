---
title: TakeoverConfig's 4th positional field is no_match_fallback, so the stock "takeover
  off" fixture silently sets it to deny at ~22 sites
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/47-takeoverconfig-positional-construction-silently-sets-the-fallback
---

# A positional argument that changes an unrelated decision

**Found 2026-08-13 while repairing `test_configuration.py`. It surfaced as a real test failure, not by inspection.**

## The hazard

`TakeoverConfig`'s fourth positional field is `no_match_fallback`, and `resolved_no_match_fallback()` honours it as the legacy alias.

The module's stock stand-in for "takeover is off" is:

```python
TakeoverConfig(False, (), (), "deny")
```

Used at roughly **22 sites**. Every one of them **also silently sets the no-match fallback to `deny`** — a completely different decision from the one the fixture is named for.

## Why it matters beyond one module

A test that reaches the no-match branch under this fixture gets `deny` for a reason its author never chose, and cannot tell that from a `deny` produced by the mechanism under test. **That is catalogue shape 4 manufactured by a fixture** — and it is invisible, because the fixture reads as "takeover disabled" and nothing on the line mentions fallbacks.

One test in `test_configuration.py` genuinely depended on it, discovered only when the fixture was corrected. Any future test in that file that touches the no-match path inherits the hazard.

## Fix directions

- **`@dataclass(kw_only=True)` on `TakeoverConfig`.** Makes the positional form impossible, so a fixture must name what it sets. Cheapest, and it converts the whole class of mistake into a syntax error.
- Or a named constructor for the common case — `TakeoverConfig.disabled()` — so the stand-in carries no incidental values at all.

The first is preferable: it fixes every current and future site rather than the ones someone remembers to migrate.

## REFINEMENT 2026-08-13: the hazard also arrives through a DEFAULT, not only a position

`test_takeover_mode.py` used the **keyword** form at both its `TakeoverConfig` sites, so the positional mis-index above was absent — **and the damage happened anyway**. Both sites hardcoded `no_match_fallback="deny"` unconditionally, *including in the "takeover off" fixture*, while production's own default is `ask`. Every Bash test reaching the no-match branch got a `deny` nobody chose.

So `kw_only=True` is necessary and **not sufficient**. The version of the hazard actually found is closed by either:

- **removing the default entirely**, so a construction site must state the fallback, or
- a named constructor for the common case — `TakeoverConfig.disabled()` — carrying no incidental values at all.

**A second fixture hazard of the same family, found in the same module and not covered by this ticket's original framing:** `ignored_allow_patterns` was `("Bash(*)", …)` when takeover was enabled and `()` when disabled — so flipping `takeover_enabled` changed **two things at once**, and no difference in outcome could be attributed to the switch. Production seeds those patterns regardless of `enabled`. The general rule: **a fixture parameterised on a boolean must vary that boolean and nothing else**, or the test cannot attribute what it observes.

## Relation to a standing preference

This is the positional-tuple hazard in a different costume: a positional field that is easy to mis-index or to fill in without meaning to. A frozen dataclass was already the right shape here — **what is missing is `kw_only`**, which is the part that actually prevents the mistake.

## Also found in the same pass, unrelated to the above

- **`_discover_rules_files` is dead production code.** Its only callers are five tests in `test_configuration.py`, plus two incidental strings in the verdict corpus. **Five tests exercise code nothing in production reaches.** Delete it, or wire it up — the working queue flagged this and it is confirmed.
- **Two more by-value import bindings that defeat naive patching**: `config.py:52` imports `entries_for_tool` from `rule_entry`, and `config_types.py:15` imports `_strip_tool_wrapper`. Patching the defining module is a silent no-op for both. Add them to the sweep in proposed ticket 43.