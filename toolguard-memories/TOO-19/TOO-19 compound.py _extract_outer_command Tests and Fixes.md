---
title: TOO-19 compound.py _extract_outer_command Tests and Fixes
type: note
permalink: toolguard/too-19/too-19-compound-extract-outer-command-tests-and-fixes
tags: [TOO-19, task-memory]
---

# TOO-19: `_extract_outer_command` characterization tests and bug fixes

## Summary

`toolguard/compound.py::_extract_outer_command` had zero direct test coverage.
Added 16 new unit tests in `test/unit/test_compound.py` (three new test
classes) that pin its behaviour, exposed 4 real failures, fixed the two
underlying bugs, and added a separate display-bounding step so the ASK-floor
reason string shown at the permission prompt (`compound.py:71`, now inside
`_resolve_leaf`) can never be an unbounded blob.

## Baseline

`uv run python -m unittest discover -s test -t .` -> **1795 tests, OK** (confirmed
before any change).

## Task 1: characterization tests, run before fixing

Added `TestExtractOuterCommand` (9 tests) calling `_extract_outer_command`
directly. Ran the new tests against the *unmodified* function first.

**Failures observed (the real bug inventory) -- 4 of 9 new characterization
tests failed:**

1. `test_attached_flag_single_quote_no_space` -- `python -c'import os'` ->
   returned the whole string instead of `python -c`.
2. `test_attached_flag_no_quote_no_space` -- `python -cimport os` -> returned
   the whole string instead of `python -c`.
3. `test_combined_short_flags` -- `python -uc "code"` -> returned the whole
   string instead of `python -uc`.

**Passed as-is (not bugs):** plain `-c "code"` (space-separated), heredoc
sentinel form, multiline `-c` argument (no embedded newline -- this guarantee
already held because `.split()`/`.join()` collapse whitespace regardless of
where the loop breaks), `-e`, `-r`, and the no-inline-flag fallback case (my
initial assertions there were loose -- see "What I verified vs. speculated"
below).

A 4th test failed but belongs to Task 3, not Task 1: `test_long_inline_code_
is_truncated_with_marker` in `TestAskFloorReasonTruncation` failed against the
unmodified code because no truncation existed yet at all (expected -- this is
the pre-fix baseline for the display-bounding gap, confirmed separately from
the outer-command-extraction bugs above).

So: **the ticket's bug hypothesis (a) was fully confirmed** -- all three
attached/combined-flag forms were broken exactly as suspected. **Bug (b)
(unbounded fallback) was confirmed as a display-only problem, not a
newline-safety problem** -- see below.

## What I verified vs. speculated

- The ticket's concern that the unbounded fallback could let an embedded
  newline through the outer-command stub does **not** actually happen: the
  function already tokenizes via `str.split()` and rejoins via `" ".join()`,
  which collapses all whitespace (including newlines) unconditionally, on
  every code path, independent of where/whether the loop breaks. I wrote
  `test_multiline_inline_code_has_no_embedded_newline` and it passed even
  pre-fix. I kept the test (it is still a real guarantee worth pinning) but
  corrected my own initial assumption before reporting it as a "confirmed
  bug" -- it isn't one.
- The real problem with the unbounded fallback is purely **verbosity/length**
  for display (and, in principle, for whatever `resolve_one` does with a very
  long string), which Task 3's truncation step addresses directly.
- I also checked whether the attached/combined-flag forms can currently even
  reach `_extract_outer_command` in production: `_detect_foreign_inline_code`
  in `command_extractor.py` only sets `ask_floor=True` when the flag token is
  an **exact** match against a per-executor list (e.g. `["-c"]` for python) --
  so `-uc`/`-cimport`/`-c'code'` do not currently trigger the ASK floor at all
  upstream. The fix in `_extract_outer_command` is still correct and worth
  having (defense-in-depth, future-proofing, and the ticket explicitly asked
  for it, tested directly against the function), but I want to flag clearly
  that today's upstream detection is stricter than the forms this ticket
  worried about, so the practical blast radius of the pre-fix bug was smaller
  than it might look from `_extract_outer_command` alone. Noting this for the
  record rather than silently omitting it.

## Task 2: fixes

### (a) Attached/combined inline-flag forms

Replaced the token-equality check (`tok in ("-c", "-e", "-r")`) with a regex,
`_INLINE_FLAG_TOKEN_RE = re.compile(r"^-([a-zA-Z]{0,2})([cer])(.*)$")`, which
recognizes:
- a bundle of 0-2 other short-flag letters before the inline-code letter
  (covers `-uc`), and
- an optional attached remainder after the inline-code letter (covers
  `-cimport`, `-c'code'`).

The `{0,2}` bound on the bundle prefix is deliberate: it lets realistic
combined short flags (`-uc`) match while rejecting unrelated word-like
single-dash flags whose prefix before a trailing c/e/r would be longer (e.g.
`-name`, `-recurse`, `-force`, `-verbose` all fail to match because their
letter-run before the final c/e/r exceeds 2 characters). This was verified by
walking the regex backtracking by hand for `-name` -- documented in the code
comment for the constant.

When the match has an attached remainder, the stub is emitted immediately
(`-{bundle}{flag_letter}`) regardless of what follows. When there's no
attached remainder (bare `-c`/`-uc`), the original semantics are preserved:
only stop if a following token exists (else keep scanning, unchanged from
before).

### (b) Unbounded fallback -- resolved via separation of concerns, not truncation-in-place

