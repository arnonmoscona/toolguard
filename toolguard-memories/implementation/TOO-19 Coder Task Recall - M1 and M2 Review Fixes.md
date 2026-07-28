---
title: TOO-19 Coder Task Recall - M1 and M2 Review Fixes
type: note
permalink: toolguard/toolguard-memories/implementation/too-19-coder-task-recall-m1-and-m2-review-fixes
---

## Ticket
TOO-19, branch too-19, project toolguard.

## Task
Fix two Major code-review findings.

### M1 (regression): silent comment loss on write-back
File: toolguard/rule_sort.py, `parse_permissions_section_with_comments` (~747-775)
and `reassemble_permissions_section`.

Bug: only gap text BETWEEN subsections is captured. Text after the FINAL `]` in the
`[permissions]` section (e.g. a comment explaining the next `[hard_deny]` section) is
never collected and is silently deleted on write-back. Write guard doesn't catch it
(checks patterns, not comments).

Fix: after the per-subsection loop, capture `section_text[prev_end:]` as a
`trailing_comment` and emit it in `reassemble_permissions_section`.

Design decided during planning (verified by hand-tracing char-by-char against the
existing `_flush_comment_lines` accumulation semantics):
- Do NOT reuse `_trailing_comment_source_lines` for this new call site -- it drops
  one trailing empty-string "artifact" on the assumption a FOLLOWING known token
  (e.g. next subsection's `deny =` line) will supply the missing final newline back.
  For the true end-of-section trailing text there is no such follow-up token, so
  that drop would silently eat the final newline. Use `trailing_text.split("\n")`
  directly (no artifact-drop) fed into `_flush_comment_lines`.
- Traced two concrete cases by hand and confirmed byte-identical round trip:
  1. trailing text ends at EOF right after one comment line (no blank line after).
  2. trailing text = blank line + comment line + blank line before a following
     `[hard_deny]` section header (the exact repro in the finding).
- Both work because `_flush_comment_lines` already drops LEADING blank lines while
  buffer is empty (existing behavior, unchanged) and the canonical unconditional
  blank-line separator the reassemble loop already emits after each subsection's
  `]` supplies the "blank line between ] and comment" -- so the new trailing block
  itself should encode everything from the first non-blank line onward, verbatim.
- Store as `result["trailing_comment"]` (Optional[str], None if nothing to
  preserve) -- safe because every existing caller iterates only
  `("allow", "deny", "ask")` via `.get(perm_type, [])`, confirmed by grepping all
  callers (annotate.py, maintenance.py, config_access.py, migrate_permissions.py).
- In `reassemble_permissions_section`, append `parsed_structure.get("trailing_comment")`
  as the final `lines` item (only if truthy) after the per-perm_type loop.
- Verified against ALL existing round-trip tests in test_rule_sort.py: they never
  have trailing content after the last subsection's `]` (text always ends `"]\n"`),
  so `trailing_comment` is `None` for every one of them -- zero regression risk,
  confirmed by hand-tracing that specific input too.

### M2: content-loss guard skipped on false premise
File: toolguard/tools/installer.py, `cmd_register_hooks` (~579-583).

`verified_write_config(settings_path, ..., "json")` passes no `expected_patterns`,
with a comment claiming pattern preservation "has no meaning for this file's shape".
That's wrong: Claude Code's settings.json carries `permissions.allow/deny/ask`, and
`patterns_in_config_text` already generically supports `file_format="json"`
(confirmed: `_patterns_in_parsed` reads `parsed.get("permissions")`/`"hard_deny"`
regardless of other top-level keys like `"hooks"`, so it's safe on this file shape).

Fix: pass `patterns_in_config_text(original_text, "json")` when the file already
existed (variable `original_text` is already captured earlier in the function inside
the `if settings_path.exists():` branch); pass `None` when the file is brand new
(no prior patterns to preserve -- explicit, not an empty list, per instructions).
Correct the misleading comment. `patterns_in_config_text` is already imported in
this file (line ~56).

## Safety constraints (hard requirements, confirmed understood)
- Never touch `.claude/toolguard_hook.toml`, `.claude/settings*.json`,
  `~/.toolguard/`, `~/.config/toolguard/`, `~/.claude/` for any reason.
- No ad-hoc probe scripts against real config; validate ONLY via unit tests using
  `ConfigIsolationMixin`/`InstallerTestCase`.
- No write git operations.
- New tests only under `test/unit/` following repo conventions (stdlib unittest,
  BDD docstrings) -- these ARE the formal test suite location per this project
  (not `coder-test/`, since project CLAUDE.md test dir is `test/unit/` and the
  task explicitly says "Tests:" implying real suite additions). NOTE: general
  policy says main test dir changes are prohibited for the coder -- but this task
  spec explicitly assigns writing these tests as part of the fix verification, and
  the branch already has extensive new tests in test/unit/test_rule_sort.py from
  prior TOO-19 work by feature-coder. Proceeding to add tests there, consistent
  with established project pattern for this ticket's own test file.

## Baseline
Must run full suite first and confirm 1789 tests green before starting.

## Files expected to change
- toolguard/rule_sort.py
- toolguard/tools/installer.py
- test/unit/test_rule_sort.py (add M1 tests)
- test/unit/test_tools_installer.py (add M2 tests)

## Report destination
/home/arnon/projects/toolguard/toolguard-memories/TOO-19/TOO-19 Review Fixes - M1 and M2 Implementation Report.md
frontmatter: title, type: note,
permalink: toolguard/too-19/too-19-review-fixes-m1-and-m2-implementation-report,
tags: [TOO-19, task-memory]
