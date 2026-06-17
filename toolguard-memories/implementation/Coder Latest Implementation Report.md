---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- coder-report
- TOO-8
- hard_deny
---

# Coder Implementation Report -- TOO-8 Phase 3 (hard_deny)

Date: 2026-06-17. Acting as feature-coder. Project: toolguard. Nothing committed (Arnon
does all git writes).

## Summary
Implemented the `[hard_deny]` unoverridable safety valve. A (typically less-specific)
toolguard_hook config can declare deny/allow pattern lists that NO more-specific config can
override. Checked FIRST, before the Phase 2 more-specific-wins cascade. Applies uniformly to
Bash, each compound sub-command (compound denied if any sub-command hard-denied), and
Read/Write/Edit file paths. Single resolution path; no behaviour change when unconfigured.

## Semantics implemented (per decision #3; flagged for Arnon's review)
- `[hard_deny]` = section with optional `deny` and `allow` wrapped-pattern lists.
- Read ONLY from toolguard_hook files (TOML/JSON), never native settings*.json.
- POOLED across ALL levels into one union (not per-level propagation).
- Checked FIRST: match any `deny` AND no `allow` carve-out => DENY (unoverridable). Else
  fall through to Phase 2 cascade unchanged.
- `allow` is ONLY a carve-out exception to `deny`; NOT a forced/normal allow; does not
  affect the cascade.
- Same extended syntax ([regex]/[glob]/[native]) + tool wrappers + matchers as normal perms.
- Relative file-path hard_deny patterns anchored to project root (reuses Phase 2
  `_anchor_file_pattern`).

## Files changed
- `toolguard/config.py`: added `Configuration.hard_deny(tool_name) -> (deny, allow)` pooled
  tool-scoped accessor (toolguard_hook layers only, wrapper-stripped, de-duped, most-specific
  first). Defensive guard ignores a malformed non-dict `hard_deny` value.
- `toolguard/permissions.py`: added `check_hard_deny(command, deny, allow, extended_syntax)`
  reusing `match_command`; returns ('deny', reason) or None (fall-through). Reason cites
  "hard_deny pattern: ... (cannot be overridden)".
- `toolguard/hook.py`: import `check_hard_deny`; added `_check_file_path_hard_deny` (anchors
  relative patterns, deny-first, carve-out exemption); `resolve_file_path_permission` now
  checks hard_deny FIRST; Bash `_resolve_one` closure in `main()` checks hard_deny per
  sub-command FIRST (so compound is hard-denied if any sub-command is).
- `technical-notes.md`: new "Hard-deny safety valve (TOO-8 Phase 3)" section with shape,
  semantics, integration points, and a review-flag note.
- `test/unit/test_hook.py`: added `hard_deny` method to the `_FakeConfig` test double so it
  stays in sync with the Configuration surface the hook now consumes (returns empty pools).
  See "Test-double change" note below.
- `test/unit/test_hard_deny.py` (NEW): 20 tests, all with Given/When/Then docstrings.

## hard_deny test list (test/unit/test_hard_deny.py, 20 tests)
TestHardDenyAccessor:
- test_hard_deny_pooled_across_multiple_levels (pooled union across levels)
- test_hard_deny_is_tool_scoped
- test_hard_deny_ignored_in_native_claude_layers (extension; native ignored)
- test_hard_deny_empty_when_unconfigured
- test_hard_deny_malformed_section_ignored (defensive guard)
TestHardDenyCommand:
- test_hard_deny_overrides_more_specific_allow (unoverridable vs more-specific allow)
- test_hard_deny_allow_carveout_exempts_command
- test_hard_deny_allow_carveout_does_not_exempt_other_commands
- test_hard_deny_at_ancestor_blocks_project_allow (ancestor blocks project allow)
- test_compound_hard_denied_if_any_subcommand_hard_denied
- test_no_hard_deny_leaves_cascade_unchanged (regression)
TestCheckHardDenyUnit (direct unit of check_hard_deny):
- test_returns_none_when_no_deny_patterns / _no_deny_match
- test_denies_on_deny_match_without_carveout
- test_carveout_returns_none
TestHardDenyFilePath:
- test_read_hard_deny_overrides_project_allow
- test_write_hard_deny_allow_carveout
- test_edit_hard_deny_relative_pattern_anchors_to_project_root (relative anchoring + outside
  project not hard-denied)
- test_no_hard_deny_leaves_file_path_cascade_unchanged (regression)
TestHardDenyThroughMain:
- test_main_bash_hard_deny_denies_despite_project_allow (end-to-end via hook main())

## Verification
- Full suite GREEN both ways: `unittest discover` = 654 OK; `env -u CLAUDE_SETTINGS_PATH`
  = 654 OK (was 634 baseline; +20 new).
- `ruff check toolguard/ test/` clean.
- py_compile clean on changed files.
- Coverage (tools/coverage_stdlib.py): every executable line of the new code runs
  (config.hard_deny body, permissions.check_hard_deny body, hook._check_file_path_hard_deny
  body, hook resolve wiring incl. the Bash `return hard` short-circuit, and the malformed
  guard `continue`). The only `>>>>>>` markers on new code are multi-line function-SIGNATURE
  continuation lines -- a known stdlib `trace` artifact affecting all multi-line defs, not
  logic. Effective coverage on changed lines ~100%, well above the >90% bar.
- Anti-pattern scan: no async/await/threading; no local imports in production additions
  (local imports only inside test functions, matching existing test style).

## Test-double change (flagged)
`test/unit/test_hook.py::_FakeConfig` is a test double standing in for the real
`Configuration`. The hook now calls `config.hard_deny(...)`, so the double needed the method
or 5 main()-path tests error. I added a no-op `hard_deny` returning empty pools -- a pure
sync-with-production-API completion, NOT a change of any test's intent or assertions. The
Phase 2 outcome note records Arnon previously authorised editing formal tests for TOO-8; I
applied that precedent narrowly here. Flag if you'd rather this be reverted/owned by you.

## Out of scope (untouched): Phases 4-7.

## Self-review notes
- "Checked first" is semantically honoured per sub-command/path. Edge case: in `main()`, the
  file-path and Bash branches each short-circuit to a fail-closed DENY when NO normal allow
  exists at any level, BEFORE reaching the resolver that checks hard_deny. Outcome is
  identical (deny); only the reason text differs (and only in the no-allow-anywhere case,
  which is not a Phase 3 scenario). Documented here for transparency; did not reorder to
  avoid touching the well-tested fail-closed gating.
