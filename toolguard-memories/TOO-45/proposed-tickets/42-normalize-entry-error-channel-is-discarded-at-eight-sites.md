---
title: normalize_entry returns (None, error) and eight call sites discard the error,
  keeping the None
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/42-normalize-entry-error-channel-is-discarded-at-eight-sites
---

# A rejected entry becomes a silent `None` flowing downstream

**Found 2026-08-13, while answering a narrower question: is `render_toml_entry(None)` reachable at runtime?**

## What was measured

`normalize_entry` is the single normalize/merge chokepoint for permission entries. On a bad entry it does the right thing:

```
normalize_entry(None, False)
  -> (None, (Issue(level='error',
                   message="Permission entry has an unsupported type 'NoneType': None",
                   corrective_steps="Use either a 'Tool(pattern)' string or a structured table ..."),))
```

**A clear rejection, with a good diagnostic.** The JSON-null path into `render_toml_entry` is therefore closed at the first hop.

**But the rejection is returned in a channel most callers throw away.** Eight sites take the entry and discard the issues:

| site | form |
|---|---|
| `config.py:1022` | `entry, _issues = normalize_entry(...)` |
| `config_validation.py:81` | keeps issues (correct — this one is the validator) |
| `permission_migration.py:1075` | `new_entry, _issues = ...` |
| ~~`rule_entry.py:527`~~ | **NOT AN INSTANCE — see correction below** |
| `tools/config_access.py:189` | `entry, _issues = ...` |
| `tools/config_access.py:279` | `entry, _issues = ...` |
| `tools/redundancy.py:224` | `normalize_entry(...)[0]` — positional, no name at all |
| `tools/rule_apply.py:205` | `new_entry, _issues = ...` |

**CORRECTION 2026-08-13, same day this ticket was filed: the count is SEVEN, not eight.** `rule_entry.py:527` (`normalize_entries_preserving`) was counted by grepping for the `_issues` shape, which is exactly the mistake this campaign keeps punishing — matching a pattern instead of reading the code. It is materially unlike the other seven: it does **not** let a `None` flow downstream. It replaces the `None` with `RuleEntry(raw=raw, synthesized_pattern=True)`, re-encoding the rejection as **structured data that is tested and that `real_patterns` acts on**. The Issue's prose is lost; the *fact* of rejection is not.

So the damage model below holds for seven sites. And the corrected count makes `rule_entry.py:527` the **model for the fix** rather than an instance of the defect: it shows the pipeline already has a way to carry a rejection forward without a bare `None`.

The underscore prefix marks the discard as deliberate at each remaining site. **Collectively it means a rejected entry does not stop anything — it becomes a `None` in a list that downstream code assumes holds entries.**

## Why it matters

Neither writer that renders TOML filters `None`:

- `permission_migration.py:509` — `for entry in entries: lines.append(f"  {render_toml_entry(entry)},")`
- `tools/installer.py:1618` and `:1623` — same shape for the `[hard_deny]` section

`render_toml_entry(None)` returns `'"None"'`, so a `None` that reaches either writer produces **a rule literally named `None`** in the user's config — in the `[hard_deny]` case, in the section that is supposed to be unoverridable.

## What is NOT established

**No complete path from a config file to `render_toml_entry(None)` has been traced.** The ingredients are all present; a demonstrated end-to-end reproduction is not. Do not describe this as a confirmed bypass until someone closes that gap — the honest status is *plausible and unproven*.

## Why the ticket is still worth filing at this status

The narrow question ("what should `render_toml_entry(None)` do?") is the wrong one, and it is the question the test suite currently records as an open design issue. **The right question is why a rejected entry is representable at all downstream.** Options:

- have `normalize_entry` raise rather than return `(None, issues)`, so a caller cannot ignore it by accident
- keep the tuple but make callers filter, and add the filter to the two writers as a belt-and-braces measure
- return a sentinel that is not `None`, so it cannot silently satisfy a truthiness or iteration check

Any of those makes the `render_toml_entry(None)` question moot, which is the sign it was a symptom rather than the defect.

## Related

Proposed ticket 25 (`rule_entry` accepts a multi-line entry that is displayed as configured and matches nothing) is the same family: **the entry pipeline is tolerant in places where tolerance is indistinguishable from silent loss.**

The `render_toml_entry(None)` characterization test in `test_rule_sort.py` should stay as-is until this is decided — it records a real observable, and asserting any particular answer would preempt the design choice above.