Per the ticket's suggested resolution when matching-completeness and
display-safety are in tension, I kept `_extract_outer_command`'s return value
**untruncated** (it is still used to check for explicit denies via
`resolve_one`), and added a **separate** function, `_truncate_for_display`,
applied only at the one place the string is rendered into a user-visible
reason (inside `_resolve_leaf`, the code that used to be at line 71). This
means:
- Matching (`resolve_one(outer_cmd)`) always sees the full, non-truncated
  outer-command stub -- no deny pattern can be defeated by shortening.
- Display (`f"ASK floor applied ...: {display_cmd}"`) always sees a bounded,
  single-line string.

### Deny-still-fires verification (explicit ask)

Added `TestExtractOuterCommandDenyStillFires` (4 tests) that go through
`_resolve_leaf` (not just `_extract_outer_command`) with a real
`check_permission`-backed `resolve_one` closure and confirm an explicit deny
still fires for: the attached-no-quote form, the space-separated form, and
the combined-short-flags form; plus one control test confirming a plain allow
is still clamped to `ask` (not weakened to `allow`). All 4 pass with the fix
in place.

## Task 3: bounding the display string

Added `_truncate_for_display(cmd, max_len=120)`:
- Collapses whitespace (defense in depth; `_extract_outer_command`'s output
  is already newline-free, but this makes the guarantee independent of the
  caller).
- If the string exceeds 120 characters, truncates and appends
  `" ...[truncated]"` (visible ellipsis marker, keeps the leading
  executor/flag portion visible).
- `_MAX_DISPLAY_COMMAND_LEN = 120` is a module-level constant with a
  docstring pointing at the call site.

Added `TestAskFloorReasonTruncation` (3 tests):
- A leaf with **no** recognizable inline flag or heredoc sentinel (the
  unbounded-fallback path) and a very long body -> reason is truncated with
  `...` and stays under 300 chars, executor name still visible.
- A short command -> reason unchanged, no ellipsis.
- A long multi-line inline-code payload -> reason has no embedded newline.

Note: my first draft of the "long command is truncated" test used
`python -c "<500 x's>"` (space-separated, i.e. the already-fixed case from
Task 2a) and it **failed** to exercise truncation at all, because
`_extract_outer_command` now correctly bounds that case to `python -c` before
truncation is even needed. I caught this by running the test and seeing it
fail for the wrong reason, and corrected it to use a leaf with no recognizable
flag/sentinel (the genuine unbounded-fallback scenario truncation exists to
guard).

## Test results

- New tests added: 16 (`TestExtractOuterCommand`: 9, `TestExtractOuterCommand
  DenyStillFires`: 4, `TestAskFloorReasonTruncation`: 3).
- Full suite after fix: `uv run python -m unittest discover -s test -t .` ->
  **1811 tests, OK** (1795 baseline + 16 new).
- `uv run ruff check .` -> all checks passed.
- `uv run ruff format toolguard/compound.py test/unit/test_compound.py` ->
  1 file reformatted (`compound.py`; the test file was already
  ruff-format-clean). Ran only on the two touched files, never a bare
  `ruff format .`.
- `uv run python -m py_compile toolguard/compound.py test/unit/test_compound.py`
  -> OK.
- Anti-pattern scan of both changed files: no `async`/`await`, no
  `threading`/`Thread`, no local (in-function) imports.

## Files changed

- `toolguard/compound.py` -- fixed `_extract_outer_command` (attached/combined
  inline-flag recognition), added `_truncate_for_display` and
  `_MAX_DISPLAY_COMMAND_LEN`/`_INLINE_FLAG_TOKEN_RE` module constants, updated
  `_resolve_leaf` to bound the ASK-floor reason string, updated docstrings to
  match (including the module-docstring cross-reference at `_resolve_leaf`,
  which already described the outer-command-stub behaviour accurately and did
  not need a wording change beyond what's inline above).
- `test/unit/test_compound.py` -- added imports for `_extract_outer_command`,
  `_resolve_leaf`, `LeafCommand`, `check_permission`; added the three new test
  classes described above (16 tests total).

No other files were changed.

## Safety confirmation

- No live configuration was touched: no edits to any
  `.claude/toolguard_hook.toml`, `.claude/settings.json`,
  `.claude/settings.local.json`, or anything under `~/.toolguard/` or
  `~/.config/toolguard/`.
- No ad-hoc `python -c` / heredoc probe scripts were run. All validation was
  via `uv run python -m unittest` against `test/unit/test_compound.py` (and
  the full suite), which is pure string-in/string-out and fully exercised the
  change.
- No write git operations were run (only `git status`/`git diff` for
  read-only inspection).
- Pre-existing nested `toolguard-memories/toolguard-memories/` and
  `toolguard-memories/toolguard/` directories were confirmed to already exist
  before this session (dated 2026-07-26/27, from earlier ticket work) --
  I did not create any new nested memory directory. This report was written
  directly to the exact path specified in the task instructions.

## Elapsed time and rough cost estimate

- Phase 1 (planning/reading): ~3 min, ~$0.05
- Phase 2 (implementation: tests + fix, iterative runs): ~9 min, ~$0.20
- Phase 3 (self-review, ruff, re-run suite): ~3 min, ~$0.05
- Phase 4 (this report): ~2 min, ~$0.03
- **Total: ~17 min, ~$0.33** (rough token-based estimate for a Sonnet-class
  model at this session's context size; not a precise billing figure).
