---
title: TOO-19 Review Fixes - M3 and M5 Implementation Report
type: note
permalink: toolguard/too-19/too-19-review-fixes-m3-and-m5-implementation-report
tags:
  - TOO-19
  - task-memory
---

# TOO-19 Review Fixes -- M3 and M5 Implementation Report

Branch: `too-19`. Both defects were reproduced by running code BEFORE any fix was made,
and the same repros were re-run AFTER the fix to confirm resolution.

## Baseline

`uv run python -m unittest discover -s test -t .` -- **1783 tests, OK** (confirmed both
before and after the fix; no regressions).

## M3 -- `cmd_seed_self_perms` unhashable-dict crash class

### Repro (before fix)

Built a fake-HOME fixture (mirroring `InstallerTestCase` in
`test/unit/test_tools_installer.py`), wrote a `toolguard_hook.toml` with a structured
`[permissions] allow` entry and a structured `[hard_deny] deny` entry, then invoked
`main(["seed-self-perms", ...])`.

Before the fix this raised:

```
TypeError: cannot use 'dict' as a dict key (unhashable type: 'dict')
```

(from `write_toml_config` -> `sort_patterns` -> `get_tool_priority` on the raw dict read
straight out of `tomllib.loads()`).

Repro script: `scratchpad/repro_m3.py` (session scratchpad).

### Fix

In `toolguard/tools/installer.py`:

