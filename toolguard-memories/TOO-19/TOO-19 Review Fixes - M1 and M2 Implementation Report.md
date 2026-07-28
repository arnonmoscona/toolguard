---
title: TOO-19 Review Fixes - M1 and M2 Implementation Report
type: note
permalink: toolguard/too-19/too-19-review-fixes-m1-and-m2-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Fixed both Major code-review findings on branch too-19.

### M1: silent trailing-comment loss on write-back (toolguard/rule_sort.py)

`parse_permissions_section_with_comments` only captured comment/gap text BETWEEN
subsections; anything after the FINAL `]` in `[permissions]` (e.g. a comment
explaining a following `[hard_deny]` section) was silently dropped on write-back,
and the write guard (pattern-based) never caught it.

Fix: after the per-subsection loop, the remaining `section_text[prev_end:]` is
captured as `result["trailing_comment"]` (`None` if empty/whitespace-only), and
`reassemble_permissions_section` appends it verbatim as the final line if truthy.

Key design decision, verified by hand-tracing: the new call site does NOT reuse
`_trailing_comment_source_lines` (which drops one trailing split artifact on the
assumption a FOLLOWING known token supplies the missing final newline back --
true for inter-subsection gaps, false here since nothing follows the section's
last `]`). Instead `section_text[prev_end:].split("\n")` is fed to
`_flush_comment_lines` directly. Hand-traced two cases character-by-character
(EOF right after one comment line; blank+comment+blank before a following
section header) and confirmed byte-identical round trip in both, and confirmed
every existing round-trip test in test_rule_sort.py has no trailing content
(text always ends `"]\n"`), so `trailing_comment` is `None` for all of them --
zero regression to the existing suite.

All 4 existing callers of `parse_permissions_section_with_comments`
(`toolguard/tools/annotate.py`, `toolguard/tools/maintenance.py`,
`toolguard/tools/config_access.py`, `toolguard/scripts/migrate_permissions.py`)
only ever iterate `perm_type in ("allow", "deny", "ask")` via
`.get(perm_type, [])`, confirmed by grep, so adding the new top-level key is
non-breaking. One existing test asserted an exact-dict-equality on the parsed
result (`test_empty_list_returns_empty_lists_for_all_subsections`); updated its
expected dict to include `"trailing_comment": None`.

New tests added to `test/unit/test_rule_sort.py`
(`TestReassemblePermissionsSectionRoundTrip`):
- `test_trailing_comment_after_final_array_survives_round_trip`
- `test_multiple_trailing_comment_lines_survive_round_trip`
- `test_whitespace_only_trailing_text_adds_no_spurious_output`
- `test_trailing_comment_survives_when_auto_sort_reorders_entries`

### M2: content-loss guard skipped on false premise (toolguard/tools/installer.py)

`cmd_register_hooks`'s `verified_write_config(settings_path, ..., "json")` call
passed no `expected_patterns`, with a comment claiming pattern preservation "has
no meaning for this file's shape." Wrong: Claude Code's `settings.json` can carry
native `permissions.allow/deny/ask` alongside the hooks this function merges, and
`patterns_in_config_text` already supports `file_format="json"` generically (it
reads `permissions`/`hard_deny` keys, ignoring `hooks`). Since this write rewrites
the WHOLE file, an undetected merge bug could silently drop a user's native
permission rules.

Fix: capture `original_text` unconditionally (was previously scoped only inside
the `if settings_path.exists()` branch) as `Optional[str]`, and compute
`expected_patterns = patterns_in_config_text(original_text, "json")` when the
file existed and had non-blank content, else `None` (explicit -- a brand-new or
empty file has no prior patterns to preserve, and passing blank text to
`patterns_in_config_text` would itself raise `JSONDecodeError`). Corrected the
misleading comment. `patterns_in_config_text` was already imported in this file.

New tests added to `test/unit/test_tools_installer.py` (`TestSummaryOutput`):
- `test_register_hooks_preserves_existing_native_permissions` -- seeds
  `settings.json` with `permissions.allow` entries, runs `register-hooks`,
  asserts they survive byte-for-byte and the hooks merge still happened.
- `test_register_hooks_refuses_write_that_would_drop_native_permissions` --
  patches `installer_module.json.dumps` to simulate a merge bug that strips the
  `permissions` key, asserts the CLI returns exit code 2
  (`ConfigWriteVerificationError`) and the original file on disk is left
  completely untouched.

## Files changed

- `toolguard/rule_sort.py` -- M1 fix (parse + reassemble) and docstring updates.
- `toolguard/tools/installer.py` -- M2 fix (`cmd_register_hooks`) and comment fix.
- `test/unit/test_rule_sort.py` -- 4 new tests + 1 existing test's expected dict
  updated for the new `trailing_comment` key.
- `test/unit/test_tools_installer.py` -- 2 new tests.

## Verification

- Baseline confirmed BEFORE any change: `uv run python -m unittest discover -s
  test -t .` -> `Ran 1789 tests ... OK`.
- After both fixes + new tests: `Ran 1795 tests ... OK` (1789 + 6 new, zero
  regressions).
- `uv run ruff format` run explicitly on only the 4 touched files (no bare
  `ruff format .`); all left unchanged/reformatted cleanly.
- `uv run ruff check .` (repo-wide, read-only): all checks passed.
- `uv run python -m py_compile` on all 4 touched files: OK.
- Anti-pattern scan (async/await, threading, local imports) on the 4 touched
  files: none found.
- Doc-drift sweep: grepped the whole repo for the old misleading comment string
  ("has no meaning for this file's shape") -- no other occurrences, so no
  further sweep needed.
- One ad-hoc `uv run python -c "..."` inline validation attempt for M1 was
  DENIED by the permission system before any file/content was touched; I did not
  retry or work around it -- switched immediately to writing the real unit
  tests and validating exclusively through the test runner, per the task's
  safety constraints.

## Safety confirmation

- Did NOT create, edit, delete, or move any of: `.claude/toolguard_hook.toml`,
  `.claude/settings*.json` (real, at any level), anything under
  `~/.toolguard/`, `~/.config/toolguard/`, or `~/.claude/`.
- All validation went through the isolated unit test suite
  (`InstallerTestCase`'s `Path.home()`-patched `TemporaryDirectory` fixture for
  the M2 tests; pure text-in/text-out functions with no file I/O for the M1
  tests, consistent with `test/unit/test_rule_sort.py`'s own documented
  isolation-exemption). No ad-hoc probe scripts touched real config.
- No write git operations were run (only read-only `git status`/`git diff
  --stat`).
- Verified no nested `toolguard-memories/toolguard-memories/...` directory was
  created by this task (a pre-existing nested directory/mixed add-delete
  already existed in `git status` from EARLIER, unrelated TOO-19 work before
  this task started -- not touched or added to here). This report itself was
  written directly to `toolguard-memories/TOO-19/` via the `toolguard`
  basic-memory project, directory `"TOO-19"` (no nesting).

## Elapsed time / rough cost estimate

- Phase 1 (planning: reading code, tracing M1 byte-by-byte, task recall memory):
  ~20 min.
- Phase 2 (implementation: both fixes + 6 new tests): ~25 min.
- Phase 3 (self-review: format/lint/anti-pattern scan/full suite runs x3):
  ~10 min.
- Phase 4 (this report + IDE handoff): ~5 min.
- Total: ~60 min. Estimated cost (Sonnet-class model, this conversation's token
  volume): roughly $2-4 total -- this was a small, well-scoped fix with no
  large file reads beyond the two target modules and their existing tests.
