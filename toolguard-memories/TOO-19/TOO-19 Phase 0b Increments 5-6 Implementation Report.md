---
title: TOO-19 Phase 0b Increments 5-6 Implementation Report
type: note
permalink: toolguard/too-19/too-19-phase-0b-increments-5-6-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Final two increments of TOO-19 Phase 0b: fixing two consumers of the already-rewritten
`parse_permissions_section_with_comments` (increment 3/4) so a multi-line structured
permission entry is handled correctly.

- **Part A (`annotate.py`, increment 5): genuine bug, fixed.** A structured entry
  written across multiple physical lines never got its `# toolguard:` annotation
  comment at all (silently dropped).
- **Part B (`config_access.py`, increment 6): probed first, found ALREADY CORRECT.**
  `_inline_comment_after_pattern`/`_layer_comment_map`'s `#NOSECURITY`/inline-comment
  recovery already worked correctly for a multi-line structured entry, as a side effect
  of increment 3/4's parser rewrite. No production logic change was needed -- only a
  docstring clarification and new regression tests. This contradicts the spec's framing
  ("Adapt so that...") which implied a code change was required; see "Contradicting the
  spec" below.

## Root cause (Part A)

`_rule_line_patterns` (renamed `_rule_first_line_patterns`) built a dict keyed by a
rule's full `content` string from `parse_permissions_section_with_comments` -- for a
structured entry that content can span multiple physical lines (joined by `\n`).
`annotate_section_text` iterated `section_text.split("\n")` one PHYSICAL line at a time
and did `line_to_pattern.get(line)` -- a single physical line can never equal a
multi-line dict key, so the lookup always missed for a structured entry, and no
annotation was ever inserted for it. Confirmed via a throwaway probe script
(`/tmp/.../scratchpad/probe_part_ab.py`) before touching any code: with the OLD code,
`# toolguard:` marker present: False for a multi-line entry.

## Fix (Part A)

`toolguard/tools/annotate.py`:
- `_rule_line_patterns` renamed to `_rule_first_line_patterns` (private, only used
  internally in this file -- confirmed via grep before renaming). Now keys the map by
  `content.split("\n", 1)[0]` (the rule's own FIRST physical line) instead of the full
  `content`. For a plain single-line entry this is a no-op (`content` has no `\n`),
  so existing behaviour is byte-identical.
- `annotate_section_text`: only the call site name changed
  (`_rule_line_patterns` -> `_rule_first_line_patterns`); its per-physical-line loop
  needed NO structural change -- marker-stripping genuinely needs a per-line scan
  regardless (a stale `# toolguard:` comment is always its own standalone physical
  line), and once the lookup map is keyed by first-line text, the existing
  `line_to_pattern.get(line)` call naturally anchors the inserted comment above a
  multi-line rule's first line only, and lets every other physical line of that rule
  (and everything else in the section) pass through unchanged.
- Both functions' docstrings updated to describe first-line anchoring and multi-line
  support explicitly.

Diff shape: ~30 lines changed in one file, entirely docstring + one dict-key change +
one rename; no new imports, no new helper functions, no touch to
`annotate_config_file` or `clarity_annotations`.

I deliberately reused the EXISTING public `parse_permissions_section_with_comments`
(itself already built on `rule_sort.split_array_elements`) rather than re-deriving
subsection boundaries / re-splitting elements directly in `annotate.py`. This avoids
duplicating chunk-parsing logic that lives only in `rule_sort.py` -- the spec's own
"a duplicate predicate has already shipped once on this ticket" warning. The one-line
key change is the entire architectural delta; `split_array_elements` is reached
transitively via the existing parser, not re-invoked ad hoc.

## Part B: probe findings and why no code change was needed

Wrote `/tmp/.../scratchpad/probe_part_ab.py` and ran it BEFORE editing `config_access.py`
to check `_inline_comment_after_pattern`'s behaviour on a real multi-line structured
entry. Findings:
- `_layer_comment_map` already calls `_inline_comment_after_pattern(content)` with the
  FULL (possibly multi-line) `content` string directly -- it is never split into
  physical lines first.
- `str.rfind` and slicing operate on the whole string ignoring embedded `\n`, so the
  existing "find the last quote, then look for `#` after it" logic already finds a
  multi-line structured entry's trailing comment correctly (it lands on whichever
  physical line the entry's own last quoted/closing token is on, which is exactly where
  the trailing comment actually sits).
- Confirmed empirically (see probe output) for: a two-line entry with a trailing
  `# comment`; a two-line entry with `additionalContext = "see issue #42"` and no real
  trailing comment (correctly returns `""`, i.e. the embedded `#` is never
  mis-detected); and a single-line inline-table entry with a trailing
  `# NOSECURITY: dev`.

