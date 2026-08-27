---
title: A settings.local.json containing a JSON array crashes the divergence check
  on the live hook path
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/46-non-object-json-crashes-the-divergence-check-on-the-hook-path
---

**FIXED in `05f786d` (TOO-45 phase 2).** Non-object JSON in `settings.local.json` no longer crashes the divergence check, verified end-to-end through the real hook — see `toolguard/config_divergence.py:45-46`.

# `config.get(...)` outside the `try`

**Found 2026-08-13. A RED test is in the tree. This is queue row V2, now reproduced.**

## The defect

`config_divergence.py:51` calls `config.get("permissions", {})` **outside** the enclosing `try`. If `settings.local.json` contains a top-level JSON array — `[]` — the parsed object is a `list`, `.get` does not exist, and an `AttributeError` propagates out of `check_and_warn_divergence`.

That function runs on the **live hook path**.

## Relationship to proposed ticket 40 — same family, different site

Ticket 40 found that `verify_config_text` accepts any JSON document, so a *write* can put `null` or `[]` into a config. This is the *read* side of the same assumption: **the codebase repeatedly assumes a parsed JSON config is a `dict` and checks that in only some places.**

Worth fixing together. The general form is one guard at the parse boundary, not `isinstance` checks scattered at each use.

## What is and is not established about the consequence

**Established:** the `AttributeError` escapes `check_and_warn_divergence`.

**Not established, and it should not be claimed without measurement:** `hook.py` wraps its work in three top-level `except` clauses, so the ordinary outcome is that the exception is caught, `log_crash` runs, and `_emit_decision` emits a `deny`. That is fail-closed and acceptable.

The compounding risk is **conditional**: proposed ticket 23 shows `log_crash` can itself raise (its `errors_dir` is built above its own `try`), and when it does, `_emit_decision` never runs and the hook exits with **nothing on stdout** — which Claude Code reads as no enforcement. So a malformed config file plus a `log_crash` failure gives a silent no-enforcement path.

**Both conditions are needed.** Ticket 23's failure requires `Path.home()` to raise, which is rare. Do not describe this as a guaranteed chain — describe it as two filed defects that compose badly, which is a good reason to fix the cheaper one (23, a one-line fix already proven) first.

## Status in the tree

`test_config_divergence.test_non_object_json_top_level_is_treated_as_unreadable` is deliberately RED. It reports as an **error**, not a failure, because the `AttributeError` propagates — worth knowing when reading suite totals, since an error is easy to miss in a `failures=N` summary.

## Also found in the same module, not defects

- **The once-per-day pre-check and the warn-claim are redundant in-process.** Removing either alone changes no same-day outcome: the pre-check answers first in-process, and the warn-claim's unique job is the cross-process race, which only a subprocess test can exercise. Neither is dead code, but **neither is observable through the other's outcome** — worth knowing before anyone "simplifies" one away. Both are now independently detected.
- **`sorted()` in the warning's pattern list had zero test detection**; now covered.
- Queue row V3 confirmed by reading: `except (json.JSONDecodeError, IOError, Exception)` is exactly `except Exception`. Not fixable from the test side.