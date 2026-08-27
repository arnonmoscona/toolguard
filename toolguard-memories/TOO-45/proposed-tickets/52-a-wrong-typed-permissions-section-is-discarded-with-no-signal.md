---
title: A wrong-typed permissions section is discarded silently - no parse failure,
  no validation issue, no warning
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/52-a-wrong-typed-permissions-section-is-discarded-with-no-signal
---

**PARTIALLY FIXED in `05f786d`.** The wrong-typed `[[permissions]]` shape is now caught at both sites (`toolguard/config.py:1737`, `toolguard/config_validation.py:75`); still open: a bare-string `allow = "Bash(ls:*)"` is still silently lost, since `toolguard/config.py:1733` iterates its characters rather than checking its shape, producing nine character-level warnings and no error.

# `[[permissions]]` loses every rule in the section, silently

**Found 2026-08-13. Three RED tests are in the tree. Measured end to end, not inferred.**

## The defect

Write `[[permissions]]` instead of `[permissions]` — a plausible typo, and valid TOML — and the whole section is discarded with **no signal of any kind**:

| check | result |
|---|---|
| does it parse? | **yes** |
| `permissions` comes back as | a `list`, not a `dict` |
| `validate_permissions` | returns `()` |
| `parse_failures` | empty |
| `validation_issues()` | empty |
| `has_any_rules("Bash")` | **`False`** |

So the user's rules are gone, toolguard believes the tool is unconfigured, and **nothing anywhere says so.** The same holds for `allow`/`deny`/`ask` written as a bare string rather than a list.

This is ticket 29's family — "reports OK having examined nothing" — but at its worst: not a checker returning a vacuous pass, a **configuration silently ceasing to exist**.

## THE TRAP FOR PHASE 2 — one defect, two sites, and fixing one hides nothing

**`config.py:1704`, inside `Configuration.validation_issues()`, has its OWN `isinstance(permissions, dict)` guard that skips the layer *before* `validate_permissions` is ever called.**

Measured: fixing `config_validation.py` alone turns the unit-level REDs green **while the end-to-end test stays red**. A fix that looks complete by its own tests would leave the user-visible loss intact.

Both sites need the change. The end-to-end RED test (`test_a_discarded_permissions_section_is_surfaced_somewhere`) is the one that proves it, and it is deliberately written at that altitude for this reason.

Same family as proposed ticket 42 — a guard that discards information quietly, duplicated, so neither site alone is the whole answer.

## Mutate toward the fix

- a `validate_permissions` that reports wrong-shaped sections: module goes **4 REDs → 2**
- a content-hashed cache key (ticket 27): **4 → 3**
- **at HEAD, both fixes produced 0 failures** — the suite saw neither defect nor correction

## Status in the tree

RED, all asserting correct behaviour:

- `test_toml_config.test_permissions_of_the_wrong_type_is_reported`
- `test_toml_config.test_allow_written_as_a_bare_string_is_reported`
- `test_toml_config.test_a_discarded_permissions_section_is_surfaced_somewhere` — the end-to-end one; see the phase-2 trap above
- `test_toml_config.test_equal_length_same_mtime_rewrite_is_not_served_stale` — proposed ticket 27's stated obligation, now pinned

## Deliberately pinned rather than made red

`governed_tools = "Bash"` silently falls back to `["Bash"]`. Pinned as characterization because the fallback is **safe** — it governs more, not less — and a permission naming another tool still draws a warning. The other two shapes lose rules outright, which is why they are red and this is not.

## Two corrections to neighbouring tickets

- **Ticket 46's guard is JSON-only.** `_try_parse_source`'s "expected a top-level object/table" check **can never fire for TOML** — a TOML top level is always a table. Deleting it outright produces zero failures. Its entire coverage obligation belongs to the JSON side.
- **`discover_config_files` is labelled "legacy… superseded" in its docstring, and `permission_migration.py:802` calls it live.** Either the label or the call is wrong.