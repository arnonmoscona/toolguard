---
title: TOO-19 Phase 0b Increments 3-4 Implementation Report
type: note
permalink: toolguard/too-19/too-19-phase-0b-increments-3-4-implementation-report
tags:
- TOO-19
- task-memory
- implementation
---

## Summary

Implemented TOO-19 Phase 0b increments 3 and 4 on branch `too-19`:

- **Part A (increment 3):** rewrote `parse_permissions_section_with_comments` in
  `toolguard/rule_sort.py` on top of `split_array_elements` (landed in increment 2, unused
  until now) and stdlib `tomllib`, replacing the hand-rolled one-pattern-per-physical-line
  regex scanner.
- **Part B (increment 4):** verified (via new tests, written first per red-green-refactor)
  that `reassemble_permissions_section` needed **zero production-code changes** to satisfy
  the byte-identical multi-line round-trip requirement -- it already worked generically once
  fed correct multi-line content by the Part A parser.

Files touched: `toolguard/rule_sort.py` (rewritten/extended), `test/unit/test_rule_sort.py`
(new tests + one rename). No other files modified. Full suite: 1677 tests green (1670
baseline + 7 net new). `ruff check .` clean repo-wide; `ruff format` run on only the two
touched files.

## Diff shape per part

**Part A:** replaced the ~126-line line-by-line scanner inside
`parse_permissions_section_with_comments` with:
- `_find_array_close` -- quote/depth-aware scanner locating a `[`'s matching `]` (mirrors
  `split_array_elements`'s own quote/comment rules).
- `_flatten_inline_table` -- collapses a multi-line `{...}` chunk to a single TOML-1.0-legal
  line (see "Deviation" below).
- `_toml_value_of_chunk` -- wraps one element's text as `x = [ <chunk> ]` and parses with
  `tomllib.loads`.
- `_flush_comment_lines` -- ports the old buffer-accumulation rule (comment lines always
  kept; blank lines kept only once the buffer is non-empty) to operate on an arbitrary list
  of candidate lines instead of a live line-by-line scan.
- `_rule_pattern_of_value` -- extracts the pattern string from a parsed value (the value
  itself for a plain string; the `PATTERN_KEY` ("match") field for a dict).
- `_locate_subsection` / `_parse_array_body` -- split what was one function into "find this
  subsection's `[`...`]` span" and "parse the elements inside it", so the outer orchestrator
  (below) can compute inter-subsection gaps without re-scanning.
- `_trailing_comment_source_lines` -- drops the one spurious empty split-token a trailing
  `\n` produces, shared by three "process a whole comment/blank span" call sites (array
  bottom, comment-only empty array, inter-subsection gap).
- `parse_permissions_section_with_comments` itself is now a thin orchestrator: locates all
  three subsections (wherever they appear, in TEXT order, not fixed `allow`/`deny`/`ask`
  enumeration order), and for each one, computes the "gap" comment between it and the
  previous subsection's close (or start of the section) before delegating to
  `_parse_array_body`.

**Part B:** `reassemble_permissions_section`'s code is UNCHANGED. Only its docstring was
tightened (see below). Tests written first (headline byte-identical round trip for a
multi-line structured entry with leading+trailing comments) failed for the right reason
against the OLD parser (which cannot produce multi-line `rule` content at all), and passed
immediately once Part A landed, with zero further code changes needed.

## Byte-identical round trip confirmation

`test_round_trip_byte_identical_for_unchanged_multiline_structured_entry` in
`test/unit/test_rule_sort.py` (class `TestReassemblePermissionsSectionRoundTrip`) is the
headline test. It parses this text:

```
[permissions]
allow = [
  # about the structured rule
  {
    match = "Bash(git status)",
    additionalContext = "read-only",
  },  # trailing note
]
```

builds a `RuleEntry(pattern="Bash(git status)", metadata={"additionalContext": "read-only"},
raw={...})` (i.e. `has_raw` True -- nothing changed), reassembles with `new_permissions =
{"allow": [entry], ...}`, and asserts `reassembled == text` exactly (full string equality,
not a substring check). Three more tests cover: sort-and-reassemble reordering a multi-line
entry while preserving it verbatim; a trailing inline comment surviving on the entry's own
last line; and a neighbouring plain entry's removal leaving the structured entry's block
byte-identical. All four pass.

## Return shape compatibility for annotate.py / config_access.py

Unchanged: `parse_permissions_section_with_comments` still returns
`Dict[str, List[Tuple[item_type, content, parsed_value]]]` with the same `'comment_block'`/
`'rule'` item types. Grepped `test_tools_annotate.py` and `test_tools_config_access.py` for
any structured-entry fixture -- none exist, so both files' existing coverage is entirely
plain-string entries, which parse identically to before. Full suite run confirms both test
files pass **unmodified**. `content` for a multi-line structured `rule` item now legitimately
contains embedded `\n` characters (a new possibility the old parser could never produce);
neither consumer was exercised against that shape by any existing test, and per the task
this is explicitly out of scope for this increment.

## Characterization tests: what changed and why

Of the 17 original characterization tests in `TestParsePermissionsSectionWithComments`, 16
pass completely unmodified. The 17th,
`test_escaped_double_quote_truncates_pattern_value_NOTE_bug`, was renamed to
`test_escaped_double_quote_no_longer_truncates_pattern_value` and its assertion flipped from
the truncated value (`'Bash(echo \\'`) to the correct one (`'Bash(echo "hi")'`), per the
ticket's explicit mandate: "This intentionally FIXES a bug... Update that test to assert the
corrected behaviour and rename it." This is the only test-file change to previously-existing
test content; every other new/changed test is net-new.

