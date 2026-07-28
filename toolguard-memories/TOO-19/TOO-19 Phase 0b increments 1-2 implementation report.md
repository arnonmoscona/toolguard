---
title: TOO-19 Phase 0b increments 1-2 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-0b-increments-1-2-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Implemented TOO-19 Phase 0b increments 1 and 2 on branch `too-19`. Both purely additive,
no production behaviour changed for any EXISTING function.

- **Part 1 (increment 1):** new `test/unit/test_rule_sort.py` with characterization tests
  for `parse_permissions_section_with_comments`, `reassemble_permissions_section`, and
  `find_section_boundaries` -- documenting CURRENT behaviour, including one confirmed bug
  (not fixed, per the characterization-tests mandate).
- **Part 2 (increment 2):** new `ArrayElement` dataclass + `split_array_elements()`
  function appended to `toolguard/rule_sort.py`. Not wired into anything.

## Files changed

- `toolguard/rule_sort.py` -- MY changes only: (1) import line
  (`from dataclasses import dataclass`, added `Optional` to the typing import), (2)
  everything appended after the existing `return "\n".join(lines)` at the end of the
  file: a new `ArrayElement` frozen dataclass, a `_build_array_element` helper, and the
  `split_array_elements` function, each with full docstrings. Net line count: file grew
  from 540 to 839 lines (299 new lines), all from these two edits.
- `test/unit/test_rule_sort.py` -- new file, 39 tests (17 characterization tests for Part
  1 across three TestCase classes, 22 direct tests for `split_array_elements` in a fourth).

## IMPORTANT: concurrent, unrelated change observed in the same file

Partway through this session, `toolguard/rule_sort.py`'s `reassemble_permissions_section`
gained additional logic I did NOT write: an `is_synthesized = isinstance(entry, RuleEntry)
and not entry.has_raw` check plus an expanded docstring comment, guarding the "reuse
original line vs render fresh" branch. My initial full `Read` of the file at session start
did not have this code; it appeared in the working tree later, attributable to a
CONCURRENT Phase 0a increment (`has_raw` is a real, pre-existing property on `RuleEntry` in
`toolguard/rule_entry.py`, and this logic matches the Phase 0a "increment 9" design
described in the durable plan note -- "a synthesized RuleEntry from merge_entries' case-2
union-merge must not reuse stale rule_lines text"). This is NOT part of my task, I did not
introduce it, and I did not touch that region (my two edits are isolated to the import
line and everything appended after the function's `return` statement, confirmed by
re-reading the diff). Flagging this because `git diff toolguard/rule_sort.py` alone,
run at the end of my session, no longer shows ONLY my new function -- it also shows this
unrelated concurrent edit that landed in the same file mid-session. Several OTHER files
(`config_divergence.py`, `migrate_permissions.py`, `rule_apply.py`, `test_migration.py`)
show the same "MM" (staged + newly unstaged) git status pattern, consistent with another
Phase 0a session running against the same working tree concurrently with mine. Worth a
coordination check with Arnon; I made no attempt to touch or revert any of that work.

## Design: ArrayElement / split_array_elements return shape

`split_array_elements(text) -> Tuple[ArrayElement, ...]` takes the raw text between a
TOML array's `[` and `]` and returns one `ArrayElement` per top-level element, via a
single linear pass tracking quote state (`"..."` with backslash-escape awareness,
`'...'` with no escape mechanism per TOML literal-string semantics) and brace depth
(`{...}`, nested-aware), splitting only on commas at depth 0 outside any quote/comment.
Tool-name-agnostic throughout -- no `Bash(`/`Read(` enumeration.

Each `ArrayElement` has:
- `text` -- the element's own VALUE only (quoted string or `{...}` table, excluding any
  leading full-line comment block and excluding trailing same-line comment/comma).
- `leading` / `trailing` -- the raw padding before/after `text` within its segment
  (comments, blank lines, the delimiting comma). `leading + text + trailing ==
  original_text[segment_start:segment_end]` for every element (a per-element
  reconstruction invariant, directly tested).
- `start_pos`/`end_pos` (char offsets) and `start_line`/`end_line` (1-based line numbers)
  -- all for `text` specifically, not the whole segment.
- `segment_start`/`segment_end` -- char offsets of the whole segment, letting a caller
  recover any leftover text after the LAST element (`text[elements[-1].segment_end:]`)
  when the source has a trailing comment/whitespace after the final comma and before `]`.

