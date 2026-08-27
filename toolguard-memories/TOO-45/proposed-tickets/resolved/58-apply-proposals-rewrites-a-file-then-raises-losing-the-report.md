---
title: apply_proposals rewrites one file, then raises on a malformed sibling - the
  caller gets a changed config and no report at all
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/58-apply-proposals-rewrites-a-file-then-raises-losing-the-report
---

**FIXED in `05f786d` (TOO-45 phase 2).** `apply_proposals` no longer rewrites the file and then raises, losing the report; both defects confirmed fixed by live dry-run and real-run probes — see `toolguard/tools/rule_apply.py:329-346`.

# A partial write with no record of what was written

**Found 2026-08-13. Two RED tests are in the tree. Queue row M5 said "batch atomicity stops at validation" by inspection; this is that, executed.**

## Defect 1 — a rewritten file is lost from the report

`apply_proposals` over `[good.toml, malformed.toml]`:

1. **rewrites `good.toml` on disk**, then
2. **raises** on the malformed sibling.

The caller gets a **modified configuration and no `ChangeReport` at all.** There is no record of what was changed, because the report is the return value and the exception replaces it.

`_render_via_writer` runs per target *before* the write gate, so something as ordinary as `permissions = "hello"` — a scalar where a table belongs — aborts the batch after earlier files have already been committed.

**This is the write-path twin of the campaign's recurring finding.** Elsewhere the problem was "the report says something happened and nothing did." Here it is the reverse: **something happened and there is no report.** Both leave the user unable to learn the true state from the output.

## Defect 2 — `dry_run=True` raises as well

A preview that is documented to write nothing is **destroyed by an unrelated malformed sibling**. A user cannot even *inspect* the proposed changes while any file in the set is malformed — which is precisely when they most want to look before acting.

## Status in the tree

- `test_tools_rule_apply.test_a_rewritten_file_is_never_lost_from_the_report` (:758)
- `test_tools_rule_apply.test_a_dry_run_previews_the_files_it_can_render` (:782)

Both written **mechanism-agnostically**: they pass under *skip-the-bad-file-with-a-reason* **or** *validate-everything-before-the-first-write*, so neither preempts the design decision. Which of those is right is Arnon's call.

## The related gap that had no coverage at all

**The `list_type != "allow"` refusal is this module's only structural guard against enacting a widening** — a `deny`-typed proposal, if accepted, would be written into `allow`. **It had zero test coverage.**

That guard is the last line behind proposed ticket 57's hole 1, where `--apply` could enact a `git :*` broadening because `collect_consolidations` returning broadenings survived with zero failures. **Two layers of the same write path, both unguarded, found on the same day.**

## What the module could not see

Every content check was `assertIn`/`assertNotIn` over the **whole file text** — placement-blind by construction, since a pattern sitting in `deny` satisfies `assertIn(pattern, text)` identically. **`deny` and `ask` were absent from every fixture**, so dropping either list entirely was undetectable. The `verified_write_config` test asserted two `assertIn`s on `expected_patterns` and **never looked at the text actually handed to the guard**.

Mutant survival: **13 of 29 → 0 of 29.** Newly covered: `deny`/`ask` preservation, the widening guard, idempotence, multi-file grouping, `patterns_removed`/`patterns_added`, both `_read_raw_permissions` guards, and two render branches.

The repair reads results back with `tomllib`/`json` **rather than toolguard's own reader**, deliberately — so a shared read/write bug cannot hide behind a round trip.

## Ticket 39 confirmed unchanged from this side

`expected_patterns` is a flat list carrying **no list identity** — measured: `['Bash(ls:*)', 'Bash([regex]^git (diff|status))', 'Bash(rm -rf /:*)', 'Bash(curl:*)']`. Following ticket 39's own precedent, no list-aware API was invented in a test; the placement is caught **on disk** instead, and the blindness is recorded in the docstring.

## Pinned, not red

`test_a_second_copy_of_a_removed_rule_survives` — removal takes one occurrence per pattern, so a duplicated rule survives consolidation. Characterization: the survivor is **narrower** than the regex replacing it, so the result is redundant rather than a widening.