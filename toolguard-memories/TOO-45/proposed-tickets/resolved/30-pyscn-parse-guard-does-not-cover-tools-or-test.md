---
title: The pyscn parse-failure guard covers only toolguard/, and three unguarded three-name
  except clauses exist outside it
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/30-pyscn-parse-guard-does-not-cover-tools-or-test
---

**FIXED in `05f786d` (TOO-45 phase 2).** The parse-failure guard now AST-scans every tracked `.py` file, not just `toolguard/` — see `test/unit/test_static_analysis_coverage.py:66,139`.

# The pyscn parse-failure guard covers only `toolguard/`

**Low severity, recorded because one of the affected files is the sweep's own verification instrument.**

## Background, already documented in the repo

`toolguard/install_provenance.py:53-56` records the hazard precisely: the parenthesis-free **three-name** form (`except A, B, C:`) is valid Python 3.14 but **silently excludes the file from `pyscn` analysis**, while the **two-name** form (`except A, B:`) parses fine and is used deliberately throughout. `test/unit/test_static_analysis_coverage.py` exists because *"that happened for real: one `except A, B, C:` clause silently reduced a..."*.

Note the interaction with an existing convention: `ruff format` **strips the parentheses** from `except (A, B):` on this project, so the two-name form appears everywhere and is correct. The hazard is specific to three or more names.

## The gap

`test_pyscn_reports_no_parse_failures` runs `pyscn analyze toolguard` -- **the package only**. `tools/` and `test/` are outside its scope, and three three-name clauses live there:

| file | clause |
|---|---|
| `tools/comment_hygiene.py:106` | `except OSError, SyntaxError, UnicodeDecodeError:` |
| `tools/change_role_classifier.py:1909` | `except SyntaxError, UnicodeError, LookupError:` |
| `test/unit/_real_log_dir_guard.py:114` | `except TypeError, ValueError, OSError:` |

All 22 unparenthesized clauses across the repo were enumerated; the other 19 are the safe two-name form.

## Why it is worth a row at all

The guard's scope is defensible -- `pyscn analyze` is run on the main package per the pre-push checklist, so `tools/` was never in scope. Two things make it worth recording anyway:

1. **`tools/comment_hygiene.py` is the instrument that verifies this entire sweep.** If it is ever brought under static analysis, it silently is not.
2. **`_real_log_dir_guard.py` is itself a guard**, installed from `test/unit/__init__.py` before any test module imports, and it exists because a checklist failed to prevent a real leak three times. A guard that static analysis cannot see is a poor place for this shape.

## Fix direction

Cheapest correct fix: parenthesise those three clauses. `ruff format` will leave a three-name parenthesised tuple alone (it only strips the two-name form), so the fix is stable.

If wider coverage is wanted, extend `test_pyscn_reports_no_parse_failures` to `tools/` — but decide that deliberately rather than by accident, since it changes what the pre-push `pyscn analyze` step is expected to cover.

## Provenance

TOO-45 #07, found by the `test/unit` infrastructure batch flagging `_real_log_dir_guard.py:114`, then scoped by enumerating all 22 unparenthesized except clauses and reading the guard test's actual target. 2026-08-12.
