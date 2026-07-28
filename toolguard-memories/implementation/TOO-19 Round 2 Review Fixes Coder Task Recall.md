---
title: TOO-19 Round 2 Review Fixes Coder Task Recall
type: note
permalink: toolguard/implementation/too-19-round-2-review-fixes-coder-task-recall
---

## Context
Ticket TOO-19, branch too-19. Fixing 3 confirmed defects found via repro (not just review).
Baseline: 1757 unit tests, all green (confirmed 2026-07-27 14:58).

## Defect 1 (MAJOR): malformed structured entry blocks every config write
Files: toolguard/rule_entry.py (normalize_entries_preserving), toolguard/config_write_guard.py
(_entry_pattern / _patterns_in_parsed).

normalize_entries_preserving assigns unparseable elements a SYNTHETIC pattern = repr(raw).
Write paths pass these as expected_patterns to verified_write_config, which recomputes REAL
patterns from written text - never produces repr() string - so content-loss guard thinks a
rule was dropped and refuses the write.

Repro: allow = [ "Bash(ls)", { additionalContext = "oops" } ]  (missing `match` key)
-> ConfigWriteVerificationError: write would drop existing rule pattern(s) -- missing
   pattern(s): {'additionalContext': 'oops'}
Same for JSON config with non-string element like 42.

Fix approach: add explicit `synthesized_pattern: bool` field (or equivalent marker) to
RuleEntry, set in normalize_entries_preserving. Filter these out wherever expected_patterns
built: migrate_permissions._patterns_from_permissions, rule_apply._apply_to_file,
maintenance._permission_patterns_in_text (has own repr() fallback via _rule_pattern_of_value
- fix that too).

DO NOT weaken content-loss guard generally - must still refuse genuine drops. Add test
proving real dropped pattern still refused.

Improve error message: tell user which FILE and, where known, which entry is malformed.

Tests needed: malformed structured entry still migrates/writes; genuine drop still refused;
JSON non-string element works.

## Defect 2 (MAJOR): render_toml_entry crashes on non-str, non-dict values
File: toolguard/rule_sort.py (render_toml_entry)

Repro: render_toml_entry on entry whose to_source() is 42, None, or True raises
AttributeError: 'int' object has no attribute 'replace'. Handles dict, falls through to
_escape_toml_string for everything else - but JSON config permissions.allow can hold any
JSON value, and normalize_entries_preserving deliberately preserves it.

Fix: module already has total renderer _render_toml_scalar (handles all these, dispatches to
_render_toml_inline_table for dicts). Delegate to it. Confirm behavior unchanged for the two
supported shapes (plain string, structured dict) - existing tests must stay green with NO
edits to them.

Add tests for int / bool / None / list entry values.

## Defect 3 (MAJOR): find_section_boundaries regression - trailing comment
File: toolguard/toml_scan.py (find_section_boundaries)

Previous fix (this session) tightened substring scan to whole-line anchored regex
`^[ \t]*\[name\][ \t]*$`. Fixed a corruption bug but regressed valid common TOML shape:
`[permissions] # my perms` -> now returns (-1,-1) instead of correct boundaries.

Impact: write_toml_config treats as "no section" and APPENDS a duplicate table -> write
guard refuses -> migration hard-fails. installer._replace_or_append_toml_section has same
issue for [takeover_mode]/[hard_deny]. annotate, config_access._layer_comment_map,
maintenance._permission_patterns_in_text silently degrade to "no rules found".

Fix: allow optional trailing comment in BOTH header pattern and next-section-header
(end-boundary) pattern: `^[ \t]*\[name\][ \t]*(#.*)?$`.

CRITICAL: do not regress original bug - `[permissions]` appearing INSIDE a quoted string
(e.g. additionalContext value) must NOT match. Verify with
scratchpad/probe6.py -> must still print "parsed OK" with hard_deny rule intact.

Add characterization tests: trailing comment; trailing comment with odd spacing; comment
containing `]`; quoted-string false-positive regression guard.

## Wrap-up requirements
- Full suite green, report count.
- Re-run scratchpad/probe6.py (must print "parsed OK", hard_deny intact) and
  scratchpad/verify_change4.py (must print "PASS - both metadata preserved").
- ruff format ONLY the edited files (not bare `.`), then ruff check . clean.
- Append dated "Round 2 review fixes" section to existing report:
  toolguard-memories/TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md
- NO git write operations.

## Notes on current repo state
Working tree already has a very large staged+unstaged diff spanning nearly the whole
toolguard/ package and many test files (pre-existing from prior session work on TOO-19,
not created by me). This task is scoped ONLY to the 3 defects above - must not get drawn
into reviewing/redoing the rest of that diff.