## A regression I found and fixed (not anticipated by the ticket spec)

Running the full suite after the initial Part A rewrite surfaced ONE real failure outside
`test_rule_sort.py`: `test_migration.py::TestCommentPreservation::test_preserves_top_of_section_comments`.
That test has a comment block sitting BETWEEN the `[permissions]` header and `allow = [`
(i.e. OUTSIDE any array's own brackets) -- something my first cut of the rewrite, which only
looked inside each subsection's own `[`...`]` span, silently dropped. The old line-by-line
parser handled this via one GLOBAL comment buffer spanning the whole section text, flushing
whatever was pending to whichever subsection came next.

Since `test_migration.py` is off-limits to modify, I fixed this in production code: the
orchestrator now locates all three subsections by their actual text position (not fixed
enumeration order) and computes the "gap" text between each pair of adjacent subsections
(or from the section start to the first one), attaching any comment found there as a leading
`comment_block` for the FOLLOWING subsection -- exactly mirroring the old parser's semantics.
Verified against `test_preserves_bottom_of_section_comments` (comment INSIDE the array, was
already correctly handled) and all other `TestCommentPreservation` tests, all still pass.
Full suite confirms 1677/1677 green including this fix.

## Deviation from the literal spec text (reported, as required)

The task said: "wrap the chunk as `x = [ <chunk> ]`, parse with `tomllib.loads`... This works
uniformly for a plain string and for a structured inline table." Verified empirically (see
task recall memory) that this is **not literally true**: stdlib `tomllib` implements TOML
1.0, which requires an inline table on a single physical line with no trailing comma --
both violated by this project's own multi-line, trailing-comma authoring style (see
`split_array_elements`'s own `test_multiline_structured_entry_spans_correct_line_range`).
Confirmed both restrictions raise `tomllib.TOMLDecodeError` via a real script run in the
scratchpad before writing any production code.

Resolution (documented in `_flatten_inline_table`'s docstring): for a `{`-prefixed chunk
only, collapse internal newlines to spaces and strip one trailing comma before the closing
`}`, before handing it to `tomllib.loads`. A plain quoted string needs no normalization
(TOML strings without triple-quote syntax cannot span lines). This is necessary for the
ticket's own explicit multi-line-structured-entry requirement to be satisfiable at all with
stdlib `tomllib` -- there is no way to honor both "use tomllib" and "support this project's
existing multi-line/trailing-comma authoring style" without it.

## Other reported items

- **Dead/untested legacy path dropped:** the old parser recognized an alternate
  `[permissions.allow]` TOML-header subsection form via a dedicated regex branch, documented
  in its own docstring as "reserved, not currently emitted." Grepped the entire repo (source
  and tests) -- zero real usage or test coverage anywhere. The rewrite only recognizes the
  actually-used `allow = [` / `deny = [` / `ask = [` assignment form. Reported per the
  ticket's own framing of this as acceptable ("out of scope" territory), not silently
  dropped.
- **Doc-drift sweep:** found and fixed several stale docstrings/comments left over from
  increment 2 that described `split_array_elements` as "NOT WIRED INTO ANYTHING YET" (module
  docstring in `test_rule_sort.py`, a banner comment in `rule_sort.py`, and two test class
  docstrings) -- all now describe the increment-3 wiring. Also renamed `_bottom_comment_lines`
  to `_trailing_comment_source_lines` once it gained a third call site (the inter-subsection
  gap) that isn't really "bottom of anything."

## Self-review results

- `uv run ruff format toolguard/rule_sort.py test/unit/test_rule_sort.py` -- clean (ran
  twice; one run reformatted a single over-long line the first time through, re-verified
  clean after).
- `uv run ruff check .` -- clean, whole repo.
- `uv run python -m py_compile` on both touched files -- clean.
- Anti-pattern scan (`async def`/`await`/`threading`/`Thread(`/indented `import`) -- zero
  hits in either touched file.
- `uv run python -m unittest discover -s test -t .` -- 1677 tests, 0 failures/errors.
- `test/unit/test_architecture.py` -- green (ran standalone and as part of the full suite).
- Scope: exactly 2 files touched (1 modified, 1 new) -- well within the scope-inflation
  guardrails.

## Elapsed time / cost estimate (rough)

- Phase 1 (planning, reading rule_sort.py/rule_entry.py/consumers/test conventions,
  empirically verifying the tomllib multi-line/trailing-comma restriction before writing any
  code): ~45 min.
- Phase 2 (implementation: Part A tests-first, Part A production code, Part B tests-first,
  discovering + fixing the gap-comment regression, doc-drift sweep): ~50 min.
- Phase 3 (self-review: ruff, anti-pattern scan, full-suite reruns, docstring accuracy
  pass): ~15 min.
- Phase 4 (this report, memory writes, IDE open): ~5 min.
- Total: roughly 1h55m of wall time this session. Cost estimate (Sonnet-class model,
  moderate tool-call volume, ~2 full-suite reruns and several targeted reruns, no large file
  dumps): very roughly $3-5 in API terms -- this is a coarse estimate, not a billed figure.