I then wrote the RED tests first anyway (per the strict red-green-refactor instruction)
and ran them against the untouched code -- they passed immediately (green on the first
run), confirming the probe's finding rather than assuming it. No production code change
was made to the actual comment-extraction/NOSECURITY logic. The only change to
`config_access.py` is a docstring clarification on `_inline_comment_after_pattern`
(renamed nothing, changed no logic) explicitly documenting that *line* is really a
rule's full (possibly multi-line) source span and that this is already handled
correctly -- since the previous docstring's "the last quote character on the line"
phrasing undersold/obscured that fact.

Diff shape: docstring-only change to one function in one file (plus tests). All other
`config_access.py` diff noise visible via `git diff` predates this session (Phase 0a /
0b increments 1-4 are uncommitted in the working tree already -- confirmed via
`git log`/`git status`; e.g. the `with_layer_rules_replaced` `dataclasses.replace` +
`normalize_entry` fix and various signature reformatting were already present before I
touched anything). Isolated my own diff with
`git diff toolguard/tools/config_access.py | grep -A25 _inline_comment_after_pattern`
to confirm exactly one docstring hunk is mine.

## Files changed

- `toolguard/tools/annotate.py` -- real fix (Part A)
- `toolguard/tools/config_access.py` -- docstring only (Part B)
- `test/unit/test_tools_annotate.py` -- 3 new tests added (new class
  `TestAnnotateSectionTextMultilineEntry`), 0 existing tests modified
- `test/unit/test_tools_config_access.py` -- 5 new tests added (new class
  `TestRuleCommentExposureStructuredEntries`), 0 existing tests modified

## Test results

- Baseline at session start: `uv run python -m unittest discover -s test -t .` ->
  1677 tests, OK (re-confirmed before any edit).
- After Part A (3 new tests): 1680 tests, OK.
- After Part B (5 new tests): 1685 tests, OK.
- `test/unit/test_architecture.py`: 7 tests, OK.
- `uv run ruff check` on all 4 touched files: All checks passed.
- `uv run ruff format --diff` on all 4 touched files: the only remaining hunks are in
  PRE-EXISTING lines I never touched (confirmed line-by-line); zero hunks remain in any
  line I added or edited. This project has an unconfigured line-length convention (no
  `[tool.ruff]` in `pyproject.toml`) that causes `ruff format` to want to reformat much
  pre-existing code -- per prior project memory this is known diff-pollution, so I
  manually wrapped only the 2 lines I personally added that exceeded 88 columns,
  matching ruff's own suggested wrapping for those specific lines, rather than running a
  blanket format.
- Anti-pattern scan (`async def`, `await`, `threading`, `Thread(`, local imports) on all
  4 touched files: zero hits.

## Confirmations requested by the spec

1. **Multi-line structured entry gets exactly one annotation, above its first line**:
   confirmed by `test_multiline_entry_gets_exactly_one_note_above_its_first_line` (also
   asserts the SECOND physical line of the same entry has no marker) and
   `test_multiline_entry_annotation_is_idempotent`.
2. **`#` inside a quoted string is never treated as a comment**: confirmed for both
   single-line and multi-line structured entries by
   `test_hash_inside_single_line_structured_value_is_not_an_inline_comment` and
   `test_hash_inside_multiline_structured_value_is_not_an_inline_comment` (both assert
   `nosecurity_reason_for(...)` returns `None` when the only `#` present is inside a
   quoted `additionalContext` value with no real trailing comment). Tested via a real
   temp TOML file + the public `nosecurity_reason_for` function end-to-end, matching the
   existing test file's established style (mirrors the pre-existing
   `test_hash_inside_regex_pattern_is_not_an_inline_comment` for the plain-pattern case).
3. **Neither existing test file needed modification**: confirmed -- both files only
   received new test classes appended after the existing content; zero lines of
   pre-existing test code were changed.
4. **Anything contradicting the spec**: Part B's framing ("Adapt so that a multi-line
   chunk's trailing inline comment ... is found correctly") implied a code change was
   required. The actual finding, verified empirically before touching any code, is that
   this already worked correctly as an unplanned side effect of increment 3/4's parser
   rewrite (`_inline_comment_after_pattern` was already being called with the full,
   possibly multi-line `content` string, and Python's `rfind`/slicing are inherently
   newline-agnostic). I made a docstring-only change plus new tests rather than a
   functional change, and flagged this explicitly rather than inventing an unnecessary
   code change to match the spec's framing.

## Time/cost estimate

- Planning (read rule_sort.py/annotate.py/config_access.py/test files, probe script,
  memory writes): ~12 min, ~$0.35
- Implementation (Part A fix + tests, Part B tests + docstring, ruff wrapping): ~10 min,
  ~$0.30
- Self-review (full suite runs, architecture test, diff isolation, ruff check/format
  verification): ~4 min, ~$0.10
- Total: ~26 min, ~$0.75 (rough estimate based on Sonnet 5 token pricing and this
  session's tool-call volume; no extended thinking blocks beyond planning)
