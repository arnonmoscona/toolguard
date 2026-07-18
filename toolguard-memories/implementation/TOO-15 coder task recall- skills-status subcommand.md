---
title: 'TOO-15 coder task recall: skills-status subcommand'
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-skills-status-subcommand
---

## Ticket / Context
TOO-15 wrap-up. Install/uninstall runbook hardening essentially done. Remaining completion-gate
item: bundled toolguard-maintenance skill needs to detect at START of a maintenance pass and
OFFER (never auto-apply) remediation for:
1. Stale/partial GLOBAL binary install (uv tool install behind tracked branch).
2. Bundled skills (toolguard-security-audit, toolguard-maintenance) not installed at user or
   project scope, robust to broken/dangling symlinks and directories missing SKILL.md.

## Reuse (do NOT reimplement)
- toolguard/tools/installer.py: `_BUNDLED_SKILL_NAMES`, `_claude_dir(scope, project_dir)`,
  `cmd_discover_projects`, `cmd_install_skills` (read both for style before writing).
- toolguard/update_check.py: `detect_install() -> InstallInfo` (git-install vs local vs unknown;
  never hangs/raises on network issues). Do NOT shell out to toolguard-update-check console script.

## Task 1: New subcommand `toolguard-install skills-status`
- Add `cmd_skills_status` in toolguard/tools/installer.py, wired into argparse the same way as
  other subcommands (find `_build_parser()`); help text constant above function.
- NOT `_add_scope_args` (that's single-scope) -- this always checks BOTH scopes. Look at how
  discover-projects sets up its own args as precedent.
- Args: `--project-dir PROJECT_DIR` (optional, default = cwd), `--format {text,json}` (default text).
- For each name in _BUNDLED_SKILL_NAMES x each scope in ("user","project"):
  resolve `_claude_dir(scope, project_dir) / "skills" / name`, classify:
  - missing: `Path.exists()` is False (correctly False for broken symlink -- verify with live test)
  - installed: path is a dir (real or symlink to real dir) AND `path/"SKILL.md"` is a file
  - invalid: exists() True but not "installed" criteria (empty dir, non-dir, etc). Distinct
    reportable state, not collapsed into missing.
- Include binary-install status block from detect_install(): kind, whether update available,
  unknown/offline handled plainly.
- text format: house style like cmd_discover_projects prints (indented sections, no repr dumps).
- json format: top-level `binary` and `skills` keys; consistent with toolguard-audit --format json
  shape (check that module first).
- Exit code always 0 (read-only diagnostic). Only raise InstallerError for genuine fs/permission
  errors, not for missing/invalid/stale states.

## Task 2: Tests
New TestSkillsStatus class in test/unit/test_tools_installer.py, following TestDiscoverProjects
style (read first). Cover:
- Fresh state: both skills missing both scopes.
- Both fully installed both scopes (real dirs w/ SKILL.md).
- Symlink to REAL valid skill dir elsewhere -> installed (not missing). Dogfooding uses symlinks.
- BROKEN/dangling symlink (os.symlink to nonexistent target) -> missing, no crash. THE key footgun
  case, must not skip.
- Real dir but no SKILL.md -> invalid.
- Binary-install-status block: mock toolguard.update_check.detect_install (see
  test/unit/test_update_check.py mocking style -- unittest.mock.patch, no real git/network calls).
- --format json produces valid parseable JSON with expected keys.
- Every test needs Given/When/Then BDD docstring per CLAUDE.md.
- Full suite green: `uv run python -m unittest discover -s test -t .`
- ruff format . and ruff check . clean (only touch changed files, not repo-wide reformat).

## Task 3: Wire into skills/toolguard-maintenance/SKILL.md (doc only)
- Add short new step EARLY in flow (read "How this skill runs -- the passes" and "First run vs
  periodic" sections first; insertion point likely right at the very start, before
  redundancy/consolidation passes -- this is pre-flight setup check).
- Instruct agent to run `toolguard-install skills-status`, respecting skill's ALREADY-ESTABLISHED
  --dev vs default-console-script convention (read "Development mode (toolguard maintainers
  only -- the ONLY exception)" section, follow exactly; never hardcode uv run python -m as default).
- If binary update available: tell user, offer `uv tool upgrade toolguard`, NEVER auto-run (match
  skill's existing "no auto-apply, ever" posture from Hard constraints).
- If any bundled skill missing/invalid at a scope: tell user which + where, offer
  `toolguard-install install-skills`, explicitly asking user to choose scope per item (explain
  audit/maintenance lean user-level, project-specific lean local). Never install without explicit
  per-item choice.
- If everything current/complete: say so briefly, move on to normal flow.
- Keep concise, match existing voice/heading level/terseness.

## Out of scope
- Do not touch docs/install.md, docs/uninstall.md, toolguard-security-audit skill.
- Do not reimplement git/network/version-comparison logic from update_check.py.
- Do not add new dependency (stdlib only: pathlib/argparse/json).
- Do not touch PEG grammar or command_extractor.py.

## Success criteria
- New subcommand works per spec, exit code 0 always for diagnostic states, InstallerError only for
  genuine fs errors.
- Tests cover all 7 scenarios above including the broken-symlink footgun case.
- Full existing suite stays green.
- ruff format/check clean on touched files only.
- SKILL.md updated per spec, matching house style.
- Report: files added/modified w/ line refs, test count before/after, ruff/suite confirmation.
- Arnon reviews diff himself; do not mark done in any tracking system.

## Scope inflation guard
This should be: 1 file modified (installer.py) substantially, 1 test file modified substantially,
1 skill markdown file modified lightly = 3 files total. Well within limits.