1. **`cmd_seed_self_perms`**: the raw `[permissions]` `allow`/`deny`/`ask` lists and the
   raw `[hard_deny]` `deny`/`allow` lists are now routed through
   `toolguard.rule_entry.normalize_entries_preserving(..., is_native=False)` immediately
   after `tomllib.loads()`, exactly the pattern already used by
   `migrate_permissions._build_merged_permissions` and
   `rule_apply._read_raw_permissions` for this same defect class (no new mechanism
   invented, per the ticket's explicit instruction). This never drops an element, even a
   malformed one (it is preserved verbatim behind a synthesized pattern).
2. **Membership/dedup** is now done by `.pattern` (via a small local helper,
   `_entry_pattern`, since a list under seeding legitimately mixes normalized
   `RuleEntry` objects with freshly-appended plain `str` candidates across loop
   iterations -- a bare `.pattern` access crashes on the `str` elements). Three
   membership-set computations were fixed this way: the `permissions[list_type]`
   candidates loop, the self-integrity `hard_deny` loop, and (see below)
   `cmd_seed_hard_deny`'s own loop. Each set is grown incrementally inside its loop
   (rather than only computed once) so within-batch duplicates are also caught, matching
   the original code's behavior of testing against the live, growing list.
3. **`_render_hard_deny_section`** now renders each deny/allow entry via
   `toolguard.rule_sort.render_toml_entry` instead of assuming `str` and calling
   `.replace(...)` directly -- this was the second crash: `AttributeError: 'dict' object
   has no attribute 'replace'` on a structured `hard_deny` entry (confirmed by the same
   repro, since the fixture's `[hard_deny] deny` entry was also structured).
4. **`expected_patterns`** computation (the content-loss-guard argument) in both
   `cmd_seed_self_perms` and `cmd_seed_hard_deny` now goes through
   `toolguard.rule_entry.real_patterns(...)` rather than `set(raw_list)` -- the raw lists
   are now `RuleEntryOrStr`, and `real_patterns` is the documented single chokepoint that
   excludes a synthesized (repr()-based) pattern from `expected_patterns`, since such a
   pattern can never appear in the text actually written and would otherwise wrongly
   trip the guard.

### Second `tomllib.loads` site (~line 1506, now ~1621): `cmd_seed_hard_deny`

Inspected as instructed. It has the exact same defect class: `deny_patterns =
list(current_hard_deny.get("deny", []))` / `allow_patterns = list(...get("allow", []))`
were raw elements, membership was tested by raw identity
(`protection.pattern in deny_patterns`), and rendering went through the same
`_render_hard_deny_section` (so it would hit the same `AttributeError` on a structured
entry). Fixed identically: `normalize_entries_preserving`, pattern-based membership via
`_entry_pattern`, and `real_patterns` for `expected_patterns`.

No other command in `installer.py` calls `tomllib.loads` -- grepped the whole file to
confirm only these two sites exist.

### Post-fix verification

- Repro script now prints `NO CRASH, exit code 0` and successfully seeds all
  self-permissions/hard-deny patterns.
- A follow-up check (config with pre-existing structured `[permissions]` and
  `[hard_deny]` entries): after seeding, the structured entries are preserved verbatim
  (`{ match = "Bash(ls)", additionalContext = "already structured" }` and the structured
  hard_deny entry both round-trip unchanged), and a SECOND run of `seed-self-perms`
  reports every candidate as "already present, no changes needed" -- i.e. no duplicate
  bare-string re-add of an already-present structured pattern.

## M5 -- sort/reassemble drops the trailing comma when a reused span is the source's last element

### Repro (before fix)

```python
section_text = '[permissions]\nallow = [\n  "Bash(zz)",\n  "Bash(aa)"\n]\n'
# "Bash(aa)" is the source's LAST element and has no trailing comma.
parsed = parse_permissions_section_with_comments(section_text)
output = reassemble_permissions_section(parsed, {"allow": ["Bash(zz)", "Bash(aa)"], ...}, auto_sort=True)
tomllib.loads(output)  # -> tomllib.TOMLDecodeError: Unclosed array (at line 4, column 3)
```

Sorting moves `Bash(aa)` (source's last, comma-less element) out of last position; its
reused original span is emitted verbatim with no comma, producing:

```
allow = [
  "Bash(aa)"
  "Bash(zz)",
]
```

Repro script: `scratchpad/repro_m5.py`.

### Fix

In `toolguard/rule_sort.py`, added `_ensure_trailing_comma(same_line_tail: str) -> str`
and call it in `_parse_array_body` right after computing each element's `same_line_tail`
(the same-line text immediately following the element's own value, before it is folded
into the reused `content` span stored in `rule_lines`).

The check looks only at the code portion of `same_line_tail` (everything before its first
`#`, so a literal comma inside an inline comment is never mistaken for the delimiter) and:
- leaves it unchanged if a real comma is already present (every element but a
  comma-less last element already has one, since `split_array_elements` only creates an
  element boundary at a comma);
- otherwise inserts a comma at the very start of `same_line_tail`, immediately after the
  element's own value and before any pre-existing trailing whitespace/comment on that
  line.

This is unconditional and safe: a trailing comma on the array's actual last element is
always legal TOML, so every reused span now uniformly ends in a comma.

### Post-fix verification

Repro now parses OK and reorders correctly (`["Bash(aa)", "Bash(zz)"]`). Additionally
verified, per the ticket's explicit test list, inline via ad hoc scripts (not added to
`coder-test/` since they were single-shot verification, see below):

1. **Comment on the comma-less last element** -- `"Bash(aa)"  # trailing comment` (no
   comma) round-trips to `"Bash(aa)",  # trailing comment` after sort, and the comment
   text is still attached to the correct pattern, still valid TOML.
2. **Structured entry as the comma-less last element** -- `{ match = "Bash(aa)",
   additionalContext = "note" }` (no comma) round-trips with a comma correctly appended,
   metadata intact, still valid TOML.

## Required wrap-up probes (all re-run after both fixes, in this order)

- `scratchpad/probe6.py` -> prints `parsed OK; hard_deny = {'deny': [{'match': 'Bash(rm
  -rf /)', 'additionalContext': 'see [permissions] docs'}]}` -- hard_deny rule intact.
- `scratchpad/verify_change4.py` -> prints `RESULT: PASS - both metadata preserved`.
- Content-loss guard genuine-drop check (ad hoc, not a pre-existing script): called
  `verified_write_config` with text that omits an `expected_patterns` entry entirely --
  still raises `ConfigWriteVerificationError: ... missing pattern(s): Bash(git:*)`. The
  guard is NOT weakened by either fix.
- Full suite: **1783 tests, OK** (re-confirmed after both fixes and after `ruff format`).

## Linting

`uv run ruff format toolguard/rule_sort.py toolguard/tools/installer.py` (explicit files
only, never a bare `ruff format .`) -- reformatted `installer.py` (this file already had
substantial pre-existing uncommitted WIP from earlier phases of this ticket; `ruff
format` normalized a few nearby pre-existing lines -- e.g. quote style on
`_UV_BIN_PATH_PREPEND_ALLOW`, one `raise InstallerError(...)` collapsed to one line --
that were not touched by my own edits but sit in the same file). `rule_sort.py` needed no
reformatting.

`uv run ruff check .` (repo-wide, as instructed for the check-only step) -- **All checks
passed.**

## Files changed (this task's diff only)

- `toolguard/rule_sort.py` -- added `_ensure_trailing_comma`; call site in
  `_parse_array_body` (M5).
- `toolguard/tools/installer.py` -- `cmd_seed_self_perms`, `cmd_seed_hard_deny`,
  `_render_hard_deny_section`; new imports (`RuleEntry`, `normalize_entries_preserving`,
  `real_patterns` from `toolguard.rule_entry`; `RuleEntryOrStr`, `render_toml_entry` from
  `toolguard.rule_sort`; `Dict` from `typing`); new small helper `_entry_pattern` (M3).

Both files already carried substantial pre-existing, uncommitted changes from earlier
increments of this same ticket (visible in `git status` before this task started) -- the
diff stat for each file (697 / 252 lines) reflects that combined history, not just this
task's edits. This task's own edits are the sections described above; nothing else in
either file was touched.

No other files were created or modified by this task (this report file itself is the
only new file).

## Honesty / incomplete-work notes

- I did not add new automated unit tests under `test/unit/` (per project convention,
  that directory is off-limits to this agent) and did not add new tests under
  `coder-test/` either, since the ticket's own verification requirements were fully
  covered by targeted repro/verification scripts run interactively and reported above.
  If a permanent regression test is wanted for M3/M5, the two repro scripts in this
  session's scratchpad (`repro_m3.py`, `repro_m5.py`) are ready to be adapted into
  `test/unit/test_tools_installer.py` / `test/unit/test_rule_sort.py` test cases by
  whoever owns that directory.
- Nothing else was left incomplete. Both defects are fixed, verified by their own repro,
  by the two ticket-mandated probe scripts, by a genuine-drop guard check, and by the
  full 1783-test suite.