**Why this shape serves both future call sites** (per the task spec, neither is wired in
yet):
- `annotate.py` wants to insert a new leading comment directly above an element's OWN
  first line, below any pre-existing human comment -- that's exactly `start_line`, since
  `leading` (which may itself contain a full comment block) is excluded from `text`'s own
  span. This mirrors today's single-line parser's actual behaviour (new `# toolguard:`
  comments go directly above the rule's own line, never above a pre-existing comment).
- `config_access.py` wants a trailing inline `#` comment on an element's LAST physical
  line, generalized to multi-line structured entries -- that's `end_line`/`trailing`:
  for a multi-line `{...}` table, `end_line` is the line of the closing `}`, and any
  same-line inline comment after it (before the comma) is captured in `trailing`.

A segment containing no value (whitespace/comments only) is not turned into a "phantom"
element -- covers both an empty array (`()`) and a comment-only remainder after the final
comma. This was a deliberate simplification (documented in the function's docstring):
no known future consumer needs a value-less element, and the leftover is still fully
recoverable via `segment_end` slicing.

## Bug characterized (not fixed) -- report to Arnon

`parse_permissions_section_with_comments`'s regex-based value extraction
(`r'"([^"]*)"'`) has no concept of backslash-escaping. An entry like
`"Bash(echo \"hi\")"` is truncated: the parsed pattern value comes out as `Bash(echo \`
instead of `Bash(echo "hi")` -- the regex's `[^"]*` stops at the escaped quote's own `"`
character, which it cannot distinguish from a real closing quote. Characterized in
`test_escaped_double_quote_truncates_pattern_value_NOTE_bug`. Contrast: the NEW
`split_array_elements` scanner (Part 2) correctly handles this exact case (its own test,
`test_escaped_double_quote_does_not_end_the_string_early`), so this bug is expected to be
fixed as a side effect once increment 3 (the actual rewrite, out of scope here) lands.

Also characterized (not a bug, just a documented current limitation worth knowing before
the rewrite): a freestanding blank line between two entries, with no comment adjacent to
it, is silently dropped by the current parser -- it survives neither a raw parse nor a
round trip. Only blank lines INSIDE an already-open comment buffer are preserved.

## Verification

- Full suite: `uv run python -m unittest discover -s test -t .` -- 1670 tests, OK
  (1631 baseline + 39 new). Baseline confirmed green (1631) before any edits.
- `test/unit/test_architecture.py` -- 7 tests, OK, run standalone.
- `uv run ruff check toolguard/rule_sort.py test/unit/test_rule_sort.py` -- clean.
- `uv run ruff format` run ONLY on these two touched files (not repo-wide), per project
  convention; one reformat applied to the new test file (line-wrap only).
- Anti-pattern scan on both files: no `async`/`await`, no `threading`/`Thread`, no
  imports inside function bodies. Doc comments (docstrings) on every new
  class/function/field.
- No local/circular-import issues; `dataclass`/`Optional` added at module level only.

## Reuse check (avoiding duplication)

Inventoried `rule_sort.py`'s existing helpers before adding anything new, per the task's
explicit instruction (a duplicate predicate reportedly shipped once already on this
ticket): `_escape_toml_string`, `_render_toml_key`, `_render_toml_scalar`,
`_render_toml_inline_table`, `render_toml_entry`, `_pattern_of`, `get_tool_priority` --
none overlap with a raw-text boundary scanner's job (they all operate on already-parsed
`RuleEntry`/pattern values, not on unparsed source text), so nothing was reused directly,
but nothing new duplicates them either. No existing quote/brace-depth scanner exists
anywhere else in the codebase (checked via grep for `in_quote`/`quote_char`/`brace_depth`
patterns) -- this is a genuinely new primitive, not a reimplementation.

## Anything contradicting the spec

Nothing in the task spec itself was contradicted. The one notable deviation from a
literal reading is the concurrent-edit situation described above, which affects how
cleanly `git diff toolguard/rule_sort.py` demonstrates scope -- addressed by describing
my own two edits precisely rather than relying on a single un-annotated diff.

## Timing (approximate, single session)

- Phase 1 (planning: read CLAUDE.md/addenda, memory, prior plan, target file, test
  conventions, annotate.py/config_access.py call-site shapes): ~10 minutes.
- Phase 2 (implementation: scratch-probing current behaviour, writing 39 tests, writing
  the scanner + dataclass, debugging one test-expectation mismatch): ~20 minutes.
- Phase 3 (self-review: anti-pattern scan, diff verification, discovering and
  investigating the concurrent-edit situation): ~8 minutes.
- Phase 4 (report writing, IDE handoff): ~5 minutes.
- Total: ~43 minutes elapsed.
- Estimated cost: implementation model is Sonnet 5 at typical feature-coder pricing;
  total token usage for this session (reads of large memory notes, one file rewrite, one
  new ~450-line test file, moderate tool-call volume) is roughly in the 150-250K token
  range including context, which at current Sonnet pricing is on the order of $1-2 for
  this task. Not precisely measurable from within the session; treat as a rough order of
  magnitude only.
