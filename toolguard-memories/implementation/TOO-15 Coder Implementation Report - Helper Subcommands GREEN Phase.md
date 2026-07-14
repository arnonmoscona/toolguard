---
title: TOO-15 Coder Implementation Report - Helper Subcommands GREEN Phase
type: note
permalink: toolguard/implementation/too-15-coder-implementation-report-helper-subcommands-green-phase
tags:
- TOO-15
- task-memory
- coder-implementation-report
---

## Status: GREEN -- complete, approved plan implemented, full suite passing

Coordinator independently verified the RED state (re-ran suite, matched 1427/failures=4/errors=19
exactly, reviewed both test file diffs directly) and approved the `[hard_deny]` design plan
(mirror `cmd_enable_takeover`'s precedent rather than extending `write_toml_config`). Proceeded to
implement.

Full details in the scratchpad report (GREEN PHASE section at the bottom):
`/tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-helper-subcommands-report.md`

## Summary

- New: `toolguard/tools/recommended_protections.py` -- `RecommendedProtection` frozen dataclass +
  `required_hard_deny_patterns()` returning the 8 canonical "Sensitive files" patterns verbatim
  from docs/security.md, mirroring `self_permission.py`'s declarative shape.
- Modified: `toolguard/tools/installer.py` -- implemented `cmd_discover_projects`,
  `cmd_install_skills`, `cmd_seed_hard_deny` (plus their helpers and `--help` text), wired into
  `_build_parser()`, and added the one-line `traces/` bullet to `_README_TEMPLATE`. `seed-hard-deny`
  reuses the existing `_replace_or_append_toml_section`/`find_section_boundaries` machinery (the
  same approach `enable-takeover` already uses for `[takeover_mode]`) rather than extending
  `write_toml_config` (confirmed `[permissions]`-specific).

## Verification

- `uv run python -m unittest discover -s test -t .` -> **1430 tests, OK** (0 failures/errors).
  (1430 not 1427: `test_recommended_protections.py` now collects its 4 real tests instead of
  unittest's 1 synthetic import-failure placeholder -- net +3, fully reconciles.)
- `uv run ruff check .` -> All checks passed (whole project).
- `py_compile` clean on both changed production files.
- Anti-pattern scan: no async/await, no threading, no local imports.
- JetBrains inspection: one pre-existing out-of-scope warning (untouched), one lambda-shadowing
  weak-warning fixed (`lambda record: ...` -> `lambda entry: ...`), re-verified clean after.
- Focused verbose run of all new/changed test classes: 33/33 pass.
- Cross-checked every `--help` test's asserted substring against the actual help text
  programmatically -- all present.

No commit or push performed, per instructions.
